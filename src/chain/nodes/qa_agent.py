"""Q&A agent node.

After the user has confirmed their movie, this node handles all follow-up
questions using the existing imdbapi LangGraph ReAct agent (create_movie_agent).

The confirmed movie is injected into every agent invocation as a rich
context block prepended to the user's question.  This anchors the ReAct
agent to the correct title even though ``create_movie_agent`` does not
expose a runtime ``system_prompt`` override.
"""

from __future__ import annotations

from typing import Any

from imdbapi import IMDBAPIClient
from imdbapi.langchain.agent import create_movie_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from chain.state import MovieFinderState
from chain.utils.llm_factory import get_reasoning_llm
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def qa_agent_node(state: MovieFinderState) -> dict[str, Any]:
    """Execute the ReAct agent for follow-up Q&A.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with the agent's response messages and updated phase.
    """
    confirmed: dict[str, Any] = state.get("confirmed_movie_data") or {}
    messages: list[BaseMessage] = state.get("messages", [])

    if not confirmed:
        logger.warning("qa_agent_node: no confirmed movie data — routing to discovery")
        return {"phase": "discovery"}

    async with IMDBAPIClient() as client:
        agent = create_movie_agent(
            client,
            llm=get_reasoning_llm(),
        )

        # Build a copy of the last user message with rich movie context prepended.
        # We must NOT mutate the original message object in the graph state.
        last_user_msg = _last_human_message(messages)
        context_block = _build_system_prompt(confirmed)
        augmented_msg = HumanMessage(content=f"{context_block}\n\n---\n\n{last_user_msg.content}")

        logger.info(f"Executing Q&A agent for movie: {confirmed.get('imdb_title')}")

        try:
            result = await agent.ainvoke({"messages": [augmented_msg]})
            new_messages = result.get("messages", [])
        except Exception as exc:
            logger.error(f"Q&A agent failed: {exc}")
            new_messages = [
                AIMessage(content="I'm sorry, I encountered an error while looking that up.")
            ]

    # Log tool usage if any
    for msg in new_messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                movie_title = confirmed.get("imdb_title") or confirmed.get("rag_title")
                args_preview = _truncate(str(tc.get("args", {})), 300)
                logger.debug(
                    f"→ TOOL CALL  [{movie_title}] | tool={tc.get('name', '?')} | args={args_preview}"
                )

    return {
        "messages": new_messages,
        "phase": "qa",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_system_prompt(confirmed: dict[str, Any]) -> str:
    """Build a rich movie-context block to inject into the agent's input.

    All fields are drawn from the enriched IMDb record stored in
    ``confirmed_movie_data``.  Missing fields are silently omitted so
    partial enrichment results still yield a useful context block.

    Args:
        confirmed: The confirmed movie data dict from state.

    Returns:
        A formatted multi-line context string ready to prepend to the
        user's question.
    """
    title = confirmed.get("imdb_title") or confirmed.get("rag_title", "unknown")
    imdb_id = confirmed.get("imdb_id", "unknown")

    lines: list[str] = [
        "[Confirmed movie context — use this to answer the user's question]",
        f"- IMDb ID: {imdb_id}",
        f"- Title: {title}",
    ]

    if year := confirmed.get("imdb_year"):
        lines.append(f"- Year: {year}")
    if rating := confirmed.get("imdb_rating"):
        lines.append(f"- IMDb rating: {rating}")
    if directors := confirmed.get("imdb_directors"):
        directors_str = ", ".join(directors) if isinstance(directors, list) else str(directors)
        lines.append(f"- Directors: {directors_str}")
    if stars := confirmed.get("imdb_stars"):
        stars_str = ", ".join(stars) if isinstance(stars, list) else str(stars)
        lines.append(f"- Stars: {stars_str}")
    if genres := confirmed.get("imdb_genres"):
        genres_str = ", ".join(genres) if isinstance(genres, list) else str(genres)
        lines.append(f"- Genres: {genres_str}")
    if plot := confirmed.get("imdb_plot"):
        lines.append(f"- Plot: {plot}")

    lines.append(
        "\nWhen using tools, always reference the IMDb ID above to select the correct title."
    )
    return "\n".join(lines)


def _last_human_message(messages: list[BaseMessage]) -> HumanMessage:
    """Find the latest user message in the conversation history.

    Args:
        messages: The list of conversation messages.

    Returns:
        The last HumanMessage, or an empty HumanMessage if none found.
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return HumanMessage(content="")


def _truncate(text: str, length: int) -> str:
    """Truncate a string for logging.

    Args:
        text: The string to truncate.
        length: Maximum length.

    Returns:
        Truncated string with '..' suffix if truncated.
    """
    return (text[:length] + "..") if len(text) > length else text
