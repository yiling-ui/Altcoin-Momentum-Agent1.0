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
from app.sim.pessimistic_fill_model import (
    AmbiguousIntrabarPolicy,
    PessimisticFillModel,
)
from app.sim.replay_feed_provider import ReplayFeedBatch, ReplayFeedProvider
from app.sim.simulated_capital_flow import SimulatedCapitalFlowEngine
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
        feature_cache: Optional[AsOfFeatureCache] = None,
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
            data_manifest_hash=compute_artefact_hash(
                cfg.data_manifest_artefact
            ),
            universe_manifest_hash=compute_artefact_hash(
                cfg.universe_manifest_artefact
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
            try:
                self._capital_flow.consume_fill(fill)
            except Exception as exc:
                self._record_failure(
                    kind="capital_flow_consume_error",
                    detail=str(exc),
                    simulated_time=new_st,
                )
                raise
            self._emit_telegram_fill(fill=fill, simulated_time=new_st)

        # 4) Decision callback (strategy-less in v0).
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

        # 5) Submit orders WITHOUT a replay_batch; they will fill
        #    against the next batch's closed bars (strict forward-only).
        for req in orders:
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
        while True:
            b = self.step_once()
            if b is None:
                break
            batches.append(b)
        # Final mark-to-market at blind_end so the equity time-series
        # contains a closing point even if the last batch was earlier.
        try:
            self._capital_flow.apply_mark_prices(
                {}, simulated_time=self._config.window.blind_end
            )
        except Exception:  # pragma: no cover - defensive
            pass
        self._phase = _RunnerPhase.BLIND_COMPLETE
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
        self.run_blind_window()
        self.score_after_window_close()
        paths = self.generate_outputs(report_dir=report_dir)
        return {
            "manifest": self._manifest.to_dict() if self._manifest else None,
            "score": self._score.to_dict() if self._score else None,
            "paths": paths,
        }

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

    def _build_report_dict(self) -> Dict[str, Any]:
        manifest = self._manifest
        score = self._score
        if manifest is None or score is None:
            raise RuntimeError(
                "report cannot be built before scoring"
            )
        out: Dict[str, Any] = {
            "run_id": manifest.run_id,
            "window_id": manifest.window.window_id,
            "phase": PHASE_NAME,
            "code_commit": manifest.code_commit,
            "manifest": manifest.to_dict(),
            "score": score.to_dict(),
            "ledger_summary": self._capital_flow.get_ledger()
            .summary()
            .to_dict(),
            "steps_run": self._steps_run,
            "batches_consumed": self._batches_consumed,
            "violations_count": len(self._violations),
            "invalidations": [
                copy.deepcopy(x) for x in self._invalidations
            ],
            "failure_ledger_entry_count": len(self._failure_entries),
            "discovery_quality_step_count": len(
                self._discovery_quality_steps
            ),
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
