"""Paper Shadow Strategy Bridge v0 for Phase 11C.1D-D (PR106 - Paper
Shadow Strategy Bridge for Blind Runner).

Strict blind walk-forward, paper-only, deterministic strategy bridge.
This module is the **eighth** anti-future-lookahead infrastructure
block of the strict blind walk-forward stack defined by Phase
11C.1D-D (the *Strict Blind Walk-forward Sim-Live Constitution*,
PR93). It builds strictly on top of the PR94 / PR95 / PR96 / PR97 /
PR98 / PR99 / PR100 substrate.

Purpose (PR106 brief):

  The PR100 Blind Walk-forward Runner already validates the
  no-lookahead infrastructure end-to-end, but it ships **no**
  executable decision path, so a strict historical blind run can
  never produce an entry / exit / fill / PnL and the file-only
  Telegram monitor can never show a trading event. This module is a
  minimal, deterministic, **paper-only** decision bridge that the
  runner can use as its ``decision_callback``. When a valid as-of
  signal occurs it emits :class:`OrderRequest` objects that the
  runner forwards to the (PR97) :class:`MockExchange`; the resulting
  fills flow into the (PR98) Simulated Capital Flow + Trade Ledger
  exactly as before.

What this bridge IS:

  * a pure / deterministic / replayable decision callback,
  * a consumer of CLOSED 1m (or 5m) klines that are already visible
    at ``simulated_time`` (``available_at <= simulated_time`` AND
    candle closed),
  * a long-only baseline breakout + volume-expansion scenario rule
    with fixed risk assumptions.

What this bridge is NOT (hard boundary, same as the rest of the
strict-blind stack):

  * NOT a live trading path,
  * NOT an auto-tuner (no parameter is tuned from any blind result),
  * NOT an AI / DeepSeek hot path (AI text is NEVER a label, truth,
    direction, sizing, leverage, stop, target, or execution input),
  * NOT a real exchange / Binance private API client,
  * NOT a real Telegram outbound,
  * NOT a Phase 12 enabler.

This module MUST NOT and CANNOT:

  * import app.risk / app.execution / app.exchanges / app.telegram /
    app.config,
  * call DeepSeek / any LLM / any network endpoint,
  * place a real exchange order,
  * publish to a real Telegram channel,
  * patch any runtime config / threshold / symbol limit / candidate
    pool / regime weight / strategy parameter,
  * read any future label / outcome / MFE / MAE / completed tail
    label as a live input,
  * authorise live trading, auto-tuning, or Phase 12.

No-lookahead contract (Constitution §5 / §6): at simulated time
``T`` the bridge MAY only use records whose ``available_at <= T`` and
candles that have closed (``close_time <= T``). Any record that fails
either gate is rejected (counted in :pyattr:`diagnostics`), NEVER
silently used.

Determinism: two bridges fed the identical batch sequence and the
identical capital-flow position state produce the identical order /
rejection sequence. The bridge NEVER consults the wall-clock.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Deque,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from app.sim.mock_exchange import OrderRequest
from app.sim.pessimistic_fill_model import MockOrderSide, MockOrderType
from app.sim.replay_feed_provider import ReplayFeedBatch
from app.sim.simulation_clock import ensure_utc_aware, parse_interval_seconds
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D / PR106 / Paper Shadow Strategy Bridge v0"
)

# Default deterministic baseline bridge name. Surfaced into the blind
# report's ``strategy_bridge_name`` and the trade ledger / transcript.
DEFAULT_BRIDGE_NAME: str = "baseline_breakout_volume_v0"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    """Project-wide safety boundary, re-pinned on every serialisation
    boundary so that no payload can ever be misread as authorising
    live trading, auto-tuning, AI trade authority, or Phase 12.
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
        "real_exchange_order_path": False,
        "real_capital": False,
        "telegram_outbound_enabled": False,
        "telegram_live_command_authority": False,
        "ai_trade_authority": False,
        "ai_in_decision_chain": False,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "auto_tuning_inside_blind_window": False,
        "uses_future_labels": False,
        "uses_outcome_labels": False,
        "phase_12_forbidden": True,
        # Defensive non-trade markers:
        "is_paper_shadow_strategy_bridge_payload": True,
        "is_real_exchange_order": False,
        "is_runtime_patch": False,
    }


def _validate_positive(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be int / float, got {type(value)!r}")
    f = float(value)
    if not math.isfinite(f) or f <= 0.0:
        raise ValueError(f"{name} must be a finite number > 0, got {f!r}")
    return f


def _validate_positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int, got {type(value)!r}")
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value!r}")
    return int(value)


