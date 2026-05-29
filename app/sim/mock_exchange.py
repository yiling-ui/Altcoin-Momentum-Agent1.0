"""MockExchange for Phase 11C.1D-D-D (PR97 - MockExchange +
Pessimistic Fill Model v0).

Strict blind walk-forward simulated exchange. This module is the
**fourth** anti-future-lookahead infrastructure block of the strict
blind walk-forward stack defined by Phase 11C.1D-D (the *Strict Blind
Walk-forward Sim-Live Constitution*, PR93). It builds strictly on top
of the PR94 substrate (:class:`SimulationClock`,
:class:`HistoricalRecordTime`, :class:`TimeWallGuard`,
:class:`CandleVisibilityGuard`, :class:`NoLookaheadViolation`,
:func:`assert_no_forbidden_fields`), the PR95 substrate
(:class:`HistoricalMarketStore`, :class:`HistoricalKlineRecord`,
:class:`HistoricalMarketRecordType`), and the PR96 substrate
(:class:`ReplayFeedBatch`, :class:`ReplayFeedProvider`,
:class:`ReplayFeedProviderConfig`,
:class:`ReplayFeedDiagnostics`, :class:`ReplayFeedCursor`).

Constitution §11: the MockExchange consumes ReplayFeedProvider /
HistoricalMarketStore visible market data only. It NEVER calls a
real exchange endpoint, NEVER signs a request, NEVER touches the
Binance private API, NEVER opens a private websocket, NEVER fetches
account / order / position / leverage / margin endpoints, and
NEVER advertises a real exchange order id. It implements order
lifecycle simulation (CREATED -> ACCEPTED -> {PARTIALLY_FILLED} ->
{FILLED, REJECTED, CANCELED, EXPIRED, STALE,
AMBIGUOUS_INTRABAR_PATH}) and routes every fill decision through
:class:`PessimisticFillModel`.

Hard safety boundary (Phase 11C.1D-D-D / PR97):

  - mode = paper
  - sandbox_only = True
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
  - telegram_live_command_authority = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

This module MUST NOT and CANNOT:

  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram / Binance private API / any
    network
  - place a real order
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - emit a real exchange order id, an api key, an api secret, or a
    signed-endpoint reference
  - authorize live trading or auto-tuning
  - enter Phase 12

The MockExchange is NOT responsible for:

  - the Simulated Capital Flow + Trade Ledger (PR98),
  - the Telegram Sandbox Outbox (PR99),
  - the Blind Walk-forward Runner (PR100),
  - real Execution FSM wiring,
  - real Risk Engine decisions.

PR97 acceptance authorises ONLY PR98 (*Simulated Capital Flow +
Trade Ledger v0*) to begin its own gate.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

from app.sim.historical_market_store import HistoricalKlineRecord
from app.sim.pessimistic_fill_model import (
    AmbiguousIntrabarPolicy,
    ConservativeAssumption,
    FillModelDecision,
    FillReason,
    MockExchangeConfig,
    MockFill,
    MockOrder,
    MockOrderSide,
    MockOrderStatus,
    MockOrderType,
    PessimisticFillModel,
)
from app.sim.replay_feed_provider import ReplayFeedBatch
from app.sim.simulation_clock import ensure_utc_aware
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-D / PR97 / MockExchange + Pessimistic Fill "
    "Model v0"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    """Project-wide safety boundary, re-pinned on every serialisation
    boundary so that no payload can ever be misread as authorising
    live trading, auto-tuning, or Phase 12.
    """
    return {
        "phase": PHASE_NAME,
        "mode": "paper",
        "sandbox_only": True,
        "simulated_only": True,
        "no_live_order": True,
        "live_trading": False,
        "exchange_live_orders": False,
        "binance_private_api_enabled": False,
        "signed_endpoint_reachable": False,
        "private_websocket_reachable": False,
        "account_endpoint_reachable": False,
        "order_endpoint_reachable": False,
        "position_endpoint_reachable": False,
        "leverage_endpoint_reachable": False,
        "margin_endpoint_reachable": False,
        "real_exchange_order_path": False,
        "real_capital": False,
        "telegram_outbound_enabled": False,
        "telegram_live_command_authority": False,
        "ai_trade_authority": False,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        # Defensive non-trade markers:
        "is_mock_exchange_payload": True,
        "is_real_exchange_order": False,
        "is_runtime_patch": False,
    }


def _check_evidence_refs(refs: Iterable[Any]) -> Tuple[str, ...]:
    out: List[str] = []
    for r in refs:
        if not isinstance(r, str):
            raise TypeError(
                f"evidence_refs entries must be strings, got "
                f"{type(r)!r}"
            )
        out.append(r)
    return tuple(out)


# ---------------------------------------------------------------------------
# OrderRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderRequest:
    """A request to submit a simulated order.

    The :class:`MockExchange` constructs a :class:`MockOrder` from
    this request and (optionally) the visible :class:`ReplayFeedBatch`.
    The request is the **only** input the exchange accepts; raw
    Mapping-shape inputs are refused.
    """

    symbol: str
    side: str
    order_type: str
    requested_qty: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    client_tag: Optional[str] = None
    pair_with_order_id: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if self.side not in MockOrderSide.ALLOWED:
            raise ValueError(
                f"side must be one of {sorted(MockOrderSide.ALLOWED)}, "
                f"got {self.side!r}"
            )
        if self.order_type not in MockOrderType.ALLOWED:
            raise ValueError(
                f"order_type must be one of "
                f"{sorted(MockOrderType.ALLOWED)}, got "
                f"{self.order_type!r}"
            )
        # Refuse hostile callers smuggling forbidden fields via the
        # client_tag / evidence_refs free-text channels.
        if self.client_tag is not None and (
            not isinstance(self.client_tag, str) or not self.client_tag
        ):
            raise ValueError(
                "client_tag must be a non-empty string or None"
            )
        if self.pair_with_order_id is not None and (
            not isinstance(self.pair_with_order_id, str)
            or not self.pair_with_order_id
        ):
            raise ValueError(
                "pair_with_order_id must be a non-empty string or "
                "None"
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _check_evidence_refs(self.evidence_refs),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "requested_qty": float(self.requested_qty),
            "limit_price": (
                float(self.limit_price)
                if self.limit_price is not None
                else None
            ),
            "stop_price": (
                float(self.stop_price)
                if self.stop_price is not None
                else None
            ),
            "client_tag": self.client_tag,
            "pair_with_order_id": self.pair_with_order_id,
            "evidence_refs": list(self.evidence_refs),
            "is_order_request": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# MockExchangeDiagnostics
# ---------------------------------------------------------------------------


@dataclass
class MockExchangeDiagnostics:
    """Cumulative diagnostics for a :class:`MockExchange`.

    The exchange mutates this object across calls; callers that
    want a stable snapshot use :meth:`snapshot`.
    """

    orders_submitted_count: int = 0
    orders_accepted_count: int = 0
    orders_rejected_count: int = 0
    orders_canceled_count: int = 0
    orders_expired_count: int = 0
    orders_stale_count: int = 0
    orders_filled_count: int = 0
    orders_partially_filled_count: int = 0
    orders_ambiguous_intrabar_count: int = 0
    fills_count: int = 0
    process_batch_count: int = 0

    def snapshot(self) -> "MockExchangeDiagnostics":
        return MockExchangeDiagnostics(
            orders_submitted_count=self.orders_submitted_count,
            orders_accepted_count=self.orders_accepted_count,
            orders_rejected_count=self.orders_rejected_count,
            orders_canceled_count=self.orders_canceled_count,
            orders_expired_count=self.orders_expired_count,
            orders_stale_count=self.orders_stale_count,
            orders_filled_count=self.orders_filled_count,
            orders_partially_filled_count=(
                self.orders_partially_filled_count
            ),
            orders_ambiguous_intrabar_count=(
                self.orders_ambiguous_intrabar_count
            ),
            fills_count=self.fills_count,
            process_batch_count=self.process_batch_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "orders_submitted_count": int(self.orders_submitted_count),
            "orders_accepted_count": int(self.orders_accepted_count),
            "orders_rejected_count": int(self.orders_rejected_count),
            "orders_canceled_count": int(self.orders_canceled_count),
            "orders_expired_count": int(self.orders_expired_count),
            "orders_stale_count": int(self.orders_stale_count),
            "orders_filled_count": int(self.orders_filled_count),
            "orders_partially_filled_count": int(
                self.orders_partially_filled_count
            ),
            "orders_ambiguous_intrabar_count": int(
                self.orders_ambiguous_intrabar_count
            ),
            "fills_count": int(self.fills_count),
            "process_batch_count": int(self.process_batch_count),
            "is_mock_exchange_diagnostics": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# MockExchange
# ---------------------------------------------------------------------------


class MockExchange:
    """Strict blind walk-forward simulated exchange.

    The exchange is **deterministic, paper-only, and pure**:

      * It NEVER opens a network socket, signs a request, talks to
        a real exchange, the Telegram API, or any LLM.
      * It NEVER consults the wall-clock; every visible moment
        comes from the supplied ``simulated_time`` or the
        :class:`ReplayFeedBatch`.
      * It NEVER produces a real exchange order id; every
        :class:`MockOrder` carries a deterministic
        ``"mock_order_{counter:08d}"`` id, every :class:`MockFill`
        carries a deterministic ``"mock_fill_{counter:08d}"`` id.
      * Two exchanges fed identical config / requests / batches
        produce identical order / fill sequences.
      * It NEVER bypasses the
        :class:`PessimisticFillModel`'s conservative rules
        (taker fee + slippage + latency on market / forced exit /
        stop / take-profit, no-fill-on-touch on limit, worst-case
        / AMBIGUOUS on same-candle stop + take-profit).

    Lifecycle:

      * ``submit_order(request, replay_batch=None,
        simulated_time=None)`` accepts a new
        :class:`OrderRequest`, builds a :class:`MockOrder`,
        validates against the visible kline (if any), and
        immediately runs the fill model (if a batch is supplied).
        Returns the :class:`MockOrder`.
      * ``cancel_order(order_id, simulated_time)`` cancels an
        open order. Returns the :class:`MockOrder` with status
        :pyattr:`MockOrderStatus.CANCELED`.
      * ``process_batch(replay_batch)`` advances the visible
        market state by one batch and routes every open order
        through the fill model. Returns the list of
        :class:`MockFill` objects produced **by this call**.
      * ``get_order(order_id)`` returns the :class:`MockOrder`
        or raises :class:`KeyError`.
      * ``list_open_orders()`` / ``list_all_orders()`` /
        ``list_fills()`` return defensive copies of the
        in-memory state.
      * ``reset()`` clears all in-memory state (test-only).
    """

    def __init__(
        self,
        *,
        config: Optional[MockExchangeConfig] = None,
        fill_model: Optional[PessimisticFillModel] = None,
    ) -> None:
        if fill_model is not None and not isinstance(
            fill_model, PessimisticFillModel
        ):
            raise TypeError(
                f"fill_model must be PessimisticFillModel, got "
                f"{type(fill_model)!r}"
            )
        if config is None and fill_model is None:
            config = MockExchangeConfig()
        if config is None:
            config = fill_model.config
        elif not isinstance(config, MockExchangeConfig):
            raise TypeError(
                f"config must be MockExchangeConfig, got "
                f"{type(config)!r}"
            )
        if fill_model is None:
            fill_model = PessimisticFillModel(config)
        elif fill_model.config is not config:
            raise ValueError(
                "fill_model.config must be the same instance as "
                "the supplied config"
            )
        self._config: MockExchangeConfig = config
        self._fill_model: PessimisticFillModel = fill_model
        self._orders: Dict[str, MockOrder] = {}
        self._fills: List[MockFill] = []
        self._order_counter: int = 0
        self._fill_counter: int = 0
        self._diagnostics: MockExchangeDiagnostics = (
            MockExchangeDiagnostics()
        )
        # Defensive tripwires (mirrors PR94 / PR95 / PR96 guards).
        self.sandbox_only: bool = True
        self.simulated_only: bool = True
        self.no_live_order: bool = True
        self.live_trading: bool = False
        self.exchange_live_orders: bool = False
        self.binance_private_api_enabled: bool = False
        self.signed_endpoint_reachable: bool = False
        self.private_websocket_reachable: bool = False
        self.account_endpoint_reachable: bool = False
        self.order_endpoint_reachable: bool = False
        self.position_endpoint_reachable: bool = False
        self.leverage_endpoint_reachable: bool = False
        self.margin_endpoint_reachable: bool = False
        self.real_exchange_order_path: bool = False
        self.real_capital: bool = False
        self.telegram_outbound_enabled: bool = False
        self.ai_trade_authority: bool = False
        self.trade_authority: bool = False
        self.auto_tuning_allowed: bool = False
        self.phase_12_forbidden: bool = True

    # ----- public introspection -----

    @property
    def config(self) -> MockExchangeConfig:
        return self._config

    @property
    def fill_model(self) -> PessimisticFillModel:
        return self._fill_model

    @property
    def diagnostics(self) -> MockExchangeDiagnostics:
        return self._diagnostics

    @property
    def order_count(self) -> int:
        return len(self._orders)

    @property
    def fill_count(self) -> int:
        return len(self._fills)

    def safety_payload(self) -> Dict[str, Any]:
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        return out

    # ----- public lifecycle API -----

    def submit_order(
        self,
        request: OrderRequest,
        replay_batch: Optional[ReplayFeedBatch] = None,
        *,
        simulated_time: Optional[datetime] = None,
    ) -> MockOrder:
        """Accept a new :class:`OrderRequest` and create a
        :class:`MockOrder`.

        If ``replay_batch`` is supplied, the order is immediately
        evaluated against the visible kline for its symbol and may
        transition to :pyattr:`MockOrderStatus.PARTIALLY_FILLED` /
        :pyattr:`MockOrderStatus.FILLED` /
        :pyattr:`MockOrderStatus.REJECTED` /
        :pyattr:`MockOrderStatus.STALE` /
        :pyattr:`MockOrderStatus.AMBIGUOUS_INTRABAR_PATH`.
        Otherwise the order remains in
        :pyattr:`MockOrderStatus.ACCEPTED`.

        ``simulated_time`` MUST be supplied when ``replay_batch``
        is None (or it defaults to the batch's
        ``simulated_time`` when a batch is supplied).
        """
        if not isinstance(request, OrderRequest):
            raise TypeError(
                f"request must be OrderRequest, got {type(request)!r}"
            )
        sim = self._resolve_simulated_time(replay_batch, simulated_time)
        order_id = self._next_order_id()
        order = MockOrder(
            order_id=order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            requested_qty=request.requested_qty,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            client_tag=request.client_tag,
            pair_with_order_id=request.pair_with_order_id,
            created_at_simulated=sim,
            status=MockOrderStatus.ACCEPTED,
            last_status_change_at_simulated=sim,
            evidence_refs=request.evidence_refs,
        )
        self._orders[order_id] = order
        self._diagnostics.orders_submitted_count += 1
        self._diagnostics.orders_accepted_count += 1
        # If a replay_batch is supplied, immediately try to fill.
        if replay_batch is not None:
            self._evaluate_order(order, replay_batch)
        return order

    def cancel_order(
        self,
        order_id: str,
        simulated_time: datetime,
    ) -> MockOrder:
        """Cancel an open order. Idempotent on terminal orders."""
        if not isinstance(order_id, str) or not order_id:
            raise ValueError("order_id must be a non-empty string")
        if order_id not in self._orders:
            raise KeyError(f"unknown order_id {order_id!r}")
        order = self._orders[order_id]
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        if order.is_terminal:
            return order
        order.status = MockOrderStatus.CANCELED
        order.last_status_change_at_simulated = sim
        self._diagnostics.orders_canceled_count += 1
        return order

    def expire_order(
        self,
        order_id: str,
        simulated_time: datetime,
    ) -> MockOrder:
        """Mark an open order as expired. Idempotent on terminal orders."""
        if not isinstance(order_id, str) or not order_id:
            raise ValueError("order_id must be a non-empty string")
        if order_id not in self._orders:
            raise KeyError(f"unknown order_id {order_id!r}")
        order = self._orders[order_id]
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        if order.is_terminal:
            return order
        order.status = MockOrderStatus.EXPIRED
        order.last_status_change_at_simulated = sim
        self._diagnostics.orders_expired_count += 1
        return order

    def process_batch(
        self, replay_batch: ReplayFeedBatch
    ) -> List[MockFill]:
        """Evaluate every open order against ``replay_batch``.

        Returns the list of :class:`MockFill` objects produced
        **during this call** (does NOT include earlier fills).
        """
        if not isinstance(replay_batch, ReplayFeedBatch):
            raise TypeError(
                f"replay_batch must be ReplayFeedBatch, got "
                f"{type(replay_batch)!r}"
            )
        self._diagnostics.process_batch_count += 1
        fills: List[MockFill] = []
        # Iterate orders in deterministic order (by order_id, which
        # is a zero-padded counter).
        for order_id in sorted(self._orders):
            order = self._orders[order_id]
            if not order.is_open:
                continue
            new_fills = self._evaluate_order(order, replay_batch)
            fills.extend(new_fills)
        return fills

    def get_order(self, order_id: str) -> MockOrder:
        if order_id not in self._orders:
            raise KeyError(f"unknown order_id {order_id!r}")
        return self._orders[order_id]

    def list_open_orders(self) -> List[MockOrder]:
        return [
            self._orders[oid]
            for oid in sorted(self._orders)
            if self._orders[oid].is_open
        ]

    def list_all_orders(self) -> List[MockOrder]:
        return [self._orders[oid] for oid in sorted(self._orders)]

    def list_fills(self) -> List[MockFill]:
        return list(self._fills)

    def reset(self) -> None:
        """Reset all in-memory state. Test-only."""
        self._orders = {}
        self._fills = []
        self._order_counter = 0
        self._fill_counter = 0
        self._diagnostics = MockExchangeDiagnostics()

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "config": self._config.to_dict(),
            "diagnostics": self._diagnostics.to_dict(),
            "order_count": int(self.order_count),
            "fill_count": int(self.fill_count),
            "is_mock_exchange": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    # ----- internal helpers -----

    def _resolve_simulated_time(
        self,
        replay_batch: Optional[ReplayFeedBatch],
        simulated_time: Optional[datetime],
    ) -> datetime:
        if simulated_time is not None:
            return ensure_utc_aware(
                simulated_time, "simulated_time"
            )
        if replay_batch is not None:
            return replay_batch.simulated_time
        raise ValueError(
            "simulated_time must be supplied when no replay_batch "
            "is provided"
        )

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"mock_order_{self._order_counter:08d}"

    def _next_fill_id(self) -> str:
        self._fill_counter += 1
        return f"mock_fill_{self._fill_counter:08d}"

    def _latest_visible_kline(
        self,
        symbol: str,
        replay_batch: ReplayFeedBatch,
    ) -> Optional[HistoricalKlineRecord]:
        """Return the latest visible kline for ``symbol`` in
        ``replay_batch``, preferring 1m over 5m, sorted by close_time.

        Visible by construction: every kline in the batch already
        has ``available_at <= simulated_time`` and a closed candle.
        """
        candidates: List[HistoricalKlineRecord] = []
        for k in replay_batch.klines_1m:
            if k.symbol == symbol:
                candidates.append(k)
        if candidates:
            return max(candidates, key=lambda k: k.close_time)
        for k in replay_batch.klines_5m:
            if k.symbol == symbol:
                candidates.append(k)
        if candidates:
            return max(candidates, key=lambda k: k.close_time)
        return None

    def _is_ambiguous_intrabar_pair(
        self,
        order: MockOrder,
        kline: HistoricalKlineRecord,
    ) -> bool:
        """Detect the same-candle stop + take-profit ambiguity.

        Returns True iff:

          * ``order`` is :pyattr:`MockOrderType.STOP_MARKET` or
            :pyattr:`MockOrderType.TAKE_PROFIT_MARKET`, AND
          * there exists a paired open order on the books (matched
            via ``pair_with_order_id`` on either side) of the
            opposite-trigger type, AND
          * both trigger levels are touched by ``kline``.
        """
        if order.order_type not in (
            MockOrderType.STOP_MARKET,
            MockOrderType.TAKE_PROFIT_MARKET,
        ):
            return False
        partner = self._find_pair(order)
        if partner is None or not partner.is_open:
            return False
        if order.order_type == partner.order_type:
            # Two stops or two TPs are not the ambiguous case.
            return False
        # Both trigger levels are touched by the same kline iff:
        #   * the stop level is within [low, high], AND
        #   * the take-profit level is within [low, high].
        stop_order, tp_order = (
            (order, partner)
            if order.order_type == MockOrderType.STOP_MARKET
            else (partner, order)
        )
        sp = stop_order.stop_price
        tp = tp_order.stop_price
        if sp is None or tp is None:
            return False
        low = float(kline.low)
        high = float(kline.high)
        stop_touched = (
            (
                stop_order.side == MockOrderSide.SELL
                and low <= float(sp)
            )
            or (
                stop_order.side == MockOrderSide.BUY
                and high >= float(sp)
            )
        )
        tp_touched = (
            (
                tp_order.side == MockOrderSide.SELL
                and high >= float(tp)
            )
            or (
                tp_order.side == MockOrderSide.BUY
                and low <= float(tp)
            )
        )
        return bool(stop_touched and tp_touched)

    def _find_pair(self, order: MockOrder) -> Optional[MockOrder]:
        """Return the paired order if any, by ``pair_with_order_id``."""
        if order.pair_with_order_id is not None and (
            order.pair_with_order_id in self._orders
        ):
            return self._orders[order.pair_with_order_id]
        # Reverse lookup: another order may name THIS order as its
        # pair.
        for other in self._orders.values():
            if other.pair_with_order_id == order.order_id:
                return other
        return None

    def _evaluate_order(
        self,
        order: MockOrder,
        replay_batch: ReplayFeedBatch,
    ) -> List[MockFill]:
        sim = replay_batch.simulated_time
        kline = self._latest_visible_kline(order.symbol, replay_batch)
        ambiguous_pair = False
        if kline is not None:
            ambiguous_pair = self._is_ambiguous_intrabar_pair(
                order, kline
            )
        fill_id_candidate = self._peek_next_fill_id()
        decision = self._fill_model.evaluate(
            order,
            kline,
            simulated_time=sim,
            fill_id=fill_id_candidate,
            ambiguous_intrabar_pair=ambiguous_pair,
        )
        return self._apply_decision(
            order, decision, sim, ambiguous_pair=ambiguous_pair
        )

    def _peek_next_fill_id(self) -> str:
        # We compute the candidate id BEFORE knowing whether the
        # decision actually produces a fill, so we use a peek-and-
        # commit pattern: only commit (advance the counter) when the
        # decision actually carries a fill.
        return f"mock_fill_{self._fill_counter + 1:08d}"

    def _apply_decision(
        self,
        order: MockOrder,
        decision: FillModelDecision,
        simulated_time: datetime,
        *,
        ambiguous_pair: bool,
    ) -> List[MockFill]:
        fills: List[MockFill] = []
        new_status = decision.new_status
        if decision.fill is not None:
            # Commit the fill counter (the decision used the peeked
            # fill_id, so we advance the counter to match).
            self._fill_counter += 1
            self._fills.append(decision.fill)
            self._diagnostics.fills_count += 1
            order.filled_qty = float(order.filled_qty) + float(
                decision.fill.filled_qty
            )
            fills.append(decision.fill)
        if new_status is not None and new_status != order.status:
            old_status = order.status
            order.status = new_status
            order.last_status_change_at_simulated = simulated_time
            if new_status == MockOrderStatus.FILLED:
                self._diagnostics.orders_filled_count += 1
            elif new_status == MockOrderStatus.PARTIALLY_FILLED:
                # PARTIALLY_FILLED is not terminal; we count
                # transitions, not unique orders, so we increment
                # only on the FIRST entry into PARTIALLY_FILLED.
                if old_status != MockOrderStatus.PARTIALLY_FILLED:
                    self._diagnostics.orders_partially_filled_count += 1
            elif new_status == MockOrderStatus.REJECTED:
                self._diagnostics.orders_rejected_count += 1
            elif new_status == MockOrderStatus.CANCELED:
                self._diagnostics.orders_canceled_count += 1
            elif new_status == MockOrderStatus.EXPIRED:
                self._diagnostics.orders_expired_count += 1
            elif new_status == MockOrderStatus.STALE:
                self._diagnostics.orders_stale_count += 1
            elif new_status == (
                MockOrderStatus.AMBIGUOUS_INTRABAR_PATH
            ):
                self._diagnostics.orders_ambiguous_intrabar_count += 1
                # Also mark the paired order ambiguous (under the
                # AMBIGUOUS policy both orders are unresolved).
                partner = self._find_pair(order)
                if (
                    ambiguous_pair
                    and partner is not None
                    and partner.is_open
                ):
                    partner.status = (
                        MockOrderStatus.AMBIGUOUS_INTRABAR_PATH
                    )
                    partner.last_status_change_at_simulated = (
                        simulated_time
                    )
                    self._diagnostics.orders_ambiguous_intrabar_count += 1
        # WORST_CASE policy: when the ambiguous-intrabar stop fires,
        # the paired take-profit order MUST be canceled (the
        # favorable level cannot be claimed because we cannot prove
        # the TP was hit before the stop within the bar).
        if (
            ambiguous_pair
            and decision.fill is not None
            and decision.fill.fill_reason == (
                FillReason.AMBIGUOUS_WORST_CASE_STOP_FILL
            )
        ):
            partner = self._find_pair(order)
            if partner is not None and partner.is_open:
                partner.status = MockOrderStatus.CANCELED
                partner.last_status_change_at_simulated = (
                    simulated_time
                )
                self._diagnostics.orders_canceled_count += 1
        return fills


__all__ = [
    "PHASE_NAME",
    "MockExchange",
    "MockExchangeDiagnostics",
    "OrderRequest",
]
