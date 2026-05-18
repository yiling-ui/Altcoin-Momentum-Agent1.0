"""Phase 4 - market-data value-object contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.market_data.models import (
    Bar,
    BarInterval,
    BufferStats,
    LiquidationEvent,
    LiquidationSide,
    MarketDataBufferConfig,
    MarketDataDegradedReason,
    MarketDataStalenessConfig,
)


def test_bar_interval_widths():
    assert BarInterval.M1.width_ms == 60_000
    assert BarInterval.M5.width_ms == 300_000


def test_bar_requires_close_after_open():
    with pytest.raises(ValidationError):
        Bar(
            symbol="BTCUSDT",
            interval=BarInterval.M1,
            open_ts=1_000_000,
            close_ts=1_000_000,  # equal -> rejected
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
        )


def test_bar_is_frozen_and_extra_forbid():
    bar = Bar(
        symbol="BTCUSDT",
        interval=BarInterval.M1,
        open_ts=1_000_000,
        close_ts=1_060_000,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
    )
    with pytest.raises(ValidationError):
        Bar(
            symbol="BTCUSDT",
            interval=BarInterval.M1,
            open_ts=1_000_000,
            close_ts=1_060_000,
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            extra_evil_field="no",  # extra=forbid
        )
    # frozen
    with pytest.raises(ValidationError):
        bar.close = 2.0  # type: ignore[misc]


def test_liquidation_event_round_trip():
    ev = LiquidationEvent(
        symbol="PEPEUSDT",
        timestamp=1,
        side=LiquidationSide.LONG,
        price=1.0,
        qty=10.0,
    )
    assert ev.side is LiquidationSide.LONG
    assert ev.notional is None


def test_market_data_buffer_config_defaults_match_spec():
    cfg = MarketDataBufferConfig()
    assert cfg.trades_window_1m_ms == 60_000
    assert cfg.trades_window_5m_ms == 300_000
    assert cfg.trades_window_15m_ms == 900_000
    assert cfg.atr_window_1m == 14
    assert cfg.atr_window_5m == 14
    # Staleness defaults are >= window widths so that "we have not yet
    # received any data" is the only thing that triggers staleness in
    # a freshly-fed buffer.
    s = cfg.staleness
    assert s.trades_max_silence_ms >= cfg.trades_window_1m_ms
    assert s.orderbook_max_silence_ms > 0
    assert s.oi_max_silence_ms > 0
    assert s.funding_max_silence_ms > 0


def test_staleness_config_is_frozen():
    s = MarketDataStalenessConfig()
    with pytest.raises(ValidationError):
        s.trades_max_silence_ms = 1  # type: ignore[misc]


def test_buffer_stats_defaults_are_zero():
    stats = BufferStats()
    assert stats.symbols_tracked == 0
    assert stats.symbols_degraded == 0
    assert stats.data_unreliable_events_emitted == 0
    assert stats.market_snapshot_events_emitted == 0
    assert stats.rest_ws_conflicts_total == 0


def test_degraded_reason_vocabulary():
    """Phase 4 ships exactly this set of reasons. Adding a reason is
    fine; removing one is a public-API break that tests must catch.
    """
    expected = {
        "never_initialised",
        "exchange_disconnected",
        "exchange_degraded",
        "trades_stale",
        "orderbook_stale",
        "oi_stale",
        "funding_stale",
        "rest_ws_conflict",
        "explicit_mark",
    }
    assert {r.value for r in MarketDataDegradedReason} == expected
