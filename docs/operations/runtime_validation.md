# 首轮工程验收记录

更新：2026-10-17。**一轮真实 RRSI 编排已完成，但没有得到任务能力提升。** 机器可读记录见 [runtime_validation.json](runtime_validation.json)，命令见 [运行说明](runtime.md)。

随后已完成 50 次调用／100 万 token 上限的冻结 Harness 复测：原始与候选均 10 次调用，实际补丁均通过官方评分，新增搜索为 0。完整结果见 [预算复测记录](../experiments/budget_recheck.md)。随后又完成新预算下的 [完整 RSI 单轮](../experiments/full_cycle_50.md)：重新测量基准、生成新候选并实际评分，二者均通过，同分保留 H₀。本轮 52 次调用、388,605 token，无收益证据。下文保留原先 24 次调用预算的一轮 RSI 记录。

最新另已完成 [全部 Mini 50 题原始基线](../experiments/mini50_baseline.md)：31/50（62%），1,153 次调用、15,443,407 token，基础设施缺失为 0，本批 RSI=0。后续 [全 50 题一轮 RSI](../experiments/mini50_round1.md) 也已完成：候选 29/50（58%），原始 31/50（62%），拒绝退步候选。搜索 168 次／1,067,853 token，候选执行 1,317 次／19,005,386 token。下文为历史单题工程记录，其分数和用量不能与最新批次混淆。

## 已验收的链路

官方 RRSI 的分析 → 提案 → critic → 候选 smoke → 实际任务执行 → 失败记分 → 上游选择 → Git 版本保存已经走完。目标为 mini-SWE-agent 2.4.6；改进角色和执行器均为 `deepseek-flash`，thinking 关闭。RRSI 上游搜索和选择源码保持原样。

Python 3.12 依赖锁安装通过；本机 ARM Docker 可运行官方 amd64 镜像。当前 22 项本地与上游测试通过，覆盖公开字段剥离、预算记账、缺失任务分母、真实 Git worktree 隔离和选择，以及批次进度、镜像所有权和父镜像保护。已完成运行的 `run` 命令再次执行，不会增加模型调用；本次已验证。

开发任务为 `django__django-11790`。官方镜像 digest：`sha256:061b5e37b0dfc15512b9604c843618b47aece8e603d08d0926c3990e0e9b3ac4`。参考补丁通过、无修复对照失败，二者均实际执行官方测试，证据在 `work/rrsi-smoke/grader_checks/summary.json`。

## 本轮实际结果

工作区：`work/rrsi-smoke-v3`。完整配置保存在该目录 `attempt-config.json`，来源/数据/适配代码哈希在 `repo/source_manifest.json`。

| 项目 | 原始 Harness | RRSI 候选 |
|---|---:|---:|
| Git commit | `4ff14f4` | `568ec2d` |
| 实际目标 API 调用 | 22 | 22 |
| 目标实际 token | 192,139 | 185,599 |
| 退出状态 | BudgetExceeded | BudgetExceeded |
| 提交补丁 | 无 | 无 |
| 任务分数 | 0 | 0 |

搜索端实际使用 51 次调用、531,242 token；四个角色均执行过，分别为 analyst 3、digester 36、propose 11、critic 1。加上基准和候选，本轮共 **95 次调用、908,980 token**，未超过授权预算。这里的 token 是累计输入和输出 usage，不是唯一上下文长度或美元费用。

候选只修改通用任务提示，加入完成条件、及时提交以及自编测试失败的排查顺序。critic 接受，语法/接口 smoke 通过，候选随后实际执行。

**两个新运行均因预算保护停止、没有提交，按空提交直接记 0；本轮候选没有执行官方测试。** 独立评分边界使用确定的空提交失败规则，不能将其说成“候选补丁通过/未通过官方测试”。官方测试链路由之前的参考/无修复对照及成功基准验收。

预算记账在发送请求前用 UTF-8 字节数和协议余量做保守预留，再按实际 API usage 结算。因此可能在实际调用数、实际 token 尚未达到标称上限时停止；本轮两次均在 22/24 次调用时停止。后续比较必须冻结并披露该计量规则，不能把这项工程行为当作模型能力结论。

## 选择规则暴露的问题

原配置为 `w_c=15`、`w_n=0`、`delta=0`。候选分数与基准同为 0，但目标 token 下降约 3.4%，上游 RRSI 的成本正则化规则因此接纳了候选。原始决定完整保留，**接纳不代表任务能力改善，也不代表应部署该候选**。

关键本地产物：

- `work/rrsi-smoke-v3/runs/swe/r0/A/diff.patch`：模型生成的 Harness 修改。
- `work/rrsi-smoke-v3/runs/swe/r0/A/critic.json`、`smoke.json`：审核与接口检查。
- `work/rrsi-smoke-v3/runs/swe/jobs/`：真实轨迹、用量、退出状态和评分。
- `work/rrsi-smoke-v3/runs/swe/r0/decisions.json`：原始接纳理由。
- `work/rrsi-smoke-v3/runs/swe/frontier.json`、`summary.json`：最终版本和汇总。

已准备 [smoke-score-first.json](../../configs/smoke-score-first.json)，仅将 `w_c` 调为 0，并使用新工作区；保留 `w_n=0`、`delta=0`，使同分候选无法单凭省 token 被接纳。使用本轮真实分数离线重放上游选择，结果为拒绝，见 `work/rrsi-smoke-v3/score_first_replay.json`；重放未调用 API，未改写原始结果。**新配置尚未启动真实搜索，也不宣称保留原论文完整目标。**

## 此前失败尝试全部保留

| 运行 | 结果 | 实际调用 | 实际 token |
|---|---|---:|---:|
| 原始 Harness 基准 1 | Submitted；官方 resolved=true | 11 | 52,371 |
| 原始 Harness 基准 2 | BudgetExceeded；未提交，按失败计 | 22 | 190,998 |
| 文本动作搜索 1 | 修复阶段预算耗尽；未评测候选 | 50 | 765,418 |
| 文本动作搜索 2 | 诊断阶段动作协议不稳定；预算耗尽，未评测候选 | 60 | 334,035 |
| 原生工具搜索 1 | 分析、提案与 critic 已执行；修复阶段预算耗尽，未评测候选 | 60 | 534,341 |

记录分别在 `work/rrsi-smoke` 与 `work/rrsi-smoke-v2`；极小 API 探测另存。失败记录没有删除，也不视为免费尝试。搜索协议、预算经过工程调试，不能将这些尝试当作冻结协议的正式重复实验。

文本协议曾使模型自行续写工具结果，原始 JSON 提取也会误处理字符串内的代码围栏。当前适配使用 DeepSeek 原生 `submit_rrsi_action` 传递动作，由 RRSI 执行真实工具。适配范围见运行说明。

启动本轮曾被自动审批拒绝；用户随后明确批准公开代码、公开题目及生成轨迹发送到 `https://api.deepseek.com`，并批准本轮付费预算。授权记录在 `work/rrsi-smoke-v3/authorization.json`。本轮结束后没有继续发起新搜索。

## 后续实验条件

冻结 Harness 复测已产生有效提交和官方评分。下一步校准多次运行的提交可靠性、预算和分数优先对照，再扩展到预先列为开发用途的 5–10 题，测独立重复与成本；之后决定正式样本规模。原始 Harness 在同一题上既成功也失败，当前无法估计稳定收益。

P0 候选 Python 在主机子进程中导入，尚不是完整的恶意代码沙箱。正式实验仍需独立数据划分、访问边界和噪声校准；目前没有模型间比较、训练、蒸馏或泛化结果。
