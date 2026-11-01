"""Fill and verify the persistent, pinned SWE-bench Verified Mini50 image cache."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'configs/swe-mini-image-cache.json'
WORK = ROOT / 'work/swe-mini-image-cache'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def inspect(client, item):
    import docker
    try:
        image = client.images.get(item['image'])
    except docker.errors.ImageNotFound:
        return None
    if image.id != item['expected_id'] or image.attrs.get('Architecture') != 'amd64':
        raise RuntimeError(f"Pinned image mismatch: {item['instance_id']}")
    return image


def fill(client, policy, *, pull=False):
    rows = []
    report = {'status': 'running', 'started_at': time.time(), 'total': len(policy['images']),
              'policy_sha256': hashlib.sha256(POLICY.read_bytes()).hexdigest(),
              'retain_after_use': True, 'model_calls': 0, 'tasks': rows}
    def save(status='running'):
        report.update(status=status, checked=len(rows), cached=sum(r['state'] == 'cached' for r in rows),
                      downloaded=sum(r.get('downloaded', False) for r in rows),
                      free_bytes=shutil.disk_usage(ROOT).free, updated_at=time.time())
        write_json(WORK / 'status.json', report)
    save()
    try:
        for item in policy['images']:
            image = inspect(client, item)
            downloaded = False
            if image is None and pull:
                if shutil.disk_usage(ROOT).free < policy['min_free_bytes']:
                    raise RuntimeError('disk_space_guard_below_4GiB; existing cache retained')
                print(f"[mini-cache] pulling {item['instance_id']}", flush=True)
                image = client.images.pull(item['pinned_reference'], platform='linux/amd64')
                if image.id != item['expected_id'] or image.attrs.get('Architecture') != 'amd64':
                    raise RuntimeError(f"Downloaded image identity mismatch: {item['instance_id']}")
                repository, tag = item['image'].rsplit(':', 1)
                image.tag(repository, tag=tag)
                image = inspect(client, item)
                downloaded = True
            rows.append({'instance_id': item['instance_id'], 'image': item['image'],
                         'expected_id': item['expected_id'], 'state': 'cached' if image else 'missing',
                         'downloaded': downloaded, 'id': image.id if image else None})
            save()
            print(f"[mini-cache] checked={len(rows)}/{report['total']} cached={report['cached']} newly_downloaded={report['downloaded']}", flush=True)
        save('completed' if all(r['state'] == 'cached' for r in rows) else 'missing_images')
        return report
    except BaseException as exc:
        report['error_type'] = type(exc).__name__
        report['error'] = str(exc)
        save('interrupted_cache_retained')
        raise


def main():
    import docker
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('fill', 'status'))
    args = parser.parse_args()
    policy = json.loads(POLICY.read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / 'cache.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        client = docker.from_env(timeout=900)
        try:
            client.ping()
            report = fill(client, policy, pull=args.command == 'fill')
            print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}, indent=2))
        finally:
            client.close()


if __name__ == '__main__':
    main()
