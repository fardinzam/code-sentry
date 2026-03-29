"""ReAct agent orchestrator (§7.3, §7.10.5, §2.2).

Implements the main Observe → Think → Act → Validate loop:

  1. Assemble prompt (5-stage pipeline via prompt_assembler).
  2. Call LLM → get raw response.
  3. Parse + validate response (Pydantic) with 3-attempt retry chain.
  4. Dispatch tool call → capture observation.
  5. Append iteration to conversation history.
  6. Repeat until submit_proposal, give_up, iteration limit, or token budget.

The orchestrator is intentionally stateless across tasks — each call to
``run()`` gets its own history, budget counters, and task ID.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from src.agent.history import ConversationHistory
from src.agent.output_parser import (
    build_validation_error_reprompt,
    parse_iteration_response,
    try_salvage_partial,
)
from src.agent.prompt_assembler import TaskType, assemble_prompt
from src.agent.schemas import AgentIterationResponse, OrchestratorResult
from src.llm.client import LLMClient
from src.retrieval.search import SearchResult
from src.utils.constants import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_TOKENS_PER_TASK,
    FINAL_ITERATION_THRESHOLD,
    JSON_VALIDATION_MAX_RETRIES,
)
from src.utils.errors import (
    FatalTaskError,
    LLMBudgetExhaustedError,
    LLMError,
    SchemaValidationError,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Token budget fraction reserved for Stage 4 (history), used by ConversationHistory
_HISTORY_BUDGET_FRACTION = 0.15
# Output instructions injected into every prompt
_OUTPUT_INSTRUCTIONS = """Respond ONLY with valid JSON in this exact format:

{
  "thought": "Your reasoning for this step",
  "action": {
    "tool": (
      "one of: file_read | vector_search | ast_query | file_write"
      " | shell_exec | git_op | submit_proposal | give_up"
    ),
    "args": { }
  }
}

