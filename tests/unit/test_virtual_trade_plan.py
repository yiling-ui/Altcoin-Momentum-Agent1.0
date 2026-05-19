"""Phase 8.5 - VirtualTradePlan contract tests (Issue #8.5)."""

from __future__ import annotations

import json

import pytest

from app.core.enums import Direction
from app.learning import (
    VirtualTradePlan,
    payload_to_virtual_trade_plan,
    virtual_trade_plan_to_payload,
)


def test_virtual_trade_plan_required_fields():
    plan = VirtualTradePlan(
        virtual_entry=100.0,
        virtual_stop=95.0,
        virtual_tp1=110.0,
        virtual_tp2=120.0,
        invalid_price=92.0,
        suggested_leverage=2.0,
        risk_budget_pct=0.005,
        direction=Direction.LONG,
        setup_type="scout_breakout",
    )
    assert plan.virtual_entry == 100.0
    assert plan.virtual_stop == 95.0
    assert plan.virtual_tp1 == 110.0
    assert plan.virtual_tp2 == 120.0
    assert plan.invalid_price == 92.0
    assert plan.suggested_leverage == 2.0
    assert plan.risk_budget_pct == 0.005
    assert plan.direction is Direction.LONG
    assert plan.setup_type == "scout_breakout"


def test_virtual_trade_plan_payload_has_all_required_fields():
    plan = VirtualTradePlan(
        virtual_entry=100.0,
        virtual_stop=95.0,
        virtual_tp1=110.0,
    )
    payload = virtual_trade_plan_to_payload(plan)
    required = {
        "virtual_entry",
        "virtual_stop",
        "virtual_tp1",
        "virtual_tp2",
        "invalid_price",
        "suggested_leverage",
        "risk_budget_pct",
        "direction",
        "setup_type",
    }
    assert required.issubset(payload.keys())


def test_virtual_trade_plan_round_trip_preserves_fields():
    original = VirtualTradePlan(
        virtual_entry=12.34,
        virtual_stop=11.0,
        virtual_tp1=15.0,
        virtual_tp2=20.0,
        invalid_price=10.0,
        suggested_leverage=3.0,
        risk_budget_pct=0.01,
        direction=Direction.SHORT,
        setup_type="attack_continuation",
        notes=("scout_promoted", "T3_confirmed"),
    )
    payload = virtual_trade_plan_to_payload(original)
    restored = payload_to_virtual_trade_plan(payload)
    assert restored == original


def test_virtual_trade_plan_round_trip_handles_optional_nones():
    original = VirtualTradePlan(
        virtual_entry=100.0,
        virtual_stop=95.0,
        virtual_tp1=110.0,
    )
    payload = virtual_trade_plan_to_payload(original)
    assert payload["virtual_tp2"] is None
    assert payload["invalid_price"] is None
    restored = payload_to_virtual_trade_plan(payload)
    assert restored == original


def test_virtual_trade_plan_payload_is_json_safe():
    plan = VirtualTradePlan(
        virtual_entry=1.0, virtual_stop=0.5, virtual_tp1=2.0,
        direction=Direction.LONG, setup_type="paper_only",
    )
    json.dumps(virtual_trade_plan_to_payload(plan), sort_keys=True)


def test_virtual_trade_plan_rejects_leverage_below_one():
    with pytest.raises(Exception):
        VirtualTradePlan(
            virtual_entry=1.0,
            virtual_stop=0.5,
            virtual_tp1=2.0,
            suggested_leverage=0.5,
        )


def test_virtual_trade_plan_rejects_risk_budget_pct_outside_unit_range():
    with pytest.raises(Exception):
        VirtualTradePlan(
            virtual_entry=1.0,
            virtual_stop=0.5,
            virtual_tp1=2.0,
            risk_budget_pct=1.5,
        )
    with pytest.raises(Exception):
        VirtualTradePlan(
            virtual_entry=1.0,
            virtual_stop=0.5,
            virtual_tp1=2.0,
            risk_budget_pct=-0.1,
        )


def test_virtual_trade_plan_is_frozen():
    plan = VirtualTradePlan(virtual_entry=1.0, virtual_stop=0.5, virtual_tp1=2.0)
    with pytest.raises((TypeError, ValueError)):
        plan.virtual_entry = 2.0  # type: ignore[misc]
