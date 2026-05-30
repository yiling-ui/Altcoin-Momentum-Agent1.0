"""Live Capital State (PR112 - Live Capital / Risk / Funding-Aware PnL v0).

Builds a read-only :class:`LiveCapitalState` from the PR111 Binance
private-read account snapshot (:class:`app.live.binance_models.
BinanceAccountSnapshot`) + open-order count. The state is the single
truthful view of the real account that the PR112 live capital / risk
engine consumes.

PR112 boundary (hard):
  - This module READS a real account snapshot only. It NEVER places /
    cancels an order, changes leverage, changes margin mode, switches
    runtime mode, or auto-escalates a capital profile.
  - ``real_orders_allowed`` is forced ``False`` on every state in PR112
    (no live execution adapter exists; PR113 owns the execution gateway).
  - ``exchange_live_orders`` is forced ``False``.
  - ``source`` is always ``BINANCE_PRIVATE_READ``.

The account id is only ever stored masked (``account_id_masked``); the
raw value never enters a state object, an event payload, or a Telegram
card.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode
from app.live.binance_models import (
    BinanceAccountSnapshot,
    BinancePositionSnapshot,
)
from app.live.capital_profile import CapitalProfileId
from app.live.secrets import mask_secret

# The only data source PR112 ever attributes a live capital state to.
LIVE_CAPITAL_STATE_SOURCE = "BINANCE_PRIVATE_READ"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _position_side(position_amt: float) -> str:
    if position_amt > 0:
        return "LONG"
    if position_amt < 0:
        return "SHORT"
    return "FLAT"


def _margin_label(margin_type: str) -> str:
    """Normalise Binance ``marginType`` to ``isolated`` / ``cross`` / ``--``."""
    t = (margin_type or "").strip().lower()
    if t in ("isolated", "isolated_margin"):
        return "isolated"
    if t in ("cross", "crossed", "cross_margin"):
        return "cross"
    return "--"


@dataclass(frozen=True)
class LivePosition:
    """A single read-only open position view (PR112).

    Built from a PR111 :class:`BinancePositionSnapshot`. ``mark_price``
    and ``liquidation_price`` are not present on the v2/account parse, so
    they may be enriched from a ``/fapi/v2/positionRisk`` row when
    available; otherwise they fall back to ``entry_price`` / ``None``.
    """

    symbol: str
    side: str
    position_amt: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    notional_usdt: float
    leverage: float
    isolated_or_cross: str
    liquidation_price: float | None
    update_time: int | None

    @property
    def is_open(self) -> bool:
        return abs(self.position_amt) > 0.0

    @classmethod
    def from_binance(
        cls,
        snapshot: BinancePositionSnapshot,
        *,
        mark_price: float | None = None,
        liquidation_price: float | None = None,
        update_time: int | None = None,
    ) -> "LivePosition":
        amt = _to_float(snapshot.position_amt)
        entry = _to_float(snapshot.entry_price)
        mark = _to_float(mark_price) if mark_price is not None else entry
        # Notional is computed from the mark price when available so the
        # position's current exposure is honest; fall back to entry.
        ref_price = mark if mark > 0 else entry
        notional = abs(amt) * ref_price
        return cls(
            symbol=snapshot.symbol,
            side=_position_side(amt),
            position_amt=amt,
            entry_price=entry,
            mark_price=mark,
            unrealized_pnl=_to_float(snapshot.unrealized_pnl),
            notional_usdt=notional,
            leverage=_to_float(snapshot.leverage),
            isolated_or_cross=_margin_label(snapshot.margin_type),
            liquidation_price=(
                _to_float(liquidation_price)
                if liquidation_price is not None
                else None
            ),
            update_time=update_time,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "position_amt": self.position_amt,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "unrealized_pnl": self.unrealized_pnl,
            "notional_usdt": self.notional_usdt,
            "leverage": self.leverage,
            "isolated_or_cross": self.isolated_or_cross,
            "liquidation_price": self.liquidation_price,
            "update_time": self.update_time,
        }


@dataclass(frozen=True)
class LiveCapitalState:
    """Read-only truthful view of the real account (PR112).

    Built from a PR111 :class:`BinanceAccountSnapshot`. Every field is a
    measurement / state flag. The object carries the PR112 safety
    markers (``real_orders_allowed=False`` / ``exchange_live_orders=False``)
    so a reviewer can assert them directly.
    """

    account_id_masked: str
    runtime_mode: LiveRuntimeMode
    capital_profile_id: CapitalProfileId
    wallet_balance_usdt: float
    available_balance_usdt: float
    account_equity_usdt: float
    unrealized_pnl_usdt: float
    used_margin_usdt: float
    free_margin_usdt: float
    open_position_count: int
    open_order_count: int
    positions: tuple[LivePosition, ...] = ()
    fetched_at: int = field(default_factory=now_ms)
    source: str = LIVE_CAPITAL_STATE_SOURCE
    is_real_account_snapshot: bool = True
    # PR112 hard markers: no live execution adapter exists yet.
    real_orders_allowed: bool = False
    exchange_live_orders: bool = False

    @property
    def open_positions(self) -> tuple[LivePosition, ...]:
        return tuple(p for p in self.positions if p.is_open)

    @property
    def total_position_notional_usdt(self) -> float:
        return sum(p.notional_usdt for p in self.open_positions)

    @classmethod
    def from_account_snapshot(
        cls,
        account: BinanceAccountSnapshot,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
        capital_profile_id: CapitalProfileId | str = CapitalProfileId.L0_SHADOW,
        open_order_count: int = 0,
        account_id: str | None = None,
        mark_prices: dict[str, float] | None = None,
        liquidation_prices: dict[str, float] | None = None,
        is_real_account_snapshot: bool = True,
    ) -> "LiveCapitalState":
        """Build a :class:`LiveCapitalState` from a Binance account snapshot.

        ``mark_prices`` / ``liquidation_prices`` may be supplied (keyed by
        symbol) to enrich the positions from a ``/fapi/v2/positionRisk``
        read; otherwise the entry price is used for notional and the
        liquidation price is left unknown.
        """
        if isinstance(capital_profile_id, str) and not isinstance(
            capital_profile_id, CapitalProfileId
        ):
            capital_profile_id = CapitalProfileId(capital_profile_id)

        marks = mark_prices or {}
        liqs = liquidation_prices or {}
        positions: list[LivePosition] = []
        for p in account.positions:
            if not p.is_open:
                continue
            positions.append(
                LivePosition.from_binance(
                    p,
                    mark_price=marks.get(p.symbol),
                    liquidation_price=liqs.get(p.symbol),
                    update_time=account.timestamp_ms or None,
                )
            )

        # Equity: prefer the exchange's margin balance (wallet + unrealized);
        # fall back to wallet + unrealized when margin balance is absent.
        equity = account.total_margin_balance
        if equity <= 0:
            equity = account.total_wallet_balance + account.total_unrealized_pnl
        available = account.available_balance
        # Used margin is whatever is not freely available; clamped at 0.
        used_margin = max(0.0, equity - available)

        return cls(
            account_id_masked=mask_secret(account_id) if account_id else "<absent>",
            runtime_mode=runtime_mode,
            capital_profile_id=capital_profile_id,
            wallet_balance_usdt=account.total_wallet_balance,
            available_balance_usdt=available,
            account_equity_usdt=equity,
            unrealized_pnl_usdt=account.total_unrealized_pnl,
            used_margin_usdt=used_margin,
            free_margin_usdt=available,
            open_position_count=len(positions),
            open_order_count=int(open_order_count),
            positions=tuple(positions),
            fetched_at=account.timestamp_ms or now_ms(),
            source=LIVE_CAPITAL_STATE_SOURCE,
            is_real_account_snapshot=bool(is_real_account_snapshot),
            real_orders_allowed=False,
            exchange_live_orders=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id_masked": self.account_id_masked,
            "runtime_mode": self.runtime_mode.value,
            "capital_profile_id": self.capital_profile_id.value,
            "wallet_balance_usdt": self.wallet_balance_usdt,
            "available_balance_usdt": self.available_balance_usdt,
            "account_equity_usdt": self.account_equity_usdt,
            "unrealized_pnl_usdt": self.unrealized_pnl_usdt,
            "used_margin_usdt": self.used_margin_usdt,
            "free_margin_usdt": self.free_margin_usdt,
            "open_position_count": self.open_position_count,
            "open_order_count": self.open_order_count,
            "positions": [p.to_dict() for p in self.positions],
            "fetched_at": self.fetched_at,
            "source": self.source,
            "is_real_account_snapshot": self.is_real_account_snapshot,
            "real_orders_allowed": self.real_orders_allowed,
            "exchange_live_orders": self.exchange_live_orders,
        }


__all__ = [
    "LIVE_CAPITAL_STATE_SOURCE",
    "LivePosition",
    "LiveCapitalState",
]
