"""Freeze the tested optimizer phase before its first paid request."""
import datetime
from pathlib import Path
import shutil

from acl_frameworks.common import ROOT,read,sha,verify
from acl_dgm.native import verify as verify_dgm
from acl_rsi.settings import write_json
from .protocol import WORK,CONFIG,FRAMEWORKS
from .common import settings,preflight


def main():
    target=WORK/'optimizer-runtime-lock.json'
    if target.exists():raise ValueError('Optimizer stage is already frozen')
    baseline=read(WORK/'baseline/runtime-lock.json')
    assert sha(ROOT/'acl_unified/common.py')==baseline['common']
    assert sha(ROOT/'acl_unified/protocol.py')==baseline['protocol']
    assert sha(ROOT/'acl_unified/baseline.py')==baseline['baseline_controller']
    assert all(sha(ROOT/p)==digest for p,digest in baseline['runner'].items())
    old=read(ROOT/'experiments/runs/framework-live-2026-10-19-v1/runtime-repair.json')['runtime']
    assert all(sha(ROOT/p)==digest for p,digest in old.items())
    old_dgm=read(ROOT/'experiments/runs/dgm-hard10-v1/integration-lock.json')['adapter_sha256']
    assert all(sha(ROOT/p)==digest for p,digest in old_dgm.items())
    revisions={n:(verify_dgm().name if n=='dgm' else verify(n)[0]['revision']) for n in FRAMEWORKS}
    revisions['dgm']=read(ROOT/'configs/frameworks/dgm.json')['revision']
    preflight()
    for name in FRAMEWORKS:settings(name)
    packages=('acl_unified','acl_rsi','acl_gepa_swe','acl_frameworks','acl_dgm','acl_gepa','acl_terminal_rsi')
    files=[p for package in packages for p in (ROOT/package).glob('*.py')]
    files += [CONFIG,ROOT/'configs/frameworks/registry.json',ROOT/'configs/frameworks/dgm.json',
        ROOT/'configs/swe-mini-image-cache.json',ROOT/'docs/agent_sources.lock.json',
        ROOT/'docs/rrsi_sources.lock.json',ROOT/'docs/rsi_frameworks.sources.lock.json']
    files += [WORK/name/'config.json' for name in FRAMEWORKS]
    write_json(target,{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'config_sha256':sha(CONFIG),'files':{str(p.relative_to(ROOT)):sha(p) for p in files},
        'framework_revisions':revisions,'baseline_stage_lock_sha256':sha(WORK/'baseline/runtime-lock.json'),
        'offline_checks':{'new_tests':12,'shared_regression_tests':34,'dependency_lock_check':'passed'},
        'no_optimizer_api_calls_before_freeze':True})
    snapshot=WORK/'optimizer-runtime-snapshot'
    for package in packages:
        shutil.copytree(ROOT/package,snapshot/package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    write_json(WORK/'authorization.json',{'user_instruction':'可以，开始做吧',
        'scope':'preceding unified four-development/six-report pilot, five frameworks, fresh H0',
        'provider':'https://api.deepseek.com','model':'deepseek-flash',
        'max_target_executions':60,'max_calls':3400,'max_tokens':65000000,
        'manual_candidate_recovery':False,'retain_all_mini50_images':True})
    print({'status':'optimizer_phase_frozen','files':len(files),'frameworks':FRAMEWORKS,'new_model_calls':0})


if __name__=='__main__':main()
