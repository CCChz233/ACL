"""Model-only repair of native artifacts BEFORE any paid task evaluation."""
import ast
import json
from pathlib import Path
import re
import shutil
import time
import yaml
from jinja2 import Environment
from acl_frameworks.common import read,sha
from acl_frameworks.proposer import DeepSeekFileProposer,TOOLS
from acl_rsi.settings import write_json
from acl_rsi.deepseek import BudgetExceeded
from acl_unified import common
from .provider import gateway,delivery_phase


def strict_validator(original,parent):
    def check(folder,*,require_change=True,contract=True):
        original(folder,require_change=False,contract=contract)
        folder=Path(folder);data=yaml.safe_load((folder/'swebench.yaml').read_text())
        before=yaml.safe_load((parent/'swebench.yaml').read_text())
        keys={'agent':('system_template','instance_template'),'model':('observation_template','format_error_template')}
        for section,names in keys.items():
            for key in names:
                try:Environment().parse(data[section][key])
                except Exception as error:raise common.InvalidCandidate(f'{section}.{key}: {type(error).__name__}: {error}') from error
        if require_change:
            same_code=ast.dump(ast.parse((folder/'agent.py').read_text()))==ast.dump(ast.parse((parent/'agent.py').read_text()))
            norm=lambda text:re.sub(r'\s+',' ',text).strip()
            same_prompts=all(norm(data[s][k])==norm(before[s][k]) for s,names in keys.items() for k in names)
            if same_code and same_prompts:raise common.InvalidCandidate('No real modification: only comments/whitespace or identical parent')
    return check


class Delivery:
    def __init__(self,cfg,work,bindings):
        self.cfg,self.work,self.b=cfg,Path(work),bindings
        self.check=bindings['validate'];self.calls=0

    def native_context(self):
        patterns=('attempts/*/diagnosis.json','native-proposal.json','runs/swe/r0/analysis_report.json',
            'optimizer/native/improvement_plans/*.md')
        values={}
        for pattern in patterns:
            for p in self.work.glob(pattern):values[str(p.relative_to(self.work))]=p.read_text()[:16000]
        return values

    def ensure(self,folder,*,require_change=True,contract=True,force_reason=None):
        folder=Path(folder)
        try:
            result=self.check(folder,require_change=require_change,contract=contract)
            if not force_reason:return result
            reason=force_reason
        except (ValueError,SyntaxError) as error:
            if not require_change:raise
            reason=str(error)
        if list(self.work.glob('evaluations/*/trials/*/worker-attempt.json')):
            raise common.InvalidCandidate('Cannot repair or mutate any candidate after task execution has started')
        if self.calls>=3:raise common.InvalidCandidate('Three model validity-repair sessions exhausted')
        self.calls+=1
        files=('agent.py','swebench.yaml','LICENSE.md')
        if any(not (folder/f).is_file() or (folder/f).is_symlink() for f in files):
            raise common.InvalidCandidate('Repair requires three real native artifact files')
        if {p.name for p in folder.iterdir()}-set(files)-{'__pycache__'}:
            raise common.InvalidCandidate('Native artifact contains unsupported extra files')
        audit=self.work/'delivery'/f'repair-{self.calls}'
        common.copy_harness(folder,audit/'before')
        public=self.work/'delivery-public'
        if not (public/'snapshot.json').exists():self.b['export'](public,self.cfg['protocol']['all_task_ids'])
        target=public/'candidates/native/harness'
        common.copy_harness(folder,target)
        context=self.native_context()
        write_json(public/'reports/native-context.json',context)
        meter=gateway(self.cfg,self.work,'validity_repair')
        reader=DeepSeekFileProposer(public,meter)
        messages=[{'role':'system','content':
            'Complete the EXISTING native framework candidate, preserving its diagnosed mechanism. '
            'You must produce a real generic code/prompt change relative to harness/. '
            'Fix syntax, all four Jinja template strings, scope and tool-result pairing. '
            'Use small Edit operations; preserve license and every non-prompt YAML value. '
            'Never add task/repository-specific solutions, IDs or rules. '
            'Only write candidates/native/harness/agent.py or swebench.yaml. '
            'Do not redesign the method or inspect private grading. '
            'Read reports/native-context.json for the native plan/diagnosis. '
            'Then use Finish with the single existing name native. This is model-authored validity repair, not benchmark feedback optimization.'},
            {'role':'user','content':'Gate rejection: '+reason+'\nRepair the saved native artifact. Parent is harness/; public histories are history/. Finish after the small required repair.'}]
        before=common.fingerprint(folder);finished=False
        with delivery_phase():
            while not finished:
                try:response=meter(model=self.cfg['model'],messages=messages,tools=TOOLS)
                except BudgetExceeded:
                    self.check(target);finished=True;break
                message=response.choices[0].message
                messages.append(message.model_dump(exclude_none=True))
                calls=message.tool_calls or []
                if not calls:raise common.InvalidCandidate('Repair returned no executable tool action')
                for call in calls:
                    try:
                        args=json.loads(call.function.arguments)
                        if call.function.name=='Finish':
                            rows=args['candidates']
                            if len(rows)!=1 or rows[0]['name']!='native':raise ValueError('Finish only the existing native candidate')
                            self.check(target);finished=True;result='Native candidate passes all gates'
                        else:
                            if call.function.name in ('Write','Edit') and args.get('path') not in (
                                'candidates/native/harness/agent.py','candidates/native/harness/swebench.yaml'):
                                raise ValueError('Only the two permitted native candidate files are writable')
                            if call.function.name=='Read':args['limit']=min(args.get('limit',12000),32000)
                            result=reader.tool(call.function.name,args)
                    except (ValueError,KeyError,OSError,SyntaxError) as error:result='Gate/ToolError: '+str(error)[:1000]
                    messages.append({'role':'tool','tool_call_id':call.id,'content':result})
        self.check(target)
        common.copy_harness(target,folder)
        common.copy_harness(folder,audit/'after')
        write_json(audit/'record.json',{'reason':reason,'native_artifact':str(folder),'before':before,
            'after':common.fingerprint(folder),'model_only_edits':True,'no_target_feedback_used':True,
            'completed_at':time.time(),'native_context_files':list(context)})
        return self.check(folder,require_change=require_change,contract=contract)
