import hashlib
from itertools import combinations
from pathlib import Path

from acl_frameworks.common import ROOT, read, sha
from acl_rsi.settings import write_json

WORK = ROOT / 'experiments/runs/unified-hard10-v1'
CONFIG = ROOT / 'configs/unified-hard10-v1.json'
H0 = ROOT / 'experiments/runs/verified-mini-50-baseline-v2/repo/domains/swe/harness'
FRAMEWORKS = ['harnessfix', 'meta-harness', 'gepa', 'rrsi', 'dgm']
FILES = ('agent.py', 'swebench.yaml', 'LICENSE.md')
EDITABLE = {'agent': ('system_template', 'instance_template'),
            'model': ('observation_template', 'format_error_template')}
SCOPE = '''Improve only generic mini-SWE-agent behavior. Edit agent.py and only these four
YAML strings: agent.system_template, agent.instance_template, model.observation_template,
model.format_error_template. ALL other YAML keys/values must remain identical to H0;
do not add YAML keys. New controller behavior can use defaults defined in agent.py.
Preserve DefaultAgent and the Model/Environment tool-call protocol: exactly one paired
tool observation for EVERY tool call, including intercepted/skipped actions; preserve
the submission sentinel and patch-return command. Do not add dependencies, files,
repository-specific conditions, task IDs, task solutions, credentials/host access,
or access to private tests/reference patches. The task worker externally fixes
DeepSeek Flash, thinking=false, 50 API calls, 1M total tokens, 4096 output tokens and
1200 seconds; these limits cannot be raised by editing source. Search is one candidate,
80 calls/1M tokens INCLUDING every diagnosis/plan/repair. No human-guided recovery.
Only the four exported development histories are available. Six report tasks are sealed.
Source YAML model_name and step_limit are original unused/overridden defaults.
'''


def split(selection):
    rows = selection['selected']
    choices = []
    for part in combinations(rows, 4):
        if any(sum(r['repo'] == repo for r in part) != 2 for repo in ('django/django', 'sphinx-doc/sphinx')):
            continue
        if sum(r['scores'][0] for r in part) != 1:
            continue
        failed = [r for r in part if not r['scores'][0]]
        if {r['baseline_stop'] for r in failed} != {'LimitsExceeded', 'BudgetExceeded', 'Submitted'}:
            continue
        ids = sorted(r['task_id'] for r in part)
        digest = hashlib.sha256(('unified-v1|17|'+','.join(ids)).encode()).hexdigest()
        choices.append((digest, part))
    _, chosen = min(choices, key=lambda x:x[0])
    dev = sorted(r['task_id'] for r in chosen)
    train = [min((r for r in chosen if r['repo'] == repo and not r['scores'][0]),
                 key=lambda r:hashlib.sha256(('hf-train|17|'+r['task_id']).encode()).hexdigest())['task_id']
             for repo in ('django/django', 'sphinx-doc/sphinx')]
    val = sorted(set(dev)-set(train))
    return {'development_ids': dev, 'hf_train_ids': train, 'hf_selection_ids': val,
            'report_ids': [i for i in selection['task_ids'] if i not in dev]}


def prepare():
    selection_path = ROOT / 'experiments/runs/hard10-selection-v1/selection.json'
    selection = read(selection_path)
    source = read(ROOT / 'configs/dgm-hard10-v1.json')
    source.update(purpose='unified-five-frameworks-hard10-one-candidate', workspace=str(WORK),
                  evolve_ids=selection['task_ids'], heldout_ids=[])
    source['protocol'] = {'frameworks': FRAMEWORKS, 'seed': 17, 'rounds': 1, 'candidate_cap': 1,
        'all_task_ids': selection['task_ids'], **split(selection),
        'selection_file': str(selection_path.relative_to(ROOT)), 'selection_sha256': sha(selection_path),
        'split_policy': 'H0-only strata: 2/repo, 1 historical pass, 3 failures with one each call/token/submitted; min SHA256 salted17; ignores all candidate outcomes',
        'scope': 'historically used development panel; sealed feedback is prospective, not unseen test data',
        'max_target_executions': 60, 'max_total_calls': 3400, 'max_total_tokens': 65000000,
        'baseline': 'fresh ten tasks, shared by all frameworks', 'manual_recovery': False,
        'candidate_tests': 'scope/syntax/constructor and single/multiple tool-result contracts before paid evaluation',
        'nomination': 'native development decision; DGM archive readout uses best development accuracy, H0 on ties',
        'report_evaluation': 'raw valid candidate on six after nomination frozen, including native non-promotion; selected H0 reuses fresh baseline report',
        'task_concurrency': 1, 'search_wall_seconds': 3600, 'framework_wall_seconds': 30000}
    source['rrsi'].update(T=1, n_fail_traces=3, n_success_traces=1)
    if CONFIG.exists() and read(CONFIG) != source:
        raise ValueError('Unified protocol already frozen with different content')
    write_json(CONFIG, source)
    WORK.mkdir(parents=True, exist_ok=True)
    if (WORK / 'config.json').exists() and read(WORK / 'config.json') != source:
        raise ValueError('Run configuration differs')
    write_json(WORK / 'config.json', source)
    write_json(WORK / 'protocol.json', source['protocol'])
    return source


if __name__ == '__main__':
    import json
    print(json.dumps(prepare()['protocol'], ensure_ascii=False, indent=2))
