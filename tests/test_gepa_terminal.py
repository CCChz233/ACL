import json
from pathlib import Path

import pytest
import yaml

from acl_gepa.adapter import TerminalAdapter
from acl_gepa.common import BASE_CONFIG, candidate_id, read, seed_candidate, validate_candidate
from acl_gepa.feedback import EvaluationUnavailable, grade
from acl_gepa.reflection import DeepSeekReflection
from acl_gepa.run import optimize


def write_trial(path, reward, *, ctrf=True):
    (path / 'agent').mkdir(parents=True, exist_ok=True)
    (path / 'verifier').mkdir(exist_ok=True)
    (path / 'result.json').write_text(json.dumps({'verifier_result': {'rewards': {'reward': reward}}}))
    (path / 'agent/worker.json').write_text(json.dumps({'exit_status': 'Submitted', 'usage': {'calls': 1, 'actual_tokens': 20}}))
    (path / 'agent/trajectory.json').write_text(json.dumps({'messages': [
        {'role': 'system', 'content': 'initial'}, {'role': 'user', 'content': 'PUBLIC REQUIREMENT'},
        {'role': 'assistant', 'content': 'I will inspect output', 'extra': {'actions': [{'command': 'ls /app'}]}},
        {'role': 'user', 'content': 'PUBLIC OBSERVATION'}]}))
    (path / 'verifier/test-stdout.txt').write_text('SECRET_EXPECTED_8675309')
    if ctrf:
        (path / 'verifier/ctrf.json').write_text(json.dumps({'results': {'summary': {'tests': 1},
            'tests': [{'name': 'SECRET_PRIVATE_TEST_NAME', 'status': 'passed' if reward else 'failed'}]}}))


def changed(seed, suffix='Scripted fixture policy.'):
    data = yaml.safe_load(seed['terminal.yaml'])
    data['agent']['system_template'] += suffix + '\n'
    return {'terminal.yaml': yaml.safe_dump(data, sort_keys=False)}


@pytest.fixture
def setup(tmp_path):
    base = read(BASE_CONFIG)
    cfg = {'task_ids': ['task-a', 'task-b'], 'gepa': {'seed': 0}}
    baseline = tmp_path / 'baseline'
    write_trial(baseline / 'trials/task-a', 0)
    write_trial(baseline / 'trials/task-b', 1)
    work = tmp_path / 'gepa'
    work.mkdir()
    return cfg, base, baseline, work


def test_native_gepa_search_uses_real_adapter_cache_and_private_feedback_boundary(setup):
    cfg, base, baseline, work = setup
    executions, reflections = [], []
    def execute(task_id, data, folder):
        executions.append(task_id)
        write_trial(folder / 'trials' / task_id, 1)
    adapter = TerminalAdapter(cfg, base, work, executor=execute, baseline_work=baseline)
    updated = yaml.safe_load(adapter.seed['terminal.yaml'])
    updated['agent']['system_template'] += 'Inspect task artifacts before submitting.\n'
    proposal = yaml.safe_dump(updated, sort_keys=False)
    def reflection(prompt):
        reflections.append(prompt)
        assert 'PUBLIC REQUIREMENT' in prompt and 'PUBLIC OBSERVATION' in prompt
        assert 'SECRET_EXPECTED_8675309' not in prompt and 'SECRET_PRIVATE_TEST_NAME' not in prompt
        return '```yaml\n' + proposal + '\n```'
    result = optimize(cfg, base, work, adapter, reflection)
    assert result.best_score == 1 and result.num_candidates == 2
    assert len(reflections) == 1 and sorted(executions) == cfg['task_ids']
    # Native GEPA counts its seed score import; fresh executions remain exactly two.
    assert result.total_metric_calls == 4
    adapter.evaluate([{'task_id': i} for i in cfg['task_ids']], result.best_candidate, capture_traces=True)
    assert len(executions) == 2
    assert 'SECRET' not in (work / 'reflection-feedback.json').read_text()
    assert (work / 'gepa-result.json').exists()


def test_invalid_grader_aborts_without_fake_zero_or_automatic_retry(setup):
    cfg, base, baseline, work = setup
    calls = []
    def execute(task_id, data, folder):
        calls.append(task_id)
        write_trial(folder / 'trials' / task_id, 0, ctrf=False)
    adapter = TerminalAdapter(cfg, base, work, executor=execute, baseline_work=baseline)
    candidate = changed(adapter.seed)
    with pytest.raises(EvaluationUnavailable, match='missing_official_test_record'):
        adapter.evaluate([{'task_id': 'task-a'}], candidate)
    with pytest.raises(EvaluationUnavailable):
        adapter.evaluate([{'task_id': 'task-a'}], candidate)
    assert calls == ['task-a']
    report = read(work / 'candidates' / candidate_id(candidate) / 'evaluation-invalid.json')
    assert report['candidate_score'] is None
    # Real test failures remain valid method outcomes.
    assert grade(baseline / 'trials/task-a', baseline / 'trials/task-a') == 0


