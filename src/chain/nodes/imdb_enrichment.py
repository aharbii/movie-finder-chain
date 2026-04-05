"""IMDB enrichment node.

For each RAG candidate, searches IMDb for a matching title, computes a
confidence score based on year proximity and title similarity, then batch-
fetches full metadata for the high-confidence matches.

Design choices
--------------
* Search calls are serialised (concurrency = 1) to avoid triggering the
  Cloudflare rate limiter.  Firing multiple requests concurrently causes all
  of them to hit 429 simultaneously and exhausts the retry budget quickly.
* Full ``titles.get()`` calls are batched in groups of 5 using ``batch_get``
  with exponential-backoff retry on HTTP 429.
* The node has no timeout — it waits as long as the API needs, honouring the
  ``retry_after`` value from each 429 response.
* Failures on individual candidates are caught and logged — the node never
  raises so a partial result is still useful.
"""

from __future__ import annotations

import asyncio
import json
from difflib import SequenceMatcher
from typing import Any

from imdbapi import IMDBAPIClient
from imdbapi.exceptions import IMDBAPIRateLimitError
from imdbapi.models.title import BatchGetTitlesResponse, Title

from chain.config import get_config
from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)

# IMDb search returns TitleRef-like summaries; batch_get accepts up to 5 IDs.
_BATCH_SIZE = 5
# Maximum number of RAG candidates to enrich and present.
# RAG_TOP_K intentionally fetches more for a wider semantic net; we cap here.
_MAX_ENRICH_CANDIDATES = 5
# Retry config for 429 responses.
# Delay is read from the API's retry_after field; this is the fallback.
_DEFAULT_RETRY_AFTER = 30.0
_RETRY_MAX_RETRIES = 3


async def imdb_enrichment_node(state: MovieFinderState) -> dict[str, Any]:
    """Enrich every RAG candidate with live IMDb metadata.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with enriched_movies.
    """
    cfg = get_config()
    candidates: list[dict[str, Any]] = state.get("rag_candidates", [])

    if not candidates:
        logger.warning("imdb_enrichment_node: no RAG candidates to enrich")
        return {"enriched_movies": []}

    # Qdrant returns candidates sorted by score — take the top N.
    candidates = candidates[:_MAX_ENRICH_CANDIDATES]

    try:
        enriched_movies = await _run_imdb_enrichment(
            candidates, cfg.imdb_search_limit, cfg.confidence_threshold
        )
    except Exception as exc:
        # Defensive last-resort: any unhandled exception from the enrichment
        # workflow (e.g. connectivity failure, unexpected library error) falls
        # back to RAG-only degraded records so the pipeline can still present
        # results.  Per-candidate failures inside _search_best_match are already
        # caught there; this guard handles the rare case where the client
        # context manager or batch step itself fails.
        logger.warning(
            "IMDb enrichment failed unexpectedly — using degraded RAG-only results: %s", exc
        )
        enriched_movies = _build_degraded_movies(candidates)

    logger.info(
        "Enriched %s/%s candidates with IMDb data",
        sum(1 for movie in enriched_movies if movie.get("imdb_id")),
        len(enriched_movies),
    )
    return {"enriched_movies": enriched_movies}


async def _run_imdb_enrichment(
    candidates: list[dict[str, Any]],
    search_limit: int,
    confidence_threshold: float,
) -> list[dict[str, Any]]:
    """Execute the full IMDb enrichment workflow, honouring API retry_after delays."""
    async with IMDBAPIClient() as client:
        # Step 1: sequential IMDb search — one candidate at a time.
        # asyncio.gather fires all coroutines simultaneously; with a semaphore
        # they each acquire and release within milliseconds of each other,
        # overwhelming the rate limiter.  A plain loop ensures each candidate's
        # full retry cycle (including any 30s back-off) completes before the
        # next search starts.
        best_matches: list[tuple[dict[str, Any], str | None, float]] = []
        for candidate in candidates:
            match = await _search_best_match(client, candidate, search_limit)
            best_matches.append(match)
        # best_matches[i] = (candidate, imdb_id | None, confidence)

        # Step 2: batch-fetch full title details for confident matches
        id_to_full: dict[str, dict[str, Any]] = {}
        confident_ids = [
            imdb_id for _, imdb_id, conf in best_matches if imdb_id and conf >= confidence_threshold
        ]

        batch_tasks = [
            _batch_get_with_retry(client, confident_ids[index : index + _BATCH_SIZE])
            for index in range(0, len(confident_ids), _BATCH_SIZE)
        ]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        for batch, result in zip(
            [
                confident_ids[index : index + _BATCH_SIZE]
                for index in range(0, len(confident_ids), _BATCH_SIZE)
            ],
            batch_results,
            strict=False,
        ):
            if isinstance(result, BaseException):
                logger.warning(f"batch_get failed for {batch}: {result}")
                continue
            for title in result.titles:
                id_to_full[title.id] = _title_to_dict(title)

    # Step 3: merge RAG + IMDb data into enriched records
    return _merge_enriched_movies(best_matches, id_to_full)


