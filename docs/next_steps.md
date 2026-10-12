# Benchmark 补齐结果与下一步实验

日期：2026-10-12。范围为本地项目；未连接服务器，未调用模型 API 或启动实验。

## 本轮完成

| Benchmark | 数量 | 本轮确认 |
|---|---:|---|
| SWE-bench Pro V2 | 642 | 已有完整任务与资源，6,436 项官方 SHA256 校验通过 |
| Terminal-Bench 4.0.0 | 66 | 原来缺失的 181 个资源全部补齐，全部 3,200 个官方 Git blob 验证通过 |
| Terminal-Bench 2.1 | 89 | 新增完整源码与任务，全部 1,101 个官方 Git blob 验证通过 |
| SWE-bench Verified | 500 | 官方 SHA256、实际行数及任务 ID 唯一性验证通过，新增完整 JSON 与任务清单 |
| SWE-bench Verified Mini | 50 | 同上；确认 50 个任务都属于 Verified，新增排除 Mini 后的 450 个 ID |

统一任务清单保存在 `benchmarks/all_benchmark_tasks.csv`；来源与验证记录保存在 `benchmarks/`。目前共 1,347 个条目，不能把子集或版本条目当作独立样本相加。

本地源码与测试数据已经齐全。Docker 镜像拉取、任务构建及实际评分尚未完成，不能表述为所有 benchmark 已可运行。最近检查时 Docker 服务无法连接，Harbor 专用环境也未配置。

## 下一步优先打通一个无记忆基线

建议采用 Harbor 管理任务环境与评分，使用 mini-swe-agent 的简单执行循环作为固定 Solver harness，再加入我们自己的经验模块。Harbor 的官方入门路径要求 Python 3.12+，并支持 mini-swe-agent。[Harbor 官方 Quickstart](https://github.com/harbor-framework/docs/blob/main/quickstart.mdx)

本地已有 Pro V2 的 host-side mini-swe-agent 适配器和补丁重评分代码，可先复用接口；无需先把 SEAL 与 AZR 的整套训练依赖移植过来。适配器尚未运行验收，不能把“代码已有”理解为“兼容已确认”。

第一个交付物应是：固定任务版本、固定 Agent、固定预算的一条完整运行记录，包含工具动作、观察、补丁或最终状态、评分、失败类型和成本。

执行顺序：

1. 建立项目 Python 3.12 环境与依赖锁，检查 Harbor CLI 与 Agent 适配器导入。确定可运行 Linux/amd64 任务的容器后端；本轮先不改变服务器配置。
2. 用 1–3 个任务检查参考解、空 Agent/空补丁、任务重置和日志。Pro 要检查补丁在新环境中重新评分；终端任务检查任务状态及 verifier。该阶段只调基础设施，不根据最终测试任务调方法。
3. 接固定模型端点，运行无记忆 Agent，确认多步 bash 调用、结束动作、预算限制及完整轨迹保存。Mini 可作为明确披露的开发检查资产。
4. 基线闭环跑通后，从独立训练数据收集经验，在新开发任务上比较无记忆与外部记忆。此时才开始方法实验。

## 训练数据建议

代码优先从 SWE-smith 的现成任务选小规模子集。官方提供约 52K 可执行任务及容器接口，适合先收集轨迹；任务生成机制也便于后续 Trainer 修改课程和采样。作者明确说明其环境构建依赖 Docker，并主要支持 Ubuntu，因此在 Mac 上优先做数据整理和控制程序，而不是假定全部生成流程可直接运行。[SWE-smith 官方仓库](https://github.com/SWE-bench/SWE-smith)

SWE-Gym 可作为真实 issue 训练补充；其任务包含仓库上下文、可执行环境和测试反馈。第一轮先选一个来源，避免同时调试两套训练环境。[SWE-Gym 官方说明](https://github.com/SWE-Gym/SWE-Gym/blob/main/README.md)

终端训练候选优先 Tmax 的文本任务。它提供 Harbor 任务与程序化 verifier，但生成流程主要保证可执行性；这不能代替对任务描述、参考行为及 verifier 是否一致的质量检查。先审计一个小子集，暂不引入完整多模态任务池。[Tmax 数据说明](https://github.com/hamishivi/tmax/blob/master/rl_data/README.md)

建议预试跑规模为：代码 train 100–200 个、dev 与 meta-val 各约 20–30 个；终端在后续用小规模文本子集复现同一闭环。这些数字是工程起步建议，不能直接支撑论文结论。

代码按仓库划分并排除最终测试仓库、任务变体；终端按生成来源、模板及任务内容分组。随机拆实例或仅检查 task_id 不足以证明独立。本轮只核验了候选来源，尚未下载或划分训练集。

已生成 `benchmarks/test_repository_exclusions.json`，列出 Pro 的 11 个和 Verified 的 12 个测试仓库身份，共 23 个。Pro 身份由固定任务 ID 提取，下载训练候选时仍需核对规范仓库 URL 与血缘关系。这份清单可作为下一轮数据筛选的起点。

## 第一个方法实验与论文主线的关系

第一轮建议冻结模型权重，仅比较三个组：无记忆、相关经验检索、相同长度的不匹配经验控制。经验来自独立训练任务；统一模型、Agent、任务、上下文和总 token 预算，单独记录经验获取与检索成本。先判断收益是否来自有用经验，再接 SFT 或 RL。

这个实验能验证经验是否有效，不能独自证明 Trainer 自进化。后续还需让经验使用策略根据独立反馈更新，并在同一个 fresh Solver 上比较初始策略、演化策略与强固定策略，控制策略搜索和训练预算。

当前最值得推进的是“一个基线跑通 + 独立训练/开发小集”，随后实现经验模块。下一阶段不需要继续扩充最终 benchmark 数量。
