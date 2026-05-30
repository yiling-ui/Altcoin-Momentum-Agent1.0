"""Capital Event Contract (PR110 - Live Foundation v0).

Identify the SOURCE of every real account balance change so a deposit
is never mistaken for strategy profit and a withdrawal is never
mistaken for strategy loss.

The brief's failure mode: a 10U account that grows to 10,000U because
the operator deposited 9,990U is NOT a 1000x strategy result. Strategy
performance statistics and capital-profile selection MUST be computed
on the *adjusted* equity (external flows separated out), never on raw
balance deltas.

This module ships:

  - :class:`CapitalEventType` - the closed taxonomy of balance-change
    sources.
  - :class:`CapitalEventCategory` - the coarse bucket each type maps
    to (trading PnL vs. external flow vs. fee/funding vs. manual vs.
    internal transfer vs. harvest/rebase).
  - :class:`LiveCapitalEvent` - the per-event record with the
    classification flags the brief mandates.
  - :class:`CapitalEventLedger` - an accumulator that keeps trading
    PnL, external flows, and fees/funding strictly separated.

PR110 boundary: descriptive accounting only. Nothing here moves
capital, places an order, or flips a Phase 1 safety flag. The system
does NOT call any exchange withdrawal / transfer API.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.clock import now_ms


class CapitalEventType(str, Enum):
    """Closed taxonomy of real account balance-change sources."""

    EXTERNAL_DEPOSIT = "EXTERNAL_DEPOSIT"
    EXTERNAL_WITHDRAWAL = "EXTERNAL_WITHDRAWAL"
    REALIZED_PNL = "REALIZED_PNL"
    REALIZED_LOSS = "REALIZED_LOSS"
    FEE = "FEE"
    FUNDING_FEE = "FUNDING_FEE"
    FUNDING_INCOME = "FUNDING_INCOME"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    PROFIT_HARVEST = "PROFIT_HARVEST"
    CAPITAL_REBASE = "CAPITAL_REBASE"


class CapitalEventCategory(str, Enum):
    """Coarse bucket used to keep strategy PnL away from everything else."""

    TRADING_PNL = "TRADING_PNL"
    EXTERNAL_FLOW = "EXTERNAL_FLOW"
    FEE_FUNDING = "FEE_FUNDING"
    MANUAL = "MANUAL"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    HARVEST_REBASE = "HARVEST_REBASE"


@dataclass(frozen=True)
class CapitalEventClassification:
    """The derived flags for a :class:`CapitalEventType`."""

    category: CapitalEventCategory
    is_trading_pnl: bool
    is_external_capital_flow: bool
    is_fee_or_funding: bool
    affects_performance_stats: bool
    affects_profile_selection: bool


# Deterministic classification table. This is the single source of
# truth for "is this strategy PnL, an external flow, or a fee?".
_CLASSIFICATION: dict[CapitalEventType, CapitalEventClassification] = {
    CapitalEventType.EXTERNAL_DEPOSIT: CapitalEventClassification(
        category=CapitalEventCategory.EXTERNAL_FLOW,
        is_trading_pnl=False,
        is_external_capital_flow=True,
        is_fee_or_funding=False,
        affects_performance_stats=False,
        affects_profile_selection=True,
    ),
    CapitalEventType.EXTERNAL_WITHDRAWAL: CapitalEventClassification(
        category=CapitalEventCategory.EXTERNAL_FLOW,
        is_trading_pnl=False,
        is_external_capital_flow=True,
        is_fee_or_funding=False,
        affects_performance_stats=False,
        affects_profile_selection=True,
    ),
    CapitalEventType.REALIZED_PNL: CapitalEventClassification(
        category=CapitalEventCategory.TRADING_PNL,
        is_trading_pnl=True,
        is_external_capital_flow=False,
        is_fee_or_funding=False,
        affects_performance_stats=True,
        affects_profile_selection=True,
    ),
    CapitalEventType.REALIZED_LOSS: CapitalEventClassification(
        category=CapitalEventCategory.TRADING_PNL,
        is_trading_pnl=True,
        is_external_capital_flow=False,
        is_fee_or_funding=False,
        affects_performance_stats=True,
        affects_profile_selection=True,
    ),
    CapitalEventType.FEE: CapitalEventClassification(
        category=CapitalEventCategory.FEE_FUNDING,
        is_trading_pnl=False,
        is_external_capital_flow=False,
        is_fee_or_funding=True,
        affects_performance_stats=True,
        affects_profile_selection=True,
    ),
    CapitalEventType.FUNDING_FEE: CapitalEventClassification(
        category=CapitalEventCategory.FEE_FUNDING,
        is_trading_pnl=False,
        is_external_capital_flow=False,
        is_fee_or_funding=True,
        affects_performance_stats=True,
        affects_profile_selection=True,
    ),
    CapitalEventType.FUNDING_INCOME: CapitalEventClassification(
        category=CapitalEventCategory.FEE_FUNDING,
        is_trading_pnl=False,
        is_external_capital_flow=False,
        is_fee_or_funding=True,
        affects_performance_stats=True,
        affects_profile_selection=True,
    ),
    CapitalEventType.MANUAL_ADJUSTMENT: CapitalEventClassification(
        category=CapitalEventCategory.MANUAL,
        is_trading_pnl=False,
        is_external_capital_flow=True,
        is_fee_or_funding=False,
        affects_performance_stats=False,
        affects_profile_selection=True,
    ),
    CapitalEventType.TRANSFER_IN: CapitalEventClassification(
        category=CapitalEventCategory.INTERNAL_TRANSFER,
        is_trading_pnl=False,
        is_external_capital_flow=True,
        is_fee_or_funding=False,
        affects_performance_stats=False,
        affects_profile_selection=True,
    ),
    CapitalEventType.TRANSFER_OUT: CapitalEventClassification(
        category=CapitalEventCategory.INTERNAL_TRANSFER,
        is_trading_pnl=False,
        is_external_capital_flow=True,
        is_fee_or_funding=False,
        affects_performance_stats=False,
        affects_profile_selection=True,
    ),
    CapitalEventType.PROFIT_HARVEST: CapitalEventClassification(
        category=CapitalEventCategory.HARVEST_REBASE,
        is_trading_pnl=False,
        is_external_capital_flow=True,
        is_fee_or_funding=False,
        affects_performance_stats=False,
        affects_profile_selection=True,
    ),
    CapitalEventType.CAPITAL_REBASE: CapitalEventClassification(
        category=CapitalEventCategory.HARVEST_REBASE,
        is_trading_pnl=False,
        is_external_capital_flow=False,
        is_fee_or_funding=False,
        affects_performance_stats=False,
        affects_profile_selection=True,
    ),
}


def classify_capital_event(event_type: CapitalEventType | str) -> CapitalEventClassification:
    """Return the deterministic classification for a capital event type."""
    if isinstance(event_type, str) and not isinstance(event_type, CapitalEventType):
        event_type = CapitalEventType(event_type)
    return _CLASSIFICATION[event_type]


@dataclass(frozen=True)
class LiveCapitalEvent:
    """A single classified real-account balance-change record.

    The classification flags are derived from ``event_type`` via the
    deterministic table; build instances with :meth:`create` so the
    flags can never drift from the type.
    """

    event_id: str
    event_type: CapitalEventType
    amount_usdt: float
    asset: str
    balance_before: float
    balance_after: float
    detected_at: int
    source: str
    category: CapitalEventCategory
    is_trading_pnl: bool
    is_external_capital_flow: bool
    is_fee_or_funding: bool
    affects_performance_stats: bool
    affects_profile_selection: bool
    audit_reason: str
    exchange_tx_ref: str | None = None
    account_update_ref: str | None = None

    @classmethod
    def create(
        cls,
        *,
        event_type: CapitalEventType | str,
        amount_usdt: float,
        asset: str = "USDT",
        balance_before: float = 0.0,
        balance_after: float | None = None,
        source: str = "exchange_account_update",
        detected_at: int | None = None,
        exchange_tx_ref: str | None = None,
        account_update_ref: str | None = None,
        audit_reason: str | None = None,
        event_id: str | None = None,
    ) -> "LiveCapitalEvent":
        if isinstance(event_type, str) and not isinstance(event_type, CapitalEventType):
            event_type = CapitalEventType(event_type)
        cls_flags = classify_capital_event(event_type)
        signed = _signed_balance_delta(event_type, amount_usdt)
        if balance_after is None:
            balance_after = float(balance_before) + signed
        return cls(
            event_id=event_id or str(uuid.uuid4()),
            event_type=event_type,
            amount_usdt=float(amount_usdt),
            asset=asset,
            balance_before=float(balance_before),
            balance_after=float(balance_after),
            detected_at=detected_at if detected_at is not None else now_ms(),
            source=source,
            category=cls_flags.category,
            is_trading_pnl=cls_flags.is_trading_pnl,
            is_external_capital_flow=cls_flags.is_external_capital_flow,
            is_fee_or_funding=cls_flags.is_fee_or_funding,
            affects_performance_stats=cls_flags.affects_performance_stats,
            affects_profile_selection=cls_flags.affects_profile_selection,
            audit_reason=audit_reason or f"classified_as_{cls_flags.category.value}",
            exchange_tx_ref=exchange_tx_ref,
            account_update_ref=account_update_ref,
        )

    @property
    def trading_pnl_contribution(self) -> float:
        """Signed PnL contribution; 0 for any non-trading-PnL event.

        REALIZED_PNL contributes ``+abs(amount)``; REALIZED_LOSS
        contributes ``-abs(amount)``. Deposits / withdrawals / fees /
        funding / transfers / harvest / rebase contribute exactly 0 so
        they can never pollute strategy PnL.
        """
        if not self.is_trading_pnl:
            return 0.0
        if self.event_type is CapitalEventType.REALIZED_LOSS:
            return -abs(self.amount_usdt)
        return abs(self.amount_usdt)

    @property
    def external_flow_contribution(self) -> float:
        """Signed external-capital contribution; 0 for non-external events.

        Deposits / transfers-in / manual-credit are positive; withdrawals
        / transfers-out / profit-harvest are negative.
        """
        if not self.is_external_capital_flow:
            return 0.0
        return _signed_balance_delta(self.event_type, self.amount_usdt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "amount_usdt": self.amount_usdt,
            "asset": self.asset,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "detected_at": self.detected_at,
            "source": self.source,
            "category": self.category.value,
            "is_trading_pnl": self.is_trading_pnl,
            "is_external_capital_flow": self.is_external_capital_flow,
            "is_fee_or_funding": self.is_fee_or_funding,
            "affects_performance_stats": self.affects_performance_stats,
            "affects_profile_selection": self.affects_profile_selection,
            "audit_reason": self.audit_reason,
            "exchange_tx_ref": self.exchange_tx_ref,
            "account_update_ref": self.account_update_ref,
            "trading_pnl_contribution": self.trading_pnl_contribution,
            "external_flow_contribution": self.external_flow_contribution,
        }


def _signed_balance_delta(event_type: CapitalEventType, amount_usdt: float) -> float:
    """Return the signed balance delta a positive ``amount`` implies."""
    amt = abs(float(amount_usdt))
    negative_types = {
        CapitalEventType.EXTERNAL_WITHDRAWAL,
        CapitalEventType.REALIZED_LOSS,
        CapitalEventType.FEE,
        CapitalEventType.FUNDING_FEE,
        CapitalEventType.TRANSFER_OUT,
        CapitalEventType.PROFIT_HARVEST,
    }
    if event_type in negative_types:
        return -amt
    if event_type in (CapitalEventType.MANUAL_ADJUSTMENT, CapitalEventType.CAPITAL_REBASE):
        # Manual adjustment / rebase carry their own sign.
        return float(amount_usdt)
    return amt


@dataclass
class CapitalEventLedger:
    """Accumulates capital events while keeping the categories separate.

    Guarantees (PR110 / brief):
      - external deposits / withdrawals NEVER move ``total_realized_pnl``.
      - fees / funding are tracked in their OWN accumulators.
      - ``adjusted_equity`` (for capital-profile selection) tracks the
        real balance but exposes ``net_strategy_pnl`` so the operator
        can see strategy performance with external flows removed.
    """

    initial_capital_usdt: float = 0.0
    total_realized_pnl: float = 0.0
    total_external_deposits: float = 0.0
    total_external_withdrawals: float = 0.0
    total_fees: float = 0.0
    total_funding: float = 0.0
    total_manual_adjustment: float = 0.0
    total_internal_transfers: float = 0.0
    total_profit_harvested: float = 0.0
    current_balance_usdt: float = 0.0
    event_count: int = 0

    def apply(self, event: LiveCapitalEvent) -> None:
        """Fold one classified event into the ledger."""
        self.event_count += 1
        self.current_balance_usdt = event.balance_after

        if event.is_trading_pnl:
            self.total_realized_pnl += event.trading_pnl_contribution
        elif event.category is CapitalEventCategory.FEE_FUNDING:
            if event.event_type is CapitalEventType.FUNDING_INCOME:
                self.total_funding += abs(event.amount_usdt)
            elif event.event_type is CapitalEventType.FUNDING_FEE:
                self.total_funding -= abs(event.amount_usdt)
            else:  # FEE
                self.total_fees += abs(event.amount_usdt)
        elif event.event_type is CapitalEventType.EXTERNAL_DEPOSIT:
            self.total_external_deposits += abs(event.amount_usdt)
        elif event.event_type is CapitalEventType.EXTERNAL_WITHDRAWAL:
            self.total_external_withdrawals += abs(event.amount_usdt)
        elif event.event_type in (
            CapitalEventType.TRANSFER_IN,
            CapitalEventType.TRANSFER_OUT,
        ):
            self.total_internal_transfers += event.external_flow_contribution
        elif event.event_type is CapitalEventType.PROFIT_HARVEST:
            self.total_profit_harvested += abs(event.amount_usdt)
        elif event.event_type is CapitalEventType.MANUAL_ADJUSTMENT:
            self.total_manual_adjustment += float(event.amount_usdt)
        # CAPITAL_REBASE is a baseline re-anchor; it does not change any
        # of the accumulators above (balance is updated via balance_after).

    @property
    def net_strategy_pnl(self) -> float:
        """Strategy PnL net of fees / funding; excludes external flows."""
        return self.total_realized_pnl - self.total_fees + self.total_funding

    @property
    def net_external_capital(self) -> float:
        """Net external capital contributed (deposits - withdrawals - harvest)."""
        return (
            self.total_external_deposits
            - self.total_external_withdrawals
            - self.total_profit_harvested
            + self.total_internal_transfers
            + self.total_manual_adjustment
        )

    @property
    def adjusted_equity_for_profile(self) -> float:
        """Equity used for capital-profile selection.

        Uses the truthful current balance. External flows are tracked
        separately so the operator can always see strategy performance
        with deposits / withdrawals removed via :pyattr:`net_strategy_pnl`.
        """
        return self.current_balance_usdt

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital_usdt": self.initial_capital_usdt,
            "total_realized_pnl": self.total_realized_pnl,
            "total_external_deposits": self.total_external_deposits,
            "total_external_withdrawals": self.total_external_withdrawals,
            "total_fees": self.total_fees,
            "total_funding": self.total_funding,
            "total_manual_adjustment": self.total_manual_adjustment,
            "total_internal_transfers": self.total_internal_transfers,
            "total_profit_harvested": self.total_profit_harvested,
            "current_balance_usdt": self.current_balance_usdt,
            "event_count": self.event_count,
            "net_strategy_pnl": self.net_strategy_pnl,
            "net_external_capital": self.net_external_capital,
            "adjusted_equity_for_profile": self.adjusted_equity_for_profile,
        }


__all__ = [
    "CapitalEventType",
    "CapitalEventCategory",
    "CapitalEventClassification",
    "classify_capital_event",
    "LiveCapitalEvent",
    "CapitalEventLedger",
]
