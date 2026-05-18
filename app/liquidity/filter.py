"""Liquidity Filter (Phase 5 - Issue #5).

Spec §19. The filter takes a :class:`LiquidityInput` (or assembles
one from the Phase 4 buffer + Phase 3 gateway) and produces a
:class:`LiquidityDecision`. The mandatory
:meth:`LiquidityFilter.can_exit_position` (Spec §19.2) is exposed as
both an instance method and a free function so the Risk Engine
(Issue #7) can call it without instantiating a filter.

Phase 5 boundary: the filter never places, modifies, or cancels an
order. It never reads an API key. It never opens a socket. It only
walks the order book in memory and emits one ``LIQUIDITY_CHECKED``
event per evaluation.
"""

from __future__ import annotations

from app.core.clock import now_ms
from app.core.enums import (
    LiquidityRejectReason,
    MarketRegime,
    RiskPermission,
)
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.exchanges.models import OrderBook
from app.liquidity.models import (
    ExitPlan,
    LiquidityConfig,
    LiquidityDecision,
    LiquidityInput,
    Side,
)
from app.liquidity.slippage import estimate_book_walk
from app.regime.models import RegimeSnapshot

# Length of the Phase 4 5-minute volume window in seconds. Used as
# the denominator for the throughput-from-volume fallback in
# can_exit_position.
#
# IMPORTANT: ``volume_5m / _VOLUME_WINDOW_5M_SECONDS`` is the *upper
# bound* on instantaneous capacity, not a conservative estimate. It
# assumes:
#   1. The next 5 minutes will print at the same pace as the previous
#      5 minutes.
#   2. Every realised trade in that window is interchangeable with our
#      own outflow (i.e. the rest of the tape will not crowd our exit
#      price).
#   3. ATR / OI / volatility do not expand into our exit window.
#
# None of these assumptions hold in a thinning or panicking tape. The
# 5x ``min_depth_multiplier`` cushion in :class:`LiquidityConfig` is
# what keeps this safe under normal regimes; the throughput value
# itself is permissive. **Issue #7's Risk Engine MUST apply a
# conservative discount** on top of any value derived from this
# constant before sizing an attack candidate. See the can_exit_position
# docstring for the recommended discount directions.
_VOLUME_WINDOW_5M_SECONDS = 5 * 60


