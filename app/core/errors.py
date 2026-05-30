"""Typed error hierarchy for AMA-RT.

These error classes are referenced by the skeleton modules (Risk Engine,
Execution FSM, Telegram, Monitoring) so that Phase 2+ can raise them
without further refactor.
"""

from __future__ import annotations


class AMARTError(Exception):
    """Base exception for all AMA-RT failures."""


class ConfigError(AMARTError):
    """Configuration is invalid or missing."""


class SafetyViolation(AMARTError):
    """A caller attempted an action forbidden in the current phase.

    Examples: live order in paper mode, bypassing the Risk Engine,
    enabling right-tail amplification before paper acceptance.
    """


class RiskRejection(AMARTError):
    """The Risk Engine refused to approve an action."""


class ExecutionError(AMARTError):
    """Execution FSM detected an inconsistent or unsafe state."""


class ReconciliationError(AMARTError):
    """Local state and exchange state disagree."""


class EventPersistenceError(AMARTError):
    """An event could not be appended to (or read from) the event log.

    Phase 2 raises this from `EventRepository` when SQLite reports an
    integrity / IO error, after logging the failure via loguru. Callers
    should treat this as a hard error - losing an event silently is the
    one thing the event-sourcing substrate is forbidden to do.
    """


# ---------------------------------------------------------------------------
# Phase 3 - Exchange Gateway (Issue #3)
# ---------------------------------------------------------------------------
class SafeModeViolation(SafetyViolation):
    """Raised when a caller attempts an action forbidden by the current
    Phase 3 safe mode.

    Phase 3 introduces the Exchange Gateway abstraction in read-only mode.
    Any attempt to call a write surface (`create_order`, `cancel_order`,
    `set_leverage`, `set_margin_mode`) on any `ExchangeClientBase`
    subclass must raise this exception. The exception is also raised by
    the Phase 3 boot path if the safety lock has drifted between Phase 1
    config-load time and the moment the exchange client is constructed.

    `SafeModeViolation` is a subclass of `SafetyViolation` so any
    pre-existing handler that catches the broader Phase 1 exception
    (e.g. the Phase 2 `_assert_phase1_safety` boot check) continues to
    catch the Phase 3 narrowing. Tests assert this inheritance.
    """


class ExchangeError(AMARTError):
    """Base class for exchange-gateway errors that are not safety violations.

    Phase 3 + later phases can raise this for transport-level problems
    (REST 5xx, WebSocket dropouts, parsing failures). It is intentionally
    distinct from `SafeModeViolation`: a connection drop is recoverable
    and merely degrades the data tier; a write attempt while live trading
    is disabled is unrecoverable and must abort the action.
    """


class ExchangeConnectionError(ExchangeError):
    """The WebSocket / REST link to the exchange is unhealthy.

    Issued when the gateway is asked for data while the connection state
    is anything other than `CONNECTED`. Spec §14.2 + §31 require that
    downstream modules treat this as a `DATA_UNRELIABLE` signal and stop
    new openings.
    """


# ---------------------------------------------------------------------------
# Phase 10D - Telegram Outbound + Export Commands (Issue #10 Part 4)
# ---------------------------------------------------------------------------
class TelegramTransportError(AMARTError):
    """Raised when the Telegram outbound transport cannot deliver a message.

    Phase 10D introduces the receive-only Telegram outbound layer. This
    exception is the typed failure surface the alert dispatcher catches
    and downgrades into a ``TELEGRAM_SEND_FAILED`` audit event - it is
    NOT a safety violation, just a recoverable transport problem
    (timeout, rate-limit, network drop, refusal-only HTTP skeleton).

    ``TelegramTransportError`` is intentionally NOT a subclass of
    :class:`SafetyViolation`. The Phase 10D contract: a Telegram send
    failure must NEVER bring down the trading process or interfere with
    Risk Engine / Execution FSM / Capital Flow Engine. The dispatcher
    swallows the exception, writes the audit event, and continues.
    """


