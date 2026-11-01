"""Stable structural gate and read-only reuse of previously completed trials."""
import inspect
from pathlib import Path
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from acl_gepa_swe.feedback import record, EvaluationUnavailable
from acl_gepa_swe.executor import SWEExecutor
from acl_unified import common
from acl_dgm.adapter import validate as STRUCTURE
from acl_multiround.runtime import initial_state
from acl_multiround_v3 import runtime as previous
from .protocol import WORK, OLD, round_dir


def stable_validate():
    # The legacy common gate imports adapter.validate at call time. DGM later
    # binds that name to Delivery.ensure, causing gate -> delivery -> gate recursion.
    source = inspect.getsource(common.validate)
    anchor = 'from acl_dgm.adapter import validate as structure'
    assert source.count(anchor) == 1
    namespace = dict(common.__dict__, _STRUCTURE=STRUCTURE)
    exec(compile(source.replace(anchor, 'structure = _STRUCTURE'), '<recovery-stable-gate>', 'exec'), namespace)
    return namespace['validate']


def worker_count():
    old = len(list(OLD.glob('*/round-*/evaluations/*/trials/*/worker-attempt.json')))
    new = sum(1 for p in WORK.glob('*/round-*/evaluations/*/trials/*/worker-attempt.json')
              if not (p.parents[4] / 'reused-evaluation.json').exists())
    return old + new


def parent_state(name, index, ids):
    state = initial_state(ids) if index == 1 else read(round_dir(name, index-1) / 'result.json')['next_parent']
    if state is None:
        raise ValueError('Previous round has no retained parent')
    assert common.fingerprint(Path(state['harness'])) == state['harness_sha256']
    assert set(state['scores']) == set(state['trials']) == set(ids)
    return state


class CachedExecutor(SWEExecutor):
    def trial(self, iid, folder):
        if (self.work / 'reused-evaluation.json').exists():
            receipt = read(self.work / 'reused-evaluation.json')
            if common.fingerprint(folder / 'harness') != receipt['harness_sha256']:
                raise EvaluationUnavailable('Recovered scored candidate changed')
            record(folder / 'trials' / iid, iid, self.instances[iid], trace=False)
            return 0  # No manifest rewrite, worker rerun or grader rerun.
        return super().trial(iid, folder)


def bind(cfg, instances, work, parent):
    common.validate = stable_validate()
    previous.WORK = WORK
    previous.worker_count = worker_count
    import acl_multiround.runtime as base
    base.SWEExecutor = CachedExecutor
    b = previous.bind(cfg, instances, work, parent)
    return b
