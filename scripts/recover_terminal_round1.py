"""Bounded syntax-only repair of the original RRSI candidate; no strategy rewrite."""
import fcntl
import json
import re
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from acl_terminal_rsi.run import prepare,summarize,git
from acl_terminal_rsi.common import read,sha
from acl_terminal_rsi.search import bind
from acl_rsi.settings import write_json
import rrsi.loop


def main():
    cfg,run=prepare();work=Path(cfg['workspace'])
    with (work/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        archive=work/'syntax-failure-attempt1'
        if not archive.exists():
            rdir=run.runs/'r0'
            prep=read(rdir/'A/prep.json')
            if prep.get('gate_failure')!='smoke_fail': raise ValueError('Expected YAML smoke failure')
            archive.mkdir()
            shutil.copyfile(run.frontier_path,archive/'frontier.json')
            shutil.copyfile(run.history.path,archive/'history.jsonl')
            shutil.move(str(rdir),str(archive/'r0'))
            rdir.mkdir()
            shutil.copyfile(archive/'r0/analysis_report.json',rdir/'analysis_report.json')
            shutil.copytree(archive/'r0/analysis',rdir/'analysis')
            frontier=run.frontier();frontier['trajectory']=frontier['trajectory'][:1]
            run.save_frontier(frontier);run.history.replace_round(0)
            write_json(work/'syntax-recovery.json',{'reason':'YAML single-quote escaping failure; no target API calls made',
              'original_search_calls':37,'cumulative_search_call_cap':80,'cumulative_token_cap':1000000,
              'script_sha256':sha(__file__),'repair_scope':'quotation/whitespace only; preserve original semantic text',
              'original_diff_sha256':sha(archive/'r0/A/diff.patch')})
        elif read(work/'syntax-recovery.json')['script_sha256']!=sha(__file__):
            raise ValueError('Recovery code changed')
        original=read(archive/'r0/A/proposal.json')
        smoke=read(archive/'r0/A/smoke.json')
        native=rrsi.loop.propose
        applied=False
        def repair_only(domain,harness,*args,**kwargs):
            nonlocal applied
            if not applied:
                result=__import__('subprocess').run(['git','apply',str(archive/'r0/A/diff.patch')],cwd=Path(harness).parents[2],capture_output=True,text=True)
                if result.returncode:raise RuntimeError('Could not restore original candidate patch')
                applied=True
            path=Path(harness)/'terminal.yaml';before=path.read_text()
            kwargs['repair_brief']={'reasons':['The policy was accepted by critic, but YAML parsing failed: '+smoke['error'],
              'Repair ONLY YAML quoting syntax. YAML single-quoted scalars escape an embedded apostrophe by doubling it. Preserve all semantic words and rules; do not redesign the strategy.'],
              'your_declared_edits':original['edits']}
            result=native(domain,harness,*args,**kwargs)
            write_json(work/'syntax-repair-proposal.json',result)
            after=path.read_text()
            normalize=lambda s:re.sub(r"[\s']+",'',s)
            if normalize(before)!=normalize(after):raise ValueError('Repair changed semantic text rather than quoting')
            domain.smoke(Path(harness).parents[2],run.runs,'repair',[])
            result.update(edits=original['edits'],summary=original['summary'],mechanism=original['mechanism'],targets_mode=original['targets_mode'])
            return result
        rrsi.loop.propose=repair_only
        ledger=bind(cfg)
        write_json(work/'controller.json',{'status':'running_syntax_repair_then_evaluation'})
        if len(run.frontier()['trajectory'])<2:run.round(0)
        report=summarize(cfg,run,ledger)
        write_json(work/'controller.json',{'status':report['status']})
        print(json.dumps({k:v for k,v in report.items() if k not in ('paired_tasks','frontier')},indent=2))

if __name__=='__main__':main()
