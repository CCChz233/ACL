import argparse
import datetime
import json
from pathlib import Path

from acl_rsi.settings import write_json
from .common import ROOT, REGISTRY, read, sha, verify


def main():
    parser = argparse.ArgumentParser(description='Prepare and check RSI framework integrations; no experiment launch')
    parser.add_argument('command', choices=('check', 'prepare', 'smoke'))
    parser.add_argument('--work', type=Path)
    args = parser.parse_args()
    registry = read(REGISTRY)
    verified = {name: verify(name)[0]['revision'] for name in registry['frameworks']}
    if args.command == 'check':
        print(json.dumps({'status': 'source_versions_verified', 'frameworks': verified,
                          'model': registry['provider']['model'], 'live_experiments_enabled': False,
                          'new_model_calls': 0}, indent=2))
        return
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    work = args.work or ROOT / 'experiments/runs/framework-integration' / now
    work = work.resolve()
    if args.command == 'prepare':
        from .context import export_baseline
        from .harnessfix import compile_snapshot, isolated_plan
        export_baseline(work / 'harnessfix/optimizer', ['django__django-11790', 'django__django-11815'])
        compile_snapshot(work / 'harnessfix/optimizer')
        report = isolated_plan(work / 'harnessfix', ['django__django-11790'], ['django__django-11815'])
        report['scope'] = 'integration artifacts only; task IDs are development fixtures, not a frozen experimental split'
    else:
        from .smoke import run
        report = run(work)
    write_json(work / 'integration-lock.json', {'registry_sha256': sha(REGISTRY),
        'upstream_revisions': verified,
        'adapter_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'acl_frameworks').glob('*.py'))}})
    print(json.dumps({'work': str(work), **report}, indent=2))


if __name__ == '__main__':
    main()
