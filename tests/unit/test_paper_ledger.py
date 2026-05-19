"""Phase 9 - PaperLedger tests."""

from __future__ import annotations

import pytest

from app.core.enums import Direction
from app.execution.models import OrderIntent, OrderKind, OrderRequest, OrderSide
from app.execution.paper_ledger import (
    PaperLedger,
    PaperPosition,
    PaperStop,
)


def _request(client_order_id: str = "ord_1") -> OrderRequest:
    return OrderRequest(
        client_order_id=client_order_id,
        symbol="PEPEUSDT",
        side=OrderSide.BUY,
        kind=OrderKind.LIMIT,
        qty=1.0,
        limit_price=100.0,
        intent=OrderIntent.NEW_OPEN,
        direction=Direction.LONG,
        opportunity_id="opp_1",
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def test_record_order_appends_to_open_orders():
    ledger = PaperLedger()
    order = ledger.record_order(request=_request(), exchange_order_id="exch_1")
    assert order.client_order_id == "ord_1"
    assert ledger.orders_recorded == 1
    assert len(ledger.open_orders) == 1
    assert ledger.get_order("ord_1") is order


def test_apply_partial_fill_clamps_to_qty():
    ledger = PaperLedger()
    ledger.record_order(request=_request(), exchange_order_id="exch_1")
    ledger.apply_partial_fill(client_order_id="ord_1", fill_qty=0.4)
    assert ledger.get_order("ord_1").filled_qty == pytest.approx(0.4)
    ledger.apply_partial_fill(client_order_id="ord_1", fill_qty=0.7)  # would push over
    assert ledger.get_order("ord_1").filled_qty == pytest.approx(1.0)


def test_apply_partial_fill_unknown_id_raises():
    ledger = PaperLedger()
    with pytest.raises(KeyError):
        ledger.apply_partial_fill(client_order_id="nope", fill_qty=1)


def test_close_order_removes_from_open_orders():
    ledger = PaperLedger()
    ledger.record_order(request=_request(), exchange_order_id="exch_1")
    closed = ledger.close_order("ord_1")
    assert closed is not None
    assert ledger.get_order("ord_1") is None
    # idempotent
    assert ledger.close_order("ord_1") is None


# ---------------------------------------------------------------------------
# Stops
# ---------------------------------------------------------------------------
def test_record_stop_and_query_by_position():
    ledger = PaperLedger()
    s = PaperStop(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        qty=1.0,
        stop_price=98.0,
        reduce_only=True,
        timestamp=1,
    )
    ledger.record_stop(s)
    assert ledger.stops_recorded == 1
    assert ledger.stops_for_position("pos_1") == (s,)
    assert ledger.get_stop("stop_1") is s


def test_remove_stop_drops_it():
    ledger = PaperLedger()
    s = PaperStop(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        qty=1.0,
        stop_price=98.0,
        reduce_only=True,
        timestamp=1,
    )
    ledger.record_stop(s)
    ledger.remove_stop("stop_1")
    assert ledger.get_stop("stop_1") is None


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------
def test_open_position_and_lookup_by_symbol():
    ledger = PaperLedger()
    pos = PaperPosition(
        position_id="pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=1.0,
        entry_price=100.0,
    )
    ledger.open_position(pos)
    assert ledger.positions_opened == 1
    assert ledger.position_for_symbol("PEPEUSDT") is pos


def test_close_position_also_removes_attached_stops():
    ledger = PaperLedger()
    pos = PaperPosition(
        position_id="pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=1.0,
        entry_price=100.0,
    )
    ledger.open_position(pos)
    s = PaperStop(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        qty=1.0,
        stop_price=98.0,
        reduce_only=True,
        timestamp=1,
    )
    ledger.record_stop(s)

    ledger.close_position("pos_1")
    assert ledger.positions_closed == 1
    assert ledger.position_for_symbol("PEPEUSDT") is None
    assert ledger.get_stop("stop_1") is None  # auto-removed


def test_confirm_position_stop_updates_position():
    ledger = PaperLedger()
    pos = PaperPosition(
        position_id="pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=1.0,
        entry_price=100.0,
    )
    ledger.open_position(pos)
    updated = ledger.confirm_position_stop(position_id="pos_1", stop_price=98.0)
    assert updated.stop_price == 98.0
    assert updated.stop_confirmed is True


def test_confirm_position_stop_unknown_position_raises():
    ledger = PaperLedger()
    with pytest.raises(KeyError):
        ledger.confirm_position_stop(position_id="missing", stop_price=98.0)


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------
def test_set_equity_updates_snapshot():
    ledger = PaperLedger(initial_equity=100.0)
    assert ledger.equity.total_equity == 100.0
    ledger.set_equity(200.0, timestamp=42)
    assert ledger.equity.total_equity == 200.0
    assert ledger.equity.timestamp == 42
