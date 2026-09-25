import json

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


class FakeStreamResponse:
    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request(
                    "POST",
                    "http://ollama.test/api/chat",
                ),
                response=httpx.Response(self.status_code),
            )

    def iter_lines(self):
        yield from self._lines


def patch_stream(monkeypatch, lines, status_code=200):
    captured = {}

    def fake_stream(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeStreamResponse(lines, status_code)

    monkeypatch.setattr(httpx, "stream", fake_stream)

    return captured


def content_line(text):
    return json.dumps({"message": {"content": text}})


def test_stream_yields_content_deltas(monkeypatch):
    captured = patch_stream(
        monkeypatch,
        [
            content_line("Employees receive "),
            content_line("20 days of annual leave [1]."),
            json.dumps({"done": True}),
        ],
    )

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
        timeout=12,
        num_predict=256,
    )

    deltas = list(
        client.stream(
            system_prompt="system",
            user_prompt="question",
        )
    )

    assert deltas == [
        "Employees receive ",
        "20 days of annual leave [1].",
    ]

    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["kwargs"]["timeout"] == 12

    payload = captured["kwargs"]["json"]
    assert payload["stream"] is True
    assert payload["model"] == "qwen3:8b"
    assert payload["options"]["num_predict"] == 256


def test_stream_skips_empty_and_done_chunks(monkeypatch):
    patch_stream(
        monkeypatch,
        [
            content_line(""),
            content_line("answer"),
            json.dumps({"done": True}),
            content_line("after-done-ignored"),
        ],
    )

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    deltas = list(
        client.stream(
            system_prompt="system",
            user_prompt="question",
        )
    )

    assert deltas == ["answer"]


def test_stream_requires_model(monkeypatch):
    monkeypatch.setattr(
        "backend.services.llm.ollama_client.settings.ollama_model",
        None,
    )

    client = OllamaLLMClient()

    with pytest.raises(
        LLMGenerationError,
        match="OLLAMA_MODEL is not configured",
    ):
        list(
            client.stream(
                system_prompt="system",
                user_prompt="question",
            )
        )


def test_stream_handles_timeout(monkeypatch):
    def fake_stream(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "stream", fake_stream)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Ollama request timed out",
    ):
        list(
            client.stream(
                system_prompt="system",
                user_prompt="question",
            )
        )


def test_stream_handles_connection_error(monkeypatch):
    def fake_stream(*args, **kwargs):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx, "stream", fake_stream)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Unable to connect to Ollama",
    ):
        list(
            client.stream(
                system_prompt="system",
                user_prompt="question",
            )
        )


def test_stream_handles_missing_model(monkeypatch):
    patch_stream(monkeypatch, [], status_code=404)

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="missing-model",
    )

    with pytest.raises(
        LLMGenerationError,
        match="model 'missing-model' was not found",
    ):
        list(
            client.stream(
                system_prompt="system",
                user_prompt="question",
            )
        )


def test_stream_handles_invalid_json(monkeypatch):
    patch_stream(monkeypatch, ["not-json"])

    client = OllamaLLMClient(
        base_url="http://ollama.test",
        model="qwen3:8b",
    )

    with pytest.raises(
        LLMGenerationError,
        match="Ollama returned invalid JSON",
    ):
        list(
            client.stream(
                system_prompt="system",
                user_prompt="question",
            )
        )
