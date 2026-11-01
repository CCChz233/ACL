# 项目结构与维护约定

更新：2026-10-20。上游框架、Agent、Benchmark 和实验已分开存放；本轮将 43 份文档及机器可读说明实际分到主题子目录，将 6 份早期报告移入归档。旧路径保留相对软链接，运行代码与原始实验证据继续保留原位。

## 当前目录一览

```text
ACL/
├── README.md             项目总入口
├── frameworks/           9 套上游自改进框架源码
├── agents/               独立 Agent，目前为 mini-swe-agent
├── benchmarks/
│   ├── sources/          3 套 Benchmark 源码
│   └── datasets/         固定任务数据
├── experiments/
│   ├── README.md         按协议查最新/历史结果
│   ├── CATALOG.md        42 个批次/用途目录及 7 个历史散落文件
│   └── runs/             候选、轨迹、评分、请求和用量账本
├── reports/
│   ├── README.md         最新结果、组会及专项审计入口
│   └── exports/          最新分析、组会和审计；archive/ 放早期交付物
├── docs/
│   ├── research/         当前故事、计划、对照设计
│   ├── frameworks/       上游来源、接入及复现说明
│   ├── experiments/      各阶段实验协议和结果说明
│   ├── operations/       运行、资源、镜像及元数据核查
│   └── archive/          已退出研究主线
├── configs/              各批次冻结配置、框架来源及镜像缓存清单
├── scripts/              执行/分析/恢复工具；按 scripts/README.md 分类
├── tests/                集成层检查
├── references/           论文、用户提供的研究材料
├── acl_*/                顶层 12 个运行/适配包，实际目录保持原位
├── .venv/                SWE Python 环境
├── .venv-terminal/       Terminal 历史独立环境
├── .cache/               依赖、数据等本地缓存
├── repos/                13 个上游目录的兼容链接
├── work -> experiments/runs
├── outputs -> reports/exports
└── RSI必看 -> references/papers
```

`acl_*/` 是上述十二个顶层包的缩写，不是一个实际的父文件夹。上游框架源码和我们写的运行/适配代码属于不同层，分别从 frameworks 和本页运行包表进入。

## 本次发现与整理

| 问题 | 处理 |
|---|---|
| 早期索引缺少最新十题两轮结果，甚至还写“未接入” | 最新结果统一从 experiments/README.md 和 reports/README.md 进入 |
| 42 个历史目录混排，完成/中断/恢复不易分辨 | 建立全量分类目录；按协议、用途和恢复关系导航，不靠 v1/v2 猜成绩 |
| docs 一级 48 个文件，scripts 一级 33 个文件（整理前） | 43 份文档/JSON 实际分入四类子目录；scripts 保留原位置，按职责表查找 |
| 六份早期导出文件与当前分析混排 | 移入 reports/exports/archive/2026-10-10--12，保留旧访问路径 |
| 12 个 acl 包顶层展开，包含 v2/v3/recovery | 补齐职责与协议对应关系；不搬动具有物理路径依赖和来源锁的代码 |
| work/outputs/repos 看起来像重复存放 | 实测为兼容链接，不是第二份数据；继续保留 |
| runs 内有旧源码包、准备脚本和连接元数据 | 纳入历史文件清单，保留路径；本轮未打开连接内容或执行旧脚本 |

前一阶段的导航整理见 [原记录](../reports/exports/project-layout-audit-2026-10-20/README.md)；本次实际搬迁的映射、原文备份和校验见 [迁移记录](../reports/exports/project-layout-migration-2026-10-20/README.md)。43 个旧文档入口是软链接，目录项仍可见，但不再各自存放独立正文；使用本页子目录进入正式文件。实验、源码及配置未搬迁。后续若进行 src 布局重构，应建立新运行时版本并单独验证。

## 正式目录

| 目录 | 职责 |
|---|---|
| `frameworks/` | 官方 RSI / 自改进研究源码，独立 checkout、锁版本；含 HarnessFix 与 2026-11-01 钉住的 RSIHub |
| `agents/` | 独立 Agent 官方源码；初始 Harness 固定，候选另存 |
| `benchmarks/sources/` | SWE-bench Pro、Terminal 2.1 与 Terminal 4 源码 |
| `benchmarks/datasets/` | 固定版本数据，不改参考答案或哈希 |
| `experiments/runs/` | 候选、轨迹、评分、用量账本及维护审计 |
| `configs/` | 冻结实验配置、镜像策略、目录注册 |
| `scripts/` | 准备、运行、分析及维护入口 |
| `tests/` | 本项目接口、评分边界、缓存和恢复测试 |
| `docs/` | 研究方案、协议和结果说明，按 [导航](README.md) 查找 |
| `references/papers/` | 论文及阅读材料 |
| `reports/exports/` | Word 等导出交付物 |