def _validate_unit_fraction(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be int / float, got {type(value)!r}")
    f = float(value)
    if not math.isfinite(f) or f <= 0.0 or f > 1.0:
        raise ValueError(f"{name} must be in (0, 1], got {f!r}")
    return f


# ---------------------------------------------------------------------------
# Closed taxonomy of bridge signal reasons
# ---------------------------------------------------------------------------


class PaperShadowSignalReason:
    """Closed taxonomy of deterministic bridge signal reasons.

    These are descriptive labels recorded into ``evidence_refs`` /
    the simulated trade record. They are NEVER an AI recommendation,
    NEVER a runtime config patch, NEVER a live trade authority signal.
    """

    BREAKOUT_VOLUME_ENTRY: str = "breakout_volume_entry"
    EXIT_TAKE_PROFIT: str = "exit_take_profit"
    EXIT_STOP_LOSS: str = "exit_stop_loss"
    EXIT_MAX_HOLD: str = "exit_max_hold"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            BREAKOUT_VOLUME_ENTRY,
            EXIT_TAKE_PROFIT,
            EXIT_STOP_LOSS,
            EXIT_MAX_HOLD,
        }
    )


class PaperShadowRejectReason:
    """Closed taxonomy of deterministic bridge rejection reasons.

    A rejection means a candidate decision was *not* turned into a
    simulated order. The bridge NEVER silently swallows a
    no-lookahead violation: an out-of-as-of / forming-candle record
    is rejected and counted here.
    """

    FEATURE_NOT_YET_AVAILABLE_AT_ASOF_TIME: str = (
        "feature_not_yet_available_at_asof_time"
    )
    UNCLOSED_CANDLE: str = "unclosed_candle"
    WRONG_TIMEFRAME: str = "wrong_timeframe"
    MAX_CONCURRENT_POSITIONS_REACHED: str = (
        "max_concurrent_positions_reached"
    )
    SYMBOL_NOT_IN_ASOF_UNIVERSE: str = "symbol_not_in_asof_universe"
    # PR108 - capital-safety kill-switch awareness. When the bound
    # Simulated Capital Flow has latched its kill switch (capital floor
    # reached or hard drawdown limit breached) the bridge stops emitting
    # NEW entries for the rest of the blind window and records the
    # suppressed signal here. Descriptive only.
    ACCOUNT_HALTED: str = "account_halted"
    CAPITAL_EXHAUSTED: str = "capital_exhausted"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            FEATURE_NOT_YET_AVAILABLE_AT_ASOF_TIME,
            UNCLOSED_CANDLE,
            WRONG_TIMEFRAME,
            MAX_CONCURRENT_POSITIONS_REACHED,
            SYMBOL_NOT_IN_ASOF_UNIVERSE,
            ACCOUNT_HALTED,
            CAPITAL_EXHAUSTED,
        }
    )


# Internal per-symbol intent state machine (NOT a trade authority
# signal; purely the bridge's own bookkeeping of what it has already
# submitted so it never double-submits while a fill is in flight).
class _Intent:
    FLAT: str = "FLAT"
    ENTRY_PENDING: str = "ENTRY_PENDING"
    LONG: str = "LONG"
    EXIT_PENDING: str = "EXIT_PENDING"


