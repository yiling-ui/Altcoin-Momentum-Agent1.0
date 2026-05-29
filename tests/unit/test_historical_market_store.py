"""Unit tests for Phase 11C.1D-D-B / PR95 / Historical Market Store v0.

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
    HISTORICAL_MARKET_STORE_PHASE_NAME,
    DataCompletenessState,
    DataQualityFlag,
    HistoricalKlineRecord,
    HistoricalMarketRecord,
    HistoricalMarketRecordType,
    HistoricalMarketStore,
    NoLookaheadViolation,
    NoLookaheadViolationReason,
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
    revision_time: datetime = None,
    revised_from_record_id: str = None,
    late_arrival: bool = False,
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
        revision_time=revision_time,
        revised_from_record_id=revised_from_record_id,
        late_arrival=late_arrival,
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
    data_completeness_state: str = DataCompletenessState.OK,
    data_quality_flags=(),
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
        data_completeness_state=data_completeness_state,
        source="binance_public",
        record_id=record_id,
        event_time=event_time,
        data_quality_flags=tuple(data_quality_flags),
    )


# ---------------------------------------------------------------------------
# 1. add and query available record with available_at <= simulated_time
# ---------------------------------------------------------------------------


def test_add_and_query_available_record():
    store = HistoricalMarketStore()
    sim = _T0
    rec_past = _make_funding(
        record_id="f_past",
        event_time=sim - timedelta(minutes=5),
        available_at=sim - timedelta(minutes=4),
    )
    rec_eq = _make_funding(
        record_id="f_eq",
        event_time=sim - timedelta(minutes=1),
        available_at=sim,  # boundary inclusive
    )
    store.add_record(rec_past)
    store.add_record(rec_eq)
    out = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        symbol="BTCUSDT",
        simulated_time=sim,
    )
    assert [r.record_id for r in out] == ["f_past", "f_eq"]
    assert store.violations == ()  # no future records
    # add_records also works.
    store2 = HistoricalMarketStore()
    store2.add_records([rec_past, rec_eq])
    out2 = store2.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=sim,
    )
    assert {r.record_id for r in out2} == {"f_past", "f_eq"}


# ---------------------------------------------------------------------------
# 2. future record with available_at > simulated_time is not returned
# ---------------------------------------------------------------------------


def test_future_record_not_returned():
    store = HistoricalMarketStore()
    sim = _T0
    rec_past = _make_funding(
        record_id="f_past",
        event_time=sim - timedelta(minutes=5),
        available_at=sim - timedelta(minutes=4),
    )
    rec_future = _make_funding(
        record_id="f_future",
        event_time=sim + timedelta(minutes=1),
        available_at=sim + timedelta(minutes=2),
    )
    store.add_record(rec_past)
    store.add_record(rec_future)
    out = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=sim,
    )
    assert [r.record_id for r in out] == ["f_past"]
    assert "f_future" not in {r.record_id for r in out}


# ---------------------------------------------------------------------------
# 3. future record creates NoLookaheadViolation / diagnostics
# ---------------------------------------------------------------------------


def test_future_record_creates_no_lookahead_violation_diagnostic():
    store = HistoricalMarketStore()
    sim = _T0
    rec_future = _make_funding(
        record_id="f_future",
        event_time=sim + timedelta(minutes=1),
        available_at=sim + timedelta(minutes=2),
    )
    store.add_record(rec_future)
    assert store.violations == ()
    out = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=sim,
    )
    assert out == []
    vs = store.violations
    assert len(vs) == 1
    v = vs[0]
    assert isinstance(v, NoLookaheadViolation)
    assert v.reason == NoLookaheadViolationReason.FUTURE_AVAILABLE_AT
    assert v.simulated_time == sim
    assert v.available_at == sim + timedelta(minutes=2)
    assert v.record_id == "f_future"
    # clear_violations resets.
    store.clear_violations()
    assert store.violations == ()


# ---------------------------------------------------------------------------
# 4. ingested_at is never used as availability
# ---------------------------------------------------------------------------


def test_ingested_at_is_never_used_as_availability():
    store = HistoricalMarketStore()
    sim = _T0
    # Record has ingested_at in the past but available_at in the future:
    # MUST be rejected as future data, NOT silently treated as available
    # because ingested_at <= sim.
    rec = HistoricalMarketRecord(
        record_id="f_lateavail",
        record_type=HistoricalMarketRecordType.FUNDING_RATE,
        symbol="BTCUSDT",
        event_time=sim - timedelta(minutes=2),
        available_at=sim + timedelta(minutes=10),
        ingested_at=sim - timedelta(minutes=5),
        source="binance_public",
        payload={"funding_rate": 0.0001},
    )
    store.add_record(rec)
    out = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=sim,
    )
    assert out == []
    assert len(store.violations) == 1
    assert (
        store.violations[0].reason
        == NoLookaheadViolationReason.FUTURE_AVAILABLE_AT
    )
    # And the record's serialised view distinguishes the four
    # timestamps - ingested_at is NOT used as availability anywhere in
    # the payload.
    d = rec.to_dict()
    assert d["available_at"] == (sim + timedelta(minutes=10)).isoformat()
    assert d["ingested_at"] == (sim - timedelta(minutes=5)).isoformat()
    assert d["available_at"] != d["ingested_at"]


# ---------------------------------------------------------------------------
# 5. query_latest returns latest available record only
# ---------------------------------------------------------------------------


def test_query_latest_returns_latest_available_record_only():
    store = HistoricalMarketStore()
    sim = _T0
    r1 = _make_funding(
        record_id="f_t-3",
        event_time=sim - timedelta(minutes=3),
        available_at=sim - timedelta(minutes=3),
        payload={"funding_rate": 0.0001},
    )
    r2 = _make_funding(
        record_id="f_t-1",
        event_time=sim - timedelta(minutes=1),
        available_at=sim - timedelta(minutes=1),
        payload={"funding_rate": 0.0003},
    )
    r3 = _make_funding(
        record_id="f_future",
        event_time=sim + timedelta(minutes=2),
        available_at=sim + timedelta(minutes=2),
        payload={"funding_rate": 0.9},
    )
    store.add_records([r1, r2, r3])
    latest = store.query_latest(
        HistoricalMarketRecordType.FUNDING_RATE,
        "BTCUSDT",
        simulated_time=sim,
    )
    assert latest is not None
    assert latest.record_id == "f_t-1"
    # Future record produced one violation but is NOT returned.
    assert all(
        v.record_id != "f_t-1" for v in store.violations
    )
    assert any(
        v.record_id == "f_future" for v in store.violations
    )
    # No visible record => None.
    early_sim = sim - timedelta(hours=1)
    store.clear_violations()
    assert (
        store.query_latest(
            HistoricalMarketRecordType.FUNDING_RATE,
            "BTCUSDT",
            simulated_time=early_sim,
        )
        is None
    )


# ---------------------------------------------------------------------------
# 6. query_klines respects interval and available_at
# ---------------------------------------------------------------------------


def test_query_klines_respects_interval_and_available_at():
    store = HistoricalMarketStore()
    sim = _T0 + timedelta(minutes=30)  # plenty of time after open_time
    # 1m kline at _T0..(_T0+1m) - should be visible.
    k_1m = _make_kline(
        symbol="BTCUSDT",
        interval="1m",
        open_time=_T0,
    )
    # 5m kline at _T0..(_T0+5m) - should be visible.
    k_5m = _make_kline(
        symbol="BTCUSDT",
        interval="5m",
        open_time=_T0,
    )
    # Different symbol: should NOT appear in BTCUSDT query.
    k_eth = _make_kline(
        symbol="ETHUSDT",
        interval="1m",
        open_time=_T0,
    )
    store.add_records([k_1m, k_5m, k_eth])
    out_1m = store.query_klines(
        "BTCUSDT", "1m", simulated_time=sim
    )
    assert [k.record_id for k in out_1m] == [k_1m.record_id]
    out_5m = store.query_klines(
        "BTCUSDT", "5m", simulated_time=sim
    )
    assert [k.record_id for k in out_5m] == [k_5m.record_id]
    out_eth = store.query_klines(
        "ETHUSDT", "1m", simulated_time=sim
    )
    assert [k.record_id for k in out_eth] == [k_eth.record_id]
    # Different interval: empty.
    assert store.query_klines("ETHUSDT", "5m", simulated_time=sim) == []
    # Available_at gating: simulated time before close_time => empty +
    # violation.
    store2 = HistoricalMarketStore()
    store2.add_record(k_1m)
    early = _T0 + timedelta(seconds=30)
    res = store2.query_klines("BTCUSDT", "1m", simulated_time=early)
    assert res == []
    assert len(store2.violations) >= 1
    reasons = {v.reason for v in store2.violations}
    assert reasons.intersection(
        {
            NoLookaheadViolationReason.FUTURE_AVAILABLE_AT,
            NoLookaheadViolationReason.UNCLOSED_CANDLE_FIELD_ACCESS,
        }
    )
    # Unsupported intervals are rejected.
    with pytest.raises(ValueError):
        store2.query_klines("BTCUSDT", "1h", simulated_time=sim)


# ---------------------------------------------------------------------------
# 7. 1m kline final OHLCV unavailable before close / available after close
# ---------------------------------------------------------------------------


def test_1m_kline_final_ohlcv_visibility():
    store = HistoricalMarketStore()
    k = _make_kline(symbol="BTCUSDT", interval="1m", open_time=_T0)
    store.add_record(k)
    close_time = _T0 + timedelta(seconds=60)
    # Before close: invisible + violation.
    res_open = store.query_klines(
        "BTCUSDT", "1m", simulated_time=_T0 + timedelta(seconds=30)
    )
    assert res_open == []
    assert len(store.violations) >= 1
    # Exactly at close: visible.
    store.clear_violations()
    res_at_close = store.query_klines(
        "BTCUSDT", "1m", simulated_time=close_time
    )
    assert [r.record_id for r in res_at_close] == [k.record_id]
    assert store.violations == ()
    # After close: visible, full OHLCV present.
    res_after = store.query_klines(
        "BTCUSDT", "1m", simulated_time=close_time + timedelta(seconds=1)
    )
    assert len(res_after) == 1
    rec = res_after[0]
    assert rec.high == 101.0
    assert rec.low == 99.0
    assert rec.close == 100.5
    assert rec.volume == 12.34


# ---------------------------------------------------------------------------
# 8. 5m kline final OHLCV unavailable before close / available after close
# ---------------------------------------------------------------------------


def test_5m_kline_final_ohlcv_visibility():
    store = HistoricalMarketStore()
    k = _make_kline(
        symbol="ETHUSDT",
        interval="5m",
        open_time=_T0,
        open_=200.0,
        high=220.0,
        low=195.0,
        close=210.0,
        volume=50.0,
    )
    store.add_record(k)
    close_time = _T0 + timedelta(minutes=5)
    # 4 minutes in: invisible + violation.
    res_open = store.query_klines(
        "ETHUSDT", "5m", simulated_time=_T0 + timedelta(minutes=4)
    )
    assert res_open == []
    assert len(store.violations) >= 1
    # Exactly at close: visible.
    store.clear_violations()
    res_at_close = store.query_klines(
        "ETHUSDT", "5m", simulated_time=close_time
    )
    assert len(res_at_close) == 1
    rec = res_at_close[0]
    assert rec.open == 200.0
    assert rec.high == 220.0
    assert rec.low == 195.0
    assert rec.close == 210.0
    assert rec.volume == 50.0
    assert store.violations == ()
    # After close: still visible.
    res_after = store.query_klines(
        "ETHUSDT", "5m", simulated_time=close_time + timedelta(minutes=1)
    )
    assert len(res_after) == 1


# ---------------------------------------------------------------------------
# 9. as-of universe includes listed symbols only after listed_at /
#    available_at
# ---------------------------------------------------------------------------


def test_asof_universe_listed_only_after_listed_at_and_available_at():
    store = HistoricalMarketStore()
    # BTCUSDT listed at T0; available at T0.
    btc = _make_symbol_status(
        symbol="BTCUSDT",
        listed_at=_T0,
        available_at=_T0,
    )
    # ETHUSDT listed at T0+1h; pre-listing announcement available at
    # T0+30m, with explicit event_time set to the announcement time so
    # that available_at >= event_time (the brief's "special metadata
    # with explicit reason" exception to the available_at >= event_time
    # rule).
    announcement_time = _T0 + timedelta(minutes=15)
    eth = _make_symbol_status(
        symbol="ETHUSDT",
        listed_at=_T0 + timedelta(hours=1),
        available_at=_T0 + timedelta(minutes=30),
        event_time=announcement_time,
        status=SymbolStatus.PRE_TRADING,
    )
    store.add_records([btc, eth])

    # Before T0: nothing.
    universe_before = store.query_asof_universe(
        _T0 - timedelta(minutes=1)
    )
    assert universe_before == []
    # At T0: only BTCUSDT (ETHUSDT not yet available, not yet listed).
    universe_t0 = store.query_asof_universe(_T0)
    assert [s.symbol for s in universe_t0] == ["BTCUSDT"]
    # At T0 + 30m: ETH announcement available but not yet listed -
    # MUST NOT be in the universe.
    universe_30m = store.query_asof_universe(
        _T0 + timedelta(minutes=30)
    )
    assert [s.symbol for s in universe_30m] == ["BTCUSDT"]
    # At T0 + 1h: ETH listed AND visible; both in universe.
    universe_1h = store.query_asof_universe(_T0 + timedelta(hours=1))
    assert [s.symbol for s in universe_1h] == ["BTCUSDT", "ETHUSDT"]


# ---------------------------------------------------------------------------
# 10. as-of universe excludes delisted symbols after delisted_at
# ---------------------------------------------------------------------------


def test_asof_universe_excludes_delisted_symbols_after_delisted_at():
    store = HistoricalMarketStore()
    # XRP listed at T0, delisted at T0+1h.
    listing = _make_symbol_status(
        symbol="XRPUSDT",
        listed_at=_T0,
        available_at=_T0,
        record_id="symstat_xrp_listing",
    )
    # The DELISTED announcement record (later state).
    delisting = _make_symbol_status(
        symbol="XRPUSDT",
        listed_at=_T0,
        delisted_at=_T0 + timedelta(hours=1),
        available_at=_T0 + timedelta(hours=1),
        event_time=_T0 + timedelta(hours=1),
        status=SymbolStatus.DELISTED,
        record_id="symstat_xrp_delisting",
    )
    store.add_records([listing, delisting])
    # Before delisting: in universe.
    before = store.query_asof_universe(_T0 + timedelta(minutes=30))
    assert [s.symbol for s in before] == ["XRPUSDT"]
    assert before[0].status == SymbolStatus.TRADING
    # Exactly at delisted_at: excluded (delisted_at <= sim => excluded).
    at_delist = store.query_asof_universe(_T0 + timedelta(hours=1))
    assert at_delist == []
    # After delisting: still excluded.
    after = store.query_asof_universe(_T0 + timedelta(hours=2))
    assert after == []


# ---------------------------------------------------------------------------
# 11. as-of universe does not use current symbol list
# ---------------------------------------------------------------------------


def test_asof_universe_does_not_use_current_symbol_list():
    store = HistoricalMarketStore()
    # Empty store at any time => empty universe (no current list is
    # baked into the store).
    assert store.query_asof_universe(_T0) == []
    assert store.query_asof_universe(_T0 + timedelta(days=365)) == []
    # Add a symbol that lists at T0+1h with available_at=T0+1h.
    future_listing = _make_symbol_status(
        symbol="NEWUSDT",
        listed_at=_T0 + timedelta(hours=1),
        available_at=_T0 + timedelta(hours=1),
    )
    store.add_record(future_listing)
    # Querying at T0 (i.e. *before* the listing's available_at) MUST
    # NOT include NEWUSDT just because it is "currently in the store"
    # at the program-runtime level.
    universe_t0 = store.query_asof_universe(_T0)
    assert universe_t0 == []
    # And the past is reconstructed from stored records ONLY: querying
    # at T0+1h finally shows NEWUSDT.
    universe_t1 = store.query_asof_universe(_T0 + timedelta(hours=1))
    assert [s.symbol for s in universe_t1] == ["NEWUSDT"]


# ---------------------------------------------------------------------------
# 12. data_quality_flags preserved
# ---------------------------------------------------------------------------


def test_data_quality_flags_preserved():
    store = HistoricalMarketStore()
    sim = _T0
    rec = _make_funding(
        record_id="f_q",
        event_time=sim - timedelta(minutes=1),
        available_at=sim,
        data_quality_flags=(
            DataQualityFlag.DATA_GAP,
            DataQualityFlag.LATE_ARRIVAL,
        ),
    )
    store.add_record(rec)
    out = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=sim,
    )
    assert len(out) == 1
    assert out[0].data_quality_flags == (
        DataQualityFlag.DATA_GAP,
        DataQualityFlag.LATE_ARRIVAL,
    )
    assert out[0].to_dict()["data_quality_flags"] == [
        DataQualityFlag.DATA_GAP,
        DataQualityFlag.LATE_ARRIVAL,
    ]
    # Kline records preserve flags.
    k = _make_kline(
        symbol="BTCUSDT",
        interval="1m",
        open_time=_T0,
        record_id="kline_with_flag",
        data_quality_flags=(DataQualityFlag.INCOMPLETE_KLINE,),
    )
    store.add_record(k)
    klines = store.query_klines(
        "BTCUSDT", "1m", simulated_time=_T0 + timedelta(seconds=60)
    )
    assert len(klines) == 1
    assert (
        DataQualityFlag.INCOMPLETE_KLINE in klines[0].data_quality_flags
    )
    # SymbolStatusRecord preserves flags.
    s = _make_symbol_status(
        symbol="LTCUSDT",
        listed_at=_T0,
        available_at=_T0,
        data_completeness_state=DataCompletenessState.DEGRADED,
        data_quality_flags=(DataQualityFlag.SYMBOL_STATUS_UNKNOWN,),
    )
    store.add_record(s)
    fetched = store.query_symbol_status(
        "LTCUSDT", simulated_time=_T0
    )
    assert fetched is not None
    assert fetched.data_completeness_state == DataCompletenessState.DEGRADED
    assert (
        DataQualityFlag.SYMBOL_STATUS_UNKNOWN
        in fetched.data_quality_flags
    )
    # Unsupported flag is rejected at construction.
    with pytest.raises(ValueError):
        _make_funding(
            record_id="f_bad_flag",
            event_time=sim,
            available_at=sim,
            data_quality_flags=("NOT_A_REAL_FLAG",),
        )


# ---------------------------------------------------------------------------
# 13. late-arriving / revised record visible only after its own
#     available_at
# ---------------------------------------------------------------------------


def test_late_arrival_and_revised_record_visible_only_after_own_available_at():
    store = HistoricalMarketStore()
    # Original record was supposed to be available at T0+1m.
    original = _make_funding(
        record_id="f_orig",
        event_time=_T0,
        available_at=_T0 + timedelta(minutes=1),
        payload={"funding_rate": 0.0001},
    )
    # A revised version arrives later (simulating a data correction at
    # T0+10m). Its own available_at marks the earliest sim time at
    # which it may be observed.
    revised = HistoricalMarketRecord(
        record_id="f_rev",
        record_type=HistoricalMarketRecordType.FUNDING_RATE,
        symbol="BTCUSDT",
        event_time=_T0,  # the underlying market event is the same
        available_at=_T0 + timedelta(minutes=10),
        ingested_at=_T0 + timedelta(minutes=10),
        source="binance_public",
        payload={"funding_rate": 0.0002},
        data_quality_flags=(
            DataQualityFlag.REVISED_RECORD,
            DataQualityFlag.LATE_ARRIVAL,
        ),
        revision_time=_T0 + timedelta(minutes=10),
        revised_from_record_id="f_orig",
        late_arrival=True,
    )
    store.add_records([original, revised])

    # At T0+30s: nothing visible.
    res_30s = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=_T0 + timedelta(seconds=30),
    )
    assert res_30s == []
    # At T0+2m: only the original is visible.
    res_2m = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=_T0 + timedelta(minutes=2),
    )
    assert [r.record_id for r in res_2m] == ["f_orig"]
    # At T0+10m: BOTH original and revision are visible (the revision
    # does NOT overwrite or invalidate the original; the original
    # remains in the audit trail per Constitution §E).
    res_10m = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=_T0 + timedelta(minutes=10),
    )
    assert {r.record_id for r in res_10m} == {"f_orig", "f_rev"}
    # query_latest at T0+10m picks the revision (it has the same
    # event_time, but the revision's available_at is later, breaking
    # the tie deterministically toward the more recent observation).
    latest = store.query_latest(
        HistoricalMarketRecordType.FUNDING_RATE,
        "BTCUSDT",
        simulated_time=_T0 + timedelta(minutes=10),
    )
    assert latest is not None
    assert latest.record_id == "f_rev"
    assert latest.payload["funding_rate"] == 0.0002
    assert latest.revised_from_record_id == "f_orig"
    assert latest.late_arrival is True
    assert DataQualityFlag.REVISED_RECORD in latest.data_quality_flags


# ---------------------------------------------------------------------------
# 14. deterministic ordering
# ---------------------------------------------------------------------------


def test_deterministic_ordering():
    # Build two stores with records inserted in different orders.
    a = HistoricalMarketStore()
    b = HistoricalMarketStore()
    sim = _T0 + timedelta(hours=1)

    recs_in_order = [
        _make_funding(
            record_id="z",
            event_time=sim - timedelta(minutes=10),
            available_at=sim - timedelta(minutes=10),
        ),
        _make_funding(
            record_id="a",
            event_time=sim - timedelta(minutes=20),
            available_at=sim - timedelta(minutes=20),
        ),
        _make_funding(
            record_id="m",
            event_time=sim - timedelta(minutes=15),
            available_at=sim - timedelta(minutes=15),
        ),
    ]
    a.add_records(recs_in_order)
    b.add_records(list(reversed(recs_in_order)))
    out_a = a.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=sim,
    )
    out_b = b.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=sim,
    )
    # Both stores produce the SAME deterministic ordering.
    assert [r.record_id for r in out_a] == ["a", "m", "z"]
    assert [r.record_id for r in out_b] == ["a", "m", "z"]
    # Klines: deterministic by open_time.
    a2 = HistoricalMarketStore()
    b2 = HistoricalMarketStore()
    klines = [
        _make_kline(
            symbol="BTCUSDT",
            interval="1m",
            open_time=_T0 + timedelta(minutes=2),
            record_id="k_2",
        ),
        _make_kline(
            symbol="BTCUSDT",
            interval="1m",
            open_time=_T0,
            record_id="k_0",
        ),
        _make_kline(
            symbol="BTCUSDT",
            interval="1m",
            open_time=_T0 + timedelta(minutes=1),
            record_id="k_1",
        ),
    ]
    a2.add_records(klines)
    b2.add_records(list(reversed(klines)))
    sim_kline = _T0 + timedelta(hours=1)
    out_a2 = a2.query_klines(
        "BTCUSDT", "1m", simulated_time=sim_kline
    )
    out_b2 = b2.query_klines(
        "BTCUSDT", "1m", simulated_time=sim_kline
    )
    assert [k.record_id for k in out_a2] == ["k_0", "k_1", "k_2"]
    assert [k.record_id for k in out_b2] == ["k_0", "k_1", "k_2"]
    # Universe: deterministic by symbol.
    a3 = HistoricalMarketStore()
    b3 = HistoricalMarketStore()
    syms = [
        _make_symbol_status(
            symbol="ZECUSDT", listed_at=_T0, available_at=_T0
        ),
        _make_symbol_status(
            symbol="BTCUSDT", listed_at=_T0, available_at=_T0
        ),
        _make_symbol_status(
            symbol="MATICUSDT", listed_at=_T0, available_at=_T0
        ),
    ]
    a3.add_records(syms)
    b3.add_records(list(reversed(syms)))
    u_a = a3.query_asof_universe(_T0)
    u_b = b3.query_asof_universe(_T0)
    assert [s.symbol for s in u_a] == ["BTCUSDT", "MATICUSDT", "ZECUSDT"]
    assert [s.symbol for s in u_b] == ["BTCUSDT", "MATICUSDT", "ZECUSDT"]


# ---------------------------------------------------------------------------
# 15. JSON serializable output
# ---------------------------------------------------------------------------


def test_json_serializable_output():
    store = HistoricalMarketStore()
    rec = _make_funding(
        record_id="f_json",
        event_time=_T0,
        available_at=_T0,
        payload={
            "funding_rate": 0.0001,
            "interval": "8h",
            "nested": {"a": 1, "b": [1, 2, 3]},
        },
    )
    k = _make_kline(symbol="BTCUSDT", interval="1m", open_time=_T0)
    s = _make_symbol_status(
        symbol="BTCUSDT", listed_at=_T0, available_at=_T0
    )
    store.add_records([rec, k, s])
    # Each record's to_dict() is JSON-serialisable.
    for payload in (
        rec.to_dict(),
        k.to_dict(),
        s.to_dict(),
        store.to_dict(),
        store.safety_payload(),
    ):
        text = json.dumps(payload, sort_keys=True)
        round_tripped = json.loads(text)
        assert round_tripped["phase_12_forbidden"] is True
    # Querying then serialising one of each works.
    out_records = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=_T0,
    )
    assert json.dumps([r.to_dict() for r in out_records], sort_keys=True)
    # Violations also serialise (they're audit artefacts).
    store2 = HistoricalMarketStore()
    store2.add_record(
        _make_funding(
            record_id="future",
            event_time=_T0,
            available_at=_T0 + timedelta(minutes=5),
        )
    )
    store2.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        simulated_time=_T0,
    )
    for v in store2.violations:
        json.dumps(v.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# 16. phase_12_forbidden=true where safety payload exists
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_in_every_safety_payload():
    store = HistoricalMarketStore()
    assert store.phase_12_forbidden is True
    assert store.safety_payload()["phase_12_forbidden"] is True
    assert store.to_dict()["phase_12_forbidden"] is True
    rec = _make_funding(
        record_id="x",
        event_time=_T0,
        available_at=_T0,
    )
    assert rec.to_dict()["phase_12_forbidden"] is True
    k = _make_kline(symbol="BTCUSDT", interval="1m", open_time=_T0)
    assert k.to_dict()["phase_12_forbidden"] is True
    s = _make_symbol_status(
        symbol="BTCUSDT", listed_at=_T0, available_at=_T0
    )
    assert s.to_dict()["phase_12_forbidden"] is True
    # The literal "Phase 12" must NOT appear as a destination in the
    # phase identifier.
    assert "Phase 12" not in HISTORICAL_MARKET_STORE_PHASE_NAME


# ---------------------------------------------------------------------------
# 17. auto_tuning_allowed=false where safety payload exists
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_in_every_safety_payload():
    store = HistoricalMarketStore()
    assert store.auto_tuning_allowed is False
    assert store.safety_payload()["auto_tuning_allowed"] is False
    assert store.to_dict()["auto_tuning_allowed"] is False
    rec = _make_funding(
        record_id="x", event_time=_T0, available_at=_T0
    )
    assert rec.to_dict()["auto_tuning_allowed"] is False
    k = _make_kline(symbol="BTCUSDT", interval="1m", open_time=_T0)
    assert k.to_dict()["auto_tuning_allowed"] is False
    s = _make_symbol_status(
        symbol="BTCUSDT", listed_at=_T0, available_at=_T0
    )
    assert s.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 18. trade_authority=false where safety payload exists
# ---------------------------------------------------------------------------


def test_trade_authority_false_in_every_safety_payload():
    store = HistoricalMarketStore()
    assert store.trade_authority is False
    assert store.ai_trade_authority is False
    payload = store.safety_payload()
    assert payload["trade_authority"] is False
    assert payload["ai_trade_authority"] is False
    rec = _make_funding(
        record_id="x", event_time=_T0, available_at=_T0
    )
    assert rec.to_dict()["trade_authority"] is False
    assert rec.to_dict()["ai_trade_authority"] is False
    k = _make_kline(symbol="BTCUSDT", interval="1m", open_time=_T0)
    assert k.to_dict()["trade_authority"] is False
    s = _make_symbol_status(
        symbol="BTCUSDT", listed_at=_T0, available_at=_T0
    )
    assert s.to_dict()["trade_authority"] is False
    # No public method on the store / record types exposes a trade verb.
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
    for inst in (store, rec, k, s):
        public = {n for n in dir(inst) if not n.startswith("_")}
        assert public.isdisjoint(forbidden_verbs)


# ---------------------------------------------------------------------------
# 19. forbidden fields absent from serialized outputs
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_in_serialized_outputs():
    store = HistoricalMarketStore()
    rec = _make_funding(
        record_id="f", event_time=_T0, available_at=_T0
    )
    k = _make_kline(symbol="BTCUSDT", interval="1m", open_time=_T0)
    s = _make_symbol_status(
        symbol="BTCUSDT", listed_at=_T0, available_at=_T0
    )
    store.add_records([rec, k, s])
    payloads = [
        store.to_dict(),
        store.safety_payload(),
        rec.to_dict(),
        k.to_dict(),
        s.to_dict(),
    ]
    for p in payloads:
        assert_no_forbidden_fields(p)
        keys = set(_walk_keys(p))
        assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS), (
            f"forbidden field present: "
            f"{keys & FORBIDDEN_OUTPUT_FIELDS}"
        )
    # A hostile payload smuggled through HistoricalMarketRecord.payload
    # is rejected at construction time.
    with pytest.raises(ValueError):
        HistoricalMarketRecord(
            record_id="f_bad",
            record_type=HistoricalMarketRecordType.FUNDING_RATE,
            symbol="BTCUSDT",
            event_time=_T0,
            available_at=_T0,
            payload={"runtime_config_patch": {"x": 1}},
        )
    with pytest.raises(ValueError):
        HistoricalMarketRecord(
            record_id="f_bad2",
            record_type=HistoricalMarketRecordType.FUNDING_RATE,
            symbol="BTCUSDT",
            event_time=_T0,
            available_at=_T0,
            payload={"deep": [{"inner": {"leverage": 5}}]},
        )
    with pytest.raises(ValueError):
        HistoricalMarketRecord(
            record_id="f_bad3",
            record_type=HistoricalMarketRecordType.FUNDING_RATE,
            symbol="BTCUSDT",
            event_time=_T0,
            available_at=_T0,
            payload={"long": True},
        )


# ---------------------------------------------------------------------------
# 20. module does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports_in_module_or_init():
    root = _project_root()
    init_path = root / "app" / "sim" / "__init__.py"
    store_path = root / "app" / "sim" / "historical_market_store.py"

    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in (init_path, store_path):
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
    importlib.import_module("app.sim.historical_market_store")
    new = set(sys.modules) - before
    for nm in new:
        for bad in forbidden_prefixes:
            assert not nm.startswith(bad), (
                f"importing app.sim pulled forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 21. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_llm_telegram_binance_or_network_path():
    root = _project_root()
    files = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "historical_market_store.py",
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
    # Defensive: reloading the module does not import any forbidden
    # module.
    pre = set(sys.modules)
    importlib.import_module("app.sim.historical_market_store")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), (
                f"unexpected import: {nm}"
            )


# ---------------------------------------------------------------------------
# Extra: closed taxonomies
# ---------------------------------------------------------------------------


def test_closed_taxonomies():
    assert HistoricalMarketRecordType.ALLOWED == frozenset(
        {
            "KLINE_1M",
            "KLINE_5M",
            "FUNDING_RATE",
            "OPEN_INTEREST",
            "TICKER_24H",
            "EXCHANGE_INFO",
            "SYMBOL_STATUS",
            "LISTING_STATUS",
            "DELISTING_STATUS",
        }
    )
    assert HistoricalMarketRecordType.KLINE_TYPES == frozenset(
        {"KLINE_1M", "KLINE_5M"}
    )
    assert DataQualityFlag.ALLOWED == frozenset(
        {
            "DATA_GAP",
            "LATE_ARRIVAL",
            "REVISED_RECORD",
            "INCOMPLETE_KLINE",
            "SYMBOL_STATUS_UNKNOWN",
            "FUNDING_MISSING",
            "OI_MISSING",
            "TICKER_MISSING",
        }
    )
    assert SymbolStatus.ALLOWED == frozenset(
        {
            "TRADING",
            "BREAK",
            "HALT",
            "DELISTED",
            "SETTLING",
            "PRE_TRADING",
            "UNKNOWN",
        }
    )
    # DELISTED is explicitly NOT in the tradable / monitorable set.
    assert (
        SymbolStatus.DELISTED
        not in SymbolStatus.TRADABLE_OR_MONITORABLE
    )
    assert DataCompletenessState.ALLOWED == frozenset(
        {"OK", "DEGRADED", "INCOMPLETE", "UNKNOWN"}
    )
    # Unsupported record type rejected.
    with pytest.raises(ValueError):
        HistoricalMarketRecord(
            record_id="x",
            record_type="NOT_A_TYPE",
            symbol="BTCUSDT",
            event_time=_T0,
            available_at=_T0,
        )


# ---------------------------------------------------------------------------
# Extra: HistoricalKlineRecord rejects available_at before close_time
# ---------------------------------------------------------------------------


def test_kline_rejects_available_at_before_close_time():
    # available_at < close_time: rejected (final OHLCV invisible before
    # close - Constitution §6).
    with pytest.raises(ValueError):
        HistoricalKlineRecord(
            symbol="BTCUSDT",
            interval="1m",
            open_time=_T0,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
            available_at=_T0 + timedelta(seconds=30),  # < close_time
        )
    # available_at == close_time: accepted.
    HistoricalKlineRecord(
        symbol="BTCUSDT",
        interval="1m",
        open_time=_T0,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        available_at=_T0 + timedelta(seconds=60),
    )
    # OHLC sanity rejected.
    with pytest.raises(ValueError):
        HistoricalKlineRecord(
            symbol="BTCUSDT",
            interval="1m",
            open_time=_T0,
            open=100.0,
            high=99.0,  # < low
            low=99.5,
            close=100.5,
            volume=10.0,
            available_at=_T0 + timedelta(seconds=60),
        )
    with pytest.raises(ValueError):
        HistoricalKlineRecord(
            symbol="BTCUSDT",
            interval="1m",
            open_time=_T0,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=-1.0,  # negative volume
            available_at=_T0 + timedelta(seconds=60),
        )
    # Inconsistent close_time rejected.
    with pytest.raises(ValueError):
        HistoricalKlineRecord(
            symbol="BTCUSDT",
            interval="1m",
            open_time=_T0,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
            close_time=_T0 + timedelta(seconds=120),  # != open + 1m
            available_at=_T0 + timedelta(seconds=120),
        )
    # Unsupported v0 interval rejected.
    with pytest.raises(ValueError):
        HistoricalKlineRecord(
            symbol="BTCUSDT",
            interval="1h",
            open_time=_T0,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
            available_at=_T0 + timedelta(hours=1),
        )


# ---------------------------------------------------------------------------
# Extra: SymbolStatusRecord enforces invariants
# ---------------------------------------------------------------------------


def test_symbol_status_record_invariants():
    # delisted_at < listed_at rejected.
    with pytest.raises(ValueError):
        SymbolStatusRecord(
            symbol="BTCUSDT",
            market_type="PERP",
            listed_at=_T0,
            status=SymbolStatus.DELISTED,
            available_at=_T0,
            delisted_at=_T0 - timedelta(days=1),
        )
    # DELISTED status without delisted_at rejected.
    with pytest.raises(ValueError):
        SymbolStatusRecord(
            symbol="BTCUSDT",
            market_type="PERP",
            listed_at=_T0,
            status=SymbolStatus.DELISTED,
            available_at=_T0,
        )
    # available_at < event_time rejected (event_time defaults to listed_at).
    with pytest.raises(ValueError):
        SymbolStatusRecord(
            symbol="BTCUSDT",
            market_type="PERP",
            listed_at=_T0,
            status=SymbolStatus.TRADING,
            available_at=_T0 - timedelta(minutes=1),
        )
    # Pre-listing announcement: explicit event_time enables
    # available_at < listed_at (the brief's "special metadata with
    # explicit reason" exception).
    pre = SymbolStatusRecord(
        symbol="ETHUSDT",
        market_type="PERP",
        listed_at=_T0 + timedelta(hours=1),
        status=SymbolStatus.PRE_TRADING,
        available_at=_T0,
        event_time=_T0,  # announcement time
    )
    assert pre.available_at < pre.listed_at
    assert pre.event_time == _T0


# ---------------------------------------------------------------------------
# Extra: query_symbol_status returns latest visible record
# ---------------------------------------------------------------------------


def test_query_symbol_status_returns_latest_visible_record():
    store = HistoricalMarketStore()
    base = _make_symbol_status(
        symbol="BTCUSDT",
        listed_at=_T0,
        available_at=_T0,
        status=SymbolStatus.TRADING,
        record_id="symstat_btc_t0",
    )
    halt = _make_symbol_status(
        symbol="BTCUSDT",
        listed_at=_T0,
        available_at=_T0 + timedelta(hours=1),
        event_time=_T0 + timedelta(hours=1),
        status=SymbolStatus.HALT,
        record_id="symstat_btc_halt",
    )
    store.add_records([base, halt])
    s_t0 = store.query_symbol_status("BTCUSDT", _T0)
    assert s_t0 is not None
    assert s_t0.status == SymbolStatus.TRADING
    s_t1 = store.query_symbol_status("BTCUSDT", _T0 + timedelta(hours=1))
    assert s_t1 is not None
    assert s_t1.status == SymbolStatus.HALT
    # Unknown symbol => None.
    assert store.query_symbol_status("UNKNOWNUSDT", _T0) is None


# ---------------------------------------------------------------------------
# Extra: deterministic violation IDs
# ---------------------------------------------------------------------------


def test_deterministic_violation_ids():
    a = HistoricalMarketStore(time_wall_guard=TimeWallGuard())
    b = HistoricalMarketStore(time_wall_guard=TimeWallGuard())
    sim = _T0
    rec = _make_funding(
        record_id="f_future",
        event_time=sim + timedelta(minutes=1),
        available_at=sim + timedelta(minutes=2),
    )
    a.add_record(rec)
    b.add_record(rec)
    a.query_records(
        HistoricalMarketRecordType.FUNDING_RATE, simulated_time=sim
    )
    b.query_records(
        HistoricalMarketRecordType.FUNDING_RATE, simulated_time=sim
    )
    assert len(a.violations) == 1
    assert len(b.violations) == 1
    pa = a.violations[0].to_dict()
    pb = b.violations[0].to_dict()
    # violation_id is per-guard counter, so identical for two fresh
    # guards.
    assert pa == pb
