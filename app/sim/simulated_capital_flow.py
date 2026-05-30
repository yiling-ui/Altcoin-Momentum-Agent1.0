"""Simulated Capital Flow Engine v0 for Phase 11C.1D-D-E (PR98 -
Simulated Capital Flow + Trade Ledger v0).

Strict blind walk-forward simulated capital accounting / position
book / equity timeseries. This module is the **fifth**
anti-future-lookahead infrastructure block of the strict blind
walk-forward stack defined by Phase 11C.1D-D (the *Strict Blind
Walk-forward Sim-Live Constitution*, PR93). It builds strictly on
top of the PR94 substrate (:class:`SimulationClock`,
:class:`HistoricalRecordTime`, :class:`TimeWallGuard`,
:class:`CandleVisibilityGuard`, :class:`NoLookaheadViolation`,
:func:`assert_no_forbidden_fields`), the PR95 substrate
(:class:`HistoricalMarketStore`, :class:`HistoricalKlineRecord`,
:class:`HistoricalMarketRecordType`), the PR96 substrate
(:class:`ReplayFeedBatch`, :class:`ReplayFeedProvider`,
:class:`ReplayFeedProviderConfig`), and the PR97 substrate
(:class:`MockExchange`, :class:`MockExchangeConfig`,
:class:`MockOrder`, :class:`MockFill`, :class:`MockOrderStatus`,
:class:`PessimisticFillModel`).

Constitution §12: the Simulated Capital Flow consumes
:class:`MockOrder` / :class:`MockFill` lifecycle outputs only. It
NEVER calls a real exchange endpoint, NEVER signs a request,
NEVER touches the Binance private API, NEVER opens a private
websocket, NEVER fetches account / order / position / leverage /
margin endpoints, and NEVER advertises a real account id, a real
exchange order id, an api key, an api secret, or a
signed-endpoint reference.

Hard safety boundary (Phase 11C.1D-D-E / PR98):

  - mode = paper
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
  - live_trading = False
  - live_capital_enabled = False
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
  - emit a real exchange order id, a real account id, an api key,
    an api secret, or a signed-endpoint reference
  - authorize live trading or auto-tuning
  - enter Phase 12

The Simulated Capital Flow is NOT responsible for:

  - the Telegram Sandbox Outbox (PR99),
  - the Blind Walk-forward Runner (PR100),
  - real Risk Engine decisions,
  - real Execution FSM wiring.

PR98 acceptance authorises ONLY PR99 (*Telegram Sandbox Outbox*) to
begin its own gate. Phase 12 remains FORBIDDEN.

Notes on closed-vocabulary fields:

  * :pyattr:`SimulatedPosition.side` is a paper-only descriptor of
    the simulated position's direction (``LONG`` / ``SHORT``). It
    is NEVER an AI / strategy recommendation, NEVER a trade
    authority signal, NEVER a runtime config patch.
  * :pyattr:`SimulatedCapitalState.risk_state` is a closed
    descriptive string drawn from :class:`RiskFreezeReason` /
    ``"NORMAL"``. It is NEVER a runtime config patch.
"""

from __future__ import annotations

import json
import math
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

from app.sim.pessimistic_fill_model import (
    ConservativeAssumption,
    FillReason,
    MockFill,
    MockOrder,
    MockOrderSide,
    MockOrderStatus,
    MockOrderType,
)
from app.sim.replay_feed_provider import ReplayFeedBatch
from app.sim.simulation_clock import ensure_utc_aware
from app.sim.time_wall_guard import assert_no_forbidden_fields
from app.sim.trade_ledger import (
    EquityTimeseriesPoint,
    TradeFailureFlag,
    TradeLedger,
    TradeLedgerEntry,
    TradeOutcome,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-E / PR98 / Simulated Capital Flow + Trade "
    "Ledger v0"
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
        "live_capital_enabled": False,
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
        "is_simulated_capital_payload": True,
        "is_real_account": False,
        "is_runtime_patch": False,
    }


def _validate_finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{name} must be int / float, got {type(value)!r}"
        )
    f = float(value)
    if not math.isfinite(f):
        raise ValueError(f"{name} must be finite, got {f!r}")
    return f


def _validate_non_negative(name: str, value: Any) -> float:
    f = _validate_finite(name, value)
    if f < 0.0:
        raise ValueError(f"{name} must be >= 0, got {f!r}")
    return f


def _validate_unit_fraction(name: str, value: Any) -> float:
    f = _validate_finite(name, value)
    if f < 0.0 or f > 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {f!r}")
    return f


def _check_str_tuple(values: Iterable[Any], field_name: str) -> Tuple[str, ...]:
    out: List[str] = []
    for v in values:
        if not isinstance(v, str):
            raise TypeError(
                f"{field_name} entries must be strings, got "
                f"{type(v)!r}"
            )
        out.append(v)
    return tuple(out)


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


class PositionSide:
    """Closed taxonomy of simulated position directions.

    Paper-only descriptor of the simulated position's direction.
    NEVER an AI / strategy recommendation, NEVER a trade authority
    signal, NEVER a runtime config patch.
    """

    LONG: str = "LONG"
    SHORT: str = "SHORT"

    ALLOWED: FrozenSet[str] = frozenset({LONG, SHORT})


class PositionStatus:
    """Closed taxonomy of simulated position lifecycle statuses."""

    OPEN: str = "OPEN"
    CLOSED: str = "CLOSED"

    ALLOWED: FrozenSet[str] = frozenset({OPEN, CLOSED})


class RiskFreezeReason:
    """Closed taxonomy of capital-freeze reasons.

    Descriptive only. NEVER a runtime config patch.
    """

    NORMAL: str = "NORMAL"
    MAX_DRAWDOWN_EXCEEDED: str = "MAX_DRAWDOWN_EXCEEDED"
    CONSECUTIVE_LOSS_PAUSE: str = "CONSECUTIVE_LOSS_PAUSE"
    LIQUIDATION_STRESS: str = "LIQUIDATION_STRESS"
    MANUAL_FREEZE: str = "MANUAL_FREEZE"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            NORMAL,
            MAX_DRAWDOWN_EXCEEDED,
            CONSECUTIVE_LOSS_PAUSE,
            LIQUIDATION_STRESS,
            MANUAL_FREEZE,
        }
    )


