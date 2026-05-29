"""Unit tests for Phase 11C.1D-D-E / PR98 / Simulated Capital Flow +
Trade Ledger v0.

These tests are the safety contract for this PR. If any of them fails
the module is not safe to merge.

Hard safety boundary covered by these tests:

  - mode = paper
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
  - live_trading = False
  - live_capital_enabled = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - signed_endpoint_reachable = False
  - private_websocket_reachable = False
  - account_endpoint_reachable = False
  - order_endpoint_reachable = False
  - position_endpoint_reachable = False
  - leverage_endpoint_reachable = False
  - margin_endpoint_reachable = False
  - real_exchange_order_path = False
  - real_capital = False
  - telegram_outbound_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

The tests also assert that the new modules:

  - do NOT import app.risk / app.execution / app.exchanges /
    app.telegram / app.config
  - do NOT pull any DeepSeek / LLM / Telegram / Binance / network
    transport
  - emit no forbidden trade / runtime-config / "live ready" field
  - emit no real exchange order id / api key / api secret /
    real-account / signed-endpoint reference
  - are deterministic
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
    SIMULATED_CAPITAL_FLOW_PHASE_NAME,
    TRADE_LEDGER_PHASE_NAME,
    CapitalFrozenError,
    ConservativeAssumption,
    EquityTimeseriesPoint,
    FillReason,
    HistoricalKlineRecord,
    HistoricalMarketStore,
    MockExchange,
    MockExchangeConfig,
    MockFill,
    MockOrderSide,
    MockOrderType,
    OrderRequest,
    PositionSide,
    PositionStatus,
    ReplayFeedBatch,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
    RiskFreezeReason,
    SimulatedCapitalConfig,
    SimulatedCapitalFlowEngine,
    SimulatedCapitalState,
    SimulatedPosition,
    SimulationClock,
    TradeFailureFlag,
    TradeLedger,
    TradeLedgerEntry,
    TradeLedgerSummary,
    TradeOutcome,
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


def _collect_imported_modules(source_text: str):
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


def _collect_code_identifiers(source_text: str):
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


def _make_fill(
    *,
    order_id: str = "mock_order_00000001",
    fill_id: str = "mock_fill_00000001",
    symbol: str = "BTCUSDT",
    side: str = MockOrderSide.BUY,
    filled_qty: float = 1.0,
    fill_price: float = 100.0,
    fee: float = 0.04,
    slippage_bps: float = 5.0,
    fill_reason: str = FillReason.MARKET_FILL,
    filled_at_simulated: datetime = None,
    funding_impact=None,
    evidence_refs=(),
    conservative_assumption=(
        ConservativeAssumption.TAKER_FEE_APPLIED,
        ConservativeAssumption.SLIPPAGE_APPLIED,
    ),
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
        conservative_assumption=conservative_assumption,
        latency_bps=None,
        funding_impact=funding_impact,
        reference_price=fill_price,
        evidence_refs=evidence_refs,
    )


def _make_engine(**cfg_kwargs) -> SimulatedCapitalFlowEngine:
    cfg_kwargs.setdefault("initial_capital", 10_000.0)
    return SimulatedCapitalFlowEngine(
        config=SimulatedCapitalConfig(**cfg_kwargs)
    )


# ---------------------------------------------------------------------------
# 1. initialises capital state from initial_capital
# ---------------------------------------------------------------------------


def test_capital_state_initialised_from_initial_capital():
    eng = _make_engine(initial_capital=12_345.6)
    # No event yet -> caller MUST supply simulated_time.
    state = eng.get_state(simulated_time=_T0)
    assert isinstance(state, SimulatedCapitalState)
    assert state.initial_capital == 12_345.6
    assert state.exchange_equity == 12_345.6
    assert state.locked_profit == 0.0
    assert state.open_risk == 0.0
    assert state.unrealized_pnl == 0.0
    assert state.realized_pnl == 0.0
    assert state.total_lifetime_equity == 12_345.6
    assert state.drawdown == 0.0
    assert state.active_positions == 0
    assert state.risk_state == RiskFreezeReason.NORMAL
    assert state.capital_frozen is False
    assert state.freeze_reason is None
    assert state.simulated_only is True
    assert state.no_live_order is True
    assert state.live_capital_enabled is False
    assert state.phase_12_forbidden is True
    assert state.trade_authority is False
    assert state.auto_tuning_allowed is False


# ---------------------------------------------------------------------------
# 2. mock fill opens simulated position
# ---------------------------------------------------------------------------


def test_mock_fill_opens_simulated_position():
    eng = _make_engine()
    fill = _make_fill(
        side=MockOrderSide.BUY,
        filled_qty=2.0,
        fill_price=100.0,
        fee=0.08,
    )
    out = eng.consume_fill(fill)
    # Open does not produce a ledger entry.
    assert out is None
    positions = eng.get_positions()
    assert len(positions) == 1
    p = positions[0]
    assert p.symbol == "BTCUSDT"
    assert p.side == PositionSide.LONG
    assert p.qty == 2.0
    assert p.avg_entry_price == 100.0
    assert p.status == PositionStatus.OPEN
    assert p.fees_paid == 0.08
    assert p.simulated_only is True
    assert p.no_live_order is True
    assert p.live_capital_enabled is False
    # Fill fee deducted from exchange_equity.
    state = eng.get_state()
    assert state.exchange_equity == pytest.approx(10_000.0 - 0.08)
    assert state.active_positions == 1
    # SELL-first opens a SHORT.
    eng2 = _make_engine()
    eng2.consume_fill(
        _make_fill(
            symbol="ETHUSDT",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=2_000.0,
        )
    )
    p2 = eng2.get_positions()[0]
    assert p2.side == PositionSide.SHORT


# ---------------------------------------------------------------------------
# 3. opposite-side fill closes or reduces position
# ---------------------------------------------------------------------------


def test_opposite_side_fill_reduces_then_closes_position():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=2.0,
            fill_price=100.0,
            fee=0.08,
            filled_at_simulated=_T0,
        )
    )
    # Reduce by 1.0.
    out_reduce = eng.consume_fill(
        _make_fill(
            order_id="mock_order_00000002",
            fill_id="mock_fill_00000002",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=110.0,
            fee=0.044,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    # Reduction does not produce a ledger entry (still open).
    assert out_reduce is None
    p = eng.get_positions()[0]
    assert p.qty == 1.0
    assert p.status == PositionStatus.OPEN
    assert p.realized_pnl == pytest.approx(10.0)
    # Now close the remaining 1.0.
    out_close = eng.consume_fill(
        _make_fill(
            order_id="mock_order_00000003",
            fill_id="mock_fill_00000003",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=115.0,
            fee=0.046,
            filled_at_simulated=_T0 + timedelta(minutes=2),
        )
    )
    assert isinstance(out_close, TradeLedgerEntry)
    assert out_close.symbol == "BTCUSDT"
    assert out_close.outcome == TradeOutcome.WIN
    # Ledger has one entry.
    assert len(eng.get_ledger()) == 1
    # No more open positions.
    assert eng.get_positions() == ()


# ---------------------------------------------------------------------------
# 4. fees / slippage reduce equity
# ---------------------------------------------------------------------------


def test_fees_and_slippage_reduce_equity():
    eng = _make_engine(initial_capital=1_000.0)
    fill = _make_fill(
        side=MockOrderSide.BUY,
        filled_qty=1.0,
        fill_price=100.0,
        fee=1.5,
        slippage_bps=10.0,
    )
    eng.consume_fill(fill)
    state = eng.get_state()
    assert state.exchange_equity == pytest.approx(1_000.0 - 1.5)
    p = eng.get_positions()[0]
    assert p.fees_paid == 1.5
    # slippage_paid = price * qty * bps/10000 = 100 * 1 * 10/10000 = 0.1
    assert p.slippage_paid == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# 5. realized PnL computed deterministically
# ---------------------------------------------------------------------------


def test_realized_pnl_deterministic_across_two_runs():
    def run() -> List[float]:
        eng = _make_engine()
        eng.consume_fill(
            _make_fill(
                side=MockOrderSide.BUY,
                filled_qty=2.0,
                fill_price=100.0,
                fee=0.08,
                filled_at_simulated=_T0,
            )
        )
        out = eng.consume_fill(
            _make_fill(
                order_id="mock_order_00000002",
                fill_id="mock_fill_00000002",
                side=MockOrderSide.SELL,
                filled_qty=2.0,
                fill_price=120.0,
                fee=0.096,
                filled_at_simulated=_T0 + timedelta(minutes=5),
            )
        )
        assert out is not None
        return [
            out.net_pnl,
            eng.get_state().realized_pnl,
            eng.get_state().exchange_equity,
        ]

    a = run()
    b = run()
    assert a == b
    # Gross = (120 - 100) * 2 = 40; net = 40 - 0.08 - 0.096 = 39.824
    assert a[0] == pytest.approx(40.0 - 0.08 - 0.096)
    assert a[1] == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# 6. unrealized PnL updates from visible mark price / batch price
# ---------------------------------------------------------------------------


def test_unrealized_pnl_updates_from_mark_price_and_batch():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    eng.apply_mark_prices(
        {"BTCUSDT": 110.0}, _T0 + timedelta(minutes=1)
    )
    p = eng.get_positions()[0]
    assert p.unrealized_pnl == pytest.approx(10.0)
    state = eng.get_state()
    assert state.unrealized_pnl == pytest.approx(10.0)
    # ReplayFeedBatch path.
    store = HistoricalMarketStore()
    open_time = _T0 + timedelta(minutes=2)
    store.add_record(
        HistoricalKlineRecord(
            symbol="BTCUSDT",
            interval="1m",
            open_time=open_time,
            open=108.0,
            high=115.0,
            low=107.0,
            close=112.0,
            volume=10.0,
            available_at=open_time + timedelta(seconds=60),
            source="binance_public",
            record_id="k1",
        )
    )
    end_time = open_time + timedelta(minutes=5)
    clock = SimulationClock(
        start_time_utc=open_time,
        end_time_utc=end_time,
        monotonic_forward_only=True,
    )
    cfg = ReplayFeedProviderConfig(
        start_time=open_time,
        end_time=end_time,
        step_interval=timedelta(minutes=1),
    )
    provider = ReplayFeedProvider(store=store, clock=clock, config=cfg)
    batch = provider.next_batch()
    eng.apply_replay_batch(batch)
    p = eng.get_positions()[0]
    assert p.unrealized_pnl == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# 7. open_risk updates with active positions
# ---------------------------------------------------------------------------


def test_open_risk_updates_with_active_positions():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=2.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    s1 = eng.get_state()
    assert s1.open_risk == pytest.approx(200.0)
    assert s1.active_positions == 1
    eng.consume_fill(
        _make_fill(
            order_id="mock_order_00000002",
            fill_id="mock_fill_00000002",
            symbol="ETHUSDT",
            side=MockOrderSide.SELL,
            filled_qty=3.0,
            fill_price=2_000.0,
            fee=0.0,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    s2 = eng.get_state()
    assert s2.open_risk == pytest.approx(200.0 + 3.0 * 2_000.0)
    assert s2.active_positions == 2
    # Close one position, open_risk drops.
    eng.consume_fill(
        _make_fill(
            order_id="mock_order_00000003",
            fill_id="mock_fill_00000003",
            side=MockOrderSide.SELL,
            filled_qty=2.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0 + timedelta(minutes=2),
        )
    )
    s3 = eng.get_state()
    assert s3.active_positions == 1
    assert s3.open_risk == pytest.approx(3.0 * 2_000.0)


# ---------------------------------------------------------------------------
# 8. drawdown updates from equity timeseries
# ---------------------------------------------------------------------------


def test_drawdown_updates_from_equity_timeseries():
    eng = _make_engine(initial_capital=1_000.0)
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    # Push mark UP -> peak rises.
    eng.apply_mark_prices(
        {"BTCUSDT": 200.0}, _T0 + timedelta(minutes=1)
    )
    s_peak = eng.get_state()
    assert s_peak.unrealized_pnl == pytest.approx(100.0)
    assert s_peak.drawdown == 0.0
    peak_equity = s_peak.total_lifetime_equity
    # Push mark DOWN -> drawdown rises.
    eng.apply_mark_prices(
        {"BTCUSDT": 150.0}, _T0 + timedelta(minutes=2)
    )
    s_dd = eng.get_state()
    assert s_dd.unrealized_pnl == pytest.approx(50.0)
    expected_dd = (peak_equity - (1_000.0 + 50.0)) / peak_equity
    assert s_dd.drawdown == pytest.approx(expected_dd)
    # Equity timeseries records the moves.
    ts = eng.get_equity_timeseries()
    assert len(ts) >= 3
    drawdowns = [pt.drawdown for pt in ts]
    # The last drawdown is positive; the peak point's drawdown is 0.
    assert any(d > 0.0 for d in drawdowns)
    assert drawdowns[-1] == pytest.approx(expected_dd)


# ---------------------------------------------------------------------------
# 9. locked_profit is not reused when locked_profit_reuse_allowed=false
# ---------------------------------------------------------------------------


def test_locked_profit_not_reused_when_disallowed():
    cfg = SimulatedCapitalConfig(
        initial_capital=1_000.0,
        profit_lock_fraction=1.0,
        locked_profit_reuse_allowed=False,
    )
    eng = SimulatedCapitalFlowEngine(config=cfg)
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    out = eng.consume_fill(
        _make_fill(
            order_id="mock_order_00000002",
            fill_id="mock_fill_00000002",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=120.0,
            fee=0.0,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    assert isinstance(out, TradeLedgerEntry)
    assert out.outcome == TradeOutcome.WIN
    assert out.locked_profit_delta == pytest.approx(20.0)
    state = eng.get_state()
    # Net profit was 20; profit_lock_fraction=1.0 -> all 20 locked.
    assert state.locked_profit == pytest.approx(20.0)
    # exchange_equity = initial + realized - locked = 1000 + 20 - 20.
    assert state.exchange_equity == pytest.approx(1_000.0)
    # available_capital_for_new_exposure excludes locked_profit.
    avail_no_reuse = eng.available_capital_for_new_exposure()
    assert avail_no_reuse == pytest.approx(1_000.0)
    # Toggle to allow reuse: a fresh engine re-runs the same flow.
    cfg2 = SimulatedCapitalConfig(
        initial_capital=1_000.0,
        profit_lock_fraction=1.0,
        locked_profit_reuse_allowed=True,
    )
    eng2 = SimulatedCapitalFlowEngine(config=cfg2)
    eng2.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    eng2.consume_fill(
        _make_fill(
            order_id="mock_order_00000002",
            fill_id="mock_fill_00000002",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=120.0,
            fee=0.0,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    # When reuse allowed, profit-lock is NOT applied at all in v0.
    assert eng2.get_state().locked_profit == 0.0


# ---------------------------------------------------------------------------
# 10. capital freezes after configured drawdown threshold
# ---------------------------------------------------------------------------


def test_capital_freezes_after_max_drawdown_pause_pct():
    cfg = SimulatedCapitalConfig(
        initial_capital=1_000.0,
        max_drawdown_pause_pct=0.05,  # 5%
    )
    eng = SimulatedCapitalFlowEngine(config=cfg)
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    # Push mark up to set a peak (peak = 1000 + 50 = 1050).
    eng.apply_mark_prices({"BTCUSDT": 150.0}, _T0 + timedelta(minutes=1))
    # Now crash. unrealised = -100, marked equity = 900, drawdown vs
    # peak 1050 is ~14.3% > 5%.
    eng.apply_mark_prices({"BTCUSDT": 0.1}, _T0 + timedelta(minutes=2))
    state = eng.get_state()
    assert state.capital_frozen is True
    assert state.freeze_reason == RiskFreezeReason.MAX_DRAWDOWN_EXCEEDED
    assert state.risk_state == RiskFreezeReason.MAX_DRAWDOWN_EXCEEDED
    # Opening a NEW simulated position is refused.
    with pytest.raises(CapitalFrozenError):
        eng.consume_fill(
            _make_fill(
                order_id="mock_order_00000002",
                fill_id="mock_fill_00000002",
                symbol="ETHUSDT",
                side=MockOrderSide.BUY,
                filled_qty=1.0,
                fill_price=2_000.0,
                fee=0.0,
                filled_at_simulated=_T0 + timedelta(minutes=3),
            )
        )


# ---------------------------------------------------------------------------
# 11. forced exit produces ledger entry
# ---------------------------------------------------------------------------


def test_forced_exit_produces_ledger_entry():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    entry = eng.forced_exit(
        "BTCUSDT",
        exit_price=90.0,
        simulated_time=_T0 + timedelta(minutes=1),
        fee=0.05,
        slippage_bps=10.0,
        evidence_refs=("ev:liquidation",),
    )
    assert isinstance(entry, TradeLedgerEntry)
    assert entry.exit_reason == "SIMULATED_FORCED_EXIT_CLOSE"
    assert TradeFailureFlag.FORCED_EXIT_TRIGGERED in entry.failure_flags
    assert entry.outcome == TradeOutcome.LOSS
    # Net = -10 - 0.05 fees = -10.05.
    assert entry.net_pnl == pytest.approx(-10.05)
    # Ledger appended.
    assert len(eng.get_ledger()) == 1
    # Position closed.
    assert eng.get_positions() == ()


# ---------------------------------------------------------------------------
# 12. funding impact can be applied if present
# ---------------------------------------------------------------------------


def test_funding_impact_applied_if_present():
    eng = _make_engine(initial_capital=1_000.0)
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    eq_before = eng.get_state().exchange_equity
    eng.apply_funding(
        "BTCUSDT",
        funding_amount=-0.25,
        simulated_time=_T0 + timedelta(minutes=1),
    )
    eq_after = eng.get_state().exchange_equity
    assert eq_after == pytest.approx(eq_before - 0.25)
    p = eng.get_positions()[0]
    assert p.funding_paid == pytest.approx(-0.25)
    # Now close the trade and confirm the funding flowed into net_pnl.
    out = eng.consume_fill(
        _make_fill(
            order_id="mock_order_00000002",
            fill_id="mock_fill_00000002",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0 + timedelta(minutes=2),
        )
    )
    assert isinstance(out, TradeLedgerEntry)
    # Gross 0, fees 0, funding -0.25 -> net -0.25.
    assert out.net_pnl == pytest.approx(-0.25)


# ---------------------------------------------------------------------------
# 13. trade ledger appends and summarizes entries deterministically
# ---------------------------------------------------------------------------


def test_trade_ledger_appends_and_summarises_deterministically():
    def run():
        eng = _make_engine()
        # Trade 1: WIN +10
        eng.consume_fill(
            _make_fill(
                order_id="o1",
                fill_id="f1",
                side=MockOrderSide.BUY,
                filled_qty=1.0,
                fill_price=100.0,
                fee=0.0,
                filled_at_simulated=_T0,
            )
        )
        eng.consume_fill(
            _make_fill(
                order_id="o2",
                fill_id="f2",
                side=MockOrderSide.SELL,
                filled_qty=1.0,
                fill_price=110.0,
                fee=0.0,
                filled_at_simulated=_T0 + timedelta(minutes=1),
            )
        )
        # Trade 2: LOSS -5
        eng.consume_fill(
            _make_fill(
                order_id="o3",
                fill_id="f3",
                symbol="ETHUSDT",
                side=MockOrderSide.BUY,
                filled_qty=1.0,
                fill_price=200.0,
                fee=0.0,
                filled_at_simulated=_T0 + timedelta(minutes=2),
            )
        )
        eng.consume_fill(
            _make_fill(
                order_id="o4",
                fill_id="f4",
                symbol="ETHUSDT",
                side=MockOrderSide.SELL,
                filled_qty=1.0,
                fill_price=195.0,
                fee=0.0,
                filled_at_simulated=_T0 + timedelta(minutes=3),
            )
        )
        return eng.get_ledger()

    a = run()
    b = run()
    assert a.to_json() == b.to_json()
    summary = a.summary()
    assert isinstance(summary, TradeLedgerSummary)
    assert summary.trade_count == 2
    assert summary.win_count == 1
    assert summary.loss_count == 1
    assert summary.total_realized_pnl == pytest.approx(5.0)
    # Symbol query.
    btc = a.entries_for_symbol("BTCUSDT")
    eth = a.entries_for_symbol("ETHUSDT")
    assert len(btc) == 1
    assert len(eth) == 1
    assert btc[0].outcome == TradeOutcome.WIN
    assert eth[0].outcome == TradeOutcome.LOSS
    # Time range query.
    in_range = a.entries_in_range(
        _T0,
        _T0 + timedelta(minutes=1, seconds=30),
    )
    assert len(in_range) == 1
    assert in_range[0].symbol == "BTCUSDT"


# ---------------------------------------------------------------------------
# 14. equity timeseries point JSON serializable
# ---------------------------------------------------------------------------


def test_equity_timeseries_point_json_serialisable():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            fee=0.0,
            filled_at_simulated=_T0,
        )
    )
    ts = eng.get_equity_timeseries()
    assert len(ts) >= 1
    pt = ts[0]
    assert isinstance(pt, EquityTimeseriesPoint)
    payload = pt.to_dict()
    assert json.dumps(payload, sort_keys=True)  # round-trip
    # to_json roundtrips.
    reloaded = json.loads(pt.to_json())
    assert reloaded["exchange_equity"] == pt.exchange_equity
    assert reloaded["simulated_only"] is True
    assert reloaded["no_live_order"] is True
    assert reloaded["live_capital_enabled"] is False
    assert reloaded["phase_12_forbidden"] is True
    assert reloaded["trade_authority"] is False
    assert reloaded["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 15. all outputs simulated_only=True / no_live_order=True
# ---------------------------------------------------------------------------


def test_all_outputs_simulated_only_and_no_live_order():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            filled_at_simulated=_T0,
        )
    )
    out = eng.consume_fill(
        _make_fill(
            order_id="o2",
            fill_id="f2",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=110.0,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    payloads = [
        eng.get_state().to_dict(),
        eng.config.to_dict(),
        eng.get_positions(),  # tuple - check via to_dict each
        eng.get_equity_timeseries()[0].to_dict(),
        eng.get_ledger().to_dict(),
        out.to_dict() if out is not None else {},
        eng.to_dict(),
        eng.safety_payload(),
        SimulatedPosition(
            position_id="sim_position_00000099",
            symbol="X",
            side=PositionSide.LONG,
            qty=0.0,
            avg_entry_price=0.0,
            opened_at_simulated=_T0,
            updated_at_simulated=_T0,
            status=PositionStatus.CLOSED,
        ).to_dict(),
    ]
    for d in payloads:
        if isinstance(d, tuple):
            for p in d:
                p_d = p.to_dict()
                assert p_d["simulated_only"] is True
                assert p_d["no_live_order"] is True
        elif d:
            assert d["simulated_only"] is True
            assert d["no_live_order"] is True


# ---------------------------------------------------------------------------
# 16. phase_12_forbidden=True
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_in_every_payload():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            filled_at_simulated=_T0,
        )
    )
    payloads = [
        eng.get_state().to_dict(),
        eng.config.to_dict(),
        eng.get_equity_timeseries()[0].to_dict(),
        eng.get_ledger().to_dict(),
        eng.to_dict(),
        eng.safety_payload(),
    ]
    for d in payloads:
        assert d["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 17. auto_tuning_allowed=False
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_in_every_payload():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            filled_at_simulated=_T0,
        )
    )
    payloads = [
        eng.get_state().to_dict(),
        eng.config.to_dict(),
        eng.get_equity_timeseries()[0].to_dict(),
        eng.get_ledger().to_dict(),
        eng.to_dict(),
        eng.safety_payload(),
    ]
    for d in payloads:
        assert d["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 18. trade_authority=False
# ---------------------------------------------------------------------------


def test_trade_authority_false_in_every_payload():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            filled_at_simulated=_T0,
        )
    )
    payloads = [
        eng.get_state().to_dict(),
        eng.config.to_dict(),
        eng.get_equity_timeseries()[0].to_dict(),
        eng.get_ledger().to_dict(),
        eng.to_dict(),
        eng.safety_payload(),
    ]
    for d in payloads:
        assert d["trade_authority"] is False
        assert d["ai_trade_authority"] is False
        assert eng.trade_authority is False


# ---------------------------------------------------------------------------
# 19. live_capital_enabled=False
# ---------------------------------------------------------------------------


def test_live_capital_enabled_false_in_every_payload():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            filled_at_simulated=_T0,
        )
    )
    payloads = [
        eng.get_state().to_dict(),
        eng.config.to_dict(),
        eng.get_equity_timeseries()[0].to_dict(),
        eng.get_ledger().to_dict(),
        eng.to_dict(),
        eng.safety_payload(),
        eng.get_positions()[0].to_dict(),
    ]
    for d in payloads:
        assert d["live_capital_enabled"] is False
        assert d["live_trading"] is False
        assert d["exchange_live_orders"] is False
        assert d["binance_private_api_enabled"] is False
    assert eng.live_capital_enabled is False
    assert eng.live_trading is False
    assert eng.exchange_live_orders is False
    assert eng.binance_private_api_enabled is False
    # Refuse a SimulatedCapitalConfig with live flags forced on.
    with pytest.raises(ValueError):
        SimulatedCapitalConfig(
            initial_capital=1.0, sandbox_only=False
        )
    with pytest.raises(ValueError):
        SimulatedCapitalConfig(
            initial_capital=1.0, live_capital_enabled=True
        )


# ---------------------------------------------------------------------------
# 20. forbidden fields absent from serialized outputs
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_from_serialised_outputs():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            filled_at_simulated=_T0,
        )
    )
    out = eng.consume_fill(
        _make_fill(
            order_id="o2",
            fill_id="f2",
            side=MockOrderSide.SELL,
            filled_qty=1.0,
            fill_price=110.0,
            filled_at_simulated=_T0 + timedelta(minutes=1),
        )
    )
    payloads = [
        eng.config.to_dict(),
        eng.get_state(_T0 + timedelta(minutes=1)).to_dict(),
        eng.get_equity_timeseries()[0].to_dict(),
        eng.get_ledger().to_dict(),
        eng.get_ledger().summary().to_dict(),
        out.to_dict(),
        eng.to_dict(),
        eng.safety_payload(),
    ]
    explicit = {
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        "apply_change",
        "deploy_change",
        "enable_live",
        "live_ready",
        "trading_approved",
        "real_order_id",
        "exchange_order_id",
        "real_account_id",
        "api_key",
        "api_secret",
    }
    for p in payloads:
        assert_no_forbidden_fields(p)
        keys = set(_walk_keys(p))
        assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS), (
            f"forbidden field present: {keys & FORBIDDEN_OUTPUT_FIELDS}"
        )
        for forbidden in explicit:
            assert forbidden not in keys, (
                f"forbidden field {forbidden!r} smuggled into payload"
            )


# ---------------------------------------------------------------------------
# 21. module does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports_in_modules():
    root = _project_root()
    paths = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "simulated_capital_flow.py",
        root / "app" / "sim" / "trade_ledger.py",
    ]
    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in paths:
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
    # Importing the new modules does not pull any forbidden module.
    before = set(sys.modules)
    importlib.import_module("app.sim")
    importlib.import_module("app.sim.simulated_capital_flow")
    importlib.import_module("app.sim.trade_ledger")
    new = set(sys.modules) - before
    for nm in new:
        for bad in forbidden_prefixes:
            assert not nm.startswith(bad), (
                f"importing app.sim pulled forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 22. no DeepSeek / LLM / Telegram / Binance / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_llm_telegram_binance_or_network_path():
    root = _project_root()
    paths = [
        root / "app" / "sim" / "simulated_capital_flow.py",
        root / "app" / "sim" / "trade_ledger.py",
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
    for path in paths:
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
    pre = set(sys.modules)
    importlib.import_module("app.sim.simulated_capital_flow")
    importlib.import_module("app.sim.trade_ledger")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), (
                f"unexpected import: {nm}"
            )


# ---------------------------------------------------------------------------
# 23. no real account / signed endpoint / API key fields
# ---------------------------------------------------------------------------


def test_no_real_account_signed_endpoint_or_api_key_fields():
    eng = _make_engine()
    eng.consume_fill(
        _make_fill(
            side=MockOrderSide.BUY,
            filled_qty=1.0,
            fill_price=100.0,
            filled_at_simulated=_T0,
        )
    )
    forbidden_string_fields = (
        "api_key",
        "api_secret",
        "exchange_order_id",
        "real_order_id",
        "real_account_id",
        "binance_signed",
        "private_websocket_url",
        "listenkey",
        "listen_key",
        "signed_request",
        "signed_endpoint_url",
    )
    payloads = [
        eng.config.to_dict(),
        eng.get_state().to_dict(),
        eng.get_equity_timeseries()[0].to_dict(),
        eng.get_ledger().to_dict(),
        eng.get_positions()[0].to_dict(),
        eng.to_dict(),
        eng.safety_payload(),
    ]
    for d in payloads:
        keys = set(_walk_keys(d))
        for forbidden in forbidden_string_fields:
            assert forbidden not in keys, (
                f"forbidden field {forbidden!r} present"
            )
        assert d["binance_private_api_enabled"] is False
        assert d["signed_endpoint_reachable"] is False
        assert d["private_websocket_reachable"] is False
        assert d["account_endpoint_reachable"] is False
        assert d["order_endpoint_reachable"] is False
        assert d["position_endpoint_reachable"] is False
        assert d["leverage_endpoint_reachable"] is False
        assert d["margin_endpoint_reachable"] is False
        assert d["real_exchange_order_path"] is False
        assert d["real_capital"] is False
        assert d["exchange_live_orders"] is False
        assert d["live_capital_enabled"] is False
    # No public method on the engine / ledger exposes a trade verb.
    forbidden_verbs = {
        "place_order",
        "place_real_order",
        "sign_request",
        "sign",
        "open_websocket",
        "private_websocket",
        "listen_key",
        "set_leverage",
        "apply_change",
        "deploy",
        "enable_live",
        "fetch_account",
        "fetch_position",
        "fetch_balance",
    }
    for inst in (eng, eng.ledger, eng.config):
        public = {n for n in dir(inst) if not n.startswith("_")}
        assert public.isdisjoint(forbidden_verbs), (
            f"{inst!r} exposes forbidden verbs: "
            f"{public & forbidden_verbs}"
        )


# ---------------------------------------------------------------------------
# 24. deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output_across_two_independent_runs():
    def run_serialised() -> str:
        eng = _make_engine(initial_capital=10_000.0)
        eng.consume_fill(
            _make_fill(
                order_id="o1",
                fill_id="f1",
                side=MockOrderSide.BUY,
                filled_qty=1.0,
                fill_price=100.0,
                fee=0.04,
                filled_at_simulated=_T0,
            )
        )
        eng.apply_mark_prices(
            {"BTCUSDT": 110.0}, _T0 + timedelta(minutes=1)
        )
        eng.consume_fill(
            _make_fill(
                order_id="o2",
                fill_id="f2",
                side=MockOrderSide.SELL,
                filled_qty=1.0,
                fill_price=120.0,
                fee=0.048,
                filled_at_simulated=_T0 + timedelta(minutes=2),
            )
        )
        return eng.to_dict().__repr__()

    assert run_serialised() == run_serialised()


# ---------------------------------------------------------------------------
# Extra: closed-taxonomy enforcement
# ---------------------------------------------------------------------------


def test_closed_taxonomy_enforcement():
    assert isinstance(PositionSide.ALLOWED, frozenset)
    assert isinstance(PositionStatus.ALLOWED, frozenset)
    assert isinstance(RiskFreezeReason.ALLOWED, frozenset)
    assert isinstance(TradeOutcome.ALLOWED, frozenset)
    assert isinstance(TradeFailureFlag.ALLOWED, frozenset)
    # Defensive: "BUY" / "SELL" are NOT valid PositionSide values.
    assert "BUY" not in PositionSide.ALLOWED
    assert "SELL" not in PositionSide.ALLOWED
    with pytest.raises(ValueError):
        SimulatedPosition(
            position_id="x",
            symbol="X",
            side="UPSIDE",
            qty=0.0,
            avg_entry_price=0.0,
            opened_at_simulated=_T0,
            updated_at_simulated=_T0,
        )
    with pytest.raises(ValueError):
        TradeLedgerEntry(
            trade_id="x",
            symbol="X",
            entry_time=_T0,
            entry_reason="SIMULATED_ENTRY",
            order_type="MARKET",
            requested_qty=0.0,
            filled_qty=0.0,
            avg_fill_price=0.0,
            slippage_bps=0.0,
            fee=0.0,
            max_drawdown_during_trade=0.0,
            max_favorable_excursion=0.0,
            net_pnl=0.0,
            locked_profit_delta=0.0,
            outcome="JACKPOT",
        )
    with pytest.raises(ValueError):
        TradeLedgerEntry(
            trade_id="x",
            symbol="X",
            entry_time=_T0,
            entry_reason="SIMULATED_ENTRY",
            order_type="MARKET",
            requested_qty=0.0,
            filled_qty=0.0,
            avg_fill_price=0.0,
            slippage_bps=0.0,
            fee=0.0,
            max_drawdown_during_trade=0.0,
            max_favorable_excursion=0.0,
            net_pnl=0.0,
            locked_profit_delta=0.0,
            failure_flags=("MARS_LANDED",),
        )


# ---------------------------------------------------------------------------
# Extra: phase-name strings present and frozen
# ---------------------------------------------------------------------------


def test_phase_name_strings_present():
    assert "PR98" in SIMULATED_CAPITAL_FLOW_PHASE_NAME
    assert "PR98" in TRADE_LEDGER_PHASE_NAME
    assert "11C.1D-D-E" in SIMULATED_CAPITAL_FLOW_PHASE_NAME
