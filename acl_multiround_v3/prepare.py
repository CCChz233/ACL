"""Freeze a fresh all-framework rerun, with a larger shared search allowance."""
import datetime
import shutil
from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import write_json
from acl_unified import common
from acl_multiround_v2.protocol import verify as verify_previous
from .protocol import WORK,OLD,CONFIG,FRAMEWORKS,round_dir,verify


def main():
    verify_previous();common.preflight()
    if WORK.exists():raise ValueError('High-budget experiment already initialized')
    cfg=read(OLD/'config.json')
    cfg.update(purpose='highbudget-two-rounds-required-real-harness-delivery',workspace=str(WORK))
    cfg['search'].update(max_calls=400,max_tokens=8000000,max_output_tokens=4096)
    cfg['protocol'].update(rounds=2,max_new_target_executions=100,max_new_calls=9000,max_new_tokens=180000000,
        search_wall_seconds=7200,framework_wall_seconds=36000,native_call_cap=300,native_token_cap=6000000,
        empty_round_policy='delivery_failed, do not claim unchanged H0 is a successful modification',
        scope_reduction='fresh high-budget rerun; old lower-budget results retained separately',
        native_parameters={'hf_analysis':20,'hf_planning':60,'hf_implementation':100,
            'rrsi_analyst_turns':3,'rrsi_digester_turns':6,'rrsi_propose_turns':80},
        model_validity_repair='up to three sessions inside same400/8M ledger, only before task evaluation; no human edits',
        native_completion='at most two native checkpoint attempts, no paid task retries and one evaluated final candidate',
        protocol_scope='high budget plus stage allocation and explicit model validity repair; not a pure budget-only ablation')
    write_json(CONFIG,cfg);write_json(WORK/'config.json',cfg)
    for name in FRAMEWORKS:
        for index in (1,2):
            work=round_dir(name,index)
            write_json(work/'config.json',dict(cfg,workspace=str(work)))
            write_json(work/'storage-policy.json',{'retain_mini_images':True,'local_only':True})
    write_json(WORK/'baseline.json',read(OLD/'baseline.json'))
    files={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'acl_multiround_v3').glob('*.py')}
    files[str(CONFIG.relative_to(ROOT))]=sha(CONFIG)
    files['tests/test_highbudget.py']=sha(ROOT/'tests/test_highbudget.py')
    for p in WORK.glob('*/round-*/config.json'):files[str(p.relative_to(ROOT))]=sha(p)
    write_json(WORK/'runtime-lock.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'files':files,'config_sha256':sha(CONFIG),'previous_runtime_lock_sha256':sha(OLD/'runtime-lock.json')})
    write_json(WORK/'authorization.json',{'user_instruction':'加大那个步骤吧，然后重跑一下，必须得让它修改出来',
        'scope':'five frameworks, two rounds, same ten tasks, real native artifact plus metered model repair',
        'search_per_round':cfg['search'],'target_per_task':cfg['target'],
        'native_phase_limit':[300,6000000],'overall_optimizer_limit':[400,8000000],
        'max_calls':9000,'max_tokens':180000000,'max_task_executions':100,
        'manual_candidate_source_edits':False,'retain_all50_mini_images':True})
    snapshot=WORK/'source-snapshot'
    for package in ('acl_multiround_v3','acl_multiround_v2','acl_multiround','acl_unified','acl_rsi','acl_gepa_swe','acl_frameworks','acl_dgm'):
        shutil.copytree(ROOT/package,snapshot/package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    verify()
    from .status import summarize
    summarize(write=True)
    print({'status':'highbudget_frozen_ready','per_round_calls':400,'per_round_tokens':8000000,'rounds':10,'new_api_calls':0})


if __name__=='__main__':main()
