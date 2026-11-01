"""Merged candidate/retained table, first-party grades and deduplicated costs."""
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from .protocol import WORK, OLD
from .runtime import worker_count


def merged_usage():
    rows = {}
    for root in (OLD, WORK):
        for path in root.glob('*/round-*/**/usage.json'):
            if 'optimizer-api' not in path.parts and 'trials' not in path.parts:
                continue
            for row in read(path)['requests']:
                previous = rows.get(row['id'])
                if previous is not None and previous != row:
                    raise ValueError('Conflicting duplicated usage ID')
                rows[row['id']] = row
    values = list(rows.values())
    return {'calls': len(values), 'actual_tokens': sum(x.get('usage', {}).get('total_tokens', 0) for x in values),
            'charged_or_reserved_tokens': sum(x['charged_tokens'] for x in values),
            'unknown_usage_requests': sum('usage' not in x for x in values)}


def summarize(write=False):
    frameworks = []
    for name in ('harnessfix', 'meta-harness', 'gepa', 'rrsi', 'dgm'):
        rounds = []
        for n in (1, 2):
            recovery = WORK / name / f'round-{n}'
            folder = recovery if (recovery / 'started.json').exists() else OLD / name / f'round-{n}'
            p = folder / 'result.json'
            item = read(p) if p.exists() else read(folder / 'status.json') if (folder / 'status.json').exists() else {'status': 'pending'}
            grades = [read(p) for p in folder.glob('evaluations/candidate/trials/*/grade.json')]
            parent = read(folder / 'input-parent.json') if (folder / 'input-parent.json').exists() else {}
            old = {i for i, v in parent.get('scores', {}).items() if v}
            new = {g['instance_id'] for g in grades if g.get('resolved')}
            full = len(grades) == 10
            rounds.append({'status': item['status'], 'source': str(folder), 'graded': len(grades),
                'candidate_resolved': len(new) if full else None,
                'gained': sorted(new-old) if full else None, 'regressed': sorted(old-new) if full else None,
                'retained': item.get('retained_resolved'), 'selected': item.get('native_selected'),
                'parent_source_round': parent.get('source_round')})
        frameworks.append({'framework': name, 'rounds': rounds})
    usage = merged_usage()
    count = worker_count()
    assert count <= 100 and usage['calls'] <= 9000 and usage['charged_or_reserved_tokens'] <= 180000000
    result = {'frameworks': frameworks, 'combined_usage': usage, 'combined_target_executions': count,
              'batch': read(WORK / 'batch-status.json') if (WORK / 'batch-status.json').exists() else {'status': 'prepared'}}
    if write:
        write_json(WORK / 'summary.json', result)
        lines = ['# 十题两轮完整对比：缺失阶段恢复', '',
                 '共同H0：3/10。仅补HarnessFix/DGM；其余框架保留原始结果。新增与退化相对每轮实际父版本。', '',
                 '| 框架 | H0 | 第1轮候选 | 新增 | 退化 | 第2轮候选 | 新增 | 退化 | 最终保留 |',
                 '|---|---:|---|---:|---:|---|---:|---:|---|']
        for entry in frameworks:
            cells = []
            for row in entry['rounds']:
                score = f'{row["candidate_resolved"]}/10' if row['candidate_resolved'] is not None else f'{row["status"]}（已评分{row["graded"]}/10）'
                cells += [score, str(len(row['gained'])) if row['gained'] is not None else '—',
                          str(len(row['regressed'])) if row['regressed'] is not None else '—']
            retained = next((x['retained'] for x in reversed(entry['rounds']) if x['retained'] is not None), None)
            lines.append('| ' + ' | '.join([entry['framework'], '3/10']+cells+[f'{retained}/10' if retained is not None else '待确认'])+' |')
        lines += ['', 'HarnessFix第1轮复用十题已有评分、重放原生选择，禁止新模型请求；DGM第1轮重放第一份原生候选，全部旧失败成本计入。原始失败不覆盖。',
                  '恢复修复：HF反馈目录映射、DGM结构验证绑定递归。候选源码无人工修改。恢复结果是工程修复后的结果，不冒充原始运行。', '',
                  f'合并去重成本：{usage["calls"]}次调用，{usage["actual_tokens"]:,}已知实际token，{usage["unknown_usage_requests"]}次未知usage；含预留{usage["charged_or_reserved_tokens"]:,}token。',
                  f'合并任务执行：{count}/100（HF第1轮缓存重放不重复计数）。', '']
        (WORK / 'report.md').write_text('\n'.join(lines))
    return result
