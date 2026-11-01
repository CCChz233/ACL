"""Offline tests: no API calls, Docker execution or synthetic benchmark claims."""
import copy
import json
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletion

from acl_frameworks.common import REGISTRY, read
from acl_frameworks.context import EvidenceWorkspace
from acl_frameworks.meta_harness import MetaHarnessAdapter
from acl_frameworks.provider import RecordedDeepSeek
from acl_frameworks.provider import repair_xml_closure
from acl_frameworks.proposer import DeepSeekFileProposer
from acl_frameworks.smoke import run
from acl_rsi.deepseek import BudgetExceeded, DeepSeekClient, ProviderError


def config():
    cfg = copy.deepcopy(read(REGISTRY)['provider'])
    cfg['limits'].update(max_calls=2, max_tokens=100000)
    return cfg


def factory_with(create):
    def factory(cfg, ledger, role, limits):
        client = DeepSeekClient.__new__(DeepSeekClient)
        client.cfg, client.ledger, client.role, client.limits = cfg, ledger, role, limits
        client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **payload: create(ledger, payload))), close=lambda: None)
        return client
    return factory


def completion():
    return ChatCompletion(id='offline', created=0, model='deepseek-flash', object='chat.completion',
        choices=[{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'ok'}}],
        usage={'prompt_tokens': 20, 'completion_tokens': 5, 'total_tokens': 25})


def test_disabled_and_wrong_model_never_construct_client(tmp_path):
    def forbidden(*args):
        pytest.fail('No SDK client may be constructed')
    gate = RecordedDeepSeek(config(), tmp_path, 'repair', client_factory=forbidden)
    with pytest.raises(RuntimeError, match='disabled'):
        gate(model='deepseek-flash', messages=[])
    with pytest.raises(ValueError, match='model'):
        gate(model='another-model', messages=[])


def test_flash_xml_dsml_compatibility_is_narrow_and_does_not_invent_commands():
    body = "Thought\n<mswea_bash_command>python3 <<'PY'\nprint(1)\nPY"
    broken = body+'</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>'
    assert repair_xml_closure(broken) == body+'\n</mswea_bash_command>'
    assert repair_xml_closure(body) == body
    assert repair_xml_closure('no XML command') == 'no XML command'
    assert repair_xml_closure(broken+' trailing text') == broken+' trailing text'
    valid = '<mswea_bash_command>echo 1</mswea_bash_command>'
    assert repair_xml_closure(valid) == valid


def test_serialization_repair_preserves_raw_provider_response(tmp_path):
    raw = '<mswea_bash_command>echo 1</｜｜DSML｜｜ parameter></｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>'
    def create(ledger, payload):
        response = completion()
        response.choices[0].message.content = raw
        return response
    cfg = config()
    cfg['xml_dsml_compat'] = True
    gate = RecordedDeepSeek(cfg, tmp_path, 'implementation', enabled=True,
                            client_factory=factory_with(create))
    response = gate(model='deepseek-flash', messages=[], temperature=0)
    assert response.choices[0].message.content == '<mswea_bash_command>echo 1\n</mswea_bash_command>'
    row = read(tmp_path / 'usage.json')['requests'][0]
    stored = read(tmp_path / 'usage-responses' / (row['id']+'.json'))
    assert stored['choices'][0]['message']['content'] == raw
    assert (tmp_path / 'format-repairs' / (row['id']+'.json')).exists()
    assert read(tmp_path / 'requests' / (row['id']+'.json'))['temperature'] == 0


def test_payload_timing_and_correct_concurrent_reservation(tmp_path):
    def create(ledger, payload):
        # A different process/thread can reserve between our reservation and API.
        ledger.reserve('concurrent-role', [], 10)
        return completion()
    gate = RecordedDeepSeek(config(), tmp_path, 'repair', enabled=True,
                            client_factory=factory_with(create))
    messages = [{'role': 'user', 'content': 'public fixture'}]
    gate(model='openai/deepseek-flash', messages=messages)
    rows = read(tmp_path / 'usage.json')['requests']
    assert rows[0]['status'] == 'completed' and rows[0]['usage']['total_tokens'] == 25
    assert rows[0]['framework_role'] == 'repair' and rows[0]['api_seconds'] >= 0
    assert rows[1]['status'] == 'reserved' and 'framework_role' not in rows[1]
    payload = read(tmp_path / 'requests' / (rows[0]['id']+'.json'))
    assert payload['messages'] == messages and payload['model'] == 'deepseek-flash'
    assert payload['extra_body']['thinking']['type'] == 'disabled'
    assert (tmp_path / 'usage-responses' / (rows[0]['id']+'.json')).exists()
    with pytest.raises(BudgetExceeded):
        gate(model='deepseek-flash', messages=[])


