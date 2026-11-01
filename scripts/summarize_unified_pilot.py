"""Create a readable, source-validated report after the current batch; no model calls."""
import argparse
import json
from pathlib import Path
import time

from acl_frameworks.common import ROOT,read,sha
from acl_gepa_swe.feedback import record
from acl_rsi.settings import write_json
from acl_unified.protocol import WORK,FRAMEWORKS,CONFIG
from acl_unified.status import summarize


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait',action='store_true')
    args=parser.parse_args()
    if args.wait:
        while True:
            state=read(WORK/'batch-status.json')
            if state['status'] not in ('running','waiting_fresh_baseline'):break
            time.sleep(30)
    result=summarize()
    cfg=read(CONFIG);p=cfg['protocol']
    instances={i['instance_id']:i for i in read(ROOT/cfg['dataset'])}
    baseline={}
    evidence={}
    for iid in p['all_task_ids']:
        trial=WORK/'baseline/evaluations/h0/trials'/iid
        baseline[iid]=record(trial,iid,instances[iid],trace=False)['score']
        evidence[str((trial/'grade.json').relative_to(ROOT))]=sha(trial/'grade.json')
    assert baseline==result['baseline']['scores']
    rows=[]
    for name in FRAMEWORKS:
        folder=WORK/name
        item=result['frameworks'][name]
        candidate=item.get('candidate_report_scores')
        chosen=item.get('selected_report_scores')
        if candidate is not None:
            assert set(candidate)==set(p['report_ids'])
            nomination=read(folder/'nomination.json')
            for f,digest in nomination['candidate_sha256'].items():
                assert sha(folder/'evaluations/candidate/harness'/f)==digest
            measured={}
            for iid in p['all_task_ids']:
                trial=folder/'evaluations/candidate/trials'/iid
                measured[iid]=record(trial,iid,instances[iid],trace=False)['score']
                evidence[str((trial/'grade.json').relative_to(ROOT))]=sha(trial/'grade.json')
                if iid in p['report_ids']:
                    assert read(trial/'worker-attempt.json')['started_at']>=nomination['frozen_at']
            assert measured==item['raw_candidate_all10']
            assert {i:measured[i] for i in p['report_ids']}==candidate
            expected=candidate if item['selected']=='candidate' else {i:baseline[i] for i in p['report_ids']}
            assert chosen==expected
        elif chosen is not None:
            assert item['selected']=='h0'
            assert chosen=={i:baseline[i] for i in p['report_ids']}
        rows.append({'framework':name,'status':item['status'],'raw_candidate_report_resolved':
            int(sum(candidate.values())) if candidate is not None else None,
            'selected':item.get('selected'),'selected_report_resolved':int(sum(chosen.values())) if chosen is not None else None,
            'raw_candidate_all10_resolved':int(sum(item['raw_candidate_all10'].values())) if item.get('raw_candidate_all10') else None,
            'newly_resolved_report':[i for i in p['report_ids'] if candidate is not None and candidate[i]>baseline[i]],
            'regressions_report':[i for i in p['report_ids'] if candidate is not None and candidate[i]<baseline[i]],
            'graded_candidate_tasks':item['graded_tasks'],'optimizer_usage':item['optimizer_usage'],'target_usage':item['target_usage']})
    write_json(WORK/'validated-report.json',{'batch':result.get('batch'),
        'scope':'historical development panel, four dev/six prospectively sealed report tasks',
        'fresh_baseline_all10':int(sum(baseline.values())),
        'fresh_baseline_report':int(sum(baseline[i] for i in p['report_ids'])),
        'frameworks':rows,'whole_experiment_usage':result['whole_experiment_usage'],
        'grade_sha256':evidence,'no_extra_api_calls_in_report':True})
    def value(n,denom):return '未得到有效候选评分' if n is None else f'{n}/{denom}'
    labels={'completed':'完成','running':'运行中','pending':'排队',
        'budget_exhausted':'搜索预算保护停止','native_run_failed':'原生阶段未完成',
        'invalid_candidate':'候选未通过统一约束','native_finished_without_scored_candidate':'原生流程未产生可评分候选',
        'infrastructure_stopped':'基础设施停止'}
    lines=['# 五框架统一十题结果','',
        f'新共同基线：全十题 {int(sum(baseline.values()))}/10；四题开发 {int(sum(baseline[i] for i in p["development_ids"]))}/4；六题评测 {int(sum(baseline[i] for i in p["report_ids"]))}/6。','',
        '六题只在候选与保留决定冻结后评测；所有十题均为历史开发数据，不能称为未见测试集。未生成候选、候选无效与基础设施错误不会填成 0/6。','',
        '| 框架 | 状态 | 原始候选：六题 | 最终保留版本：六题 | 候选十题（描述性） | 已评分候选题数 |',
        '|---|---|---:|---:|---:|---:|']
    for r in rows:
        selected='未取得有效读数' if r['selected_report_resolved'] is None else f'{r["selected"]}：{r["selected_report_resolved"]}/6'
        lines.append(f'| {r["framework"]} | {labels.get(r["status"],r["status"])} | {value(r["raw_candidate_report_resolved"],6)} | {selected} | {value(r["raw_candidate_all10_resolved"],10)} | {r["graded_candidate_tasks"]} |')
    lines+=['','| 框架 | 搜索调用 | 搜索已知 token | 任务调用 | 任务已知 token |','|---|---:|---:|---:|---:|']
    for r in rows:
        a,b=r['optimizer_usage'],r['target_usage']
        lines.append(f'| {r["framework"]} | {a["calls"]} | {a["actual_tokens"]:,} | {b["calls"]} | {b["actual_tokens"]:,} |')
    u=result['whole_experiment_usage']
    lines+=['',f'含共同基线的全轮累计：{u["calls"]} 次请求，{u["actual_tokens"]:,} 个已知实际 token；'
        f'{u["unknown_usage_requests"]} 次请求暂无 usage，保守预留合计 {u["charged_or_reserved_tokens"]:,} token。未估计金额。','',
        '拒绝候选后保留 H0 的成绩来自新共同基线，不能误解为候选通过数。原生 archive/frontier 的接纳机制按各框架保留；本轮只比较一个候选，不能代表多轮进化能力。','',
        '完整证据位于各框架 optimizer-api、nomination.json、result.json 和 evaluations/candidate/trials。协议见 docs/unified_framework_pilot.md。','']
    (WORK/'report.md').write_text('\n'.join(lines))
    print(json.dumps({'report':str(WORK/'report.md'),'frameworks':rows},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
