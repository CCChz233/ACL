from acl_frameworks.meta_harness import MetaHarnessAdapter
from acl_frameworks.proposer import DeepSeekFileProposer
from acl_frameworks.common import read
from acl_rsi.settings import write_json
from .common import export,Evaluator,validate
from .provider import gateway
from .protocol import SCOPE


def run(cfg,instances,work):
    ids=cfg['protocol']['development_ids']
    public=work/'optimizer'
    export(public,ids)
    proposer=DeepSeekFileProposer(public,gateway(cfg,work,'propose'))
    def propose(prompt,iteration):
        rows=proposer(prompt+'\nProduce exactly ONE candidate. '+SCOPE,iteration)
        if len(rows)!=1:raise ValueError('One candidate cap')
        return rows
    adapter=MetaHarnessAdapter(work,ids,propose,Evaluator(cfg,instances,work))
    def candidate_gate(name,path):
        try:validate(adapter.folder(name),require_change=name!='h0');return True
        except ValueError as error:
            write_json(work/'candidate-validation.json',{'candidate':name,'valid':False,'reason':str(error)[:300]})
            return False
    adapter.native.validate_candidate=candidate_gate
    frontier=adapter.run(1)
    return {'frontier':frontier,'selected':'h0' if frontier.get('_best',{}).get('agent')=='h0' else 'candidate'}
