# Terminal 12 题：一轮 RRSI 改进与复测

更新：2026-10-18。当前状态：候选已生成并锁定；镜像与评分依赖连续下载失败，且无可用代理，已停止本轮付费执行。只有 2 题有效评分，1 题评分无效，9 题未执行；**没有改进后的完整准确率，不能判断是否改善**。

原生汇总曾把第 3 题记为候选退步，但该题测试并未启动。这一汇总错误已修正；原始 trial、reward 和旧汇总均保留。以下以 [审计结果](terminal_round1_results.json) 为准。

原始基线为 7/12（58.3%）。本轮复用原始 12 题证据，不重新计作新基线；任务、DeepSeek Flash（thinking disabled）、mini-SWE-agent 2.4.6 DefaultAgent、工具接口、镜像内容、计时、评分与预算保持一致。RRSI 只允许修改通用 system/instance 提示和 observation/format-error 模板，编辑文件为 `terminal.yaml`。执行循环、环境和预算不在编辑范围。

本轮为 Google Research RRSI 固定版本上的小规模受限适配：T=1、m=1、k=1、一个通用机制编辑，delta=0，准确率优先；同分保留原始版本。只评测这一个语义候选。任务已用于诊断与提案，本轮结果是开发集上的前后比较，不能作为未见任务泛化或论文效果复现。

搜索最多 80 次调用、100 万 token；候选每题最多 50 次调用、100 万累计 token、单次输出 4096 token、命令超时 60 秒，原 task wall limit 与基线一致（最多 1200 秒）。全批最多 600 次目标调用、1200 万目标 token，不自动重试付费任务。

## 候选与搜索记录

初始语义候选由 DeepSeek/RRSI 生成，增加分阶段工作、尽早写出最佳可用产出、限制无效重复、保留中间结果到磁盘、提交前检查单位/范围及任务产出等提示。没有新增执行工具、任务专用解法或预算。最终候选 commit 为 `94ba950`。

第一阶段搜索用了 37 次调用、172,832 token。8 份 digester 记录中 5 份成功，3 份因限定回合数未返回，全部保留，不能当作有效诊断。Analyst 汇总后，Proposer 产出了候选，Critic 接受；原候选因 YAML 单引号未转义而未通过 smoke，未调用目标模型。

随后由 RRSI/DeepSeek 在同一累计搜索预算内修复引号，代码检查要求除空白与单引号以外的文本完全不变。原策略和语义编辑记录保留；没有手工添加优化建议或另选策略。累计搜索 **41 次调用、211,900 token**（analyst 2、digester 30、proposer 7、critic 2），新 Critic 与 smoke 通过。原失败 round、修复提案、前后历史和全部费用均归档。

诊断采用明确披露的预算适配：一次 Analyst 派发、最多 8 份 trace、Digester 最多 4 回合且第 3 回合要求返回，串行 digest；Proposer 每次最多 28 回合。该限制用于防止诊断耗尽整轮预算，不能称为论文完整搜索配置。

## 评测与镜像传输恢复

首次评测在镜像拉取阶段失败：Docker 配置的镜像源无法解析，官方 CDN 直连也遇到 EOF。此时没有任何目标 API 调用。采用公开镜像中转供给相同镜像，每题开始前必须验证 Docker image ID 与原始基线记录完全相同，才能运行模型；没有修改 Docker 全局设置或任务容器内容。下载路径变化不进入模型工作预算。

该恢复直接对锁定的 `94ba950` 使用原生 RRSI reevaluate/readjudicate，不新增搜索或选择新策略。脚本与规则保存在 `evaluation-recovery.json`，只清理本轮新增 canonical/mirror 标签，保留原有镜像。

后续也尝试了官方 registry、公开镜像中转、宿主机 curl HTTP/1.1 下载与校验后 OCI 导入。第 3 题的镜像由宿主机下载成功，校验 ID 与原始版本一致；第 4 题仍因 CDN 的 TLS/EOF/超时失败，尚无目标调用。没有关闭 TLS 校验、修改 Docker 全局源或更换镜像内容。所有传输尝试及脚本哈希保存在 `download-attempts.jsonl`、`download-retry-protocol.json` 与 `image-transfer-logs/`。

