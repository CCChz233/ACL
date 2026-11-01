import asyncio
import json
import re
from pathlib import Path
from rrsi.domain import Domain
from rrsi.evaluate import TaskResult
from acl_rsi.settings import ROOT, write_json
from .common import BASE_WORK, read, sha, validate_harness


class TerminalDomain(Domain):
    name='terminal'
    harness_path='harness'
    source_exts={'.yaml'}
    briefs={
      'analyst': 'Analyze a frozen mini-SWE-agent terminal pilot. Only external binary rewards and the agent own messages are supplied. No private verifier output or expected answers. Dispatch at most 8 digesters in your first action, covering failures and representative successes; your next action must report. Diagnose reusable mechanisms, not solutions to task instances.',
      'digester': 'Read the assigned compact terminal-agent trace. It contains public requirements, call/stop metadata and bounded excerpts of the agent own messages. First read the assigned file; return a concise evidence-based digest within three calls. Do not infer hidden expected answers. Separate observed failures from causal hypotheses.',
      'proposer': 'Improve ONLY terminal.yaml generic system/instance prompts and observation/format-error templates. The native mini DefaultAgent loop, DeepSeek Flash, bash tool, task container, grader and budgets are immutable. Each target trial allows 50 API calls, 1000000 total tokens, 4096 output tokens per call, 60-second command timeout and the original task wall limit. Task completion is graded on final container state. Keep public task interpolation and completion marker. One coherent generic mechanism, not task-specific instructions, answer values or file paths. Do not add YAML keys or files. Use edit_file for bounded changes and done with one declared edit.',
      'critic': 'Only a generic terminal.yaml prompt/template edit is admissible. Reject task IDs, task-specific paths, benchmark answers/algorithms, access to host/credentials/verifier, changes to budgets/model/runtime, and Jinja introspection. Public requirements vary; avoid domain-specific workarounds. Preserve submission semantics and successful behavior.'}
    component_signals=[('prompt',[r'system_template',r'instance_template']),
                       ('output_plumbing',[r'observation_template',r'format_error_template'])]

    def __init__(self,cfg):
        self.cfg=cfg
        self.ids=[x['id'] for x in cfg['tasks']]
        self.critic_patterns=[(re.escape(i),'task-specific identifier') for i in self.ids]
        self.critic_patterns += [(r'DEEPSEEK_API_KEY|dotenv|os\.environ|api\.deepseek|public-feedback|/logs/|/tests/|/solution/|reward\.txt','private runtime or evaluation access')]

    def evolve_ids(self): return self.ids
    def heldout_ids(self): return []
    def smoke_ids(self,incumbent_per_task=None): return []
    def trial_dir(self,runs_dir,job,task_id,trial=0):
        if job=='base': return BASE_WORK/'trials'/task_id
        return Path(self.cfg['workspace'])/'candidate-eval'/'trials'/task_id

    def run(self,root,runs_dir,job,ids,k,log_prefix=''):
        if k!=1 or job not in ('base','r0A'): raise ValueError('one candidate/trial only')
        (Path(runs_dir)/'jobs'/job).mkdir(parents=True,exist_ok=True)
        if job=='base':
            if any(not (self.trial_dir(runs_dir,job,i)/'result.json').exists() for i in ids):
                raise ValueError('Baseline evidence incomplete')
            return
        import acl_terminal.run as runner
        harness=self.harness_dir(Path(root))/'terminal.yaml'
        data=validate_harness(harness,self.ids)
        eval_work=Path(self.cfg['workspace'])/'candidate-eval'
        eval_work.mkdir(parents=True,exist_ok=True)
        execution={**self.cfg,**data,'workspace':str(eval_work)}
        execution_path=eval_work/'execution-config.json'
        if execution_path.exists() and read(execution_path)!=execution:
            raise ValueError('Candidate execution config changed')
        write_json(execution_path,execution)
        runner.CONFIG=execution_path
        if not (eval_work/'preexisting-images.json').exists():
            write_json(eval_work/'preexisting-images.json',runner.inventory())
        original=runner.docker
        expected={row['image']:read(BASE_WORK/'image-pulls'/f'baseline-{row["id"]}.json')['Id'] for row in self.cfg['tasks']}
        def checked_docker(*args,**kwargs):
            result=original(*args,**kwargs)
            if args[:2]==('image','inspect') and result.returncode==0 and args[2] in expected:
                if json.loads(result.stdout)[0]['Id']!=expected[args[2]]:
                    raise ValueError('Task image differs from baseline; no model call permitted')
            return result
        runner.docker=checked_docker
        try:
            for i in ids:
                print(f'[terminal-rsi] evaluating {i}',flush=True)
                asyncio.run(runner.run_trial(i,'baseline',execution,eval_work))
                progress=runner.summarize(eval_work,self.cfg['tasks'])
                print(f'[terminal-rsi] done={progress["completed"]}/12 passed={progress["passed"]}',flush=True)
        finally:
            runner.docker=original
            protected=set(read(eval_work/'preexisting-images.json'))
            write_json(eval_work/'cleanup-audit.json',{'missing_preexisting':sorted(protected-set(runner.inventory()))})

    def score(self,runs_dir,job,ids,k):
        results={}
        for i in ids:
            path=self.trial_dir(runs_dir,job,i)
            result=read(path/'result.json') if (path/'result.json').exists() else {}
            worker=read(path/'agent/worker.json') if (path/'agent/worker.json').exists() else {}
            reward=((result.get('verifier_result') or {}).get('rewards') or {}).get('reward')
            missing=reward is None or result.get('exception_info') is not None or worker.get('exit_status')=='ProviderError'
            results[i]=TaskResult(rewards=[float(reward or 0)],tokens=[worker.get('usage',{}).get('actual_tokens') or None],missing=int(missing))
        return results,{'scope':'same 12 development tasks; one paired execution per task','rrsi_round':job}

    def load_trial(self,runs_dir,job,task_id,trial):
        path=self.trial_dir(runs_dir,job,task_id)
        if not (path/'agent/worker.json').exists(): return None
        result=read(path/'result.json')
        return {'task_id':task_id,'worker':read(path/'agent/worker.json'),
                'trajectory':read(path/'agent/trajectory.json'),
                'score':((result.get('verifier_result') or {}).get('rewards') or {}).get('reward',0)}

    def render_trace(self,rec,detail=False):
        messages=rec['trajectory'].get('messages',[])
        rows=[f'Task: {rec["task_id"]}; official binary reward={rec["score"]}; stop={rec["worker"]["exit_status"]}; usage={rec["worker"]["usage"]}',
              'Only public task requirements and agent-generated observations follow; no verifier text.']
        if len(messages)>1: rows.append('PUBLIC TASK: '+str(messages[1].get('content',''))[:3200])
        rows.append('Agent actions/observations (bounded excerpts; use these as evidence, not an exhaustive transcript):')
        indexes=sorted(set(list(range(min(8,len(messages))))+list(range(max(0,len(messages)-54),len(messages)))))
        for index in indexes:
            msg=messages[index]
            if msg.get('role')=='system' or (index==1 and msg.get('role')=='user'): continue
            content=str(msg.get('content') or '')
            if msg.get('role')=='assistant':
                commands=[a.get('command','') for a in msg.get('extra',{}).get('actions',[])]
                if not commands:
                    commands=[t.get('function',{}).get('arguments','') for t in msg.get('tool_calls',[])]
                rows.append(f'[{index}] assistant: '+content[:120]+' COMMANDS: '+json.dumps(commands)[:260])
            else:
                rows.append(f'[{index}] {msg.get("role")}: '+content[:180])
        return '\n'.join(rows)[:22000]

    def task_row(self,task_id,rec,tr):
        return f'{task_id} | reward={tr.mean} | calls={rec["worker"]["usage"]["calls"]} | stop={rec["worker"]["exit_status"]}'

    def smoke(self,root,runs_dir,job,ids):
        try:
            hdir=self.harness_dir(Path(root))
            if {p.name for p in hdir.iterdir() if p.is_file()}!={'terminal.yaml'}:
                raise ValueError('Only terminal.yaml is editable')
            validate_harness(hdir/'terminal.yaml',self.ids)
            return True,{'stage':'declarative_template_validation','api_calls':0}
        except Exception as exc:
            return False,{'error_type':type(exc).__name__,'error':str(exc)}
