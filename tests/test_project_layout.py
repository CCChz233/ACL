import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def helper():
    spec = importlib.util.spec_from_file_location('project_paths_fixture', ROOT / 'scripts/project_paths.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_setup_uses_canonical_directory_and_restores_relative_legacy_path(tmp_path, monkeypatch):
    module = helper()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / 'configs').mkdir()
    (tmp_path / 'configs/project-layout.json').write_text(json.dumps({'sources': [
        {'legacy': 'repos/example', 'canonical': 'frameworks/example'}]}))
    canonical = module.source_location('repos/example')
    assert canonical == tmp_path / 'frameworks/example'
    assert (tmp_path / 'repos/example').is_symlink()
    canonical.mkdir()
    (canonical / 'source.py').write_text('frozen source')
    assert (tmp_path / 'repos/example/source.py').read_text() == 'frozen source'
    assert module.source_location('repos/example') == canonical
    with pytest.raises(ValueError, match='Unregistered'):
        module.source_location('repos/unregistered')


def test_existing_checkout_is_never_overwritten_by_prepare(tmp_path, monkeypatch):
    module = helper()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / 'configs').mkdir()
    (tmp_path / 'configs/project-layout.json').write_text(json.dumps({'sources': [
        {'legacy': 'repos/example', 'canonical': 'agents/example'}]}))
    legacy = tmp_path / 'repos/example'
    legacy.mkdir(parents=True)
    (legacy / 'user.py').write_text('user edits')
    with pytest.raises(ValueError, match='Old physical checkout'):
        module.source_location('repos/example')
    assert (legacy / 'user.py').read_text() == 'user edits'


def test_new_source_extension_preserves_base_migration_manifest(tmp_path, monkeypatch):
    module = helper()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / 'configs').mkdir()
    base = tmp_path / 'configs/project-layout.json'
    base.write_text(json.dumps({'sources': []}))
    before = base.read_bytes()
    (tmp_path / 'configs/project-layout.extensions.json').write_text(json.dumps({'sources': [
        {'legacy': 'repos/harnessfix', 'canonical': 'frameworks/harnessfix'}]}))
    assert module.source_location('repos/harnessfix') == tmp_path / 'frameworks/harnessfix'
    assert (tmp_path / 'repos/harnessfix').is_symlink()
    assert base.read_bytes() == before
