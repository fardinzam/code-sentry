"""Unit tests for Git client and sandbox manager (§1.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.git_ops.client import GitClient, _sanitize_url, make_sandbox_branch_name
from src.utils.errors import SandboxError


class TestURLSanitization:
    """Tokens must be stripped from URLs before logging."""

    def test_https_url_with_token_is_sanitized(self) -> None:
        url = "https://ghp_abc123@github.com/org/repo.git"
        sanitized = _sanitize_url(url)
        assert "ghp_abc123" not in sanitized
        assert "***" in sanitized
        assert "github.com/org/repo.git" in sanitized

    def test_plain_https_url_is_unchanged(self) -> None:
        url = "https://github.com/org/repo.git"
        assert _sanitize_url(url) == url

    def test_ssh_url_is_unchanged(self) -> None:
        url = "git@github.com:org/repo.git"
        assert _sanitize_url(url) == url


class TestSandboxBranchNaming:
    """ai-review/<uuid4> naming convention (§8.1)."""

    def test_branch_has_correct_prefix(self) -> None:
        name = make_sandbox_branch_name()
        assert name.startswith("ai-review/")

    def test_branch_names_are_unique(self) -> None:
        names = {make_sandbox_branch_name() for _ in range(100)}
        assert len(names) == 100


class TestGitClientWithRealRepo:
    """Integration tests using a real temporary Git repository."""

    @pytest.fixture()
    def git_repo(self, tmp_path: Path) -> tuple[Path, GitClient]:
        """Create a minimal initialized Git repo."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True
        )

        # Initial commit
        (repo / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

        return repo, GitClient(repo_path=repo)

    def test_get_current_sha_returns_hex(self, git_repo: tuple[Path, GitClient]) -> None:
        _, client = git_repo
        sha = client.get_current_sha()
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_is_dirty_false_on_clean_repo(self, git_repo: tuple[Path, GitClient]) -> None:
        _, client = git_repo
        assert not client.is_dirty()

    def test_is_dirty_true_after_modification(self, git_repo: tuple[Path, GitClient]) -> None:
        repo, client = git_repo
        (repo / "new_file.txt").write_text("hello")
        assert client.is_dirty()

    def test_create_and_delete_branch(self, git_repo: tuple[Path, GitClient]) -> None:
        _, client = git_repo
        client.create_branch("feature/test")
        branches = client.list_branches()
        assert "feature/test" in branches

        client.checkout("main")
        client.delete_branch("feature/test")
        branches_after = client.list_branches()
        assert "feature/test" not in branches_after

    def test_commit_log_returns_entries(self, git_repo: tuple[Path, GitClient]) -> None:
        _, client = git_repo
        log = client.get_commit_log(n=5)
        assert len(log) >= 1
        assert "sha" in log[0]
        assert "message" in log[0]


class TestSandboxManager:
    """Tests for sandbox branch lifecycle."""

    @pytest.fixture()
    def git_repo(self, tmp_path: Path) -> tuple[Path, GitClient]:
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=repo, check=True, capture_output=True
        )
        (repo / "src.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo, GitClient(repo_path=repo)

    def test_create_raises_if_repo_is_dirty(self, git_repo: tuple[Path, GitClient]) -> None:
        from src.git_ops.sandbox import SandboxManager

        repo, client = git_repo
        (repo / "dirty.txt").write_text("unstaged")

        manager = SandboxManager(client)
        with pytest.raises(SandboxError, match="uncommitted changes"):
            manager.create()
