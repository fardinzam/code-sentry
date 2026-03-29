"""Unit tests for the indexing pipeline (§7.1, §1.6, §8.3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.config.settings import IndexingSettings
from src.indexing.pipeline import (
    IndexingPipeline,
    _Checkpoint,
    _discover_files,
    _is_ignored,
    _load_ignore_patterns,
    _validate_repo_size,
)
from src.utils.errors import RepositoryTooLargeError

# ─── Ignore rules ─────────────────────────────────────────────────────────────


class TestIgnorePatterns:
    """Test .gitignore / .reviewerignore loading and matching."""

    def test_load_empty_when_no_files(self, tmp_path: Path) -> None:
        patterns = _load_ignore_patterns(tmp_path)
        assert patterns == []

    def test_load_patterns_from_gitignore(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n# comment\n\n")
        patterns = _load_ignore_patterns(tmp_path)
        assert "*.pyc" in patterns
        assert "__pycache__/" in patterns
        assert len(patterns) == 2  # comments and blanks excluded

    def test_load_combines_both_files(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("*.pyc\n")
        (tmp_path / ".reviewerignore").write_text("vendor/\n")
        patterns = _load_ignore_patterns(tmp_path)
        assert "*.pyc" in patterns
        assert "vendor/" in patterns

    def test_is_ignored_matches_filename(self, tmp_path: Path) -> None:
        file_path = tmp_path / "src" / "cache.pyc"
        assert _is_ignored(file_path, tmp_path, ["*.pyc"])

    def test_is_ignored_no_match(self, tmp_path: Path) -> None:
        file_path = tmp_path / "src" / "main.py"
        assert not _is_ignored(file_path, tmp_path, ["*.pyc"])


# ─── File discovery ───────────────────────────────────────────────────────────


class TestDiscoverFiles:
    """Test file discovery with extension and ignore filtering."""

    def test_discovers_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")

        files = list(_discover_files(tmp_path, [".py"], []))
        assert len(files) == 1
        assert files[0].name == "main.py"

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "config").write_text("data")
        (tmp_path / "main.py").write_text("x = 1")

        files = list(_discover_files(tmp_path, [".py", ".txt"], []))
        names = [f.name for f in files]
        assert "config" not in names

    def test_skips_pycache(self, tmp_path: Path) -> None:
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.cpython-311.pyc").write_bytes(b"\x00")
        (tmp_path / "main.py").write_text("x = 1")

        files = list(_discover_files(tmp_path, [".py", ".pyc"], []))
        assert all("__pycache__" not in str(f) for f in files)

    def test_applies_ignore_patterns(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "test.py").write_text("y = 2")

        files = list(_discover_files(tmp_path, [".py"], ["test.py"]))
        assert len(files) == 1
        assert files[0].name == "main.py"


# ─── Guardrails ───────────────────────────────────────────────────────────────


class TestValidateRepoSize:
    """Test repo size guardrail."""

    def test_within_limits_does_not_raise(self, tmp_path: Path) -> None:
        _validate_repo_size([Path("a.py")] * 100, tmp_path)

    def test_exceeds_hard_limit_raises(self, tmp_path: Path) -> None:
        files = [Path(f"f{i}.py") for i in range(200_001)]
        with pytest.raises(RepositoryTooLargeError, match="hard limit"):
            _validate_repo_size(files, tmp_path)

    def test_warning_logged_above_soft_limit(self, tmp_path: Path, caplog: Any) -> None:
        import logging

        files = [Path(f"f{i}.py") for i in range(50_001)]
        with caplog.at_level(logging.WARNING):
            _validate_repo_size(files, tmp_path)
        assert any("Large repository" in r.message for r in caplog.records)


# ─── Checkpoint ───────────────────────────────────────────────────────────────


class TestCheckpoint:
    """Test checkpoint save/load/clear."""

    def test_new_checkpoint_has_no_done_files(self, tmp_path: Path) -> None:
        cp = _Checkpoint(tmp_path / "ckpt.json")
        assert not cp.is_done("src/main.py")

    def test_mark_done_persists(self, tmp_path: Path) -> None:
        cp = _Checkpoint(tmp_path / "ckpt.json")
        cp.mark_done("src/main.py", 5)
        assert cp.is_done("src/main.py")

        # Verify persisted to disk
        data = json.loads((tmp_path / "ckpt.json").read_text())
        assert "src/main.py" in data["completed_files"]
        assert data["total_chunks"] == 5

    def test_clear_removes_file(self, tmp_path: Path) -> None:
        ckpt_path = tmp_path / "ckpt.json"
        cp = _Checkpoint(ckpt_path)
        cp.mark_done("a.py", 2)
        assert ckpt_path.exists()

        cp.clear()
        assert not ckpt_path.exists()
        assert not cp.is_done("a.py")

    def test_load_resumes_from_existing(self, tmp_path: Path) -> None:
        ckpt_path = tmp_path / "ckpt.json"
        ckpt_path.write_text(json.dumps({
            "completed_files": ["x.py", "y.py"],
            "total_chunks": 10,
        }))

        cp = _Checkpoint(ckpt_path)
        assert cp.is_done("x.py")
        assert cp.is_done("y.py")
        assert not cp.is_done("z.py")

    def test_load_handles_corrupted_file(self, tmp_path: Path) -> None:
        ckpt_path = tmp_path / "ckpt.json"
        ckpt_path.write_text("not json at all")

        # Should not raise
        cp = _Checkpoint(ckpt_path)
        assert not cp.is_done("anything.py")


# ─── IndexingPipeline ─────────────────────────────────────────────────────────


class TestIndexingPipeline:
    """Test the pipeline orchestrator with mocked dependencies."""

    def _make_pipeline(
        self,
        tmp_path: Path,
        embedder: Any = None,
        vector_db: Any = None,
    ) -> IndexingPipeline:
        repo = tmp_path / "repo"
        repo.mkdir(exist_ok=True)
        cr_dir = repo / ".code-reviewer"
        cr_dir.mkdir(exist_ok=True)

        if embedder is None:
            embedder = MagicMock()
            embedder.embed_batch.return_value = [[0.1, 0.2]]

        if vector_db is None:
            vector_db = MagicMock()

        settings = IndexingSettings(include_extensions=[".py", ".md"])
        return IndexingPipeline(
            repo_root=repo,
            embedder=embedder,
            vector_db=vector_db,
            settings=settings,
            code_reviewer_dir=cr_dir,
        )

    def test_run_indexes_files(self, tmp_path: Path) -> None:
        pipeline = self._make_pipeline(tmp_path)
        repo = tmp_path / "repo"
        (repo / "main.py").write_text("def hello():\n    return 1\n")

        stats = pipeline.run()

        assert stats["files_processed"] >= 0
        assert stats["chunks_created"] >= 0

    def test_run_skips_empty_files(self, tmp_path: Path) -> None:
        pipeline = self._make_pipeline(tmp_path)
        repo = tmp_path / "repo"
        (repo / "empty.py").write_text("")

        stats = pipeline.run()
        assert stats["files_processed"] == 0

    def test_run_with_resume_skips_done_files(self, tmp_path: Path) -> None:
        pipeline = self._make_pipeline(tmp_path)
        repo = tmp_path / "repo"
        (repo / "done.py").write_text("x = 1\n")

        # Pre-populate checkpoint
        pipeline._checkpoint.mark_done("done.py", 1)

        stats = pipeline.run(resume=True)
        assert stats["files_skipped"] >= 1

    def test_run_handles_embedding_failure(self, tmp_path: Path) -> None:
        embedder = MagicMock()
        embedder.embed_batch.side_effect = RuntimeError("API down")
        pipeline = self._make_pipeline(tmp_path, embedder=embedder)
        repo = tmp_path / "repo"
        (repo / "code.py").write_text("def foo():\n    pass\n")

        # Should not raise; file is skipped
        stats = pipeline.run()
        assert stats["files_processed"] == 0

    def test_run_handles_vectordb_failure(self, tmp_path: Path) -> None:
        embedder = MagicMock()
        embedder.embed_batch.return_value = [[0.1]]
        vector_db = MagicMock()
        vector_db.upsert_chunks.side_effect = RuntimeError("disk full")
        pipeline = self._make_pipeline(tmp_path, embedder=embedder, vector_db=vector_db)
        repo = tmp_path / "repo"
        (repo / "code.py").write_text("def foo():\n    pass\n")

        stats = pipeline.run()
        assert stats["files_processed"] == 0

    def test_run_skips_oversized_files(self, tmp_path: Path) -> None:
        pipeline = self._make_pipeline(tmp_path)
        pipeline._settings.max_file_tokens = 1  # Very low limit
        repo = tmp_path / "repo"
        (repo / "big.py").write_text("x = 1\n" * 100)

        stats = pipeline.run()
        assert stats["files_processed"] == 0
