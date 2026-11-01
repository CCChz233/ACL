# 脚本入口

更新：2026-10-20。从项目根目录运行，既有脚本位置保留，按下面的职责表选入口。源码、试验快照和已启动过的运行版本有路径与哈希依赖，本次不批量移动脚本。上游位置由 `project_paths.py` 与基础/扩展目录清单解析。

## 查目录、看状态、复核现有结果

| 入口 | 行为 |
|---|---|
| [maintenance/audit_workspace.py](maintenance/audit_workspace.py) | 盘点目录、占用和保护文件哈希；默认只打印，`--output` 显式保存新审计；零模型/Docker |
| `python -m acl_multiround_v3.status` | 读取原高预算状态，不启动模型；最终合并结果从 [实验索引](../experiments/README.md) 看 |
| [framework_pilot_status.py](framework_pilot_status.py) | 读取最小试跑的状态/官方评分/用量 |
| [analyze_full10_results.py](analyze_full10_results.py) | 从既有逐题评分、父版本和用量重建十题分析；写分析附件，不重跑任务 |
| [audit_within_round_checkpoints.py](audit_within_round_checkpoints.py) | 还原历史编辑、执行离线提交检查及固定动作回放；写审计产物，零模型/Docker |
| [summarize_unified_completion.py](summarize_unified_completion.py) | 合并旧统一试跑及恢复记录；与高预算两轮结果分开 |
| `summarize_mini50_round.py`、`summarize_terminal_pilot.py`、`summarize_dgm_hard10.py` | 各自历史协议的保存结果汇总 |
| `terminal_pilot_status.py`、`terminal_round_status.py` | 读取 Terminal 历史任务状态 |

## 准备与执行入口

| 职责 | 入口 | 用途 |
|---|---|---|
| Agent / RRSI 准备 | `prepare_agent_sources.py` | 恢复并核验固定源码 |
| 框架准备 | `prepare_rsi_frameworks.py` | 核验；`--clone` 恢复缺失源码 |
| 四套框架准备 | `prepare_framework_integrations.py` | HarnessFix / Meta-Harness / GEPA / RRSI 来源锁核验，`--clone` 仅恢复缺失源码 |
| 五套框架准备 | `prepare_research_frameworks.py` | 追加 DGM，不改旧锁；`--clone` 仅恢复缺失源码 |
| RSIHub 准备 | `prepare_rsihub.py` | 钉住 RSIHub 源码；`--clone` 仅恢复缺失 checkout；不装入 `.venv` |
| Benchmark 准备 | `prepare_benchmarks.py`、`verify_benchmarks.py` | 准备固定资产和检查任务清单 |
| 镜像缓存 | `cache_swe_mini_images.py` | `fill` 补齐，`status` 本地核验 |
| SWE 统一运行 | `run_swe_local.py` | baseline / RRSI / GEPA，核验并保留本地镜像 |
| 离线框架检查 | `smoke_rsi_frameworks.py` | 假模型和原生接口检查 |
| 旧物理迁移工具 | `maintenance/reorganize_workspace.py` | 2026-10-19 的迁移/核验，核验也会写旧审计；日常盘点用新的 audit_workspace.py |
| 恢复补丁官方评分 | `grade_within_round_recovered_patches.py` | 会使用 Docker 官方 grader；不是模型能力的小测试，不因看状态而运行 |

## 历史恢复与准备工具

这些脚本对应独立的故障和预算，保留用于复现，不作为默认日常入口：

- DGM：`recover_dgm_hard10.py`、`recover_dgm_hard10_v2.py`、`build_dgm_hard10_sources.py`、`build_hard10_audit_notebook.py`。
- 统一试跑：`continue_unified_pilot.py`、`recover_unified_dgm_empty.py`。
- Terminal：`evaluate_terminal_round1.py`、`recover_terminal_round1.py`、`resume_terminal_round1_downloads.py`、`terminal_image_loader.py`、`terminal_image_loader_tls12.py`。

启动真实运行或恢复前，按 [实验索引](../experiments/README.md) 确认协议与预算，保留失败成本和既有结果。脚本存在不代表该批次仍在运行。

一般前缀为 `VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python`；Terminal 历史环境使用 `.venv-terminal`。`uv --offline` 只约束依赖管理，不自动禁止 Docker 或模型网络请求。
