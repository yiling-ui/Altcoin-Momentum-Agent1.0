"""Funding-aware live PnL accounting (PR112 - Live Capital / Risk v0).

Turns a list of PR111 classified Binance income events
(:class:`app.live.binance_income.BinanceIncomeEvent`) into a
:class:`LivePnlSummary` whose headline figure ALWAYS includes both
commission and funding:

    net_strategy_pnl = gross_realized_pnl - commission_total + funding_total

PR112 accounting rules (from the brief):

  1. A deposit / transfer-in is NEVER counted as strategy profit.
  2. A withdrawal / transfer-out is NEVER counted as strategy loss.
  3. Funding fee / funding income is kept separate from price PnL and
     ALWAYS folded into the operator-facing net figure.
  4. An unknown income type is preserved separately (never coerced into
     realized PnL / fees / funding / external flows).
  5. Funding attribution stays account-level in PR112. A funding row
     that cannot be linked to a trade/position is marked
     ``UNATTRIBUTED_PENDING_POSITION_LINK``; position-level attribution
     is a PR113 / PR114 handoff (see :data:`FUNDING_ATTRIBUTION_HANDOFF`).

This module performs NO IO. It only classifies + sums already-fetched
rows. It never places an order, never changes capital, and never flips
a safety flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.live.binance_income import (
    AttributionStatus,
    BinanceIncomeEvent,
    classify_income_rows,
)
from app.live.capital_event import CapitalEventType

# HANDOFF marker surfaced in the summary so a reviewer / PR113 sees that
# position-level funding attribution is intentionally deferred.
FUNDING_ATTRIBUTION_HANDOFF = (
    "HANDOFF(PR113/PR114): attach funding/commission/realized-pnl income "
    "rows to the live trade ledger at position/trade level. PR112 keeps "
    "funding attribution account-level."
)


class FundingAttributionStatus:
    """Closed taxonomy of account-level funding-attribution states (PR112)."""

    # No funding rows were present at all.
    NOT_APPLICABLE = "NOT_APPLICABLE"
    # All funding rows carried a trade id (rare in account-level reads).
    ATTRIBUTED = "ATTRIBUTED"
    # At least one funding row has no trade/position link yet.
    UNATTRIBUTED_PENDING_POSITION_LINK = "UNATTRIBUTED_PENDING_POSITION_LINK"


@dataclass(frozen=True)
class LivePnlSummary:
    """Funding-aware PnL summary derived from classified income events.

    Every external-flow figure is tracked separately from strategy PnL
    so a deposit can never inflate performance and a withdrawal can never
    look like a loss.
    """

    gross_realized_pnl_usdt: float
    commission_total_usdt: float
    funding_total_usdt: float
    net_strategy_pnl_usdt: float
    external_deposit_total_usdt: float
    external_withdrawal_total_usdt: float
    transfer_in_total_usdt: float
    transfer_out_total_usdt: float
    adjusted_strategy_equity_usdt: float
    performance_equity_excluding_external_flows: float
    unknown_income_total_usdt: float
    funding_attribution_status: str
    unattributed_funding_count: int = 0
    funding_event_count: int = 0
    unknown_income_count: int = 0
    income_event_count: int = 0
    account_equity_usdt: float = 0.0
    funding_attribution_handoff: str = FUNDING_ATTRIBUTION_HANDOFF

    @property
    def net_external_capital_usdt(self) -> float:
        """Net external capital contributed (deposits/transfers in - out)."""
        return (
            self.external_deposit_total_usdt
            - self.external_withdrawal_total_usdt
            + self.transfer_in_total_usdt
            - self.transfer_out_total_usdt
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gross_realized_pnl_usdt": self.gross_realized_pnl_usdt,
            "commission_total_usdt": self.commission_total_usdt,
            "funding_total_usdt": self.funding_total_usdt,
            "net_strategy_pnl_usdt": self.net_strategy_pnl_usdt,
            "external_deposit_total_usdt": self.external_deposit_total_usdt,
            "external_withdrawal_total_usdt": self.external_withdrawal_total_usdt,
            "transfer_in_total_usdt": self.transfer_in_total_usdt,
            "transfer_out_total_usdt": self.transfer_out_total_usdt,
            "net_external_capital_usdt": self.net_external_capital_usdt,
            "adjusted_strategy_equity_usdt": self.adjusted_strategy_equity_usdt,
            "performance_equity_excluding_external_flows": (
                self.performance_equity_excluding_external_flows
            ),
            "unknown_income_total_usdt": self.unknown_income_total_usdt,
            "funding_attribution_status": self.funding_attribution_status,
            "unattributed_funding_count": self.unattributed_funding_count,
            "funding_event_count": self.funding_event_count,
            "unknown_income_count": self.unknown_income_count,
            "income_event_count": self.income_event_count,
            "account_equity_usdt": self.account_equity_usdt,
            "funding_attribution_handoff": self.funding_attribution_handoff,
        }


def build_live_pnl_summary(
    income_events: list[BinanceIncomeEvent],
    *,
    account_equity_usdt: float = 0.0,
) -> LivePnlSummary:
    """Fold classified income events into a funding-aware PnL summary.

    ``account_equity_usdt`` (optional) is the truthful current equity
    from :class:`app.live.capital_state.LiveCapitalState`. When supplied:

      - ``adjusted_strategy_equity_usdt`` = the truthful equity itself
        (the real balance is never hidden), and
      - ``performance_equity_excluding_external_flows`` = the truthful
        equity with the net external capital flow removed, so the
        operator can see strategy-only performance.
    """

    gross_realized = 0.0
    commission_total = 0.0
    funding_total = 0.0
    external_deposit = 0.0
    external_withdrawal = 0.0
    transfer_in = 0.0
    transfer_out = 0.0
    unknown_total = 0.0
    unknown_count = 0
    funding_count = 0
    unattributed_funding = 0

    for ev in income_events or ():
        ce = ev.capital_event
        if ce is None:
            unknown_count += 1
            unknown_total += ev.income
            continue
        et = ce.event_type
        amt = abs(ce.amount_usdt)
        if et is CapitalEventType.REALIZED_PNL:
            gross_realized += amt
        elif et is CapitalEventType.REALIZED_LOSS:
            gross_realized -= amt
        elif et is CapitalEventType.FEE:
            commission_total += amt
        elif et is CapitalEventType.FUNDING_INCOME:
            funding_total += amt
            funding_count += 1
            if (
                ev.attribution_status
                is AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
            ):
                unattributed_funding += 1
        elif et is CapitalEventType.FUNDING_FEE:
            funding_total -= amt
            funding_count += 1
            if (
                ev.attribution_status
                is AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
            ):
                unattributed_funding += 1
        elif et is CapitalEventType.EXTERNAL_DEPOSIT:
            external_deposit += amt
        elif et is CapitalEventType.EXTERNAL_WITHDRAWAL:
            external_withdrawal += amt
        elif et is CapitalEventType.TRANSFER_IN:
            transfer_in += amt
        elif et is CapitalEventType.TRANSFER_OUT:
            transfer_out += amt
        # Any other classified type (MANUAL / HARVEST / REBASE) is
        # deliberately not folded into strategy PnL.

    net_strategy_pnl = gross_realized - commission_total + funding_total

    # Funding attribution roll-up (account-level in PR112).
    if funding_count == 0:
        attribution_status = FundingAttributionStatus.NOT_APPLICABLE
    elif unattributed_funding > 0:
        attribution_status = (
            FundingAttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
        )
    else:
        attribution_status = FundingAttributionStatus.ATTRIBUTED

    net_external = (
        external_deposit - external_withdrawal + transfer_in - transfer_out
    )
    adjusted_equity = float(account_equity_usdt)
    performance_equity = adjusted_equity - net_external

    return LivePnlSummary(
        gross_realized_pnl_usdt=gross_realized,
        commission_total_usdt=commission_total,
        funding_total_usdt=funding_total,
        net_strategy_pnl_usdt=net_strategy_pnl,
        external_deposit_total_usdt=external_deposit,
        external_withdrawal_total_usdt=external_withdrawal,
        transfer_in_total_usdt=transfer_in,
        transfer_out_total_usdt=transfer_out,
        adjusted_strategy_equity_usdt=adjusted_equity,
        performance_equity_excluding_external_flows=performance_equity,
        unknown_income_total_usdt=unknown_total,
        funding_attribution_status=attribution_status,
        unattributed_funding_count=unattributed_funding,
        funding_event_count=funding_count,
        unknown_income_count=unknown_count,
        income_event_count=len(income_events or ()),
        account_equity_usdt=float(account_equity_usdt),
    )


def build_live_pnl_summary_from_rows(
    rows: list[dict[str, Any]],
    *,
    account_equity_usdt: float = 0.0,
) -> LivePnlSummary:
    """Convenience: classify raw Binance income rows, then summarise."""
    return build_live_pnl_summary(
        classify_income_rows(rows), account_equity_usdt=account_equity_usdt
    )


__all__ = [
    "FUNDING_ATTRIBUTION_HANDOFF",
    "FundingAttributionStatus",
    "LivePnlSummary",
    "build_live_pnl_summary",
    "build_live_pnl_summary_from_rows",
]
