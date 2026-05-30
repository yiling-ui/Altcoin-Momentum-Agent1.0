"""Binance API key permission inspection for the Live API Pack (PR111).

PR111 hard rules:

  - Withdraw permission is NEVER required. A read-only or trade-without-
    withdraw key is the recommended setup.
  - If the key reports a high-risk permission (withdraw / internal
    transfer), a warning is produced and surfaced in the health check +
    docs. PR111 does not refuse to operate, but it flags it loudly.
  - ``can_trade_if_account_reports_it`` simply mirrors the exchange's
    own ``canTrade`` flag. It is NOT a runtime trade authorisation; the
    order path stays blocked in PR111 regardless.
"""

from __future__ import annotations

from app.live.binance_models import BinanceAccountSnapshot, BinancePermissionSnapshot


# Human-readable warning strings (safe for logs - never carry a secret).
WARNING_WITHDRAW_ENABLED = (
    "binance_key_has_withdraw_permission: high-risk. PR111 never requires "
    "withdraw; disable it on the API key if your exchange allows."
)
WARNING_DEPOSIT_ENABLED = (
    "binance_key_has_deposit_permission: review whether this is intended."
)


def inspect_permissions(account: BinanceAccountSnapshot) -> BinancePermissionSnapshot:
    """Build a :class:`BinancePermissionSnapshot` from an account snapshot.

    The account read itself proves read permission. ``canTrade`` /
    ``canDeposit`` / ``canWithdraw`` come straight from the exchange
    response. A withdraw permission flips the high-risk warning.
    """

    warnings: list[str] = []
    high_risk = False

    if account.can_withdraw:
        high_risk = True
        warnings.append(WARNING_WITHDRAW_ENABLED)
    if account.can_deposit:
        warnings.append(WARNING_DEPOSIT_ENABLED)

    return BinancePermissionSnapshot(
        can_read=True,
        can_trade_if_account_reports_it=bool(account.can_trade),
        can_deposit=bool(account.can_deposit),
        can_withdraw=bool(account.can_withdraw),
        high_risk_permission_warning=high_risk,
        warnings=tuple(warnings),
    )


__all__ = [
    "inspect_permissions",
    "WARNING_WITHDRAW_ENABLED",
    "WARNING_DEPOSIT_ENABLED",
]
