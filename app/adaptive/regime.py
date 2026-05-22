"""Phase 11C.1C-A - Cheap deterministic market regime classifier.

The classifier is intentionally simple: it derives a macro bucket
from a small set of inputs the WS-radar already produces or the
runner can supply on the seam:

  - ``avg_price_acceleration_60s`` - average per-symbol 60s price
    acceleration across the radar's known universe (positive ->
    risk-on tilt).
  - ``positive_acceleration_ratio`` - fraction of symbols with a
    positive 60s acceleration (broad-based rally vs. narrow).
  - ``liquidation_event_rate`` - ratio of recent liquidation events
    over the window (high -> SYSTEMIC_RISK / RISK_OFF).
  - ``data_quality`` - ``"ok"`` / ``"stale"`` / ``"unknown"``;
    Phase 4 / Phase 11C.1B mark every snapshot as ``"stale"`` when
    the WS link goes silent.

Phase 11C.1C-A boundary
-----------------------

This is a *first version* designed to be deterministic, testable,
and decoupled from any heavy data pipeline. A later PR will replace
the heuristic with the full Phase 5 Regime Engine output. Until
then the classifier is conservative: it returns ``NEUTRAL`` when
inputs are missing and only enters an explicit ``RISK_OFF`` /
``NO_TRADE`` bucket when the inputs unambiguously demand it.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.adaptive.models import (
    MarketRegimeAssessment,
    REGIME_BUCKETS,
    STRATEGY_MODES,
)


#: Default risk-multiplier mapping per bucket. Used to populate
#: :attr:`MarketRegimeAssessment.risk_multiplier` when the runner
#: does not supply an explicit value. Phase 7+ may override.
DEFAULT_REGIME_RISK_MULTIPLIER: dict[str, float] = {
    "MEME_RISK_ON": 1.0,
    "SECTOR_ROTATION": 0.85,
    "BTC_ABSORPTION": 0.70,
    "ALT_RISK_OFF": 0.50,
    "SYSTEMIC_RISK": 0.0,
    "RISK_OFF": 0.0,
    "NO_TRADE": 0.0,
    "NEUTRAL": 0.75,
}

#: Default allowed strategy modes per bucket. ``reject`` is implicit
#: (always available) and not listed here.
DEFAULT_REGIME_ALLOWED_MODES: dict[str, tuple[str, ...]] = {
    "MEME_RISK_ON": ("follow", "pullback", "observe"),
    "SECTOR_ROTATION": ("follow", "pullback", "observe"),
    "BTC_ABSORPTION": ("pullback", "observe"),
    "ALT_RISK_OFF": ("observe",),
    "SYSTEMIC_RISK": (),
    "RISK_OFF": (),
    "NO_TRADE": (),
    "NEUTRAL": ("pullback", "observe"),
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def assess_market_regime(
    *,
    avg_price_acceleration_60s: float | None = None,
    positive_acceleration_ratio: float | None = None,
    liquidation_event_rate: float | None = None,
    data_quality: str | None = None,
    snapshot_count: int = 0,
    extra: Mapping[str, Any] | None = None,
) -> MarketRegimeAssessment:
    """Assess the current macro regime from the radar's aggregate state.

    All inputs are optional. The classifier is conservative:

      - data_quality=='stale' -> NO_TRADE (confidence 1.0)
      - liquidation_event_rate >= 0.10 -> SYSTEMIC_RISK
      - avg_price_acceleration_60s <= -0.005 AND positive_ratio < 0.30
        -> ALT_RISK_OFF
      - avg_price_acceleration_60s >= 0.005 AND positive_ratio >= 0.55
        -> MEME_RISK_ON (broad-based)
      - avg_price_acceleration_60s >= 0.002 AND positive_ratio >= 0.40
        -> SECTOR_ROTATION (narrower rally)
      - otherwise -> NEUTRAL

    Returns a :class:`MarketRegimeAssessment` with risk_multiplier
    and allowed_strategy_modes filled in from the default mapping.
    """
    notes: list[str] = []
    no_trade_reason: list[str] = []

    quality = (data_quality or "unknown").strip().lower()
    if quality == "stale":
        notes.append("ws_data_stale")
        no_trade_reason.append("ws_data_stale")
        regime = "NO_TRADE"
        confidence = 1.0
        return _build_assessment(
            regime=regime,
            confidence=confidence,
            notes=notes,
            no_trade_reason=no_trade_reason,
        )

    if snapshot_count <= 0:
        notes.append("insufficient_snapshots")
        return _build_assessment(
            regime="NEUTRAL",
            confidence=0.1,
            notes=notes,
            no_trade_reason=no_trade_reason,
        )

    avg_accel = _safe_float(avg_price_acceleration_60s, 0.0)
    pos_ratio = _safe_float(positive_acceleration_ratio, 0.0)
    liq_rate = _safe_float(liquidation_event_rate, 0.0)

    if liq_rate >= 0.10:
        notes.append("liquidation_pulse")
        no_trade_reason.append("systemic_liquidation_pulse")
        return _build_assessment(
            regime="SYSTEMIC_RISK",
            confidence=min(1.0, 0.5 + liq_rate),
            notes=notes,
            no_trade_reason=no_trade_reason,
        )

    if avg_accel <= -0.005 and pos_ratio < 0.30:
        notes.append("broad_dump")
        return _build_assessment(
            regime="ALT_RISK_OFF",
            confidence=min(1.0, 0.4 + abs(avg_accel) * 10),
            notes=notes,
            no_trade_reason=no_trade_reason,
        )

    if avg_accel >= 0.005 and pos_ratio >= 0.55:
        notes.append("broad_rally")
        return _build_assessment(
            regime="MEME_RISK_ON",
            confidence=min(1.0, 0.5 + avg_accel * 10),
            notes=notes,
            no_trade_reason=no_trade_reason,
        )

    if avg_accel >= 0.002 and pos_ratio >= 0.40:
        notes.append("narrow_rotation")
        return _build_assessment(
            regime="SECTOR_ROTATION",
            confidence=min(1.0, 0.4 + avg_accel * 10),
            notes=notes,
            no_trade_reason=no_trade_reason,
        )

    if avg_accel >= 0.0 and pos_ratio < 0.40:
        notes.append("btc_only_lift")
        return _build_assessment(
            regime="BTC_ABSORPTION",
            confidence=0.4,
            notes=notes,
            no_trade_reason=no_trade_reason,
        )

    notes.append("indeterminate")
    return _build_assessment(
        regime="NEUTRAL",
        confidence=0.3,
        notes=notes,
        no_trade_reason=no_trade_reason,
    )


def _build_assessment(
    *,
    regime: str,
    confidence: float,
    notes: list[str],
    no_trade_reason: list[str],
) -> MarketRegimeAssessment:
    if regime not in REGIME_BUCKETS:
        regime = "NEUTRAL"
    risk_multiplier = float(DEFAULT_REGIME_RISK_MULTIPLIER.get(regime, 0.75))
    allowed_modes_raw = DEFAULT_REGIME_ALLOWED_MODES.get(regime, ())
    allowed_modes = tuple(m for m in allowed_modes_raw if m in STRATEGY_MODES)
    return MarketRegimeAssessment(
        regime_name=regime,
        confidence=max(0.0, min(1.0, float(confidence))),
        risk_multiplier=risk_multiplier,
        allowed_strategy_modes=allowed_modes,
        no_trade_reason=tuple(no_trade_reason),
        notes=tuple(notes),
    )


__all__ = [
    "DEFAULT_REGIME_ALLOWED_MODES",
    "DEFAULT_REGIME_RISK_MULTIPLIER",
    "assess_market_regime",
]
