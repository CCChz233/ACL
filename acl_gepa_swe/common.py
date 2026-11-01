import copy
import importlib.metadata
import json
from pathlib import Path
import shutil

import yaml

from acl_gepa.common import candidate_id, import_gepa
from acl_rsi.settings import ROOT, load_instances, load_settings, write_json
from acl_terminal_rsi.common import read, sha, validate_harness

BASE = ROOT / 'work/verified-mini-50-baseline-v2'
HARNESS = BASE / 'repo/domains/swe/harness'
CONFIG = ROOT / 'configs/gepa-mini50-v1.json'
EDITABLE = {'agent': ('system_template', 'instance_template'),
            'model': ('observation_template', 'format_error_template')}


def seed_candidate():
    return {'swebench.yaml': (HARNESS / 'swebench.yaml').read_text()}


def validate(candidate, folder, task_ids):
    if set(candidate) != {'swebench.yaml'} or not isinstance(candidate['swebench.yaml'], str):
        raise ValueError('Only swebench.yaml can be proposed')
    text = candidate['swebench.yaml']
    if len(text) > 32000:
        raise ValueError('Oversized harness')
    data = yaml.safe_load(text)
    original = yaml.safe_load(seed_candidate()['swebench.yaml'])
    if not isinstance(data, dict):
        raise ValueError('Expected YAML mapping')
    frozen = copy.deepcopy(data)
    for section, keys in EDITABLE.items():
        for key in keys:
            if key not in data.get(section, {}):
                raise ValueError('Missing prompt component')
            frozen[section][key] = original[section][key]
    if frozen != original:
        raise ValueError('Only four prompt templates may change; all execution settings are frozen')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    reduced = {'agent': {k: data['agent'][k] for k in EDITABLE['agent']},
               'templates': {k: data['model'][k] for k in EDITABLE['model']}}
    check = folder / 'template-validation.yaml'
    check.write_text(yaml.safe_dump(reduced, sort_keys=False))
    validate_harness(check, task_ids)
    check.unlink()
    if 'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt' not in data['agent']['instance_template']:
        raise ValueError('Preserve exact submission command')
    forbidden = ('DEEPSEEK_API_KEY', 'dotenv', 'os.environ', 'api.deepseek',
                 'test_patch', 'FAIL_TO_PASS', 'PASS_TO_PASS', 'benchmarks/datasets',
                 'acl_rsi', 'runs/swe', '/logs/verifier', 'reward.txt')
    if any(s in text for s in forbidden):
        raise ValueError('Private evaluation/runtime access in candidate')
    for name in ('agent.py', 'LICENSE.md'):
        source = HARNESS / name
        destination = folder / name
        if destination.exists() and sha(destination) != sha(source):
            raise ValueError('Frozen agent source changed')
        if not destination.exists():
            shutil.copy2(source, destination)
    destination = folder / 'swebench.yaml'
    if destination.exists() and destination.read_text() != text:
        raise ValueError('Candidate artifact changed')
    destination.write_text(text)
    return data


def baseline_trial(iid):
    return BASE / 'runs/swe/jobs/base' / iid / 'trial-0'


def prepare():
    cfg = load_settings(CONFIG)
    original = load_settings(ROOT / 'configs/mini50-baseline.json')
    manifest = read(BASE / 'repo/source_manifest.json')
    for key in ('evolve_ids', 'heldout_ids', 'target', 'grading_seconds', 'thinking'):
        if cfg[key] != original[key]:
            raise ValueError(f'Protocol mismatch: {key}')
    for key in ('model', 'api_base', 'thinking'):
        if cfg[key] != manifest[key]:
            raise ValueError(f'Provider mismatch: {key}')
    if sha(cfg['dataset']) != manifest['dataset_sha256']:
        raise ValueError('Dataset changed')
    if sha(ROOT / 'configs/mini50-baseline.json') != manifest['config_sha256']:
        raise ValueError('Baseline config changed')
    for name, digest in manifest['runner_sha256'].items():
        if sha(ROOT / 'acl_rsi' / name) != digest:
            raise ValueError(f'Frozen SWE runtime changed: {name}')
    for name, digest in manifest['source_sha256'].items():
        if sha(HARNESS / name) != digest:
            raise ValueError('Frozen baseline harness changed')
    _, revision = import_gepa()
    instances = load_instances(cfg)
    evidence = {}
    from .feedback import record
    for iid in cfg['evolve_ids']:
        trial = baseline_trial(iid)
        record(trial, iid, instances[iid], trace=False)
        trial_manifest = read(trial / 'manifest.json')
        if (trial_manifest['config_sha256'] != manifest['config_sha256'] or
                trial_manifest['base_commit'] != instances[iid]['base_commit']):
            raise ValueError('Baseline trial provenance mismatch')
        paths = [trial / n for n in ('manifest.json', 'worker.json', 'grade.json',
                  'trajectory.json', 'usage.json', 'patch.diff')]
        paths.append(BASE / 'images' / f'{iid}.json')
        grade = read(trial / 'grade.json')
        if grade.get('report_path'):
            paths.append(Path(grade['report_path']))
        evidence[iid] = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    work = Path(cfg['workspace'])
    work.mkdir(parents=True, exist_ok=True)
    lock = {'config_sha256': sha(CONFIG), 'baseline_manifest_sha256': sha(BASE / 'repo/source_manifest.json'),
            'gepa_revision': revision, 'baseline_evidence': evidence,
            'runtime': {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'acl_gepa_swe').glob('*.py'))},
            'shared_runtime': {str(ROOT.joinpath(p).relative_to(ROOT)): sha(ROOT / p) for p in
                  ('acl_gepa/common.py', 'acl_gepa/reflection.py', 'acl_terminal_rsi/common.py')},
            'packages': {p: importlib.metadata.version(p) for p in
                         ('mini-swe-agent', 'swebench', 'openai', 'docker')},
            'seed_id': candidate_id(seed_candidate())}
    path = work / 'runtime-lock.json'
    if path.exists() and read(path) != lock:
        raise ValueError('Frozen GEPA SWE runtime changed; use a new versioned workspace')
    validate(seed_candidate(), work / 'seed', cfg['evolve_ids'])
    write_json(path, lock)
    return cfg, work, instances
