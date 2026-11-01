"""Prepare/test DGM; paid execution requires an explicit live config and flag."""
import argparse
import datetime
import json
from pathlib import Path

from acl_frameworks.common import ROOT, read, sha, verify as verify_existing
from acl_frameworks.context import export_baseline
from acl_rsi.settings import load_settings, write_json
from .adapter import DGMAdapter
from .native import LOCK, verify

IDS = ['django__django-11790', 'django__django-11815']


def smoke(work):
    """Actual native main, with explicitly synthetic callbacks and no API/Docker."""
    def propose(context):
        p = context['candidate_harness'] / 'agent.py'
        p.write_text(p.read_text()+'\n# Offline DGM archive fixture.\n')
    calls = []
    def evaluate(name, harness, ids):
        calls.append(name)
        return {iid: {'score': int(name == 'initial' and iid == IDS[1]),
            'empty_patch': False, 'messages': [], 'patch': 'offline fixture only'} for iid in ids}
    if (Path(work) / 'smoke-results.json').exists():
        raise ValueError('Use a fresh offline fixture workspace')
    adapter = DGMAdapter(work, IDS, propose, evaluate, evidence_scope='synthetic_contract_fixture')
    result = adapter.run(2)
    assert result['archive'] == ['initial', 'node_0000', 'node_0001']
    # The lower-scoring children are retained: preserve open-ended archive,
    # never silently turn DGM into greedy incumbent improvement.
    assert read(adapter.archive / 'node_0000/metadata.json')['overall_performance']['accuracy_score'] == 0
    report = {'status': 'offline_native_outer_passed', 'synthetic_fixture_only': True,
        'native_generations': 2, 'archive': result['archive'], 'callback_calls': calls,
        'lower_scoring_valid_candidate_retained': True, 'model_calls': 0,
        'benchmark_executions': 0, 'benchmark_accuracy': None,
        'dgm_revision': read(LOCK)['revision']}
    write_json(Path(work) / 'smoke-results.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'prepare', 'smoke', 'run'])
    parser.add_argument('--work', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    verify()
    revisions = {name: verify_existing(name)[0]['revision'] for name in ('harnessfix', 'meta-harness', 'gepa', 'rrsi')}
    revisions['dgm'] = read(LOCK)['revision']
    if args.command == 'check':
        print(json.dumps({'status': 'five_pinned_sources_verified', 'revisions': revisions,
                          'dgm_live_validated': False, 'new_model_calls': 0}, indent=2))
        return
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    work = (args.work or ROOT / 'experiments/runs/dgm-integration' / stamp).resolve()
    runtime_lock = {'revisions': revisions, 'dgm_lock_sha256': sha(LOCK),
        'adapter_sha256': {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / 'acl_dgm').glob('*.py')},
        'baseline_manifest_sha256': sha(ROOT / 'work/verified-mini-50-baseline-v2/repo/source_manifest.json'),
        'initial_harness': {f: sha(ROOT / 'work/verified-mini-50-baseline-v2/repo/domains/swe/harness' / f)
                            for f in ('agent.py', 'swebench.yaml', 'LICENSE.md')},
        'dataset_sha256': sha(ROOT / 'benchmarks/datasets/swe-bench-verified-mini/test.json')}
    if (work / 'integration-lock.json').exists() and read(work / 'integration-lock.json') != runtime_lock:
        raise ValueError('Existing DGM source/runtime lock differs; preserve this run and use a new workspace')
    if args.command == 'run':
        if not args.live or not args.config:
            parser.error('Paid execution requires both --live and an explicit budgeted --config')
        source = read(args.config)
        if source.get('model') != 'deepseek-flash' or source.get('api_base') != 'https://api.deepseek.com' or source.get('thinking'):
            raise ValueError('Fixed DeepSeek Flash provider required')
        if not all(source['search'].get(k, 0) > 0 for k in ('max_calls', 'max_tokens')):
            raise ValueError('Integration template has zero paid budget; freeze a new experimental configuration')
        if source['target'] != read(ROOT / 'configs/mini50-baseline.json')['target']:
            raise ValueError('Current DGM adapter fixes the original Mini50 target execution budget')
        source['workspace'] = str(work)
        path = work / 'config.json'
        if path.exists() and read(path) != source:
            raise ValueError('Existing run configuration differs')
        write_json(path, source)
        cfg = load_settings(path)
        if cfg['model'] != 'deepseek-flash' or cfg['api_base'] != 'https://api.deepseek.com':
            raise ValueError('Environment overrides the fixed provider')
        write_json(work / 'integration-lock.json', runtime_lock)
        from .runtime import DGMProposer, SWEEvaluator
        adapter = DGMAdapter(work, cfg['evolve_ids'], DGMProposer(cfg, work, enabled=True), SWEEvaluator(cfg, work))
        report = {'status': 'native_run_completed', 'state': adapter.run(1),
                  'scope': 'DGM-adapted; inspect valid children before claiming a scored candidate'}
    elif args.command == 'prepare':
        cfg = load_settings(ROOT / 'configs/dgm-mini-pilot.template.json')
        from .runtime import SWEEvaluator
        adapter = DGMAdapter(work, IDS, None, SWEEvaluator(cfg, work))
        adapter.prepare()
        adapter.publish()
        report = {'status': 'real_historical_baseline_prepared', 'new_model_calls': 0,
                  'dgm_live_validated': False, 'task_ids': IDS}
    else:
        report = smoke(work)
    write_json(work / 'integration-lock.json', runtime_lock)
    print(json.dumps({'work': str(work), **report}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
