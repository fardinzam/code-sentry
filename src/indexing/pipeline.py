"""Indexing pipeline orchestrator (§7.1, §1.6, §8.3).

Walks a repository, applies ignore rules, chunks all files, embeds them,
and stores them in the vector database. Supports checkpoint-based resume.
"""

from __future__ import annotations

import fnmatch
import json
import os
import time
from collections.abc import Generator
from pathlib import Path

from src.config.settings import IndexingSettings
from src.indexing.chunker import chunk_file
from src.indexing.embedder import EmbeddingClient
from src.indexing.vectordb import VectorDBClient
from src.utils.constants import MAX_FILE_COUNT_HARD, MAX_FILE_COUNT_WARN
from src.utils.errors import RepositoryTooLargeError
from src.utils.logging import get_logger

logger = get_logger(__name__)

_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".mp4", ".mp3",
        ".pdf", ".zip", ".tar", ".gz", ".whl", ".egg", ".pyc", ".so", ".dll",
    }
)


# ─── Ignore rules ─────────────────────────────────────────────────────────────


def _load_ignore_patterns(repo_root: Path) -> list[str]:
    """Load patterns from .gitignore and .reviewerignore."""
    patterns: list[str] = []
    for name in (".gitignore", ".reviewerignore"):
        ignore_path = repo_root / name
        if ignore_path.exists():
            for line in ignore_path.read_text().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    patterns.append(stripped)
    return patterns


def _is_ignored(path: Path, repo_root: Path, patterns: list[str]) -> bool:
    """Return True if the path matches any ignore pattern."""
    rel = str(path.relative_to(repo_root))
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern):
            return True
        # Match directory prefixes
        if fnmatch.fnmatch(rel.split("/")[0] + "/", pattern):
            return True
    return False


# ─── File discovery ───────────────────────────────────────────────────────────


def _discover_files(
    repo_root: Path,
    include_extensions: list[str],
    ignore_patterns: list[str],
) -> Generator[Path, None, None]:
    """Yield all indexable files in the repository."""
    for dirpath, dirnames, filenames in os.walk(repo_root):
        current = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in {"__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
            and not _is_ignored(current / d, repo_root, ignore_patterns)
        ]

        for filename in filenames:
            file_path = current / filename
            suffix = file_path.suffix.lower()
            if suffix in _BINARY_EXTENSIONS:
                continue
            if suffix not in include_extensions:
                continue
            if _is_ignored(file_path, repo_root, ignore_patterns):
                continue

            # Validate path is resolvable (catches broken symlinks)
            try:
                file_path.resolve()
            except OSError:
                continue

            yield file_path


# ─── Guardrails ───────────────────────────────────────────────────────────────


def _validate_repo_size(files: list[Path], repo_root: Path) -> None:
    """Enforce §8.3 pre-indexing guardrails."""
    count = len(files)
    if count > MAX_FILE_COUNT_HARD:
        raise RepositoryTooLargeError(
            f"Repository has {count:,} files (hard limit: {MAX_FILE_COUNT_HARD:,}). "
            "Use --include to restrict the scope: code-reviewer index --include src/"
        )
    if count > MAX_FILE_COUNT_WARN:
        logger.warning(
            "Large repository detected - indexing may take >10 minutes",
            extra={"file_count": count},
        )


# ─── Checkpoint ───────────────────────────────────────────────────────────────


