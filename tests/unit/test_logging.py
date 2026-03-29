"""Unit tests for the structured logger and audit trail (§1.3)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.utils.logging import AuditLogger, configure_logging, get_logger


class TestJSONLogging:
    """Verify JSON log format and rotation configuration."""

    def test_get_logger_returns_standard_logger(self) -> None:
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_configure_logging_is_idempotent(self, tmp_path: Path) -> None:
        """Calling configure_logging twice should not add duplicate handlers."""
        import src.utils.logging as log_module

        log_module._configured = False
        root = logging.getLogger()
        initial_handlers = len(root.handlers)

        configure_logging(level="INFO", fmt="text")
        after_first = len(root.handlers)

        configure_logging(level="DEBUG", fmt="json")  # second call — should be no-op
        after_second = len(root.handlers)

        assert after_first == after_second
        # Clean up
        log_module._configured = False
        for h in root.handlers[initial_handlers:]:
            root.removeHandler(h)

    def test_file_handler_created_when_log_dir_provided(self, tmp_path: Path) -> None:
        import src.utils.logging as log_module

        log_module._configured = False

        configure_logging(level="INFO", fmt="json", log_dir=tmp_path)

        log_file = tmp_path / "code-reviewer.log"
        logger = get_logger("test.file")
        logger.info("test message")

        assert log_file.exists()
        content = log_file.read_text()
        parsed = json.loads(content.strip())
        assert parsed["msg"] == "test message"
        assert parsed["level"] == "INFO"

        # Clean up
        log_module._configured = False
        root = logging.getLogger()
        root.handlers.clear()


class TestAuditLogger:
    """Verify append-only audit trail behaviour."""

    def test_audit_entries_are_written_as_jsonl(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        logger = AuditLogger(task_id="task-001", audit_dir=audit_dir)

        logger.log("TOOL_CALL", {"tool": "file_read", "path": "src/main.py"})
        logger.log("LLM_REQUEST", {"tokens": 500})
        logger.close()

        log_file = audit_dir / "task-001.jsonl"
        assert log_file.exists()

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2

        entry = json.loads(lines[0])
        assert entry["event_type"] == "TOOL_CALL"
        assert entry["task_id"] == "task-001"
        assert entry["details"]["tool"] == "file_read"

    def test_audit_logger_appends_not_overwrites(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"

        # First session
        logger1 = AuditLogger(task_id="task-append", audit_dir=audit_dir)
        logger1.log("SESSION_START", {})
        logger1.close()

        # Second session — must append
        logger2 = AuditLogger(task_id="task-append", audit_dir=audit_dir)
        logger2.log("SESSION_END", {})
        logger2.close()

        lines = (audit_dir / "task-append.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_audit_logger_context_manager(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        with AuditLogger(task_id="task-ctx", audit_dir=audit_dir) as audit:
            audit.log("START", {"x": 1})

        # File should be closed and flushed
        log_file = audit_dir / "task-ctx.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
