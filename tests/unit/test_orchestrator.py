"""Unit tests for Phase 2.2: ReAct Agent Loop.

Covers:
  - AgentIterationResponse / OrchestratorResult Pydantic schemas
  - ConversationHistory: append, to_messages, token-budget summarisation
  - output_parser: JSON extraction, validation, repair, reprompt, salvage
  - Orchestrator main loop: submit_proposal, give_up, iteration limit,
    token budget, LLM errors, validation retry chain
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.agent.history import ConversationHistory, _summarise_entries
from src.agent.orchestrator import Orchestrator
from src.agent.output_parser import (
    build_validation_error_reprompt,
    extract_json,
    parse_iteration_response,
    try_salvage_partial,
)
from src.agent.prompt_assembler import TaskType
from src.agent.schemas import (
    AgentIterationResponse,
    HistoryEntry,
    OrchestratorResult,
    ToolAction,
)
from src.llm.client import LLMResponse
from src.utils.errors import LLMBudgetExhaustedError, LLMError, SchemaValidationError

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_llm_response(content: str, tokens: int = 50) -> LLMResponse:
    return LLMResponse(
        content=content,
        input_tokens=tokens,
        output_tokens=tokens,
        model="gpt-4o",
        latency_ms=100.0,
    )


def _make_valid_json(tool: str = "file_read", args: dict[str, Any] | None = None) -> str:
    return json.dumps({
        "thought": "I need to read the file.",
        "action": {"tool": tool, "args": args or {"path": "src/main.py"}},
    })


def _make_tool_action(tool: str = "file_read") -> ToolAction:
    return ToolAction(tool=tool, args={"path": "src/main.py"})


def _make_history_entry(tool: str = "file_read", obs: str = "file content") -> HistoryEntry:
    return HistoryEntry(
        thought="Reading the file.",
        action=_make_tool_action(tool),
        observation=obs,
    )


# ─── Pydantic schemas ─────────────────────────────────────────────────────────


class TestToolAction:
    def test_valid_tool_action(self) -> None:
        ta = ToolAction(tool="file_read", args={"path": "src/a.py"})
        assert ta.tool == "file_read"
        assert ta.args == {"path": "src/a.py"}

    def test_default_empty_args(self) -> None:
        ta = ToolAction(tool="give_up")
        assert ta.args == {}

    def test_tool_required(self) -> None:
        with pytest.raises(ValidationError):
            ToolAction.model_validate({})


class TestAgentIterationResponse:
    def test_valid_response(self) -> None:
        r = AgentIterationResponse.model_validate({
            "thought": "I should read the file.",
            "action": {"tool": "file_read", "args": {}},
        })
        assert r.thought == "I should read the file."

    def test_thought_required(self) -> None:
        with pytest.raises(ValidationError):
            AgentIterationResponse.model_validate({"action": {"tool": "file_read"}})

    def test_thought_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            AgentIterationResponse.model_validate({
                "thought": "",
                "action": {"tool": "file_read"},
            })


class TestOrchestratorResult:
    def test_valid_completed(self) -> None:
        r = OrchestratorResult(
            status="COMPLETED",
            task_id="abc",
            iterations_used=3,
            tokens_used=1500,
            proposal={"title": "Fix bug"},
        )
        assert r.status == "COMPLETED"
        assert r.proposal == {"title": "Fix bug"}

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorResult(
                status="UNKNOWN",
                task_id="abc",
                iterations_used=1,
                tokens_used=100,
            )


# ─── ConversationHistory ──────────────────────────────────────────────────────


class TestConversationHistory:
    def test_initially_empty(self) -> None:
        h = ConversationHistory()
        assert len(h) == 0
        assert h.to_messages() == []

    def test_append_and_len(self) -> None:
        h = ConversationHistory()
        h.append("thought", _make_tool_action(), "observation")
        assert len(h) == 1

    def test_entries_returns_copy(self) -> None:
        h = ConversationHistory()
        h.append("thought", _make_tool_action(), "obs")
        entries = h.entries
        entries.clear()
        assert len(h) == 1  # internal state unchanged

    def test_to_messages_returns_user_assistant_pairs(self) -> None:
        h = ConversationHistory()
        h.append("I will read a file.", _make_tool_action("file_read"), "file contents here")
        msgs = h.to_messages()
        roles = [m["role"] for m in msgs]
        assert "assistant" in roles
        assert "user" in roles

    def test_observation_in_messages(self) -> None:
        h = ConversationHistory()
        h.append("thinking", _make_tool_action(), "UNIQUE_OBSERVATION_XYZ")
        msgs = h.to_messages()
        all_content = " ".join(m["content"] for m in msgs)
        assert "UNIQUE_OBSERVATION_XYZ" in all_content

    def test_keeps_last_3_full_verbatim(self) -> None:
        # Use tiny budget to force summarisation of older entries
        h = ConversationHistory(token_budget=50)
        for i in range(6):
            h.append(f"thought {i}", _make_tool_action(), f"observation {i}")
        msgs = h.to_messages()
        all_content = " ".join(m["content"] for m in msgs)
        # Last 3 observations must appear
        for i in (3, 4, 5):
            assert f"observation {i}" in all_content

    def test_older_entries_compressed_when_over_budget(self) -> None:
        h = ConversationHistory(token_budget=20)  # very tight
        for i in range(6):
            h.append(f"thought {i}", _make_tool_action(), f"observation {i}")
        msgs = h.to_messages()
        all_content = " ".join(m["content"] for m in msgs)
        # A summary block should appear for the very old entries
        assert "Prior steps summary" in all_content or len(msgs) <= 8

    def test_summarise_entries_format(self) -> None:
        entries = [_make_history_entry("file_read", "result A")]
        summary = _summarise_entries(entries)
        assert "Prior steps summary" in summary
        assert "file_read" in summary


# ─── output_parser ────────────────────────────────────────────────────────────


class TestExtractJson:
    def test_plain_json_string(self) -> None:
        raw = '{"thought": "hi", "action": {"tool": "file_read", "args": {}}}'
        data = extract_json(raw)
        assert data["thought"] == "hi"

    def test_json_in_fence(self) -> None:
        raw = '```json\n{"thought": "hi", "action": {"tool": "file_read", "args": {}}}\n```'
        data = extract_json(raw)
        assert data["thought"] == "hi"

    def test_trailing_comma_repair(self) -> None:
        raw = '{"thought": "hi", "action": {"tool": "file_read", "args": {}},}'
        data = extract_json(raw)
        assert data["thought"] == "hi"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(SchemaValidationError):
            extract_json("not json at all <<<")


class TestParseIterationResponse:
    def test_valid_parse(self) -> None:
        raw = _make_valid_json("vector_search", {"query": "auth"})
        parsed = parse_iteration_response(raw)
        assert parsed.action.tool == "vector_search"

    def test_missing_thought_raises(self) -> None:
        raw = json.dumps({"action": {"tool": "file_read", "args": {}}})
        with pytest.raises(SchemaValidationError):
            parse_iteration_response(raw)

    def test_submit_proposal_parses(self) -> None:
        raw = _make_valid_json("submit_proposal", {"title": "Fix bug"})
        parsed = parse_iteration_response(raw)
        assert parsed.action.tool == "submit_proposal"


class TestBuildValidationErrorReprompt:
    def test_attempt_1_mentions_error(self) -> None:
        err = SchemaValidationError("missing 'thought'")
        msgs = build_validation_error_reprompt("bad json", err, 1)
        assert len(msgs) == 1
        assert "missing 'thought'" in msgs[0]["content"]

    def test_attempt_2_includes_few_shot(self) -> None:
        err = SchemaValidationError("still bad")
        msgs = build_validation_error_reprompt("bad json", err, 2)
        # Should include the format_correction example (user + assistant + user)
        roles = [m["role"] for m in msgs]
        assert "assistant" in roles


class TestTrySalvagePartial:
    def test_salvages_dict_with_thought(self) -> None:
        raw = json.dumps({"thought": "I was thinking...", "extra": "data"})
        result = try_salvage_partial(raw)
        assert result is not None
        assert result["thought"] == "I was thinking..."

    def test_returns_none_for_garbage(self) -> None:
        result = try_salvage_partial("not json at all !!!")
        assert result is None

    def test_returns_none_for_json_without_thought(self) -> None:
        raw = json.dumps({"action": {"tool": "file_read"}})
        result = try_salvage_partial(raw)
        assert result is None


# ─── Orchestrator ─────────────────────────────────────────────────────────────


def _make_orchestrator(
    tmp_path: Path,
    llm: Any,
    tool_registry: Any | None = None,
    task_type: TaskType = TaskType.REFACTOR,
    max_iterations: int = 5,
    token_budget: int = 100_000,
) -> Orchestrator:
    if tool_registry is None:
        tool_registry = lambda tool, args: f"OK: {tool} called"  # noqa: E731
    return Orchestrator(
        llm=llm,
        tool_registry=tool_registry,
        task_type=task_type,
        repo_root=tmp_path,
        max_iterations=max_iterations,
        token_budget=token_budget,
    )


class TestOrchestratorSubmitProposal:
    def test_submit_proposal_on_first_iteration(self, tmp_path: Path) -> None:
        llm = MagicMock()
        proposal_args = {"title": "Rename variable"}
        llm.generate.return_value = _make_llm_response(
            _make_valid_json("submit_proposal", proposal_args)
        )
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run(task_id="t1")

        assert result.status == "COMPLETED"
        assert result.task_id == "t1"
        assert result.iterations_used == 1
        assert result.proposal == proposal_args

    def test_submit_proposal_after_tool_calls(self, tmp_path: Path) -> None:
        llm = MagicMock()
        # iter 1: file_read, iter 2: submit_proposal
        llm.generate.side_effect = [
            _make_llm_response(_make_valid_json("file_read")),
            _make_llm_response(_make_valid_json("submit_proposal", {"title": "Done"})),
        ]
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run()
        assert result.status == "COMPLETED"
        assert result.iterations_used == 2


class TestOrchestratorGiveUp:
    def test_give_up_marks_failed(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.return_value = _make_llm_response(
            _make_valid_json("give_up", {"reason": "Cannot locate root cause"})
        )
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run()
        assert result.status == "FAILED"
        assert result.give_up_reason == "Cannot locate root cause"

    def test_give_up_logs_reason(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.return_value = _make_llm_response(
            _make_valid_json("give_up", {"reason": "Reason XYZ"})
        )
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run()
        assert "Reason XYZ" in (result.give_up_reason or "")


class TestOrchestratorIterationLimit:
    def test_iteration_limit_returns_failed(self, tmp_path: Path) -> None:
        llm = MagicMock()
        # Always returns a tool call (never submits)
        llm.generate.return_value = _make_llm_response(_make_valid_json("file_read"))
        orch = _make_orchestrator(tmp_path, llm, max_iterations=3)
        result = orch.run()
        assert result.status == "FAILED"
        assert result.iterations_used == 3
        assert "max iteration" in (result.error_message or "").lower()

    def test_llm_called_max_iterations_times(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.return_value = _make_llm_response(_make_valid_json("file_read"))
        orch = _make_orchestrator(tmp_path, llm, max_iterations=3)
        orch.run()
        assert llm.generate.call_count == 3


class TestOrchestratorTokenBudget:
    def test_token_budget_reached_returns_failed(self, tmp_path: Path) -> None:
        llm = MagicMock()
        # Each call uses 1000 tokens; budget is 500 so exceeded after first
        llm.generate.return_value = _make_llm_response(
            _make_valid_json("file_read"), tokens=300
        )
        orch = _make_orchestrator(tmp_path, llm, token_budget=500)
        result = orch.run()
        assert result.status == "FAILED"
        assert "budget" in (result.error_message or "").lower()


class TestOrchestratorLLMErrors:
    def test_llm_error_returns_failed(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.side_effect = LLMError("Rate limit exceeded")
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run()
        assert result.status == "FAILED"
        assert "Rate limit" in (result.error_message or "")

    def test_budget_exhausted_error_returns_failed(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.side_effect = LLMBudgetExhaustedError("Budget gone")
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run()
        assert result.status == "FAILED"


class TestOrchestratorValidationRetry:
    def test_validation_failure_retried_and_succeeds(self, tmp_path: Path) -> None:
        llm = MagicMock()
        bad_response = "not json"
        good_response = _make_valid_json("submit_proposal", {"title": "OK"})
        llm.generate.side_effect = [
            _make_llm_response(bad_response),    # first attempt → bad
            _make_llm_response(good_response),   # recovery reprompt → good
        ]
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run()
        assert result.status == "COMPLETED"

    def test_all_attempts_fail_returns_failed(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.return_value = _make_llm_response("not json")
        orch = _make_orchestrator(tmp_path, llm, max_iterations=1)
        result = orch.run()
        assert result.status in ("FAILED", "PARTIAL")


class TestOrchestratorToolDispatch:
    def test_tool_observation_passed_to_history(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.side_effect = [
            _make_llm_response(_make_valid_json("file_read")),
            _make_llm_response(_make_valid_json("submit_proposal", {"title": "done"})),
        ]
        observations = []
        def registry(tool: str, args: dict[str, Any]) -> str:
            obs = f"Result of {tool}"
            observations.append(obs)
            return obs

        orch = _make_orchestrator(tmp_path, llm, tool_registry=registry)
        result = orch.run()
        assert result.status == "COMPLETED"
        assert len(observations) == 1

    def test_tool_error_returned_as_observation(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.side_effect = [
            _make_llm_response(_make_valid_json("file_read")),
            _make_llm_response(_make_valid_json("submit_proposal", {"title": "done"})),
        ]
        def registry(tool: str, args: dict[str, Any]) -> str:
            raise ValueError("File not found")

        orch = _make_orchestrator(tmp_path, llm, tool_registry=registry)
        result = orch.run()
        # Should not crash — error is treated as observation
        assert result.status == "COMPLETED"

    def test_auto_generates_task_id(self, tmp_path: Path) -> None:
        llm = MagicMock()
        llm.generate.return_value = _make_llm_response(
            _make_valid_json("submit_proposal", {"title": "ok"})
        )
        orch = _make_orchestrator(tmp_path, llm)
        result = orch.run()
        assert result.task_id
        assert len(result.task_id) == 36  # UUID format
