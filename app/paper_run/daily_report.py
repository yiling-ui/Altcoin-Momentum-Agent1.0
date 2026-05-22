"""Phase 11B - Daily Paper Report builder.

Reads the same :class:`EventRepository` the rest of the system writes
to and emits a Markdown report under
``data/reports/daily/{date}-paper-report.md``. The report is **read-only**
in the sense that the builder NEVER calls ``EventRepository.append_event``
and NEVER mutates any other database.

Phase 11B brief - the report MUST contain:

  - System uptime
  - Event count
  - Candidate-opportunity count
  - Risk-rejection count
  - State-transition count
  - Paper-trade count
  - Paper PnL
  - Capital-rebase count
  - P0 / P1 incident counts
  - Protection-mode entry count
  - Telegram message-sent count
  - Export count
  - Top reject reasons
  - Top symbols
  - Errors / degraded-status notes

Defence in depth: the rendered Markdown body is run through
:func:`app.exports.redaction.assert_no_forbidden_substrings` so a
malformed payload cannot leak a credential literal.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.core.clock import now_ms
from app.core.events import CAPITAL_EVENT_TYPES, Event, EventType
from app.database.repositories import EventRepository
from app.exports.redaction import assert_no_forbidden_substrings


# Top-N caps for "top symbols" / "top reject reasons" sections.
_TOP_REJECT_REASONS_LIMIT = 5
_TOP_SYMBOLS_LIMIT = 5


@dataclass(frozen=True)
class DailyReportSnapshot:
    """JSON-safe view of one daily report. The supervisor + acceptance
    report consume this dataclass directly; the Markdown body is
    available as :attr:`markdown`."""

    date: str
    started_at_ms: int
    finished_at_ms: int
    uptime_seconds: int
    event_count: int
    candidate_opportunity_count: int
    risk_approved_count: int
    risk_rejected_count: int
    state_transition_count: int
    paper_trade_count: int
    paper_realized_pnl: float
    paper_unrealized_pnl: float
    capital_rebase_count: int
    capital_deposit_count: int
    capital_withdrawal_count: int
    incidents_p0_count: int
    incidents_p1_count: int
    incidents_p2_count: int
    incidents_p3_count: int
    protection_mode_entered_count: int
    protection_mode_exited_count: int
    telegram_messages_sent_count: int
    telegram_send_failed_count: int
    telegram_command_rejected_count: int
    data_export_generated_count: int
    data_export_failed_count: int
    llm_interpreted_count: int
    llm_degraded_count: int
    llm_schema_rejected_count: int
    reconciliation_started_count: int
    reconciliation_resolved_count: int
    reconciliation_mismatch_count: int
    new_opens_paused: bool
    top_reject_reasons: tuple[tuple[str, int], ...]
    top_symbols: tuple[tuple[str, int], ...]
    error_notes: tuple[str, ...] = field(default_factory=tuple)
    degraded_notes: tuple[str, ...] = field(default_factory=tuple)
    safety_summary: dict[str, bool] = field(default_factory=dict)
    paper_cloud_summary: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1A - Binance public REST rate-limit governor metrics.
    rate_limit_429_count: int = 0
    rate_limit_418_count: int = 0
    retry_after_seconds_last: int = 0
    retry_after_seconds_total: int = 0
    used_weight_1m_last: int = 0
    used_weight_1m_max: int = 0
    rest_requests_total: int = 0
    rest_requests_skipped_by_budget: int = 0
    rate_limit_protection_triggered: bool = False
    rate_limit_ban: bool = False
    rate_limit_backoff_started_count: int = 0
    rate_limit_backoff_ended_count: int = 0
    ingestion_errors: int = 0
    rate_limit_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1B - WebSocket-first all-market radar metrics.
    ws_messages_received: int = 0
    ws_messages_received_by_stream: dict[str, int] = field(default_factory=dict)
    ws_reconnect_count: int = 0
    ws_staleness_ms_max: int = 0
    ws_stale_count: int = 0
    ws_connect_count: int = 0
    ws_disconnect_count: int = 0
    ws_is_stale: bool = False
    radar_candidates_seen: int = 0
    candidate_pool_size_max: int = 0
    pre_anomaly_candidates: int = 0
    liquidation_events_seen: int = 0
    radar_score_top_symbols: list[dict[str, Any]] = field(default_factory=list)
    ws_metrics: dict[str, Any] = field(default_factory=dict)
    candidate_pool_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector
    # metrics. The runner passes the WSRadarChainDriver's
    # ``adaptive_metrics_payload()`` through ``adaptive_metrics``;
    # the builder cross-checks the event-log counts of the six new
    # event types against those counters before rendering.
    market_regime_counts: dict[str, int] = field(default_factory=dict)
    candidate_stage_counts: dict[str, int] = field(default_factory=dict)
    strategy_mode_counts: dict[str, int] = field(default_factory=dict)
    opportunity_grade_counts: dict[str, int] = field(default_factory=dict)
    top_opportunity_scores: list[dict[str, Any]] = field(default_factory=list)
    label_queue_enqueued: int = 0
    observe_count: int = 0
    reject_count: int = 0
    follow_count: int = 0
    pullback_count: int = 0
    late_chase_rejected_count: int = 0
    blowoff_observed_count: int = 0
    market_regime_assessed_count: int = 0
    candidate_stage_classified_count: int = 0
    opportunity_scored_count: int = 0
    strategy_mode_selected_count: int = 0
    cluster_context_attached_count: int = 0
    adaptive_metrics: dict[str, Any] = field(default_factory=dict)
    markdown: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "started_at_ms": int(self.started_at_ms),
            "finished_at_ms": int(self.finished_at_ms),
            "uptime_seconds": int(self.uptime_seconds),
            "event_count": int(self.event_count),
            "candidate_opportunity_count": int(self.candidate_opportunity_count),
            "risk_approved_count": int(self.risk_approved_count),
            "risk_rejected_count": int(self.risk_rejected_count),
            "state_transition_count": int(self.state_transition_count),
            "paper_trade_count": int(self.paper_trade_count),
            "paper_realized_pnl": float(self.paper_realized_pnl),
            "paper_unrealized_pnl": float(self.paper_unrealized_pnl),
            "capital_rebase_count": int(self.capital_rebase_count),
            "capital_deposit_count": int(self.capital_deposit_count),
            "capital_withdrawal_count": int(self.capital_withdrawal_count),
            "incidents_p0_count": int(self.incidents_p0_count),
            "incidents_p1_count": int(self.incidents_p1_count),
            "incidents_p2_count": int(self.incidents_p2_count),
            "incidents_p3_count": int(self.incidents_p3_count),
            "protection_mode_entered_count": int(
                self.protection_mode_entered_count
            ),
            "protection_mode_exited_count": int(
                self.protection_mode_exited_count
            ),
            "telegram_messages_sent_count": int(
                self.telegram_messages_sent_count
            ),
            "telegram_send_failed_count": int(self.telegram_send_failed_count),
            "telegram_command_rejected_count": int(
                self.telegram_command_rejected_count
            ),
            "data_export_generated_count": int(
                self.data_export_generated_count
            ),
            "data_export_failed_count": int(self.data_export_failed_count),
            "llm_interpreted_count": int(self.llm_interpreted_count),
            "llm_degraded_count": int(self.llm_degraded_count),
            "llm_schema_rejected_count": int(self.llm_schema_rejected_count),
            "reconciliation_started_count": int(
                self.reconciliation_started_count
            ),
            "reconciliation_resolved_count": int(
                self.reconciliation_resolved_count
            ),
            "reconciliation_mismatch_count": int(
                self.reconciliation_mismatch_count
            ),
            "new_opens_paused": bool(self.new_opens_paused),
            "top_reject_reasons": [
                {"reason": r, "count": int(c)}
                for r, c in self.top_reject_reasons
            ],
            "top_symbols": [
                {"symbol": s, "count": int(c)} for s, c in self.top_symbols
            ],
            "error_notes": list(self.error_notes),
            "degraded_notes": list(self.degraded_notes),
            "safety_summary": dict(self.safety_summary),
            "paper_cloud_summary": dict(self.paper_cloud_summary),
            # Phase 11C.1A rate-limit metrics.
            "rate_limit_429_count": int(self.rate_limit_429_count),
            "rate_limit_418_count": int(self.rate_limit_418_count),
            "retry_after_seconds_last": int(self.retry_after_seconds_last),
            "retry_after_seconds_total": int(self.retry_after_seconds_total),
            "used_weight_1m_last": int(self.used_weight_1m_last),
            "used_weight_1m_max": int(self.used_weight_1m_max),
            "rest_requests_total": int(self.rest_requests_total),
            "rest_requests_skipped_by_budget": int(
                self.rest_requests_skipped_by_budget
            ),
            "rate_limit_protection_triggered": bool(
                self.rate_limit_protection_triggered
            ),
            "rate_limit_ban": bool(self.rate_limit_ban),
            "rate_limit_backoff_started_count": int(
                self.rate_limit_backoff_started_count
            ),
            "rate_limit_backoff_ended_count": int(
                self.rate_limit_backoff_ended_count
            ),
            "ingestion_errors": int(self.ingestion_errors),
            "rate_limit_metrics": dict(self.rate_limit_metrics),
            # Phase 11C.1B WS-first radar.
            "ws_messages_received": int(self.ws_messages_received),
            "ws_messages_received_by_stream": dict(
                self.ws_messages_received_by_stream
            ),
            "ws_reconnect_count": int(self.ws_reconnect_count),
            "ws_staleness_ms_max": int(self.ws_staleness_ms_max),
            "ws_stale_count": int(self.ws_stale_count),
            "ws_connect_count": int(self.ws_connect_count),
            "ws_disconnect_count": int(self.ws_disconnect_count),
            "ws_is_stale": bool(self.ws_is_stale),
            "radar_candidates_seen": int(self.radar_candidates_seen),
            "candidate_pool_size_max": int(self.candidate_pool_size_max),
            "pre_anomaly_candidates": int(self.pre_anomaly_candidates),
            "liquidation_events_seen": int(self.liquidation_events_seen),
            "radar_score_top_symbols": list(self.radar_score_top_symbols),
            "ws_metrics": dict(self.ws_metrics),
            "candidate_pool_metrics": dict(self.candidate_pool_metrics),
            # Phase 11C.1C-A adaptive metrics.
            "market_regime_counts": dict(self.market_regime_counts),
            "candidate_stage_counts": dict(self.candidate_stage_counts),
            "strategy_mode_counts": dict(self.strategy_mode_counts),
            "opportunity_grade_counts": dict(self.opportunity_grade_counts),
            "top_opportunity_scores": list(self.top_opportunity_scores),
            "label_queue_enqueued": int(self.label_queue_enqueued),
            "observe_count": int(self.observe_count),
            "reject_count": int(self.reject_count),
            "follow_count": int(self.follow_count),
            "pullback_count": int(self.pullback_count),
            "late_chase_rejected_count": int(self.late_chase_rejected_count),
            "blowoff_observed_count": int(self.blowoff_observed_count),
            "market_regime_assessed_count": int(
                self.market_regime_assessed_count
            ),
            "candidate_stage_classified_count": int(
                self.candidate_stage_classified_count
            ),
            "opportunity_scored_count": int(self.opportunity_scored_count),
            "strategy_mode_selected_count": int(
                self.strategy_mode_selected_count
            ),
            "cluster_context_attached_count": int(
                self.cluster_context_attached_count
            ),
            "adaptive_metrics": dict(self.adaptive_metrics),
        }


class DailyReportBuilder:
    """Builds :class:`DailyReportSnapshot` from a :class:`EventRepository`.

    The builder is stateless aside from the wired repository and
    output directory. Each :meth:`build` call queries events.db,
    aggregates the numbers, and writes one Markdown file under
    ``output_dir / filename``.
    """

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        output_dir: Path,
        filename_template: str = "{date}-paper-report.md",
    ) -> None:
        self._event_repo = event_repo
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._filename_template = filename_template

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    # ------------------------------------------------------------------
    def build(
        self,
        *,
        started_at_ms: int,
        finished_at_ms: int | None = None,
        clock_ms: int | None = None,
        safety_summary: Mapping[str, bool] | None = None,
        paper_cloud_summary: Mapping[str, Any] | None = None,
        write_to_disk: bool = True,
        error_notes: Iterable[str] = (),
        degraded_notes: Iterable[str] = (),
        rate_limit_metrics: Mapping[str, Any] | None = None,
        ingestion_errors: int | None = None,
        ws_metrics: Mapping[str, Any] | None = None,
        candidate_pool_metrics: Mapping[str, Any] | None = None,
        adaptive_metrics: Mapping[str, Any] | None = None,
    ) -> DailyReportSnapshot:
        """Build the daily report.

        ``started_at_ms`` is the Phase 11B run's first observation; the
        builder pulls every event in ``[started_at_ms, finished_at_ms]``
        from events.db so the cadence-driven cloud loop reports the
        previous 24-hour window without leakage.

        Phase 11C.1A additions:

        ``rate_limit_metrics`` carries the
        :meth:`BinancePublicRestGovernor.metrics_payload` dict so the
        builder can report exact governor counters that may not be
        fully reconstructable from events.db alone (the governor still
        emits ``RATE_LIMIT_429`` / ``RATE_LIMIT_BACKOFF_STARTED`` /
        ``RATE_LIMIT_BACKOFF_ENDED`` / ``RATE_LIMIT_418`` /
        ``RATE_LIMIT_PROTECTION_ENTERED`` events on every transition,
        and the builder cross-checks the event counts against the
        governor counters before rendering).

        ``ingestion_errors`` is the runner-side count of failed REST
        ingest attempts (e.g. transport failures that did NOT trigger
        a 429 or 418).

        Phase 11C.1C-A addition:

        ``adaptive_metrics`` carries the
        :meth:`WSRadarChainDriver.adaptive_metrics_payload` dict so the
        builder can render the new
        ``Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector``
        Markdown section. The builder cross-checks the event-log
        counts of the six new event types
        (``MARKET_REGIME_ASSESSED`` / ``CANDIDATE_STAGE_CLASSIFIED`` /
        ``OPPORTUNITY_SCORED`` / ``STRATEGY_MODE_SELECTED`` /
        ``CLUSTER_CONTEXT_ATTACHED`` / ``LABEL_QUEUE_ENQUEUED``)
        against those counters before rendering.
        """
        finished_ms = (
            finished_at_ms
            if finished_at_ms is not None
            else (clock_ms if clock_ms is not None else now_ms())
        )
        events = self._event_repo.list_events(
            since_ts=int(started_at_ms),
            until_ts=int(finished_ms),
        )
        snapshot = self._aggregate(
            events=events,
            started_at_ms=int(started_at_ms),
            finished_at_ms=int(finished_ms),
            safety_summary=safety_summary or {},
            paper_cloud_summary=paper_cloud_summary or {},
            error_notes=tuple(error_notes),
            degraded_notes=tuple(degraded_notes),
            rate_limit_metrics=dict(rate_limit_metrics or {}),
            ingestion_errors=ingestion_errors,
            ws_metrics=dict(ws_metrics or {}),
            candidate_pool_metrics=dict(candidate_pool_metrics or {}),
            adaptive_metrics=dict(adaptive_metrics or {}),
        )

        if write_to_disk:
            date_label = snapshot.date
            filename = self._filename_template.format(date=date_label)
            target = self._output_dir / filename
            self._output_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(snapshot.markdown, encoding="utf-8")
        return snapshot

    # ------------------------------------------------------------------
    def _aggregate(
        self,
        *,
        events: list[Event],
        started_at_ms: int,
        finished_at_ms: int,
        safety_summary: Mapping[str, bool],
        paper_cloud_summary: Mapping[str, Any],
        error_notes: tuple[str, ...],
        degraded_notes: tuple[str, ...],
        rate_limit_metrics: Mapping[str, Any] | None = None,
        ingestion_errors: int | None = None,
        ws_metrics: Mapping[str, Any] | None = None,
        candidate_pool_metrics: Mapping[str, Any] | None = None,
        adaptive_metrics: Mapping[str, Any] | None = None,
    ) -> DailyReportSnapshot:
        date_label = datetime.fromtimestamp(
            finished_at_ms / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")

        type_counts: Counter[str] = Counter()
        reject_reasons: Counter[str] = Counter()
        symbol_counts: Counter[str] = Counter()
        incidents_by_level: Counter[str] = Counter()
        paper_realized_pnl = 0.0
        paper_unrealized_pnl = 0.0
        paper_trade_count = 0
        candidate_opportunity_ids: set[str] = set()
        new_opens_paused = False
        local_error_notes: list[str] = []
        local_degraded_notes: list[str] = []

        for ev in events:
            type_counts[ev.event_type.value] += 1
            if ev.symbol:
                symbol_counts[str(ev.symbol)] += 1
            payload = ev.payload or {}
            if ev.event_type is EventType.RISK_REJECTED:
                for r in payload.get("reasons") or []:
                    reject_reasons[str(r)] += 1
            if ev.event_type is EventType.OPPORTUNITY_GRADED:
                opp_id = payload.get("opportunity_id")
                if opp_id:
                    candidate_opportunity_ids.add(str(opp_id))
            if ev.event_type is EventType.POSITION_CLOSED:
                paper_trade_count += 1
                try:
                    paper_realized_pnl += float(
                        payload.get("realized_pnl", 0.0) or 0.0
                    )
                except (TypeError, ValueError):
                    pass
            if ev.event_type is EventType.POSITION_UPDATED:
                try:
                    paper_unrealized_pnl = float(
                        payload.get("unrealized_pnl", paper_unrealized_pnl)
                    )
                except (TypeError, ValueError):
                    pass
            if ev.event_type is EventType.INCIDENT_OPENED:
                incidents_by_level[str(payload.get("level", "P3"))] += 1
            if ev.event_type is EventType.RECONCILIATION_RESOLVED:
                if bool(payload.get("new_opens_paused")):
                    new_opens_paused = True
                if int(payload.get("p0_count", 0) or 0) > 0:
                    local_error_notes.append(
                        f"reconciliation_p0={int(payload.get('p0_count', 0))}"
                    )
                if int(payload.get("p1_count", 0) or 0) > 0:
                    local_degraded_notes.append(
                        f"reconciliation_p1={int(payload.get('p1_count', 0))}"
                    )
            if ev.event_type is EventType.LLM_DEGRADED:
                reasons = payload.get("degraded_reasons") or payload.get(
                    "reasons"
                ) or []
                if reasons:
                    local_degraded_notes.append(
                        "llm_degraded:" + ",".join(str(r) for r in reasons)
                    )
            if ev.event_type is EventType.PROTECTION_MODE_ENTERED:
                local_error_notes.append(
                    f"protection_entered:{payload.get('reason', 'unknown')}"
                )

        capital_count = sum(
            type_counts.get(t.value, 0) for t in CAPITAL_EVENT_TYPES
        )

        # Phase 11C.1A - rate-limit metrics. The runner passes the
        # governor's metrics_payload() through ``rate_limit_metrics``.
        # Counts are double-checked against the events.db audit trail
        # so a stale governor counter cannot hide a real protection
        # event.
        gov_metrics = dict(rate_limit_metrics or {})
        rate_limit_429_count = max(
            int(gov_metrics.get("rate_limit_429_count", 0) or 0),
            int(type_counts.get(EventType.RATE_LIMIT_429.value, 0)),
        )
        rate_limit_418_count = max(
            int(gov_metrics.get("rate_limit_418_count", 0) or 0),
            int(type_counts.get(EventType.RATE_LIMIT_418.value, 0)),
        )
        backoff_started_from_events = int(
            type_counts.get(EventType.RATE_LIMIT_BACKOFF_STARTED.value, 0)
        )
        backoff_ended_from_events = int(
            type_counts.get(EventType.RATE_LIMIT_BACKOFF_ENDED.value, 0)
        )
        protection_entered_from_events = int(
            type_counts.get(
                EventType.RATE_LIMIT_PROTECTION_ENTERED.value, 0
            )
        )
        rate_limit_protection_triggered = bool(
            gov_metrics.get("rate_limit_protection_triggered", False)
        ) or protection_entered_from_events > 0
        rate_limit_ban = bool(
            gov_metrics.get("rate_limit_ban", False)
        ) or rate_limit_418_count > 0
        # If the governor never saw a 429/418 the daily report still
        # shows zero - that is the steady-state Phase 11C.1A
        # invariant: a healthy run shows zero counts and the
        # protection flag stays False.
        ingestion_errors_value = int(
            ingestion_errors
            if ingestion_errors is not None
            else int(gov_metrics.get("ingestion_errors", 0) or 0)
        )

        snapshot = DailyReportSnapshot(
            date=date_label,
            started_at_ms=int(started_at_ms),
            finished_at_ms=int(finished_at_ms),
            uptime_seconds=max(
                0, int((finished_at_ms - started_at_ms) // 1000)
            ),
            event_count=len(events),
            candidate_opportunity_count=len(candidate_opportunity_ids),
            risk_approved_count=int(
                type_counts.get(EventType.RISK_APPROVED.value, 0)
            ),
            risk_rejected_count=int(
                type_counts.get(EventType.RISK_REJECTED.value, 0)
            ),
            state_transition_count=int(
                type_counts.get(EventType.STATE_TRANSITION.value, 0)
            ),
            paper_trade_count=paper_trade_count,
            paper_realized_pnl=float(paper_realized_pnl),
            paper_unrealized_pnl=float(paper_unrealized_pnl),
            capital_rebase_count=int(
                type_counts.get(EventType.CAPITAL_REBASE.value, 0)
            ),
            capital_deposit_count=int(
                type_counts.get(EventType.CAPITAL_DEPOSIT.value, 0)
            ),
            capital_withdrawal_count=int(
                type_counts.get(EventType.CAPITAL_WITHDRAWAL.value, 0)
            ),
            incidents_p0_count=int(incidents_by_level.get("P0", 0)),
            incidents_p1_count=int(incidents_by_level.get("P1", 0)),
            incidents_p2_count=int(incidents_by_level.get("P2", 0)),
            incidents_p3_count=int(incidents_by_level.get("P3", 0)),
            protection_mode_entered_count=int(
                type_counts.get(EventType.PROTECTION_MODE_ENTERED.value, 0)
            ),
            protection_mode_exited_count=int(
                type_counts.get(EventType.PROTECTION_MODE_EXITED.value, 0)
            ),
            telegram_messages_sent_count=int(
                type_counts.get(EventType.TELEGRAM_MESSAGE_SENT.value, 0)
            ),
            telegram_send_failed_count=int(
                type_counts.get(EventType.TELEGRAM_SEND_FAILED.value, 0)
            ),
            telegram_command_rejected_count=int(
                type_counts.get(EventType.TELEGRAM_COMMAND_REJECTED.value, 0)
            ),
            data_export_generated_count=int(
                type_counts.get(EventType.DATA_EXPORT_GENERATED.value, 0)
            ),
            data_export_failed_count=int(
                type_counts.get(EventType.DATA_EXPORT_FAILED.value, 0)
            ),
            llm_interpreted_count=int(
                type_counts.get(EventType.LLM_INTERPRETED.value, 0)
            ),
            llm_degraded_count=int(
                type_counts.get(EventType.LLM_DEGRADED.value, 0)
            ),
            llm_schema_rejected_count=int(
                type_counts.get(EventType.LLM_SCHEMA_REJECTED.value, 0)
            ),
            reconciliation_started_count=int(
                type_counts.get(EventType.RECONCILIATION_STARTED.value, 0)
            ),
            reconciliation_resolved_count=int(
                type_counts.get(EventType.RECONCILIATION_RESOLVED.value, 0)
            ),
            reconciliation_mismatch_count=int(
                type_counts.get(EventType.RECONCILIATION_MISMATCH.value, 0)
            ),
            new_opens_paused=bool(new_opens_paused),
            top_reject_reasons=tuple(
                reject_reasons.most_common(_TOP_REJECT_REASONS_LIMIT)
            ),
            top_symbols=tuple(symbol_counts.most_common(_TOP_SYMBOLS_LIMIT)),
            error_notes=tuple(list(error_notes) + local_error_notes),
            degraded_notes=tuple(list(degraded_notes) + local_degraded_notes),
            safety_summary=dict(safety_summary),
            paper_cloud_summary=dict(paper_cloud_summary),
            # Phase 11C.1A rate-limit metrics.
            rate_limit_429_count=int(rate_limit_429_count),
            rate_limit_418_count=int(rate_limit_418_count),
            retry_after_seconds_last=int(
                gov_metrics.get("retry_after_seconds_last", 0) or 0
            ),
            retry_after_seconds_total=int(
                gov_metrics.get("retry_after_seconds_total", 0) or 0
            ),
            used_weight_1m_last=int(
                gov_metrics.get("used_weight_1m_last", 0) or 0
            ),
            used_weight_1m_max=int(
                gov_metrics.get("used_weight_1m_max", 0) or 0
            ),
            rest_requests_total=int(
                gov_metrics.get("rest_requests_total", 0) or 0
            ),
            rest_requests_skipped_by_budget=int(
                gov_metrics.get("rest_requests_skipped_by_budget", 0) or 0
            ),
            rate_limit_protection_triggered=bool(
                rate_limit_protection_triggered
            ),
            rate_limit_ban=bool(rate_limit_ban),
            rate_limit_backoff_started_count=int(
                max(
                    int(gov_metrics.get("backoff_started_count", 0) or 0),
                    backoff_started_from_events,
                )
            ),
            rate_limit_backoff_ended_count=int(
                max(
                    int(gov_metrics.get("backoff_ended_count", 0) or 0),
                    backoff_ended_from_events,
                )
            ),
            ingestion_errors=int(ingestion_errors_value),
            rate_limit_metrics=dict(gov_metrics),
            # Phase 11C.1B WS-first radar metrics.
            ws_messages_received=int(
                (ws_metrics or {}).get("ws_messages_received", 0) or 0
            ),
            ws_messages_received_by_stream=dict(
                (ws_metrics or {}).get(
                    "ws_messages_received_by_stream", {}
                )
                or {}
            ),
            ws_reconnect_count=int(
                max(
                    int((ws_metrics or {}).get("ws_reconnect_count", 0) or 0),
                    int(type_counts.get(EventType.PUBLIC_WS_DISCONNECTED.value, 0)),
                )
            ),
            ws_staleness_ms_max=int(
                (ws_metrics or {}).get("ws_staleness_ms_max", 0) or 0
            ),
            ws_stale_count=int(
                max(
                    int((ws_metrics or {}).get("ws_stale_count", 0) or 0),
                    int(type_counts.get(EventType.PUBLIC_WS_STALE.value, 0)),
                )
            ),
            ws_connect_count=int(
                max(
                    int((ws_metrics or {}).get("ws_connect_count", 0) or 0),
                    int(type_counts.get(EventType.PUBLIC_WS_CONNECTED.value, 0)),
                )
            ),
            ws_disconnect_count=int(
                (ws_metrics or {}).get("ws_disconnect_count", 0) or 0
            ),
            ws_is_stale=bool(
                (ws_metrics or {}).get("ws_is_stale", False)
            ),
            radar_candidates_seen=int(
                (candidate_pool_metrics or {}).get(
                    "radar_candidates_seen", 0
                )
                or 0
            ),
            candidate_pool_size_max=int(
                (candidate_pool_metrics or {}).get(
                    "candidate_pool_size_max", 0
                )
                or 0
            ),
            pre_anomaly_candidates=int(
                (candidate_pool_metrics or {}).get(
                    "candidate_pool_promoted", 0
                )
                or 0
            ),
            liquidation_events_seen=int(
                (candidate_pool_metrics or {}).get(
                    "liquidation_events_seen", 0
                )
                or 0
            ),
            radar_score_top_symbols=list(
                (candidate_pool_metrics or {}).get(
                    "candidate_pool_top_symbols", []
                )
                or []
            ),
            ws_metrics=dict(ws_metrics or {}),
            candidate_pool_metrics=dict(candidate_pool_metrics or {}),
            # Phase 11C.1C-A adaptive metrics. The values come from
            # the ``adaptive_metrics`` kwarg first; the event-log
            # counts of the six new event types are used as a
            # cross-check / fall-back so a stale runner counter
            # cannot under-report a real adaptive event.
            market_regime_counts=dict(
                (adaptive_metrics or {}).get("market_regime_counts", {})
                or {}
            ),
            candidate_stage_counts=dict(
                (adaptive_metrics or {}).get("candidate_stage_counts", {})
                or {}
            ),
            strategy_mode_counts=dict(
                (adaptive_metrics or {}).get("strategy_mode_counts", {})
                or {}
            ),
            opportunity_grade_counts=dict(
                (adaptive_metrics or {}).get("opportunity_grade_counts", {})
                or {}
            ),
            top_opportunity_scores=list(
                (adaptive_metrics or {}).get("top_opportunity_scores", [])
                or []
            ),
            label_queue_enqueued=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "label_queue_enqueued", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.LABEL_QUEUE_ENQUEUED.value, 0
                        )
                    ),
                )
            ),
            observe_count=int(
                (adaptive_metrics or {}).get("observe_count", 0) or 0
            ),
            reject_count=int(
                (adaptive_metrics or {}).get("reject_count", 0) or 0
            ),
            follow_count=int(
                (adaptive_metrics or {}).get("follow_count", 0) or 0
            ),
            pullback_count=int(
                (adaptive_metrics or {}).get("pullback_count", 0) or 0
            ),
            late_chase_rejected_count=int(
                (adaptive_metrics or {}).get(
                    "late_chase_rejected_count", 0
                )
                or 0
            ),
            blowoff_observed_count=int(
                (adaptive_metrics or {}).get("blowoff_observed_count", 0)
                or 0
            ),
            market_regime_assessed_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "market_regime_assessed_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.MARKET_REGIME_ASSESSED.value, 0
                        )
                    ),
                )
            ),
            candidate_stage_classified_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "candidate_stage_classified_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.CANDIDATE_STAGE_CLASSIFIED.value, 0
                        )
                    ),
                )
            ),
            opportunity_scored_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "opportunity_scored_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.OPPORTUNITY_SCORED.value, 0
                        )
                    ),
                )
            ),
            strategy_mode_selected_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "strategy_mode_selected_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_MODE_SELECTED.value, 0
                        )
                    ),
                )
            ),
            cluster_context_attached_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "cluster_context_attached_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.CLUSTER_CONTEXT_ATTACHED.value, 0
                        )
                    ),
                )
            ),
            adaptive_metrics=dict(adaptive_metrics or {}),
        )
        # Build Markdown last so we can embed the snapshot itself.
        markdown = self._render_markdown(
            snapshot=snapshot, capital_count=capital_count
        )
        # Defence-in-depth: refuse to emit a report that contains a
        # forbidden literal.
        assert_no_forbidden_substrings(markdown)
        return _replace_markdown(snapshot, markdown)

    # ------------------------------------------------------------------
    def _render_markdown(
        self,
        *,
        snapshot: DailyReportSnapshot,
        capital_count: int,
    ) -> str:
        """Render the daily report Markdown body."""
        safety_lines = "\n".join(
            f"- `{k}` = `{v}`"
            for k, v in sorted(snapshot.safety_summary.items())
        ) or "- (no safety summary supplied)"

        cloud_lines = "\n".join(
            f"- `{k}` = `{json.dumps(v, separators=(',', ':'), default=str)}`"
            for k, v in sorted(snapshot.paper_cloud_summary.items())
        ) or "- (no paper-cloud summary supplied)"

        top_reject = "\n".join(
            f"- `{r}` x {c}" for r, c in snapshot.top_reject_reasons
        ) or "- (no risk rejections in this window)"

        top_symbols = "\n".join(
            f"- `{s}` x {c}" for s, c in snapshot.top_symbols
        ) or "- (no symbol activity in this window)"

        error_notes = "\n".join(
            f"- `{n}`" for n in snapshot.error_notes
        ) or "- (no error notes in this window)"

        degraded_notes = "\n".join(
            f"- `{n}`" for n in snapshot.degraded_notes
        ) or "- (no degraded notes in this window)"

        rate_limit_block = (
            f"- HTTP 429 count: **{snapshot.rate_limit_429_count}**\n"
            f"- HTTP 418 count: **{snapshot.rate_limit_418_count}**\n"
            f"- Retry-After last (seconds): "
            f"**{snapshot.retry_after_seconds_last}**\n"
            f"- Retry-After total (seconds): "
            f"**{snapshot.retry_after_seconds_total}**\n"
            f"- X-MBX-USED-WEIGHT-1M last: "
            f"**{snapshot.used_weight_1m_last}**\n"
            f"- X-MBX-USED-WEIGHT-1M max: "
            f"**{snapshot.used_weight_1m_max}**\n"
            f"- REST requests total: **{snapshot.rest_requests_total}**\n"
            f"- REST requests skipped by budget: "
            f"**{snapshot.rest_requests_skipped_by_budget}**\n"
            f"- Backoff windows started: "
            f"**{snapshot.rate_limit_backoff_started_count}**\n"
            f"- Backoff windows ended: "
            f"**{snapshot.rate_limit_backoff_ended_count}**\n"
            f"- Rate-limit protection triggered: "
            f"**{snapshot.rate_limit_protection_triggered}**\n"
            f"- Rate-limit IP ban observed: "
            f"**{snapshot.rate_limit_ban}**\n"
            f"- Ingestion errors (transport): "
            f"**{snapshot.ingestion_errors}**\n"
        )

        ws_top_lines = "\n".join(
            f"- `{row.get('symbol', '?')}` score="
            f"{float(row.get('radar_score', 0.0)):.2f} "
            f"state={row.get('state', '?')}"
            for row in (snapshot.radar_score_top_symbols or [])[:10]
        ) or "- (no radar candidates in this window)"

        ws_messages_by_stream_lines = "\n".join(
            f"- `{stream}` x {count}"
            for stream, count in sorted(
                snapshot.ws_messages_received_by_stream.items()
            )
        ) or "- (no WS messages observed)"

        ws_block = (
            f"- WS messages received: "
            f"**{snapshot.ws_messages_received}**\n"
            f"- WS reconnect count: "
            f"**{snapshot.ws_reconnect_count}**\n"
            f"- WS staleness (ms) max: "
            f"**{snapshot.ws_staleness_ms_max}**\n"
            f"- WS stale event count: "
            f"**{snapshot.ws_stale_count}**\n"
            f"- WS connect count: "
            f"**{snapshot.ws_connect_count}**\n"
            f"- WS disconnect count: "
            f"**{snapshot.ws_disconnect_count}**\n"
            f"- WS currently stale: **{snapshot.ws_is_stale}**\n"
            f"- Radar candidates seen: "
            f"**{snapshot.radar_candidates_seen}**\n"
            f"- Candidate pool size max: "
            f"**{snapshot.candidate_pool_size_max}**\n"
            f"- Pre-anomaly candidates promoted: "
            f"**{snapshot.pre_anomaly_candidates}**\n"
            f"- Liquidation events seen: "
            f"**{snapshot.liquidation_events_seen}**\n"
        )

        # Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector
        # Markdown block. Every value is read straight off the
        # snapshot so a stale runner counter cannot under-report a
        # real adaptive event (the snapshot's
        # ``..._count`` fields take ``max`` of the runner counter and
        # the events.db count).
        def _kv_lines(d: dict) -> str:
            if not d:
                return "- (no entries in this window)"
            return "\n".join(
                f"- `{k}` x {int(v)}" for k, v in sorted(
                    d.items(), key=lambda r: (-int(r[1]), str(r[0]))
                )
            )

        market_regime_lines = _kv_lines(snapshot.market_regime_counts)
        candidate_stage_lines = _kv_lines(snapshot.candidate_stage_counts)
        strategy_mode_lines = _kv_lines(snapshot.strategy_mode_counts)
        opportunity_grade_lines = _kv_lines(snapshot.opportunity_grade_counts)
        if snapshot.top_opportunity_scores:
            top_score_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"score={float(row.get('score', 0.0)):.2f} "
                f"grade={row.get('grade', '?')} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.top_opportunity_scores[:10]
            )
        else:
            top_score_lines = "- (no opportunity scores in this window)"

        adaptive_block = (
            f"- MARKET_REGIME_ASSESSED count: "
            f"**{snapshot.market_regime_assessed_count}**\n"
            f"- CANDIDATE_STAGE_CLASSIFIED count: "
            f"**{snapshot.candidate_stage_classified_count}**\n"
            f"- OPPORTUNITY_SCORED count: "
            f"**{snapshot.opportunity_scored_count}**\n"
            f"- STRATEGY_MODE_SELECTED count: "
            f"**{snapshot.strategy_mode_selected_count}**\n"
            f"- CLUSTER_CONTEXT_ATTACHED count: "
            f"**{snapshot.cluster_context_attached_count}**\n"
            f"- LABEL_QUEUE_ENQUEUED count: "
            f"**{snapshot.label_queue_enqueued}**\n"
            f"- Strategy modes: follow="
            f"{snapshot.follow_count} pullback="
            f"{snapshot.pullback_count} observe="
            f"{snapshot.observe_count} reject="
            f"{snapshot.reject_count}\n"
            f"- Late-chase rejected: "
            f"**{snapshot.late_chase_rejected_count}**\n"
            f"- Blowoff observed: "
            f"**{snapshot.blowoff_observed_count}**\n"
        )

        body = (
            f"# AMA-RT Phase 11B - Daily Paper Report\n\n"
            f"- **Date (UTC):** {snapshot.date}\n"
            f"- **Window:** {snapshot.started_at_ms} ms -> "
            f"{snapshot.finished_at_ms} ms (uptime "
            f"{snapshot.uptime_seconds}s)\n"
            f"- **Trading mode:** paper (Phase 1 safety lock in force)\n"
            f"- **New opens paused (latest reconciliation):** "
            f"{snapshot.new_opens_paused}\n\n"
            f"## Phase 1 safety summary\n{safety_lines}\n\n"
            f"## Paper-cloud configuration\n{cloud_lines}\n\n"
            f"## Counters\n"
            f"- Total events: **{snapshot.event_count}**\n"
            f"- Candidate opportunities: **"
            f"{snapshot.candidate_opportunity_count}**\n"
            f"- Risk approved: **{snapshot.risk_approved_count}**\n"
            f"- Risk rejected: **{snapshot.risk_rejected_count}**\n"
            f"- State transitions: **{snapshot.state_transition_count}**\n"
            f"- Paper trades closed: **{snapshot.paper_trade_count}**\n"
            f"- Paper realized PnL: **{snapshot.paper_realized_pnl:.4f}**\n"
            f"- Paper unrealized PnL: "
            f"**{snapshot.paper_unrealized_pnl:.4f}**\n"
            f"- Capital events (deposit/withdrawal/harvest/rebase/budget): "
            f"**{capital_count}**\n"
            f"- Capital rebases: **{snapshot.capital_rebase_count}**\n"
            f"- Capital deposits: **{snapshot.capital_deposit_count}**\n"
            f"- Capital withdrawals: **{snapshot.capital_withdrawal_count}**\n"
            f"- Reconciliations: started="
            f"{snapshot.reconciliation_started_count} resolved="
            f"{snapshot.reconciliation_resolved_count} mismatches="
            f"{snapshot.reconciliation_mismatch_count}\n"
            f"- Incidents: P0={snapshot.incidents_p0_count} "
            f"P1={snapshot.incidents_p1_count} "
            f"P2={snapshot.incidents_p2_count} "
            f"P3={snapshot.incidents_p3_count}\n"
            f"- Protection mode entered: "
            f"**{snapshot.protection_mode_entered_count}** "
            f"(exited: {snapshot.protection_mode_exited_count})\n"
            f"- Telegram messages sent: "
            f"**{snapshot.telegram_messages_sent_count}** "
            f"(failed: {snapshot.telegram_send_failed_count}, "
            f"commands rejected: {snapshot.telegram_command_rejected_count})\n"
            f"- Data exports generated: "
            f"**{snapshot.data_export_generated_count}** "
            f"(failed: {snapshot.data_export_failed_count})\n"
            f"- LLM events: interpreted={snapshot.llm_interpreted_count} "
            f"degraded={snapshot.llm_degraded_count} "
            f"schema_rejected={snapshot.llm_schema_rejected_count}\n\n"
            f"## Phase 11C.1A rate-limit governor\n{rate_limit_block}\n"
            f"## Phase 11C.1B WebSocket all-market radar\n{ws_block}\n"
            f"### WS messages by stream\n{ws_messages_by_stream_lines}\n\n"
            f"### Radar score top symbols\n{ws_top_lines}\n\n"
            f"## Phase 11C.1C-A Adaptive Candidate Regime "
            f"& Strategy Selector\n"
            f"_Adaptive sub-blocks are paper / virtual only. "
            f"Strategy modes do NOT authorise real orders; the Risk "
            f"Engine remains the single trade-decision gate._\n\n"
            f"{adaptive_block}\n"
            f"### Market regime counts\n{market_regime_lines}\n\n"
            f"### Candidate stage counts\n{candidate_stage_lines}\n\n"
            f"### Strategy mode counts\n{strategy_mode_lines}\n\n"
            f"### Opportunity grade counts\n{opportunity_grade_lines}\n\n"
            f"### Top opportunity scores\n{top_score_lines}\n\n"
            f"## Top risk-rejection reasons\n{top_reject}\n\n"
            f"## Top symbols by event volume\n{top_symbols}\n\n"
            f"## Error notes\n{error_notes}\n\n"
            f"## Degraded notes\n{degraded_notes}\n\n"
            f"---\n"
            f"_Phase 11B paper-mode cloud run. No live trading. "
            f"No real exchange order. No credential is read by this "
            f"report._\n"
        )
        return body


def _replace_markdown(
    snapshot: DailyReportSnapshot, markdown: str
) -> DailyReportSnapshot:
    """Return a copy of ``snapshot`` with ``markdown`` swapped in.

    :class:`DailyReportSnapshot` is frozen so we use ``dataclasses.replace``.
    """
    from dataclasses import replace

    return replace(snapshot, markdown=markdown)


__all__ = [
    "DailyReportBuilder",
    "DailyReportSnapshot",
]
