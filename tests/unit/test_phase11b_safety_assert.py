"""Phase 11B - boot-time safety assertion tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.config.settings import Settings, get_settings, load_settings
from app.core.errors import SafeModeViolation, SafetyViolation
from app.exchanges.mock import MockExchangeClient
from app.paper_run.config import (
    DEFAULT_PAPER_CLOUD_PATH,
    PaperCloudConfig,
)
from app.paper_run.safety_assert import (
    SafetyAssertionReport,
    assert_paper_cloud_safety,
)


def _settings() -> Settings:
    """Always re-load settings so a previous test's monkeypatch does
    not leak through ``functools.lru_cache``."""
    get_settings.cache_clear()
    return load_settings()


def _paper_cloud() -> PaperCloudConfig:
    return PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)


def test_passes_with_phase1_lock_in_force():
    report = assert_paper_cloud_safety(
        settings=_settings(),
        paper_cloud=_paper_cloud(),
        exchange_client=None,
    )
    assert isinstance(report, SafetyAssertionReport)
    assert report.passed is True
    assert report.trading_mode_paper is True
    assert report.live_trading_enabled_false is True
    assert report.right_tail_enabled_false is True
    assert report.llm_enabled_false is True
    assert report.exchange_live_order_enabled_false is True
    assert report.real_order_enabled_false is True


def test_passes_with_mock_exchange_write_surface_probe():
    """The four ExchangeClientBase write surfaces must still raise."""
    exchange = MockExchangeClient()
    try:
        report = assert_paper_cloud_safety(
            settings=_settings(),
            paper_cloud=_paper_cloud(),
            exchange_client=exchange,
        )
        assert report.write_surfaces_refuse is True
    finally:
        exchange.stop(reason="test_done")


def test_refuses_when_settings_trading_mode_not_paper():
    base = _settings()
    bad_mode = base.defaults.mode.model_copy(
        update={"trading_mode": "live_limited"}
    )
    bad_defaults = base.defaults.model_copy(update={"mode": bad_mode})
    bad_settings = Settings(
        defaults=bad_defaults,
        risk=base.risk,
        strategy=base.strategy,
        project_root=base.project_root,
    )
    with pytest.raises(SafetyViolation):
        assert_paper_cloud_safety(
            settings=bad_settings,
            paper_cloud=_paper_cloud(),
            exchange_client=None,
        )


@pytest.mark.parametrize(
    "field",
    [
        "live_trading_enabled",
        "right_tail_enabled",
        "llm_enabled",
        "exchange_live_order_enabled",
    ],
)
def test_refuses_when_settings_safety_flag_drifted(field: str):
    base = _settings()
    drifted = base.defaults.mode.model_copy(update={field: True})
    bad_defaults = base.defaults.model_copy(update={"mode": drifted})
    bad_settings = Settings(
        defaults=bad_defaults,
        risk=base.risk,
        strategy=base.strategy,
        project_root=base.project_root,
    )
    with pytest.raises(SafetyViolation):
        assert_paper_cloud_safety(
            settings=bad_settings,
            paper_cloud=_paper_cloud(),
            exchange_client=None,
        )


def test_refuses_when_paper_cloud_yaml_drifted_in_memory():
    """A paper_cloud config built directly with unsafe values is
    refused even though :class:`PaperCloudConfig.from_mapping` already
    rejects it. Guards against in-memory drift."""

    # We bypass the loader's validation by constructing a frozen
    # dataclass field-by-field via dataclasses.replace.
    safe = _paper_cloud()
    bad = replace(safe, llm_enabled=True)
    with pytest.raises(SafetyViolation):
        assert_paper_cloud_safety(
            settings=_settings(),
            paper_cloud=bad,
            exchange_client=None,
        )


def test_refuses_when_paper_cloud_real_order_enabled():
    safe = _paper_cloud()
    bad = replace(safe, real_order_enabled=True)
    with pytest.raises(SafetyViolation):
        assert_paper_cloud_safety(
            settings=_settings(),
            paper_cloud=bad,
            exchange_client=None,
        )


def test_safety_assertion_report_passed_only_when_all_true():
    report = SafetyAssertionReport(
        trading_mode_paper=True,
        live_trading_enabled_false=True,
        right_tail_enabled_false=True,
        llm_enabled_false=True,
        exchange_live_order_enabled_false=True,
        write_surfaces_refuse=True,
        paper_cloud_yaml_consistent=True,
        real_order_enabled_false=True,
    )
    assert report.passed is True
    not_safe = replace(report, write_surfaces_refuse=False)
    assert not_safe.passed is False
