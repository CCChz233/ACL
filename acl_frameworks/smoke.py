"""Offline native contract checks. Synthetic fixture rewards are never benchmark scores."""
import contextlib
import io
from pathlib import Path
import shutil

from acl_rsi.settings import write_json
from .common import ROOT, read, verify
from .context import export_baseline
from .harnessfix import compile_snapshot, isolated_plan, promotion_check
from .meta_harness import MetaHarnessAdapter


def run(work):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if (work / 'smoke-results.json').exists():
        raise ValueError('Use a fresh smoke workspace; preserve previous checks')
    ids = ['django__django-11790', 'django__django-11815']
    snapshot = work / 'harnessfix/optimizer'
    export_baseline(snapshot, ids)
    htir = compile_snapshot(snapshot)
    plan = isolated_plan(work / 'harnessfix', [ids[0]], [ids[1]])
    comparison = {'net_change': 1, 'target_metric_results': {'improved_metric_count': 1},
        'baseline_metrics': {'metrics': {'error_rate': 0, 'invalid_submission_rate': 0}},
        'current_metrics': {'metrics': {'error_rate': 0, 'invalid_submission_rate': 0}}}
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        accepted = promotion_check(work / 'harnessfix/promotion-positive', audit={'passed': True}, comparison=comparison)
        rejected = promotion_check(work / 'harnessfix/promotion-negative', audit={'passed': False}, comparison=comparison)
    assert accepted['promoted'] and not rejected['promoted']
    export_baseline(work / 'meta/optimizer', ids)
    attempts = []
    def proposer(prompt, iteration):
        attempts.append(iteration)
        name = f'fixture_{iteration}'
        target = work / 'meta/optimizer/candidates' / name / 'harness'
        shutil.copytree(work / 'meta/optimizer/harness', target)
        with (target / 'agent.py').open('a') as handle:
            handle.write('\n# Offline fixture only; no task execution.\n')
        return [{'name': name, 'hypothesis': 'offline controller fixture', 'changes': 'comment only'}]
    calls = []
    def evaluator(name, harness, task_ids):
        calls.append(name)
        return {iid: float(name != 'h0') for iid in task_ids}
    adapter = MetaHarnessAdapter(work / 'meta', ids, proposer, evaluator)
    with contextlib.redirect_stdout(log):
        frontier = adapter.run(1)
    assert frontier['_best']['agent'] == 'fixture_1' and calls == ['h0', 'fixture_1']
    (work / 'native-contracts.log').write_text(log.getvalue())
    report = {'status': 'passed', 'scope': 'offline native contract checks only',
        'harnessfix': {'native_htir_bundles': len(htir), 'native_pipeline_dry_run': plan['status'],
                       'native_promotion_accept_and_reject': True},
        'meta_harness': {'native_loop_and_frontier': True, 'evaluation_callback_calls': calls,
                         'synthetic_fixture_only': True},
        'model_calls': 0, 'benchmark_executions': 0, 'benchmark_accuracy': None,
        'upstream_clean': {name: verify(name)[0]['revision'] for name in ('harnessfix', 'meta-harness', 'gepa', 'rrsi')}}
    write_json(work / 'smoke-results.json', report)
    return report
