"""Unit tests for Phase 11C.1D-D / PR108 - Simulated Capital Safety
Floor / Kill Switch / No Negative Equity Guard.

These tests are the safety contract for PR108. They prove that the
(PR98) Simulated Capital Flow engine, with the PR108 capital-safety
layer:

  * never lets the simulated equity silently go negative (no-negative
    equity guard clamps the cash balance at the capital floor and
    books a deterministic ``liquidation_shortfall`` WITHOUT hiding the
    realised loss in the ledger),
  * force-exits every open simulated position and latches the kill
    switch when the marked equity hits the capital floor
    (``SIM_CAPITAL_EXHAUSTED`` / ``SIM_LIQUIDATION``) or breaches the
    configured hard drawdown limit (``MAX_DRAWDOWN_LIMIT_REACHED`` /
    ``RISK_HALT``),
  * refuses to OPEN any new simulated position after the kill switch
    is latched (raises the predictable, paper-only
    :class:`SimAccountHaltedError`, NEVER a bare RuntimeError),
  * exposes the pre-entry capital/risk gate
    (:meth:`can_open_position`) with a closed
    :class:`CapitalRejectReason` taxonomy,
  * records forced capital-safety exits in the trade ledger with the
    truthful realised PnL + a capital-safety exit reason,
  * is deterministic.

Hard safety boundary asserted here (unchanged by PR108):

  - simulated_only = True
  - no_live_order = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - telegram_outbound_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.sim import (
    CapitalRejectReason,
    ConservativeAssumption,
    FillReason,
    ForcedExitReason,
    MockFill,
    MockOrderSide,
    RiskHaltReason,
    SimAccountHaltedError,
    SimulatedCapitalConfig,
    SimulatedCapitalFlowEngine,
    TradeFailureFlag,
    TradeOutcome,
    assert_no_forbidden_fields,
)


_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_fill(
    *,
    order_id: str = "mock_order_00000001",
    fill_id: str = "mock_fill_00000001",
    symbol: str = "BTCUSDT",
    side: str = MockOrderSide.BUY,
    filled_qty: float = 1.0,
    fill_price: float = 100.0,
    fee: float = 0.0,
    slippage_bps: float = 0.0,
    fill_reason: str = FillReason.MARKET_FILL,
    filled_at_simulated: datetime = None,
    funding_impact=None,
    evidence_refs=(),
) -> MockFill:
    if filled_at_simulated is None:
        filled_at_simulated = _T0
    return MockFill(
        fill_id=fill_id,
        order_id=order_id,
        symbol=symbol,
        side=side,
        filled_qty=filled_qty,
        fill_price=fill_price,
        fee=fee,
        slippage_bps=slippage_bps,
        fill_reason=fill_reason,
        filled_at_simulated=filled_at_simulated,
        conservative_assumption=(
            ConservativeAssumption.TAKER_FEE_APPLIED,
        ),
        latency_bps=None,
        funding_impact=funding_impact,
        reference_price=fill_price,
        evidence_refs=evidence_refs,
    )


def _make_engine(**cfg_kwargs) -> SimulatedCapitalFlowEngine:
    cfg_kwargs.setdefault("initial_capital", 100.0)
    return SimulatedCapitalFlowEngine(
        config=SimulatedCapitalConfig(**cfg_kwargs)
    )


# ---------------------------------------------------------------------------
# 1. Defaults are conservative + serialisable
# ---------------------------------------------------------------------------


def test_capital_safety_defaults_conservative():
    cfg = SimulatedCapitalConfig(initial_capital=100.0)
    assert cfg.capital_floor == 0.0
    assert cfg.no_negative_equity_guard is True
    assert cfg.halt_on_capital_exhaustion is True
    assert cfg.max_drawdown_halt_pct is None
    assert cfg.min_equity_to_open is None
    d = cfg.to_dict()
    assert d["capital_floor"] == 0.0
    assert d["no_negative_equity_guard"] is True
    assert d["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 2. Pre-entry gate refuses an unaffordable new position
# ---------------------------------------------------------------------------


def test_pre_entry_gate_rejects_insufficient_equity():
    eng = _make_engine(initial_capital=100.0)
    # Open a position consuming most of the free equity.
    eng.consume_fill(
        _make_fill(filled_qty=0.8, fill_price=100.0)  # notional 80
    )
    # Available = 100 - 80 = 20. A 30-notional new open is refused.
    ok, reason = eng.can_open_position(notional=30.0)
    assert ok is False
    assert reason == CapitalRejectReason.INSUFFICIENT_EQUITY
    # A 10-notional new open is allowed.
    ok2, reason2 = eng.can_open_position(notional=10.0)
    assert ok2 is True
    assert reason2 is None


def test_pre_entry_gate_uses_mark_price_for_notional():
    eng = _make_engine(initial_capital=100.0)
    eng.consume_fill(
        _make_fill(symbol="ETHUSDT", filled_qty=0.9, fill_price=100.0)
    )  # notional 90 -> available 10
    # requested_qty 0.2 at last mark 100 => notional 20 > available 10.
    ok, reason = eng.can_open_position(
        symbol="ETHUSDT", requested_qty=0.2
    )
    assert ok is False
    assert reason == CapitalRejectReason.INSUFFICIENT_EQUITY


def test_pre_entry_gate_respects_max_active_positions():
    eng = _make_engine(initial_capital=10_000.0, max_active_positions=1)
    eng.consume_fill(_make_fill(filled_qty=1.0, fill_price=100.0))
    ok, reason = eng.can_open_position(notional=10.0)
    assert ok is False
    assert reason == CapitalRejectReason.MAX_ACTIVE_POSITIONS_REACHED


# ---------------------------------------------------------------------------
# 3. No-negative-equity guard clamps a losing close at the floor
# ---------------------------------------------------------------------------


def test_no_negative_equity_guard_clamps_close():
    eng = _make_engine(initial_capital=100.0)
    # Open a position whose notional (200) exceeds the equity (100).
    eng.consume_fill(
        _make_fill(filled_qty=2.0, fill_price=100.0, fee=0.0)
    )
    # Close at 40: gross = (40-100)*2 = -120 -> raw cash would be -20.
    entry = eng.consume_fill(
        _make_fill(
            order_id="o2",
            fill_id="f2",
            side=MockOrderSide.SELL,
            filled_qty=2.0,
            fill_price=40.0,
            fee=0.0,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    assert entry is not None
    # The ledger keeps the truthful realised loss (NOT hidden).
    assert entry.net_pnl == pytest.approx(-120.0)
    assert entry.outcome == TradeOutcome.LOSS
    # But the account equity floors at 0 (no silent negative equity).
    state = eng.get_state()
    assert state.exchange_equity == pytest.approx(0.0)
    assert eng.current_marked_equity() == pytest.approx(0.0)
    assert eng.final_equity == pytest.approx(0.0)
    assert state.capital_exhausted is True
    # The excess loss is booked as a deterministic liquidation shortfall.
    assert eng.liquidation_shortfall == pytest.approx(20.0)


def test_no_negative_equity_guard_can_be_disabled():
    eng = _make_engine(
        initial_capital=100.0, no_negative_equity_guard=False
    )
    eng.consume_fill(_make_fill(filled_qty=2.0, fill_price=100.0))
    eng.consume_fill(
        _make_fill(
            order_id="o2",
            fill_id="f2",
            side=MockOrderSide.SELL,
            filled_qty=2.0,
            fill_price=40.0,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    # With the guard OFF the cash balance is allowed to go negative
    # (documents the toggle; default keeps the guard ON).
    assert eng.get_state().exchange_equity == pytest.approx(-20.0)


# ---------------------------------------------------------------------------
# 4. enforce_capital_safety force-exits + latches the kill switch on
#    capital exhaustion (marked equity at/under the floor)
# ---------------------------------------------------------------------------


def test_enforce_capital_safety_liquidates_on_exhaustion():
    eng = _make_engine(initial_capital=100.0)
    eng.consume_fill(
        _make_fill(filled_qty=2.0, fill_price=100.0)
    )  # notional 200
    # Mark the position deeply underwater: unrealised = (40-100)*2=-120
    # -> marked equity = 100 - 120 = -20 <= floor(0).
    eng.apply_mark_prices(
        {"BTCUSDT": 40.0}, _T0 + timedelta(minutes=1)
    )
    event = eng.enforce_capital_safety(_T0 + timedelta(minutes=1))
    assert event is not None
    assert event["halt_reason"] == RiskHaltReason.CAPITAL_EXHAUSTED
    assert event["forced_exit_reason"] == ForcedExitReason.SIM_LIQUIDATION
    assert event["capital_exhausted"] is True
    assert event["forced_exit_count"] == 1
    # Position force-closed through the simulated flow.
    assert eng.get_positions() == ()
    assert eng.account_halted is True
    assert eng.halted_by_risk is True
    assert eng.halt_reason == RiskHaltReason.CAPITAL_EXHAUSTED
    assert eng.capital_exhausted is True
    assert eng.forced_exit_count == 1
    assert eng.capital_exhaustion_event_count == 1
    # No silent negative equity.
    assert eng.final_equity == pytest.approx(0.0)
    # The forced exit was recorded in the ledger with the SIM_LIQUIDATION
    # exit reason + the truthful realised loss + the forced-exit flag.
    ledger = eng.get_ledger()
    assert len(ledger) == 1
    e = ledger.entries[0]
    assert e.exit_reason == ForcedExitReason.SIM_LIQUIDATION
    assert TradeFailureFlag.FORCED_EXIT_TRIGGERED in e.failure_flags
    assert e.net_pnl == pytest.approx(-120.0)


# ---------------------------------------------------------------------------
# 5. enforce_capital_safety force-exits + halts on the hard drawdown
#    kill switch (equity still positive)
# ---------------------------------------------------------------------------


def test_enforce_capital_safety_halts_on_max_drawdown():
    eng = _make_engine(
        initial_capital=1_000.0, max_drawdown_halt_pct=0.2
    )
    eng.consume_fill(
        _make_fill(filled_qty=5.0, fill_price=100.0)
    )  # notional 500
    # Peak marked equity = 1000 (mark unchanged at 100).
    eng.apply_mark_prices(
        {"BTCUSDT": 100.0}, _T0 + timedelta(minutes=1)
    )
    # Drop to 60: unrealised = (60-100)*5 = -200 -> marked = 800,
    # drawdown vs peak 1000 = 0.2 >= 0.2.
    eng.apply_mark_prices(
        {"BTCUSDT": 60.0}, _T0 + timedelta(minutes=2)
    )
    event = eng.enforce_capital_safety(_T0 + timedelta(minutes=2))
    assert event is not None
    assert event["halt_reason"] == (
        RiskHaltReason.MAX_DRAWDOWN_LIMIT_REACHED
    )
    assert event["forced_exit_reason"] == ForcedExitReason.RISK_HALT
    # Drawdown halt is NOT a capital exhaustion (equity still positive).
    assert eng.capital_exhausted is False
    assert eng.account_halted is True
    assert eng.halt_reason == RiskHaltReason.MAX_DRAWDOWN_LIMIT_REACHED
    assert eng.get_positions() == ()
    assert eng.final_equity == pytest.approx(800.0)
    e = eng.get_ledger().entries[0]
    assert e.exit_reason == ForcedExitReason.RISK_HALT


# ---------------------------------------------------------------------------
# 6. A halted account cannot open new positions (kill switch latched)
# ---------------------------------------------------------------------------


def test_halted_account_refuses_new_open():
    eng = _make_engine(initial_capital=100.0)
    eng.consume_fill(_make_fill(filled_qty=2.0, fill_price=100.0))
    eng.apply_mark_prices(
        {"BTCUSDT": 40.0}, _T0 + timedelta(minutes=1)
    )
    eng.enforce_capital_safety(_T0 + timedelta(minutes=1))
    assert eng.account_halted is True
    # The pre-entry gate refuses a new open.
    ok, reason = eng.can_open_position(notional=10.0)
    assert ok is False
    assert reason == CapitalRejectReason.CAPITAL_EXHAUSTED
    # Trying to consume a NEW open fill raises the predictable,
    # paper-only SimAccountHaltedError (NOT a bare RuntimeError abort).
    with pytest.raises(SimAccountHaltedError) as ei:
        eng.consume_fill(
            _make_fill(
                order_id="o9",
                fill_id="f9",
                symbol="ETHUSDT",
                side=MockOrderSide.BUY,
                filled_qty=1.0,
                fill_price=2_000.0,
                filled_at_simulated=_T0 + timedelta(minutes=2),
            )
        )
    assert ei.value.reason == RiskHaltReason.CAPITAL_EXHAUSTED


def test_halt_is_latched_not_auto_released():
    eng = _make_engine(
        initial_capital=1_000.0, max_drawdown_halt_pct=0.2
    )
    eng.consume_fill(_make_fill(filled_qty=5.0, fill_price=100.0))
    eng.apply_mark_prices({"BTCUSDT": 100.0}, _T0 + timedelta(minutes=1))
    eng.apply_mark_prices({"BTCUSDT": 60.0}, _T0 + timedelta(minutes=2))
    eng.enforce_capital_safety(_T0 + timedelta(minutes=2))
    assert eng.account_halted is True
    # Even after the price fully recovers the kill switch stays latched.
    eng.apply_mark_prices({"BTCUSDT": 200.0}, _T0 + timedelta(minutes=3))
    event = eng.enforce_capital_safety(_T0 + timedelta(minutes=3))
    assert event is None  # nothing new triggered; still halted
    assert eng.account_halted is True
    ok, _reason = eng.can_open_position(notional=10.0)
    assert ok is False


# ---------------------------------------------------------------------------
# 7. min_equity is tracked + capital_safety_snapshot is complete + safe
# ---------------------------------------------------------------------------


def test_capital_safety_snapshot_fields_and_min_equity():
    eng = _make_engine(initial_capital=100.0, max_drawdown_halt_pct=0.5)
    eng.consume_fill(_make_fill(filled_qty=1.0, fill_price=100.0))
    eng.apply_mark_prices({"BTCUSDT": 90.0}, _T0 + timedelta(minutes=1))
    snap = eng.capital_safety_snapshot()
    for key in (
        "initial_capital",
        "final_equity",
        "min_equity",
        "max_drawdown",
        "max_drawdown_limit",
        "capital_floor",
        "capital_exhausted",
        "halted_by_risk",
        "risk_halt_reason",
        "forced_exit_count",
        "capital_reject_count",
        "capital_exhaustion_event_count",
        "liquidation_like_event_count",
        "liquidation_shortfall",
        "no_negative_equity_guard",
    ):
        assert key in snap, f"missing snapshot field {key!r}"
    # min_equity tracked the dip (unrealised -10 -> marked 90).
    assert snap["min_equity"] == pytest.approx(90.0)
    assert snap["max_drawdown_limit"] == pytest.approx(0.5)
    assert snap["phase_12_forbidden"] is True
    assert snap["trade_authority"] is False
    assert snap["ai_trade_authority"] is False
    # JSON round-trip + forbidden-field guard.
    assert json.dumps(snap, sort_keys=True)
    assert_no_forbidden_fields(snap)


def test_register_capital_reject_counts():
    eng = _make_engine(initial_capital=100.0)
    eng.register_capital_reject(CapitalRejectReason.INSUFFICIENT_EQUITY)
    eng.register_capital_reject(CapitalRejectReason.CAPITAL_EXHAUSTED)
    assert eng.capital_reject_count == 2
    with pytest.raises(ValueError):
        eng.register_capital_reject("not_a_reason")


# ---------------------------------------------------------------------------
# 8. Determinism: identical sequences -> identical capital-safety state
# ---------------------------------------------------------------------------


def test_capital_safety_deterministic():
    def run() -> str:
        eng = _make_engine(
            initial_capital=100.0, max_drawdown_halt_pct=0.3
        )
        eng.consume_fill(_make_fill(filled_qty=3.0, fill_price=100.0))
        eng.apply_mark_prices(
            {"BTCUSDT": 100.0}, _T0 + timedelta(minutes=1)
        )
        eng.apply_mark_prices(
            {"BTCUSDT": 50.0}, _T0 + timedelta(minutes=2)
        )
        eng.enforce_capital_safety(_T0 + timedelta(minutes=2))
        return json.dumps(
            eng.capital_safety_snapshot(), sort_keys=True
        )

    assert run() == run()


# ---------------------------------------------------------------------------
# 9. forced_exit honours the capital-safety exit_reason override
# ---------------------------------------------------------------------------


def test_forced_exit_reason_override():
    eng = _make_engine(initial_capital=1_000.0)
    eng.consume_fill(_make_fill(filled_qty=1.0, fill_price=100.0))
    entry = eng.forced_exit(
        "BTCUSDT",
        exit_price=90.0,
        simulated_time=_T0 + timedelta(minutes=1),
        exit_reason_override=ForcedExitReason.FORCED_CAPITAL_SAFETY_EXIT,
    )
    assert entry is not None
    assert entry.exit_reason == (
        ForcedExitReason.FORCED_CAPITAL_SAFETY_EXIT
    )
    assert TradeFailureFlag.FORCED_EXIT_TRIGGERED in entry.failure_flags


# ---------------------------------------------------------------------------
# 10. The state payload exposes the capital-safety reporting fields
# ---------------------------------------------------------------------------


def test_state_payload_exposes_capital_safety_fields():
    eng = _make_engine(initial_capital=100.0, max_drawdown_halt_pct=0.4)
    eng.consume_fill(_make_fill(filled_qty=1.0, fill_price=100.0))
    d = eng.get_state().to_dict()
    for key in (
        "account_halted",
        "halted_by_risk",
        "risk_halt_reason",
        "capital_exhausted",
        "min_equity",
        "max_drawdown_limit",
        "forced_exit_count",
        "liquidation_like_event_count",
        "liquidation_shortfall",
    ):
        assert key in d, f"missing state field {key!r}"
    assert d["account_halted"] is False
    assert d["capital_exhausted"] is False
    assert d["max_drawdown_limit"] == pytest.approx(0.4)
