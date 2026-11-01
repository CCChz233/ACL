import hashlib
import json
from pathlib import Path

from acl_terminal_rsi.common import read


class EvaluationUnavailable(RuntimeError):
    pass


def record(trial, iid, instance, trace=True):
    trial = Path(trial)
    if not all((trial / name).exists() for name in ('worker.json', 'grade.json', 'patch.diff')):
        raise EvaluationUnavailable('missing_worker_or_grade')
    worker, grade = read(trial / 'worker.json'), read(trial / 'grade.json')
    if worker.get('instance_id') != iid or grade.get('instance_id') != iid:
        raise EvaluationUnavailable('wrong_instance')
    if worker.get('exit_status') in ('DockerException', 'CalledProcessError', 'FileNotFoundError', 'ProviderError'):
        raise EvaluationUnavailable('worker_infrastructure_or_provider_error')
    patch = (trial / 'patch.diff').read_text()
    if hashlib.sha256(patch.encode()).hexdigest() != grade.get('patch_sha256'):
        raise EvaluationUnavailable('patch_digest_mismatch')
    if grade.get('infrastructure_failure'):
        raise EvaluationUnavailable('grader_infrastructure_failure')
    if not patch.strip():
        if grade.get('reason') != 'empty_submission' or not grade.get('completed') or grade.get('resolved'):
            raise EvaluationUnavailable('invalid_empty_patch_grade')
    elif grade.get('completed'):
        path = grade.get('report_path')
        if not path or not Path(path).exists():
            raise EvaluationUnavailable('missing_official_report')
        official = read(path).get(iid, {})
        if (not isinstance(official.get('resolved'), bool) or
                official['resolved'] != grade.get('resolved') or
                'tests_status' not in official or not official.get('patch_successfully_applied')):
            raise EvaluationUnavailable('official_report_mismatch')
    elif grade.get('reason') not in ('invalid_patch', 'grading_timeout') or grade.get('resolved'):
        raise EvaluationUnavailable('grading_incomplete')
    value = {'task_id': iid, 'score': float(bool(grade['resolved'])), 'stop': worker.get('exit_status'),
             'usage': worker.get('usage', {}), 'grading_reason': grade.get('reason', 'official_tests')}
    if trace:
        # Only the agent's own interactions and public issue enter GEPA. Grader
        # output, reference patches and evaluation test identities are never read here.
        messages = read(trial / 'trajectory.json').get('messages', []) if (trial / 'trajectory.json').exists() else []
        public = [{k: m[k] for k in ('role', 'content', 'tool_calls') if k in m} for m in messages]
        text = json.dumps(public, ensure_ascii=False)
        value['public_agent_trace'] = text if len(text) <= 9000 else text[:3000] + '\n[interaction excerpt omitted]\n' + text[-6000:]
        value['problem_statement'] = instance['problem_statement']
    return value
