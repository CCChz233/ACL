# GEPA 接入 DeepSeek＋mini-SWE-agent

更新：2026-10-18。**接入代码与离线验收已完成，真实 GEPA 优化和候选 Benchmark 尚未启动。** 原始 Terminal 12 题基线已通过新接口导入，仍为 7/12，没有重跑基线或新增模型调用。首题镜像本次已成功下载并通过原始 ID 校验；其余镜像和容器内评分依赖的网络可用性仍未确认。

实现位于 `acl_gepa/`，配置为 [gepa-terminal-v1.json](../../configs/gepa-terminal-v1.json)，入口为 `python -m acl_gepa.run`。使用已锁定的 GEPA 官方提交 `f1cfdee2856e9dc4b5b4dc5cc2e391d0aa20d819` 和原生 `gepa.optimize`／`GEPAAdapter`，没有改写上游搜索源码，也没有修改冻结的 RRSI、mini 执行循环或旧基线。

## 1. 当前接入协议

| 项目 | 配置 |
|---|---|
| 改进与执行模型 | DeepSeek Flash，`https://api.deepseek.com`，thinking disabled |
| 初始 Harness | 原始 mini-SWE-agent 2.4.6 Terminal 提示与模板 |
| 编辑范围 | 一个 `terminal.yaml`；仅 system、instance、observation、format-error 四项文本 |
| 合法性检查 | 保留任务插值和完成命令；拒绝额外配置、任务 ID、私有评分路径、Jinja 调用与反射 |
| 原始证据 | `work/terminal-pilot-v1/` 的 12 道已有效评分任务，7/12 |
| GEPA 配置 | 单次原生迭代、最多一个新候选、全 12 题反思批次、Pareto 父候选选择、关闭 merge、seed=0 |
| 选择 | GEPA 原生严格提升；最终逐题汇总同分保留 H₀ |
| 搜索上限 | 80 次调用／100 万 token 的外部硬上限；本接入限制一次反思生成，不自动重采样或语法修复，实际最多 1 次新反思请求 |
| 目标每题上限 | 50 次调用、100 万累计 token、单次输出 4096 token、命令超时 60 秒 |
| 全候选执行上限 | 12 题各一次，最多 600 次目标调用／1200 万目标 token；wall limit 沿用原任务，最多 1200 秒 |
| 数据用途 | 同一 12 题开发集比较；没有封存测试或泛化结论 |

这是用于验收接口的受限 GEPA 配置，不是完整种群演化或 merge 效果复现。全批反思与此前 RRSI 的有界分角色诊断有所不同；正式方法比较要同时披露反馈组织、搜索成本和有效评测次数，不能直接归因为某个单独机制。

## 2. 数据与调用路径

`原始 YAML → 原生 GEPA → 公开轨迹反馈 → DeepSeek 反思 → 新 YAML → 原始 PilotAgent/DefaultAgent → 官方评分 → GEPA 接纳／保留原始版本`。

适配器把 `terminal.yaml` 当作 GEPA 的单一文本组件；反思模板明确要求通用机制修改和成功行为保留，没有采用默认模板中补入任务专用事实的引导。`make_reflective_dataset` 只提供任务 ID、公开任务／Agent 自身交互的有界摘录、binary reward、停止原因和用量，不提供测试内容、CTRF 测试名或 verifier 原始输出。

实际执行继续使用 `acl_terminal.agent:PilotAgent`，其内部仍为原始 mini `DefaultAgent`、ShellBridge 和预算模型。新 executor 只负责镜像校验、Harbor 配置、检查点与外部评分检查；没有增加执行模型可见工具或推理预算。

同一候选同一题复用已保存结果，重复读取不会产生新执行。YAML 仅格式或注释改变、实际配置未变时，复用原始基线，避免把对同一策略的随机重测当作 Harness 改进。不同真实候选由哈希标识，超过一个新候选会被拒绝。

GEPA 的内部 metric 计数包含导入的基线分数，不能直接解释为新执行次数或模型 API 次数。真实调用和 token 以外部 ledger 为准。

## 3. 评分有效性和恢复

数值 reward 不再单独构成有效评分。需要：无 trial／provider 基础设施异常、存在官方 CTRF、测试集合与原始该题一致、所有测试完成，并且测试结果与 binary reward 一致。

- 实际运行测试后未通过：有效方法结果，记 0 分。
- 评分依赖下载失败、缺测试记录、测试未跑完：中断批次，分数为 `null`，保留 H₀，不作为候选退步。
- 已存在未完成 trial：拒绝自动重跑，避免重复付费。
- 恢复反思：复用已保存的同一响应，校验上下文哈希；请求中断或上下文改变时停止，不重新采样。

