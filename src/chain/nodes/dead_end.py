"""Dead-end node.

Executes when the maximum number of refinements has been reached without
finding the movie the user is looking for.  Writes a final apologetic
message and marks the action as finished.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def dead_end_node(state: MovieFinderState) -> dict[str, Any]:
    """Inform the user that the search is exhausted.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with a final AIMessage.
    """
    logger.info("Search exhausted — presenting dead end message")

    msg = (
        "I'm sorry, I couldn't find the exact movie you're looking for after "
        "several attempts. You might want to try again with different details, "
        "or start a fresh search!"
    )

    return {
        "messages": [AIMessage(content=msg)],
    }
