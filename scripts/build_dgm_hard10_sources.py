"""Project reviewed experiment evidence into a small, credential-free Sources receipt."""
from acl_frameworks.common import ROOT, read
from acl_rsi.settings import write_json

selection = read(ROOT / 'experiments/runs/hard10-selection-v1/selection.json')
folder = ROOT / 'experiments/runs/dgm-hard10-v1-recovery2'
summary = read(folder / 'validated-summary.json')
rows = summary['rows']
payload = {'schemaVersion': 1, 'items': [
    {'id': 'hard-task-selection', 'title': '困难十题的选择依据', 'queries': [{
        'id': 'historical-selection', 'source': {'label': 'Mini50 历史运行与冻结名单',
            'files': [{'label': 'selection.json'}, {'label': 'selection-audit.ipynb'}],
            'metricDefinitions': [{'label': '历史通过', 'definition': '历史通过表示该 Harness 在该题对应的一次有效运行通过官方评分。'}],
            'filters': ['Django：5 题', 'Sphinx：5 题', 'H0 失败：8 题', '高成本脆弱成功：2 题'],
            'caveats': ['按历史结果筛选的开发集，不代表完整 Mini50 或未见测试集。',
                'H0、RRSI 候选、GEPA 候选是不同 Harness 的运行，不能当作三个独立随机重复。'],
            'evidenceFlow': [{'kind': 'validation', 'title': '原始记录核验',
                'detail': '150 份原始 trial 通过实例、patch 摘要和评分一致性检查；全 50 题重新计数为 31、29、25。'}]},
        'columns': [{'field': 'task', 'label': '任务'}, {'field': 'h0', 'label': 'H0'},
                    {'field': 'rrsi', 'label': 'RRSI 候选'}, {'field': 'gepa', 'label': 'GEPA 候选'}],
        'rows': [{'task': r['task_id'], 'h0': r['scores'][0], 'rrsi': r['scores'][1], 'gepa': r['scores'][2]} for r in selection['selected']]
    }]},
    {'id': 'recovered-dgm-results', 'title': 'DGM 恢复后候选的十题结果', 'queries': [{
        'id': 'official-task-outcomes', 'source': {'label': 'DGM 十题官方评分',
            'files': [{'label': 'validated-summary.json'}, {'label': 'protocol-contract.json'}, {'label': 'recovery-audit.json'}],
            'metricDefinitions': [{'label': '解决数', 'definition': '解决数统计冻结十题中通过官方评分的题目，H0 复用历史记录，候选每题重新执行一次。'}],
            'caveats': ['原候选先发生工具协议错误，经两次模型接口修复后才完成十题，属于恢复后的工程试跑。',
                '单次新旧运行差异包含模型随机性，不能证明稳定收益或 DGM 原论文效果复现。'],
            'evidenceFlow': [{'kind': 'validation', 'title': '评分重验',
                'detail': '十题逐一核验 worker、patch 摘要与 grade；有官方报告的非空提交检查报告一致性，空提交保留明确失败标识。缺失评分没有记作失败。'}]},
        'columns': [{'field': 'task', 'label': '任务'}, {'field': 'baseline', 'label': 'H0'},
                    {'field': 'candidate', 'label': '恢复后候选'}],
        'rows': [{'task': r['task_id'], 'baseline': r['baseline_score'], 'candidate': r['candidate_score']} for r in rows],
        'methods': [{'language': 'calculation', 'code':
            f"H0 = {summary['baseline_resolved']} / 10\nCandidate = {summary['candidate_resolved']} / 10\n"
            f"Newly resolved = {len(summary['newly_resolved'])}\nRegressions = {len(summary['regressions'])}"}]
    }]},
    {'id': 'run-consumption', 'title': '全轮调用与 token 消耗', 'queries': [{
        'id': 'shared-usage-ledgers', 'source': {'label': '共享搜索与任务用量账本',
            'files': [{'label': 'usage.json'}, {'label': 'validated-summary.json'}],
            'metricDefinitions': [{'label': '累计消耗', 'definition': '累计消耗覆盖诊断、自修改、两次接口恢复、一次失败任务尝试和十次有效候选执行。'}],
            'caveats': ['无用量回执的请求保留预算预留，不能认定为零消耗；未估计金额。']},
        'columns': ['calls', 'actual_tokens', 'unknown_usage_requests', 'charged_or_reserved_tokens'],
        'rows': [{k: summary['whole_experiment_usage'][k] for k in
                  ('calls', 'actual_tokens', 'unknown_usage_requests', 'charged_or_reserved_tokens')}]
    }]}
]}
write_json(folder / 'sources-receipt.json', payload)
print(folder / 'sources-receipt.json')