# ---------------------------------------------------------------------------
# SimulatedCapitalConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulatedCapitalConfig:
    """Frozen configuration for a :class:`SimulatedCapitalFlowEngine`.

    The frozen container guarantees downstream modules cannot mutate
    capital / risk-budget / freeze-threshold assumptions at runtime.
    """

    initial_capital: float
    base_currency: str = "USDT"
    max_active_positions: int = 5
    max_symbol_exposure_pct: float = 0.25
    max_regime_exposure_pct: Optional[float] = None
    single_trade_risk_budget_pct: float = 0.02
    profit_lock_fraction: float = 0.0
    locked_profit_reuse_allowed: bool = False
    consecutive_loss_pause_threshold: Optional[int] = None
    max_drawdown_pause_pct: Optional[float] = None
    paper_liquidation_stress_enabled: bool = True
    # Hard-pinned safety markers:
    sandbox_only: bool = True
    live_capital_enabled: bool = False

    def __post_init__(self) -> None:
        ic = _validate_finite("initial_capital", self.initial_capital)
        if ic <= 0.0:
            raise ValueError("initial_capital must be > 0")
        if not isinstance(self.base_currency, str) or not self.base_currency:
            raise ValueError("base_currency must be a non-empty string")
        if (
            not isinstance(self.max_active_positions, int)
            or isinstance(self.max_active_positions, bool)
        ):
            raise TypeError("max_active_positions must be int")
        if self.max_active_positions <= 0:
            raise ValueError("max_active_positions must be > 0")
        msx = _validate_unit_fraction(
            "max_symbol_exposure_pct", self.max_symbol_exposure_pct
        )
        if msx <= 0.0:
            raise ValueError("max_symbol_exposure_pct must be > 0")
        mrx: Optional[float] = None
        if self.max_regime_exposure_pct is not None:
            mrx = _validate_unit_fraction(
                "max_regime_exposure_pct", self.max_regime_exposure_pct
            )
            if mrx <= 0.0:
                raise ValueError(
                    "max_regime_exposure_pct must be > 0 or None"
                )
        strb = _validate_unit_fraction(
            "single_trade_risk_budget_pct",
            self.single_trade_risk_budget_pct,
        )
        if strb <= 0.0:
            raise ValueError("single_trade_risk_budget_pct must be > 0")
        plf = _validate_unit_fraction(
            "profit_lock_fraction", self.profit_lock_fraction
        )
        if not isinstance(self.locked_profit_reuse_allowed, bool):
            raise TypeError("locked_profit_reuse_allowed must be bool")
        clpt: Optional[int] = None
        if self.consecutive_loss_pause_threshold is not None:
            if (
                not isinstance(
                    self.consecutive_loss_pause_threshold, int
                )
                or isinstance(
                    self.consecutive_loss_pause_threshold, bool
                )
            ):
                raise TypeError(
                    "consecutive_loss_pause_threshold must be int or None"
                )
            if self.consecutive_loss_pause_threshold <= 0:
                raise ValueError(
                    "consecutive_loss_pause_threshold must be > 0 or None"
                )
            clpt = self.consecutive_loss_pause_threshold
        mdpp: Optional[float] = None
        if self.max_drawdown_pause_pct is not None:
            mdpp = _validate_unit_fraction(
                "max_drawdown_pause_pct", self.max_drawdown_pause_pct
            )
            if mdpp <= 0.0:
                raise ValueError(
                    "max_drawdown_pause_pct must be > 0 or None"
                )
        if not isinstance(self.paper_liquidation_stress_enabled, bool):
            raise TypeError(
                "paper_liquidation_stress_enabled must be bool"
            )
        if self.sandbox_only is not True:
            raise ValueError("sandbox_only must be True")
        if self.live_capital_enabled is not False:
            raise ValueError("live_capital_enabled must be False")
        object.__setattr__(self, "initial_capital", ic)
        object.__setattr__(self, "max_symbol_exposure_pct", msx)
        object.__setattr__(self, "max_regime_exposure_pct", mrx)
        object.__setattr__(self, "single_trade_risk_budget_pct", strb)
        object.__setattr__(self, "profit_lock_fraction", plf)
        object.__setattr__(
            self, "consecutive_loss_pause_threshold", clpt
        )
        object.__setattr__(self, "max_drawdown_pause_pct", mdpp)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "initial_capital": float(self.initial_capital),
            "base_currency": self.base_currency,
            "max_active_positions": int(self.max_active_positions),
            "max_symbol_exposure_pct": float(
                self.max_symbol_exposure_pct
            ),
            "max_regime_exposure_pct": (
                float(self.max_regime_exposure_pct)
                if self.max_regime_exposure_pct is not None
                else None
            ),
            "single_trade_risk_budget_pct": float(
                self.single_trade_risk_budget_pct
            ),
            "profit_lock_fraction": float(self.profit_lock_fraction),
            "locked_profit_reuse_allowed": bool(
                self.locked_profit_reuse_allowed
            ),
            "consecutive_loss_pause_threshold": (
                int(self.consecutive_loss_pause_threshold)
                if self.consecutive_loss_pause_threshold is not None
                else None
            ),
            "max_drawdown_pause_pct": (
                float(self.max_drawdown_pause_pct)
                if self.max_drawdown_pause_pct is not None
                else None
            ),
            "paper_liquidation_stress_enabled": bool(
                self.paper_liquidation_stress_enabled
            ),
            "is_simulated_capital_config": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# SimulatedPosition
# ---------------------------------------------------------------------------


