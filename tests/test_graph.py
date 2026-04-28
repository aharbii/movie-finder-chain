"""Tests for graph compilation and routing logic.

Routing functions (_route_by_phase, _route_after_confirmation) are pure —
tested without mocks.

Graph compilation is tested to verify the graph builds without error and
the compiled object exposes the expected interface.
"""

from __future__ import annotations

import os
import sys
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from chain.graph import (
    _route_after_confirmation,
    _route_by_phase,
    checkpoint_lifespan,
    compile_graph,
)
from chain.state import MovieFinderState

# ===========================================================================
# _route_by_phase  (pure function — no external deps)
# ===========================================================================


class TestRouteByPhase:
    def test_default_routes_to_rag_search(self) -> None:
        assert _route_by_phase(cast(MovieFinderState, {})) == "rag_search"

    def test_discovery_routes_to_rag_search(self) -> None:
        assert _route_by_phase(cast(MovieFinderState, {"phase": "discovery"})) == "rag_search"

    def test_confirmation_routes_to_confirmation(self) -> None:
        assert _route_by_phase(cast(MovieFinderState, {"phase": "confirmation"})) == "confirmation"

    def test_qa_routes_to_qa_agent(self) -> None:
        assert _route_by_phase(cast(MovieFinderState, {"phase": "qa"})) == "qa_agent"

    def test_unknown_phase_falls_back_to_rag_search(self) -> None:
        assert (
            _route_by_phase(cast(MovieFinderState, {"phase": "unknown_gibberish"})) == "rag_search"
        )

    def test_none_phase_routes_to_rag_search(self) -> None:
        assert _route_by_phase(cast(MovieFinderState, {"phase": None})) == "rag_search"


# ===========================================================================
# _route_after_confirmation  (pure function — no external deps)
# ===========================================================================


class TestRouteAfterConfirmation:
    def test_confirmed_routes_to_qa_agent(self) -> None:
        assert (
            _route_after_confirmation(cast(MovieFinderState, {"next_action": "confirmed"}))
            == "qa_agent"
        )

    def test_refine_routes_to_refinement(self) -> None:
        assert (
            _route_after_confirmation(cast(MovieFinderState, {"next_action": "refine"}))
            == "refinement"
        )

    def test_exhausted_routes_to_dead_end(self) -> None:
        assert (
            _route_after_confirmation(cast(MovieFinderState, {"next_action": "exhausted"}))
            == "dead_end"
        )

    def test_wait_routes_to_end(self) -> None:
        from langgraph.graph import END

        assert _route_after_confirmation(cast(MovieFinderState, {"next_action": "wait"})) == END

    def test_missing_next_action_defaults_to_end(self) -> None:
        from langgraph.graph import END

        assert _route_after_confirmation(cast(MovieFinderState, {})) == END

    def test_none_next_action_defaults_to_end(self) -> None:
        from langgraph.graph import END

        assert _route_after_confirmation(cast(MovieFinderState, {"next_action": None})) == END


# ===========================================================================
# compile_graph
# ===========================================================================


class TestCompileGraph:
    def test_returns_compiled_graph(self) -> None:
        graph = compile_graph()
        # Duck-type: any compiled LangGraph exposes these methods
        assert callable(getattr(graph, "ainvoke", None))
        assert callable(getattr(graph, "astream", None))

    def test_compiled_graph_has_invoke(self) -> None:
        graph = compile_graph()
        assert hasattr(graph, "ainvoke")
        assert hasattr(graph, "astream")

    def test_custom_checkpointer_accepted(self) -> None:
        graph = compile_graph(checkpointer=MemorySaver())
        assert callable(getattr(graph, "ainvoke", None))

    def test_graph_nodes_are_registered(self) -> None:
        """The compiled graph knows about all expected nodes."""
        graph = compile_graph()
        node_names = set(graph.get_graph().nodes.keys())
        expected = {
            "rag_search",
            "imdb_enrichment",
            "validation",
            "presentation",
            "confirmation",
            "refinement",
            "qa_agent",
            "dead_end",
            "__start__",
            "__end__",
        }
        assert expected.issubset(node_names)


