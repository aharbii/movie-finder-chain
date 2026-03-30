"""Output Pydantic models for the Movie Finder chain.

These are the serialisable models returned to the API / frontend layer.
They are separate from the internal state dicts used inside the graph so
that the public contract can evolve independently.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RagCandidate(BaseModel):
    """Raw result from the Qdrant vector-store search.

    Attributes:
        title: Movie title.
        release_year: Year of release.
        director: Director name.
        genre: List of genres.
        cast: List of primary cast members.
        plot: Plot description from the database.
        rag_score: Qdrant cosine similarity (0–1).
    """

    title: str
    release_year: int = 0
    director: str = ""
    genre: list[str] = Field(default_factory=list)
    cast: list[str] = Field(default_factory=list)
    plot: str = ""
    rag_score: float = 0.0


class EnrichedMovie(BaseModel):
    """A RAG candidate cross-referenced and enriched with live IMDb data.

    Attributes:
        rag_title: Title from the RAG source.
        rag_year: Release year from the RAG source.
        rag_director: Director from the RAG source.
        rag_genre: Genres from the RAG source.
        rag_cast: Cast members from the RAG source.
        rag_plot: Plot summary from the RAG source.
        imdb_id: Unique IMDb identifier (tt...).
        imdb_title: Official IMDb title.
        imdb_year: Official IMDb release year.
        imdb_rating: IMDb user rating (0-10).
        imdb_plot: Official IMDb plot summary.
        imdb_genres: Official IMDb genres.
        imdb_directors: Official IMDb directors.
        imdb_stars: Official IMDb stars.
        imdb_poster_url: URL to the movie poster.
        confidence: Match confidence score (0-1).
    """

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
        """Return the official IMDb title if available, otherwise the RAG title."""
        return self.imdb_title or self.rag_title

    @property
    def display_year(self) -> int | None:
        """Return the official IMDb year if available, otherwise the RAG year."""
        return self.imdb_year or (self.rag_year if self.rag_year else None)


class CandidatePool(BaseModel):
    """The full pool of enriched candidates returned to the user.

    Attributes:
        query: The plot description used for the search.
        candidates: List of enriched movie candidates.
        refinement_count: Number of refinement loops performed.
    """

    query: str
    candidates: list[EnrichedMovie]
    refinement_count: int = 0


class ConfirmedMovie(BaseModel):
    """The movie the user has positively identified.

    Attributes:
        imdb_id: Unique IMDb identifier.
        title: Movie title.
        year: Release year.
        rating: IMDb user rating.
        plot: Plot summary.
        genres: List of genres.
        directors: List of directors.
        stars: List of primary stars.
        poster_url: URL to the poster image.
    """

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
    """Structured output from the confirmation classifier LLM call.

    Attributes:
        decision: One of: 'confirmed', 'not_found', 'unclear'.
        movie_index: 0-based index of the confirmed movie in the candidates list.
        reasoning: Brief reasoning for the classification decision.
    """

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
    """Structured output from the refinement LLM call.

    Attributes:
        refined_query: An improved Qdrant search query incorporating all plot details.
        message_to_user: A natural message informing the user we are searching again.
    """

    refined_query: str = Field(
        description="An improved Qdrant search query incorporating all plot details so far.",
    )
    message_to_user: str = Field(
        description="A natural message informing the user we are searching again "
        "with updated details. Do NOT ask a question — just acknowledge and search.",
    )
