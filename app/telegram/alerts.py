"""Phase 10D - AlertDispatcher: proactive Telegram push (Issue #10 Part 4).

The dispatcher is the *single sink* for proactive Telegram messages.
Every Phase 10D push - regime flips, candidate symbols, state
transitions, order events, risk rejections, profit locks, capital
rebases, incidents, daily reports - flows through this class.

Responsibilities
----------------

  - Throttle / dedupe (``alert_dedupe_key`` + per-key cooldown).
  - Severity routing (``INFO`` / ``WARNING`` / ``CRITICAL``).
  - P0 / P1 bypass: incidents and CRITICAL-severity alerts skip the
    cooldown.
  - Aggregation: low-severity risk rejections are buffered into a
    rolling 10-minute summary so the chat never gets flooded by a
    burst of routine ``manipulation_m1`` rejections.
  - Defence-in-depth redaction: every outbound payload is run through
    :func:`app.exports.redaction.assert_no_forbidden_substrings`
    before reaching the transport.
  - Audit: every successful send writes a ``TELEGRAM_MESSAGE_SENT``
    event; every failed send writes a ``TELEGRAM_SEND_FAILED`` event.
    The dispatcher NEVER raises into the caller - a transport drop
    must not bring down the trading process.

Phase 10D boundary
------------------

The dispatcher:

  - opens NO socket
  - imports NO exchange / LLM / third-party Telegram bot SDK
  - reads NO ``os.environ``
  - defines NO write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - holds NO ``api_key`` / ``api_secret`` / ``bot_token`` parameter
    or literal anywhere in its source tree
  - never calls Risk Engine / Execution FSM / Capital Flow Engine
  - never affects trading state - it only formats + delivers strings
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from loguru import logger

from app.core.clock import now_ms
from app.core.errors import TelegramTransportError
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.exports.redaction import (
    assert_no_forbidden_substrings,
    forbidden_substrings,
    redact,
)
from app.telegram.formatter import (
    ALL_TAGS,
    FORMATTERS,
    HIGH_PRIORITY_REJECT_REASONS,
    TAG_RISK_REJECTION,
)
from app.telegram.outbound import (
    FakeTelegramClient,
    OutboundCall,
    OutboundSurface,
    TelegramOutboundClient,
)


class AlertSeverity(str, Enum):
    """Severity ladder for proactive pushes.

    INFO    - routine; subject to dedupe + cooldown.
    WARNING - elevated; shorter cooldown.
    CRITICAL- bypasses cooldown entirely (P0/P1, stop_unconfirmed,
              unknown_position, kill_all results, protection mode).
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Ordinal ranks for severity comparison. String values would sort
# alphabetically (``critical < info < warning``) which is wrong; we
# explicitly assign integers so a numerically higher severity bypasses
# a lower-severity cooldown.
_SEVERITY_RANK: dict[AlertSeverity, int] = {
    AlertSeverity.INFO: 0,
    AlertSeverity.WARNING: 1,
    AlertSeverity.CRITICAL: 2,
}


# Default cooldown table (milliseconds). The dispatcher consults this
# table indexed by (tag, severity) when computing the time-to-next-send
# for a given dedupe key. CRITICAL is hard-coded to 0 below so it
# always bypasses the cooldown.
_DEFAULT_COOLDOWN_MS: dict[AlertSeverity, int] = {
    AlertSeverity.INFO: 60_000,
    AlertSeverity.WARNING: 30_000,
    AlertSeverity.CRITICAL: 0,
}

# Aggregation window for low-severity risk rejections.
_DEFAULT_AGGREGATION_WINDOW_MS = 10 * 60 * 1000


@dataclass
class AlertDispatchResult:
    """Outcome of a dispatch call. Returned to the caller so tests can
    assert without inspecting the underlying transport.

    ``sent`` is True iff the transport accepted the message. ``reason``
    explains a non-send (``cooldown_active``, ``deduped``, ``aggregated``,
    ``transport_failed``, ``transport_disabled``, ``redacted``).
    ``call`` is the recorded :class:`OutboundCall` when present.
    """

    sent: bool
    reason: str
    call: OutboundCall | None = None
    severity: AlertSeverity = AlertSeverity.INFO
    dedupe_key: str | None = None
    text: str | None = None


@dataclass
class _CooldownEntry:
    last_sent_ts: int
    last_text: str
    severity: AlertSeverity


