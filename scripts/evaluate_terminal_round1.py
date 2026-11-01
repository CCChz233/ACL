"""Resume the locked RRSI candidate with digest-checked public mirror transport."""
import asyncio
import fcntl
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from acl_terminal_rsi.run import prepare,summarize
from acl_terminal_rsi.common import BASE_WORK,read,sha
from acl_rsi.settings import write_json


def main():
    cfg,run=prepare();work=Path(cfg['workspace']);evaluation=work/'candidate-eval'
    with (work/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        import acl_terminal.run as runner
        native_exec=asyncio.create_subprocess_exec;native_trial=runner.run_trial
        expected={t['image']:read(BASE_WORK/'image-pulls'/f'baseline-{t["id"]}.json')['Id'] for t in cfg['tasks']}
        protected=set(read(evaluation/'preexisting-images.json'))
        mirror='docker.1ms.run'
        archive=work/'image-transport-failure-attempt1'
        if not archive.exists():
            archive.mkdir()
            for source,name in [(run.frontier_path,'frontier.json'),(run.history.path,'history.jsonl'),
                                 (run.runs/'r0/decisions.json','decisions.json'),
                                 (evaluation/'image-pulls/baseline-make-mips-interpreter.log','pull.log')]:
                if source.exists():shutil.copyfile(source,archive/name)
        manifest={'script_sha256':sha(__file__),'candidate_commit':read(run.runs/'r0/A/prep.json')['commit'],
                  'reason':'configured registry mirror DNS failure and official CDN EOF; public mirror transport only',
                  'mirror':mirror,'required_image_ids':expected,'new_search_calls':0,
                  'policy':'verify baseline image IDs before target API; remove only new canonical/mirror tags'}
        manifest_path=work/'evaluation-recovery.json'
        if manifest_path.exists() and read(manifest_path)!=manifest:raise ValueError('Evaluation recovery protocol changed')
        write_json(manifest_path,manifest)
        class Immediate:
            returncode=0
            async def wait(self):return 0
        async def supply(*args,**kwargs):
            if len(args)<5 or args[:4]!=('docker','pull','--platform','linux/amd64') or args[4] not in expected:
                return await native_exec(*args,**kwargs)
            image=args[4];alias=mirror+'/'+image
            for candidate in (image,alias):
                r=runner.docker('image','inspect',candidate,check=False)
                if r.returncode==0 and json.loads(r.stdout)[0]['Id']==expected[image]:
                    if candidate!=image:runner.docker('tag',candidate,image)
                    kwargs['stdout'].write(f'Using locally available image verified against baseline: {expected[image]}\n')
                    kwargs['stdout'].flush()
                    return Immediate()
            process=await native_exec('docker','pull','--platform','linux/amd64',alias,**kwargs)
            class PullAndTag:
                async def wait(self):
                    code=await process.wait()
                    if code:return code
                    info=json.loads(runner.docker('image','inspect',alias).stdout)[0]
                    if info['Id']!=expected[image]:raise ValueError('Mirror image differs from frozen baseline')
                    runner.docker('tag',alias,image)
                    return 0
            return PullAndTag()
        async def trial(*args,**kwargs):
            task_id=args[0];image=next(t['image'] for t in cfg['tasks'] if t['id']==task_id)
            try:return await native_trial(*args,**kwargs)
            finally:
                records=[]
                for name in (image,mirror+'/'+image,'registry-1.docker.io/'+image):
                    r=runner.docker('image','inspect',name,check=False)
                    if r.returncode==0:
                        info=json.loads(r.stdout)[0]
                        if info['Id'] not in protected:
                            removal=runner.docker('image','rm',name,check=False)
                            records.append({'tag':name,'id':info['Id'],'returncode':removal.returncode})
                write_json(evaluation/'image-pulls'/f'{task_id}-transport-cleanup.json',records)
        asyncio.create_subprocess_exec=supply;runner.run_trial=trial
        write_json(work/'controller.json',{'status':'evaluating_locked_candidate','candidate':manifest['candidate_commit']})
        try:
            run.reevaluate(0,['A'])
            report=summarize(cfg,run)
            write_json(work/'controller.json',{'status':report['status']})
            print(json.dumps({k:v for k,v in report.items() if k not in ('paired_tasks','frontier')},indent=2))
        finally:
            asyncio.create_subprocess_exec=native_exec;runner.run_trial=native_trial
            write_json(evaluation/'transport-cleanup-audit.json',{'missing_preexisting':sorted(protected-set(runner.inventory()))})

if __name__=='__main__':main()
