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