class _Checkpoint:
    """Persist indexing progress to enable resume on crash (§14.2)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._completed: list[str] = []
        self._total_chunks: int = 0
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data: dict[str, object] = json.loads(self._path.read_text())
                completed = data.get("completed_files", [])
                self._completed = list(completed) if isinstance(completed, list) else []
                total = data.get("total_chunks", 0)
                self._total_chunks = int(total) if isinstance(total, (int, float)) else 0
            except Exception:
                pass

    def is_done(self, file_path: str) -> bool:
        return file_path in self._completed

    def mark_done(self, file_path: str, chunk_count: int) -> None:
        self._completed.append(file_path)
        self._total_chunks += chunk_count
        self._path.write_text(
            json.dumps(
                {"completed_files": self._completed, "total_chunks": self._total_chunks},
                indent=2,
            )
        )

    def clear(self) -> None:
        self._completed = []
        self._total_chunks = 0
        if self._path.exists():
            self._path.unlink()


# ─── Pipeline ─────────────────────────────────────────────────────────────────


class IndexingPipeline:
    """Orchestrates the full parse -> chunk -> embed -> store pipeline.

    Args:
        repo_root: Root of the repository to index.
        embedder: Embedding client implementation.
        vector_db: Vector database client implementation.
        settings: Indexing configuration.
        code_reviewer_dir: Path to the .code-reviewer/ metadata directory.
    """

    def __init__(
        self,
        repo_root: Path,
        embedder: EmbeddingClient,
        vector_db: VectorDBClient,
        settings: IndexingSettings,
        code_reviewer_dir: Path,
    ) -> None:
        self._repo = repo_root
        self._embedder = embedder
        self._vector_db = vector_db
        self._settings = settings
        self._cr_dir = code_reviewer_dir
        self._checkpoint = _Checkpoint(code_reviewer_dir / "index_checkpoint.json")

    def run(self, resume: bool = False) -> dict[str, int]:
        """Execute the full indexing pipeline.

        Args:
            resume: If True, skip files that were already indexed in a previous run.

        Returns:
            Stats dict with keys: files_processed, chunks_created, files_skipped.
        """
        if not resume:
            self._checkpoint.clear()

        ignore_patterns = _load_ignore_patterns(self._repo)
        all_files = list(
            _discover_files(self._repo, self._settings.include_extensions, ignore_patterns)
        )
        _validate_repo_size(all_files, self._repo)

        stats: dict[str, int] = {"files_processed": 0, "chunks_created": 0, "files_skipped": 0}
        start_time = time.monotonic()

        logger.info(
            "Starting indexing",
            extra={"repo": str(self._repo), "total_files": len(all_files), "resume": resume},
        )

        for i, file_path in enumerate(all_files):
            rel = str(file_path.relative_to(self._repo))

            if resume and self._checkpoint.is_done(rel):
                stats["files_skipped"] += 1
                continue

            # Size guardrail: skip files exceeding max_file_tokens
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read file", extra={"file": rel, "error": str(exc)})
                continue

            estimated_tokens = len(text) // 4
            if estimated_tokens > self._settings.max_file_tokens:
                logger.warning(
                    "File exceeds max_file_tokens - skipping",
                    extra={"file": rel, "estimated_tokens": estimated_tokens},
                )
                continue

            # Chunk
            try:
                chunks = chunk_file(file_path, self._repo)
            except Exception as exc:
                logger.warning("Chunking failed", extra={"file": rel, "error": str(exc)})
                continue

            if not chunks:
                continue

            # Embed
            try:
                vectors = self._embedder.embed_batch([c.text for c in chunks])
            except Exception as exc:
                logger.warning(
                    "Embedding failed - skipping file",
                    extra={"file": rel, "error": str(exc)},
                )
                continue

            # Store (whole-file atomicity)
            try:
                self._vector_db.upsert_chunks(chunks, vectors)
            except Exception as exc:
                logger.error(
                    "Vector DB write failed - file not indexed",
                    extra={"file": rel, "error": str(exc)},
                )
                continue

            self._checkpoint.mark_done(rel, len(chunks))
            stats["files_processed"] += 1
            stats["chunks_created"] += len(chunks)

            if (i + 1) % 50 == 0 or (i + 1) == len(all_files):
                elapsed = time.monotonic() - start_time
                logger.info(
                    "Indexing progress",
                    extra={
                        "processed": stats["files_processed"],
                        "total": len(all_files),
                        "chunks": stats["chunks_created"],
                        "elapsed_s": round(elapsed, 1),
                    },
                )

        self._checkpoint.clear()
        logger.info("Indexing complete", extra=stats)
        return stats
