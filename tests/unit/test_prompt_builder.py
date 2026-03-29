"""Unit tests for the prompt builder (§7.10.2)."""

from __future__ import annotations

from pathlib import Path

from src.retrieval.prompt_builder import (
    PromptBuilder,
    _build_file_tree,
    _count_tokens_approx,
    _format_search_results,
    _truncate_to_tokens,
)
from src.retrieval.search import SearchResult


def _make_result(
    text: str = "def foo(): pass",
    file_path: str = "src/main.py",
    score: float = 0.85,
) -> SearchResult:
    """Create a test SearchResult."""
    return SearchResult(
        text=text,
        file_path=file_path,
        symbol_name="foo",
        start_line=1,
        end_line=5,
        score=score,
        metadata={"file_path": file_path},
    )


# ─── Helper functions ────────────────────────────────────────────────────────


class TestCountTokensApprox:
    """Token estimation helper."""

    def test_empty_string(self) -> None:
        assert _count_tokens_approx("") == 1

    def test_short_string(self) -> None:
        assert _count_tokens_approx("hello") > 0

    def test_long_string(self) -> None:
        assert _count_tokens_approx("x" * 400) == 100


class TestTruncateToTokens:
    """Budget-aware text truncation."""

    def test_short_text_not_truncated(self) -> None:
        text = "short"
        assert _truncate_to_tokens(text, 100) == text

    def test_long_text_truncated(self) -> None:
        text = "x" * 1000
        result = _truncate_to_tokens(text, 10)  # ~40 chars
        assert len(result) < len(text)
        assert "[truncated]" in result


class TestFormatSearchResults:
    """Format chunks into labelled context blocks."""

    def test_formats_with_header(self) -> None:
        results = [_make_result()]
        formatted = _format_search_results(results)
        assert "### [1] src/main.py" in formatted
        assert "`foo`" in formatted
        assert "def foo(): pass" in formatted

    def test_empty_results(self) -> None:
        assert _format_search_results([]) == ""

    def test_multiple_results(self) -> None:
        results = [_make_result(file_path=f"src/{i}.py") for i in range(3)]
        formatted = _format_search_results(results)
        assert "### [1]" in formatted
        assert "### [3]" in formatted


class TestBuildFileTree:
    """File tree generation for structural context."""

    def test_includes_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1")
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "utils.py").write_text("y = 2")

        tree = _build_file_tree(tmp_path)
        assert "main.py" in tree
        assert "src/" in tree
        assert "utils.py" in tree

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / "main.py").write_text("x = 1")

        tree = _build_file_tree(tmp_path)
        assert ".git" not in tree

    def test_truncates_at_max_lines(self, tmp_path: Path) -> None:
        for i in range(100):
            (tmp_path / f"file_{i}.py").write_text(f"x = {i}")

        tree = _build_file_tree(tmp_path, max_lines=5)
        assert "truncated" in tree


# ─── PromptBuilder ────────────────────────────────────────────────────────────


class TestPromptBuilder:
    """Full prompt assembly pipeline."""

    def _make_builder(self, tmp_path: Path) -> PromptBuilder:
        (tmp_path / "main.py").write_text("x = 1")
        return PromptBuilder(
            system_prompt="You are a code reviewer.",
            repo_root=tmp_path,
            total_token_budget=100_000,
        )

    def test_build_returns_messages(self, tmp_path: Path) -> None:
        builder = self._make_builder(tmp_path)
        messages = builder.build(
            retrieved_chunks=[_make_result()],
            history=[],
            output_instructions="Return JSON.",
        )
        assert len(messages) >= 2  # system + user
        assert messages[0]["role"] == "system"
        assert "code reviewer" in messages[0]["content"]

    def test_build_includes_retrieved_context(self, tmp_path: Path) -> None:
        builder = self._make_builder(tmp_path)
        messages = builder.build(
            retrieved_chunks=[_make_result(text="unique_chunk_text")],
            history=[],
            output_instructions="Return JSON.",
        )
        all_content = " ".join(m["content"] for m in messages)
        assert "unique_chunk_text" in all_content

    def test_build_includes_remaining_iterations(self, tmp_path: Path) -> None:
        builder = self._make_builder(tmp_path)
        messages = builder.build(
            retrieved_chunks=[],
            history=[],
            output_instructions="",
            remaining_iterations=5,
        )
        assert "5" in messages[0]["content"]

    def test_build_includes_history(self, tmp_path: Path) -> None:
        builder = self._make_builder(tmp_path)
        history = [
            {"role": "user", "content": "Fix the bug in main.py"},
            {"role": "assistant", "content": "Done."},
        ]
        messages = builder.build(
            retrieved_chunks=[],
            history=history,
            output_instructions="",
        )
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    def test_build_truncates_large_chunks(self, tmp_path: Path) -> None:
        builder = PromptBuilder(
            system_prompt="Review.",
            repo_root=tmp_path,
            total_token_budget=100,  # Very small budget
        )
        (tmp_path / "a.py").write_text("x = 1")
        big_chunk = _make_result(text="x " * 10_000)
        messages = builder.build(
            retrieved_chunks=[big_chunk],
            history=[],
            output_instructions="Return JSON.",
        )
        # Should still produce messages without error
        assert len(messages) >= 1

    def test_fit_history_keeps_recent(self, tmp_path: Path) -> None:
        builder = self._make_builder(tmp_path)
        history = [
            {"role": "user", "content": f"message {i}"}
            for i in range(10)
        ]
        fitted = builder._fit_history(history, budget_tokens=10_000)
        # Must always keep the last 3
        assert fitted[-1]["content"] == "message 9"
        assert fitted[-2]["content"] == "message 8"
        assert fitted[-3]["content"] == "message 7"

    def test_fit_history_empty(self, tmp_path: Path) -> None:
        builder = self._make_builder(tmp_path)
        assert builder._fit_history([], budget_tokens=1000) == []

    def test_fit_chunks_to_budget_drops_excess(self, tmp_path: Path) -> None:
        builder = self._make_builder(tmp_path)
        chunks = [_make_result(text="x" * 400) for _ in range(100)]  # each ~100 tokens
        fitted = builder._fit_chunks_to_budget(chunks, budget_tokens=250)
        assert len(fitted) < len(chunks)
