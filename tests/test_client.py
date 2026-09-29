import io
import json
from unittest.mock import patch
import urllib.error

import pytest

from coderoute.config import Config, load_local_env
from coderoute.models.client import ChatClient, ModelAPIError


def test_live_config_is_required(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="base_url"):
        ChatClient(Config())
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        ChatClient(Config(base_url="https://example.com/v1"))


def test_chat_request_and_usage(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-test-key")
    client = ChatClient(Config(base_url="https://example.com/v1"))
    response = {"choices": [{"message": {"content": '{"tool":"run_test","args":{}}'}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 12}, "model": "served-model"}
    with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as call:
        reply = client.complete([{"role": "user", "content": "Return JSON"}], 5)
    request = call.call_args.args[0]
    assert request.full_url == "https://example.com/v1/chat/completions"
    assert json.loads(request.data)["model"] == "deepseek-v4-flash"
    assert reply.usage["prompt_tokens"] == 30
    assert reply.model == "served-model"


@pytest.mark.parametrize("value", [0, -1, True, "16"])
def test_invalid_budget_rejected(tmp_path, value):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"max_steps": value}))
    with pytest.raises(ValueError):
        Config.load(path)


def test_local_env_preserves_existing_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEROUTE_TEST_EXISTING", "existing")
    monkeypatch.delenv("CODEROUTE_TEST_NEW", raising=False)
    path = tmp_path / ".env"
    path.write_text('# comment\nCODEROUTE_TEST_EXISTING=override\nCODEROUTE_TEST_NEW="literal$value"\n')
    load_local_env(path)
    import os
    assert os.environ["CODEROUTE_TEST_EXISTING"] == "existing"
    assert os.environ["CODEROUTE_TEST_NEW"] == "literal$value"
    monkeypatch.delenv("CODEROUTE_TEST_NEW")


def test_http_error_retains_status_without_provider_body(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-secret")
    client = ChatClient(Config(base_url="https://example.com/v1"))
    error = urllib.error.HTTPError('https://example.com', 403, 'private-provider-message', {}, None)
    with patch('urllib.request.urlopen', side_effect=error):
        with pytest.raises(ModelAPIError) as caught:
            client.complete([], 2)
    assert caught.value.status_code == 403
    assert str(caught.value) == 'Model API returned HTTP 403'
