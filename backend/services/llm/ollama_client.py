import httpx

from backend.core.config import settings


class OllamaLLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 300.0,
    ):
        self.base_url = (
            base_url
            or settings.ollama_base_url
        ).rstrip("/")

        self.model = (
            model
            or settings.ollama_model
        )

        self.timeout = timeout

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if not self.model:
            raise RuntimeError(
                "OLLAMA_MODEL is not configured"
            )

        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                "stream": False,
            },
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()

        message = data.get("message")

        if not isinstance(message, dict):
            raise RuntimeError(
                "Ollama response did not contain a message"
            )

        content = message.get("content")

        if not isinstance(content, str):
            raise RuntimeError(
                "Ollama response did not contain text content"
            )

        return content.strip()

