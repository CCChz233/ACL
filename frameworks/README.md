# RSI / 自改进框架

这里保存官方源码的实际目录，旧 `repos/<name>` 是兼容链接。本项目适配代码放在 `acl_*` 包，不写入上游仓库。

2026-10-19：新增 [HarnessFix 官方源码](https://github.com/HarnessFix/HarnessFix)，与 Meta-Harness 均完成离线检查及含显式恢复的两题真实闭环；GEPA 与 RRSI 复用已有接入。具体边界见 [接入验收](../docs/frameworks/framework_integration.md)、[真实试跑](../docs/frameworks/framework_live_pilot.md)。当前研究比较框架内部上下文策略，正式对照尚未开始，详见 [研究故事](../docs/research/research_story.md)。

| 框架 | 目录 | 本项目状态 |
|---|---|---|
| HarnessFix | [harnessfix/](harnessfix) | 最小真实闭环通过；两题候选 1/2，基线 1/2，未接纳 |
| Google Research RRSI | [rrsi/](rrsi) | 已接入；SWE Mini50 单轮候选 29/50 |
| GEPA | [gepa/](gepa) | 已接入；SWE Mini50 单轮候选 25/50 |
| Stanford Meta-Harness | [meta-harness/](meta-harness) | adapted 最小真实闭环通过；两题候选 0/2，基线 1/2，保留 H0 |
| Darwin Gödel Machine | [dgm/](dgm) | DGM-adapted：原生外循环/谱系/父 mini 自修改边界离线通过，真实候选评分未运行 |
| ADAS | [adas/](adas) | 已下载并做离线检查 |
| Google Research Harness² | [harness2/](harness2) | 已下载并运行确定性离线示例 |
| SEAL | [seal/](seal) | 训练/适应路线参考，尚未用于 SWE 主线 |
| Absolute Zero Reasoner | [absolute-zero/](absolute-zero) | 自博弈/RL 路线参考，尚未用于 SWE 主线 |
| RSIHub | [rsihub/](rsihub) | 2026-11-01 钉住源码，拟作后续实验底座；尚未实跑。见 [接入说明](../docs/frameworks/rsihub_integration.md) |

框架的内嵌示例 Agent 保留在原仓库；独立 Agent 放在 [agents/](../agents/README.md)。固定版本继续由 [RRSI 来源锁](../docs/rrsi_sources.lock.json)、[框架来源锁](../docs/rsi_frameworks.sources.lock.json) 及历史 SEAL/AZR 记录管理。历史清单的旧路径继续有效。

新增框架登记 [project-layout.extensions.json](../configs/project-layout.extensions.json)，不改历史迁移锁。当前四套来源见 [registry.json](../configs/frameworks/registry.json)，用 `scripts/prepare_framework_integrations.py` 核验或恢复。背景与选择依据见 [框架筛选记录](../docs/frameworks/rsi_framework_selection.md)。

DGM 已有目录映射，追加锁为 [dgm.json](../configs/frameworks/dgm.json)。统一核验/恢复五套框架使用 `scripts/prepare_research_frameworks.py`；[DGM 说明](../docs/frameworks/dgm_integration.md) 区分离线验收与真实实验状态。

RSIHub 追加锁为 [rsihub.json](../configs/frameworks/rsihub.json)，核验入口 `scripts/prepare_rsihub.py`；不改五套已有锁。未装入项目 `.venv`。
