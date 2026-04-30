"""Tests for MovieSearchService.

All embedding and vector-store calls are mocked — no real network traffic.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from chain.models.output import RagCandidate
from chain.rag.service import MovieSearchService, _to_list
from chain.rag.vector_store import VectorSearchHit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_vector_hits() -> list[MagicMock]:
    """Three fake vector-search hits."""

    def _make_point(payload: dict[str, Any]) -> MagicMock:
        pt = MagicMock()
        pt.payload = payload
        return pt

    return [
        _make_point(
            {
                "title": "Inception",
                "release_year": 2010,
                "director": "Christopher Nolan",
                "genre": ["Action", "Sci-Fi"],
                "cast": ["Leonardo DiCaprio", "Joseph Gordon-Levitt"],
                "plot": "A thief who steals secrets through dreams.",
            }
        ),
        _make_point(
            {
                "title": "The Matrix",
                "release_year": 1999,
                "director": "Lana Wachowski",
                "genre": "Action/Sci-Fi",  # slash-separated string
                "cast": "Keanu Reeves, Laurence Fishburne",  # comma-separated string
                "plot": "A hacker discovers reality is a simulation.",
            }
        ),
        _make_point({"title": "Ghost Movie", "release_year": None, "director": ""}),
    ]


@pytest.fixture
def service(mock_config: Any) -> MovieSearchService:
    """Return a MovieSearchService with mocked embedding and Qdrant clients."""
    with (
        patch("chain.rag.service.get_query_embedder"),
        patch("chain.rag.service.get_vector_search_provider"),
    ):
        svc = MovieSearchService(mock_config)

    # Replace real clients with controllable mocks
    svc._embedder = MagicMock()
    svc._vector_store = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# search() — happy path
# ---------------------------------------------------------------------------


def test_search_returns_rag_candidates(
    service: MovieSearchService, fake_vector_hits: list[MagicMock]
) -> None:
    # Arrange: embedding provider returns a fake vector
    cast(Any, service._embedder).embed_query.return_value = [0.1] * 3072

    # Arrange: vector store returns our fake hits
    cast(Any, service._vector_store).search.return_value = [
        VectorSearchHit(payload=cast(dict[str, Any], point.payload), score=0.9)
        for point in fake_vector_hits
    ]

    # Act
    results = service.search("a heist movie set in dreams", top_k=3)

    # Assert
    assert len(results) == 3
    assert all(isinstance(r, RagCandidate) for r in results)


def test_search_uses_query_embedder(
    service: MovieSearchService, fake_vector_hits: list[MagicMock]
) -> None:
    cast(Any, service._embedder).embed_query.return_value = [0.0] * 3072

    cast(Any, service._vector_store).search.return_value = []

    service.search("test query")

    cast(Any, service._embedder).embed_query.assert_called_once_with("test query")


def test_search_uses_correct_vector_target(
    service: MovieSearchService, fake_vector_hits: list[MagicMock]
) -> None:
    cast(Any, service._embedder).embed_query.return_value = [0.0] * 3072

    cast(Any, service._vector_store).search.return_value = []

    service.search("test query", top_k=5)

    cast(Any, service._vector_store).search.assert_called_once_with(
        [0.0] * 3072,
        5,
        service._embedding_model,
    )


def test_search_normalises_genre_string(
    service: MovieSearchService, fake_vector_hits: list[MagicMock]
) -> None:
    """Slash-separated genre strings are split into a list."""
    cast(Any, service._embedder).embed_query.return_value = [0.0] * 3072

    cast(Any, service._vector_store).search.return_value = [
        VectorSearchHit(payload=cast(dict[str, Any], point.payload), score=0.9)
        for point in fake_vector_hits
    ]

    results = service.search("query")

    # The second point has "Action/Sci-Fi" as a slash-separated string
    matrix_result = next(r for r in results if r.title == "The Matrix")
    assert isinstance(matrix_result.genre, list)
    assert "Action" in matrix_result.genre
    assert "Sci-Fi" in matrix_result.genre


def test_search_handles_missing_year(
    service: MovieSearchService, fake_vector_hits: list[MagicMock]
) -> None:
    """Points with release_year=None default to 0, not a crash."""
    cast(Any, service._embedder).embed_query.return_value = [0.0] * 3072

    cast(Any, service._vector_store).search.return_value = [
        VectorSearchHit(payload=cast(dict[str, Any], point.payload), score=0.9)
        for point in fake_vector_hits
    ]

    results = service.search("query")
    ghost = next(r for r in results if r.title == "Ghost Movie")
    assert ghost.release_year == 0


def test_search_empty_results(service: MovieSearchService) -> None:
    """Empty vector search results produce an empty list — no crash."""
    cast(Any, service._embedder).embed_query.return_value = [0.0] * 3072

    cast(Any, service._vector_store).search.return_value = []

    results = service.search("obscure movie nobody remembers")
    assert results == []


# ---------------------------------------------------------------------------
# _to_list() — conversion helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (["Action", "Drama"], ["Action", "Drama"]),
        ("Action/Drama", ["Action", "Drama"]),
        ("Action, Drama", ["Action", "Drama"]),
        ("Drama", ["Drama"]),
        ("", []),
        (None, []),
        (42, []),
    ],
)
def test_to_list(value: Any, expected: list[str]) -> None:
    assert _to_list(value) == expected
