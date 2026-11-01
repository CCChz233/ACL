# 50 次调用预算下的完整 RSI 单轮

日期：2026-10-17。当前是单题工程验收，不是完整 Benchmark 评测。

## 范围

重新从固定 mini-SWE-agent 原始 Harness 出发，执行基准 → 分析新轨迹 → 生成新 Harness → critic → 候选 smoke → 新容器执行 → 独立评分 → RRSI 选择及版本保存。

这是新预算下的一轮完整搜索，不复用此前冻结复测的基准或候选结果。仍使用开发题 `django__django-11790`，该题已经用于工程调试，不作未见评测。

## 固定配置

| 项目 | 设置 |
|---|---|
| 搜索引擎 | 固定官方 RRSI commit；上游源码不修改 |
| 目标 | 固定 mini-SWE-agent 2.4.6 的循环与模板副本 |
| 改进角色和执行器 | deepseek-flash；thinking 关闭；会话与用量独立 |
| 搜索总上限 | 160 次调用、2,000,000 token |
| 每次目标执行上限 | 50 次调用、1,000,000 token、1,200 秒 |
| 规模 | 1 题 × 1 次基准；1 轮 × 1 个候选 × 每题 1 次 |
| 候选审核 | 最多 1 次 critic 修复 |
| 选择 | delta=0、w_c=0、w_n=0；同分候选不能靠省 token 或新颖性被接纳 |
| 轨迹采样 | n_fail_traces=1、n_success_traces=1；允许分析成功基准 |
| 评分 | 官方 SWE-bench 4.1，新容器评分实际提交；空提交直接失败 |

完整配置见 [full-cycle-50.json](../../configs/full-cycle-50.json)。分数优先属于明确披露的 RRSI 配置适配；不能将本轮结果说成原论文任务、模型和完整优化目标的数值复现。若基准满分，候选同分时保留原版本是预期行为。

## 复现与证据

```sh
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json smoke
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json run
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json status
```

新工作区为 `work/rrsi-full-cycle-50/`，之前的工程运行和冻结复测目录均保留。

- `repo/source_manifest.json`：上游版本与源文件、数据、配置、运行代码哈希。
- `authorization.json`：本轮公开材料和预算授权范围。
- `search_usage.json`：全部搜索角色的实际 API 用量。
- `runs/swe/r0/`：分析、提案、diff、critic、smoke、评测和选择。
- `runs/swe/jobs/`：基准与新候选的真实轨迹、补丁、实际 token、停止原因及官方评分。
- `runs/swe/frontier.json`、`summary.json`：保留版本及完整轮次汇总。

## 当前状态

本轮已完成，机器可读证据见 [full_cycle_50.json](full_cycle_50.json)。

| 阶段 | 实际结果 |
|---|---|
| 新基准 | 13 次调用、67,696 token；提交实际补丁，官方 resolved=true |
| 搜索 | 17 次调用、110,854 token；analyst 2、digester 8、propose 6、critic 1 |
| 新提案 | 修改通用工作流提示，加入版本检查、跨文件赋值顺序追踪、UTF-8 编辑及先窄后宽的测试建议 |
| Critic / smoke | 均通过，无需修复 |
| 新候选 | 22 次调用、210,055 token；提交实际补丁，官方 resolved=true |
| 最终选择 | 两者同为 1/1，通过分数没有提升；拒绝候选，H₁=H₀ |

本轮合计 **52 次 API 调用、388,605 实际 token**，在已记录的预算内。完成后的恢复命令未增加调用；任务及评分容器均已清理。

候选 commit 为 `5ebe4d2`，最终保留基准 `43c7e75`。候选 token 约为基准 3.10 倍，这是本次观测，不是重复估计。选择拒绝的直接原因是分数没有提升，不能将关闭成本奖励后的决定说成单纯因费用过高。

基准与候选的独立官方报告分别保存在 `runs/swe/jobs/base/` 和 `runs/swe/jobs/r0A/` 对应 trial 目录下的 official 子目录；候选修改见 `runs/swe/r0/A/diff.patch`，原始选择理由见 `runs/swe/r0/decisions.json`。

**工程链路完整通过，没有观察到改进收益。** 原始基准已达单题满分，这一配置没有成功率上涨空间；后续应依预先固定的开发任务清单评估，而不是以这题单次结果判断通用能力。

## 结论边界

本轮验证较高预算下的新搜索能否实际走完整条链路。单题、单候选、单次执行无法估计稳定收益、改进者能力差异、泛化或递归加速。后续应按固定协议扩展开发任务并做独立重复，分别统计提交率、官方通过率、候选接纳及全部成本；当前不启动训练。
