# DGM 困难十题试跑

2026-10-19。用户要求缩减到十题后，从过去三套 Harness 的真实运行记录确定开发集，再运行一代 DGM-adapted。候选生成前已冻结选题，不随本轮结果替换任务。

## 选择与解释范围

原始 H0、RRSI 候选、GEPA 候选共 150 份记录经原始 worker、patch 摘要、官方评分报告检查；全 50 题重新计数为 31、29、25 道通过。三套 Harness 的记录不是三个独立随机种子重复。

每个仓库选五题：调用上限失败、token 上限失败、反复未解决的非空提交（没有时用曾恢复的失败题）、曾被其他 Harness 修好的失败题、高成本且曾退步的成功题。层内按历史恢复次数、H0 token 排序，ID 打破平局。最终为 Django 五题、Sphinx 五题，八道 H0 失败、两道脆弱成功。详细 ID 和原始记录哈希见 [冻结选题](../../experiments/runs/hard10-selection-v1/selection.md) 与 [机器记录](../../experiments/runs/hard10-selection-v1/selection.json)。

历史通过数为 H0 **2/10**、RRSI 候选 **3/10**、GEPA 候选 **2/10**。这是按历史结果有意选出的困难开发集，不能估计完整 Mini50 或未见测试集的通过率，也不能据此公平排名三个框架。

## 冻结协议

- 优化器和任务模型均为 DeepSeek Flash，thinking=false，mini-SWE-agent 固定；仅允许修改 agent.py、swebench.yaml。
- DGM 原生外循环、父代选择与 keep_all archive；一代、一个新候选，seed=17。
- 复用已保存的 H0 十题结果；只新增十次候选任务执行。
- 诊断与实现共用上限 80 次调用、100 万 token；每题 50 次调用、100 万 token，输出上限 4096，任务墙钟上限 1200 秒。
- 全轮最多 580 次调用、1100 万 token。预留估算可使运行在实际累计 token 达到上限前停止；不自动追加预算或付费重试。
- 任务串行、仅使用已固定的本地 Docker 镜像，所有 Mini50 镜像永久保留；低于 4 GiB 空间保护线时停止。

配置：[dgm-hard10-v1.json](../../configs/dgm-hard10-v1.json)。初始运行：[dgm-hard10-v1](../../experiments/runs/dgm-hard10-v1)。运行源码副本、配置、集成锁均已保存。

## 状态与产物

原始候选在首题拦截提交时漏掉配对的 tool 结果，下一次 API 请求遭到 HTTP400 拒绝；该尝试保持无有效评分。第一次模型恢复补齐配对结果，但错误地把消息字典当作原始命令输出，离线检查拒绝，未开始任务。第二次模型恢复修正原始输出结构，通过单工具、多工具及重新提交检查后，已完成十题。

最终有效运行目录为 [dgm-hard10-v1-recovery2](../../experiments/runs/dgm-hard10-v1-recovery2)，后台 tmux 任务已正常退出。前一次恢复保存在 [recovery](../../experiments/runs/dgm-hard10-v1-recovery)。所有诊断、自修改和两次恢复共用初始 `optimizer-api/usage.json`，搜索账本没有重置；原始候选未改写。模型完成恢复，未由人手工修改候选实现。

十个唯一题目包含一次保留的失败尝试，之后为修复候选重新执行十次任务；每次新任务前，为其完整 50 次调用/100 万 token 检查剩余全轮预算，所有错误和恢复均计入原先 580 次调用、1100 万 token 上限。若剩余额度不足，不启动该题。结果应写作**经过接口恢复的工程试跑**，不作为未经干预的自主 DGM 复现。

最终结果以有效运行目录的 `result.json`、独立重验的 `validated-summary.json` 和逐题有效 `grade.json` 为准。没有评分的题保持未知，不能记为失败；DGM 将有效候选收入 archive 本身不表示改进。

只读进度命令（不发起模型调用）：

```sh
VIRTUAL_ENV="$PWD/.venv" UV_CACHE_DIR="$PWD/.cache/uv" uv run --active --no-project --no-env-file --offline python -m acl_dgm.experiment status --work experiments/runs/dgm-hard10-v1-recovery2
```

优化阶段保留诊断、实现完整轨迹、逐次请求与原始响应、usage 账本；候选阶段保留冻结 Harness、每题完整交互、patch、worker 状态、官方评分和调用/token 信息。最终比较应同时报告新增解决、回归、空提交、预算终止和基础设施错误。

恢复目录的只读通用 status 命令仅显示当地任务用量；全轮优化用量请读取初始目录的共享账本，完整累计消耗保存在恢复目录 `progress.json` 与最终汇总中。选题审计 [notebook](../../experiments/runs/hard10-selection-v1/selection-audit.ipynb) 已从上到下执行，重新验证 150 份历史记录及十题名单，全程零模型请求。

## 最终结果

独立重验后，**历史 H0 为 2/10，恢复后候选为 4/10**。新增解决 Django-12209、Django-12039、Sphinx-10435、Sphinx-10466；回归 Django-12406、Sphinx-8551。两个原有成功均未保住，净增两题。这是一次正向观测，尚不能证明稳定改进。

三个失败为空提交：Django-12273 耗尽 50 次调用，Sphinx-11510、Sphinx-10673 触发 token 预算保护；其余三个失败为已提交补丁但未通过官方测试。最终十题没有基础设施或 API 错误被填成失败；原始失败尝试单独保留为未评分。

搜索（含恢复）66 次调用、960,130 token；十次有效候选执行 353 次调用、5,321,405 token；失败首题尝试 30 次调用、265,366 个已知实际 token。全轮合计 **449 次请求、6,546,901 个已知实际 token**。其中一次被拒绝请求无用量回执，保留 71,033 token 预留，全轮保守账本为 6,617,934，低于总预算。未估计金额。

变化是首次提交前插入一次通用复查提醒，并要求重新提交；没有自动运行测试或实际读取 diff 的新检查器。源 YAML 仍有历史默认 step_limit=250，但真实 worker 继续覆盖为 50 次调用、100 万 token，未提升执行预算。

最终证据：[逐题报告](../../experiments/runs/dgm-hard10-v1-recovery2/summary.md)、[验证汇总](../../experiments/runs/dgm-hard10-v1-recovery2/validated-summary.json)、[候选 diff](../../experiments/runs/dgm-hard10-v1-recovery2/candidate.diff)、[源码及镜像核验](../../experiments/runs/dgm-hard10-v1-recovery2/verification.json)。全部 50 个固定 Mini 镜像仍在本地；1,059 个历史冻结文件、旧四框架代码与清单、本轮 DGM 运行代码均未改变。
