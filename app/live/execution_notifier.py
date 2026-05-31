"""Live execution Telegram notifier (PR120 - independent app/live sender).

Pushes live execution operator cards to Telegram using the INDEPENDENT
``app.live`` Telegram transport (the same urllib transport PR111's
:class:`app.live.telegram_client.TelegramLiveClient` uses). It does NOT
reuse the legacy ``app.telegram`` AlertDispatcher.

Two card families flow through one stable schema
(:func:`app.live.execution_telegram.build_execution_telegram_payload`):

  - 空盘跑 / dry-run plan + reject cards
    (``SHADOW_ENTRY_PLAN`` / ``LIVE_RISK_REJECT`` / ``LIVE_EXECUTION_BLOCKED``):
    always ``real_order=false`` / ``order_id=--`` / ``actual_*=--`` /
    ``real_capital_changed=false``.
  - 有资金跑 real order / fill cards
    (``LIVE_ORDER_SUBMITTED`` / ``LIVE_ORDER_FILLED`` /
    ``LIVE_EXIT_FILLED`` ...): real ``order_id`` / actual fill price /
    fee / funding / net_pnl and ``real_order=true``.

Hard safety boundaries (the brief). The notifier:

  1. NEVER sends when ``outbound_enabled`` is False (or in dry-run) - it
     contacts no network and records ``TELEGRAM_OUTBOUND_SUPPRESSED``.
  2. ONLY ever sends to allow-listed chat ids.
  3. NEVER lets a shadow / dry-run card carry ``real_order=true`` (the
     payload builder forbids it; the notifier never overrides it).
  4. ONLY accepts ``OrderSource.LIVE``; SIM / BLIND / REPLAY /
     PAPER_SHADOW / BACKTEST / OFFLINE_AI / TELEGRAM_SANDBOX are refused
     and audited as ``LIVE_SOURCE_REJECTED``.
  5. De-duplicates by ``event_id`` (or ``client_order_id`` + payload
     type) so a retry never double-pushes the same lifecycle step.
  6. NEVER places / cancels / modifies an order. It imports NO order
     surface; it only renders + sends text. Telegram can never reach
     Binance through it.
  7. Exposes NO ``ai_*`` parameter. AI has no path to call it; the
     execution gateway already refuses ``ai_trade_authority`` before any
     payload is built.

This module performs network IO ONLY when outbound is enabled AND a real
transport is injected; every unit test injects a fake transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.events import Event, EventType
from app.exports.redaction import assert_no_forbidden_substrings, redact
from app.live.api_config import TelegramApiConfig
from app.live.execution_telegram import (
    execution_payload_dedup_key,
    render_execution_payload,
)
from app.live.status import TELEGRAM_OUTBOUND_DISABLED
from app.live.telegram_client import TelegramTransport, _default_transport

LIVE_EXECUTION_NOTIFIER_MODULE = "live.execution_notifier"

TELEGRAM_API_BASE = "https://api.telegram.org"

# Reason sentinels (stable, log-safe).
REASON_SENT = "sent"
REASON_SOURCE_NOT_LIVE = "source_not_live"
REASON_DUPLICATE = "duplicate_suppressed"
REASON_OUTBOUND_DISABLED = TELEGRAM_OUTBOUND_DISABLED
REASON_MISSING_TOKEN = "MISSING_TOKEN"
REASON_NO_ALLOWED_CHAT = "no_allowed_chat_id"
REASON_NO_TRANSPORT = "no_transport_configured"
REASON_SEND_FAILED = "send_failed"


@dataclass
class NotifyResult:
    """Outcome of a single :meth:`LiveExecutionNotifier.notify` call."""

    payload_type: str
    sent: bool = False
    sent_count: int = 0
    suppressed: bool = False
    deduped: bool = False
    reason: str = ""
    chat_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "sent": self.sent,
            "sent_count": self.sent_count,
            "suppressed": self.suppressed,
            "deduped": self.deduped,
            "reason": self.reason,
            "chat_ids": list(self.chat_ids),
        }


class LiveExecutionNotifier:
    """Sends live execution cards to Telegram via the independent transport."""

    def __init__(
        self,
        *,
        telegram_config: TelegramApiConfig,
        transport: TelegramTransport | None = None,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
        dry_run: bool = False,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._tg = telegram_config
        self._transport = transport
        self._runtime_mode = runtime_mode
        self._dry_run = bool(dry_run)
        self._event_repo = event_repo
        self._clock = clock
        # De-dup memory: keys already pushed at least once.
        self._sent_keys: set[str] = set()

    # ------------------------------------------------------------------
    # Construction helper
    # ------------------------------------------------------------------
    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
        dry_run: bool = False,
        transport: TelegramTransport | None = None,
        event_repo: Any | None = None,
    ) -> "LiveExecutionNotifier":
        """Build a notifier from a ``LiveApiConfig`` (or ``TelegramApiConfig``).

        A real urllib transport is wired ONLY when outbound could actually
        be used (outbound enabled, not dry-run, token present). Otherwise
        the transport stays ``None`` so nothing can contact the network.
        """
        tg = getattr(config, "telegram", config)
        if (
            transport is None
            and not dry_run
            and getattr(tg, "outbound_enabled", False)
            and getattr(tg, "has_token", False)
        ):
            transport = _default_transport()
        return cls(
            telegram_config=tg,
            transport=transport,
            runtime_mode=runtime_mode,
            dry_run=dry_run,
            event_repo=event_repo,
        )

    @property
    def outbound_enabled(self) -> bool:
        return bool(self._tg and self._tg.outbound_enabled) and not self._dry_run

    # ------------------------------------------------------------------
    # Notify
    # ------------------------------------------------------------------
    def notify(
        self,
        payload: dict[str, Any],
        *,
        source: OrderSource | str = OrderSource.LIVE,
    ) -> NotifyResult:
        """Render + send one execution payload (or suppress it).

        ``source`` is the provenance of the order the payload describes.
        Only ``OrderSource.LIVE`` is accepted; any other source is refused
        and audited (defence-in-depth on top of the gateway's isolation
        guard). The notifier never mutates the payload's ``real_order``
        flag - a shadow card stays a shadow card.
        """
        payload_type = str(payload.get("payload_type", payload.get("event_type", "?")))

        # 1. Live-source isolation (defence-in-depth).
        src_value = source.value if isinstance(source, OrderSource) else str(source)
        if src_value != OrderSource.LIVE.value:
            self._emit(
                EventType.LIVE_SOURCE_REJECTED,
                {
                    "reason": REASON_SOURCE_NOT_LIVE,
                    "blocked_source": src_value,
                    "payload_type": payload_type,
                },
            )
            return NotifyResult(
                payload_type=payload_type,
                suppressed=True,
                reason=REASON_SOURCE_NOT_LIVE,
            )

        # 2. De-dup: never push the same lifecycle step twice.
        key = execution_payload_dedup_key(payload)
        if key in self._sent_keys:
            return NotifyResult(
                payload_type=payload_type, deduped=True, reason=REASON_DUPLICATE
            )

        # 3. Outbound gate: disabled / dry-run -> never contact the network.
        if not self.outbound_enabled:
            self._emit(
                EventType.TELEGRAM_OUTBOUND_SUPPRESSED,
                {
                    "reason": REASON_OUTBOUND_DISABLED,
                    "dry_run": self._dry_run,
                    "payload_type": payload_type,
                },
            )
            return NotifyResult(
                payload_type=payload_type,
                suppressed=True,
                reason=REASON_OUTBOUND_DISABLED,
            )

        # 4. Token gate.
        if not (self._tg and self._tg.has_token):
            return NotifyResult(
                payload_type=payload_type, suppressed=True, reason=REASON_MISSING_TOKEN
            )

        # 5. Allow-list gate: only allow-listed chat ids ever receive a card.
        chat_ids = tuple(self._tg.allowed_chat_ids) if self._tg else ()
        if not chat_ids:
            return NotifyResult(
                payload_type=payload_type,
                suppressed=True,
                reason=REASON_NO_ALLOWED_CHAT,
            )

        # 6. Transport gate.
        if self._transport is None:
            return NotifyResult(
                payload_type=payload_type, suppressed=True, reason=REASON_NO_TRANSPORT
            )

        # 7. Render (redaction defence-in-depth: never let a secret reach
        # the wire even though the payload schema carries none).
        message = render_execution_payload(redact(dict(payload)))
        try:
            assert_no_forbidden_substrings(message)
        except AssertionError:  # pragma: no cover - payload carries no secret
            message = f"[ama-rt:live] {payload_type} (message withheld: redaction guard)"

        sent_count = 0
        failures = 0
        for chat_id in chat_ids:
            if not self._tg.is_chat_allowed(chat_id):  # pragma: no cover - chat_ids come from the allow-list
                continue
            body = {"chat_id": str(chat_id), "text": message}
            try:
                self._transport("sendMessage", self._method_url("sendMessage"), body)
            except Exception:  # secret-free; send failure is non-fatal
                failures += 1
                logger.debug("execution_notifier: send failed (non-fatal)")
                continue
            sent_count += 1
            self._emit(
                EventType.TELEGRAM_OUTBOUND_MESSAGE_SENT,
                {"chat_id": str(chat_id), "payload_type": payload_type},
            )

        if sent_count > 0:
            # Record the key only after a real send so a suppressed attempt
            # (outbound off) does not block a later genuine push.
            self._sent_keys.add(key)
            return NotifyResult(
                payload_type=payload_type,
                sent=True,
                sent_count=sent_count,
                reason=REASON_SENT,
                chat_ids=chat_ids,
            )

        return NotifyResult(
            payload_type=payload_type,
            suppressed=True,
            reason=REASON_SEND_FAILED,
            chat_ids=chat_ids,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _method_url(self, method: str) -> str:
        # The token is only ever placed in the URL handed to the transport;
        # it is never logged or returned.
        token = self._tg.bot_token.reveal() if self._tg else ""
        return f"{TELEGRAM_API_BASE}/bot{token}/{method}"

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=LIVE_EXECUTION_NOTIFIER_MODULE,
                    payload={
                        **payload,
                        # PR120 safety markers (audit visibility).
                        "trade_authority": False,
                        "ai_trade_authority": False,
                        "exchange_live_orders": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover - audit must never crash a notify
            logger.debug("execution_notifier: event emit failed (non-fatal)")


__all__ = [
    "LIVE_EXECUTION_NOTIFIER_MODULE",
    "REASON_SENT",
    "REASON_SOURCE_NOT_LIVE",
    "REASON_DUPLICATE",
    "REASON_OUTBOUND_DISABLED",
    "REASON_MISSING_TOKEN",
    "REASON_NO_ALLOWED_CHAT",
    "REASON_NO_TRANSPORT",
    "REASON_SEND_FAILED",
    "NotifyResult",
    "LiveExecutionNotifier",
]
