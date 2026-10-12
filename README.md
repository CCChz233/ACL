# RSI Code & Terminal

面向代码与终端 Agent 的持续自改进研究。目标是验证：Agent 累积的经验能否改善后续任务表现，以及负责使用这些经验的训练策略能否随反馈变得更有效。

**当前处于实验准备阶段。Benchmark 源码、任务资源与测试数据已下载并校验；Agent、经验模块、训练和运行验收尚未完成。** 本仓库没有已完成的模型训练或论文结果。

## 研究问题

Solver 解决代码/终端任务；Trainer 决定如何筛选、检索、蒸馏与使用经验。先比较固定模型上的经验效用，再加入参数更新和策略演化。

固定检索带来收益本身不能证明 RSI。后续需要冻结初始与演化后的 Trainer，重置为同一个 fresh Solver，在独立任务与相同预算下比较训练收益，并加入强固定策略和等预算策略搜索基线。

## 当前进度

| 项目 | 状态 |
|---|---|
| 研究定位与首轮实验方案 | 已记录，待实验检验 |
| 五套 benchmark 的完整源码/资源或测试数据 | 本地已验证；大文件通过脚本获取 |
| 任务清单、固定来源版本、仓库排除清单 | 已有 |
| 容器镜像、参考解与实际评分 | 待运行验收 |
| 固定 Solver Agent 与轨迹日志 | 待实现/接入 |
| 独立 train/dev/meta-val 划分 | 待建立 |
| 经验提炼、检索与选择策略 | 待实现 |
| SFT/RL、持续轮次与 fresh Solver 检验 | 待实现 |

## Benchmark

| 角色 | Benchmark | 任务数 |
|---|---|---:|
| 代码主测试 | SWE-bench Pro V2 | 642 |
| 终端主测试 | Terminal-Bench 4.0.0 | 66 |
| 代码参考测试 | SWE-bench Verified | 500 |
| 终端参考测试 | Terminal-Bench 2.1 | 89 |
| 开发检查 | SWE-bench Verified Mini | 50 |

Mini 是 Verified 的子集；若用于方法开发，最终未见 Verified 测试应排除其 50 个任务。不同 benchmark 条目不能直接当作相互独立的样本合并。测试轨迹、参考补丁及隐藏 verifier 不进入训练经验库。

固定提交、官方来源与数据哈希见 [sources.lock.json](benchmarks/sources.lock.json)。[统一任务清单](benchmarks/all_benchmark_tasks.csv)包含 1,347 个条目；不包含参考补丁或任务答案。

## 本地检查与复现

准备脚本使用 Python 3.12+ 标准库，不要求先安装训练依赖。

```sh
python3 scripts/verify_benchmarks.py
python3 scripts/prepare_benchmarks.py --only terminal-bench-4.0.0
python3 scripts/prepare_benchmarks.py
python3 scripts/verify_benchmarks.py --check-downloads
```

第一个命令仅检查版本锁和清单。下载命令从固定官方版本恢复数据至忽略目录；最后一个命令检查实际任务文件、数据哈希以及 Pro 官方校验清单。网络不可用时，可将相同版本数据放到清单指定的位置后验证；不能关闭 TLS 校验替代文件验证。

这些检查只验证文件准备，不验证 Docker 镜像可用性、评分正确性或模型能力。正式评测还需要支持任务镜像的容器后端、Harbor、Agent 和模型端点；Pro V2 要保留官方补丁捕获及干净环境重评分协议。

## 目录

```text
benchmarks/     固定来源版本、任务清单与数据关系
scripts/        可移植的下载与文件检查工具
docs/           研究方案、执行顺序和第三方来源说明
repos/          本地下载的上游源码（不提交）
benchmarks/datasets/  本地测试数据（不提交）
```

论文 PDF、模型权重、大型任务附件、服务器连接信息及环境密钥留在本地。上游源码按各自许可证使用，本仓库不重新发布这些材料。

下一步：[跑通固定无记忆基线，再建立独立训练/开发小集](docs/next_steps.md)。研究定位见 [研究方案](docs/research_plan.md)。
