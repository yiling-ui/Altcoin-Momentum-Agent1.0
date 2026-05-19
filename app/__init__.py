"""AMA-RT Altcoin Momentum Agent - Right Tail Edition.

Phase 10D: Telegram Outbound + Export Commands (Issue #10 Part 4).

This package is paper-mode by default and contains NO live trading
code. Every Phase 1-10C contract remains in force. Phase 10D ADDS
the operator-facing :mod:`app.telegram` outbound layer:

  - 10 production-grade formatters that replace the Phase 1
    placeholders. Every formatter is short, redacted, banner-tagged,
    and free of trade-decision side effects.
  - :class:`TelegramOutboundClient` ABC + :class:`FakeTelegramClient`
    (deterministic recorder; default transport for paper mode) +
    :class:`TelegramHttpClient` (refusal-only HTTP skeleton; the real
    transport ships behind Spec §41 Go/No-Go in a separate PR).
  - :class:`AlertDispatcher` with throttle / dedupe / severity /
    cooldown + P0 bypass + low-severity risk-rejection aggregation.
  - :class:`TelegramCommandCenter` with the 16 Issue-mandated
    commands (status / positions / pnl / risk / capital / incidents /
    pause / resume / kill_all / rebase + 6 ``/export_*``).
  - :class:`TelegramExportBridge` that connects ``/export_*`` to the
    Phase 8.5 :class:`TestDataExportService`. Sends a SHORT generating
    summary + the redacted ``.zip`` document attachment; never a raw
    chat dump.

Phase 10D is constrained:

  - The five Phase 1 safety flags remain locked. ``llm_enabled``
    stays ``False`` at boot. Phase 10D does not flip any of them.
  - No exchange SDK / HTTP / WebSocket / LLM client / third-party
    Telegram bot library (``python_telegram_bot`` / ``telebot`` /
    ``aiogram``) is imported anywhere under :mod:`app.telegram`.
  - No write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``) is added.
  - No ``api_key`` / ``api_secret`` / ``bot_token`` parameter or
    concrete env-var literal lives anywhere under :mod:`app.telegram`.
  - No ``os.environ`` / ``getenv`` reads anywhere under
    :mod:`app.telegram`. Credentials must be passed in explicitly.
  - The dispatcher / command center / export bridge NEVER raise
    into the caller; every transport / formatter / export failure
    becomes an audit event.
  - ``/kill_all`` / ``/rebase`` write audit events but do NOT touch
    any real exchange surface in Phase 10D. Paper-mode protective
    close-out is handled by the Phase 9 :class:`ExecutionFSMDriver`.
  - ``/pause`` / ``/resume`` flip an in-process advisory flag only.
    The Risk Engine remains the single trading-decision gate.
  - All bytes that leave through the dispatcher are run through
    :func:`app.exports.redaction.assert_no_forbidden_substrings`
    first. The bridge consumes the Phase 8.5 :class:`TestDataExportService`
    redacted-zip output without re-implementing redaction.

Phase 10C contracts that remain in force:

  - app.llm.*: receive-only LLM Guarded Interpreter (Spec §22).
  - LLM_INTERPRETED / LLM_DEGRADED / LLM_SCHEMA_REJECTED events
    populate normally; Phase 10D never calls the interpreter.

Phase 10B contracts that remain in force:

  - app.reflection.*: read-only Reflection Engine.
  - app.replay.*: read-only Replay Engine over events.db.

Phase 9 contracts that remain in force:

  - app.execution.*: paper-mode Execution FSM driver. The four
    ExchangeClientBase write surfaces continue to raise
    SafeModeViolation; Phase 10D NEVER overrides them.
  - app.reconciliation.*: pure-function reconciler.
  - app.incidents.*: incident repository (writes incidents.db).

Phase 10D does NOT implement:

  - A real Telegram outbound HTTP transport (the
    :class:`TelegramHttpClient` is a refusal-only skeleton)
  - Real-trade persistence into trades.db / positions.db
  - LLM-driven trade decisions / direction / leverage / target_price
  - Real network access at boot
"""

__version__ = "1.4.0a10d"
__phase__ = "Phase 10D - Telegram Outbound + Export Commands"
