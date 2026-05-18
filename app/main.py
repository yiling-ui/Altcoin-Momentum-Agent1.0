"""AMA-RT entrypoint (Phase 2 - Event Sourcing and Database).

Run with:

    python -m app.main

This entrypoint DOES NOT trade. It only:
    1. Loads settings (with the Phase 1 safety lock applied + re-asserted).
    2. Opens & migrates the five Phase 2 SQLite databases:
       events.db, trades.db, positions.db, capital.db, incidents.db.
    3. Wires the Phase 1 skeletons (RiskEngine, ExecutionFSM,
       TelegramCommandCenter, MetricsRegistry, HealthChecker).
    4. Writes one self-check audit trail:
         RISK_APPROVED         (paper-only skeleton check)
         STATE_TRANSITION      (IDLE -> IDLE)
         TELEGRAM_COMMAND_RECEIVED (/status)
         CAPITAL_DEPOSIT       (paper-mode boot deposit, mirrored into
                                capital.db's capital_events_index)
       and prints a one-line status banner before exiting 0.

It will refuse to run if the safety flags ever evaluate to a
non-Phase-1 configuration. This is the runtime-side mirror of the
unit-tested invariant in `app.config.settings`. Phase 2 does NOT loosen
any Phase 1 safety guarantee.
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
from app.core.errors import SafetyViolation  # noqa: E402
from app.core.events import Event, EventType  # noqa: E402
from app.database.connection import DatabaseSet, PHASE2_DATABASES  # noqa: E402
from app.database.migrations import migrate_database_set  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402
from app.execution.fsm import ExecutionFSM  # noqa: E402
from app.monitoring.health import HealthChecker, HealthStatus  # noqa: E402
from app.monitoring.metrics import MetricsRegistry  # noqa: E402
from app.risk.engine import RiskEngine, RiskRequest  # noqa: E402
from app.telegram.bot import TelegramCommandCenter  # noqa: E402


# Phase 2 keeps the same safety invariant Phase 1 introduced. Issue #2 is
# explicit: "禁止修改默认安全配置" / "禁止 live trading".
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

        # Skeletons
        risk = RiskEngine(settings=settings, event_repo=repo)
        fsm = ExecutionFSM()
        telegram = TelegramCommandCenter(settings=settings, event_repo=repo)
        metrics = MetricsRegistry()
        health = HealthChecker()
        health.register("event_log", lambda: HealthStatus.OK)
        health.register("safety_lock", lambda: HealthStatus.OK)

        # Demonstration that the wiring is alive: ask the Risk Engine to
        # adjudicate a trivial paper-mode action. RISK_APPROVED is written.
        decision = risk.evaluate(
            RiskRequest(
                source_module="bootstrap",
                action="phase2_self_check",
                symbol=None,
                live_trading_required=False,
                right_tail_amplify=False,
            )
        )
        metrics.incr("risk_decisions_total")
        metrics.set_gauge("phase", 2)

        # STATE_TRANSITION marker so replay shows the process booted.
        repo.append_event(
            Event(
                event_type=EventType.STATE_TRANSITION,
                source_module="bootstrap",
                payload={
                    "from": fsm.state.value,
                    "to": ExecutionState.IDLE.value,
                    "reason": "phase2_boot",
                },
            )
        )

        # Telegram skeleton: drive one /status command through the bus.
        from app.telegram.commands import Command  # local import keeps boot light

        telegram.handle(Command(name="/status", user_id="phase2-bootstrap"))

        # Phase 2 introduces capital event helpers. Emit a paper-mode
        # CAPITAL_DEPOSIT marker so a fresh database has at least one
        # capital event for replay tests.
        #
        # CRITICAL - this is a *boot probe*, not an accounting entry:
        #   * amount = 0.0 by design - it MUST NOT change initial_capital,
        #     lifetime_equity, withdrawn_profit, trading_capital or any
        #     performance figure produced by Issue #8 (Capital Flow
        #     Engine). Spec §28 says "提现不是亏损 / 提现是资金基准重置";
        #     symmetrically, this marker is not a deposit either.
        #   * source_module = 'bootstrap' and note = 'phase2_boot_paper_marker'
        #     so the Capital Flow Engine in Issue #8 can recognise and
        #     skip it (the boot-marker contract is pinned by the test
        #     test_capital_boot_marker_contract_is_safe_for_issue8).
        #   * No funds move. Paper mode is asserted at the top of run().
        repo.record_capital_deposit(
            amount=0.0,
            source_module="bootstrap",
            note="phase2_boot_paper_marker",
        )

        overall, _ = health.evaluate()
        capital_count = repo.count_events(event_type=EventType.CAPITAL_DEPOSIT)
        # `risk_decision` shows the *paper-mode boot self-check* outcome.
        # It is NOT a real-trade approval. The reason string
        # 'paper_only_skeleton_approval' is the only positive Phase 2
        # outcome possible here; any genuine trade-shaped request would
        # have to set live_trading_required=True / right_tail_amplify=True
        # / stop_unconfirmed=True / unknown_position=True and be hard-
        # rejected by the Risk Engine. See test_phase2_boot_risk_engine_*
        # in tests/unit/test_main_entrypoint.py for the contract.
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
            f"risk_decision={decision.approved}/{decision.reasons[0]}(paper_self_check_only) "
            f"health={overall.value}"
        )
    finally:
        dbs.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
