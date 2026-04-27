"""Confirmation node.

Reads the user's latest message and classifies it using the configured
classifier LLM with structured output.  Sets ``next_action`` on the state
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
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from chain.config import ChainConfig, get_config
from chain.models.output import ConfirmationClassification
from chain.state import MovieFinderState
from chain.utils.llm_factory import get_classifier_llm
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def confirmation_node(state: MovieFinderState) -> dict[str, Any]:
    """Classify the user's confirmation response and route accordingly.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with next_action, and potentially confirmed_movie fields.
    """
    cfg = get_config()
    messages: list[BaseMessage] = state.get("messages", [])
    movies: list[dict[str, Any]] = state.get("enriched_movies", [])
    refinement_count: int = state.get("refinement_count", 0)

    user_message = _last_human_text(messages)
    if not user_message:
        logger.warning("Confirmation node: no human message found — staying on wait")
        return {"next_action": "wait"}

    logger.debug(f"User reply: {user_message[:200]!r}")

    # Build candidates block for the prompt
    candidates_block = _format_candidates(movies)

    # Load and fill the prompt template
    prompt_text = _load_prompt().format(
        candidates_block=candidates_block,
        user_message=user_message,
    )

    llm = get_classifier_llm().with_structured_output(ConfirmationClassification)

    try:
        result = cast(
            ConfirmationClassification,
            await llm.ainvoke([HumanMessage(content=prompt_text)]),
        )
    except Exception as exc:
        logger.error(f"Confirmation classifier failed: {exc}")
        return {
            "messages": [AIMessage(content="I didn't quite catch that. Could you clarify?")],
            "next_action": "wait",
        }

    logger.info(
        f"Confirmation decision: {result.decision} (idx={result.movie_index}) | reason: {result.reasoning}"
    )

    if result.decision == "confirmed" and result.movie_index is not None:
        idx = result.movie_index
        if 0 <= idx < len(movies):
            confirmed = movies[idx]
            confirmed_title = confirmed.get("imdb_title") or confirmed.get("rag_title")
            confirmed_year = confirmed.get("imdb_year") or confirmed.get("rag_year", "")
            confirmed_id = confirmed.get("imdb_id", "—")
            logger.info(
                f"Movie confirmed: {confirmed_title} ({confirmed_year}) | imdb_id={confirmed_id}"
            )
            confirmation_message = await _generate_confirmation_message(confirmed, cfg)
            return {
                "confirmed_movie_id": confirmed.get("imdb_id"),
                "confirmed_movie_title": confirmed_title,
                "confirmed_movie_data": confirmed,
                "next_action": "confirmed",
                "messages": [AIMessage(content=confirmation_message)],
            }

    if result.decision == "not_found":
        if refinement_count >= cfg.max_refinements:
            logger.info(
                f"User says not found & max refinements ({cfg.max_refinements}) reached — routing to dead end"
            )
            return {"next_action": "exhausted"}
        logger.info(
            f"User says not found — routing to refinement (attempt {refinement_count + 1}/{cfg.max_refinements})"
        )
        return {"next_action": "refine"}

    # Unclear — ask for clarification
    logger.debug("Decision unclear — asking user for clarification")
    return {
        "messages": [
            AIMessage(
                content=(
                    "I'm not sure which movie you meant. "
                    'You can tell me the title, say something like "the second one", '
                    "or let me know if none of them match."
                )
            )
        ],
        "next_action": "wait",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_human_text(messages: list[BaseMessage]) -> str:
    """Extract the text of the last human message.

    Args:
        messages: The list of conversation messages.

    Returns:
        The content of the last human message, or empty string.
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and isinstance(msg.content, str):
            return msg.content
    return ""


def _format_candidates(movies: list[dict[str, Any]]) -> str:
    """Format the list of candidates for the LLM prompt.

    Args:
        movies: The list of enriched movie records.

    Returns:
        A numbered string list of candidates.
    """
    if not movies:
        return "(no candidates)"
    lines = []
    for i, m in enumerate(movies, start=1):
        title = m.get("imdb_title") or m.get("rag_title", "?")
        year = m.get("imdb_year") or m.get("rag_year", "?")
        lines.append(f"{i}. {title} ({year})")
    return "\n".join(lines)


async def _generate_confirmation_message(movie: dict[str, Any], cfg: ChainConfig) -> str:
    """Generate a warm, personalised confirmation message using the LLM.

    Args:
        movie: The confirmed enriched movie record.
        cfg: Chain configuration (model names, API key).

    Returns:
        AI-generated confirmation message as a string.
    """
    title = movie.get("imdb_title") or movie.get("rag_title", "this movie")
    year = movie.get("imdb_year") or movie.get("rag_year", "")
    rating = movie.get("imdb_rating")
    directors = movie.get("imdb_directors") or (
        [movie["rag_director"]] if movie.get("rag_director") else []
    )
    stars = movie.get("imdb_stars") or []
    genres = movie.get("imdb_genres") or movie.get("rag_genre") or []
    plot = movie.get("imdb_plot") or movie.get("rag_plot") or ""

    movie_facts: list[str] = [f"Title: {title} ({year})"]
    if rating:
        movie_facts.append(f"IMDb Rating: {rating}/10")
    if directors:
        movie_facts.append(f"Director(s): {', '.join(directors)}")
    if stars:
        movie_facts.append(f"Stars: {', '.join(stars)}")
    if genres:
        movie_facts.append(f"Genres: {', '.join(genres)}")
    if plot:
        movie_facts.append(f"Plot: {plot}")

    prompt = (
        "You are a friendly, enthusiastic movie assistant. The user has just identified their movie.\n\n"
        "Movie details:\n" + "\n".join(f"- {fact}" for fact in movie_facts) + "\n\n"
        "Write a warm, celebratory confirmation message that:\n"
        "1. Celebrates that the user found their movie (use an appropriate emoji or two)\n"
        "2. Shows a quick summary of the movie using the details above with emoji labels\n"
        "3. Invites them to ask follow-up questions with 4-5 personalised example questions "
        "   drawn from the actual cast, director, and genres above\n\n"
        "Use markdown for formatting. Keep it concise and upbeat. Do not invent facts not listed above."
    )

    try:
        response = await get_classifier_llm().ainvoke([HumanMessage(content=prompt)])
        return str(response.content)
    except Exception as exc:  # pragma: no cover
        logger.error(f"Failed to generate confirmation message: {exc}")  # pragma: no cover
        return f"Great! I've confirmed **{title} ({year})** as your movie. What would you like to know about it?"  # pragma: no cover


def _load_prompt() -> str:
    """Load the confirmation prompt template.

    Returns:
        The prompt template string.
    """
    try:
        return (
            importlib.resources.files("chain.prompts")
            .joinpath("confirmation.md")
            .read_text(encoding="utf-8")
        )
    except Exception:
        fallback_prompt = (
            'Candidates:\n{candidates_block}\n\nUser said: "{user_message}"\n'
            "Classify as confirmed/not_found/unclear."
        )
        return fallback_prompt  # pragma: no cover
