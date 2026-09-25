import httpx
import pytest

from backend.core.exceptions import LLMGenerationError
from backend.services.llm.ollama_client import OllamaLLMClient


def test_generate_requires_model(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm.ollama_client.settings.ollama_model",
        None,
    )

    client = OllamaLLMClient()

    with pytest.raises(
        LLMGenerationError,
        match="OLLAMA_MODEL is not configured",
    ):
        client.generate(
            system_prompt="system",
            user_prompt="question",
        )


def test_generate_returns_message_content(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "content": "  grounded answer  ",
                }
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
        timeout=12,
        num_predict=256,
    )

    result = client.generate(
        system_prompt="system",
        user_prompt="question",
    )

    assert result == "grounded answer"
    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["kwargs"]["timeout"] == 12

    payload = captured["kwargs"]["json"]

    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert payload["options"]["num_predict"] == 256


def test_generate_handles_timeout(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Ollama request timed out",
    ):
        client.generate(
            system_prompt="system",
            user_prompt="question",
        )


def test_generate_handles_connection_error(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Unable to connect to Ollama",
    ):
        client.generate(
            system_prompt="system",
            user_prompt="question",
        )


def test_generate_handles_missing_model(monkeypatch):
    class FakeResponse:
        status_code = 404

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "not found",
                request=httpx.Request("POST", "http://ollama.test/api/chat"),
                response=httpx.Response(404),
            )

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="missing-model",
    )

    with pytest.raises(
        LLMGenerationError,
        match="model 'missing-model' was not found",
    ):
        client.generate(
            system_prompt="system",
            user_prompt="question",
        )


def test_generate_handles_invalid_json(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("invalid json")

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Ollama returned invalid JSON",
    ):
        client.generate(
            system_prompt="system",
            user_prompt="question",
        )


def test_generate_handles_missing_message(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"unexpected": "response"}

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Ollama response did not contain a message",
    ):
        client.generate(
            system_prompt="system",
            user_prompt="question",
        )


def test_generate_handles_non_text_content(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": None}}

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Ollama response did not contain text content",
    ):
        client.generate(
            system_prompt="system",
            user_prompt="question",
        )


def capture_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "answer"}}

    def fake_post(url, **kwargs):
        captured["payload"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    return captured


def test_generate_disables_thinking_by_default(monkeypatch):
    captured = capture_payload(monkeypatch)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    client.generate(
        system_prompt="system",
        user_prompt="question",
    )

    assert captured["payload"]["think"] is False


def test_generate_honours_think_override(monkeypatch):
    captured = capture_payload(monkeypatch)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
        think=True,
    )

    client.generate(
        system_prompt="system",
        user_prompt="question",
    )

    assert captured["payload"]["think"] is True


def test_generate_reads_think_from_settings(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm.ollama_client.settings.ollama_think",
        True,
    )

    assert OllamaLLMClient().think is True


def test_generate_reads_num_predict_from_settings(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm.ollama_client.settings.ollama_num_predict",
        64,
    )

    assert OllamaLLMClient().num_predict == 64
