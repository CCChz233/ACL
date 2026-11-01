from pathlib import Path
from types import SimpleNamespace
import pytest
from acl_unified import common
from acl_unified.protocol import H0
from acl_multiround_recovery.runtime import stable_validate
from acl_multiround_recovery.adapters import public_run_with_canonical_trials


def test_dgm_gate_does_not_reenter_dynamically_bound_structure(monkeypatch):
    import acl_dgm.adapter as native
    check = stable_validate()
    def recursive(*args):
        raise AssertionError('Structural validation recursed through delivery')
    monkeypatch.setattr(native, 'validate', recursive)
    check(H0, require_change=False)


def test_saved_first_dgm_artifact_passes_nonrecursive_gate():
    from acl_multiround_recovery.protocol import OLD
    check = stable_validate()
    check(OLD / 'dgm/round-1/optimizer/candidates/node_0000/harness')


def test_hf_canonical_mapping_and_unknown_path_rejection(tmp_path):
    canonical = tmp_path / 'evaluations/candidate/trials/task'
    canonical.mkdir(parents=True)
    (canonical / 'grade.json').write_text('{}')
    observed = []
    def original(public, traces, evaluation, ids, resolve):
        observed.extend(resolve(i) for i in ids)
    run = public_run_with_canonical_trials(original, tmp_path)
    run(None, None, None, ['task'], lambda i: tmp_path / 'evaluations/v1/trials' / i)
    assert observed == [canonical]
    with pytest.raises(ValueError, match='Unexpected missing'):
        run(None, None, None, ['task'], lambda i: tmp_path / 'evaluations/unrelated/trials' / i)


def test_reused_trials_cannot_trigger_paid_worker(tmp_path):
    from acl_multiround_recovery.runtime import CachedExecutor
    from acl_rsi.settings import write_json
    from acl_unified import common
    h = common.copy_harness(H0, tmp_path / 'eval/harness')
    write_json(tmp_path / 'reused-evaluation.json', {'harness_sha256': common.fingerprint(h)})
    ex = CachedExecutor({}, tmp_path, {'task': {}})
    with pytest.raises(Exception, match='missing_worker_or_grade'):
        ex.trial('task', tmp_path / 'eval')
    assert not (tmp_path / 'eval/trials/task/worker-attempt.json').exists()
