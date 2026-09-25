from typing import Iterator, Protocol


class LLMClient(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        ...

    def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Iterator[str]:
        ...
