import httpx

from backend.core.config import settings
from backend.core.exceptions import LLMGenerationError


class OllamaLLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        num_predict: int | None = None,
        think: bool | None = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = (
            settings.ollama_timeout if timeout is None else timeout
        )
        self.num_predict = (
            settings.ollama_num_predict
            if num_predict is None
            else num_predict
        )
        self.think = (
            settings.ollama_think if think is None else think
        )

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if not self.model:
            raise LLMGenerationError(
                "OLLAMA_MODEL is not configured"
            )

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "think": self.think,
                    "options": {
                        "num_predict": self.num_predict,
                    },
                    "keep_alive": "5m",
                },
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMGenerationError(
                "Ollama request timed out"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMGenerationError(
                "Unable to connect to Ollama"
            ) from exc

        if response.status_code == 404:
            raise LLMGenerationError(
                f"Ollama model '{self.model}' was not found"
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMGenerationError(
                f"Ollama request failed with HTTP {response.status_code}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMGenerationError(
                "Ollama returned invalid JSON"
            ) from exc

        message = data.get("message")
        if not isinstance(message, dict):
            raise LLMGenerationError(
                "Ollama response did not contain a message"
            )

        content = message.get("content")
        if not isinstance(content, str):
            raise LLMGenerationError(
                "Ollama response did not contain text content"
            )

        return content.strip()
