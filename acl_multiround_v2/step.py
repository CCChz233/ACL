"""Same native step adapters, at most two rounds; no unchanged-parent paid retest."""
import argparse
import json
from pathlib import Path
import time
import traceback
from acl_frameworks.common import read
from acl_rsi.settings import load_instances,write_json
from acl_rsi.deepseek import ProviderError
from acl_gepa_swe.feedback import EvaluationUnavailable
from acl_unified import common
from acl_multiround import adapters
from acl_multiround.step import exception_kind
from .protocol import FRAMEWORKS,round_dir,settings,verify
from .runtime import bind,parent_state


def execute(name,index):
    verify();common.preflight();cfg=settings(name,index);instances=load_instances(cfg)
    work=round_dir(name,index);ids=cfg['protocol']['all_task_ids']
    if (work/'started.json').exists():raise ValueError('Already started; no silent paid retry')
    parent=parent_state(name,index,ids)
    write_json(work/'input-parent.json',parent)
    write_json(work/'started.json',{'framework':name,'round':index,'started_at':time.time()})
    write_json(work/'status.json',{'status':'running','phase':'optimization','started_at':time.time()})
    b=bind(cfg,instances,work,parent)
    native={};error_info=None;proposal='native_finished'
    try:native=adapters.run(name,cfg,instances,work,b)
    except BaseException as error:
        if isinstance(error,KeyboardInterrupt):raise
        proposal=exception_kind(error);error_info={'type':type(error).__name__,'classification':proposal}
        (work/'native-exception.txt').write_text(traceback.format_exc())
    try:
        workers=[read(p) for p in work.glob('evaluations/candidate/trials/*/worker.json')]
        if (work/'global-budget-stop.json').exists():raise EvaluationUnavailable('global_100_task_execution_cap')
        if proposal=='infrastructure_stopped' or any(w.get('exit_status') in ('ProviderError','DockerException','CalledProcessError','FileNotFoundError') for w in workers):
            raise EvaluationUnavailable('native_or_worker_infrastructure_failure')
        folder=work/'evaluations/candidate';valid=False
        if (folder/'harness').exists():
            try:b['validate'](folder/'harness');valid=True
            except common.InvalidCandidate as error:
                write_json(work/'candidate-invalid.json',{'reason':str(error),'checked_without_api':True})
                if list((folder/'trials').glob('*/worker-attempt.json')):raise
                proposal='invalid_candidate'
        if valid:
            scores=b['Evaluator'](cfg,instances,work)('candidate',folder/'harness',ids)
            assert set(scores)==set(ids)
            kind='candidate';trials={i:str(folder/'trials'/i) for i in ids}
            fingerprint=common.fingerprint(folder/'harness')
        else:
            if list(work.glob('evaluations/candidate/trials/*/worker-attempt.json')):
                raise EvaluationUnavailable('Started candidate cannot be silently discarded')
            scores=None;trials=None;kind='unchanged_parent_reused';fingerprint=parent['harness_sha256']
        selected='candidate' if valid and native.get('selected')=='candidate' and not error_info else 'parent'
        next_parent={'harness':str(folder/'harness'),'harness_sha256':fingerprint,
            'scores':scores,'trials':trials,'source_round':index} if selected=='candidate' else parent
        common.copy_harness(Path(next_parent['harness']),work/'selected/harness')
        next_parent=dict(next_parent,harness=str(work/'selected/harness'))
        result={'status':'completed' if valid else 'completed_without_update','framework':name,'round':index,
            'proposal_status':proposal,'native_error':error_info,'native':native,
            'evaluated_kind':kind,'round_scores':scores,'round_resolved':int(sum(scores.values())) if scores is not None else None,
            'candidate_scores':scores,'evaluated_harness_sha256':fingerprint,'trials':trials,
            'native_selected':selected,'retained_resolved':int(sum(next_parent['scores'].values())),
            'retained_score_reused':selected=='parent','score_reused':not valid,
            'next_parent':next_parent,'finished_at':time.time(),'unchanged_parent_new_calls':0}
        write_json(work/'result.json',result)
        write_json(work/'status.json',{'status':result['status'],'finished_at':time.time()})
        verify()
        print(json.dumps({k:result[k] for k in ('framework','round','status','round_resolved','evaluated_kind','retained_resolved')},ensure_ascii=False),flush=True)
        return 0
    except BaseException as error:
        (work/'evaluation-exception.txt').write_text(traceback.format_exc())
        result={'status':'infrastructure_stopped' if isinstance(error,(EvaluationUnavailable,ProviderError)) else 'step_failed',
            'framework':name,'round':index,'proposal_status':proposal,'native_error':error_info,
            'error_type':type(error).__name__,'round_scores':None,'next_parent':None,'automatic_paid_retry':False,
            'finished_at':time.time()}
        write_json(work/'result.json',result);write_json(work/'status.json',{'status':result['status'],'finished_at':time.time()})
        print(json.dumps(result,ensure_ascii=False),flush=True);return 2


def main():
    p=argparse.ArgumentParser();p.add_argument('framework',choices=FRAMEWORKS);p.add_argument('round',type=int,choices=(1,2))
    a=p.parse_args();raise SystemExit(execute(a.framework,a.round))


if __name__=='__main__':main()
