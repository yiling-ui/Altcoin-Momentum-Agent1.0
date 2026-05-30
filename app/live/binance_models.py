"""Binance live API data models for the Live API Integration Pack (PR111).

Frozen dataclasses parsed from Binance USDT-M futures REST responses.
None of these models carries an API key / secret / signature. The
account / balance / position models are read-only views; PR111 never
mutates exchange state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.live.capital_events import CapitalEvent, classify_income_row
from app.live.status import HealthStatus


# ---------------------------------------------------------------------------
# Symbol filters / exchangeInfo
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinanceSymbolFilter:
    """Per-symbol precision + notional rules parsed from exchangeInfo."""

    symbol: str
    status: str = "TRADING"
    contract_type: str = "PERPETUAL"
    base_asset: str = ""
    quote_asset: str = "USDT"
    tick_size: float = 0.0
    step_size: float = 0.0
    min_qty: float = 0.0
    max_qty: float = 0.0
    min_notional: float = 0.0
    price_precision: int = 0
    quantity_precision: int = 0

    @property
    def is_tradable(self) -> bool:
        return self.status == "TRADING"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "contract_type": self.contract_type,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "tick_size": self.tick_size,
            "step_size": self.step_size,
            "min_qty": self.min_qty,
            "max_qty": self.max_qty,
            "min_notional": self.min_notional,
            "price_precision": self.price_precision,
            "quantity_precision": self.quantity_precision,
        }


@dataclass(frozen=True)
class BinanceExchangeInfoSnapshot:
    """Parsed exchangeInfo: a map of symbol -> :class:`BinanceSymbolFilter`."""

    timestamp_ms: int
    filters: dict[str, BinanceSymbolFilter] = field(default_factory=dict)

    @property
    def symbol_count(self) -> int:
        return len(self.filters)

    def get(self, symbol: str) -> BinanceSymbolFilter | None:
        return self.filters.get(symbol)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "symbol_count": self.symbol_count,
            "symbols": sorted(self.filters.keys()),
        }


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_exchange_info(body: dict[str, Any]) -> BinanceExchangeInfoSnapshot:
    """Parse a Binance USDT-M futures exchangeInfo body."""

    filters: dict[str, BinanceSymbolFilter] = {}
    for sym in body.get("symbols", []) or []:
        symbol = str(sym.get("symbol", "") or "")
        if not symbol:
            continue
        tick_size = 0.0
        step_size = 0.0
        min_qty = 0.0
        max_qty = 0.0
        min_notional = 0.0
        for f in sym.get("filters", []) or []:
            ftype = f.get("filterType")
            if ftype == "PRICE_FILTER":
                tick_size = _to_float(f.get("tickSize"))
            elif ftype == "LOT_SIZE":
                step_size = _to_float(f.get("stepSize"))
                min_qty = _to_float(f.get("minQty"))
                max_qty = _to_float(f.get("maxQty"))
            elif ftype in ("MIN_NOTIONAL", "NOTIONAL"):
                min_notional = _to_float(f.get("notional") or f.get("minNotional"))
        filters[symbol] = BinanceSymbolFilter(
            symbol=symbol,
            status=str(sym.get("status", "TRADING") or "TRADING"),
            contract_type=str(sym.get("contractType", "PERPETUAL") or "PERPETUAL"),
            base_asset=str(sym.get("baseAsset", "") or ""),
            quote_asset=str(sym.get("quoteAsset", "USDT") or "USDT"),
            tick_size=tick_size,
            step_size=step_size,
            min_qty=min_qty,
            max_qty=max_qty,
            min_notional=min_notional,
            price_precision=_to_int(sym.get("pricePrecision")),
            quantity_precision=_to_int(sym.get("quantityPrecision")),
        )
    timestamp = _to_int(body.get("serverTime"), default=0)
    return BinanceExchangeInfoSnapshot(timestamp_ms=timestamp, filters=filters)


# ---------------------------------------------------------------------------
# Account / balance / position
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinanceBalanceSnapshot:
    """A single per-asset balance row."""

    asset: str
    wallet_balance: float = 0.0
    available_balance: float = 0.0
    cross_unrealized_pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance,
            "cross_unrealized_pnl": self.cross_unrealized_pnl,
        }


@dataclass(frozen=True)
class BinancePositionSnapshot:
    """A single open / flat position row (read-only)."""

    symbol: str
    position_amt: float = 0.0
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    leverage: float = 0.0
    margin_type: str = ""
    position_side: str = "BOTH"

    @property
    def is_open(self) -> bool:
        return abs(self.position_amt) > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "position_amt": self.position_amt,
            "entry_price": self.entry_price,
            "unrealized_pnl": self.unrealized_pnl,
            "leverage": self.leverage,
            "margin_type": self.margin_type,
            "position_side": self.position_side,
        }


@dataclass(frozen=True)
class BinanceAccountSnapshot:
    """Read-only account snapshot parsed from ``/fapi/v2/account``."""

    timestamp_ms: int
    total_wallet_balance: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_margin_balance: float = 0.0
    available_balance: float = 0.0
    fee_tier: int = 0
    can_trade: bool = False
    can_deposit: bool = False
    can_withdraw: bool = False
    balances: tuple[BinanceBalanceSnapshot, ...] = ()
    positions: tuple[BinancePositionSnapshot, ...] = ()

    @property
    def open_position_count(self) -> int:
        return sum(1 for p in self.positions if p.is_open)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "total_wallet_balance": self.total_wallet_balance,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_margin_balance": self.total_margin_balance,
            "available_balance": self.available_balance,
            "fee_tier": self.fee_tier,
            "can_trade": self.can_trade,
            "can_deposit": self.can_deposit,
            "can_withdraw": self.can_withdraw,
            "balance_count": len(self.balances),
            "open_position_count": self.open_position_count,
        }


def parse_account(body: dict[str, Any], *, timestamp_ms: int = 0) -> BinanceAccountSnapshot:
    """Parse a Binance USDT-M futures ``/fapi/v2/account`` body."""

    balances: list[BinanceBalanceSnapshot] = []
    for a in body.get("assets", []) or []:
        balances.append(
            BinanceBalanceSnapshot(
                asset=str(a.get("asset", "") or ""),
                wallet_balance=_to_float(a.get("walletBalance")),
                available_balance=_to_float(a.get("availableBalance")),
                cross_unrealized_pnl=_to_float(a.get("crossUnPnl")),
            )
        )
    positions: list[BinancePositionSnapshot] = []
    for p in body.get("positions", []) or []:
        positions.append(
            BinancePositionSnapshot(
                symbol=str(p.get("symbol", "") or ""),
                position_amt=_to_float(p.get("positionAmt")),
                entry_price=_to_float(p.get("entryPrice")),
                unrealized_pnl=_to_float(p.get("unrealizedProfit")),
                leverage=_to_float(p.get("leverage")),
                margin_type=str(p.get("marginType", "") or ""),
                position_side=str(p.get("positionSide", "BOTH") or "BOTH"),
            )
        )
    return BinanceAccountSnapshot(
        timestamp_ms=timestamp_ms,
        total_wallet_balance=_to_float(body.get("totalWalletBalance")),
        total_unrealized_pnl=_to_float(body.get("totalUnrealizedProfit")),
        total_margin_balance=_to_float(body.get("totalMarginBalance")),
        available_balance=_to_float(body.get("availableBalance")),
        fee_tier=_to_int(body.get("feeTier")),
        can_trade=bool(body.get("canTrade", False)),
        can_deposit=bool(body.get("canDeposit", False)),
        can_withdraw=bool(body.get("canWithdraw", False)),
        balances=tuple(balances),
        positions=tuple(positions),
    )


# ---------------------------------------------------------------------------
# Income events
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinanceIncomeEvent:
    """A single Binance income row plus its classified capital event."""

    symbol: str | None
    income_type: str
    income: float
    asset: str
    time_ms: int | None
    tran_id: str | None
    trade_id: str | None
    capital_event: CapitalEvent

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "BinanceIncomeEvent":
        capital_event = classify_income_row(row)
        return cls(
            symbol=capital_event.symbol,
            income_type=capital_event.raw_income_type,
            income=capital_event.amount,
            asset=capital_event.asset,
            time_ms=capital_event.time_ms,
            tran_id=capital_event.tran_id,
            trade_id=capital_event.trade_id,
            capital_event=capital_event,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "income_type": self.income_type,
            "income": self.income,
            "asset": self.asset,
            "time_ms": self.time_ms,
            "tran_id": self.tran_id,
            "trade_id": self.trade_id,
            "capital_event": self.capital_event.to_dict(),
        }


# ---------------------------------------------------------------------------
# Permission + health results
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinancePermissionSnapshot:
    """Permission view inferred from the account read.

    PR111 does NOT require withdraw permission. If the key reports a
    high-risk permission (withdraw / internal-transfer), a warning is
    produced. ``can_trade_if_account_reports_it`` mirrors the exchange's
    own ``canTrade`` flag - it is NOT a runtime authorisation to trade.
    """

    can_read: bool = False
    can_trade_if_account_reports_it: bool = False
    can_deposit: bool = False
    can_withdraw: bool = False
    high_risk_permission_warning: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_read": self.can_read,
            "can_trade_if_account_reports_it": self.can_trade_if_account_reports_it,
            "can_deposit": self.can_deposit,
            "can_withdraw": self.can_withdraw,
            "high_risk_permission_warning": self.high_risk_permission_warning,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class BinanceApiHealthResult:
    """Aggregate Binance health-check result (public + private read + trade)."""

    status: HealthStatus
    public_market_ok: bool = False
    private_read_ok: bool = False
    private_trade_configured: bool = False
    private_trade_enabled_by_config: bool = False
    private_trade_blocked_by_mode: bool = True
    can_read_account: bool = False
    can_read_positions: bool = False
    can_read_income: bool = False
    can_trade_if_account_reports_it: bool = False
    high_risk_permission_warning: bool = False
    server_time_ms: int | None = None
    symbol_count: int = 0
    open_position_count: int = 0
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    masked_api_key: str = "<absent>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "public_market_ok": self.public_market_ok,
            "private_read_ok": self.private_read_ok,
            "private_trade_configured": self.private_trade_configured,
            "private_trade_enabled_by_config": self.private_trade_enabled_by_config,
            "private_trade_blocked_by_mode": self.private_trade_blocked_by_mode,
            "can_read_account": self.can_read_account,
            "can_read_positions": self.can_read_positions,
            "can_read_income": self.can_read_income,
            "can_trade_if_account_reports_it": self.can_trade_if_account_reports_it,
            "high_risk_permission_warning": self.high_risk_permission_warning,
            "server_time_ms": self.server_time_ms,
            "symbol_count": self.symbol_count,
            "open_position_count": self.open_position_count,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "masked_api_key": self.masked_api_key,
        }


__all__ = [
    "BinanceSymbolFilter",
    "BinanceExchangeInfoSnapshot",
    "BinanceBalanceSnapshot",
    "BinancePositionSnapshot",
    "BinanceAccountSnapshot",
    "BinanceIncomeEvent",
    "BinancePermissionSnapshot",
    "BinanceApiHealthResult",
    "parse_exchange_info",
    "parse_account",
]
