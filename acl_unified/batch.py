"""Durable serial five-framework run; baseline and runtime locks are prerequisites."""
import fcntl
import os
import signal
import subprocess
import sys
import time

from acl_frameworks.common import ROOT,read
from acl_rsi.settings import write_json
from .protocol import WORK,FRAMEWORKS


def main():
    with (WORK/'batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            path=WORK/'baseline/status.json'
            baseline=read(path) if path.exists() else {'status':'pending'}
            if baseline['status']=='completed':break
            if baseline['status']=='stopped':
                write_json(WORK/'batch-status.json',{'status':'baseline_stopped','automatic_paid_retry':False})
                return
            alive=subprocess.run(['tmux','has-session','-t','acl-unified-h0'],capture_output=True).returncode==0
            if baseline['status']=='running' and not alive:
                write_json(WORK/'batch-status.json',{'status':'baseline_process_missing','automatic_paid_retry':False})
                return
            write_json(WORK/'batch-status.json',{'status':'waiting_fresh_baseline','updated_at':time.time()})
            time.sleep(15)
        if not (WORK/'optimizer-runtime-lock.json').exists():raise ValueError('Runtime not frozen')
        states={}
        for name in FRAMEWORKS:
            result=WORK/name/'result.json'
            if result.exists():
                states[name]=read(result)['status']
                if states[name]=='infrastructure_stopped':break
                continue
            states[name]='running'
            write_json(WORK/'batch-status.json',{'status':'running','frameworks':states,'updated_at':time.time()})
            (WORK/name).mkdir(exist_ok=True)
            with (WORK/name/'process.log').open('a') as log:
                proc=subprocess.Popen([sys.executable,'-m','acl_unified.framework',name],cwd=ROOT,
                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',LITELLM_LOCAL_MODEL_COST_MAP='True'),
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:code=proc.wait(timeout=read(WORK/'config.json')['protocol']['framework_wall_seconds'])
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    code=124
            states[name]=read(result)['status'] if result.exists() else 'process_failed'
            if code!=0:
                write_json(WORK/'batch-status.json',{'status':'stopped','frameworks':states,'exit_code':code,
                    'automatic_paid_retry':False,'updated_at':time.time()})
                break
        else:
            write_json(WORK/'batch-status.json',{'status':'completed','frameworks':states,'finished_at':time.time()})
        from .status import summarize
        summarize(write=True)


if __name__=='__main__':main()
