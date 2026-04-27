"""Tests for vector store providers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from chain.config import ChainConfig
from chain.rag.vector_store import (
    ChromaDBVectorSearchProvider,
    EmbeddingModelMetadata,
    PGVectorSearchProvider,
    PineconeVectorSearchProvider,
    QdrantVectorSearchProvider,
    _cast_payload,
    _required,
    create_vector_search_provider,
)


@pytest.fixture
def mock_embedding_model() -> EmbeddingModelMetadata:
    return EmbeddingModelMetadata(name="test-model", dimension=128)


def test_required_helper() -> None:
    assert _required("value", "ENV_VAR") == "value"
    with pytest.raises(ValueError, match="ENV_VAR is required"):
        _required(None, "ENV_VAR")
    with pytest.raises(ValueError, match="ENV_VAR is required"):
        _required("", "ENV_VAR")


def test_cast_payload() -> None:
    assert _cast_payload('{"a": 1}') == {"a": 1}
    assert _cast_payload({"a": 1}) == {"a": 1}


def test_qdrant_provider(
    monkeypatch: pytest.MonkeyPatch, mock_embedding_model: EmbeddingModelMetadata
) -> None:
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_API_KEY_RO", "test-key")
    config = ChainConfig(vector_store="qdrant")

    mock_qdrant_client = MagicMock()
    mock_module = MagicMock()
    mock_module.QdrantClient.return_value = mock_qdrant_client

    with patch.dict(sys.modules, {"qdrant_client": mock_module}):
        provider = QdrantVectorSearchProvider(config)
        mock_module.QdrantClient.assert_called_once_with(
            url="http://localhost:6333",
            api_key="test-key",
        )

        assert provider.target_name(mock_embedding_model) == "movies_test_model_128"

        mock_point = MagicMock()
        mock_point.payload = {"title": "Test Movie"}
        mock_point.score = 0.95
        mock_results = MagicMock()
        mock_results.points = [mock_point, MagicMock(payload=None)]  # testing point without payload
        mock_qdrant_client.query_points.return_value = mock_results

        hits = provider.search([0.1, 0.2], 5, mock_embedding_model)
        assert len(hits) == 1
        assert hits[0].payload == {"title": "Test Movie"}
        assert hits[0].score == 0.95
        mock_qdrant_client.query_points.assert_called_once_with(
            collection_name="movies_test_model_128",
            query=[0.1, 0.2],
            with_payload=True,
            limit=5,
        )


def test_qdrant_provider_uses_generic_vector_credentials() -> None:
    config = ChainConfig(
        vector_store="qdrant",
        qdrant_url=None,
        qdrant_api_key_ro=None,
        vector_store_url="http://localhost:6333",
        vector_store_api_key="generic-key",
    )

    mock_qdrant_client = MagicMock()
    mock_module = MagicMock()
    mock_module.QdrantClient.return_value = mock_qdrant_client

    with patch.dict(sys.modules, {"qdrant_client": mock_module}):
        QdrantVectorSearchProvider(config)

    mock_module.QdrantClient.assert_called_once_with(
        url="http://localhost:6333",
        api_key="generic-key",
    )


def test_chromadb_provider(
    monkeypatch: pytest.MonkeyPatch, mock_embedding_model: EmbeddingModelMetadata
) -> None:
    config = ChainConfig(vector_store="chromadb")

    mock_chromadb_client = MagicMock()
    mock_module = MagicMock()
    mock_module.PersistentClient.return_value = mock_chromadb_client

    with patch.dict(sys.modules, {"chromadb": mock_module}):
        provider = ChromaDBVectorSearchProvider(config)
        mock_module.PersistentClient.assert_called_once_with(path=config.chromadb_persist_path)

        mock_collection = MagicMock()
        mock_chromadb_client.get_or_create_collection.return_value = mock_collection

        # Test successful query
        mock_collection.query.return_value = {
            "metadatas": [[{"title": "Movie 1"}, None, {"title": "Movie 2"}]],
            "distances": [[0.1, 0.2, 0.3]],
        }

        hits = provider.search([0.1, 0.2], 5, mock_embedding_model)
        assert len(hits) == 2
        assert hits[0].payload == {"title": "Movie 1"}
        assert hits[0].score == 0.9
        assert hits[1].payload == {"title": "Movie 2"}
        assert hits[1].score == 0.7

        # Test empty query
        mock_collection.query.return_value = {"metadatas": []}
        assert provider.search([0.1, 0.2], 5, mock_embedding_model) == []

        # Test missing distance
        mock_collection.query.return_value = {
            "metadatas": [[{"title": "Movie 3"}]],
            "distances": [],
        }
        hits = provider.search([0.1, 0.2], 5, mock_embedding_model)
        assert len(hits) == 1
        assert hits[0].score is None


def test_pinecone_provider(
    monkeypatch: pytest.MonkeyPatch, mock_embedding_model: EmbeddingModelMetadata
) -> None:
    monkeypatch.setenv("PINECONE_API_KEY", "pc-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "test-index")
    monkeypatch.delenv("PINECONE_INDEX_HOST", raising=False)
    config = ChainConfig(vector_store="pinecone")

    mock_pinecone_client = MagicMock()
    mock_module = MagicMock()
    mock_module.Pinecone.return_value = mock_pinecone_client

    with patch.dict(sys.modules, {"pinecone": mock_module}):
        provider = PineconeVectorSearchProvider(config)
        mock_module.Pinecone.assert_called_once_with(
            api_key="pc-key",
        )

        mock_index = MagicMock()
        mock_pinecone_client.Index.return_value = mock_index

        assert provider.target_name(mock_embedding_model) == "movies_test_model_128"

        mock_match1 = {"metadata": {"title": "Movie 1"}, "score": 0.8}
        mock_match2 = {"metadata": {"title": "Movie 2"}, "score": 0.7}
        mock_match3 = {"metadata": None, "score": 0.5}

        mock_response = MagicMock()
        mock_response.matches = [mock_match1, mock_match2, mock_match3]
        mock_index.query.return_value = mock_response

        hits = provider.search([0.1, 0.2], 5, mock_embedding_model)
        assert len(hits) == 2
        assert hits[0].payload == {"title": "Movie 1"}
        assert hits[0].score == 0.8
        assert hits[1].payload == {"title": "Movie 2"}
        assert hits[1].score == 0.7

        mock_pinecone_client.Index.assert_called_once_with("test-index")

        # test cached index
        provider.search([0.1, 0.2], 5, mock_embedding_model)
        mock_pinecone_client.Index.assert_called_once_with("test-index")  # Call count stays 1

        # Test host configuration
        monkeypatch.setenv("PINECONE_INDEX_HOST", "https://test-host")
        config2 = ChainConfig(vector_store="pinecone")
        provider2 = PineconeVectorSearchProvider(config2)
        provider2._client.Index.return_value = mock_index
        mock_index.query.return_value = MagicMock(matches=[])
        provider2.search([0.1, 0.2], 5, mock_embedding_model)
        provider2._client.Index.assert_called_with(host="https://test-host")


def test_pinecone_provider_uses_generic_vector_api_key() -> None:
    config = ChainConfig(vector_store="pinecone", vector_store_api_key="generic-key")

    mock_module = MagicMock()

    with patch.dict(sys.modules, {"pinecone": mock_module}):
        PineconeVectorSearchProvider(config)

    mock_module.Pinecone.assert_called_once_with(api_key="generic-key")


def test_import_errors() -> None:
    config = ChainConfig()

    with (
        patch.dict(sys.modules, {"chromadb": None}),
        pytest.raises(RuntimeError, match="optional 'chromadb' dependency"),
    ):
        ChromaDBVectorSearchProvider(config)

    with (
        patch.dict(sys.modules, {"pinecone": None}),
        pytest.raises(RuntimeError, match="optional 'pinecone' dependency"),
    ):
        PineconeVectorSearchProvider(config)

    with (
        patch.dict(sys.modules, {"psycopg": None}),
        pytest.raises(RuntimeError, match="optional 'pgvector' dependency"),
    ):
        PGVectorSearchProvider(config)


def test_pgvector_provider(
    monkeypatch: pytest.MonkeyPatch, mock_embedding_model: EmbeddingModelMetadata
) -> None:
    monkeypatch.setenv(
        "PGVECTOR_DSN",
        "postgres://user:pass@localhost/db",
    )
    config = ChainConfig(vector_store="pgvector")

    mock_psycopg_module = MagicMock()
    mock_pgvector_module = MagicMock()

    mock_conn = MagicMock()
    mock_psycopg_module.connect.return_value = mock_conn
    mock_conn.__enter__.return_value = mock_conn

    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch.dict(
        sys.modules, {"psycopg": mock_psycopg_module, "pgvector.psycopg": mock_pgvector_module}
    ):
        provider = PGVectorSearchProvider(config)

        assert provider.target_name(mock_embedding_model) == "movies_test_model_128"
        assert provider._table_name(mock_embedding_model) == "public_movies_test_model_128"

        mock_cursor.fetchall.return_value = [
            ('{"title": "Movie 1"}', 0.9),
            ({"title": "Movie 2"}, 0.8),
        ]

        hits = provider.search([0.1, 0.2], 5, mock_embedding_model)
        assert len(hits) == 2
        assert hits[0].payload == {"title": "Movie 1"}
        assert hits[0].score == 0.9
        assert hits[1].payload == {"title": "Movie 2"}
        assert hits[1].score == 0.8

        mock_psycopg_module.connect.assert_called_once_with("postgres://user:pass@localhost/db")
        mock_pgvector_module.register_vector.assert_called_once_with(mock_conn)
        mock_cursor.execute.assert_called_once()


def test_pgvector_provider_uses_generic_vector_store_url() -> None:
    config = ChainConfig(vector_store="pgvector", vector_store_url="postgres://user:pass@host/db")

    mock_psycopg_module = MagicMock()
    mock_pgvector_module = MagicMock()
    mock_conn = MagicMock()
    mock_psycopg_module.connect.return_value = mock_conn

    with patch.dict(
        sys.modules,
        {"psycopg": mock_psycopg_module, "pgvector.psycopg": mock_pgvector_module},
    ):
        provider = PGVectorSearchProvider(config)
        provider._connect()

    mock_psycopg_module.connect.assert_called_once_with("postgres://user:pass@host/db")
    mock_pgvector_module.register_vector.assert_called_once_with(mock_conn)


def test_create_vector_search_provider_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_STORE", "chromadb")
    config = ChainConfig()
    mock_provider = MagicMock()
    with patch.dict("chain.rag.vector_store._VECTOR_STORES", {"chromadb": mock_provider}):
        create_vector_search_provider(config)
        mock_provider.assert_called_once_with(config)

    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "http://a")
    monkeypatch.setenv("QDRANT_API_KEY_RO", "b")
    mock_provider2 = MagicMock()
    with patch.dict("chain.rag.vector_store._VECTOR_STORES", {"qdrant": mock_provider2}):
        config2 = ChainConfig()
        create_vector_search_provider(config2)
        mock_provider2.assert_called_once_with(config2)

    monkeypatch.setenv("VECTOR_STORE", "pinecone")
    monkeypatch.setenv("PINECONE_API_KEY", "a")
    mock_provider3 = MagicMock()
    with patch.dict("chain.rag.vector_store._VECTOR_STORES", {"pinecone": mock_provider3}):
        config3 = ChainConfig()
        create_vector_search_provider(config3)
        mock_provider3.assert_called_once_with(config3)

    monkeypatch.setenv("VECTOR_STORE", "pgvector")
    monkeypatch.setenv("PGVECTOR_DSN", "a")
    mock_provider4 = MagicMock()
    with patch.dict("chain.rag.vector_store._VECTOR_STORES", {"pgvector": mock_provider4}):
        config4 = ChainConfig()
        create_vector_search_provider(config4)
        mock_provider4.assert_called_once_with(config4)
