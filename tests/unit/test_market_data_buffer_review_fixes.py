"""Phase 4 review fixes (PR #15 review).

Three follow-up checks requested before merge:

  1. ``snapshot()`` must support a throttle so Phase 5+ high-frequency
     callers do not bloat ``events.db``.
  2. ``BufferStats`` must expose a ``late_trades_dropped_total``
     counter so a misordered tape is observable at runtime.
  3. ``refresh_from_exchange()`` docstring + README must declare the
     Phase 4 boundary explicitly (no real network by default).

Tests #1 and #2 verify behaviour. Test #3 verifies the docstring
contract because the boundary is policy, not runtime behaviour.
"""

from __future__ import annotations

import sqlite3
from inspect import getsource

import pytest

from app.core.events import EventType
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.exchanges.models import RecentTrade, TradeSide
from app.market_data import MarketDataBuffer
from app.market_data.buffer import MarketDataBuffer as BufferClass
from app.market_data.models import MarketDataBufferConfig


T0 = 1_779_062_400_000


def trade(*, ts: int, qty: float = 1.0) -> RecentTrade:
    return RecentTrade(
        symbol="BTCUSDT",
        trade_id=f"t-{ts}-{qty}",
        timestamp=ts,
        price=100.0,
        qty=qty,
        side=TradeSide.BUY,
        is_buyer_maker=False,
    )


@pytest.fixture
def repo() -> EventRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    yield EventRepository(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Review item 1: snapshot() throttle
# ---------------------------------------------------------------------------
def test_default_emits_market_snapshot_event(repo):
    """Phase 4 default behaviour is preserved: a single snapshot
    appends one MARKET_SNAPSHOT event when ``emit_event`` is None."""
    buf = MarketDataBuffer(event_repo=repo)
    buf.track("BTCUSDT")
    buf.ingest_trade(trade(ts=T0))
    snap = buf.snapshot("BTCUSDT")
    assert snap.symbol == "BTCUSDT"
    snaps = repo.list_events(event_type=EventType.MARKET_SNAPSHOT)
    assert len(snaps) == 1
    assert buf.market_snapshot_events_emitted == 1
    assert buf.market_snapshot_events_skipped == 0


def test_explicit_emit_false_skips_event(repo):
    """Per-call ``emit_event=False`` overrides the config default."""
    buf = MarketDataBuffer(event_repo=repo)
    buf.track("BTCUSDT")
    buf.ingest_trade(trade(ts=T0))
    snap = buf.snapshot("BTCUSDT", emit_event=False)
    assert snap.symbol == "BTCUSDT"
    assert repo.list_events(event_type=EventType.MARKET_SNAPSHOT) == []
    assert buf.market_snapshot_events_emitted == 0
    assert buf.market_snapshot_events_skipped == 1
    assert buf.stats().market_snapshot_events_skipped == 1


def test_config_flag_disables_emit_by_default(repo):
    """Construct-time throttle: a high-frequency consumer can flip the
    config flag once and every default ``snapshot()`` call thereafter
    skips event emission."""
    cfg = MarketDataBufferConfig(market_snapshot_event_emit_enabled=False)
    buf = MarketDataBuffer(event_repo=repo, config=cfg)
    buf.track("BTCUSDT")
    buf.ingest_trade(trade(ts=T0))
    for _ in range(5):
        buf.snapshot("BTCUSDT")
    assert repo.list_events(event_type=EventType.MARKET_SNAPSHOT) == []
    assert buf.market_snapshot_events_emitted == 0
    assert buf.market_snapshot_events_skipped == 5


def test_config_flag_off_but_explicit_true_still_emits(repo):
    """Explicit per-call ``emit_event=True`` beats the config default
    when a downstream module needs an audit-trail entry on demand."""
    cfg = MarketDataBufferConfig(market_snapshot_event_emit_enabled=False)
    buf = MarketDataBuffer(event_repo=repo, config=cfg)
    buf.track("BTCUSDT")
    buf.ingest_trade(trade(ts=T0))
    buf.snapshot("BTCUSDT", emit_event=True)
    assert len(repo.list_events(event_type=EventType.MARKET_SNAPSHOT)) == 1
    assert buf.market_snapshot_events_emitted == 1


# ---------------------------------------------------------------------------
# Review item 2: late_trades_dropped_total observability
# ---------------------------------------------------------------------------
def test_late_trades_dropped_counter_starts_at_zero():
    buf = MarketDataBuffer()
    buf.track("BTCUSDT")
    buf.ingest_trade(trade(ts=T0))
    assert buf.late_trades_dropped_total == 0
    assert buf.stats().late_trades_dropped_total == 0


def test_late_trades_dropped_counter_increments_on_out_of_order_tape():
    """A trade whose bucket has already closed must be DROPPED (not
    back-filled - Spec section 14.2 forbids silent rewrites) AND the
    buffer must surface that fact in ``BufferStats`` so Phase 5 / 6
    monitoring can alert on it."""
    buf = MarketDataBuffer()
    buf.track("BTCUSDT")
    buf.ingest_trade(trade(ts=T0))
    buf.ingest_trade(trade(ts=T0 + 60_500))  # closes bar 0
    buf.ingest_trade(trade(ts=T0 + 30_000))  # late -> dropped from 1m AND 5m
    # The 1m and 5m candle builders both saw the late trade and both
    # incremented their dropped counters - the buffer aggregates them.
    assert buf.late_trades_dropped_total >= 1
    assert buf.stats().late_trades_dropped_total >= 1


def test_late_trades_dropped_counter_isolates_per_symbol_aggregate():
    buf = MarketDataBuffer()
    buf.track("BTCUSDT")
    buf.track("ETHUSDT")
    buf.ingest_trade(trade(ts=T0))
    buf.ingest_trade(trade(ts=T0 + 60_500))
    buf.ingest_trade(trade(ts=T0 + 30_000))  # one late trade for BTCUSDT
    snap_total = buf.late_trades_dropped_total
    assert snap_total >= 1
    # ETHUSDT received nothing late.
    eth_state = buf._symbols["ETHUSDT"]  # noqa: SLF001
    assert eth_state.candle_1m.dropped_late_trades == 0


# ---------------------------------------------------------------------------
# Review item 3: refresh_from_exchange docstring contract
# ---------------------------------------------------------------------------
def test_refresh_from_exchange_docstring_declares_phase4_boundary():
    """The Phase 4 boundary is policy, not runtime behaviour, so we
    pin it via the docstring. If a future PR removes the Phase 4
    wording the assertion fails and the reviewer knows to add the
    guarantee back somewhere visible (or to upgrade the boundary
    explicitly)."""
    src = getsource(BufferClass.refresh_from_exchange)
    text = src.lower()  # case-insensitive
    for required in (
        "mockexchangeclient",
        "fixture-driven",
        "phase 4 does not allow auto-connecting",
        "opt-in",
        "no api key",
        "no write surface",
        "must not depend on real network",
    ):
        assert required in text, (
            f"refresh_from_exchange docstring missing: {required!r}"
        )
