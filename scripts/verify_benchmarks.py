#!/usr/bin/env python3
"""Offline checks of portable benchmark metadata and optional local artifacts."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    'swe-bench-pro-v2': 'SWE-bench-Pro-V2',
    'terminal-bench-4.0.0': 'Terminal-Bench-4.0.0',
    'terminal-bench-2.1': 'Terminal-Bench-2.1',
    'swe-bench-verified': 'SWE-bench-Verified',
    'swe-bench-verified-mini': 'SWE-bench-Verified-Mini',
}


def safe_path(parent, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'Unsafe relative path: {relative}')
    return parent / path


def digest(path, algorithm='sha256', prefix=b''):
    h = hashlib.new(algorithm)
    h.update(prefix)
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_lock():
    lock = json.loads((ROOT / 'benchmarks/sources.lock.json').read_text())
    assert lock['schema_version'] == 1
    assert set(x['id'] for x in lock['benchmarks']) == set(LABELS)
    return lock['benchmarks']


def verify_download(item):
    directory = safe_path(ROOT, item['local_dir'])
    assert directory.is_dir(), f'Missing download: {directory}'
    if item['kind'] == 'github_archive':
        configs = list(safe_path(directory, item['tasks_dir']).glob('*/task.toml'))
        assert len(configs) == item['task_count'], (item['id'], len(configs))
        for config in configs:
            for required in ['instruction.md', 'environment/Dockerfile', 'tests/test.sh', 'solution/solve.sh']:
                assert (config.parent / required).is_file(), (config.parent.name, required)
        if item.get('official_checksums'):
            manifest = safe_path(directory, item['official_checksums'])
            for line in manifest.read_text().splitlines():
                expected, relative = line.split(None, 1)
                target = safe_path(manifest.parent, relative.lstrip('*'))
                assert digest(target) == expected, f'Official checksum mismatch: {relative}'
        tree = ROOT / '.cache/benchmark_sources' / (item['id'] + '-tree.json')
        if tree.is_file():
            verify_tree(directory, json.loads(tree.read_text()), item['revision'])
    else:
        for file in item['files']:
            target = safe_path(directory, file['path'])
            assert target.is_file(), target
            assert target.stat().st_size == file['bytes'], target
            assert digest(target) == file['sha256'], f'Data SHA256 mismatch: {target.name}'


def verify_tree(directory, tree, revision):
    import os
    assert tree['sha'] == revision and not tree.get('truncated')
    for item in tree['tree']:
        if item['type'] != 'blob':
            continue
        path = safe_path(directory, item['path'])
        assert path.is_file() or path.is_symlink(), f'Missing source: {item["path"]}'
        if path.is_symlink():
            payload = os.readlink(path).encode()
            actual = hashlib.sha1(f'blob {len(payload)}\0'.encode() + payload).hexdigest()
        else:
            actual = digest(path, 'sha1', f'blob {path.stat().st_size}\0'.encode())
        assert actual == item['sha'], f'Git blob mismatch: {item["path"]}'
        if path.is_file() and path.stat().st_size < 1024:
            assert not path.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1\n'), \
                f'LFS artifact not materialized: {item["path"]}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-downloads', action='store_true')
    args = parser.parse_args()
    with (ROOT / 'benchmarks/all_benchmark_tasks.csv').open() as f:
        all_rows = list(csv.DictReader(f))
    assert len(all_rows) == 1347
    assert len({(x['benchmark'], x['task_id']) for x in all_rows}) == len(all_rows)
    grouped = {}
    for item in load_lock():
        assert re.fullmatch('[0-9a-f]{40}', item['revision']), item['id']
        safe_path(ROOT, item['local_dir'])
        with safe_path(ROOT / 'benchmarks', item['catalog']).open() as f:
            rows = list(csv.DictReader(f))
        ids = {x.get('task_id') or x['instance_id'] for x in rows}
        assert len(rows) == len(ids) == item['task_count'], item['id']
        assert ids == {x['task_id'] for x in all_rows if x['benchmark'] == LABELS[item['id']]}
        grouped[item['id']] = ids
        if args.check_downloads:
            verify_download(item)
        print(f'{item["id"]}: {len(ids)} catalog entries verified' + ('; local files verified' if args.check_downloads else ''))
    full = grouped['swe-bench-verified']
    mini = grouped['swe-bench-verified-mini']
    assert mini <= full
    remaining = json.loads((ROOT / 'benchmarks/verified_without_mini_ids.json').read_text())
    assert len(remaining) == 450 and set(remaining) == full - mini
    print('Mini overlap verified. These checks do not establish runtime readiness.')


if __name__ == '__main__':
    main()
