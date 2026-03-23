"""Refinement node.

When the user says the movie is not in the candidate pool, this node uses an
LLM to analyse the entire conversation and build a richer, more targeted query
for the next RAG search iteration.  It also writes a short AI message so the
user knows we are trying again.

It does NOT ask the user new questions — it extracts details already provided
in the conversation.  This keeps the loop tight: refinement → rag_search →
presentation all happen within the same graph invocation.
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
    """Build a richer query from conversation history and update the state."""
    cfg = get_config()
    messages: list[BaseMessage] = state.get("messages", [])
    original_query: str = state.get("user_plot_query", "")
    refinement_count: int = state.get("refinement_count", 0)

    logger.info(
        f"Refining search (attempt {refinement_count + 1}/{cfg.max_refinements}) | original query: {original_query[:100]!r}"
    )

    conversation_history = _format_conversation(messages)

    prompt_text = _load_prompt().format(
        conversation_history=conversation_history,
        original_query=original_query,
    )

    llm = ChatAnthropic(
        model_name=cfg.reasoning_model,
        api_key=SecretStr(cfg.anthropic_api_key),
    ).with_structured_output(RefinementPlan)

    try:
        plan = cast(
            RefinementPlan,
            await llm.ainvoke([HumanMessage(content=prompt_text)]),
        )
    except Exception as exc:
        logger.error(f"Refinement LLM failed: {exc}")
        # Fall back to the original query — at least we won't crash
        plan = RefinementPlan(
            refined_query=original_query,
            message_to_user="Let me search again with what we have so far…",
        )

    logger.info(f"Refined query: {original_query[:80]!r} → {plan.refined_query[:80]!r}")
    logger.debug(f"Message to user: {plan.message_to_user!r}")

    return {
        "user_plot_query": plan.refined_query,
        "refinement_count": refinement_count + 1,
        "messages": [AIMessage(content=plan.message_to_user)],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_conversation(messages: list[BaseMessage]) -> str:
    lines = []
    for msg in messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _load_prompt() -> str:
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