class LiquidityFilter:
    """Stateless liquidity gate."""

    SOURCE_MODULE = "liquidity.filter"

    def __init__(
        self,
        *,
        config: LiquidityConfig | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._config = config or LiquidityConfig()
        self._event_repo = event_repo
        self._evaluations: int = 0
        self._exit_checks: int = 0
        self._liquidity_checked_emitted: int = 0
        self._liquidity_checked_skipped: int = 0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def config(self) -> LiquidityConfig:
        return self._config

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def exit_checks(self) -> int:
        return self._exit_checks

    @property
    def liquidity_checked_events_emitted(self) -> int:
        return self._liquidity_checked_emitted

    @property
    def liquidity_checked_events_skipped(self) -> int:
        """Number of decisions that were NOT persisted because the
        per-call override or the :attr:`LiquidityConfig.event_emit_enabled`
        config flag suppressed them. Phase 4 PR #15 review fix shape:
        observability for the throttle itself.
        """
        return self._liquidity_checked_skipped

    # ------------------------------------------------------------------
    # evaluate (Spec §19.1)
    # ------------------------------------------------------------------
    def evaluate(
        self, request: LiquidityInput, *, emit_event: bool | None = None
    ) -> LiquidityDecision:
        cfg = self._config
        reasons: list[LiquidityRejectReason] = []
        notes: list[str] = []

        # 1. Regime gate (Phase 5 hard rule 1).
        if (
            request.risk_permission is not None
            and request.risk_permission in cfg.blocking_risk_permissions
        ):
            reasons.append(LiquidityRejectReason.REGIME_BLOCKED)
            notes.append(
                f"risk_permission={request.risk_permission.value}"
                + (
                    f" market_regime={request.market_regime.value}"
                    if request.market_regime is not None
                    else ""
                )
            )

        # 2. Data degraded (Phase 5 hard rule 4).
        if request.is_data_degraded:
            reasons.append(LiquidityRejectReason.DATA_DEGRADED)
            notes.append("market_data_buffer reports degraded view")

        # 3. Book missing -> can't compute slippage / depth.
        book = request.orderbook
        if book is None:
            reasons.append(LiquidityRejectReason.BOOK_MISSING)
            notes.append("orderbook not available")
            return self._finalise_evaluate(
                request,
                reasons=reasons,
                notes=notes,
                spread_score=0.0,
                depth_score=0.0,
                slippage_pct=None,
                exit_seconds=None,
                exit_plan=None,
                emit_event=emit_event,
            )

        # 4. Spread.
        spread_pct = (
            request.spread_pct
            if request.spread_pct is not None
            else _spread_pct_from_book(book)
        )
        spread_score = _score_spread(spread_pct, cfg.max_spread_pct)
        if spread_pct is None or spread_pct > cfg.max_spread_pct:
            reasons.append(LiquidityRejectReason.SPREAD_TOO_WIDE)
            notes.append(
                "spread_pct="
                + (f"{spread_pct:.6f}" if spread_pct is not None else "None")
                + f" > max={cfg.max_spread_pct:.6f}"
            )

        # 5. Slippage / depth via book walk.
        side_str = request.side.value
        walk = estimate_book_walk(book, qty=request.planned_qty, side=side_str)
        slippage_pct = walk.slippage_pct

        # Depth check uses the *total* available depth on the opposite
        # side of the book, not what the walk happened to fill - the
        # walk only consumes ``planned_qty``, so it can never clear
        # ``planned_qty * multiplier`` (Issue #5: depth requirement is
        # "the book must support a 5x exit cushion", not "the entry
        # itself eats 5x").
        if side_str in ("long", "buy"):
            total_opposite_qty = sum(lvl.qty for lvl in book.asks)
        else:
            total_opposite_qty = sum(lvl.qty for lvl in book.bids)

        depth_score = _score_depth(
            available=total_opposite_qty,
            planned=request.planned_qty,
            multiplier=cfg.min_depth_multiplier,
        )
        if request.planned_qty > 0:
            min_required = request.planned_qty * cfg.min_depth_multiplier
            if total_opposite_qty + 1e-12 < min_required:
                reasons.append(LiquidityRejectReason.DEPTH_INSUFFICIENT)
                notes.append(
                    f"available_qty={total_opposite_qty:.6f}"
                    f" < required={min_required:.6f}"
                    f" (qty={request.planned_qty:.6f} x {cfg.min_depth_multiplier})"
                )
            if walk.exhausted:
                reasons.append(LiquidityRejectReason.NO_EXIT_CHANNEL)
                notes.append("book exhausted before planned qty cleared")
            if slippage_pct is not None and slippage_pct > cfg.max_slippage_pct:
                reasons.append(LiquidityRejectReason.SLIPPAGE_TOO_HIGH)
                notes.append(
                    f"estimated_slippage_pct={slippage_pct:.6f}"
                    f" > max={cfg.max_slippage_pct:.6f}"
                )

        # 6. Exit-time estimate / can_exit_position.
        exit_plan = self._compute_exit_plan(request)
        if request.planned_qty > 0 and not exit_plan.feasible:
            for reason in exit_plan.reject_reasons:
                if reason not in reasons:
                    reasons.append(reason)

        passed = not reasons
        return self._finalise_evaluate(
            request,
            reasons=reasons,
            notes=notes,
            spread_score=spread_score,
            depth_score=depth_score,
            slippage_pct=slippage_pct,
            exit_seconds=exit_plan.estimated_exit_seconds,
            exit_plan=exit_plan,
            emit_event=emit_event,
            forced_passed=passed,
        )

    # ------------------------------------------------------------------
    # can_exit_position (Spec §19.2 - mandatory)
    # ------------------------------------------------------------------
    def can_exit_position(
        self,
        symbol: str,
        qty: float,
        max_slippage_pct: float | None = None,
        max_seconds: float | None = None,
        *,
        side: Side = Side.LONG,
        orderbook: OrderBook | None = None,
        volume_5m: float | None = None,
        throughput_qty_per_sec: float | None = None,
        last_price: float | None = None,
        is_data_degraded: bool = False,
        risk_permission: RiskPermission | None = None,
        market_regime: MarketRegime | None = None,
        spread_pct: float | None = None,
        emit_event: bool | None = None,
    ) -> ExitPlan:
        """Spec §19.2 mandatory function.

        Returns an :class:`ExitPlan` describing whether the position
        can be flattened within ``max_seconds`` at <= ``max_slippage_pct``.
        Phase 5 hard rule 3: when ``feasible`` is False, the Risk
        Engine MUST refuse an attack candidate (Issue #7 will read
        this).

        ``max_slippage_pct`` and ``max_seconds`` default to the
        configured ceilings.

        Throughput estimate
        -------------------

        When the caller does not pass ``throughput_qty_per_sec``, the
        function falls back to ``volume_5m / 300`` (i.e. realised base
        volume averaged over the rolling 5-minute window from
        :class:`MarketDataBuffer`). This is the **upper bound** on
        instantaneous capacity, not a conservative estimate:

          - It assumes the next 5 minutes will print at the same pace
            as the previous 5 minutes - a reasonable default in a
            calm tape, fragile in a thinning one.
          - It counts every realised trade against our own outflow
            even though our flatten order will compete with the rest
            of the tape; the 5x ``min_depth_multiplier`` cushion in
            :class:`LiquidityConfig` is what makes this safe in normal
            regimes, not the throughput estimate itself.
          - It does NOT discount for ATR expansion, OI flush, or
            crowding around our exit price. A spike in the next 5
            minutes can collapse realised liquidity faster than this
            estimate degrades.

        Issue #7's Risk Engine MUST therefore apply a conservative
        discount on top of the value returned here before sizing an
        attack candidate. Recommended directions for that discount
        (left for Issue #7 to pin down; Phase 5 does NOT make sizing
        decisions):

          - scale by an ATR-expansion factor (worse vol -> bigger
            divisor),
          - cap at a configured fraction of recent average volume,
          - and require ``feasible=True`` to remain ``feasible=True``
            after the discounted re-check.

        Degraded data
        -------------

        ``is_data_degraded=True`` already maps to
        ``LiquidityRejectReason.DATA_DEGRADED`` and forces
        ``feasible=False`` in the returned :class:`ExitPlan`. Callers
        in Phase 7+ MUST therefore:

          1. Read ``MarketDataBuffer.is_degraded(symbol)`` for every
             can_exit_position check, and pass the result through.
          2. Treat a missing or stale order book identically: an
             explicit ``orderbook=None`` already maps to
             ``LiquidityRejectReason.BOOK_MISSING`` /
             ``feasible=False``, but a *stale* book that the buffer
             has flagged DEGRADED but happens to still be in memory
             must NOT be passed in with ``is_data_degraded=False``.
             The buffer's degraded view is the single source of
             truth.
          3. Never invert the result. If ``feasible=False`` for any
             reason - degraded data, slippage, no-exit-channel,
             exit-too-slow, or regime block - Issue #7's No-Trade
             Gate MUST refuse the attack candidate.

        The per-symbol DATA_DEGRADED + can_exit_position interaction
        is exercised by
        ``tests/unit/test_can_exit_position.py
        ::test_can_exit_position_rejects_when_data_degraded``.
        """
        cfg = self._config
        max_slip = max_slippage_pct if max_slippage_pct is not None else cfg.max_slippage_pct
        max_secs = max_seconds if max_seconds is not None else cfg.max_exit_seconds
        request = LiquidityInput(
            symbol=symbol,
            side=side,
            planned_qty=qty,
            last_price=last_price,
            spread_pct=spread_pct,
            orderbook=orderbook,
            volume_5m=volume_5m or 0.0,
            is_data_degraded=is_data_degraded,
            market_regime=market_regime,
            risk_permission=risk_permission,
            throughput_qty_per_sec=throughput_qty_per_sec,
        )
        plan = self._compute_exit_plan(
            request,
            max_slippage_pct=max_slip,
            max_seconds=max_secs,
        )
        self._exit_checks += 1
        # Resolve event-emission policy:
        #   emit_event=True  -> always emit (per-call override)
        #   emit_event=False -> always skip (per-call override)
        #   emit_event=None  -> follow self._config.event_emit_enabled
        should_emit = emit_event if emit_event is not None else self._config.event_emit_enabled
        if should_emit and self._event_repo is not None:
            payload: dict[str, object] = {
                "symbol": plan.symbol,
                "side": plan.side.value,
                "qty": plan.qty,
                "feasible": plan.feasible,
                "estimated_slippage_pct": plan.estimated_slippage_pct,
                "estimated_exit_seconds": plan.estimated_exit_seconds,
                "cleared_qty": plan.cleared_qty,
                "weighted_avg_fill_price": plan.weighted_avg_fill_price,
                "reject_reasons": [r.value for r in plan.reject_reasons],
                "notes": list(plan.notes),
                "max_slippage_pct": max_slip,
                "max_seconds": max_secs,
                "check": "can_exit_position",
            }
            self._event_repo.append_event(
                Event(
                    event_type=EventType.LIQUIDITY_CHECKED,
                    source_module=self.SOURCE_MODULE,
                    symbol=symbol,
                    timestamp=plan.timestamp or now_ms(),
                    payload=payload,
                )
            )
            self._liquidity_checked_emitted += 1
        else:
            self._liquidity_checked_skipped += 1
        return plan

    # ------------------------------------------------------------------
    # Helpers used by tests + Issue #7 (preferred direct interface)
    # ------------------------------------------------------------------
    def evaluate_with_buffer(
        self,
        symbol: str,
        *,
        side: Side,
        planned_qty: float,
        market_data_buffer,
        regime: RegimeSnapshot | None = None,
        emit_event: bool | None = None,
    ) -> LiquidityDecision:
        """Build a :class:`LiquidityInput` from the Phase 4 buffer."""
        snap = market_data_buffer.snapshot(symbol, emit_event=False)
        is_degraded = bool(market_data_buffer.is_degraded(symbol))
        # Phase 4 buffer doesn't directly expose the latest book, but
        # the snapshot was built from it; we re-read via the per-symbol
        # state which the buffer maintains. Tests substitute a stub.
        try:
            book = market_data_buffer._state_for(symbol).orderbook
        except Exception:  # pragma: no cover - defensive
            book = None
        request = LiquidityInput(
            symbol=symbol,
            side=side,
            planned_qty=planned_qty,
            last_price=snap.last_price,
            spread_pct=snap.spread_pct,
            orderbook=book,
            volume_5m=snap.volume_5m,
            is_data_degraded=is_degraded,
            market_regime=regime.market_regime if regime is not None else None,
            risk_permission=regime.risk_permission if regime is not None else None,
            timestamp=snap.timestamp,
        )
        return self.evaluate(request, emit_event=emit_event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _compute_exit_plan(
        self,
        request: LiquidityInput,
        *,
        max_slippage_pct: float | None = None,
        max_seconds: float | None = None,
    ) -> ExitPlan:
        cfg = self._config
        max_slip = max_slippage_pct if max_slippage_pct is not None else cfg.max_slippage_pct
        max_secs = max_seconds if max_seconds is not None else cfg.max_exit_seconds
        reasons: list[LiquidityRejectReason] = []
        notes: list[str] = []

        # Regime / degraded gates feed in here too so a direct
        # can_exit_position call enforces the Phase 5 hard rules even
        # when the caller skipped evaluate().
        if (
            request.risk_permission is not None
            and request.risk_permission in cfg.blocking_risk_permissions
        ):
            reasons.append(LiquidityRejectReason.REGIME_BLOCKED)
            notes.append(
                f"risk_permission={request.risk_permission.value}"
                + (
                    f" market_regime={request.market_regime.value}"
                    if request.market_regime is not None
                    else ""
                )
            )
        if request.is_data_degraded:
            reasons.append(LiquidityRejectReason.DATA_DEGRADED)
            notes.append("market_data_buffer reports degraded view")

        book = request.orderbook
        if book is None:
            reasons.append(LiquidityRejectReason.BOOK_MISSING)
            notes.append("orderbook not available")
            return ExitPlan(
                symbol=request.symbol,
                side=request.side,
                qty=request.planned_qty,
                feasible=False,
                estimated_slippage_pct=None,
                estimated_exit_seconds=None,
                cleared_qty=0.0,
                weighted_avg_fill_price=None,
                reject_reasons=tuple(reasons),
                notes=tuple(notes),
                timestamp=request.timestamp if request.timestamp is not None else now_ms(),
            )

        walk = estimate_book_walk(
            book, qty=request.planned_qty, side=request.side.value
        )
        slippage_pct = walk.slippage_pct
        if request.planned_qty > 0 and walk.exhausted:
            reasons.append(LiquidityRejectReason.NO_EXIT_CHANNEL)
            notes.append(
                f"book exhausted: cleared={walk.cleared_qty:.6f} of qty={request.planned_qty:.6f}"
            )
        if (
            request.planned_qty > 0
            and slippage_pct is not None
            and slippage_pct > max_slip
        ):
            reasons.append(LiquidityRejectReason.SLIPPAGE_TOO_HIGH)
            notes.append(
                f"estimated_slippage_pct={slippage_pct:.6f} > max={max_slip:.6f}"
            )

        # Throughput-based exit-time estimate.
        throughput = request.throughput_qty_per_sec
        if throughput is None or throughput <= 0:
            if request.volume_5m and request.volume_5m > 0:
                throughput = request.volume_5m / _VOLUME_WINDOW_5M_SECONDS
            else:
                throughput = cfg.default_throughput_qty_per_sec

        if request.planned_qty <= 0:
            exit_seconds: float | None = 0.0
        elif throughput and throughput > 0:
            exit_seconds = request.planned_qty / throughput
            if exit_seconds > max_secs:
                reasons.append(LiquidityRejectReason.EXIT_TOO_SLOW)
                notes.append(
                    f"exit_seconds={exit_seconds:.2f} > max={max_secs:.2f}"
                    f" (qty={request.planned_qty:.6f} / throughput={throughput:.6f})"
                )
        else:
            exit_seconds = None
            reasons.append(LiquidityRejectReason.EXIT_TOO_SLOW)
            notes.append("throughput estimate unavailable (volume_5m=0)")

        feasible = not reasons and (
            request.planned_qty == 0
            or (
                not walk.exhausted
                and (slippage_pct is None or slippage_pct <= max_slip)
                and (exit_seconds is None or exit_seconds <= max_secs)
            )
        )

        # Deduplicate reasons preserving order.
        seen: set[LiquidityRejectReason] = set()
        ordered: list[LiquidityRejectReason] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                ordered.append(r)

        return ExitPlan(
            symbol=request.symbol,
            side=request.side,
            qty=request.planned_qty,
            feasible=feasible,
            estimated_slippage_pct=slippage_pct,
            estimated_exit_seconds=exit_seconds,
            cleared_qty=walk.cleared_qty,
            weighted_avg_fill_price=walk.weighted_avg_fill_price,
            reject_reasons=tuple(ordered),
            notes=tuple(notes),
            timestamp=request.timestamp if request.timestamp is not None else now_ms(),
        )

    def _finalise_evaluate(
        self,
        request: LiquidityInput,
        *,
        reasons: list[LiquidityRejectReason],
        notes: list[str],
        spread_score: float,
        depth_score: float,
        slippage_pct: float | None,
        exit_seconds: float | None,
        exit_plan: ExitPlan | None,
        emit_event: bool | None,
        forced_passed: bool | None = None,
    ) -> LiquidityDecision:
        # Deduplicate while preserving insertion order.
        seen: set[LiquidityRejectReason] = set()
        ordered: list[LiquidityRejectReason] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                ordered.append(r)
        passed = forced_passed if forced_passed is not None else not ordered

        decision = LiquidityDecision(
            symbol=request.symbol,
            side=request.side,
            passed=passed,
            spread_score=spread_score,
            depth_score=depth_score,
            estimated_slippage_pct=slippage_pct,
            estimated_exit_seconds=exit_seconds,
            reject_reasons=tuple(ordered),
            notes=tuple(notes),
            exit_plan=exit_plan,
            timestamp=request.timestamp if request.timestamp is not None else now_ms(),
        )
        self._evaluations += 1
        # Resolve event-emission policy (mirrors can_exit_position):
        #   emit_event=True  -> always emit (per-call override)
        #   emit_event=False -> always skip (per-call override)
        #   emit_event=None  -> follow self._config.event_emit_enabled
        should_emit = emit_event if emit_event is not None else self._config.event_emit_enabled
        if should_emit and self._event_repo is not None:
            payload: dict[str, object] = {
                "symbol": decision.symbol,
                "side": decision.side.value,
                "passed": decision.passed,
                "spread_score": decision.spread_score,
                "depth_score": decision.depth_score,
                "estimated_slippage_pct": decision.estimated_slippage_pct,
                "estimated_exit_seconds": decision.estimated_exit_seconds,
                "reject_reasons": [r.value for r in decision.reject_reasons],
                "notes": list(decision.notes),
                "planned_qty": request.planned_qty,
                "spread_pct": request.spread_pct,
                "is_data_degraded": request.is_data_degraded,
                "market_regime": (
                    request.market_regime.value if request.market_regime else None
                ),
                "risk_permission": (
                    request.risk_permission.value if request.risk_permission else None
                ),
                "check": "evaluate",
            }
            self._event_repo.append_event(
                Event(
                    event_type=EventType.LIQUIDITY_CHECKED,
                    source_module=self.SOURCE_MODULE,
                    symbol=decision.symbol,
                    timestamp=decision.timestamp or now_ms(),
                    payload=payload,
                )
            )
            self._liquidity_checked_emitted += 1
        else:
            self._liquidity_checked_skipped += 1
        return decision


# ---------------------------------------------------------------------------
# Free-function variant of can_exit_position. The Risk Engine (Issue #7)
# can call this without instantiating a filter.
# ---------------------------------------------------------------------------
def can_exit_position(
    symbol: str,
    qty: float,
    max_slippage_pct: float,
    max_seconds: float,
    *,
    orderbook: OrderBook | None,
    side: Side = Side.LONG,
    volume_5m: float | None = None,
    throughput_qty_per_sec: float | None = None,
    is_data_degraded: bool = False,
    risk_permission: RiskPermission | None = None,
    market_regime: MarketRegime | None = None,
    spread_pct: float | None = None,
    config: LiquidityConfig | None = None,
    event_repo: EventRepository | None = None,
    emit_event: bool | None = False,
) -> ExitPlan:
    """Stateless alternative to :meth:`LiquidityFilter.can_exit_position`.

    Tests use this for the bulk of the can_exit_position cases and
    Issue #7's No-Trade Gate calls it without keeping a filter
    instance around.

    Same throughput-estimate caveats as the method form: when the
    caller does not pass ``throughput_qty_per_sec``, the underlying
    helper falls back to ``volume_5m / 300``, which is an UPPER
    BOUND. **Issue #7 MUST apply a conservative discount on top.**
    A degraded data view (``is_data_degraded=True``) already forces
    ``feasible=False`` with reason ``DATA_DEGRADED``. See
    :meth:`LiquidityFilter.can_exit_position` for the full contract.
    """
    f = LiquidityFilter(config=config, event_repo=event_repo)
    return f.can_exit_position(
        symbol,
        qty,
        max_slippage_pct,
        max_seconds,
        side=side,
        orderbook=orderbook,
        volume_5m=volume_5m,
        throughput_qty_per_sec=throughput_qty_per_sec,
        is_data_degraded=is_data_degraded,
        risk_permission=risk_permission,
        market_regime=market_regime,
        spread_pct=spread_pct,
        emit_event=emit_event,
    )


# ---------------------------------------------------------------------------
# Score helpers (private)
# ---------------------------------------------------------------------------
def _score_spread(spread_pct: float | None, max_spread_pct: float) -> float:
    if spread_pct is None or max_spread_pct <= 0:
        return 0.0
    if spread_pct <= 0:
        return 1.0
    score = 1.0 - (spread_pct / max_spread_pct)
    return max(0.0, min(score, 1.0))


def _score_depth(
    *, available: float, planned: float, multiplier: float
) -> float:
    if planned <= 0 or multiplier <= 0:
        return 1.0
    required = planned * multiplier
    if required <= 0:
        return 1.0
    return max(0.0, min(available / required, 1.0))


def _spread_pct_from_book(book: OrderBook) -> float | None:
    spread = book.spread
    ask = book.best_ask
    if spread is None or ask is None or ask <= 0:
        return None
    return max(spread / ask, 0.0)
