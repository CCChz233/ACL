import argparse
import fcntl
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from acl_rsi.settings import ROOT, write_json
from .common import BASE_CONFIG,BASE_WORK,CONFIG,read,sha,verify_baseline,harness_config,load_cfg

# Keep the original pilot environment unchanged; import the pinned official checkout.
sys.path.insert(0,str(ROOT/'repos/rrsi'))
from rrsi.config import RRSIConfig
from rrsi.loop import Run
from .domain import TerminalDomain


def git(repo,*args):
    r=subprocess.run(['git','-c','user.name=ACL RSI','-c','user.email=acl-rsi@localhost',*args],cwd=repo,capture_output=True,text=True,check=True)
    return r.stdout.strip()


def prepare():
    base=verify_baseline()
    cfg={**base,'purpose':'terminal-pilot-one-rrsi-round-same12',
      'workspace':'work/terminal-round1','baseline_workspace':str(BASE_WORK),
      'search':{'max_calls':80,'max_tokens':1000000,'max_output_tokens':4096},
      'rrsi':{'T':1,'k':1,'m':1,'b_min':1,'b_max':1,'delta':0.0,'w_s':100.0,'w_c':0.0,'w_n':0.0,
              'm_draft':0,'repair_rounds':1,'n_fail_traces':5,'n_success_traces':3,'invalid_missing_frac':0.0,'eval_parallel':1},
      'search_adapter':{'analyst_dispatches':1,'digester_calls_per_trace':3,'digest_parallelism':1,
                        'analyst_max_turns':4,'digester_max_turns':4,'proposer_max_turns':28},
      'edit_space':'generic prompts and observation/format-error templates only',
      'assessment':'development same-task comparison; no heldout/generalization claim'}
    if CONFIG.exists() and read(CONFIG)!=cfg: raise ValueError('Frozen round config changed')
    if not CONFIG.exists(): write_json(CONFIG,cfg)
    cfg=load_cfg(); work=Path(cfg['workspace']);work.mkdir(parents=True,exist_ok=True)
    rrsi_lock=read(ROOT/'docs/rrsi_sources.lock.json')
    if git(ROOT/'repos/rrsi','rev-parse','HEAD')!=rrsi_lock['revision'] or git(ROOT/'repos/rrsi','diff','--name-only'):
        raise ValueError('Pinned RRSI checkout changed')
    repo=work/'repo'; manifest={'config_sha256':sha(CONFIG),'baseline_config_sha256':sha(BASE_CONFIG),
       'rrsi_revision':rrsi_lock['revision'],
       'adapter_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'acl_terminal_rsi').glob('*.py'))},
       'baseline_runtime_lock_sha256':sha(BASE_WORK/'runtime-lock.json'),
       'baseline_evidence':{t['id']:{n:sha(BASE_WORK/'trials'/t['id']/n) for n in
          ('result.json','agent/worker.json','agent/trajectory.json','agent/usage.json')} for t in cfg['tasks']}}
    manifest_path=work/'round-lock.json'
    if manifest_path.exists() and read(manifest_path)!=manifest: raise ValueError('Round runtime/evidence changed')
    if not manifest_path.exists(): write_json(manifest_path,manifest)
    if not (repo/'.git').exists():
        repo.mkdir(parents=True);git(repo,'init','-b','codex/seed')
        domain_dir=repo/'domains/terminal';harness=domain_dir/'harness';harness.mkdir(parents=True)
        import yaml
        (harness/'terminal.yaml').write_text(yaml.safe_dump(harness_config(base),sort_keys=False,allow_unicode=True))
        (domain_dir/'SKILL.md').write_text('Improve only reusable terminal.yaml prompts and templates. Preserve the mini loop, public task and completion marker. No task IDs, special-case paths, answers, verifier access, extra files, budget changes or model changes. Use only supplied public agent traces and binary scores.\n')
        (domain_dir/'PATTERNS.md').write_text('Choose one defensible generic mechanism based on trace evidence. Preserve successful behavior. External budgets are immutable and count every API call. No private verifier contents are available.\n')
        (repo/'.gitignore').write_text('__pycache__/\n*.pyc\n')
        git(repo,'add','.');git(repo,'commit','-m','Seed original terminal mini prompts for one RRSI round')
    domain=TerminalDomain(cfg);domain.root=repo/'domains/terminal'
    run=Run(domain,RRSIConfig(**cfg['rrsi'],proposer_model=cfg['model'],analyst_model=cfg['model'],critic_model=cfg['model']),repo,work/'runs')
    return cfg,run