## 本轮实际结果与成本

| 任务 | 原始 | 候选有效结果 | 说明 |
|---|---:|---:|---|
| make-mips-interpreter | 未通过 | 未通过 | 官方 3 项测试实际运行；目标累计 token 预算停止 |
| headless-terminal | 通过 | 通过 | 官方 7 项测试全部通过 |
| merge-diff-arc-agi-task | 通过 | 无效评分 | uv 安装脚本下载不完整，`uvx` 不存在，pytest 未运行，无 CTRF |
| 其余 9 题 | 5 通过、4 未通过 | 未执行 | 第 4 题镜像传输失败后停止批次 |

两道有效配对结果与原始版本相同，不足以说明总体无效或有效。第 3 题原始 `reward=0` 留存作审计，候选有效分数记为 `null`，不计作退步；不能把当前结果报成 1/3 或 1/12。原生 RRSI 的决定为 `eval_invalid`，保留 H₀，是评测未完成，不能表述为分数较差而拒绝候选。

| 成本范围 | 调用次数 | 输入 token | 输出 token | 总 token |
|---|---:|---:|---:|---:|
| 全部搜索，含失败诊断与语法修复 | 41 | 198,608 | 13,292 | 211,900 |
| 候选执行，含第 3 题无效评分对应执行 | 89 | 1,208,533 | 27,182 | 1,235,715 |
| 本轮合计 | 130 | 1,407,141 | 40,474 | 1,447,615 |

合计输入缓存命中 1,261,056 token、未命中 146,085 token，API 累计延迟约 241.09 秒；这是 API 请求耗时之和，不是实验墙钟时间。本表不含旧基线的 381 次调用、4,967,447 token。未按未知价格推算金额。

全部 130 组请求和原始响应、唯一 provider response ID、用量与延迟均已核对；41 组搜索加 89 组执行，provider 用量与 ledger 一致。候选 YAML 已单独导出为 `work/terminal-round1/candidate-harness.yaml`，diff 保存在 `runs/terminal/r0/A/diff.patch`。审计哈希清单在 `records-audit.json`，原始基线与冻结适配器均未变化。

资源核查：原有 82 个镜像 ID 全部保留，本轮新增镜像 ID 与任务容器均为 0，没有运行中的实验进程。少量已校验镜像下载缓存保留用于未来恢复，没有执行全局 Docker prune。

## 数据边界与查看

改进者只接收 binary reward、停止原因、用量和 Agent 自身公开任务交互的截断视图；不提供 verifier 原始输出、tests、solution 或参考答案。Raman 的原始评分日志含参考数值，仅留作本机审计。

`work/terminal-round1/` 保存配置/代码/基线证据哈希、搜索原始请求及响应、诊断与提案、候选 diff、语法恢复、镜像恢复、候选逐次请求/响应/轨迹和官方评分。原始 `work/terminal-pilot-v1/` 保持不变。

没有保存完整容器文件系统快照。第 3 题的容器已由原执行器清理，不能直接在原状态下重新评分；仅有轨迹不足以代替原状态。后续恢复应显式区分新执行或轨迹重建，不自动重跑该题或把重建结果混为原始评分。

```bash
.venv-terminal/bin/python scripts/terminal_round_status.py
.venv-terminal/bin/python scripts/terminal_round_status.py --write
```

第二条命令只重建审计汇总，不发起 API 调用。冻结版本的 `python -m acl_terminal_rsi.run summary` 仅检查数值 reward，无法发现此次评分初始化失败，会重新写出不准确的退步项；本轮查看使用上述审计命令。旧汇总归档为 `summary-before-grading-audit.json`。正式后续版本必须先修复评分有效性校验，并在 Agent 完成后保存容器状态以支持网络故障下的独立重评分。
