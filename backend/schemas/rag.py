from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    question: str = Field(min_length=1)


class RAGSourceResponse(BaseModel):
    chunk_id: int
    document_id: int
    document_name: str | None
    chunk_index: int
    score: float
    page_start: int | None
    page_end: int | None


class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[RAGSourceResponse]
