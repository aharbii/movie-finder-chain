"""Tests for ADR 0008 provider factory and vector collection config."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from chain.config import (
    ChainConfig,
    resolve_vector_collection_name,
    sanitize_model_name,
)
from chain.rag.vector_store import get_vector_search_provider
from chain.utils.llm_factory import get_classifier_llm, get_query_embedder, get_reasoning_llm


def test_sanitize_model_name_matches_rag_contract() -> None:
    assert sanitize_model_name("BAAI/bge-m3") == "baai_bge_m3"
    assert sanitize_model_name("text-embedding-3-large") == "text_embedding_3_large"
    assert sanitize_model_name("nomic.embed text") == "nomic_embed_text"
    assert sanitize_model_name("foo@bar---baz") == "foo_bar_baz"


def test_qdrant_collection_prefix_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("VECTOR_COLLECTION_PREFIX", "test_prefix")
    config = ChainConfig()
    assert config.qdrant_collection_prefix == "test_prefix"


def test_validate_url_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_URL", "ftp://invalid")
    with pytest.raises(ValidationError, match="is not a valid HTTP"):
        ChainConfig()


def test_validate_collection_prefix_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_COLLECTION_PREFIX", "   ")
    with pytest.raises(ValidationError, match="must not be blank"):
        ChainConfig()


def test_resolve_qdrant_collection_name_alias() -> None:
    from chain.config import resolve_qdrant_collection_name

    assert resolve_qdrant_collection_name("movies", "test-model", 128) == "movies_test_model_128"
    assert (
        resolve_vector_collection_name("movies", "text-embedding-3-large", 3072)
        == "movies_text_embedding_3_large_3072"
    )


def test_config_rejects_unknown_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLASSIFIER_PROVIDER", "not-a-provider")

    with pytest.raises(ValidationError):
        ChainConfig()


def test_config_exposes_generic_vector_collection_name(mock_config: ChainConfig) -> None:
    assert mock_config.vector_collection_name == "movies_text_embedding_3_large_3072"
    assert mock_config.qdrant_collection_name == mock_config.vector_collection_name


def test_classifier_llm_uses_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLASSIFIER_PROVIDER", "openai")
    monkeypatch.setenv("CLASSIFIER_MODEL", "gpt-4.1-mini")

    with patch("chain.utils.llm_factory._build_chat_model", return_value=MagicMock()) as build:
        first = get_classifier_llm()
        second = get_classifier_llm()

    assert first is second
    build.assert_called_once_with(provider="openai", model="gpt-4.1-mini")


def test_reasoning_llm_uses_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONING_PROVIDER", "groq")
    monkeypatch.setenv("REASONING_MODEL", "llama-3.3-70b-versatile")

    with patch("chain.utils.llm_factory._build_chat_model", return_value=MagicMock()) as build:
        get_reasoning_llm()

    build.assert_called_once_with(provider="groq", model="llama-3.3-70b-versatile")


def test_query_embedder_uses_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-m3")

    with patch("chain.utils.llm_factory._build_query_embedder", return_value=MagicMock()) as build:
        get_query_embedder()

    build.assert_called_once_with(provider="ollama", model="bge-m3")


def test_vector_store_uses_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_STORE", "pinecone")
    monkeypatch.setenv("PINECONE_API_KEY", "pc-test")

    with patch(
        "chain.rag.vector_store.create_vector_search_provider", return_value=MagicMock()
    ) as build:
        first = get_vector_search_provider()
        second = get_vector_search_provider()

    assert first is second
    build.assert_called_once_with()


def test_config_accepts_rag_vector_store_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_STORE", "chromadb")
    assert ChainConfig().vector_store == "chromadb"
