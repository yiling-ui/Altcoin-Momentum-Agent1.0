"""Anomaly Scanner (Phase 6 - Issue #6, Spec §18).

Implements the Spec §18.2 weighted-sum formula:

    anomaly_score =
          OI_score        * 0.25
        + CVD_score       * 0.25
        + Volume_score    * 0.20
        + ATR_score       * 0.10
        + Funding_score   * 0.10
        + Liquidation_score * 0.10

Each component score is in [0, 1], the weighted sum is in [0, 1] and
the final score is scaled to [0, 100]. ``Sweep`` and
``Multi-Timeframe Breakout`` add small bonuses on top of the weighted
sum so a clean breakout cannot be missed when the underlying spikes
are not yet extreme.

**``anomaly_score`` is an ANOMALY INDICATOR only, NOT an entry
signal.** A high score does NOT authorise opening a position. The
scanner returns an :class:`AnomalyDecision` (`anomaly_score` +
`reason_tags` + `notes`) and optionally emits a single
``ANOMALY_DETECTED`` event - that is its complete public contract.
It NEVER constructs an :class:`app.core.models.TradeDecision`,
NEVER enqueues an order, NEVER mutates any position. Real openings
remain gated by the Phase 5 regime / universe / liquidity contract,
the Phase 6 confirmation tier (T2+ for ATTACK), the Phase 6
manipulation tier (M0 / M1 for ATTACK), the Phase 7 Risk Engine and
No-Trade Gate, and the Phase 9 Execution FSM.

Phase 6 boundary: same as :class:`PreAnomalyScanner`. Stateless, no
network, no orders, no LLM. One event per evaluation.
"""

from __future__ import annotations

from app.core.clock import now_ms
from app.core.enums import AnomalyReasonTag, RiskPermission
from app.core.events import Event, EventType
from app.core.models import MarketSnapshot
from app.database.repositories import EventRepository
from app.regime.models import RegimeSnapshot
from app.scanner.models import AnomalyConfig, AnomalyDecision, AnomalyInput


def _sat(value: float, threshold: float) -> float:
    """Saturating component score: 0 at <= 0, 1 at >= threshold,
    linear in between. Used for every Spec §18 dimension."""
    if threshold <= 0:
        return 0.0 if value <= 0 else 1.0
    if value <= 0:
        return 0.0
    return min(value / threshold, 1.0)


