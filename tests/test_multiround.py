"""Longitudinal invariants with public local fixtures; no API or Docker calls."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
from acl_frameworks.common import ROOT,read
from acl_unified import common
from acl_unified.protocol import CONFIG,H0
from acl_rsi.settings import load_settings,load_instances
from acl_multiround import runtime,adapters


@pytest.fixture
def context(tmp_path,monkeypatch):
    cfg=load_settings(CONFIG)
    ids=cfg['protocol']['all_task_ids']
    cfg['protocol'].update(development_ids=ids,report_ids=[],hf_train_ids=ids,hf_selection_ids=ids)
    cfg['evolve_ids']=ids;cfg['heldout_ids']=[];cfg['workspace']=str(tmp_path/'round-2')
    work=Path(cfg['workspace']);work.mkdir()
    cfg['config_path']=str(work/'config.json');(work/'config.json').write_text(json.dumps(cfg))
    parent=runtime.initial_state(ids)
    folder=common.copy_harness(H0,tmp_path/'evolved-parent')
    code=folder/'agent.py'
    code.write_text(code.read_text().replace('class DefaultAgent:', 'class DefaultAgent:\n    prior_round_fixture = True'))
    parent.update(harness=str(folder),harness_sha256=common.fingerprint(folder),source_round=1)
    instances=load_instances(cfg)
    for key in ('validate','export','baseline_trial','Evaluator'):
        monkeypatch.setattr(common,key,getattr(common,key))
    monkeypatch.setattr(common,'preflight',lambda:None)
    def fake_trial(self,iid,destination):
        dest=destination/'trials'/iid
        if not dest.exists():shutil.copytree(Path(parent['trials'][iid]),dest)
        return 0
    monkeypatch.setattr(runtime.SWEExecutor,'trial',fake_trial)
    bindings=runtime.bind(cfg,instances,work,parent)
    return cfg,instances,work,parent,bindings


def test_full_ten_export_uses_evolved_parent_not_h0(context):
    cfg,instances,work,parent,b=context
    ws=b['export'](work/'optimizer',cfg['evolve_ids'])
    data=read(ws.root/'snapshot.json')
    assert len(data['tasks'])==10 and data['source_round']==1
    assert 'prior_round_fixture' in (ws.root/'harness/agent.py').read_text()
    assert data['harness']==parent['harness_sha256']
    for feedback in (ws.root/'history').glob('*/feedback.json'):
        assert not {'patch','test_patch','FAIL_TO_PASS','PASS_TO_PASS'} & read(feedback).keys()


def test_same_parent_and_comment_only_are_not_new_candidates(context):
    cfg,instances,work,parent,b=context
    with pytest.raises(common.InvalidCandidate):b['validate'](Path(parent['harness']))
    child=common.copy_harness(Path(parent['harness']),work/'child')
    p=child/'agent.py';p.write_text(p.read_text()+'\n# Just formatting fixture\n')
    with pytest.raises(common.InvalidCandidate):b['validate'](child)


def test_parent_retest_covers_all_ten_and_keeps_same_harness(context):
    cfg,instances,work,parent,b=context
    folder,scores=runtime.retest_parent(cfg,instances,work,parent)
    assert len(scores)==10 and scores==parent['scores']
    assert common.fingerprint(folder/'harness')==parent['harness_sha256']
    assert len(list((folder/'trials').glob('*/grade.json')))==10


def test_harnessfix_both_native_callbacks_use_full_ten_current_parent(context):
    cfg,instances,work,parent,b=context
    m=adapters.harnessfix_module(cfg,instances,work,b)
    assert m.IDS==cfg['evolve_ids'] and len(m.IDS)==10
    assert m.HARNESS==Path(parent['harness'])
    for iid in cfg['evolve_ids']:
        assert (m.BASE/'runs/swe/jobs/base'/iid/'trial-0').resolve()==Path(parent['trials'][iid]).resolve()
    source=(work/'adapted-hf-boundary.py').read_text()
    assert 'IDS[:1]' not in source and 'IDS[1:]' not in source
    assert m.Evaluator is b['Evaluator'] and m.export_baseline is b['export']


def test_gepa_native_step_materializes_relative_to_evolved_parent(context,monkeypatch):
    cfg,instances,work,parent,b=context
    module=adapters.load_step('gepa',b,work)
    calls=[]
    def gateway(*a):
        def complete(**kw):
            calls.append(kw)
            edit={'edits':[{'file':'agent.py','old':'prior_round_fixture = True','new':'prior_round_fixture = False'}]}
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(tool_calls=None,content='```json\n'+json.dumps(edit)+'\n```'))])
        return complete
    monkeypatch.setattr(module,'gateway',gateway)
    result=module.run(cfg,instances,work)
    assert len(calls)==1
    assert len(list((work/'evaluations/candidate/trials').glob('*/grade.json')))==10
    assert 'prior_round_fixture = False' in (work/'evaluations/candidate/harness/agent.py').read_text()
    assert 'All TEN' in module.SCOPE


def test_meta_native_step_receives_full_ten_and_evolved_parent(context,monkeypatch):
    cfg,instances,work,parent,b=context
    module=adapters.load_step('meta',b,work)
    class Proposer:
        def __init__(self,public,*a):self.public=public
        def __call__(self,*a):
            child=common.copy_harness(Path(parent['harness']),self.public/'candidates/h1/harness')
            p=child/'agent.py';p.write_text(p.read_text().replace('prior_round_fixture = True','prior_round_fixture = False'))
            return [{'name':'h1','hypothesis':'offline fixture','changes':'fixture'}]
    monkeypatch.setattr(module,'DeepSeekFileProposer',Proposer);monkeypatch.setattr(module,'gateway',lambda *a:None)
    result=module.run(cfg,instances,work)
    assert len(list((work/'evaluations/candidate/trials').glob('*/grade.json')))==10
    assert read(work/'optimizer/snapshot.json')['source_round']==1


def test_next_round_loads_previous_retained_parent_only(tmp_path,monkeypatch):
    ids=read(CONFIG)['protocol']['all_task_ids'];state=runtime.initial_state(ids)
    root=tmp_path/'method';(root/'round-1').mkdir(parents=True)
    (root/'round-1/result.json').write_text(json.dumps({'next_parent':state,'candidate_scores':{i:0 for i in ids}}))
    monkeypatch.setattr(runtime,'round_dir',lambda n,r:root/f'round-{r}')
    assert runtime.parent_state('method',2,ids)==state
    (root/'round-1/result.json').write_text(json.dumps({'next_parent':None}))
    with pytest.raises((TypeError,ValueError)):runtime.parent_state('method',2,ids)


def test_budget_failure_retests_parent_ten_without_claiming_candidate(context,monkeypatch):
    cfg,instances,work,parent,b=context
    from acl_multiround import step
    from acl_rsi.deepseek import BudgetExceeded
    monkeypatch.setattr(step,'verify',lambda:None)
    monkeypatch.setattr(step,'settings',lambda *a:cfg)
    monkeypatch.setattr(step,'round_dir',lambda *a:work)
    monkeypatch.setattr(step,'parent_state',lambda *a:parent)
    def fail(*a):raise BudgetExceeded('call_limit',{})
    monkeypatch.setattr(adapters,'run',fail)
    assert step.execute('rrsi',2)==0
    result=read(work/'result.json')
    assert result['evaluated_kind']=='unchanged_parent_retest'
    assert result['candidate_scores'] is None
    assert result['proposal_status']=='search_budget_exhausted'
    assert result['next_parent']['harness_sha256']==parent['harness_sha256']
    assert len(result['round_scores'])==10


def test_rejected_valid_candidate_does_not_replace_retained_parent(context,monkeypatch):
    cfg,instances,work,parent,b=context
    from acl_multiround import step
    monkeypatch.setattr(step,'verify',lambda:None);monkeypatch.setattr(step,'settings',lambda *a:cfg)
    monkeypatch.setattr(step,'round_dir',lambda *a:work);monkeypatch.setattr(step,'parent_state',lambda *a:parent)
    def propose(*a):
        folder=common.copy_harness(Path(parent['harness']),work/'evaluations/candidate/harness')
        p=folder/'agent.py';p.write_text(p.read_text().replace('prior_round_fixture = True','prior_round_fixture = False'))
        return {'selected':'h0'}
    monkeypatch.setattr(adapters,'run',propose)
    assert step.execute('gepa',2)==0
    result=read(work/'result.json')
    assert result['evaluated_kind']=='candidate' and len(result['candidate_scores'])==10
    assert result['native_selected']=='parent' and result['retained_score_reused']
    assert result['next_parent']['harness_sha256']==parent['harness_sha256']


def test_dgm_predeclared_empty_list_fix_preserves_parent_seed(context,monkeypatch):
    cfg,instances,work,parent,b=context
    import acl_dgm.runtime as native_runtime
    import acl_dgm.adapter as native_adapter
    monkeypatch.setattr(native_runtime,'SCOPE',native_runtime.SCOPE)
    monkeypatch.setattr(native_adapter,'outer',native_adapter.outer)
    monkeypatch.setattr(native_adapter,'export_baseline',native_adapter.export_baseline)
    def edit(self,context):
        p=context['candidate_harness']/'agent.py'
        p.write_text(p.read_text().replace('prior_round_fixture = True','prior_round_fixture = False'))
    monkeypatch.setattr(native_runtime.DGMProposer,'__call__',edit)
    result=adapters.dgm(cfg,instances,work,b)
    assert len(list((work/'evaluations/candidate/trials').glob('*/grade.json')))==10
    assert (work/'dgm-choose-fixed.py').exists()
    assert result['state']['archive']==['initial','node_0000']


def test_rrsi_seeds_native_repo_with_previous_parent(context,monkeypatch):
    cfg,instances,work,parent,b=context
    import acl_unified.provider as provider
    counters={}
    def generate(settings,directory,role):
        def call(*a,**kw):
            counters[role]=counters.get(role,0)+1
            if role=='analyst':return json.dumps({'action':'report','failure_modes':[],'capability_gaps':[],'success_habits':[]})
            if role=='critic':return json.dumps({'verdict':'accept','reasons':[],'risk_notes':[]})
            if role=='propose' and counters[role]==1:return json.dumps({'action':'edit_file','path':'agent.py','old':'prior_round_fixture = True','new':'prior_round_fixture = False'})
            return json.dumps({'action':'done','summary':'offline fixture','edits':[{'id':'C1','component':'prompt','hypothesis':'fixture','targets_mode':'fixture','predicted_affected':[cfg['evolve_ids'][0]],'retroactive_check':'fixture'}]})
        return call
    monkeypatch.setattr(provider,'rrsi_generate',generate)
    for role in ('analyst','digester','propose','critic'):
        import importlib
        m=importlib.import_module('rrsi.'+role)
        monkeypatch.setattr(m,'generate',m.generate)
        if role=='propose':monkeypatch.setattr(m,'SYSTEM_TMPL',m.SYSTEM_TMPL)
        if role=='digester':
            monkeypatch.setattr(m,'subprocess',m.subprocess);monkeypatch.setattr(m,'_safe',m._safe)
    result=adapters.rrsi(cfg,instances,work,b)
    assert len(list((work/'evaluations/candidate/trials').glob('*/grade.json')))==10
    assert 'prior_round_fixture' in (work/'repo/domains/swe/harness/agent.py').read_text()
