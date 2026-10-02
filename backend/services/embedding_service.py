import logging
import time

from langchain_huggingface import HuggingFaceEmbeddings

from backend.core.config import settings
from backend.core.logging import LOGGER_NAME


logger = logging.getLogger(LOGGER_NAME)

# Maximum number of retries before raising an embedding failure.
_MAX_RETRIES = 3
# Backoff base seconds between retries (doubles each attempt).
_RETRY_BASE_SECONDS = 0.5


class EmbeddingService:
    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int | None = None,
        verify_dimension: bool = True,
    ):
        self.model_name = (
            model_name
            or settings.embedding_model
        )
        self.batch_size = (
            batch_size
            if batch_size is not None
            else settings.embedding_batch_size
        )

        self._embeddings = HuggingFaceEmbeddings(
            model_name=self.model_name,
            show_progress=False,
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": self.batch_size,
            },
            model_kwargs={
                # Device auto-detection: CPU when GPU unavailable.
                "device": None,
            },
        )

        if verify_dimension:
            self._verify_dimension()

    def _verify_dimension(self) -> None:
        """Probe the real embedding dimension once at init time.

        Raises ValueError immediately if settings.embedding_dimension does
        not match what the model actually emits. This prevents an
        entire document pipeline from crashing at the Qdrant upsert step
        after hours of embedding work on a dimension mismatch.
        """
        probe_vector = self._retry_embedding_call(
            lambda: self._embeddings.embed_documents(["probe"]),
            operation="dimension_probe",
        )

        real_dimension = len(probe_vector[0])
        configured = settings.embedding_dimension

        if real_dimension != configured:
            raise ValueError(
                f"Embedding dimension mismatch: model '{self.model_name}' "
                f"produces {real_dimension}-dimensional vectors but "
                f"settings.embedding_dimension={configured}. Update the "
                f"configuration or the Qdrant collection schema."
            )

        logger.info(
            "Embedding model verified: %s dimension=%d batch_size=%d",
            self.model_name,
            real_dimension,
            self.batch_size,
        )

    @staticmethod
    def _retry_embedding_call(
        func,
        operation: str,
    ):
        """Run an embedding call with transient-error retries.

        A small set of network / memory-pressure / internal HF pipeline
        exceptions are handled by a short exponential backoff. Non-
        transient errors (ValueError from empty inputs, genuine schema
        issues) are raised immediately.
        """
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return func()
            except (ValueError, TypeError, KeyError):
                # Contract / usage errors — a retry won't help.
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

                if attempt >= _MAX_RETRIES:
                    break

                delay = _RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Embedding call '%s' attempt %d/%d failed; "
                    "retrying in %.2fs: %s",
                    operation,
                    attempt,
                    _MAX_RETRIES,
                    delay,
                    str(exc),
                )
                time.sleep(delay)

        assert last_exc is not None
        logger.error(
            "Embedding call '%s' failed permanently after %d attempts",
            operation,
            _MAX_RETRIES,
        )
        raise last_exc

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        # Drop empty / whitespace-only entries BEFORE the encoder so the
        # batch never contains zero-length inputs that trigger sporadic
        # tokenizer crashes.
        original_len = len(texts)
        cleaned = [t for t in texts if t.strip()]

        if not cleaned:
            # If every entry was empty we still must return a list whose
            # length matches the input contract. A zero-length vector is
            # invalid semantically, so this is a contract error.
            if original_len > 0:
                logger.warning(
                    "embed_documents called with %d empty strings; "
                    "returning empty vector list",
                    original_len,
                )
            return []

        if len(cleaned) != original_len:
            logger.warning(
                "embed_documents dropped %d/%d whitespace-only texts "
                "before encoding",
                original_len - len(cleaned),
                original_len,
            )

        vectors = self._retry_embedding_call(
            lambda: self._embeddings.embed_documents(cleaned),
            operation="embed_documents",
        )

        if len(vectors) != len(cleaned):
            raise RuntimeError(
                f"embed_documents input/output length mismatch: "
                f"input={len(cleaned)} output={len(vectors)}"
            )

        return vectors

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        if not text.strip():
            raise ValueError(
                "Query text cannot be empty"
            )

        vector = self._retry_embedding_call(
            lambda: self._embeddings.embed_query(text),
            operation="embed_query",
        )

        real_dimension = len(vector)
        configured = settings.embedding_dimension
        if real_dimension != configured:
            # Protect against a broken provider returning a different
            # shaped vector at query time (e.g. provider fallback).
            raise RuntimeError(
                f"Query embedding dimension mismatch: got {real_dimension}, "
                f"expected {configured}"
            )

        return vector
