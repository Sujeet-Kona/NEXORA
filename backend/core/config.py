from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


SUPPORTED_LLM_PROVIDERS = ("ollama", "openai")

SUPPORTED_ENVIRONMENTS = (
    "development",
    "testing",
    "staging",
    "production",
)

# Environments where unsafe configuration must prevent startup.
PRODUCTION_ENVIRONMENTS = ("production",)

# Only HMAC algorithms are supported: the API both signs and verifies tokens
# with a single shared secret, so asymmetric algorithms are never required and
# "none" must always be rejected.
SUPPORTED_JWT_ALGORITHMS = ("HS256", "HS384", "HS512")

MIN_PRODUCTION_JWT_SECRET_LENGTH = 32

# Common placeholder/insecure secrets that must never run in production.
WEAK_JWT_SECRETS = frozenset(
    {
        "",
        "changeme",
        "change-me",
        "change_me",
        "secret",
        "jwt-secret",
        "jwt_secret",
        "dev-secret",
        "development",
        "nexora",
        "replace-with-a-secure-secret",
        "ci-only-insecure-secret-do-not-use-in-production",
    }
)


class Settings(BaseSettings):
    environment: str = "development"

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    login_max_failed_attempts: int = Field(default=5, ge=1)
    login_lockout_seconds: int = Field(default=300, ge=0)

    cors_origins: str = ""
    cors_allow_credentials: bool = True

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
    retrieval_min_relevance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )

    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_base_url: str | None = None
    openai_timeout: float = 120.0
    openai_max_tokens: int = 512

    llm_provider: str = "ollama"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None
    ollama_timeout: float = 300.0
    ollama_num_predict: int = 256
    ollama_think: bool = False

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        environment = value.strip().lower()

        if environment not in SUPPORTED_ENVIRONMENTS:
            raise ValueError(
                "ENVIRONMENT must be one of "
                f"{', '.join(SUPPORTED_ENVIRONMENTS)}"
            )

        return environment

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        algorithm = value.strip().upper()

        if algorithm not in SUPPORTED_JWT_ALGORITHMS:
            raise ValueError(
                "JWT_ALGORITHM must be one of "
                f"{', '.join(SUPPORTED_JWT_ALGORITHMS)}"
            )

        return algorithm

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        provider = value.strip().lower()

        if provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(
                "LLM_PROVIDER must be one of "
                f"{', '.join(SUPPORTED_LLM_PROVIDERS)}"
            )

        return provider

    @property
    def is_production(self) -> bool:
        return self.environment in PRODUCTION_ENVIRONMENTS

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if not self.is_production:
            return self

        secret = (self.jwt_secret_key or "").strip()

        if (
            len(secret) < MIN_PRODUCTION_JWT_SECRET_LENGTH
            or secret.lower() in WEAK_JWT_SECRETS
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a strong, unique value of at least "
                f"{MIN_PRODUCTION_JWT_SECRET_LENGTH} characters in production"
            )

        if "*" in self.cors_allowed_origins:
            raise ValueError(
                "CORS_ORIGINS must not use a wildcard ('*') in production"
            )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
