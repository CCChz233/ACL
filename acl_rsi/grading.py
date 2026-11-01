"""Independent SWE-bench 4.1 grading in a fresh official task container."""
import hashlib
from pathlib import Path

from .settings import write_json

NO_FIX_PATCH = """diff --git a/.rrsi_no_fix b/.rrsi_no_fix
new file mode 100644
--- /dev/null
+++ b/.rrsi_no_fix
@@ -0,0 +1 @@
+No implementation changes.
"""


def grade(instance: dict, patch: str, directory: Path, timeout: int) -> dict:
    import docker
    from swebench.harness import run_evaluation as evaluator
    from swebench.harness.constants import APPLY_PATCH_FAIL
    from swebench.harness.test_spec.test_spec import make_test_spec

    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(patch.encode()).hexdigest()
    previous = directory / "grade.json"
    if previous.exists():
        saved = __import__("json").loads(previous.read_text())
        if saved.get("patch_sha256") != fingerprint:
            raise ValueError("grade cache belongs to a different patch; use a new trial directory")
        return saved
    result = {"instance_id": instance["instance_id"], "patch_sha256": fingerprint,
              "resolved": False, "completed": False, "infrastructure_failure": False}
    if not patch.strip():
        result.update(completed=True, reason="empty_submission")
    else:
        spec = make_test_spec(instance, namespace="swebench", arch="x86_64")
        evaluator.RUN_EVALUATION_LOG_DIR = directory / "official"
        client = docker.from_env(timeout=600)
        try:
            client.ping()
            # Never start an expensive image build accidentally during an engineering check.
            client.images.get(spec.instance_image_key)
            answer = evaluator.run_instance(
                spec, {"instance_id": instance["instance_id"], "model_name_or_path": "deepseek-flash",
                       "model_patch": patch}, False, False, client,
                "acl-" + hashlib.sha256(str(directory).encode()).hexdigest()[:12], timeout=timeout,
            )
            result.update(answer or {})
            log = next((directory / "official").rglob("run_instance.log"), None)
            report = next((directory / "official").rglob("report.json"), None)
            result["report_path"] = str(report) if report else None
            if not result["completed"]:
                text = log.read_text(errors="replace") if log else ""
                invalid_patch = APPLY_PATCH_FAIL in text
                timed_out = "Test timed out" in text
                result["infrastructure_failure"] = not (invalid_patch or timed_out)
                result["reason"] = "invalid_patch" if invalid_patch else ("grading_timeout" if timed_out else "grading_incomplete")
        except (docker.errors.DockerException, OSError) as exc:
            result.update(infrastructure_failure=True, reason=type(exc).__name__)
        finally:
            client.close()
    write_json(previous, result)
    return result
