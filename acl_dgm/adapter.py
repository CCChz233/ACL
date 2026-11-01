"""Native DGM main + archive, with strict public-evidence SWE callbacks."""
import ast
import contextlib
import difflib
import io
import json
import os
from pathlib import Path
import shutil
import sys

import yaml

from acl_frameworks.common import read, sha
from acl_frameworks.context import export_baseline
from acl_rsi.settings import write_json
from .native import outer

FILES = ('agent.py', 'swebench.yaml', 'LICENSE.md')


def validate(folder, baseline):
    folder = Path(folder)
    entries = {p.name for p in folder.iterdir()}
    cache = folder / '__pycache__'
    if cache.exists() and (cache.is_symlink() or not cache.is_dir()
            or any(p.is_symlink() or not p.is_file() or p.suffix != '.pyc' for p in cache.iterdir())):
        raise ValueError('Invalid Python bytecode cache')
    if entries - {'__pycache__'} != set(FILES):
        raise ValueError('Only agent.py and swebench.yaml are editable; preserve LICENSE.md')
    for name in FILES:
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Candidate files must be real local files')
    tree = ast.parse((folder / 'agent.py').read_text())
    if not any(isinstance(n, ast.ClassDef) and n.name == 'DefaultAgent' for n in tree.body):
        raise ValueError('Missing DefaultAgent')
    data = yaml.safe_load((folder / 'swebench.yaml').read_text())
    if not isinstance(data, dict) or not all(isinstance(data.get(k), dict) for k in ('agent', 'model')):
        raise ValueError('Invalid harness YAML')
    for section, keys in {'agent': ('system_template', 'instance_template'),
                          'model': ('observation_template', 'format_error_template')}.items():
        if not all(isinstance(data[section].get(k), str) for k in keys):
            raise ValueError('Missing runtime templates')
    if sha(folder / 'LICENSE.md') != sha(Path(baseline) / 'LICENSE.md'):
        raise ValueError('License changed')


def performance(ids, outcomes):
    if set(outcomes) != set(ids):
        raise ValueError('Incomplete evaluation; never synthesize zero scores')
    resolved, unresolved, empty = [], [], []
    for iid in ids:
        item = outcomes[iid]
        if item.get('score') not in (0, 1) or not isinstance(item.get('empty_patch'), bool):
            raise ValueError('Invalid evaluation')
        if item['score'] and item['empty_patch']:
            raise ValueError('An empty patch cannot resolve a task')
        (resolved if item['score'] else empty if item['empty_patch'] else unresolved).append(iid)
    return {'accuracy_score': len(resolved)/len(ids), 'total_submitted_instances': len(ids),
        'total_resolved_instances': len(resolved), 'total_resolved_ids': resolved,
        'total_unresolved_ids': unresolved, 'total_emptypatch_ids': empty}


