# Terminal-Bench 2.1 先导实验

## 本次运行结果

原始基线 **7/12（58.3%）**；12 题均由官方 verifier 完成判分，无 Harbor 环境/评分异常。Terminal 上 **RSI=0 轮**。本次验证的是 DeepSeek Flash 与 mini 的终端任务接入，不是 RSI 收益或论文效果复现。

总计 **381 次调用、4,967,447 token**（输入 4,870,491，输出 96,956；输入缓存命中 4,647,680、未命中 222,811）。每题均在 50 次调用／100 万 token 的预算内。

| 任务 | 官方通过 | 停止原因 | 调用 | token |
|---|---:|---|---:|---:|
| make-mips-interpreter | 否 | token 预留上限 | 32 | 902,810 |
| headless-terminal | 是 | 主动交卷 | 17 | 81,915 |
| merge-diff-arc-agi-task | 是 | 主动交卷 | 32 | 162,651 |
| build-cython-ext | 是 | 调用上限 | 50 | 844,702 |
| nginx-request-logging | 是 | 主动交卷 | 9 | 25,954 |
| configure-git-webserver | 是 | 主动交卷 | 34 | 189,616 |
| gcode-to-text | 否 | 调用上限 | 50 | 784,607 |
| db-wal-recovery | 否 | token 预留上限 | 41 | 923,015 |
| financial-document-processor | 是 | 主动交卷 | 40 | 342,032 |
| regex-log | 是 | 主动交卷 | 15 | 60,478 |
| adaptive-rejection-sampler | 否 | 连续格式错误 | 34 | 369,344 |
| raman-fitting | 否 | 主动交卷 | 27 | 280,323 |

五道失败的可观察事实：

- make-mips-interpreter：32 次调用后触发 token 预留上限；官方运行超时，未得到要求的帧图像。
- gcode-to-text：50 次调用后停止，要求的 out.txt 尚未生成。
- db-wal-recovery：41 次调用后触发 token 预留上限，恢复 JSON 未生成。
- adaptive-rejection-sampler：34 次调用；最后连续 3 次输出均达到 4,096 token，工具参数未完整生成，触发连续格式错误停止，未形成要求的 R 实现。
- raman-fitting：主动交卷且结果文件存在，但两个峰的参数未通过官方测试。

另有 build-cython-ext 用尽 50 次调用，但最终状态通过全部 11 项测试，仍计为通过。预算停止不能直接当作失败，也不能把交卷直接当作成功。

这些记录提供了上下文选择、工具准备、实现拆分和完成状态验证的候选瓶颈。还没有组件干预证据，不能据此认定某个能力是 RSI 的决定因素。

按元数据分组：软件工程 1/2、调试 2/2、系统管理 2/2、文件操作 0/2、数据处理 2/2、科学计算 0/2。每类只有两题，不能据此推断完整领域能力。12 题单次运行中，一题对应 8.33 个百分点，结果仅用于先导诊断。

审计：381 份请求参数、381 份原始响应、381 份耗时记录及 12 份完整轨迹均齐全；账本与原始响应 usage 一致。实际返回型号均为 deepseek-flash，fingerprint 一致。运行代码、配置与任务文件哈希均保持一致；JSON 日志未发现 API 密钥。

资源：原有 82 个镜像 ID 全部保留，本轮新增任务镜像标签与任务容器均已清理；审计时磁盘可用约 19.08 GiB。

逐题结构化结果见 [terminal_pilot_results.json](terminal_pilot_results.json)；完整运行材料位于 `work/terminal-pilot-v1/`，最终审计为其中 `final-audit.json`。

正式进入 RSI 前，先补全超时观测、冻结相同的环境准备与计时规则，并从未用于本次执行的任务中固定独立评测集；当前 12 题和 extract-elf 对照作为开发材料。Terminal 的 RRSI 搜索 Domain 尚未接入，当前不启动训练。

数据隔离：原始 verifier 输出可能含参考数值，仅作为宿主机审计材料保存，不能直接发送给 Improver。`work/terminal-pilot-v1/public-feedback.json` 仅包含 reward、停止原因、用量与 Agent 自身轨迹路径；后续 Domain 应按此白名单构造反馈，屏蔽 tests、solution 和原始 verifier 日志。

当前阶段：12 题先导基线与最终审计已完成；尚未进行 Terminal-Bench RSI 搜索。

固定 DeepSeek Flash（thinking disabled）与 mini-SWE-agent 2.4.6 的原始 DefaultAgent 循环。通过 Harbor 0.24.0 的官方 Docker 生命周期、公开任务说明与官方 verifier 接入 Terminal-Bench 2.1。必要的任务接口修改是：使用通用终端任务提示；以容器最终状态交卷，取消 SWE-bench 专用的 Git patch 要求。模型只接收 instruction.md 和自身执行结果；测试与参考解不进入模型上下文。

