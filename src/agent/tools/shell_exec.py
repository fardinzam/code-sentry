"""shell_exec tool: run a sandboxed shell command inside the repo directory.

Only commands whose base name appears in the allowlist are permitted.
All execution is scoped to ``repo_root`` as the working directory.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

# Allowlist of permitted command base names (§7.3 FR-3.2)
_COMMAND_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Python tooling
        "python",
        "python3",
        "pytest",
        "ruff",
        "mypy",
        "pip",
        "pip3",
        # Project build/test tools
        "make",
        "poetry",
        "uv",
        # Code quality
        "black",
        "isort",
        "flake8",
        "pylint",
        # Basic shell utilities (read-only)
        "echo",
        "cat",
        "ls",
        "find",
        "grep",
        "wc",
        "head",
        "tail",
        "diff",
        "tree",
    }
)

_TIMEOUT_SECONDS = 30
_MAX_OUTPUT_CHARS = 4000


def make_shell_exec_handler(repo_root: Path) -> Callable[[dict], str]:  # type: ignore[type-arg]
    """Return a shell_exec handler constrained to ``repo_root``.

    Handler args:
        command (str): Shell command string to execute.

    Returns:
        Combined stdout+stderr output, truncated at ``_MAX_OUTPUT_CHARS``.

    Security:
        - Only commands whose first token matches ``_COMMAND_ALLOWLIST``
          are executed; all others are rejected.
        - Working directory is always ``repo_root`` (not user-supplied).
        - ``shell=False`` to prevent injection via shell metacharacters.
        - 30-second execution timeout.
    """

    def handler(args: dict) -> str:  # type: ignore[type-arg]
        command_str = args.get("command", "").strip()
        if not command_str:
            return "[ERROR] shell_exec: 'command' argument is required."

        try:
            tokens = shlex.split(command_str)
        except ValueError as exc:
            return f"[ERROR] shell_exec: failed to parse command: {exc}"

        if not tokens:
            return "[ERROR] shell_exec: empty command."

        base_cmd = tokens[0].split("/")[-1]  # strip path prefix
        if base_cmd not in _COMMAND_ALLOWLIST:
            allowed = ", ".join(sorted(_COMMAND_ALLOWLIST))
            return (
                f"[SANDBOX VIOLATION] shell_exec: command '{base_cmd}' is not "
                f"in the allowlist.\nAllowed commands: {allowed}"
            )

        try:
            proc = subprocess.run(
                tokens,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                shell=False,  # explicit: no shell interpolation
            )
        except FileNotFoundError:
            return f"[ERROR] shell_exec: command '{base_cmd}' not found on PATH."
        except subprocess.TimeoutExpired:
            return f"[ERROR] shell_exec: command timed out after {_TIMEOUT_SECONDS}s."
        except OSError as exc:
            return f"[ERROR] shell_exec: OS error running command: {exc}"

        combined = ""
        if proc.stdout:
            combined += proc.stdout
        if proc.stderr:
            combined += "\n[stderr]\n" + proc.stderr

        combined = combined.strip()
        if not combined:
            combined = "(no output)"

        truncated = len(combined) > _MAX_OUTPUT_CHARS
        if truncated:
            combined = combined[:_MAX_OUTPUT_CHARS] + "\n[... output truncated ...]"

        exit_info = f"[exit code: {proc.returncode}]"
        return f"{exit_info}\n{combined}"

    return handler
