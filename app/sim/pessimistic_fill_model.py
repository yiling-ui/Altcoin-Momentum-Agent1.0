"""PessimisticFillModel + Mock order / fill / config types for
Phase 11C.1D-D-D (PR97 - MockExchange + Pessimistic Fill Model v0).

Strict blind walk-forward conservative fill substrate. This module is
the **fourth** anti-future-lookahead infrastructure block of the strict
blind walk-forward stack defined by Phase 11C.1D-D (the *Strict Blind
Walk-forward Sim-Live Constitution*, PR93). It builds strictly on top
of the PR94 substrate (:class:`SimulationClock`,
:class:`HistoricalRecordTime`, :class:`TimeWallGuard`,
:class:`CandleVisibilityGuard`, :class:`NoLookaheadViolation`,
:func:`assert_no_forbidden_fields`), the PR95 substrate
(:class:`HistoricalMarketStore`, :class:`HistoricalKlineRecord`,
:class:`HistoricalMarketRecordType`, :class:`SymbolStatus`,
:class:`DataQualityFlag`, :class:`DataCompletenessState`), and the
PR96 substrate (:class:`ReplayFeedBatch`,
:class:`ReplayFeedProvider`, :class:`ReplayFeedProviderConfig`,
:class:`ReplayFeedDiagnostics`, :class:`ReplayFeedCursor`).

Constitution §11: the MockExchange + Pessimistic Fill Model never
calls a real exchange endpoint, never signs a request, never touches
the Binance private API, and never advertises a real exchange order
id. Fills are computed from visible market data only. The fill model
is **pessimistic**: market orders pay a taker fee plus slippage,
limit orders do not fill on touch by default (penetration required),
stop orders fill at the adverse stop price plus taker fee plus
slippage, take-profit orders fill conservatively, forced exits use
a conservative market exit, and same-candle stop + take-profit
triggers fall back to a worst-case or :pyattr:`AMBIGUOUS_INTRABAR_PATH`
status under closed-taxonomy ambiguous-intrabar policy. Insufficient
visible data NEVER produces an optimistic fill: the model rejects
or marks the order :pyattr:`STALE`.

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

PR97 acceptance authorises ONLY PR98 (*Simulated Capital Flow +
Trade Ledger v0*) to begin its own gate. PR97 does NOT implement,
and does NOT authorise:

  - the Simulated Capital Flow + Trade Ledger (PR98),
  - the Telegram Sandbox Outbox (PR99),
  - the Blind Walk-forward Runner (PR100),
  - Phase 12.

The Risk Engine remains the single trade-decision gate.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

from app.sim.historical_market_store import HistoricalKlineRecord
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
# Closed taxonomies
# ---------------------------------------------------------------------------


class MockOrderType:
    """Closed taxonomy of mock order types.

    Constitution §11 v0 minimum scope. ``FORCED_EXIT`` is the
    paper-side conservative exit primitive used by the
    (separately gated) PR98 Simulated Capital Flow + Trade Ledger
    when a position must be unwound; PR97 implements only the
    fill arithmetic, not the unwind decision.
    """

    MARKET: str = "MARKET"
    LIMIT: str = "LIMIT"
    STOP_MARKET: str = "STOP_MARKET"
    TAKE_PROFIT_MARKET: str = "TAKE_PROFIT_MARKET"
    FORCED_EXIT: str = "FORCED_EXIT"

    ALLOWED: FrozenSet[str] = frozenset(
        {MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET, FORCED_EXIT}
    )


class MockOrderSide:
    """Closed taxonomy of mock order sides.

    NOTE: ``side`` is a SIMULATED ORDER FIELD ONLY. It MUST NEVER
    surface as an AI / strategy recommendation, a Risk Engine
    suggestion, an Execution FSM directive, a runtime config
    patch, or a Telegram outbound. The MockExchange is
    paper-only; every output carries
    ``simulated_only=True`` / ``no_live_order=True``.
    """

    BUY: str = "BUY"
    SELL: str = "SELL"

    ALLOWED: FrozenSet[str] = frozenset({BUY, SELL})


class MockOrderStatus:
    """Closed taxonomy of mock order statuses (Constitution §11)."""

    CREATED: str = "CREATED"
    ACCEPTED: str = "ACCEPTED"
    PARTIALLY_FILLED: str = "PARTIALLY_FILLED"
    FILLED: str = "FILLED"
    REJECTED: str = "REJECTED"
    CANCELED: str = "CANCELED"
    EXPIRED: str = "EXPIRED"
    STALE: str = "STALE"
    AMBIGUOUS_INTRABAR_PATH: str = "AMBIGUOUS_INTRABAR_PATH"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            CREATED,
            ACCEPTED,
            PARTIALLY_FILLED,
            FILLED,
            REJECTED,
            CANCELED,
            EXPIRED,
            STALE,
            AMBIGUOUS_INTRABAR_PATH,
        }
    )

    # The set of statuses considered "open" (the order may still be
    # acted on by ``MockExchange.process_batch``).
    OPEN: FrozenSet[str] = frozenset(
        {CREATED, ACCEPTED, PARTIALLY_FILLED}
    )

    # The set of statuses considered "terminal" (no further
    # transitions allowed).
    TERMINAL: FrozenSet[str] = frozenset(
        {
            FILLED,
            REJECTED,
            CANCELED,
            EXPIRED,
            STALE,
            AMBIGUOUS_INTRABAR_PATH,
        }
    )


class AmbiguousIntrabarPolicy:
    """Closed taxonomy of ambiguous-intrabar handling policies."""

    WORST_CASE: str = "WORST_CASE"
    AMBIGUOUS: str = "AMBIGUOUS"

    ALLOWED: FrozenSet[str] = frozenset({WORST_CASE, AMBIGUOUS})


class LimitTouchFillPolicy:
    """Closed taxonomy of limit-order touch fill policies.

    ``NO_FILL_ON_TOUCH`` (default) is the conservative rule: a
    price that only touches the limit (``low == limit`` for a BUY
    limit, ``high == limit`` for a SELL limit) does NOT fill.
    ``ALLOW_FILL_ON_TOUCH`` is exposed only for parity testing of
    the underlying primitive; it MUST NOT be the default. The
    Constitution §11 conservative rule is enforced via the
    ``MockExchangeConfig`` default, not the
    :class:`PessimisticFillModel` primitive.
    """

    NO_FILL_ON_TOUCH: str = "NO_FILL_ON_TOUCH"
    ALLOW_FILL_ON_TOUCH: str = "ALLOW_FILL_ON_TOUCH"

    ALLOWED: FrozenSet[str] = frozenset(
        {NO_FILL_ON_TOUCH, ALLOW_FILL_ON_TOUCH}
    )


class FillReason:
    """Closed taxonomy of fill reasons surfaced on :class:`MockFill`."""

    MARKET_FILL: str = "MARKET_FILL"
    LIMIT_FILL_ON_PENETRATION: str = "LIMIT_FILL_ON_PENETRATION"
    STOP_TRIGGERED_FILL: str = "STOP_TRIGGERED_FILL"
    TAKE_PROFIT_TRIGGERED_FILL: str = "TAKE_PROFIT_TRIGGERED_FILL"
    FORCED_EXIT_FILL: str = "FORCED_EXIT_FILL"
    AMBIGUOUS_WORST_CASE_STOP_FILL: str = (
        "AMBIGUOUS_WORST_CASE_STOP_FILL"
    )

    ALLOWED: FrozenSet[str] = frozenset(
        {
            MARKET_FILL,
            LIMIT_FILL_ON_PENETRATION,
            STOP_TRIGGERED_FILL,
            TAKE_PROFIT_TRIGGERED_FILL,
            FORCED_EXIT_FILL,
            AMBIGUOUS_WORST_CASE_STOP_FILL,
        }
    )


class ConservativeAssumption:
    """Closed taxonomy of conservative-assumption markers."""

    TAKER_FEE_APPLIED: str = "TAKER_FEE_APPLIED"
    SLIPPAGE_APPLIED: str = "SLIPPAGE_APPLIED"
    LATENCY_PENALTY_APPLIED: str = "LATENCY_PENALTY_APPLIED"
    LIMIT_PENETRATION_REQUIRED: str = "LIMIT_PENETRATION_REQUIRED"
    STOP_ADVERSE_FILL: str = "STOP_ADVERSE_FILL"
    TAKE_PROFIT_CONSERVATIVE_FILL: str = (
        "TAKE_PROFIT_CONSERVATIVE_FILL"
    )
    FORCED_EXIT_CONSERVATIVE_FILL: str = (
        "FORCED_EXIT_CONSERVATIVE_FILL"
    )
    AMBIGUOUS_INTRABAR_WORST_CASE: str = (
        "AMBIGUOUS_INTRABAR_WORST_CASE"
    )
    PARTIAL_FILL: str = "PARTIAL_FILL"
    NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA: str = (
        "NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA"
    )

    ALLOWED: FrozenSet[str] = frozenset(
        {
            TAKER_FEE_APPLIED,
            SLIPPAGE_APPLIED,
            LATENCY_PENALTY_APPLIED,
            LIMIT_PENETRATION_REQUIRED,
            STOP_ADVERSE_FILL,
            TAKE_PROFIT_CONSERVATIVE_FILL,
            FORCED_EXIT_CONSERVATIVE_FILL,
            AMBIGUOUS_INTRABAR_WORST_CASE,
            PARTIAL_FILL,
            NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA,
        }
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
        "is_pessimistic_fill_model_payload": True,
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


def _check_conservative_assumptions(
    items: Iterable[Any],
) -> Tuple[str, ...]:
    out: List[str] = []
    seen: set = set()
    for it in items:
        if not isinstance(it, str):
            raise TypeError(
                f"conservative_assumption entries must be strings, "
                f"got {type(it)!r}"
            )
        if it not in ConservativeAssumption.ALLOWED:
            raise ValueError(
                f"conservative_assumption {it!r} not in closed "
                f"taxonomy {sorted(ConservativeAssumption.ALLOWED)}"
            )
        if it not in seen:
            seen.add(it)
            out.append(it)
    return tuple(out)


def _validate_positive_number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got bool")
    if not isinstance(value, (int, float)):
        raise TypeError(
            f"{name} must be int / float, got {type(value)!r}"
        )
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return float(value)


def _validate_non_negative_number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got bool")
    if not isinstance(value, (int, float)):
        raise TypeError(
            f"{name} must be int / float, got {type(value)!r}"
        )
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return float(value)


def _validate_optional_non_negative_number(
    name: str, value: Any
) -> Optional[float]:
    if value is None:
        return None
    return _validate_non_negative_number(name, value)


def _bps_to_fraction(bps: float) -> float:
    """Return the decimal fraction equivalent of ``bps`` basis points."""
    return float(bps) / 10000.0


# ---------------------------------------------------------------------------
# MockOrder
# ---------------------------------------------------------------------------


@dataclass
class MockOrder:
    """A simulated order managed by :class:`MockExchange`.

    Mutable so that :class:`MockExchange.process_batch` can update
    ``status`` / ``filled_qty`` / ``last_status_change_at_simulated``
    in place. The defensive safety flags
    (``simulated_only`` / ``no_live_order`` /
    ``phase_12_forbidden`` / ``trade_authority``) are validated at
    construction and re-validated on every ``to_dict()``.

    A :class:`MockOrder` NEVER carries a real exchange order id, an
    API key, an API secret, a signed-endpoint reference, or any
    runtime-tuning patch field.
    """

    order_id: str
    symbol: str
    side: str
    order_type: str
    requested_qty: float
    created_at_simulated: datetime
    status: str = MockOrderStatus.CREATED
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    client_tag: Optional[str] = None
    filled_qty: float = 0.0
    last_status_change_at_simulated: Optional[datetime] = None
    pair_with_order_id: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()
    # Hard-pinned safety markers:
    simulated_only: bool = True
    no_live_order: bool = True
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, str) or not self.order_id:
            raise ValueError("order_id must be a non-empty string")
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
        if self.status not in MockOrderStatus.ALLOWED:
            raise ValueError(
                f"status must be one of "
                f"{sorted(MockOrderStatus.ALLOWED)}, got "
                f"{self.status!r}"
            )
        self.requested_qty = _validate_positive_number(
            "requested_qty", self.requested_qty
        )
        self.filled_qty = _validate_non_negative_number(
            "filled_qty", self.filled_qty
        )
        if self.filled_qty > self.requested_qty:
            raise ValueError(
                "filled_qty must be <= requested_qty"
            )
        self.limit_price = _validate_optional_non_negative_number(
            "limit_price", self.limit_price
        )
        self.stop_price = _validate_optional_non_negative_number(
            "stop_price", self.stop_price
        )
        if self.order_type == MockOrderType.LIMIT and (
            self.limit_price is None
        ):
            raise ValueError(
                "LIMIT order requires a limit_price"
            )
        if self.order_type == MockOrderType.STOP_MARKET and (
            self.stop_price is None
        ):
            raise ValueError(
                "STOP_MARKET order requires a stop_price"
            )
        if self.order_type == MockOrderType.TAKE_PROFIT_MARKET and (
            self.stop_price is None
        ):
            raise ValueError(
                "TAKE_PROFIT_MARKET order requires a stop_price "
                "(the take-profit trigger level)"
            )
        self.created_at_simulated = ensure_utc_aware(
            self.created_at_simulated, "created_at_simulated"
        )
        if self.last_status_change_at_simulated is not None:
            self.last_status_change_at_simulated = ensure_utc_aware(
                self.last_status_change_at_simulated,
                "last_status_change_at_simulated",
            )
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
                "pair_with_order_id must be a non-empty string or None"
            )
        self.evidence_refs = _check_evidence_refs(self.evidence_refs)
        # Hard-pinned safety flags (refuse construction with any
        # other value; defensive against hostile callers).
        if self.simulated_only is not True:
            raise ValueError("simulated_only must be True")
        if self.no_live_order is not True:
            raise ValueError("no_live_order must be True")
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        if self.trade_authority is not False:
            raise ValueError("trade_authority must be False")
        if self.auto_tuning_allowed is not False:
            raise ValueError("auto_tuning_allowed must be False")

    @property
    def is_open(self) -> bool:
        return self.status in MockOrderStatus.OPEN

    @property
    def is_terminal(self) -> bool:
        return self.status in MockOrderStatus.TERMINAL

    @property
    def remaining_qty(self) -> float:
        return max(0.0, float(self.requested_qty) - float(self.filled_qty))

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "requested_qty": float(self.requested_qty),
            "filled_qty": float(self.filled_qty),
            "remaining_qty": float(self.remaining_qty),
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
            "status": self.status,
            "created_at_simulated": (
                self.created_at_simulated.isoformat()
            ),
            "last_status_change_at_simulated": (
                self.last_status_change_at_simulated.isoformat()
                if self.last_status_change_at_simulated is not None
                else None
            ),
            "client_tag": self.client_tag,
            "pair_with_order_id": self.pair_with_order_id,
            "evidence_refs": list(self.evidence_refs),
            "is_mock_order": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# MockFill
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MockFill:
    """A simulated fill produced by :class:`PessimisticFillModel`.

    Frozen / hashable. Carries the conservative-assumption markers
    that prove the fill obeys Constitution §11: every fill is
    derived from visible market data only, every fill carries a
    fee, every fill carries a slippage / latency / adverse-fill
    marker as appropriate, and no fill ever advertises a real
    exchange order id, an api key, or a signed-endpoint reference.
    """

    fill_id: str
    order_id: str
    symbol: str
    side: str
    filled_qty: float
    fill_price: float
    fee: float
    slippage_bps: float
    fill_reason: str
    filled_at_simulated: datetime
    conservative_assumption: Tuple[str, ...] = ()
    latency_bps: Optional[float] = None
    funding_impact: Optional[float] = None
    reference_price: Optional[float] = None
    evidence_refs: Tuple[str, ...] = ()
    # Hard-pinned safety markers:
    simulated_only: bool = True
    no_live_order: bool = True
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.fill_id, str) or not self.fill_id:
            raise ValueError("fill_id must be a non-empty string")
        if not isinstance(self.order_id, str) or not self.order_id:
            raise ValueError("order_id must be a non-empty string")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if self.side not in MockOrderSide.ALLOWED:
            raise ValueError(
                f"side must be one of {sorted(MockOrderSide.ALLOWED)}, "
                f"got {self.side!r}"
            )
        if self.fill_reason not in FillReason.ALLOWED:
            raise ValueError(
                f"fill_reason must be one of "
                f"{sorted(FillReason.ALLOWED)}, got "
                f"{self.fill_reason!r}"
            )
        qty = _validate_positive_number("filled_qty", self.filled_qty)
        price = _validate_positive_number("fill_price", self.fill_price)
        fee = _validate_non_negative_number("fee", self.fee)
        slip = _validate_non_negative_number(
            "slippage_bps", self.slippage_bps
        )
        latency = _validate_optional_non_negative_number(
            "latency_bps", self.latency_bps
        )
        ref_price = _validate_optional_non_negative_number(
            "reference_price", self.reference_price
        )
        funding = self.funding_impact
        if funding is not None:
            if isinstance(funding, bool) or not isinstance(
                funding, (int, float)
            ):
                raise TypeError(
                    f"funding_impact must be int / float / None, "
                    f"got {type(funding)!r}"
                )
            funding = float(funding)
        ts = ensure_utc_aware(
            self.filled_at_simulated, "filled_at_simulated"
        )
        ca = _check_conservative_assumptions(
            self.conservative_assumption
        )
        refs = _check_evidence_refs(self.evidence_refs)
        if self.simulated_only is not True:
            raise ValueError("simulated_only must be True")
        if self.no_live_order is not True:
            raise ValueError("no_live_order must be True")
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        if self.trade_authority is not False:
            raise ValueError("trade_authority must be False")
        if self.auto_tuning_allowed is not False:
            raise ValueError("auto_tuning_allowed must be False")
        object.__setattr__(self, "filled_qty", qty)
        object.__setattr__(self, "fill_price", price)
        object.__setattr__(self, "fee", fee)
        object.__setattr__(self, "slippage_bps", slip)
        object.__setattr__(self, "latency_bps", latency)
        object.__setattr__(self, "reference_price", ref_price)
        object.__setattr__(self, "funding_impact", funding)
        object.__setattr__(self, "filled_at_simulated", ts)
        object.__setattr__(self, "conservative_assumption", ca)
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "filled_qty": float(self.filled_qty),
            "fill_price": float(self.fill_price),
            "fee": float(self.fee),
            "slippage_bps": float(self.slippage_bps),
            "latency_bps": (
                float(self.latency_bps)
                if self.latency_bps is not None
                else None
            ),
            "funding_impact": (
                float(self.funding_impact)
                if self.funding_impact is not None
                else None
            ),
            "reference_price": (
                float(self.reference_price)
                if self.reference_price is not None
                else None
            ),
            "fill_reason": self.fill_reason,
            "filled_at_simulated": (
                self.filled_at_simulated.isoformat()
            ),
            "conservative_assumption": list(self.conservative_assumption),
            "evidence_refs": list(self.evidence_refs),
            "is_mock_fill": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# MockExchangeConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MockExchangeConfig:
    """Frozen configuration for the :class:`MockExchange` and the
    :class:`PessimisticFillModel`.

    All bps fields are non-negative basis points (1 bps = 0.01%).
    The frozen container guarantees downstream modules cannot mutate
    fee / slippage / latency / policy assumptions at runtime.

    Hard rules (Constitution §11):

      * ``reject_if_no_visible_price`` defaults to ``True``: an
        order without a visible price reference at evaluation time
        is rejected or marked stale, NEVER optimistically filled.
      * ``limit_touch_fill_policy`` defaults to
        ``NO_FILL_ON_TOUCH``: a price that only touches the limit
        does NOT fill; penetration is required.
      * ``ambiguous_intrabar_policy`` defaults to ``WORST_CASE``:
        same-candle stop + take-profit triggers fall back to the
        adverse stop fill. ``AMBIGUOUS`` marks both orders
        :pyattr:`MockOrderStatus.AMBIGUOUS_INTRABAR_PATH` instead.
      * ``partial_fill_enabled`` is allowed. When
        ``max_fill_fraction_per_batch`` is set (in ``(0, 1]``), each
        ``process_batch`` fills at most that fraction of the
        order's remaining quantity.
      * ``sandbox_only`` is hard-pinned ``True``,
        ``live_order_enabled`` is hard-pinned ``False``;
        construction refuses any other value.
    """

    taker_fee_bps: float = 4.0
    maker_fee_bps: float = 2.0
    default_slippage_bps: float = 5.0
    latency_penalty_bps: float = 0.0
    stale_after_seconds: float = 300.0
    reject_if_no_visible_price: bool = True
    limit_touch_fill_policy: str = (
        LimitTouchFillPolicy.NO_FILL_ON_TOUCH
    )
    ambiguous_intrabar_policy: str = (
        AmbiguousIntrabarPolicy.WORST_CASE
    )
    partial_fill_enabled: bool = True
    max_fill_fraction_per_batch: Optional[float] = None
    sandbox_only: bool = True
    live_order_enabled: bool = False

    def __post_init__(self) -> None:
        for fname, fval in (
            ("taker_fee_bps", self.taker_fee_bps),
            ("maker_fee_bps", self.maker_fee_bps),
            ("default_slippage_bps", self.default_slippage_bps),
            ("latency_penalty_bps", self.latency_penalty_bps),
            ("stale_after_seconds", self.stale_after_seconds),
        ):
            v = _validate_non_negative_number(fname, fval)
            object.__setattr__(self, fname, v)
        if self.limit_touch_fill_policy not in (
            LimitTouchFillPolicy.ALLOWED
        ):
            raise ValueError(
                f"limit_touch_fill_policy must be one of "
                f"{sorted(LimitTouchFillPolicy.ALLOWED)}, got "
                f"{self.limit_touch_fill_policy!r}"
            )
        if self.ambiguous_intrabar_policy not in (
            AmbiguousIntrabarPolicy.ALLOWED
        ):
            raise ValueError(
                f"ambiguous_intrabar_policy must be one of "
                f"{sorted(AmbiguousIntrabarPolicy.ALLOWED)}, got "
                f"{self.ambiguous_intrabar_policy!r}"
            )
        for fname, fval in (
            ("reject_if_no_visible_price", self.reject_if_no_visible_price),
            ("partial_fill_enabled", self.partial_fill_enabled),
            ("sandbox_only", self.sandbox_only),
            ("live_order_enabled", self.live_order_enabled),
        ):
            if not isinstance(fval, bool):
                raise TypeError(
                    f"{fname} must be bool, got {type(fval)!r}"
                )
        if self.sandbox_only is not True:
            raise ValueError(
                "MockExchangeConfig.sandbox_only must be True"
            )
        if self.live_order_enabled is not False:
            raise ValueError(
                "MockExchangeConfig.live_order_enabled must be False"
            )
        if self.max_fill_fraction_per_batch is not None:
            f = _validate_positive_number(
                "max_fill_fraction_per_batch",
                self.max_fill_fraction_per_batch,
            )
            if f > 1.0:
                raise ValueError(
                    "max_fill_fraction_per_batch must be <= 1.0"
                )
            object.__setattr__(self, "max_fill_fraction_per_batch", f)
        # If partial_fill_enabled=False but max_fill_fraction_per_batch
        # was set, refuse: contradictory configuration.
        if (
            not self.partial_fill_enabled
            and self.max_fill_fraction_per_batch is not None
            and self.max_fill_fraction_per_batch < 1.0
        ):
            raise ValueError(
                "max_fill_fraction_per_batch < 1.0 requires "
                "partial_fill_enabled=True"
            )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "taker_fee_bps": float(self.taker_fee_bps),
            "maker_fee_bps": float(self.maker_fee_bps),
            "default_slippage_bps": float(self.default_slippage_bps),
            "latency_penalty_bps": float(self.latency_penalty_bps),
            "stale_after_seconds": float(self.stale_after_seconds),
            "reject_if_no_visible_price": bool(
                self.reject_if_no_visible_price
            ),
            "limit_touch_fill_policy": self.limit_touch_fill_policy,
            "ambiguous_intrabar_policy": self.ambiguous_intrabar_policy,
            "partial_fill_enabled": bool(self.partial_fill_enabled),
            "max_fill_fraction_per_batch": (
                float(self.max_fill_fraction_per_batch)
                if self.max_fill_fraction_per_batch is not None
                else None
            ),
            "is_mock_exchange_config": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# FillModelDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FillModelDecision:
    """The output of a single :class:`PessimisticFillModel` evaluation.

    A decision either:

      * yields a :class:`MockFill` (``status`` advances to
        ``FILLED`` or ``PARTIALLY_FILLED``), or
      * yields a non-fill terminal status
        (``REJECTED`` / ``STALE`` / ``EXPIRED`` /
        ``AMBIGUOUS_INTRABAR_PATH``), with no :class:`MockFill`,
        or
      * leaves the order open (``status=None``, ``fill=None``).

    The decision NEVER places a real order, NEVER reaches the
    network, NEVER advertises a real exchange order id, and NEVER
    optimistically fills when visible data is insufficient.
    """

    fill: Optional[MockFill] = None
    new_status: Optional[str] = None
    reason: Optional[str] = None
    detail: Optional[str] = None

    def __post_init__(self) -> None:
        if self.new_status is not None and (
            self.new_status not in MockOrderStatus.ALLOWED
        ):
            raise ValueError(
                f"new_status must be one of "
                f"{sorted(MockOrderStatus.ALLOWED)}, got "
                f"{self.new_status!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "fill": (
                self.fill.to_dict() if self.fill is not None else None
            ),
            "new_status": self.new_status,
            "reason": self.reason,
            "detail": self.detail,
            "is_fill_model_decision": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# PessimisticFillModel
# ---------------------------------------------------------------------------


class PessimisticFillModel:
    """Strict blind walk-forward conservative fill model.

    The model is **pure / deterministic / pessimistic**:

      * It NEVER opens a network socket, signs a request, talks to
        a real exchange, the Telegram API, or any LLM.
      * It NEVER consults the wall-clock; every visible moment is
        the caller-supplied ``simulated_time``.
      * It NEVER infers tick / trade paths from a kline; whenever
        intra-bar ordering is ambiguous it falls back to the
        worst-case fill or marks the order
        :pyattr:`MockOrderStatus.AMBIGUOUS_INTRABAR_PATH`
        according to the configured
        :class:`AmbiguousIntrabarPolicy`.
      * It NEVER optimistically fills when visible price data is
        absent: the order is rejected or marked
        :pyattr:`MockOrderStatus.STALE`, never
        :pyattr:`MockOrderStatus.FILLED`.
      * It NEVER produces a real exchange order id.

    The model takes:

      * a :class:`MockOrder` (open),
      * a single :class:`HistoricalKlineRecord` (the visible
        price data) or ``None`` (insufficient visible data),
      * a :class:`MockExchangeConfig`,
      * a ``simulated_time`` (UTC-aware),
      * an optional ``ambiguous_intrabar_pair`` flag (the order
        is paired with another order whose level is also touched
        on the same kline; used by :class:`MockExchange` when
        deciding stop + take-profit pairs).

    and returns a :class:`FillModelDecision`.
    """

    def __init__(self, config: MockExchangeConfig) -> None:
        if not isinstance(config, MockExchangeConfig):
            raise TypeError(
                f"config must be MockExchangeConfig, got "
                f"{type(config)!r}"
            )
        self._config: MockExchangeConfig = config
        # Defensive tripwires (mirrors PR94 / PR95 / PR96 guards).
        self.sandbox_only: bool = True
        self.simulated_only: bool = True
        self.no_live_order: bool = True
        self.live_trading: bool = False
        self.exchange_live_orders: bool = False
        self.binance_private_api_enabled: bool = False
        self.telegram_outbound_enabled: bool = False
        self.ai_trade_authority: bool = False
        self.trade_authority: bool = False
        self.auto_tuning_allowed: bool = False
        self.phase_12_forbidden: bool = True

    # ----- public introspection -----

    @property
    def config(self) -> MockExchangeConfig:
        return self._config

    def safety_payload(self) -> Dict[str, Any]:
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        return out

    # ----- public evaluators -----

    def evaluate(
        self,
        order: MockOrder,
        kline: Optional[HistoricalKlineRecord],
        *,
        simulated_time: datetime,
        fill_id: str,
        ambiguous_intrabar_pair: bool = False,
    ) -> FillModelDecision:
        """Evaluate ``order`` against ``kline`` at ``simulated_time``.

        Returns a :class:`FillModelDecision`. The caller (typically
        :class:`MockExchange`) is responsible for applying the
        decision to the order.
        """
        if not isinstance(order, MockOrder):
            raise TypeError(
                f"order must be MockOrder, got {type(order)!r}"
            )
        if not order.is_open:
            return FillModelDecision(
                new_status=order.status,
                reason="order_already_terminal",
            )
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        if not isinstance(fill_id, str) or not fill_id:
            raise ValueError("fill_id must be a non-empty string")
        if kline is not None and not isinstance(
            kline, HistoricalKlineRecord
        ):
            raise TypeError(
                f"kline must be HistoricalKlineRecord or None, got "
                f"{type(kline)!r}"
            )
        if kline is not None and kline.symbol != order.symbol:
            raise ValueError(
                "kline symbol does not match order symbol"
            )
        # Insufficient visible price data: reject / stale / no
        # optimistic fill (Constitution §11).
        if kline is None:
            return self._handle_no_visible_price(order, sim)
        if order.order_type == MockOrderType.MARKET:
            return self._evaluate_market(
                order, kline, sim, fill_id
            )
        if order.order_type == MockOrderType.LIMIT:
            return self._evaluate_limit(
                order, kline, sim, fill_id
            )
        if order.order_type == MockOrderType.STOP_MARKET:
            return self._evaluate_stop_market(
                order,
                kline,
                sim,
                fill_id,
                ambiguous_intrabar_pair=ambiguous_intrabar_pair,
            )
        if order.order_type == MockOrderType.TAKE_PROFIT_MARKET:
            return self._evaluate_take_profit_market(
                order,
                kline,
                sim,
                fill_id,
                ambiguous_intrabar_pair=ambiguous_intrabar_pair,
            )
        if order.order_type == MockOrderType.FORCED_EXIT:
            return self._evaluate_forced_exit(
                order, kline, sim, fill_id
            )
        # Should be unreachable due to MockOrder construction
        # validation, but kept for defensive completeness.
        raise ValueError(
            f"unsupported order_type {order.order_type!r}"
        )

    # ----- internal helpers -----

    def _handle_no_visible_price(
        self,
        order: MockOrder,
        simulated_time: datetime,
    ) -> FillModelDecision:
        if self._config.reject_if_no_visible_price:
            # Distinguish stale (created earlier than now -
            # stale_after_seconds) from immediate-reject. A market
            # order that requested fill on the current bar but had no
            # visible kline at evaluation time is rejected; an order
            # that has been waiting too long becomes STALE instead.
            age_seconds = (
                simulated_time - order.created_at_simulated
            ).total_seconds()
            if age_seconds >= self._config.stale_after_seconds:
                return FillModelDecision(
                    new_status=MockOrderStatus.STALE,
                    reason=(
                        ConservativeAssumption
                        .NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA
                    ),
                    detail=(
                        f"order age {age_seconds:.1f}s >= "
                        f"stale_after_seconds "
                        f"{self._config.stale_after_seconds:.1f}s "
                        f"and no visible price"
                    ),
                )
            return FillModelDecision(
                new_status=MockOrderStatus.REJECTED,
                reason=(
                    ConservativeAssumption
                    .NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA
                ),
                detail="no visible price reference for fill",
            )
        # If the operator has explicitly disabled the conservative
        # rule, the order remains open without any optimistic fill.
        return FillModelDecision(
            new_status=None,
            reason="no_visible_price_remaining_open",
        )

    def _eligible_qty(self, order: MockOrder) -> float:
        remaining = order.remaining_qty
        if not self._config.partial_fill_enabled:
            return remaining
        cap = self._config.max_fill_fraction_per_batch
        if cap is None:
            return remaining
        # cap fraction is per BATCH, applied to remaining qty.
        capped = order.requested_qty * float(cap)
        return min(remaining, capped) if capped > 0.0 else 0.0

    def _resolve_status_after_fill(
        self,
        order: MockOrder,
        eligible_qty: float,
    ) -> str:
        new_filled = order.filled_qty + eligible_qty
        if new_filled + 1e-12 >= order.requested_qty:
            return MockOrderStatus.FILLED
        return MockOrderStatus.PARTIALLY_FILLED

    def _conservative_assumptions_for_fees(
        self,
        *,
        slippage_applied: bool,
        latency_applied: bool,
        partial: bool,
        extras: Iterable[str] = (),
    ) -> Tuple[str, ...]:
        out: List[str] = [ConservativeAssumption.TAKER_FEE_APPLIED]
        if slippage_applied:
            out.append(ConservativeAssumption.SLIPPAGE_APPLIED)
        if latency_applied:
            out.append(ConservativeAssumption.LATENCY_PENALTY_APPLIED)
        for e in extras:
            if e not in out:
                out.append(e)
        if partial:
            out.append(ConservativeAssumption.PARTIAL_FILL)
        return tuple(out)

    def _adverse_market_price(
        self,
        side: str,
        reference_price: float,
        slippage_bps: float,
        latency_bps: float,
    ) -> float:
        """Return the adverse-side market price.

        For BUY: ``reference * (1 + (slippage + latency) bps)``.
        For SELL: ``reference * (1 - (slippage + latency) bps)``.
        """
        total_bps = float(slippage_bps) + float(latency_bps)
        frac = _bps_to_fraction(total_bps)
        if side == MockOrderSide.BUY:
            return float(reference_price) * (1.0 + frac)
        return float(reference_price) * (1.0 - frac)

    def _compute_fee(
        self, fill_price: float, filled_qty: float, fee_bps: float
    ) -> float:
        return float(fill_price) * float(filled_qty) * _bps_to_fraction(
            fee_bps
        )

    # ----- order-type evaluators -----

    def _evaluate_market(
        self,
        order: MockOrder,
        kline: HistoricalKlineRecord,
        simulated_time: datetime,
        fill_id: str,
    ) -> FillModelDecision:
        cfg = self._config
        ref_price = float(kline.close)
        slippage = float(cfg.default_slippage_bps)
        latency = float(cfg.latency_penalty_bps)
        latency_applied = latency > 0.0
        fill_price = self._adverse_market_price(
            order.side, ref_price, slippage, latency
        )
        eligible = self._eligible_qty(order)
        if eligible <= 0.0:
            return FillModelDecision(
                new_status=None,
                reason="no_eligible_qty_this_batch",
            )
        new_status = self._resolve_status_after_fill(order, eligible)
        partial = new_status == MockOrderStatus.PARTIALLY_FILLED
        fee = self._compute_fee(
            fill_price, eligible, cfg.taker_fee_bps
        )
        ca = self._conservative_assumptions_for_fees(
            slippage_applied=slippage > 0.0,
            latency_applied=latency_applied,
            partial=partial,
        )
        fill = MockFill(
            fill_id=fill_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            filled_qty=eligible,
            fill_price=fill_price,
            fee=fee,
            slippage_bps=slippage,
            latency_bps=latency if latency_applied else None,
            reference_price=ref_price,
            fill_reason=FillReason.MARKET_FILL,
            filled_at_simulated=simulated_time,
            conservative_assumption=ca,
        )
        return FillModelDecision(
            fill=fill, new_status=new_status, reason="market_fill"
        )

    def _evaluate_limit(
        self,
        order: MockOrder,
        kline: HistoricalKlineRecord,
        simulated_time: datetime,
        fill_id: str,
    ) -> FillModelDecision:
        cfg = self._config
        if order.limit_price is None:
            return FillModelDecision(
                new_status=MockOrderStatus.REJECTED,
                reason="limit_price_missing",
            )
        limit = float(order.limit_price)
        kline_low = float(kline.low)
        kline_high = float(kline.high)
        # Conservative limit rules:
        #  - BUY limit fills only when the kline's low strictly
        #    PENETRATES below the limit (price < limit). Touch-only
        #    (low == limit) does NOT fill under NO_FILL_ON_TOUCH.
        #  - SELL limit fills only when the kline's high strictly
        #    PENETRATES above the limit (price > limit). Touch-only
        #    does NOT fill under NO_FILL_ON_TOUCH.
        touched_only = False
        penetrated = False
        if order.side == MockOrderSide.BUY:
            if kline_low < limit:
                penetrated = True
            elif kline_low == limit:
                touched_only = True
        else:  # SELL
            if kline_high > limit:
                penetrated = True
            elif kline_high == limit:
                touched_only = True
        if not penetrated:
            if touched_only and cfg.limit_touch_fill_policy == (
                LimitTouchFillPolicy.NO_FILL_ON_TOUCH
            ):
                return FillModelDecision(
                    new_status=None,
                    reason="limit_touched_only_no_fill",
                )
            if touched_only and cfg.limit_touch_fill_policy == (
                LimitTouchFillPolicy.ALLOW_FILL_ON_TOUCH
            ):
                pass  # fall through to fill at the limit
            else:
                return FillModelDecision(
                    new_status=None,
                    reason="limit_not_reached",
                )
        # Fill price = limit (the conservative best-case trade
        # price for the resting order). We add a latency penalty
        # adverse to the order's side if configured.
        latency = float(cfg.latency_penalty_bps)
        latency_applied = latency > 0.0
        fill_price = limit
        if latency_applied:
            fill_price = self._adverse_market_price(
                order.side, fill_price, 0.0, latency
            )
        eligible = self._eligible_qty(order)
        if eligible <= 0.0:
            return FillModelDecision(
                new_status=None,
                reason="no_eligible_qty_this_batch",
            )
        new_status = self._resolve_status_after_fill(order, eligible)
        partial = new_status == MockOrderStatus.PARTIALLY_FILLED
        # Limit orders post; conservative v0 charges the maker fee
        # (limit orders typically rest in the book and the model
        # is intentionally not advertising "free maker rebate").
        fee = self._compute_fee(
            fill_price, eligible, cfg.maker_fee_bps
        )
        ca: List[str] = [ConservativeAssumption.TAKER_FEE_APPLIED]
        # The taker-fee marker doubles as "fee applied"; for limit
        # orders we additionally surface the penetration marker.
        ca.append(ConservativeAssumption.LIMIT_PENETRATION_REQUIRED)
        if latency_applied:
            ca.append(ConservativeAssumption.LATENCY_PENALTY_APPLIED)
        if partial:
            ca.append(ConservativeAssumption.PARTIAL_FILL)
        fill = MockFill(
            fill_id=fill_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            filled_qty=eligible,
            fill_price=fill_price,
            fee=fee,
            slippage_bps=0.0,
            latency_bps=latency if latency_applied else None,
            reference_price=limit,
            fill_reason=FillReason.LIMIT_FILL_ON_PENETRATION,
            filled_at_simulated=simulated_time,
            conservative_assumption=tuple(ca),
        )
        return FillModelDecision(
            fill=fill,
            new_status=new_status,
            reason="limit_fill_on_penetration",
        )

    def _stop_triggered(
        self, order: MockOrder, kline: HistoricalKlineRecord
    ) -> bool:
        if order.stop_price is None:
            return False
        sp = float(order.stop_price)
        # Stop triggers when kline range crosses the stop level.
        # For a BUY stop (e.g., stop-loss to cover a short), the
        # stop triggers when high >= stop. For a SELL stop (e.g.,
        # stop-loss to close a long), the stop triggers when
        # low <= stop.
        if order.side == MockOrderSide.BUY:
            return float(kline.high) >= sp
        return float(kline.low) <= sp

    def _take_profit_triggered(
        self, order: MockOrder, kline: HistoricalKlineRecord
    ) -> bool:
        if order.stop_price is None:
            return False
        tp = float(order.stop_price)
        # Take-profit triggers when the kline range reaches the TP
        # level on the favorable side. For a SELL take-profit
        # (long position locking gain), high >= tp triggers. For a
        # BUY take-profit (short position locking gain), low <= tp
        # triggers.
        if order.side == MockOrderSide.SELL:
            return float(kline.high) >= tp
        return float(kline.low) <= tp

    def _evaluate_stop_market(
        self,
        order: MockOrder,
        kline: HistoricalKlineRecord,
        simulated_time: datetime,
        fill_id: str,
        *,
        ambiguous_intrabar_pair: bool = False,
    ) -> FillModelDecision:
        cfg = self._config
        if not self._stop_triggered(order, kline):
            return FillModelDecision(
                new_status=None, reason="stop_not_triggered"
            )
        if ambiguous_intrabar_pair and cfg.ambiguous_intrabar_policy == (
            AmbiguousIntrabarPolicy.AMBIGUOUS
        ):
            return FillModelDecision(
                new_status=MockOrderStatus.AMBIGUOUS_INTRABAR_PATH,
                reason="ambiguous_intrabar_path",
                detail=(
                    "stop and take-profit both triggered on the "
                    "same kline; AmbiguousIntrabarPolicy=AMBIGUOUS"
                ),
            )
        # Pessimistic stop fill: fill at the stop price moved
        # adverse by slippage + latency. For a SELL stop (closing a
        # long), adverse means fill is BELOW stop (worse than the
        # stop level). For a BUY stop (covering a short), adverse
        # means fill is ABOVE stop.
        slippage = float(cfg.default_slippage_bps)
        latency = float(cfg.latency_penalty_bps)
        latency_applied = latency > 0.0
        ref_price = float(order.stop_price)
        fill_price = self._adverse_market_price(
            order.side, ref_price, slippage, latency
        )
        eligible = self._eligible_qty(order)
        if eligible <= 0.0:
            return FillModelDecision(
                new_status=None,
                reason="no_eligible_qty_this_batch",
            )
        new_status = self._resolve_status_after_fill(order, eligible)
        partial = new_status == MockOrderStatus.PARTIALLY_FILLED
        fee = self._compute_fee(
            fill_price, eligible, cfg.taker_fee_bps
        )
        extras = [ConservativeAssumption.STOP_ADVERSE_FILL]
        reason = "stop_triggered_fill"
        fill_reason = FillReason.STOP_TRIGGERED_FILL
        if ambiguous_intrabar_pair and cfg.ambiguous_intrabar_policy == (
            AmbiguousIntrabarPolicy.WORST_CASE
        ):
            extras.append(
                ConservativeAssumption.AMBIGUOUS_INTRABAR_WORST_CASE
            )
            fill_reason = (
                FillReason.AMBIGUOUS_WORST_CASE_STOP_FILL
            )
            reason = "ambiguous_intrabar_worst_case_stop_fill"
        ca = self._conservative_assumptions_for_fees(
            slippage_applied=slippage > 0.0,
            latency_applied=latency_applied,
            partial=partial,
            extras=extras,
        )
        fill = MockFill(
            fill_id=fill_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            filled_qty=eligible,
            fill_price=fill_price,
            fee=fee,
            slippage_bps=slippage,
            latency_bps=latency if latency_applied else None,
            reference_price=ref_price,
            fill_reason=fill_reason,
            filled_at_simulated=simulated_time,
            conservative_assumption=ca,
        )
        return FillModelDecision(
            fill=fill, new_status=new_status, reason=reason
        )

    def _evaluate_take_profit_market(
        self,
        order: MockOrder,
        kline: HistoricalKlineRecord,
        simulated_time: datetime,
        fill_id: str,
        *,
        ambiguous_intrabar_pair: bool = False,
    ) -> FillModelDecision:
        cfg = self._config
        if not self._take_profit_triggered(order, kline):
            return FillModelDecision(
                new_status=None,
                reason="take_profit_not_triggered",
            )
        if ambiguous_intrabar_pair and cfg.ambiguous_intrabar_policy == (
            AmbiguousIntrabarPolicy.AMBIGUOUS
        ):
            return FillModelDecision(
                new_status=MockOrderStatus.AMBIGUOUS_INTRABAR_PATH,
                reason="ambiguous_intrabar_path",
                detail=(
                    "take-profit and stop both triggered on the "
                    "same kline; AmbiguousIntrabarPolicy=AMBIGUOUS"
                ),
            )
        if ambiguous_intrabar_pair and cfg.ambiguous_intrabar_policy == (
            AmbiguousIntrabarPolicy.WORST_CASE
        ):
            # WORST_CASE: the stop is taken; the take-profit order is
            # canceled (fill is NOT realised on the favorable level
            # because we cannot prove the favorable level was hit
            # first within the bar).
            return FillModelDecision(
                new_status=MockOrderStatus.CANCELED,
                reason="ambiguous_intrabar_worst_case_take_profit_canceled",
                detail=(
                    "take-profit canceled because the stop on the "
                    "paired order was assumed to fire first under "
                    "AmbiguousIntrabarPolicy=WORST_CASE"
                ),
            )
        # Conservative TP fill: fill at the trigger level moved
        # adverse to the TP side by slippage + latency. For a SELL
        # TP, adverse means fill is BELOW the TP price; for a BUY
        # TP, adverse means fill is ABOVE the TP price.
        slippage = float(cfg.default_slippage_bps)
        latency = float(cfg.latency_penalty_bps)
        latency_applied = latency > 0.0
        ref_price = float(order.stop_price)
        fill_price = self._adverse_market_price(
            order.side, ref_price, slippage, latency
        )
        eligible = self._eligible_qty(order)
        if eligible <= 0.0:
            return FillModelDecision(
                new_status=None,
                reason="no_eligible_qty_this_batch",
            )
        new_status = self._resolve_status_after_fill(order, eligible)
        partial = new_status == MockOrderStatus.PARTIALLY_FILLED
        fee = self._compute_fee(
            fill_price, eligible, cfg.taker_fee_bps
        )
        extras = [
            ConservativeAssumption.TAKE_PROFIT_CONSERVATIVE_FILL
        ]
        ca = self._conservative_assumptions_for_fees(
            slippage_applied=slippage > 0.0,
            latency_applied=latency_applied,
            partial=partial,
            extras=extras,
        )
        fill = MockFill(
            fill_id=fill_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            filled_qty=eligible,
            fill_price=fill_price,
            fee=fee,
            slippage_bps=slippage,
            latency_bps=latency if latency_applied else None,
            reference_price=ref_price,
            fill_reason=FillReason.TAKE_PROFIT_TRIGGERED_FILL,
            filled_at_simulated=simulated_time,
            conservative_assumption=ca,
        )
        return FillModelDecision(
            fill=fill,
            new_status=new_status,
            reason="take_profit_triggered_fill",
        )

    def _evaluate_forced_exit(
        self,
        order: MockOrder,
        kline: HistoricalKlineRecord,
        simulated_time: datetime,
        fill_id: str,
    ) -> FillModelDecision:
        cfg = self._config
        ref_price = float(kline.close)
        slippage = float(cfg.default_slippage_bps)
        latency = float(cfg.latency_penalty_bps)
        latency_applied = latency > 0.0
        fill_price = self._adverse_market_price(
            order.side, ref_price, slippage, latency
        )
        eligible = self._eligible_qty(order)
        if eligible <= 0.0:
            return FillModelDecision(
                new_status=None,
                reason="no_eligible_qty_this_batch",
            )
        new_status = self._resolve_status_after_fill(order, eligible)
        partial = new_status == MockOrderStatus.PARTIALLY_FILLED
        fee = self._compute_fee(
            fill_price, eligible, cfg.taker_fee_bps
        )
        extras = [
            ConservativeAssumption.FORCED_EXIT_CONSERVATIVE_FILL
        ]
        ca = self._conservative_assumptions_for_fees(
            slippage_applied=slippage > 0.0,
            latency_applied=latency_applied,
            partial=partial,
            extras=extras,
        )
        fill = MockFill(
            fill_id=fill_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            filled_qty=eligible,
            fill_price=fill_price,
            fee=fee,
            slippage_bps=slippage,
            latency_bps=latency if latency_applied else None,
            reference_price=ref_price,
            fill_reason=FillReason.FORCED_EXIT_FILL,
            filled_at_simulated=simulated_time,
            conservative_assumption=ca,
        )
        return FillModelDecision(
            fill=fill,
            new_status=new_status,
            reason="forced_exit_fill",
        )


__all__ = [
    "PHASE_NAME",
    "AmbiguousIntrabarPolicy",
    "ConservativeAssumption",
    "FillModelDecision",
    "FillReason",
    "LimitTouchFillPolicy",
    "MockExchangeConfig",
    "MockFill",
    "MockOrder",
    "MockOrderSide",
    "MockOrderStatus",
    "MockOrderType",
    "PessimisticFillModel",
]
