"""Manipulation Detector (Phase 6 - Issue #6, Spec §21).

Maps an input snapshot to a :class:`ManipulationLevel` from M0 (no
manipulation) to M3 (heavy manipulation). Each fired signal
contributes one point; the tier ladder is:

    0 signals  -> M0
    1 signal   -> M1
    2 signals  -> M2
    3+ signals -> M3

Phase 6 hard rules (Issue #6):

  - M2: forbid ATTACK / RIGHT_TAIL_AMPLIFY (Risk Engine enforces).
  - M3: forbid any new opening (Risk Engine enforces).

The detector is **stateless**, runs entirely on already-collected
metrics, never opens a socket, never places an order, never calls an
LLM.
"""

from __future__ import annotations

from app.core.clock import now_ms
from app.core.enums import (
    ManipulationLevel,
    ManipulationReasonTag,
    RiskPermission,
)
from app.core.events import Event, EventType
from app.core.models import MarketSnapshot
from app.database.repositories import EventRepository
from app.confirmation.models import ConfirmationBarSummary
from app.manipulation.models import (
    ManipulationConfig,
    ManipulationDecision,
    ManipulationInput,
)
from app.regime.models import RegimeSnapshot


class ManipulationDetector:
    """Stateless M0..M3 classifier."""

    SOURCE_MODULE = "manipulation.detector"

    def __init__(
        self,
        *,
        config: ManipulationConfig | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._config = config or ManipulationConfig()
        self._event_repo = event_repo
        self._evaluations = 0
        self._events_emitted = 0
        self._events_skipped = 0

    @property
    def config(self) -> ManipulationConfig:
        return self._config

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def manipulation_events_emitted(self) -> int:
        return self._events_emitted

    @property
    def manipulation_events_skipped(self) -> int:
        return self._events_skipped

    # ------------------------------------------------------------------
    def evaluate(
        self,
        request: ManipulationInput,
        *,
        emit_event: bool | None = None,
    ) -> ManipulationDecision:
        cfg = self._config
        tags: list[ManipulationReasonTag] = []
        notes: list[str] = []

        if (
            request.risk_permission is not None
            and request.risk_permission is RiskPermission.BLOCK_ALL
        ):
            tags.append(ManipulationReasonTag.REGIME_BLOCKED)
            notes.append(f"risk_permission={request.risk_permission.value}")
            # Treat regime block as M0 - the regime gate already stops
            # trading; manipulation level itself is not promoted by
            # something orthogonal.
            return self._finalise(
                request,
                level=ManipulationLevel.M0,
                fired=0,
                tags=tuple(tags),
                notes=tuple(notes),
                emit_event=emit_event,
            )
        if request.is_data_degraded:
            tags.append(ManipulationReasonTag.DATA_DEGRADED)
            notes.append("market_data_buffer reports degraded view")
            return self._finalise(
                request,
                level=ManipulationLevel.M0,
                fired=0,
                tags=tuple(tags),
                notes=tuple(notes),
                emit_event=emit_event,
            )

        ret_for_flat = (
            request.return_pct_1m
            if request.return_pct_1m is not None
            else request.return_pct_5m
        )

        # 1. CVD up but price flat (Spec §21.2 CVD-price divergence).
        if (
            request.cvd_1m is not None
            and request.volume_1m > 0
            and ret_for_flat is not None
        ):
            cvd_strength = request.cvd_1m / max(request.volume_1m, 1e-12)
            if (
                cvd_strength >= cfg.cvd_strength_min
                and abs(ret_for_flat) <= cfg.flat_return_pct
            ):
                tags.append(ManipulationReasonTag.CVD_UP_PRICE_FLAT)
                notes.append(
                    f"cvd_strength={cvd_strength:.4f}"
                    f" return={ret_for_flat:.4f}"
                )
                # The buy-pressure-no-push tag fires in the same
                # condition family but at a higher CVD bar - it
                # represents an even more extreme divergence.
                if cvd_strength >= cfg.buy_pressure_no_push_cvd_min:
                    tags.append(ManipulationReasonTag.BUY_PRESSURE_NO_PUSH)

        # 2. Volume up + price no move.
        baseline_volume_1m = request.volume_5m / 5.0 if request.volume_5m > 0 else 0.0
        if (
            baseline_volume_1m > 0
            and request.return_pct_1m is not None
            and request.volume_1m > 0
        ):
            ratio = request.volume_1m / baseline_volume_1m
            if (
                ratio >= cfg.volume_up_ratio
                and abs(request.return_pct_1m) <= cfg.flat_return_pct
            ):
                tags.append(ManipulationReasonTag.VOLUME_UP_PRICE_NO_MOVE)
                notes.append(
                    f"volume_ratio={ratio:.3f}"
                    f" return_pct_1m={request.return_pct_1m:.4f}"
                )

        # 3. OI up + price flat.
        if (
            request.oi is not None
            and request.prev_oi is not None
            and request.prev_oi > 0
            and ret_for_flat is not None
        ):
            oi_ret = (request.oi / request.prev_oi) - 1.0
            if oi_ret >= cfg.oi_up_pct and abs(ret_for_flat) <= cfg.flat_return_pct:
                tags.append(ManipulationReasonTag.OI_UP_PRICE_FLAT)
                notes.append(
                    f"oi_return={oi_ret:.4f}"
                    f" return={ret_for_flat:.4f}"
                )

        # 4. Funding hot + price weak.
        if request.funding_rate is not None and ret_for_flat is not None:
            if (
                abs(request.funding_rate) >= cfg.funding_hot_pct
                and abs(ret_for_flat) <= cfg.weak_return_pct
            ):
                tags.append(ManipulationReasonTag.FUNDING_HOT_PRICE_WEAK)
                notes.append(
                    f"funding_rate={request.funding_rate:.6f}"
                    f" return={ret_for_flat:.4f}"
                )

        # 5. Upper-wick growth across the recent window.
        bars = request.last_n_closed_bars
        n_window = min(cfg.upper_wick_window, len(bars))
        if n_window > 0:
            wick_window = bars[-n_window:]
            fractions: list[float] = []
            for b in wick_window:
                rng = b.high - b.low
                if rng <= 0:
                    continue
                top_of_body = max(b.open, b.close)
                wick = max(b.high - top_of_body, 0.0)
                fractions.append(wick / rng)
            if fractions:
                avg = sum(fractions) / len(fractions)
                if avg >= cfg.upper_wick_min_fraction:
                    tags.append(ManipulationReasonTag.UPPER_WICK_GROWTH)
                    notes.append(
                        f"upper_wick_avg_fraction={avg:.3f} window={n_window}"
                    )

        # 6. Book-wall flicker (caller-supplied count).
        if request.book_wall_flicker_count >= cfg.book_wall_flicker_min:
            tags.append(ManipulationReasonTag.BOOK_WALL_FLICKER)
            notes.append(
                f"book_wall_flicker_count={request.book_wall_flicker_count}"
            )

        # 7. Narrative after pump.
        if request.narrative_after_pump:
            tags.append(ManipulationReasonTag.NARRATIVE_AFTER_PUMP)
            notes.append("narrative_after_pump=true")

        # Tier mapping: count signals (skip non-blocking diagnostics).
        signal_tags = {
            ManipulationReasonTag.CVD_UP_PRICE_FLAT,
            ManipulationReasonTag.VOLUME_UP_PRICE_NO_MOVE,
            ManipulationReasonTag.OI_UP_PRICE_FLAT,
            ManipulationReasonTag.FUNDING_HOT_PRICE_WEAK,
            ManipulationReasonTag.UPPER_WICK_GROWTH,
            ManipulationReasonTag.BUY_PRESSURE_NO_PUSH,
            ManipulationReasonTag.BOOK_WALL_FLICKER,
            ManipulationReasonTag.NARRATIVE_AFTER_PUMP,
        }
        fired = sum(1 for t in tags if t in signal_tags)
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
        return_pct_1m: float | None = None,
        return_pct_5m: float | None = None,
        prev_close_price: float | None = None,
        prev_oi: float | None = None,
        last_n_closed_bars: tuple[ConfirmationBarSummary, ...] = (),
        narrative_after_pump: bool = False,
        book_wall_flicker_count: int = 0,
        regime: RegimeSnapshot | None = None,
        is_data_degraded: bool = False,
        emit_event: bool | None = None,
    ) -> ManipulationDecision:
        request = ManipulationInput(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            last_price=snapshot.last_price,
            prev_close_price=prev_close_price,
            return_pct_1m=return_pct_1m,
            return_pct_5m=return_pct_5m,
            spread_pct=snapshot.spread_pct,
            volume_1m=snapshot.volume_1m,
            volume_5m=snapshot.volume_5m,
            cvd_1m=snapshot.cvd_1m,
            cvd_5m=snapshot.cvd_5m,
            oi=snapshot.oi,
            prev_oi=prev_oi,
            funding_rate=snapshot.funding_rate,
            last_n_closed_bars=last_n_closed_bars,
            narrative_after_pump=narrative_after_pump,
            book_wall_flicker_count=book_wall_flicker_count,
            is_data_degraded=is_data_degraded,
            market_regime=regime.market_regime if regime is not None else None,
            risk_permission=regime.risk_permission if regime is not None else None,
        )
        return self.evaluate(request, emit_event=emit_event)

    # ------------------------------------------------------------------
    def _finalise(
        self,
        request: ManipulationInput,
        *,
        level: ManipulationLevel,
        fired: int,
        tags: tuple[ManipulationReasonTag, ...],
        notes: tuple[str, ...],
        emit_event: bool | None,
    ) -> ManipulationDecision:
        decision = ManipulationDecision(
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
                    event_type=EventType.MANIPULATION_DETECTED,
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
                        "return_pct_1m": request.return_pct_1m,
                        "return_pct_5m": request.return_pct_5m,
                        "volume_1m": request.volume_1m,
                        "volume_5m": request.volume_5m,
                        "cvd_1m": request.cvd_1m,
                        "oi": request.oi,
                        "prev_oi": request.prev_oi,
                        "funding_rate": request.funding_rate,
                        "narrative_after_pump": request.narrative_after_pump,
                        "book_wall_flicker_count": request.book_wall_flicker_count,
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


def _level_from_signal_count(n: int) -> ManipulationLevel:
    """Map fired-signal count to M0..M3. 0=M0, 1=M1, 2=M2, 3+=M3."""
    if n <= 0:
        return ManipulationLevel.M0
    if n == 1:
        return ManipulationLevel.M1
    if n == 2:
        return ManipulationLevel.M2
    return ManipulationLevel.M3
