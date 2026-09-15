from fastapi import Request

from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.llm.ollama_client import OllamaLLMClient


def request_embedding_service(
    request: Request,
) -> EmbeddingService:
    return request.app.state.embedding_service


def request_qdrant_repository(
    request: Request,
) -> QdrantRepository:
    return request.app.state.qdrant_repository


def request_ollama_client(
    request: Request,
) -> OllamaLLMClient:
    return request.app.state.ollama_client
