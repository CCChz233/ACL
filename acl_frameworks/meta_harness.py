"""Reuse Meta-Harness's native evolution/frontier loop with SWE boundary callbacks."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace

import yaml

from acl_rsi.settings import write_json
from .common import load_module, read


class MetaHarnessAdapter:
    def __init__(self, work, ids, proposer, evaluator):
        self.work, self.ids = Path(work).resolve(), list(ids)
        self.proposer, self.evaluator = proposer, evaluator
        self.public = self.work / 'optimizer'
        self.native = load_module('meta-harness', 'reference_examples/terminal_bench_2/meta_harness.py', 'acl_native_meta')
        self.native.EVOLVE_DIR = self.work / 'controller'
        self.native.AGENTS_DIR = self.public / 'candidates'
        self.native.BASELINES = [('h0', 'h0:AgentHarness')]
        self.native.BASELINE_AGENT_NAME = 'h0'
        self.native.N_EVAL_TASKS = len(ids)
        self.native.MODEL = 'deepseek-flash'
        self.native.harbor_run = self.evaluate
        self.native.parse_job_results = lambda path, expected_trials=None: self.results(path)
        self.native.propose_claude = self.propose
        self.native.validate_candidate = self.validate
        self.native.parse_trial_metrics = lambda path: {}

    def folder(self, name):
        if not re.fullmatch('[a-zA-Z0-9_-]{1,64}', name):
            raise ValueError('Invalid candidate name')
        return self.public / ('harness' if name == 'h0' else f'candidates/{name}/harness')

    def validate(self, name, import_path):
        folder = self.folder(name)
        for item in ('agent.py', 'swebench.yaml', 'LICENSE.md'):
            p = folder / item
            if not p.is_file() or not p.resolve().is_relative_to(self.public.resolve()):
                return False
        ast.parse((folder / 'agent.py').read_text())
        data = yaml.safe_load((folder / 'swebench.yaml').read_text())
        return isinstance(data, dict) and 'agent' in data and 'model' in data

    def evaluate(self, import_path, job_name, n_trials=1, n_concurrent=1):
        if n_trials != 1:
            raise ValueError('Integration evaluator requires explicit single-trial protocol')
        name = 'h0' if import_path.startswith('h0:') else import_path.split(':')[0].split('.')[-1]
        job = self.native.JOBS_DIR / job_name
        path = job / 'outcomes.json'
        if not path.exists():
            scores = self.evaluator(name, self.folder(name), self.ids)
            if set(scores) != set(self.ids) or any(v not in (0, 1, 0.0, 1.0) for v in scores.values()):
                raise ValueError('Incomplete or invalid grading; no synthetic zero scores')
            write_json(path, {'valid': True, 'scores': scores})
        self.results(job)
        return job, True

    def results(self, path):
        data = read(Path(path) / 'outcomes.json')
        if (data.get('valid') is not True or set(data['scores']) != set(self.ids)
                or any(v not in (0, 1, 0.0, 1.0) for v in data['scores'].values())):
            raise ValueError('Invalid cached evaluation')
        return {i: [float(data['scores'][i])] for i in self.ids}

    def propose(self, task_prompt, iteration, timeout=2400):
        # Only public scores and history are made available. Raw evaluation jobs
        # live outside the optimizer workspace and cannot be read by file tools.
        for path in (self.native.FRONTIER_VAL, self.native.EVOLUTION_SUMMARY):
            if path.exists():
                target = self.public / 'history' / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
        candidates = self.proposer(f'Iteration {iteration}. Inspect harness/ and full history/. '
            'Read prior scores and changes; produce generic SWE harness improvements.', iteration)
        if not 1 <= len(candidates) <= 3 or len({r['name'] for r in candidates}) != len(candidates):
            raise ValueError('Expected 1-3 uniquely named candidates')
        for row in candidates:
            if row['name'] == 'h0':
                raise ValueError('Baseline identity is immutable')
            self.folder(row['name'])
            row['import_path'] = f"candidates.{row['name']}:AgentHarness"
        write_json(self.native.PENDING_EVAL, {'iteration': iteration, 'candidates': candidates})
        return True

    def run(self, iterations=1):
        self.native.run_evolve(SimpleNamespace(run_name='integration', fresh=False,
            iterations=iterations, trials=1, concurrent=1, skip_baseline=False,
            propose_timeout=2400, skip_smoke=True, full_eval=False))
        return read(self.native.FRONTIER_VAL)
