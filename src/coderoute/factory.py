from dataclasses import replace

from .harness import RepairHarness
from .models.client import ChatClient, DemoClient
from .models.lightweight_demo import LightweightDemoClient
from .models.multi_demo import MultiDemoClient
from .multi_harness import MultiAgentHarness
from .routers.hybrid import HybridRouter
from .routers.llm import LLMRouter, RuleLLMRouter


def build_harness(config, workflow, mode="live"):
    if workflow not in {"single", "fixed", "llm", "dynamic", "hybrid"}:
        raise ValueError("Unknown workflow")
    client = (DemoClient() if workflow == "single" else MultiDemoClient()) if mode == "mock" else ChatClient(config)
    if workflow == "single":
        return RepairHarness(config, client)
    if workflow == "hybrid":
        if mode == "mock":
            lightweight = LightweightDemoClient()
        else:
            if not config.lightweight_model or not config.lightweight_base_url:
                raise ValueError("Live hybrid requires lightweight_model and lightweight_base_url; no mock fallback")
            lightweight = ChatClient(replace(config, model=config.lightweight_model,
                base_url=config.lightweight_base_url, api_key_env=config.lightweight_api_key_env,
                max_tokens=config.lightweight_max_tokens, thinking_mode=config.lightweight_thinking_mode))
        return MultiAgentHarness(config, client, HybridRouter(config.confidence_threshold), lightweight)
    router = {"llm": LLMRouter, "dynamic": RuleLLMRouter}.get(workflow)
    return MultiAgentHarness(config, client, router() if router else None)
