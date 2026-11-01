"""One budgeted, recorded DeepSeek reflection; crash recovery never resamples."""
import hashlib
import json
from pathlib import Path
import time

from acl_rsi.deepseek import DeepSeekClient, UsageLedger
from acl_rsi.settings import write_json
from .common import read


class DeepSeekReflection:
    def __init__(self, cfg, work, client_factory=DeepSeekClient):
        self.cfg, self.work, self.client_factory = cfg, Path(work), client_factory

    def __call__(self, prompt):
        messages = [{'role': 'user', 'content': prompt}] if isinstance(prompt, str) else prompt
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        attempt = self.work / 'reflection-attempt.json'
        cached = self.work / 'reflection-completion.json'
        if cached.exists():
            response = read(cached)
            if response['prompt_sha256'] != digest:
                raise RuntimeError('Reflection context changed; no automatic new proposal')
            if response['finish_reason'] != 'stop' or not response['content']:
                raise RuntimeError('Cached reflection was incomplete; no automatic retry')
            return response['content']
        if attempt.exists():
            raise RuntimeError('Incomplete reflection attempt; manual recovery required, no paid retry')
        ledger = UsageLedger(self.work / 'search_usage.json', self.cfg['search']['max_calls'], self.cfg['search']['max_tokens'])
        client = self.client_factory(self.cfg, ledger, 'gepa_reflection', self.cfg['search'])
        create = client.client.chat.completions.create
        def recorded_create(**payload):
            rid = ledger.update(lambda state: state['requests'][-1]['id'])
            write_json(self.work / 'search_requests' / f'{rid}.json', payload)
            started = time.time()
            try:
                return create(**payload)
            finally:
                ledger.update(lambda state: next(r for r in state['requests'] if r['id'] == rid).update(
                    api_started_at=started, api_finished_at=time.time(), api_seconds=time.time() - started))
        client.client.chat.completions.create = recorded_create
        write_json(attempt, {'prompt_sha256': digest, 'automatic_resampling': False})
        try:
            response = client.complete(messages)
            choice = response.choices[0]
            completion = {'prompt_sha256': digest, 'finish_reason': choice.finish_reason,
                          'content': choice.message.content or ''}
            write_json(cached, completion)
            if choice.finish_reason != 'stop' or not completion['content']:
                raise RuntimeError('Incomplete reflection output; raw response and usage retained')
            return completion['content']
        finally:
            client.client.close()
