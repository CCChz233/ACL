from acl_frameworks.common import ROOT,read,sha
from acl_rsi.settings import load_settings
from acl_unified.protocol import FRAMEWORKS,FILES,H0

WORK=ROOT/'experiments/runs/full10-highbudget-two-rounds-v1'
OLD=ROOT/'experiments/runs/full10-two-rounds-v1'
CONFIG=ROOT/'configs/full10-highbudget-two-rounds-v1.json'


def round_dir(name,index):return WORK/name/f'round-{index}'


def settings(name,index):
    cfg=load_settings(round_dir(name,index)/'config.json')
    if cfg['model']!='deepseek-flash' or cfg['api_base'].rstrip('/')!='https://api.deepseek.com' or cfg['thinking']:
        raise ValueError('Fixed provider configuration required')
    return cfg


def verify():
    from acl_multiround_v2.protocol import verify as old_verify
    old_verify()
    lock=read(WORK/'runtime-lock.json')
    assert sha(CONFIG)==lock['config_sha256']
    for path,digest in lock['files'].items():
        if sha(ROOT/path)!=digest:raise ValueError('Two-round frozen source/evidence changed: '+path)
    actual={str(p.relative_to(ROOT)) for p in (ROOT/'acl_multiround_v3').glob('*.py')}
    assert actual=={p for p in lock['files'] if p.startswith('acl_multiround_v3/')}
