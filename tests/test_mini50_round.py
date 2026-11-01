import json
from pathlib import Path

import pytest

from acl_rsi.cli import make_run
from acl_rsi.mini50_round import CandidateDomain, import_baseline, job_progress
from acl_rsi.settings import ROOT, load_settings


def test_candidate_progress_never_counts_reused_baseline_as_new_spend(tmp_path):
    cfg = {'workspace': str(tmp_path), 'evolve_ids': ['a', 'b']}
    for job, calls, tokens in [('base', 40, 800000), ('r0A', 3, 20000)]:
        trial = tmp_path / 'jobs' / job / 'a/trial-0'
        trial.mkdir(parents=True)
        (trial / 'worker.json').write_text(json.dumps({'usage': {'calls': calls, 'actual_tokens': tokens}}))
        (trial / 'grade.json').write_text(json.dumps({'completed': True, 'resolved': True}))
    data = job_progress(cfg, tmp_path, 'r0A', 'running')
    assert (data['api_calls'], data['actual_tokens'], data['n_completed'], data['n_total']) == (3, 20000, 1, 2)


def test_baseline_import_checks_evidence_and_never_runs_worker(tmp_path, monkeypatch):
    cfg = load_settings(ROOT / 'configs/mini50-round1.json')
    cfg['workspace'] = str(tmp_path / 'experiment')
    run = make_run(cfg)
    domain = CandidateDomain(cfg); domain.root = run.domain.root; run.domain = domain
    import_baseline(cfg, run)
    monkeypatch.setattr('acl_rsi.domain.MiniSWEDomain.run', lambda *a, **kw: pytest.fail('must not rerun baseline'))
    run.baseline()
    assert run.frontier()['incumbent']['S'] == .62
    assert not (Path(cfg['workspace']) / 'search_usage.json').exists()
    grade = run.jobs / 'base' / cfg['evolve_ids'][0] / 'trial-0/grade.json'
    grade.write_text('{}')
    with pytest.raises(ValueError, match='imported baseline evidence changed'):
        import_baseline(cfg, run)


def test_round_runner_rejects_extra_candidates_without_docker():
    domain = object.__new__(CandidateDomain)
    with pytest.raises(ValueError, match='one round and one candidate'):
        domain.run(None, None, 'r0B', [], 1)


def test_recovery_aggregates_saved_evidence_without_dispatching_more_digesters(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from acl_rsi.resume_mini50_round import aggregate_saved_digests
    folder = tmp_path / 'analysis/digests'; folder.mkdir(parents=True)
    (folder / 'good.json').write_text(json.dumps({'task_id': 'a', 'lens': 'failure', 'blocker': 'no submission'}))
    (folder / 'failed.json').write_text(json.dumps({'task_id': 'b', 'error': 'max turns'}))
    seen = {}
    class FakeClient:
        def __init__(self, *args): pass
        def complete(self, messages, **kwargs):
            seen.update(messages=messages, **kwargs)
            act = {'action': 'report', 'failure_modes': [{'mode': 'non_submission', 'n_tasks': 1}],
                   'capability_gaps': [], 'success_habits': []}
            call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(act)))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])
    monkeypatch.setattr('acl_rsi.resume_mini50_round.DeepSeekClient', FakeClient)
    domain = SimpleNamespace(cfg={'workspace': str(tmp_path), 'search': {'max_calls': 240, 'max_tokens': 2000000}},
                             briefs={'analyst': 'generic harness analysis'}, render_trace=lambda rec, detail: 'public success trace')
    report = aggregate_saved_digests(domain, {'a': {}, 'c': {}},
                                    {'a': SimpleNamespace(mean=0), 'c': SimpleNamespace(mean=1)}, tmp_path)
    assert seen['tools'][0]['function']['parameters']['properties']['action']['enum'] == ['report']
    inputs = json.loads(seen['messages'][1]['content'])
    assert len(inputs['saved_digests']) == len(inputs['unsuccessful_digest_records']) == 1
    assert report['recovery']['successful_raw_traces'] == 1
    assert report['n_digests'] == 1
