# Agentic AI Code Reviewer — Development Task List

> **Source of truth:** [PROJECT_REQUIREMENTS.md](./PROJECT_REQUIREMENTS.md)  
> **Timeline:** 16 weeks across 6 phases  
> **Legend:** `[ ]` = not started, `[/]` = in progress, `[x]` = done

---

## Phase 1: Foundation (Weeks 1–3)

**Goal:** Project scaffolding, Git integration, code indexing pipeline, basic RAG retrieval, and CLI skeleton.

### 1.1 Project Scaffolding

- [ ] Initialize Python project with `pyproject.toml` (Python 3.11+, project name `code-reviewer`)
- [ ] Set up directory structure:
  ```
  src/
    cli/           # Typer CLI commands
    api/           # FastAPI server (placeholder)
    agent/         # ReAct agent loop
    indexing/      # AST parsing, chunking, embedding
    retrieval/     # Vector search, hybrid retrieval
    evaluation/    # Compile/test/lint pipeline
    scoring/       # Quality scoring algorithm
    schemas/       # Pydantic models, JSON schemas
    git_ops/       # Git integration module
    llm/           # LLM client abstraction
    db/            # Database models + migrations
    config/        # Configuration loading
      prompts/     # System prompt templates
        examples/  # Few-shot examples (JSON files)
    utils/         # Shared utilities
  tests/
    unit/
    integration/
    fixtures/      # Canonical test repo, LLM cassettes
  ```
- [ ] Configure development tooling:
  - [ ] `ruff` for linting (create `ruff.toml` with project rules)
  - [ ] `mypy` for type checking (create `mypy.ini` or `pyproject.toml` section)
  - [ ] `pytest` as test runner with `pytest.ini` or `pyproject.toml` section
  - [ ] `pre-commit` hooks for lint + type check
- [ ] Create `.gitignore` (Python, `.env`, `.code-reviewer/`, `node_modules/`, IDE files)
- [ ] Create `.reviewerignore` template (default patterns for generated code, vendor dirs)
- [ ] Set up GitHub Actions CI pipeline stub:
  - [ ] Lint job (`ruff check .`)
  - [ ] Type check job (`mypy src/`)
  - [ ] Test job (`pytest tests/unit/`)
- [ ] Write `README.md` with project overview, install instructions (placeholder), and badge placeholders

### 1.2 Configuration System (§7.11)

- [ ] Implement config loader (`src/config/settings.py`):
  - [ ] Parse TOML files using `tomli` (Python 3.11+ has `tomllib`)
  - [ ] Implement 5-layer hierarchy: defaults → global `~/.config/code-reviewer/config.toml` → project `<repo>/.code-reviewer/config.toml` → env vars (`CODE_REVIEWER_<SECTION>_<KEY>`) → CLI flags
  - [ ] Define Pydantic `Settings` model with all config keys from §7.11.2 (llm, embedding, vectordb, indexing, retrieval, evaluation, scoring, git, server, logging) with typed defaults
  - [ ] Sensitive value enforcement: warn + ignore if `api_key`, `auth_token`, or `db_url` found in config files (§7.11.3)
- [ ] Create default `config.toml` template at `config/default_config.toml` (shipped with package)
- [ ] Write `code-reviewer config` CLI command:
  - [ ] `config show` — print resolved config (mask sensitive values)
  - [ ] `config init` — generate `.code-reviewer/config.toml` in current repo with comments
  - [ ] `config validate` — check config for errors
- [ ] **Tests:**
  - [ ] Unit test: config hierarchy merging (5 layers, later overrides earlier)
  - [ ] Unit test: sensitive value detection and masking
  - [ ] Unit test: env var to config key mapping (`CODE_REVIEWER_LLM_MODEL` → `llm.model`)

### 1.3 Logging & Audit Trail (§8.2)

