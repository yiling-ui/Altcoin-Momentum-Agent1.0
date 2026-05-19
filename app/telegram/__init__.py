"""Telegram outbound + Command Center package (Spec §32, Issue #10 Part 4).

Phase 10D ships:

  - :class:`TelegramOutboundClient` ABC + :class:`FakeTelegramClient`
    (deterministic in-process recorder; default transport for paper
    mode) + :class:`TelegramHttpClient` (refusal-only HTTP skeleton -
    every call raises :class:`TelegramTransportError`; the real
    transport ships behind Spec §41 Go/No-Go).
  - :class:`AlertDispatcher` - proactive push pipeline with
    throttle / dedupe / severity / cooldown + P0 bypass + low-severity
    risk-rejection aggregation.
  - :class:`TelegramCommandCenter` - 18-command operator surface
    (status / positions / pnl / risk / capital / incidents / pause /
    resume / kill_all / rebase + 6 ``/export_*`` commands).
  - :class:`TelegramExportBridge` - bridges ``/export_*`` to the
    Phase 8.5 :class:`TestDataExportService`. Sends a SHORT generating
    summary + the redacted ``.zip`` as a Telegram document
    attachment; never a raw chat dump.
  - 10 production-ready formatters that replace the Phase 1
    placeholders. Every formatter: short, paper-mode banner, live
    flag, redacted, no IO, no Risk Engine bypass.

Phase 10D boundary - every clause is enforced by tests:

  1. No real network call by default. The default outbound transport
     is :class:`FakeTelegramClient`. :class:`TelegramHttpClient`
     refuses on every call.
  2. No write surface. No file under ``app/telegram/`` defines
     ``create_order`` / ``cancel_order`` / ``set_leverage`` /
     ``set_margin_mode``.
  3. No Telegram command bypasses the Risk Engine. ``/pause`` /
     ``/resume`` flip an in-process advisory flag only; the Risk
     Engine remains the single trading-decision gate.
  4. ``/kill_all`` writes audit events but does NOT call any real
     exchange write surface in Phase 10D.
  5. ``/rebase`` does NOT execute a real withdrawal; Phase 8 Capital
     Flow Engine remains the only entry point.
  6. No state-mutating component import (``RiskEngine`` /
     ``ExecutionFSMDriver`` / ``CapitalFlowEngine`` / etc.).
  7. No ``os.environ`` reads. Credentials must be passed in
     explicitly by the caller.
  8. No hard-coded secret. No ``api_key`` / ``api_secret`` /
     ``bot_token`` parameter or concrete env-var literal anywhere
     under :mod:`app.telegram`.
  9. No exception escapes. The dispatcher / command center /
     export bridge NEVER raise into the caller; every transport /
     formatter / export failure becomes an audit event.
  10. The Phase 1 safety lock remains in force.
"""

from app.telegram import formatter as formatter
from app.telegram.alerts import (
    AlertDispatchResult,
    AlertDispatcher,
    AlertSeverity,
    assert_message_redacted,
)
from app.telegram.bot import ExportHandler, TelegramCommandCenter
from app.telegram.commands import (
    AVAILABLE_COMMANDS,
    CONFIRM_REQUIRED,
    EXPORT_COMMAND_SET,
    EXPORT_COMMANDS,
    LOUD_AUDIT_COMMANDS,
    OPERATOR_COMMANDS,
    STATUS_COMMANDS,
    Command,
    CommandResult,
    CommandStatus,
)
from app.telegram.exports import TelegramExportBridge
from app.telegram.formatter import (
    ALL_TAGS,
    ALLOWED_TRADING_MODES,
    FORMATTERS,
    HIGH_PRIORITY_REJECT_REASONS,
    TAG_CANDIDATE_SYMBOL,
    TAG_CAPITAL_REBASE,
    TAG_DAILY_REPORT,
    TAG_INCIDENT_ALERT,
    TAG_MARKET_REGIME,
    TAG_ORDER_EVENT,
    TAG_PROFIT_LOCK,
    TAG_RISK_REJECTION,
    TAG_STATE_TRANSITION,
    TAG_SYSTEM_STATUS,
    TRADING_MODE_LIVE,
    TRADING_MODE_LIVE_LIMITED,
    TRADING_MODE_PAPER,
    format_candidate_symbol,
    format_capital_rebase,
    format_daily_report,
    format_incident_alert,
    format_market_regime,
    format_order_event,
    format_profit_lock,
    format_risk_rejection,
    format_state_transition,
    format_system_status,
)
from app.telegram.outbound import (
    FakeTelegramClient,
    OutboundCall,
    OutboundSurface,
    TelegramHttpClient,
    TelegramOutboundClient,
)


__all__ = [
    # Formatters + tags
    "formatter",
    "FORMATTERS",
    "ALL_TAGS",
    "HIGH_PRIORITY_REJECT_REASONS",
    "ALLOWED_TRADING_MODES",
    "TRADING_MODE_PAPER",
    "TRADING_MODE_LIVE_LIMITED",
    "TRADING_MODE_LIVE",
    "TAG_SYSTEM_STATUS",
    "TAG_MARKET_REGIME",
    "TAG_CANDIDATE_SYMBOL",
    "TAG_STATE_TRANSITION",
    "TAG_ORDER_EVENT",
    "TAG_RISK_REJECTION",
    "TAG_PROFIT_LOCK",
    "TAG_CAPITAL_REBASE",
    "TAG_INCIDENT_ALERT",
    "TAG_DAILY_REPORT",
    "format_system_status",
    "format_market_regime",
    "format_candidate_symbol",
    "format_state_transition",
    "format_order_event",
    "format_risk_rejection",
    "format_profit_lock",
    "format_capital_rebase",
    "format_incident_alert",
    "format_daily_report",
    # Outbound transport
    "TelegramOutboundClient",
    "FakeTelegramClient",
    "TelegramHttpClient",
    "OutboundCall",
    "OutboundSurface",
    # Alert dispatcher
    "AlertDispatcher",
    "AlertDispatchResult",
    "AlertSeverity",
    "assert_message_redacted",
    # Command center
    "TelegramCommandCenter",
    "ExportHandler",
    # Commands
    "Command",
    "CommandResult",
    "CommandStatus",
    "AVAILABLE_COMMANDS",
    "STATUS_COMMANDS",
    "OPERATOR_COMMANDS",
    "EXPORT_COMMANDS",
    "EXPORT_COMMAND_SET",
    "CONFIRM_REQUIRED",
    "LOUD_AUDIT_COMMANDS",
    # Export bridge
    "TelegramExportBridge",
]
