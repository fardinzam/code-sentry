"""Configuration system for code-reviewer.

Implements a 5-layer hierarchy (§7.11):
  1. Built-in defaults (lowest priority)
  2. Global config: ~/.config/code-reviewer/config.toml
  3. Project config: <repo>/.code-reviewer/config.toml
  4. Environment variables: CODE_REVIEWER_<SECTION>_<KEY>
  5. CLI flags (highest priority — applied externally by CLI commands)

Sensitive values (api_key, auth_token, db_url, password, secret) are NEVER
read from config files. If present, the system logs a warning and ignores them.
"""

from __future__ import annotations

import logging
import os
try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]
import warnings
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.utils.constants import SENSITIVE_KEY_FRAGMENTS

logger = logging.getLogger(__name__)

# ─── Sub-section models ───────────────────────────────────────────────────────


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_LLM_")

    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens_per_task: int = 100_000
    request_timeout_seconds: int = 120
    max_retries: int = 3


class EmbeddingSettings(BaseSettings):
    """Embedding model configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_EMBEDDING_")

    provider: str = "openai"
    model: str = "text-embedding-3-small"
    batch_size: int = 100
    dimensions: int = 1536


class VectorDBSettings(BaseSettings):
    """Vector database configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_VECTORDB_")

    backend: str = "chromadb"
    persist_directory: str = ".code-reviewer/vectordb"
    collection_name: str = "codebase"
    similarity_threshold: float = 0.3
    top_k: int = 20


class IndexingSettings(BaseSettings):
    """Codebase indexing configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_INDEXING_")

    min_chunk_tokens: int = 30
    max_chunk_tokens: int = 1500
    target_chunk_tokens: int = 650
    max_file_tokens: int = 50_000
    context_lines: int = 3
    include_extensions: list[str] = Field(
        default=[".py", ".js", ".ts", ".java", ".go", ".rs", ".md", ".txt", ".yaml", ".toml", ".json"]
    )


class RetrievalSettings(BaseSettings):
    """RAG retrieval configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_RETRIEVAL_")

    top_k: int = 20
    keyword_weight: float = 0.3
    similarity_threshold: float = 0.3


