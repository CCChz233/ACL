"""Grade two predeclared historical patches; no optimizer or target-model calls.

This is conditional replay evidence, never a new free-running checkpoint score.
Uses existing pinned images only and leaves all historical artifacts unchanged.
"""
from pathlib import Path
import hashlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/exports/within-round-audit-2026-10-20'
sys.path.insert(0, str(ROOT))
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['MSWEA_GLOBAL_CONFIG_DIR'] = str(OUT / 'empty-global-config')
os.environ['MSWEA_SILENT_STARTUP'] = '1'


def main():
    import docker
    from acl_rsi.grading import grade
    from acl_rsi.worker import image_name
    from scripts.run_swe_local import require_cache

    ids = ['sphinx-doc__sphinx-10435', 'django__django-12039']
    dataset = json.loads((ROOT/'benchmarks/datasets/swe-bench-verified-mini/test.json').read_text())
    instances = {r['instance_id']: r for r in dataset}
    audit = json.loads((OUT/'meta-round1-audit.json').read_text())
    provenance = {r['task']:r for r in audit['conditional_episode_replays']}
    client = docker.from_env(timeout=60)
    try:
        require_cache(client, json.loads((ROOT/'configs/swe-mini-image-cache.json').read_text()))
        image_ids_before = {i:client.images.get(image_name(i)).id for i in ids}
    finally:
        client.close()
    rows = []
    started = time.time()
    for iid in ids:
        patch_file = OUT/'recovered-patches'/iid/'patch.diff'
        patch = patch_file.read_text()
        assert hashlib.sha256(patch.encode()).hexdigest() == provenance[iid]['patch_provenance']['sha256']
        print('GRADE_START',iid,flush=True)
        result = grade(instances[iid], patch, OUT/'official-recovered-patch-grades'/iid, 600)
        row = {'task':iid, 'grade':result, 'patch_sha256':hashlib.sha256(patch.encode()).hexdigest(),
               'conditional_replay':provenance[iid]['replays'],
               'scope':'fixed recorded model actions; patch grading, not free-running earlier-harness evaluation'}
        rows.append(row)
        (OUT/'recovered-patch-grading-summary.json').write_text(json.dumps(
            {'api_calls':0,'selected_tasks':ids,'completed':len(rows),'results':rows,
             'seconds':time.time()-started},ensure_ascii=False,indent=2))
        print('GRADE_DONE',iid,result.get('resolved'),result.get('completed'),result.get('reason'),flush=True)
    client = docker.from_env(timeout=60)
    try:
        after = {i:client.images.get(image_name(i)).id for i in ids}
        assert after == image_ids_before
    finally:
        client.close()
    print('PINNED_IMAGES_RETAINED',True,flush=True)


if __name__ == '__main__':
    main()
