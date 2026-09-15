from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    question: str = Field(min_length=1)


class RAGSourceResponse(BaseModel):
    chunk_id: int
    document_id: int
    chunk_index: int
    score: float


class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[RAGSourceResponse]
