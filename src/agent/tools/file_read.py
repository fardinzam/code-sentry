from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

_MAX_LINES = 500
_TRUNCATION_MESSAGE = "\n[... output truncated at {max} lines ...]"


def make_file_read_handler(repo_root: Path) -> Callable[[dict], str]:  # type: ignore[type-arg]
    """Return a file_read handler bound to ``repo_root``.

    Handler args:
        path (str): Relative path to the file (e.g. ``"src/main.py"``).
        start_line (int, optional): 1-indexed start line. Defaults to 1.
        end_line (int, optional): 1-indexed end line (inclusive).
            Defaults to end of file.

    Returns:
        Observation string with numbered lines, or an error description.
    """

    def handler(args: dict) -> str:  # type: ignore[type-arg]
        raw_path = args.get("path", "")
        if not raw_path:
            return "[ERROR] file_read: 'path' argument is required."

        abs_path = (repo_root / raw_path).resolve()

        # Sandbox: reject paths outside the repo root
        try:
            abs_path.relative_to(repo_root.resolve())
        except ValueError:
            return f"[ERROR] file_read: path '{raw_path}' is outside the repository root."

        if not abs_path.exists():
            return f"[ERROR] file_read: file '{raw_path}' does not exist."
        if not abs_path.is_file():
            return f"[ERROR] file_read: '{raw_path}' is not a file."

        try:
            lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return f"[ERROR] file_read: could not read '{raw_path}': {exc}"

        total = len(lines)
        start = max(1, int(args.get("start_line", 1))) - 1  # convert to 0-indexed
        end = min(total, int(args.get("end_line", total)))   # 1-indexed inclusive

        if start >= total:
            return f"[ERROR] file_read: start_line {start + 1} exceeds file length ({total})."

        selected = lines[start:end]
        truncated = False
        if len(selected) > _MAX_LINES:
            selected = selected[:_MAX_LINES]
            truncated = True

        numbered = "\n".join(
            f"{start + i + 1}: {line}" for i, line in enumerate(selected)
        )
        header = f"### {raw_path} (lines {start + 1}-{start + len(selected)} of {total})"
        result = f"{header}\n\n{numbered}"
        if truncated:
            result += _TRUNCATION_MESSAGE.format(max=_MAX_LINES)
        return result

    return handler
