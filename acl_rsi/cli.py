import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from .settings import ROOT, load_instances, load_settings, write_json


def git(repo, *args):
    result = subprocess.run(["git", "-c", "user.name=ACL RSI", "-c", "user.email=acl-rsi@localhost", *args],
                            cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def prepare(cfg):
    repo = Path(cfg["workspace"]) / "repo"
    source = ROOT / "repos" / "mini-swe-agent"
    rrsi = ROOT / "repos" / "rrsi"
    rrsi_lock = json.loads((ROOT / "docs" / "rrsi_sources.lock.json").read_text())
    if git(rrsi, "rev-parse", "HEAD") != rrsi_lock["revision"]:
        raise ValueError("RRSI checkout differs from source lock")
    if git(rrsi, "diff", "--name-only"):
        raise ValueError("RRSI upstream has local source modifications")
    mini_lock = json.loads((ROOT / "docs/agent_sources.lock.json").read_text())
    for relative, expected in mini_lock.get("target_files_sha256", {}).items():
        if hashlib.sha256((source / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"mini source differs from lock: {relative}")
    inputs = {
        "agent.py": source / "src/minisweagent/agents/default.py",
        "swebench.yaml": source / "src/minisweagent/config/benchmarks/swebench.yaml",
        "LICENSE.md": source / "LICENSE.md",
    }
    manifest = {"rrsi_revision": rrsi_lock["revision"],
                "mini_revision": mini_lock["revision"],
                "source_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()},
                "dataset_sha256": hashlib.sha256(Path(cfg["dataset"]).read_bytes()).hexdigest(),
                "runner_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sorted((ROOT / "acl_rsi").glob("*.py"))},
                "config_sha256": cfg["config_sha256"], "model": cfg["model"], "api_base": cfg["api_base"],
                "thinking": cfg.get("thinking", False), "purpose": cfg["purpose"]}
    seed_manifest = repo / "source_manifest.json"
    if seed_manifest.exists():
        if json.loads(seed_manifest.read_text()) != manifest:
            raise ValueError("workspace configuration changed; select a fresh workspace")
        return repo
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-b", "codex/seed")
    domain_dir = repo / "domains" / "swe"
    harness = domain_dir / "harness"
    harness.mkdir(parents=True, exist_ok=True)
    for name, path in inputs.items():
        shutil.copy2(path, harness / name)
    (domain_dir / "SKILL.md").write_text(
        "Improve generic mini-SWE-agent behavior. Keep DefaultAgent's public interface. "
        "Edit only this harness. Never encode task-specific source fixes, IDs, reference patches, "
        "private tests or answers. Do not read host artifacts, credentials or the grader. "
        "Model endpoints, call/token/time limits and task containers are externally fixed.\n")
    (domain_dir / "PATTERNS.md").write_text(
        "Prefer evidence-based, bounded changes to agent control flow, prompts and observation formatting. "
        "Preserve successful behavior. A generic mechanism must apply beyond the current issue.\n")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    write_json(seed_manifest, manifest)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Seed pinned mini-SWE-agent harness for RRSI smoke")
    return repo


def make_run(cfg):
    from rrsi.config import RRSIConfig
    from rrsi.loop import Run
    from .domain import MiniSWEDomain
    repo = prepare(cfg)
    domain = MiniSWEDomain(cfg)
    domain.root = repo / "domains" / "swe"
    settings = RRSIConfig(**cfg["rrsi"], proposer_model=cfg["model"],
                          analyst_model=cfg["model"], critic_model=cfg["model"])
    return Run(domain, settings, repo, Path(cfg["workspace"]) / "runs")


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="RRSI + mini-SWE-agent + DeepSeek engineering runner")
    parser.add_argument("--config", default=str(ROOT / "configs/smoke.json"))
    parser.add_argument("command", choices=["doctor", "probe", "prepare", "smoke", "verify-grader", "baseline", "round", "run", "status"])
    parser.add_argument("--round", type=int, default=0)
    args = parser.parse_args()
    cfg = load_settings(args.config)
    if args.command == "doctor":
        import importlib.metadata
        import os
        versions = {name: importlib.metadata.version(name) for name in ("rrsi", "mini-swe-agent", "swebench", "openai")}
        result = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}} {{.Architecture}}"], capture_output=True, text=True)
        print(json.dumps({"python": sys.version.split()[0], "versions": versions, "model": cfg["model"],
                          "api_base": cfg["api_base"], "key_configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
                          "docker_ready": result.returncode == 0, "docker": result.stdout.strip()}, indent=2))
        return
    if args.command == "probe":
        from .deepseek import DeepSeekClient, UsageLedger
        ledger = UsageLedger(Path(cfg["workspace"]) / "probe_usage.json", 4, 20000)
        response = DeepSeekClient(cfg, ledger, "probe", cfg["search"]).generate(
            'Return the JSON object {"ok": true}.', json_only=True, max_tokens=128)
        print(json.dumps({"ok": json.loads(response).get("ok") is True, "usage": ledger.summary()}))
        return
    if args.command == "prepare":
        print(prepare(cfg))
        return
    run = make_run(cfg)
    if args.command == "smoke":
        ok, details = run.domain.smoke(run.repo, run.runs, "smoke", [])
        print(json.dumps({"ok": ok, **details}))
        if not ok:
            raise SystemExit(1)
        return
    if args.command == "verify-grader":
        from .grading import NO_FIX_PATCH, grade
        reports = []
        instances = load_instances(cfg)
        for iid in cfg["evolve_ids"]:
            for label, patch, expected in [("reference", instances[iid]["patch"], True), ("no_fix", NO_FIX_PATCH, False)]:
                report = grade(instances[iid], patch, Path(cfg["workspace"]) / "grader_checks" / iid / label,
                               cfg["grading_seconds"])
                reports.append({"instance_id": iid, "control": label, **report})
                if not report["completed"] or report["resolved"] != expected:
                    write_json(Path(cfg["workspace"]) / "grader_checks" / "summary.json", reports)
                    raise RuntimeError(f"grader control {label} failed for {iid}; see grader_checks")
        write_json(Path(cfg["workspace"]) / "grader_checks" / "summary.json", reports)
        print(json.dumps(reports, indent=2))
        return
    if args.command == "status":
        print(json.dumps(run.frontier(), indent=2))
        return
    from .deepseek import bind_search_client
    ledger = bind_search_client(cfg, Path(cfg["workspace"]) / "search_usage.json")
    try:
        if args.command == "baseline":
            if run.frontier_path.exists():
                raise ValueError("baseline already exists; choose a fresh workspace to restart")
            run.baseline()
        elif args.command == "round":
            run.round(args.round)
        else:
            if not run.frontier_path.exists():
                run.baseline()
            for index in range(len(run.frontier()["trajectory"]) - 1, cfg["rrsi"]["T"]):
                run.round(index)
    except Exception as exc:
        # Keep failed paid attempts inspectable without serializing provider exceptions.
        write_json(Path(cfg["workspace"]) / "failure.json", {
            "status": "failed", "command": args.command, "error_type": type(exc).__name__,
            "config_sha256": cfg["config_sha256"], "search_usage": ledger.summary(),
        })
        raise
    summary = {"purpose": cfg["purpose"], "model": cfg["model"], "config_sha256": cfg["config_sha256"],
               "frontier": run.frontier(), "search_usage": ledger.summary()}
    write_json(Path(cfg["workspace"]) / "summary.json", summary)
    print(json.dumps({"summary": str(Path(cfg["workspace"]) / "summary.json"),
                      "search_usage": summary["search_usage"]}, indent=2))


if __name__ == "__main__":
    main()

