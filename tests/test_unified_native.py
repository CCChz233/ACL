"""Native one-round contracts with synthetic callbacks; zero API/Docker work."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from acl_frameworks.common import ROOT,read
from acl_unified import common
from acl_unified.protocol import H0,FILES,CONFIG


@pytest.fixture
def setup(tmp_path,monkeypatch):
    from acl_rsi.settings import load_settings,load_instances
    cfg=load_settings(CONFIG)
    cfg['evolve_ids']=cfg['protocol']['development_ids'];cfg['heldout_ids']=[]
    cfg['workspace']=str(tmp_path)
    cfg['config_path']=str(tmp_path/'config.json')
    (tmp_path/'config.json').write_text(json.dumps(cfg))
    instances=load_instances(cfg)
    old=ROOT/'experiments/runs/verified-mini-50-baseline-v2/runs/swe/jobs/base'
    def trial(iid):return old/iid/'trial-0'
    monkeypatch.setattr(common,'baseline_trial',trial)
    class Evaluator:
        def __init__(self,cfg,instances,work):self.work=Path(work)
        def __call__(self,name,harness,ids,**kw):
            if name not in ('h0','initial'):
                common.validate(harness)
                common.copy_harness(harness,self.work/'evaluations/candidate/harness')
                for iid in ids:
                    dest=self.work/'evaluations/candidate/trials'/iid
                    if not dest.exists():shutil.copytree(trial(iid),dest)
            return {i:float(read(trial(i)/'grade.json')['resolved']) for i in ids}
    monkeypatch.setattr(common,'Evaluator',Evaluator)
    return cfg,instances,tmp_path,trial,Evaluator


def test_gepa_native_supports_code_edit_spec_and_retains_complete_public_access(setup,monkeypatch):
    cfg,instances,work,trial,evaluator=setup
    import acl_unified.gepa as m
    monkeypatch.setattr(m,'baseline_trial',trial);monkeypatch.setattr(m,'Evaluator',evaluator)
    calls=[]
    def gateway(*a):
        def complete(**kw):
            calls.append(kw)
            change={'edits':[{'file':'agent.py','old':'class AgentConfig(BaseModel):','new':'# Synthetic fixture only\nclass AgentConfig(BaseModel):'}]}
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(tool_calls=None,
                content='```json\n'+json.dumps(change)+'\n```'))])
        return complete
    monkeypatch.setattr(m,'gateway',gateway)
    result=m.run(cfg,instances,work)
    assert len(calls)==1 and calls[0]['tools']
    assert (work/'evaluations/candidate/harness/agent.py').read_text()!= (H0/'agent.py').read_text()
    assert result['selected']=='h0'
    exported=read(work/'optimizer/snapshot.json')['tasks']
    assert {r['task_id'] for r in exported}==set(cfg['evolve_ids'])


def test_dgm_native_uses_only_development_tasks_and_no_old_harness_candidate(setup,monkeypatch):
    cfg,instances,work,trial,evaluator=setup
    import acl_unified.dgm as m
    monkeypatch.setattr(m.native_adapter,'export_baseline',m.native_adapter.export_baseline)
    monkeypatch.setattr(m.runtime,'SCOPE',m.runtime.SCOPE)
    monkeypatch.setattr(m,'baseline_trial',trial);monkeypatch.setattr(m,'Evaluator',evaluator)
    def edit(self,context):
        p=context['candidate_harness']/'agent.py';p.write_text(p.read_text()+'\n# Synthetic fixture.\n')
    monkeypatch.setattr(m.runtime.DGMProposer,'__call__',edit)
    result=m.run(cfg,instances,work)
    assert result['state']['archive']==['initial','node_0000']
    assert result['selected']=='h0'
    history=work/'optimizer/history/dgm-archive/initial/predictions/trial-0'
    assert {p.stem for p in history.glob('*.json')}==set(cfg['evolve_ids'])


def test_meta_native_one_candidate_validation_and_frontier(setup,monkeypatch):
    cfg,instances,work,trial,evaluator=setup
    import acl_unified.meta as m
    monkeypatch.setattr(m,'Evaluator',evaluator)
    class Proposer:
        def __init__(self,public,gateway):self.public=public
        def __call__(self,prompt,iteration):
            folder=common.copy_harness(H0,self.public/'candidates/h1/harness')
            p=folder/'agent.py';p.write_text(p.read_text()+'\n# Synthetic fixture\n')
            return [{'name':'h1','hypothesis':'fixture','changes':'comment'}]
    monkeypatch.setattr(m,'DeepSeekFileProposer',Proposer);monkeypatch.setattr(m,'gateway',lambda *a:None)
    result=m.run(cfg,instances,work)
    assert result['selected']=='h0'
    assert (work/'evaluations/candidate/harness').exists()


def test_rrsi_native_diagnosis_proposal_critic_and_selection(setup,monkeypatch):
    cfg,instances,work,trial,evaluator=setup
    import acl_unified.rrsi as m
    import importlib
    for role in ('analyst','digester','propose','critic'):
        native=importlib.import_module('rrsi.'+role)
        monkeypatch.setattr(native,'generate',native.generate)
        if role=='propose':monkeypatch.setattr(native,'SYSTEM_TMPL',native.SYSTEM_TMPL)
        if role=='digester':
            monkeypatch.setattr(native,'subprocess',native.subprocess)
            monkeypatch.setattr(native,'_safe',native._safe)
    monkeypatch.setattr(m,'baseline_trial',trial);monkeypatch.setattr(m,'Evaluator',evaluator)
    counters={}
    def fake_generate(cfg,work,role):
        def generate(*a,**kw):
            counters[role]=counters.get(role,0)+1
            if role=='analyst':return json.dumps({'action':'report','failure_modes':[],'capability_gaps':[],'success_habits':[]})
            if role=='critic':return json.dumps({'verdict':'accept','reasons':[],'risk_notes':[]})
            if role=='propose' and counters[role]==1:
                return json.dumps({'action':'edit_file','path':'agent.py','old':'class AgentConfig(BaseModel):',
                    'new':'# Synthetic fixture\nclass AgentConfig(BaseModel):'})
            return json.dumps({'action':'done','summary':'offline fixture','edits':[{'id':'C1','component':'prompt',
                'hypothesis':'offline fixture','targets_mode':'fixture','predicted_affected':[cfg['evolve_ids'][0]],
                'retroactive_check':'offline fixture'}]})
        return generate
    monkeypatch.setattr(m,'rrsi_generate',fake_generate)
    result=m.run(cfg,instances,work)
    assert counters=={'analyst':1,'propose':2,'critic':1}
    assert result['selected']=='h0'
    assert (work/'evaluations/candidate/harness').exists()


def test_hf_versioned_boundary_binds_fresh_baseline_four_task_split(setup):
    cfg,instances,work,trial,evaluator=setup
    from acl_unified.harnessfix import adapted_module
    module=adapted_module(cfg,work)
    assert module.IDS[:2]==cfg['protocol']['hf_train_ids']
    assert module.IDS[2:]==cfg['protocol']['hf_selection_ids']
    assert module.export_baseline is common.export
    assert module.Evaluator is evaluator
    source=(work/'adapted-hf-boundary.py').read_text()
    assert 'IDS[:1]' not in source and 'IDS[1:]' not in source


def test_nomination_is_frozen_before_report_and_not_changed_by_bad_report(setup,monkeypatch):
    cfg,instances,work,trial,evaluator=setup
    import acl_unified.framework as m
    folder=common.copy_harness(H0,work/'evaluations/candidate/harness')
    p=folder/'agent.py';p.write_text(p.read_text()+'\n# Synthetic fixture\n')
    for iid in cfg['evolve_ids']:
        shutil.copytree(trial(iid),folder.parent/'trials'/iid)
    class ReportEvaluator:
        def __init__(self,*args):pass
        def __call__(self,name,harness,ids,report=False):
            assert report and (work/'nomination.json').exists()
            assert read(work/'nomination.json')['selected']=='candidate'
            assert set(ids)==set(cfg['protocol']['report_ids'])
            return {i:0.0 for i in ids}
    monkeypatch.setattr(common,'Evaluator',ReportEvaluator)
    result=m.finish_report(cfg,instances,work,{'selected':'candidate'})
    assert result['selected']=='candidate' and sum(result['candidate_report_scores'].values())==0
    assert read(work/'nomination.json')['selected']=='candidate'


def test_rrsi_critic_call_uses_recorded_native_tool_protocol(monkeypatch):
    import acl_unified.provider as m
    seen=[]
    def make_gateway(*a):
        def complete(**kw):
            seen.append(kw)
            function=SimpleNamespace(arguments='{"verdict":"accept","reasons":[],"risk_notes":[]}')
            message=SimpleNamespace(tool_calls=[SimpleNamespace(function=function)],content=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        return complete
    monkeypatch.setattr(m,'gateway',make_gateway)
    output=m.rrsi_generate({'model':'deepseek-flash'},None,'critic')('prompt',system='Review',json_only=True,model='deepseek-flash')
    assert json.loads(output)['verdict']=='accept'
    assert seen[0]['tools'][0]['function']['name']=='submit_rrsi_action'
    assert seen[0]['tool_choice']['function']['name']=='submit_rrsi_action'
