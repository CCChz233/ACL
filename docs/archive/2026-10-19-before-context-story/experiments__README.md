# 实验索引

实际工作区位于 `runs/`，旧 `work/` 链接到同一目录。配置、候选、轨迹、补丁、评分和用量账本保留原样。

| 实验 | 工作区 | 当前结果 |
|---|---|---|
| SWE Mini50 原始基线 | [runs/verified-mini-50-baseline-v2/](runs/verified-mini-50-baseline-v2/) | 31/50，62% |
| SWE Mini50 RRSI | [runs/verified-mini-50-round1-recovery/](runs/verified-mini-50-round1-recovery/) | 29/50，58%；保留原始 Harness |
| SWE Mini50 GEPA | [runs/gepa-mini50-v1/](runs/gepa-mini50-v1/) | 25/50，50%；保留原始 Harness |
| Terminal 12 题基线 | [runs/terminal-pilot-v1/](runs/terminal-pilot-v1/) | 7/12，58.3% |
| Terminal RRSI | [runs/terminal-round1/](runs/terminal-round1/) | 2 题有效评分，整轮未完成 |
| Terminal GEPA 接入 | [runs/gepa-terminal-v1/](runs/gepa-terminal-v1/) | 接入准备，无真实候选成绩 |
| Mini50 本地镜像缓存 | [runs/swe-mini-image-cache/](runs/swe-mini-image-cache/) | 已校验 50/50，使用后保留 |

其他 smoke、预算校准、失败或恢复目录继续保留。`v1`、`v2`、`recovery` 表示各自历史阶段；不同工作区的结果与用量不能混为一次实验。新实验使用新配置和工作区，不覆盖已保存结果。当前下一步是退步诊断，尚未启动多模型矩阵或训练。
