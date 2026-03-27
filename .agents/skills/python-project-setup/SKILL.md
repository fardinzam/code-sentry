---
name: python-project-setup
description: How to scaffold a Python project with pyproject.toml, poetry, ruff, mypy, pytest, and pre-commit hooks
---

# Python Project Setup

## Overview

This skill guides scaffolding a production-grade Python project for the `codeagent` package. It covers project metadata, dependency management, linting, type checking, testing, and pre-commit hooks.

## Prerequisites

- Python 3.11+
- `pip` (or `poetry` if using Poetry workflow)

## Step-by-Step Instructions

### 1. Create `pyproject.toml`

Use this as the canonical project configuration file. It replaces `setup.py`, `setup.cfg`, `requirements.txt`, and tool-specific config files.

```toml
[project]
name = "codeagent"
version = "0.1.0"
description = "AI-powered code reviewer and auto-refactor system"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Your Name" }]

dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    "pydantic-settings>=2.0.0",
    "sqlalchemy>=2.0.0",
    "gitpython>=3.1.0",
    "chromadb>=0.4.0",
    "openai>=1.0.0",
    "tiktoken>=0.5.0",
    "tree-sitter>=0.21.0",
    "tree-sitter-python>=0.21.0",
    "unidiff>=0.7.0",
    "jinja2>=3.1.0",
    "httpx>=0.25.0",
    "structlog>=23.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "pre-commit>=3.0.0",
    "vcrpy>=5.0.0",
    "responses>=0.23.0",
    "radon>=6.0.0",
]
local = [
    "sentence-transformers>=2.2.0",
    "faiss-cpu>=1.7.0",
]

[project.scripts]
codeagent = "codeagent.cli.main:app"

[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["codeagent*"]

[tool.ruff]
target-version = "py311"
line-length = 120
src = ["codeagent", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "C4", "SIM", "TCH"]
ignore = ["S101"]  # allow assert in tests

[tool.ruff.lint.isort]
known-first-party = ["codeagent"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = ["chromadb.*", "tree_sitter.*", "unidiff.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=codeagent --cov-report=term-missing"
asyncio_mode = "auto"
```

### 2. Create Package Layout

```bash
mkdir -p codeagent/{cli,indexer,retriever,agent/prompts/{schemas,templates,few_shots},sandbox,scorer,db,ui,utils}
mkdir -p tests/{unit,integration,fixtures/sample_repo}
touch codeagent/__init__.py
touch codeagent/{cli,indexer,retriever,agent,agent/prompts,sandbox,scorer,db,ui,utils}/__init__.py
```

### 3. Set Up Ruff (Linter/Formatter)

Ruff is configured in `pyproject.toml` above. Key commands:

```bash
ruff check .              # Lint
ruff check . --fix        # Lint + auto-fix
ruff format .             # Format
```

### 4. Set Up Pre-Commit Hooks

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.5.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic-settings, sqlalchemy, typer]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

Install: `pre-commit install`

### 5. Create Makefile

```makefile
.PHONY: lint format test type-check install dev

install:
	pip install -e .

dev:
	pip install -e ".[dev,local]"

lint:
	ruff check .

format:
	ruff format .

test:
	pytest

type-check:
	mypy codeagent/

all: format lint type-check test
```

## Common Pitfalls

- **Don't mix `requirements.txt` and `pyproject.toml`** — use `pyproject.toml` as the single source of truth
- **Pin major versions, not exact versions** — use `>=X.Y.0` to allow compatible updates
- **Always add new third-party modules to `[[tool.mypy.overrides]]`** if they lack type stubs
- **Run `ruff format` before `ruff check`** — formatting changes can fix lint errors