# ---------------------------------------------------------------------------
# PaperShadowStrategyBridgeConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperShadowStrategyBridgeConfig:
    """Frozen configuration for a :class:`PaperShadowStrategyBridge`.

    The frozen container guarantees the rule's parameters cannot be
    mutated at runtime (no auto-tuning inside a blind window). Every
    default is conservative and is NOT optimised for profitability.

    Rule (long-only baseline breakout + volume expansion):

      * Maintain a rolling window of CLOSED ``timeframe`` candles per
        symbol, built only from already-available candles.
      * ENTRY when, on the latest closed bar:
          - ``close > max(high)`` over the previous
            ``breakout_lookback`` closed bars, AND
          - ``volume > volume_multiplier * mean(volume)`` over the
            previous ``breakout_lookback`` closed bars, AND
          - (optional) the latest bar is green (``close >= open``).
      * EXIT when any of:
          - latest ``close >= entry_price * (1 + take_profit_pct)``,
          - latest ``close <= entry_price * (1 - stop_loss_pct)``,
          - bars held ``>= max_hold_bars``.
      * Fixed sizing: ``requested_qty = position_notional / close``.
      * Fixed nominal ``leverage`` (descriptive; the paper capital
        engine is not margined in v0).
    """

    bridge_name: str = DEFAULT_BRIDGE_NAME
    timeframe: str = "1m"
    symbols: Optional[Tuple[str, ...]] = None
    breakout_lookback: int = 10
    volume_multiplier: float = 1.5
    require_green_bar: bool = True
    min_history_bars: int = 11
    max_hold_bars: int = 15
    take_profit_pct: float = 0.02
    stop_loss_pct: float = 0.01
    position_notional: float = 20.0
    leverage: float = 1.0
    max_concurrent_positions: int = 3
    restrict_to_asof_universe: bool = True
    # Hard-pinned safety markers (cannot be flipped through the
    # constructor):
    ai_trade_authority: bool = False
    trade_authority: bool = False
    auto_tuning_allowed: bool = False
    phase_12_forbidden: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.bridge_name, str) or not self.bridge_name:
            raise ValueError("bridge_name must be a non-empty string")
        if self.timeframe not in ("1m", "5m"):
            raise ValueError(
                f"timeframe must be '1m' or '5m', got {self.timeframe!r}"
            )
        # Parse to assert it is a recognised interval string.
        parse_interval_seconds(self.timeframe)
        syms: Optional[Tuple[str, ...]] = None
        if self.symbols is not None:
            tmp = tuple(self.symbols)
            if not tmp:
                raise ValueError(
                    "symbols, when provided, must be non-empty"
                )
            for s in tmp:
                if not isinstance(s, str) or not s:
                    raise ValueError(
                        "symbols entries must be non-empty strings"
                    )
            syms = tmp
        bl = _validate_positive_int("breakout_lookback", self.breakout_lookback)
        vm = _validate_positive("volume_multiplier", self.volume_multiplier)
        if not isinstance(self.require_green_bar, bool):
            raise TypeError("require_green_bar must be bool")
        mhb = _validate_positive_int("min_history_bars", self.min_history_bars)
        if mhb <= bl:
            raise ValueError(
                "min_history_bars must be > breakout_lookback so the "
                "rule always has a full prior window plus the trigger "
                "bar"
            )
        mh = _validate_positive_int("max_hold_bars", self.max_hold_bars)
        tp = _validate_unit_fraction("take_profit_pct", self.take_profit_pct)
        sl = _validate_unit_fraction("stop_loss_pct", self.stop_loss_pct)
        pn = _validate_positive("position_notional", self.position_notional)
        lev = _validate_positive("leverage", self.leverage)
        mcp = _validate_positive_int(
            "max_concurrent_positions", self.max_concurrent_positions
        )
        if not isinstance(self.restrict_to_asof_universe, bool):
            raise TypeError("restrict_to_asof_universe must be bool")
        if self.ai_trade_authority is not False:
            raise ValueError("ai_trade_authority must be False")
        if self.trade_authority is not False:
            raise ValueError("trade_authority must be False")
        if self.auto_tuning_allowed is not False:
            raise ValueError("auto_tuning_allowed must be False")
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        object.__setattr__(self, "symbols", syms)
        object.__setattr__(self, "breakout_lookback", bl)
        object.__setattr__(self, "volume_multiplier", vm)
        object.__setattr__(self, "min_history_bars", mhb)
        object.__setattr__(self, "max_hold_bars", mh)
        object.__setattr__(self, "take_profit_pct", tp)
        object.__setattr__(self, "stop_loss_pct", sl)
        object.__setattr__(self, "position_notional", pn)
        object.__setattr__(self, "leverage", lev)
        object.__setattr__(self, "max_concurrent_positions", mcp)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "bridge_name": self.bridge_name,
            "timeframe": self.timeframe,
            "symbols": (
                list(self.symbols) if self.symbols is not None else None
            ),
            "breakout_lookback": int(self.breakout_lookback),
            "volume_multiplier": float(self.volume_multiplier),
            "require_green_bar": bool(self.require_green_bar),
            "min_history_bars": int(self.min_history_bars),
            "max_hold_bars": int(self.max_hold_bars),
            "take_profit_pct": float(self.take_profit_pct),
            "stop_loss_pct": float(self.stop_loss_pct),
            "position_notional": float(self.position_notional),
            "leverage_ratio": float(self.leverage),
            "max_concurrent_positions": int(self.max_concurrent_positions),
            "restrict_to_asof_universe": bool(self.restrict_to_asof_universe),
            "is_paper_shadow_strategy_bridge_config": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# Internal closed-bar snapshot + per-symbol state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ClosedBar:
    """An immutable snapshot of one CLOSED candle used by the rule."""

    symbol: str
    open_time: datetime
    close_time: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    record_id: str


