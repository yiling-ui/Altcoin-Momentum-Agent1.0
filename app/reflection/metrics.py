"""Phase 10B - Reflection Engine deterministic metric helpers (Issue #10 Part 2).

Pure functions that compute MFE / MAE / tail_contribution from the
Phase 10A :class:`PaperTradeReplay` plus the Phase 8.5 ``learning_ready``
payload. **Every function returns a typed result that signals "data
insufficient" instead of fabricating a number.**

Phase 10B boundary
------------------

Nothing in this module:

  - imports an exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads ``os.environ`` for credentials
  - opens a socket
  - calls an LLM
  - defines a write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - mutates global state
  - calls :meth:`EventRepository.append_event` / ``append_many``
  - subscribes to outside data (no backfill, no quote feed)

Determinism rule
----------------

If the underlying data is not enough to compute a metric, the helper
returns ``MetricResult(value=None, unknown_reasons=(UnknownReason.X,))``.
The Reflection Engine NEVER swaps in a fallback number, NEVER
extrapolates, and NEVER calls a price feed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.events import Event, EventType
from app.reflection.models import UnknownReason


# ---------------------------------------------------------------------------
# MetricResult value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MetricResult:
    """Deterministic metric output.

    ``value`` is ``None`` when the underlying data is insufficient, in
    which case ``unknown_reasons`` carries one or more typed
    :class:`UnknownReason` codes.

    The Reflection Engine merges the ``unknown_reasons`` of every
    metric call into the final result's ``data_quality_notes`` list.
    """

    value: float | None
    unknown_reasons: tuple[UnknownReason, ...]

    @property
    def known(self) -> bool:
        return self.value is not None and not self.unknown_reasons


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _direction_long(events: Iterable[Event]) -> bool:
    """True if the trade was a LONG position.

    Reads the first ``ORDER_SENT`` payload (set by
    :class:`OrderRequest`). Defaults to long when the payload does not
    record a direction (Phase 9 paper-mode default), which keeps the
    helper deterministic.
    """
    for ev in events:
        if ev.event_type is EventType.ORDER_SENT:
            payload = ev.payload or {}
            direction = payload.get("request", {}).get("direction") or payload.get(
                "direction"
            )
            if direction == "short":
                return False
            return True
    return True


def _entry_price(events: Iterable[Event]) -> float | None:
    """Return the most-trusted entry price for a paper trade.

    Phase 9 paper-mode keeps the request limit_price in the
    ``ORDER_SENT.request.limit_price`` payload and the realised fill
    price in the ``ORDER_FILLED.avg_fill_price`` payload. We prefer
    the realised fill; if neither is present we return ``None`` and
    the caller flags ``NO_FILL_RECORDED``.
    """
    fill_price: float | None = None
    request_price: float | None = None
    for ev in events:
        if ev.event_type is EventType.ORDER_FILLED:
            payload = ev.payload or {}
            fill_price = _coerce_float(
                payload.get("avg_fill_price")
                or payload.get("fill_price")
                or payload.get("price")
            )
            if fill_price is not None:
                break
        elif ev.event_type is EventType.ORDER_SENT and request_price is None:
            payload = ev.payload or {}
            request_price = _coerce_float(
                (payload.get("request") or {}).get("limit_price")
                or payload.get("limit_price")
            )
    if fill_price is not None:
        return fill_price
    return request_price


def _observed_prices(events: Iterable[Event]) -> list[float]:
    """Collect every price observation we can read from a paper-trade
    event chain.

    Phase 9 paper-mode does NOT carry a continuous price path - it
    only records entry / fill / stop / exit landmarks. Phase 10B
    therefore uses this list to compute MFE / MAE *only when there
    are at least two distinct landmarks*. Otherwise the metric
    returns :class:`UnknownReason.INSUFFICIENT_PRICE_PATH`.

    Future phases that subscribe to a real continuous quote feed will
    enrich the event payloads with a price path; Phase 10B will
    automatically pick those up because the helper indexes by payload
    key.
    """
    prices: list[float] = []
    for ev in events:
        payload = ev.payload or {}
        if ev.event_type is EventType.ORDER_FILLED:
            for key in ("avg_fill_price", "fill_price", "price"):
                p = _coerce_float(payload.get(key))
                if p is not None:
                    prices.append(p)
                    break
        elif ev.event_type is EventType.ORDER_PARTIAL_FILLED:
            for key in ("fill_price", "avg_fill_price", "price"):
                p = _coerce_float(payload.get(key))
                if p is not None:
                    prices.append(p)
                    break
        elif ev.event_type is EventType.STOP_CONFIRMED:
            for key in ("stop_price", "trigger_price"):
                p = _coerce_float(payload.get(key))
                if p is not None:
                    prices.append(p)
                    break
        elif ev.event_type is EventType.POSITION_OPENED:
            p = _coerce_float(payload.get("entry_price"))
            if p is not None:
                prices.append(p)
        elif ev.event_type is EventType.POSITION_UPDATED:
            for key in ("mark_price", "last_price"):
                p = _coerce_float(payload.get(key))
                if p is not None:
                    prices.append(p)
                    break
        elif ev.event_type is EventType.POSITION_CLOSED:
            for key in ("exit_price", "close_price", "mark_price", "last_price"):
                p = _coerce_float(payload.get(key))
                if p is not None:
                    prices.append(p)
                    break
        elif ev.event_type is EventType.MARKET_SNAPSHOT:
            p = _coerce_float(payload.get("last_price"))
            if p is not None:
                prices.append(p)
    return prices


# ---------------------------------------------------------------------------
# Public metric helpers
# ---------------------------------------------------------------------------
def compute_mfe(
    events: Iterable[Event],
    *,
    direction_long: bool | None = None,
    entry_price: float | None = None,
) -> MetricResult:
    """Return Maximum Favourable Excursion as an absolute price delta.

    Definition (Phase 10B):

      - LONG  : ``mfe = max(prices) - entry_price``
      - SHORT : ``mfe = entry_price - min(prices)``

    Returns ``MetricResult(value=None, unknown_reasons=(...))`` when:

      - entry price is unknown
      - fewer than two price observations are available
      - all observations equal the entry (no excursion)
    """
    events_t = tuple(events)
    direction = direction_long if direction_long is not None else _direction_long(events_t)
    entry = entry_price if entry_price is not None else _entry_price(events_t)
    if entry is None:
        return MetricResult(value=None, unknown_reasons=(UnknownReason.NO_FILL_RECORDED,))
    prices = _observed_prices(events_t)
    if len(prices) < 2:
        return MetricResult(
            value=None,
            unknown_reasons=(UnknownReason.INSUFFICIENT_PRICE_PATH,),
        )
    if direction:
        excursion = max(prices) - entry
    else:
        excursion = entry - min(prices)
    if excursion <= 0:
        # No favourable movement observed in the available landmarks.
        return MetricResult(
            value=None,
            unknown_reasons=(UnknownReason.INSUFFICIENT_PRICE_PATH,),
        )
    return MetricResult(value=float(excursion), unknown_reasons=())


def compute_mae(
    events: Iterable[Event],
    *,
    direction_long: bool | None = None,
    entry_price: float | None = None,
) -> MetricResult:
    """Return Maximum Adverse Excursion as an absolute price delta (>= 0).

    Definition (Phase 10B):

      - LONG  : ``mae = entry_price - min(prices)``
      - SHORT : ``mae = max(prices) - entry_price``

    Returns ``MetricResult(value=None, unknown_reasons=(...))`` when:

      - entry price is unknown
      - fewer than two price observations are available
      - the trade never traded against the entry
    """
    events_t = tuple(events)
    direction = direction_long if direction_long is not None else _direction_long(events_t)
    entry = entry_price if entry_price is not None else _entry_price(events_t)
    if entry is None:
        return MetricResult(value=None, unknown_reasons=(UnknownReason.NO_FILL_RECORDED,))
    prices = _observed_prices(events_t)
    if len(prices) < 2:
        return MetricResult(
            value=None,
            unknown_reasons=(UnknownReason.INSUFFICIENT_PRICE_PATH,),
        )
    if direction:
        adverse = entry - min(prices)
    else:
        adverse = max(prices) - entry
    if adverse <= 0:
        # No adverse excursion observed in the available landmarks.
        return MetricResult(
            value=None,
            unknown_reasons=(UnknownReason.INSUFFICIENT_PRICE_PATH,),
        )
    return MetricResult(value=float(adverse), unknown_reasons=())


def compute_tail_contribution(
    *,
    events: Iterable[Event],
    state_transitions: Iterable[tuple[str, str]] | None,
    realized_pnl: float | None,
    virtual_trade_plan: dict[str, Any] | None,
) -> MetricResult:
    """Return the tail contribution as a plain float (USDT-equivalent).

    Definition (Phase 10B):

      - If the trade entered ``RIGHT_TAIL_AMPLIFY`` and we have a
        ``realized_pnl`` *attributed to the right-tail amplify add* in
        either the ``POSITION_CLOSED`` payload (``tail_pnl``) or the
        learning-ready ``virtual_trade_plan.tail_contribution``, return
        that number.
      - If the trade did NOT enter ``RIGHT_TAIL_AMPLIFY`` and we have a
        :class:`virtual_trade_plan`, return ``0.0`` - there was no
        tail contribution and the data is sufficient to know it was
        zero.
      - Otherwise return ``MetricResult(value=None, unknown_reasons=...)``.

    Phase 10B does NOT split a single ``realized_pnl`` between the
    base position and the tail add; that requires fill-level
    attribution which the Phase 9 paper ledger does not yet produce.
    The helper therefore prefers a caller-supplied ``tail_pnl``
    payload field when present, and falls back to "unknown" rather
    than guessing.
    """
    events_t = tuple(events)
    states_t: tuple[tuple[str, str], ...] = tuple(state_transitions or ())
    entered_rta = any(to == "right_tail_amplify" for _, to in states_t)
    # Look for a caller-supplied tail PnL on POSITION_CLOSED.
    explicit_tail_pnl: float | None = None
    for ev in events_t:
        if ev.event_type is EventType.POSITION_CLOSED:
            payload = ev.payload or {}
            explicit_tail_pnl = _coerce_float(payload.get("tail_pnl"))
            if explicit_tail_pnl is None:
                explicit_tail_pnl = _coerce_float(
                    (payload.get("tail") or {}).get("realized_pnl")
                )
            break
    if entered_rta:
        if explicit_tail_pnl is not None:
            return MetricResult(value=float(explicit_tail_pnl), unknown_reasons=())
        # Fall back to the plan's reported tail_contribution if any.
        if isinstance(virtual_trade_plan, dict):
            plan_tail = _coerce_float(virtual_trade_plan.get("tail_contribution"))
            if plan_tail is not None:
                return MetricResult(value=float(plan_tail), unknown_reasons=())
        return MetricResult(
            value=None,
            unknown_reasons=(
                UnknownReason.NO_RIGHT_TAIL_AMPLIFY_LIFECYCLE,
            )
            if not entered_rta
            else (UnknownReason.INSUFFICIENT_PRICE_PATH,),
        )
    # Did not enter RTA. If we have a plan we can confidently say zero.
    if virtual_trade_plan is not None:
        return MetricResult(value=0.0, unknown_reasons=())
    if not states_t:
        return MetricResult(
            value=None,
            unknown_reasons=(
                UnknownReason.NO_STATE_TRANSITION_TRAIL,
                UnknownReason.NO_VIRTUAL_TRADE_PLAN,
            ),
        )
    return MetricResult(
        value=None,
        unknown_reasons=(UnknownReason.NO_VIRTUAL_TRADE_PLAN,),
    )


def realized_pnl_for(events: Iterable[Event]) -> float | None:
    """Return the realised PnL recorded on the ``POSITION_CLOSED`` event.

    ``None`` when no closing event landed.
    """
    for ev in events:
        if ev.event_type is EventType.POSITION_CLOSED:
            payload = ev.payload or {}
            for key in ("realized_pnl", "realised_pnl", "pnl"):
                value = _coerce_float(payload.get(key))
                if value is not None:
                    return value
            return None
    return None


__all__ = [
    "MetricResult",
    "compute_mfe",
    "compute_mae",
    "compute_tail_contribution",
    "realized_pnl_for",
]
