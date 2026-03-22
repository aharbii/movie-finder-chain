"""Confirmation node.

Reads the user's latest message and classifies it using a lightweight LLM
(Claude Haiku) with structured output.  Sets ``next_action`` on the state
so the conditional edge after this node can route correctly.

Possible next_action values
---------------------------
``"confirmed"``  → user identified a candidate; sets confirmed_movie_* fields.
``"refine"``     → user says it's not there; refinement_node will re-search.
``"exhausted"``  → max refinement cycles reached; dead_end node will respond.
``"wait"``       → unclear response; AI asks for clarification and waits.
"""

from __future__ import annotations

import importlib.resources
import logging
from typing import Any, cast

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import SecretStr

from chain.config import get_config
from chain.models.output import ConfirmationClassification
from chain.state import MovieFinderState

logger = logging.getLogger(__name__)

_PROMPT_PATH = importlib.resources.files("chain") / "../../prompts/confirmation.md"


async def confirmation_node(state: MovieFinderState) -> dict[str, Any]:
    """Classify the user's confirmation response and route accordingly."""
    cfg = get_config()
    messages: list[BaseMessage] = state.get("messages", [])
    movies: list[dict[str, Any]] = state.get("enriched_movies", [])
    refinement_count: int = state.get("refinement_count", 0)

    user_message = _last_human_text(messages)
    if not user_message:
        return {"next_action": "wait"}

    # Build candidates block for the prompt
    candidates_block = _format_candidates(movies)

    # Load and fill the prompt template
    prompt_text = _load_prompt().format(
        candidates_block=candidates_block,
        user_message=user_message,
    )

    llm = ChatAnthropic(
        model_name=cfg.classifier_model,
        api_key=SecretStr(cfg.anthropic_api_key),
    ).with_structured_output(ConfirmationClassification)

    try:
        result = cast(
            ConfirmationClassification,
            await llm.ainvoke([HumanMessage(content=prompt_text)]),
        )
    except Exception as exc:
        logger.error("Confirmation classifier failed: %s", exc)
        return {
            "messages": [AIMessage(content="I didn't quite catch that. Could you clarify?")],
            "next_action": "wait",
        }

    logger.info(
        "Confirmation decision: %s (idx=%s) | reason: %s",
        result.decision,
        result.movie_index,
        result.reasoning,
    )

    if result.decision == "confirmed" and result.movie_index is not None:
        idx = result.movie_index
        if 0 <= idx < len(movies):
            confirmed = movies[idx]
            return {
                "confirmed_movie_id": confirmed.get("imdb_id"),
                "confirmed_movie_title": confirmed.get("imdb_title") or confirmed.get("rag_title"),
                "confirmed_movie_data": confirmed,
                "next_action": "confirmed",
                "messages": [
                    AIMessage(
                        content=(
                            f"Great! I've confirmed **{confirmed.get('imdb_title') or confirmed.get('rag_title')}**"
                            f" ({confirmed.get('imdb_year') or confirmed.get('rag_year', '')}) as your movie. "
                            "You can now ask me anything about it!"
                        )
                    )
                ],
            }

    if result.decision == "not_found":
        if refinement_count >= cfg.max_refinements:
            return {"next_action": "exhausted"}
        return {"next_action": "refine"}

    # Unclear — ask for clarification
    return {
        "messages": [
            AIMessage(
                content=(
                    "I'm not sure which movie you meant. Could you reply with its number "
                    '(e.g. *"It\'s #2"*), or let me know if none of the options match?'
                )
            )
        ],
        "next_action": "wait",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_human_text(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and isinstance(msg.content, str):
            return msg.content
    return ""


def _format_candidates(movies: list[dict[str, Any]]) -> str:
    if not movies:
        return "(no candidates)"
    lines = []
    for i, m in enumerate(movies, start=1):
        title = m.get("imdb_title") or m.get("rag_title", "?")
        year = m.get("imdb_year") or m.get("rag_year", "?")
        lines.append(f"{i}. {title} ({year})")
    return "\n".join(lines)


def _load_prompt() -> str:
    try:
        return (
            importlib.resources.files("chain.prompts")
            .joinpath("confirmation.md")
            .read_text(encoding="utf-8")
        )
    except Exception:
        return (
            'Candidates:\n{candidates_block}\n\nUser said: "{user_message}"\n'
            "Classify as confirmed/not_found/unclear."
        )
