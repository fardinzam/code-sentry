"""Conversation history management for the ReAct agent loop (§7.10.5, §2.2).

Enforces the "keep last 3 full, summarise oldest" strategy when the
cumulative token count of older entries exceeds the Stage 4 budget.
"""

from __future__ import annotations

from src.agent.schemas import HistoryEntry, ToolAction
from src.utils.logging import get_logger

logger = get_logger(__name__)

_APPROX_CHARS_PER_TOKEN = 4
_MIN_RECENT_FULL = 3  # always keep this many recent iterations verbatim


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // _APPROX_CHARS_PER_TOKEN)


def _entry_tokens(entry: HistoryEntry) -> int:
    return (
        _approx_tokens(entry.thought)
        + _approx_tokens(str(entry.action.model_dump()))
        + _approx_tokens(entry.observation)
    )


class ConversationHistory:
    """Maintains and manages the per-task conversation history.

    Rules (§7.10.5):
    - Each completed iteration appends a ``HistoryEntry``.
    - The 3 most recent entries are always kept verbatim.
    - When converting to prompt messages, entries that exceed the token
      budget are collapsed into a single one-line summary.
    """

    def __init__(self, token_budget: int = 10_000) -> None:
        self._budget = token_budget
        self._entries: list[HistoryEntry] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def append(
        self,
        thought: str,
        action: ToolAction,
        observation: str,
    ) -> None:
        """Record a completed ReAct iteration."""
        entry = HistoryEntry(
            thought=thought,
            action=action,
            observation=observation,
        )
        self._entries.append(entry)
        logger.debug(
            "History entry appended",
            extra={"iteration": len(self._entries), "tool": action.tool},
        )

    def to_messages(self) -> list[dict[str, str]]:
        """Convert history to LLM message dicts for prompt injection.

        Always keeps the 3 most recent entries verbatim. Older entries
        that collectively fit within the remaining token budget are also
        kept verbatim; the rest are compressed into a summary prefix.
        """
        if not self._entries:
            return []

        recent = self._entries[-_MIN_RECENT_FULL:]
        older = self._entries[:-_MIN_RECENT_FULL]

        recent_tokens = sum(_entry_tokens(e) for e in recent)
        remaining_budget = self._budget - recent_tokens

        # Greedily include older entries that still fit (newest-first)
        included_older: list[HistoryEntry] = []
        skipped_older: list[HistoryEntry] = []
        for entry in reversed(older):
            t = _entry_tokens(entry)
            if remaining_budget - t >= 0:
                included_older.insert(0, entry)
                remaining_budget -= t
            else:
                skipped_older.append(entry)

        messages: list[dict[str, str]] = []

        # Summarise any entries that didn't fit
        if skipped_older:
            summary = _summarise_entries(skipped_older)
            messages.append({"role": "user", "content": summary})
            messages.append(
                {
                    "role": "assistant",
                    "content": "[Summary acknowledged. Continuing from most recent state.]",
                }
            )

        for entry in included_older + recent:
            messages.extend(_entry_to_messages(entry))

        return messages

    @property
    def entries(self) -> list[HistoryEntry]:
        """Read-only access to all history entries."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# ── Private helpers ───────────────────────────────────────────────────────────


def _entry_to_messages(entry: HistoryEntry) -> list[dict[str, str]]:
    """Convert a single ``HistoryEntry`` into a user/assistant message pair."""
    user_content = (
        f"**Observation from {entry.action.tool}:**\n{entry.observation}"
    )
    assistant_content = (
        f"**Thought:** {entry.thought}\n"
        f"**Action:** {entry.action.tool}({entry.action.args})"
    )
    return [
        {"role": "assistant", "content": assistant_content},
        {"role": "user", "content": user_content},
    ]


def _summarise_entries(entries: list[HistoryEntry]) -> str:
    """Produce a one-line summary for each entry (used when over budget)."""
    lines = ["Prior steps summary (condensed due to token budget):"]
    for i, e in enumerate(entries, 1):
        tool = e.action.tool
        # Grab a short observation snippet
        obs_snippet = e.observation[:120].replace("\n", " ")
        if len(e.observation) > 120:
            obs_snippet += "..."
        lines.append(f"  {i}. [{tool}] {e.thought[:80]} → {obs_snippet}")
    return "\n".join(lines)
