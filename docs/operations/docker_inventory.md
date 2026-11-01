# Docker 镜像盘点与清理候选

状态：初次只读盘点后，用户已授权清理；执行结果见本节。

2026-10-18 已删除 73 个无容器引用且不属于当前 SWE-bench Mini50 的镜像：50 个旧 SWE-bench、17 个 FeatureLiftBench、1 个 Terminal Bench、5 个 Python/locbench/hello-world 镜像。构建缓存已清空，Docker 本次 prune 报告回收 11.62 GB（包含删除镜像后转为可回收的层，不能与其他统计直接相加）。未删除任何容器或数据卷。当前已缓存的 Mini 镜像全部保留；9 类被 Dify 等容器引用的镜像保留。实测宿主机可用空间从约 12.7 GiB 增至 41.2 GiB，增加约 28.5 GiB。精确操作记录位于 `work/docker-audit/cleanup-20261018/result.json`。

以下为清理前的盘点快照；当前镜像数量随 Mini50 后台运行继续增加，且已切换为保留 Mini 缓存。
采集时间：2026-10-18T09:30:54.475Z

共 85 个镜像。Docker 报告镜像占用约 45.88 GB，可回收约 38.26 GB；可回收范围包含当前实验缓存，不应全部直接删除。构建缓存约 3.748 GB。

| 类别 | 数量 | 容器引用 | 建议 |
|---|---:|---:|---|
| featureliftbench | 17 | 0 | 确认旧实验不再使用后可清理 |
| current_swe50 | 3 | 0 | 保留 |
| other | 5 | 0 | 保留 |
| terminal_bench | 1 | 0 | 保留 |
| other_swebench | 50 | 0 | 确认旧实验不再使用后可清理 |
| dify_services | 9 | 9 | 保留 |

旧 SWE-bench 镜像与本轮题目 ID 无重叠；17 个 FeatureLiftBench 镜像目前无容器引用，但部分是本地构建版本，删除后可能需要重建。所有容器、数据卷、Dify 服务和当前实验镜像均不属于本清理候选。

镜像层共享且 Docker 接口的压缩/展开大小统计有差异，不能把逐镜像大小相加视作实际释放量。上一轮“每题约 1 GiB”来自 inspect 元数据；system df 中部分任务展开大小约 4 GB。实际回收空间需删除后复测。

## 待确认镜像清单

