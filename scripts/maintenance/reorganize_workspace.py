"""Move local assets into the canonical layout without changing frozen evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / 'configs/project-layout.json'
AUDIT = ROOT / 'work/project-layout-migration/2026-10-19'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def snapshot(layout):
    paths = []
    for name in layout['frozen_runtime_packages']:
        paths.extend((ROOT / name).rglob('*.py'))
    paths.extend((ROOT / 'configs').glob('*.json'))
    paths.extend((ROOT / 'docs').glob('*lock.json'))
    paths.append(ROOT / 'benchmarks/sources.lock.json')
    paths.append(ROOT / 'benchmarks/datasets/swe-bench-verified-mini/test.json')
    for name in ('verified-mini-50-baseline-v2', 'verified-mini-50-round1-recovery',
                 'gepa-mini50-v1', 'gepa-terminal-v1', 'terminal-pilot-v1', 'terminal-round1'):
        folder = ROOT / 'work' / name
        paths.extend(p for p in folder.rglob('*.json') if p.name in
                     ('grade.json', 'worker.json', 'usage.json', 'summary.json',
                      'runtime-lock.json', 'source_manifest.json', 'result.json'))
        paths.extend(folder.rglob('patch.diff'))
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths)) if p.is_file()}


def repositories(layout):
    rows = []
    for item in layout['sources']:
        path = ROOT / item['legacy']
        entry = {'name': item['name'], 'canonical': item['canonical']}
        if (path / '.git').exists():
            entry['revision'] = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
            entry['tracked_status'] = subprocess.check_output(
                ['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no'], text=True)
        rows.append(entry)
    return rows


def verify(layout):
    rows = []
    for item in layout['sources'] + layout['assets']:
        old, new = ROOT / item['legacy'], ROOT / item['canonical']
        if not old.is_symlink() or not new.is_dir() or new.is_symlink() or old.resolve() != new.resolve():
            raise ValueError(f"Invalid canonical/compatibility layout: {item['name']}")
        rows.append({'name': item['name'], 'canonical': item['canonical'], 'legacy': item['legacy']})
    before = read(AUDIT / 'before.json')
    actual = snapshot(layout)
    changed = [p for p, digest in before['frozen_evidence'].items() if actual.get(p) != digest]
    if changed:
        raise ValueError('Frozen evidence changed: ' + ', '.join(changed))
    current = repositories(layout)
    if current != before['repositories']:
        raise ValueError('Upstream revisions or tracked status changed')
    report = {'status': 'verified', 'physical_moves': len(rows), 'compatibility_links': len(rows),
              'frozen_files_checked': len(before['frozen_evidence']), 'changed_frozen_files': changed,
              'upstream_revisions_and_tracked_status_unchanged': True, 'paths': rows,
              'model_calls': 0, 'docker_images_modified': False}
    write(AUDIT / 'verification.json', report)
    return report


def migrate(layout):
    items = layout['sources'] + layout['assets']
    if all((ROOT / i['legacy']).is_symlink() for i in items):
        return verify(layout)
    for item in items:
        old, new = ROOT / item['legacy'], ROOT / item['canonical']
        if not old.is_dir() or old.is_symlink() or new.exists() or new.is_symlink():
            raise ValueError(f"Ambiguous pre-migration paths: {item['name']}")
    write(AUDIT / 'before.json', {'layout_sha256': sha(LAYOUT), 'repositories': repositories(layout),
                               'frozen_evidence': snapshot(layout)})
    completed = []
    try:
        for item in items:
            old, new = ROOT / item['legacy'], ROOT / item['canonical']
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            completed.append((old, new))
            old.symlink_to(os.path.relpath(new, old.parent), target_is_directory=True)
            print(f"{item['legacy']} -> {item['canonical']}", flush=True)
        return verify(layout)
    except BaseException:
        for old, new in reversed(completed):
            if old.is_symlink():
                old.unlink()
            new.rename(old)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('migrate', 'verify'))
    args = parser.parse_args()
    layout = read(LAYOUT)
    report = migrate(layout) if args.command == 'migrate' else verify(layout)
    print(json.dumps({k: v for k, v in report.items() if k != 'paths'}, indent=2))


if __name__ == '__main__':
    main()
