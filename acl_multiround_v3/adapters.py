"""Higher-budget native stages, explicit model completion, no shared replacement optimizer."""
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
from acl_frameworks.common import ROOT,sha
from acl_rsi.settings import write_json
from acl_rsi.deepseek import BudgetExceeded
from acl_frameworks.proposer import DeepSeekFileProposer
from acl_unified import common
from acl_multiround.protocol import SCOPE as OLD_SCOPE
from .provider import gateway,rrsi_generate,delivery_phase
from acl_dgm import adapter as _dgm_adapter
from acl_dgm.native import outer as _dgm_outer
_DGM_VALIDATE=_dgm_adapter.validate

SCOPE=OLD_SCOPE.replace('80 search calls/1M tokens','400 search calls/8M tokens')+'''
Deliver a real modification in this round. Complete one small native hypothesis
instead of spending all resources reading histories. Invalid candidates must be
repaired by the model before evaluation, never replaced with the original parent.
'''


def build_native(name,cfg,instances,work,b):
    source=ROOT/'acl_multiround/adapters.py'
    text=source.read_text()
    anchor='source=Path(live.__file__);text=source.read_text()'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'''
    text=text.replace("20 if 'analysis' in file else 40", "20 if 'analysis' in file else 100")
    text=text.replace("agg.AGG_AGENT_STEP_LIMIT = 20", "agg.AGG_AGENT_STEP_LIMIT = 60")
    text=text.replace("    spec.loader.exec_module(module)", "    spec.loader.exec_module(module)\\n    install_native_hf(module)")''')
    text=text.replace("link.symlink_to(bindings['baseline_trial'](iid))", "\n        if not link.exists():link.symlink_to(bindings['baseline_trial'](iid))")
    module=importlib.util.module_from_spec(importlib.util.spec_from_loader('acl_multiround._highbudget_adapters',loader=None))
    module.__package__='acl_multiround';module.__file__=str(source)
    exec(compile(text,str(source),'exec'),module.__dict__)
    module.SCOPE=SCOPE;module.gateway=gateway
    (work/'highbudget-native-adapters.py').write_text(text)
    write_json(work/'native-parameter-adaptation.json',{'original_sha256':sha(source),
        'hf_analysis_steps':20,'hf_planner_steps':60,'hf_implementation_steps':100,
        'rrsi_analyst_turns':3,'rrsi_digester_turns':6,'rrsi_proposer_turns':80,
        'native_call_token_reservation':[300,6000000],'total_call_token_limits':[400,8000000],
        'model_only_validity_repair':True,'human_candidate_edits':False})

    class SeededProposer(DeepSeekFileProposer):
        def __init__(self,public,meter):
            super().__init__(public,meter)
            target=Path(public)/'candidates/h1/harness'
            if not target.exists():common.copy_harness(b['parent'],target)
        def __call__(self,prompt,iteration):
            prompt+='\nCandidate candidates/h1/harness/ is already seeded from the CURRENT PARENT. '
            prompt+='Use small Edit calls to implement ONE real mechanism, then Finish name h1. '
            prompt+='Begin implementation after inspecting at most two detailed histories; all ten remain readable. '
            prompt+='Do not rewrite unchanged source or license. Do not spend the entire budget exploring.'
            result=super().__call__(prompt,iteration)
            write_json(work/'native-proposal.json',result)
            return result

    def load_step(which,bindings,directory):
        src=ROOT/'acl_unified'/f'{which}.py';code=src.read_text()
        code=code.replace('    export(public,ids)',"    if not (public/'snapshot.json').exists():export(public,ids)")
        code=code.replace("    export(work/'optimizer',ids)","    if not (work/'optimizer/snapshot.json').exists():export(work/'optimizer',ids)")
        if which=='rrsi':
            code=code.replace('    runner.baseline()','    if not runner.frontier_path.exists():runner.baseline()')
        if which=='dgm':
            code=code.replace("child=adapter.archive/'node_0000/metadata.json'", "child=adapter.archive/(state['archive'][-1]+'/metadata.json')")
        m=importlib.util.module_from_spec(importlib.util.spec_from_loader('acl_unified._highbudget_'+which,loader=None))
        m.__package__='acl_unified';m.__file__=str(src)
        exec(compile(code,str(src),'exec'),m.__dict__)
        for key in ('validate','export','Evaluator','baseline_trial'):setattr(m,key,bindings[key])
        m.H0=bindings['parent'];m.SCOPE=SCOPE;m.gateway=gateway;m.rrsi_generate=rrsi_generate
        if which=='meta':m.DeepSeekFileProposer=SeededProposer
        return m
    module.load_step=load_step

    original_hf=module.harnessfix_module
    def hf_module(*args):
        m=original_hf(*args)
        def install(native):
            modify=native.step_modify;audit=native.step_plan_diff_audit
            def flat(target):
                p=work/'native-delivery/harness';p.mkdir(parents=True,exist_ok=True)
                shutil.copy2(target/m.AGENT_FILE,p/'agent.py');shutil.copy2(target/m.YAML_FILE,p/'swebench.yaml')
                shutil.copy2(b['parent']/'LICENSE.md',p/'LICENSE.md');return p
            def restore(p,target):
                shutil.copy2(p/'agent.py',target/m.AGENT_FILE);shutil.copy2(p/'swebench.yaml',target/m.YAML_FILE)
            def complete_modify(*a,**kw):
                target=modify(*a,**kw);p=flat(target);b['validate'](p);restore(p,target);return target
            def complete_audit(*a,**kw):
                result=audit(*a,**kw)
                if not result.get('passed'):
                    target=kw.get('target_dir') if 'target_dir' in kw else a[3]
                    p=flat(target)
                    b['delivery'].ensure(p,force_reason='Native HarnessFix plan/diff audit rejected: '+json.dumps(result,ensure_ascii=False)[:7000])
                    restore(p,target);result=audit(*a,**kw)
                return result
            native.step_modify=complete_modify;native.step_plan_diff_audit=complete_audit
        m.install_native_hf=install
        return m
    module.harnessfix_module=hf_module

    if name=='rrsi':
        for role,limit in (('analyst',3),('digester',6),('propose',80)):
            setattr(importlib.import_module('rrsi.'+role),'MAX_TURNS',limit)
        loop=importlib.import_module('rrsi.loop');propose_module=importlib.import_module('rrsi.propose')
        original_propose=propose_module.propose
        def complete_propose(*a,**kw):
            try:result=original_propose(*a,**kw)
            except BudgetExceeded:result={'status':'budget_boundary','reason':'Native proposal requires completion'}
            if result.get('status')!='done':
                write_json(work/'rrsi-proposal-completion.json',{'original':result,'same_native_proposer':True})
                retry=dict(kw,repair_brief={'reasons':['Complete the native partial proposal with real generic edits and truthful done metadata. '+str(result.get('reason',''))]})
                with delivery_phase():result=original_propose(*a,**retry)
            if result.get('status')=='done':
                target=Path(a[1] if len(a)>1 else kw['harness_dir'])
                b['validate'](target)  # before native critic and git commit, not after scoring
            return result
        loop.propose=complete_propose
    if name=='dgm':
        native=importlib.import_module('acl_dgm.adapter');old_validate=native.validate
        native.outer=_dgm_outer
        old_validate=_DGM_VALIDATE
        def gate(folder,baseline):
            if Path(folder).resolve().is_relative_to((work/'optimizer/candidates').resolve()):return b['validate'](folder)
            return old_validate(folder,baseline)
        native.validate=gate
    return module


def run(name,cfg,instances,work,b):
    return build_native(name,cfg,instances,work,b).run(name,cfg,instances,work,b)
