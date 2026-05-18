"""Real Trade Confirmation classifier (Phase 6 - Issue #6, Spec §20).

Maps each input snapshot to a :class:`TradeConfirmationLevel` from
T0 (no confirmation) to T4 (very strong confirmation). Each fired
signal contributes one point; the tier ladder is:

    0 signals  -> T0
    1 signal   -> T1
    2 signals  -> T2
    3 signals  -> T3
    4+ signals -> T4

Spec §20.4 lists T3 example conditions:

  - CVD and price agree direction across the recent window
  - breakout level held across >= 3 bars
  - large active buy followed by further upside
  - trade efficiency above the trailing mean

Phase 6 ships the classifier; the Risk Engine (this Phase) reads
:class:`TradeConfirmationLevel` and refuses to authorise an attack
candidate when the level is T0 / T1.
"""

from __future__ import annotations

from app.confirmation.models import (
    ConfirmationConfig,
    ConfirmationDecision,
    ConfirmationInput,
    ConfirmationBarSummary,
)
from app.core.clock import now_ms
from app.core.enums import (
    ConfirmationReasonTag,
    RiskPermission,
    TradeConfirmationLevel,
)
from app.core.events import Event, EventType
from app.core.models import MarketSnapshot
from app.database.repositories import EventRepository
from app.regime.models import RegimeSnapshot


