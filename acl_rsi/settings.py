import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_settings(path: str | Path) -> dict:
    load_dotenv(ROOT / ".env", override=False)
    path = Path(path).resolve()
    cfg = json.loads(path.read_text())
    cfg["config_path"] = str(path)
    for name in ("dataset", "workspace"):
        cfg[name] = str((ROOT / cfg[name]).resolve())
    cfg["api_base"] = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    cfg["model"] = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    cfg["config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evolve, heldout = cfg["evolve_ids"], cfg.get("heldout_ids", [])
    if not evolve or len(set(evolve)) != len(evolve) or set(evolve) & set(heldout):
        raise ValueError("evolve_ids must be unique, nonempty and disjoint from heldout_ids")
    return cfg


def load_instances(cfg: dict) -> dict[str, dict]:
    rows = json.loads(Path(cfg["dataset"]).read_text())
    instances = {row["instance_id"]: row for row in rows}
    if len(instances) != len(rows):
        raise ValueError("duplicate instance IDs in dataset")
    missing = set(cfg["evolve_ids"] + cfg.get("heldout_ids", [])) - instances.keys()
    if missing:
        raise ValueError(f"unknown instance IDs: {sorted(missing)}")
    return instances


def public_instance(instance: dict) -> dict:
    """Never pass reference patches, hidden tests or expected outcomes to the worker."""
    return {key: instance[key] for key in ("instance_id", "repo", "base_commit", "problem_statement")}


def write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)