@dataclass
class _SymbolState:
    bars: Deque[_ClosedBar]
    last_open_time: Optional[datetime] = None
    intent: str = _Intent.FLAT
    bars_seen: int = 0
    entry_bar_index: Optional[int] = None
    entry_signal_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# PaperShadowStrategyBridgeDiagnostics
# ---------------------------------------------------------------------------


@dataclass
class PaperShadowStrategyBridgeDiagnostics:
    """Cumulative, deterministic diagnostics for one bridge run."""

    steps_seen: int = 0
    klines_considered: int = 0
    klines_ingested: int = 0
    klines_rejected_not_available: int = 0
    klines_rejected_unclosed: int = 0
    klines_rejected_wrong_timeframe: int = 0
    klines_rejected_duplicate: int = 0
    entry_signals: int = 0
    exit_signals: int = 0
    rejections: int = 0

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "steps_seen": int(self.steps_seen),
            "klines_considered": int(self.klines_considered),
            "klines_ingested": int(self.klines_ingested),
            "klines_rejected_not_available": int(
                self.klines_rejected_not_available
            ),
            "klines_rejected_unclosed": int(self.klines_rejected_unclosed),
            "klines_rejected_wrong_timeframe": int(
                self.klines_rejected_wrong_timeframe
            ),
            "klines_rejected_duplicate": int(self.klines_rejected_duplicate),
            "entry_signals": int(self.entry_signals),
            "exit_signals": int(self.exit_signals),
            "rejections": int(self.rejections),
            "is_paper_shadow_strategy_bridge_diagnostics": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# PaperShadowStrategyBridge
# ---------------------------------------------------------------------------


