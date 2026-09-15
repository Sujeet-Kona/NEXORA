from functools import lru_cache

from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.llm.ollama_client import OllamaLLMClient


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


@lru_cache(maxsize=1)
def get_qdrant_repository() -> QdrantRepository:
    return QdrantRepository()


@lru_cache(maxsize=1)
def get_ollama_client() -> OllamaLLMClient:
    return OllamaLLMClient()
