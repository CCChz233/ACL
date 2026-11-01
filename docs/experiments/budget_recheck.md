# 提高执行预算：冻结 Harness 复测

日期：2026-10-17。目的：检查上一轮未提交是否与执行预算有关；不是重新搜索，也不是正式效果比较。

## 本轮设置

使用同一道开发题 `django__django-11790`，DeepSeek `deepseek-flash`，thinking 关闭，官方 Docker 任务镜像和独立 SWE-bench 评分保持一致。每个 Harness 各运行一次。

| 配置 | 前次 | 本次 |
|---|---:|---:|
| 单题模型调用上限 | 24 | 50 |
| 单题累计 token 上限 | 250,000 | 1,000,000 |
| 单次输出上限 | 4,096 | 4,096 |
| 单题时间上限 | 1,200 秒 | 1,200 秒 |
| shell 命令超时 | 60 秒 | 60 秒 |

原始 Harness 固定于 `4ff14f46023626d78c4dc24c6b321afe3adbd93c`，候选固定于 `568ec2d7cbf39eeefad93c10178e6a3f39e22400`，均来自上一轮本地实验仓库。新运行读取已提交 Git 对象，复制到各自独立快照，验证代码/数据/配置哈希；不继续修改候选。配置见 [budget-recheck.json](../../configs/budget-recheck.json)。

搜索预算字段沿用原配置，但本轮代码不调用任何搜索角色，不产生新搜索费用，不运行新的 RRSI 选择。

## 运行与产物

```sh
.venv/bin/python -m acl_rsi.recheck --prepare-only
.venv/bin/python -m acl_rsi.recheck
```

第一个命令只恢复固定快照、做语法与接口检查，不调用 API。第二个命令先执行原始 Harness，再执行候选，各自使用新容器；只有存在实际补丁时才进入官方测试，空提交直接按失败计分。完整评测记录可恢复，已完成的任务不会重新请求模型。

本地工作区：`work/budget-recheck-50/`。

- `manifest.json`：固定源 commit、模型、配置、数据及当前运行代码哈希。
- `snapshots/base/`、`snapshots/candidate/`：冻结的两个 Harness。
- `runs/swe/jobs/{base,candidate}/`：轨迹、实际调用、补丁、退出状态及独立评分。
- `summary.json`：两组结果及完成状态。
- `authorization.json`：本轮预算和外发授权范围。

## 停止原因

预算预留和结算算法保持原样，仅增加明确诊断字段。`worker.json` 的 `budget_stop.reason` 区分：

| 原因 | 含义 |
|---|---|
| `call_limit` | 调用数达到上限，包括 mini 自身步数检查 |
| `token_limit` | 已返回的实际 API token 达到上限 |
| `token_reservation` | 下一次请求的保守预留无法装入剩余额度，尚未发送请求 |

继续使用 UTF-8 字节数与协议余量估算预留；本轮没有同时调整估算方法、向模型增加预算提示或更改自动提交行为，以便单独检查提高预算的影响。预算计量和诊断测试共 15 项本地/上游测试通过。

## 当前状态

两次真实运行均已正常提交，并在新容器中通过官方测试。机器可读结果见 [budget_recheck.json](budget_recheck.json)。

| Harness | 实际调用 | 实际 token | 官方 resolved |
|---|---:|---:|---|
| 原始 Harness | 10 | 50,047 | true |
| 已有 RRSI 候选 | 10 | 52,779 | true |

本轮共 20 次 API 调用、102,826 token，新增搜索调用为 0。运行结束后的恢复命令也已检查，不会新增模型调用；任务容器已清理。

**本次证明两份 Harness 都能产生实际补丁并完成官方评分，但没有证明候选提升，也没有证明提高预算导致成功。** 两次都只用了 10 次调用、不到旧 token 上限；原始 Harness 在旧预算下也曾成功，所以随机性仍是竞争解释。本次候选比原始 Harness 多用约 5.5% token，单次差异不能当作稳定的成本变化。

新预算下没有重新执行 RRSI 分析、提案或选择；这里是对冻结代码的预算诊断。下一步应建立多个开发任务和独立重复，固定每组预算并分别报告提交率、官方通过率和实际成本。