When you have a final proposal ready, use tool "submit_proposal" with the proposal data in args.
When you cannot complete the task, use tool "give_up" with {"reason": "..."} in args."""

_FINAL_ITERATION_SUFFIX = (
    "\n\n⚠️  This is your FINAL iteration. "
    "You MUST either call submit_proposal with your best current proposal, "
    "or call give_up with your reason. Do not call any other tool."
)


class Orchestrator:
    """ReAct agent orchestrator.

    Args:
        llm: An ``LLMClient``-compatible object for generating completions.
        tool_registry: Callable that dispatches a tool call and returns the
            observation string.  Signature:
            ``(tool_name: str, args: dict) -> str``
        task_type: The agent task type (REFACTOR, BUG_FIX, etc.).
        repo_root: Absolute path to the repository root.
        max_iterations: Maximum number of ReAct iterations before forcing
            a final iteration.
        token_budget: Maximum cumulative tokens (input + output) for the task.
        repo_name: Repository name, injected into the system prompt.
        primary_language: Primary language of the codebase.
        default_branch: Default Git branch name.
        head_sha: Current HEAD commit SHA.
        extra_prompt_vars: Additional template variables for task-specific
            prompt placeholders (e.g. ``{"bug_description": "..."}`).
    """

    def __init__(
        self,
        llm: LLMClient,
        tool_registry: Any,  # Callable[[str, dict], str]
        task_type: TaskType,
        repo_root: Path,
        *,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        token_budget: int = DEFAULT_MAX_TOKENS_PER_TASK,
        repo_name: str = "",
        primary_language: str = "Python",
        default_branch: str = "main",
        head_sha: str = "",
        extra_prompt_vars: dict[str, str] | None = None,
    ) -> None:
        self._llm = llm
        self._registry = tool_registry
        self._task_type = task_type
        self._repo_root = repo_root
        self._max_iterations = max_iterations
        self._token_budget = token_budget
        self._repo_name = repo_name
        self._primary_language = primary_language
        self._default_branch = default_branch
        self._head_sha = head_sha
        self._extra_vars = extra_prompt_vars

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        task_id: str | None = None,
        retrieved_chunks: list[SearchResult] | None = None,
    ) -> OrchestratorResult:
        """Execute the ReAct loop for one task.

        Args:
            task_id: Unique identifier for this task. Generated if not
                supplied.
            retrieved_chunks: Initial RAG context to inject into Stage 2
                of the first prompt.

        Returns:
            ``OrchestratorResult`` containing the final status, token usage,
            and (if successful) the proposal data.
        """
        task_id = task_id or str(uuid.uuid4())
        retrieved_chunks = retrieved_chunks or []

        history = ConversationHistory(
            token_budget=int(self._token_budget * _HISTORY_BUDGET_FRACTION)
        )
        tokens_used = 0
        proposal: dict[str, Any] | None = None

        logger.info(
            "Agent task started",
            extra={
                "task_id": task_id,
                "task_type": self._task_type,
                "max_iterations": self._max_iterations,
            },
        )

        for iteration in range(1, self._max_iterations + 1):
            remaining = self._max_iterations - iteration + 1
            is_final = remaining <= FINAL_ITERATION_THRESHOLD

            # ── Stage 1-5: Assemble prompt ───────────────────────────────────
            output_instructions = _OUTPUT_INSTRUCTIONS
            if is_final:
                output_instructions += _FINAL_ITERATION_SUFFIX

            messages = assemble_prompt(
                self._task_type,
                repo_name=self._repo_name,
                primary_language=self._primary_language,
                default_branch=self._default_branch,
                head_sha=self._head_sha,
                repo_root=self._repo_root,
                retrieved_chunks=retrieved_chunks,
                history=history.to_messages(),
                output_instructions=output_instructions,
                remaining_iterations=remaining,
                total_token_budget=self._token_budget,
                extra_vars=self._extra_vars,
            )

            # ── LLM call ─────────────────────────────────────────────────────
            try:
                response = self._llm.generate(messages)
            except LLMBudgetExhaustedError:
                logger.error("Token budget exhausted", extra={"task_id": task_id})
                return OrchestratorResult(
                    status="FAILED",
                    task_id=task_id,
                    iterations_used=iteration,
                    tokens_used=tokens_used,
                    error_message="Token budget exhausted.",
                )
            except LLMError as exc:
                logger.error(
                    "LLM error during iteration",
                    extra={"task_id": task_id, "iteration": iteration, "error": str(exc)},
                )
                return OrchestratorResult(
                    status="FAILED",
                    task_id=task_id,
                    iterations_used=iteration,
                    tokens_used=tokens_used,
                    error_message=str(exc),
                )

            tokens_used += response.total_tokens
            raw_content = response.content

            logger.info(
                "LLM response received",
                extra={
                    "task_id": task_id,
                    "iteration": iteration,
                    "tokens": response.total_tokens,
                    "total_tokens_used": tokens_used,
                },
            )

            # ── Parse + validate with retry chain ────────────────────────────
            parsed, status = self._parse_with_retry(
                raw_content, messages, task_id, iteration
            )

            if status == "FAILED":
                return OrchestratorResult(
                    status="FAILED",
                    task_id=task_id,
                    iterations_used=iteration,
                    tokens_used=tokens_used,
                    error_message="All JSON validation attempts exhausted.",
                )
            if status == "PARTIAL":
                return OrchestratorResult(
                    status="PARTIAL",
                    task_id=task_id,
                    iterations_used=iteration,
                    tokens_used=tokens_used,
                    error_message="Could only salvage partial response.",
                )

            assert parsed is not None  # status == "OK" guarantees this

            # ── Token budget guard ───────────────────────────────────────────
            if tokens_used >= self._token_budget:
                logger.warning(
                    "Token budget reached",
                    extra={"task_id": task_id, "tokens_used": tokens_used},
                )
                return OrchestratorResult(
                    status="FAILED",
                    task_id=task_id,
                    iterations_used=iteration,
                    tokens_used=tokens_used,
                    error_message="Token budget exhausted mid-task.",
                )

            tool_name = parsed.action.tool
            tool_args = parsed.action.args

            # ── Terminal tools ───────────────────────────────────────────────
            if tool_name == "submit_proposal":
                logger.info(
                    "Agent submitted proposal",
                    extra={"task_id": task_id, "iteration": iteration},
                )
                proposal = tool_args
                history.append(parsed.thought, parsed.action, "Proposal submitted.")
                return OrchestratorResult(
                    status="COMPLETED",
                    task_id=task_id,
                    iterations_used=iteration,
                    tokens_used=tokens_used,
                    proposal=proposal,
                )

            if tool_name == "give_up":
                reason = str(tool_args.get("reason", "No reason provided."))
                logger.info(
                    "Agent gave up",
                    extra={"task_id": task_id, "iteration": iteration, "reason": reason},
                )
                history.append(parsed.thought, parsed.action, f"Task abandoned: {reason}")
                return OrchestratorResult(
                    status="FAILED",
                    task_id=task_id,
                    iterations_used=iteration,
                    tokens_used=tokens_used,
                    give_up_reason=reason,
                )

            # ── Execute tool → capture observation ───────────────────────────
            observation = self._dispatch_tool(tool_name, tool_args, task_id, iteration)
            history.append(parsed.thought, parsed.action, observation)

        # ── Iteration limit exceeded ─────────────────────────────────────────
        logger.warning(
            "Agent hit iteration limit without submitting",
            extra={"task_id": task_id, "max_iterations": self._max_iterations},
        )
        return OrchestratorResult(
            status="FAILED",
            task_id=task_id,
            iterations_used=self._max_iterations,
            tokens_used=tokens_used,
            error_message=f"Reached max iteration limit ({self._max_iterations}).",
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_with_retry(
        self,
        raw: str,
        prior_messages: list[dict[str, str]],
        task_id: str,
        iteration: int,
    ) -> tuple[AgentIterationResponse | None, str]:
        """Attempt to parse and validate the raw LLM response.

        Returns ``(parsed, status)`` where status is "OK", "PARTIAL", or
        "FAILED".  On "OK", ``parsed`` is a validated ``AgentIterationResponse``.
        """
        last_error: SchemaValidationError | None = None

        for attempt in range(1, JSON_VALIDATION_MAX_RETRIES + 1):
            try:
                parsed = parse_iteration_response(raw)
                if attempt > 1:
                    logger.info(
                        "Validation succeeded on retry",
                        extra={"task_id": task_id, "attempt": attempt},
                    )
                return parsed, "OK"

            except SchemaValidationError as exc:
                last_error = exc
                logger.warning(
                    "Validation attempt failed",
                    extra={
                        "task_id": task_id,
                        "iteration": iteration,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )

                if attempt < JSON_VALIDATION_MAX_RETRIES - 1:
                    # Attempt 1 & 2: re-prompt and try again
                    recovery_msgs = build_validation_error_reprompt(
                        raw, exc, attempt
                    )
                    try:
                        recovery_response = self._llm.generate(
                            prior_messages + recovery_msgs
                        )
                        raw = recovery_response.content
                    except LLMError:
                        break
                elif attempt == JSON_VALIDATION_MAX_RETRIES - 1:
                    # Final attempt: try to salvage
                    partial = try_salvage_partial(raw)
                    if partial:
                        logger.warning(
                            "Returning salvaged partial response",
                            extra={"task_id": task_id},
                        )
                        return None, "PARTIAL"

        logger.error(
            "All validation attempts failed",
            extra={
                "task_id": task_id,
                "error": str(last_error),
                "raw_response": raw[:500],
            },
        )
        return None, "FAILED"

    def _dispatch_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        task_id: str,
        iteration: int,
    ) -> str:
        """Call the tool registry and return the observation string.

        Any tool execution error is caught and returned as an observation
        so the agent can adapt (§14.5 — tool errors passed as observations).
        """
        logger.info(
            "Tool call",
            extra={
                "task_id": task_id,
                "iteration": iteration,
                "tool": tool_name,
                "tool_args": tool_args,
            },
        )
        try:
            observation: str = self._registry(tool_name, tool_args)
            return observation
        except FatalTaskError as exc:
            return f"[FATAL ERROR] Tool '{tool_name}' failed: {exc}"
        except Exception as exc:
            logger.warning(
                "Tool error returned as observation",
                extra={"tool": tool_name, "error": str(exc)},
            )
            return f"[ERROR] Tool '{tool_name}' raised: {exc}"
