# Verified Mini：一轮 RSI 的完整 50 题结果

**本轮已完成。原始 Harness 为 31/50（62%），RSI 新候选为 29/50（58%），下降 4 个百分点。候选未被接纳，最终保留原始 Harness，保留版本的已测得分仍为 62%。** 这次真实完成了分析、模型提案、critic、接口检查、全 50 题执行、官方评分与选择。

## 改进前后对比

| 题目来源 | 题数 | 原始 Harness | RSI 候选 | 净变化 |
|---|---:|---:|---:|---:|
| Django | 25 | 18/25（72%） | 17/25（68%） | −1 题 |
| Sphinx | 25 | 13/25（52%） | 12/25（48%） | −1 题 |
| 全部 | 50 | 31/50（62%） | 29/50（58%） | −2 题／−4 个百分点 |

机器可读逐题结果、配对变化、版本和成本见 [mini50_round1_results.json](mini50_round1_results.json)。本轮复用已经完成的基线及完整轨迹，不重新付费跑基准；50 个任务 ID、数据哈希、目标模型、每题执行预算和实际镜像 digest 与基线一致。候选 50 题均完成计分，无基础设施缺失。

| 逐题配对变化 | 数量 | 任务 |
|---|---:|---|
| 原始失败、候选通过 | 2 | django__django-12039；sphinx-doc__sphinx-10435 |
| 原始通过、候选失败 | 4 | django__django-12406；django__django-12774；sphinx-doc__sphinx-10323；sphinx-doc__sphinx-8265 |
| 两者均通过 | 27 | 见逐题 JSON |
| 两者均失败 | 17 | 见逐题 JSON |

不能仅展示 2 个新增通过案例而忽略 4 个退步案例。以 django__django-12039 为例，新执行补丁覆盖了原始执行遗漏的共享逻辑，与候选提出的检查方向一致；但这不是提示修改导致收益的独立因果证据。

## RSI 实际改了什么

候选 commit `45a04e7`，仅修改 `swebench.yaml` 的通用任务工作流和提交前提示，没有新增工具、没有修改 Agent Python 执行循环、没有训练模型，也没有编码具体题目的修复答案。

新增要求包括：

1. 先列出问题描述中的具体需求与预期结果。
2. 检查生成相关结果的共享逻辑和其他分支，避免只修复复现脚本触及的路径。
3. 使用明确预期和断言验证边界，不能只凭自己的输出看起来合理。
4. 大量跳过测试、没有实际断言的绿灯不作为验证证据。
5. 提交前逐项对应需求与观察结果，验证充分后及时提交。

模型 critic 接受该通用提示修改，语法与接口 smoke 通过；这些检查没有保证其任务收益。候选在真实全量评测中退步，因此上游选择规则拒绝它。

## 失败分类与用量

| 项目 | 原始基线 | RSI 候选 |
|---|---:|---:|
| 实际提交并通过官方测试 | 31 | 29 |
| 实际提交但未通过官方测试 | 7 | 8 |
| token 请求预留不足，未提交 | 8 | 9 |
| 达到调用上限，未提交 | 4 | 4 |
| 目标模型调用 | 1,153 | 1,317 |
| 目标累计输入／输出 token | 15,443,407 | 19,005,386 |
| 每题平均 token | 308,868.14 | 380,107.72 |

候选共有 37 份实际补丁执行了官方独立测试；其余 13 题没有提交，按失败记 0。目标 token 增加约 23.1%，同时通过率下降。这里的预算停止包含保守预留检查，不表示每题实际花满 100 万 token。验证更繁重是否导致执行成本增长与退步，还需受控实验，不能仅由这次共变认定。

搜索总计 **168 次调用、1,067,853 token**，包含首次失败尝试的完整成本。角色为 analyst 4、digester 157、propose 6、critic 1。原始 160 次之外实际只新增 8 次，未用满批准追加的 80 次。

本轮新增总用量（搜索含失败尝试＋候选 50 题）为 **1,485 次调用、20,073,239 token**；复用的历史基线用量另列，不重复计入新增调用。未估算美元费用，token 为累计 API usage，包含重复发送上下文。

## 固定协议与恢复适配

