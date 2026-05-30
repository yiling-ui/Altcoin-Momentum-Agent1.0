"""Live AI briefing generation (PR115 - DeepSeek Live Intelligence v0).

Turns a :class:`app.live.ai_live_evidence.LiveAIEvidenceBundle` into a
:class:`LiveAIBriefing` — a market-intelligence-only operator briefing.

The AI is told, in the system prompt, that it is MARKET_INTELLIGENCE_ONLY
and CANNOT decide trades / direction / size / leverage / stop /
take-profit / target / order / execution / config patch. Whatever the
model returns is passed through :func:`app.live.ai_output_guard.
sanitize_ai_output`, which strips any forbidden trade-authority field. A
briefing that leaked a forbidden field is marked
``REJECTED_FOR_TRADE_AUTHORITY`` and is never treated as actionable.

Failure handling (the brief):
  * DeepSeek disabled               -> status ``DISABLED`` (no crash).
  * DeepSeek key missing/placeholder-> status ``MISSING_SECRET`` (no crash).
  * DeepSeek HTTP / transport error -> status ``ERROR`` (safe error text).
  * Insufficient live evidence      -> status ``INSUFFICIENT_EVIDENCE``.

This module performs network IO ONLY through the injected DeepSeek
client / transport (every unit test injects a fake). It never places an
order, never changes capital / mode / profile, and never flips a safety
flag. Every briefing pins ``ai_trade_authority = False`` and
``source_scope = LIVE_ONLY``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from app.core.clock import now_ms
from app.core.errors import LiveApiError
from app.core.events import Event, EventType
from app.live.ai_live_evidence import SOURCE_SCOPE_LIVE_ONLY, LiveAIEvidenceBundle
from app.live.ai_output_guard import (
    ALLOWED_BRIEFING_FIELDS,
    BriefingStatus,
    sanitize_ai_output,
)
from app.live.api_config import DeepSeekApiConfig
from app.live.deepseek_client import DeepSeekLiveClient, DeepSeekTransport
from app.live.secrets import API_HEALTH_MISSING_SECRET

AI_LIVE_BRIEFING_MODULE = "live.ai_live_briefing"

AI_AUTHORITY_LABEL = "MARKET_INTELLIGENCE_ONLY"

# Evidence-quality buckets.
EVIDENCE_STRONG = "STRONG"
EVIDENCE_MODERATE = "MODERATE"
EVIDENCE_WEAK = "WEAK"
EVIDENCE_INSUFFICIENT = "INSUFFICIENT"

# Sections that contribute to evidence quality (in operator order).
_EVIDENCE_SECTIONS: tuple[str, ...] = (
    "account_status",
    "pnl_summary",
    "open_positions",
    "risk_summary",
    "recent_order_summary",
    "funding_summary",
    "telegram_state",
    "api_health_summary",
    "market_snapshot_summary",
)


# ---------------------------------------------------------------------------
# Prompt contract
# ---------------------------------------------------------------------------
#: The system prompt. It states, unambiguously, that the AI has no trade
#: authority and lists every decision it must NOT make.
LIVE_AI_SYSTEM_PROMPT = (
    "You are AMA-RT's live market-intelligence assistant. Your authority "
    "is MARKET_INTELLIGENCE_ONLY.\n"
    "You CANNOT decide trades. You CANNOT output a trade direction "
    "(buy/sell/long/short). You CANNOT output position size or sizing. "
    "You CANNOT output leverage. You CANNOT output stop-loss, take-profit, "
    "or target price. You CANNOT output an entry/exit price, order type, "
    "or any execution instruction. You CANNOT output a runtime config "
    "patch, strategy patch, or risk-limit patch. You CANNOT tell the "
    "operator to open, close, add to, or hold a position.\n"
    "You ONLY summarise and explain the live evidence provided to you. "
    "Use ONLY the provided live evidence; do not invent data. If the "
    "evidence is insufficient to answer, say so explicitly via the "
    "'evidence_quality' and 'missing_evidence' fields rather than "
    "guessing. Be concise, factual, and operator-friendly."
)


def build_prompt_messages(bundle: LiveAIEvidenceBundle) -> list[dict[str, str]]:
    """Build the chat messages for a live-safe AI briefing.

    The requested output schema is restricted to
    :data:`ALLOWED_BRIEFING_FIELDS` (no trade-authority field is ever
    requested). The user message embeds the compressed live evidence.
    """
    schema_hint = {key: "" for key in ALLOWED_BRIEFING_FIELDS}
    schema_hint["evidence_quality"] = "STRONG|MODERATE|WEAK|INSUFFICIENT"
    schema_hint["missing_evidence"] = []
    user = (
        "Produce a live-safe operator briefing as a JSON object. Populate "
        "ONLY these keys (omit anything you cannot support with the "
        "evidence):\n"
        f"{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
        "Rules: market-intelligence only; NO direction, size, leverage, "
        "stop, take-profit, target, order, execution instruction, or "
        "config patch. Explain risk points, evidence quality, funding "
        "impact, profile limits, and anomalies. If evidence is "
        "insufficient, set evidence_quality=INSUFFICIENT and list the "
        "missing pieces.\n\n"
        "LIVE EVIDENCE (source_scope=LIVE_ONLY):\n"
        f"{json.dumps(bundle.to_dict(), ensure_ascii=False, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": LIVE_AI_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Evidence quality
# ---------------------------------------------------------------------------
def _section_present(bundle: LiveAIEvidenceBundle, name: str) -> bool:
    value = getattr(bundle, name, None)
    if value is None:
        return False
    if isinstance(value, (dict, list, tuple)):
        return len(value) > 0
    return bool(value)


def assess_evidence_quality(bundle: LiveAIEvidenceBundle) -> tuple[str, list[str]]:
    """Return ``(quality, missing_evidence)`` from the bundle's sections."""
    present = [s for s in _EVIDENCE_SECTIONS if _section_present(bundle, s)]
    missing = [s for s in _EVIDENCE_SECTIONS if s not in present]
    n = len(present)
    if n == 0:
        quality = EVIDENCE_INSUFFICIENT
    elif n >= 6:
        quality = EVIDENCE_STRONG
    elif n >= 3:
        quality = EVIDENCE_MODERATE
    else:
        quality = EVIDENCE_WEAK
    return quality, missing


