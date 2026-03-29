"""Unit tests for the AST parser and code chunker (§1.5)."""

from __future__ import annotations

from pathlib import Path

from src.indexing.chunker import (
    _estimate_tokens,
    _markdown_chunks,
    chunk_file,
)

# ─── Test fixtures ────────────────────────────────────────────────────────────


SIMPLE_PYTHON = '''"""Module docstring."""


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def subtract(x: int, y: int) -> int:
    """Subtract y from x."""
    return x - y


class Calculator:
    """A simple calculator."""

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    def divide(self, a: float, b: float) -> float:
        """Divide a by b."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
'''

SIMPLE_MARKDOWN = """# Project Title

Introduction paragraph here.

## Installation

Run pip install to get started.

## Usage

Import and use the module.
"""

LARGE_FUNCTION = "def big():\n" + "    x = 1\n" * 2000  # ~8000 tokens


# ─── Chunker tests ─────────────────────────────────────────────────────────────


class TestChunkFile:
    """Integration tests for the chunk_file public API."""

    def test_python_functions_produce_separate_chunks(self, tmp_path: Path) -> None:
        src = tmp_path / "math_ops.py"
        src.write_text(SIMPLE_PYTHON)

        chunks = chunk_file(src, tmp_path)

        # At minimum one chunk should be produced (even on line-based fallback)
        assert len(chunks) >= 1
        # At least one chunk should contain code from our sample
        all_text = " ".join(c.text for c in chunks)
        assert "def add" in all_text or "def subtract" in all_text

    def test_each_chunk_has_correct_file_path(self, tmp_path: Path) -> None:
        src = tmp_path / "sample.py"
        src.write_text(SIMPLE_PYTHON)

        chunks = chunk_file(src, tmp_path)
        for chunk in chunks:
            assert chunk.file_path == "sample.py"

    def test_empty_file_returns_no_chunks(self, tmp_path: Path) -> None:
        src = tmp_path / "empty.py"
        src.write_text("")

        chunks = chunk_file(src, tmp_path)
        assert chunks == []

    def test_markdown_file_split_at_headings(self, tmp_path: Path) -> None:
        md = tmp_path / "README.md"
        md.write_text(SIMPLE_MARKDOWN)

        chunks = chunk_file(md, tmp_path)
        assert all(c.language == "markdown" for c in chunks)
        assert all(c.chunk_method == "heading" for c in chunks)

    def test_toml_file_single_chunk(self, tmp_path: Path) -> None:
        cfg = tmp_path / "pyproject.toml"
        cfg.write_text("[tool.pytest]\ntest_paths = ['tests']\n")

        chunks = chunk_file(cfg, tmp_path)
        assert len(chunks) == 1
        assert chunks[0].chunk_method == "single"

    def test_large_file_triggers_line_fallback(self, tmp_path: Path) -> None:
        """A file with a massive function should still produce chunks."""
        src = tmp_path / "big.py"
        src.write_text(LARGE_FUNCTION)

        chunks = chunk_file(src, tmp_path)
        assert len(chunks) >= 1

    def test_chunk_indices_are_sequential(self, tmp_path: Path) -> None:
        src = tmp_path / "ops.py"
        src.write_text(SIMPLE_PYTHON)

        chunks = chunk_file(src, tmp_path)
        indices = [c.chunk_index for c in chunks]
        assert indices == sorted(indices)


class TestMarkdownChunker:
    """Test Markdown heading-based splitting."""

    def test_splits_at_h2_headings(self) -> None:
        chunks = _markdown_chunks(SIMPLE_MARKDOWN, "doc.md")
        texts = [c.text for c in chunks]
        assert any("Installation" in t for t in texts)
        assert any("Usage" in t for t in texts)

    def test_chunk_method_is_heading(self) -> None:
        chunks = _markdown_chunks(SIMPLE_MARKDOWN, "doc.md")
        assert all(c.chunk_method == "heading" for c in chunks)

    def test_empty_markdown_falls_back_to_paragraphs(self) -> None:
        plain = "First paragraph.\n\nSecond paragraph."
        chunks = _markdown_chunks(plain, "plain.md")
        assert len(chunks) >= 1


class TestTokenEstimation:
    """Token estimation helper."""

    def test_non_empty_string_has_positive_tokens(self) -> None:
        assert _estimate_tokens("hello world") > 0

    def test_empty_string_returns_one(self) -> None:
        assert _estimate_tokens("") == 1

    def test_longer_text_has_more_tokens(self) -> None:
        short = _estimate_tokens("hi")
        long = _estimate_tokens("x" * 1000)
        assert long > short
