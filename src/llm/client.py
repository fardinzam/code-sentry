"""LLM client abstraction with provider adapters, retry, and caching (§12.2, §7.13)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from src.utils.errors import LLMAuthError, LLMBudgetExhaustedError, LLMError, TransientError
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ─── Response model ───────────────────────────────────────────────────────────


@dataclass
class LLMResponse:
    """Structured response from any LLM provider.

    Attributes:
        content: Text content of the response.
        input_tokens: Number of tokens in the prompt.
        output_tokens: Number of tokens in the completion.
        model: Model name used.
        latency_ms: Round-trip time in milliseconds.
        cached: True if the response was served from cache.
    """

    content: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: float
    cached: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ─── Protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class LLMClient(Protocol):
    """Interface for LLM providers."""

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        """Generate a completion from a message list."""
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate the token count for a text string."""
        ...


# ─── OpenAI adapter ───────────────────────────────────────────────────────────


class OpenAIClient:
    """OpenAI chat completions adapter.

    Args:
        model: Model name (e.g. "gpt-4o").
        api_key: API key. Reads from OPENAI_API_KEY env if not provided.
        temperature: Sampling temperature.
        max_retries: Retry attempts on transient errors (rate limits, timeouts).
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        temperature: float = 0.2,
        max_retries: int = 3,
        timeout: int = 120,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("openai package required: pip install openai") from exc

        self._client = OpenAI(api_key=api_key, timeout=timeout)
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        temperature = kwargs.get("temperature", self._temperature)
        json_mode = kwargs.get("json_mode", False)

        extra: dict[str, Any] = {}
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        for attempt in range(self._max_retries):
            try:
                start = time.monotonic()
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    **extra,
                )
                latency_ms = (time.monotonic() - start) * 1000
                return LLMResponse(
                    content=response.choices[0].message.content or "",
                    input_tokens=response.usage.prompt_tokens if response.usage else 0,
                    output_tokens=response.usage.completion_tokens if response.usage else 0,
                    model=self._model,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                error_str = str(exc)
                if "401" in error_str or "403" in error_str or "invalid_api_key" in error_str:
                    raise LLMAuthError(
                        "LLM API key is invalid or expired. "
                        "Run `code-reviewer config` to update your API key."
                    ) from exc
                if "429" in error_str or "timeout" in error_str.lower():
                    if attempt < self._max_retries - 1:
                        delay = 2.0 ** attempt
                        logger.warning("LLM rate limited — retrying", extra={"delay_s": delay})
                        time.sleep(delay)
                        continue
                    raise TransientError(
                        f"LLM rate limit not resolved after {self._max_retries} attempts"
                    ) from exc
                raise LLMError(f"OpenAI API error: {exc}") from exc

        raise LLMError("Unexpected: retry loop exhausted without returning or raising")

    def count_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken."""
        try:
            import tiktoken

            enc = tiktoken.encoding_for_model(self._model)
            return len(enc.encode(text))
        except Exception:
            return max(1, len(text) // 4)


# ─── Ollama adapter ───────────────────────────────────────────────────────────


class OllamaClient:
    """Ollama local LLM adapter via the OpenAI-compatible API.

    Args:
        model: Ollama model name (e.g. "llama3").
        base_url: Ollama server base URL.
        temperature: Sampling temperature.
    """

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.2,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        try:
            import httpx
        except ImportError as exc:
            raise ImportError("httpx package required: pip install httpx") from exc

        temperature = kwargs.get("temperature", self._temperature)
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if kwargs.get("json_mode"):
            payload["format"] = "json"

        try:
            start = time.monotonic()
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=300.0,
            )
            response.raise_for_status()
            data = response.json()
            latency_ms = (time.monotonic() - start) * 1000

            return LLMResponse(
                content=data.get("message", {}).get("content", ""),
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                model=self._model,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            if "503" in str(exc) or "Connection" in str(exc):
                raise TransientError(f"Ollama unavailable: {exc}") from exc
            raise LLMError(f"Ollama error: {exc}") from exc

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


# ─── Token budget tracker ─────────────────────────────────────────────────────


class TokenBudgetTracker:
    """Track token usage per task and enforce budget limits.

    Args:
        max_tokens: Hard token limit for this task.
        warn_at_percent: Emit a warning log when usage exceeds this fraction.
    """

    def __init__(self, max_tokens: int, warn_at_percent: float = 0.8) -> None:
        self._max = max_tokens
        self._warn_at = int(max_tokens * warn_at_percent)
        self._used = 0

    def record(self, tokens: int) -> None:
        """Record token usage from one LLM call.

        Raises:
            LLMBudgetExhaustedError: When the budget is exceeded.
        """
        self._used += tokens
        if self._used > self._max:
            raise LLMBudgetExhaustedError(
                f"Token budget exhausted: {self._used:,} / {self._max:,} tokens used."
            )
        if self._used >= self._warn_at:
            logger.warning(
                "Token budget >80% consumed",
                extra={"used": self._used, "max": self._max},
            )

    @property
    def remaining(self) -> int:
        return max(0, self._max - self._used)

    @property
    def total_used(self) -> int:
        return self._used


# ─── Cache key ────────────────────────────────────────────────────────────────


def _make_cache_key(model: str, temperature: float, messages: list[dict[str, str]]) -> str:
    """Compute a deterministic SHA-256 cache key from prompt inputs (§7.13.1)."""
    payload = json.dumps(
        {"model": model, "temperature": temperature, "messages": messages},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ─── Factory ──────────────────────────────────────────────────────────────────


def make_llm_client(provider: str, model: str, **kwargs: Any) -> LLMClient:
    """Instantiate the correct LLMClient for the given provider.

    Args:
        provider: "openai", "anthropic", "ollama", or "vllm".
        model: Model name.
        **kwargs: Additional constructor arguments.

    Returns:
        LLMClient instance.

    Raises:
        ValueError: For unknown provider names.
    """
    if provider == "openai":
        return OpenAIClient(model=model, **kwargs)
    if provider == "ollama":
        return OllamaClient(model=model, **kwargs)
    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        "Supported: 'openai', 'ollama'. (Anthropic/vLLM adapters coming in Phase 2)"
    )
