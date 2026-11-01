"""One RRSI round over Mini50, reusing the verified frozen baseline evidence."""
import argparse
import fcntl
import hashlib
import json
import logging
import shutil
from pathlib import Path

from .cli import make_run
from .deepseek import bind_search_client
from .domain import MiniSWEDomain
from .mini50 import StreamingDomain
from .settings import ROOT, load_settings, write_json
from .worker import image_name


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def job_progress(cfg, runs, job, status):
    tasks = []
    for iid in cfg['evolve_ids']:
        trial = Path(runs) / 'jobs' / job / iid / 'trial-0'
        worker = read(trial / 'worker.json') if (trial / 'worker.json').exists() else {}
        grade = read(trial / 'grade.json') if (trial / 'grade.json').exists() else {}
        tasks.append({'instance_id': iid, 'completed': bool(grade.get('completed')),
                      'resolved': bool(grade.get('resolved')),
                      'infrastructure_failure': bool(grade.get('infrastructure_failure')),
                      'exit_status': worker.get('exit_status'), 'usage': worker.get('usage', {}),
                      'budget_stop': worker.get('budget_stop')})
    data = {'job': job, 'status': status, 'n_total': len(tasks),
            'n_completed': sum(t['completed'] for t in tasks),
            'n_resolved': sum(t['resolved'] for t in tasks),
            'n_infrastructure_failures': sum(t['infrastructure_failure'] for t in tasks),
            'api_calls': sum(t['usage'].get('calls', 0) for t in tasks),
            'actual_tokens': sum(t['usage'].get('actual_tokens', 0) for t in tasks), 'tasks': tasks}
    write_json(Path(cfg['workspace']) / f'progress-{job}.json', data)
    return data


def import_baseline(cfg, run):
    """Copy immutable evidence with explicit provenance; never relabel it as a new run."""
    source = (ROOT / cfg['baseline_workspace']).resolve()
    manifest = read(source / 'repo/source_manifest.json')
    oldcfg = read(ROOT / cfg['baseline_config'])
    for key in ('evolve_ids', 'heldout_ids', 'thinking', 'target', 'grading_seconds', 'dataset'):
        if key != 'dataset' and oldcfg[key] != cfg[key]:
            raise ValueError(f'baseline execution configuration mismatch: {key}')
    if sha(cfg['dataset']) != manifest['dataset_sha256']:
        raise ValueError('baseline dataset changed')
    if (cfg['model'], cfg['api_base']) != (manifest['model'], manifest['api_base']):
        raise ValueError('baseline model/endpoint changed')
    # Existing adapter modules must match; this new orchestration module is recorded separately.
    for name, digest in manifest['runner_sha256'].items():
        if sha(ROOT / 'acl_rsi' / name) != digest:
            raise ValueError(f'baseline adapter changed: {name}')
    if read(run.repo / 'source_manifest.json')['source_sha256'] != manifest['source_sha256']:
        raise ValueError('baseline harness source changed')
    provenance_file = Path(cfg['workspace']) / 'baseline_provenance.json'
    evidence = {}
    for iid in cfg['evolve_ids']:
        src = source / 'runs/swe/jobs/base' / iid / 'trial-0'
        grade, worker = read(src / 'grade.json'), read(src / 'worker.json')
        if not grade.get('completed') or grade.get('infrastructure_failure'):
            raise ValueError(f'incomplete baseline: {iid}')
        if sha(src / 'patch.diff') != grade['patch_sha256']:
            raise ValueError(f'baseline patch hash mismatch: {iid}')
        if read(src / 'manifest.json')['harness_sha256'] != run.domain.tree_digest(run.domain.harness_dir(run.repo)):
            raise ValueError(f'baseline harness mismatch: {iid}')
        evidence[iid] = {name: sha(src / name) for name in
                         ('manifest.json', 'worker.json', 'grade.json', 'trajectory.json', 'usage.json', 'patch.diff')}
        dst = run.jobs / 'base' / iid / 'trial-0'
        if not dst.exists():
            shutil.copytree(src, dst)
        for name, digest in evidence[iid].items():
            if sha(dst / name) != digest:
                raise ValueError(f'imported baseline evidence changed: {iid}/{name}')
    provenance = {'source_workspace': str(source), 'source_config_sha256': manifest['config_sha256'],
                  'reuse_only': True, 'new_baseline_api_calls': 0, 'evidence_sha256': evidence}
    if provenance_file.exists() and read(provenance_file) != provenance:
        raise ValueError('baseline provenance changed')
    write_json(provenance_file, provenance)