目标设置：mini-SWE-agent 2.4.6、deepseek-flash、https://api.deepseek.com、thinking 关闭；其余未明确指定的采样参数采用提供商默认，无固定随机种子。每题最多 50 次调用、100 万累计 token、1,200 秒，输出上限 4,096 token，shell 超时 60 秒。评分器为官方 SWE-bench 4.1。

原始搜索配置：[mini50-round1.json](../../configs/mini50-round1.json)。1 轮、1 个候选、每题 1 次，分数优先：delta=0、w_c=0、w_n=0，同分或退步保留 H₀。诊断按上游排序选择最多 8 个低分任务与 3 个高分任务轨迹，不声称分析器读取了全部 50 份完整轨迹；候选评测覆盖全部 50 题。

首次搜索在诊断阶段反复调用 digest，160 次上限耗尽时尚未生成候选。实际花费 886,840 token，角色为 analyst 3、digester 157；保存 9 份摘要文件，其中 8 份正常返回、1 份达到 digester 轮数上限。

用户随后明确批准追加最多 80 次，累计搜索上限 240 次／200 万 token。使用 [恢复配置](../../configs/mini50-round1-recovery.json)，将原有 160 次调用及响应复制进累计账本；由模型单次汇总已有摘要和成功轨迹，禁止再次分派 digest，随后恢复标准提案、critic、评测与选择。上游仓库源码保持不变，但该恢复是明确的协议适配，不能当作完全未中断的原生 analyst 流程。首次失败工作区完整保留，不重置成本。

## 资源与复现

候选评测串行按需拉取镜像，仅清理本轮新增任务标签；原有 82 个镜像 ID 全部保留，本轮 owned 清单已清空。没有全局 prune 或 force 镜像删除。运行中低于 4 GiB 空闲即停止，本轮未触发。

恢复工作区约 57 MiB，包含复用基线副本、搜索记录、候选轨迹与评分记录；未保存每步完整容器文件系统快照。所有 50 份候选轨迹、1,317 份候选模型原始响应和 168 份累计搜索原始响应均保存。

```sh
.venv/bin/python -m acl_rsi.resume_mini50_round --config configs/mini50-round1-recovery.json --prepare-only
.venv/bin/python -m acl_rsi.resume_mini50_round --config configs/mini50-round1-recovery.json
.venv/bin/python scripts/summarize_mini50_round.py
```

完成后重复运行入口已验证不增加模型调用。22 项本地及上游工程测试通过。

工作区：`work/verified-mini-50-round1-recovery/`；首次失败记录：`work/verified-mini-50-round1/`。

| 路径 | 内容 |
|---|---|
| baseline_provenance.json | 基线复用来源与逐题证据哈希，原始文件不改写 |
| authorization.json / recovery_provenance.json | 预算批准、失败成本与恢复适配 |
| repo/source_manifest.json | 版本、数据、配置和运行代码哈希 |
| search_usage.json / search_usage-responses/ | 累计搜索调用与原始响应 |
| runs/swe/r0/analysis_report.json | 模型诊断报告 |
| runs/swe/r0/A/diff.patch / proposal.json | 实际 Harness 修改与模型提案 |
| runs/swe/r0/A/critic.json / smoke.json | 审核与接口检查 |
| runs/swe/jobs/r0A/ | 50 题输入、轨迹、补丁、账本及独立评分 |
| runs/swe/r0/decisions.json | 分数从 0.62 降至 0.58，拒绝候选的实际决定 |
| runs/swe/frontier.json | 完成 1 轮，保留原始版本 |
| progress-r0A.json / summary.json | 全 50 题分母下的完整结果与成本 |
| cleanup_validation.json / final_validation.json | 清理与最终核对证据 |

## 结论与下一步

本轮没有测到净收益：新增通过 2 题，同时退步 4 题，总分下降。它证明了候选生成、全量执行和拒绝退步候选的链路可运行，不能证明 self-improvement 能力已经增强，也不能凭一次运行判断模型间能力差异。

当前仅为同一可见开发集、一个候选、每题一次的比较，尚无独立搜索重复、未见测试或因果机制结论。下一步优先分析新增通过与退步的轨迹、预算停止和诊断阶段资源分配，再冻结验证划分与干预；不直接凭这次结果启动训练或扩大模型矩阵。
