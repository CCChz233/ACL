"""Shared constraints, live evaluation and public fresh-baseline evidence export."""
import ast
import copy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import yaml

from acl_frameworks.common import ROOT, read, sha
from acl_frameworks.context import EvidenceWorkspace
from acl_gepa_swe.executor import SWEExecutor
from acl_gepa_swe.feedback import record
from acl_rsi.settings import load_instances, load_settings, write_json
from .protocol import WORK, CONFIG, H0, FILES, EDITABLE


class InvalidCandidate(ValueError):
    pass


def baseline_trial(iid):
    return WORK / 'baseline/evaluations/h0/trials' / iid


def copy_harness(source, target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copy2(Path(source) / f, target / f)
    return target


def fingerprint(folder):
    return {f: sha(Path(folder)/f) for f in FILES}


def validate(folder, *, require_change=True, contract=True):
    from acl_dgm.adapter import validate as structure
    folder = Path(folder)
    try:
        structure(folder, H0)
        old, new = yaml.safe_load((H0/'swebench.yaml').read_text()), yaml.safe_load((folder/'swebench.yaml').read_text())
        comparison = copy.deepcopy(new)
        for section, keys in EDITABLE.items():
            for key in keys:
                if not isinstance(new.get(section, {}).get(key), str):
                    raise ValueError('Missing prompt template')
                comparison[section][key] = old[section][key]
        if comparison != old:
            raise ValueError('YAML outside the four prompt strings changed')
        if require_change and fingerprint(folder) == fingerprint(H0):
            raise ValueError('No operation candidate')
        tree = ast.parse((folder/'agent.py').read_text())
        # Workers still load Python on the controller host; reject direct host/API access.
        forbidden = {'os','subprocess','socket','httpx','requests','urllib','docker','openai','importlib','shutil'}
        for n in ast.walk(tree):
            modules = [a.name.split('.')[0] for a in n.names] if isinstance(n, ast.Import) else ([n.module.split('.')[0]] if isinstance(n, ast.ImportFrom) and n.module else [])
            if forbidden.intersection(modules):
                raise ValueError('Direct host/API access import')
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {'eval','exec','__import__','open','compile'}:
                raise ValueError('Direct host execution/file access')
            if isinstance(n, ast.Attribute) and n.attr in {'ledger','client','__globals__','__subclasses__'}:
                raise ValueError('External provider/budget access')
        original = {f:(H0/f).read_text() for f in ('agent.py','swebench.yaml')}
        added = '\n'.join(line for f in original for line in (folder/f).read_text().splitlines() if line not in original[f].splitlines())
        dataset = read(ROOT/'benchmarks/datasets/swe-bench-verified-mini/test.json')
        if any(r['instance_id'] in added for r in dataset) or any(s in added.lower() for s in ('django','sphinx','deepseek_api_key','test_patch','fail_to_pass','pass_to_pass')):
            raise ValueError('Task-specific or private/credential content')
        if contract:
            protocol_contract(folder)
    except InvalidCandidate:
        raise
    except Exception as error:
        raise InvalidCandidate(f'{type(error).__name__}: {str(error)[:240]}') from error


def protocol_contract(folder):
    from acl_dgm.runtime import NativeMiniModel
    from acl_rsi.worker import load_agent
    templates = yaml.safe_load((Path(folder)/'swebench.yaml').read_text())
    def no_api(**kwargs):
        raise AssertionError('Offline gate called a model')
    no_api.ledger = SimpleNamespace(summary=lambda:{})
    model = NativeMiniModel({'model':'deepseek-flash'}, templates['model'], no_api)
    result = []
    for commands in (['echo probe'], ['echo first','echo second'],
                     ['echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt'],
                     ['echo before','echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt','echo after']):
        env = SimpleNamespace(execute=lambda a:{'output':'fixture output','returncode':0,'exception_info':''},
                              get_template_vars=lambda:{}, serialize=lambda:{})
        agent = load_agent(Path(folder)/'agent.py')(model,env,**templates['agent'])
        actions = [{'command':c,'tool_call_id':f'fixture_{i}'} for i,c in enumerate(commands)]
        message = {'role':'assistant','content':'','extra':{'actions':actions},'tool_calls':[
            {'id':a['tool_call_id'],'type':'function','function':{'name':'bash','arguments':json.dumps({'command':a['command']})}} for a in actions]}
        outputs = agent.execute_actions(message)
        returned = [r['tool_call_id'] for r in outputs if r.get('role')=='tool']
        if returned != [a['tool_call_id'] for a in actions]:
            raise ValueError('Tool result pairing/order mismatch')
        # If a candidate pauses submission, reissuing must still return paired results.
        outputs2 = agent.execute_actions(message)
        if [r['tool_call_id'] for r in outputs2 if r.get('role')=='tool'] != returned:
            raise ValueError('Repeated action tool result mismatch')
        result.append({'tool_calls':len(actions),'paired':len(returned)})
    return result


def preflight():
    import docker
    from scripts.run_swe_local import require_cache
    client = docker.from_env(timeout=60)
    try:
        require_cache(client, read(ROOT/'configs/swe-mini-image-cache.json'))
        if shutil.disk_usage(ROOT).free < 4294967296:
            raise RuntimeError('Disk guard; images retained')
    finally:
        client.close()


def settings(name):
    path = WORK / name / 'config.json'
    if not path.exists():
        cfg = read(CONFIG)
        cfg.update(workspace=str(WORK/name), evolve_ids=cfg['protocol']['development_ids'], heldout_ids=[])
        write_json(path,cfg)
    cfg = load_settings(path)
    if cfg['model'] != 'deepseek-flash' or cfg['api_base'].rstrip('/') != 'https://api.deepseek.com' or cfg['thinking']:
        raise ValueError('Fixed provider configuration required')
    return cfg


def export(root, ids):
    expected = read(CONFIG)['protocol']['development_ids']
    if set(ids) != set(expected):
        raise ValueError('Only the four development histories can be exported')
    ws = EvidenceWorkspace(root)
    if (ws.root/'snapshot.json').exists():
        raise ValueError('Public snapshot already exists')
    cfg=load_settings(CONFIG); instances=load_instances(cfg)
    rows=[]
    for iid in ids:
        trial=baseline_trial(iid)
        row=record(trial,iid,instances[iid],trace=False)
        messages=[]
        for m in read(trial/'trajectory.json').get('messages',[]):
            clean={k:m[k] for k in ('role','content','tool_calls','tool_call_id') if k in m}
            if m.get('extra',{}).get('actions'):
                clean['extra']={'actions':m['extra']['actions']}
            messages.append(clean)
        target=ws.root/'history'/iid
        write_json(target/'trajectory.json',{'messages':messages})
        write_json(target/'feedback.json',{'problem_statement':instances[iid]['problem_statement'],
            'resolved':row['score'],'stop':row['stop'],'usage':row['usage']})
        rows.append({'task_id':iid,'trajectory_sha256':sha(target/'trajectory.json'),'feedback_sha256':sha(target/'feedback.json')})
    copy_harness(H0,ws.root/'harness')
    write_json(ws.root/'snapshot.json',{'scope':'fresh baseline, historical development tasks, report feedback sealed',
        'tasks':rows,'harness':fingerprint(ws.root/'harness')})
    return ws


class Evaluator:
    def __init__(self,cfg,instances,work):
        self.cfg,self.instances,self.work=cfg,instances,Path(work)
        self.executor=SWEExecutor(cfg,self.work,instances)

    def __call__(self,name,harness,ids,*,report=False):
        allowed = self.cfg['protocol']['report_ids'] if report else self.cfg['protocol']['development_ids']
        if not set(ids) <= set(allowed):
            raise ValueError('Evaluation permission violation')
        if name in ('h0','initial'):
            return {i:record(baseline_trial(i),i,self.instances[i],trace=False)['score'] for i in ids}
        validate(harness)
        folder=self.work/'evaluations/candidate'
        if not (folder/'harness').exists():
            copy_harness(harness,folder/'harness')
        if fingerprint(harness) != fingerprint(folder/'harness'):
            raise InvalidCandidate('Only one immutable candidate is permitted')
        preflight()
        scores={}
        for iid in ids:
            print(f'[unified] {self.work.name} {iid}',flush=True)
            self.executor.trial(iid,folder)
            scores[iid]=record(folder/'trials'/iid,iid,self.instances[iid],trace=False)['score']
            write_json(self.work/'progress.json',{'latest_task':iid,'latest_score':scores[iid],
                'scored_tasks':[p.parent.name for p in (folder/'trials').glob('*/grade.json')]})
        return scores
