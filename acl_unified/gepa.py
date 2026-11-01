"""Native GEPA reflection over an edit specification covering code and prompts."""
import json

from acl_gepa.common import import_gepa,candidate_id
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from .common import copy_harness,validate,Evaluator,baseline_trial,export
from acl_frameworks.proposer import DeepSeekFileProposer,TOOLS
from acl_gepa_swe.feedback import record
from .provider import gateway
from .protocol import H0,FILES,SCOPE

COMPONENT='harness_edit_spec'
SEED={COMPONENT:'{"edits": []}'}


def materialize(candidate,folder):
    if set(candidate)!={COMPONENT}:raise ValueError('GEPA parameter changed')
    spec=json.loads(candidate[COMPONENT])
    if set(spec)!={'edits'} or not isinstance(spec['edits'],list):raise ValueError('Invalid edit specification')
    files={f:(H0/f).read_text() for f in FILES}
    for e in spec['edits']:
        if set(e)!={'file','old','new'} or e['file'] not in ('agent.py','swebench.yaml') or not all(isinstance(e[k],str) for k in e):
            raise ValueError('Illegal edit')
        if not e['old'] or files[e['file']].count(e['old'])!=1:raise ValueError('Edit needs one unique match')
        files[e['file']]=files[e['file']].replace(e['old'],e['new'],1)
    copy_harness(H0,folder)
    for f in FILES:(folder/f).write_text(files[f])
    validate(folder,require_change=bool(spec['edits']))
    return bool(spec['edits'])


def run(cfg,instances,work):
    gepa,_=import_gepa()
    from gepa.core.adapter import EvaluationBatch
    ids=cfg['protocol']['development_ids']
    public=work/'optimizer'
    export(public,ids)
    evaluator=Evaluator(cfg,instances,work)
    meter=gateway(cfg,work,'gepa_reflection')
    class Adapter:
        propose_new_texts=None
        def evaluate(self,batch,candidate,capture_traces=False):
            if not all(i['task_id'] in ids for i in batch):raise ValueError('Sealed task requested')
            folder=work/'gepa-candidates'/candidate_id(candidate)/'harness'
            changed=materialize(candidate,folder)
            scores=evaluator('candidate' if changed else 'h0',folder,[i['task_id'] for i in batch])
            rows=[]
            for i in batch:
                iid=i['task_id']
                trial=work/'evaluations/candidate/trials'/iid if changed else baseline_trial(iid)
                row=record(trial,iid,instances[iid],trace=False)
                if capture_traces:
                    # Retain the established GEPA 9k-character preview; complete
                    # public evidence can be expanded by the same metered LM.
                    row.update(record(trial,iid,instances[iid],trace=True))
                    row['raw_history_path']=f'history/{iid}/trajectory.json'
                rows.append(row)
            return EvaluationBatch(outputs=rows,scores=[scores[i['task_id']] for i in batch],
                trajectories=rows if capture_traces else None,num_metric_calls=len(batch) if changed else 0)
        def make_reflective_dataset(self,candidate,eval_batch,components_to_update):
            if components_to_update!=[COMPONENT]:raise ValueError('Unexpected GEPA component')
            rows=[{'Inputs':{'public_issue':r['problem_statement']},'Generated Outputs':{
                'public_agent_trace':r['public_agent_trace'],'full_history_read_path':r['raw_history_path'],'stop':r['stop']},'Feedback':{
                'resolved':r['score'],'usage':r['usage']}} for r in eval_batch.trajectories]
            write_json(work/'reflection-feedback.json',rows)
            return {COMPONENT:rows}
    def reflect(prompt):
        messages=[{'role':'user','content':prompt}] if isinstance(prompt,str) else prompt
        reader=DeepSeekFileProposer(public,meter)
        tools=[t for t in TOOLS if t['function']['name'] in ('Read','Glob','Grep')]
        while True:
            response=meter(model=cfg['model'],messages=messages,tools=tools)
            choice=response.choices[0];message=choice.message
            if choice.finish_reason=='length':raise ValueError('GEPA reflection truncated')
            if not message.tool_calls:return message.content or ''
            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                try:result=reader.tool(call.function.name,json.loads(call.function.arguments))
                except (ValueError,OSError,KeyError):result='ToolError: invalid public read request'
                messages.append({'role':'tool','tool_call_id':call.id,'content':result})
    sources=json.dumps({f:(H0/f).read_text() for f in ('agent.py','swebench.yaml')},ensure_ascii=False)
    template='''Improve a generic mini agent by editing its controller and prompt strings.
'''+SCOPE+'''\nAll source files at the common H0:\n'''+sources+'''
Current edit specification (applied to H0):
<curr_param>
Public development interactions and binary feedback:
<side_info>
The interaction text is a preview. Read/Glob/Grep provide complete public files
under history/ and harness/ when more evidence is needed. Read offset and limit
are character units; Grep pattern is a file glob and text is a literal substring.
Return one fenced code block containing ONLY a JSON object {"edits":[{"file":"agent.py" or "swebench.yaml","old":"unique exact original substring","new":"replacement"}]}.
The edit specification must be complete relative to H0; preserve escaped newlines in JSON.
Use a small coherent generic change. This edit representation permits controller code edits,
not just prompts; no need to return entire unchanged files. No extra prose.
'''
    result=gepa.optimize(seed_candidate=SEED,trainset=[{'task_id':i} for i in ids],valset=None,
        adapter=Adapter(),reflection_lm=reflect,reflection_prompt_template=template,
        reflection_minibatch_size=len(ids),skip_perfect_score=False,candidate_selection_strategy='pareto',
        module_selector='all',use_merge=False,max_metric_calls=2*len(ids),
        stop_callbacks=lambda state:state.i>=0,run_dir=str(work/'native-gepa'),cache_evaluation=True,
        write_agent_state=False,seed=17,raise_on_exception=True,display_progress_bar=False)
    result=result.to_dict();write_json(work/'native-result.json',result)
    # Native result schema is retained; nomination is determined from dev outcomes below.
    if len(result['candidates'])>2:raise ValueError('Native GEPA exceeded one-new-candidate cap')
    return {'native_result':result,'selected':'h0' if result['best_idx']==0 else 'candidate'}
