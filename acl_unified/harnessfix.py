"""Versioned boundary adaptation of the previously verified native HF runner.

Execute its saved source under a separate module name. Exact replacements are
limited to split cardinality and source-copy hygiene; callbacks bind fresh H0,
unified validation and the common budget. No historical file is modified.
"""
import importlib.util
from pathlib import Path
import sys

from acl_frameworks import live
from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import write_json
from . import common
from .protocol import WORK,H0,SCOPE
from .provider import gateway


def adapted_module(cfg,work):
    source=Path(live.__file__)
    text=source.read_text()
    replacements={
        'IDS[:1]':'IDS[:2]', 'IDS[1:]':'IDS[2:]',
        "ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.env')":
        "ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.env', 'data')",
        "folder.mkdir(exist_ok=True)":"folder.mkdir(parents=True, exist_ok=True)",
    }
    changes={}
    for old,new in replacements.items():
        count=text.count(old)
        if not count:raise ValueError('HF boundary anchor changed')
        text=text.replace(old,new);changes[old]=count
    module=importlib.util.module_from_spec(importlib.util.spec_from_loader('acl_frameworks.acl_unified_hf_boundary',loader=None))
    module.__package__='acl_frameworks';module.__file__=str(source)
    exec(compile(text,str(source),'exec'),module.__dict__)
    p=cfg['protocol']
    module.IDS=p['hf_train_ids']+p['hf_selection_ids']
    module.BASE=WORK/'baseline';module.HARNESS=H0
    module.SCOPE=SCOPE+'\nFull checkout editable paths: '+live.AGENT_FILE+' and '+live.YAML_FILE+'.'
    module.export_baseline=common.export
    module.Evaluator=common.Evaluator
    module.gateway=gateway
    write_json(work/'hf-boundary-adaptation.json',{'original_sha256':sha(source),'replacements':changes,
        'training_ids':p['hf_train_ids'],'selection_ids':p['hf_selection_ids'],
        'fresh_baseline':str(module.BASE),'original_source_unchanged':True})
    (work/'adapted-hf-boundary.py').write_text(text)
    return module


def run(cfg,instances,work):
    module=adapted_module(cfg,work)
    return module.hf_run(cfg,instances,work)
