"""Validation node.

Filters the enriched movie candidates based on a confidence threshold and
IMDb data presence.  Candidates that are too low-confidence or failed to
resolve to an IMDb ID are removed from the active state.
"""

from __future__ import annotations

from typing import Any

from chain.config import get_config
from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def validation_node(state: MovieFinderState) -> dict[str, Any]:
    """Filter out low-confidence candidates.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with a filtered enriched_movies list.
    """
    cfg = get_config()
    enriched: list[dict[str, Any]] = state.get("enriched_movies", [])

    if not enriched:
        return {"enriched_movies": []}

    # Keep candidates whose confidence meets the threshold.
    # IMDb ID is not required — degraded (RAG-only) candidates carry their
    # Qdrant cosine similarity as confidence and are presented without IMDb data.
    valid_movies = [m for m in enriched if m["confidence"] >= cfg.confidence_threshold]

    # Log what was filtered out
    filtered_count = len(enriched) - len(valid_movies)
    if filtered_count > 0:
        logger.info(f"Validation node: filtered out {filtered_count} low-confidence candidate(s)")
        for movie in enriched:
            conf = movie.get("confidence", 0.0)
            if conf < cfg.confidence_threshold:
                title = movie.get("imdb_title") or movie.get("rag_title", "?")
                imdb_id = movie.get("imdb_id", "—")
                logger.debug(f"  [Filtered] {title} (conf={conf:.2f}, id={imdb_id})")

    # If everything was filtered out, we still return an empty list so the
    # presentation node can handle the "no results" message correctly.
    return {"enriched_movies": valid_movies}
