import argparse
import fcntl
import json
from pathlib import Path

from acl_rsi.settings import ROOT, write_json
from .common import BASE_WORK, candidate_id, prepare, read, seed_candidate
from .adapter import TerminalAdapter, gepa
from .feedback import EvaluationUnavailable, public_record
from .reflection import DeepSeekReflection

REFLECTION_TEMPLATE = '''Improve this reusable mini-SWE-agent terminal harness YAML.
Only agent.system_template, agent.instance_template, templates.observation_template
and templates.format_error_template may change. Keep exactly those sections/keys,
the public {{task}} interpolation, and the existing completion marker semantics.
Preserve the mini execution loop, tools, model, budgets and task-independent behavior.
Use one coherent generic improvement mechanism supported by the traces. No task IDs,
task-specific paths/answers/algorithms, private tests, verifier access, host files,
credentials, extra YAML keys, Jinja calls or introspection. Avoid broad rewrites.
Original successes are regression evidence. Distinguish observed symptoms from hypotheses.
Current YAML:
<curr_param>
Public interaction excerpts and external binary feedback:
<side_info>
Return only the complete improved YAML in one fenced code block. No prose outside it.
'''


def optimize(cfg, base, work, adapter, reflection):
    # Full 12-task batches make the first integration candidate directly auditable.
    # valset=None shares GEPA's native evaluation cache with the development batch.
    result = gepa.optimize(seed_candidate=adapter.seed,
        trainset=[{'task_id': i} for i in cfg['task_ids']], valset=None,
        adapter=adapter, reflection_lm=reflection,
        reflection_prompt_template=REFLECTION_TEMPLATE,
        reflection_minibatch_size=len(cfg['task_ids']), skip_perfect_score=False,
        candidate_selection_strategy='pareto', module_selector='all',
        use_merge=False, max_metric_calls=2 * len(cfg['task_ids']),
        stop_callbacks=lambda state: state.i >= 0,
        run_dir=str(work / 'native-gepa'), cache_evaluation=True,
        write_agent_state=False, seed=cfg['gepa']['seed'],
        raise_on_exception=True, display_progress_bar=False)
    write_json(work / 'gepa-result.json', result.to_dict())
    return result


def summary(cfg, base, work):
    seed_id = candidate_id(seed_candidate(base))
    identity = work / 'candidate-identity.json'
    cid = read(identity)['candidate_id'] if identity.exists() else None
    rows = []
    for task_id in cfg['task_ids']:
        baseline = BASE_WORK / 'trials' / task_id
        b = public_record(baseline, baseline, task_id)
        c, state, reason = None, 'pending', None
        if cid:
            trial = work / 'candidates' / cid / 'trials' / task_id
            if (trial / 'result.json').exists():
                try:
                    c = public_record(trial, baseline, task_id)
                    state = 'valid'
                except EvaluationUnavailable as exc:
                    state, reason = 'invalid_evaluation', str(exc)
            elif trial.exists():
                state = 'incomplete_no_automatic_retry'
        rows.append({'task_id': task_id, 'baseline': b['score'], 'candidate': c['score'] if c else None,
                     'state': state, 'invalid_reason': reason})
    complete = all(r['state'] == 'valid' for r in rows)
    unchanged = cid is None and (work / 'gepa-result.json').exists()
    passed = sum(r['candidate'] == 1 for r in rows)
    baseline_passed = sum(r['baseline'] == 1 for r in rows)
    ledgers = [work / 'search_usage.json']
    if cid:
        ledgers.extend((work / 'candidates' / cid / 'trials').glob('*/agent/usage.json'))
    usage = []
    for path in ledgers:
        if path.exists():
            usage.extend(read(path)['requests'])
    report = {'status': 'completed' if complete else 'no_new_harness_proposed' if unchanged else 'not_fully_evaluated',
              'baseline_passed': baseline_passed, 'total': len(rows),
              'candidate_passed': passed if complete else None,
              'candidate_score': passed / len(rows) if complete else None,
              'selection': ('candidate' if passed > baseline_passed else 'original') if complete else 'undetermined_keep_original',
              'seed_candidate_id': seed_id, 'candidate_id': cid,
              'calls': len(usage), 'tokens': sum(r.get('usage', {}).get('total_tokens', 0) for r in usage),
              'charged_tokens': sum(r['charged_tokens'] for r in usage),
              'scope': 'same 12 development tasks; one new candidate; not heldout evidence', 'tasks': rows}
    write_json(work / 'summary.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'preflight', 'run', 'resume', 'summary', 'smoke'))
    parser.add_argument('--pull-first-image', action='store_true')
    args = parser.parse_args()
    if args.command == 'smoke':
        from .smoke import run
        print(json.dumps(run(), indent=2)); return
    cfg, base, work = prepare()
    if args.command == 'prepare':
        adapter = TerminalAdapter(cfg, base, work)
        batch = adapter.evaluate([{'task_id': i} for i in cfg['task_ids']], adapter.seed, capture_traces=True)
        print(json.dumps({'prepared': str(work), 'baseline_passed': sum(batch.scores),
                          'tasks': len(batch.scores), 'new_api_calls': 0})); return
    if args.command == 'summary':
        print(json.dumps(summary(cfg, base, work), indent=2)); return
    from .terminal import TerminalExecutor
    executor = TerminalExecutor(cfg, base, work)
    if args.command == 'preflight':
        print(json.dumps(executor.preflight(args.pull_first_image), indent=2)); return
    with (work / 'controller.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (work / 'gepa-result.json').exists():
            print(json.dumps(summary(cfg, base, work), indent=2)); return
        if args.command == 'run' and (work / 'reflection-attempt.json').exists():
            raise RuntimeError('Existing attempt: use resume; no new paid proposal')
        preflight = executor.preflight(pull_first=True)
        if preflight['status'] != 'ready_for_first_image_only':
            write_json(work / 'controller.json', preflight)
            print(json.dumps(preflight, indent=2)); return
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
        adapter = TerminalAdapter(cfg, base, work, executor=executor)
        write_json(work / 'controller.json', {'status': 'running'})
        try:
            optimize(cfg, base, work, adapter, DeepSeekReflection(cfg, work))
            report = summary(cfg, base, work)
            write_json(work / 'controller.json', {'status': report['status']})
            print(json.dumps(report, indent=2))
        except BaseException as exc:
            summary(cfg, base, work)
            write_json(work / 'controller.json', {'status': 'interrupted', 'error_type': type(exc).__name__,
                       'automatic_paid_retry': False})
            raise


if __name__ == '__main__':
    main()
