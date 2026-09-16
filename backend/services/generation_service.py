from dataclasses import dataclass

from backend.services.llm.base import LLMClient
from backend.services.retrieval_service import RetrievedChunk


SYSTEM_PROMPT = """
You are Nexora, a grounded enterprise knowledge assistant.
Answer the user's question using only the supplied document context.
Do not invent facts, use outside knowledge, or contradict the context.
If the context does not contain enough information, say so clearly.
Keep the answer concise and directly answer the user's question.
""".strip()


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    sources: list[RetrievedChunk]


def _build_context(
    chunks: list[RetrievedChunk],
) -> str:
    return "\n\n".join(
        chunk.text.strip()
        for chunk in chunks
        if chunk.text.strip()
    )


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
            answer=(
                "The available documents do not contain "
                "enough information to answer this question."
            ),
            sources=[],
        )

    user_prompt = (
        "Document context:\n\n"
        f"{_build_context(chunks)}\n\n"
        "User question:\n"
        f"{question.strip()}"
    )

    answer = llm_client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    ).strip()

    if not answer:
        raise RuntimeError(
            "LLM returned an empty answer"
        )

    return GeneratedAnswer(
        answer=answer,
        sources=list(chunks),
    )
