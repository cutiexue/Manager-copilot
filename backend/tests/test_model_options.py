"""Request settings per provider, checked against each provider's documented parameters."""

from types import SimpleNamespace

from langchain_openai import ChatOpenAI

from llm import model_options


def config(provider, model):
    return SimpleNamespace(provider=provider, model=model, api_key="test-key", base_url="https://example.invalid/v1")


def test_deepseek_gets_only_documented_parameters():
    # api-docs.deepseek.com (checked 2026-10-24): max_tokens, thinking; no parallel_tool_calls.
    options = model_options(config("deepseek", "deepseek-flash"))
    assert options["max_tokens"] == 2048
    assert options["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "model_kwargs" not in options and "max_completion_tokens" not in options
    ChatOpenAI(**options)  # builds without contacting the API


def test_openai_keeps_sequential_tool_calls():
    options = model_options(config("openai", "gpt-4.1-mini"))
    assert options["max_completion_tokens"] == 4096
    assert options["model_kwargs"] == {"parallel_tool_calls": False}
    assert "extra_body" not in options
    ChatOpenAI(**options)
