"""Git client wrapping subprocess calls to the system git binary (§12.1).

All operations are thin, typed wrappers. Authentication is handled via
environment variables and the auth_method setting (§12.1.1).
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path

from src.utils.errors import GitError
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Token pattern to redact from logged URLs
_TOKEN_IN_URL_RE = re.compile(r"(https?://)([^@]+)@")


def _sanitize_url(url: str) -> str:
    """Strip embedded credentials from a Git URL before logging."""
    return _TOKEN_IN_URL_RE.sub(r"\1***@", url)


def _run(
    args: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command, raising GitError on non-zero exit.

    Args:
        args: Command arguments (without leading "git").
        cwd: Working directory for the command.
        env: Optional environment overrides merged with the current env.
        check: If True, raise GitError on non-zero exit code.

    Returns:
        CompletedProcess with stdout and stderr as decoded strings.

    Raises:
        GitError: When the command exits with a non-zero status.
    """
    merged_env = {**os.environ, **(env or {})}
    cmd = ["git", *args]
    logger.debug("Running git command", extra={"cmd": " ".join(cmd), "cwd": str(cwd)})

    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
    )

    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args[:2])} failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    return result


class GitClient:
    """Typed interface over the system git binary.

    Args:
        repo_path: Absolute path to the git repository root.
        auth_method: One of "auto", "ssh", "https_token", "credential_helper".
    """

    def __init__(self, repo_path: Path, auth_method: str = "auto") -> None:
        self._repo = repo_path
        self._auth_method = auth_method

    # ─── Auth helpers ─────────────────────────────────────────────────────────

    def _auth_env(self) -> dict[str, str]:
        """Build environment variables required for the configured auth method."""
        if self._auth_method == "ssh":
            ssh_key = os.environ.get("CODE_REVIEWER_GIT_SSH_KEY", "~/.ssh/id_rsa")
            return {"GIT_SSH_COMMAND": f"ssh -i {ssh_key} -o StrictHostKeyChecking=no"}
        # auto / credential_helper / https_token: git picks up credentials itself
        return {}

    def _inject_token_into_url(self, url: str) -> str:
        """Prepend a PAT into an HTTPS clone URL (https_token auth mode)."""
        token = os.environ.get("CODE_REVIEWER_GIT_TOKEN", "")
        if not token:
            return url
        # Replace https://host with https://<token>@host
        return re.sub(r"^(https?://)", rf"\1{token}@", url)

    # ─── Repository operations ────────────────────────────────────────────────

    def clone(self, url: str, dest: Path) -> None:
        """Clone a remote repository.

        Args:
            url: Remote URL (HTTPS or SSH).
            dest: Local destination path.

        Raises:
            GitError: If clone fails.
        """
        clone_url = self._inject_token_into_url(url) if self._auth_method == "https_token" else url
        logger.info("Cloning repository", extra={"url": _sanitize_url(url), "dest": str(dest)})
        _run(["clone", clone_url, str(dest)], cwd=dest.parent, env=self._auth_env())

    def get_current_sha(self) -> str:
        """Return the SHA of HEAD.

        Returns:
            40-character hex SHA string.
        """
        result = _run(["rev-parse", "HEAD"], cwd=self._repo)
        return result.stdout.strip()

    def get_current_branch(self) -> str:
        """Return the name of the currently checked-out branch."""
        result = _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=self._repo)
        return result.stdout.strip()

    def is_dirty(self) -> bool:
        """Return True if the working tree has uncommitted changes."""
        result = _run(["status", "--porcelain"], cwd=self._repo)
        return bool(result.stdout.strip())

    # ─── Branch operations ────────────────────────────────────────────────────

    def create_branch(self, name: str) -> None:
        """Create and checkout a new branch from the current HEAD.

        Args:
            name: Branch name, e.g. "ai-review/abc123".

        Raises:
            GitError: If the branch already exists or checkout fails.
        """
        logger.info("Creating branch", extra={"branch": name})
        _run(["checkout", "-b", name], cwd=self._repo)

    def checkout(self, ref: str) -> None:
        """Checkout an existing branch or commit.

        Args:
            ref: Branch name or commit SHA.
        """
        _run(["checkout", ref], cwd=self._repo)

    def delete_branch(self, name: str, *, remote: bool = False) -> None:
        """Delete a local branch, and optionally the remote tracking branch.

        Args:
            name: Branch name.
            remote: If True, also delete the remote branch via push.
        """
        logger.info("Deleting branch", extra={"branch": name, "remote": remote})
        _run(["branch", "-D", name], cwd=self._repo)
        if remote:
            _run(["push", "origin", "--delete", name], cwd=self._repo, env=self._auth_env())

    def list_branches(self, pattern: str = "") -> list[str]:
        """List local branches, optionally filtered by a pattern.

        Args:
            pattern: Glob pattern passed to git branch --list.

        Returns:
            List of branch names (stripped of leading whitespace/asterisk).
        """
        args = ["branch", "--list"]
        if pattern:
            args.append(pattern)
        result = _run(args, cwd=self._repo)
        return [line.strip().lstrip("* ") for line in result.stdout.splitlines() if line.strip()]

    # ─── Diff operations ──────────────────────────────────────────────────────

    def generate_diff(self, base_ref: str, head_ref: str = "HEAD") -> str:
        """Generate a unified diff between two refs.

        Args:
            base_ref: Base commit/branch (the "before" state).
            head_ref: Head commit/branch (the "after" state). Defaults to HEAD.

        Returns:
            Unified diff as a string.
        """
        result = _run(
            ["diff", "--unified=3", base_ref, head_ref],
            cwd=self._repo,
            check=False,  # git diff exits 1 when there are differences
        )
        return result.stdout

    def apply_diff_check(self, patch_text: str) -> tuple[bool, str]:
        """Dry-run a unified diff patch without modifying the working tree.

        Args:
            patch_text: Unified diff content.

        Returns:
            Tuple of (success: bool, error_message: str).
        """
        result = _run(
            ["apply", "--check", "--3way"],
            cwd=self._repo,
            check=False,
        )
        # Feed patch via stdin using a separate run call
        proc = subprocess.run(
            ["git", "apply", "--check", "--3way"],
            cwd=self._repo,
            input=patch_text,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0, proc.stderr.strip()

    def apply_diff(self, patch_text: str) -> None:
        """Apply a unified diff patch to the working tree.

        Args:
            patch_text: Unified diff content.

        Raises:
            GitError: If the patch cannot be applied.
        """
        proc = subprocess.run(
            ["git", "apply", "--3way"],
            cwd=self._repo,
            input=patch_text,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise GitError(
                f"Failed to apply diff:\n{proc.stderr.strip()}\n"
                "Re-run with '--ignore-whitespace' or request a corrected diff from the agent."
            )

    # ─── Staging / committing ─────────────────────────────────────────────────

    def add_all(self) -> None:
        """Stage all changes in the working tree."""
        _run(["add", "-A"], cwd=self._repo)

    def commit(self, message: str) -> None:
        """Create a commit with the staged changes.

        Args:
            message: Commit message.
        """
        _run(["commit", "-m", message], cwd=self._repo)

    def reset_hard(self, ref: str = "HEAD") -> None:
        """Hard-reset the working tree to a reference (used for rollback).

        Args:
            ref: The commit to reset to. Defaults to HEAD (clears uncommitted changes).
        """
        logger.warning("Hard-resetting branch", extra={"ref": ref})
        _run(["reset", "--hard", ref], cwd=self._repo)

    # ─── Log / history ────────────────────────────────────────────────────────

    def get_commit_log(self, n: int = 10) -> list[dict[str, str]]:
        """Return the last N commits as structured records.

        Args:
            n: Number of commits to return.

        Returns:
            List of dicts with keys: sha, author, date, message.
        """
        fmt = "%H%x1f%an%x1f%ai%x1f%s"
        result = _run(["log", f"-{n}", f"--format={fmt}"], cwd=self._repo)
        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append(
                    {"sha": parts[0], "author": parts[1], "date": parts[2], "message": parts[3]}
                )
        return commits

    def get_changed_files(self, base_ref: str) -> list[str]:
        """List files changed between base_ref and HEAD.

        Args:
            base_ref: Base commit or branch name.

        Returns:
            List of relative file paths.
        """
        result = _run(["diff", "--name-only", base_ref, "HEAD"], cwd=self._repo)
        return [f for f in result.stdout.strip().splitlines() if f]


def make_sandbox_branch_name() -> str:
    """Generate a unique sandbox branch name using UUID4 (§8.1).

    Returns:
        Branch name in the form "ai-review/<uuid4>".
    """
    return f"ai-review/{uuid.uuid4()}"
