"""git_op tool: safe read-only Git operations for the agent.

Supported operations: diff, log, show, status, branch.
All write operations (commit, push, checkout) are intentionally excluded
— those are handled by the GitSandboxManager, not the agent directly.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

_ALLOWED_OPS: frozenset[str] = frozenset({"diff", "log", "show", "status", "branch"})
_MAX_OUTPUT_CHARS = 6000
_TIMEOUT_SECONDS = 15

# Write-mode flags that are never allowed in read-only git operations
_WRITE_FLAGS: frozenset[str] = frozenset({
    "--amend", "--force", "-f", "--delete", "-d", "-D",
    "--hard", "--soft", "--mixed", "--push",
})


def make_git_op_handler(repo_root: Path) -> Callable[[dict], str]:  # type: ignore[type-arg]
    """Return a git_op handler bound to ``repo_root``.

    Handler args:
        operation (str): One of ``diff | log | show | status | branch``.
        args (list[str], optional): Additional arguments passed to the
            git sub-command.

    Returns:
        Git command output string, or an error description.

    Security:
        Only read-only git sub-commands are allowed. The ``--no-pager``
        flag is always prepended so output is captured correctly.
    """

    def handler(tool_args: dict) -> str:  # type: ignore[type-arg]
        operation = tool_args.get("operation", "").strip()
        extra_args = tool_args.get("args", [])

        if not operation:
            return "[ERROR] git_op: 'operation' argument is required."

        if operation not in _ALLOWED_OPS:
            allowed = ", ".join(sorted(_ALLOWED_OPS))
            return (
                f"[ERROR] git_op: operation '{operation}' is not allowed. "
                f"Permitted operations: {allowed}"
            )

        if not isinstance(extra_args, list):
            extra_args = []

        # Sanitise extra args: reject any that look like write flags
        for arg in extra_args:
            if str(arg) in _WRITE_FLAGS:
                return (
                    f"[SANDBOX VIOLATION] git_op: argument '{arg}' "
                    "is prohibited for read-only git operations."
                )

        cmd = ["git", "--no-pager", operation, *[str(a) for a in extra_args]]

        try:
            proc = subprocess.run(
                cmd,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return f"[ERROR] git_op: timed out after {_TIMEOUT_SECONDS}s."
        except OSError as exc:
            return f"[ERROR] git_op: OS error: {exc}"

        output = (proc.stdout or "") + (f"\n[stderr] {proc.stderr}" if proc.stderr else "")
        output = output.strip()

        if not output:
            output = "(no output)"

        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n[... output truncated ...]"

        return f"[exit {proc.returncode}] git {operation}\n\n{output}"

    return handler
