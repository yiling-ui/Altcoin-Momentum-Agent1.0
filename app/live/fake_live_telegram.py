"""Fake live Telegram transport + operator (PR117 - Full-System Single-Altcoin
Live Sandbox Audit v0).

Lets the REAL PR114 :class:`app.live.telegram_operator.TelegramOperatorConsole`
run end to end against a fake authorized / unauthorized chat without ever
contacting Telegram:

  * :class:`FakeTelegramTransport` - a transport callable
    ``(method, url, json_body) -> json`` that records every outbound
    ``sendMessage`` (and can feed ``getUpdates``) without IO.
  * :class:`FakeOperator` - the authorized + unauthorized chat identities.
  * :class:`SandboxConsoleDataProvider` - supplies readable, deterministic
    snapshots so ``/status`` / ``/pnl`` / ``/risk`` / ``/capital`` /
    ``/profile`` cards are meaningful in the audit.

HARD boundaries (the brief): a Telegram command can NEVER place a naked
order, bypass the Risk Engine / Execution Gateway / Capital Profile /
kill switch, nor be driven by a non-LIVE source. This module only models
the transport + the operator identity; the REAL console enforces the
rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.live.capital_profile import CapitalProfileId, get_profile
from app.live.telegram_commands import LiveConsoleDataProvider

FAKE_LIVE_TELEGRAM_MODULE = "live.fake_live_telegram"

DEFAULT_AUTHORIZED_CHAT_ID = "770011"
DEFAULT_UNAUTHORIZED_CHAT_ID = "999999"


@dataclass
class FakeTelegramCall:
    """A single recorded Telegram transport call."""

    method: str
    body: dict[str, Any] = field(default_factory=dict)


class FakeTelegramTransport:
    """A deterministic fake Telegram transport (no socket, ever).

    Mirrors :data:`app.live.telegram_operator.OutboundTransport`:
    ``(method, url, json_body) -> parsed JSON``. It records every call so
    the audit can assert which cards were sent vs suppressed, and it can
    return queued ``getUpdates`` results.
    """

    def __init__(self, *, updates: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[FakeTelegramCall] = []
        self.sent_messages: list[dict[str, Any]] = []
        self._updates = list(updates or [])

    @property
    def sent_count(self) -> int:
        return len(self.sent_messages)

    def __call__(self, method: str, url: str, body: dict[str, Any]) -> Any:
        # url carries the bot token; we deliberately never store it.
        self.calls.append(FakeTelegramCall(method=method, body=dict(body or {})))
        if method == "sendMessage":
            self.sent_messages.append(dict(body or {}))
            return {"ok": True, "result": {"message_id": len(self.sent_messages)}}
        if method == "getUpdates":
            return {"ok": True, "result": self._updates}
        return {"ok": True, "result": {}}


@dataclass(frozen=True)
class FakeOperator:
    """The fake operator identities used by the audit."""

    authorized_chat_id: str = DEFAULT_AUTHORIZED_CHAT_ID
    unauthorized_chat_id: str = DEFAULT_UNAUTHORIZED_CHAT_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorized_chat_id": self.authorized_chat_id,
            "unauthorized_chat_id": self.unauthorized_chat_id,
        }


class SandboxConsoleDataProvider(LiveConsoleDataProvider):
    """Supplies readable, deterministic snapshots for the operator cards.

    Every figure is a fixed sandbox value so the cards are legible and
    the audit can assert they separate strategy PnL from external flows.
    """

    def __init__(
        self,
        *,
        capital_profile_id: CapitalProfileId = CapitalProfileId.L1_10U_PROBE,
        account_equity_usdt: float = 10.0,
        gross_realized_pnl_usdt: float = 2.0,
        commission_total_usdt: float = 0.2,
        funding_total_usdt: float = -0.1,
        external_deposit_total_usdt: float = 100.0,
        external_withdrawal_total_usdt: float = 50.0,
        funding_attribution_status: str = "UNATTRIBUTED_PENDING_POSITION_LINK",
        positions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._profile_id = capital_profile_id
        self._equity = float(account_equity_usdt)
        self._gross = float(gross_realized_pnl_usdt)
        self._commission = float(commission_total_usdt)
        self._funding = float(funding_total_usdt)
        self._deposit = float(external_deposit_total_usdt)
        self._withdrawal = float(external_withdrawal_total_usdt)
        self._funding_status = funding_attribution_status
        self._positions = positions or []

    @property
    def net_strategy_pnl_usdt(self) -> float:
        return round(self._gross - self._commission + self._funding, 8)

    def safety_flags(self) -> dict[str, Any]:
        return {
            "exchange_live_orders": False,
            "trade_authority_flag": False,
            "private_trade_enabled": False,
            "binance_public_status": "PASS",
            "binance_private_read_status": "PASS",
            "telegram_outbound_status": "PASS",
            "deepseek_status": "SKIPPED",
        }

    def account_status(self) -> dict[str, Any]:
        prof = get_profile(self._profile_id)
        return {
            "wallet_balance_usdt": self._equity,
            "available_balance_usdt": self._equity,
            "usable_capital_usdt": min(self._equity, prof.max_account_capital_usdt),
        }

    def positions(self) -> list[dict[str, Any]]:
        return list(self._positions)

    def pnl(self) -> dict[str, Any]:
        return {
            "gross_realized_pnl_usdt": self._gross,
            "commission_total_usdt": self._commission,
            "funding_total_usdt": self._funding,
            "net_strategy_pnl_usdt": self.net_strategy_pnl_usdt,
            "external_deposit_total_usdt": self._deposit,
            "external_withdrawal_total_usdt": self._withdrawal,
            "funding_attribution_status": self._funding_status,
        }

    def risk(self) -> dict[str, Any]:
        prof = get_profile(self._profile_id)
        return {
            "capital_profile_id": self._profile_id.value,
            "max_account_capital_usdt": prof.max_account_capital_usdt,
            "max_position_notional_usdt": prof.max_position_notional_usdt,
            "max_leverage": prof.max_leverage,
            "risk_halt_active": False,
        }

    def capital(self) -> dict[str, Any]:
        prof = get_profile(self._profile_id)
        return {
            "capital_profile_id": self._profile_id.value,
            "account_equity_usdt": self._equity,
            "max_account_capital_usdt": prof.max_account_capital_usdt,
            "external_deposit_total_usdt": self._deposit,
            "external_withdrawal_total_usdt": self._withdrawal,
        }

    def account_equity_usdt(self) -> float | None:
        return self._equity

    def funding_attribution_status(self) -> str | None:
        return self._funding_status


__all__ = [
    "FAKE_LIVE_TELEGRAM_MODULE",
    "DEFAULT_AUTHORIZED_CHAT_ID",
    "DEFAULT_UNAUTHORIZED_CHAT_ID",
    "FakeTelegramCall",
    "FakeTelegramTransport",
    "FakeOperator",
    "SandboxConsoleDataProvider",
]
