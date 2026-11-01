"""Metered DeepSeek diagnosis + self-editing parent mini agent and official SWE boundary."""
import importlib
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

import yaml

from acl_frameworks.common import ROOT, read
from acl_frameworks.provider import RecordedDeepSeek
from acl_frameworks.live import Evaluator, BASE
from acl_rsi.deepseek import BudgetExceeded, normalize_json_response
from acl_rsi.model import DeepSeekMiniModel, ModelConfig
from acl_rsi.settings import write_json
from acl_rsi.worker import load_agent, image_name
from .adapter import validate

SCOPE = ('Improve the generic mini harness, not a benchmark solution. Edit only agent.py and '
    'swebench.yaml; preserve LICENSE.md, model, provider, grading and task budgets. '
    'Task runtime is fixed at max_calls=50, max_tokens=1000000, wall_seconds=1200; '
    'source defaults are overridden. Do not add dependencies or repository-specific rules. '
    'Use the bash tool. End with echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT and a summary. '
    'Private tests, reference patches, credentials and host files are unavailable.')


def diagnosis_messages(context):
    """Reuse native diagnosis questions, removing private-test evidence sections."""
    prompts = importlib.import_module('prompts.self_improvement_prompt')
    source = context['parent_harness']
    code = '\n'.join(f'## {f}\n'+(source / f).read_text() for f in ('agent.py', 'swebench.yaml'))
    system = 'The agent is mini-SWE-agent DefaultAgent, using metered DeepSeek tools.\n'+prompts.diagnose_system_message.format(code=code)
    folder = context['workspace'] / 'history/dgm-archive' / context['parent'] / 'predictions/trial-0'
    entry = context['entry']
    specials = {'solve_empty_patches': prompts.diagnose_prompt_emptypatches,
                'solve_stochasticity': prompts.diagnose_prompt_stochasticity,
                'solve_contextlength': prompts.diagnose_prompt_contextlength}
    if entry in specials:
        user = specials[entry]+'\nPublic outcomes: '+(folder.parent.parent / 'metadata.json').read_text()
    else:
        template = re.sub(r'# Private Test Patch.*?(?=# Issue Test Results)', '', prompts.diagnose_prompt, flags=re.S)
        template = template.replace('The test results from SWE-bench using the above official private tests.',
                                    'Only the public binary outcome is supplied; private grader detail is withheld.')
        evidence = read(folder / (entry+'.json'))
        feedback = read(context['workspace'] / 'history' / entry / 'feedback.json')
        user = template.format(md_log=(folder / (entry+'.md')).read_text(),
            github_issue=feedback['problem_statement'], predicted_patch=evidence['model_patch'],
            eval_log=evidence['eval_result'])
    return [{'role': 'system', 'content': system+'\n'+SCOPE},
            {'role': 'user', 'content': user+'\n'+SCOPE}]


class NativeMiniModel(DeepSeekMiniModel):
    def __init__(self, cfg, templates, gateway):
        self.config = ModelConfig(model_name=cfg['model'],
            observation_template=templates['observation_template'],
            format_error_template=templates['format_error_template'])
        self.ledger = gateway.ledger
        self.client = SimpleNamespace(complete=lambda messages, **kw:
            gateway(model=cfg['model'], messages=messages, **kw))


