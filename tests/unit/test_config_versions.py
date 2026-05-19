"""Phase 8.5 - ConfigVersions contract tests (Issue #8.5)."""

from __future__ import annotations

import json

import pytest

import app
from app.learning import (
    ConfigVersions,
    config_versions_to_payload,
    payload_to_config_versions,
)
from app.learning.versions import (
    APP_VERSION_LABEL,
    DEFAULT_CAPITAL_STATE_VERSION,
    DEFAULT_LLM_PROMPT_VERSION,
    DEFAULT_RISK_CONFIG_VERSION,
    DEFAULT_SCORING_VERSION,
    DEFAULT_STATE_MACHINE_VERSION,
    DEFAULT_STRATEGY_VERSION,
)


def test_config_versions_defaults_track_app_version():
    """Phase 8.5 self-check #1: ``ConfigVersions`` defaults must
    track :data:`app.__version__` at import time so a future
    ``__version__`` bump (1.4.0a8.5 -> 1.4.0a9 -> 1.5.0 ...) is
    automatically reflected in every emitted event without needing
    a parallel edit in this module.

    The labels are formatted ``"v<__version__>"``.
    """
    expected = f"v{app.__version__}"
    assert APP_VERSION_LABEL == expected
    assert DEFAULT_STRATEGY_VERSION == expected
    assert DEFAULT_RISK_CONFIG_VERSION == expected
    assert DEFAULT_SCORING_VERSION == expected
    assert DEFAULT_CAPITAL_STATE_VERSION == expected
    assert DEFAULT_STATE_MACHINE_VERSION == expected


def test_config_versions_defaults_match_module_constants():
    versions = ConfigVersions.defaults()
    assert versions.strategy_version == DEFAULT_STRATEGY_VERSION
    assert versions.risk_config_version == DEFAULT_RISK_CONFIG_VERSION
    assert versions.scoring_version == DEFAULT_SCORING_VERSION
    assert versions.capital_state_version == DEFAULT_CAPITAL_STATE_VERSION
    assert versions.state_machine_version == DEFAULT_STATE_MACHINE_VERSION
    assert versions.llm_prompt_version == DEFAULT_LLM_PROMPT_VERSION


def test_config_versions_defaults_llm_prompt_is_na():
    """Phase 8.5 forbids any LLM trade involvement; the default prompt
    version label must therefore be a non-secret stub."""
    assert ConfigVersions.defaults().llm_prompt_version == "n/a"
    assert DEFAULT_LLM_PROMPT_VERSION == "n/a"


def test_config_versions_payload_has_six_required_fields():
    payload = config_versions_to_payload(ConfigVersions.defaults())
    expected = {
        "strategy_version",
        "risk_config_version",
        "scoring_version",
        "capital_state_version",
        "state_machine_version",
        "llm_prompt_version",
    }
    assert set(payload.keys()) == expected


def test_config_versions_round_trip():
    original = ConfigVersions(
        strategy_version="strategy-2026-05",
        risk_config_version="risk-2026-05",
        scoring_version="scoring-2026-05",
        capital_state_version="capital-2026-05",
        state_machine_version="state-2026-05",
        llm_prompt_version="prompt-2026-05",
    )
    payload = config_versions_to_payload(original)
    restored = payload_to_config_versions(payload)
    assert restored == original


def test_config_versions_payload_is_json_safe():
    json.dumps(config_versions_to_payload(ConfigVersions.defaults()))


def test_config_versions_is_frozen():
    versions = ConfigVersions.defaults()
    with pytest.raises((TypeError, ValueError)):
        versions.strategy_version = "x"  # type: ignore[misc]


def test_config_versions_payload_to_handles_legacy_missing_fields():
    """Older payloads that pre-date one of the six fields must replay
    by falling back to the Phase 8.5 defaults."""
    legacy = {"strategy_version": "v1"}
    restored = payload_to_config_versions(legacy)
    assert restored.strategy_version == "v1"
    assert restored.risk_config_version == DEFAULT_RISK_CONFIG_VERSION
    assert restored.llm_prompt_version == DEFAULT_LLM_PROMPT_VERSION


def test_config_versions_defaults_have_no_hardcoded_phase_label():
    """Defence against version-string drift: the labels must not be
    a frozen ``"v1.4.0a8.5"`` literal that survives a future bump.
    Anchor: they are the formatted ``app.__version__`` rather than
    a hard-coded copy.

    If a future maintainer reverts to a hard-coded literal AND bumps
    ``app.__version__`` separately, this test fires.
    """
    if app.__version__ != "1.4.0a8.5":
        for label in (
            DEFAULT_STRATEGY_VERSION,
            DEFAULT_RISK_CONFIG_VERSION,
            DEFAULT_SCORING_VERSION,
            DEFAULT_CAPITAL_STATE_VERSION,
            DEFAULT_STATE_MACHINE_VERSION,
        ):
            assert "1.4.0a8.5" not in label, (
                f"stale Phase 8.5 hard-coded literal in default {label!r}; "
                f"defaults must track app.__version__"
            )
