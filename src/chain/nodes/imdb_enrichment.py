"""IMDB enrichment node.

For each RAG candidate, searches IMDb for a matching title, computes a
confidence score based on year proximity and title similarity, then batch-
fetches full metadata for the high-confidence matches.

Design choices
--------------
* Search calls are parallelised with ``asyncio.gather``, but capped at
  ``_SEARCH_CONCURRENCY`` concurrent requests via a semaphore to avoid
  triggering Cloudflare rate limits on the API.
* Full ``titles.get()`` calls are batched in groups of 5 using ``batch_get``
  with exponential-backoff retry on HTTP 429.
* Failures on individual candidates are caught and logged — the node never
  raises so a partial result is still useful.
"""

from __future__ import annotations

import asyncio
import logging
from difflib import SequenceMatcher
from typing import Any

from imdbapi import IMDBAPIClient
from imdbapi.exceptions import IMDBAPIRateLimitError
from imdbapi.models.title import BatchGetTitlesResponse

from chain.config import get_config
from chain.state import MovieFinderState

logger = logging.getLogger(__name__)

# IMDb search returns TitleRef-like summaries; batch_get accepts up to 5 IDs.
_BATCH_SIZE = 5
# Max concurrent search requests — keeps us under the API rate limit.
_SEARCH_CONCURRENCY = 3
# Seconds to stagger the start of each search task to avoid burst rate-limiting.
_SEARCH_STAGGER_DELAY = 0.5
# Retry config for 429 responses (seconds).
_RETRY_BASE_DELAY = 30.0
_RETRY_MAX_ATTEMPTS = 4


