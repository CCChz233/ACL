import datetime
import shutil
import time
from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import write_json
from acl_unified import common
from acl_multiround.protocol import verify as verify_old
from acl_multiround.runtime import initial_state
from .protocol import WORK,OLD,CONFIG,FRAMEWORKS,round_dir,verify
from .runtime import legacy_usage_paths,legacy_worker_paths


def main():
    verify_old();common.preflight()
    if WORK.exists():raise ValueError('Reduction already initialized')
    # A reduction cannot silently abandon ongoing model calls. All old started
    # workers must have written their final record before taking the snapshot.
    for path in legacy_worker_paths():
        assert (path.parent/'worker.json').exists(), 'Old in-flight worker not finished yet'
    assert not any(OLD.glob('*/round-*/result.json')), 'Unexpected completed rounds; inspect before adopting'
    old=OLD/'harnessfix/round-1'
    assert 'BudgetExceeded: call_limit' in (old/'native-exception.txt').read_text()
    assert len(read(old/'optimizer-api/usage.json')['requests'])==80
    assert not (old/'evaluations/candidate').exists()
    cfg=read(OLD/'config.json')
    cfg.update(purpose='two-round-reduction-only-valid-new-harnesses',workspace=str(WORK))
    cfg['protocol'].update(rounds=2,max_new_target_executions=100,max_new_calls=5800,max_new_tokens=110000000,
        empty_round_policy='reuse parent scores/trajectories, mark unchanged; ZERO new target calls',
        scope_reduction='explicit user selected two rounds; carry already-spent HF1 search and cancelled parent-retest overhead',
        global_cap='100 target worker executions includes all legacy started retests; require 10 free slots for a new complete candidate evaluation')
    write_json(CONFIG,cfg);write_json(WORK/'config.json',cfg)
    for name in FRAMEWORKS:
        for index in (1,2):
            work=round_dir(name,index)
            write_json(work/'config.json',dict(cfg,workspace=str(work)))
            write_json(work/'storage-policy.json',{'retain_mini_images':True,'local_only':True})
    write_json(WORK/'baseline.json',read(OLD/'baseline.json'))
    state=initial_state(cfg['protocol']['all_task_ids'])
    work=round_dir('harnessfix',1)
    write_json(work/'input-parent.json',state)
    common.copy_harness(state['harness'],work/'selected/harness')
    next_parent=dict(state,harness=str(work/'selected/harness'))
    write_json(work/'result.json',{'status':'completed_without_update','framework':'harnessfix','round':1,
        'proposal_status':'search_budget_exhausted','native_error':{'type':'BudgetExceeded','classification':'search_budget_exhausted'},
        'evaluated_kind':'unchanged_parent_reused','round_scores':None,'round_resolved':None,'candidate_scores':None,
        'native_selected':'parent','retained_resolved':int(sum(state['scores'].values())),
        'retained_score_reused':True,'score_reused':True,'next_parent':next_parent,'unchanged_parent_new_calls':0,
        'optimizer_usage_reference':'harnessfix/round-1/optimizer-api/usage.json',
        'adopted_existing_search_without_new_calls':True,'finished_at':time.time()})
    write_json(work/'status.json',{'status':'completed_without_update','adopted_from_five_round_scope':True})
    files={}
    for p in (ROOT/'acl_multiround_v2').glob('*.py'):files[str(p.relative_to(ROOT))]=sha(p)
    files[str(CONFIG.relative_to(ROOT))]=sha(CONFIG)
    files['tests/test_two_rounds.py']=sha(ROOT/'tests/test_two_rounds.py')
    for p in WORK.glob('*/round-*/config.json'):files[str(p.relative_to(ROOT))]=sha(p)
    for p in legacy_usage_paths():files[str(p.relative_to(ROOT))]=sha(p)
    for p in (old/'input-parent.json',old/'native-exception.txt',old/'config.json'):files[str(p.relative_to(ROOT))]=sha(p)
    for p in legacy_worker_paths():
        for name in ('worker-attempt.json','worker.json','patch.diff'):
            file=p.parent/name;files[str(file.relative_to(ROOT))]=sha(file)
    write_json(WORK/'runtime-lock.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'files':files,'config_sha256':sha(CONFIG),'original_runtime_lock_sha256':sha(OLD/'runtime-lock.json'),
        'offline_checks':'see offline-validation.json'})
    write_json(WORK/'authorization.json',{'user_instruction':'统一跑2轮，最多100次任务评测（推荐）',
        'additional_selected_policy':'only evaluate valid new harness; reuse scores for unchanged parent and mark no update',
        'legacy_optimizer_search_reused':80,'legacy_target_executions_charged':len(legacy_worker_paths()),
        'max_total_worker_executions_including_legacy':100,'max_calls_including_legacy':5800,'max_tokens_including_legacy':110000000,
        'no_manual_candidate_edits':True,'retain_all_mini50_images':True})
    snapshot=WORK/'source-snapshot'
    for package in ('acl_multiround_v2','acl_multiround','acl_unified','acl_rsi','acl_gepa_swe','acl_frameworks','acl_dgm'):
        shutil.copytree(ROOT/package,snapshot/package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    audit=OLD/'scope-reduction';audit.mkdir(exist_ok=True)
    for f in ('batch-status.json','report.md','summary.json','harnessfix/round-1/status.json'):
        path=OLD/f
        if path.exists():
            target=audit/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    write_json(OLD/'scope-reduction.json',{'reason':'user selected two rounds and zero unchanged-parent retests',
        'new_workspace':str(WORK),'legacy_workers':len(legacy_worker_paths()),'legacy_usage_preserved':True,'changed_at':time.time()})
    write_json(OLD/'batch-status.json',{'status':'superseded_by_user_reduction','new_workspace':str(WORK),
        'old_scheduler_stopped':True,'updated_at':time.time()})
    write_json(old/'status.json',{'status':'stopped_on_scope_reduction','optimization_finished':True,'partial_parent_retests_preserved':True})
    (OLD/'report.md').write_text('# 已按用户要求缩减为两轮\n\n旧五轮队列已停止。当前结果请看 `../full10-two-rounds-v1/report.md`。\n\n原报告、状态和用量快照保存在 scope-reduction/；已发生消耗计入新方案总账，不重新调用模型。\n')
    verify()
    from .status import summarize
    summarize(write=True)
    print({'status':'two_rounds_frozen_ready','legacy_workers':len(legacy_worker_paths()),'adopted_hf_search_calls':80,'new_api_calls':0})


if __name__=='__main__':main()
