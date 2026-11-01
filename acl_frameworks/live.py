"""Bounded real engineering pilots; native search logic, explicit SWE boundaries."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

import yaml

from acl_rsi.settings import load_instances, load_settings, write_json
from acl_rsi.deepseek import UsageLedger
from acl_gepa_swe.common import BASE, HARNESS
from acl_gepa_swe.executor import SWEExecutor
from acl_gepa_swe.feedback import record
from .common import ROOT, REGISTRY, read, sha, verify
from .context import export_baseline
from .provider import RecordedDeepSeek, bind_litellm
from .proposer import DeepSeekFileProposer
from .meta_harness import MetaHarnessAdapter

IDS = ['django__django-11790', 'django__django-11815']
AGENT_FILE = 'src/minisweagent/agents/default.py'
YAML_FILE = 'src/minisweagent/config/benchmarks/swebench.yaml'
SCOPE = ('Deployment permits edits ONLY to '+AGENT_FILE+' and '+YAML_FILE+'. '
         'The actual evaluator overrides source defaults: max_calls=50, max_tokens=1000000, '
         'max_output_tokens=4096, wall_seconds=1200. Source defaults such as step_limit=250 are NOT the task budget. '
         'Do not add other files. Keep the existing tool-call interface, fixed DeepSeek model, '
         'budgets and submission command. Private grader output is unavailable; binary outcomes '
         'and the agent own interactions are the complete feedback. Make a generic change, '
         'never task-specific solutions. This is a two-task engineering pilot, not heldout evaluation.')


def prepare(work):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    config_path = work / 'config.json'
    if config_path.exists():
        cfg = load_settings(config_path)
        lock = read(work / 'lock.json')
        if lock['config_sha256'] != sha(config_path):
            raise ValueError('Pilot configuration changed')
        runtime = (read(work / 'runtime-repair.json')['runtime']
                   if (work / 'runtime-repair.json').exists() else lock['runtime'])
        for file, digest in runtime.items():
            if sha(ROOT / file) != digest:
                raise ValueError('Pilot runtime changed; preserve run and use a new workspace')
        return cfg, load_instances(cfg)
    cfg = read(ROOT / 'configs/mini50-baseline.json')
    cfg.update(purpose='new-frameworks-one-round-engineering-pilot', workspace=str(work),
               evolve_ids=IDS, heldout_ids=[], model='deepseek-flash', api_base='https://api.deepseek.com')
    cfg['search'] = {'max_calls': 80, 'max_tokens': 1000000, 'max_output_tokens': 4096}
    cfg['protocol'] = {'iterations': 1, 'candidates_per_framework': 1,
        'train_ids': [IDS[0]], 'selection_ids': [IDS[1]], 'heldout': False,
        'baseline_reused': str(BASE), 'max_new_target_trials_per_framework': 2,
        'optimizer_limits_per_framework': cfg['search'], 'editable_files': [AGENT_FILE, YAML_FILE]}
    cfg['image_cache']['mode'] = 'local_only_retained'
    write_json(config_path, cfg)
    write_json(work / 'storage-policy.json', {'retain_mini_images': True, 'local_only': True})
    write_json(work / 'lock.json', {'config_sha256': sha(config_path),
        'frameworks': {name: verify(name)[0]['revision'] for name in read(REGISTRY)['frameworks']},
        'runtime': {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / 'acl_frameworks').glob('*.py')},
        'initial_harness': {p.name: sha(p) for p in HARNESS.iterdir() if p.is_file()}})
    return load_settings(config_path), load_instances(load_settings(config_path))


def gateway(cfg, work, role):
    provider = {k: cfg[k] for k in ('model', 'api_base', 'thinking')}
    limits = copy.deepcopy(cfg['search'])
    adjustment = work / 'optimizer-budget-adjustment.json'
    if adjustment.exists():
        for key in ('max_calls', 'max_tokens'):
            limits[key] = min(limits[key], read(adjustment)[key])
    provider.update(limits=limits, context_strategy='full', xml_dsml_compat=role != 'propose')
    return RecordedDeepSeek(provider, work / 'optimizer-api', role, enabled=True)


class Evaluator:
    def __init__(self, cfg, instances, work):
        self.cfg, self.instances, self.work = cfg, instances, Path(work)
        self.executor = SWEExecutor(cfg, self.work, instances)

    def __call__(self, name, harness, ids):
        if name == 'h0':
            return {i: record(BASE / 'runs/swe/jobs/base' / i / 'trial-0', i,
                              self.instances[i], trace=False)['score'] for i in ids}
        folder = self.work / 'evaluations' / name
        destination = folder / 'harness'
        if not destination.exists():
            shutil.copytree(harness, destination)
        for file in ('agent.py', 'swebench.yaml', 'LICENSE.md'):
            if sha(destination / file) != sha(Path(harness) / file):
                raise ValueError('Candidate changed after evaluation began')
        import docker
        from scripts.run_swe_local import require_cache
        client = docker.from_env(timeout=60)
        try:
            require_cache(client, read(ROOT / 'configs/swe-mini-image-cache.json'))
        finally:
            client.close()
        scores = {}
        for iid in ids:
            print(f'[pilot] evaluate {name} {iid}', flush=True)
            self.executor.trial(iid, folder)
            scores[iid] = record(folder / 'trials' / iid, iid, self.instances[iid], trace=False)['score']
        return scores


def public_run(public, traces, evaluation, ids, source_trials):
    """Translate real outcomes/own traces to native HF layout, without grader details."""
    result = {'resolved_ids': [], 'unresolved_ids': [], 'error_ids': [], 'empty_patch_ids': []}
    for iid in ids:
        trial = source_trials(iid)
        feedback = record(trial, iid, read_public_instance(iid), trace=False)
        # Snapshot exporter already allowlists original baseline messages. For
        # candidate trajectories, keep the same public message fields.
        raw = read(trial / 'trajectory.json') if (trial / 'trajectory.json').exists() else {'messages': []}
        messages = []
        for m in raw.get('messages', []):
            clean = {k: m[k] for k in ('role', 'content', 'tool_calls', 'tool_call_id') if k in m}
            if m.get('extra', {}).get('actions'):
                clean['extra'] = {'actions': m['extra']['actions']}
            messages.append(clean)
        trajectory = {'messages': messages, 'info': {'exit_status': feedback['stop'],
            'model_stats': {'api_calls': feedback['usage'].get('calls', 0), 'instance_cost': None}}}
        write_json(traces / iid / f'{iid}.traj.json', trajectory)
        key = 'resolved_ids' if feedback['score'] else 'unresolved_ids'
        result[key].append(iid)
        if not (trial / 'patch.diff').read_text().strip():
            result['empty_patch_ids'].append(iid)
    write_json(evaluation / 'results.json', result)


def read_public_instance(iid):
    # record() only needs the instance when trace=True, but supply a real public
    # instance consistently; never make private test fields optimizer-visible.
    return next(r for r in read(ROOT / 'benchmarks/datasets/swe-bench-verified-mini/test.json') if r['instance_id'] == iid)


def install_sandbox(public, audit):
    """Run native Bash tools in a local cached container, never on the host."""
    import minisweagent.environments.local as local
    from minisweagent.environments.docker import DockerEnvironment
    from acl_rsi.worker import image_name
    public = Path(public).resolve()
    live = []
    class SandboxEnvironment(DockerEnvironment):
        def __init__(self, **kwargs):
            env = kwargs.get('env', {})
            mounts = ['--volume', f'{public}:{public}:ro']
            target = env.get('TARGET_DIR')
            if target:
                target = Path(target).resolve()
                if not target.is_relative_to(public / 'native/task_agent'):
                    raise ValueError('Unexpected writable target')
                mounts += ['--volume', f'{target}:{target}:rw']
            super().__init__(image=image_name(IDS[0]), cwd=str(public / 'native'),
                timeout=kwargs.get('timeout', 120), env=env,
                run_args=['--rm', '--platform', 'linux/amd64', '--network', 'none',
                          '--cpus', '2', '--memory', '2g', *mounts])
            live.append(self)

        def execute(self, action, cwd='', *, timeout=None):
            started = time.time()
            try:
                return super().execute(action, cwd, timeout=timeout)
            finally:
                audit.parent.mkdir(parents=True, exist_ok=True)
                with audit.open('a') as handle:
                    handle.write(json.dumps({'time': started, 'command': action.get('command'),
                                             'seconds': time.time()-started})+'\n')
    original = local.LocalEnvironment
    local.LocalEnvironment = SandboxEnvironment
    def close():
        local.LocalEnvironment = original
        for env in live:
            if env.container_id:
                subprocess.run(['docker', 'rm', '-f', env.container_id], capture_output=True, timeout=60)
                env.container_id = None
    return close


def hf_run(cfg, instances, work, candidate_version=1):
    if candidate_version != 1:
        raise ValueError('Pilot must start at native version 1; start-version N assumes base N-1 was accepted')
    public = work / 'optimizer'
    _, source = verify('harnessfix')
    native = public / 'native'
    if not native.exists():
        export_baseline(public, IDS)
        shutil.copytree(source, native, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.env'))
        shutil.copytree(ROOT / 'agents/mini-swe-agent', public / 'h0-agent',
                        ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '*.egg-info'))
        shutil.copy2(HARNESS / 'agent.py', public / 'h0-agent' / AGENT_FILE)
        shutil.copy2(HARNESS / 'swebench.yaml', public / 'h0-agent' / YAML_FILE)
        # Confine a bounded pilot to the same deployment surface in both systems.
        for file in ('failure_analysis/analysis_config_swe.yaml', 'enhancement_implementation/config_swe.yaml'):
            p = native / file
            data = yaml.safe_load(p.read_text())
            data['agent']['system_template'] += '\n\n'+SCOPE
            data['agent']['step_limit'] = 20 if 'analysis' in file else 40
            data['agent']['cost_limit'] = 0
            p.write_text(yaml.safe_dump(data, sort_keys=False))
    spec = importlib.util.spec_from_file_location('acl_live_hf', native / 'run_pipeline_swe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ORIGINAL_AGENT_DIR = public / 'h0-agent'
    module.VENV_PYTHON = Path(sys.executable)
    module.RUN_LABEL = 'pilot'
    for split, ids in [('train', IDS[:1]), ('val', IDS[1:])]:
        folder = native / 'data' / f'acl_{split}'
        folder.mkdir(exist_ok=True)
        (folder / 'instance_ids.txt').write_text('\n'.join(ids)+'\n')
    evaluator = Evaluator(cfg, instances, work)
    outcomes = {}
    def boundary(split, version):
        ids = IDS[:1] if split == 'train' else IDS[1:]
        if split == 'train':
            traces, evaluation = module.train_traces_dir(cfg['model'], version), module.train_eval_dir(cfg['model'], version)
        else:
            traces = module.val_traces_dir_for_base(cfg['model'], version)
            evaluation = module.val_eval_dir_for_base(cfg['model'], version)
        if version == 0:
            source_trials = lambda i: BASE / 'runs/swe/jobs/base' / i / 'trial-0'
        else:
            full = module.enhanced_agent_dir(version)
            from failure_analysis.plan_diff_audit import _changed_files
            changed = _changed_files(public / 'h0-agent', full)
            if set(changed) - {AGENT_FILE, YAML_FILE}:
                raise ValueError('Candidate modifies unsupported deployment files: '+str(changed))
            flat = public / 'candidates' / f'v{version}' / 'harness'
            flat.mkdir(parents=True, exist_ok=True)
            for src, dest in [(AGENT_FILE, 'agent.py'), (YAML_FILE, 'swebench.yaml')]:
                shutil.copy2(full / src, flat / dest)
            shutil.copy2(HARNESS / 'LICENSE.md', flat / 'LICENSE.md')
            scores = evaluator(f'v{version}', flat, ids)
            outcomes.update(scores)
            source_trials = lambda i: work / 'evaluations' / f'v{version}' / 'trials' / i
        public_run(public, traces, evaluation, ids, source_trials)
        return traces, evaluation
    module.step_train_inference = lambda base_version, **kw: boundary('train', base_version)[0]
    module.step_train_evaluate = lambda base_version, **kw: module.train_eval_dir(cfg['model'], base_version)
    module.step_val_baseline_inference = lambda **kw: boundary('val', 0)[0]
    module.step_val_baseline_evaluate = lambda **kw: module.val_baseline_eval_dir(cfg['model'])
    module.step_val_inference = lambda version, **kw: boundary('val', version)[0]
    module.step_val_evaluate = lambda version, **kw: module.val_enhanced_eval_dir(cfg['model'], version)
    original_run = module.run
    def dispatch(command, **options):
        script = Path(command[1]) if len(command) > 1 else Path('')
        if script.name in ('run_analysis.py', 'aggregate_results.py'):
            stage = 'diagnosis' if script.name == 'run_analysis.py' else 'planning'
            bind_litellm(gateway(cfg, work, stage))
            old = sys.argv
            sys.argv = [str(p) for p in command[1:]]
            try:
                if stage == 'planning':
                    # Append deployment constraints to the module prompt, without
                    # changing its clustering, planner or spec validation logic.
                    spec = importlib.util.spec_from_file_location('acl_live_aggregate', script)
                    agg = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(agg)
                    agg.SYSTEM_PROMPT += '\n\n'+SCOPE
                    agg.AGG_AGENT_STEP_LIMIT = 20
                    agg.AGG_AGENT_COST_LIMIT = 0
                    agg.main()
                else:
                    runpy.run_path(str(script), run_name='__main__')
            finally:
                sys.argv = old
                bind_litellm(gateway(cfg, work, 'implementation'))
        else:
            return original_run(command, **options)
    module.run = dispatch
    bind_litellm(gateway(cfg, work, 'implementation'))
    close = install_sandbox(public, work / 'shell-events.jsonl')
    old = sys.argv
    sys.argv = ['run_pipeline_swe.py', '--model', cfg['model'], '--analysis-model', cfg['model'],
        '--workers', '1', '--max-iterations', '1', '--start-version', str(candidate_version),
        '--train-dir', str(native / 'data/acl_train'),
        '--val-dir', str(native / 'data/acl_val'), '--run-label', 'pilot']
    try:
        sys.path.insert(0, str(native))
        module.main()
    finally:
        sys.argv = old
        close()
    report = read(module.iteration_report_path(candidate_version))
    if not outcomes:
        raise RuntimeError('No candidate was graded; native audit may have rejected it')
    return {'status': 'real_closed_loop_completed', 'candidate_scores': outcomes,
            'promotion': report['promotion'], 'native_report': str(module.iteration_report_path(candidate_version))}


def meta_run(cfg, instances, work):
    public = work / 'optimizer'
    if not (public / 'snapshot.json').exists():
        export_baseline(public, IDS)
    proposer = DeepSeekFileProposer(public, gateway(cfg, work, 'propose'))
    def one_proposal(prompt, iteration):
        existing = sorted(p.name for p in (public / 'candidates').iterdir()) if (public / 'candidates').exists() else []
        meter = gateway(cfg, work, 'propose')
        if existing and meter.ledger.summary()['charged_tokens'] > 850000:
            # Budget finalization, not a new search: the model reviews its own
            # saved candidate and emits the native proposal record in one call.
            from .proposer import TOOLS
            artifacts = {name: {file: (public / 'candidates' / name / 'harness' / file).read_text()
                for file in ('agent.py', 'swebench.yaml')} for name in existing}
            response = meter(model=cfg['model'], messages=[
                {'role': 'system', 'content': 'Finalize your existing candidate at the search budget boundary. '
                 'Review the saved source below and submit exactly one existing candidate with Finish. '
                 'This is completion of an interrupted proposal, not permission to invent a new candidate. '+SCOPE},
                {'role': 'user', 'content': json.dumps(artifacts, ensure_ascii=False)}],
                tools=[t for t in TOOLS if t['function']['name'] == 'Finish'],
                tool_choice={'type': 'function', 'function': {'name': 'Finish'}}, max_tokens=1024)
            calls = response.choices[0].message.tool_calls or []
            if len(calls) != 1 or calls[0].function.name != 'Finish':
                raise ValueError('Missing model proposal finalization')
            rows = json.loads(calls[0].function.arguments)['candidates']
            if len(rows) != 1 or rows[0]['name'] not in existing:
                raise ValueError('Budget finalization must select one existing candidate')
            write_json(work / 'budget-finalization.json', {'request': 'one recorded model Finish',
                'existing_candidate_hashes': {name: {f: sha(public / 'candidates' / name / 'harness' / f)
                    for f in ('agent.py', 'swebench.yaml')} for name in existing}})
            return rows
        checkpoint = (' A prior interrupted proposal already wrote these candidate folders: '+str(existing)+
            '. Resume the existing candidate; inspect its agent.py and swebench.yaml and Finish. '
            'Do not repeat completed history exploration. All original history remains readable.') if existing else ''
        rows = proposer(prompt+' Produce exactly ONE candidate. '+SCOPE+checkpoint, iteration)
        if len(rows) != 1:
            raise ValueError('Pilot budget allows exactly one candidate')
        return rows
    evaluator = Evaluator(cfg, instances, work)
    adapter = MetaHarnessAdapter(work, IDS, one_proposal, evaluator)
    frontier = adapter.run(1)
    jobs = list((work / 'controller/jobs').rglob('outcomes.json'))
    candidates = [p for p in jobs if 'h0' not in p.parent.name]
    if len(candidates) != 1:
        raise RuntimeError('Expected one real candidate evaluation')
    return {'status': 'real_closed_loop_completed', 'frontier': frontier,
            'candidate_scores': read(candidates[0])['scores']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('framework', choices=['harnessfix', 'meta-harness'])
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--candidate-version', type=int, default=1)
    args = parser.parse_args()
    cfg, instances = prepare(args.work)
    if cfg['model'] != 'deepseek-flash' or cfg['api_base'].rstrip('/') != 'https://api.deepseek.com':
        raise ValueError('Provider differs from authorized fixed setup')
    work = Path(cfg['workspace']) / args.framework
    work.mkdir(exist_ok=True)
    if (work / 'result.json').exists():
        print(json.dumps(read(work / 'result.json'), ensure_ascii=False, indent=2))
        return
    started = time.time()
    write_json(work / 'status.json', {'status': 'running', 'started_at': started})
    try:
        result = hf_run(cfg, instances, work, args.candidate_version) if args.framework == 'harnessfix' else meta_run(cfg, instances, work)
        result.update(framework=args.framework, started_at=started, finished_at=time.time(),
            scope='two development tasks; engineering validation, not an efficacy study',
            baseline_scores=Evaluator(cfg, instances, work)('h0', HARNESS, IDS),
            optimizer_usage=UsageLedger(work / 'optimizer-api/usage.json', 80, 1000000).summary())
        result['effective_optimizer_limits'] = gateway(cfg, work, 'summary').cfg['limits']
        result['target_usage'] = {'calls': 0, 'actual_tokens': 0}
        for path in (work / 'evaluations').glob('*/trials/*/usage.json'):
            rows = read(path)['requests']
            result['target_usage']['calls'] += len(rows)
            result['target_usage']['actual_tokens'] += sum(r.get('usage', {}).get('total_tokens', 0) for r in rows)
        adjustment = work / 'optimizer-budget-adjustment.json'
        if adjustment.exists():
            result['engineering_recovery_overhead'] = read(adjustment)['debug_usage']
        write_json(work / 'result.json', result)
        write_json(work / 'status.json', {'status': 'completed', 'finished_at': time.time()})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except BaseException as exc:
        write_json(work / 'status.json', {'status': 'stopped', 'error_type': type(exc).__name__,
                                          'finished_at': time.time(), 'automatic_paid_retry': False})
        raise


if __name__ == '__main__':
    main()
