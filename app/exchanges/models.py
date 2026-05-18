"""Read-only data models exchanged between the gateway and upstream
modules (Spec §13, §14, §16).

These are intentionally *narrow*: each model only carries the fields a
read-only consumer (Universe Filter, Liquidity Filter, MarketDataBuffer,
Reconciliation) actually needs. We do **not** ship order/position write
models in Phase 3 - those land in Issue #9 with the full Execution FSM.

Every model uses Pydantic v2 with `extra="forbid"` to make the schema
contract explicit; this matches the convention set by `app/core/models.py`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import DataReliability


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


# ---------------------------------------------------------------------------
# Symbol metadata (Spec §16, Universe Filter input)
# ---------------------------------------------------------------------------
class ExchangeSymbol(_Base):
    """Static metadata for a tradable symbol.

    Phase 3 only ships the read-only fields that the Universe Filter
    (Issue #5) and Risk Engine (Issue #7) need. Order-book filters,
    leverage brackets, fee tiers etc. land with their own consumers.
    """

    symbol: str
    base_asset: str
    quote_asset: str
    contract_type: str = "PERPETUAL"
    status: str = "TRADING"  # TRADING | BREAK | HALTED | DELISTED
    price_tick: float = 0.0
    qty_step: float = 0.0
    min_notional: float = 0.0


# ---------------------------------------------------------------------------
# Order book (Spec §14, §19, REST B-tier source)
# ---------------------------------------------------------------------------
class OrderBookLevel(_Base):
    price: float
    qty: float


class OrderBook(_Base):
    """A point-in-time snapshot of the order book.

    `bids` are sorted descending by price; `asks` are sorted ascending.
    `reliability` is filled in by the gateway and reflects the source.
    A WS-maintained depth-diff book is tier A (raw exchange data); a
    one-shot REST snapshot taken as a fallback when the WS link is
    degraded should be tagged tier B explicitly by the adapter that
    produced it. The default here is tier A because that is the canonical
    Phase 4+ source.
    """

    symbol: str
    timestamp: int  # ms
    bids: tuple[OrderBookLevel, ...] = Field(default_factory=tuple)
    asks: tuple[OrderBookLevel, ...] = Field(default_factory=tuple)
    reliability: DataReliability = DataReliability.A

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def mid_price(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @field_validator("bids")
    @classmethod
    def _validate_bid_order(cls, v: tuple[OrderBookLevel, ...]) -> tuple[OrderBookLevel, ...]:
        prices = [lvl.price for lvl in v]
        if any(prices[i] < prices[i + 1] for i in range(len(prices) - 1)):
            raise ValueError("bids must be sorted descending by price")
        return v

    @field_validator("asks")
    @classmethod
    def _validate_ask_order(cls, v: tuple[OrderBookLevel, ...]) -> tuple[OrderBookLevel, ...]:
        prices = [lvl.price for lvl in v]
        if any(prices[i] > prices[i + 1] for i in range(len(prices) - 1)):
            raise ValueError("asks must be sorted ascending by price")
        return v


# ---------------------------------------------------------------------------
# Recent trade (Spec §14, §20, WebSocket A-tier source)
# ---------------------------------------------------------------------------
class RecentTrade(_Base):
    """A single tape print.

    `is_buyer_maker` follows the Binance convention: if True, the
    aggressor was a *seller* (the buyer was the resting order). The
    Manipulation Detector (Issue #6) and CVD calculator (Issue #4) use
    this directly to compute aggression.
    """

    symbol: str
    trade_id: str
    timestamp: int  # ms
    price: float
    qty: float
    side: TradeSide
    is_buyer_maker: bool = False
    reliability: DataReliability = DataReliability.A


# ---------------------------------------------------------------------------
# Funding rate (Spec §14, §18, REST B-tier source)
# ---------------------------------------------------------------------------
class FundingRate(_Base):
    symbol: str
    timestamp: int  # ms
    rate: float  # e.g. 0.0001 = 0.01% / 8h
    next_funding_ts: int  # ms
    reliability: DataReliability = DataReliability.B


# ---------------------------------------------------------------------------
# Open interest (Spec §14, §18, REST B-tier source)
# ---------------------------------------------------------------------------
class OpenInterest(_Base):
    symbol: str
    timestamp: int  # ms
    open_interest: float  # in contracts
    open_interest_value: float | None = None  # in USDT-quote
    reliability: DataReliability = DataReliability.B


# ---------------------------------------------------------------------------
# Account snapshot (Spec §13.1, §27.4, REST B-tier source)
# ---------------------------------------------------------------------------
class AccountSnapshot(_Base):
    """Read-only account snapshot for Risk Engine / Capital Flow Engine.

    Phase 3 keeps the schema deliberately small. The Capital Flow Engine
    (Issue #8) extends this with realised PnL streams and withdrawal
    history.
    """

    timestamp: int  # ms
    total_equity: float
    available_balance: float
    margin_balance: float
    unrealized_pnl: float = 0.0
    open_position_count: int = 0
    reliability: DataReliability = DataReliability.B
