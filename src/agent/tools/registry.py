"""Agent tool registry: registration, schema validation, and dispatch (§7.3 FR-3.2).

Tools are registered with a name, callable handler, and JSON input schema.
The registry is the single dispatch point called by the Orchestrator.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from src.utils.errors import FatalTaskError
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Type alias for a tool handler function
ToolHandler = Callable[[dict[str, Any]], str]


class ToolSchema:
    """Describes a tool's name, description, and argument schema."""

    def __init__(
        self,
        name: str,
        description: str,
        args_schema: dict[str, Any],
    ) -> None:
        self.name = name
        self.description = description
        self.args_schema = args_schema

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the schema."""
        return {
            "name": self.name,
            "description": self.description,
            "args": self.args_schema,
        }


class ToolRegistry:
    """Registry that maps tool names to handlers and their schemas.

    Usage::

        registry = ToolRegistry()
        registry.register(schema, handler)
        observation = registry.dispatch("file_read", {"path": "src/main.py"})

    The Orchestrator passes ``registry.dispatch`` as its ``tool_registry``
    callable.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}
        self._schemas: dict[str, ToolSchema] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        """Register a tool handler under the given schema name.

        Args:
            schema: Metadata and argument schema for the tool.
            handler: Callable that accepts ``args`` dict and returns a
                     string observation.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if schema.name in self._handlers:
            msg = f"Tool '{schema.name}' is already registered."
            raise ValueError(msg)
        self._handlers[schema.name] = handler
        self._schemas[schema.name] = schema
        logger.debug("Tool registered", extra={"tool_name": schema.name})

    def dispatch(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Execute a tool by name and return the observation string.

        Args:
            tool_name: Name of the registered tool.
            tool_args: Arguments dict passed to the tool handler.

        Returns:
            String observation (stdout, result text, or error description).

        Raises:
            FatalTaskError: If the tool is not registered.
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            known = ", ".join(sorted(self._handlers))
            msg = (
                f"Unknown tool '{tool_name}'. "
                f"Registered tools: {known or '(none)'}"
            )
            raise FatalTaskError(msg)

        logger.info(
            "Dispatching tool",
            extra={"tool_name": tool_name},
        )
        return handler(tool_args)

    # ── Inspection ────────────────────────────────────────────────────────────

    def list_tools(self) -> list[str]:
        """Return names of all registered tools."""
        return sorted(self._handlers)

    def get_schema(self, tool_name: str) -> ToolSchema | None:
        """Return the schema for a tool, or None if not registered."""
        return self._schemas.get(tool_name)

    def schemas_as_json(self) -> str:
        """Serialise all tool schemas to a JSON string (for prompt injection)."""
        return json.dumps(
            [s.to_dict() for s in self._schemas.values()],
            indent=2,
        )
