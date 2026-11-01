import copy
import shutil

import pytest
import yaml

from acl_unified.protocol import H0,FILES,ROOT,split
from acl_unified.common import InvalidCandidate,validate,protocol_contract
from acl_frameworks.common import read


def fixture(tmp_path):
    for f in FILES:shutil.copy2(H0/f,tmp_path/f)
    return tmp_path


def test_stratified_split_is_deterministic_and_ignores_other_candidate_scores():
    s=read(ROOT/'experiments/runs/hard10-selection-v1/selection.json')
    a=split(s)
    for r in s['selected']:r['scores'][1:]=[1,1]
    assert split(s)==a
    assert len(a['development_ids'])==4 and len(a['report_ids'])==6
    assert set(a['hf_train_ids'])|set(a['hf_selection_ids'])==set(a['development_ids'])
    assert not set(a['development_ids'])&set(a['report_ids'])


def test_h0_tool_protocol_and_scope(tmp_path):
    folder=fixture(tmp_path)
    validate(folder,require_change=False)
    assert len(protocol_contract(folder))==4
    with pytest.raises(InvalidCandidate,match='No operation'):validate(folder)


def test_code_edits_allowed_but_budget_and_new_yaml_keys_rejected(tmp_path):
    folder=fixture(tmp_path)
    (folder/'agent.py').write_text((folder/'agent.py').read_text()+'\n# Generic fixture change.\n')
    validate(folder)
    old=yaml.safe_load((folder/'swebench.yaml').read_text())
    for key,value in [('step_limit',999),('confirm_before_submit',True)]:
        new=copy.deepcopy(old);new['agent'][key]=value
        (folder/'swebench.yaml').write_text(yaml.safe_dump(new))
        with pytest.raises(InvalidCandidate,match='YAML outside'):validate(folder)


def test_added_task_specific_rule_rejected(tmp_path):
    folder=fixture(tmp_path)
    (folder/'agent.py').write_text((folder/'agent.py').read_text()+'\n# django special rule\n')
    with pytest.raises(InvalidCandidate,match='Task-specific'):validate(folder)


def test_tool_interception_without_paired_response_rejected(tmp_path):
    folder=fixture(tmp_path)
    p=folder/'agent.py'
    s=p.read_text().replace('outputs = [self.env.execute(action) for action in message.get("extra", {}).get("actions", [])]',
        'return self.add_messages({"role":"user", "content":"review"})\n        outputs = []')
    assert s!=p.read_text();p.write_text(s)
    with pytest.raises(InvalidCandidate,match='pairing'):validate(folder)
