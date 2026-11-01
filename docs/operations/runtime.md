# RRSI × mini-SWE-agent × DeepSeek：运行说明

> 本文描述已完成的 RRSI 工程接入和历史协议，不是当前研究故事。2026-10-19 最新主线为 [证据高效上下文](../research/research_story.md)，最近待办为 [HarnessFix 调用链与成本审计](../research/next_steps.md)。历史模型比较或组件分析建议不再作为默认执行任务；原命令、预算和结果记录保留其原有含义。

2026-10-18 存储策略更新：SWE-bench Mini50 镜像永久保存在本地，后续统一使用 [本地缓存包装入口](swe_mini_image_cache.md)。下列旧命令和旧清理记录保留为历史协议；当前应改用 `scripts/run_swe_local.py baseline` / `rrsi-recovery` 等入口，避免旧运行器删除缓存。

更新：2026-10-17。**全 50 题的一轮 RSI 已完成：原始 31/50（62%），候选 29/50（58%），下降 4 个百分点，最终保留原始 Harness。** 候选仅修改通用任务提示；诊断预算耗尽后的恢复和成本均披露，详见 [本轮完整结果](../experiments/mini50_round1.md)。

原始基线记录：**全部 Verified Mini 50 题原始基线已完成：31/50（62%），无基础设施缺失。** 实际 1,153 次调用、15,443,407 token，本批 RSI=0；详见 [50 题结果报告](../experiments/mini50_baseline.md) 和 [冻结配置](../../configs/mini50-baseline.json)。

此前已完成 50 次调用／100 万 token 执行预算下的 [单题完整 RSI](../experiments/full_cycle_50.md)：新基准与新候选均通过，分数同为 1/1，最终保留原始 Harness。该轮共 52 次调用、388,605 token，未观察到改进收益；不能当作全 50 题的改进结果。

此前 [冻结 Harness 预算复测](../experiments/budget_recheck.md) 中，原始和已有候选均正常提交并通过官方测试；那次没有重新搜索。24 次预算下的首次 RRSI 记录、失败尝试及来源见 [历史验收记录](runtime_validation.md)，所有目录保留。

全 50 题基线入口如下；已完成工作区再次执行不会新增模型调用。本轮新增任务镜像标签已清理，原有 82 个镜像 ID 全部保留。

```sh
.venv/bin/python -m acl_rsi.mini50 --prepare-only
.venv/bin/python -m acl_rsi.mini50
```

完整 50 题 RSI 入口如下，复用原始基线，已完成工作区重复运行不会新增调用：

```sh
.venv/bin/python -m acl_rsi.resume_mini50_round --config configs/mini50-round1-recovery.json
.venv/bin/python scripts/summarize_mini50_round.py
```

本轮搜索累计上限 240 次／200 万 token，实际 168 次／1,067,853 token，包含首次失败的 160 次；候选执行 1,317 次／19,005,386 token。下一轮未启动；先分析退步与预算分配，再冻结后续验证划分。

## 固定组合

| 部分 | 当前设置 |
|---|---|
| RSI 搜索引擎 | 官方 google-research/rrsi，固定 [来源锁](../rrsi_sources.lock.json)，上游源码不改 |
| 被修改目标 | mini-SWE-agent 2.4.6 的 DefaultAgent 循环与 SWE-bench 模板副本；[来源锁](../agent_sources.lock.json) |
| 改进者 | analyst、digester、proposer、critic 均为 deepseek-flash |
| 执行器 | 独立会话的 deepseek-flash；thinking 关闭，独立用量记录 |
| 端点 | https://api.deepseek.com |
| 开发任务 | 最新基线为全部 Verified Mini 50 题；历史单题 RSI 为 django__django-11790；这些开发题不再作为未见测试 |
| 容器 | 本机 ARM Docker 运行官方 Linux/amd64 任务镜像 |
| 独立评分 | 官方 swebench==4.1.0，与已锁定的传统 Verified 数据兼容 |
| 规模 | 全 50 题已完成 1 轮、1 个新候选、每题 1 次；原始基线直接复用 |
| 选择 | 分数优先：delta=0、w_c=0、w_n=0；同分保留 H₀ |

成本奖励关闭是本次明确的配置适配，不能声称复现了原论文完整优化目标。该配置的阈值 0 未经噪声校准，不用于正式结果。

## 安装与检查

先恢复 [Benchmark 资产](../../benchmarks/README.md) 和固定上游源码；原始源码、数据与大型产物保留在忽略目录。

```sh
python3.12 scripts/prepare_agent_sources.py
uv --native-tls sync --locked --extra dev --python python3.12
```

恢复脚本克隆缺失的官方源码并检出固定 commit；已存在时核对版本和目标文件哈希，不覆盖本地修改。从 [.env.example](../../.env.example) 创建本地 `.env`，填写已授权端点和密钥；该文件不提交，不把密钥写进日志、配置清单或命令参数。

```sh
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json doctor
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json prepare
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json smoke
```

