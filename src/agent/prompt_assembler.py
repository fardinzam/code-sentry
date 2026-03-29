"""Prompt assembler for the ReAct agent loop (§7.10.1, §7.10.2).

Loads system prompt templates, fills placeholders, selects task-specific
extensions, injects few-shot examples, and wires into the 5-stage prompt
construction pipeline defined in ``src/retrieval/prompt_builder.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.version_info >= (3, 11):  # noqa: UP036
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]  # noqa: UP042
        """Backport of StrEnum for Python 3.10."""

from src.retrieval.prompt_builder import PromptBuilder
from src.retrieval.search import SearchResult
from src.utils.logging import get_logger

logger = get_logger(__name__)

# ─── Resolved path to the prompts directory ──────────────────────────────────
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


class TaskType(StrEnum):
    """Supported agent task types (§7.10.1)."""

    REFACTOR = "refactor"
    BUG_FIX = "bug_fix"
    REVIEW_PR = "review_pr"
    HEALTH_SCAN = "health_scan"
    EXPLAIN = "explain"


# Maps task types to their few-shot strategy (§7.10.4):
#   - None  → zero-shot (default for REFACTOR, BUG_FIX)
#   - str   → filename in examples/ directory (one-shot for REVIEW_PR)
_FEW_SHOT_MAP: dict[TaskType, str | None] = {
    TaskType.REFACTOR: None,
    TaskType.BUG_FIX: None,
    TaskType.REVIEW_PR: "review_pr_example.json",
    TaskType.HEALTH_SCAN: None,
    TaskType.EXPLAIN: None,
}

# File used for dynamic few-shot when validation fails (§7.10.4)
_FORMAT_CORRECTION_FILE = "format_correction.json"


def _load_template(filename: str) -> str:
    """Load a prompt template file from the prompts directory.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    path = _PROMPTS_DIR / filename
    if not path.exists():
        msg = f"Prompt template not found: {path}"
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8").strip()


def _load_few_shot_examples(filename: str) -> list[dict[str, str]]:
    """Load few-shot examples from a JSON file.

    Returns a list of ``{"user_message": ..., "assistant_message": ...}``
    dicts ready for injection into the message list.
    """
    path = _PROMPTS_DIR / "examples" / filename
    if not path.exists():
        logger.warning("Few-shot example file not found: %s", path)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    result: list[dict[str, str]] = data.get("examples", [])
    return result


def load_format_correction_example() -> list[dict[str, str]]:
    """Load the format-correction few-shot example (§7.10.4).

    Used when the agent fails JSON validation on the first attempt.
    """
    return _load_few_shot_examples(_FORMAT_CORRECTION_FILE)


def build_system_prompt(
    task_type: TaskType,
    *,
    repo_name: str = "",
    primary_language: str = "Python",
    default_branch: str = "main",
    head_sha: str = "",
    extra_vars: dict[str, str] | None = None,
) -> str:
    """Assemble the full system prompt for a given task type.

    Combines the common preamble (§7.10.1) with the task-specific extension,
    filling all placeholder variables.

    Args:
        task_type: The agent task type.
        repo_name: Repository name (e.g. ``"myorg/myrepo"``).
        primary_language: Primary programming language of the repo.
        default_branch: Default Git branch name.
        head_sha: Current HEAD commit SHA.
        extra_vars: Additional template variables for task-specific
            placeholders (e.g. ``{"bug_description": "...", ...}``).

    Returns:
        The fully rendered system prompt string.
    """
    preamble = _load_template("system_common.txt")
    extension = _load_template(f"{task_type.value}.txt")

    full_prompt = f"{preamble}\n\n---\n\n{extension}"

    # Fill common placeholders
    variables: dict[str, str] = {
        "repo_name": repo_name,
        "primary_language": primary_language,
        "default_branch": default_branch,
        "head_sha": head_sha,
    }
    if extra_vars:
        variables.update(extra_vars)

    # Use str.format_map with a defaulting dict so missing keys
    # produce the placeholder string rather than raising KeyError.
    full_prompt = full_prompt.format_map(_SafeDict(variables))

    return full_prompt


class _SafeDict(dict[str, str]):
    """dict subclass that returns ``{key}`` for missing keys.

    Prevents ``KeyError`` when a template contains placeholders that
    are not provided at render time (e.g. task-specific vars in the
    common preamble).
    """

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def get_few_shot_messages(
    task_type: TaskType,
) -> list[dict[str, str]]:
    """Return few-shot example messages for a task type (§7.10.4).

    Returns an empty list for zero-shot task types.
    """
    filename = _FEW_SHOT_MAP.get(task_type)
    if filename is None:
        return []

    examples = _load_few_shot_examples(filename)
    messages: list[dict[str, str]] = []
    for ex in examples:
        if "user_message" in ex and "assistant_message" in ex:
            messages.append({"role": "user", "content": ex["user_message"]})
            messages.append(
                {"role": "assistant", "content": ex["assistant_message"]}
            )
    return messages


def assemble_prompt(
    task_type: TaskType,
    *,
    repo_name: str = "",
    primary_language: str = "Python",
    default_branch: str = "main",
    head_sha: str = "",
    repo_root: Path,
    retrieved_chunks: list[SearchResult],
    history: list[dict[str, str]],
    output_instructions: str = "",
    remaining_iterations: int = 15,
    total_token_budget: int = 100_000,
    extra_vars: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Full prompt assembly pipeline (§7.10.2).

    Combines all 5 stages via the ``PromptBuilder`` and injects
    few-shot examples between the system prompt and retrieved context.

    Args:
        task_type: Agent task type (determines prompt extension + few-shot).
        repo_name: Repository identifier.
        primary_language: Primary language of the codebase.
        default_branch: Default branch name (e.g. "main").
        head_sha: Current HEAD commit SHA.
        repo_root: Path to repository root for structural context.
        retrieved_chunks: Ranked search results from RAG retrieval.
        history: Previous ReAct iterations as message dicts.
        output_instructions: JSON schema and formatting constraints.
        remaining_iterations: Iterations remaining in the agent loop.
        total_token_budget: Total token budget for prompt assembly.
        extra_vars: Additional template variables.

    Returns:
        Ordered list of ``{"role": ..., "content": ...}`` message dicts
        ready for an LLM API call.
    """
    system_prompt = build_system_prompt(
        task_type,
        repo_name=repo_name,
        primary_language=primary_language,
        default_branch=default_branch,
        head_sha=head_sha,
        extra_vars=extra_vars,
    )

    builder = PromptBuilder(
        system_prompt=system_prompt,
        repo_root=repo_root,
        total_token_budget=total_token_budget,
    )

    messages = builder.build(
        retrieved_chunks=retrieved_chunks,
        history=history,
        output_instructions=output_instructions,
        remaining_iterations=remaining_iterations,
    )

    # Inject few-shot examples after the system message (§7.10.4)
    few_shot = get_few_shot_messages(task_type)
    if few_shot:
        # Insert after position 0 (the system message)
        for i, msg in enumerate(few_shot):
            messages.insert(1 + i, msg)

    return messages
