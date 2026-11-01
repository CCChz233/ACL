"""Explicitly authorized infrastructure continuation; frozen pilot files stay intact.

GEPA's failed report worker restarts once with the unused portion of its original
budget. This is an engineering continuation, not an untouched formal execution.
Unstarted RRSI/DGM stages use the original frozen runners and budgets.
"""
import argparse
import copy
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

from acl_frameworks.common import ROOT, read, sha
from acl_gepa_swe.executor import SWEExecutor
from acl_gepa_swe.feedback import record
from acl_rsi.settings import load_instances, load_settings, write_json
from acl_unified import common
from acl_unified.framework import verify_lock, baseline_scores
from acl_unified.protocol import WORK, FRAMEWORKS
from acl_unified.status import summarize, ledger

CONT = ROOT / 'experiments/runs/unified-hard10-v1-continuation1'
FAILED = 'django__django-12039'


def remaining(target, worker):
    return dict(target,
        max_calls=target['max_calls']-worker['usage']['calls'],
        max_tokens=target['max_tokens']-worker['usage']['charged_tokens'],
        wall_seconds=max(0, math.floor(target['wall_seconds']-worker['seconds'])))


def plan():
    verify_lock()
    cfg = common.settings('gepa')
    folder = WORK/'gepa'
    nomination = read(folder/'nomination.json')
    assert nomination['candidate_sha256'] == common.fingerprint(folder/'evaluations/candidate/harness')
    assert nomination['selected'] == 'candidate'
    worker = read(folder/f'evaluations/candidate/trials/{FAILED}/worker.json')
    assert worker['provider_error']['type'] == 'APIConnectionError'
    rest = remaining(cfg['target'], worker)
    assert all(rest[k] > 0 for k in ('max_calls','max_tokens','wall_seconds'))
    ids = cfg['protocol']['report_ids']
    missing = [i for i in ids if not (folder/f'evaluations/candidate/trials/{i}/grade.json').exists()]
    assert FAILED in missing
    return {'user_instruction':'继续吧，把这个全做完。', 'authorized_at':time.time(),
        'original_work':str(WORK), 'scope':'same immutable GEPA candidate, report only; unstarted RRSI/DGM',
        'gepa_nomination_sha256':sha(folder/'nomination.json'),
        'gepa_candidate_sha256':nomination['candidate_sha256'],
        'gepa_missing_report_ids':missing, 'gepa_retry_id':FAILED,
        'gepa_retry_target_limits':rest,
        'retry_policy':'one explicitly authorized restart, original failed usage charged; no automatic retries',
        'protocol_deviation':'fresh task context after API connection failure, residual original task budget; report separately',
        'no_optimizer_recovery_or_budget_increase':True,
        'original_result_sha256':{n:sha(WORK/n/'result.json') for n in ('harnessfix','meta-harness','gepa')},
        'frozen_runtime_lock_sha256':sha(WORK/'optimizer-runtime-lock.json'),
        'controller_sha256':sha(Path(__file__)),
        'total_caps':{'calls':3400,'charged_or_reserved_tokens':65000000,'target_executions':60}}


def usages():
    original = list(WORK.glob('*/optimizer-api/usage.json')) + list(WORK.glob('*/evaluations/*/trials/*/usage.json'))
    extra = list(CONT.glob('gepa/evaluations/candidate/trials/*/usage.json'))
    return ledger(original+extra)


def verify_original(audit):
    verify_lock()
    for name, digest in audit['original_result_sha256'].items():
        assert sha(WORK/name/'result.json') == digest
    assert sha(WORK/'gepa/nomination.json') == audit['gepa_nomination_sha256']
    assert common.fingerprint(WORK/'gepa/evaluations/candidate/harness') == audit['gepa_candidate_sha256']


def cap_guard(calls=0, tokens=0, executions=0):
    u = usages()
    used = len(list(WORK.glob('*/evaluations/*/trials/*/worker-attempt.json')))
    used += len(list(CONT.glob('gepa/evaluations/*/trials/*/worker-attempt.json')))
    assert u['calls']+calls <= 3400
    assert u['charged_or_reserved_tokens']+tokens <= 65000000
    assert used+executions <= 60


