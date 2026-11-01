# 权威来源与高 Star RSI 框架：首批筛选和本地试运行

更新：2026-10-18。结论：优先接入 **GEPA**，将 **Meta-Harness** 作为第二个直接相关的方法；保留现有 RRSI。另克隆 DGM、ADAS 与 Google Research 新发布的 Harness² 作机制和工程对照。机构来源、社区关注和当前约束的适配性分别判断，不把 Star 当作效果排名。

本轮调查 10 个仓库，新克隆 5 个官方研究实现。模型仍固定 DeepSeek Flash，目标初始 Harness 保留 mini-SWE-agent。本轮运行的是离线工程检查，**没有新增模型调用、训练或 SWE/Terminal Benchmark 评分**。

## 1. 筛选依据

首批入选标准为：可验证的论文/研究团队来源，官方实现，GitHub 至少 1,000 Star，且包含与固定模型下的 Harness、Agent 代码或 Agent 设计优化相关的无需权重训练的方法。这是本次调查范围内的选择，不是全网穷尽排名；较新的高质量研究也可能尚未达到该门槛。

Star、Fork、许可证和维护状态来自 GitHub REST API `/repos/{owner}/{repo}` 的 2026-10-18 快照。主要快照为 UTC 08:06，Harness² 随后补查；精确时间及原始响应保存在 `work/rsi-framework-selection/`。机器可读来源、全部 10 项元数据和固定提交见 [版本锁](../rsi_frameworks.sources.lock.json)。网页显示的四舍五入数量可能滞后于 API。

“官方实现”包括论文作者确认的个人仓库；不表示相应大学或公司对软件作产品背书。

## 2. 入选清单

