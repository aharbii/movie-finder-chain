"""Q&A agent node.

After the user has confirmed their movie, this node handles all follow-up
questions using the existing imdbapi LangGraph ReAct agent (create_movie_agent).

The confirmed movie is injected into the agent's system prompt as static
context, ensuring the LLM "stays" on the correct movie even when using
external tools.
"""

from __future__ import annotations

from typing import Any

from imdbapi import IMDBAPIClient
from imdbapi.langchain.agent import create_movie_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import SecretStr

from chain.config import get_config
from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)

MOVIE_AGENT_SYSTEM_PROMPT = (
    "You are a movie expert assistant. The user has already identified "
    "their movie. Your job is to answer follow-up questions about it.\n\n"
    "Use the provided IMDb Title ID with your tools to get accurate, "
    "up-to-date data. If a tool returns a list of results, pick the one "
    "that matches the Title ID provided in your context."
)


async def qa_agent_node(state: MovieFinderState) -> dict[str, Any]:
    """Execute the ReAct agent for follow-up Q&A.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with the agent's response messages and updated phase.
    """
    cfg = get_config()
    confirmed: dict[str, Any] = state.get("confirmed_movie_data") or {}
    messages: list[BaseMessage] = state.get("messages", [])

    if not confirmed:
        logger.warning("qa_agent_node: no confirmed movie data — routing to discovery")
        return {"phase": "discovery"}

    # Use the reasoning model from config (Sonnet)
    llm = ChatAnthropic(
        model_name=cfg.reasoning_model,
        api_key=SecretStr(cfg.anthropic_api_key),
    )

    async with IMDBAPIClient() as client:
        # Create agent with explicit client and custom LLM/prompt
        agent = create_movie_agent(
            client,
            llm=llm,
        )

        last_user_msg = _last_human_message(messages)
        # Augment the last message with context if not already there
        context_prefix = (
            f"[Context: User confirmed movie {confirmed.get('imdb_id')} "
            f"({confirmed.get('imdb_title')})]\n\n"
        )
        last_user_msg.content = context_prefix + str(last_user_msg.content)

        logger.info(f"Executing Q&A agent for movie: {confirmed.get('imdb_title')}")

        try:
            result = await agent.ainvoke({"messages": [last_user_msg]})
            new_messages = result.get("messages", [])
        except Exception as exc:
            logger.error(f"Q&A agent failed: {exc}")
            new_messages = [AIMessage(content="I'm sorry, I encountered an error while looking that up.")]

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


def _last_human_message(messages: list[BaseMessage]) -> HumanMessage:
    """Find the latest user message.

    Args:
        messages: The list of conversation messages.

    Returns:
        The last HumanMessage.
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            # Create a copy so we don't mutate the original state
            return HumanMessage(content=msg.content)
    return HumanMessage(content="")


def _truncate(text: str, length: int) -> str:
    """Truncate a string for logging.

    Args:
        text: The string to truncate.
        length: Maximum length.

    Returns:
        Truncated string.
    """
    return (text[:length] + "..") if len(text) > length else text