配置及逐文件哈希见 `configs/terminal-pilot-v1.json`。任务仓库固定至 `7131e4375048a0e408a8fb404b5f499d726b695b`。

## 抽样与预算

从官方元数据中先筛选无 GPU、CPU 不超过 2、内存不超过 4096 MiB、官方 agent timeout 不超过 1800 秒、不使用自定义 Compose 的任务。六类各按 SHA256(`acl-terminal-pilot-v1:` + task_id) 排序取前 2 题，共 12 题。没有使用模型成绩筛题。该子集用于接入与失败诊断，不能代表全部 89 题。

每题最多 50 次调用、100 万 token、单次输出 4096 token，命令超时 60 秒；agent 时间为官方上限与 1200 秒的较小值（make-mips-interpreter 因而从官方 1800 秒截至 1200 秒）。请求预算包含保守的 token 预留，可能提前终止。全批最多 600 次调用、1200 万 token，不自动重试付费执行。官方 verifier 每题最多 900 秒。

先在独立的 extract-elf 任务上验收官方 oracle 与 no-op 对照，不使用模型，不纳入 12 题成绩。Docker 使用 linux/amd64；本机 ARM 上模拟执行，速度不能与原生 Linux 直接比较。串行执行，磁盘不足 4 GiB 停止，只删除本轮新增的任务镜像标签，保留已有镜像。

## 数据与判分

`work/terminal-pilot-v1/` 保存冻结配置、代码哈希、依赖版本、镜像摘要、官方 trial result、verifier 输出、完整 mini 轨迹、逐次公开请求与原始响应、token/cache 统计、API 延迟、停止原因及资源清理记录。API 密钥留在宿主机，不写入日志或注入任务容器。

官方 reward=1 计为通过。达到调用、token 或时间上限时，也评分最终环境状态；这与 SWE-bench 的 patch 提交流程不同。停止原因和 reward 分开报告。环境/评分异常另列，不能解释成模型能力下降。

先导完成后，检查通过率、失败类型、预算消耗和环境异常，再确定独立的搜索集与保留评测集。当前 12 题不应在反复观察后仍被称为无污染的最终测试集；更换 benchmark 也不保证 RSI 获得正收益。

## 执行与查看

```bash
.venv-terminal/bin/python -m acl_terminal.run controls
.venv-terminal/bin/python -m acl_terminal.run baseline
.venv-terminal/bin/python scripts/terminal_pilot_status.py
.venv-terminal/bin/python -m acl_terminal.run summary
```

基线会跳过已有完整 result.json；若存在未完成 trial，会停止要求恢复，避免无提示重跑付费模型。不要删除 usage ledger 后重跑。运行中不得修改被冻结的配置、mini 源码或适配器；恢复前会检查运行代码与任务文件哈希。

本次接入验收：extract-elf 的官方 oracle reward=1、no-op reward=0，均无 Harbor 异常；另有 2 项适配器测试通过（含模拟模型的完整 mini 循环与日志验收）。验收后只修正依赖清单的保存和下载后的磁盘阈值检查，单独保留 preflight-runtime-lock.json；首次真实调用前写入 baseline runtime-lock.json。

记录解释：API 调用数以 usage.json 的请求账本为准。mini 的循环计数可能包含一次被预算器拒绝、实际未发送的尝试。Token 为累计请求用量，包含缓存命中的输入；缓存命中与未命中另外报告，不代表独立文本大小。金额未估算，Harbor 的 cost_usd 与自定义 currency_cost 为 null；mini 原生 model_cost/instance_cost 的占位 0 不能解释成免费。

保存范围为完整消息轨迹、发送参数、原始响应、官方评分与声明的 artifacts；本轮不保存整个容器文件系统或服务进程快照。长命令超时由 Harbor 结束宿主端执行等待，观测中只保留异常类型，可能没有超时前的部分 stdout。这些是当前先导接口的限制，后续若修改必须建立新的协议版本并重测对照，不能在本批中途修改。

mini 的代码与 DeepSeek 客户端在宿主机执行，Harbor 负责创建官方任务容器、执行 shell 命令和运行 verifier。setup 不向任务容器额外安装 Python、R 或 mini 的运行依赖；Agent 自己需要的任务工具在执行预算内准备。这是本地先导协议，不能直接与预先安装语言环境的其他 Agent 成绩或论文速度对照。后续 H₀/H₁ 比较必须使用同一种准备与计时方式。