class AnomalyScanner:
    """Stateless Anomaly classifier."""

    SOURCE_MODULE = "scanner.anomaly"

    def __init__(
        self,
        *,
        config: AnomalyConfig | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._config = config or AnomalyConfig()
        self._event_repo = event_repo
        self._evaluations = 0
        self._events_emitted = 0
        self._events_skipped = 0

    @property
    def config(self) -> AnomalyConfig:
        return self._config

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def anomaly_events_emitted(self) -> int:
        return self._events_emitted

    @property
    def anomaly_events_skipped(self) -> int:
        return self._events_skipped

    # ------------------------------------------------------------------
    def evaluate(
        self,
        request: AnomalyInput,
        *,
        emit_event: bool | None = None,
    ) -> AnomalyDecision:
        cfg = self._config
        tags: list[AnomalyReasonTag] = []
        notes: list[str] = []
        component_scores: dict[str, float] = {
            "oi": 0.0,
            "cvd": 0.0,
            "volume": 0.0,
            "atr": 0.0,
            "funding": 0.0,
            "liquidation": 0.0,
        }

        if (
            request.risk_permission is not None
            and request.risk_permission is RiskPermission.BLOCK_ALL
        ):
            tags.append(AnomalyReasonTag.REGIME_BLOCKED)
            notes.append(
                f"risk_permission={request.risk_permission.value}"
            )
            return self._finalise(
                request,
                score=0.0,
                tags=tuple(tags),
                notes=tuple(notes),
                component_scores=component_scores,
                emit_event=emit_event,
            )
        if request.is_data_degraded:
            tags.append(AnomalyReasonTag.DATA_DEGRADED)
            notes.append("market_data_buffer reports degraded view")
            return self._finalise(
                request,
                score=0.0,
                tags=tuple(tags),
                notes=tuple(notes),
                component_scores=component_scores,
                emit_event=emit_event,
            )

        # 1. OI spike.
        if (
            request.oi is not None
            and request.prev_oi is not None
            and request.prev_oi > 0
        ):
            oi_ret = (request.oi / request.prev_oi) - 1.0
            component_scores["oi"] = _sat(oi_ret, cfg.oi_spike_pct)
            if oi_ret >= cfg.oi_spike_pct:
                tags.append(AnomalyReasonTag.OI_SPIKE)
                notes.append(f"oi_return={oi_ret:.4f}")

        # 2. CVD spike: cvd_1m vs cvd_5m baseline (per-minute).
        if request.cvd_1m is not None and request.cvd_5m is not None:
            baseline_cvd_1m = abs(request.cvd_5m) / 5.0
            if baseline_cvd_1m > 0:
                ratio = abs(request.cvd_1m) / baseline_cvd_1m
                component_scores["cvd"] = _sat(ratio, cfg.cvd_spike_ratio)
                if ratio >= cfg.cvd_spike_ratio:
                    tags.append(AnomalyReasonTag.CVD_SPIKE)
                    notes.append(f"cvd_ratio_1m_vs_baseline={ratio:.3f}")
            else:
                # cvd_5m is zero but cvd_1m is large: count as full hit.
                if abs(request.cvd_1m) > 0:
                    component_scores["cvd"] = 1.0
                    tags.append(AnomalyReasonTag.CVD_SPIKE)
                    notes.append("cvd_1m positive while cvd_5m=0")

        # 3. Volume spike.
        baseline_volume_1m = request.volume_5m / 5.0 if request.volume_5m > 0 else 0.0
        if baseline_volume_1m > 0:
            ratio = request.volume_1m / baseline_volume_1m
            component_scores["volume"] = _sat(ratio, cfg.volume_spike_ratio)
            if ratio >= cfg.volume_spike_ratio:
                tags.append(AnomalyReasonTag.VOLUME_SPIKE)
                notes.append(f"volume_ratio={ratio:.3f}")

        # 4. ATR expansion.
        if (
            request.atr_1m is not None
            and request.atr_5m is not None
            and request.atr_5m > 0
        ):
            ratio = request.atr_1m / request.atr_5m
            component_scores["atr"] = _sat(ratio, cfg.atr_expansion_ratio)
            if ratio >= cfg.atr_expansion_ratio:
                tags.append(AnomalyReasonTag.ATR_EXPANSION)
                notes.append(f"atr_ratio_1m_vs_5m={ratio:.3f}")

        # 5. Funding extreme (absolute).
        if request.funding_rate is not None:
            magnitude = abs(request.funding_rate)
            component_scores["funding"] = _sat(magnitude, cfg.funding_extreme_pct)
            if magnitude >= cfg.funding_extreme_pct:
                tags.append(AnomalyReasonTag.FUNDING_EXTREME)
                notes.append(f"funding_rate={request.funding_rate:.6f}")

        # 6. Liquidation spike.
        component_scores["liquidation"] = _sat(
            request.liquidations_qty_1m, cfg.liquidation_spike_qty
        )
        if request.liquidations_qty_1m >= cfg.liquidation_spike_qty:
            tags.append(AnomalyReasonTag.LIQUIDATION_SPIKE)
            notes.append(f"liquidations_qty_1m={request.liquidations_qty_1m:.4f}")

        # Weighted sum (0..1).
        weighted = (
            component_scores["oi"] * cfg.weight_oi
            + component_scores["cvd"] * cfg.weight_cvd
            + component_scores["volume"] * cfg.weight_volume
            + component_scores["atr"] * cfg.weight_atr
            + component_scores["funding"] * cfg.weight_funding
            + component_scores["liquidation"] * cfg.weight_liquidation
        )
        # Scale to [0, 100].
        score = weighted * cfg.score_ceiling

        # 7. Sweep bonus.
        if request.sweep_legs >= cfg.sweep_min_legs:
            tags.append(AnomalyReasonTag.SWEEP)
            notes.append(f"sweep_legs={request.sweep_legs}")
            score += cfg.weight_sweep_bonus

        # 8. Multi-timeframe breakout bonus: last price tops every
        # supplied higher-timeframe high.
        if cfg.multi_timeframe_breakout_required and request.last_price is not None:
            highs = [
                h
                for h in (request.high_5m, request.high_15m, request.high_1h)
                if h is not None and h > 0
            ]
            if len(highs) >= 2 and all(request.last_price > h for h in highs):
                tags.append(AnomalyReasonTag.MULTI_TIMEFRAME_BREAKOUT)
                notes.append(
                    "last_price > "
                    + ", ".join(f"{h:.6f}" for h in highs)
                )
                score += cfg.weight_breakout_bonus

        score = max(0.0, min(score, cfg.score_ceiling))
        return self._finalise(
            request,
            score=score,
            tags=tuple(tags),
            notes=tuple(notes),
            component_scores=component_scores,
            emit_event=emit_event,
        )

    # ------------------------------------------------------------------
    def evaluate_snapshot(
        self,
        snapshot: MarketSnapshot,
        *,
        prev_oi: float | None = None,
        prev_close_price: float | None = None,
        high_5m: float | None = None,
        high_15m: float | None = None,
        high_1h: float | None = None,
        liquidations_qty_1m: float = 0.0,
        sweep_legs: int = 0,
        regime: RegimeSnapshot | None = None,
        is_data_degraded: bool = False,
        emit_event: bool | None = None,
    ) -> AnomalyDecision:
        request = AnomalyInput(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            last_price=snapshot.last_price,
            prev_close_price=prev_close_price,
            high_5m=high_5m,
            high_15m=high_15m,
            high_1h=high_1h,
            spread_pct=snapshot.spread_pct,
            volume_1m=snapshot.volume_1m,
            volume_5m=snapshot.volume_5m,
            cvd_1m=snapshot.cvd_1m,
            cvd_5m=snapshot.cvd_5m,
            atr_1m=snapshot.atr_1m,
            atr_5m=snapshot.atr_5m,
            oi=snapshot.oi,
            prev_oi=prev_oi,
            funding_rate=snapshot.funding_rate,
            liquidations_qty_1m=liquidations_qty_1m,
            sweep_legs=sweep_legs,
            is_data_degraded=is_data_degraded,
            market_regime=regime.market_regime if regime is not None else None,
            risk_permission=regime.risk_permission if regime is not None else None,
        )
        return self.evaluate(request, emit_event=emit_event)

    # ------------------------------------------------------------------
    def _finalise(
        self,
        request: AnomalyInput,
        *,
        score: float,
        tags: tuple[AnomalyReasonTag, ...],
        notes: tuple[str, ...],
        component_scores: dict[str, float],
        emit_event: bool | None,
    ) -> AnomalyDecision:
        decision = AnomalyDecision(
            symbol=request.symbol,
            anomaly_score=float(score),
            reason_tags=tags,
            notes=notes,
            timestamp=request.timestamp if request.timestamp is not None else now_ms(),
        )
        self._evaluations += 1
        should_emit = (
            emit_event if emit_event is not None else self._config.event_emit_enabled
        )
        if should_emit and self._event_repo is not None:
            self._event_repo.append_event(
                Event(
                    event_type=EventType.ANOMALY_DETECTED,
                    source_module=self.SOURCE_MODULE,
                    symbol=decision.symbol,
                    timestamp=decision.timestamp or now_ms(),
                    payload={
                        "symbol": decision.symbol,
                        "anomaly_score": decision.anomaly_score,
                        "reason_tags": [t.value for t in decision.reason_tags],
                        "notes": list(decision.notes),
                        "component_scores": dict(component_scores),
                        "weights": {
                            "oi": self._config.weight_oi,
                            "cvd": self._config.weight_cvd,
                            "volume": self._config.weight_volume,
                            "atr": self._config.weight_atr,
                            "funding": self._config.weight_funding,
                            "liquidation": self._config.weight_liquidation,
                        },
                        "last_price": request.last_price,
                        "volume_1m": request.volume_1m,
                        "volume_5m": request.volume_5m,
                        "cvd_1m": request.cvd_1m,
                        "atr_1m": request.atr_1m,
                        "atr_5m": request.atr_5m,
                        "oi": request.oi,
                        "prev_oi": request.prev_oi,
                        "funding_rate": request.funding_rate,
                        "liquidations_qty_1m": request.liquidations_qty_1m,
                        "sweep_legs": request.sweep_legs,
                        "is_data_degraded": request.is_data_degraded,
                        "market_regime": (
                            request.market_regime.value
                            if request.market_regime
                            else None
                        ),
                        "risk_permission": (
                            request.risk_permission.value
                            if request.risk_permission
                            else None
                        ),
                    },
                )
            )
            self._events_emitted += 1
        else:
            self._events_skipped += 1
        return decision
