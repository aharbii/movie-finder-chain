"""Validation node.

Post-processes enriched movies: filters out low-confidence matches, deduplicates
by IMDb ID, and sorts highest-confidence first.  The result is the definitive
candidate pool presented to the user.
"""

from __future__ import annotations

import logging

from chain.config import get_config
from chain.state import MovieFinderState

logger = logging.getLogger(__name__)


def validation_node(state: MovieFinderState) -> dict:
    """Filter, deduplicate, and rank the enriched movie list."""
    cfg = get_config()
    enriched: list[dict] = state.get("enriched_movies", [])

    # Keep candidates that have an IMDb match above the confidence threshold.
    # Also include candidates without any IMDb match (confidence==0) if there
    # were fewer than 3 validated results — so the user always sees something.
    validated = [
        m for m in enriched if m.get("imdb_id") and m["confidence"] >= cfg.confidence_threshold
    ]

    # Deduplicate by IMDb ID (keep highest confidence per ID)
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for movie in sorted(validated, key=lambda m: m["confidence"], reverse=True):
        imdb_id = movie.get("imdb_id")
        if imdb_id not in seen_ids:
            if imdb_id:
                seen_ids.add(imdb_id)
            deduped.append(movie)

    # If validation produced nothing useful, fall back to the raw enriched list
    # sorted by whatever confidence we have (even 0.0), so the node never returns
    # an empty pool when RAG found candidates.
    if not deduped and enriched:
        logger.warning(
            "No candidates above confidence threshold %.2f — returning all %d raw candidates",
            cfg.confidence_threshold,
            len(enriched),
        )
        deduped = sorted(enriched, key=lambda m: m["confidence"], reverse=True)

    # Cap at a reasonable display limit
    final = deduped[:5]

    logger.info(
        "Validation: %d enriched → %d validated → %d displayed",
        len(enriched),
        len(deduped),
        len(final),
    )
    return {"enriched_movies": final}