`doctor` 只报告版本、端点和密钥是否存在。`prepare` 创建实验 Git 仓库；`smoke` 检查语法与接口，均不调用模型。显式 `probe` 子命令会产生一次极小 API 调用。

## 历史单题完整单轮入口

预先拉取固定题目的官方镜像，并保留 digest：

```sh
docker pull --platform linux/amd64 docker.io/swebench/sweb.eval.x86_64.django_1776_django-11790:latest
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json run
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json status
```

`run` 从新的原始 Harness 基准开始，调用上游 Run.round 完成分析、提案、critic、候选 smoke、实际执行、评分及选择。也可依次使用 `baseline`、`round --round 0`。基准存在时 `baseline` 拒绝覆盖；完成一轮后再次 `run` 不会重开一轮。运行代码、配置和初始源码必须匹配来源清单；改变这些输入时使用新工作区。

参考补丁/无修复评分对照已经实际验收，证据在 `work/rrsi-smoke/grader_checks/summary.json`。需要独立复验时使用 `verify-grader`：参考补丁应通过，无修复对照应失败；对照创建无关标记文件，使官方测试实际执行。参考 patch、test patch 和预期测试结果不进入模型输入。

正常任务只有提交实际补丁才进入官方新容器测试；空提交直接按失败计分。候选实际执行、评分结果和最终选择均有记录，才称为完成候选执行验收；仅提案或 critic 接受不算完成。保留 H₀ 也是合法结果。

## 预算与动作适配

全 50 题基线不进行搜索：搜索上限为 0，全批目标上限为 2,500 次调用、5,000 万 token。以下 160 次调用、200 万 token 的搜索预算仅属于历史单题完整 RSI，覆盖四个搜索角色及最多一次 critic 修复。每次目标执行上限为 50 次调用、100 万累计 token、1,200 秒；单次输出 4,096 token，shell 命令超时 60 秒。基准和一个候选各有独立目标预算。

跨线程/进程账本先预留，再按真实 API usage 结算；预留使用 UTF-8 字节数和协议余量，可能提前停止。worker.json 的 budget_stop.reason 区分 call_limit、token_limit 和 token_reservation。累计 token 包含反复发送的上下文，不是唯一内容长度。失败请求保留预留额度，API 自动重试关闭。当前不估算美元费用；mini 内部零值 cost 不表示免费。

DeepSeek 原生函数 submit_rrsi_action 在既有模型调用边界传递 JSON 动作，由 RRSI 执行真实工具；原始响应单独保存。该桥接避免模型在文本中自行续写工具结果，并保留字符串内代码围栏。初始提示将“执行器是不同模型”改为“执行器独立配置”，以对应同型号设置。这些适配属于固定公共框架，跨模型比较前统一冻结。

## 输入、隔离与证据

可编辑范围是 mini 循环和模板副本，其他已安装 mini 库、模型包装、预算和评分器由外部固定。worker 只接收任务 ID、仓库身份、base commit 和问题描述。目标任务在禁网、固定 CPU/内存的独立容器执行；评分重新启动容器。候选版本由 RRSI 自身 Git worktree 管理，超时由外部进程监督并清理对应容器。

P0 仍在主机子进程中导入候选 Python，不是完整的恶意 Harness 沙箱。critic 和字段剥离不能代替正式访问边界验收。

最新完整 RSI 工作区为 `work/verified-mini-50-round1-recovery/`，逐题进度为 `progress-r0A.json`；原始基线在 `work/verified-mini-50-baseline-v2/`，另有 `progress.json`、镜像所有权与清理验证记录；下表也适用于历史单题 RSI 工作区 `work/rrsi-full-cycle-50/`，其中 `r0/` 和搜索用量仅在执行过搜索时产生。

| 路径 | 内容 |
|---|---|
| repo/source_manifest.json | 上游版本及目标、数据、配置、适配代码哈希 |
| authorization.json | 本轮授权材料和预算范围 |
| search_usage.json | 搜索角色调用及真实用量 |
| runs/swe/r0/ | 分析、提案、diff、critic、smoke、候选评分和选择 |
| runs/swe/jobs/ | 各任务输入、轨迹、补丁、用量、停止原因和评分产物 |
| runs/swe/frontier.json | 最终版本和演化轨迹 |
| summary.json / failure.json | 完成汇总或失败类型与已发生用量 |

任务缓存核对配置、Harness 哈希；评分缓存核对补丁哈希。基础设施故障保留前次证据，正常预算停止或无效修改按方法失败记录，不静默排除。

## 检查与后续

```sh
.venv/bin/python -m pytest -q tests repos/rrsi/tests
```

当前 22 项测试通过，覆盖公开字段剥离、预算原子预留及停止原因、缺失任务分母、真实 Git worktree 隔离、上游选择、批次进度、镜像所有权及父镜像保护。真实模型与官方评分另外验收。

全 50 题已完成一次基线和一个候选的比较，候选从 62% 降至 58%，没有本轮净收益。下一步先分析新增通过、退步和预算停止，冻结反馈/选择/封存划分，再决定后续轮数。一次执行不能估计方差；模型比较、因果机制和训练仍待独立实验。
