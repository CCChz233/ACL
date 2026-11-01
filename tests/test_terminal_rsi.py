import json
import sys
from pathlib import Path
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'repos/rrsi'))
from acl_terminal_rsi.common import read,BASE_CONFIG,validate_harness,harness_config,verify_baseline
from acl_terminal_rsi.domain import TerminalDomain


def test_harness_validation_allows_seed_and_rejects_execution_or_budget(tmp_path):
    base=read(BASE_CONFIG);path=tmp_path/'terminal.yaml'
    data=harness_config(base);path.write_text(yaml.safe_dump(data))
    assert validate_harness(path)==data
    bad={**data,'target':{'max_calls':999}};path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError,match='Only'): validate_harness(path)
    bad=json.loads(json.dumps(data));bad['agent']['instance_template']+=' {{ cycler.__init__() }}'
    path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError): validate_harness(path)
    bad=json.loads(json.dumps(data));bad['agent']['instance_template']+=' make-mips-interpreter'
    path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError,match='identifier'):validate_harness(path,['make-mips-interpreter'])


def test_trace_feedback_excludes_verifier_and_keeps_format_errors(tmp_path):
    cfg=read(BASE_CONFIG);domain=TerminalDomain(cfg)
    path=tmp_path/'agent';path.mkdir()
    (tmp_path/'result.json').write_text(json.dumps({'verifier_result':{'rewards':{'reward':0}},'private_expected':'SECRET_EXPECTED_123'}))
    (tmp_path/'verifier').mkdir();(tmp_path/'verifier/test-stdout.txt').write_text('SECRET_EXPECTED_123')
    (path/'worker.json').write_text(json.dumps({'exit_status':'RepeatedFormatError','usage':{'calls':3}}))
    (path/'trajectory.json').write_text(json.dumps({'messages':[
      {'role':'system','content':'system'}, {'role':'user','content':'PUBLIC_INSTRUCTION'},
      {'role':'user','content':'Your response reached output token limit finish_reason=length'},
      {'role':'exit','content':'RepeatedFormatError'}]}))
    domain.trial_dir=lambda *args:tmp_path
    rec=domain.load_trial(tmp_path,'base','example',0)
    text=domain.render_trace(rec,True)
    assert 'SECRET_EXPECTED_123' not in json.dumps(rec)+text
    assert 'PUBLIC_INSTRUCTION' in text and 'finish_reason=length' in text
    assert rec['score']==0


def test_original_baseline_remains_frozen():
    cfg=verify_baseline()
    assert len(cfg['tasks'])==12
    assert cfg['target']=={'max_calls':50,'max_tokens':1000000,'max_output_tokens':4096,'command_seconds':60}
