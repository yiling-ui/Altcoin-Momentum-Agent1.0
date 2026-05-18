"""Telegram message formatters (Phase 1 skeletons).

Issue #10 will pipe these strings into an outbound `python-telegram-bot`
adapter. Phase 1 only declares the 10 categories listed in Issue #10:

    - format_system_status
    - format_market_regime
    - format_candidate_symbol
    - format_state_transition
    - format_order_event
    - format_risk_rejection
    - format_profit_lock
    - format_capital_rebase
    - format_incident_alert
    - format_daily_report

Each function is deterministic, pure and free of network calls. They take
plain dicts (or domain models in later phases) and return a UTF-8 string.
The signatures are stable so Issue #10 can swap in real templates without
changing call sites.

Phase 1 implementations are intentionally minimal: a single human-readable
line tagged with [PHASE1-SKELETON] so any leak of a placeholder into a
real channel is immediately recognisable.
"""

from __future__ import annotations

from typing import Any, Mapping

_PHASE1_TAG = "[PHASE1-SKELETON]"


def _kv(payload: Mapping[str, Any]) -> str:
    """Render a payload mapping as ``k=v k=v`` for the skeleton output."""
    return " ".join(f"{k}={v}" for k, v in payload.items())


# ---------------------------------------------------------------------------
# 1. System status        - /status, periodic heartbeat (Spec §32, §36)
# ---------------------------------------------------------------------------
def format_system_status(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} system_status {_kv(payload)}"


# ---------------------------------------------------------------------------
# 2. Market regime        - REGIME_UPDATED event (Spec §15)
# ---------------------------------------------------------------------------
def format_market_regime(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} market_regime {_kv(payload)}"


# ---------------------------------------------------------------------------
# 3. Candidate symbol     - PRE_ANOMALY_DETECTED / ANOMALY_DETECTED (Spec §17/§18)
# ---------------------------------------------------------------------------
def format_candidate_symbol(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} candidate_symbol {_kv(payload)}"


# ---------------------------------------------------------------------------
# 4. State transition     - STATE_TRANSITION event (Spec §26)
# ---------------------------------------------------------------------------
def format_state_transition(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} state_transition {_kv(payload)}"


# ---------------------------------------------------------------------------
# 5. Order event          - ORDER_SENT / ORDER_FILLED / ORDER_CANCELLED (Spec §30)
# ---------------------------------------------------------------------------
def format_order_event(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} order_event {_kv(payload)}"


# ---------------------------------------------------------------------------
# 6. Risk rejection       - RISK_REJECTED event (Spec §27)
# ---------------------------------------------------------------------------
def format_risk_rejection(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} risk_rejection {_kv(payload)}"


# ---------------------------------------------------------------------------
# 7. Profit lock          - LOCK_PROFIT / EXIT_TRIGGERED (Spec §29)
# ---------------------------------------------------------------------------
def format_profit_lock(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} profit_lock {_kv(payload)}"


# ---------------------------------------------------------------------------
# 8. Capital rebase       - CAPITAL_WITHDRAWAL / PROFIT_HARVEST /
#                           CAPITAL_REBASE / RISK_BUDGET_RECALCULATED (Spec §28)
# ---------------------------------------------------------------------------
def format_capital_rebase(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} capital_rebase {_kv(payload)}"


# ---------------------------------------------------------------------------
# 9. Incident alert       - INCIDENT_OPENED / PROTECTION_MODE_ENTERED (Spec §38)
# ---------------------------------------------------------------------------
def format_incident_alert(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} incident_alert {_kv(payload)}"


# ---------------------------------------------------------------------------
# 10. Daily report        - end-of-day summary
# ---------------------------------------------------------------------------
def format_daily_report(payload: Mapping[str, Any]) -> str:
    return f"{_PHASE1_TAG} daily_report {_kv(payload)}"


# Public registry so Issue #10 can iterate / sanity-check coverage.
FORMATTERS: dict[str, callable] = {
    "system_status": format_system_status,
    "market_regime": format_market_regime,
    "candidate_symbol": format_candidate_symbol,
    "state_transition": format_state_transition,
    "order_event": format_order_event,
    "risk_rejection": format_risk_rejection,
    "profit_lock": format_profit_lock,
    "capital_rebase": format_capital_rebase,
    "incident_alert": format_incident_alert,
    "daily_report": format_daily_report,
}

__all__ = [
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
    "FORMATTERS",
]
