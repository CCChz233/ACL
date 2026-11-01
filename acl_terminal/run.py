import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial
from acl_rsi.settings import ROOT, write_json

CONFIG = ROOT / 'configs/terminal-pilot-v1.json'


def docker(*args, check=True):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check)


def inventory():
    return sorted(set(docker('image', 'ls', '-q', '--no-trunc').stdout.split()))


def freeze(cfg, workspace):
    files = [CONFIG, ROOT / 'configs/terminal-pilot-requirements.lock.txt',
             ROOT / 'repos/mini-swe-agent/src/minisweagent/agents/default.py',
             ROOT / 'acl_rsi/deepseek.py', ROOT / 'acl_rsi/model.py',
             *sorted((ROOT / 'acl_terminal').glob('*.py'))]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    path = workspace / 'runtime-lock.json'
    if path.exists():
        if json.loads(path.read_text()) != hashes:
            raise RuntimeError('Frozen runtime differs; do not resume')
    else:
        write_json(path, hashes)
    for row in cfg['tasks']:
        for name, digest in row['files'].items():
            path = ROOT / 'repos/terminal-bench-2-1/tasks' / row['id'] / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f'Task file changed: {path}')


def summarize(workspace, tasks):
    rows = []
    for item in tasks:
        path = workspace / 'trials' / item['id'] / 'result.json'
        if not path.exists():
            continue
        result = json.loads(path.read_text())
        worker = workspace / 'trials' / item['id'] / 'agent' / 'worker.json'
        detail = json.loads(worker.read_text()) if worker.exists() else {}
        reward = (result.get('verifier_result') or {}).get('rewards')
        rows.append({'id': item['id'], 'category': item['category'], 'reward': reward,
                     'worker': detail, 'exception': result.get('exception_info')})
    summary = {'completed': len(rows), 'planned': len(tasks), 'results': rows,
               'passed': sum((row['reward'] or {}).get('reward') == 1 for row in rows),
               'calls': sum(row['worker'].get('usage', {}).get('calls', 0) for row in rows),
               'tokens': sum(row['worker'].get('usage', {}).get('actual_tokens', 0) for row in rows)}
    write_json(workspace / 'summary.json', summary)
    return summary