class TelegramAuthError(SafetyViolation):
    """Raised when an unauthorised user attempts a Telegram command.

    Phase 10D enforces the operator allow-list. Calls from non-admin
    users are rejected and recorded as ``TELEGRAM_COMMAND_REJECTED``.
    The exception is a :class:`SafetyViolation` so any Phase 1 / Phase 9
    handler that catches the broader safety hierarchy continues to
    catch it.
    """


class DataExportError(AMARTError):
    """Phase 10D: an export command failed to deliver its document.

    This is the typed failure for the Telegram export bridge layered
    on top of Phase 8.5 :class:`app.exports.service.ExportError`. It
    converts into a ``DATA_EXPORT_FAILED`` audit event; the dispatcher
    never escalates to the Risk Engine or interrupts trading.
    """


# ---------------------------------------------------------------------------
# PR110 - Live Foundation v0 (Live Path Isolation + Runtime Mode Guard +
# Right-tail Leverage Gate)
# ---------------------------------------------------------------------------
class LivePathIsolationViolation(SafetyViolation):
    """Raised when a non-LIVE order intent attempts to reach the live path.

    PR110 introduces a hard isolation boundary: the historical / blind /
    simulated / paper-shadow code paths (``OrderSource.SIM`` /
    ``BLIND`` / ``REPLAY`` / ``PAPER_SHADOW``) may continue to exist,
    but they MUST NEVER reach a live order gateway. The
    :class:`app.live.path_isolation.LivePathIsolationGuard` raises this
    exception (and emits a ``LIVE_PATH_BLOCKED`` event) the moment any
    order intent whose ``source`` is not ``OrderSource.LIVE`` is handed
    to the live path.

    It is a :class:`SafetyViolation` so any existing Phase 1 / Phase 9
    handler that catches the broader safety hierarchy continues to
    catch it.
    """


class LiveModeViolation(SafetyViolation):
    """Raised when an action is attempted in the wrong live runtime mode.

    Examples: a real order attempt while the runtime is ``LIVE_SHADOW``;
    a real order attempt while ``LIVE_LIMITED`` has not been armed via
    the operator confirmation handshake; an attempt to arm
    ``LIVE_LIMITED`` without a persisted confirmation state.

    A :class:`SafetyViolation` subclass for the same handler-compatibility
    reason as :class:`LivePathIsolationViolation`.
    """


class LeverageGateViolation(SafetyViolation):
    """Raised when forbidden (e.g. AI-derived) input reaches the leverage gate.

    The PR110 right-tail leverage gate is deterministic: leverage may be
    decided ONLY by the capital profile + the deterministic right-tail
    evidence gate + the risk engine. Any attempt to feed the gate an
    AI / LLM / Telegram / blind-result field is a safety violation. The
    gate normally returns a *rejection decision* (so the audit trail
    records the refusal); this exception is reserved for the defensive
    assertion path.
    """


# ---------------------------------------------------------------------------
# PR111 - Live API Integration Pack v0
# ---------------------------------------------------------------------------
class LiveTradeNotEnabled(SafeModeViolation):
    """Raised when any Binance ``PRIVATE_TRADE`` surface is invoked in PR111.

    PR111 ships the live private-trade client interface but keeps every
    order / cancel / leverage / margin surface BLOCKED. A caller that
    invokes one of those surfaces gets this exception (or, where a
    non-raising contract is expected, the ``TRADE_API_BLOCKED_BY_PR111``
    sentinel). No real order request is ever built or sent.

    It subclasses :class:`SafeModeViolation` (and therefore
    :class:`SafetyViolation`) so any existing boot-time / Risk Engine
    handler that catches the broader safety hierarchy continues to
    catch it. The exception text never carries a secret.
    """


class LiveApiError(ExchangeError):
    """Recoverable transport / protocol failure talking to a live API.

    Used by the PR111 Binance / Telegram / DeepSeek clients for HTTP
    transport errors (timeout, non-2xx, malformed JSON). It is NOT a
    safety violation - the health check downgrades it into a FAIL /
    WARN status. The error text is sanitised so it never carries a
    secret, token, or full request signature.
    """
