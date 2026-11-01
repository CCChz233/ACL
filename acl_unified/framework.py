"""One isolated framework process; nomination precedes sealed report feedback."""
import argparse
import ast
import importlib
import json
from pathlib import Path
import shutil
import time
import traceback
import yaml

from acl_frameworks.common import ROOT,read,sha,verify
from acl_dgm.native import verify as verify_dgm
from acl_rsi.deepseek import BudgetExceeded,ProviderError
from acl_rsi.settings import load_instances,write_json
from acl_gepa_swe.feedback import record,EvaluationUnavailable
from . import common
from .protocol import WORK,CONFIG,FRAMEWORKS,H0,FILES


def verify_lock():
    lock=read(WORK/'optimizer-runtime-lock.json')
    for path,digest in lock['files'].items():
        if sha(ROOT/path)!=digest:raise ValueError('Unified optimizer source changed: '+path)
    recorded={p for p in lock['files'] if p.startswith('acl_unified/')}
    if recorded!={str(p.relative_to(ROOT)) for p in (ROOT/'acl_unified').glob('*.py')}:
        raise ValueError('Unified module set changed')
    if sha(CONFIG)!=lock['config_sha256']:raise ValueError('Unified configuration changed')
    for name in FRAMEWORKS:
        verify_dgm() if name=='dgm' else verify(name)


def baseline_scores(cfg,instances,ids):
    return {i:record(common.baseline_trial(i),i,instances[i],trace=False)['score'] for i in ids}


def source_is_candidate_error(work):
    """Only classify an API400 as candidate-caused when the recorded protocol is malformed."""
    for path in work.glob('evaluations/candidate/trials/*/worker.json'):
        worker=read(path)
        if worker.get('provider_error',{}).get('status_code')!=400:continue
        trial=path.parent
        for request in (trial/'api-requests').glob('*.json'):
            outstanding=set()
            for m in read(request).get('messages',[]):
                role=m.get('role')
                if role=='assistant':
                    if outstanding:return True
                    outstanding={t['id'] for t in m.get('tool_calls',[])}
                elif role=='tool':
                    if m.get('tool_call_id') not in outstanding:return True
                    outstanding.remove(m['tool_call_id'])
                elif outstanding:return True
            if outstanding:return True
    return False


