"""Freeze a challenging, repository-balanced ten-task development cohort from real history."""
import argparse
import json
from pathlib import Path

from acl_frameworks.common import ROOT, read, sha
from acl_gepa_swe.feedback import record
from acl_rsi.settings import write_json


def choose(rows):
    selected = []
    for repo in ('django/django', 'sphinx-doc/sphinx'):
        pool = [r for r in rows if r['repo'] == repo]
        used = set()
        def take(eligible, category, key):
            candidates = sorted([r for r in pool if r['task_id'] not in used and eligible(r)],
                                key=lambda r: (*key(r), r['task_id']))
            if not candidates:
                raise ValueError('Missing cohort stratum: '+repo+' '+category)
            row = dict(candidates[0], selection_category=category)
            used.add(row['task_id']); selected.append(row)
        take(lambda r: r['baseline_stop'] == 'LimitsExceeded' and r['scores'][0] == 0,
             'call_budget_failure', lambda r: (-r['baseline_tokens'],))
        take(lambda r: r['baseline_stop'] == 'BudgetExceeded' and r['scores'][0] == 0,
             'token_budget_failure', lambda r: (-r['baseline_tokens'],))
        persistent = any(r['scores'] == [0, 0, 0] and r['baseline_stop'] == 'Submitted' for r in pool)
        if persistent:
            take(lambda r: r['scores'] == [0, 0, 0] and r['baseline_stop'] == 'Submitted',
                 'persistent_submitted_failure', lambda r: (-r['baseline_tokens'],))
        else:
            take(lambda r: r['scores'][0] == 0 and sum(r['scores'][1:]) > 0 and r['baseline_stop'] == 'Submitted',
                 'historically_recoverable_failure', lambda r: (-sum(r['scores'][1:]), -r['baseline_tokens']))
        take(lambda r: r['scores'][0] == 0 and sum(r['scores'][1:]) > 0 and r['baseline_stop'] == 'Submitted',
             'historically_recoverable_failure', lambda r: (-sum(r['scores'][1:]), -r['baseline_tokens']))
        take(lambda r: r['scores'][0] == 1 and sum(r['scores'][1:]) < 2,
             'costly_fragile_success', lambda r: (-r['baseline_tokens'],))
    assert len(selected) == len({r['task_id'] for r in selected}) == 10
    assert sum(r['scores'][0] for r in selected) == 2
    return selected


def audit():
    dataset_path = ROOT / 'benchmarks/datasets/swe-bench-verified-mini/test.json'
    dataset = read(dataset_path)
    gepa = read(ROOT / 'work/gepa-mini50-v1/summary.json')['candidate_id']
    rows, hashes = [], {}
    for task in dataset:
        iid = task['instance_id']
        paths = [ROOT / 'work/verified-mini-50-baseline-v2/runs/swe/jobs/base' / iid / 'trial-0',
                 ROOT / 'work/verified-mini-50-round1-recovery/runs/swe/jobs/r0A' / iid / 'trial-0',
                 ROOT / 'work/gepa-mini50-v1/candidates' / gepa / 'trials' / iid]
        records = [record(p, iid, task, trace=False) for p in paths]
        for path in paths:
            files = [path / n for n in ('manifest.json', 'worker.json', 'grade.json', 'usage.json', 'patch.diff')]
            grade = read(path / 'grade.json')
            if grade.get('report_path'):
                files.append(Path(grade['report_path']))
            for file in files:
                hashes[str(file.resolve().relative_to(ROOT))] = sha(file)
        base = records[0]
        rows.append({'task_id': iid, 'repo': task['repo'],
            'public_issue_title': task['problem_statement'].splitlines()[0][:180],
            'scores': [int(r['score']) for r in records], 'baseline_stop': base['stop'],
            'baseline_calls': base['usage']['calls'], 'baseline_tokens': base['usage']['actual_tokens'],
            'baseline_nonempty_patch': bool((paths[0] / 'patch.diff').read_text().strip()),
            'evidence_trials': [str(p.resolve().relative_to(ROOT)) for p in paths]})
    assert len(rows) == len({r['task_id'] for r in rows}) == 50
    totals = [sum(r['scores'][k] for r in rows) for k in range(3)]
    assert totals == [31, 29, 25], totals
    return {'source_runs': ['H0', 'RRSI candidate', 'GEPA candidate'], 'valid_task_trials': 150,
        'full50_resolved': totals, 'dataset_sha256': sha(dataset_path),
        'source_file_sha256': hashes, 'all50': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Selection artifact already exists; do not overwrite the frozen cohort')
    evidence = audit()
    selected = choose(evidence['all50'])
    result = {'name': 'swe-mini-hard10-v1', 'scope': 'historically selected development cohort; not heldout',
        'policy': 'Five per repository: one call-limit failure, one token-limit failure, '
                  'one persistent submitted failure if available (otherwise recoverable), '
                  'one historically recoverable failure, one costly fragile success. '
                  'Rank by historical candidate successes where applicable, then H0 actual tokens; task ID breaks ties.',
        'selection_bias': 'Purposefully conditioned on past harness outcomes. Three harness runs are not independent repeated trials.',
        'selector_sha256': sha(Path(__file__)), 'task_ids': [r['task_id'] for r in selected],
        'historical_resolved': {name: sum(r['scores'][k] for r in selected)
            for k, name in enumerate(evidence['source_runs'])}, 'selected': selected, **evidence}
    write_json(output / 'selection.json', result)
    lines = ['# SWE Mini 困难十题开发集', '',
        '根据 H0、RRSI 候选、GEPA 候选的原始记录选题；150 份试跑记录均通过有效性检查，'
        '全 50 题合计重算为 31、29、25 道通过。历史三套 Harness 结果不是独立随机重复。', '',
        '每仓库 5 题；共 8 道基线失败、2 道高成本且曾回归的成功题。'
        '此集合用于开发和工程验证，不估计完整 Mini50 或未见任务的通过率。', '',
        '| 任务 | H0/RRSI/GEPA | H0 调用 | H0 token | 选入原因 |', '|---|---|---:|---:|---|']
    for r in selected:
        lines.append(f"| {r['task_id']} | {'/'.join(map(str,r['scores']))} | {r['baseline_calls']} | {r['baseline_tokens']:,} | {r['selection_category']} |")
    (output / 'selection.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'selection': str(output / 'selection.json'), 'task_ids': result['task_ids'],
        'historical_resolved': result['historical_resolved'], 'valid_task_trials':150}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
