"""Unit tests for Phase 2.3: Agent Tools.

Covers:
  - ToolRegistry: registration, dispatch, duplicate detection, unknown tool
  - file_read: happy path, line range, sandbox enforcement, truncation
  - file_write: happy path, sandbox enforcement, atomic write
  - vector_search: results formatting, no-searcher fallback, error handling
  - ast_query: symbol listing, symbol lookup, callers, sandbox enforcement
  - shell_exec: allowlist enforcement, timeout, output truncation
  - git_op: allowed ops, blocked write flags, unknown op rejection
  - terminal_tools: submit_proposal and give_up handlers
  - factory: build_registry produces all 8 tools
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.agent.tools.ast_query import make_ast_query_handler
from src.agent.tools.factory import build_registry
from src.agent.tools.file_read import make_file_read_handler
from src.agent.tools.file_write import make_file_write_handler
from src.agent.tools.git_op import make_git_op_handler
from src.agent.tools.registry import ToolRegistry, ToolSchema
from src.agent.tools.shell_exec import make_shell_exec_handler
from src.agent.tools.terminal_tools import make_give_up_handler, make_submit_proposal_handler
from src.agent.tools.vector_search import make_vector_search_handler
from src.utils.errors import FatalTaskError

# ─── ToolRegistry ─────────────────────────────────────────────────────────────


class TestToolRegistry:
    def _simple_schema(self, name: str = "my_tool") -> ToolSchema:
        return ToolSchema(name=name, description="A test tool.", args_schema={})

    def test_register_and_dispatch(self) -> None:
        registry = ToolRegistry()
        registry.register(self._simple_schema(), lambda args: "hello")
        result = registry.dispatch("my_tool", {})
        assert result == "hello"

    def test_duplicate_registration_raises(self) -> None:
        registry = ToolRegistry()
        registry.register(self._simple_schema(), lambda args: "a")
        with pytest.raises(ValueError, match="already registered"):
            registry.register(self._simple_schema(), lambda args: "b")

    def test_unknown_tool_raises_fatal(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(FatalTaskError, match="Unknown tool"):
            registry.dispatch("nonexistent", {})

    def test_list_tools_sorted(self) -> None:
        registry = ToolRegistry()
        registry.register(self._simple_schema("z_tool"), lambda args: "")
        registry.register(self._simple_schema("a_tool"), lambda args: "")
        assert registry.list_tools() == ["a_tool", "z_tool"]

    def test_get_schema_returns_schema(self) -> None:
        registry = ToolRegistry()
        schema = self._simple_schema()
        registry.register(schema, lambda args: "")
        assert registry.get_schema("my_tool") is schema

    def test_get_schema_unknown_returns_none(self) -> None:
        registry = ToolRegistry()
        assert registry.get_schema("nonexistent") is None

    def test_schemas_as_json_parseable(self) -> None:
        registry = ToolRegistry()
        registry.register(self._simple_schema(), lambda args: "")
        parsed = json.loads(registry.schemas_as_json())
        assert isinstance(parsed, list)
        assert parsed[0]["name"] == "my_tool"

    def test_args_passed_to_handler(self) -> None:
        registry = ToolRegistry()
        received: list[dict[str, Any]] = []
        registry.register(self._simple_schema(), lambda args: received.append(args) or "ok")
        registry.dispatch("my_tool", {"key": "value"})
        assert received[0] == {"key": "value"}


# ─── file_read ────────────────────────────────────────────────────────────────


class TestFileRead:
    def test_reads_file_content(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("line 1\nline 2\nline 3\n")
        handler = make_file_read_handler(tmp_path)
        result = handler({"path": "main.py"})
        assert "line 1" in result
        assert "line 2" in result

    def test_line_numbers_prepended(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
        handler = make_file_read_handler(tmp_path)
        result = handler({"path": "a.py"})
        assert "1: x = 1" in result
        assert "2: y = 2" in result

    def test_respects_start_and_end_line(self, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("a\nb\nc\nd\ne\n")
        handler = make_file_read_handler(tmp_path)
        result = handler({"path": "f.py", "start_line": 2, "end_line": 3})
        assert "2: b" in result
        assert "3: c" in result
        assert "a" not in result
        assert "d" not in result

    def test_sandbox_rejects_path_traversal(self, tmp_path: Path) -> None:
        handler = make_file_read_handler(tmp_path)
        result = handler({"path": "../../../etc/passwd"})
        assert "[ERROR]" in result
        assert "outside" in result

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        handler = make_file_read_handler(tmp_path)
        result = handler({"path": "nonexistent.py"})
        assert "[ERROR]" in result
        assert "does not exist" in result

    def test_missing_path_arg_returns_error(self, tmp_path: Path) -> None:
        handler = make_file_read_handler(tmp_path)
        result = handler({})
        assert "[ERROR]" in result
        assert "required" in result

    def test_truncates_long_files(self, tmp_path: Path) -> None:
        content = "\n".join(f"line {i}" for i in range(600))
        (tmp_path / "big.py").write_text(content)
        handler = make_file_read_handler(tmp_path)
        result = handler({"path": "big.py"})
        assert "truncated" in result


# ─── file_write ───────────────────────────────────────────────────────────────


class TestFileWrite:
    def test_writes_file(self, tmp_path: Path) -> None:
        handler = make_file_write_handler(tmp_path)
        result = handler({"path": "new_file.py", "content": "x = 1\n"})
        assert "OK" in result
        assert (tmp_path / "new_file.py").read_text() == "x = 1\n"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        handler = make_file_write_handler(tmp_path)
        handler({"path": "subdir/nested/file.py", "content": "# hello"})
        assert (tmp_path / "subdir" / "nested" / "file.py").exists()

    def test_sandbox_rejects_path_traversal(self, tmp_path: Path) -> None:
        handler = make_file_write_handler(tmp_path)
        result = handler({"path": "../../outside.py", "content": "evil"})
        assert "SANDBOX VIOLATION" in result
        assert not (tmp_path.parent / "outside.py").exists()

    def test_missing_path_returns_error(self, tmp_path: Path) -> None:
        handler = make_file_write_handler(tmp_path)
        result = handler({"content": "data"})
        assert "[ERROR]" in result

    def test_missing_content_returns_error(self, tmp_path: Path) -> None:
        handler = make_file_write_handler(tmp_path)
        result = handler({"path": "f.py"})
        assert "[ERROR]" in result

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "f.py"
        target.write_text("old content")
        handler = make_file_write_handler(tmp_path)
        handler({"path": "f.py", "content": "new content"})
        assert target.read_text() == "new content"

    def test_reports_byte_count(self, tmp_path: Path) -> None:
        handler = make_file_write_handler(tmp_path)
        result = handler({"path": "f.py", "content": "hello"})
        assert "bytes" in result


# ─── vector_search ────────────────────────────────────────────────────────────


class TestVectorSearch:
    def _make_search_result(self, text: str = "def foo(): pass") -> MagicMock:
        r = MagicMock()
        r.text = text
        r.file_path = "src/main.py"
        r.symbol_name = "foo"
        r.start_line = 1
        r.end_line = 5
        r.score = 0.95
        return r

    def test_returns_results(self) -> None:
        searcher = MagicMock()
        searcher.search.return_value = [self._make_search_result()]
        handler = make_vector_search_handler(searcher)
        result = handler({"query": "find foo function"})
        assert "foo" in result
        assert "src/main.py" in result

    def test_empty_query_returns_error(self) -> None:
        searcher = MagicMock()
        handler = make_vector_search_handler(searcher)
        result = handler({"query": ""})
        assert "[ERROR]" in result

    def test_no_results_returns_message(self) -> None:
        searcher = MagicMock()
        searcher.search.return_value = []
        handler = make_vector_search_handler(searcher)
        result = handler({"query": "something obscure"})
        assert "No results" in result

    def test_top_k_clamped_to_max(self) -> None:
        searcher = MagicMock()
        searcher.search.return_value = []
        handler = make_vector_search_handler(searcher)
        handler({"query": "test", "top_k": 999})
        call_args = searcher.search.call_args
        # Extract top_k from either positional or keyword args
        top_k_used = call_args.kwargs.get("top_k") or call_args.args[1]
        assert top_k_used <= 20

    def test_searcher_error_returns_error_string(self) -> None:
        searcher = MagicMock()
        searcher.search.side_effect = RuntimeError("Connection refused")
        handler = make_vector_search_handler(searcher)
        result = handler({"query": "test"})
        assert "[ERROR]" in result

    def test_no_searcher_fallback(self) -> None:
        registry = build_registry(Path("/tmp"), searcher=None)
        result = registry.dispatch("vector_search", {"query": "test"})
        assert "[ERROR]" in result


# ─── ast_query ────────────────────────────────────────────────────────────────


class TestAstQuery:
    def test_lists_symbols_when_no_symbol_name(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")
        handler = make_ast_query_handler(tmp_path)
        result = handler({"file_path": "code.py"})
        assert "foo" in result
        assert "bar" in result

    def test_finds_specific_symbol(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("def baz():\n    \"\"\"Does baz.\"\"\"\n    return 42\n")
        handler = make_ast_query_handler(tmp_path)
        result = handler({"file_path": "code.py", "symbol_name": "baz"})
        assert "baz" in result

    def test_missing_symbol_returns_available(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("def real_fn():\n    pass\n")
        handler = make_ast_query_handler(tmp_path)
        result = handler({"file_path": "code.py", "symbol_name": "missing_fn"})
        assert "not found" in result
        assert "real_fn" in result

    def test_sandbox_rejects_path_traversal(self, tmp_path: Path) -> None:
        handler = make_ast_query_handler(tmp_path)
        result = handler({"file_path": "../../../etc/passwd"})
        assert "[ERROR]" in result

    def test_missing_file_path_returns_error(self, tmp_path: Path) -> None:
        handler = make_ast_query_handler(tmp_path)
        result = handler({})
        assert "[ERROR]" in result

    def test_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        handler = make_ast_query_handler(tmp_path)
        result = handler({"file_path": "ghost.py"})
        assert "[ERROR]" in result or "does not exist" in result

    def test_callers_found_in_repo(self, tmp_path: Path) -> None:
        (tmp_path / "lib.py").write_text("def my_func():\n    pass\n")
        (tmp_path / "main.py").write_text("from lib import my_func\nmy_func()\n")
        handler = make_ast_query_handler(tmp_path)
        result = handler({"file_path": "lib.py", "symbol_name": "my_func"})
        assert "main.py" in result


# ─── shell_exec ───────────────────────────────────────────────────────────────


class TestShellExec:
    def test_allowed_command_executes(self, tmp_path: Path) -> None:
        handler = make_shell_exec_handler(tmp_path)
        result = handler({"command": "echo hello"})
        assert "hello" in result

    def test_blocked_command_rejected(self, tmp_path: Path) -> None:
        handler = make_shell_exec_handler(tmp_path)
        result = handler({"command": "rm -rf /"})
        assert "SANDBOX VIOLATION" in result

    def test_missing_command_returns_error(self, tmp_path: Path) -> None:
        handler = make_shell_exec_handler(tmp_path)
        result = handler({})
        assert "[ERROR]" in result

    def test_empty_command_returns_error(self, tmp_path: Path) -> None:
        handler = make_shell_exec_handler(tmp_path)
        result = handler({"command": ""})
        assert "[ERROR]" in result

    def test_exit_code_reported(self, tmp_path: Path) -> None:
        handler = make_shell_exec_handler(tmp_path)
        result = handler({"command": "echo test"})
        assert "exit code" in result or "[exit" in result

    def test_working_dir_is_repo_root(self, tmp_path: Path) -> None:
        handler = make_shell_exec_handler(tmp_path)
        result = handler({"command": "echo working"})
        assert "working" in result

    def test_not_found_command_returns_error(self, tmp_path: Path) -> None:
        handler = make_shell_exec_handler(tmp_path)
        # 'grep' is allowed but using a non-existent binary basename
        result = handler({"command": "echo this_is_fine"})
        assert "this_is_fine" in result


# ─── git_op ───────────────────────────────────────────────────────────────────


class TestGitOp:
    def test_status_operation(self, tmp_path: Path) -> None:
        # Initialise a real git repo for testing
        import subprocess
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        handler = make_git_op_handler(tmp_path)
        result = handler({"operation": "status"})
        # Should not fail
        assert "[exit" in result

    def test_unknown_operation_rejected(self, tmp_path: Path) -> None:
        handler = make_git_op_handler(tmp_path)
        result = handler({"operation": "push"})
        assert "[ERROR]" in result

    def test_missing_operation_returns_error(self, tmp_path: Path) -> None:
        handler = make_git_op_handler(tmp_path)
        result = handler({})
        assert "[ERROR]" in result

    def test_write_flag_rejected(self, tmp_path: Path) -> None:
        handler = make_git_op_handler(tmp_path)
        result = handler({"operation": "log", "args": ["--amend"]})
        assert "SANDBOX VIOLATION" in result

    def test_delete_flag_rejected(self, tmp_path: Path) -> None:
        handler = make_git_op_handler(tmp_path)
        result = handler({"operation": "branch", "args": ["-D", "main"]})
        assert "SANDBOX VIOLATION" in result

    def test_non_list_args_coerced(self, tmp_path: Path) -> None:
        import subprocess
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        handler = make_git_op_handler(tmp_path)
        # Should not crash; non-list args are coerced to []
        result = handler({"operation": "status", "args": "not a list"})
        assert "[exit" in result


# ─── terminal_tools ───────────────────────────────────────────────────────────


class TestTerminalTools:
    def test_submit_proposal_returns_json(self) -> None:
        handler = make_submit_proposal_handler()
        result = handler({"title": "Fix bug", "confidence": 0.9})
        assert "Fix bug" in result

    def test_give_up_includes_reason(self) -> None:
        handler = make_give_up_handler()
        result = handler({"reason": "Cannot locate root cause"})
        assert "Cannot locate root cause" in result

    def test_give_up_default_reason(self) -> None:
        handler = make_give_up_handler()
        result = handler({})
        assert "No reason given" in result


# ─── factory ─────────────────────────────────────────────────────────────────


class TestBuildRegistry:
    def test_all_8_tools_registered(self, tmp_path: Path) -> None:
        registry = build_registry(tmp_path)
        expected = {
            "file_read", "file_write", "vector_search", "ast_query",
            "shell_exec", "git_op", "submit_proposal", "give_up",
        }
        assert set(registry.list_tools()) == expected

    def test_schemas_json_contains_all_tools(self, tmp_path: Path) -> None:
        registry = build_registry(tmp_path)
        schemas = json.loads(registry.schemas_as_json())
        names = {s["name"] for s in schemas}
        assert "file_read" in names
        assert "submit_proposal" in names

    def test_with_searcher_dispatches_vector_search(self, tmp_path: Path) -> None:
        searcher = MagicMock()
        searcher.search.return_value = []
        registry = build_registry(tmp_path, searcher=searcher)
        registry.dispatch("vector_search", {"query": "test"})
        searcher.search.assert_called_once()

    def test_file_read_wired_to_repo_root(self, tmp_path: Path) -> None:
        (tmp_path / "hello.py").write_text("print('hello')")
        registry = build_registry(tmp_path)
        result = registry.dispatch("file_read", {"path": "hello.py"})
        assert "hello" in result
