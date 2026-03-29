"""Project-wide constants.

All magic numbers and string literals live here. Never scatter them inline.
"""

# ─── Indexing ────────────────────────────────────────────────────────────────
MIN_CHUNK_TOKENS: int = 30
MAX_CHUNK_TOKENS: int = 1500
TARGET_CHUNK_TOKENS: int = 650  # midpoint of 500-800 target range
CHUNK_CONTEXT_LINES: int = 3  # leading/trailing lines attached as metadata
MAX_FILE_TOKENS: int = 50_000
MAX_FILE_COUNT_WARN: int = 50_000
MAX_FILE_COUNT_HARD: int = 200_000
MAX_SYMLINK_DEPTH: int = 5
DEFAULT_EMBEDDING_BATCH_SIZE: int = 100

# ─── Agent ───────────────────────────────────────────────────────────────────
DEFAULT_MAX_ITERATIONS: int = 15
DEFAULT_MAX_TOKENS_PER_TASK: int = 100_000
FINAL_ITERATION_THRESHOLD: int = 1  # iterations remaining before forcing submit
DEFAULT_MAX_REFINEMENT_ROUNDS: int = 3
JSON_VALIDATION_MAX_RETRIES: int = 3

# ─── Scoring ─────────────────────────────────────────────────────────────────
SCORE_WEIGHT_CORRECTNESS: float = 0.40
SCORE_WEIGHT_READABILITY: float = 0.20
SCORE_WEIGHT_RISK: float = 0.25
SCORE_WEIGHT_COMPLEXITY: float = 0.15
MIN_VIABLE_SCORE: int = 30

# ─── Evaluation ──────────────────────────────────────────────────────────────
DEFAULT_EVAL_TIMEOUT_SECONDS: int = 600  # 10 minutes
DEFAULT_EVAL_MEMORY_GB: int = 4
BASELINE_REFRESH_COMMITS: int = 50
BENCHMARK_REGRESSION_THRESHOLD_PERCENT: float = 10.0
BENCHMARK_IMPROVEMENT_THRESHOLD_PERCENT: float = 10.0
BENCHMARK_WARMUP_RUNS: int = 3
BENCHMARK_MEASUREMENT_RUNS: int = 5
BENCHMARK_TIMEOUT_SECONDS: int = 60

# ─── Caching ─────────────────────────────────────────────────────────────────
LLM_CACHE_TTL_HOURS: int = 24
EMBEDDING_CACHE_TTL_DAYS: int = 7
LLM_CACHE_MAX_SIZE_MB: int = 500
HIGH_TEMPERATURE_CACHE_BYPASS: float = 0.5

# ─── Git / Sandbox ───────────────────────────────────────────────────────────
SANDBOX_BRANCH_PREFIX: str = "ai-review"
DEFAULT_SANDBOX_RETENTION_DAYS: int = 7

# ─── Monitoring ──────────────────────────────────────────────────────────────
LOG_MAX_BYTES: int = 50 * 1024 * 1024  # 50 MB
LOG_BACKUP_COUNT: int = 5
LOG_RETENTION_DAYS: int = 30
ALERT_EVAL_FAILURE_RATE_THRESHOLD: float = 0.20
ALERT_COST_BUDGET_WARN_PERCENT: float = 0.80
ALERT_QUEUE_DEPTH_WARN: int = 20
ALERT_DISK_FREE_MIN_GB: float = 1.0

# ─── API ─────────────────────────────────────────────────────────────────────
API_V1_PREFIX: str = "/api/v1"

# ─── Sensitive config key fragments (never read from config files) ────────────
SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = ("api_key", "auth_token", "db_url", "password", "secret")