class RealTradeConfirmation:
    """Stateless T0..T4 classifier."""

    SOURCE_MODULE = "confirmation.real_trade"

    def __init__(
        self,
        *,
        config: ConfirmationConfig | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._config = config or ConfirmationConfig()
        self._event_repo = event_repo
        self._evaluations = 0
        self._events_emitted = 0
        self._events_skipped = 0

    @property
    def config(self) -> ConfirmationConfig:
        return self._config

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def trade_confirmed_events_emitted(self) -> int:
        return self._events_emitted

    @property
    def trade_confirmed_events_skipped(self) -> int:
        return self._events_skipped

    # ------------------------------------------------------------------
    def evaluate(
        self,
        request: ConfirmationInput,
        *,
        emit_event: bool | None = None,
    ) -> ConfirmationDecision:
        cfg = self._config
        tags: list[ConfirmationReasonTag] = []
        notes: list[str] = []

        if (
            request.risk_permission is not None
            and request.risk_permission is RiskPermission.BLOCK_ALL
        ):
            tags.append(ConfirmationReasonTag.REGIME_BLOCKED)
            notes.append(f"risk_permission={request.risk_permission.value}")
            return self._finalise(
                request,
                level=TradeConfirmationLevel.T0,
                fired=0,
                tags=tuple(tags),
                notes=tuple(notes),
                emit_event=emit_event,
            )
        if request.is_data_degraded:
            tags.append(ConfirmationReasonTag.DATA_DEGRADED)
            notes.append("market_data_buffer reports degraded view")
            return self._finalise(
                request,
                level=TradeConfirmationLevel.T0,
                fired=0,
                tags=tuple(tags),
                notes=tuple(notes),
                emit_event=emit_event,
            )

        # 1. CVD-price agreement.
        return_for_alignment = request.return_pct_1m
        if (
            request.cvd_1m is not None
            and request.volume_1m > 0
            and return_for_alignment is not None
        ):
            cvd_strength = request.cvd_1m / max(request.volume_1m, 1e-12)
            if (
                abs(cvd_strength) >= cfg.cvd_alignment_min_strength
                and (cvd_strength > 0) == (return_for_alignment > 0)
                and abs(return_for_alignment) > 0
            ):
                tags.append(ConfirmationReasonTag.CVD_PRICE_AGREEMENT)
                notes.append(
                    f"cvd_strength={cvd_strength:.4f}"
                    f" return_pct_1m={return_for_alignment:.4f}"
                )

        # 2. Breakout hold.
        bars: tuple[ConfirmationBarSummary, ...] = request.last_n_closed_bars
        breakout_level = request.breakout_level
        if breakout_level is not None and len(bars) >= cfg.breakout_hold_min_bars:
            window = bars[-cfg.breakout_hold_min_bars :]
            if all(b.close >= breakout_level for b in window):
                tags.append(ConfirmationReasonTag.BREAKOUT_HELD)
                notes.append(
                    f"breakout_level={breakout_level:.6f}"
                    f" held_for={len(window)}bars"
                )

        # 3. Large-trade follow-through.
        if (
            request.largest_trade_qty_1m >= cfg.large_trade_qty_threshold
            and len(bars) >= cfg.large_trade_followthrough_bars + 1
        ):
            window = bars[-(cfg.large_trade_followthrough_bars + 1) :]
            higher_highs = all(
                window[i + 1].high >= window[i].high for i in range(len(window) - 1)
            )
            if higher_highs:
                tags.append(ConfirmationReasonTag.LARGE_TRADE_FOLLOW_THROUGH)
                notes.append(
                    f"largest_trade_qty={request.largest_trade_qty_1m:.4f}"
                    f" followthrough_bars={cfg.large_trade_followthrough_bars}"
                )

        # 4. Trade efficiency above mean.
        if (
            request.return_pct_1m is not None
            and request.volume_1m > 0
            and request.historical_efficiency_mean is not None
            and request.historical_efficiency_mean > 0
        ):
            current_eff = abs(request.return_pct_1m) / max(request.volume_1m, 1e-12)
            ratio = current_eff / request.historical_efficiency_mean
            if ratio >= cfg.trade_efficiency_relative_min:
                tags.append(ConfirmationReasonTag.TRADE_EFFICIENCY_HIGH)
                notes.append(f"efficiency_ratio={ratio:.3f}")

        # 5. Volume up + price move.
        baseline_volume_1m = request.volume_5m / 5.0 if request.volume_5m > 0 else 0.0
        if baseline_volume_1m > 0 and request.return_pct_1m is not None:
            volume_ratio = request.volume_1m / baseline_volume_1m
            if (
                volume_ratio >= cfg.volume_up_ratio
                and abs(request.return_pct_1m) >= cfg.min_price_move_pct
            ):
                tags.append(ConfirmationReasonTag.VOLUME_UP_PRICE_MOVE)
                notes.append(
                    f"volume_ratio={volume_ratio:.3f}"
                    f" return_pct_1m={request.return_pct_1m:.4f}"
                )

        fired = sum(
            1
            for t in tags
            if t
            not in (
                ConfirmationReasonTag.DATA_DEGRADED,
                ConfirmationReasonTag.REGIME_BLOCKED,
                ConfirmationReasonTag.INSUFFICIENT_HISTORY,
            )
        )
        level = _level_from_signal_count(fired)
        return self._finalise(
            request,
            level=level,
            fired=fired,
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
        return_pct_1m: float | None = None,
        return_pct_5m: float | None = None,
        breakout_level: float | None = None,
        last_n_closed_bars: tuple[ConfirmationBarSummary, ...] = (),
        largest_trade_qty_1m: float = 0.0,
        historical_efficiency_mean: float | None = None,
        regime: RegimeSnapshot | None = None,
        is_data_degraded: bool = False,
        emit_event: bool | None = None,
    ) -> ConfirmationDecision:
        request = ConfirmationInput(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            last_price=snapshot.last_price,
            prev_close_price=prev_close_price,
            cvd_1m=snapshot.cvd_1m,
            cvd_5m=snapshot.cvd_5m,
            volume_1m=snapshot.volume_1m,
            volume_5m=snapshot.volume_5m,
            return_pct_1m=return_pct_1m,
            return_pct_5m=return_pct_5m,
            breakout_level=breakout_level,
            last_n_closed_bars=last_n_closed_bars,
            largest_trade_qty_1m=largest_trade_qty_1m,
            historical_efficiency_mean=historical_efficiency_mean,
            is_data_degraded=is_data_degraded,
            market_regime=regime.market_regime if regime is not None else None,
            risk_permission=regime.risk_permission if regime is not None else None,
        )
        return self.evaluate(request, emit_event=emit_event)

    # ------------------------------------------------------------------
    def _finalise(
        self,
        request: ConfirmationInput,
        *,
        level: TradeConfirmationLevel,
        fired: int,
        tags: tuple[ConfirmationReasonTag, ...],
        notes: tuple[str, ...],
        emit_event: bool | None,
    ) -> ConfirmationDecision:
        decision = ConfirmationDecision(
            symbol=request.symbol,
            level=level,
            fired_signals=fired,
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
                    event_type=EventType.TRADE_CONFIRMED,
                    source_module=self.SOURCE_MODULE,
                    symbol=decision.symbol,
                    timestamp=decision.timestamp or now_ms(),
                    payload={
                        "symbol": decision.symbol,
                        "level": decision.level.value,
                        "fired_signals": decision.fired_signals,
                        "reason_tags": [t.value for t in decision.reason_tags],
                        "notes": list(decision.notes),
                        "last_price": request.last_price,
                        "prev_close_price": request.prev_close_price,
                        "return_pct_1m": request.return_pct_1m,
                        "return_pct_5m": request.return_pct_5m,
                        "cvd_1m": request.cvd_1m,
                        "volume_1m": request.volume_1m,
                        "volume_5m": request.volume_5m,
                        "breakout_level": request.breakout_level,
                        "largest_trade_qty_1m": request.largest_trade_qty_1m,
                        "historical_efficiency_mean": request.historical_efficiency_mean,
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


def _level_from_signal_count(n: int) -> TradeConfirmationLevel:
    """Map fired-signal count to T0..T4. 0=T0, 1=T1, 2=T2, 3=T3, 4+=T4."""
    if n <= 0:
        return TradeConfirmationLevel.T0
    if n == 1:
        return TradeConfirmationLevel.T1
    if n == 2:
        return TradeConfirmationLevel.T2
    if n == 3:
        return TradeConfirmationLevel.T3
    return TradeConfirmationLevel.T4
