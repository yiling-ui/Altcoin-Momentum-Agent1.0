"""Phase 8.5 - Test Data Export Service.

Reads from a Phase-2 :class:`EventRepository` and writes a redacted
``.zip`` bundle to ``data/reports/exports/`` containing:

    manifest.json
    summary_report.md
    events.jsonl
    opportunities.jsonl
    signal_snapshots.jsonl
    risk_decisions.jsonl
    state_transitions.jsonl
    capital_events.jsonl
    virtual_trade_plans.jsonl

Every output stream is **redacted** (see :mod:`app.exports.redaction`)
and ``manifest.json.redaction_applied`` is hard-coded to ``True``.

Time ranges supported (Issue contract):

    today    -> [00:00 UTC today, now]
    24h      -> [now - 24h, now]
    7d       -> [now - 7d,  now]
    range    -> explicit start_ms, end_ms

Type filters supported:

    all              every output file
    events           events.jsonl + manifest + summary
    opportunities    opportunities.jsonl + manifest + summary
    rejections       risk_decisions.jsonl + manifest + summary (rejected only)
    capital          capital_events.jsonl + manifest + summary
    state            state_transitions.jsonl + manifest + summary
    learning         opportunities + signal_snapshots + virtual_trade_plans
                     + risk_decisions + manifest + summary

Phase 8.5 boundary
------------------

The service:

  - Never opens a socket.
  - Never imports an exchange / Telegram / LLM library.
  - Never reads ``os.environ`` for credentials.
  - Never mutates events.db (read-only access).
  - Never bypasses the redaction step.
  - Refuses to grow above ``max_zip_bytes`` and signals the caller to
    request a smaller window instead. The Issue contract reserves
    fragmentation / Telegram-side splitting for Issue #10.
"""

from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.core.clock import now_ms
from app.core.events import CAPITAL_EVENT_TYPES, Event, EventType
from app.database.repositories import EventRepository
from app.exports.manifest import ExportManifest
from app.exports.redaction import (
    REDACTED,
    assert_no_forbidden_substrings,
    redact,
)
from app.exports.summary import build_summary_report, collect_summary_stats
from app.learning.context import LEARNING_READY_KEY


# Default ceiling. The Issue contract reserves fragmentation /
# splitting for Telegram (Issue #10); Phase 8.5 just refuses to grow
# beyond this size and asks the caller to narrow the window.
DEFAULT_MAX_ZIP_BYTES = 50 * 1024 * 1024  # 50 MiB

# Canonical type-filter set (Issue contract).
ALLOWED_TYPE_FILTERS: frozenset[str] = frozenset(
    {"all", "events", "opportunities", "rejections", "capital", "state", "learning"}
)

# Canonical range labels (Issue contract).
ALLOWED_RANGE_LABELS: frozenset[str] = frozenset({"today", "24h", "7d", "range"})


class ExportError(Exception):
    """Raised when an export request cannot be satisfied (e.g. zip
    size cap exceeded, invalid range, invalid type filter)."""


@dataclass
class ExportResult:
    """Outcome of an export call."""

    zip_path: Path
    manifest: ExportManifest
    summary_md: str
    files: list[dict[str, object]] = field(default_factory=list)
    bytes_written: int = 0


def resolve_time_range(
    *,
    range_label: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    clock_ms: int | None = None,
) -> tuple[int, int]:
    """Return ``(start_ms, end_ms)`` per the Issue contract."""
    if range_label not in ALLOWED_RANGE_LABELS:
        raise ExportError(
            f"unsupported range_label={range_label!r}; "
            f"must be one of {sorted(ALLOWED_RANGE_LABELS)}"
        )
    now = clock_ms if clock_ms is not None else now_ms()
    if range_label == "today":
        # Midnight UTC today.
        utc = datetime.fromtimestamp(now / 1000.0, tz=timezone.utc)
        midnight = utc.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(midnight.timestamp() * 1000), int(now)
    if range_label == "24h":
        return int(now - 24 * 60 * 60 * 1000), int(now)
    if range_label == "7d":
        return int(now - 7 * 24 * 60 * 60 * 1000), int(now)
    # range
    if start_ms is None or end_ms is None:
        raise ExportError(
            "range_label='range' requires explicit start_ms and end_ms"
        )
    if int(end_ms) < int(start_ms):
        raise ExportError(
            f"range end ({end_ms}) must be >= range start ({start_ms})"
        )
    return int(start_ms), int(end_ms)


