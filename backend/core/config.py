from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    storage_backend: str = "local"
    storage_path: str = "storage"
    max_upload_size_bytes: int = 10485760

    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_batch_size: int = 32
    qdrant_upsert_batch_size: int = 32

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "nexora_document_chunks"

    retrieval_top_k: int = Field(default=2, ge=1)
    retrieval_dense_top_k: int = Field(default=10, ge=1)
    retrieval_lexical_top_k: int = Field(default=10, ge=1)
    retrieval_rerank_top_k: int = Field(default=8, ge=1)

    openai_api_key: str | None = None
    openai_model: str | None = None

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
