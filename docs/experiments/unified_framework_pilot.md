# 五框架统一困难十题试跑

2026-10-19。用户批准后启动的新比较，独立于所有旧实验。当前源码在 `acl_unified/`，运行目录在 `experiments/runs/unified-hard10-v1/`。当前状态以该目录 `batch-status.json`、分阶段 `status.json` 及逐题有效评分为准；后台启动不表示已经完成。

最终状态：五框架本轮均已尝试并结束。[完整结果](../../experiments/runs/unified-hard10-v1-completion/report.md)和[审计数据](../../experiments/runs/unified-hard10-v1-completion/validated-summary.json)分别记录原始失败与明确授权的工程恢复。新 H0 **3/10**，GEPA **5/10**（开发 2/4、评测 3/6），新增两题且无回归。其余四框架未在原搜索预算内形成有效可评分候选。DGM 修复空列表后搜索 39 次、864,518 token，触发 token 预留保护，部分候选模板语法无效；离线门禁复核与原始包装异常均保留。总计 **890 次请求、13,256,099 已知实际 token**，一次未知 usage，含保守预留 13,305,010 token，21 次任务 worker 执行。GEPA 中断续跑和 DGM 选择分支适配均需披露，不当作未改配置的正式复现或稳定排名。

启动验收：新共同 H0 十题已全部有效评分，**3/10**，其中开发四题 **1/4**、评测六题 **2/6**。46 项相关离线/回归检查通过；优化阶段冻结 77 个源文件/配置摘要及运行副本，1,059 个历史文件保持不变。旧 H0 的 2/10 不再作为本轮比较基线。

## 冻结设置

优化器及任务模型固定 DeepSeek Flash、thinking=false；mini 2.4.6、原始 H0、任务镜像、官方 grader 和模型执行限制固定。每框架一轮、最多一个候选。保留框架各自的原生诊断、搜索、审查与接纳过程；不是原论文完整配置或多轮收益比较。

共同修改空间：`agent.py` 与 YAML 的 `agent.system_template`、`agent.instance_template`、`model.observation_template`、`model.format_error_template` 四个字符串。其余 YAML 字段和值、新增键、许可证、依赖与其他文件不能修改。Python 可新增通用行为及默认配置；禁止任务/仓库专用规则、答案、私有测试、宿主文件或外部 provider/预算访问。

仅注释和排版变化不计有效候选。所有候选先通过相同的结构/语法/YAML 范围检查、构造与单/多工具、首次提交及重复动作的结果配对检查；检查不调用模型。当前 Python worker 仍由本机运行时加载候选代码，静态规则不代表任意代码的完整进程隔离。

## 十题与信息边界

沿用事先冻结的困难十题，仅使用原始 H0 的历史结果与 ID 划分，不按 DGM/RRSI/GEPA 新候选结果打分选取。枚举四题子集，要求两个仓库各二题、一个历史成功与三个历史失败；失败须各覆盖调用上限、token 上限、已提交失败。用固定 salt/seed 17 的 SHA256 排序确定唯一划分。

| 部分 | 任务 |
|---|---|
| 四题开发 | Django-12209、Django-12406、Sphinx-10466、Sphinx-10673 |
| HarnessFix 内部 train | Django-12209、Sphinx-10673 |
| HarnessFix 内部 selection | Django-12406、Sphinx-10466 |
| 六题冻结后评测 | Django-11885、Django-12273、Django-12039、Sphinx-11510、Sphinx-10435、Sphinx-8551 |

这十题全部是已使用的开发数据，六题仅在**本轮优化器反馈通道**中封存，不是未见测试集。共同 H0 在十题上重新执行一次；各框架共享同一份新的四题 H0 公开历史，六题轨迹/评分不进入优化器工作区。反馈只包含公开题面、自己的交互和补丁、二值评分，不含参考 patch 或隐藏测试/评分日志。

