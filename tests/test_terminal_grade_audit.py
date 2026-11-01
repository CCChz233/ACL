import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('terminal_round_status', Path(__file__).resolve().parents[1] / 'scripts/terminal_round_status.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_grader_setup_failure_is_not_regression_and_real_test_failure_is_valid(tmp_path):
    baseline, candidate = tmp_path / 'baseline', tmp_path / 'candidate'
    for path in (baseline, candidate):
        (path / 'verifier').mkdir(parents=True)
    record = {'results': {'summary': {'tests': 1}, 'tests': [{'name': 'test_example', 'status': 'passed'}]}}
    (baseline / 'verifier/ctrf.json').write_text(json.dumps(record))
    (candidate / 'result.json').write_text(json.dumps({'verifier_result': {'rewards': {'reward': 0}}, 'exception_info': None}))
    (candidate / 'verifier/test-stdout.txt').write_text('curl: (18) Transferred a partial file\nuvx: command not found')
    result = audit.grade(candidate, baseline)
    assert result['state'] == 'invalid_grading'
    assert result['raw_reward'] == 0 and result['candidate'] is None
    record['results']['tests'][0]['status'] = 'failed'
    (candidate / 'verifier/ctrf.json').write_text(json.dumps(record))
    result = audit.grade(candidate, baseline)
    assert result['state'] == 'valid' and result['candidate'] == 0
    record['results']['tests'][0]['status'] = 'passed'
    (candidate / 'verifier/ctrf.json').write_text(json.dumps(record))
    assert audit.grade(candidate, baseline)['state'] == 'invalid_grading'
