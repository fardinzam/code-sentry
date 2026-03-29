"""Structured output parser for agent LLM responses (§7.10.3).

Implements the 3-attempt validation failure retry chain:
  Attempt 1 — re-prompt with validation error
  Attempt 2 — salvage partial data, mark PARTIAL
  Attempt 3 — log raw response, mark FAILED

Uses Pydantic validators for schema enforcement and loads the
format-correction few-shot example for recovery re-prompting.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from src.agent.prompt_assembler import load_format_correction_example
from src.agent.schemas import AgentIterationResponse
from src.utils.errors import SchemaValidationError
from src.utils.logging import get_logger

logger = get_logger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Pull JSON from a raw LLM response string.

    Tries three strategies in order:
    1. Find a ```json ... ``` fenced block.
    2. Find any ``` ... ``` fenced block.
    3. Assume the whole string is JSON.

    Raises:
        SchemaValidationError: If no valid JSON can be extracted.
    """
    # Strategy 1 & 2: fenced block
    match = _JSON_FENCE_RE.search(text)
    json_str = match.group(1).strip() if match else text.strip()

    # Basic repairs for common LLM JSON errors
    json_str = _repair_json(json_str)

    try:
        result: dict[str, Any] = json.loads(json_str)
        return result
    except json.JSONDecodeError as exc:
        msg = f"JSON decode failed: {exc}"
        raise SchemaValidationError(msg) from exc


def _repair_json(text: str) -> str:
    """Attempt lightweight repairs for common LLM JSON mistakes."""
    # Strip stray markdown fences
    text = re.sub(r"^```\w*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    # Remove trailing commas before ] or }
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text.strip()


def parse_iteration_response(raw: str) -> AgentIterationResponse:
    """Validate a raw LLM string against the AgentIterationResponse schema.

    Raises:
        SchemaValidationError: If valid JSON exists but fails Pydantic
            validation (caller should re-prompt).
    """
    data = extract_json(raw)
    try:
        return AgentIterationResponse.model_validate(data)
    except ValidationError as exc:
        msg = f"Schema validation failed: {exc}"
        raise SchemaValidationError(msg) from exc


def build_validation_error_reprompt(
    original_raw: str,
    error: SchemaValidationError,
    attempt: int,
) -> list[dict[str, str]]:
    """Build a re-prompt message list for a validation failure (§7.10.3).

    Attempt 1: explain the error + ask to fix.
    Attempt 2: include the format-correction few-shot example.
    """
    error_msg = str(error)

    if attempt == 1:
        return [
            {
                "role": "user",
                "content": (
                    f"Your previous response was not valid JSON or did not "
                    f"match the required schema.\n\nError: {error_msg}\n\n"
                    f"Your raw response was:\n```\n{original_raw[:2000]}\n```\n\n"
                    "Please fix your response to match the required schema exactly. "
                    "Respond ONLY with valid JSON."
                ),
            }
        ]

    # Attempt 2: include the format-correction few-shot
    examples = load_format_correction_example()
    messages: list[dict[str, str]] = []
    for ex in examples:
        messages.append({"role": "user", "content": ex["user_message"]})
        messages.append(
            {"role": "assistant", "content": ex["assistant_message"]}
        )
    messages.append(
        {
            "role": "user",
            "content": (
                f"Your response still did not match the schema.\n\nError: {error_msg}\n\n"
                "Following the example above exactly, please re-submit your response."
            ),
        }
    )
    return messages


def try_salvage_partial(raw: str) -> dict[str, Any] | None:
    """Attempt to salvage any parseable data from a failed response.

    Returns whatever dict was extractable, or None if nothing usable found.
    """
    try:
        data = extract_json(raw)
        # Check if at minimum a thought exists
        if isinstance(data, dict) and data.get("thought"):
            logger.warning("Salvaging partial agent response (thought only).")
            return data
    except SchemaValidationError:
        pass
    return None
