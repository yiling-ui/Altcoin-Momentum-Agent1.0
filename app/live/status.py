"""Shared health-status vocabulary for the Live API Integration Pack (PR111)."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class HealthStatus(str, Enum):
    """Tri-state health status for a live API surface."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"

    @property
    def rank(self) -> int:
        # Higher rank = worse. SKIPPED is treated as neutral (does not
        # by itself fail the overall status).
        return {
            HealthStatus.PASS: 0,
            HealthStatus.SKIPPED: 0,
            HealthStatus.WARN: 1,
            HealthStatus.FAIL: 2,
        }[self]


def worst_of(statuses: Iterable[HealthStatus]) -> HealthStatus:
    """Return the worst (most severe) status in ``statuses``.

    An empty / all-SKIPPED collection yields ``PASS`` (nothing failed).
    """
    worst = HealthStatus.PASS
    saw_any_non_skipped = False
    for s in statuses:
        if s != HealthStatus.SKIPPED:
            saw_any_non_skipped = True
        if s.rank > worst.rank:
            worst = s
    if not saw_any_non_skipped:
        return HealthStatus.PASS
    return worst


# Sentinel status strings used by per-surface results (kept as plain
# strings so they can be embedded verbatim in JSON output / events).
TRADE_API_BLOCKED_BY_PR111 = "TRADE_API_BLOCKED_BY_PR111"
TELEGRAM_OUTBOUND_DISABLED = "TELEGRAM_OUTBOUND_DISABLED"

# PR112 hardening: distinct operator-facing reason tags so the health
# check never collapses every failure into a generic "HTTP error". Each
# tag tells the operator exactly what to do next.
SECRET_OK = ""
MISSING_REAL_SECRET = "MISSING_REAL_SECRET"
PLACEHOLDER_SECRET_CONFIGURED = "PLACEHOLDER_SECRET_CONFIGURED"
INVALID_SECRET_OR_UNAUTHORIZED = "INVALID_SECRET_OR_UNAUTHORIZED"  # HTTP 401
PERMISSION_DENIED = "PERMISSION_DENIED"  # HTTP 403
RATE_LIMITED = "RATE_LIMITED"  # HTTP 429
API_ENDPOINT_UNAVAILABLE = "API_ENDPOINT_UNAVAILABLE"  # HTTP 5xx / 404
NETWORK_ERROR = "NETWORK_ERROR"  # transport / DNS / timeout
MALFORMED_API_RESPONSE = "MALFORMED_API_RESPONSE"
PRIVATE_TRADE_CORRECTLY_BLOCKED = "PRIVATE_TRADE_CORRECTLY_BLOCKED"
API_GENERIC_ERROR = "API_GENERIC_ERROR"


def classify_api_error(message: str) -> str:
    """Map a sanitised API error message to a typed operator reason tag.

    The PR111 clients already strip query strings / signatures from their
    error text, so this only inspects the safe remainder. It distinguishes
    HTTP 401 (bad/expired key), 403 (permission), 429 (rate limit),
    5xx/404 (endpoint down), transport errors (network), and malformed
    JSON - instead of collapsing them into one generic message.
    """

    text = (message or "").lower()
    if "401" in text or "unauthorized" in text or "invalid api" in text or "signature" in text:
        return INVALID_SECRET_OR_UNAUTHORIZED
    if "403" in text or "forbidden" in text or "permission" in text:
        return PERMISSION_DENIED
    if "429" in text or "rate limit" in text or "too many" in text:
        return RATE_LIMITED
    if "transport error" in text or "timed out" in text or "timeout" in text:
        return NETWORK_ERROR
    if "urlerror" in text or "connection" in text or "name resolution" in text:
        return NETWORK_ERROR
    if "malformed" in text or "json" in text:
        return MALFORMED_API_RESPONSE
    for code in ("500", "502", "503", "504", "404"):
        if code in text:
            return API_ENDPOINT_UNAVAILABLE
    return API_GENERIC_ERROR


__all__ = [
    "HealthStatus",
    "worst_of",
    "TRADE_API_BLOCKED_BY_PR111",
    "TELEGRAM_OUTBOUND_DISABLED",
    "SECRET_OK",
    "MISSING_REAL_SECRET",
    "PLACEHOLDER_SECRET_CONFIGURED",
    "INVALID_SECRET_OR_UNAUTHORIZED",
    "PERMISSION_DENIED",
    "RATE_LIMITED",
    "API_ENDPOINT_UNAVAILABLE",
    "NETWORK_ERROR",
    "MALFORMED_API_RESPONSE",
    "PRIVATE_TRADE_CORRECTLY_BLOCKED",
    "API_GENERIC_ERROR",
    "classify_api_error",
]
