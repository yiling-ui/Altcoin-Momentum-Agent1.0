"""Phase 8.5 - Test Data Export summary report.

Generates ``summary_report.md`` containing the Issue-mandated
sections:

    - Time range
    - Total event count
    - Opportunity count
    - Risk-rejected count
    - State-transition count
    - Capital Rebase count
    - Profit Harvest count
    - Paper PnL / mock PnL (if available)
    - Top reject reasons
    - Top symbols by event count
    - Whether incidents / degraded / protection_mode events exist

Phase 8.5 boundary
------------------

The summary builder is a pure function. It walks already-loaded
events; it never re-queries the database or calls any external
service. Output is plain markdown so the file is review-friendly
inside a zip.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from app.core.events import CAPITAL_EVENT_TYPES, Event, EventType
from app.exports.manifest import ExportManifest
from app.learning.context import LEARNING_READY_KEY


def _fmt_ts(ts_ms: int) -> str:
    if ts_ms <= 0:
        return "-"
    try:
        return (
            datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            .strftime("%Y-%m-%d %H:%M:%SZ")
        )
    except (OverflowError, OSError, ValueError):
        return f"ts={ts_ms}"


def _top_reject_reasons(events: Iterable[Event], limit: int = 5) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for ev in events:
        if ev.event_type is not EventType.RISK_REJECTED:
            continue
        for reason in ev.payload.get("reasons", []) or []:
            counter[str(reason)] += 1
    return counter.most_common(limit)


def _top_symbols(events: Iterable[Event], limit: int = 10) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for ev in events:
        if ev.symbol:
            counter[ev.symbol] += 1
    return counter.most_common(limit)


def _has_incident_or_degraded(events: Iterable[Event]) -> dict[str, bool]:
    flags = {
        "incidents_present": False,
        "data_unreliable_present": False,
        "protection_mode_present": False,
        "exchange_disconnected_present": False,
    }
    for ev in events:
        if ev.event_type is EventType.INCIDENT_OPENED:
            flags["incidents_present"] = True
        elif ev.event_type is EventType.DATA_UNRELIABLE:
            flags["data_unreliable_present"] = True
        elif ev.event_type is EventType.PROTECTION_MODE_ENTERED:
            flags["protection_mode_present"] = True
        elif ev.event_type is EventType.EXCHANGE_DISCONNECTED:
            flags["exchange_disconnected_present"] = True
    return flags


def _paper_pnl(events: Iterable[Event]) -> float | None:
    """Best-effort paper-mode PnL extraction.

    Phase 8.5 prefers the Capital Flow Engine's
    ``net_trading_pnl`` carried by the most recent
    ``CAPITAL_REBASE`` event. When no rebase event exists we return
    ``None`` rather than guessing.
    """
    last_pnl: float | None = None
    last_ts = -1
    for ev in events:
        if ev.event_type is not EventType.CAPITAL_REBASE:
            continue
        ts = ev.timestamp or 0
        if ts < last_ts:
            continue
        pnl = ev.payload.get("net_trading_pnl")
        if pnl is None:
            continue
        try:
            last_pnl = float(pnl)
        except (TypeError, ValueError):
            continue
        last_ts = ts
    return last_pnl


def _opportunity_ids(events: Iterable[Event]) -> set[str]:
    ids: set[str] = set()
    for ev in events:
        learn = ev.payload.get(LEARNING_READY_KEY)
        if not isinstance(learn, dict):
            continue
        opp = learn.get("opportunity")
        if isinstance(opp, dict) and opp.get("opportunity_id"):
            ids.add(str(opp["opportunity_id"]))
        risk = learn.get("risk_decision")
        if isinstance(risk, dict) and risk.get("opportunity_id"):
            ids.add(str(risk["opportunity_id"]))
    return ids


def build_summary_report(
    *,
    events: list[Event],
    manifest: ExportManifest,
) -> str:
    """Return the markdown text of ``summary_report.md``.

    The report intentionally avoids printing raw event payloads -
    those live in the per-type ``.jsonl`` files so the zip stays
    small and human-readable summaries don't leak large dumps.
    """
    rebase_count = sum(
        1 for ev in events if ev.event_type is EventType.CAPITAL_REBASE
    )
    profit_harvest_count = sum(
        1 for ev in events if ev.event_type is EventType.PROFIT_HARVEST
    )
    capital_count = sum(1 for ev in events if ev.event_type in CAPITAL_EVENT_TYPES)
    state_transition_count = sum(
        1 for ev in events if ev.event_type is EventType.STATE_TRANSITION
    )
    rejected = sum(1 for ev in events if ev.event_type is EventType.RISK_REJECTED)
    approved = sum(1 for ev in events if ev.event_type is EventType.RISK_APPROVED)
    pnl = _paper_pnl(events)
    pnl_text = f"{pnl:.4f} USDT" if pnl is not None else "n/a"
    incident_flags = _has_incident_or_degraded(events)
    top_reasons = _top_reject_reasons(events)
    top_symbols = _top_symbols(events)
    opportunity_ids = _opportunity_ids(events)

    lines: list[str] = []
    lines.append(f"# AMA-RT Test Data Export Summary")
    lines.append("")
    lines.append(f"- Export ID: `{manifest.export_id}`")
    lines.append(f"- Generated at: `{_fmt_ts(manifest.generated_at)}`")
    lines.append(f"- Trading mode: `{manifest.trading_mode}`")
    lines.append(f"- App version: `{manifest.app_version}`")
    lines.append(f"- Type filter: `{manifest.type_filter}`")
    lines.append(f"- Redaction applied: `{manifest.redaction_applied}`")
    lines.append("")
    lines.append("## Time range")
    lines.append("")
    lines.append(
        f"- Start: `{_fmt_ts(manifest.time_range_start)}` "
        f"(ts_ms={manifest.time_range_start})"
    )
    lines.append(
        f"- End:   `{_fmt_ts(manifest.time_range_end)}` "
        f"(ts_ms={manifest.time_range_end})"
    )
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Total events: **{len(events)}**")
    lines.append(f"- Opportunities (learning-ready): **{len(opportunity_ids)}**")
    lines.append(f"- Risk approved: **{approved}**")
    lines.append(f"- Risk rejected: **{rejected}**")
    lines.append(f"- State transitions: **{state_transition_count}**")
    lines.append(f"- Capital events (all): **{capital_count}**")
    lines.append(f"- Capital Rebase: **{rebase_count}**")
    lines.append(f"- Profit Harvest: **{profit_harvest_count}**")
    lines.append(f"- Paper PnL / mock PnL: **{pnl_text}**")
    lines.append("")
    lines.append("## Top reject reasons")
    lines.append("")
    if top_reasons:
        for reason, count in top_reasons:
            lines.append(f"- `{reason}` x {count}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Top symbols by event count")
    lines.append("")
    if top_symbols:
        for symbol, count in top_symbols:
            lines.append(f"- `{symbol}` x {count}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Incidents / degraded / protection mode")
    lines.append("")
    lines.append(
        f"- INCIDENT_OPENED present: **{incident_flags['incidents_present']}**"
    )
    lines.append(
        f"- DATA_UNRELIABLE present: **{incident_flags['data_unreliable_present']}**"
    )
    lines.append(
        f"- PROTECTION_MODE_ENTERED present: "
        f"**{incident_flags['protection_mode_present']}**"
    )
    lines.append(
        f"- EXCHANGE_DISCONNECTED present: "
        f"**{incident_flags['exchange_disconnected_present']}**"
    )
    lines.append("")
    lines.append("## Safety lock")
    lines.append("")
    safety = manifest.safety_summary or {}
    if safety:
        for key in sorted(safety.keys()):
            lines.append(f"- `{key}` = `{safety[key]}`")
    else:
        lines.append("- (no safety summary recorded)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "_This summary is generated by Phase 8.5 TestDataExportService. "
        "All sensitive fields have been redacted before export. The "
        "system is paper-mode-only; no live trading occurred during "
        "the export window._"
    )
    lines.append("")
    return "\n".join(lines)


def collect_summary_stats(events: list[Event]) -> dict[str, Any]:
    """Lightweight stats helper used by the export service to fill
    counts on the manifest. Exposed publicly so tests can call it
    directly."""
    return {
        "event_count": len(events),
        "opportunity_count": len(_opportunity_ids(events)),
        "risk_approved_count": sum(
            1 for ev in events if ev.event_type is EventType.RISK_APPROVED
        ),
        "risk_rejected_count": sum(
            1 for ev in events if ev.event_type is EventType.RISK_REJECTED
        ),
        "state_transition_count": sum(
            1 for ev in events if ev.event_type is EventType.STATE_TRANSITION
        ),
        "capital_event_count": sum(
            1 for ev in events if ev.event_type in CAPITAL_EVENT_TYPES
        ),
        "incident_count": sum(
            1 for ev in events if ev.event_type is EventType.INCIDENT_OPENED
        ),
    }
