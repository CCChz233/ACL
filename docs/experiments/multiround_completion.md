# 高预算十题对比：缺失阶段恢复

2026-10-20 用户明确要求补齐无结果项并重跑，替代此前夜间停止要求。只恢复 HarnessFix/DGM；Meta-Harness、GEPA、RRSI不重跑，Meta第一轮运行时Bug与0/10记录保留。

## 恢复边界

- 工作区：`experiments/runs/full10-highbudget-completion-v1`；包：`acl_multiround_recovery`。
- HarnessFix第一轮原始十题已完整评分5/10。原生边界在评测后读取`evaluations/v1/trials`，共同评测器实际写入`evaluations/candidate/trials`。恢复只修目录映射，复制已有产物和评分，在新工作区重放原生比较/选择。禁止新增模型请求、任务执行或重新评分。第二轮从原生实际保留版本继续。
- DGM第一轮在结构验证回调中递归：共同validate动态导入adapter.validate，后者被绑定至Delivery.ensure，后者又进入共同validate。恢复将结构验证器绑定为原始不可递归函数，不放宽修改范围、真实修改或协议检查。
- DGM第一次与第二次原生候选均能在正常验证器下通过离线检查。固定重放**第一次原生候选node_0000**，不依据评测结果选择候选，不人工修改源码。重新进入原生验证、十题评测和archive选择，再进行第二轮。
- 既有日志、失败状态、候选与成本不覆盖。新增恢复结果单列来源，不冒充未改动的原生论文复现，也不等于纯预算消融。

## 固定条件与开销

DeepSeek Flash、mini-SWE-agent、原先同十题、共同H0 3/10；每题50调用/100万token/1200秒不变。每轮400调用/800万token，原生300/600万与模型修复余额规则不变。第一轮原搜索账本完整继承，包含DGM第二份无用候选开销；第二轮使用原本未使用的预算。

最多新增30次任务执行（HF第二轮10 + DGM两轮20），与旧70合计最多100。合并调用/token仍不超过9000/1.8亿。账本按request ID去重；HF缓存重放不重复计成本/任务数。全部50个任务镜像永久保留，只使用本地固定镜像。

## 验证与交付

新增4项离线回归覆盖DGM动态结构绑定递归、原首份DGM候选有效性、HF路径映射/拒绝未知缺失路径、复用评分禁止启动worker。与旧回归合计38项通过。源码、配置和重放证据在新增付费调用前快照冻结；每个步骤独立进程，串行运行，遇到新的基础设施错误不自动重复付费worker。

运行：`python -m acl_multiround_recovery.prepare`，随后`python -m acl_multiround_recovery.batch`（项目uv环境）。`report.md`与`summary.json`合并五个框架，列分数、新增解决、退化、最终保留及恢复来源。所有十题仍属反复使用的开发数据，单次结果不能证明泛化或稳定优劣。
