"""Binance income-history adapter for the Live API Integration Pack (PR111).

Binance USDT-M futures income rows (``/fapi/v1/income``) are classified
into PR110's Capital Event contract (:mod:`app.live.capital_event`) so
that funding fees, commissions, realized PnL, and wallet transfers are
accounted for separately and funding is NEVER mixed with trading PnL.

PR111 deliberately does NOT define its own capital-event taxonomy: it
maps each Binance income type onto PR110's
:class:`app.live.capital_event.CapitalEventType` and folds the result
into a PR110 :class:`app.live.capital_event.CapitalEventLedger`, whose
``net_strategy_pnl = total_realized_pnl - total_fees + total_funding``
is exactly the figure PR111 must compute.

PR111 funding / fee accounting rules
------------------------------------

1. Funding fee is NEVER mixed with trading price PnL (the PR110 ledger
   keeps ``total_funding`` separate from ``total_realized_pnl``).
2. ``trade_id`` / ``symbol`` / ``time`` are preserved for later
   trade/position attribution.
3. Funding that cannot yet be attributed to a ``trade_id`` is marked
   ``attribution_status = UNATTRIBUTED_PENDING_POSITION_LINK``.
4. An unknown Binance income type is preserved verbatim
   (``raw_income_type`` + ``UNKNOWN_INCOME_TYPE``) and is NEVER mapped
   into a PR110 capital-event type, so it can never silently pollute
   realized PnL / fees / funding / deposits / withdrawals.

HANDOFF(PR113/PR114): position-level funding attribution MUST be added
before real live PnL is considered final. PR111 only does account-level
classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.live.capital_event import (
    CapitalEventLedger,
    CapitalEventType,
    LiveCapitalEvent,
)

UNKNOWN_INCOME_TYPE_TAG = "UNKNOWN_INCOME_TYPE"


class AttributionStatus(str, Enum):
    """Whether a classified income event is linked to a trade/position."""

    ATTRIBUTED = "ATTRIBUTED"
    UNATTRIBUTED_PENDING_POSITION_LINK = "UNATTRIBUTED_PENDING_POSITION_LINK"
    NOT_APPLICABLE = "NOT_APPLICABLE"


#: Raw Binance income types PR111 explicitly maps onto a PR110
#: CapitalEventType. Anything not here is preserved as UNKNOWN.
KNOWN_BINANCE_INCOME_TYPES: frozenset[str] = frozenset(
    {
        "REALIZED_PNL",
        "FUNDING_FEE",
        "COMMISSION",
        "TRANSFER",
        "INTERNAL_TRANSFER",
        "WELCOME_BONUS",
    }
)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def map_income_type(
    income_type: str, income: float
) -> tuple[CapitalEventType | None, AttributionStatus]:
    """Map a raw Binance income type + signed amount to a PR110 event type.

    Returns ``(capital_event_type, attribution_status)``. A capital
    event type of ``None`` means the income type is unknown / unmapped
    and must be preserved verbatim rather than coerced.
    """

    t = (income_type or "").strip().upper()
    if t == "REALIZED_PNL":
        event = (
            CapitalEventType.REALIZED_PNL if income >= 0 else CapitalEventType.REALIZED_LOSS
        )
        return event, AttributionStatus.ATTRIBUTED  # caller downgrades if no trade_id
    if t == "FUNDING_FEE":
        event = (
            CapitalEventType.FUNDING_INCOME if income >= 0 else CapitalEventType.FUNDING_FEE
        )
        return event, AttributionStatus.ATTRIBUTED
    if t == "COMMISSION":
        return CapitalEventType.FEE, AttributionStatus.ATTRIBUTED
    if t in ("TRANSFER", "INTERNAL_TRANSFER"):
        event = (
            CapitalEventType.TRANSFER_IN if income >= 0 else CapitalEventType.TRANSFER_OUT
        )
        return event, AttributionStatus.NOT_APPLICABLE
    if t == "WELCOME_BONUS":
        # A bonus credit is inferable as a (non-trading) external deposit.
        return CapitalEventType.EXTERNAL_DEPOSIT, AttributionStatus.NOT_APPLICABLE
    return None, AttributionStatus.NOT_APPLICABLE


@dataclass(frozen=True)
class BinanceIncomeEvent:
    """A single Binance income row + its PR110 capital-event classification.

    ``capital_event`` is a PR110 :class:`LiveCapitalEvent` for a mapped
    row, or ``None`` for an unknown income type (preserved verbatim via
    ``raw_income_type`` so it is never silently dropped or mis-mapped).
    """

    symbol: str | None
    raw_income_type: str
    income: float
    asset: str
    time_ms: int | None
    tran_id: str | None
    trade_id: str | None
    capital_event: LiveCapitalEvent | None
    attribution_status: AttributionStatus
    info_tag: str = ""

    @property
    def is_unmapped(self) -> bool:
        return self.capital_event is None

    @property
    def is_funding(self) -> bool:
        return self.capital_event is not None and self.capital_event.event_type in (
            CapitalEventType.FUNDING_FEE,
            CapitalEventType.FUNDING_INCOME,
        )

    @property
    def is_fee(self) -> bool:
        return self.capital_event is not None and (
            self.capital_event.event_type is CapitalEventType.FEE
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "BinanceIncomeEvent":
        income_type = str(row.get("incomeType", "") or "").strip().upper()
        income = _to_float(row.get("income"))
        asset = str(row.get("asset", "USDT") or "USDT").strip() or "USDT"
        symbol = _opt_str(row.get("symbol"))
        trade_id = _opt_str(row.get("tradeId"))
        tran_id = _opt_str(row.get("tranId"))
        time_ms: int | None = None
        if row.get("time") is not None:
            try:
                time_ms = int(row.get("time"))
            except (TypeError, ValueError):
                time_ms = None

        event_type, attribution = map_income_type(income_type, income)

        capital_event: LiveCapitalEvent | None = None
        info_tag = ""
        if event_type is None:
            info_tag = UNKNOWN_INCOME_TYPE_TAG
        else:
            # Funding / realized-pnl / commission without a trade_id are
            # account-level until a later PR links them to a position.
            if attribution is AttributionStatus.ATTRIBUTED and not trade_id:
                attribution = AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
            capital_event = LiveCapitalEvent.create(
                event_type=event_type,
                amount_usdt=abs(income),
                asset=asset,
                source="binance_income_history",
                detected_at=time_ms,
                exchange_tx_ref=tran_id,
                account_update_ref=trade_id,
                audit_reason=f"binance_income:{income_type}",
            )

        return cls(
            symbol=symbol,
            raw_income_type=income_type,
            income=income,
            asset=asset,
            time_ms=time_ms,
            tran_id=tran_id,
            trade_id=trade_id,
            capital_event=capital_event,
            attribution_status=attribution,
            info_tag=info_tag,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "income_type": self.raw_income_type,
            "income": self.income,
            "asset": self.asset,
            "time_ms": self.time_ms,
            "tran_id": self.tran_id,
            "trade_id": self.trade_id,
            "is_unmapped": self.is_unmapped,
            "attribution_status": self.attribution_status.value,
            "info_tag": self.info_tag,
            "capital_event": self.capital_event.to_dict() if self.capital_event else None,
        }


@dataclass(frozen=True)
class BinanceIncomeSummary:
    """Funding / fee / realized-PnL summary derived from income events.

    Wraps a PR110 :class:`CapitalEventLedger` so funding is kept strictly
    separate from trading PnL. Unknown income types are tallied
    separately and never enter the ledger.
    """

    ledger: CapitalEventLedger
    event_count: int
    unknown_count: int
    unknown_total: float
    unattributed_funding_count: int

    @property
    def gross_realized_pnl(self) -> float:
        return self.ledger.total_realized_pnl

    @property
    def commission_total(self) -> float:
        return self.ledger.total_fees

    @property
    def funding_total(self) -> float:
        return self.ledger.total_funding

    @property
    def net_strategy_pnl(self) -> float:
        return self.ledger.net_strategy_pnl

    @property
    def external_deposit_total(self) -> float:
        return self.ledger.total_external_deposits

    @property
    def external_withdrawal_total(self) -> float:
        return self.ledger.total_external_withdrawals

    @property
    def internal_transfer_total(self) -> float:
        return self.ledger.total_internal_transfers

    def to_dict(self) -> dict[str, Any]:
        return {
            "gross_realized_pnl": self.gross_realized_pnl,
            "commission_total": self.commission_total,
            "funding_total": self.funding_total,
            "net_strategy_pnl": self.net_strategy_pnl,
            "external_deposit_total": self.external_deposit_total,
            "external_withdrawal_total": self.external_withdrawal_total,
            "internal_transfer_total": self.internal_transfer_total,
            "unknown_count": self.unknown_count,
            "unknown_total": self.unknown_total,
            "unattributed_funding_count": self.unattributed_funding_count,
            "event_count": self.event_count,
        }


def classify_income_rows(rows: list[dict[str, Any]]) -> list[BinanceIncomeEvent]:
    """Classify a list of Binance income rows into capital events."""
    return [BinanceIncomeEvent.from_row(row) for row in (rows or [])]


def summarise_income_events(events: list[BinanceIncomeEvent]) -> BinanceIncomeSummary:
    """Fold classified income events into a PR110-backed summary.

    Funding is kept separate from trading PnL by the PR110 ledger.
    Unknown / unmapped rows are tallied separately and never enter the
    ledger.
    """

    ledger = CapitalEventLedger()
    unknown_count = 0
    unknown_total = 0.0
    unattributed_funding = 0

    for ev in events:
        if ev.capital_event is None:
            unknown_count += 1
            unknown_total += ev.income
            continue
        ledger.apply(ev.capital_event)
        if (
            ev.is_funding
            and ev.attribution_status
            is AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
        ):
            unattributed_funding += 1

    return BinanceIncomeSummary(
        ledger=ledger,
        event_count=len(events),
        unknown_count=unknown_count,
        unknown_total=unknown_total,
        unattributed_funding_count=unattributed_funding,
    )


__all__ = [
    "AttributionStatus",
    "BinanceIncomeEvent",
    "BinanceIncomeSummary",
    "KNOWN_BINANCE_INCOME_TYPES",
    "UNKNOWN_INCOME_TYPE_TAG",
    "map_income_type",
    "classify_income_rows",
    "summarise_income_events",
]