@dataclass
class SimulatedPosition:
    """A mutable simulated position book entry.

    Mutated by :class:`SimulatedCapitalFlowEngine` as fills arrive.
    Hard-pinned safety markers cannot be flipped through the
    constructor.
    """

    position_id: str
    symbol: str
    side: str
    qty: float
    avg_entry_price: float
    opened_at_simulated: datetime
    updated_at_simulated: datetime
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_paid: float = 0.0
    slippage_paid: float = 0.0
    funding_paid: float = 0.0
    status: str = PositionStatus.OPEN
    evidence_refs: Tuple[str, ...] = ()
    max_favorable_excursion: float = 0.0
    max_drawdown_during_trade: float = 0.0
    # Hard-pinned safety markers:
    simulated_only: bool = True
    no_live_order: bool = True
    live_capital_enabled: bool = False
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.position_id, str) or not self.position_id:
            raise ValueError("position_id must be a non-empty string")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if self.side not in PositionSide.ALLOWED:
            raise ValueError(
                f"side must be one of {sorted(PositionSide.ALLOWED)}, "
                f"got {self.side!r}"
            )
        if self.status not in PositionStatus.ALLOWED:
            raise ValueError(
                f"status must be one of "
                f"{sorted(PositionStatus.ALLOWED)}, got {self.status!r}"
            )
        qty = _validate_non_negative("qty", self.qty)
        aep = _validate_non_negative("avg_entry_price", self.avg_entry_price)
        oa = ensure_utc_aware(
            self.opened_at_simulated, "opened_at_simulated"
        )
        ua = ensure_utc_aware(
            self.updated_at_simulated, "updated_at_simulated"
        )
        if ua < oa:
            raise ValueError(
                "updated_at_simulated must be >= opened_at_simulated"
            )
        rp = _validate_finite("realized_pnl", self.realized_pnl)
        upnl = _validate_finite("unrealized_pnl", self.unrealized_pnl)
        fp = _validate_non_negative("fees_paid", self.fees_paid)
        sp = _validate_non_negative("slippage_paid", self.slippage_paid)
        fu = _validate_finite("funding_paid", self.funding_paid)
        refs = _check_str_tuple(self.evidence_refs, "evidence_refs")
        mfe = _validate_finite(
            "max_favorable_excursion", self.max_favorable_excursion
        )
        mae = _validate_non_negative(
            "max_drawdown_during_trade", self.max_drawdown_during_trade
        )
        if self.simulated_only is not True:
            raise ValueError("simulated_only must be True")
        if self.no_live_order is not True:
            raise ValueError("no_live_order must be True")
        if self.live_capital_enabled is not False:
            raise ValueError("live_capital_enabled must be False")
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        if self.trade_authority is not False:
            raise ValueError("trade_authority must be False")
        if self.auto_tuning_allowed is not False:
            raise ValueError("auto_tuning_allowed must be False")
        self.qty = qty
        self.avg_entry_price = aep
        self.opened_at_simulated = oa
        self.updated_at_simulated = ua
        self.realized_pnl = rp
        self.unrealized_pnl = upnl
        self.fees_paid = fp
        self.slippage_paid = sp
        self.funding_paid = fu
        self.evidence_refs = refs
        self.max_favorable_excursion = mfe
        self.max_drawdown_during_trade = mae

    @property
    def notional(self) -> float:
        return float(self.qty) * float(self.avg_entry_price)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": float(self.qty),
            "avg_entry_price": float(self.avg_entry_price),
            "opened_at_simulated": self.opened_at_simulated.isoformat(),
            "updated_at_simulated": self.updated_at_simulated.isoformat(),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "fees_paid": float(self.fees_paid),
            "slippage_paid": float(self.slippage_paid),
            "funding_paid": float(self.funding_paid),
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "max_favorable_excursion": float(self.max_favorable_excursion),
            "max_drawdown_during_trade": float(
                self.max_drawdown_during_trade
            ),
            "is_simulated_position": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# SimulatedCapitalState
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulatedCapitalState:
    """Frozen snapshot of the simulated capital state at a moment in
    simulated time. Hard-pinned safety markers cannot be flipped
    through the constructor.
    """

    timestamp: datetime
    initial_capital: float
    exchange_equity: float
    locked_profit: float
    open_risk: float
    unrealized_pnl: float
    realized_pnl: float
    total_lifetime_equity: float
    drawdown: float
    active_positions: int
    risk_state: str
    capital_frozen: bool
    freeze_reason: Optional[str] = None
    # Hard-pinned safety markers:
    simulated_only: bool = True
    no_live_order: bool = True
    live_capital_enabled: bool = False
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        ts = ensure_utc_aware(self.timestamp, "timestamp")
        ic = _validate_finite("initial_capital", self.initial_capital)
        eq = _validate_finite("exchange_equity", self.exchange_equity)
        lp = _validate_non_negative("locked_profit", self.locked_profit)
        risk = _validate_non_negative("open_risk", self.open_risk)
        upnl = _validate_finite("unrealized_pnl", self.unrealized_pnl)
        rpnl = _validate_finite("realized_pnl", self.realized_pnl)
        tle = _validate_finite(
            "total_lifetime_equity", self.total_lifetime_equity
        )
        dd = _validate_non_negative("drawdown", self.drawdown)
        if (
            not isinstance(self.active_positions, int)
            or isinstance(self.active_positions, bool)
        ):
            raise TypeError("active_positions must be int")
        if self.active_positions < 0:
            raise ValueError("active_positions must be >= 0")
        if self.risk_state not in RiskFreezeReason.ALLOWED:
            raise ValueError(
                f"risk_state must be one of "
                f"{sorted(RiskFreezeReason.ALLOWED)}, got "
                f"{self.risk_state!r}"
            )
        if not isinstance(self.capital_frozen, bool):
            raise TypeError("capital_frozen must be bool")
        if self.freeze_reason is not None:
            if self.freeze_reason not in RiskFreezeReason.ALLOWED:
                raise ValueError(
                    f"freeze_reason must be one of "
                    f"{sorted(RiskFreezeReason.ALLOWED)} or None, got "
                    f"{self.freeze_reason!r}"
                )
        if self.simulated_only is not True:
            raise ValueError("simulated_only must be True")
        if self.no_live_order is not True:
            raise ValueError("no_live_order must be True")
        if self.live_capital_enabled is not False:
            raise ValueError("live_capital_enabled must be False")
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        if self.trade_authority is not False:
            raise ValueError("trade_authority must be False")
        if self.auto_tuning_allowed is not False:
            raise ValueError("auto_tuning_allowed must be False")
        object.__setattr__(self, "timestamp", ts)
        object.__setattr__(self, "initial_capital", ic)
        object.__setattr__(self, "exchange_equity", eq)
        object.__setattr__(self, "locked_profit", lp)
        object.__setattr__(self, "open_risk", risk)
        object.__setattr__(self, "unrealized_pnl", upnl)
        object.__setattr__(self, "realized_pnl", rpnl)
        object.__setattr__(self, "total_lifetime_equity", tle)
        object.__setattr__(self, "drawdown", dd)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(),
            "initial_capital": float(self.initial_capital),
            "exchange_equity": float(self.exchange_equity),
            "locked_profit": float(self.locked_profit),
            "open_risk": float(self.open_risk),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "total_lifetime_equity": float(self.total_lifetime_equity),
            "drawdown": float(self.drawdown),
            "active_positions": int(self.active_positions),
            "risk_state": self.risk_state,
            "capital_frozen": bool(self.capital_frozen),
            "freeze_reason": self.freeze_reason,
            "is_simulated_capital_state": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# Internal trade-tracker (per open position)
# ---------------------------------------------------------------------------


@dataclass
class _OpenTradeContext:
    """Per-open-position bookkeeping the engine maintains across the
    open / reduce / close lifecycle. NOT serialised; internal only.
    """

    trade_id: str
    symbol: str
    entry_time: datetime
    entry_reason: str
    order_type: str
    requested_qty: float = 0.0
    filled_qty: float = 0.0
    avg_fill_price_num: float = 0.0  # sum(price * qty) on entry side
    avg_fill_price_den: float = 0.0  # sum(qty) on entry side
    slippage_bps_sum: float = 0.0
    slippage_bps_count: int = 0
    fee_total: float = 0.0
    funding_total: float = 0.0
    realized_pnl_gross: float = 0.0
    max_favorable_excursion: float = 0.0
    max_drawdown_during_trade: float = 0.0
    failure_flags: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    regime_state: Optional[str] = None
    candidate_rank: Optional[int] = None
    risk_decision: Optional[str] = None
    exit_reason: Optional[str] = None
    exit_time: Optional[datetime] = None

    def avg_entry_price(self) -> float:
        if self.avg_fill_price_den <= 0.0:
            return 0.0
        return self.avg_fill_price_num / self.avg_fill_price_den

    def avg_slippage_bps(self) -> float:
        if self.slippage_bps_count == 0:
            return 0.0
        return self.slippage_bps_sum / float(self.slippage_bps_count)


# ---------------------------------------------------------------------------
# SimulatedCapitalFlowEngine
# ---------------------------------------------------------------------------


_FILL_REASON_TO_ENTRY_REASON: Dict[str, str] = {
    FillReason.MARKET_FILL: "SIMULATED_MARKET_ENTRY",
    FillReason.LIMIT_FILL_ON_PENETRATION: "SIMULATED_LIMIT_ENTRY",
    FillReason.STOP_TRIGGERED_FILL: "SIMULATED_STOP_ENTRY",
    FillReason.TAKE_PROFIT_TRIGGERED_FILL: "SIMULATED_TAKE_PROFIT_ENTRY",
    FillReason.FORCED_EXIT_FILL: "SIMULATED_FORCED_EXIT_ENTRY",
    FillReason.AMBIGUOUS_WORST_CASE_STOP_FILL: "SIMULATED_AMBIGUOUS_ENTRY",
}

