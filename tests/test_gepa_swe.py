import hashlib
import json

import pytest
import yaml

from acl_gepa_swe.adapter import SWEAdapter
from acl_gepa_swe.common import seed_candidate, validate
from acl_gepa_swe.feedback import EvaluationUnavailable, record
from acl_gepa_swe.run import optimize
from acl_rsi.settings import write_json


def fixture_trial(path, iid, resolved):
    path.mkdir(parents=True, exist_ok=True)
    (path / 'patch.diff').write_text('fixture patch')
    write_json(path / 'worker.json', {'instance_id': iid, 'exit_status': 'Submitted',
                                     'usage': {'calls': 1, 'actual_tokens': 20}})
    write_json(path / 'trajectory.json', {'messages': [{'role': 'assistant', 'content': 'PUBLIC_AGENT_TRACE'}]})
    write_json(path / 'official/report.json', {iid: {'resolved': resolved, 'patch_successfully_applied': True,
               'tests_status': {'PRIVATE_TEST_SENTINEL': 'secret grading details'}}})
    write_json(path / 'grade.json', {'instance_id': iid, 'resolved': resolved, 'completed': True,
        'infrastructure_failure': False, 'patch_sha256': hashlib.sha256(b'fixture patch').hexdigest(),
        'report_path': str(path / 'official/report.json')})


def changed():
    data = yaml.safe_load(seed_candidate()['swebench.yaml'])
    data['agent']['system_template'] += '\nInspect evidence before editing and validate the submitted diff.\n'
    return {'swebench.yaml': yaml.safe_dump(data, sort_keys=False)}


def test_native_one_candidate_full_batch_cache_and_feedback_boundary(tmp_path, monkeypatch):
    import acl_gepa_swe.adapter as module
    ids = ['fixture-a', 'fixture-b']
    cfg = {'evolve_ids': ids, 'gepa': {'seed': 0}}
    instances = {i: {'problem_statement': 'PUBLIC ISSUE'} for i in ids}
    base = tmp_path / 'baseline'
    for i, resolved in zip(ids, (False, True)):
        fixture_trial(base / i, i, resolved)
    monkeypatch.setattr(module, 'baseline_trial', lambda iid: base / iid)
    calls = []
    class Executor:
        def evaluate(self, task_ids, folder):
            fresh = 0
            for iid in task_ids:
                trial = folder / 'trials' / iid
                if not (trial / 'grade.json').exists():
                    calls.append(iid)
                    fixture_trial(trial, iid, True)
                    fresh += 1
            return fresh
    work = tmp_path / 'work'
    work.mkdir()
    adapter = SWEAdapter(cfg, work, instances, Executor())
    reflections = []
    def reflect(prompt):
        reflections.append(prompt)
        assert 'PUBLIC_AGENT_TRACE' in prompt and 'PUBLIC ISSUE' in prompt
        assert 'PRIVATE_TEST_SENTINEL' not in prompt
        return '```yaml\n' + changed()['swebench.yaml'] + '\n```'
    result = optimize(cfg, work, adapter, reflect)
    assert result.best_score == 1 and result.num_candidates == 2
    assert result.total_metric_calls == 4 and sorted(calls) == ids and len(reflections) == 1
    adapter.evaluate([{'task_id': i} for i in ids], result.best_candidate)
    assert len(calls) == 2
    reformatted = {'swebench.yaml': yaml.safe_dump(yaml.safe_load(adapter.seed['swebench.yaml']))}
    assert adapter.evaluate([{'task_id': i} for i in ids], reformatted).scores == [0, 1]
    assert len(calls) == 2


def test_budget_model_loop_frozen_and_missing_report_not_scored(tmp_path):
    data = yaml.safe_load(seed_candidate()['swebench.yaml'])
    data['agent']['step_limit'] = 999
    with pytest.raises(ValueError, match='frozen'):
        validate({'swebench.yaml': yaml.safe_dump(data)}, tmp_path / 'bad', [])
    fixture_trial(tmp_path / 'trial', 'fixture-a', True)
    (tmp_path / 'trial/official/report.json').unlink()
    with pytest.raises(EvaluationUnavailable, match='missing_official_report'):
        record(tmp_path / 'trial', 'fixture-a', {'problem_statement': 'public'})


def test_incomplete_worker_is_not_paid_again(tmp_path):
    from acl_gepa_swe.executor import SWEExecutor
    cfg = {'config_sha256': 'fixture'}
    folder = tmp_path / 'candidate'
    validate(changed(), folder / 'harness', [])
    trial = folder / 'trials/fixture-a'
    write_json(trial / 'worker-attempt.json', {'started': True})
    executor = SWEExecutor(cfg, tmp_path, {'fixture-a': {'base_commit': 'abc', 'instance_id': 'fixture-a',
        'repo': 'fixture', 'problem_statement': 'PUBLIC'}})
    with pytest.raises(EvaluationUnavailable, match='no_automatic_paid_retry'):
        executor.trial('fixture-a', folder)


def test_user_storage_override_retains_mini_images_without_changing_protocol(tmp_path, monkeypatch):
    from acl_gepa_swe.executor import SWEExecutor, StreamingDomain
    cfg = {'target': {'max_calls': 50, 'max_tokens': 1000000}}
    executor = SWEExecutor(cfg, tmp_path, {})
    calls = []
    monkeypatch.setattr(StreamingDomain, 'release', lambda *args: calls.append(args))
    executor.release(None, 'mini-image', {}, set(), tmp_path / 'cache.json')
    assert len(calls) == 1
    write_json(tmp_path / 'storage-policy.json', {'retain_mini_images': True})
    executor.release(None, 'mini-image', {}, set(), tmp_path / 'cache.json')
    assert len(calls) == 1
    assert cfg == {'target': {'max_calls': 50, 'max_tokens': 1000000}}