Agent 完成后、grader 开始前，通过 Harbor `AGENT_END` hook 创建 `docker commit` 检查点。有效评分后删除检查点；首个评分异常会中断批次并保留该检查点，普通任务容器由 Harbor 清理。检查点只有容器文件系统，**不含 RAM、运行进程或挂载卷内容**，仅支持状态审计与显式恢复设计，不能声称能原样重放评分。当前没有实际 GEPA trial，因此未创建此类检查点。

磁盘在镜像获取前后均检查 4 GiB 下限；镜像 ID 和 amd64 架构必须与原基线一致。只清理本工作区新增的命名镜像／检查点标签，不执行全局 prune，不删除原有镜像。

## 4. 已完成的验收

相关 **16 项测试通过**，覆盖原生 GEPA 单候选流程、有效失败与评分初始化失败的区分、私有反馈隔离、重复执行缓存、部分中断恢复、模型请求及用量记录、编辑边界、镜像身份、下载后磁盘检查和检查点保留／清理。

另保存完整 CLI 离线示例：一次脚本化反思、两道模拟任务、原生 GEPA 提案与接纳，以及再次读取结果时零重复执行。示例使用预设响应和预设评分，**不代表 DeepSeek 提升了准确率**。真实模型 API、token 和 Docker 任务数均为 0。

验收索引见 [机器可读报告](gepa_terminal_integration.json)。详细记录位于：

- `work/gepa-integration-checks/pytest.xml`：测试结果。
- `work/gepa-integration-smoke/latest.json`：最新离线示例及产物目录。
- `work/gepa-terminal-v1/runtime-lock.json`：最终代码、配置、基线证据与镜像元数据哈希。
- `work/gepa-terminal-v1/preflight.json`：首题镜像预检。

首次 prepare 后、任何 API 调用前的磁盘检查补充已单独归档旧准备锁并重新锁定；没有在已发生模型调用后更换运行代码。

## 5. 运行与产物

使用现有环境，避免自动升级已冻结依赖：

```bash
export VIRTUAL_ENV="$PWD/.venv-terminal"
export UV_CACHE_DIR="$PWD/work/rsi-framework-selection/uv-cache"
export LITELLM_LOCAL_MODEL_COST_MAP=True
export PYTHONDONTWRITEBYTECODE=1

# 不调用模型：冻结／核对接入，导入已有基线。
uv run --active --no-project --no-env-file --offline python -m acl_gepa.run prepare

# 不调用模型：完整模拟示例。
uv run --active --no-project --no-env-file --offline python -m acl_gepa.run smoke

# 不调用模型：检查首题镜像；带参数时最多尝试拉取 60 秒。
uv run --active --no-project --no-env-file --offline python -m acl_gepa.run preflight --pull-first-image

# 以下会开始真实 DeepSeek 搜索与候选任务执行，产生 API 费用。
uv run --active --no-project --no-env-file --offline python -m acl_gepa.run run

# 复用同一提案和已完成题目；无效／未完成 trial 不自动付费重跑。
uv run --active --no-project --no-env-file --offline python -m acl_gepa.run resume

uv run --active --no-project --no-env-file --offline python -m acl_gepa.run summary
```

`uv --offline` 只禁止 uv 下载依赖，不禁止 run／resume 内的 DeepSeek 和 Docker 网络请求。真实命令从本地 `.env` 读取现有密钥，不将其写入配置和轨迹。preflight 的 `ready_for_first_image_only` 只表示首题镜像可用，不表示其余题目与 grader 网络均已验收。

真实运行将保存 `search_usage.json`、`search_requests/`、原始响应及延迟、反思输入／响应哈希、候选 YAML、逐题完整请求／响应／轨迹／官方评分、checkpoint 元数据和资源清理审计。当前真实 GEPA 候选、准确率及调用成本均尚未产生。

## 6. 当前资源状态

原有 82 个镜像 ID 全部保留，无本轮任务容器。新增首题缓存镜像的 Docker `Size` 为 518,975,750 字节，ID 为 `sha256:082fc8821b317f30fdfbf8d08d528874ce331c03e8083aef0406d48cdd7132a2`，与原基线一致；宿主机剩余约 13.91 GiB。这是 Docker 镜像逻辑大小，不等于 Docker 虚拟磁盘增长量。后续任务执行结束时按本工作区记录的原有镜像清单处理缓存标签。