class TestSetupTracingEnv:
    def test_apply_langsmith_env_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from chain.graph import _apply_langsmith_env

        # Unset just in case
        for k in [
            "LANGSMITH_TRACING",
            "LANGSMITH_PROJECT",
            "LANGSMITH_API_KEY",
            "LANGSMITH_ENDPOINT",
        ]:
            monkeypatch.delenv(k, raising=False)

        config = MagicMock()
        config.langsmith_tracing = True
        config.langsmith_project = "test-project"
        config.langsmith_api_key = "test-key"
        config.langsmith_endpoint = "http://test"

        with patch("chain.config.get_config", return_value=config):
            _apply_langsmith_env()

        assert os.environ["LANGSMITH_TRACING"] == "true"
        assert os.environ["LANGSMITH_PROJECT"] == "test-project"
        assert os.environ["LANGSMITH_API_KEY"] == "test-key"

    def test_apply_langsmith_env_enabled_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from chain.graph import _apply_langsmith_env

        # Unset just in case
        for k in [
            "LANGSMITH_TRACING",
            "LANGSMITH_PROJECT",
            "LANGSMITH_API_KEY",
            "LANGSMITH_ENDPOINT",
        ]:
            monkeypatch.delenv(k, raising=False)

        config = MagicMock()
        config.langsmith_tracing = True
        config.langsmith_project = "test-project"
        config.langsmith_api_key = None
        config.langsmith_endpoint = "http://test"

        with patch("chain.config.get_config", return_value=config):
            _apply_langsmith_env()

        assert os.environ["LANGSMITH_TRACING"] == "true"
        assert "LANGSMITH_API_KEY" not in os.environ

    def test_apply_langsmith_env_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from chain.config import ChainConfig
        from chain.graph import _apply_langsmith_env

        monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
        config = ChainConfig(langsmith_tracing=False)

        with patch("chain.config.get_config", return_value=config):
            _apply_langsmith_env()

        assert "LANGSMITH_TRACING" not in os.environ


class TestLazyImport:
    def test_load_async_postgres_saver_success(self) -> None:
        from chain.graph import _load_async_postgres_saver

        mock_module = MagicMock()
        mock_module.AsyncPostgresSaver = "mocked_saver"

        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres.aio": mock_module}):
            saver = _load_async_postgres_saver()
            assert saver == "mocked_saver"

    def test_load_async_postgres_saver_missing(self) -> None:
        from chain.graph import _load_async_postgres_saver

        orig_import = __import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if "langgraph.checkpoint.postgres" in name:
                raise ImportError("mocked import error")
            return orig_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(
                RuntimeError,
                match="Persistent checkpointing requires `langgraph-checkpoint-postgres`",
            ),
        ):
            _load_async_postgres_saver()


class TestCheckpointLifespan:
    @pytest.mark.asyncio
    async def test_defaults_to_memory_saver_without_database_url(self) -> None:
        async with checkpoint_lifespan() as checkpointer:
            assert isinstance(checkpointer, MemorySaver)

    @pytest.mark.asyncio
    async def test_uses_async_postgres_saver_when_database_url_is_configured(self) -> None:
        mock_checkpointer = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_checkpointer
        mock_context_manager.__aexit__.return_value = False

        mock_async_postgres_saver = MagicMock()
        mock_async_postgres_saver.from_conn_string.return_value = mock_context_manager

        with (
            patch("chain.graph._load_async_postgres_saver", return_value=mock_async_postgres_saver),
            patch("chain.config.get_config", return_value=MagicMock(database_url="postgres://db")),
        ):
            async with checkpoint_lifespan() as checkpointer:
                assert checkpointer is mock_checkpointer

        mock_async_postgres_saver.from_conn_string.assert_called_once_with("postgres://db")
        mock_checkpointer.setup.assert_awaited_once()
