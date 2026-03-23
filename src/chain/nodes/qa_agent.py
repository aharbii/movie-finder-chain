"""Q&A agent node.

After the user has confirmed their movie, this node handles all follow-up
questions using the existing imdbapi LangGraph ReAct agent (create_movie_agent).

The confirmed movie is injected into the agent's system prompt so the agent
knows the target title and its IMDb ID upfront — no need for the user to
repeat the title in every question.

The agent runs to completion (tool calls + final answer) within a single node
execution.  The main graph's checkpointer persists the full conversation
history; the Q&A agent sub-graph is stateless (no checkpointer) and simply
processes the current message batch.
"""

from __future__ import annotations

import importlib.resources
from typing import Any

from imdbapi import IMDBAPIClient
from imdbapi.langchain.agent import MOVIE_AGENT_SYSTEM_PROMPT
from imdbapi.langchain.tools import create_imdb_tools
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import SecretStr

from chain.config import get_config
from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def qa_agent_node(state: MovieFinderState) -> dict[str, Any]:
    """Run the IMDb ReAct agent on the current conversation messages."""
    cfg = get_config()
    confirmed: dict[str, Any] = state.get("confirmed_movie_data") or {}
    messages: list[BaseMessage] = state.get("messages", [])

    confirmed_title: str = confirmed.get("imdb_title") or confirmed.get("rag_title") or "Unknown"
    confirmed_id: str = confirmed.get("imdb_id") or "—"

    # Log the user's question
    user_question = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    logger.info(
        f"Q&A | movie: {confirmed_title} ({confirmed_id}) | user: {str(user_question)[:200]!r}"
    )

    system_prompt = _build_system_prompt(confirmed)

    llm = ChatAnthropic(
        model_name=cfg.reasoning_model,
        api_key=SecretStr(cfg.anthropic_api_key),
    )

    # Anthropic requires the conversation to end with a HumanMessage.
    # The confirmation node appends an AIMessage before routing here, so trim it.
    last_human_idx = max(
        (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)),
        default=len(messages) - 1,
    )
    messages_for_agent = messages[: last_human_idx + 1]

    async with IMDBAPIClient() as client:
        tools = create_imdb_tools(client)
        # No checkpointer here — state is managed by the outer graph
        agent = create_agent(llm, tools, system_prompt=system_prompt)

        result = await agent.ainvoke({"messages": messages_for_agent})

    # Extract only the messages that the agent added (everything beyond input)
    new_messages: list[BaseMessage] = result["messages"][len(messages_for_agent) :]

    _log_agent_turn(new_messages, confirmed_title)

    return {
        "messages": new_messages,
        "phase": "qa",
        "next_action": "wait",
    }


def _log_agent_turn(messages: list[BaseMessage], movie_title: str) -> None:
    """Log tool calls, tool results, and the final agent response for a Q&A turn."""
    tool_call_count = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_call_count += 1
                args_preview = _truncate(str(tc.get("args", {})), 300)
                logger.debug(
                    f"→ TOOL CALL  [{movie_title}] | tool={tc.get('name', '?')} | args={args_preview}"
                )
        elif isinstance(msg, ToolMessage):
            content_preview = _truncate(str(msg.content), 400)
            logger.debug(
                f"← TOOL RESULT [{movie_title}] | tool={msg.name or '?'} | {content_preview}"
            )
        elif isinstance(msg, AIMessage):
            # Final agent response (no tool calls)
            response_preview = _truncate(str(msg.content), 500)
            logger.info(f"← AGENT [{movie_title}] | {response_preview}")

    if tool_call_count:
        logger.info(f"Agent used {tool_call_count} tool call(s) to answer about '{movie_title}'")


def _truncate(text: str, max_len: int) -> str:
    """Truncate long strings for log readability."""
    return text if len(text) <= max_len else text[:max_len] + " …"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_system_prompt(confirmed: dict[str, Any]) -> str:
    """Combine the base IMDb agent prompt with confirmed-movie context."""
    imdb_id = confirmed.get("imdb_id", "unknown")
    imdb_title = confirmed.get("imdb_title") or confirmed.get("rag_title", "Unknown")
    imdb_year = confirmed.get("imdb_year") or confirmed.get("rag_year", "?")
    imdb_rating = confirmed.get("imdb_rating", "N/A")
    directors = ", ".join(confirmed.get("imdb_directors", [])[:3]) or "unknown"
    stars = ", ".join(confirmed.get("imdb_stars", [])[:5]) or "unknown"
    genres = ", ".join(confirmed.get("imdb_genres", [])[:5]) or "unknown"
    plot = confirmed.get("imdb_plot", "")

    try:
        context_template = (
            importlib.resources.files("chain.prompts")
            .joinpath("qa_context.md")
            .read_text(encoding="utf-8")
        )
        context = context_template.format(
            imdb_id=imdb_id,
            imdb_title=imdb_title,
            imdb_year=imdb_year,
            imdb_rating=imdb_rating,
            directors=directors,
            stars=stars,
            genres=genres,
            imdb_plot=plot or "Not available",
        )
    except Exception:
        context = (
            f"\n\n## Confirmed Movie\n"
            f"**{imdb_title}** ({imdb_year}) — IMDb ID: {imdb_id}\n"
            f"Directors: {directors} | Stars: {stars} | Genres: {genres}\n"
            f"When using IMDb tools, the title ID is **{imdb_id}**."
        )

    return str(MOVIE_AGENT_SYSTEM_PROMPT + "\n\n" + context)
