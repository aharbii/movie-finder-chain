"""Unit tests for all LangGraph nodes.

Every external dependency is mocked:
- LLM calls (ChatAnthropic.with_structured_output, create_movie_agent)
- IMDBAPIClient (async context manager)
- MovieSearchService
- get_config → uses mock_config fixture from conftest

Tests validate:
- Correct state keys are written
- Edge cases (empty candidates, unclear responses, max refinements)
- Error handling (LLM failure, IMDB call failure)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from chain.models.output import ConfirmationClassification, RefinementPlan
from chain.nodes.confirmation import confirmation_node
from chain.nodes.dead_end import dead_end_node
from chain.nodes.imdb_enrichment import _compute_confidence, imdb_enrichment_node
from chain.nodes.presentation import presentation_node
from chain.nodes.qa_agent import qa_agent_node
from chain.nodes.rag_search import _get_search_service, rag_search_node
from chain.nodes.refinement import refinement_node
from chain.nodes.validation import validation_node

# ===========================================================================
# rag_search_node
# ===========================================================================


class TestRagSearchNode:
    def test_search_service_is_cached_singleton(self, mock_config: Any) -> None:
        _get_search_service.cache_clear()

        with (
            patch("chain.nodes.rag_search.get_config", return_value=mock_config),
            patch("chain.nodes.rag_search.MovieSearchService") as mock_service_cls,
        ):
            first = _get_search_service()
            second = _get_search_service()

        assert first is second
        mock_service_cls.assert_called_once_with(mock_config)
        _get_search_service.cache_clear()

    @pytest.mark.asyncio
    async def test_extracts_query_from_last_human_message(self, mock_config: Any) -> None:
        """Uses last HumanMessage content when user_plot_query is not set."""
        state = {
            "messages": [HumanMessage(content="A movie where dreams are invaded")],
            "user_plot_query": "",
        }

        mock_candidates = [
            MagicMock(
                model_dump=lambda: {
                    "title": "Inception",
                    "release_year": 2010,
                    "director": "",
                    "genre": [],
                    "cast": [],
                    "plot": "",
                }
            )
        ]

        with (
            patch("chain.nodes.rag_search.get_config", return_value=mock_config),
            patch("chain.nodes.rag_search._get_search_service") as mock_get_svc,
        ):
            mock_svc = mock_get_svc.return_value
            mock_svc.search.return_value = mock_candidates

            result = await rag_search_node(state, {})  # type: ignore[arg-type]

        assert result["user_plot_query"] == "A movie where dreams are invaded"
        assert len(result["rag_candidates"]) == 1

    @pytest.mark.asyncio
    async def test_prefers_explicit_user_plot_query(self, mock_config: Any) -> None:
        """An explicit user_plot_query overrides the last message content."""
        state = {
            "messages": [HumanMessage(content="original message")],
            "user_plot_query": "refined: a sci-fi heist set in dreams",
        }

        with (
            patch("chain.nodes.rag_search.get_config", return_value=mock_config),
            patch("chain.nodes.rag_search._get_search_service") as mock_get_svc,
        ):
            mock_svc = mock_get_svc.return_value
            mock_svc.search.return_value = []

            result = await rag_search_node(state, {})  # type: ignore[arg-type]

        assert "refined" in result["user_plot_query"]

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_candidates(self, mock_config: Any) -> None:
        state: dict[str, Any] = {"messages": [], "user_plot_query": ""}

        with (
            patch("chain.nodes.rag_search.get_config", return_value=mock_config),
            patch("chain.nodes.rag_search._get_search_service"),
        ):
            result = await rag_search_node(state, {})  # type: ignore[arg-type]

        assert result["rag_candidates"] == []


# ===========================================================================
# imdb_enrichment_node
# ===========================================================================


class TestImdbEnrichmentNode:
    @pytest.mark.asyncio
    async def test_returns_enriched_movies_when_match_found(
        self, mock_config: Any, sample_rag_candidates: list[dict[str, Any]]
    ) -> None:
        """Enriches each candidate when IMDB search returns a confident match."""
        state = {"rag_candidates": sample_rag_candidates[:1]}  # just Inception

        # Fake IMDB search result
        mock_search_hit = MagicMock()
        mock_search_hit.id = "tt1375666"
        mock_search_hit.start_year = 2010
        mock_search_hit.primary_title = "Inception"

        mock_search_resp = MagicMock()
        mock_search_resp.titles = [mock_search_hit]

        # Fake full title from batch_get
        mock_full_title = MagicMock()
        mock_full_title.id = "tt1375666"
        mock_full_title.primary_title = "Inception"
        mock_full_title.start_year = 2010
        mock_full_title.rating = MagicMock(aggregate_rating=8.8)
        mock_full_title.plot = "A thief who steals secrets."
        mock_full_title.genres = ["Action", "Sci-Fi"]
        mock_full_title.directors = [MagicMock(display_name="Christopher Nolan")]
        mock_full_title.stars = [MagicMock(display_name="Leonardo DiCaprio")]
        mock_full_title.primary_image = MagicMock(url="https://example.com/poster.jpg")

        mock_batch_resp = MagicMock()
        mock_batch_resp.titles = [mock_full_title]

        mock_client = AsyncMock()
        mock_client.search.titles = AsyncMock(return_value=mock_search_resp)
        mock_client.titles.batch_get = AsyncMock(return_value=mock_batch_resp)

        # Patch IMDBAPIClient as async context manager
        with (
            patch("chain.nodes.imdb_enrichment.get_config", return_value=mock_config),
            patch("chain.nodes.imdb_enrichment.IMDBAPIClient") as mock_client_cls,
        ):
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await imdb_enrichment_node(state)  # type: ignore[arg-type]

        enriched = result["enriched_movies"]
        assert len(enriched) == 1
        assert enriched[0]["imdb_id"] == "tt1375666"
        assert enriched[0]["imdb_title"] == "Inception"
        assert enriched[0]["imdb_rating"] == 8.8
        assert enriched[0]["imdb_poster_url"] == "https://example.com/poster.jpg"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_candidates(self, mock_config: Any) -> None:
        state: dict[str, Any] = {"rag_candidates": []}

        with patch("chain.nodes.imdb_enrichment.get_config", return_value=mock_config):
            result = await imdb_enrichment_node(state)  # type: ignore[arg-type]

        assert result["enriched_movies"] == []

    @pytest.mark.asyncio
    async def test_handles_imdb_search_failure_gracefully(
        self, mock_config: Any, sample_rag_candidates: list[dict[str, Any]]
    ) -> None:
        """A failed IMDB search for one candidate does not crash the whole node."""
        state = {"rag_candidates": sample_rag_candidates[:1]}

        mock_client = AsyncMock()
        mock_client.search.titles = AsyncMock(side_effect=Exception("IMDB timeout"))

        with (
            patch("chain.nodes.imdb_enrichment.get_config", return_value=mock_config),
            patch("chain.nodes.imdb_enrichment.IMDBAPIClient") as mock_client_cls,
        ):
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await imdb_enrichment_node(state)  # type: ignore[arg-type]

        # Should return the candidate with imdb_id=None, not crash
        enriched = result["enriched_movies"]
        assert len(enriched) == 1
        assert enriched[0]["imdb_id"] is None
        assert enriched[0]["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_returns_degraded_rag_only_results_on_timeout(
        self, mock_config: Any, sample_rag_candidates: list[dict[str, Any]]
    ) -> None:
        state = {"rag_candidates": sample_rag_candidates[:1]}

        with (
            patch("chain.nodes.imdb_enrichment.get_config", return_value=mock_config),
            patch(
                "chain.nodes.imdb_enrichment._run_imdb_enrichment",
                new=AsyncMock(side_effect=TimeoutError),
            ),
        ):
            result = await imdb_enrichment_node(state)  # type: ignore[arg-type]

        enriched = result["enriched_movies"]
        assert len(enriched) == 1
        assert enriched[0]["rag_title"] == "Inception"
        assert enriched[0]["imdb_id"] is None
        assert enriched[0]["imdb_title"] is None
        assert enriched[0]["confidence"] == 0.0


class TestComputeConfidence:
    def _make_hit(self, title: str, year: int | None) -> MagicMock:
        hit = MagicMock()
        hit.primary_title = title
        hit.start_year = year
        return hit

    def test_exact_title_and_year_high_confidence(self) -> None:
        # rag_score=0 (no Qdrant score in unit test) + perfect IMDb match (1.0)
        # → 0.4*0 + 0.6*1.0 = 0.6
        candidate = {"title": "Inception", "release_year": 2010, "rag_score": 0.0}
        hit = self._make_hit("Inception", 2010)
        score = _compute_confidence(candidate, hit)
        assert score == pytest.approx(0.6)

    def test_rag_score_blended_into_confidence(self) -> None:
        # Exact title+year IMDb match (imdb_match=1.0) + high rag_score
        # → 0.4*0.9 + 0.6*1.0 = 0.96
        candidate = {"title": "Inception", "release_year": 2010, "rag_score": 0.9}
        hit = self._make_hit("Inception", 2010)
        score = _compute_confidence(candidate, hit)
        assert score == pytest.approx(0.96)

    def test_rag_score_differentiates_equal_imdb_matches(self) -> None:
        # Two candidates with identical IMDb match but different rag_scores
        high = {"title": "Inception", "release_year": 2010, "rag_score": 0.92}
        low = {"title": "Inception", "release_year": 2010, "rag_score": 0.75}
        hit = self._make_hit("Inception", 2010)
        assert _compute_confidence(high, hit) > _compute_confidence(low, hit)

    def test_year_off_by_two_still_reasonable(self) -> None:
        candidate = {"title": "Inception", "release_year": 2010, "rag_score": 0.0}
        hit = self._make_hit("Inception", 2012)
        score = _compute_confidence(candidate, hit)
        assert 0.2 < score < 0.7

    def test_completely_different_title_and_year_low_confidence(self) -> None:
        candidate = {"title": "Inception", "release_year": 2010, "rag_score": 0.0}
        hit = self._make_hit("Titanic", 1997)
        score = _compute_confidence(candidate, hit)
        assert score < 0.2

    def test_no_year_uses_title_only(self) -> None:
        # No year → only title contributes to imdb_match (0.5), rag_score=0
        # → 0.4*0 + 0.6*0.5 = 0.3
        candidate = {"title": "Inception", "release_year": 0, "rag_score": 0.0}
        hit = self._make_hit("Inception", None)
        score = _compute_confidence(candidate, hit)
        assert score == pytest.approx(0.3)


# ===========================================================================
# validation_node
# ===========================================================================


class TestValidationNode:
    @pytest.mark.asyncio
    async def test_filters_below_confidence_threshold(self, mock_config: Any) -> None:
        movies = [
            {"imdb_id": "tt0000001", "confidence": 0.9, "rag_title": "Good Match"},
            {"imdb_id": "tt0000002", "confidence": 0.1, "rag_title": "Bad Match"},
        ]
        state = {"enriched_movies": movies}

        with patch("chain.nodes.validation.get_config", return_value=mock_config):
            result = await validation_node(state)  # type: ignore[arg-type]

        # Default threshold is 0.3; 0.1 should be excluded
        assert all(m["confidence"] >= 0.3 for m in result["enriched_movies"])
        assert len(result["enriched_movies"]) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_movies(self, mock_config: Any) -> None:
        state: dict[str, Any] = {"enriched_movies": []}
        with patch("chain.nodes.validation.get_config", return_value=mock_config):
            result = await validation_node(state)  # type: ignore[arg-type]
        assert result["enriched_movies"] == []


# ===========================================================================
# presentation_node
# ===========================================================================


class TestPresentationNode:
    @pytest.mark.asyncio
    async def test_returns_ai_message_with_movie_list(
        self, sample_enriched_movies: list[dict[str, Any]]
    ) -> None:
        state = {"enriched_movies": sample_enriched_movies, "refinement_count": 0}
        result = await presentation_node(state)  # type: ignore[arg-type]

        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)
        assert "Inception" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_sets_phase_to_confirmation(
        self, sample_enriched_movies: list[dict[str, Any]]
    ) -> None:
        state = {"enriched_movies": sample_enriched_movies, "refinement_count": 0}
        result = await presentation_node(state)  # type: ignore[arg-type]
        assert result["phase"] == "confirmation"

    @pytest.mark.asyncio
    async def test_includes_all_candidate_titles(
        self, sample_enriched_movies: list[dict[str, Any]]
    ) -> None:
        state = {"enriched_movies": sample_enriched_movies, "refinement_count": 0}
        result = await presentation_node(state)  # type: ignore[arg-type]
        content = str(result["messages"][0].content)
        for movie in sample_enriched_movies:
            assert movie["imdb_title"] in content

    @pytest.mark.asyncio
    async def test_empty_candidates_produces_fallback_message(self) -> None:
        state = {"enriched_movies": [], "refinement_count": 0}
        result = await presentation_node(state)  # type: ignore[arg-type]
        assert "couldn't find" in str(result["messages"][0].content).lower()
        assert result["phase"] == "discovery"

    @pytest.mark.asyncio
    async def test_refinement_message_shown_after_search_again(
        self, sample_enriched_movies: list[dict[str, Any]]
    ) -> None:
        state = {"enriched_movies": sample_enriched_movies, "refinement_count": 1}
        result = await presentation_node(state)  # type: ignore[arg-type]
        assert "searched again" in str(result["messages"][0].content).lower()


# ===========================================================================
# confirmation_node
# ===========================================================================


class TestConfirmationNode:
    def _make_llm_mock(self, classification: ConfirmationClassification) -> MagicMock:
        """Build a mock LLM chain: ChatAnthropic().with_structured_output().ainvoke()."""
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=classification)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain
        return mock_llm

    @pytest.mark.asyncio
    async def test_confirmed_sets_confirmed_movie_fields(
        self,
        mock_config: Any,
        sample_enriched_movies: list[dict[str, Any]],
        confirmed_classification: ConfirmationClassification,
    ) -> None:
        state = {
            "messages": [HumanMessage(content="It's number 1!")],
            "enriched_movies": sample_enriched_movies,
            "refinement_count": 0,
        }

        with (
            patch("chain.nodes.confirmation.get_config", return_value=mock_config),
            patch(
                "chain.nodes.confirmation.ChatAnthropic",
                return_value=self._make_llm_mock(confirmed_classification),
            ),
        ):
            result = await confirmation_node(state)  # type: ignore[arg-type]

        assert result["next_action"] == "confirmed"
        assert result["confirmed_movie_id"] == sample_enriched_movies[0]["imdb_id"]
        assert result["confirmed_movie_title"] == sample_enriched_movies[0]["imdb_title"]
        assert result["confirmed_movie_data"] == sample_enriched_movies[0]

    @pytest.mark.asyncio
    async def test_not_found_sets_refine_action(
        self,
        mock_config: Any,
        sample_enriched_movies: list[dict[str, Any]],
        not_found_classification: ConfirmationClassification,
    ) -> None:
        state = {
            "messages": [HumanMessage(content="None of these match.")],
            "enriched_movies": sample_enriched_movies,
            "refinement_count": 0,
        }

        with (
            patch("chain.nodes.confirmation.get_config", return_value=mock_config),
            patch(
                "chain.nodes.confirmation.ChatAnthropic",
                return_value=self._make_llm_mock(not_found_classification),
            ),
        ):
            result = await confirmation_node(state)  # type: ignore[arg-type]

        assert result["next_action"] == "refine"

    @pytest.mark.asyncio
    async def test_not_found_exhausted_when_max_refinements_reached(
        self,
        mock_config: Any,
        sample_enriched_movies: list[dict[str, Any]],
        not_found_classification: ConfirmationClassification,
    ) -> None:
        state = {
            "messages": [HumanMessage(content="Still not right.")],
            "enriched_movies": sample_enriched_movies,
            "refinement_count": 3,  # at the limit
        }

        with (
            patch("chain.nodes.confirmation.get_config", return_value=mock_config),
            patch(
                "chain.nodes.confirmation.ChatAnthropic",
                return_value=self._make_llm_mock(not_found_classification),
            ),
        ):
            result = await confirmation_node(state)  # type: ignore[arg-type]

        assert result["next_action"] == "exhausted"

    @pytest.mark.asyncio
    async def test_unclear_response_sets_wait_and_adds_clarification(
        self, mock_config: Any, sample_enriched_movies: list[dict[str, Any]]
    ) -> None:
        unclear = ConfirmationClassification(decision="unclear", reasoning="ambiguous")
        state = {
            "messages": [HumanMessage(content="hmm maybe?")],
            "enriched_movies": sample_enriched_movies,
            "refinement_count": 0,
        }

        with (
            patch("chain.nodes.confirmation.get_config", return_value=mock_config),
            patch(
                "chain.nodes.confirmation.ChatAnthropic", return_value=self._make_llm_mock(unclear)
            ),
        ):
            result = await confirmation_node(state)  # type: ignore[arg-type]

        assert result["next_action"] == "wait"
        assert any(isinstance(m, AIMessage) for m in result.get("messages", []))

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_wait(
        self, mock_config: Any, sample_enriched_movies: list[dict[str, Any]]
    ) -> None:
        """LLM exception → graceful wait, no crash."""
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(side_effect=Exception("LLM unavailable"))
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain

        state = {
            "messages": [HumanMessage(content="The second one!")],
            "enriched_movies": sample_enriched_movies,
            "refinement_count": 0,
        }

        with (
            patch("chain.nodes.confirmation.get_config", return_value=mock_config),
            patch("chain.nodes.confirmation.ChatAnthropic", return_value=mock_llm),
        ):
            result = await confirmation_node(state)  # type: ignore[arg-type]

        assert result["next_action"] == "wait"

    @pytest.mark.asyncio
    async def test_no_human_message_returns_wait(
        self, mock_config: Any, sample_enriched_movies: list[dict[str, Any]]
    ) -> None:
        state = {
            "messages": [AIMessage(content="Here are the candidates…")],
            "enriched_movies": sample_enriched_movies,
            "refinement_count": 0,
        }

        with patch("chain.nodes.confirmation.get_config", return_value=mock_config):
            result = await confirmation_node(state)  # type: ignore[arg-type]

        assert result["next_action"] == "wait"


# ===========================================================================
# refinement_node
# ===========================================================================


class TestRefinementNode:
    def _make_llm_mock(self, plan: RefinementPlan) -> MagicMock:
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=plan)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain
        return mock_llm

    @pytest.mark.asyncio
    async def test_updates_user_plot_query(
        self, mock_config: Any, refinement_plan: RefinementPlan
    ) -> None:
        state = {
            "messages": [
                HumanMessage(content="A heist movie where they steal dreams"),
                AIMessage(content="Here are candidates..."),
                HumanMessage(content="None of these, it was set in space"),
            ],
            "user_plot_query": "A heist movie where they steal dreams",
            "refinement_count": 0,
        }

        with (
            patch("chain.nodes.refinement.get_config", return_value=mock_config),
            patch(
                "chain.nodes.refinement.ChatAnthropic",
                return_value=self._make_llm_mock(refinement_plan),
            ),
        ):
            result = await refinement_node(state)  # type: ignore[arg-type]

        assert result["user_plot_query"] == refinement_plan.refined_query
        assert result["refinement_count"] == 1

    @pytest.mark.asyncio
    async def test_increments_refinement_count(
        self, mock_config: Any, refinement_plan: RefinementPlan
    ) -> None:
        state = {
            "messages": [HumanMessage(content="not right")],
            "user_plot_query": "query",
            "refinement_count": 1,
        }

        with (
            patch("chain.nodes.refinement.get_config", return_value=mock_config),
            patch(
                "chain.nodes.refinement.ChatAnthropic",
                return_value=self._make_llm_mock(refinement_plan),
            ),
        ):
            result = await refinement_node(state)  # type: ignore[arg-type]

        assert result["refinement_count"] == 2

    @pytest.mark.asyncio
    async def test_adds_ai_message_to_state(
        self, mock_config: Any, refinement_plan: RefinementPlan
    ) -> None:
        state = {
            "messages": [HumanMessage(content="no match")],
            "user_plot_query": "original query",
            "refinement_count": 0,
        }

        with (
            patch("chain.nodes.refinement.get_config", return_value=mock_config),
            patch(
                "chain.nodes.refinement.ChatAnthropic",
                return_value=self._make_llm_mock(refinement_plan),
            ),
        ):
            result = await refinement_node(state)  # type: ignore[arg-type]

        assert any(isinstance(m, AIMessage) for m in result.get("messages", []))
        ai_content = next(m.content for m in result["messages"] if isinstance(m, AIMessage))
        assert ai_content == refinement_plan.message_to_user

    @pytest.mark.asyncio
    async def test_llm_failure_uses_original_query(self, mock_config: Any) -> None:
        """LLM error falls back to the original query so the loop can continue."""
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(side_effect=Exception("API error"))
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain

        state = {
            "messages": [HumanMessage(content="no match")],
            "user_plot_query": "my original query",
            "refinement_count": 0,
        }

        with (
            patch("chain.nodes.refinement.get_config", return_value=mock_config),
            patch("chain.nodes.refinement.ChatAnthropic", return_value=mock_llm),
        ):
            result = await refinement_node(state)  # type: ignore[arg-type]

        assert result["user_plot_query"] == "my original query"
        assert result["refinement_count"] == 1


# ===========================================================================
# dead_end_node
# ===========================================================================


class TestDeadEndNode:
    @pytest.mark.asyncio
    async def test_adds_ai_message(self, mock_config: Any) -> None:
        state = {"user_plot_query": "a movie about robots", "refinement_count": 3}
        result = await dead_end_node(state)  # type: ignore[arg-type]
        assert isinstance(result["messages"][0], AIMessage)


# ===========================================================================
# qa_agent_node
# ===========================================================================


class TestQaAgentNode:
    @pytest.mark.asyncio
    async def test_adds_new_messages_to_state(
        self, mock_config: Any, sample_confirmed_movie: dict[str, Any]
    ) -> None:
        """Agent response is appended as new messages."""
        ai_response = AIMessage(content="Inception is rated PG-13.")
        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(return_value={"messages": [ai_response]})

        state = {
            "messages": [HumanMessage(content="Is it for kids?")],
            "confirmed_movie_data": sample_confirmed_movie,
        }

        with (
            patch("chain.nodes.qa_agent.get_config", return_value=mock_config),
            patch("chain.nodes.qa_agent.IMDBAPIClient") as mock_client_cls,
            patch("chain.nodes.qa_agent.create_movie_agent", return_value=mock_agent),
        ):
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await qa_agent_node(state)  # type: ignore[arg-type]

        # Should have added only the new messages (everything beyond the input)
        assert any(isinstance(m, AIMessage) for m in result["messages"])
        assert result["phase"] == "qa"

    @pytest.mark.asyncio
    async def test_phase_stays_qa(
        self, mock_config: Any, sample_confirmed_movie: dict[str, Any]
    ) -> None:
        state = {
            "messages": [HumanMessage(content="Who are the actors?")],
            "confirmed_movie_data": sample_confirmed_movie,
        }

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(
            return_value={"messages": [AIMessage(content="Stars include…")]}
        )

        with (
            patch("chain.nodes.qa_agent.get_config", return_value=mock_config),
            patch("chain.nodes.qa_agent.IMDBAPIClient") as mock_client_cls,
            patch("chain.nodes.qa_agent.create_movie_agent", return_value=mock_agent),
        ):
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await qa_agent_node(state)  # type: ignore[arg-type]

        assert result["phase"] == "qa"
