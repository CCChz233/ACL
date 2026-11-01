"""Freeze the entire prospective protocol and source before the first paid call."""
import datetime
from pathlib import Path
import shutil
from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import write_json
from acl_unified.framework import verify_lock
from acl_unified.common import preflight
from acl_unified.status import ledger
from .protocol import WORK,CONFIG,BASE,H0,FILES,FRAMEWORKS,prepare,verify
from .runtime import initial_state


def main():
    verify_lock();cfg=prepare();preflight()
    ids=cfg['protocol']['all_task_ids'];state=initial_state(ids)
    assert sum(state['scores'].values())==3
    baseline_files={}
    for iid in ids:
        for f in ('trajectory.json','worker.json','grade.json','patch.diff','manifest.json','usage.json'):
            p=BASE/'trials'/iid/f;baseline_files[str(p.relative_to(ROOT))]=sha(p)
    for f in FILES:baseline_files[str((H0/f).relative_to(ROOT))]=sha(H0/f)
    baseline_files[str((ROOT/'configs/swe-mini-image-cache.json').relative_to(ROOT))]=sha(ROOT/'configs/swe-mini-image-cache.json')
    write_json(WORK/'baseline.json',{'scores':state['scores'],'resolved':3,'harness_sha256':state['harness_sha256'],
        'source':str(BASE),'reused_without_new_calls':True,
        'historical_usage':ledger([BASE/'trials'/iid/'usage.json' for iid in ids])})
    files=dict(read(ROOT/'experiments/runs/unified-hard10-v1/optimizer-runtime-lock.json')['files'])
    for p in (ROOT/'acl_multiround').glob('*.py'):files[str(p.relative_to(ROOT))]=sha(p)
    files[str(CONFIG.relative_to(ROOT))]=sha(CONFIG)
    files['tests/test_multiround.py']=sha(ROOT/'tests/test_multiround.py')
    files['pyproject.toml']=sha(ROOT/'pyproject.toml')
    for p in WORK.glob('*/round-*/config.json'):files[str(p.relative_to(ROOT))]=sha(p)
    write_json(WORK/'runtime-lock.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'files':files,'config_sha256':sha(CONFIG),'baseline_files':baseline_files,
        'tests':'full10 longitudinal offline tests plus existing unified contracts, see offline-validation.json'})
    write_json(WORK/'authorization.json',{'user_instruction':'那你现在开始跑一下吧。',
        'agreed_design':'one shared H0, same ten tasks each round, five independent frameworks, rounds1..5',
        'model':'deepseek-flash','api_base':'https://api.deepseek.com',
        'per_round_search':cfg['search'],'per_task':cfg['target'],
        'max_new_target_executions':250,'max_new_calls':14500,'max_new_tokens':275000000,
        'retain_all_mini_images':True,'no_manual_candidate_edits':True})
    snapshot=WORK/'source-snapshot'
    for package in ('acl_multiround','acl_unified','acl_rsi','acl_gepa_swe','acl_frameworks','acl_dgm'):
        shutil.copytree(ROOT/package,snapshot/package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    verify()
    from .status import summarize
    summarize(write=True)
    print({'status':'frozen_ready','files':len(files),'baseline':3,'rounds':25,'max_new_task_executions':250,'new_api_calls':0})


if __name__=='__main__':main()
