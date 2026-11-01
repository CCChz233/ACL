"""Native HarnessFix adapters: HTIR, isolated pipeline planning and model boundary."""
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import sys

from acl_rsi.settings import write_json
from .common import ROOT, load_module, read, sha, verify
from .provider import bind_litellm


def compile_snapshot(snapshot):
    module = load_module('harnessfix', 'failure_analysis/htir.py', 'acl_native_hf_htir')
    root = Path(snapshot)
    spec = read(root / 'snapshot.json')
    rows = []
    for item in spec['tasks']:
        iid = item['task_id']
        folder = root / 'history' / iid
        feedback = read(folder / 'feedback.json')
        bundle = module.compile_swe_htir(instance_id=iid,
            failure_category='resolved' if feedback['resolved'] else 'unresolved',
            paths={'traj_path': str(folder / 'trajectory.json'), 'report_path': '', 'test_output_path': ''},
            task_description=feedback['problem_statement'])
        module.write_bundle(bundle, folder / 'htir.json')
        rows.append({'task_id': iid, 'htir_sha256': sha(folder / 'htir.json')})
    return rows


def isolated_plan(work, train_ids, val_ids):
    """Exercise the actual upstream pipeline --dry-run, with zero subprocesses."""
    _, source = verify('harnessfix')
    work = Path(work).resolve()
    native = work / 'native'
    if not native.exists():
        shutil.copytree(source, native, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.env',
            'traces', 'logs', 'results', '.venv', 'pipeline_state.json'))
    for label, ids in (('train', train_ids), ('val', val_ids)):
        folder = native / 'data' / f'acl_{label}'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'instance_ids.txt').write_text('\n'.join(ids)+'\n')
    spec = importlib.util.spec_from_file_location('acl_native_hf_pipeline', native / 'run_pipeline_swe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The public pipeline uses Path(__file__) for outputs. It executes only in
    # this isolated copy; original source and old runs are never written.
    module.ORIGINAL_AGENT_DIR = ROOT / 'agents/mini-swe-agent'
    module.VENV_PYTHON = Path(sys.executable)
    # Native --dry-run still reads prior grading metadata. Supply an explicitly
    # synthetic unresolved fixture in this disposable planning copy only.
    module.RUN_LABEL = 'integration'
    fixture = module.train_eval_dir('openai/deepseek-flash', 0) / 'offline-fixture.json'
    write_json(fixture, {'scope': 'synthetic dry-run prerequisite, not benchmark evidence',
                         'resolved_ids': [], 'unresolved_ids': list(train_ids)})
    old_argv = sys.argv
    sys.argv = ['run_pipeline_swe.py', '--model', 'openai/deepseek-flash',
                '--analysis-model', 'openai/deepseek-flash', '--workers', '1',
                '--max-iterations', '1', '--train-dir', str(native / 'data/acl_train'),
                '--val-dir', str(native / 'data/acl_val'), '--run-label', 'integration', '--dry-run']
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            module.main()
    finally:
        sys.argv = old_argv
    (work / 'native-pipeline-dry-run.log').write_text(log.getvalue())
    report = {'status': 'native_dry_run_passed', 'model': 'deepseek-flash',
              'agent_source': 'agents/mini-swe-agent', 'agent_version': '2.4.6',
              'upstream_vendored_version': '2.2.7', 'model_calls': 0,
              'numeric_benchmark_score': None, 'all_core_stages_planned': True,
              'synthetic_grading_prerequisite': str(fixture),
              'limitations': ['This is native control-flow planning, not a paid end-to-end run.',
                'Private official grader detail is not exposed to the optimizer.',
                'The 2.2.7 to 2.4.6 adaptation requires the first bounded real experiment.']}
    write_json(work / 'harnessfix-plan.json', report)
    return report


def bind_provider(gateway):
    """Connect native analysis/aggregation/repair LiteLLM calls to recorded DeepSeek."""
    bind_litellm(gateway)


def promotion_check(output, *, audit, comparison):
    module = load_module('harnessfix', 'run_pipeline_swe.py', 'acl_native_hf_promotion')
    module.FAILURE_ANALYSIS_DIR = Path(output)
    return module.step_promotion_decision(version=1, audit=audit, train_compare=comparison,
        val_compare=comparison, min_improvement=1, min_target_metrics=1,
        max_error_rate_delta=0.15, max_invalid_rate_delta=0.15, dry_run=False)
