"""Live funding / commission attribution (PR114 - Operator Console v0).

PR111 / PR112 classify Binance income-history rows (funding fee / funding
income / commission / realized PnL) at the ACCOUNT level only. PR113's
order ledger carries funding forward with a placeholder
``UNATTRIBUTED_PENDING_POSITION_LINK`` status. PR114 closes the first
version of the handoff: it attributes those income rows to the live
order / fill / position / trade ledger WHERE POSSIBLE, while never
dropping a funding event.

Attribution rules (the brief):

  1. Commission rows:
       - if the row carries a ``trade_id`` / ``order_id`` that matches a
         ledger row / fill, attach it to that order / fill.
       - else attach by ``symbol`` + nearest timestamp to a known fill.
       - else keep account-level.
  2. Funding rows (funding fee paid / funding income received):
       - if the row has a ``symbol`` and its time falls within
         ``[entry_time, exit_time]`` of a position / trade, attach it.
       - if multiple positions of the same symbol overlap the funding
         time, the row is AMBIGUOUS: allocate deterministically by
         notional weight (and mark the status ambiguous).
       - if no matching position / trade, keep account-level.
  3. A funding / commission row that cannot be linked to any
     position / trade keeps ``UNATTRIBUTED_PENDING_POSITION_LINK`` and is
     STILL counted in the account-level totals (never dropped).

Attribution status taxonomy (per row + rolled up):
  - ``ATTRIBUTED_TO_TRADE``
  - ``ATTRIBUTED_TO_POSITION``
  - ``ATTRIBUTED_TO_ORDER`` (commission rows)
  - ``ACCOUNT_LEVEL_ONLY``
  - ``AMBIGUOUS_MULTIPLE_POSITIONS``
  - ``UNATTRIBUTED_PENDING_POSITION_LINK``

This module is pure (no IO). It never places an order, never changes
capital, and never flips a safety flag. It only re-buckets already-read
income rows so the live PnL never silently ignores funding paid while a
position was held.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from app.live.binance_income import BinanceIncomeEvent
from app.live.capital_event import CapitalEventType

FUNDING_ATTRIBUTION_MODULE = "live.funding_attribution"


class FundingAttributionOutcome(str, Enum):
    """Per-row attribution outcome (PR114)."""

    ATTRIBUTED_TO_TRADE = "ATTRIBUTED_TO_TRADE"
    ATTRIBUTED_TO_POSITION = "ATTRIBUTED_TO_POSITION"
    ATTRIBUTED_TO_ORDER = "ATTRIBUTED_TO_ORDER"
    ACCOUNT_LEVEL_ONLY = "ACCOUNT_LEVEL_ONLY"
    AMBIGUOUS_MULTIPLE_POSITIONS = "AMBIGUOUS_MULTIPLE_POSITIONS"
    UNATTRIBUTED_PENDING_POSITION_LINK = "UNATTRIBUTED_PENDING_POSITION_LINK"

    @property
    def is_attributed(self) -> bool:
        return self in (
            FundingAttributionOutcome.ATTRIBUTED_TO_TRADE,
            FundingAttributionOutcome.ATTRIBUTED_TO_POSITION,
            FundingAttributionOutcome.ATTRIBUTED_TO_ORDER,
        )


@dataclass(frozen=True)
class PositionInterval:
    """A held-position / trade interval used to attribute funding rows.

    ``exit_time_ms`` of ``None`` means the position is still open (the
    interval extends to +infinity for the purpose of matching). A trade
    id and / or position id may be attached; ``trade_id`` wins when both
    are present (trade-level attribution is the strongest).
    """

    symbol: str
    entry_time_ms: int
    exit_time_ms: int | None = None
    notional_usdt: float = 0.0
    trade_id: str | None = None
    position_id: str | None = None
    side: str | None = None

    def contains(self, time_ms: int | None) -> bool:
        """True if ``time_ms`` falls within the held interval (inclusive)."""
        if time_ms is None:
            return False
        if time_ms < self.entry_time_ms:
            return False
        if self.exit_time_ms is not None and time_ms > self.exit_time_ms:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_time_ms": self.entry_time_ms,
            "exit_time_ms": self.exit_time_ms,
            "notional_usdt": self.notional_usdt,
            "trade_id": self.trade_id,
            "position_id": self.position_id,
            "side": self.side,
        }


@dataclass(frozen=True)
class FillRef:
    """A minimal reference to a live fill / order for commission attribution."""

    symbol: str
    trade_time_ms: int | None = None
    trade_id: str | None = None
    order_id: str | None = None
    client_order_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trade_time_ms": self.trade_time_ms,
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
        }


@dataclass(frozen=True)
class AttributedIncome:
    """A single income row + the result of attributing it (PR114)."""

    symbol: str | None
    income_type: str
    amount_usdt: float
    time_ms: int | None
    trade_id: str | None
    is_funding: bool
    is_commission: bool
    outcome: FundingAttributionOutcome
    attributed_trade_id: str | None = None
    attributed_position_id: str | None = None
    attributed_order_id: str | None = None
    allocation_weight: float = 1.0
    note: str = ""

    @property
    def attributed(self) -> bool:
        return self.outcome.is_attributed

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "income_type": self.income_type,
            "amount_usdt": self.amount_usdt,
            "time_ms": self.time_ms,
            "trade_id": self.trade_id,
            "is_funding": self.is_funding,
            "is_commission": self.is_commission,
            "outcome": self.outcome.value,
            "attributed_trade_id": self.attributed_trade_id,
            "attributed_position_id": self.attributed_position_id,
            "attributed_order_id": self.attributed_order_id,
            "allocation_weight": self.allocation_weight,
            "note": self.note,
        }


@dataclass(frozen=True)
class FundingAttributionResult:
    """The full result of attributing a batch of income rows (PR114)."""

    rows: tuple[AttributedIncome, ...]
    attributed_funding_usdt: float
    account_level_funding_usdt: float
    total_funding_usdt: float
    commission_total_usdt: float
    attributed_commission_usdt: float
    funding_event_count: int
    commission_event_count: int
    unattributed_funding_count: int
    ambiguous_funding_count: int
    attribution_status: str

    def funding_for_trade(self, trade_id: str) -> float:
        """Net funding (income positive / fee negative) attributed to a trade."""
        return sum(
            r.amount_usdt
            for r in self.rows
            if r.is_funding and r.attributed_trade_id == trade_id
        )

    def funding_for_position(self, position_id: str) -> float:
        """Net funding attributed to a position id."""
        return sum(
            r.amount_usdt
            for r in self.rows
            if r.is_funding and r.attributed_position_id == position_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [r.to_dict() for r in self.rows],
            "attributed_funding_usdt": self.attributed_funding_usdt,
            "account_level_funding_usdt": self.account_level_funding_usdt,
            "total_funding_usdt": self.total_funding_usdt,
            "commission_total_usdt": self.commission_total_usdt,
            "attributed_commission_usdt": self.attributed_commission_usdt,
            "funding_event_count": self.funding_event_count,
            "commission_event_count": self.commission_event_count,
            "unattributed_funding_count": self.unattributed_funding_count,
            "ambiguous_funding_count": self.ambiguous_funding_count,
            "attribution_status": self.attribution_status,
        }


def _signed_funding_amount(ev: BinanceIncomeEvent) -> float:
    """Signed funding contribution: income positive, fee negative."""
    ce = ev.capital_event
    if ce is None:
        return 0.0
    amt = abs(ce.amount_usdt)
    if ce.event_type is CapitalEventType.FUNDING_INCOME:
        return amt
    if ce.event_type is CapitalEventType.FUNDING_FEE:
        return -amt
    return 0.0


def _commission_amount(ev: BinanceIncomeEvent) -> float:
    """Commission magnitude (always a cost; reported as a positive total)."""
    ce = ev.capital_event
    if ce is None:
        return 0.0
    if ce.event_type is CapitalEventType.FEE:
        return abs(ce.amount_usdt)
    return 0.0


def _matching_intervals(
    symbol: str | None, time_ms: int | None, intervals: Sequence[PositionInterval]
) -> list[PositionInterval]:
    if not symbol or time_ms is None:
        return []
    return [
        iv
        for iv in intervals
        if iv.symbol == symbol and iv.contains(time_ms)
    ]


def _attribute_funding_row(
    ev: BinanceIncomeEvent, intervals: Sequence[PositionInterval]
) -> AttributedIncome:
    amount = _signed_funding_amount(ev)
    matches = _matching_intervals(ev.symbol, ev.time_ms, intervals)

    if not matches:
        # No position/trade overlaps the funding time -> account-level.
        outcome = (
            FundingAttributionOutcome.ACCOUNT_LEVEL_ONLY
            if ev.symbol and ev.time_ms is not None
            else FundingAttributionOutcome.UNATTRIBUTED_PENDING_POSITION_LINK
        )
        note = (
            "no_position_or_trade_overlaps_funding_time"
            if outcome is FundingAttributionOutcome.ACCOUNT_LEVEL_ONLY
            else "missing_symbol_or_time_cannot_link"
        )
        return AttributedIncome(
            symbol=ev.symbol,
            income_type=ev.raw_income_type,
            amount_usdt=amount,
            time_ms=ev.time_ms,
            trade_id=ev.trade_id,
            is_funding=True,
            is_commission=False,
            outcome=outcome,
            note=note,
        )

    if len(matches) == 1:
        iv = matches[0]
        if iv.trade_id:
            return AttributedIncome(
                symbol=ev.symbol,
                income_type=ev.raw_income_type,
                amount_usdt=amount,
                time_ms=ev.time_ms,
                trade_id=ev.trade_id,
                is_funding=True,
                is_commission=False,
                outcome=FundingAttributionOutcome.ATTRIBUTED_TO_TRADE,
                attributed_trade_id=iv.trade_id,
                attributed_position_id=iv.position_id,
                note="funding_time_inside_single_trade_interval",
            )
        return AttributedIncome(
            symbol=ev.symbol,
            income_type=ev.raw_income_type,
            amount_usdt=amount,
            time_ms=ev.time_ms,
            trade_id=ev.trade_id,
            is_funding=True,
            is_commission=False,
            outcome=FundingAttributionOutcome.ATTRIBUTED_TO_POSITION,
            attributed_position_id=iv.position_id,
            note="funding_time_inside_single_position_interval",
        )

    # Multiple overlapping positions for the same symbol -> ambiguous.
    # Deterministic allocation by notional weight (largest notional wins
    # the primary link; the full set is recorded for audit). The amount
    # stays whole on the dominant interval so the account total is exact.
    total_notional = sum(max(0.0, iv.notional_usdt) for iv in matches)
    # Deterministic ordering: by notional desc, then entry_time asc, then
    # an id for a stable tiebreak.
    ranked = sorted(
        matches,
        key=lambda iv: (-max(0.0, iv.notional_usdt), iv.entry_time_ms, iv.trade_id or iv.position_id or ""),
    )
    primary = ranked[0]
    weight = (
        max(0.0, primary.notional_usdt) / total_notional
        if total_notional > 0
        else 1.0 / len(matches)
    )
    return AttributedIncome(
        symbol=ev.symbol,
        income_type=ev.raw_income_type,
        amount_usdt=amount,
        time_ms=ev.time_ms,
        trade_id=ev.trade_id,
        is_funding=True,
        is_commission=False,
        outcome=FundingAttributionOutcome.AMBIGUOUS_MULTIPLE_POSITIONS,
        attributed_trade_id=primary.trade_id,
        attributed_position_id=primary.position_id,
        allocation_weight=round(weight, 6),
        note=(
            f"funding_time_overlaps_{len(matches)}_positions_"
            f"deterministic_notional_allocation"
        ),
    )


def _nearest_fill(
    symbol: str | None, time_ms: int | None, fills: Sequence[FillRef]
) -> FillRef | None:
    if not symbol:
        return None
    same_symbol = [f for f in fills if f.symbol == symbol]
    if not same_symbol:
        return None
    if time_ms is None:
        return same_symbol[0]
    timed = [f for f in same_symbol if f.trade_time_ms is not None]
    if not timed:
        return same_symbol[0]
    return min(timed, key=lambda f: abs((f.trade_time_ms or 0) - time_ms))


def _attribute_commission_row(
    ev: BinanceIncomeEvent, fills: Sequence[FillRef]
) -> AttributedIncome:
    amount = _commission_amount(ev)

    # 1. Direct trade_id / order_id match.
    if ev.trade_id:
        for f in fills:
            if f.trade_id and f.trade_id == ev.trade_id:
                return AttributedIncome(
                    symbol=ev.symbol or f.symbol,
                    income_type=ev.raw_income_type,
                    amount_usdt=amount,
                    time_ms=ev.time_ms,
                    trade_id=ev.trade_id,
                    is_funding=False,
                    is_commission=True,
                    outcome=FundingAttributionOutcome.ATTRIBUTED_TO_ORDER,
                    attributed_trade_id=f.trade_id,
                    attributed_order_id=f.order_id,
                    note="commission_matched_by_trade_id",
                )

    # 2. Symbol + nearest timestamp.
    near = _nearest_fill(ev.symbol, ev.time_ms, fills)
    if near is not None:
        return AttributedIncome(
            symbol=ev.symbol or near.symbol,
            income_type=ev.raw_income_type,
            amount_usdt=amount,
            time_ms=ev.time_ms,
            trade_id=ev.trade_id,
            is_funding=False,
            is_commission=True,
            outcome=FundingAttributionOutcome.ATTRIBUTED_TO_ORDER,
            attributed_trade_id=near.trade_id,
            attributed_order_id=near.order_id,
            note="commission_matched_by_symbol_and_nearest_time",
        )

    # 3. Account-level.
    return AttributedIncome(
        symbol=ev.symbol,
        income_type=ev.raw_income_type,
        amount_usdt=amount,
        time_ms=ev.time_ms,
        trade_id=ev.trade_id,
        is_funding=False,
        is_commission=True,
        outcome=(
            FundingAttributionOutcome.ACCOUNT_LEVEL_ONLY
            if ev.symbol
            else FundingAttributionOutcome.UNATTRIBUTED_PENDING_POSITION_LINK
        ),
        note="commission_no_matching_fill",
    )


def attribute_funding_events(
    income_events: Sequence[BinanceIncomeEvent],
    *,
    positions: Sequence[PositionInterval] | None = None,
    fills: Sequence[FillRef] | None = None,
) -> FundingAttributionResult:
    """Attribute funding + commission income rows to trades/positions/orders.

    ``positions`` are held-position / trade intervals (entry/exit time +
    notional). ``fills`` are minimal fill references for commission
    attribution. Both are optional: with neither supplied every funding /
    commission row stays account-level (and is still counted).

    Funding is NEVER dropped: each row is bucketed into exactly one
    outcome and contributes to the appropriate total.
    """
    intervals = list(positions or ())
    fill_refs = list(fills or ())

    rows: list[AttributedIncome] = []
    attributed_funding = 0.0
    account_level_funding = 0.0
    total_funding = 0.0
    commission_total = 0.0
    attributed_commission = 0.0
    funding_count = 0
    commission_count = 0
    unattributed_funding = 0
    ambiguous_funding = 0

    for ev in income_events or ():
        if ev.is_funding:
            funding_count += 1
            row = _attribute_funding_row(ev, intervals)
            rows.append(row)
            total_funding += row.amount_usdt
            if row.outcome is FundingAttributionOutcome.AMBIGUOUS_MULTIPLE_POSITIONS:
                ambiguous_funding += 1
                attributed_funding += row.amount_usdt
            elif row.attributed:
                attributed_funding += row.amount_usdt
            else:
                account_level_funding += row.amount_usdt
                if (
                    row.outcome
                    is FundingAttributionOutcome.UNATTRIBUTED_PENDING_POSITION_LINK
                ):
                    unattributed_funding += 1
        elif ev.is_fee:
            commission_count += 1
            row = _attribute_commission_row(ev, fill_refs)
            rows.append(row)
            commission_total += row.amount_usdt
            if row.attributed:
                attributed_commission += row.amount_usdt
        # Non funding / non commission rows (realized pnl, transfers,
        # deposits) are left to the PR112 PnL summary; they are not
        # attribution targets here.

    status = roll_up_attribution_status(
        funding_count=funding_count,
        unattributed_funding=unattributed_funding,
        ambiguous_funding=ambiguous_funding,
        account_level_funding_count=sum(
            1
            for r in rows
            if r.is_funding
            and r.outcome is FundingAttributionOutcome.ACCOUNT_LEVEL_ONLY
        ),
    )

    return FundingAttributionResult(
        rows=tuple(rows),
        attributed_funding_usdt=attributed_funding,
        account_level_funding_usdt=account_level_funding,
        total_funding_usdt=total_funding,
        commission_total_usdt=commission_total,
        attributed_commission_usdt=attributed_commission,
        funding_event_count=funding_count,
        commission_event_count=commission_count,
        unattributed_funding_count=unattributed_funding,
        ambiguous_funding_count=ambiguous_funding,
        attribution_status=status,
    )


def roll_up_attribution_status(
    *,
    funding_count: int,
    unattributed_funding: int,
    ambiguous_funding: int,
    account_level_funding_count: int,
) -> str:
    """Roll a batch of per-row outcomes up into a single status string.

    Priority (worst-first so the operator sees the weakest link):
      - no funding rows           -> NOT_APPLICABLE
      - any pending link          -> UNATTRIBUTED_PENDING_POSITION_LINK
      - any ambiguous             -> AMBIGUOUS_MULTIPLE_POSITIONS
      - any account-level only    -> ACCOUNT_LEVEL_ONLY
      - else                      -> ATTRIBUTED_TO_POSITION
    """
    if funding_count == 0:
        return "NOT_APPLICABLE"
    if unattributed_funding > 0:
        return FundingAttributionOutcome.UNATTRIBUTED_PENDING_POSITION_LINK.value
    if ambiguous_funding > 0:
        return FundingAttributionOutcome.AMBIGUOUS_MULTIPLE_POSITIONS.value
    if account_level_funding_count > 0:
        return FundingAttributionOutcome.ACCOUNT_LEVEL_ONLY.value
    return FundingAttributionOutcome.ATTRIBUTED_TO_POSITION.value


__all__ = [
    "FUNDING_ATTRIBUTION_MODULE",
    "FundingAttributionOutcome",
    "PositionInterval",
    "FillRef",
    "AttributedIncome",
    "FundingAttributionResult",
    "attribute_funding_events",
    "roll_up_attribution_status",
]
