"""VirtualTradePlan contract (Phase 8.5).

A ``VirtualTradePlan`` records the *paper-mode hypothetical trade
plan* attached to a candidate the Risk Engine has evaluated. Even
when the engine refuses the trade, the plan is preserved so future
MFE/MAE labelling, Tail labelling, Reflection, and Dataset Builder
can answer "what would have happened if we had taken it".

Phase 8.5 boundary
------------------

A ``VirtualTradePlan`` is **purely descriptive**:

  - It does NOT trigger any order, ever.
  - It does NOT bypass the Risk Engine.
  - It does NOT mutate ``CapitalState`` or any position.
  - It does NOT open a socket, call an exchange, or invoke an LLM.

The plan is intended to be saved on a candidate and replayed later;
it is NOT an authorisation to trade.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import Direction


class VirtualTradePlan(BaseModel):
    """Hypothetical trade plan for replay / labelling.

    Required Issue contract fields:

      - virtual_entry      planned entry price
      - virtual_stop       planned protective stop price
      - virtual_tp1        first take-profit
      - virtual_tp2        second take-profit
      - invalid_price      level at which the setup is invalidated
      - suggested_leverage planned leverage (>= 1.0)
      - risk_budget_pct    fraction of risk budget allocated (0..1)
      - direction          long | short | none
      - setup_type         free-form short tag (e.g. "scout_breakout",
                           "attack_continuation", "right_tail_amplify")

    Phase 8.5 enforces:

      - leverage >= 1.0
      - 0 <= risk_budget_pct <= 1.0
      - direction is a typed Direction enum
      - all price fields are floats (callers may pass ``None`` for
        TP2 / invalid_price when the plan is asymmetric)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    virtual_entry: float
    virtual_stop: float
    virtual_tp1: float
    virtual_tp2: float | None = None
    invalid_price: float | None = None
    suggested_leverage: float = 1.0
    risk_budget_pct: float = 0.0
    direction: Direction = Direction.NONE
    setup_type: str = "unknown"
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("suggested_leverage")
    @classmethod
    def _check_leverage(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError(f"suggested_leverage must be >= 1.0; got {value}")
        return float(value)

    @field_validator("risk_budget_pct")
    @classmethod
    def _check_risk_budget(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(
                f"risk_budget_pct must be in [0.0, 1.0]; got {value}"
            )
        return float(value)

    def to_payload(self) -> dict[str, Any]:
        return virtual_trade_plan_to_payload(self)


def virtual_trade_plan_to_payload(plan: VirtualTradePlan) -> dict[str, Any]:
    """Return a JSON-safe dict suitable for event payloads."""
    return {
        "virtual_entry": float(plan.virtual_entry),
        "virtual_stop": float(plan.virtual_stop),
        "virtual_tp1": float(plan.virtual_tp1),
        "virtual_tp2": (
            float(plan.virtual_tp2) if plan.virtual_tp2 is not None else None
        ),
        "invalid_price": (
            float(plan.invalid_price) if plan.invalid_price is not None else None
        ),
        "suggested_leverage": float(plan.suggested_leverage),
        "risk_budget_pct": float(plan.risk_budget_pct),
        "direction": plan.direction.value,
        "setup_type": str(plan.setup_type),
        "notes": list(plan.notes),
    }


def payload_to_virtual_trade_plan(payload: dict[str, Any]) -> VirtualTradePlan:
    """Inverse of :func:`virtual_trade_plan_to_payload`."""
    return VirtualTradePlan(
        virtual_entry=float(payload["virtual_entry"]),
        virtual_stop=float(payload["virtual_stop"]),
        virtual_tp1=float(payload["virtual_tp1"]),
        virtual_tp2=(
            float(payload["virtual_tp2"])
            if payload.get("virtual_tp2") is not None
            else None
        ),
        invalid_price=(
            float(payload["invalid_price"])
            if payload.get("invalid_price") is not None
            else None
        ),
        suggested_leverage=float(payload.get("suggested_leverage", 1.0) or 1.0),
        risk_budget_pct=float(payload.get("risk_budget_pct", 0.0) or 0.0),
        direction=Direction(payload.get("direction", Direction.NONE.value)),
        setup_type=str(payload.get("setup_type", "unknown")),
        notes=tuple(str(n) for n in payload.get("notes", []) or []),
    )
