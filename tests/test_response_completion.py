import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from coderoute.config import Config
from coderoute.factory import build_harness
from coderoute.harness import RepairHarness
from coderoute.models.client import ChatClient, ModelReply
from coderoute.multi_harness import MultiAgentHarness
from coderoute.models.multi_demo import MultiDemoClient
from coderoute.routers.hybrid import HybridRouter


DEMO = Path(__file__).resolve().parents[1] / 'examples' / 'demo_repo'


@pytest.mark.parametrize('mode', ['', 'enabled', 'disabled'])
def test_thinking_wire_format_and_nullable_content(monkeypatch, mode):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')
    client = ChatClient(Config(base_url='https://example.com', thinking_mode=mode))
    response = {'choices': [{'message': {'content': None}, 'finish_reason': 'length'}],
                'usage': {'completion_tokens': 4096}}
    with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as call:
        reply = client.complete([], 1)
    body = json.loads(call.call_args.args[0].data)
    assert body.get('thinking') == ({'type': mode} if mode else None)
    assert reply.finish_reason == 'length'
    assert reply.content == '' and reply.usage['completion_tokens'] == 4096


def test_lightweight_does_not_inherit_main_thinking(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setenv('CODEROUTE_LIGHTWEIGHT_API_KEY', 'test-light-key')
    config = Config(base_url='https://example.com', thinking_mode='disabled',
                    lightweight_base_url='https://other.example.com', lightweight_model='small')
    harness = build_harness(config, 'hybrid')
    assert harness.client.config.thinking_mode == 'disabled'
    assert harness.lightweight_client.config.thinking_mode == ''


@pytest.mark.parametrize('value', ['automatic', None, 0])
def test_invalid_thinking_configuration(tmp_path, value):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'thinking_mode': value}))
    with pytest.raises(ValueError, match='thinking_mode'):
        Config.load(path)


@pytest.mark.parametrize('harness_type', [RepairHarness, MultiAgentHarness])
@pytest.mark.parametrize('content,reason,error', [
    ('{"tool":"read_file","args":{"path":"config_reader.py"}}', 'length', 'output_truncated'),
    ('  ', 'stop', 'empty_response'),
    ('{}', 'content_filter', 'unexpected_finish_reason')])
def test_unusable_response_is_counted_but_not_executed_or_retried(tmp_path, harness_type, content, reason, error):
    class Client:
        mode = 'live'
        calls = 0

        def complete(self, messages, timeout):
            self.calls += 1
            return ModelReply(content, {'prompt_tokens': 10, 'completion_tokens': 32}, 'test', reason)

    client = Client()
    root = tmp_path / 'run'
    state = harness_type(Config(), client).run(DEMO, 'Fix blanks', root)
    assert state.status == 'execution_error' and error in state.stop_reason
    assert client.calls == 1
    metrics = json.loads((root / 'metrics.json').read_text())
    assert metrics['tool_calls'] == 0
    assert metrics['output_tokens'] == 32 and metrics['usage_missing_calls'] == 0
    assert metrics['response_errors'][error] == 1
    events = json.loads((root / 'trajectory.json').read_text())
    response = next(e for e in events if e.get('event') == 'model_response')
    assert response['finish_reason'] == reason
    assert response['response_error'] == error


@pytest.mark.parametrize('budget,escalations', [(48, 3), (3, 0)])
def test_truncated_lightweight_falls_back_only_with_budget(tmp_path, budget, escalations):
    class Light:
        mode = 'mock'

        def complete(self, messages, timeout):
            return ModelReply('', {'prompt_tokens': 10, 'completion_tokens': 512}, 'light', 'length')

    root = tmp_path / 'run'
    state = MultiAgentHarness(Config(max_model_calls=budget), MultiDemoClient(),
                              HybridRouter(), Light()).run(DEMO, 'blank', root)
    metrics = json.loads((root / 'metrics.json').read_text())
    assert state.status == ('succeeded' if escalations else 'budget_exhausted')
    assert metrics['llm_escalations'] == escalations
    assert metrics['response_errors']['output_truncated'] == metrics['lightweight_model_calls']
    assert metrics['lightweight_output_tokens'] == 512 * metrics['lightweight_model_calls']