def test_failed_api_keeps_reservation_and_sanitizes_error(tmp_path):
    def fail(ledger, payload):
        raise RuntimeError('sensitive SDK detail must never be serialized')
    gate = RecordedDeepSeek(config(), tmp_path, 'analysis', enabled=True,
                            client_factory=factory_with(fail))
    with pytest.raises(ProviderError) as error:
        gate(model='deepseek-flash', messages=[])
    assert 'sensitive' not in str(error.value)
    row = read(tmp_path / 'usage.json')['requests'][0]
    assert row['status'] == 'reserved' and row['charged_tokens'] > 0
    assert 'usage' not in row and row['api_seconds'] >= 0


def test_workspace_guards_and_read_continuation(tmp_path):
    ws = EvidenceWorkspace(tmp_path / 'public')
    (tmp_path / 'private').write_text('private grader')
    (ws.root / 'escape').symlink_to(tmp_path / 'private')
    for path in ('../private', '.env', 'escape', ''):
        with pytest.raises(ValueError):
            ws.read(path)
    with pytest.raises(ValueError):
        ws.write('history/change.json', 'overwrite')
    ws.write('candidates/c/harness/agent.py', 'a'*40000+'END')
    proposer = DeepSeekFileProposer(ws.root, None)
    first = json.loads(proposer.tool('Read', {'path': 'candidates/c/harness/agent.py'}))
    second = json.loads(proposer.tool('Read', {'path': 'candidates/c/harness/agent.py',
                                               'offset': first['next_offset']}))
    assert first['truncated'] and not second['truncated']
    assert first['content']+second['content'] == 'a'*40000+'END'
    proposer.tool('Edit', {'path': 'candidates/c/harness/agent.py', 'old': 'END', 'new': 'TAIL'})
    assert ws.path('candidates/c/harness/agent.py').read_text() == 'a'*40000+'TAIL'


def test_native_controllers_and_export_are_offline(tmp_path):
    report = run(tmp_path / 'smoke')
    assert report['status'] == 'passed'
    assert report['model_calls'] == report['benchmark_executions'] == 0
    assert report['benchmark_accuracy'] is None
    snapshot = tmp_path / 'smoke/meta/optimizer'
    assert not list(snapshot.rglob('test_output.txt'))
    assert not list(snapshot.rglob('report.json'))
    assert not list(snapshot.rglob('.env'))
    assert set(read(next(snapshot.glob('history/*/feedback.json')))) == {
        'resolved', 'stop', 'usage', 'problem_statement'}


def test_invalid_grade_never_becomes_zero_or_gets_cached(tmp_path):
    adapter = MetaHarnessAdapter(tmp_path, ['task'], None, lambda *args: {'task': None})
    adapter.native.JOBS_DIR = tmp_path / 'private-jobs'
    with pytest.raises(ValueError, match='invalid grading'):
        adapter.evaluate('h0:AgentHarness', 'job')
    assert not (tmp_path / 'private-jobs/job/outcomes.json').exists()
    path = tmp_path / 'private-jobs/job'
    path.mkdir(parents=True)
    (path / 'outcomes.json').write_text(json.dumps({'valid': True, 'scores': {'task': 99}}))
    with pytest.raises(ValueError, match='Invalid cached'):
        adapter.results(path)


def test_native_litellm_binding_stops_budget_retries(monkeypatch, tmp_path):
    import litellm
    from minisweagent.models.litellm_model import LitellmModel
    from acl_frameworks.provider import bind_litellm
    # Register restoration before the production binding mutates either object.
    monkeypatch.setattr(litellm, 'completion', litellm.completion)
    monkeypatch.setattr(LitellmModel, 'abort_exceptions', LitellmModel.abort_exceptions)
    gate = RecordedDeepSeek(config(), tmp_path, 'native-analysis')
    bind_litellm(gate)
    assert litellm.completion is gate
    assert BudgetExceeded in LitellmModel.abort_exceptions
    assert ProviderError in LitellmModel.abort_exceptions
    with pytest.raises(RuntimeError, match='disabled'):
        litellm.completion(model='openai/deepseek-flash', messages=[])
