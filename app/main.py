"""AMA-RT entrypoint (Phase 1 - Safety Foundation).

Run with:

    python -m app.main

This entrypoint DOES NOT trade. It only:
    1. Loads settings (with the Phase 1 safety lock applied).
    2. Initialises the events.db SQLite database.
    3. Wires the Phase 1 skeletons (RiskEngine, ExecutionFSM,
       TelegramCommandCenter, MetricsRegistry, HealthChecker) and writes a
       single STATE_TRANSITION audit event so it is visible that the
       process started.
    4. Prints a banner that includes the phase, mode and safety flag set,
       and exits 0.

It will refuse to run if the safety flags ever evaluate to a non-Phase-1
configuration. This is the runtime-side mirror of the unit-tested invariant
in `app.config.settings`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import __phase__, __version__  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.core.constants import DB_EVENTS, PROJECT_NAME  # noqa: E402
from app.core.enums import ExecutionState  # noqa: E402
from app.core.errors import SafetyViolation  # noqa: E402
from app.core.events import Event, EventType  # noqa: E402
from app.database.connection import open_sqlite  # noqa: E402
from app.database.migrations import apply_schema  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402
from app.execution.fsm import ExecutionFSM  # noqa: E402
from app.monitoring.health import HealthChecker, HealthStatus  # noqa: E402
from app.monitoring.metrics import MetricsRegistry  # noqa: E402
from app.risk.engine import RiskEngine, RiskRequest  # noqa: E402
from app.telegram.bot import TelegramCommandCenter  # noqa: E402


def _assert_phase1_safety(settings) -> None:
    """Defence-in-depth: refuse to start if the safety lock has been undone."""
    if settings.trading_mode != "paper":
        raise SafetyViolation("Phase 1 requires trading_mode=paper")
    if settings.live_trading_enabled:
        raise SafetyViolation("Phase 1 forbids live_trading_enabled=True")
    if settings.right_tail_enabled:
        raise SafetyViolation("Phase 1 forbids right_tail_enabled=True")
    if settings.llm_enabled:
        raise SafetyViolation("Phase 1 forbids llm_enabled=True")
    if settings.exchange_live_order_enabled:
        raise SafetyViolation("Phase 1 forbids exchange_live_order_enabled=True")


def run() -> int:
    settings = get_settings()
    _assert_phase1_safety(settings)

    # Database
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    conn = open_sqlite(
        settings.sqlite_dir / DB_EVENTS,
        wal=settings.defaults.database.wal_mode,
    )
    apply_schema(conn)
    repo = EventRepository(conn)

    # Skeletons
    risk = RiskEngine(settings=settings, event_repo=repo)
    fsm = ExecutionFSM()
    telegram = TelegramCommandCenter(settings=settings, event_repo=repo)
    metrics = MetricsRegistry()
    health = HealthChecker()
    health.register("event_log", lambda: HealthStatus.OK)
    health.register("safety_lock", lambda: HealthStatus.OK)

    # A demonstration that the wiring is alive: ask the Risk Engine to
    # adjudicate a trivial paper-mode action. This will write a
    # RISK_APPROVED event but no trade.
    decision = risk.evaluate(
        RiskRequest(
            source_module="bootstrap",
            action="phase1_self_check",
            symbol=None,
            live_trading_required=False,
            right_tail_amplify=False,
        )
    )
    metrics.incr("risk_decisions_total")
    metrics.set_gauge("phase", 1)

    # Write a STATE_TRANSITION event marking IDLE -> IDLE so replay shows
    # the process booted.
    repo.append(
        Event(
            event_type=EventType.STATE_TRANSITION,
            source_module="bootstrap",
            payload={
                "from": fsm.state.value,
                "to": ExecutionState.IDLE.value,
                "reason": "phase1_boot",
            },
        )
    )

    # Telegram skeleton: drive one /status command through the bus so the
    # event log shows TELEGRAM_COMMAND_RECEIVED. There is no outbound call.
    from app.telegram.commands import Command  # local import keeps boot light

    telegram.handle(Command(name="/status", user_id="phase1-bootstrap"))

    overall, _ = health.evaluate()
    print(
        f"[{PROJECT_NAME}] {__phase__} v{__version__} "
        f"mode={settings.trading_mode} "
        f"live_trading={settings.live_trading_enabled} "
        f"right_tail={settings.right_tail_enabled} "
        f"llm={settings.llm_enabled} "
        f"exchange_live_orders={settings.exchange_live_order_enabled} "
        f"events_count={repo.count()} "
        f"risk_decision={decision.approved}/{decision.reasons[0]} "
        f"health={overall.value}"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
