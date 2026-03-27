"""AST-aware code chunker implementing §7.1.1 chunking strategy.

Chunking hierarchy (highest to lowest priority):
  1. Individual functions / methods
  2. Small classes (fit within max tokens)
  3. Class split into method chunks (each prefixed with class signature)
  4. Module-level statements grouped into blocks
  5. Line-based fallback (when AST parse fails)

Non-code documents:
  - Markdown: split at ## heading boundaries
  - Plain text: split at paragraph (double-newline)
  - Config files (YAML, TOML, JSON): single chunk per file
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from src.indexing.parser import CodeSymbol, ParseError, parse_python_file
from src.utils.constants import (
    CHUNK_CONTEXT_LINES,
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    TARGET_CHUNK_TOKENS,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Markdown heading boundary pattern
_MD_HEADING_RE = re.compile(r"^#{1,3} .+", re.MULTILINE)

# Extensions treated as single-chunk config files
_CONFIG_EXTENSIONS: frozenset[str] = frozenset({".yaml", ".yml", ".toml", ".json", ".ini", ".cfg"})

# Whitespace-only line pattern used for paragraph splitting
_BLANK_LINE_RE = re.compile(r"\n\n+")


@dataclass
class Chunk:
    """A single indexable unit of a source file.

    Attributes:
        text: The primary text to embed.
        file_path: Relative path to the source file.
        language: Programming language or document type.
        chunk_index: 0-based position within this file's chunk list.
        start_line: 1-indexed start line in the original file.
        end_line: 1-indexed end line in the original file.
        symbol_name: Function/class name if applicable.
        symbol_type: "function", "method", "class", "module", "doc".
        chunk_method: How the chunk was produced: "ast", "line", "heading", "paragraph", "single".
        context_before: Lines immediately before this chunk (not embedded).
        context_after: Lines immediately after this chunk (not embedded).
        estimated_tokens: Rough token estimate (chars / 4).
    """

    text: str
    file_path: str
    language: str
    chunk_index: int
    start_line: int
    end_line: int
    symbol_name: str = ""
    symbol_type: str = "module"
    chunk_method: str = "ast"
    context_before: str = ""
    context_after: str = ""
    estimated_tokens: int = field(init=False)

    def __post_init__(self) -> None:
        self.estimated_tokens = max(1, len(self.text) // 4)


# ─── Token estimation ─────────────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


# ─── Source lines helpers ─────────────────────────────────────────────────────


def _get_context_lines(lines: list[str], start_0: int, end_0: int) -> tuple[str, str]:
    """Extract leading/trailing context lines (not embedded, metadata only).

    Args:
        lines: All lines of the file (0-indexed).
        start_0: 0-indexed start of the chunk.
        end_0: 0-indexed end of the chunk (inclusive).

    Returns:
        Tuple of (context_before, context_after) strings.
    """
    before_start = max(0, start_0 - CHUNK_CONTEXT_LINES)
    after_end = min(len(lines), end_0 + 1 + CHUNK_CONTEXT_LINES)

    context_before = "".join(lines[before_start:start_0])
    context_after = "".join(lines[end_0 + 1 : after_end])
    return context_before, context_after


# ─── AST-based chunking ───────────────────────────────────────────────────────


def _symbol_to_chunk(
    symbol: CodeSymbol,
    file_path: str,
    language: str,
    chunk_index: int,
    lines: list[str],
    class_signature: str = "",
) -> Chunk:
    """Convert a single CodeSymbol into a Chunk."""
    text = symbol.source
    if class_signature and symbol.symbol_type == "method":
        # Prepend class signature so the chunk is self-contained (§7.1.1)
        text = f"{class_signature}\n    ...\n{symbol.source}"

    before, after = _get_context_lines(lines, symbol.start_line - 1, symbol.end_line - 1)
    return Chunk(
        text=text,
        file_path=file_path,
        language=language,
        chunk_index=chunk_index,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        symbol_name=symbol.name,
        symbol_type=symbol.symbol_type,
        chunk_method="ast",
        context_before=before,
        context_after=after,
    )


def _chunk_symbols(
    symbols: list[CodeSymbol],
    file_path: str,
    language: str,
    lines: list[str],
) -> list[Chunk]:
    """Apply the AST chunking hierarchy to a list of extracted symbols."""
    chunks: list[Chunk] = []
    idx = 0

    for symbol in symbols:
        tokens = _estimate_tokens(symbol.source)

        # Functions and methods: one chunk per symbol
        if symbol.symbol_type in ("function", "method"):
            if tokens < MIN_CHUNK_TOKENS and chunks:
                # Too small: merge into the previous chunk
                prev = chunks[-1]
                chunks[-1] = Chunk(
                    text=prev.text + "\n\n" + symbol.source,
                    file_path=prev.file_path,
                    language=prev.language,
                    chunk_index=prev.chunk_index,
                    start_line=prev.start_line,
                    end_line=symbol.end_line,
                    symbol_name=prev.symbol_name,
                    symbol_type=prev.symbol_type,
                    chunk_method="ast",
                )
            else:
                class_sig = ""
                if symbol.parent_class:
                    class_sig = f"class {symbol.parent_class}:"
                chunks.append(
                    _symbol_to_chunk(symbol, file_path, language, idx, lines, class_sig)
                )
                idx += 1

        # Classes: whole class if small, else split into method chunks
        elif symbol.symbol_type == "class":
            if tokens <= MAX_CHUNK_TOKENS:
                chunks.append(_symbol_to_chunk(symbol, file_path, language, idx, lines))
                idx += 1
            # If too large, the individual method symbols were already added above

    return chunks


# ─── Line-based fallback ──────────────────────────────────────────────────────


def _line_based_chunks(
    text: str,
    file_path: str,
    language: str,
    lines: list[str],
) -> list[Chunk]:
    """Split a file into fixed-size line groups when AST parsing fails."""
    target_lines = TARGET_CHUNK_TOKENS * 4 // 80  # ~80 chars per line estimate
    chunks: list[Chunk] = []

    for idx, start in enumerate(range(0, len(lines), target_lines)):
        group = lines[start : start + target_lines]
        text_part = "".join(group)
        if not text_part.strip():
            continue
        before, after = _get_context_lines(lines, start, min(start + target_lines - 1, len(lines) - 1))
        chunks.append(
            Chunk(
                text=text_part,
                file_path=file_path,
                language=language,
                chunk_index=idx,
                start_line=start + 1,
                end_line=min(start + target_lines, len(lines)),
                chunk_method="line",
                context_before=before,
                context_after=after,
            )
        )
    return chunks


# ─── Non-code document chunking ───────────────────────────────────────────────


def _markdown_chunks(text: str, file_path: str) -> list[Chunk]:
    """Split a Markdown file at heading boundaries (§7.1.1)."""
    splits = _MD_HEADING_RE.split(text)
    headings = _MD_HEADING_RE.findall(text)

    chunks: list[Chunk] = []
    line_cursor = 1

    for idx, (heading, body) in enumerate(zip([""] + headings, splits if not headings else [""] + splits)):
        combined = (heading + "\n" + body).strip()
        if not combined:
            continue
        line_count = combined.count("\n") + 1
        chunks.append(
            Chunk(
                text=combined,
                file_path=file_path,
                language="markdown",
                chunk_index=idx,
                start_line=line_cursor,
                end_line=line_cursor + line_count - 1,
                symbol_type="doc",
                chunk_method="heading",
            )
        )
        line_cursor += line_count

    return chunks if chunks else _paragraph_chunks(text, file_path)


def _paragraph_chunks(text: str, file_path: str) -> list[Chunk]:
    """Split plain text at double-newline paragraph boundaries."""
    paragraphs = _BLANK_LINE_RE.split(text)
    chunks: list[Chunk] = []
    line_cursor = 1

    for idx, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped:
            continue
        line_count = para.count("\n") + 1
        chunks.append(
            Chunk(
                text=stripped,
                file_path=file_path,
                language="text",
                chunk_index=idx,
                start_line=line_cursor,
                end_line=line_cursor + line_count - 1,
                symbol_type="doc",
                chunk_method="paragraph",
            )
        )
        line_cursor += line_count

    return chunks


def _single_chunk(text: str, file_path: str, language: str) -> list[Chunk]:
    """Return the entire file as a single chunk (for config files)."""
    line_count = text.count("\n") + 1
    return [
        Chunk(
            text=text.strip(),
            file_path=file_path,
            language=language,
            chunk_index=0,
            start_line=1,
            end_line=line_count,
            chunk_method="single",
        )
    ]


# ─── Public API ───────────────────────────────────────────────────────────────


def chunk_file(path: Path, repo_root: Path) -> list[Chunk]:
    """Produce all chunks for a single file.

    Args:
        path: Absolute path to the file to chunk.
        repo_root: Repository root, used to compute relative paths.

    Returns:
        Ordered list of Chunk objects. Empty if the file is empty.
    """
    rel_path = str(path.relative_to(repo_root))
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace")

    if not text.strip():
        return []

    # Config files: single chunk
    if suffix in _CONFIG_EXTENSIONS:
        return _single_chunk(text, rel_path, suffix.lstrip("."))

    # Markdown
    if suffix == ".md":
        return _markdown_chunks(text, rel_path)

    # Python: AST-aware chunking
    if suffix == ".py":
        lines = text.splitlines(keepends=True)
        try:
            symbols = parse_python_file(path)
            if not symbols:
                # Empty or module-only file — line-based
                return _line_based_chunks(text, rel_path, "python", lines)
            return _chunk_symbols(symbols, rel_path, "python", lines)
        except ParseError as exc:
            logger.warning(
                "AST parse failed — using line-based fallback",
                extra={"file": rel_path, "error": str(exc)},
            )
            return _line_based_chunks(text, rel_path, "python", lines)

    # Plain text and everything else
    lines = text.splitlines(keepends=True)
    return _paragraph_chunks(text, rel_path) or _line_based_chunks(text, rel_path, "text", lines)
