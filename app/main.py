"""AMA-RT entrypoint (Phase 4 - Market Data Buffer).

Run with:

    python -m app.main

This entrypoint DOES NOT trade. It only:
    1. Loads settings (with the Phase 1 safety lock applied + re-asserted).
    2. Opens & migrates the five Phase 2 SQLite databases:
       events.db, trades.db, positions.db, capital.db, incidents.db.
    3. Wires the Phase 1 skeletons (RiskEngine, ExecutionFSM,
       TelegramCommandCenter, MetricsRegistry, HealthChecker).
    4. Instantiates the Phase 3 read-only Exchange Gateway as a
       `MockExchangeClient` (no network, no SDK), calls its
       `assert_read_only()` boot check, exercises one of each read-only
       method and confirms the four write surfaces refuse with
       `SafeModeViolation`. Emits an `EXCHANGE_CONNECTED` event.
    5. Constructs a Phase 4 :class:`MarketDataBuffer`, drives it from
       the Mock client (deterministic, no network), produces one
       :class:`MarketSnapshot` per tracked symbol, and registers a
       `market_data_buffer` health probe. The buffer is then taken
       through one degraded transition (WebSocket disconnect) and one
       recovery transition so the audit trail in `events.db` shows the
       full lifecycle.
    6. Writes one self-check audit trail:
         RISK_APPROVED         (paper-only skeleton check)
         STATE_TRANSITION      (IDLE -> IDLE)
         TELEGRAM_COMMAND_RECEIVED (/status)
         CAPITAL_DEPOSIT       (paper-mode boot deposit, mirrored into
                                capital.db's capital_events_index)
         EXCHANGE_CONNECTED    (Phase 3 boot self-check)
         MARKET_SNAPSHOT       (Phase 4 boot self-check, one per symbol)
         DATA_UNRELIABLE       (Phase 4 boot self-check, one disconnect)
         EXCHANGE_DISCONNECTED (Phase 3 graceful shutdown)
       and prints a one-line status banner before exiting 0.

It will refuse to run if the safety flags ever evaluate to a
non-Phase-1 configuration, or if the Phase 3 read-only invariant has
drifted. Phase 4 does NOT loosen any Phase 1 / Phase 3 safety
guarantee.
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
from app.core.enums import ExecutionState  # noqa: E402
from app.core.errors import SafeModeViolation, SafetyViolation  # noqa: E402
from app.core.events import Event, EventType  # noqa: E402
from app.database.connection import DatabaseSet, PHASE2_DATABASES  # noqa: E402
from app.database.migrations import migrate_database_set  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402
from app.exchanges import MockExchangeClient  # noqa: E402
from app.exchanges.base import WRITE_SURFACE_METHODS  # noqa: E402
from app.exchanges.mock import MockExchangeSeed  # noqa: E402
from app.exchanges.models import RecentTrade, TradeSide  # noqa: E402
from app.execution.fsm import ExecutionFSM  # noqa: E402
from app.market_data import MarketDataBuffer  # noqa: E402
from app.monitoring.health import HealthChecker, HealthStatus  # noqa: E402
from app.monitoring.metrics import MetricsRegistry  # noqa: E402
from app.risk.engine import RiskEngine, RiskRequest  # noqa: E402
from app.telegram.bot import TelegramCommandCenter  # noqa: E402


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

        # Demonstration that the wiring is alive: ask the Risk Engine to
        # adjudicate a trivial paper-mode action. RISK_APPROVED is written.
        decision = risk.evaluate(
            RiskRequest(
                source_module="bootstrap",
                action="phase4_self_check",
                symbol=None,
                live_trading_required=False,
                right_tail_amplify=False,
            )
        )
        metrics.incr("risk_decisions_total")
        metrics.set_gauge("phase", 4)
        metrics.incr("exchange_health_probes")
        metrics.set_gauge(
            "market_data_symbols_tracked", buffer.stats().symbols_tracked
        )

        # STATE_TRANSITION marker so replay shows the process booted.
        repo.append_event(
            Event(
                event_type=EventType.STATE_TRANSITION,
                source_module="bootstrap",
                payload={
                    "from": fsm.state.value,
                    "to": ExecutionState.IDLE.value,
                    "reason": "phase4_boot",
                },
            )
        )

        # Telegram skeleton: drive one /status command through the bus.
        from app.telegram.commands import Command  # local import keeps boot light

        telegram.handle(Command(name="/status", user_id="phase4-bootstrap"))

        # Phase 2 introduced capital event helpers. Emit a paper-mode
        # CAPITAL_DEPOSIT marker so a fresh database has at least one
        # capital event for replay tests. This is paper-mode bookkeeping
        # only - no funds move.
        repo.record_capital_deposit(
            amount=0.0,
            source_module="bootstrap",
            note="phase4_boot_paper_marker",
        )

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
            f"risk_decision={decision.approved}/{decision.reasons[0]} "
            f"health={overall.value}"
        )
        # Stop the exchange cleanly so DATA_UNRELIABLE is emitted on
        # shutdown - that lets replay-based tests confirm the lifecycle
        # closed properly.
        exchange.stop(reason="phase4_shutdown")
    finally:
        dbs.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
