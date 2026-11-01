from pathlib import Path
from acl_frameworks.common import read
from acl_gepa_swe.feedback import EvaluationUnavailable
from acl_multiround.runtime import initial_state
from acl_multiround.runtime import bind as original_bind
from acl_unified import common
from acl_rsi.settings import write_json
from .protocol import WORK,OLD,round_dir


def legacy_usage_paths():
    return list(OLD.glob('*/round-*/optimizer-api/usage.json'))+list(OLD.glob('*/round-*/evaluations/*/trials/*/usage.json'))


def legacy_worker_paths():return list(OLD.glob('*/round-*/evaluations/*/trials/*/worker-attempt.json'))


def worker_count():
    return len(legacy_worker_paths())+len(list(WORK.glob('*/round-*/evaluations/*/trials/*/worker-attempt.json')))


def reserve_ten(work):
    path=Path(work)/'evaluation-budget-reservation.json'
    if path.exists():return
    used=worker_count()
    if used+10>100:
        write_json(Path(work)/'global-budget-stop.json',{'used':used,'requested':10,'limit':100})
        raise EvaluationUnavailable('global_100_worker_cap: cannot reserve a complete ten-task evaluation')
    write_json(path,{'prior_executions_including_cancelled_legacy_retests':used,'reserved_candidate_tasks':10,'global_limit':100})


def parent_state(name,index,ids):
    state=initial_state(ids) if index==1 else read(round_dir(name,index-1)/'result.json')['next_parent']
    if state is None:raise ValueError('Previous round did not retain a valid parent')
    if common.fingerprint(Path(state['harness']))!=state['harness_sha256']:raise ValueError('Parent changed')
    assert set(state['scores'])==set(ids) and set(state['trials'])==set(ids)
    return state


def bind(cfg,instances,work,parent):
    b=original_bind(cfg,instances,work,parent)
    base=b['Evaluator']
    class CappedEvaluator(base):
        def __call__(self,name,harness,ids,**kwargs):
            if name not in ('h0','initial'):reserve_ten(self.work)
            return super().__call__(name,harness,ids,**kwargs)
    b['Evaluator']=CappedEvaluator
    common.Evaluator=CappedEvaluator
    return b
