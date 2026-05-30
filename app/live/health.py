"""Unified live API health check for the Live API Integration Pack (PR111).

Aggregates the Binance / Telegram / DeepSeek health checks into one
report. The report is non-mutating and carries the project safety
flags. Running it NEVER:

  - places / cancels / modifies an order
  - switches runtime mode
  - enables live trading
  - changes leverage / margin
  - sends a Telegram message unless ``send_telegram_test`` is set
  - calls DeepSeek unless ``call_deepseek`` is set
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig
from app.live.binance_client import BinanceLiveClient
from app.live.binance_models import BinanceApiHealthResult
from app.live.deepseek_health import DeepSeekApiHealthResult, run_deepseek_health_check
from app.live.status import (
    HealthStatus,
    TRADE_API_BLOCKED_BY_PR111,
    worst_of,
)
from app.live.telegram_health import TelegramApiHealthResult, run_telegram_health_check

# HANDOFF(PR110): capital profile id comes from the PR110 Capital Profile
# Ladder. Until PR110 lands, PR111 uses a self-contained default.
DEFAULT_CAPITAL_PROFILE_ID = "shadow_default"


def build_safety_flags(config: LiveApiConfig) -> dict[str, Any]:
    """Return the PR111 safety-flag block embedded in every health report.

    Every flag below is an *assertion* about PR111 behaviour. PR111 does
    not place live orders, does not grant AI trade authority, and keeps
    LIVE_SHADOW as the default mode.
    """
    return {
        # Equivalent safety remains recorded even though PR110 renamed
        # the phase taxonomy. PR111 still forbids the Phase-12 live path.
        "phase_12_forbidden": True,
        "live_trading": False,
        "exchange_live_orders": False,
        "trade_authority": False,
        "ai_trade_authority": False,
        "right_tail": False,
        "live_runtime_mode": config.live_runtime_mode.value,
        "telegram_outbound_enabled": config.telegram.outbound_enabled,
        "binance_private_read_enabled": config.binance.enable_private_read,
        "binance_private_trade_enabled_by_config": config.binance.enable_private_trade,
        "binance_private_trade_blocked": True,
        "deepseek_enabled": config.deepseek.enabled,
        "secret_logging_allowed": config.general.secret_logging_allowed,
        "secrets_masked": True,
    }


@dataclass(frozen=True)
class LiveApiHealthReport:
    """Aggregate unified health report."""

    overall_status: HealthStatus
    live_runtime_mode: str
    capital_profile_id: str
    binance_public_status: HealthStatus
    binance_private_read_status: HealthStatus
    binance_private_trade_status: str
    telegram_status: HealthStatus
    deepseek_status: HealthStatus
    safety_flags: dict[str, Any]
    binance: BinanceApiHealthResult | None = None
    telegram: TelegramApiHealthResult | None = None
    deepseek: DeepSeekApiHealthResult | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "live_runtime_mode": self.live_runtime_mode,
            "capital_profile_id": self.capital_profile_id,
            "binance_public_status": self.binance_public_status.value,
            "binance_private_read_status": self.binance_private_read_status.value,
            "binance_private_trade_status": self.binance_private_trade_status,
            "telegram_status": self.telegram_status.value,
            "deepseek_status": self.deepseek_status.value,
            "exchange_live_orders": False,
            "ai_trade_authority": False,
            "telegram_outbound_enabled": bool(
                self.safety_flags.get("telegram_outbound_enabled", False)
            ),
            "secrets_masked": True,
            "safety_flags": self.safety_flags,
            "warnings": list(self.warnings),
            "binance": self.binance.to_dict() if self.binance else None,
            "telegram": self.telegram.to_dict() if self.telegram else None,
            "deepseek": self.deepseek.to_dict() if self.deepseek else None,
        }


def _binance_public_status(result: BinanceApiHealthResult) -> HealthStatus:
    return HealthStatus.PASS if result.public_market_ok else HealthStatus.FAIL


def _binance_private_read_status(
    config: LiveApiConfig, result: BinanceApiHealthResult
) -> HealthStatus:
    if not config.binance.enable_private_read:
        return HealthStatus.SKIPPED
    if not config.binance.has_credentials:
        return HealthStatus.WARN
    if not result.private_read_ok:
        return HealthStatus.FAIL
    return HealthStatus.WARN if result.high_risk_permission_warning else HealthStatus.PASS


def run_unified_health_check(
    config: LiveApiConfig,
    *,
    check_binance: bool = True,
    check_telegram: bool = True,
    check_deepseek: bool = False,
    send_telegram_test: bool = False,
    call_deepseek: bool = False,
    test_chat_id: str | int | None = None,
    capital_profile_id: str = DEFAULT_CAPITAL_PROFILE_ID,
    event_repo: Any | None = None,
    binance_client: BinanceLiveClient | None = None,
) -> LiveApiHealthReport:
    """Run the unified, non-mutating health check across enabled providers."""

    runtime_mode = config.live_runtime_mode
    safety_flags = build_safety_flags(config)

    _emit(event_repo, EventType.API_HEALTH_CHECK_STARTED, {
        "check_binance": check_binance,
        "check_telegram": check_telegram,
        "check_deepseek": check_deepseek,
        "live_runtime_mode": runtime_mode.value,
    })

    warnings: list[str] = []
    contributing: list[HealthStatus] = []

    # --- Binance ---
    binance_result: BinanceApiHealthResult | None = None
    binance_public_status = HealthStatus.SKIPPED
    binance_private_read_status = HealthStatus.SKIPPED
    binance_private_trade_status = TRADE_API_BLOCKED_BY_PR111
    if check_binance:
        cli = binance_client or BinanceLiveClient(
            config.binance, runtime_mode=runtime_mode, event_repo=event_repo
        )
        binance_result = cli.health_check()
        binance_public_status = _binance_public_status(binance_result)
        binance_private_read_status = _binance_private_read_status(config, binance_result)
        contributing.append(binance_public_status)
        if binance_private_read_status != HealthStatus.SKIPPED:
            contributing.append(binance_private_read_status)
        warnings.extend(binance_result.warnings)

    # --- Telegram ---
    telegram_result: TelegramApiHealthResult | None = None
    telegram_status = HealthStatus.SKIPPED
    if check_telegram:
        telegram_result = run_telegram_health_check(
            config.telegram,
            runtime_mode=runtime_mode,
            send_test=send_telegram_test,
            test_chat_id=test_chat_id,
            event_repo=event_repo,
        )
        telegram_status = telegram_result.status
        contributing.append(telegram_status)

    # --- DeepSeek ---
    deepseek_result: DeepSeekApiHealthResult | None = None
    deepseek_status = HealthStatus.SKIPPED
    if check_deepseek:
        deepseek_result = run_deepseek_health_check(
            config.deepseek,
            call_api=call_deepseek,
            event_repo=event_repo,
        )
        deepseek_status = deepseek_result.status
        contributing.append(deepseek_status)

    overall = worst_of(contributing)

    report = LiveApiHealthReport(
        overall_status=overall,
        live_runtime_mode=runtime_mode.value,
        capital_profile_id=capital_profile_id,
        binance_public_status=binance_public_status,
        binance_private_read_status=binance_private_read_status,
        binance_private_trade_status=binance_private_trade_status,
        telegram_status=telegram_status,
        deepseek_status=deepseek_status,
        safety_flags=safety_flags,
        binance=binance_result,
        telegram=telegram_result,
        deepseek=deepseek_result,
        warnings=tuple(warnings),
    )

    _emit(event_repo, EventType.API_HEALTH_CHECK_COMPLETED, {
        "overall_status": overall.value,
        "live_runtime_mode": runtime_mode.value,
        "safety_flags": safety_flags,
    })

    return report


def _emit(event_repo: Any | None, event_type: EventType, payload: dict[str, Any]) -> None:
    if event_repo is None:
        return
    try:
        event_repo.append(
            Event(event_type=event_type, source_module="live_api_health", payload=payload)
        )
    except Exception:  # pragma: no cover
        pass


__all__ = [
    "LiveApiHealthReport",
    "run_unified_health_check",
    "build_safety_flags",
    "DEFAULT_CAPITAL_PROFILE_ID",
]
