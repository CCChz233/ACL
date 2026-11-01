"""Run existing frozen SWE entry points with a verified, retained local Mini50 cache."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUNNERS = {'baseline': 'acl_rsi.mini50', 'rrsi': 'acl_rsi.mini50_round',
           'rrsi-recovery': 'acl_rsi.resume_mini50_round', 'gepa': 'acl_gepa_swe.run',
           'single': 'acl_rsi.cli'}


def require_cache(client, policy):
    import docker
    missing = []
    for item in policy['images']:
        try:
            image = client.images.get(item['image'])
        except docker.errors.ImageNotFound:
            missing.append(item['instance_id'])
            continue
        if image.id != item['expected_id']:
            raise RuntimeError(f"Wrong pinned image: {item['instance_id']}")
    if missing:
        raise RuntimeError('Local Mini50 cache is incomplete; run scripts/cache_swe_mini_images.py fill first. '
                           + 'Missing: ' + ', '.join(missing))


def retain_mini_images(policy):
    from acl_rsi.mini50 import StreamingDomain
    original = StreamingDomain.release
    tags = {i['image'] for i in policy['images']}
    ids = {i['expected_id'] for i in policy['images']}

    def release(client, name, owned, protected, cache_file):
        if name in tags or owned.get(name) in ids:
            # Keep the official tag and layers after both successful and failed
            # evaluations. Container cleanup is unaffected.
            print(f'[mini-cache] retained local task image {name}', flush=True)
            return
        return original(client, name, owned, protected, cache_file)

    StreamingDomain.release = staticmethod(release)


def main():
    import docker
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runner', choices=RUNNERS)
    args, forwarded = parser.parse_known_args()
    path = ROOT / 'configs/swe-mini-image-cache.json'
    policy = json.loads(path.read_text())
    client = docker.from_env(timeout=60)
    try:
        require_cache(client, policy)
    finally:
        client.close()
    retain_mini_images(policy)
    audit = ROOT / 'work/swe-mini-image-cache/runner-history' / (uuid.uuid4().hex + '.json')
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps({'started_at': time.time(), 'module': RUNNERS[args.runner],
        'policy_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'local_cache_verified': 50, 'retain_images': True,
        'frozen_experiment_files_modified': False}, indent=2) + '\n')
    sys.argv = [RUNNERS[args.runner], *forwarded]
    # Reuse the imported baseline module so its patched cleaner is not replaced
    # by a second class definition under __main__.
    importlib.import_module(RUNNERS[args.runner]).main()


if __name__ == '__main__':
    main()
