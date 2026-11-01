# DGM 接入：原生 archive 搜索与 mini 自修改

2026-10-19。已有官方 DGM 已完成离线接入；随后按用户要求启动了[困难十题真实试跑](../experiments/dgm_hard10.md)。下文的零调用与离线验收说明属于此前接入阶段，真实成绩以独立运行产物为准。

来源：[官方 DGM](https://github.com/jennyzzt/dgm)，提交 `a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2`，Apache-2.0。实际目录 `frameworks/dgm/`，旧 `repos/dgm` 仍为兼容链接。追加来源锁为 [dgm.json](../../configs/frameworks/dgm.json)，代码为 [acl_dgm](../../acl_dgm)。旧四框架清单和已验收运行代码均未改动。

## 保留的机制

实际执行未修改的 `DGM_outer.py` 的 `main`：父代使用默认 `score_child_prop`，兼顾得分与已有子代数；有效性筛选沿用 `is_compiled_self_improve`；archive 默认 `keep_all`，得分较低但有效的候选也会保留。父代、diff、每代子节点和 archive 按原生格式存储、恢复。

替换的是 `self_improve` 执行边界。诊断复用原生问题和输出字段、使用 DeepSeek Flash；代码修改由**选中父版本的 mini DefaultAgent** 驱动，因此父 controller 的代码变化能进入后续自修改，而非永远由固定外部编辑器修改。诊断与实现共用优化账本；任务执行和官方评分复用既有 SWE 边界。

## 适配差异

名称为 **DGM-adapted**，不宣称原论文完整配置或数值复现：

- 原版目标是自己的 `coding_agent.py` 和工具系统；本地使用初始 mini 2.4.6，只部署 `agent.py`、`swebench.yaml` 的变化，保留许可证。
- 原版诊断读参考 patch、隐藏测试和详细 grader 输出。本地移除隐藏测试提示段，只传公开题面、自身交互、自身 patch 和二值结果；后续各上下文组须共用权限。
- 当前使用原生 `shallow_eval`、`no_full_eval`，单 worker、单 trial、每代 1 次改进。分级扩展评分、Polyglot、并行及完整工具修改空间未验收。
- 两个优化角色固定 `deepseek-flash`、既有端点、thinking=false。默认模板的优化调用/token 预算为 0；真实执行须冻结正预算配置并显式启用 live。
- Bash 工具在无网络容器中执行，公开资料只读、候选可写，复用并保留本地任务镜像。父 controller 和任务 worker 的 Python 代码仍由现有本机运行时加载，不代表对任意 controller 代码的完整进程隔离。

## 准备与离线检查

从项目根目录使用已有 SWE 环境：

```sh
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/prepare_research_frameworks.py
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python -m acl_dgm.cli check
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python -m acl_dgm.cli prepare
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python -m acl_dgm.cli smoke
```

五框架准备脚本加 `--clone` 仅恢复缺失的固定 checkout，不重置已有源码；旧四框架锁与 DGM 追加锁共同构成当前清单。

`prepare` 从两道已有开发题的真实 H0 记录初始化 native archive，不执行新候选。`smoke` 用合成 proposer/evaluator 执行两代真实外循环，验证退步候选仍入库、谱系和恢复。所有 smoke 分数均为合成夹具，不是 Benchmark 成绩。

测试还覆盖无效候选不评分、基础设施错误不记 0、隐藏证据不进入诊断、模块命名空间恢复，以及确实执行所选父版本的 controller。

[零预算模板](../../configs/dgm-mini-pilot.template.json) 用于准备。付费 `run` 同时要求 `--live`、显式配置、正优化预算；已有配置或源码锁变化时拒绝无记录续跑。模型请求/响应、usage、诊断、实现轨迹、官方评分和 archive 独立保存。

## 当前状态

源码、执行边界和原生 archive 离线接入完成。**困难十题真实工程试跑已完成：历史 H0 2/10，经过两次模型接口恢复的候选 4/10，新增解决四题、回归两题。** 此结果不是未经干预的 DGM 复现或稳定收益证据，详情见 [十题协议与结果](../experiments/dgm_hard10.md)。其他四框架的真实试跑记录保持原状。离线证据位于 `experiments/runs/dgm-integration-2026-10-19/`，最终真实试跑位于 `experiments/runs/dgm-hard10-v1-recovery2/`。

最终验收：DGM 专门测试 11 项、已有 SWE/框架测试 38 项、Terminal 测试 16 项，共 65 项通过；1,059 个历史冻结文件、旧四框架运行代码和来源清单均未改变。五套固定源码及依赖锁检查通过，本轮新增模型调用、Benchmark 执行和镜像修改均为 0。见 [机器可读汇总](../../experiments/runs/dgm-integration-2026-10-19/verification.json) 与 [最终两代原生检查](../../experiments/runs/dgm-integration-2026-10-19/smoke-v4/smoke-results.json)。

多代真实验收还需处理原生边界：默认 `score_child_prop` 可用，但 CLI choices 存在字符串拼接问题，本适配不显式传该参数；父代已解决全部任务时，某些采样分支可能从空列表选题。原生实现保持不改，处理策略应在正式实验前冻结。