async def run_trial(task_id, mode, cfg, workspace):
    path = workspace / 'trials' / (task_id if mode == 'baseline' else mode + '-' + task_id)
    if (path / 'result.json').exists():
        return json.loads((path / 'result.json').read_text())
    if path.exists():
        raise RuntimeError(f'Incomplete trial exists; manual recovery required: {path}')
    meta = __import__('tomllib').loads((ROOT / 'repos/terminal-bench-2-1/tasks' / task_id / 'task.toml').read_text())
    image = meta['environment']['docker_image']
    before = set(inventory())
    if shutil.disk_usage(ROOT).free < cfg['min_free_bytes']:
        raise RuntimeError('Disk below 4 GiB; stopped')
    pull_log = workspace / 'image-pulls'
    pull_log.mkdir(exist_ok=True)
    with (pull_log / f'{mode}-{task_id}.log').open('w') as log:
        process = await asyncio.create_subprocess_exec('docker', 'pull', '--platform', 'linux/amd64', image,
                    stdout=log, stderr=asyncio.subprocess.STDOUT)
        if await process.wait():
            raise RuntimeError(f'Image pull failed: {image}')
    resolved = json.loads(docker('image', 'inspect', image).stdout)[0]
    write_json(pull_log / f'{mode}-{task_id}.json', {k: resolved.get(k) for k in
               ('Id', 'RepoTags', 'RepoDigests', 'Architecture', 'Os', 'Size')})
    if shutil.disk_usage(ROOT).free < cfg['min_free_bytes']:
        if resolved['Id'] not in before:
            docker('image', 'rm', image, check=False)
        raise RuntimeError('Disk below 4 GiB after pull; stopped')
    overlay = workspace / 'platform.yaml'
    overlay.write_text('services:\n  main:\n    platform: linux/amd64\n')
    wall = min(int(meta['agent']['timeout_sec']), 1200)
    agent = {'name': 'oracle'} if mode == 'oracle' else {
        'import_path': 'acl_terminal.agent:NoopAgent' if mode == 'noop' else 'acl_terminal.agent:PilotAgent',
        'model_name': 'deepseek-flash' if mode == 'baseline' else None,
        'override_timeout_sec': wall + 180,
        'kwargs': {'pilot_config': str(CONFIG), 'wall_seconds': wall} if mode == 'baseline' else {}}
    trial_cfg = TrialConfig.model_validate({'task': {'path': str(ROOT / 'repos/terminal-bench-2-1/tasks' / task_id)},
        'trials_dir': str(path.parent), 'trial_name': path.name, 'agent': agent,
        'environment': {'type': 'docker', 'delete': True, 'extra_docker_compose': [str(overlay)]},
        'verifier': {'override_timeout_sec': 900}})
    try:
        trial = await Trial.create(trial_cfg)
        result = (await trial.run()).model_dump(mode='json')
    finally:
        # Only remove the named task tag if its image ID did not exist before this task.
        # Never prune shared layers, other images, or force-remove anything.
        if resolved['Id'] not in before:
            cleaned = docker('image', 'rm', image, check=False)
            write_json(pull_log / f'{mode}-{task_id}-cleanup.json',
                       {'image': image, 'id': resolved['Id'], 'returncode': cleaned.returncode,
                        'stdout': cleaned.stdout, 'stderr': cleaned.stderr})
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['controls', 'baseline', 'summary'])
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text())
    workspace = ROOT / cfg['workspace']
    workspace.mkdir(parents=True, exist_ok=True)
    if args.mode == 'summary':
        print(json.dumps(summarize(workspace, cfg['tasks']), indent=2))
        return
    freeze(cfg, workspace)
    if not (workspace / 'preexisting-images.json').exists():
        write_json(workspace / 'preexisting-images.json', inventory())
        (workspace / 'requirements.lock.txt').write_text(
            (ROOT / 'configs/terminal-pilot-requirements.lock.txt').read_text())
    if args.mode == 'controls':
        controls = {}
        for mode in ['oracle', 'noop']:
            print(f'{datetime.now(timezone.utc).isoformat()} CONTROL {mode}', flush=True)
            result = await run_trial('extract-elf', mode, cfg, workspace)
            controls[mode] = {'reward': (result.get('verifier_result') or {}).get('rewards'),
                              'exception': result.get('exception_info')}
        write_json(workspace / 'controls.json', controls)
        print(json.dumps(controls, indent=2), flush=True)
        if controls['oracle']['reward'] != {'reward': 1.0} or controls['noop']['reward'] != {'reward': 0.0}:
            raise RuntimeError('Grading controls failed')
        return
    controls = json.loads((workspace / 'controls.json').read_text())
    if controls['oracle']['reward'] != {'reward': 1.0} or controls['noop']['reward'] != {'reward': 0.0}:
        raise RuntimeError('Grading controls failed')
    for row in cfg['tasks']:
        print(f'{datetime.now(timezone.utc).isoformat()} START {row["id"]}', flush=True)
        result = await run_trial(row['id'], 'baseline', cfg, workspace)
        summary = summarize(workspace, cfg['tasks'])
        print(json.dumps({'done': row['id'], 'reward': (result.get('verifier_result') or {}).get('rewards'),
                          'exception': (result.get('exception_info') or {}).get('exception_type'),
                          'completed': summary['completed'], 'passed': summary['passed'],
                          'calls': summary['calls'], 'tokens': summary['tokens']}), flush=True)
    protected = set(json.loads((workspace / 'preexisting-images.json').read_text()))
    write_json(workspace / 'cleanup-audit.json', {'preexisting_count': len(protected),
        'missing_preexisting': sorted(protected - set(inventory())), 'free_bytes': shutil.disk_usage(ROOT).free})

if __name__ == '__main__':
    asyncio.run(main())