- [ ] Implement structured JSON logger (`src/utils/logging.py`):
  - [ ] JSON lines format (one JSON object per log line)
  - [ ] Configurable log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`
  - [ ] Rotating file handler: max 50 MB per file, keep 5 backups (from `[logging]` config)
  - [ ] Console handler with human-readable format option
- [ ] Implement audit trail logger (separate from application logs):
  - [ ] Immutable append-only log for agent actions, LLM calls, file modifications
  - [ ] Each entry includes: timestamp, event_type, task_id, details (JSON)
  - [ ] Stored at `.code-reviewer/audit/` with one file per task
- [ ] **Tests:**
  - [ ] Unit test: JSON log format correctness
  - [ ] Unit test: rotation triggers at size limit
  - [ ] Unit test: audit trail immutability (append-only)

### 1.4 Git Integration Module (§12.1)

- [ ] Implement `GitClient` class (`src/git_ops/client.py`) wrapping `subprocess` calls to `git`:
  - [ ] `clone(url, path)` — clone repo via HTTPS or SSH
  - [ ] `create_branch(name)` — create and checkout a new branch
  - [ ] `delete_branch(name)` — delete local (and optionally remote) branch
  - [ ] `apply_diff(patch_text)` — apply a unified diff via `git apply`
  - [ ] `apply_diff_check(patch_text)` — dry-run via `git apply --check --3way`
  - [ ] `generate_diff(base_ref, head_ref)` — produce unified diff between two refs
  - [ ] `get_commit_log(n)` — return last N commits with messages
  - [ ] `get_changed_files(base_ref)` — list files changed since a ref
  - [ ] `is_dirty()` — check for uncommitted changes
  - [ ] `get_current_sha()` — return HEAD commit SHA
- [ ] Implement authentication for private repos (§12.1.1):
  - [ ] Auto-detect mode: use system's existing Git credential config
  - [ ] SSH key mode: configure `GIT_SSH_COMMAND` with key from `CODE_REVIEWER_GIT_SSH_KEY`
  - [ ] HTTPS token mode: inject token from `CODE_REVIEWER_GIT_TOKEN` into clone URLs
  - [ ] Credential helper mode: delegate to `git credential-helper`
  - [ ] Sanitize clone URLs before logging (strip embedded tokens)
- [ ] Implement sandbox branch manager (`src/git_ops/sandbox.py`):
  - [ ] Create sandbox branches with `ai-review/<uuid4>` naming (§8.1)
  - [ ] Atomic diff application with rollback on failure (§14.3)
  - [ ] Branch cleanup: delete branches older than `sandbox_retention_days`
  - [ ] Dirty-state guard: refuse to create sandbox if repo has uncommitted changes
- [ ] Write `code-reviewer cleanup` CLI command — list/remove stale `ai-review/*` branches
- [ ] **Tests:**
  - [ ] Unit test: URL sanitization (token stripped from logged URLs)
  - [ ] Integration test: clone → branch → apply diff → generate diff → delete branch (using temp Git repo)
  - [ ] Integration test: dirty-state detection blocks sandbox creation
  - [ ] Integration test: atomic rollback on partial multi-file diff failure

### 1.5 AST Parser & Code Chunker (§7.1)

- [ ] Implement tree-sitter parser wrapper (`src/indexing/parser.py`):
  - [ ] Install `tree-sitter` and language grammars for Python (+ Java optional)
  - [ ] Parse source files into ASTs
  - [ ] Extract function/method definitions with name, line range, docstring
  - [ ] Extract class definitions with methods list
  - [ ] Handle parse failure: log warning, mark file as `parse_failed`
- [ ] Implement AST-aware chunker (`src/indexing/chunker.py`) per §7.1.1:
  - [ ] Chunking hierarchy: function/method → class (if small) → class split into methods → module-level → file-level fallback
  - [ ] Size constraints: min 30 tokens, max 1,500 tokens, target 500–800 tokens
  - [ ] Merge chunks smaller than min with their next sibling
  - [ ] Split chunks larger than max at the next-lower AST boundary
  - [ ] Context: include 3 lines leading/trailing as metadata (not embedded)
  - [ ] Signature carry-forward: when splitting class, prepend class signature to each method chunk
- [ ] Implement non-code document chunker:
  - [ ] Markdown: split at `## heading` boundaries
  - [ ] Plain text: split at double-newline (paragraph)
  - [ ] Config files (YAML, TOML, JSON): single chunk per file
  - [ ] Attach docstrings and inline comments to their parent code chunk
- [ ] Implement large file handling:
  - [ ] Skip files exceeding `max_file_tokens` (default 50K)
  - [ ] Still index metadata (path, size, language) for structural context
  - [ ] Log warning with file path and token count
- [ ] Implement `.reviewerignore` + `.gitignore` filtering
- [ ] Implement line-based fallback chunking when AST parse fails
- [ ] **Tests:**
  - [ ] Unit test: Python function extraction captures name, lines, docstring
  - [ ] Unit test: chunk size constraints (min merge, max split)
  - [ ] Unit test: class splitting with signature carry-forward
  - [ ] Unit test: Markdown heading-based splitting
  - [ ] Unit test: large file skip with warning
  - [ ] Unit test: fallback chunking on parse failure

### 1.6 Embedding Pipeline (§7.1, §1.4)

- [ ] Implement embedding client abstraction (`src/indexing/embedder.py`):
  - [ ] `EmbeddingClient` interface with `embed_batch(texts: list[str]) -> list[list[float]]`
  - [ ] OpenAI adapter: uses `text-embedding-3-small` (configurable)
  - [ ] Ollama adapter: uses local embedding model
  - [ ] Batch size control (default: 100 chunks per API call)
  - [ ] Rate-limit handling with exponential backoff (transient error, §14.2)
- [ ] Implement vector DB integration (`src/indexing/vectordb.py`):
  - [ ] ChromaDB adapter (local development): create collection, add embeddings, query
  - [ ] Store per-chunk metadata: file path, language, function/class name, line range, imports, `chunk_method`
  - [ ] Batch commit per-file granularity (no partial writes)
- [ ] Implement indexing orchestrator (`src/indexing/pipeline.py`):
  - [ ] Walk repository files (respecting ignore patterns)
  - [ ] Parse → chunk → embed → store pipeline
  - [ ] Progress display: files parsed, chunks created, time elapsed (via `rich` progress bar)
  - [ ] Checkpoint file (`.code-reviewer/index_checkpoint.json`) for resume on crash (§14.2)
  - [ ] Repository size guardrails (§8.3): pre-indexing validation (file count, LOC, binary detection, symlink depth)
  - [ ] Complexity/cost estimate display before indexing
- [ ] Write CLI commands:
  - [ ] `code-reviewer init <repo-path>` — register a project + create `.code-reviewer/` directory
  - [ ] `code-reviewer index` — run full indexing pipeline
  - [ ] `code-reviewer index --resume` — resume from checkpoint
  - [ ] `code-reviewer index --status` — show indexing stats
- [ ] **Tests:**
  - [ ] Unit test: embedding client batching and retry logic
  - [ ] Integration test: full indexing pipeline (parse → chunk → embed → store) on a small test repo
  - [ ] Integration test: checkpoint creation and resume after simulated crash
  - [ ] Unit test: repository size guardrail enforcement

### 1.7 Basic RAG Retrieval (§7.2)

- [ ] Implement retrieval module (`src/retrieval/search.py`):
  - [ ] Vector similarity search via ChromaDB with `top_k` and `similarity_threshold` filtering
  - [ ] Keyword/symbol search via text matching on chunk metadata (function names, file paths)
  - [ ] Hybrid search: combine vector + keyword results with configurable `keyword_weight` (§7.11.2)
  - [ ] De-duplicate results across search methods
  - [ ] Rank and return top-K chunks with relevance scores
- [ ] Implement prompt builder (`src/retrieval/prompt_builder.py`):
  - [ ] Assemble prompts via the 5-stage pipeline (§7.10.2): system prompt → retrieved context → structural context → conversation history → output instructions
  - [ ] Token budget allocation and enforcement (count tokens via `tiktoken`)
  - [ ] Overflow handling: truncate lowest-relevance retrieved chunks first
  - [ ] Build file tree summary and import graph for structural context stage
- [ ] **Tests:**
  - [ ] Unit test: hybrid search ranking (vector + keyword combination)
  - [ ] Unit test: token budget enforcement (truncation at correct stage)
  - [ ] Integration test: index a test repo → query → verify relevant chunks returned

### 1.8 LLM Client Abstraction (§12.2, §7.13)

- [ ] Implement `LLMClient` interface (`src/llm/client.py`):
  - [ ] `generate(messages, **kwargs) -> LLMResponse` method
  - [ ] `count_tokens(text) -> int` method
  - [ ] Response model: `LLMResponse(content, input_tokens, output_tokens, model, latency_ms)`
- [ ] Implement provider adapters:
  - [ ] OpenAI adapter via `openai` Python SDK (supports `response_format: json_object`)
  - [ ] Anthropic adapter via `anthropic` Python SDK
  - [ ] Ollama adapter via HTTP API (`localhost:11434`)
  - [ ] vLLM adapter via OpenAI-compatible HTTP API
- [ ] Implement retry logic:
  - [ ] Exponential backoff on rate limits (429) and timeouts (transient errors)
  - [ ] Max 3 retries, then raise `LLMError`
  - [ ] Immediate halt on auth errors (401/403) — no retry
- [ ] Implement token budget tracking:
  - [ ] Per-task token counter (input + output cumulative)
  - [ ] Alert when approaching budget (>80% of `max_tokens_per_task`)
  - [ ] Hard stop at budget limit
- [ ] Implement LLM response caching (§7.13):
  - [ ] SHA-256 cache key from model + temperature + prompt hash
  - [ ] SQLite `llm_cache` table for local storage
  - [ ] TTL: 24 hours for LLM responses, 7 days for embeddings
  - [ ] LRU eviction at max cache size (500 MB)
  - [ ] Bypass: `temperature > 0.5`, final iteration, `--no-cache` flag
  - [ ] Invalidation: full cache clear on model/temperature config change
- [ ] Implement cost tracking (§8.2.3):
  - [ ] Per-request cost estimation from provider pricing table
  - [ ] Per-task cost accumulation (stored with task metadata)
  - [ ] Monthly cost rollup query
  - [ ] Budget alerting: warn at 80%, halt at 100% of `max_monthly_cost_usd`
- [ ] **Tests:**
  - [ ] Unit test: token counting accuracy
  - [ ] Unit test: retry logic (429 retried, 401 not retried)
  - [ ] Unit test: cache hit/miss behavior
  - [ ] Unit test: TTL expiration and LRU eviction
  - [ ] Unit test: budget halt at limit

---

## Phase 2: Agent Core (Weeks 4–6)

**Goal:** Working ReAct agent loop that can analyze code and propose changes across multiple task types.

### 2.1 System Prompt Templates (§7.10.1)

- [x] Create common preamble template (`config/prompts/system_common.txt`) with placeholder variables: `{repo_name}`, `{primary_language}`, `{default_branch}`, `{head_sha}`
- [x] Create task-specific prompt extensions:
  - [x] `config/prompts/refactor.txt` — code quality improvement instructions
  - [x] `config/prompts/bug_fix.txt` — root cause analysis + fix instructions
  - [x] `config/prompts/review_pr.txt` — PR critique instructions
  - [x] `config/prompts/health_scan.txt` — broad code health audit instructions
  - [x] `config/prompts/explain.txt` — code understanding instructions
- [x] Create few-shot examples:
  - [x] `config/prompts/examples/review_pr_example.json` — one-shot PR review example
  - [x] `config/prompts/examples/format_correction.json` — dynamic few-shot for validation failures
- [x] Implement prompt assembler (`src/agent/prompt_assembler.py`):
  - [x] Load system prompt templates and fill placeholders
  - [x] Select task-specific extension based on `task_type`
  - [x] Inject few-shot examples when appropriate (§7.10.4)
  - [x] Wire into the 5-stage prompt construction pipeline (§7.10.2)

### 2.2 ReAct Agent Loop (§7.3, §7.10.5)

- [x] Implement agent orchestrator (`src/agent/orchestrator.py`):
  - [x] Main loop: assemble prompt → call LLM → parse response → execute tool → capture observation → repeat
  - [x] Iteration counter with `remaining_iterations` passed to each prompt
  - [x] Max iteration enforcement (default: 15, configurable)
  - [x] Token budget tracking per task (cumulative across iterations)
  - [x] Final iteration forcing: "Submit your best proposal now or give up"
  - [x] `give_up` handling: terminate gracefully, log reasoning, mark FAILED
- [x] Implement conversation history management:
  - [x] Append `{ thought, action, observation }` per iteration
  - [x] Summarize oldest iterations when history exceeds Stage 4 token budget
  - [x] Always keep the 3 most recent iterations in full
- [x] Implement structured output parsing (§7.10.3):
  - [x] Parse LLM JSON response via Pydantic validators
  - [x] Validation failure retry chain: re-prompt with error (attempt 1) → salvage partial (attempt 2) → mark FAILED (attempt 3)
  - [x] Use `response_format: json_object` when supported by provider

### 2.3 Agent Tools (§7.3 FR-3.2)

- [x] Implement tool registry (`src/agent/tools/registry.py`):
  - [x] Register tools by name with input/output schemas
  - [x] Dispatch tool calls from agent responses
  - [x] Capture tool output as observation string
- [x] Implement individual tools:
  - [x] `file_read(path, start_line, end_line)` — read file contents from the repo
  - [x] `vector_search(query, top_k)` — semantic search over indexed codebase
  - [x] `ast_query(file_path, symbol_name)` — query AST for function/class definitions, callers
  - [x] `file_write(path, content)` — write to file **within sandbox branch only**
  - [x] `shell_exec(command)` — run sandboxed shell command (with allowlist)
  - [x] `git_op(operation, args)` — Git operations (diff, log, show)
  - [x] `submit_proposal(proposal_json)` — submit final proposal
  - [x] `give_up(reason)` — terminate task gracefully
- [x] Sandbox enforcement: `file_write` and `shell_exec` reject operations outside the repo directory

### 2.4 Proposal Schema & Validation (§10.3)

- [ ] Implement Pydantic models (`src/schemas/proposal.py`):
  - [ ] `AgentProposal` model matching §10.3.1 JSON schema (all fields, types, constraints)
  - [ ] `FileChange` model with `path`, `diff`, `change_type`, `summary`
  - [ ] `PartialProposal` model for §10.3.3 partial responses
  - [ ] `FailedTask` model for §10.3.3 failed task responses
  - [ ] `PRReview` model for §10.3.4 PR review variant (inline comments, quality score)
- [ ] Implement validation rules (§10.3.2):
  - [ ] Title length 10–120 chars
  - [ ] Explanation length ≥ 50 chars
  - [ ] `files_changed` has 1–20 items, no duplicate paths
  - [ ] Each `diff` parsed by `unidiff` library for format validity
  - [ ] Each `diff` dry-run via `git apply --check`
  - [ ] Confidence vs. risk consistency check (warning only)
- [ ] Store JSON Schema at `src/schemas/proposal_v1.json` for external consumers
- [ ] Implement `schema_version` field injection on persisted proposals
- [ ] **Tests:**
  - [ ] Unit test: valid proposal passes all validators
  - [ ] Unit test: missing required fields triggers re-prompt
  - [ ] Unit test: diff format validation (valid + invalid cases)
  - [ ] Unit test: title/explanation length constraints

### 2.5 Diff Format Translation (§7.4.1)

- [ ] Implement diff translator (`src/git_ops/diff_translator.py`):
  - [ ] Stage 1: Extract diff blocks from LLM JSON (regex for ```diff fences and `--- / +++ / @@` patterns)
  - [ ] Stage 2: Normalize format — fix missing headers, incorrect `@@` hunk line numbers, whitespace
  - [ ] Stage 3: Parse with `unidiff` Python library
  - [ ] Stage 4: Dry-run `git apply --check --3way`
  - [ ] Stage 5: Apply `git apply` + `git add` + `git commit`
- [ ] Implement auto-fix strategies for common LLM errors:
  - [ ] Re-compute `@@` hunk headers by matching context lines against actual file
  - [ ] Infer missing `--- a/` / `+++ b/` headers from proposal `path` field
  - [ ] Attempt `git apply --ignore-whitespace` for whitespace corruption
  - [ ] Rebuild context lines from actual file when LLM hallucinated surrounding code
- [ ] **Tests:**
  - [ ] Unit test: diff extraction from JSON with code fences
  - [ ] Unit test: header inference from path field
  - [ ] Unit test: `@@` hunk recomputation
  - [ ] Integration test: full pipeline on valid and invalid LLM-style diffs

### 2.6 Task Types: REFACTOR & BUG_FIX (§7.10.1)

- [ ] Implement refactoring task runner (`src/agent/tasks/refactor.py`):
  - [ ] Scope analysis: identify target files/modules from user input or health scan output
  - [ ] Agent prompt: code smells (duplication, complexity, naming, dead code)
  - [ ] Post-proposal validation: ensure no behavior change (tests must still pass)
- [ ] Implement bug-fix task runner (`src/agent/tasks/bug_fix.py`):
  - [ ] Accept bug report or failing test as input
  - [ ] Agent prompt: root cause localization, fix proposal, regression risk assessment
  - [ ] Post-proposal validation: the specific failing test should now pass
- [ ] Write CLI commands:
  - [ ] `code-reviewer propose refactor [--scope <path>] [--exclude <path>] [--focus "description"]`
  - [ ] `code-reviewer propose bug-fix --description "..." [--test <test_id>]`
  - [ ] `code-reviewer status [<task-id>]` — show task status
- [ ] Implement agent reasoning audit trail:
  - [ ] Log every tool call with args and response
  - [ ] Log every LLM prompt (hashed for deduplication) and response
  - [ ] Store per-task at `.code-reviewer/audit/<task-id>.jsonl`
- [ ] **Tests:**
  - [ ] Agent test: refactor task with mocked LLM responses (pre-recorded cassettes)
  - [ ] Agent test: bug-fix task with mocked LLM responses
  - [ ] Integration test: full propose → validate diff → commit on sandbox branch

---

## Phase 3: Evaluation Pipeline (Weeks 7–8)

**Goal:** Automated validation of proposed changes through compile, test, lint, and optional perf steps.

### 3.1 Evaluation Pipeline Orchestrator (§7.5)

- [ ] Implement pipeline orchestrator (`src/evaluation/pipeline.py`):
  - [ ] Step runner: execute each step sequentially (compile → test → lint → perf)
  - [ ] Per-step timeout enforcement (default: 10 min, configurable)
  - [ ] Capture per-step: pass/fail status, stdout/stderr (last 500 lines on timeout), timing
  - [ ] Configurable evaluation profiles: `quick` (lint only), `full` (compile + test + lint), `custom`
  - [ ] Step skip logic: if compile fails, skip test (but still run lint)
- [ ] Per-step result model (`src/schemas/evaluation.py`):
  - [ ] `EvaluationStepResult(step, status, duration_ms, stdout, stderr, exit_code)`
  - [ ] Status enum: `RUNNING`, `PASSED`, `FAILED`, `TIMEOUT`, `SKIPPED`
- [ ] Implement pre-change baseline runner:
  - [ ] Run tests/lint on base branch first to capture existing failures
  - [ ] Cache baseline results per commit SHA
  - [ ] Compute delta: `post_failures - pre_failures` (only new failures count against proposal)

### 3.2 Evaluation Steps

- [ ] Implement compile/build check step (`src/evaluation/steps/compile.py`):
  - [ ] Auto-detect build system: `pyproject.toml` → `pip install -e .`, `setup.py` → `python setup.py build`, `Makefile` → `make`
  - [ ] Capture exit code + stderr
- [ ] Implement test execution step (`src/evaluation/steps/test.py`):
  - [ ] Auto-detect test runner: `pytest`, `unittest`, `tox`
  - [ ] Run full test suite on sandbox branch
  - [ ] Parse test results for pass/fail count (via `pytest --tb=short -q`)
  - [ ] Detect crash vs. test assertion failure (distinguish exit codes)
- [ ] Implement lint check step (`src/evaluation/steps/lint.py`):
  - [ ] Run configured linter (`ruff`, `flake8`, `pylint`) on changed files only
  - [ ] Compute delta: new warnings/errors introduced vs. baseline
  - [ ] Handle "linter not installed" gracefully: `SKIPPED` with reason
- [ ] Implement performance benchmark step (`src/evaluation/steps/perf.py`) per §7.5.1:
  - [ ] Load benchmark definitions from `.code-reviewer/benchmarks.toml`
  - [ ] Run baselines if not cached, or load from `.code-reviewer/benchmarks/baseline_<sha>.json`
  - [ ] Execute benchmarks with warmup and measurement runs
  - [ ] Compute delta percentage: flag as REGRESSION/IMPROVEMENT/NEUTRAL
  - [ ] Auto-refresh baseline after N commits (configurable)

### 3.3 Container Isolation (§7.5 FR-5.9)

- [ ] Implement containerized evaluation runner (`src/evaluation/container.py`):
  - [ ] Docker-based: build image from repo's Dockerfile or generate a minimal one
  - [ ] Memory limit via `--memory` flag (default 4 GB, from §8.3)
  - [ ] Timeout enforcement via Docker's `--stop-timeout`
  - [ ] Volume mount: sandbox branch worktree (read-only for compile/test)
  - [ ] Fallback: if Docker unavailable, run in subprocess with `ulimit` resource limits
  - [ ] Mark fallback as `DEGRADED_MODE` in evaluation metadata

### 3.4 CLI: Evaluation Results Display

- [ ] Extend `code-reviewer status <task-id>` to show evaluation results:
  - [ ] Per-step pass/fail with timing
  - [ ] Test count: `347 passed, 0 failed (2 new since base)`
  - [ ] Lint delta: `+0 errors, +1 warning (new: line 45 in utils.py)`
  - [ ] Performance: `startup: 1.2s → 1.3s (+8%, NEUTRAL)`
- [ ] Implement `code-reviewer logs <task-id> [--step compile|test|lint|perf]` — display raw logs
- [ ] **Tests:**
  - [ ] Integration test: full evaluation pipeline on a test repo with known pass/fail
  - [ ] Unit test: delta computation (pre-change vs. post-change)
  - [ ] Unit test: benchmark regression detection formula
  - [ ] Integration test: container runner with resource limits

---

## Phase 4: Scoring & Explanation (Weeks 9–10)

**Goal:** Composite quality scores, risk classification, human-readable explanations, and accept/reject workflow.

### 4.1 Composite Scoring Algorithm (§7.6)

- [ ] Implement scoring engine (`src/scoring/engine.py`):
  - [ ] Compute correctness sub-score from evaluation results (§7.6.2)
  - [ ] Compute readability sub-score from lint delta (§7.6.2)
  - [ ] Compute risk sub-score from blast radius analysis (§7.6.3)
  - [ ] Compute complexity reduction sub-score using `radon` (§7.6.4)
  - [ ] Apply configurable weights (default: 0.40 / 0.20 / 0.25 / 0.15)
  - [ ] Produce composite score 0–100
  - [ ] Redistribute weights if a sub-score is unavailable (e.g., complexity tools missing)
- [ ] Implement risk classification matrix (§7.6.3):
  - [ ] Score 3 dimensions: files touched, change magnitude, test coverage of changed code
  - [ ] Map total points to risk level: LOW / MEDIUM / HIGH / CRITICAL
- [ ] Implement complexity metrics (§7.6.4):
  - [ ] Cyclomatic complexity via `radon` (pre vs. post)
  - [ ] Function length analysis via AST (pre vs. post)
  - [ ] Nesting depth analysis via AST
- [ ] Implement minimum viable score check (default: 30):
  - [ ] Flag proposals below threshold as "not recommended" in UI/CLI
- [ ] **Tests:**
  - [ ] Unit test: scoring formula with known inputs → expected score
  - [ ] Unit test: risk matrix point calculation and level mapping
  - [ ] Unit test: weight redistribution when complexity is unavailable
  - [ ] Calibration test: 20 known-good + 20 known-bad proposals against expected scores (§7.6.5)

### 4.2 Explanation Generation (§7.7)

- [ ] Implement explanation generator (`src/scoring/explainer.py`):
  - [ ] If agent already produced a good explanation → use it directly
  - [ ] If explanation is too short or missing → LLM call with the diff + evaluation results to generate one
  - [ ] Format: what changed, why, expected impact, risks (per FR-7.2)
- [ ] Implement proposal Markdown report export:
  - [ ] Title, score, risk level, explanation
  - [ ] File-by-file diff with syntax highlighting (using `pygments`)
  - [ ] Evaluation results summary
  - [ ] Exportable as `.md` file or rendered in CLI/Web UI

### 4.3 Accept/Reject Workflow (UC-6)

- [ ] Implement `code-reviewer accept <proposal-id>`:
  - [ ] Merge sandbox branch into the target branch (or fast-forward)
  - [ ] Record acceptance in metadata DB with reviewer comment (optional)
  - [ ] Log human override if score was below minimum
- [ ] Implement `code-reviewer reject <proposal-id> [--reason "..."]`:
  - [ ] Mark proposal as `REJECTED` in metadata DB
  - [ ] Optionally clean up sandbox branch immediately
  - [ ] Preserve audit trail and reasoning
- [ ] Implement `code-reviewer revise <proposal-id> --feedback "..."`:
  - [ ] Pass original proposal + evaluation results + user feedback to agent
  - [ ] Agent generates revised proposal on same sandbox branch (amend)
  - [ ] Re-run evaluation pipeline
  - [ ] Max refinement rounds: 3 (configurable)
- [ ] Implement partial acceptance for multi-file proposals:
  - [ ] `code-reviewer accept <proposal-id> --files src/a.py src/b.py` — accept only specified files
  - [ ] Rejected files are dropped; accepted files are committed
- [ ] **Tests:**
  - [ ] Integration test: accept merges sandbox branch correctly
  - [ ] Integration test: reject preserves audit trail
  - [ ] Integration test: revise loop (propose → feedback → revise → re-evaluate)

### 4.4 CLI: Scoring & Explanation Display

- [ ] Extend `code-reviewer status <proposal-id>` with score display:
  - [ ] Composite score with sub-score breakdown
  - [ ] Risk level badge (colored: green/yellow/orange/red)
  - [ ] One-line summary
- [ ] Implement `code-reviewer diff <proposal-id>`:
  - [ ] Syntax-highlighted unified diff in terminal (via `rich`)
  - [ ] Side-by-side mode (optional flag `--side-by-side`)
- [ ] Implement `code-reviewer explain <proposal-id>`:
  - [ ] Display full explanation text
- [ ] Implement `code-reviewer export <proposal-id> --format md`:
  - [ ] Export Markdown report to file

---

## Phase 5: Web UI & API (Weeks 11–13)

**Goal:** FastAPI REST API, WebSocket real-time updates, and a browser-based dashboard.

### 5.1 Database Layer (§10)

- [ ] Implement SQLAlchemy models (`src/db/models.py`) matching §10.1 data entities:
  - [ ] `Project` (id, name, repo_path, config, created_at, updated_at)
  - [ ] `IndexRun` (id, project_id, status, stats, started_at, completed_at)
  - [ ] `Task` (id, project_id, type, status, parameters, created_at, updated_at)
  - [ ] `Proposal` (id, task_id, schema_version, title, status, score, risk_level, data JSON, created_at)
  - [ ] `EvaluationRun` (id, proposal_id, profile, steps JSON, started_at, completed_at)
  - [ ] `AuditLogEntry` (id, task_id, event_type, timestamp, data JSON)
  - [ ] `DeadLetterTask` (id, task_id, failure_reason, error_message, retry_count, status)
  - [ ] `HealthScanResult` (id, project_id, commit_sha, summary JSON, issues JSON, scanned_at)
  - [ ] `LLMCacheEntry` (id, cache_key, response, tokens_used, created_at, expires_at)
- [ ] Set up Alembic migrations (`src/db/migrations/`):
  - [ ] Initial migration: create all tables
  - [ ] Configure for both SQLite and PostgreSQL dialects
- [ ] Implement DB session management with `async_sessionmaker` (async SQLAlchemy)
- [ ] Write `code-reviewer db upgrade` / `db downgrade` / `db export` / `db import` / `db validate` CLI commands (§16.4)

### 5.2 FastAPI REST API (§11)

- [ ] Set up FastAPI application (`src/api/app.py`):
  - [ ] CORS middleware (restricted origins from config)
  - [ ] Request ID middleware (attach UUID to each request for tracing)
  - [ ] Error handler: generic error messages to client, full details logged server-side
  - [ ] API key authentication middleware (optional, from `CODE_REVIEWER_SERVER_API_KEY`)
- [ ] Implement API endpoints:
  - [ ] `POST /api/v1/projects` — register a project
  - [ ] `GET /api/v1/projects` — list projects
  - [ ] `GET /api/v1/projects/{id}` — project details
  - [ ] `POST /api/v1/projects/{id}/index` — trigger indexing
  - [ ] `GET /api/v1/projects/{id}/index/status` — indexing status
  - [ ] `POST /api/v1/projects/{id}/tasks` — create a new task
  - [ ] `GET /api/v1/projects/{id}/tasks` — list tasks
  - [ ] `GET /api/v1/tasks/{id}` — task details
  - [ ] `GET /api/v1/tasks/{id}/proposals` — list proposals for a task
  - [ ] `GET /api/v1/proposals/{id}` — proposal detail (score, diff, explanation)
  - [ ] `POST /api/v1/proposals/{id}/accept` — accept a proposal
  - [ ] `POST /api/v1/proposals/{id}/reject` — reject a proposal
  - [ ] `POST /api/v1/proposals/{id}/revise` — request changes with feedback
  - [ ] `GET /api/v1/proposals/{id}/evaluation` — evaluation results
  - [ ] `GET /api/v1/proposals/{id}/audit` — audit trail
  - [ ] `POST /api/v1/projects/{id}/query` — natural language query (§7.2.1)
  - [ ] `POST /api/v1/projects/{id}/scan` — trigger health scan
  - [ ] `GET /api/v1/projects/{id}/scans` — list health scan results
  - [ ] `GET /api/v1/health` — system health check
  - [ ] `GET /metrics` — Prometheus-compatible metrics endpoint (§8.2.2)
- [ ] Implement background task dispatch:
  - [ ] Celery/RQ integration for async task execution (indexing, agent tasks, evaluation)
  - [ ] Task priority levels: HIGH (user-initiated), NORMAL, LOW (background scans)
  - [ ] Task deduplication check (§8.1)
- [ ] Implement rate limiting per §13 Security Considerations
- [ ] **Tests:**
  - [ ] API test: all endpoint contracts (request/response shapes)
  - [ ] API test: auth required endpoints reject unauthenticated requests
  - [ ] API test: rate limiting triggers 429 after threshold

### 5.3 WebSocket & Real-Time Updates (§7.9.1)

- [ ] Implement WebSocket endpoint (`ws://host:port/ws/events?project_id=<id>`):
  - [ ] Project-scoped channels
  - [ ] Event types: proposal status change, evaluation step completion, agent iteration progress, indexing progress, health scan completion
  - [ ] Throttle agent iteration events to max 1/sec
- [ ] Implement SSE fallback for HTMX mode (`/api/v1/events/stream`)
- [ ] Wire background task workers to emit events on state changes

### 5.4 Web UI (§7.9)

- [ ] Set up React (Vite) or Jinja2+HTMX frontend (based on final tech choice):
  - [ ] If React: initialize with Vite, install Zustand or React Query, set up router
  - [ ] If Jinja2+HTMX: create template directory, base layout, HTMX includes
- [ ] Implement pages:
  - [ ] **Dashboard** — health summary widget, recent proposals list, cost summary, active tasks
  - [ ] **Proposal List** — table with filters (status, type, score, date), pagination, live status updates via WebSocket
  - [ ] **Proposal Detail** — diff viewer (side-by-side + inline, syntax-highlighted), explanation panel, score breakdown, evaluation results timeline, accept/reject/revise buttons
  - [ ] **Evaluation Results** — per-step pass/fail cards with expandable logs and timing
  - [ ] **Agent Audit Trail** — ReAct iteration viewer (thought → action → observation timeline)
  - [ ] **Health Report** — issue list by severity/category, health score over time chart (line graph, last 30 scans)
  - [ ] **NL Query** — "Ask the codebase" input + answer panel with source citations
  - [ ] **Settings** — project config editor, user preferences
- [ ] Design system:
  - [ ] Dark mode support (toggle)
  - [ ] Responsive layout (mobile/tablet)
  - [ ] Component library: score badge, risk level indicator, diff viewer, log viewer, progress bar
- [ ] Implement optimistic updates:
  - [ ] Accept/reject updates status locally before server round-trip
  - [ ] New task creates placeholder card immediately
- [ ] Implement offline handling:
  - [ ] WebSocket reconnect with fallback to polling (10s interval)
  - [ ] "Connection lost — reconnecting..." banner
- [ ] **Tests:**
  - [ ] UI test: dashboard renders with mock data
  - [ ] UI test: proposal detail displays diff and scores
  - [ ] UI test: accept/reject buttons trigger correct API calls

---

## Phase 6: Polish & Production Readiness (Weeks 14–16)

**Goal:** Docker deployment, CI/CD integration, health scans, performance optimization, documentation, and portfolio readiness.

### 6.1 Error Handling & Recovery (§14)

- [ ] Implement error classification layer (`src/utils/errors.py`):
  - [ ] Error class hierarchy: `TransientError`, `RecoverableError`, `FatalTaskError`, `FatalSystemError`
  - [ ] Decorator/wrapper for automatic retry on transient errors (max 3, exponential backoff 2s base)
- [ ] Implement indexing error recovery (§14.2):
  - [ ] File-level skip on parse failure
  - [ ] `pending_embeddings` queue for retry
  - [ ] Checkpoint-based resume
- [ ] Implement sandbox error recovery (§14.3):
  - [ ] Branch name collision: append random suffix and retry once
  - [ ] Atomic rollback: `git reset --hard` on partial diff failure
  - [ ] Re-prompt agent with apply error for corrected diff
- [ ] Implement evaluation error recovery (§14.4):
  - [ ] Pre-existing failure baselining
  - [ ] Container fallback to subprocess with `ulimit`
- [ ] Implement agent error recovery (§14.5):
  - [ ] Malformed JSON re-prompt chain (3 attempts)
  - [ ] Token budget final iteration ("submit or give up")
  - [ ] Tool errors passed as observations
- [ ] Implement graceful degradation (§14.6):
  - [ ] Vector DB down → keyword/grep fallback
  - [ ] Redis down → synchronous in-process execution
  - [ ] LLM down → queue tasks, retry every 60s
  - [ ] Git remote down → local-only mode
- [ ] Implement dead letter queue (§14.7):
  - [ ] Persist failed tasks with metadata
  - [ ] CLI: `tasks --failed`, `tasks retry <id>`, `tasks abandon <id>`, `tasks retry-all`
  - [ ] Automatic retry for transient failures (backoff: 30s → 2min → 10min)
- [ ] **Tests:**
  - [ ] Unit test: retry decorator with mock transient errors
  - [ ] Integration test: dead letter queue round-trip (fail → persist → retry → succeed)
  - [ ] Integration test: graceful degradation (simulate vector DB down)

### 6.2 Concurrency & Locking (§8.1)

- [ ] Implement file-based locks (`src/utils/locks.py`):
  - [ ] Repo-level mutex for branch create/delete
  - [ ] Branch-level exclusive lock for `git apply`
  - [ ] Repo-level exclusive lock for re-indexing
  - [ ] Lock files stored at `.code-reviewer/locks/`
- [ ] Implement file-level conflict detection:
  - [ ] Query in-flight proposals for affected file lists
  - [ ] Queue new task if overlap with EVALUATING proposal
- [ ] Implement task queue with priority levels:
  - [ ] Celery/RQ queue with HIGH/NORMAL/LOW priority
  - [ ] Task deduplication (reject identical pending tasks)
  - [ ] Max concurrent agents: 1; max concurrent evaluations: 5

### 6.3 Health Scan Implementation (§7.12)

- [ ] Implement health scan runner (`src/agent/tasks/health_scan.py`):
  - [ ] 9 check categories: complexity, duplication, dead code, TODO/FIXME, test coverage gaps, dependency health, naming consistency, security anti-patterns, documentation gaps
  - [ ] Use `radon` for complexity, `semgrep` for security, AST analysis for dead code / naming / docs, `pip-audit` for dependencies
  - [ ] Issue severity classification: CRITICAL / ERROR / WARNING / INFO (§7.12.2)
- [ ] Implement health report model matching §7.12.3 schema:
  - [ ] Summary with totals by severity and category
  - [ ] Health score (0–100)
  - [ ] Per-issue detail: category, severity, file, line, title, description, suggested action, auto_fixable flag
- [ ] Implement trend tracking (§7.12.4):
  - [ ] Compare current scan to most recent previous scan
  - [ ] Compute deltas: issues_delta, health_score_delta, new_issues, resolved_issues
- [ ] Implement scheduled scans:
  - [ ] `code-reviewer scan` — one-off scan
  - [ ] `code-reviewer scan --schedule "0 2 * * *"` — cron schedule (nightly at 2am)
  - [ ] Store Celery Beat schedule for recurring scans
- [ ] **Tests:**
  - [ ] Unit test: each health check category against canonical test repo with known issues
  - [ ] Unit test: health score calculation
  - [ ] Unit test: trend delta computation
  - [ ] Integration test: full scan → report → trend comparison on test repo

### 6.4 NL Query Interface (§7.2.1)

- [ ] Implement query handler (`src/agent/tasks/explain.py`):
  - [ ] Accept free-form natural language question
  - [ ] Select retrieval strategy based on query type heuristic (location / explanation / architecture / usage / comparison / debugging)
  - [ ] Adjusted context budget: 70% retrieved, 15% structural, 5% output, 10% response
  - [ ] Return structured response: answer (Markdown), sources, confidence, follow-up suggestions
- [ ] Wire into CLI: `code-reviewer ask "question about the codebase"`
- [ ] Wire into API: `POST /api/v1/projects/{id}/query`
- [ ] **Tests:**
  - [ ] Agent test: query with mocked LLM, verify source citations
  - [ ] Integration test: index test repo → ask question → verify sources reference correct files

### 6.5 PR Review Integration (§12.3)

- [ ] Implement PR review task type (`src/agent/tasks/review_pr.py`):
  - [ ] Accept PR diff (from local `git diff` or GitHub API)
  - [ ] Produce inline comments (PRReview schema, §10.3.4)
  - [ ] Overall assessment: APPROVE / REQUEST_CHANGES / COMMENT
  - [ ] Quality score 0–100
- [ ] Implement GitHub PR integration:
  - [ ] Fetch PR diff via GitHub API (`CODE_REVIEWER_GITHUB_TOKEN`)
  - [ ] Post review comments as PR review via GitHub API
  - [ ] Create check runs for evaluation results (if GitHub App auth configured)
- [ ] Implement webhook receiver:
  - [ ] `POST /api/v1/webhooks/github` — receive PR events
  - [ ] HMAC signature verification (§13 Security)
  - [ ] Auto-trigger review on `pull_request.opened` / `pull_request.synchronize`
- [ ] CLI: `code-reviewer review --pr <ref>` (generic CI command)
- [ ] **Tests:**
  - [ ] Agent test: PR review with mocked LLM, verify inline comment structure
  - [ ] API test: webhook signature verification (valid + invalid)
  - [ ] Integration test: webhook → review → comment (mocked GitHub API)

### 6.6 Docker & Deployment (§16)

- [ ] Create `Dockerfile` for the API server + worker
- [ ] Create `docker-compose.yml` (§16.2):
  - [ ] `api` — FastAPI server
  - [ ] `worker` — Celery worker for background tasks
  - [ ] `redis` — task queue and cache backend
  - [ ] `chromadb` — vector database
  - [ ] `postgres` — metadata database (optional, can use SQLite for local)
  - [ ] `ollama` — local LLM (optional)
- [ ] Write `code-reviewer db` migration commands (§16.4):
  - [ ] `db export`, `db check`, `db upgrade`, `db import`, `db validate`
  - [ ] Auto-migrate on startup (if `[database] auto_migrate = true`)
- [ ] Implement `/api/v1/health` endpoint:
  - [ ] Check DB connectivity, vector DB, Redis, LLM provider
  - [ ] Return per-component status
- [ ] Write environment-specific config templates (dev, staging, production)
- [ ] **Tests:**
  - [ ] Docker Compose stack starts cleanly (`docker-compose up -d`, health checks pass)
  - [ ] E2E test: index → propose → evaluate → accept on Dockerized stack

### 6.7 Monitoring & Alerting (§8.2)

- [ ] Implement Prometheus metrics endpoint (`/metrics`):
  - [ ] All 9 metrics from §8.2.2 (proposals, evaluations, LLM tokens/latency, queue depth)
  - [ ] Use `prometheus_client` Python library
- [ ] Implement LLM cost tracking (§8.2.3):
  - [ ] `code-reviewer costs --period month` — CLI cost report
  - [ ] Web UI cost-over-time chart
- [ ] Implement alerting (§8.2.4):
  - [ ] Log-based alerts for 5 triggers (eval failure rate, cost budget, vector DB, queue depth, disk space)
  - [ ] Optional webhook delivery (Slack-compatible JSON)

### 6.8 Testing & Quality Assurance (§15)

- [ ] Create canonical test repository (`tests/fixtures/test_repo/`):
  - [ ] ~50 files, ~5K LOC Python
  - [ ] Seeded issues: dead code, duplicated functions, a known bug, lint violations, high-complexity function
  - [ ] Working test suite with one intentionally failing test (for bug-fix task testing)
- [ ] Create LLM response cassettes (`tests/fixtures/cassettes/`):
  - [ ] Pre-recorded responses for: refactor, bug-fix, PR review, health scan, explain
  - [ ] Deterministic agent tests that run without LLM API access
- [ ] Write remaining tests to reach coverage targets:
  - [ ] Unit tests: 80%+ coverage
  - [ ] Integration tests: all key workflows
  - [ ] Agent tests: all task types with cassettes
  - [ ] API tests: all endpoints
  - [ ] E2E test: full flow (index → propose → evaluate → score → accept) with local Ollama
- [ ] Finalize CI pipeline (§15.3):
  - [ ] `lint (ruff)` → `type-check (mypy)` → `unit tests` → `integration tests` → `build Docker image` → `E2E tests`

### 6.9 Documentation & Portfolio

- [ ] Write comprehensive `README.md`:
  - [ ] Project overview, architecture diagram, feature list
  - [ ] Installation: pip install, Docker Compose, development setup
  - [ ] Quick-start guide: init → index → propose → review → accept
  - [ ] Configuration reference (link to config schema)
  - [ ] API documentation (link to auto-generated OpenAPI docs)
- [ ] Write `CONTRIBUTING.md` with development setup, testing, and code style guidelines
- [ ] Ensure OpenAPI docs auto-generated by FastAPI at `/docs`
- [ ] Record portfolio demo:
  - [ ] Screen recording: CLI workflow (index → propose → evaluate → accept)
  - [ ] Screen recording: Web UI dashboard → proposal review → accept
  - [ ] Screenshots of: diff viewer, scoring breakdown, health report, audit trail
- [ ] Write `ARCHITECTURE.md` with system diagram, component responsibilities, data flow
