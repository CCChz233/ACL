"""User reduction: zero paid no-update retests, retained-parent chain, strict cap."""
from pathlib import Path
import pytest
from acl_frameworks.common import read
from acl_unified import common
from acl_unified.protocol import H0,CONFIG
from acl_rsi.settings import load_settings,load_instances,write_json
from acl_rsi.deepseek import BudgetExceeded
from acl_gepa_swe.feedback import EvaluationUnavailable
from acl_multiround.runtime import initial_state
from acl_multiround_v2 import step,runtime


@pytest.fixture
def setup(tmp_path,monkeypatch):
    cfg=load_settings(CONFIG);ids=cfg['protocol']['all_task_ids']
    cfg['evolve_ids']=ids;cfg['heldout_ids']=[]
    cfg['protocol'].update(development_ids=ids,report_ids=[],rounds=2)
    cfg['workspace']=str(tmp_path)
    parent=initial_state(ids)
    monkeypatch.setattr(step,'verify',lambda:None);monkeypatch.setattr(common,'preflight',lambda:None)
    monkeypatch.setattr(step,'settings',lambda *a:cfg);monkeypatch.setattr(step,'round_dir',lambda *a:tmp_path)
    monkeypatch.setattr(step,'parent_state',lambda *a:parent)
    paid=[]
    class Evaluator:
        def __init__(self,*a):pass
        def __call__(self,name,harness,ids):paid.append(name);return {i:parent['scores'][i] for i in ids}
    bindings={'validate':lambda *a,**kw:None,'Evaluator':Evaluator}
    monkeypatch.setattr(step,'bind',lambda *a:bindings)
    return cfg,tmp_path,parent,bindings,paid


def test_budget_exhaustion_reuses_parent_without_evaluation(setup,monkeypatch):
    cfg,work,parent,b,paid=setup
    def fail(*a):raise BudgetExceeded('call_limit',{})
    monkeypatch.setattr(step.adapters,'run',fail)
    assert step.execute('harnessfix',1)==0
    r=read(work/'result.json')
    assert not paid and r['round_scores'] is None and r['round_resolved'] is None
    assert r['candidate_scores'] is None and r['score_reused']
    assert r['evaluated_kind']=='unchanged_parent_reused'
    assert r['next_parent']['scores']==parent['scores']
    assert r['next_parent']['trials']==parent['trials']
    assert not list(work.glob('evaluations/*/trials/*/worker-attempt.json'))


def test_invalid_unstarted_candidate_is_not_evaluated(setup,monkeypatch):
    cfg,work,parent,b,paid=setup
    def propose(*a):
        common.copy_harness(H0,work/'evaluations/candidate/harness');return {'selected':'candidate'}
    def invalid(*a,**kw):raise common.InvalidCandidate('fixture malformed template')
    b['validate']=invalid;monkeypatch.setattr(step.adapters,'run',propose)
    assert step.execute('dgm',1)==0
    r=read(work/'result.json')
    assert not paid and r['proposal_status']=='invalid_candidate' and r['native_selected']=='parent'
    assert r['next_parent']['harness_sha256']==parent['harness_sha256']


def test_started_invalid_candidate_is_not_masked_by_parent_reuse(setup,monkeypatch):
    cfg,work,parent,b,paid=setup
    def propose(*a):
        common.copy_harness(H0,work/'evaluations/candidate/harness')
        t=work/'evaluations/candidate/trials'/cfg['evolve_ids'][0]
        write_json(t/'worker-attempt.json',{'started_at':1});write_json(t/'worker.json',{'exit_status':'Submitted'})
        return {'selected':'h0'}
    def invalid(*a,**kw):raise common.InvalidCandidate('fixture changed after start')
    b['validate']=invalid;monkeypatch.setattr(step.adapters,'run',propose)
    assert step.execute('gepa',1)==2
    r=read(work/'result.json')
    assert r['next_parent'] is None and r['round_scores'] is None and not paid


def test_valid_rejected_candidate_reports_raw_score_and_keeps_parent(setup,monkeypatch):
    cfg,work,parent,b,paid=setup
    def propose(*a):
        folder=common.copy_harness(H0,work/'evaluations/candidate/harness')
        p=folder/'agent.py';p.write_text(p.read_text().replace('class DefaultAgent:','class DefaultAgent:\n    fixture = True'))
        return {'selected':'h0'}
    monkeypatch.setattr(step.adapters,'run',propose)
    assert step.execute('meta-harness',1)==0
    r=read(work/'result.json')
    assert paid==['candidate'] and len(r['round_scores'])==10 and not r['score_reused']
    assert r['retained_score_reused'] and r['next_parent']['harness_sha256']==parent['harness_sha256']


def test_global_cap_reserves_complete_ten_including_legacy(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'worker_count',lambda:91)
    with pytest.raises(EvaluationUnavailable):runtime.reserve_ten(tmp_path)
    assert read(tmp_path/'global-budget-stop.json')['used']==91
    assert not (tmp_path/'evaluation-budget-reservation.json').exists()
    monkeypatch.setattr(runtime,'worker_count',lambda:90)
    runtime.reserve_ten(tmp_path)
    assert read(tmp_path/'evaluation-budget-reservation.json')['global_limit']==100


def test_no_update_second_round_keeps_original_measurement_source(tmp_path,monkeypatch):
    cfg=load_settings(CONFIG);ids=cfg['protocol']['all_task_ids'];state=initial_state(ids)
    first=tmp_path/'round-1';first.mkdir()
    write_json(first/'result.json',{'next_parent':state,'evaluated_kind':'unchanged_parent_reused'})
    monkeypatch.setattr(runtime,'round_dir',lambda name,index:tmp_path/f'round-{index}')
    next_state=runtime.parent_state('method',2,ids)
    assert next_state['source_round']==0 and next_state['trials']==state['trials']
