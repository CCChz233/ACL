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
    assert usage['calls']<=9000 and usage['charged_or_reserved_tokens']<=180000000 and count<=100
    result={'baseline':read(WORK/'baseline.json'),'frameworks':rows,'total_usage_including_prior_scope_spend':usage,
        'total_target_executions_including_prior_retests':count,
        'prior_scope_overhead':{'usage':ledger(legacy_usage_paths()),'worker_executions':len(legacy_worker_paths())},
        'batch':read(WORK/'batch-status.json') if (WORK/'batch-status.json').exists() else {'status':'not_started'}}
    if write:
        write_json(WORK/'summary.json',result)
        lines=['# 高预算两轮：真实 Harness 交付与完整十题评测','',
            '**第0轮共同原始 Agent：3/10。** DeepSeek Flash + mini-SWE-agent。每轮先交付通过门禁的实际修改，再评测完整十题。每轮搜索上限400次/800万token，含原生补全与模型修复。','',
            '| 方法 | 第0轮 | 第1轮 | 第2轮 |','|---|---:|---|---|', '| 原始 Agent | 3/10 | — | — |']
        for item in rows:
            cells=[]
            for r in item['rounds']:
                if r.get('round_scores') is not None:cell=f'{r["round_resolved"]}/10'
                elif r.get('evaluated_kind')=='unchanged_parent_reused':cell=f'未更新（沿用 {r["retained_resolved"]}/10）'
                else:cell='运行中' if r['status']=='running' else '待测' if r['status']=='pending' else '交付失败/中止'
                cells.append(cell)
            lines.append('| '+item['framework']+' | 共用 H0 | '+' | '.join(cells)+' |')
        lines+=['','本轮不得用缓存H0冒充成功交付；未生成有效修改时记交付失败。原始候选与原生保留版本分别展示。模型修复和原生续写都使用同一优化账本，单列来源。',
            '', '| 框架 | 轮次 | 提案状态 | 原生选择 | 保留成绩 | 搜索调用 | 新任务调用 |', '|---|---:|---|---|---:|---:|---:|']
        for item in rows:
            for index,r in enumerate(item['rounds'],1):
                if r['status']=='pending':continue
                retained=f'{r["retained_resolved"]}/10' if 'retained_resolved' in r else '交付失败/中止'
                if r.get('retained_score_reused'):retained+='（缓存）'
                lines.append('| '+' | '.join([item['framework'],str(index),r.get('proposal_status',r['status']),
                    r.get('native_selected','待定'),retained,str(r['optimizer_usage']['calls']),str(r['target_usage']['calls'])])+' |')
        lines+=['', f'本次独立高预算重跑：{usage["calls"]} 次请求，{usage["actual_tokens"]:,} 已知实际 token；未知 usage {usage["unknown_usage_requests"]} 次，含预留 {usage["charged_or_reserved_tokens"]:,} token；新任务执行 {count}/100。旧低预算成本单独留档，H0不重新执行。',
            '', '每轮400次/800万token总优化预算，其中原生阶段先用最多300次/600万，余量供原生续写及模型门禁修复；每题评测仍50次/100万token/1200秒。',
            '', '这是加大预算并要求产物交付的工程比较，含阶段上限调整和模型有效性修复，不等同于纯预算消融或未改原论文框架。所有十题均反复作为开发反馈；无人工候选编辑，旧源码和结果不改。','']
        (WORK/'report.md').write_text('\n'.join(lines))
    return result


if __name__=='__main__':print(json.dumps(summarize(),ensure_ascii=False,indent=2))
