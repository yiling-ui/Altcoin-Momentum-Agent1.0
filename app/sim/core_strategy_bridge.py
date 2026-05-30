"""Core Strategy Sim-Live Bridge v0 for Phase 11C.1D-D (PR109 - Core
Strategy Sim-Live Bridge for Recent 60D Full-Market Blind Validation).

Strict blind walk-forward, paper-only, deterministic decision bridge
that drives the **AMA-RT core strategy decision lifecycle** (market
regime -> candidate stage -> opportunity score -> strategy mode)
instead of the PR106 ``baseline_breakout_volume_v0`` shadow rule.

Why this exists (PR109 brief)
-----------------------------

PR106/107/108 proved the strict blind walk-forward substrate end to
end with a *baseline* paper-shadow rule. The cloud PR108 result was a
clean technical pass (violations_count=0, no negative equity, kill
switch latched correctly) but the baseline rule was **not** the real
AMA-RT strategy, so its PnL is not a Go/No-Go signal for live capital.

This module **bridges the existing AMA-RT core strategy** - the same
pure, deterministic functions the Phase 11C.1C adaptive candidate
lifecycle uses:

  * :func:`app.adaptive.regime.assess_market_regime`
  * :func:`app.adaptive.stage.classify_candidate_stage`
  * :func:`app.adaptive.scoring.compute_opportunity_score`
  * :func:`app.adaptive.selector.select_strategy_mode`

into a blind-runner-compatible decision callback. It is the **minimal
adapter**: the only new logic is the as-of feature extraction that
turns already-visible CLOSED candles into the score inputs the core
functions consume. Every trade decision is the output of the real
core selector; the bridge never invents its own alpha.

What this bridge IS
-------------------

  * a pure / deterministic / replayable decision callback (a
    ``PaperShadowStrategyBridge`` subclass so the PR100 runner can use
    it with zero runner-side type changes),
  * a consumer of CLOSED 1m (or 5m) klines that are already visible at
    ``simulated_time`` (``available_at <= simulated_time`` AND candle
    closed),
  * an as-of-universe-restricted scanner (never trades a symbol that
    was not TRADING / monitorable as-of the current simulated time),
  * a thin glue layer over the AMA-RT core regime/stage/score/selector.

What this bridge is NOT (hard boundary, same as the rest of the
strict-blind stack)
-------------------------------------------------------------------

  * NOT a live trading path,
  * NOT an auto-tuner (no parameter is tuned from any blind result;
    the config is frozen for the whole window),
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

It DOES import the pure ``app.adaptive`` core-strategy functions
(``regime`` / ``stage`` / ``scoring`` / ``selector``). Those depend
only on ``app.adaptive.models`` (pydantic value objects); importing
them performs no network I/O, opens no socket, reads no credentials,
and never touches ``app.config`` / ``app.risk`` / ``app.execution`` /
``app.exchanges`` / ``app.telegram``.

No-lookahead contract (Constitution §5 / §6 / §9): at simulated time
``T`` the bridge MAY only use records whose ``available_at <= T``,
candles that have CLOSED (``close_time <= T``), and symbols that are
in the as-of universe at ``T``. Every gate is inherited verbatim from
:class:`PaperShadowStrategyBridge`; this subclass only changes the
*decision* taken on top of the already-gated, already-closed bars.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import (
    Any,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

# Pure AMA-RT core-strategy decision lifecycle. These functions depend
# only on app.adaptive.models (pydantic value objects); see the module
# docstring for the import-safety rationale.
from app.adaptive.models import MarketRegimeAssessment
from app.adaptive.regime import assess_market_regime
from app.adaptive.scoring import compute_opportunity_score
from app.adaptive.selector import select_strategy_mode
from app.adaptive.stage import classify_candidate_stage

from app.sim.mock_exchange import OrderRequest
from app.sim.paper_shadow_strategy_bridge import (
    DEFAULT_BRIDGE_NAME,
    PaperShadowRejectReason,
    PaperShadowStrategyBridge,
    PaperShadowStrategyBridgeConfig,
    _ClosedBar,
    _Intent,
    _SymbolState,
    _validate_positive,
    _validate_positive_int,
    _validate_unit_fraction,
)
from app.sim.pessimistic_fill_model import MockOrderSide, MockOrderType
from app.sim.replay_feed_provider import ReplayFeedBatch
from app.sim.simulation_clock import ensure_utc_aware
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D / PR109 / Core Strategy Sim-Live Bridge v0"
)

#: Canonical strategy profile name surfaced into the blind report.
CORE_STRATEGY_PROFILE: str = "core"

#: Default deterministic core-strategy bridge name. Surfaced into the
#: blind report's ``strategy_bridge_name`` and the trade ledger /
#: transcript.
DEFAULT_CORE_BRIDGE_NAME: str = "ama_rt_core_strategy_v0"


# ---------------------------------------------------------------------------
# Closed taxonomy of core-strategy signal reasons
# ---------------------------------------------------------------------------


class CoreStrategySignalReason:
    """Closed taxonomy of deterministic core-strategy signal reasons.

    These are descriptive labels recorded into ``evidence_refs`` / the
    simulated trade record. They are NEVER an AI recommendation, NEVER
    a runtime config patch, NEVER a live trade authority signal. Each
    entry reason maps 1:1 onto the core selector's ``follow`` /
    ``pullback`` strategy mode.
    """

    CORE_FOLLOW_ENTRY: str = "core_follow_entry"
    CORE_PULLBACK_ENTRY: str = "core_pullback_entry"
    EXIT_TAKE_PROFIT: str = "exit_take_profit"
    EXIT_STOP_LOSS: str = "exit_stop_loss"
    EXIT_MAX_HOLD: str = "exit_max_hold"
    EXIT_STAGE_EXHAUSTED: str = "exit_stage_exhausted"
    EXIT_REGIME_RISK_OFF: str = "exit_regime_risk_off"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            CORE_FOLLOW_ENTRY,
            CORE_PULLBACK_ENTRY,
            EXIT_TAKE_PROFIT,
            EXIT_STOP_LOSS,
            EXIT_MAX_HOLD,
            EXIT_STAGE_EXHAUSTED,
            EXIT_REGIME_RISK_OFF,
        }
    )


# Regime buckets the selector treats as an outright no-trade veto.
_REGIME_VETO_BUCKETS: FrozenSet[str] = frozenset(
    {"RISK_OFF", "NO_TRADE", "SYSTEMIC_RISK", "ALT_RISK_OFF"}
)

# Candidate stages that mean "the move is over / rolled over" -> exit
# any open core position.
_STAGE_EXIT_BUCKETS: FrozenSet[str] = frozenset({"blowoff", "dumped"})


# ---------------------------------------------------------------------------
# CoreStrategyBridgeConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoreStrategyBridgeConfig(PaperShadowStrategyBridgeConfig):
    """Frozen configuration for a :class:`CoreStrategyBridge`.

    Extends :class:`PaperShadowStrategyBridgeConfig` (so the inherited
    ingestion / no-lookahead / intent state machine work unchanged) and
    adds the as-of feature-extraction scales that map already-closed
    candles onto the AMA-RT core-strategy score inputs.

    The frozen container guarantees the rule's parameters cannot be
    mutated at runtime (no auto-tuning inside a blind window). Every
    default is conservative and is NOT optimised for profitability;
    PR109's job is to bridge the real core strategy, never to tune it.

    The inherited ``breakout_lookback`` is reused as the rolling
    reference-window length (how many CLOSED bars back the "first seen"
    reference price sits). ``min_history_bars`` must stay strictly
    greater than it (inherited invariant).
    """

    bridge_name: str = DEFAULT_CORE_BRIDGE_NAME
    # Number of recent CLOSED bars used to measure the *recent*
    # momentum that ignites a follow/pullback entry. Must be < the
    # rolling window (breakout_lookback).
    momentum_lookback: int = 3
    # Recent return that maps to a full (100) momentum_strength input.
    momentum_full_scale_pct: float = 0.05
    # Volume-vs-rolling-mean ratio that maps to a full (100)
    # volume_expansion input.
    volume_full_scale_ratio: float = 2.0
    # Quote-volume (close * volume) that maps to a full (100)
    # liquidity_quality input.
    liquidity_reference_quote_volume: float = 500_000.0
    # Total run-up over the rolling window that maps to a full (100)
    # late_chase_risk input.
    late_chase_full_scale_pct: float = 0.20
    # Upper-wick-fraction multiplier that maps to the manipulation_risk
    # input (1.0 => a full upper wick == 100 manipulation_risk).
    manipulation_wick_scale: float = 1.0
    # Minimum opportunity score required to ACT on a follow/pullback
    # mode (the core selector still gates the mode itself).
    min_opportunity_score: float = 50.0
    # Scale the per-entry notional by the regime risk multiplier
    # (core risk path); a risk-off-tilted regime sizes down.
    scale_notional_by_regime: bool = True

    def __post_init__(self) -> None:
        # Run every inherited validation / normalisation first.
        super().__post_init__()
        ml = _validate_positive_int("momentum_lookback", self.momentum_lookback)
        if ml >= int(self.breakout_lookback):
            raise ValueError(
                "momentum_lookback must be < breakout_lookback so the "
                "recent-momentum window is a strict subset of the "
                "rolling reference window"
            )
        mfs = _validate_unit_fraction(
            "momentum_full_scale_pct", self.momentum_full_scale_pct
        )
        vfs = _validate_positive(
            "volume_full_scale_ratio", self.volume_full_scale_ratio
        )
        if vfs <= 1.0:
            raise ValueError(
                "volume_full_scale_ratio must be > 1.0 (a ratio of 1.0 "
                "is no expansion at all)"
            )
        lrqv = _validate_positive(
            "liquidity_reference_quote_volume",
            self.liquidity_reference_quote_volume,
        )
        lcfs = _validate_unit_fraction(
            "late_chase_full_scale_pct", self.late_chase_full_scale_pct
        )
        mws = _validate_positive(
            "manipulation_wick_scale", self.manipulation_wick_scale
        )
        mos = float(self.min_opportunity_score)
        if isinstance(self.min_opportunity_score, bool) or not (
            0.0 <= mos <= 100.0
        ):
            raise ValueError(
                "min_opportunity_score must be a number in [0.0, 100.0]"
            )
        if not isinstance(self.scale_notional_by_regime, bool):
            raise TypeError("scale_notional_by_regime must be bool")
        object.__setattr__(self, "momentum_lookback", ml)
        object.__setattr__(self, "momentum_full_scale_pct", mfs)
        object.__setattr__(self, "volume_full_scale_ratio", vfs)
        object.__setattr__(
            self, "liquidity_reference_quote_volume", lrqv
        )
        object.__setattr__(self, "late_chase_full_scale_pct", lcfs)
        object.__setattr__(self, "manipulation_wick_scale", mws)
        object.__setattr__(self, "min_opportunity_score", mos)

    def to_dict(self) -> Dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "strategy_profile": CORE_STRATEGY_PROFILE,
                "is_core_strategy_bridge_config": True,
                "momentum_lookback": int(self.momentum_lookback),
                "momentum_full_scale_pct": float(
                    self.momentum_full_scale_pct
                ),
                "volume_full_scale_ratio": float(
                    self.volume_full_scale_ratio
                ),
                "liquidity_reference_quote_volume": float(
                    self.liquidity_reference_quote_volume
                ),
                "late_chase_full_scale_pct": float(
                    self.late_chase_full_scale_pct
                ),
                "manipulation_wick_scale": float(
                    self.manipulation_wick_scale
                ),
                "min_opportunity_score": float(self.min_opportunity_score),
                "scale_notional_by_regime": bool(
                    self.scale_notional_by_regime
                ),
            }
        )
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clip_pct(value: float) -> float:
    """Clip ``value`` to ``[0.0, 100.0]`` (the core-score input range)."""
    v = float(value)
    if not math.isfinite(v) or v < 0.0:
        return 0.0
    if v > 100.0:
        return 100.0
    return v


def _ts_ms(dt: datetime) -> int:
    return int(ensure_utc_aware(dt, "bar_time").timestamp() * 1000.0)


@dataclass(frozen=True)
class _CoreFeatures:
    """As-of feature snapshot fed to the AMA-RT core score inputs."""

    momentum_strength: float
    volume_expansion: float
    liquidity_quality: float
    freshness: float
    manipulation_risk: float
    late_chase_risk: float
    total_distance: float
    current_close: float
    stage: Any  # CandidateStageAssessment


# ---------------------------------------------------------------------------
# CoreStrategyBridge
# ---------------------------------------------------------------------------


class CoreStrategyBridge(PaperShadowStrategyBridge):
    """Deterministic, paper-only blind-runner decision bridge driven by
    the AMA-RT core strategy decision lifecycle.

    Subclasses :class:`PaperShadowStrategyBridge` so the PR100 runner
    accepts it as a drop-in ``paper_shadow_bridge`` (it passes the
    runner's ``isinstance`` gate and reuses ``drain_rejections`` /
    ``_states`` / ``_Intent`` / ``leverage`` / ``diagnostics``). The
    subclass overrides ONLY the decision step: ingestion, the
    no-lookahead visibility gate, the per-symbol intent state machine,
    and the rejection bookkeeping are inherited verbatim.

    On each step the runner calls ``bridge(simulated_time, batch,
    runner)`` and forwards every returned :class:`OrderRequest` to the
    :class:`MockExchange`. Position state is reconciled from the (PR98)
    :class:`SimulatedCapitalFlowEngine` open-position book.
    """

    def __init__(
        self,
        *,
        config: Optional[CoreStrategyBridgeConfig] = None,
        capital_flow: Any = None,
    ) -> None:
        if config is None:
            config = CoreStrategyBridgeConfig()
        if not isinstance(config, CoreStrategyBridgeConfig):
            raise TypeError(
                "config must be CoreStrategyBridgeConfig, got "
                f"{type(config)!r}"
            )
        super().__init__(config=config, capital_flow=capital_flow)
        # Market-wide regime assessment recomputed once per step from
        # the already-ingested, already-closed bars. Descriptive only;
        # the core selector reads it but it is NEVER a trade authority.
        self._current_regime: Optional[MarketRegimeAssessment] = None
        # Distinct symbols that produced at least one core entry signal
        # (paper-only bookkeeping for the report's symbols_traded_count).
        self._symbols_with_entry_signal: set = set()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def core_config(self) -> CoreStrategyBridgeConfig:
        return self._config  # type: ignore[return-value]

    @property
    def strategy_profile(self) -> str:
        return CORE_STRATEGY_PROFILE

    @property
    def core_strategy_enabled(self) -> bool:
        return True

    @property
    def current_regime(self) -> Optional[MarketRegimeAssessment]:
        return self._current_regime

    @property
    def symbols_scanned(self) -> Tuple[str, ...]:
        return tuple(sorted(self._states.keys()))

    @property
    def symbols_traded(self) -> Tuple[str, ...]:
        return tuple(sorted(self._symbols_with_entry_signal))

    def to_dict(self) -> Dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "is_core_strategy_bridge": True,
                "strategy_profile": CORE_STRATEGY_PROFILE,
                "core_strategy_enabled": True,
                "symbols_scanned_count": len(self._states),
                "symbols_traded_count": len(
                    self._symbols_with_entry_signal
                ),
                "current_regime": (
                    self._current_regime.regime_name
                    if self._current_regime is not None
                    else None
                ),
            }
        )
        assert_no_forbidden_fields(out)
        return out

    # ------------------------------------------------------------------
    # Decision-callback entry point (override: insert regime assessment)
    # ------------------------------------------------------------------

    def __call__(
        self,
        simulated_time: datetime,
        batch: ReplayFeedBatch,
        runner: Any = None,
    ) -> Sequence[OrderRequest]:
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

        # Recompute the market-wide regime from the already-ingested,
        # already-closed bars BEFORE evaluating any symbol. The regime
        # is a pure function of as-of-visible price action; it never
        # reads the future and never carries trade authority.
        self._current_regime = self._assess_regime(asof_symbols=asof_symbols)

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

    # ------------------------------------------------------------------
    # Internal: market-wide regime assessment (as-of only)
    # ------------------------------------------------------------------

    def _assess_regime(
        self, *, asof_symbols: Optional[FrozenSet[str]]
    ) -> MarketRegimeAssessment:
        """Assess the macro regime from the latest as-of-visible bars.

        Uses the most recent two CLOSED bars per scanned symbol to
        derive a per-symbol 1-bar acceleration, then aggregates the
        average acceleration + positive ratio across the scanned
        universe. Liquidation data is not available from klines alone,
        so the liquidation rate is 0.0; the classifier stays in the
        conservative NEUTRAL / risk-on buckets accordingly. Pure /
        deterministic / as-of; no future read.
        """
        accels: List[float] = []
        for symbol, state in self._states.items():
            if asof_symbols is not None and symbol not in asof_symbols:
                continue
            bars = list(state.bars)
            if len(bars) < 2:
                continue
            prev_close = float(bars[-2].close)
            cur_close = float(bars[-1].close)
            if prev_close > 0.0:
                accels.append((cur_close - prev_close) / prev_close)
        if not accels:
            # No two-bar history yet: conservative NEUTRAL.
            return assess_market_regime(
                data_quality="ok", snapshot_count=0
            )
        avg_accel = sum(accels) / float(len(accels))
        positive_ratio = sum(1 for a in accels if a > 0.0) / float(
            len(accels)
        )
        return assess_market_regime(
            avg_price_acceleration_60s=avg_accel,
            positive_acceleration_ratio=positive_ratio,
            liquidation_event_rate=0.0,
            data_quality="ok",
            snapshot_count=len(accels),
        )

    # ------------------------------------------------------------------
    # Internal: as-of feature extraction
    # ------------------------------------------------------------------

    def _build_core_features(
        self, state: _SymbolState
    ) -> Optional[_CoreFeatures]:
        """Turn the rolling CLOSED-bar window into AMA-RT score inputs.

        Returns ``None`` when there is not enough closed history yet.
        Every input is derived ONLY from already-closed, already-visible
        bars (the inherited ingestion guard guarantees this).
        """
        cfg: CoreStrategyBridgeConfig = self._config  # type: ignore
        bars = list(state.bars)
        if len(bars) < cfg.min_history_bars:
            return None
        window = bars[-(cfg.breakout_lookback + 1):]
        if len(window) < cfg.breakout_lookback + 1:
            return None
        ref = window[0]
        current = window[-1]
        prior = window[:-1]

        ref_close = float(ref.close)
        cur_close = float(current.close)
        if ref_close <= 0.0 or cur_close <= 0.0:
            return None

        total_distance = (cur_close - ref_close) / ref_close

        # Recent momentum over a strict subset of the rolling window.
        recent_ref = window[-(cfg.momentum_lookback + 1)]
        recent_ref_close = float(recent_ref.close)
        recent_ret = (
            (cur_close - recent_ref_close) / recent_ref_close
            if recent_ref_close > 0.0
            else 0.0
        )
        momentum_strength = _clip_pct(
            recent_ret / cfg.momentum_full_scale_pct * 100.0
        )

        prior_vol_mean = sum(float(b.volume) for b in prior) / float(
            len(prior)
        )
        if prior_vol_mean > 0.0:
            vol_ratio = float(current.volume) / prior_vol_mean
        else:
            vol_ratio = 0.0
        volume_expansion = _clip_pct(
            (vol_ratio - 1.0)
            / (cfg.volume_full_scale_ratio - 1.0)
            * 100.0
        )

        quote_volume = cur_close * float(current.volume)
        liquidity_quality = _clip_pct(
            quote_volume / cfg.liquidity_reference_quote_volume * 100.0
        )

        prev_close = float(prior[-1].close)
        accel_60 = (
            (cur_close - prev_close) / prev_close
            if prev_close > 0.0
            else 0.0
        )

        stage = classify_candidate_stage(
            first_seen_ts_ms=_ts_ms(ref.open_time),
            first_seen_price=ref_close,
            current_price=cur_close,
            current_ts_ms=_ts_ms(current.open_time),
            price_24h_high=None,
            price_acceleration_60s=accel_60,
        )
        freshness = _clip_pct(float(stage.freshness) * 100.0)
        late_chase_risk = _clip_pct(
            max(0.0, total_distance)
            / cfg.late_chase_full_scale_pct
            * 100.0
        )

        bar_range = float(current.high) - float(current.low)
        if bar_range > 0.0:
            upper_wick = float(current.high) - max(
                float(current.open), float(current.close)
            )
            manipulation_risk = _clip_pct(
                upper_wick / bar_range * 100.0 * cfg.manipulation_wick_scale
            )
        else:
            manipulation_risk = 0.0

        return _CoreFeatures(
            momentum_strength=momentum_strength,
            volume_expansion=volume_expansion,
            liquidity_quality=liquidity_quality,
            freshness=freshness,
            manipulation_risk=manipulation_risk,
            late_chase_risk=late_chase_risk,
            total_distance=total_distance,
            current_close=cur_close,
            stage=stage,
        )

    def _regime_fit(self, regime: MarketRegimeAssessment) -> float:
        """Map the regime onto a [0,100] regime-fit score input."""
        return _clip_pct(
            float(regime.risk_multiplier) * 70.0
            + float(regime.confidence) * 30.0
        )

    # ------------------------------------------------------------------
    # Internal: per-symbol rule evaluation (override the decision only)
    # ------------------------------------------------------------------

    def _maybe_enter(
        self,
        *,
        symbol: str,
        state: _SymbolState,
        simulated_time: datetime,
        asof_symbols: Optional[FrozenSet[str]],
        open_positions: Mapping[str, Any],
    ) -> List[OrderRequest]:
        cfg: CoreStrategyBridgeConfig = self._config  # type: ignore
        features = self._build_core_features(state)
        if features is None:
            return []

        regime = self._current_regime or assess_market_regime(
            data_quality="ok", snapshot_count=0
        )
        score = compute_opportunity_score(
            {
                "momentum_strength": features.momentum_strength,
                "volume_expansion": features.volume_expansion,
                "liquidity_quality": features.liquidity_quality,
                "regime_fit": self._regime_fit(regime),
                "freshness": features.freshness,
                "manipulation_risk": features.manipulation_risk,
                "late_chase_risk": features.late_chase_risk,
            }
        )
        decision = select_strategy_mode(
            market_regime=regime,
            candidate_stage=features.stage,
            opportunity_score=score,
        )

        # Only follow / pullback express a paper entry plan. observe /
        # reject are simply "no entry this bar" (NOT a suppressed valid
        # signal, so they are not recorded as rejections).
        if decision.mode == "follow" and decision.follow_allowed:
            signal_reason = CoreStrategySignalReason.CORE_FOLLOW_ENTRY
        elif decision.mode == "pullback" and decision.pullback_allowed:
            signal_reason = CoreStrategySignalReason.CORE_PULLBACK_ENTRY
        else:
            return []

        # Core selection gate: the opportunity score must clear the
        # configured floor before the plan is acted on.
        if float(score.score) < float(cfg.min_opportunity_score):
            return []

        # As-of universe gate (Constitution §9): never trade a symbol
        # that is not tradable / monitorable as-of the current time.
        if asof_symbols is not None and symbol not in asof_symbols:
            self._add_rejection(
                symbol=symbol,
                simulated_time=simulated_time,
                reason=PaperShadowRejectReason.SYMBOL_NOT_IN_ASOF_UNIVERSE,
                detail=(
                    "core entry signal suppressed: symbol not as-of "
                    f"tradable (mode={decision.mode} grade={score.grade})"
                ),
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
        # limit breached) the bridge stops emitting NEW entries for the
        # rest of the blind window. The runner's pre-entry gate is the
        # authoritative second line of defence.
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
                    "core entry signal suppressed: simulated account "
                    f"halted ({halt_detail})"
                ),
            )
            return []

        # Core risk path sizing: fixed notional, optionally scaled down
        # by the regime risk multiplier. Never margined in v0.
        notional = float(cfg.position_notional)
        if cfg.scale_notional_by_regime:
            notional *= float(regime.risk_multiplier)
        if not math.isfinite(notional) or notional <= 0.0:
            return []
        qty = notional / features.current_close
        if not math.isfinite(qty) or qty <= 0.0:
            return []

        evidence_refs = self._build_core_evidence_refs(
            reason=signal_reason,
            decision=decision,
            score=score,
            state=state,
        )
        request = OrderRequest(
            symbol=symbol,
            side=MockOrderSide.BUY,
            order_type=MockOrderType.MARKET,
            requested_qty=qty,
            client_tag=f"core_strategy:{cfg.bridge_name}:{signal_reason}",
            evidence_refs=evidence_refs,
        )
        state.intent = _Intent.ENTRY_PENDING
        state.entry_signal_reason = signal_reason
        self._diagnostics.entry_signals += 1
        self._symbols_with_entry_signal.add(symbol)
        return [request]

    def _maybe_exit(
        self,
        *,
        symbol: str,
        state: _SymbolState,
        position: Any,
        simulated_time: datetime,
    ) -> List[OrderRequest]:
        cfg: CoreStrategyBridgeConfig = self._config  # type: ignore
        bars = list(state.bars)
        if not bars:
            return []
        current = bars[-1]
        entry_price = float(getattr(position, "avg_entry_price", 0.0) or 0.0)
        qty = float(getattr(position, "qty", 0.0) or 0.0)
        if qty <= 0.0:
            return []

        reason: Optional[str] = None
        # 1) Fixed risk controls (core risk path): take-profit, stop,
        #    and a hard time stop.
        if entry_price > 0.0:
            if current.close >= entry_price * (1.0 + cfg.take_profit_pct):
                reason = CoreStrategySignalReason.EXIT_TAKE_PROFIT
            elif current.close <= entry_price * (1.0 - cfg.stop_loss_pct):
                reason = CoreStrategySignalReason.EXIT_STOP_LOSS
        if reason is None and state.entry_bar_index is not None:
            bars_held = state.bars_seen - state.entry_bar_index
            if bars_held >= cfg.max_hold_bars:
                reason = CoreStrategySignalReason.EXIT_MAX_HOLD
        # 2) Core lifecycle exits: the regime turned to an outright
        #    no-trade veto, or the candidate's stage rolled over into
        #    blowoff / dumped. Both are as-of, deterministic, no future
        #    read.
        if reason is None:
            regime = self._current_regime
            if (
                regime is not None
                and str(regime.regime_name) in _REGIME_VETO_BUCKETS
            ):
                reason = CoreStrategySignalReason.EXIT_REGIME_RISK_OFF
        if reason is None:
            features = self._build_core_features(state)
            if (
                features is not None
                and str(features.stage.stage) in _STAGE_EXIT_BUCKETS
            ):
                reason = CoreStrategySignalReason.EXIT_STAGE_EXHAUSTED

        if reason is None:
            return []

        evidence_refs = self._build_core_evidence_refs(
            reason=reason,
            decision=None,
            score=None,
            state=state,
            bars=[current],
        )
        request = OrderRequest(
            symbol=symbol,
            side=MockOrderSide.SELL,
            order_type=MockOrderType.MARKET,
            requested_qty=qty,
            client_tag=f"core_strategy:{cfg.bridge_name}:{reason}",
            evidence_refs=evidence_refs,
        )
        state.intent = _Intent.EXIT_PENDING
        self._diagnostics.exit_signals += 1
        return [request]

    # ------------------------------------------------------------------
    # Internal: evidence refs
    # ------------------------------------------------------------------

    def _build_core_evidence_refs(
        self,
        *,
        reason: str,
        decision: Any,
        score: Any,
        state: _SymbolState,
        bars: Optional[Sequence[_ClosedBar]] = None,
    ) -> Tuple[str, ...]:
        """Build evidence refs for a core entry / exit signal.

        Refs only ever point at already-available, CLOSED bars (the
        rolling window the decision was derived from). The leading
        ``signal:`` ref carries the core mode / grade so a reviewer can
        trace which AMA-RT lifecycle branch fired.
        """
        refs: List[str] = [f"signal:{reason}"]
        if decision is not None:
            refs.append(f"core_mode:{decision.mode}")
        if score is not None:
            refs.append(f"core_grade:{score.grade}")
            refs.append(f"core_score:{round(float(score.score), 4)}")
        window_bars: Sequence[_ClosedBar]
        if bars is not None:
            window_bars = bars
        else:
            cfg: CoreStrategyBridgeConfig = self._config  # type: ignore
            all_bars = list(state.bars)
            window_bars = all_bars[-(cfg.breakout_lookback + 1):]
        for b in window_bars:
            refs.append(
                f"asof:{b.symbol}:{b.close_time.isoformat()}:{b.record_id}"
            )
        return tuple(refs)


__all__ = [
    "PHASE_NAME",
    "CORE_STRATEGY_PROFILE",
    "DEFAULT_CORE_BRIDGE_NAME",
    "DEFAULT_BRIDGE_NAME",
    "CoreStrategySignalReason",
    "CoreStrategyBridge",
    "CoreStrategyBridgeConfig",
]
