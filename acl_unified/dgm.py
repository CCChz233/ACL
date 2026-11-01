"""Native DGM archive and selected-parent self-editing, common four-task evidence."""
from acl_dgm import adapter as native_adapter
from acl_dgm import runtime
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from .common import export,Evaluator,baseline_trial
from .protocol import SCOPE
from .provider import gateway


def run(cfg,instances,work):
    ids=cfg['protocol']['development_ids']
    native_adapter.export_baseline=export
    runtime.SCOPE=SCOPE+'\nFor self-editing task completion, echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT on its own first output line.'
    backend=Evaluator(cfg,instances,work)
    def evaluate(name,harness,task_ids):
        scores=backend(name,harness,task_ids)
        results={}
        for iid in task_ids:
            trial=baseline_trial(iid) if name=='initial' else work/'evaluations/candidate/trials'/iid
            messages=[]
            for m in read(trial/'trajectory.json').get('messages',[]):
                clean={k:m[k] for k in ('role','content','tool_calls','tool_call_id') if k in m}
                if m.get('extra',{}).get('actions'):clean['extra']={'actions':m['extra']['actions']}
                messages.append(clean)
            patch=(trial/'patch.diff').read_text()
            results[iid]={'score':scores[iid],'empty_patch':not patch.strip(),'patch':patch,'messages':messages}
        return results
    class Proposer(runtime.DGMProposer):
        def meter(self,role):return gateway(self.cfg,self.work,role)
    adapter=native_adapter.DGMAdapter(work,ids,Proposer(cfg,work,enabled=True),evaluate,
        seed=17,evidence_scope='unified_fresh_development_baseline')
    state=adapter.run(1)
    baseline=read(adapter.archive/'initial/metadata.json')['overall_performance']['accuracy_score']
    child=adapter.archive/'node_0000/metadata.json'
    score=read(child).get('overall_performance',{}).get('accuracy_score',-1) if child.exists() else -1
    result={'state':state,'selected':'candidate' if score>baseline else 'h0',
        'nomination':'best development accuracy in native archive; H0 wins ties; archive itself stays keep_all'}
    write_json(work/'native-result.json',result)
    return result
