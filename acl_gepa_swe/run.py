import argparse
import fcntl
import json
from pathlib import Path

from acl_gepa.reflection import DeepSeekReflection
from acl_rsi.settings import write_json
from acl_terminal_rsi.common import read
from .adapter import SWEAdapter, gepa
from .common import baseline_trial, prepare
from .feedback import EvaluationUnavailable, record

REFLECTION_TEMPLATE = '''Improve this reusable mini-SWE-agent SWE-bench YAML harness.
Only agent.system_template, agent.instance_template, model.observation_template and
model.format_error_template may change. Preserve ALL other keys and values exactly,
including budgets, environment and model settings. The external model is fixed to
DeepSeek Flash; YAML model_name is an unused original placeholder. Keep {{task}}
interpolation, native bash tools, and the exact standalone submission command:
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt
Use a coherent generic improvement supported by observed interaction failures.
Treat successful traces as regression evidence. Distinguish hypotheses from facts.
Never encode task identifiers, task-specific source paths, answers, patches, test
identities, host files, credentials, private grading data, template calls or introspection.
Do not change agent.py. Do not add keys or insert task-specific algorithms.
Current complete YAML:
<curr_param>
Public interaction excerpts and external binary results (8 failures and 3 successes):
<side_info>
Return only the complete improved YAML in one fenced code block, without other prose.
'''


def optimize(cfg, work, adapter, reflection):
    result = gepa.optimize(seed_candidate=adapter.seed,
        trainset=[{'task_id': i} for i in cfg['evolve_ids']], valset=None,
        adapter=adapter, reflection_lm=reflection, reflection_prompt_template=REFLECTION_TEMPLATE,
        reflection_minibatch_size=len(cfg['evolve_ids']), skip_perfect_score=False,
        candidate_selection_strategy='pareto', module_selector='all', use_merge=False,
        max_metric_calls=2 * len(cfg['evolve_ids']), stop_callbacks=lambda state: state.i >= 0,
        run_dir=str(work / 'native-gepa'), cache_evaluation=True, write_agent_state=False,
        seed=cfg['gepa']['seed'], raise_on_exception=True, display_progress_bar=False)
    write_json(work / 'gepa-result.json', result.to_dict())
    return result


def ledger(paths):
    rows = []
    for path in paths:
        if path.exists():
            rows.extend(read(path)['requests'])
    return {'calls': len(rows), 'completed_calls': sum(r['status'] == 'completed' for r in rows),
            'actual_tokens': sum(r.get('usage', {}).get('total_tokens', 0) for r in rows),
            'charged_tokens': sum(r['charged_tokens'] for r in rows),
            'api_seconds': sum(r.get('api_seconds', 0) for r in rows),
            'prompt_tokens': sum(r.get('usage', {}).get('prompt_tokens', 0) for r in rows),
            'completion_tokens': sum(r.get('usage', {}).get('completion_tokens', 0) for r in rows)}


def summarize(cfg, work, instances):
    identity = work / 'candidate-identity.json'
    cid = read(identity)['candidate_id'] if identity.exists() else None
    rows = []
    for iid in cfg['evolve_ids']:
        b = record(baseline_trial(iid), iid, instances[iid], trace=False)
        c, state, reason = None, 'pending', None
        if cid:
            trial = work / 'candidates' / cid / 'trials' / iid
            if (trial / 'grade.json').exists():
                try:
                    c = record(trial, iid, instances[iid], trace=False)
                    state = 'valid'
                except EvaluationUnavailable as exc:
                    state, reason = 'invalid', str(exc)
            elif (trial / 'worker-attempt.json').exists():
                state = 'running_or_incomplete'
        rows.append({'task_id': iid, 'baseline': b['score'], 'candidate': c['score'] if c else None,
                     'state': state, 'invalid_reason': reason,
                     'stop': c['stop'] if c else None, 'usage': c['usage'] if c else None})
    complete = all(r['state'] == 'valid' for r in rows)
    n_valid = sum(r['state'] == 'valid' for r in rows)
    n_passed = sum(r['candidate'] == 1 for r in rows)
    b_passed = sum(r['baseline'] == 1 for r in rows)
    targets = list((work / 'candidates' / cid / 'trials').glob('*/usage.json')) if cid else []
    report = {'status': 'completed' if complete else 'not_fully_evaluated',
              'total': len(rows), 'n_valid': n_valid, 'resolved_so_far': n_passed,
              'baseline_passed': b_passed, 'baseline_accuracy': b_passed / len(rows),
              'candidate_passed': n_passed if complete else None,
              'candidate_accuracy': n_passed / len(rows) if complete else None,
              'newly_resolved': [r['task_id'] for r in rows if r['baseline'] == 0 and r['candidate'] == 1],
              'regressions': [r['task_id'] for r in rows if r['baseline'] == 1 and r['candidate'] == 0],
              'candidate_id': cid, 'target_usage': ledger(targets),
              'search_usage': ledger([work / 'search_usage.json']),
              'selection': ('candidate' if n_passed > b_passed else 'original') if complete else 'undetermined_keep_original',
              'scope': 'same50 development comparison; one prompt-only candidate; no heldout or framework-ranking claim',
              'tasks': rows}
    write_json(work / 'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'preflight', 'run', 'resume', 'summary'))
    args = parser.parse_args()
    cfg, work, instances = prepare()
    if args.command in ('prepare', 'summary'):
        report = summarize(cfg, work, instances)
        print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}, indent=2))
        return
    from .executor import SWEExecutor
    executor = SWEExecutor(cfg, work, instances)
    if args.command == 'preflight':
        print(json.dumps(executor.preflight(), indent=2))
        return
    with (work / 'controller.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (work / 'gepa-result.json').exists():
            print(json.dumps(summarize(cfg, work, instances), indent=2))
            return
        if args.command == 'run' and (work / 'reflection-attempt.json').exists():
            raise RuntimeError('Use resume to reuse the saved proposal')
        executor.preflight()
        write_json(work / 'controller.json', {'status': 'running'})
        try:
            adapter = SWEAdapter(cfg, work, instances, executor)
            optimize(cfg, work, adapter, DeepSeekReflection(cfg, work))
            report = summarize(cfg, work, instances)
            write_json(work / 'controller.json', {'status': report['status']})
            print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}, indent=2))
        except BaseException as exc:
            summarize(cfg, work, instances)
            write_json(work / 'controller.json', {'status': 'interrupted', 'error_type': type(exc).__name__,
                       'automatic_paid_retry': False})
            raise


if __name__ == '__main__':
    main()
