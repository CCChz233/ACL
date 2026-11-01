"""Saved end-to-end integration fixture; no models, Docker, or benchmark scores."""
from datetime import datetime, timezone
import json
from pathlib import Path
import yaml

from acl_rsi.settings import ROOT, write_json
from .adapter import TerminalAdapter
from .common import BASE_CONFIG, read
from .run import optimize


def fixture_trial(path, passed):
    (path / 'agent').mkdir(parents=True)
    (path / 'verifier').mkdir()
    write_json(path / 'result.json', {'verifier_result': {'rewards': {'reward': int(passed)}}})
    write_json(path / 'agent/worker.json', {'exit_status': 'Submitted', 'usage': {'calls': 0, 'actual_tokens': 0}})
    write_json(path / 'agent/trajectory.json', {'messages': [
        {'role': 'system', 'content': 'fixture'}, {'role': 'user', 'content': 'Public integration fixture'},
        {'role': 'user', 'content': 'Scripted observation; no model execution'}]})
    write_json(path / 'verifier/ctrf.json', {'results': {'summary': {'tests': 1},
        'tests': [{'name': 'private_fixture_test', 'status': 'passed' if passed else 'failed'}]}})


def run():
    directory = ROOT / 'work/gepa-integration-smoke'
    work = directory / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    work.mkdir(parents=True)
    base = read(BASE_CONFIG)
    cfg = {'task_ids': ['fixture-a', 'fixture-b'], 'gepa': {'seed': 0}}
    baseline = work / 'fixture-baseline'
    fixture_trial(baseline / 'trials/fixture-a', False)
    fixture_trial(baseline / 'trials/fixture-b', True)
    executions, reflections = [], []
    def executor(task_id, data, candidate_folder):
        executions.append(task_id)
        fixture_trial(candidate_folder / 'trials' / task_id, True)
    adapter = TerminalAdapter(cfg, base, work, executor=executor, baseline_work=baseline)
    def reflection(prompt):
        reflections.append(prompt)
        assert 'private_fixture_test' not in prompt
        data = yaml.safe_load(adapter.seed['terminal.yaml'])
        data['agent']['system_template'] += 'Scripted integration fixture only.\n'
        return '```yaml\n' + yaml.safe_dump(data, sort_keys=False) + '\n```'
    result = optimize(cfg, base, work, adapter, reflection)
    adapter.evaluate([{'task_id': i} for i in cfg['task_ids']], result.best_candidate, capture_traces=True)
    assert len(reflections) == 1 and len(executions) == 2 and result.num_candidates == 2
    report = {'status': 'passed', 'kind': 'native GEPA + adapter with scripted LM and grading fixtures',
              'model_api_calls': 0, 'model_tokens': 0, 'docker_tasks': 0,
              'scripted_reflection_calls': len(reflections), 'fresh_fixture_executions': len(executions),
              'native_metric_count_including_seed_import': result.total_metric_calls,
              'duplicate_fixture_executions_after_cache_check': 0,
              'real_benchmark_accuracy': None, 'work': str(work.relative_to(ROOT))}
    write_json(work / 'integration-report.json', report)
    write_json(directory / 'latest.json', report)
    return report
