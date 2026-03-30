"""Chain configuration via Pydantic Settings.

All values are read from environment variables (or a .env file).
Fail-fast validation happens on first import so misconfigured deployments
surface immediately rather than at the first API call.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChainConfig(BaseSettings):
    """Configuration singleton for the Movie Finder chain.

    Attributes:
        qdrant_url: Qdrant Cloud cluster URL.
        qdrant_api_key_ro: Read-only API key for the cluster.
        qdrant_collection_name: Name of the collection to search.
        openai_api_key: OpenAI API key (for embeddings).
        anthropic_api_key: Anthropic API key (for Claude reasoning).
        embedding_model: The OpenAI embedding model name.
        embedding_dimension: Dimension of the vectors (must match collection).
        classifier_model: Claude model name for routing/classification.
        reasoning_model: Claude model name for presentation/Q&A.
        langsmith_tracing: Whether to enable LangSmith tracing.
        langsmith_endpoint: LangSmith API endpoint.
        langsmith_api_key: LangSmith API key.
        langsmith_project: LangSmith project name.
        rag_top_k: Number of candidates to fetch from Qdrant.
        max_refinements: Max discovery refinement loops before dead-ending.
        imdb_search_limit: Max hits per IMDb search query.
        confidence_threshold: Minimum IMDb match score to present to user.
        log_level: Logging level (INFO, DEBUG, etc.).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Qdrant ---
    qdrant_url: str = Field(..., alias="QDRANT_URL")
    qdrant_api_key_ro: str = Field(..., alias="QDRANT_API_KEY_RO")
    qdrant_collection_name: str = Field("movies", alias="QDRANT_COLLECTION_NAME")

    # --- LLM Providers ---
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")

    # --- Models ---
    embedding_model: str = Field("text-embedding-3-large", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(3072, alias="EMBEDDING_DIMENSION")
    classifier_model: str = Field("claude-haiku-4-5-20251001", alias="CLASSIFIER_MODEL")
    reasoning_model: str = Field("claude-sonnet-4-6", alias="REASONING_MODEL")

    # --- LangSmith ---
    langsmith_tracing: bool = Field(False, alias="LANGSMITH_TRACING")
    langsmith_endpoint: str = Field(
        "https://api.smith.langchain.com", alias="LANGSMITH_ENDPOINT"
    )
    langsmith_api_key: str | None = Field(None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field("movie-finder", alias="LANGSMITH_PROJECT")

    # --- Pipeline Logic ---
    rag_top_k: int = Field(8, alias="RAG_TOP_K")
    max_refinements: int = Field(3, alias="MAX_REFINEMENTS")
    imdb_search_limit: int = Field(3, alias="IMDB_SEARCH_LIMIT")
    confidence_threshold: float = Field(0.3, alias="CONFIDENCE_THRESHOLD")

    # --- Logging ---
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("qdrant_url", "langsmith_endpoint", mode="before")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Strip trailing slash from URLs.

        Args:
            v: The URL string.

        Returns:
            URL without trailing slash.

        Raises:
            ValueError: If the URL doesn't start with http.
        """
        if v and not v.startswith("http"):
            raise ValueError(f"{v} is not a valid HTTP(S) URL")
        return v.rstrip("/")


@lru_cache(maxsize=1)
def get_config() -> ChainConfig:
    """Return the singleton ChainConfig instance (cached after first call).

    Returns:
        The singleton ChainConfig.
    """
    return ChainConfig()  # type: ignore[call-arg]
