"""Phase 10B - deterministic metric helper tests (Issue #10 Part 2).

Pin the determinism rule: when the underlying data is insufficient
the metric MUST return ``MetricResult(value=None,
unknown_reasons=(UnknownReason.X,))`` and NEVER fabricate a fallback
number.
"""

from __future__ import annotations

from app.core.events import Event, EventType
from app.reflection.metrics import (
    MetricResult,
    compute_mae,
    compute_mfe,
    compute_tail_contribution,
    realized_pnl_for,
)
from app.reflection.models import UnknownReason


def _ev(event_type: EventType, payload: dict, *, ts: int = 0) -> Event:
    return Event(
        event_type=event_type,
        source_module="test",
        payload=payload,
        timestamp=ts,
    )


# ---------------------------------------------------------------------------
# MFE
# ---------------------------------------------------------------------------
def test_compute_mfe_returns_none_when_no_fill_recorded():
    result = compute_mfe([])
    assert result.value is None
    assert UnknownReason.NO_FILL_RECORDED in result.unknown_reasons


def test_compute_mfe_returns_none_when_only_one_price_landmark():
    """A single fill price is not enough to compute MFE."""
    events = [_ev(EventType.ORDER_FILLED, {"avg_fill_price": 100.0})]
    result = compute_mfe(events)
    assert result.value is None
    assert UnknownReason.INSUFFICIENT_PRICE_PATH in result.unknown_reasons


def test_compute_mfe_for_long_uses_max_minus_entry():
    """Long trade: MFE = max(prices) - entry."""
    events = [
        _ev(EventType.ORDER_FILLED, {"avg_fill_price": 100.0}),
        _ev(EventType.POSITION_OPENED, {"entry_price": 100.0}),
        _ev(EventType.POSITION_UPDATED, {"mark_price": 110.0}),
        _ev(EventType.POSITION_CLOSED, {"exit_price": 105.0}),
    ]
    result = compute_mfe(events)
    assert result.value == 10.0
    assert result.unknown_reasons == ()


def test_compute_mfe_for_short_uses_entry_minus_min():
    """Short trade: MFE = entry - min(prices)."""
    events = [
        _ev(
            EventType.ORDER_SENT,
            {"request": {"direction": "short"}, "direction": "short"},
        ),
        _ev(EventType.ORDER_FILLED, {"avg_fill_price": 100.0}),
        _ev(EventType.POSITION_OPENED, {"entry_price": 100.0}),
        _ev(EventType.POSITION_UPDATED, {"mark_price": 90.0}),
        _ev(EventType.POSITION_CLOSED, {"exit_price": 92.0}),
    ]
    result = compute_mfe(events)
    assert result.value == 10.0
    assert result.unknown_reasons == ()


def test_compute_mfe_returns_none_when_no_favourable_movement():
    """All observed prices equal entry -> insufficient price path."""
    events = [
        _ev(EventType.ORDER_FILLED, {"avg_fill_price": 100.0}),
        _ev(EventType.POSITION_OPENED, {"entry_price": 100.0}),
        _ev(EventType.POSITION_CLOSED, {"exit_price": 100.0}),
    ]
    result = compute_mfe(events)
    assert result.value is None
    assert UnknownReason.INSUFFICIENT_PRICE_PATH in result.unknown_reasons


# ---------------------------------------------------------------------------
# MAE
# ---------------------------------------------------------------------------
def test_compute_mae_returns_none_when_no_fill_recorded():
    result = compute_mae([])
    assert result.value is None
    assert UnknownReason.NO_FILL_RECORDED in result.unknown_reasons


def test_compute_mae_for_long_uses_entry_minus_min():
    events = [
        _ev(EventType.ORDER_FILLED, {"avg_fill_price": 100.0}),
        _ev(EventType.POSITION_OPENED, {"entry_price": 100.0}),
        _ev(EventType.POSITION_UPDATED, {"mark_price": 95.0}),
        _ev(EventType.POSITION_CLOSED, {"exit_price": 98.0}),
    ]
    result = compute_mae(events)
    assert result.value == 5.0
    assert result.unknown_reasons == ()


def test_compute_mae_returns_none_when_no_adverse_movement():
    events = [
        _ev(EventType.ORDER_FILLED, {"avg_fill_price": 100.0}),
        _ev(EventType.POSITION_OPENED, {"entry_price": 100.0}),
        _ev(EventType.POSITION_CLOSED, {"exit_price": 102.0}),
    ]
    result = compute_mae(events)
    assert result.value is None
    assert UnknownReason.INSUFFICIENT_PRICE_PATH in result.unknown_reasons


