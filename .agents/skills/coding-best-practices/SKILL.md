---
name: Coding Best Practices
description: Enforces coding standards, DRY principles, formatting, and quality conventions for the Agentic AI Code Reviewer project.
---

# Coding Best Practices

Follow these practices throughout the entire codebase. Violations should be treated as bugs.

---

## 1. DRY — Don't Repeat Yourself

- **Never duplicate logic.** If the same block of code appears in two or more places, extract it into a shared function, method, or utility module.
- **Parameterize behavior differences.** If two functions differ by only a constant, flag, or format string, merge them into one function with a parameter.
- **Centralize constants.** Define magic numbers, strings, status codes, and configuration keys as named constants in a dedicated constants module (`src/utils/constants.py`), not inline.
- **Single source of truth for schemas.** Pydantic models in `src/schemas/` are the canonical definitions. Never re-declare field names, types, or constraints elsewhere.
- **Reuse error messages.** Keep user-facing error strings in one place so they stay consistent.

```python
# ❌ BAD
def get_user_by_id(user_id):
    conn = sqlite3.connect("app.db")
    ...

def get_user_by_email(email):
    conn = sqlite3.connect("app.db")
    ...

# ✅ GOOD
def _get_connection():
    return sqlite3.connect(settings.database_url)

def get_user_by_id(user_id):
    conn = _get_connection()
    ...
```

---

## 2. Formatting & Style

- **Follow PEP 8** for all Python code. Use `ruff` as the single linter/formatter.
- **Max line length: 100 characters.** Configure in `ruff.toml`.
- **Use trailing commas** in multi-line collections, function args, and imports. This produces cleaner diffs.
- **Import order:** Standard library → third-party → local. Use `ruff` to enforce. Group with blank lines.
- **Blank lines:** Two blank lines before top-level definitions (functions, classes). One blank line between methods inside a class.
- **Consistent string quotes:** Use double quotes (`"`) for strings throughout the project.
- **No commented-out code.** Delete dead code; Git preserves history. Use `TODO:` comments only for planned work with a description.

```python
# ✅ GOOD import order
import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from src.config.settings import get_settings
from src.utils.logging import get_logger
```

---

## 3. Naming Conventions

- **Variables and functions:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_SNAKE_CASE`
- **Private/internal:** Prefix with single underscore (`_helper_function`)
- **Boolean variables:** Prefix with `is_`, `has_`, `should_`, `can_` (e.g., `is_valid`, `has_coverage`)
- **Functions that return booleans:** Same prefixes (e.g., `is_empty()`, `has_permission()`)
- **Avoid abbreviations** unless universally understood (`id`, `url`, `db` are OK; `mgr`, `tbl`, `cnt` are not)
- **File names:** `snake_case.py`. Match the primary class or concept (e.g., `proposal.py` for `AgentProposal`).

---

## 4. Function & Method Design

- **Single Responsibility:** Each function does one thing. If a function name has "and" in it, split it.
- **Max function length: ~50 lines.** If longer, decompose into sub-functions.
- **Max parameters: 5.** If more, group into a dataclass, Pydantic model, or `TypedDict`.
- **No side effects in getters.** Functions named `get_*` or `compute_*` should not modify state.
- **Return early** to avoid deeply nested conditionals:

```python
# ❌ BAD
def process(item):
    if item is not None:
        if item.is_active:
            if item.value > 0:
                return handle(item)
    return None

# ✅ GOOD
def process(item):
    if item is None:
        return None
    if not item.is_active:
        return None
    if item.value <= 0:
        return None
    return handle(item)
```

- **Use type hints on all function signatures** (parameters and return type).

---

## 5. Error Handling

- **Use specific exception types.** Never catch bare `except:` or `except Exception:` unless re-raising.
- **Define project-level exceptions** in `src/utils/errors.py`:
  - `CodeReviewerError` (base)
  - `TransientError`, `RecoverableError`, `FatalTaskError`, `FatalSystemError`
  - `LLMError`, `GitError`, `IndexingError`, `EvaluationError`
- **Fail fast.** Validate inputs at function entry, not deep inside logic.
- **Include context in error messages:** what failed, why, and what the user can do about it.

```python
# ❌ BAD
raise Exception("Failed")

