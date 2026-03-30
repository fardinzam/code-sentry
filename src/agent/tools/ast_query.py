"""ast_query tool: query AST for function/class definitions and callers.

Uses the existing tree-sitter parser to extract named symbols from a file
and find call sites within the repository.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from src.indexing.parser import parse_python_file
from src.utils.logging import get_logger

logger = get_logger(__name__)

_MAX_CALLERS = 20
_CALLER_FILE_LIMIT = 200


def make_ast_query_handler(repo_root: Path) -> Callable[[dict], str]:  # type: ignore[type-arg]
    """Return an ast_query handler bound to ``repo_root``.

    Handler args:
        file_path (str): Relative path to the Python source file.
        symbol_name (str): Function or class name to look up. If empty,
            returns all top-level symbols in the file.

    Returns:
        Observation string describing the located symbol(s) and callers.
    """

    def handler(args: dict) -> str:  # type: ignore[type-arg]
        raw_path = args.get("file_path", "")
        symbol_name = args.get("symbol_name", "").strip()

        if not raw_path:
            return "[ERROR] ast_query: 'file_path' argument is required."

        abs_path = (repo_root / raw_path).resolve()
        try:
            abs_path.relative_to(repo_root.resolve())
        except ValueError:
            return f"[ERROR] ast_query: '{raw_path}' is outside the repository root."

        if not abs_path.exists():
            return f"[ERROR] ast_query: file '{raw_path}' does not exist."

        try:
            symbols = parse_python_file(abs_path)
        except Exception as exc:
            return f"[ERROR] ast_query: failed to parse '{raw_path}': {exc}"

        if not symbols:
            return f"No symbols found in '{raw_path}'."

        # If no symbol_name, list all symbols
        if not symbol_name:
            lines = [f"## Symbols in `{raw_path}`\n"]
            for sym in symbols:
                lines.append(
                    f"- **{sym.symbol_type}** `{sym.name}` "
                    f"(lines {sym.start_line}-{sym.end_line})"
                    + (f"\n  > {sym.docstring[:120]}" if sym.docstring else "")
                )
            return "\n".join(lines)

        # Find matching symbol(s) (case-sensitive, allow partial class.method match)
        matches = [
            s for s in symbols
            if s.name == symbol_name
            or s.name.endswith(f".{symbol_name}")
        ]
        if not matches:
            available = [s.name for s in symbols]
            return (
                f"Symbol '{symbol_name}' not found in '{raw_path}'.\n"
                f"Available symbols: {available}"
            )

        lines = []
        for match in matches:
            lines.append(
                f"## `{match.name}` ({match.symbol_type}) "
                f"in `{raw_path}` - lines {match.start_line}-{match.end_line}"
            )
            if match.docstring:
                lines.append(f"**Docstring:** {match.docstring}")
            if match.parent_class:
                lines.append(f"**Enclosing class:** `{match.parent_class}`")
            lines.append(f"\n```python\n{match.source[:1500]}\n```")

        # Search for callers in the repo
        callers = _find_callers(repo_root, symbol_name)
        if callers:
            lines.append(f"\n## Callers of `{symbol_name}` ({len(callers)} found)")
            for caller_file, caller_line in callers[:_MAX_CALLERS]:
                lines.append(f"- `{caller_file}` line {caller_line}")
            if len(callers) > _MAX_CALLERS:
                lines.append(f"  ... and {len(callers) - _MAX_CALLERS} more")
        else:
            lines.append(f"\nNo callers of `{symbol_name}` found in repository.")

        return "\n".join(lines)

    return handler


def _find_callers(repo_root: Path, symbol_name: str) -> list[tuple[str, int]]:
    """Search for call sites of ``symbol_name`` across Python files in repo.

    Returns a list of (relative_path, line_number) tuples.
    """
    pattern = re.compile(rf"\b{re.escape(symbol_name)}\s*\(")
    callers: list[tuple[str, int]] = []
    py_files = list(repo_root.rglob("*.py"))[:_CALLER_FILE_LIMIT]

    for py_file in py_files:
        try:
            for lineno, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    rel = str(py_file.relative_to(repo_root))
                    callers.append((rel, lineno))
        except OSError:
            continue

    return callers