async def imdb_enrichment_node(state: MovieFinderState) -> dict[str, Any]:
    """Enrich every RAG candidate with live IMDb metadata."""
    cfg = get_config()
    candidates: list[dict[str, Any]] = state.get("rag_candidates", [])

    if not candidates:
        logger.warning("imdb_enrichment_node: no RAG candidates to enrich")
        return {"enriched_movies": []}

    semaphore = asyncio.Semaphore(_SEARCH_CONCURRENCY)

    async with IMDBAPIClient() as client:
        # Step 1: staggered + rate-limited parallel IMDB search.
        # Each task sleeps i * _SEARCH_STAGGER_DELAY before its first request
        # so we never fire all queries simultaneously.
        search_tasks = [
            _search_best_match(
                client, c, cfg.imdb_search_limit, semaphore, i * _SEARCH_STAGGER_DELAY
            )
            for i, c in enumerate(candidates)
        ]
        best_matches: list[tuple[dict[str, Any], str | None, float]] = await asyncio.gather(
            *search_tasks
        )
        # best_matches[i] = (candidate, imdb_id | None, confidence)

        # Step 2: batch-fetch full title details for confident matches
        id_to_full: dict[str, dict[str, Any]] = {}
        confident_ids = [
            imdb_id
            for _, imdb_id, conf in best_matches
            if imdb_id and conf >= cfg.confidence_threshold
        ]

        for batch_start in range(0, len(confident_ids), _BATCH_SIZE):
            batch = confident_ids[batch_start : batch_start + _BATCH_SIZE]
            try:
                resp = await _batch_get_with_retry(client, batch)
                for title in resp.titles:
                    id_to_full[title.id] = _title_to_dict(title)
            except Exception as exc:
                logger.warning("batch_get failed for %s: %s", batch, exc)

    # Step 3: merge RAG + IMDb data into enriched records
    enriched: list[dict[str, Any]] = []
    for candidate, imdb_id, confidence in best_matches:
        imdb_data = id_to_full.get(imdb_id, {}) if imdb_id else {}
        enriched.append(
            {
                # RAG fields
                "rag_title": candidate.get("title", ""),
                "rag_year": candidate.get("release_year", 0),
                "rag_director": candidate.get("director", ""),
                "rag_genre": candidate.get("genre", []),
                "rag_cast": candidate.get("cast", []),
                "rag_plot": candidate.get("plot", ""),
                # IMDb fields
                "imdb_id": imdb_data.get("id"),
                "imdb_title": imdb_data.get("primaryTitle"),
                "imdb_year": imdb_data.get("startYear"),
                "imdb_rating": imdb_data.get("rating"),
                "imdb_plot": imdb_data.get("plot"),
                "imdb_genres": imdb_data.get("genres", []),
                "imdb_directors": imdb_data.get("directors", []),
                "imdb_stars": imdb_data.get("stars", []),
                "imdb_poster_url": imdb_data.get("posterUrl"),
                # Confidence
                "confidence": confidence,
            }
        )

    logger.info(
        "Enriched %d/%d candidates with IMDb data",
        sum(1 for e in enriched if e.get("imdb_id")),
        len(enriched),
    )
    return {"enriched_movies": enriched}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _batch_get_with_retry(client: IMDBAPIClient, ids: list[str]) -> BatchGetTitlesResponse:
    """Call ``client.titles.batch_get`` with exponential-backoff on 429."""
    delay = _RETRY_BASE_DELAY
    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            return await client.titles.batch_get(ids)
        except IMDBAPIRateLimitError as exc:
            last_exc = exc
            if attempt == _RETRY_MAX_ATTEMPTS:
                break
            logger.warning(
                "batch_get rate-limited (attempt %d/%d) — retrying in %.0fs: %s",
                attempt,
                _RETRY_MAX_ATTEMPTS,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
            delay *= 2  # exponential backoff
    raise last_exc or IMDBAPIRateLimitError(429, "rate limited")


async def _search_best_match(
    client: IMDBAPIClient,
    candidate: dict[str, Any],
    search_limit: int,
    semaphore: asyncio.Semaphore,
    initial_delay: float = 0.0,
) -> tuple[dict[str, Any], str | None, float]:
    """Search IMDb for a title matching *candidate* and return the best hit."""
    title = candidate.get("title", "")
    year = candidate.get("release_year", 0)
    query = f"{title} {year}" if year else title

    if initial_delay:
        await asyncio.sleep(initial_delay)

    delay = _RETRY_BASE_DELAY
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            async with semaphore:
                result = await client.search.titles(query, limit=search_limit)
            break  # success
        except IMDBAPIRateLimitError as exc:
            if attempt == _RETRY_MAX_ATTEMPTS:
                logger.warning("IMDB search failed for '%s': %s", title, exc)
                return candidate, None, 0.0
            logger.warning(
                "Search rate-limited for '%s' (attempt %d/%d) — retrying in %.0fs",
                title,
                attempt,
                _RETRY_MAX_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)
            delay *= 2
        except Exception as exc:
            logger.warning("IMDB search failed for '%s': %s", title, exc)
            return candidate, None, 0.0

    best_id: str | None = None
    best_score = 0.0

    for hit in result.titles:
        score = _compute_confidence(candidate, hit)
        if score > best_score:
            best_score = score
            best_id = hit.id

    return candidate, best_id, best_score


def _compute_confidence(candidate: dict[str, Any], imdb_hit: object) -> float:
    """Score how well an IMDb search hit matches a RAG candidate (0–1)."""
    score = 0.0

    # --- Year proximity (up to 0.5) ---
    rag_year: int = candidate.get("release_year", 0) or 0
    imdb_year: int = getattr(imdb_hit, "start_year", None) or 0
    if rag_year and imdb_year:
        diff = abs(rag_year - imdb_year)
        if diff == 0:
            score += 0.5
        elif diff <= 2:
            score += 0.35
        elif diff <= 5:
            score += 0.15

    # --- Title similarity (up to 0.5) ---
    rag_title = (candidate.get("title", "") or "").lower().strip()
    imdb_title = (getattr(imdb_hit, "primary_title", "") or "").lower().strip()

    if rag_title and imdb_title:
        if rag_title == imdb_title:
            score += 0.5
        elif rag_title in imdb_title or imdb_title in rag_title:
            score += 0.35
        else:
            ratio = SequenceMatcher(None, rag_title, imdb_title).ratio()
            score += ratio * 0.3

    return min(score, 1.0)


def _title_to_dict(title: object) -> dict[str, Any]:
    """Convert a Title model to a plain dict for state storage."""
    directors = [d.display_name for d in (getattr(title, "directors", []) or [])]
    stars = [s.display_name for s in (getattr(title, "stars", []) or [])]
    rating_obj = getattr(title, "rating", None)
    image_obj = getattr(title, "primary_image", None)

    return {
        "id": getattr(title, "id", None),
        "primaryTitle": getattr(title, "primary_title", None),
        "startYear": getattr(title, "start_year", None),
        "rating": rating_obj.aggregate_rating if rating_obj else None,
        "plot": getattr(title, "plot", None),
        "genres": getattr(title, "genres", []) or [],
        "directors": directors,
        "stars": stars,
        "posterUrl": image_obj.url if image_obj else None,
    }
