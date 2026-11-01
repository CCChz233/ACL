"""Read-only workspace inventory; never reads .env, runs models, or uses Docker.

Uses lstat/scandir without following symbolic links. --output explicitly saves
the inventory to a new report; source files and experiment artifacts are not
changed. Protected fingerprints support before/after documentation maintenance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SKIP = {'.git', '__pycache__', 'node_modules', '.venv', '.venv-terminal', '.cache'}
EVIDENCE_NAMES = {
    'grade.json', 'worker.json', 'usage.json', 'result.json', 'summary.json',
    'input-parent.json', 'runtime-lock.json', 'source_manifest.json', 'patch.diff',
    'final-audit.json',
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def walk_files(folder: Path):
    for base, directories, files in os.walk(folder, followlinks=False):
        directories[:] = sorted(
            name for name in directories
            if name not in SKIP and not (Path(base) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(base) / name
            if not path.is_symlink():
                yield path


def listing(folder: Path):
    rows = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name):
        row = {'name': path.name}
        if path.is_symlink():
            row |= {'kind': 'symlink', 'target': os.readlink(path), 'exists': path.exists()}
        elif path.is_dir():
            children = list(path.iterdir())
            row |= {'kind': 'directory', 'direct_entries': len(children)}
        else:
            row |= {'kind': 'file', 'bytes': path.stat().st_size}
        rows.append(row)
    return rows


def inventory():
    packages = sorted(p.name for p in ROOT.glob('acl_*') if p.is_dir()
                      and not p.is_symlink() and not p.name.endswith('.egg-info'))
    protected = {}
    for name in packages + ['scripts', 'tests', 'configs']:
        for path in walk_files(ROOT / name):
            if path.suffix in {'.py', '.json', '.toml', '.txt', '.mjs'}:
                protected[str(path.relative_to(ROOT))] = sha(path)
    for path in (ROOT / 'docs').glob('*lock.json'):
        protected[str(path.relative_to(ROOT))] = sha(path)
    for path in walk_files(ROOT / 'experiments/runs'):
        if path.name in EVIDENCE_NAMES:
            protected[str(path.relative_to(ROOT))] = sha(path)
    for name in ['pyproject.toml', 'uv.lock', 'benchmarks/sources.lock.json',
                 'benchmarks/datasets/swe-bench-verified-mini/test.json']:
        path = ROOT / name
        if path.is_file():
            protected[name] = sha(path)

    # du reports allocated space, not logical bytes or Docker's external store.
    names = sorted(p.name for p in ROOT.iterdir() if not p.is_symlink())
    disk = subprocess.run(['du', '-sk', *names], cwd=ROOT, capture_output=True, text=True)
    if disk.returncode:
        raise RuntimeError('du failed: ' + disk.stderr[:300])
    disk_kib = {}
    for line in disk.stdout.splitlines():
        kib, name = line.split('\t', 1)
        disk_kib[name] = int(kib)

    areas = {name: listing(ROOT / name) for name in
             ['frameworks', 'agents', 'benchmarks/sources', 'experiments/runs',
              'reports/exports', 'docs', 'scripts', 'configs', 'repos']}
    return {
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'workspace only; no symlink traversal, model calls, Docker access, or secret content',
        'top_level': listing(ROOT), 'runtime_packages': packages,
        'areas': areas,
        'counts': {name: dict(Counter(row['kind'] for row in rows)) for name, rows in areas.items()},
        'allocated_kib_by_top_entry': disk_kib,
        'allocated_kib_total': sum(disk_kib.values()),
        'protected_fingerprints': dict(sorted(protected.items())),
        'protected_count': len(protected),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', type=Path, help='Compare fingerprints with a prior inventory')
    args = parser.parse_args()
    result = inventory()
    if args.compare:
        before = json.loads(args.compare.read_text())['protected_fingerprints']
        after = result['protected_fingerprints']
        result['comparison'] = {
            'checked': len(before),
            'changed_or_missing': [name for name, digest in before.items() if after.get(name) != digest],
            'added': sorted(set(after) - set(before)),
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Reports are append-only: never overwrite a previous audit by accident.
        with args.output.open('x') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    summary = {key: result[key] for key in ['captured_at', 'counts', 'allocated_kib_total', 'protected_count']}
    summary['runtime_packages'] = len(result['runtime_packages'])
    if 'comparison' in result:
        summary['comparison'] = result['comparison']
    if args.output:
        summary['output'] = str(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if result.get('comparison', {}).get('changed_or_missing'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
