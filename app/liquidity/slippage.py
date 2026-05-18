"""Order-book walk and slippage helpers (Phase 5 - Issue #5).

These helpers are pure - no IO, no events, no state - so they are
trivially testable and reused by both :class:`LiquidityFilter` and
``can_exit_position``.

Conventions
-----------

  - Walk the *opposite* side of the book vs the order's side:
      LONG / buy  -> walk asks (lifts offers, price moves up)
      SHORT / sell -> walk bids (hits bids, price moves down)
  - Reference price is the best opposite-side price (best ask for
    long, best bid for short). Slippage is reported as a non-negative
    fraction of that reference price.
  - If the book is shallower than ``qty``, the walk fills as much as
    it can and reports ``cleared_qty < qty``; the caller decides
    whether that counts as a reject.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.exchanges.models import OrderBook


@dataclass(frozen=True)
class BookWalkResult:
    """Outcome of walking the opposite side of the book for ``qty``.

    Fields:
        cleared_qty:                  base qty actually filled
        weighted_avg_fill_price:      VWAP of the fills (or None when
                                       cleared_qty == 0)
        worst_fill_price:             furthest price touched
        reference_price:              best opposite-side price at the
                                       time of the walk
        slippage_pct:                 (worst - reference) / reference
                                       for a buy walk; (reference -
                                       worst) / reference for a sell
                                       walk. Always >= 0.
        exhausted:                    True if the book ran out before
                                       ``qty`` was filled
    """

    cleared_qty: float
    weighted_avg_fill_price: float | None
    worst_fill_price: float | None
    reference_price: float | None
    slippage_pct: float | None
    exhausted: bool


def estimate_book_walk(
    book: OrderBook | None, *, qty: float, side: str
) -> BookWalkResult:
    """Walk the opposite side of the book for ``qty``.

    ``side`` is the order's side (the side the *trader* is taking):

      - ``"long"`` / ``"buy"``  -> walk asks
      - ``"short"`` / ``"sell"`` -> walk bids

    Returns a :class:`BookWalkResult`. Empty input yields an
    "exhausted" result with all metrics ``None``.
    """
    if book is None or qty <= 0:
        return BookWalkResult(
            cleared_qty=0.0,
            weighted_avg_fill_price=None,
            worst_fill_price=None,
            reference_price=_reference_price(book, side) if book is not None else None,
            slippage_pct=None,
            exhausted=True,
        )

    side_norm = side.lower()
    if side_norm in ("long", "buy"):
        levels = book.asks
        ascending = True  # asks are ascending in price
    elif side_norm in ("short", "sell"):
        levels = book.bids
        ascending = False
    else:
        raise ValueError(f"unknown side {side!r}; expected long/short/buy/sell")

    if not levels:
        return BookWalkResult(
            cleared_qty=0.0,
            weighted_avg_fill_price=None,
            worst_fill_price=None,
            reference_price=None,
            slippage_pct=None,
            exhausted=True,
        )

    reference_price = levels[0].price
    cleared = 0.0
    notional = 0.0
    worst = reference_price
    remaining = qty
    for lvl in levels:
        if remaining <= 0:
            break
        take = min(remaining, lvl.qty)
        if take <= 0:
            continue
        cleared += take
        notional += take * lvl.price
        worst = lvl.price
        remaining -= take

    if cleared <= 0:
        return BookWalkResult(
            cleared_qty=0.0,
            weighted_avg_fill_price=None,
            worst_fill_price=None,
            reference_price=reference_price,
            slippage_pct=None,
            exhausted=True,
        )

    avg = notional / cleared
    if reference_price is None or reference_price <= 0:
        slippage_pct: float | None = None
    elif ascending:
        slippage_pct = max((worst - reference_price) / reference_price, 0.0)
    else:
        slippage_pct = max((reference_price - worst) / reference_price, 0.0)

    exhausted = cleared + 1e-12 < qty
    return BookWalkResult(
        cleared_qty=cleared,
        weighted_avg_fill_price=avg,
        worst_fill_price=worst,
        reference_price=reference_price,
        slippage_pct=slippage_pct,
        exhausted=exhausted,
    )


def estimated_slippage_pct(
    book: OrderBook | None, *, qty: float, side: str
) -> float | None:
    """Convenience wrapper returning only the slippage_pct (or None)."""
    return estimate_book_walk(book, qty=qty, side=side).slippage_pct


def walk_book_for_quote_notional(
    book: OrderBook | None, *, quote_notional: float, side: str
) -> BookWalkResult:
    """Walk the book until ``quote_notional`` (USDT) has been spent.

    Useful for sizing an attack candidate by quote currency rather
    than base qty. Phase 5 only ships this as a helper; nobody calls
    it on the boot path. Issue #6 / #7 will use it for sizing.
    """
    if book is None or quote_notional <= 0:
        return BookWalkResult(
            cleared_qty=0.0,
            weighted_avg_fill_price=None,
            worst_fill_price=None,
            reference_price=_reference_price(book, side) if book is not None else None,
            slippage_pct=None,
            exhausted=True,
        )

    side_norm = side.lower()
    if side_norm in ("long", "buy"):
        levels = book.asks
        ascending = True
    elif side_norm in ("short", "sell"):
        levels = book.bids
        ascending = False
    else:
        raise ValueError(f"unknown side {side!r}; expected long/short/buy/sell")

    if not levels:
        return BookWalkResult(
            cleared_qty=0.0,
            weighted_avg_fill_price=None,
            worst_fill_price=None,
            reference_price=None,
            slippage_pct=None,
            exhausted=True,
        )

    reference_price = levels[0].price
    cleared = 0.0
    notional = 0.0
    worst = reference_price
    remaining_quote = quote_notional
    for lvl in levels:
        if remaining_quote <= 0:
            break
        avail_quote = lvl.qty * lvl.price
        take_quote = min(remaining_quote, avail_quote)
        if take_quote <= 0:
            continue
        take_qty = take_quote / lvl.price
        cleared += take_qty
        notional += take_quote
        worst = lvl.price
        remaining_quote -= take_quote

    if cleared <= 0:
        return BookWalkResult(
            cleared_qty=0.0,
            weighted_avg_fill_price=None,
            worst_fill_price=None,
            reference_price=reference_price,
            slippage_pct=None,
            exhausted=True,
        )

    avg = notional / cleared
    if reference_price is None or reference_price <= 0:
        slippage_pct: float | None = None
    elif ascending:
        slippage_pct = max((worst - reference_price) / reference_price, 0.0)
    else:
        slippage_pct = max((reference_price - worst) / reference_price, 0.0)

    exhausted = remaining_quote > 1e-9
    return BookWalkResult(
        cleared_qty=cleared,
        weighted_avg_fill_price=avg,
        worst_fill_price=worst,
        reference_price=reference_price,
        slippage_pct=slippage_pct,
        exhausted=exhausted,
    )


def _reference_price(book: OrderBook | None, side: str) -> float | None:
    if book is None:
        return None
    side_norm = side.lower()
    if side_norm in ("long", "buy"):
        return book.best_ask
    if side_norm in ("short", "sell"):
        return book.best_bid
    return None
