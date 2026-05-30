"""AI output guard for PR115 - DeepSeek Live Intelligence v0.

DeepSeek output is MARKET_INTELLIGENCE_ONLY. Before any AI payload is
turned into a :class:`LiveAIBriefing` (or shown to the operator), it must
pass schema validation + a forbidden-field sanitizer:

  * Any trade-authority field is stripped at every nesting depth,
    matched case-insensitively. The brief's explicit forbidden list is
    included verbatim, plus a defence-in-depth superset.
  * When a forbidden field is present, the result is flagged
    ``REJECTED_FOR_TRADE_AUTHORITY`` and the events
    ``AI_FORBIDDEN_FIELD_STRIPPED`` +
    ``DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`` are emitted.
  * Every result pins ``ai_trade_authority = False`` and
    ``source_scope = LIVE_ONLY``.

This module is pure (no network IO). It never places an order, never
changes capital / mode / profile, and never flips a safety flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core.events import Event, EventType
from app.live.ai_live_evidence import SOURCE_SCOPE_LIVE_ONLY
from app.live.deepseek_client import FORBIDDEN_TRADE_AUTHORITY_FIELDS

AI_OUTPUT_GUARD_MODULE = "live.ai_output_guard"


# ---------------------------------------------------------------------------
# Briefing status taxonomy
# ---------------------------------------------------------------------------
class BriefingStatus:
    """Closed taxonomy of live AI briefing statuses (PR115)."""

    OK = "OK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED_FOR_TRADE_AUTHORITY = "REJECTED_FOR_TRADE_AUTHORITY"
    DISABLED = "DISABLED"
    MISSING_SECRET = "MISSING_SECRET"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Forbidden output fields
# ---------------------------------------------------------------------------
#: The PR115 brief's explicit forbidden output fields.
PR115_FORBIDDEN_OUTPUT_FIELDS: frozenset[str] = frozenset(
    {
        "should_buy",
        "should_sell",
        "should_long",
        "should_short",
        "direction",
        "position_size",
        "size",
        "leverage",
        "stop_price",
        "take_profit",
        "target_price",
        "order_type",
        "entry_price",
        "exit_price",
        "execute",
        "trade_decision",
        "runtime_config_patch",
        "strategy_patch",
        "risk_limit_patch",
    }
)

#: Defence-in-depth superset: the brief's list + the PR111 trade-authority
#: set already enforced by the DeepSeek client.
FORBIDDEN_OUTPUT_FIELDS: frozenset[str] = (
    PR115_FORBIDDEN_OUTPUT_FIELDS | FORBIDDEN_TRADE_AUTHORITY_FIELDS
)

_FORBIDDEN_OUTPUT_LOWER: frozenset[str] = frozenset(
    f.lower() for f in FORBIDDEN_OUTPUT_FIELDS
)

#: The ONLY fields a :class:`LiveAIBriefing` body may carry. The AI is
#: asked to populate these and nothing else.
ALLOWED_BRIEFING_FIELDS: tuple[str, ...] = (
    "market_summary",
    "account_summary",
    "risk_summary",
    "pnl_summary",
    "funding_summary",
    "position_notes",
    "rejection_summary",
    "anomaly_notes",
    "operator_notes",
    "evidence_quality",
    "missing_evidence",
)


def _strip_forbidden(payload: Any) -> tuple[Any, list[str]]:
    """Recursively strip forbidden keys (case-insensitive) from ``payload``.

    Returns ``(clean_payload, stripped_dotted_paths)``.
    """
    stripped: list[str] = []

    def _walk(node: Any, path: str) -> Any:
        if isinstance(node, Mapping):
            out: dict[str, Any] = {}
            for raw_key, value in node.items():
                key = str(raw_key)
                here = f"{path}.{key}" if path else key
                if key.strip().lower() in _FORBIDDEN_OUTPUT_LOWER:
                    stripped.append(here)
                    continue
                out[key] = _walk(value, here)
            return out
        if isinstance(node, (list, tuple)):
            return [_walk(item, f"{path}[{idx}]") for idx, item in enumerate(node)]
        return node

    cleaned = _walk(payload, "")
    return cleaned, sorted(set(stripped))


@dataclass(frozen=True)
class AIOutputGuardResult:
    """Result of sanitising a raw AI payload (PR115)."""

    clean_payload: dict[str, Any]
    forbidden_fields_detected: tuple[str, ...]
    status: str
    ai_trade_authority: bool = False  # always False by construction
    source_scope: str = SOURCE_SCOPE_LIVE_ONLY

    @property
    def had_forbidden_fields(self) -> bool:
        return len(self.forbidden_fields_detected) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "clean_payload": dict(self.clean_payload),
            "forbidden_fields_detected": list(self.forbidden_fields_detected),
            "status": self.status,
            "ai_trade_authority": False,
            "source_scope": SOURCE_SCOPE_LIVE_ONLY,
            "trade_authority": False,
            "exchange_live_orders": False,
        }


def sanitize_ai_output(
    payload: Mapping[str, Any],
    *,
    event_repo: Any | None = None,
    source_module: str = AI_OUTPUT_GUARD_MODULE,
) -> AIOutputGuardResult:
    """Strip every forbidden trade-authority field from ``payload``.

    When a forbidden field is present the result status is
    ``REJECTED_FOR_TRADE_AUTHORITY`` and both
    ``AI_FORBIDDEN_FIELD_STRIPPED`` and
    ``DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`` are emitted. The
    clean payload (with the forbidden keys removed) is always returned so
    the surviving intelligence can still be summarised — but it is marked
    not actionable.
    """
    cleaned, stripped = _strip_forbidden(dict(payload))
    if not isinstance(cleaned, dict):
        cleaned = {}

    status = BriefingStatus.OK
    if stripped:
        status = BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
        _emit(
            event_repo,
            EventType.AI_FORBIDDEN_FIELD_STRIPPED,
            {"stripped_fields": list(stripped)},
            source_module=source_module,
        )
        _emit(
            event_repo,
            EventType.DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY,
            {"rejected_fields": list(stripped)},
            source_module=source_module,
        )

    return AIOutputGuardResult(
        clean_payload=cleaned,
        forbidden_fields_detected=tuple(stripped),
        status=status,
        ai_trade_authority=False,
    )


def _emit(
    event_repo: Any | None,
    event_type: EventType,
    payload: dict[str, Any],
    *,
    source_module: str,
) -> None:
    if event_repo is None:
        return
    try:
        event_repo.append(
            Event(
                event_type=event_type,
                source_module=source_module,
                payload={
                    **payload,
                    "ai_trade_authority": False,
                    "trade_authority": False,
                    "exchange_live_orders": False,
                    "phase_12_forbidden": True,
                },
            )
        )
    except Exception:  # pragma: no cover - event emit is best-effort
        pass


__all__ = [
    "AI_OUTPUT_GUARD_MODULE",
    "BriefingStatus",
    "PR115_FORBIDDEN_OUTPUT_FIELDS",
    "FORBIDDEN_OUTPUT_FIELDS",
    "ALLOWED_BRIEFING_FIELDS",
    "AIOutputGuardResult",
    "sanitize_ai_output",
]
