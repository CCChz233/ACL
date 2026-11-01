"""Read-only, reproducible analysis of the completed full-ten-task pilot.

Run in the project uv environment. Writes only analysis exports and reviewed
inline presentation inputs; never changes experiments or calls a model.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'experiments/runs/full10-highbudget-two-rounds-v1'
DONE = ROOT / 'experiments/runs/full10-highbudget-completion-v1'
OUT = ROOT / 'reports/exports/full10-two-rounds-analysis'
VIZ = Path('/Users/chz/.codex/visualizations/2026/10/15/01a14002-254b-7f01-a931-e2e33d285ba7')
NAMES = {'harnessfix': 'HarnessFix', 'meta-harness': 'Meta-Harness', 'gepa': 'GEPA', 'rrsi': 'RRSI', 'dgm': 'DGM'}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def usage(paths):
    rows = {}
    for p in paths:
        for row in read(p)['requests']:
            if row['id'] in rows:
                assert rows[row['id']] == row
            rows[row['id']] = row
    return {'calls': len(rows),
            'actual_tokens': sum(v.get('usage', {}).get('total_tokens', 0) for v in rows.values()),
            'charged_or_reserved_tokens': sum(v['charged_tokens'] for v in rows.values()),
            'unknown_usage_requests': sum('usage' not in v for v in rows.values()),
            'prompt_tokens': sum(v.get('usage', {}).get('prompt_tokens', 0) for v in rows.values()),
            'completion_tokens': sum(v.get('usage', {}).get('completion_tokens', 0) for v in rows.values())}


def short(iid):
    return iid.replace('django__django-', 'Django-').replace('sphinx-doc__sphinx-', 'Sphinx-')


def main():
    summary = read(DONE / 'summary.json')
    assert summary['batch']['status'] == 'completed'
    rows = []
    task_rows = []
    retained_paths = []
    candidates_by_round = {1: [], 2: []}
    shared_baseline = None
    shared_target_budget = None
    for entry in summary['frameworks']:
        method = entry['framework']
        results = []
        for n, saved in enumerate(entry['rounds'], 1):
            folder = Path(saved['source'])
            result = read(folder / 'result.json')
            parent = read(folder / 'input-parent.json')
            cfg = read(folder / 'config.json')
            assert cfg['model'] == 'deepseek-flash'
            if shared_target_budget is None:
                shared_target_budget = cfg['target']
            assert cfg['target'] == shared_target_budget
            ids = set(parent['scores'])
            grade_paths = list(folder.glob('evaluations/candidate/trials/*/grade.json'))
            assert len(grade_paths) == 10
            actual = {read(p)['instance_id']: int(read(p)['resolved']) for p in grade_paths}
            assert set(actual) == ids and actual == result['candidate_scores']
            gained = sorted(i for i in ids if actual[i] and not parent['scores'][i])
            lost = sorted(i for i in ids if parent['scores'][i] and not actual[i])
            assert gained == saved['gained'] and lost == saved['regressed']
            assert sum(actual.values()) == sum(parent['scores'].values()) + len(gained)-len(lost)
            next_parent = result['next_parent']
            retained_set = {i for i, v in next_parent['scores'].items() if v}
            assert len(retained_set) == result['retained_resolved']
            results.append({'round': n, 'candidate': sum(actual.values()),
                'retained': len(retained_set), 'gained': gained, 'regressed': lost,
                'selected': result['native_selected'], 'parent_round': parent['source_round'],
                'parent_resolved': int(sum(parent['scores'].values())),
                'source': str(folder.relative_to(ROOT)), 'scores': actual,
                'exit_counts': dict(Counter(read(p.parent/'worker.json')['exit_status'] for p in grade_paths))})
            candidates_by_round[n].append(results[-1])
            if n == 1:
                assert int(sum(parent['scores'].values())) == 3
                if shared_baseline is None:
                    shared_baseline = parent['scores']
                assert parent['scores'] == shared_baseline
                assert {i: int(read(Path(parent['trials'][i])/'grade.json')['resolved']) for i in ids} == parent['scores']
                baseline_scores = parent['scores']
            retained_paths.append({'framework': NAMES[method], 'round': n,
                                   'solved': len(retained_set)})
        retained_paths.append({'framework': NAMES[method], 'round': 0, 'solved': 3})
        # Sources include discarded native searches but exclude duplicated HF replay costs.
        opts = [p for root in (OLD, DONE) for p in (root/method).glob('round-*/optimizer-api/usage.json')]
        targets = [p for root in (OLD, DONE) for p in (root/method).glob('round-*/evaluations/candidate/trials/*/usage.json')]
        costs = {'optimizer': usage(opts), 'target': usage(targets)}
        final = read(Path(entry['rounds'][-1]['source'])/'result.json')['next_parent']
        rows.append({'framework': NAMES[method], 'rounds': results, 'final': int(sum(final['scores'].values())),
                     'final_source_round': final['source_round'], 'final_scores': final['scores'], 'usage': costs})
    baseline = {i for i, v in baseline_scores.items() if v}
    final_union = set().union(*({i for i, v in row['final_scores'].items() if v} for row in rows))
    never_solved = [i for i in baseline_scores if not any(r['scores'][i] for row in rows for r in row['rounds']) and i not in baseline]
    for iid in baseline_scores:
        task_rows.append({'task': iid, 'baseline': int(baseline_scores[iid]),
                          **{row['framework']: int(row['final_scores'][iid]) for row in rows}})
    opt_total = sum(row['usage']['optimizer']['actual_tokens'] for row in rows)
    target_total = sum(row['usage']['target']['actual_tokens'] for row in rows)
    calls = sum(row['usage'][key]['calls'] for row in rows for key in ('optimizer', 'target'))
    assert calls == summary['combined_usage']['calls']
    assert opt_total+target_total == summary['combined_usage']['actual_tokens']
    all_candidates = [r for row in rows for r in row['rounds']]
    out = {'captured_at': datetime.now(timezone.utc).isoformat(), 'baseline': {'resolved': 3, 'n': 10},
           'methods': rows, 'task_matrix_final': task_rows,
           'diagnostics': {'accepted_round1': sum(r['selected']=='candidate' for r in candidates_by_round[1]),
               'accepted_round2': sum(r['selected']=='candidate' for r in candidates_by_round[2]),
               'second_candidates_improved_parent': sum(r['candidate']>r['parent_resolved'] for r in candidates_by_round[2]),
               'second_candidates_tied_parent': sum(r['candidate']==r['parent_resolved'] for r in candidates_by_round[2]),
               'second_candidates_worse_parent': sum(r['candidate']<r['parent_resolved'] for r in candidates_by_round[2]),
               'final_union': sorted(final_union), 'never_solved': never_solved,
               'evaluated_candidates': len(all_candidates), 'accepted_candidates': sum(r['selected']=='candidate' for r in all_candidates),
               'optimizer_actual_tokens': opt_total, 'target_actual_tokens': target_total},
           'combined_usage': summary['combined_usage']}
    write(OUT/'analysis.json', out)
    lines = ['# 十题两轮RSI实验：含无RSI基线的结果与分析', '',
        '固定DeepSeek Flash、mini-SWE-agent、同一套十题和每题预算。下表是候选的实际成绩；最终保留单列。新增/退化相对该轮实际父版本，非一律相对H0。无RSI基线只测一份，两轮不重复运行。', '',
        '| 方法 | 第0轮 | 第1轮候选（新增/退化） | 第2轮候选（新增/退化） | 最终保留 | 相对基线净增 |',
        '|---|---:|---|---|---:|---:|', '| 无RSI Baseline | 3/10 | — | — | 3/10 | 0题 |']
    for row in rows:
        values = [f'{r["candidate"]}/10（+{len(r["gained"])}/−{len(r["regressed"])}）' for r in row['rounds']]
        lines.append('| '+' | '.join([row['framework'], '3/10']+values+[f'{row["final"]}/10', f'+{row["final"]-3}题'])+' |')
    lines += ['', 'Meta第一轮0/10：十题均因候选缺少exception_info字段而UndefinedError退出；保留H0，第2轮从H0继续。HF、RRSI第二轮打平未采纳；DGM第二轮退化未采纳。HF/DGM包含工程恢复，恢复来源与全部旧失败成本均保留。', '',
        '## 实际保留的演化过程', '', '| 方法 | 第0轮 | 第1轮后 | 第2轮后 |', '|---|---:|---:|---:|', '| 无RSI Baseline | 3/10 | 沿用3/10 | 沿用3/10 |']
    for row in rows:
        lines.append(f'| {row["framework"]} | 3/10 | {row["rounds"][0]["retained"]}/10 | {row["rounds"][1]["retained"]}/10 |')
    lines += ['', '## 可以观察到什么', '',
        '1. 在这次开发集运行中，四个框架最终保留成绩超过H0；DGM为6/10、HF/Meta/RRSI为5/10、GEPA为3/10。这是可运行性与潜在收益信号，不能称作稳定的框架排名。',
        '2. 第2轮候选中，1个超过父版本、3个打平、1个退化。唯一提高的Meta从H0出发；已在第1轮提高的HF/RRSI/DGM均没有再次提高。两轮数据不足以宣称收益饱和，但不支持多迭代必然提高。',
        '3. HF与RRSI第二轮均新增1题、退化1题；DGM第二轮新增0题、退化3题。只看总分会掩盖行为变化，候选评分和接纳规则都需保留。最终成绩单调不降也由拒绝退化的规则保证，并非每次修改都更强。',
        '4. Meta第一轮为运行时接口破坏，不能与正常推理失败混为一谈。应报告端到端0/10，同时单列运行错误和保留H0 3/10，补真实循环/异常路径的离线门禁。',
        '5. 各最终版本解题集合的事后并集为'+str(len(final_union))+'/10，其中Sphinx-10435被四个提升框架新增解决。互补性是待检验假设；这个并集依赖事后知道每题选谁，不是可部署系统的7/10成绩。所有候选都没解出的题：'+', '.join(short(i) for i in never_solved)+'。',
        '6. 相同预算上限不等于相同实际开销。下面列出优化器与任务执行分别消耗的累计实际token；不换算货币费用，不将缓存命中或重复输入当作唯一证据规模。', '',
        '| 框架 | 优化器调用 | 优化器实际token | 任务调用 | 任务实际token |', '|---|---:|---:|---:|---:|']
    for row in rows:
        u=row['usage'];lines.append(f'| {row["framework"]} | {u["optimizer"]["calls"]} | {u["optimizer"]["actual_tokens"]:,} | {u["target"]["calls"]} | {u["target"]["actual_tokens"]:,} |')
    lines += ['', 'RRSI与Meta最后都保留5/10，但两轮优化器累计实际token分别为1,477,712与6,689,916。它们的算法、阶段与读取策略不同，因此不能把差值归因于某一种上下文方法；GEPA只有7次优化器调用，也不能把同预算上限误称为相同实际搜索投入。', '',
        f'合计优化器{opt_total:,}token、任务执行{target_total:,}token，共{opt_total+target_total:,}已知实际token；1次未知usage，含预留总计{summary["combined_usage"]["charged_or_reserved_tokens"]:,}token。总4079次调用、100次候选任务执行；共享H0的历史成本不计入这批新增成本。', '',
        '## 不能据此得出的结论', '',
        '- 十题均反复用于反馈、选择和评测，属开发集；只有一次基线/单次候选评测，没有相同预算的无修改重复尝试或重新采样对照，无法区分Harness效应、随机波动和多次尝试选择的贡献。',
        '- 最终保留版本按同十题反馈选择，故保留曲线带有选择偏差，不能当作独立测试成绩。候选间也不是独立样本。',
        '- 框架采用一步原生适配与共同外循环，HF/DGM有工程恢复，部分阶段上限和模型修复已调整，不是原论文完整配置复现。',
        '- 尚未实施EAEC，没有上下文方法的配对对照；这些结果不能证明冗余上下文造成失败，也不能证明上下文压缩能保持或提高效果。', '',
        '## 下一步建议（未自动启动实验）', '',
        '先冻结已有候选，做相同预算的H0重跑/多次尝试对照和候选配对重复评测，估计波动；另用未参与反馈的新任务检验泛化。随后以HarnessFix为当前主线，在固定父快照、固定诊断/修改阶段、固定验证接纳规则下比较上下文组织方法；DGM作为已跑通的外部补充验证，不能因本次6/10而直接替换研究主线。正式预算须先定。', '',
        '## 逐题结果（最终实际保留版本）', '', '| 题目 | 无RSI | HF | Meta | GEPA | RRSI | DGM |', '|---|---:|---:|---:|---:|---:|---:|']
    for row in task_rows:
        vals=[row['baseline']]+[row[n] for n in NAMES.values()]
        lines.append('| '+short(row['task'])+' | '+' | '.join('✓' if v else '✗' for v in vals)+' |')
    lines += ['', '证据：各轮input-parent.json、result.json、逐题grade.json/worker.json与usage.json；summary.json只作为目录索引，分数和变动从逐题证据重算。final-audit.json验证100次评分。计算脚本：scripts/analyze_full10_results.py。', '']
    (OUT/'analysis.md').write_text('\n'.join(lines))
    # Only bounded, reviewed fields enter the inline payloads. No absolute paths.
    source={'label':'SWE十题两轮实验',
        'files':[{'label':'逐题grade.json与worker.json'}, {'label':'逐轮input-parent.json与result.json'}],
        'metricDefinitions':[{'definition':'保留成绩是每轮接纳或拒绝候选后实际采用版本在共同十题上的已有评分。'}],
        'filters':['模型：DeepSeek Flash', 'Agent：mini-SWE-agent', '任务：同一套10道开发题'],
        'caveats':['未更新版本沿用此前评分，图中保留曲线不代表每轮重新评测该版本。',
                   '只运行一次且使用同题反馈选择；不代表独立测试或稳定优劣。',
                   'HarnessFix与DGM包含已记录的工程恢复。']}
    chart_rows=[{'method':n,'stage':f'第{r}轮后','solved':next(x['solved'] for x in retained_paths if x['framework']==n and x['round']==r)}
                for n in NAMES.values() for r in (0,1,2)]
    chart={'schemaVersion':1,'id':'full10-retained-rounds','title':'每轮后实际保留的版本：通过题数',
        'chart':{'type':'bar','x':'method','y':'solved','series':'stage','yLabel':'解出题数（共10题）','showXAxisLabel':False,'showValues':True,'startAtZero':True},
        'rows':chart_rows,'source':source,'generatedAt':out['captured_at'],'height':340}
    write(VIZ/'full10-retained-rounds.json',chart)
    receipt={'schemaVersion':1,'items':[{'id':'retained-rounds','title':'候选接纳后保留成绩的演化',
        'queries':[{'id':'retained-rounds','source':source,'rows':chart_rows,'columns':['method','stage','solved'],
            'capturedAt':out['captured_at'],'preview':{'kind':'aggregate','note':'5个框架、3个阶段的完整保留成绩。','totalRows':15}}]}]}
    write(VIZ/'full10-retained-sources.json',receipt)
    other_source={'label':'SWE十题候选与成本审计',
        'files':[{'label':'analysis.json'},{'label':'final-audit.json'},{'label':'usage.json'},{'label':'Meta第1轮trajectory.json'},{'label':'research_story.md'}],
        'caveats':['每轮候选与实际父版本比较；被拒绝候选不作为下一轮起点。','端到端失败包括Meta第1轮运行时Bug；原始失败不覆盖。'],
        'evidenceFlow':[{'kind':'validation','title':'结果核对','detail':'逐题重算10个候选分数及新增/退化，并核对实际父版本；分框架去重账本合计4079次调用、68994255已知实际token。'}]}
    receipt2={'schemaVersion':1,'items':[{'id':'candidate-gains-regressions','title':'候选分数、回归与成本',
        'queries':[{'id':'candidate-detail','source':other_source,
            'rows':[{'method':row['framework'],'round':r['round'],'candidate':r['candidate'],
                     'gained':len(r['gained']),'regressed':len(r['regressed']),'accepted':r['selected']=='candidate'} for row in rows for r in row['rounds']],
            'columns':['method','round','candidate','gained','regressed','accepted'],
            'methods':[{'language':'python','code':
                "gained = sorted(i for i in ids if actual[i] and not parent['scores'][i])\nlost = sorted(i for i in ids if parent['scores'][i] and not actual[i])"}]},
            {'id':'optimizer-costs','source':{'label':'分框架去重API账本','files':[{'label':'optimizer-api/usage.json'},{'label':'trials/usage.json'}],
                'metricDefinitions':[{'definition':'实际token是API返回的累计输入与输出token，同一request ID只计一次，包含失败尝试的已知开销。'}],
                'caveats':['DGM有1次请求缺失usage；已知实际token不含该请求，含预留token另列。','共同H0的历史运行成本不计入这批新增成本。']},
             'rows':[{'method':r['framework'],'optimizer_tokens':r['usage']['optimizer']['actual_tokens'],
                      'target_tokens':r['usage']['target']['actual_tokens']} for r in rows],
             'columns':['method','optimizer_tokens','target_tokens']}]}]}
    write(VIZ/'full10-analysis-sources.json',receipt2)
    print(json.dumps({'diagnostics':out['diagnostics'],'costs':[{ 'method':r['framework'],**r['usage']} for r in rows]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
