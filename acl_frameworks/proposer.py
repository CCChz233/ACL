"""DeepSeek filesystem proposer for Meta-Harness; all accesses are audited."""
import json

from .context import EvidenceWorkspace


PARAMETERS = {
    'Read': {'path': {'type': 'string'}, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}},
    'Glob': {'pattern': {'type': 'string'}},
    'Grep': {'pattern': {'type': 'string'}, 'text': {'type': 'string'}},
    'Write': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
    'Edit': {'path': {'type': 'string'}, 'old': {'type': 'string'}, 'new': {'type': 'string'}},
    'Finish': {'candidates': {'type': 'array', 'minItems': 1, 'maxItems': 3,
        'description': 'Metadata of saved candidate folders only; never include source code.',
        'items': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': 'Existing candidate folder name, e.g. h1.'},
            'hypothesis': {'type': 'string', 'maxLength': 1024},
            'changes': {'type': 'string', 'maxLength': 1024}},
            'required': ['name', 'hypothesis', 'changes'], 'additionalProperties': False}}},
}
REQUIRED = {'Read': ['path'], 'Glob': ['pattern'], 'Grep': ['pattern', 'text'],
            'Write': ['path', 'content'], 'Edit': ['path', 'old', 'new'], 'Finish': ['candidates']}
TOOLS = [{'type': 'function', 'function': {'name': name, 'description': 'Public optimizer workspace '+name,
          'parameters': {'type': 'object', 'properties': props, 'required': REQUIRED[name],
                         'additionalProperties': False}}} for name, props in PARAMETERS.items()]
PARAMETERS['Read']['offset']['description'] = 'Zero-based CHARACTER offset, not line number; default 0.'
PARAMETERS['Read']['limit']['description'] = 'Maximum CHARACTERS returned, not lines; default 32000.'
PARAMETERS['Grep']['pattern']['description'] = 'FILE GLOB, e.g. candidates/h1/harness/*.py. Not a text regex.'
PARAMETERS['Grep']['text']['description'] = 'Literal substring to search inside the matched files.'


class DeepSeekFileProposer:
    def __init__(self, workspace, gateway):
        self.ws = EvidenceWorkspace(workspace)
        self.gateway = gateway

    def tool(self, name, args):
        if name == 'Read':
            offset = args.get('offset', 0)
            value = self.ws.read(args['path'], offset, args.get('limit', 32000))
            total = len(self.ws.path(args['path']).read_text())
            return json.dumps({'content': value, 'offset': offset, 'next_offset': offset+len(value),
                               'total_chars': total, 'truncated': offset+len(value) < total})
        if name == 'Glob':
            return json.dumps(self.ws.glob(args['pattern']))
        if name == 'Grep':
            rows = []
            for path in self.ws.glob(args['pattern']):
                source = self.ws.path(path)
                text = source.read_text()
                self.ws.event({'operation': 'grep', 'path': path, 'total_chars': len(text)})
                rows.extend(f'{path}:{n}: {line}' for n, line in enumerate(text.splitlines(), 1) if args['text'] in line)
            text = '\n'.join(rows)
            return json.dumps({'matches': text[:32000], 'truncated': len(text) > 32000})
        if name == 'Write':
            self.ws.write(args['path'], args['content'])
            return 'written'
        if name == 'Edit':
            path = self.ws.path(args['path'], write=True)
            text = path.read_text()
            if text.count(args['old']) != 1:
                raise ValueError('Edit must have exactly one match in the returned content')
            self.ws.write(args['path'], text.replace(args['old'], args['new'], 1))
            return 'edited'
        raise ValueError('Unknown optimizer tool')

    def __call__(self, prompt, iteration):
        messages = [{'role': 'system', 'content':
            'Improve the mini-SWE-agent harness using public files. Read history and harness sources. '
            'Preserve model, task budget and grading. Never encode task-specific answers. '
            'Write each candidate under candidates/<name>/harness/, with agent.py, swebench.yaml and LICENSE.md. '
            'Use Finish with name/import_path/hypothesis/changes records. No host access or private grader evidence. '
            'Retain generic improvements; do not interpret tool errors as evidence of benchmark success.'},
            {'role': 'user', 'content': prompt}]
        while True:
            response = self.gateway(model='deepseek-flash', messages=messages, tools=TOOLS)
            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))
            calls = message.tool_calls or []
            if not calls:
                raise ValueError('Proposer returned no tool action or Finish')
            for call in calls:
                args = json.loads(call.function.arguments)
                if call.function.name == 'Finish':
                    if len(calls) != 1 or not args['candidates'] or len(args['candidates']) > 3:
                        raise ValueError('Finish must be a single call with 1-3 candidates')
                    return args['candidates']
                try:
                    result = self.tool(call.function.name, args)
                except (ValueError, OSError) as exc:
                    result = 'ToolError: '+type(exc).__name__
                messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': result})
