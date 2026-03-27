"""Project-level exception hierarchy.

All exceptions raised by this system are subclasses of CodeReviewerError.
The four top-level classes map directly to §14.1 error classification.
"""


class CodeReviewerError(Exception):
    """Base class for all code-reviewer errors."""


# ─── §14.1 Error Classes ──────────────────────────────────────────────────────


class TransientError(CodeReviewerError):
    """Temporary failure likely to resolve on retry (e.g. rate limit, timeout)."""


class RecoverableError(CodeReviewerError):
    """Failure requiring corrective action, but the task can continue."""


class FatalTaskError(CodeReviewerError):
    """Failure that terminates the current task but not the system."""


class FatalSystemError(CodeReviewerError):
    """Failure threatening system integrity — halts the affected subsystem."""


# ─── Domain-specific errors ───────────────────────────────────────────────────


class ConfigError(CodeReviewerError):
    """Invalid or missing configuration."""


class LLMError(CodeReviewerError):
    """Error communicating with an LLM provider."""


class LLMAuthError(FatalTaskError):
    """LLM API key is invalid or expired. Do not retry."""


class LLMBudgetExhaustedError(FatalTaskError):
    """Token or cost budget exhausted for this task."""


class GitError(CodeReviewerError):
    """Error executing a Git operation."""


class DiffApplicationError(RecoverableError):
    """Diff could not be applied cleanly to the sandbox branch."""


class IndexingError(CodeReviewerError):
    """Error during codebase indexing."""


class ParseError(RecoverableError):
    """AST parsing failed for a source file."""


class EmbeddingError(TransientError):
    """Error calling the embedding API."""


class VectorDBError(CodeReviewerError):
    """Error communicating with the vector database."""


class EvaluationError(CodeReviewerError):
    """Error running the evaluation pipeline."""


class ScoringError(CodeReviewerError):
    """Error computing the quality score."""


class SchemaValidationError(RecoverableError):
    """Agent output does not conform to the expected JSON schema."""


class SandboxError(CodeReviewerError):
    """Error managing a sandbox Git branch."""


class RepositoryTooLargeError(FatalTaskError):
    """Repository exceeds the hard file-count limit for indexing."""
