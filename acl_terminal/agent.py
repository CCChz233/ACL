import asyncio
import json
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from harbor.agents.base import BaseAgent
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.docker import DockerEnvironment

from acl_rsi.deepseek import BudgetExceeded, ProviderError
from acl_rsi.model import DeepSeekMiniModel
from acl_rsi.settings import ROOT, write_json


class ShellBridge:
    def __init__(self, environment, loop, seconds=60):
        self.environment, self.loop, self.seconds = environment, loop, seconds
        self.stopped = threading.Event()

    def execute(self, action):
        if self.stopped.is_set():
            raise RuntimeError('Agent stopped')
        future = asyncio.run_coroutine_threadsafe(
            self.environment.exec(action['command'], timeout_sec=self.seconds), self.loop)
        try:
            result = future.result(timeout=self.seconds + 30)
            output = {'output': (result.stdout or '') + (result.stderr or ''),
                      'returncode': result.return_code, 'exception_info': ''}
        except Exception as exc:
            future.cancel()
            output = {'output': '', 'returncode': -1,
                      'exception_info': f'Command failed: {type(exc).__name__}'}
        DockerEnvironment._check_finished(self, output)
        return output

    def get_template_vars(self):
        return {}

    def serialize(self):
        return {'info': {'config': {'environment_type': 'harbor-docker-shell-bridge',
                                  'command_timeout_sec': self.seconds}}}


class PilotAgent(BaseAgent):
    def __init__(self, *args, pilot_config, wall_seconds=900, **kwargs):
        super().__init__(*args, **kwargs)
        self.pilot_config = Path(pilot_config)
        self.wall_seconds = int(wall_seconds)

    @staticmethod
    def name():
        return 'mini-swe-agent-deepseek-terminal-pilot'

    def version(self):
        return '2.4.6+terminal-adapter-v1'

    async def setup(self, environment):
        pass

    async def run(self, instruction, environment, context):
        load_dotenv(ROOT / '.env', override=False)
        cfg = json.loads(self.pilot_config.read_text())
        bridge = ShellBridge(environment, asyncio.get_running_loop(), cfg['target']['command_seconds'])
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        model = DeepSeekMiniModel(cfg, cfg['templates'], self.logs_dir / 'usage.json')
        # Log exact public API payloads and wall latency without credentials/headers.
        create = model.client.client.chat.completions.create
        def recorded_create(**payload):
            rid = model.ledger.update(lambda state: state['requests'][-1]['id'])
            requests = self.logs_dir / 'requests'
            requests.mkdir(exist_ok=True)
            write_json(requests / f'{rid}.json', payload)
            started = time.time()
            try:
                return create(**payload)
            finally:
                model.ledger.update(lambda state: next(row for row in state['requests'] if row['id'] == rid).update(
                    api_started_at=started, api_finished_at=time.time(), api_seconds=time.time() - started))
        model.client.client.chat.completions.create = recorded_create
        query = model.query
        def guarded_query(messages, **kwargs):
            if bridge.stopped.is_set():
                raise RuntimeError('Agent stopped')
            return query(messages, **kwargs)
        model.query = guarded_query
        agent = DefaultAgent(model, bridge, **cfg['agent'], step_limit=0, cost_limit=0,
                             wall_time_limit_seconds=self.wall_seconds,
                             output_path=self.logs_dir / 'trajectory.json')
        def worker():
            started = time.time()
            try:
                result = agent.run(instruction)
            except BudgetExceeded as exc:
                result = {'exit_status': exc.reason, 'budget': exc.details}
            except ProviderError as exc:
                result = {'exit_status': 'ProviderError', 'error_type': exc.error_type,
                          'status_code': exc.status_code}
            except Exception as exc:
                result = {'exit_status': 'RuntimeError', 'error_type': type(exc).__name__}
            finally:
                bridge.stopped.set()
            result.update(seconds=time.time() - started, usage=model.ledger.summary())
            agent.save(self.logs_dir / 'trajectory.json', {'info': {'worker_result': result}})
            write_json(self.logs_dir / 'worker.json', result)
            return result
        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            bridge.stopped.set()
            # Wait for bounded in-flight API/command to finish before allowing grading.
            await asyncio.shield(task)
            raise
        state = json.loads((self.logs_dir / 'usage.json').read_text())
        usage = [row.get('usage', {}) for row in state['requests']]
        context.n_input_tokens = sum(u.get('prompt_tokens', 0) for u in usage)
        context.n_output_tokens = sum(u.get('completion_tokens', 0) for u in usage)
        context.n_cache_tokens = sum(u.get('prompt_cache_hit_tokens', 0) for u in usage)
        context.metadata = result


class NoopAgent(BaseAgent):
    @staticmethod
    def name():
        return 'pilot-noop-control'

    def version(self):
        return '1'

    async def setup(self, environment):
        pass

    async def run(self, instruction, environment, context):
        context.metadata = {'control': 'no-op', 'api_calls': 0}
