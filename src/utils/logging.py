"""Structured JSON logging and audit trail for code-reviewer (§8.2.1, §1.3).

Usage:
    from src.utils.logging import get_logger, get_audit_logger

    log = get_logger(__name__)
    log.info("Indexing started", extra={"project_id": "abc"})

    audit = get_audit_logger(task_id="task-123", audit_dir=Path(".code-reviewer/audit"))
    audit.log("TOOL_CALL", {"tool": "file_read", "path": "src/main.py"})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path
from typing import Any


# ─── JSON formatter ──────────────────────────────────────────────────────────


class _JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line (JSON Lines format)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach any extra fields passed via extra={}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


# ─── Application logger ───────────────────────────────────────────────────────

_configured: bool = False


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    log_dir: Path | None = None,
    max_bytes: int = 52_428_800,
    backup_count: int = 5,
) -> None:
    """Configure the root logger. Call once at application startup.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
        fmt: Output format — "json" or "text".
        log_dir: Directory for rotating file logs. None disables file logging.
        max_bytes: Max file size before rotation.
        backup_count: Number of rotated backups to keep.
    """
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler
    console = logging.StreamHandler()
    if fmt == "json":
        console.setFormatter(_JSONFormatter())
    else:
        console.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s")
        )
    root.addHandler(console)

    # Rotating file handler (optional)
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "code-reviewer.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(_JSONFormatter())
        root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Call configure_logging() first.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        Standard Python Logger instance.
    """
    return logging.getLogger(name)


# ─── Audit trail logger ───────────────────────────────────────────────────────


class AuditLogger:
    """Append-only audit trail for a single agent task.

    Writes one JSON object per line to .code-reviewer/audit/<task_id>.jsonl.
    The file is opened in append mode and is never overwritten.

    Args:
        task_id: UUID of the task being audited.
        audit_dir: Directory to store audit files.
    """

    def __init__(self, task_id: str, audit_dir: Path) -> None:
        self._task_id = task_id
        audit_dir.mkdir(parents=True, exist_ok=True)
        self._path = audit_dir / f"{task_id}.jsonl"
        # Open in append mode — never truncate existing content
        self._file = self._path.open("a", encoding="utf-8")

    def log(self, event_type: str, details: dict[str, Any]) -> None:
        """Append an audit event.

        Args:
            event_type: Constant like "TOOL_CALL", "LLM_REQUEST", "FILE_WRITE".
            details: Arbitrary JSON-serialisable event data.
        """
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "task_id": self._task_id,
            "event_type": event_type,
            "details": details,
        }
        self._file.write(json.dumps(entry, default=str) + "\n")
        self._file.flush()  # ensure durability; audit trail must not buffer

    def close(self) -> None:
        """Close the audit file. Call when the task completes."""
        self._file.close()

    def __enter__(self) -> "AuditLogger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def get_audit_logger(task_id: str, audit_dir: Path) -> AuditLogger:
    """Create an audit logger for the given task.

    Args:
        task_id: UUID of the agent task.
        audit_dir: Base directory for audit files (e.g. Path(".code-reviewer/audit")).

    Returns:
        AuditLogger instance. Must be closed after use (supports context manager).
    """
    return AuditLogger(task_id=task_id, audit_dir=audit_dir)
