# 文档导航

更新：2026-10-20。现行方案、最新结果、运行说明和历史协议分开查找。后续头脑风暴不自动替换已落地的研究定义；历史文档中的日期、试跑状态保留当时含义。

文档已实际分为 [research/](research/README.md)、[frameworks/](frameworks/README.md)、[experiments/](experiments/README.md) 和 [operations/](operations/README.md)。一级目录中的旧同名路径为兼容链接，只有一份实际内容；日常打开、编辑和新增文档使用子目录正式路径。原有三份来源锁仍保留原位。

## 现行研究与维护入口

| 主题 | 文档 |
|---|---|
| 目录职责与维护约定 | [project_structure.md](project_structure.md) |
| RSI 领域脉络、原文与逐篇导读 | [研究脉络](../references/papers/rsi-research-lineage-2026-10-21/RSI研究脉络.md)、[资料库](../references/papers/rsi-research-lineage-2026-10-21/README.md) |
| 当前唯一研究故事：证据高效上下文 | [research_story.md](research/research_story.md) |
| 深化设计：证据需求、移除/补回与读取策略 | [evidence_research_agenda.md](research/evidence_research_agenda.md) |
| 研究计划与下一步 | [research_plan.md](research/research_plan.md)、[next_steps.md](research/next_steps.md) |
| 当前上下文对照 / RSI 框架验证 | [harness_baselines.md](research/harness_baselines.md) |

## 最新实验与分析

| 主题 | 文档 |
|---|---|
| 最新高预算两轮及补全 | [协议](experiments/multiround_highbudget.md)、[补全说明](experiments/multiround_completion.md)、[最终结果](../experiments/runs/full10-highbudget-completion-v1/report.md) |
| 无 RSI 基线、新增与退化的逐题分析 | [analysis.md](../reports/exports/full10-two-rounds-analysis/analysis.md) |
| 同轮后期修改的提交协议退化核验 | [findings.md](../reports/exports/within-round-audit-2026-10-20/findings.md) |
| 全量实验批次 | [实验索引](../experiments/README.md)、[分类目录](../experiments/CATALOG.md) |
| 组会与其他导出报告 | [报告索引](../reports/README.md) |

## 运行、接入与资源

| 主题 | 文档 |
|---|---|
| 运行说明 | [runtime.md](operations/runtime.md) |
| Mini50 镜像保留与运行入口 | [swe_mini_image_cache.md](operations/swe_mini_image_cache.md) |
| 配置与脚本分类入口 | [configs](../configs/README.md)、[scripts](../scripts/README.md) |
| 新框架接入与离线验收 | [framework_integration.md](frameworks/framework_integration.md) |
| 新框架最小真实闭环 | [framework_live_pilot.md](frameworks/framework_live_pilot.md) |
| DGM 原生 archive 与 mini 自修改接入 | [dgm_integration.md](frameworks/dgm_integration.md) |
| RSIHub 源码钉住（拟作后续底座，尚未实跑） | [rsihub_integration.md](frameworks/rsihub_integration.md) |
| 来源筛选与复现边界 | [rsi_framework_selection.md](frameworks/rsi_framework_selection.md)、[rrsi_paper_reproduction.md](frameworks/rrsi_paper_reproduction.md) |
| 元数据与资源核查历史 | [metadata_audit.md](operations/metadata_audit.md)、[docker_inventory.md](operations/docker_inventory.md) |

## 历史协议与开发试跑

| 主题 | 文档 |
|---|---|
| DGM 困难十题选择与真实试跑 | [dgm_hard10.md](experiments/dgm_hard10.md) |
| 五框架统一四题开发／六题评测试跑 | [unified_framework_pilot.md](experiments/unified_framework_pilot.md) |
| 五框架统一十题最终结果与完整用量 | [report.md](../experiments/runs/unified-hard10-v1-completion/report.md) |
| 历史低预算：五框架统一两轮，仅评测有效新 Harness | [multiround_two_rounds.md](experiments/multiround_two_rounds.md) · [历史结果表](../experiments/runs/full10-two-rounds-v1/report.md) |
| 已缩减的五轮原方案与原始记录 | [multiround_full10.md](experiments/multiround_full10.md) |
| 已退出的旧故事与 Baseline | [旧故事归档](archive/2026-10-19-before-context-story/README.md)、[早期外部经验方案](research/baseline_protocol.md) |
| SWE 原始基线 | [mini50_baseline.md](experiments/mini50_baseline.md) |
| SWE RRSI 结果 | [mini50_round1.md](experiments/mini50_round1.md) |
| SWE GEPA 结果与协议 | [gepa_swe_mini50.md](experiments/gepa_swe_mini50.md) |
| Terminal 基线与 RRSI | [terminal_pilot.md](experiments/terminal_pilot.md)、[terminal_round1.md](experiments/terminal_round1.md) |
| GEPA Terminal 接入 | [gepa_terminal_integration.md](experiments/gepa_terminal_integration.md) |

机器可读 JSON 随对应主题归类，旧路径仍可访问；来源锁的路径和字节保持不变。最新总体状态看根 [README](../README.md)，具体结果以对应工作区保存的证据为准。
