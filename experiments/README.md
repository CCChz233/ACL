# 实验索引

更新：2026-10-20。原始工作区统一在 `runs/`；根目录 `work/` 只是指向这里的兼容链接。**先从本页选实验批次，再读对应报告，不按文件夹名猜“最新成绩”。**

## 最新可比较的五框架结果

| 入口 | 用途 |
|---|---|
| [高预算两轮最终汇总](runs/full10-highbudget-completion-v1/report.md) | 最新完整表格、缺项补全说明及成本；共同 H0 3/10 |
| [合并审计](runs/full10-highbudget-completion-v1/final-audit.json) | 100 份候选逐题评分、来源锁与一致性检查 |
| [原高预算批次](runs/full10-highbudget-two-rounds-v1) | 原始 Meta-Harness、GEPA、RRSI 及原 HF/DGM 失败证据 |
| [补全批次](runs/full10-highbudget-completion-v1) | HF/DGM 补全与恢复记录、全批合并报告 |
| [逐题分析与无 RSI 对照](../reports/exports/full10-two-rounds-analysis/analysis.md) | 题目级新修复、退化、保留版本与限制 |

这两个高预算目录共同构成同一最终比较的证据，不是两个可直接相加的独立实验。原始候选与保留版本分开看，恢复成本保留。

## 历史批次：按协议查找

| 协议/用途 | 入口 | 阅读说明 |
|---|---|---|
| 低预算两轮 | [full10-two-rounds-v1](runs/full10-two-rounds-v1/report.md) | 已完成；未更新可能沿用父版本评分，不填入高预算表 |
| 原五轮计划 | [full10-five-rounds-v1](runs/full10-five-rounds-v1) | 已缩减并停止，历史尝试与成本保留 |
| 四题反馈/六题报告的统一试跑 | [unified-hard10-v1-completion](runs/unified-hard10-v1-completion/report.md) | 汇总原始、续跑和 DGM 恢复目录；不同于后来的全十题两轮 |
| DGM 困难十题开发 | [dgm-hard10-v1-recovery2](runs/dgm-hard10-v1-recovery2) | 原始/恢复阶段都保留；不能当统一高预算结果 |
| HarnessFix/Meta 最小闭环 | [framework-live-2026-10-19-v1](runs/framework-live-2026-10-19-v1) | 两题工程验收，含显式恢复 |
| Mini50 无 RSI 基线 | [verified-mini-50-baseline-v2](runs/verified-mini-50-baseline-v2) | 31/50；更早 baseline/v1 是准备历史 |
| Mini50 RRSI | [verified-mini-50-round1-recovery](runs/verified-mini-50-round1-recovery) | 29/50，旧单轮工程探索 |
| Mini50 GEPA | [gepa-mini50-v1](runs/gepa-mini50-v1) | 25/50，旧单轮工程探索 |
| Terminal 基线/RSI | [terminal-pilot-v1](runs/terminal-pilot-v1)、[terminal-round1](runs/terminal-round1) | 基线 7/12；RSI 仅两题有效评分，整轮未完成 |
| 来源、接口、镜像和目录核验 | [全量分类目录](CATALOG.md) | smoke、integration、audit 不是正式任务成绩 |

## 文件的含义

| 常见位置 | 内容 |
|---|---|
| `input-parent.json` | 本轮实际父版本、来源、已有评分 |
| `result.json` / `report.md` | 本轮决定与报告；须结合逐题记录确认 |
| `evaluations/candidate/harness/` | 已评分候选源码与提示 |
| `trials/<任务>/` | 轨迹、补丁、worker、官方 grade、请求及 usage |
| `selected/harness/` | 本轮后保留的版本；可能仍是父版本 |
| `runtime-lock.json` 等 | 实验时的源码/配置版本锁 |

截至本次整理，`runs/` 有 **42 个一级目录和 7 个散落的历史文件**，全部在 [CATALOG.md](CATALOG.md) 分类列出。散落文件含旧源码包、准备脚本、连接元数据和恢复日志，不代表额外七次实验；不打开连接文件读取凭据。其历史路径继续保留。

新实验建立新版本工作区，原始结果、失败和来源锁不覆盖。现有 Mini50/十题已用于开发；上下文与基本动作筛选的新研究实验尚未完成，不能把本页成绩改标成新方法效果。
