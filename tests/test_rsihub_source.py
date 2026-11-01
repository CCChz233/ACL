"""Pinned RSIHub checkout; no model, Harbor, or Docker."""
from acl_frameworks.common import ROOT, read
from acl_rsihub.native import LOCK, verify


def test_lock_points_at_extension_mapping():
    cfg = read(LOCK)
    assert cfg["source"] == "frameworks/rsihub"
    assert cfg["protocol"]["paid_runs_started"] is False
    layout = read(ROOT / "configs/project-layout.extensions.json")
    item = next(row for row in layout["sources"] if row["name"] == "RSIHub")
    assert item["canonical"] == cfg["source"]


def test_local_recipe_uses_deepseek_flash_on_miniswe():
    text = (ROOT / "configs/rsihub/deepseek-flash/evolve.yaml").read_text()
    lowered = text.lower()
    assert "gpt-5" not in lowered
    assert "codex" not in lowered
    assert lowered.count("model: deepseek/deepseek-flash") == 2
    assert "reasoning_effort" not in lowered
    assert "max_tokens: 4096" in text


def test_pinned_checkout_hashes_if_present():
    cfg = read(LOCK)
    if not (ROOT / cfg["source"]).exists():
        return
    root = verify()
    assert root == ROOT / cfg["source"]
