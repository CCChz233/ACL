import hashlib
import json
from pathlib import Path
import yaml
from jinja2 import Environment, nodes
from acl_rsi.settings import ROOT, write_json

BASE_CONFIG = ROOT / 'configs/terminal-pilot-v1.json'
CONFIG = ROOT / 'configs/terminal-round1.json'
BASE_WORK = ROOT / 'work/terminal-pilot-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def harness_config(cfg):
    return {key:cfg[key] for key in ('agent','templates')}


def validate_harness(path, task_ids=()):
    text=Path(path).read_text()
    if len(text)>32000:
        raise ValueError('Harness text exceeds 32000 characters')
    data=yaml.safe_load(text)
    if not isinstance(data,dict) or set(data)!={'agent','templates'}:
        raise ValueError('Only agent/templates may change')
    keys={'agent':{'system_template','instance_template'},
          'templates':{'observation_template','format_error_template'}}
    for section, expected in keys.items():
        if not isinstance(data[section],dict) or set(data[section])!=expected:
            raise ValueError(f'Invalid {section} keys; budgets and loop stay frozen')
        for value in data[section].values():
            if not isinstance(value,str) or not value.strip():
                raise ValueError('Templates must be nonempty strings')
            tree=Environment().parse(value)
            if any(isinstance(n,(nodes.Call,nodes.Import,nodes.FromImport,nodes.Include,nodes.Extends))
                   for n in tree.find_all(nodes.Node)):
                raise ValueError('Executable template constructs are prohibited')
            if '__' in value or any(isinstance(n,nodes.Filter) and n.name=='attr' for n in tree.find_all(nodes.Node)):
                raise ValueError('Template introspection is prohibited')
            if any(i in value for i in task_ids):
                raise ValueError('Task identifier in reusable harness')
    if '{{task}}' not in data['agent']['instance_template'].replace(' ',''):
        raise ValueError('Public task must remain in instance template')
    return data


def load_cfg():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=False)
    cfg=read(CONFIG)
    cfg['workspace']=str(ROOT/cfg['workspace'])
    cfg['config_path']=str(CONFIG)
    cfg['config_sha256']=sha(CONFIG)
    return cfg


def verify_baseline():
    for name,digest in read(BASE_WORK/'runtime-lock.json').items():
        if sha(ROOT/name)!=digest:
            raise ValueError(f'Baseline runtime changed: {name}')
    baseline=read(BASE_CONFIG)
    for task in baseline['tasks']:
        for name,digest in task['files'].items():
            if sha(ROOT/'repos/terminal-bench-2-1/tasks'/task['id']/name)!=digest:
                raise ValueError('Task file changed')
    return baseline
