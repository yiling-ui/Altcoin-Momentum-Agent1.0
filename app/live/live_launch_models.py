"""Launch-pack data models (PR116 - 10U LIVE_LIMITED Launch Pack v0).

The PR116 launch pack wires PR110-PR115 together into a controlled,
operator-confirmed, small-capital real-money runtime. This module holds
the frozen, log-safe data contracts shared by:

  - :mod:`app.live.live_launch_readiness` (the readiness checker),
  - :mod:`app.live.live_shadow_runner`    (the LIVE_SHADOW runner),
  - :mod:`app.live.live_limited_arming`   (the arming + smoke workflow),
  - :mod:`app.live.live_kill_switch`      (the kill switch),
  - :mod:`app.live.live_runtime`          (the dynamic-profile runtime),

and by the three CLIs (``live_launch_check`` / ``live_shadow_run`` /
``live_limited_smoke``) + the Telegram operator console.

Hard PR116 posture (the brief): every model below pins the safe-by-
default markers - ``real_order=False`` / ``trade_authority=False`` /
``ai_trade_authority=False`` / ``exchange_live_orders=False`` /
``live_trading=False`` / ``no_real_order_sent=True`` - unless an explicit,
fully-gated real-order smoke actually sent an order. Nothing in this
module performs IO, places an order, or flips a safety flag; these are
pure data contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.live.status import HealthStatus, worst_of

LIVE_LAUNCH_MODELS_MODULE = "live.live_launch_models"

# Overall launch-readiness verdicts (reuse the PR111 tri-state vocabulary).
LAUNCH_PASS = HealthStatus.PASS
LAUNCH_WARN = HealthStatus.WARN
LAUNCH_FAIL = HealthStatus.FAIL
LAUNCH_SKIPPED = HealthStatus.SKIPPED


def launch_safety_markers() -> dict[str, Any]:
    """The safe-by-default marker block stamped on every launch payload.

    PR116 default posture: LIVE_SHADOW, no real orders, no trade
    authority, no AI trade authority, no live orders. These markers are
    assertions a reviewer / test can pin directly.
    """
    return {
        "real_order": False,
        "real_capital_changed": False,
        "trade_authority": False,
        "ai_trade_authority": False,
        "exchange_live_orders": False,
        "live_trading": False,
        "no_real_order_sent": True,
        "phase_12_forbidden": True,
    }


# ---------------------------------------------------------------------------
# One readiness check item
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LaunchCheckItem:
    """A single readiness-check line.

    ``status`` is a :class:`HealthStatus`. ``is_blocker`` marks an item
    whose non-PASS status contributes a blocker (for the live-limited GO
    decision). ``blocks_shadow`` additionally marks the (small) subset of
    items that must pass for a LIVE_SHADOW GO.
    """

    check_id: str
    status: HealthStatus
    detail: str = ""
    value: Any = None
    is_blocker: bool = False
    blocks_shadow: bool = False

    @property
    def ok(self) -> bool:
        return self.status in (HealthStatus.PASS, HealthStatus.SKIPPED)

    @property
    def failed(self) -> bool:
        return self.status is HealthStatus.FAIL

    @property
    def warned(self) -> bool:
        return self.status is HealthStatus.WARN

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "detail": self.detail,
            "value": self.value,
            "is_blocker": self.is_blocker,
            "blocks_shadow": self.blocks_shadow,
            "ok": self.ok,
        }


# ---------------------------------------------------------------------------
# The full launch readiness report
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LaunchReadinessReport:
    """Aggregate end-to-end launch readiness report (PR116).

    Carries every field the brief's readiness-checker output lists, plus
    the per-check item list and the blocker / warning roll-ups. Running a
    readiness check NEVER sends a real order: ``no_real_order_sent`` is
    always True.
    """

    overall_status: HealthStatus
    go_for_live_shadow: bool
    go_for_live_limited: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    items: tuple[LaunchCheckItem, ...]

    # Runtime / capital context.
    runtime_mode: str
    capital_profile_id: str
    account_equity_usdt: float | None
    usable_live_capital_usdt: float | None
    profile_max_account_capital_usdt: float
    capital_cap_enforced: bool
    capital_profile_mismatch: bool
    l1_10u_cap_enforced: bool

    # Binance.
    binance_public_ok: bool
    binance_private_read_ok: bool
    binance_private_trade_configured: bool
    binance_private_trade_enabled: bool

    # Telegram.
    telegram_outbound_ok: bool
    telegram_allowed_chat_ok: bool

    # DeepSeek (intelligence-only).
    deepseek_ok_or_optional: bool

    # Operator / system flags.
    kill_switch_armed: bool
    live_limited_confirmed: bool
    exchange_live_orders: bool
    trade_authority: bool
    ai_trade_authority: bool

    # Isolation / accounting / order validation.
    live_path_isolation_ok: bool
    blind_sim_isolation_ok: bool
    funding_accounting_ok: bool
    order_precision_ok: bool
    dry_order_validation_ok: bool
    execution_gateway_dry_run_ok: bool

    # Hard PR116 marker.
    no_real_order_sent: bool = True
    requested_pre_live_limited: bool = False
    require_real_keys: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "overall_status": self.overall_status.value,
            "go_for_live_shadow": self.go_for_live_shadow,
            "go_for_live_limited": self.go_for_live_limited,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "items": [i.to_dict() for i in self.items],
            "runtime_mode": self.runtime_mode,
            "capital_profile_id": self.capital_profile_id,
            "account_equity": self.account_equity_usdt,
            "account_equity_usdt": self.account_equity_usdt,
            "usable_live_capital": self.usable_live_capital_usdt,
            "usable_live_capital_usdt": self.usable_live_capital_usdt,
            "profile_max_account_capital_usdt": self.profile_max_account_capital_usdt,
            "capital_cap_enforced": self.capital_cap_enforced,
            "capital_profile_mismatch": self.capital_profile_mismatch,
            "l1_10u_cap_enforced": self.l1_10u_cap_enforced,
            "binance_public_ok": self.binance_public_ok,
            "binance_private_read_ok": self.binance_private_read_ok,
            "binance_private_trade_configured": self.binance_private_trade_configured,
            "binance_private_trade_enabled": self.binance_private_trade_enabled,
            "telegram_outbound_ok": self.telegram_outbound_ok,
            "telegram_allowed_chat_ok": self.telegram_allowed_chat_ok,
            "deepseek_ok_or_optional": self.deepseek_ok_or_optional,
            "kill_switch_armed": self.kill_switch_armed,
            "live_limited_confirmed": self.live_limited_confirmed,
            "exchange_live_orders": self.exchange_live_orders,
            "trade_authority": self.trade_authority,
            "ai_trade_authority": self.ai_trade_authority,
            "live_path_isolation_ok": self.live_path_isolation_ok,
            "blind_sim_isolation_ok": self.blind_sim_isolation_ok,
            "funding_accounting_ok": self.funding_accounting_ok,
            "order_precision_ok": self.order_precision_ok,
            "dry_order_validation_ok": self.dry_order_validation_ok,
            "execution_gateway_dry_run_ok": self.execution_gateway_dry_run_ok,
            "no_real_order_sent": self.no_real_order_sent,
            "requested_pre_live_limited": self.requested_pre_live_limited,
            "require_real_keys": self.require_real_keys,
        }
        d.update(launch_safety_markers())
        # The launch readiness report reflects the REAL operator flags for
        # the unsafe-enabling toggles (so the operator can see them), so do
        # not let the generic safe markers overwrite them.
        d["exchange_live_orders"] = self.exchange_live_orders
        d["trade_authority"] = self.trade_authority
        d["no_real_order_sent"] = self.no_real_order_sent
        return d

    def telegram_summary_card(self) -> dict[str, Any]:
        """Build the LIVE_READINESS_SUMMARY operator card (build only)."""
        card: dict[str, Any] = {
            "card_type": "LIVE_READINESS_SUMMARY",
            "overall_status": self.overall_status.value,
            "go_for_live_shadow": self.go_for_live_shadow,
            "go_for_live_limited": self.go_for_live_limited,
            "go_no_go": "GO" if self.go_for_live_limited else "NO-GO",
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "runtime_mode": self.runtime_mode,
            "capital_profile_id": self.capital_profile_id,
            "account_equity_usdt": self.account_equity_usdt,
            "usable_live_capital_usdt": self.usable_live_capital_usdt,
            "exchange_live_orders": self.exchange_live_orders,
            "trade_authority": self.trade_authority,
            "kill_switch_armed": self.kill_switch_armed,
            "binance_public_ok": self.binance_public_ok,
            "binance_private_read_ok": self.binance_private_read_ok,
            "telegram_outbound_ok": self.telegram_outbound_ok,
            "deepseek_ok_or_optional": self.deepseek_ok_or_optional,
        }
        card.update(launch_safety_markers())
        return card


# ---------------------------------------------------------------------------
# Shadow run result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ShadowRunResult:
    """Outcome of one LIVE_SHADOW run iteration (PR116).

    A shadow run reads live market / private-read data and produces
    operator cards (status / risk / positions / optional AI briefing). It
    NEVER places a real order: ``real_order`` is False and
    ``no_real_order_sent`` is True on every run.
    """

    runtime_mode: str
    capital_profile_id: str
    account_equity_usdt: float | None
    usable_live_capital_usdt: float | None
    open_position_count: int
    cards: tuple[dict[str, Any], ...]
    telegram_sent_count: int
    telegram_suppressed_count: int
    ai_briefing_status: str | None
    warnings: tuple[str, ...] = ()
    real_order: bool = False
    no_real_order_sent: bool = True

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "runtime_mode": self.runtime_mode,
            "mode_display": "空盘跑",
            "capital_profile_id": self.capital_profile_id,
            "account_equity_usdt": self.account_equity_usdt,
            "usable_live_capital_usdt": self.usable_live_capital_usdt,
            "open_position_count": self.open_position_count,
            "cards": [dict(c) for c in self.cards],
            "telegram_sent_count": self.telegram_sent_count,
            "telegram_suppressed_count": self.telegram_suppressed_count,
            "ai_briefing_status": self.ai_briefing_status,
            "warnings": list(self.warnings),
        }
        d.update(launch_safety_markers())
        return d

    def telegram_summary_card(self) -> dict[str, Any]:
        """Build the LIVE_SHADOW_SUMMARY operator card (build only)."""
        card = {
            "card_type": "LIVE_SHADOW_SUMMARY",
            "mode_display": "空盘跑",
            "runtime_mode": self.runtime_mode,
            "capital_profile_id": self.capital_profile_id,
            "account_equity_usdt": self.account_equity_usdt,
            "usable_live_capital_usdt": self.usable_live_capital_usdt,
            "open_position_count": self.open_position_count,
            "ai_briefing_status": self.ai_briefing_status,
        }
        card.update(launch_safety_markers())
        return card


# ---------------------------------------------------------------------------
# Smoke result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SmokeResult:
    """Outcome of a LIVE_LIMITED smoke attempt (dry-run or real-order).

    ``real_order`` is True ONLY when a real order request actually left
    the system through :class:`app.live.execution_gateway.
    LiveExecutionGateway`. Every blocked / dry path keeps
    ``real_order=False`` and ``no_real_order_sent=True``.
    """

    mode: str  # "dry_run" | "real_order"
    symbol: str
    side: str
    notional_usdt: float
    leverage: float
    client_order_id: str | None
    allowed: bool
    reject_reason: str | None
    reject_reasons: tuple[str, ...]
    order_status: str | None
    exchange_order_id: str | None
    fill_price: float | None
    fee_usdt: float | None
    funding_attribution_status: str | None
    net_pnl_usdt: float | None
    validation_ok: bool
    dry_run: bool
    real_order: bool
    no_real_order_sent: bool
    blocked_reason: str | None = None
    ledger_recorded: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "mode": self.mode,
            "symbol": self.symbol,
            "side": self.side,
            "notional_usdt": self.notional_usdt,
            "leverage": self.leverage,
            "client_order_id": self.client_order_id,
            "allowed": self.allowed,
            "reject_reason": self.reject_reason,
            "reject_reasons": list(self.reject_reasons),
            "order_status": self.order_status,
            "order_id": self.exchange_order_id,
            "exchange_order_id": self.exchange_order_id,
            "fill_price": self.fill_price,
            "fee_usdt": self.fee_usdt,
            "fee": self.fee_usdt,
            "funding_attribution_status": self.funding_attribution_status,
            "funding_status": self.funding_attribution_status,
            "net_pnl_usdt": self.net_pnl_usdt,
            "net_pnl": self.net_pnl_usdt,
            "validation_ok": self.validation_ok,
            "dry_run": self.dry_run,
            "blocked_reason": self.blocked_reason,
            "ledger_recorded": self.ledger_recorded,
        }
        d.update(launch_safety_markers())
        # The smoke result reflects whether a REAL order was actually sent.
        d["real_order"] = self.real_order
        d["no_real_order_sent"] = self.no_real_order_sent
        return d

    def telegram_result_card(self) -> dict[str, Any]:
        """Build the LIVE_SMOKE_RESULT operator card (build only)."""
        card = {
            "card_type": "LIVE_SMOKE_RESULT",
            "symbol": self.symbol,
            "side": self.side,
            "notional_usdt": self.notional_usdt,
            "leverage": self.leverage,
            "order_id": self.exchange_order_id or "--",
            "fill_price": self.fill_price,
            "fee": self.fee_usdt,
            "funding_status": self.funding_attribution_status,
            "net_pnl": self.net_pnl_usdt,
            "order_status": self.order_status,
            "reject_reason": self.reject_reason,
        }
        card.update(launch_safety_markers())
        card["real_order"] = self.real_order
        card["no_real_order_sent"] = self.no_real_order_sent
        return card


__all__ = [
    "LIVE_LAUNCH_MODELS_MODULE",
    "LAUNCH_PASS",
    "LAUNCH_WARN",
    "LAUNCH_FAIL",
    "LAUNCH_SKIPPED",
    "launch_safety_markers",
    "LaunchCheckItem",
    "LaunchReadinessReport",
    "ShadowRunResult",
    "SmokeResult",
    "worst_of",
]
