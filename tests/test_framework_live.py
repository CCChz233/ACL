"""Real-pilot boundaries tested without any network/model/container execution."""
from pathlib import Path

import pytest

from acl_frameworks.common import read
from acl_frameworks.live import IDS, BASE, Evaluator, install_sandbox, prepare, public_run


def test_pilot_budget_and_resumable_source_lock(tmp_path):
    cfg, instances = prepare(tmp_path)
    assert cfg['evolve_ids'] == IDS and not cfg['heldout_ids']
    assert cfg['search']['max_calls'] == 80
    assert cfg['protocol']['candidates_per_framework'] == 1
    assert cfg['target']['max_calls'] == 50
    resumed, _ = prepare(tmp_path)
    assert resumed['config_sha256'] == cfg['config_sha256']
    assert Evaluator(cfg, instances, tmp_path)('h0', None, IDS) == {IDS[0]: 0.0, IDS[1]: 1.0}


def test_native_trace_translation_does_not_export_private_grading(tmp_path):
    public_run(tmp_path, tmp_path / 'traces', tmp_path / 'eval', IDS,
               lambda i: BASE / 'runs/swe/jobs/base' / i / 'trial-0')
    assert read(tmp_path / 'eval/results.json')['resolved_ids'] == [IDS[1]]
    trace = read(tmp_path / 'traces' / IDS[0] / (IDS[0]+'.traj.json'))
    assert trace['messages'] and trace['info']['model_stats']['api_calls'] > 0
    assert not list(tmp_path.rglob('report.json'))
    assert not list(tmp_path.rglob('test_output.txt'))


def test_native_bash_is_confined_and_restored(tmp_path, monkeypatch):
    import minisweagent.environments.local as local
    from minisweagent.environments.docker import DockerEnvironment
    seen = []
    def fake_init(self, **kwargs):
        seen.append(kwargs)
        self.container_id = None
    monkeypatch.setattr(DockerEnvironment, '__init__', fake_init)
    monkeypatch.setattr(DockerEnvironment, 'execute', lambda *a, **kw: {'returncode': 0, 'output': 'ok'})
    original = local.LocalEnvironment
    public = tmp_path / 'public'
    close = install_sandbox(public, tmp_path / 'audit.jsonl')
    try:
        with pytest.raises(ValueError, match='writable target'):
            local.LocalEnvironment(env={'TARGET_DIR': str(tmp_path / 'private')})
        env = local.LocalEnvironment(env={'TARGET_DIR': str(public / 'native/task_agent/candidate')})
        env.execute({'command': 'cat public-file'})
        assert f'{public}:{public}:ro' in seen[0]['run_args']
        assert f'{public}/native/task_agent/candidate:{public}/native/task_agent/candidate:rw' in seen[0]['run_args']
        assert '--network' in seen[0]['run_args'] and 'none' in seen[0]['run_args']
    finally:
        close()
    assert local.LocalEnvironment is original
    assert 'cat public-file' in (tmp_path / 'audit.jsonl').read_text()


def test_rejected_native_version_cannot_silently_become_baseline(tmp_path):
    from acl_frameworks.live import hf_run
    with pytest.raises(ValueError, match='assumes base'):
        hf_run({}, {}, tmp_path, candidate_version=2)


def test_budget_finalization_uses_existing_candidate_and_native_controller(tmp_path, monkeypatch):
    import json
    import shutil
    from types import SimpleNamespace
    from acl_frameworks import live
    from acl_frameworks.context import export_baseline
    from acl_gepa_swe.common import HARNESS
    export_baseline(tmp_path / 'optimizer', IDS)
    shutil.copytree(HARNESS, tmp_path / 'optimizer/candidates/h1/harness')
    seen = []
    class Meter:
        ledger = SimpleNamespace(summary=lambda: {'charged_tokens': 903147})
        def __call__(self, **payload):
            seen.append(payload)
            args = json.dumps({'candidates': [{'name': 'h1', 'hypothesis': 'offline', 'changes': 'fixture'}]})
            call = SimpleNamespace(function=SimpleNamespace(name='Finish', arguments=args))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])
    monkeypatch.setattr(live, 'gateway', lambda *a: Meter())
    monkeypatch.setattr(live, 'Evaluator', lambda *a: lambda name, harness, ids: {i: float(name != 'h0') for i in ids})
    result = live.meta_run({'model': 'deepseek-flash'}, {}, tmp_path)
    assert result['candidate_scores'] == {i: 1.0 for i in IDS}
    assert len(seen) == 1 and seen[0]['tool_choice']['function']['name'] == 'Finish'
    assert (tmp_path / 'budget-finalization.json').exists()
