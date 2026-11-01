import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml

from acl_rsi.settings import ROOT, write_json
from acl_terminal_rsi.common import BASE_CONFIG, BASE_WORK, harness_config, read, sha, validate_harness, verify_baseline

CONFIG = ROOT / 'configs/gepa-terminal-v1.json'


def import_gepa():
    path = ROOT / 'repos/gepa'
    lock = read(ROOT / 'docs/rsi_frameworks.sources.lock.json')
    source = next(x for x in lock['cloned_frameworks'] if x['name'] == 'GEPA')
    head = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if head != source['revision'] or subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no'], text=True):
        raise ValueError('Pinned GEPA source changed')
    sys.path.insert(0, str(path / 'src'))
    import gepa
    return gepa, head


def seed_candidate(base):
    return {'terminal.yaml': yaml.safe_dump(harness_config(base), sort_keys=False, allow_unicode=True)}


def candidate_id(candidate):
    return hashlib.sha256(json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_candidate(candidate, path, ids):
    if set(candidate) != {'terminal.yaml'} or not isinstance(candidate['terminal.yaml'], str):
        raise ValueError('Only terminal.yaml may be edited')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(candidate['terminal.yaml'])
    data = validate_harness(path, ids)
    if 'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' not in data['agent']['instance_template']:
        raise ValueError('Completion marker must remain in instance template')
    text = candidate['terminal.yaml']
    forbidden = ('DEEPSEEK_API_KEY', 'dotenv', 'os.environ', 'api.deepseek',
                 '/tests', '/solution', '/logs/verifier', 'reward.txt', 'public-feedback')
    if any(word in text for word in forbidden):
        raise ValueError('Private evaluation/runtime access in candidate')
    return data


def prepare(config_path=CONFIG):
    base = verify_baseline()
    cfg = read(config_path)
    _, revision = import_gepa()
    if cfg['model'] != base['model'] or cfg['thinking'] != base['thinking'] or cfg['api_base'] != base['api_base']:
        raise ValueError('Model/provider changed')
    if cfg['target'] != base['target'] or cfg['task_ids'] != [t['id'] for t in base['tasks']]:
        raise ValueError('Target budget/task selection changed')
    work = ROOT / cfg['workspace']
    work.mkdir(parents=True, exist_ok=True)
    manifest = {'config_sha256': sha(config_path), 'baseline_config_sha256': sha(BASE_CONFIG),
                'gepa_revision': revision,
                'adapter_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'acl_gepa').glob('*.py'))},
                'shared_harness_validation_sha256': sha(ROOT / 'acl_terminal_rsi/common.py'),
                'baseline_runtime_lock_sha256': sha(BASE_WORK / 'runtime-lock.json'),
                'baseline_evidence': {t['id']: {name: sha(BASE_WORK / 'trials' / t['id'] / name)
                    for name in ('result.json', 'agent/worker.json', 'agent/trajectory.json', 'agent/usage.json', 'verifier/ctrf.json')}
                    for t in base['tasks']},
                'baseline_image_records': {t['id']: sha(BASE_WORK / 'image-pulls' / f'baseline-{t["id"]}.json') for t in base['tasks']},
                'seed_candidate_sha256': candidate_id(seed_candidate(base))}
    lock = work / 'runtime-lock.json'
    if lock.exists() and read(lock) != manifest:
        raise ValueError('GEPA runtime/config/baseline evidence changed; use a versioned new workspace')
    if not lock.exists():
        write_json(lock, manifest)
    validate_candidate(seed_candidate(base), work / 'seed/terminal.yaml', cfg['task_ids'])
    return cfg, base, work
