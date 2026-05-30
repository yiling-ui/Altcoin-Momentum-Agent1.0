"""Telegram health check for the Live API Integration Pack (PR111).

Reports token presence, allow-list configuration, outbound gate, and an
optional explicit test-message send. Never sends a message unless the
operator explicitly requests it AND outbound is enabled. Never crashes
when outbound is disabled - it reports ``TELEGRAM_OUTBOUND_DISABLED``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.live.api_config import LiveRuntimeMode, TelegramApiConfig
from app.live.secrets import API_HEALTH_MISSING_SECRET, PLACEHOLDER_SECRET_CONFIGURED
from app.live.status import (
    HealthStatus,
    TELEGRAM_OUTBOUND_DISABLED,
    classify_api_error,
    worst_of,
)
from app.live.telegram_client import TelegramLiveClient


@dataclass(frozen=True)
class TelegramApiHealthResult:
    """Aggregate Telegram health-check result."""

    status: HealthStatus
    bot_token_present: bool
    allowed_chat_ids_configured: bool
    outbound_enabled: bool
    test_message_sent: bool = False
    masked_bot_token: str = "<absent>"
    detail: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "bot_token_present": self.bot_token_present,
            "allowed_chat_ids_configured": self.allowed_chat_ids_configured,
            "outbound_enabled": self.outbound_enabled,
            "test_message_sent": self.test_message_sent,
            "masked_bot_token": self.masked_bot_token,
            "detail": self.detail,
            "error_message": self.error_message,
        }


def run_telegram_health_check(
    config: TelegramApiConfig,
    *,
    client: TelegramLiveClient | None = None,
    runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
    send_test: bool = False,
    test_chat_id: str | int | None = None,
    event_repo: Any | None = None,
) -> TelegramApiHealthResult:
    """Run a non-mutating Telegram health check.

    ``send_test`` defaults to ``False``: the health check never sends a
    message unless explicitly asked AND outbound is enabled.
    """

    cli = client or TelegramLiveClient(
        config, runtime_mode=runtime_mode, event_repo=event_repo
    )

    bot_token_present = config.has_token
    allowed_configured = bool(config.allowed_chat_ids)
    outbound_enabled = config.outbound_enabled

    statuses: list[HealthStatus] = []
    detail_parts: list[str] = []
    error_message = ""
    test_sent = False

    if not bot_token_present:
        statuses.append(HealthStatus.WARN)
        detail_parts.append(API_HEALTH_MISSING_SECRET)

    if not outbound_enabled:
        detail_parts.append(TELEGRAM_OUTBOUND_DISABLED)
        statuses.append(HealthStatus.SKIPPED)
    else:
        # Outbound is enabled. Validate token reachability via getMe only
        # if a REAL token is present; never send a message unless requested.
        # PR112 hardening: a placeholder token never reaches getMe (it would
        # only produce a confusing HTTP error).
        if bot_token_present and config.bot_token.is_placeholder:
            statuses.append(HealthStatus.WARN)
            detail_parts.append(PLACEHOLDER_SECRET_CONFIGURED)
        elif bot_token_present:
            try:
                cli.get_me()
                statuses.append(HealthStatus.PASS)
            except Exception as exc:  # token / transport failure
                error_message = classify_api_error(_sanitise(exc))
                detail_parts.append(error_message)
                statuses.append(HealthStatus.FAIL)

        if send_test:
            chat = test_chat_id
            if chat is None and config.allowed_chat_ids:
                chat = config.allowed_chat_ids[0]
            if config.bot_token.is_placeholder:
                # Never send with a placeholder token.
                statuses.append(HealthStatus.WARN)
                detail_parts.append(PLACEHOLDER_SECRET_CONFIGURED)
            elif chat is None:
                statuses.append(HealthStatus.WARN)
                detail_parts.append("no_test_chat_id")
            else:
                result = cli.send_test_message(chat)
                test_sent = result.sent
                statuses.append(result.status)
                detail_parts.append(result.detail)
                if result.status == HealthStatus.FAIL and not error_message:
                    error_message = result.detail

    status = worst_of(statuses) if statuses else HealthStatus.PASS
    return TelegramApiHealthResult(
        status=status,
        bot_token_present=bot_token_present,
        allowed_chat_ids_configured=allowed_configured,
        outbound_enabled=outbound_enabled,
        test_message_sent=test_sent,
        masked_bot_token=config.bot_token.masked(),
        detail=";".join(detail_parts),
        error_message=error_message,
    )


def _sanitise(exc: Exception) -> str:
    text = str(exc)
    if "?" in text:
        text = text.split("?", 1)[0]
    return text[:200]


__all__ = ["TelegramApiHealthResult", "run_telegram_health_check"]
