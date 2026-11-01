import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

from acl_rsi.deepseek import BudgetExceeded, UsageLedger, normalize_json_response
from acl_rsi.domain import MiniSWEDomain
from acl_rsi.settings import public_instance


def test_public_task_omits_reference_and_hidden_tests():
    task = {"instance_id": "a", "repo": "r", "base_commit": "b", "problem_statement": "p",
            "patch": "SECRET", "test_patch": "SECRET", "FAIL_TO_PASS": ["SECRET"]}
    assert public_instance(task) == {"instance_id": "a", "repo": "r", "base_commit": "b", "problem_statement": "p"}


def test_json_with_embedded_code_fences_is_not_replaced_by_the_example():
    response = json.dumps({"action": "report", "evidence": 'The tool returned ```json\n{"command":"inspect"}\n```.'})
    assert json.loads(normalize_json_response(response))["action"] == "report"
    assert json.loads(normalize_json_response('```json\n{"action":"report"}\n```')) == {"action": "report"}
    assert json.loads(normalize_json_response('{"action":"read_file","path":"agent.py"}\nExplanation.')) == {
        "action": "read_file", "path": "agent.py"}
    assert json.loads(normalize_json_response('{"action":"read_file"}\n{"action":"write_file"}')) == {
        "action": "read_file"}


def test_budget_reservations_are_atomic_across_threads(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.json", 3, 100000)
    def reserve(_):
        try:
            return ledger.reserve("role", [{"role": "user", "content": "x"}], 10)
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(reserve, range(12)))
    assert len([rid for rid in ids if rid]) == 3
    assert ledger.summary()["calls"] == 3
    rid = next(rid for rid in ids if rid)
    ledger.finish(rid, {"total_tokens": 12}, "model")
    assert ledger.summary()["completed"] == 1
    assert ledger.summary()["actual_tokens"] == 12
    with pytest.raises(BudgetExceeded) as stop:
        ledger.reserve("role", [], 1)
    assert stop.value.reason == "call_limit"


def test_over_budget_request_is_never_recorded_as_sent(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.json", 10, 5000)
    with pytest.raises(BudgetExceeded) as stop:
        ledger.reserve("role", [{"role": "user", "content": "x" * 6000}], 10)
    assert stop.value.reason == "token_reservation"
    assert stop.value.details["actual_tokens"] == 0
    assert not ledger.summary()["calls"]


def test_actual_token_limit_is_distinct_from_preflight_reservation(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.json", 10, 5000)
    rid = ledger.reserve("role", [], 10)
    ledger.finish(rid, {"total_tokens": 5000}, "model")
    with pytest.raises(BudgetExceeded) as stop:
        ledger.reserve("role", [], 10)
    assert stop.value.reason == "token_limit"
    assert ledger.summary()["calls"] == 1


def test_missing_trial_counts_as_failure_in_full_denominator(tmp_path):
    # Construct only the scoring boundary: it must not need an API or container.
    domain = object.__new__(MiniSWEDomain)
    domain.cfg = {"purpose": "test"}
    directory = domain.trial_dir(tmp_path, "base", "a", 0)
    directory.mkdir(parents=True)
    (directory / "grade.json").write_text(json.dumps({"resolved": True, "completed": True}))
    (directory / "worker.json").write_text(json.dumps({"usage": {"actual_tokens": 100}}))
    results, _ = domain.score(tmp_path, "base", ["a"], 2)
    assert results["a"].rewards == [1.0, 0.0]
    assert results["a"].mean == 0.5
    assert results["a"].missing == 1


def test_batch_progress_keeps_pending_and_infrastructure_separate(tmp_path):
    from acl_rsi.mini50 import progress
    cfg = {"workspace": str(tmp_path), "evolve_ids": ["pass", "infra", "pending"]}
    for iid, outcome in [("pass", {"completed": True, "resolved": True}),
                         ("infra", {"completed": False, "infrastructure_failure": True})]:
        trial = tmp_path / "runs/jobs/base" / iid / "trial-0"
        trial.mkdir(parents=True)
        (trial / "worker.json").write_text(json.dumps({"usage": {"calls": 2, "actual_tokens": 100}}))
        (trial / "grade.json").write_text(json.dumps(outcome))
    result = progress(cfg, tmp_path / "runs", "running")
    assert (result["n_total"], result["n_completed"], result["n_resolved"], result["n_infrastructure_failures"]) == (3, 1, 1, 1)
    assert result["api_calls"] == 4


def test_image_cleanup_preserves_preexisting_image_even_if_owned_record_is_stale(tmp_path):
    from types import SimpleNamespace
    from acl_rsi.mini50 import StreamingDomain
    client = SimpleNamespace(images=SimpleNamespace(
        get=lambda _: SimpleNamespace(id="existing"),
        remove=lambda *args, **kwargs: pytest.fail("must not remove preexisting images")))
    owned = {"task:latest": "existing"}
    StreamingDomain.release(client, "task:latest", owned, {"existing"}, tmp_path / "cache.json")
    assert owned == {"task:latest": "existing"}


def test_image_cleanup_removes_only_owned_tag_without_pruning_parents(tmp_path):
    from types import SimpleNamespace
    from acl_rsi.mini50 import StreamingDomain
    removed = []
    client = SimpleNamespace(images=SimpleNamespace(
        get=lambda _: SimpleNamespace(id="new"),
        remove=lambda *args, **kwargs: removed.append((args, kwargs))))
    owned = {"task:latest": "new"}
    StreamingDomain.release(client, "task:latest", owned, {"existing"}, tmp_path / "cache.json")
    assert removed == [(("task:latest",), {"force": False, "noprune": True})]
    assert not owned


def test_rrsi_worktrees_isolate_candidate_edits_and_persist_selection(tmp_path):
    from rrsi import gitops
    from rrsi.evaluate import EvalResult, TaskResult
    from rrsi.config import RRSIConfig
    from rrsi.selection import Candidate, select_round
    subprocess.run(["git", "init", "-q", str(tmp_path / "repo")], check=True)
    repo = tmp_path / "repo"
    (repo / "harness.py").write_text("x = 0\n")
    gitops.commit_path(repo, "harness.py", "seed")
    gitops.ensure_branch(repo, "evolve/test")
    first = gitops.worktree_add(repo, tmp_path / "first", "test/first", "evolve/test")
    second = gitops.worktree_add(repo, tmp_path / "second", "test/second", "evolve/test")
    (first / "harness.py").write_text("x = 1\n")
    commit = gitops.commit_path(first, "harness.py", "candidate")
    assert (second / "harness.py").read_text() == "x = 0\n"
    base = EvalResult("base", 1, {"a": TaskResult([0.0], tokens=[100])}, 0.0, 100, 1, 0)
    improved = EvalResult("candidate", 1, {"a": TaskResult([1.0], tokens=[100])}, 1.0, 100, 1, 0)
    candidate = Candidate("A", [], ev=improved, commit=commit)
    winner, decisions = select_round([candidate], base, 0, 0, RRSIConfig(), {})
    assert winner is candidate and decisions[0].admissible
    gitops.fast_forward(repo, "evolve/test", commit)
    assert gitops.git(repo, "show", "evolve/test:harness.py").stdout == "x = 1\n"
    gitops.worktree_remove(repo, first, "test/first")
    gitops.worktree_remove(repo, second, "test/second")
