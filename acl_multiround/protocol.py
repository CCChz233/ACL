from pathlib import Path
from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import write_json,load_settings
from acl_unified.protocol import H0,FILES,FRAMEWORKS

WORK=ROOT/'experiments/runs/full10-five-rounds-v1'
CONFIG=ROOT/'configs/full10-five-rounds-v1.json'
BASE=ROOT/'experiments/runs/unified-hard10-v1/baseline/evaluations/h0'
SCOPE='''Improve only generic mini-SWE-agent Harness behavior, starting from the supplied
CURRENT PARENT harness. Edit agent.py and only these four YAML prompt strings:
agent.system_template, agent.instance_template, model.observation_template,
model.format_error_template. All other YAML keys/values and LICENSE.md stay fixed.
Preserve every tool-call/result pairing and the patch submission command. No added
dependencies, task/repository-specific rules or solutions, hidden tests, credentials,
host artifacts, direct provider access or budget changes. Task execution is fixed
at DeepSeek Flash, thinking=false, 50 calls/1M tokens/4096 output/1200s per task.
This round has at most ONE candidate and 80 search calls/1M tokens shared by all
diagnosis, planning, implementation and native repair. All TEN public task histories
and binary outcomes are available. No heldout split; these are development tasks.
The next round starts from the native-retained parent. Prior round attempt summaries
are available under history/rounds/. Do not repeat changes already rejected.
'''


def round_dir(name,index):return WORK/name/f'round-{index}'


def settings(name,index):
    path=round_dir(name,index)/'config.json'
    cfg=load_settings(path)
    if cfg['model']!='deepseek-flash' or cfg['api_base'].rstrip('/')!='https://api.deepseek.com' or cfg['thinking']:
        raise ValueError('Provider differs from fixed experiment')
    return cfg


def verify():
    lock=read(WORK/'runtime-lock.json')
    assert sha(CONFIG)==lock['config_sha256']
    for file,digest in lock['files'].items():
        if sha(ROOT/file)!=digest:raise ValueError('Frozen full10 source/config changed: '+file)
    actual={str(p.relative_to(ROOT)) for p in (ROOT/'acl_multiround').glob('*.py')}
    assert actual=={p for p in lock['files'] if p.startswith('acl_multiround/')}
    for file,digest in lock['baseline_files'].items():assert sha(ROOT/file)==digest
    from acl_unified.framework import verify_lock
    verify_lock()


def prepare():
    if (WORK/'runtime-lock.json').exists():raise ValueError('Experiment already frozen')
    source=read(ROOT/'configs/unified-hard10-v1.json')
    ids=source['protocol']['all_task_ids']
    source.update(purpose='full-ten-tasks-five-frameworks-five-longitudinal-rounds',workspace=str(WORK),evolve_ids=ids,heldout_ids=[])
    source['rrsi'].update(T=1,n_fail_traces=10,n_success_traces=10)
    source['protocol']={'frameworks':FRAMEWORKS,'all_task_ids':ids,'development_ids':ids,
        'report_ids':[],'hf_train_ids':ids,'hf_selection_ids':ids,
        'rounds':5,'candidate_cap':1,'seed':17,'task_concurrency':1,
        'search_wall_seconds':3600,'framework_wall_seconds':30000,
        'max_new_target_executions':250,'max_new_calls':14500,'max_new_tokens':275000000,
        'scope':'all ten historical development tasks are feedback and evaluation each round',
        'parent_policy':'native-retained harness and its own complete trajectories; independent framework lineages',
        'native_state':'one native step per outer round seeded with current parent; prior public attempt summaries carried; native internal long-run scheduler/archive is locally reinitialized',
        'empty_round_policy':'no valid proposal: explicitly re-evaluate unchanged parent on all ten; mark as parent retest, never a successful modification',
        'raw_and_retained':'report raw tested version separately from native-retained version; carry retention, not rejected candidates',
        'infrastructure_policy':'no automatic paid worker retries; block broken lineage, preserve all partial evidence',
        'harnessfix_feedback':'train and selection callbacks both use same TEN tasks, evaluation cache avoids double paid runs',
        'dgm_bugfix':'predeclared unresolved-or-empty-patch selection fallback, same seed17; unchanged upstream on disk',
        'native_role_turn_limits':'unchanged native one-step limits within shared per-round ledger',
        'baseline':'reuse one source-locked ten-task H0 from unified-hard10-v1, 3/10; no old candidate reused'}
    write_json(CONFIG,source);write_json(WORK/'config.json',source)
    for name in FRAMEWORKS:
        for index in range(1,6):
            cfg=dict(source,workspace=str(round_dir(name,index)))
            write_json(round_dir(name,index)/'config.json',cfg)
            write_json(round_dir(name,index)/'storage-policy.json',{'retain_mini_images':True,'local_only':True})
    return source
