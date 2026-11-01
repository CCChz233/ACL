"""Canonical asset paths and compatibility links for pinned historical manifests."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_location(legacy_path):
    layout = json.loads((ROOT / 'configs/project-layout.json').read_text())
    extension = ROOT / 'configs/project-layout.extensions.json'
    sources = layout['sources'] + (json.loads(extension.read_text())['sources'] if extension.exists() else [])
    item = next((i for i in sources if i['legacy'] == legacy_path), None)
    if item is None:
        raise ValueError(f'Unregistered upstream source: {legacy_path}')
    old, canonical = ROOT / legacy_path, ROOT / item['canonical']
    if old.is_symlink():
        if old.resolve() != canonical.resolve():
            raise ValueError(f'Unexpected compatibility link: {legacy_path}')
    elif old.exists():
        raise ValueError(f'Old physical checkout still exists: {legacy_path}; migrate the workspace first')
    else:
        old.parent.mkdir(parents=True, exist_ok=True)
        old.symlink_to(os.path.relpath(canonical, old.parent), target_is_directory=True)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    return canonical
