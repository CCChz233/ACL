"""Reuse the frozen high-budget step controller with versioned local bindings."""
from acl_frameworks.common import ROOT

_source = ROOT / 'acl_multiround_v3/step.py'
exec(compile(_source.read_text(), str(_source), 'exec'), globals())