框架先使用四题完成候选及原生开发决定，保存 `nomination.json` 的代码摘要和保留决定，再评测六题。有效但未被原生规则接纳的候选也可得到独立六题读数；保留 H0 的六题读数复用本轮共同基线。六题不能反馈给优化器再改候选。

## 预算与执行

- 每框架优化总额：80 次调用、100 万累计 token，单次输出 4096；诊断、规划、反思、实现及原生修复共用账本。搜索经过时间上限 3600 秒，框架进程总保护上限 30000 秒。
- 每题：50 次 API 调用、100 万累计 token、1200 秒任务墙钟、60 秒工具命令、900 秒评分。来源 YAML 的原始默认预算由外部 worker 覆盖。
- 全部最多 60 次任务执行：共同 H0 十题，加五个框架各最多十题；最多 3400 次 API 请求、6500 万累计 token。无效候选提前停止，实际任务数可以少于 60。
- 保守请求预留可能在实际 token 达到上限前停止；无 usage 的请求保持未知并保留额度，不当作免费。记录输入、输出、缓存、时间与请求 ID，不估计金额。
- Docker 可用内存约 8 GB，任务串行。全部 50 个固定镜像先核验、仅用本地缓存、永久保留；任务容器可清理。低于 4 GiB 空间保护线时停止。
- 无人工定向恢复，不追加优化预算、不自动重跑付费 worker。官方 grader 的独立基础设施错误允许沿用公共评分边界，只重评已保存补丁一次，不重新调用任务模型。

先执行共同 H0，再按 HarnessFix、Meta-Harness、GEPA、RRSI、DGM 串行。每框架独立进程，原生模块和预算注入互不污染。网络/Docker/评分基础设施失败与候选无效分开；不存在的候选分数不填 0，原生回退 H0 的成绩引用共同基线。

## 五套适配差异

| 框架 | 本轮边界 |
|---|---|
| HarnessFix | 复用已验证的原生 HTIR 管线及模型桥接；版本化内存副本把两题边界扩为 2 train＋2 selection，绑定新 H0。框架工作副本不复制上游 data 目录。 |
| Meta-Harness | 原生进化/frontier；同一文件提案器读取四题并提交一个候选；统一 gate 替换原先较弱的语法检查。没有人工预算结束 Finish 补写。 |
| GEPA | 原生 `gepa.optimize` 与反思选择；参数为相对 H0 的精确替换 edit spec，覆盖 Python 与四个提示，而非旧版 prompt-only。保留既有 9k 字符轨迹预览，并允许同一记账反思模型用 Read/Glob/Grep 展开完整公开文件。 |
| RRSI | 原生 Analyze/Propose/Critic/Evaluate/Select 一轮；Domain 绑定新 H0 与统一执行器。Digester 的只读 Bash 只挂载四题渲染轨迹，在无网络容器运行。 |
| DGM | 原生 archive/main、父 mini 自修改与 keep_all；只用四题历史。最后提名 archive 中开发正确率最高者，同分保留 H0；不把 archive 入库误写为进步。 |

这些工具和输入表示差异仍属于 adapted 系统的组成部分；统一预算不意味着五种算法或工具完全相同。当前是小样本工程筛选，论文上下文主实验仍应在同一框架内部比较。

## 状态与结果

### 2026-10-19 明确授权的基础设施续跑

原始队列在 GEPA 第三道评测题 Django-12039 的 `APIConnectionError` 后按协议停止。此前候选四题开发从 H0 1/4 到 2/4；六题评测中前两题均未通过。HarnessFix 原生汇总返回空计划；Meta-Harness 触发 token 预留保护；两者均未得到可评分候选。这些不是 0/6，且不追加搜索来覆盖原始失败。

用户随后明确要求“继续吧，把这个全做完。”，新增独立控制器 `scripts/continue_unified_pilot.py`，运行目录 `experiments/runs/unified-hard10-v1-continuation1/`，tmux 会话 `acl-unified-continuation`。原始 `result.json`、GEPA 提名及候选均校验摘要并保留。RRSI/DGM 使用原冻结运行器首次启动；互相独立的阶段不会因前一框架的失败而跳过。