@dataclass
class _AggregationBucket:
    """Per-key sliding-window aggregation bucket.

    Used for low-severity risk-rejection summarisation. The dispatcher
    flushes the bucket on a configurable cadence (default 10m) and
    sends a single aggregated message instead of N individual ones.
    """

    key: str
    started_at_ts: int
    last_seen_ts: int
    count: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    sample_text: str = ""


class AlertDispatcher:
    """Proactive Telegram push pipeline.

    Construct ONCE per process. The dispatcher holds:

      - the outbound transport (default: :class:`FakeTelegramClient`)
      - an :class:`EventRepository` for audit events
      - a per-(tag, severity) cooldown table
      - a per-key aggregation bucket

    Phase 10D ships ``outbound_enabled=False`` by default. The
    dispatcher still records audit events; tests can flip the flag
    explicitly to verify transport interactions deterministically.
    """

    SOURCE_MODULE = "telegram.alerts"

    def __init__(
        self,
        *,
        outbound: TelegramOutboundClient | None = None,
        event_repo: EventRepository | None = None,
        chat_id: str = "primary",
        outbound_enabled: bool = False,
        cooldown_ms: Mapping[AlertSeverity, int] | None = None,
        aggregation_window_ms: int = _DEFAULT_AGGREGATION_WINDOW_MS,
        max_message_length: int = 1024,
    ) -> None:
        self._outbound: TelegramOutboundClient = outbound or FakeTelegramClient(
            outbound_enabled=outbound_enabled
        )
        self._event_repo = event_repo
        self._chat_id = str(chat_id)
        self._outbound_enabled = bool(outbound_enabled)
        self._cooldown_ms: dict[AlertSeverity, int] = dict(
            cooldown_ms or _DEFAULT_COOLDOWN_MS
        )
        self._aggregation_window_ms = int(aggregation_window_ms)
        self._max_message_length = int(max_message_length)
        self._cooldown: dict[str, _CooldownEntry] = {}
        self._aggregation: dict[str, _AggregationBucket] = {}
        # Counters for monitoring + boot drill assertions.
        self.messages_sent = 0
        self.documents_sent = 0
        self.send_failed = 0
        self.deduped = 0
        self.cooldown_blocked = 0
        self.aggregated = 0
        self.aggregated_flushes = 0
        self.redaction_blocked = 0

    # ==================================================================
    # Public properties / accessors (test + boot helpers)
    # ==================================================================
    @property
    def outbound(self) -> TelegramOutboundClient:
        return self._outbound

    @property
    def event_repo(self) -> EventRepository | None:
        return self._event_repo

    @property
    def outbound_enabled(self) -> bool:
        return self._outbound_enabled

    def reset(self) -> None:
        """Wipe in-process state so a fresh boot drill / test sees no leftovers."""
        self._cooldown.clear()
        self._aggregation.clear()
        self.messages_sent = 0
        self.documents_sent = 0
        self.send_failed = 0
        self.deduped = 0
        self.cooldown_blocked = 0
        self.aggregated = 0
        self.aggregated_flushes = 0
        self.redaction_blocked = 0
        if isinstance(self._outbound, FakeTelegramClient):
            self._outbound.reset()

    # ==================================================================
    # Dispatch
    # ==================================================================
    def dispatch(
        self,
        *,
        tag: str,
        payload: Mapping[str, Any],
        severity: AlertSeverity = AlertSeverity.INFO,
        dedupe_key: str | None = None,
        bypass_throttle: bool = False,
        clock_ms: int | None = None,
    ) -> AlertDispatchResult:
        """Format ``payload`` with the registered formatter for ``tag``,
        then send through the transport subject to throttle rules.

        Returns :class:`AlertDispatchResult` describing the outcome.
        Every result is recorded as a ``TELEGRAM_MESSAGE_SENT`` (on
        success) or ``TELEGRAM_SEND_FAILED`` (on transport failure)
        audit event when an :class:`EventRepository` is wired in.
        """
        if tag not in FORMATTERS:
            return AlertDispatchResult(
                sent=False,
                reason=f"unknown_tag:{tag}",
                severity=severity,
                dedupe_key=dedupe_key,
            )

        formatter = FORMATTERS[tag]
        try:
            text = formatter(payload)
        except Exception as exc:  # noqa: BLE001 - dispatcher must never raise
            logger.error(
                "AlertDispatcher: formatter for tag={} raised {}", tag, exc
            )
            self._audit_failed(
                tag=tag,
                severity=severity,
                reason="formatter_exception",
                error=str(exc),
                dedupe_key=dedupe_key,
            )
            return AlertDispatchResult(
                sent=False,
                reason="formatter_exception",
                severity=severity,
                dedupe_key=dedupe_key,
            )

        # Truncate before redaction-check so a maliciously huge string
        # cannot push the audit row over reasonable limits.
        if len(text) > self._max_message_length:
            text = text[: self._max_message_length - 1] + "\u2026"

        # Belt-and-braces: refuse to send any text that contains a
        # forbidden substring even after the formatter's redaction.
        try:
            assert_no_forbidden_substrings(text)
        except AssertionError as exc:
            logger.error(
                "AlertDispatcher: redaction gate failed for tag={} ({})",
                tag,
                exc,
            )
            self.redaction_blocked += 1
            self._audit_failed(
                tag=tag,
                severity=severity,
                reason="redaction_gate_failed",
                error=str(exc),
                dedupe_key=dedupe_key,
            )
            return AlertDispatchResult(
                sent=False,
                reason="redaction_gate_failed",
                severity=severity,
                dedupe_key=dedupe_key,
                text=text,
            )

        clock = int(clock_ms if clock_ms is not None else now_ms())
        # Promote stop_unconfirmed / unknown_position risk rejections
        # to CRITICAL automatically so they always bypass throttle.
        severity = self._auto_promote(tag=tag, payload=payload, severity=severity)
        bypass_throttle = bypass_throttle or severity is AlertSeverity.CRITICAL

        key = dedupe_key or self._default_dedupe_key(tag, payload)

        # Aggregation path: low-severity risk rejections are buffered.
        if (
            tag == TAG_RISK_REJECTION
            and severity is AlertSeverity.INFO
            and not bypass_throttle
        ):
            self._aggregate(key=key, text=text, payload=payload, clock_ms=clock)
            self.aggregated += 1
            return AlertDispatchResult(
                sent=False,
                reason="aggregated",
                severity=severity,
                dedupe_key=key,
                text=text,
            )

        # Throttle / dedupe path.
        if not bypass_throttle and self._is_within_cooldown(
            key=key, severity=severity, text=text, clock_ms=clock
        ):
            self.cooldown_blocked += 1
            return AlertDispatchResult(
                sent=False,
                reason="cooldown_active",
                severity=severity,
                dedupe_key=key,
                text=text,
            )

        return self._send_text(
            tag=tag,
            text=text,
            severity=severity,
            dedupe_key=key,
            clock_ms=clock,
        )

    # ==================================================================
    # Document send (used by TelegramExportBridge)
    # ==================================================================
    def send_document(
        self,
        *,
        document_path: str,
        document_bytes: bytes,
        caption: str,
        filename: str | None = None,
        chat_id: str | None = None,
        clock_ms: int | None = None,
    ) -> AlertDispatchResult:
        """Send a redacted document attachment and a short caption.

        Used by the Phase 10D Telegram export bridge. The document
        bytes MUST already have been produced by Phase 8.5
        :class:`TestDataExportService` (which runs the redactor +
        :func:`assert_no_forbidden_substrings` on every file before
        zipping). The dispatcher runs the caption through the
        redaction gate as well.
        """
        clock = int(clock_ms if clock_ms is not None else now_ms())
        target = chat_id or self._chat_id
        # Redaction gate on the caption.
        try:
            assert_no_forbidden_substrings(caption)
        except AssertionError as exc:
            logger.error(
                "AlertDispatcher.send_document: redaction gate failed ({})",
                exc,
            )
            self.redaction_blocked += 1
            self._audit_failed(
                tag="document",
                severity=AlertSeverity.CRITICAL,
                reason="redaction_gate_failed",
                error=str(exc),
                dedupe_key=None,
            )
            return AlertDispatchResult(
                sent=False,
                reason="redaction_gate_failed",
                severity=AlertSeverity.CRITICAL,
                text=caption,
            )

        if not self._outbound_enabled:
            # Audit only when the transport is disabled. This path is
            # exercised by the boot drill so the dispatcher writes a
            # TELEGRAM_MESSAGE_SENT-tagged row even when no real bytes
            # leave the process.
            self.documents_sent += 1
            self._audit_sent(
                tag="document",
                severity=AlertSeverity.WARNING,
                surface=OutboundSurface.SEND_DOCUMENT,
                text=caption,
                document_filename=filename or document_path,
                document_size_bytes=len(document_bytes),
                dedupe_key=None,
                clock_ms=clock,
            )
            return AlertDispatchResult(
                sent=True,
                reason="audited_only",
                severity=AlertSeverity.WARNING,
                text=caption,
                call=OutboundCall(
                    surface=OutboundSurface.SEND_DOCUMENT,
                    chat_id=str(target),
                    text=caption,
                    document_filename=filename or document_path,
                    document_size_bytes=len(document_bytes),
                    timestamp=clock,
                ),
            )

        try:
            self._outbound.send_document(
                str(target),
                document_path,
                document_bytes,
                filename=filename,
                caption=caption,
                timestamp=clock,
            )
        except TelegramTransportError as exc:
            logger.warning(
                "AlertDispatcher.send_document: transport error ({})", exc
            )
            self.send_failed += 1
            self._audit_failed(
                tag="document",
                severity=AlertSeverity.WARNING,
                reason="transport_error",
                error=str(exc),
                dedupe_key=None,
            )
            return AlertDispatchResult(
                sent=False,
                reason="transport_failed",
                severity=AlertSeverity.WARNING,
                text=caption,
            )
        # Success.
        self.documents_sent += 1
        call = OutboundCall(
            surface=OutboundSurface.SEND_DOCUMENT,
            chat_id=str(target),
            text=caption,
            document_filename=filename or document_path,
            document_size_bytes=len(document_bytes),
            timestamp=clock,
        )
        self._audit_sent(
            tag="document",
            severity=AlertSeverity.WARNING,
            surface=OutboundSurface.SEND_DOCUMENT,
            text=caption,
            document_filename=filename or document_path,
            document_size_bytes=len(document_bytes),
            dedupe_key=None,
            clock_ms=clock,
        )
        return AlertDispatchResult(
            sent=True,
            reason="ok",
            severity=AlertSeverity.WARNING,
            text=caption,
            call=call,
        )

    # ==================================================================
    # Aggregation flush
    # ==================================================================
    def flush_aggregations(
        self,
        *,
        clock_ms: int | None = None,
    ) -> list[AlertDispatchResult]:
        """Flush every aggregation bucket older than the window.

        The dispatcher does NOT spawn a background timer; the boot
        drill / test harness / future scheduler must call this
        method on a cadence. Returns one
        :class:`AlertDispatchResult` per bucket flushed.
        """
        clock = int(clock_ms if clock_ms is not None else now_ms())
        results: list[AlertDispatchResult] = []
        for key in list(self._aggregation):
            bucket = self._aggregation[key]
            if (clock - bucket.started_at_ts) < self._aggregation_window_ms:
                continue
            text = self._compose_aggregated_summary(bucket)
            del self._aggregation[key]
            self.aggregated_flushes += 1
            results.append(
                self._send_text(
                    tag=TAG_RISK_REJECTION,
                    text=text,
                    severity=AlertSeverity.INFO,
                    dedupe_key=f"agg:{key}",
                    clock_ms=clock,
                    bypass_cooldown=True,
                )
            )
        return results

    def force_flush_aggregations(
        self, *, clock_ms: int | None = None
    ) -> list[AlertDispatchResult]:
        """Force-flush every bucket regardless of window age."""
        clock = int(clock_ms if clock_ms is not None else now_ms())
        results: list[AlertDispatchResult] = []
        for key in list(self._aggregation):
            bucket = self._aggregation[key]
            text = self._compose_aggregated_summary(bucket)
            del self._aggregation[key]
            self.aggregated_flushes += 1
            results.append(
                self._send_text(
                    tag=TAG_RISK_REJECTION,
                    text=text,
                    severity=AlertSeverity.INFO,
                    dedupe_key=f"agg:{key}",
                    clock_ms=clock,
                    bypass_cooldown=True,
                )
            )
        return results

    # ==================================================================
    # Internals
    # ==================================================================
    def _auto_promote(
        self,
        *,
        tag: str,
        payload: Mapping[str, Any],
        severity: AlertSeverity,
    ) -> AlertSeverity:
        """Promote risk-rejection alerts that carry a high-priority reason.

        ``stop_unconfirmed`` / ``unknown_position`` are always
        CRITICAL regardless of caller-supplied severity. They bypass
        the throttle so the operator never misses a stop-unconfirmed
        warning.
        """
        if tag != TAG_RISK_REJECTION:
            return severity
        raw = payload.get("reasons") or payload.get("reject_reasons") or ()
        if isinstance(raw, str):
            reasons_lower = {r.strip().lower() for r in raw.split(",")}
        else:
            try:
                reasons_lower = {str(r).strip().lower() for r in raw}
            except TypeError:
                return severity
        if any(
            critical in reasons_lower
            for critical in ("stop_unconfirmed", "unknown_position")
        ):
            return AlertSeverity.CRITICAL
        if any(r in reasons_lower for r in HIGH_PRIORITY_REJECT_REASONS):
            return AlertSeverity.WARNING
        return severity

    def _default_dedupe_key(
        self,
        tag: str,
        payload: Mapping[str, Any],
    ) -> str:
        """Compose a stable dedupe key from a payload.

        Default key shape: ``<tag>:<symbol>:<state-or-event>``. The
        Issue brief requires that "the same symbol with the same
        state cannot be re-sent in a short window".
        """
        sym = str(payload.get("symbol") or "-")
        sub = (
            payload.get("to")
            or payload.get("event")
            or payload.get("action")
            or payload.get("level")
            or "-"
        )
        return f"{tag}:{sym}:{sub}"

    def _is_within_cooldown(
        self,
        *,
        key: str,
        severity: AlertSeverity,
        text: str,
        clock_ms: int,
    ) -> bool:
        existing = self._cooldown.get(key)
        if existing is None:
            return False
        cooldown = self._cooldown_ms.get(severity, _DEFAULT_COOLDOWN_MS[AlertSeverity.INFO])
        if cooldown <= 0:
            return False
        if existing.last_text == text and severity is existing.severity:
            self.deduped += 1
            return (clock_ms - existing.last_sent_ts) < cooldown
        # A different text under the same key still counts as cooldown
        # for INFO severity (rate-limit), but a higher-severity message
        # bypasses an existing INFO cooldown so a P1 incident never
        # sits behind an info dedupe.
        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[existing.severity]:
            return False
        return (clock_ms - existing.last_sent_ts) < cooldown

    def _aggregate(
        self,
        *,
        key: str,
        text: str,
        payload: Mapping[str, Any],
        clock_ms: int,
    ) -> None:
        bucket = self._aggregation.get(key)
        if bucket is None:
            bucket = _AggregationBucket(
                key=key,
                started_at_ts=clock_ms,
                last_seen_ts=clock_ms,
                count=0,
                reasons={},
                sample_text=text,
            )
            self._aggregation[key] = bucket
        bucket.last_seen_ts = clock_ms
        bucket.count += 1
        raw = payload.get("reasons") or payload.get("reject_reasons") or ()
        if isinstance(raw, str):
            iterable: Iterable[str] = (
                r.strip() for r in raw.split(",") if r.strip()
            )
        else:
            try:
                iterable = (str(r).strip() for r in raw)
            except TypeError:
                iterable = ()
        for r in iterable:
            bucket.reasons[r] = bucket.reasons.get(r, 0) + 1

    def _compose_aggregated_summary(self, bucket: _AggregationBucket) -> str:
        top = sorted(bucket.reasons.items(), key=lambda kv: -kv[1])[:5]
        top_str = ",".join(f"{k}x{v}" for k, v in top) if top else "-"
        return (
            f"[ama-rt:risk_rejection_summary] count={bucket.count} "
            f"top={top_str} key={bucket.key}"
        )

    def _send_text(
        self,
        *,
        tag: str,
        text: str,
        severity: AlertSeverity,
        dedupe_key: str,
        clock_ms: int,
        bypass_cooldown: bool = False,
    ) -> AlertDispatchResult:
        # Always update the cooldown table - a CRITICAL bypass still
        # records the timestamp so the next non-critical send under
        # the same key sees the cooldown.
        self._cooldown[dedupe_key] = _CooldownEntry(
            last_sent_ts=clock_ms,
            last_text=text,
            severity=severity,
        )
        if not self._outbound_enabled:
            # Audit-only path. The fake / disabled transport never
            # actually delivers; we still emit the audit row so
            # paper-mode runs can prove the dispatcher would have
            # sent the message.
            self.messages_sent += 1
            call = OutboundCall(
                surface=OutboundSurface.SEND_MESSAGE,
                chat_id=str(self._chat_id),
                text=text,
                timestamp=clock_ms,
            )
            self._audit_sent(
                tag=tag,
                severity=severity,
                surface=OutboundSurface.SEND_MESSAGE,
                text=text,
                document_filename=None,
                document_size_bytes=None,
                dedupe_key=dedupe_key,
                clock_ms=clock_ms,
            )
            return AlertDispatchResult(
                sent=True,
                reason="audited_only",
                severity=severity,
                dedupe_key=dedupe_key,
                text=text,
                call=call,
            )

        try:
            self._outbound.send_message(
                str(self._chat_id),
                text,
                timestamp=clock_ms,
            )
        except TelegramTransportError as exc:
            logger.warning(
                "AlertDispatcher: transport error for tag={} severity={} ({})",
                tag,
                severity.value,
                exc,
            )
            self.send_failed += 1
            self._audit_failed(
                tag=tag,
                severity=severity,
                reason="transport_error",
                error=str(exc),
                dedupe_key=dedupe_key,
            )
            return AlertDispatchResult(
                sent=False,
                reason="transport_failed",
                severity=severity,
                dedupe_key=dedupe_key,
                text=text,
            )

        # Success.
        self.messages_sent += 1
        call = OutboundCall(
            surface=OutboundSurface.SEND_MESSAGE,
            chat_id=str(self._chat_id),
            text=text,
            timestamp=clock_ms,
        )
        self._audit_sent(
            tag=tag,
            severity=severity,
            surface=OutboundSurface.SEND_MESSAGE,
            text=text,
            document_filename=None,
            document_size_bytes=None,
            dedupe_key=dedupe_key,
            clock_ms=clock_ms,
        )
        return AlertDispatchResult(
            sent=True,
            reason="ok",
            severity=severity,
            dedupe_key=dedupe_key,
            text=text,
            call=call,
        )

    # ==================================================================
    # Audit
    # ==================================================================
    def _audit_sent(
        self,
        *,
        tag: str,
        severity: AlertSeverity,
        surface: OutboundSurface,
        text: str,
        document_filename: str | None,
        document_size_bytes: int | None,
        dedupe_key: str | None,
        clock_ms: int,
    ) -> None:
        if self._event_repo is None:
            return
        payload: dict[str, Any] = {
            "tag": tag,
            "severity": severity.value,
            "surface": surface.value,
            "chat_id": self._chat_id,
            "outbound_enabled": self._outbound_enabled,
            "transport": getattr(self._outbound, "name", "unknown"),
            "text_preview": redact(text)[:240],
            "text_length": len(text),
            "dedupe_key": dedupe_key,
        }
        if document_filename is not None:
            payload["document_filename"] = document_filename
        if document_size_bytes is not None:
            payload["document_size_bytes"] = int(document_size_bytes)
        self._safe_append(
            Event(
                event_type=EventType.TELEGRAM_MESSAGE_SENT,
                source_module=self.SOURCE_MODULE,
                payload=payload,
                timestamp=clock_ms,
            )
        )

    def _audit_failed(
        self,
        *,
        tag: str,
        severity: AlertSeverity,
        reason: str,
        error: str,
        dedupe_key: str | None,
    ) -> None:
        if self._event_repo is None:
            return
        payload: dict[str, Any] = {
            "tag": tag,
            "severity": severity.value,
            "reason": reason,
            "error": redact(error)[:240],
            "dedupe_key": dedupe_key,
            "transport": getattr(self._outbound, "name", "unknown"),
        }
        self._safe_append(
            Event(
                event_type=EventType.TELEGRAM_SEND_FAILED,
                source_module=self.SOURCE_MODULE,
                payload=payload,
            )
        )

    def _safe_append(self, event: Event) -> None:
        """Wrap append_event so a persistence error does NOT raise into the caller.

        The dispatcher's whole point is to deliver alerts safely; if
        the audit log is itself unavailable we log loudly via loguru
        and continue. Phase 1 :class:`EventPersistenceError` semantics
        still apply at the repository layer for callers that DO want
        to react to the error - but the dispatcher always degrades.
        """
        try:
            self._event_repo.append_event(event)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "AlertDispatcher: failed to write audit event {} ({})",
                event.event_type.value,
                exc,
            )


# ---------------------------------------------------------------------------
# Public sanity helper - used by tests + boot drill
# ---------------------------------------------------------------------------
def assert_message_redacted(text: str) -> None:
    """Belt-and-braces: refuse a message that contains a forbidden literal.

    Convenience wrapper over the Phase 8.5 ``assert_no_forbidden_substrings``
    helper so callers (the export bridge, the command center) can
    audit a candidate string before reaching the dispatcher.
    """
    assert_no_forbidden_substrings(
        text,
        extra=("/.env", "\\.env", *forbidden_substrings()),
    )


__all__ = [
    "AlertSeverity",
    "AlertDispatchResult",
    "AlertDispatcher",
    "assert_message_redacted",
    "ALL_TAGS",
]
