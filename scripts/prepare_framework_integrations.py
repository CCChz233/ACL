"""Verify the four current RSI sources; optionally restore missing pinned checkouts."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acl_frameworks.common import REGISTRY, read, verify
from project_paths import source_location


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clone', action='store_true', help='Only clone missing sources; never reset existing work')
    args = parser.parse_args()
    env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
    for name, cfg in read(REGISTRY)['frameworks'].items():
        path = source_location('repos/'+name)
        if path != ROOT / cfg['source']:
            raise ValueError('Registry and directory mapping disagree')
        if not path.exists() and args.clone:
            subprocess.run(['git', '-c', 'http.version=HTTP/1.1', '-c', 'core.hooksPath=/dev/null',
                'clone', '--no-checkout', '--filter=blob:none', cfg['url'], str(path)],
                env=env, check=True, timeout=180)
            subprocess.run(['git', '-C', str(path), '-c', 'core.hooksPath=/dev/null',
                'checkout', '--detach', cfg['revision']], env=env, check=True, timeout=180)
        verify(name)
        print(f"{name}: pinned source verified ({cfg['revision'][:12]})")


if __name__ == '__main__':
    main()
