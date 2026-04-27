"""Tests for llm factory."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from chain.config import ChainConfig
from chain.utils.llm_factory import (
    OpenAIQueryEmbedder,
    _build_chat_model,
    _build_query_embedder,
    _required,
)


def test_required_helper() -> None:
    assert _required("value", "ENV_VAR") == "value"
    with pytest.raises(ValueError, match="ENV_VAR is required"):
        _required(None, "ENV_VAR")


def test_openai_query_embedder() -> None:
    mock_client = MagicMock()
    mock_module = MagicMock()
    mock_module.OpenAI.return_value = mock_client

    mock_response = MagicMock()
    mock_response.usage.total_tokens = 42
    mock_response.data = [MagicMock(embedding=[0.1, 0.2])]
    mock_client.embeddings.create.return_value = mock_response

    with patch.dict(sys.modules, {"openai": mock_module}):
        embedder = OpenAIQueryEmbedder(api_key="test-key", model="test-model")

        result = embedder.embed_query("test query")
    assert result == [0.1, 0.2]
    assert embedder.last_token_count == 42
    mock_client.embeddings.create.assert_called_once_with(input="test query", model="test-model")


def test_build_chat_model_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_anthropic": mock_module}):
        _build_chat_model(provider="anthropic", model="claude-3")
        mock_module.ChatAnthropic.assert_called_once_with(
            model_name="claude-3", api_key=SecretStr("test-key")
        )


def test_build_chat_model_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_openai": mock_module}):
        _build_chat_model(provider="openai", model="gpt-4")
        mock_module.ChatOpenAI.assert_called_once_with(model="gpt-4", api_key=SecretStr("test-key"))


def test_build_chat_model_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_groq": mock_module}):
        _build_chat_model(provider="groq", model="llama3")
        mock_module.ChatGroq.assert_called_once_with(model="llama3", api_key=SecretStr("test-key"))


def test_build_chat_model_together(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "test-key")
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_openai": mock_module}):
        _build_chat_model(provider="together", model="llama3")
        mock_module.ChatOpenAI.assert_called_once_with(
            model="llama3", api_key=SecretStr("test-key"), base_url="https://api.together.xyz/v1"
        )


def test_build_chat_model_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_ollama": mock_module}):
        _build_chat_model(provider="ollama", model="llama3")
        mock_module.ChatOllama.assert_called_once_with(
            model="llama3", base_url=ChainConfig().ollama_base_url
        )


def test_build_chat_model_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_google_genai": mock_module}):
        _build_chat_model(provider="google", model="gemini")
        mock_module.ChatGoogleGenerativeAI.assert_called_once_with(
            model="gemini", api_key=SecretStr("test-key")
        )


def test_build_chat_model_unsupported() -> None:
    with pytest.raises(ValueError, match="Unsupported chat provider"):
        _build_chat_model(provider="unknown", model="model")  # type: ignore


def test_build_query_embedder_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("chain.utils.llm_factory.OpenAIQueryEmbedder") as mock_cls:
        _build_query_embedder(provider="openai", model="text-embedding-3")
        mock_cls.assert_called_once_with(
            api_key="test-key",
            model="text-embedding-3",
        )


def test_build_query_embedder_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_ollama": mock_module}):
        _build_query_embedder(provider="ollama", model="mxbai")
        mock_module.OllamaEmbeddings.assert_called_once_with(
            model="mxbai", base_url=ChainConfig().ollama_base_url
        )


def test_build_query_embedder_huggingface(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"langchain_huggingface": mock_module}):
        _build_query_embedder(provider="huggingface", model="bge")
        mock_module.HuggingFaceEmbeddings.assert_called_once_with(model_name="bge")


def test_build_query_embedder_unsupported() -> None:
    with pytest.raises(ValueError, match="Unsupported embedding provider"):
        _build_query_embedder(provider="unknown", model="model")  # type: ignore
