"""Typed errors for the Live Execution Gateway (PR113 - Live Execution v0).

PR113 introduces the first code path able to compose + send a real
Binance USDT-M futures order. The error hierarchy below distinguishes a
*safety* refusal (the order must NOT be sent) from a *recoverable*
transport / validation problem.

  - :class:`LiveExecutionBlocked` - a real order was attempted but the
    execution gate refused it. A :class:`SafeModeViolation` so any
    existing safety handler keeps catching it. This is the DEFAULT
    outcome in PR113 (the gates are all-false by default).
  - :class:`AiTradeAuthorityForbidden` - an attempt to drive the
    execution gateway with AI trade authority. A hard refusal: AI NEVER
    places an order in AMA-RT.
  - :class:`OrderValidationError` - the order failed an exchangeInfo /
    profile validation. Recoverable; the gateway turns it into a
    rejection rather than crashing.
  - :class:`ExecutionAdapterError` - a transport / protocol failure
    talking to the live order API. Recoverable; the error text is
    sanitised so it never carries a secret / signature.

Nothing here ever logs a raw secret, key, token, or full request
signature.
"""

from __future__ import annotations

from app.core.errors import ExchangeError, SafetyViolation


class LiveExecutionError(ExchangeError):
    """Base class for live-execution failures that are not safety violations."""


class LiveExecutionBlocked(SafetyViolation):
    """Raised when the execution gate refuses to let a real order leave.

    This is the DEFAULT in PR113: with ``exchange_live_orders=false`` /
    ``trade_authority=false`` / ``LIVE_SHADOW`` the gateway blocks every
    real order. A :class:`SafetyViolation` subclass so any Phase 1 / PR110
    handler that catches the broader safety hierarchy keeps catching it.

    NOTE: the gateway's normal submission API does NOT raise this; it
    returns a ``BLOCKED`` :class:`app.live.execution_models.LiveOrderResult`
    so the refusal is auditable. The exception is reserved for the
    defensive ``assert_*`` paths.
    """


class AiTradeAuthorityForbidden(SafetyViolation):
    """Raised when AI trade authority attempts to drive the execution gateway.

    AMA-RT constitution: AI never decides direction / size / leverage /
    stop / target / exit, and AI never places an order. The execution
    gateway refuses any call carrying ``ai_trade_authority=True``.
    """


class OrderValidationError(LiveExecutionError):
    """Raised when an order fails exchangeInfo / profile validation.

    Recoverable: the gateway converts it into a rejection (no order is
    sent). Carries a typed reason list, never a secret.
    """

    def __init__(self, message: str, *, reasons: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.reasons = tuple(reasons)


class ExecutionAdapterError(LiveExecutionError):
    """Recoverable transport / protocol failure talking to the order API.

    The message is sanitised (no query string / signature / secret).
    """


__all__ = [
    "LiveExecutionError",
    "LiveExecutionBlocked",
    "AiTradeAuthorityForbidden",
    "OrderValidationError",
    "ExecutionAdapterError",
]