# ✅ GOOD
raise GitError(
    f"Failed to apply diff to '{file_path}': {e}. "
    f"Ensure the file exists and the diff targets the correct lines."
) from e
```

- **Log and re-raise** at system boundaries; handle at the appropriate layer.
- **Never swallow exceptions silently.** At minimum, log a warning.

---

## 6. Documentation

- **All public functions, classes, and modules must have docstrings.**
- **Docstring format:** Google style.

```python
def compute_score(evaluation: EvaluationResult, weights: ScoreWeights) -> float:
    """Compute the composite quality score for a proposal.

    Args:
        evaluation: The completed evaluation pipeline result.
        weights: Configurable scoring weights.

    Returns:
        Composite score between 0.0 and 100.0.

    Raises:
        ScoringError: If evaluation results are incomplete.
    """
```

- **Inline comments:** Use sparingly. Explain *why*, not *what*. If you need to explain *what* the code does, the code is too complex — refactor it.
- **No redundant comments:**

```python
# ❌ BAD
x = x + 1  # Increment x

# ✅ GOOD
x += 1  # Offset by 1 to account for zero-indexed file line numbers
```

---

## 7. Testing Practices

- **Every module gets a corresponding test file.** `src/scoring/engine.py` → `tests/unit/test_scoring_engine.py`
- **Test function names describe behavior:** `test_scoring_returns_zero_when_compile_fails`
- **Use Arrange-Act-Assert pattern:**

```python
def test_risk_level_is_critical_when_many_files_touched():
    # Arrange
    proposal = create_test_proposal(files_changed=15, lines_changed=600, coverage=0.1)

    # Act
    risk = classify_risk(proposal)

    # Assert
    assert risk == RiskLevel.CRITICAL
```

- **Use `pytest` fixtures** for shared setup. No test should depend on another test's state.
- **Use factory functions** (e.g., `create_test_proposal()`) instead of duplicating object construction in every test.
- **Mock external dependencies** (LLM, Git, vector DB) at the boundary, not deep internals. Prefer dependency injection.
- **No tests that hit real external APIs** unless tagged with `@pytest.mark.integration` and excluded from CI by default.

---

## 8. Project Structure & Modularity

- **One concern per module.** Don't mix Git operations with scoring logic in the same file.
- **Dependency direction:** `cli/` → `api/` → `agent/` → `scoring/`, `evaluation/`, `retrieval/` → `indexing/`, `git_ops/`, `llm/` → `db/`, `config/`, `schemas/`, `utils/`. Never import upward.
- **Use interfaces (Protocol classes)** for external dependencies (`LLMClient`, `EmbeddingClient`, `VectorDBClient`). This enables testing with mocks and swapping implementations.

```python
from typing import Protocol

class LLMClient(Protocol):
    def generate(self, messages: list[dict], **kwargs) -> LLMResponse: ...
    def count_tokens(self, text: str) -> int: ...
```

- **Keep `__init__.py` files lean.** Only re-export the public API of the module. No logic.
- **Configuration is injected, not imported globally.** Pass `Settings` as a parameter or use dependency injection, don't scatter `from src.config import settings` across every file.

---

## 9. Git & Version Control Practices

- **Commit messages:** Use conventional commits format: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- **Atomic commits.** Each commit is a single logical change that passes all tests.
- **Never commit secrets, `.env` files, or API keys.** Enforce via `.gitignore` and pre-commit hooks.
- **Branch naming:** `feature/<short-description>`, `fix/<short-description>`, `refactor/<short-description>`.

---

## 10. Performance & Resource Awareness

- **Use generators / iterators** for large data instead of loading everything into memory.
- **Batch API calls** (embeddings, LLM) rather than one-at-a-time.
- **Close resources explicitly** (files, DB connections, HTTP clients). Use context managers (`with`).
- **Profile before optimizing.** Don't prematurely optimize; write clear code first, then optimize bottlenecks with evidence.

```python
# ❌ BAD — loads all files into memory
all_chunks = [chunk for file in files for chunk in parse_file(file)]
embed_all(all_chunks)

# ✅ GOOD — processes in batches
for batch in batched(parse_files(files), batch_size=100):
    embed_batch(batch)
```

---

## 11. Security Defaults

- **Never log secrets.** Sanitize API keys, tokens, and passwords before logging.
- **Use parameterized queries** for all database operations (SQLAlchemy handles this, but be vigilant with raw SQL).
- **Validate all external input** (CLI args, API request bodies, webhook payloads) at the boundary.
- **Principle of least privilege.** The agent sandbox restricts file operations to the repo directory. Evaluation containers run with limited resources.
