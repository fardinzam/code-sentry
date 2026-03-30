"""submit_proposal and give_up tools.

These are terminal tools — they signal the orchestrator to exit the
ReAct loop. The handlers here are minimal stubs because the Orchestrator
intercepts these tool names directly before calling the registry.
Registering them in the registry makes them visible in the tool schema
list injected into the system prompt.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def make_submit_proposal_handler() -> Callable[[dict[str, Any]], str]:
    """Return a submit_proposal handler.

    In normal operation, the Orchestrator intercepts ``submit_proposal``
    before it reaches the registry. This handler exists solely to make
    the tool visible in the schema list and to provide a safe fallback.

    Handler args:
        Any fields forming the proposal (title, explanation, files_changed, etc.)
    """

    def handler(args: dict[str, Any]) -> str:
        return f"Proposal submitted:\n{json.dumps(args, indent=2)}"

    return handler


def make_give_up_handler() -> Callable[[dict[str, Any]], str]:
    """Return a give_up handler.

    Like ``submit_proposal``, the Orchestrator intercepts this before
    the registry is reached.

    Handler args:
        reason (str): Explanation of why the task cannot be completed.
    """

    def handler(args: dict[str, Any]) -> str:
        reason = args.get("reason", "No reason given.")
        return f"Task abandoned: {reason}"

    return handler
