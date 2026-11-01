from copy import deepcopy
from pathlib import Path

from acl_rsi.settings import write_json
from .common import BASE_WORK, candidate_id, harness_config, import_gepa, read, seed_candidate, validate_candidate
from .feedback import EvaluationUnavailable, public_record

gepa, _ = import_gepa()
from gepa.core.adapter import EvaluationBatch


class TerminalAdapter:
    propose_new_texts = None

    def __init__(self, cfg, base, work, executor=None, baseline_work=BASE_WORK):
        self.cfg, self.base, self.work = cfg, base, Path(work)
        self.baseline_work = Path(baseline_work)
        self.seed = seed_candidate(base)
        self.executor = executor

    def evaluate(self, batch, candidate, capture_traces=False):
        # Validate the entire batch before any potentially paid execution.
        if any(item['task_id'] not in self.cfg['task_ids'] for item in batch):
            raise ValueError('Unknown task in GEPA batch')
        cid = candidate_id(candidate)
        folder = self.work / 'candidates' / cid
        folder.mkdir(parents=True, exist_ok=True)
        write_json(folder / 'candidate.json', candidate)
        data = validate_candidate(candidate, folder / 'terminal.yaml', self.cfg['task_ids'])
        # YAML reformatting is the same executable policy and must not buy a fresh
        # stochastic baseline run that can masquerade as a harness improvement.
        baseline = data == harness_config(self.base)
        if not baseline:
            identity = self.work / 'candidate-identity.json'
            if identity.exists() and read(identity)['candidate_id'] != cid:
                raise ValueError('One-new-candidate cap reached')
            write_json(identity, {'candidate_id': cid})
        records, fresh_executions = [], 0
        for item in batch:
            task_id = item['task_id']
            reference = self.baseline_work / 'trials' / task_id
            trial = reference if baseline else folder / 'trials' / task_id
            if not (trial / 'result.json').exists() and not baseline:
                if trial.exists():
                    raise EvaluationUnavailable('incomplete_trial_requires_manual_recovery')
                if self.executor is None:
                    raise EvaluationUnavailable('live_executor_not_configured')
                self.executor(task_id, data, folder)
                fresh_executions += 1
            try:
                record = public_record(trial, reference, task_id)
            except EvaluationUnavailable as exc:
                write_json(folder / 'evaluation-invalid.json', {'task_id': task_id, 'reason': str(exc),
                           'candidate_score': None, 'automatic_paid_retry': False})
                raise
            records.append(record)
        return EvaluationBatch(outputs=[{'task_id': r['task_id'], 'score': r['score'],
                    'stop': r['stop'], 'usage': r['usage']} for r in records],
                scores=[r['score'] for r in records], trajectories=records if capture_traces else None,
                num_metric_calls=fresh_executions)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        if components_to_update != ['terminal.yaml'] or eval_batch.trajectories is None:
            raise ValueError('Only terminal.yaml and whitelisted traces are reflective inputs')
        # No result.json, verifier logs, CTRF test names, task tests or solutions cross this interface.
        records = [{'Inputs': {'task_id': r['task_id']},
                    'Generated Outputs': {'stop': r['stop'], 'public_agent_trace': r['public_agent_trace']},
                    'Feedback': {'binary_reward': r['score'], 'usage': r['usage'], 'scope': r['trace_scope']}}
                   for r in eval_batch.trajectories]
        write_json(self.work / 'reflection-feedback.json', records)
        return {'terminal.yaml': deepcopy(records)}