class DGMAdapter:
    def __init__(self, work, ids, proposer, evaluator, seed=17, evidence_scope='historical_development'):
        if not ids or len(set(ids)) != len(ids):
            raise ValueError('Need unique development task IDs')
        self.work, self.ids = Path(work).resolve(), list(ids)
        self.public = self.work / 'optimizer'
        self.controller = self.work / 'controller'
        self.archive = self.controller / 'output_dgm/pilot'
        self.proposer, self.evaluator, self.seed = proposer, evaluator, seed
        self.evidence_scope = evidence_scope
        self.next_generation = 0
        self.failed = []

    def metadata(self, name, parent, outcomes):
        folder = self.archive / name
        write_json(folder / 'metadata.json', {'run_id': name, 'parent_commit': parent,
            'evidence_scope': self.evidence_scope,
            'overall_performance': performance(self.ids, outcomes)})
        predictions = folder / 'predictions/trial-0'
        for iid, item in outcomes.items():
            # Only own messages, own patch and binary outcome enter native log reader.
            (predictions).mkdir(parents=True, exist_ok=True)
            (predictions / (iid+'.md')).write_text(json.dumps(item.get('messages', []), ensure_ascii=False))
            write_json(predictions / (iid+'.json'), {'model_patch': item.get('patch', ''),
                'eval_result': 'resolved' if item['score'] else 'empty_patch' if item['empty_patch'] else 'unresolved'})
        return read(folder / 'metadata.json')

    def prepare(self):
        if not (self.public / 'snapshot.json').exists():
            export_baseline(self.public, self.ids)
        state = self.archive / 'dgm_metadata.jsonl'
        if state.exists():
            return
        initial = self.archive / 'initial/harness'
        initial.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.public / 'harness', initial)
        outcomes = self.evaluator('initial', initial, self.ids)
        self.metadata('initial', None, outcomes)
        state.write_text(json.dumps({'generation': -1, 'archive': ['initial'],
            'scope': self.evidence_scope, 'new_baseline_model_calls': 0})+'\n')
        for split in ('small', 'medium', 'big'):
            write_json(self.controller / 'swe_bench/subsets' / (split+'.json'), self.ids)

    def publish(self):
        target = self.public / 'history/dgm-archive'
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(self.archive, target)

    def improve(self, parent_commit, entry, **kwargs):
        if kwargs['num_evals'] != 1 or kwargs['polyglot'] or kwargs['test_more_threshold'] is not None:
            raise ValueError('Current adapter requires native shallow single-trial SWE protocol')
        if kwargs['test_task_list'] != self.ids:
            raise ValueError('Native task subset differs')
        name = f'node_{self.next_generation:04d}'
        self.next_generation += 1
        parent = self.archive / parent_commit / 'harness'
        candidate = self.public / 'candidates' / name / 'harness'
        if candidate.exists():
            raise ValueError('Interrupted attempt exists; preserve it and resume explicitly')
        shutil.copytree(parent, candidate)
        self.publish()
        context = {'name': name, 'parent': parent_commit, 'entry': entry,
            'parent_harness': self.public / 'history/dgm-archive' / parent_commit / 'harness',
            'candidate_harness': candidate, 'workspace': self.public}
        try:
            self.proposer(context)
        except Exception as error:
            self.failed.append({'candidate': name, 'phase': 'proposal', 'error_type': type(error).__name__})
            raise
        try:
            validate(candidate, self.public / 'harness')
        except (ValueError, SyntaxError, yaml.YAMLError) as error:
            write_json(self.archive / name / 'metadata.json', {'run_id': name, 'parent_commit': parent_commit,
                'overall_performance': {}, 'invalid_candidate': type(error).__name__})
            return read(self.archive / name / 'metadata.json')
        try:
            outcomes = self.evaluator(name, candidate, self.ids)
            performance(self.ids, outcomes)
        except Exception as error:
            self.failed.append({'candidate': name, 'error_type': type(error).__name__})
            raise
        saved = self.archive / name / 'harness'
        shutil.copytree(candidate, saved)
        patch = ''
        for file in FILES:
            before, after = (parent / file).read_text(), (saved / file).read_text()
            if before != after:
                patch += f'diff --git a/{file} b/{file}\n'+''.join(difflib.unified_diff(
                    before.splitlines(True), after.splitlines(True), fromfile='a/'+file, tofile='b/'+file))
        (self.archive / name / 'model_patch.diff').write_text(patch)
        return self.metadata(name, parent_commit, outcomes)

    def run(self, generations=1):
        if generations < 1:
            raise ValueError('Need at least one generation')
        self.prepare()
        old_cwd, old_argv = Path.cwd(), sys.argv
        output = io.StringIO()
        try:
            with outer(self.improve, self.seed) as native:
                state = native.load_dgm_metadata(self.archive / 'dgm_metadata.jsonl', last_only=True)
                self.next_generation = state['generation']+1
                os.chdir(self.controller)
                sys.argv = ['DGM_outer.py', '--continue_from', str(self.archive),
                    '--max_generation', str(state['generation']+1+generations),
                    '--selfimprove_size', '1', '--selfimprove_workers', '1',
                    '--num_swe_evals', '1', '--shallow_eval', '--no_full_eval']
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    native.main()
                result = native.load_dgm_metadata(self.archive / 'dgm_metadata.jsonl', last_only=True)
        finally:
            os.chdir(old_cwd)
            sys.argv = old_argv
            with (self.work / 'native-outer.log').open('a') as handle:
                handle.write(output.getvalue())
        if self.failed:
            write_json(self.work / 'evaluation-failures.json', self.failed)
            raise RuntimeError('DGM caught evaluation failures; inspect preserved errors, no zero imputation')
        self.publish()
        return result
