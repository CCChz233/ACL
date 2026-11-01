# 本地 Benchmark 准备状态

更新日期：2026-10-12。本轮仅补齐本地文件，没有连接服务器、启动模型或执行评测。

## 源码与测试数据已补齐

| Benchmark | 数量 | 本地位置 | 固定版本与验证 |
|---|---:|---|---|
| SWE-bench Pro V2 | 642 | `sources/swe-bench-pro/v2/tasks/` | commit `66f92766bba642462d4bbe5479e83f91f9211862`；全部 6,436 项官方 SHA256 通过 |
| Terminal-Bench 4.0.0 | 66 | `sources/terminal-bench-4/tasks/` | v4.0.0、commit `452bf305c6daa62fc59061d22133a7cbc7c1572e`；全部 3,200 个官方 Git blob 验证通过，补齐原先缺失的 181 个大型资源 |
| Terminal-Bench 2.1 | 89 | `sources/terminal-bench-2.1/tasks/` | commit `7131e4375048a0e408a8fb404b5f499d726b695b`；全部 1,101 个官方 Git blob 验证通过 |
| SWE-bench Verified | 500 | `datasets/swe-bench-verified/` | 完整 test Parquet、JSON；官方 SHA256、实际行数、ID 唯一性通过 |
| SWE-bench Verified Mini | 50 | `datasets/swe-bench-verified-mini/` | 完整 test Parquet、JSON；官方 SHA256、实际行数、ID 唯一性通过 |

Terminal-Bench 4 原有 Git checkout 保留在原路径，稀疏检出已关闭，工作区无改动。Terminal-Bench 2.1 为固定官方提交的完整源码归档，不含 Git 历史。

现有本地下载归档保留在忽略目录 `../work/benchmark_downloads/`。可移植的恢复与校验入口是 `../scripts/prepare_benchmarks.py` 和 `../scripts/verify_benchmarks.py`，后续下载缓存位于忽略目录 `../.cache/benchmark_sources/`。

## 清单与数据边界

- `all_benchmark_tasks.csv`：统一任务清单，共 1,347 个 benchmark 条目；该数字不是相互独立的任务总数。
- 各 benchmark 的任务 CSV：任务标识与可用元数据，不包含参考补丁。
- `terminal-bench-4-validated.json`、`terminal-bench-2-1-validated.json`：来源、固定提交、源码数量及归档哈希。
- `datasets/*/source.json`：测试数据来源、数据文件版本、哈希及行数。
- `terminal_bench_4_deferred_files.csv`：保留原来的 181 文件历史清单，每项现在标记为已下载并校验。
- `verified-mini-overlap.json`、`verified_without_mini_ids.json`：Mini 的 50 个 ID 全属于 Verified；使用 Mini 调方法后，未见 Verified 测试剩余 450 个。
- `benchmark_relationships.json`：版本及子集关系记录；Terminal 版本间没有同名任务，不足以证明内容或来源独立，仍需要任务来源/内容审计。
- `download_status.json`：机器可读状态，分别记录资源完整性与运行验收。
- `test_repository_exclusions.json`：下一轮代码训练候选需要排除的测试仓库身份；Pro 仓库名由固定官方任务 ID 提取，仍需核对规范 URL，并进一步检查任务近重复及仓库血缘。

这些都是测试/评测资产，尚未建立独立训练和 meta-validation 数据。参考解、测试补丁及 verifier 内容不能写入 Solver 上下文或经验库。

## 仍未完成的运行准备

本地为 macOS ARM64，Docker 客户端存在，但服务在最近只读检查中无法连接；Harbor 及本项目专用环境尚未配置。任务容器镜像未拉取，任务 Dockerfile 未构建，参考解及评分流程未在本地运行。因此本轮完成的是完整源码/资源/测试数据准备，不是运行验收。

Pro V2 官方镜像为 Linux/amd64。正式运行前应确定支持这些环境的执行后端，并保留官方网络限制、补丁捕获与干净容器重评分协议。

下一步建议见 [下一步方案](../docs/research/next_steps.md)。
