from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import ValidationError

from backend.core.config import Settings
from backend.core.exceptions import (
    LLMConfigurationError,
    LLMGenerationError,
)
from backend.services.llm.ollama_client import OllamaLLMClient
from backend.services.llm.openai_client import (
    OpenAICompatibleLLMClient,
)
from backend.services.llm.provider import build_llm_client


class _StubConfig:
    def __init__(self, provider):
        self.llm_provider = provider


def _client_with_fake(result, *, api_key="sk-test", model="gpt-test"):
    client = OpenAICompatibleLLMClient(
        api_key=api_key,
        model=model,
    )

    completions = SimpleNamespace(
        create=lambda **kwargs: (
            _raise(result)
            if isinstance(result, Exception)
            else result
        )
    )

    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )

    return client


def _raise(exc):
    raise exc


# --- provider selection -------------------------------------------------


def test_build_llm_client_selects_ollama():
    client = build_llm_client(_StubConfig("ollama"))

    assert isinstance(client, OllamaLLMClient)


def test_build_llm_client_selects_openai():
    client = build_llm_client(_StubConfig("openai"))

    assert isinstance(client, OpenAICompatibleLLMClient)


def test_build_llm_client_normalizes_provider_case():
    client = build_llm_client(_StubConfig("  OpenAI  "))

    assert isinstance(client, OpenAICompatibleLLMClient)


def test_build_llm_client_rejects_unknown_provider():
    with pytest.raises(LLMConfigurationError, match="Unsupported"):
        build_llm_client(_StubConfig("anthropic"))


def test_settings_reject_invalid_provider():
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://u:p@localhost/db",
            jwt_secret_key="x",
            llm_provider="bogus",
        )


def test_settings_default_provider_is_ollama():
    config = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",
        jwt_secret_key="x",
    )

    assert config.llm_provider == "ollama"


def test_settings_normalize_provider_value():
    config = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",
        jwt_secret_key="x",
        llm_provider=" OpenAI ",
    )

    assert config.llm_provider == "openai"


# --- openai-compatible configuration guards -----------------------------


def test_generate_requires_api_key():
    client = OpenAICompatibleLLMClient(api_key=None, model="gpt-test")

    with pytest.raises(
        LLMGenerationError,
        match="OPENAI_API_KEY is not configured",
    ):
        client.generate(system_prompt="s", user_prompt="q")


def test_generate_requires_model():
    client = OpenAICompatibleLLMClient(api_key="sk-test", model=None)

    with pytest.raises(
        LLMGenerationError,
        match="OPENAI_MODEL is not configured",
    ):
        client.generate(system_prompt="s", user_prompt="q")


# --- openai-compatible generate -----------------------------------------


def test_generate_returns_stripped_content():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="  grounded [1]  ")
            )
        ]
    )

    client = _client_with_fake(response)

    assert (
        client.generate(system_prompt="s", user_prompt="q")
        == "grounded [1]"
    )


def test_generate_handles_missing_choices():
    client = _client_with_fake(SimpleNamespace(choices=[]))

    with pytest.raises(
        LLMGenerationError,
        match="did not contain a completion",
    ):
        client.generate(system_prompt="s", user_prompt="q")


def test_generate_handles_non_text_content():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
    )

    client = _client_with_fake(response)

    with pytest.raises(
        LLMGenerationError,
        match="did not contain text content",
    ):
        client.generate(system_prompt="s", user_prompt="q")


def test_generate_maps_timeout():
    request = httpx.Request("POST", "http://x")
    client = _client_with_fake(openai.APITimeoutError(request=request))

    with pytest.raises(LLMGenerationError, match="timed out"):
        client.generate(system_prompt="s", user_prompt="q")


def test_generate_maps_connection_error():
    request = httpx.Request("POST", "http://x")
    client = _client_with_fake(
        openai.APIConnectionError(request=request)
    )

    with pytest.raises(LLMGenerationError, match="Unable to connect"):
        client.generate(system_prompt="s", user_prompt="q")


def test_generate_maps_not_found():
    request = httpx.Request("POST", "http://x")
    response = httpx.Response(404, request=request)
    client = _client_with_fake(
        openai.NotFoundError("nope", response=response, body=None),
        model="missing-model",
    )

    with pytest.raises(
        LLMGenerationError,
        match="model 'missing-model' was not found",
    ):
        client.generate(system_prompt="s", user_prompt="q")


def test_generate_maps_status_error_without_leaking_key():
    request = httpx.Request("POST", "http://x")
    response = httpx.Response(500, request=request)
    client = _client_with_fake(
        openai.APIStatusError(
            "boom",
            response=response,
            body=None,
        ),
        api_key="sk-super-secret-value",
    )

    with pytest.raises(LLMGenerationError) as excinfo:
        client.generate(system_prompt="s", user_prompt="q")

    assert "HTTP 500" in str(excinfo.value)
    assert "sk-super-secret-value" not in str(excinfo.value)


# --- openai-compatible stream -------------------------------------------


def test_stream_yields_content_deltas():
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="a"))]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="b"))]
        ),
        SimpleNamespace(choices=[]),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]
        ),
    ]

    client = _client_with_fake(iter(chunks))

    deltas = list(client.stream(system_prompt="s", user_prompt="q"))

    assert deltas == ["a", "b"]


def test_stream_requires_api_key():
    client = OpenAICompatibleLLMClient(api_key=None, model="gpt-test")

    with pytest.raises(
        LLMGenerationError,
        match="OPENAI_API_KEY is not configured",
    ):
        list(client.stream(system_prompt="s", user_prompt="q"))


def test_stream_maps_connection_error():
    request = httpx.Request("POST", "http://x")

    client = _client_with_fake(
        openai.APIConnectionError(request=request)
    )

    with pytest.raises(LLMGenerationError, match="Unable to connect"):
        list(client.stream(system_prompt="s", user_prompt="q"))
