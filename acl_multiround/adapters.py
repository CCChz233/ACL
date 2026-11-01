"""Versioned one-step adapters, seeded with the previous retained Harness."""
import contextlib
import importlib.util
import inspect
from pathlib import Path
import sys
from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import write_json
from acl_unified import common
from acl_unified.provider import gateway
from .protocol import SCOPE,FILES


def load_step(name,bindings,work):
    source=ROOT/'acl_unified'/f'{name}.py'
    module=importlib.util.module_from_spec(importlib.util.spec_from_loader('acl_unified._full10_'+name,loader=None))
    module.__package__='acl_unified';module.__file__=str(source)
    exec(compile(source.read_text(),str(source),'exec'),module.__dict__)
    for key in ('validate','export','Evaluator','baseline_trial'):setattr(module,key,bindings[key])
    module.H0=bindings['parent'];module.SCOPE=SCOPE
    write_json(work/f'{name}-adapter-source.json',{'source':str(source.relative_to(ROOT)),
        'sha256':sha(source),'binding':'current retained parent, all ten tasks, per-round meter; process local',
        'native_long_run_scheduler':'one native step reinitialized per outer round; prior attempt summaries remain public'})
    return module


def harnessfix_module(cfg,instances,work,bindings):
    from acl_frameworks import live
    source=Path(live.__file__);text=source.read_text()
    replacements={'IDS[:1]':'IDS','IDS[1:]':'IDS',
        "ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.env')":
        "ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.env', 'data')",
        'folder.mkdir(exist_ok=True)':'folder.mkdir(parents=True, exist_ok=True)'}
    for old,new in replacements.items():
        if not text.count(old):raise ValueError('HF source anchor changed')
        text=text.replace(old,new)
    module=importlib.util.module_from_spec(importlib.util.spec_from_loader('acl_frameworks._full10_hf',loader=None))
    module.__package__='acl_frameworks';module.__file__=str(source)
    exec(compile(text,str(source),'exec'),module.__dict__)
    ids=cfg['protocol']['all_task_ids']
    alias=work/'parent-evidence'
    for iid in ids:
        link=alias/'runs/swe/jobs/base'/iid/'trial-0'
        link.parent.mkdir(parents=True,exist_ok=True)
        link.symlink_to(bindings['baseline_trial'](iid))
    module.IDS=ids;module.BASE=alias;module.HARNESS=bindings['parent']
    module.SCOPE=SCOPE+'\nFull editable checkout paths: '+live.AGENT_FILE+' and '+live.YAML_FILE+'.'
    module.export_baseline=bindings['export'];module.Evaluator=bindings['Evaluator'];module.gateway=gateway
    (work/'adapted-hf-boundary.py').write_text(text)
    write_json(work/'hf-boundary-adaptation.json',{'original_sha256':sha(source),'replacements':replacements,
        'train_ids':ids,'selection_ids':ids,'warning':'same all-ten feedback set, no heldout selection'})
    return module


def harnessfix(cfg,instances,work,bindings):
    module=harnessfix_module(cfg,instances,work,bindings)
    result=module.hf_run(cfg,instances,work)
    result['selected']='candidate' if result.get('promotion',{}).get('promoted') else 'h0'
    return result


def rrsi(cfg,instances,work,bindings):
    module=load_step('rrsi',bindings,work)
    original=module.make_run
    def make_run(settings):
        run=original(settings)
        folder=run.repo/'domains/swe/harness'
        common.copy_harness(bindings['parent'],folder)
        from acl_rsi.cli import git
        git(run.repo,'add','domains/swe/harness')
        if git(run.repo,'diff','--cached','--name-only'):
            git(run.repo,'commit','-m','Seed retained parent for longitudinal full10 step')
        previous=sorted(work.parent.glob('round-*/runs/swe/global_analysis.json'))
        previous=[p for p in previous if p.parent.parent.parent!=work]
        if previous:run.global_analysis.write_bytes(previous[-1].read_bytes())
        return run
    module.make_run=make_run
    return module.run(cfg,instances,work)


def dgm(cfg,instances,work,bindings):
    module=load_step('dgm',bindings,work)
    from acl_dgm import adapter
    original=adapter.outer
    before='''            if unresolved_ids == 0:
                continue
            entry_ids = unresolved_ids'''
    after='''            entry_ids = unresolved_ids or empty_ids
            if not entry_ids:
                continue'''
    @contextlib.contextmanager
    def fixed_outer(*args,**kwargs):
        with original(*args,**kwargs) as native:
            source=inspect.getsource(native.choose_selfimproves)
            if source.count(before)!=1:raise ValueError('DGM empty-list anchor changed')
            source=source.replace(before,after)
            namespace=dict(native.__dict__)
            exec(compile(source,str(work/'dgm-choose-fixed.py'),'exec'),namespace)
            native.choose_selfimproves=namespace['choose_selfimproves']
            (work/'dgm-choose-fixed.py').write_text(source)
            yield native
    adapter.outer=fixed_outer
    return module.run(cfg,instances,work)


def run(name,cfg,instances,work,bindings):
    if name=='harnessfix':return harnessfix(cfg,instances,work,bindings)
    if name=='rrsi':return rrsi(cfg,instances,work,bindings)
    if name=='dgm':return dgm(cfg,instances,work,bindings)
    return load_step('meta' if name=='meta-harness' else 'gepa',bindings,work).run(cfg,instances,work)
