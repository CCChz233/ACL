"""Validate and combine frozen pilot, GEPA continuation and separate DGM bug fix."""
import json
from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import write_json,load_instances
from acl_gepa_swe.feedback import record
from acl_unified import common
from acl_unified.protocol import WORK,FRAMEWORKS
from acl_unified.status import ledger
from scripts.continue_unified_pilot import CONT,verify_original

REC=ROOT/'experiments/runs/unified-hard10-v1-dgm-empty-recovery1'
OUT=ROOT/'experiments/runs/unified-hard10-v1-completion'


def main():
    verify_original(read(CONT/'authorization.json'))
    cfg=common.settings('gepa');p=cfg['protocol'];instances=load_instances(cfg)
    evidence={};baseline={}
    for iid in p['all_task_ids']:
        trial=common.baseline_trial(iid)
        baseline[iid]=record(trial,iid,instances[iid],trace=False)['score']
        evidence[str((trial/'grade.json').relative_to(ROOT))]=sha(trial/'grade.json')
    rows=[];all_usage=list(WORK.glob('*/evaluations/*/trials/*/usage.json'))
    all_usage+=list(WORK.glob('*/optimizer-api/usage.json'))
    all_usage+=list(CONT.glob('gepa/evaluations/candidate/trials/*/usage.json'))
    all_usage+=list(REC.glob('evaluations/candidate/trials/*/usage.json'))
    all_usage+=list(REC.glob('optimizer-api/usage.json'))
    for name in FRAMEWORKS:
        original=read(WORK/name/'result.json')
        folder=WORK/name
        result=original
        recovery=False
        if name=='gepa':result=read(CONT/'gepa/result.json');recovery=True
        if name=='dgm' and (REC/'result.json').exists():result=read(REC/'result.json');folder=REC;recovery=True
        scores=result.get('candidate_report_scores');all10=result.get('raw_candidate_all10')
        measured={}
        if scores is not None:
            nomination=read(folder/'nomination.json')
            assert common.fingerprint(folder/'evaluations/candidate/harness')==nomination['candidate_sha256']
            for iid in p['all_task_ids']:
                trial=ROOT/result['trial_sources'][iid] if 'trial_sources' in result else folder/'evaluations/candidate/trials'/iid
                measured[iid]=record(trial,iid,instances[iid],trace=False)['score']
                evidence[str((trial/'grade.json').relative_to(ROOT))]=sha(trial/'grade.json')
                if iid in p['report_ids']:assert read(trial/'worker-attempt.json')['started_at']>=nomination['frozen_at']
            assert measured==all10
            assert scores=={i:measured[i] for i in p['report_ids']}
        opt=[WORK/name/'optimizer-api/usage.json']
        targets=list((WORK/name).glob('evaluations/candidate/trials/*/usage.json'))
        if name=='gepa':targets+=list(CONT.glob('gepa/evaluations/candidate/trials/*/usage.json'))
        if name=='dgm':
            opt+=[REC/'optimizer-api/usage.json'];targets+=list(REC.glob('evaluations/candidate/trials/*/usage.json'))
        selected=result.get('selected',original.get('selected','h0'))
        chosen=measured if selected=='candidate' and measured else baseline if selected=='h0' else None
        row={'framework':name,'original_status':original['status'],'final_status':result['status'],
            'engineering_recovery':recovery,'selected':selected,
            'candidate_development':int(sum(measured[i] for i in p['development_ids'])) if measured else None,
            'candidate_report':int(sum(scores.values())) if scores is not None else None,
            'candidate_all10':int(sum(measured.values())) if measured else None,
            'selected_all10':int(sum(chosen.values())) if chosen else None,
            'newly_resolved':[i for i in measured if measured[i]>baseline[i]],
            'regressions':[i for i in measured if measured[i]<baseline[i]],
            'candidate_scores':measured or None,
            'optimizer_usage':ledger([q for q in opt if q.exists()]),'target_usage':ledger(targets)}
        if name=='dgm' and (REC/'offline-gate-recheck.json').exists():
            gate=read(REC/'offline-gate-recheck.json')
            assert gate['candidate_sha256']==common.fingerprint(REC/'optimizer/candidates/node_0000/harness')
            assert gate['model_calls']==0 and gate['status']=='invalid_candidate'
            row.update(raw_result_status=result['status'],final_status='invalid_candidate',candidate_gate=gate)
        assert row['optimizer_usage']['calls']<=80
        assert row['optimizer_usage']['charged_or_reserved_tokens']<=1000000
        if name=='dgm' and (REC/'status.json').exists() and not (REC/'result.json').exists():row['final_status']='running_bugfix_recovery'
        rows.append(row)
    assert len(all_usage)==len(set(all_usage))
    usage=ledger(all_usage)
    executions=len(list(WORK.glob('*/evaluations/*/trials/*/worker-attempt.json')))
    executions+=len(list(CONT.glob('gepa/evaluations/candidate/trials/*/worker-attempt.json')))
    executions+=len(list(REC.glob('evaluations/candidate/trials/*/worker-attempt.json')))
    assert usage['calls']<=3400 and usage['charged_or_reserved_tokens']<=65000000 and executions<=60
    result={'baseline':baseline,'frameworks':rows,'whole_experiment_usage':usage,'target_executions':executions,
        'grade_sha256':evidence,'all_task_ids':p['all_task_ids'],'development_ids':p['development_ids'],
        'report_ids':p['report_ids'],'scope':'historical development pilot; recoveries explicitly separated',
        'no_model_calls_in_report':True}
    write_json(OUT/'validated-summary.json',result)
    def n(value,total):return f'{value}/{total}' if value is not None else 'N/A'
    labels={'native_run_failed':'原生阶段失败','budget_exhausted':'搜索预算耗尽',
        'completed':'完成','completed_with_infrastructure_retry':'完成（连接中断续跑）',
        'invalid_candidate':'候选无效','infrastructure_stopped':'基础设施中断',
        'running_bugfix_recovery':'空列表修复后运行中'}
    lines=['# 五框架统一困难十题：最终汇总','',
        '**共同 H0：开发 1/4；冻结后评测 2/6；全十题 3/10。** 模型均为 DeepSeek Flash，目标均为 mini-SWE-agent；每框架一轮、最多一个候选。','',
        '| 框架 | 最后状态 | 候选开发四题 | 候选评测六题 | 候选十题 | 最终保留十题 |',
        '|---|---|---:|---:|---:|---:|']
    for r in rows:
        status=labels.get(r['final_status'],r['final_status'])
        if r['framework']=='dgm' and r['engineering_recovery']:status+='（空列表修复适配）'
        lines.append('| '+' | '.join([r['framework'],status,n(r['candidate_development'],4),n(r['candidate_report'],6),n(r['candidate_all10'],10),r['selected']+' '+n(r['selected_all10'],10)])+' |')
    lines+=['','N/A 表示没有有效完整候选读数，不是 0 分。没有产出候选时保留 H0，引用共同基线，不额外重跑十题。','',
        '## 原始失败和恢复边界','',
        '- HarnessFix：汇总阶段返回空计划，未生成可评分候选；不追加搜索。',
        '- Meta-Harness：触发 token 预留保护，实际消耗可以小于 100 万；未完成可评分候选。',
        '- RRSI：80 次调用在 analyst/digester 阶段耗尽，未生成候选；不追加搜索。',
        '- GEPA：候选、提名及六个已完成评分不变；APIConnectionError 后仅用原题预算余额重启一次，再补三道题。新上下文重启属于工程偏离，原失败成本仍计入。',
        '- DGM：原运行在任何模型调用前因 random.choice([]) 退出。独立恢复只将空 unresolved 列表兜底为原有 empty-patch 列表，保留 seed17、父代选择和 archive 规则；原始源码和失败结果未改。修复适配后 39 次搜索调用、864,518 实际 token，下一次请求触发 token 预留保护；部分候选因模板语法错误（unknown tag endif）未过统一门禁。原生包装为 RuntimeError 的结果原样保留，报告的候选无效分类来自另存的离线门禁复核；无额外模型调用、无人工候选修复。','',
        '## 逐题候选结果','', '| 任务 | 部分 | H0 | GEPA | DGM 修复适配 |','|---|---|---:|---:|---:|']
    byname={r['framework']:r for r in rows}
    for iid in p['all_task_ids']:
        vals=[str(int(baseline[iid]))]+[str(int(byname[name]['candidate_scores'][iid])) if byname[name]['candidate_scores'] else 'N/A' for name in ('gepa','dgm')]
        lines.append('| '+' | '.join([iid,'开发' if iid in p['development_ids'] else '冻结后评测']+vals)+' |')
    lines+=['','## 完整成本','', '| 框架 | 搜索调用 | 搜索已知 token | 任务调用 | 任务已知 token |', '|---|---:|---:|---:|---:|']
    for r in rows:
        a,b=r['optimizer_usage'],r['target_usage']
        lines.append(f'| {r["framework"]} | {a["calls"]} | {a["actual_tokens"]:,} | {b["calls"]} | {b["actual_tokens"]:,} |')
    lines+=['',f'包含 H0、所有失败和恢复：**{usage["calls"]} 次请求，{usage["actual_tokens"]:,} 已知实际 token**；未知 usage {usage["unknown_usage_requests"]} 次，实际/预留总计 {usage["charged_or_reserved_tokens"]:,} token；{executions} 次任务 worker 执行。不估计费用。','',
        '## 解释范围','',
        '十题均为历史开发数据；后六题仅在本轮优化反馈中封存。单次结果可以说明本次预算内能否形成有效候选及其观察收益，不能说明框架稳定优劣或独立泛化能力。无候选也不能直接解释为该框架永远无效。GEPA 与 DGM 的恢复和适配偏离必须随结果披露。','',
        '机器可审计结果见 validated-summary.json；其中包含逐题分数、评分文件摘要、完整分阶段用量。原始 formal 队列的 stopped 状态保持不变。','']
    (OUT/'report.md').write_text('\n'.join(lines))
    print(json.dumps({'report':str(OUT/'report.md'),'rows':rows,'usage':usage},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
