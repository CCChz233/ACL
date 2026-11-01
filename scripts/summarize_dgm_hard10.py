"""Read and validate finished DGM engineering records; no paid calls or task execution."""
import json
from pathlib import Path

from acl_frameworks.common import ROOT, read, sha
from acl_dgm.experiment import usage
from acl_gepa_swe.feedback import record
from acl_rsi.settings import write_json


def main():
    selection = read(ROOT / 'experiments/runs/hard10-selection-v1/selection.json')
    original = ROOT / 'experiments/runs/dgm-hard10-v1'
    work = ROOT / 'experiments/runs/dgm-hard10-v1-recovery2'
    result = read(work / 'result.json')
    if result['status'] != 'completed' or result['graded'] != 10:
        raise ValueError('Need ten completed validated task outcomes')
    instances = {r['instance_id']: r for r in read(ROOT / 'benchmarks/datasets/swe-bench-verified-mini/test.json')}
    rows = []
    for old in selection['selected']:
        iid = old['task_id']
        trial = work / 'evaluations/node_0000/trials' / iid
        current = record(trial, iid, instances[iid], trace=False)
        row = {'task_id': iid, 'selection_category': old['selection_category'],
            'baseline_score': old['scores'][0], 'candidate_score': int(current['score']),
            'baseline_calls': old['baseline_calls'], 'baseline_tokens': old['baseline_tokens'],
            'calls': usage(trial / 'usage.json')['calls'], 'actual_tokens': usage(trial / 'usage.json')['actual_tokens'],
            'stop': current['stop'], 'grading_reason': current['grading_reason'],
            'empty_patch': not (trial / 'patch.diff').read_text().strip(),
            'trial': str(trial.relative_to(ROOT)),
            'sha256': {f: sha(trial / f) for f in ('manifest.json', 'worker.json', 'grade.json', 'patch.diff', 'usage.json')}}
        grade = read(trial / 'grade.json')
        if grade.get('report_path'):
            row['official_report_sha256'] = sha(Path(grade['report_path']))
        rows.append(row)
    paths = [original / 'optimizer-api/usage.json'] + list(original.glob('evaluations/*/trials/*/usage.json')) + list(work.glob('evaluations/*/trials/*/usage.json'))
    requests = [r for p in paths for r in read(p)['requests']]
    total = {k: sum(usage(p)[k] for p in paths) for k in ('calls', 'completed', 'actual_tokens', 'unknown_usage_requests', 'charged_or_reserved_tokens')}
    assert total['calls'] <= 580 and total['charged_or_reserved_tokens'] <= 11000000
    token_types = {key: sum(r.get('usage', {}).get(key, 0) or 0 for r in requests) for key in
        ('prompt_tokens', 'completion_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')}
    assert token_types['prompt_tokens'] + token_types['completion_tokens'] == total['actual_tokens']
    total.update(token_types)
    baseline = sum(r['baseline_score'] for r in rows)
    candidate = sum(r['candidate_score'] for r in rows)
    report = {'status': 'ten_tasks_validated', 'scope': result['scope'], 'rows': rows,
        'baseline_resolved': baseline, 'candidate_resolved': candidate, 'total_tasks': 10,
        'newly_resolved': [r['task_id'] for r in rows if r['candidate_score'] > r['baseline_score']],
        'regressions': [r['task_id'] for r in rows if r['candidate_score'] < r['baseline_score']],
        'optimizer_usage': usage(original / 'optimizer-api/usage.json'),
        'failed_first_attempt_usage': usage(original / 'evaluations/node_0000/trials/django__django-12209/usage.json'),
        'whole_experiment_usage': total, 'native_archive_policy': 'keep_all; admission does not imply improvement',
        'best_observed_harness': 'candidate' if candidate > baseline else 'H0',
        'selection_sha256': sha(ROOT / 'experiments/runs/hard10-selection-v1/selection.json'),
        'candidate_sha256': {f: sha(work / 'evaluations/node_0000/harness' / f) for f in ('agent.py', 'swebench.yaml', 'LICENSE.md')},
        'caveats': ['Historically selected development cohort; not heldout or representative of Mini50.',
            'Historical baseline reused, one fresh candidate trial per task; no repeated-seed causal estimate.',
            'Original candidate caused an API protocol failure; two model repair sessions shared the original search budget.',
            'Eleven target attempts across ten unique IDs: one failed attempt plus ten repaired-candidate evaluations.',
            'Unknown usage on rejected requests remains reserved; currency cost is not estimated.']}
    write_json(work / 'validated-summary.json', report)
    lines = ['# DGM 困难十题结果', '',
        f'经过接口恢复的候选通过 **{candidate}/10**；复用历史 H0 为 **{baseline}/10**。'
        f'新增解决 {len(report["newly_resolved"])} 题，回归 {len(report["regressions"])} 题。', '',
        '这是困难开发集上的一次工程试跑：原候选在首题发生工具协议错误，模型在同一搜索账本内进行了两次接口修复，'
        '随后才完成十题。不能写作未经干预的 DGM 效果复现，也不能外推完整 Mini50。', '',
        '| 任务 | H0 | 修复后候选 | H0 调用 | 新调用 | 新 token | 退出状态 |', '|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        lines.append(f'| {r["task_id"]} | {r["baseline_score"]} | {r["candidate_score"]} | {r["baseline_calls"]} | {r["calls"]} | {r["actual_tokens"]:,} | {r["stop"]} |')
    lines += ['', f'总消耗（含诊断、自修改、两次接口修复和失败首题）：{total["calls"]} 次请求，'
        f'{total["actual_tokens"]:,} 个已知实际 token，{total["unknown_usage_requests"]} 次请求无用量回执；'
        f'包含未知请求预留后的保守 token 账本合计 {total["charged_or_reserved_tokens"]:,}。', '',
        '完整请求/响应、轨迹、候选代码、patch 与官方评分均已保存。金额未估计；错误请求不按零消耗处理。', '',
        '原生 archive 保留有效候选，包括较差候选；入库本身不是改进。单次结果差异还可能包含模型随机性，'
        '需要独立任务与重复运行才能判断稳定收益。', '']
    (work / 'summary.md').write_text('\n'.join(lines))
    before = original / 'optimizer/harness'
    after = work / 'evaluations/node_0000/harness'
    import difflib
    patch = ''.join('diff --git a/'+f+' b/'+f+'\n'+''.join(difflib.unified_diff(
        (before/f).read_text().splitlines(True), (after/f).read_text().splitlines(True),
        fromfile='a/'+f, tofile='b/'+f)) for f in ('agent.py','swebench.yaml') if sha(before/f) != sha(after/f))
    (work / 'candidate.diff').write_text(patch)
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','caveats')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
