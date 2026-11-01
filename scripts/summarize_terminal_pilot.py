"""Aggregate official rewards and audit artifacts; never rerun agent or verifier."""
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT/'configs/terminal-pilot-v1.json').read_text())
work = ROOT/cfg['workspace']
rows = []
for task in cfg['tasks']:
    path = work/'trials'/task['id']
    if not (path/'result.json').exists():
        continue
    result = json.loads((path/'result.json').read_text())
    worker = json.loads((path/'agent/worker.json').read_text()) if (path/'agent/worker.json').exists() else {}
    ledger = json.loads((path/'agent/usage.json').read_text()) if (path/'agent/usage.json').exists() else {'requests':[]}
    calls = ledger['requests']
    completed = [r for r in calls if r['status']=='completed']
    test_path = path/'verifier/ctrf.json'
    tests = json.loads(test_path.read_text()).get('results',{}).get('tests',[]) if test_path.exists() else []
    trajectory_path = path/'agent/trajectory.json'
    messages = json.loads(trajectory_path.read_text()).get('messages',[]) if trajectory_path.exists() else []
    responses = [json.loads(p.read_text()) for p in (path/'agent/usage-responses').glob('*.json')]
    reward = ((result.get('verifier_result') or {}).get('rewards') or {}).get('reward')
    rows.append({'id':task['id'], 'category':task['category'], 'reward':reward,
        'exit_status':worker.get('exit_status'), 'exception':result.get('exception_info'),
        'calls':len(calls), 'completed_calls':len(completed),
        'input_tokens':sum(r['usage'].get('prompt_tokens',0) for r in completed),
        'output_tokens':sum(r['usage'].get('completion_tokens',0) for r in completed),
        'total_tokens':sum(r['usage'].get('total_tokens',0) for r in completed),
        'cache_hit_tokens':sum(r['usage'].get('prompt_cache_hit_tokens',0) for r in completed),
        'cache_miss_tokens':sum(r['usage'].get('prompt_cache_miss_tokens',0) for r in completed),
        'api_seconds':sum(r.get('api_seconds',0) for r in calls), 'agent_seconds':worker.get('seconds'),
        'request_records':len(list((path/'agent/requests').glob('*.json'))),
        'response_records':len(list((path/'agent/usage-responses').glob('*.json'))),
        'latency_records':sum('api_seconds' in r for r in calls),
        'provider_models':dict(Counter(r.get('model') for r in responses)),
        'system_fingerprints':dict(Counter(r.get('system_fingerprint') for r in responses)),
        'tool_error_observations':sum(m.get('role')=='tool' and m.get('extra',{}).get('returncode',0)!=0 for m in messages),
        'failed_tests':[t.get('name') for t in tests if t.get('status') not in ('passed','skipped')],
        'passed_tests':sum(t.get('status')=='passed' for t in tests),
        'test_count':len(tests), 'trajectory':str((path/'agent/trajectory.json').relative_to(ROOT))})
by_category = defaultdict(lambda:{'n':0,'passed':0,'tokens':0})
for r in rows:
    group=by_category[r['category']]; group['n']+=1
    group['passed']+=r['reward']==1; group['tokens']+=r['total_tokens']
lock=json.loads((work/'runtime-lock.json').read_text())
report={'benchmark':'Terminal-Bench 2.1 operationally filtered 12-task pilot',
    'model':cfg['model'],'harness':'mini-SWE-agent 2.4.6 + frozen terminal adapter v1',
    'rrsi_rounds':0,'completed':len(rows),'planned':len(cfg['tasks']),
    'validly_graded':sum(r['reward'] is not None and r['exception'] is None for r in rows),
    'passed':sum(r['reward']==1 for r in rows),
    'score_on_planned':sum(r['reward']==1 for r in rows)/len(cfg['tasks']) if len(rows)==len(cfg['tasks']) else None,
    'score_on_completed':sum(r['reward']==1 for r in rows)/len(rows) if rows else None,
    'calls':sum(r['calls'] for r in rows),'tokens':sum(r['total_tokens'] for r in rows),
    'input_tokens':sum(r['input_tokens'] for r in rows),'output_tokens':sum(r['output_tokens'] for r in rows),
    'cache_hit_tokens':sum(r['cache_hit_tokens'] for r in rows),'cache_miss_tokens':sum(r['cache_miss_tokens'] for r in rows),
    'exit_status_counts':dict(Counter(r['exit_status'] for r in rows)),
    'passed_without_submission':sum(r['reward']==1 and r['exit_status']!='Submitted' for r in rows),
    'all_recorded_requests_have_payload':all(r['calls']==r['request_records'] for r in rows),
    'all_completed_calls_have_response':all(r['completed_calls']==r['response_records'] for r in rows),
    'all_recorded_calls_have_latency':all(r['calls']==r['latency_records'] for r in rows),
    'runtime_hashes_match':all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in lock.items()),
    'by_category':dict(by_category),'results':rows}
output=ROOT/'docs/terminal_pilot_results.json'
output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
# Verifier stdout can contain reference answers; never use it as model feedback.
feedback = [{'task_id':r['id'], 'reward':r['reward'], 'exit_status':r['exit_status'],
             'calls':r['calls'], 'total_tokens':r['total_tokens'], 'trajectory':r['trajectory']}
            for r in rows]
(work/'public-feedback.json').write_text(json.dumps(feedback,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('results','by_category')},indent=2))
