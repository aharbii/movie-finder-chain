"""LangGraph state definition for the Movie Finder pipeline.

The graph is event-driven: every user message triggers a new `graph.ainvoke()`
call (same thread_id). The `phase` field drives which branch executes.

Phase lifecycle:
    discovery -> confirmation -> qa
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage


class MovieFinderState(TypedDict):
    """The complete state schema for the Movie Finder LangGraph.

    Attributes:
        messages: Conversation history (Human/AI/Tool messages).
            Annotated with `add` so new updates are appended, not overwritten.
        phase: Current pipeline stage. Controls the entry router.
        next_action: Set by the confirmation node to drive routing.
        user_plot_query: The current refined plot description.
        refinement_count: How many times we've looped back to search.
        rag_candidates: Raw hits from the vector store.
        enriched_movies: RAG hits augmented with IMDb metadata and confidence.
        confirmed_movie_id: IMDb title ID of the final selection.
        confirmed_movie_title: Human-readable title of the selection.
        confirmed_movie_data: Full record for Q&A context injection.
    """

    # --- Conversation history ---
    # `add` ensures new messages are appended to existing ones.
    messages: Annotated[list[BaseMessage], add]

    # --- State machine control ---
    phase: NotRequired[Literal["discovery", "confirmation", "qa"]]
    next_action: NotRequired[Literal["confirmed", "refine", "exhausted", "wait"] | None]

    # --- Discovery pipeline data ---
    user_plot_query: NotRequired[str | None]
    refinement_count: NotRequired[int]
    rag_candidates: NotRequired[list[dict[str, Any]]]
    enriched_movies: NotRequired[list[dict[str, Any]]]

    # --- Confirmation / Q&A data ---
    confirmed_movie_id: NotRequired[str | None]  # IMDb title ID, e.g. "tt1375666"
    confirmed_movie_title: NotRequired[str | None]  # Human-readable title
    confirmed_movie_data: NotRequired[dict[str, Any] | None]  # Full enriched record for Q&A context
