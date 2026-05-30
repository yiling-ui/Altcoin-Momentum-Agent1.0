"""Telegram operator authorisation + live-source isolation (PR114).

Two gates protect the live operator console:

  1. :class:`TelegramAuthGuard` - only a chat id in the configured
     allow-list (``AMA_TELEGRAM_ALLOWED_CHAT_IDS``) may run a command.
     An unauthorised chat id is refused and recorded as
     ``TELEGRAM_UNAUTHORIZED_COMMAND``; it can never change live mode /
     profile / risk / execution.

  2. :func:`assert_live_source` / :class:`LiveSourceGuard` - only an
     ``OrderSource.LIVE`` actor may drive a live state mutation. A
     blind / replay / sim / paper-shadow / backtest / offline-AI /
     telegram-sandbox source attempting to change the live runtime mode,
     capital profile, risk state, kill switch, or request an
     execution-gateway action is refused and recorded as
     ``LIVE_SOURCE_REJECTED``. This is the PR114 strengthening of the
     PR110 path-isolation boundary beyond just the order gateway.

Neither gate ever opens a network socket, places an order, or flips a
safety flag. Both are deterministic and safe for logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.enums import OrderSource
from app.core.errors import LiveSourceRejected, TelegramUnauthorizedCommand
from app.core.events import Event, EventType

TELEGRAM_AUTH_MODULE = "live.telegram_auth"

# AI never drives the console. An AI-origin actor id is refused outright.
AI_ACTOR_IDS: frozenset[str] = frozenset(
    {"ai", "deepseek", "llm", "offline_ai", "ai_briefing"}
)


@dataclass(frozen=True)
class AuthDecision:
    """Result of an authorisation check (PR114)."""

    authorized: bool
    chat_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorized": self.authorized,
            "chat_id": self.chat_id,
            "reason": self.reason,
        }


class TelegramAuthGuard:
    """Enforces the operator chat-id allow-list (PR114)."""

    def __init__(
        self,
        allowed_chat_ids: Iterable[str | int] | None = None,
        *,
        event_repo: Any | None = None,
    ) -> None:
        self._allowed = frozenset(str(c).strip() for c in (allowed_chat_ids or ()) if str(c).strip())
        self._event_repo = event_repo

    @property
    def allowed_chat_ids(self) -> frozenset[str]:
        return self._allowed

    def is_authorized(self, chat_id: str | int | None) -> bool:
        """True only when ``chat_id`` is in a non-empty allow-list.

        An EMPTY allow-list authorises NOBODY (fail closed): if the
        operator has not configured any chat id, no chat may control the
        live system.
        """
        if chat_id is None:
            return False
        if not self._allowed:
            return False
        return str(chat_id).strip() in self._allowed

    def authorize(self, chat_id: str | int | None, *, command: str = "") -> AuthDecision:
        """Return an :class:`AuthDecision`; audit a refusal.

        Does NOT raise - callers that want a hard stop use
        :meth:`assert_authorized`.
        """
        cid = "" if chat_id is None else str(chat_id).strip()
        if self.is_authorized(chat_id):
            return AuthDecision(authorized=True, chat_id=cid, reason="chat_id_allowed")
        reason = (
            "no_allowed_chat_ids_configured"
            if not self._allowed
            else "chat_id_not_in_allowlist"
        )
        self._emit_unauthorized(cid, command, reason)
        return AuthDecision(authorized=False, chat_id=cid, reason=reason)

    def assert_authorized(self, chat_id: str | int | None, *, command: str = "") -> None:
        """Raise :class:`TelegramUnauthorizedCommand` for an unauthorised chat."""
        decision = self.authorize(chat_id, command=command)
        if not decision.authorized:
            raise TelegramUnauthorizedCommand(
                f"telegram operator command refused: chat id is not authorised "
                f"({decision.reason}). Only allow-listed operator chat ids may "
                f"control the live system."
            )

    def _emit_unauthorized(self, chat_id: str, command: str, reason: str) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=EventType.TELEGRAM_UNAUTHORIZED_COMMAND,
                    source_module=TELEGRAM_AUTH_MODULE,
                    payload={
                        "chat_id": chat_id,
                        # The command head only (never the raw args, which
                        # could carry a confirmation code or other value).
                        "command": (command or "").split(" ", 1)[0],
                        "reason": reason,
                        # PR114 safety markers.
                        "trade_authority": False,
                        "ai_trade_authority": False,
                        "exchange_live_orders": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover - audit must never crash auth
            pass


# ---------------------------------------------------------------------------
# Live-source isolation (PR114 hardening)
# ---------------------------------------------------------------------------
def _coerce_source(source: OrderSource | str | None) -> OrderSource:
    """Coerce an actor source to an :class:`OrderSource` (fail-safe to SIM).

    An unknown / missing source maps to ``OrderSource.SIM`` (a blocked
    source), never ``LIVE`` - the same fail-safe posture as PR110's
    :func:`classify_source_module`.
    """
    if isinstance(source, OrderSource):
        return source
    if source is None:
        return OrderSource.SIM
    try:
        return OrderSource(str(source))
    except ValueError:
        return OrderSource.SIM


class LiveSourceGuard:
    """Refuses any non-LIVE source attempting to drive live operation.

    PR114 extends the PR110 isolation boundary beyond the order gateway:
    a non-LIVE source may not change the live runtime mode / capital
    profile / risk / kill switch, nor request an execution-gateway
    action. Only ``OrderSource.LIVE`` is admissible.
    """

    def __init__(self, *, event_repo: Any | None = None) -> None:
        self._event_repo = event_repo
        self._rejected_count = 0

    @property
    def rejected_count(self) -> int:
        return self._rejected_count

    def is_live_source(self, source: OrderSource | str | None) -> bool:
        return _coerce_source(source) is OrderSource.LIVE

    def authorize(
        self, source: OrderSource | str | None, *, action: str = "live_mutation"
    ) -> bool:
        """Return True for a LIVE source; audit + count a refusal otherwise."""
        coerced = _coerce_source(source)
        if coerced is OrderSource.LIVE:
            return True
        self._rejected_count += 1
        self._emit_rejected(coerced, action)
        return False

    def assert_live_source(
        self, source: OrderSource | str | None, *, action: str = "live_mutation"
    ) -> None:
        """Raise :class:`LiveSourceRejected` for any non-LIVE source."""
        if not self.authorize(source, action=action):
            coerced = _coerce_source(source)
            raise LiveSourceRejected(
                f"live operation refused: source={coerced.value} cannot {action}. "
                f"Only OrderSource.LIVE may drive live mode / profile / risk / "
                f"execution. Blind / replay / sim / paper-shadow / backtest / "
                f"offline-AI / telegram-sandbox sources are isolated from live "
                f"operation (PR114)."
            )

    def _emit_rejected(self, source: OrderSource, action: str) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=EventType.LIVE_SOURCE_REJECTED,
                    source_module=TELEGRAM_AUTH_MODULE,
                    payload={
                        "rejected_source": source.value,
                        "action": action,
                        "trade_authority": False,
                        "ai_trade_authority": False,
                        "exchange_live_orders": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover
            pass


def assert_live_source(
    source: OrderSource | str | None,
    *,
    action: str = "live_mutation",
    event_repo: Any | None = None,
) -> None:
    """Convenience one-shot live-source assertion (raises on non-LIVE)."""
    LiveSourceGuard(event_repo=event_repo).assert_live_source(source, action=action)


def is_ai_actor(actor: str | None) -> bool:
    """True when an actor id looks like an AI / LLM origin (never allowed)."""
    return bool(actor) and str(actor).strip().lower() in AI_ACTOR_IDS


__all__ = [
    "TELEGRAM_AUTH_MODULE",
    "AI_ACTOR_IDS",
    "AuthDecision",
    "TelegramAuthGuard",
    "LiveSourceGuard",
    "assert_live_source",
    "is_ai_actor",
]
