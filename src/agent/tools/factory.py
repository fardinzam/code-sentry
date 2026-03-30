"""Factory: build a fully-wired ToolRegistry for a given task (§7.3 FR-3.2).

Usage::

    from src.agent.tools.factory import build_registry
    from src.retrieval.search import HybridSearcher

    registry = build_registry(
        repo_root=Path("/path/to/repo"),
        searcher=my_searcher,         # optional; omit for offline use
    )
    observation = registry.dispatch("file_read", {"path": "src/main.py"})
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.agent.tools.ast_query import make_ast_query_handler
from src.agent.tools.file_read import make_file_read_handler
from src.agent.tools.file_write import make_file_write_handler
from src.agent.tools.git_op import make_git_op_handler
from src.agent.tools.registry import ToolRegistry, ToolSchema
from src.agent.tools.shell_exec import make_shell_exec_handler
from src.agent.tools.terminal_tools import (
    make_give_up_handler,
    make_submit_proposal_handler,
)
from src.agent.tools.vector_search import make_vector_search_handler

if TYPE_CHECKING:
    from src.retrieval.search import HybridSearcher


def build_registry(
    repo_root: Path,
    searcher: HybridSearcher | None = None,
) -> ToolRegistry:
    """Build and return a ``ToolRegistry`` with all agent tools registered.

    Args:
        repo_root: Absolute path to the repository root.
        searcher: Optional ``HybridSearcher`` instance. If omitted,
            ``vector_search`` will return an informative error when called.

    Returns:
        A fully wired ``ToolRegistry`` ready for use by the Orchestrator.
    """
    registry = ToolRegistry()

    # ── file_read ─────────────────────────────────────────────────────────────
    registry.register(
        ToolSchema(
            name="file_read",
            description="Read file contents from the repository.",
            args_schema={
                "path": "str — relative file path (required)",
                "start_line": "int — 1-indexed start line (optional, default: 1)",
                "end_line": "int — 1-indexed end line inclusive (optional, default: EOF)",
            },
        ),
        make_file_read_handler(repo_root),
    )

    # ── file_write ────────────────────────────────────────────────────────────
    registry.register(
        ToolSchema(
            name="file_write",
            description=(
                "Write content to a file within the sandbox branch. "
                "Paths outside the repository root are rejected."
            ),
            args_schema={
                "path": "str — relative file path (required)",
                "content": "str — full file content to write (required)",
            },
        ),
        make_file_write_handler(repo_root),
    )

    # ── vector_search ─────────────────────────────────────────────────────────
    if searcher is not None:
        search_handler = make_vector_search_handler(searcher)
    else:
        def search_handler(args: dict[str, object]) -> str:
            return "[ERROR] vector_search: no searcher configured for this task."

    registry.register(
        ToolSchema(
            name="vector_search",
            description="Semantic search over the indexed codebase.",
            args_schema={
                "query": "str — natural-language or code search query (required)",
                "top_k": "int — maximum results to return (optional, default: 5, max: 20)",
            },
        ),
        search_handler,
    )

    # ── ast_query ─────────────────────────────────────────────────────────────
    registry.register(
        ToolSchema(
            name="ast_query",
            description=(
                "Query AST for function/class definitions and callers. "
                "Returns symbol metadata and call sites."
            ),
            args_schema={
                "file_path": "str — relative path to Python source file (required)",
                "symbol_name": (
                    "str — function or class name to look up (optional; "
                    "if omitted, lists all symbols in the file)"
                ),
            },
        ),
        make_ast_query_handler(repo_root),
    )

    # ── shell_exec ────────────────────────────────────────────────────────────
    registry.register(
        ToolSchema(
            name="shell_exec",
            description=(
                "Run a sandboxed shell command inside the repo directory. "
                "Only allowlisted commands are permitted."
            ),
            args_schema={
                "command": "str — shell command string (required)",
            },
        ),
        make_shell_exec_handler(repo_root),
    )

    # ── git_op ────────────────────────────────────────────────────────────────
    registry.register(
        ToolSchema(
            name="git_op",
            description=(
                "Read-only Git operations: diff, log, show, status, branch."
            ),
            args_schema={
                "operation": "str — one of: diff | log | show | status | branch (required)",
                "args": "list[str] — additional git arguments (optional)",
            },
        ),
        make_git_op_handler(repo_root),
    )

    # ── submit_proposal ───────────────────────────────────────────────────────
    registry.register(
        ToolSchema(
            name="submit_proposal",
            description=(
                "Submit the final proposal. The orchestrator intercepts "
                "this tool and terminates the loop with COMPLETED status."
            ),
            args_schema={
                "title": "str — one-line summary of the proposal",
                "explanation": "str — detailed justification",
                "files_changed": "list — file diffs or modifications",
                "confidence": "float — 0.0-1.0 confidence score",
                "risk_assessment": "str — LOW | MEDIUM | HIGH",
            },
        ),
        make_submit_proposal_handler(),
    )

    # ── give_up ───────────────────────────────────────────────────────────────
    registry.register(
        ToolSchema(
            name="give_up",
            description=(
                "Terminate the task gracefully. Use when you cannot complete "
                "the task. The orchestrator intercepts this and marks FAILED."
            ),
            args_schema={
                "reason": "str — explanation of why the task cannot be completed",
            },
        ),
        make_give_up_handler(),
    )

    return registry
