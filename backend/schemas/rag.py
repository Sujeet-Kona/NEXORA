from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[int] | None = Field(default=None, min_length=1, max_length=100)


class RAGSourceResponse(BaseModel):
    citation_index: int
    chunk_id: int
    document_id: int
    document_name: str | None
    chunk_index: int
    score: float
    page_start: int | None
    page_end: int | None


class RAGTimingResponse(BaseModel):
    retrieval_ms: float
    generation_ms: float
    ttft_ms: float | None
    total_ms: float


class RAGUsageResponse(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[RAGSourceResponse]
    timing: RAGTimingResponse
    usage: RAGUsageResponse | None
