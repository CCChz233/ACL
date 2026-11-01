# SWE-bench Mini50：本地镜像永久缓存

用户已明确要求：全部 50 个任务镜像保留在本地，每题和每轮结束后都不删除，后续直接复用。

2026-10-18 已完成：从 38/50 补齐至 50/50，新增下载 12 个，全部 image ID 和 Linux/amd64 架构与固定清单一致。随后实际通过统一入口读取已完成的 GEPA 结果，并再次核验 50/50 个本地镜像，新增下载为 0，新增模型调用为 0。永久缓存与本地运行保护的 3 项测试通过。

`configs/swe-mini-image-cache.json` 锁定这 50 个官方镜像的标签、digest 和原始基线 image ID。补齐脚本先检查本地，已有且 ID 正确时不发起 pull；仅对缺失项按固定 digest 下载 Linux/amd64 镜像，再恢复官方标签。所有镜像保留，磁盘不足 4 GiB 时停止后续下载。任务容器仍正常清理。

补齐与检查均不调用模型：

```bash
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/cache_swe_mini_images.py fill
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/cache_swe_mini_images.py status
```

`--offline` 限制 uv 的依赖解析网络，不限制 Docker 下载；`status` 本身只检查本地 Docker。

后续 SWE 运行统一通过以下包装入口，先核验全部 50 个本地镜像，再启动原运行器。缓存不全会在付费执行前停止；包装入口拦截历史运行器的 Mini 镜像删除操作。原始冻结源码、预算、评分器和已保存结果不改动。已有 Docker 镜像默认本地复用，因此不需要重复 pull；每轮记录包装脚本与缓存策略哈希。

```bash
# 查看已完成的 GEPA 结果，不产生新的模型调用
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/run_swe_local.py gepa summary

# 原始 50 题基线入口；已完成工作区复用保存结果
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/run_swe_local.py baseline

# 原 RRSI 恢复入口；已完成工作区复用保存结果
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/run_swe_local.py rrsi-recovery --config configs/mini50-round1-recovery.json
```

可用运行器别名：`baseline`、`rrsi`、`rrsi-recovery`、`gepa`、`single`；后续参数原样传递。不要直接使用历史入口重新启用旧的逐题删除策略，也不要将 Mini 镜像纳入 `docker image prune -a` 等清理操作。

补齐任务通过 tmux 会话 `acl-mini50-cache` 完成；日志、逐题状态和退出码位于 `work/swe-mini-image-cache/`。`fill-result.json` 保存新增下载 12 个的记录；`status.json` 保存后续零下载复核结果，当前为 `status=completed`、`cached=50`。
