"""Replay frozen baseline/candidate harnesses at a new execution budget, without search."""
import argparse
import hashlib
import json
import logging
import subprocess
from pathlib import Path

from rrsi.evaluate import evaluate

from .domain import MiniSWEDomain
from .settings import ROOT, load_settings, write_json


def source_git(repo: Path, *args) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repo)


def prepare_snapshots(cfg):
    workspace = Path(cfg["workspace"])
    source = cfg["frozen_sources"]
    repo = (ROOT / source["repo"]).resolve()
    commits = {name: source_git(repo, "rev-parse", f"{source[name]}^{{commit}}").decode().strip()
               for name in ("base", "candidate")}
    if any(commits[name] != source[name] for name in commits):
        raise ValueError("frozen source commits must be full immutable hashes")
    manifest = {"purpose": cfg["purpose"], "config_sha256": cfg["config_sha256"],
                "dataset_sha256": hashlib.sha256(Path(cfg["dataset"]).read_bytes()).hexdigest(),
                "model": cfg["model"], "api_base": cfg["api_base"], "thinking": cfg.get("thinking", False),
                "source_commits": commits, "target_limits": cfg["target"],
                "runner_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((ROOT / "acl_rsi").glob("*.py"))}}
    path = workspace / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("recheck inputs changed; choose a fresh workspace")
    snapshots = {}
    for name, commit in commits.items():
        snapshot = workspace / "snapshots" / name
        entries = source_git(repo, "ls-tree", "-rz", commit, "--", "domains/swe/harness").split(b"\0")
        if not any(entries):
            raise ValueError("source commit has no harness")
        for entry in filter(None, entries):
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, oid = metadata.split()
            relative = Path(raw_path.decode())
            if mode not in (b"100644", b"100755") or kind != b"blob" or ".." in relative.parts:
                raise ValueError("frozen harness must contain regular files only")
            file = snapshot / relative
            data = source_git(repo, "cat-file", "blob", oid.decode())
            if file.exists() and file.read_bytes() != data:
                raise ValueError(f"frozen snapshot was modified: {name}/{relative}")
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        snapshots[name] = snapshot
    write_json(path, manifest)
    return snapshots


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs/budget-recheck.json"))
    parser.add_argument("--prepare-only", action="store_true", help="Verify snapshots and smoke without API calls")
    args = parser.parse_args()
    cfg = load_settings(args.config)
    workspace = Path(cfg["workspace"])
    snapshots = prepare_snapshots(cfg)
    domain = MiniSWEDomain(cfg)
    runs = workspace / "runs" / "swe"
    for name, snapshot in snapshots.items():
        ok, detail = domain.smoke(snapshot, runs, name + "_smoke", [])
        write_json(workspace / f"{name}_smoke.json", {"ok": ok, **detail})
        if not ok:
            raise RuntimeError(f"{name} smoke failed")
    if args.prepare_only:
        print(json.dumps({"prepared": str(workspace), "api_calls": 0}))
        return
    summary = {"purpose": cfg["purpose"], "search_calls": 0, "status": "running", "evaluations": {}}
    try:
        for name, snapshot in snapshots.items():
            print(f"[recheck] {name}: max {cfg['target']['max_calls']} calls / {cfg['target']['max_tokens']} tokens", flush=True)
            ev = evaluate(domain, snapshot, runs, name, cfg["evolve_ids"], cfg["rrsi"]["k"])
            summary["evaluations"][name] = ev.to_json()
            write_json(workspace / "summary.json", summary)
            if ev.missing:
                raise RuntimeError(f"{name} infrastructure failure; inspect preserved records before retrying")
        summary["status"] = "completed"
    except Exception as exc:
        summary.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        write_json(workspace / "summary.json", summary)
    print(json.dumps({"summary": str(workspace / "summary.json"), **summary}, indent=2))


if __name__ == "__main__":
    main()
