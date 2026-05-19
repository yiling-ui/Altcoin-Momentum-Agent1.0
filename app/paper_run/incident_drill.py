"""Phase 11B - Incident drill harness.

Runs the eight drills the Phase 11B brief requires:

  1. ``stop_unconfirmed``        - Risk Engine rejects new open.
  2. ``unknown_position``        - Risk Engine rejects new open.
  3. ``data_degraded``           - No-Trade Gate rejects attack intent.
  4. ``p0_ghost_position``       - Reconciler produces a P0 + latches
                                   the new-opens pause.
  5. ``p0_unattached_stop``      - Reconciler produces a P0
                                   ``UNATTACHED_STOP`` mismatch.
  6. ``rebase_in_progress``      - Risk Engine rejects new opens while
                                   ``CapitalFlowEngine.is_rebase_in_progress``
                                   is True; reduce-only protective
                                   exit STILL succeeds.
  7. ``telegram_export_failure`` - The Telegram export bridge writes a
                                   ``DATA_EXPORT_FAILED`` row when the
                                   underlying transport raises.
  8. ``llm_degraded``            - The LLM Guarded Interpreter returns
                                   a degraded result tagged
                                   ``llm_disabled`` when
                                   ``llm_enabled=False``.

Each drill is isolated: it builds its own disposable wiring (fresh
:class:`RiskEngine` / fresh :class:`Reconciler` / etc.) so the
supervisor's main loop is never perturbed. Every drill writes audit
events to the SAME :class:`EventRepository` so the daily report
captures the drill activity.

Phase 11B boundary
------------------

The harness:

  - opens NO socket
  - imports NO exchange / LLM / Telegram SDK
  - reads NO ``os.environ``
  - never calls ``ExchangeClientBase.create_order`` /
    ``cancel_order`` / ``set_leverage`` / ``set_margin_mode``
  - drives every drill against in-process fakes / paper ledgers
  - never bypasses the Risk Engine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

from loguru import logger

from app.config.settings import Settings
from app.core.clock import now_ms
from app.core.enums import (
    Direction,
    ExchangeConnectionState,
    IncidentLevel,
    ManipulationLevel,
    RiskRejectReason,
)
from app.core.errors import TelegramTransportError
from app.core.events import EventType
from app.database.repositories import EventRepository
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
from app.llm.client import FakeLLMClient
from app.llm.interpreter import LLMGuardedInterpreter
from app.llm.models import LLMInterpretationInput
from app.reconciliation.models import (
    EquitySnapshot,
    LinkHealth,
    LocalSnapshot,
    OrderView,
    PositionView,
    RemoteSnapshot,
    StopView,
)
from app.reconciliation.reconciler import Reconciler
from app.risk.engine import RiskEngine, RiskRequest
from app.telegram.alerts import AlertDispatcher
from app.telegram.commands import Command, CommandStatus
from app.telegram.exports import TelegramExportBridge
from app.telegram.outbound import FakeTelegramClient


class DrillStatus(str, Enum):
    """Result of one drill."""

    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass
class IncidentDrillResult:
    """One drill outcome.

    ``observations`` carries deterministic facts the supervisor stitches
    into the acceptance report. Every observation is a short string -
    the harness NEVER writes a credential value.
    """

    name: str
    status: DrillStatus
    observations: tuple[str, ...] = field(default_factory=tuple)
    failure_reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.status is DrillStatus.PASS

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "observations": list(self.observations),
            "failure_reason": self.failure_reason,
        }


# A stub capital-flow engine - just enough surface for RiskEngine's
# rebase-in-progress / tier auto-population checks. Wired into
# RiskEngine.set_capital_flow_engine for the rebase_in_progress drill
# only. The real CapitalFlowEngine is heavier and would emit
# CAPITAL_DEPOSIT events on every construction; we keep this stub
# strictly local.
class _RebaseStubCapitalFlow:
    """Lightweight stand-in for the rebase_in_progress drill.

    Phase 11B uses a stub here on purpose: the real
    :class:`CapitalFlowEngine` would emit additional events that
    perturb the daily-report counters in ways that are unrelated to
    the drill itself. The Risk Engine's only requirement is that the
    attached object exposes ``is_rebase_in_progress`` (bool) +
    ``trading_capital`` / ``initial_capital`` floats.
    """

    def __init__(self) -> None:
        self.is_rebase_in_progress: bool = True
        self.trading_capital: float = 100.0
        self.initial_capital: float = 100.0


@dataclass
class IncidentDrillHarness:
    """Phase 11B incident drill orchestrator.

    Construct ONCE per supervisor boot and call :meth:`run_drills` (or
    one of the per-drill helpers). The harness re-uses the wired
    :class:`Settings` + :class:`EventRepository` + (optional)
    :class:`IncidentRepository`.
    """

    settings: Settings
    event_repo: EventRepository
    incident_repo: IncidentRepository
    SOURCE_MODULE: str = field(default="paper_run.incident_drill", init=False)

    # ------------------------------------------------------------------
    # Public dispatcher
    # ------------------------------------------------------------------
    def run_drills(
        self,
        drills: Iterable[str],
    ) -> list[IncidentDrillResult]:
        """Run every drill name in order and return the results."""
        results: list[IncidentDrillResult] = []
        for name in drills:
            results.append(self.run_drill(name))
        return results

    def run_drill(self, name: str) -> IncidentDrillResult:
        """Dispatch one drill by name."""
        handler = self._handler_for(name)
        if handler is None:
            return IncidentDrillResult(
                name=name,
                status=DrillStatus.SKIPPED,
                observations=(f"unknown_drill:{name}",),
                failure_reason="unknown_drill",
            )
        try:
            return handler()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "IncidentDrillHarness drill={} raised {}: {}",
                name,
                type(exc).__name__,
                exc,
            )
            return IncidentDrillResult(
                name=name,
                status=DrillStatus.FAIL,
                observations=(f"unexpected_exception:{type(exc).__name__}",),
                failure_reason=str(exc),
            )

    def _handler_for(self, name: str):
        return {
            "stop_unconfirmed": self.drill_stop_unconfirmed,
            "unknown_position": self.drill_unknown_position,
            "data_degraded": self.drill_data_degraded,
            "p0_ghost_position": self.drill_p0_ghost_position,
            "p0_unattached_stop": self.drill_p0_unattached_stop,
            "rebase_in_progress": self.drill_rebase_in_progress,
            "telegram_export_failure": self.drill_telegram_export_failure,
            "llm_degraded": self.drill_llm_degraded,
        }.get(name)

    # ==================================================================
    # Drill 1 - stop_unconfirmed
    # ==================================================================
    def drill_stop_unconfirmed(self) -> IncidentDrillResult:
        risk = self._fresh_risk_engine()
        decision = risk.evaluate(
            RiskRequest(
                source_module=self.SOURCE_MODULE,
                action="drill_stop_unconfirmed",
                symbol="DRILLUSDT",
                live_trading_required=False,
                stop_unconfirmed=True,
                is_new_open=True,
            )
        )
        if decision.approved:
            return IncidentDrillResult(
                name="stop_unconfirmed",
                status=DrillStatus.FAIL,
                observations=("risk_engine_did_not_reject",),
                failure_reason=(
                    "Phase 11B drill: stop_unconfirmed must reject new "
                    f"opens; got approved={decision.approved}"
                ),
            )
        if RiskRejectReason.STOP_UNCONFIRMED.value not in decision.reasons:
            return IncidentDrillResult(
                name="stop_unconfirmed",
                status=DrillStatus.FAIL,
                observations=tuple(decision.reasons),
                failure_reason=(
                    "Phase 11B drill: STOP_UNCONFIRMED missing from reasons"
                ),
            )
        return IncidentDrillResult(
            name="stop_unconfirmed",
            status=DrillStatus.PASS,
            observations=(
                f"reasons={','.join(decision.reasons)}",
                "risk_engine_rejected_new_open",
            ),
        )

    # ==================================================================
    # Drill 2 - unknown_position
    # ==================================================================
    def drill_unknown_position(self) -> IncidentDrillResult:
        risk = self._fresh_risk_engine()
        decision = risk.evaluate(
            RiskRequest(
                source_module=self.SOURCE_MODULE,
                action="drill_unknown_position",
                symbol="DRILLUSDT",
                live_trading_required=False,
                unknown_position=True,
                is_new_open=True,
            )
        )
        if decision.approved:
            return IncidentDrillResult(
                name="unknown_position",
                status=DrillStatus.FAIL,
                observations=("risk_engine_did_not_reject",),
                failure_reason=(
                    "Phase 11B drill: unknown_position must reject new opens"
                ),
            )
        if RiskRejectReason.UNKNOWN_POSITION.value not in decision.reasons:
            return IncidentDrillResult(
                name="unknown_position",
                status=DrillStatus.FAIL,
                observations=tuple(decision.reasons),
                failure_reason=(
                    "Phase 11B drill: UNKNOWN_POSITION missing from reasons"
                ),
            )
        return IncidentDrillResult(
            name="unknown_position",
            status=DrillStatus.PASS,
            observations=(
                f"reasons={','.join(decision.reasons)}",
                "risk_engine_rejected_new_open",
            ),
        )

    # ==================================================================
    # Drill 3 - data_degraded
    # ==================================================================
    def drill_data_degraded(self) -> IncidentDrillResult:
        risk = self._fresh_risk_engine()
        decision = risk.evaluate(
            RiskRequest(
                source_module=self.SOURCE_MODULE,
                action="drill_data_degraded",
                symbol="DRILLUSDT",
                live_trading_required=False,
                attack_intent=True,
                is_new_open=True,
                is_data_degraded=True,
                exchange_connection_state=ExchangeConnectionState.DEGRADED,
            )
        )
        if decision.approved:
            return IncidentDrillResult(
                name="data_degraded",
                status=DrillStatus.FAIL,
                observations=("risk_engine_did_not_reject",),
                failure_reason=(
                    "Phase 11B drill: DATA_DEGRADED on attack intent must "
                    "reject"
                ),
            )
        # The No-Trade Gate populates DATA_DEGRADED into the audit
        # reasons; we accept any reason that mentions degraded.
        observations = tuple(decision.reasons)
        if not any(
            "data_degraded" in r or "exchange" in r for r in observations
        ):
            return IncidentDrillResult(
                name="data_degraded",
                status=DrillStatus.FAIL,
                observations=observations,
                failure_reason=(
                    "Phase 11B drill: expected a data_degraded / exchange "
                    "reason"
                ),
            )
        return IncidentDrillResult(
            name="data_degraded",
            status=DrillStatus.PASS,
            observations=observations + ("no_trade_gate_rejected_attack",),
        )

    # ==================================================================
    # Drill 4 - p0_ghost_position
    # ==================================================================
    def drill_p0_ghost_position(self) -> IncidentDrillResult:
        # Defensive baseline cleanup: resolve any pre-existing open P0
        # incidents from a previous run / earlier drill so the
        # latched-pause clearance flow has a clean starting state.
        # Production never crosses this path - pre-existing P0s in a
        # real deploy MUST be resolved through the runbook before
        # operator-initiated drills run.
        for stale in self.incident_repo.list_open_incidents(
            level=IncidentLevel.P0
        ):
            self.incident_repo.resolve_incident(
                incident_id=stale.incident_id,
                resolution="phase11b_drill_baseline_cleanup",
                source_module=self.SOURCE_MODULE,
            )
        if self.incident_repo.in_protection_mode:
            self.incident_repo.exit_protection_mode(
                reason="phase11b_drill_baseline_cleanup",
                source_module=self.SOURCE_MODULE,
            )

        reconciler = self._fresh_reconciler()
        local = LocalSnapshot(
            equity=EquitySnapshot(total_equity=100.0),
            link=LinkHealth(
                websocket_state=ExchangeConnectionState.CONNECTED,
                rest_state=ExchangeConnectionState.CONNECTED,
            ),
        )
        remote = RemoteSnapshot(
            positions=(
                PositionView(
                    position_id="ghost_pos_1",
                    symbol="GHOSTUSDT",
                    direction="long",
                    qty=0.001,
                    entry_price=100.0,
                    stop_price=98.0,
                    stop_confirmed=True,
                    margin_mode="isolated",
                    leverage=1.0,
                ),
            ),
            equity=EquitySnapshot(total_equity=100.0),
            link=LinkHealth(
                websocket_state=ExchangeConnectionState.CONNECTED,
                rest_state=ExchangeConnectionState.CONNECTED,
            ),
        )
        decision = reconciler.reconcile(local=local, remote=remote)
        if decision.matched:
            return IncidentDrillResult(
                name="p0_ghost_position",
                status=DrillStatus.FAIL,
                observations=(),
                failure_reason="reconciler_did_not_detect_ghost",
            )
        if not decision.has_p0:
            return IncidentDrillResult(
                name="p0_ghost_position",
                status=DrillStatus.FAIL,
                observations=tuple(m.mismatch_type.value for m in decision.mismatches),
                failure_reason="reconciler_did_not_classify_p0",
            )
        if not reconciler.new_opens_paused:
            return IncidentDrillResult(
                name="p0_ghost_position",
                status=DrillStatus.FAIL,
                observations=("new_opens_paused_not_set",),
                failure_reason="new_opens_paused_must_be_True_after_p0",
            )
        if not reconciler.p0_latched_pause:
            return IncidentDrillResult(
                name="p0_ghost_position",
                status=DrillStatus.FAIL,
                observations=("p0_latched_pause_not_set",),
                failure_reason="p0_latched_pause_must_be_True_after_p0",
            )
        # Verify a clean reconciliation alone does NOT auto-clear the
        # latch (Phase 9 fix-up rule).
        clean_decision = reconciler.reconcile(local=local, remote=local)
        observations = (
            f"p0_count={sum(1 for m in decision.mismatches if m.severity.value == 'P0')}",
            f"new_opens_paused_after_clean={reconciler.new_opens_paused}",
            f"p0_latched_pause_after_clean={reconciler.p0_latched_pause}",
            f"incidents_opened={len(decision.incidents_opened)}",
        )
        if not reconciler.new_opens_paused:
            return IncidentDrillResult(
                name="p0_ghost_position",
                status=DrillStatus.FAIL,
                observations=observations,
                failure_reason=(
                    "p0 latched-pause cleared by a single clean reconciliation"
                ),
            )
        # Operator confirms + protection exits + incident resolved + clean.
        for incident_id in decision.incidents_opened:
            self.incident_repo.resolve_incident(
                incident_id=incident_id,
                resolution="phase11b_drill_resolved",
                source_module=self.SOURCE_MODULE,
            )
        reconciler.exit_protection_mode(reason="phase11b_drill_operator")
        reconciler.mark_p0_incidents_resolved(note="phase11b_drill_resolved")
        reconciler.confirm_operator_resume(reason="phase11b_drill_operator")
        cleared_decision = reconciler.reconcile(local=local, remote=local)
        observations = observations + (
            f"new_opens_paused_after_resume={reconciler.new_opens_paused}",
            f"p0_latched_pause_after_resume={reconciler.p0_latched_pause}",
            f"clean_decision_matched={cleared_decision.matched}",
        )
        if reconciler.new_opens_paused or reconciler.p0_latched_pause:
            return IncidentDrillResult(
                name="p0_ghost_position",
                status=DrillStatus.FAIL,
                observations=observations,
                failure_reason=(
                    "p0 latched-pause did not clear after operator confirm"
                ),
            )
        return IncidentDrillResult(
            name="p0_ghost_position",
            status=DrillStatus.PASS,
            observations=observations,
        )

    # ==================================================================
    # Drill 5 - p0_unattached_stop
    # ==================================================================
    def drill_p0_unattached_stop(self) -> IncidentDrillResult:
        reconciler = self._fresh_reconciler()
        position = PositionView(
            position_id="pos_drill_unattached",
            symbol="UNATTACHEDUSDT",
            direction="long",
            qty=0.001,
            entry_price=100.0,
            stop_price=98.0,
            stop_confirmed=True,
            margin_mode="isolated",
            leverage=1.0,
        )
        local_stop = StopView(
            stop_order_id="stop_drill_local",
            position_id="pos_drill_unattached",
            symbol="UNATTACHEDUSDT",
            qty=0.001,
            stop_price=98.0,
            side="sell",
            reduce_only=True,
        )
        local = LocalSnapshot(
            positions=(position,),
            stops=(local_stop,),
            equity=EquitySnapshot(total_equity=100.0),
            link=LinkHealth(
                websocket_state=ExchangeConnectionState.CONNECTED,
                rest_state=ExchangeConnectionState.CONNECTED,
            ),
        )
        remote = RemoteSnapshot(
            positions=(position,),
            stops=(),  # remote has NO stop on this position - unattached.
            equity=EquitySnapshot(total_equity=100.0),
            link=LinkHealth(
                websocket_state=ExchangeConnectionState.CONNECTED,
                rest_state=ExchangeConnectionState.CONNECTED,
            ),
        )
        decision = reconciler.reconcile(local=local, remote=remote)
        if decision.matched:
            return IncidentDrillResult(
                name="p0_unattached_stop",
                status=DrillStatus.FAIL,
                observations=(),
                failure_reason="reconciler_did_not_detect_unattached_stop",
            )
        if not decision.has_p0:
            return IncidentDrillResult(
                name="p0_unattached_stop",
                status=DrillStatus.FAIL,
                observations=tuple(m.mismatch_type.value for m in decision.mismatches),
                failure_reason="reconciler_did_not_classify_p0",
            )
        if not reconciler.new_opens_paused:
            return IncidentDrillResult(
                name="p0_unattached_stop",
                status=DrillStatus.FAIL,
                observations=("new_opens_paused_not_set",),
                failure_reason="new_opens_paused_must_be_True_after_p0",
            )
        # Cleanup the drill's own P0 incidents + protection mode so a
        # later drill / re-run starts clean.
        for incident_id in decision.incidents_opened:
            self.incident_repo.resolve_incident(
                incident_id=incident_id,
                resolution="phase11b_drill_p0_unattached_stop_cleanup",
                source_module=self.SOURCE_MODULE,
            )
        if self.incident_repo.in_protection_mode:
            self.incident_repo.exit_protection_mode(
                reason="phase11b_drill_p0_unattached_stop_cleanup",
                source_module=self.SOURCE_MODULE,
            )
        return IncidentDrillResult(
            name="p0_unattached_stop",
            status=DrillStatus.PASS,
            observations=(
                f"mismatches={','.join(m.mismatch_type.value for m in decision.mismatches)}",
                f"p0_latched_pause={reconciler.p0_latched_pause}",
                f"incidents_opened={len(decision.incidents_opened)}",
            ),
        )

    # ==================================================================
    # Drill 6 - rebase_in_progress
    # ==================================================================
    def drill_rebase_in_progress(self) -> IncidentDrillResult:
        risk = self._fresh_risk_engine()
        stub = _RebaseStubCapitalFlow()
        risk.set_capital_flow_engine(stub)

        # 6a. New open while rebase in progress -> rejected.
        decision_open = risk.evaluate(
            RiskRequest(
                source_module=self.SOURCE_MODULE,
                action="drill_rebase_in_progress_new_open",
                symbol="REBASEUSDT",
                live_trading_required=False,
                is_new_open=True,
            )
        )
        if decision_open.approved:
            return IncidentDrillResult(
                name="rebase_in_progress",
                status=DrillStatus.FAIL,
                observations=("risk_engine_did_not_reject_new_open",),
                failure_reason=(
                    "Phase 11B drill: REBASE_IN_PROGRESS must reject new opens"
                ),
            )
        if (
            RiskRejectReason.REBASE_IN_PROGRESS.value
            not in decision_open.reasons
        ):
            return IncidentDrillResult(
                name="rebase_in_progress",
                status=DrillStatus.FAIL,
                observations=tuple(decision_open.reasons),
                failure_reason=(
                    "Phase 11B drill: REBASE_IN_PROGRESS missing from reasons"
                ),
            )

        # 6b. Reduce-only protective close still allowed.
        decision_exit = risk.evaluate(
            RiskRequest(
                source_module=self.SOURCE_MODULE,
                action="drill_rebase_in_progress_exit",
                symbol="REBASEUSDT",
                live_trading_required=False,
                is_new_open=False,
            )
        )
        if not decision_exit.approved:
            return IncidentDrillResult(
                name="rebase_in_progress",
                status=DrillStatus.FAIL,
                observations=tuple(decision_exit.reasons),
                failure_reason=(
                    "Phase 11B drill: protective exit (is_new_open=False) "
                    "must NOT be blocked by REBASE_IN_PROGRESS"
                ),
            )

        return IncidentDrillResult(
            name="rebase_in_progress",
            status=DrillStatus.PASS,
            observations=(
                f"new_open_reasons={','.join(decision_open.reasons)}",
                "protective_exit_approved",
            ),
        )

    # ==================================================================
    # Drill 7 - telegram_export_failure
    # ==================================================================
    def drill_telegram_export_failure(self) -> IncidentDrillResult:
        # Build a disposable export service rooted at a tmp dir under
        # data_dir so the drill does not pollute the daily exports.
        tmp_export_dir: Path = (
            self.settings.data_dir / "reports" / "drill_exports"
        )
        tmp_export_dir.mkdir(parents=True, exist_ok=True)
        service = TestDataExportService(
            event_repo=self.event_repo,
            trading_mode=self.settings.trading_mode,
            output_dir=tmp_export_dir,
        )
        # Telegram client that fails on send_document.
        failing_client = FakeTelegramClient(
            outbound_enabled=True,
            failure_mode="phase11b_drill_inject_transport_failure",
        )
        dispatcher = AlertDispatcher(
            outbound=failing_client,
            event_repo=self.event_repo,
            chat_id="phase11b_drill",
            outbound_enabled=True,
        )
        bridge = TelegramExportBridge(
            service=service,
            dispatcher=dispatcher,
            event_repo=self.event_repo,
        )
        safety_snapshot = {
            "trading_mode": self.settings.trading_mode,
            "live_trading_enabled": False,
            "right_tail_enabled": False,
            "llm_enabled": False,
            "exchange_live_order_enabled": False,
        }
        result = bridge.handle(
            command=Command(
                name="/export_test_data",
                user_id="phase11b_drill_user",
                args=("24h",),
                chat_id="phase11b_drill",
            ),
            settings=self.settings,
            safety_snapshot=safety_snapshot,
        )
        if result.status is CommandStatus.OK:
            return IncidentDrillResult(
                name="telegram_export_failure",
                status=DrillStatus.FAIL,
                observations=(f"status={result.status.value}",),
                failure_reason=(
                    "Phase 11B drill: failing transport must surface "
                    "EXECUTION_ERROR; got OK"
                ),
            )
        if dispatcher.send_failed == 0:
            return IncidentDrillResult(
                name="telegram_export_failure",
                status=DrillStatus.FAIL,
                observations=(
                    f"dispatcher.send_failed={dispatcher.send_failed}",
                ),
                failure_reason=(
                    "Phase 11B drill: dispatcher.send_failed must be > 0 "
                    "after a transport drop"
                ),
            )
        # The bridge MUST have written a DATA_EXPORT_FAILED audit row.
        recent_failures = self.event_repo.list_events(
            event_type=EventType.DATA_EXPORT_FAILED,
            source_module="telegram.exports",
        )
        if not recent_failures:
            return IncidentDrillResult(
                name="telegram_export_failure",
                status=DrillStatus.FAIL,
                observations=(
                    f"command_status={result.status.value}",
                    f"dispatcher.send_failed={dispatcher.send_failed}",
                ),
                failure_reason=(
                    "Phase 11B drill: DATA_EXPORT_FAILED audit event must "
                    "be present in events.db"
                ),
            )
        return IncidentDrillResult(
            name="telegram_export_failure",
            status=DrillStatus.PASS,
            observations=(
                f"command_status={result.status.value}",
                f"dispatcher.send_failed={dispatcher.send_failed}",
                f"data_export_failed_events={len(recent_failures)}",
                f"failing_client_failed_calls={len(failing_client.failed_calls)}",
            ),
        )

    # ==================================================================
    # Drill 8 - llm_degraded
    # ==================================================================
    def drill_llm_degraded(self) -> IncidentDrillResult:
        # llm_enabled is False per Phase 1 lock. The interpreter must
        # short-circuit to a degraded result tagged ``llm_disabled``.
        # The fake client must NEVER be called.
        fake_payload = {
            "narrative": "phase11b drill: llm degraded short-circuit",
            "catalyst": "weak",
            "evidence_quality": "C",
            "source_diversity": 1,
            "kol_concentration": 0.1,
            "bot_risk": 0.1,
            "hype_stage": "early",
            "contradictions": [],
            "risk_tags": [],
            "confidence": 0.4,
        }
        fake_client = FakeLLMClient(
            payload=fake_payload, model_name="phase11b-drill-fake"
        )
        interpreter = LLMGuardedInterpreter(
            client=fake_client,
            event_repo=self.event_repo,
            llm_enabled=False,
        )
        result = interpreter.interpret(
            LLMInterpretationInput(
                source_text=(
                    "phase11b drill: llm degraded - no socket, no clean "
                    "result, llm_enabled=False"
                ),
                symbol="DRILLUSDT",
                opportunity_id="opp_phase11b_drill_llm",
                anomaly_score=82.0,
                sources=("internal:phase11b_drill",),
                correlation_id="phase11b-drill-llm",
            )
        )
        if not result.degraded:
            return IncidentDrillResult(
                name="llm_degraded",
                status=DrillStatus.FAIL,
                observations=(),
                failure_reason="llm_interpreter_did_not_degrade",
            )
        if "llm_disabled" not in result.degraded_reason_values:
            return IncidentDrillResult(
                name="llm_degraded",
                status=DrillStatus.FAIL,
                observations=tuple(result.degraded_reason_values),
                failure_reason=(
                    "Phase 11B drill: degraded reasons must include "
                    "llm_disabled"
                ),
            )
        if fake_client.calls != 0:
            return IncidentDrillResult(
                name="llm_degraded",
                status=DrillStatus.FAIL,
                observations=(f"fake_client.calls={fake_client.calls}",),
                failure_reason=(
                    "Phase 11B drill: fake client called even though "
                    "llm_enabled=False"
                ),
            )
        return IncidentDrillResult(
            name="llm_degraded",
            status=DrillStatus.PASS,
            observations=(
                f"degraded_reasons={','.join(result.degraded_reason_values)}",
                f"fake_client_calls={fake_client.calls}",
                f"clean_results={interpreter.counters.clean_results}",
            ),
        )

    # ==================================================================
    # Internals
    # ==================================================================
    def _fresh_risk_engine(self) -> RiskEngine:
        """Build a disposable :class:`RiskEngine` so a drill cannot
        mutate the supervisor's main risk-engine state."""
        return RiskEngine(
            settings=self.settings,
            event_repo=self.event_repo,
        )

    def _fresh_reconciler(self) -> Reconciler:
        """Build a disposable :class:`Reconciler` wired to the shared
        :class:`IncidentRepository`. Each drill that walks the
        reconciler resets its latched-pause state automatically because
        a fresh instance is built per drill."""
        return Reconciler(
            event_repo=self.event_repo,
            protection_hook=self.incident_repo,
        )


__all__ = [
    "DrillStatus",
    "IncidentDrillResult",
    "IncidentDrillHarness",
]
