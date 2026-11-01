"""Versioned DGM empty-unresolved-list bug fix; no candidate or budget rescue."""
import argparse
import ast
import contextlib
import inspect
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import yaml

from acl_frameworks.common import ROOT, read, sha
from acl_rsi.settings import load_settings, load_instances, write_json
from acl_rsi.deepseek import BudgetExceeded, ProviderError
from acl_gepa_swe.feedback import EvaluationUnavailable
from acl_unified import common
from acl_unified.framework import verify_lock, finish_report, source_is_candidate_error
from acl_unified.protocol import WORK, H0

REC = ROOT/'experiments/runs/unified-hard10-v1-dgm-empty-recovery1'
BEFORE = '''            if unresolved_ids == 0:
                continue
            entry_ids = unresolved_ids'''
AFTER = '''            entry_ids = unresolved_ids or empty_ids
            if not entry_ids:
                continue'''


def patched_choose(native):
    source=inspect.getsource(native.choose_selfimproves)
    if source.count(BEFORE)!=1:raise ValueError('Unexpected upstream branch; refuse patch')
    namespace=dict(native.__dict__)
    exec(compile(source.replace(BEFORE,AFTER),str(REC/'choose_selfimproves.py'),'exec'),namespace)
    return namespace['choose_selfimproves'],source.replace(BEFORE,AFTER)


def offline_check():
    """The real fresh baseline has zero unresolved-with-patch and three empty IDs."""
    from acl_dgm.native import outer
    folder=WORK/'dgm/controller/output_dgm/pilot'
    meta=read(folder/'initial/metadata.json')['overall_performance']
    assert not meta['total_unresolved_ids'] and len(meta['total_emptypatch_ids'])==3
    with outer(lambda *a,**kw:None,17) as native:
        choose,source=patched_choose(native)
        chosen=choose(str(folder),['initial'],1)
    assert len(chosen)==1 and chosen[0][0]=='initial'
    assert chosen[0][1] in meta['total_emptypatch_ids']+['solve_empty_patches','solve_stochasticity','solve_contextlength']
    return chosen,source


def worker():
    from acl_dgm import adapter
    from acl_unified import dgm
    audit=read(REC/'authorization.json')
    verify_lock()
    assert sha(Path(__file__))==audit['controller_sha256']
    assert sha(WORK/'dgm/result.json')==audit['original_result_sha256']
    assert not (REC/'started.json').exists()
    write_json(REC/'started.json',{'started_at':time.time()})
    cfg=load_settings(REC/'config.json');cfg['framework_name']='dgm'
    instances=load_instances(cfg)
    original_outer=adapter.outer
    @contextlib.contextmanager
    def corrected_outer(*args,**kwargs):
        with original_outer(*args,**kwargs) as native:
            native.choose_selfimproves,source=patched_choose(native)
            assert source==(REC/'choose_selfimproves.py').read_text()
            yield native
    adapter.outer=corrected_outer
    original_validate=common.validate
    def strict(folder,**options):
        result=original_validate(folder,**options)
        if options.get('require_change',True):
            same_ast=ast.dump(ast.parse((Path(folder)/'agent.py').read_text()))==ast.dump(ast.parse((H0/'agent.py').read_text()))
            same_yaml=yaml.safe_load((Path(folder)/'swebench.yaml').read_text())==yaml.safe_load((H0/'swebench.yaml').read_text())
            if same_ast and same_yaml:raise common.InvalidCandidate('Semantic no-operation')
        return result
    common.validate=strict
    try:
        native=dgm.run(cfg,instances,REC)
        result=finish_report(cfg,instances,REC,native)
    except Exception as error:
        (REC/'exception.txt').write_text(traceback.format_exc())
        invalid=isinstance(error,common.InvalidCandidate) or source_is_candidate_error(REC)
        result={'status':'invalid_candidate' if invalid else 'budget_exhausted' if isinstance(error,BudgetExceeded)
            else 'infrastructure_stopped' if isinstance(error,(EvaluationUnavailable,ProviderError)) else 'native_run_failed',
            'error_type':type(error).__name__,'candidate_report_scores':None,'automatic_paid_retry':False}
    result.update(framework='dgm',finished_at=time.time(),
        scope='adapted DGM engineering recovery; upstream empty-list selection branch fixed in memory',
        original_native_failed=True, candidate_repair=False,optimizer_budget_increased=False)
    verify_lock()
    assert sha(WORK/'dgm/result.json')==audit['original_result_sha256']
    write_json(REC/'result.json',result)
    write_json(REC/'status.json',{'status':result['status'],'finished_at':time.time()})
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--worker',action='store_true')
    args=parser.parse_args()
    if args.worker:worker();return
    verify_lock()
    assert not (WORK/'dgm/optimizer-api/usage.json').exists(), 'Original DGM spent calls; refuse fresh budget'
    chosen,source=offline_check()
    if not args.run:
        print(json.dumps({'offline_selection':chosen,'api_calls':0,'source_modified_on_disk':False}));return
    if REC.exists():raise ValueError('Recovery already exists; no silent retry')
    common.preflight()
    from scripts.continue_unified_pilot import cap_guard
    cap_guard(580,11000000,10)
    REC.mkdir(parents=True)
    cfg=read(WORK/'dgm/config.json');cfg['workspace']=str(REC)
    write_json(REC/'config.json',cfg)
    (REC/'choose_selfimproves.py').write_text(source)
    (REC/'controller-source.py').write_bytes(Path(__file__).read_bytes())
    write_json(REC/'storage-policy.json',{'retain_mini_images':True})
    write_json(REC/'authorization.json',{'user_instruction':'继续吧，把这个全做完。',
        'created_at':time.time(),'original_result_sha256':sha(WORK/'dgm/result.json'),
        'controller_sha256':sha(Path(__file__)),'upstream_function_sha256':sha(REC/'choose_selfimproves.py'),
        'reason':'Native list == 0 guard falls through to random.choice([]) when all failed tasks have empty patches',
        'fix':'unresolved_ids or empty_ids; skip if both empty; same parent probabilities/seed17',
        'original_optimizer_calls':0,'max_optimizer_calls':80,'max_optimizer_tokens':1000000,
        'new_candidates_max':1,'framework_wall_seconds':30000,'manual_candidate_edits':False,
        'scope':'separate adapted engineering run, not untouched formal DGM result'})
    write_json(REC/'status.json',{'status':'running','started_at':time.time()})
    with (REC/'process.log').open('a') as log:
        proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],cwd=ROOT,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',LITELLM_LOCAL_MODEL_COST_MAP='True'),
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:proc.wait(timeout=30000)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            write_json(REC/'status.json',{'status':'framework_wall_limit','finished_at':time.time()})
    subprocess.run([sys.executable,str(ROOT/'scripts/summarize_unified_completion.py')],cwd=ROOT,check=True)


if __name__=='__main__':main()
