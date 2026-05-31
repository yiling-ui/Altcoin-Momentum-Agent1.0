"""Binance live API data models for the Live API Integration Pack (PR111).

Frozen dataclasses parsed from Binance USDT-M futures REST responses.
None of these models carries an API key / secret / signature. The
account / balance / position models are read-only views; PR111 never
mutates exchange state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# BinanceIncomeEvent lives in app.live.binance_income (it maps onto PR110's
# Capital Event contract). Re-exported here for backward compatibility so
# callers can keep importing it from app.live.binance_models.
from app.live.binance_income import BinanceIncomeEvent
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
# API-key restrictions (the AUTHORITATIVE permission source)
# ---------------------------------------------------------------------------
# Sentinel used in sanitised debug output for a permission field that the
# Binance API did NOT expose. A missing field is NEVER treated as ``True``.
NOT_REPORTED: str = "NOT_REPORTED"

# Map of raw Binance ``apiRestrictions`` camelCase field -> snapshot attr.
# These are the ONLY fields that may drive a key-permission warning.
_RESTRICTION_FIELD_MAP: dict[str, str] = {
    "ipRestrict": "ip_restrict",
    "enableReading": "enable_reading",
    "enableWithdrawals": "enable_withdrawals",
    "enableInternalTransfer": "enable_internal_transfer",
    "permitsUniversalTransfer": "permits_universal_transfer",
    "enableFutures": "enable_futures",
    "enableSpotAndMarginTrading": "enable_spot_and_margin_trading",
    "enableMargin": "enable_margin",
    "enableVanillaOptions": "enable_vanilla_options",
}

# Fields that may carry identifying / timing information and must NEVER be
# echoed in debug output (no account id, no create time, no expiry).
_RESTRICTION_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {"createTime", "tradingAuthorityExpirationTime", "accountId", "uid", "id"}
)


def _to_tristate_bool(value: Any) -> bool | None:
    """Parse a raw value into ``True`` / ``False`` / ``None`` (NOT_REPORTED).

    Only an explicit boolean-ish value yields ``True`` / ``False``. Anything
    ambiguous (missing / unknown) yields ``None`` so it is reported as
    NOT_REPORTED rather than silently treated as enabled.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes", "on"}:
            return True
        if token in {"false", "0", "no", "off"}:
            return False
    return None


@dataclass(frozen=True)
class BinanceApiRestrictionsSnapshot:
    """API-KEY restriction view parsed from ``GET /sapi/v1/account/apiRestrictions``.

    This is the **only** authoritative source for the withdraw / transfer
    permission warnings. Each permission is tri-state:

      * ``True``  - Binance explicitly reported the field as enabled.
      * ``False`` - Binance explicitly reported the field as disabled.
      * ``None``  - Binance did NOT expose the field (NOT_REPORTED). It is
        NEVER inferred as ``True``.

    Account-level ``canWithdraw`` / ``canDeposit`` (from ``/fapi/v2/account``)
    are *account capabilities*, NOT *key permissions*, and must never drive a
    withdraw warning. ``reported`` is ``True`` only when at least one known
    restriction field was present in the response.
    """

    reported: bool = False
    ip_restrict: bool | None = None
    enable_reading: bool | None = None
    enable_withdrawals: bool | None = None
    enable_internal_transfer: bool | None = None
    permits_universal_transfer: bool | None = None
    enable_futures: bool | None = None
    enable_spot_and_margin_trading: bool | None = None
    enable_margin: bool | None = None
    enable_vanilla_options: bool | None = None
    raw_fields_seen: tuple[str, ...] = ()

    @staticmethod
    def _display(value: bool | None) -> Any:
        """Render a tri-state value for debug output (NOT_REPORTED for None)."""
        return NOT_REPORTED if value is None else bool(value)

    def to_debug_dict(self) -> dict[str, Any]:
        """Sanitised debug view. NEVER carries an API key / secret / id.

        Only the whitelisted raw permission field names + their tri-state
        values are surfaced (plus ``raw_permission_fields_seen``). No secret,
        signature, account id, create time, or expiry is ever included.
        """
        disp = self._display
        return {
            "raw_permission_fields_seen": list(self.raw_fields_seen),
            "restrictions_reported": self.reported,
            "enableWithdrawals": disp(self.enable_withdrawals),
            "enableInternalTransfer": disp(self.enable_internal_transfer),
            "permitsUniversalTransfer": disp(self.permits_universal_transfer),
            "enableFutures": disp(self.enable_futures),
            "enableSpotAndMarginTrading": disp(self.enable_spot_and_margin_trading),
            "enableReading": disp(self.enable_reading),
            "ipRestrict": disp(self.ip_restrict),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "reported": self.reported,
            "ip_restrict": self.ip_restrict,
            "enable_reading": self.enable_reading,
            "enable_withdrawals": self.enable_withdrawals,
            "enable_internal_transfer": self.enable_internal_transfer,
            "permits_universal_transfer": self.permits_universal_transfer,
            "enable_futures": self.enable_futures,
            "enable_spot_and_margin_trading": self.enable_spot_and_margin_trading,
            "enable_margin": self.enable_margin,
            "enable_vanilla_options": self.enable_vanilla_options,
            "raw_fields_seen": list(self.raw_fields_seen),
        }


