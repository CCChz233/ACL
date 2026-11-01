"""Round-major serial queue; no duplicated paid attempts on restart."""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from acl_frameworks.common import ROOT,read
from acl_rsi.settings import write_json
from .protocol import WORK,FRAMEWORKS,round_dir,verify
from .status import summarize


def main():
    verify()
    with (WORK/'batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        blocked={}
        for index in range(1,6):
            for name in FRAMEWORKS:
                if name in blocked:continue
                folder=round_dir(name,index);result=folder/'result.json'
                if result.exists():
                    if not read(result).get('next_parent'):blocked[name]=f'round-{index} failed'
                    continue
                if (folder/'started.json').exists():
                    blocked[name]=f'round-{index} interrupted; explicit recovery required'
                    continue
                verify()
                write_json(WORK/'batch-status.json',{'status':'running','framework':name,'round':index,
                    'blocked_lineages':blocked,'updated_at':time.time()})
                summarize(write=True)
                with (folder/'process.log').open('a') as log:
                    proc=subprocess.Popen([sys.executable,'-m','acl_multiround.step',name,str(index)],cwd=ROOT,
                        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',LITELLM_LOCAL_MODEL_COST_MAP='True'),
                        stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    try:
                        deadline=time.monotonic()+30000
                        while True:
                            try:
                                code=proc.wait(timeout=min(30,max(0,deadline-time.monotonic())))
                                break
                            except subprocess.TimeoutExpired:
                                if time.monotonic()>=deadline:raise
                                try:summarize(write=True)
                                except (json.JSONDecodeError,OSError):pass  # Concurrent ledger flush; retry next refresh.
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid,signal.SIGTERM)
                        try:proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                        code=124
                if code or not result.exists() or not read(result).get('next_parent'):
                    blocked[name]=f'round-{index} stopped, exit={code}'
                summarize(write=True)
        write_json(WORK/'batch-status.json',{'status':'completed' if not blocked else 'finished_with_blocked_lineages',
            'blocked_lineages':blocked,'finished_at':time.time(),'automatic_paid_retry':False})
        summarize(write=True)


if __name__=='__main__':main()