def test_immutable_surfaces_and_one_candidate_limit(setup):
    cfg, base, baseline, work = setup
    seed = seed_candidate(base)
    path = work / 'candidate.yaml'
    bad = yaml.safe_load(seed['terminal.yaml'])
    bad['target'] = {'max_calls': 999}
    with pytest.raises(ValueError):
        validate_candidate({'terminal.yaml': yaml.safe_dump(bad)}, path, cfg['task_ids'])
    bad = yaml.safe_load(seed['terminal.yaml'])
    bad['agent']['instance_template'] = '{{task}}'
    with pytest.raises(ValueError, match='Completion marker'):
        validate_candidate({'terminal.yaml': yaml.safe_dump(bad)}, path, cfg['task_ids'])
    adapter = TerminalAdapter(cfg, base, work, baseline_work=baseline)
    first = changed(seed, 'First scripted fixture policy.')
    second = changed(seed, 'Second scripted fixture policy.')
    with pytest.raises(EvaluationUnavailable):
        adapter.evaluate([{'task_id': 'task-a'}], first)
    with pytest.raises(ValueError, match='cap'):
        adapter.evaluate([{'task_id': 'task-a'}], second)


def test_reflection_preserves_payload_response_usage_and_resume_does_not_resample(tmp_path, monkeypatch):
    from openai.types.chat import ChatCompletion
    from acl_rsi.deepseek import DeepSeekClient
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'offline-key-never-sent')
    cfg = {'api_base': 'https://api.deepseek.com', 'model': 'deepseek-flash', 'thinking': False,
           'search': {'max_calls': 80, 'max_tokens': 1000000, 'max_output_tokens': 4096}}
    calls = []
    def factory(cfg, ledger, role, limits):
        client = DeepSeekClient(cfg, ledger, role, limits)
        def create(**payload):
            calls.append(payload)
            return ChatCompletion.model_validate({'id': 'offline-response-1', 'created': 0,
                'object': 'chat.completion', 'model': 'deepseek-flash',
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '```yaml\nfixture\n```'}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
        client.client.chat.completions.create = create
        return client
    reflection = DeepSeekReflection(cfg, tmp_path, factory)
    assert reflection('public prompt') == reflection('public prompt')
    assert len(calls) == 1 and calls[0]['extra_body']['thinking']['type'] == 'disabled'
    state = read(tmp_path / 'search_usage.json')
    row = state['requests'][0]
    assert row['usage']['total_tokens'] == 15 and row['api_seconds'] >= 0
    assert (tmp_path / 'search_requests' / (row['id'] + '.json')).exists()
    assert (tmp_path / 'search_usage-responses' / (row['id'] + '.json')).exists()
    with pytest.raises(RuntimeError, match='context changed'):
        reflection('changed context')
    assert 'offline-key-never-sent' not in ''.join(p.read_text() for p in tmp_path.rglob('*.json'))


def test_executor_image_mismatch_stops_before_model_and_preflight_inventory_is_frozen(tmp_path, monkeypatch):
    import subprocess
    import acl_gepa.terminal as terminal
    base = read(BASE_CONFIG)
    task = base['tasks'][0]
    executor = terminal.TerminalExecutor({'task_ids': [task['id']]}, base, tmp_path)
    commands = []
    def docker(*args, **kwargs):
        commands.append(args)
        output = 'sha256:original\n' if args[:2] == ('image', 'ls') else json.dumps([{'Id': 'sha256:wrong', 'Architecture': 'amd64'}])
        return subprocess.CompletedProcess(args, 0, output, '')
    monkeypatch.setattr(terminal, 'docker', docker)
    monkeypatch.setattr(executor, 'expected_image', lambda _: 'sha256:expected')
    assert executor.preflight()['status'] == 'blocked_before_model_call'
    assert read(tmp_path / 'preexisting-images.json') == ['sha256:original']
    assert all(cmd[:1] != ('pull',) for cmd in commands)
    assert not (tmp_path / 'trials').exists()


def test_disk_guard_checks_space_again_after_download(tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    import acl_gepa.terminal as terminal
    base = read(BASE_CONFIG)
    task = base['tasks'][0]
    executor = terminal.TerminalExecutor({'task_ids': [task['id']]}, base, tmp_path)
    free = iter([5 * 2**30, 3 * 2**30])
    monkeypatch.setattr(terminal.shutil, 'disk_usage', lambda _: SimpleNamespace(free=next(free)))
    monkeypatch.setattr(terminal, 'docker', lambda *args, **kwargs:
        subprocess.CompletedProcess(args, 0, json.dumps([{'Id': 'sha256:expected', 'Architecture': 'amd64'}]), ''))
    monkeypatch.setattr(executor, 'expected_image', lambda _: 'sha256:expected')
    with pytest.raises(EvaluationUnavailable, match='after_image_pull'):
        executor.ensure_image(task['id'])


def test_partial_native_resume_keeps_completed_trial_and_original_proposal(setup):
    cfg, base, baseline, work = setup
    attempted, reflection_contexts = [], []
    broken = True
    def execute(task_id, data, folder):
        attempted.append(task_id)
        if task_id == 'task-b' and broken:
            raise EvaluationUnavailable('image_pull_failed_before_model')
        write_trial(folder / 'trials' / task_id, 1)
    adapter = TerminalAdapter(cfg, base, work, executor=execute, baseline_work=baseline)
    proposal = '```yaml\n' + changed(adapter.seed)['terminal.yaml'] + '\n```'
    def reflection(prompt):
        reflection_contexts.append(prompt)
        return proposal
    with pytest.raises(EvaluationUnavailable):
        optimize(cfg, base, work, adapter, reflection)
    first_completed = list((work / 'candidates').glob('*/trials/task-a/result.json'))
    assert len(first_completed) == 1
    before = first_completed[0].read_bytes()
    broken = False
    result = optimize(cfg, base, work, adapter, reflection)
    assert result.best_score == 1 and attempted.count('task-a') == 1
    # DeepSeekReflection separately guarantees this identical context is returned from its saved response.
    assert reflection_contexts[0] == reflection_contexts[1]
    assert first_completed[0].read_bytes() == before


def test_yaml_reformatting_reuses_baseline_instead_of_paid_resampling(setup):
    cfg, base, baseline, work = setup
    def forbidden_executor(*args):
        pytest.fail('Same executable policy must not be rerun')
    adapter = TerminalAdapter(cfg, base, work, executor=forbidden_executor, baseline_work=baseline)
    reformatted = {'terminal.yaml': yaml.safe_dump(yaml.safe_load(adapter.seed['terminal.yaml'])) + '\n# formatting only\n'}
    result = adapter.evaluate([{'task_id': i} for i in cfg['task_ids']], reformatted, capture_traces=True)
    assert result.scores == [0, 1] and result.num_metric_calls == 0
    assert not (work / 'candidate-identity.json').exists()


@pytest.mark.parametrize('valid_grade', [False, True])
def test_checkpoint_retained_only_for_invalid_grading_and_original_images_protected(tmp_path, monkeypatch, valid_grade):
    import asyncio
    import subprocess
    from types import SimpleNamespace
    from harbor.trial.trial import Trial
    import acl_gepa.terminal as terminal
    from acl_gepa.common import BASE_WORK
    base = read(BASE_CONFIG)
    task = base['tasks'][0]
    folder = tmp_path / 'candidate'
    folder.mkdir()
    commands = []
    def docker(*args, **kwargs):
        commands.append(args)
        output = 'sha256:original\n' if args[:2] == ('image', 'ls') else 'sha256:checkpoint\n'
        return subprocess.CompletedProcess(args, 0, output, '')
    monkeypatch.setattr(terminal, 'docker', docker)
    executor = terminal.TerminalExecutor({'model': 'deepseek-flash', 'task_ids': [task['id']]}, base, tmp_path)
    monkeypatch.setattr(executor, 'ensure_image', lambda _: {'Id': 'sha256:new-task', 'Architecture': 'amd64'})
    class FakeTrial:
        def add_hook(self, event, hook):
            self.hook = hook
        async def run(self):
            path = folder / 'trials' / task['id']
            write_trial(path, 0, ctrf=False)
            await self.hook(None)
            if valid_grade:
                reference = read(BASE_WORK / 'trials' / task['id'] / 'verifier/ctrf.json')
                for test in reference['results']['tests']:
                    test['status'] = 'failed'
                (path / 'verifier/ctrf.json').write_text(json.dumps(reference))
        @property
        def agent_environment(self):
            async def compose(args):
                return SimpleNamespace(stdout='fixture-container-id')
            return SimpleNamespace(_run_docker_compose_command=compose)
    async def create(config):
        assert config.agent.import_path == 'acl_terminal.agent:PilotAgent'
        assert config.environment.delete is True
        return FakeTrial()
    monkeypatch.setattr(Trial, 'create', create)
    if valid_grade:
        asyncio.run(executor.run_trial(task['id'], yaml.safe_load(seed_candidate(base)['terminal.yaml']), folder))
    else:
        with pytest.raises(EvaluationUnavailable):
            asyncio.run(executor.run_trial(task['id'], yaml.safe_load(seed_candidate(base)['terminal.yaml']), folder))
    record = read(folder / 'trials' / task['id'] / 'agent/checkpoint-retention.json')
    assert record['retained_for_invalid_trial'] is not valid_grade
    removed = [args[2] for args in commands if args[:2] == ('image', 'rm')]
    assert task['image'] in removed and 'sha256:original' not in removed
    assert (record['tag'] in removed) is valid_grade
