# GEPA × mini-SWE-agent × SWE-bench Mini 50

本轮使用 GEPA 官方核心 `gepa.optimize`，固定 DeepSeek Flash、mini-SWE-agent 和原 SWE-bench Verified Mini 50 题。单轮候选已全部完成：25/50（50%），原始基线 31/50（62%），新增修好 3 题、退步 9 题，保留原始 Harness；原始证据见工作区 `summary.json`。这是新上下文研究之前的工程先导，不是 EAEC 或其他上下文方法的结果。

- 原始 H0：31/50（62%），复用已冻结的真实执行及官方评分记录，不重新调用模型。
- 历史 RRSI H1：29/50（58%）。
- GEPA：先从 H0 的 8 条失败、3 条成功的公开交互摘录和二元反馈反思一次，再执行一个新候选的全部 50 题。候选评分与选择使用完整 50 题，保留原始成功轨迹作为回归证据。
- 模型：搜索和任务执行均为 `deepseek-flash`，thinking 关闭。原始 YAML 的其他模型名称是未使用的占位字段，真实请求由外部 DeepSeek 适配器发送。
- 修改空间：仅 `swebench.yaml` 的四个提示模板；`agent.py`、工具、环境、预算和评分器冻结。范围与上一轮 RRSI 实际产出的提示修改相近，但不等于比较两个框架的全部能力。
- 每题最多 50 次调用、1,000,000 token；整批最多 2,500 次任务调用、50,000,000 token。搜索上限 80 次、1,000,000 token，本轮实际设计为一次反思请求，输出上限 8,192 token。
- 复用官方镜像且要求 image ID 与 H0 相同。最初串行拉取并清理本轮新下载镜像；2026-10-18 用户要求清理无用镜像并将 Mini 镜像保存在本地后，改为保留本轮 Mini 镜像。磁盘剩余不足 4 GiB 仍停止。
- 不自动重复付费任务；保存补丁后，评分器基础设施失败最多单独重评一次。无效评分中止，不记为失败题。空补丁、无效补丁、明确评分超时仍按原协议记为方法失败。

查看后台：

```bash
tmux attach -t acl-gepa-swe50
tail -f /Users/chz/code/ACL/work/gepa-mini50-v1/controller.log
cat /Users/chz/code/ACL/work/gepa-mini50-v1/controller.json
cat /Users/chz/code/ACL/work/gepa-mini50-v1/summary.json
```

目录 `/Users/chz/code/ACL/work/gepa-mini50-v1/` 保存冻结清单、完整搜索请求/响应、反思输入和候选、镜像标识、每题 API 请求/响应、token 与时间账本、交互轨迹、提交补丁、官方测试日志和评分、清理记录。`summary.json` 在每题评分完成时更新；更实时的调用量可看各题 `usage.json`。`exit-code.txt` 在控制器退出时写入，0 代表正常退出，非 0 需查看控制器日志。

实现位于 `acl_gepa_swe/`，独立于已经冻结的 RRSI 和 Terminal 接入代码。启动前离线验证了原生 GEPA 两题完整循环、评分私有信息隔离、缓存复用、预算冻结及中断不重复付费，共 3 个测试通过。运行命令由 `work/gepa-mini50-v1/launch.sh` 固定。

本轮是相同开发集的一次候选比较；没有独立 heldout，也没有重复随机种子。结果可判断这一候选的效果，不能据此证明 GEPA 全面优于 RRSI 或模型获得了可迁移的自我改进能力。

2026-10-18 存储策略变更：删除 73 个无容器引用且不属于当前 Mini50 的镜像，清空构建缓存；保留当前 Mini 镜像、9 类被其他容器引用的服务镜像、所有容器与数据卷。磁盘可用空间从约 12.7 GiB 增至 41.2 GiB。清理时仅暂停调度控制器，正在执行的任务独立完成并保存；随后使用同一候选和已缓存的 GEPA 反思续跑，没有重新执行已保存的付费任务。变更只涉及 `executor.py` 的镜像释放和清理审计，配置、Harness、模型、预算、评分器保持不变；新旧运行清单、源代码备份及授权记录保存在 `work/docker-audit/cleanup-20261018/` 和本轮的 `storage-policy-transition.json`。后台控制器现在位于 tmux 会话的 `retain-mini` 窗口，原 `zsh` 窗口退出码 137 对应本次有记录的切换，不表示当前续跑失败。切换后搜索请求仍为 1 次，已完成 16/50 题并进入下一题。