_FILL_REASON_TO_EXIT_REASON: Dict[str, str] = {
    FillReason.MARKET_FILL: "SIMULATED_MARKET_CLOSE",
    FillReason.LIMIT_FILL_ON_PENETRATION: "SIMULATED_LIMIT_CLOSE",
    FillReason.STOP_TRIGGERED_FILL: "SIMULATED_STOP_CLOSE",
    FillReason.TAKE_PROFIT_TRIGGERED_FILL: "SIMULATED_TAKE_PROFIT_CLOSE",
    FillReason.FORCED_EXIT_FILL: "SIMULATED_FORCED_EXIT_CLOSE",
    FillReason.AMBIGUOUS_WORST_CASE_STOP_FILL: "SIMULATED_AMBIGUOUS_CLOSE",
}


class CapitalFrozenError(RuntimeError):
    """Raised when a caller attempts to open a NEW simulated position
    while the simulated capital is frozen.
    """


class SimulatedCapitalFlowEngine:
    """Strict blind walk-forward simulated capital flow engine.

    The engine is **deterministic, paper-only, and pure**:

      * It NEVER opens a network socket, signs a request, talks to
        a real exchange, the Telegram API, or any LLM.
      * It NEVER consults the wall-clock; every visible moment
        comes from the supplied :class:`MockFill.filled_at_simulated`
        or from explicit ``simulated_time`` inputs.
      * It NEVER reads / writes a real account book.
      * It NEVER produces a real exchange order id, an api key,
        an api secret, or a signed-endpoint reference.
      * Two engines fed identical fills / mark-prices / config
        produce identical state / ledger / equity timeseries.

    Lifecycle:

      1. Construct with a :class:`SimulatedCapitalConfig`.
      2. Drive forward via :meth:`consume_fill`,
         :meth:`apply_mark_prices`, :meth:`apply_replay_batch`,
         :meth:`apply_funding`, and :meth:`forced_exit`.
      3. Read :meth:`get_state` / :meth:`get_positions` /
         :meth:`get_ledger` / :meth:`get_equity_timeseries`.
    """

    def __init__(
        self,
        *,
        config: SimulatedCapitalConfig,
        ledger: Optional[TradeLedger] = None,
    ) -> None:
        if not isinstance(config, SimulatedCapitalConfig):
            raise TypeError(
                f"config must be SimulatedCapitalConfig, got "
                f"{type(config)!r}"
            )
        self._config = config
        self._ledger = ledger if ledger is not None else TradeLedger()
        # Cash: realised cash effects (initial capital +/- closed PnL,
        # minus locked profit, minus fees on opens / closes).
        self._exchange_equity: float = float(config.initial_capital)
        self._locked_profit: float = 0.0
        self._realized_pnl: float = 0.0
        # Mark prices (symbol -> mark) needed to compute unrealised PnL.
        self._mark_prices: Dict[str, float] = {}
        # Simulated time of last applied event (drives state.timestamp).
        self._last_simulated_time: Optional[datetime] = None
        # Position book + per-trade context.
        self._positions: Dict[str, SimulatedPosition] = {}
        self._trade_contexts: Dict[str, _OpenTradeContext] = {}
        # Equity timeseries.
        self._equity_timeseries: List[EquityTimeseriesPoint] = []
        # Drawdown bookkeeping.
        self._peak_equity: float = float(config.initial_capital)
        self._current_drawdown: float = 0.0
        # Freeze bookkeeping.
        self._capital_frozen: bool = False
        self._freeze_reason: Optional[str] = None
        self._consecutive_losses: int = 0
        # Counters for deterministic id generation.
        self._position_seq: int = 0
        self._trade_seq: int = 0
        # Diagnostics.
        self._fills_consumed: int = 0
        self._opens_count: int = 0
        self._closes_count: int = 0
        self._reductions_count: int = 0
        self._increases_count: int = 0
        self._frozen_open_attempts: int = 0
        # Defensive: assert config safety markers held.
        assert self._config.sandbox_only is True
        assert self._config.live_capital_enabled is False

    # ----- properties -----

    @property
    def config(self) -> SimulatedCapitalConfig:
        return self._config

    @property
    def ledger(self) -> TradeLedger:
        return self._ledger

    @property
    def capital_frozen(self) -> bool:
        return self._capital_frozen

    @property
    def freeze_reason(self) -> Optional[str]:
        return self._freeze_reason

    # ----- pinned safety properties (defensive tripwires) -----

    @property
    def simulated_only(self) -> bool:
        return True

    @property
    def no_live_order(self) -> bool:
        return True

    @property
    def live_trading(self) -> bool:
        return False

    @property
    def live_capital_enabled(self) -> bool:
        return False

    @property
    def exchange_live_orders(self) -> bool:
        return False

    @property
    def binance_private_api_enabled(self) -> bool:
        return False

    @property
    def trade_authority(self) -> bool:
        return False

    @property
    def auto_tuning_allowed(self) -> bool:
        return False

    @property
    def phase_12_forbidden(self) -> bool:
        return True

    # ----- public API: state inspection -----

    def get_positions(self) -> Tuple[SimulatedPosition, ...]:
        """Return all currently OPEN simulated positions, sorted by
        symbol for deterministic ordering.
        """
        return tuple(
            sorted(
                (
                    p
                    for p in self._positions.values()
                    if p.status == PositionStatus.OPEN
                ),
                key=lambda p: p.symbol,
            )
        )

    def get_ledger(self) -> TradeLedger:
        return self._ledger

    def get_equity_timeseries(self) -> Tuple[EquityTimeseriesPoint, ...]:
        return tuple(self._equity_timeseries)

    def get_state(
        self, simulated_time: Optional[datetime] = None
    ) -> SimulatedCapitalState:
        """Return the current :class:`SimulatedCapitalState`.

        ``simulated_time``, if supplied, MUST be ``>=
        last_simulated_time`` (forward-only). If omitted, the engine
        uses ``last_simulated_time``; if no event has been observed
        yet, the caller MUST supply ``simulated_time`` explicitly.
        """
        ts = self._resolve_state_timestamp(simulated_time)
        return self._build_state(ts)

    def available_capital_for_new_exposure(self) -> float:
        """Return the cash available for opening a NEW simulated
        position.

        ``locked_profit`` is included only when
        :pyattr:`SimulatedCapitalConfig.locked_profit_reuse_allowed`
        is ``True``.
        """
        avail = self._exchange_equity - self._open_risk()
        if self._config.locked_profit_reuse_allowed:
            avail += self._locked_profit
        return float(avail)

    def current_marked_equity(self) -> float:
        """Return the current mark-to-market simulated equity.

        This is ``exchange_equity + locked_profit + unrealized_pnl``
        of all OPEN simulated positions. It is a paper-only read of
        the engine's in-memory state: it NEVER reads a real account
        book, NEVER signs a request, NEVER touches a real exchange.
        Used by the (separately gated) Blind Walk-forward Runner /
        Paper Shadow Strategy Bridge to stamp ``equity_before`` /
        ``equity_after`` on a simulated trade record.
        """
        return float(
            self._exchange_equity
            + self._locked_profit
            + self._unrealized_pnl_total()
        )

    # ----- public API: fill consumption -----

    def consume_fill(
        self,
        fill: MockFill,
        *,
        evidence_refs: Iterable[str] = (),
        regime_state: Optional[str] = None,
        candidate_rank: Optional[int] = None,
        risk_decision: Optional[str] = None,
    ) -> Optional[TradeLedgerEntry]:
        """Consume a single :class:`MockFill` and update the simulated
        capital state. Returns a :class:`TradeLedgerEntry` if the fill
        fully closed a position, otherwise ``None``.

        The engine determines whether the fill is an OPEN, an
        INCREASE, a REDUCE, or a CLOSE based on the existing position
        on the symbol and the fill's ``side``:

          * No open position on symbol -> OPEN (BUY -> LONG, SELL ->
            SHORT).
          * Open position on symbol with same direction -> INCREASE.
          * Open position on symbol with opposite direction -> REDUCE
            (or CLOSE if filled_qty zeroes the position).
        """
        if not isinstance(fill, MockFill):
            raise TypeError(
                f"fill must be MockFill, got {type(fill)!r}"
            )
        evidence_refs_t = _check_str_tuple(evidence_refs, "evidence_refs")
        sim_time = ensure_utc_aware(
            fill.filled_at_simulated, "fill.filled_at_simulated"
        )
        self._advance_clock(sim_time)
        self._fills_consumed += 1

        existing = self._positions.get(fill.symbol)
        if existing is None or existing.status != PositionStatus.OPEN:
            # OPEN a new position.
            return self._open_position(
                fill,
                evidence_refs=evidence_refs_t,
                regime_state=regime_state,
                candidate_rank=candidate_rank,
                risk_decision=risk_decision,
            )

        # An open position on this symbol exists.
        same_direction = (
            (existing.side == PositionSide.LONG and fill.side == MockOrderSide.BUY)
            or (
                existing.side == PositionSide.SHORT
                and fill.side == MockOrderSide.SELL
            )
        )
        if same_direction:
            return self._increase_position(
                existing,
                fill,
                evidence_refs=evidence_refs_t,
            )
        # Opposite direction -> reduce or close.
        return self._reduce_or_close_position(
            existing,
            fill,
            evidence_refs=evidence_refs_t,
            forced=fill.fill_reason == FillReason.FORCED_EXIT_FILL,
        )

    def apply_mark_prices(
        self,
        mark_prices: Mapping[str, float],
        simulated_time: datetime,
    ) -> SimulatedCapitalState:
        """Apply mark prices for unrealised PnL computation and emit
        a fresh :class:`EquityTimeseriesPoint`.
        """
        if not isinstance(mark_prices, Mapping):
            raise TypeError(
                f"mark_prices must be a Mapping, got "
                f"{type(mark_prices)!r}"
            )
        ts = ensure_utc_aware(simulated_time, "simulated_time")
        self._advance_clock(ts)
        for sym, price in mark_prices.items():
            if not isinstance(sym, str) or not sym:
                raise ValueError("mark price symbol must be non-empty str")
            p = _validate_non_negative(f"mark_price[{sym}]", price)
            self._mark_prices[sym] = float(p)
        # Update unrealised PnL on every open position; track MFE / MAE.
        for pos in self._positions.values():
            if pos.status != PositionStatus.OPEN:
                continue
            self._update_position_unrealized(pos)
        self._record_equity_point(ts)
        self._update_freeze_state()
        return self._build_state(ts)

    def apply_replay_batch(
        self, batch: ReplayFeedBatch
    ) -> SimulatedCapitalState:
        """Pull the close-price of every visible 1m kline out of the
        :class:`ReplayFeedBatch` and apply them as mark prices.
        """
        if not isinstance(batch, ReplayFeedBatch):
            raise TypeError(
                f"batch must be ReplayFeedBatch, got {type(batch)!r}"
            )
        marks: Dict[str, float] = {}
        for k in batch.klines_1m:
            sym = getattr(k, "symbol", None)
            close = getattr(k, "close", None)
            if isinstance(sym, str) and sym and close is not None:
                marks[sym] = float(close)
        for k in batch.klines_5m:
            sym = getattr(k, "symbol", None)
            close = getattr(k, "close", None)
            if isinstance(sym, str) and sym and sym not in marks and close is not None:
                marks[sym] = float(close)
        return self.apply_mark_prices(marks, batch.simulated_time)

    def apply_funding(
        self,
        symbol: str,
        funding_amount: float,
        simulated_time: datetime,
    ) -> None:
        """Apply a funding cash impact to an open simulated position.

        ``funding_amount`` may be positive (paid TO the position) or
        negative (paid BY the position). Cash effect mirrors the sign
        on ``exchange_equity``.
        """
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("symbol must be a non-empty string")
        amt = _validate_finite("funding_amount", funding_amount)
        ts = ensure_utc_aware(simulated_time, "simulated_time")
        self._advance_clock(ts)
        pos = self._positions.get(symbol)
        if pos is None or pos.status != PositionStatus.OPEN:
            # Funding on a closed / non-existent simulated position is
            # silently ignored at v0.
            return
        pos.funding_paid += amt
        pos.updated_at_simulated = ts
        self._exchange_equity += amt
        ctx = self._trade_contexts.get(pos.position_id)
        if ctx is not None:
            ctx.funding_total += amt
        self._record_equity_point(ts)
        self._update_freeze_state()

    def forced_exit(
        self,
        symbol: str,
        *,
        exit_price: float,
        simulated_time: datetime,
        fee: float = 0.0,
        slippage_bps: float = 0.0,
        evidence_refs: Iterable[str] = (),
    ) -> Optional[TradeLedgerEntry]:
        """Force-close the open simulated position on ``symbol`` at
        ``exit_price`` and produce the resulting trade-ledger entry.

        This is a paper-only convenience for the FORCED_EXIT path
        when no :class:`MockFill` is available (e.g. liquidation
        stress). It produces a deterministic ledger entry tagged
        :data:`TradeFailureFlag.FORCED_EXIT_TRIGGERED`.
        """
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("symbol must be a non-empty string")
        ep = _validate_non_negative("exit_price", exit_price)
        fe = _validate_non_negative("fee", fee)
        sb = _validate_non_negative("slippage_bps", slippage_bps)
        refs_t = _check_str_tuple(evidence_refs, "evidence_refs")
        ts = ensure_utc_aware(simulated_time, "simulated_time")
        self._advance_clock(ts)
        pos = self._positions.get(symbol)
        if pos is None or pos.status != PositionStatus.OPEN:
            return None
        # Synthesize a closing fill-equivalent event without producing
        # a real MockFill (we don't need an order_id collision).
        return self._close_or_reduce_position_internal(
            pos,
            close_qty=pos.qty,
            close_price=ep,
            fee=fe,
            slippage_bps=sb,
            simulated_time=ts,
            fill_reason=FillReason.FORCED_EXIT_FILL,
            forced=True,
            evidence_refs=refs_t,
            funding_impact=None,
        )

    # ----- public API: manual freeze / unfreeze -----

    def freeze_capital(
        self,
        reason: str = RiskFreezeReason.MANUAL_FREEZE,
    ) -> None:
        if reason not in RiskFreezeReason.ALLOWED:
            raise ValueError(
                f"reason must be one of "
                f"{sorted(RiskFreezeReason.ALLOWED)}, got {reason!r}"
            )
        if reason == RiskFreezeReason.NORMAL:
            raise ValueError(
                "cannot freeze with reason NORMAL; use unfreeze_capital()"
            )
        self._capital_frozen = True
        self._freeze_reason = reason

    def unfreeze_capital(self) -> None:
        self._capital_frozen = False
        self._freeze_reason = None

    # ----- internal: position lifecycle -----

    def _open_position(
        self,
        fill: MockFill,
        *,
        evidence_refs: Tuple[str, ...],
        regime_state: Optional[str],
        candidate_rank: Optional[int],
        risk_decision: Optional[str],
    ) -> Optional[TradeLedgerEntry]:
        if self._capital_frozen:
            self._frozen_open_attempts += 1
            raise CapitalFrozenError(
                f"capital is frozen ({self._freeze_reason}); cannot "
                f"open new simulated position on {fill.symbol}"
            )
        if (
            len([
                p
                for p in self._positions.values()
                if p.status == PositionStatus.OPEN
            ])
            >= self._config.max_active_positions
        ):
            raise RuntimeError(
                f"max_active_positions={self._config.max_active_positions} "
                f"reached; cannot open new simulated position on "
                f"{fill.symbol}"
            )
        side = (
            PositionSide.LONG
            if fill.side == MockOrderSide.BUY
            else PositionSide.SHORT
        )
        self._position_seq += 1
        position_id = f"sim_position_{self._position_seq:08d}"
        self._trade_seq += 1
        trade_id = f"sim_trade_{self._trade_seq:08d}"
        ts = fill.filled_at_simulated
        pos = SimulatedPosition(
            position_id=position_id,
            symbol=fill.symbol,
            side=side,
            qty=float(fill.filled_qty),
            avg_entry_price=float(fill.fill_price),
            opened_at_simulated=ts,
            updated_at_simulated=ts,
            fees_paid=float(fill.fee),
            slippage_paid=(
                float(fill.fill_price)
                * float(fill.filled_qty)
                * float(fill.slippage_bps)
                / 10000.0
            ),
            evidence_refs=tuple(evidence_refs) + tuple(fill.evidence_refs),
        )
        self._positions[fill.symbol] = pos
        # Cash effect of opening fee.
        self._exchange_equity -= float(fill.fee)
        # Funding impact (rare on opens but supported).
        if fill.funding_impact is not None:
            self._exchange_equity += float(fill.funding_impact)
            pos.funding_paid += float(fill.funding_impact)
        # Per-trade context.
        ctx = _OpenTradeContext(
            trade_id=trade_id,
            symbol=fill.symbol,
            entry_time=ts,
            entry_reason=_FILL_REASON_TO_ENTRY_REASON.get(
                fill.fill_reason, "SIMULATED_ENTRY"
            ),
            order_type=self._infer_order_type(fill),
            requested_qty=float(fill.filled_qty),
            filled_qty=float(fill.filled_qty),
            avg_fill_price_num=float(fill.fill_price)
            * float(fill.filled_qty),
            avg_fill_price_den=float(fill.filled_qty),
            slippage_bps_sum=float(fill.slippage_bps),
            slippage_bps_count=1,
            fee_total=float(fill.fee),
            funding_total=(
                float(fill.funding_impact)
                if fill.funding_impact is not None
                else 0.0
            ),
            evidence_refs=list(evidence_refs)
            + list(fill.evidence_refs),
            regime_state=regime_state,
            candidate_rank=candidate_rank,
            risk_decision=risk_decision,
        )
        if ConservativeAssumption.PARTIAL_FILL in fill.conservative_assumption:
            ctx.failure_flags.append(TradeFailureFlag.PARTIAL_FILL_ONLY)
        if (
            ConservativeAssumption.AMBIGUOUS_INTRABAR_WORST_CASE
            in fill.conservative_assumption
        ):
            ctx.failure_flags.append(TradeFailureFlag.AMBIGUOUS_INTRABAR_PATH)
        self._trade_contexts[position_id] = ctx
        self._opens_count += 1
        # Update mark and emit equity point.
        self._mark_prices[fill.symbol] = float(fill.fill_price)
        self._update_position_unrealized(pos)
        self._record_equity_point(ts)
        self._update_freeze_state()
        return None

    def _increase_position(
        self,
        pos: SimulatedPosition,
        fill: MockFill,
        *,
        evidence_refs: Tuple[str, ...],
    ) -> Optional[TradeLedgerEntry]:
        if self._capital_frozen:
            self._frozen_open_attempts += 1
            raise CapitalFrozenError(
                f"capital is frozen ({self._freeze_reason}); cannot "
                f"increase simulated position on {fill.symbol}"
            )
        ts = fill.filled_at_simulated
        new_qty = pos.qty + float(fill.filled_qty)
        new_num = (
            pos.avg_entry_price * pos.qty
            + float(fill.fill_price) * float(fill.filled_qty)
        )
        new_avg = new_num / new_qty if new_qty > 0 else 0.0
        pos.qty = new_qty
        pos.avg_entry_price = new_avg
        pos.fees_paid += float(fill.fee)
        pos.slippage_paid += (
            float(fill.fill_price)
            * float(fill.filled_qty)
            * float(fill.slippage_bps)
            / 10000.0
        )
        pos.updated_at_simulated = ts
        if fill.funding_impact is not None:
            pos.funding_paid += float(fill.funding_impact)
            self._exchange_equity += float(fill.funding_impact)
        self._exchange_equity -= float(fill.fee)
        for r in evidence_refs:
            if r not in pos.evidence_refs:
                pos.evidence_refs = pos.evidence_refs + (r,)
        for r in fill.evidence_refs:
            if r not in pos.evidence_refs:
                pos.evidence_refs = pos.evidence_refs + (r,)
        ctx = self._trade_contexts.get(pos.position_id)
        if ctx is not None:
            ctx.requested_qty += float(fill.filled_qty)
            ctx.filled_qty += float(fill.filled_qty)
            ctx.avg_fill_price_num += (
                float(fill.fill_price) * float(fill.filled_qty)
            )
            ctx.avg_fill_price_den += float(fill.filled_qty)
            ctx.slippage_bps_sum += float(fill.slippage_bps)
            ctx.slippage_bps_count += 1
            ctx.fee_total += float(fill.fee)
            if fill.funding_impact is not None:
                ctx.funding_total += float(fill.funding_impact)
            ctx.evidence_refs.extend(evidence_refs)
            ctx.evidence_refs.extend(fill.evidence_refs)
        self._increases_count += 1
        self._mark_prices[fill.symbol] = float(fill.fill_price)
        self._update_position_unrealized(pos)
        self._record_equity_point(ts)
        self._update_freeze_state()
        return None

    def _reduce_or_close_position(
        self,
        pos: SimulatedPosition,
        fill: MockFill,
        *,
        evidence_refs: Tuple[str, ...],
        forced: bool,
    ) -> Optional[TradeLedgerEntry]:
        # Defensive: cap closing quantity at the open position size.
        close_qty = min(float(fill.filled_qty), pos.qty)
        return self._close_or_reduce_position_internal(
            pos,
            close_qty=close_qty,
            close_price=float(fill.fill_price),
            fee=float(fill.fee),
            slippage_bps=float(fill.slippage_bps),
            simulated_time=fill.filled_at_simulated,
            fill_reason=fill.fill_reason,
            forced=forced,
            evidence_refs=tuple(evidence_refs)
            + tuple(fill.evidence_refs),
            funding_impact=fill.funding_impact,
        )

    def _close_or_reduce_position_internal(
        self,
        pos: SimulatedPosition,
        *,
        close_qty: float,
        close_price: float,
        fee: float,
        slippage_bps: float,
        simulated_time: datetime,
        fill_reason: str,
        forced: bool,
        evidence_refs: Tuple[str, ...],
        funding_impact: Optional[float],
    ) -> Optional[TradeLedgerEntry]:
        if close_qty <= 0:
            return None
        ts = simulated_time
        # Realised gross PnL on this slice.
        if pos.side == PositionSide.LONG:
            gross = (close_price - pos.avg_entry_price) * close_qty
        else:
            gross = (pos.avg_entry_price - close_price) * close_qty
        # Update position.
        pos.qty -= close_qty
        pos.realized_pnl += gross
        pos.fees_paid += fee
        pos.slippage_paid += (
            close_price * close_qty * slippage_bps / 10000.0
        )
        pos.updated_at_simulated = ts
        if funding_impact is not None:
            pos.funding_paid += float(funding_impact)
            self._exchange_equity += float(funding_impact)
        for r in evidence_refs:
            if r not in pos.evidence_refs:
                pos.evidence_refs = pos.evidence_refs + (r,)
        # Cash effect: PnL minus close fee.
        self._exchange_equity += gross - fee
        self._realized_pnl += gross
        # Per-trade context.
        ctx = self._trade_contexts.get(pos.position_id)
        if ctx is not None:
            ctx.fee_total += fee
            ctx.slippage_bps_sum += slippage_bps
            ctx.slippage_bps_count += 1
            ctx.realized_pnl_gross += gross
            ctx.evidence_refs.extend(evidence_refs)
            if funding_impact is not None:
                ctx.funding_total += float(funding_impact)
            if forced and TradeFailureFlag.FORCED_EXIT_TRIGGERED not in (
                ctx.failure_flags
            ):
                ctx.failure_flags.append(
                    TradeFailureFlag.FORCED_EXIT_TRIGGERED
                )
            if fill_reason == FillReason.AMBIGUOUS_WORST_CASE_STOP_FILL:
                if (
                    TradeFailureFlag.AMBIGUOUS_INTRABAR_PATH
                    not in ctx.failure_flags
                ):
                    ctx.failure_flags.append(
                        TradeFailureFlag.AMBIGUOUS_INTRABAR_PATH
                    )
        ledger_entry: Optional[TradeLedgerEntry] = None
        # Update mark for unrealised re-mark.
        self._mark_prices[pos.symbol] = close_price
        self._update_position_unrealized(pos)
        if pos.qty <= 1e-12:
            # Full close -> finalise position + ledger entry.
            pos.qty = 0.0
            pos.unrealized_pnl = 0.0
            pos.status = PositionStatus.CLOSED
            self._closes_count += 1
            ledger_entry = self._finalise_trade(
                pos,
                ctx,
                exit_time=ts,
                exit_reason=_FILL_REASON_TO_EXIT_REASON.get(
                    fill_reason, "SIMULATED_CLOSE"
                ),
                forced=forced,
            )
            if ctx is not None:
                self._trade_contexts.pop(pos.position_id, None)
        else:
            self._reductions_count += 1
        # Update peak / drawdown / freeze AFTER cash impact applied.
        self._record_equity_point(ts)
        self._update_freeze_state()
        return ledger_entry

    def _finalise_trade(
        self,
        pos: SimulatedPosition,
        ctx: Optional[_OpenTradeContext],
        *,
        exit_time: datetime,
        exit_reason: str,
        forced: bool,
    ) -> TradeLedgerEntry:
        if ctx is None:
            # Should not happen on a normal lifecycle, but be defensive.
            ctx = _OpenTradeContext(
                trade_id=f"sim_trade_orphan_{self._trade_seq:08d}",
                symbol=pos.symbol,
                entry_time=pos.opened_at_simulated,
                entry_reason="SIMULATED_ENTRY",
                order_type="MARKET",
            )
        net_pnl = ctx.realized_pnl_gross - ctx.fee_total + ctx.funding_total
        # Locked-profit policy: if reuse not allowed and config has a
        # profit_lock_fraction, lock that fraction of POSITIVE net_pnl.
        locked_delta = 0.0
        if (
            net_pnl > 0.0
            and (not self._config.locked_profit_reuse_allowed)
            and self._config.profit_lock_fraction > 0.0
        ):
            locked_delta = net_pnl * float(
                self._config.profit_lock_fraction
            )
            self._locked_profit += locked_delta
            self._exchange_equity -= locked_delta
        outcome = (
            TradeOutcome.WIN
            if net_pnl > 0.0
            else (
                TradeOutcome.LOSS
                if net_pnl < 0.0
                else TradeOutcome.BREAKEVEN
            )
        )
        # Consecutive-loss tracking.
        if outcome == TradeOutcome.LOSS:
            self._consecutive_losses += 1
        elif outcome == TradeOutcome.WIN:
            self._consecutive_losses = 0
        # Build the ledger entry.
        failure_flags = (
            tuple(ctx.failure_flags)
            if ctx.failure_flags
            else (TradeFailureFlag.NONE,)
        )
        # Deduplicate evidence_refs preserving order.
        seen: set = set()
        ev: List[str] = []
        for r in ctx.evidence_refs:
            if r not in seen:
                seen.add(r)
                ev.append(r)
        entry = TradeLedgerEntry(
            trade_id=ctx.trade_id,
            symbol=pos.symbol,
            entry_time=ctx.entry_time,
            exit_time=exit_time,
            entry_reason=ctx.entry_reason,
            exit_reason=exit_reason,
            regime_state=ctx.regime_state,
            candidate_rank=ctx.candidate_rank,
            risk_decision=ctx.risk_decision,
            order_type=ctx.order_type,
            requested_qty=ctx.requested_qty,
            filled_qty=ctx.filled_qty,
            avg_fill_price=ctx.avg_entry_price(),
            slippage_bps=ctx.avg_slippage_bps(),
            fee=ctx.fee_total,
            max_drawdown_during_trade=pos.max_drawdown_during_trade,
            max_favorable_excursion=pos.max_favorable_excursion,
            net_pnl=net_pnl,
            locked_profit_delta=locked_delta,
            failure_flags=failure_flags,
            evidence_refs=tuple(ev),
            outcome=outcome,
        )
        self._ledger.append(entry)
        return entry

    # ----- internal: equity / drawdown / freeze -----

    def _open_risk(self) -> float:
        total = 0.0
        for p in self._positions.values():
            if p.status == PositionStatus.OPEN:
                total += float(p.notional)
        return total

    def _unrealized_pnl_total(self) -> float:
        total = 0.0
        for p in self._positions.values():
            if p.status == PositionStatus.OPEN:
                total += float(p.unrealized_pnl)
        return total

    def _active_positions_count(self) -> int:
        return sum(
            1
            for p in self._positions.values()
            if p.status == PositionStatus.OPEN
        )

    def _update_position_unrealized(self, pos: SimulatedPosition) -> None:
        mark = self._mark_prices.get(pos.symbol)
        if mark is None:
            return
        if pos.side == PositionSide.LONG:
            upnl = (float(mark) - float(pos.avg_entry_price)) * float(pos.qty)
        else:
            upnl = (float(pos.avg_entry_price) - float(mark)) * float(pos.qty)
        pos.unrealized_pnl = float(upnl)
        if upnl > pos.max_favorable_excursion:
            pos.max_favorable_excursion = float(upnl)
        # MAE = max drop from MFE (always >= 0).
        drop = pos.max_favorable_excursion - upnl
        if drop > pos.max_drawdown_during_trade:
            pos.max_drawdown_during_trade = float(drop)

    def _record_equity_point(self, ts: datetime) -> None:
        eq = float(self._exchange_equity)
        lp = float(self._locked_profit)
        upnl = float(self._unrealized_pnl_total())
        marked_equity = eq + lp + upnl
        if marked_equity > self._peak_equity:
            self._peak_equity = marked_equity
        if self._peak_equity > 0.0:
            self._current_drawdown = max(
                0.0,
                (self._peak_equity - marked_equity) / self._peak_equity,
            )
        else:
            self._current_drawdown = 0.0
        risk_state = self._risk_state_string()
        point = EquityTimeseriesPoint(
            timestamp=ts,
            exchange_equity=eq,
            locked_profit=lp,
            open_risk=float(self._open_risk()),
            unrealized_pnl=upnl,
            realized_pnl=float(self._realized_pnl),
            total_lifetime_equity=float(self._peak_equity),
            drawdown=float(self._current_drawdown),
            active_positions=self._active_positions_count(),
            risk_state=risk_state,
        )
        # Append; never mutate prior points (deterministic).
        self._equity_timeseries.append(point)

    def _update_freeze_state(self) -> None:
        # Drawdown-based freeze.
        if (
            self._config.max_drawdown_pause_pct is not None
            and self._current_drawdown
            >= float(self._config.max_drawdown_pause_pct)
        ):
            self._capital_frozen = True
            self._freeze_reason = RiskFreezeReason.MAX_DRAWDOWN_EXCEEDED
            return
        # Consecutive-loss freeze.
        if (
            self._config.consecutive_loss_pause_threshold is not None
            and self._consecutive_losses
            >= int(self._config.consecutive_loss_pause_threshold)
        ):
            self._capital_frozen = True
            self._freeze_reason = RiskFreezeReason.CONSECUTIVE_LOSS_PAUSE
            return
        # Otherwise, leave existing freeze in place (manual /
        # liquidation freezes require explicit unfreeze).

    def _risk_state_string(self) -> str:
        if not self._capital_frozen:
            return RiskFreezeReason.NORMAL
        return self._freeze_reason or RiskFreezeReason.MANUAL_FREEZE

    def _resolve_state_timestamp(
        self, simulated_time: Optional[datetime]
    ) -> datetime:
        if simulated_time is None:
            if self._last_simulated_time is None:
                raise ValueError(
                    "no events have been observed yet; "
                    "supply simulated_time explicitly"
                )
            return self._last_simulated_time
        ts = ensure_utc_aware(simulated_time, "simulated_time")
        if (
            self._last_simulated_time is not None
            and ts < self._last_simulated_time
        ):
            raise ValueError(
                "SimulatedCapitalFlowEngine cannot move backward; "
                f"requested simulated_time={ts.isoformat()} < "
                f"last_simulated_time="
                f"{self._last_simulated_time.isoformat()}"
            )
        return ts

    def _build_state(self, ts: datetime) -> SimulatedCapitalState:
        return SimulatedCapitalState(
            timestamp=ts,
            initial_capital=float(self._config.initial_capital),
            exchange_equity=float(self._exchange_equity),
            locked_profit=float(self._locked_profit),
            open_risk=float(self._open_risk()),
            unrealized_pnl=float(self._unrealized_pnl_total()),
            realized_pnl=float(self._realized_pnl),
            total_lifetime_equity=float(self._peak_equity),
            drawdown=float(self._current_drawdown),
            active_positions=self._active_positions_count(),
            risk_state=self._risk_state_string(),
            capital_frozen=bool(self._capital_frozen),
            freeze_reason=self._freeze_reason,
        )

    def _advance_clock(self, ts: datetime) -> None:
        if (
            self._last_simulated_time is not None
            and ts < self._last_simulated_time
        ):
            raise ValueError(
                "SimulatedCapitalFlowEngine cannot move backward; "
                f"requested simulated_time={ts.isoformat()} < "
                f"last_simulated_time="
                f"{self._last_simulated_time.isoformat()}"
            )
        self._last_simulated_time = ts

    def _infer_order_type(self, fill: MockFill) -> str:
        if fill.fill_reason == FillReason.MARKET_FILL:
            return MockOrderType.MARKET
        if fill.fill_reason == FillReason.LIMIT_FILL_ON_PENETRATION:
            return MockOrderType.LIMIT
        if fill.fill_reason == FillReason.STOP_TRIGGERED_FILL:
            return MockOrderType.STOP_MARKET
        if fill.fill_reason in (
            FillReason.AMBIGUOUS_WORST_CASE_STOP_FILL,
        ):
            return MockOrderType.STOP_MARKET
        if fill.fill_reason == FillReason.TAKE_PROFIT_TRIGGERED_FILL:
            return MockOrderType.TAKE_PROFIT_MARKET
        if fill.fill_reason == FillReason.FORCED_EXIT_FILL:
            return MockOrderType.FORCED_EXIT
        return MockOrderType.MARKET

    # ----- public API: serialization -----

    def safety_payload(self) -> Dict[str, Any]:
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        return out

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "config": self._config.to_dict(),
            "state": self.get_state().to_dict()
            if self._last_simulated_time is not None
            else None,
            "positions": [
                p.to_dict()
                for p in sorted(
                    self._positions.values(),
                    key=lambda p: (p.symbol, p.position_id),
                )
            ],
            "equity_timeseries": [
                pt.to_dict() for pt in self._equity_timeseries
            ],
            "ledger": self._ledger.to_dict(),
            "diagnostics": {
                "fills_consumed": int(self._fills_consumed),
                "opens_count": int(self._opens_count),
                "closes_count": int(self._closes_count),
                "reductions_count": int(self._reductions_count),
                "increases_count": int(self._increases_count),
                "frozen_open_attempts": int(self._frozen_open_attempts),
                "is_simulated_capital_diagnostics": True,
            },
            "is_simulated_capital_flow_engine": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


__all__ = [
    "PHASE_NAME",
    "CapitalFrozenError",
    "PositionSide",
    "PositionStatus",
    "RiskFreezeReason",
    "SimulatedCapitalConfig",
    "SimulatedCapitalFlowEngine",
    "SimulatedCapitalState",
    "SimulatedPosition",
]
