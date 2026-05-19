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
    ) -> DailyReportSnapshot:
        """Build the daily report.

        ``started_at_ms`` is the Phase 11B run's first observation; the
        builder pulls every event in ``[started_at_ms, finished_at_ms]``
        from events.db so the cadence-driven cloud loop reports the
        previous 24-hour window without leakage.
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
