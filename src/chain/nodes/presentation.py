"""Presentation node.

Formats the validated candidate pool into a user-facing AI message and sets
``phase = "confirmation"`` so the next invocation routes to the confirmation
branch.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage

from chain.state import MovieFinderState

logger = logging.getLogger(__name__)


def presentation_node(state: MovieFinderState) -> dict:
    """Format enriched movies into a structured AI message for the user."""
    movies: list[dict] = state.get("enriched_movies", [])
    refinement_count: int = state.get("refinement_count", 0)

    if not movies:
        text = (
            "I searched our database but couldn't find any movies matching your description. "
            "Could you share more details — for example, the approximate decade, country of "
            "origin, a specific actor you remember, or a key scene?"
        )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "confirmation",
            "next_action": "wait",
        }

    lines: list[str] = []

    if refinement_count == 0:
        lines.append("Based on your description, here are the movies that best match your plot:")
    else:
        lines.append(
            f"I've refined the search (attempt {refinement_count + 1}) and found these candidates:"
        )

    lines.append("")

    for i, movie in enumerate(movies, start=1):
        title = movie.get("imdb_title") or movie.get("rag_title", "Unknown")
        year = movie.get("imdb_year") or movie.get("rag_year") or "?"
        rating = movie.get("imdb_rating")
        directors = movie.get("imdb_directors") or []
        stars = movie.get("imdb_stars") or []
        genres = movie.get("imdb_genres") or movie.get("rag_genre") or []
        plot = movie.get("imdb_plot") or ""
        poster = movie.get("imdb_poster_url")
        confidence = movie.get("confidence", 0.0)

        lines.append(f"**{i}. {title}** ({year})")

        if rating:
            lines.append(f"   ⭐ IMDb Rating: {rating}/10")
        if directors:
            lines.append(f"   🎬 Director(s): {', '.join(directors[:2])}")
        if stars:
            lines.append(f"   🎭 Stars: {', '.join(stars[:4])}")
        if genres:
            lines.append(f"   🎞️  Genre: {', '.join(genres[:3])}")
        if plot:
            # Trim to avoid spoilers — show only the first two sentences
            sentences = plot.split(". ")
            brief = ". ".join(sentences[:2])
            if len(sentences) > 2:
                brief += "..."
            lines.append(f"   📖 {brief}")
        if poster:
            lines.append(f"   🖼️  Poster: {poster}")
        if confidence < 0.5:
            lines.append("   ⚠️  *(lower confidence match)*")

        lines.append("")

    lines.append(
        '**Is your movie one of these?** Reply with the number (e.g. *"It\'s #2"*), '
        "or tell me it's not listed and I'll search again with more details."
    )

    return {
        "messages": [AIMessage(content="\n".join(lines))],
        "phase": "confirmation",
        "next_action": "wait",
    }
