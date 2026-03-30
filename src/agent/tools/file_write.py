"""file_write tool: write content to a file within the sandbox branch.

Enforces that the target path is inside the repository root.
Atomically writes content via a temporary file to avoid partial writes.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path


def make_file_write_handler(repo_root: Path) -> Callable[[dict], str]:  # type: ignore[type-arg]
    """Return a file_write handler bound to ``repo_root``.

    Handler args:
        path (str): Relative path to write (e.g. ``"src/utils.py"``).
        content (str): Full file content to write.

    Returns:
        Observation string confirming the write or describing the error.

    Security:
        Rejects any path that resolves outside ``repo_root`` (sandbox
        enforcement per §7.3 FR-4.7).
    """

    def handler(args: dict) -> str:  # type: ignore[type-arg]
        raw_path = args.get("path", "")
        content = args.get("content")

        if not raw_path:
            return "[ERROR] file_write: 'path' argument is required."
        if content is None:
            return "[ERROR] file_write: 'content' argument is required."

        abs_path = (repo_root / raw_path).resolve()

        # Sandbox enforcement
        try:
            abs_path.relative_to(repo_root.resolve())
        except ValueError:
            return (
                f"[SANDBOX VIOLATION] file_write: path '{raw_path}' "
                "is outside the repository root. Write rejected."
            )

        # Atomic write via temp file → rename
        try:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=abs_path.parent, prefix=".tmp_", suffix=".write"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                os.replace(tmp_name, abs_path)
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
                raise
        except OSError as exc:
            return f"[ERROR] file_write: could not write '{raw_path}': {exc}"

        line_count = content.count("\n") + (1 if content else 0)
        return (
            f"OK: wrote {line_count} line(s) to '{raw_path}' "
            f"({len(content.encode())} bytes)."
        )

    return handler
