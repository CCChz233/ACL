from copy import deepcopy
from pathlib import Path

import yaml

from acl_gepa.common import candidate_id, import_gepa
from acl_rsi.settings import write_json
from acl_terminal_rsi.common import read
from .common import baseline_trial, seed_candidate, validate
from .feedback import EvaluationUnavailable, record

gepa, _ = import_gepa()
from gepa.core.adapter import EvaluationBatch


class SWEAdapter:
    propose_new_texts = None

    def __init__(self, cfg, work, instances, executor=None):
        self.cfg, self.work, self.instances, self.executor = cfg, Path(work), instances, executor
        self.seed = seed_candidate()

    def evaluate(self, batch, candidate, capture_traces=False):
        if any(item['task_id'] not in self.cfg['evolve_ids'] for item in batch):
            raise ValueError('Unknown SWE task')
        cid = candidate_id(candidate)
        folder = self.work / 'candidates' / cid
        data = validate(candidate, folder / 'harness', self.cfg['evolve_ids'])
        write_json(folder / 'candidate.json', candidate)
        baseline = data == yaml.safe_load(self.seed['swebench.yaml'])
        if not baseline:
            identity = self.work / 'candidate-identity.json'
            if identity.exists() and read(identity)['candidate_id'] != cid:
                raise ValueError('One-new-candidate cap reached')
            write_json(identity, {'candidate_id': cid})
        fresh = 0
        if not baseline and self.executor:
            fresh = self.executor.evaluate([i['task_id'] for i in batch], folder)
        records = []
        for item in batch:
            iid = item['task_id']
            trial = baseline_trial(iid) if baseline else folder / 'trials' / iid
            try:
                records.append(record(trial, iid, self.instances[iid], trace=capture_traces))
            except EvaluationUnavailable as exc:
                write_json(folder / 'evaluation-invalid.json', {'task_id': iid, 'reason': str(exc), 'score': None})
                raise
        return EvaluationBatch(outputs=[{k: r[k] for k in ('task_id', 'score', 'stop', 'usage')} for r in records],
            scores=[r['score'] for r in records], trajectories=records if capture_traces else None,
            num_metric_calls=fresh)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        if components_to_update != ['swebench.yaml'] or eval_batch.trajectories is None:
            raise ValueError('Only swebench.yaml may be reflected on')
        rows = sorted(eval_batch.trajectories, key=lambda r: r['task_id'])
        chosen = [r for r in rows if r['score'] == 0][:8] + [r for r in rows if r['score'] == 1][:3]
        public = [{'Inputs': {'public_issue': r['problem_statement']},
                   'Generated Outputs': {'stop': r['stop'], 'public_agent_trace': r['public_agent_trace']},
                   'Feedback': {'resolved': r['score'], 'usage': r['usage']}} for r in chosen]
        write_json(self.work / 'reflection-feedback.json', public)
        return {'swebench.yaml': deepcopy(public)}
