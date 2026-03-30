"""Presentation node.

Formats the enriched movie candidates into a user-friendly AIMessage.
If multiple candidates are found, they are presented as a numbered list.
If only one is found, it is presented with its primary details.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from chain.state import MovieFinderState
from chain.utils.logger import get_logger

logger = get_logger(__name__)


async def presentation_node(state: MovieFinderState) -> dict[str, Any]:
    """Format and present the candidates to the user.

    Args:
        state: The current graph state.

    Returns:
        Partial state update with an AIMessage and updated phase.
    """
    movies: list[dict[str, Any]] = state.get("enriched_movies", [])
    refinement_count: int = state.get("refinement_count", 0)

    if not movies:
        logger.info("No movies to present")
        return {
            "messages": [AIMessage(content="I couldn't find any movies matching that description.")],
            "phase": "discovery",  # Stay in discovery to let user try again
        }

    logger.info(f"Presenting {len(movies)} candidates to user")

    content = _format_single(movies[0]) if len(movies) == 1 else _format_list(movies)

    # Prefix with a "trying again" message if this was a refinement loop
    if refinement_count > 0:
        content = f"I've searched again with more details. Here is what I found:\n\n{content}"

    return {
        "messages": [AIMessage(content=content)],
        "phase": "confirmation",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_list(movies: list[dict[str, Any]]) -> str:
    """Format multiple movies into a numbered list.

    Args:
        movies: The list of movie records.

    Returns:
        A formatted string list.
    """
    lines = ["I found a few possibilities. Is it one of these?\n"]
    for i, m in enumerate(movies, start=1):
        t = m.get("imdb_title") or m.get("rag_title", "?")
        y = m.get("imdb_year") or m.get("rag_year") or "?"
        conf = m.get("confidence", 0.0)
        imdb_id = m.get("imdb_id", "—")
        lines.append(f"{i}. **{t}** ({y}) — *confidence: {conf:.0%}* [IMDb: {imdb_id}]")

    lines.append("\nReply with the number, or say \"none of these\" to refine the search.")
    return "\n".join(lines)


def _format_single(movie: dict[str, Any]) -> str:
    """Format a single movie with full details.

    Args:
        movie: The movie record.

    Returns:
        A formatted string with movie details.
    """
    title = movie.get("imdb_title") or movie.get("rag_title", "Unknown")
    year = movie.get("imdb_year") or movie.get("rag_year") or "?"
    rating = movie.get("imdb_rating")
    directors = movie.get("imdb_directors") or []
    stars = movie.get("imdb_stars") or []
    genres = movie.get("imdb_genres") or movie.get("rag_genre") or []
    plot = movie.get("imdb_plot") or ""
    poster = movie.get("imdb_poster_url")
    confidence = movie.get("confidence", 0.0)

    lines = [
        f"I'm quite sure it's **{title}** ({year})!\n",
        f"**IMDb Rating:** {rating}/10" if rating else "**IMDb Rating:** N/A",
        f"**Genre:** {', '.join(genres)}" if genres else None,
        f"**Director:** {', '.join(directors)}" if directors else None,
        f"**Stars:** {', '.join(stars)}" if stars else None,
        f"\n{plot}\n" if plot else "",
        f"*(Confidence: {confidence:.0%})*" if confidence > 0 else "",
    ]

    if poster:
        lines.append(f"\n![Poster]({poster})")

    lines.append("\nIs this the right one? (Yes/No)")
    return "\n".join(filter(None, lines))
