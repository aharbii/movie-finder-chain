"""Tests for MovieSearchService.

All OpenAI and Qdrant calls are mocked — no real network traffic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from chain.models.output import RagCandidate
from chain.rag.service import MovieSearchService, _to_list

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_qdrant_points() -> list[MagicMock]:
    """Three fake Qdrant ScoredPoint objects."""

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
    """Return a MovieSearchService with mocked OpenAI and Qdrant clients."""
    with (
        patch("chain.rag.service.OpenAI"),
        patch("chain.rag.service.QdrantClient"),
    ):
        svc = MovieSearchService(mock_config)

    # Replace real clients with controllable mocks
    svc._openai = MagicMock()
    svc._qdrant = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# search() — happy path
# ---------------------------------------------------------------------------


def test_search_returns_rag_candidates(
    service: MovieSearchService, fake_qdrant_points: list[MagicMock]
) -> None:
    # Arrange: OpenAI returns a fake embedding vector
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.1] * 3072)]
    embedding_response.usage.total_tokens = 10
    service._openai.embeddings.create.return_value = embedding_response

    # Arrange: Qdrant returns our fake points
    qdrant_response = MagicMock()
    qdrant_response.points = fake_qdrant_points
    service._qdrant.query_points.return_value = qdrant_response

    # Act
    results = service.search("a heist movie set in dreams", top_k=3)

    # Assert
    assert len(results) == 3
    assert all(isinstance(r, RagCandidate) for r in results)


def test_search_uses_correct_embedding_model(
    service: MovieSearchService, fake_qdrant_points: list[MagicMock]
) -> None:
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.0] * 3072)]
    embedding_response.usage.total_tokens = 5
    service._openai.embeddings.create.return_value = embedding_response

    qdrant_response = MagicMock()
    qdrant_response.points = []
    service._qdrant.query_points.return_value = qdrant_response

    service.search("test query")

    service._openai.embeddings.create.assert_called_once_with(
        input="test query",
        model=service._embedding_model,
    )


def test_search_uses_correct_collection(
    service: MovieSearchService, fake_qdrant_points: list[MagicMock]
) -> None:
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.0] * 3072)]
    embedding_response.usage.total_tokens = 5
    service._openai.embeddings.create.return_value = embedding_response

    qdrant_response = MagicMock()
    qdrant_response.points = []
    service._qdrant.query_points.return_value = qdrant_response

    service.search("test query", top_k=5)

    call_kwargs = service._qdrant.query_points.call_args
    assert call_kwargs.kwargs["collection_name"] == service._collection
    assert call_kwargs.kwargs["limit"] == 5


def test_search_normalises_genre_string(
    service: MovieSearchService, fake_qdrant_points: list[MagicMock]
) -> None:
    """Slash-separated genre strings are split into a list."""
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.0] * 3072)]
    embedding_response.usage.total_tokens = 5
    service._openai.embeddings.create.return_value = embedding_response

    qdrant_response = MagicMock()
    qdrant_response.points = fake_qdrant_points
    service._qdrant.query_points.return_value = qdrant_response

    results = service.search("query")

    # The second point has "Action/Sci-Fi" as a slash-separated string
    matrix_result = next(r for r in results if r.title == "The Matrix")
    assert isinstance(matrix_result.genre, list)
    assert "Action" in matrix_result.genre
    assert "Sci-Fi" in matrix_result.genre


def test_search_handles_missing_year(
    service: MovieSearchService, fake_qdrant_points: list[MagicMock]
) -> None:
    """Points with release_year=None default to 0, not a crash."""
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.0] * 3072)]
    embedding_response.usage.total_tokens = 5
    service._openai.embeddings.create.return_value = embedding_response

    qdrant_response = MagicMock()
    qdrant_response.points = fake_qdrant_points
    service._qdrant.query_points.return_value = qdrant_response

    results = service.search("query")
    ghost = next(r for r in results if r.title == "Ghost Movie")
    assert ghost.release_year == 0


def test_search_empty_results(service: MovieSearchService) -> None:
    """Empty Qdrant results produce an empty list — no crash."""
    embedding_response = MagicMock()
    embedding_response.data = [MagicMock(embedding=[0.0] * 3072)]
    embedding_response.usage.total_tokens = 3
    service._openai.embeddings.create.return_value = embedding_response

    qdrant_response = MagicMock()
    qdrant_response.points = []
    service._qdrant.query_points.return_value = qdrant_response

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
