"""Run one candidate against public task fields; private grading runs separately."""
import argparse
import importlib.util
import json
import subprocess
import time
from pathlib import Path

import yaml
from minisweagent.environments.docker import DockerEnvironment

from .model import DeepSeekMiniModel
from .deepseek import BudgetExceeded, ProviderError
from .settings import load_settings, write_json


def image_name(instance_id: str) -> str:
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_').lower()}:latest"


def load_agent(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DefaultAgent


def run_trial(cfg: dict, harness: Path, instance: dict, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    templates = yaml.safe_load((harness / "swebench.yaml").read_text())
    model = DeepSeekMiniModel(cfg, templates["model"], output / "usage.json")
    env = None
    agent = None
    started = time.time()
    result = {"instance_id": instance["instance_id"], "exit_status": "not_started", "submission": ""}
    try:
        env = DockerEnvironment(
            image=image_name(instance["instance_id"]), cwd="/testbed",
            timeout=cfg["target"]["command_seconds"], pull_timeout=600,
            interpreter=["bash", "-c"],
            env={"BASH_ENV": "/root/.bashrc", "PAGER": "cat", "PIP_PROGRESS_BAR": "off"},
            run_args=["--rm", "--platform", "linux/amd64", "--network", "none", "--cpus", "2", "--memory", "6g"],
        )
        write_json(output / "container.json", {"id": env.container_id})
        agent_kwargs = dict(templates["agent"])
        # The model wrapper enforces calls/tokens regardless of edits to agent guards.
        agent_kwargs.update(step_limit=cfg["target"]["max_calls"], cost_limit=0,
                            wall_time_limit_seconds=cfg["target"]["wall_seconds"],
                            output_path=output / "trajectory.json")
        agent = load_agent(harness / "agent.py")(model, env, **agent_kwargs)
        result.update(agent.run(instance["problem_statement"]))
    except Exception as exc:
        result.update(exit_status=type(exc).__name__, error_type=type(exc).__name__)
        if isinstance(exc, BudgetExceeded):
            result["budget_stop"] = {"reason": exc.reason, **exc.details}
        if isinstance(exc, ProviderError):
            result["provider_error"] = {"type": exc.error_type, "status_code": exc.status_code}
    finally:
        if agent is not None:
            agent.save(output / "trajectory.json")
        if env is not None and env.container_id:
            subprocess.run(["docker", "rm", "-f", env.container_id], capture_output=True, timeout=60)
            env.container_id = None
        patch = result.pop("submission", "") or ""
        (output / "patch.diff").write_text(patch)
        result.update(usage=model.ledger.summary(), seconds=time.time() - started)
        if result["exit_status"] == "LimitsExceeded" and result["usage"]["calls"] >= cfg["target"]["max_calls"]:
            result["budget_stop"] = {"reason": "call_limit", "source": "mini_agent_guard",
                                     "calls": result["usage"]["calls"], "max_calls": cfg["target"]["max_calls"]}
        write_json(output / "worker.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_trial(load_settings(args.config), args.harness, json.loads(args.instance.read_text()), args.output)


if __name__ == "__main__":
    main()

