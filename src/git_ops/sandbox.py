"""Sandbox branch manager for isolated agent changes (§12.1, §8.1).

Each proposal gets an isolated Git branch named ai-review/<uuid4>.
All file modifications happen only within that branch. Provides atomic
rollback on failure and cleanup of stale branches.
"""

from __future__ import annotations

import time

from src.git_ops.client import GitClient, make_sandbox_branch_name
from src.utils.errors import DiffApplicationError, GitError, SandboxError
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SandboxManager:
    """Manages sandbox branches for proposal isolation.

    Args:
        client: GitClient for the target repository.
        retention_days: Delete sandbox branches older than this many days.
    """

    def __init__(self, client: GitClient, retention_days: int = 7) -> None:
        self._client = client
        self._retention_days = retention_days

    def create(self) -> str:
        """Create a new sandbox branch from the current HEAD.

        Raises:
            SandboxError: If the repo has uncommitted changes.

        Returns:
            The name of the newly created sandbox branch.
        """
        if self._client.is_dirty():
            raise SandboxError(
                "Repository has uncommitted changes. "
                "Commit or stash them before creating a sandbox branch."
            )

        branch_name = make_sandbox_branch_name()
        logger.info("Creating sandbox branch", extra={"branch": branch_name})
        self._client.create_branch(branch_name)
        return branch_name

    def apply_patch(self, branch_name: str, patch_text: str, commit_message: str) -> None:
        """Apply a diff patch to the sandbox branch atomically.

        If the apply fails, the branch is hard-reset to HEAD before the
        patch was attempted, guaranteeing no partial changes remain.

        Args:
            branch_name: The sandbox branch to apply the patch on.
            patch_text: Unified diff content.
            commit_message: Git commit message.

        Raises:
            DiffApplicationError: If the patch cannot be applied.
        """
        pre_apply_sha = self._client.get_current_sha()

        try:
            ok, err = self._client.apply_diff_check(patch_text)
            if not ok:
                raise DiffApplicationError(
                    f"Dry-run check failed for branch '{branch_name}': {err}. "
                    "The agent diff may have incorrect line numbers or context lines."
                )

            self._client.apply_diff(patch_text)
            self._client.add_all()
            self._client.commit(commit_message)
            logger.info(
                "Patch applied successfully",
                extra={"branch": branch_name, "commit": self._client.get_current_sha()},
            )

        except (GitError, DiffApplicationError):
            logger.warning(
                "Patch application failed — rolling back to pre-apply state",
                extra={"branch": branch_name, "reset_to": pre_apply_sha},
            )
            self._client.reset_hard(pre_apply_sha)
            raise

    def delete(self, branch_name: str, *, remote: bool = False) -> None:
        """Delete a sandbox branch.

        Args:
            branch_name: Branch to delete.
            remote: Also push a delete to origin.
        """
        logger.info("Deleting sandbox branch", extra={"branch": branch_name})
        self._client.delete_branch(branch_name, remote=remote)

    def cleanup_stale(self, base_branch: str) -> list[str]:
        """Delete sandbox branches that are older than the retention period.

        This is a best-effort operation — failures on individual branches
        are logged but do not stop cleanup of others.

        Args:
            base_branch: Check out this branch before deleting others.

        Returns:
            List of branch names that were deleted.
        """
        self._client.checkout(base_branch)

        all_sandbox = self._client.list_branches("ai-review/*")
        cutoff_ts = time.time() - (self._retention_days * 86_400)

        deleted: list[str] = []
        for branch in all_sandbox:
            try:
                # Use the commit date of the branch tip to determine age
                log = self._client.get_commit_log(n=1)
                if not log:
                    continue
                # get_commit_log is run on HEAD; we need the branch tip
                # so we briefly inspect it via git log <branch> -1
                import subprocess

                proc = subprocess.run(
                    ["git", "log", branch, "-1", "--format=%ct"],
                    cwd=self._client._repo,
                    capture_output=True,
                    text=True,
                )
                if proc.returncode != 0 or not proc.stdout.strip():
                    continue

                commit_ts = int(proc.stdout.strip())
                if commit_ts < cutoff_ts:
                    self.delete(branch)
                    deleted.append(branch)
                    logger.info("Deleted stale sandbox branch", extra={"branch": branch})

            except Exception as exc:
                logger.warning(
                    "Failed to clean up sandbox branch",
                    extra={"branch": branch, "error": str(exc)},
                )

        return deleted