def parse_iso_date(value: str) -> int:
    """Parse an ISO date / datetime string to ms-UTC.

    Accepts ``YYYY-MM-DD`` (interpreted as UTC midnight) and
    ``YYYY-MM-DDTHH:MM:SS`` (UTC). Used by the CLI when the operator
    supplies ``--start`` / ``--end``.
    """
    s = str(value).strip()
    if not s:
        raise ExportError("date string is empty")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        # Allow trailing Z.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as exc:
            raise ExportError(f"unparseable date string: {value!r}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def _event_to_redacted_dict(event: Event) -> dict[str, object]:
    """Convert an ``Event`` to a redacted JSON-safe dict."""
    raw = event.to_dict()
    return redact(raw)


def _is_opportunity_event(event: Event) -> bool:
    learn = event.payload.get(LEARNING_READY_KEY) if event.payload else None
    if not isinstance(learn, dict):
        return False
    opp = learn.get("opportunity")
    return isinstance(opp, dict) and bool(opp.get("opportunity_id"))


def _is_signal_snapshot_event(event: Event) -> bool:
    learn = event.payload.get(LEARNING_READY_KEY) if event.payload else None
    if not isinstance(learn, dict):
        return False
    return isinstance(learn.get("signal_snapshot"), dict)


def _is_virtual_trade_plan_event(event: Event) -> bool:
    learn = event.payload.get(LEARNING_READY_KEY) if event.payload else None
    if not isinstance(learn, dict):
        return False
    return isinstance(learn.get("virtual_trade_plan"), dict)


def _is_risk_decision_event(event: Event) -> bool:
    return event.event_type in (EventType.RISK_APPROVED, EventType.RISK_REJECTED)


class TestDataExportService:
    """Phase 8.5 Test Data Export Service.

    Stateless aside from the supplied :class:`EventRepository` and
    target output directory. Each ``export()`` call produces a fresh
    zip on disk.
    """

    # Tell pytest NOT to collect this class as a test case (its name
    # starts with ``Test`` because it is the project-facing name; it
    # does not contain test methods).
    __test__ = False

    SOURCE_MODULE = "exports.test_data"

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        trading_mode: str = "paper",
        app_version: str | None = None,
        output_dir: Path,
        max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
    ) -> None:
        self._event_repo = event_repo
        self._trading_mode = trading_mode
        # Late-import the version label so pytest collection does not
        # fail if the package layout changes.
        if app_version is None:
            from app import __version__ as v
            app_version = v
        self._app_version = app_version
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        if max_zip_bytes <= 0:
            raise ExportError(f"max_zip_bytes must be > 0; got {max_zip_bytes}")
        self._max_zip_bytes = int(max_zip_bytes)

    # ------------------------------------------------------------------
    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def max_zip_bytes(self) -> int:
        return self._max_zip_bytes

    @property
    def trading_mode(self) -> str:
        return self._trading_mode

    @property
    def app_version(self) -> str:
        return self._app_version

    # ------------------------------------------------------------------
    def export(
        self,
        *,
        range_label: str = "24h",
        start_ms: int | None = None,
        end_ms: int | None = None,
        type_filter: str = "all",
        clock_ms: int | None = None,
        zip_filename: str | None = None,
    ) -> ExportResult:
        """Generate a redacted zip and return the path.

        Empty result sets are allowed - the bundle is still created
        with manifest + summary so the caller knows the request was
        served.
        """
        if type_filter not in ALLOWED_TYPE_FILTERS:
            raise ExportError(
                f"unsupported type_filter={type_filter!r}; "
                f"must be one of {sorted(ALLOWED_TYPE_FILTERS)}"
            )
        ts_start, ts_end = resolve_time_range(
            range_label=range_label,
            start_ms=start_ms,
            end_ms=end_ms,
            clock_ms=clock_ms,
        )

        events = self._event_repo.list_events(
            since_ts=ts_start, until_ts=ts_end
        )

        bundle = self._build_bundle(
            events=events,
            ts_start=ts_start,
            ts_end=ts_end,
            type_filter=type_filter,
            clock_ms=clock_ms,
        )

        # Resolve zip path. Filename includes the export_id so two
        # exports created in the same millisecond don't collide.
        ts = clock_ms if clock_ms is not None else now_ms()
        if zip_filename is None:
            zip_filename = (
                f"ama_rt_test_data_{ts}_{bundle['manifest'].export_id[:8]}.zip"
            )
        zip_path = self._output_dir / zip_filename

        # Materialise zip in memory so we can reject when it would
        # exceed the cap before writing to disk.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, content in bundle["files"]:
                zf.writestr(name, content)

        size = buf.tell()
        if size > self._max_zip_bytes:
            raise ExportError(
                f"export bundle ({size} bytes) exceeds max_zip_bytes "
                f"({self._max_zip_bytes}). Issue contract: narrow the "
                f"time range or the type filter; Telegram fragmentation "
                f"is a separate Issue #10 work item."
            )

        with zip_path.open("wb") as fh:
            fh.write(buf.getvalue())

        manifest: ExportManifest = bundle["manifest"]
        return ExportResult(
            zip_path=zip_path,
            manifest=manifest,
            summary_md=bundle["summary_md"],
            files=manifest.files,
            bytes_written=size,
        )

    # ------------------------------------------------------------------
    def _build_bundle(
        self,
        *,
        events: list[Event],
        ts_start: int,
        ts_end: int,
        type_filter: str,
        clock_ms: int | None,
    ) -> dict[str, object]:
        """Assemble all files for the zip + the manifest. Returns:

            {"manifest": ExportManifest,
             "summary_md": str,
             "files": list[(name, content)]}
        """
        # Group / serialise.
        events_jsonl = self._serialise_events(events)
        opportunities_jsonl, opportunity_count = self._serialise_filtered(
            events, _is_opportunity_event
        )
        signal_snapshots_jsonl, signal_count = self._serialise_filtered(
            events, _is_signal_snapshot_event
        )
        virtual_plans_jsonl, vtp_count = self._serialise_filtered(
            events, _is_virtual_trade_plan_event
        )
        if type_filter == "rejections":
            rejected_only = [
                ev for ev in events if ev.event_type is EventType.RISK_REJECTED
            ]
            risk_decisions_jsonl, _ = self._serialise_filtered(
                rejected_only, lambda _ev: True
            )
        else:
            risk_decisions_jsonl, _ = self._serialise_filtered(
                events, _is_risk_decision_event
            )
        state_jsonl, _ = self._serialise_filtered(
            events, lambda ev: ev.event_type is EventType.STATE_TRANSITION
        )
        capital_jsonl, _ = self._serialise_filtered(
            events, lambda ev: ev.event_type in CAPITAL_EVENT_TYPES
        )

        # Choose what goes into the bundle for each type_filter.
        files_named: OrderedDict[str, str] = OrderedDict()
        if type_filter == "all":
            files_named["events.jsonl"] = events_jsonl
            files_named["opportunities.jsonl"] = opportunities_jsonl
            files_named["signal_snapshots.jsonl"] = signal_snapshots_jsonl
            files_named["risk_decisions.jsonl"] = risk_decisions_jsonl
            files_named["state_transitions.jsonl"] = state_jsonl
            files_named["capital_events.jsonl"] = capital_jsonl
            files_named["virtual_trade_plans.jsonl"] = virtual_plans_jsonl
        elif type_filter == "events":
            files_named["events.jsonl"] = events_jsonl
        elif type_filter == "opportunities":
            files_named["opportunities.jsonl"] = opportunities_jsonl
        elif type_filter == "rejections":
            files_named["risk_decisions.jsonl"] = risk_decisions_jsonl
        elif type_filter == "capital":
            files_named["capital_events.jsonl"] = capital_jsonl
        elif type_filter == "state":
            files_named["state_transitions.jsonl"] = state_jsonl
        elif type_filter == "learning":
            files_named["opportunities.jsonl"] = opportunities_jsonl
            files_named["signal_snapshots.jsonl"] = signal_snapshots_jsonl
            files_named["virtual_trade_plans.jsonl"] = virtual_plans_jsonl
            files_named["risk_decisions.jsonl"] = risk_decisions_jsonl
        else:  # pragma: no cover - already validated upstream
            raise ExportError(f"unhandled type_filter={type_filter!r}")

        # Stats for the manifest header.
        stats = collect_summary_stats(events)
        # Build the manifest with per-file sizes / row counts.
        files_meta: list[dict[str, object]] = []
        for name, content in files_named.items():
            files_meta.append(
                {
                    "name": name,
                    "row_count": (
                        sum(1 for line in content.splitlines() if line.strip())
                    ),
                    "byte_size": len(content.encode("utf-8")),
                }
            )

        export_id = f"export_{uuid.uuid4().hex}"
        generated_at = clock_ms if clock_ms is not None else now_ms()
        manifest = ExportManifest(
            export_id=export_id,
            generated_at=int(generated_at),
            time_range_start=int(ts_start),
            time_range_end=int(ts_end),
            trading_mode=self._trading_mode,
            app_version=self._app_version,
            event_count=stats["event_count"],
            opportunity_count=opportunity_count,
            risk_rejected_count=stats["risk_rejected_count"],
            risk_approved_count=stats["risk_approved_count"],
            state_transition_count=stats["state_transition_count"],
            capital_event_count=stats["capital_event_count"],
            virtual_trade_plan_count=vtp_count,
            signal_snapshot_count=signal_count,
            incident_count=stats["incident_count"],
            type_filter=type_filter,
            redaction_applied=True,
            files=files_meta,
            safety_summary=self._safety_summary(),
        )

        summary_md = build_summary_report(events=events, manifest=manifest)
        # Defence-in-depth: refuse to ship a bundle whose summary or
        # manifest contains a forbidden literal. The redaction layer
        # should already have removed any such substrings; if a future
        # bug surfaces one, this gate fails the export loudly.
        manifest_pretty = manifest.to_pretty_json()
        assert_no_forbidden_substrings(manifest_pretty)
        assert_no_forbidden_substrings(summary_md)
        for fname, content in files_named.items():
            assert_no_forbidden_substrings(
                content, extra=("/.env", "\\.env")
            )

        all_files: list[tuple[str, str]] = [
            ("manifest.json", manifest_pretty),
            ("summary_report.md", summary_md),
        ]
        all_files.extend(files_named.items())
        return {
            "manifest": manifest,
            "summary_md": summary_md,
            "files": all_files,
        }

    # ------------------------------------------------------------------
    def _serialise_events(self, events: Iterable[Event]) -> str:
        out: list[str] = []
        for ev in events:
            out.append(
                json.dumps(
                    _event_to_redacted_dict(ev),
                    separators=(",", ":"),
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
        return "\n".join(out) + ("\n" if out else "")

    def _serialise_filtered(
        self,
        events: Iterable[Event],
        predicate,
    ) -> tuple[str, int]:
        rows: list[str] = []
        count = 0
        for ev in events:
            if not predicate(ev):
                continue
            count += 1
            rows.append(
                json.dumps(
                    _event_to_redacted_dict(ev),
                    separators=(",", ":"),
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
        return "\n".join(rows) + ("\n" if rows else ""), count

    # ------------------------------------------------------------------
    def _safety_summary(self) -> dict[str, bool]:
        """Snapshot of the Phase 1 safety flags. Pulled lazily so we
        do not import the settings module at class load time (test
        suites that monkeypatch ``AMA_DATA_DIR`` / clear the cache
        depend on the singleton being built fresh)."""
        try:
            from app.config.settings import get_settings

            settings = get_settings()
        except Exception:  # pragma: no cover - extremely defensive
            return {}
        return {
            "live_trading_enabled": bool(settings.live_trading_enabled),
            "right_tail_enabled": bool(settings.right_tail_enabled),
            "llm_enabled": bool(settings.llm_enabled),
            "exchange_live_order_enabled": bool(
                settings.exchange_live_order_enabled
            ),
            "trading_mode_paper": settings.trading_mode == "paper",
        }