def resume_gepa(audit):
    work = CONT/'gepa'
    work.mkdir(parents=True, exist_ok=True)
    if (work/'result.json').exists():return read(work/'result.json')
    if (work/'started.json').exists():raise RuntimeError('Continuation already started; no silent second retry')
    write_json(work/'started.json',{'started_at':time.time(),'explicit_paid_restart':True})
    cfg = common.settings('gepa'); instances = load_instances(cfg)
    folder = work/'evaluations/candidate'
    common.copy_harness(WORK/'gepa/evaluations/candidate/harness',folder/'harness')
    write_json(work/'storage-policy.json',{'retain_mini_images':True})
    nomination = read(WORK/'gepa/nomination.json')
    try:
        common.validate(folder/'harness')
        for iid in audit['gepa_missing_report_ids']:
            verify_original(audit)
            common.preflight()
            one = copy.deepcopy(read(WORK/'gepa/config.json'))
            one['workspace'] = str(work)
            if iid == FAILED:one['target'] = audit['gepa_retry_target_limits']
            cap_guard(one['target']['max_calls'],one['target']['max_tokens'],1)
            config_path = work/'configs'/f'{iid}.json'
            write_json(config_path,one)
            one = load_settings(config_path)
            write_json(work/'progress.json',{'status':'running','current_task':iid,'updated_at':time.time()})
            print('[continuation] GEPA report '+iid,flush=True)
            SWEExecutor(one,work,instances).trial(iid,folder)
        measured={}; sources={}
        for iid in cfg['protocol']['all_task_ids']:
            source = folder/'trials'/iid if iid in audit['gepa_missing_report_ids'] else WORK/'gepa/evaluations/candidate/trials'/iid
            measured[iid]=record(source,iid,instances[iid],trace=False)['score']
            sources[iid]=str(source.relative_to(ROOT))
            if iid in cfg['protocol']['report_ids']:
                assert read(source/'worker-attempt.json')['started_at'] >= nomination['frozen_at']
        base=baseline_scores(cfg,instances,cfg['protocol']['all_task_ids'])
        scores={i:measured[i] for i in cfg['protocol']['report_ids']}
        result={'status':'completed_with_infrastructure_retry','selected':nomination['selected'],
            'candidate_dev_scores':nomination['dev_scores'],'candidate_report_scores':scores,
            'selected_report_scores':scores, 'raw_candidate_all10':measured,
            'fresh_baseline_all10':base,'trial_sources':sources,
            'manual_infrastructure_recovery':True,'candidate_repair':False,
            'protocol_deviation':audit['protocol_deviation']}
    except Exception as error:
        (work/'exception.txt').write_text(traceback.format_exc())
        result={'status':'continuation_stopped','error_type':type(error).__name__,
            'candidate_report_scores':None,'automatic_paid_retry':False}
    verify_original(audit)
    write_json(work/'result.json',dict(result,finished_at=time.time()))
    return result


