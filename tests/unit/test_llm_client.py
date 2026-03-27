"""Unit tests for LLM client (retry, budget, cache key) (§1.8)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.llm.client import (
    LLMResponse,
    OpenAIClient,
    TokenBudgetTracker,
    _make_cache_key,
)
from src.utils.errors import LLMAuthError, LLMBudgetExhaustedError, TransientError


class TestTokenBudgetTracker:
    """Budget tracker enforces limits and warns at threshold."""

    def test_recording_within_budget_does_not_raise(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=10_000)
        tracker.record(5_000)
        assert tracker.total_used == 5_000
        assert tracker.remaining == 5_000

    def test_exceeding_budget_raises_error(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=1_000)
        with pytest.raises(LLMBudgetExhaustedError):
            tracker.record(1_001)

    def test_warning_logged_at_80_percent(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        tracker = TokenBudgetTracker(max_tokens=1_000, warn_at_percent=0.8)
        with caplog.at_level(logging.WARNING, logger="src.llm.client"):
            tracker.record(800)
        assert any("80%" in r.message or "budget" in r.message.lower() for r in caplog.records)

    def test_remaining_never_goes_negative(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=100)
        try:
            tracker.record(200)
        except LLMBudgetExhaustedError:
            pass
        assert tracker.remaining == 0


class TestCacheKey:
    """Cache keys must be deterministic and distinguish prompt differences."""

    def test_same_inputs_produce_same_key(self) -> None:
        msg = [{"role": "user", "content": "hello"}]
        key1 = _make_cache_key("gpt-4o", 0.2, msg)
        key2 = _make_cache_key("gpt-4o", 0.2, msg)
        assert key1 == key2

    def test_different_model_produces_different_key(self) -> None:
        msg = [{"role": "user", "content": "hello"}]
        assert _make_cache_key("gpt-4o", 0.2, msg) != _make_cache_key("gpt-4", 0.2, msg)

    def test_different_temperature_produces_different_key(self) -> None:
        msg = [{"role": "user", "content": "hello"}]
        assert _make_cache_key("gpt-4o", 0.0, msg) != _make_cache_key("gpt-4o", 0.9, msg)

    def test_different_content_produces_different_key(self) -> None:
        msg1 = [{"role": "user", "content": "hello"}]
        msg2 = [{"role": "user", "content": "world"}]
        assert _make_cache_key("gpt-4o", 0.2, msg1) != _make_cache_key("gpt-4o", 0.2, msg2)

    def test_key_is_64_hex_chars(self) -> None:
        key = _make_cache_key("gpt-4o", 0.2, [])
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


class TestOpenAIClientRetry:
    """Verify retry behaviour on rate limits and auth errors."""

    def _make_client(self) -> OpenAIClient:
        client = OpenAIClient(model="gpt-4o", api_key="test")
        return client

    def test_auth_error_is_not_retried(self) -> None:
        client = self._make_client()

        call_count = [0]

        def fake_create(**kwargs: object) -> None:
            call_count[0] += 1
            raise Exception("401 Unauthorized: invalid_api_key")

        with patch.object(client._client.chat.completions, "create", side_effect=fake_create):
            with pytest.raises(LLMAuthError):
                client.generate([{"role": "user", "content": "hi"}])

        # Auth errors must NOT be retried
        assert call_count[0] == 1

    def test_rate_limit_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = self._make_client()
        monkeypatch.setattr(time, "sleep", lambda _: None)  # skip actual sleep

        call_count = [0]

        def fake_create(**kwargs: object) -> object:
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("429 Too Many Requests: rate limit exceeded")
            # Third attempt succeeds
            mock_usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            mock_choice = MagicMock()
            mock_choice.message.content = "ok"
            mock_resp = MagicMock(choices=[mock_choice], usage=mock_usage)
            return mock_resp

        with patch.object(client._client.chat.completions, "create", side_effect=fake_create):
            response = client.generate([{"role": "user", "content": "hi"}])

        assert call_count[0] == 3
        assert response.content == "ok"

    def test_exhausted_retries_raise_transient_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = self._make_client()
        monkeypatch.setattr(time, "sleep", lambda _: None)

        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=Exception("429 rate limit"),
        ):
            with pytest.raises(TransientError):
                client.generate([{"role": "user", "content": "hi"}])
