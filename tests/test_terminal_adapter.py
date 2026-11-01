import asyncio
from types import SimpleNamespace
import pytest
from minisweagent.exceptions import Submitted
from acl_terminal.agent import ShellBridge

@pytest.mark.asyncio
async def test_shell_bridge_submission_and_results():
    class Fake:
        calls = []
        async def exec(self, command, timeout_sec):
            self.calls.append((command, timeout_sec))
            if command == 'finish':
                return SimpleNamespace(stdout='COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\ndone', stderr='', return_code=0)
            return SimpleNamespace(stdout='out', stderr='err', return_code=7)
    fake = Fake()
    bridge = ShellBridge(fake, asyncio.get_running_loop(), 60)
    result = await asyncio.to_thread(bridge.execute, {'command': 'test'})
    assert result == {'output': 'outerr', 'returncode': 7, 'exception_info': ''}
    with pytest.raises(Submitted):
        await asyncio.to_thread(bridge.execute, {'command': 'finish'})
    bridge.stopped.set()
    with pytest.raises(RuntimeError, match='stopped'):
        await asyncio.to_thread(bridge.execute, {'command': 'never execute'})
    assert fake.calls == [('test', 60), ('finish', 60)]

@pytest.mark.asyncio
async def test_full_mini_loop_records_payload_usage_and_stops(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from openai.types.chat import ChatCompletion
    from harbor.models.agent.context import AgentContext
    from acl_terminal.agent import PilotAgent
    import acl_rsi.deepseek as provider
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-placeholder')
    def complete(**kwargs):
        assert kwargs['model'] == 'deepseek-flash'
        assert kwargs['extra_body'] == {'thinking': {'type': 'disabled'}}
        return ChatCompletion.model_validate({'id': 'unit-test', 'object': 'chat.completion',
            'created': 1, 'model': 'deepseek-flash', 'usage': {'prompt_tokens': 8, 'completion_tokens': 2, 'total_tokens': 10},
            'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': 'Done',
                'tool_calls': [{'id': 'test-call', 'type': 'function', 'function': {
                    'name': 'bash', 'arguments': '{"command":"echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}'}}]}}]})
    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=complete))
    monkeypatch.setattr(provider, 'OpenAI', FakeClient)
    class Environment:
        async def exec(self, command, timeout_sec):
            return SimpleNamespace(stdout='COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n', stderr='', return_code=0)
    agent = PilotAgent(logs_dir=tmp_path, pilot_config=Path('configs/terminal-pilot-v1.json').resolve())
    context = AgentContext()
    await agent.run('public instruction', Environment(), context)
    worker = json.loads((tmp_path / 'worker.json').read_text())
    assert worker['exit_status'] == 'Submitted'
    assert worker['usage']['calls'] == 1
    assert worker['usage']['actual_tokens'] == 10
    assert context.n_input_tokens == 8
    assert len(list((tmp_path / 'requests').glob('*.json'))) == 1
    assert len(list((tmp_path / 'usage-responses').glob('*.json'))) == 1
    assert 'public instruction' in (tmp_path / 'trajectory.json').read_text()
    assert 'unit-test-placeholder' not in ''.join(p.read_text() for p in tmp_path.rglob('*.json'))
