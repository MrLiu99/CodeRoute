import json
import math
import os
from dataclasses import dataclass, fields
from pathlib import Path


def load_local_env(path):
    """Read simple KEY=value entries without shell expansion; existing env wins."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name.isidentifier():
            raise ValueError("Invalid .env entry; expected KEY=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


@dataclass
class Config:
    model: str = "deepseek-v4-flash"
    base_url: str = ""
    api_key_env: str = "DEEPSEEK_API_KEY"
    max_steps: int = 16
    model_timeout: int = 90
    test_timeout: int = 30
    wall_timeout: int = 600
    max_output_chars: int = 12000
    max_context_chars: int = 100000
    max_tokens: int = 4096
    thinking_mode: str = ""
    max_role_turns: int = 8
    max_model_calls: int = 48
    lightweight_model: str = ""
    lightweight_base_url: str = ""
    lightweight_api_key_env: str = "CODEROUTE_LIGHTWEIGHT_API_KEY"
    lightweight_timeout: int = 30
    lightweight_max_tokens: int = 512
    lightweight_thinking_mode: str = ""
    confidence_threshold: float = 0.65
    native_tool_calls: bool = False
    protocol_recovery: bool = False
    review_validation: bool = False
    max_review_probes: int = 3
    developer_budget_handoff: bool = False
    role_context_refresh: bool = False

    @classmethod
    def load(cls, path=None):
        data = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError("Unknown config fields: " + ", ".join(sorted(unknown)))
        for field, env in (("base_url", "CODEROUTE_BASE_URL"), ("model", "CODEROUTE_MODEL"),
                           ("lightweight_base_url", "CODEROUTE_LIGHTWEIGHT_BASE_URL"),
                           ("lightweight_model", "CODEROUTE_LIGHTWEIGHT_MODEL")):
            if os.getenv(env):
                data[field] = os.environ[env]
        config = cls(**data)
        for name in ("thinking_mode", "lightweight_thinking_mode"):
            if getattr(config, name) not in ("", "enabled", "disabled"):
                raise ValueError(name + " must be empty, enabled, or disabled")
        for f in fields(cls):
            value = getattr(config, f.name)
            if f.type is bool and type(value) is not bool:
                raise ValueError(f"{f.name} must be a boolean")
            if f.type is int and (type(value) is not int or value <= 0):
                raise ValueError(f"{f.name} must be a positive integer")
            if f.type is str and not isinstance(value, str):
                raise ValueError(f"{f.name} must be a string")
            if f.type is float and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"{f.name} must be a finite number in [0,1]")
        return config