def summarize(cfg,run,ledger=None):
    work=Path(cfg['workspace']);domain=run.domain
    pairs=[]
    for task in cfg['tasks']:
        i=task['id'];b=domain.load_trial(run.runs,'base',i,0)
        c=domain.load_trial(run.runs,'r0A',i,0)
        pairs.append({'task_id':i,'category':task['category'],'baseline':b['score'],
          'candidate':c['score'] if c else None,'stop':c['worker']['exit_status'] if c else None,
          'usage':c['worker']['usage'] if c else None})
    complete=all(p['candidate'] is not None for p in pairs)
    passed=sum(p['candidate']==1 for p in pairs)
    usage_path=work/'search_usage.json'
    search_rows=read(usage_path)['requests'] if usage_path.exists() else []
    report={'status':'completed' if complete else 'candidate_not_fully_evaluated',
      'baseline_passed':7,'candidate_passed':passed if complete else None,'total':12,
      'baseline_score':7/12,'candidate_score':passed/12 if complete else None,
      'delta_percentage_points':(passed-7)/12*100 if complete else None,
      'new_passes':[p['task_id'] for p in pairs if p['baseline']==0 and p['candidate']==1],
      'regressions':[p['task_id'] for p in pairs if p['baseline']==1 and p['candidate']==0],
      'candidate_calls':sum((p['usage'] or {}).get('calls',0) for p in pairs),
      'candidate_tokens':sum((p['usage'] or {}).get('actual_tokens',0) for p in pairs),
      'search_calls':len(search_rows),'search_tokens':sum(r.get('usage',{}).get('total_tokens',0) for r in search_rows),
      'search_calls_by_role':{role:sum(r['role']==role for r in search_rows) for role in ('analyst','digester','propose','critic')},
      'paired_tasks':pairs,'frontier':run.frontier() if run.frontier_path.exists() else None,
      'scope':'same 12 development tasks, one round, one candidate; not heldout evidence'}
    write_json(work/'summary.json',report)
    return report


def main():
    logging.getLogger('httpx').setLevel(logging.WARNING)
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','summary']);args=p.parse_args()
    cfg,run=prepare();work=Path(cfg['workspace'])
    if args.command=='prepare':
        ok,details=run.domain.smoke(run.repo,run.runs,'smoke',[])
        if not ok: raise RuntimeError(details)
        if not run.frontier_path.exists(): run.baseline()
        print(json.dumps({'prepared':str(work),'baseline':run.frontier()['incumbent']['S'],'new_api_calls':0}));return
    if args.command=='summary':
        print(json.dumps(summarize(cfg,run),indent=2));return
    with (work/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not run.frontier_path.exists(): run.baseline()
        from .search import bind
        ledger=bind(cfg)
        try:
            write_json(work/'controller.json',{'status':'running'})
            if len(run.frontier()['trajectory'])<2: run.round(0)
            report=summarize(cfg,run,ledger)
            write_json(work/'controller.json',{'status':report['status']})
            print(json.dumps({k:v for k,v in report.items() if k not in ('paired_tasks','frontier')},indent=2))
        except BaseException as exc:
            write_json(work/'controller.json',{'status':'interrupted','error_type':type(exc).__name__,'search_usage':ledger.summary()})
            raise

if __name__=='__main__':main()
