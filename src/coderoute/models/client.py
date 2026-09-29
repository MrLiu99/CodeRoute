import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


@dataclass
class ModelReply:
    content: str
    usage: dict = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""
    tool_calls: list = field(default_factory=list)
    reasoning_content: str = ""
    native: bool = False

    def response_error(self):
        if self.finish_reason == "length":
            return "output_truncated"
        if self.tool_calls:
            for call in self.tool_calls:
                if (not isinstance(call, dict) or not isinstance(call.get('id'), str)
                        or not call['id'] or call.get('type') != 'function'
                        or not isinstance(call.get('function'), dict)
                        or not isinstance(call['function'].get('name'), str)
                        or not isinstance(call['function'].get('arguments'), str)):
                    return 'invalid_tool_call'
            if len({c['id'] for c in self.tool_calls}) != len(self.tool_calls):
                return 'invalid_tool_call'
            if len(self.tool_calls) != 1:
                return 'multiple_tool_calls'
        if self.finish_reason not in ("", "stop", "tool_calls" if self.tool_calls else "stop"):
            return "unexpected_finish_reason"
        if not self.content.strip():
            return "empty_response"
        if self.native and not self.tool_calls:
            return 'missing_tool_call'
        return ""

    def assistant_message(self):
        if not self.tool_calls:
            return {'role': 'assistant', 'content': self.content}
        message = {'role': 'assistant', 'content': None, 'tool_calls': self.tool_calls}
        if self.reasoning_content:
            message['reasoning_content'] = self.reasoning_content
        return message

    def require_complete(self):
        error = self.response_error()
        if error:
            raise ModelResponseError(error)


class ModelResponseError(RuntimeError):
    """A received response is unusable; usage must be recorded before raising."""
    def __init__(self, code):
        self.code = code
        super().__init__(code + ": no action executed; inspect finish_reason, max_tokens and thinking_mode")


class ModelAPIError(RuntimeError):
    """Sanitized provider error; never includes response body or credentials."""
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"Model API returned HTTP {status_code}")


class ChatClient:
    """Minimal Chat Completions adapter. No automatic paid retries."""
    mode = "live"

    def __init__(self, config):
        self.config = config
        parsed = urllib.parse.urlparse(config.base_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("Set base_url in config or CODEROUTE_BASE_URL before live mode")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Remote API endpoints must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain credentials, query or fragment")
        self.key = os.getenv(config.api_key_env)
        if not self.key:
            raise ValueError(f"Set the {config.api_key_env} environment variable before live mode")

    def complete(self, messages, timeout):
        return self._complete(messages, timeout)

    def complete_tools(self, messages, timeout, functions, routing=False):
        return self._complete(messages, timeout, functions, routing)

    def _complete(self, messages, timeout, functions=None, routing=False):
        body = {"model": self.config.model, "messages": messages,
                "stream": False, "max_tokens": self.config.max_tokens,
                "response_format": {"type": "json_object"}}
        if functions:
            body.pop('response_format')
            body.update(tools=functions, tool_choice='required', parallel_tool_calls=False)
            if urllib.parse.urlparse(self.config.base_url).hostname == 'api.deepseek.com' and self.config.thinking_mode != 'disabled':
                body['tool_choice'] = 'auto'
        if self.config.thinking_mode:
            body["thinking"] = {"type": self.config.thinking_mode}
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            # Do not persist provider bodies, request headers or credentials.
            raise ModelAPIError(error.code) from None
        except urllib.error.URLError:
            raise RuntimeError("Model API connection failed; check endpoint and connectivity") from None
        choice = data["choices"][0]
        content = choice["message"].get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ValueError("Model returned no text content")
        calls = choice['message'].get('tool_calls') or []
        if not isinstance(calls, list):
            calls = [{'invalid_payload': True}]
        if len(calls) == 1 and isinstance(calls[0], dict):
            func = calls[0].get('function') or {}
            if not isinstance(func, dict):
                func = {}
            if isinstance(func.get('arguments'), str):
                # Preserve raw arguments; the harness parses only after recording usage.
                content = (func['arguments'] if routing and func.get('name') == 'route' else
                           '{"tool":' + json.dumps(func.get('name')) + ',"args":' + func['arguments'] + '}')
        return ModelReply(content, data.get("usage") or {}, data.get("model", self.config.model),
                          choice.get("finish_reason") or "", calls,
                          choice['message'].get('reasoning_content') or '', bool(functions))


class DemoClient:
    """Scripted tool integration fixture, NOT a reasoning model or benchmark."""
    mode = "mock"

    def __init__(self):
        self.actions = iter([
            {"tool": "search_code", "args": {"query": "read_config"}},
            {"tool": "read_file", "args": {"path": "config_reader.py"}},
            {"tool": "run_test", "args": {}},
            {"tool": "edit_file", "args": {"path": "config_reader.py",
             "old": "    return json.loads(text)",
             "new": "    if text == \"\":\n        return {}\n    return json.loads(text)"}},
            {"tool": "run_test", "args": {}},
            {"tool": "edit_file", "args": {"path": "config_reader.py",
             "old": 'if text == "":', "new": "if not text.strip():"}},
            {"tool": "run_test", "args": {}},
            {"tool": "git_diff", "args": {}},
            {"tool": "finish", "args": {"summary": "Scripted empty/whitespace handling repair"}},
        ])

    def complete(self, messages, timeout):
        return ModelReply(json.dumps(next(self.actions)), model="scripted-demo")