class CandidateDomain(MiniSWEDomain):
    """Serial evaluation with ownership-limited image cleanup and no paid retry."""
    def run(self, root, runs_dir, job, ids, k, log_prefix=''):
        if k != 1:
            raise ValueError('single trial only')
        if job == 'base':
            for iid in ids:
                trial = self.trial_dir(runs_dir, job, iid, 0)
                if not (trial / 'worker.json').exists() or not (trial / 'grade.json').exists():
                    raise ValueError('baseline must be imported before evaluation')
            job_progress(self.cfg, runs_dir, job, 'reused')
            return
        if job != 'r0A':
            raise ValueError('one round and one candidate only')
        import docker
        workspace = Path(self.cfg['workspace'])
        client = docker.from_env(timeout=600)
        inventory = workspace / 'image_inventory.json'
        if not inventory.exists():
            write_json(inventory, {'preexisting_ids': [im.id for im in client.images.list()]})
        protected = set(read(inventory)['preexisting_ids'])
        cache = workspace / 'owned_images.json'
        owned = read(cache) if cache.exists() else {}
        anchors = {}
        state = 'interrupted'
        try:
            for number, iid in enumerate(ids, 1):
                trial = self.trial_dir(runs_dir, job, iid, 0)
                if (trial / 'worker.json').exists() and (trial / 'grade.json').exists():
                    # Preserve even failed attempts: no extra API spend on automatic retry.
                    job_progress(self.cfg, runs_dir, job, 'running')
                    continue
                if shutil.disk_usage(ROOT).free < self.cfg['image_cache']['min_free_bytes']:
                    raise RuntimeError('disk_space_guard: below minimum')
                name = image_name(iid)
                print(f'[mini50-rsi] {number}/{len(ids)} {iid}: checking image', flush=True)
                try:
                    image = client.images.get(name)
                except docker.errors.ImageNotFound:
                    print(f'[mini50-rsi] pulling {name}', flush=True)
                    image = client.images.pull(name, platform='linux/amd64')
                    if image.id not in protected:
                        owned[name] = image.id
                        write_json(cache, owned)
                if shutil.disk_usage(ROOT).free < self.cfg['image_cache']['min_free_bytes']:
                    raise RuntimeError('disk_space_guard: below minimum after pull')
                write_json(workspace / 'images' / f'{iid}.json', {
                    'instance_id': iid, 'image': name, 'id': image.id,
                    'repo_digests': image.attrs.get('RepoDigests', []), 'size_bytes': image.attrs['Size']})
                family = self.instances[iid]['repo']
                if name in owned and family not in anchors:
                    anchors[family] = name
                super().run(root, runs_dir, job, [iid], k, log_prefix)
                data = job_progress(self.cfg, runs_dir, job, 'running')
                print(f"[mini50-rsi] completed={data['n_completed']}/50 resolved={data['n_resolved']} calls={data['api_calls']}", flush=True)
                if name in owned and name not in anchors.values():
                    StreamingDomain.release(client, name, owned, protected, cache)
            state = 'completed'
        finally:
            for name in list(owned):
                StreamingDomain.release(client, name, owned, protected, cache)
            job_progress(self.cfg, runs_dir, job, state)
            present = {im.id for im in client.images.list()}
            write_json(workspace / 'cleanup_validation.json', {
                'preexisting_image_ids': len(protected),
                'preexisting_image_ids_still_present': len(protected & present),
                'missing_preexisting_ids': sorted(protected - present),
                'owned_image_tags_remaining': owned})
            client.close()


def main():
    logging.getLogger('httpx').setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'configs/mini50-round1.json'))
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    cfg = load_settings(args.config)
    if len(cfg['evolve_ids']) != 50 or any(cfg['rrsi'][key] != 1 for key in ('T', 'k', 'm')):
        raise ValueError('expected all 50 tasks, one round, one candidate, one trial')
    workspace = Path(cfg['workspace']); workspace.mkdir(parents=True, exist_ok=True)
    with (workspace / 'controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = make_run(cfg)
        domain = CandidateDomain(cfg); domain.root = run.domain.root; run.domain = domain
        import_baseline(cfg, run)
        ok, details = domain.smoke(run.repo, run.runs, 'baseline_smoke', [])
        if not ok:
            raise RuntimeError(f'baseline smoke failed: {details}')
        if not run.frontier_path.exists():
            run.baseline()
        if args.prepare_only:
            print(json.dumps({'prepared': cfg['workspace'], 'baseline': run.frontier()['incumbent']['S'], 'new_api_calls': 0}))
            return
        ledger = bind_search_client(cfg, workspace / 'search_usage.json')
        try:
            write_json(workspace / 'controller.json', {'status': 'running', 'scope': 'one RSI round, all50 candidate evaluation'})
            if len(run.frontier()['trajectory']) < 2:
                run.round(0)
            candidate = job_progress(cfg, run.runs, 'r0A', 'completed')
            complete = candidate['n_completed'] == 50 and candidate['n_infrastructure_failures'] == 0
            status = 'completed' if complete else 'round_finished_without_valid_candidate'
            summary = {'status': status, 'purpose': cfg['purpose'], 'frontier': run.frontier(),
                       'baseline_reused': True, 'baseline_score': .62,
                       'candidate': candidate, 'search_usage': ledger.summary(),
                       'config_sha256': cfg['config_sha256']}
            write_json(workspace / 'summary.json', summary)
            write_json(workspace / 'controller.json', {'status': status})
            print(json.dumps({key: value for key, value in summary.items() if key not in ('frontier', 'candidate')}, indent=2))
        except BaseException as exc:
            write_json(workspace / 'failure.json', {'status': 'interrupted', 'error_type': type(exc).__name__, 'search_usage': ledger.summary()})
            write_json(workspace / 'controller.json', {'status': 'interrupted', 'error_type': type(exc).__name__})
            raise


if __name__ == '__main__':
    main()
