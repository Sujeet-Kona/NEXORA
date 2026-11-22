from uuid import UUID, uuid5

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

        @self._wrap("collection initialization")
        def _load_or_create_collection():
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

        _load_or_create_collection()

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

            try:
                self.client.create_payload_index(
                    collection_name=settings.qdrant_collection,
                    field_name="generation_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                # Generation filtering remains enforced by the query filter;
                # the payload index only improves filtering performance.
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




    def upsert_generation_chunks(
        self,
        chunks: list[tuple[str, list[float], int, int, int, int]],
    ) -> None:
        """Upsert generation-scoped vectors without touching active document vectors.


        Each record is (generation_id, vector, organization_id, document_id,
        chunk_index, document_version). Point IDs are deterministic UUIDs derived
        from generation UUID and chunk index, so separate generations never
        overwrite each other.
        """
        points = []
        seen_point_ids = set()
        generation_scope = {}
        for (
            generation_id,
            vector,
            organization_id,
            document_id,
            chunk_index,
            document_version,
        ) in chunks:
            if isinstance(chunk_index, bool) or not isinstance(chunk_index, int):
                raise ValueError("Chunk index must be an integer")
            if chunk_index < 0:
                raise ValueError("Chunk index must be non-negative")
            scope = (organization_id, document_id)
            previous_scope = generation_scope.setdefault(generation_id, scope)
            if previous_scope != scope:
                raise ValueError(
                    "Generation batch must not mix documents or organizations"
                )
            try:
                namespace = UUID(generation_id)
            except (ValueError, AttributeError) as exc:
                raise ValueError("Generation ID must be a valid UUID") from exc
            if len(vector) != settings.embedding_dimension:
                raise ValueError(
                    "Embedding dimension does not match Qdrant configuration"
                )
            point_id = str(uuid5(namespace, str(chunk_index)))
            if point_id in seen_point_ids:
                raise ValueError(
                    "Duplicate generation chunk index in upsert batch"
                )
            seen_point_ids.add(point_id)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "organization_id": organization_id,
                        "document_id": document_id,
                        "generation_id": generation_id,
                        "chunk_index": chunk_index,
                        "version": int(document_version),
                    },
                )
            )
        if not points:
            return
        self.ensure_collection()

        @self._wrap("generation upsert")
        def _do():
            self.client.upsert(
                collection_name=settings.qdrant_collection,
                wait=True,
                points=points,
            )
        _do()



    def delete_generation_chunks(
        self,
        generation_id: str,
        document_id: int,
        organization_id: int,
    ) -> None:
        """Delete only points belonging to one generation and tenant."""
        self.ensure_collection()



        @self._wrap("generation delete", organization_id=organization_id)
        def _do():
            self.client.delete(
                collection_name=settings.qdrant_collection,
                wait=True,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="organization_id",
                                match=models.MatchValue(value=organization_id),
                            ),
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            ),
                            models.FieldCondition(
                                key="generation_id",
                                match=models.MatchValue(value=generation_id),
                            ),
                        ]
                    )
                ),
            )
        _do()



    def count_generation_chunks(
        self,
        generation_id: str,
        document_id: int,
        organization_id: int,
    ) -> int:
        """Count points for one generation, scoped to its document and tenant."""
        self.ensure_collection()

        generation_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="organization_id",
                    match=models.MatchValue(value=organization_id),
                ),
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                ),
                models.FieldCondition(
                    key="generation_id",
                    match=models.MatchValue(value=generation_id),
                ),
            ]
        )

        @self._wrap("generation count", organization_id=organization_id)
        def _do():
            return self.client.count(
                collection_name=settings.qdrant_collection,
                count_filter=generation_filter,
                exact=True,
            )

        return _do().count


    def list_generation_chunk_indexes(
        self,
        generation_id: str,
        document_id: int,
        organization_id: int,
    ) -> list[int]:
        """Return all chunk indexes for one generation using paginated scroll."""
        self.ensure_collection()
        generation_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="organization_id",
                    match=models.MatchValue(value=organization_id),
                ),
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                ),
                models.FieldCondition(
                    key="generation_id",
                    match=models.MatchValue(value=generation_id),
                ),
            ]
        )

        @self._wrap("generation chunk-index listing", organization_id=organization_id)
        def _do():
            indexes = []
            offset = None
            while True:
                points, next_offset = self.client.scroll(
                    collection_name=settings.qdrant_collection,
                    scroll_filter=generation_filter,
                    limit=256,
                    offset=offset,
                    with_payload=["chunk_index"],
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    chunk_index = payload.get("chunk_index")
                    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
                        raise ValueError("Invalid generation chunk index payload")
                    if chunk_index in indexes:
                        raise ValueError("Duplicate generation chunk index payload")
                    indexes.append(chunk_index)
                if next_offset is None:
                    break
                if next_offset == offset:
                    raise RuntimeError("Qdrant scroll pagination did not advance")
                offset = next_offset
            return indexes

        return _do()


    def search_generation(
        self,
        query_vector: list[float],
        organization_id: int,
        generation_ids: list[str],
        limit: int = 5,
        document_ids: list[int] | None = None,
    ):
        """Search staged generations with mandatory tenant/generation filters."""
        if len(query_vector) != settings.embedding_dimension:
            raise ValueError(
                "Embedding dimension does not match Qdrant configuration"
            )
        if not generation_ids:
            return []
        self.ensure_collection()
        must_conditions = [
            models.FieldCondition(
                key="organization_id",
                match=models.MatchValue(value=organization_id),
            ),
            models.FieldCondition(
                key="generation_id",
                match=models.MatchAny(any=generation_ids),
            ),
        ]
        if document_ids is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=document_ids),
                )
            )
        @self._wrap("generation search", organization_id=organization_id)
        def _do():
            return self.client.query_points(
                collection_name=settings.qdrant_collection,
                query=query_vector,
                query_filter=models.Filter(must=must_conditions),
                limit=limit,
                with_payload=True,
            )
        return _do()
