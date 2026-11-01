# 当前研究框架接入验收

本页记录 2026-10-19 的离线准备验收，保留该阶段含义。随后用户要求跑通真实闭环，新阶段及当前状态见 [真实试跑](framework_live_pilot.md)；不要将本页的“尚未实跑”当作后续工作区的实时状态。

| 框架 | 固定提交 | 当前状态 |
|---|---|---|
| HarnessFix | `9167a0b9a587` | 新增官方源码；原生 HTIR、管线 dry-run、接纳/拒绝规则通过离线检查 |
| Meta-Harness | `8123ccabe2b1` | 复用官方源码；新增 DeepSeek 文件工具提案器和 SWE 边界回调，原生进化/前沿更新通过测试 |
| GEPA | `f1cfdee2856e` | 复用已完成 Mini50 的原适配，不改历史实现 |
| RRSI | `be50316e1db0` | 复用已完成 Mini50 的原适配，不改历史实现 |

四套当前来源锁在 [registry.json](../../configs/frameworks/registry.json)，记录官方 URL、完整提交及关键文件哈希。其他已下载的 DGM、ADAS、Harness²、SEAL、Absolute Zero 保持参考状态。本轮不扩大到这些框架，也未实现 ContextEvolve-adapted、ACON-adapted 或 EAEC。

## 新代码与离线入口

新增 [acl_frameworks/](../../acl_frameworks)；上游 checkout 保持干净，现有冻结包不改动。离线 CLI 提供 `check`、`prepare`、`smoke`，默认模型固定 DeepSeek Flash、thinking=false，模型调用开关关闭，默认调用/token 上限均为 0。后续真实试跑使用独立 `acl_frameworks.live` 入口及版本化预算，不改变离线默认值。

从项目根目录使用已有 SWE 环境：

```sh
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/prepare_framework_integrations.py
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python -m acl_frameworks.cli check
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python -m acl_frameworks.cli smoke
```

准备脚本加 `--clone` 可恢复缺失的固定源码，已有目录不会被重置。每次 smoke 使用新工作区，保存来源/适配哈希、HTIR、原生 dry-run 日志和测试报告。`uv --offline` 仅约束依赖解析；本入口依靠模型开关和测试回调保证无付费调用。

验收证据：[smoke-v2/smoke-results.json](../../experiments/runs/framework-integration-2026-10-19/smoke-v2/smoke-results.json)、[原生管线日志](../../experiments/runs/framework-integration-2026-10-19/smoke-v2/harnessfix/native-pipeline-dry-run.log)。首次 smoke-v1 因上游 dry-run 仍要求评测文件而失败，保留目录；v2 在隔离副本加入明确标注的合成前置文件后通过。日志里的合成分数、`Best validation` 等输出都不是实验结果。

回归验证：SWE 环境 31 项、Terminal 环境 16 项测试通过；1,059 个历史冻结文件完整，锁文件检查通过，四套来源固定提交与关键哈希通过。机器可读汇总见 [verification.json](../../experiments/runs/framework-integration-2026-10-19/verification.json)。

## 适配边界和真实实验前待办

**HarnessFix。** 保留原生 HTIR、诊断→计划→修改→审计→训练/验证比较→接纳与停止流程。原生管线 dry-run 和接纳函数已实际调用；诊断/聚合/修复的真实模型调用尚未执行。内嵌 mini 是 2.2.7，我们保持已有 2.4.6，未安装或覆盖它。模型桥接为进程内 LiteLLM 注入；后续必须为每个原生子进程显式安装桥接、传播同一预算账本，不能直接运行上游脚本就假定已记账。2.4.6 的命令、路径和输出格式需在首个有界闭环进一步确认。

**Meta-Harness。** 直接复用官方 Terminal 示例的 `run_evolve`、候选队列和 frontier 更新逻辑，将 proposer 与 evaluator 替换成 SWE 边界。DeepSeek 提案器提供 Read/Glob/Grep/Write/Edit/Finish，访问限制在公开工作区；没有原版 Claude Code 的 Bash/Agent 工具。因此应称为 Meta-Harness-adapted，不能宣称原版工具配置等价。当前离线 evaluator 使用明确标注的合成回报测试控制流；真实 SWE 执行器绑定、候选失败恢复、预算传播和试跑仍留给实验阶段。无效/缺失评分会中止，不会被记成模型失败 0 分。

**上下文与元数据。** 两个历史开发任务只作接口夹具，导出公开题面、模型自己的交互和二值反馈，私有官方 grader 日志不进入优化器。HarnessFix 原版会读取更多评分详情；这是本适配的显式权限差异，后续所有上下文组须保持一致。Full 当前指可按需读取全部公开文件，不是一次性长文本拼接。

已提供逐次请求载荷、原始响应、真实 usage、角色/策略及 API 耗时记账接口；失败且缺 usage 的请求保留 token 预留，不当作免费。文件读取记录路径、哈希、offset 与长度。该记账接口已用模拟 SDK 测试，尚未经新框架真实 API 请求验证；分阶段成本标注、缓存费用、组织器与执行侧总成本汇总仍需补齐。

**许可证。** HarnessFix 固定版本没有根许可证文件；不把 vendored mini 的 MIT 误当整个框架的许可证。研究复用来源如实登记；公开再分发前需确认上游授权。

## 后续实验顺序

先冻结新工作区、开发/选择任务、调用/token/时间预算，以及本地镜像保留规则，再完成 HarnessFix 一次最小真实闭环和成本审计。之后做共享轨迹的上下文配对实验，验证信号后再进入多轮 RSI 和 Meta-Harness 确认。Mini50 是历史开发数据，不能当新的未见测试集；现有 31/50、29/50、25/50 不属于本轮结果。
