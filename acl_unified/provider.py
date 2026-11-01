"""All optimization roles share one strictly metered request ledger."""
from types import SimpleNamespace
import time

from acl_frameworks.provider import RecordedDeepSeek
from acl_rsi.deepseek import DeepSeekClient
from acl_rsi.deepseek import BudgetExceeded
from acl_rsi.settings import write_json
from acl_frameworks.common import read


def gateway(cfg,work,role):
    provider={k:cfg[k] for k in ('model','api_base','thinking')}
    provider.update(limits=cfg['search'],xml_dsml_compat=role in ('diagnosis','planning','implementation'))
    meter=RecordedDeepSeek(provider,work/'optimizer-api',role,enabled=True)
    def call(**kwargs):
        path=work/'optimizer-api/search-start.json'
        if not path.exists():write_json(path,{'started_at':time.time()})
        if time.time()-read(path)['started_at']>cfg['protocol']['search_wall_seconds']:
            raise BudgetExceeded('search_wall_limit',{})
        return meter(**kwargs)
    call.ledger=meter.ledger
    return call


def rrsi_generate(cfg,work,role):
    meter=gateway(cfg,work,role)
    def complete(messages,*,json_only=False,**kw):
        if json_only:kw['response_format']={'type':'json_object'}
        return meter(model=kw.pop('model',None) or cfg['model'],messages=messages,**kw)
    client=SimpleNamespace(role=role,complete=complete)
    def generate(prompt,**kwargs):
        return DeepSeekClient.generate(client,prompt,**kwargs)
    return generate
