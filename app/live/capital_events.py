"""Capital Event contract for the Live API Integration Pack (PR111).

Binance USDT-M futures income rows (``/fapi/v1/income``) are classified
into a single, auditable Capital Event contract so that funding fees,
commissions, realized PnL, and wallet transfers are accounted for
separately and never mixed.

HANDOFF(PR110): the PR110 brief introduces a "Capital Event Contract".
While PR110 is in review, this module ships a self-contained
:class:`CapitalEvent` shaped to be unified with PR110's once both land.
The classification logic (``classify_income_*``) is deliberately
independent of the existing :mod:`app.capital` module so it can be wired
into either contract.

PR111 funding / fee accounting rules
------------------------------------

1. Funding fee is NEVER mixed with trading price PnL.
2. The PnL summary computes:
       gross_realized_pnl
       commission_total
       funding_total
       net_strategy_pnl = realized_pnl - fees + funding
3. ``trade_id`` / ``symbol`` / ``time`` are preserved when present for
   later trade/position attribution.
4. Funding that cannot yet be attributed to a ``trade_id`` is stored as
   an account-level funding event with
   ``attribution_status = UNATTRIBUTED_PENDING_POSITION_LINK``.

HANDOFF(PR113/PR114): position-level funding attribution MUST be added
before real live PnL is considered final. PR111 only does account-level
classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Capital event taxonomy
# ---------------------------------------------------------------------------
class CapitalEventType(str, Enum):
    """Canonical capital-event categories.

    Mirrors the PR111 brief mapping for Binance income rows.
    """

    REALIZED_PNL = "REALIZED_PNL"          # realized trading profit (>= 0)
    REALIZED_LOSS = "REALIZED_LOSS"        # realized trading loss (< 0)
    FUNDING_FEE = "FUNDING_FEE"            # funding paid out (< 0)
    FUNDING_INCOME = "FUNDING_INCOME"      # funding received (>= 0)
    FEE = "FEE"                            # trading commission
    TRANSFER_IN = "TRANSFER_IN"            # wallet transfer into futures
    TRANSFER_OUT = "TRANSFER_OUT"          # wallet transfer out of futures
    EXTERNAL_DEPOSIT = "EXTERNAL_DEPOSIT"  # inferable external deposit
    EXTERNAL_WITHDRAWAL = "EXTERNAL_WITHDRAWAL"  # inferable external withdrawal
    UNKNOWN = "UNKNOWN"                    # unknown / unmapped income type


class AttributionStatus(str, Enum):
    """Whether a capital event is linked to a specific trade/position."""

    ATTRIBUTED = "ATTRIBUTED"
    UNATTRIBUTED_PENDING_POSITION_LINK = "UNATTRIBUTED_PENDING_POSITION_LINK"
    NOT_APPLICABLE = "NOT_APPLICABLE"


#: Raw Binance income types we explicitly recognise and map to a non-UNKNOWN
#: capital-event category. Anything not in this set is preserved as
#: ``raw_income_type`` with capital_event_type=UNKNOWN (never dropped).
KNOWN_BINANCE_INCOME_TYPES: frozenset[str] = frozenset(
    {
        "REALIZED_PNL",
        "FUNDING_FEE",
        "COMMISSION",
        "TRANSFER",
        "INTERNAL_TRANSFER",
        "COMMISSION_REBATE",
        "API_REBATE",
        "REFERRAL_KICKBACK",
        "WELCOME_BONUS",
    }
)

UNKNOWN_INCOME_TYPE_TAG = "UNKNOWN_INCOME_TYPE"


@dataclass(frozen=True)
class CapitalEvent:
    """A single classified capital event.

    The event carries the classified category, the signed amount, the
    asset, and best-effort attribution metadata. ``raw_income_type``
    preserves the original Binance income type so an unknown row is never
    silently dropped.
    """

    capital_event_type: CapitalEventType
    amount: float
    asset: str = "USDT"
    symbol: str | None = None
    trade_id: str | None = None
    time_ms: int | None = None
    tran_id: str | None = None
    raw_income_type: str = ""
    attribution_status: AttributionStatus = AttributionStatus.NOT_APPLICABLE
    info_tag: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capital_event_type": self.capital_event_type.value,
            "amount": float(self.amount),
            "asset": self.asset,
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "time_ms": self.time_ms,
            "tran_id": self.tran_id,
            "raw_income_type": self.raw_income_type,
            "attribution_status": self.attribution_status.value,
            "info_tag": self.info_tag,
        }


@dataclass(frozen=True)
class CapitalPnLSummary:
    """Aggregate funding / fee / realized PnL summary.

    Funding is kept strictly separate from trading price PnL.
    ``net_strategy_pnl = gross_realized_pnl - commission_total + funding_total``.
    """

    gross_realized_pnl: float
    commission_total: float
    funding_total: float
    transfer_in_total: float
    transfer_out_total: float
    unknown_total: float
    unattributed_funding_count: int
    event_count: int

    @property
    def net_strategy_pnl(self) -> float:
        # commission_total is stored as a positive magnitude of fees paid.
        return self.gross_realized_pnl - self.commission_total + self.funding_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "gross_realized_pnl": self.gross_realized_pnl,
            "commission_total": self.commission_total,
            "funding_total": self.funding_total,
            "net_strategy_pnl": self.net_strategy_pnl,
            "transfer_in_total": self.transfer_in_total,
            "transfer_out_total": self.transfer_out_total,
            "unknown_total": self.unknown_total,
            "unattributed_funding_count": self.unattributed_funding_count,
            "event_count": self.event_count,
        }


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


def classify_income_row(row: dict[str, Any]) -> CapitalEvent:
    """Classify ONE Binance income row into a :class:`CapitalEvent`.

    A Binance income row (``/fapi/v1/income``) looks like::

        {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE",
         "income": "-0.012", "asset": "USDT", "time": 1700000000000,
         "tranId": 9223, "tradeId": "12345"}

    The function never raises on a malformed row; an unparseable amount
    becomes ``0.0`` and an unknown ``incomeType`` is preserved as
    ``raw_income_type`` with ``capital_event_type = UNKNOWN``.
    """

    income_type = str(row.get("incomeType", "") or "").strip().upper()
    amount = _to_float(row.get("income"))
    asset = str(row.get("asset", "USDT") or "USDT").strip() or "USDT"
    symbol = _opt_str(row.get("symbol"))
    trade_id = _opt_str(row.get("tradeId"))
    tran_id = _opt_str(row.get("tranId"))
    time_ms = None
    if row.get("time") is not None:
        try:
            time_ms = int(row.get("time"))
        except (TypeError, ValueError):
            time_ms = None

    event_type: CapitalEventType
    attribution = AttributionStatus.NOT_APPLICABLE
    info_tag = ""

    if income_type == "REALIZED_PNL":
        event_type = (
            CapitalEventType.REALIZED_PNL if amount >= 0 else CapitalEventType.REALIZED_LOSS
        )
        attribution = (
            AttributionStatus.ATTRIBUTED
            if trade_id
            else AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
        )
    elif income_type == "FUNDING_FEE":
        event_type = (
            CapitalEventType.FUNDING_INCOME if amount >= 0 else CapitalEventType.FUNDING_FEE
        )
        # Funding is account-level until a later PR links it to a position.
        attribution = (
            AttributionStatus.ATTRIBUTED
            if trade_id
            else AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
        )
    elif income_type in ("COMMISSION", "COMMISSION_REBATE", "API_REBATE", "REFERRAL_KICKBACK"):
        event_type = CapitalEventType.FEE
        attribution = (
            AttributionStatus.ATTRIBUTED
            if trade_id
            else AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
        )
        if income_type != "COMMISSION":
            info_tag = income_type
    elif income_type in ("TRANSFER", "INTERNAL_TRANSFER"):
        event_type = (
            CapitalEventType.TRANSFER_IN if amount >= 0 else CapitalEventType.TRANSFER_OUT
        )
        if income_type == "INTERNAL_TRANSFER":
            info_tag = "INTERNAL_TRANSFER"
    elif income_type in ("WELCOME_BONUS",):
        # A bonus credit is inferable as an external (non-trading) deposit.
        event_type = CapitalEventType.EXTERNAL_DEPOSIT
        info_tag = income_type
    else:
        event_type = CapitalEventType.UNKNOWN
        info_tag = UNKNOWN_INCOME_TYPE_TAG

    return CapitalEvent(
        capital_event_type=event_type,
        amount=amount,
        asset=asset,
        symbol=symbol,
        trade_id=trade_id,
        time_ms=time_ms,
        tran_id=tran_id,
        raw_income_type=income_type,
        attribution_status=attribution,
        info_tag=info_tag,
    )


def classify_income_rows(rows: list[dict[str, Any]]) -> list[CapitalEvent]:
    """Classify a list of Binance income rows."""
    return [classify_income_row(row) for row in (rows or [])]


def summarise_capital_events(events: list[CapitalEvent]) -> CapitalPnLSummary:
    """Aggregate classified capital events into a :class:`CapitalPnLSummary`.

    Funding is kept strictly separate from trading price PnL.
    """

    gross_realized = 0.0
    commission_total = 0.0
    funding_total = 0.0
    transfer_in = 0.0
    transfer_out = 0.0
    unknown_total = 0.0
    unattributed_funding = 0

    for ev in events:
        t = ev.capital_event_type
        if t in (CapitalEventType.REALIZED_PNL, CapitalEventType.REALIZED_LOSS):
            gross_realized += ev.amount
        elif t in (CapitalEventType.FUNDING_FEE, CapitalEventType.FUNDING_INCOME):
            funding_total += ev.amount
            if ev.attribution_status == AttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK:
                unattributed_funding += 1
        elif t == CapitalEventType.FEE:
            # Store commission as a positive magnitude of fees paid. A
            # rebate (positive income) reduces the magnitude.
            commission_total += -ev.amount
        elif t in (CapitalEventType.TRANSFER_IN, CapitalEventType.EXTERNAL_DEPOSIT):
            transfer_in += ev.amount
        elif t in (CapitalEventType.TRANSFER_OUT, CapitalEventType.EXTERNAL_WITHDRAWAL):
            transfer_out += ev.amount
        elif t == CapitalEventType.UNKNOWN:
            unknown_total += ev.amount

    return CapitalPnLSummary(
        gross_realized_pnl=gross_realized,
        commission_total=commission_total,
        funding_total=funding_total,
        transfer_in_total=transfer_in,
        transfer_out_total=transfer_out,
        unknown_total=unknown_total,
        unattributed_funding_count=unattributed_funding,
        event_count=len(events),
    )


__all__ = [
    "CapitalEventType",
    "AttributionStatus",
    "CapitalEvent",
    "CapitalPnLSummary",
    "KNOWN_BINANCE_INCOME_TYPES",
    "UNKNOWN_INCOME_TYPE_TAG",
    "classify_income_row",
    "classify_income_rows",
    "summarise_capital_events",
]