- `featureliftbench-eval:python200-prime-212930ea` — `sha256:bacb3078db5e`
- `featureliftbench-agent:python200-prime-212930ea` — `sha256:0a05b2e797e1`
- `featureliftbench-eval:python200-prime-180dc917` — `sha256:17e674e4d4ee`
- `featureliftbench-agent:python200-prime-180dc917` — `sha256:808893c0ddeb`
- `featureliftbench-agent:python200-prime-9f89ac9a` — `sha256:7b9c018c07a5`
- `featureliftbench-agent:python200-prime-7279620d` — `sha256:0d75377c6cda`
- `featureliftbench-agent:python200-prime-769f2486` — `sha256:70808ca91447`
- `featureliftbench-eval:python200-prime-7279620d` — `sha256:b0c1cf87884b`
- `featureliftbench-eval:python200-prime-769f2486` — `sha256:b8fc25c81722`
- `featureliftbench-eval:python200-prime-9f89ac9a` — `sha256:f6fa80a3b4a8`
- `featureliftbench-agent:python200-prime-742fccd6` — `sha256:dcd668072313`
- `featureliftbench-eval:python200-prime-742fccd6` — `sha256:ba892a70fbff`
- `featureliftbench-agent:openhands-rsg-pilot-v1` — `sha256:ee3b790de2bc`
- `featureliftbench-agent:rsg-phase1` — `sha256:aa570a3d8ccc`
- `featureliftbench-eval:latest` — `sha256:cccf858c5f9b`
- `featureliftbench-eval-go:latest` — `sha256:4fa67d5a44bf`
- `featureliftbench-agent:latest` — `sha256:cc6229204b71`
- `swebench/sweb.eval.x86_64.django_1776_django-11451:latest` — `sha256:c224c70ff7b4`
- `swebench/sweb.eval.x86_64.django_1776_django-11433:latest` — `sha256:2bcc81d4fc96`
- `swebench/sweb.eval.x86_64.django_1776_django-11400:latest` — `sha256:435433409f08`
- `swebench/sweb.eval.x86_64.django_1776_django-11333:latest` — `sha256:3dd97a00452a`
- `swebench/sweb.eval.x86_64.django_1776_django-11299:latest` — `sha256:69b6218bba90`
- `swebench/sweb.eval.x86_64.django_1776_django-11292:latest` — `sha256:199de3e4867d`
- `swebench/sweb.eval.x86_64.django_1776_django-11276:latest` — `sha256:e06c9bfdb304`
- `swebench/sweb.eval.x86_64.django_1776_django-11265:latest` — `sha256:a87afae829a0`
- `swebench/sweb.eval.x86_64.django_1776_django-11239:latest` — `sha256:34a04902ed37`
- `swebench/sweb.eval.x86_64.django_1776_django-11211:latest` — `sha256:08091f677ad2`
- `swebench/sweb.eval.x86_64.django_1776_django-11206:latest` — `sha256:e18698a2f7b8`
- `swebench/sweb.eval.x86_64.django_1776_django-11179:latest` — `sha256:5e92af63a5d0`
- `swebench/sweb.eval.x86_64.django_1776_django-11163:latest` — `sha256:8659f17b539c`
- `swebench/sweb.eval.x86_64.django_1776_django-11141:latest` — `sha256:78dd49837eaf`
- `swebench/sweb.eval.x86_64.django_1776_django-11149:latest` — `sha256:c498f2579013`
- `swebench/sweb.eval.x86_64.django_1776_django-11138:latest` — `sha256:dc815d469dcb`
- `swebench/sweb.eval.x86_64.django_1776_django-11133:latest` — `sha256:cf92d32f28cf`
- `swebench/sweb.eval.x86_64.django_1776_django-11119:latest` — `sha256:7ec77b424d0b`
- `swebench/sweb.eval.x86_64.django_1776_django-11099:latest` — `sha256:57060beb3096`
- `swebench/sweb.eval.x86_64.django_1776_django-11095:latest` — `sha256:00e6558c4cc9`
- `swebench/sweb.eval.x86_64.django_1776_django-11087:latest` — `sha256:b552856e03fc`
- `swebench/sweb.eval.x86_64.django_1776_django-11066:latest` — `sha256:d76032bd6cb8`
- `swebench/sweb.eval.x86_64.django_1776_django-10999:latest` — `sha256:caf176599a4a`
- `swebench/sweb.eval.x86_64.django_1776_django-10973:latest` — `sha256:38e892e7ff1a`
- `swebench/sweb.eval.x86_64.django_1776_django-10914:latest` — `sha256:f821080544e1`
- `swebench/sweb.eval.x86_64.django_1776_django-10880:latest` — `sha256:dee440908552`
- `swebench/sweb.eval.x86_64.django_1776_django-10554:latest` — `sha256:6fe93aa03ebb`
- `swebench/sweb.eval.x86_64.django_1776_django-10097:latest` — `sha256:148894532806`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-7671:latest` — `sha256:e00a59320ce1`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-8872:latest` — `sha256:d6c5c8dc8f0e`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-8707:latest` — `sha256:55e63ac83d4a`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-7606:latest` — `sha256:f4bcd149eb4c`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-7336:latest` — `sha256:a12e32454ae1`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-7166:latest` — `sha256:6909381901b8`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14995:latest` — `sha256:b29a3bf3daeb`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14598:latest` — `sha256:f1ff70694c40`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14539:latest` — `sha256:a8d0f9829ec2`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14508:latest` — `sha256:a6aea03ce1c6`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14182:latest` — `sha256:374a7f3206d2`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14365:latest` — `sha256:bb1ec8d27d47`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14369:latest` — `sha256:113488bfd3a6`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14309:latest` — `sha256:89fc1b9379b3`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-13453:latest` — `sha256:6b3593a3d1fa`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-14096:latest` — `sha256:f0277869f587`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-13977:latest` — `sha256:bcc442a117de`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-13398:latest` — `sha256:423240067cb2`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-13236:latest` — `sha256:a43e166eb5ae`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-13579:latest` — `sha256:c645e9435a14`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest` — `sha256:f3f63bb87d58`
- `swebench/sweb.eval.x86_64.astropy_1776_astropy-13033:latest` — `sha256:42797a2c686e`
