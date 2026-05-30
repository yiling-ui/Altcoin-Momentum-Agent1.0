"""Telegram AI briefing commands (PR115 - DeepSeek Live Intelligence v0).

Extends the PR114 operator console with a small set of SAFE, read-only AI
commands. Every command returns an explanation / summary card only; none
of them can place / cancel an order, change mode / profile / risk, or
trigger any live command:

  /ai_status              - DeepSeek enabled? key present? last briefing
                            status? Always MARKET_INTELLIGENCE_ONLY.
  /brief                  - generate / return the latest live-safe briefing.
  /explain_risk           - explain current risk state + recent rejects.
  /explain_position SYM   - explain an open position using live data.
  /summarize_pnl          - gross / commission / funding / net + flows.
  /summarize_rejections   - summarise recent risk / execution rejects.

HARD boundaries (the brief):
  * The AI can NEVER decide direction / size / leverage / stop /
    take-profit / target / order, nor recommend open / close / add /
    hold. Every card carries ``no_order_instruction=True`` +
    ``recommends_action=False`` + ``ai_trade_authority=False`` +
    ``source_scope=LIVE_ONLY``.
  * A non-LIVE source (SIM / BLIND / REPLAY / PAPER_SHADOW / BACKTEST /
    OFFLINE_AI / TELEGRAM_SANDBOX) is refused (``LIVE_SOURCE_REJECTED`` /
    ``AI_TELEGRAM_BRIEFING_BLOCKED``).
  * A live order / state-changing command handed to this handler is
    BLOCKED (the AI handler exposes no path to it).
  * A briefing that leaked a trade-authority field is never sent as an
    actionable card (``AI_TELEGRAM_BRIEFING_BLOCKED``).

This module builds + renders cards only. It NEVER opens a Telegram
socket, places an order, or flips a safety flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.core.enums import OrderSource
from app.core.events import Event, EventType
from app.exports.redaction import redact
from app.live.ai_live_briefing import (
    AI_AUTHORITY_LABEL,
    LiveAIBriefing,
    LiveAIBriefingGenerator,
)
from app.live.ai_live_evidence import (
    SOURCE_SCOPE_LIVE_ONLY,
    EvidenceBundleResult,
    build_live_ai_evidence_bundle,
)
from app.live.ai_output_guard import BriefingStatus
from app.live.telegram_auth import LiveSourceGuard

AI_TELEGRAM_MODULE = "live.ai_telegram"

AI_BRIEFING_HEADER = "[AI Briefing / MARKET_INTELLIGENCE_ONLY]"

# The safe, read-only AI command surface.
AI_COMMANDS: tuple[str, ...] = (
    "/ai_status",
    "/brief",
    "/explain_risk",
    "/explain_position",
    "/summarize_pnl",
    "/summarize_rejections",
)

# Live order / state-changing commands the AI handler MUST refuse. The AI
# console exposes NO path to any of these; handing one in is blocked.
_BLOCKED_LIVE_COMMANDS: frozenset[str] = frozenset(
    {
        "/mode",
        "/mode shadow",
        "/mode live_limited",
        "/confirm_live",
        "/confirm_kill",
        "/kill_all",
        "/profile",
        "/profile set",
        "/pause",
        "/resume",
        "/order",
        "/buy",
        "/sell",
        "/close",
        "/cancel",
        "/leverage",
    }
)


class AICardType:
    """Closed taxonomy of PR115 AI Telegram card types."""

    AI_STATUS = "AI_STATUS"
    AI_BRIEFING = "AI_BRIEFING"
    AI_RISK_EXPLANATION = "AI_RISK_EXPLANATION"
    AI_POSITION_EXPLANATION = "AI_POSITION_EXPLANATION"
    AI_PNL_SUMMARY = "AI_PNL_SUMMARY"
    AI_REJECTION_SUMMARY = "AI_REJECTION_SUMMARY"
    AI_COMMAND_BLOCKED = "AI_COMMAND_BLOCKED"


@dataclass
class AICommandResult:
    """Outcome of handling one AI command."""

    command: str
    ok: bool
    blocked: bool
    card: dict[str, Any]
    text: str
    reason: str = ""
    briefing: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "ok": self.ok,
            "blocked": self.blocked,
            "card": self.card,
            "text": self.text,
            "reason": self.reason,
            "briefing": self.briefing,
        }


# ---------------------------------------------------------------------------
# Card finalisation + rendering
# ---------------------------------------------------------------------------
def _ai_markers() -> dict[str, Any]:
    """Markers stamped on EVERY AI card (PR115)."""
    return {
        "header": AI_BRIEFING_HEADER,
        "authority": AI_AUTHORITY_LABEL,
        "ai_trade_authority": False,
        "source_scope": SOURCE_SCOPE_LIVE_ONLY,
        "no_order_instruction": True,
        "recommends_action": False,
        "trade_authority": False,
        "exchange_live_orders": False,
        "live_trading": False,
        "real_order": False,
        "phase_12_forbidden": True,
    }


def _finalize_ai_card(card: dict[str, Any]) -> dict[str, Any]:
    """Redact card content first, then stamp the fixed AI markers.

    Redaction runs first so any secret a caller accidentally placed in
    the card is scrubbed; the constant markers are added AFTER so they
    stay visible (the redactor would otherwise mask ``*_authority`` keys).
    """
    safe = redact(card)
    safe.update(_ai_markers())
    return safe


def render_ai_card(card: Mapping[str, Any]) -> str:
    """Render a short, redacted one-line text view of an AI card."""
    c = redact(dict(card))
    ctype = c.get("card_type", "?")
    parts = [f"[ama-rt:ai:{ctype}]", AI_BRIEFING_HEADER]
    for key in (
        "status",
        "evidence_quality",
        "symbol",
        "deepseek_enabled",
        "commission_total",
        "funding_total",
        "net_strategy_pnl",
    ):
        if key in c and c[key] not in (None, ""):
            parts.append(f"{key}={c[key]}")
    parts.append("ai_trade_authority=False")
    parts.append("source_scope=LIVE_ONLY")
    parts.append("no_order_instruction=True")
    return " ".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
class AIBriefingTelegram:
    """Handles the PR115 safe AI Telegram commands (read-only)."""

    def __init__(
        self,
        *,
        generator: LiveAIBriefingGenerator,
        evidence_provider: Callable[[], EvidenceBundleResult] | None = None,
        source_guard: LiveSourceGuard | None = None,
        event_repo: Any | None = None,
        dry_run_briefings: bool = False,
    ) -> None:
        self._generator = generator
        self._evidence_provider = evidence_provider or _default_evidence_provider
        self._source_guard = source_guard or LiveSourceGuard(event_repo=event_repo)
        self._event_repo = event_repo
        self._dry_run = bool(dry_run_briefings)

    # -- dispatch ------------------------------------------------------
    def handle(
        self,
        text: str,
        *,
        source: OrderSource | str = OrderSource.LIVE,
    ) -> AICommandResult:
        """Parse + handle one AI command. Read-only; never mutates state."""
        raw = (text or "").strip()
        parts = raw.split()
        head = parts[0].lower() if parts else ""
        args = tuple(parts[1:])

        # Live order / state-changing command handed to the AI handler.
        # The AI exposes no path to it: refuse + audit.
        if head in _BLOCKED_LIVE_COMMANDS:
            return self._blocked(
                head, "ai_cannot_run_live_or_state_changing_command"
            )

        if head not in AI_COMMANDS:
            return self._blocked(head or raw, "not_an_ai_command")

        # Live-source isolation: only LIVE may drive AI commands.
        if not self._source_guard.authorize(source, action=f"ai_command:{head}"):
            return self._blocked(head, "non_live_source_rejected")

        if head == "/ai_status":
            return self._cmd_ai_status(head)
        if head == "/brief":
            return self._cmd_brief(head)
        if head == "/explain_risk":
            return self._cmd_explain_risk(head)
        if head == "/explain_position":
            return self._cmd_explain_position(head, args)
        if head == "/summarize_pnl":
            return self._cmd_summarize_pnl(head)
        if head == "/summarize_rejections":
            return self._cmd_summarize_rejections(head)
        return self._blocked(head, "not_an_ai_command")  # pragma: no cover

    # -- /ai_status ----------------------------------------------------
    def _cmd_ai_status(self, command: str) -> AICommandResult:
        status = self._generator.status()
        card = _finalize_ai_card(
            {
                "card_type": AICardType.AI_STATUS,
                "deepseek_enabled": status.get("deepseek_enabled", False),
                "deepseek_key_present": status.get("deepseek_key_present", False),
                "deepseek_key_masked": status.get("deepseek_key_masked"),
                "model": status.get("model"),
                "last_briefing_status": status.get("last_briefing_status"),
                "api_health": status.get("api_health", "--"),
            }
        )
        return self._ok(command, card)

    # -- /brief --------------------------------------------------------
    def _cmd_brief(self, command: str) -> AICommandResult:
        ev = self._evidence_provider()
        if ev is None or not ev.accepted or ev.bundle is None:
            return self._blocked(
                command,
                "non_live_evidence_rejected",
                forbidden=getattr(ev, "forbidden_sources_detected", ()),
            )
        briefing = self._generator.generate(ev.bundle, dry_run=self._dry_run)
        card = _finalize_ai_card(
            {
                "card_type": AICardType.AI_BRIEFING,
                "status": briefing.status,
                "market_summary": briefing.market_summary,
                "account_summary": briefing.account_summary,
                "risk_notes": briefing.risk_summary,
                "pnl_summary": briefing.pnl_summary,
                "funding_summary": briefing.funding_summary,
                "position_notes": briefing.position_notes,
                "rejection_summary": briefing.rejection_summary,
                "anomaly_notes": briefing.anomaly_notes,
                "operator_notes": briefing.operator_notes,
                "evidence_quality": briefing.evidence_quality,
                "missing_evidence": list(briefing.missing_evidence),
            }
        )
        return self._briefing_result(command, card, briefing)

    # -- /explain_risk -------------------------------------------------
    def _cmd_explain_risk(self, command: str) -> AICommandResult:
        ev = self._evidence_provider()
        if ev is None or not ev.accepted or ev.bundle is None:
            return self._blocked(
                command,
                "non_live_evidence_rejected",
                forbidden=getattr(ev, "forbidden_sources_detected", ()),
            )
        briefing = self._generator.generate(ev.bundle, dry_run=self._dry_run)
        card = _finalize_ai_card(
            {
                "card_type": AICardType.AI_RISK_EXPLANATION,
                "status": briefing.status,
                "risk_notes": briefing.risk_summary,
                "rejection_summary": briefing.rejection_summary,
                "anomaly_notes": briefing.anomaly_notes,
                "evidence_quality": briefing.evidence_quality,
                "missing_evidence": list(briefing.missing_evidence),
                "note": (
                    "Risk explanation only. No order action is recommended."
                ),
            }
        )
        return self._briefing_result(command, card, briefing)

    # -- /explain_position --------------------------------------------
    def _cmd_explain_position(self, command: str, args: tuple[str, ...]) -> AICommandResult:
        symbol = args[0].upper() if args else ""
        ev = self._evidence_provider()
        if ev is None or not ev.accepted or ev.bundle is None:
            return self._blocked(
                command,
                "non_live_evidence_rejected",
                forbidden=getattr(ev, "forbidden_sources_detected", ()),
            )
        # Pull the matching live position from the evidence (live data only).
        matched = None
        for pos in ev.bundle.open_positions:
            if str(pos.get("symbol", "")).upper() == symbol:
                matched = pos
                break
        briefing = self._generator.generate(ev.bundle, dry_run=self._dry_run)
        card = _finalize_ai_card(
            {
                "card_type": AICardType.AI_POSITION_EXPLANATION,
                "symbol": symbol or "--",
                "status": briefing.status,
                "position": redact(dict(matched)) if matched else None,
                "position_notes": briefing.position_notes,
                "risk_notes": briefing.risk_summary,
                "evidence_quality": briefing.evidence_quality,
                "missing_evidence": list(briefing.missing_evidence),
                "note": (
                    "Position explanation only. No hold / add / close / "
                    "open recommendation is given."
                ),
            }
        )
        return self._briefing_result(command, card, briefing)

    # -- /summarize_pnl ------------------------------------------------
    def _cmd_summarize_pnl(self, command: str) -> AICommandResult:
        ev = self._evidence_provider()
        if ev is None or not ev.accepted or ev.bundle is None:
            return self._blocked(
                command,
                "non_live_evidence_rejected",
                forbidden=getattr(ev, "forbidden_sources_detected", ()),
            )
        pnl = ev.bundle.pnl_summary or {}
        briefing = self._generator.generate(ev.bundle, dry_run=self._dry_run)
        card = _finalize_ai_card(
            {
                "card_type": AICardType.AI_PNL_SUMMARY,
                "status": briefing.status,
                # Funding-aware figures (explanatory only).
                "gross_realized_pnl": pnl.get("gross_realized_pnl_usdt"),
                "commission_total": pnl.get("commission_total_usdt"),
                "funding_total": pnl.get("funding_total_usdt"),
                "net_strategy_pnl": pnl.get("net_strategy_pnl_usdt"),
                "deposits": pnl.get("external_deposit_total_usdt"),
                "withdrawals": pnl.get("external_withdrawal_total_usdt"),
                "pnl_summary": briefing.pnl_summary,
                "funding_summary": briefing.funding_summary,
                "evidence_quality": briefing.evidence_quality,
                "note": (
                    "PnL/funding/commission are explanatory only; deposits "
                    "and withdrawals are kept separate from strategy PnL."
                ),
            }
        )
        return self._briefing_result(command, card, briefing)

    # -- /summarize_rejections -----------------------------------------
    def _cmd_summarize_rejections(self, command: str) -> AICommandResult:
        ev = self._evidence_provider()
        if ev is None or not ev.accepted or ev.bundle is None:
            return self._blocked(
                command,
                "non_live_evidence_rejected",
                forbidden=getattr(ev, "forbidden_sources_detected", ()),
            )
        orders = ev.bundle.recent_order_summary or {}
        risk = ev.bundle.risk_summary or {}
        briefing = self._generator.generate(ev.bundle, dry_run=self._dry_run)
        card = _finalize_ai_card(
            {
                "card_type": AICardType.AI_REJECTION_SUMMARY,
                "status": briefing.status,
                "recent_rejections": orders.get("reject_reasons")
                or orders.get("recent_rejections"),
                "risk_flags": risk.get("flags"),
                "rejection_summary": briefing.rejection_summary,
                "evidence_quality": briefing.evidence_quality,
                "no_bypass_suggested": True,
                "note": (
                    "Rejections are summarised for awareness only; the AI "
                    "never suggests bypassing the Risk Engine or any gate."
                ),
            }
        )
        return self._briefing_result(command, card, briefing)

    # -- helpers -------------------------------------------------------
    def _briefing_result(
        self, command: str, card: dict[str, Any], briefing: LiveAIBriefing
    ) -> AICommandResult:
        """Finalise a briefing-backed card; block if trade-authority leaked."""
        if briefing.rejected_for_trade_authority:
            # Never send a trade-authority-leaking briefing as actionable.
            self._emit(
                EventType.AI_TELEGRAM_BRIEFING_BLOCKED,
                {
                    "command": command,
                    "briefing_id": briefing.briefing_id,
                    "reason": BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY,
                    "forbidden_fields_detected": list(
                        briefing.forbidden_fields_detected
                    ),
                },
            )
            card = dict(card)
            card["blocked_reason"] = BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
            return AICommandResult(
                command=command,
                ok=False,
                blocked=True,
                card=card,
                text=render_ai_card(card),
                reason=BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY,
                briefing=briefing.to_dict(),
            )
        self._emit(
            EventType.AI_TELEGRAM_BRIEFING_SENT,
            {
                "command": command,
                "briefing_id": briefing.briefing_id,
                "status": briefing.status,
                "evidence_quality": briefing.evidence_quality,
            },
        )
        return AICommandResult(
            command=command,
            ok=True,
            blocked=False,
            card=card,
            text=render_ai_card(card),
            briefing=briefing.to_dict(),
        )

    def _ok(self, command: str, card: dict[str, Any]) -> AICommandResult:
        self._emit(
            EventType.AI_TELEGRAM_BRIEFING_SENT,
            {"command": command, "card_type": card.get("card_type")},
        )
        return AICommandResult(
            command=command,
            ok=True,
            blocked=False,
            card=card,
            text=render_ai_card(card),
        )

    def _blocked(
        self,
        command: str,
        reason: str,
        *,
        forbidden: tuple[str, ...] = (),
    ) -> AICommandResult:
        card = _finalize_ai_card(
            {
                "card_type": AICardType.AI_COMMAND_BLOCKED,
                "command": command,
                "blocked_reason": reason,
                "forbidden_sources_detected": list(forbidden),
                "note": "AI command refused; no order / state change performed.",
            }
        )
        self._emit(
            EventType.AI_TELEGRAM_BRIEFING_BLOCKED,
            {
                "command": command,
                "reason": reason,
                "forbidden_sources_detected": list(forbidden),
            },
        )
        return AICommandResult(
            command=command,
            ok=False,
            blocked=True,
            card=card,
            text=render_ai_card(card),
            reason=reason,
        )

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=AI_TELEGRAM_MODULE,
                    payload={
                        **payload,
                        "ai_trade_authority": False,
                        "trade_authority": False,
                        "exchange_live_orders": False,
                        "source_scope": SOURCE_SCOPE_LIVE_ONLY,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover - event emit is best-effort
            pass


def _default_evidence_provider() -> EvidenceBundleResult:
    """Default provider: an empty LIVE-only evidence bundle (no account)."""
    return build_live_ai_evidence_bundle(sources=[OrderSource.LIVE])


__all__ = [
    "AI_TELEGRAM_MODULE",
    "AI_BRIEFING_HEADER",
    "AI_COMMANDS",
    "AICardType",
    "AICommandResult",
    "AIBriefingTelegram",
    "render_ai_card",
]
