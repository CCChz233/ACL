# 配置索引

更新：2026-10-20。实验运行时的配置和源锁保留原字节；从本页按用途找文件，不直接改旧配置后重新运行。

| 用途 | 配置 |
|---|---|
| 正式目录映射 | [project-layout.json](project-layout.json)，新增来源合并 [project-layout.extensions.json](project-layout.extensions.json) |
| 五框架来源与适配 | [frameworks/registry.json](frameworks/registry.json)、[frameworks/dgm.json](frameworks/dgm.json) |
| RSIHub 源码钉住 | [frameworks/rsihub.json](frameworks/rsihub.json)；不改五套已有锁 |
| RSIHub 的 DeepSeek Flash recipe | [rsihub/deepseek-flash/evolve.yaml](rsihub/deepseek-flash/evolve.yaml)；不改上游 recipe |
| 最新已完成高预算两轮 | [full10-highbudget-two-rounds-v1.json](full10-highbudget-two-rounds-v1.json)；补全约束另见 [协议](../docs/experiments/multiround_completion.md) 与独立批次记录 |
| 历史低预算/已缩减五轮 | [full10-two-rounds-v1.json](full10-two-rounds-v1.json)、[full10-five-rounds-v1.json](full10-five-rounds-v1.json) |
| 历史四题/六题统一试跑 | [unified-hard10-v1.json](unified-hard10-v1.json) |
| DGM 困难十题开发 | [dgm-hard10-v1.json](dgm-hard10-v1.json)；template 仅作模板 |
| Mini50 无 RSI / RRSI / GEPA | [mini50-baseline.json](mini50-baseline.json)、[mini50-round1.json](mini50-round1.json)、[mini50-round1-recovery.json](mini50-round1-recovery.json)、[gepa-mini50-v1.json](gepa-mini50-v1.json) |
| Terminal | [terminal-pilot-v1.json](terminal-pilot-v1.json)、[terminal-round1.json](terminal-round1.json)、[gepa-terminal-v1.json](gepa-terminal-v1.json) |
| Mini 镜像永久缓存 | [swe-mini-image-cache.json](swe-mini-image-cache.json)；标签及 digest/ID，运行后保留 |

其余 smoke、预算校准、旧完整闭环与 requirements lock 保留历史用途。源码版本锁位于 `docs/*sources.lock.json`、`benchmarks/sources.lock.json` 和各实验批次内，不搬动或重写。

改变协议时新建配置版本和工作区。配置里有 API 端点与模型 ID 不代表允许启动新付费批次；密钥继续只保留在本地环境文件，不写入配置。
