"""Offline native DGM archive contracts; no model or Docker calls."""
import json
import random
from types import SimpleNamespace
import sys

import pytest

from acl_frameworks.common import ROOT, read
from acl_dgm.adapter import DGMAdapter, performance, validate
from acl_dgm.cli import IDS, smoke
from acl_dgm.native import outer
from acl_dgm.runtime import DGMProposer, diagnosis_messages


def rows(name, harness, ids):
    return {i: {'score': int(name == 'initial' and i == IDS[1]), 'empty_patch': False,
                'patch': 'own patch', 'messages': [{'role': 'user', 'content': 'own trace'}]} for i in ids}


def edit(context):
    p = context['candidate_harness'] / 'agent.py'
    p.write_text(p.read_text()+'\n# Offline fixture\n')


def test_native_two_generation_archive_keeps_worse_children_and_resumes(tmp_path):
    report = smoke(tmp_path)
    assert report['model_calls'] == report['benchmark_executions'] == 0
    assert report['benchmark_accuracy'] is None
    adapter = DGMAdapter(tmp_path, IDS, edit, rows, evidence_scope='synthetic_contract_fixture')
    state = adapter.run(1)
    assert state['generation'] == 2
    assert state['archive'] == ['initial', 'node_0000', 'node_0001', 'node_0002']
    assert read(adapter.archive / 'node_0002/metadata.json')['parent_commit'] in state['archive'][:-1]


def test_native_sampling_can_revisit_a_lower_scoring_parent(tmp_path):
    smoke(tmp_path)
    with outer(lambda **kwargs: None) as native:
        archive = tmp_path / 'controller/output_dgm/pilot'
        selected = set()
        for seed in range(200):
            native.random = random.Random(seed)
            selected.add(native.choose_selfimproves(str(archive), ['initial', 'node_0000'], 1,
                method='score_child_prop')[0][0])
        assert selected == {'initial', 'node_0000'}


def test_invalid_candidate_excluded_without_grading_or_zero_imputation(tmp_path):
    calls = []
    def invalid(context):
        (context['candidate_harness'] / 'agent.py').write_text('broken python !!!')
    def evaluate(name, harness, ids):
        calls.append(name)
        return rows(name, harness, ids)
    adapter = DGMAdapter(tmp_path, IDS, invalid, evaluate)
    state = adapter.run()
    assert state['archive'] == ['initial'] and state['children_compiled'] == []
    assert calls == ['initial']


def test_evaluation_failure_is_surfaced_despite_native_exception_handler(tmp_path):
    def evaluate(name, harness, ids):
        if name != 'initial':
            raise ConnectionError('fixture infrastructure failure')
        return rows(name, harness, ids)
    adapter = DGMAdapter(tmp_path, IDS, edit, evaluate)
    with pytest.raises(RuntimeError, match='evaluation failures'):
        adapter.run()
    assert read(tmp_path / 'evaluation-failures.json')[0]['error_type'] == 'ConnectionError'


def test_provider_configuration_error_is_not_mislabeled_invalid_candidate(tmp_path):
    def propose(context):
        raise ValueError('provider configuration unavailable')
    adapter = DGMAdapter(tmp_path, IDS, propose, rows)
    with pytest.raises(RuntimeError, match='evaluation failures'):
        adapter.run()
    failure = read(tmp_path / 'evaluation-failures.json')[0]
    assert failure['phase'] == 'proposal' and failure['error_type'] == 'ValueError'


def test_empty_patch_and_failure_are_distinct_and_invalid_results_rejected():
    result = performance(['a', 'b'], {'a': {'score': 0, 'empty_patch': True},
                                      'b': {'score': 0, 'empty_patch': False}})
    assert result['total_emptypatch_ids'] == ['a'] and result['total_unresolved_ids'] == ['b']
    with pytest.raises(ValueError, match='Incomplete'):
        performance(['a'], {})
    with pytest.raises(ValueError, match='empty patch'):
        performance(['a'], {'a': {'score': 1, 'empty_patch': True}})


def test_diagnosis_never_exports_reference_patch_or_private_test_sections(tmp_path):
    adapter = DGMAdapter(tmp_path, IDS, edit, rows)
    adapter.prepare()
    adapter.publish()
    context = {'parent_harness': tmp_path / 'optimizer/history/dgm-archive/initial/harness',
        'workspace': tmp_path / 'optimizer', 'parent': 'initial', 'entry': IDS[0]}
    before = sys.modules.get('utils')
    with outer(lambda **kwargs: None):
        messages = diagnosis_messages(context)
    text = json.dumps(messages)
    assert 'Private Test Patch Start' not in text and '{test_patch}' not in text
    assert 'own trace' in text and 'own patch' in text
    assert sys.modules.get('utils') is before
    assert not list((tmp_path / 'optimizer').rglob('test_output.txt'))


