"""MovieSearchService — thin wrapper around query embeddings + vector search.

Replicates the search path from rag_ingestion as a self-contained,
importable service so the chain package has no hard dependency on the
rag_ingestion source tree.

The vector collection name and embedding model must exactly match what was
used during ingestion (configured via ChainConfig).
"""

from __future__ import annotations

from chain.config import ChainConfig
from chain.models.output import RagCandidate
from chain.rag.vector_store import EmbeddingModelMetadata, get_vector_search_provider
from chain.utils.llm_factory import get_query_embedder
from chain.utils.logger import get_logger


class MovieSearchService:
    """Synchronous search service.

    Synchronous because provider SDKs and vector-store client interfaces are
    synchronous. Callers in async nodes should wrap with ``asyncio.to_thread``.
    """

    def __init__(self, config: ChainConfig) -> None:
        """Initialize the search service.

        Args:
            config: ``ChainConfig`` instance (injected so callers can pass a mock in tests).
        """
        self._embedding_model = EmbeddingModelMetadata(
            name=config.embedding_model,
            dimension=config.embedding_dimension,
        )
        self._collection = config.vector_collection_name
        self._embedder = get_query_embedder()
        self._vector_store = get_vector_search_provider()
        self.logger = get_logger(self.__class__.__name__)

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
        return self._search_vector_store(vector, top_k)

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
        vector = self._embedder.embed_query(text)
        token_count = getattr(self._embedder, "last_token_count", None)
        token_label = f"{token_count} tokens" if isinstance(token_count, int) else "unknown tokens"
        self.logger.debug(
            f"Embedded query with {self._embedding_model.name} ({token_label}): {text[:60]!r}"
        )
        return vector

    def _search_vector_store(self, vector: list[float], top_k: int) -> list[RagCandidate]:
        """Query the configured vector store for similar vectors.

        Args:
            vector: The query vector.
            top_k: Number of results.

        Returns:
            List of RagCandidate.
        """
        results = self._vector_store.search(vector, top_k, self._embedding_model)

        candidates: list[RagCandidate] = []
        for hit in results:
            payload = hit.payload

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
                    rag_score=float(hit.score or 0.0),
                )
            )

        target_name = self._vector_store.target_name(self._embedding_model)
        self.logger.info(f"RAG returned {len(candidates)} candidate(s) from target {target_name!r}")
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
