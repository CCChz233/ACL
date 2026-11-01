"""Only missing HarnessFix/DGM stages, no other framework reruns."""
from acl_frameworks.common import ROOT

_source = ROOT / 'acl_multiround_v3/batch.py'
exec(compile(_source.read_text().replace('acl_multiround_v3.step', 'acl_multiround_recovery.step'), str(_source), 'exec'), globals())