class DGMProposer:
    def __init__(self, cfg, work, *, enabled=False):
        self.cfg, self.work, self.enabled = cfg, Path(work), enabled

    def meter(self, role):
        cfg = {k: self.cfg[k] for k in ('model', 'api_base', 'thinking')}
        cfg['limits'] = self.cfg['search']
        return RecordedDeepSeek(cfg, self.work / 'optimizer-api', role, enabled=self.enabled)

    def __call__(self, context):
        if not self.enabled:
            raise RuntimeError('DGM model calls are disabled; use an explicit versioned live configuration')
        output = self.work / 'attempts' / context['name']
        output.mkdir(parents=True, exist_ok=False)
        messages = diagnosis_messages(context)
        response = self.meter('diagnosis')(model=self.cfg['model'], messages=messages,
            response_format={'type': 'json_object'})
        diagnosis = json.loads(normalize_json_response(response.choices[0].message.content or ''))
        if not all(isinstance(diagnosis.get(k), str) and diagnosis[k].strip()
                   for k in ('implementation_suggestion', 'problem_description')):
            raise ValueError('Incomplete diagnosis')
        write_json(output / 'diagnosis.json', diagnosis)
        parent = context['parent_harness']
        validate(parent, context['workspace'] / 'harness')
        templates = yaml.safe_load((parent / 'swebench.yaml').read_text())
        meter = self.meter('implementation')
        model = NativeMiniModel(self.cfg, templates['model'], meter)
        # Use the PARENT'S evolved controller, not a permanently fixed external editor.
        agent_class = load_agent(parent / 'agent.py')
        from minisweagent.environments.docker import DockerEnvironment
        import docker
        from scripts.run_swe_local import require_cache
        client = docker.from_env(timeout=60)
        try:
            require_cache(client, read(ROOT / 'configs/swe-mini-image-cache.json'))
        finally:
            client.close()
        public, candidate = context['workspace'], context['candidate_harness']
        env = DockerEnvironment(image=image_name(self.cfg['evolve_ids'][0]), cwd=str(candidate),
            timeout=60, env={'PAGER': 'cat'}, run_args=['--rm', '--platform', 'linux/amd64',
                '--network', 'none', '--cpus', '2', '--memory', '2g',
                '--volume', f'{public}:{public}:ro', '--volume', f'{candidate}:{candidate}:rw'])
        agent = None
        try:
            kwargs = dict(templates['agent'])
            kwargs.update(system_template='You improve a coding agent using bash tools. '+SCOPE,
                instance_template='{{task}}', step_limit=self.cfg['search']['max_calls'], cost_limit=0,
                wall_time_limit_seconds=1200, output_path=output / 'trajectory.json')
            agent = agent_class(model, env, **kwargs)
            task = f'Parent harness: {parent}\nWritable candidate: {candidate}\n'+json.dumps(diagnosis, ensure_ascii=False)
            result = agent.run(task)
            write_json(output / 'implementation.json', {'exit_status': result.get('exit_status'),
                                                        'parent_controller': str(parent)})
        except BudgetExceeded as error:
            write_json(output / 'implementation.json', {'exit_status': 'BudgetExceeded', 'reason': error.reason,
                'partial_candidate_preserved': True, 'requires_native_validity_filter': True})
        finally:
            if agent:
                agent.save(output / 'trajectory.json')
            if env.container_id:
                subprocess.run(['docker', 'rm', '-f', env.container_id], capture_output=True, timeout=60)
                env.container_id = None


class SWEEvaluator:
    def __init__(self, cfg, work):
        from acl_rsi.settings import load_instances
        self.instances = load_instances(cfg)
        self.work = Path(work)
        self.backend = Evaluator(cfg, self.instances, self.work)

    def __call__(self, name, harness, ids):
        scores = self.backend('h0' if name == 'initial' else name, harness, ids)
        result = {}
        for iid in ids:
            trial = (BASE / 'runs/swe/jobs/base' / iid / 'trial-0') if name == 'initial' else self.work / 'evaluations' / name / 'trials' / iid
            raw = read(trial / 'trajectory.json') if (trial / 'trajectory.json').exists() else {'messages': []}
            messages = []
            for m in raw.get('messages', []):
                row = {k: m[k] for k in ('role', 'content', 'tool_calls', 'tool_call_id') if k in m}
                if m.get('extra', {}).get('actions'):
                    row['extra'] = {'actions': m['extra']['actions']}
                messages.append(row)
            patch = (trial / 'patch.diff').read_text()
            result[iid] = {'score': scores[iid], 'empty_patch': not patch.strip(),
                           'messages': messages, 'patch': patch}
        return result
