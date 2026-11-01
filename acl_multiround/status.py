"""Read-only result matrix, explicit parent retests, and complete new-run cost."""
import json
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from acl_unified.status import ledger
from .protocol import WORK,CONFIG,FRAMEWORKS,round_dir


def summarize(write=False):
    cfg=read(CONFIG)
    rows=[]
    for name in FRAMEWORKS:
        rounds=[]
        for index in range(1,6):
            folder=round_dir(name,index)
            p=folder/'result.json'
            value=read(p) if p.exists() else read(folder/'status.json') if (folder/'status.json').exists() else {'status':'pending'}
            value={k:v for k,v in value.items() if k not in ('native','next_parent')}
            value['optimizer_usage']=ledger([folder/'optimizer-api/usage.json']) if (folder/'optimizer-api/usage.json').exists() else ledger([])
            value['target_usage']=ledger(list(folder.glob('evaluations/*/trials/*/usage.json')))
            value['graded_tasks']=len(list(folder.glob('evaluations/*/trials/*/grade.json')))
            progress=folder/'progress.json'
            if progress.exists():value['progress']=read(progress)
            rounds.append(value)
        rows.append({'framework':name,'rounds':rounds})
    paths=list(WORK.glob('*/round-*/optimizer-api/usage.json'))+list(WORK.glob('*/round-*/evaluations/*/trials/*/usage.json'))
    usage=ledger(paths)
    count=len(list(WORK.glob('*/round-*/evaluations/*/trials/*/worker-attempt.json')))
    assert usage['calls']<=14500 and usage['charged_or_reserved_tokens']<=275000000 and count<=250
    value={'baseline':read(WORK/'baseline.json'),'frameworks':rows,'new_usage':usage,'new_target_executions':count,
        'batch':read(WORK/'batch-status.json') if (WORK/'batch-status.json').exists() else {'status':'not_started'}}
    if write:
        write_json(WORK/'summary.json',value)
        lines=['# 五框架 × 五轮：完整十题反馈与评测','',
            '**第0轮共同原始 Agent：3/10。** DeepSeek Flash + mini-SWE-agent。每轮完整十题反馈并评测；不使用四/六划分。','',
            '| 方法 | 第0轮 | 第1轮 | 第2轮 | 第3轮 | 第4轮 | 第5轮 |','|---|---:|---:|---:|---:|---:|---:|',
            '| 原始 Agent | 3/10 | — | — | — | — | — |']
        for item in rows:
            cells=[]
            for r in item['rounds']:
                if r.get('round_scores') is not None:
                    cell=f'{r["round_resolved"]}/10'
                    if r['evaluated_kind']=='unchanged_parent_retest':cell+='†'
                else:cell='运行中' if r['status']=='running' else '待测' if r['status']=='pending' else 'N/A'
                cells.append(cell)
            lines.append('| '+item['framework']+' | 共用 H0 | '+' | '.join(cells)+' |')
        lines+=['','† 本轮没有有效新候选，实际重测上一轮保留版本；波动不是已验证的 Harness 改进。N/A 代表不完整或错误，不填零。',
            '', '主表是本轮实际测试版本的原始成绩；各框架可能拒绝这个候选，下一轮使用原生保留版本。下面另列保留成绩，不能把缓存成绩说成重新执行。','',
            '| 框架 | 轮次 | 本轮测试对象 | 提案结果 | 原生选择 | 保留成绩 | 新搜索调用 | 新任务调用 |',
            '|---|---:|---|---|---|---:|---:|---:|']
        for item in rows:
            for index,r in enumerate(item['rounds'],1):
                if r['status']=='pending':continue
                retained=f'{r["retained_resolved"]}/10' if 'retained_resolved' in r else 'N/A'
                if r.get('retained_score_reused'):retained+='（缓存）'
                lines.append('| '+' | '.join([item['framework'],str(index),r.get('evaluated_kind','尚未完成'),
                    r.get('proposal_status',r['status']),r.get('native_selected','待定'),retained,
                    str(r['optimizer_usage']['calls']),str(r['target_usage']['calls'])])+' |')
        lines+=['',f'新增请求 {usage["calls"]}，已知实际 token {usage["actual_tokens"]:,}，未知 usage {usage["unknown_usage_requests"]} 次，实际/预留 {usage["charged_or_reserved_tokens"]:,} token；新任务执行 {count}/250。H0 历史成本单列于 baseline.json，未重新计作新消耗。',
            '', '范围：五个原生单步适配器 + 共同多轮外层；每步以同一框架上一轮保留的 Harness 及其十题轨迹为父代，保留原生接纳规则。原生长期 archive/调度在局部单步中重新初始化，先前公开失败摘要传递；不是原论文各自完整多代算法复现。',
            '', '十题全部反复作为开发反馈；不得称为未见测试集上的泛化收益。原始框架和旧实验不变。所有 50 个任务镜像永久保留。','']
        (WORK/'report.md').write_text('\n'.join(lines))
    return value


if __name__=='__main__':print(json.dumps(summarize(),ensure_ascii=False,indent=2))
