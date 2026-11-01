"""Offline historical checkpoint audit; never calls an API or starts Docker.

Reconstructs Meta-Harness edits from recorded calls, only applying operations
whose recorded tool result confirms success. Executes only validated harness
Python with a deterministic in-memory model/environment; no generated shell
commands or model-authored self-tests are executed.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "reports/exports/within-round-audit-2026-10-20"
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['MSWEA_GLOBAL_CONFIG_DIR'] = str(OUT / 'empty-global-config')
os.environ['MSWEA_SILENT_STARTUP'] = '1'
OLD = ROOT / "experiments/runs/full10-highbudget-two-rounds-v1"
NEW = ROOT / "experiments/runs/full10-highbudget-completion-v1"
FILES = ("agent.py", "swebench.yaml", "LICENSE.md")


def read(path):
    return json.loads(path.read_text())


def hashes(folder):
    return {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in FILES}


def probe(folder):
    from acl_rsi.model import DeepSeekMiniModel, ModelConfig
    from minisweagent.environments.docker import DockerEnvironment

    templates = yaml.safe_load((folder / "swebench.yaml").read_text())
    ast.parse((folder / "agent.py").read_text())
    spec = importlib.util.spec_from_file_location("audit_candidate_agent", folder / "agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patch = "diff --git a/probe.py b/probe.py\n--- a/probe.py\n+++ b/probe.py\n@@ -1 +1 @@\n-old\n+new\n"
    rows = []
    for scenario in ("submit", "normal_then_submit", "batch_then_submit"):
        commands = ([['echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt']]
                    if scenario == "submit" else
                    [['echo probe'], ['echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt']]
                    if scenario == "normal_then_submit" else
                    [['echo one', 'echo two'], ['echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt']])

        class Model(DeepSeekMiniModel):
            def __init__(self):
                self.config = ModelConfig(**{**templates['model'], 'model_name': 'offline-replay-no-api'})
                self.calls = 0

            def query(self, messages, **kwargs):
                if self.calls >= len(commands):
                    raise RuntimeError("Offline fixture exhausted: submission was not propagated")
                actions = [{'command': c, 'tool_call_id': f'probe_{self.calls}_{i}'}
                           for i, c in enumerate(commands[self.calls])]
                self.calls += 1
                return {'role': 'assistant', 'content': '', 'extra': {'actions': actions, 'cost': 0.0},
                        'tool_calls': [{'id': a['tool_call_id'], 'type': 'function', 'function':
                                       {'name': 'bash', 'arguments': json.dumps({'command': a['command']})}}
                                       for a in actions]}

            def serialize(self):
                return {'info': {'config': {'model': self.config.model_dump()}, 'offline': True}}

        class Env:
            def execute(self, action):
                output = {'output': 'fixture output', 'returncode': 0, 'exception_info': ''}
                if 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' in action['command']:
                    output['output'] = 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n' + patch
                # Use the genuine submission parser, without constructing Docker.
                DockerEnvironment._check_finished(self, output)
                return output

            def get_template_vars(self):
                return {}

            def serialize(self):
                return {'info': {'offline': True}}

        try:
            kwargs = dict(templates['agent'])
            kwargs.update(step_limit=8, cost_limit=0, wall_time_limit_seconds=30, output_path=None)
            agent = module.DefaultAgent(Model(), Env(), **kwargs)
            result = agent.run('Offline submission protocol fixture')
            rows.append({'scenario': scenario, 'ok': result.get('exit_status') == 'Submitted'
                         and result.get('submission') == patch, 'exit_status': result.get('exit_status'),
                         'submission_matches': result.get('submission') == patch})
        except Exception as error:
            rows.append({'scenario': scenario, 'ok': False, 'exit_status': type(error).__name__,
                         'error': str(error)[:300]})
    return rows


def recover_patch(messages):
    """Only exact cat patch.txt stdout; reject intervening non-read commands."""
    actions = {a['tool_call_id']: a['command'] for m in messages
               for a in m.get('extra', {}).get('actions', [])}
    candidates = []
    for i, m in enumerate(messages):
        if m.get('role') != 'tool':
            continue
        command = actions.get(m.get('tool_call_id'), '')
        raw = m.get('extra', {}).get('raw_output', '')
        if 'cat patch.txt' in command and raw.startswith('diff --git ') and raw.endswith('\n'):
            candidates.append((i, raw, command, m['tool_call_id']))
    if not candidates:
        return None
    i, patch, command, cid = candidates[-1]
    later = [a['command'] for m in messages[i+1:] for a in m.get('extra', {}).get('actions', [])]
    # In the two header-only final observations, only grep is allowed after cat.
    if not all(('COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' in c or
                ('grep ' in c and 'patch.txt' in c and '>' not in c)) for c in later):
        return None
    return {'patch': patch, 'source_message_index': i, 'tool_call_id': cid,
            'source_command': command, 'subsequent_commands': later,
            'sha256': hashlib.sha256(patch.encode()).hexdigest()}


def replay_recorded_episode(folder, messages, patch):
    """Conditional controller replay. Model decisions and shell observations are fixed."""
    from acl_rsi.model import DeepSeekMiniModel, ModelConfig
    from minisweagent.environments.docker import DockerEnvironment
    templates = yaml.safe_load((folder / 'swebench.yaml').read_text())
    spec = importlib.util.spec_from_file_location('audit_episode_agent', folder / 'agent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assistant = [copy.deepcopy(m) for m in messages if m.get('role') == 'assistant']
    tool_results = {m['tool_call_id']: m for m in messages if m.get('role') == 'tool'}
    initial_user = next(m['content'] for m in messages if m.get('role') == 'user')

    class Model(DeepSeekMiniModel):
        def __init__(self):
            self.config = ModelConfig(**templates['model'])
            self.calls = 0
        def query(self, history, **kwargs):
            if self.calls >= len(assistant):
                raise RuntimeError('Recorded actions exhausted')
            value = copy.deepcopy(assistant[self.calls])
            self.calls += 1
            return value
        def serialize(self):
            return {'info': {'offline_replay': True}}

    class Env:
        def execute(self, action):
            if action['tool_call_id'] in tool_results:
                extra = tool_results[action['tool_call_id']]['extra']
                return {'output': extra['raw_output'], 'returncode': extra['returncode'],
                        'exception_info': extra.get('exception_info', '')}
            assert 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' in action['command']
            output = {'output': 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n'+patch,
                      'returncode': 0, 'exception_info': ''}
            DockerEnvironment._check_finished(self, output)
            return output
        def get_template_vars(self):
            return {}
        def serialize(self):
            return {'info': {'offline_replay': True}}

    model = Model()
    kwargs = dict(templates['agent'])
    kwargs.update(step_limit=50, cost_limit=0, wall_time_limit_seconds=1200, output_path=None,
                  system_template='Offline conditional replay', instance_template='{{ task }}')
    agent = module.DefaultAgent(model, Env(), **kwargs)
    try:
        result = agent.run(initial_user)
        return {'exit_status': result.get('exit_status'), 'submission_matches': result.get('submission') == patch,
                'recorded_model_turns_used': model.calls}
    except Exception as e:
        return {'exit_status': type(e).__name__, 'error': str(e), 'recorded_model_turns_used': model.calls}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Per-round inventory, not a count of repeated copies of one artifact.
    inventory = []
    for framework in ('harnessfix', 'meta-harness', 'gepa', 'rrsi', 'dgm'):
        for index in (1, 2):
            base = NEW if framework in ('harnessfix', 'dgm') else OLD
            work = base / framework / f'round-{index}'
            result = read(work / 'result.json')
            scored = []
            for folder in sorted((work / 'evaluations').glob('*/harness')):
                grades = list((folder.parent / 'trials').glob('*/grade.json'))
                scored.append({'path': str(folder.relative_to(ROOT)), 'sha256': hashes(folder),
                               'task_grades': len(grades)})
            inventory.append({'framework': framework, 'round': index, 'work': str(work.relative_to(ROOT)),
                              'candidate_resolved': result.get('round_resolved'),
                              'scored_candidate_artifacts': scored})
    (OUT / 'inventory.json').write_text(json.dumps(inventory, indent=2))

    work = OLD / 'meta-harness/round-1'
    parent = read(work / 'input-parent.json')
    assert hashes(Path(parent['harness'])) == parent['harness_sha256']
    ledger = sorted(read(work / 'optimizer-api/usage.json')['requests'], key=lambda r: r['time'])
    results = {}
    for row in ledger:
        p = work / 'optimizer-api/requests' / f"{row['id']}.json"
        if p.exists():
            for message in read(p).get('messages', []):
                if message.get('role') == 'tool':
                    key = message['tool_call_id']
                    if key in results:
                        assert results[key] == message['content'], f'Conflicting tool result {key}'
                    results[key] = message['content']

    state = {f: (Path(parent['harness']) / f).read_text() for f in FILES}
    events, checkpoints = [], []
    edit_count = 0

    def save_checkpoint(event=None):
        folder = OUT / 'meta-round1-checkpoints' / f'edit-{edit_count:03d}'
        folder.mkdir(parents=True, exist_ok=True)
        for f, text in state.items():
            (folder / f).write_text(text)
        try:
            checks = probe(folder)
            error = None
        except Exception as e:
            checks, error = [], f'{type(e).__name__}: {e}'
        cp = {'edit': edit_count, 'path': str(folder.relative_to(ROOT)), 'sha256': hashes(folder),
              'origin': event, 'offline_submission_checks': checks, 'load_error': error,
              'benchmark_resolved': None, 'benchmark_evaluation': 'not_run'}
        checkpoints.append(cp)

    save_checkpoint()
    seen = set()
    for row in ledger:
        response_path = work / 'optimizer-api/usage-responses' / f"{row['id']}.json"
        if not response_path.exists():
            continue
        response = read(response_path)
        for choice in response.get('choices', []):
            for call in choice['message'].get('tool_calls') or []:
                if call['id'] in seen:
                    continue
                seen.add(call['id'])
                function = call['function']
                try:
                    args = json.loads(function['arguments'])
                except Exception:
                    continue
                if function['name'] not in ('Edit', 'Write'):
                    continue
                path = args.get('path', '')
                if not path.startswith('candidates/h1/harness/'):
                    continue
                name = path.rsplit('/', 1)[-1]
                event = {'request_id': row['id'], 'tool_call_id': call['id'],
                         'time': row['time'], 'operation': function['name'], 'path': path,
                         'recorded_result': results.get(call['id'])}
                if event['recorded_result'] not in ('edited', 'written'):
                    event['applied'] = False
                    events.append(event)
                    continue
                assert name in FILES
                if function['name'] == 'Edit':
                    assert state[name].count(args['old']) == 1, f'Replay mismatch {call["id"]}'
                    state[name] = state[name].replace(args['old'], args['new'], 1)
                    event['old'] = args['old']
                    event['new'] = args['new']
                else:
                    state[name] = args['content']
                edit_count += 1
                event.update(applied=True, edit=edit_count)
                events.append(event)
                save_checkpoint({k: event[k] for k in ('request_id', 'tool_call_id', 'operation', 'path')})

    final = work / 'evaluations/candidate/harness'
    assert checkpoints[-1]['sha256'] == hashes(final), 'Reconstructed final artifact differs from measured final'
    final_grades, episode_replays = [], []
    for trial in sorted((final.parent / 'trials').iterdir()):
        if not (trial / 'worker.json').exists():
            continue
        worker = read(trial / 'worker.json')
        trajectory = read(trial / 'trajectory.json')
        exits = [m for m in trajectory.get('messages', []) if m.get('role') == 'exit']
        final_grades.append({'task': trial.name, 'exit_status': worker.get('exit_status'),
                             'error': exits[-1].get('content') if exits else None,
                             'traceback': exits[-1].get('extra', {}).get('traceback') if exits else None})
        recovered = recover_patch(trajectory['messages'])
        row = {'task': trial.name, 'complete_patch_recovered': recovered is not None}
        if recovered:
            patch_folder = OUT / 'recovered-patches' / trial.name
            patch_folder.mkdir(parents=True, exist_ok=True)
            (patch_folder/'patch.diff').write_text(recovered['patch'])
            row['patch_provenance'] = {k:v for k,v in recovered.items() if k != 'patch'}
            row['replays'] = {f'edit-{n:03d}': replay_recorded_episode(
                OUT/'meta-round1-checkpoints'/f'edit-{n:03d}', trajectory['messages'], recovered['patch'])
                for n in (26, 27, 28)}
        episode_replays.append(row)
    result = {'scope': 'ten final high-budget framework-rounds; full edit reconstruction for Meta round1',
              'api_calls': 0, 'docker_runs': 0, 'benchmark_runs': 0,
              'reconstruction': 'Only recorded successful edits; exact final three-file hashes verified',
              'successful_harness_edits': edit_count, 'checkpoints': checkpoints,
              'events': events, 'measured_final_failures': final_grades,
              'conditional_episode_replays': episode_replays,
              'limitations': ['Offline checks measure submission protocol, not SWE-bench solve rate.',
                              'An earlier changed candidate passing these checks does not prove it improved benchmark quality.',
                              'Intermediate benchmark scores were not measured in the historical run.']}
    (OUT / 'meta-round1-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    for cp in checkpoints:
        print(cp['edit'], 'load_error='+str(cp['load_error']),
              [(r['scenario'],r['exit_status'],r['ok']) for r in cp['offline_submission_checks']])
    print('REPLAY_FINAL_HASH_MATCH', True)
    print('CONDITIONAL_EPISODE_REPLAYS',[(r['task'],r.get('replays')) for r in episode_replays])
    print('SCORED_ARTIFACTS_PER_ROUND', [(r['framework'],r['round'],len(r['scored_candidate_artifacts'])) for r in inventory])


if __name__ == '__main__':
    main()