# ---------------------------------------------------------------------------
# tail_contribution
# ---------------------------------------------------------------------------
def test_tail_contribution_zero_when_plan_supplied_and_no_rta():
    """We can confidently say zero when no RTA was reached AND a plan
    was supplied."""
    events = [_ev(EventType.POSITION_CLOSED, {"realized_pnl": 5.0})]
    result = compute_tail_contribution(
        events=events,
        state_transitions=(("no_trade", "observe"),),
        realized_pnl=5.0,
        virtual_trade_plan={"virtual_entry": 1.0, "virtual_tp1": 1.1, "virtual_tp2": 1.2},
    )
    assert result.value == 0.0
    assert result.unknown_reasons == ()


def test_tail_contribution_unknown_when_no_plan_and_no_rta_and_no_states():
    result = compute_tail_contribution(
        events=[],
        state_transitions=(),
        realized_pnl=None,
        virtual_trade_plan=None,
    )
    assert result.value is None
    # Both reasons fire because we have nothing to lean on.
    assert UnknownReason.NO_STATE_TRANSITION_TRAIL in result.unknown_reasons
    assert UnknownReason.NO_VIRTUAL_TRADE_PLAN in result.unknown_reasons


def test_tail_contribution_uses_explicit_tail_pnl_when_rta_entered():
    events = [_ev(EventType.POSITION_CLOSED, {"realized_pnl": 100.0, "tail_pnl": 75.0})]
    result = compute_tail_contribution(
        events=events,
        state_transitions=(
            ("attack", "right_tail_amplify"),
            ("right_tail_amplify", "lock_profit"),
        ),
        realized_pnl=100.0,
        virtual_trade_plan=None,
    )
    assert result.value == 75.0
    assert result.unknown_reasons == ()


def test_tail_contribution_falls_back_to_plan_tail_contribution_when_rta_entered():
    events = [_ev(EventType.POSITION_CLOSED, {"realized_pnl": 50.0})]
    result = compute_tail_contribution(
        events=events,
        state_transitions=(("attack", "right_tail_amplify"),),
        realized_pnl=50.0,
        virtual_trade_plan={
            "virtual_entry": 1.0,
            "virtual_tp1": 1.1,
            "virtual_tp2": 1.2,
            "tail_contribution": 25.0,
        },
    )
    assert result.value == 25.0
    assert result.unknown_reasons == ()


def test_tail_contribution_unknown_when_rta_entered_and_no_plan_and_no_explicit_tail_pnl():
    events = [_ev(EventType.POSITION_CLOSED, {"realized_pnl": 10.0})]
    result = compute_tail_contribution(
        events=events,
        state_transitions=(("attack", "right_tail_amplify"),),
        realized_pnl=10.0,
        virtual_trade_plan=None,
    )
    assert result.value is None
    # Cannot infer attribution without one of the two fields.
    assert result.unknown_reasons


# ---------------------------------------------------------------------------
# realized_pnl_for
# ---------------------------------------------------------------------------
def test_realized_pnl_for_returns_none_when_no_close_event():
    assert realized_pnl_for([]) is None


def test_realized_pnl_for_reads_position_closed_payload():
    events = [_ev(EventType.POSITION_CLOSED, {"realized_pnl": 12.5})]
    assert realized_pnl_for(events) == 12.5


def test_realized_pnl_for_accepts_alternative_keys():
    events = [_ev(EventType.POSITION_CLOSED, {"realised_pnl": 4.5})]
    assert realized_pnl_for(events) == 4.5
    events2 = [_ev(EventType.POSITION_CLOSED, {"pnl": -1.2})]
    assert realized_pnl_for(events2) == -1.2


def test_metric_result_known_property_is_true_only_when_value_present_and_no_reasons():
    assert MetricResult(value=1.0, unknown_reasons=()).known is True
    assert MetricResult(value=None, unknown_reasons=()).known is False
    assert (
        MetricResult(
            value=1.0, unknown_reasons=(UnknownReason.NO_FILL_RECORDED,)
        ).known
        is False
    )


# ---------------------------------------------------------------------------
# No fabrication / no extrapolation
# ---------------------------------------------------------------------------
def test_metrics_never_fabricate_when_only_entry_landmark_exists():
    """A trade where only the entry landmark is recorded MUST yield
    None for MFE / MAE, never a fabricated zero or extrapolated value."""
    events = [
        _ev(EventType.ORDER_FILLED, {"avg_fill_price": 50.0}),
    ]
    mfe = compute_mfe(events)
    mae = compute_mae(events)
    assert mfe.value is None
    assert mae.value is None
    assert UnknownReason.INSUFFICIENT_PRICE_PATH in mfe.unknown_reasons
    assert UnknownReason.INSUFFICIENT_PRICE_PATH in mae.unknown_reasons
