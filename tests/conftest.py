"""Shared pytest fixtures for the movie-finder chain test suite.

External dependencies are fully mocked so tests run without:
- A running Qdrant instance
- Real OpenAI API credits
- Real Anthropic API credits
- Real IMDb API access

Pattern mirrors backend/imdbapi/tests/conftest.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from chain.config import ChainConfig, get_config
from chain.models.output import ConfirmationClassification, RefinementPlan

# ---------------------------------------------------------------------------
# Config fixture — isolated from real env vars
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_config_cache() -> Iterator[None]:
    """Clear the lru_cache on get_config before and after every test."""
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def mock_config(monkeypatch: pytest.MonkeyPatch) -> ChainConfig:
    """Return a ChainConfig pre-loaded with test-safe values."""
    monkeypatch.setenv("QDRANT_ENDPOINT", "https://test.qdrant.io")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_config.cache_clear()
    cfg = get_config()
    return cfg


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_rag_candidates() -> list[dict[str, Any]]:
    """Three RAG candidates as plain dicts (as stored in state)."""
    return [
        {
            "title": "Inception",
            "release_year": 2010,
            "director": "Christopher Nolan",
            "genre": ["Action", "Adventure", "Sci-Fi"],
            "cast": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Ellen Page"],
            "plot": "A thief who enters the dreams of others to steal secrets.",
        },
        {
            "title": "The Matrix",
            "release_year": 1999,
            "director": "Lana Wachowski",
            "genre": ["Action", "Sci-Fi"],
            "cast": ["Keanu Reeves", "Laurence Fishburne", "Carrie-Anne Moss"],
            "plot": "A hacker discovers the reality he knows is a simulation.",
        },
        {
            "title": "Interstellar",
            "release_year": 2014,
            "director": "Christopher Nolan",
            "genre": ["Adventure", "Drama", "Sci-Fi"],
            "cast": ["Matthew McConaughey", "Anne Hathaway", "Jessica Chastain"],
            "plot": "A team of explorers travel through a wormhole in space.",
        },
    ]


@pytest.fixture
def sample_enriched_movies() -> list[dict[str, Any]]:
    """Three enriched movies (RAG + IMDb data merged) for node/graph tests."""
    return [
        {
            "rag_title": "Inception",
            "rag_year": 2010,
            "rag_director": "Christopher Nolan",
            "rag_genre": ["Action", "Sci-Fi"],
            "rag_cast": ["Leonardo DiCaprio"],
            "rag_plot": "A thief who steals corporate secrets through dream-sharing.",
            "imdb_id": "tt1375666",
            "imdb_title": "Inception",
            "imdb_year": 2010,
            "imdb_rating": 8.8,
            "imdb_plot": "A thief who steals corporate secrets through the use of dream-sharing technology.",
            "imdb_genres": ["Action", "Adventure", "Sci-Fi"],
            "imdb_directors": ["Christopher Nolan"],
            "imdb_stars": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
            "imdb_poster_url": "https://example.com/inception.jpg",
            "confidence": 0.95,
        },
        {
            "rag_title": "The Matrix",
            "rag_year": 1999,
            "rag_director": "Lana Wachowski",
            "rag_genre": ["Action", "Sci-Fi"],
            "rag_cast": ["Keanu Reeves"],
            "rag_plot": "A hacker discovers reality is a simulation.",
            "imdb_id": "tt0133093",
            "imdb_title": "The Matrix",
            "imdb_year": 1999,
            "imdb_rating": 8.7,
            "imdb_plot": "When a beautiful stranger leads computer hacker Neo to a forbidding underworld.",
            "imdb_genres": ["Action", "Sci-Fi"],
            "imdb_directors": ["Lana Wachowski", "Lilly Wachowski"],
            "imdb_stars": ["Keanu Reeves", "Laurence Fishburne", "Carrie-Anne Moss"],
            "imdb_poster_url": "https://example.com/matrix.jpg",
            "confidence": 0.90,
        },
        {
            "rag_title": "Interstellar",
            "rag_year": 2014,
            "rag_director": "Christopher Nolan",
            "rag_genre": ["Sci-Fi", "Drama"],
            "rag_cast": ["Matthew McConaughey"],
            "rag_plot": "Explorers travel through a wormhole.",
            "imdb_id": "tt0816692",
            "imdb_title": "Interstellar",
            "imdb_year": 2014,
            "imdb_rating": 8.7,
            "imdb_plot": "A team of explorers travel through a wormhole in space.",
            "imdb_genres": ["Adventure", "Drama", "Sci-Fi"],
            "imdb_directors": ["Christopher Nolan"],
            "imdb_stars": ["Matthew McConaughey", "Anne Hathaway", "Jessica Chastain"],
            "imdb_poster_url": "https://example.com/interstellar.jpg",
            "confidence": 0.88,
        },
    ]


@pytest.fixture
def sample_confirmed_movie() -> dict[str, Any]:
    """A confirmed movie dict (post-confirmation state)."""
    return {
        "rag_title": "Inception",
        "rag_year": 2010,
        "rag_director": "Christopher Nolan",
        "rag_genre": ["Action", "Sci-Fi"],
        "rag_cast": ["Leonardo DiCaprio"],
        "rag_plot": "A thief who steals corporate secrets through dream-sharing.",
        "imdb_id": "tt1375666",
        "imdb_title": "Inception",
        "imdb_year": 2010,
        "imdb_rating": 8.8,
        "imdb_plot": "A thief who steals corporate secrets through the use of dream-sharing technology.",
        "imdb_genres": ["Action", "Adventure", "Sci-Fi"],
        "imdb_directors": ["Christopher Nolan"],
        "imdb_stars": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
        "imdb_poster_url": "https://example.com/inception.jpg",
        "confidence": 0.95,
    }


# ---------------------------------------------------------------------------
# Structured-output classifier stubs
# ---------------------------------------------------------------------------


@pytest.fixture
def confirmed_classification() -> ConfirmationClassification:
    return ConfirmationClassification(
        decision="confirmed", movie_index=0, reasoning="User said it's #1"
    )


@pytest.fixture
def not_found_classification() -> ConfirmationClassification:
    return ConfirmationClassification(decision="not_found", reasoning="User said none match")


@pytest.fixture
def refinement_plan() -> RefinementPlan:
    return RefinementPlan(
        refined_query=(
            "A sci-fi heist movie where a team of thieves enter people's dreams "
            "to plant an idea, set in a world where dream-sharing technology exists"
        ),
        message_to_user="Let me search again with your updated details…",
    )
