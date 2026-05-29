"""Unit tests for Phase 11C.1D-D-A / PR94 / SimulationClock + Time-Wall
Guard.

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

  - does not import app.risk / app.execution / app.exchanges /
    app.telegram / app.config
  - does not pull any DeepSeek / LLM / Telegram / Binance / network
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
    PHASE_NAME,
    CandleVisibilityGuard,
    HistoricalRecordTime,
    NoLookaheadViolation,
    NoLookaheadViolationReason,
    NoLookaheadViolationSeverity,
    SimulationClock,
    TimeWallGuard,
    assert_no_forbidden_fields,
    ensure_utc_aware,
    parse_interval_seconds,
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


def _make_record(
    *,
    available_at: datetime,
    event_time: datetime = None,
    ingested_at: datetime = None,
    source: str = "binance_public",
    record_id: str = "rec_1",
    symbol: str = "BTCUSDT",
    interval: str = "1m",
) -> HistoricalRecordTime:
    if event_time is None:
        event_time = available_at - timedelta(seconds=60)
    return HistoricalRecordTime(
        event_time=event_time,
        available_at=available_at,
        ingested_at=ingested_at,
        source=source,
        record_id=record_id,
        symbol=symbol,
        interval=interval,
    )


# ---------------------------------------------------------------------------
# 1. SimulationClock starts at configured UTC time
# ---------------------------------------------------------------------------


def test_simulation_clock_starts_at_configured_utc_time():
    clk = SimulationClock(start_time_utc=_T0)
    assert clk.now() == _T0
    assert clk.start_time_utc == _T0
    assert clk.current_time_utc == _T0
    assert clk.now().tzinfo is not None
    assert clk.now().utcoffset() == timedelta(0)
    # Naive datetime is rejected.
    with pytest.raises(ValueError):
        SimulationClock(start_time_utc=datetime(2026, 1, 1, 12, 0, 0))
    # Non-UTC tz is normalised to UTC.
    other_tz = timezone(timedelta(hours=8))
    clk2 = SimulationClock(
        start_time_utc=datetime(2026, 1, 1, 20, 0, 0, tzinfo=other_tz)
    )
    assert clk2.now() == _T0  # 20:00 +08:00 == 12:00 UTC
    assert clk2.now().utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# 2. SimulationClock advances forward deterministically
# ---------------------------------------------------------------------------


def test_simulation_clock_advances_forward_deterministically():
    clk = SimulationClock(start_time_utc=_T0)
    t1 = clk.step(timedelta(seconds=60))
    assert t1 == _T0 + timedelta(seconds=60)
    t2 = clk.step(60)  # int seconds
    assert t2 == _T0 + timedelta(seconds=120)
    t3 = clk.step(60.0)  # float seconds
    assert t3 == _T0 + timedelta(seconds=180)
    t4 = clk.step("1m")  # interval string
    assert t4 == _T0 + timedelta(seconds=240)
    t5 = clk.step("5m")
    assert t5 == _T0 + timedelta(seconds=240 + 300)
    # set_time forward
    target = _T0 + timedelta(hours=1)
    assert clk.set_time(target) == target
    # determinism: two clocks given identical inputs reach identical state
    a = SimulationClock(start_time_utc=_T0)
    b = SimulationClock(start_time_utc=_T0)
    for d in [60, "1m", 30, "5m"]:
        a.step(d)
        b.step(d)
    assert a.now() == b.now()
    assert a.to_dict() == b.to_dict()


# ---------------------------------------------------------------------------
# 3. SimulationClock cannot move backward by default
# ---------------------------------------------------------------------------


def test_simulation_clock_cannot_move_backward_by_default():
    clk = SimulationClock(start_time_utc=_T0)
    clk.step("5m")
    with pytest.raises(ValueError):
        clk.step(-60)
    with pytest.raises(ValueError):
        clk.step(timedelta(seconds=-1))
    with pytest.raises(ValueError):
        clk.set_time(_T0)
    # Test-only flag explicitly allows rewind.
    clk2 = SimulationClock(
        start_time_utc=_T0, monotonic_forward_only=False
    )
    clk2.step("5m")
    clk2.step(-60)  # allowed
    clk2.set_time(_T0)  # allowed
    assert clk2.now() == _T0
    # end_time_utc upper bound is enforced.
    bounded = SimulationClock(
        start_time_utc=_T0,
        end_time_utc=_T0 + timedelta(minutes=10),
    )
    with pytest.raises(ValueError):
        bounded.step("1h")
    with pytest.raises(ValueError):
        bounded.set_time(_T0 + timedelta(hours=1))
    # assert_within_bounds passes within bounds.
    bounded.step("5m")
    bounded.assert_within_bounds()


# ---------------------------------------------------------------------------
# 4. TimeWallGuard allows record with available_at <= simulated_time
# ---------------------------------------------------------------------------


def test_time_wall_guard_allows_record_with_available_at_le_simulated_time():
    guard = TimeWallGuard()
    sim = _T0
    # Equal: allowed (boundary is inclusive).
    rec_eq = _make_record(available_at=sim)
    assert guard.can_read(rec_eq, sim) is True
    assert guard.validate_no_lookahead(rec_eq, sim) is None
    # Strictly past: allowed.
    rec_past = _make_record(available_at=sim - timedelta(seconds=1))
    assert guard.can_read(rec_past, sim) is True
    assert guard.validate_no_lookahead(rec_past, sim) is None
    # Mapping-shape records work too.
    rec_map = {
        "available_at": sim - timedelta(minutes=5),
        "event_time": sim - timedelta(minutes=6),
        "record_id": "rec_map",
        "symbol": "ETHUSDT",
        "source": "binance_public",
    }
    assert guard.can_read(rec_map, sim) is True
    assert guard.validate_no_lookahead(rec_map, sim) is None


# ---------------------------------------------------------------------------
# 5. TimeWallGuard rejects record with available_at > simulated_time
# ---------------------------------------------------------------------------


def test_time_wall_guard_rejects_future_record():
    guard = TimeWallGuard()
    sim = _T0
    rec = _make_record(available_at=sim + timedelta(seconds=1))
    assert guard.can_read(rec, sim) is False
    v = guard.validate_no_lookahead(rec, sim)
    assert v is not None
    assert v.reason == NoLookaheadViolationReason.FUTURE_AVAILABLE_AT
    assert v.simulated_time == sim
    assert v.available_at == sim + timedelta(seconds=1)
    assert v.severity == NoLookaheadViolationSeverity.P0
    # assert_can_read raises with NO_LOOKAHEAD_VIOLATION marker.
    with pytest.raises(ValueError) as ei:
        guard.assert_can_read(rec, sim)
    assert "NO_LOOKAHEAD_VIOLATION" in str(ei.value)
    assert "FUTURE_AVAILABLE_AT" in str(ei.value)


# ---------------------------------------------------------------------------
# 6. TimeWallGuard does not use ingested_at as availability
# ---------------------------------------------------------------------------


def test_time_wall_guard_does_not_use_ingested_at_as_availability():
    guard = TimeWallGuard()
    sim = _T0
    # Future available_at, but ingested_at is in the past. The guard
    # MUST still reject this record - ingested_at is not a substitute
    # for available_at.
    rec = _make_record(
        available_at=sim + timedelta(minutes=10),
        ingested_at=sim - timedelta(minutes=10),
    )
    assert guard.can_read(rec, sim) is False
    v = guard.validate_no_lookahead(rec, sim)
    assert v is not None
    assert v.reason == NoLookaheadViolationReason.FUTURE_AVAILABLE_AT
    # The dedicated INGESTED_AT_USED_AS_AVAILABILITY violation helper.
    iv = guard.make_ingested_at_used_as_availability_violation(rec, sim)
    assert iv.reason == (
        NoLookaheadViolationReason.INGESTED_AT_USED_AS_AVAILABILITY
    )
    assert iv.simulated_time == sim
    assert iv.available_at == sim + timedelta(minutes=10)


# ---------------------------------------------------------------------------
# 7. missing available_at creates NoLookaheadViolation
# ---------------------------------------------------------------------------


def test_missing_available_at_creates_no_lookahead_violation():
    guard = TimeWallGuard()
    sim = _T0
    # HistoricalRecordTime cannot be constructed without available_at,
    # but a Mapping-shape record can omit it. The guard must reject.
    rec = {
        "event_time": sim - timedelta(seconds=60),
        "record_id": "rec_no_avail",
        "symbol": "BTCUSDT",
        "source": "binance_public",
        # available_at is intentionally absent.
    }
    assert guard.can_read(rec, sim) is False
    v = guard.validate_no_lookahead(rec, sim)
    assert v is not None
    assert v.reason == NoLookaheadViolationReason.MISSING_AVAILABLE_AT
    assert v.available_at is None
    assert v.record_id == "rec_no_avail"
    # And the constructor of HistoricalRecordTime itself rejects naive
    # available_at (a different defensive boundary).
    with pytest.raises(ValueError):
        HistoricalRecordTime(
            event_time=sim,
            available_at=datetime(2026, 1, 1, 12, 0, 0),  # naive
        )


# ---------------------------------------------------------------------------
# 8. filter_available returns only available records and records
#    violations for future records
# ---------------------------------------------------------------------------


def test_filter_available_returns_allowed_and_violations_no_silent_drop():
    guard = TimeWallGuard()
    sim = _T0
    past = _make_record(
        available_at=sim - timedelta(seconds=30), record_id="r_past"
    )
    boundary = _make_record(available_at=sim, record_id="r_boundary")
    future = _make_record(
        available_at=sim + timedelta(seconds=30), record_id="r_future"
    )
    missing = {"event_time": sim - timedelta(seconds=10), "record_id": "r_missing"}
    allowed, violations = guard.filter_available(
        [past, boundary, future, missing], sim
    )
    assert [r.record_id for r in allowed if hasattr(r, "record_id")] == [
        "r_past",
        "r_boundary",
    ]
    # No record is silently dropped: future + missing both produce
    # auditable violation objects.
    assert len(violations) == 2
    reasons = {v.reason for v in violations}
    assert NoLookaheadViolationReason.FUTURE_AVAILABLE_AT in reasons
    assert NoLookaheadViolationReason.MISSING_AVAILABLE_AT in reasons
    # reject_future_records is a thin wrapper.
    only_v = guard.reject_future_records(
        [past, boundary, future, missing], sim
    )
    assert len(only_v) == 2
    # Violation IDs are unique and monotonically increasing.
    ids = [v.violation_id for v in violations]
    assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# 9. 1m candle final OHLCV invisible before close
# ---------------------------------------------------------------------------


def test_1m_candle_final_ohlcv_invisible_before_close():
    cv = CandleVisibilityGuard()
    open_time = _T0
    interval = "1m"
    # simulated_time strictly before close.
    sim = open_time + timedelta(seconds=30)
    assert cv.is_candle_closed(open_time, interval, sim) is False
    candle = {
        "open_time": open_time,
        "interval": interval,
        "symbol": "BTCUSDT",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 12.34,
    }
    visible = cv.visible_candle_fields(candle, sim)
    for forbidden in ("high", "low", "close", "volume"):
        assert forbidden not in visible, (
            f"{forbidden!r} must not be visible before candle close"
        )
    # open_time / open / interval / symbol may still be visible as
    # partial metadata (the consumer must still treat them as partial).
    assert visible["open_time"] == open_time
    assert visible["interval"] == interval
    assert visible["symbol"] == "BTCUSDT"


# ---------------------------------------------------------------------------
# 10. 1m candle final OHLCV visible after close
# ---------------------------------------------------------------------------


def test_1m_candle_final_ohlcv_visible_after_close():
    cv = CandleVisibilityGuard()
    open_time = _T0
    interval = "1m"
    close_time = cv.candle_close_time(open_time, interval)
    assert close_time == open_time + timedelta(seconds=60)
    # Exactly at close_time counts as closed.
    sim = close_time
    assert cv.is_candle_closed(open_time, interval, sim) is True
    candle = {
        "open_time": open_time,
        "interval": interval,
        "symbol": "BTCUSDT",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 12.34,
    }
    visible = cv.visible_candle_fields(candle, sim)
    for required in ("open", "high", "low", "close", "volume"):
        assert required in visible
    # And after close, assert_candle_fields_visible returns silently.
    cv.assert_candle_fields_visible(candle, sim)
    cv.assert_candle_fields_visible(
        candle, close_time + timedelta(seconds=1)
    )


# ---------------------------------------------------------------------------
# 11. 5m candle final OHLCV invisible before close
# ---------------------------------------------------------------------------


def test_5m_candle_final_ohlcv_invisible_before_close():
    cv = CandleVisibilityGuard()
    open_time = _T0
    interval = "5m"
    close_time = cv.candle_close_time(open_time, interval)
    assert close_time == open_time + timedelta(minutes=5)
    # 4 minutes in: still open.
    sim = open_time + timedelta(minutes=4)
    assert cv.is_candle_closed(open_time, interval, sim) is False
    candle = {
        "open_time": open_time,
        "interval": interval,
        "symbol": "ETHUSDT",
        "open": 200.0,
        "high": 220.0,
        "low": 195.0,
        "close": 210.0,
        "volume": 50.0,
    }
    visible = cv.visible_candle_fields(candle, sim)
    for forbidden in ("high", "low", "close", "volume"):
        assert forbidden not in visible
    # 5 minutes in: closed; full payload visible.
    sim_closed = open_time + timedelta(minutes=5)
    assert cv.is_candle_closed(open_time, interval, sim_closed) is True
    full = cv.visible_candle_fields(candle, sim_closed)
    assert full["high"] == 220.0
    assert full["low"] == 195.0
    assert full["close"] == 210.0
    assert full["volume"] == 50.0


# ---------------------------------------------------------------------------
# 12. unclosed candle high/low/close/volume access creates violation
# ---------------------------------------------------------------------------


def test_unclosed_candle_field_access_creates_violation():
    cv = CandleVisibilityGuard()
    open_time = _T0
    interval = "1m"
    sim = open_time + timedelta(seconds=30)  # before close
    for forbidden in ("high", "low", "close", "volume"):
        candle = {
            "open_time": open_time,
            "interval": interval,
            "symbol": "BTCUSDT",
            "open": 100.0,
            forbidden: 123.45,
        }
        with pytest.raises(ValueError) as ei:
            cv.assert_candle_fields_visible(candle, sim)
        assert "UNCLOSED_CANDLE_FIELD_ACCESS" in str(ei.value)
        assert forbidden in str(ei.value)
    # And the dedicated TimeWallGuard helper can mint an audit
    # NoLookaheadViolation for the same condition.
    guard = TimeWallGuard()
    v = guard.make_unclosed_candle_field_access_violation(
        simulated_time=sim,
        field_name="high",
        candle_open_time=open_time,
        interval=interval,
        record_id="cdl_1",
        symbol="BTCUSDT",
    )
    assert (
        v.reason
        == NoLookaheadViolationReason.UNCLOSED_CANDLE_FIELD_ACCESS
    )
    assert v.event_time == open_time
    assert v.available_at == open_time + timedelta(seconds=60)


# ---------------------------------------------------------------------------
# 13. outcome label during blind window creates violation object
# ---------------------------------------------------------------------------


def test_outcome_label_during_blind_window_creates_violation():
    guard = TimeWallGuard()
    sim = _T0
    forbidden_labels = (
        "future_top_mover_label",
        "completed_tail_label",
        "post_discovery_outcome",
        "future_mfe",
        "future_mae",
        "severe_missed_tail_label",
        "final_window_pnl",
        "future_drawdown",
        "future_funding_rate_change",
        "future_regime_label",
        "future_ai_briefing",
        "future_replay_summary",
        "future_reflection_summary",
    )
    for label in forbidden_labels:
        v = guard.make_outcome_label_violation(
            simulated_time=sim,
            label=label,
            record_id=f"lbl_{label}",
            symbol="BTCUSDT",
        )
        assert (
            v.reason
            == NoLookaheadViolationReason.OUTCOME_LABEL_DURING_BLIND_WINDOW
        )
        assert v.severity == NoLookaheadViolationSeverity.P0
        assert v.simulated_time == sim
        assert label in (v.detail or "")
    # Empty label is rejected.
    with pytest.raises(ValueError):
        guard.make_outcome_label_violation(
            simulated_time=sim, label=""
        )


# ---------------------------------------------------------------------------
# 14. NoLookaheadViolation is JSON-serializable
# ---------------------------------------------------------------------------


def test_no_lookahead_violation_is_json_serializable():
    guard = TimeWallGuard()
    sim = _T0
    rec = _make_record(available_at=sim + timedelta(minutes=1))
    v = guard.validate_no_lookahead(rec, sim)
    assert v is not None
    payload = v.to_dict()
    s = json.dumps(payload, sort_keys=True)
    back = json.loads(s)
    assert back["violation_id"] == v.violation_id
    assert back["reason"] == NoLookaheadViolationReason.FUTURE_AVAILABLE_AT
    assert back["phase_12_forbidden"] is True
    assert back["auto_tuning_allowed"] is False
    assert back["trade_authority"] is False
    assert (
        back["simulated_time"] == sim.isoformat()
    )
    assert back["is_no_lookahead_violation"] is True
    assert back["is_trade"] is False
    assert back["is_runtime_patch"] is False
    # SimulationClock + HistoricalRecordTime payloads are JSON
    # serialisable too.
    clk = SimulationClock(start_time_utc=_T0)
    clk.step("5m")
    json.dumps(clk.to_dict(), sort_keys=True)
    h = HistoricalRecordTime(
        event_time=sim,
        available_at=sim,
        ingested_at=sim,
        source="binance_public",
        record_id="r_hrt",
        symbol="BTCUSDT",
        interval="1m",
    )
    json.dumps(h.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# 15. phase_12_forbidden=true everywhere
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_everywhere():
    clk = SimulationClock(start_time_utc=_T0)
    assert clk.to_dict()["phase_12_forbidden"] is True
    h = HistoricalRecordTime(event_time=_T0, available_at=_T0)
    assert h.to_dict()["phase_12_forbidden"] is True
    guard = TimeWallGuard()
    assert guard.phase_12_forbidden is True
    cv = CandleVisibilityGuard()
    assert cv.phase_12_forbidden is True
    # Synthetic violation also carries the flag.
    v = guard.validate_no_lookahead(
        _make_record(available_at=_T0 + timedelta(minutes=1)), _T0
    )
    assert v is not None
    assert v.to_dict()["phase_12_forbidden"] is True
    # The literal "Phase 12" must not appear in the phase identifier
    # as a destination.
    assert "Phase 12" not in PHASE_NAME


# ---------------------------------------------------------------------------
# 16. auto_tuning_allowed=False everywhere
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_everywhere():
    clk = SimulationClock(start_time_utc=_T0)
    assert clk.to_dict()["auto_tuning_allowed"] is False
    h = HistoricalRecordTime(event_time=_T0, available_at=_T0)
    assert h.to_dict()["auto_tuning_allowed"] is False
    guard = TimeWallGuard()
    assert guard.auto_tuning_allowed is False
    cv = CandleVisibilityGuard()
    assert cv.auto_tuning_allowed is False
    v = guard.validate_no_lookahead(
        _make_record(available_at=_T0 + timedelta(seconds=1)), _T0
    )
    assert v is not None
    assert v.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 17. trade_authority=False everywhere
# ---------------------------------------------------------------------------


def test_trade_authority_false_everywhere():
    clk = SimulationClock(start_time_utc=_T0)
    assert clk.to_dict()["trade_authority"] is False
    assert clk.to_dict()["ai_trade_authority"] is False
    h = HistoricalRecordTime(event_time=_T0, available_at=_T0)
    assert h.to_dict()["trade_authority"] is False
    guard = TimeWallGuard()
    assert guard.trade_authority is False
    assert guard.ai_trade_authority is False
    cv = CandleVisibilityGuard()
    assert cv.trade_authority is False
    v = guard.validate_no_lookahead(
        _make_record(available_at=_T0 + timedelta(seconds=1)), _T0
    )
    assert v is not None
    assert v.to_dict()["trade_authority"] is False


# ---------------------------------------------------------------------------
# 18. forbidden fields absent from serialized outputs
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_in_all_outputs():
    clk = SimulationClock(start_time_utc=_T0)
    clk.step("1m")
    h = HistoricalRecordTime(
        event_time=_T0,
        available_at=_T0,
        ingested_at=_T0,
        source="binance_public",
        record_id="rec",
        symbol="BTCUSDT",
        interval="1m",
    )
    guard = TimeWallGuard()
    v = guard.validate_no_lookahead(
        _make_record(available_at=_T0 + timedelta(minutes=1)), _T0
    )
    assert v is not None
    payloads = [
        clk.to_dict(),
        h.to_dict(),
        v.to_dict(),
        guard.make_outcome_label_violation(
            simulated_time=_T0, label="future_top_mover_label"
        ).to_dict(),
        guard.make_unclosed_candle_field_access_violation(
            simulated_time=_T0,
            field_name="high",
            candle_open_time=_T0,
            interval="1m",
        ).to_dict(),
    ]
    for p in payloads:
        assert_no_forbidden_fields(p)
        keys = set(_walk_keys(p))
        assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS), (
            f"forbidden field present in payload: "
            f"{keys & FORBIDDEN_OUTPUT_FIELDS}"
        )
    # The recursive guard rejects hostile payloads.
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"runtime_config_patch": {"x": 1}})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"nested": [{"buy": True}]})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields(
            {"deep": [{"inner": {"leverage": 5}}]}
        )
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"top": {"trading_approved": True}})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"top": {"live_ready": True}})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"top": {"long": True}})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"top": {"short": True}})


# ---------------------------------------------------------------------------
# 19. module does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports_in_module_or_init():
    root = _project_root()
    init_path = root / "app" / "sim" / "__init__.py"
    clock_path = root / "app" / "sim" / "simulation_clock.py"
    guard_path = root / "app" / "sim" / "time_wall_guard.py"

    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in (init_path, clock_path, guard_path):
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
    # Importing app.sim does NOT pull any forbidden module into sys.modules.
    before = set(sys.modules)
    importlib.import_module("app.sim")
    new = set(sys.modules) - before
    for nm in new:
        for bad in forbidden_prefixes:
            assert not nm.startswith(bad), (
                f"importing app.sim pulled forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 20. no DeepSeek / LLM / Telegram / Binance / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_llm_telegram_binance_or_network_path():
    root = _project_root()
    files = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "simulation_clock.py",
        root / "app" / "sim" / "time_wall_guard.py",
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
    # Defensive: reloading the module does not import any forbidden module.
    pre = set(sys.modules)
    importlib.import_module("app.sim.simulation_clock")
    importlib.import_module("app.sim.time_wall_guard")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), (
                f"unexpected import: {nm}"
            )


# ---------------------------------------------------------------------------
# 21. deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output():
    sim = _T0
    # Two clocks given identical inputs reach identical state.
    a = SimulationClock(start_time_utc=sim)
    b = SimulationClock(start_time_utc=sim)
    for d in [60, "1m", 30, "5m", timedelta(hours=1)]:
        a.step(d)
        b.step(d)
    assert a.now() == b.now()
    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(
        b.to_dict(), sort_keys=True
    )
    # Two violations built from identical inputs serialise identically
    # (modulo the per-instance violation_id counter).
    g1 = TimeWallGuard()
    g2 = TimeWallGuard()
    rec = _make_record(available_at=sim + timedelta(seconds=10))
    v1 = g1.validate_no_lookahead(rec, sim)
    v2 = g2.validate_no_lookahead(rec, sim)
    assert v1 is not None and v2 is not None
    p1 = v1.to_dict()
    p2 = v2.to_dict()
    p1.pop("violation_id")
    p2.pop("violation_id")
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
    # Per-guard violation IDs are deterministic given the same call sequence.
    g3 = TimeWallGuard()
    g4 = TimeWallGuard()
    seq_a = [
        g3.validate_no_lookahead(rec, sim).violation_id,  # type: ignore[union-attr]
        g3.validate_no_lookahead(rec, sim).violation_id,  # type: ignore[union-attr]
    ]
    seq_b = [
        g4.validate_no_lookahead(rec, sim).violation_id,  # type: ignore[union-attr]
        g4.validate_no_lookahead(rec, sim).violation_id,  # type: ignore[union-attr]
    ]
    assert seq_a == seq_b


# ---------------------------------------------------------------------------
# Extra: parse_interval_seconds covers the closed taxonomy
# ---------------------------------------------------------------------------


def test_parse_interval_seconds_closed_taxonomy():
    assert parse_interval_seconds("1m") == 60
    assert parse_interval_seconds("5m") == 300
    assert parse_interval_seconds("1h") == 3600
    assert parse_interval_seconds("1d") == 86400
    with pytest.raises(ValueError):
        parse_interval_seconds("2m")
    with pytest.raises(ValueError):
        parse_interval_seconds("")
    with pytest.raises(TypeError):
        parse_interval_seconds(60)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Extra: ensure_utc_aware rejects naive datetime
# ---------------------------------------------------------------------------


def test_ensure_utc_aware_rejects_naive_datetime():
    with pytest.raises(ValueError):
        ensure_utc_aware(
            datetime(2026, 1, 1, 12, 0, 0), "naive"
        )
    # Non-UTC tz is normalised to UTC.
    other = timezone(timedelta(hours=-5))
    out = ensure_utc_aware(
        datetime(2026, 1, 1, 7, 0, 0, tzinfo=other), "non_utc"
    )
    assert out.utcoffset() == timedelta(0)
    assert out == _T0
    with pytest.raises(TypeError):
        ensure_utc_aware("2026-01-01", "string")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Extra: HistoricalRecordTime.available_at >= event_time invariant
# ---------------------------------------------------------------------------


def test_historical_record_time_invariants():
    sim = _T0
    # available_at < event_time is rejected.
    with pytest.raises(ValueError):
        HistoricalRecordTime(
            event_time=sim,
            available_at=sim - timedelta(seconds=1),
        )
    # naive event_time / available_at / ingested_at are rejected.
    with pytest.raises(ValueError):
        HistoricalRecordTime(
            event_time=datetime(2026, 1, 1, 12, 0, 0),
            available_at=sim,
        )
    with pytest.raises(ValueError):
        HistoricalRecordTime(
            event_time=sim,
            available_at=datetime(2026, 1, 1, 12, 0, 0),
        )
    with pytest.raises(ValueError):
        HistoricalRecordTime(
            event_time=sim,
            available_at=sim,
            ingested_at=datetime(2026, 1, 1, 12, 0, 0),
        )
    # Unsupported interval label is rejected.
    with pytest.raises(ValueError):
        HistoricalRecordTime(
            event_time=sim,
            available_at=sim,
            interval="2m",
        )


# ---------------------------------------------------------------------------
# Extra: NoLookaheadViolationReason / Severity closed enums
# ---------------------------------------------------------------------------


def test_no_lookahead_violation_reason_and_severity_closed_enums():
    assert NoLookaheadViolationReason.ALLOWED == frozenset(
        {
            "FUTURE_AVAILABLE_AT",
            "MISSING_AVAILABLE_AT",
            "INGESTED_AT_USED_AS_AVAILABILITY",
            "UNCLOSED_CANDLE_FIELD_ACCESS",
            "OUTCOME_LABEL_DURING_BLIND_WINDOW",
        }
    )
    assert NoLookaheadViolationSeverity.ALLOWED == frozenset(
        {"P0", "P1"}
    )
    # Constructing a violation with an illegal reason / severity raises.
    with pytest.raises(ValueError):
        NoLookaheadViolation(
            violation_id="x",
            reason="NOT_A_REAL_REASON",
            simulated_time=_T0,
        )
    with pytest.raises(ValueError):
        NoLookaheadViolation(
            violation_id="x",
            reason=NoLookaheadViolationReason.FUTURE_AVAILABLE_AT,
            simulated_time=_T0,
            severity="P9",
        )
    with pytest.raises(ValueError):
        NoLookaheadViolation(
            violation_id="",
            reason=NoLookaheadViolationReason.FUTURE_AVAILABLE_AT,
            simulated_time=_T0,
        )


# ---------------------------------------------------------------------------
# Extra: FORBIDDEN_OUTPUT_FIELDS contains the brief-mandated names
# ---------------------------------------------------------------------------


def test_forbidden_output_fields_brief_mandated():
    must_be_forbidden = {
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "entry",
        "exit",
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "target",
        "take_profit",
        "risk_budget",
        "order",
        "execution_command",
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        "signal_to_trade",
        "should_buy",
        "should_short",
        "apply_change",
        "deploy_change",
        "enable_live",
        "live_ready",
        "trading_approved",
    }
    assert must_be_forbidden.issubset(FORBIDDEN_OUTPUT_FIELDS)


# ---------------------------------------------------------------------------
# Extra: TimeWallGuard does not place orders / does not steer trades
# ---------------------------------------------------------------------------


def test_time_wall_guard_does_not_steer_trades():
    guard = TimeWallGuard()
    # No public method on the guard exposes a trade verb.
    public = {n for n in dir(guard) if not n.startswith("_")}
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
    assert public.isdisjoint(forbidden_verbs)
    # Same for the other public classes.
    for inst in (
        SimulationClock(start_time_utc=_T0),
        CandleVisibilityGuard(),
    ):
        public_i = {n for n in dir(inst) if not n.startswith("_")}
        assert public_i.isdisjoint(forbidden_verbs)
