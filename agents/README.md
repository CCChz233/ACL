# Agent 源码

| Agent | 目录 | 作用 |
|---|---|---|
| mini-SWE-agent 2.4.6 | [mini-swe-agent/](mini-swe-agent) | 当前固定初始 Agent；执行模型为 DeepSeek Flash |

原始循环是 `mini-swe-agent/src/minisweagent/agents/default.py`，SWE 模板是 `mini-swe-agent/src/minisweagent/config/benchmarks/swebench.yaml`。固定提交与文件哈希见 [来源锁](../docs/agent_sources.lock.json)。

RSI 产生的 Harness 候选存入对应 [实验工作区](../experiments/README.md)，不覆盖官方源码。DeepSeek 接口、任务执行和评分的适配代码仍在根目录 `acl_*` 包，职责见 [项目结构](../docs/project_structure.md)。
