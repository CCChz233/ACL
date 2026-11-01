from acl_frameworks.common import ROOT, read, sha
from acl_rsi.settings import load_settings
from acl_multiround_v3.protocol import WORK as OLD, verify as verify_old

WORK = ROOT / 'experiments/runs/full10-highbudget-completion-v1'
FRAMEWORKS = ('harnessfix', 'dgm')


def round_dir(name, index):
    return WORK / name / f'round-{index}'


def settings(name, index):
    cfg = load_settings(round_dir(name, index) / 'config.json')
    assert cfg['model'] == 'deepseek-flash' and cfg['api_base'].rstrip('/') == 'https://api.deepseek.com'
    assert not cfg['thinking']
    return cfg


def verify():
    verify_old()
    lock = read(WORK / 'runtime-lock.json')
    for path, digest in lock['files'].items():
        if sha(ROOT / path) != digest:
            raise ValueError('Recovery frozen file changed: ' + path)
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'acl_multiround_recovery').glob('*.py')}
    assert actual == {p for p in lock['files'] if p.startswith('acl_multiround_recovery/')}