def test_disabled_provider_never_attempts_network(tmp_path):
    cfg = read(ROOT / 'configs/dgm-mini-pilot.template.json')
    with pytest.raises(RuntimeError, match='disabled'):
        DGMProposer(cfg, tmp_path)({})


def test_compilation_cache_allowed_but_extra_source_rejected(tmp_path):
    adapter = DGMAdapter(tmp_path, IDS, edit, rows)
    adapter.prepare()
    folder = adapter.public / 'harness'
    cache = folder / '__pycache__'
    cache.mkdir()
    (cache / 'agent.cpython-312.pyc').write_bytes(b'fixture')
    validate(folder, folder)
    (cache / 'unexpected.py').write_text('')
    with pytest.raises(ValueError, match='bytecode cache'):
        validate(folder, folder)


def test_parent_model_real_sdk_toolcall_contract():
    from openai.types.chat import ChatCompletion
    from acl_dgm.runtime import NativeMiniModel
    seen = []
    response = ChatCompletion.model_validate({'id': 'fixture', 'object': 'chat.completion',
        'created': 0, 'model': 'deepseek-flash', 'choices': [{'index': 0,
        'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
        'tool_calls': [{'id': 'call_fixture', 'type': 'function', 'function': {
            'name': 'bash', 'arguments': '{"command":"echo ok"}'}}]}}],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
    def gateway(**kw):
        seen.append(kw)
        return response
    gateway.ledger = SimpleNamespace(summary=lambda: {'calls': 1})
    model = NativeMiniModel({'model': 'deepseek-flash'}, {
        'observation_template': '{{output}}', 'format_error_template': 'bad format'}, gateway)
    message = model.query([{'role': 'user', 'content': 'task', 'extra': {'private': True}}])
    assert message['extra']['actions'][0]['command'] == 'echo ok'
    assert seen[0]['tools'] and seen[0]['messages'] == [{'role': 'user', 'content': 'task'}]
    observations = model.format_observation_messages(message, [{'output': 'ok', 'returncode': 0}])
    assert observations[0]['tool_call_id'] == 'call_fixture'
    assert model.serialize()['info']['usage']['calls'] == 1


def test_cli_zero_budget_template_cannot_start_paid_work(tmp_path, monkeypatch):
    from acl_dgm.cli import main
    monkeypatch.setattr(sys, 'argv', ['dgm', 'run', '--live', '--config',
        str(ROOT / 'configs/dgm-mini-pilot.template.json'), '--work', str(tmp_path)])
    with pytest.raises(ValueError, match='zero paid budget'):
        main()
    assert not (tmp_path / 'optimizer-api').exists()


def test_cli_preserves_an_existing_run_with_different_lock(tmp_path, monkeypatch):
    from acl_dgm.cli import main
    path = tmp_path / 'integration-lock.json'
    path.write_text('{"different_runtime": true}')
    before = path.read_bytes()
    monkeypatch.setattr(sys, 'argv', ['dgm', 'prepare', '--work', str(tmp_path)])
    with pytest.raises(ValueError, match='source/runtime lock differs'):
        main()
    assert path.read_bytes() == before and not (tmp_path / 'optimizer').exists()


def test_self_modifier_loads_the_selected_parent_controller(tmp_path, monkeypatch):
    from acl_dgm import runtime
    import docker
    import minisweagent.environments.docker as environment
    from scripts import run_swe_local
    adapter = DGMAdapter(tmp_path / 'data', IDS, edit, rows)
    adapter.prepare(); adapter.publish()
    parent = adapter.public / 'history/dgm-archive/initial/harness'
    (parent / 'agent.py').write_text('''
from pathlib import Path
class DefaultAgent:
    def __init__(self, model, env, output_path, **kwargs): self.output = Path(output_path)
    def run(self, task):
        (self.output.parent / 'selected-parent-ran').write_text('yes')
        return {'exit_status': 'Submitted'}
    def save(self, path): Path(path).write_text('{}')
''')
    class Meter:
        ledger = SimpleNamespace()
        def __call__(self, **kwargs):
            content = json.dumps({'problem_description': 'generic improvement', 'implementation_suggestion': 'bounded change'})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    class Environment:
        container_id = None
        def __init__(self, **kwargs): pass
    monkeypatch.setattr(runtime.DGMProposer, 'meter', lambda *a: Meter())
    monkeypatch.setattr(docker, 'from_env', lambda **kw: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(run_swe_local, 'require_cache', lambda *a: None)
    monkeypatch.setattr(environment, 'DockerEnvironment', Environment)
    cfg = read(ROOT / 'configs/dgm-mini-pilot.template.json')
    context = {'name': 'fixture', 'parent': 'initial', 'entry': IDS[0],
        'parent_harness': parent, 'candidate_harness': adapter.public / 'candidates/fixture/harness',
        'workspace': adapter.public}
    with outer(lambda **kwargs: None):
        DGMProposer(cfg, tmp_path / 'run', enabled=True)(context)
    assert (tmp_path / 'run/attempts/fixture/selected-parent-ran').exists()
