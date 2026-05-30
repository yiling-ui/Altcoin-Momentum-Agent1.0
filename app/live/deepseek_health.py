"""DeepSeek health check for the Live API Integration Pack (PR111).

Reports key presence, enabled gate, and an optional safe test briefing.
The briefing is generated only when the client is enabled AND a key is
present. The result always pins ``ai_trade_authority = False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.events import Event, EventType
from app.live.api_config import DeepSeekApiConfig
from app.live.deepseek_client import DeepSeekBriefing, DeepSeekLiveClient
from app.live.secrets import API_HEALTH_MISSING_SECRET, PLACEHOLDER_SECRET_CONFIGURED
from app.live.status import HealthStatus, classify_api_error, worst_of


@dataclass(frozen=True)
class DeepSeekApiHealthResult:
    """Aggregate DeepSeek health-check result."""

    status: HealthStatus
    api_key_present: bool
    enabled: bool
    briefing_generated: bool = False
    ai_trade_authority: bool = False  # pinned False
    forbidden_fields_rejected: tuple[str, ...] = ()
    masked_api_key: str = "<absent>"
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    detail: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "api_key_present": self.api_key_present,
            "enabled": self.enabled,
            "briefing_generated": self.briefing_generated,
            "ai_trade_authority": False,
            "forbidden_fields_rejected": list(self.forbidden_fields_rejected),
            "masked_api_key": self.masked_api_key,
            "model": self.model,
            "usage": dict(self.usage),
            "detail": self.detail,
            "error_message": self.error_message,
        }


def run_deepseek_health_check(
    config: DeepSeekApiConfig,
    *,
    client: DeepSeekLiveClient | None = None,
    call_api: bool = False,
    event_repo: Any | None = None,
) -> DeepSeekApiHealthResult:
    """Run a non-mutating DeepSeek health check.

    ``call_api`` defaults to ``False``: the check only contacts DeepSeek
    when explicitly asked AND the client is enabled with a key present.
    """

    api_key_present = config.has_key
    enabled = config.enabled

    statuses: list[HealthStatus] = []
    detail_parts: list[str] = []
    error_message = ""
    briefing: DeepSeekBriefing | None = None

    if not api_key_present:
        statuses.append(HealthStatus.WARN)
        detail_parts.append(API_HEALTH_MISSING_SECRET)
    if not enabled:
        statuses.append(HealthStatus.SKIPPED)
        detail_parts.append("deepseek_disabled")

    # PR112 hardening: a placeholder key never reaches a real DeepSeek call.
    placeholder_key = api_key_present and config.api_key.is_placeholder
    if placeholder_key:
        statuses.append(HealthStatus.WARN)
        detail_parts.append(PLACEHOLDER_SECRET_CONFIGURED)

    if call_api and enabled and api_key_present and not placeholder_key:
        cli = client or DeepSeekLiveClient(config, event_repo=event_repo)
        try:
            briefing = cli.generate_test_briefing()
            statuses.append(HealthStatus.PASS)
            detail_parts.append("briefing_ok")
            if briefing.rejected_fields:
                statuses.append(HealthStatus.WARN)
                detail_parts.append("forbidden_fields_rejected")
                if event_repo is not None:
                    try:
                        event_repo.append(
                            Event(
                                event_type=EventType.DEEPSEEK_HEALTH_OK,
                                source_module="deepseek_health",
                                payload={"rejected_fields": list(briefing.rejected_fields)},
                            )
                        )
                    except Exception:  # pragma: no cover
                        pass
            else:
                if event_repo is not None:
                    try:
                        event_repo.append(
                            Event(
                                event_type=EventType.DEEPSEEK_HEALTH_OK,
                                source_module="deepseek_health",
                                payload={"briefing_generated": True},
                            )
                        )
                    except Exception:  # pragma: no cover
                        pass
        except Exception as exc:
            statuses.append(HealthStatus.FAIL)
            error_message = classify_api_error(_sanitise(exc))
            detail_parts.append(error_message)
    elif call_api:
        # Asked to call but not eligible (disabled / missing / placeholder key).
        detail_parts.append("call_skipped_not_eligible")

    status = worst_of(statuses) if statuses else HealthStatus.PASS
    return DeepSeekApiHealthResult(
        status=status,
        api_key_present=api_key_present,
        enabled=enabled,
        briefing_generated=briefing is not None,
        ai_trade_authority=False,
        forbidden_fields_rejected=briefing.rejected_fields if briefing else (),
        masked_api_key=config.api_key.masked(),
        model=briefing.model if briefing else config.model,
        usage=briefing.usage if briefing else {},
        detail=";".join(detail_parts),
        error_message=error_message,
    )


def _sanitise(exc: Exception) -> str:
    text = str(exc)
    if "?" in text:
        text = text.split("?", 1)[0]
    return text[:200]


__all__ = ["DeepSeekApiHealthResult", "run_deepseek_health_check"]