GEPA 只补四道未完成的报告题。连接失败题仅允许一次明确授权的任务重启，采用原预算余额：40 次调用、887,263 token、910 秒；原失败 10 次调用、112,737 个实际/预留 token 与约 290 秒仍计入总成本。重启使用新的任务上下文，不能称作原封不动的正式试验；候选代码不修改、四题开发决定不重选、报告反馈不进入优化器。其余三道题沿用原 50 次/100 万/1200 秒限制。总调用、token、任务执行次数继续受原全局上限约束。

续跑保存单独的 `authorization.json`、控制器副本、各题配置/轨迹/评分、`status.json`、`summary.json` 和 `report.md`；新报告合并原结果与续跑证据，明确标记工程续跑。若再次出现基础设施问题，记录未完成项，不自动无限重试。原目录的 `batch-status.json` 仍保留原始 stopped 状态，查看当前进度请读续跑目录。

```sh
VIRTUAL_ENV="$PWD/.venv" UV_CACHE_DIR="$PWD/.cache/uv" PYTHONPATH="$PWD" uv run --active --no-project --no-env-file --offline python scripts/continue_unified_pilot.py --report
```

上述命令只校验和汇总，不调用模型。当前状态以续跑 `status.json` 和逐题有效评分为准，不能将后台启动写成全部完成。

续跑后 GEPA 已完整评分：开发 2/4、评测 3/6、十题 5/10，对应 H0 1/4、2/6、3/10；新增 Sphinx-10673 与 Sphinx-10435，无回归。RRSI 在 analyst/digester 阶段用完 80 次调用（377,640 实际 token），未产生候选。DGM 在模型调用前触发上游空列表分支：H0 三个失败均为空补丁，`total_unresolved_ids=[]`，原生 `unresolved_ids == 0` 条件未挡住 `random.choice([])`。

为完成用户要求的 DGM 运行，另建 `scripts/recover_unified_dgm_empty.py` 与 `experiments/runs/unified-hard10-v1-dgm-empty-recovery1/`，tmux `acl-unified-dgm-empty`。只在独立进程的内存函数中将空 unresolved 列表兜底为 empty-patch 列表，均空则跳过；上游工作树和冻结适配源码保持不变。真实基线元数据上的离线选择检查通过，seed17 不变。原 DGM 搜索消耗为零，因此修复适配运行仍只允许原来的 80 次/100 万 token、一个候选。此为修改了选择边界的工程适配，不能宣称是未修改原生 DGM 的正式结果。

合并以上原始结果、GEPA 续跑及 DGM 修复适配的总报告在 `experiments/runs/unified-hard10-v1-completion/report.md`，逐题评分摘要和完整用量在同目录 `validated-summary.json`。`scripts/summarize_unified_completion.py` 只做证据校验及汇总，不调用模型；DGM 运行结束自动生成总报告。

后台会话：共同基线 `acl-unified-h0`；五框架队列 `acl-unified-hard10`。队列等待共同基线完成后自动继续。进程异常或基础设施停止时保存状态并停止；不隐式重试。

```sh
VIRTUAL_ENV="$PWD/.venv" UV_CACHE_DIR="$PWD/.cache/uv" uv run --active --no-project --no-env-file --offline python -m acl_unified.status
```

`baseline/result.json` 保存新共同基线；每框架的 `nomination.json`、`result.json`、`optimizer-api/` 和 `evaluations/candidate/trials/` 分别保存冻结提名、结果、搜索账本和逐题轨迹/patch/官方评分。主报告分别列出六题候选与保留版本通过数、开发四题、十题描述性总数、新增解决/回归、候选有效性及完整成本，不能把开发十题总数作为独立泛化成绩。

阶段锁：基线单独保存其执行源码摘要；优化阶段启动前冻结全部新适配源码与旧复用代码的 SHA256，后续变化拒绝无记录续跑。旧实验源码、配置、轨迹与所有官方 checkout 保持不变。
