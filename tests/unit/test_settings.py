"""Tests for the Phase 1 safety lock in `app.config.settings`."""

from __future__ import annotations

import pytest

from app.config.settings import PHASE1_SAFETY_FLAGS, load_settings


def test_phase1_defaults_are_safe(phase1_settings):
    assert phase1_settings.trading_mode == "paper"
    assert phase1_settings.live_trading_enabled is False
    assert phase1_settings.right_tail_enabled is False
    assert phase1_settings.llm_enabled is False
    assert phase1_settings.exchange_live_order_enabled is False


@pytest.mark.parametrize(
    "env",
    [
        {"AMA_TRADING_MODE": "live"},
        {"AMA_LIVE_TRADING_ENABLED": "true"},
        {"AMA_RIGHT_TAIL_ENABLED": "true"},
        {"AMA_LLM_ENABLED": "true"},
        {"AMA_EXCHANGE_LIVE_ORDER_ENABLED": "true"},
    ],
)
def test_phase1_lock_overrides_env(monkeypatch, env):
    """Env vars MUST NOT be able to flip the safety flags in Phase 1."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = load_settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert s.right_tail_enabled is False
    assert s.llm_enabled is False
    assert s.exchange_live_order_enabled is False


def test_phase1_safety_flags_constant_matches_invariants():
    assert PHASE1_SAFETY_FLAGS == {
        "trading_mode": "paper",
        "live_trading_enabled": False,
        "right_tail_enabled": False,
        "llm_enabled": False,
        "exchange_live_order_enabled": False,
    }


def test_data_dir_resolves_under_project_root(phase1_settings):
    assert phase1_settings.data_dir.is_absolute()
    assert phase1_settings.sqlite_dir.name == "sqlite"
