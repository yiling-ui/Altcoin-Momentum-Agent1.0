"""Trade Ledger v0 for Phase 11C.1D-D-E (PR98 - Simulated Capital
Flow + Trade Ledger v0).

Strict blind walk-forward simulated trade ledger and equity
timeseries. This module is the **fifth** anti-future-lookahead
infrastructure block of the strict blind walk-forward stack defined
by Phase 11C.1D-D (the *Strict Blind Walk-forward Sim-Live
Constitution*, PR93). It builds strictly on top of the PR94 / PR95
/ PR96 / PR97 substrate and is consumed by the PR98 Simulated
Capital Flow engine (:mod:`app.sim.simulated_capital_flow`).

This module is **paper-only**. Every output it produces carries the
hard-pinned safety markers ``simulated_only=True`` /
``no_live_order=True`` / ``live_trading=False`` /
``exchange_live_orders=False`` /
``binance_private_api_enabled=False`` /
``phase_12_forbidden=True`` / ``auto_tuning_allowed=False`` /
``trade_authority=False`` / ``live_capital_enabled=False`` and
NEVER advertises a real account id, a real exchange order id, an
api key, an api secret, or a signed-endpoint reference.

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

PR98 acceptance authorises ONLY PR99 (*Telegram Sandbox Outbox*) to
begin its own gate. PR98 does NOT implement, and does NOT authorise:

  - the Telegram Sandbox Outbox (PR99),
  - the Blind Walk-forward Runner (PR100),
  - Phase 12.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from app.sim.simulation_clock import ensure_utc_aware
from app.sim.time_wall_guard import assert_no_forbidden_fields


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


def _validate_finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"{name} must be int / float, got {type(value)!r}"
        )
    f = float(value)
    if not math.isfinite(f):
        raise ValueError(f"{name} must be finite, got {f!r}")
    return f


def _validate_non_negative(name: str, value: Any) -> float:
    f = _validate_finite_number(name, value)
    if f < 0.0:
        raise ValueError(f"{name} must be >= 0, got {f!r}")
    return f


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


class TradeOutcome:
    """Closed taxonomy of net trade outcomes (post-fee, post-slippage)."""

    WIN: str = "WIN"
    LOSS: str = "LOSS"
    BREAKEVEN: str = "BREAKEVEN"

    ALLOWED: FrozenSet[str] = frozenset({WIN, LOSS, BREAKEVEN})


class TradeFailureFlag:
    """Closed taxonomy of trade-level failure / degradation flags.

    These are descriptive only. They NEVER imply a runtime config
    patch, a threshold patch, or any live-trading authority.
    """

    NONE: str = "NONE"
    PARTIAL_FILL_ONLY: str = "PARTIAL_FILL_ONLY"
    AMBIGUOUS_INTRABAR_PATH: str = "AMBIGUOUS_INTRABAR_PATH"
    FORCED_EXIT_TRIGGERED: str = "FORCED_EXIT_TRIGGERED"
    DRAWDOWN_FREEZE_ACTIVE: str = "DRAWDOWN_FREEZE_ACTIVE"
    CONSECUTIVE_LOSS_FREEZE_ACTIVE: str = (
        "CONSECUTIVE_LOSS_FREEZE_ACTIVE"
    )
    LIQUIDATION_STRESS_TRIGGERED: str = "LIQUIDATION_STRESS_TRIGGERED"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            NONE,
            PARTIAL_FILL_ONLY,
            AMBIGUOUS_INTRABAR_PATH,
            FORCED_EXIT_TRIGGERED,
            DRAWDOWN_FREEZE_ACTIVE,
            CONSECUTIVE_LOSS_FREEZE_ACTIVE,
            LIQUIDATION_STRESS_TRIGGERED,
        }
    )


# ---------------------------------------------------------------------------
# EquityTimeseriesPoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EquityTimeseriesPoint:
    """A single deterministic snapshot of the simulated equity curve.

    The point is **immutable** and **JSON-serialisable** via
    :meth:`to_dict` / :meth:`to_json`. The hard-pinned safety markers
    (``simulated_only`` / ``no_live_order`` / ``live_capital_enabled``
    / ``phase_12_forbidden`` / ``trade_authority`` /
    ``auto_tuning_allowed``) cannot be flipped through the dataclass
    constructor.
    """

    timestamp: datetime
    exchange_equity: float
    locked_profit: float
    open_risk: float
    unrealized_pnl: float
    realized_pnl: float
    total_lifetime_equity: float
    drawdown: float
    active_positions: int
    risk_state: str
    # Hard-pinned safety markers:
    simulated_only: bool = True
    no_live_order: bool = True
    live_capital_enabled: bool = False
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        ts = ensure_utc_aware(self.timestamp, "timestamp")
        eq = _validate_finite_number("exchange_equity", self.exchange_equity)
        lp = _validate_finite_number("locked_profit", self.locked_profit)
        risk = _validate_finite_number("open_risk", self.open_risk)
        upnl = _validate_finite_number("unrealized_pnl", self.unrealized_pnl)
        rpnl = _validate_finite_number("realized_pnl", self.realized_pnl)
        tle = _validate_finite_number(
            "total_lifetime_equity", self.total_lifetime_equity
        )
        dd = _validate_finite_number("drawdown", self.drawdown)
        if dd < 0.0:
            raise ValueError("drawdown must be >= 0")
        if not isinstance(self.active_positions, int) or isinstance(
            self.active_positions, bool
        ):
            raise TypeError("active_positions must be int")
        if self.active_positions < 0:
            raise ValueError("active_positions must be >= 0")
        if not isinstance(self.risk_state, str) or not self.risk_state:
            raise ValueError("risk_state must be a non-empty string")
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
            "exchange_equity": float(self.exchange_equity),
            "locked_profit": float(self.locked_profit),
            "open_risk": float(self.open_risk),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "total_lifetime_equity": float(self.total_lifetime_equity),
            "drawdown": float(self.drawdown),
            "active_positions": int(self.active_positions),
            "risk_state": self.risk_state,
            "is_equity_timeseries_point": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# TradeLedgerEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeLedgerEntry:
    """A single deterministic trade-ledger entry.

    The entry is **immutable** and **JSON-serialisable**. It is the
    canonical record of one round-trip simulated trade
    (open + close, possibly via reductions and / or a forced exit).
    Hard-pinned safety markers cannot be flipped through the
    constructor.
    """

    trade_id: str
    symbol: str
    entry_time: datetime
    entry_reason: str
    order_type: str
    requested_qty: float
    filled_qty: float
    avg_fill_price: float
    slippage_bps: float
    fee: float
    max_drawdown_during_trade: float
    max_favorable_excursion: float
    net_pnl: float
    locked_profit_delta: float
    failure_flags: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    regime_state: Optional[str] = None
    candidate_rank: Optional[int] = None
    risk_decision: Optional[str] = None
    outcome: str = TradeOutcome.BREAKEVEN
    # Hard-pinned safety markers:
    simulated_only: bool = True
    no_live_order: bool = True
    live_capital_enabled: bool = False
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.trade_id, str) or not self.trade_id:
            raise ValueError("trade_id must be a non-empty string")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        et = ensure_utc_aware(self.entry_time, "entry_time")
        xt: Optional[datetime] = None
        if self.exit_time is not None:
            xt = ensure_utc_aware(self.exit_time, "exit_time")
            if xt < et:
                raise ValueError("exit_time must be >= entry_time")
        if not isinstance(self.entry_reason, str) or not self.entry_reason:
            raise ValueError("entry_reason must be a non-empty string")
        if self.exit_reason is not None and (
            not isinstance(self.exit_reason, str) or not self.exit_reason
        ):
            raise ValueError(
                "exit_reason must be a non-empty string or None"
            )
        if not isinstance(self.order_type, str) or not self.order_type:
            raise ValueError("order_type must be a non-empty string")
        rq = _validate_non_negative("requested_qty", self.requested_qty)
        fq = _validate_non_negative("filled_qty", self.filled_qty)
        afp = _validate_non_negative("avg_fill_price", self.avg_fill_price)
        sb = _validate_non_negative("slippage_bps", self.slippage_bps)
        fee = _validate_non_negative("fee", self.fee)
        mdd = _validate_non_negative(
            "max_drawdown_during_trade", self.max_drawdown_during_trade
        )
        mfe = _validate_finite_number(
            "max_favorable_excursion", self.max_favorable_excursion
        )
        net = _validate_finite_number("net_pnl", self.net_pnl)
        lpd = _validate_finite_number(
            "locked_profit_delta", self.locked_profit_delta
        )
        if lpd < 0.0:
            raise ValueError("locked_profit_delta must be >= 0")
        ff = _check_str_tuple(self.failure_flags, "failure_flags")
        for f in ff:
            if f not in TradeFailureFlag.ALLOWED:
                raise ValueError(
                    f"failure_flags entries must be one of "
                    f"{sorted(TradeFailureFlag.ALLOWED)}, got {f!r}"
                )
        refs = _check_str_tuple(self.evidence_refs, "evidence_refs")
        if self.regime_state is not None and (
            not isinstance(self.regime_state, str) or not self.regime_state
        ):
            raise ValueError(
                "regime_state must be a non-empty string or None"
            )
        if self.candidate_rank is not None:
            if (
                not isinstance(self.candidate_rank, int)
                or isinstance(self.candidate_rank, bool)
            ):
                raise TypeError("candidate_rank must be int or None")
            if self.candidate_rank < 0:
                raise ValueError("candidate_rank must be >= 0")
        if self.risk_decision is not None and (
            not isinstance(self.risk_decision, str)
            or not self.risk_decision
        ):
            raise ValueError(
                "risk_decision must be a non-empty string or None"
            )
        if self.outcome not in TradeOutcome.ALLOWED:
            raise ValueError(
                f"outcome must be one of "
                f"{sorted(TradeOutcome.ALLOWED)}, got {self.outcome!r}"
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
        object.__setattr__(self, "entry_time", et)
        object.__setattr__(self, "exit_time", xt)
        object.__setattr__(self, "requested_qty", rq)
        object.__setattr__(self, "filled_qty", fq)
        object.__setattr__(self, "avg_fill_price", afp)
        object.__setattr__(self, "slippage_bps", sb)
        object.__setattr__(self, "fee", fee)
        object.__setattr__(self, "max_drawdown_during_trade", mdd)
        object.__setattr__(self, "max_favorable_excursion", mfe)
        object.__setattr__(self, "net_pnl", net)
        object.__setattr__(self, "locked_profit_delta", lpd)
        object.__setattr__(self, "failure_flags", ff)
        object.__setattr__(self, "evidence_refs", refs)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": (
                self.exit_time.isoformat()
                if self.exit_time is not None
                else None
            ),
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason,
            "regime_state": self.regime_state,
            "candidate_rank": self.candidate_rank,
            "risk_decision": self.risk_decision,
            "order_type": self.order_type,
            "requested_qty": float(self.requested_qty),
            "filled_qty": float(self.filled_qty),
            "avg_fill_price": float(self.avg_fill_price),
            "slippage_bps": float(self.slippage_bps),
            "fee": float(self.fee),
            "max_drawdown_during_trade": float(
                self.max_drawdown_during_trade
            ),
            "max_favorable_excursion": float(
                self.max_favorable_excursion
            ),
            "net_pnl": float(self.net_pnl),
            "locked_profit_delta": float(self.locked_profit_delta),
            "failure_flags": list(self.failure_flags),
            "evidence_refs": list(self.evidence_refs),
            "outcome": self.outcome,
            "is_trade_ledger_entry": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# TradeLedgerSummary
# ---------------------------------------------------------------------------


def _median(values: List[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    s = sorted(values)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


@dataclass(frozen=True)
class TradeLedgerSummary:
    """Deterministic summary metrics over a :class:`TradeLedger`."""

    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    total_realized_pnl: float = 0.0
    total_fees: float = 0.0
    total_slippage_bps: float = 0.0
    max_drawdown: float = 0.0
    median_mfe: float = 0.0
    median_mae: float = 0.0
    # Hard-pinned safety markers:
    simulated_only: bool = True
    no_live_order: bool = True
    live_capital_enabled: bool = False
    phase_12_forbidden: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "trade_count": int(self.trade_count),
            "win_count": int(self.win_count),
            "loss_count": int(self.loss_count),
            "breakeven_count": int(self.breakeven_count),
            "total_realized_pnl": float(self.total_realized_pnl),
            "total_fees": float(self.total_fees),
            "total_slippage_bps": float(self.total_slippage_bps),
            "max_drawdown": float(self.max_drawdown),
            "median_mfe": float(self.median_mfe),
            "median_mae": float(self.median_mae),
            "is_trade_ledger_summary": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# TradeLedger
# ---------------------------------------------------------------------------


class TradeLedger:
    """Append-only, deterministic ledger of simulated trades.

    The ledger is a thin in-memory record of
    :class:`TradeLedgerEntry` objects. It supports:

      * append (only via :meth:`append`),
      * query by symbol (:meth:`entries_for_symbol`),
      * query by time range (:meth:`entries_in_range`),
      * deterministic summary metrics (:meth:`summary`).

    The ledger is paper-only. It NEVER reads / writes a real account
    book, NEVER advertises a real account / order id, NEVER signs a
    request. All outputs are deterministic given identical inputs.
    """

    def __init__(self) -> None:
        self._entries: List[TradeLedgerEntry] = []

    # ----- core API -----

    def append(self, entry: TradeLedgerEntry) -> None:
        if not isinstance(entry, TradeLedgerEntry):
            raise TypeError(
                f"entry must be TradeLedgerEntry, got {type(entry)!r}"
            )
        # Defensive: hard-pinned safety markers must hold.
        if entry.simulated_only is not True:
            raise ValueError("entry.simulated_only must be True")
        if entry.no_live_order is not True:
            raise ValueError("entry.no_live_order must be True")
        if entry.live_capital_enabled is not False:
            raise ValueError("entry.live_capital_enabled must be False")
        if entry.phase_12_forbidden is not True:
            raise ValueError("entry.phase_12_forbidden must be True")
        if entry.trade_authority is not False:
            raise ValueError("entry.trade_authority must be False")
        if entry.auto_tuning_allowed is not False:
            raise ValueError("entry.auto_tuning_allowed must be False")
        self._entries.append(entry)

    @property
    def entries(self) -> Tuple[TradeLedgerEntry, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(tuple(self._entries))

    # ----- queries -----

    def entries_for_symbol(self, symbol: str) -> Tuple[TradeLedgerEntry, ...]:
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("symbol must be a non-empty string")
        return tuple(e for e in self._entries if e.symbol == symbol)

    def entries_in_range(
        self,
        start: datetime,
        end: datetime,
    ) -> Tuple[TradeLedgerEntry, ...]:
        st = ensure_utc_aware(start, "start")
        et = ensure_utc_aware(end, "end")
        if et < st:
            raise ValueError("end must be >= start")
        out: List[TradeLedgerEntry] = []
        for e in self._entries:
            ref = e.exit_time if e.exit_time is not None else e.entry_time
            if st <= ref <= et:
                out.append(e)
        return tuple(out)

    # ----- summary -----

    def summary(self) -> TradeLedgerSummary:
        n = len(self._entries)
        if n == 0:
            return TradeLedgerSummary()
        win = 0
        loss = 0
        be = 0
        total_pnl = 0.0
        total_fees = 0.0
        total_slippage_bps = 0.0
        max_dd = 0.0
        mfes: List[float] = []
        maes: List[float] = []
        for e in self._entries:
            if e.outcome == TradeOutcome.WIN:
                win += 1
            elif e.outcome == TradeOutcome.LOSS:
                loss += 1
            else:
                be += 1
            total_pnl += float(e.net_pnl)
            total_fees += float(e.fee)
            total_slippage_bps += float(e.slippage_bps)
            if e.max_drawdown_during_trade > max_dd:
                max_dd = float(e.max_drawdown_during_trade)
            mfes.append(float(e.max_favorable_excursion))
            maes.append(float(e.max_drawdown_during_trade))
        return TradeLedgerSummary(
            trade_count=n,
            win_count=win,
            loss_count=loss,
            breakeven_count=be,
            total_realized_pnl=total_pnl,
            total_fees=total_fees,
            total_slippage_bps=total_slippage_bps,
            max_drawdown=max_dd,
            median_mfe=_median(mfes),
            median_mae=_median(maes),
        )

    # ----- serialization -----

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "entries": [e.to_dict() for e in self._entries],
            "summary": self.summary().to_dict(),
            "is_trade_ledger": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def safety_payload(self) -> Dict[str, Any]:
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        return out


__all__ = [
    "PHASE_NAME",
    "EquityTimeseriesPoint",
    "TradeFailureFlag",
    "TradeLedger",
    "TradeLedgerEntry",
    "TradeLedgerSummary",
    "TradeOutcome",
]