def parse_api_restrictions(body: Any) -> BinanceApiRestrictionsSnapshot:
    """Parse a Binance ``/sapi/v1/account/apiRestrictions`` body.

    A missing / empty / malformed body yields a snapshot with
    ``reported=False`` and every permission ``None`` (NOT_REPORTED) - so a
    transport that does not expose the endpoint can NEVER produce a
    false-positive withdraw warning.
    """

    if not isinstance(body, dict) or not body:
        return BinanceApiRestrictionsSnapshot(reported=False)

    kwargs: dict[str, bool | None] = {}
    seen: list[str] = []
    for raw_name, attr in _RESTRICTION_FIELD_MAP.items():
        if raw_name in body:
            kwargs[attr] = _to_tristate_bool(body.get(raw_name))
            seen.append(raw_name)
    # Record any additional (non-sensitive) field NAMES the API exposed so an
    # operator can see exactly what came back - names only, never values.
    for raw_name in body.keys():
        if raw_name in _RESTRICTION_FIELD_MAP or raw_name in _RESTRICTION_SENSITIVE_FIELDS:
            continue
        seen.append(str(raw_name))

    return BinanceApiRestrictionsSnapshot(
        reported=len(kwargs) > 0,
        raw_fields_seen=tuple(seen),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Income events: see app.live.binance_income.BinanceIncomeEvent (imported
# above). It maps each Binance income row onto PR110's Capital Event
# contract (app.live.capital_event).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Permission + health results
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinancePermissionSnapshot:
    """Permission view built from the API-KEY restrictions (PR118).

    PR118 hard rule: the withdraw warning (``high_risk_permission_warning``)
    is set **only** when the raw ``apiRestrictions.enableWithdrawals`` field
    is explicitly ``True``. It is NEVER inferred from account-level
    capabilities (``canWithdraw`` / ``canDeposit`` / ``canTrade``) nor from
    transfer / futures / spot-margin permissions.

    Permission fields are tri-state (``True`` / ``False`` / ``None`` =
    NOT_REPORTED). ``can_trade_if_account_reports_it`` mirrors the exchange's
    own ``canTrade`` flag - it is INFO only, NOT a runtime trade
    authorisation. Universal / internal transfer are surfaced as their own
    (lower-severity) warnings, never as a withdraw warning.
    """

    can_read: bool = False
    can_trade_if_account_reports_it: bool = False
    # Tri-state key permissions sourced from /sapi/v1/account/apiRestrictions.
    withdraw_permission: bool | None = None
    internal_transfer_permission: bool | None = None
    universal_transfer_permission: bool | None = None
    futures_trade_permission: bool | None = None
    spot_margin_trade_permission: bool | None = None
    reading_permission: bool | None = None
    ip_restricted: bool | None = None
    restrictions_reported: bool = False
    high_risk_permission_warning: bool = False
    warnings: tuple[str, ...] = ()
    # Structured (severity, message) findings: BLOCKER / WARN / INFO.
    findings: tuple[tuple[str, str], ...] = ()
    # Sanitised debug view (NEVER carries a secret / signature / account id).
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_read": self.can_read,
            "can_trade_if_account_reports_it": self.can_trade_if_account_reports_it,
            "withdraw_permission": self.withdraw_permission,
            "internal_transfer_permission": self.internal_transfer_permission,
            "universal_transfer_permission": self.universal_transfer_permission,
            "futures_trade_permission": self.futures_trade_permission,
            "spot_margin_trade_permission": self.spot_margin_trade_permission,
            "reading_permission": self.reading_permission,
            "ip_restricted": self.ip_restricted,
            "restrictions_reported": self.restrictions_reported,
            "high_risk_permission_warning": self.high_risk_permission_warning,
            "warnings": list(self.warnings),
            "findings": [{"severity": s, "message": m} for s, m in self.findings],
            "debug": dict(self.debug),
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
    # PR118: tri-state API-KEY permissions sourced ONLY from the raw
    # /sapi/v1/account/apiRestrictions endpoint (None = NOT_REPORTED).
    withdraw_permission: bool | None = None
    universal_transfer_permission: bool | None = None
    internal_transfer_permission: bool | None = None
    futures_trade_permission: bool | None = None
    api_restrictions_reported: bool = False
    # Sanitised permission debug (raw field names + tri-state values only;
    # never an API key / secret / signature / account id).
    permission_debug: dict[str, Any] = field(default_factory=dict)
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
            "withdraw_permission": self.withdraw_permission,
            "universal_transfer_permission": self.universal_transfer_permission,
            "internal_transfer_permission": self.internal_transfer_permission,
            "futures_trade_permission": self.futures_trade_permission,
            "api_restrictions_reported": self.api_restrictions_reported,
            "permission_debug": dict(self.permission_debug),
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
    "BinanceApiRestrictionsSnapshot",
    "BinanceIncomeEvent",
    "BinancePermissionSnapshot",
    "BinanceApiHealthResult",
    "parse_exchange_info",
    "parse_account",
    "parse_api_restrictions",
    "NOT_REPORTED",
]
