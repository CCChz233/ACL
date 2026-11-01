"""Verify the pinned RSIHub checkout. Does not load Harbor or call models."""
import subprocess

from acl_frameworks.common import ROOT, read, sha

LOCK = ROOT / "configs/frameworks/rsihub.json"


def verify():
    cfg = read(LOCK)
    root = ROOT / cfg["source"]
    if not root.exists():
        raise FileNotFoundError("RSIHub checkout missing; run scripts/prepare_rsihub.py --clone")
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != cfg["revision"]:
        raise ValueError("RSIHub source revision differs")
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    )
    if dirty:
        raise ValueError("RSIHub tracked source changed")
    for file, digest in cfg["files"].items():
        if sha(root / file) != digest:
            raise ValueError("RSIHub source hash differs: " + file)
    return root