def finish_report(cfg,instances,work,native):
    dev,report=cfg['protocol']['development_ids'],cfg['protocol']['report_ids']
    folder=work/'evaluations/candidate/harness'
    base=baseline_scores(cfg,instances,dev+report)
    if not folder.exists():
        write_json(work/'nomination.json',{'selected':'h0','reason':'no scored native candidate',
            'h0_sha256':common.fingerprint(H0),'frozen_at':time.time(),
            'six_task_feedback_not_provided_to_optimizer':True})
        return {'status':'native_finished_without_scored_candidate','selected':'h0','candidate_report_scores':None,
                'selected_report_scores':{i:base[i] for i in report},'native':native}
    common.validate(folder)
    # Native GEPA result is retained; for a single child its best score/tie behavior
    # is independently checked against the same four stored dev scores.
    child_dev={i:record(folder.parent/'trials'/i,i,instances[i],trace=False)['score'] for i in dev}
    selected=native.get('selected')
    if selected is None and cfg['framework_name']=='gepa':
        selected='candidate' if sum(child_dev.values())>sum(base[i] for i in dev) else 'h0'
    if selected not in ('h0','candidate'):raise ValueError('Missing native nomination')
    nomination={'selected':selected,'dev_scores':child_dev,'baseline_dev_scores':{i:base[i] for i in dev},
        'candidate_sha256':common.fingerprint(folder),'frozen_at':time.time(),
        'six_task_feedback_not_provided_to_optimizer':True}
    write_json(work/'nomination.json',nomination)
    scores=common.Evaluator(cfg,instances,work)('candidate',folder,report,report=True)
    if common.fingerprint(folder)!=nomination['candidate_sha256']:raise ValueError('Candidate changed during report')
    return {'status':'completed','selected':selected,'candidate_dev_scores':child_dev,
        'baseline_dev_scores':{i:base[i] for i in dev},'candidate_report_scores':scores,
        'baseline_report_scores':{i:base[i] for i in report},
        'selected_report_scores':scores if selected=='candidate' else {i:base[i] for i in report},
        'raw_candidate_all10':{**child_dev,**scores},'fresh_baseline_all10':base,'native':native,
        'scope':'single-candidate pilot; report tasks historically used, not unseen'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('framework',choices=FRAMEWORKS)
    name=parser.parse_args().framework
    verify_lock()
    if read(WORK/'baseline/status.json')['status']!='completed':raise ValueError('Fresh baseline not completed')
    cfg=common.settings(name);cfg['framework_name']=name
    instances=load_instances(cfg);work=WORK/name
    if (work/'status.json').exists():raise ValueError('Framework already started; no silent retry')
    write_json(work/'status.json',{'status':'running','started_at':time.time()})
    original_validate=common.validate
    def audited_validate(folder,**options):
        try:
            checked=original_validate(folder,**options)
            if options.get('require_change',True):
                ast_same=ast.dump(ast.parse((Path(folder)/'agent.py').read_text()))==ast.dump(ast.parse((H0/'agent.py').read_text()))
                yaml_same=yaml.safe_load((Path(folder)/'swebench.yaml').read_text())==yaml.safe_load((H0/'swebench.yaml').read_text())
                if ast_same and yaml_same:raise common.InvalidCandidate('Semantic no-operation: only formatting/comments changed')
            return checked
        except common.InvalidCandidate as error:
            write_json(work/'candidate-invalid.json',{'type':type(error).__name__,'reason':str(error)[:300]})
            raise
    common.validate=audited_validate
    modules={'harnessfix':'harnessfix','meta-harness':'meta','gepa':'gepa','rrsi':'rrsi','dgm':'dgm'}
    try:
        native=importlib.import_module('acl_unified.'+modules[name]).run(cfg,instances,work)
        if (work/'candidate-invalid.json').exists():raise common.InvalidCandidate('Candidate rejected by shared gate')
        # Infrastructure exceptions may be caught by native loops; never accept a
        # partly evaluated candidate as a valid outcome or as a measured zero.
        folder=work/'evaluations/candidate'
        if folder.exists():
            for iid in cfg['protocol']['development_ids']:
                record(folder/'trials'/iid,iid,instances[iid],trace=False)
        result=finish_report(cfg,instances,work,native)
        code=0
    except BaseException as error:
        invalid=(work/'candidate-invalid.json').exists() or isinstance(error,common.InvalidCandidate) or source_is_candidate_error(work)
        budget=isinstance(error,BudgetExceeded)
        # Native loops can wrap provider/budget exceptions; consult only explicit
        # persisted records, rather than inventing task scores.
        infra=isinstance(error,(EvaluationUnavailable,ProviderError)) and not invalid
        workers=[read(p) for p in work.glob('evaluations/candidate/trials/*/worker.json')]
        if any(w.get('exit_status') in ('DockerException','CalledProcessError','FileNotFoundError','ProviderError') for w in workers) and not invalid:infra=True
        nomination=work/'nomination.json'
        if not nomination.exists():
            write_json(nomination,{'selected':'h0','reason':'native run did not produce an eligible nomination',
                'h0_sha256':common.fingerprint(H0),'frozen_at':time.time(),
                'six_task_feedback_not_provided_to_optimizer':True})
        selected=read(nomination)['selected']
        result={'status':'invalid_candidate' if invalid else 'budget_exhausted' if budget else 'infrastructure_stopped' if infra else 'native_run_failed',
            'error_type':type(error).__name__,'selected':selected,'candidate_report_scores':None,
            'selected_report_scores':baseline_scores(cfg,instances,cfg['protocol']['report_ids']) if selected=='h0' else None,
            'automatic_paid_retry':False,'manual_recovery':False}
        # Tracebacks contain source and sanitized provider errors, never raw SDK exceptions.
        (work/'exception.txt').write_text(traceback.format_exc())
        code=2 if infra else 0
    result.update(framework=name,finished_at=time.time())
    write_json(work/'result.json',result)
    write_json(work/'status.json',{'status':result['status'],'finished_at':time.time()})
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(code)


if __name__=='__main__':main()
