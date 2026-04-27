"""Vector-store provider strategies for query-time RAG search."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol, cast

from chain.config import (
    ChainConfig,
    VectorStoreProvider,
    get_config,
    resolve_vector_collection_name,
)


@dataclass(frozen=True)
class EmbeddingModelMetadata:
    """Embedding model identity shared with ingestion-side vector stores."""

    name: str
    dimension: int


@dataclass(frozen=True)
class VectorSearchHit:
    """A vector search result normalized across providers."""

    payload: dict[str, Any]
    score: float | None = None


class VectorSearchProvider(Protocol):
    """Minimal query-time vector-store interface."""

    def target_name(self, embedding_model: EmbeddingModelMetadata) -> str:
        """Return the concrete vector-store target name for an embedding model."""

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        embedding_model: EmbeddingModelMetadata,
    ) -> list[VectorSearchHit]:
        """Return top-k vector search hits."""


class QdrantVectorSearchProvider:
    """Qdrant-backed query-time vector search provider."""

    def __init__(self, config: ChainConfig) -> None:
        from qdrant_client import QdrantClient

        self._config = config
        self._client = QdrantClient(
            url=_required(config.qdrant_url or config.vector_store_url, "QDRANT_URL"),
            api_key=_required(
                config.qdrant_api_key_ro or config.vector_store_api_key,
                "QDRANT_API_KEY_RO",
            ),
        )

    def target_name(self, embedding_model: EmbeddingModelMetadata) -> str:
        """Return the ADR 0008 collection name."""
        return resolve_vector_collection_name(
            self._config.vector_collection_prefix,
            embedding_model.name,
            embedding_model.dimension,
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        embedding_model: EmbeddingModelMetadata,
    ) -> list[VectorSearchHit]:
        """Search Qdrant for nearest movie vectors."""
        results = self._client.query_points(
            collection_name=self.target_name(embedding_model),
            query=query_vector,
            with_payload=True,
            limit=top_k,
        )
        return [
            VectorSearchHit(payload=point.payload, score=float(point.score))
            for point in results.points
            if point.payload
        ]


class ChromaDBVectorSearchProvider:
    """ChromaDB-backed query-time vector search provider."""

    def __init__(self, config: ChainConfig) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "ChromaDB support requires the optional 'chromadb' dependency."
            ) from exc

        self._config = config
        self._client = chromadb.PersistentClient(path=config.chromadb_persist_path)

    def target_name(self, embedding_model: EmbeddingModelMetadata) -> str:
        """Return the ADR 0008 collection name."""
        return resolve_vector_collection_name(
            self._config.vector_collection_prefix,
            embedding_model.name,
            embedding_model.dimension,
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        embedding_model: EmbeddingModelMetadata,
    ) -> list[VectorSearchHit]:
        """Search ChromaDB for nearest movie vectors."""
        collection = self._client.get_or_create_collection(name=self.target_name(embedding_model))
        results = collection.query(query_embeddings=[query_vector], n_results=top_k)
        metadatas = results.get("metadatas", [])
        distances = results.get("distances", [])
        if not metadatas:
            return []

        first_batch = metadatas[0]
        first_distances = distances[0] if distances else []
        hits: list[VectorSearchHit] = []
        for index, metadata in enumerate(first_batch):
            if not metadata:
                continue
            distance = first_distances[index] if index < len(first_distances) else None
            score = None if distance is None else 1.0 - float(distance)
            hits.append(VectorSearchHit(payload=cast(dict[str, Any], metadata), score=score))
        return hits


class PineconeVectorSearchProvider:
    """Pinecone-backed query-time vector search provider."""

    def __init__(self, config: ChainConfig) -> None:
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError(
                "Pinecone support requires the optional 'pinecone' dependency."
            ) from exc

        self._config = config
        self._client = Pinecone(
            api_key=_required(
                config.pinecone_api_key or config.vector_store_api_key, "PINECONE_API_KEY"
            )
        )
        self._index_host = config.pinecone_index_host
        self._index_name = config.pinecone_index_name
        self._index: Any | None = None

    def target_name(self, embedding_model: EmbeddingModelMetadata) -> str:
        """Return the ADR 0008 namespace name."""
        return resolve_vector_collection_name(
            self._config.vector_collection_prefix,
            embedding_model.name,
            embedding_model.dimension,
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        embedding_model: EmbeddingModelMetadata,
    ) -> list[VectorSearchHit]:
        """Search Pinecone for nearest movie vectors."""
        response = self._get_index().query(
            namespace=self.target_name(embedding_model),
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
        )
        matches = getattr(response, "matches", None) or response.get("matches", [])
        hits: list[VectorSearchHit] = []
        for match in matches:
            metadata = getattr(match, "metadata", None) or match.get("metadata")
            if not metadata:
                continue
            raw_score = getattr(match, "score", None) or match.get("score")
            score = None if raw_score is None else float(raw_score)
            hits.append(VectorSearchHit(payload=cast(dict[str, Any], metadata), score=score))
        return hits

    def _get_index(self) -> Any:
        if self._index is not None:
            return self._index

        if self._index_host:
            self._index = self._client.Index(host=self._index_host)
        else:
            self._index = self._client.Index(self._index_name)  # pragma: no cover
        return self._index


class PGVectorSearchProvider:
    """PostgreSQL pgvector-backed query-time vector search provider."""

    def __init__(self, config: ChainConfig) -> None:
        try:
            import psycopg
            from pgvector.psycopg import register_vector
        except ImportError as exc:
            raise RuntimeError(
                "PGVector support requires the optional 'pgvector' dependency."
            ) from exc

        self._config = config
        self._psycopg = psycopg
        self._register_vector = register_vector

    def target_name(self, embedding_model: EmbeddingModelMetadata) -> str:
        """Return the ADR 0008 table suffix."""
        return resolve_vector_collection_name(
            self._config.vector_collection_prefix,
            embedding_model.name,
            embedding_model.dimension,
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        embedding_model: EmbeddingModelMetadata,
    ) -> list[VectorSearchHit]:
        """Search pgvector for nearest movie vectors."""
        table_name = self._table_name(embedding_model)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f'''
                SELECT payload, 1 - (embedding <=> %s) AS score
                FROM "{table_name}"
                ORDER BY embedding <=> %s
                LIMIT %s
                ''',
                (query_vector, query_vector, top_k),
            )
            rows = cursor.fetchall()

        return [VectorSearchHit(payload=_cast_payload(row[0]), score=float(row[1])) for row in rows]

    def _connect(self) -> Any:
        connection = self._psycopg.connect(
            _required(self._config.pgvector_dsn or self._config.vector_store_url, "PGVECTOR_DSN")
        )
        self._register_vector(connection)
        return connection

    def _table_name(self, embedding_model: EmbeddingModelMetadata) -> str:
        target_name = self.target_name(embedding_model)
        return resolve_vector_collection_name(
            self._config.pgvector_schema,
            target_name,
            0,
        ).removesuffix("_0")


_VECTOR_STORES: dict[VectorStoreProvider, Callable[[ChainConfig], VectorSearchProvider]] = {
    "qdrant": QdrantVectorSearchProvider,
    "chromadb": ChromaDBVectorSearchProvider,
    "pinecone": PineconeVectorSearchProvider,
    "pgvector": PGVectorSearchProvider,
}


def create_vector_search_provider(config: ChainConfig | None = None) -> VectorSearchProvider:
    """Create the configured vector search provider without caching."""
    resolved_config = config or get_config()
    store_cls = _VECTOR_STORES[resolved_config.vector_store]
    return store_cls(resolved_config)


@lru_cache(maxsize=1)
def get_vector_search_provider() -> VectorSearchProvider:
    """Return the configured vector search provider as a process singleton."""
    return create_vector_search_provider()


def _required(value: str | None, env_var: str) -> str:
    """Return a required config value or raise a provider-specific error."""
    if value:
        return value
    raise ValueError(f"{env_var} is required for the selected vector store")


def _cast_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        return cast(dict[str, Any], json.loads(payload))
    return cast(dict[str, Any], dict(payload))
