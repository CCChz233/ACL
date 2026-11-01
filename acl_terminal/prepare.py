import hashlib
import json
import tomllib
from pathlib import Path
import yaml
from acl_rsi.settings import ROOT, write_json

CATEGORIES = ['software-engineering', 'debugging', 'system-administration',
              'file-operations', 'data-processing', 'scientific-computing']
CONFIG = ROOT / 'configs/terminal-pilot-v1.json'


def prepare():
    tasks = ROOT / 'repos/terminal-bench-2-1/tasks'
    pool = []
    for path in sorted(tasks.iterdir()):
        if not (path / 'task.toml').is_file():
            continue
        data = tomllib.loads((path / 'task.toml').read_text())
        env = data['environment']
        if (env.get('gpus', 0) == 0 and env.get('cpus', 1) <= 2
                and env.get('memory_mb', 2048) <= 4096
                and data['agent']['timeout_sec'] <= 1800
                and not data.get('metadata', {}).get('custom_docker_compose')):
            pool.append((path, data))
    selected = []
    for category in CATEGORIES:
        eligible = [(p,d) for p,d in pool if d['metadata']['category'] == category]
        selected.extend(sorted(eligible, key=lambda row: hashlib.sha256(
            ('acl-terminal-pilot-v1:' + row[0].name).encode()).hexdigest())[:2])
    rows = []
    for path, data in selected:
        rows.append({'id': path.name, 'category': data['metadata']['category'],
                     'difficulty': data['metadata']['difficulty'],
                     'image': data['environment']['docker_image'],
                     'wall_seconds': min(int(data['agent']['timeout_sec']), 1200),
                     'official_agent_seconds': data['agent']['timeout_sec'],
                     'files': {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(path.rglob('*')) if p.is_file()}})
    original = yaml.safe_load((ROOT / 'repos/mini-swe-agent/src/minisweagent/config/benchmarks/swebench.yaml').read_text())
    cfg = {'purpose': 'terminal-bench-2.1-mini-deepseek-baseline-pilot',
           'benchmark_commit': '7131e4375048a0e408a8fb404b5f499d726b695b',
           'workspace': 'work/terminal-pilot-v1', 'api_base': 'https://api.deepseek.com',
           'model': 'deepseek-flash', 'thinking': False,
           'selection': '2/category sorted by SHA256(acl-terminal-pilot-v1:ID), metadata eligibility only',
           'tasks': rows, 'target': {'max_calls': 50, 'max_tokens': 1000000,
              'max_output_tokens': 4096, 'command_seconds': 60},
           'agent': {'system_template': original['agent']['system_template'],
                     'instance_template': '''<task>\n{{task}}\n</task>\n
Solve this task in the provided Linux environment using the bash tool.
For each response, explain your reasoning briefly and make at least one bash tool call.
Each command runs in a fresh subshell. Use explicit paths or cd as needed.
You may inspect and modify files, install tools, and run services as required by the task.
Verify your work before finishing. When complete, issue this command:
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
The final environment state is your submission. You cannot continue after finishing.
'''}, 'templates': {k: original['model'][k] for k in ('observation_template', 'format_error_template')},
           'min_free_bytes': 4 * 1024**3, 'retries': 0, 'rrsi_rounds': 0,
           'platform': 'linux/amd64', 'seed': None,
           'sampling': 'provider defaults; thinking disabled; max_tokens=4096'}
    if CONFIG.exists():
        if json.loads(CONFIG.read_text()) != cfg:
            raise RuntimeError('Frozen config differs; use a new version')
    else:
        write_json(CONFIG, cfg)
    print(json.dumps({'config': str(CONFIG), 'tasks': [r['id'] for r in rows]}, indent=2))

if __name__ == '__main__':
    prepare()
