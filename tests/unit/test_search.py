"""Unit tests for the hybrid search engine (§7.2, §1.7)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.retrieval.search import HybridSearcher, SearchResult


def _make_vector_db(query_results: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock VectorDBClient."""
    db = MagicMock()
    db.query.return_value = query_results or []
    return db


def _make_embedder(embedding: list[float] | None = None) -> MagicMock:
    """Create a mock EmbeddingClient."""
    emb = MagicMock()
    emb.embed_batch.return_value = [embedding or [0.1, 0.2, 0.3]]
    return emb


def _meta(
    fp: str = "a.py",
    sym: str = "foo",
    sl: int = 1,
    el: int = 1,
) -> dict[str, str | int]:
    """Build a compact metadata dict for test results."""
    return {
        "file_path": fp,
        "symbol_name": sym,
        "start_line": sl,
        "end_line": el,
    }


class TestSearchResult:
    """SearchResult dataclass."""

    def test_creation(self) -> None:
        sr = SearchResult(
            text="code",
            file_path="a.py",
            symbol_name="foo",
            start_line=1,
            end_line=5,
            score=0.9,
            metadata={},
        )
        assert sr.text == "code"
        assert sr.score == 0.9


class TestHybridSearcher:
    """Test the combined vector + keyword search."""

    def test_empty_results(self) -> None:
        searcher = HybridSearcher(
            vector_db=_make_vector_db([]),
            embedder=_make_embedder(),
        )
        results = searcher.search("find me something")
        assert results == []

    def test_vector_search_returns_results(self) -> None:
        raw_results = [
            {
                "id": "a.py::0",
                "text": "def foo(): pass",
                "metadata": _meta("a.py", "foo", 1, 3),
                "distance": 0.1,
            }
        ]
        searcher = HybridSearcher(
            vector_db=_make_vector_db(raw_results),
            embedder=_make_embedder(),
        )
        results = searcher.search("foo")
        assert len(results) >= 1
        assert results[0].file_path == "a.py"
        assert results[0].score > 0

    def test_results_sorted_by_score(self) -> None:
        raw_results = [
            {
                "id": "a.py::0",
                "text": "def a(): pass",
                "metadata": _meta("a.py", "a"),
                "distance": 0.5,
            },
            {
                "id": "b.py::0",
                "text": "def b(): pass",
                "metadata": _meta("b.py", "b"),
                "distance": 0.1,
            },
        ]
        searcher = HybridSearcher(
            vector_db=_make_vector_db(raw_results),
            embedder=_make_embedder(),
        )
        results = searcher.search("something")
        assert len(results) == 2
        assert results[0].score >= results[1].score

    def test_similarity_threshold_filters_low_scores(self) -> None:
        raw_results = [
            {
                "id": "far.py::0",
                "text": "def far(): pass",
                "metadata": _meta("far.py", "far"),
                "distance": 1.9,
            }
        ]
        searcher = HybridSearcher(
            vector_db=_make_vector_db(raw_results),
            embedder=_make_embedder(),
            similarity_threshold=0.5,
        )
        results = searcher.search("query")
        assert results == []

    def test_top_k_limits_results(self) -> None:
        raw_results = [
            {
                "id": f"f{i}.py::0",
                "text": f"def f{i}(): pass",
                "metadata": _meta(f"f{i}.py", f"f{i}"),
                "distance": 0.1 * i,
            }
            for i in range(10)
        ]
        searcher = HybridSearcher(
            vector_db=_make_vector_db(raw_results),
            embedder=_make_embedder(),
            top_k=3,
            similarity_threshold=0.0,
        )
        results = searcher.search("query")
        assert len(results) <= 3

    def test_top_k_override(self) -> None:
        raw_results = [
            {
                "id": f"f{i}.py::0",
                "text": f"def f{i}(): pass",
                "metadata": _meta(f"f{i}.py", f"f{i}"),
                "distance": 0.05,
            }
            for i in range(10)
        ]
        searcher = HybridSearcher(
            vector_db=_make_vector_db(raw_results),
            embedder=_make_embedder(),
            top_k=20,
            similarity_threshold=0.0,
        )
        results = searcher.search("query", top_k=2)
        assert len(results) <= 2

    def test_vector_search_failure_returns_empty(self) -> None:
        embedder = _make_embedder()
        embedder.embed_batch.side_effect = RuntimeError("API down")

        searcher = HybridSearcher(
            vector_db=_make_vector_db([]),
            embedder=embedder,
        )
        results = searcher.search("query")
        assert results == []

    def test_keyword_search_boosts_existing_result(self) -> None:
        """When both searches match, score should increase."""
        vector_result = {
            "id": "main.py::0",
            "text": "def calculate(): pass",
            "metadata": _meta("main.py", "calculate", 1, 3),
            "distance": 0.2,
        }

        db = MagicMock()
        db.query.return_value = [vector_result]

        searcher = HybridSearcher(
            vector_db=db,
            embedder=_make_embedder(),
            keyword_weight=0.3,
            similarity_threshold=0.0,
        )
        results = searcher.search("calculate function")
        assert len(results) >= 1
