# Agentic AI Code Reviewer & Auto-Refactor System — Project Requirements Document

> **Version:** 1.0  
> **Date:** March 26, 2026  
> **Status:** Draft

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Goals & Non-Goals](#3-goals--non-goals)
4. [Target Users & Personas](#4-target-users--personas)
5. [Use Cases & User Flows](#5-use-cases--user-flows)
6. [System Architecture Overview](#6-system-architecture-overview)
7. [Functional Requirements](#7-functional-requirements)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [Tech Stack](#9-tech-stack)
10. [Data Model & Schema](#10-data-model--schema)
11. [API Design](#11-api-design)
12. [Integration Points](#12-integration-points)
13. [Security Considerations](#13-security-considerations)
14. [Error Handling & Recovery Strategy](#14-error-handling--recovery-strategy)
15. [Testing Strategy](#15-testing-strategy)
16. [Deployment Architecture](#16-deployment-architecture)
17. [Phased Roadmap](#17-phased-roadmap)
18. [Risks & Mitigations](#18-risks--mitigations)
19. [Success Metrics & KPIs](#19-success-metrics--kpis)
20. [Glossary](#20-glossary)

---

## 1. Executive Summary

This project delivers an **AI-powered agentic system** that ingests a production codebase (source code, design docs, configuration), understands its structure and semantics, and autonomously proposes safe refactors and bug fixes. Every proposed change is applied in an isolated sandbox branch, validated through an automated evaluation pipeline (compile → test → lint → performance), scored for quality and risk, and presented as an auditable diff with a natural-language explanation — all before any human merge decision.

The system combines **LLM reasoning**, **vector-based code retrieval (RAG)**, **static analysis**, and **CI/CD orchestration** into a cohesive agentic workflow, exposed through both a CLI and a lightweight web UI.

---

## 2. Problem Statement

Modern production codebases accumulate technical debt, code smells, subtle bugs, and inconsistent patterns at a pace that outstrips manual review capacity. Engineering teams face:

- **Review bottleneck:** Senior engineers spend 20–30% of their time on code review, slowing feature velocity.
- **Debt accumulation:** Known refactors are deprioritized because safe execution requires deep context that is expensive to acquire.
- **Inconsistent quality:** Style, pattern, and architectural adherence erode as teams scale.
- **Risk aversion:** Large-scale refactors are avoided because the blast radius is hard to predict without running full validation suites.

There is no existing open-source tool that combines codebase understanding, autonomous change proposal, sandboxed validation, and auditable scoring into a single agentic loop.

---

## 3. Goals & Non-Goals

### 3.1 Goals

| ID | Goal | Priority |
|----|------|----------|
| G1 | Index and semantically understand a repository of up to 500K LOC (code + docs) | P0 |
| G2 | Let an AI agent autonomously identify refactoring opportunities and bug-fix candidates | P0 |
| G3 | Apply proposed changes in an isolated sandbox branch with zero impact on main | P0 |
| G4 | Run an automated evaluation pipeline: compile, unit tests, linting, and basic performance benchmarks | P0 |
| G5 | Produce an auditable diff with a natural-language explanation for every proposed change | P0 |
| G6 | Score each change on correctness, readability, performance impact, and risk | P1 |
| G7 | Provide a CLI for developers to interact with the system from the terminal | P0 |
| G8 | Provide a lightweight web UI for browsing proposals, diffs, scores, and agent logs | P1 |
| G9 | Support configurable LLM backends (OpenAI API, local open-weight models via Ollama/vLLM) | P1 |
| G10 | Generate a comprehensive audit trail for every agent action (traceability) | P1 |

### 3.2 Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG1 | Auto-merging changes without human approval | Safety — this is a human-in-the-loop system |
| NG2 | Supporting non-Git version control systems | Focused scope |
| NG3 | Real-time collaborative editing | Out of scope; this is a batch/async review system |
| NG4 | Full IDE plugin (VS Code, IntelliJ) | Deferred to future iteration |
| NG5 | Multi-language support in a single repo analysis pass | V1 targets Python (or Java) monoglot repos |
| NG6 | Training or fine-tuning custom LLMs | System consumes pre-trained models via API |

---

## 4. Target Users & Personas

### Persona 1: Solo Developer / Open-Source Maintainer
- Maintains one or more medium-sized repos (10K–100K LOC).
- Wants automated help identifying tech debt and making safe improvements.
- Comfortable with CLI tools and Git workflows.

### Persona 2: Tech Lead at a Small-to-Mid Team
- Oversees 3–10 engineers committing to a shared repo.
- Needs to enforce coding standards and catch drift without personally reviewing every PR.
- Values auditable reports for compliance or architectural governance.

### Persona 3: Platform / DevOps Engineer
- Integrates tooling into CI/CD pipelines.
- Wants to plug in the reviewer as a GitHub Action or pipeline step.
- Cares about configurability, API access, and logging.

---

## 5. Use Cases & User Flows

### UC-1: On-Demand Codebase Analysis

**Actor:** Developer via CLI or Web UI  
**Trigger:** User initiates a review scan.  
**Flow:**
1. User points the system at a repository (local path or remote Git URL).
2. System indexes the codebase (parses ASTs, generates embeddings, stores in vector DB).
3. System presents a summary of codebase structure, health metrics, and detected issues.

### UC-2: AI-Proposed Refactoring

**Actor:** AI Agent (autonomous, triggered by user or schedule)  
**Trigger:** User requests "propose refactors" or agent runs on a cron schedule.  
**Flow:**
1. Agent retrieves relevant code chunks via vector search + AST analysis.
2. Agent reasons about refactoring opportunities (code duplication, dead code, complex functions, naming inconsistencies, pattern violations).
3. For each opportunity, agent generates a concrete code diff.
4. Agent applies the diff to a sandbox branch.
5. Evaluation pipeline runs (compile → test → lint → perf).
6. Agent produces a scored report with the diff, explanation, and confidence level.
7. User reviews the proposal in the CLI or Web UI and decides to accept, reject, or request modification.

### UC-3: AI-Proposed Bug Fix

**Actor:** AI Agent  
**Trigger:** User provides a bug report, error log, or failing test. Alternatively, agent detects potential bugs via static analysis + LLM reasoning.  
**Flow:**
1. Agent localizes the bug using retrieval (vector search over error traces, logs, and code).
2. Agent generates a fix as a code diff.
3. Fix is applied in a sandbox branch and validated through the evaluation pipeline.
4. Agent explains the root cause, the fix, and why it is safe.
5. User reviews and decides.

### UC-4: Batch Review of Existing PRs

**Actor:** Developer or CI bot  
**Trigger:** A new pull request is opened.  
**Flow:**
1. System ingests the PR diff.
2. Agent analyzes the diff in context of the full codebase (via RAG).
3. Agent produces inline review comments, an overall assessment, and improvement suggestions.
4. Results are posted back as PR comments or displayed in the Web UI.

### UC-5: Scheduled Health Scan

**Actor:** Cron scheduler  
**Trigger:** Periodic (e.g., nightly or weekly).  
**Flow:**
1. Agent runs a full scan of the codebase on the latest commit.
2. Generates a health report: new issues since last scan, trend metrics, prioritized refactoring backlog.
3. Report is emailed or posted to a configured notification channel.

### UC-6: Iterative Proposal Refinement

**Actor:** Developer via CLI or Web UI  
**Trigger:** User reviews a proposal and wants modifications rather than outright acceptance or rejection.  
**Flow:**
1. User views a proposal and selects "Request Changes" (rather than Accept or Reject).
2. User provides feedback as free-text comments (e.g., "Good idea, but don't rename the public API method" or "Also fix the same issue in `utils.py`").
3. Agent receives the original proposal, the evaluation results, and the user feedback as context.
4. Agent generates a revised proposal on the same sandbox branch (amending, not creating a new branch).
5. Evaluation pipeline re-runs on the revised change.
6. User reviews the revised proposal. Cycle repeats up to a configurable max (default: 3 refinement rounds).

**Scope Constraints:**
- `propose --scope <path>` — limit the agent to a specific directory or file.
- `propose --exclude <path>` — exclude specific files from modifications.
- `propose --focus "description"` — natural language hint for what to focus on.

**Partial Acceptance:**
- For multi-file proposals, the user can accept individual file diffs and reject others.
- Accepted files are committed; rejected files are dropped from the proposal.
- Agent may be asked to regenerate only the rejected portions.

---

## 6. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface Layer                        │
│                    ┌────────────┐  ┌────────────┐                   │
│                    │  Web UI    │  │    CLI      │                   │
│                    └─────┬──────┘  └─────┬──────┘                   │
│                          │               │                          │
│                          ▼               ▼                          │
│                    ┌─────────────────────────┐                      │
│                    │      API Gateway        │                      │
│                    │   (FastAPI / Flask)      │                      │
│                    └────────┬────────────────┘                      │
│                             │                                       │
├─────────────────────────────┼───────────────────────────────────────┤
│                     Core Services Layer                             │
│                             │                                       │
│  ┌──────────────┐  ┌───────┴────────┐  ┌─────────────────────┐     │
│  │  Indexing     │  │  Agent         │  │  Evaluation          │    │
│  │  Pipeline     │  │  Orchestrator  │  │  Pipeline            │    │
│  │              │  │  (ReAct Loop)  │  │  (Compile/Test/Lint) │     │
│  └──────┬───────┘  └───────┬────────┘  └──────────┬──────────┘     │
│         │                  │                       │                │
│  ┌──────┴───────┐  ┌──────┴────────┐  ┌───────────┴─────────┐     │
│  │  AST Parser  │  │  LLM Client   │  │  Git Sandbox        │     │
│  │  + Chunker   │  │  (Multi-      │  │  Manager            │     │
│  │              │  │   Provider)   │  │                     │      │
│  └──────────────┘  └───────────────┘  └─────────────────────┘     │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│                       Data Layer                                   │
│                                                                    │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────────┐     │
│  │  Vector DB   │  │  Metadata     │  │  Audit Log          │     │
│  │  (ChromaDB / │  │  Store        │  │  Store              │     │
│  │   Qdrant)    │  │  (SQLite /    │  │  (SQLite /          │     │
│  │              │  │   Postgres)   │  │   File-based)       │     │
│  └──────────────┘  └───────────────┘  └─────────────────────┘     │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | Responsibility |
|-----------|---------------|
| **Web UI** | Browser-based dashboard for browsing proposals, diffs, scores, and logs |
| **CLI** | Terminal interface for all operations (index, scan, review, configure) |
| **API Gateway** | RESTful API serving both UI and CLI; handles auth and request routing |
| **Indexing Pipeline** | Parses source code into ASTs, chunks files, generates embeddings, stores in vector DB |
| **Agent Orchestrator** | Core agentic loop (ReAct pattern) — observes, reasons, acts, validates |
| **Evaluation Pipeline** | Runs compile, test, lint, and performance checks on sandbox branches |
| **AST Parser + Chunker** | Language-specific parsing (tree-sitter or ast module) and intelligent code chunking |
| **LLM Client** | Abstracted interface to LLM providers (OpenAI, Anthropic, Ollama, vLLM) |
| **Git Sandbox Manager** | Creates/manages sandbox branches, applies diffs, and handles Git operations |
| **Vector DB** | Stores code embeddings for similarity search and RAG retrieval |
| **Metadata Store** | Persists project config, scan history, proposal status, and user preferences |
| **Audit Log Store** | Immutable log of every agent action, LLM call, and evaluation result |

---

## 7. Functional Requirements

### 7.1 Codebase Indexing & Embedding Pipeline

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | System SHALL clone or ingest a Git repository from a local path or remote URL | P0 |
| FR-1.2 | System SHALL parse source files into Abstract Syntax Trees (ASTs) using tree-sitter or language-native parsers | P0 |
| FR-1.3 | System SHALL chunk source files intelligently at function/class/module boundaries (not naïve line-based splitting) | P0 |
| FR-1.4 | System SHALL generate vector embeddings for each code chunk using a configurable embedding model (e.g., OpenAI `text-embedding-3-small`, `nomic-embed-text`, `code-bert`) | P0 |
| FR-1.5 | System SHALL store embeddings in a vector database (ChromaDB for local, Qdrant for production) | P0 |
| FR-1.6 | System SHALL index non-code documents (README, design docs, ADRs, inline comments) alongside code | P1 |
| FR-1.7 | System SHALL support incremental re-indexing (only re-embed files changed since last index) | P1 |
| FR-1.8 | System SHALL extract and store metadata per chunk: file path, language, function/class name, line range, imports, dependencies | P0 |
| FR-1.9 | System SHALL respect `.gitignore` and a configurable `.reviewerignore` for excluding paths | P0 |
| FR-1.10 | System SHALL display indexing progress and statistics (files parsed, chunks created, time elapsed) | P1 |

#### 7.1.1 Chunking Strategy

Code files are chunked using AST-aware splitting. Non-code files fall back to semantic splitting.

**AST-Based Chunking Hierarchy (priority order):**

| Chunk Boundary | When Used | Example |
|----------------|-----------|---------|
| **Function / Method** | Default for all functions and methods | A single Python `def` or Java method |
| **Class** | When a class is ≤ max chunk size (including all methods) | A small dataclass or DTO |
| **Class → individual methods** | When a class exceeds max chunk size | Each method becomes its own chunk; class docstring is a separate chunk |
| **Module-level code** | Top-level statements not inside a function/class | Import block, global constants, `if __name__` block |
| **File-level** | Fallback when AST parsing fails entirely | The whole file as a single chunk (if under max), or line-based split |

**Size Constraints:**

| Parameter | Default | Configurable | Notes |
|-----------|---------|-------------|-------|
| Min chunk size | 30 tokens (~3 lines) | Yes | Chunks smaller than this are merged with the next sibling |
| Max chunk size | 1,500 tokens (~150 lines) | Yes | Chunks exceeding this are split at the next-lower AST boundary |
| Target chunk size | 500–800 tokens | Yes | Ideal chunk size for embedding quality |
| Max file size | 50,000 tokens (~5,000 lines) | Yes | Files exceeding this are skipped with a warning (likely generated code) |

**Overlap Strategy:**

- **Context window:** Each chunk includes 3 lines of leading context (preceding code) and 3 lines of trailing context as metadata (not embedded, but included when the chunk is retrieved for prompts).
- **Signature carry-forward:** When a class is split into per-method chunks, each method chunk includes the class signature and docstring as a prefix (counted against the chunk's token budget).
- **No embedding overlap:** Overlapping tokens are NOT double-embedded (avoids inflating vector DB size and skewing similarity scores).

**Non-Code Document Chunking:**

| Document Type | Chunking Strategy |
|---------------|-------------------|
| Markdown (README, ADRs, design docs) | Split at `## heading` boundaries. Each section = one chunk. Sections exceeding max chunk size are split at paragraph breaks. |
| Plain text | Split at double-newline (paragraph) boundaries |
| Inline code comments | Attached to the code chunk they belong to (not separate) |
| Docstrings | Attached to the function/class chunk they document |
| Config files (YAML, TOML, JSON) | Indexed as a single chunk per file (usually small) |

**Large File Handling:**

Files exceeding the max file size (default 50K tokens) are:
1. Logged as a warning (`"Skipping large file: {path} ({tokens} tokens)"`)
2. Excluded from embedding
3. Still indexed in metadata (file path, size, language) for structural context
4. Retrievable by explicit file path query but not by similarity search

**Fallback When AST Parsing Fails:**

If tree-sitter fails to parse a file (syntax errors, unsupported language features):
1. Log warning: `"AST parse failed for {path}: {error}. Falling back to line-based chunking."`
2. Split the file at blank-line boundaries (heuristic paragraph splitting)
3. Apply min/max chunk size constraints
4. Mark all chunks from this file with `chunk_method: "line_based"` in metadata

### 7.2 Code Understanding & Retrieval (RAG)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | System SHALL support hybrid retrieval: vector similarity search + keyword/symbol search | P0 |
| FR-2.2 | System SHALL resolve cross-file references (imports, function calls) to pull in relevant context | P1 |
| FR-2.3 | System SHALL rank retrieved chunks by relevance with a configurable top-K parameter | P0 |
| FR-2.4 | System SHALL construct LLM prompts that include retrieved context, file structure, and the user query | P0 |
| FR-2.5 | System SHALL support "question the codebase" — free-form natural language queries about code behavior, architecture, and design | P1 |
| FR-2.6 | System SHALL build a dependency graph of modules/packages to inform context retrieval | P2 |

#### 7.2.1 Natural Language Query Interface

The "question the codebase" feature (FR-2.5) allows free-form queries. This section specifies query handling in detail.

**Supported Query Types:**

| Query Category | Example | Retrieval Strategy |
|---------------|---------|-------------------|
| **Location** ("Where is X?") | "Where is the database connection pool initialized?" | Keyword search on function/class names + vector search |
| **Explanation** ("What does X do?") | "What does the `process_payment` function do?" | Direct file read (if path/name known) + vector search for callers |
| **Architecture** ("How does X work?") | "How does the authentication flow work end-to-end?" | Broad vector search + dependency graph traversal |
| **Usage** ("Where is X used?") | "Where is the `UserService` class used?" | AST-based reference search (import/call graph) + keyword search |
| **Comparison** ("What's the difference?") | "What's the difference between `save_draft` and `publish`?" | Direct file reads for both targets + vector search for context |
| **Debugging** ("Why does X happen?") | "Why does the cache return stale data after 60 seconds?" | Vector search on error-related terms + config file retrieval |

**Response Format:**

```json
{
  "answer": "string — natural language answer in Markdown format",
  "sources": [
    {
      "file": "string — relative file path",
      "lines": "string — line range (e.g., '45-67')",
      "relevance": "number 0.0–1.0",
      "snippet": "string — relevant code excerpt"
    }
  ],
  "confidence": "number 0.0–1.0",
  "follow_up_suggestions": ["string — suggested follow-up questions"]
}
```

**Context Window Budget for Queries:** Queries use the same prompt construction pipeline as agent tasks (§7.10.2), but with adjusted allocations:
- Retrieved context: 70% (more context, since no conversation history)
- Structural context: 15%
- Output instructions: 5%
- Reserved for response: 10%

### 7.3 AI Agent Orchestration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | System SHALL implement a ReAct-style agent loop: Observe → Think → Act → Validate | P0 |
| FR-3.2 | Agent SHALL have access to the following tools: file read, file write (sandbox only), vector search, AST query, run shell command (sandboxed), Git operations | P0 |
| FR-3.3 | Agent SHALL maintain a scratchpad / working memory of its reasoning chain | P0 |
| FR-3.4 | Agent SHALL enforce a maximum iteration count per task to prevent infinite loops (configurable, default: 15) | P0 |
| FR-3.5 | Agent SHALL enforce a maximum token budget per task (configurable, default: 100K tokens) | P1 |
| FR-3.6 | Agent SHALL log every tool call, LLM prompt, and LLM response to the audit trail | P0 |
| FR-3.7 | Agent SHALL support multiple task types: `refactor`, `bug-fix`, `review-pr`, `health-scan`, `explain` | P0 |
| FR-3.8 | Agent SHALL produce structured output (JSON) for each proposal, conforming to a defined schema | P0 |
| FR-3.9 | Agent SHALL gracefully handle LLM errors (rate limits, timeouts, malformed responses) with retry + exponential backoff | P0 |
| FR-3.10 | Agent SHALL support configurable "personas" or system prompts to adjust review strictness and style | P2 |

### 7.4 Change Proposal & Sandbox Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | System SHALL create an isolated Git branch for each proposal (naming: `ai-review/<task-id>`) | P0 |
| FR-4.2 | System SHALL apply agent-generated diffs to the sandbox branch using `git apply` or programmatic patch | P0 |
| FR-4.3 | System SHALL validate that the diff applies cleanly; if not, agent retries with corrected diff | P0 |
| FR-4.4 | System SHALL support multi-file changes within a single proposal | P0 |
| FR-4.5 | System SHALL generate unified diffs (`diff --unified`) for human review | P0 |
| FR-4.6 | System SHALL clean up sandbox branches after a configurable retention period (default: 7 days) | P1 |
| FR-4.7 | System SHALL prevent the agent from modifying files outside the sandbox branch | P0 |
| FR-4.8 | System SHALL support reverting a sandbox branch to its pre-change state | P1 |

#### 7.4.1 Diff Format & LLM-to-Git Translation

LLMs produce diffs in various formats. The system normalizes them into valid unified diffs before applying.

**Expected LLM Output Format:**

The agent is instructed to produce standard unified diff format (as produced by `diff -u`):

```diff
--- a/src/utils/parser.py
+++ b/src/utils/parser.py
@@ -45,7 +45,8 @@ def parse_config(path: str):
     with open(path) as f:
-        data = json.load(f)
+        try:
+            data = json.load(f)
+        except json.JSONDecodeError as e:
+            raise ConfigError(f"Invalid JSON in {path}") from e
     return data
```

**Translation Pipeline:**

```
LLM raw output
     │
     ▼
┌─────────────────────────────┐
│ 1. Extract diff blocks      │  Regex extraction of ```diff fences
│    from JSON response       │  or unified diff patterns (--- / +++ / @@)
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 2. Normalize format         │  Fix common LLM errors:
│                             │  - Missing `--- a/` or `+++ b/` headers
│                             │  - Incorrect line numbers in @@ hunks
│                             │  - Whitespace-only diffs (stripped)
│                             │  - Missing trailing newlines
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 3. Parse with `unidiff`     │  Python library validates structure.
│                             │  Fails fast on malformed patches.
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 4. Dry-run: `git apply      │  Ensures patch applies cleanly
│    --check --3way`          │  against the sandbox branch.
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ 5. Apply: `git apply`       │  Applied to sandbox worktree.
│    + `git add` + `git commit │  Committed with metadata in message.
│    -m "agent: <title>"`     │
└─────────────────────────────┘
```

**Common LLM Diff Errors & Fixes:**

| Error | Detection | Auto-Fix |
|-------|-----------|----------|
| Incorrect `@@` line numbers | `unidiff` parse failure; `git apply --check` fails | Re-compute hunk headers by matching context lines against the actual file |
| Missing file headers (`--- a/`, `+++ b/`) | Regex check for header line pattern | Infer from `path` field in the proposal JSON and prepend headers |
| Inverted diff (additions marked as deletions) | Heuristic: if applying *increases* deletions where LLM said it was adding code | Swap `+`/`-` prefixes and re-validate |
| Whitespace corruption (tabs ↔ spaces) | `git apply` fails with "patch does not apply" | Attempt `git apply --ignore-whitespace`; if that fails, re-prompt agent |
| Context line mismatch (LLM hallucinated surrounding code) | `git apply` fails on context | Extract only `+`/`-` lines, rebuild context from the actual file, re-create patch |

If auto-fix fails after all attempts, the raw diff and error are sent back to the agent as an observation for retry (see §14.3 Sandbox Branch Failures).

### 7.5 Automated Evaluation Pipeline

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | System SHALL run compilation/build checks on the sandbox branch after applying changes | P0 |
| FR-5.2 | System SHALL run the project's unit test suite on the sandbox branch | P0 |
| FR-5.3 | System SHALL run a configurable linter (e.g., `ruff`, `flake8`, `pylint` for Python; `checkstyle` for Java) on changed files | P0 |
| FR-5.4 | System SHALL run basic performance benchmarks (if configured) to detect regressions | P2 |
| FR-5.5 | System SHALL capture pass/fail status, error output, and timing for each evaluation step | P0 |
| FR-5.6 | System SHALL compute a delta between pre-change and post-change evaluation results (e.g., "2 new lint warnings introduced", "all 347 tests pass") | P1 |
| FR-5.7 | System SHALL support configurable evaluation profiles (e.g., "quick" = lint only, "full" = compile + test + lint + perf) | P1 |
| FR-5.8 | System SHALL timeout long-running evaluation steps (configurable, default: 10 minutes per step) | P0 |
| FR-5.9 | System SHALL run evaluations in isolated containers or virtual environments to prevent side effects | P1 |

#### 7.5.1 Performance Benchmarking Step (FR-5.4)

When the `perf` evaluation step is enabled, the system runs user-defined benchmarks to detect performance regressions.

**What Constitutes a Benchmark:**

| Benchmark Type | Description | Tool |
|---------------|-------------|------|
| **Execution time** | Wall-clock time for specific functions or scripts | `pytest-benchmark`, `hyperfine`, or custom `time`-based wrapper |
| **Memory usage** | Peak memory consumption during benchmark execution | `tracemalloc` (Python), `/usr/bin/time -v` |
| **Throughput** | Operations per second for data-processing or I/O code | Custom benchmark scripts |
| **Startup time** | Application cold-start time | `hyperfine --warmup 3` |

**Baseline Establishment:**

1. When `perf` is first enabled or when `code-reviewer benchmark --baseline` is run, the system executes all configured benchmarks on the **current base branch commit**.
2. Results are stored as the baseline in `.code-reviewer/benchmarks/baseline_{commit_sha}.json`.
3. Baselines are automatically refreshed when the base branch advances by more than 50 commits since the last baseline (configurable via `[evaluation.perf] baseline_refresh_commits`).

**Regression Detection:**

```
For each benchmark metric:
  delta_percent = ((post_value - baseline_value) / baseline_value) × 100

  If delta_percent > regression_threshold:
    → Flag as REGRESSION
  If delta_percent < -improvement_threshold:
    → Flag as IMPROVEMENT
  Else:
    → Flag as NEUTRAL
```

| Parameter | Default | Config Key |
|-----------|---------|-----------|
| Regression threshold | +10% (slower/more memory) | `[evaluation.perf] regression_threshold_percent` |
| Improvement threshold | −10% (faster/less memory) | `[evaluation.perf] improvement_threshold_percent` |
| Warmup runs | 3 | `[evaluation.perf] warmup_runs` |
| Measurement runs | 5 | `[evaluation.perf] measurement_runs` |
| Timeout per benchmark | 60 seconds | `[evaluation.perf] benchmark_timeout_seconds` |

**Benchmark Configuration:**

Users define benchmarks in `.code-reviewer/benchmarks.toml`:

```toml
[[benchmark]]
name = "process_batch"
command = "python -m pytest tests/benchmarks/test_batch.py --benchmark-only"
metric = "execution_time"       # execution_time | memory | throughput
unit = "seconds"

[[benchmark]]
name = "startup"
command = "hyperfine --warmup 3 'python -m myapp --dry-run'"
metric = "execution_time"
unit = "seconds"
```

**Benchmark Result Schema:**

```json
{
  "benchmark_name": "string",
  "metric": "execution_time | memory | throughput",
  "baseline_value": "number",
  "post_change_value": "number",
  "delta_percent": "number",
  "status": "REGRESSION | IMPROVEMENT | NEUTRAL",
  "unit": "string (seconds, MB, ops/sec)",
  "runs": "integer — number of measurement runs"
}
```

### 7.6 Change Scoring & Quality Assessment

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6.1 | System SHALL assign a composite quality score (0–100) to each proposal | P0 |
| FR-6.2 | Score SHALL be composed of weighted sub-scores: correctness (tests pass), readability (lint clean), risk (blast radius), and complexity reduction | P0 |
| FR-6.3 | System SHALL classify risk level: `low`, `medium`, `high`, `critical` based on number of files touched, test coverage of affected code, and change magnitude | P1 |
| FR-6.4 | System SHALL flag proposals that reduce test coverage | P1 |
| FR-6.5 | System SHALL provide a confidence score for the agent's own assessment (LLM self-evaluation) | P1 |

#### 7.6.1 Composite Score Formula

```
CompositeScore = (W_correctness × S_correctness)
              + (W_readability × S_readability)
              + (W_risk       × S_risk)
              + (W_complexity × S_complexity)

Where all sub-scores S are normalized to 0–100, and all weights W sum to 1.0.
```

**Default Weights:**

| Sub-Score | Weight | Rationale |
|-----------|--------|-----------|
| Correctness (`W_correctness`) | 0.40 | Highest priority: does the code still work? |
| Readability (`W_readability`) | 0.20 | Lint cleanliness and style conformance |
| Risk (`W_risk`) | 0.25 | Blast radius and change safety |
| Complexity Reduction (`W_complexity`) | 0.15 | Net improvement in code complexity |

Weights are configurable per-project in the project config file.

#### 7.6.2 Sub-Score Definitions

| Sub-Score | How Measured | Scoring |
|-----------|-------------|---------|
| **Correctness** | Evaluation pipeline results (compile + tests) | 100 = all pass, no regressions. −25 per new test failure. −50 if compile fails. 0 if tests cannot run. |
| **Readability** | Linter results (delta: new warnings/errors) | 100 = no new lint issues. −5 per new warning. −15 per new error. Bonus +10 if lint issues are resolved. |
| **Risk** | Blast radius analysis (see §7.6.3) | 100 = low risk. Penalized by files touched, dependency depth, test coverage of changed code. |
| **Complexity Reduction** | Cyclomatic complexity delta + function length delta | 100 = significant reduction. 50 = neutral. < 50 = complexity increased. |

#### 7.6.3 Risk Classification Matrix

Risk level is derived from three dimensions scored independently:

| Dimension | LOW (3 pts) | MEDIUM (2 pts) | HIGH (1 pt) | CRITICAL (0 pts) |
|-----------|------------|----------------|-------------|-------------------|
| **Files touched** | 1 file | 2–5 files | 6–10 files | >10 files |
| **Change magnitude** | <20 lines changed | 20–100 lines | 100–500 lines | >500 lines |
| **Test coverage of changed code** | >80% covered | 50–80% covered | 20–50% covered | <20% or unknown |

**Risk level mapping:**
- **LOW** (7–9 pts): Minimal review needed
- **MEDIUM** (4–6 pts): Standard review
- **HIGH** (2–3 pts): Careful review, consider staging
- **CRITICAL** (0–1 pts): Recommend human rewrite

Risk sub-score = `(total_points / 9) × 100`

#### 7.6.4 Complexity Metrics

Complexity reduction is measured using:

| Metric | Tool | How Computed |
|--------|------|-------------|
| **Cyclomatic complexity** | `radon` (Python) | Average CC per function, pre vs. post. Score = max(0, 100 − (delta_cc × 10)) |
| **Function length** | AST analysis | Average lines per function, pre vs. post. Penalty if average increases. |
| **Nesting depth** | AST analysis | Max nesting depth per function. Penalty for increased nesting. |
| **Cognitive complexity** | `radon` or custom | Measures how hard code is to understand (loops, conditionals, recursion). |

If complexity tools are unavailable, this sub-score defaults to 50 (neutral) and is excluded from the weighted calculation (weights redistributed proportionally).

#### 7.6.5 Score Calibration

| Strategy | Detail |
|----------|--------|
| **Calibration test suite** | A set of 20 known-good and 20 known-bad proposals (from the canonical test repo) with manually assigned target scores. The scoring algorithm is validated against these. |
| **Score distribution monitoring** | Track score distribution over time. If >80% of proposals score >90, weights may need tightening. If <20% pass 50, the agent or scoring is miscalibrated. |
| **Human override** | Reviewers can override the composite score when accepting/rejecting. Overrides are logged and feed back into calibration datasets. |
| **Minimum viable score** | Proposals scoring below 30 are auto-flagged as "not recommended" in the UI. Configurable threshold (default: 30). |

### 7.7 Auditable Diff & Explanation Generation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-7.1 | System SHALL generate a human-readable explanation for every proposed change | P0 |
| FR-7.2 | Explanation SHALL include: what changed, why, expected impact, and any risks | P0 |
| FR-7.3 | System SHALL provide a side-by-side or inline diff view in the Web UI | P1 |
| FR-7.4 | System SHALL provide syntax-highlighted diffs in the CLI | P0 |
| FR-7.5 | System SHALL persist all proposals, diffs, explanations, and scores for audit history | P0 |
| FR-7.6 | System SHALL support exporting proposals as Markdown reports | P1 |

### 7.8 CLI Interface

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.1 | CLI SHALL provide commands: `init`, `index`, `scan`, `review`, `propose`, `status`, `accept`, `reject`, `config`, `logs` | P0 |
| FR-8.2 | `init` — initialize configuration for a target repository | P0 |
| FR-8.3 | `index` — run the indexing pipeline on the target repo | P0 |
| FR-8.4 | `scan` — run a health scan and display detected issues | P0 |
| FR-8.5 | `propose` — instruct the agent to generate refactoring or bug-fix proposals | P0 |
| FR-8.6 | `review <pr-ref>` — analyze an existing pull request | P1 |
| FR-8.7 | `status` — show status of active proposals and running evaluations | P0 |
| FR-8.8 | `accept <proposal-id>` — merge a proposal's sandbox branch into the target branch | P0 |
| FR-8.9 | `reject <proposal-id>` — discard a proposal and clean up its sandbox branch | P0 |
| FR-8.10 | `config` — manage system configuration (LLM provider, model, temperature, evaluation profile, etc.) | P0 |
| FR-8.11 | `logs <proposal-id>` — view the agent's reasoning trace and audit log for a proposal | P0 |
| FR-8.12 | CLI SHALL use `click` or `typer` for argument parsing with help text and autocompletion | P1 |
| FR-8.13 | CLI SHALL support both interactive and non-interactive (CI-friendly) modes | P1 |

### 7.9 Web UI

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-9.1 | Web UI SHALL display a dashboard home with codebase health summary and recent proposals | P1 |
| FR-9.2 | Web UI SHALL display a list of all proposals with status, score, and timestamp | P1 |
| FR-9.3 | Web UI SHALL render syntax-highlighted diffs (side-by-side and inline modes) | P1 |
| FR-9.4 | Web UI SHALL display the agent's reasoning trace (tool calls, LLM responses) for transparency | P1 |
| FR-9.5 | Web UI SHALL allow accepting or rejecting proposals with optional reviewer comments | P1 |
| FR-9.6 | Web UI SHALL display evaluation pipeline results (pass/fail per step, logs, timing) | P1 |
| FR-9.7 | Web UI SHALL include a search/filter interface for proposals (by status, score, date, type) | P2 |
| FR-9.8 | Web UI SHALL be a server-rendered or SPA application (React, Svelte, or simple Jinja2 templates) | P1 |
| FR-9.9 | Web UI SHALL support dark mode and be responsive for mobile/tablet viewing | P2 |

#### 7.9.1 State Management & Real-Time Updates

**State Architecture:**

The Web UI uses a client-side state management pattern appropriate to the chosen framework:

| Framework | State Library | Server Communication |
|-----------|--------------|---------------------|
| React (Vite) | Zustand or React Query | REST API + WebSocket |
| Jinja2 + HTMX | Server-side (session state) | HTMX polling or SSE (Server-Sent Events) |

**Real-Time Update Channels:**

| Event | Delivery Method | Payload |
|-------|----------------|--------|
| Proposal status change (PENDING → EVALUATING → EVALUATED) | WebSocket / SSE | `{ proposal_id, new_status, timestamp }` |
| Evaluation step completion | WebSocket / SSE | `{ proposal_id, step, result, duration_ms }` |
| Agent iteration progress | WebSocket / SSE (throttled: max 1/sec) | `{ task_id, iteration, thought_summary }` |
| Indexing progress | WebSocket / SSE | `{ project_id, files_processed, total_files, percent }` |
| Health scan completion | WebSocket / SSE | `{ scan_id, health_score, issues_count }` |

WebSocket endpoint: `ws://host:port/ws/events?project_id=<id>`. The client subscribes to a project-scoped channel.

**Optimistic Updates:**

- When a user accepts/rejects a proposal, the UI immediately updates the status locally before the server responds (rollback on error).
- When submitting a new task, a placeholder card appears in the "Active Tasks" list immediately.

**Offline Handling:**

- If the WebSocket connection drops, the UI falls back to polling the REST API every 10 seconds.
- A "Connection lost — reconnecting..." banner is displayed; auto-hides on reconnect.
- No data is lost — all state is server-authoritative; the UI is a read-through view.

**Page-Specific State:**

| Page | Data Fetched | Refresh Strategy |
|------|-------------|------------------|
| Dashboard | Latest 10 proposals, health summary, cost summary | Real-time via WebSocket |
| Proposal Detail | Full proposal JSON, diff, evaluation results, audit trace | Fetched once, updated via WebSocket events |
| Proposal List | Paginated list with filters (status, type, score) | Paginated REST API, live status updates via WebSocket |
| Health Report | Last scan results, trend chart data | Fetched once; new scans push via WebSocket |
| Settings | Project config, user preferences | Fetched once; no real-time |

### 7.10 Prompt Engineering & LLM Interaction Design

#### 7.10.1 System Prompt Templates

Each agent task type uses a dedicated system prompt. All system prompts share a common preamble followed by task-specific instructions.

**Common Preamble (included in every system prompt):**

```
You are an expert software engineer acting as an automated code reviewer.
You have access to a codebase through retrieval tools and can read files,
search code, and query the AST. You MUST:

- Produce changes that are minimal, safe, and well-justified.
- Never modify files outside the designated sandbox branch.
- Always explain your reasoning before making changes.
- Output all proposals in the required JSON schema (see output format below).
- Stop and report if you are uncertain rather than guessing.

Repository: {repo_name}
Language: {primary_language}
Default Branch: {default_branch}
Current Commit: {head_sha}
```

**Task-specific system prompt extensions:**

| Task Type | System Prompt Focus | Key Instructions |
|-----------|-------------------|------------------|
| `REFACTOR` | Code quality improvement | "Identify code smells (duplication, excessive complexity, naming issues, dead code, long functions, inconsistent patterns). Propose the smallest diff that meaningfully improves readability or maintainability. Do NOT change external behavior." |
| `BUG_FIX` | Root cause analysis + fix | "Given the bug report or failing test below, localize the root cause by reading relevant code. Propose a fix that resolves the issue without introducing regressions. Explain the root cause, why the fix is correct, and what could break." |
| `REVIEW_PR` | Pull request critique | "Review the provided diff in context of the full codebase. Identify bugs, style issues, performance concerns, and missing edge cases. Produce inline comments keyed to file:line. Rate overall quality." |
| `HEALTH_SCAN` | Broad code health audit | "Scan the codebase for systemic issues: high-complexity functions (cyclomatic complexity >10), TODO/FIXME density, test coverage gaps, dependency staleness, code duplication clusters, and security anti-patterns. Produce a prioritized issue list, not diffs." |
| `EXPLAIN` | Code understanding | "Answer the user's question about the codebase using retrieved context. Cite specific files and line numbers. Do not propose changes unless explicitly asked." |

#### 7.10.2 Prompt Construction Pipeline

Every LLM call assembles its prompt through a 5-stage pipeline. Each stage has a **token budget** to ensure the total stays within the model's context window.

```
┌─────────────────────────────────────────────────────────┐
│              Prompt Construction Pipeline                │
│                                                         │
│  Stage 1: System Prompt         (~500 tokens, fixed)    │
│  ┌───────────────────────────────────────────────┐      │
│  │ Common preamble + task-specific instructions  │      │
│  └──────────────────────┬────────────────────────┘      │
│                         ▼                               │
│  Stage 2: Retrieved Context     (~60% of remaining)     │
│  ┌───────────────────────────────────────────────┐      │
│  │ Code chunks from vector search, ranked by     │      │
│  │ relevance. Each chunk includes file path,     │      │
│  │ line range, and surrounding context.           │      │
│  └──────────────────────┬────────────────────────┘      │
│                         ▼                               │
│  Stage 3: Structural Context    (~15% of remaining)     │
│  ┌───────────────────────────────────────────────┐      │
│  │ File tree summary, import graph for affected  │      │
│  │ modules, function signatures of callers/       │      │
│  │ callees (not full bodies).                     │      │
│  └──────────────────────┬────────────────────────┘      │
│                         ▼                               │
│  Stage 4: Conversation History  (~15% of remaining)     │
│  ┌───────────────────────────────────────────────┐      │
│  │ Previous ReAct iterations (thought + action   │      │
│  │ + observation), condensed if over budget.      │      │
│  └──────────────────────┬────────────────────────┘      │
│                         ▼                               │
│  Stage 5: Output Instructions   (~10% of remaining)     │
│  ┌───────────────────────────────────────────────┐      │
│  │ JSON schema definition, format constraints,   │      │
│  │ and few-shot example (if enabled).             │      │
│  └───────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

**Token Budget Allocation (for a 128K context model):**

| Stage | Budget | Notes |
|-------|--------|-------|
| System Prompt | 500 tokens (fixed) | Rarely changes |
| Retrieved Context | ~76K tokens | Largest portion; truncated by relevance rank |
| Structural Context | ~19K tokens | File tree, import graph, signatures |
| Conversation History | ~19K tokens | Prior ReAct steps; summarized if exceeds budget |
| Output Instructions + Few-shot | ~13K tokens | Schema + 1–2 examples |
| **Reserved for response** | Remaining (~4K–8K) | Model's generation space |

**Overflow handling:** When a stage exceeds its budget, content is truncated starting from the lowest-relevance items. Retrieved context chunks are dropped from the bottom of the ranked list. Conversation history is summarized (prior iterations compressed to one-line summaries) to fit budget.

#### 7.10.3 Structured Output Strategy

The agent must produce machine-parseable output. The system uses a two-layer approach:

1. **Constrained output format:** LLM is instructed to respond in JSON (using OpenAI's `response_format: { type: "json_object" }` or equivalent structured output mode when available).

2. **Post-processing validation:** Every LLM response passes through a Pydantic validator before being accepted. If validation fails:
   - **Attempt 1:** Re-prompt the LLM with the validation error and the original response, asking it to fix the output.
   - **Attempt 2:** If re-prompt fails, extract what can be salvaged (e.g., explanation text without a valid diff) and mark the proposal as `PARTIAL`.
   - **Attempt 3:** If all extraction fails, log the raw response to the audit trail and mark the task as `FAILED`.

**Response format per ReAct iteration:**

```json
{
  "thought": "string — the agent's reasoning for this step",
  "action": {
    "tool": "string — tool name (file_read | vector_search | ast_query | file_write | shell_exec | git_op | submit_proposal | give_up)",
    "args": { }
  }
}
```

**Final submission format** (when `action.tool == "submit_proposal"`):

```json
{
  "thought": "Final reasoning summary",
  "action": {
    "tool": "submit_proposal",
    "args": {
      "title": "string — short descriptive title",
      "task_type": "REFACTOR | BUG_FIX | REVIEW_PR",
      "files_changed": [
        {
          "path": "string — relative file path",
          "diff": "string — unified diff for this file",
          "change_type": "MODIFY | CREATE | DELETE"
        }
      ],
      "explanation": "string — multi-paragraph explanation (what, why, impact, risks)",
      "confidence": "number 0.0–1.0 — agent self-assessed confidence",
      "risk_assessment": "LOW | MEDIUM | HIGH | CRITICAL",
      "related_files": ["string — files that callers should also review but were not changed"]
    }
  }
}
```

#### 7.10.4 Few-Shot Example Strategy

| Approach | When Used | Rationale |
|----------|-----------|-----------|
| **Zero-shot** | Default for `REFACTOR` and `BUG_FIX` tasks | Saves token budget; strong models perform well zero-shot on code tasks |
| **One-shot** | `REVIEW_PR` task type | One example PR review calibrates tone, depth, and format expectations |
| **Dynamic few-shot** | When the agent fails validation on first attempt | Re-prompt includes a known-good example to guide format correction |
| **Retrieval-augmented few-shot** | Future enhancement (P2) | Retrieve examples similar to the current task from a curated examples database |

Few-shot examples are stored as JSON files in `config/prompts/examples/` and loaded at prompt construction time. They count against the Stage 5 token budget.

#### 7.10.5 Multi-Step ReAct Iteration Handoff

The ReAct loop manages state across iterations as follows:

```
Iteration 1:  System Prompt → Context → "Begin analysis"
                ↓
              LLM responds: { thought: "...", action: { tool: "vector_search", args: {...} } }
                ↓
              System executes tool, captures observation
                ↓
Iteration 2:  System Prompt → Context → [Iteration 1 thought+action+observation] → "Continue"
                ↓
              LLM responds: { thought: "...", action: { tool: "file_read", args: {...} } }
                ↓
              ... (repeat until submit_proposal or give_up or iteration limit)
```

**Key rules:**
- Each iteration appends `{ thought, action, observation }` to the conversation history.
- When history exceeds its token budget (Stage 4), the oldest iterations are **summarized** into a single block: `"Prior steps summary: searched for X, read file Y, found issue Z."` The most recent 3 iterations are always kept in full.
- The agent receives a `remaining_iterations` counter in each prompt so it can plan accordingly.
- If the agent emits `give_up` as its tool, the task is terminated gracefully with a `FAILED` status and the reasoning is preserved in the audit log.

### 7.11 Configuration Schema & Defaults

All system behavior is governed by a layered configuration system.

#### 7.11.1 Configuration Hierarchy

Settings are resolved in this order (later overrides earlier):

```
1. Built-in defaults (hardcoded)
     ↓ overridden by
2. Global config file:  ~/.config/code-reviewer/config.toml
     ↓ overridden by
3. Project config file: <repo_root>/.code-reviewer/config.toml
     ↓ overridden by
4. Environment variables: CODE_REVIEWER_<SECTION>_<KEY>  (e.g., CODE_REVIEWER_LLM_MODEL)
     ↓ overridden by
5. CLI flags:  --model, --temperature, etc.
```

#### 7.11.2 Config File Format (TOML)

```toml
# ─── LLM Provider ────────────────────────────────────
[llm]
provider = "openai"             # openai | anthropic | ollama | vllm
model = "gpt-4o"                # Model name
temperature = 0.2               # 0.0–1.0
max_tokens_per_response = 4096  # Max tokens per LLM response
api_base_url = ""               # Custom API base (for Ollama/vLLM)

[llm.budget]
max_tokens_per_task = 100000    # Total token budget per agent task
max_iterations_per_task = 15    # Max ReAct loop iterations
max_monthly_cost_usd = 50.0    # Monthly spending cap (cloud providers)

# ─── Embedding ────────────────────────────────────────
[embedding]
provider = "openai"             # openai | ollama
model = "text-embedding-3-small"
batch_size = 100                # Chunks per embedding API call

# ─── Vector Database ─────────────────────────────────
[vectordb]
backend = "chromadb"            # chromadb | qdrant
persist_directory = ".code-reviewer/vectordb"
collection_name = "codebase"
distance_metric = "cosine"

# ─── Indexing ─────────────────────────────────────────
[indexing]
min_chunk_tokens = 30
max_chunk_tokens = 1500
target_chunk_tokens = 800
max_file_tokens = 50000
context_lines = 3               # Lines of surrounding context per chunk
ignore_patterns = ["*.min.js", "*.generated.*", "vendor/", "node_modules/"]

# ─── Retrieval ────────────────────────────────────────
[retrieval]
top_k = 15                      # Max chunks to retrieve per query
similarity_threshold = 0.3      # Min cosine similarity to include
hybrid_search = true            # Enable keyword + vector hybrid
keyword_weight = 0.3            # Weight for keyword vs. vector (0–1)

# ─── Evaluation Pipeline ─────────────────────────────
[evaluation]
profile = "full"                # quick | full | custom
timeout_seconds = 600           # Per-step timeout
run_in_container = true         # Container isolation for eval steps

[evaluation.steps]
compile = true
test = true
lint = true
perf = false                    # Performance benchmarks (disabled by default)

[evaluation.lint]
tool = "ruff"                   # ruff | flake8 | pylint
config_file = ""                # Path to lint config (auto-detected if empty)

# ─── Scoring ──────────────────────────────────────────
[scoring]
weight_correctness = 0.40
weight_readability = 0.20
weight_risk = 0.25
weight_complexity = 0.15
minimum_viable_score = 30       # Proposals below this are flagged
auto_reject_below = 0           # 0 = disabled; set >0 to auto-reject

# ─── Git ──────────────────────────────────────────────
[git]
sandbox_branch_prefix = "ai-review"
sandbox_retention_days = 7
auto_push = false               # Push sandbox branches to remote
auth_method = "auto"            # auto | ssh | https_token | credential_helper

# ─── Server ──────────────────────────────────────────
[server]
host = "127.0.0.1"
port = 8000
cors_allowed_origins = ["http://localhost:3000"]
api_key = ""                    # Set via env var CODE_REVIEWER_SERVER_API_KEY

# ─── Logging ──────────────────────────────────────────
[logging]
level = "INFO"                  # DEBUG | INFO | WARNING | ERROR
format = "json"                 # json | text
file = ".code-reviewer/logs/code-reviewer.log"
max_file_size_mb = 50
backup_count = 5                # Number of rotated log files to keep
```

#### 7.11.3 Sensitive vs. Non-Sensitive Configuration

| Sensitive (env vars / secret manager only) | Non-Sensitive (config file OK) |
|--------------------------------------------|-------------------------------|
| `llm.api_key` → `CODE_REVIEWER_LLM_API_KEY` | `llm.model`, `llm.temperature` |
| `server.api_key` → `CODE_REVIEWER_SERVER_API_KEY` | `indexing.*`, `retrieval.*` |
| `git.auth_token` → `CODE_REVIEWER_GIT_TOKEN` | `scoring.*`, `evaluation.*` |
| Database credentials → `CODE_REVIEWER_DB_URL` | `logging.*`, `server.host/port` |

Sensitive values are NEVER read from config files. If present in a config file, the system logs a warning and ignores them.

### 7.12 Health Scan Definition

The `HEALTH_SCAN` task type (FR-3.7, UC-5) performs a systematic audit of codebase quality. This section specifies exactly what is checked and how results are structured.

#### 7.12.1 Health Check Categories

| Category | Checks Performed | Tool / Method |
|----------|-----------------|---------------|
| **Complexity** | Functions with cyclomatic complexity > 10; functions > 50 lines; nesting depth > 4 | `radon` (Python) + AST analysis |
| **Duplication** | Code clone detection: blocks of ≥ 6 similar lines across files | AST-based structural comparison or `jscpd` |
| **Dead Code** | Unused imports, unreachable functions, variables assigned but never read | AST analysis + cross-reference check |
| **TODO/FIXME Density** | Count and location of `TODO`, `FIXME`, `HACK`, `XXX` comments | Regex search |
| **Test Coverage Gaps** | Files and functions with no corresponding test file or <20% coverage | Coverage report parsing (if available) + heuristic matching |
| **Dependency Health** | Outdated packages, packages with known vulnerabilities | `pip-audit`, `safety`, `pip list --outdated` |
| **Naming Consistency** | Violations of naming conventions (snake_case for Python, camelCase for Java) | AST analysis + configurable naming rules |
| **Security Anti-Patterns** | Hardcoded secrets, `eval()` usage, SQL string concatenation, insecure file permissions | `semgrep` rules + regex patterns |
| **Documentation Gaps** | Public functions/classes without docstrings | AST analysis |

#### 7.12.2 Issue Severity Levels

| Severity | Definition | Example |
|----------|-----------|---------|
| **CRITICAL** | Security vulnerability or data-loss risk | Hardcoded API key, SQL injection, `eval()` on user input |
| **ERROR** | Bug-likely code or major quality issue | Dead code in critical path, cyclomatic complexity > 25, failing import |
| **WARNING** | Code smell that should be addressed | Duplicate code block, function > 100 lines, TODO older than 6 months |
| **INFO** | Minor improvement opportunity | Missing docstring, slightly inconsistent naming, minor lint violation |

#### 7.12.3 Health Report Schema

```json
{
  "scan_id": "uuid",
  "project_id": "uuid",
  "commit_sha": "string",
  "scanned_at": "ISO-8601 timestamp",
  "summary": {
    "total_issues": "integer",
    "by_severity": { "CRITICAL": 0, "ERROR": 0, "WARNING": 0, "INFO": 0 },
    "by_category": { "complexity": 0, "duplication": 0, "dead_code": 0, "...": 0 },
    "health_score": "integer 0–100 (higher = healthier)"
  },
  "issues": [
    {
      "id": "uuid",
      "category": "string",
      "severity": "CRITICAL | ERROR | WARNING | INFO",
      "file": "string — relative path",
      "line": "integer",
      "title": "string — short description",
      "description": "string — detailed explanation",
      "suggested_action": "string — what to do about it",
      "auto_fixable": "boolean — can the agent propose a fix?"
    }
  ],
  "trends": {
    "issues_delta": "integer — change vs. last scan (negative = improvement)",
    "health_score_delta": "integer",
    "new_issues": "integer",
    "resolved_issues": "integer"
  }
}
```

#### 7.12.4 Trend Tracking

- Each scan result is persisted in the metadata store with its commit SHA.
- The `trends` section compares the current scan to the most recent previous scan.
- The Web UI displays a **health score over time** chart (line graph, last 30 scans).
- CLI `scan --trend` shows a summary: `"Health: 72/100 (+3 since last scan, 5 new issues, 8 resolved)"`.

### 7.13 LLM Response Caching

To reduce costs and latency, the system caches LLM responses that are likely to be reused.

#### 7.13.1 Cache Key Design

```
cache_key = SHA-256(
    model_name
  + temperature
  + system_prompt_hash
  + user_prompt_content
  + retrieved_context_hashes[]   (sorted, to handle retrieval order variance)
)
```

The key is a pure function of the prompt contents — identical prompts always produce the same key, regardless of when they are sent.

#### 7.13.2 What Is Cached

| Cacheable | Not Cacheable |
|-----------|--------------|
| `EXPLAIN` task responses (codebase Q&A) | `REFACTOR` and `BUG_FIX` proposals (creative, non-deterministic) |
| Individual ReAct iterations (same tool call with same context) | Final `submit_proposal` actions (must be fresh) |
| Embedding API responses (same chunk text → same vector) | Health scan results (depend on current code state) |

#### 7.13.3 Storage & Eviction

| Parameter | Default | Configurable |
|-----------|---------|-------------|
| Cache backend | SQLite table `llm_cache` (local), Redis (production) | `[cache] backend = sqlite | redis` |
| TTL | 24 hours for LLM responses; 7 days for embeddings | `[cache] llm_ttl_hours`, `[cache] embedding_ttl_days` |
| Max cache size | 500 MB (local), 2 GB (Redis) | `[cache] max_size_mb` |
| Eviction policy | LRU (Least Recently Used) when max size exceeded | Not configurable |

#### 7.13.4 Invalidation Rules

| Trigger | Action |
|---------|--------|
| Codebase is re-indexed (files changed) | Invalidate all cached responses that referenced chunks from changed files |
| Configuration change (model, temperature) | Invalidate entire LLM response cache (new model = new responses) |
| Manual flush | `code-reviewer cache clear` — clears all caches |
| Embedding model change | Invalidate all embedding cache entries; triggers full re-embedding |

#### 7.13.5 Cache Bypass

Caching is automatically disabled for:
- Prompts with `temperature > 0.5` (high randomness makes caching pointless)
- The final iteration of any agent task (ensures fresh evaluation)
- Any request made with `--no-cache` CLI flag

---

## 8. Non-Functional Requirements

| ID | Requirement | Category | Priority |
|----|-------------|----------|----------|
| NFR-1 | Indexing 100K LOC repository SHALL complete in under 10 minutes | Performance | P1 |
| NFR-2 | Agent SHALL produce a proposal for a single issue in under 5 minutes (excluding evaluation) | Performance | P1 |
| NFR-3 | System SHALL be deployable as a single Docker Compose stack or local Python install | Deployment | P0 |
| NFR-4 | System SHALL support concurrent evaluation of up to 5 proposals | Scalability | P2 |
| NFR-5 | All LLM API keys and credentials SHALL be stored securely (env vars or secret manager, never in code) | Security | P0 |
| NFR-6 | Agent file operations SHALL be sandboxed to the repo directory only | Security | P0 |
| NFR-7 | System SHALL support Python 3.10+ | Compatibility | P0 |
| NFR-8 | System SHALL provide structured JSON logging with configurable log levels | Observability | P1 |
| NFR-9 | System SHALL be usable offline with a local LLM (Ollama) and local vector DB (ChromaDB) | Availability | P2 |
| NFR-10 | Codebase data SHALL never be sent to external services unless the user explicitly configures an external LLM provider | Privacy | P0 |
| NFR-11 | All REST API endpoints SHALL respond within 500ms (excluding long-running tasks, which use async jobs) | Performance | P1 |
| NFR-12 | System SHALL handle repositories with up to 500K LOC without OOM or crash | Reliability | P1 |

### 8.3 Repository Size Guardrails

To support NFR-12 and prevent resource exhaustion, the system enforces limits at multiple stages:

#### Pre-Indexing Validation

| Check | Threshold | Action on Exceed |
|-------|-----------|------------------|
| Total file count | 50,000 files (after `.gitignore` + `.reviewerignore` filtering) | Warning: "Large repository detected ({count} files). Indexing may take >10 minutes." Proceed unless over hard limit (200,000 files → reject with suggestion to use `--include` paths). |
| Total LOC | 500,000 lines (after filtering) | Warning only; no hard reject. Logged for performance monitoring. |
| Single file size | 50,000 tokens (~5,000 lines) | Skip file (see §7.1.1 Large File Handling). Log warning. |
| Binary files | Any file detected as binary (via `file` command or extension list) | Auto-skip. Not indexed. List available in `.code-reviewer/skipped_files.log`. |
| Symlink depth | Max 5 levels of symlink resolution | Stop following at depth 5. Log warning. |

#### Runtime Memory Budget

| Component | Memory Limit | Enforcement |
|-----------|-------------|-------------|
| Indexing worker | 2 GB (configurable) | `resource.setrlimit(RLIMIT_AS, ...)` or Docker `--memory` flag |
| Agent task | 1 GB | Same mechanism |
| Evaluation container | 4 GB | Docker `--memory` flag on eval container |
| Vector DB | Bounded by disk (ChromaDB) or container memory (Qdrant) | Configured in vector DB settings |

#### Repository Complexity Estimates

Before starting a task, the system computes a rough cost estimate:

```
estimated_chunks = total_files × avg_chunks_per_file  (from index metadata)
estimated_tokens = estimated_chunks × target_chunk_tokens
estimated_cost   = (estimated_tokens / 1000) × price_per_1k_tokens

Display to user:
  "This repository has ~{estimated_chunks} chunks ({estimated_tokens} tokens).
   Estimated cost per full-context proposal: ~${estimated_cost:.2f}"
```

This estimate is shown on `code-reviewer index` and `code-reviewer propose` to set cost expectations.

### 8.1 Concurrency & Conflict Management

When multiple proposals are in flight simultaneously, the system must prevent conflicts:

**Task Scheduling:**

| Policy | Detail |
|--------|--------|
| Task queue | All agent and evaluation tasks go through a FIFO queue (Celery/RQ). Max concurrent agent tasks: 1 (serial LLM access). Max concurrent evaluations: 5 (configurable via `NFR-4`). |
| Priority levels | `HIGH` (user-initiated), `NORMAL` (scheduled), `LOW` (background scans). Higher priority tasks preempt lower ones in the queue. |
| Task deduplication | If a task with identical parameters (same task type + same target files) is already queued or running, the new submission is rejected with a reference to the existing task. |

**File-Level Conflict Detection:**

```
Before an agent begins work:
  1. Query all PENDING/EVALUATING proposals for their affected file list
  2. If the new task's target scope overlaps with an existing proposal's files:
     a. If the existing proposal is EVALUATING → queue the new task (wait for completion)
     b. If the existing proposal is PENDING → allow both (they'll be on separate branches)
  3. At diff application time: if the base branch has moved since the proposal was created,
     rebase the sandbox branch and re-validate the diff
```

**Git Operation Locking:**

| Operation | Lock Scope | Lock Type |
|-----------|-----------|-----------|
| Branch create/delete | Repo-level | Mutex (one at a time) |
| `git apply` | Branch-level | Exclusive (per sandbox branch) |
| Index (re-index) | Repo-level | Exclusive (blocks new proposals until complete) |
| Read operations (diff, log, show) | None | No locking needed |

Locks are implemented via file-based locks (`.code-reviewer/locks/`) for local mode, or Redis-based distributed locks for multi-worker deployments.

**Branch Naming:** Branch names use `ai-review/<uuid4>` format (e.g., `ai-review/a1b2c3d4-5678-...`), guaranteeing uniqueness without collision checks.

### 8.2 Monitoring & Observability

Beyond structured JSON logging (NFR-8), the system provides runtime metrics, cost tracking, and alerting.

#### 8.2.1 Log Management

| Policy | Detail |
|--------|--------|
| Rotation | Rotate log files when they exceed 50 MB (configurable). Keep last 5 rotated files. |
| Retention | Logs older than 30 days are automatically deleted. Audit trail logs are retained indefinitely (separate from application logs). |
| Format | JSON lines (one JSON object per line) for machine parsing. Human-readable `text` format available via config. |
| Levels | `DEBUG` (development only), `INFO` (default), `WARNING`, `ERROR`. Agent reasoning traces logged at `DEBUG`. |

#### 8.2.2 Application Metrics

The API server exposes a Prometheus-compatible `/metrics` endpoint with the following gauges and counters:

| Metric | Type | Description |
|--------|------|-------------|
| `code_reviewer_proposals_total` | Counter | Total proposals by status (labels: `status`, `task_type`) |
| `code_reviewer_proposals_active` | Gauge | Currently in-progress proposals |
| `code_reviewer_evaluation_duration_seconds` | Histogram | Evaluation pipeline duration (labels: `step`, `result`) |
| `code_reviewer_agent_iterations_total` | Counter | Total ReAct loop iterations |
| `code_reviewer_llm_tokens_total` | Counter | Total LLM tokens consumed (labels: `provider`, `direction=[input|output]`) |
| `code_reviewer_llm_requests_total` | Counter | Total LLM API calls (labels: `provider`, `status=[success|error]`) |
| `code_reviewer_llm_latency_seconds` | Histogram | LLM response latency |
| `code_reviewer_index_chunks_total` | Gauge | Total chunks in the vector DB per project |
| `code_reviewer_task_queue_depth` | Gauge | Number of tasks waiting in the queue |

#### 8.2.3 LLM Cost Tracking

| Feature | Detail |
|---------|--------|
| Per-task cost | Each proposal records `tokens_used` (input + output) and estimated cost based on provider pricing table. |
| Daily/monthly rollup | Aggregated in the metadata DB. Queryable via `code-reviewer costs --period month`. |
| Budget alerting | Warning at 80% of `max_monthly_cost_usd`. Hard stop at 100%. |
| Cost dashboard | Web UI displays a cost-over-time chart grouped by task type. |
| Provider pricing | Configurable pricing table in `config.toml` under `[llm.pricing]` (default: OpenAI public rates, updated per release). |

#### 8.2.4 Alerting

For self-hosted deployments, the system supports basic alerting:

| Trigger | Default Threshold | Notification |
|---------|-------------------|-------------|
| Evaluation pipeline failure rate | >20% failures in last 10 runs | Log `ERROR` + optional webhook |
| LLM cost approaching budget | >80% of monthly cap | Log `WARNING` + optional webhook |
| Vector DB unreachable | 3 consecutive health check failures | Log `ERROR` + optional webhook |
| Task queue depth | >20 pending tasks | Log `WARNING` |
| Disk space low | <1 GB free on data directory | Log `ERROR` |

Webhook URL is configured via `[alerting] webhook_url` in `config.toml`. Supports Slack-compatible JSON payloads.

---

## 9. Tech Stack

### 9.1 Core Language & Frameworks

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Primary Language | **Python 3.11+** | Rich LLM/ML ecosystem, fast prototyping |
| CLI Framework | **Typer** + **Rich** | Modern CLI with colors, tables, progress bars |
| API Server | **FastAPI** | Async, auto-docs (OpenAPI), type-safe |
| Web UI | **React** (Vite) or **Jinja2 + HTMX** | React for rich SPA; Jinja2+HTMX for simpler server-rendered option |
| Task Queue | **Celery** + **Redis** or **RQ** | Background evaluation and agent tasks |

### 9.2 AI & ML

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| LLM Provider (cloud) | **OpenAI API** (GPT-4o) | Best reasoning for code tasks |
| LLM Provider (local) | **Ollama** / **vLLM** with open-weight models (CodeLlama, DeepSeek-Coder, Qwen2.5-Coder) | Offline/privacy-first option |
| LLM Abstraction | **LiteLLM** or custom adapter | Unified interface across providers |
| Embeddings | **OpenAI `text-embedding-3-small`** or **`nomic-embed-text`** (local via Ollama) | High quality code embeddings |
| Agent Framework | **Custom ReAct loop** (not LangChain — keep it lightweight) | Full control, minimal dependencies |

### 9.3 Data & Storage

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Vector Database | **ChromaDB** (local) / **Qdrant** (production) | Lightweight local dev, scalable production |
| Metadata Store | **SQLite** (local) / **PostgreSQL** (production) | Simple, portable, upgradable |
| Cache | **Redis** (optional) | LLM response caching, task queue backend |

### 9.4 Code Analysis

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| AST Parsing | **tree-sitter** (`py-tree-sitter`) | Multi-language AST parsing, fast, reliable |
| Linting | **Ruff** (Python) | Extremely fast, replaces flake8+isort+black |
| Static Analysis | **Semgrep** (optional) | Pattern-based static analysis for security/bug detection |
| Type Checking | **mypy** (optional) | Catch type errors in Python projects |

### 9.5 Infrastructure

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Version Control | **GitPython** + subprocess | Programmatic Git operations |
| Containerization | **Docker** + **Docker Compose** | Reproducible deployment |
| CI/CD | **GitHub Actions** (self-hosted runner) or generic runner | Pipeline execution |
| Process Isolation | **Docker containers** or **Python `subprocess`** with cgroups | Sandbox evaluation |

---

## 10. Data Model & Schema

### 10.1 Core Entities

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│     Project      │       │     Proposal      │       │   Evaluation     │
├──────────────────┤       ├──────────────────┤       ├──────────────────┤
│ id (UUID)        │       │ id (UUID)        │       │ id (UUID)        │
│ name             │1    N │ project_id (FK)  │1    N │ proposal_id (FK) │
│ repo_url         │◄──────│ task_type        │◄──────│ step_name        │
│ repo_local_path  │       │ status           │       │ status           │
│ default_branch   │       │ sandbox_branch   │       │ passed           │
│ language         │       │ diff_unified     │       │ output_log       │
│ index_status     │       │ explanation      │       │ duration_ms      │
│ last_indexed_at  │       │ score_total      │       │ created_at       │
│ config (JSON)    │       │ score_breakdown  │       └──────────────────┘
│ created_at       │       │ risk_level       │
│ updated_at       │       │ llm_model_used   │       ┌──────────────────┐
└──────────────────┘       │ tokens_used      │       │   AuditLogEntry  │
                           │ created_at       │       ├──────────────────┤
                           │ updated_at       │       │ id (UUID)        │
                           └──────────────────┘       │ proposal_id (FK) │
                                                      │ timestamp        │
┌──────────────────┐                                  │ event_type       │
│   CodeChunk      │                                  │ tool_name        │
├──────────────────┤                                  │ input_data       │
│ id (UUID)        │                                  │ output_data      │
│ project_id (FK)  │                                  │ llm_prompt       │
│ file_path        │                                  │ llm_response     │
│ language         │                                  │ token_count      │
│ chunk_type       │                                  └──────────────────┘
│ name             │
│ start_line       │
│ end_line         │
│ content          │
│ embedding_id     │
│ metadata (JSON)  │
│ last_modified    │
└──────────────────┘
```

### 10.2 Status Enums

```
ProposalStatus:  PENDING → EVALUATING → EVALUATED → ACCEPTED → REJECTED → EXPIRED

EvaluationStep:  COMPILE | TEST | LINT | PERF

EvaluationStatus:  RUNNING → PASSED | FAILED | TIMEOUT | SKIPPED

TaskType:  REFACTOR | BUG_FIX | REVIEW_PR | HEALTH_SCAN | EXPLAIN

RiskLevel:  LOW | MEDIUM | HIGH | CRITICAL
```

### 10.3 Agent Proposal Schema

The formal schema for agent-produced proposals. All agent output is validated against this schema before persistence. This definition corresponds to the `submit_proposal` output described in §7.10.3.

#### 10.3.1 Full Proposal Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AgentProposal",
  "version": "1.0.0",
  "type": "object",
  "required": ["title", "task_type", "files_changed", "explanation", "confidence", "risk_assessment"],
  "properties": {
    "title": {
      "type": "string",
      "minLength": 10,
      "maxLength": 120,
      "description": "Short descriptive title for the proposal"
    },
    "task_type": {
      "type": "string",
      "enum": ["REFACTOR", "BUG_FIX", "REVIEW_PR"]
    },
    "files_changed": {
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {
        "type": "object",
        "required": ["path", "diff", "change_type"],
        "properties": {
          "path": {
            "type": "string",
            "pattern": "^[^/].*",
            "description": "Relative path from repo root (no leading slash)"
          },
          "diff": {
            "type": "string",
            "minLength": 1,
            "description": "Unified diff format (output of 'diff -u')"
          },
          "change_type": {
            "type": "string",
            "enum": ["MODIFY", "CREATE", "DELETE"]
          },
          "summary": {
            "type": "string",
            "description": "Optional one-line summary of what changed in this file"
          }
        }
      }
    },
    "explanation": {
      "type": "string",
      "minLength": 50,
      "description": "Multi-paragraph explanation: what changed, why, expected impact, and risks"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Agent self-assessed confidence in the correctness of this proposal"
    },
    "risk_assessment": {
      "type": "string",
      "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },
    "related_files": {
      "type": "array",
      "items": { "type": "string" },
      "default": [],
      "description": "Files not changed but relevant for reviewer context"
    },
    "breaking_changes": {
      "type": "boolean",
      "default": false,
      "description": "Whether this change may break existing public APIs or contracts"
    },
    "test_impact": {
      "type": "string",
      "enum": ["NONE", "EXISTING_TESTS_AFFECTED", "NEW_TESTS_NEEDED", "TESTS_REMOVED"],
      "default": "NONE",
      "description": "Expected impact on the test suite"
    }
  }
}
```

#### 10.3.2 Validation Rules

| Rule | Enforcement | On Failure |
|------|-------------|------------|
| All `required` fields present | Pydantic model validation | Re-prompt LLM (see §7.10.3 retry chain) |
| `title` length 10–120 chars | Schema constraint | Re-prompt with specific error |
| `explanation` length ≥ 50 chars | Schema constraint | Re-prompt; trivially short explanations are rejected |
| `files_changed` has 1–20 items | Schema constraint | >20 files suggests scope creep; agent is asked to split |
| Each `diff` is valid unified diff format | Custom parser validation (`unidiff` library) | Re-prompt with diff format instructions + example |
| Each `path` is a valid relative path within repo | Path validation against repo file list | Re-prompt with corrected path list |
| No duplicate `path` entries in `files_changed` | Pydantic validator | Merge or re-prompt |
| `diff` applies cleanly via `git apply --check` | Dry-run application | Agent is re-prompted with the apply error and asked to regenerate the diff |
| `confidence` matches risk heuristic (low confidence + LOW risk = warning) | Post-validation consistency check | Logged as warning, not blocking |

#### 10.3.3 Partial & Error Response Schemas

When the agent cannot produce a complete proposal, a fallback schema is used:

**Partial Proposal** (status: `PARTIAL`):

```json
{
  "title": "string (may be auto-generated)",
  "task_type": "string",
  "status": "PARTIAL",
  "explanation": "string — whatever analysis the agent completed",
  "partial_reason": "DIFF_VALIDATION_FAILED | CONTEXT_INSUFFICIENT | TOKEN_BUDGET_EXCEEDED | LLM_FORMAT_ERROR",
  "raw_llm_response": "string — the unprocessed LLM output for debugging",
  "files_changed": [],
  "confidence": 0.0
}
```

**Failed Task** (status: `FAILED`):

```json
{
  "task_type": "string",
  "status": "FAILED",
  "failure_reason": "MAX_ITERATIONS_REACHED | TOKEN_BUDGET_EXHAUSTED | LLM_ERROR_UNRECOVERABLE | AGENT_GAVE_UP | SANDBOX_ERROR",
  "error_message": "string — human-readable description of what went wrong",
  "reasoning_trace": "string — condensed summary of the agent's work before failure",
  "iterations_completed": "integer",
  "tokens_used": "integer"
}
```

#### 10.3.4 PR Review Schema (REVIEW_PR variant)

`REVIEW_PR` tasks use a different output since they produce comments, not diffs:

```json
{
  "title": "string — review title",
  "task_type": "REVIEW_PR",
  "overall_assessment": "APPROVE | REQUEST_CHANGES | COMMENT",
  "summary": "string — high-level review summary",
  "inline_comments": [
    {
      "file": "string — relative path",
      "line": "integer — line number in the diff",
      "severity": "CRITICAL | WARNING | SUGGESTION | NITPICK",
      "comment": "string — the review comment",
      "suggested_fix": "string | null — optional code suggestion"
    }
  ],
  "quality_score": "integer 0–100",
  "confidence": "number 0.0–1.0"
}
```

#### 10.3.5 Schema Versioning

| Policy | Detail |
|--------|--------|
| Version format | Semantic versioning (`major.minor.patch`) |
| Current version | `1.0.0` |
| Version stored with each proposal | `schema_version` field added to persisted proposals in the metadata DB |
| Backward compatibility | Minor/patch versions are backward-compatible; major bumps may require migration |
| Migration script | `code-reviewer migrate-schema` CLI command applies schema upgrades to historical proposals |
| Schema location | `src/schemas/proposal_v1.json` and Pydantic model in `src/schemas/proposal.py` |

---

## 11. API Design

### 11.1 REST API Endpoints

#### Projects
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/projects` | Register a new project (repo) |
| `GET` | `/api/v1/projects` | List all projects |
| `GET` | `/api/v1/projects/{id}` | Get project details |
| `PUT` | `/api/v1/projects/{id}` | Update project config |
| `DELETE` | `/api/v1/projects/{id}` | Remove project |

#### Indexing
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/projects/{id}/index` | Trigger indexing (async job) |
| `GET` | `/api/v1/projects/{id}/index/status` | Get indexing status |

#### Proposals
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/projects/{id}/proposals` | Request agent to generate proposals |
| `GET` | `/api/v1/projects/{id}/proposals` | List proposals (with filters) |
| `GET` | `/api/v1/proposals/{id}` | Get proposal details (diff, explanation, score) |
| `POST` | `/api/v1/proposals/{id}/accept` | Accept and merge proposal |
| `POST` | `/api/v1/proposals/{id}/reject` | Reject proposal |
| `GET` | `/api/v1/proposals/{id}/evaluation` | Get evaluation results |
| `GET` | `/api/v1/proposals/{id}/audit-log` | Get agent audit trail |

#### Search & Query
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/projects/{id}/query` | Natural language query against codebase |
| `POST` | `/api/v1/projects/{id}/search` | Semantic code search |

#### System
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | System health check |
| `GET` | `/api/v1/config` | Get system configuration |
| `PUT` | `/api/v1/config` | Update system configuration |

### 11.2 WebSocket Endpoints

| Path | Description |
|------|-------------|
| `ws://host/ws/proposals/{id}/stream` | Real-time agent reasoning stream (tool calls, thoughts) |
| `ws://host/ws/evaluation/{id}/stream` | Real-time evaluation pipeline output |

---

## 12. Integration Points

### 12.1 Git Integration
- Clone repos via HTTPS or SSH.
- Create, checkout, push, and delete branches programmatically.
- Generate diffs using `git diff`.
- Read commit history for change context.

#### 12.1.1 Authentication for Private Repositories

The system supports multiple Git authentication methods, configured via `[git] auth_method` in the config file:

| Method | Config Value | How It Works |
|--------|-------------|--------------|
| **Auto-detect** | `auto` (default) | Uses the system's existing Git credential configuration (SSH agent, credential helper, etc.). No additional setup required. |
| **SSH key** | `ssh` | Uses SSH key at the path specified by `CODE_REVIEWER_GIT_SSH_KEY` env var (default: `~/.ssh/id_rsa`). Supports passphrase-protected keys via SSH agent. |
| **HTTPS personal access token** | `https_token` | Uses a personal access token from env var `CODE_REVIEWER_GIT_TOKEN`. Injected into clone URLs as `https://<token>@github.com/...`. Token is never logged or persisted. |
| **Git credential helper** | `credential_helper` | Delegates to the system's configured `git credential-helper` (e.g., macOS Keychain, `git-credential-store`). |

**GitHub API Authentication (for PR review integration):**

| Feature | Auth Required | Configuration |
|---------|--------------|---------------|
| Read public repos | None | — |
| Read private repos | Personal access token (PAT) or GitHub App token | `CODE_REVIEWER_GITHUB_TOKEN` env var |
| Post PR comments | PAT with `repo` scope, or GitHub App with `pull_requests: write` | Same env var |
| Create check runs | GitHub App with `checks: write` | GitHub App ID + private key via env vars |

**Security Rules:**
- Git credentials are never written to log files, audit trails, or config files.
- Clone URLs with embedded tokens are sanitized before logging.
- SSH keys with passphrases are supported only via SSH agent (passphrase is never handled by the system directly).

### 12.2 LLM Provider Integration
- Abstracted behind a unified `LLMClient` interface.
- Provider-specific adapters: OpenAI, Anthropic, Ollama (local), vLLM (local).
- Configuration: model name, temperature, max tokens, retry policy.
- Token counting and budget enforcement.

### 12.3 CI/CD Integration
- **GitHub Actions:** Trigger the reviewer as a workflow step; post results as PR comments via GitHub API.
- **Generic CI:** Expose a CLI command (`code-reviewer review --pr <ref>`) that can be invoked from any CI system.
- **Webhook:** HTTP endpoint to receive PR events and trigger reviews automatically.

### 12.4 Notification Integration (Future)
- Slack webhook for proposal notifications.
- Email digest for periodic health scan reports.

---

## 13. Security Considerations

| Area | Measure |
|------|---------|
| **API Keys** | Stored in environment variables or `.env` file (never committed). Support for external secret managers (AWS Secrets Manager, HashiCorp Vault) in production. |
| **Secret Rotation** | API keys and LLM provider credentials rotated every 90 days. Integrate secret scanning (e.g., `trufflehog`, GitHub secret scanning) into CI to detect leaked credentials in commits. |
| **Sandbox Isolation** | Agent file operations are restricted to the sandbox branch directory. Shell commands run inside Docker containers with no network access (unless configured). |
| **Input Validation** | All API inputs validated with Pydantic models. Path traversal prevention on file operations. Parameterized queries for all database operations to prevent injection. |
| **Code Execution** | Evaluation pipeline runs in isolated containers with resource limits (CPU, memory, time). No arbitrary code execution from LLM output. |
| **Data Privacy** | Code is never sent to external LLM providers unless the user explicitly configures a cloud LLM. Local LLM option is fully air-gapped. |
| **Authentication** | Web UI and API protected by API key authentication (MVP). OAuth2/OIDC support planned for multi-user deployment. |
| **Session & Token Expiration** | JWT tokens for Web UI sessions include expiration (`exp` claim). Implement refresh token rotation so that stolen tokens have a limited lifespan. Configurable session timeout (default: 24 hours). |
| **Rate Limiting** | All public API endpoints protected with rate limiting (e.g., via `slowapi` or middleware) to prevent abuse, bot spam, and cost spikes. Configurable per-endpoint limits (default: 60 requests/min). |
| **CORS Configuration** | API CORS policy restricted to the production Web UI domain. No wildcard (`*`) origins in production. Development mode may allow `localhost` origins only. |
| **Error Detail Hiding** | API returns generic error messages to clients (e.g., "Internal server error"). Full stack traces, file paths, and debug details are logged server-side only, never exposed in responses. |
| **AI Cost Caps** | Hard spending limits configured in LLM provider dashboards. Per-task token budgets enforced in code (see FR-3.5). Per-user or per-project daily/monthly request limits to prevent runaway costs. |
| **Webhook Signature Verification** | Incoming CI/CD webhooks (e.g., GitHub PR events) verified using HMAC signature validation to ensure authenticity. Reject unsigned or invalid webhook payloads. |
| **Environment Separation** | Distinct database instances, API keys, and LLM provider credentials for development, staging, and production environments. No shared secrets across environments. |
| **Audit Trail** | Every agent action, LLM call, and file modification is logged immutably. |
| **Dependency Security** | Dependencies pinned in `requirements.txt` / `pyproject.toml`. Regular vulnerability scanning with `pip-audit` or `safety`. |

---

## 14. Error Handling & Recovery Strategy

This section defines how the system handles failures across every component. The goal is to ensure no failure mode results in silent data corruption, orphaned resources, or unrecoverable state.

### 14.1 Error Classification

All errors are categorized into one of four classes, each with a default response:

| Class | Description | Default Response | Example |
|-------|-------------|-----------------|---------|
| **Transient** | Temporary failures likely to resolve on retry | Automatic retry with exponential backoff (max 3 attempts, base 2s) | LLM rate limit (429), network timeout, temporary disk I/O error |
| **Recoverable** | Failures that require corrective action but can proceed | Execute recovery procedure, then continue | Diff fails to apply, AST parse fails for one file, LLM returns malformed JSON |
| **Fatal (task)** | Failures that terminate the current task but don't affect the system | Mark task as FAILED, log fully, clean up resources | Token budget exhausted, max iterations reached, sandbox branch conflict |
| **Fatal (system)** | Failures that threaten system integrity | Halt affected subsystem, alert operator, refuse new tasks until resolved | Database corruption, vector DB unreachable, disk full |

### 14.2 Indexing Pipeline Failures

| Failure | Recovery | State Handling |
|---------|----------|---------------|
| **Single file parse error** (tree-sitter fails) | Skip file, log warning, fall back to line-based chunking for that file. Continue indexing remaining files. | File marked as `parse_failed` in metadata; excluded from AST-based queries but included in text search |
| **Embedding API error** (timeout, rate limit) | Retry with backoff (transient). After 3 failures, skip the chunk and continue. | Unembed chunks tracked in a `pending_embeddings` queue for later retry |
| **Indexing crashes mid-way** (OOM, process killed) | On restart, detect incomplete index via `index_status = IN_PROGRESS` flag. Resume from last successfully indexed file (checkpoint-based). | Checkpoint file stored at `.code-reviewer/index_checkpoint.json` with last processed file path and chunk count |
| **Vector DB write failure** | Retry (transient). After 3 failures, halt indexing and report. | No partial writes — embeddings are batch-committed (per-file granularity). Failed batch can be replayed. |
| **Disk full** | Halt indexing, report available space vs. estimated need. | Index marked as `FAILED` with a descriptive error |

**Resume command:** `code-reviewer index --resume` picks up from the last checkpoint.

### 14.3 Sandbox Branch Failures

| Failure | Recovery | State Handling |
|---------|----------|---------------|
| **Branch creation fails** (name conflict) | Append a random suffix to branch name and retry once. If still fails, mark task as FAILED. | No orphaned branches — branch is only created after name validation |
| **Diff application fails** (`git apply` returns non-zero) | Return the error to the agent with the failing hunk. Agent is given 2 additional iterations to produce a corrected diff. | Sandbox branch is reset to its clean state (`git reset --hard`) before each retry |
| **Partial multi-file diff failure** (files 1–2 apply, file 3 fails) | **Atomic rollback:** reset entire sandbox branch to pre-diff state. Report which file(s) failed. Agent retries the full diff. | Diffs are applied in a transaction: `git stash` before apply, `git stash pop` on failure. Alternatively, apply to a temp worktree first. |
| **Repo in dirty state** (uncommitted changes, merge conflicts) | Refuse to create sandbox. Report: "Repository has uncommitted changes. Please commit or stash before running." | Agent never modifies a dirty repo |
| **Branch cleanup fails** (network error when deleting remote branch) | Retry in background. Add to cleanup queue. Alert on next startup if stale branches exist. | `code-reviewer cleanup` command lists and removes stale `ai-review/*` branches |

### 14.4 Evaluation Pipeline Failures

| Failure | Recovery | State Handling |
|---------|----------|---------------|
| **Build/compile fails** | Record as `FAILED` evaluation step. Continue to lint step (lint may still provide value). Do NOT run tests. | Proposal score penalized heavily; compile failure is a blocking issue |
| **Test suite timeout** (exceeds configured limit) | Kill test process. Record as `TIMEOUT`. | Step result includes partial output (last 500 lines of stdout/stderr) |
| **Test suite crashes** (segfault, OOM) | Record as `FAILED`. Capture exit code and signal. | Distinguish from test assertion failures — crash = infrastructure issue, not code issue |
| **Lint tool not found** (e.g., `ruff` not installed in evaluation environment) | Record as `SKIPPED` with reason. Warn user in report. | Non-blocking; proposal can proceed without lint score |
| **Pre-existing test failures** (tests that fail before the agent's change) | Run tests on the **base branch first** to establish a baseline. Only failures **introduced by the diff** are counted against the proposal. | Baseline results cached per commit SHA. Delta = `(post_failures - pre_failures)` |
| **Evaluation container fails to start** | Retry once. If Docker/container runtime is unavailable, fall back to running evaluation in a subprocess with resource limits (`ulimit`). | Recorded as `DEGRADED_MODE` in evaluation metadata |

### 14.5 Agent Orchestration Failures

| Failure | Recovery | State Handling |
|---------|----------|---------------|
| **LLM returns malformed JSON** | Re-prompt with validation error + the raw response (see §7.10.3 retry chain). Up to 3 attempts. | Each attempt logged to audit trail with the raw response and error |
| **LLM returns empty response** | Retry once (transient). If persists, mark as LLM_ERROR_UNRECOVERABLE. | FAILED task with `failure_reason: LLM_ERROR_UNRECOVERABLE` |
| **LLM API key invalid/expired** | Halt immediately. Do not retry. Surface error: "LLM API key is invalid. Run `code-reviewer config` to update." | Task marked FAILED; no further LLM calls until config is updated |
| **Token budget exhausted mid-task** | Agent is given one final iteration with a forced instruction: "You are out of budget. Submit your best proposal now or give up." | If agent submits, proposal proceeds. If not, FAILED with `TOKEN_BUDGET_EXHAUSTED`. |
| **Max iterations reached** | Same as token budget — one final "submit or give up" iteration. | FAILED with `MAX_ITERATIONS_REACHED` if agent doesn't submit |
| **Tool execution error** (vector search returns error, file not found) | Error is returned as the tool's observation. Agent decides how to proceed (retry with different args, try a different tool, or give up). | Tool errors are part of the normal ReAct loop — the agent is expected to reason about them |

### 14.6 Graceful Degradation Matrix

When external services become unavailable, the system degrades rather than failing completely:

| Service Down | Impact | Degraded Behavior | User Notification |
|-------------|--------|-------------------|-------------------|
| **LLM provider API** | Cannot generate proposals | Queue incoming tasks. Retry every 60s. CLI shows "LLM provider unavailable — tasks queued." | Warning banner in Web UI; CLI status message |
| **Vector DB** | Cannot perform semantic search | Fall back to keyword/grep-based search (reduced quality). Mark retrieval as `DEGRADED`. | "Operating in degraded mode: semantic search unavailable" |
| **Redis** (task queue) | Cannot dispatch background tasks | Fall back to synchronous in-process execution (blocking, single-task). | "Background workers unavailable. Tasks will run synchronously." |
| **Metadata DB** (SQLite/Postgres) | Cannot persist proposals or state | Halt all operations. This is a Fatal (system) error. | "Database unreachable. System halted." |
| **Git remote** | Cannot push sandbox branches | Operate in local-only mode. Proposals stored locally. Push deferred. | "Remote unavailable. Proposals saved locally." |

### 14.7 Dead Letter Queue & Task Recovery

Failed tasks are persisted for inspection and retry:

```
┌──────────────────────────────────────────────────┐
│                Dead Letter Queue                  │
├──────────────────────────────────────────────────┤
│ task_id          UUID                            │
│ task_type        REFACTOR | BUG_FIX | ...        │
│ original_input   JSON — original task parameters │
│ failure_reason   enum (see §10.3.3)              │
│ error_message    string                          │
│ failed_at        timestamp                       │
│ retry_count      integer (default 0, max 3)      │
│ last_retry_at    timestamp | null                │
│ status           PENDING_RETRY | ABANDONED       │
│ audit_log_ref    UUID — link to full audit trail  │
└──────────────────────────────────────────────────┘
```

**CLI commands:**
- `code-reviewer tasks --failed` — list all items in the dead letter queue
- `code-reviewer tasks retry <task-id>` — re-queue a failed task for retry
- `code-reviewer tasks abandon <task-id>` — permanently mark as abandoned
- `code-reviewer tasks retry-all` — retry all eligible failed tasks (retry_count < 3)

**Automatic retry policy:** Transient failures are retried automatically (max 3 times, exponential backoff: 30s → 2min → 10min). Recoverable and Fatal failures require manual retry via CLI.

---

## 15. Testing Strategy

### 15.1 Test Pyramid

| Level | Scope | Tools | Coverage Target |
|-------|-------|-------|----------------|
| **Unit Tests** | Individual functions, parsers, chunkers, scoring logic, prompt builders | `pytest`, `pytest-mock` | 80%+ |
| **Integration Tests** | Indexing pipeline, RAG retrieval, Git sandbox operations, evaluation pipeline | `pytest`, `testcontainers`, temp Git repos | Key workflows |
| **Agent Tests** | Deterministic agent runs with mocked LLM responses | `pytest`, `vcrpy` or custom response cassettes | All task types |
| **API Tests** | REST endpoint contracts, auth, error handling | `pytest`, `httpx` (async client) | All endpoints |
| **E2E Tests** | Full flow: index → propose → evaluate → score → accept | `pytest`, real local LLM (Ollama), test repo | Happy path + key error paths |
| **UI Tests** | Component rendering, user interactions | `vitest`, `playwright` (if React); manual if Jinja2 | Critical paths |

### 15.2 Test Fixtures
- A small canonical test repository (~50 files, ~5K LOC) with known issues (dead code, duplicated functions, a seeded bug, lint violations) for deterministic agent testing.
- Pre-recorded LLM response cassettes for reproducible agent tests without API calls.

### 15.3 CI Pipeline
```
[ lint (ruff) ] → [ type-check (mypy) ] → [ unit tests ] → [ integration tests ] → [ build Docker image ] → [ E2E tests ]
```

---

## 16. Deployment Architecture

### 16.1 Local Development
```
code-reviewer (pip install -e .)
├── CLI available as `code-reviewer` command
├── API server: `code-reviewer serve` (FastAPI on localhost:8000)
├── Vector DB: ChromaDB (embedded, file-based)
├── Metadata DB: SQLite
└── LLM: Ollama (local) or OpenAI API (cloud)
```

### 16.2 Docker Compose (Self-Hosted)
```yaml
services:
  api:        # FastAPI server
  worker:     # Celery worker for agent + evaluation tasks
  web:        # Web UI (static files served by Nginx or built-in)
  vectordb:   # Qdrant
  metadb:     # PostgreSQL
  redis:      # Task queue + cache
  ollama:     # Local LLM (optional)
```

### 16.3 Production (Future)
- Kubernetes deployment with Helm chart.
- Horizontal scaling of worker nodes.
- Managed vector DB (Qdrant Cloud, Pinecone).
- Managed PostgreSQL (RDS, Cloud SQL).

### 16.4 Data Migration (SQLite → PostgreSQL)

When upgrading from local development (SQLite) to a Docker Compose or production deployment (PostgreSQL), data must be migrated safely.

#### Schema Management

| Tool | Usage |
|------|-------|
| **Alembic** | Schema migrations for both SQLite and PostgreSQL. All schema changes are versioned as Alembic migration scripts. |
| Migration directory | `src/db/migrations/` — contains all Alembic revision files. |
| Auto-generation | `alembic revision --autogenerate -m "description"` detects schema changes from SQLAlchemy models. |
| Apply migrations | `code-reviewer db upgrade` (wraps `alembic upgrade head`). |
| Rollback | `code-reviewer db downgrade -1` (rolls back one migration). |

#### Migration Process

```
1. Export data from SQLite:
   $ code-reviewer db export --format json --output backup.json

2. Verify PostgreSQL connection:
   $ code-reviewer db check --db-url postgresql://user:pass@host/dbname

3. Apply schema to PostgreSQL:
   $ CODE_REVIEWER_DB_URL=postgresql://... code-reviewer db upgrade

4. Import data into PostgreSQL:
   $ CODE_REVIEWER_DB_URL=postgresql://... code-reviewer db import --input backup.json

5. Validate migration:
   $ code-reviewer db validate
   → Compares row counts and checksums between source and target
```

#### Schema Versioning Policy

| Policy | Detail |
|--------|--------|
| Version format | Alembic revision IDs (auto-generated hash) with human-readable message |
| Initial migration | Creates all tables from §10 Data Model. Included in project scaffolding. |
| Forward-only in production | Downgrade scripts are provided for development but not guaranteed in production. |
| SQLite ↔ PostgreSQL compatibility | All migrations tested against both backends in CI. SQL dialect differences handled by SQLAlchemy's dialect abstraction. |
| Startup auto-migrate | On application startup, system checks current schema version and applies pending migrations automatically (configurable: `[database] auto_migrate = true`). |

---

## 17. Phased Roadmap

### Phase 1: Foundation (Weeks 1–3)
**Goal:** Core indexing + basic agent loop + CLI skeleton

- [ ] Project scaffolding (pyproject.toml, directory structure, CI)
- [ ] Git integration module (clone, branch, diff, apply)
- [ ] AST parser + intelligent code chunker (tree-sitter)
- [ ] Embedding pipeline (code chunks → vectors)
- [ ] Vector DB integration (ChromaDB)
- [ ] Basic RAG retrieval (vector search + prompt construction)
- [ ] LLM client abstraction (OpenAI + Ollama adapters)
- [ ] CLI commands: `init`, `index`, `config`
- [ ] Unit tests for all foundation modules

### Phase 2: Agent Core (Weeks 4–6)
**Goal:** Working agent loop that proposes changes

- [ ] ReAct agent loop (observe → think → act → validate)
- [ ] Agent tool implementations (file read, vector search, AST query)
- [ ] Sandbox branch manager (create, apply diff, validate)
- [ ] Refactoring task type (detect + propose code improvements)
- [ ] Bug-fix task type (given a bug report, localize + fix)
- [ ] Structured proposal output (JSON schema)
- [ ] CLI commands: `propose`, `status`
- [ ] Agent reasoning audit trail logging
- [ ] Integration tests with mocked LLM

### Phase 3: Evaluation Pipeline (Weeks 7–8)
**Goal:** Automated validation of proposed changes

- [ ] Evaluation pipeline orchestrator (step runner)
- [ ] Build/compile check step
- [ ] Unit test execution step
- [ ] Lint check step (Ruff)
- [ ] Evaluation result capture (pass/fail, output, timing)
- [ ] Pre-change vs. post-change delta computation
- [ ] Configurable evaluation profiles (quick, full)
- [ ] Timeout and resource limit enforcement
- [ ] CLI commands: display evaluation results inline

### Phase 4: Scoring & Explanation (Weeks 9–10)
**Goal:** Quality scores and human-readable explanations

- [ ] Composite scoring algorithm (correctness, readability, risk, complexity)
- [ ] Risk classification (low/medium/high/critical)
- [ ] Natural-language explanation generation (LLM-based)
- [ ] Unified diff generation with syntax highlighting (CLI)
- [ ] CLI commands: `accept`, `reject`, `logs`
- [ ] Proposal export as Markdown report

### Phase 5: Web UI (Weeks 11–13)
**Goal:** Browser-based dashboard

- [ ] FastAPI REST API (all endpoints from §11)
- [ ] WebSocket streaming for agent reasoning and evaluation logs
- [ ] Web UI: Dashboard (health summary, recent proposals)
- [ ] Web UI: Proposal detail (diff viewer, explanation, scores)
- [ ] Web UI: Evaluation results display
- [ ] Web UI: Accept/reject workflow
- [ ] Web UI: Agent audit trail viewer
- [ ] Dark mode, responsive layout

### Phase 6: Polish & Production Readiness (Weeks 14–16)
**Goal:** Harden for real-world use

- [ ] Docker Compose deployment stack
- [ ] Incremental re-indexing
- [ ] PR review integration (GitHub API)
- [ ] Scheduled health scans (cron)
- [ ] API key authentication
- [ ] Performance optimization (chunking, embedding batching, caching)
- [ ] Comprehensive E2E test suite
- [ ] Documentation (README, usage guide, API docs)
- [ ] Portfolio demo recording / screenshots

---

## 18. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **LLM hallucinations produce invalid code** | High | High | Always validate proposals through the evaluation pipeline before surfacing to user. Never auto-merge. |
| **LLM API costs escalate** | Medium | Medium | Token budget enforcement per task. Support local models (Ollama). Cache LLM responses for identical prompts. |
| **Agent enters infinite reasoning loops** | Medium | Medium | Hard iteration limit (default 15). Token budget cap. Watchdog timer per task. |
| **Sandbox branch leaks into main** | Low | Critical | Git operations wrapped in a safe API; agent has no direct main-branch write access. Branch protection rules. |
| **Large repos cause OOM** | Medium | High | Streaming/batched indexing. Configurable max file size. Lazy embedding loading. |
| **Evaluation pipeline flaky tests** | Medium | Medium | Distinguish between pre-existing failures and regressions. Delta-based scoring only penalizes new failures. |
| **LLM rate limits block agent** | Medium | Low | Exponential backoff + retry. Queue-based task execution. Support provider failover. |
| **tree-sitter parsing gaps for edge-case syntax** | Low | Low | Fallback to line-based chunking if AST parse fails. Log parse warnings for review. |
| **Scope creep** | High | Medium | Strict phase-gated roadmap. V1 focused on single-language (Python) repos. Non-goals clearly defined. |

---

## 19. Success Metrics & KPIs

### 19.1 Technical Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Indexing throughput | ≥ 10K LOC/min | Wall-clock time for index command |
| Proposal quality (agent-generated diffs that pass evaluation) | ≥ 60% of proposals pass all checks | Ratio of PASSED / total proposals |
| Evaluation pipeline reliability | ≥ 95% runs complete without system error | Pipeline error rate monitoring |
| End-to-end proposal time (excl. evaluation) | ≤ 5 min per proposal | Agent task duration logging |
| RAG retrieval relevance | ≥ 70% of retrieved chunks are relevant (manual spot-check) | Periodic human evaluation |

### 19.2 Portfolio / Demo Metrics

| Metric | Target |
|--------|--------|
| Demo repo successfully indexed and analyzed | At least 2 open-source repos (10K+ LOC) |
| Agent successfully proposes and validates ≥ 5 meaningful refactors | Demonstrated in portfolio |
| Web UI is polished and functional for end-to-end workflow | Screenshot/video for resume |
| System runs locally with zero cloud dependencies (Ollama mode) | Demonstrated |
| README and documentation are comprehensive | Published on GitHub |

---

## 20. Glossary

| Term | Definition |
|------|-----------|
| **AST** | Abstract Syntax Tree — a tree representation of the syntactic structure of source code |
| **RAG** | Retrieval-Augmented Generation — enhancing LLM prompts with retrieved context from a knowledge base |
| **ReAct** | Reasoning + Acting — an agent pattern where the LLM interleaves reasoning traces with tool actions |
| **Sandbox Branch** | An isolated Git branch where proposed changes are applied and tested without affecting the main branch |
| **Evaluation Pipeline** | A sequence of automated checks (compile, test, lint, perf) run against proposed code changes |
| **Proposal** | A discrete unit of work produced by the agent: a code diff + explanation + score |
| **Chunking** | Splitting source files into semantically meaningful segments (functions, classes) for embedding |
| **Embedding** | A dense vector representation of a code chunk, used for similarity search |
| **Vector DB** | A database optimized for storing and querying vector embeddings via similarity search |
| **LLM** | Large Language Model — the AI model used for code understanding, reasoning, and generation |
| **Blast Radius** | The scope of potential impact of a code change (number of files, functions, and tests affected) |
| **Diff** | A textual representation of differences between two versions of a file |
| **ADR** | Architecture Decision Record — a document capturing an important architectural decision |
| **tree-sitter** | A parser tool that builds concrete syntax trees for source code, supporting many languages |

---

*End of Project Requirements Document*
