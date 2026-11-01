# Agent Harness 自改进研究

研究模型能否分析执行轨迹、改进 Agent Harness，并让相同执行模型在后续任务上获益。当前改进者与执行器均固定为 **DeepSeek Flash**，Agent 为 **mini-SWE-agent**；先诊断机制与受控验证，再决定是否训练。

## 项目目录

```text
ACL/
├── frameworks/          # RSI / 自改进框架官方源码
├── agents/              # 独立 Agent 官方源码
├── benchmarks/
│   ├── sources/         # Benchmark 官方源码
│   └── datasets/        # 固定版本数据
├── experiments/runs/    # 实验工作区、候选、轨迹、评分与调用账本
├── configs/             # 实验配置、目录注册和镜像策略
├── scripts/             # 准备、运行、分析及维护入口
├── tests/               # 本项目集成层测试
├── docs/                # 研究方案、协议、结果说明和运行文档
├── references/papers/   # 论文与阅读材料
├── reports/exports/     # 导出的报告、Word 文档等
└── acl_*/               # 已被历史实验冻结的 Python 集成包
```

`repos/`、`work/`、`outputs/` 和 `RSI必看/` 保留为兼容路径，新源码与资料使用正式目录。详细职责和维护约定见 [项目结构](docs/project_structure.md)；目录映射由 [project-layout.json](configs/project-layout.json) 管理。

## 从哪里开始

| 目的 | 入口 |
|---|---|
| 找 RSI 框架及接入状态 | [frameworks/](frameworks/README.md) |
| 找 Agent 和 Harness 的位置 | [agents/](agents/README.md) |
| 看研究故事 | [研究方案](docs/research_story.md) |
| 看实验及原始证据 | [experiments/](experiments/README.md) |
| 找准备、运行和维护命令 | [scripts/](scripts/README.md) |
| 查其他文档 | [文档导航](docs/README.md) |
| 恢复源码与依赖 | [运行说明](docs/runtime.md) |

## 已完成的 SWE-bench Mini50 试验

| 方案 | 通过数 | 通过率 |
|---|---:|---:|
| 原始 mini-SWE-agent | 31/50 | 62% |
| 一轮 RRSI 提示候选 | 29/50 | 58% |
| 一轮 GEPA 提示候选 | 25/50 | 50% |

每种框架仅评测一个新候选，使用相同 50 道开发题和每题执行预算；两个候选均退步，当前保留原始 Harness。结果不是框架排名，也没有证明模型获得了可迁移的自我改进能力。下一步是诊断退步和受控机制验证，尚未开始多模型比较或训练。

详细记录：[原始基线](docs/mini50_baseline.md)、[RRSI](docs/mini50_round1.md)、[GEPA](docs/gepa_swe_mini50.md)。Terminal-Bench 另有 12 题基线和未完成候选，见 [实验索引](experiments/README.md)。

## 常用命令

在项目根目录执行，复用现有 `.venv`：

```bash
# 核查本地 50 个任务镜像；不调用模型
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/cache_swe_mini_images.py status

# 读取已完成的 GEPA 结果；不重新执行任务
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/run_swe_local.py gepa summary

# 检查目录、兼容路径与迁移前后的冻结证据
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/maintenance/reorganize_workspace.py verify
```

SWE-bench Mini50 镜像已全部缓存在本地，**任务或批次结束后保留镜像，只清理容器**。后续 SWE 实验统一使用 `scripts/run_swe_local.py`，详见 [镜像缓存与运行入口](docs/swe_mini_image_cache.md)。

上游源码、下载数据、大型结果、导出文档和密钥不提交 Git；版本与数据来源按固定清单恢复。`.env` 留在根目录，密钥不写入配置、日志或文档。
