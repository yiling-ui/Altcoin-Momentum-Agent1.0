"""Fake live Binance / account / fee / funding engines (PR117 - Full-System
Single-Altcoin Live Sandbox Audit v0).

These fakes let the FULL, REAL PR110-PR116 live execution chain run end
to end without ever touching a real exchange:

  * :class:`FakeBinanceTransport` - a deterministic transport callable
    ``(method, url, headers) -> json`` that the REAL
    :class:`app.live.binance_execution_adapter.BinanceExecutionAdapter`
    calls instead of opening a socket. It can simulate a clean fill, a
    partial fill, an exchange reject, or a post-submit timeout, and it
    records every call so the audit can prove no duplicate order was
    ever sent.
  * :class:`FakeBinanceLiveAdapter` - wires the fake transport + a
    sandbox ``exchangeInfo`` into a real ``BinanceExecutionAdapter`` so
    the audit exercises the real compose/validate/parse code path.
  * :class:`FakeFeeEngine` - deterministic commission.
  * :class:`FakeFundingEngine` - deterministic funding fee / income.
  * :class:`FakeLiveAccount` - a tiny balance / equity / position book
    that keeps external flows separate from strategy PnL (via the PR110
    capital-event ledger).

Hard boundaries (PR117): no real order, no real socket, no real key. The
fake Binance config uses obviously-fake (but non-placeholder) sandbox
credentials and ``use_testnet=True`` so even a misfire could not reach
production; and the transport never performs IO regardless.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode
from app.live.api_config import BinanceApiConfig
from app.live.binance_execution_adapter import (
    BinanceExecutionAdapter,
    BinanceExecutionHttpError,
)
from app.live.binance_models import (
    BinanceAccountSnapshot,
    BinanceBalanceSnapshot,
    BinanceExchangeInfoSnapshot,
    BinancePositionSnapshot,
    BinanceSymbolFilter,
)
from app.live.capital_event import CapitalEventLedger, CapitalEventType, LiveCapitalEvent
from app.live.execution_errors import ExecutionAdapterError
from app.live.secrets import SecretValue

FAKE_LIVE_EXCHANGE_MODULE = "live.fake_live_exchange"

DEFAULT_SANDBOX_SYMBOL = "RAVEUSDT_SANDBOX"

# Order-behaviour selectors for the fake transport.
BEHAVIOR_FILL = "fill"
BEHAVIOR_PARTIAL = "partial"
BEHAVIOR_REJECT = "reject"
BEHAVIOR_TIMEOUT = "timeout"

# Status surfaced when a post-submit query fails / times out: the order
# may or may not have landed, so the audit ledger marks it for manual
# reconciliation and NEVER blind-retries (no duplicate order).
UNKNOWN_PENDING_RECONCILIATION = "UNKNOWN_PENDING_RECONCILIATION"


def build_sandbox_exchange_info(
    symbol: str = DEFAULT_SANDBOX_SYMBOL, *, timestamp_ms: int | None = None
) -> BinanceExchangeInfoSnapshot:
    """Build a one-symbol sandbox ``exchangeInfo`` snapshot.

    The filters are realistic for a sub-dollar altcoin: 0.0001 tick,
    whole-unit step, 1 minimum qty, 5 USDT minimum notional.
    """
    f = BinanceSymbolFilter(
        symbol=symbol,
        status="TRADING",
        contract_type="PERPETUAL",
        base_asset=symbol.replace("USDT_SANDBOX", "").replace("USDT", "") or "RAVE",
        quote_asset="USDT",
        tick_size=0.0001,
        step_size=1.0,
        min_qty=1.0,
        max_qty=1_000_000.0,
        min_notional=5.0,
        price_precision=4,
        quantity_precision=0,
    )
    return BinanceExchangeInfoSnapshot(
        timestamp_ms=timestamp_ms if timestamp_ms is not None else now_ms(),
        filters={symbol: f},
    )


def fake_sandbox_binance_config() -> BinanceApiConfig:
    """A fake-but-non-placeholder Binance config for the sandbox audit.

    ``enable_private_trade`` / ``enable_private_read`` are True and
    ``use_testnet`` is True so the REAL adapter's last-line authorisation
    predicate is satisfied for the all-gates fake LIVE_LIMITED case - yet
    the transport is a fake that never opens a socket, so no real order
    is ever sent and no real key is ever used.
    """
    return BinanceApiConfig(
        api_key=SecretValue(name="AMA_BINANCE_API_KEY", _raw="sandbox-fake-binance-key-117"),
        api_secret=SecretValue(
            name="AMA_BINANCE_API_SECRET", _raw="sandbox-fake-binance-secret-117"
        ),
        enable_private_read=True,
        enable_private_trade=True,
        use_testnet=True,
    )


@dataclass
class FakeTransportCall:
    """A single recorded transport call (method + path only; never the sig)."""

    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)


class FakeBinanceTransport:
    """A deterministic fake Binance transport (no socket, ever).

    The behaviour applied to an order POST is selected by ``behavior``:
    ``fill`` / ``partial`` / ``reject`` / ``timeout``. Every call is
    recorded so the audit can assert no duplicate order was sent.
    """

    def __init__(
        self,
        *,
        behavior: str = BEHAVIOR_FILL,
        fill_price: float = 1.0,
        partial_ratio: float = 0.4,
        reject_code: int = -2010,
        reject_msg: str = "Order would immediately trigger.",
    ) -> None:
        self.behavior = behavior
        self.fill_price = float(fill_price)
        self.partial_ratio = float(partial_ratio)
        self.reject_code = reject_code
        self.reject_msg = reject_msg
        self.calls: list[FakeTransportCall] = []
        self._last_order: dict[str, Any] | None = None

    @property
    def order_post_count(self) -> int:
        return sum(
            1
            for c in self.calls
            if c.method == "POST" and c.path.endswith("/fapi/v1/order")
        )

    def __call__(self, method: str, url: str, headers: Mapping[str, str]) -> Any:
        split = urllib.parse.urlsplit(url)
        path = split.path
        params = {
            k: (v[0] if isinstance(v, list) and v else v)
            for k, v in urllib.parse.parse_qs(split.query).items()
            if k not in ("signature", "timestamp", "recvWindow")
        }
        self.calls.append(FakeTransportCall(method=method, path=path, params=params))

        if path.endswith("/fapi/v1/order") and method == "POST":
            return self._handle_order(params)
        if path.endswith("/fapi/v1/order") and method == "GET":
            # Idempotent status read: return the last order body (or NEW).
            return self._last_order or self._order_body(params, status="NEW", filled_qty=0.0)
        if path.endswith("/fapi/v1/order") and method == "DELETE":
            body = self._order_body(params, status="CANCELED", filled_qty=0.0)
            return body
        if path.endswith("/fapi/v1/openOrders"):
            return []
        if path.endswith("/fapi/v1/userTrades"):
            return []
        # Default benign response.
        return {}

    # ------------------------------------------------------------------
    def _handle_order(self, params: Mapping[str, Any]) -> dict[str, Any]:
        if self.behavior == BEHAVIOR_REJECT:
            raise BinanceExecutionHttpError(self.reject_code, self.reject_msg)
        if self.behavior == BEHAVIOR_TIMEOUT:
            # Mimic the urllib transport's sanitised transport error. The
            # real adapter passes retries=0 for orders so this NEVER
            # duplicates the order.
            raise ExecutionAdapterError(
                "binance: transport error talking to /fapi/v1/order: timed out"
            )
        requested_qty = _to_float(params.get("quantity"))
        if self.behavior == BEHAVIOR_PARTIAL:
            filled = round(requested_qty * self.partial_ratio, 8)
            body = self._order_body(params, status="PARTIALLY_FILLED", filled_qty=filled)
        else:  # BEHAVIOR_FILL
            body = self._order_body(params, status="FILLED", filled_qty=requested_qty)
        self._last_order = body
        return body

    def _order_body(
        self, params: Mapping[str, Any], *, status: str, filled_qty: float
    ) -> dict[str, Any]:
        price = self.fill_price
        return {
            "orderId": 8800117,
            "clientOrderId": params.get("newClientOrderId")
            or params.get("origClientOrderId")
            or "",
            "symbol": params.get("symbol", DEFAULT_SANDBOX_SYMBOL),
            "status": status,
            "side": params.get("side", "BUY"),
            "type": params.get("type", "MARKET"),
            "price": params.get("price", "0"),
            "avgPrice": str(price) if filled_qty > 0 else "0",
            "executedQty": str(filled_qty),
            "cumQuote": str(round(filled_qty * price, 8)),
            "reduceOnly": params.get("reduceOnly", "false") in ("true", True),
            "updateTime": now_ms(),
        }


class FakeBinanceLiveAdapter:
    """A real :class:`BinanceExecutionAdapter` wired to a fake transport.

    Exposes the underlying adapter (``.adapter``) for the execution
    gateway and the transport (``.transport``) for call-count assertions.
    """

    name = "FakeBinanceLiveAdapter"

    def __init__(
        self,
        *,
        symbol: str = DEFAULT_SANDBOX_SYMBOL,
        behavior: str = BEHAVIOR_FILL,
        fill_price: float = 1.0,
        partial_ratio: float = 0.4,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_LIMITED,
        event_repo: Any | None = None,
    ) -> None:
        self.symbol = symbol
        self._config = fake_sandbox_binance_config()
        self.transport = FakeBinanceTransport(
            behavior=behavior, fill_price=fill_price, partial_ratio=partial_ratio
        )
        self.exchange_info = build_sandbox_exchange_info(symbol)
        self.adapter = BinanceExecutionAdapter(
            self._config,
            runtime_mode=runtime_mode,
            transport=self.transport,
            exchange_info=self.exchange_info,
            event_repo=event_repo,
        )

    @property
    def order_post_count(self) -> int:
        return self.transport.order_post_count


class FakeFeeEngine:
    """Deterministic commission (Binance USDT-M futures-style bps fees)."""

    def __init__(self, *, taker_fee_bps: float = 4.0, maker_fee_bps: float = 2.0) -> None:
        self.taker_fee_bps = float(taker_fee_bps)
        self.maker_fee_bps = float(maker_fee_bps)

    def commission(self, notional_usdt: float, *, maker: bool = False) -> float:
        """Return the commission (a positive cost) for ``notional_usdt``."""
        bps = self.maker_fee_bps if maker else self.taker_fee_bps
        return round(abs(float(notional_usdt)) * bps / 10_000.0, 8)


class FakeFundingEngine:
    """Deterministic funding fee / income.

    PR117 convention (the brief's pairing): the ``funding_negative_hold``
    scenario produces a funding FEE (a cost that reduces net PnL); the
    ``funding_positive_hold`` scenario produces funding INCOME (a gain
    that increases net PnL). The magnitude is ``|rate| * notional *
    intervals`` in both cases.
    """

    def magnitude(self, notional_usdt: float, funding_rate: float, *, intervals: int = 1) -> float:
        return round(abs(float(notional_usdt)) * abs(float(funding_rate)) * max(1, int(intervals)), 8)

    def funding_fee(self, notional_usdt: float, funding_rate: float, *, intervals: int = 1) -> float:
        """Funding paid (positive magnitude; folded into net PnL as negative)."""
        return self.magnitude(notional_usdt, funding_rate, intervals=intervals)

    def funding_income(self, notional_usdt: float, funding_rate: float, *, intervals: int = 1) -> float:
        """Funding received (positive magnitude; folded into net PnL as positive)."""
        return self.magnitude(notional_usdt, funding_rate, intervals=intervals)


@dataclass
class FakePosition:
    """A tiny open-position view for the fake account."""

    symbol: str
    side: str
    quantity: float
    entry_price: float
    leverage: float

    @property
    def notional_usdt(self) -> float:
        return abs(self.quantity) * self.entry_price


class FakeLiveAccount:
    """A tiny fake live account book.

    Tracks the wallet balance + open positions and keeps external flows
    (deposits / withdrawals) STRICTLY separate from strategy PnL via the
    PR110 :class:`CapitalEventLedger`. ``equity`` is the truthful balance;
    ``net_strategy_pnl`` excludes external flows.
    """

    def __init__(self, *, initial_balance_usdt: float = 10.0) -> None:
        self.ledger = CapitalEventLedger(
            initial_capital_usdt=float(initial_balance_usdt),
            current_balance_usdt=float(initial_balance_usdt),
        )
        self.positions: list[FakePosition] = []

    # -- balance / equity ----------------------------------------------
    @property
    def balance_usdt(self) -> float:
        return self.ledger.current_balance_usdt

    @property
    def equity_usdt(self) -> float:
        # Sandbox simplification: equity == wallet balance (no floating PnL
        # held separately; realised PnL is already folded into balance).
        return self.ledger.current_balance_usdt

    @property
    def net_strategy_pnl(self) -> float:
        return self.ledger.net_strategy_pnl

    @property
    def net_external_capital(self) -> float:
        return self.ledger.net_external_capital

    # -- capital events ------------------------------------------------
    def apply_event(
        self, event_type: CapitalEventType, amount_usdt: float, *, source: str = "fake_account"
    ) -> LiveCapitalEvent:
        ev = LiveCapitalEvent.create(
            event_type=event_type,
            amount_usdt=abs(float(amount_usdt)),
            balance_before=self.ledger.current_balance_usdt,
            source=source,
        )
        self.ledger.apply(ev)
        return ev

    def deposit(self, amount_usdt: float) -> LiveCapitalEvent:
        return self.apply_event(CapitalEventType.EXTERNAL_DEPOSIT, amount_usdt)

    def withdraw(self, amount_usdt: float) -> LiveCapitalEvent:
        return self.apply_event(CapitalEventType.EXTERNAL_WITHDRAWAL, amount_usdt)

    def realized_profit(self, amount_usdt: float) -> LiveCapitalEvent:
        return self.apply_event(CapitalEventType.REALIZED_PNL, amount_usdt)

    def realized_loss(self, amount_usdt: float) -> LiveCapitalEvent:
        return self.apply_event(CapitalEventType.REALIZED_LOSS, amount_usdt)

    def commission(self, amount_usdt: float) -> LiveCapitalEvent:
        return self.apply_event(CapitalEventType.FEE, amount_usdt)

    def funding_fee(self, amount_usdt: float) -> LiveCapitalEvent:
        return self.apply_event(CapitalEventType.FUNDING_FEE, amount_usdt)

    def funding_income(self, amount_usdt: float) -> LiveCapitalEvent:
        return self.apply_event(CapitalEventType.FUNDING_INCOME, amount_usdt)

    # -- positions -----------------------------------------------------
    def open_position(self, symbol: str, side: str, quantity: float, entry_price: float, leverage: float) -> FakePosition:
        pos = FakePosition(
            symbol=symbol, side=side, quantity=quantity, entry_price=entry_price, leverage=leverage
        )
        self.positions.append(pos)
        return pos

    def flat(self) -> None:
        self.positions.clear()

    # -- snapshot ------------------------------------------------------
    def to_account_snapshot(self) -> BinanceAccountSnapshot:
        """Build a read-only :class:`BinanceAccountSnapshot` for risk eval."""
        positions = tuple(
            BinancePositionSnapshot(
                symbol=p.symbol,
                position_amt=p.quantity if p.side == "LONG" else -p.quantity,
                entry_price=p.entry_price,
                unrealized_pnl=0.0,
                leverage=p.leverage,
                margin_type="isolated",
            )
            for p in self.positions
        )
        bal = self.ledger.current_balance_usdt
        return BinanceAccountSnapshot(
            timestamp_ms=now_ms(),
            total_wallet_balance=bal,
            total_unrealized_pnl=0.0,
            total_margin_balance=bal,
            available_balance=bal,
            can_trade=True,
            can_deposit=True,
            can_withdraw=True,
            balances=(BinanceBalanceSnapshot(asset="USDT", wallet_balance=bal, available_balance=bal),),
            positions=positions,
        )


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "FAKE_LIVE_EXCHANGE_MODULE",
    "DEFAULT_SANDBOX_SYMBOL",
    "BEHAVIOR_FILL",
    "BEHAVIOR_PARTIAL",
    "BEHAVIOR_REJECT",
    "BEHAVIOR_TIMEOUT",
    "UNKNOWN_PENDING_RECONCILIATION",
    "build_sandbox_exchange_info",
    "fake_sandbox_binance_config",
    "FakeTransportCall",
    "FakeBinanceTransport",
    "FakeBinanceLiveAdapter",
    "FakeFeeEngine",
    "FakeFundingEngine",
    "FakePosition",
    "FakeLiveAccount",
]