def _build_degraded_movies(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return RAG-only records when IMDb enrichment times out.

    Confidence is set to the Qdrant cosine similarity score so that
    high-quality RAG matches are not discarded by the validation node.
    """
    return [
        {
            "rag_title": candidate.get("title", ""),
            "rag_year": candidate.get("release_year", 0),
            "rag_director": candidate.get("director", ""),
            "rag_genre": candidate.get("genre", []),
            "rag_cast": candidate.get("cast", []),
            "rag_plot": candidate.get("plot", ""),
            "imdb_id": None,
            "imdb_title": None,
            "imdb_year": None,
            "imdb_rating": None,
            "imdb_plot": None,
            "imdb_genres": [],
            "imdb_directors": [],
            "imdb_stars": [],
            "imdb_poster_url": None,
            "confidence": float(candidate.get("rag_score", 0.0)),
        }
        for candidate in candidates
    ]


def _merge_enriched_movies(
    best_matches: list[tuple[dict[str, Any], str | None, float]],
    id_to_full: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge RAG candidates with any fetched IMDb metadata."""
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
    return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_retry_after(exc: IMDBAPIRateLimitError) -> float:
    """Read the ``retry_after`` value (seconds) from a 429 response body.

    The imdbapi.dev Cloudflare 429 payload is a JSON object with a top-level
    ``retry_after`` integer field.  Falls back to ``_DEFAULT_RETRY_AFTER`` if
    the field is absent or the body cannot be parsed.

    Args:
        exc: The rate-limit exception raised by the IMDb client.

    Returns:
        How long to wait before the next retry, in seconds.
    """
    try:
        data = json.loads(exc.message)
        return float(data.get("retry_after", _DEFAULT_RETRY_AFTER))
    except Exception:
        return _DEFAULT_RETRY_AFTER


async def _batch_get_with_retry(client: IMDBAPIClient, ids: list[str]) -> BatchGetTitlesResponse:
    """Call ``client.titles.batch_get`` with exponential-backoff on 429.

    Args:
        client: The IMDb API client.
        ids: The list of IMDb title IDs to fetch.

    Returns:
        The batch response.

    Raises:
        IMDBAPIRateLimitError: If max retry attempts reached.
    """
    last_exc: Exception | None = None
    total_attempts = _RETRY_MAX_RETRIES + 1
    delay = _DEFAULT_RETRY_AFTER
    for attempt in range(1, total_attempts + 1):
        try:
            return await client.titles.batch_get(ids)
        except IMDBAPIRateLimitError as exc:
            last_exc = exc
            if attempt == total_attempts:
                break
            delay = _extract_retry_after(exc)
            logger.warning(
                f"batch_get rate-limited (attempt {attempt}/{total_attempts}) — retrying in {delay:.0f}s: {exc}"
            )
            await asyncio.sleep(delay)
            delay *= 2  # exponential backoff for subsequent retries
    raise last_exc or IMDBAPIRateLimitError(429, "rate limited")


async def _search_best_match(
    client: IMDBAPIClient,
    candidate: dict[str, Any],
    search_limit: int,
) -> tuple[dict[str, Any], str | None, float]:
    """Search IMDb for a title matching *candidate* and return the best hit.

    Args:
        client: The IMDb API client.
        candidate: The RAG candidate dict.
        search_limit: Max number of hits to fetch from search.
    Returns:
        A tuple of (candidate, best_imdb_id, confidence_score).
    """
    title = candidate.get("title", "")
    year = candidate.get("release_year", 0)
    query = f"{title} {year}" if year else title

    total_attempts = _RETRY_MAX_RETRIES + 1
    delay = _DEFAULT_RETRY_AFTER
    for attempt in range(1, total_attempts + 1):
        try:
            result = await client.search.titles(query, limit=search_limit)
            break  # success
        except IMDBAPIRateLimitError as exc:
            if attempt == total_attempts:
                logger.warning(f"IMDB search failed for '{title}': {exc}")
                return candidate, None, 0.0
            delay = _extract_retry_after(exc)
            logger.warning(
                f"Search rate-limited for '{title}' (attempt {attempt}/{total_attempts}) — retrying in {delay:.0f}s"
            )
            await asyncio.sleep(delay)
            delay *= 2  # exponential backoff for subsequent retries
        except Exception as exc:
            logger.warning(f"IMDB search failed for '{title}': {exc}")
            return candidate, None, 0.0

    best_id: str | None = None
    best_score = 0.0
    best_title = ""

    for hit in result.titles:
        score = _compute_confidence(candidate, hit)
        if score > best_score:
            best_score = score
            best_id = hit.id
            best_title = hit.primary_title or ""

    if best_id:
        logger.debug(f"IMDb match: {title!r} → {best_title!r} ({best_id}) conf={best_score:.2f}")
    else:
        logger.debug(f"IMDb: no match found for {title!r} (searched {len(result.titles)} hits)")

    return candidate, best_id, best_score


def _compute_confidence(candidate: dict[str, Any], imdb_hit: Title) -> float:
    """Score how well an IMDb search hit matches a RAG candidate (0–1).

    Blends two signals:
    - ``rag_score``: Qdrant cosine similarity — how semantically relevant this
      movie is to the user's plot description (query-level relevance).
    - ``imdb_match``: title + year proximity — how confidently we matched the
      RAG candidate to the correct IMDb record (record-level correctness).

    Weight: 40% vector relevance + 60% IMDb match.  This ensures candidates
    with identical IMDb record quality (e.g. exact title+year) are still
    differentiated by their semantic distance to the user's query.

    Args:
        candidate: The RAG candidate dict.
        imdb_hit: The IMDb Title hit summary.

    Returns:
        A confidence score between 0.0 and 1.0.
    """
    # --- IMDb match score: title similarity + year proximity (0–1) ---
    imdb_match = 0.0

    rag_year: int = candidate.get("release_year") or 0
    imdb_year: int = imdb_hit.start_year or 0
    if rag_year and imdb_year:
        diff = abs(rag_year - imdb_year)
        if diff == 0:
            imdb_match += 0.5
        elif diff <= 2:
            imdb_match += 0.35
        elif diff <= 5:
            imdb_match += 0.15

    rag_title = (candidate.get("title", "") or "").lower().strip()
    imdb_title = (imdb_hit.primary_title or "").lower().strip()
    if rag_title and imdb_title:
        if rag_title == imdb_title:
            imdb_match += 0.5
        elif rag_title in imdb_title or imdb_title in rag_title:
            imdb_match += 0.35
        else:
            ratio = SequenceMatcher(None, rag_title, imdb_title).ratio()
            imdb_match += ratio * 0.3

    # --- RAG vector similarity (Qdrant cosine score, already 0–1) ---
    rag_score: float = float(candidate.get("rag_score") or 0.0)

    # --- Weighted blend ---
    return min(0.4 * rag_score + 0.6 * imdb_match, 1.0)


def _title_to_dict(title: Title) -> dict[str, Any]:
    """Convert a Title model to a plain dict for state storage.

    Args:
        title: The IMDb Title model.

    Returns:
        A dictionary representation of the title metadata.
    """
    directors = [d.display_name for d in (title.directors or [])]
    stars = [s.display_name for s in (title.stars or [])]
    rating_obj = title.rating
    image_obj = title.primary_image

    return {
        "id": title.id,
        "primaryTitle": title.primary_title,
        "startYear": title.start_year,
        "rating": rating_obj.aggregate_rating if rating_obj else None,
        "plot": title.plot,
        "genres": title.genres or [],
        "directors": directors,
        "stars": stars,
        "posterUrl": image_obj.url if image_obj else None,
    }