# ---------------------------------------------------------------------------
# Briefing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveAIBriefing:
    """A validated, trade-authority-free live operator briefing (PR115)."""

    briefing_id: str
    status: str
    market_summary: str = ""
    account_summary: str = ""
    risk_summary: str = ""
    pnl_summary: str = ""
    funding_summary: str = ""
    position_notes: str = ""
    rejection_summary: str = ""
    anomaly_notes: str = ""
    operator_notes: str = ""
    evidence_quality: str = EVIDENCE_INSUFFICIENT
    missing_evidence: tuple[str, ...] = ()
    forbidden_fields_detected: tuple[str, ...] = ()
    evidence_bundle_id: str = ""
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    created_at: int = field(default_factory=now_ms)
    ai_trade_authority: bool = False  # pinned False
    source_scope: str = SOURCE_SCOPE_LIVE_ONLY

    @property
    def actionable(self) -> bool:
        """A briefing is NEVER actionable. AI has no trade authority."""
        return False

    @property
    def rejected_for_trade_authority(self) -> bool:
        return self.status == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "briefing_id": self.briefing_id,
            "status": self.status,
            "market_summary": self.market_summary,
            "account_summary": self.account_summary,
            "risk_summary": self.risk_summary,
            "pnl_summary": self.pnl_summary,
            "funding_summary": self.funding_summary,
            "position_notes": self.position_notes,
            "rejection_summary": self.rejection_summary,
            "anomaly_notes": self.anomaly_notes,
            "operator_notes": self.operator_notes,
            "evidence_quality": self.evidence_quality,
            "missing_evidence": list(self.missing_evidence),
            "forbidden_fields_detected": list(self.forbidden_fields_detected),
            "evidence_bundle_id": self.evidence_bundle_id,
            "model": self.model,
            "usage": dict(self.usage),
            "error_message": self.error_message,
            "created_at": self.created_at,
            "authority": AI_AUTHORITY_LABEL,
            # Hard-pinned PR115 markers.
            "ai_trade_authority": False,
            "source_scope": SOURCE_SCOPE_LIVE_ONLY,
            "trade_authority": False,
            "exchange_live_orders": False,
            "live_trading": False,
            "phase_12_forbidden": True,
        }


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------
class LiveAIBriefingGenerator:
    """Generates live-safe AI briefings from a live evidence bundle (PR115)."""

    def __init__(
        self,
        config: DeepSeekApiConfig,
        *,
        client: DeepSeekLiveClient | None = None,
        transport: DeepSeekTransport | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config
        self._event_repo = event_repo
        self._clock = clock
        # Build a client only when one is not supplied. A transport is
        # passed through so tests can inject a fake; the client refuses to
        # call when disabled / key missing.
        self._client = client or DeepSeekLiveClient(
            config, transport=transport, event_repo=event_repo
        )
        self._last_status: str | None = None
        self._last_briefing_id: str | None = None

    # -- introspection -------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    @property
    def has_key(self) -> bool:
        return bool(self._config.has_key)

    def status(self) -> dict[str, Any]:
        """A redacted status snapshot for ``/ai_status`` and the CLI."""
        return {
            "module": AI_LIVE_BRIEFING_MODULE,
            "pr": "PR115",
            "authority": AI_AUTHORITY_LABEL,
            "deepseek_enabled": self.enabled,
            "deepseek_key_present": self.has_key,
            "deepseek_key_masked": self._config.api_key.masked(),
            "deepseek_key_placeholder": (
                self._config.has_key and self._config.api_key.is_placeholder
            ),
            "model": self._config.model,
            "last_briefing_status": self._last_status,
            "last_briefing_id": self._last_briefing_id,
            "source_scope": SOURCE_SCOPE_LIVE_ONLY,
            # Hard-pinned PR115 markers.
            "ai_trade_authority": False,
            "trade_authority": False,
            "exchange_live_orders": False,
            "live_trading": False,
            "phase_12_forbidden": True,
        }

    # -- generation ----------------------------------------------------
    def generate(
        self,
        bundle: LiveAIEvidenceBundle,
        *,
        dry_run: bool = False,
    ) -> LiveAIBriefing:
        """Generate a live-safe briefing from ``bundle``.

        Never raises: every failure mode maps to a safe status. ``dry_run``
        produces a deterministic local briefing (no DeepSeek call).
        """
        briefing_id = "AIB-" + uuid.uuid4().hex[:12].upper()
        quality, missing = assess_evidence_quality(bundle)

        self._emit(
            EventType.LIVE_AI_BRIEFING_REQUESTED,
            {
                "briefing_id": briefing_id,
                "evidence_bundle_id": bundle.evidence_bundle_id,
                "evidence_quality": quality,
                "dry_run": bool(dry_run),
            },
        )

        # Dry-run: deterministic local compression, no network.
        if dry_run:
            briefing = self._build_local_briefing(briefing_id, bundle, quality, missing)
            self._finish(briefing)
            return briefing

        # Config gates (no crash).
        if not self._config.enabled:
            return self._fail_briefing(
                briefing_id, bundle, quality, missing,
                status=BriefingStatus.DISABLED,
                error="deepseek_disabled",
            )
        if not self._config.has_key or self._config.api_key.is_placeholder:
            return self._fail_briefing(
                briefing_id, bundle, quality, missing,
                status=BriefingStatus.MISSING_SECRET,
                error=API_HEALTH_MISSING_SECRET,
            )

        # Call DeepSeek.
        messages = build_prompt_messages(bundle)
        try:
            raw = self._client.chat_completion(messages)
        except LiveApiError as exc:
            return self._fail_briefing(
                briefing_id, bundle, quality, missing,
                status=BriefingStatus.ERROR,
                error=_safe_error(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive
            return self._fail_briefing(
                briefing_id, bundle, quality, missing,
                status=BriefingStatus.ERROR,
                error=_safe_error(exc),
            )

        content, model, usage = _parse_chat_response(raw, self._config.model)
        guard = sanitize_ai_output(content, event_repo=self._event_repo)

        briefing = self._build_briefing_from_payload(
            briefing_id,
            bundle,
            guard.clean_payload,
            quality,
            missing,
            forbidden=guard.forbidden_fields_detected,
            guard_status=guard.status,
            model=model,
            usage=usage,
        )
        self._finish(briefing)
        return briefing

    # -- builders ------------------------------------------------------
    def _build_local_briefing(
        self,
        briefing_id: str,
        bundle: LiveAIEvidenceBundle,
        quality: str,
        missing: list[str],
    ) -> LiveAIBriefing:
        """Deterministic, no-network briefing built from evidence only."""
        status = (
            BriefingStatus.INSUFFICIENT_EVIDENCE
            if quality == EVIDENCE_INSUFFICIENT
            else BriefingStatus.OK
        )
        d = _deterministic_summaries(bundle)
        return LiveAIBriefing(
            briefing_id=briefing_id,
            status=status,
            market_summary=d["market_summary"],
            account_summary=d["account_summary"],
            risk_summary=d["risk_summary"],
            pnl_summary=d["pnl_summary"],
            funding_summary=d["funding_summary"],
            position_notes=d["position_notes"],
            rejection_summary=d["rejection_summary"],
            anomaly_notes=d["anomaly_notes"],
            operator_notes=(
                "Dry-run local briefing (no DeepSeek call). Informational "
                "only; AI has no trade authority."
            ),
            evidence_quality=quality,
            missing_evidence=tuple(missing),
            evidence_bundle_id=bundle.evidence_bundle_id,
            model="(dry-run/local)",
            created_at=int(self._clock()),
        )

    def _build_briefing_from_payload(
        self,
        briefing_id: str,
        bundle: LiveAIEvidenceBundle,
        payload: Mapping[str, Any],
        quality: str,
        missing: list[str],
        *,
        forbidden: tuple[str, ...],
        guard_status: str,
        model: str,
        usage: dict[str, Any],
    ) -> LiveAIBriefing:
        # Status precedence: trade-authority leak > insufficient > ok.
        if guard_status == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY:
            status = BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
        elif quality == EVIDENCE_INSUFFICIENT:
            status = BriefingStatus.INSUFFICIENT_EVIDENCE
        else:
            status = BriefingStatus.OK

        ai_quality = str(payload.get("evidence_quality", "") or "").upper()
        if ai_quality not in (
            EVIDENCE_STRONG,
            EVIDENCE_MODERATE,
            EVIDENCE_WEAK,
            EVIDENCE_INSUFFICIENT,
        ):
            ai_quality = quality

        ai_missing = payload.get("missing_evidence")
        if isinstance(ai_missing, (list, tuple)):
            missing_evidence = tuple(str(m) for m in ai_missing)
        else:
            missing_evidence = tuple(missing)

        return LiveAIBriefing(
            briefing_id=briefing_id,
            status=status,
            market_summary=_text(payload.get("market_summary")),
            account_summary=_text(payload.get("account_summary")),
            risk_summary=_text(payload.get("risk_summary")),
            pnl_summary=_text(payload.get("pnl_summary")),
            funding_summary=_text(payload.get("funding_summary")),
            position_notes=_text(payload.get("position_notes")),
            rejection_summary=_text(payload.get("rejection_summary")),
            anomaly_notes=_text(payload.get("anomaly_notes")),
            operator_notes=_text(payload.get("operator_notes")),
            evidence_quality=ai_quality,
            missing_evidence=missing_evidence,
            forbidden_fields_detected=tuple(forbidden),
            evidence_bundle_id=bundle.evidence_bundle_id,
            model=model,
            usage=dict(usage),
            created_at=int(self._clock()),
        )

    def _fail_briefing(
        self,
        briefing_id: str,
        bundle: LiveAIEvidenceBundle,
        quality: str,
        missing: list[str],
        *,
        status: str,
        error: str,
    ) -> LiveAIBriefing:
        briefing = LiveAIBriefing(
            briefing_id=briefing_id,
            status=status,
            operator_notes=(
                "AI briefing unavailable; see status/error. Informational "
                "only; AI has no trade authority."
            ),
            evidence_quality=quality,
            missing_evidence=tuple(missing),
            evidence_bundle_id=bundle.evidence_bundle_id,
            model=self._config.model,
            error_message=error,
            created_at=int(self._clock()),
        )
        self._last_status = status
        self._last_briefing_id = briefing_id
        self._emit(
            EventType.LIVE_AI_BRIEFING_FAILED,
            {
                "briefing_id": briefing_id,
                "evidence_bundle_id": bundle.evidence_bundle_id,
                "status": status,
                "error": error,
            },
        )
        return briefing

    def _finish(self, briefing: LiveAIBriefing) -> None:
        self._last_status = briefing.status
        self._last_briefing_id = briefing.briefing_id
        self._emit(
            EventType.LIVE_AI_BRIEFING_GENERATED,
            {
                "briefing_id": briefing.briefing_id,
                "evidence_bundle_id": briefing.evidence_bundle_id,
                "status": briefing.status,
                "evidence_quality": briefing.evidence_quality,
                "forbidden_fields_detected": list(briefing.forbidden_fields_detected),
            },
        )

    # -- events --------------------------------------------------------
    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=AI_LIVE_BRIEFING_MODULE,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    # Defensive: never let a query string / signature ride along.
    if "?" in text:
        text = text.split("?", 1)[0]
    return text[:200]


def _parse_chat_response(
    raw: Mapping[str, Any], default_model: str
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Extract the JSON content + model + usage from a chat response."""
    usage = dict(raw.get("usage", {}) or {})
    model = str(raw.get("model", default_model) or default_model)
    content_obj: dict[str, Any] = {}
    try:
        choices = raw.get("choices") or []
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                content_obj = json.loads(content)
            elif isinstance(content, Mapping):
                content_obj = dict(content)
    except (json.JSONDecodeError, ValueError, AttributeError, IndexError, TypeError):
        content_obj = {}
    if not isinstance(content_obj, dict):
        content_obj = {}
    return content_obj, model, usage


def _deterministic_summaries(bundle: LiveAIEvidenceBundle) -> dict[str, str]:
    """Build factual, no-AI summaries from the evidence (dry-run path)."""
    acct = bundle.account_status or {}
    pnl = bundle.pnl_summary or {}
    risk = bundle.risk_summary or {}
    funding = bundle.funding_summary or {}
    positions = bundle.open_positions or ()
    orders = bundle.recent_order_summary or {}
    market = bundle.market_snapshot_summary or {}

    def g(d: Mapping[str, Any], *keys: str) -> Any:
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return None

    account_summary = (
        f"mode={bundle.runtime_mode} profile={bundle.capital_profile_id} "
        f"equity={g(acct, 'account_equity_usdt')} "
        f"available={g(acct, 'available_balance_usdt')} "
        f"open_positions={g(acct, 'open_position_count') if acct else len(positions)}"
    )
    pnl_summary = (
        f"gross_realized={g(pnl, 'gross_realized_pnl_usdt')} "
        f"commission={g(pnl, 'commission_total_usdt')} "
        f"funding={g(pnl, 'funding_total_usdt')} "
        f"net_strategy={g(pnl, 'net_strategy_pnl_usdt')} "
        f"deposits={g(pnl, 'external_deposit_total_usdt')} "
        f"withdrawals={g(pnl, 'external_withdrawal_total_usdt')}"
    ) if pnl else "no PnL evidence"
    risk_summary = (
        f"profile_status={g(risk, 'profile_status')} "
        f"flags={g(risk, 'flags')} "
        f"risk_halt={g(risk, 'risk_halt_active')} "
        f"max_leverage={g(risk, 'max_leverage')}"
    ) if risk else "no risk evidence"
    funding_summary = (
        f"funding_total={g(funding, 'funding_total_usdt')} "
        f"attribution={g(funding, 'funding_attribution_status', 'attribution_status')}"
    ) if funding else "no funding evidence"
    position_notes = (
        f"{len(positions)} open position(s)"
        if positions
        else "no open positions in evidence"
    )
    rejection_summary = (
        f"recent_rejections={g(orders, 'reject_reasons', 'recent_rejections')}"
        if orders
        else "no recent rejection evidence"
    )
    market_summary = (
        f"regime={g(market, 'market_regime', 'regime')} "
        f"note={g(market, 'note', 'summary')}"
        if market
        else "no market snapshot in evidence"
    )
    return {
        "market_summary": market_summary,
        "account_summary": account_summary,
        "risk_summary": risk_summary,
        "pnl_summary": pnl_summary,
        "funding_summary": funding_summary,
        "position_notes": position_notes,
        "rejection_summary": rejection_summary,
        "anomaly_notes": "",
    }


__all__ = [
    "AI_LIVE_BRIEFING_MODULE",
    "AI_AUTHORITY_LABEL",
    "EVIDENCE_STRONG",
    "EVIDENCE_MODERATE",
    "EVIDENCE_WEAK",
    "EVIDENCE_INSUFFICIENT",
    "LIVE_AI_SYSTEM_PROMPT",
    "build_prompt_messages",
    "assess_evidence_quality",
    "LiveAIBriefing",
    "LiveAIBriefingGenerator",
]
