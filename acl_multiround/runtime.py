"""Per-process bindings to immutable current-parent evidence and full-ten evaluator."""
import ast
import copy
import json
from pathlib import Path
import time
import yaml
from acl_frameworks.common import ROOT,read,sha
from acl_frameworks.context import EvidenceWorkspace
from acl_rsi.settings import write_json,load_instances
from acl_gepa_swe.feedback import record
from acl_gepa_swe.executor import SWEExecutor
from acl_unified import common as frozen
from .protocol import WORK,BASE,H0,FILES,round_dir,SCOPE


def initial_state(ids):
    instances=load_instances({'dataset':str(ROOT/'benchmarks/datasets/swe-bench-verified-mini/test.json'),'evolve_ids':ids,'heldout_ids':[]})
    scores={i:record(BASE/'trials'/i,i,instances[i],trace=False)['score'] for i in ids}
    return {'harness':str(H0),'harness_sha256':frozen.fingerprint(H0),'scores':scores,
        'trials':{i:str(BASE/'trials'/i) for i in ids},'source_round':0}


def parent_state(name,index,ids):
    state=initial_state(ids) if index==1 else read(round_dir(name,index-1)/'result.json')['next_parent']
    if frozen.fingerprint(Path(state['harness']))!=state['harness_sha256']:raise ValueError('Parent harness changed')
    if set(state['scores'])!=set(ids) or set(state['trials'])!=set(ids):raise ValueError('Incomplete parent evidence')
    return state


def bind(cfg,instances,work,parent):
    ids=cfg['protocol']['all_task_ids']
    work=Path(work)
    parent_harness=Path(parent['harness'])
    original_validate=frozen.validate
    def validate(folder,*,require_change=True,contract=True):
        # Global YAML/security constraints always stay relative to original H0.
        result=original_validate(folder,require_change=False,contract=contract)
        folder=Path(folder)
        if require_change:
            same_ast=ast.dump(ast.parse((folder/'agent.py').read_text()))==ast.dump(ast.parse((parent_harness/'agent.py').read_text()))
            same_yaml=yaml.safe_load((folder/'swebench.yaml').read_text())==yaml.safe_load((parent_harness/'swebench.yaml').read_text())
            if same_ast and same_yaml:raise frozen.InvalidCandidate('No semantic change relative to current parent')
        return result
    def baseline_trial(iid):return Path(parent['trials'][iid])
    def export(root,requested):
        if set(requested)!=set(ids):raise ValueError('Export must contain all ten current-parent histories')
        ws=EvidenceWorkspace(root)
        if (ws.root/'snapshot.json').exists():raise ValueError('Do not overwrite evidence')
        rows=[]
        for iid in requested:
            trial=baseline_trial(iid)
            score=record(trial,iid,instances[iid],trace=False)
            if score['score']!=parent['scores'][iid]:raise ValueError('Parent score/source mismatch')
            messages=[]
            for m in read(trial/'trajectory.json').get('messages',[]):
                clean={k:m[k] for k in ('role','content','tool_calls','tool_call_id') if k in m}
                if m.get('extra',{}).get('actions'):clean['extra']={'actions':m['extra']['actions']}
                messages.append(clean)
            target=ws.root/'history'/iid
            write_json(target/'trajectory.json',{'messages':messages})
            write_json(target/'feedback.json',{'problem_statement':instances[iid]['problem_statement'],
                'resolved':score['score'],'stop':score['stop'],'usage':score['usage']})
            rows.append({'task_id':iid,'trajectory_sha256':sha(target/'trajectory.json'),'feedback_sha256':sha(target/'feedback.json')})
        frozen.copy_harness(parent_harness,ws.root/'harness')
        for previous in sorted(work.parent.glob('round-*/result.json')):
            if previous.parent==work:continue
            old=read(previous)
            brief={k:old.get(k) for k in ('round','status','proposal_status','native_selected','evaluated_kind','round_scores','native_error')}
            write_json(ws.root/'history/rounds'/f'{previous.parent.name}.json',brief)
        write_json(ws.root/'snapshot.json',{'scope':'all ten current-parent public histories; no heldout',
            'tasks':rows,'harness':frozen.fingerprint(parent_harness),'source_round':parent['source_round']})
        return ws
    class Evaluator:
        def __init__(self,settings,task_instances,directory):
            self.cfg,self.instances,self.work=settings,task_instances,Path(directory)
            self.executor=SWEExecutor(settings,self.work,task_instances)
        def __call__(self,name,harness,requested,**kwargs):
            if not set(requested)<=set(ids):raise ValueError('Unexpected task')
            if name in ('h0','initial'):return {i:parent['scores'][i] for i in requested}
            validate(harness)
            folder=self.work/'evaluations/candidate'
            if not (folder/'harness').exists():frozen.copy_harness(harness,folder/'harness')
            if frozen.fingerprint(harness)!=frozen.fingerprint(folder/'harness'):raise frozen.InvalidCandidate('One immutable candidate per round')
            frozen.preflight()
            scores={}
            for iid in requested:
                print(f'[full10] {work.parent.name}/{work.name} candidate {iid}',flush=True)
                self.executor.trial(iid,folder)
                scores[iid]=record(folder/'trials'/iid,iid,instances[iid],trace=False)['score']
                write_json(work/'progress.json',{'phase':'candidate_evaluation','latest_task':iid,
                    'graded_tasks':len(list((folder/'trials').glob('*/grade.json'))),'updated_at':time.time()})
            return scores
    # These are process-local bindings; no old source/config files are edited.
    frozen.validate=validate;frozen.export=export;frozen.baseline_trial=baseline_trial;frozen.Evaluator=Evaluator
    return {'validate':validate,'export':export,'Evaluator':Evaluator,'baseline_trial':baseline_trial,'parent':parent_harness}


def retest_parent(cfg,instances,work,parent):
    folder=work/'evaluations/unchanged-parent'
    frozen.copy_harness(Path(parent['harness']),folder/'harness')
    frozen.preflight()
    executor=SWEExecutor(cfg,work,instances)
    scores={}
    for iid in cfg['protocol']['all_task_ids']:
        print(f'[full10] {work.parent.name}/{work.name} unchanged-parent {iid}',flush=True)
        executor.trial(iid,folder)
        scores[iid]=record(folder/'trials'/iid,iid,instances[iid],trace=False)['score']
        write_json(work/'progress.json',{'phase':'unchanged_parent_retest','latest_task':iid,
            'graded_tasks':len(list((folder/'trials').glob('*/grade.json'))),'updated_at':time.time()})
    return folder,scores
