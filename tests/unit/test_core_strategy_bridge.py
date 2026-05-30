"""Unit tests for the Core Strategy Sim-Live Bridge v0
(Phase 11C.1D-D / PR109).

These tests are the safety + behaviour contract for PR109. They prove
that the deterministic, paper-only Core Strategy Bridge - which drives
the **real AMA-RT core strategy decision lifecycle** (market regime ->
candidate stage -> opportunity score -> strategy selector) instead of
the PR106 baseline shadow rule:

  * uses ONLY records whose ``available_at <= simulated_time`` and
    candles that have CLOSED (no forming / open candle is ever used),
  * trades ONLY symbols in the as-of universe at the current simulated
    time (a symbol that is not tradable / monitorable as-of T is never
    entered),
  * produces a deterministic simulated ENTRY + EXIT on a crafted
    fixture, routed through the (PR97) MockExchange and booked into the
    (PR98) Simulated Capital Flow + Trade Ledger,
  * records the required enriched trade fields (entry/exit time,
    entry/exit price, realized pnl, pnl_pct, equity transitions, ...),
  * surfaces SIM_ENTRY / SIM_EXIT / WINDOW_SUMMARY in the file-only
    Telegram sandbox transcript,
  * keeps the PR108 capital-safety floor in force (no negative equity),
  * NEVER carries AI trade authority, live trading, exchange live
    orders, the Binance private API, real Telegram outbound, or any
    Phase 12 authority,
  * is deterministic (identical fixtures -> identical trades).

Hard safety boundary asserted here:

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

import ast
import json
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pytest

from app.sim import (
    BlindRunStatus,
    BlindWalkForwardRunner,
    BlindWalkForwardRunnerConfig,
    BlindWalkForwardWindow,
    CoreStrategyBridge,
    CoreStrategyBridgeConfig,
    CoreStrategySignalReason,
    HistoricalKlineRecord,
    HistoricalMarketStore,
    MockExchange,
    PaperShadowRejectReason,
    PaperShadowStrategyBridge,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
    SimulatedCapitalConfig,
    SimulatedCapitalFlowEngine,
    SimulationClock,
    SymbolStatus,
    SymbolStatusRecord,
    TelegramSandboxOutbox,
    TelegramSandboxOutboxConfig,
    assert_no_forbidden_fields,
)

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_SYMBOL = "COREUSDT"


# ---------------------------------------------------------------------------
# Deterministic fixture store
# ---------------------------------------------------------------------------


def _kline(
    *,
    symbol: str,
    open_time: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    record_id: str,
) -> HistoricalKlineRecord:
    return HistoricalKlineRecord(
        symbol=symbol,
        interval="1m",
        open_time=open_time,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        available_at=open_time + timedelta(seconds=60),
        source="binance_public",
        record_id=record_id,
    )


def _symbol_status(
    symbol: str,
    *,
    status: str = SymbolStatus.TRADING,
) -> SymbolStatusRecord:
    listed = _T0 - timedelta(days=30)
    return SymbolStatusRecord(
        symbol=symbol,
        market_type="PERP",
        listed_at=listed,
        status=status,
        available_at=listed,
        min_notional=1.0,
        tick_size=0.01,
        step_size=0.0001,
        contract_type="USDT_PERP",
        source="binance_public",
    )


# Price / volume path that deterministically ignites ONE core "pullback"
# entry on the breakout bar (mid stage + strong recent momentum +
# elevated late-chase) and then goes flat so the max-hold exit fires and
# no second entry can ever trigger.
#  i:        -2   -1    0    1    2    3      4 .. tail (flat at 106)
_CORE_PRICES = [100, 100, 100, 100, 102, 104, 106] + [106] * 9
_CORE_VOLS = [10, 10, 10, 10, 10, 10, 30] + [10] * 9


def _make_core_store(
    *,
    symbol: str = _SYMBOL,
    blind_minutes: int,
    with_status: bool = True,
    status: str = SymbolStatus.TRADING,
    prices: Optional[List[float]] = None,
    vols: Optional[List[float]] = None,
) -> HistoricalMarketStore:
    store = HistoricalMarketStore()
    if with_status:
        store.add_record(_symbol_status(symbol, status=status))
    p = prices if prices is not None else _CORE_PRICES
    v = vols if vols is not None else _CORE_VOLS
    for idx, (close, vol) in enumerate(zip(p, v)):
        i = idx - 2  # two warmup bars before the blind window opens
        open_time = _T0 + timedelta(minutes=i)
        store.add_record(
            _kline(
                symbol=symbol,
                open_time=open_time,
                open_=close,
                high=close,
                low=close,
                close=close,
                volume=vol,
                record_id=f"{symbol}_k_{i}",
            )
        )
    return store


def _make_core_config(**overrides) -> CoreStrategyBridgeConfig:
    base = dict(
        bridge_name="ama_rt_core_strategy_v0",
        timeframe="1m",
        breakout_lookback=5,
        min_history_bars=6,
        momentum_lookback=2,
        momentum_full_scale_pct=0.05,
        volume_full_scale_ratio=1.5,
        liquidity_reference_quote_volume=1000.0,
        late_chase_full_scale_pct=0.08,
        manipulation_wick_scale=0.01,
        min_opportunity_score=50.0,
        max_hold_bars=2,
        take_profit_pct=0.5,
        stop_loss_pct=0.5,
        position_notional=20.0,
        max_concurrent_positions=3,
        scale_notional_by_regime=False,
    )
    base.update(overrides)
    return CoreStrategyBridgeConfig(**base)


def _make_runner(
    *,
    tmpdir: Path,
    blind_minutes: int = 14,
    store: Optional[HistoricalMarketStore] = None,
    bridge: Optional[CoreStrategyBridge] = None,
    capital: Optional[SimulatedCapitalFlowEngine] = None,
) -> BlindWalkForwardRunner:
    if store is None:
        store = _make_core_store(blind_minutes=blind_minutes)
    clock = SimulationClock(
        start_time_utc=_T0,
        end_time_utc=_T0 + timedelta(minutes=blind_minutes),
        monotonic_forward_only=True,
    )
    provider = ReplayFeedProvider(
        store=store,
        clock=clock,
        config=ReplayFeedProviderConfig(
            start_time=_T0,
            end_time=_T0 + timedelta(minutes=blind_minutes),
            step_interval=timedelta(minutes=1),
            allow_reemit=False,
            include_asof_universe=True,
        ),
    )
    if capital is None:
        capital = SimulatedCapitalFlowEngine(
            config=SimulatedCapitalConfig(initial_capital=100.0)
        )
    exchange = MockExchange()
    telegram = TelegramSandboxOutbox(
        config=TelegramSandboxOutboxConfig(
            output_jsonl_path=str(tmpdir / "tg.jsonl"),
            output_markdown_path=str(tmpdir / "tg.md"),
        )
    )
    if bridge is None:
        bridge = CoreStrategyBridge(
            config=_make_core_config(), capital_flow=capital
        )
    window = BlindWalkForwardWindow(
        train_start=_T0 - timedelta(minutes=5),
        train_end=_T0,
        blind_start=_T0,
        blind_end=_T0 + timedelta(minutes=blind_minutes),
        reference_window="60d",
    )
    cfg = BlindWalkForwardRunnerConfig(
        window=window,
        config_artefact={"ver": 1},
        rule_artefact={"rule": "ama_rt_core_strategy_v0"},
        feature_schema_artefact={"schema": ["close", "high", "volume"]},
        data_manifest_artefact={"data": "v0"},
        universe_manifest_artefact={"universe": [_SYMBOL]},
        fee_model_artefact={"taker_bps": 4.0},
        slippage_model_artefact={"bps": 5.0},
        latency_model_artefact={"bps": 0.0},
        outage_model_artefact={"min_gap_seconds": 0},
        fill_model_artefact={"policy": "WORST_CASE"},
        code_commit="pr109commit1234",
        run_id="bwf_pr109_test",
        report_root=str(tmpdir / "reports"),
        strategy_profile="core",
        paper_shadow_strategy_bridge_name=bridge.bridge_name,
    )
    return BlindWalkForwardRunner(
        config=cfg,
        replay_provider=provider,
        capital_flow=capital,
        mock_exchange=exchange,
        telegram_sandbox=telegram,
        paper_shadow_bridge=bridge,
    )


# ---------------------------------------------------------------------------
# 0. The bridge is a drop-in PaperShadowStrategyBridge subclass
# ---------------------------------------------------------------------------


def test_core_bridge_is_paper_shadow_subclass():
    bridge = CoreStrategyBridge(config=_make_core_config())
    # The PR100 runner type-checks ``paper_shadow_bridge`` against
    # PaperShadowStrategyBridge; the core bridge must satisfy that.
    assert isinstance(bridge, PaperShadowStrategyBridge)
    assert bridge.strategy_profile == "core"
    assert bridge.core_strategy_enabled is True
    assert bridge.bridge_name == "ama_rt_core_strategy_v0"


# ---------------------------------------------------------------------------
# 1. Bridge rejects records not yet available (available_at > T)
# ---------------------------------------------------------------------------


def test_core_bridge_rejects_record_not_yet_available():
    bridge = CoreStrategyBridge(config=_make_core_config())
    open_time = _T0
    k = _kline(
        symbol=_SYMBOL,
        open_time=open_time,
        open_=100.0,
        high=100.2,
        low=99.8,
        close=100.0,
        volume=10.0,
        record_id="k_future",
    )
    # available_at = open_time + 60s. A simulated_time strictly before
    # that must reject the record (no future read).
    visible, reason = bridge.is_record_visible(
        k, simulated_time=open_time + timedelta(seconds=30)
    )
    assert visible is False
    assert reason == (
        PaperShadowRejectReason.FEATURE_NOT_YET_AVAILABLE_AT_ASOF_TIME
    )
    visible2, reason2 = bridge.is_record_visible(
        k, simulated_time=open_time + timedelta(seconds=60)
    )
    assert visible2 is True
    assert reason2 is None


# ---------------------------------------------------------------------------
# 2. Forming / open candles are NOT used
# ---------------------------------------------------------------------------


def test_core_bridge_rejects_forming_or_unclosed_candle():
    bridge = CoreStrategyBridge(config=_make_core_config())
    sim_time = _T0 + timedelta(minutes=5)
    forming = types.SimpleNamespace(
        interval="1m",
        available_at=sim_time - timedelta(seconds=1),
        close_time=sim_time + timedelta(seconds=59),
        record_id="forming_1m",
        symbol=_SYMBOL,
    )
    visible, reason = bridge.is_record_visible(
        forming, simulated_time=sim_time
    )
    assert visible is False
    assert reason == PaperShadowRejectReason.UNCLOSED_CANDLE


def test_core_history_contains_only_closed_available_bars(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    runner.run()
    bridge = runner._paper_shadow_bridge
    diag = bridge.diagnostics
    assert diag.klines_ingested > 0
    # The bridge must NEVER have ingested a forming / early-access bar.
    assert diag.klines_rejected_unclosed == 0
    state = bridge._states[_SYMBOL]
    for bar in state.bars:
        # Every ingested bar is a closed candle whose close_time is at
        # or before its available_at + step.
        assert bar.close_time <= bar.available_at + timedelta(seconds=1)


# ---------------------------------------------------------------------------
# 3. Deterministic fixture -> exactly one core entry + one core exit
# ---------------------------------------------------------------------------


def test_core_fixture_produces_one_entry_and_one_exit(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    result = runner.run()
    bridge = runner._paper_shadow_bridge
    assert bridge.diagnostics.entry_signals == 1
    assert bridge.diagnostics.exit_signals == 1
    summary = runner.trade_ledger.summary().to_dict()
    assert summary["trade_count"] == 1
    assert result["score"]["status"] == BlindRunStatus.EVIDENCE_GENERATED
    assert result["score"]["closed_trade_count"] == 1
    trades = runner.paper_shadow_trades
    assert len(trades) == 1
    # The entry decision came from the AMA-RT core selector
    # (follow / pullback), not the PR106 baseline breakout rule.
    assert trades[0]["entry_signal_reason"] in (
        CoreStrategySignalReason.CORE_FOLLOW_ENTRY,
        CoreStrategySignalReason.CORE_PULLBACK_ENTRY,
    )


# ---------------------------------------------------------------------------
# 4. Enriched trade record carries the required fields
# ---------------------------------------------------------------------------


def test_core_enriched_trade_record_has_required_fields(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    runner.run()
    trades = runner.paper_shadow_trades
    assert len(trades) == 1
    t = trades[0]
    for field in (
        "entry_time",
        "exit_time",
        "symbol",
        "side",
        "leverage_ratio",
        "entry_price",
        "exit_price",
        "notional",
        "realized_pnl",
        "pnl_pct",
        "equity_before",
        "equity_after",
        "exit_reason",
        "signal_reason",
        "evidence_refs",
        "as_of_refs",
    ):
        assert field in t, f"missing enriched field {field!r}"
    assert t["symbol"] == _SYMBOL
    assert t["side"] == "LONG"
    assert t["entry_time"] is not None
    assert t["exit_time"] is not None
    assert t["entry_price"] > 0.0
    assert t["exit_price"] > 0.0
    assert isinstance(t["realized_pnl"], float)
    assert isinstance(t["pnl_pct"], float)
    assert t["is_simulated"] is True
    assert t["no_live_order"] is True
    assert t["phase_12_forbidden"] is True
    # as_of_refs only ever point at already-closed candles, and the
    # signal ref records which core lifecycle branch fired.
    assert t["as_of_refs"]
    for ref in t["as_of_refs"]:
        assert ref.startswith("asof:")
    assert any(
        r.startswith("signal:core_") for r in t["evidence_refs"]
    )
    assert any(r.startswith("core_mode:") for r in t["evidence_refs"])
    # Underlying PR98 ledger entry carries the canonical timestamps.
    entry = runner.trade_ledger.entries[0]
    assert entry.entry_time is not None
    assert entry.exit_time is not None
    assert entry.exit_time >= entry.entry_time


# ---------------------------------------------------------------------------
# 5. As-of universe only: a non-as-of symbol is never traded
# ---------------------------------------------------------------------------


def test_core_bridge_trades_only_asof_universe(tmp_path):
    # Two symbols: GATEUSDT is TRADING (so the as-of universe is
    # non-empty) and flat (no signal). COREUSDT has the breakout-shaped
    # path BUT carries NO symbol-status record, so it is never in the
    # as-of universe. The core lifecycle still fires its entry signal on
    # COREUSDT, but the as-of gate must SUPPRESS it (never opened).
    blind_minutes = 14
    store = HistoricalMarketStore()
    store.add_record(_symbol_status("GATEUSDT", status=SymbolStatus.TRADING))
    # Flat gate symbol (in the as-of universe, never triggers).
    flat = [100.0] * len(_CORE_PRICES)
    for idx, close in enumerate(flat):
        i = idx - 2
        store.add_record(
            _kline(
                symbol="GATEUSDT",
                open_time=_T0 + timedelta(minutes=i),
                open_=close,
                high=close,
                low=close,
                close=close,
                volume=10.0,
                record_id=f"GATEUSDT_k_{i}",
            )
        )
    # Trigger symbol with NO status record -> excluded from the as-of
    # universe.
    for idx, (close, vol) in enumerate(zip(_CORE_PRICES, _CORE_VOLS)):
        i = idx - 2
        store.add_record(
            _kline(
                symbol=_SYMBOL,
                open_time=_T0 + timedelta(minutes=i),
                open_=close,
                high=close,
                low=close,
                close=close,
                volume=vol,
                record_id=f"{_SYMBOL}_k_{i}",
            )
        )

    capital = SimulatedCapitalFlowEngine(
        config=SimulatedCapitalConfig(initial_capital=100.0)
    )
    bridge = CoreStrategyBridge(
        config=_make_core_config(), capital_flow=capital
    )
    runner = _make_runner(
        tmpdir=tmp_path,
        blind_minutes=blind_minutes,
        store=store,
        bridge=bridge,
        capital=capital,
    )
    out = runner.run()

    # The core lifecycle decided to enter COREUSDT, but the as-of gate
    # SUPPRESSED it before any order was built, so NO position ever
    # opened and NO closed trade exists. The suppression is recorded as
    # a SYMBOL_NOT_IN_ASOF_UNIVERSE rejection (never silently dropped).
    assert runner.trade_ledger.summary().to_dict()["trade_count"] == 0
    assert len(capital.get_positions()) == 0
    rejections = runner.paper_shadow_rejections
    assert any(
        r.get("reason")
        == PaperShadowRejectReason.SYMBOL_NOT_IN_ASOF_UNIVERSE
        and r.get("symbol") == _SYMBOL
        for r in rejections
    )
    # COREUSDT is scanned but never traded; GATEUSDT is scanned, never
    # traded (no signal).
    report = json.loads(
        Path(out["paths"]["blind_walk_forward_report.json"]).read_text(
            encoding="utf-8"
        )
    )
    assert report["symbols_scanned_count"] >= 2
    assert report["symbols_traded_count"] == 0
    assert runner.violations == ()


# ---------------------------------------------------------------------------
# 6. MockExchange is the only execution path
# ---------------------------------------------------------------------------


def test_core_mock_exchange_is_only_execution_path(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    exchange = runner._mock_exchange
    assert isinstance(exchange, MockExchange)
    # Every simulated fill flowed through the MockExchange (entry +
    # exit), and the trade ledger was built from those fills only.
    fills = exchange.list_fills()
    assert len(fills) >= 2
    assert runner.trade_ledger.summary().to_dict()["trade_count"] == 1
    # No real exchange / private API path is ever advertised.
    payload = exchange.safety_payload()
    assert payload["sandbox_only"] is True
    assert payload["live_trading"] is False
    assert payload["exchange_live_orders"] is False
    assert payload["real_exchange_order_path"] is False
    assert payload["binance_private_api_enabled"] is False
    report = json.loads(
        Path(out["paths"]["blind_walk_forward_report.json"]).read_text(
            encoding="utf-8"
        )
    )
    assert report["exchange_live_orders"] is False
    assert report["real_exchange_order_path"] is False
    assert report["binance_private_api_enabled"] is False


# ---------------------------------------------------------------------------
# 7. PR108 capital safety still prevents negative equity (core path)
# ---------------------------------------------------------------------------


def test_core_capital_safety_prevents_negative_equity(tmp_path):
    # Enter via the core lifecycle, then the price collapses hard. The
    # PR108 no-negative-equity guard + drawdown kill switch must keep
    # the simulated equity at or above the capital floor and latch the
    # halt - never going negative.
    prices = [100, 100, 100, 100, 102, 104, 106, 60, 30, 10, 5, 3, 2, 1, 1, 1]
    vols = [10, 10, 10, 10, 10, 10, 30, 10, 10, 10, 10, 10, 10, 10, 10, 10]
    store = _make_core_store(
        blind_minutes=14, prices=prices, vols=vols
    )
    capital = SimulatedCapitalFlowEngine(
        config=SimulatedCapitalConfig(
            initial_capital=100.0,
            capital_floor=0.0,
            no_negative_equity_guard=True,
            max_drawdown_halt_pct=0.05,
            halt_on_capital_exhaustion=True,
        )
    )
    bridge = CoreStrategyBridge(
        config=_make_core_config(
            stop_loss_pct=0.5, take_profit_pct=0.9, max_hold_bars=50
        ),
        capital_flow=capital,
    )
    runner = _make_runner(
        tmpdir=tmp_path, blind_minutes=14, store=store, bridge=bridge,
        capital=capital,
    )
    out = runner.run()  # must NOT raise
    report = json.loads(
        Path(out["paths"]["blind_walk_forward_report.json"]).read_text(
            encoding="utf-8"
        )
    )
    # No negative equity, floor honoured, guard on.
    assert report["final_equity"] >= 0.0
    assert report["final_equity"] >= report["capital_floor"]
    assert report["no_negative_equity_guard"] is True
    # Every equity-timeseries mark stayed at or above the floor.
    for pt in runner.equity_timeseries:
        assert float(pt.exchange_equity) >= 0.0
    # The drawdown kill switch latched (forced exit or halt).
    assert report["halted_by_risk"] is True
    assert out["score"]["no_lookahead_violation_count"] == 0


# ---------------------------------------------------------------------------
# 8. Telegram sandbox transcript shows the required events
# ---------------------------------------------------------------------------


def test_core_transcript_contains_required_events(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    transcript_path = Path(out["paths"]["telegram_sandbox_transcript.md"])
    assert transcript_path.exists()
    text = transcript_path.read_text(encoding="utf-8")
    assert "SIM_ENTRY" in text
    assert "SIM_EXIT" in text
    assert "WINDOW_SUMMARY" in text
    # Mandatory sandbox markers on every paper-shadow message body.
    assert "SIMULATED_ONLY" in text
    assert "NO_LIVE_ORDER" in text
    assert "NO_REAL_CAPITAL" in text
    assert "NO_COMMAND_AUTHORITY" in text


def test_core_window_summary_reports_strategy_profile(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    text = Path(
        out["paths"]["telegram_sandbox_transcript.md"]
    ).read_text(encoding="utf-8")
    assert "strategy_profile=core" in text
    assert "core_strategy_enabled=True" in text


# ---------------------------------------------------------------------------
# 9. Report carries strategy_profile + all required PR109 fields
# ---------------------------------------------------------------------------


def test_core_report_fields(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    report = json.loads(
        Path(out["paths"]["blind_walk_forward_report.json"]).read_text(
            encoding="utf-8"
        )
    )
    assert report["strategy_profile"] == "core"
    assert report["core_strategy_enabled"] is True
    assert report["paper_shadow_strategy_enabled"] is False
    assert report["strategy_bridge_name"] == "ama_rt_core_strategy_v0"
    # All PR109 brief §10 report fields present.
    for field in (
        "initial_capital",
        "final_equity",
        "total_realized_pnl",
        "max_drawdown",
        "halted_by_risk",
        "capital_exhausted",
        "trade_count",
        "closed_trade_count",
        "win_count",
        "loss_count",
        "symbols_scanned_count",
        "symbols_traded_count",
        "violations_count",
        "invalidations",
    ):
        assert field in report, f"missing report field {field!r}"
    assert report["symbols_scanned_count"] >= 1
    assert report["symbols_traded_count"] >= 1
    assert report["initial_capital"] == 100.0
    assert_no_forbidden_fields(report)


# ---------------------------------------------------------------------------
# 10. AI trade authority remains False everywhere
# ---------------------------------------------------------------------------


def test_core_ai_trade_authority_false_everywhere(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    bridge = runner._paper_shadow_bridge
    assert bridge.ai_trade_authority is False
    assert bridge.ai_in_decision_chain is False
    d = bridge.to_dict()
    assert d["ai_trade_authority"] is False
    assert d["ai_in_decision_chain"] is False
    assert d["uses_future_labels"] is False
    assert d["uses_outcome_labels"] is False
    assert d["is_core_strategy_bridge"] is True
    out = runner.run()
    assert out["score"]["ai_trade_authority"] is False
    report = json.loads(
        Path(out["paths"]["blind_walk_forward_report.json"]).read_text(
            encoding="utf-8"
        )
    )
    assert report["ai_trade_authority"] is False


# ---------------------------------------------------------------------------
# 11. No live / private / telegram outbound safety flags flipped
# ---------------------------------------------------------------------------


def test_core_safety_flags_remain_false(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    bridge = runner._paper_shadow_bridge
    payload = bridge.safety_payload()
    for flag in (
        "live_trading",
        "exchange_live_orders",
        "binance_private_api_enabled",
        "real_exchange_order_path",
        "real_capital",
        "telegram_outbound_enabled",
        "telegram_live_command_authority",
        "ai_trade_authority",
        "trade_authority",
        "auto_tuning_allowed",
        "auto_tuning_inside_blind_window",
    ):
        assert payload[flag] is False, flag
    assert payload["simulated_only"] is True
    assert payload["no_live_order"] is True
    assert payload["phase_12_forbidden"] is True

    out = runner.run()
    # The Telegram sandbox never advertises real outbound.
    assert runner._telegram.telegram_outbound_enabled is False
    assert runner._telegram.telegram_production_channel_enabled is False
    for name in (
        "blind_walk_forward_report.json",
        "paper_shadow_trades.json",
        "trade_ledger.json",
    ):
        p = Path(out["paths"][name])
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["live_trading"] is False
        assert data["phase_12_forbidden"] is True
        assert data["trade_authority"] is False
        assert data["telegram_outbound_enabled"] is False
        assert_no_forbidden_fields(data)


# ---------------------------------------------------------------------------
# 12. Determinism: identical fixtures -> identical simulated trades
# ---------------------------------------------------------------------------


def test_core_deterministic_trades(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()

    def _run(target: Path) -> List[dict]:
        runner = _make_runner(tmpdir=target)
        runner.run()
        return list(runner.paper_shadow_trades)

    trades_a = _run(a)
    trades_b = _run(b)
    assert len(trades_a) == len(trades_b) == 1

    def _norm(t: dict) -> dict:
        return {
            k: t[k]
            for k in (
                "symbol",
                "side",
                "entry_price",
                "exit_price",
                "quantity",
                "realized_pnl",
                "pnl_pct",
                "entry_signal_reason",
                "exit_signal_reason",
                "outcome",
            )
        }

    assert _norm(trades_a[0]) == _norm(trades_b[0])


# ---------------------------------------------------------------------------
# 13. The core bridge module imports no forbidden app modules / no net
# ---------------------------------------------------------------------------


def _collect_imports(text: str) -> set:
    tree = ast.parse(text)
    mods: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_core_bridge_module_imports_no_forbidden_modules():
    root = Path(__file__).resolve().parents[2]
    text = (
        root / "app" / "sim" / "core_strategy_bridge.py"
    ).read_text(encoding="utf-8")
    mods = _collect_imports(text)
    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for m in mods:
        for fp in forbidden_prefixes:
            assert not (m == fp or m.startswith(fp + ".")), m
    forbidden_substrings = (
        "deepseek",
        "openai",
        "anthropic",
        "requests",
        "httpx",
        "urllib",
        "websocket",
        "ccxt",
    )
    for m in mods:
        lo = m.lower()
        for s in forbidden_substrings:
            assert s not in lo, m


def test_core_bridge_config_to_dict_has_no_forbidden_fields():
    cfg = _make_core_config()
    d = cfg.to_dict()
    assert_no_forbidden_fields(d)
    # leverage must be surfaced under the guard-safe key only.
    assert "leverage" not in d
    assert d["leverage_ratio"] == 1.0
    assert d["is_core_strategy_bridge_config"] is True
    assert d["strategy_profile"] == "core"


# ---------------------------------------------------------------------------
# 14. The runner rejects an invalid strategy profile
# ---------------------------------------------------------------------------


def test_runner_config_rejects_invalid_strategy_profile():
    window = BlindWalkForwardWindow(
        train_start=_T0 - timedelta(minutes=5),
        train_end=_T0,
        blind_start=_T0,
        blind_end=_T0 + timedelta(minutes=5),
        reference_window="60d",
    )
    with pytest.raises(ValueError):
        BlindWalkForwardRunnerConfig(
            window=window,
            code_commit="x",
            strategy_profile="not_a_profile",
        )
