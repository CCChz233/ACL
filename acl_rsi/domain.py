import ast
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

import yaml
from rrsi.domain import Domain
from rrsi.evaluate import TaskResult

from .grading import grade
from .settings import ROOT, load_instances, public_instance, write_json


class MiniSWEDomain(Domain):
    name = "swe"
    harness_path = "harness"
    source_exts = {".py", ".yaml", ".md"}
    briefs = {
        "analyst": "Analyze mini-SWE-agent's repository-repair trajectories. Distinguish tool/protocol failures from missing task skills. Recommend reusable harness mechanisms, never task-specific solutions.",
        "digester": "Read a repository-repair agent trajectory. Report evidence of failures, missing support, and useful behavior. The score is an external official SWE-bench result.",
        "proposer": "Edit mini-SWE-agent's agent.py or swebench.yaml. The executor, model provider, container environment, budgets and grader are external and immutable. Preserve DefaultAgent and the mini-SWE-agent Model/Environment interfaces. Propose mechanisms general across repositories, not fixes to the current issue.",
        "critic": "Review generic mini-SWE-agent changes. Reject issue-specific paths, patches, answers or case identifiers, access to host files/grading artifacts, and attempts to change the frozen executor or external budgets. Changes to shell observation formatting are allowed.",
    }
    component_signals = [
        ("prompt", [r"system_template", r"instance_template", r"swebench.yaml"]),
        ("control_flow", [r"def step", r"def run", r"execute_actions", r"def query"]),
        ("context_mgmt", [r"messages", r"summar", r"context"]),
        ("output_plumbing", [r"observation_template", r"format_error_template", r"truncat"]),
    ]

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.instances = load_instances(cfg)
        self.critic_patterns = [
            (r"test_patch|FAIL_TO_PASS|PASS_TO_PASS", "hidden evaluation data"),
            (r"DEEPSEEK_API_KEY|dotenv|os\.environ", "host credential or configuration access"),
            (r"benchmarks/datasets|acl_rsi|runs/swe|official/", "host experiment artifacts"),
            *[(re.escape(iid), "task-specific identifier") for iid in cfg["evolve_ids"]],
        ]

    def evolve_ids(self):
        return list(self.cfg["evolve_ids"])

    def heldout_ids(self):
        return list(self.cfg.get("heldout_ids", []))

    def smoke_ids(self, incumbent_per_task=None):
        return []  # Compile/constructor smoke adds no extra evaluation or API calls.

    def trial_dir(self, runs_dir: Path, job: str, task_id: str, trial: int) -> Path:
        return Path(runs_dir) / "jobs" / job / task_id / f"trial-{trial}"

    def run(self, root, runs_dir, job, ids, k, log_prefix=""):
        harness = self.harness_dir(Path(root))
        for iid in ids:
            for trial in range(k):
                directory = self.trial_dir(runs_dir, job, iid, trial)
                directory.mkdir(parents=True, exist_ok=True)
                manifest = {"instance_id": iid, "base_commit": self.instances[iid]["base_commit"],
                            "harness_sha256": self.tree_digest(harness),
                            "config_sha256": self.cfg["config_sha256"], "trial": trial}
                path = directory / "manifest.json"
                if path.exists() and json.loads(path.read_text()) != manifest:
                    raise ValueError("trial manifest changed; use a fresh experiment workspace")
                write_json(path, manifest)
                instance_path = directory / "public_instance.json"
                write_json(instance_path, public_instance(self.instances[iid]))
                worker_path = directory / "worker.json"
                if worker_path.exists() and (directory / "grade.json").exists():
                    previous = json.loads((directory / "grade.json").read_text())
                    if previous.get("infrastructure_failure"):
                        # Preserve failed evidence and let RRSI's bounded retry really rerun the trial.
                        number = len(list(directory.glob("attempt-*"))) + 1
                        archive = directory / f"attempt-{number}"
                        archive.mkdir()
                        for file in list(directory.iterdir()):
                            if file.is_file() and file.name not in {"manifest.json", "public_instance.json"}:
                                file.rename(archive / file.name)
                if not worker_path.exists():
                    cmd = [sys.executable, "-m", "acl_rsi.worker", "--config", self.cfg["config_path"],
                           "--harness", str(harness), "--instance", str(instance_path), "--output", str(directory)]
                    env = {**os.environ, "PYTHONPATH": str(ROOT)}
                    with (directory / "worker.log").open("w") as log:
                        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                                start_new_session=True)
                        try:
                            proc.wait(timeout=self.cfg["target"]["wall_seconds"] + 180)
                            if proc.returncode:
                                raise RuntimeError(f"worker failed with exit code {proc.returncode}; see worker.log")
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGTERM)
                            try:
                                proc.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                os.killpg(proc.pid, signal.SIGKILL)
                                proc.wait()
                            container_file = directory / "container.json"
                            if container_file.exists():
                                container = json.loads(container_file.read_text())["id"]
                                subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=60)
                            usage_path = directory / "usage.json"
                            actual = 0
                            if usage_path.exists():
                                records = json.loads(usage_path.read_text())["requests"]
                                actual = sum(row.get("usage", {}).get("total_tokens", 0) for row in records)
                            write_json(worker_path, {"exit_status": "WorkerTimeout", "usage": {"actual_tokens": actual}})
                            (directory / "patch.diff").write_text("")
                worker = json.loads(worker_path.read_text())
                infrastructure = worker["exit_status"] in {"DockerException", "CalledProcessError", "FileNotFoundError", "ProviderError"}
                if infrastructure:
                    write_json(directory / "grade.json", {"resolved": False, "completed": False,
                                                          "infrastructure_failure": True})
                else:
                    grade(self.instances[iid], (directory / "patch.diff").read_text(), directory,
                          self.cfg["grading_seconds"])
                print(f"[swe] {job}/{iid}/{trial}: {worker['exit_status']}", flush=True)

    def score(self, runs_dir, job, ids, k):
        results = {}
        for iid in ids:
            rewards, tokens, missing = [], [], 0
            for trial in range(k):
                directory = self.trial_dir(runs_dir, job, iid, trial)
                try:
                    outcome = json.loads((directory / "grade.json").read_text())
                    worker = json.loads((directory / "worker.json").read_text())
                except FileNotFoundError:
                    outcome, worker = {"infrastructure_failure": True}, {}
                rewards.append(float(bool(outcome.get("resolved"))))
                tokens.append(worker.get("usage", {}).get("actual_tokens") or None)
                missing += int(outcome.get("infrastructure_failure", False))
            results[iid] = TaskResult(rewards=rewards, tokens=tokens, missing=missing)
        return results, {"purpose": self.cfg["purpose"], "n_trials": len(ids) * k}

    def load_trial(self, runs_dir, job, task_id, trial):
        directory = self.trial_dir(runs_dir, job, task_id, trial)
        if not (directory / "worker.json").exists():
            return None
        trajectory = json.loads((directory / "trajectory.json").read_text()) if (directory / "trajectory.json").exists() else {}
        return {"task_id": task_id, "trajectory": trajectory,
                "worker": json.loads((directory / "worker.json").read_text()),
                "score": bool(json.loads((directory / "grade.json").read_text()).get("resolved"))}

    def render_trace(self, rec, detail=False):
        cap = 12000 if detail else 3000
        rows = [f"Task: {rec['task_id']}; externally graded resolved={rec['score']}; exit={rec['worker']['exit_status']}"]
        for index, message in enumerate(rec["trajectory"].get("messages", [])):
            # Exclude full SDK responses and private grader output.
            rows.append(f"[step {index}] {message.get('role')}: {str(message.get('content', ''))[:cap]}")
            if message.get("tool_calls"):
                rows.append(json.dumps(message["tool_calls"])[:cap])
        return "\n".join(rows)

    def task_row(self, task_id, rec, tr):
        return f"{task_id} | rewards={tr.rewards} | calls={rec['worker'].get('usage', {}).get('calls')} | exit={rec['worker']['exit_status']}"

    def smoke(self, root, runs_dir, job, ids):
        harness = self.harness_dir(Path(root))
        try:
            ast.parse((harness / "agent.py").read_text())
            config = yaml.safe_load((harness / "swebench.yaml").read_text())
            if not all(key in config for key in ("agent", "model")):
                raise ValueError("missing agent/model templates")
            from .worker import load_agent
            cls = load_agent(harness / "agent.py")
            if not all(callable(getattr(cls, key, None)) for key in ("run", "save")):
                raise ValueError("missing DefaultAgent interface")
            return True, {"stage": "compile_and_interface", "api_calls": 0}
        except (SyntaxError, ValueError, AttributeError, ImportError, KeyError) as exc:
            return False, {"stage": "compile_and_interface", "error_type": type(exc).__name__}

    @staticmethod
    def tree_digest(harness):
        digest = hashlib.sha256()
        for path in sorted(Path(harness).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(str(path.relative_to(harness)).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

