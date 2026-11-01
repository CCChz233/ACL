"""Read-only progress and full cost accounting, without loading candidate code."""
import json
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from .protocol import WORK,FRAMEWORKS


def ledger(paths):
    requests=[r for p in paths for r in read(p)['requests']]
    return {'calls':len(requests),'actual_tokens':sum(r.get('usage',{}).get('total_tokens',0) for r in requests),
        'unknown_usage_requests':sum('usage' not in r for r in requests),
        'charged_or_reserved_tokens':sum(r['charged_tokens'] for r in requests)}


def summarize(write=False):
    result={'protocol':read(WORK/'protocol.json'),'baseline':{},'frameworks':{},'whole_experiment_usage':{}}
    p=WORK/'baseline/result.json'
    result['baseline']=read(p) if p.exists() else read(WORK/'baseline/status.json')
    progress=WORK/'baseline/progress.json'
    if progress.exists():result['baseline']['progress']=read(progress)
    batch=WORK/'batch-status.json'
    if batch.exists():result['batch']=read(batch)
    for name in FRAMEWORKS:
        folder=WORK/name
        saved=folder/'result.json'
        item=read(saved) if saved.exists() else read(folder/'status.json') if (folder/'status.json').exists() else {'status':'pending'}
        if 'native' in item:item={k:v for k,v in item.items() if k!='native'}
        item['optimizer_usage']=ledger([folder/'optimizer-api/usage.json']) if (folder/'optimizer-api/usage.json').exists() else ledger([])
        item['target_usage']=ledger(list(folder.glob('evaluations/candidate/trials/*/usage.json')))
        item['graded_tasks']=len(list(folder.glob('evaluations/candidate/trials/*/grade.json')))
        result['frameworks'][name]=item
    paths=list(WORK.glob('*/optimizer-api/usage.json'))+list(WORK.glob('*/evaluations/*/trials/*/usage.json'))
    result['whole_experiment_usage']=ledger(paths)
    u=result['whole_experiment_usage']
    assert u['calls']<=3400 and u['charged_or_reserved_tokens']<=65000000
    if write:write_json(WORK/'summary.json',result)
    return result


if __name__=='__main__':print(json.dumps(summarize(),ensure_ascii=False,indent=2))
