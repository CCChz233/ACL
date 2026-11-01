"""Audit the locked candidate without API calls; --write saves corrected summaries.

Require complete official pytest/CTRF records in addition to numeric rewards.
Grader setup failures must not be reported as harness regressions. Raw trials,
the frozen adapter, and search inputs are never modified by this audit.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/terminal-round1'


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grade(trial, baseline_trial):
    result = read(trial / 'result.json')
    if result is None:
        return {'state': 'pending', 'raw_reward': None, 'candidate': None}
    reward = ((result.get('verifier_result') or {}).get('rewards') or {}).get('reward')
    exception = (result.get('exception_info') or {}).get('exception_type')
    ctrf = read(trial / 'verifier/ctrf.json')
    base_ctrf = read(baseline_trial / 'verifier/ctrf.json')
    reason = None
    if exception:
        reason = 'trial_exception:' + exception
    elif reward not in (0, 1):
        reason = 'missing_binary_reward'
    elif not ctrf or not base_ctrf:
        reason = 'missing_official_test_record'
    else:
        tests = ctrf.get('results', {}).get('tests', [])
        baseline_tests = base_ctrf.get('results', {}).get('tests', [])
        summary = ctrf.get('results', {}).get('summary', {})
        if (not tests or summary.get('tests') != len(tests)
                or Counter(t.get('name') for t in tests) != Counter(t.get('name') for t in baseline_tests)
                or any(t.get('status') not in ('passed', 'failed') for t in tests)):
            reason = 'incomplete_official_test_record'
        elif reward != int(all(t.get('status') == 'passed' for t in tests)):
            reason = 'reward_test_record_disagreement'
    return {'state': 'invalid_grading' if reason else 'valid',
            'raw_reward': reward, 'candidate': None if reason else reward,
            'invalid_reason': reason, 'exception': exception,
            'test_count': len(ctrf['results']['tests']) if ctrf else 0}


def requests(path):
    if not path.exists():
        return []
    with path.open() as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        return json.load(handle)['requests']


def usage(rows):
    keys = ('prompt_tokens', 'completion_tokens', 'total_tokens',
            'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')
    return {'calls': len(rows), 'completed': sum(r['status'] == 'completed' for r in rows),
            **{key: sum(r.get('usage', {}).get(key, 0) or 0 for r in rows) for key in keys},
            'api_seconds': sum(r.get('api_seconds', 0) or 0 for r in rows)}


def audit():
    cfg = read(ROOT / 'configs/terminal-round1.json')
    base = ROOT / cfg['baseline_workspace']
    rows, all_target = [], []
    for task in cfg['tasks']:
        trial = WORK / 'candidate-eval/trials' / task['id']
        baseline_trial = base / 'trials' / task['id']
        calls = requests(trial / 'agent/usage.json')
        all_target.extend(calls)
        worker = read(trial / 'agent/worker.json')
        state = grade(trial, baseline_trial)
        if state['state'] == 'pending' and calls:
            state['state'] = 'grading' if worker else 'running'
        baseline_result = read(baseline_trial / 'result.json')
        rows.append({'task_id': task['id'], 'category': task['category'],
                     'baseline': baseline_result['verifier_result']['rewards']['reward'],
                     **state, 'stop': worker.get('exit_status') if worker else None,
                     'usage': usage(calls)})
    search = requests(WORK / 'search_usage.json')
    completed = sum(r['state'] == 'valid' for r in rows)
    invalid = sum(r['state'] == 'invalid_grading' for r in rows)
    passed = sum(r['candidate'] == 1 for r in rows)
    return {'status': 'completed' if completed == len(rows) else 'network_blocked_incomplete',
            'audit_policy': 'Require binary reward plus complete official pytest/CTRF tests matching baseline; raw evidence unchanged.',
            'candidate_commit': '94ba950', 'baseline_passed': 7, 'total': len(rows),
            'baseline_score': 7 / 12, 'valid_evaluations': completed,
            'invalid_grading': invalid, 'pending': sum(r['state'] == 'pending' for r in rows),
            'valid_subset_passed': passed, 'candidate_passed': passed if completed == len(rows) else None,
            'candidate_score': passed / len(rows) if completed == len(rows) else None,
            'delta_percentage_points': (passed - 7) / len(rows) * 100 if completed == len(rows) else None,
            'new_passes': [r['task_id'] for r in rows if r['baseline'] == 0 and r['candidate'] == 1],
            'regressions': [r['task_id'] for r in rows if r['baseline'] == 1 and r['candidate'] == 0],
            'search_usage': usage(search), 'candidate_usage': usage(all_target),
            'combined_usage': usage(search + all_target),
            'search_calls_by_role': dict(Counter(r['role'] for r in search)),
            'paired_tasks': rows, 'selection': 'eval_invalid; retain original harness; no measured candidate rejection',
            'scope': 'Same 12 development tasks, one semantic candidate; no heldout or full accuracy claim.',
            'resume_constraints': 'No automatic paid retry. Third task lost container state; its saved trajectory cannot replace a valid original grade.',
            'audit_script_sha256': sha(Path(__file__))}


def save(report):
    def write(path, data):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    old = WORK / 'summary.json'
    archived = WORK / 'summary-before-grading-audit.json'
    if old.exists() and not archived.exists():
        archived.write_bytes(old.read_bytes())
    write(old, report)
    write(WORK / 'evaluation-status.json', report)
    write(ROOT / 'docs/terminal_round1_results.json', report)
    write(WORK / 'controller.json', {'status': report['status'],
                                   'reason': 'Image/CDN and grader dependency downloads failed; no proxy available.',
                                   'paid_work_running': False,
                                   'report': 'evaluation-status.json'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    report = audit()
    if args.write:
        save(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