def run_unstarted(name):
    work=WORK/name
    if (work/'result.json').exists():return read(work/'result.json')
    if (work/'status.json').exists():raise RuntimeError('Stage already started; no silent retry: '+name)
    cap_guard(580,11000000,10)
    verify_lock();common.preflight()
    print('[continuation] Starting original frozen '+name,flush=True)
    with (work/'process.log').open('a') as log:
        proc=subprocess.Popen([sys.executable,'-m','acl_unified.framework',name],cwd=ROOT,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',LITELLM_LOCAL_MODEL_COST_MAP='True'),
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=proc.wait(timeout=30000)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            code=124
    return read(work/'result.json') if (work/'result.json').exists() else {'status':'process_failed','exit_code':code}


def report():
    data=summarize()
    recovery=CONT/'gepa/result.json'
    if recovery.exists():data['frameworks']['gepa']['continuation']=read(recovery)
    data['whole_experiment_usage_including_continuation']=usages()
    audit=read(CONT/'authorization.json')
    verify_original(audit);cap_guard()
    data['continuation_authorization']=audit
    data['continuation_status']=read(CONT/'status.json') if (CONT/'status.json').exists() else {}
    cfg=common.settings('gepa'); instances=load_instances(cfg)
    rows=[]
    for name in FRAMEWORKS:
        item=data['frameworks'][name]
        result=item.get('continuation',item)
        scores=result.get('candidate_report_scores');all10=result.get('raw_candidate_all10')
        if scores is not None:
            assert set(scores)==set(cfg['protocol']['report_ids'])
            measured={}
            nomination=read(WORK/name/'nomination.json')
            assert common.fingerprint(WORK/name/'evaluations/candidate/harness')==nomination['candidate_sha256']
            for iid in cfg['protocol']['all_task_ids']:
                source=ROOT/result['trial_sources'][iid] if 'trial_sources' in result else WORK/name/'evaluations/candidate/trials'/iid
                measured[iid]=record(source,iid,instances[iid],trace=False)['score']
                if iid in cfg['protocol']['report_ids']:assert read(source/'worker-attempt.json')['started_at']>=nomination['frozen_at']
            assert measured==all10
            assert scores=={i:measured[i] for i in cfg['protocol']['report_ids']}
        rows.append((name,result['status'],f'{int(sum(scores.values()))}/6' if scores is not None else 'N/A',
            f'{int(sum(all10.values()))}/10' if all10 is not None else 'N/A'))
    write_json(CONT/'summary.json',data)
    lines=['# 统一十题实验：含明确授权的中断续跑','',
        '新 H0：开发 1/4，冻结后评测 2/6，全十题 3/10。全部任务为历史开发数据。','',
        'GEPA 候选及原始提名不变；连接失败题仅用原预算余额重新开始，失败调用计费保留，单列工程续跑。其余框架无额外搜索/人工候选修复。','',
        '| 框架 | 状态 | 候选评测六题 | 候选十题（描述性） |','|---|---|---:|---:|']
    lines += ['| '+' | '.join(row)+' |' for row in rows]
    u=usages()
    lines += ['',f'含 H0、所有失败与续跑：{u["calls"]} 次请求；已知实际 token {u["actual_tokens"]:,}；未知 usage {u["unknown_usage_requests"]} 次；含预留 {u["charged_or_reserved_tokens"]:,} token。',
        '', 'N/A 不代表 0 分；未产出有效候选的框架保留 H0。原始中断结果仍保存在 unified-hard10-v1，未覆盖。',
        '', 'GEPA 开发集提升不能独立证明泛化；十题仅为单次工程筛选，不能据此宣称框架稳定优劣。','']
    (CONT/'report.md').write_text('\n'.join(lines))
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--report',action='store_true')
    args=parser.parse_args()
    if args.report:
        data=report();print(json.dumps({'usage':usages(),'status':data['continuation_status']},ensure_ascii=False));return
    audit=plan()
    if not args.run:
        print(json.dumps(audit,ensure_ascii=False,indent=2));return
    CONT.mkdir(parents=True,exist_ok=True)
    with (CONT/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (CONT/'authorization.json').exists():raise RuntimeError('Continuation already started')
        common.preflight()
        write_json(CONT/'authorization.json',audit)
        (CONT/'controller-source.py').write_bytes(Path(__file__).read_bytes())
        states={}
        for name in ('gepa','rrsi','dgm'):
            write_json(CONT/'status.json',{'status':'running','current_framework':name,'frameworks':states,'updated_at':time.time()})
            try:
                result=resume_gepa(audit) if name=='gepa' else run_unstarted(name)
                states[name]=result['status']
            except Exception as error:
                (CONT/f'{name}-controller-exception.txt').write_text(traceback.format_exc())
                states[name]='controller_stopped:'+type(error).__name__
            write_json(CONT/'status.json',{'status':'running','current_framework':name,'frameworks':states,'updated_at':time.time()})
            report()
        completed=all(s in ('completed','completed_with_infrastructure_retry','invalid_candidate',
            'budget_exhausted','native_run_failed','native_finished_without_scored_candidate') for s in states.values())
        write_json(CONT/'status.json',{'status':'finished' if completed else 'finished_with_unresolved_errors',
            'frameworks':states,'finished_at':time.time(),'automatic_paid_retry':False})
        report()
        print(json.dumps(states,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
