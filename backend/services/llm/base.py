from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class LLMGeneration:
    text: str
    usage: LLMUsage | None


class LLMStreamResult:
    def __init__(self, iterator: Iterator[str]):
        self._iterator = iterator
        self.usage: LLMUsage | None = None

    def __iter__(self) -> Iterator[str]:
        return self._iterator


class LLMClient(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMGeneration:
        ...

    def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMStreamResult:
        ...