框架的内嵌示例 Agent 保留在原仓库，不拆散上游结构。独立 Agent 进入 `agents/`。

## 集成代码

| 包 | 职责 |
|---|---|
| `acl_rsi` | RRSI→mini→SWE 的模型、预算、执行、评分与恢复 |
| `acl_terminal` | mini 在 Terminal/Harbor 下的执行适配 |
| `acl_terminal_rsi` | Terminal 的 RRSI Domain 和候选评测 |
| `acl_gepa` | GEPA 公共反思记录和 Terminal 接入 |
| `acl_gepa_swe` | GEPA 的 SWE Mini50 接入 |
| `acl_frameworks` | HarnessFix / Meta-Harness 接入、公开上下文与记账边界；后续真实运行已冻结版本 |
| `acl_dgm` | DGM archive、父 mini 自修改和 SWE 回调；独立新增，不改四框架已验收运行代码 |
| `acl_rsihub` | RSIHub 源码核验；无 live 运行，不改已有运行包 |
| `acl_unified` | 五框架四题反馈/六题报告的统一试跑 |
| `acl_multiround` | 最初五轮纵向计划，已缩减；保存历史运行入口 |
| `acl_multiround_v2` | 已完成的低预算两轮，仅评测新候选 |
| `acl_multiround_v3` | 已完成的高预算两轮，要求真实修改 |
| `acl_multiround_recovery` | 高预算缺项补全与合并审计 |

这些包保留根目录实际位置。多个批次已锁定源码字节哈希，部分模块还按物理路径计算项目根目录；新版本不代表可以随意覆盖旧包。将来改为 `src/` 应作为新的运行时版本，与历史可复验环境并存。新来源登记 `configs/project-layout.extensions.json`，解析器合并它与冻结的基础清单。新增框架详情见 [接入验收](frameworks/framework_integration.md)。

后续 HarnessFix/Meta-Harness 真实试跑也锁定了 `acl_frameworks` 的字节与代码快照。新增 DGM 因而放在 `acl_dgm`，不修改该运行时；DGM 原目录已有映射，无须重写基础清单。来源和接口详见 [DGM 接入](frameworks/dgm_integration.md)。

## 兼容规则

- 上游来源正式与旧路径由冻结的 `configs/project-layout.json` 及扩展清单管理；本次文档和报告映射另见迁移记录的 moves.json，不修改历史来源清单。
- `repos/*` 是指向框架、Agent 和 Benchmark 正式目录的相对链接。
- `work` 指向 `experiments/runs`；`outputs` 指向 `reports/exports`；`RSI必看` 指向 `references/papers`。
- 每份源码和结果只有一个实际目录，不复制大型数据。旧绝对路径、Git worktree 和 editable 安装通过兼容路径继续访问。
- 来源清单中的旧 `local_path` 保持原字节；准备脚本通过 `scripts/project_paths.py` 使用正式目录并恢复旧链接。
- 新 clone 不再放入 `repos/`。`pyproject.toml` 和 `uv.lock` 已使用正式 editable 路径。

## 日常维护

只读盘点可运行（无需模型或 Docker）：

```bash
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/maintenance/audit_workspace.py
```

本脚本枚举目录、空间分配与源码/逐题证据哈希，不读取 `.env` 内容；不传 `--output` 时只打印摘要。要保存审计，给 `--output` 一个新的路径；不会覆盖既有审计。空间口径只包含本项目，Docker 的外部镜像存储不在其中。

框架见 [frameworks/README](../frameworks/README.md)，实验见 [experiments/README](../experiments/README.md)，命令见 [scripts/README](../scripts/README.md)。SWE 运行统一走 `scripts/run_swe_local.py`，50 个 Mini 镜像本地保留。

```bash
# 核验准备入口，不下载已有源码
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/prepare_agent_sources.py
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/prepare_rsi_frameworks.py

# 核验本次整理后的冻结证据；不覆盖历史审计
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/maintenance/audit_workspace.py --compare reports/exports/project-layout-migration-2026-10-20/before.json
```

2026-10-19 的物理迁移审计保存在 `experiments/runs/project-layout-migration/2026-10-19/`：当时核对 1,059 份冻结源码、配置与实验证据，移动 15 个目录并保留 15 个兼容链接。该历史记录不由本次整理覆盖；当前额外来源也通过扩展映射登记。

验收完成：SWE 原环境 23 项测试、Terminal 原环境 16 项测试均通过；`uv lock --check --offline` 通过，准备脚本核验 7 个固定源码，Benchmark 清单检查通过。实际经统一入口读取 GEPA 原结果，并核验全部 50 个本地镜像；新增模型调用为 0。新导航的 68 个本地链接均有效。两套运行环境分别验证，未安装或混合依赖。
