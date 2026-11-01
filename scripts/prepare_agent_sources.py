#!/usr/bin/env python3
"""Restore pinned official agent sources without changing existing checkouts."""
import hashlib
import json
import subprocess
from pathlib import Path
from project_paths import source_location

ROOT = Path(__file__).resolve().parents[1]


def prepare(lock_name):
    lock = json.loads((ROOT / "docs" / lock_name).read_text())
    directory = source_location(lock["local_path"])
    if not directory.exists():
        directory.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", lock["url"], str(directory)], check=True)
        subprocess.run(["git", "-C", str(directory), "checkout", lock["revision"]], check=True)
    if (directory / ".git").exists():
        result = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                                check=True, capture_output=True, text=True)
        if result.stdout.strip() != lock["revision"]:
            raise ValueError(f"{directory.name}: revision differs from lock; existing checkout was not modified")
        if subprocess.run(["git", "-C", str(directory), "diff", "--quiet"], check=False).returncode:
            raise ValueError(f"{directory.name}: upstream files have local changes")
    elif not lock.get("target_files_sha256"):
        raise ValueError(f"{directory.name}: non-Git source requires locked file hashes")
    for relative, expected in lock.get("target_files_sha256", {}).items():
        actual = hashlib.sha256((directory / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"{directory.name}/{relative}: source hash mismatch")
    print(f"{directory.name}: pinned source verified ({lock['revision'][:12]})")


if __name__ == "__main__":
    prepare("agent_sources.lock.json")
    prepare("rrsi_sources.lock.json")
