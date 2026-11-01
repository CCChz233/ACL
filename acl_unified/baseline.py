"""Fresh common H0; exact frozen historical worker, local images only."""
import shutil
import time

from acl_frameworks.common import ROOT,read,sha
from acl_gepa_swe.executor import SWEExecutor
from acl_gepa_swe.feedback import record
from acl_rsi.settings import load_instances,write_json
from .protocol import WORK,H0,FILES,prepare
from .common import settings,copy_harness,preflight,protocol_contract


def main():
    prepare()
    cfg=settings('baseline'); cfg['evolve_ids']=cfg['protocol']['all_task_ids']
    # The saved baseline config still hides no data from a model: only task workers read it.
    path=WORK/'baseline/config.json'; raw=read(path); raw['evolve_ids']=cfg['evolve_ids']; write_json(path,raw)
    from acl_rsi.settings import load_settings
    cfg=load_settings(path); instances=load_instances(cfg)
    status=WORK/'baseline/status.json'
    if status.exists():
        raise ValueError('Baseline already started; never automatically rerun paid work')
    preflight(); protocol_contract(H0)
    folder=WORK/'baseline/evaluations/h0'
    copy_harness(H0,folder/'harness')
    write_json(WORK/'baseline/runtime-lock.json',{'config_sha256':sha(path),
        'runner':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'acl_gepa_swe').glob('*.py')},
        'baseline_controller':sha(__file__),'common':sha(ROOT/'acl_unified/common.py'),
        'protocol':sha(ROOT/'acl_unified/protocol.py'),'harness':{f:sha(H0/f) for f in FILES}})
    write_json(status,{'status':'running','started_at':time.time()})
    scores={}
    try:
        executor=SWEExecutor(cfg,WORK/'baseline',instances)
        for iid in cfg['evolve_ids']:
            preflight()
            executor.trial(iid,folder)
            trial=folder/'trials'/iid
            scores[iid]=record(trial,iid,instances[iid],trace=False)['score']
            alias=WORK/'baseline/runs/swe/jobs/base'/iid/'trial-0'
            alias.parent.mkdir(parents=True,exist_ok=True)
            alias.symlink_to(trial)
            write_json(WORK/'baseline/progress.json',{'graded':len(scores),'total':10,'scores':scores})
        write_json(WORK/'baseline/result.json',{'status':'completed','fresh':True,'scores':scores,
            'resolved':sum(scores.values()),'total':10,'development_ids':cfg['protocol']['development_ids'],
            'report_ids':cfg['protocol']['report_ids']})
        write_json(status,{'status':'completed','finished_at':time.time()})
    except BaseException as e:
        write_json(status,{'status':'stopped','error_type':type(e).__name__,'automatic_paid_retry':False})
        raise


if __name__=='__main__':main()
