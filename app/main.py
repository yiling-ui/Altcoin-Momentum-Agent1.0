"""AMA-RT entrypoint (Phase 10A - Replay Engine).

Run with:

    python -m app.main

This entrypoint DOES NOT trade. Phase 10A wires the read-only
Replay Engine into the boot drill on top of the Phase 9
Execution FSM + Reconciliation drill. After the paper-mode order
has been driven through POSITION_OPEN and a clean reconciliation
pass has landed, Replay reconstructs:

  - the paper trade lifecycle keyed by the boot client_order_id,
  - the boot CAPITAL_DEPOSIT marker,
  - the bootstrap RISK_APPROVED decision,
  - any P0 incidents (boot drill expects zero),
  - the boot STATE_TRANSITION ladder for the first eligible symbol,
  - the boot Telegram /status command,
  - the P0 latched-pause invariant against the boot's clean
    reconciliation pass.

Every Phase 1-9 contract stays in force:

  - The five Phase 1 safety flags remain locked.
  - The four Phase 3 ExchangeClientBase write surfaces still raise
    SafeModeViolation - Phase 10A NEVER overrides them. Paper-mode
    state lives in a separate :class:`PaperLedger`.
  - Phase 8.5 redaction / export contract is unchanged.
  - LLM remains disabled; Telegram outbound remains deferred to
    Issue #10 Part 10D.
  - Replay is read-only - it never writes to events.db, never
    instantiates an exchange client, never opens a socket.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import __phase__, __version__  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.core.clock import now_ms  # noqa: E402
from app.core.constants import PROJECT_NAME  # noqa: E402
from app.core.enums import Direction, ExecutionState, TradeState, TradeStateTrigger  # noqa: E402
from app.core.errors import SafeModeViolation, SafetyViolation  # noqa: E402
from app.core.events import Event, EventType  # noqa: E402
from app.database.connection import DatabaseSet, PHASE2_DATABASES  # noqa: E402
from app.database.migrations import migrate_database_set  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402
from app.exchanges import MockExchangeClient  # noqa: E402
from app.exchanges.base import WRITE_SURFACE_METHODS  # noqa: E402
from app.exchanges.mock import MockExchangeSeed  # noqa: E402
from app.exchanges.models import RecentTrade, TradeSide  # noqa: E402
from app.execution.fsm import ExecutionFSM, ExecutionFSMDriver  # noqa: E402
from app.execution.models import (  # noqa: E402
    OrderIntent,
    OrderKind,
    OrderRequest,
    OrderSide,
    side_for_direction,
)
from app.execution.paper_ledger import PaperLedger  # noqa: E402
from app.incidents.repository import IncidentRepository  # noqa: E402
from app.liquidity import LiquidityFilter, Side as LiquiditySide  # noqa: E402
from app.manipulation import ManipulationDetector  # noqa: E402
from app.market_data import MarketDataBuffer  # noqa: E402
from app.monitoring.health import HealthChecker, HealthStatus  # noqa: E402
from app.monitoring.metrics import MetricsRegistry  # noqa: E402
from app.reconciliation import (  # noqa: E402
    Reconciler,
    local_snapshot_from_paper_ledger,
    remote_snapshot_from_paper_ledger,
)
from app.regime import RegimeEngine  # noqa: E402
from app.replay import (  # noqa: E402
    P0LatchedPauseInvariantReport,
    ReplayEngine,
)
from app.risk.engine import RiskEngine, RiskRequest  # noqa: E402
from app.scanner import AnomalyScanner, PreAnomalyScanner  # noqa: E402
from app.state_machine import (  # noqa: E402
    TradeStateContext,
    TradeStateMachine,
)
from app.confirmation import RealTradeConfirmation  # noqa: E402
from app.telegram.bot import TelegramCommandCenter  # noqa: E402
from app.universe import UniverseFilter  # noqa: E402


# Phase 4 keeps the same safety invariant Phase 1 introduced. Issues #2,
# #3 and #4 are all explicit: "禁止修改默认安全配置" / "禁止 live
# trading" / "禁止真实下单".
def _assert_phase1_safety(settings) -> None:
    """Defence-in-depth: refuse to start if the safety lock has been undone."""
    if settings.trading_mode != "paper":
        raise SafetyViolation("Phase 1 safety lock requires trading_mode=paper")
    if settings.live_trading_enabled:
        raise SafetyViolation("Phase 1 safety lock forbids live_trading_enabled=True")
    if settings.right_tail_enabled:
        raise SafetyViolation("Phase 1 safety lock forbids right_tail_enabled=True")
    if settings.llm_enabled:
        raise SafetyViolation("Phase 1 safety lock forbids llm_enabled=True")
    if settings.exchange_live_order_enabled:
        raise SafetyViolation(
            "Phase 1 safety lock forbids exchange_live_order_enabled=True"
        )


def _assert_phase3_read_only(client) -> None:
    """Defence-in-depth: refuse to start if Phase 3 read-only invariant
    has drifted. Walks every banned write surface and confirms it
    refuses with SafeModeViolation."""
    client.assert_read_only()
    for fn_name in WRITE_SURFACE_METHODS:
        fn = getattr(client, fn_name, None)
        if fn is None:
            raise SafeModeViolation(
                f"{client.name}.{fn_name} is missing; Phase 3 contract requires "
                f"all four write surfaces to exist and refuse."
            )
        try:
            fn()
        except SafeModeViolation:
            continue
        # If we reach this point, the call did NOT raise. That means
        # someone overrode the base-class refusal without restoring it.
        raise SafeModeViolation(
            f"{client.name}.{fn_name} did NOT refuse a probe call. "
            f"Phase 3 contract demands SafeModeViolation. Refusing to start."
        )


def _assert_phase9_no_live_writes(driver: ExecutionFSMDriver) -> None:
    """Defence-in-depth: refuse to start if Phase 9 driver somehow flipped
    a flag that would let a real order land. Today the construction-time
    refusals in :class:`ExecutionFSMDriver` already enforce this; this is
    the boot-time mirror so monitoring sees an explicit assertion line.
    """
    settings = driver._settings  # noqa: SLF001 - intentional cross-module probe
    if settings.trading_mode != "paper":
        raise SafeModeViolation(
            "ExecutionFSMDriver requires trading_mode=paper at boot."
        )
    if settings.live_trading_enabled:
        raise SafeModeViolation(
            "Phase 9 forbids live_trading_enabled at boot."
        )
    if settings.exchange_live_order_enabled:
        raise SafeModeViolation(
            "Phase 9 forbids exchange_live_order_enabled at boot."
        )


def _build_phase4_boot_seed() -> MockExchangeSeed:
    """Deterministic in-process tape used by the Phase 4 boot self-check.

    All timestamps are anchored to ``now_ms()`` so the buffer's
    staleness gate (Spec §14.2) sees a fresh window when the entrypoint
    runs the boot drill. This is only used by ``python -m app.main``;
    tests build their own seeds. **No file is read, no network call is
    made, no credential is consumed.**
    """
    from app.exchanges.models import (
        ExchangeSymbol,
        FundingRate,
        OpenInterest,
        OrderBook,
        OrderBookLevel,
    )

    base = now_ms()
    symbols = [
        ExchangeSymbol(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            price_tick=0.1,
            qty_step=0.001,
            min_notional=5.0,
        ),
        ExchangeSymbol(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            price_tick=0.01,
            qty_step=0.001,
            min_notional=5.0,
        ),
        ExchangeSymbol(
            symbol="PEPEUSDT",
            base_asset="PEPE",
            quote_asset="USDT",
            price_tick=0.0000001,
            qty_step=1.0,
            min_notional=5.0,
        ),
    ]
    trades: dict[str, list[RecentTrade]] = {}
    orderbooks: dict[str, OrderBook] = {}
    funding: dict[str, FundingRate] = {}
    oi: dict[str, OpenInterest] = {}
    for sym in symbols:
        # Five fresh trades, alternating sides, all within the last
        # 4 seconds. Well inside every staleness threshold.
        sym_trades: list[RecentTrade] = []
        for i in range(5):
            sym_trades.append(
                RecentTrade(
                    symbol=sym.symbol,
                    trade_id=f"phase4-boot-{sym.symbol}-{i}",
                    timestamp=base - (4 - i) * 1000,
                    price=100.0 + (i % 3) * 0.1,
                    qty=1.0,
                    side=TradeSide.BUY if i % 2 == 0 else TradeSide.SELL,
                    is_buyer_maker=(i % 2 == 1),
                )
            )
        trades[sym.symbol] = sym_trades
        orderbooks[sym.symbol] = OrderBook(
            symbol=sym.symbol,
            timestamp=base,
            bids=tuple(
                OrderBookLevel(price=100.0 - 0.1 * (i + 1), qty=1.0 + i)
                for i in range(5)
            ),
            asks=tuple(
                OrderBookLevel(price=100.0 + 0.1 * (i + 1), qty=1.0 + i)
                for i in range(5)
            ),
        )
        funding[sym.symbol] = FundingRate(
            symbol=sym.symbol,
            timestamp=base,
            rate=0.0001,
            next_funding_ts=base + 8 * 60 * 60 * 1000,
        )
        oi[sym.symbol] = OpenInterest(
            symbol=sym.symbol,
            timestamp=base,
            open_interest=1_000_000.0,
            open_interest_value=1_000_000_00.0,
        )
    return MockExchangeSeed(
        symbols=symbols,
        trades=trades,
        orderbooks=orderbooks,
        funding_rates=funding,
        open_interest=oi,
    )


def _build_liquidity_input_for_boot(
    *,
    symbol: str,
    book,
    snap,
    is_data_degraded: bool,
    regime,
):
    """Construct a deterministic Phase 5 :class:`LiquidityInput` for the
    boot drill. Kept out of :func:`run` so the call site stays readable.
    """
    from app.liquidity import LiquidityInput, Side

    return LiquidityInput(
        symbol=symbol,
        side=Side.LONG,
        planned_qty=0.001,
        last_price=snap.last_price,
        spread_pct=snap.spread_pct,
        orderbook=book,
        volume_5m=snap.volume_5m,
        is_data_degraded=is_data_degraded,
        market_regime=regime.market_regime,
        risk_permission=regime.risk_permission,
        timestamp=snap.timestamp,
    )


def run() -> int:
    settings = get_settings()
    _assert_phase1_safety(settings)

    # Database: open + migrate all five Phase 2 databases.
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    dbs = DatabaseSet.open(
        settings.sqlite_dir,
        wal=settings.defaults.database.wal_mode,
        databases=PHASE2_DATABASES,
    )
    try:
        migrate_database_set(dbs)

        # `capital.db` is wired into the EventRepository so CAPITAL_*
        # events are mirrored into capital_events_index automatically.
        repo = EventRepository(dbs.events, capital_conn=dbs.capital)

        # ---- Phase 3 - Exchange Gateway boot self-check ----------
        # Phase 3 ships ONLY the read-only mock; the BinanceClient
        # skeleton exists for static-typing purposes and refuses every
        # read with NotImplementedError. We exercise the mock and then
        # immediately stop it so the entrypoint stays deterministic.
        # Phase 4: we seed the mock with a FRESH tape so the deterministic
        # mock data is not stale by Phase 4's staleness gate; the seed
        # is generated from now_ms() so every boot is fully reproducible
        # against its own clock anchor. No real network. No fixture
        # file is loaded. No credential is read.
        boot_seed = _build_phase4_boot_seed()
        exchange = MockExchangeClient(
            seed=boot_seed, event_repo=repo, autostart=True
        )
        _assert_phase3_read_only(exchange)
        exchange_symbols = exchange.get_symbols()
        # ----------------------------------------------------------

        # ---- Phase 4 - Market Data Buffer boot self-check --------
        # Drive the buffer from MockExchangeClient fixture data only.
        # No real Binance WebSocket. No real REST. No API key. No
        # auto-connect to the real exchange. No write surface.
        buffer = MarketDataBuffer(exchange=exchange, event_repo=repo)
        for sym in exchange_symbols:
            buffer.track(sym.symbol)
            buffer.refresh_from_exchange(sym.symbol)
            buffer.snapshot(sym.symbol)
        # Exercise the WS-disconnect path so the audit trail shows
        # DATA_UNRELIABLE at boot - this is the wiring tested by Issue
        # #7's future No-Trade Gate.
        buffer.on_websocket_disconnect(reason="phase4_boot_disconnect_probe")
        buffer.on_websocket_reconnect(reason="phase4_boot_reconnect_probe")
        # ----------------------------------------------------------

        # ---- Phase 5 - Regime / Universe / Liquidity boot self-check ----
        # All three engines read from the same in-process buffer and
        # deterministic mock; they NEVER call a write surface, NEVER
        # open a socket, NEVER import an exchange SDK. Each engine
        # writes exactly the events Issue #5 requires.
        regime_engine = RegimeEngine(event_repo=repo)
        # Use BTCUSDT as the BTC reference; alt symbols are everything
        # else the mock exposes. The buffer is fully populated above
        # so the convenience helper has live data to read.
        alt_symbols = [s.symbol for s in exchange_symbols if s.symbol != "BTCUSDT"]
        regime_snapshot = regime_engine.evaluate_from_buffer(
            buffer,
            btc_symbol="BTCUSDT",
            alt_symbols=alt_symbols,
        )

        universe_filter = UniverseFilter(event_repo=repo)
        universe_decisions = []
        for sym_meta in exchange_symbols:
            snap = buffer.snapshot(sym_meta.symbol, emit_event=False)
            decision = universe_filter.evaluate_snapshot(
                snap,
                symbol_meta=sym_meta,
                regime=regime_snapshot,
                is_data_degraded=buffer.is_degraded(sym_meta.symbol),
            )
            universe_decisions.append(decision)

        liquidity_filter = LiquidityFilter(event_repo=repo)
        # Drive Liquidity once per symbol with a tiny planned qty so
        # the boot drill exercises both the evaluate path AND the
        # can_exit_position path. Phase 5 uses planned_qty = 0.001 (the
        # mock symbols all have qty_step >= 0.001) so the deterministic
        # mock book is always deep enough to clear the path.
        for sym_meta in exchange_symbols:
            snap = buffer.snapshot(sym_meta.symbol, emit_event=False)
            book = buffer._state_for(sym_meta.symbol).orderbook
            liquidity_filter.evaluate(
                _build_liquidity_input_for_boot(
                    symbol=sym_meta.symbol,
                    book=book,
                    snap=snap,
                    is_data_degraded=buffer.is_degraded(sym_meta.symbol),
                    regime=regime_snapshot,
                )
            )
            liquidity_filter.can_exit_position(
                sym_meta.symbol,
                qty=0.001,
                max_slippage_pct=0.01,
                max_seconds=60.0,
                side=LiquiditySide.LONG,
                orderbook=book,
                volume_5m=snap.volume_5m,
                last_price=snap.last_price,
                is_data_degraded=buffer.is_degraded(sym_meta.symbol),
                risk_permission=regime_snapshot.risk_permission,
                market_regime=regime_snapshot.market_regime,
                spread_pct=snap.spread_pct,
            )
        # ----------------------------------------------------------

        # ---- Phase 6 - Scanner / Confirmation / Manipulation -----
        # All four classifiers read from the same in-process buffer +
        # regime snapshot. They never call a write surface, never open
        # a socket, never import an exchange SDK, never call an LLM.
        # Each emits ONE event of its own type per evaluation.
        pre_anomaly_scanner = PreAnomalyScanner(event_repo=repo)
        anomaly_scanner = AnomalyScanner(event_repo=repo)
        confirmation = RealTradeConfirmation(event_repo=repo)
        manipulation = ManipulationDetector(event_repo=repo)
        observed_manipulation_level = None
        observed_confirmation_level = None
        for sym_meta in exchange_symbols:
            snap = buffer.snapshot(sym_meta.symbol, emit_event=False)
            is_degraded_view = buffer.is_degraded(sym_meta.symbol)
            pre_anomaly_scanner.evaluate_snapshot(
                snap,
                regime=regime_snapshot,
                is_data_degraded=is_degraded_view,
            )
            anomaly_scanner.evaluate_snapshot(
                snap,
                regime=regime_snapshot,
                is_data_degraded=is_degraded_view,
            )
            conf_decision = confirmation.evaluate_snapshot(
                snap,
                regime=regime_snapshot,
                is_data_degraded=is_degraded_view,
            )
            manip_decision = manipulation.evaluate_snapshot(
                snap,
                regime=regime_snapshot,
                is_data_degraded=is_degraded_view,
            )
            # Track the worst-observed reading so the bootstrap risk
            # check can be exercised against a real classifier output
            # rather than a hard-coded value.
            if observed_manipulation_level is None or (
                manip_decision.fired_signals
                > (observed_manipulation_level[1].fired_signals)
            ):
                observed_manipulation_level = (manip_decision.level, manip_decision)
            if observed_confirmation_level is None or (
                conf_decision.fired_signals
                > observed_confirmation_level[1].fired_signals
            ):
                observed_confirmation_level = (conf_decision.level, conf_decision)
        # ----------------------------------------------------------

        # Skeletons
        risk = RiskEngine(settings=settings, event_repo=repo)
        fsm = ExecutionFSM()
        telegram = TelegramCommandCenter(settings=settings, event_repo=repo)
        metrics = MetricsRegistry()
        health = HealthChecker()
        health.register("event_log", lambda: HealthStatus.OK)
        health.register("safety_lock", lambda: HealthStatus.OK)
        # Phase 3: the exchange link is a first-class health probe.
        health.register(
            "exchange_link",
            lambda: HealthStatus.OK
            if exchange.health.is_data_trustworthy()
            else HealthStatus.DEGRADED,
        )
        # Phase 4: the market data buffer is a first-class probe too.
        health.register(
            "market_data_buffer",
            lambda: HealthStatus.OK
            if buffer.stats().symbols_degraded == 0
            else HealthStatus.DEGRADED,
        )
        # Phase 5: the regime gate is a first-class probe. SYSTEMIC_RISK
        # is the only state that must show DEGRADED so monitoring sees
        # a hard block.
        from app.core.enums import RiskPermission as _RiskPermission

        health.register(
            "regime_gate",
            lambda: HealthStatus.OK
            if regime_snapshot.risk_permission is not _RiskPermission.BLOCK_ALL
            else HealthStatus.DEGRADED,
        )

        # Demonstration that the wiring is alive: ask the Risk Engine to
        # adjudicate a trivial paper-mode action. RISK_APPROVED is written.
        # Phase 7 hooks the observed manipulation + confirmation levels,
        # the regime snapshot, the worst Phase 5 universe / liquidity
        # decisions, the buffer's degraded view, and the exchange link
        # state. With attack_intent=False and is_new_open=False the
        # bootstrap stays a clean approval - the Phase 7 No-Trade Gate
        # does NOT fire on a non-opening self-check.
        bootstrap_manipulation = (
            observed_manipulation_level[0]
            if observed_manipulation_level is not None
            else None
        )
        bootstrap_confirmation = (
            observed_confirmation_level[0]
            if observed_confirmation_level is not None
            else None
        )
        # Phase 7: drive a Trade State Machine for the first eligible
        # symbol so the boot drill exercises STATE_TRANSITION events
        # via the new state_machine package. Use the buffer's
        # symbol set; pick the first one for the drill.
        first_symbol = (
            exchange_symbols[0].symbol if exchange_symbols else "BOOT"
        )
        state_machine = TradeStateMachine(
            symbol=first_symbol, event_repo=repo
        )
        state_machine.transition_to(
            TradeState.OBSERVE,
            trigger=TradeStateTrigger.SIGNAL,
            reasons=("phase9_boot",),
        )
        decision = risk.evaluate(
            RiskRequest(
                source_module="bootstrap",
                action="phase7_self_check",
                symbol=None,
                live_trading_required=False,
                right_tail_amplify=False,
                attack_intent=False,
                # is_new_open=False so the Phase 7 No-Trade Gate does
                # not fire on the boot self-check (this is a
                # paper-mode bookkeeping call, not a real opening).
                is_new_open=False,
                manipulation_level=bootstrap_manipulation,
                trade_confirmation_level=bootstrap_confirmation,
                regime_snapshot=regime_snapshot,
                is_data_degraded=False,
                exchange_connection_state=exchange.health.state,
            )
        )
        metrics.incr("risk_decisions_total")
        metrics.set_gauge("phase", 6)
        metrics.incr("exchange_health_probes")
        metrics.set_gauge(
            "market_data_symbols_tracked", buffer.stats().symbols_tracked
        )
        metrics.incr("regime_evaluations", regime_engine.evaluations)
        metrics.incr("universe_evaluations", universe_filter.evaluations)
        metrics.incr("liquidity_evaluations", liquidity_filter.evaluations)
        metrics.incr("liquidity_exit_checks", liquidity_filter.exit_checks)
        metrics.incr("pre_anomaly_evaluations", pre_anomaly_scanner.evaluations)
        metrics.incr("anomaly_evaluations", anomaly_scanner.evaluations)
        metrics.incr("trade_confirmation_evaluations", confirmation.evaluations)
        metrics.incr("manipulation_evaluations", manipulation.evaluations)

        # STATE_TRANSITION marker so replay shows the process booted.
        repo.append_event(
            Event(
                event_type=EventType.STATE_TRANSITION,
                source_module="bootstrap",
                payload={
                    "from": fsm.state.value,
                    "to": ExecutionState.IDLE.value,
                    "reason": "phase9_boot",
                },
            )
        )

        # ---- Phase 9 - Execution FSM driver + Reconciliation ----
        # Build an in-process IncidentRepository (writes incidents.db)
        # and an ExecutionFSMDriver wired against the Risk Engine and
        # the in-process paper ledger. The driver is paper-mode by
        # construction; the four ExchangeClientBase write surfaces
        # remain SafeModeViolation refusals.
        incidents = IncidentRepository(
            incidents_conn=dbs.incidents,
            event_repo=repo,
        )
        paper_ledger = PaperLedger(initial_equity=0.0)
        execution_driver = ExecutionFSMDriver(
            risk_engine=risk,
            event_repo=repo,
            paper_ledger=paper_ledger,
            settings=settings,
            protection_hook=incidents,
        )
        _assert_phase9_no_live_writes(execution_driver)

        # Drive ONE paper-mode order from IDLE through POSITION_OPEN.
        # Use the first exchange symbol so the boot drill runs even
        # when the mock exposes a different symbol set in a future PR.
        boot_symbol = (
            exchange_symbols[0].symbol if exchange_symbols else "BOOT"
        )
        boot_order = OrderRequest(
            client_order_id=f"phase9_boot_{int(now_ms())}",
            symbol=boot_symbol,
            side=side_for_direction(Direction.LONG, is_close=False),
            kind=OrderKind.LIMIT,
            qty=0.001,
            limit_price=100.0,
            intent=OrderIntent.NEW_OPEN,
            direction=Direction.LONG,
            leverage=1.0,
            stop_price=98.0,
            opportunity_id="opp_phase9_boot",
            notes=("phase9_boot_paper_self_check",),
        )
        boot_session = execution_driver.simulate_paper_lifecycle(
            boot_order,
            ack_id="phase9_boot_ack",
            fill_price=100.0,
            stop_price=98.0,
            regime_snapshot=regime_snapshot,
            manipulation_level=bootstrap_manipulation,
            trade_confirmation_level=bootstrap_confirmation,
            is_data_degraded=False,
            exchange_connection_state=exchange.health.state,
        )
        # Trigger an exit with is_new_open=False so the Phase 9
        # protective-exit / reduce-only-closing-flow contract is
        # exercised at boot.
        execution_driver.trigger_exit(
            session=boot_session,
            reason="phase9_boot_paper_close",
            regime_snapshot=regime_snapshot,
            manipulation_level=bootstrap_manipulation,
            is_data_degraded=False,
            exchange_connection_state=exchange.health.state,
        )
        execution_driver.on_position_closed(
            session=boot_session,
            realized_pnl=0.0,
        )

        # Run ONE Reconciliation pass against a snapshot built from
        # the same paper ledger. This must be a clean reconciliation
        # in paper mode (local view == remote view), so no
        # RECONCILIATION_MISMATCH should fire on a fresh boot.
        reconciler = Reconciler(
            event_repo=repo,
            protection_hook=incidents,
        )
        local_snap = local_snapshot_from_paper_ledger(
            paper_ledger,
            websocket_state=exchange.health.state,
            rest_state=exchange.health.state,
        )
        remote_snap = remote_snapshot_from_paper_ledger(
            paper_ledger,
            websocket_state=exchange.health.state,
            rest_state=exchange.health.state,
        )
        reconciliation_decision = reconciler.reconcile(
            local=local_snap, remote=remote_snap
        )

        health.register(
            "execution_driver",
            lambda: HealthStatus.OK
            if execution_driver.counters.error_protection_entered == 0
            else HealthStatus.DEGRADED,
        )
        health.register(
            "reconciliation",
            lambda: HealthStatus.OK
            if not reconciler.new_opens_paused
            else HealthStatus.DEGRADED,
        )
        # ----------------------------------------------------------

        # Telegram skeleton: drive one /status command through the bus.
        from app.telegram.commands import Command  # local import keeps boot light

        telegram.handle(Command(name="/status", user_id="phase6-bootstrap"))

        # Phase 2 introduced capital event helpers. Emit a paper-mode
        # CAPITAL_DEPOSIT marker so a fresh database has at least one
        # capital event for replay tests. This is paper-mode bookkeeping
        # only - no funds move.
        repo.record_capital_deposit(
            amount=0.0,
            source_module="bootstrap",
            note="phase9_boot_paper_marker",
        )

        # ---- Phase 10A - Replay Engine boot self-check -----------
        # Phase 10A is read-only. The Replay Engine never opens a
        # socket, never imports an exchange / LLM / Telegram client,
        # never instantiates a state-mutating component, and never
        # writes to events.db. The boot self-check exercises every
        # public replay surface on the events the prior Phase 1-9
        # boot drills already wrote.
        from app.replay.loaders import (  # noqa: E402  -- local import keeps the boot import block tidy
            load_capital_flow_events,
        )
        replay = ReplayEngine(event_repo=repo)
        replay_paper_trade = replay.replay_paper_trade(
            client_order_id=boot_order.client_order_id,
        )
        # The boot drill drives the order all the way to POSITION_CLOSED
        # so the diff against the canonical closed paper-trade chain
        # MUST be a clean match.
        if not replay_paper_trade.diff_against_canonical.matched:
            raise RuntimeError(
                "Phase 10A boot self-check: paper trade lifecycle diff "
                "does not match the canonical chain. divergences="
                f"{replay_paper_trade.diff_against_canonical.divergences!r}"
            )
        # The Phase 10A capital-rebase replay needs an actual
        # CAPITAL_REBASE event; the Phase 9 boot drill does not emit
        # one (no withdrawal / deposit happens), so we only assert the
        # capital-flow loader returns the boot CAPITAL_DEPOSIT marker
        # we just wrote. A future Phase 10A self-check that drives
        # CapitalFlowEngine.deposit() would exercise replay_capital_rebase
        # directly; we explicitly do NOT instantiate CapitalFlowEngine
        # here because Phase 10A is read-only and the Phase 9 boot
        # drill already exercises the capital-event substrate.
        boot_capital_flow_events = load_capital_flow_events(repo)
        if not boot_capital_flow_events:
            raise RuntimeError(
                "Phase 10A boot self-check: events.db has no capital "
                "events even though the Phase 2 marker was emitted."
            )
        # Find the bootstrap RISK_APPROVED event (first one written -
        # the FSM driver writes RISK_APPROVED for every paper-mode
        # submit_order too, but the bootstrap one comes first by
        # construction).
        bootstrap_risk_events = repo.list_events(
            event_type=EventType.RISK_APPROVED,
            source_module="risk_engine",
        )
        if not bootstrap_risk_events:
            raise RuntimeError(
                "Phase 10A boot self-check: events.db has no "
                "RISK_APPROVED event."
            )
        replay_risk = replay.replay_risk_decision(
            event_id=bootstrap_risk_events[0].event_id,
        )
        if not replay_risk.approved:
            raise RuntimeError(
                "Phase 10A boot self-check: bootstrap risk decision "
                "should be RISK_APPROVED."
            )
        replay_p0 = replay.replay_p0_incidents()
        if replay_p0:
            raise RuntimeError(
                "Phase 10A boot self-check: clean boot drill should "
                "produce zero P0 incidents."
            )
        replay_state = replay.replay_state_transitions(symbol=first_symbol)
        if not replay_state.events:
            raise RuntimeError(
                "Phase 10A boot self-check: boot drill must produce at "
                "least one STATE_TRANSITION event."
            )
        replay_telegram = replay.replay_telegram_commands()
        # The Phase 1 Telegram skeleton emits one /status during boot.
        if not replay_telegram:
            raise RuntimeError(
                "Phase 10A boot self-check: boot drill must produce at "
                "least one TELEGRAM_COMMAND_RECEIVED event."
            )
        invariant: P0LatchedPauseInvariantReport = (
            replay.verify_p0_latched_pause_invariant()
        )
        if not invariant.held:
            raise RuntimeError(
                "Phase 10A boot self-check: P0 latched-pause invariant "
                "violation in boot reconciliation pass: "
                f"{invariant.violations!r}"
            )
        replay_paper_trade_count = 1
        replay_p0_incident_count = len(replay_p0)
        replay_telegram_command_count = len(replay_telegram)
        replay_state_transition_count = len(replay_state.events)
        replay_invariant_held = invariant.held
        # ----------------------------------------------------------


        overall, _ = health.evaluate()
        capital_count = repo.count_events(event_type=EventType.CAPITAL_DEPOSIT)
        exchange_connected_count = repo.count_events(
            event_type=EventType.EXCHANGE_CONNECTED
        )
        market_snapshot_count = repo.count_events(
            event_type=EventType.MARKET_SNAPSHOT
        )
        data_unreliable_count = repo.count_events(
            event_type=EventType.DATA_UNRELIABLE
        )
        regime_count = repo.count_events(event_type=EventType.REGIME_UPDATED)
        universe_count = repo.count_events(event_type=EventType.UNIVERSE_FILTERED)
        universe_eligible_count = sum(
            1 for d in universe_decisions if d.eligible
        )
        liquidity_count = repo.count_events(event_type=EventType.LIQUIDITY_CHECKED)
        pre_anomaly_count = repo.count_events(
            event_type=EventType.PRE_ANOMALY_DETECTED
        )
        anomaly_count = repo.count_events(event_type=EventType.ANOMALY_DETECTED)
        trade_confirmed_count = repo.count_events(
            event_type=EventType.TRADE_CONFIRMED
        )
        manipulation_count = repo.count_events(
            event_type=EventType.MANIPULATION_DETECTED
        )
        # Phase 7: count STATE_TRANSITION events written by the
        # state-machine boot drill (separate from the bootstrap
        # IDLE -> IDLE marker emitted earlier).
        state_transition_count = repo.count_events(
            event_type=EventType.STATE_TRANSITION
        )
        # Phase 9 event counts.
        order_sent_count = repo.count_events(event_type=EventType.ORDER_SENT)
        order_filled_count = repo.count_events(event_type=EventType.ORDER_FILLED)
        stop_confirmed_count = repo.count_events(
            event_type=EventType.STOP_CONFIRMED
        )
        position_opened_count = repo.count_events(
            event_type=EventType.POSITION_OPENED
        )
        position_closed_count = repo.count_events(
            event_type=EventType.POSITION_CLOSED
        )
        reconciliation_started_count = repo.count_events(
            event_type=EventType.RECONCILIATION_STARTED
        )
        reconciliation_resolved_count = repo.count_events(
            event_type=EventType.RECONCILIATION_RESOLVED
        )
        reconciliation_mismatch_count = repo.count_events(
            event_type=EventType.RECONCILIATION_MISMATCH
        )
        incident_opened_count = repo.count_events(
            event_type=EventType.INCIDENT_OPENED
        )
        protection_entered_count = repo.count_events(
            event_type=EventType.PROTECTION_MODE_ENTERED
        )
        stats = buffer.stats()
        print(
            f"[{PROJECT_NAME}] {__phase__} v{__version__} "
            f"mode={settings.trading_mode} "
            f"live_trading={settings.live_trading_enabled} "
            f"right_tail={settings.right_tail_enabled} "
            f"llm={settings.llm_enabled} "
            f"exchange_live_orders={settings.exchange_live_order_enabled} "
            f"databases={len(PHASE2_DATABASES)} "
            f"events_count={repo.count_events()} "
            f"capital_events={capital_count} "
            f"exchange={exchange.name}/{exchange.health.state.value} "
            f"exchange_symbols={len(exchange_symbols)} "
            f"exchange_connected_events={exchange_connected_count} "
            f"market_data={stats.symbols_tracked}/{stats.symbols_degraded} "
            f"market_snapshots={market_snapshot_count} "
            f"data_unreliable={data_unreliable_count} "
            f"regime={regime_snapshot.market_regime.value}/"
            f"{regime_snapshot.risk_permission.value} "
            f"regime_events={regime_count} "
            f"universe={universe_eligible_count}/{len(universe_decisions)} "
            f"universe_events={universe_count} "
            f"liquidity_events={liquidity_count} "
            f"pre_anomaly_events={pre_anomaly_count} "
            f"anomaly_events={anomaly_count} "
            f"trade_confirmed_events={trade_confirmed_count} "
            f"manipulation_events={manipulation_count} "
            f"state_transitions={state_transition_count} "
            f"trade_state={state_machine.state.value} "
            f"daily_loss_breaker={risk.daily_loss_breaker.state.value} "
            f"consecutive_loss_breaker={risk.consecutive_loss_breaker.state.value} "
            f"orders_submitted={execution_driver.counters.orders_submitted} "
            f"order_sent_events={order_sent_count} "
            f"order_filled_events={order_filled_count} "
            f"stops_confirmed={stop_confirmed_count} "
            f"positions_opened={position_opened_count} "
            f"positions_closed={position_closed_count} "
            f"reconciliations_run={reconciler.reconciliations_run} "
            f"reconciliation_started_events={reconciliation_started_count} "
            f"reconciliation_resolved_events={reconciliation_resolved_count} "
            f"reconciliation_mismatches={reconciliation_mismatch_count} "
            f"new_opens_paused={reconciler.new_opens_paused} "
            f"incidents_opened={incident_opened_count} "
            f"protection_mode_entered={protection_entered_count} "
            f"replay_paper_trade_matched={replay_paper_trade.diff_against_canonical.matched} "
            f"replay_p0_incidents={replay_p0_incident_count} "
            f"replay_telegram_commands={replay_telegram_command_count} "
            f"replay_state_transitions={replay_state_transition_count} "
            f"replay_p0_latched_pause_invariant={replay_invariant_held} "
            f"risk_decision={decision.approved}/{decision.reasons[0]} "
            f"health={overall.value}"
        )
        # Stop the exchange cleanly so DATA_UNRELIABLE is emitted on
        # shutdown - that lets replay-based tests confirm the lifecycle
        # closed properly.
        exchange.stop(reason="phase9_shutdown")
    finally:
        dbs.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
