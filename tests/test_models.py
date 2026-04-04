"""Tests for Pydantic output models.

Validates field defaults, type coercion, computed properties,
and that models serialise/deserialise without data loss.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chain.models.output import (
    CandidatePool,
    ConfirmationClassification,
    ConfirmedMovie,
    EnrichedMovie,
    RagCandidate,
    RefinementPlan,
)

# ===========================================================================
# RagCandidate
# ===========================================================================


class TestRagCandidate:
    def test_required_title(self) -> None:
        c = RagCandidate(title="Inception")
        assert c.title == "Inception"

    def test_defaults(self) -> None:
        c = RagCandidate(title="X")
        assert c.release_year == 0
        assert c.director == ""
        assert c.genre == []
        assert c.cast == []
        assert c.plot == ""

    def test_full_fields(self) -> None:
        c = RagCandidate(
            title="Inception",
            release_year=2010,
            director="Christopher Nolan",
            genre=["Action", "Sci-Fi"],
            cast=["Leonardo DiCaprio"],
            plot="Dream heist.",
        )
        assert c.release_year == 2010
        assert "Action" in c.genre

    def test_serialise_round_trip(self) -> None:
        c = RagCandidate(title="Inception", release_year=2010)
        data = c.model_dump()
        c2 = RagCandidate(**data)
        assert c == c2


# ===========================================================================
# EnrichedMovie
# ===========================================================================


class TestEnrichedMovie:
    def _make(self, **kwargs: object) -> EnrichedMovie:
        base: dict[str, object] = {"rag_title": "Inception", "rag_year": 2010}
        base.update(kwargs)
        return EnrichedMovie(**base)

    def test_minimal_required_fields(self) -> None:
        m = self._make()
        assert m.rag_title == "Inception"
        assert m.imdb_id is None
        assert m.confidence == 0.0

    def test_display_title_prefers_imdb(self) -> None:
        m = self._make(imdb_title="Inception (2010)", imdb_year=2010)
        assert m.display_title == "Inception (2010)"

    def test_display_title_falls_back_to_rag(self) -> None:
        m = self._make()  # no imdb_title
        assert m.display_title == "Inception"

    def test_display_year_prefers_imdb(self) -> None:
        m = self._make(rag_year=2010, imdb_year=2010)
        assert m.display_year == 2010

    def test_display_year_falls_back_to_rag(self) -> None:
        m = self._make(rag_year=2010)  # no imdb_year
        assert m.display_year == 2010

    def test_display_year_none_when_both_missing(self) -> None:
        m = self._make(rag_year=0)
        assert m.display_year is None

    def test_confidence_range(self) -> None:
        m = self._make(confidence=0.85)
        assert m.confidence == 0.85

    def test_round_trip_serialisation(self) -> None:
        m = self._make(imdb_id="tt1375666", imdb_rating=8.8, confidence=0.95)
        data = m.model_dump()
        m2 = EnrichedMovie(**data)
        assert m == m2


# ===========================================================================
# CandidatePool
# ===========================================================================


class TestCandidatePool:
    def test_default_refinement_count(self) -> None:
        pool = CandidatePool(query="dream heist", candidates=[])
        assert pool.refinement_count == 0

    def test_with_candidates(self) -> None:
        movie = EnrichedMovie(rag_title="Inception", rag_year=2010)
        pool = CandidatePool(query="dream heist", candidates=[movie])
        assert len(pool.candidates) == 1


# ===========================================================================
# ConfirmedMovie
# ===========================================================================


class TestConfirmedMovie:
    def test_required_fields(self) -> None:
        m = ConfirmedMovie(imdb_id="tt1375666", title="Inception")
        assert m.imdb_id == "tt1375666"

    def test_optional_fields_default_none_or_empty(self) -> None:
        m = ConfirmedMovie(imdb_id="tt1375666", title="Inception")
        assert m.year is None
        assert m.rating is None
        assert m.plot is None
        assert m.genres == []
        assert m.poster_url is None


# ===========================================================================
# ConfirmationClassification
# ===========================================================================


class TestConfirmationClassification:
    def test_confirmed_with_index(self) -> None:
        c = ConfirmationClassification(decision="confirmed", movie_index=2)
        assert c.decision == "confirmed"
        assert c.movie_index == 2

    def test_not_found_no_index(self) -> None:
        c = ConfirmationClassification(decision="not_found")
        assert c.movie_index is None

    def test_unclear_no_index(self) -> None:
        c = ConfirmationClassification(decision="unclear")
        assert c.movie_index is None

    def test_reasoning_defaults_empty(self) -> None:
        c = ConfirmationClassification(decision="confirmed", movie_index=0)
        assert c.reasoning == ""

    def test_with_reasoning(self) -> None:
        c = ConfirmationClassification(
            decision="confirmed", movie_index=1, reasoning="User said '#2'"
        )
        assert "#2" in c.reasoning


# ===========================================================================
# RefinementPlan
# ===========================================================================


class TestRefinementPlan:
    def test_required_fields(self) -> None:
        plan = RefinementPlan(
            refined_query="sci-fi heist set in dreams",
            message_to_user="Searching again…",
        )
        assert plan.refined_query == "sci-fi heist set in dreams"
        assert plan.message_to_user == "Searching again…"

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            RefinementPlan(refined_query="query")  # type: ignore[call-arg]  # missing message_to_user
