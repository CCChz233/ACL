"""Reserve a real delivery/repair allowance within the same per-round ledger."""
import contextlib
import contextvars
import copy
from acl_unified.provider import gateway as original_gateway
from acl_rsi.deepseek import DeepSeekClient
from types import SimpleNamespace

PHASE=contextvars.ContextVar('highbudget_phase',default='native')


@contextlib.contextmanager
def delivery_phase():
    token=PHASE.set('delivery')
    try:yield
    finally:PHASE.reset(token)


def gateway(cfg,work,role):
    native=copy.deepcopy(cfg)
    native['search'].update(max_calls=cfg['protocol']['native_call_cap'],max_tokens=cfg['protocol']['native_token_cap'])
    a=original_gateway(native,work,role)
    b=original_gateway(cfg,work,role+'_delivery')
    def complete(**kwargs):return (b if PHASE.get()=='delivery' else a)(**kwargs)
    complete.ledger=b.ledger
    return complete


def rrsi_generate(cfg,work,role):
    meter=gateway(cfg,work,role)
    def complete(messages,*,json_only=False,**kwargs):
        if json_only:kwargs['response_format']={'type':'json_object'}
        return meter(model=kwargs.pop('model',None) or cfg['model'],messages=messages,**kwargs)
    client=SimpleNamespace(role=role,complete=complete)
    instructions={
        'analyst':'You have three analyst turns. Dispatch one focused batch of digesters, then REPORT. Do not repeatedly dispatch the same trace. All ten histories remain available.',
        'digester':'You have six tool turns. Read the relevant beginning/end or search once, then RETURN a compact evidence-grounded digest. Do not keep exploring until the turn limit.',
        'propose':'Implement a small real generic Harness change, then call done with truthful edit metadata. Prioritize a valid deliverable over exhaustive history exploration.'}
    def generate(prompt,**kwargs):
        kwargs['system']=(kwargs.get('system') or '')+'\n'+instructions.get(role,'')
        return DeepSeekClient.generate(client,prompt,**kwargs)
    return generate
