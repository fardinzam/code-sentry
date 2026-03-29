"""Unit tests for the prompt assembler (§7.10.1, §7.10.2, §7.10.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.prompt_assembler import (
    TaskType,
    _SafeDict,
    assemble_prompt,
    build_system_prompt,
    get_few_shot_messages,
    load_format_correction_example,
)
from src.retrieval.search import SearchResult

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_result(text: str = "def foo(): pass") -> SearchResult:
    return SearchResult(
        text=text,
        file_path="src/main.py",
        symbol_name="foo",
        start_line=1,
        end_line=5,
        score=0.9,
        metadata={"file_path": "src/main.py"},
    )


# ─── TaskType enum ───────────────────────────────────────────────────────────


class TestTaskType:
    """Task type enum values."""

    def test_all_task_types_defined(self) -> None:
        expected = {"refactor", "bug_fix", "review_pr", "health_scan", "explain"}
        actual = {t.value for t in TaskType}
        assert actual == expected

    def test_task_type_is_string_enum(self) -> None:
        assert TaskType.REFACTOR == "refactor"
        assert isinstance(TaskType.BUG_FIX, str)


# ─── Template loading ────────────────────────────────────────────────────────


class TestBuildSystemPrompt:
    """Test system prompt assembly from templates."""

    def test_contains_common_preamble(self) -> None:
        prompt = build_system_prompt(TaskType.REFACTOR)
        assert "expert software engineer" in prompt
        assert "automated code reviewer" in prompt

    def test_contains_task_extension(self) -> None:
        prompt = build_system_prompt(TaskType.REFACTOR)
        assert "REFACTOR" in prompt
        assert "code smells" in prompt.lower() or "Code Quality" in prompt

    def test_fills_repo_name_placeholder(self) -> None:
        prompt = build_system_prompt(
            TaskType.REFACTOR, repo_name="myorg/myrepo"
        )
        assert "myorg/myrepo" in prompt

    def test_fills_all_common_placeholders(self) -> None:
        prompt = build_system_prompt(
            TaskType.EXPLAIN,
            repo_name="test-repo",
            primary_language="Java",
            default_branch="develop",
            head_sha="abc123",
        )
        assert "test-repo" in prompt
        assert "Java" in prompt
        assert "develop" in prompt
        assert "abc123" in prompt

    def test_extra_vars_fill_task_specific_placeholders(self) -> None:
        prompt = build_system_prompt(
            TaskType.BUG_FIX,
            extra_vars={"bug_description": "NullPointerException in login"},
        )
        assert "NullPointerException in login" in prompt

    def test_explain_fills_user_question(self) -> None:
        prompt = build_system_prompt(
            TaskType.EXPLAIN,
            extra_vars={"user_question": "How does auth work?"},
        )
        assert "How does auth work?" in prompt

    def test_missing_placeholder_preserved(self) -> None:
        """Unfilled placeholders should remain as {key} not raise."""
        prompt = build_system_prompt(TaskType.BUG_FIX)
        assert "{bug_description}" in prompt

    def test_each_task_type_loads_successfully(self) -> None:
        for task_type in TaskType:
            prompt = build_system_prompt(task_type)
            assert len(prompt) > 100

    def test_refactor_mentions_behavior_preservation(self) -> None:
        prompt = build_system_prompt(TaskType.REFACTOR)
        assert "behavior" in prompt.lower() or "NOT change" in prompt

    def test_bug_fix_mentions_root_cause(self) -> None:
        prompt = build_system_prompt(TaskType.BUG_FIX)
        assert "root cause" in prompt.lower()

    def test_review_pr_mentions_inline_comments(self) -> None:
        prompt = build_system_prompt(TaskType.REVIEW_PR)
        assert "inline" in prompt.lower() or "file:line" in prompt

    def test_health_scan_mentions_severity_levels(self) -> None:
        prompt = build_system_prompt(TaskType.HEALTH_SCAN)
        assert "CRITICAL" in prompt
        assert "WARNING" in prompt

    def test_explain_mentions_citations(self) -> None:
        prompt = build_system_prompt(TaskType.EXPLAIN)
        assert "file" in prompt.lower()
        assert "line" in prompt.lower()

    def test_invalid_template_raises_file_not_found(self) -> None:
        """Non-existent task type template should raise."""
        # Create a fake TaskType value to test error handling
        with pytest.raises(FileNotFoundError, match="not found"):
            build_system_prompt(
                TaskType.REFACTOR,
            )
            # Direct template loading test
            from src.agent.prompt_assembler import _load_template
            _load_template("nonexistent_task.txt")


# ─── SafeDict ────────────────────────────────────────────────────────────────


class TestSafeDict:
    """SafeDict returns {key} for missing keys."""

    def test_existing_key_returns_value(self) -> None:
        d = _SafeDict({"name": "test"})
        assert d["name"] == "test"

    def test_missing_key_returns_placeholder(self) -> None:
        d = _SafeDict({})
        assert d["missing"] == "{missing}"

    def test_format_map_with_safe_dict(self) -> None:
        template = "Hello {name}, your {role} awaits."
        result = template.format_map(_SafeDict({"name": "Alice"}))
        assert result == "Hello Alice, your {role} awaits."


# ─── Few-shot examples ───────────────────────────────────────────────────────


class TestGetFewShotMessages:
    """Test few-shot example loading (§7.10.4)."""

    def test_refactor_is_zero_shot(self) -> None:
        messages = get_few_shot_messages(TaskType.REFACTOR)
        assert messages == []

    def test_bug_fix_is_zero_shot(self) -> None:
        messages = get_few_shot_messages(TaskType.BUG_FIX)
        assert messages == []

    def test_health_scan_is_zero_shot(self) -> None:
        messages = get_few_shot_messages(TaskType.HEALTH_SCAN)
        assert messages == []

    def test_explain_is_zero_shot(self) -> None:
        messages = get_few_shot_messages(TaskType.EXPLAIN)
        assert messages == []

    def test_review_pr_has_one_shot_example(self) -> None:
        messages = get_few_shot_messages(TaskType.REVIEW_PR)
        assert len(messages) >= 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_review_pr_example_contains_diff(self) -> None:
        messages = get_few_shot_messages(TaskType.REVIEW_PR)
        assert any("diff" in m["content"].lower() for m in messages)

    def test_review_pr_example_assistant_is_json(self) -> None:
        import json

        messages = get_few_shot_messages(TaskType.REVIEW_PR)
        assistant_msg = messages[1]["content"]
        # Should be valid JSON
        parsed = json.loads(assistant_msg)
        assert "thought" in parsed
        assert "action" in parsed


class TestFormatCorrectionExample:
    """Test the dynamic validation-failure few-shot (§7.10.4)."""

    def test_loads_successfully(self) -> None:
        examples = load_format_correction_example()
        assert len(examples) >= 1

    def test_has_user_and_assistant_messages(self) -> None:
        examples = load_format_correction_example()
        for ex in examples:
            assert "user_message" in ex
            assert "assistant_message" in ex

    def test_assistant_message_is_valid_json(self) -> None:
        import json

        examples = load_format_correction_example()
        assistant = examples[0]["assistant_message"]
        parsed = json.loads(assistant)
        assert "action" in parsed
        assert parsed["action"]["tool"] == "submit_proposal"
        assert "confidence" in parsed["action"]["args"]


# ─── Full prompt assembly ────────────────────────────────────────────────────


class TestAssemblePrompt:
    """Test the full 5-stage prompt assembly pipeline (§7.10.2)."""

    def _assemble(
        self,
        tmp_path: Path,
        task_type: TaskType = TaskType.REFACTOR,
        **kwargs: object,
    ) -> list[dict[str, str]]:
        (tmp_path / "main.py").write_text("x = 1")
        defaults: dict[str, object] = {
            "repo_name": "test/repo",
            "primary_language": "Python",
            "default_branch": "main",
            "head_sha": "abc123",
            "repo_root": tmp_path,
            "retrieved_chunks": [_make_result()],
            "history": [],
            "output_instructions": "Return valid JSON.",
            "remaining_iterations": 10,
        }
        defaults.update(kwargs)
        return assemble_prompt(task_type, **defaults)  # type: ignore[arg-type]

    def test_returns_non_empty_messages(self, tmp_path: Path) -> None:
        messages = self._assemble(tmp_path)
        assert len(messages) >= 2

    def test_first_message_is_system(self, tmp_path: Path) -> None:
        messages = self._assemble(tmp_path)
        assert messages[0]["role"] == "system"

    def test_system_message_contains_preamble(self, tmp_path: Path) -> None:
        messages = self._assemble(tmp_path)
        assert "expert software engineer" in messages[0]["content"]

    def test_system_message_contains_task_extension(
        self, tmp_path: Path
    ) -> None:
        messages = self._assemble(tmp_path)
        assert "REFACTOR" in messages[0]["content"]

    def test_system_message_has_remaining_iterations(
        self, tmp_path: Path
    ) -> None:
        messages = self._assemble(tmp_path, remaining_iterations=7)
        assert "7" in messages[0]["content"]

    def test_retrieved_context_in_user_message(self, tmp_path: Path) -> None:
        messages = self._assemble(tmp_path)
        all_content = " ".join(m["content"] for m in messages)
        assert "def foo(): pass" in all_content

    def test_review_pr_injects_few_shot(self, tmp_path: Path) -> None:
        messages = self._assemble(tmp_path, task_type=TaskType.REVIEW_PR)
        roles = [m["role"] for m in messages]
        # Should have: system, user (few-shot), assistant (few-shot), ...
        assert roles.count("assistant") >= 1

    def test_refactor_no_few_shot(self, tmp_path: Path) -> None:
        messages = self._assemble(tmp_path, task_type=TaskType.REFACTOR)
        # No assistant messages from few-shot (only system + user)
        assistant_count = sum(
            1 for m in messages if m["role"] == "assistant"
        )
        assert assistant_count == 0

    def test_history_messages_included(self, tmp_path: Path) -> None:
        history = [
            {"role": "user", "content": "Step 1"},
            {"role": "assistant", "content": "Done step 1"},
        ]
        messages = self._assemble(tmp_path, history=history)
        all_content = " ".join(m["content"] for m in messages)
        assert "Step 1" in all_content

    def test_structural_context_included(self, tmp_path: Path) -> None:
        messages = self._assemble(tmp_path)
        all_content = " ".join(m["content"] for m in messages)
        assert "main.py" in all_content

    def test_bug_fix_with_description(self, tmp_path: Path) -> None:
        messages = self._assemble(
            tmp_path,
            task_type=TaskType.BUG_FIX,
            extra_vars={"bug_description": "IndexError in parse()"},
        )
        assert "IndexError in parse()" in messages[0]["content"]
