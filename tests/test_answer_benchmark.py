from types import SimpleNamespace

from backend.evaluation.answer_benchmark import _relevant_chunk_ids
from backend.evaluation.dataset import EvaluationCase


def test_answer_benchmark_uses_shared_pdf_text_normalization():
    chunks = [
        SimpleNamespace(
            id=17,
            document_id=4,
            chunk_index=0,
            text="Low-Rank Adaptation of Large\\nLanguage Models",
            page_start=1,
            page_end=1,
            organization_id=2,
        )
    ]
    case = EvaluationCase(
        question="What is the full title of the LoRA paper?",
        document="LORA.pdf",
        anchor="Low-Rank Adaptation of Large Language Models",
        expected=("LoRA: Low-Rank Adaptation of Large Language Models",),
    )

    assert _relevant_chunk_ids(
        chunks,
        {4: "LORA.pdf"},
        case,
    ) == {17}


def test_answer_benchmark_keeps_ground_truth_document_scoped():
    chunks = [
        SimpleNamespace(
            id=17,
            document_id=4,
            chunk_index=0,
            text="Low-Rank Adaptation of Large Language Models",
            page_start=1,
            page_end=1,
            organization_id=2,
        )
    ]
    case = EvaluationCase(
        question="What is the full title of the LoRA paper?",
        document="LORA.pdf",
        anchor="Low-Rank Adaptation of Large Language Models",
        expected=("LoRA: Low-Rank Adaptation of Large Language Models",),
    )

    try:
        _relevant_chunk_ids(chunks, {4: "Different.pdf"}, case)
    except RuntimeError as exc:
        assert str(exc) == (
            "Ground truth not found for: "
            "What is the full title of the LoRA paper?"
        )
    else:
        raise AssertionError("Ground truth must remain document-scoped")


def test_answer_benchmark_requires_inline_citation_to_relevant_source():
    from backend.evaluation.answer_benchmark import _has_grounded_citation

    sources = [
        SimpleNamespace(chunk_id=17),
        SimpleNamespace(chunk_id=18),
    ]

    assert _has_grounded_citation("The title is LoRA [1].", sources, {17})
    assert not _has_grounded_citation("The title is LoRA.", sources, {17})
    assert not _has_grounded_citation("The title is LoRA [2].", sources, {17})
    assert not _has_grounded_citation("The title is LoRA [3].", sources, {17})
    assert not _has_grounded_citation("The title is LoRA [1] [3].", sources, {17})
