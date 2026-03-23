"""LangGraph graph definition for the Movie Finder pipeline.

## Event-driven design

The graph is stateless between invocations — all state is persisted by the
checkpointer (MemorySaver by default, swappable for a Redis/Postgres saver).
Every user message triggers a new ``graph.ainvoke()`` call with the same
``thread_id``; the graph reads ``state["phase"]`` to decide which branch to run.

## Phase lifecycle

```
phase="discovery"    (default)
  START → rag_search → imdb_enrichment → validation → presentation → END
  (state["phase"] is now "confirmation")

phase="confirmation"
  START → confirmation → <conditional>
    "confirmed"  → qa_agent → END  (phase becomes "qa")
    "refine"     → refinement → rag_search → ... → presentation → END
    "exhausted"  → dead_end  → END
    "wait"       → END            (unclear response; AI asked for clarification)

phase="qa"
  START → qa_agent → END
  (loop on every subsequent user message)
```

## LangSmith

Set the following env vars to enable tracing:

    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
    LANGCHAIN_API_KEY=<your key>
    LANGCHAIN_PROJECT=movie-finder

LangChain/LangGraph picks these up automatically on import.

## FastAPI integration (future)

    graph = compile_graph()

    @app.post("/chat/{session_id}")
    async def chat(session_id: str, body: ChatRequest):
        config = {"configurable": {"thread_id": session_id}}
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=body.message)]},
            config=config,
        )
        last_ai = next(
            (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None
        )
        return {"reply": last_ai.content if last_ai else ""}
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.graph import CompiledGraph

from chain.nodes.confirmation import confirmation_node
from chain.nodes.dead_end import dead_end_node
from chain.nodes.imdb_enrichment import imdb_enrichment_node
from chain.nodes.presentation import presentation_node
from chain.nodes.qa_agent import qa_agent_node
from chain.nodes.rag_search import rag_search_node
from chain.nodes.refinement import refinement_node
from chain.nodes.validation import validation_node
from chain.state import MovieFinderState

# ---------------------------------------------------------------------------
# Routing functions (pure — no side effects)
# ---------------------------------------------------------------------------


def _route_by_phase(
    state: MovieFinderState,
) -> Literal["rag_search", "confirmation", "qa_agent"]:
    """Entry router: pick the first node to execute based on current phase."""
    phase = state.get("phase") or "discovery"
    if phase == "confirmation":
        return "confirmation"
    if phase == "qa":
        return "qa_agent"
    return "rag_search"  # "discovery" or anything unrecognised


def _route_after_confirmation(
    state: MovieFinderState,
) -> Literal["qa_agent", "refinement", "dead_end", "__end__"]:
    """Post-confirmation router: where to go based on next_action."""
    action = state.get("next_action") or "wait"
    if action == "confirmed":
        return "qa_agent"
    if action == "refine":
        return "refinement"
    if action == "exhausted":
        return "dead_end"
    return "__end__"  # END == "__end__"; return the literal so mypy can verify the Literal type


# ---------------------------------------------------------------------------
# LangSmith observability helper
# ---------------------------------------------------------------------------


def _apply_langsmith_env() -> None:
    """Propagate LangSmith config from ChainConfig into os.environ.

    LangChain reads these env vars directly — pydantic-settings loading them
    into the config object is not enough.  This ensures tracing works even
    when the package is imported without a prior load_dotenv() call.

    Only sets vars that are not already present in the environment (so an
    explicit shell export always takes precedence).
    """
    from chain.config import get_config  # local import to avoid circular dependency

    cfg = get_config()
    if not cfg.langsmith_tracing:
        return

    vars_to_set = {
        "LANGCHAIN_TRACING_V2": "true",
        "LANGSMITH_TRACING": "true",
        "LANGCHAIN_ENDPOINT": cfg.langsmith_endpoint,
        "LANGSMITH_ENDPOINT": cfg.langsmith_endpoint,
        "LANGCHAIN_PROJECT": cfg.langsmith_project,
        "LANGSMITH_PROJECT": cfg.langsmith_project,
    }
    if cfg.langsmith_api_key:
        vars_to_set["LANGCHAIN_API_KEY"] = cfg.langsmith_api_key
        vars_to_set["LANGSMITH_API_KEY"] = cfg.langsmith_api_key

    for key, value in vars_to_set.items():
        os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def compile_graph(checkpointer: BaseCheckpointSaver[Any] | None = None) -> CompiledGraph:
    """Build and compile the Movie Finder LangGraph graph.

    Parameters
    ----------
    checkpointer:
        A LangGraph ``BaseCheckpointSaver`` instance for multi-turn memory.
        Defaults to an in-memory ``MemorySaver``.  For production, pass a
        Redis- or Postgres-backed saver.

    Returns
    -------
    CompiledGraph
        Ready for ``.ainvoke()`` / ``.astream()``.

    Example
    -------
    ::

        graph = compile_graph()
        config = {"configurable": {"thread_id": "session-abc"}}

        # First turn — discovery
        await graph.ainvoke(
            {"messages": [HumanMessage("A heist movie where they steal dreams")]},
            config=config,
        )

        # Second turn — user confirms
        await graph.ainvoke(
            {"messages": [HumanMessage("Yes! It's number 1")]},
            config=config,
        )

        # Third turn — Q&A
        await graph.ainvoke(
            {"messages": [HumanMessage("Is it safe for a 12-year-old?")]},
            config=config,
        )
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    _apply_langsmith_env()

    builder = StateGraph(MovieFinderState)

    # ------------------------------------------------------------------ #
    # Nodes
    # ------------------------------------------------------------------ #
    builder.add_node("rag_search", rag_search_node)
    builder.add_node("imdb_enrichment", imdb_enrichment_node)
    builder.add_node("validation", validation_node)
    builder.add_node("presentation", presentation_node)
    builder.add_node("confirmation", confirmation_node)
    builder.add_node("refinement", refinement_node)
    builder.add_node("qa_agent", qa_agent_node)
    builder.add_node("dead_end", dead_end_node)

    # ------------------------------------------------------------------ #
    # Edges
    # ------------------------------------------------------------------ #

    # Entry: route by phase
    builder.add_conditional_edges(
        START,
        _route_by_phase,
        {
            "rag_search": "rag_search",
            "confirmation": "confirmation",
            "qa_agent": "qa_agent",
        },
    )

    # Discovery pipeline (linear)
    builder.add_edge("rag_search", "imdb_enrichment")
    builder.add_edge("imdb_enrichment", "validation")
    builder.add_edge("validation", "presentation")
    builder.add_edge("presentation", END)

    # Confirmation routing
    builder.add_conditional_edges(
        "confirmation",
        _route_after_confirmation,
        {
            "qa_agent": "qa_agent",
            "refinement": "refinement",
            "dead_end": "dead_end",
            END: END,
        },
    )

    # Refinement loops back into the discovery pipeline
    builder.add_edge("refinement", "rag_search")

    # Q&A and dead-end terminate
    builder.add_edge("qa_agent", END)
    builder.add_edge("dead_end", END)

    return builder.compile(checkpointer=checkpointer)
