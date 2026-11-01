import importlib.util
from pathlib import Path
from types import SimpleNamespace

import docker
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, script):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_frozen_swe_cleaners_retain_mini_tags_and_ids(monkeypatch):
    run = load('swe_local_fixture', 'run_swe_local.py')
    from acl_rsi.mini50 import StreamingDomain
    calls = []
    monkeypatch.setattr(StreamingDomain, 'release', staticmethod(lambda *args: calls.append(args)))
    run.retain_mini_images({'images': [{'image': 'mini:latest', 'expected_id': 'sha256:mini'}]})
    StreamingDomain.release(None, 'mini:latest', {}, set(), None)
    StreamingDomain.release(None, 'alias:latest', {'alias:latest': 'sha256:mini'}, set(), None)
    assert not calls
    StreamingDomain.release(None, 'unrelated:latest', {}, set(), None)
    assert len(calls) == 1


def test_incomplete_local_cache_stops_before_any_paid_runner():
    run = load('swe_local_cache_fixture', 'run_swe_local.py')
    class Images:
        def get(self, name):
            if name == 'missing':
                raise docker.errors.ImageNotFound('missing')
            return SimpleNamespace(id='sha256:wrong')
    client = SimpleNamespace(images=Images())
    with pytest.raises(RuntimeError, match='incomplete'):
        run.require_cache(client, {'images': [{'image': 'missing', 'instance_id': 'task', 'expected_id': 'sha256:expected'}]})
    with pytest.raises(RuntimeError, match='Wrong pinned'):
        run.require_cache(client, {'images': [{'image': 'wrong', 'instance_id': 'task', 'expected_id': 'sha256:expected'}]})


def test_filling_matching_local_cache_makes_no_pull_or_delete_calls(tmp_path, monkeypatch):
    cache = load('swe_fill_fixture', 'cache_swe_mini_images.py')
    policy_path = tmp_path / 'policy.json'
    policy_path.write_text('{}')
    monkeypatch.setattr(cache, 'POLICY', policy_path)
    monkeypatch.setattr(cache, 'WORK', tmp_path / 'work')
    class Images:
        def get(self, name):
            return SimpleNamespace(id='sha256:expected', attrs={'Architecture': 'amd64'})
        def pull(self, *args, **kwargs):
            pytest.fail('Existing pinned image must not be downloaded again')
        def remove(self, *args, **kwargs):
            pytest.fail('Mini images must never be deleted by cache fill')
    report = cache.fill(SimpleNamespace(images=Images()), {'images': [
        {'image': 'mini:latest', 'instance_id': 'fixture', 'expected_id': 'sha256:expected'}],
        'min_free_bytes': 4294967296}, pull=True)
    assert report['status'] == 'completed' and report['cached'] == 1 and report['downloaded'] == 0
