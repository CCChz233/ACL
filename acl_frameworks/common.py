import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'configs/frameworks/registry.json'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(name):
    cfg = read(REGISTRY)['frameworks'][name]
    source = ROOT / cfg['source']
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != cfg['revision']:
        raise ValueError(f'{name}: pinned revision changed')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True):
        raise ValueError(f'{name}: upstream tracked files changed')
    for relative, expected in cfg['files'].items():
        if sha(source / relative) != expected:
            raise ValueError(f'{name}: source hash mismatch: {relative}')
    return cfg, source


def load_module(name, relative, module_name):
    _, source = verify(name)
    # Native modules use sibling imports; load in a dedicated process for each
    # framework, never import a different framework under the same module alias.
    sys.path.insert(0, str(source))
    sys.path.insert(0, str((source / relative).parent))
    spec = importlib.util.spec_from_file_location(module_name, source / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
