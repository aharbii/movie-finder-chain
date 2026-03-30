"""MovieSearchService — thin wrapper around Qdrant + OpenAI embeddings.

Replicates the search path from rag_ingestion (QdrantVectorStore.search +
OpenAIEmbeddingProvider.embed) as a self-contained, importable service so
the chain package has no hard dependency on the rag_ingestion source tree.

The collection name and embedding model must exactly match what was used
during ingestion (configured via ChainConfig).
"""

from __future__ import annotations

from openai import OpenAI
from qdrant_client import QdrantClient

from chain.config import ChainConfig
from chain.models.output import RagCandidate
from chain.utils.logger import get_logger


class MovieSearchService:
    """Synchronous search service.

    Synchronous because both the OpenAI client (sync variant) and the
    qdrant-client default interface are synchronous. Callers in async
    nodes should wrap with ``asyncio.to_thread``.
    """

    def __init__(self, config: ChainConfig) -> None:
        """Initialize the search service.

        Args:
            config: ``ChainConfig`` instance (injected so callers can pass a mock in tests).
        """
        self._collection = config.qdrant_collection_name
        self._embedding_model = config.embedding_model
        self.logger = get_logger(self.__class__.__name__)

        self._openai = OpenAI(api_key=config.openai_api_key)
        self._qdrant = QdrantClient(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key_ro,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 8) -> list[RagCandidate]:
        """Embed *query* and return the top-*k* closest movie candidates.

        Args:
            query: Natural-language plot description from the user.
            top_k: Maximum number of results to return.

        Returns:
            List of RagCandidate ordered by cosine similarity (closest first).
        """
        vector = self._embed(query)
        return self._search_qdrant(vector, top_k)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Args:
            text: The text to embed.

        Returns:
            List of floats representing the embedding.
        """
        response = self._openai.embeddings.create(
            input=text,
            model=self._embedding_model,
        )
        self.logger.debug(f"Embedded query ({response.usage.total_tokens} tokens): {text[:60]!r}")
        return list(response.data[0].embedding)

    def _search_qdrant(self, vector: list[float], top_k: int) -> list[RagCandidate]:
        """Query Qdrant for similar vectors.

        Args:
            vector: The query vector.
            top_k: Number of results.

        Returns:
            List of RagCandidate.
        """
        results = self._qdrant.query_points(
            collection_name=self._collection,
            query=vector,
            with_payload=True,
            limit=top_k,
        )

        candidates: list[RagCandidate] = []
        for point in results.points:
            if not point.payload:
                continue
            payload = point.payload

            # Normalise genre / cast — stored as list or "/"-separated string
            genre = _to_list(payload.get("genre", []))
            cast = _to_list(payload.get("cast", []))

            candidates.append(
                RagCandidate(
                    title=payload.get("title", ""),
                    release_year=int(payload.get("release_year") or 0),
                    director=payload.get("director", ""),
                    genre=genre,
                    cast=cast,
                    plot=payload.get("plot", ""),
                    rag_score=float(point.score),
                )
            )

        self.logger.info(
            f"RAG returned {len(candidates)} candidate(s) from collection {self._collection!r}"
        )
        for i, c in enumerate(candidates, start=1):
            self.logger.debug(
                f"  #{i}  {c.title} ({c.release_year or '?'}) | director: {c.director or '—'} | genre: {', '.join(c.genre[:3]) if c.genre else '—'}"
            )
        return candidates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_list(value: object) -> list[str]:
    """Convert a string or list stored in Qdrant payload to a plain list.

    Args:
        value: The value from Qdrant payload.

    Returns:
        A list of strings.
    """
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        # rag_ingestion stores genre as "/" separated, cast as ", " separated
        if "/" in value:
            return [v.strip() for v in value.split("/") if v.strip()]
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value] if value else []
    return []