class EvaluationSettings(BaseSettings):
    """Evaluation pipeline configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_EVALUATION_")

    profile: str = "full"  # quick | full | custom
    timeout_seconds: int = 600
    linter: str = "ruff"
    enable_perf: bool = False
    perf_regression_threshold_percent: float = 10.0
    perf_improvement_threshold_percent: float = 10.0
    perf_warmup_runs: int = 3
    perf_measurement_runs: int = 5
    perf_benchmark_timeout_seconds: int = 60
    perf_baseline_refresh_commits: int = 50


class ScoringSettings(BaseSettings):
    """Scoring algorithm configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_SCORING_")

    weight_correctness: float = 0.40
    weight_readability: float = 0.20
    weight_risk: float = 0.25
    weight_complexity: float = 0.15
    min_viable_score: int = 30

    @field_validator("weight_correctness", "weight_readability", "weight_risk", "weight_complexity")
    @classmethod
    def _must_be_fraction(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Scoring weights must be between 0.0 and 1.0")
        return v

    @model_validator(mode="after")
    def _weights_must_sum_to_one(self) -> "ScoringSettings":
        total = (
            self.weight_correctness
            + self.weight_readability
            + self.weight_risk
            + self.weight_complexity
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Scoring weights must sum to 1.0 (got {total:.3f})")
        return self


class GitSettings(BaseSettings):
    """Git integration configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_GIT_")

    auth_method: str = "auto"  # auto | ssh | https_token | credential_helper
    sandbox_retention_days: int = 7
    default_branch: str = "main"


class AgentSettings(BaseSettings):
    """Agent loop configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_AGENT_")

    max_iterations: int = 15
    max_refinement_rounds: int = 3


class ServerSettings(BaseSettings):
    """API server configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_SERVER_")

    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False
    workers: int = 1


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_DATABASE_")

    backend: str = "sqlite"  # sqlite | postgresql
    sqlite_path: str = ".code-reviewer/metadata.db"
    auto_migrate: bool = True


class CacheSettings(BaseSettings):
    """LLM response cache configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_CACHE_")

    backend: str = "sqlite"  # sqlite | redis
    llm_ttl_hours: int = 24
    embedding_ttl_days: int = 7
    max_size_mb: int = 500


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="CODE_REVIEWER_LOGGING_")

    level: str = "INFO"
    format: str = "json"  # json | text
    log_dir: str = ".code-reviewer/logs"
    max_bytes: int = 52_428_800  # 50 MB
    backup_count: int = 5


# ─── Root settings ────────────────────────────────────────────────────────────


class Settings:
    """Resolved configuration assembled from the 5-layer hierarchy.

    Do not instantiate directly. Use get_settings() which applies
    the layered merge correctly.
    """

    def __init__(
        self,
        llm: LLMSettings | None = None,
        embedding: EmbeddingSettings | None = None,
        vectordb: VectorDBSettings | None = None,
        indexing: IndexingSettings | None = None,
        retrieval: RetrievalSettings | None = None,
        evaluation: EvaluationSettings | None = None,
        scoring: ScoringSettings | None = None,
        git: GitSettings | None = None,
        agent: AgentSettings | None = None,
        server: ServerSettings | None = None,
        database: DatabaseSettings | None = None,
        cache: CacheSettings | None = None,
        logging: LoggingSettings | None = None,
    ) -> None:
        self.llm = llm or LLMSettings()
        self.embedding = embedding or EmbeddingSettings()
        self.vectordb = vectordb or VectorDBSettings()
        self.indexing = indexing or IndexingSettings()
        self.retrieval = retrieval or RetrievalSettings()
        self.evaluation = evaluation or EvaluationSettings()
        self.scoring = scoring or ScoringSettings()
        self.git = git or GitSettings()
        self.agent = agent or AgentSettings()
        self.server = server or ServerSettings()
        self.database = database or DatabaseSettings()
        self.cache = cache or CacheSettings()
        self.logging = logging or LoggingSettings()


# ─── TOML Loading ─────────────────────────────────────────────────────────────

_SECTION_MAP: dict[str, type] = {
    "llm": LLMSettings,
    "embedding": EmbeddingSettings,
    "vectordb": VectorDBSettings,
    "indexing": IndexingSettings,
    "retrieval": RetrievalSettings,
    "evaluation": EvaluationSettings,
    "scoring": ScoringSettings,
    "git": GitSettings,
    "agent": AgentSettings,
    "server": ServerSettings,
    "database": DatabaseSettings,
    "cache": CacheSettings,
    "logging": LoggingSettings,
}


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load a TOML config file, stripping sensitive keys and warning on each."""
    if not path.exists():
        return {}

    with path.open("rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    return _strip_sensitive(raw, str(path))


def _strip_sensitive(data: dict[str, Any], source: str) -> dict[str, Any]:
    """Recursively remove sensitive keys from config data, warning for each."""
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            cleaned[key] = _strip_sensitive(value, source)
        elif any(fragment in key.lower() for fragment in SENSITIVE_KEY_FRAGMENTS):
            warnings.warn(
                f"Sensitive key '{key}' found in config file '{source}'. "
                "It has been ignored. Use environment variables instead.",
                stacklevel=4,
            )
        else:
            cleaned[key] = value
    return cleaned


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override onto base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _build_section(section_name: str, merged_toml: dict[str, Any]) -> Any:
    """Instantiate a settings sub-model from merged TOML data.

    Env vars are automatically picked up by pydantic-settings via env_prefix.
    """
    cls = _SECTION_MAP[section_name]
    toml_data = merged_toml.get(section_name, {})
    # pydantic-settings picks up env vars automatically on instantiation
    return cls(**toml_data)


def get_settings(project_root: Path | None = None) -> Settings:
    """Build the resolved Settings object from all config layers.

    Args:
        project_root: Root directory of the target repository. If None,
            uses the current working directory.

    Returns:
        Fully resolved Settings instance.
    """
    root = project_root or Path.cwd()

    # Layer 2: global config
    global_toml = _load_toml_file(
        Path.home() / ".config" / "code-reviewer" / "config.toml"
    )

    # Layer 3: project config
    project_toml = _load_toml_file(root / ".code-reviewer" / "config.toml")

    merged = _merge(global_toml, project_toml)

    return Settings(
        **{name: _build_section(name, merged) for name in _SECTION_MAP}
    )
