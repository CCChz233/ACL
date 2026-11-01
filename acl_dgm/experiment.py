"""Durable one-generation DGM experiment and read-only progress accounting."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

from acl_frameworks.common import ROOT, read, sha
from acl_gepa_swe.feedback import record
from acl_rsi.settings import write_json


def usage(path):
    rows = read(path)['requests'] if path.exists() else []
    return {'calls': len(rows), 'completed': sum(r['status'] == 'completed' for r in rows),
        'actual_tokens': sum(r.get('usage', {}).get('total_tokens', 0) for r in rows),
        'unknown_usage_requests': sum('usage' not in r for r in rows),
        'charged_or_reserved_tokens': sum(r['charged_tokens'] for r in rows)}


def snapshot(work):
    cfg = read(work / 'config.json')
    selection = read(ROOT / cfg['protocol']['selection_file'])
    assert sha(ROOT / cfg['protocol']['selection_file']) == cfg['protocol']['selection_sha256']
    assert selection['task_ids'] == cfg['evolve_ids']
    instances = {r['instance_id']: r for r in read(ROOT / cfg['dataset'])}
    baseline = {r['task_id']: r['scores'][0] for r in selection['selected']}
    trials, pending = [], []
    for iid in cfg['evolve_ids']:
        path = work / 'evaluations/node_0000/trials' / iid
        row = {'task_id': iid, 'baseline_score': baseline[iid], 'usage': usage(path / 'usage.json')}
        if (path / 'worker.json').exists() and (path / 'grade.json').exists():
            validated = record(path, iid, instances[iid], trace=False)
            row.update({k: v for k, v in validated.items() if k != 'usage'})
        else:
            pending.append(iid)
        trials.append(row)
    scored = [r for r in trials if 'score' in r]
    target_usage = {k: sum(r['usage'][k] for r in trials) for k in
        ('calls', 'completed', 'actual_tokens', 'unknown_usage_requests', 'charged_or_reserved_tokens')}
    return {'scope': 'historically selected hard development tasks; not heldout or Mini50 estimate',
        'baseline_reused': True, 'baseline_resolved': sum(baseline.values()), 'total_tasks': len(trials),
        'graded': len(scored), 'candidate_resolved_so_far': sum(int(r['score']) for r in scored),
        'newly_resolved': [r['task_id'] for r in scored if r['score'] == 1 and not r['baseline_score']],
        'regressions': [r['task_id'] for r in scored if r['score'] == 0 and r['baseline_score']],
        'pending': pending, 'trials': trials, 'optimizer_usage': usage(work / 'optimizer-api/usage.json'),
        'target_usage': target_usage, 'model': cfg['model'], 'generations': 1, 'candidate_count': 1,
        'native_archive_policy': 'keep_all; archive admission does not establish improvement',
        'updated_at': time.time()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'status'])
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    if args.command == 'status':
        print(json.dumps(snapshot(work), ensure_ascii=False, indent=2))
        return
    if not args.config or (work / 'status.json').exists():
        raise ValueError('Need explicit config and a fresh experiment; never automatically retry paid work')
    work.mkdir(parents=True, exist_ok=True)
    cfg = read(args.config)
    if cfg['evolve_ids'] != read(ROOT / cfg['protocol']['selection_file'])['task_ids']:
        raise ValueError('Cohort differs from frozen selection')
    import docker
    from scripts.run_swe_local import require_cache
    client = docker.from_env(timeout=60)
    try:
        require_cache(client, read(ROOT / 'configs/swe-mini-image-cache.json'))
        if shutil.disk_usage(ROOT).free < cfg['image_cache']['min_free_bytes']:
            raise RuntimeError('Disk guard: preserve images and stop')
    finally:
        client.close()
    shutil.copytree(ROOT / 'acl_dgm', work / 'runtime-snapshot/acl_dgm',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(args.config, work / 'input-config.json')
    started = time.time()
    write_json(work / 'status.json', {'status': 'running', 'started_at': started})
    from .cli import main as run
    old = sys.argv
    sys.argv = ['dgm', 'run', '--live', '--work', str(work), '--config', str(args.config.resolve())]
    try:
        run()
        result = snapshot(work)
        result['status'] = 'completed' if result['graded'] == result['total_tasks'] else 'candidate_not_fully_evaluated'
        write_json(work / 'result.json', result)
        write_json(work / 'status.json', {'status': result['status'], 'started_at': started, 'finished_at': time.time()})
    except BaseException as error:
        write_json(work / 'status.json', {'status': 'stopped', 'error_type': type(error).__name__,
            'started_at': started, 'finished_at': time.time(), 'automatic_paid_retry': False})
        raise
    finally:
        sys.argv = old


if __name__ == '__main__':
    main()
