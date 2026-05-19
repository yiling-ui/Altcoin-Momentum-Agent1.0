"""SignalSnapshot serialisation contract (Phase 8.5, Spec §11.2).

The Phase-1 :class:`app.core.models.SignalSnapshot` is the single
source of truth for the field set:

    symbol
    timestamp
    regime
    pre_anomaly_score
    anomaly_score
    liquidity_score
    trade_confirmation_level
    manipulation_level
    right_tail_score
    opportunity_grade
    no_trade_reason

This module does NOT redefine the model; it provides a
deterministic, JSON-safe serialiser + deserialiser so future
Replay / Dataset Builder code can round-trip a SignalSnapshot
through events.db without ambiguity.

Phase 8.5 boundary
------------------

Every helper in this module is pure: it takes value objects in,
returns dicts / value objects out, and never opens a socket, never
imports an exchange SDK, never calls an LLM, never mutates global
state.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import (
    ManipulationLevel,
    MarketRegime,
    OpportunityGrade,
    TradeConfirmationLevel,
)
from app.core.models import SignalSnapshot


def signal_snapshot_to_payload(snapshot: SignalSnapshot) -> dict[str, Any]:
    """Return a JSON-safe dict for the Spec §11.2 SignalSnapshot.

    Enum fields are serialised to their ``.value`` strings so the
    payload is byte-stable across processes. ``no_trade_reason`` is
    rendered as a list of strings (already the storage shape).

    The output dict is deliberately a flat mapping so the Reflection
    engine (Issue #10) can index into it without traversing nested
    structures.
    """
    return {
        "symbol": snapshot.symbol,
        "timestamp": int(snapshot.timestamp),
        "regime": snapshot.regime.value,
        "pre_anomaly_score": float(snapshot.pre_anomaly_score),
        "anomaly_score": float(snapshot.anomaly_score),
        "liquidity_score": float(snapshot.liquidity_score),
        "trade_confirmation_level": snapshot.trade_confirmation_level.value,
        "manipulation_level": snapshot.manipulation_level.value,
        "right_tail_score": float(snapshot.right_tail_score),
        "opportunity_grade": snapshot.opportunity_grade.value,
        "no_trade_reason": list(snapshot.no_trade_reason),
    }


def payload_to_signal_snapshot(payload: dict[str, Any]) -> SignalSnapshot:
    """Inverse of :func:`signal_snapshot_to_payload`.

    Raises a Pydantic ``ValidationError`` if required fields are
    missing or the enum values are unknown.
    """
    return SignalSnapshot(
        symbol=str(payload["symbol"]),
        timestamp=int(payload["timestamp"]),
        regime=MarketRegime(payload["regime"]),
        pre_anomaly_score=float(payload.get("pre_anomaly_score", 0.0) or 0.0),
        anomaly_score=float(payload.get("anomaly_score", 0.0) or 0.0),
        liquidity_score=float(payload.get("liquidity_score", 0.0) or 0.0),
        trade_confirmation_level=TradeConfirmationLevel(
            payload.get("trade_confirmation_level", TradeConfirmationLevel.T0.value)
        ),
        manipulation_level=ManipulationLevel(
            payload.get("manipulation_level", ManipulationLevel.M0.value)
        ),
        right_tail_score=float(payload.get("right_tail_score", 0.0) or 0.0),
        opportunity_grade=OpportunityGrade(
            payload.get("opportunity_grade", OpportunityGrade.D.value)
        ),
        no_trade_reason=[str(r) for r in payload.get("no_trade_reason", []) or []],
    )
