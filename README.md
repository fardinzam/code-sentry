# Agentic AI Code Reviewer & Auto-Refactor System

An AI-powered engineering system that understands a production codebase, proposes safe code changes, and validates them through automated evaluation pipelines.

## Features

- **Codebase Indexing** — AST-aware parsing and vector embedding of your entire codebase
- **AI Agent** — ReAct-loop agent that proposes refactors, bug fixes, and PR reviews
- **Automated Evaluation** — Compile, test, lint, and performance checks on every proposal
- **Quality Scoring** — Composite scoring algorithm with risk classification
- **Sandbox Safety** — All changes applied on isolated Git branches, never touching your main code
- **Auditable** — Full reasoning trace, diff, and explanation for every proposal
- **Web UI & CLI** — Browser dashboard and terminal interface

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| CLI | Typer + Rich |
| API Server | FastAPI |
| LLM | OpenAI, Anthropic, Ollama (local) |
| Embeddings | text-embedding-3-small / nomic-embed-text |
| Vector DB | ChromaDB (local), Qdrant (production) |
| AST Parsing | tree-sitter |
| Database | SQLite (local), PostgreSQL (production) |
| Task Queue | Celery + Redis |

## Quick Start

### Prerequisites

- Python 3.11+
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/code-reviewer.git
cd code-reviewer

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"
```

### Basic Usage

```bash
# Initialize a project
code-reviewer init /path/to/your/repo

# Index the codebase
code-reviewer index

# Propose a refactor
code-reviewer propose refactor --scope src/

# Check status
code-reviewer status

# Review and accept
code-reviewer diff <proposal-id>
code-reviewer accept <proposal-id>
```

## Project Structure

```
src/
├── cli/           # Typer CLI commands
├── api/           # FastAPI REST API server
├── agent/         # ReAct agent loop and task types
│   ├── tasks/     # Refactor, bug-fix, review, health-scan, explain
│   └── tools/     # Agent tools (file_read, vector_search, etc.)
├── indexing/      # AST parsing, chunking, embedding pipeline
├── retrieval/     # Vector search, hybrid retrieval, prompt building
├── evaluation/    # Automated evaluation pipeline
│   └── steps/     # Compile, test, lint, performance steps
├── scoring/       # Quality scoring algorithm
├── schemas/       # Pydantic models and JSON schemas
├── git_ops/       # Git integration and sandbox management
├── llm/           # LLM client abstraction (OpenAI, Anthropic, Ollama)
├── db/            # SQLAlchemy models and Alembic migrations
├── config/        # Configuration loading and prompt templates
└── utils/         # Logging, error handling, shared utilities
tests/
├── unit/          # Unit tests (80%+ coverage target)
├── integration/   # Integration tests
└── fixtures/      # Test repo, LLM response cassettes
```

## Development

```bash
# Run linting
ruff check .

# Run type checking
mypy src/

# Run tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=html
```

## Documentation

- [Project Requirements (PRD)](./PROJECT_REQUIREMENTS.md) — Full technical specification
- [Development Task List](./TODO.md) — Phased implementation plan
- API docs available at `http://localhost:8000/docs` when the server is running

## License

MIT
