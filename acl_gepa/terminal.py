"""Same frozen mini agent and Harbor task limits, with audited scoring outside it."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import uuid

from acl_rsi.settings import ROOT, write_json
from .common import BASE_WORK, read
from .feedback import EvaluationUnavailable, grade


def docker(*args, check=True, timeout=120):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check, timeout=timeout)


class TerminalExecutor:
    def __init__(self, cfg, base, work):
        self.cfg, self.base, self.work = cfg, base, Path(work)
        self.tasks = {t['id']: t for t in base['tasks']}

    def expected_image(self, task_id):
        return read(BASE_WORK / 'image-pulls' / f'baseline-{task_id}.json')['Id']

    def protected_images(self):
        path = self.work / 'preexisting-images.json'
        if not path.exists():
            write_json(path, sorted(set(docker('image', 'ls', '-q', '--no-trunc').stdout.split())))
        return set(read(path))

    def ensure_image(self, task_id, pull=True):
        task = self.tasks[task_id]
        if shutil.disk_usage(ROOT).free < self.base['min_free_bytes']:
            raise EvaluationUnavailable('disk_below_4_gib')
        result = docker('image', 'inspect', task['image'], check=False, timeout=15)
        if result.returncode and pull:
            result = docker('pull', '--platform', 'linux/amd64', task['image'], check=False, timeout=60)
            directory = self.work / 'image-pulls'
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f'{task_id}.log').write_text(result.stdout + result.stderr)
            if result.returncode:
                raise EvaluationUnavailable('image_pull_failed')
            result = docker('image', 'inspect', task['image'], check=False, timeout=15)
        if result.returncode:
            raise EvaluationUnavailable('image_not_available')
        image = json.loads(result.stdout)[0]
        if image['Id'] != self.expected_image(task_id) or image['Architecture'] != 'amd64':
            raise EvaluationUnavailable('image_differs_from_frozen_baseline')
        if shutil.disk_usage(ROOT).free < self.base['min_free_bytes']:
            raise EvaluationUnavailable('disk_below_4_gib_after_image_pull')
        return image

    def preflight(self, pull_first=False):
        result = {'status': 'ready_for_first_image_only', 'model_api_calls': 0,
                  'task_count': len(self.tasks), 'full_network_readiness_verified': False}
        try:
            docker('info', '--format', '{{.OSType}}', timeout=15)
            self.protected_images()  # Before any preflight download, not after it.
            task_id = self.cfg['task_ids'][0]
            image = self.ensure_image(task_id, pull=pull_first)
            result['first_image_id'] = image['Id']
        except (EvaluationUnavailable, subprocess.SubprocessError, OSError) as exc:
            result.update(status='blocked_before_model_call', reason=str(exc) if isinstance(exc, EvaluationUnavailable) else type(exc).__name__)
        write_json(self.work / 'preflight.json', result)
        return result

    def __call__(self, task_id, harness_data, folder):
        asyncio.run(self.run_trial(task_id, harness_data, Path(folder)))

    async def run_trial(self, task_id, harness_data, folder):
        # Imported only for a real target trial, never for prepare or offline smoke.
        from harbor.models.trial.config import TrialConfig
        from harbor.trial.hooks import TrialEvent
        from harbor.trial.trial import Trial

        trial_path = folder / 'trials' / task_id
        if trial_path.exists():
            raise EvaluationUnavailable('existing_trial_no_automatic_paid_retry')
        before = self.protected_images()
        image = self.ensure_image(task_id)
        execution = {**self.base, **harness_data, 'workspace': str(folder)}
        execution_path = folder / 'execution-config.json'
        if execution_path.exists() and read(execution_path) != execution:
            raise ValueError('Candidate execution config changed')
        write_json(execution_path, execution)
        overlay = folder / 'platform.yaml'
        overlay.write_text('services:\n  main:\n    platform: linux/amd64\n')
        wall = self.tasks[task_id]['wall_seconds']
        config = TrialConfig.model_validate({
            'task': {'path': str(ROOT / 'repos/terminal-bench-2-1/tasks' / task_id)},
            'trials_dir': str(trial_path.parent), 'trial_name': task_id,
            'agent': {'import_path': 'acl_terminal.agent:PilotAgent', 'model_name': self.cfg['model'],
                      'override_timeout_sec': wall + 180,
                      'kwargs': {'pilot_config': str(execution_path), 'wall_seconds': wall}},
            'environment': {'type': 'docker', 'delete': True, 'extra_docker_compose': [str(overlay)]},
            'verifier': {'override_timeout_sec': 900}})
        snapshot = {}
        trial = None

        async def checkpoint(_event):
            # Capture filesystem before grader setup can alter it. RAM/processes and
            # volume contents are not in docker commit; do not claim exact state replay.
            env = trial.agent_environment
            result = await env._run_docker_compose_command(['ps', '-q', 'main'])
            cid = result.stdout.strip()
            if not cid or len(cid.split()) != 1:
                raise EvaluationUnavailable('cannot_identify_checkpoint_container')
            tag = 'acl-gepa-checkpoint:' + uuid.uuid4().hex
            committed = await asyncio.to_thread(docker, 'commit', cid, tag)
            snapshot.update(image_id=committed.stdout.strip(), tag=tag,
                            kind='filesystem_image_only', excludes=['RAM', 'running_process_state', 'mounted_volume_contents'])
            write_json(trial_path / 'agent/filesystem-checkpoint.json', snapshot)

        valid = False
        try:
            trial = await Trial.create(config)
            trial.add_hook(TrialEvent.AGENT_END, checkpoint)
            await trial.run()
            grade(trial_path, BASE_WORK / 'trials' / task_id)
            worker = read(trial_path / 'agent/worker.json')
            if worker.get('exit_status') in ('ProviderError', 'RuntimeError'):
                raise EvaluationUnavailable('worker_infrastructure_error')
            valid = True
        finally:
            # Keep at most the first invalid task's filesystem image for inspection;
            # the adapter then aborts the batch. No running task container is retained.
            if snapshot:
                if valid:
                    docker('image', 'rm', snapshot['tag'], check=False)
                write_json(trial_path / 'agent/checkpoint-retention.json', {
                    **snapshot, 'retained_for_invalid_trial': not valid})
            if image['Id'] not in before:
                docker('image', 'rm', self.tasks[task_id]['image'], check=False)
            after = set(docker('image', 'ls', '-q', '--no-trunc').stdout.split())
            write_json(folder / 'resource-audit.json', {'missing_preexisting_image_ids': sorted(before - after),
                       'retained_checkpoint': snapshot if snapshot and not valid else None})
