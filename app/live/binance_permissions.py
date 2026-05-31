"""Binance API key permission inspection for the Live API Pack (PR111/PR118).

PR111 hard rules (unchanged):

  - Withdraw permission is NEVER required. A read-only or trade-without-
    withdraw key is the recommended setup.
  - ``can_trade_if_account_reports_it`` simply mirrors the exchange's own
    ``canTrade`` flag. It is NOT a runtime trade authorisation; the order
    path stays blocked regardless.

PR118 hotfix - fix the withdraw false-positive:

  - The withdraw warning (``high_risk_permission_warning``) is raised
    **only** when the raw ``apiRestrictions.enableWithdrawals`` field is
    explicitly ``True``. It is NEVER inferred from account-level
    capabilities (``canRead`` / ``canTrade`` / ``canDeposit`` /
    ``canWithdraw``) nor from ``enableFutures`` /
    ``enableSpotAndMarginTrading`` / ``permitsUniversalTransfer`` /
    ``enableInternalTransfer``.
  - Universal transfer and internal transfer each get their OWN, separate
    (lower-severity) warning - never the withdraw warning.
  - Futures trade / account ``canTrade`` are INFO only.
  - A permission the API did not expose is treated as NOT_REPORTED, never
    as ``True``.
  - The deposit warning is removed: the apiRestrictions endpoint exposes no
    field that proves key-level deposit permission, and account-level
    ``canDeposit`` is an account capability, not a key permission.
"""

from __future__ import annotations

from typing import Any

from app.live.binance_models import (
    BinanceAccountSnapshot,
    BinanceApiRestrictionsSnapshot,
    BinancePermissionSnapshot,
)


# Severity tags for structured findings.
SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_WARN = "WARN"
SEVERITY_INFO = "INFO"


# Human-readable warning / info strings (safe for logs - never carry a secret).
WARNING_WITHDRAW_ENABLED = (
    "binance_key_has_withdraw_permission: HIGH-RISK / BLOCKER. The API key's "
    "raw apiRestrictions.enableWithdrawals is true. AMA-RT never needs "
    "withdraw; disable it on the API key."
)
WARNING_UNIVERSAL_TRANSFER_ENABLED = (
    "binance_key_has_universal_transfer_permission: WARN. The API key's raw "
    "apiRestrictions.permitsUniversalTransfer is true. This is NOT a withdraw "
    "permission; review whether it is intended."
)
WARNING_INTERNAL_TRANSFER_ENABLED = (
    "binance_key_has_internal_transfer_permission: WARN. The API key's raw "
    "apiRestrictions.enableInternalTransfer is true. This is NOT a withdraw "
    "permission; review whether it is intended."
)
INFO_FUTURES_TRADE_ENABLED = (
    "binance_key_has_futures_trade_permission: INFO. The API key's raw "
    "apiRestrictions.enableFutures is true (expected for a trade-capable key)."
)
INFO_ACCOUNT_CAN_TRADE = (
    "binance_account_can_trade: INFO. The account reports canTrade=true. This "
    "mirrors the exchange flag only; it is NOT a runtime trade authorisation "
    "and the AMA-RT order path stays blocked by config."
)


def inspect_permissions(
    account: BinanceAccountSnapshot | None = None,
    restrictions: BinanceApiRestrictionsSnapshot | None = None,
) -> BinancePermissionSnapshot:
    """Build a :class:`BinancePermissionSnapshot`.

    ``restrictions`` (parsed from ``/sapi/v1/account/apiRestrictions``) is the
    ONLY authoritative source for key permissions. ``account`` (parsed from
    ``/fapi/v2/account``) contributes INFO only (``canTrade``); its
    ``canWithdraw`` / ``canDeposit`` capabilities NEVER drive a withdraw
    warning.

    When ``restrictions`` is ``None`` (e.g. the endpoint was unreachable),
    every key permission is NOT_REPORTED and NO withdraw warning is produced -
    the safe, false-positive-free default.
    """

    r = restrictions
    withdraw = r.enable_withdrawals if r is not None else None
    internal_transfer = r.enable_internal_transfer if r is not None else None
    universal_transfer = r.permits_universal_transfer if r is not None else None
    futures = r.enable_futures if r is not None else None
    spot_margin = r.enable_spot_and_margin_trading if r is not None else None
    reading = r.enable_reading if r is not None else None
    ip_restrict = r.ip_restrict if r is not None else None
    restrictions_reported = bool(r is not None and r.reported)

    account_can_trade = bool(account.can_trade) if account is not None else False

    warnings: list[str] = []
    findings: list[tuple[str, str]] = []
    high_risk = False

    # Rule 1 + 7: the withdraw warning is a BLOCKER and is set ONLY when the
    # raw enableWithdrawals field is explicitly True. Nothing else flips it.
    if withdraw is True:
        high_risk = True
        warnings.append(WARNING_WITHDRAW_ENABLED)
        findings.append((SEVERITY_BLOCKER, WARNING_WITHDRAW_ENABLED))

    # Rule 3 + 7: transfer permissions are their OWN WARN-level findings,
    # never the withdraw warning.
    if universal_transfer is True:
        warnings.append(WARNING_UNIVERSAL_TRANSFER_ENABLED)
        findings.append((SEVERITY_WARN, WARNING_UNIVERSAL_TRANSFER_ENABLED))
    if internal_transfer is True:
        warnings.append(WARNING_INTERNAL_TRANSFER_ENABLED)
        findings.append((SEVERITY_WARN, WARNING_INTERNAL_TRANSFER_ENABLED))

    # Rule 7: futures-trade permission + account canTrade are INFO only and
    # do NOT contribute to the surfaced ``warnings`` / health status.
    if futures is True:
        findings.append((SEVERITY_INFO, INFO_FUTURES_TRADE_ENABLED))
    if account_can_trade:
        findings.append((SEVERITY_INFO, INFO_ACCOUNT_CAN_TRADE))

    # ``can_read`` is proven by a successful account read OR an explicit
    # enableReading=true. It is informational and never a warning.
    can_read = (account is not None) or (reading is True)

    debug: dict[str, Any] = (
        r.to_debug_dict()
        if r is not None
        else BinanceApiRestrictionsSnapshot().to_debug_dict()
    )

    return BinancePermissionSnapshot(
        can_read=can_read,
        can_trade_if_account_reports_it=account_can_trade,
        withdraw_permission=withdraw,
        internal_transfer_permission=internal_transfer,
        universal_transfer_permission=universal_transfer,
        futures_trade_permission=futures,
        spot_margin_trade_permission=spot_margin,
        reading_permission=reading,
        ip_restricted=ip_restrict,
        restrictions_reported=restrictions_reported,
        high_risk_permission_warning=high_risk,
        warnings=tuple(warnings),
        findings=tuple(findings),
        debug=debug,
    )


__all__ = [
    "inspect_permissions",
    "SEVERITY_BLOCKER",
    "SEVERITY_WARN",
    "SEVERITY_INFO",
    "WARNING_WITHDRAW_ENABLED",
    "WARNING_UNIVERSAL_TRANSFER_ENABLED",
    "WARNING_INTERNAL_TRANSFER_ENABLED",
    "INFO_FUTURES_TRADE_ENABLED",
    "INFO_ACCOUNT_CAN_TRADE",
]
