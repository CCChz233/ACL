"""Explicitly audited model repair of a DGM tool protocol defect, then the same ten tasks.

Never change the failed candidate or frozen runtime. Share the original optimizer
ledger; count its failed target attempt toward the whole-experiment budget.
"""
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import time

import yaml

from acl_dgm.adapter import DGMAdapter, FILES, validate
from acl_dgm.experiment import usage, snapshot
from acl_dgm.runtime import NativeMiniModel, SWEEvaluator, SCOPE
from acl_frameworks.common import ROOT, read, sha
from acl_frameworks.provider import RecordedDeepSeek
from acl_rsi.deepseek import BudgetExceeded
from acl_rsi.settings import load_settings, write_json
from acl_rsi.worker import image_name, load_agent

OLD = ROOT / 'experiments/runs/dgm-hard10-v1'
WORK = ROOT / 'experiments/runs/dgm-hard10-v1-recovery'


def contract(harness):
    """Exercise candidate tool results with one and multiple tool calls, without an API."""
    templates = yaml.safe_load((harness / 'swebench.yaml').read_text())
    def no_api(**kw):
        raise AssertionError('Contract gate cannot call the model')
    no_api.ledger = SimpleNamespace(summary=lambda: {})
    model = NativeMiniModel({'model': 'deepseek-flash'}, templates['model'], no_api)
    reports = []
    for commands in (['echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt'],
                     ['echo before', 'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt', 'echo after']):
        executed = []
        def execute(action):
            executed.append(action['command'])
            return {'output': 'fixture diff', 'returncode': 0}
        env = SimpleNamespace(execute=execute, get_template_vars=lambda: {})
        agent = load_agent(harness / 'agent.py')(model, env, **templates['agent'])
        actions = [{'command': command, 'tool_call_id': 'fixture_'+str(n)} for n, command in enumerate(commands)]
        message = {'role': 'assistant', 'content': '', 'extra': {'actions': actions},
            'tool_calls': [{'id': a['tool_call_id'], 'type': 'function', 'function': {
                'name': 'bash', 'arguments': json.dumps({'command': a['command']})}} for a in actions]}
        output = agent.execute_actions(message)
        returned = [r['tool_call_id'] for r in output if r.get('role') == 'tool']
        assert returned == [a['tool_call_id'] for a in actions], ('tool result mismatch', returned)
        assert not any('COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' in c for c in executed), 'First submission was not intercepted'
        agent.execute_actions(message)
        assert any('COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' in c for c in executed), 'Resubmission never executes'
        reports.append({'tool_calls': len(actions), 'paired_results': len(returned), 'resubmission_executed': True})
    return reports


def totals():
    paths = [OLD / 'optimizer-api/usage.json']
    paths += list(OLD.glob('evaluations/*/trials/*/usage.json'))
    paths += list(WORK.glob('evaluations/*/trials/*/usage.json'))
    return {k: sum(usage(p)[k] for p in paths) for k in
        ('calls', 'actual_tokens', 'unknown_usage_requests', 'charged_or_reserved_tokens')}