| 框架 / 官方仓库 | 经核对的研究来源 | Star | 方法与本项目关系 | 本地优先级 |
|---|---|---:|---|---|
| [GEPA](https://github.com/gepa-ai/gepa) | UC Berkeley、Stanford 等论文作者团队；作者维护组织 | 7,028 | 反思式文本/代码优化；当前提示模板编辑空间最容易对齐 | 第一接入 |
| [DGM](https://github.com/jennyzzt/dgm) | UBC、Vector Institute、Sakana AI 合作；作者官方个人仓库 | 2,425 | 自修改编码 Agent 与历史档案演化；接 mini 需改执行与评测接口 | 经典参考 |
| [Harness²](https://github.com/google-research/harness2) | Google Research 机构仓库 | 2,208 | 任务内改进与跨任务经验更新；原协议含额外任务时探索 | 新近方法参考 |
| [Meta-Harness](https://github.com/stanford-iris-lab/meta-harness) | Stanford IRIS 机构仓库；论文含 Stanford、MIT、KRAFTON 作者 | 1,673 | 通过文件系统检索历代代码、分数和轨迹，搜索 Harness | 第二接入 |
| [ADAS](https://github.com/ShengranHu/ADAS) | UBC、Vector Institute；论文作者官方个人仓库 | 1,650 | ICLR 2025，Meta Agent Search 自动设计 Agent 程序 | 设计搜索参考 |
| [RRSI](https://github.com/google-research/rrsi) | Google Research 机构仓库 | 1,541 | 现有正则化 Harness 搜索对照，已有本地真实运行记录 | 保留原对照 |

GEPA 的作者与方法来源见 [论文](https://arxiv.org/abs/2507.19457)；其实现不仅支持 prompt，也支持代码和配置。我们优先它，是对当前编辑空间和工程成本的判断，尚无 DeepSeek 上优于 RRSI 的证据。

Meta-Harness 的 [论文](https://arxiv.org/html/2603.28052v1) 和仓库明确提供完整历史检索机制与 Terminal 示例。官方示例的提议者使用 Claude Code，Terminal 初始版本也不是 mini；本项目必须换为 DeepSeek 接口并对齐目标 Harness，命名为 Meta-Harness-adapted。

DGM 的团队与官方仓库由 [Sakana AI 项目说明](https://sakana.ai/dgm/) 确认。ADAS 的团队、论文与官方代码由 [作者项目页](https://www.shengranhu.com/ADAS/) 确认。它们是研究出处可靠的作者发布，不能仅因仓库位于个人账号就排除。

Harness² 为 Google 官方研究仓库的新近发布，提供无需模型密钥的本地示例。其任务级 Propose–Probe–Compose 和持续经验更新与我们“离线搜索后部署一个固定 Harness”的成本口径不同，不能把额外任务时计算带来的成绩直接混入同预算比较。

## 3. 调查后未列为首批主对照的项目

| 项目 | Star | 当前决定 |
|---|---:|---|
| [DSPy](https://github.com/stanfordnlp/dspy) | 38,676 | Stanford NLP 的通用语言模型程序优化框架，集成 GEPA；高关注度属整个框架，不是独立 Harness RSI 实验的采用量。首轮直接接 GEPA，减少额外系统差异 |
| [Agent Lightning](https://github.com/microsoft/agent-lightning) | 18,739 | 微软官方 Agent 训练框架；与当前固定权重、固定远程 DeepSeek 的主实验不直接对齐，暂不接训练路线 |
| [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve) | 7,584 | 相关且高关注，但属于社区实现，不能当作 Google AlphaEvolve 官方开源；本轮机构/学校优先条件下暂缓 |
| [SICA](https://github.com/MaximeRobeyns/self_improving_coding_agent) | 409 | 直接相关、作者官方实现，但未达到本轮 Star 门槛；保留研究参考，未克隆 |

通用 Agent 编排、个人助手和纯训练系统不因 Star 高而自动成为 Harness 自改进基线。当前只对以上公开仓库作核对，不宣称它们之外没有更合适的方法。

## 4. 本地源码和固定版本

| 名称 | 本地目录 | 固定提交前缀 | 许可证 |
|---|---|---|---|
| GEPA | `repos/gepa` | `f1cfdee2856e` | MIT |
| Meta-Harness | `repos/meta-harness` | `8123ccabe2b19` | MIT |
| DGM | `repos/dgm` | `a565fd2d1dca` | Apache-2.0 |
| ADAS | `repos/ADAS` | `2702bee8fefd` | Apache-2.0 |
| Harness² | `repos/harness2` | `1cfe254e8d25` | Apache-2.0 |

五个均从官方 GitHub HTTPS 浅克隆，没有初始化子模块。首次克隆受本机 HTTPS→SSH URL 改写影响而失败；随后仅对下载进程设置 `GIT_CONFIG_GLOBAL=/dev/null` 并使用 HTTP/1.1 成功，没有修改全局 Git 配置。首次失败与成功下载日志均留存。

五个 checkout 的固定提交、根文件哈希、干净 Git 状态与对象连接性检查均通过。本轮源码、独立依赖、下载缓存和示例产物合计约 0.30 GiB；未下载新的 Benchmark 镜像。

原始 RRSI、mini、旧实验配置与结果保持原版本；新源码置于忽略目录，Git 锁和检查脚本保存在项目中。使用以下命令检查来源，缺失时加 `--clone` 恢复：

```bash
.venv-terminal/bin/python scripts/prepare_rsi_frameworks.py
.venv-terminal/bin/python scripts/prepare_rsi_frameworks.py --clone
```

## 5. 试运行范围

试运行结果见 [机器可读记录](rsi_frameworks_smoke.json)。每项检查保存退出码、耗时、日志及哈希；失败的初始检查也在 `smoke-attempt*` 中归档。

最终共 7 组检查全部通过。GEPA/Meta 的测试数量、DGM/ADAS 的局部检查和 Harness² demo 分别报告，不把它们相加成统一的框架准确率。原始 Terminal 基线证据与冻结适配器哈希复核通过。

| 方法 | 实际检查 | 能证明什么 |
|---|---|---|
| GEPA | 官方 `test_optimize`、候选选择和接纳规则测试，32 项通过；优化测试使用 Mock LM | 原生导入、模拟优化和选择流程在本机可运行 |
| Meta-Harness | 官方历史/最终测试隔离契约测试，6 项通过；Terminal CLI `--help` 通过 | 部分搜索记录与数据边界逻辑可运行，Terminal 入口可导入 |
| DGM | 原生档案读取、候选有效性函数；DeepSeek 客户端构造检查 | 历史记录接口和模型路由的局部兼容性；不等于完整改进循环 |
| ADAS | 原生 7 个初始设计、提案/反思上下文生成、初始设计语法编译 | 提案材料能构造，未执行设计中的模型调用 |
| Harness² | 官方 deterministic demo，k=2、parallel 与 sequential 两种模式，2 个示例任务完成 | 真实 Python 执行、脚本化候选编辑、选择和经验库保存可运行 |

Harness² 示例的改进者是作者编写的确定性编辑器，执行了 28 次本地 Python 脚本、32 次脚本化编辑/选择接口调用。**这些不是 32 次大模型调用，也不是 DeepSeek 的自改进成功率。** 示例任务只用于工程验证，不属于本项目 Benchmark。

离线检查禁用了模型网络连接和自动 `.env` 读取，不读取已有 API 密钥；使用现有 Terminal Python 环境的包，并把缺失依赖安装到 `work/rsi-framework-selection/extra-dependencies/`，没有升级旧环境。增补包版本在 `configs/rsi-framework-smoke-requirements.txt` 保存。初次 Meta 导入尝试获取 LiteLLM 价格表，被离线保护阻止，随后通过官方本地价格表选项禁用该联网步骤。

复跑工程检查：

```bash
uv pip install --python .venv-terminal/bin/python \
  --target work/rsi-framework-selection/extra-dependencies \
  -r configs/rsi-framework-smoke-requirements.txt

VIRTUAL_ENV="$PWD/.venv-terminal" \
UV_CACHE_DIR="$PWD/work/rsi-framework-selection/uv-cache" \
uv run --active --no-project --no-env-file --offline \
  python scripts/smoke_rsi_frameworks.py
```

这不是完整依赖锁或跨机器复现承诺；记录的运行环境仍依赖原 Terminal 环境。不能将本地测试通过写成论文效果复现，或声称五套框架均已接好 mini 并完成真实搜索。

## 6. 下一步选择

**GEPA-adapted 接入现已完成**，见 [接入与验收记录](../experiments/gepa_terminal_integration.md)：候选使用相同的 mini 提示/模板，DeepSeek 反思复用外部预算与用量记录，执行使用原 PilotAgent；已补严格评分校验、缓存与恢复，16 项相关检查通过。真实模型搜索和候选 Benchmark 尚未启动。首题镜像现已下载成功，但其余题目及 grader 依赖网络仍未验收。

第二步接 **Meta-Harness-adapted**，保留按需检索完整历史这一关键机制；限制可见文件为规定的公开交互、允许反馈和候选代码，不能把包含参考数值的原始 verifier 日志直接暴露给提议者。若研究代码级优化，另外冻结较宽的合法编辑空间，并为所有比较方法重设相同起点，不与当前提示版本混比。

DGM/ADAS 暂作代码级设计搜索参考；Harness² 另作为任务时适应研究候选。先完成一个新方法的真实比较，再决定是否扩展，避免五个框架各跑一个候选却无法解释结果。

真实比较前仍需验收镜像及评分依赖下载；换搜索框架不会消除当前网络故障。现有 Terminal 12 题属于开发数据，后续独立验证需使用未参与方法选择的任务。本轮没有启动新的付费 Benchmark 搜索，也没有自动扩大旧实验预算。
