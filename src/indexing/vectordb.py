"""ChromaDB vector database integration (§7.1, §1.6).

Provides a VectorDBClient interface and a ChromaDB implementation.
All writes are batched per-file granularity — no partial writes.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.indexing.chunker import Chunk
from src.utils.errors import VectorDBError
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ─── Protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class VectorDBClient(Protocol):
    """Interface for vector database backends."""

    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Store chunks and their embedding vectors."""
        ...

    def query(
        self,
        vector: list[float],
        top_k: int = 20,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic similarity search.

        Returns:
            List of result dicts with keys: id, text, metadata, distance.
        """
        ...

    def delete_by_file(self, file_path: str) -> None:
        """Remove all chunks belonging to a specific file."""
        ...

    def count(self) -> int:
        """Return the total number of stored chunks."""
        ...


# ─── ChromaDB implementation ──────────────────────────────────────────────────


class ChromaDBClient:
    """ChromaDB vector store for local development.

    Args:
        persist_directory: Directory where ChromaDB persists data.
        collection_name: Name of the ChromaDB collection.
    """

    def __init__(self, persist_directory: str, collection_name: str = "codebase") -> None:
        try:
            import chromadb  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("chromadb package required: pip install chromadb") from exc

        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB collection ready",
            extra={"collection": collection_name, "path": persist_directory},
        )

    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Store or update chunks with their embedding vectors.

        Uses upsert so re-indexing a file replaces its old chunks.

        Args:
            chunks: Chunk objects produced by the chunker.
            vectors: Corresponding embedding vectors (same length as chunks).

        Raises:
            VectorDBError: If the write fails.
            ValueError: If chunks and vectors lengths differ.
        """
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks ({len(chunks)}) and vectors ({len(vectors)}) must have the same length"
            )
        if not chunks:
            return

        ids = [f"{c.file_path}::{c.chunk_index}" for c in chunks]
        texts = [c.text for c in chunks]
        metadatas = [
            {
                "file_path": c.file_path,
                "language": c.language,
                "symbol_name": c.symbol_name,
                "symbol_type": c.symbol_type,
                "chunk_method": c.chunk_method,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "estimated_tokens": c.estimated_tokens,
                "context_before": c.context_before[:200],  # truncate for storage
                "context_after": c.context_after[:200],
            }
            for c in chunks
        ]

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=vectors,
                documents=texts,
                metadatas=metadatas,
            )
        except Exception as exc:
            raise VectorDBError(f"ChromaDB upsert failed: {exc}") from exc

    def query(
        self,
        vector: list[float],
        top_k: int = 20,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a similarity search and return the top-K results.

        Args:
            vector: Query embedding vector.
            top_k: Number of results to return.
            where: Optional metadata filter (ChromaDB where clause).

        Returns:
            List of dicts with keys: id, text, metadata, distance.
        """
        try:
            kwargs: dict[str, Any] = {
                "query_embeddings": [vector],
                "n_results": min(top_k, self.count() or 1),
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where

            result = self._collection.query(**kwargs)
        except Exception as exc:
            raise VectorDBError(f"ChromaDB query failed: {exc}") from exc

        results: list[dict[str, Any]] = []
        if not result["ids"] or not result["ids"][0]:
            return results

        for doc_id, text, meta, dist in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            results.append({"id": doc_id, "text": text, "metadata": meta, "distance": dist})

        return results

    def delete_by_file(self, file_path: str) -> None:
        """Delete all chunks belonging to a file.

        Args:
            file_path: Relative file path matching the stored metadata.
        """
        try:
            self._collection.delete(where={"file_path": file_path})
        except Exception as exc:
            raise VectorDBError(f"ChromaDB delete failed for '{file_path}': {exc}") from exc

    def count(self) -> int:
        """Return the total chunk count in the collection."""
        return self._collection.count()
