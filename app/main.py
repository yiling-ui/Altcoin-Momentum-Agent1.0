"""AMA-RT entrypoint (Phase 3 - Exchange Gateway Read-Only).

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
    5. Writes one self-check audit trail:
         RISK_APPROVED         (paper-only skeleton check)
         STATE_TRANSITION      (IDLE -> IDLE)
         TELEGRAM_COMMAND_RECEIVED (/status)
         CAPITAL_DEPOSIT       (paper-mode boot deposit, mirrored into
                                capital.db's capital_events_index)
         EXCHANGE_CONNECTED    (Phase 3 boot self-check)
       and prints a one-line status banner before exiting 0.

It will refuse to run if the safety flags ever evaluate to a
non-Phase-1 configuration, or if the Phase 3 read-only invariant has
drifted. Phase 3 does NOT loosen any Phase 1 / Phase 2 safety
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
from app.core.constants import PROJECT_NAME  # noqa: E402
from app.core.enums import ExecutionState  # noqa: E402
from app.core.errors import SafeModeViolation, SafetyViolation  # noqa: E402
from app.core.events import Event, EventType  # noqa: E402
from app.database.connection import DatabaseSet, PHASE2_DATABASES  # noqa: E402
from app.database.migrations import migrate_database_set  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402
from app.exchanges import MockExchangeClient  # noqa: E402
from app.exchanges.base import WRITE_SURFACE_METHODS  # noqa: E402
from app.execution.fsm import ExecutionFSM  # noqa: E402
from app.monitoring.health import HealthChecker, HealthStatus  # noqa: E402
from app.monitoring.metrics import MetricsRegistry  # noqa: E402
from app.risk.engine import RiskEngine, RiskRequest  # noqa: E402
from app.telegram.bot import TelegramCommandCenter  # noqa: E402


# Phase 3 keeps the same safety invariant Phase 1 introduced. Issue #2
# and Issue #3 are both explicit: "禁止修改默认安全配置" / "禁止 live
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
        exchange = MockExchangeClient(event_repo=repo, autostart=True)
        _assert_phase3_read_only(exchange)
        exchange_symbols = exchange.get_symbols()
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

        # Demonstration that the wiring is alive: ask the Risk Engine to
        # adjudicate a trivial paper-mode action. RISK_APPROVED is written.
        decision = risk.evaluate(
            RiskRequest(
                source_module="bootstrap",
                action="phase3_self_check",
                symbol=None,
                live_trading_required=False,
                right_tail_amplify=False,
            )
        )
        metrics.incr("risk_decisions_total")
        metrics.set_gauge("phase", 3)
        metrics.incr("exchange_health_probes")

        # STATE_TRANSITION marker so replay shows the process booted.
        repo.append_event(
            Event(
                event_type=EventType.STATE_TRANSITION,
                source_module="bootstrap",
                payload={
                    "from": fsm.state.value,
                    "to": ExecutionState.IDLE.value,
                    "reason": "phase3_boot",
                },
            )
        )

        # Telegram skeleton: drive one /status command through the bus.
        from app.telegram.commands import Command  # local import keeps boot light

        telegram.handle(Command(name="/status", user_id="phase3-bootstrap"))

        # Phase 2 introduced capital event helpers. Emit a paper-mode
        # CAPITAL_DEPOSIT marker so a fresh database has at least one
        # capital event for replay tests. This is paper-mode bookkeeping
        # only - no funds move.
        repo.record_capital_deposit(
            amount=0.0,
            source_module="bootstrap",
            note="phase3_boot_paper_marker",
        )

        overall, _ = health.evaluate()
        capital_count = repo.count_events(event_type=EventType.CAPITAL_DEPOSIT)
        exchange_connected_count = repo.count_events(
            event_type=EventType.EXCHANGE_CONNECTED
        )
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
            f"risk_decision={decision.approved}/{decision.reasons[0]} "
            f"health={overall.value}"
        )
        # Stop the exchange cleanly so DATA_UNRELIABLE is emitted on
        # shutdown - that lets replay-based tests confirm the lifecycle
        # closed properly.
        exchange.stop(reason="phase3_shutdown")
    finally:
        dbs.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
