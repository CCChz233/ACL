"""Run the two bounded pilots serially, suitable for a durable tmux session."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from acl_rsi.settings import write_json
from .live import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--hf-candidate-version', type=int, default=1)
    args = parser.parse_args()
    work = args.work.resolve()
    prepare(work)
    states = {}
    for name in ('harnessfix', 'meta-harness'):
        states[name] = {'status': 'running', 'started_at': time.time()}
        write_json(work / 'batch-status.json', states)
        with (work / (name+'.log')).open('a') as log:
            command = [sys.executable, '-m', 'acl_frameworks.live', name, '--work', str(work)]
            if name == 'harnessfix':
                command += ['--candidate-version', str(args.hf_candidate_version)]
            proc = subprocess.Popen(command,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=5400)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                code = 124
        states[name].update(status='completed' if code == 0 else 'stopped',
                            exit_code=code, finished_at=time.time())
        write_json(work / 'batch-status.json', states)
    print(json.dumps(states, indent=2))


if __name__ == '__main__':
    main()
