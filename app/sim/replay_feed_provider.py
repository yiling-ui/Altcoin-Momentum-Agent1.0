"""ReplayFeedProvider v0 for Phase 11C.1D-D-C (PR96).

Strict blind walk-forward historical replay feed provider. This module
is the **third** anti-future-lookahead infrastructure block of the
strict blind walk-forward stack defined by Phase 11C.1D-D (the
*Strict Blind Walk-forward Sim-Live Constitution*, PR93). It builds
strictly on top of the PR94 substrate (:class:`SimulationClock`,
:class:`HistoricalRecordTime`, :class:`TimeWallGuard`,
:class:`CandleVisibilityGuard`, :class:`NoLookaheadViolation`,
:func:`assert_no_forbidden_fields`) and the PR95 substrate
(:class:`HistoricalMarketStore`, :class:`HistoricalMarketRecord`,
:class:`HistoricalKlineRecord`, :class:`SymbolStatusRecord`,
:class:`HistoricalMarketRecordType`, :class:`SymbolStatus`,
:class:`DataQualityFlag`, :class:`DataCompletenessState`).

Constitution §5: at simulated time ``T``, the system MAY only access
records whose ``available_at <= T``. Constitution §6: a 1m / 5m /
longer-period candle's final OHLCV is fully visible only after that
candle has closed. Constitution §9: the as-of universe at ``T`` MUST
NOT use the *current* symbol list to reconstruct the past.

The :class:`ReplayFeedProvider` is the deterministic, forward-only
feed layer that consumes a :class:`HistoricalMarketStore` and a
:class:`SimulationClock` and emits per-tick :class:`ReplayFeedBatch`
batches that obey those rules. The provider is the data-feed
substrate that the (separately gated) PR100 *Blind Walk-forward
Runner* will eventually drive; this PR does NOT implement the
runner, the MockExchange, the Pessimistic Fill Model, the Simulated
Capital Flow, the Trade Ledger, or the Telegram Sandbox Outbox.

Hard safety boundary (Phase 11C.1D-D-C / PR96):

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
  - place an order
  - emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / stop_loss / target /
    take_profit / risk_budget / order / execution_command
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - authorize live trading or auto-tuning
  - enter Phase 12

This module does NOT and CANNOT:

  - implement the MockExchange + Pessimistic Fill Model (PR97's
    responsibility),
  - implement the Simulated Capital Flow + Trade Ledger (PR98's
    responsibility),
  - implement the Telegram Sandbox Outbox (PR99's responsibility),
  - implement the Blind Walk-forward Runner (PR100's responsibility),
  - read real market network,
  - tune any parameter or rule.

PR96 acceptance only authorises **PR97 - MockExchange + Pessimistic
Fill Model v0** to begin its own gate. It does NOT authorise PR98 /
PR99 / PR100, live trading, auto-tuning, the DeepSeek hot path,
Telegram live outbound, or Phase 12. Phase 12 remains FORBIDDEN.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Union,
)

from app.sim.historical_market_store import (
    DataCompletenessState,
    DataQualityFlag,
    HistoricalKlineRecord,
    HistoricalMarketRecord,
    HistoricalMarketRecordType,
    HistoricalMarketStore,
    SymbolStatus,
    SymbolStatusRecord,
)
from app.sim.simulation_clock import (
    SimulationClock,
    ensure_utc_aware,
    parse_interval_seconds,
)
from app.sim.time_wall_guard import (
    CandleVisibilityGuard,
    NoLookaheadViolation,
    NoLookaheadViolationReason,
    TimeWallGuard,
    assert_no_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-C / PR96 / ReplayFeedProvider v0"
)


# ---------------------------------------------------------------------------
# Default "include all" record-type list (Constitution §10 v0 minimum)
# ---------------------------------------------------------------------------

_DEFAULT_INCLUDE_RECORD_TYPES: Tuple[str, ...] = (
    HistoricalMarketRecordType.KLINE_1M,
    HistoricalMarketRecordType.KLINE_5M,
    HistoricalMarketRecordType.FUNDING_RATE,
    HistoricalMarketRecordType.OPEN_INTEREST,
    HistoricalMarketRecordType.TICKER_24H,
    HistoricalMarketRecordType.EXCHANGE_INFO,
    HistoricalMarketRecordType.SYMBOL_STATUS,
    HistoricalMarketRecordType.LISTING_STATUS,
    HistoricalMarketRecordType.DELISTING_STATUS,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    """Project-wide safety boundary, re-pinned on every serialisation
    boundary in this module so that no payload can ever be misread as
    authorising live trading, auto-tuning, or Phase 12.
    """
    return {
        "phase": PHASE_NAME,
        "mode": "paper",
        "sandbox_only": True,
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
        "is_replay_feed_provider_payload": True,
        "is_trade": False,
        "is_runtime_patch": False,
    }


def _coerce_to_timedelta(
    delta: Union[timedelta, int, float, str],
) -> timedelta:
    if isinstance(delta, timedelta):
        return delta
    if isinstance(delta, bool):
        # bool is a subclass of int; refuse it here.
        raise TypeError(
            "step delta must be timedelta / number / interval string, "
            "got bool"
        )
    if isinstance(delta, (int, float)):
        return timedelta(seconds=float(delta))
    if isinstance(delta, str):
        return timedelta(seconds=parse_interval_seconds(delta))
    raise TypeError(
        f"step delta must be timedelta / number / interval string, "
        f"got {type(delta)!r}"
    )


def _record_sort_key(record: Any) -> Tuple[Any, ...]:
    """Deterministic sort key used everywhere a record list is emitted.

    For klines, ``event_time`` defaults to ``open_time`` at construction
    so this falls back to ``open_time`` automatically. The trailing
    ``record_id`` and ``symbol`` make ordering total.
    """
    event_time = getattr(record, "event_time", None) or getattr(
        record, "open_time", None
    )
    available_at = getattr(record, "available_at", None)
    symbol = getattr(record, "symbol", None) or ""
    record_id = getattr(record, "record_id", None) or ""
    return (event_time, available_at, symbol, record_id)


# ---------------------------------------------------------------------------
# ReplayFeedProviderConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayFeedProviderConfig:
    """Configuration for a :class:`ReplayFeedProvider`.

    Hard rules:

      * ``start_time`` and ``end_time`` are timezone-aware UTC and
        ``end_time >= start_time``.
      * ``step_interval`` is a strictly positive ``timedelta`` (numbers
        are coerced to seconds; interval strings such as ``"1m"`` are
        coerced via :func:`parse_interval_seconds`).
      * ``include_record_types`` is a non-empty tuple of values from
        :data:`HistoricalMarketRecordType.ALLOWED`.
      * ``symbols`` is either ``None`` (no filter) or a non-empty tuple
        of non-empty strings.
      * ``include_asof_universe`` / ``allow_reemit`` /
        ``strict_time_wall`` / ``strict_candle_visibility`` are bools.

    The config is **frozen**; downstream modules cannot mutate
    visibility rules at runtime. Loosening any rule requires a new
    config object (and is a docs / brief / new-PR concern).
    """

    start_time: datetime
    end_time: datetime
    step_interval: Union[timedelta, int, float, str]
    include_record_types: Tuple[str, ...] = _DEFAULT_INCLUDE_RECORD_TYPES
    symbols: Optional[Tuple[str, ...]] = None
    include_asof_universe: bool = True
    allow_reemit: bool = False
    strict_time_wall: bool = True
    strict_candle_visibility: bool = True

    def __post_init__(self) -> None:
        st = ensure_utc_aware(self.start_time, "start_time")
        et = ensure_utc_aware(self.end_time, "end_time")
        if et < st:
            raise ValueError("end_time must be >= start_time")
        si = _coerce_to_timedelta(self.step_interval)
        if si <= timedelta(0):
            raise ValueError("step_interval must be > 0")
        irt = tuple(self.include_record_types)
        if not irt:
            raise ValueError("include_record_types must be non-empty")
        for t in irt:
            if t not in HistoricalMarketRecordType.ALLOWED:
                raise ValueError(
                    f"include_record_types contains unknown type "
                    f"{t!r}; allowed: "
                    f"{sorted(HistoricalMarketRecordType.ALLOWED)}"
                )
        if len(set(irt)) != len(irt):
            raise ValueError(
                "include_record_types must not contain duplicates"
            )
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
        for fname, fval in (
            ("include_asof_universe", self.include_asof_universe),
            ("allow_reemit", self.allow_reemit),
            ("strict_time_wall", self.strict_time_wall),
            ("strict_candle_visibility", self.strict_candle_visibility),
        ):
            if not isinstance(fval, bool):
                raise TypeError(
                    f"{fname} must be bool, got {type(fval)!r}"
                )
        object.__setattr__(self, "start_time", st)
        object.__setattr__(self, "end_time", et)
        object.__setattr__(self, "step_interval", si)
        object.__setattr__(self, "include_record_types", irt)
        object.__setattr__(self, "symbols", syms)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "step_interval_seconds": self.step_interval.total_seconds(),
            "include_record_types": list(self.include_record_types),
            "symbols": (
                list(self.symbols) if self.symbols is not None else None
            ),
            "include_asof_universe": self.include_asof_universe,
            "allow_reemit": self.allow_reemit,
            "strict_time_wall": self.strict_time_wall,
            "strict_candle_visibility": self.strict_candle_visibility,
            "is_replay_feed_provider_config": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# ReplayFeedDiagnostics
# ---------------------------------------------------------------------------


@dataclass
class ReplayFeedDiagnostics:
    """Cumulative diagnostics for a :class:`ReplayFeedProvider`.

    The provider mutates this object across calls; callers that want
    a stable snapshot use :meth:`snapshot`.
    """

    total_records_considered: int = 0
    emitted_record_count: int = 0
    future_records_rejected_count: int = 0
    missing_available_at_count: int = 0
    unclosed_candle_violation_count: int = 0
    duplicate_record_skipped_count: int = 0
    data_gap_flags: List[str] = field(default_factory=list)
    violations: List[NoLookaheadViolation] = field(default_factory=list)

    def record_violation(self, v: NoLookaheadViolation) -> None:
        """Append ``v`` and bump the matching reason counter.

        :class:`NoLookaheadViolationReason.OUTCOME_LABEL_DURING_BLIND_WINDOW`
        and :class:`NoLookaheadViolationReason.INGESTED_AT_USED_AS_AVAILABILITY`
        are stored in :pyattr:`violations` but do not have a dedicated
        v0 counter; downstream PRs (PR100) will fold them into the run
        invalidation matrix.
        """
        if not isinstance(v, NoLookaheadViolation):
            raise TypeError(
                f"violation must be NoLookaheadViolation, got "
                f"{type(v)!r}"
            )
        self.violations.append(v)
        r = v.reason
        if r == NoLookaheadViolationReason.FUTURE_AVAILABLE_AT:
            self.future_records_rejected_count += 1
        elif r == NoLookaheadViolationReason.MISSING_AVAILABLE_AT:
            self.missing_available_at_count += 1
        elif r == (
            NoLookaheadViolationReason.UNCLOSED_CANDLE_FIELD_ACCESS
        ):
            self.unclosed_candle_violation_count += 1
        # Other reasons are stored in violations but not counted in v0.

    def record_data_quality_flag(self, flag: str) -> None:
        if not isinstance(flag, str):
            raise TypeError(
                f"flag must be a string, got {type(flag)!r}"
            )
        if flag not in DataQualityFlag.ALLOWED:
            raise ValueError(
                f"flag {flag!r} not in closed taxonomy "
                f"{sorted(DataQualityFlag.ALLOWED)}"
            )
        if flag not in self.data_gap_flags:
            self.data_gap_flags.append(flag)

    def snapshot(self) -> "ReplayFeedDiagnostics":
        """Return a deep-copy snapshot of the diagnostics."""
        return ReplayFeedDiagnostics(
            total_records_considered=self.total_records_considered,
            emitted_record_count=self.emitted_record_count,
            future_records_rejected_count=(
                self.future_records_rejected_count
            ),
            missing_available_at_count=self.missing_available_at_count,
            unclosed_candle_violation_count=(
                self.unclosed_candle_violation_count
            ),
            duplicate_record_skipped_count=(
                self.duplicate_record_skipped_count
            ),
            data_gap_flags=list(self.data_gap_flags),
            violations=list(self.violations),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "total_records_considered": self.total_records_considered,
            "emitted_record_count": self.emitted_record_count,
            "future_records_rejected_count": (
                self.future_records_rejected_count
            ),
            "missing_available_at_count": (
                self.missing_available_at_count
            ),
            "unclosed_candle_violation_count": (
                self.unclosed_candle_violation_count
            ),
            "duplicate_record_skipped_count": (
                self.duplicate_record_skipped_count
            ),
            "data_gap_flags": list(self.data_gap_flags),
            "violations": [v.to_dict() for v in self.violations],
            "is_replay_feed_diagnostics": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# ReplayFeedCursor
# ---------------------------------------------------------------------------


@dataclass
class ReplayFeedCursor:
    """Forward-only cursor for a :class:`ReplayFeedProvider`.

    The cursor mirrors :class:`SimulationClock` discipline: it NEVER
    moves backward, NEVER falls below ``start_time``, and NEVER
    exceeds ``end_time``. The provider is responsible for keeping
    cursor and clock in sync.
    """

    start_time: datetime
    end_time: datetime
    step_interval: timedelta
    current_time: datetime
    emitted_record_ids: Set[str] = field(default_factory=set)
    replay_complete: bool = False

    def __post_init__(self) -> None:
        st = ensure_utc_aware(self.start_time, "start_time")
        et = ensure_utc_aware(self.end_time, "end_time")
        if et < st:
            raise ValueError("end_time must be >= start_time")
        ct = ensure_utc_aware(self.current_time, "current_time")
        if ct < st:
            raise ValueError("current_time must be >= start_time")
        if ct > et:
            raise ValueError("current_time must be <= end_time")
        if not isinstance(self.step_interval, timedelta):
            raise TypeError(
                f"step_interval must be timedelta, got "
                f"{type(self.step_interval)!r}"
            )
        if self.step_interval <= timedelta(0):
            raise ValueError("step_interval must be > 0")
        if not isinstance(self.emitted_record_ids, set):
            raise TypeError(
                "emitted_record_ids must be a set"
            )
        if not isinstance(self.replay_complete, bool):
            raise TypeError(
                "replay_complete must be bool"
            )
        self.start_time = st
        self.end_time = et
        self.current_time = ct
        if ct >= et:
            self.replay_complete = True

    def advance_to(self, new_time: datetime) -> datetime:
        """Move the cursor forward to ``new_time``.

        Raises :class:`ValueError` on backward motion or out-of-bounds
        target. Marks :pyattr:`replay_complete` when the cursor
        reaches :pyattr:`end_time`.
        """
        nt = ensure_utc_aware(new_time, "new_time")
        if nt < self.current_time:
            raise ValueError(
                "ReplayFeedCursor cannot move backward"
            )
        if nt < self.start_time:
            raise ValueError(
                "ReplayFeedCursor.advance_to precedes start_time"
            )
        if nt > self.end_time:
            raise ValueError(
                "ReplayFeedCursor.advance_to exceeds end_time"
            )
        self.current_time = nt
        if nt >= self.end_time:
            self.replay_complete = True
        return self.current_time

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "current_time": self.current_time.isoformat(),
            "step_interval_seconds": self.step_interval.total_seconds(),
            "emitted_record_id_count": len(self.emitted_record_ids),
            "replay_complete": self.replay_complete,
            "is_replay_feed_cursor": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# ReplayFeedBatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayFeedBatch:
    """A single emitted batch from a :class:`ReplayFeedProvider`.

    Contract:

      * Every record in :pyattr:`records` / :pyattr:`klines_1m` /
        :pyattr:`klines_5m` / :pyattr:`funding_rates` /
        :pyattr:`open_interest` / :pyattr:`ticker_24h` /
        :pyattr:`symbol_status` has ``available_at <=
        simulated_time`` (Constitution §5).
      * Every kline's underlying candle is closed at
        ``simulated_time`` (Constitution §6); this is implied by the
        :class:`HistoricalKlineRecord` construction-time invariant
        ``available_at >= close_time`` and reasserted by the
        :class:`CandleVisibilityGuard` belt-and-suspenders check.
      * :pyattr:`asof_universe` is the set of
        :class:`SymbolStatusRecord` rows that satisfy Constitution §9
        at ``simulated_time``.
      * :pyattr:`violations` contains every
        :class:`NoLookaheadViolation` produced by the underlying store
        during construction of this batch (subset of the cumulative
        list on :pyattr:`diagnostics.violations`).
      * :pyattr:`records` is the catch-all union of all per-type lists,
        deterministically sorted by ``(event_time, available_at,
        symbol, record_id)``.
      * :pyattr:`phase_12_forbidden` is hard-pinned ``True``;
        :pyattr:`auto_tuning_allowed` and :pyattr:`trade_authority`
        are hard-pinned ``False``.
    """

    batch_id: str
    simulated_time: datetime
    records: Tuple[Any, ...] = ()
    klines_1m: Tuple[HistoricalKlineRecord, ...] = ()
    klines_5m: Tuple[HistoricalKlineRecord, ...] = ()
    funding_rates: Tuple[HistoricalMarketRecord, ...] = ()
    open_interest: Tuple[HistoricalMarketRecord, ...] = ()
    ticker_24h: Tuple[HistoricalMarketRecord, ...] = ()
    symbol_status: Tuple[SymbolStatusRecord, ...] = ()
    asof_universe: Tuple[SymbolStatusRecord, ...] = ()
    diagnostics: Optional[ReplayFeedDiagnostics] = None
    violations: Tuple[NoLookaheadViolation, ...] = ()
    replay_complete: bool = False
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False
    trade_authority: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise ValueError("batch_id must be a non-empty string")
        st = ensure_utc_aware(self.simulated_time, "simulated_time")
        # Hard-pin the safety flags so they cannot be flipped by a
        # caller passing alternative values to the dataclass.
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        if self.auto_tuning_allowed is not False:
            raise ValueError("auto_tuning_allowed must be False")
        if self.trade_authority is not False:
            raise ValueError("trade_authority must be False")
        object.__setattr__(self, "simulated_time", st)
        object.__setattr__(
            self, "records", tuple(self.records)
        )
        object.__setattr__(
            self, "klines_1m", tuple(self.klines_1m)
        )
        object.__setattr__(
            self, "klines_5m", tuple(self.klines_5m)
        )
        object.__setattr__(
            self, "funding_rates", tuple(self.funding_rates)
        )
        object.__setattr__(
            self, "open_interest", tuple(self.open_interest)
        )
        object.__setattr__(
            self, "ticker_24h", tuple(self.ticker_24h)
        )
        object.__setattr__(
            self, "symbol_status", tuple(self.symbol_status)
        )
        object.__setattr__(
            self, "asof_universe", tuple(self.asof_universe)
        )
        object.__setattr__(
            self, "violations", tuple(self.violations)
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "batch_id": self.batch_id,
            "simulated_time": self.simulated_time.isoformat(),
            "records": [r.to_dict() for r in self.records],
            "klines_1m": [r.to_dict() for r in self.klines_1m],
            "klines_5m": [r.to_dict() for r in self.klines_5m],
            "funding_rates": [
                r.to_dict() for r in self.funding_rates
            ],
            "open_interest": [
                r.to_dict() for r in self.open_interest
            ],
            "ticker_24h": [r.to_dict() for r in self.ticker_24h],
            "symbol_status": [
                r.to_dict() for r in self.symbol_status
            ],
            "asof_universe": [
                r.to_dict() for r in self.asof_universe
            ],
            "diagnostics": (
                self.diagnostics.to_dict()
                if self.diagnostics is not None
                else None
            ),
            "violations": [v.to_dict() for v in self.violations],
            "replay_complete": self.replay_complete,
            "is_replay_feed_batch": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# ReplayFeedProvider
# ---------------------------------------------------------------------------


class ReplayFeedProvider:
    """Strict blind walk-forward historical replay feed provider.

    The provider is **deterministic, forward-only, and pure**:

      * It NEVER opens a network socket, signs a request, talks to
        Binance, the Telegram API, or any LLM.
      * It NEVER consults the wall-clock; every visible moment comes
        from the supplied :class:`SimulationClock`.
      * It NEVER writes runtime config; it has no hot path into the
        Risk Engine, the Execution FSM, or the Capital Flow Engine.
      * It NEVER bypasses the
        :class:`HistoricalMarketStore.time_wall_guard` /
        :class:`HistoricalMarketStore.candle_visibility_guard` rules.
      * Two providers fed identical store / clock / config produce
        identical batch sequences.

    Lifecycle:

      1. Construct with a :class:`HistoricalMarketStore`, a
         :class:`SimulationClock`, and a
         :class:`ReplayFeedProviderConfig`.
      2. Drive forward via :meth:`next_batch`,
         :meth:`advance_and_get_batch`, or :meth:`batch_at`.
      3. Read :meth:`get_diagnostics` and (optionally)
         :meth:`get_asof_universe` between batches.
      4. Optionally :meth:`reset` (only with
         ``monotonic_forward_only=False`` on the clock; test-only).
    """

    def __init__(
        self,
        *,
        store: HistoricalMarketStore,
        clock: SimulationClock,
        config: ReplayFeedProviderConfig,
        time_wall_guard: Optional[TimeWallGuard] = None,
        candle_visibility_guard: Optional[CandleVisibilityGuard] = None,
    ) -> None:
        if not isinstance(store, HistoricalMarketStore):
            raise TypeError(
                f"store must be HistoricalMarketStore, got "
                f"{type(store)!r}"
            )
        if not isinstance(clock, SimulationClock):
            raise TypeError(
                f"clock must be SimulationClock, got {type(clock)!r}"
            )
        if not isinstance(config, ReplayFeedProviderConfig):
            raise TypeError(
                f"config must be ReplayFeedProviderConfig, got "
                f"{type(config)!r}"
            )
        # Validate that the clock window contains the config window.
        if clock.start_time_utc > config.start_time:
            raise ValueError(
                "SimulationClock.start_time_utc > config.start_time"
            )
        if (
            clock.end_time_utc is not None
            and clock.end_time_utc < config.end_time
        ):
            raise ValueError(
                "SimulationClock.end_time_utc < config.end_time"
            )
        # Forward-only clocks must not have advanced past config.start_time.
        if (
            clock.monotonic_forward_only
            and clock.now() > config.start_time
        ):
            raise ValueError(
                "SimulationClock has already advanced past "
                "config.start_time; cannot start a fresh replay"
            )
        # Snap clock to config.start_time.
        if clock.now() < config.start_time:
            clock.set_time(config.start_time)
        elif clock.now() > config.start_time:
            # Only reachable when monotonic_forward_only=False.
            clock.set_time(config.start_time)
        self._store: HistoricalMarketStore = store
        self._clock: SimulationClock = clock
        self._config: ReplayFeedProviderConfig = config
        self._tw: TimeWallGuard = (
            time_wall_guard or store.time_wall_guard
        )
        self._cv: CandleVisibilityGuard = (
            candle_visibility_guard or store.candle_visibility_guard
        )
        self._cursor: ReplayFeedCursor = ReplayFeedCursor(
            start_time=config.start_time,
            end_time=config.end_time,
            step_interval=config.step_interval,
            current_time=config.start_time,
        )
        self._diagnostics: ReplayFeedDiagnostics = ReplayFeedDiagnostics()
        self._batch_counter: int = 0
        # Defensive tripwires (mirrors PR94 / PR95 guards).
        self.sandbox_only: bool = True
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
    def store(self) -> HistoricalMarketStore:
        return self._store

    @property
    def clock(self) -> SimulationClock:
        return self._clock

    @property
    def config(self) -> ReplayFeedProviderConfig:
        return self._config

    @property
    def cursor(self) -> ReplayFeedCursor:
        return self._cursor

    @property
    def diagnostics(self) -> ReplayFeedDiagnostics:
        return self._diagnostics

    @property
    def time_wall_guard(self) -> TimeWallGuard:
        return self._tw

    @property
    def candle_visibility_guard(self) -> CandleVisibilityGuard:
        return self._cv

    @property
    def replay_complete(self) -> bool:
        return self._cursor.replay_complete

    # ----- public API -----

    def next_batch(self) -> ReplayFeedBatch:
        """Advance the simulated clock by ``config.step_interval`` and
        return the resulting :class:`ReplayFeedBatch`.

        Raises :class:`StopIteration` when the cursor has already
        reached :pyattr:`config.end_time`.
        """
        if self._cursor.replay_complete:
            raise StopIteration("replay_complete")
        proposed = (
            self._cursor.current_time + self._config.step_interval
        )
        if proposed > self._config.end_time:
            proposed = self._config.end_time
        return self._advance_to_and_build(proposed)

    def advance_and_get_batch(
        self, delta: Union[timedelta, int, float, str]
    ) -> ReplayFeedBatch:
        """Advance the simulated clock by ``delta`` and return the
        resulting :class:`ReplayFeedBatch`.

        ``delta`` may be a :class:`datetime.timedelta`, a number of
        seconds (int / float), or an interval string such as ``"1m"``.
        """
        td = _coerce_to_timedelta(delta)
        if td < timedelta(0):
            raise ValueError(
                "advance_and_get_batch requires delta >= 0"
            )
        if self._cursor.replay_complete and td > timedelta(0):
            raise StopIteration("replay_complete")
        proposed = self._cursor.current_time + td
        if proposed > self._config.end_time:
            proposed = self._config.end_time
        return self._advance_to_and_build(proposed)

    def batch_at(self, simulated_time: datetime) -> ReplayFeedBatch:
        """Advance the simulated clock to ``simulated_time`` (which
        MUST be ``>= cursor.current_time``) and return the resulting
        :class:`ReplayFeedBatch`.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        if sim < self._cursor.current_time:
            raise ValueError(
                "ReplayFeedProvider cannot move backward; "
                f"requested simulated_time={sim.isoformat()} < "
                f"current_time="
                f"{self._cursor.current_time.isoformat()}"
            )
        if sim < self._config.start_time:
            raise ValueError(
                "simulated_time precedes config.start_time"
            )
        if sim > self._config.end_time:
            raise ValueError(
                "simulated_time exceeds config.end_time"
            )
        return self._advance_to_and_build(sim)

    def get_asof_universe(
        self, simulated_time: Optional[datetime] = None
    ) -> Tuple[SymbolStatusRecord, ...]:
        """Return the as-of universe at ``simulated_time``.

        If ``simulated_time`` is ``None``, the cursor's current time
        is used. ``simulated_time`` MUST be ``>=
        cursor.current_time`` (forward-only) and MUST be inside the
        config window.
        """
        if simulated_time is None:
            sim = self._cursor.current_time
        else:
            sim = ensure_utc_aware(simulated_time, "simulated_time")
            if sim < self._cursor.current_time:
                raise ValueError(
                    "ReplayFeedProvider cannot move backward"
                )
            if sim < self._config.start_time:
                raise ValueError(
                    "simulated_time precedes config.start_time"
                )
            if sim > self._config.end_time:
                raise ValueError(
                    "simulated_time exceeds config.end_time"
                )
        pre = len(self._store.violations)
        out = tuple(self._store.query_asof_universe(sim))
        for v in self._store.violations[pre:]:
            self._diagnostics.record_violation(v)
        return out

    def get_diagnostics(self) -> ReplayFeedDiagnostics:
        """Return a snapshot of the cumulative diagnostics."""
        return self._diagnostics.snapshot()

    def reset(self) -> None:
        """Reset cursor / diagnostics / clock back to ``start_time``.

        Test-only: requires ``monotonic_forward_only=False`` on the
        clock. Production callers MUST construct a fresh provider for
        a fresh run.
        """
        if self._clock.monotonic_forward_only:
            raise ValueError(
                "ReplayFeedProvider.reset requires "
                "monotonic_forward_only=False on the clock"
            )
        self._clock.set_time(self._config.start_time)
        self._cursor = ReplayFeedCursor(
            start_time=self._config.start_time,
            end_time=self._config.end_time,
            step_interval=self._config.step_interval,
            current_time=self._config.start_time,
        )
        self._diagnostics = ReplayFeedDiagnostics()
        self._batch_counter = 0

    def safety_payload(self) -> Dict[str, Any]:
        """Return the project-wide safety boundary payload."""
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        return out

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "config": self._config.to_dict(),
            "cursor": self._cursor.to_dict(),
            "diagnostics": self._diagnostics.to_dict(),
            "batch_count": self._batch_counter,
            "is_replay_feed_provider": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    # ----- internal helpers -----

    def _advance_to_and_build(
        self, target: datetime
    ) -> ReplayFeedBatch:
        if target != self._clock.now():
            self._clock.set_time(target)
        if target != self._cursor.current_time:
            self._cursor.advance_to(target)
        elif target == self._config.end_time:
            # Re-mark as complete (idempotent) so a second call sees
            # the cursor settled.
            self._cursor.replay_complete = True
        return self._build_batch(target)

    def _build_batch(self, simulated_time: datetime) -> ReplayFeedBatch:
        config = self._config
        store = self._store
        cursor = self._cursor
        diagnostics = self._diagnostics

        syms_filter: Optional[FrozenSet[str]] = (
            frozenset(config.symbols)
            if config.symbols is not None
            else None
        )

        def _symbol_filter(rec: Any) -> bool:
            if syms_filter is None:
                return True
            sym = getattr(rec, "symbol", None)
            if sym is None:
                # Records with no symbol scope (e.g., exchange info)
                # are always included regardless of symbol filter.
                return True
            return sym in syms_filter

        def _filter_dedup(recs: List[Any]) -> List[Any]:
            out: List[Any] = []
            for r in recs:
                diagnostics.total_records_considered += 1
                if not _symbol_filter(r):
                    continue
                rid = getattr(r, "record_id", None)
                if not config.allow_reemit and rid in (
                    cursor.emitted_record_ids
                ):
                    diagnostics.duplicate_record_skipped_count += 1
                    continue
                out.append(r)
            return out

        pre_violation_count = len(store.violations)

        recs_by_type: Dict[str, List[Any]] = {}
        for rt in config.include_record_types:
            raw = store.query_records(rt, simulated_time=simulated_time)
            recs_by_type[rt] = _filter_dedup(list(raw))

        klines_1m = list(
            recs_by_type.get(HistoricalMarketRecordType.KLINE_1M, [])
        )
        klines_5m = list(
            recs_by_type.get(HistoricalMarketRecordType.KLINE_5M, [])
        )
        funding_rates = list(
            recs_by_type.get(
                HistoricalMarketRecordType.FUNDING_RATE, []
            )
        )
        open_interest = list(
            recs_by_type.get(
                HistoricalMarketRecordType.OPEN_INTEREST, []
            )
        )
        ticker_24h = list(
            recs_by_type.get(
                HistoricalMarketRecordType.TICKER_24H, []
            )
        )
        symbol_status_events = list(
            recs_by_type.get(
                HistoricalMarketRecordType.SYMBOL_STATUS, []
            )
        )

        # Belt-and-suspenders: re-check candle visibility for each
        # emitted kline. By construction, a HistoricalKlineRecord with
        # available_at <= simulated_time has a closed candle (because
        # available_at >= close_time is enforced at construction). The
        # explicit check protects against ill-shaped Mapping-style
        # records that bypassed the dataclass.
        if config.strict_candle_visibility:
            for k in klines_1m + klines_5m:
                ot = getattr(k, "open_time", None)
                interval = getattr(k, "interval", None)
                if ot is None or interval is None:
                    continue
                if not self._cv.is_candle_closed(
                    ot, interval, simulated_time
                ):
                    v = (
                        self._tw.make_unclosed_candle_field_access_violation(
                            simulated_time=simulated_time,
                            field_name="close",
                            candle_open_time=ot,
                            interval=interval,
                            record_id=getattr(k, "record_id", None),
                            symbol=getattr(k, "symbol", None),
                            source=getattr(k, "source", None),
                        )
                    )
                    diagnostics.record_violation(v)
                    raise ValueError(
                        "UNCLOSED_CANDLE_FIELD_ACCESS: replay batch "
                        "would emit a kline whose candle is not yet "
                        "closed at simulated_time"
                    )

        # Aggregate the catch-all "records" union deterministically.
        all_records: List[Any] = []
        for rt in config.include_record_types:
            all_records.extend(recs_by_type[rt])
        all_records_sorted = sorted(all_records, key=_record_sort_key)

        # Update emitted_record_ids on ALL emitted records (including
        # re-emitted ones when allow_reemit=True).
        for r in all_records_sorted:
            rid = getattr(r, "record_id", None)
            if rid:
                cursor.emitted_record_ids.add(rid)

        diagnostics.emitted_record_count += len(all_records_sorted)

        # Aggregate data-quality flags from emitted records.
        for r in all_records_sorted:
            for f in getattr(r, "data_quality_flags", ()):
                if isinstance(f, str) and f in DataQualityFlag.ALLOWED:
                    if f not in diagnostics.data_gap_flags:
                        diagnostics.data_gap_flags.append(f)

        # As-of universe (Constitution §9). Always re-emitted
        # (descriptive snapshot, not deduped).
        asof: Tuple[SymbolStatusRecord, ...] = ()
        if config.include_asof_universe:
            asof = tuple(
                store.query_asof_universe(simulated_time)
            )

        # Process every NoLookaheadViolation produced by this batch's
        # store queries. Append to cumulative diagnostics; expose the
        # batch-local subset on the batch object.
        new_violations = list(store.violations[pre_violation_count:])
        for v in new_violations:
            diagnostics.record_violation(v)

        # Sort per-type lists deterministically too.
        klines_1m.sort(key=_record_sort_key)
        klines_5m.sort(key=_record_sort_key)
        funding_rates.sort(key=_record_sort_key)
        open_interest.sort(key=_record_sort_key)
        ticker_24h.sort(key=_record_sort_key)
        symbol_status_events.sort(key=_record_sort_key)

        self._batch_counter += 1
        batch_id = f"replay_batch_{self._batch_counter:06d}"

        return ReplayFeedBatch(
            batch_id=batch_id,
            simulated_time=simulated_time,
            records=tuple(all_records_sorted),
            klines_1m=tuple(klines_1m),
            klines_5m=tuple(klines_5m),
            funding_rates=tuple(funding_rates),
            open_interest=tuple(open_interest),
            ticker_24h=tuple(ticker_24h),
            symbol_status=tuple(symbol_status_events),
            asof_universe=asof,
            diagnostics=diagnostics.snapshot(),
            violations=tuple(new_violations),
            replay_complete=cursor.replay_complete,
        )


__all__ = [
    "PHASE_NAME",
    "ReplayFeedBatch",
    "ReplayFeedCursor",
    "ReplayFeedDiagnostics",
    "ReplayFeedProvider",
    "ReplayFeedProviderConfig",
]
