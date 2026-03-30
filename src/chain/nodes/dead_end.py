"""Dead-end node.

Executes when the maximum number of refinements has been reached without
finding the movie the user is looking for.  Writes a final apologetic
message with actionable tips, then resets the phase so the user can
start a fresh search in the same session.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from chain.config import get_config
from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def dead_end_node(state: MovieFinderState) -> dict[str, Any]:
    """Inform the user that the search is exhausted and reset graph state.

    Resets ``phase``, ``refinement_count``, and ``next_action`` so the
    session is ready for a new search without requiring a full restart.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with a final AIMessage and discovery-phase reset.
    """
    cfg = get_config()
    logger.info(
        f"Dead end reached after {cfg.max_refinements} refinement attempt(s) "
        "— no matching movie found"
    )

    text = (
        f"After {cfg.max_refinements} search attempts, I wasn't able to find your movie "
        f"in the database.\n\n"
        "The film might not be in our current dataset (which focuses on American and British "
        "cinema up to the dataset's cut-off date), or the plot details might need more "
        "specificity.\n\n"
        "**Tips to try in a new search:**\n"
        "- Mention a specific actor or director you remember\n"
        "- Include the approximate decade or year of release\n"
        "- Describe a memorable scene, costume, or quote\n"
        "- Specify the country of origin or language\n\n"
        "Feel free to start a new search whenever you're ready!"
    )

    return {
        "messages": [AIMessage(content=text)],
        "phase": "discovery",
        "refinement_count": 0,
        "next_action": "wait",
    }
