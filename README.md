# ACL：Agent Harness 自改进研究工作区

这里集中存放 RSI 框架源码、Agent、Benchmark、实验与研究资料。更新：2026-10-20；研究文档、协议及运行说明已实际分目录，早期导出报告已归档。

已落地的研究定义见 [研究故事](docs/research/research_story.md) 和 [深化设计](docs/research/evidence_research_agenda.md)，优化器/执行器固定 DeepSeek Flash，Agent 为 mini-SWE-agent。新上下文方法尚未验证；后续头脑风暴不自动替换当前文档。

最新完整实验是五框架、共同十题、高预算两轮，共 100 份候选逐题评分。查看 [最终结果](experiments/runs/full10-highbudget-completion-v1/report.md) 或 [含无 RSI 基线的分析](reports/exports/full10-two-rounds-analysis/analysis.md)。旧 Mini50、四题/六题试跑、低预算两轮及失败恢复均从 [实验索引](experiments/README.md) 查找，不混用成绩。

## 项目目录

```text
ACL/
├── frameworks/          # 9 套上游 RSI / 自改进框架源码
├── agents/              # 独立 Agent 官方源码，目前为 mini-swe-agent
├── benchmarks/
│   ├── sources/         # Benchmark 官方源码
│   └── datasets/        # 固定版本数据
├── experiments/         # README + 全量 CATALOG；runs/ 保留原始实验
├── configs/             # 实验配置、目录注册和镜像策略
├── scripts/             # 准备、运行、分析及维护入口
├── tests/               # 本项目集成层测试
├── docs/
│   ├── research/        # 当前故事、研究计划、Baseline 设计
│   ├── frameworks/      # 框架接入、来源筛选和复现边界
│   ├── experiments/     # 实验协议与结果说明
│   ├── operations/      # 运行、资源、镜像与元数据核查
│   └── archive/         # 已退出的研究故事
├── references/papers/   # 论文与阅读材料
├── reports/exports/     # 当前分析、组会报告；archive/ 存早期交付物
└── acl_*/               # 顶层 12 个历代运行/适配包，不是一个实际父目录
```

`repos/`、`work/`、`outputs/` 和 `RSI必看/` 保留为兼容路径，新源码与资料使用正式目录。详细职责和维护约定见 [项目结构](docs/project_structure.md)；目录映射由 [project-layout.json](configs/project-layout.json) 管理。

## 从哪里开始

| 目的 | 入口 |
|---|---|
| 看最新十题两轮结果 | [最终汇总](experiments/runs/full10-highbudget-completion-v1/report.md)、[逐题分析](reports/exports/full10-two-rounds-analysis/analysis.md) |
| 看整个文件夹的结构与维护规则 | [项目结构](docs/project_structure.md) |
| 找 RSI 框架及接入状态 | [frameworks/](frameworks/README.md) |
| 找 Agent 和 Harness 的位置 | [agents/](agents/README.md) |
| 看最新研究故事 | [证据高效上下文主线](docs/research/research_story.md) |
| 系统了解 RSI 研究发展与相关论文 | [研究脉络](references/papers/rsi-research-lineage-2026-10-21/RSI研究脉络.md)、[40 篇论文资料库](references/papers/rsi-research-lineage-2026-10-21/README.md) |
| 看实验阶段与最近待办 | [研究计划](docs/research/research_plan.md)、[执行清单](docs/research/next_steps.md) |
| 查两类 Baseline | [上下文对照 / RSI 框架验证](docs/research/harness_baselines.md) |
| 看实验及原始证据 | [experiments/](experiments/README.md) |
| 按用途找全部历史批次 | [全量分类目录](experiments/CATALOG.md) |
| 找组会、结果分析与专项审计 | [reports/](reports/README.md) |
| 找冻结配置 | [configs/](configs/README.md) |
| 找准备、运行和维护命令 | [scripts/](scripts/README.md) |
| 查其他文档 | [文档导航](docs/README.md) |
| 恢复源码与依赖 | [运行说明](docs/operations/runtime.md) |
| 把仓库和本地包放到新机器 | 下文「到一台新机器」 |

## 只读检查项目

在项目根目录执行，复用现有 `.venv`：

```bash
# 枚举目录、占用和源码/证据哈希；不调用模型或 Docker，不读取密钥内容
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/maintenance/audit_workspace.py
```

## 维护约定

- 上游框架进 frameworks，独立 Agent 进 agents，Benchmark 源码进 benchmarks/sources；研究资料与导出报告分开存放。
- 历代运行包、配置、失败轨迹、评分及来源锁保留原路径和字节；新协议使用新工作区，具体入口见 scripts/README.md。
- SWE Mini50 的全部任务镜像本地长期保留，运行后不删除镜像；项目目录占用不包含 Docker 的外部镜像存储。
- `.venv` 与 `.venv-terminal` 是两套不同运行环境，`.cache` 是缓存；本次不混装依赖或删除资源。

上游源码、下载数据、大型结果、导出报告和密钥不进 Git。2026-11-01 打好的本地包是 `acl-local-assets.tar`（约 7.8 GB），和仓库分开保存。`.env` 留在根目录，密钥不写入配置、日志或文档。

## 仓库和本地包

GitHub 上的 [ACL](https://github.com/CCChz233/ACL) 是项目代码：`acl_*` 运行包、`configs/`、`scripts/`、`tests/`、`docs/`、各目录 README、`pyproject.toml` 和 `uv.lock`。

`acl-local-assets.tar` 在仓库根目录解包后，补上 Git 里没有的这些路径：

| 包内路径 | 内容 |
|---|---|
| `experiments/runs/` | 实验账本、轨迹和评分 |
| `frameworks/` | 钉住的上游框架源码 |
| `benchmarks/sources/` | Benchmark 源码 |
| `references/papers/` | 论文和阅读材料 |
| `reports/exports/` | 报告、审计和演示文稿 |
| `agents/mini-swe-agent/` | 钉住的 mini-SWE-agent 源码 |
| `.env` | DeepSeek 端点、模型和密钥 |

`work/`、`outputs/`、`RSI必看/` 是指向 `experiments/runs`、`reports/exports`、`references/papers` 的链接，包里没有再放一份。`.venv` 和 `.venv-terminal` 在新机器上重建。SWE Mini50 的 Docker 镜像不在仓库里，也不在这个包里；要在新机器上直接评测，需另行导出本机 Docker 镜像。

## 到一台新机器

在服务器上克隆代码，把 `acl-local-assets.tar` 拷到机器上，然后在仓库根目录解包：

```sh
git clone git@github.com:CCChz233/ACL.git
cd ACL
tar -xf /路径/acl-local-assets.tar
```

解包后根目录应能看到 `.env`。没有这个文件时，按 [.env.example](.env.example) 新建，填写已授权的 `DEEPSEEK_API_KEY`。接着安装依赖并做不调用模型的检查：

```sh
python3.12 scripts/prepare_agent_sources.py
uv --native-tls sync --locked --extra dev --python python3.12
.venv/bin/python -m acl_rsi --config configs/full-cycle-50.json doctor
```

`prepare_agent_sources.py` 核对已经解包的固定源码，缺失时才克隆。`doctor` 只报告版本、端点和密钥是否存在。更早的运行入口和历史协议见 [运行说明](docs/operations/runtime.md)。
