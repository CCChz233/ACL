"""Repair integration boundaries; never hand-edit candidate source."""
from pathlib import Path
from acl_frameworks.common import read, ROOT, sha
from acl_rsi.settings import write_json
from acl_unified import common
from acl_multiround_v3 import adapters as previous
from .protocol import OLD


def public_run_with_canonical_trials(original, work):
    def run(public, traces, evaluation, ids, source_trials):
        def resolve(iid):
            trial = Path(source_trials(iid))
            if all((trial / f).exists() for f in ('worker.json', 'grade.json', 'patch.diff')):
                return trial
            canonical = work / 'evaluations/candidate/trials' / iid
            if trial.parent.parent.name != 'v1' or not (canonical / 'grade.json').exists():
                raise ValueError('Unexpected missing HarnessFix evidence: ' + str(trial))
            return canonical
        return original(public, traces, evaluation, ids, resolve)
    return run


def run(name, cfg, instances, work, b):
    module = previous.build_native(name, cfg, instances, work, b)
    if name == 'harnessfix':
        original = module.harnessfix_module
        def corrected(*args):
            native = original(*args)
            native.public_run = public_run_with_canonical_trials(native.public_run, work)
            # Round1 reuses the saved plan/editor output; no model request allowed.
            if (work / 'reused-evaluation.json').exists():
                def no_api(*a, **kw):
                    raise RuntimeError('Offline HarnessFix completion unexpectedly requested model calls')
                native.gateway = lambda *a, **kw: no_api
            return native
        module.harnessfix_module = corrected
    elif name == 'dgm' and cfg['recovery']['replay_first_native_artifact']:
        original_load = module.load_step
        def load_step(which, bindings, directory):
            result = original_load(which, bindings, directory)
            if which != 'dgm':
                return result
            original_proposer = result.runtime.DGMProposer
            source = OLD / 'dgm/round-1/optimizer/candidates/node_0000/harness'
            class ReplayFirstNativeArtifact(original_proposer):
                def __call__(self, context):
                    if context['name'] != 'node_0000':
                        raise ValueError('Only the first saved native proposal may be replayed')
                    common.copy_harness(source, context['candidate_harness'])
                    write_json(work / 'replayed-native-artifact.json', {
                        'source': str(source), 'sha256': common.fingerprint(source),
                        'candidate': str(context['candidate_harness']),
                        'selection': 'first native attempt, fixed before any target feedback',
                        'new_model_calls_for_replay': 0, 'human_candidate_edits': False,
                        'all_original_failed_search_cost_included': True})
            result.runtime.DGMProposer = ReplayFirstNativeArtifact
            return result
        module.load_step = load_step
    return module.run(name, cfg, instances, work, b)
