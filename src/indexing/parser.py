"""AST parser wrapping tree-sitter for Python source files (§7.1).

Extracts function/class definitions with line ranges and docstrings.
Falls back to line-based chunking when AST parse fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.utils.errors import ParseError
from src.utils.logging import get_logger

logger = get_logger(__name__)

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Node, Parser

    _PY_LANGUAGE = Language(tspython.language())
    _PARSER = Parser(_PY_LANGUAGE)
    _TREE_SITTER_AVAILABLE = True
except Exception:  # pragma: no cover
    _TREE_SITTER_AVAILABLE = False
    Node = None  # type: ignore[assignment,misc]
    logger.warning("tree-sitter not available - AST parsing disabled, using line-based fallback")


@dataclass
class CodeSymbol:
    """A function, method, or class extracted from source code.

    Attributes:
        name: Qualified name (ClassName.method_name for methods).
        symbol_type: "function", "method", or "class".
        start_line: 1-indexed start line (inclusive).
        end_line: 1-indexed end line (inclusive).
        docstring: First string literal in the body, if present.
        source: Full source text of this symbol.
        parent_class: Enclosing class name for methods, else empty string.
    """

    name: str
    symbol_type: str
    start_line: int
    end_line: int
    docstring: str = ""
    source: str = ""
    parent_class: str = ""
    imports: list[str] = field(default_factory=list)


# ParseError is re-exported so chunker.py can import it from here.
__all__ = ["CodeSymbol", "ParseError", "parse_python_file"]


def _extract_docstring(node: object, source_bytes: bytes) -> str:
    """Extract the first string literal from a function/class body."""
    for child in getattr(node, "children", []):
        if child.type == "block":
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    for expr in stmt.children:
                        if expr.type == "string":
                            raw: bytes | None = source_bytes[
                                expr.start_byte : expr.end_byte
                            ]
                            if raw is not None:
                                return raw.decode("utf-8", errors="replace").strip("\"' \n")
    return ""


def _node_source(node: object, source_bytes: bytes) -> str:
    raw: bytes = source_bytes[
        getattr(node, "start_byte", 0) : getattr(node, "end_byte", 0)
    ]
    return raw.decode("utf-8", errors="replace")


def _node_name(name_node: object | None) -> str:
    """Safely decode a name node's text bytes."""
    if name_node is None:
        return "<anon>"
    text: bytes | None = getattr(name_node, "text", None)
    if text is None:
        return "<anon>"
    return text.decode("utf-8", errors="replace")


def _extract_symbols(tree_root: object, source_bytes: bytes) -> list[CodeSymbol]:
    """Walk the AST and extract all top-level and class-level symbols."""
    symbols: list[CodeSymbol] = []

    def walk(node: object, parent_class: str = "") -> None:
        node_type: str = getattr(node, "type", "")
        if node_type in ("function_definition", "async_function_definition"):
            name_node = getattr(node, "child_by_field_name", lambda _: None)("name")
            name = _node_name(name_node)
            qualified = f"{parent_class}.{name}" if parent_class else name
            symbols.append(
                CodeSymbol(
                    name=qualified,
                    symbol_type="method" if parent_class else "function",
                    start_line=getattr(node, "start_point", (0,))[0] + 1,
                    end_line=getattr(node, "end_point", (0,))[0] + 1,
                    docstring=_extract_docstring(node, source_bytes),
                    source=_node_source(node, source_bytes),
                    parent_class=parent_class,
                )
            )

        elif node_type == "class_definition":
            name_node = getattr(node, "child_by_field_name", lambda _: None)("name")
            class_name = _node_name(name_node)
            body = getattr(node, "child_by_field_name", lambda _: None)("body")
            symbols.append(
                CodeSymbol(
                    name=class_name,
                    symbol_type="class",
                    start_line=getattr(node, "start_point", (0,))[0] + 1,
                    end_line=getattr(node, "end_point", (0,))[0] + 1,
                    docstring=_extract_docstring(node, source_bytes),
                    source=_node_source(node, source_bytes),
                )
            )
            if body:
                for child in getattr(body, "children", []):
                    walk(child, parent_class=class_name)

        else:
            for child in getattr(node, "children", []):
                walk(child, parent_class=parent_class)

    walk(tree_root)
    return symbols


def parse_python_file(path: Path) -> list[CodeSymbol]:
    """Parse a Python source file and extract all code symbols.

    Args:
        path: Absolute path to the Python source file.

    Returns:
        List of CodeSymbol objects. Empty list if path does not exist.

    Raises:
        ParseError: If tree-sitter fails to parse the file (rare; usually
            means a syntax error so severe that tree-sitter gives up).
    """
    if not path.exists():
        return []

    source_bytes = path.read_bytes()

    if not _TREE_SITTER_AVAILABLE:
        raise ParseError(f"tree-sitter not available; cannot AST-parse '{path}'")

    try:
        tree = _PARSER.parse(source_bytes)
        if tree.root_node.has_error:
            logger.warning(
                "AST parse contains errors - partial results may be returned",
                extra={"file": str(path)},
            )
        return _extract_symbols(tree.root_node, source_bytes)
    except Exception as exc:
        raise ParseError(
            f"tree-sitter failed to parse '{path}': {exc}. "
            "The file will be processed with line-based chunking instead."
        ) from exc
