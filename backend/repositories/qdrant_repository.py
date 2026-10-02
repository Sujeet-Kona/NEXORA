from qdrant_client import QdrantClient, models

from backend.core.config import settings
from backend.core.exceptions import VectorStoreError


class QdrantRepository:
    def __init__(
        self,
        client: QdrantClient | None = None,
        is_local: bool = False,
    ):
        self.is_local = is_local
        self._collection_ready = False

        if client is not None:
            self.client = client
        elif settings.qdrant_api_key:
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
            )
        else:
            self.client = QdrantClient(
                url=settings.qdrant_url,
            )

    @staticmethod
    def _wrap(operation: str, organization_id: int | None = None):
        """Decorator / context helper: convert raw qdrant-client errors into
        an application-level VectorStoreError. Never exposes raw gRPC /
        HTTP internals in API 500 messages."""
        from functools import wraps

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except (ValueError, AssertionError):
                    # Contract errors: raise as-is so the caller can fix them.
                    raise
                except Exception as exc:
                    raise VectorStoreError(
                        f"Qdrant {operation} failed" + (
                            f" for organization {organization_id}"
                            if organization_id is not None
                            else ""
                        )
                    ) from exc

            return wrapper

        return decorator

    def ensure_collection(self) -> None:
        if self._collection_ready:
            return

        collections = self.client.get_collections()

        names = {
            collection.name
            for collection in collections.collections
        }

        if settings.qdrant_collection not in names:
            self.client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=settings.embedding_dimension,
                    distance=models.Distance.COSINE,
                ),
            )

        if not self.is_local:
            for field_name in (
                "organization_id",
                "document_id",
                "version",
            ):
                try:
                    self.client.create_payload_index(
                        collection_name=settings.qdrant_collection,
                        field_name=field_name,
                        field_schema=models.PayloadSchemaType.INTEGER,
                    )
                except Exception:
                    # Payload indexes are best-effort optimisation; a
                    # pre-existing index or a remote-server quirk should
                    # never prevent startup.
                    pass

        self._collection_ready = True

    def upsert_chunks(
        self,
        chunks: list[tuple[int, list[float], int, int, int, int]],
    ) -> None:
        """Upsert chunk vectors.

        Parameters
        ----------
        chunks:
            ``(chunk_id, vector, organization_id, document_id,
            chunk_index, document_version)``.
        """
        points = []

        for (
            chunk_id,
            vector,
            organization_id,
            document_id,
            chunk_index,
            document_version,
        ) in chunks:
            if len(vector) != settings.embedding_dimension:
                raise ValueError(
                    "Embedding dimension does not match Qdrant configuration"
                )

            points.append(
                models.PointStruct(
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "organization_id": organization_id,
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_index,
                        "version": int(document_version),
                    },
                )
            )

        if not points:
            return

        self.ensure_collection()

        @self._wrap("upsert", organization_id=None)
        def _do():
            self.client.upsert(
                collection_name=settings.qdrant_collection,
                wait=True,
                points=points,
            )

        _do()

    def delete_document_chunks(
        self,
        document_id: int,
        organization_id: int,
    ) -> None:
        self.ensure_collection()

        @self._wrap("delete", organization_id=organization_id)
        def _do():
            self.client.delete(
                collection_name=settings.qdrant_collection,
                wait=True,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="organization_id",
                                match=models.MatchValue(
                                    value=organization_id,
                                ),
                            ),
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(
                                    value=document_id,
                                ),
                            ),
                        ]
                    )
                ),
            )

        _do()

    def search(
        self,
        query_vector: list[float],
        organization_id: int,
        limit: int = 5,
        document_ids: list[int] | None = None,
    ):
        if len(query_vector) != settings.embedding_dimension:
            raise ValueError(
                "Embedding dimension does not match Qdrant configuration"
            )

        self.ensure_collection()

        must_conditions = [
            models.FieldCondition(
                key="organization_id",
                match=models.MatchValue(
                    value=organization_id,
                ),
            )
        ]

        if document_ids is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(
                        any=document_ids,
                    ),
                )
            )

        @self._wrap("search", organization_id=organization_id)
        def _do():
            return self.client.query_points(
                collection_name=settings.qdrant_collection,
                query=query_vector,
                query_filter=models.Filter(
                    must=must_conditions,
                ),
                limit=limit,
                with_payload=True,
            )

        return _do()


