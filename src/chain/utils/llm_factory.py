"""Provider factories for chat models and query embeddings."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol, cast

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from chain.config import ChatProvider, EmbeddingProvider, get_config


class QueryEmbedder(Protocol):
    """Minimal embedding interface needed by the RAG search service."""

    def embed_query(self, text: str) -> list[float]:
        """Return an embedding vector for a single query string."""


class OpenAIQueryEmbedder:
    """OpenAI SDK adapter implementing the QueryEmbedder protocol."""

    def __init__(self, *, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.last_token_count = 0

    def embed_query(self, text: str) -> list[float]:
        """Return an OpenAI embedding for ``text``."""
        response = self._client.embeddings.create(input=text, model=self._model)
        self.last_token_count = int(response.usage.total_tokens)
        return list(response.data[0].embedding)


@lru_cache(maxsize=1)
def get_classifier_llm() -> BaseChatModel:
    """Return the cached classifier chat model."""
    cfg = get_config()
    return _build_chat_model(
        provider=cfg.classifier_provider,
        model=cfg.classifier_model,
    )


@lru_cache(maxsize=1)
def get_reasoning_llm() -> BaseChatModel:
    """Return the cached reasoning chat model."""
    cfg = get_config()
    return _build_chat_model(
        provider=cfg.reasoning_provider,
        model=cfg.reasoning_model,
    )


@lru_cache(maxsize=1)
def get_query_embedder() -> QueryEmbedder:
    """Return the cached query embedding provider."""
    cfg = get_config()
    return _build_query_embedder(
        provider=cfg.embedding_provider,
        model=cfg.embedding_model,
    )


def _build_chat_model(*, provider: ChatProvider, model: str) -> BaseChatModel:
    """Build a chat model for the selected provider."""
    cfg = get_config()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return cast(
            BaseChatModel,
            ChatAnthropic(
                model_name=model,
                api_key=SecretStr(_required(cfg.anthropic_api_key, "ANTHROPIC_API_KEY")),
            ),
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return cast(
            BaseChatModel,
            ChatOpenAI(
                model=model,
                api_key=SecretStr(_required(cfg.openai_api_key, "OPENAI_API_KEY")),
            ),
        )

    if provider == "groq":
        from langchain_groq import ChatGroq

        return cast(
            BaseChatModel,
            ChatGroq(
                model=model,
                api_key=SecretStr(_required(cfg.groq_api_key, "GROQ_API_KEY")),
            ),
        )

    if provider == "together":
        from langchain_openai import ChatOpenAI

        return cast(
            BaseChatModel,
            ChatOpenAI(
                model=model,
                api_key=SecretStr(_required(cfg.together_api_key, "TOGETHER_API_KEY")),
                base_url="https://api.together.xyz/v1",
            ),
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return cast(
            BaseChatModel,
            ChatOllama(
                model=model,
                base_url=cfg.ollama_base_url,
            ),
        )

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return cast(
            BaseChatModel,
            ChatGoogleGenerativeAI(
                model=model,
                api_key=SecretStr(_required(cfg.google_api_key, "GOOGLE_API_KEY")),
            ),
        )

    raise ValueError(f"Unsupported chat provider: {provider}")


def _build_query_embedder(*, provider: EmbeddingProvider, model: str) -> QueryEmbedder:
    """Build a query embedding provider."""
    cfg = get_config()
    if provider == "openai":
        return OpenAIQueryEmbedder(
            api_key=_required(cfg.openai_api_key, "OPENAI_API_KEY"),
            model=model,
        )

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return cast(
            QueryEmbedder,
            OllamaEmbeddings(
                model=model,
                base_url=cfg.ollama_base_url,
            ),
        )

    if provider in {"sentence-transformers", "huggingface"}:
        from langchain_huggingface import HuggingFaceEmbeddings

        return cast(
            QueryEmbedder,
            HuggingFaceEmbeddings(model_name=model),
        )

    raise ValueError(f"Unsupported embedding provider: {provider}")


def _required(value: str | None, env_var: str) -> str:
    """Return a configured secret or raise a provider-specific error."""
    if value:
        return value
    raise ValueError(f"{env_var} is required for the selected provider")
