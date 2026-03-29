"""Prompt builder implementing the 5-stage prompt assembly pipeline (§7.10.2).

Stages (in order, highest to lowest priority for token budget):
  1. System prompt (task-specific)
  2. Retrieved context (semantic search results)
  3. Structural context (file tree, import graph summary)
  4. Conversation history (previous ReAct iterations)
  5. Output instructions (JSON schema, constraints)
"""

from __future__ import annotations

import os
from pathlib import Path

from src.retrieval.search import SearchResult
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Token budget allocation fractions (must sum to 1.0)
_BUDGET_SYSTEM = 0.10
_BUDGET_RETRIEVED = 0.55
_BUDGET_STRUCTURAL = 0.15
_BUDGET_HISTORY = 0.10
_BUDGET_OUTPUT = 0.10


def _count_tokens_approx(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens tokens."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def _format_search_results(results: list[SearchResult]) -> str:
    """Format retrieved chunks into a labelled context block."""
    parts: list[str] = []
    for i, r in enumerate(results):
        header = f"### [{i + 1}] {r.file_path}"
        if r.symbol_name:
            header += f" — `{r.symbol_name}`"
        header += f" (lines {r.start_line}-{r.end_line}, score={r.score:.2f})"
        parts.append(f"{header}\n```\n{r.text}\n```")
    return "\n\n".join(parts)


def _build_file_tree(repo_root: Path, max_lines: int = 60) -> str:
    """Build a compact file tree string for structural context."""
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".")
            and d not in {"__pycache__", "node_modules", ".venv", "venv", "dist"}
        )
        depth = Path(dirpath).relative_to(repo_root).parts
        indent = "  " * len(depth)
        folder = Path(dirpath).name if depth else str(repo_root.name)
        lines.append(f"{indent}{folder}/")
        for filename in sorted(filenames)[:10]:  # cap files per dir
            lines.append(f"{indent}  {filename}")
        if len(lines) >= max_lines:
            lines.append("  ... (truncated)")
            break
    return "\n".join(lines)


class PromptBuilder:
    """Assembles multi-stage prompts with token budget enforcement.

    Args:
        system_prompt: The task-specific system prompt (stage 1).
        repo_root: Repository root for building structural context.
        total_token_budget: Maximum tokens for the entire assembled prompt.
    """

    def __init__(
        self,
        system_prompt: str,
        repo_root: Path,
        total_token_budget: int = 100_000,
    ) -> None:
        self._system_prompt = system_prompt
        self._repo_root = repo_root
        self._total_budget = total_token_budget

    def build(
        self,
        retrieved_chunks: list[SearchResult],
        history: list[dict[str, str]],
        output_instructions: str,
        remaining_iterations: int = 15,
    ) -> list[dict[str, str]]:
        """Assemble the full message list for an LLM call.

        Token budgets are enforced per stage. Overflow is handled by truncating
        the lowest-priority retrieved chunks first.

        Args:
            retrieved_chunks: Ordered search results (most relevant first).
            history: Previous ReAct iterations as message dicts.
            output_instructions: JSON schema and formatting constraints.
            remaining_iterations: Injected into the system message.

        Returns:
            List of {"role": ..., "content": ...} message dicts.
        """
        budgets = {
            "system": int(self._total_budget * _BUDGET_SYSTEM),
            "retrieved": int(self._total_budget * _BUDGET_RETRIEVED),
            "structural": int(self._total_budget * _BUDGET_STRUCTURAL),
            "history": int(self._total_budget * _BUDGET_HISTORY),
            "output": int(self._total_budget * _BUDGET_OUTPUT),
        }

        # Stage 1: System prompt
        system_text = self._system_prompt + f"\n\n**Remaining iterations: {remaining_iterations}**"
        system_text = _truncate_to_tokens(system_text, budgets["system"])

        # Stage 2: Retrieved context — truncate chunks from the bottom until within budget
        filtered_chunks = self._fit_chunks_to_budget(retrieved_chunks, budgets["retrieved"])
        retrieved_text = _format_search_results(filtered_chunks)

        # Stage 3: Structural context — file tree
        file_tree = _build_file_tree(self._repo_root)
        structural_text = _truncate_to_tokens(
            f"## Repository Structure\n\n```\n{file_tree}\n```",
            budgets["structural"],
        )

        # Stage 4: Conversation history — summarise oldest if over budget
        history_text = self._fit_history(history, budgets["history"])

        # Stage 5: Output instructions
        output_text = _truncate_to_tokens(output_instructions, budgets["output"])

        # Assemble messages
        user_content = "\n\n---\n\n".join(
            part for part in [retrieved_text, structural_text, output_text] if part
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_text},
        ]
        for hist_msg in history_text:
            messages.append(hist_msg)
        if user_content:
            messages.append({"role": "user", "content": user_content})

        return messages

    def _fit_chunks_to_budget(
        self, chunks: list[SearchResult], budget_tokens: int
    ) -> list[SearchResult]:
        """Drop lowest-relevance chunks until total fits within budget."""
        result: list[SearchResult] = []
        used = 0
        for chunk in chunks:
            tokens = _count_tokens_approx(chunk.text)
            if used + tokens > budget_tokens:
                break
            result.append(chunk)
            used += tokens
        return result

    def _fit_history(
        self, history: list[dict[str, str]], budget_tokens: int
    ) -> list[dict[str, str]]:
        """Keep the 3 most recent history messages in full; summarise the rest."""
        if not history:
            return []

        # Always keep last 3 messages
        keep_full = history[-3:]
        older = history[:-3]

        kept_tokens = sum(_count_tokens_approx(m["content"]) for m in keep_full)
        remaining_budget = budget_tokens - kept_tokens

        if remaining_budget <= 0 or not older:
            return keep_full

        # Include as many older messages as fit
        result: list[dict[str, str]] = []
        for msg in reversed(older):
            tokens = _count_tokens_approx(msg["content"])
            if remaining_budget - tokens < 0:
                break
            result.insert(0, msg)
            remaining_budget -= tokens

        return result + keep_full
