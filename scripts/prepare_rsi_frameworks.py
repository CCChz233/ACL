#!/usr/bin/env python3
"""Verify selected sources; --clone restores missing pinned official checkouts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from project_paths import source_location

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clone', action='store_true')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'docs/rsi_frameworks.sources.lock.json').read_text())
    env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null',
               GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0')
    for item in lock['cloned_frameworks']:
        path = source_location(item['local_path'])
        if not path.exists() and args.clone:
            subprocess.run(['git', '-c', 'http.version=HTTP/1.1', '-c', 'core.hooksPath=/dev/null',
                            'clone', '--no-checkout', '--filter=blob:none', item['url'], str(path)],
                           env=env, check=True, timeout=180)
            subprocess.run(['git', '-C', str(path), '-c', 'core.hooksPath=/dev/null',
                            'checkout', '--detach', item['revision']],
                           env=env, check=True, timeout=180)
        revision = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != item['revision']:
            raise ValueError(f"{item['name']}: existing checkout differs; left untouched")
        if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain'], text=True):
            raise ValueError(f"{item['name']}: local changes; left untouched")
        for name, expected in item['root_file_sha256'].items():
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"{item['name']}/{name}: hash mismatch")
        subprocess.run(['git', '-C', str(path), 'fsck', '--connectivity-only'],
                       check=True, capture_output=True, text=True)
        print(f"{item['name']}: pinned source verified ({revision[:12]})")


if __name__ == '__main__':
    main()
