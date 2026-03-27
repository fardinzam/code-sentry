---
name: llm-prompt-engineering
description: How to build the prompt engineering layer with Jinja2 templates, JSON output schemas, structured outputs, and error-recovery prompts
---

# LLM Prompt Engineering

## Overview

This skill guides building the prompt engineering layer for the `codeagent` system. It covers the 6-layer prompt architecture, Jinja2 template assembly, OpenAI Structured Outputs, markdown fence parsing for local models, and error-recovery re-prompting.

## Prerequisites

```bash
pip install jinja2 openai tiktoken jsonschema pydantic
```

## Step-by-Step Instructions

### 1. Prompt Builder Class

The `PromptBuilder` assembles the 6-layer prompt structure using Jinja2 templates.

```python
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import tiktoken
import json

PROMPTS_DIR = Path(__file__).parent / "prompts"

class PromptBuilder:
    def __init__(self, model: str = "gpt-4o"):
        self.env = Environment(
            loader=FileSystemLoader(PROMPTS_DIR / "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.model = model
        self.encoder = tiktoken.encoding_for_model(model)

    def build(
        self,
        mode: str,
        context_chunks: list[dict],
        task_instruction: str,
        conversation_history: list[dict] | None = None,
        max_context_tokens: int | None = None,
    ) -> list[dict]:
        """Assemble the 6-layer prompt as a list of chat messages."""
        messages = []

        # Layer 1: System prompt (mode-specific)
        system_template = self.env.get_template(f"system_{mode}.j2")
        schema = self._load_schema(mode)
        system_content = system_template.render(output_schema=json.dumps(schema, indent=2))
        messages.append({"role": "system", "content": system_content})

        # Layer 2: Output schema is embedded in system prompt (above)

        # Layer 3: Few-shot examples (as user/assistant turns)
        few_shots = self._load_few_shots(mode)
        for example in few_shots:
            messages.append({"role": "user", "content": example["user_message"]})
            messages.append({"role": "assistant", "content": example["assistant_message"]})

        # Layer 4: Retrieved context
        context_text = self._pack_context(context_chunks, max_context_tokens)

        # Layer 5: Task instruction (combined with context)
        user_content = f"## Retrieved Context\n\n{context_text}\n\n## Task\n\n{task_instruction}"
        messages.append({"role": "user", "content": user_content})

        # Layer 6: Conversation history (inject before task if multi-turn)
        if conversation_history:
            # Insert history before the final user message
            for msg in conversation_history[-5:]:  # Cap at 5 turns
                messages.insert(-1, msg)

        return messages

    def count_tokens(self, messages: list[dict]) -> int:
        """Count exact tokens for a message list."""
        total = 0
        for msg in messages:
            total += 4  # message overhead
            total += len(self.encoder.encode(msg["content"]))
        total += 2  # reply priming
        return total

    def _load_schema(self, mode: str) -> dict:
        schema_map = {"review": "review_output", "refactor": "change_output",
                       "bugfix": "change_output", "explain": "explain_output"}
        schema_file = PROMPTS_DIR / "schemas" / f"{schema_map[mode]}.json"
        return json.loads(schema_file.read_text())

    def _load_few_shots(self, mode: str) -> list[dict]:
        fs_file = PROMPTS_DIR / "few_shots" / f"{mode}_examples.json"
        if fs_file.exists():
            return json.loads(fs_file.read_text())
        return []

    def _pack_context(self, chunks: list[dict], max_tokens: int | None) -> str:
        """Pack chunks into context, respecting token budget."""
        parts = []
        token_count = 0
        for chunk in chunks:
            chunk_text = f"### {chunk['metadata']['file_path']} (lines {chunk['metadata']['start_line']}-{chunk['metadata']['end_line']})\n```python\n{chunk['source']}\n```\n"
            chunk_tokens = len(self.encoder.encode(chunk_text))
            if max_tokens and token_count + chunk_tokens > max_tokens:
                break
            parts.append(chunk_text)
            token_count += chunk_tokens
        return "\n".join(parts)
```

### 2. Jinja2 System Prompt Template Example

File: `templates/system_review.j2`

```jinja2
You are a senior Python code reviewer with deep expertise in software quality, security, and best practices.

YOUR TASK:
Analyze the provided code and identify issues across these categories:
- **Bugs**: Logic errors, off-by-one errors, null/None handling, race conditions
- **Security**: SQL injection, path traversal, credential exposure, unsafe deserialization
- **Performance**: Unnecessary loops, N+1 queries, missing caching opportunities
- **Style**: Naming conventions (PEP 8), dead code, overly complex expressions
- **Duplication**: Copy-pasted logic that should be extracted into shared functions

RULES:
1. Be specific — reference exact line numbers and variable names.
2. Explain *why* each issue matters, not just *what* is wrong.
3. Categorize every finding by severity (critical / warning / info).
4. Do NOT propose code changes or diffs. Only describe issues and suggest fixes in prose.
5. If the code is well-written and you find no issues, say so. Do not invent problems.
6. Assign a confidence score (0–100) reflecting how certain you are in your analysis.
7. Assign a risk level (low / medium / high) based on the severity of findings.

OUTPUT SCHEMA:
Respond ONLY with valid JSON matching this schema. No additional text.

{{ output_schema }}
```

