"""Read-only live status, including in-flight request reservations."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
workspace = root / 'work/terminal-pilot-v1'
cfg = json.loads((root / 'configs/terminal-pilot-v1.json').read_text())
rows = []
for task in cfg['tasks']:
    trial = workspace / 'trials' / task['id']
    ledger_path = trial / 'agent/usage.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'requests': []}
    result = json.loads((trial / 'result.json').read_text()) if (trial / 'result.json').exists() else None
    worker = json.loads((trial / 'agent/worker.json').read_text()) if (trial / 'agent/worker.json').exists() else None
    requests = ledger['requests']
    rows.append({'id': task['id'], 'state': 'done' if result else 'grading' if worker else 'running' if requests else 'setup' if trial.exists() else 'pending',
        'calls': len(requests), 'completed_calls': sum(r['status'] == 'completed' for r in requests),
        'tokens': sum(r.get('usage', {}).get('total_tokens', 0) for r in requests),
        'reward': (result.get('verifier_result') or {}).get('rewards') if result else None,
        'stop': worker.get('exit_status') if worker else None,
        'error': (result.get('exception_info') or {}).get('exception_type') if result else None})
print(json.dumps({'tasks': rows, 'calls': sum(r['calls'] for r in rows), 'tokens': sum(r['tokens'] for r in rows),
    'completed_tasks': sum(r['state'] == 'done' for r in rows),
    'passed': sum((r['reward'] or {}).get('reward') == 1 for r in rows)}, indent=2))
