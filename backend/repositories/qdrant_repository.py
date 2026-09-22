from qdrant_client import QdrantClient, models

from backend.core.config import settings


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
            self.client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name="organization_id",
                field_schema=models.PayloadSchemaType.INTEGER,
            )
            self.client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name="document_id",
                field_schema=models.PayloadSchemaType.INTEGER,
            )

        self._collection_ready = True

    def upsert_chunks(
        self,
        chunks: list[tuple[int, list[float], int, int, int]],
    ) -> None:
        points = []

        for (
            chunk_id,
            vector,
            organization_id,
            document_id,
            chunk_index,
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
                    },
                )
            )

        if not points:
            return

        self.ensure_collection()

        self.client.upsert(
            collection_name=settings.qdrant_collection,
            wait=True,
            points=points,
        )

    def upsert_chunk(
        self,
        chunk_id: int,
        vector: list[float],
        organization_id: int,
        document_id: int,
        chunk_index: int,
    ) -> None:
        self.upsert_chunks(
            [
                (
                    chunk_id,
                    vector,
                    organization_id,
                    document_id,
                    chunk_index,
                )
            ]
        )

    def delete_document_chunks(
        self,
        document_id: int,
        organization_id: int,
    ) -> None:
        self.ensure_collection()

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

    def delete_chunk(
        self,
        chunk_id: int,
        organization_id: int,
    ) -> None:
        self.ensure_collection()

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
                            key="chunk_id",
                            match=models.MatchValue(
                                value=chunk_id,
                            ),
                        ),
                    ]
                )
            ),
        )

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

        return self.client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=models.Filter(
                must=must_conditions,
            ),
            limit=limit,
            with_payload=True,
        )


