import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from acl_rsi.deepseek import UsageLedger
from acl_rsi.grading import grade
from acl_rsi.mini50 import StreamingDomain
from acl_rsi.settings import ROOT, public_instance, write_json
from acl_rsi.worker import image_name
from acl_terminal_rsi.common import read, sha
from .common import BASE
from .feedback import EvaluationUnavailable, record


class SWEExecutor:
    def __init__(self, cfg, work, instances):
        self.cfg, self.work, self.instances = cfg, Path(work), instances

    def inventory(self, client):
        path = self.work / 'image_inventory.json'
        if not path.exists():
            write_json(path, {'preexisting_ids': sorted(i.id for i in client.images.list()),
                             'created_at': time.time()})
        return set(read(path)['preexisting_ids'])

    def retain_images(self):
        # Storage-only user override; model, harness, trials and budgets stay frozen.
        path = self.work / 'storage-policy.json'
        return path.exists() and read(path).get('retain_mini_images') is True

    def release(self, client, name, owned, protected, cache):
        if not self.retain_images():
            StreamingDomain.release(client, name, owned, protected, cache)

    def image(self, client, iid, protected, owned):
        import docker
        free = shutil.disk_usage(ROOT).free
        if free < self.cfg['image_cache']['min_free_bytes']:
            raise EvaluationUnavailable('disk_space_below_4GiB')
        name = image_name(iid)
        try:
            image = client.images.get(name)
        except docker.errors.ImageNotFound:
            print(f'[gepa-swe] pulling {iid}', flush=True)
            image = client.images.pull(name, platform='linux/amd64')
            if image.id not in protected:
                owned[name] = image.id
                write_json(self.work / 'owned_images.json', owned)
        expected = read(BASE / 'images' / f'{iid}.json')
        if image.id != expected['id']:
            raise EvaluationUnavailable('image_identity_differs_from_baseline')
        write_json(self.work / 'images' / f'{iid}.json', {'image': name, 'id': image.id,
                   'repo_digests': image.attrs.get('RepoDigests', []),
                   'size_bytes': image.attrs['Size'], 'host_free_bytes_before': free})
        if shutil.disk_usage(ROOT).free < self.cfg['image_cache']['min_free_bytes']:
            raise EvaluationUnavailable('disk_space_below_4GiB_after_pull')
        return image

    def preflight(self):
        import docker
        client = docker.from_env(timeout=600)
        cache = self.work / 'owned_images.json'
        owned = read(cache) if cache.exists() else {}
        try:
            client.ping()
            protected = self.inventory(client)
            iid = self.cfg['evolve_ids'][0]
            image = self.image(client, iid, protected, owned)
            result = subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                '--network', 'none', '--cpus', '2', '--memory', '6g', '--entrypoint', 'bash',
                image_name(iid), '-c', 'test -d /testbed && python --version'],
                capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise EvaluationUnavailable('first_task_container_preflight_failed')
            status = {'status': 'ready_first_image_only', 'instance_id': iid, 'image_id': image.id,
                      'protected_images': len(protected), 'free_bytes': shutil.disk_usage(ROOT).free,
                      'new_model_calls': 0, 'other_49_images_not_yet_checked': True}
            write_json(self.work / 'preflight.json', status)
            return status
        finally:
            for name in list(owned):
                self.release(client, name, owned, self.inventory(client), cache)
            client.close()

    def trial(self, iid, folder):
        trial = folder / 'trials' / iid
        manifest = {'instance_id': iid, 'base_commit': self.instances[iid]['base_commit'],
                    'config_sha256': self.cfg['config_sha256'], 'trial': 0,
                    'harness_files': {n: sha(folder / 'harness' / n) for n in
                                      ('agent.py', 'swebench.yaml', 'LICENSE.md')}}
        path = trial / 'manifest.json'
        if path.exists() and read(path) != manifest:
            raise EvaluationUnavailable('trial_provenance_changed')
        started = (trial / 'worker-attempt.json').exists()
        trial.mkdir(parents=True, exist_ok=True)
        write_json(path, manifest)
        write_json(trial / 'public_instance.json', public_instance(self.instances[iid]))
        worker_path = trial / 'worker.json'
        fresh = 0
        if not worker_path.exists():
            if started or (trial / 'usage.json').exists():
                raise EvaluationUnavailable('incomplete_worker_no_automatic_paid_retry')
            write_json(trial / 'worker-attempt.json', {'started_at': time.time(), 'automatic_paid_retry': False})
            env = dict(os.environ, PYTHONPATH=str(ROOT), LITELLM_LOCAL_MODEL_COST_MAP='True', PYTHONDONTWRITEBYTECODE='1')
            with (trial / 'worker.log').open('a') as log:
                proc = subprocess.Popen([sys.executable, '-m', 'acl_gepa_swe.worker',
                    '--config', self.cfg['config_path'], '--harness', str(folder / 'harness'),
                    '--instance', str(trial / 'public_instance.json'), '--output', str(trial)],
                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = proc.wait(timeout=self.cfg['target']['wall_seconds'] + 180)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    container = trial / 'container.json'
                    if container.exists():
                        subprocess.run(['docker', 'rm', '-f', read(container)['id']], capture_output=True, timeout=60)
                    usage = UsageLedger(trial / 'usage.json', self.cfg['target']['max_calls'],
                                        self.cfg['target']['max_tokens']).summary()
                    (trial / 'patch.diff').write_text('')
                    write_json(worker_path, {'instance_id': iid, 'exit_status': 'WorkerTimeout',
                                            'usage': usage, 'budget_stop': {'reason': 'wall_limit'}})
                    code = 0
            if code != 0 or not worker_path.exists():
                raise EvaluationUnavailable('worker_process_failed_no_automatic_paid_retry')
            fresh = 1
        worker = read(worker_path)
        if worker.get('exit_status') in ('DockerException', 'CalledProcessError', 'FileNotFoundError', 'ProviderError'):
            raise EvaluationUnavailable('worker_infrastructure_or_provider_error')
        grade_path = trial / 'grade.json'
        # A durable patch may be regraded once after a grader-only infrastructure
        # failure. The expensive worker and all its API calls remain untouched.
        for attempt in range(2):
            graded = grade(self.instances[iid], (trial / 'patch.diff').read_text(), trial, self.cfg['grading_seconds'])
            if not graded.get('infrastructure_failure'):
                break
            backup = trial / 'grader-infrastructure-attempt-0'
            if attempt or backup.exists():
                raise EvaluationUnavailable('grader_infrastructure_failure_after_recovery')
            backup.mkdir()
            shutil.move(str(grade_path), backup / 'grade.json')
            if (trial / 'official').exists():
                shutil.move(str(trial / 'official'), backup / 'official')
        record(trial, iid, self.instances[iid], trace=False)
        return fresh

    def evaluate(self, ids, folder):
        import docker
        client = docker.from_env(timeout=600)
        cache = self.work / 'owned_images.json'
        protected = self.inventory(client)
        owned = read(cache) if cache.exists() else {}
        anchors, fresh = {}, 0
        try:
            for iid in ids:
                trial = folder / 'trials' / iid
                if (trial / 'worker.json').exists() and (trial / 'grade.json').exists():
                    try:
                        record(trial, iid, self.instances[iid], trace=False)
                        continue
                    except EvaluationUnavailable:
                        pass  # Only the grader may be recovered; worker never reruns.
                self.image(client, iid, protected, owned)
                name, family = image_name(iid), self.instances[iid]['repo']
                if name in owned and family not in anchors:
                    anchors[family] = name
                print(f'[gepa-swe] evaluating {iid}', flush=True)
                fresh += self.trial(iid, folder)
                from .run import summarize
                report = summarize(self.cfg, self.work, self.instances)
                print(f"[gepa-swe] valid={report['n_valid']}/{report['total']} resolved_so_far={report['resolved_so_far']} calls={report['target_usage']['calls']}", flush=True)
                if name in owned and name not in anchors.values():
                    self.release(client, name, owned, protected, cache)
            return fresh
        finally:
            for name in list(owned):
                self.release(client, name, owned, protected, cache)
            current = {i.id for i in client.images.list()}
            cleanup = ROOT / 'work/docker-audit/cleanup-20261018/result.json'
            approved = set(read(cleanup).get('deleted_image_ids', [])) if cleanup.exists() else set()
            write_json(self.work / 'cleanup_validation.json', {'missing_preexisting_ids': sorted(protected - current),
                       'user_approved_deleted_ids': sorted((protected - current) & approved),
                       'unexpected_missing_preexisting_ids': sorted(protected - current - approved),
                       'retain_mini_images': self.retain_images(),
                       'owned_images_retained': owned, 'free_bytes': shutil.disk_usage(ROOT).free})
            client.close()
