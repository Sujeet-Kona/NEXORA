from langchain_huggingface import HuggingFaceEmbeddings

from backend.core.config import settings


class EmbeddingService:
    def __init__(
        self,
        model_name: str | None = None,
    ):
        self.model_name = (
            model_name
            or settings.embedding_model
        )

        self._embeddings = HuggingFaceEmbeddings(
            model_name=self.model_name,
            encode_kwargs={
                "normalize_embeddings": True,
            },
        )

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        return self._embeddings.embed_documents(
            texts
        )

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        if not text.strip():
            raise ValueError(
                "Query text cannot be empty"
            )

        return self._embeddings.embed_query(
            text
        )

    @property
    def dimension(self) -> int:
        return settings.embedding_dimension
