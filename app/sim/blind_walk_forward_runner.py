"""Blind walk-forward runner v0 for Phase 11C.1D-D-G (PR100).

Strict blind walk-forward orchestrator. This module is the
**seventh** anti-future-lookahead infrastructure block of the strict
blind walk-forward stack defined by Phase 11C.1D-D (the *Strict
Blind Walk-forward Sim-Live Constitution*, PR93). It strings PR94 /
PR95 / PR96 / PR97 / PR98 / PR99 into the first version of the
strict forward-only historical sim-live blind runner.

The runner:

  * builds and freezes a :class:`BlindRunManifest`,
  * drives :class:`SimulationClock` from ``window.blind_start`` to
    ``window.blind_end``,
  * pulls one batch per step from
    :class:`ReplayFeedProvider`,
  * marks :class:`SimulatedCapitalFlowEngine` against the closed
    1m candles in each batch,
  * forwards every order returned by an optional decision callback
    to :class:`MockExchange` (which uses
    :class:`PessimisticFillModel` under the hood),
  * forwards every fill back into
    :class:`SimulatedCapitalFlowEngine` so the trade ledger and the
    equity time-series stay consistent,
  * writes a sandbox-only Telegram transcript via
    :class:`TelegramSandboxOutbox`,
  * records every :class:`NoLookaheadViolation` and every
    :class:`BlindRunInvalidationReason`,
  * scores **only** after ``window.blind_end`` and **only** via
    :func:`score_blind_run`,
  * emits the full set of operator artefacts to
    ``data/reports/blind_walk_forward/<run_id>/``.

What this runner is NOT (Phase 11C.1D-D-G hard boundary):

  * NOT a live trading runner.
  * NOT an auto-tuner.
  * NOT a Telegram bot.
  * NOT a Binance private-API client.
  * NOT an AI / DeepSeek hot path.
  * NOT a Phase 12 enabler.

This module MUST NOT and CANNOT:

  * import ``app.risk`` / ``app.execution`` / ``app.exchanges`` /
    ``app.telegram`` / ``app.config``,
  * call DeepSeek / any LLM / any network endpoint,
  * place a real exchange order,
  * publish to a real Telegram channel,
  * patch any runtime config / symbol limit / threshold /
    candidate pool / regime weight / strategy parameter,
  * authorise live trading, auto-tuning, or Phase 12.

Successful PR100 acceptance only authorises a paper-only blind-run
checkpoint / operator evidence run. It does NOT authorise live
trading, auto-tuning, real Telegram outbound, real exchange orders,
the Binance private API, or Phase 12.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from app.sim.blind_walk_forward_manifest import (
    ALLOWED_TIMEFRAMES,
    DEFAULT_BASE_CLOCK_STEP,
    BlindRunManifest,
    BlindWalkForwardWindow,
    PHASE_NAME,
    compute_artefact_hash,
    safety_payload as manifest_safety_payload,
)
from app.sim.blind_walk_forward_scoring import (
    BlindRunInvalidationReason,
    BlindRunScore,
    BlindRunStatus,
    score_blind_run,
)
from app.sim.historical_market_store import (
    HistoricalKlineRecord,
    HistoricalMarketStore,
)
from app.sim.mock_exchange import (
    MockExchange,
    MockFill,
    OrderRequest,
)
from app.sim.paper_shadow_strategy_bridge import (
    PaperShadowStrategyBridge,
)
from app.sim.pessimistic_fill_model import (
    AmbiguousIntrabarPolicy,
    PessimisticFillModel,
)
from app.sim.replay_feed_provider import ReplayFeedBatch, ReplayFeedProvider
from app.sim.simulated_capital_flow import (
    CapitalFrozenError,
    CapitalRejectReason,
    ForcedExitReason,
    InsufficientSimulatedEquityError,
    MaxActivePositionsReachedError,
    RiskHaltReason,
    SimAccountHaltedError,
    SimulatedCapitalFlowEngine,
)
from app.sim.simulation_clock import (
    SimulationClock,
    ensure_utc_aware,
    parse_interval_seconds,
)
from app.sim.telegram_sandbox_outbox import (
    TelegramSandboxMessage,
    TelegramSandboxMessageType,
    TelegramSandboxOutbox,
    TelegramSandboxSeverity,
)
from app.sim.time_wall_guard import (
    NoLookaheadViolation,
    assert_no_forbidden_fields,
)
from app.sim.trade_ledger import TradeLedger, TradeLedgerEntry


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

# Re-export PHASE_NAME so callers can import a single symbol from this
# module without reaching into the manifest module.
__phase__ = PHASE_NAME


# ---------------------------------------------------------------------------
# Default report directory
# ---------------------------------------------------------------------------

DEFAULT_REPORT_ROOT: str = "data/reports/blind_walk_forward"


# ---------------------------------------------------------------------------
# Paper-shadow simulated-rejection reasons (PR107 hotfix)
# ---------------------------------------------------------------------------

# Closed reasons for a paper-only SIM_REJECT raised by the runner when
# the (PR98) Simulated Capital Flow refuses to OPEN a new simulated
# position. These are *predictable* simulated risk/capital rejections,
# NOT program errors: the runner records a SIM_REJECT and continues the
# blind run instead of aborting it. They NEVER authorise raising any
# cap, live trading, auto-tuning, or Phase 12.
PAPER_SHADOW_REJECT_MAX_ACTIVE_POSITIONS: str = (
    "max_active_positions_reached"
)
PAPER_SHADOW_REJECT_CAPITAL_FROZEN: str = "capital_frozen"

# PR108 - Simulated Capital Safety Floor / Kill Switch / No Negative
# Equity Guard. Additional closed reasons for a paper-only SIM_REJECT
# raised by the runner's pre-entry capital/risk gate or by the
# Simulated Capital Flow refusing an OPEN. These are *predictable*
# simulated risk/capital rejections, NOT program errors. They NEVER
# authorise raising any cap / floor / drawdown limit, live trading,
# auto-tuning, or Phase 12.
PAPER_SHADOW_REJECT_INSUFFICIENT_EQUITY: str = "insufficient_equity"
PAPER_SHADOW_REJECT_CAPITAL_EXHAUSTED: str = "capital_exhausted"
PAPER_SHADOW_REJECT_RISK_HALT_ACTIVE: str = "risk_halt_active"
PAPER_SHADOW_REJECT_MAX_DRAWDOWN_LIMIT: str = (
    "max_drawdown_limit_reached"
)

# The set of reject reasons that count as capital/risk rejections for
# the report's ``capital_reject_count`` aggregate.
_CAPITAL_REJECT_REASONS: FrozenSet[str] = frozenset(
    {
        PAPER_SHADOW_REJECT_MAX_ACTIVE_POSITIONS,
        PAPER_SHADOW_REJECT_CAPITAL_FROZEN,
        PAPER_SHADOW_REJECT_INSUFFICIENT_EQUITY,
        PAPER_SHADOW_REJECT_CAPITAL_EXHAUSTED,
        PAPER_SHADOW_REJECT_RISK_HALT_ACTIVE,
        PAPER_SHADOW_REJECT_MAX_DRAWDOWN_LIMIT,
    }
)

# Map a closed :class:`CapitalRejectReason` (from the engine's
# pre-entry gate) onto the runner's paper-shadow reject reason string.
_CAPITAL_REJECT_REASON_MAP: Dict[str, str] = {
    CapitalRejectReason.INSUFFICIENT_EQUITY: (
        PAPER_SHADOW_REJECT_INSUFFICIENT_EQUITY
    ),
    CapitalRejectReason.CAPITAL_EXHAUSTED: (
        PAPER_SHADOW_REJECT_CAPITAL_EXHAUSTED
    ),
    CapitalRejectReason.RISK_HALT_ACTIVE: (
        PAPER_SHADOW_REJECT_RISK_HALT_ACTIVE
    ),
    CapitalRejectReason.MAX_DRAWDOWN_LIMIT_REACHED: (
        PAPER_SHADOW_REJECT_MAX_DRAWDOWN_LIMIT
    ),
    CapitalRejectReason.MAX_ACTIVE_POSITIONS_REACHED: (
        PAPER_SHADOW_REJECT_MAX_ACTIVE_POSITIONS
    ),
}


# ---------------------------------------------------------------------------
# Progress logging (PR104)
# ---------------------------------------------------------------------------

# Module logger. Heartbeats go through ``logging`` (NOT stdout) so the
# operator JSON summary printed by ``scripts/run_blind_walk_forward.py``
# stays machine-parseable. Operators see progress by configuring
# logging at INFO (the script does this in ``main``).
_LOGGER = logging.getLogger("app.sim.blind_walk_forward_runner")

# Emit a heartbeat every this many blind-window steps so a long real
# replay (e.g. a 1-day 1m window = 1440 steps) shows liveness instead of
# appearing hung for 10+ minutes with no output directory.
DEFAULT_HEARTBEAT_EVERY_STEPS: int = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safety_payload() -> Dict[str, Any]:
    """Local mirror of the manifest-level safety payload, used by the
    runner's own report / discovery-quality / failure-ledger
    serialisations.
    """
    return manifest_safety_payload()


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(
        f"Object of type {type(obj)!r} is not JSON serialisable"
    )


def _validate_timeframes(tfs: Iterable[Any]) -> Tuple[str, ...]:
    out: List[str] = []
    seen: set = set()
    for tf in tfs:
        if not isinstance(tf, str) or not tf:
            raise TypeError(
                f"timeframe must be a non-empty string, got {type(tf)!r}"
            )
        if tf not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"timeframe {tf!r} not in allowed set "
                f"{ALLOWED_TIMEFRAMES}"
            )
        if tf in seen:
            raise ValueError(
                f"timeframe {tf!r} duplicated in allowed_timeframes"
            )
        seen.add(tf)
        out.append(tf)
    if not out:
        raise ValueError("allowed_timeframes must be non-empty")
    return tuple(out)


def _validate_base_step(step: str) -> str:
    if not isinstance(step, str) or not step:
        raise TypeError(
            f"base_clock_step must be a non-empty string, got "
            f"{type(step)!r}"
        )
    if step not in ALLOWED_TIMEFRAMES:
        raise ValueError(
            f"base_clock_step {step!r} not in allowed set "
            f"{ALLOWED_TIMEFRAMES}"
        )
    if parse_interval_seconds(step) < parse_interval_seconds(
        DEFAULT_BASE_CLOCK_STEP
    ):
        raise ValueError(
            f"base_clock_step must be >= {DEFAULT_BASE_CLOCK_STEP}; "
            f"got {step!r}"
        )
    return step


def _normalise_intrabar_policy(value: Any) -> str:
    if isinstance(value, str) and value:
        v = value.upper()
        allowed = {
            "WORST_CASE",
            "AMBIGUOUS_INTRABAR_PATH",
            "AMBIGUOUS",
        }
        if v not in allowed:
            raise ValueError(
                f"intrabar_ambiguity_policy must be one of "
                f"{sorted(allowed)}; got {value!r}"
            )
        return v
    raise TypeError(
        f"intrabar_ambiguity_policy must be str; got "
        f"{type(value)!r}"
    )


# ---------------------------------------------------------------------------
# Multi-timeframe as-of guard (PR100 brief §4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MultiTimeframeAsOfGuard:
    """Closed-candle / available-at multi-timeframe gate.

    Hard rules (Constitution §6 + PR100 brief §4):

      * every timeframe must be a member of
        :data:`ALLOWED_TIMEFRAMES`,
      * every kline used as a feature input must be **closed** at
        ``simulated_time``: ``open_time + interval <= simulated_time``,
      * every record used as a feature input must satisfy
        ``available_at <= simulated_time``.

    The guard is **pure**: it returns a tuple of structured rejection
    reasons rather than raising, so the runner can route them into
    the no-lookahead violation ledger and the failure ledger.
    """

    base_clock_step: str = DEFAULT_BASE_CLOCK_STEP
    allowed_timeframes: Tuple[str, ...] = ALLOWED_TIMEFRAMES

    def __post_init__(self) -> None:
        bcs = _validate_base_step(self.base_clock_step)
        atf = _validate_timeframes(self.allowed_timeframes)
        if bcs not in atf:
            raise ValueError(
                f"base_clock_step {bcs!r} must be in "
                f"allowed_timeframes {atf!r}"
            )
        object.__setattr__(self, "base_clock_step", bcs)
        object.__setattr__(self, "allowed_timeframes", atf)

    def is_kline_visible(
        self,
        *,
        timeframe: str,
        open_time: datetime,
        available_at: datetime,
        simulated_time: datetime,
    ) -> Tuple[bool, Optional[str]]:
        if timeframe not in self.allowed_timeframes:
            return False, f"timeframe_not_allowed:{timeframe}"
        ot = ensure_utc_aware(open_time, "open_time")
        av = ensure_utc_aware(available_at, "available_at")
        st = ensure_utc_aware(simulated_time, "simulated_time")
        # Closed-candle rule: open_time + interval <= simulated_time.
        interval = timedelta(
            seconds=parse_interval_seconds(timeframe)
        )
        close_time = ot + interval
        if close_time > st:
            return (
                False,
                "unclosed_higher_timeframe_candle",
            )
        # Available-at rule: feature must be observable at simulated_time.
        if av > st:
            return False, "feature_not_yet_available_at_asof_time"
        return True, None


# ---------------------------------------------------------------------------
# As-of feature cache (PR100 brief §4)
# ---------------------------------------------------------------------------


class AsOfFeatureCache:
    """Feature cache keyed by ``as_of_time``.

    Hard rule: a feature with ``as_of_time = T`` is reachable only
    when the consumer's simulated_time is ``>= T``. The cache itself
    NEVER discloses a future feature even if asked for one (it
    returns ``None`` and increments a future-access counter).
    """

    def __init__(self) -> None:
        self._values: Dict[datetime, Dict[str, Any]] = {}
        self._future_access_count: int = 0

    @property
    def future_access_count(self) -> int:
        return self._future_access_count

    @property
    def keys_count(self) -> int:
        return len(self._values)

    def put(
        self,
        *,
        as_of_time: datetime,
        feature_id: str,
        value: Any,
    ) -> None:
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError(
                "feature_id must be a non-empty string"
            )
        ts = ensure_utc_aware(as_of_time, "as_of_time")
        bucket = self._values.setdefault(ts, {})
        bucket[feature_id] = value

    def get(
        self,
        *,
        as_of_time: datetime,
        feature_id: str,
        simulated_time: datetime,
    ) -> Optional[Any]:
        ts = ensure_utc_aware(as_of_time, "as_of_time")
        st = ensure_utc_aware(simulated_time, "simulated_time")
        if ts > st:
            self._future_access_count += 1
            return None
        bucket = self._values.get(ts)
        if bucket is None:
            return None
        return bucket.get(feature_id)


# ---------------------------------------------------------------------------
# Decision callback contract
# ---------------------------------------------------------------------------


# A decision callback receives a (simulated_time, batch, runner)
# triple and returns a tuple of OrderRequest objects. The runner
# forwards the orders to MockExchange. The callback is strategy-less
# in v0; it exists so that tests and downstream PRs can drive the
# substrate without modifying the runner. AI MUST NOT be the
# decision callback.
DecisionCallback = Callable[
    [datetime, ReplayFeedBatch, "BlindWalkForwardRunner"],
    Sequence[OrderRequest],
]


# ---------------------------------------------------------------------------
# BlindWalkForwardRunnerConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlindWalkForwardRunnerConfig:
    """Frozen configuration for one strict blind walk-forward run.

    Hard-pinned safety markers (cannot be flipped by callers):

      * ``ai_blind_window_enabled = False``
      * ``auto_tuning_inside_blind_window = False``
      * ``phase_12_forbidden = True``
    """

    window: BlindWalkForwardWindow
    base_clock_step: str = DEFAULT_BASE_CLOCK_STEP
    allowed_timeframes: Tuple[str, ...] = ALLOWED_TIMEFRAMES
    strict_time_wall: bool = True
    strict_closed_candle_visibility: bool = True
    strict_feature_asof: bool = True
    intrabar_ambiguity_policy: str = "WORST_CASE"
    ai_blind_window_enabled: bool = False
    ai_post_window_summary_enabled: bool = True
    telegram_sandbox_enabled: bool = True
    auto_tuning_inside_blind_window: bool = False
    phase_12_forbidden: bool = True
    # PR106: Paper Shadow Strategy Bridge opt-in markers. These are
    # purely informational manifest/report flags; the actual decision
    # path is supplied via the ``paper_shadow_bridge`` constructor
    # argument. Both default OFF (substrate-only v0 behaviour).
    paper_shadow_strategy_enabled: bool = False
    paper_shadow_strategy_bridge_name: Optional[str] = None
    # Frozen artefact source bundles; the runner hashes each on
    # ``prepare_manifest`` to fill ``BlindRunManifest`` hashes.
    config_artefact: Mapping[str, Any] = field(default_factory=dict)
    rule_artefact: Mapping[str, Any] = field(default_factory=dict)
    feature_schema_artefact: Mapping[str, Any] = field(
        default_factory=dict
    )
    data_manifest_artefact: Mapping[str, Any] = field(
        default_factory=dict
    )
    universe_manifest_artefact: Mapping[str, Any] = field(
        default_factory=dict
    )
    fee_model_artefact: Mapping[str, Any] = field(default_factory=dict)
    slippage_model_artefact: Mapping[str, Any] = field(
        default_factory=dict
    )
    latency_model_artefact: Mapping[str, Any] = field(
        default_factory=dict
    )
    outage_model_artefact: Mapping[str, Any] = field(
        default_factory=dict
    )
    fill_model_artefact: Mapping[str, Any] = field(default_factory=dict)
    # Optional pre-computed manifest hashes (PR103 - Blind Runner
    # Historical Store Input Glue). When an operator wires a real
    # PR101/PR102 Historical Data Store into the runner, the
    # data / universe manifests already carry their own deterministic
    # ``sha256:`` content hashes. Passing them here makes
    # :meth:`prepare_manifest` pin those *real* hashes onto the
    # :class:`BlindRunManifest` instead of hashing the (empty) inline
    # artefact bundle. They are NEVER fabricated: when ``None`` the
    # runner falls back to ``compute_artefact_hash`` of the inline
    # artefact, exactly as before.
    data_manifest_hash: Optional[str] = None
    universe_manifest_hash: Optional[str] = None
    code_commit: str = "unknown"
    run_id: Optional[str] = None
    report_root: str = DEFAULT_REPORT_ROOT

    def __post_init__(self) -> None:
        if not isinstance(self.window, BlindWalkForwardWindow):
            raise TypeError(
                f"window must be BlindWalkForwardWindow; got "
                f"{type(self.window)!r}"
            )
        bcs = _validate_base_step(self.base_clock_step)
        atf = _validate_timeframes(self.allowed_timeframes)
        if bcs not in atf:
            raise ValueError(
                f"base_clock_step {bcs!r} must be in "
                f"allowed_timeframes {atf!r}"
            )
        amb = _normalise_intrabar_policy(self.intrabar_ambiguity_policy)
        # Hard-pinned safety markers cannot be flipped.
        if self.ai_blind_window_enabled is not False:
            raise ValueError(
                "ai_blind_window_enabled must be False (PR100 §5)"
            )
        if self.auto_tuning_inside_blind_window is not False:
            raise ValueError(
                "auto_tuning_inside_blind_window must be False "
                "(PR100 brief)"
            )
        if self.phase_12_forbidden is not True:
            raise ValueError(
                "phase_12_forbidden must be True (Phase 12 = FORBIDDEN)"
            )
        for fname in (
            "strict_time_wall",
            "strict_closed_candle_visibility",
            "strict_feature_asof",
        ):
            if getattr(self, fname) is not True:
                raise ValueError(
                    f"{fname} must be True in blind walk-forward v0"
                )
        if not isinstance(self.paper_shadow_strategy_enabled, bool):
            raise TypeError(
                "paper_shadow_strategy_enabled must be bool"
            )
        if self.paper_shadow_strategy_bridge_name is not None and (
            not isinstance(self.paper_shadow_strategy_bridge_name, str)
            or not self.paper_shadow_strategy_bridge_name
        ):
            raise ValueError(
                "paper_shadow_strategy_bridge_name must be a non-empty "
                "string or None"
            )
        if not isinstance(self.code_commit, str) or not self.code_commit:
            raise ValueError("code_commit must be a non-empty string")
        if (
            not isinstance(self.report_root, str)
            or not self.report_root
        ):
            raise ValueError(
                "report_root must be a non-empty string"
            )
        rid = self.run_id
        if rid is None:
            rid = (
                f"bwf_{self.window.window_id}_"
                f"{self.code_commit[:8]}_"
                f"{uuid.uuid4().hex[:8]}"
            )
        if not isinstance(rid, str) or not rid:
            raise ValueError("run_id must be a non-empty string")
        for fname in (
            "config_artefact",
            "rule_artefact",
            "feature_schema_artefact",
            "data_manifest_artefact",
            "universe_manifest_artefact",
            "fee_model_artefact",
            "slippage_model_artefact",
            "latency_model_artefact",
            "outage_model_artefact",
            "fill_model_artefact",
        ):
            v = getattr(self, fname)
            if not isinstance(v, Mapping):
                raise TypeError(
                    f"{fname} must be a Mapping; got {type(v)!r}"
                )
        # PR103: optional pre-computed manifest hashes must, when
        # provided, be canonical ``sha256:`` strings. We never accept a
        # fabricated / non-hash sentinel here.
        for fname in ("data_manifest_hash", "universe_manifest_hash"):
            v = getattr(self, fname)
            if v is None:
                continue
            if not isinstance(v, str) or not v.startswith("sha256:"):
                raise ValueError(
                    f"{fname}, when provided, must be a non-empty "
                    f"'sha256:'-prefixed string; got {v!r}"
                )
        object.__setattr__(self, "base_clock_step", bcs)
        object.__setattr__(self, "allowed_timeframes", atf)
        object.__setattr__(self, "intrabar_ambiguity_policy", amb)
        object.__setattr__(self, "run_id", rid)


# ---------------------------------------------------------------------------
# Internal phases
# ---------------------------------------------------------------------------


class _RunnerPhase:
    INITIALISED: str = "INITIALISED"
    PREPARED: str = "PREPARED"
    FROZEN: str = "FROZEN"
    BLIND_RUNNING: str = "BLIND_RUNNING"
    BLIND_COMPLETE: str = "BLIND_COMPLETE"
    SCORED: str = "SCORED"
    EMITTED: str = "EMITTED"


# ---------------------------------------------------------------------------
# BlindWalkForwardRunner
# ---------------------------------------------------------------------------


class BlindWalkForwardRunner:
    """Strict blind walk-forward runner v0.

    Wires PR94..PR99 substrate into a single forward-only loop.
    """

    def __init__(
        self,
        *,
        config: BlindWalkForwardRunnerConfig,
        replay_provider: ReplayFeedProvider,
        capital_flow: SimulatedCapitalFlowEngine,
        mock_exchange: MockExchange,
        telegram_sandbox: TelegramSandboxOutbox,
        decision_callback: Optional[DecisionCallback] = None,
        paper_shadow_bridge: Optional[PaperShadowStrategyBridge] = None,
        feature_cache: Optional[AsOfFeatureCache] = None,
        heartbeat_every_steps: int = DEFAULT_HEARTBEAT_EVERY_STEPS,
    ) -> None:
        if not isinstance(config, BlindWalkForwardRunnerConfig):
            raise TypeError(
                f"config must be BlindWalkForwardRunnerConfig; got "
                f"{type(config)!r}"
            )
        if not isinstance(replay_provider, ReplayFeedProvider):
            raise TypeError(
                f"replay_provider must be ReplayFeedProvider; got "
                f"{type(replay_provider)!r}"
            )
        if not isinstance(capital_flow, SimulatedCapitalFlowEngine):
            raise TypeError(
                f"capital_flow must be SimulatedCapitalFlowEngine; "
                f"got {type(capital_flow)!r}"
            )
        if not isinstance(mock_exchange, MockExchange):
            raise TypeError(
                f"mock_exchange must be MockExchange; got "
                f"{type(mock_exchange)!r}"
            )
        if not isinstance(telegram_sandbox, TelegramSandboxOutbox):
            raise TypeError(
                f"telegram_sandbox must be TelegramSandboxOutbox; "
                f"got {type(telegram_sandbox)!r}"
            )
        # Hard cross-component safety assertions (defensive).
        if telegram_sandbox.telegram_outbound_enabled is not False:
            raise ValueError(
                "telegram_sandbox.telegram_outbound_enabled must be "
                "False"
            )
        if (
            telegram_sandbox.telegram_production_channel_enabled
            is not False
        ):
            raise ValueError(
                "telegram_sandbox.telegram_production_channel_enabled"
                " must be False"
            )
        if capital_flow.live_trading is not False:
            raise ValueError("capital_flow.live_trading must be False")
        if capital_flow.exchange_live_orders is not False:
            raise ValueError(
                "capital_flow.exchange_live_orders must be False"
            )
        if capital_flow.binance_private_api_enabled is not False:
            raise ValueError(
                "capital_flow.binance_private_api_enabled must be "
                "False"
            )

        self._config: BlindWalkForwardRunnerConfig = config
        self._replay_provider: ReplayFeedProvider = replay_provider
        self._capital_flow: SimulatedCapitalFlowEngine = capital_flow
        self._mock_exchange: MockExchange = mock_exchange
        self._telegram: TelegramSandboxOutbox = telegram_sandbox
        # PR106: optional Paper Shadow Strategy Bridge. When supplied it
        # acts as the decision callback (it is callable). It is a
        # paper-only, deterministic, no-AI-authority decision path.
        if paper_shadow_bridge is not None:
            if not isinstance(
                paper_shadow_bridge, PaperShadowStrategyBridge
            ):
                raise TypeError(
                    "paper_shadow_bridge must be "
                    "PaperShadowStrategyBridge; got "
                    f"{type(paper_shadow_bridge)!r}"
                )
            if decision_callback is not None:
                raise ValueError(
                    "provide either decision_callback or "
                    "paper_shadow_bridge, not both"
                )
            # Defensive: the bridge can never carry trade / AI / tuning
            # authority.
            for attr in (
                "ai_trade_authority",
                "trade_authority",
                "auto_tuning_allowed",
                "live_trading",
                "exchange_live_orders",
                "binance_private_api_enabled",
            ):
                if getattr(paper_shadow_bridge, attr, False) is not False:
                    raise ValueError(
                        f"paper_shadow_bridge.{attr} must be False"
                    )
            if getattr(paper_shadow_bridge, "phase_12_forbidden", True) \
                    is not True:
                raise ValueError(
                    "paper_shadow_bridge.phase_12_forbidden must be True"
                )
            # Bind the capital-flow position book so the bridge can
            # reconcile its per-symbol intent against the real
            # simulated position state.
            paper_shadow_bridge.attach_capital_flow(capital_flow)
            decision_callback = paper_shadow_bridge
        self._paper_shadow_bridge: Optional[PaperShadowStrategyBridge] = (
            paper_shadow_bridge
        )
        self._paper_shadow_enabled: bool = bool(
            config.paper_shadow_strategy_enabled
            or paper_shadow_bridge is not None
        )
        self._paper_shadow_bridge_name: Optional[str] = (
            paper_shadow_bridge.bridge_name
            if paper_shadow_bridge is not None
            else config.paper_shadow_strategy_bridge_name
        )
        # Enriched, paper-only simulated trade records + per-symbol
        # open-trade metadata used to stamp entry-time equity / side /
        # leverage onto the closed-trade record (PR106 brief §6).
        self._paper_shadow_trades: List[Dict[str, Any]] = []
        self._paper_shadow_open_meta: Dict[str, Dict[str, Any]] = {}
        self._paper_shadow_rejections: List[Dict[str, Any]] = []
        self._paper_shadow_entry_count: int = 0
        self._paper_shadow_exit_count: int = 0
        # PR108: capital-safety / kill-switch bookkeeping (runner side).
        self._capital_reject_count: int = 0
        self._capital_safety_halt_emitted: bool = False
        self._capital_safety_event_count: int = 0
        self._decision_callback: Optional[DecisionCallback] = (
            decision_callback
        )
        self._feature_cache: AsOfFeatureCache = (
            feature_cache or AsOfFeatureCache()
        )
        self._asof_guard: MultiTimeframeAsOfGuard = (
            MultiTimeframeAsOfGuard(
                base_clock_step=config.base_clock_step,
                allowed_timeframes=config.allowed_timeframes,
            )
        )
        self._phase: str = _RunnerPhase.INITIALISED
        self._manifest: Optional[BlindRunManifest] = None
        self._violations: List[NoLookaheadViolation] = []
        self._invalidations: List[Dict[str, Any]] = []
        self._failure_entries: List[Dict[str, Any]] = []
        self._discovery_quality_steps: List[Dict[str, Any]] = []
        self._batches_consumed: int = 0
        self._steps_run: int = 0
        self._safety_boundary_failed: bool = False
        self._score: Optional[BlindRunScore] = None
        self._post_window_ai_summary: Optional[Dict[str, Any]] = None
        self._telegram_message_counter: int = 0
        # Locked clock used for both the simulation and any feature
        # cache lookups; feeding the same clock to the provider keeps
        # the run forward-only.
        self._clock: SimulationClock = replay_provider.clock
        # Defensive: the provider's clock must not advance backwards.
        self._last_simulated_time: datetime = self._clock.now()
        # PR104: progress heartbeat cadence (steps). Clamped to >= 1 so
        # ``steps % heartbeat == 0`` never divides by zero.
        try:
            hb = int(heartbeat_every_steps)
        except (TypeError, ValueError):
            hb = DEFAULT_HEARTBEAT_EVERY_STEPS
        self._heartbeat_every: int = hb if hb > 0 else (
            DEFAULT_HEARTBEAT_EVERY_STEPS
        )
        # Resolved per-run output directory; created at run start so an
        # operator can see the run exists immediately (PR104).
        self._output_dir: Optional[str] = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> BlindWalkForwardRunnerConfig:
        return self._config

    @property
    def manifest(self) -> Optional[BlindRunManifest]:
        return self._manifest

    @property
    def phase_name(self) -> str:
        return self._phase

    @property
    def violations(self) -> Tuple[NoLookaheadViolation, ...]:
        return tuple(self._violations)

    @property
    def invalidations(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(copy.deepcopy(x) for x in self._invalidations)

    @property
    def feature_cache(self) -> AsOfFeatureCache:
        return self._feature_cache

    @property
    def asof_guard(self) -> MultiTimeframeAsOfGuard:
        return self._asof_guard

    @property
    def score(self) -> Optional[BlindRunScore]:
        return self._score

    @property
    def trade_ledger(self) -> TradeLedger:
        return self._capital_flow.get_ledger()

    @property
    def equity_timeseries(self) -> Tuple[Any, ...]:
        return self._capital_flow.get_equity_timeseries()

    @property
    def steps_run(self) -> int:
        return self._steps_run

    @property
    def batches_consumed(self) -> int:
        return self._batches_consumed

    @property
    def paper_shadow_strategy_enabled(self) -> bool:
        return self._paper_shadow_enabled

    @property
    def paper_shadow_strategy_bridge_name(self) -> Optional[str]:
        return self._paper_shadow_bridge_name

    @property
    def paper_shadow_trades(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(copy.deepcopy(x) for x in self._paper_shadow_trades)

    @property
    def paper_shadow_rejections(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(
            copy.deepcopy(x) for x in self._paper_shadow_rejections
        )

    # ------------------------------------------------------------------
    # Manifest preparation / freezing
    # ------------------------------------------------------------------

    def prepare_manifest(self) -> BlindRunManifest:
        """Build and freeze the :class:`BlindRunManifest`.

        Each artefact bundle is hashed deterministically; the result
        is what downstream reviewers will diff against subsequent
        runs to detect drift.
        """
        if self._phase not in {
            _RunnerPhase.INITIALISED,
            _RunnerPhase.PREPARED,
        }:
            raise RuntimeError(
                f"prepare_manifest must be called before the blind "
                f"window starts; current phase={self._phase}"
            )
        cfg = self._config
        ai_state = (
            "OFFLINE_POST_WINDOW_ONLY"
            if cfg.ai_post_window_summary_enabled
            else "OFFLINE_ASOF_ONLY"
        )
        telegram_state = (
            "SANDBOX_FILE_ONLY"
            if cfg.telegram_sandbox_enabled
            else "DISABLED"
        )
        manifest = BlindRunManifest(
            run_id=cfg.run_id or "bwf_unknown",
            window=cfg.window,
            code_commit=cfg.code_commit,
            config_hash=compute_artefact_hash(cfg.config_artefact),
            rule_hash=compute_artefact_hash(cfg.rule_artefact),
            feature_schema_hash=compute_artefact_hash(
                cfg.feature_schema_artefact
            ),
            data_manifest_hash=(
                cfg.data_manifest_hash
                if cfg.data_manifest_hash is not None
                else compute_artefact_hash(cfg.data_manifest_artefact)
            ),
            universe_manifest_hash=(
                cfg.universe_manifest_hash
                if cfg.universe_manifest_hash is not None
                else compute_artefact_hash(
                    cfg.universe_manifest_artefact
                )
            ),
            simulation_clock_start=cfg.window.blind_start,
            simulation_clock_end=cfg.window.blind_end,
            base_clock_step=cfg.base_clock_step,
            allowed_timeframes=cfg.allowed_timeframes,
            fee_model_hash=compute_artefact_hash(cfg.fee_model_artefact),
            slippage_model_hash=compute_artefact_hash(
                cfg.slippage_model_artefact
            ),
            latency_model_hash=compute_artefact_hash(
                cfg.latency_model_artefact
            ),
            outage_model_hash=compute_artefact_hash(
                cfg.outage_model_artefact
            ),
            fill_model_hash=compute_artefact_hash(
                cfg.fill_model_artefact
            ),
            ai_enabled_state=ai_state,
            ai_post_window_summary_enabled=bool(
                cfg.ai_post_window_summary_enabled
            ),
            telegram_sandbox_state=telegram_state,
            intrabar_ambiguity_policy=cfg.intrabar_ambiguity_policy,
        )
        self._manifest = manifest
        self._phase = _RunnerPhase.PREPARED
        return manifest

    def freeze_artifacts(self) -> BlindRunManifest:
        """Idempotent freeze step.

        Calling :meth:`prepare_manifest` already produces the frozen
        manifest. :meth:`freeze_artifacts` re-asserts that the
        manifest is present and that no caller has tampered with it.
        """
        if self._manifest is None:
            self.prepare_manifest()
        assert self._manifest is not None
        # Frozen-manifest tamper guard: re-serialise + reconstruct
        # to verify dictability.
        serialised = self._manifest.to_dict()
        assert_no_forbidden_fields(serialised)
        self._phase = _RunnerPhase.FROZEN
        # Sandbox Telegram entry: run start.
        self._emit_telegram_status(
            severity=TelegramSandboxSeverity.INFO,
            title="Blind walk-forward run prepared",
            body_lines=(
                f"run_id={self._manifest.run_id}",
                f"window_id={self._manifest.window.window_id}",
                f"blind_start={self._manifest.window.blind_start.isoformat()}",
                f"blind_end={self._manifest.window.blind_end.isoformat()}",
                f"base_clock_step={self._manifest.base_clock_step}",
                "phase=Phase 11C.1D-D-G / PR100",
                "live_trading=false",
                "exchange_live_orders=false",
                "binance_private_api_enabled=false",
                "trade_authority=false",
                "auto_tuning_inside_blind_window=false",
                "phase_12_forbidden=true",
            ),
        )
        return self._manifest

    # ------------------------------------------------------------------
    # Step / loop
    # ------------------------------------------------------------------

    def step_once(self) -> Optional[ReplayFeedBatch]:
        """Advance one base-clock step. Returns ``None`` once the
        replay is exhausted at or beyond ``window.blind_end``.
        """
        if self._phase not in {
            _RunnerPhase.FROZEN,
            _RunnerPhase.BLIND_RUNNING,
        }:
            raise RuntimeError(
                f"step_once requires the manifest to be frozen and "
                f"the run not yet scored; current phase={self._phase}"
            )
        if self._phase == _RunnerPhase.FROZEN:
            self._phase = _RunnerPhase.BLIND_RUNNING
        if self._replay_provider.replay_complete:
            return None
        if self._clock.now() >= self._config.window.blind_end:
            return None

        try:
            batch = self._replay_provider.next_batch()
        except StopIteration:
            return None
        except Exception as exc:  # pragma: no cover - defensive
            self._record_failure(
                kind="provider_error",
                detail=str(exc),
                simulated_time=self._clock.now(),
            )
            self._safety_boundary_failed = True
            raise

        # Forward-only invariant.
        new_st = self._clock.now()
        if new_st < self._last_simulated_time:
            self._record_invalidation(
                BlindRunInvalidationReason.FUTURE_RECORD_ACCESS,
                detail=(
                    "simulation_clock advanced backwards: "
                    f"{self._last_simulated_time.isoformat()} -> "
                    f"{new_st.isoformat()}"
                ),
            )
        self._last_simulated_time = new_st

        # Forward provider violations into the runner ledger and the
        # invalidation list (Constitution: any future-record access
        # invalidates the run).
        if batch.violations:
            for v in batch.violations:
                self._violations.append(v)
                self._record_failure(
                    kind="no_lookahead_violation",
                    detail=(
                        f"violation_type={getattr(v, 'reason', '')} "
                        f"severity={getattr(v, 'severity', '')}"
                    ),
                    simulated_time=new_st,
                )
            self._record_invalidation(
                BlindRunInvalidationReason.FUTURE_RECORD_ACCESS,
                detail=(
                    f"{len(batch.violations)} violation(s) routed "
                    "from ReplayFeedProvider in step "
                    f"{self._steps_run}"
                ),
            )

        # Sample diagnostic into the discovery-quality ledger BEFORE
        # any decision callback runs so we capture the as-of state.
        self._record_discovery_quality(batch=batch, simulated_time=new_st)

        # 1) Process previously-submitted orders against the new
        #    batch's closed bars FIRST. Orders submitted on step T
        #    can only fill against bars at step T+1 or later, never
        #    against the same bars that produced the decision (this
        #    is the forward-only invariant for the order path).
        try:
            new_fills = tuple(
                self._mock_exchange.process_batch(batch)
            )
        except Exception as exc:
            self._record_failure(
                kind="mock_exchange_process_error",
                detail=str(exc),
                simulated_time=new_st,
            )
            raise

        # 2) Apply replay batch to capital flow (mark-to-market with
        #    closed candles only).
        try:
            self._capital_flow.apply_replay_batch(batch)
        except Exception as exc:
            self._record_failure(
                kind="capital_flow_error",
                detail=str(exc),
                simulated_time=new_st,
            )
            raise

        # 3) Forward fills into capital flow + telegram sandbox.
        for fill in new_fills:
            # Capture pre-fill open-position / equity so the enriched
            # paper-only simulated trade record can stamp side / entry
            # price / equity transitions (PR106 brief §6). All reads
            # are paper-only in-memory state; no real account is read.
            symbol = getattr(fill, "symbol", None)
            prev_position = (
                self._open_position_for(symbol)
                if isinstance(symbol, str) and symbol
                else None
            )
            equity_before = self._capital_flow.current_marked_equity()
            try:
                closed_entry = self._capital_flow.consume_fill(fill)
            except (
                MaxActivePositionsReachedError,
                CapitalFrozenError,
            ) as exc:
                # PR107 hotfix: a fill that would OPEN a new simulated
                # position can be refused by the (PR98) Simulated
                # Capital Flow when the position book is already at its
                # max_active_positions cap (or the capital is frozen).
                # This is a *predictable* simulated risk/capital
                # rejection, NOT a program error: convert it into a
                # SIM_REJECT paper-shadow rejection event (written to
                # the transcript + report rejection summary) and
                # CONTINUE the blind run instead of aborting it. The
                # already-opened / closed simulated trades are
                # untouched.
                self._handle_capital_flow_reject(
                    fill=fill,
                    exc=exc,
                    simulated_time=new_st,
                )
                continue
            except Exception as exc:
                # Any OTHER exception is unexpected: never swallow it.
                # Record it in the failure ledger and re-raise so the
                # run fails loudly (we only absorb explicit, predictable
                # simulated risk/capital rejections above).
                self._record_failure(
                    kind="capital_flow_consume_error",
                    detail=str(exc),
                    simulated_time=new_st,
                )
                raise
            equity_after = self._capital_flow.current_marked_equity()
            self._emit_telegram_fill(fill=fill, simulated_time=new_st)
            if closed_entry is not None:
                # The fill fully closed a simulated position -> SIM_EXIT.
                self._handle_simulated_exit(
                    fill=fill,
                    closed_entry=closed_entry,
                    prev_position=prev_position,
                    equity_after=equity_after,
                    simulated_time=new_st,
                )
            elif isinstance(symbol, str) and symbol:
                now_position = self._open_position_for(symbol)
                if prev_position is None and now_position is not None:
                    # The fill opened a NEW simulated position ->
                    # SIM_ENTRY.
                    self._handle_simulated_entry(
                        fill=fill,
                        position=now_position,
                        equity_before=equity_before,
                        equity_after=equity_after,
                        simulated_time=new_st,
                    )

        # 3b) PR108 capital-safety enforcement. After marks + fills are
        #     applied, ask the Simulated Capital Flow whether the
        #     simulated equity has hit the hard floor or breached the
        #     configured drawdown kill switch. If so it force-exits every
        #     open simulated position (through the simulated flow, NEVER
        #     a real exchange) and latches the kill switch; we surface
        #     SIM_FORCED_EXIT + SIM_CAPITAL_EXHAUSTED / SIM_ACCOUNT_HALTED
        #     transcript entries. Once halted, the decision callback below
        #     and the pre-submit gate refuse every new entry for the rest
        #     of the blind window.
        try:
            safety_event = self._capital_flow.enforce_capital_safety(
                new_st
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._record_failure(
                kind="capital_safety_error",
                detail=str(exc),
                simulated_time=new_st,
            )
            raise
        if safety_event is not None:
            self._handle_capital_safety_event(
                event=safety_event, simulated_time=new_st
            )

        # 4) Decision callback (paper-shadow bridge or strategy-less).
        orders: Sequence[OrderRequest] = ()
        if self._decision_callback is not None:
            try:
                returned = self._decision_callback(new_st, batch, self)
            except Exception as exc:
                self._record_failure(
                    kind="decision_callback_error",
                    detail=str(exc),
                    simulated_time=new_st,
                )
                raise
            if returned is None:
                returned = ()
            orders = tuple(returned)
            for req in orders:
                if not isinstance(req, OrderRequest):
                    raise TypeError(
                        f"decision_callback must return OrderRequest "
                        f"objects; got {type(req)!r}"
                    )
            # PR106: drain any deterministic paper-shadow rejections the
            # bridge recorded for this step and surface them as
            # SIM_REJECT transcript entries. A rejection is NEVER a
            # silent skip: it is logged so the operator can see a valid
            # signal that was suppressed (e.g. concurrency cap, or a
            # record that failed the as-of / closed-candle gate).
            if self._paper_shadow_bridge is not None:
                for rej in self._paper_shadow_bridge.drain_rejections():
                    self._handle_simulated_reject(
                        rejection=rej, simulated_time=new_st
                    )

        # 5) Submit orders WITHOUT a replay_batch; they will fill
        #    against the next batch's closed bars (strict forward-only).
        #
        # PR107 hotfix: before forwarding an order that would OPEN a new
        # simulated position, check the (PR98) Simulated Capital Flow
        # concurrency cap. If accepting the order would push the
        # projected open-position count to or beyond
        # ``max_active_positions`` we DROP the order here and record a
        # deterministic SIM_REJECT (reason=max_active_positions_reached)
        # rather than letting the later fill abort the run. The
        # projected count = currently-open positions + opens already
        # accepted earlier in this same step. This never raises the
        # cap, never enables live trading, and is paper-only.
        max_active = int(self._capital_flow.config.max_active_positions)
        open_now = len(self._capital_flow.get_positions())
        accepted_opens_this_step = 0
        for req in orders:
            if self._order_would_open_new_position(req):
                # PR108 pre-entry capital/risk gate: refuse a new
                # simulated OPEN when the kill switch is latched, the
                # capital is exhausted, the configured drawdown limit is
                # reached, the concurrency cap is hit, or there is not
                # enough free equity to cover the position. Each refusal
                # is a deterministic SIM_REJECT (paper-only); it NEVER
                # raises a cap/floor/limit and NEVER aborts the run.
                projected = open_now + accepted_opens_this_step
                if projected >= max_active:
                    self._handle_capacity_presubmit_reject(
                        symbol=getattr(req, "symbol", None),
                        active_positions=projected,
                        max_active_positions=max_active,
                        simulated_time=new_st,
                    )
                    continue
                gate_ok, gate_reason = self._capital_flow.can_open_position(
                    symbol=getattr(req, "symbol", None),
                    requested_qty=getattr(req, "requested_qty", None),
                )
                if not gate_ok:
                    self._handle_capital_gate_reject(
                        symbol=getattr(req, "symbol", None),
                        reason=gate_reason
                        or CapitalRejectReason.RISK_HALT_ACTIVE,
                        simulated_time=new_st,
                    )
                    continue
                accepted_opens_this_step += 1
            try:
                self._mock_exchange.submit_order(
                    req, simulated_time=new_st
                )
            except Exception as exc:
                self._record_failure(
                    kind="mock_exchange_submit_error",
                    detail=str(exc),
                    simulated_time=new_st,
                )
                raise

        self._batches_consumed += 1
        self._steps_run += 1
        return batch

    def run_blind_window(self) -> Tuple[ReplayFeedBatch, ...]:
        """Drive :meth:`step_once` until the blind window closes."""
        if self._manifest is None:
            self.freeze_artifacts()
        if self._phase not in {
            _RunnerPhase.FROZEN,
            _RunnerPhase.BLIND_RUNNING,
        }:
            raise RuntimeError(
                f"run_blind_window requires phase FROZEN or "
                f"BLIND_RUNNING; got {self._phase}"
            )
        batches: List[ReplayFeedBatch] = []
        _LOGGER.info(
            "blind walk-forward window starting: run_id=%s "
            "blind_start=%s blind_end=%s base_clock_step=%s",
            self._manifest.run_id,
            self._config.window.blind_start.isoformat(),
            self._config.window.blind_end.isoformat(),
            self._config.base_clock_step,
        )
        while True:
            b = self.step_once()
            if b is None:
                break
            batches.append(b)
            # PR104: progress heartbeat so a long real replay (e.g. a
            # 1-day 1m window = 1440 steps) shows liveness instead of
            # appearing hung. Goes through logging, never stdout.
            if self._steps_run % self._heartbeat_every == 0:
                _LOGGER.info(
                    "blind walk-forward heartbeat: run_id=%s "
                    "steps_run=%d batches_consumed=%d "
                    "simulated_time=%s violations=%d",
                    self._manifest.run_id,
                    self._steps_run,
                    self._batches_consumed,
                    self._last_simulated_time.isoformat(),
                    len(self._violations),
                )
        # Final mark-to-market at blind_end so the equity time-series
        # contains a closing point even if the last batch was earlier.
        try:
            self._capital_flow.apply_mark_prices(
                {}, simulated_time=self._config.window.blind_end
            )
        except Exception:  # pragma: no cover - defensive
            pass
        self._phase = _RunnerPhase.BLIND_COMPLETE
        # PR106: emit a paper-shadow WINDOW_SUMMARY transcript entry so
        # a file-based monitor sees a closing summary of the simulated
        # trading activity for this blind window.
        self._emit_window_summary()
        self._emit_telegram_status(
            severity=TelegramSandboxSeverity.INFO,
            title="Blind walk-forward window complete",
            body_lines=(
                f"run_id={self._manifest.run_id}",
                f"steps_run={self._steps_run}",
                f"batches_consumed={self._batches_consumed}",
                f"violations={len(self._violations)}",
                f"failure_ledger_entries={len(self._failure_entries)}",
                "live_trading=false",
                "exchange_live_orders=false",
                "trade_authority=false",
                "phase_12_forbidden=true",
            ),
            message_type=(
                TelegramSandboxMessageType.MONTHLY_BLIND_TEST_SUMMARY
            ),
        )
        return tuple(batches)

    # ------------------------------------------------------------------
    # Scoring (post blind window only)
    # ------------------------------------------------------------------

    def score_after_window_close(self) -> BlindRunScore:
        """Compute the :class:`BlindRunScore`.

        Allowed only when the blind window has finished.
        """
        if self._phase not in {
            _RunnerPhase.BLIND_COMPLETE,
            _RunnerPhase.SCORED,
            _RunnerPhase.EMITTED,
        }:
            raise RuntimeError(
                "score_after_window_close requires the blind window "
                "to be complete; current phase=" + self._phase
            )
        now = datetime.now(timezone.utc)
        if now < self._config.window.blind_end:
            # Defensive — we should never get here because the loop
            # itself enforces forward-only progress, but this guard
            # makes the intent explicit at the public boundary.
            raise RuntimeError(
                "score_after_window_close called before window.blind_end"
            )
        ledger_summary = self._capital_flow.get_ledger().summary().to_dict()
        # Failure ledger MUST exist on a non-empty run (brief §9).
        if (
            self._steps_run > 0
            and not self._failure_entries
            and not self._violations
            and not self._invalidations
        ):
            # Empty failure ledger on a non-zero run is allowed: it
            # means the run was clean. We only invalidate on the
            # MISSING_FAILURE_LEDGER taxonomy when the failure-ledger
            # writer was never invoked (see generate_failure_ledger).
            pass
        invalidation_reasons = tuple(
            x["reason"] for x in self._invalidations
        )
        partial_reasons: List[str] = []
        if (
            self._batches_consumed == 0
            and self._steps_run > 0
        ):
            partial_reasons.append("zero_batches_consumed_after_steps")
        score = score_blind_run(
            run_id=self._manifest.run_id if self._manifest else "unknown",
            window_id=(
                self._manifest.window.window_id
                if self._manifest
                else "unknown"
            ),
            scored_at=now,
            sample_count=self._batches_consumed,
            ledger_summary=ledger_summary,
            no_lookahead_violation_count=len(self._violations),
            failure_ledger_entry_count=len(self._failure_entries),
            invalidation_reasons=invalidation_reasons,
            safety_boundary_failed=self._safety_boundary_failed,
            partial_evidence_reasons=tuple(partial_reasons),
        )
        self._score = score
        self._phase = _RunnerPhase.SCORED
        self._emit_telegram_status(
            severity=TelegramSandboxSeverity.INFO,
            title=f"Blind walk-forward scored: {score.status}",
            body_lines=(
                f"run_id={score.run_id}",
                f"window_id={score.window_id}",
                f"sample_count={score.sample_count}",
                f"closed_trade_count={score.closed_trade_count}",
                f"violations={score.no_lookahead_violation_count}",
                f"failures={score.failure_ledger_entry_count}",
                f"invalidations={list(score.invalidation_reasons)}",
                "live_trading=false",
                "trade_authority=false",
                "phase_12_forbidden=true",
            ),
            message_type=(
                TelegramSandboxMessageType.FAILURE_LEDGER_SUMMARY
            ),
        )
        return score

    # ------------------------------------------------------------------
    # Failure ledger / discovery quality ledger
    # ------------------------------------------------------------------

    def generate_failure_ledger(self) -> List[Dict[str, Any]]:
        """Aggregate the run's failure ledger entries.

        Returns a list of plain dicts (deep-copied) so callers cannot
        mutate the internal state. The list is empty for clean runs.
        """
        return [copy.deepcopy(x) for x in self._failure_entries]

    def generate_discovery_quality_ledger(self) -> List[Dict[str, Any]]:
        """Aggregate per-step structural discovery-quality samples.

        v0: structural counters only (kline counts, universe size,
        feature-cache lookups). NOT a tail label, NOT a strategy
        validation sample, NOT an AI bundle. The runner emits ONE
        entry per blind-window step.
        """
        return [copy.deepcopy(x) for x in self._discovery_quality_steps]

    # ------------------------------------------------------------------
    # AI as-of / post-window isolation (PR100 brief §5)
    # ------------------------------------------------------------------

    def assert_blind_window_ai_evidence_bundle(
        self,
        *,
        bundle: Mapping[str, Any],
        simulated_time: datetime,
    ) -> None:
        """Reject a candidate AI Evidence Bundle that touches the
        future or any outcome label.

        This guard implements PR100 §5: blind-window AI is OFFLINE,
        as-of, and may NEVER read tail_label / MFE / MAE /
        post-discovery outcome / failure ledger / replay-reflection
        future content. Calling this method does NOT enable AI: it
        only gives downstream callers a single closed contract to
        check before they hand a bundle to a (still-FORBIDDEN)
        AI hot path.
        """
        if not isinstance(bundle, Mapping):
            raise TypeError(
                f"bundle must be a Mapping; got {type(bundle)!r}"
            )
        st = ensure_utc_aware(simulated_time, "simulated_time")
        forbidden_outcome_keys: FrozenSet[str] = frozenset(
            {
                "tail_label",
                "training_label",
                "outcome",
                "post_discovery_outcome",
                "mfe",
                "mae",
                "max_favorable_excursion",
                "max_adverse_excursion",
                "future_replay",
                "future_reflection",
                "future_outcome",
            }
        )
        leaked = sorted(
            k
            for k in bundle.keys()
            if isinstance(k, str) and k in forbidden_outcome_keys
        )
        if leaked:
            self._record_invalidation(
                BlindRunInvalidationReason.AI_OUTPUT_USED_AS_TRUTH_OR_LABEL,
                detail=(
                    "blind-window AI evidence bundle leaked outcome "
                    f"keys: {leaked}"
                ),
            )
            raise ValueError(
                "blind-window AI evidence bundle must not contain "
                f"outcome / tail_label / future_* keys: {leaked}"
            )
        evidence_refs = bundle.get("evidence_refs", ())
        if not isinstance(evidence_refs, (list, tuple)):
            raise TypeError(
                "evidence_refs must be a list/tuple of mappings"
            )
        for ref in evidence_refs:
            if not isinstance(ref, Mapping):
                raise TypeError(
                    "evidence_refs entries must be Mapping objects"
                )
            av = ref.get("available_at")
            if av is None:
                raise ValueError(
                    "evidence_refs entries must carry "
                    "'available_at'"
                )
            try:
                av_ts = ensure_utc_aware(
                    av if isinstance(av, datetime) else datetime.fromisoformat(str(av)),
                    "evidence_ref.available_at",
                )
            except Exception as exc:  # pragma: no cover
                raise ValueError(
                    f"evidence_refs.available_at unparseable: {exc!r}"
                )
            if av_ts > st:
                self._record_invalidation(
                    (
                        BlindRunInvalidationReason
                        .AI_OUTPUT_USED_AS_TRUTH_OR_LABEL
                    ),
                    detail=(
                        "blind-window AI evidence_ref available_at "
                        f"{av_ts.isoformat()} is in the future of "
                        f"simulated_time {st.isoformat()}"
                    ),
                )
                raise ValueError(
                    "blind-window AI evidence_ref available_at "
                    f"{av_ts.isoformat()} > simulated_time "
                    f"{st.isoformat()}"
                )

    def build_post_window_ai_summary(
        self,
        *,
        commentary: str = "",
    ) -> Dict[str, Any]:
        """Return an OFFLINE post-window AI summary template.

        Hard rule (PR100 brief §5): post-window AI summaries can
        ONLY be produced after ``blind_end``. The output is
        commentary, NEVER truth, NEVER training label, NEVER tail
        label, NEVER strategy validation sample, NEVER runtime config.
        """
        if self._phase not in {
            _RunnerPhase.BLIND_COMPLETE,
            _RunnerPhase.SCORED,
            _RunnerPhase.EMITTED,
        }:
            raise RuntimeError(
                "post-window AI summary unavailable inside the blind "
                "window"
            )
        if not self._config.ai_post_window_summary_enabled:
            raise RuntimeError(
                "ai_post_window_summary_enabled is False"
            )
        if not isinstance(commentary, str):
            raise TypeError("commentary must be a string")
        out: Dict[str, Any] = {
            "run_id": (
                self._manifest.run_id if self._manifest else "unknown"
            ),
            "window_id": (
                self._manifest.window.window_id
                if self._manifest
                else "unknown"
            ),
            "ai_role": "OFFLINE_POST_WINDOW_COMMENTARY_ONLY",
            "ai_authority": "NONE",
            "is_truth_layer_fact": False,
            "is_training_label": False,
            "is_tail_label": False,
            "is_strategy_validation_sample": False,
            "is_runtime_patch": False,
            "is_ai_in_decision_chain": False,
            "commentary": commentary,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        self._post_window_ai_summary = out
        return copy.deepcopy(out)

    # ------------------------------------------------------------------
    # Output emission
    # ------------------------------------------------------------------

    def generate_outputs(
        self,
        *,
        report_dir: Optional[str] = None,
    ) -> Dict[str, str]:
        """Write all required artefacts to disk and return a map of
        artefact-name -> absolute path.

        Required artefacts (PR100 brief §7):

          * blind_run_manifest.json
          * trade_ledger.json
          * equity_timeseries.json
          * discovery_quality_ledger.json
          * failure_ledger.json
          * telegram_sandbox_transcript.md
          * blind_walk_forward_report.json
          * blind_walk_forward_report.md
          * no_lookahead_violations.json
        """
        if self._phase not in {
            _RunnerPhase.SCORED,
            _RunnerPhase.EMITTED,
        }:
            raise RuntimeError(
                "generate_outputs requires the run to be scored "
                "(score_after_window_close must be called first)"
            )
        if self._manifest is None or self._score is None:
            raise RuntimeError(
                "generate_outputs requires both manifest and score"
            )
        target_root = report_dir or os.path.join(
            self._config.report_root, self._manifest.run_id
        )
        os.makedirs(target_root, exist_ok=True)

        manifest_dict = self._manifest.to_dict()
        score_dict = self._score.to_dict()
        ledger = self._capital_flow.get_ledger()
        ledger_dict = ledger.to_dict()
        equity_dict = {
            "run_id": self._manifest.run_id,
            "window_id": self._manifest.window.window_id,
            "points": [
                p.to_dict() for p in self.equity_timeseries
            ],
            "is_blind_walk_forward_payload": True,
        }
        equity_dict.update(_safety_payload())
        discovery_dict = {
            "run_id": self._manifest.run_id,
            "window_id": self._manifest.window.window_id,
            "entries": self.generate_discovery_quality_ledger(),
            "is_blind_walk_forward_payload": True,
        }
        discovery_dict.update(_safety_payload())
        failure_dict = {
            "run_id": self._manifest.run_id,
            "window_id": self._manifest.window.window_id,
            "entries": self.generate_failure_ledger(),
            "is_blind_walk_forward_payload": True,
        }
        failure_dict.update(_safety_payload())
        violations_dict = {
            "run_id": self._manifest.run_id,
            "window_id": self._manifest.window.window_id,
            "violations": [
                self._violation_to_dict(v) for v in self._violations
            ],
            "invalidations": [copy.deepcopy(x) for x in self._invalidations],
            "is_blind_walk_forward_payload": True,
        }
        violations_dict.update(_safety_payload())

        report_dict = self._build_report_dict()

        # Validate every payload one more time before serialising.
        for d in (
            manifest_dict,
            score_dict,
            equity_dict,
            discovery_dict,
            failure_dict,
            violations_dict,
            report_dict,
        ):
            assert_no_forbidden_fields(d)

        paths: Dict[str, str] = {}

        def _write_json(name: str, payload: Any) -> str:
            p = os.path.join(target_root, name)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(
                    payload,
                    fh,
                    sort_keys=True,
                    indent=2,
                    default=_json_default,
                )
            paths[name] = p
            return p

        _write_json("blind_run_manifest.json", manifest_dict)
        # Trade ledger uses its own to_dict already; we add a wrapper
        # that also re-pins safety + run identity.
        ledger_payload = {
            "run_id": self._manifest.run_id,
            "window_id": self._manifest.window.window_id,
            "ledger": ledger_dict,
            "capital_safety": self._capital_flow.capital_safety_snapshot(),
            "capital_reject_count": int(self._capital_reject_count),
            "is_blind_walk_forward_payload": True,
        }
        ledger_payload.update(_safety_payload())
        assert_no_forbidden_fields(ledger_payload)
        _write_json("trade_ledger.json", ledger_payload)
        _write_json("equity_timeseries.json", equity_dict)
        _write_json("discovery_quality_ledger.json", discovery_dict)
        _write_json("failure_ledger.json", failure_dict)
        _write_json("no_lookahead_violations.json", violations_dict)
        _write_json("blind_walk_forward_report.json", report_dict)

        # PR106: paper-shadow simulated trades + rejections sidecar so a
        # reviewer can see every simulated entry / exit / reject with
        # the enriched fields (side / leverage / entry+exit price / pnl
        # / pnl_pct / equity_before / equity_after / signal_reason /
        # as_of_refs). The canonical PR98 trade ledger remains the
        # source of truth in trade_ledger.json; this is an enriched,
        # paper-only view of the same closed trades.
        paper_shadow_dict = {
            "run_id": self._manifest.run_id,
            "window_id": self._manifest.window.window_id,
            "paper_shadow_strategy_enabled": self._paper_shadow_enabled,
            "strategy_bridge_name": self._paper_shadow_bridge_name,
            "no_paper_shadow_signals": bool(
                self._paper_shadow_enabled
                and self._paper_shadow_entry_count == 0
            ),
            "entry_signal_count": self._paper_shadow_entry_count,
            "exit_signal_count": self._paper_shadow_exit_count,
            "reject_count": len(self._paper_shadow_rejections),
            "capital_reject_count": int(self._capital_reject_count),
            "forced_exit_count": int(
                self._capital_flow.forced_exit_count
            ),
            "capital_safety": self._capital_flow.capital_safety_snapshot(),
            "trades": [
                copy.deepcopy(t) for t in self._paper_shadow_trades
            ],
            "rejections": [
                copy.deepcopy(r) for r in self._paper_shadow_rejections
            ],
            "is_blind_walk_forward_payload": True,
        }
        if self._paper_shadow_bridge is not None:
            paper_shadow_dict["bridge"] = (
                self._paper_shadow_bridge.to_dict()
            )
        paper_shadow_dict.update(_safety_payload())
        assert_no_forbidden_fields(paper_shadow_dict)
        _write_json("paper_shadow_trades.json", paper_shadow_dict)

        # Telegram sandbox transcript (markdown).
        transcript_path = os.path.join(
            target_root, "telegram_sandbox_transcript.md"
        )
        self._telegram.write_markdown_transcript(transcript_path)
        paths["telegram_sandbox_transcript.md"] = transcript_path

        # Markdown report.
        md_path = os.path.join(
            target_root, "blind_walk_forward_report.md"
        )
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(self._build_report_markdown(report_dict))
        paths["blind_walk_forward_report.md"] = md_path

        self._phase = _RunnerPhase.EMITTED
        return paths

    def run(
        self,
        *,
        report_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """End-to-end orchestration: prepare -> freeze -> blind ->
        score -> emit. Returns a dict of {manifest, score, paths}.
        """
        self.prepare_manifest()
        self.freeze_artifacts()
        # PR104: create the per-run output directory at run start (not
        # only after scoring) so a long real replay surfaces a visible
        # artefact directory immediately instead of looking hung.
        out_dir = self._resolve_output_dir(report_dir)
        os.makedirs(out_dir, exist_ok=True)
        self._output_dir = out_dir
        _LOGGER.info(
            "blind walk-forward run output directory ready: %s", out_dir
        )
        self.run_blind_window()
        self.score_after_window_close()
        paths = self.generate_outputs(report_dir=out_dir)
        return {
            "manifest": self._manifest.to_dict() if self._manifest else None,
            "score": self._score.to_dict() if self._score else None,
            "paths": paths,
        }

    def _resolve_output_dir(
        self, report_dir: Optional[str] = None
    ) -> str:
        """Resolve the per-run output directory path (PR104).

        Mirrors the resolution used by :meth:`generate_outputs` so the
        directory created at run start is the same one the artefacts are
        written to.
        """
        if report_dir:
            return report_dir
        run_id = (
            self._manifest.run_id
            if self._manifest is not None
            else (self._config.run_id or "bwf_unknown")
        )
        return os.path.join(self._config.report_root, run_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_invalidation(self, reason: str, *, detail: str) -> None:
        if reason not in BlindRunInvalidationReason.ALLOWED:
            raise ValueError(
                f"invalidation reason {reason!r} not in closed taxonomy"
            )
        if not isinstance(detail, str):
            raise TypeError("invalidation detail must be a string")
        self._invalidations.append(
            {
                "reason": reason,
                "detail": detail,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _record_failure(
        self,
        *,
        kind: str,
        detail: str,
        simulated_time: datetime,
    ) -> None:
        ts = ensure_utc_aware(simulated_time, "simulated_time")
        self._failure_entries.append(
            {
                "kind": kind,
                "detail": detail,
                "simulated_time": ts.isoformat(),
                "step": self._steps_run,
                "is_real_exchange_order": False,
                "is_real_telegram_outbound": False,
                "is_runtime_patch": False,
            }
        )

    def _record_discovery_quality(
        self,
        *,
        batch: ReplayFeedBatch,
        simulated_time: datetime,
    ) -> None:
        kline_by_tf: Dict[str, int] = {}
        for k in batch.klines_1m:
            kline_by_tf["1m"] = kline_by_tf.get("1m", 0) + 1
        for k in batch.klines_5m:
            kline_by_tf["5m"] = kline_by_tf.get("5m", 0) + 1
        kline_total = sum(kline_by_tf.values())
        entry: Dict[str, Any] = {
            "step": self._steps_run,
            "simulated_time": ensure_utc_aware(
                simulated_time, "simulated_time"
            ).isoformat(),
            "asof_universe_size": len(batch.asof_universe),
            "kline_total": kline_total,
            "kline_by_timeframe": dict(sorted(kline_by_tf.items())),
            "asof_record_total": len(batch.records),
            "violations_in_batch": len(batch.violations),
            "feature_cache_keys": self._feature_cache.keys_count,
            "feature_cache_future_access_count": (
                self._feature_cache.future_access_count
            ),
            "is_real_exchange_order": False,
            "is_real_telegram_outbound": False,
            "is_runtime_patch": False,
        }
        self._discovery_quality_steps.append(entry)

    def _violation_to_dict(
        self, violation: NoLookaheadViolation
    ) -> Dict[str, Any]:
        if hasattr(violation, "to_dict"):
            try:
                d = violation.to_dict()
                if isinstance(d, Mapping):
                    return dict(d)
            except Exception:  # pragma: no cover - defensive
                pass
        return {
            "violation_type": getattr(violation, "violation_type", ""),
            "reason": getattr(violation, "reason", ""),
            "simulated_time": (
                getattr(violation, "simulated_time", "")
                if not isinstance(
                    getattr(violation, "simulated_time", None), datetime
                )
                else getattr(violation, "simulated_time").isoformat()
            ),
        }

    def _fill_against_batch(
        self, *, batch: ReplayFeedBatch
    ) -> Tuple[MockFill, ...]:
        """Deprecated v0 helper retained for documentation purposes.

        The runner now calls
        :meth:`MockExchange.process_batch` directly so that orders
        submitted in step T fill only against bars at step T+1 or
        later (the strict forward-only invariant for the order path).
        """
        try:
            return tuple(self._mock_exchange.process_batch(batch))
        except Exception:  # pragma: no cover - defensive
            return ()

    def _emit_telegram_status(
        self,
        *,
        severity: str,
        title: str,
        body_lines: Iterable[str],
        message_type: str = TelegramSandboxMessageType.EQUITY_SUMMARY,
    ) -> None:
        if not self._config.telegram_sandbox_enabled:
            return
        body = "\n".join(body_lines)
        if not body:
            body = "(no body)"
        run_id = (
            self._manifest.run_id if self._manifest else "unknown"
        )
        self._telegram_message_counter += 1
        message_id = (
            f"bwf_{run_id}_status_"
            f"{self._telegram_message_counter:06d}"
        )
        try:
            msg = TelegramSandboxMessage(
                message_id=message_id,
                timestamp_simulated=self._clock.now(),
                message_type=message_type,
                severity=severity,
                title=title,
                body=body,
            )
            self._telegram.append_message(msg)
        except Exception:  # pragma: no cover - telegram is sandbox
            pass

    def _emit_telegram_fill(
        self,
        *,
        fill: MockFill,
        simulated_time: datetime,
    ) -> None:
        if not self._config.telegram_sandbox_enabled:
            return
        body_lines = [
            f"symbol={getattr(fill, 'symbol', '')}",
            f"side_value={getattr(fill, 'side', '')}",
            f"quantity={getattr(fill, 'filled_qty', 0.0)}",
            f"fill_price={getattr(fill, 'fill_price', 0.0)}",
            "simulated_only=true",
            "no_live_order=true",
            "trade_authority=false",
            "live_trading=false",
            "exchange_live_orders=false",
            "binance_private_api_enabled=false",
        ]
        body = "\n".join(body_lines)
        run_id = (
            self._manifest.run_id if self._manifest else "unknown"
        )
        self._telegram_message_counter += 1
        message_id = (
            f"bwf_{run_id}_fill_"
            f"{self._telegram_message_counter:06d}"
        )
        symbol = getattr(fill, "symbol", None)
        if not isinstance(symbol, str) or not symbol:
            symbol = None
        try:
            msg = TelegramSandboxMessage(
                message_id=message_id,
                timestamp_simulated=ensure_utc_aware(
                    simulated_time, "simulated_time"
                ),
                message_type=(
                    TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT
                ),
                severity=TelegramSandboxSeverity.INFO,
                title="Simulated fill",
                body=body,
                symbol=symbol,
            )
            self._telegram.append_message(msg)
        except Exception:  # pragma: no cover - telegram is sandbox
            pass

    # ------------------------------------------------------------------
    # PR106 - Paper Shadow Strategy Bridge helpers
    # ------------------------------------------------------------------

    def _open_position_for(self, symbol: Optional[str]) -> Optional[Any]:
        """Return the OPEN simulated position for ``symbol`` or None.

        Read-only view of the (PR98) Simulated Capital Flow position
        book. Paper-only: never reads a real account.
        """
        if not isinstance(symbol, str) or not symbol:
            return None
        for p in self._capital_flow.get_positions():
            if getattr(p, "symbol", None) == symbol:
                return p
        return None

    @staticmethod
    def _extract_signal_reason(
        evidence_refs: Iterable[Any],
    ) -> Optional[str]:
        for r in evidence_refs or ():
            if isinstance(r, str) and r.startswith("signal:"):
                return r[len("signal:"):]
        return None

    def _paper_shadow_leverage(self) -> float:
        if self._paper_shadow_bridge is not None:
            try:
                return float(self._paper_shadow_bridge.leverage)
            except Exception:  # pragma: no cover - defensive
                return 1.0
        return 1.0

    def _append_paper_shadow_telegram(
        self,
        *,
        title: str,
        message_type: str,
        body_lines: Sequence[str],
        simulated_time: datetime,
        symbol: Optional[str] = None,
        severity: str = TelegramSandboxSeverity.INFO,
        evidence_refs: Tuple[str, ...] = (),
    ) -> None:
        """Append a paper-shadow transcript message.

        Every message carries the four mandatory simulated markers in
        its body (in addition to the four labels the renderer always
        prepends): ``SIMULATED_ONLY`` / ``NO_LIVE_ORDER`` /
        ``NO_REAL_CAPITAL`` / ``NO_COMMAND_AUTHORITY``.
        """
        if not self._config.telegram_sandbox_enabled:
            return
        header = [
            title,
            "SIMULATED_ONLY",
            "NO_LIVE_ORDER",
            "NO_REAL_CAPITAL",
            "NO_COMMAND_AUTHORITY",
        ]
        body = "\n".join(list(header) + list(body_lines))
        run_id = self._manifest.run_id if self._manifest else "unknown"
        self._telegram_message_counter += 1
        message_id = (
            f"bwf_{run_id}_paper_shadow_"
            f"{self._telegram_message_counter:06d}"
        )
        sym = symbol if isinstance(symbol, str) and symbol else None
        try:
            msg = TelegramSandboxMessage(
                message_id=message_id,
                timestamp_simulated=ensure_utc_aware(
                    simulated_time, "simulated_time"
                ),
                message_type=message_type,
                severity=severity,
                title=title,
                body=body,
                symbol=sym,
                evidence_refs=tuple(evidence_refs),
            )
            self._telegram.append_message(msg)
        except Exception:  # pragma: no cover - telegram is sandbox
            pass

    def _handle_simulated_entry(
        self,
        *,
        fill: MockFill,
        position: Any,
        equity_before: float,
        equity_after: float,
        simulated_time: datetime,
    ) -> None:
        symbol = getattr(fill, "symbol", "")
        side = getattr(position, "side", None) or (
            "LONG"
            if getattr(fill, "side", None) == "BUY"
            else "SHORT"
        )
        entry_price = float(
            getattr(position, "avg_entry_price", None)
            or getattr(fill, "fill_price", 0.0)
        )
        qty = float(
            getattr(position, "qty", None)
            or getattr(fill, "filled_qty", 0.0)
        )
        leverage = self._paper_shadow_leverage()
        signal_reason = self._extract_signal_reason(
            getattr(fill, "evidence_refs", ())
        )
        self._paper_shadow_open_meta[symbol] = {
            "side": side,
            "leverage": leverage,
            "entry_price": entry_price,
            "entry_qty": qty,
            "entry_signal_reason": signal_reason,
            "equity_before": float(equity_before),
        }
        self._paper_shadow_entry_count += 1
        notional = entry_price * qty
        self._append_paper_shadow_telegram(
            title="SIM_ENTRY",
            message_type=(
                TelegramSandboxMessageType.SIMULATED_ENTRY_ALERT
            ),
            simulated_time=simulated_time,
            symbol=symbol if isinstance(symbol, str) else None,
            evidence_refs=tuple(getattr(fill, "evidence_refs", ())),
            body_lines=[
                f"bridge={self._paper_shadow_bridge_name or 'none'}",
                f"symbol={symbol}",
                f"side={side}",
                f"leverage={leverage}",
                f"entry_price={entry_price}",
                f"quantity={qty}",
                f"notional={notional}",
                f"signal_reason={signal_reason}",
                f"equity_after={float(equity_after)}",
            ],
        )

    def _handle_simulated_exit(
        self,
        *,
        fill: MockFill,
        closed_entry: TradeLedgerEntry,
        prev_position: Optional[Any],
        equity_after: float,
        simulated_time: datetime,
    ) -> None:
        symbol = closed_entry.symbol
        side = (
            getattr(prev_position, "side", None)
            if prev_position is not None
            else None
        )
        if side is None:
            # SELL closes a LONG; BUY closes a SHORT.
            side = (
                "LONG"
                if getattr(fill, "side", None) == "SELL"
                else "SHORT"
            )
        entry_price = float(closed_entry.avg_fill_price)
        exit_price = float(getattr(fill, "fill_price", 0.0))
        qty = float(closed_entry.filled_qty)
        notional = entry_price * qty
        net_pnl = float(closed_entry.net_pnl)
        pnl_pct = (net_pnl / notional * 100.0) if notional > 0.0 else 0.0
        meta = self._paper_shadow_open_meta.pop(symbol, {})
        equity_before = float(meta.get("equity_before", 0.0))
        leverage = float(
            meta.get("leverage", self._paper_shadow_leverage())
        )
        entry_signal_reason = meta.get("entry_signal_reason")
        exit_signal_reason = self._extract_signal_reason(
            getattr(fill, "evidence_refs", ())
        )
        record: Dict[str, Any] = {
            "trade_id": closed_entry.trade_id,
            "run_id": (
                self._manifest.run_id if self._manifest else "unknown"
            ),
            "window_id": (
                self._manifest.window.window_id
                if self._manifest
                else "unknown"
            ),
            "symbol": symbol,
            "side": side,
            "leverage_ratio": leverage,
            "entry_time": (
                closed_entry.entry_time.isoformat()
                if closed_entry.entry_time is not None
                else None
            ),
            "exit_time": (
                closed_entry.exit_time.isoformat()
                if closed_entry.exit_time is not None
                else None
            ),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": qty,
            "notional": notional,
            "fees": float(closed_entry.fee),
            "slippage_bps": float(closed_entry.slippage_bps),
            "realized_pnl": net_pnl,
            "pnl_pct": pnl_pct,
            "equity_before": equity_before,
            "equity_after": float(equity_after),
            "exit_reason": closed_entry.exit_reason,
            "entry_signal_reason": entry_signal_reason,
            "exit_signal_reason": exit_signal_reason,
            "signal_reason": entry_signal_reason or exit_signal_reason,
            "outcome": closed_entry.outcome,
            "evidence_refs": list(closed_entry.evidence_refs),
            "as_of_refs": [
                r
                for r in closed_entry.evidence_refs
                if isinstance(r, str) and r.startswith("asof:")
            ],
            "bridge_name": self._paper_shadow_bridge_name,
            # Hard-pinned per-trade safety markers (PR106 brief §6).
            "is_simulated": True,
            "no_live_order": True,
            "phase_12_forbidden": True,
            "trade_authority": False,
            "ai_trade_authority": False,
        }
        assert_no_forbidden_fields(record)
        self._paper_shadow_trades.append(record)
        self._paper_shadow_exit_count += 1
        self._append_paper_shadow_telegram(
            title="SIM_EXIT",
            message_type=(
                TelegramSandboxMessageType.SIMULATED_EXIT_ALERT
            ),
            simulated_time=simulated_time,
            symbol=symbol,
            evidence_refs=tuple(closed_entry.evidence_refs),
            body_lines=[
                f"bridge={self._paper_shadow_bridge_name or 'none'}",
                f"symbol={symbol}",
                f"side={side}",
                f"leverage={leverage}",
                f"entry_price={entry_price}",
                f"exit_price={exit_price}",
                f"quantity={qty}",
                f"realized_pnl={net_pnl}",
                f"pnl_pct={pnl_pct}",
                f"outcome={closed_entry.outcome}",
                f"exit_reason={closed_entry.exit_reason}",
                f"signal_reason={exit_signal_reason}",
                f"equity_after={float(equity_after)}",
            ],
        )

    def _order_would_open_new_position(self, req: Any) -> bool:
        """Return True if submitting ``req`` would OPEN a brand-new
        simulated position (paper-only, read-only check).

        A fill OPENs a position only when the symbol currently has no
        OPEN position in the (PR98) Simulated Capital Flow book (a fill
        on an already-open symbol increases / reduces / closes it).
        This is used by the PR107 pre-submit concurrency gate so the
        runner never forwards an order that the later fill would have
        to reject. It is deliberately conservative: it treats any order
        on a flat symbol as a potential open regardless of side.
        """
        symbol = getattr(req, "symbol", None)
        if not isinstance(symbol, str) or not symbol:
            return False
        return self._open_position_for(symbol) is None

    def _handle_capacity_presubmit_reject(
        self,
        *,
        symbol: Optional[str],
        active_positions: int,
        max_active_positions: int,
        simulated_time: datetime,
    ) -> None:
        """Record a SIM_REJECT for an entry order dropped BEFORE
        submission because the simulated concurrency cap is reached
        (PR107 pre-submit gate).
        """
        sym = symbol if isinstance(symbol, str) and symbol else "unknown"
        rejection: Dict[str, Any] = {
            "symbol": sym,
            "simulated_time": ensure_utc_aware(
                simulated_time, "simulated_time"
            ).isoformat(),
            "reason": PAPER_SHADOW_REJECT_MAX_ACTIVE_POSITIONS,
            "detail": (
                f"pre-submit concurrency gate: active_positions="
                f"{int(active_positions)} >= max_active_positions="
                f"{int(max_active_positions)}; simulated order suppressed"
            ),
            "stage": "pre_submit",
            "active_positions": int(active_positions),
            "max_active_positions": int(max_active_positions),
            "bridge_name": self._paper_shadow_bridge_name,
            "no_live_order": True,
            "phase_12_forbidden": True,
            "trade_authority": False,
            "ai_trade_authority": False,
        }
        self._handle_simulated_reject(
            rejection=rejection, simulated_time=simulated_time
        )

    def _handle_capital_flow_reject(
        self,
        *,
        fill: MockFill,
        exc: Exception,
        simulated_time: datetime,
    ) -> None:
        """Convert an expected, predictable Simulated Capital Flow
        OPEN rejection (max_active_positions reached, or capital
        frozen) into a SIM_REJECT paper-shadow rejection event and keep
        the blind run going (PR107 hotfix §3).

        This is the belt-and-suspenders fallback for the rare case
        where a fill still reaches :meth:`consume_fill` after the
        pre-submit gate (e.g. several in-flight orders for distinct
        symbols all filling on the same step). It NEVER swallows an
        unknown exception: only the explicit
        :class:`MaxActivePositionsReachedError` /
        :class:`CapitalFrozenError` types are routed here.
        """
        symbol = getattr(fill, "symbol", None)
        sym = symbol if isinstance(symbol, str) and symbol else "unknown"
        if isinstance(exc, MaxActivePositionsReachedError):
            reason = PAPER_SHADOW_REJECT_MAX_ACTIVE_POSITIONS
            active = getattr(exc, "active_positions", None)
            cap = getattr(exc, "max_active_positions", None)
            if cap is None:
                cap = int(self._capital_flow.config.max_active_positions)
            detail = (
                f"consume_fill open rejected: active_positions="
                f"{active if active is not None else 'n/a'} >= "
                f"max_active_positions={cap}; simulated fill not opened"
            )
        elif isinstance(exc, SimAccountHaltedError):
            halt_reason = getattr(exc, "reason", None)
            if halt_reason == RiskHaltReason.CAPITAL_EXHAUSTED:
                reason = PAPER_SHADOW_REJECT_CAPITAL_EXHAUSTED
            elif (
                halt_reason == RiskHaltReason.MAX_DRAWDOWN_LIMIT_REACHED
            ):
                reason = PAPER_SHADOW_REJECT_MAX_DRAWDOWN_LIMIT
            else:
                reason = PAPER_SHADOW_REJECT_RISK_HALT_ACTIVE
            detail = (
                "consume_fill open rejected: simulated account halted "
                f"({halt_reason}); simulated fill not opened"
            )
        elif isinstance(exc, InsufficientSimulatedEquityError):
            reason = PAPER_SHADOW_REJECT_INSUFFICIENT_EQUITY
            detail = (
                "consume_fill open rejected: insufficient simulated "
                f"equity (required={getattr(exc, 'required', None)} "
                f"available={getattr(exc, 'available', None)}); "
                "simulated fill not opened"
            )
        else:
            reason = PAPER_SHADOW_REJECT_CAPITAL_FROZEN
            detail = (
                "consume_fill open rejected: simulated capital frozen "
                f"({getattr(self._capital_flow, 'freeze_reason', None)}); "
                "simulated fill not opened"
            )
        rejection: Dict[str, Any] = {
            "symbol": sym,
            "simulated_time": ensure_utc_aware(
                simulated_time, "simulated_time"
            ).isoformat(),
            "reason": reason,
            "detail": detail,
            "stage": "consume_fill",
            "bridge_name": self._paper_shadow_bridge_name,
            "no_live_order": True,
            "phase_12_forbidden": True,
            "trade_authority": False,
            "ai_trade_authority": False,
        }
        # Reset the bridge's per-symbol in-flight intent so a rejected
        # entry does NOT leave the symbol stuck ENTRY_PENDING forever.
        self._reset_bridge_intent_after_reject(sym)
        self._handle_simulated_reject(
            rejection=rejection, simulated_time=simulated_time
        )

    def _reset_bridge_intent_after_reject(self, symbol: str) -> None:
        """Best-effort reset of the paper-shadow bridge's per-symbol
        intent after a simulated OPEN rejection so the symbol can be
        re-evaluated on a later step instead of being stuck pending.

        Paper-only bookkeeping; never touches a real account, never
        carries trade authority.
        """
        bridge = self._paper_shadow_bridge
        if bridge is None:
            return
        try:
            states = getattr(bridge, "_states", None)
            if not isinstance(states, dict):
                return
            state = states.get(symbol)
            if state is None:
                return
            # Only reset a symbol that has no real open position; if a
            # position actually opened we must not clobber the intent.
            if self._open_position_for(symbol) is not None:
                return
            from app.sim.paper_shadow_strategy_bridge import (  # noqa: PLC0415
                _Intent,
            )

            state.intent = _Intent.FLAT
            state.entry_bar_index = None
            state.entry_signal_reason = None
        except Exception:  # pragma: no cover - defensive, never abort
            return

    def _handle_simulated_reject(
        self,
        *,
        rejection: Mapping[str, Any],
        simulated_time: datetime,
    ) -> None:
        rec = dict(rejection)
        rec.setdefault("is_simulated", True)
        rec.setdefault("no_live_order", True)
        rec.setdefault("trade_authority", False)
        rec.setdefault("ai_trade_authority", False)
        rec.setdefault("phase_12_forbidden", True)
        # PR108: count capital/risk rejections + keep the engine's own
        # capital_reject_count consistent.
        reason = rec.get("reason")
        equity_now = self._capital_flow.current_marked_equity()
        drawdown_now = self._capital_flow_drawdown()
        rec.setdefault("equity_before", float(equity_now))
        rec.setdefault("equity_after", float(equity_now))
        rec.setdefault("drawdown", float(drawdown_now))
        if isinstance(reason, str) and reason in _CAPITAL_REJECT_REASONS:
            self._capital_reject_count += 1
            try:
                if reason in CapitalRejectReason.ALLOWED:
                    self._capital_flow.register_capital_reject(reason)
            except Exception:  # pragma: no cover - defensive
                pass
        assert_no_forbidden_fields(rec)
        self._paper_shadow_rejections.append(rec)
        symbol = rec.get("symbol")
        self._append_paper_shadow_telegram(
            title="SIM_REJECT",
            message_type=TelegramSandboxMessageType.RISK_REJECTION,
            simulated_time=simulated_time,
            symbol=symbol if isinstance(symbol, str) else None,
            severity=TelegramSandboxSeverity.NOTICE,
            body_lines=[
                f"bridge={self._paper_shadow_bridge_name or 'none'}",
                f"symbol={symbol}",
                f"reason={rec.get('reason')}",
                f"reject_reason={rec.get('reason')}",
                f"detail={rec.get('detail')}",
                f"equity_before={float(rec.get('equity_before', 0.0))}",
                f"equity_after={float(rec.get('equity_after', 0.0))}",
                f"drawdown={float(rec.get('drawdown', 0.0))}",
            ],
        )

    def _capital_flow_drawdown(self) -> float:
        """Best-effort read of the current simulated drawdown."""
        try:
            state = self._capital_flow.get_state()
            return float(getattr(state, "drawdown", 0.0))
        except Exception:  # pragma: no cover - defensive
            return 0.0

    def _handle_capital_gate_reject(
        self,
        *,
        symbol: Optional[str],
        reason: str,
        simulated_time: datetime,
    ) -> None:
        """Record a SIM_REJECT for an entry order dropped BEFORE
        submission by the PR108 pre-entry capital/risk gate.
        """
        sym = symbol if isinstance(symbol, str) and symbol else "unknown"
        mapped = _CAPITAL_REJECT_REASON_MAP.get(
            reason, PAPER_SHADOW_REJECT_RISK_HALT_ACTIVE
        )
        rejection: Dict[str, Any] = {
            "symbol": sym,
            "simulated_time": ensure_utc_aware(
                simulated_time, "simulated_time"
            ).isoformat(),
            "reason": mapped,
            "detail": (
                "pre-entry capital/risk gate refused a new simulated "
                f"open (gate_reason={reason}); simulated order "
                "suppressed"
            ),
            "stage": "pre_entry_gate",
            "halted_by_risk": bool(
                getattr(self._capital_flow, "account_halted", False)
            ),
            "capital_exhausted": bool(
                getattr(self._capital_flow, "capital_exhausted", False)
            ),
            "risk_halt_reason": getattr(
                self._capital_flow, "halt_reason", None
            ),
            "bridge_name": self._paper_shadow_bridge_name,
            "no_live_order": True,
            "phase_12_forbidden": True,
            "trade_authority": False,
            "ai_trade_authority": False,
        }
        self._reset_bridge_intent_after_reject(sym)
        self._handle_simulated_reject(
            rejection=rejection, simulated_time=simulated_time
        )

    def _handle_capital_safety_event(
        self,
        *,
        event: Mapping[str, Any],
        simulated_time: datetime,
    ) -> None:
        """Surface a PR108 capital-safety enforcement event.

        Emits a SIM_FORCED_EXIT transcript entry + enriched paper-shadow
        trade record for every force-closed position, then a single
        SIM_CAPITAL_EXHAUSTED (capital floor breach) or
        SIM_ACCOUNT_HALTED (drawdown kill switch) transcript entry. The
        forced exits already went through the simulated capital flow;
        this method only records + notifies.
        """
        self._capital_safety_event_count += 1
        halt_reason = event.get("halt_reason")
        forced_exit_reason = event.get("forced_exit_reason")
        equity_before = float(event.get("equity_before", 0.0))
        equity_after = float(event.get("equity_after", 0.0))
        drawdown = float(event.get("drawdown", 0.0))
        forced_exits = event.get("forced_exits") or ()
        for closed_entry in forced_exits:
            self._handle_forced_capital_exit(
                closed_entry=closed_entry,
                exit_reason=(
                    forced_exit_reason
                    or ForcedExitReason.FORCED_CAPITAL_SAFETY_EXIT
                ),
                equity_after=equity_after,
                simulated_time=simulated_time,
            )
        capital_exhausted = bool(event.get("capital_exhausted", False))
        if capital_exhausted:
            title = "SIM_CAPITAL_EXHAUSTED"
        else:
            title = "SIM_ACCOUNT_HALTED"
        self._append_paper_shadow_telegram(
            title=title,
            message_type=TelegramSandboxMessageType.RISK_REJECTION,
            simulated_time=simulated_time,
            severity=TelegramSandboxSeverity.CRITICAL,
            body_lines=[
                f"bridge={self._paper_shadow_bridge_name or 'none'}",
                f"reason={halt_reason}",
                f"risk_halt_reason={halt_reason}",
                f"capital_exhausted={capital_exhausted}",
                "halted_by_risk=true",
                f"forced_exit_count={int(event.get('forced_exit_count', 0))}",
                f"equity_before={equity_before}",
                f"equity_after={equity_after}",
                f"drawdown={drawdown}",
                "liquidation_shortfall="
                f"{float(event.get('liquidation_shortfall', 0.0))}",
                "no_new_entries_for_remainder_of_window=true",
            ],
        )

    def _handle_forced_capital_exit(
        self,
        *,
        closed_entry: TradeLedgerEntry,
        exit_reason: str,
        equity_after: float,
        simulated_time: datetime,
    ) -> None:
        """Record an enriched paper-shadow trade for a forced
        capital-safety exit + emit a SIM_FORCED_EXIT transcript entry.
        """
        symbol = closed_entry.symbol
        meta = self._paper_shadow_open_meta.pop(symbol, {})
        side = meta.get("side", "LONG")
        leverage = float(
            meta.get("leverage", self._paper_shadow_leverage())
        )
        entry_price = float(closed_entry.avg_fill_price)
        qty = float(closed_entry.filled_qty)
        notional = entry_price * qty
        net_pnl = float(closed_entry.net_pnl)
        pnl_pct = (net_pnl / notional * 100.0) if notional > 0.0 else 0.0
        equity_before = float(meta.get("equity_before", 0.0))
        record: Dict[str, Any] = {
            "trade_id": closed_entry.trade_id,
            "run_id": (
                self._manifest.run_id if self._manifest else "unknown"
            ),
            "window_id": (
                self._manifest.window.window_id
                if self._manifest
                else "unknown"
            ),
            "symbol": symbol,
            "side": side,
            "leverage_ratio": leverage,
            "entry_time": (
                closed_entry.entry_time.isoformat()
                if closed_entry.entry_time is not None
                else None
            ),
            "exit_time": (
                closed_entry.exit_time.isoformat()
                if closed_entry.exit_time is not None
                else None
            ),
            "entry_price": entry_price,
            "exit_price": entry_price,
            "quantity": qty,
            "notional": notional,
            "fees": float(closed_entry.fee),
            "slippage_bps": float(closed_entry.slippage_bps),
            "realized_pnl": net_pnl,
            "pnl_pct": pnl_pct,
            "equity_before": equity_before,
            "equity_after": float(equity_after),
            "exit_reason": exit_reason,
            "entry_signal_reason": meta.get("entry_signal_reason"),
            "exit_signal_reason": exit_reason,
            "signal_reason": meta.get("entry_signal_reason") or exit_reason,
            "outcome": closed_entry.outcome,
            "evidence_refs": list(closed_entry.evidence_refs),
            "as_of_refs": [
                r
                for r in closed_entry.evidence_refs
                if isinstance(r, str) and r.startswith("asof:")
            ],
            "bridge_name": self._paper_shadow_bridge_name,
            "is_forced_capital_safety_exit": True,
            "is_simulated": True,
            "no_live_order": True,
            "phase_12_forbidden": True,
            "trade_authority": False,
            "ai_trade_authority": False,
        }
        assert_no_forbidden_fields(record)
        self._paper_shadow_trades.append(record)
        self._paper_shadow_exit_count += 1
        self._append_paper_shadow_telegram(
            title="SIM_FORCED_EXIT",
            message_type=TelegramSandboxMessageType.FORCED_EXIT,
            simulated_time=simulated_time,
            symbol=symbol,
            severity=TelegramSandboxSeverity.WARNING,
            evidence_refs=tuple(closed_entry.evidence_refs),
            body_lines=[
                f"bridge={self._paper_shadow_bridge_name or 'none'}",
                f"symbol={symbol}",
                f"side={side}",
                f"reason={exit_reason}",
                f"exit_reason={exit_reason}",
                f"entry_price={entry_price}",
                f"quantity={qty}",
                f"realized_pnl={net_pnl}",
                f"pnl_pct={pnl_pct}",
                f"outcome={closed_entry.outcome}",
                f"equity_before={equity_before}",
                f"equity_after={float(equity_after)}",
            ],
        )

    def _emit_window_summary(self) -> None:
        """Emit a paper-shadow WINDOW_SUMMARY transcript entry.

        Called once at blind-window close. Summarises the simulated
        trading activity (counts + realised PnL) so a file-based
        monitor can show a closing window summary.
        """
        if not self._config.telegram_sandbox_enabled:
            return
        summary = self._capital_flow.get_ledger().summary().to_dict()
        no_signals = bool(
            self._paper_shadow_enabled
            and self._paper_shadow_entry_count == 0
        )
        safety = self._capital_flow.capital_safety_snapshot()
        self._append_paper_shadow_telegram(
            title="WINDOW_SUMMARY",
            message_type=(
                TelegramSandboxMessageType.MONTHLY_BLIND_TEST_SUMMARY
            ),
            simulated_time=self._config.window.blind_end,
            body_lines=[
                f"bridge={self._paper_shadow_bridge_name or 'none'}",
                "paper_shadow_strategy_enabled="
                f"{self._paper_shadow_enabled}",
                f"entry_signals={self._paper_shadow_entry_count}",
                f"exit_signals={self._paper_shadow_exit_count}",
                f"reject_signals={len(self._paper_shadow_rejections)}",
                f"trade_count={int(summary.get('trade_count', 0))}",
                "closed_trade_count="
                f"{int(summary.get('trade_count', 0))}",
                f"win_count={int(summary.get('win_count', 0))}",
                f"loss_count={int(summary.get('loss_count', 0))}",
                "breakeven_count="
                f"{int(summary.get('breakeven_count', 0))}",
                "total_realized_pnl="
                f"{float(summary.get('total_realized_pnl', 0.0))}",
                f"max_drawdown={float(summary.get('max_drawdown', 0.0))}",
                f"no_paper_shadow_signals={no_signals}",
                # PR108 capital-safety closing fields.
                f"initial_capital={float(safety['initial_capital'])}",
                f"final_equity={float(safety['final_equity'])}",
                f"min_equity={float(safety['min_equity'])}",
                f"capital_exhausted={bool(safety['capital_exhausted'])}",
                f"halted_by_risk={bool(safety['halted_by_risk'])}",
                f"risk_halt_reason={safety['risk_halt_reason']}",
                f"forced_exit_count={int(safety['forced_exit_count'])}",
                "capital_reject_count="
                f"{int(self._capital_reject_count)}",
                "max_drawdown_limit="
                f"{safety['max_drawdown_limit']}",
                "equity_after="
                f"{self._capital_flow.current_marked_equity()}",
            ],
        )

    def _build_report_dict(self) -> Dict[str, Any]:
        manifest = self._manifest
        score = self._score
        if manifest is None or score is None:
            raise RuntimeError(
                "report cannot be built before scoring"
            )
        ledger_summary = (
            self._capital_flow.get_ledger().summary().to_dict()
        )
        no_paper_shadow_signals = bool(
            self._paper_shadow_enabled
            and self._paper_shadow_entry_count == 0
        )
        capital_safety = self._capital_flow.capital_safety_snapshot()
        out: Dict[str, Any] = {
            "run_id": manifest.run_id,
            "window_id": manifest.window.window_id,
            "phase": PHASE_NAME,
            "code_commit": manifest.code_commit,
            "manifest": manifest.to_dict(),
            "score": score.to_dict(),
            "ledger_summary": ledger_summary,
            "steps_run": self._steps_run,
            "batches_consumed": self._batches_consumed,
            "violations_count": len(self._violations),
            "no_lookahead_violations_count": len(self._violations),
            "invalidations": [
                copy.deepcopy(x) for x in self._invalidations
            ],
            "failure_ledger_entry_count": len(self._failure_entries),
            "discovery_quality_step_count": len(
                self._discovery_quality_steps
            ),
            # PR106 - Paper Shadow Strategy Bridge reporting (brief §9).
            "paper_shadow_strategy_enabled": self._paper_shadow_enabled,
            "strategy_bridge_name": self._paper_shadow_bridge_name,
            "trade_count": int(ledger_summary.get("trade_count", 0)),
            "closed_trade_count": int(
                ledger_summary.get("trade_count", 0)
            ),
            "total_realized_pnl": float(
                ledger_summary.get("total_realized_pnl", 0.0)
            ),
            "max_drawdown": float(
                ledger_summary.get("max_drawdown", 0.0)
            ),
            "win_count": int(ledger_summary.get("win_count", 0)),
            "loss_count": int(ledger_summary.get("loss_count", 0)),
            "breakeven_count": int(
                ledger_summary.get("breakeven_count", 0)
            ),
            "paper_shadow_entry_signal_count": (
                self._paper_shadow_entry_count
            ),
            "paper_shadow_exit_signal_count": (
                self._paper_shadow_exit_count
            ),
            "paper_shadow_reject_count": len(
                self._paper_shadow_rejections
            ),
            "paper_shadow_trade_count": len(self._paper_shadow_trades),
            "no_paper_shadow_signals": no_paper_shadow_signals,
            # PR108 - Simulated Capital Safety Floor / Kill Switch
            # reporting (brief §2 / §8).
            "initial_capital": float(capital_safety["initial_capital"]),
            "final_equity": float(capital_safety["final_equity"]),
            "min_equity": float(capital_safety["min_equity"]),
            "max_drawdown_limit": capital_safety["max_drawdown_limit"],
            "capital_floor": float(capital_safety["capital_floor"]),
            "capital_exhausted": bool(
                capital_safety["capital_exhausted"]
            ),
            "halted_by_risk": bool(capital_safety["halted_by_risk"]),
            "risk_halt_reason": capital_safety["risk_halt_reason"],
            "forced_exit_count": int(
                capital_safety["forced_exit_count"]
            ),
            "capital_reject_count": int(self._capital_reject_count),
            "capital_exhaustion_event_count": int(
                capital_safety["capital_exhaustion_event_count"]
            ),
            "liquidation_like_event_count": int(
                capital_safety["liquidation_like_event_count"]
            ),
            "liquidation_shortfall": float(
                capital_safety["liquidation_shortfall"]
            ),
            "no_negative_equity_guard": bool(
                capital_safety["no_negative_equity_guard"]
            ),
            "capital_safety": capital_safety,
            "is_blind_walk_forward_report": True,
            "next_allowed_step": (
                "blind_walk_forward_operator_evidence_run_or_checkpoint"
            ),
            "this_authorises_live_trading": False,
            "this_authorises_auto_tuning": False,
            "this_authorises_real_telegram": False,
            "this_authorises_binance_private_api": False,
            "this_authorises_phase_12": False,
        }
        if self._paper_shadow_bridge is not None:
            out["paper_shadow_strategy_bridge"] = (
                self._paper_shadow_bridge.to_dict()
            )
        if self._post_window_ai_summary is not None:
            out["post_window_ai_summary"] = copy.deepcopy(
                self._post_window_ai_summary
            )
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    def _build_report_markdown(self, report: Mapping[str, Any]) -> str:
        manifest = report["manifest"]
        score = report["score"]
        lines: List[str] = []
        lines.append(
            f"# Blind Walk-forward Run {report['run_id']}"
        )
        lines.append("")
        lines.append(f"- phase: `{report['phase']}`")
        lines.append(f"- window_id: `{report['window_id']}`")
        lines.append(f"- code_commit: `{report['code_commit']}`")
        lines.append(f"- status: `{score['status']}`")
        lines.append("")
        lines.append("## Safety boundary")
        lines.append("")
        lines.append("- mode: `historical_blind_sim_live`")
        lines.append("- live_trading: `false`")
        lines.append("- exchange_live_orders: `false`")
        lines.append("- binance_private_api_enabled: `false`")
        lines.append("- telegram_outbound_enabled: `false`")
        lines.append("- telegram_live_command_authority: `false`")
        lines.append(
            "- telegram_production_channel_enabled: `false`"
        )
        lines.append("- ai_trade_authority: `false`")
        lines.append("- trade_authority: `false`")
        lines.append("- auto_tuning_inside_blind_window: `false`")
        lines.append("- auto_tuning_allowed: `false`")
        lines.append("- phase_12_forbidden: `true`")
        lines.append("")
        lines.append("## Aggregates")
        lines.append("")
        lines.append(f"- steps_run: `{report['steps_run']}`")
        lines.append(
            f"- batches_consumed: `{report['batches_consumed']}`"
        )
        lines.append(
            f"- violations_count: `{report['violations_count']}`"
        )
        lines.append(
            f"- failure_ledger_entry_count: "
            f"`{report['failure_ledger_entry_count']}`"
        )
        lines.append(
            f"- discovery_quality_step_count: "
            f"`{report['discovery_quality_step_count']}`"
        )
        lines.append(
            f"- closed_trade_count: `{score['closed_trade_count']}`"
        )
        lines.append(
            f"- total_realized_pnl: `{score['total_realized_pnl']}`"
        )
        lines.append("")
        lines.append("## Paper shadow strategy")
        lines.append("")
        lines.append(
            "- paper_shadow_strategy_enabled: "
            f"`{report.get('paper_shadow_strategy_enabled')}`"
        )
        lines.append(
            f"- strategy_bridge_name: `{report.get('strategy_bridge_name')}`"
        )
        lines.append(
            f"- trade_count: `{report.get('trade_count')}`"
        )
        lines.append(
            "- paper_shadow_entry_signal_count: "
            f"`{report.get('paper_shadow_entry_signal_count')}`"
        )
        lines.append(
            "- paper_shadow_exit_signal_count: "
            f"`{report.get('paper_shadow_exit_signal_count')}`"
        )
        lines.append(
            "- paper_shadow_reject_count: "
            f"`{report.get('paper_shadow_reject_count')}`"
        )
        lines.append(
            "- no_paper_shadow_signals: "
            f"`{report.get('no_paper_shadow_signals')}`"
        )
        lines.append("")
        lines.append("## Capital safety (PR108)")
        lines.append("")
        lines.append(
            f"- initial_capital: `{report.get('initial_capital')}`"
        )
        lines.append(f"- final_equity: `{report.get('final_equity')}`")
        lines.append(f"- min_equity: `{report.get('min_equity')}`")
        lines.append(f"- max_drawdown: `{report.get('max_drawdown')}`")
        lines.append(
            f"- max_drawdown_limit: `{report.get('max_drawdown_limit')}`"
        )
        lines.append(
            f"- capital_exhausted: `{report.get('capital_exhausted')}`"
        )
        lines.append(
            f"- halted_by_risk: `{report.get('halted_by_risk')}`"
        )
        lines.append(
            f"- risk_halt_reason: `{report.get('risk_halt_reason')}`"
        )
        lines.append(
            f"- forced_exit_count: `{report.get('forced_exit_count')}`"
        )
        lines.append(
            f"- capital_reject_count: `{report.get('capital_reject_count')}`"
        )
        lines.append(
            "- capital_exhaustion_event_count: "
            f"`{report.get('capital_exhaustion_event_count')}`"
        )
        lines.append(
            "- no_negative_equity_guard: "
            f"`{report.get('no_negative_equity_guard')}`"
        )
        lines.append("")
        lines.append("## Manifest hashes")
        lines.append("")
        for k in (
            "config_hash",
            "rule_hash",
            "feature_schema_hash",
            "data_manifest_hash",
            "universe_manifest_hash",
            "fee_model_hash",
            "slippage_model_hash",
            "latency_model_hash",
            "outage_model_hash",
            "fill_model_hash",
        ):
            lines.append(f"- {k}: `{manifest.get(k)}`")
        lines.append("")
        lines.append("## Authority statement")
        lines.append("")
        lines.append(
            "Successful PR100 acceptance only authorises a "
            "paper-only blind-run checkpoint or operator evidence "
            "run. It does NOT authorise live trading, auto-tuning, "
            "real Telegram outbound, real exchange orders, the "
            "Binance private API, or Phase 12."
        )
        lines.append("")
        return "\n".join(lines)


__all__ = [
    "AsOfFeatureCache",
    "BlindWalkForwardRunner",
    "BlindWalkForwardRunnerConfig",
    "DEFAULT_REPORT_ROOT",
    "DecisionCallback",
    "MultiTimeframeAsOfGuard",
]
