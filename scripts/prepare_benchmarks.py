#!/usr/bin/env python3
"""Restore pinned public benchmark source/data without configuring training."""
from pathlib import Path
import argparse
import json
import shutil
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

from verify_benchmarks import ROOT, digest, load_lock, safe_path, verify_download, verify_tree
from project_paths import source_location

CACHE = ROOT / '.cache/benchmark_sources'


def read_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'rsi-code-terminal-preparation'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    partial = destination.with_suffix(destination.suffix + '.partial')
    for attempt in range(3):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            headers = {'User-Agent': 'rsi-code-terminal-preparation'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as response:
                append = offset > 0 and response.status == 206
                with partial.open('ab' if append else 'wb') as f:
                    while chunk := response.read(4 * 1024 * 1024):
                        f.write(chunk)
            partial.replace(destination)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def prepare(item):
    directory = (source_location(item['local_dir']) if item['local_dir'].startswith('repos/')
                 else safe_path(ROOT, item['local_dir']))
    if item['kind'] == 'github_archive':
        tree_file = CACHE / (item['id'] + '-tree.json')
        if tree_file.exists():
            tree = json.loads(tree_file.read_text())
        else:
            tree = read_json(f'https://api.github.com/repos/{item["repository"]}/git/trees/{item["revision"]}?recursive=1')
            assert tree['sha'] == item['revision'] and not tree.get('truncated')
            tree_file.write_text(json.dumps(tree) + '\n')
        if directory.exists():
            # Never overwrite existing user changes or incomplete checkouts.
            verify_tree(directory, tree, item['revision'])
        else:
            archive = CACHE / (item['id'] + '-' + item['revision'] + '.tar.gz')
            url = f'https://codeload.github.com/{item["repository"]}/tar.gz/{item["revision"]}'
            download(url, archive)
            with tempfile.TemporaryDirectory(prefix=item['id'] + '-', dir=CACHE) as temporary:
                with tarfile.open(archive) as package:
                    package.extractall(temporary, filter='data')
                entries = list(Path(temporary).iterdir())
                assert len(entries) == 1 and entries[0].is_dir()
                verify_tree(entries[0], tree, item['revision'])
                directory.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(entries[0]), directory)
    else:
        directory.mkdir(parents=True, exist_ok=True)
        for file in item['files']:
            target = safe_path(directory, file['path'])
            path = urllib.parse.quote(file['path'], safe='/')
            url = f'https://huggingface.co/datasets/{item["repository"]}/resolve/{item["revision"]}/{path}'
            download(url, target)
            assert target.stat().st_size == file['bytes'] and digest(target) == file['sha256']
    verify_download(item)
    print(f'{item["id"]}: source/data verified; runtime not evaluated', flush=True)


def main():
    items = load_lock()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', choices=[x['id'] for x in items])
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    for item in items:
        if not args.only or item['id'] == args.only:
            prepare(item)


if __name__ == '__main__':
    main()
