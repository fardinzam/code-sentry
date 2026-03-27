"""Unit tests for the configuration system (§1.2)."""

from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path

import pytest

from src.config.settings import (
    LLMSettings,
    ScoringSettings,
    _load_toml_file,
    _merge,
    _strip_sensitive,
    get_settings,
)


class TestConfigHierarchy:
    """Test the 5-layer config merge (§7.11)."""

    def test_defaults_are_applied_without_config_files(self, tmp_path: Path) -> None:
        settings = get_settings(tmp_path)
        assert settings.llm.model == "gpt-4o"
        assert settings.llm.temperature == 0.2
        assert settings.evaluation.timeout_seconds == 600

    def test_project_config_overrides_defaults(self, tmp_path: Path) -> None:
        cr_dir = tmp_path / ".code-reviewer"
        cr_dir.mkdir()
        (cr_dir / "config.toml").write_text('[llm]\nmodel = "gpt-4o-mini"\n')

        settings = get_settings(tmp_path)
        assert settings.llm.model == "gpt-4o-mini"
        # Other keys should still be defaults
        assert settings.llm.temperature == 0.2

    def test_env_var_overrides_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # pydantic-settings reads env vars at class instantiation time.
        # Test at the subsection level where env_prefix is applied.
        monkeypatch.setenv("CODE_REVIEWER_LLM_MODEL", "claude-3-opus")
        from src.config.settings import LLMSettings
        settings = LLMSettings()
        assert settings.model == "claude-3-opus"

    def test_deep_merge_preserves_other_sections(self, tmp_path: Path) -> None:
        cr_dir = tmp_path / ".code-reviewer"
        cr_dir.mkdir()
        (cr_dir / "config.toml").write_text('[evaluation]\ntimeout_seconds = 300\n')

        settings = get_settings(tmp_path)
        assert settings.evaluation.timeout_seconds == 300
        # LLM section untouched
        assert settings.llm.model == "gpt-4o"


class TestSensitiveValueDetection:
    """Sensitive keys are stripped and warned about (§7.11.3)."""

    def test_api_key_in_config_file_is_ignored(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[llm]\napi_key = "sk-test-12345"\nmodel = "gpt-4o"\n')

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _load_toml_file(config_path)

        assert "api_key" not in result.get("llm", {})
        assert any("api_key" in str(w.message) for w in caught)

    def test_non_sensitive_keys_are_not_stripped(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[llm]\nmodel = "gpt-4o"\ntemperature = 0.5\n')

        result = _load_toml_file(config_path)
        assert result["llm"]["model"] == "gpt-4o"
        assert result["llm"]["temperature"] == 0.5

    def test_all_sensitive_fragments_are_caught(self) -> None:
        sensitive_data = {
            "auth_token": "tok123",
            "db_url": "postgresql://...",
            "password": "secret",
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _strip_sensitive(sensitive_data, "test.toml")

        assert result == {}
        assert len(caught) == 3


class TestConfigMerge:
    """Test deep merge logic."""

    def test_later_overrides_earlier(self) -> None:
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 99}}
        merged = _merge(base, override)
        assert merged["a"]["x"] == 1
        assert merged["a"]["y"] == 99

    def test_merge_does_not_mutate_inputs(self) -> None:
        base = {"a": {"x": 1}}
        override = {"a": {"x": 2}}
        _merge(base, override)
        assert base["a"]["x"] == 1


class TestScoringSettingsValidation:
    """Scoring weights must be valid fractions summing to 1.0."""

    def test_weights_summing_to_one_are_valid(self) -> None:
        s = ScoringSettings(
            weight_correctness=0.40,
            weight_readability=0.20,
            weight_risk=0.25,
            weight_complexity=0.15,
        )
        assert s.weight_correctness == 0.40

    def test_weights_not_summing_to_one_raise_error(self) -> None:
        with pytest.raises(Exception, match="sum"):
            ScoringSettings(
                weight_correctness=0.50,
                weight_readability=0.50,
                weight_risk=0.10,
                weight_complexity=0.10,
            )

    def test_weight_out_of_range_raises_error(self) -> None:
        with pytest.raises(Exception):
            ScoringSettings(
                weight_correctness=1.5,
                weight_readability=0.0,
                weight_risk=0.0,
                weight_complexity=0.0,
            )
