"""Unchanged native RRSI loop, with fresh common evidence and unified evaluator."""
import importlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from acl_rsi.cli import make_run
from acl_rsi.domain import MiniSWEDomain
from acl_rsi.settings import write_json
from acl_rsi.worker import image_name
from acl_gepa_swe.feedback import record
from rrsi.evaluate import TaskResult
from .common import baseline_trial,Evaluator,validate,export
from .provider import rrsi_generate
from .protocol import SCOPE


def run(cfg,instances,work):
    p=cfg['protocol'];ids=p['development_ids']
    export(work/'optimizer',ids)
    runner=make_run(cfg)
    evaluator=Evaluator(cfg,instances,work)
    class Domain(MiniSWEDomain):
        briefs={k:v+'\n'+SCOPE for k,v in MiniSWEDomain.briefs.items()}
        def run(self,root,runs_dir,job,task_ids,k,log_prefix=''):
            if k!=1 or set(task_ids)!=set(ids) or job not in ('base','r0A'):
                raise ValueError('Unexpected native evaluation request')
            (Path(runs_dir)/'jobs'/job).mkdir(parents=True,exist_ok=True)
            evaluator('h0' if job=='base' else 'candidate',self.harness_dir(Path(root)),task_ids)
        def trial(self,job,iid):
            return baseline_trial(iid) if job=='base' else work/'evaluations/candidate/trials'/iid
        def score(self,runs_dir,job,task_ids,k):
            scores={}
            for iid in task_ids:
                r=record(self.trial(job,iid),iid,instances[iid],trace=False)
                scores[iid]=TaskResult(rewards=[r['score']],tokens=[r['usage'].get('actual_tokens')],missing=0)
            return scores,{'scope':'unified four-task development'}
        def load_trial(self,runs_dir,job,task_id,trial):
            folder=self.trial(job,task_id)
            return {'task_id':task_id,'trajectory':json.loads((folder/'trajectory.json').read_text()),
                'worker':json.loads((folder/'worker.json').read_text()),
                'score':bool(record(folder,task_id,instances[task_id],trace=False)['score'])}
        def smoke(self,root,runs_dir,job,task_ids):
            try:
                validate(self.harness_dir(Path(root)),require_change=not job.startswith('baseline'))
                return True,{'stage':'unified_scope_and_protocol','api_calls':0}
            except ValueError as error:
                return False,{'stage':'unified_scope_and_protocol','error':str(error)[:300]}
    domain=Domain(cfg);domain.root=runner.domain.root;runner.domain=domain
    for role in ('analyst','digester','propose','critic'):
        module=importlib.import_module('rrsi.'+role)
        module.generate=rrsi_generate(cfg,work,role)
        if role=='propose':
            module.SYSTEM_TMPL=module.SYSTEM_TMPL.replace('is a DIFFERENT\nmodel from you','is configured independently\nfrom your search role')
    # Model-issued Bash remains read-only, inside a container mounting only rendered dev traces.
    digester=importlib.import_module('rrsi.digester')
    def safe(root,relative):
        target=(root/relative).resolve()
        if not target.is_relative_to(root.resolve()):raise ValueError('Trace path escape')
        return target
    digester._safe=safe
    def bash(command,*,shell,cwd,capture_output,text,timeout):
        cwd=Path(cwd).resolve()
        if not cwd.is_relative_to(work.resolve()):raise ValueError('Trace mount outside workspace')
        return subprocess.run(['docker','run','--rm','--platform','linux/amd64','--network','none',
            '--cpus','1','--memory','1g','--volume',f'{cwd}:/evidence:ro','-w','/evidence',
            image_name(ids[0]),'bash','-c',command],capture_output=True,text=True,timeout=timeout+30)
    digester.subprocess=SimpleNamespace(run=bash)
    runner.baseline()
    runner.round(0)
    frontier=runner.frontier()
    write_json(work/'native-result.json',frontier)
    return {'frontier':frontier,'selected':'candidate' if frontier['incumbent']['job']=='r0A' else 'h0'}
