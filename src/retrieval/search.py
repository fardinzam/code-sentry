"""Hybrid retrieval: vector similarity + keyword search (§7.2, §1.7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.indexing.embedder import EmbeddingClient
from src.indexing.vectordb import VectorDBClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """A single retrieval result.

    Attributes:
        text: Chunk text.
        file_path: Relative file path.
        symbol_name: Function/class name if available.
        start_line: 1-indexed start line.
        end_line: 1-indexed end line.
        score: Combined relevance score 0.0–1.0 (higher = more relevant).
        metadata: Full metadata dict from the vector store.
    """

    text: str
    file_path: str
    symbol_name: str
    start_line: int
    end_line: int
    score: float
    metadata: dict[str, Any]


class HybridSearcher:
    """Combines vector similarity search with keyword/symbol matching.

    The final score is: (1 - keyword_weight) * vector_score + keyword_weight * keyword_score

    Args:
        vector_db: Vector database client.
        embedder: Embedding client for query vectorization.
        top_k: Maximum results to return.
        keyword_weight: Fraction [0, 1] given to keyword score.
        similarity_threshold: Minimum vector score to include a result.
    """

    def __init__(
        self,
        vector_db: VectorDBClient,
        embedder: EmbeddingClient,
        top_k: int = 20,
        keyword_weight: float = 0.3,
        similarity_threshold: float = 0.3,
    ) -> None:
        self._vector_db = vector_db
        self._embedder = embedder
        self._top_k = top_k
        self._kw_weight = keyword_weight
        self._threshold = similarity_threshold

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        """Retrieve the most relevant chunks for a query.

        Runs vector search and keyword search in parallel (sequentially for now),
        merges and deduplicates results, then ranks by combined score.

        Args:
            query: Natural language or code query string.
            top_k: Override the instance top_k for this call.

        Returns:
            Ordered list of SearchResult objects, most relevant first.
        """
        k = top_k or self._top_k

        # Vector search
        vector_results = self._vector_search(query, k * 2)

        # Keyword search
        keyword_results = self._keyword_search(query, k * 2)

        # Deduplicate: merge by chunk id (file_path::chunk_index)
        merged: dict[str, SearchResult] = {}
        for result in vector_results:
            key = f"{result.file_path}::{result.start_line}"
            merged[key] = result

        for kw_result in keyword_results:
            key = f"{kw_result.file_path}::{kw_result.start_line}"
            if key in merged:
                # Boost existing result's score with keyword signal
                existing = merged[key]
                merged[key] = SearchResult(
                    text=existing.text,
                    file_path=existing.file_path,
                    symbol_name=existing.symbol_name,
                    start_line=existing.start_line,
                    end_line=existing.end_line,
                    score=min(1.0, existing.score + self._kw_weight * kw_result.score),
                    metadata=existing.metadata,
                )
            else:
                merged[key] = kw_result

        ranked = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        filtered = [r for r in ranked if r.score >= self._threshold]
        return filtered[:k]

    def _vector_search(self, query: str, k: int) -> list[SearchResult]:
        """Run semantic similarity search."""
        try:
            vectors = self._embedder.embed_batch([query])
            raw = self._vector_db.query(vectors[0], top_k=k)
        except Exception as exc:
            logger.warning("Vector search failed", extra={"error": str(exc)})
            return []

        results: list[SearchResult] = []
        for item in raw:
            meta = item.get("metadata", {})
            # ChromaDB distance is cosine distance [0, 2]; convert to similarity [0, 1]
            distance = item.get("distance", 1.0)
            vector_score = max(0.0, 1.0 - (distance / 2.0))
            combined_score = (1.0 - self._kw_weight) * vector_score
            results.append(
                SearchResult(
                    text=item.get("text", ""),
                    file_path=meta.get("file_path", ""),
                    symbol_name=meta.get("symbol_name", ""),
                    start_line=int(meta.get("start_line", 0)),
                    end_line=int(meta.get("end_line", 0)),
                    score=combined_score,
                    metadata=meta,
                )
            )
        return results

    def _keyword_search(self, query: str, k: int) -> list[SearchResult]:
        """Simple keyword match against metadata (function names, file paths).

        ChromaDB supports a `where_document` filter for text contains.
        We use the $contains operator for a basic substring match.
        """
        # Extract potential symbol/file tokens from the query
        tokens = [t.strip("'\".()[]") for t in query.split() if len(t) > 3]
        if not tokens:
            return []

        results: list[SearchResult] = []
        seen: set[str] = set()

        for token in tokens[:3]:  # limit to top 3 tokens to avoid excessive queries
            try:
                raw = self._vector_db.query(
                    vector=[0.0] * 1536,  # dummy vector; we use where_document filter
                    top_k=k,
                    where={"$or": [
                        {"file_path": {"$contains": token}},
                        {"symbol_name": {"$contains": token}},
                    ]},
                )
            except Exception:
                # Not all VectorDB backends support metadata text search; skip
                continue

            for item in raw:
                meta = item.get("metadata", {})
                key = meta.get("file_path", "") + str(meta.get("start_line", ""))
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    SearchResult(
                        text=item.get("text", ""),
                        file_path=meta.get("file_path", ""),
                        symbol_name=meta.get("symbol_name", ""),
                        start_line=int(meta.get("start_line", 0)),
                        end_line=int(meta.get("end_line", 0)),
                        score=self._kw_weight * 0.8,  # keyword hits get 80% of the keyword weight
                        metadata=meta,
                    )
                )

        return results[:k]
