# RSIHub 接入：源码钉住，尚未实跑

日期：2026-11-01。用户确定以 [RSIHub](https://github.com/simple-agent-lab/RSIHub) 作为后续实验底座。本轮只登记来源、钉住提交、核验关键文件；**没有安装进项目 `.venv`，没有 Harbor 任务，没有模型调用。**

论文：[arXiv 2610.32253](https://arxiv.org/abs/2610.32253)（NeurIPS 2026 Meta-Agents Workshop）。固定提交 `d6554299c58bf0fe2db04ddda0277f9db67ea680`（2026-10-27），Apache-2.0。实际目录 `frameworks/rsihub/`，兼容链接 `repos/rsihub`。追加锁 [rsihub.json](../../configs/frameworks/rsihub.json)。未改四框架 [registry.json](../../configs/frameworks/registry.json)、DGM 锁，以及任何 `experiments/runs/`。

现行研究故事仍是 [证据高效上下文](../research/research_story.md)。RSIHub 是拟用的执行底座，不是已经完成的上下文方法对照。

## 为什么这样接入

RSIHub 把方法政策放在 recipe / operator 里，把执行、评测、恢复和谱系留给框架。循环为 `select → rollout → analyze → mutate → guardrail → evaluate → absorb`。评测器在可变面之外。和本项目相关的接口是：

- `library/analyze/`：把 rollout 轨迹收成有界的修改证据。现成实现包括 `ahe`、`trajectory_only`、`gepa`、`failure_patterns`、`trace_browser`。
- `library/mutate/`：在声明的可变路径上提案；recipe 配置编辑器看到哪些保留上下文。
- `src/evolve/frozen/interfaces.py`：operator 合同，后续新 analyze 应对齐这里，而不是改框架核心。

官方 AHE recipe 默认用 Harbor、Codex mutate、GPT-5.4、Terminal-Bench 2 子集，目标 seed 是 mini-swe-agent `388da74`。这与本地已冻结的 mini 2.4.6 和 DeepSeek Flash **不是同一配置**。接入名称是源码钉住，不能写成 RSIHub 原论文复现或 SWE Mini50 续跑。

## 准备

从项目根目录、现有 SWE 环境：

```sh
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python scripts/prepare_rsihub.py
VIRTUAL_ENV="$PWD/.venv" uv run --active --no-project --no-env-file --offline python -m acl_rsihub.cli check
```

`prepare_rsihub.py --clone` 只在目录缺失时克隆固定提交，不重置已有 checkout。不要把 RSIHub 装进 `.venv`：它依赖 Harbor 0.18.0 和独立 `uv.lock`，与 SWE / Terminal 两套环境分开。真实验收需要单独虚拟环境，本轮未建。

## 本地模型设置

官方 `recipes/*/evolve.yaml` 仍是 GPT-5.4，而且多数 mutate 使用 Codex。这些文件在来源锁里，不能改。

要用和 `acl_rsi` 相同的模型，初始化时指向本地 recipe，不要用 `--recipe ahe` 这一类内置名字：

```sh
evolve init --recipe-path configs/rsihub/deepseek-flash/evolve.yaml ...
```

[configs/rsihub/deepseek-flash/evolve.yaml](../../configs/rsihub/deepseek-flash/evolve.yaml) 里，评测器和 mutate 都是 MiniSWE，模型都是 `deepseek/deepseek-flash`。`deepseek/` 前缀让 RSIHub 走 LiteLLM 的对话接口；写成 `openai/...` 会改走 OpenAI Responses，DeepSeek 对不上。输出上限 4096，没有 `reasoning_effort`。

工作区 `.env` 使用现有密钥，不要把密钥写进 YAML：

```dotenv
DEEPSEEK_API_KEY=已有的密钥
OPENAI_API_KEY=同一个密钥
OPENAI_BASE_URL=https://api.deepseek.com
```

LiteLLM 的 `deepseek/` 模型读 `DEEPSEEK_API_KEY`。RSIHub 冻结运行身份时读 `OPENAI_BASE_URL`，所以两处都要设成原来的 `https://api.deepseek.com`。`acl_rsi` 里显式发送的 `thinking: disabled` 还没有接到 RSIHub 的 MiniSWE 运行器；这份 recipe 只是不再打开 reasoning effort。

## 明确还没做

- 没有 `acl_rsihub` 的 live/run。本地 recipe 还没有拿来执行 `evolve init`。
- 没有把本地 mini 2.4.6 换成上游 recipe 里的 seed。
- 没有 Terminal-Bench 2 recipe 试跑，也没有 SWE-bench 适配。
- 没有新的 analyze operator，也没有改写研究故事。
- 历史 Mini50 / 十题成绩不能当作 RSIHub 上的结果。

下一步若继续：单独环境核官方 `evolve` CLI 能否导入；再冻结 DeepSeek / 可变面 / 数据 split，才考虑在 `library/analyze` 插证据干预。付费运行必须新工作区、正预算和显式 live 开关。