def main():
    if (WORK / 'status.json').exists():
        raise ValueError('Recovery already started; no automatic paid retry')
    # Ensure that the failed source remains byte-identical.
    for file, digest in read(OLD / 'integration-lock.json')['adapter_sha256'].items():
        assert sha(ROOT / file) == digest
    WORK.mkdir(parents=True, exist_ok=True)
    source = read(OLD / 'config.json')
    source['workspace'] = str(WORK)
    source['purpose'] = 'dgm-hard10-explicit-protocol-recovery'
    write_json(WORK / 'config.json', source)
    cfg = load_settings(WORK / 'config.json')
    before = totals()
    write_json(WORK / 'recovery-audit.json', {'failed_attempt': str(OLD.relative_to(ROOT)),
        'reason': 'generated checkpoint omitted paired tool result; DeepSeek HTTP400 on first task',
        'original_candidate_unchanged': True, 'candidate_repair_by': 'selected parent mini agent with DeepSeek Flash',
        'optimizer_ledger': str((OLD / 'optimizer-api/usage.json').relative_to(ROOT)),
        'before_usage': before, 'shared_optimizer_limits': cfg['search'],
        'whole_experiment_limits': {'calls': 580, 'tokens': 11000000},
        'target_attempts': 'one failed attempt retained plus at most ten repaired-candidate attempts',
        'scope': 'recovered engineering pilot; not an untouched autonomous DGM efficacy experiment',
        'script_sha256': sha(Path(__file__)),
        'original_candidate_sha256': {f: sha(OLD / 'optimizer/candidates/node_0000/harness' / f) for f in FILES}})
    shutil.copy2(__file__, WORK / 'recovery-runtime.py')
    write_json(WORK / 'status.json', {'status': 'running', 'started_at': time.time()})
    def propose(context):
        candidate, parent = context['candidate_harness'], context['parent_harness']
        for f in FILES:
            shutil.copy2(OLD / 'optimizer/candidates/node_0000/harness' / f, candidate / f)
        provider = {k: cfg[k] for k in ('model', 'api_base', 'thinking')}
        provider['limits'] = cfg['search']
        gateway = RecordedDeepSeek(provider, OLD / 'optimizer-api', 'implementation_protocol_recovery', enabled=True)
        templates = yaml.safe_load((parent / 'swebench.yaml').read_text())
        model = NativeMiniModel(cfg, templates['model'], gateway)
        from minisweagent.environments.docker import DockerEnvironment
        env = DockerEnvironment(image=image_name(cfg['evolve_ids'][0]), cwd=str(candidate), timeout=60,
            env={'PAGER': 'cat', 'PYTHONDONTWRITEBYTECODE': '1'}, run_args=['--rm', '--platform', 'linux/amd64',
            '--network', 'none', '--cpus', '2', '--memory', '2g',
            '--volume', f'{context["workspace"]}:{context["workspace"]}:ro', '--volume', f'{candidate}:{candidate}:rw'])
        options = dict(templates['agent'])
        options.update(system_template='You repair your previously generated mini-agent candidate using bash. '+SCOPE,
            instance_template='{{task}}', step_limit=cfg['search']['max_calls'], cost_limit=0,
            wall_time_limit_seconds=600, output_path=WORK / 'repair-trajectory.json')
        agent = load_agent(parent / 'agent.py')(model, env, **options)
        task = f'''Repair the existing candidate at {candidate}. Keep its existing pre-submission review idea.
The candidate's execute_actions intercepts the submit tool call but appends only a user message.
DeepSeek then rejects the conversation (HTTP400) because the assistant tool_call has no matching tool result.
Every incoming tool call must get exactly one role=tool observation with its own tool_call_id,
including the intercepted submission and any actions after it. Preserve order and avoid duplicated results.
The model.format_observation_messages method pairs the full actions list with outputs and pads missing outputs.
Also the review currently suggests only the echo fragment, dropping the original patch-printing command.
Make resubmission guidance preserve the complete original command so a patch is actually returned.
Only repair these protocol defects, no benchmark-specific changes or new improvement search.
Read only relevant portions (around execute_actions and _patch_review_message) to conserve the remaining budget.
Do not install dependencies. Do not attempt import tests: mini-swe-agent is installed on the controller host,
not this tool container. Python syntax checking in the container is sufficient; the host will test the protocol.
Finish by a bash command with echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT on its own first output line.
All previous optimizer calls count toward the SAME 80-call/1M-token cap. Remaining charged tokens at start:
{cfg['search']['max_tokens']-gateway.ledger.summary()['charged_tokens']}.
'''
        try:
            result = agent.run(task)
            write_json(WORK / 'repair-exit.json', result)
        except BudgetExceeded as error:
            write_json(WORK / 'repair-exit.json', {'exit_status': 'BudgetExceeded', 'reason': error.reason})
        finally:
            agent.save(WORK / 'repair-trajectory.json')
            if env.container_id:
                subprocess.run(['docker', 'rm', '-f', env.container_id], capture_output=True, timeout=60)
                env.container_id = None
        validate(candidate, context['workspace'] / 'harness')
        write_json(WORK / 'protocol-contract.json', {'status': 'passed', 'checks': contract(candidate),
            'candidate_sha256': {f: sha(candidate / f) for f in FILES}, 'new_model_calls_in_contract': 0})
    evaluator = SWEEvaluator(cfg, WORK)
    def evaluate(name, harness, ids):
        if name == 'initial':
            return evaluator(name, harness, ids)
        results = {}
        for iid in ids:
            charged = totals()
            if charged['calls']+cfg['target']['max_calls'] > 580 or charged['charged_or_reserved_tokens']+cfg['target']['max_tokens'] > 11000000:
                raise RuntimeError('Whole experiment budget: cannot reserve another complete target trial')
            print('[recovery] evaluate '+iid, flush=True)
            results.update(evaluator(name, harness, [iid]))
            write_json(WORK / 'progress.json', {'graded': len(results), 'scores': {k: v['score'] for k,v in results.items()},
                'whole_experiment_usage': totals()})
        return results
    try:
        adapter = DGMAdapter(WORK, cfg['evolve_ids'], propose, evaluate)
        state = adapter.run(1)
        report = snapshot(WORK)
        report.update(status='completed', native_state=state, optimizer_usage=usage(OLD / 'optimizer-api/usage.json'),
            whole_experiment_usage=totals(), scope='recovered engineering pilot on selected development tasks')
        write_json(WORK / 'result.json', report)
        write_json(WORK / 'status.json', {'status': 'completed', 'finished_at': time.time()})
    except BaseException as error:
        write_json(WORK / 'status.json', {'status': 'stopped', 'error_type': type(error).__name__,
            'finished_at': time.time(), 'whole_experiment_usage': totals(), 'automatic_paid_retry': False})
        raise


if __name__ == '__main__':
    main()
