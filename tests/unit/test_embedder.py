"""Unit tests for the embedding client adapters (§7.1, §1.6)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.indexing.embedder import (
    EmbeddingClient,
    OllamaEmbeddingClient,
    OpenAIEmbeddingClient,
    _with_retry,
    make_embedding_client,
)
from src.utils.errors import EmbeddingError, TransientError

# ─── Protocol compliance ─────────────────────────────────────────────────────


class TestEmbeddingProtocol:
    """Verify that concrete clients satisfy the EmbeddingClient protocol."""

    def test_openai_client_is_embedding_client(self) -> None:
        client = OpenAIEmbeddingClient.__new__(OpenAIEmbeddingClient)
        assert isinstance(client, EmbeddingClient)

    def test_ollama_client_is_embedding_client(self) -> None:
        client = OllamaEmbeddingClient.__new__(OllamaEmbeddingClient)
        assert isinstance(client, EmbeddingClient)


# ─── _with_retry ─────────────────────────────────────────────────────────────


class TestWithRetry:
    """Retry wrapper behaviour."""

    def test_no_error_returns_immediately(self) -> None:
        fn = MagicMock(return_value=42)
        wrapped = _with_retry(fn, max_retries=3, base_delay=0.0)
        result = wrapped("a", b="c")
        assert result == 42
        fn.assert_called_once_with("a", b="c")

    def test_retries_on_transient_error(self) -> None:
        fn = MagicMock(side_effect=[TransientError("boom"), "ok"])
        wrapped = _with_retry(fn, max_retries=3, base_delay=0.0)
        result = wrapped()
        assert result == "ok"
        assert fn.call_count == 2

    def test_raises_after_max_retries(self) -> None:
        fn = MagicMock(side_effect=TransientError("fail"))
        wrapped = _with_retry(fn, max_retries=2, base_delay=0.0)
        with pytest.raises(TransientError):
            wrapped()
        assert fn.call_count == 2


# ─── OpenAIEmbeddingClient ───────────────────────────────────────────────────


class TestOpenAIEmbeddingClient:
    """Test the OpenAI embedding adapter."""

    def _make_client(self) -> OpenAIEmbeddingClient:
        return OpenAIEmbeddingClient(model="text-embedding-3-small", api_key="test-key")

    def test_embed_batch_returns_vectors(self) -> None:
        client = self._make_client()

        mock_data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_response = MagicMock(data=mock_data)

        with patch.object(client._client.embeddings, "create", return_value=mock_response):
            result = client.embed_batch(["hello"])

        assert result == [[0.1, 0.2, 0.3]]

    def test_embed_batch_handles_multiple_batches(self) -> None:
        client = OpenAIEmbeddingClient(
            model="text-embedding-3-small", api_key="test-key", batch_size=2
        )

        mock_data_1 = [MagicMock(embedding=[0.1]), MagicMock(embedding=[0.2])]
        mock_data_2 = [MagicMock(embedding=[0.3])]

        call_count = [0]

        def fake_create(**kwargs: object) -> MagicMock:
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(data=mock_data_1)
            return MagicMock(data=mock_data_2)

        with patch.object(client._client.embeddings, "create", side_effect=fake_create):
            result = client.embed_batch(["a", "b", "c"])

        assert len(result) == 3
        assert call_count[0] == 2

    def test_rate_limit_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = self._make_client()
        monkeypatch.setattr(time, "sleep", lambda _: None)

        call_count = [0]

        def fake_create(**kwargs: object) -> MagicMock:
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("429 rate limit exceeded")
            return MagicMock(data=[MagicMock(embedding=[0.5])])

        with patch.object(client._client.embeddings, "create", side_effect=fake_create):
            result = client.embed_batch(["test"])

        assert result == [[0.5]]
        assert call_count[0] == 3

    def test_rate_limit_exhausted_raises_transient_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = self._make_client()
        monkeypatch.setattr(time, "sleep", lambda _: None)

        with (
            patch.object(
                client._client.embeddings,
                "create",
                side_effect=Exception("429 rate limit"),
            ),
            pytest.raises(TransientError, match="Rate limit"),
        ):
            client.embed_batch(["test"])

    def test_non_rate_limit_error_raises_embedding_error(self) -> None:
        client = self._make_client()

        with (
            patch.object(
                client._client.embeddings,
                "create",
                side_effect=Exception("dimension mismatch"),
            ),
            pytest.raises(EmbeddingError, match="OpenAI embedding error"),
        ):
            client.embed_batch(["test"])


# ─── OllamaEmbeddingClient ──────────────────────────────────────────────────


class TestOllamaEmbeddingClient:
    """Test the Ollama embedding adapter."""

    def test_embed_batch_success(self) -> None:
        client = OllamaEmbeddingClient(model="nomic-embed-text")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2]}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            result = client.embed_batch(["hello"])

        assert result == [[0.1, 0.2]]
        mock_post.assert_called_once()

    def test_rate_limit_raises_transient_error(self) -> None:
        client = OllamaEmbeddingClient(model="nomic-embed-text")
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 429
        exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=mock_response)

        with patch("httpx.post", side_effect=exc), pytest.raises(TransientError):
            client.embed_batch(["hello"])

    def test_connection_error_raises_transient_error(self) -> None:
        client = OllamaEmbeddingClient(model="nomic-embed-text")
        import httpx

        exc = httpx.ConnectError("Connection refused")

        with patch("httpx.post", side_effect=exc), pytest.raises(TransientError):
            client.embed_batch(["hello"])

    def test_api_error_raises_embedding_error(self) -> None:
        client = OllamaEmbeddingClient(model="nomic-embed-text")
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 500
        exc = httpx.HTTPStatusError("server error", request=MagicMock(), response=mock_response)

        with patch("httpx.post", side_effect=exc), pytest.raises(EmbeddingError):
            client.embed_batch(["hello"])


# ─── Factory ─────────────────────────────────────────────────────────────────


class TestMakeEmbeddingClient:
    """Factory function tests."""

    def test_openai_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        client = make_embedding_client(provider="openai", model="text-embedding-3-small")
        assert isinstance(client, OpenAIEmbeddingClient)

    def test_ollama_provider(self) -> None:
        client = make_embedding_client(provider="ollama", model="nomic-embed-text")
        assert isinstance(client, OllamaEmbeddingClient)

    def test_unknown_provider_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            make_embedding_client(provider="unknown", model="x")
