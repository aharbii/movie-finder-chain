"""Chain configuration via Pydantic Settings.

All values are read from environment variables (or a .env file).
Fail-fast validation happens on first import so misconfigured deployments
surface immediately rather than at the first API call.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ChatProvider = Literal["anthropic", "openai", "groq", "together", "ollama", "google"]
EmbeddingProvider = Literal["openai", "ollama", "sentence-transformers", "huggingface"]
VectorStoreProvider = Literal["qdrant", "chromadb", "pinecone", "pgvector"]

_SANITIZE_PATTERN = re.compile(r"[\/.\-\s]+")
_INVALID_PATTERN = re.compile(r"[^a-z0-9_]+")
_MULTI_UNDERSCORE_PATTERN = re.compile(r"_+")
_runtime_config: ChainConfig | None = None


class ChainConfig(BaseSettings):
    """Configuration singleton for the Movie Finder chain.

    Attributes:
        qdrant_url: Qdrant Cloud cluster URL.
        qdrant_api_key_ro: Read-only API key for the cluster.
        vector_store: Vector store provider.
        vector_collection_prefix: Prefix for dynamically resolved vector collections.
        vector_store_url: Generic vector store URL override.
        vector_store_api_key: Generic vector store API key override.
        chromadb_persist_path: Local ChromaDB persistence path.
        pinecone_api_key: Pinecone API key.
        pinecone_index_name: Pinecone index name.
        pinecone_index_host: Pinecone index host.
        pgvector_dsn: PostgreSQL DSN with pgvector enabled.
        pgvector_schema: PostgreSQL schema for pgvector tables.
        embedding_provider: Provider used for query embeddings.
        embedding_model: The embedding model name.
        embedding_dimension: Dimension of the vectors (must match collection).
        classifier_provider: Provider used for routing/classification.
        classifier_model: Model name for routing/classification.
        reasoning_provider: Provider used for presentation/Q&A.
        reasoning_model: Model name for presentation/Q&A.
        openai_api_key: OpenAI API key.
        anthropic_api_key: Anthropic API key.
        groq_api_key: Groq API key.
        together_api_key: Together API key.
        google_api_key: Google API key.
        ollama_base_url: Ollama API base URL.
        langsmith_tracing: Whether to enable LangSmith tracing.
        langsmith_endpoint: LangSmith API endpoint.
        langsmith_api_key: LangSmith API key.
        langsmith_project: LangSmith project name.
        rag_top_k: Number of candidates to fetch from the vector store.
        max_refinements: Max discovery refinement loops before dead-ending.
        imdb_search_limit: Max hits per IMDb search query.
        imdb_search_concurrency: Max concurrent IMDb search requests.
        imdb_retry_base_delay_seconds: Fallback retry delay on rate limits.
        imdb_node_timeout_seconds: Hard timeout for the IMDb enrichment node.
        confidence_threshold: Minimum IMDb match score to present to user.
        log_level: Logging level (INFO, DEBUG, etc.).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Qdrant ---
    qdrant_url: str | None = Field(
        None,
        validation_alias=AliasChoices("QDRANT_URL", "VECTOR_STORE_URL"),
    )
    qdrant_api_key_ro: str | None = Field(
        None,
        validation_alias=AliasChoices(
            "QDRANT_API_KEY_RO", "QDRANT_API_KEY", "VECTOR_STORE_API_KEY"
        ),
    )
    vector_store: VectorStoreProvider = Field("qdrant", alias="VECTOR_STORE")
    vector_collection_prefix: str = Field(
        "movies",
        validation_alias=AliasChoices("VECTOR_COLLECTION_PREFIX", "QDRANT_COLLECTION_PREFIX"),
    )
    vector_store_url: str | None = Field(None, alias="VECTOR_STORE_URL")
    vector_store_api_key: str | None = Field(None, alias="VECTOR_STORE_API_KEY")
    chromadb_persist_path: str = Field(
        "outputs/chromadb/local",
        alias="CHROMADB_PERSIST_PATH",
    )
    pinecone_api_key: str | None = Field(
        None,
        validation_alias=AliasChoices("PINECONE_API_KEY", "VECTOR_STORE_API_KEY"),
    )
    pinecone_index_name: str = Field("movie-finder-rag", alias="PINECONE_INDEX_NAME")
    pinecone_index_host: str | None = Field(None, alias="PINECONE_INDEX_HOST")
    pinecone_cloud: str = Field("aws", alias="PINECONE_CLOUD")
    pinecone_region: str = Field("us-east-1", alias="PINECONE_REGION")
    pgvector_dsn: str | None = Field(
        None,
        validation_alias=AliasChoices("PGVECTOR_DSN", "VECTOR_STORE_URL"),
    )
    pgvector_schema: str = Field("public", alias="PGVECTOR_SCHEMA")

    # --- LLM Providers ---
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    groq_api_key: str | None = Field(None, alias="GROQ_API_KEY")
    together_api_key: str | None = Field(None, alias="TOGETHER_API_KEY")
    google_api_key: str | None = Field(None, alias="GOOGLE_API_KEY")
    ollama_base_url: str = Field(
        "http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "OLLAMA_URL"),
    )
    database_url: str | None = Field(None, alias="DATABASE_URL")

    # --- Models ---
    embedding_provider: EmbeddingProvider = Field("openai", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field("text-embedding-3-large", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(
        3072,
        validation_alias=AliasChoices("EMBEDDING_DIMENSION", "EMBEDDING_DIMENSIONS"),
        ge=1,
    )
    classifier_provider: ChatProvider = Field("anthropic", alias="CLASSIFIER_PROVIDER")
    classifier_model: str = Field("claude-haiku-4-5-20251001", alias="CLASSIFIER_MODEL")
    reasoning_provider: ChatProvider = Field("anthropic", alias="REASONING_PROVIDER")
    reasoning_model: str = Field("claude-sonnet-4-6", alias="REASONING_MODEL")

    # --- LangSmith ---
    langsmith_tracing: bool = Field(False, alias="LANGSMITH_TRACING")
    langsmith_endpoint: str = Field("https://api.smith.langchain.com", alias="LANGSMITH_ENDPOINT")
    langsmith_api_key: str | None = Field(None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field("movie-finder", alias="LANGSMITH_PROJECT")

    # --- Pipeline Logic ---
    rag_top_k: int = Field(8, alias="RAG_TOP_K")
    max_refinements: int = Field(3, alias="MAX_REFINEMENTS")
    imdb_search_limit: int = Field(3, alias="IMDB_SEARCH_LIMIT")
    imdb_search_concurrency: int = Field(2, alias="IMDB_SEARCH_CONCURRENCY", ge=1)
    imdb_retry_base_delay_seconds: float = Field(
        2.0,
        alias="IMDB_RETRY_BASE_DELAY_SECONDS",
        gt=0,
    )
    imdb_node_timeout_seconds: float = Field(10.0, alias="IMDB_NODE_TIMEOUT_SECONDS", gt=0)
    confidence_threshold: float = Field(0.3, alias="CONFIDENCE_THRESHOLD")

    # --- Logging ---
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @property
    def vector_collection_name(self) -> str:
        """Return the resolved dynamic vector collection name."""
        return resolve_vector_collection_name(
            prefix=self.vector_collection_prefix,
            model=self.embedding_model,
            dimension=self.embedding_dimension,
        )

    @property
    def qdrant_collection_prefix(self) -> str:
        """Return the legacy Qdrant collection prefix alias."""
        return self.vector_collection_prefix

    @property
    def qdrant_collection_name(self) -> str:
        """Return the Qdrant collection name for backward-compatible callers."""
        return self.vector_collection_name

    @field_validator(
        "qdrant_url",
        "vector_store_url",
        "langsmith_endpoint",
        "ollama_base_url",
        mode="before",
    )
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
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
        return v.rstrip("/") if v else v

    @field_validator("vector_collection_prefix")
    @classmethod
    def validate_collection_prefix(cls, v: str) -> str:
        """Ensure the dynamic collection prefix is not blank."""
        prefix = v.strip()
        if not prefix:
            raise ValueError("VECTOR_COLLECTION_PREFIX must not be blank")
        return prefix


@lru_cache(maxsize=1)
def get_config() -> ChainConfig:
    """Return the singleton ChainConfig instance (cached after first call).

    Returns:
        The singleton ChainConfig.
    """
    return _runtime_config if _runtime_config is not None else ChainConfig()


def configure_runtime_config(config: ChainConfig | None) -> None:
    """Set an explicit runtime config supplied by the backend composition root.

    This keeps the chain usable as a standalone package while allowing the
    deployed FastAPI app to validate and pass provider settings once during
    lifespan startup.
    """
    global _runtime_config
    _runtime_config = config
    get_config.cache_clear()
    from chain.rag.vector_store import get_vector_search_provider
    from chain.utils.llm_factory import get_classifier_llm, get_query_embedder, get_reasoning_llm

    get_classifier_llm.cache_clear()
    get_reasoning_llm.cache_clear()
    get_query_embedder.cache_clear()
    get_vector_search_provider.cache_clear()


def resolve_vector_collection_name(prefix: str, model: str, dimension: int) -> str:
    """Resolve the shared zero-collision vector collection name.

    The sanitization contract is shared with the RAG ingestion pipeline:
    lowercase, replace ``/``, ``.``, ``-``, and spaces with underscores, and
    trim leading/trailing underscores.
    """
    return f"{prefix}_{sanitize_model_name(model)}_{dimension}"


def resolve_qdrant_collection_name(prefix: str, model: str, dimension: int) -> str:
    """Backward-compatible alias for the Qdrant collection naming contract."""
    return resolve_vector_collection_name(prefix, model, dimension)


def sanitize_model_name(model: str) -> str:
    """Sanitize a model name for use in a vector collection name."""
    normalized = _SANITIZE_PATTERN.sub("_", model.strip().lower())
    normalized = _INVALID_PATTERN.sub("_", normalized)
    normalized = _MULTI_UNDERSCORE_PATTERN.sub("_", normalized)
    return normalized.strip("_")
