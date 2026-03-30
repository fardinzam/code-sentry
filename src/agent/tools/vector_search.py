"""vector_search tool: semantic search over the indexed codebase.

Delegates to the HybridSearcher for embedding-based retrieval.
Returns a formatted list of ranked code chunks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_DEFAULT_TOP_K = 5
_MAX_CHUNK_CHARS = 2000


def make_vector_search_handler(searcher: Any) -> Callable[[dict[str, Any]], str]:
    """Return a vector_search handler bound to ``searcher``.

    Args:
        searcher: A ``HybridSearcher`` instance (typed as Any to avoid the
            circular import from TYPE_CHECKING at call sites).

    Handler args:
        query (str): Natural-language or code search query.
        top_k (int, optional): Maximum results to return. Defaults to 5.

    Returns:
        Formatted observation listing ranked code chunks with file paths,
        line ranges, scores, and source text.
    """

    def handler(args: dict[str, Any]) -> str:
        query = args.get("query", "")
        if not query:
            return "[ERROR] vector_search: 'query' argument is required."

        top_k = int(args.get("top_k", _DEFAULT_TOP_K))
        top_k = max(1, min(top_k, 20))  # clamp 1-20

        try:
            results = searcher.search(query, top_k=top_k)
        except Exception as exc:
            return f"[ERROR] vector_search: search failed: {exc}"

        if not results:
            return f"No results found for query: {query!r}"

        lines = [f"## Vector Search Results for: {query!r}\n"]
        for i, r in enumerate(results, 1):
            chunk = r.text[:_MAX_CHUNK_CHARS]
            truncated = len(r.text) > _MAX_CHUNK_CHARS
            lines.append(
                f"### [{i}] {r.file_path} - `{r.symbol_name}` "
                f"(lines {r.start_line}-{r.end_line}, score={r.score:.3f})"
            )
            lines.append(f"```\n{chunk}{'...' if truncated else ''}\n```\n")

        return "\n".join(lines)

    return handler
