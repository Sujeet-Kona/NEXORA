from typing import Iterator

import openai
from openai import OpenAI

from backend.core.config import settings
from backend.core.exceptions import LLMGenerationError


class OpenAICompatibleLLMClient:
    """LLM client for any OpenAI-compatible chat completions API.

    Works with the hosted OpenAI API and with self-hosted gateways that
    expose the same ``/chat/completions`` contract via ``OPENAI_BASE_URL``.
    The API key is never logged or embedded in error messages.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ):
        self.api_key = (
            settings.openai_api_key if api_key is None else api_key
        )
        self.model = (
            settings.openai_model if model is None else model
        )
        self.base_url = (
            settings.openai_base_url if base_url is None else base_url
        )
        self.timeout = (
            settings.openai_timeout if timeout is None else timeout
        )
        self.max_tokens = (
            settings.openai_max_tokens
            if max_tokens is None
            else max_tokens
        )
        self._client: OpenAI | None = None

    def _require_configuration(self) -> None:
        if not self.api_key:
            raise LLMGenerationError(
                "OPENAI_API_KEY is not configured"
            )

        if not self.model:
            raise LLMGenerationError(
                "OPENAI_MODEL is not configured"
            )

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )

        return self._client

    def _messages(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> list[dict]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _create(self, *, system_prompt: str, user_prompt: str, stream: bool):
        return self._get_client().chat.completions.create(
            model=self.model,
            messages=self._messages(system_prompt, user_prompt),
            max_tokens=self.max_tokens,
            stream=stream,
        )

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self._require_configuration()

        try:
            response = self._create(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                stream=False,
            )
        except openai.APITimeoutError as exc:
            raise LLMGenerationError(
                "OpenAI-compatible request timed out"
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMGenerationError(
                "Unable to connect to the OpenAI-compatible provider"
            ) from exc
        except openai.NotFoundError as exc:
            raise LLMGenerationError(
                f"OpenAI-compatible model '{self.model}' was not found"
            ) from exc
        except openai.APIStatusError as exc:
            raise LLMGenerationError(
                "OpenAI-compatible request failed with HTTP "
                f"{exc.status_code}"
            ) from exc
        except openai.APIError as exc:
            raise LLMGenerationError(
                "OpenAI-compatible request failed"
            ) from exc

        choices = getattr(response, "choices", None)

        if not choices:
            raise LLMGenerationError(
                "OpenAI-compatible response did not contain a completion"
            )

        content = getattr(choices[0].message, "content", None)

        if not isinstance(content, str):
            raise LLMGenerationError(
                "OpenAI-compatible response did not contain text content"
            )

        return content.strip()

    def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Iterator[str]:
        self._require_configuration()

        try:
            chunks = self._create(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                stream=True,
            )

            for chunk in chunks:
                choices = getattr(chunk, "choices", None)

                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None)

                if isinstance(content, str) and content:
                    yield content
        except openai.APITimeoutError as exc:
            raise LLMGenerationError(
                "OpenAI-compatible request timed out"
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMGenerationError(
                "Unable to connect to the OpenAI-compatible provider"
            ) from exc
        except openai.NotFoundError as exc:
            raise LLMGenerationError(
                f"OpenAI-compatible model '{self.model}' was not found"
            ) from exc
        except openai.APIStatusError as exc:
            raise LLMGenerationError(
                "OpenAI-compatible request failed with HTTP "
                f"{exc.status_code}"
            ) from exc
        except openai.APIError as exc:
            raise LLMGenerationError(
                "OpenAI-compatible request failed"
            ) from exc
