"""Telegram Bot live API client for the Live API Integration Pack (PR111).

PR111 contract:

  - Token is held as :class:`app.live.secrets.SecretValue`; it never
    appears in logs / repr / exceptions (only masked).
  - Outbound is gated by ``TelegramApiConfig.outbound_enabled``. When
    disabled, :meth:`send_test_message` does NOT contact the network and
    returns a result whose status is ``TELEGRAM_OUTBOUND_DISABLED``.
  - A test message is only sent when outbound is enabled AND the caller
    explicitly requests it.
  - Message formatting is compatible with the PR110 Telegram Operator
    Contract: every message carries a ``[ama-rt:<tag>]`` banner with the
    runtime mode + ``live=on/off`` token (matching
    :mod:`app.telegram.formatter`).
  - No command live-switching, leverage / margin / order control is
    exposed here. A full operator console is a later PR (PR114).

The default transport uses :mod:`urllib.request` (no third-party
dependency). Tests inject a fake transport callable.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from loguru import logger

from app.core.errors import LiveApiError
from app.core.events import Event, EventType
from app.live.api_config import LiveRuntimeMode, TelegramApiConfig
from app.live.secrets import API_HEALTH_MISSING_SECRET
from app.live.status import HealthStatus, TELEGRAM_OUTBOUND_DISABLED

#: Transport callable: (method, url, json_body) -> parsed JSON value.
TelegramTransport = Callable[[str, str, Mapping[str, Any]], Any]

# Operator-contract banner tag used by PR111 test messages.
TELEGRAM_TEST_TAG = "system_status"


@dataclass(frozen=True)
class TelegramSendResult:
    """Result of a Telegram outbound attempt."""

    status: HealthStatus
    sent: bool
    detail: str
    chat_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "sent": self.sent,
            "detail": self.detail,
            "chat_id": self.chat_id,
        }


def _default_transport(timeout_seconds: float = 5.0) -> TelegramTransport:
    """Return a default urllib-based Telegram transport.

    The URL embeds the bot token, so it is NEVER logged. Errors are
    converted into :class:`LiveApiError` with a token-free message.
    """

    def _post(method: str, url: str, body: Mapping[str, Any]) -> Any:
        data = json.dumps(dict(body)).encode("utf-8")
        req = urllib.request.Request(
            url,
            method="POST",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read()
                parsed = json.loads(raw.decode("utf-8"))
                if resp.status != 200 or not parsed.get("ok", False):
                    # Do NOT echo the URL (it carries the token).
                    raise LiveApiError(f"telegram: API method {method} failed")
                return parsed
        except urllib.error.HTTPError:
            raise LiveApiError(f"telegram: HTTP error on method {method}") from None
        except urllib.error.URLError as exc:
            raise LiveApiError(f"telegram: transport error on method {method}: {exc.reason}") from None
        except (json.JSONDecodeError, ValueError):
            raise LiveApiError(f"telegram: malformed JSON on method {method}") from None

    return _post


def format_operator_message(
    text: str,
    *,
    runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
    tag: str = TELEGRAM_TEST_TAG,
) -> str:
    """Format a message compatible with the PR110 operator contract.

    Produces ``[ama-rt:<tag>] mode=<MODE> live=on|off <text>``. PR111
    keeps ``live=off`` because no live order path is enabled.
    """
    live_on = runtime_mode.allows_live_orders  # always False in PR111 usage
    banner = f"mode={runtime_mode.value} live={'on' if live_on else 'off'}"
    body = str(text).replace("\n", " ").strip()
    return f"[ama-rt:{tag}] {banner} {body}".rstrip()


class TelegramLiveClient:
    """Telegram bot live client (PR111)."""

    name = "telegram_live"
    API_BASE = "https://api.telegram.org"

    def __init__(
        self,
        config: TelegramApiConfig,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
        transport: TelegramTransport | None = None,
        request_timeout_seconds: float = 5.0,
        event_repo: Any | None = None,
    ) -> None:
        self._config = config
        self._runtime_mode = runtime_mode
        self._transport: TelegramTransport = transport or _default_transport(
            timeout_seconds=request_timeout_seconds
        )
        self._event_repo = event_repo

    @property
    def config(self) -> TelegramApiConfig:
        return self._config

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(event_type=event_type, source_module=self.name, payload=payload)
            )
        except Exception:  # pragma: no cover
            logger.debug("telegram_live: event emit failed (non-fatal)")

    def _method_url(self, method: str) -> str:
        # The token is only ever placed in the URL handed to the
        # transport; it is never logged or returned.
        token = self._config.bot_token.reveal()
        return f"{self.API_BASE}/bot{token}/{method}"

    def get_me(self) -> dict[str, Any]:
        """Call getMe to validate the token. Requires a present token."""
        if not self._config.has_token:
            raise LiveApiError(f"telegram: {API_HEALTH_MISSING_SECRET}")
        return self._transport("getMe", self._method_url("getMe"), {})

    def send_test_message(
        self,
        chat_id: str | int,
        text: str = "AMA-RT PR111 live API health-check test message.",
    ) -> TelegramSendResult:
        """Send an operator-contract test message - only when outbound is enabled.

        Outbound disabled -> returns a ``TELEGRAM_OUTBOUND_DISABLED``
        result and contacts no network. Missing token -> WARN. Chat id
        not in the allow-list -> WARN (still does not send).
        """

        if not self._config.outbound_enabled:
            self._emit(
                EventType.TELEGRAM_OUTBOUND_DISABLED,
                {"reason": TELEGRAM_OUTBOUND_DISABLED, "chat_id": str(chat_id)},
            )
            return TelegramSendResult(
                status=HealthStatus.SKIPPED,
                sent=False,
                detail=TELEGRAM_OUTBOUND_DISABLED,
                chat_id=str(chat_id),
            )

        if not self._config.has_token:
            return TelegramSendResult(
                status=HealthStatus.WARN,
                sent=False,
                detail=API_HEALTH_MISSING_SECRET,
                chat_id=str(chat_id),
            )

        if self._config.allowed_chat_ids and not self._config.is_chat_allowed(chat_id):
            return TelegramSendResult(
                status=HealthStatus.WARN,
                sent=False,
                detail="chat_id_not_in_allowlist",
                chat_id=str(chat_id),
            )

        message = format_operator_message(text, runtime_mode=self._runtime_mode)
        body = {"chat_id": str(chat_id), "text": message}
        try:
            self._transport("sendMessage", self._method_url("sendMessage"), body)
        except LiveApiError as exc:
            return TelegramSendResult(
                status=HealthStatus.FAIL,
                sent=False,
                detail=str(exc),
                chat_id=str(chat_id),
            )
        self._emit(
            EventType.TELEGRAM_TEST_MESSAGE_SENT,
            {"chat_id": str(chat_id), "runtime_mode": self._runtime_mode.value},
        )
        return TelegramSendResult(
            status=HealthStatus.PASS,
            sent=True,
            detail="sent",
            chat_id=str(chat_id),
        )


__all__ = [
    "TelegramLiveClient",
    "TelegramTransport",
    "TelegramSendResult",
    "format_operator_message",
    "TELEGRAM_TEST_TAG",
]
