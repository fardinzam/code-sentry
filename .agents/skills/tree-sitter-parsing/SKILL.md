---
name: tree-sitter-parsing
description: How to parse Python source files into AST-level semantic chunks using tree-sitter
---

# Tree-Sitter Parsing

## Overview

This skill guides using `tree-sitter` to parse Python source files into semantic chunks (functions, classes, methods) for the codebase indexing engine. Tree-sitter provides fast, reliable, incremental AST parsing.

## Prerequisites

```bash
pip install tree-sitter tree-sitter-python
```

## Step-by-Step Instructions

### 1. Initialize the Parser

```python
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())

parser = Parser(PY_LANGUAGE)
```

### 2. Parse a File into AST

```python
def parse_file(file_path: str) -> tree_sitter.Tree:
    with open(file_path, "rb") as f:
        source_code = f.read()
    return parser.parse(source_code)
```

### 3. Extract Semantic Chunks

The key node types to extract for Python:

| Node type | tree-sitter type string | What it captures |
|-----------|------------------------|------------------|
| Function | `function_definition` | Top-level and nested functions |
| Class | `class_definition` | Class definitions |
| Method | `function_definition` (inside `class_definition`) | Instance/class/static methods |
| Module-level code | Root-level statements not inside functions/classes | Imports, constants, assignments |

```python
from dataclasses import dataclass

@dataclass
class CodeChunk:
    file_path: str
    chunk_type: str        # "function", "class", "method", "module"
    name: str
    start_line: int
    end_line: int
    source: str
    docstring: str | None
    language: str = "python"

def extract_chunks(file_path: str, source: bytes, tree) -> list[CodeChunk]:
    chunks = []
    root = tree.root_node

    for node in root.children:
        if node.type == "function_definition":
            chunks.append(_make_chunk(file_path, node, source, "function"))
        elif node.type == "class_definition":
            chunks.append(_make_chunk(file_path, node, source, "class"))
            # Also extract methods within the class
            for child in node.children:
                if child.type == "block":
                    for member in child.children:
                        if member.type == "function_definition":
                            chunks.append(_make_chunk(file_path, member, source, "method"))
        elif node.type == "decorated_definition":
            # Handle decorated functions/classes
            inner = node.children[-1]
            if inner.type == "function_definition":
                chunks.append(_make_chunk(file_path, inner, source, "function"))
            elif inner.type == "class_definition":
                chunks.append(_make_chunk(file_path, inner, source, "class"))

    # Module-level code: everything not captured above
    module_lines = _extract_module_level(root, source)
    if module_lines.strip():
        chunks.insert(0, CodeChunk(
            file_path=file_path,
            chunk_type="module",
            name=file_path,
            start_line=1,
            end_line=source.count(b"\n") + 1,
            source=module_lines,
            docstring=_extract_module_docstring(root, source),
        ))

    return chunks

def _make_chunk(file_path: str, node, source: bytes, chunk_type: str) -> CodeChunk:
    name_node = node.child_by_field_name("name")
    name = name_node.text.decode() if name_node else "<anonymous>"
    return CodeChunk(
        file_path=file_path,
        chunk_type=chunk_type,
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        source=source[node.start_byte:node.end_byte].decode(),
        docstring=_extract_docstring(node, source),
    )

def _extract_docstring(node, source: bytes) -> str | None:
    """Extract docstring from function/class body."""
    body = node.child_by_field_name("body")
    if body and body.children:
        first_stmt = body.children[0]
        if first_stmt.type == "expression_statement":
            expr = first_stmt.children[0]
            if expr.type == "string":
                return expr.text.decode().strip('"\\'')
    return None
```

### 4. Handle Edge Cases

```python
def safe_parse_file(file_path: str) -> list[CodeChunk]:
    """Parse with graceful fallback to raw text chunking."""
    try:
        with open(file_path, "rb") as f:
            source = f.read()

        # Skip files that are too large (>1MB)
        if len(source) > 1_000_000:
            return _raw_text_chunks(file_path, source)

        tree = parser.parse(source)

        # Check for parse errors
        if tree.root_node.has_error:
            # Still extract what we can — tree-sitter is error-tolerant
            chunks = extract_chunks(file_path, source, tree)
            if not chunks:
                return _raw_text_chunks(file_path, source)
            return chunks

        return extract_chunks(file_path, source, tree)

    except Exception:
        return _raw_text_chunks(file_path, source)

def _raw_text_chunks(file_path: str, source: bytes, chunk_size: int = 200, overlap: int = 20) -> list[CodeChunk]:
    """Fallback: sliding window text chunking."""
    lines = source.decode(errors="replace").splitlines()
    chunks = []
    for i in range(0, len(lines), chunk_size - overlap):
        chunk_lines = lines[i:i + chunk_size]
        chunks.append(CodeChunk(
            file_path=file_path,
            chunk_type="raw",
            name=f"{file_path}:{i+1}-{i+len(chunk_lines)}",
            start_line=i + 1,
            end_line=i + len(chunk_lines),
            source="\n".join(chunk_lines),
            docstring=None,
        ))
    return chunks
```

## Common Pitfalls

- **tree-sitter uses 0-indexed lines** — add 1 when storing line numbers for display
- **Bytes vs strings** — tree-sitter works with `bytes`, not `str`. Always read files in binary mode and decode chunk text
- **Decorated functions** — decorators wrap the function in a `decorated_definition` node. Always check for this wrapper
- **Nested classes/functions** — decide whether to recurse. For indexing, extracting 1 level deep (class → methods) is usually sufficient
- **Parse errors don't crash** — tree-sitter is error-tolerant and produces a partial AST. Check `has_error` but still try to extract chunks
- **Language grammar versions** — pin `tree-sitter-python` to a specific version to avoid parse behaviour changes across updates
