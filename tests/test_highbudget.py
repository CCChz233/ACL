"""No API/Docker calls: real-change gate, model-authored repair, phase accounting."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
from acl_unified import common
from acl_unified.protocol import H0,CONFIG
from acl_rsi.settings import load_settings,write_json
from acl_multiround_v3.delivery import strict_validator,Delivery
from acl_multiround_v3 import provider,adapters


def test_real_change_gate_rejects_whitespace_and_parses_all_four_templates(tmp_path):
    check=strict_validator(common.validate,H0)
    p=common.copy_harness(H0,tmp_path/'candidate')
    with pytest.raises(common.InvalidCandidate):check(p)
    y=yaml.safe_load((p/'swebench.yaml').read_text())
    y['agent']['system_template']+='\n\n'
    (p/'swebench.yaml').write_text(yaml.safe_dump(y))
    with pytest.raises(common.InvalidCandidate):check(p)
    y['agent']['system_template']+='Verify the patch before submitting.'
    y['agent']['instance_template']='{% endif %}'
    (p/'swebench.yaml').write_text(yaml.safe_dump(y))
    with pytest.raises(common.InvalidCandidate):check(p)


def test_native_and_delivery_share_directory_but_leave_reserved_allowance(monkeypatch,tmp_path):
    seen=[]
    def original(cfg,work,role):
        seen.append((cfg['search']['max_calls'],cfg['search']['max_tokens'],work,role))
        def call(**kwargs):return role
        call.ledger=object();return call
    monkeypatch.setattr(provider,'original_gateway',original)
    cfg={'search':{'max_calls':400,'max_tokens':8000000},'protocol':{'native_call_cap':300,'native_token_cap':6000000}}
    meter=provider.gateway(cfg,tmp_path,'propose')
    assert meter()=='propose'
    with provider.delivery_phase():assert meter()=='propose_delivery'
    assert meter()=='propose'
    assert seen[0][:2]==(300,6000000) and seen[1][:2]==(400,8000000)
    assert seen[0][2]==seen[1][2]


class Message:
    def __init__(self,name,args):
        self.tool_calls=[SimpleNamespace(id='fixture',function=SimpleNamespace(name=name,arguments=json.dumps(args)))];self.content=None
    def model_dump(self,**kw):return {'role':'assistant','content':None,'tool_calls':[]}


def delivery_fixture(tmp_path,monkeypatch):
    import acl_multiround_v3.delivery as m
    cfg=load_settings(CONFIG);cfg['protocol'].update(native_call_cap=300,native_token_cap=6000000)
    p=common.copy_harness(H0,tmp_path/'native-artifact')
    original=yaml.safe_load((p/'swebench.yaml').read_text())
    fixed=json.loads(json.dumps(original));fixed['agent']['system_template']+='\nVerify the patch before submitting.'
    broken=json.loads(json.dumps(fixed));broken['model']['observation_template']='{% endif %}'
    (p/'swebench.yaml').write_text(yaml.safe_dump(broken))
    def export(public,ids):
        common.copy_harness(H0,public/'harness');write_json(public/'snapshot.json',{'fixture':True})
    b={'validate':strict_validator(common.validate,H0),'export':export}
    messages=[Message('Write',{'path':'candidates/native/harness/swebench.yaml','content':yaml.safe_dump(fixed)}),
        Message('Finish',{'candidates':[{'name':'native','hypothesis':'fixture','changes':'fix template'}]})]
    calls=[]
    def meter(*a):
        def call(**kw):
            calls.append(kw);return SimpleNamespace(choices=[SimpleNamespace(message=messages.pop(0))])
        return call
    monkeypatch.setattr(m,'gateway',meter)
    return Delivery(cfg,tmp_path,b),p,calls,broken


def test_existing_native_artifact_is_repaired_by_model_before_evaluation(tmp_path,monkeypatch):
    d,p,calls,broken=delivery_fixture(tmp_path,monkeypatch)
    d.ensure(p)
    assert len(calls)==2 and d.calls==1
    assert yaml.safe_load((p/'swebench.yaml').read_text())['model']['observation_template']!='{% endif %}'
    assert yaml.safe_load((tmp_path/'delivery/repair-1/before/swebench.yaml').read_text())==broken
    record=json.loads((tmp_path/'delivery/repair-1/record.json').read_text())
    assert record['model_only_edits'] and record['no_target_feedback_used']
    d.ensure(p);assert len(calls)==2


def test_no_repair_allowed_after_any_paid_task_starts(tmp_path,monkeypatch):
    d,p,calls,broken=delivery_fixture(tmp_path,monkeypatch)
    write_json(tmp_path/'evaluations/candidate/trials/task/worker-attempt.json',{'started_at':1})
    with pytest.raises(common.InvalidCandidate,match='after task execution'):d.ensure(p)
    assert not calls


def test_hf_native_step_limits_and_parent_binding_are_versioned(tmp_path):
    cfg=load_settings(CONFIG);cfg['protocol'].update(native_call_cap=300,native_token_cap=6000000)
    ids=cfg['protocol']['all_task_ids']
    b={'parent':H0,'baseline_trial':lambda i:Path('/tmp')/i,'export':lambda *a:None,
        'Evaluator':object,'validate':lambda *a,**kw:None,'delivery':SimpleNamespace(ensure=lambda *a,**kw:None)}
    m=adapters.build_native('harnessfix',cfg,{},tmp_path,b)
    hf=m.harnessfix_module(cfg,{},tmp_path,b)
    source=(tmp_path/'adapted-hf-boundary.py').read_text()
    assert 'agg.AGG_AGENT_STEP_LIMIT = 60' in source
    assert "20 if 'analysis' in file else 100" in source
    assert hf.HARNESS==H0 and hf.IDS==ids
    assert callable(hf.install_native_hf) and 'install_native_hf(module)' in source
    assert '400 search calls/8M tokens' in adapters.SCOPE
