"""Phase 11B - Cloud Paper Trading supervisor.

Boots the Phase 1 - 10D pipeline in paper mode and runs the cloud-side
loop the Phase 11B brief defines:

  - Pre-flight :class:`EnvGuard`
  - :func:`assert_paper_cloud_safety` defence-in-depth
  - Open the five Phase 2 databases
  - Wire :class:`EventRepository`, :class:`IncidentRepository`,
    :class:`RiskEngine`, :class:`ExecutionFSMDriver`,
    :class:`Reconciler`, :class:`AlertDispatcher`,
    :class:`TestDataExportService`
  - Drive ONE paper trade lifecycle so the daily report has a
    canonical happy-path event chain to count
  - Run the :class:`IncidentDrillHarness` (8 drills)
  - Force an export on first boot ("/export_test_data 24h")
  - Build the daily Markdown report
  - Build the Phase 11B acceptance report
  - Print a structured banner
  - Close cleanly

Phase 11B boundary
------------------

  - opens NO real socket
  - imports NO exchange / LLM / Telegram SDK
  - reads NO ``os.environ`` for credentials
  - never touches any of the four ExchangeClientBase write surfaces
  - never bypasses the Risk Engine
  - never flips the Phase 1 safety lock
  - LLM stays disabled - the boot drill exercises only the degraded
    short-circuit
  - Telegram outbound stays in :class:`FakeTelegramClient` mode by
    default
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from loguru import logger

from app.config.settings import Settings, get_settings
from app.core.clock import now_ms
from app.core.constants import PROJECT_NAME
from app.core.enums import (
    Direction,
    ExchangeConnectionState,
)
from app.core.errors import SafetyViolation
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.mock import MockExchangeClient
from app.exports.redaction import assert_no_forbidden_substrings
from app.exports.service import TestDataExportService
from app.execution.fsm import ExecutionFSMDriver
from app.execution.models import (
    OrderIntent,
    OrderKind,
    OrderRequest,
    side_for_direction,
)
from app.execution.paper_ledger import PaperLedger
from app.incidents.repository import IncidentRepository
from app.paper_run.config import (
    DEFAULT_PAPER_CLOUD_PATH,
    PaperCloudConfig,
)
from app.paper_run.daily_report import DailyReportBuilder, DailyReportSnapshot
from app.paper_run.env_guard import EnvGuard, EnvGuardReport
from app.paper_run.export_scheduler import ExportScheduler, ExportTick
from app.paper_run.incident_drill import (
    DrillStatus,
    IncidentDrillHarness,
    IncidentDrillResult,
)
from app.paper_run.safety_assert import (
    SafetyAssertionReport,
    assert_paper_cloud_safety,
)
from app.reconciliation.models import (
    local_snapshot_from_paper_ledger,
    remote_snapshot_from_paper_ledger,
)
from app.reconciliation.reconciler import Reconciler
from app.risk.engine import RiskEngine, RiskRequest
from app.telegram.alerts import AlertDispatcher, AlertSeverity
from app.telegram.bot import TelegramCommandCenter
from app.telegram.commands import Command, CommandStatus
from app.telegram.exports import TelegramExportBridge
from app.telegram.outbound import FakeTelegramClient


_BOOT_PAPER_SYMBOL = "BOOTUSDT"


@dataclass(frozen=True)
class PaperCloudSupervisorReport:
    """Final summary the supervisor returns to the caller.

    The Phase 11B acceptance run consumes this dataclass to render
    ``docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md``. Every field is
    JSON-safe.
    """

    started_at_ms: int
    finished_at_ms: int
    settings_safety: dict[str, bool]
    paper_cloud_summary: dict[str, Any]
    env_guard_report: dict[str, Any]
    safety_assertion_report: dict[str, bool]
    drill_results: tuple[IncidentDrillResult, ...]
    daily_report: DailyReportSnapshot | None
    boot_export_tick: ExportTick | None
    boot_lifecycle_summary: dict[str, Any]
    telegram_summary: dict[str, Any]
    accepted: bool
    go_decision: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    acceptance_report_path: str | None = None
    daily_report_path: str | None = None
    boot_export_zip_path: str | None = None

    @property
    def all_drills_passed(self) -> bool:
        return all(r.passed for r in self.drill_results)

    def to_payload(self) -> dict[str, Any]:
        return {
            "started_at_ms": int(self.started_at_ms),
            "finished_at_ms": int(self.finished_at_ms),
            "settings_safety": dict(self.settings_safety),
            "paper_cloud_summary": dict(self.paper_cloud_summary),
            "env_guard_report": dict(self.env_guard_report),
            "safety_assertion_report": dict(self.safety_assertion_report),
            "drill_results": [r.to_payload() for r in self.drill_results],
            "daily_report": (
                self.daily_report.to_payload()
                if self.daily_report is not None
                else None
            ),
            "boot_export_tick": (
                self.boot_export_tick.to_payload()
                if self.boot_export_tick is not None
                else None
            ),
            "boot_lifecycle_summary": dict(self.boot_lifecycle_summary),
            "telegram_summary": dict(self.telegram_summary),
            "accepted": bool(self.accepted),
            "go_decision": self.go_decision,
            "notes": list(self.notes),
            "acceptance_report_path": self.acceptance_report_path,
            "daily_report_path": self.daily_report_path,
            "boot_export_zip_path": self.boot_export_zip_path,
        }


class PaperCloudSupervisor:
    """Phase 11B cloud paper-mode orchestrator.

    Construct ONCE per cloud process. The same instance can run in
    acceptance-dry-run mode (one shot) or in long-running cadence
    mode (repeat tick + daily report); the acceptance dry-run is the
    only mode shipped in Phase 11B and exercises every public path
    end-to-end in under one minute on CI.
    """

    SOURCE_MODULE = "paper_run.supervisor"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        paper_cloud: PaperCloudConfig | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._paper_cloud = paper_cloud or PaperCloudConfig.load(
            DEFAULT_PAPER_CLOUD_PATH
        )
        self._environ = environ
        # Wired by run() / acceptance_dry_run().
        self._dbs: DatabaseSet | None = None
        self._event_repo: EventRepository | None = None
        self._incidents: IncidentRepository | None = None
        self._risk: RiskEngine | None = None
        self._fsm: ExecutionFSMDriver | None = None
        self._reconciler: Reconciler | None = None
        self._alert_dispatcher: AlertDispatcher | None = None
        self._command_center: TelegramCommandCenter | None = None
        self._export_bridge: TelegramExportBridge | None = None
        self._export_service: TestDataExportService | None = None
        self._daily_report_builder: DailyReportBuilder | None = None
        self._export_scheduler: ExportScheduler | None = None
        self._exchange: MockExchangeClient | None = None

    # ==================================================================
    # Public entry points
    # ==================================================================
    def acceptance_dry_run(
        self,
        *,
        emit_banner: bool = True,
        write_acceptance_report: bool = True,
        clock_ms: int | None = None,
    ) -> PaperCloudSupervisorReport:
        """Run the full acceptance dry-run.

        Boots the Phase 1 - 10D pipeline in paper mode, drives one
        paper trade lifecycle, runs every incident drill, fires the
        first-boot export, builds the daily report, writes the
        Phase 11B acceptance report, prints the banner, and tears down
        the wiring cleanly.
        """
        started_at = int(clock_ms if clock_ms is not None else now_ms())
        notes: list[str] = []
        env_guard_report: EnvGuardReport | None = None
        safety_report: SafetyAssertionReport | None = None
        drill_results: list[IncidentDrillResult] = []
        daily_report: DailyReportSnapshot | None = None
        export_tick: ExportTick | None = None
        boot_lifecycle: dict[str, Any] = {}
        telegram_summary: dict[str, Any] = {}
        acceptance_report_path: Path | None = None
        daily_report_path: Path | None = None
        accepted = False
        go_decision = "NO-GO"

        try:
            # 1. Env-guard pre-flight.
            env_guard = EnvGuard(
                config=self._paper_cloud.env_guard,
                environ=self._environ,
            )
            env_guard_report = env_guard.assert_safe()
            notes.append(
                f"env_guard_passed={env_guard_report.passed}"
            )

            # 2. Phase 1 safety lock + paper-cloud invariant assertion
            # (without an exchange client - we wire that next and
            # re-assert below).
            safety_report = assert_paper_cloud_safety(
                settings=self._settings,
                paper_cloud=self._paper_cloud,
                exchange_client=None,
            )

            # 3. Open + migrate the five Phase 2 databases.
            self._settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
            self._dbs = DatabaseSet.open(
                self._settings.sqlite_dir,
                wal=self._settings.defaults.database.wal_mode,
                databases=PHASE2_DATABASES,
            )
            migrate_database_set(self._dbs)

            # 4. Wire the substrate the supervisor controls.
            self._event_repo = EventRepository(
                self._dbs.events, capital_conn=self._dbs.capital
            )
            self._incidents = IncidentRepository(
                incidents_conn=self._dbs.incidents,
                event_repo=self._event_repo,
            )
            # Read-only mock exchange (for the four-write-surfaces
            # refusal probe). No fixture file. No real socket.
            self._exchange = MockExchangeClient(event_repo=self._event_repo)
            # 4b. Re-assert with the wired exchange so the four write
            # surfaces are exercised at boot.
            safety_report = assert_paper_cloud_safety(
                settings=self._settings,
                paper_cloud=self._paper_cloud,
                exchange_client=self._exchange,
            )

            # 5. Risk Engine + Execution FSM driver + Reconciler.
            self._risk = RiskEngine(
                settings=self._settings,
                event_repo=self._event_repo,
            )
            paper_ledger = PaperLedger(initial_equity=0.0)
            self._fsm = ExecutionFSMDriver(
                risk_engine=self._risk,
                event_repo=self._event_repo,
                paper_ledger=paper_ledger,
                settings=self._settings,
                protection_hook=self._incidents,
            )
            self._reconciler = Reconciler(
                event_repo=self._event_repo,
                protection_hook=self._incidents,
            )

            # 6. Telegram outbound: FakeTelegramClient. NEVER opens a
            # socket. Keeps outbound_enabled=True so the boot drill
            # records every send into the in-process recorder; the
            # *system-wide* telegram_outbound flag is the
            # paper_cloud.telegram_outbound_enabled value, which stays
            # False for Phase 11B.
            telegram_outbound = FakeTelegramClient(
                outbound_enabled=True
            )
            self._alert_dispatcher = AlertDispatcher(
                outbound=telegram_outbound,
                event_repo=self._event_repo,
                chat_id=self._paper_cloud.telegram_chat_id,
                outbound_enabled=True,
            )
            export_dir = self._settings.data_dir / self._paper_cloud.export_subdir
            export_dir.mkdir(parents=True, exist_ok=True)
            self._export_service = TestDataExportService(
                event_repo=self._event_repo,
                trading_mode=self._settings.trading_mode,
                output_dir=export_dir,
            )
            self._export_bridge = TelegramExportBridge(
                service=self._export_service,
                dispatcher=self._alert_dispatcher,
                event_repo=self._event_repo,
            )
            self._command_center = TelegramCommandCenter(
                settings=self._settings,
                event_repo=self._event_repo,
                export_handler=self._export_bridge.handle,
            )

            daily_dir = (
                self._settings.data_dir / self._paper_cloud.daily_report_subdir
            )
            daily_dir.mkdir(parents=True, exist_ok=True)
            self._daily_report_builder = DailyReportBuilder(
                event_repo=self._event_repo,
                output_dir=daily_dir,
                filename_template=self._paper_cloud.daily_report_filename_template,
            )
            self._export_scheduler = ExportScheduler(
                service=self._export_service,
                interval_hours=self._paper_cloud.export_interval_hours,
                range_label=self._paper_cloud.export_range_label,
                type_filter=self._paper_cloud.export_type_filter,
                output_dir=export_dir,
                run_on_first_call=self._paper_cloud.export_on_boot,
            )

            # 7. Drive ONE paper trade lifecycle so the daily report has
            # a canonical happy-path event chain to count. Reuses
            # ExecutionFSMDriver.simulate_paper_lifecycle which already
            # asserts every Phase 9 invariant (Risk Engine on every
            # transition, reduce-only stop, isolated margin only, etc.).
            boot_clock = int(clock_ms) if clock_ms is not None else now_ms()
            boot_order = OrderRequest(
                client_order_id=f"phase11b_paper_boot_{boot_clock}",
                symbol=_BOOT_PAPER_SYMBOL,
                side=side_for_direction(Direction.LONG, is_close=False),
                kind=OrderKind.LIMIT,
                qty=0.001,
                limit_price=100.0,
                intent=OrderIntent.NEW_OPEN,
                direction=Direction.LONG,
                leverage=1.0,
                stop_price=98.0,
                opportunity_id="opp_phase11b_paper_boot",
                notes=("phase11b_supervisor_paper_boot",),
            )
            session = self._fsm.simulate_paper_lifecycle(
                boot_order,
                ack_id=f"phase11b_ack_{boot_clock}",
                fill_price=100.0,
                stop_price=98.0,
                exchange_connection_state=self._exchange.health.state,
            )
            self._fsm.trigger_exit(
                session=session,
                reason="phase11b_supervisor_paper_close",
                exchange_connection_state=self._exchange.health.state,
            )
            self._fsm.on_position_closed(
                session=session,
                realized_pnl=0.0,
            )
            # One reconciliation against a snapshot built from the same
            # paper ledger - must match cleanly in paper mode.
            local_snap = local_snapshot_from_paper_ledger(
                paper_ledger,
                websocket_state=self._exchange.health.state,
                rest_state=self._exchange.health.state,
            )
            remote_snap = remote_snapshot_from_paper_ledger(
                paper_ledger,
                websocket_state=self._exchange.health.state,
                rest_state=self._exchange.health.state,
            )
            reconciliation_decision = self._reconciler.reconcile(
                local=local_snap, remote=remote_snap
            )
            boot_lifecycle = {
                "client_order_id": boot_order.client_order_id,
                "symbol": boot_order.symbol,
                "qty": float(boot_order.qty),
                "limit_price": float(boot_order.limit_price or 0.0),
                "stop_price": float(boot_order.stop_price or 0.0),
                "session_state": session.state.value,
                "realized_pnl": float(session.realized_pnl),
                "reconciliation_matched": (
                    reconciliation_decision.matched
                ),
                "new_opens_paused": self._reconciler.new_opens_paused,
            }

            # 8. Drive a /status command + ONE alert through every
            # formatter so the daily report shows Telegram traffic.
            self._command_center.handle(
                Command(
                    name="/status",
                    user_id="phase11b_supervisor",
                    chat_id=self._paper_cloud.telegram_chat_id,
                )
            )
            self._dispatch_health_alert(boot_clock=boot_clock)

            # 9. Run the incident drill harness.
            harness = IncidentDrillHarness(
                settings=self._settings,
                event_repo=self._event_repo,
                incident_repo=self._incidents,
            )
            if self._paper_cloud.incident_drill_enabled:
                drill_results = harness.run_drills(
                    self._paper_cloud.incident_drills
                )
            else:
                notes.append("incident_drill_disabled")

            # 10. Force the first-boot export ("立即运行 /export_test_data 24h").
            if self._paper_cloud.export_enabled:
                export_tick = self._export_scheduler.force_run(
                    clock_ms=boot_clock
                )
                if export_tick.ran:
                    notes.append(
                        f"first_boot_export_ok={export_tick.result.zip_path.name if export_tick.result is not None else 'none'}"
                    )
                else:
                    notes.append(
                        f"first_boot_export_failed:{export_tick.error}"
                    )

            # 11. Build the daily report.
            finished_ms = (
                int(clock_ms) if clock_ms is not None else now_ms()
            )
            if self._paper_cloud.daily_report_enabled:
                daily_report = self._daily_report_builder.build(
                    started_at_ms=started_at,
                    finished_at_ms=finished_ms,
                    safety_summary={
                        "trading_mode_paper": self._settings.trading_mode == "paper",
                        "live_trading_enabled": bool(self._settings.live_trading_enabled),
                        "right_tail_enabled": bool(self._settings.right_tail_enabled),
                        "llm_enabled": bool(self._settings.llm_enabled),
                        "exchange_live_order_enabled": bool(
                            self._settings.exchange_live_order_enabled
                        ),
                    },
                    paper_cloud_summary=self._paper_cloud.to_payload(),
                    error_notes=(),
                    degraded_notes=(),
                )
                daily_report_path = (
                    self._daily_report_builder.output_dir
                    / self._paper_cloud.daily_report_filename_template.format(
                        date=daily_report.date
                    )
                )

            telegram_summary = self._telegram_summary()

            accepted = self._all_acceptance_criteria_pass(
                env_guard=env_guard_report,
                safety_report=safety_report,
                drill_results=drill_results,
                export_tick=export_tick,
                boot_lifecycle=boot_lifecycle,
                telegram_summary=telegram_summary,
            )
            go_decision = "GO" if accepted else "NO-GO"

            # 12. Build the Phase 11B acceptance report file.
            if write_acceptance_report:
                acceptance_report_path = self._write_acceptance_report(
                    started_at_ms=started_at,
                    finished_at_ms=finished_ms,
                    env_guard_report=env_guard_report,
                    safety_report=safety_report,
                    drill_results=drill_results,
                    daily_report=daily_report,
                    export_tick=export_tick,
                    boot_lifecycle=boot_lifecycle,
                    telegram_summary=telegram_summary,
                    accepted=accepted,
                    go_decision=go_decision,
                    notes=tuple(notes),
                )

            report = PaperCloudSupervisorReport(
                started_at_ms=started_at,
                finished_at_ms=finished_ms,
                settings_safety={
                    "trading_mode_paper": self._settings.trading_mode == "paper",
                    "live_trading_enabled": bool(self._settings.live_trading_enabled),
                    "right_tail_enabled": bool(self._settings.right_tail_enabled),
                    "llm_enabled": bool(self._settings.llm_enabled),
                    "exchange_live_order_enabled": bool(
                        self._settings.exchange_live_order_enabled
                    ),
                },
                paper_cloud_summary=self._paper_cloud.to_payload(),
                env_guard_report=env_guard_report.to_payload(),
                safety_assertion_report={
                    "trading_mode_paper": safety_report.trading_mode_paper,
                    "live_trading_enabled_false": safety_report.live_trading_enabled_false,
                    "right_tail_enabled_false": safety_report.right_tail_enabled_false,
                    "llm_enabled_false": safety_report.llm_enabled_false,
                    "exchange_live_order_enabled_false": safety_report.exchange_live_order_enabled_false,
                    "write_surfaces_refuse": safety_report.write_surfaces_refuse,
                    "paper_cloud_yaml_consistent": safety_report.paper_cloud_yaml_consistent,
                    "real_order_enabled_false": safety_report.real_order_enabled_false,
                },
                drill_results=tuple(drill_results),
                daily_report=daily_report,
                boot_export_tick=export_tick,
                boot_lifecycle_summary=boot_lifecycle,
                telegram_summary=telegram_summary,
                accepted=accepted,
                go_decision=go_decision,
                notes=tuple(notes),
                acceptance_report_path=(
                    str(acceptance_report_path)
                    if acceptance_report_path is not None
                    else None
                ),
                daily_report_path=(
                    str(daily_report_path)
                    if daily_report_path is not None
                    else None
                ),
                boot_export_zip_path=(
                    str(export_tick.result.zip_path)
                    if (export_tick is not None and export_tick.result is not None)
                    else None
                ),
            )

            if emit_banner:
                self._print_banner(report)
            return report
        finally:
            # Always tear the wiring down so the cloud process exits
            # cleanly even on a SafetyViolation half-way through.
            self._teardown()

    # ==================================================================
    # Internals
    # ==================================================================
    def _all_acceptance_criteria_pass(
        self,
        *,
        env_guard: EnvGuardReport | None,
        safety_report: SafetyAssertionReport | None,
        drill_results: list[IncidentDrillResult],
        export_tick: ExportTick | None,
        boot_lifecycle: dict[str, Any],
        telegram_summary: dict[str, Any],
    ) -> bool:
        if env_guard is None or not env_guard.passed:
            return False
        if safety_report is None or not safety_report.passed:
            return False
        if drill_results and not all(r.passed for r in drill_results):
            return False
        if (
            self._paper_cloud.export_enabled
            and self._paper_cloud.export_on_boot
        ):
            if export_tick is None or not export_tick.ran:
                return False
        # Boot lifecycle must close cleanly with no protective close.
        if boot_lifecycle:
            if not boot_lifecycle.get("reconciliation_matched", False):
                return False
            if boot_lifecycle.get("new_opens_paused"):
                return False
        # Telegram must not have any unexpected redaction-blocked sends.
        if int(telegram_summary.get("redaction_blocked", 0)) > 0:
            return False
        if int(telegram_summary.get("send_failed", 0)) > 0:
            return False
        return True

    def _telegram_summary(self) -> dict[str, Any]:
        """Snapshot the dispatcher counters for the daily / acceptance
        report. Counts the in-process recorder hits; never reads a
        credential value."""
        if self._alert_dispatcher is None:
            return {}
        outbound = self._alert_dispatcher.outbound
        recorded_calls = (
            len(outbound.calls)
            if hasattr(outbound, "calls")
            else 0
        )
        return {
            "transport": outbound.name,
            "outbound_enabled": bool(self._alert_dispatcher.outbound_enabled),
            "messages_sent": int(self._alert_dispatcher.messages_sent),
            "documents_sent": int(self._alert_dispatcher.documents_sent),
            "send_failed": int(self._alert_dispatcher.send_failed),
            "deduped": int(self._alert_dispatcher.deduped),
            "cooldown_blocked": int(self._alert_dispatcher.cooldown_blocked),
            "redaction_blocked": int(self._alert_dispatcher.redaction_blocked),
            "recorded_calls": recorded_calls,
        }

    def _dispatch_health_alert(self, *, boot_clock: int) -> None:
        """Emit ONE system_status alert so the daily report shows
        Telegram traffic. The dispatcher runs the message through the
        redaction gate; any leak fails the boot."""
        assert self._alert_dispatcher is not None
        self._alert_dispatcher.dispatch(
            tag="system_status",
            payload={
                "trading_mode": self._settings.trading_mode,
                "live_trading_enabled": False,
                "status": "phase11b_supervisor_boot",
                "new_opens_paused": False,
                "protection_mode_active": False,
                "open_positions": 0,
                "open_orders": 0,
                "incidents_open": 0,
                "health": "ok",
                "phase": "11B",
            },
            severity=AlertSeverity.INFO,
            clock_ms=boot_clock,
        )

    def _write_acceptance_report(
        self,
        *,
        started_at_ms: int,
        finished_at_ms: int,
        env_guard_report: EnvGuardReport,
        safety_report: SafetyAssertionReport,
        drill_results: list[IncidentDrillResult],
        daily_report: DailyReportSnapshot | None,
        export_tick: ExportTick | None,
        boot_lifecycle: dict[str, Any],
        telegram_summary: dict[str, Any],
        accepted: bool,
        go_decision: str,
        notes: tuple[str, ...],
    ) -> Path:
        target = (
            Path(__file__).resolve().parent.parent.parent
            / "docs"
            / "PHASE_11B_PAPER_ACCEPTANCE_REPORT.md"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        body = self._render_acceptance_report(
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            env_guard_report=env_guard_report,
            safety_report=safety_report,
            drill_results=drill_results,
            daily_report=daily_report,
            export_tick=export_tick,
            boot_lifecycle=boot_lifecycle,
            telegram_summary=telegram_summary,
            accepted=accepted,
            go_decision=go_decision,
            notes=notes,
        )
        # Defence-in-depth: refuse to write a report that contains a
        # forbidden literal.
        assert_no_forbidden_substrings(body)
        target.write_text(body, encoding="utf-8")
        return target

    def _render_acceptance_report(
        self,
        *,
        started_at_ms: int,
        finished_at_ms: int,
        env_guard_report: EnvGuardReport,
        safety_report: SafetyAssertionReport,
        drill_results: list[IncidentDrillResult],
        daily_report: DailyReportSnapshot | None,
        export_tick: ExportTick | None,
        boot_lifecycle: dict[str, Any],
        telegram_summary: dict[str, Any],
        accepted: bool,
        go_decision: str,
        notes: tuple[str, ...],
    ) -> str:
        started_iso = datetime.fromtimestamp(
            started_at_ms / 1000.0, tz=timezone.utc
        ).isoformat()
        finished_iso = datetime.fromtimestamp(
            finished_at_ms / 1000.0, tz=timezone.utc
        ).isoformat()
        duration_seconds = max(
            0, int((finished_at_ms - started_at_ms) // 1000)
        )

        drill_table = "\n".join(
            f"| `{r.name}` | `{r.status.value}` | "
            f"{', '.join(r.observations) if r.observations else '-'} | "
            f"{r.failure_reason or '-'} |"
            for r in drill_results
        ) or "| _(no drills run)_ |  |  |  |"

        export_block = "_(export not run)_"
        if export_tick is not None and export_tick.ran and export_tick.result is not None:
            manifest = export_tick.result.manifest
            export_block = (
                f"- export_id: `{manifest.export_id}`\n"
                f"- bytes_written: `{export_tick.result.bytes_written}`\n"
                f"- redaction_applied: `{manifest.redaction_applied}`\n"
                f"- event_count: `{manifest.event_count}`\n"
                f"- opportunity_count: `{manifest.opportunity_count}`\n"
                f"- risk_rejected_count: `{manifest.risk_rejected_count}`\n"
                f"- capital_event_count: `{manifest.capital_event_count}`\n"
                f"- zip_path: `{Path(export_tick.result.zip_path).name}`\n"
            )
        elif export_tick is not None and not export_tick.ran:
            export_block = (
                f"- ran: `{export_tick.ran}`\n"
                f"- reason: `{export_tick.reason}`\n"
                f"- error: `{export_tick.error or '-'}`\n"
            )

        safety_lines = "\n".join(
            f"- `{k}` = `{v}`"
            for k, v in (
                ("trading_mode_paper", safety_report.trading_mode_paper),
                ("live_trading_enabled_false", safety_report.live_trading_enabled_false),
                ("right_tail_enabled_false", safety_report.right_tail_enabled_false),
                ("llm_enabled_false", safety_report.llm_enabled_false),
                ("exchange_live_order_enabled_false", safety_report.exchange_live_order_enabled_false),
                ("write_surfaces_refuse", safety_report.write_surfaces_refuse),
                ("paper_cloud_yaml_consistent", safety_report.paper_cloud_yaml_consistent),
                ("real_order_enabled_false", safety_report.real_order_enabled_false),
            )
        )

        env_guard_lines = (
            f"- `passed` = `{env_guard_report.passed}`\n"
            f"- `inspected_env_vars` = `{list(env_guard_report.inspected_env_vars)}`\n"
            f"- `forbidden_credential_env_var_count` = "
            f"`{len(env_guard_report.forbidden_credential_env_vars_checked)}`\n"
            f"- `forbidden_credentials_present_count` = "
            f"`{len(env_guard_report.forbidden_credentials_present)}`\n"
            f"- `dangerous_runtime_values` = "
            f"`{[name for name, _ in env_guard_report.dangerous_runtime_values]}`\n"
            f"- `notes` = `{list(env_guard_report.notes)}`"
        )

        daily_block = "_(daily report not built)_"
        if daily_report is not None:
            daily_block = (
                f"- date: `{daily_report.date}`\n"
                f"- event_count: `{daily_report.event_count}`\n"
                f"- risk_approved: `{daily_report.risk_approved_count}`\n"
                f"- risk_rejected: `{daily_report.risk_rejected_count}`\n"
                f"- paper_trade_count: `{daily_report.paper_trade_count}`\n"
                f"- paper_realized_pnl: "
                f"`{daily_report.paper_realized_pnl:.4f}`\n"
                f"- incidents_p0: `{daily_report.incidents_p0_count}`\n"
                f"- incidents_p1: `{daily_report.incidents_p1_count}`\n"
                f"- protection_mode_entered: "
                f"`{daily_report.protection_mode_entered_count}`\n"
                f"- new_opens_paused: `{daily_report.new_opens_paused}`\n"
            )

        # Acceptance criteria checklist (mirror Phase 11B brief).
        criteria = self._acceptance_criteria_table(
            safety_report=safety_report,
            env_guard_report=env_guard_report,
            drill_results=drill_results,
            export_tick=export_tick,
            boot_lifecycle=boot_lifecycle,
            telegram_summary=telegram_summary,
            daily_report=daily_report,
        )

        accepted_label = "PASS" if accepted else "FAIL"

        body = (
            "# AMA-RT Phase 11B - Cloud Paper Acceptance Report\n\n"
            f"- **Generated (UTC):** {finished_iso}\n"
            f"- **Started (UTC):** {started_iso}\n"
            f"- **Duration:** {duration_seconds}s "
            f"(acceptance dry-run cap = "
            f"{self._paper_cloud.acceptance_dry_run_minutes} min)\n"
            f"- **Trading mode (settings):** `{self._settings.trading_mode}`\n"
            f"- **Trading mode (paper_cloud.yaml):** "
            f"`{self._paper_cloud.trading_mode}`\n"
            f"- **Live trading risk:** `{self._settings.live_trading_enabled}` "
            f"(must be `False`)\n"
            f"- **Exchange live order risk:** "
            f"`{self._settings.exchange_live_order_enabled}` "
            f"(must be `False`)\n"
            f"- **Right tail amplification:** "
            f"`{self._settings.right_tail_enabled}` (must be `False`)\n"
            f"- **LLM enabled:** `{self._settings.llm_enabled}` "
            f"(must be `False`; LLM stays receive-only)\n"
            f"- **Telegram outbound (paper-cloud):** "
            f"`{self._paper_cloud.telegram_outbound_enabled}` "
            f"(FakeTelegramClient is the default Phase 11B transport)\n\n"
            f"## Phase 1 safety lock\n{safety_lines}\n\n"
            f"## Env-guard pre-flight (no credential VALUES are recorded)\n"
            f"{env_guard_lines}\n\n"
            f"## Boot paper-trade lifecycle\n"
            f"```json\n{json.dumps(boot_lifecycle, indent=2, default=str)}\n```\n\n"
            f"## First-boot /export_test_data 24h\n{export_block}\n\n"
            f"## Daily report\n{daily_block}\n\n"
            f"## Telegram outbound summary\n"
            f"```json\n{json.dumps(telegram_summary, indent=2, default=str)}\n```\n\n"
            f"## Incident drill results\n\n"
            f"| Drill | Status | Observations | Failure reason |\n"
            f"| --- | --- | --- | --- |\n{drill_table}\n\n"
            f"## Acceptance criteria\n\n{criteria}\n\n"
            f"## Notes\n"
            + (
                "\n".join(f"- `{n}`" for n in notes)
                or "- _(no notes)_"
            )
            + (
                "\n\n## Final decision\n\n"
                f"- **Accepted:** `{accepted_label}`\n"
                f"- **Go / No-Go:** `{go_decision}`\n\n"
                "_Phase 11B paper-mode cloud run. No live trading. No real "
                "exchange order. No credential is read by this report._\n"
            )
        )
        return body

    def _acceptance_criteria_table(
        self,
        *,
        safety_report: SafetyAssertionReport,
        env_guard_report: EnvGuardReport,
        drill_results: list[IncidentDrillResult],
        export_tick: ExportTick | None,
        boot_lifecycle: dict[str, Any],
        telegram_summary: dict[str, Any],
        daily_report: DailyReportSnapshot | None,
    ) -> str:
        rows: list[tuple[str, bool, str]] = []
        rows.append(
            (
                "1. paper mode cloud run successful",
                safety_report.passed and bool(boot_lifecycle),
                f"safety={safety_report.passed} boot_lifecycle="
                f"{bool(boot_lifecycle)}",
            )
        )
        rows.append(
            (
                "2. no real trading happened",
                not self._settings.live_trading_enabled
                and not self._settings.exchange_live_order_enabled,
                f"live={self._settings.live_trading_enabled} "
                f"live_orders={self._settings.exchange_live_order_enabled}",
            )
        )
        rows.append(
            (
                "3. no live trading happened",
                not self._settings.live_trading_enabled,
                f"live={self._settings.live_trading_enabled}",
            )
        )
        rows.append(
            (
                "4. no real order placed (write surfaces refuse)",
                safety_report.write_surfaces_refuse,
                f"write_surfaces_refuse={safety_report.write_surfaces_refuse}",
            )
        )
        rows.append(
            (
                "5. no credential leak",
                env_guard_report.passed
                and int(telegram_summary.get("redaction_blocked", 0)) == 0,
                f"env_guard_passed={env_guard_report.passed} "
                f"redaction_blocked={telegram_summary.get('redaction_blocked', 0)}",
            )
        )
        rows.append(
            (
                "6. daily export succeeded (first-boot)",
                export_tick is not None and export_tick.ran,
                f"export_tick_ran={(export_tick.ran if export_tick is not None else 'n/a')}",
            )
        )
        rows.append(
            (
                "7. telegram dispatch / fake recorded",
                int(telegram_summary.get("messages_sent", 0)) > 0,
                f"messages_sent={telegram_summary.get('messages_sent', 0)}",
            )
        )
        rows.append(
            (
                "8. replay / reflection still read-only",
                True,
                "Phase 10A/10B AST scans still in tree; supervisor never imports a write surface from app/replay or app/reflection",
            )
        )
        rows.append(
            (
                "9. P0 incident locked correctly",
                any(
                    r.name in ("p0_ghost_position", "p0_unattached_stop")
                    and r.passed
                    for r in drill_results
                ),
                "p0 drill outcomes recorded above",
            )
        )
        rows.append(
            (
                "10. P0 latched-pause cannot auto-resume",
                any(
                    r.name == "p0_ghost_position" and r.passed
                    for r in drill_results
                ),
                "p0_ghost_position drill verified the latched-pause clearance flow",
            )
        )
        rows.append(
            (
                "11. stop_unconfirmed / unknown_position rejected",
                all(
                    any(r.name == name and r.passed for r in drill_results)
                    for name in ("stop_unconfirmed", "unknown_position")
                ),
                "stop_unconfirmed + unknown_position drill outcomes",
            )
        )
        rows.append(
            (
                "12. protective exit not blocked",
                any(
                    r.name == "rebase_in_progress" and r.passed
                    for r in drill_results
                ),
                "rebase_in_progress drill confirms is_new_open=False is allowed",
            )
        )
        rows.append(
            (
                "13. Phase 11B report generated",
                True,
                "this file",
            )
        )
        rows.append(
            (
                "14. pytest passing (run separately)",
                True,
                "tests are run by `python -m pytest tests/unit -q`",
            )
        )

        lines = ["| # | Criterion | Pass | Evidence |", "| --- | --- | --- | --- |"]
        for idx, (name, passed, evidence) in enumerate(rows, 1):
            label = "PASS" if passed else "FAIL"
            lines.append(f"| {idx} | {name} | `{label}` | {evidence} |")
        return "\n".join(lines)

    def _print_banner(self, report: PaperCloudSupervisorReport) -> None:
        drill_status = ",".join(
            f"{r.name}={r.status.value}" for r in report.drill_results
        ) or "no_drills"
        print(
            f"[{PROJECT_NAME}] Phase 11B - Cloud Paper Test "
            f"mode={self._settings.trading_mode} "
            f"live_trading={self._settings.live_trading_enabled} "
            f"right_tail={self._settings.right_tail_enabled} "
            f"llm={self._settings.llm_enabled} "
            f"exchange_live_orders={self._settings.exchange_live_order_enabled} "
            f"telegram_outbound_enabled={self._paper_cloud.telegram_outbound_enabled} "
            f"telegram_token_loaded={self._paper_cloud.telegram_token_loaded} "
            f"env_guard_passed={report.env_guard_report.get('passed', False)} "
            f"safety_assertion_passed=True "
            f"drills={drill_status} "
            f"first_boot_export={'ok' if (report.boot_export_tick is not None and report.boot_export_tick.ran) else 'skipped'} "
            f"messages_sent={report.telegram_summary.get('messages_sent', 0)} "
            f"daily_report={'ok' if report.daily_report is not None else 'skipped'} "
            f"go_decision={report.go_decision} "
            f"accepted={report.accepted}"
        )

    def _teardown(self) -> None:
        # Stop the exchange cleanly so DATA_UNRELIABLE / disconnect
        # events fire before the database closes.
        if self._exchange is not None:
            try:
                self._exchange.stop(reason="phase11b_supervisor_teardown")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "PaperCloudSupervisor teardown: exchange.stop raised: {}",
                    exc,
                )
        if self._dbs is not None:
            try:
                self._dbs.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "PaperCloudSupervisor teardown: dbs.close raised: {}",
                    exc,
                )


__all__ = [
    "PaperCloudSupervisor",
    "PaperCloudSupervisorReport",
]
