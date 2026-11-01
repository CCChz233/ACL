"""Bind official RRSI roles to one budgeted DeepSeek client per role."""
import importlib
import re
from pathlib import Path
from acl_rsi.deepseek import DeepSeekClient, UsageLedger, action_tool, normalize_json_response
from acl_rsi.settings import write_json


def bind(cfg):
    ledger=UsageLedger(Path(cfg['workspace'])/'search_usage.json',cfg['search']['max_calls'],cfg['search']['max_tokens'])
    counters={'analyst':0,'digester':{},'propose':0,'critic':0}
    for role in ('analyst','digester','propose','critic'):
        client=DeepSeekClient(cfg,ledger,role,cfg['search'])
        create=client.client.chat.completions.create
        def recorded_create(*, _create=create, **payload):
            rid=ledger.update(lambda state:state['requests'][-1]['id'])
            import time
            start=time.time()
            write_json(Path(cfg['workspace'])/'search_requests'/f'{rid}.json',payload)
            try: return _create(**payload)
            finally:
                ledger.update(lambda state:next(row for row in state['requests'] if row['id']==rid).update(api_seconds=time.time()-start))
        client.client.chat.completions.create=recorded_create
        def generate(prompt,system=None,max_retries=0,json_only=False,model=None,max_tokens=None,cache_prefix=None,
                     _role=role,_client=client):
            tool=action_tool(_role)
            if _role=='analyst':
                counters['analyst']+=1
                if counters['analyst']>=2:
                    tool['function']['parameters']['properties']['action']['enum']=['report']
                    system=(system or '')+'\nAnalysis dispatch is complete. Return the final concise report now; no further digest calls.'
            elif _role=='digester':
                assigned=re.search(r'Assigned trace: ([^\n]+)\.txt',prompt)
                tid=assigned.group(1) if assigned else 'unknown'
                counters['digester'][tid]=counters['digester'].get(tid,0)+1
                if counters['digester'][tid]>=3:
                    tool['function']['parameters']['properties']['action']['enum']=['return']
                    system=(system or '')+'\nReturn your concise digest now, below 3000 characters. No further reads. Qualify any uncertainty.'
            else:
                counters[_role]+=1
            messages=[]
            if system: messages.append({'role':'system','content':system+'\nUse submit_rrsi_action exactly once. Only runtime tools execute actions.'})
            messages.append({'role':'user','content':'\n\n'.join(x for x in (cache_prefix,prompt) if x)})
            response=_client.complete(messages,tools=[tool],tool_choice={'type':'function','function':{'name':'submit_rrsi_action'}},model=model,max_tokens=max_tokens)
            calls=response.choices[0].message.tool_calls or []
            raw=calls[0].function.arguments if calls else response.choices[0].message.content or ''
            return normalize_json_response(raw)
        importlib.import_module(f'rrsi.{role}').generate=generate
    import rrsi.analyst,rrsi.digester,rrsi.propose
    rrsi.analyst.DIGEST_PARALLELISM=1
    rrsi.analyst.MAX_TURNS=4
    rrsi.digester.MAX_TURNS=4
    rrsi.propose.MAX_TURNS=28
    rrsi.propose.SYSTEM_TMPL=rrsi.propose.SYSTEM_TMPL.replace('is a DIFFERENT\nmodel from you','is configured independently\nfrom your search role')
    return ledger
