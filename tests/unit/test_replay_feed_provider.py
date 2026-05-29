"""Unit tests for Phase 11C.1D-D-C / PR96 / ReplayFeedProvider v0.

These tests are the safety contract for this PR. If any of them fails
the module is not safe to merge.

Hard safety boundary covered by these tests:

  - mode = paper
  - sandbox_only = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - telegram_outbound_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

The tests also assert that the new module:

  - does NOT import app.risk / app.execution / app.exchanges /
    app.telegram / app.config
  - does NOT pull any DeepSeek / LLM / Telegram / Binance / network
    transport
  - emits no forbidden trade / runtime-config / "live ready" field
  - is deterministic
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Mapping

import pytest

from app.sim import (
    FORBIDDEN_OUTPUT_FIELDS,
    REPLAY_FEED_PROVIDER_PHASE_NAME,
    DataQualityFlag,
    HistoricalKlineRecord,
    HistoricalMarketRecord,
    HistoricalMarketRecordType,
    HistoricalMarketStore,
    NoLookaheadViolation,
    NoLookaheadViolationReason,
    ReplayFeedBatch,
    ReplayFeedCursor,
    ReplayFeedDiagnostics,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
    SimulationClock,
    SymbolStatus,
    SymbolStatusRecord,
    TimeWallGuard,
    assert_no_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _walk_keys(payload: Any):
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_imported_modules(source_text: str) -> set:
    tree = ast.parse(source_text)
    mods: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def _collect_code_identifiers(source_text: str) -> set:
    tree = ast.parse(source_text)
    out: set = set()

    def attr_chain(n):
        parts: List[str] = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            chain = attr_chain(node)
            if chain:
                out.add(chain)
    return out


def _make_kline(
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    open_time: datetime = None,
    available_at: datetime = None,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 12.34,
    record_id: str = None,
    data_quality_flags=(),
    source: str = "binance_public",
) -> HistoricalKlineRecord:
    if open_time is None:
        open_time = _T0
    seconds = 60 if interval == "1m" else 300
    if available_at is None:
        available_at = open_time + timedelta(seconds=seconds)
    return HistoricalKlineRecord(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        available_at=available_at,
        source=source,
        record_id=record_id,
        data_quality_flags=tuple(data_quality_flags),
    )


def _make_funding(
    *,
    record_id: str,
    symbol: str = "BTCUSDT",
    event_time: datetime = None,
    available_at: datetime = None,
    payload: Mapping[str, Any] = None,
    data_quality_flags=(),
) -> HistoricalMarketRecord:
    if event_time is None:
        event_time = _T0
    if available_at is None:
        available_at = event_time
    if payload is None:
        payload = {"funding_rate": 0.0001}
    return HistoricalMarketRecord(
        record_id=record_id,
        record_type=HistoricalMarketRecordType.FUNDING_RATE,
        symbol=symbol,
        event_time=event_time,
        available_at=available_at,
        source="binance_public",
        payload=payload,
        data_quality_flags=tuple(data_quality_flags),
    )


def _make_symbol_status(
    *,
    symbol: str,
    listed_at: datetime,
    available_at: datetime = None,
    delisted_at: datetime = None,
    status: str = SymbolStatus.TRADING,
    market_type: str = "PERP",
    record_id: str = None,
    event_time: datetime = None,
) -> SymbolStatusRecord:
    if available_at is None:
        available_at = listed_at
    return SymbolStatusRecord(
        symbol=symbol,
        market_type=market_type,
        listed_at=listed_at,
        status=status,
        available_at=available_at,
        delisted_at=delisted_at,
        min_notional=10.0,
        tick_size=0.01,
        step_size=0.001,
        contract_type="USDT_PERP",
        source="binance_public",
        record_id=record_id,
        event_time=event_time,
    )


def _make_provider(
    *,
    store: HistoricalMarketStore,
    start_time: datetime = None,
    end_time: datetime = None,
    step_interval: timedelta = None,
    include_record_types=None,
    symbols=None,
    allow_reemit: bool = False,
    include_asof_universe: bool = True,
    monotonic_forward_only: bool = True,
) -> ReplayFeedProvider:
    if start_time is None:
        start_time = _T0
    if end_time is None:
        end_time = _T0 + timedelta(minutes=30)
    if step_interval is None:
        step_interval = timedelta(minutes=1)
    clock = SimulationClock(
        start_time_utc=start_time,
        end_time_utc=end_time,
        monotonic_forward_only=monotonic_forward_only,
    )
    config_kwargs: dict = {
        "start_time": start_time,
        "end_time": end_time,
        "step_interval": step_interval,
        "allow_reemit": allow_reemit,
        "include_asof_universe": include_asof_universe,
    }
    if include_record_types is not None:
        config_kwargs["include_record_types"] = tuple(include_record_types)
    if symbols is not None:
        config_kwargs["symbols"] = tuple(symbols)
    config = ReplayFeedProviderConfig(**config_kwargs)
    return ReplayFeedProvider(store=store, clock=clock, config=config)


# ---------------------------------------------------------------------------
# 1. next_batch emits only records available at simulated_time
# ---------------------------------------------------------------------------


def test_next_batch_emits_only_records_available_at_simulated_time():
    store = HistoricalMarketStore()
    # Funding records at T0+30s (available), T0+90s (available after one
    # step), T0+150s (not available after one step).
    store.add_records(
        [
            _make_funding(
                record_id="f0",
                event_time=_T0 + timedelta(seconds=30),
                available_at=_T0 + timedelta(seconds=30),
            ),
            _make_funding(
                record_id="f1",
                event_time=_T0 + timedelta(seconds=90),
                available_at=_T0 + timedelta(seconds=90),
            ),
            _make_funding(
                record_id="f2",
                event_time=_T0 + timedelta(seconds=150),
                available_at=_T0 + timedelta(seconds=150),
            ),
        ]
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    batch1 = provider.next_batch()
    assert batch1.simulated_time == _T0 + timedelta(minutes=1)
    rid_set = {r.record_id for r in batch1.records}
    assert rid_set == {"f0"}  # only f0 has available_at <= T0+1m
    assert provider.clock.now() == _T0 + timedelta(minutes=1)
    batch2 = provider.next_batch()
    assert batch2.simulated_time == _T0 + timedelta(minutes=2)
    rid_set2 = {r.record_id for r in batch2.records}
    assert rid_set2 == {"f1"}  # f0 dedup'd; f1 newly visible


# ---------------------------------------------------------------------------
# 2. future records are rejected / diagnosed, not emitted
# ---------------------------------------------------------------------------


def test_future_records_are_rejected_and_diagnosed():
    store = HistoricalMarketStore()
    sim_target = _T0 + timedelta(minutes=1)
    store.add_records(
        [
            _make_funding(
                record_id="f_past",
                event_time=_T0,
                available_at=_T0,
            ),
            _make_funding(
                record_id="f_future_1",
                event_time=sim_target + timedelta(seconds=1),
                available_at=sim_target + timedelta(seconds=1),
            ),
            _make_funding(
                record_id="f_future_2",
                event_time=sim_target + timedelta(minutes=5),
                available_at=sim_target + timedelta(minutes=5),
            ),
        ]
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    batch = provider.next_batch()
    rid_set = {r.record_id for r in batch.records}
    assert rid_set == {"f_past"}
    assert "f_future_1" not in rid_set
    assert "f_future_2" not in rid_set
    diag = provider.get_diagnostics()
    # PR104 semantics: a not-yet-available record is *withheld*, not
    # emitted, and withholding it is NOT a no-lookahead violation by
    # itself (Constitution §5, clarified). The provider therefore does
    # NOT manufacture a future-record rejection diagnostic / violation
    # on every step - this is the fix for the per-step diagnostics
    # explosion that drove RES to ~16 GB on a real 7-day store. A
    # genuine violation would only arise if a future record were
    # actually exposed to the consumer (it never is here).
    assert diag.future_records_rejected_count == 0
    assert diag.violations == []
    assert batch.violations == ()
    # Advancing the clock to the future records makes them visible and
    # they are emitted exactly once - still with zero violations.
    b2 = provider.batch_at(sim_target + timedelta(seconds=1))
    assert "f_future_1" in {r.record_id for r in b2.records}
    b3 = provider.batch_at(sim_target + timedelta(minutes=5))
    assert "f_future_2" in {r.record_id for r in b3.records}
    assert provider.get_diagnostics().violations == []


# ---------------------------------------------------------------------------
# 3. records are emitted in deterministic order
# ---------------------------------------------------------------------------


def test_records_are_emitted_in_deterministic_order():
    # Build two stores with records inserted in different orders; the
    # batch.records sequence must be identical.
    def _build_store(order):
        s = HistoricalMarketStore()
        recs = [
            _make_funding(
                record_id="z",
                event_time=_T0 + timedelta(seconds=30),
                available_at=_T0 + timedelta(seconds=30),
            ),
            _make_funding(
                record_id="a",
                event_time=_T0 + timedelta(seconds=10),
                available_at=_T0 + timedelta(seconds=10),
            ),
            _make_funding(
                record_id="m",
                event_time=_T0 + timedelta(seconds=20),
                available_at=_T0 + timedelta(seconds=20),
            ),
        ]
        for i in order:
            s.add_record(recs[i])
        return s

    store_a = _build_store([0, 1, 2])
    store_b = _build_store([2, 1, 0])
    p_a = _make_provider(store=store_a, step_interval=timedelta(minutes=1))
    p_b = _make_provider(store=store_b, step_interval=timedelta(minutes=1))
    b_a = p_a.next_batch()
    b_b = p_b.next_batch()
    assert [r.record_id for r in b_a.records] == ["a", "m", "z"]
    assert [r.record_id for r in b_b.records] == ["a", "m", "z"]


# ---------------------------------------------------------------------------
# 4. provider advances SimulationClock forward by step_interval
# ---------------------------------------------------------------------------


def test_provider_advances_simulation_clock_forward_by_step_interval():
    store = HistoricalMarketStore()
    provider = _make_provider(
        store=store,
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=10),
        step_interval=timedelta(minutes=2),
    )
    # Initial state: cursor at start_time, clock at start_time.
    assert provider.clock.now() == _T0
    assert provider.cursor.current_time == _T0
    # next_batch advances by step_interval each call.
    b1 = provider.next_batch()
    assert provider.clock.now() == _T0 + timedelta(minutes=2)
    assert b1.simulated_time == _T0 + timedelta(minutes=2)
    b2 = provider.next_batch()
    assert provider.clock.now() == _T0 + timedelta(minutes=4)
    assert b2.simulated_time == _T0 + timedelta(minutes=4)
    # advance_and_get_batch with explicit delta also advances.
    b3 = provider.advance_and_get_batch(timedelta(minutes=3))
    assert provider.clock.now() == _T0 + timedelta(minutes=7)
    assert b3.simulated_time == _T0 + timedelta(minutes=7)
    # batch_at advances to a specific simulated_time.
    b4 = provider.batch_at(_T0 + timedelta(minutes=10))
    assert provider.clock.now() == _T0 + timedelta(minutes=10)
    assert b4.replay_complete is True
    assert provider.cursor.replay_complete is True


# ---------------------------------------------------------------------------
# 5. provider cannot move backward
# ---------------------------------------------------------------------------


def test_provider_cannot_move_backward():
    store = HistoricalMarketStore()
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    provider.next_batch()  # current_time = T0+1m
    with pytest.raises(ValueError):
        provider.batch_at(_T0)  # T0 < T0+1m
    with pytest.raises(ValueError):
        provider.advance_and_get_batch(-timedelta(seconds=1))
    # Cursor itself rejects backward motion.
    with pytest.raises(ValueError):
        provider.cursor.advance_to(_T0)
    # get_asof_universe also forbids backward queries.
    with pytest.raises(ValueError):
        provider.get_asof_universe(_T0)


# ---------------------------------------------------------------------------
# 6. duplicate records skipped by default
# ---------------------------------------------------------------------------


def test_duplicate_records_skipped_by_default():
    store = HistoricalMarketStore()
    store.add_records(
        [
            _make_funding(
                record_id="f0",
                event_time=_T0 + timedelta(seconds=10),
                available_at=_T0 + timedelta(seconds=10),
            ),
            _make_funding(
                record_id="f1",
                event_time=_T0 + timedelta(seconds=70),
                available_at=_T0 + timedelta(seconds=70),
            ),
        ]
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    b1 = provider.next_batch()  # T0+1m: f0
    rids1 = {r.record_id for r in b1.records}
    assert rids1 == {"f0"}
    b2 = provider.next_batch()  # T0+2m: f1 only (f0 already emitted)
    rids2 = {r.record_id for r in b2.records}
    assert rids2 == {"f1"}
    # Even though f0 still has available_at <= T0+2m, it is NOT
    # re-emitted. PR104: the forward-only availability cursor visits
    # each record position exactly once, so a record emitted at an
    # earlier tick is never re-scanned (no full re-scan per step).
    assert "f0" not in rids2
    assert "f0" in provider.cursor.emitted_record_ids
    assert "f1" in provider.cursor.emitted_record_ids
    # No genuine duplicate record_ids in the store => no duplicate skips.
    diag = provider.get_diagnostics()
    assert diag.duplicate_record_skipped_count == 0


# ---------------------------------------------------------------------------
# 7. allow_reemit=true can re-emit deterministically
# ---------------------------------------------------------------------------


def test_allow_reemit_re_emits_deterministically():
    store = HistoricalMarketStore()
    store.add_records(
        [
            _make_funding(
                record_id="f0",
                event_time=_T0 + timedelta(seconds=10),
                available_at=_T0 + timedelta(seconds=10),
            ),
            _make_funding(
                record_id="f1",
                event_time=_T0 + timedelta(seconds=70),
                available_at=_T0 + timedelta(seconds=70),
            ),
        ]
    )
    provider = _make_provider(
        store=store,
        step_interval=timedelta(minutes=1),
        allow_reemit=True,
    )
    b1 = provider.next_batch()  # T0+1m: f0
    rids1 = {r.record_id for r in b1.records}
    assert rids1 == {"f0"}
    b2 = provider.next_batch()  # T0+2m: f0 + f1 (re-emitted)
    rids2 = {r.record_id for r in b2.records}
    assert rids2 == {"f0", "f1"}
    diag = provider.get_diagnostics()
    assert diag.duplicate_record_skipped_count == 0


# ---------------------------------------------------------------------------
# 8. 1m unclosed candle final OHLCV is not emitted before close
# ---------------------------------------------------------------------------


def test_1m_unclosed_candle_final_ohlcv_not_emitted_before_close():
    store = HistoricalMarketStore()
    # 1m kline opening at T0+5m, closing at T0+6m. available_at == close_time.
    k = _make_kline(
        symbol="BTCUSDT",
        interval="1m",
        open_time=_T0 + timedelta(minutes=5),
        available_at=_T0 + timedelta(minutes=6),
        record_id="k_1m",
    )
    store.add_record(k)
    provider = _make_provider(
        store=store,
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=15),
        step_interval=timedelta(minutes=1),
    )
    # Advance just before close: simulated_time = T0+5m30s. Kline NOT
    # emitted; future-rejected diagnostic recorded.
    batch_before = provider.batch_at(_T0 + timedelta(minutes=5, seconds=30))
    assert batch_before.klines_1m == ()
    # Advance to the close instant: simulated_time = T0+6m. Now kline
    # IS emitted (available_at == simulated_time, candle is closed).
    batch_at_close = provider.batch_at(_T0 + timedelta(minutes=6))
    assert len(batch_at_close.klines_1m) == 1
    assert batch_at_close.klines_1m[0].record_id == "k_1m"


# ---------------------------------------------------------------------------
# 9. 5m unclosed candle final OHLCV is not emitted before close
# ---------------------------------------------------------------------------


def test_5m_unclosed_candle_final_ohlcv_not_emitted_before_close():
    store = HistoricalMarketStore()
    # 5m kline opening at T0+5m, closing at T0+10m.
    k = _make_kline(
        symbol="BTCUSDT",
        interval="5m",
        open_time=_T0 + timedelta(minutes=5),
        available_at=_T0 + timedelta(minutes=10),
        record_id="k_5m",
    )
    store.add_record(k)
    provider = _make_provider(
        store=store,
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=20),
        step_interval=timedelta(minutes=1),
    )
    # Just before close: T0+9m59s. NOT emitted.
    batch_before = provider.batch_at(
        _T0 + timedelta(minutes=9, seconds=59)
    )
    assert batch_before.klines_5m == ()
    # At close: T0+10m. Emitted.
    batch_at_close = provider.batch_at(_T0 + timedelta(minutes=10))
    assert len(batch_at_close.klines_5m) == 1
    assert batch_at_close.klines_5m[0].record_id == "k_5m"


# ---------------------------------------------------------------------------
# 10. as-of universe included and obeys listed_at / delisted_at /
#     available_at
# ---------------------------------------------------------------------------


def test_asof_universe_included_and_obeys_listed_delisted_available_at():
    store = HistoricalMarketStore()
    # DEADUSDT is initially TRADING, then receives a DELISTED record
    # whose available_at is in the future.
    store.add_records(
        [
            _make_symbol_status(
                symbol="BTCUSDT",
                listed_at=_T0 - timedelta(days=30),
                available_at=_T0 - timedelta(days=30),
                status=SymbolStatus.TRADING,
                record_id="symstat_btc_active",
            ),
            _make_symbol_status(
                symbol="LATEUSDT",
                # listed_at in the future relative to the first batch
                listed_at=_T0 + timedelta(minutes=2),
                available_at=_T0 + timedelta(minutes=2),
                status=SymbolStatus.TRADING,
                record_id="symstat_late_active",
            ),
            _make_symbol_status(
                symbol="DEADUSDT",
                listed_at=_T0 - timedelta(days=60),
                available_at=_T0 - timedelta(days=60),
                status=SymbolStatus.TRADING,
                record_id="symstat_dead_initial",
            ),
            _make_symbol_status(
                symbol="DEADUSDT",
                listed_at=_T0 - timedelta(days=60),
                available_at=_T0 + timedelta(minutes=5),
                delisted_at=_T0 + timedelta(minutes=5),
                status=SymbolStatus.DELISTED,
                event_time=_T0 + timedelta(minutes=5),
                record_id="symstat_dead_delisted",
            ),
        ]
    )
    provider = _make_provider(
        store=store,
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=20),
        step_interval=timedelta(minutes=1),
    )
    batch_t1 = provider.next_batch()  # T0+1m
    universe_t1 = {s.symbol for s in batch_t1.asof_universe}
    # BTCUSDT is in (listed and tradable). LATEUSDT not yet listed.
    # DEADUSDT IS in (TRADING record visible, DELISTED record not yet
    # available).
    assert "BTCUSDT" in universe_t1
    assert "LATEUSDT" not in universe_t1
    assert "DEADUSDT" in universe_t1
    # Advance past late listing.
    batch_t3 = provider.batch_at(_T0 + timedelta(minutes=3))
    universe_t3 = {s.symbol for s in batch_t3.asof_universe}
    assert "BTCUSDT" in universe_t3
    assert "LATEUSDT" in universe_t3
    assert "DEADUSDT" in universe_t3
    # Advance past delisting. The DELISTED record is now visible,
    # supersedes the TRADING record (later event_time), and its
    # delisted_at <= simulated_time, so DEADUSDT is excluded.
    batch_t6 = provider.batch_at(_T0 + timedelta(minutes=6))
    universe_t6 = {s.symbol for s in batch_t6.asof_universe}
    assert "BTCUSDT" in universe_t6
    assert "LATEUSDT" in universe_t6
    assert "DEADUSDT" not in universe_t6


# ---------------------------------------------------------------------------
# 11. diagnostics count future rejected records
# ---------------------------------------------------------------------------


def test_diagnostics_count_future_rejected_records():
    store = HistoricalMarketStore()
    # Three future records and one past record.
    for i in range(3):
        store.add_record(
            _make_funding(
                record_id=f"f_future_{i}",
                event_time=_T0 + timedelta(minutes=20 + i),
                available_at=_T0 + timedelta(minutes=20 + i),
            )
        )
    store.add_record(
        _make_funding(
            record_id="f_past",
            event_time=_T0,
            available_at=_T0,
        )
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    batch = provider.next_batch()  # T0+1m
    diag = provider.get_diagnostics()
    # PR104: future records are withheld silently. No per-step rejection
    # diagnostic / violation is manufactured (the old behaviour produced
    # one violation per future record per tick => O(N x steps) blow-up).
    assert diag.future_records_rejected_count == 0
    assert diag.violations == []
    assert "f_past" in {r.record_id for r in batch.records}
    # As the clock reaches them, the future records become visible and
    # are emitted exactly once, still without any violation.
    b2 = provider.batch_at(_T0 + timedelta(minutes=21))
    seen = {r.record_id for r in b2.records}
    assert "f_future_0" in seen  # available_at T0+20m
    assert "f_future_1" in seen  # available_at T0+21m
    assert provider.get_diagnostics().violations == []


# ---------------------------------------------------------------------------
# 12. diagnostics preserve NoLookaheadViolation objects
# ---------------------------------------------------------------------------


def test_diagnostics_preserve_no_lookahead_violation_objects():
    store = HistoricalMarketStore()
    store.add_record(
        _make_funding(
            record_id="f_future",
            event_time=_T0 + timedelta(minutes=10),
            available_at=_T0 + timedelta(minutes=10),
        )
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    provider.next_batch()
    diag = provider.get_diagnostics()
    # PR104: a withheld future record is not a violation, so a normal
    # forward step records none (no per-step diagnostics explosion).
    assert diag.violations == []
    # But the diagnostics structure still faithfully *preserves* any
    # genuine NoLookaheadViolation it is handed (e.g. one produced by
    # the TimeWallGuard), re-pinning the safety flags on serialisation.
    tw = TimeWallGuard()
    v = tw.validate_no_lookahead(
        {
            "record_id": "fut",
            "available_at": _T0 + timedelta(minutes=5),
            "event_time": _T0,
        },
        _T0,
    )
    assert v is not None
    diag2 = ReplayFeedDiagnostics()
    diag2.record_violation(v)
    assert len(diag2.violations) >= 1
    for vv in diag2.violations:
        assert isinstance(vv, NoLookaheadViolation)
        assert (
            vv.reason in NoLookaheadViolationReason.ALLOWED
        ), f"unknown reason {vv.reason}"
        # Each violation is JSON-serialisable and re-pins safety flags.
        d = vv.to_dict()
        assert d["phase_12_forbidden"] is True
        assert d["auto_tuning_allowed"] is False
        assert d["trade_authority"] is False


# ---------------------------------------------------------------------------
# 13. missing available_at creates violation
# ---------------------------------------------------------------------------


def test_missing_available_at_creates_violation():
    # ReplayFeedDiagnostics correctly classifies a MISSING_AVAILABLE_AT
    # violation (produced by TimeWallGuard when a Mapping-shape record
    # has no available_at).
    tw = TimeWallGuard()
    bad_record = {
        "record_id": "no_avail",
        "symbol": "BTCUSDT",
        "event_time": _T0,
        # NOTE: no available_at
    }
    v = tw.validate_no_lookahead(bad_record, _T0)
    assert v is not None
    assert v.reason == NoLookaheadViolationReason.MISSING_AVAILABLE_AT
    diag = ReplayFeedDiagnostics()
    diag.record_violation(v)
    assert diag.missing_available_at_count == 1
    assert diag.violations == [v]
    assert diag.future_records_rejected_count == 0
    # Symmetry: a FUTURE_AVAILABLE_AT violation increments only the
    # future counter.
    bad_future = {
        "record_id": "fut",
        "available_at": _T0 + timedelta(minutes=5),
        "event_time": _T0,
    }
    v_future = tw.validate_no_lookahead(bad_future, _T0)
    diag.record_violation(v_future)
    assert diag.future_records_rejected_count == 1
    assert diag.missing_available_at_count == 1
    # Unclosed-candle violation goes into its own counter.
    v_unclosed = tw.make_unclosed_candle_field_access_violation(
        simulated_time=_T0,
        field_name="close",
        candle_open_time=_T0,
        interval="1m",
        record_id="k_open",
        symbol="BTCUSDT",
        source="test",
    )
    diag.record_violation(v_unclosed)
    assert diag.unclosed_candle_violation_count == 1


# ---------------------------------------------------------------------------
# 14. batch is JSON serializable
# ---------------------------------------------------------------------------


def test_batch_is_json_serializable():
    store = HistoricalMarketStore()
    store.add_records(
        [
            _make_funding(
                record_id="f0",
                event_time=_T0,
                available_at=_T0,
            ),
            _make_kline(
                symbol="BTCUSDT",
                interval="1m",
                open_time=_T0,
                record_id="k0",
            ),
            _make_symbol_status(
                symbol="BTCUSDT",
                listed_at=_T0,
                available_at=_T0,
                record_id="sym_btc",
            ),
        ]
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    batch = provider.next_batch()
    payload = batch.to_dict()
    text = json.dumps(payload, sort_keys=True)
    round_tripped = json.loads(text)
    assert round_tripped["phase_12_forbidden"] is True
    assert round_tripped["auto_tuning_allowed"] is False
    assert round_tripped["trade_authority"] is False
    assert isinstance(round_tripped["records"], list)
    assert isinstance(round_tripped["asof_universe"], list)
    # Diagnostics, cursor, config also serialise.
    json.dumps(provider.get_diagnostics().to_dict(), sort_keys=True)
    json.dumps(provider.cursor.to_dict(), sort_keys=True)
    json.dumps(provider.config.to_dict(), sort_keys=True)
    json.dumps(provider.to_dict(), sort_keys=True)
    json.dumps(provider.safety_payload(), sort_keys=True)


# ---------------------------------------------------------------------------
# 15. phase_12_forbidden=true on every safety payload
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_in_every_safety_payload():
    store = HistoricalMarketStore()
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    assert provider.phase_12_forbidden is True
    assert provider.safety_payload()["phase_12_forbidden"] is True
    assert provider.to_dict()["phase_12_forbidden"] is True
    assert provider.config.to_dict()["phase_12_forbidden"] is True
    assert provider.cursor.to_dict()["phase_12_forbidden"] is True
    assert provider.diagnostics.to_dict()["phase_12_forbidden"] is True
    batch = provider.next_batch()
    assert batch.phase_12_forbidden is True
    assert batch.to_dict()["phase_12_forbidden"] is True
    # The literal "Phase 12" must NOT appear as a destination in the
    # phase identifier.
    assert "Phase 12" not in REPLAY_FEED_PROVIDER_PHASE_NAME


# ---------------------------------------------------------------------------
# 16. auto_tuning_allowed=false on every safety payload
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_in_every_safety_payload():
    store = HistoricalMarketStore()
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    assert provider.auto_tuning_allowed is False
    payload = provider.safety_payload()
    assert payload["auto_tuning_allowed"] is False
    assert provider.to_dict()["auto_tuning_allowed"] is False
    assert provider.config.to_dict()["auto_tuning_allowed"] is False
    assert provider.cursor.to_dict()["auto_tuning_allowed"] is False
    assert provider.diagnostics.to_dict()["auto_tuning_allowed"] is False
    batch = provider.next_batch()
    assert batch.auto_tuning_allowed is False
    assert batch.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 17. trade_authority=false on every safety payload
# ---------------------------------------------------------------------------


def test_trade_authority_false_in_every_safety_payload():
    store = HistoricalMarketStore()
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    assert provider.trade_authority is False
    assert provider.ai_trade_authority is False
    payload = provider.safety_payload()
    assert payload["trade_authority"] is False
    assert payload["ai_trade_authority"] is False
    batch = provider.next_batch()
    assert batch.trade_authority is False
    bd = batch.to_dict()
    assert bd["trade_authority"] is False
    assert bd["ai_trade_authority"] is False
    # No public method on the provider / batch / cursor / diagnostics /
    # config exposes a trade verb.
    forbidden_verbs = {
        "buy",
        "sell",
        "place_order",
        "submit_order",
        "long",
        "short",
        "open_position",
        "close_position",
        "set_leverage",
        "set_stop",
        "set_target",
        "apply_change",
        "deploy",
        "enable_live",
    }
    for inst in (
        provider,
        batch,
        provider.cursor,
        provider.diagnostics,
        provider.config,
    ):
        public = {n for n in dir(inst) if not n.startswith("_")}
        assert public.isdisjoint(forbidden_verbs), (
            f"{inst!r} exposes trade verbs: "
            f"{public & forbidden_verbs}"
        )


# ---------------------------------------------------------------------------
# 18. forbidden fields absent from serialized outputs
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_in_serialized_outputs():
    store = HistoricalMarketStore()
    store.add_records(
        [
            _make_funding(
                record_id="f0", event_time=_T0, available_at=_T0
            ),
            _make_kline(
                symbol="BTCUSDT",
                interval="1m",
                open_time=_T0,
                record_id="k0",
            ),
            _make_symbol_status(
                symbol="BTCUSDT",
                listed_at=_T0,
                available_at=_T0,
                record_id="sym_btc",
            ),
        ]
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    batch = provider.next_batch()
    payloads = [
        batch.to_dict(),
        provider.to_dict(),
        provider.safety_payload(),
        provider.config.to_dict(),
        provider.cursor.to_dict(),
        provider.diagnostics.to_dict(),
    ]
    for p in payloads:
        assert_no_forbidden_fields(p)
        keys = set(_walk_keys(p))
        assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS), (
            f"forbidden field present: "
            f"{keys & FORBIDDEN_OUTPUT_FIELDS}"
        )
    # Hostile payload smuggled through HistoricalMarketRecord.payload
    # and surfaced via the provider must be rejected at construction
    # (already covered by PR95 tests, but reasserted here).
    with pytest.raises(ValueError):
        HistoricalMarketRecord(
            record_id="bad",
            record_type=HistoricalMarketRecordType.FUNDING_RATE,
            symbol="BTCUSDT",
            event_time=_T0,
            available_at=_T0,
            payload={"runtime_config_patch": {"x": 1}},
        )


# ---------------------------------------------------------------------------
# 19. module does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports_in_module_or_init():
    root = _project_root()
    init_path = root / "app" / "sim" / "__init__.py"
    rfp_path = root / "app" / "sim" / "replay_feed_provider.py"

    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in (init_path, rfp_path):
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            for bad in forbidden_prefixes:
                assert not mod.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
        idents = _collect_code_identifiers(src)
        for ident in idents:
            for bad in forbidden_prefixes:
                assert not ident.startswith(bad), (
                    f"{path} references forbidden identifier {ident!r}"
                )
    # Importing app.sim does NOT pull any forbidden module into
    # sys.modules.
    before = set(sys.modules)
    importlib.import_module("app.sim")
    importlib.import_module("app.sim.replay_feed_provider")
    new = set(sys.modules) - before
    for nm in new:
        for bad in forbidden_prefixes:
            assert not nm.startswith(bad), (
                f"importing app.sim pulled forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 20. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_llm_telegram_binance_or_network_path():
    root = _project_root()
    files = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "replay_feed_provider.py",
    ]
    forbidden_module_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        "telegram",
        "binance",
        "ccxt",
        "websocket",
        "websockets",
        "httpx",
        "aiohttp",
        "requests",
        "urllib.request",
        "http.client",
        "grpc",
        "boto3",
        "socket",
    )
    forbidden_identifier_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        "telegram",
        "binance",
        "ccxt",
        "websocket",
        "httpx",
        "aiohttp",
        "requests.get",
        "requests.post",
        "urllib.request",
        "socket.connect",
        "socket.create_connection",
    )
    for path in files:
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            low = mod.lower()
            for bad in forbidden_module_prefixes:
                assert not low.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
        idents = _collect_code_identifiers(src)
        for ident in idents:
            low = ident.lower()
            for bad in forbidden_identifier_prefixes:
                assert not low.startswith(bad), (
                    f"{path} references forbidden code identifier "
                    f"{ident!r}"
                )
    # Reload doesn't pull any forbidden module.
    pre = set(sys.modules)
    importlib.import_module("app.sim.replay_feed_provider")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), (
                f"unexpected import: {nm}"
            )


# ---------------------------------------------------------------------------
# 21. deterministic output from same store / clock / config
# ---------------------------------------------------------------------------


def test_deterministic_output_from_same_store_clock_config():
    def _build_store():
        s = HistoricalMarketStore()
        s.add_records(
            [
                _make_funding(
                    record_id="f0",
                    event_time=_T0 + timedelta(seconds=10),
                    available_at=_T0 + timedelta(seconds=10),
                ),
                _make_funding(
                    record_id="f1",
                    event_time=_T0 + timedelta(seconds=70),
                    available_at=_T0 + timedelta(seconds=70),
                ),
                _make_kline(
                    symbol="BTCUSDT",
                    interval="1m",
                    open_time=_T0,
                    record_id="k0",
                ),
                _make_symbol_status(
                    symbol="BTCUSDT",
                    listed_at=_T0 - timedelta(days=1),
                    available_at=_T0 - timedelta(days=1),
                    record_id="sym_btc",
                ),
            ]
        )
        return s

    def _drive(provider, n):
        return [provider.next_batch().to_dict() for _ in range(n)]

    p_a = _make_provider(
        store=_build_store(),
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=10),
        step_interval=timedelta(minutes=1),
    )
    p_b = _make_provider(
        store=_build_store(),
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=10),
        step_interval=timedelta(minutes=1),
    )
    out_a = _drive(p_a, 5)
    out_b = _drive(p_b, 5)
    # The batch_id, simulated_time, sorted records, asof_universe,
    # diagnostics counters, and violations are byte-identical.
    assert out_a == out_b


# ---------------------------------------------------------------------------
# Extra: ReplayFeedProviderConfig validation
# ---------------------------------------------------------------------------


def test_replay_feed_provider_config_validation():
    # Naive datetime rejected.
    with pytest.raises((ValueError, TypeError)):
        ReplayFeedProviderConfig(
            start_time=datetime(2026, 1, 1, 12, 0, 0),
            end_time=_T0 + timedelta(hours=1),
            step_interval=timedelta(minutes=1),
        )
    # end_time < start_time rejected.
    with pytest.raises(ValueError):
        ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 - timedelta(seconds=1),
            step_interval=timedelta(minutes=1),
        )
    # step_interval = 0 rejected.
    with pytest.raises(ValueError):
        ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=1),
            step_interval=timedelta(0),
        )
    # negative step_interval rejected.
    with pytest.raises(ValueError):
        ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=1),
            step_interval=timedelta(seconds=-1),
        )
    # Unknown record type rejected.
    with pytest.raises(ValueError):
        ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=1),
            step_interval=timedelta(minutes=1),
            include_record_types=("NOT_A_TYPE",),
        )
    # Empty include_record_types rejected.
    with pytest.raises(ValueError):
        ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=1),
            step_interval=timedelta(minutes=1),
            include_record_types=(),
        )
    # Duplicates rejected.
    with pytest.raises(ValueError):
        ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=1),
            step_interval=timedelta(minutes=1),
            include_record_types=(
                HistoricalMarketRecordType.KLINE_1M,
                HistoricalMarketRecordType.KLINE_1M,
            ),
        )
    # symbols must be non-empty when supplied.
    with pytest.raises(ValueError):
        ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=1),
            step_interval=timedelta(minutes=1),
            symbols=(),
        )
    # Interval string for step_interval works.
    cfg = ReplayFeedProviderConfig(
        start_time=_T0,
        end_time=_T0 + timedelta(hours=1),
        step_interval="5m",
    )
    assert cfg.step_interval == timedelta(minutes=5)
    # Numeric seconds for step_interval works.
    cfg2 = ReplayFeedProviderConfig(
        start_time=_T0,
        end_time=_T0 + timedelta(hours=1),
        step_interval=60,
    )
    assert cfg2.step_interval == timedelta(seconds=60)


# ---------------------------------------------------------------------------
# Extra: provider replay_complete + StopIteration
# ---------------------------------------------------------------------------


def test_provider_replay_complete_and_stopiteration():
    store = HistoricalMarketStore()
    provider = _make_provider(
        store=store,
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=2),
        step_interval=timedelta(minutes=1),
    )
    b1 = provider.next_batch()  # T0+1m
    assert b1.replay_complete is False
    b2 = provider.next_batch()  # T0+2m == end_time
    assert b2.replay_complete is True
    assert provider.replay_complete is True
    with pytest.raises(StopIteration):
        provider.next_batch()


# ---------------------------------------------------------------------------
# Extra: symbol filter restricts batch contents
# ---------------------------------------------------------------------------


def test_symbol_filter_restricts_batch_contents():
    store = HistoricalMarketStore()
    store.add_records(
        [
            _make_funding(
                record_id="f_btc",
                symbol="BTCUSDT",
                event_time=_T0,
                available_at=_T0,
            ),
            _make_funding(
                record_id="f_eth",
                symbol="ETHUSDT",
                event_time=_T0,
                available_at=_T0,
            ),
        ]
    )
    provider = _make_provider(
        store=store,
        step_interval=timedelta(minutes=1),
        symbols=("BTCUSDT",),
    )
    batch = provider.next_batch()
    rids = {r.record_id for r in batch.records}
    assert rids == {"f_btc"}


# ---------------------------------------------------------------------------
# Extra: reset() requires monotonic_forward_only=False on the clock
# ---------------------------------------------------------------------------


def test_reset_requires_non_monotonic_clock():
    store = HistoricalMarketStore()
    # Default clock is monotonic_forward_only=True; reset must refuse.
    p1 = _make_provider(store=store, step_interval=timedelta(minutes=1))
    p1.next_batch()
    with pytest.raises(ValueError):
        p1.reset()
    # With monotonic_forward_only=False, reset works deterministically.
    p2 = _make_provider(
        store=store,
        step_interval=timedelta(minutes=1),
        monotonic_forward_only=False,
    )
    p2.next_batch()
    pre_diag = p2.get_diagnostics()
    assert pre_diag.emitted_record_count >= 0
    p2.reset()
    assert p2.cursor.current_time == p2.config.start_time
    assert p2.replay_complete is False
    assert p2.get_diagnostics().emitted_record_count == 0
    assert p2.cursor.emitted_record_ids == set()


# ---------------------------------------------------------------------------
# Extra: data_quality_flags propagate into diagnostics
# ---------------------------------------------------------------------------


def test_data_quality_flags_propagate_into_diagnostics():
    store = HistoricalMarketStore()
    store.add_record(
        _make_funding(
            record_id="f_gap",
            event_time=_T0,
            available_at=_T0,
            data_quality_flags=(DataQualityFlag.DATA_GAP,),
        )
    )
    store.add_record(
        _make_funding(
            record_id="f_late",
            event_time=_T0 + timedelta(seconds=30),
            available_at=_T0 + timedelta(seconds=30),
            data_quality_flags=(DataQualityFlag.LATE_ARRIVAL,),
        )
    )
    provider = _make_provider(store=store, step_interval=timedelta(minutes=1))
    provider.next_batch()
    diag = provider.get_diagnostics()
    assert DataQualityFlag.DATA_GAP in diag.data_gap_flags
    assert DataQualityFlag.LATE_ARRIVAL in diag.data_gap_flags
    # Closed taxonomy enforced on direct record_data_quality_flag.
    diag2 = ReplayFeedDiagnostics()
    with pytest.raises(ValueError):
        diag2.record_data_quality_flag("NOT_A_FLAG")



# ---------------------------------------------------------------------------
# PR104 - bounded store query performance
# ---------------------------------------------------------------------------


def _build_kline_store_spanning(
    *,
    symbols=("BTCUSDT", "ETHUSDT"),
    total_minutes: int,
    include_5m: bool = True,
):
    """Build a store of 1m (and optionally 5m) klines spanning
    ``total_minutes`` from _T0 for each symbol. A kline at open_time
    _T0 + i has available_at = open_time + interval, so most of these
    are FUTURE relative to a short blind window.
    """
    store = HistoricalMarketStore()
    for sym in symbols:
        for i in range(total_minutes):
            ot = _T0 + timedelta(minutes=i)
            store.add_record(
                _make_kline(
                    symbol=sym,
                    interval="1m",
                    open_time=ot,
                    close=100.0 + (i % 10) * 0.1,
                    record_id=f"k1m_{sym}_{i}",
                )
            )
        if include_5m:
            for j in range(total_minutes // 5):
                ot = _T0 + timedelta(minutes=j * 5)
                store.add_record(
                    _make_kline(
                        symbol=sym,
                        interval="5m",
                        open_time=ot,
                        close=100.0 + (j % 10) * 0.1,
                        record_id=f"k5m_{sym}_{j}",
                    )
                )
    return store


def test_pr104_provider_does_not_call_store_queries_per_step():
    """The hot path must NOT re-scan the whole store every tick.

    PR104: ``_build_batch`` builds a bounded availability index once
    and advances a forward-only cursor. The legacy per-step
    ``store.query_records`` / ``query_klines`` / ``query_asof_universe``
    full scans (the O(N x steps) blow-up) must never be invoked while
    stepping.
    """
    store = _build_kline_store_spanning(total_minutes=240)
    total_records = store.record_count
    # Trip-wire: fail loudly if the provider ever falls back to a
    # full-store query during stepping.
    for name in ("query_records", "query_klines", "query_asof_universe"):
        orig = getattr(store, name)

        def _boom(*_a, _name=name, _orig=orig, **_k):
            raise AssertionError(
                f"PR104 regression: provider called store.{_name} "
                "in the per-step hot path"
            )

        setattr(store, name, _boom)

    clock = SimulationClock(
        start_time_utc=_T0,
        end_time_utc=_T0 + timedelta(minutes=30),
        monotonic_forward_only=True,
    )
    provider = ReplayFeedProvider(
        store=store,
        clock=clock,
        config=ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=30),
            step_interval=timedelta(minutes=1),
            allow_reemit=False,
            include_asof_universe=True,
        ),
    )
    steps = 0
    while not provider.replay_complete:
        b = provider.next_batch()
        if b is None:
            break
        steps += 1
    assert steps == 30
    diag = provider.get_diagnostics()
    # Future records (available_at > blind_end) are withheld silently:
    # no per-step diagnostics explosion.
    assert diag.violations == []
    assert diag.future_records_rejected_count == 0
    # Only records visible within the 30m window were ever considered -
    # NOT records x steps. This is the core bounded-scan property.
    assert 0 < diag.total_records_considered < total_records
    assert diag.total_records_considered == diag.emitted_record_count


def test_pr104_one_day_window_over_seven_day_like_store_is_bounded():
    """A 1-day blind window over a ~7-day BTC/ETH-sized store
    (24,192 records: 20,160 1m + 4,032 5m) completes with bounded work
    and zero violations.
    """
    seven_days_minutes = 7 * 24 * 60  # 10,080 per symbol per 1m stream
    store = _build_kline_store_spanning(
        total_minutes=seven_days_minutes, include_5m=True
    )
    # Sanity: this really is a ~7d BTC/ETH-shaped store.
    assert store.record_count == 24192

    one_day = timedelta(days=1)
    clock = SimulationClock(
        start_time_utc=_T0,
        end_time_utc=_T0 + one_day,
        monotonic_forward_only=True,
    )
    provider = ReplayFeedProvider(
        store=store,
        clock=clock,
        config=ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + one_day,
            step_interval=timedelta(minutes=1),
            allow_reemit=False,
            include_asof_universe=True,
        ),
    )
    steps = 0
    while not provider.replay_complete:
        b = provider.next_batch()
        if b is None:
            break
        steps += 1
        assert b.violations == ()
    assert steps == 1440  # full 1-day 1m window completed
    diag = provider.get_diagnostics()
    assert diag.violations == []
    assert diag.future_records_rejected_count == 0
    # Records visible within day 1 only (~2 symbols x (1440 1m + 288
    # 5m)); the ~6 future days were never scanned. Bounded by the
    # in-window record count, NOT records x steps (~34.8M for the
    # legacy full-scan path).
    assert diag.emitted_record_count <= 4000
    assert diag.total_records_considered == diag.emitted_record_count
