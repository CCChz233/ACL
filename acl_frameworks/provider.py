"""Fixed DeepSeek gateway with exact payload/usage/timing audit, disabled by default."""
import time
import re
from pathlib import Path

from acl_rsi.deepseek import DeepSeekClient, UsageLedger
from acl_rsi.settings import write_json


def repair_xml_closure(content):
    """Recognize only the observed Flash XML-open/DSML-close serialization."""
    if content.count('<mswea_bash_command>') != 1 or '</mswea_bash_command>' in content:
        return content
    end = (r'</[｜|]+DSML[｜|]+ parameter>\s*'
           r'</[｜|]+DSML[｜|]+ invoke>\s*</[｜|]+DSML[｜|]+ calls>\s*$')
    match = re.search(end, content)
    if not match or 'DSML' in content[:match.start()]:
        return content
    return content[:match.start()]+'\n</mswea_bash_command>'


class RecordedDeepSeek:
    def __init__(self, cfg, work, role, *, enabled=False, client_factory=DeepSeekClient):
        if cfg['model'] != 'deepseek-flash' or cfg['api_base'].rstrip('/') != 'https://api.deepseek.com' or cfg.get('thinking'):
            raise ValueError('This integration fixes DeepSeek Flash, endpoint and thinking=false')
        self.cfg, self.work, self.role = cfg, Path(work), role
        self.enabled, self.factory = enabled, client_factory
        self.ledger = UsageLedger(self.work / 'usage.json', cfg['limits']['max_calls'], cfg['limits']['max_tokens'])

    def __call__(self, *, model, messages, tools=None, tool_choice=None, max_tokens=None, **kwargs):
        if model.removeprefix('openai/') != self.cfg['model']:
            raise ValueError('Unexpected upstream model; refusing silent provider/model substitution')
        if not self.enabled:
            raise RuntimeError('Model calls disabled: framework integration is not an experiment launch')
        fmt = kwargs.get('response_format') or {}
        if fmt and fmt.get('type') not in ('json_object', 'text'):
            raise ValueError('Unsupported structured output contract')
        if kwargs.get('stream'):
            raise ValueError('Streaming is not supported by the usage recorder')
        # Each invocation captures its own reservation ID. Another process can
        # append a request before the API returns; the last ledger row is unsafe.
        ledger = UsageLedger(self.ledger.path, self.ledger.max_calls, self.ledger.max_tokens)
        reserve = ledger.reserve
        request = []
        def capture(*args, **options):
            rid = reserve(*args, **options)
            request.append(rid)
            return rid
        ledger.reserve = capture
        client = self.factory(self.cfg, ledger, self.role, self.cfg['limits'])
        create = client.client.chat.completions.create

        def recorded(**payload):
            rid = request[-1]
            for key in ('temperature', 'top_p', 'stop', 'presence_penalty', 'frequency_penalty'):
                if key in kwargs:
                    payload[key] = kwargs[key]
            write_json(self.work / 'requests' / f'{rid}.json', payload)
            started = time.time()
            try:
                return create(**payload)
            finally:
                ended = time.time()
                self.ledger.update(lambda state: next(r for r in state['requests'] if r['id'] == rid).update(
                    api_started_at=started, api_finished_at=ended, api_seconds=ended-started,
                    framework_role=self.role, context_strategy=self.cfg.get('context_strategy', 'full')))
        client.client.chat.completions.create = recorded
        try:
            # The old provider enforces max calls/tokens and saves raw responses.
            response = client.complete(messages, tools=tools, tool_choice=tool_choice,
                                       json_only=fmt.get('type') == 'json_object', max_tokens=max_tokens)
            if self.cfg.get('xml_dsml_compat'):
                message = response.choices[0].message
                normalized = repair_xml_closure(message.content or '')
                if normalized != (message.content or ''):
                    write_json(self.work / 'format-repairs' / (request[-1]+'.json'), {
                        'request_id': request[-1], 'kind': 'xml-open-dsml-close',
                        'raw_response_preserved': True, 'normalized_content': normalized})
                    message.content = normalized
            return response
        finally:
            client.client.close()


def bind_litellm(gateway):
    """Explicit in-process binding, usable by HarnessFix's native model calls."""
    import litellm
    from minisweagent.models.litellm_model import LitellmModel
    from acl_rsi.deepseek import BudgetExceeded, ProviderError
    litellm.completion = gateway
    LitellmModel.abort_exceptions = list(dict.fromkeys(
        [*LitellmModel.abort_exceptions, BudgetExceeded, ProviderError]))
