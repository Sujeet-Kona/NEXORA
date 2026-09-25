from dataclasses import dataclass
import re
from typing import Iterator

from backend.core.exceptions import LLMGenerationError
from backend.services.llm.base import LLMClient
from backend.services.retrieval_service import RetrievedChunk


SYSTEM_PROMPT = """
You are Nexora, a grounded enterprise knowledge assistant.
Answer the user's question using only the supplied document context.
Each context passage begins with a bracketed number such as [1].
Cite the passages you rely on by placing their bracketed numbers
inline in your answer, for example: "Staff receive 20 days of
annual leave [1]." Only cite passages that actually support a
statement, and use the number that passage was given.
Do not invent facts, use outside knowledge, or contradict the context.
If the context does not contain enough information, say so clearly.
Keep the answer concise and directly answer the user's question.
""".strip()


NO_CONTEXT_ANSWER = (
    "The available documents do not contain "
    "enough information to answer this question."
)


# Citation markers are the bracketed passage numbers the prompt
# assigns (1..N, N is small). Bounded to two digits so bracketed
# years or other large numbers in the prose are left untouched.
_CITATION_MARKER = re.compile(r"( ?)\[(\d{1,2})\]")


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    sources: list[RetrievedChunk]


def _passages(
    chunks: list[RetrievedChunk],
) -> list[str]:
    return [
        chunk.text.strip()
        for chunk in chunks
        if chunk.text.strip()
    ]


def _build_context(
    passages: list[str],
) -> str:
    return "\n\n".join(
        "[{}]\n{}".format(index, passage)
        for index, passage in enumerate(passages, start=1)
    )


def _build_user_prompt(
    question: str,
    passages: list[str],
) -> str:
    return (
        "Document context:\n\n"
        f"{_build_context(passages)}\n\n"
        "User question:\n"
        f"{question.strip()}"
    )


def _strip_invalid_citations(
    answer: str,
    valid_count: int,
) -> str:
    def replace_marker(match: re.Match) -> str:
        number = int(match.group(2))

        if 1 <= number <= valid_count:
            return match.group(0)

        return ""

    return _CITATION_MARKER.sub(
        replace_marker,
        answer,
    ).strip()


def generate_answer(
    *,
    question: str,
    chunks: list[RetrievedChunk],
    llm_client: LLMClient,
) -> GeneratedAnswer:
    if not question.strip():
        raise ValueError(
            "Question cannot be empty"
        )

    if not chunks:
        return GeneratedAnswer(
            answer=NO_CONTEXT_ANSWER,
            sources=[],
        )

    passages = _passages(chunks)

    user_prompt = _build_user_prompt(question, passages)

    answer = llm_client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    ).strip()

    if not answer:
        raise LLMGenerationError(
            "LLM returned an empty answer"
        )

    answer = _strip_invalid_citations(
        answer,
        len(passages),
    )

    return GeneratedAnswer(
        answer=answer,
        sources=list(chunks),
    )


def stream_answer(
    *,
    question: str,
    chunks: list[RetrievedChunk],
    llm_client: LLMClient,
) -> Iterator[str]:
    if not question.strip():
        raise ValueError(
            "Question cannot be empty"
        )

    if not chunks:
        raise ValueError(
            "Cannot stream without retrieved context"
        )

    passages = _passages(chunks)

    user_prompt = _build_user_prompt(question, passages)

    for delta in llm_client.stream(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    ):
        yield delta


def finalize_streamed_answer(
    answer: str,
    chunks: list[RetrievedChunk],
) -> str:
    return _strip_invalid_citations(
        answer,
        len(_passages(chunks)),
    )
