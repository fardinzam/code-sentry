"""Pydantic models for agent I/O — ReAct iteration schema (§7.10.3).

Every LLM response is validated against one of these models before
the orchestrator acts on it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ─── Tool action ─────────────────────────────────────────────────────────────


class ToolAction(BaseModel):
    """One tool invocation emitted by the agent."""

    tool: str = Field(
        ...,
        description=(
            "Tool name: file_read | vector_search | ast_query | "
            "file_write | shell_exec | git_op | submit_proposal | give_up"
        ),
    )
    args: dict[str, Any] = Field(default_factory=dict)


# ─── ReAct iteration response ─────────────────────────────────────────────────


class AgentIterationResponse(BaseModel):
    """Validated LLM response for a single ReAct iteration (§7.10.3)."""

    thought: str = Field(..., min_length=1)
    action: ToolAction


# ─── History entry ────────────────────────────────────────────────────────────


class HistoryEntry(BaseModel):
    """One completed ReAct iteration stored in conversation history.

    Attributes:
        thought: Agent's reasoning text.
        action: Tool invocation that was made.
        observation: Result returned by the tool.
    """

    thought: str
    action: ToolAction
    observation: str


# ─── Task status ─────────────────────────────────────────────────────────────


class TaskStatus(str):
    """Possible final task statuses."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


# ─── Orchestrator result ─────────────────────────────────────────────────────


class OrchestratorResult(BaseModel):
    """Returned by Orchestrator.run() after the loop terminates."""

    status: str  # COMPLETED | FAILED | PARTIAL
    task_id: str
    iterations_used: int
    tokens_used: int
    proposal: dict[str, Any] | None = None  # set when status == COMPLETED
    give_up_reason: str | None = None  # set when agent called give_up
    error_message: str | None = None  # set on FAILED/PARTIAL

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        allowed = {"RUNNING", "COMPLETED", "FAILED", "PARTIAL"}
        if v not in allowed:
            msg = f"Invalid status '{v}'. Must be one of {allowed}."
            raise ValueError(msg)
        return v
