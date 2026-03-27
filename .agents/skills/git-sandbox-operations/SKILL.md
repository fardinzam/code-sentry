---
name: git-sandbox-operations
description: How to safely create sandbox branches, apply patches atomically, handle rollback, and clean up with GitPython
---

# Git Sandbox Operations

## Overview

This skill guides safe Git branching, atomic patch application, rollback on failure, and cleanup for the sandbox validation pipeline. Uses `GitPython` for all operations.

## Prerequisites

```bash
pip install gitpython unidiff
```

## Step-by-Step Instructions

### 1. Initialize Repo and Create Sandbox Branch

```python
import git
from datetime import datetime

class SandboxManager:
    def __init__(self, repo_path: str):
        self.repo = git.Repo(repo_path)
        self.original_branch = self.repo.active_branch.name

    def create_sandbox(self, mode: str) -> str:
        """Create an isolated sandbox branch for testing changes."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"agent/{mode}-{timestamp}"

        # Ensure working tree is clean
        if self.repo.is_dirty(untracked_files=True):
            raise RuntimeError("Working tree is dirty. Commit or stash changes first.")

        # Create and checkout the sandbox branch
        self.repo.create_head(branch_name)
        self.repo.heads[branch_name].checkout()
        return branch_name
```

### 2. Apply Patches Atomically (FR-8.1, FR-8.2)

Multi-file changes are all-or-nothing. If any file fails, roll back everything.

```python
    def apply_patch_atomic(self, changes: list[dict]) -> dict:
        """Apply all changes atomically. Rolls back if any fail.

        Args:
            changes: list of {"file": "path", "diff": "unified diff string"}

        Returns:
            {"success": bool, "applied": [...], "failed": {...} | None}
        """
        # Record pre-patch state
        pre_patch_sha = self.repo.head.commit.hexsha
        applied_files = []

        try:
            for change in changes:
                file_path = change["file"]
                diff_text = change["diff"]

                # Write diff to temp file and apply
                import tempfile, subprocess
                with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
                    f.write(diff_text)
                    patch_file = f.name

                # Dry-apply first
                result = subprocess.run(
                    ["git", "apply", "--check", patch_file],
                    cwd=self.repo.working_dir,
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    raise PatchError(file_path, result.stderr)

                # Actually apply
                result = subprocess.run(
                    ["git", "apply", patch_file],
                    cwd=self.repo.working_dir,
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    raise PatchError(file_path, result.stderr)

                applied_files.append(file_path)

            # All patches applied — commit
            self.repo.index.add(applied_files)
            self.repo.index.commit(f"codeagent: applied {len(changes)} change(s)")

            return {"success": True, "applied": applied_files, "failed": None}

        except PatchError as e:
            # ROLLBACK: reset to pre-patch state
            self.repo.git.checkout("--", ".")  # Discard working tree changes
            self.repo.git.clean("-fd")          # Remove untracked files

            return {
                "success": False,
                "applied": applied_files,
                "failed": {"file": e.file_path, "error": e.message},
            }

class PatchError(Exception):
    def __init__(self, file_path: str, message: str):
        self.file_path = file_path
        self.message = message
        super().__init__(f"Patch failed for {file_path}: {message}")
```

### 3. Cleanup (Approval / Rejection)

```python
    def approve_and_merge(self, sandbox_branch: str, target_branch: str = "main") -> None:
        """Merge sandbox branch into target and clean up."""
        self.repo.heads[target_branch].checkout()
        self.repo.git.merge(sandbox_branch, "--no-ff", m=f"Merge {sandbox_branch}")
        self.repo.delete_head(sandbox_branch, force=True)

    def reject_and_cleanup(self, sandbox_branch: str) -> None:
        """Delete sandbox branch without merging."""
        # Switch back to original branch first
        self.repo.heads[self.original_branch].checkout()
        self.repo.delete_head(sandbox_branch, force=True)
```

### 4. Crash Cleanup (FR-8.6)

Register handlers to clean up on unexpected termination:

```python
import atexit
import signal

def register_cleanup_handlers(repo_path: str) -> None:
    """Register atexit and signal handlers for orphaned branch cleanup."""
    def cleanup():
        try:
            repo = git.Repo(repo_path)
            # Find orphaned agent branches
            orphaned = [
                b for b in repo.heads
                if b.name.startswith("agent/")
            ]
            if orphaned:
                # Switch to main/master first
                default = "main" if "main" in [h.name for h in repo.heads] else "master"
                repo.heads[default].checkout()
                for branch in orphaned:
                    repo.delete_head(branch, force=True)
                    print(f"🧹 Cleaned up orphaned branch: {branch.name}")
        except Exception:
            pass  # Best-effort cleanup

    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), exit(1)))
    signal.signal(signal.SIGINT, lambda *_: (cleanup(), exit(1)))

def detect_orphaned_branches(repo_path: str) -> list[str]:
    """Find agent/* branches with no corresponding active task.
    Call on startup to clean up after previous crashes."""
    repo = git.Repo(repo_path)
    return [b.name for b in repo.heads if b.name.startswith("agent/")]
```

### 5. Running Validation Commands in Sandbox

```python
import subprocess
from dataclasses import dataclass

@dataclass
class ValidationResult:
    step: str
    status: str  # "pass" | "fail" | "error"
    output: str
    errors: str
    duration_seconds: float

def run_validation_step(
    step_name: str,
    command: list[str],
    cwd: str,
    timeout: int = 300,
) -> ValidationResult:
    """Run a validation command with timeout and capture results."""
    import time
    start = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.monotonic() - start
        return ValidationResult(
            step=step_name,
            status="pass" if result.returncode == 0 else "fail",
            output=result.stdout[-5000:],  # Cap output length
            errors=result.stderr[-2000:],
            duration_seconds=round(duration, 2),
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        return ValidationResult(
            step=step_name,
            status="error",
            output="",
            errors=f"Command timed out after {timeout}s",
            duration_seconds=round(duration, 2),
        )
```

## Common Pitfalls

- **Always check `is_dirty()` before creating branches** — applying patches to a dirty tree causes hard-to-debug merge issues
- **Use `--no-ff` for merges** — this creates a merge commit even for fast-forward cases, making the history auditable
- **Cap subprocess output** — test suites can produce megabytes of output. Always truncate `stdout`/`stderr`
- **Signal handlers must be re-entrant** — keep cleanup logic simple and idempotent (deleting an already-deleted branch should not crash)
- **Don't use `git stash` for rollback** — it's fragile. Use `git checkout -- .` + `git clean -fd` to fully reset the working tree
- **Timeout all subprocesses** — a hanging test suite will block the entire pipeline. Default 300s with override via config
- **Patch format** — `git apply` expects standard unified diff format. The `DiffValidator` (from the diff validation skill) should run before `SandboxManager`
