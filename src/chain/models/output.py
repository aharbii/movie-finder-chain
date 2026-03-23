"""Output Pydantic models for the Movie Finder chain.

These are the serialisable models returned to the API / frontend layer.
They are separate from the internal state dicts used inside the graph so
that the public contract can evolve independently.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RagCandidate(BaseModel):
    """Raw result from the Qdrant vector-store search."""

    title: str
    release_year: int = 0
    director: str = ""
    genre: list[str] = Field(default_factory=list)
    cast: list[str] = Field(default_factory=list)
    plot: str = ""
    rag_score: float = 0.0  # Qdrant cosine similarity (0–1)


class EnrichedMovie(BaseModel):
    """A RAG candidate cross-referenced and enriched with live IMDb data."""

    # --- From RAG ---
    rag_title: str
    rag_year: int = 0
    rag_director: str = ""
    rag_genre: list[str] = Field(default_factory=list)
    rag_cast: list[str] = Field(default_factory=list)
    rag_plot: str = ""

    # --- From IMDb (None when no confident match was found) ---
    imdb_id: str | None = None
    imdb_title: str | None = None
    imdb_year: int | None = None
    imdb_rating: float | None = None
    imdb_plot: str | None = None
    imdb_genres: list[str] = Field(default_factory=list)
    imdb_directors: list[str] = Field(default_factory=list)
    imdb_stars: list[str] = Field(default_factory=list)
    imdb_poster_url: str | None = None

    # --- Validation score ---
    confidence: float = 0.0

    @property
    def display_title(self) -> str:
        return self.imdb_title or self.rag_title

    @property
    def display_year(self) -> int | None:
        return self.imdb_year or (self.rag_year if self.rag_year else None)


class CandidatePool(BaseModel):
    """The full pool of enriched candidates returned to the user."""

    query: str
    candidates: list[EnrichedMovie]
    refinement_count: int = 0


class ConfirmedMovie(BaseModel):
    """The movie the user has positively identified."""

    imdb_id: str
    title: str
    year: int | None = None
    rating: float | None = None
    plot: str | None = None
    genres: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    stars: list[str] = Field(default_factory=list)
    poster_url: str | None = None


class ConfirmationClassification(BaseModel):
    """Structured output from the confirmation classifier LLM call."""

    decision: str = Field(
        description="One of: 'confirmed', 'not_found', 'unclear'",
    )
    movie_index: int | None = Field(
        default=None,
        description="0-based index of the confirmed movie in the candidates list. "
        "Only set when decision == 'confirmed'.",
    )
    reasoning: str = Field(
        default="",
        description="Brief reasoning for the classification decision.",
    )


class RefinementPlan(BaseModel):
    """Structured output from the refinement LLM call."""

    refined_query: str = Field(
        description="An improved Qdrant search query incorporating all plot details so far.",
    )
    message_to_user: str = Field(
        description="A natural message informing the user we are searching again "
        "with updated details. Do NOT ask a question — just acknowledge and search.",
    )