### 3. OpenAI Structured Outputs

For OpenAI, use Structured Outputs to guarantee valid JSON:

```python
from openai import OpenAI

def call_openai_structured(
    client: OpenAI,
    messages: list[dict],
    schema: dict,
    model: str = "gpt-4o",
) -> dict:
    """Call OpenAI with Structured Outputs for guaranteed JSON."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "agent_response",
                "strict": True,
                "schema": schema,
            },
        },
    )
    return json.loads(response.choices[0].message.content)
```

### 4. Markdown Fence Parsing (Local Models)

For Ollama/local models, extract JSON from markdown fences:

```python
import re

def parse_fenced_json(response_text: str) -> dict:
    """Extract and parse JSON from markdown-fenced LLM response."""
    # Try to find ```json ... ``` block
    pattern = r"```(?:json)?\s*\n(.*?)```"
    match = re.search(pattern, response_text, re.DOTALL)

    if match:
        json_str = match.group(1).strip()
    else:
        # Maybe the entire response is JSON (no fences)
        json_str = response_text.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Attempt basic repairs
        return _repair_json(json_str, e)

def _repair_json(text: str, original_error: json.JSONDecodeError) -> dict:
    """Attempt to repair common JSON issues from LLMs."""
    # Strip any remaining markdown
    text = re.sub(r"^```\w*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    # Fix trailing commas
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Fix single quotes → double quotes
    text = text.replace("'", '"')

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise original_error  # Re-raise original if repair fails
```

### 5. Error-Recovery Re-Prompting

```python
from jinja2 import Template

ERROR_TEMPLATES = {
    "malformed_json": "Your previous response was not valid JSON. Parse error: {{ error }}. Please respond ONLY with valid JSON matching this schema: {{ schema }}. Do not include any text outside the JSON object.",
    "malformed_diff": "The unified diff in your response could not be applied. Error: {{ error }}. Here is the current content of the target file:\n\n```python\n{{ file_content }}\n```\n\nPlease regenerate a valid unified diff.",
    "empty_response": "You returned an empty or null response. Please analyze the provided code and respond with your findings/changes in the required JSON format.",
    "missing_fields": "Your response is missing required fields: {{ missing_fields }}. Please include all required fields: summary, confidence, risk, and {{ mode_fields }}.",
    "hallucinated_import": "Your change adds an import for '{{ package }}', but this package does not exist on PyPI. Please revise using only: {{ existing_deps }}.",
    "out_of_scope": "Your changes modify functionality beyond the requested scope. The original task was: '{{ original_task }}'. Please limit your changes to only what was requested.",
}

def build_recovery_prompt(error_type: str, **kwargs) -> str:
    """Build a recovery prompt for a specific error scenario."""
    template_str = ERROR_TEMPLATES.get(error_type)
    if not template_str:
        raise ValueError(f"Unknown error type: {error_type}")
    return Template(template_str).render(**kwargs)
```

### 6. Debug Mode (FR-3.14)

```python
def dump_prompt_debug(messages: list[dict], output_path: str) -> None:
    """Dump the fully assembled prompt for debugging/tuning."""
    with open(output_path, "w") as f:
        for i, msg in enumerate(messages):
            f.write(f"{'='*60}\n")
            f.write(f"[{i}] Role: {msg['role']}\n")
            f.write(f"{'='*60}\n")
            f.write(msg["content"])
            f.write("\n\n")
    print(f"🐛 Prompt dumped to {output_path}")
```

## Common Pitfalls

- **Token counting must be exact** — use `tiktoken` for OpenAI, never estimate. A prompt that's "close to the limit" will silently truncate
- **Few-shot examples eat tokens** — 2 examples can cost 1,000+ tokens each. Budget for this in the `TokenBudgetManager`
- **Structured Outputs require `strict: True`** — without it, the schema is advisory only and the LLM may deviate
- **Don't embed the schema in the system prompt AND use Structured Outputs** — it's redundant and wastes tokens. Use one or the other depending on provider
- **Jinja2 autoescape** — don't enable HTML autoescaping for prompt templates. It will mangle code in the context
- **Error recovery max retries** — always cap at 2 retries (per FR-8.3). Log each attempt for debugging
