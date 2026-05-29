"""Unit tests for Phase 11C.1D-D-D / PR97 / MockExchange +
Pessimistic Fill Model v0.

These tests are the safety contract for this PR. If any of them fails
the module is not safe to merge.

Hard safety boundary covered by these tests:

  - mode = paper
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - signed_endpoint_reachable = False
  - private_websocket_reachable = False
  - account_endpoint_reachable = False
  - order_endpoint_reachable = False
  - position_endpoint_reachable = False
  - leverage_endpoint_reachable = False
  - margin_endpoint_reachable = False
  - real_exchange_order_path = False
  - real_capital = False
  - telegram_outbound_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

The tests also assert that the new modules:

  - do NOT import app.risk / app.execution / app.exchanges /
    app.telegram / app.config
  - do NOT pull any DeepSeek / LLM / Telegram / Binance / network
    transport
  - emit no forbidden trade / runtime-config / "live ready" field
  - emit no real exchange order id / api key / api secret /
    signed-endpoint reference
  - are deterministic
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Mapping

import pytest

from app.sim import (
    FORBIDDEN_OUTPUT_FIELDS,
    MOCK_EXCHANGE_PHASE_NAME,
    PESSIMISTIC_FILL_MODEL_PHASE_NAME,
    AmbiguousIntrabarPolicy,
    ConservativeAssumption,
    FillModelDecision,
    FillReason,
    HistoricalKlineRecord,
    HistoricalMarketStore,
    LimitTouchFillPolicy,
    MockExchange,
    MockExchangeConfig,
    MockExchangeDiagnostics,
    MockFill,
    MockOrder,
    MockOrderSide,
    MockOrderStatus,
    MockOrderType,
    OrderRequest,
    PessimisticFillModel,
    ReplayFeedBatch,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
    SimulationClock,
    assert_no_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _walk_keys(payload: Any):
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


def _walk_strings(payload: Any):
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            if isinstance(k, str):
                yield k
            yield from _walk_strings(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_strings(v)
    elif isinstance(payload, str):
        yield payload


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_imported_modules(source_text: str) -> set:
    tree = ast.parse(source_text)
    mods: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def _collect_code_identifiers(source_text: str) -> set:
    tree = ast.parse(source_text)
    out: set = set()

    def attr_chain(n):
        parts: List[str] = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            chain = attr_chain(node)
            if chain:
                out.add(chain)
    return out


def _make_kline(
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    open_time: datetime = None,
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
    volume: float = 50.0,
    available_at: datetime = None,
    record_id: str = None,
) -> HistoricalKlineRecord:
    if open_time is None:
        open_time = _T0
    seconds = 60 if interval == "1m" else 300
    if available_at is None:
        available_at = open_time + timedelta(seconds=seconds)
    return HistoricalKlineRecord(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        available_at=available_at,
        record_id=record_id,
        source="binance_public",
    )


def _make_provider(
    *,
    store: HistoricalMarketStore,
    start_time: datetime = None,
    end_time: datetime = None,
    step_interval: timedelta = None,
) -> ReplayFeedProvider:
    if start_time is None:
        start_time = _T0
    if end_time is None:
        end_time = _T0 + timedelta(minutes=30)
    if step_interval is None:
        step_interval = timedelta(minutes=1)
    clock = SimulationClock(
        start_time_utc=start_time,
        end_time_utc=end_time,
        monotonic_forward_only=True,
    )
    config = ReplayFeedProviderConfig(
        start_time=start_time,
        end_time=end_time,
        step_interval=step_interval,
    )
    return ReplayFeedProvider(store=store, clock=clock, config=config)


def _build_batch_with_kline(
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    open_time: datetime = None,
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
    volume: float = 50.0,
    record_id: str = "k0",
) -> ReplayFeedBatch:
    """Build a ReplayFeedBatch containing a single visible kline."""
    if open_time is None:
        open_time = _T0
    store = HistoricalMarketStore()
    store.add_record(
        _make_kline(
            symbol=symbol,
            interval=interval,
            open_time=open_time,
            open_=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            record_id=record_id,
        )
    )
    seconds = 60 if interval == "1m" else 300
    end_time = open_time + timedelta(seconds=seconds * 5)
    provider = _make_provider(
        store=store,
        start_time=open_time,
        end_time=end_time,
        step_interval=timedelta(seconds=seconds),
    )
    return provider.next_batch()


def _empty_batch(simulated_time: datetime = None) -> ReplayFeedBatch:
    if simulated_time is None:
        simulated_time = _T0 + timedelta(minutes=1)
    return ReplayFeedBatch(
        batch_id="batch_test_empty",
        simulated_time=simulated_time,
    )


# ---------------------------------------------------------------------------
# 1. market order fills with visible price + taker fee + slippage
# ---------------------------------------------------------------------------


def test_market_order_fills_with_visible_price_taker_fee_slippage():
    batch = _build_batch_with_kline(
        symbol="BTCUSDT",
        open_time=_T0,
        close=100.0,
        high=110.0,
        low=90.0,
    )
    cfg = MockExchangeConfig(
        taker_fee_bps=4.0,
        default_slippage_bps=5.0,
        latency_penalty_bps=2.0,
    )
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=2.0,
        ),
        replay_batch=batch,
    )
    assert order.status == MockOrderStatus.FILLED
    fills = mx.list_fills()
    assert len(fills) == 1
    f = fills[0]
    # Reference price is the kline close (100.0). Total adverse bps =
    # slippage 5 + latency 2 = 7 bps = 0.0007. BUY fill price > ref.
    assert f.reference_price == 100.0
    assert f.fill_price == pytest.approx(100.0 * (1.0 + 0.0007))
    assert f.fee > 0.0
    # Fee is taker_fee on full filled notional.
    expected_fee = f.fill_price * f.filled_qty * 0.0004
    assert f.fee == pytest.approx(expected_fee)
    assert f.slippage_bps == 5.0
    assert f.latency_bps == 2.0
    assert f.fill_reason == FillReason.MARKET_FILL
    assert ConservativeAssumption.TAKER_FEE_APPLIED in (
        f.conservative_assumption
    )
    assert ConservativeAssumption.SLIPPAGE_APPLIED in (
        f.conservative_assumption
    )
    assert ConservativeAssumption.LATENCY_PENALTY_APPLIED in (
        f.conservative_assumption
    )
    # SELL market: fill price BELOW reference.
    mx2 = MockExchange(config=cfg)
    order2 = mx2.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    assert order2.status == MockOrderStatus.FILLED
    f2 = mx2.list_fills()[0]
    assert f2.fill_price == pytest.approx(100.0 * (1.0 - 0.0007))
    assert f2.fill_price < 100.0


# ---------------------------------------------------------------------------
# 2. market order rejects / stale when no visible price
# ---------------------------------------------------------------------------


def test_market_order_rejects_or_stale_when_no_visible_price():
    cfg = MockExchangeConfig(stale_after_seconds=300.0)
    mx = MockExchange(config=cfg)
    # Empty batch -> no visible kline -> immediate REJECTED (the
    # order has just been created so age < stale_after_seconds).
    empty = _empty_batch(_T0 + timedelta(minutes=1))
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=empty,
    )
    assert order.status == MockOrderStatus.REJECTED
    assert mx.list_fills() == []
    # Old, never-filled order on a still-empty batch -> STALE.
    mx2 = MockExchange(config=cfg)
    # Submit at T0 with no batch (so it stays ACCEPTED at T0).
    order2 = mx2.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        simulated_time=_T0,
    )
    assert order2.status == MockOrderStatus.ACCEPTED
    # Now process a much-later batch with no visible kline (different
    # symbol). Order age >> stale_after_seconds -> STALE.
    far_empty = _empty_batch(_T0 + timedelta(seconds=400))
    mx2.process_batch(far_empty)
    assert order2.status == MockOrderStatus.STALE
    assert mx2.list_fills() == []
    # Verify no live side effects (no real exchange fields anywhere).
    bd = order2.to_dict()
    assert bd["live_trading"] is False
    assert bd["exchange_live_orders"] is False
    assert bd["binance_private_api_enabled"] is False
    assert bd["no_live_order"] is True


# ---------------------------------------------------------------------------
# 3. limit order does not fill on touch by default
# ---------------------------------------------------------------------------


def test_limit_order_does_not_fill_on_touch_by_default():
    # BUY limit at 95. Kline low touches 95 exactly -> no fill under
    # NO_FILL_ON_TOUCH (the conservative default).
    batch = _build_batch_with_kline(
        symbol="BTCUSDT", high=110.0, low=95.0, close=100.0
    )
    cfg = MockExchangeConfig()
    assert cfg.limit_touch_fill_policy == (
        LimitTouchFillPolicy.NO_FILL_ON_TOUCH
    )
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.LIMIT,
            requested_qty=1.0,
            limit_price=95.0,
        ),
        replay_batch=batch,
    )
    assert order.status == MockOrderStatus.ACCEPTED
    assert mx.list_fills() == []
    # SELL limit at 110 with kline high touching exactly 110 -> no fill.
    mx_sell = MockExchange(config=cfg)
    order_sell = mx_sell.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.LIMIT,
            requested_qty=1.0,
            limit_price=110.0,
        ),
        replay_batch=batch,
    )
    assert order_sell.status == MockOrderStatus.ACCEPTED
    assert mx_sell.list_fills() == []


# ---------------------------------------------------------------------------
# 4. limit order can fill only when price penetrates beyond limit
# ---------------------------------------------------------------------------


def test_limit_order_fills_only_when_price_penetrates_beyond_limit():
    # BUY limit at 95. Kline low penetrates BELOW 95 -> fill at limit.
    batch_pen = _build_batch_with_kline(
        symbol="BTCUSDT", high=110.0, low=94.0, close=100.0
    )
    cfg = MockExchangeConfig(
        taker_fee_bps=4.0,
        maker_fee_bps=2.0,
        default_slippage_bps=5.0,
        latency_penalty_bps=0.0,
    )
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.LIMIT,
            requested_qty=1.0,
            limit_price=95.0,
        ),
        replay_batch=batch_pen,
    )
    assert order.status == MockOrderStatus.FILLED
    fills = mx.list_fills()
    assert len(fills) == 1
    f = fills[0]
    assert f.fill_reason == FillReason.LIMIT_FILL_ON_PENETRATION
    # Conservative rule: fill at the limit price (best-case for the
    # resting order; with no latency penalty the fill price equals
    # the limit).
    assert f.fill_price == 95.0
    assert ConservativeAssumption.LIMIT_PENETRATION_REQUIRED in (
        f.conservative_assumption
    )
    # Fee is the maker fee (limit orders rest in the book).
    expected_fee = f.fill_price * f.filled_qty * 0.0002
    assert f.fee == pytest.approx(expected_fee)


# ---------------------------------------------------------------------------
# 5. stop market fills at adverse price with fee/slippage
# ---------------------------------------------------------------------------


def test_stop_market_fills_at_adverse_price_with_fee_and_slippage():
    # SELL stop at 95 (closing a long). Kline low <= 95 -> triggered.
    # Adverse fill: price BELOW the stop level by slippage + latency.
    batch = _build_batch_with_kline(
        symbol="BTCUSDT", high=110.0, low=94.5, close=100.0
    )
    cfg = MockExchangeConfig(
        taker_fee_bps=4.0,
        default_slippage_bps=5.0,
        latency_penalty_bps=0.0,
    )
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.STOP_MARKET,
            requested_qty=1.0,
            stop_price=95.0,
        ),
        replay_batch=batch,
    )
    assert order.status == MockOrderStatus.FILLED
    f = mx.list_fills()[0]
    assert f.fill_reason == FillReason.STOP_TRIGGERED_FILL
    # Adverse SELL fill: stop_price * (1 - 5bps) = 95.0 * 0.9995.
    assert f.fill_price == pytest.approx(95.0 * 0.9995)
    assert f.fill_price < 95.0
    assert ConservativeAssumption.STOP_ADVERSE_FILL in (
        f.conservative_assumption
    )
    assert ConservativeAssumption.SLIPPAGE_APPLIED in (
        f.conservative_assumption
    )
    assert ConservativeAssumption.TAKER_FEE_APPLIED in (
        f.conservative_assumption
    )
    # BUY stop at 105 (covering a short). Kline high >= 105 -> triggered.
    # Adverse fill: price ABOVE stop by slippage.
    batch2 = _build_batch_with_kline(
        symbol="BTCUSDT", high=106.0, low=95.0, close=100.0
    )
    mx2 = MockExchange(config=cfg)
    order2 = mx2.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.STOP_MARKET,
            requested_qty=1.0,
            stop_price=105.0,
        ),
        replay_batch=batch2,
    )
    assert order2.status == MockOrderStatus.FILLED
    f2 = mx2.list_fills()[0]
    assert f2.fill_price == pytest.approx(105.0 * 1.0005)
    assert f2.fill_price > 105.0


# ---------------------------------------------------------------------------
# 6. take profit + stop same candle -> worst-case when policy=WORST_CASE
# ---------------------------------------------------------------------------


def test_take_profit_and_stop_same_candle_worst_case_policy():
    # Long position: stop SELL at 95 (low <=95 triggers), TP SELL at
    # 110 (high >=110 triggers). Kline range [94, 111] covers both.
    batch = _build_batch_with_kline(
        symbol="BTCUSDT", high=111.0, low=94.0, close=100.0
    )
    cfg = MockExchangeConfig(
        ambiguous_intrabar_policy=AmbiguousIntrabarPolicy.WORST_CASE,
        default_slippage_bps=5.0,
        latency_penalty_bps=0.0,
    )
    mx = MockExchange(config=cfg)
    stop = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.STOP_MARKET,
            requested_qty=1.0,
            stop_price=95.0,
        ),
        simulated_time=_T0,
    )
    tp = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.TAKE_PROFIT_MARKET,
            requested_qty=1.0,
            stop_price=110.0,
            pair_with_order_id=stop.order_id,
        ),
        simulated_time=_T0,
    )
    fills = mx.process_batch(batch)
    # Under WORST_CASE: the stop fires (worst-case for the long), and
    # the TP is canceled.
    stop_after = mx.get_order(stop.order_id)
    tp_after = mx.get_order(tp.order_id)
    assert stop_after.status == MockOrderStatus.FILLED
    assert tp_after.status == MockOrderStatus.CANCELED
    assert len(fills) == 1
    assert fills[0].fill_reason == (
        FillReason.AMBIGUOUS_WORST_CASE_STOP_FILL
    )
    assert ConservativeAssumption.AMBIGUOUS_INTRABAR_WORST_CASE in (
        fills[0].conservative_assumption
    )


# ---------------------------------------------------------------------------
# 7. take profit + stop same candle -> AMBIGUOUS_INTRABAR_PATH when
#    policy=AMBIGUOUS
# ---------------------------------------------------------------------------


def test_take_profit_and_stop_same_candle_ambiguous_policy():
    batch = _build_batch_with_kline(
        symbol="BTCUSDT", high=111.0, low=94.0, close=100.0
    )
    cfg = MockExchangeConfig(
        ambiguous_intrabar_policy=AmbiguousIntrabarPolicy.AMBIGUOUS,
    )
    mx = MockExchange(config=cfg)
    stop = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.STOP_MARKET,
            requested_qty=1.0,
            stop_price=95.0,
        ),
        simulated_time=_T0,
    )
    tp = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.TAKE_PROFIT_MARKET,
            requested_qty=1.0,
            stop_price=110.0,
            pair_with_order_id=stop.order_id,
        ),
        simulated_time=_T0,
    )
    fills = mx.process_batch(batch)
    stop_after = mx.get_order(stop.order_id)
    tp_after = mx.get_order(tp.order_id)
    assert stop_after.status == MockOrderStatus.AMBIGUOUS_INTRABAR_PATH
    assert tp_after.status == MockOrderStatus.AMBIGUOUS_INTRABAR_PATH
    assert fills == []


# ---------------------------------------------------------------------------
# 8. forced exit uses conservative market fill
# ---------------------------------------------------------------------------


def test_forced_exit_uses_conservative_market_fill():
    batch = _build_batch_with_kline(
        symbol="BTCUSDT", high=110.0, low=90.0, close=100.0
    )
    cfg = MockExchangeConfig(
        taker_fee_bps=4.0,
        default_slippage_bps=5.0,
        latency_penalty_bps=2.0,
    )
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.SELL,
            order_type=MockOrderType.FORCED_EXIT,
            requested_qty=1.5,
        ),
        replay_batch=batch,
    )
    assert order.status == MockOrderStatus.FILLED
    f = mx.list_fills()[0]
    assert f.fill_reason == FillReason.FORCED_EXIT_FILL
    # Adverse SELL fill: close * (1 - 7bps).
    assert f.fill_price == pytest.approx(100.0 * (1.0 - 0.0007))
    assert ConservativeAssumption.FORCED_EXIT_CONSERVATIVE_FILL in (
        f.conservative_assumption
    )
    assert ConservativeAssumption.TAKER_FEE_APPLIED in (
        f.conservative_assumption
    )


# ---------------------------------------------------------------------------
# 9. partial fill supported if max_fill_fraction_per_batch configured
# ---------------------------------------------------------------------------


def test_partial_fill_supported_with_max_fill_fraction():
    cfg = MockExchangeConfig(
        partial_fill_enabled=True,
        max_fill_fraction_per_batch=0.5,
    )
    batch1 = _build_batch_with_kline(
        symbol="BTCUSDT", close=100.0, open_time=_T0
    )
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=4.0,
        ),
        replay_batch=batch1,
    )
    # First batch fills 50% -> 2.0 of 4.0 -> PARTIALLY_FILLED.
    assert order.status == MockOrderStatus.PARTIALLY_FILLED
    f1 = mx.list_fills()[0]
    assert f1.filled_qty == 2.0
    assert ConservativeAssumption.PARTIAL_FILL in (
        f1.conservative_assumption
    )
    # Process a second batch -> fills another 50% of the original
    # qty (2.0 of remaining 2.0) -> FILLED.
    batch2 = _build_batch_with_kline(
        symbol="BTCUSDT",
        close=100.0,
        open_time=_T0 + timedelta(minutes=1),
        record_id="k1",
    )
    mx.process_batch(batch2)
    order_final = mx.get_order(order.order_id)
    assert order_final.status == MockOrderStatus.FILLED
    fills = mx.list_fills()
    assert len(fills) == 2
    # The second fill is NOT marked PARTIAL_FILL because it completes.
    assert ConservativeAssumption.PARTIAL_FILL not in (
        fills[1].conservative_assumption
    )
    assert sum(f.filled_qty for f in fills) == 4.0


# ---------------------------------------------------------------------------
# 10. cancel order changes status without live side effects
# ---------------------------------------------------------------------------


def test_cancel_order_changes_status_without_live_side_effects():
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.LIMIT,
            requested_qty=1.0,
            limit_price=50.0,
        ),
        simulated_time=_T0,
    )
    assert order.status == MockOrderStatus.ACCEPTED
    canceled = mx.cancel_order(order.order_id, _T0 + timedelta(seconds=30))
    assert canceled.status == MockOrderStatus.CANCELED
    # No fills, no diagnostics noise.
    assert mx.list_fills() == []
    assert mx.diagnostics.fills_count == 0
    assert mx.diagnostics.orders_canceled_count == 1
    # No real exchange side effects on the dict.
    d = canceled.to_dict()
    assert d["no_live_order"] is True
    assert d["simulated_only"] is True
    assert d["live_trading"] is False
    # Idempotent on terminal orders.
    again = mx.cancel_order(order.order_id, _T0 + timedelta(seconds=60))
    assert again.status == MockOrderStatus.CANCELED
    assert mx.diagnostics.orders_canceled_count == 1
    # Cancel of unknown order_id raises.
    with pytest.raises(KeyError):
        mx.cancel_order("does_not_exist", _T0)


# ---------------------------------------------------------------------------
# 11. stale order scenario supported
# ---------------------------------------------------------------------------


def test_stale_order_scenario_supported():
    cfg = MockExchangeConfig(stale_after_seconds=120.0)
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        simulated_time=_T0,
    )
    # Process a batch much later with no visible kline for the symbol.
    far_empty = _empty_batch(_T0 + timedelta(seconds=600))
    mx.process_batch(far_empty)
    assert mx.get_order(order.order_id).status == MockOrderStatus.STALE
    assert mx.diagnostics.orders_stale_count == 1


# ---------------------------------------------------------------------------
# 12. rejected order scenario supported
# ---------------------------------------------------------------------------


def test_rejected_order_scenario_supported():
    cfg = MockExchangeConfig(stale_after_seconds=300.0)
    mx = MockExchange(config=cfg)
    # Empty batch right at submit time -> REJECTED.
    empty = _empty_batch(_T0)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=empty,
    )
    assert order.status == MockOrderStatus.REJECTED
    assert mx.diagnostics.orders_rejected_count == 1
    # MockOrder construction with bad input raises (no live side
    # effects either).
    with pytest.raises(ValueError):
        MockOrder(
            order_id="x",
            symbol="BTCUSDT",
            side="UPSIDE_DOWN",  # not in closed taxonomy
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
            created_at_simulated=_T0,
        )


# ---------------------------------------------------------------------------
# 13. deterministic output from same replay batch / config / order
# ---------------------------------------------------------------------------


def test_deterministic_output_from_same_batch_config_order():
    def _drive():
        batch = _build_batch_with_kline(
            symbol="BTCUSDT", close=100.0
        )
        cfg = MockExchangeConfig(
            taker_fee_bps=4.0,
            default_slippage_bps=5.0,
            latency_penalty_bps=1.5,
        )
        mx = MockExchange(config=cfg)
        for side in (MockOrderSide.BUY, MockOrderSide.SELL):
            mx.submit_order(
                OrderRequest(
                    symbol="BTCUSDT",
                    side=side,
                    order_type=MockOrderType.MARKET,
                    requested_qty=1.0,
                ),
                replay_batch=batch,
            )
        return [
            o.to_dict() for o in mx.list_all_orders()
        ], [f.to_dict() for f in mx.list_fills()]

    out_a = _drive()
    out_b = _drive()
    assert out_a == out_b


# ---------------------------------------------------------------------------
# 14. all outputs JSON serializable
# ---------------------------------------------------------------------------


def test_all_outputs_are_json_serializable():
    batch = _build_batch_with_kline()
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    f = mx.list_fills()[0]
    payloads = [
        cfg.to_dict(),
        order.to_dict(),
        f.to_dict(),
        mx.to_dict(),
        mx.safety_payload(),
        mx.diagnostics.to_dict(),
        mx.fill_model.safety_payload(),
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ).to_dict(),
        FillModelDecision().to_dict(),
    ]
    for p in payloads:
        text = json.dumps(p, sort_keys=True)
        round_tripped = json.loads(text)
        assert isinstance(round_tripped, dict)
        assert round_tripped["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 15. simulated_only=True / no_live_order=True
# ---------------------------------------------------------------------------


def test_simulated_only_and_no_live_order_on_every_payload():
    batch = _build_batch_with_kline()
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    assert mx.simulated_only is True
    assert mx.no_live_order is True
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    f = mx.list_fills()[0]
    for d in (
        order.to_dict(),
        f.to_dict(),
        cfg.to_dict(),
        mx.to_dict(),
        mx.safety_payload(),
        mx.diagnostics.to_dict(),
        mx.fill_model.safety_payload(),
    ):
        assert d["simulated_only"] is True
        assert d["no_live_order"] is True


# ---------------------------------------------------------------------------
# 16. phase_12_forbidden=True
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_in_every_payload():
    batch = _build_batch_with_kline()
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    assert mx.phase_12_forbidden is True
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    f = mx.list_fills()[0]
    for d in (
        order.to_dict(),
        f.to_dict(),
        cfg.to_dict(),
        mx.to_dict(),
        mx.safety_payload(),
        mx.diagnostics.to_dict(),
        mx.fill_model.safety_payload(),
    ):
        assert d["phase_12_forbidden"] is True
    # The literal "Phase 12" must NOT appear as a destination in the
    # phase identifiers.
    assert "Phase 12" not in MOCK_EXCHANGE_PHASE_NAME
    assert "Phase 12" not in PESSIMISTIC_FILL_MODEL_PHASE_NAME


# ---------------------------------------------------------------------------
# 17. auto_tuning_allowed=False
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_in_every_payload():
    batch = _build_batch_with_kline()
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    assert mx.auto_tuning_allowed is False
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    f = mx.list_fills()[0]
    for d in (
        order.to_dict(),
        f.to_dict(),
        cfg.to_dict(),
        mx.to_dict(),
        mx.safety_payload(),
        mx.diagnostics.to_dict(),
        mx.fill_model.safety_payload(),
    ):
        assert d["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 18. trade_authority=False
# ---------------------------------------------------------------------------


def test_trade_authority_false_in_every_payload():
    batch = _build_batch_with_kline()
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    assert mx.trade_authority is False
    assert mx.ai_trade_authority is False
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    f = mx.list_fills()[0]
    for d in (
        order.to_dict(),
        f.to_dict(),
        cfg.to_dict(),
        mx.to_dict(),
        mx.safety_payload(),
        mx.diagnostics.to_dict(),
        mx.fill_model.safety_payload(),
    ):
        assert d["trade_authority"] is False
        assert d["ai_trade_authority"] is False


# ---------------------------------------------------------------------------
# 19. forbidden fields absent from serialized outputs
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_from_serialized_outputs():
    batch = _build_batch_with_kline()
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    f = mx.list_fills()[0]
    payloads = [
        order.to_dict(),
        f.to_dict(),
        cfg.to_dict(),
        mx.to_dict(),
        mx.safety_payload(),
        mx.diagnostics.to_dict(),
        mx.fill_model.safety_payload(),
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ).to_dict(),
        FillModelDecision().to_dict(),
    ]
    for p in payloads:
        # Recursive forbidden-field guard.
        assert_no_forbidden_fields(p)
        keys = set(_walk_keys(p))
        assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS), (
            f"forbidden field present: "
            f"{keys & FORBIDDEN_OUTPUT_FIELDS}"
        )
        # Brief-mandated forbidden field names.
        for forbidden in (
            "runtime_config_patch",
            "symbol_limit_patch",
            "threshold_patch",
            "candidate_pool_patch",
            "regime_weight_patch",
            "strategy_parameter_patch",
            "apply_change",
            "deploy_change",
            "enable_live",
            "live_ready",
            "trading_approved",
            "real_order_id",
            "exchange_order_id",
            "api_key",
            "api_secret",
        ):
            assert forbidden not in keys, (
                f"forbidden field {forbidden!r} smuggled into payload"
            )
    # Construction-time guard: hostile evidence_refs entries are
    # rejected at the type level (must be strings only); a literal
    # "runtime_config_patch" string in evidence_refs is allowed (it's
    # a string value, not a key) BUT must not collide with a key.
    # The recursive guard checks keys, not values, so this is the
    # correct contract. We also assert that the hostile dataclass
    # bypass is impossible.
    with pytest.raises((ValueError, TypeError)):
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
            evidence_refs=(123,),  # not a string -> TypeError
        )


# ---------------------------------------------------------------------------
# 20. module does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports_in_modules():
    root = _project_root()
    paths = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "mock_exchange.py",
        root / "app" / "sim" / "pessimistic_fill_model.py",
    ]
    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in paths:
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            for bad in forbidden_prefixes:
                assert not mod.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
        idents = _collect_code_identifiers(src)
        for ident in idents:
            for bad in forbidden_prefixes:
                assert not ident.startswith(bad), (
                    f"{path} references forbidden identifier {ident!r}"
                )
    # Importing the new modules does not pull any forbidden module.
    before = set(sys.modules)
    importlib.import_module("app.sim")
    importlib.import_module("app.sim.mock_exchange")
    importlib.import_module("app.sim.pessimistic_fill_model")
    new = set(sys.modules) - before
    for nm in new:
        for bad in forbidden_prefixes:
            assert not nm.startswith(bad), (
                f"importing app.sim pulled forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 21. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_llm_telegram_binance_or_network_path():
    root = _project_root()
    paths = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "mock_exchange.py",
        root / "app" / "sim" / "pessimistic_fill_model.py",
    ]
    forbidden_module_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        "telegram",
        "binance",
        "ccxt",
        "websocket",
        "websockets",
        "httpx",
        "aiohttp",
        "requests",
        "urllib.request",
        "http.client",
        "grpc",
        "boto3",
        "socket",
    )
    forbidden_identifier_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        "telegram",
        "binance",
        "ccxt",
        "websocket",
        "httpx",
        "aiohttp",
        "requests.get",
        "requests.post",
        "urllib.request",
        "socket.connect",
        "socket.create_connection",
    )
    for path in paths:
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            low = mod.lower()
            for bad in forbidden_module_prefixes:
                assert not low.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
        idents = _collect_code_identifiers(src)
        for ident in idents:
            low = ident.lower()
            for bad in forbidden_identifier_prefixes:
                assert not low.startswith(bad), (
                    f"{path} references forbidden code identifier "
                    f"{ident!r}"
                )
    pre = set(sys.modules)
    importlib.import_module("app.sim.mock_exchange")
    importlib.import_module("app.sim.pessimistic_fill_model")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), (
                f"unexpected import: {nm}"
            )


# ---------------------------------------------------------------------------
# 22. no real exchange endpoint / signed endpoint / API key fields
# ---------------------------------------------------------------------------


def test_no_real_exchange_endpoint_signed_endpoint_or_api_key_fields():
    batch = _build_batch_with_kline()
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    order = mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    f = mx.list_fills()[0]
    # Defensive tripwires on the live instance.
    assert mx.binance_private_api_enabled is False
    assert mx.signed_endpoint_reachable is False
    assert mx.private_websocket_reachable is False
    assert mx.account_endpoint_reachable is False
    assert mx.order_endpoint_reachable is False
    assert mx.position_endpoint_reachable is False
    assert mx.leverage_endpoint_reachable is False
    assert mx.margin_endpoint_reachable is False
    assert mx.real_exchange_order_path is False
    assert mx.real_capital is False
    assert mx.exchange_live_orders is False
    # Same flags on every serialized output.
    forbidden_string_fields = (
        "api_key",
        "api_secret",
        "exchange_order_id",
        "real_order_id",
        "binance_signed",
        "private_websocket_url",
        "listenkey",
        "listen_key",
    )
    for d in (
        order.to_dict(),
        f.to_dict(),
        cfg.to_dict(),
        mx.to_dict(),
        mx.safety_payload(),
        mx.diagnostics.to_dict(),
        mx.fill_model.safety_payload(),
    ):
        keys = set(_walk_keys(d))
        for forbidden in forbidden_string_fields:
            assert forbidden not in keys, (
                f"forbidden field {forbidden!r} present"
            )
        assert d["binance_private_api_enabled"] is False
        assert d["signed_endpoint_reachable"] is False
        assert d["private_websocket_reachable"] is False
        assert d["account_endpoint_reachable"] is False
        assert d["order_endpoint_reachable"] is False
        assert d["position_endpoint_reachable"] is False
        assert d["leverage_endpoint_reachable"] is False
        assert d["margin_endpoint_reachable"] is False
        assert d["real_exchange_order_path"] is False
        assert d["real_capital"] is False
        assert d["exchange_live_orders"] is False
    # The MockExchange config refuses any attempt to construct with
    # live_order_enabled=True or sandbox_only=False.
    with pytest.raises(ValueError):
        MockExchangeConfig(live_order_enabled=True)
    with pytest.raises(ValueError):
        MockExchangeConfig(sandbox_only=False)
    # No public method on the exchange / fill model exposes a trade
    # verb such as place_order, sign_request, etc.
    forbidden_verbs = {
        "place_order",
        "place_real_order",
        "sign_request",
        "sign",
        "open_websocket",
        "private_websocket",
        "listen_key",
        "set_leverage",
        "set_stop",
        "set_target",
        "apply_change",
        "deploy",
        "enable_live",
    }
    for inst in (mx, mx.fill_model, mx.diagnostics, cfg):
        public = {n for n in dir(inst) if not n.startswith("_")}
        assert public.isdisjoint(forbidden_verbs), (
            f"{inst!r} exposes forbidden verbs: "
            f"{public & forbidden_verbs}"
        )


# ---------------------------------------------------------------------------
# Extra: closed-taxonomy enforcement
# ---------------------------------------------------------------------------


def test_closed_taxonomy_enforcement():
    # Each enum exposes ALLOWED as a frozenset.
    assert isinstance(MockOrderType.ALLOWED, frozenset)
    assert isinstance(MockOrderSide.ALLOWED, frozenset)
    assert isinstance(MockOrderStatus.ALLOWED, frozenset)
    assert isinstance(AmbiguousIntrabarPolicy.ALLOWED, frozenset)
    assert isinstance(LimitTouchFillPolicy.ALLOWED, frozenset)
    assert isinstance(FillReason.ALLOWED, frozenset)
    assert isinstance(ConservativeAssumption.ALLOWED, frozenset)
    # Closed values cannot be silently extended.
    assert "MARGIN_CALL" not in MockOrderType.ALLOWED
    assert "OPEN_INTEREST" not in MockOrderStatus.ALLOWED
    # OrderRequest / MockOrder reject unknown order_type / side /
    # status values.
    with pytest.raises(ValueError):
        OrderRequest(
            symbol="BTCUSDT",
            side="UPSIDE",
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        )
    with pytest.raises(ValueError):
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type="PUT",
            requested_qty=1.0,
        )
    with pytest.raises(ValueError):
        MockExchangeConfig(
            ambiguous_intrabar_policy="OPTIMISTIC",
        )
    with pytest.raises(ValueError):
        MockExchangeConfig(
            limit_touch_fill_policy="ALWAYS_FILL",
        )


# ---------------------------------------------------------------------------
# Extra: limit order without limit_price / stop without stop_price
# ---------------------------------------------------------------------------


def test_limit_order_requires_limit_price_stop_requires_stop_price():
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    # LIMIT without limit_price -> reject at MockOrder construction.
    with pytest.raises(ValueError):
        mx.submit_order(
            OrderRequest(
                symbol="BTCUSDT",
                side=MockOrderSide.BUY,
                order_type=MockOrderType.LIMIT,
                requested_qty=1.0,
            ),
            simulated_time=_T0,
        )
    with pytest.raises(ValueError):
        mx.submit_order(
            OrderRequest(
                symbol="BTCUSDT",
                side=MockOrderSide.BUY,
                order_type=MockOrderType.STOP_MARKET,
                requested_qty=1.0,
            ),
            simulated_time=_T0,
        )
    with pytest.raises(ValueError):
        mx.submit_order(
            OrderRequest(
                symbol="BTCUSDT",
                side=MockOrderSide.SELL,
                order_type=MockOrderType.TAKE_PROFIT_MARKET,
                requested_qty=1.0,
            ),
            simulated_time=_T0,
        )


# ---------------------------------------------------------------------------
# Extra: reset() clears in-memory state
# ---------------------------------------------------------------------------


def test_reset_clears_in_memory_state():
    cfg = MockExchangeConfig()
    mx = MockExchange(config=cfg)
    batch = _build_batch_with_kline()
    mx.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=1.0,
        ),
        replay_batch=batch,
    )
    assert mx.order_count == 1
    assert mx.fill_count == 1
    mx.reset()
    assert mx.order_count == 0
    assert mx.fill_count == 0
    assert mx.list_open_orders() == []
    assert mx.list_all_orders() == []
    assert mx.list_fills() == []
    assert mx.diagnostics.fills_count == 0
    assert mx.diagnostics.orders_submitted_count == 0
