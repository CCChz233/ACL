"""Retry only image transport; reuse every completed target execution."""
import asyncio
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import evaluate_terminal_round1

native=asyncio.create_subprocess_exec
work=ROOT/'work/terminal-round1'
loader=ROOT/'scripts/terminal_image_loader.py'
cfg=json.loads((ROOT/'configs/terminal-round1.json').read_text())
protocol={'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'loader_sha256':hashlib.sha256(loader.read_bytes()).hexdigest(),
          'transport_order':['existing verified image','public mirror','official registry via host curl HTTP/1.1 and OCI import'],
          'scope':'image downloads only; exact baseline image IDs; no extra paid retries or new candidates'}
path=work/'download-retry-protocol.json'
if path.exists() and json.loads(path.read_text())!=protocol:raise ValueError('Download protocol changed')
path.write_text(json.dumps(protocol,indent=2)+'\n')
archive=work/'image-transport-failure-attempt2'
if not archive.exists():
    archive.mkdir()
    for source,name in [(Path('/tmp/acl-terminal-round1-eval.log'),'evaluation.log'),
      (work/'summary.json','summary.json'),(work/'runs/terminal/history.jsonl','history.jsonl')]:
        if source.exists():shutil.copyfile(source,archive/name)

async def spawn(*args,**kwargs):
    process=await native(*args,**kwargs)
    if args[:2]!=('docker','pull'):return process
    class RecoveringPull:
        async def wait(self):
            code=await process.wait()
            with (work/'download-attempts.jsonl').open('a') as log:
                log.write(json.dumps({'image':args[-1],'transport':'mirror','returncode':code,'time':time.time()})+'\n')
            if code==0:return 0
            canonical=args[-1].removeprefix('docker.1ms.run/')
            task=next((t for t in cfg['tasks'] if t['image']==canonical),None)
            if task is None:return code
            command=[sys.executable,'-u',str(loader),task['id'],'--tag',args[-1]]
            dockerfile=(ROOT/'repos/terminal-bench-2-1/tasks'/task['id']/'environment/Dockerfile').read_text()
            for source,repo in [('FROM ubuntu:','library/ubuntu'),('FROM python:','library/python'),('FROM node:','library/node'),('FROM debian:','library/debian')]:
                if source in dockerfile:
                    command+=['--base-repo',repo];break
            recovery=await native(*command,**kwargs)
            result=await recovery.wait()
            with (work/'download-attempts.jsonl').open('a') as log:
                log.write(json.dumps({'image':args[-1],'transport':'host_curl_oci','returncode':result,'time':time.time()})+'\n')
            return result
    return RecoveringPull()

asyncio.create_subprocess_exec=spawn
if __name__=='__main__':evaluate_terminal_round1.main()