class PaperShadowStrategyBridge:
    """Deterministic, paper-only blind-runner decision bridge.

    The bridge is callable so it can be passed straight to
    :class:`app.sim.blind_walk_forward_runner.BlindWalkForwardRunner`
    as a ``decision_callback`` (or as the dedicated
    ``paper_shadow_bridge`` argument). On each step the runner calls
    ``bridge(simulated_time, batch, runner)`` and forwards every
    returned :class:`OrderRequest` to the :class:`MockExchange`.

    Position state is reconciled from the (PR98)
    :class:`SimulatedCapitalFlowEngine` open-position book that the
    runner drives, so the bridge never needs its own ledger and never
    double-submits while a fill is in flight.
    """

    def __init__(
        self,
        *,
        config: Optional[PaperShadowStrategyBridgeConfig] = None,
        capital_flow: Any = None,
    ) -> None:
        if config is None:
            config = PaperShadowStrategyBridgeConfig()
        if not isinstance(config, PaperShadowStrategyBridgeConfig):
            raise TypeError(
                "config must be PaperShadowStrategyBridgeConfig, got "
                f"{type(config)!r}"
            )
        # ``capital_flow`` is used read-only via ``get_positions()``.
        # We intentionally duck-type rather than import the engine to
        # keep this module free of any heavier dependency; the runner
        # always passes a real SimulatedCapitalFlowEngine.
        if capital_flow is not None and not hasattr(
            capital_flow, "get_positions"
        ):
            raise TypeError(
                "capital_flow must expose get_positions(); got "
                f"{type(capital_flow)!r}"
            )
        self._config = config
        self._capital_flow = capital_flow
        self._states: Dict[str, _SymbolState] = {}
        self._diagnostics = PaperShadowStrategyBridgeDiagnostics()
        # Rejections produced during the most recent call, drained by
        # the runner so it can emit a SIM_REJECT transcript entry.
        self._pending_rejections: List[Dict[str, Any]] = []
        # Defensive tripwires (mirror the rest of the strict-blind
        # stack). The bridge can never advertise authority it must
        # not have.
        self.simulated_only: bool = True
        self.no_live_order: bool = True
        self.ai_trade_authority: bool = False
        self.ai_in_decision_chain: bool = False
        self.trade_authority: bool = False
        self.auto_tuning_allowed: bool = False
        self.live_trading: bool = False
        self.exchange_live_orders: bool = False
        self.binance_private_api_enabled: bool = False
        self.telegram_outbound_enabled: bool = False
        self.phase_12_forbidden: bool = True

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def config(self) -> PaperShadowStrategyBridgeConfig:
        return self._config

    @property
    def bridge_name(self) -> str:
        return self._config.bridge_name

    @property
    def leverage(self) -> float:
        return float(self._config.leverage)

    @property
    def diagnostics(self) -> PaperShadowStrategyBridgeDiagnostics:
        return self._diagnostics

    def attach_capital_flow(self, capital_flow: Any) -> None:
        """Attach the position-state source after construction.

        Lets a caller build the bridge first (e.g. for the CLI) and
        bind the :class:`SimulatedCapitalFlowEngine` once it exists.
        """
        if capital_flow is not None and not hasattr(
            capital_flow, "get_positions"
        ):
            raise TypeError(
                "capital_flow must expose get_positions(); got "
                f"{type(capital_flow)!r}"
            )
        self._capital_flow = capital_flow

    def safety_payload(self) -> Dict[str, Any]:
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        return out

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "bridge_name": self.bridge_name,
            "config": self._config.to_dict(),
            "diagnostics": self._diagnostics.to_dict(),
            "is_paper_shadow_strategy_bridge": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    # ------------------------------------------------------------------
    # No-lookahead visibility guard (belt-and-suspenders)
    # ------------------------------------------------------------------

    def is_record_visible(
        self,
        record: Any,
        *,
        simulated_time: datetime,
    ) -> Tuple[bool, Optional[str]]:
        """Pure no-lookahead gate for a single kline record.

        Returns ``(True, None)`` only when the record is usable at
        ``simulated_time``:

          * the record's ``available_at`` is ``<= simulated_time``
            (Constitution §5), AND
          * the record's candle has CLOSED
            (``close_time <= simulated_time``; Constitution §6), AND
          * the record's interval matches the configured timeframe.

        Otherwise returns ``(False, reason)`` with a closed
        :class:`PaperShadowRejectReason`. The guard NEVER raises on a
        future record; the bridge routes the reason into its rejection
        diagnostics instead of silently continuing.
        """
        st = ensure_utc_aware(simulated_time, "simulated_time")
        interval = getattr(record, "interval", None)
        if interval != self._config.timeframe:
            return False, PaperShadowRejectReason.WRONG_TIMEFRAME
        available_at = getattr(record, "available_at", None)
        if available_at is None:
            return (
                False,
                PaperShadowRejectReason.FEATURE_NOT_YET_AVAILABLE_AT_ASOF_TIME,
            )
        av = ensure_utc_aware(available_at, "available_at")
        if av > st:
            return (
                False,
                PaperShadowRejectReason.FEATURE_NOT_YET_AVAILABLE_AT_ASOF_TIME,
            )
        close_time = getattr(record, "close_time", None)
        if close_time is None:
            return False, PaperShadowRejectReason.UNCLOSED_CANDLE
        ct = ensure_utc_aware(close_time, "close_time")
        if ct > st:
            return False, PaperShadowRejectReason.UNCLOSED_CANDLE
        return True, None

    # ------------------------------------------------------------------
    # Decision-callback entry point
    # ------------------------------------------------------------------

    def __call__(
        self,
        simulated_time: datetime,
        batch: ReplayFeedBatch,
        runner: Any = None,
    ) -> Sequence[OrderRequest]:
        """Decision-callback contract.

        Ingests the batch's CLOSED, available klines, evaluates the
        deterministic baseline rule per symbol, and returns the
        :class:`OrderRequest` objects to submit. Rejections are stored
        for the runner to drain via :meth:`drain_rejections`.
        """
        if not isinstance(batch, ReplayFeedBatch):
            raise TypeError(
                f"batch must be ReplayFeedBatch, got {type(batch)!r}"
            )
        st = ensure_utc_aware(simulated_time, "simulated_time")
        self._diagnostics.steps_seen += 1
        self._pending_rejections = []

        asof_symbols = self._asof_symbols(batch)
        ingested_symbols = self._ingest_visible_klines(
            batch=batch, simulated_time=st, asof_symbols=asof_symbols
        )

        orders: List[OrderRequest] = []
        # Evaluate symbols in deterministic (sorted) order.
        for symbol in sorted(ingested_symbols):
            new_orders = self._evaluate_symbol(
                symbol=symbol,
                simulated_time=st,
                asof_symbols=asof_symbols,
            )
            orders.extend(new_orders)
        return tuple(orders)

    def drain_rejections(self) -> Tuple[Dict[str, Any], ...]:
        """Return and clear the rejections produced by the last call."""
        out = tuple(self._pending_rejections)
        self._pending_rejections = []
        return out

    # ------------------------------------------------------------------
    # Internal: ingestion
    # ------------------------------------------------------------------

    def _asof_symbols(self, batch: ReplayFeedBatch) -> Optional[FrozenSet[str]]:
        if not self._config.restrict_to_asof_universe:
            return None
        syms = {
            getattr(r, "symbol", None)
            for r in getattr(batch, "asof_universe", ())
        }
        syms.discard(None)
        # When the provider emits no as-of universe (e.g. kline-only
        # smoke stores), do NOT block trading on it.
        if not syms:
            return None
        return frozenset(syms)  # type: ignore[arg-type]

    def _symbol_allowed(self, symbol: str) -> bool:
        if self._config.symbols is None:
            return True
        return symbol in self._config.symbols

    def _ingest_visible_klines(
        self,
        *,
        batch: ReplayFeedBatch,
        simulated_time: datetime,
        asof_symbols: Optional[FrozenSet[str]],
    ) -> List[str]:
        """Append every visible, closed, non-duplicate kline for the
        configured timeframe to its per-symbol rolling window.

        Returns the list of symbols that received a new bar this step
        (deduplicated).
        """
        if self._config.timeframe == "1m":
            klines = list(getattr(batch, "klines_1m", ()))
        else:
            klines = list(getattr(batch, "klines_5m", ()))

        touched: Dict[str, None] = {}
        # Deterministic ingestion order: by (open_time, record_id).
        for k in sorted(
            klines,
            key=lambda r: (
                getattr(r, "open_time", simulated_time),
                getattr(r, "record_id", ""),
            ),
        ):
            self._diagnostics.klines_considered += 1
            symbol = getattr(k, "symbol", None)
            if not isinstance(symbol, str) or not symbol:
                continue
            if not self._symbol_allowed(symbol):
                continue
            visible, reason = self.is_record_visible(
                k, simulated_time=simulated_time
            )
            if not visible:
                self._record_kline_rejection(
                    symbol=symbol,
                    simulated_time=simulated_time,
                    reason=reason or PaperShadowRejectReason.UNCLOSED_CANDLE,
                    record=k,
                )
                continue
            state = self._states.get(symbol)
            if state is None:
                state = _SymbolState(
                    bars=deque(
                        maxlen=self._config.min_history_bars
                        + self._config.breakout_lookback
                        + 4
                    )
                )
                self._states[symbol] = state
            open_time = ensure_utc_aware(
                getattr(k, "open_time"), "open_time"
            )
            # Forward-only de-dup: never re-ingest a bar we have
            # already (or one earlier than) seen.
            if (
                state.last_open_time is not None
                and open_time <= state.last_open_time
            ):
                self._diagnostics.klines_rejected_duplicate += 1
                continue
            bar = _ClosedBar(
                symbol=symbol,
                open_time=open_time,
                close_time=ensure_utc_aware(
                    getattr(k, "close_time"), "close_time"
                ),
                available_at=ensure_utc_aware(
                    getattr(k, "available_at"), "available_at"
                ),
                open=float(getattr(k, "open")),
                high=float(getattr(k, "high")),
                low=float(getattr(k, "low")),
                close=float(getattr(k, "close")),
                volume=float(getattr(k, "volume")),
                record_id=str(getattr(k, "record_id", "")),
            )
            state.bars.append(bar)
            state.last_open_time = open_time
            state.bars_seen += 1
            self._diagnostics.klines_ingested += 1
            touched[symbol] = None
        return list(touched.keys())

    def _record_kline_rejection(
        self,
        *,
        symbol: str,
        simulated_time: datetime,
        reason: str,
        record: Any,
    ) -> None:
        if reason == (
            PaperShadowRejectReason.FEATURE_NOT_YET_AVAILABLE_AT_ASOF_TIME
        ):
            self._diagnostics.klines_rejected_not_available += 1
        elif reason == PaperShadowRejectReason.UNCLOSED_CANDLE:
            self._diagnostics.klines_rejected_unclosed += 1
        elif reason == PaperShadowRejectReason.WRONG_TIMEFRAME:
            self._diagnostics.klines_rejected_wrong_timeframe += 1
        self._add_rejection(
            symbol=symbol,
            simulated_time=simulated_time,
            reason=reason,
            detail=(
                f"record_id={getattr(record, 'record_id', '')} "
                f"available_at={getattr(record, 'available_at', '')} "
                f"close_time={getattr(record, 'close_time', '')}"
            ),
        )

    # ------------------------------------------------------------------
    # Internal: per-symbol rule evaluation
    # ------------------------------------------------------------------

    def _open_positions(self) -> Dict[str, Any]:
        if self._capital_flow is None:
            return {}
        out: Dict[str, Any] = {}
        for p in self._capital_flow.get_positions():
            sym = getattr(p, "symbol", None)
            if isinstance(sym, str) and sym:
                out[sym] = p
        return out

    def _capital_exhausted(self) -> bool:
        cf = self._capital_flow
        if cf is None:
            return False
        return bool(getattr(cf, "capital_exhausted", False))

    def _capital_safety_block(self) -> Tuple[bool, Optional[str]]:
        """Return ``(True, detail)`` when the bound Simulated Capital
        Flow has latched its kill switch (PR108). Read-only / duck-typed
        so a non-capital-flow stub (older tests) never trips this gate.
        """
        cf = self._capital_flow
        if cf is None:
            return False, None
        halted = bool(getattr(cf, "account_halted", False)) or bool(
            getattr(cf, "capital_exhausted", False)
        )
        if not halted:
            return False, None
        return True, str(getattr(cf, "halt_reason", None))

    def _evaluate_symbol(
        self,
        *,
        symbol: str,
        simulated_time: datetime,
        asof_symbols: Optional[FrozenSet[str]],
    ) -> List[OrderRequest]:
        state = self._states.get(symbol)
        if state is None or not state.bars:
            return []
        open_positions = self._open_positions()
        position = open_positions.get(symbol)

        # --- Reconcile the in-flight intent against the real book ---
        if state.intent == _Intent.ENTRY_PENDING and position is not None:
            state.intent = _Intent.LONG
            state.entry_bar_index = state.bars_seen
        elif state.intent == _Intent.EXIT_PENDING and position is None:
            state.intent = _Intent.FLAT
            state.entry_bar_index = None
            state.entry_signal_reason = None
        elif state.intent == _Intent.LONG and position is None:
            # Position closed underneath us (e.g. forced exit). Reset.
            state.intent = _Intent.FLAT
            state.entry_bar_index = None
            state.entry_signal_reason = None
        elif state.intent == _Intent.FLAT and position is not None:
            # A position exists we did not open (defensive). Track it.
            state.intent = _Intent.LONG
            if state.entry_bar_index is None:
                state.entry_bar_index = state.bars_seen

        if state.intent in (_Intent.ENTRY_PENDING, _Intent.EXIT_PENDING):
            # Wait for the in-flight fill to reconcile before acting.
            return []

        if state.intent == _Intent.LONG and position is not None:
            return self._maybe_exit(
                symbol=symbol,
                state=state,
                position=position,
                simulated_time=simulated_time,
            )

        if state.intent == _Intent.FLAT and position is None:
            return self._maybe_enter(
                symbol=symbol,
                state=state,
                simulated_time=simulated_time,
                asof_symbols=asof_symbols,
                open_positions=open_positions,
            )
        return []

    def _maybe_enter(
        self,
        *,
        symbol: str,
        state: _SymbolState,
        simulated_time: datetime,
        asof_symbols: Optional[FrozenSet[str]],
        open_positions: Mapping[str, Any],
    ) -> List[OrderRequest]:
        cfg = self._config
        bars = list(state.bars)
        if len(bars) < cfg.min_history_bars:
            return []
        current = bars[-1]
        prior = bars[-(cfg.breakout_lookback + 1):-1]
        if len(prior) < cfg.breakout_lookback:
            return []

        prior_high = max(b.high for b in prior)
        prior_vol_mean = sum(b.volume for b in prior) / float(len(prior))
        breakout = current.close > prior_high
        volume_expansion = current.volume > (
            cfg.volume_multiplier * prior_vol_mean
        )
        green = current.close >= current.open
        if not (breakout and volume_expansion):
            return []
        if cfg.require_green_bar and not green:
            return []

        # As-of universe gate (Constitution §9): never trade a symbol
        # that is not tradable/monitorable as-of the current time.
        if asof_symbols is not None and symbol not in asof_symbols:
            self._add_rejection(
                symbol=symbol,
                simulated_time=simulated_time,
                reason=PaperShadowRejectReason.SYMBOL_NOT_IN_ASOF_UNIVERSE,
                detail="entry signal suppressed: symbol not as-of tradable",
            )
            return []

        # Concurrency cap.
        if len(open_positions) >= cfg.max_concurrent_positions:
            self._add_rejection(
                symbol=symbol,
                simulated_time=simulated_time,
                reason=(
                    PaperShadowRejectReason.MAX_CONCURRENT_POSITIONS_REACHED
                ),
                detail=(
                    f"open_positions={len(open_positions)} "
                    f">= max_concurrent_positions="
                    f"{cfg.max_concurrent_positions}"
                ),
            )
            return []

        # PR108 capital-safety kill switch: once the bound Simulated
        # Capital Flow has halted (capital exhausted or hard drawdown
        # limit breached) the bridge must stop emitting NEW entries for
        # the rest of the blind window. A genuine breakout signal is
        # suppressed and recorded (NEVER silently dropped). The runner's
        # pre-entry gate is the authoritative second line of defence.
        halted, halt_detail = self._capital_safety_block()
        if halted:
            self._add_rejection(
                symbol=symbol,
                simulated_time=simulated_time,
                reason=(
                    PaperShadowRejectReason.CAPITAL_EXHAUSTED
                    if self._capital_exhausted()
                    else PaperShadowRejectReason.ACCOUNT_HALTED
                ),
                detail=(
                    "entry signal suppressed: simulated account halted "
                    f"({halt_detail})"
                ),
            )
            return []

        qty = cfg.position_notional / current.close
        if not math.isfinite(qty) or qty <= 0.0:
            return []
        evidence_refs = self._build_evidence_refs(
            reason=PaperShadowSignalReason.BREAKOUT_VOLUME_ENTRY,
            bars=prior + [current],
        )
        request = OrderRequest(
            symbol=symbol,
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=qty,
            client_tag=(
                f"paper_shadow:{cfg.bridge_name}:"
                f"{PaperShadowSignalReason.BREAKOUT_VOLUME_ENTRY}"
            ),
            evidence_refs=evidence_refs,
        )
        state.intent = _Intent.ENTRY_PENDING
        state.entry_signal_reason = (
            PaperShadowSignalReason.BREAKOUT_VOLUME_ENTRY
        )
        self._diagnostics.entry_signals += 1
        return [request]

    def _maybe_exit(
        self,
        *,
        symbol: str,
        state: _SymbolState,
        position: Any,
        simulated_time: datetime,
    ) -> List[OrderRequest]:
        cfg = self._config
        bars = list(state.bars)
        if not bars:
            return []
        current = bars[-1]
        entry_price = float(getattr(position, "avg_entry_price", 0.0) or 0.0)
        qty = float(getattr(position, "qty", 0.0) or 0.0)
        if qty <= 0.0:
            return []
        reason: Optional[str] = None
        if entry_price > 0.0:
            if current.close >= entry_price * (1.0 + cfg.take_profit_pct):
                reason = PaperShadowSignalReason.EXIT_TAKE_PROFIT
            elif current.close <= entry_price * (1.0 - cfg.stop_loss_pct):
                reason = PaperShadowSignalReason.EXIT_STOP_LOSS
        if reason is None and state.entry_bar_index is not None:
            bars_held = state.bars_seen - state.entry_bar_index
            if bars_held >= cfg.max_hold_bars:
                reason = PaperShadowSignalReason.EXIT_MAX_HOLD
        if reason is None:
            return []
        evidence_refs = self._build_evidence_refs(reason=reason, bars=[current])
        request = OrderRequest(
            symbol=symbol,
            side=MockOrderSide.SELL,
            order_type=MockOrderType.MARKET,
            requested_qty=qty,
            client_tag=f"paper_shadow:{cfg.bridge_name}:{reason}",
            evidence_refs=evidence_refs,
        )
        state.intent = _Intent.EXIT_PENDING
        self._diagnostics.exit_signals += 1
        return [request]

    # ------------------------------------------------------------------
    # Internal: evidence refs + rejection bookkeeping
    # ------------------------------------------------------------------

    def _build_evidence_refs(
        self,
        *,
        reason: str,
        bars: Sequence[_ClosedBar],
    ) -> Tuple[str, ...]:
        refs: List[str] = [f"signal:{reason}"]
        # Reference only already-available, closed bars (as-of refs).
        for b in bars:
            refs.append(
                f"asof:{b.symbol}:{b.close_time.isoformat()}:{b.record_id}"
            )
        return tuple(refs)

    def _add_rejection(
        self,
        *,
        symbol: str,
        simulated_time: datetime,
        reason: str,
        detail: str,
    ) -> None:
        if reason not in PaperShadowRejectReason.ALLOWED:
            raise ValueError(
                f"reject reason {reason!r} not in closed taxonomy"
            )
        self._diagnostics.rejections += 1
        self._pending_rejections.append(
            {
                "symbol": symbol,
                "simulated_time": ensure_utc_aware(
                    simulated_time, "simulated_time"
                ).isoformat(),
                "reason": reason,
                "detail": detail,
                "bridge_name": self._config.bridge_name,
                "is_simulated": True,
                "no_live_order": True,
                "trade_authority": False,
                "ai_trade_authority": False,
                "phase_12_forbidden": True,
            }
        )


__all__ = [
    "PHASE_NAME",
    "DEFAULT_BRIDGE_NAME",
    "PaperShadowSignalReason",
    "PaperShadowRejectReason",
    "PaperShadowStrategyBridge",
    "PaperShadowStrategyBridgeConfig",
    "PaperShadowStrategyBridgeDiagnostics",
]
