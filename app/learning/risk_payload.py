"""RISK_REJECTED Learning-Ready Payload (Phase 8.5).

Issue contract: every ``RISK_REJECTED`` event must be able to carry

    - opportunity_id
    - reject_reasons
    - account_life_tier
    - regime
    - universe_eligible
    - liquidity_state
    - trade_confirmation_level
    - manipulation_level
    - capital_state_version
    - risk_config_version

Phase 8.5 ships this as a frozen value object that the Risk Engine
attaches via :func:`app.learning.context.attach_learning_ready` to
the audit payload. The legacy Phase 1 / Phase 6 / Phase 7 audit
fields are preserved unchanged; the new fields land in the
``learning_ready.risk_decision`` sub-block, so existing tests do
not see breaking changes.
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AccountLifeTier,
    ManipulationLevel,
    MarketRegime,
    TradeConfirmationLevel,
)


class RiskRejectedLearningPayload(BaseModel):
    """Learning-ready enrichment for a RISK_APPROVED / RISK_REJECTED event.

    The class supports BOTH outcomes despite its historical name -
    Reflection (Issue #10) will read approved decisions to learn
    *why an attack succeeded*, not just why it was refused.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str | None = None
    reject_reasons: tuple[str, ...] = Field(default_factory=tuple)
    account_life_tier: AccountLifeTier | None = None
    regime: MarketRegime | None = None
    universe_eligible: bool | None = None
    # Liquidity state is a free-form short label (e.g. "passed",
    # "rejected", "no_exit_channel") so we don't import the Phase 5
    # LiquidityRejectReason enum just for serialisation.
    liquidity_state: str | None = None
    trade_confirmation_level: TradeConfirmationLevel | None = None
    manipulation_level: ManipulationLevel | None = None
    capital_state_version: str | None = None
    risk_config_version: str | None = None
    # Phase 7 hooks already on the engine; carrying them lets
    # Reflection group on (regime, tier, breaker_state) without
    # re-deriving them from the un-typed audit dict.
    daily_loss_breaker_state: str | None = None
    consecutive_loss_breaker_state: str | None = None
    is_new_open: bool | None = None
    attack_intent: bool | None = None

    def to_payload(self) -> dict[str, Any]:
        return risk_rejected_to_payload(self)


def risk_rejected_to_payload(
    payload: RiskRejectedLearningPayload,
) -> dict[str, Any]:
    """Return a JSON-safe dict (enum values rendered as strings)."""
    return {
        "opportunity_id": payload.opportunity_id,
        "reject_reasons": list(payload.reject_reasons),
        "account_life_tier": (
            payload.account_life_tier.value
            if payload.account_life_tier is not None
            else None
        ),
        "regime": (
            payload.regime.value if payload.regime is not None else None
        ),
        "universe_eligible": payload.universe_eligible,
        "liquidity_state": payload.liquidity_state,
        "trade_confirmation_level": (
            payload.trade_confirmation_level.value
            if payload.trade_confirmation_level is not None
            else None
        ),
        "manipulation_level": (
            payload.manipulation_level.value
            if payload.manipulation_level is not None
            else None
        ),
        "capital_state_version": payload.capital_state_version,
        "risk_config_version": payload.risk_config_version,
        "daily_loss_breaker_state": payload.daily_loss_breaker_state,
        "consecutive_loss_breaker_state": payload.consecutive_loss_breaker_state,
        "is_new_open": payload.is_new_open,
        "attack_intent": payload.attack_intent,
    }


def reject_reasons_as_strings(reasons: Iterable[Any]) -> tuple[str, ...]:
    """Normalise an iterable of typed ``RiskRejectReason`` / strings to
    a tuple of strings. Used by the Risk Engine when constructing
    a :class:`RiskRejectedLearningPayload` from the legacy reasons
    list."""
    out: list[str] = []
    for reason in reasons:
        if reason is None:
            continue
        value = getattr(reason, "value", None)
        out.append(str(value) if value is not None else str(reason))
    return tuple(out)
