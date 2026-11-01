"""Record payloads and API timing around the unchanged original SWE worker."""
import time

from acl_rsi import worker as original
from acl_rsi.settings import write_json


class RecordedModel(original.DeepSeekMiniModel):
    def __init__(self, cfg, config, ledger_path):
        super().__init__(cfg, config, ledger_path)
        create = self.client.client.chat.completions.create

        def recorded_create(**payload):
            rid = self.ledger.update(lambda state: state['requests'][-1]['id'])
            write_json(ledger_path.parent / 'api-requests' / f'{rid}.json', payload)
            started = time.time()
            try:
                return create(**payload)
            finally:
                ended = time.time()
                self.ledger.update(lambda state: next(r for r in state['requests'] if r['id'] == rid).update(
                    api_started_at=started, api_finished_at=ended, api_seconds=ended - started))

        self.client.client.chat.completions.create = recorded_create


if __name__ == '__main__':
    original.DeepSeekMiniModel = RecordedModel
    original.main()
