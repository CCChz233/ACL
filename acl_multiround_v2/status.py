import json
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from acl_unified.status import ledger
from .protocol import WORK,OLD,FRAMEWORKS,round_dir
from .runtime import legacy_usage_paths,legacy_worker_paths,worker_count


def summarize(write=False):
    rows=[]
    for name in FRAMEWORKS:
        rounds=[]
        for index in (1,2):
            folder=round_dir(name,index);p=folder/'result.json'
            item=read(p) if p.exists() else read(folder/'status.json') if (folder/'status.json').exists() else {'status':'pending'}
            value={k:v for k,v in item.items() if k not in ('native','next_parent')}
            opt=folder/'optimizer-api/usage.json'
            if not opt.exists() and item.get('optimizer_usage_reference'):opt=OLD/item['optimizer_usage_reference']
            value['optimizer_usage']=ledger([opt]) if opt.exists() else ledger([])
            value['target_usage']=ledger(list(folder.glob('evaluations/*/trials/*/usage.json')))
            value['graded_tasks']=len(list(folder.glob('evaluations/*/trials/*/grade.json')))
            if (folder/'progress.json').exists():value['progress']=read(folder/'progress.json')
            rounds.append(value)
        rows.append({'framework':name,'rounds':rounds})
    paths=legacy_usage_paths()+list(WORK.glob('*/round-*/optimizer-api/usage.json'))+list(WORK.glob('*/round-*/evaluations/*/trials/*/usage.json'))
    assert len(paths)==len(set(paths))
    usage=ledger(paths);count=worker_count()
    assert usage['calls']<=5800 and usage['charged_or_reserved_tokens']<=110000000 and count<=100
    result={'baseline':read(WORK/'baseline.json'),'frameworks':rows,'total_usage_including_prior_scope_spend':usage,
        'total_target_executions_including_prior_retests':count,
        'prior_scope_overhead':{'usage':ledger(legacy_usage_paths()),'worker_executions':len(legacy_worker_paths())},
        'batch':read(WORK/'batch-status.json') if (WORK/'batch-status.json').exists() else {'status':'not_started'}}
    if write:
        write_json(WORK/'summary.json',result)
        lines=['# 五框架统一两轮：完整十题、只测有效新 Harness','',
            '**第0轮共同原始 Agent：3/10。** DeepSeek Flash + mini-SWE-agent。全十题提供反馈；第1、2轮只对有效新候选评测十题。','',
            '| 方法 | 第0轮 | 第1轮 | 第2轮 |','|---|---:|---|---|', '| 原始 Agent | 3/10 | — | — |']
        for item in rows:
            cells=[]
            for r in item['rounds']:
                if r.get('round_scores') is not None:cell=f'{r["round_resolved"]}/10'
                elif r.get('evaluated_kind')=='unchanged_parent_reused':cell=f'未更新（沿用 {r["retained_resolved"]}/10）'
                else:cell='运行中' if r['status']=='running' else '待测' if r['status']=='pending' else 'N/A'
                cells.append(cell)
            lines.append('| '+item['framework']+' | 共用 H0 | '+' | '.join(cells)+' |')
        lines+=['','“未更新/沿用”没有新增任务评测，不是本轮候选实测成绩。有效候选可能被原生规则拒绝；下一轮继承原生保留版本，原始候选与保留分数分列。',
            '', '| 框架 | 轮次 | 提案状态 | 原生选择 | 保留成绩 | 搜索调用 | 新任务调用 |', '|---|---:|---|---|---:|---:|---:|']
        for item in rows:
            for index,r in enumerate(item['rounds'],1):
                if r['status']=='pending':continue
                retained=f'{r["retained_resolved"]}/10' if 'retained_resolved' in r else 'N/A'
                if r.get('retained_score_reused'):retained+='（缓存）'
                lines.append('| '+' | '.join([item['framework'],str(index),r.get('proposal_status',r['status']),
                    r.get('native_selected','待定'),retained,str(r['optimizer_usage']['calls']),str(r['target_usage']['calls'])])+' |')
        overhead=result['prior_scope_overhead']
        lines+=['',f'旧五轮配置停下前已发生 {overhead["worker_executions"]} 次原版本复测；这部分轨迹、评分与调用全部留档并计入下述总数，不混为有效改进。HarnessFix 第1轮80次搜索账本直接引用，未重跑搜索。',
            '', f'含缩减前已发生消耗：{usage["calls"]} 次请求，{usage["actual_tokens"]:,} 已知实际 token；未知 usage {usage["unknown_usage_requests"]} 次，含预留 {usage["charged_or_reserved_tokens"]:,} token；任务执行 {count}/100。H0 历史基线成本单列，不重复当新消耗。',
            '', '100次上限包含旧配置已开始的复测；每个新候选先预留完整十题额度，余额不足十题则停止，避免超预算或用部分评分冒充十题结果。',
            '', '比较范围：同一十题上的两次原生单步适配 + 共同连续外层，继承上一轮保留 Harness 和完整公开轨迹；原生内部长期调度/archive局部重建，不是原论文全套长期算法复现。所有十题反复提供开发反馈，不代表未见任务泛化。','']
        (WORK/'report.md').write_text('\n'.join(lines))
    return result


if __name__=='__main__':print(json.dumps(summarize(),ensure_ascii=False,indent=2))
