"""LangGraph state definition for the Movie Finder pipeline.

The graph is event-driven: every user message triggers a new `graph.ainvoke()`
call (same thread_id). The `phase` field drives which branch executes.

Phase lifecycle
---------------
"discovery"    → initial state; RAG search + IMDB enrichment runs.
"confirmation" → candidates have been presented; waiting for user to confirm.
"qa"           → movie is confirmed; open-ended Q&A loop with IMDB agent.

next_action (set by confirmation_node, read by the confirmation router)
---------------------------------------------------------------------------
"wait"        → response was unclear; re-present or ask for clarification.
"confirmed"   → user identified their movie; move to Q&A.
"refine"      → user said the movie isn't there; run another RAG search.
"exhausted"   → max refinements reached; inform user and end.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class MovieFinderState(TypedDict, total=False):
    """Complete mutable state for the Movie Finder LangGraph graph.

    All fields default to falsy values so nodes only need to return the
    keys they actually changed.
    """

    # ------------------------------------------------------------------ #
    # Conversation history — uses add_messages reducer (append-only)
    # ------------------------------------------------------------------ #
    messages: Annotated[list[BaseMessage], add_messages]

    # ------------------------------------------------------------------ #
    # Phase and routing control
    # ------------------------------------------------------------------ #
    phase: str  # "discovery" | "confirmation" | "qa"
    next_action: str  # "wait" | "confirmed" | "refine" | "exhausted"
    refinement_count: int

    # ------------------------------------------------------------------ #
    # RAG discovery
    # ------------------------------------------------------------------ #
    user_plot_query: str  # current plot description used for RAG
    rag_candidates: list[dict]  # raw Movie dicts from Qdrant

    # ------------------------------------------------------------------ #
    # IMDB enrichment + validation
    # ------------------------------------------------------------------ #
    enriched_movies: list[dict]  # RAG + IMDB merged, sorted by confidence

    # ------------------------------------------------------------------ #
    # Confirmed movie (set after user confirms)
    # ------------------------------------------------------------------ #
    confirmed_movie_id: str | None  # IMDb title ID, e.g. "tt1375666"
    confirmed_movie_title: str | None  # Human-readable title
    confirmed_movie_data: dict | None  # Full enriched record for Q&A context
