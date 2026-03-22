"""Tests for graph compilation and routing logic.

Routing functions (_route_by_phase, _route_after_confirmation) are pure —
tested without mocks.

Graph compilation is tested to verify the graph builds without error and
the compiled object exposes the expected interface.
"""

from __future__ import annotations

from chain.graph import _route_after_confirmation, _route_by_phase, compile_graph

# ===========================================================================
# _route_by_phase  (pure function — no external deps)
# ===========================================================================


class TestRouteByPhase:
    def test_default_routes_to_rag_search(self) -> None:
        assert _route_by_phase({}) == "rag_search"

    def test_discovery_routes_to_rag_search(self) -> None:
        assert _route_by_phase({"phase": "discovery"}) == "rag_search"

    def test_confirmation_routes_to_confirmation(self) -> None:
        assert _route_by_phase({"phase": "confirmation"}) == "confirmation"

    def test_qa_routes_to_qa_agent(self) -> None:
        assert _route_by_phase({"phase": "qa"}) == "qa_agent"

    def test_unknown_phase_falls_back_to_rag_search(self) -> None:
        assert _route_by_phase({"phase": "unknown_gibberish"}) == "rag_search"

    def test_none_phase_routes_to_rag_search(self) -> None:
        assert _route_by_phase({"phase": None}) == "rag_search"  # type: ignore[typeddict-item]


# ===========================================================================
# _route_after_confirmation  (pure function — no external deps)
# ===========================================================================


class TestRouteAfterConfirmation:
    def test_confirmed_routes_to_qa_agent(self) -> None:
        assert _route_after_confirmation({"next_action": "confirmed"}) == "qa_agent"

    def test_refine_routes_to_refinement(self) -> None:
        assert _route_after_confirmation({"next_action": "refine"}) == "refinement"

    def test_exhausted_routes_to_dead_end(self) -> None:
        assert _route_after_confirmation({"next_action": "exhausted"}) == "dead_end"

    def test_wait_routes_to_end(self) -> None:
        from langgraph.graph import END

        assert _route_after_confirmation({"next_action": "wait"}) == END

    def test_missing_next_action_defaults_to_end(self) -> None:
        from langgraph.graph import END

        assert _route_after_confirmation({}) == END

    def test_none_next_action_defaults_to_end(self) -> None:
        from langgraph.graph import END

        assert _route_after_confirmation({"next_action": None}) == END  # type: ignore[typeddict-item]


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
        from langgraph.checkpoint.memory import MemorySaver

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
