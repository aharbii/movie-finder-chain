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
import logging

from imdbapi import IMDBAPIClient  # type: ignore[attr-defined]
from imdbapi.langchain.agent import MOVIE_AGENT_SYSTEM_PROMPT
from imdbapi.langchain.tools import create_imdb_tools
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage
from langgraph.prebuilt import create_react_agent

from chain.config import get_config
from chain.state import MovieFinderState

logger = logging.getLogger(__name__)


async def qa_agent_node(state: MovieFinderState) -> dict:
    """Run the IMDb ReAct agent on the current conversation messages."""
    cfg = get_config()
    confirmed: dict = state.get("confirmed_movie_data") or {}
    messages: list[BaseMessage] = state.get("messages", [])

    system_prompt = _build_system_prompt(confirmed)

    llm = ChatAnthropic(
        model=cfg.reasoning_model,
        api_key=cfg.anthropic_api_key,
    )

    async with IMDBAPIClient() as client:
        tools = create_imdb_tools(client)
        # No checkpointer here — state is managed by the outer graph
        agent = create_react_agent(llm, tools, state_modifier=system_prompt)

        result = await agent.ainvoke(
            {"messages": messages},
            config={"configurable": {}},
        )

    # Extract only the messages that the agent added (everything beyond input)
    new_messages: list[BaseMessage] = result["messages"][len(messages) :]

    logger.info(
        "Q&A agent produced %d new message(s) for '%s'",
        len(new_messages),
        confirmed.get("imdb_title", "?"),
    )

    return {
        "messages": new_messages,
        "phase": "qa",
        "next_action": "wait",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_system_prompt(confirmed: dict) -> str:
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
