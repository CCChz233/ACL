#!/usr/bin/env python3
"""Run bounded, offline checks of pinned official RSI frameworks.

Uses the existing Terminal environment without installing/upgrading packages.
Native optimization tests use mocked LMs, not DeepSeek or benchmark execution.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/rsi-framework-selection'
PYTHON = ROOT / '.venv-terminal/bin/python'

GUARD = '''
import socket, sys
def deny_network(*args, **kwargs):
    raise RuntimeError("Network disabled for offline framework smoke checks")
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network
'''


def check(name, cwd, paths, code):
    env = {k: v for k, v in os.environ.items()
           if not any(s in k.upper() for s in ('API_KEY', 'ACCESS_TOKEN', 'AUTH_TOKEN', 'SECRET'))}
    env.update({'VIRTUAL_ENV': str(PYTHON.parent.parent),
                'PATH': str(PYTHON.parent) + os.pathsep + env['PATH'],
                'UV_CACHE_DIR': str(WORK / 'uv-cache'),
                'PYTHONPATH': os.pathsep.join(str(p) for p in paths),
                'PYTHON_DOTENV_DISABLED': '1', 'RECORD_TESTS': 'false',
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'HF_HUB_OFFLINE': '1',
                'HF_DATASETS_OFFLINE': '1', 'WANDB_DISABLED': 'true',
                'LITELLM_LOCAL_MODEL_COST_MAP': 'True'})
    # Existing packages take precedence; only missing imports use this overlay.
    overlay = f"\nsys.path.append({str(WORK / 'extra-dependencies')!r})\n"
    command = [shutil.which('uv'), 'run', '--active', '--no-project',
               '--no-env-file', '--offline', 'python', '-c', GUARD + overlay + code]
    start = datetime.datetime.now(datetime.timezone.utc)
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                text=True, timeout=55)
        output = result.stdout + result.stderr
        status = 'passed' if result.returncode == 0 else 'failed'
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        output = str(exc)
        status, exit_code = 'timeout', None
    log = WORK / (name + '.smoke.log')
    log.write_text(output)
    return {'name': name, 'status': status, 'exit_code': exit_code,
            'seconds': (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds(),
            'log': str(log.relative_to(ROOT)),
            'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / 'docs/rsi_frameworks.sources.lock.json').read_text())
    for item in lock['cloned_frameworks']:
        path = ROOT / item['local_path']
        revision = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != item['revision']:
            raise ValueError(f"Pinned revision changed: {item['name']}")
        if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no'], text=True):
            raise ValueError(f"Upstream source changed: {item['name']}")
    g = ROOT / 'repos/gepa'
    m = ROOT / 'repos/meta-harness/reference_examples'
    d = ROOT / 'repos/dgm'
    a = ROOT / 'repos/ADAS'
    h = ROOT / 'repos/harness2'
    demo_root = WORK / 'harness2-demo-runs' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    checks = [
        check('gepa-native-optimization', g, [g / 'src'], '''
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider',
    'tests/test_optimize.py', 'tests/test_candidate_selector.py',
    'tests/test_acceptance_criterion.py']))
'''),
        check('meta-harness-history-contracts', m / 'text_classification',
              [m, m / 'text_classification'], '''
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', 'tests/test_evolution_contracts.py']))
'''),
        check('meta-harness-terminal-cli', m / 'terminal_bench_2',
              [m / 'terminal_bench_2'], '''
import runpy
sys.argv = ['meta_harness.py', '--help']
runpy.run_path('meta_harness.py', run_name='__main__')
'''),
        check('dgm-archive', d, [d], '''
import json, logging, tempfile
from pathlib import Path
from utils.evo_utils import load_dgm_metadata, is_compiled_self_improve
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'archive.jsonl'
    records = [{'generation': 0, 'archive': ['initial']},
               {'generation': 1, 'archive': ['initial', 'candidate']}]
    path.write_text('\\n'.join(json.dumps(r) for r in records))
    assert load_dgm_metadata(path, last_only=True) == records[-1]
    metadata = {'overall_performance': {'accuracy_score': .5,
        'total_unresolved_ids': ['a'], 'total_resolved_ids': ['b'],
        'total_emptypatch_ids': [], 'total_submitted_instances': 2}}
    assert is_compiled_self_improve(metadata, [2], logging.getLogger('offline'))
print('Native archive read and candidate validity checks passed; zero API requests.')
'''),
        check('dgm-deepseek-client', d, [d], '''
import os
os.environ['DEEPSEEK_API_KEY'] = 'offline-placeholder-never-sent'
from llm import create_client
client, model = create_client('deepseek-flash')
assert model == 'deepseek-flash' and str(client.base_url).startswith('https://api.deepseek.com')
client.close()
print('DeepSeek client construction passed; zero API requests.')
'''),
        check('adas-archive-and-proposal-context', a, [a / '_mgsm'], '''
from mgsm_prompt import get_init_archive, get_prompt, get_reflexion_prompt
archive = get_init_archive()
assert len(archive) >= 2 and all('code' in entry for entry in archive)
system, prompt = get_prompt(archive)
assert '[ARCHIVE]' not in prompt and archive[0]['name'] in prompt
assert len(get_reflexion_prompt(archive[0])) == 2
for entry in archive:
    compile(entry['code'], '<ADAS shipped candidate>', 'exec')
print(f'Native archive ({len(archive)} seeds), proposal/reflection context and candidate syntax passed; no candidate code executed.')
'''),
        check('harness2-deterministic-demo', h, [h], f'''
from harness2.cli.demo import main
raise SystemExit(main(['--output', {str(demo_root)!r}, '--k', '2', '--mode', 'both']))
'''),
    ]
    report = {'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'kind': 'offline engineering checks; not benchmark performance',
              'model_api_calls': 0, 'model_tokens': 0, 'docker_tasks': 0,
              'existing_environment_changed': False,
              'extra_dependencies_directory': str((WORK / 'extra-dependencies').relative_to(ROOT)),
              'harness2_demo': str((demo_root / 'demo.json').relative_to(ROOT)), 'checks': checks,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (WORK / 'smoke-results.json').write_text(json.dumps(report, indent=2) + '\n')
    (ROOT / 'docs/rsi_frameworks_smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if all(c['status'] == 'passed' for c in checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
