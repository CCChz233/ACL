"""Freeze explicit recovery before any new paid execution."""
import datetime
import shutil
from acl_frameworks.common import ROOT, read, sha
from acl_rsi.settings import write_json
from acl_unified import common
from .protocol import WORK, OLD, FRAMEWORKS, round_dir, verify_old, verify


def main():
    verify_old()
    common.preflight()
    if WORK.exists():
        raise ValueError('Recovery already prepared')
    for name in FRAMEWORKS:
        for n in (1, 2):
            folder = round_dir(name, n)
            cfg = read(OLD / name / f'round-{n}/config.json')
            cfg.update(workspace=str(folder), purpose='explicit-missing-results-recovery')
            cfg['recovery'] = {'original': str(OLD), 'replay_first_native_artifact': name == 'dgm' and n == 1,
                               'hf_feedback_mapping_fix': True, 'dgm_nonrecursive_structure_fix': True}
            write_json(folder / 'config.json', cfg)
            write_json(folder / 'storage-policy.json', {'retain_mini_images': True, 'local_only': True})
            if n == 1:
                shutil.copytree(OLD / name / 'round-1/optimizer-api', folder / 'optimizer-api')
    # Copy evidence, never symlink scored destinations that a native pipeline might write.
    hf = round_dir('harnessfix', 1)
    source = OLD / 'harnessfix/round-1'
    shutil.copytree(source / 'optimizer', hf / 'optimizer', symlinks=False)
    shutil.copytree(source / 'evaluations/candidate', hf / 'evaluations/candidate')
    write_json(hf / 'reused-evaluation.json', {'source': str(source / 'evaluations/candidate'),
        'harness_sha256': common.fingerprint(source / 'evaluations/candidate/harness'),
        'new_paid_workers': 0, 'new_grader_runs': 0, 'new_model_calls_allowed': 0})
    write_json(WORK / 'authorization.json', {'user_instruction': '没有结果的补上，重跑一下',
        'scope': 'HF round1 native continuation without new evaluation, HF round2; DGM first native artifact recovery and round2',
        'max_new_task_executions': 30, 'combined_max_task_executions': 100,
        'combined_call_token_caps': [9000, 180000000], 'per_round_optimizer_caps': [400, 8000000],
        'per_task_caps': [50, 1000000, 1200], 'human_candidate_edits': False, 'all_original_costs_included': True})
    write_json(WORK / 'baseline.json', read(OLD / 'baseline.json'))
    paths = list((ROOT / 'acl_multiround_recovery').glob('*.py')) + [ROOT / 'tests/test_multiround_recovery.py']
    paths += list(WORK.glob('*/round-*/config.json'))
    # Freeze the artifacts being replayed as well as controller/configuration.
    paths += [p for p in (OLD / 'dgm/round-1/optimizer/candidates/node_0000/harness').iterdir() if p.is_file()]
    paths += list(hf.glob('optimizer/**/*'))
    paths += list(hf.glob('evaluations/candidate/**/*'))
    paths = [p for p in paths if p.is_file() and p.suffix != '.pyc' and '__pycache__' not in p.parts]
    # Mutable native checkpoint copies are snapshotted separately, not runtime locked.
    runtime = [p for p in paths if not p.is_relative_to(hf / 'optimizer')]
    runtime = [p for p in runtime if not p.is_relative_to(hf / 'evaluations')]
    write_json(WORK / 'runtime-lock.json', {'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'files': {str(p.relative_to(ROOT)): sha(p) for p in runtime}})
    write_json(WORK / 'replay-evidence-lock.json', {'files': {str(p.relative_to(ROOT)): sha(p) for p in paths}})
    shutil.copytree(ROOT / 'acl_multiround_recovery', WORK / 'source-snapshot/acl_multiround_recovery',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    verify()
    from .status import summarize
    summarize(write=True)
    print('Recovery frozen, 30 maximum new task executions; zero new API calls.')


if __name__ == '__main__':
    main()
