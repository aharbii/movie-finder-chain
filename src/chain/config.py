"""Chain configuration via Pydantic Settings.

All values are read from environment variables (or a .env file).
Fail-fast validation happens on first import so misconfigured deployments
surface immediately rather than at the first API call.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChainConfig(BaseSettings):
    """Environment-driven configuration for the Movie Finder chain."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Vector store (Qdrant) ---
    qdrant_endpoint: str = Field(..., description="Qdrant Cloud cluster URL")
    qdrant_api_key: str = Field(..., description="Qdrant API key")
    # Must match the collection created during rag_ingestion (embedding model name)
    qdrant_collection: str = Field(
        default="text-embedding-3-large",
        description="Qdrant collection name (matches ingestion embedding model)",
    )

    # --- Embedding (OpenAI) ---
    openai_api_key: str = Field(..., description="OpenAI API key for embeddings")
    embedding_model: str = Field(
        default="text-embedding-3-large",
        description="OpenAI embedding model — must match the ingestion model",
    )
    embedding_dimension: int = Field(
        default=3072,
        description="Embedding vector dimension — must match the ingestion model",
    )

    # --- LLM (Anthropic) ---
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    # Fast classifier for confirmation step
    classifier_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Lightweight model for confirmation classification",
    )
    # Full reasoning for refinement and Q&A
    reasoning_model: str = Field(
        default="claude-sonnet-4-6",
        description="Model for refinement query building and Q&A agent",
    )

    # --- Search tuning ---
    rag_top_k: int = Field(default=8, ge=1, le=20, description="Number of RAG candidates")
    max_refinements: int = Field(
        default=3, ge=1, le=5, description="Max refinement cycles before dead-end"
    )
    imdb_search_limit: int = Field(
        default=3, ge=1, le=10, description="IMDB search results per RAG candidate"
    )
    confidence_threshold: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Minimum confidence to include in results"
    )

    # --- LangSmith observability ---
    langchain_tracing_v2: bool = Field(default=False)
    langchain_endpoint: str = Field(default="https://api.smith.langchain.com")
    langchain_api_key: str = Field(default="")
    langchain_project: str = Field(default="movie-finder")

    @field_validator("qdrant_endpoint")
    @classmethod
    def validate_qdrant_endpoint(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("QDRANT_ENDPOINT must be a valid HTTP(S) URL")
        return v.rstrip("/")


@lru_cache(maxsize=1)
def get_config() -> ChainConfig:
    """Return the singleton ChainConfig instance (cached after first call)."""
    return ChainConfig()  # type: ignore[call-arg]
