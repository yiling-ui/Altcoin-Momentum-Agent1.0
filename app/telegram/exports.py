"""Phase 10D - Telegram export bridge (Issue #10 Part 4).

Connects the Phase 10D :class:`TelegramCommandCenter` to the
existing Phase 8.5 :class:`app.exports.service.TestDataExportService`.
Each ``/export_*`` command produces:

  1. A SHORT generating-summary text message (export_id, time range,
     type filter, status=generating).
  2. The redacted ``.zip`` file as a Telegram document attachment
     (NEVER as a raw chat dump; the Issue brief is explicit on this).
  3. A final summary text message with manifest stats.

The bridge writes:

  - ``DATA_EXPORT_GENERATED`` on success
  - ``DATA_EXPORT_FAILED`` on every failure path (size cap exceeded,
    invalid range, invalid type filter, transport drop, redaction
    gate caught a leak)

Phase 10D boundary
------------------

The bridge:

  - opens NO socket
  - imports NO exchange / LLM / third-party Telegram bot SDK
  - reads NO ``os.environ``
  - holds NO ``api_key`` / ``api_secret`` / ``bot_token`` parameter
    or literal anywhere in its source tree
  - never bypasses the Risk Engine or the Phase 1 safety lock
  - refuses any export request whose safety snapshot reports
    ``trading_mode != paper`` (defence-in-depth on top of the CLI's
    own refusal)
  - calls :class:`TestDataExportService` directly; it does NOT
    re-implement redaction, manifest, or summary
  - calls :class:`AlertDispatcher.send_document` for the file
    attachment so the document path is identical to the CLI path
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from app.config.settings import Settings
from app.core.errors import DataExportError
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.exports.redaction import (
    assert_no_forbidden_substrings,
    redact,
)
from app.exports.service import (
    ALLOWED_RANGE_LABELS,
    ALLOWED_TYPE_FILTERS,
    ExportError,
    ExportResult,
    TestDataExportService,
)
from app.telegram.alerts import AlertDispatcher, AlertSeverity
from app.telegram.commands import Command, CommandResult, CommandStatus


# ---------------------------------------------------------------------------
# Command -> (range_label, type_filter) mapping
# ---------------------------------------------------------------------------
# The Issue contract pins the canonical (command, default-arg) pairs
# below. /export_test_data accepts an explicit range arg; the others
# have a single canonical default.
_DEFAULT_RANGE_PER_COMMAND: dict[str, str] = {
    "/export_test_data": "24h",
    "/export_events": "24h",
    "/export_rejections": "24h",
    "/export_capital": "7d",
    "/export_report": "today",
    "/export_learning_dataset": "7d",
}

_TYPE_PER_COMMAND: dict[str, str] = {
    "/export_test_data": "all",
    "/export_events": "events",
    "/export_rejections": "rejections",
    "/export_capital": "capital",
    "/export_report": "all",
    "/export_learning_dataset": "learning",
}


@dataclass
class TelegramExportBridge:
    """Bridges ``/export_*`` Telegram commands to Phase 8.5 export service.

    Construct ONCE per process and pass ``handle`` to the
    :class:`TelegramCommandCenter` via its ``export_handler`` field.
    """

    service: TestDataExportService
    dispatcher: AlertDispatcher
    event_repo: EventRepository | None = None
    refuse_when_not_paper: bool = True
    SOURCE_MODULE: str = field(default="telegram.exports", init=False)

    # ==================================================================
    # Public entry point - called by TelegramCommandCenter
    # ==================================================================
    def handle(
        self,
        command: Command,
        settings: Settings,
        safety_snapshot: dict[str, Any],
    ) -> CommandResult:
        """Run one ``/export_*`` command.

        Returns a :class:`CommandResult` describing the outcome. The
        result is suitable for the bot's reply text; the document
        itself is sent through :meth:`AlertDispatcher.send_document`.
        """
        # 1. Phase 1 safety lock guard.
        if (
            self.refuse_when_not_paper
            and safety_snapshot.get("trading_mode") != "paper"
        ):
            return self._fail(
                command=command,
                reason="refused_non_paper_mode",
                message=(
                    f"{command.name}: refusing to export under "
                    f"trading_mode={safety_snapshot.get('trading_mode')!r}. "
                    "Phase 10D allows export only in paper mode."
                ),
            )

        # 2. Resolve range_label + type_filter from the command + args.
        try:
            range_label, type_filter = self._resolve_args(command)
        except DataExportError as exc:
            return self._fail(
                command=command,
                reason="invalid_argument",
                message=str(exc),
            )

        # 3. Run the export.
        try:
            result = self.service.export(
                range_label=range_label,
                type_filter=type_filter,
            )
        except ExportError as exc:
            # The service raises ExportError on size cap exceeded,
            # invalid range, invalid type filter, etc. Treat the
            # whole class as a recoverable failure.
            return self._fail(
                command=command,
                reason="export_error",
                message=(
                    f"{command.name}: {exc}. "
                    "Try a smaller range or a single type filter; "
                    "/export_test_data 24h is the smallest preset."
                ),
                range_label=range_label,
                type_filter=type_filter,
            )
        except Exception as exc:  # noqa: BLE001 - bridge must never crash
            logger.error(
                "TelegramExportBridge: unexpected failure ({})", exc
            )
            return self._fail(
                command=command,
                reason="unexpected_exception",
                message=(
                    f"{command.name}: export failed: {exc}. "
                    "Trading process is unaffected."
                ),
                range_label=range_label,
                type_filter=type_filter,
            )

        # 4. Read bytes + assert_no_forbidden_substrings on the zip
        # caption (the bytes themselves are guarded by the service's
        # own assert_no_forbidden_substrings check on every file
        # before zipping).
        zip_path = Path(result.zip_path)
        try:
            zip_bytes = zip_path.read_bytes()
        except OSError as exc:
            return self._fail(
                command=command,
                reason="zip_read_failed",
                message=(
                    f"{command.name}: zip file unreadable: {exc}"
                ),
                range_label=range_label,
                type_filter=type_filter,
            )

        # 5. Compose the SHORT generating-summary text the operator
        # sees BEFORE the document arrives.
        generating_text = self._compose_generating_text(
            command=command,
            range_label=range_label,
            type_filter=type_filter,
            result=result,
        )
        # Defence-in-depth: refuse the message if any forbidden
        # literal slipped through.
        try:
            assert_no_forbidden_substrings(generating_text)
        except AssertionError as exc:
            return self._fail(
                command=command,
                reason="redaction_gate_failed",
                message=(
                    f"{command.name}: redaction gate refused the "
                    f"generating summary ({exc})."
                ),
                range_label=range_label,
                type_filter=type_filter,
            )

        # 6. Send the generating-summary text via the dispatcher.
        # (The send is audited as a TELEGRAM_MESSAGE_SENT row.) The
        # generating summary is composed ad-hoc from the manifest
        # (rather than going through the formatter registry) so the
        # caption travels with the document attachment in a single
        # send_document() call. This keeps the Issue contract clean:
        # exactly two outbound calls per /export_*: nothing before
        # the doc, the doc + caption together, no chat dump.
        caption = generating_text
        send_result = self.dispatcher.send_document(
            document_path=str(zip_path),
            document_bytes=zip_bytes,
            caption=caption,
            filename=zip_path.name,
        )

        if not send_result.sent:
            return self._fail(
                command=command,
                reason="send_document_failed",
                message=(
                    f"{command.name}: file send failed "
                    f"({send_result.reason}). The export zip remains "
                    f"on disk at {zip_path.name}."
                ),
                range_label=range_label,
                type_filter=type_filter,
                zip_path=str(zip_path),
            )

        # 7. Audit success.
        self._audit_generated(
            command=command,
            range_label=range_label,
            type_filter=type_filter,
            result=result,
        )

        # 8. Return a short ack to the bot driver.
        return CommandResult(
            status=CommandStatus.OK,
            message=(
                f"{command.name}: ok. "
                f"export_id={result.manifest.export_id} "
                f"range={range_label} type={type_filter} "
                f"events={result.manifest.event_count} "
                f"bytes={result.bytes_written} "
                f"file={zip_path.name}"
            ),
            metadata={
                "action": command.name,
                "export_id": result.manifest.export_id,
                "range_label": range_label,
                "type_filter": type_filter,
                "bytes_written": result.bytes_written,
                "trading_mode": result.manifest.trading_mode,
                "redaction_applied": result.manifest.redaction_applied,
                "zip_filename": zip_path.name,
            },
        )

    # ==================================================================
    # Internals
    # ==================================================================
    def _resolve_args(
        self,
        command: Command,
    ) -> tuple[str, str]:
        """Resolve ``(range_label, type_filter)`` for a command.

        Phase 10D pins the canonical defaults; ``/export_test_data``
        is the only command that takes a user-supplied range arg.
        """
        type_filter = _TYPE_PER_COMMAND.get(command.name)
        default_range = _DEFAULT_RANGE_PER_COMMAND.get(command.name)
        if type_filter is None or default_range is None:
            raise DataExportError(
                f"unsupported export command: {command.name}"
            )

        # Allow the operator to override the range only on
        # /export_test_data per the Issue brief. Other commands ship
        # with a fixed canonical default to keep the operator
        # surface predictable.
        if command.name == "/export_test_data" and command.args:
            requested = str(command.args[0]).strip().lower()
            if requested not in ALLOWED_RANGE_LABELS:
                raise DataExportError(
                    f"/export_test_data: unknown range {requested!r}. "
                    f"Allowed: {sorted(ALLOWED_RANGE_LABELS)}"
                )
            range_label = requested
        else:
            range_label = default_range

        if type_filter not in ALLOWED_TYPE_FILTERS:
            raise DataExportError(
                f"{command.name}: unknown type filter {type_filter!r}"
            )
        return range_label, type_filter

    def _compose_generating_text(
        self,
        *,
        command: Command,
        range_label: str,
        type_filter: str,
        result: ExportResult,
    ) -> str:
        manifest = result.manifest
        return (
            f"[ama-rt:export] mode={manifest.trading_mode} "
            f"command={command.name} export_id={manifest.export_id} "
            f"range={range_label} type={type_filter} "
            f"events={manifest.event_count} "
            f"opportunities={manifest.opportunity_count} "
            f"rejected={manifest.risk_rejected_count} "
            f"capital={manifest.capital_event_count} "
            f"bytes={result.bytes_written} "
            f"redacted={manifest.redaction_applied} "
            f"status=ready"
        )

    def _fail(
        self,
        *,
        command: Command,
        reason: str,
        message: str,
        range_label: str | None = None,
        type_filter: str | None = None,
        zip_path: str | None = None,
    ) -> CommandResult:
        # Try to send a short error message via the dispatcher so the
        # operator sees the failure even when the document was not
        # produced. We do NOT raise into the caller.
        try:
            self.dispatcher.dispatch(
                tag="system_status",
                payload={
                    "trading_mode": self.service.trading_mode,
                    "live_trading_enabled": False,
                    "status": "export_failed",
                    "phase": "10D",
                },
                severity=AlertSeverity.WARNING,
                dedupe_key=f"export_failed:{command.name}",
            )
        except Exception:  # noqa: BLE001
            pass

        self._audit_failed(
            command=command,
            reason=reason,
            range_label=range_label,
            type_filter=type_filter,
            error=message,
            zip_path=zip_path,
        )
        # Return an EXECUTION_ERROR so the bot driver renders the
        # short message body to the operator.
        return CommandResult(
            status=CommandStatus.EXECUTION_ERROR,
            message=message,
            metadata={
                "action": command.name,
                "reason": reason,
                "range_label": range_label,
                "type_filter": type_filter,
            },
        )

    def _audit_generated(
        self,
        *,
        command: Command,
        range_label: str,
        type_filter: str,
        result: ExportResult,
    ) -> None:
        if self.event_repo is None:
            return
        payload = redact(
            {
                "command": command.name,
                "user_id": command.user_id,
                "range_label": range_label,
                "type_filter": type_filter,
                "export_id": result.manifest.export_id,
                "bytes_written": int(result.bytes_written),
                "trading_mode": result.manifest.trading_mode,
                "app_version": result.manifest.app_version,
                "event_count": int(result.manifest.event_count),
                "opportunity_count": int(result.manifest.opportunity_count),
                "risk_rejected_count": int(result.manifest.risk_rejected_count),
                "capital_event_count": int(
                    result.manifest.capital_event_count
                ),
                "redaction_applied": bool(result.manifest.redaction_applied),
                "zip_filename": Path(result.zip_path).name,
            }
        )
        self._safe_append(
            Event(
                event_type=EventType.DATA_EXPORT_GENERATED,
                source_module=self.SOURCE_MODULE,
                payload=dict(payload),
            )
        )

    def _audit_failed(
        self,
        *,
        command: Command,
        reason: str,
        range_label: str | None,
        type_filter: str | None,
        error: str,
        zip_path: str | None,
    ) -> None:
        if self.event_repo is None:
            return
        payload = redact(
            {
                "command": command.name,
                "user_id": command.user_id,
                "reason": reason,
                "range_label": range_label,
                "type_filter": type_filter,
                "error": str(error)[:240],
                "zip_path": zip_path,
            }
        )
        self._safe_append(
            Event(
                event_type=EventType.DATA_EXPORT_FAILED,
                source_module=self.SOURCE_MODULE,
                payload=dict(payload),
            )
        )

    def _safe_append(self, event: Event) -> None:
        try:
            self.event_repo.append_event(event)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "TelegramExportBridge: failed to write {} ({})",
                event.event_type.value,
                exc,
            )


__all__ = [
    "TelegramExportBridge",
]
