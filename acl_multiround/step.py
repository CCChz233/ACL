"""A single durable, metered longitudinal step followed by all-ten evaluation."""
import argparse
import json
from pathlib import Path
import time
import traceback
from acl_frameworks.common import read
from acl_rsi.settings import load_instances,write_json
from acl_rsi.deepseek import BudgetExceeded,ProviderError
from acl_gepa_swe.feedback import record,EvaluationUnavailable
from acl_unified import common
from .protocol import WORK,FRAMEWORKS,round_dir,settings,verify
from .runtime import bind,parent_state,retest_parent


def exception_kind(error):
    if isinstance(error,BudgetExceeded):return 'search_budget_exhausted'
    if isinstance(error,common.InvalidCandidate):return 'invalid_candidate'
    if isinstance(error,(ProviderError,EvaluationUnavailable)):return 'infrastructure_stopped'
    return 'native_step_failed'


def execute(name,index):
    from . import adapters
    verify();common.preflight();cfg=settings(name,index);instances=load_instances(cfg)
    work=round_dir(name,index);ids=cfg['protocol']['all_task_ids']
    if (work/'started.json').exists():raise ValueError('Already started; explicit recovery required, no paid retry')
    parent=parent_state(name,index,ids)
    write_json(work/'input-parent.json',parent)
    write_json(work/'started.json',{'started_at':time.time(),'framework':name,'round':index,'no_automatic_paid_retry':True})
    write_json(work/'status.json',{'status':'running','phase':'optimization','started_at':time.time()})
    bindings=bind(cfg,instances,work,parent)
    native={};error_info=None;proposal_status='native_finished'
    try:
        native=adapters.run(name,cfg,instances,work,bindings)
    except BaseException as error:
        if isinstance(error,KeyboardInterrupt):raise
        proposal_status=exception_kind(error)
        error_info={'type':type(error).__name__,'classification':proposal_status}
        (work/'native-exception.txt').write_text(traceback.format_exc())
    try:
        # A partly evaluated version cannot be replaced by a parent retest: that
        # would hide infrastructure failure and exceed ten task executions.
        workers=[read(p) for p in work.glob('evaluations/candidate/trials/*/worker.json')]
        if proposal_status=='infrastructure_stopped' or any(w.get('exit_status') in ('ProviderError','DockerException','CalledProcessError','FileNotFoundError') for w in workers):
            raise EvaluationUnavailable('native_or_worker_infrastructure_failure')
        folder=work/'evaluations/candidate'
        valid=False
        if (folder/'harness').exists():
            try:bindings['validate'](folder/'harness');valid=True
            except common.InvalidCandidate as error:
                write_json(work/'candidate-invalid.json',{'reason':str(error),'checked_without_api':True})
                if list((folder/'trials').glob('*/worker-attempt.json')):raise
                proposal_status='invalid_candidate'
        if valid:
            scores=bindings['Evaluator'](cfg,instances,work)('candidate',folder/'harness',ids)
            kind='candidate'
        else:
            if list(work.glob('evaluations/candidate/trials/*/worker-attempt.json')):
                raise EvaluationUnavailable('Started candidate cannot be silently discarded')
            folder,scores=retest_parent(cfg,instances,work,parent)
            kind='unchanged_parent_retest'
        assert set(scores)==set(ids)
        trials={i:str(folder/'trials'/i) for i in ids}
        # Native failures or missing explicit decisions never promote a partial proposal.
        selected='candidate' if kind=='candidate' and native.get('selected')=='candidate' and not error_info else 'parent'
        if selected=='candidate' or kind=='unchanged_parent_retest':
            next_parent={'harness':str(folder/'harness'),'harness_sha256':common.fingerprint(folder/'harness'),
                'scores':scores,'trials':trials,'source_round':index}
        else:next_parent=parent
        common.copy_harness(Path(next_parent['harness']),work/'selected/harness')
        next_parent=dict(next_parent,harness=str(work/'selected/harness'))
        result={'status':'completed' if kind=='candidate' else 'completed_without_update',
            'framework':name,'round':index,'proposal_status':proposal_status,'native_error':error_info,
            'evaluated_kind':kind,'round_scores':scores,'round_resolved':int(sum(scores.values())),
            'evaluated_harness_sha256':common.fingerprint(folder/'harness'),'trials':trials,
            'candidate_scores':scores if kind=='candidate' else None,
            'native_selected':selected,'retained_resolved':int(sum(next_parent['scores'].values())),
            'retained_score_reused':selected=='parent' and kind=='candidate',
            'next_parent':next_parent,'native':native,'finished_at':time.time()}
        write_json(work/'result.json',result)
        write_json(work/'status.json',{'status':result['status'],'round_resolved':result['round_resolved'],
            'evaluated_kind':kind,'finished_at':time.time()})
        verify()
        print(json.dumps({k:result[k] for k in ('framework','round','status','round_resolved','evaluated_kind','native_selected')},ensure_ascii=False),flush=True)
        return 0
    except BaseException as error:
        (work/'evaluation-exception.txt').write_text(traceback.format_exc())
        result={'status':'infrastructure_stopped' if isinstance(error,(EvaluationUnavailable,ProviderError)) else 'step_failed',
            'framework':name,'round':index,'proposal_status':proposal_status,'native_error':error_info,
            'error_type':type(error).__name__,'round_scores':None,'next_parent':None,'automatic_paid_retry':False,
            'finished_at':time.time()}
        write_json(work/'result.json',result);write_json(work/'status.json',{'status':result['status'],'finished_at':time.time()})
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return 2


def main():
    p=argparse.ArgumentParser();p.add_argument('framework',choices=FRAMEWORKS);p.add_argument('round',type=int,choices=range(1,6))
    args=p.parse_args();raise SystemExit(execute(args.framework,args.round))


if __name__=='__main__':main()
