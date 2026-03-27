"""Embedding client abstraction and provider adapters (§7.1, §1.6).

Supports OpenAI and Ollama. All adapters implement the EmbeddingClient Protocol
so they can be swapped without changing call sites.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

from src.utils.constants import DEFAULT_EMBEDDING_BATCH_SIZE
from src.utils.errors import EmbeddingError, TransientError
from src.utils.logging import get_logger

logger = get_logger(__name__)

# ─── Protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class EmbeddingClient(Protocol):
    """Interface for embedding providers."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: List of strings to embed. Must be non-empty.

        Returns:
            List of embedding vectors, one per input text.
        """
        ...


# ─── Retry helper ─────────────────────────────────────────────────────────────


def _with_retry(fn: "callable", max_retries: int = 3, base_delay: float = 1.0) -> "callable":
    """Return a wrapper that retries fn on TransientError with exponential backoff."""

    def wrapper(*args: object, **kwargs: object) -> object:
        for attempt in range(max_retries):
            try:
                return fn(*args, **kwargs)
            except TransientError as exc:
                if attempt == max_retries - 1:
                    raise
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Embedding transient error — retrying",
                    extra={"attempt": attempt + 1, "delay_s": delay, "error": str(exc)},
                )
                time.sleep(delay)
        return None  # unreachable

    return wrapper


# ─── OpenAI adapter ───────────────────────────────────────────────────────────


class OpenAIEmbeddingClient:
    """Embedding adapter for OpenAI text-embedding models.

    Args:
        model: Model name (e.g. "text-embedding-3-small").
        api_key: OpenAI API key. Reads from OPENAI_API_KEY env if not provided.
        batch_size: Max texts per API call.
        max_retries: Retry attempts on transient errors.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
        max_retries: int = 3,
    ) -> None:
        try:
            from openai import OpenAI  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("openai package required: pip install openai") from exc

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._batch_size = batch_size
        self._max_retries = max_retries

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in sub-batches, retrying on rate limits.

        Args:
            texts: Texts to embed.

        Returns:
            Embedding vectors.

        Raises:
            EmbeddingError: On non-transient API errors.
        """
        all_vectors: list[list[float]] = []

        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors = self._embed_one_batch(batch)
            all_vectors.extend(vectors)

        return all_vectors

    def _embed_one_batch(self, texts: list[str]) -> list[list[float]]:
        import httpx

        for attempt in range(self._max_retries):
            try:
                response = self._client.embeddings.create(model=self._model, input=texts)
                return [item.embedding for item in response.data]
            except Exception as exc:
                error_str = str(exc)
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < self._max_retries - 1:
                        delay = 2.0 ** attempt
                        logger.warning("Rate limited — retrying", extra={"delay_s": delay})
                        time.sleep(delay)
                        continue
                    raise TransientError(f"Rate limit not resolved after {self._max_retries} attempts") from exc
                raise EmbeddingError(f"OpenAI embedding error: {exc}") from exc
        return []  # unreachable


# ─── Ollama adapter ───────────────────────────────────────────────────────────


class OllamaEmbeddingClient:
    """Embedding adapter for Ollama local models.

    Args:
        model: Model name (e.g. "nomic-embed-text").
        base_url: Ollama API base URL.
        batch_size: Max texts per call (Ollama processes one at a time; batched serially).
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._batch_size = batch_size

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts one at a time via Ollama's /api/embeddings endpoint."""
        import httpx

        vectors: list[list[float]] = []
        for text in texts:
            try:
                response = httpx.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                    timeout=60.0,
                )
                response.raise_for_status()
                vectors.append(response.json()["embedding"])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 503):
                    raise TransientError(f"Ollama temporarily unavailable: {exc}") from exc
                raise EmbeddingError(f"Ollama embedding error: {exc}") from exc
            except httpx.RequestError as exc:
                raise TransientError(f"Ollama connection error: {exc}") from exc

        return vectors


# ─── Factory ──────────────────────────────────────────────────────────────────


def make_embedding_client(provider: str, model: str, **kwargs: object) -> EmbeddingClient:
    """Instantiate the correct EmbeddingClient for the given provider.

    Args:
        provider: "openai" or "ollama".
        model: Model name.
        **kwargs: Additional constructor arguments.

    Returns:
        EmbeddingClient instance.

    Raises:
        ValueError: For unknown provider names.
    """
    if provider == "openai":
        return OpenAIEmbeddingClient(model=model, **kwargs)  # type: ignore[arg-type]
    if provider == "ollama":
        return OllamaEmbeddingClient(model=model, **kwargs)  # type: ignore[arg-type]
    raise ValueError(f"Unknown embedding provider '{provider}'. Choose 'openai' or 'ollama'.")
