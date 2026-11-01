# 新框架真实闭环验收

2026-10-19 完成两套最小真实闭环，包含下文记录的显式恢复。这是工程验收，不是正式效果实验。结果以工作区保存的官方评分与最终 `result.json` 为准；仅有日志、API 返回或合成 smoke 不算跑通。

| 对象 | 两题总通过数 | 原生选择结果 |
|---|---|---|
| 复用的原始 H0 | 1/2 | 当前保留版本 |
| HarnessFix 候选 | 1/2 | 不接纳；验证集无净提升、目标指标无改善 |
| Meta-Harness 候选 | 0/2 | frontier 保留 H0 |

四份候选评分均通过官方报告、patch 哈希与 worker 对应核验，四次任务执行都实际调用了模型并提交 patch，无基础设施评分失败。[完整验收汇总](../../experiments/runs/framework-live-2026-10-19-v1/verification.json)；[HarnessFix 结果](../../experiments/runs/framework-live-2026-10-19-v1/harnessfix/result.json)；[Meta-Harness 结果](../../experiments/runs/framework-live-2026-10-19-v1/meta-harness/result.json)。

包含失败动作、被中断的优化过程及额外基线检查，全轮共 **186 次 API 调用、2,572,130 token**：输入 2,505,537、输出 66,593，API 报告缓存命中输入 2,300,288。186 对请求/响应和 usage 均核验，无未知 usage；缓存 token 已包含在输入中，不能重复相加，也没有据此估算美元费用。HF 优化 823,835、任务执行 258,332；Meta 优化 922,212、任务执行 488,798；额外基线检查 78,953。未增加总预算。

54 项离线/回归测试通过，1,059 个历史冻结文件未变，全部 50 个任务镜像再次验证并保留。最终实际使用的适配代码另存 `runtime-snapshot/`。本次验证了经恢复后的工程闭环，尚未验收无人值守多轮搜索，也不能当成未经恢复的标准 Full Context 实验。

工作区：[framework-live-2026-10-19-v1](../../experiments/runs/framework-live-2026-10-19-v1)，后台会话 `acl-framework-live-v1`。两套框架串行运行，各 1 轮、最多 1 个候选：先 HarnessFix，后 Meta-Harness。

## 固定设置与边界

- 模型：优化与任务执行均为 DeepSeek Flash，既有 DeepSeek 端点，thinking=false。
- 任务：`django__django-11790`、`django__django-11815`，均为已使用的 Mini50 开发题。原始基线分别 0/1、1/1；复用已验证轨迹和官方评分，不再付费重跑基线。
- 每框架优化上限：80 次调用、100 万 token，单次输出最多 4,096 token。分析、规划与实现共用同一账本。
- 每框架最多新增 2 个候选任务执行；每题最多 50 次调用、100 万 token，任务模型最多 1,200 秒，评分最多 900 秒。两框架合计最多 360 次调用、600 万 token；未知 usage 保留预留量。
- HarnessFix 将第一题作 train、第二题作 selection；第二题原始已成功，没有 resolve rate 上升空间，此设置用于检查候选执行和回归处理，不能用它判断方法收益。
- 两框架统一部署范围：mini 2.4.6 的 `agents/default.py` 与 SWE YAML；provider、评分、执行预算及其他模块不允许改动。变化范围是本次适配约束，不冒充原论文全部搜索空间。
- 模型和任务的请求、原始响应、usage、轨迹、候选、评分与停止原因全部保留。本地 50 个镜像校验后复用，永久保留。

## 实际执行绑定

[live.py](../../acl_frameworks/live.py) 为显式的付费入口，与默认禁用模型的离线 CLI 分开。`batch.py` 在 tmux 中串行驱动；每个框架最多运行 90 分钟，不自动重试付费任务。新工作区保存独立配置和适配代码哈希，配置或代码变化时拒绝悄悄续跑。

HarnessFix 运行其真实 `run_pipeline_swe.main`。SWE 执行/评分边界替换为已有可复验执行器和官方评分；诊断、聚合、实现、审计、指标比较、接纳、记忆和迭代报告继续使用原生代码。模型子脚本通过进程内调度运行，保证角色与共享预算注入，不再漏掉子进程调用。工具用无网络 Docker，公开快照只读、候选目录可写；没有项目 `.env`、宿主文件系统或私有评分挂载。

Meta-Harness 运行原生进化与 frontier 更新，替换 DeepSeek 文件提案器及真实 SWE evaluator。基线回调读取既有真实评分；候选回调实际运行任务并调用官方 grader。无效或缺失结果中止，不折成 0 分。

## 检查进度

```sh
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/framework_pilot_status.py experiments/runs/framework-live-2026-10-19-v1
```

`batch-status.json` 是进程状态；每框架 `status.json` 是运行状态。只有 `result.json` 的 `real_closed_loop_completed` 才表示候选经过真实评分，接纳或拒绝不影响“工程闭环是否完成”的判断。准确率提高是另一个问题，需要后续独立数据、配对任务和重复实验。

## 首轮故障与恢复记录

首个原生 HarnessFix 实现动作以 XML 命令块开头、DSML 工具标签结束；命令内容完整但原解析器报 0 个动作。仅对已观察到的单一开头和完整 DSML 尾部组合加入兼容解析，原始 API 响应不改写，归一化另存 `format-repairs/`。失败候选没有改动，通过原生审计被拒绝，未当作有效候选评分。

第一次恢复错误地使用原生 `start-version=2`；该入口默认基线是 v1，而不是“从拒绝的 v1 回到 H0”。因此多执行了一次与 H0 相同的任务，消耗 12 次调用、78,953 token，随后在“零失败样本”分析处停止。这是本项目恢复方式的错误；新增测试禁止这样启动。该次结果与旧拒绝候选移入 `recovery-attempt-1/`，不冒充改进结果。

再次恢复重用完成的诊断和计划，从真正 H0 开始。为覆盖额外消耗，HarnessFix 的优化上限降至 68 次调用、921,047 token；加上原始上限内的候选任务、Meta-Harness 和额外基线检查，全批上限仍是 360 次调用、600 万 token。账本没有重置，来源锁和每次修复的哈希另存，旧状态与报告均留档。

Meta-Harness 首次读取历史后达到了保守 token 预留阈值，已经写出的候选保留。补全 Read 的字符单位、Grep 的文件 glob/字面子串说明；在预算结束时，由同一模型审阅已有候选源码并调用 Finish，明确记录 `budget-finalization.json`。这是工程恢复与预算结束提交，不把它当作新的上下文方法或未经恢复的标准搜索实验。

HF 后续实现过程因保守 token 预留停止，但代码改动已经落盘；恢复后使用原生计划差异审计，确认所有计划目标覆盖、语法与范围合格，再实际评测。Meta 的首次 Finish 输出误把整个源码放入未约束对象并被截断；将协议补全为 `name/hypothesis/changes` 元数据后，模型完成有效提交。两种恢复均没有人工替模型编写候选。

额外的 H0 重跑在原本失败的第一题上通过，而两份候选在该题都失败，进一步说明小样本和采样波动很大。当前只确认四套主框架均有真实 SWE 闭环工程证据；正式上下文实验还要固定恢复/预算结束策略、共享证据快照、完整成本口径与独立确认数据。不能从这次 2 题验收得出 RSI 有效或无效的研究结论。
