"""Dead-end node.

Reached when max refinement cycles are exhausted without finding a match.
Informs the user and suggests concrete ways to improve their search.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from chain.config import get_config
from chain.state import MovieFinderState


def dead_end_node(state: MovieFinderState) -> dict[str, Any]:
    """Return a graceful dead-end message to the user."""
    cfg = get_config()

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
