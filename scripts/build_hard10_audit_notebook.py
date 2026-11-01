"""Build and execute the historical cohort audit; never call an LLM or Docker."""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/runs/hard10-selection-v1/selection-audit.ipynb'
nb = nbf.v4.new_notebook()
nb.metadata['kernelspec'] = {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}
nb.cells = [
    nbf.v4.new_markdown_cell('''# 困难十题：历史选题审计

过去 H0、RRSI 候选、GEPA 候选在完整 Mini50 上分别解决 31、29、25 题。
本开发集按历史表现选取 Django、Sphinx 各五题，其中八题 H0 失败、两题为高成本脆弱成功。
集合上的历史通过数为 2、3、2，不能当作框架排名或完整 Mini50 通过率。

## Context & Methods

重读原始 trial，检查实例、worker、patch 摘要、官方报告一致性；使用冻结的确定性选题规则，
重算并比较已保存的选题清单。历史三套 Harness 不等于三个独立随机种子。

### Key Assumptions

此 notebook 只审计历史数据和选题；不重新请求模型、执行任务或访问隐藏测试正文。
运行入口是项目根目录，依赖现有项目环境和 nbformat、nbclient、ipykernel。'''),
    nbf.v4.new_code_cell('''from pathlib import Path
import json
from collections import Counter
from acl_dgm.select_hard10 import audit, choose

root = Path.cwd()
frozen = json.loads((root / 'experiments/runs/hard10-selection-v1/selection.json').read_text())
evidence = audit()
selected = choose(evidence['all50'])
assert evidence['source_file_sha256'] == frozen['source_file_sha256']
assert [r['task_id'] for r in selected] == frozen['task_ids']
assert evidence['valid_task_trials'] == 150
print('原始记录检查通过:', evidence['valid_task_trials'])
print('完整 Mini50 解决数:', evidence['full50_resolved'])
print('仓库分布:', dict(Counter(r['repo'] for r in selected)))
print('选题类型:', dict(Counter(r['selection_category'] for r in selected)))'''),
    nbf.v4.new_markdown_cell('## Results\n\n以下为全部十题，不是抽样预览。1 表示该次 Harness 通过官方评分。'),
    nbf.v4.new_code_cell('''print(f"{'Task':31} H0 RRSI GEPA H0 calls H0 tokens")
for row in selected:
    h0, rrsi, gepa = row['scores']
    print(f"{row['task_id']:31} {h0:2} {rrsi:4} {gepa:4} {row['baseline_calls']:8} {row['baseline_tokens']:9,}")
totals = [sum(row['scores'][k] for row in selected) for k in range(3)]
assert totals == [2, 3, 2]
assert len(selected) == len({r['task_id'] for r in selected}) == 10
assert sum(row['scores'][0] == 0 for row in selected) == 8
print('十题合计:', totals)'''),
    nbf.v4.new_markdown_cell('''## Takeaways

该集合覆盖耗尽调用、耗尽 token、错误非空提交、曾被其他 Harness 恢复的失败，以及脆弱成功。
适合本轮工程试跑，同时对选题历史有明显依赖。DGM 新候选成绩必须在独立运行报告中展示，
不能根据新成绩替换这里的题目，也不能把历史三个 Harness 当成独立重复用于显著性推断。

验证：本 notebook 自上而下执行全部代码单元；没有产生模型调用或 Benchmark 执行。
''')]
NotebookClient(nb, timeout=180, kernel_name='python3', resources={'metadata': {'path': str(ROOT)}}).execute()
nbf.validate(nb)
nbf.write(nb, OUT)
for cell in nb.cells:
    for output in cell.get('outputs', []):
        if output.get('output_type') == 'stream':
            print(output['text'])
print(OUT)
