"""Refinement node.

When the user says the movie is not in the candidate pool, this node uses an
LLM to analyse the entire conversation and build a richer, more targeted query
for the next RAG search iteration.  It also writes a helpful AI message
to the conversation history.
"""

from __future__ import annotations

import importlib.resources
from typing import Any, cast

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import SecretStr

from chain.config import get_config
from chain.models.output import RefinementPlan
from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def refinement_node(state: MovieFinderState) -> dict[str, Any]:
    """Analyse history and build a better RAG query.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with user_plot_query, messages, and refinement_count.
    """
    cfg = get_config()
    messages: list[BaseMessage] = state.get("messages", [])
    original_query: str = state.get("user_plot_query") or ""
    refinement_count: int = state.get("refinement_count", 0)

    # Load and fill the prompt template
    history_str = _format_history(messages)
    prompt_text = _load_prompt().format(
        conversation_history=history_str,
        original_query=original_query,
    )

    llm = ChatAnthropic(
        model_name=cfg.classifier_model,
        api_key=SecretStr(cfg.anthropic_api_key),
    ).with_structured_output(RefinementPlan)

    try:
        result = cast(RefinementPlan, await llm.ainvoke([HumanMessage(content=prompt_text)]))
        refined_query = result.refined_query
        ai_message = result.message_to_user
    except Exception as exc:
        logger.error(f"Refinement node failed: {exc}")
        refined_query = original_query
        ai_message = "I'll try searching again with those extra details."

    logger.info(f"Refined query: {refined_query[:100]!r}")

    return {
        "user_plot_query": refined_query,
        "messages": [AIMessage(content=ai_message)],
        "refinement_count": refinement_count + 1,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_history(messages: list[BaseMessage]) -> str:
    """Convert message history to a plain string for the prompt.

    Args:
        messages: The list of conversation messages.

    Returns:
        Formatted history string.
    """
    lines = []
    for m in messages:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        content = m.content if isinstance(m.content, str) else str(m.content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _load_prompt() -> str:
    """Load the refinement prompt template.

    Returns:
        The prompt template string.
    """
    try:
        return (
            importlib.resources.files("chain.prompts")
            .joinpath("refinement.md")
            .read_text(encoding="utf-8")
        )
    except Exception:
        return (
            "Conversation:\n{conversation_history}\n\n"
            'Original query: "{original_query}"\n'
            "Build a richer refined query and a short user message."
        )
