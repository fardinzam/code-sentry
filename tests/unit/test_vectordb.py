"""Unit tests for the ChromaDB vector database client (§7.1, §1.6)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.indexing.chunker import Chunk
from src.indexing.vectordb import ChromaDBClient, VectorDBClient
from src.utils.errors import VectorDBError


def _make_chunk(
    text: str = "hello world",
    file_path: str = "src/main.py",
    chunk_index: int = 0,
) -> Chunk:
    """Create a test Chunk."""
    return Chunk(
        text=text,
        file_path=file_path,
        language="python",
        chunk_index=chunk_index,
        start_line=1,
        end_line=10,
        symbol_name="my_func",
        symbol_type="function",
        chunk_method="ast",
    )


class TestVectorDBProtocol:
    """ChromaDBClient must satisfy VectorDBClient protocol."""

    def test_chromadb_is_vectordb_client(self) -> None:
        # Create a bare instance without __init__
        client = ChromaDBClient.__new__(ChromaDBClient)
        assert isinstance(client, VectorDBClient)


class TestChromaDBClientUpsert:
    """Test upsert_chunks via mocked chromadb."""

    def _make_client(self, tmp_path: Any) -> ChromaDBClient:
        return ChromaDBClient(
            persist_directory=str(tmp_path / "vectordb"),
            collection_name="test",
        )

    def test_upsert_stores_chunks(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)
        chunk = _make_chunk()
        vectors = [[0.1, 0.2, 0.3]]

        # Patch the collection's upsert to track calls
        with patch.object(client._collection, "upsert") as mock_upsert:
            client.upsert_chunks([chunk], vectors)

        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args
        assert len(call_kwargs[1]["ids"]) == 1
        assert call_kwargs[1]["ids"][0] == "src/main.py::0"

    def test_upsert_mismatched_lengths_raises_value_error(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)
        chunk = _make_chunk()

        with pytest.raises(ValueError, match="same length"):
            client.upsert_chunks([chunk], [[0.1], [0.2]])

    def test_upsert_empty_chunks_is_noop(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)

        with patch.object(client._collection, "upsert") as mock_upsert:
            client.upsert_chunks([], [])

        mock_upsert.assert_not_called()

    def test_upsert_failure_raises_vectordb_error(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)
        chunk = _make_chunk()

        with (
            patch.object(
                client._collection, "upsert", side_effect=RuntimeError("disk full")
            ),
            pytest.raises(VectorDBError, match="ChromaDB upsert failed"),
        ):
            client.upsert_chunks([chunk], [[0.1]])


class TestChromaDBClientQuery:
    """Test query via mocked chromadb."""

    def _make_client(self, tmp_path: Any) -> ChromaDBClient:
        return ChromaDBClient(
            persist_directory=str(tmp_path / "vectordb"),
            collection_name="test",
        )

    def test_query_returns_results(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)
        mock_result: dict[str, Any] = {
            "ids": [["id1", "id2"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"file_path": "a.py"}, {"file_path": "b.py"}]],
            "distances": [[0.1, 0.5]],
        }

        with (
            patch.object(client._collection, "query", return_value=mock_result),
            patch.object(client, "count", return_value=10),
        ):
            results = client.query([0.1, 0.2], top_k=5)

        assert len(results) == 2
        assert results[0]["id"] == "id1"
        assert results[0]["text"] == "doc1"
        assert results[0]["distance"] == 0.1

    def test_query_empty_results(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)
        mock_result: dict[str, Any] = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        with (
            patch.object(client._collection, "query", return_value=mock_result),
            patch.object(client, "count", return_value=0),
        ):
            results = client.query([0.1, 0.2], top_k=5)

        assert results == []

    def test_query_failure_raises_vectordb_error(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)

        with (
            patch.object(
                client._collection, "query", side_effect=RuntimeError("timeout")
            ),
            patch.object(client, "count", return_value=10),
            pytest.raises(VectorDBError, match="ChromaDB query failed"),
        ):
            client.query([0.1], top_k=5)

    def test_query_with_where_filter(self, tmp_path: Any) -> None:
        client = self._make_client(tmp_path)
        mock_result: dict[str, Any] = {
            "ids": [["id1"]],
            "documents": [["code"]],
            "metadatas": [[{"file_path": "x.py"}]],
            "distances": [[0.2]],
        }

        with (
            patch.object(client._collection, "query", return_value=mock_result) as mock_q,
            patch.object(client, "count", return_value=5),
        ):
            client.query([0.1], top_k=5, where={"file_path": "x.py"})

        # Verify where was passed through
        assert mock_q.call_args[1]["where"] == {"file_path": "x.py"}


class TestChromaDBClientDelete:
    """Test delete_by_file."""

    def test_delete_calls_collection(self, tmp_path: Any) -> None:
        client = ChromaDBClient(
            persist_directory=str(tmp_path / "vectordb"),
            collection_name="test",
        )

        with patch.object(client._collection, "delete") as mock_del:
            client.delete_by_file("src/main.py")

        mock_del.assert_called_once_with(where={"file_path": "src/main.py"})

    def test_delete_failure_raises_vectordb_error(self, tmp_path: Any) -> None:
        client = ChromaDBClient(
            persist_directory=str(tmp_path / "vectordb"),
            collection_name="test",
        )

        with (
            patch.object(
                client._collection, "delete", side_effect=RuntimeError("err")
            ),
            pytest.raises(VectorDBError, match="ChromaDB delete failed"),
        ):
            client.delete_by_file("src/main.py")


class TestChromaDBCount:
    """Test count method."""

    def test_count_returns_integer(self, tmp_path: Any) -> None:
        client = ChromaDBClient(
            persist_directory=str(tmp_path / "vectordb"),
            collection_name="test",
        )

        with patch.object(client._collection, "count", return_value=42):
            assert client.count() == 42
