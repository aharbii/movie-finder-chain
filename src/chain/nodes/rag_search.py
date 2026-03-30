"""RAG search node.

Reads the user's plot query from the last HumanMessage (or from
``state["user_plot_query"]`` when the refinement node has already set an
improved query), embeds it, and retrieves the top-k candidates from Qdrant.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from chain.config import get_config
from chain.rag.service import MovieSearchService
from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_search_service() -> MovieSearchService:
    """Return a cached instance of MovieSearchService.

    Returns:
        The MovieSearchService singleton.
    """
    return MovieSearchService(get_config())


async def rag_search_node(state: MovieFinderState, config: RunnableConfig) -> dict[str, Any]:
    """Embed the current plot query and fetch candidates from Qdrant.

    Args:
        state: The current graph state.
        config: The runnable configuration.

    Returns:
        Partial state update with rag_candidates and user_plot_query.
    """
    cfg = get_config()
    refinement_count: int = state.get("refinement_count", 0)

    # Prefer an explicitly-set refined query (set by refinement_node).
    # Fall back to the last human message in the conversation.
    query: str = state.get("user_plot_query") or ""
    if not query:
        query = _last_human_text(state.get("messages", []))

    if not query:
        logger.warning("No query found — returning empty candidates")
        return {"rag_candidates": [], "user_plot_query": ""}

    attempt_label = f"attempt {refinement_count + 1}" if refinement_count else "initial"
    logger.info(f"RAG search [{attempt_label}] | query: {query[:120]!r}")

    service = _get_search_service()
    candidates = await asyncio.to_thread(service.search, query, cfg.rag_top_k)

    if candidates:
        titles = ", ".join(f"{c.title} ({c.release_year or '?'})" for c in candidates[:5])
        logger.debug(
            f"RAG returned {len(candidates)} candidate(s): {titles}{' ...' if len(candidates) > 5 else ''}"
        )
    else:
        logger.warning(f"RAG returned 0 candidates for query: {query[:80]!r}")

    return {
        "user_plot_query": query,
        "rag_candidates": [c.model_dump() for c in candidates],
    }


def _last_human_text(messages: list[BaseMessage]) -> str:
    """Extract the text of the last human message.

    Args:
        messages: The list of conversation messages.

    Returns:
        The content of the last human message, or empty string.
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and isinstance(msg.content, str):
            return msg.content
    return ""
