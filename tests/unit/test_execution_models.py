"""Phase 9 - OrderRequest / FillEvent / StopEvent / OrderIntent tests."""

from __future__ import annotations

import pytest

from app.core.enums import Direction
from app.execution.models import (
    NEW_OPEN_INTENTS,
    REDUCE_ONLY_INTENTS,
    FillEvent,
    MarginMode,
    OrderIntent,
    OrderKind,
    OrderRequest,
    OrderSide,
    StopEvent,
    side_for_direction,
)


# ---------------------------------------------------------------------------
# OrderRequest validators
# ---------------------------------------------------------------------------
def _valid_request_kwargs() -> dict:
    return {
        "client_order_id": "ord_test_1",
        "symbol": "PEPEUSDT",
        "side": OrderSide.BUY,
        "qty": 1.0,
        "limit_price": 100.0,
        "intent": OrderIntent.NEW_OPEN,
        "direction": Direction.LONG,
    }


def test_order_request_round_trip_payload_is_json_safe():
    req = OrderRequest(**_valid_request_kwargs())
    payload = req.to_payload()
    import json

    assert json.dumps(payload)
    assert payload["client_order_id"] == "ord_test_1"
    assert payload["intent"] == "new_open"
    assert payload["margin_mode"] == "isolated"
    assert payload["is_new_open"] is True


def test_order_request_qty_must_be_positive():
    kwargs = _valid_request_kwargs()
    kwargs["qty"] = 0
    with pytest.raises(Exception):
        OrderRequest(**kwargs)


def test_order_request_leverage_must_be_at_least_one():
    kwargs = _valid_request_kwargs()
    kwargs["leverage"] = 0.5
    with pytest.raises(Exception):
        OrderRequest(**kwargs)


def test_order_request_margin_mode_must_be_isolated():
    """Cross margin is rejected at the model level (Spec §13.2 + §30.2)."""
    # The MarginMode enum doesn't even declare CROSS, so we cannot
    # construct one. The frozen=True / extra=forbid contract still
    # admits ISOLATED.
    req = OrderRequest(**_valid_request_kwargs())
    assert req.margin_mode is MarginMode.ISOLATED


def test_order_request_slippage_must_be_in_range():
    kwargs = _valid_request_kwargs()
    kwargs["max_slippage_pct"] = 0.0
    with pytest.raises(Exception):
        OrderRequest(**kwargs)
    kwargs["max_slippage_pct"] = 0.5
    with pytest.raises(Exception):
        OrderRequest(**kwargs)


def test_order_request_is_new_open_property_matches_intent():
    new_open = OrderRequest(**{**_valid_request_kwargs(), "intent": OrderIntent.NEW_OPEN})
    scale_in = OrderRequest(**{**_valid_request_kwargs(), "intent": OrderIntent.SCALE_IN})
    assert new_open.is_new_open is True
    assert scale_in.is_new_open is True
    for intent in (
        OrderIntent.LOCK_PROFIT,
        OrderIntent.FORCED_EXIT,
        OrderIntent.DISTRIBUTION_EXIT,
        OrderIntent.PROTECTIVE_CLOSE,
        OrderIntent.KILL_ALL,
        OrderIntent.STOP_ATTACH,
    ):
        kwargs = _valid_request_kwargs()
        kwargs["intent"] = intent
        kwargs["client_order_id"] = f"reduce_{intent.value}"
        kwargs["reduce_only"] = True
        req = OrderRequest(**kwargs)
        assert req.is_new_open is False
        assert req.is_reduce_only_intent is True


def test_intent_partition_is_complete():
    """Every intent is in exactly one of NEW_OPEN_INTENTS / REDUCE_ONLY_INTENTS."""
    assert NEW_OPEN_INTENTS.isdisjoint(REDUCE_ONLY_INTENTS)
    assert set(NEW_OPEN_INTENTS) | set(REDUCE_ONLY_INTENTS) == set(OrderIntent)


def test_order_request_frozen_and_extra_forbidden():
    req = OrderRequest(**_valid_request_kwargs())
    with pytest.raises(Exception):
        req.client_order_id = "mutated"  # frozen
    with pytest.raises(Exception):
        OrderRequest(extra_unknown_field="x", **_valid_request_kwargs())


# ---------------------------------------------------------------------------
# FillEvent
# ---------------------------------------------------------------------------
def test_fill_event_validates_qty_and_price():
    ok = FillEvent(fill_qty=0.5, fill_price=100.0, fill_id="f1")
    assert ok.fill_qty == 0.5

    with pytest.raises(Exception):
        FillEvent(fill_qty=0, fill_price=100.0, fill_id="f1")
    with pytest.raises(Exception):
        FillEvent(fill_qty=-1, fill_price=100.0, fill_id="f1")
    with pytest.raises(Exception):
        FillEvent(fill_qty=1, fill_price=0, fill_id="f1")
    with pytest.raises(Exception):
        FillEvent(fill_qty=1, fill_price=-50, fill_id="f1")


# ---------------------------------------------------------------------------
# StopEvent
# ---------------------------------------------------------------------------
def test_stop_event_must_be_reduce_only():
    """Spec §30.2 hard rule: every stop attachment must be reduce-only."""
    with pytest.raises(Exception):
        StopEvent(
            stop_order_id="s1",
            stop_price=100.0,
            side=OrderSide.SELL,
            qty=1.0,
            reduce_only=False,
        )
    ok = StopEvent(
        stop_order_id="s1",
        stop_price=100.0,
        side=OrderSide.SELL,
        qty=1.0,
        reduce_only=True,
    )
    assert ok.reduce_only is True


def test_stop_event_validates_qty_and_price():
    with pytest.raises(Exception):
        StopEvent(stop_order_id="s1", stop_price=0, side=OrderSide.SELL, qty=1.0)
    with pytest.raises(Exception):
        StopEvent(stop_order_id="s1", stop_price=100, side=OrderSide.SELL, qty=0)


# ---------------------------------------------------------------------------
# side_for_direction helper
# ---------------------------------------------------------------------------
def test_side_for_direction_long_open_is_buy():
    assert side_for_direction(Direction.LONG, is_close=False) is OrderSide.BUY


def test_side_for_direction_long_close_is_sell():
    assert side_for_direction(Direction.LONG, is_close=True) is OrderSide.SELL


def test_side_for_direction_short_open_is_sell():
    assert side_for_direction(Direction.SHORT, is_close=False) is OrderSide.SELL


def test_side_for_direction_short_close_is_buy():
    assert side_for_direction(Direction.SHORT, is_close=True) is OrderSide.BUY


def test_side_for_direction_none_raises():
    with pytest.raises(ValueError):
        side_for_direction(Direction.NONE, is_close=False)


# ---------------------------------------------------------------------------
# OrderKind / TimeInForce vocabularies
# ---------------------------------------------------------------------------
def test_order_kind_vocabulary():
    assert {k.value for k in OrderKind} == {
        "limit",
        "market",
        "stop_market",
        "stop_limit",
    }


def test_margin_mode_vocabulary_excludes_cross():
    """Cross margin is forbidden in Phase 9 - the enum must not declare it."""
    assert {m.value for m in MarginMode} == {"isolated"}
    assert "cross" not in {m.value for m in MarginMode}
