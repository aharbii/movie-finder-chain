"""RAG search node.

Reads the user's plot query from the last HumanMessage (or from
``state["user_plot_query"]`` when the refinement node has already set an
improved query), embeds it, and retrieves the top-k candidates from Qdrant.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from chain.config import get_config
from chain.rag.service import MovieSearchService
from chain.state import MovieFinderState

logger = logging.getLogger(__name__)


async def rag_search_node(state: MovieFinderState, config: RunnableConfig) -> dict[str, Any]:
    """Embed the current plot query and fetch candidates from Qdrant."""
    cfg = get_config()

    # Prefer an explicitly-set refined query (set by refinement_node).
    # Fall back to the last human message in the conversation.
    query: str = state.get("user_plot_query", "")
    if not query:
        query = _last_human_text(state.get("messages", []))

    if not query:
        logger.warning("rag_search_node called with no query — returning empty candidates")
        return {"rag_candidates": [], "user_plot_query": ""}

    logger.info("RAG search query: '%s...'", query[:80])

    service = MovieSearchService(cfg)
    candidates = await asyncio.to_thread(service.search, query, cfg.rag_top_k)

    return {
        "user_plot_query": query,
        "rag_candidates": [c.model_dump() for c in candidates],
    }


def _last_human_text(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and isinstance(msg.content, str):
            return msg.content
    return ""
