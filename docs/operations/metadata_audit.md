# 当前实验的记录与元数据清单

本清单核对已完成的全部 50 题基线、50 题 RSI 候选及累计搜索。基线副本、恢复时复制的搜索账本各只计一次；更早的单题工程尝试不包含在下表。原始轨迹和运行代码保持不变，未发起新 API 调用。

## Token 已记录到逐次调用

| 阶段 | 调用数 | 输入 token | 输出 token | 合计 token |
|---|---:|---:|---:|---:|
| 原始 Harness 基线 | 1,153 | 15,211,404 | 232,003 | 15,443,407 |
| RSI 搜索（含首次失败） | 168 | 1,038,124 | 29,729 | 1,067,853 |
| RSI 候选执行 | 1,317 | 18,752,015 | 253,371 | 19,005,386 |
| 合计 | 2,638 | 35,001,543 | 515,103 | 35,516,646 |

逐次账本含 `prompt_tokens`、`completion_tokens`、`total_tokens`、`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`。本范围所有调用均有这些字段和对应原始响应；已核对 total=input+output、input=cache_hit+cache_miss。缓存命中属于输入 token 的子集，不能额外再加一次。累计输入反复包含历史上下文，不等于唯一内容长度。

原始 API usage、预算预留 `reserved_tokens` 和预算结算 `charged_tokens` 分开保留。`charged_tokens` 是预算记账单位，不是货币费用；轨迹内部的零值 cost 也不代表免费。

## 已保存的内容及位置

| 类别 | 已有字段和证据 | 典型位置 |
|---|---|---|
| 实验配置 | 任务 ID 与顺序、模型/端点/thinking、搜索与执行预算、轮数/候选数/重复数、选择规则、恢复方式 | configs/mini50-round1-recovery.json |
| 数据与代码版本 | 任务 base commit；数据、配置、Harness、适配代码哈希；上游 commit；候选 commit/diff | repo/source_manifest.json；逐题 manifest.json；r0/A/diff.patch |
| 逐次模型调用 | 本地请求 UUID、角色、状态、请求预留时间、返回 model、输入/输出/cache token、预算预留与结算 | usage.json；search_usage.json |
| 原始模型响应 | 返回正文、工具调用、response ID、created、model、system_fingerprint、finish_reason、usage | usage-responses/；search_usage-responses/ |
| 执行轨迹 | system/user/assistant/tool 消息、命令、模型可见观察、工具原始输出、返回码、时间戳、异常和退出状态 | trajectory.json；worker.json；worker.log |
| 耗时 | 每题 worker 秒数；部分消息/工具结果时间戳；官方 grader 文本日志时间 | worker.json；trajectory.json；run_instance.log |
| 候选生成与选择 | 分析报告、轨迹摘要、提案、修改假设、预计影响任务、critic 风险、smoke、接受/拒绝理由、最终版本 | runs/swe/r0/；frontier.json；history.jsonl |
| 官方评分 | 补丁内容及哈希、是否应用、resolved、实际各项测试结果、评分脚本与输出 | grade.json；official/**/report.json、eval.sh、test_output.txt |
| 失败与恢复 | BudgetExceeded/LimitsExceeded 等；token_reservation/call_limit；基础设施缺失；失败搜索成本；复用来源与证据哈希 | worker.json；failure_summary.json；baseline_provenance.json；recovery_provenance.json |
| 容器及资源 | 镜像 ID/digest/逻辑大小、固定 CPU/内存/网络配置、原有资源保护与清理验证 | images/；固定 worker 源码；image_inventory.json；cleanup_validation.json |
| 汇总与验证 | 逐题成本、按项目通过率、新增通过与退步、全部分母、源码/镜像一致性检查 | docs/experiments/mini50_round1_results.json；final_validation.json |

上述运行相对路径均以 `work/verified-mini-50-round1-recovery/` 为根；原始基线证据在 `work/verified-mini-50-baseline-v2/`。37 份实际候选补丁有官方测试报告，13 个未提交任务直接记失败，没有伪造官方测试日志。

本次 2,638 份原始响应均有相同的 `system_fingerprint`。它提供版本漂移审计线索，但不能证明 deepseek-flash 对应不可变的权重版本。

## 下次运行前优先补齐

1. **完整请求快照及调用耗时。** 保存脱敏的实际 messages、tools、tool_choice、extra_body、有效输出上限及省略参数清单，连到本地 UUID/响应 ID；记录请求开始、结束、耗时、HTTP 状态及可获得的 HTTP request ID。现在已有原始响应与 Agent 对话，但没有逐次独立保存完整请求，也没有准确逐次 latency。当前不能把 API 时间戳或每题 worker 秒数当作调用耗时。
2. **统一 ID 与事件时间。** 固定 experiment/run/attempt/candidate/parent/round/role/task/trial/call 标识，时间使用 UTC 和单调时钟耗时；保留复制/恢复来源及计费去重。当前目录、Git 和账本可以关联，但还不是统一事件表。
3. **有效采样配置。** 对提供商支持的 temperature、top_p、seed 等显式配置和记录；不支持或省略时标明。当前这批使用未指定的提供商默认值、未传 seed，不能事后声称知道实际默认值或补出随机种子。模型响应 model、fingerprint 和运行窗口持续归档。
4. **正式实验划分与独立重复。** 保存 feedback/selection/heldout 清单、用途及哈希，区分独立搜索编号和同一候选的任务重复。本次全 50 题都是可见开发集、一个候选、每题一次；记录完善不能替代重复实验。
5. **组件干预定义。** 单独记录 diagnosis/planning/implementation/verification 的输入、输出、模型、预算和替换来源，保留干预与父候选关联。analyst/digester/propose/critic 的原生角色不能直接视为这四种能力的测量。

## 现有资料可补做的分析

输入/输出/cache token 按角色汇总、工具调用数、模型可见输出截断、上下文大小估计、补丁大小、失败分类、新增通过/退步与候选机制对照，大多可以离线从已有文件计算。估计值应标明口径，尤其不能将每题耗时误报为 API latency。

建议将预算失败拆成调用上限、实际 token 上限、请求预留不足和时间上限，将方法失败与基础设施错误分开，并同时报告有效提交率和官方通过率。若分析工具输出的诊断包含未经轨迹支持的 gold/hidden-test 断言，应作为模型假说核查，不能当作实际隐藏评分证据。

## 成本与可复现性的剩余边界

货币费用尚未估算。后续保存带时间的价格快照，分别计入缓存命中输入、未命中输入及输出价格；标明币种和估算口径，实际账单另行核对。本次 token 已齐全，但缺少价格/账单，不能把预算结算字段当作实际金额。

镜像下载、worker、官方评分和端到端时间尚未统一拆分；CPU/内存峰值也未系统采集。它们在研究运行效率或资源影响时值得补充，优先级低于请求/延迟、配置、实验谱系和数据划分。

未保存逐步完整容器文件系统快照；thinking 关闭，没有额外隐藏推理轨迹。API 密钥与认证请求头不进入实验快照。

机器可读核对：[metadata_audit.json](metadata_audit.json)。结果说明：[完整 RSI 结果](../experiments/mini50_round1.md)。
