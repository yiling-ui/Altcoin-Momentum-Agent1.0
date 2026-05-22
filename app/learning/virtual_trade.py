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

    Phase 11C.1C-A optional adaptive fields (paper / virtual only;
    none of these authorise a real trade):

      - opportunity_score      weighted-sum score in ``[0.0, 100.0]``
      - opportunity_grade      ``S`` / ``A`` / ``B`` / ``C``
      - candidate_stage        ``early`` / ``mid`` / ``late`` /
                               ``blowoff`` / ``dumped``
      - strategy_mode          ``follow`` / ``pullback`` /
                               ``observe`` / ``reject``
      - cluster_id             cluster the candidate belongs to
      - cluster_leader         leader symbol for the cluster
      - label_queue_pending    True while no MFE/MAE/Tail label has
                               been computed (the Phase 11C.1C-A
                               processor is a separate, future PR)
      - follow_allowed         strategy lever: follow plan permitted
      - pullback_allowed       strategy lever: pullback plan permitted
      - observe_only           strategy lever: observe-only
      - reject_reason          why the strategy mode is ``reject``
                               (paper-only)
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

    # Phase 11C.1C-A adaptive fields. All optional + frozen-safe so
    # existing Phase 8.5 callers continue to work unchanged.
    opportunity_score: float | None = None
    opportunity_grade: str | None = None
    candidate_stage: str | None = None
    strategy_mode: str | None = None
    cluster_id: str | None = None
    cluster_leader: str | None = None
    label_queue_pending: bool | None = None
    follow_allowed: bool | None = None
    pullback_allowed: bool | None = None
    observe_only: bool | None = None
    reject_reason: str | None = None

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
        # Phase 11C.1C-A adaptive fields. ``None`` (not-set) round-trips
        # cleanly so older payloads continue to deserialise unchanged.
        "opportunity_score": (
            float(plan.opportunity_score)
            if plan.opportunity_score is not None
            else None
        ),
        "opportunity_grade": (
            str(plan.opportunity_grade)
            if plan.opportunity_grade is not None
            else None
        ),
        "candidate_stage": (
            str(plan.candidate_stage)
            if plan.candidate_stage is not None
            else None
        ),
        "strategy_mode": (
            str(plan.strategy_mode)
            if plan.strategy_mode is not None
            else None
        ),
        "cluster_id": (
            str(plan.cluster_id) if plan.cluster_id is not None else None
        ),
        "cluster_leader": (
            str(plan.cluster_leader)
            if plan.cluster_leader is not None
            else None
        ),
        "label_queue_pending": (
            bool(plan.label_queue_pending)
            if plan.label_queue_pending is not None
            else None
        ),
        "follow_allowed": (
            bool(plan.follow_allowed)
            if plan.follow_allowed is not None
            else None
        ),
        "pullback_allowed": (
            bool(plan.pullback_allowed)
            if plan.pullback_allowed is not None
            else None
        ),
        "observe_only": (
            bool(plan.observe_only)
            if plan.observe_only is not None
            else None
        ),
        "reject_reason": (
            str(plan.reject_reason)
            if plan.reject_reason is not None
            else None
        ),
    }


def payload_to_virtual_trade_plan(payload: dict[str, Any]) -> VirtualTradePlan:
    """Inverse of :func:`virtual_trade_plan_to_payload`."""
    def _opt_str(key: str) -> str | None:
        value = payload.get(key)
        return str(value) if value is not None else None

    def _opt_bool(key: str) -> bool | None:
        value = payload.get(key)
        if value is None:
            return None
        return bool(value)

    def _opt_float(key: str) -> float | None:
        value = payload.get(key)
        if value is None:
            return None
        return float(value)

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
        opportunity_score=_opt_float("opportunity_score"),
        opportunity_grade=_opt_str("opportunity_grade"),
        candidate_stage=_opt_str("candidate_stage"),
        strategy_mode=_opt_str("strategy_mode"),
        cluster_id=_opt_str("cluster_id"),
        cluster_leader=_opt_str("cluster_leader"),
        label_queue_pending=_opt_bool("label_queue_pending"),
        follow_allowed=_opt_bool("follow_allowed"),
        pullback_allowed=_opt_bool("pullback_allowed"),
        observe_only=_opt_bool("observe_only"),
        reject_reason=_opt_str("reject_reason"),
    )
