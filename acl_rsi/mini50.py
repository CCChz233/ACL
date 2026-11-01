"""Run all Verified Mini baseline tasks with a bounded, owned-image cache."""
import argparse
import json
import logging
import shutil
from pathlib import Path

from .cli import make_run
from .domain import MiniSWEDomain
from .settings import ROOT, load_settings, write_json
from .worker import image_name


def progress(cfg, runs, status):
    tasks = []
    for iid in cfg["evolve_ids"]:
        trial = Path(runs) / "jobs" / "base" / iid / "trial-0"
        worker = json.loads((trial / "worker.json").read_text()) if (trial / "worker.json").exists() else {}
        grade = json.loads((trial / "grade.json").read_text()) if (trial / "grade.json").exists() else {}
        tasks.append({"instance_id": iid, "completed": bool(grade.get("completed")),
                      "resolved": bool(grade.get("resolved")),
                      "infrastructure_failure": bool(grade.get("infrastructure_failure")),
                      "exit_status": worker.get("exit_status"), "usage": worker.get("usage", {})})
    data = {"status": status, "n_total": len(tasks),
            "n_completed": sum(t["completed"] for t in tasks),
            "n_resolved": sum(t["resolved"] for t in tasks),
            "n_infrastructure_failures": sum(t["infrastructure_failure"] for t in tasks),
            "api_calls": sum(t["usage"].get("calls", 0) for t in tasks),
            "actual_tokens": sum(t["usage"].get("actual_tokens", 0) for t in tasks),
            "tasks": tasks}
    write_json(Path(cfg["workspace"]) / "progress.json", data)
    return data


class StreamingDomain(MiniSWEDomain):
    def run(self, root, runs_dir, job, ids, k, log_prefix=""):
        import docker
        if job != "base" or k != 1:
            raise ValueError("mini50 is a baseline-only, single-trial runner")
        workspace = Path(self.cfg["workspace"])
        client = docker.from_env(timeout=600)
        inventory = workspace / "image_inventory.json"
        if not inventory.exists():
            write_json(inventory, {"preexisting_ids": [image.id for image in client.images.list()]})
        protected = set(json.loads(inventory.read_text())["preexisting_ids"])
        cache_file = workspace / "owned_images.json"
        owned = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        anchors = {}
        try:
            for number, iid in enumerate(ids, 1):
                trial = self.trial_dir(runs_dir, job, iid, 0)
                if (trial / "worker.json").exists() and (trial / "grade.json").exists():
                    # Completed/failed evidence is immutable: no automatic paid reruns.
                    progress(self.cfg, runs_dir, "running")
                    continue
                free = shutil.disk_usage(ROOT).free
                if free < self.cfg["image_cache"]["min_free_bytes"]:
                    raise RuntimeError("disk_space_guard: free space below batch minimum")
                name = image_name(iid)
                print(f"[mini50] {number}/{len(ids)} {iid}: checking image", flush=True)
                try:
                    image = client.images.get(name)
                except docker.errors.ImageNotFound:
                    print(f"[mini50] pulling {name}", flush=True)
                    image = client.images.pull(name, platform="linux/amd64")
                    if image.id not in protected:
                        owned[name] = image.id
                        write_json(cache_file, owned)
                if shutil.disk_usage(ROOT).free < self.cfg["image_cache"]["min_free_bytes"]:
                    raise RuntimeError("disk_space_guard: free space below minimum after image pull")
                metadata = {"instance_id": iid, "image": name, "id": image.id,
                            "repo_digests": image.attrs.get("RepoDigests", []),
                            "size_bytes": image.attrs["Size"], "host_free_bytes_before": free}
                write_json(workspace / "images" / f"{iid}.json", metadata)
                family = self.instances[iid]["repo"]
                if name in owned and family not in anchors:
                    anchors[family] = name  # Keep one shared-layer anchor per repository.
                super().run(root, runs_dir, job, [iid], k, log_prefix)
                data = progress(self.cfg, runs_dir, "running")
                print(f"[mini50] completed={data['n_completed']}/{data['n_total']} resolved={data['n_resolved']} calls={data['api_calls']}", flush=True)
                if name in owned and name not in anchors.values():
                    self.release(client, name, owned, protected, cache_file)
        finally:
            # Never prune unrelated resources, force removal, or remove preexisting images.
            for name in list(owned):
                self.release(client, name, owned, protected, cache_file)
            client.close()

    @staticmethod
    def release(client, name, owned, protected, cache_file):
        import docker
        try:
            image = client.images.get(name)
            if image.id != owned[name] or image.id in protected:
                return
            client.images.remove(name, force=False, noprune=True)
            del owned[name]
            write_json(cache_file, owned)
        except docker.errors.ImageNotFound:
            owned.pop(name, None)
            write_json(cache_file, owned)
        except docker.errors.APIError:
            # A live container or another tag can keep an image; leave it untouched.
            print(f"[mini50] retained in-use image {name}", flush=True)


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs/mini50-baseline.json"))
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    cfg = load_settings(args.config)
    if len(cfg["evolve_ids"]) != 50 or cfg["rrsi"]["k"] != 1 or cfg["rrsi"]["T"] != 0:
        raise ValueError("expected exactly 50 baseline tasks and no search rounds")
    run = make_run(cfg)
    if set(run.domain.instances) != set(cfg["evolve_ids"]):
        raise ValueError("task list must cover the whole locked Mini dataset")
    domain = StreamingDomain(cfg)
    domain.root = run.domain.root
    run.domain = domain
    ok, details = domain.smoke(run.repo, run.runs, "baseline_smoke", [])
    if not ok:
        raise RuntimeError(f"baseline smoke failed: {details}")
    if args.prepare_only:
        print(json.dumps({"prepared": cfg["workspace"], "n_tasks": 50, "api_calls": 0}))
        return
    try:
        if not run.frontier_path.exists():
            run.baseline()
        data = progress(cfg, run.runs, "completed")
        write_json(Path(cfg["workspace"]) / "summary.json", {
            "purpose": cfg["purpose"], "frontier": run.frontier(), "progress": data,
            "search_calls": 0, "config_sha256": cfg["config_sha256"]})
        print(json.dumps({k: v for k, v in data.items() if k != "tasks"}, indent=2))
    except BaseException:
        progress(cfg, run.runs, "interrupted")
        raise


if __name__ == "__main__":
    main()
