"""Load the unchanged DGM outer loop, substituting only self-improvement boundary."""
from contextlib import contextmanager
import importlib.util
import random
import subprocess
import sys
from types import ModuleType

from acl_frameworks.common import ROOT, read, sha

LOCK = ROOT / 'configs/frameworks/dgm.json'


def verify():
    cfg = read(LOCK)
    root = ROOT / cfg['source']
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != cfg['revision']:
        raise ValueError('DGM source revision differs')
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True):
        raise ValueError('DGM tracked source changed')
    for file, digest in cfg['files'].items():
        if sha(root / file) != digest:
            raise ValueError('DGM source hash differs: '+file)
    return root


@contextmanager
def outer(self_improve, seed=17):
    root = verify()
    prefixes = ('utils', 'prompts', 'self_improve_step')
    def relevant(name):
        return any(name == prefix or name.startswith(prefix+'.') for prefix in prefixes)
    saved = {k: v for k, v in sys.modules.items() if relevant(k)}
    old_path = list(sys.path)
    try:
        for name in saved:
            del sys.modules[name]
        for name in ('utils', 'prompts'):
            package = ModuleType(name)
            package.__path__ = [str(root / name)]
            sys.modules[name] = package
        boundary = ModuleType('self_improve_step')
        boundary.self_improve = self_improve
        sys.modules['self_improve_step'] = boundary
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location('acl_dgm_native_outer', root / 'DGM_outer.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Local RNG preserves native probabilities without mutating global state.
        module.random = random.Random(seed)
        yield module
    finally:
        sys.path[:] = old_path
        for name in list(sys.modules):
            if relevant(name):
                del sys.modules[name]
        sys.modules.update(saved)
