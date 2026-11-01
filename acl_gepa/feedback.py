"""A whitelist between private scoring evidence and the improver."""
from collections import Counter
import json
from pathlib import Path

from .common import read


class EvaluationUnavailable(RuntimeError):
    pass


def grade(trial: Path, baseline: Path):
    result_path = trial / 'result.json'
    if not result_path.exists():
        raise EvaluationUnavailable('missing_result')
    result = read(result_path)
    if result.get('exception_info'):
        raise EvaluationUnavailable('trial_exception')
    reward = ((result.get('verifier_result') or {}).get('rewards') or {}).get('reward')
    if reward not in (0, 1):
        raise EvaluationUnavailable('missing_binary_reward')
    path, reference = trial / 'verifier/ctrf.json', baseline / 'verifier/ctrf.json'
    if not path.exists() or not reference.exists():
        raise EvaluationUnavailable('missing_official_test_record')
    report, old = read(path)['results'], read(reference)['results']
    tests = report.get('tests', [])
    if (not tests or report.get('summary', {}).get('tests') != len(tests)
            or Counter(t.get('name') for t in tests) != Counter(t.get('name') for t in old['tests'])
            or any(t.get('status') not in ('passed', 'failed') for t in tests)):
        raise EvaluationUnavailable('incomplete_official_test_record')
    if reward != int(all(t['status'] == 'passed' for t in tests)):
        raise EvaluationUnavailable('reward_test_record_disagreement')
    return float(reward)


def public_record(trial, baseline, task_id):
    score = grade(trial, baseline)
    worker = read(trial / 'agent/worker.json')
    if worker.get('exit_status') in ('ProviderError', 'RuntimeError'):
        raise EvaluationUnavailable('worker_infrastructure_error')
    messages = read(trial / 'agent/trajectory.json').get('messages', [])
    rows = []
    if len(messages) > 1:
        rows.append('PUBLIC TASK: ' + str(messages[1].get('content', ''))[:3200])
    indexes = sorted(set(range(min(8, len(messages)))) | set(range(max(0, len(messages) - 54), len(messages))))
    for index in indexes:
        msg = messages[index]
        role = msg.get('role')
        if role == 'system' or (index == 1 and role == 'user'):
            continue
        content = str(msg.get('content') or '')
        if role == 'assistant':
            commands = [a.get('command', '') for a in msg.get('extra', {}).get('actions', [])]
            if not commands:
                commands = [t.get('function', {}).get('arguments', '') for t in msg.get('tool_calls', [])]
            rows.append(f'[{index}] assistant: ' + content[:120] + ' COMMANDS: ' + json.dumps(commands)[:260])
        else:
            rows.append(f'[{index}] {role}: ' + content[:180])
    return {'task_id': task_id, 'score': score, 'stop': worker.get('exit_status'),
            'usage': {key: worker.get('usage', {}).get(key, 0) for key in ('calls', 'actual_tokens')},
            'public_agent_trace': '\n'.join(rows)[:22000],
            'trace_scope': 'Bounded excerpts of public task and agent interactions; no verifier text or test contents.'}
