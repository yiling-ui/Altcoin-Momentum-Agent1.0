"""Pre-Anomaly Scanner (Phase 6 - Issue #6, Spec §17).

Goal (Spec §17.1): "发现还没刷屏但正在变强的标的." -- find symbols
that are gathering momentum but have not yet fully exploded. Each
fired reason adds points; the final score is bounded at 100.

Phase 6 boundary
----------------

The scanner is **stateless** and **pure**: it never opens a socket,
never places an order, never imports an LLM. It consumes
:class:`PreAnomalyInput` (or assembles one from the Phase 4 buffer +
Phase 5 :class:`RegimeSnapshot` for the boot path) and emits exactly
one ``PRE_ANOMALY_DETECTED`` event per evaluation.
"""

from __future__ import annotations

from app.core.clock import now_ms
from app.core.enums import (
    MarketRegime,
    PreAnomalyReasonTag,
    RiskPermission,
)
from app.core.events import Event, EventType
from app.core.models import MarketSnapshot
from app.database.repositories import EventRepository
from app.regime.models import RegimeSnapshot
from app.scanner.models import (
    PreAnomalyConfig,
    PreAnomalyDecision,
    PreAnomalyInput,
)


class PreAnomalyScanner:
    """Stateless Pre-Anomaly classifier."""

    SOURCE_MODULE = "scanner.pre_anomaly"

    def __init__(
        self,
        *,
        config: PreAnomalyConfig | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._config = config or PreAnomalyConfig()
        self._event_repo = event_repo
        self._evaluations = 0
        self._events_emitted = 0
        self._events_skipped = 0

    # ------------------------------------------------------------------
    @property
    def config(self) -> PreAnomalyConfig:
        return self._config

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def pre_anomaly_events_emitted(self) -> int:
        return self._events_emitted

    @property
    def pre_anomaly_events_skipped(self) -> int:
        """Decisions whose ``PRE_ANOMALY_DETECTED`` event was suppressed
        by the per-call override or the
        :attr:`PreAnomalyConfig.event_emit_enabled` flag. Mirrors the
        Phase 5 PR #16 review-fix observability."""
        return self._events_skipped

    # ------------------------------------------------------------------
    def evaluate(
        self,
        request: PreAnomalyInput,
        *,
        emit_event: bool | None = None,
    ) -> PreAnomalyDecision:
        cfg = self._config
        tags: list[PreAnomalyReasonTag] = []
        notes: list[str] = []

        # Hard guards. We still emit the event so events.db carries the
        # rejection.
        if (
            request.risk_permission is not None
            and request.risk_permission is RiskPermission.BLOCK_ALL
        ):
            tags.append(PreAnomalyReasonTag.REGIME_BLOCKED)
            notes.append(
                f"risk_permission={request.risk_permission.value}"
                + (
                    f" market_regime={request.market_regime.value}"
                    if request.market_regime is not None
                    else ""
                )
            )
            return self._finalise(
                request,
                score=0.0,
                tags=tuple(tags),
                notes=tuple(notes),
                emit_event=emit_event,
            )
        if request.is_data_degraded:
            tags.append(PreAnomalyReasonTag.DATA_DEGRADED)
            notes.append("market_data_buffer reports degraded view")
            return self._finalise(
                request,
                score=0.0,
                tags=tuple(tags),
                notes=tuple(notes),
                emit_event=emit_event,
            )
        if request.volume_5m <= 0 or request.last_price is None:
            tags.append(PreAnomalyReasonTag.INSUFFICIENT_HISTORY)
            notes.append("volume_5m=0 or last_price missing")
            return self._finalise(
                request,
                score=0.0,
                tags=tuple(tags),
                notes=tuple(notes),
                emit_event=emit_event,
            )

        # 1. Volume base-expansion: gentle (>= ratio AND < explosive).
        baseline_volume_1m = request.volume_5m / 5.0
        if baseline_volume_1m > 0:
            ratio = request.volume_1m / baseline_volume_1m
            if cfg.volume_base_expansion_ratio <= ratio < cfg.volume_explosive_ratio:
                tags.append(PreAnomalyReasonTag.VOLUME_BASE_EXPANSION)
                notes.append(
                    f"volume_ratio_1m_vs_5m={ratio:.3f}"
                )

        # 2. Spread compression.
        if request.spread_pct is not None and request.spread_pct >= 0:
            baseline = request.baseline_spread_pct
            if baseline is None or baseline <= 0:
                # Without a baseline we treat spread compression
                # conservatively: only fire if spread is clearly small.
                if request.spread_pct < 0.001:
                    tags.append(PreAnomalyReasonTag.SPREAD_COMPRESSION)
                    notes.append(f"spread_pct={request.spread_pct:.6f}")
            elif request.spread_pct <= baseline * cfg.spread_compression_ratio:
                tags.append(PreAnomalyReasonTag.SPREAD_COMPRESSION)
                notes.append(
                    f"spread_pct={request.spread_pct:.6f}"
                    f" <= baseline*{cfg.spread_compression_ratio:.2f}"
                    f" ({baseline * cfg.spread_compression_ratio:.6f})"
                )

        # 3. Buy pressure (CVD as fraction of volume).
        if request.cvd_1m is not None and request.volume_1m > 0:
            ratio = request.cvd_1m / max(request.volume_1m, 1e-12)
            if ratio >= cfg.buy_pressure_ratio:
                tags.append(PreAnomalyReasonTag.BUY_PRESSURE_RISING)
                notes.append(f"cvd_1m_ratio={ratio:.3f}")

        # 4. OI soft rise.
        if request.oi is not None and request.prev_oi is not None and request.prev_oi > 0:
            oi_ret = (request.oi / request.prev_oi) - 1.0
            if cfg.oi_soft_rise_min <= oi_ret <= cfg.oi_soft_rise_max:
                tags.append(PreAnomalyReasonTag.OI_SOFT_RISE)
                notes.append(f"oi_return={oi_ret:.4f}")

        # 5. Funding not overheated.
        if request.funding_rate is not None:
            if abs(request.funding_rate) <= cfg.funding_overheating_pct:
                tags.append(PreAnomalyReasonTag.FUNDING_NOT_OVERHEATED)
                notes.append(f"funding_rate={request.funding_rate:.6f}")

        # 6. Minor uptrend.
        if (
            request.last_price is not None
            and request.prev_close_price is not None
            and request.prev_close_price > 0
        ):
            ret = (request.last_price / request.prev_close_price) - 1.0
            if (
                cfg.minor_uptrend_min_return_pct
                <= ret
                <= cfg.minor_uptrend_max_return_pct
            ):
                tags.append(PreAnomalyReasonTag.MINOR_UPTREND)
                notes.append(f"return_pct={ret:.4f}")

        score = min(len(tags) * cfg.points_per_tag, cfg.points_ceiling)
        return self._finalise(
            request,
            score=score,
            tags=tuple(tags),
            notes=tuple(notes),
            emit_event=emit_event,
        )

    # ------------------------------------------------------------------
    def evaluate_snapshot(
        self,
        snapshot: MarketSnapshot,
        *,
        prev_close_price: float | None = None,
        prev_oi: float | None = None,
        baseline_spread_pct: float | None = None,
        regime: RegimeSnapshot | None = None,
        is_data_degraded: bool = False,
        emit_event: bool | None = None,
    ) -> PreAnomalyDecision:
        request = PreAnomalyInput(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            last_price=snapshot.last_price,
            prev_close_price=prev_close_price,
            spread_pct=snapshot.spread_pct,
            baseline_spread_pct=baseline_spread_pct,
            volume_1m=snapshot.volume_1m,
            volume_5m=snapshot.volume_5m,
            cvd_1m=snapshot.cvd_1m,
            cvd_5m=snapshot.cvd_5m,
            oi=snapshot.oi,
            prev_oi=prev_oi,
            funding_rate=snapshot.funding_rate,
            is_data_degraded=is_data_degraded,
            market_regime=regime.market_regime if regime is not None else None,
            risk_permission=regime.risk_permission if regime is not None else None,
        )
        return self.evaluate(request, emit_event=emit_event)

    # ------------------------------------------------------------------
    def _finalise(
        self,
        request: PreAnomalyInput,
        *,
        score: float,
        tags: tuple[PreAnomalyReasonTag, ...],
        notes: tuple[str, ...],
        emit_event: bool | None,
    ) -> PreAnomalyDecision:
        decision = PreAnomalyDecision(
            symbol=request.symbol,
            pre_anomaly_score=float(score),
            reason_tags=tags,
            notes=notes,
            timestamp=request.timestamp if request.timestamp is not None else now_ms(),
        )
        self._evaluations += 1
        # Resolve event-emission policy (mirror Phase 5 PR #16 review fix):
        #   emit_event=True  -> always emit (per-call override)
        #   emit_event=False -> always skip (per-call override)
        #   emit_event=None  -> follow self._config.event_emit_enabled
        should_emit = (
            emit_event if emit_event is not None else self._config.event_emit_enabled
        )
        if should_emit and self._event_repo is not None:
            self._event_repo.append_event(
                Event(
                    event_type=EventType.PRE_ANOMALY_DETECTED,
                    source_module=self.SOURCE_MODULE,
                    symbol=decision.symbol,
                    timestamp=decision.timestamp or now_ms(),
                    payload={
                        "symbol": decision.symbol,
                        "pre_anomaly_score": decision.pre_anomaly_score,
                        "reason_tags": [t.value for t in decision.reason_tags],
                        "notes": list(decision.notes),
                        "last_price": request.last_price,
                        "prev_close_price": request.prev_close_price,
                        "spread_pct": request.spread_pct,
                        "volume_1m": request.volume_1m,
                        "volume_5m": request.volume_5m,
                        "cvd_1m": request.cvd_1m,
                        "oi": request.oi,
                        "prev_oi": request.prev_oi,
                        "funding_rate": request.funding_rate,
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
