"""Verify/restore all five selected framework sources without changing older locks."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prepare_framework_integrations import main as prepare_four
from project_paths import source_location
from acl_frameworks.common import read
from acl_dgm.native import LOCK, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clone', action='store_true')
    args = parser.parse_args()
    prepare_four()
    cfg = read(LOCK)
    source = source_location('repos/dgm')
    if source != ROOT / cfg['source']:
        raise ValueError('DGM registry and canonical directory disagree')
    if not source.exists() and args.clone:
        env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
        subprocess.run(['git', '-c', 'http.version=HTTP/1.1', '-c', 'core.hooksPath=/dev/null',
            'clone', '--no-checkout', '--filter=blob:none', cfg['url'], str(source)], env=env, check=True, timeout=180)
        subprocess.run(['git', '-C', str(source), '-c', 'core.hooksPath=/dev/null', 'checkout',
            '--detach', cfg['revision']], env=env, check=True, timeout=180)
    verify()
    print(f"dgm: pinned source verified ({cfg['revision'][:12]})")


if __name__ == '__main__':
    main()
