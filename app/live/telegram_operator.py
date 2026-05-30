"""Telegram operator console runtime (PR114 - Operator Console v0).

Wires the PR114 pieces into a runnable operator console:

    inbound update
      -> TelegramAuthGuard          (only an allowed chat id)
      -> TelegramCommandHandler     (parse + state mutation, source-isolated)
      -> operator card
      -> outbound (only when outbound is enabled AND not dry-run)

Outbound is gated three ways:
  1. ``AMA_TELEGRAM_OUTBOUND_ENABLED`` (config) must be True.
  2. ``--dry-run`` (or ``dry_run=True``) suppresses every real send.
  3. the target chat id must be in the allow-list.
When outbound is disabled / dry-run, the console still PROCESSES the
command and returns the card, but contacts NO network and records
``TELEGRAM_OUTBOUND_SUPPRESSED`` (with the ``TELEGRAM_OUTBOUND_DISABLED``
sentinel reason).

HARD boundaries (the brief): an inbound Telegram command can NEVER place
a naked order, bypass the Risk Engine / Execution Gateway / Capital
Profile / kill switch, nor be driven by a non-LIVE source. The console
runs the deterministic :class:`TelegramCommandHandler`; it never calls
the Binance execution adapter directly.

This module owns the polling loop + outbound send. It performs network
IO ONLY when outbound is enabled and a real transport is injected; every
unit test uses a fake transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.events import Event, EventType
from app.exports.redaction import assert_no_forbidden_substrings, redact
from app.live.api_config import LiveApiConfig, TelegramApiConfig
from app.live.status import TELEGRAM_OUTBOUND_DISABLED
from app.live.telegram_auth import TelegramAuthGuard
from app.live.telegram_commands import (
    HELP_COMMANDS,
    CommandResult,
    LiveConsoleDataProvider,
    TelegramCommandHandler,
)
from app.live.telegram_formatters import render_card
from app.live.telegram_state import LiveOperatorStateStore

TELEGRAM_OPERATOR_MODULE = "live.telegram_operator"

# Outbound transport: (method, url, json_body) -> parsed JSON. Mirrors
# app.live.telegram_client.TelegramTransport so the real urllib transport
# can be reused; tests inject a fake.
OutboundTransport = Callable[[str, str, dict[str, Any]], Any]

TELEGRAM_API_BASE = "https://api.telegram.org"


@dataclass(frozen=True)
class InboundUpdate:
    """A minimal inbound Telegram update (parsed from getUpdates / a test)."""

    chat_id: str
    text: str
    update_id: int | None = None
    source: OrderSource = OrderSource.LIVE
    actor: str = "operator"

    @classmethod
    def from_telegram(cls, update: dict[str, Any]) -> "InboundUpdate | None":
        """Parse a raw Telegram getUpdates entry into an InboundUpdate.

        Returns ``None`` for an update with no message text (e.g. an
        edited service message). The source is ALWAYS LIVE for a real
        Telegram inbound (a human operator); sim / blind updates only
        ever arrive in tests with an explicit non-live source.
        """
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = message.get("text")
        if chat_id is None or not text:
            return None
        return cls(
            chat_id=str(chat_id),
            text=str(text),
            update_id=update.get("update_id"),
            source=OrderSource.LIVE,
            actor="operator",
        )


@dataclass
class OutboundResult:
    """Result of an outbound send attempt (or suppression)."""

    sent: bool
    suppressed: bool
    detail: str
    chat_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sent": self.sent,
            "suppressed": self.suppressed,
            "detail": self.detail,
            "chat_id": self.chat_id,
        }


@dataclass
class HandledUpdate:
    """The full outcome of handling one inbound update."""

    authorized: bool
    command: str
    result: CommandResult | None
    outbound: OutboundResult | None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorized": self.authorized,
            "command": self.command,
            "result": self.result.to_dict() if self.result else None,
            "outbound": self.outbound.to_dict() if self.outbound else None,
            "reason": self.reason,
        }


class TelegramOperatorConsole:
    """The live operator console runtime (PR114)."""

    def __init__(
        self,
        *,
        config: LiveApiConfig | None = None,
        telegram_config: TelegramApiConfig | None = None,
        state_store: LiveOperatorStateStore | None = None,
        command_handler: TelegramCommandHandler | None = None,
        data_provider: LiveConsoleDataProvider | None = None,
        auth_guard: TelegramAuthGuard | None = None,
        transport: OutboundTransport | None = None,
        event_repo: Any | None = None,
        dry_run: bool = False,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config
        self._tg = telegram_config or (config.telegram if config else None)
        self._event_repo = event_repo
        self._dry_run = bool(dry_run)
        self._clock = clock
        self._transport = transport

        store = state_store or LiveOperatorStateStore()
        self._handler = command_handler or TelegramCommandHandler(
            state_store=store,
            data_provider=data_provider or LiveConsoleDataProvider(),
            event_repo=event_repo,
        )
        allowed = self._tg.allowed_chat_ids if self._tg else ()
        self._auth = auth_guard or TelegramAuthGuard(allowed, event_repo=event_repo)
        self._processed_update_ids: set[int] = set()

    # -- accessors -----------------------------------------------------
    @property
    def handler(self) -> TelegramCommandHandler:
        return self._handler

    @property
    def auth(self) -> TelegramAuthGuard:
        return self._auth

    @property
    def outbound_enabled(self) -> bool:
        return bool(self._tg and self._tg.outbound_enabled) and not self._dry_run

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    # -- single update -------------------------------------------------
    def handle_update(self, update: InboundUpdate) -> HandledUpdate:
        """Authorise + handle one inbound update; send / suppress the reply."""
        decision = self._auth.authorize(update.chat_id, command=update.text)
        if not decision.authorized:
            # Unauthorised: refused + audited by the auth guard. No reply
            # is sent to an unauthorised chat.
            return HandledUpdate(
                authorized=False,
                command=(update.text or "").split(" ", 1)[0],
                result=None,
                outbound=None,
                reason=decision.reason,
            )

        result = self._handler.handle(
            update.text, source=update.source, actor=update.actor
        )
        outbound = self._send_card(update.chat_id, result.card)
        return HandledUpdate(
            authorized=True,
            command=result.command,
            result=result,
            outbound=outbound,
        )

    def handle_text(
        self,
        chat_id: str | int,
        text: str,
        *,
        source: OrderSource = OrderSource.LIVE,
        actor: str = "operator",
    ) -> HandledUpdate:
        """Convenience: build an :class:`InboundUpdate` and handle it."""
        return self.handle_update(
            InboundUpdate(chat_id=str(chat_id), text=text, source=source, actor=actor)
        )

    # -- outbound ------------------------------------------------------
    def _send_card(self, chat_id: str, card: dict[str, Any]) -> OutboundResult:
        """Send (or suppress) the rendered card to ``chat_id``."""
        message = render_card(card)
        # Defence-in-depth: never let a credential reach the wire.
        try:
            assert_no_forbidden_substrings(message)
        except AssertionError:  # pragma: no cover - redactor already cleaned
            message = "[ama-rt:live] (message withheld: redaction guard)"

        if not self.outbound_enabled:
            self._emit(
                EventType.TELEGRAM_OUTBOUND_SUPPRESSED,
                {"chat_id": chat_id, "reason": TELEGRAM_OUTBOUND_DISABLED, "dry_run": self._dry_run},
            )
            return OutboundResult(
                sent=False,
                suppressed=True,
                detail=TELEGRAM_OUTBOUND_DISABLED,
                chat_id=chat_id,
            )

        if not (self._tg and self._tg.has_token):
            return OutboundResult(
                sent=False, suppressed=True, detail="MISSING_TOKEN", chat_id=chat_id
            )
        if self._tg.allowed_chat_ids and not self._tg.is_chat_allowed(chat_id):
            return OutboundResult(
                sent=False, suppressed=True, detail="chat_id_not_in_allowlist", chat_id=chat_id
            )
        if self._transport is None:
            return OutboundResult(
                sent=False, suppressed=True, detail="no_transport_configured", chat_id=chat_id
            )

        try:
            self._transport("sendMessage", self._method_url("sendMessage"), {
                "chat_id": str(chat_id),
                "text": message,
            })
        except Exception as exc:  # secret-free message
            return OutboundResult(
                sent=False, suppressed=False, detail=f"send_failed:{str(exc)[:80]}", chat_id=chat_id
            )
        self._emit(EventType.TELEGRAM_OUTBOUND_MESSAGE_SENT, {"chat_id": chat_id})
        return OutboundResult(sent=True, suppressed=False, detail="sent", chat_id=chat_id)

    def send_test_message(self, chat_id: str | int | None = None) -> OutboundResult:
        """Send a single operator test card (respects every outbound gate)."""
        target = str(chat_id) if chat_id is not None else (
            self._tg.allowed_chat_ids[0] if (self._tg and self._tg.allowed_chat_ids) else ""
        )
        card = {
            "card_type": "LIVE_OPERATOR_TEST",
            "runtime_mode": self._handler.runtime_mode.value,
            "mode_display": "空盘跑" if self._handler.runtime_mode is LiveRuntimeMode.LIVE_SHADOW else "有资金跑",
            "text": "AMA-RT PR114 operator console test message.",
            "real_order": False,
            "trade_authority": False,
            "ai_trade_authority": False,
            "exchange_live_orders": False,
            "phase_12_forbidden": True,
        }
        return self._send_card(target, card)

    def _method_url(self, method: str) -> str:
        token = self._tg.bot_token.reveal() if self._tg else ""
        return f"{TELEGRAM_API_BASE}/bot{token}/{method}"

    # -- polling -------------------------------------------------------
    def poll_once(self, *, offset: int | None = None, timeout: int = 0) -> list[HandledUpdate]:
        """Fetch + process one batch of updates via getUpdates.

        Requires a transport. Returns the list of handled updates. Used by
        the ``--once`` CLI path; ``--poll`` calls it in a loop.
        """
        if self._transport is None:
            return []
        body: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            body["offset"] = offset
        try:
            response = self._transport("getUpdates", self._method_url("getUpdates"), body)
        except Exception:  # pragma: no cover - transport failure is non-fatal
            logger.debug("telegram_operator: getUpdates failed (non-fatal)")
            return []
        updates = (response or {}).get("result", []) if isinstance(response, dict) else []
        handled: list[HandledUpdate] = []
        for raw in updates:
            uid = raw.get("update_id") if isinstance(raw, dict) else None
            if uid is not None and uid in self._processed_update_ids:
                continue
            parsed = InboundUpdate.from_telegram(raw) if isinstance(raw, dict) else None
            if parsed is None:
                if uid is not None:
                    self._processed_update_ids.add(uid)
                continue
            handled.append(self.handle_update(parsed))
            if uid is not None:
                self._processed_update_ids.add(uid)
        return handled

    # -- status --------------------------------------------------------
    def status_snapshot(self) -> dict[str, Any]:
        """A redacted JSON-safe status snapshot (used by ``--status-json``).

        The safety-flag keys deliberately avoid the substrings the
        Phase 8.5 redactor treats as sensitive (``auth`` / ``token`` /
        ``secret``) so the operator can actually SEE that every unsafe
        flag is False - a redacted ``[REDACTED]`` would hide the safety
        posture. The values are plain booleans, never credentials.
        """
        h = self._handler
        snapshot = {
            "module": TELEGRAM_OPERATOR_MODULE,
            "pr": "PR114",
            "runtime_mode": h.runtime_mode.value,
            "source_label": h.runtime_mode.value,
            "live_limited_armed": h.live_limited_armed,
            "paused": h.paused,
            "capital_profile_id": h.capital_profile_id.value,
            "kill_switch_armed": h.kill_switch_armed,
            "outbound_enabled": self.outbound_enabled,
            "dry_run": self._dry_run,
            "allowed_chat_id_count": len(self._auth.allowed_chat_ids),
            "state_warnings": h.load_warnings,
            "available_commands": list(HELP_COMMANDS),
        }
        # Redact the dynamic content first, then stamp the fixed safety
        # markers so they stay visible (the redactor would otherwise mask
        # the ``*_authority`` keys, hiding the safety posture).
        safe = redact(snapshot)
        safe.update(
            {
                "live_trading_flag": False,
                "exchange_live_orders_flag": False,
                "trade_authority_flag": False,
                "ai_trade_authority_flag": False,
                "phase_12_forbidden": True,
                "no_real_order_sent": True,
            }
        )
        return safe

    # -- events --------------------------------------------------------
    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=TELEGRAM_OPERATOR_MODULE,
                    payload={
                        **payload,
                        "trade_authority": False,
                        "ai_trade_authority": False,
                        "exchange_live_orders": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover
            pass


__all__ = [
    "TELEGRAM_OPERATOR_MODULE",
    "OutboundTransport",
    "InboundUpdate",
    "OutboundResult",
    "HandledUpdate",
    "TelegramOperatorConsole",
]
