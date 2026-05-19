"""Phase 10D - Telegram outbound transport (Issue #10 Part 4).

Three classes:

  - :class:`TelegramOutboundClient` - abstract base. Defines the
    receive-only outbound surface: ``send_message``,
    ``send_document``. NO subclass may add a write surface to the
    exchange / LLM / Risk Engine; tests assert this at the AST level.
  - :class:`FakeTelegramClient` - deterministic in-process recorder.
    Used by the boot drill, by every Phase 10D test, and by every
    paper-mode run. Records each call into an ordered tuple so the
    AlertDispatcher can verify its own behaviour.
  - :class:`TelegramHttpClient` - refusal-only HTTP skeleton. Refuses
    *every* call with :class:`TelegramTransportError` even when both
    ``outbound_enabled`` and ``token_provided`` are True. The real
    transport ships behind Spec §41 Go/No-Go in a separate PR.

Phase 10D boundary
------------------

Nothing in this module:

  - imports an exchange SDK / HTTP / WebSocket / LLM client / third
    party Telegram bot library (``python_telegram_bot`` /
    ``telebot`` / ``aiogram`` / etc.)
  - reads ``os.environ`` for credentials
  - opens a socket
  - defines a write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - calls :meth:`EventRepository.append_event` / ``append_many``
    directly - that is the AlertDispatcher's job
  - takes an ``api_key`` / ``api_secret`` / ``bot_token`` parameter
    or hard-codes any concrete env-var literal

Bot-token policy
----------------

A real Telegram outbound transport eventually requires a bot token.
Phase 10D does NOT introduce one. The :class:`TelegramHttpClient`
constructor takes a *boolean* ``token_provided`` flag so the caller
can prove the operator has supplied a token *somewhere* (a future
secret manager) without that token ever appearing as a parameter or
literal under ``app/telegram/``. Even so, the skeleton refuses every
call: the real transport requires the Spec §41 Go/No-Go gate to land
on top.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.errors import TelegramTransportError


class OutboundSurface(str, Enum):
    """The two outbound surfaces Phase 10D supports."""

    SEND_MESSAGE = "send_message"
    SEND_DOCUMENT = "send_document"


@dataclass(frozen=True)
class OutboundCall:
    """One recorded outbound call.

    Frozen so test fixtures can compare across runs without copying.
    The ``timestamp`` field is populated by the caller; the transport
    does not mint timestamps so deterministic tests stay deterministic.
    """

    surface: OutboundSurface
    chat_id: str
    text: str
    document_filename: str | None = None
    document_size_bytes: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    timestamp: int | None = None


class TelegramOutboundClient(ABC):
    """Abstract Telegram outbound surface.

    Two abstract methods only - any sub-class that adds a third
    surface (for example a future ``send_photo``) must extend the
    enum first so the AST scan continues to enforce the closed list.

    Phase 10D contract:

      - Both methods accept already-formatted text. Formatting is the
        :mod:`app.telegram.formatter` module's responsibility; this
        layer never re-templates.
      - Both methods consume *redacted* bytes / strings - the caller
        is responsible for running input through the Phase 8.5
        :func:`app.exports.redaction.redact` first. Defence-in-depth
        belt-and-braces lives in :class:`AlertDispatcher`.
      - Both methods are safe to fail. A transport error is a
        recoverable :class:`TelegramTransportError`, never a
        :class:`SafetyViolation`.
      - No method calls the Risk Engine, the Execution FSM, or the
        Capital Flow Engine. AST scans enforce this.
    """

    name: str = "telegram_outbound_abc"

    @abstractmethod
    def send_message(self, chat_id: str, text: str, **kwargs: Any) -> None:
        """Send a short text message. Raises :class:`TelegramTransportError`
        on transport failure."""

    @abstractmethod
    def send_document(
        self,
        chat_id: str,
        document_path: str,
        document_bytes: bytes,
        *,
        filename: str | None = None,
        caption: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Send a redacted document attachment. Raises
        :class:`TelegramTransportError` on transport failure."""

    # --- Optional subclass hooks ----------------------------------------
    def is_enabled(self) -> bool:
        """Return True iff the transport is configured to actually send.

        Phase 10D defaults to False everywhere; the only path that
        flips this is a future PR behind Go/No-Go.
        """
        return False


class FakeTelegramClient(TelegramOutboundClient):
    """Deterministic in-process recorder.

    Accumulates every call into the ``calls`` tuple so tests can
    assert on send counts, dedupe behaviour, redaction, and
    cooldowns without hitting a real network.

    The recorder is the default transport for the boot drill, every
    Phase 10D unit test, and any paper-mode run.

    Failure injection: when ``failure_mode`` is set the next ``send_*``
    call raises the configured :class:`TelegramTransportError`. The
    recorder still records the attempt under the
    ``failure_mode_calls`` tuple so the AlertDispatcher's error
    handling can be tested deterministically.
    """

    name: str = "telegram_fake"

    def __init__(
        self,
        *,
        outbound_enabled: bool = True,
        failure_mode: str | None = None,
    ) -> None:
        self._enabled = bool(outbound_enabled)
        self._failure_mode = failure_mode
        self._calls: list[OutboundCall] = []
        self._failed_calls: list[OutboundCall] = []

    # --- Public read API ------------------------------------------------
    @property
    def calls(self) -> tuple[OutboundCall, ...]:
        return tuple(self._calls)

    @property
    def failed_calls(self) -> tuple[OutboundCall, ...]:
        return tuple(self._failed_calls)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    def is_enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        self._calls = []
        self._failed_calls = []

    def set_failure_mode(self, failure_mode: str | None) -> None:
        self._failure_mode = failure_mode

    # --- Implementation -------------------------------------------------
    def send_message(self, chat_id: str, text: str, **kwargs: Any) -> None:
        call = OutboundCall(
            surface=OutboundSurface.SEND_MESSAGE,
            chat_id=str(chat_id),
            text=str(text),
            extras=dict(kwargs),
            timestamp=kwargs.get("timestamp"),
        )
        if self._failure_mode is not None:
            self._failed_calls.append(call)
            raise TelegramTransportError(
                f"FakeTelegramClient injected failure: {self._failure_mode}"
            )
        self._calls.append(call)

    def send_document(
        self,
        chat_id: str,
        document_path: str,
        document_bytes: bytes,
        *,
        filename: str | None = None,
        caption: str | None = None,
        **kwargs: Any,
    ) -> None:
        if not isinstance(document_bytes, (bytes, bytearray, memoryview)):
            raise TypeError(
                "document_bytes must be bytes-like; got "
                f"{type(document_bytes).__name__}"
            )
        bytes_payload = bytes(document_bytes)
        # Belt-and-braces: refuse to record an empty path.
        if not document_path:
            raise ValueError("document_path must not be empty")
        call = OutboundCall(
            surface=OutboundSurface.SEND_DOCUMENT,
            chat_id=str(chat_id),
            text=str(caption or ""),
            document_filename=str(filename or document_path),
            document_size_bytes=len(bytes_payload),
            extras={
                "document_path": str(document_path),
                "caption": str(caption or ""),
                **{k: v for k, v in kwargs.items() if k != "document_bytes"},
            },
            timestamp=kwargs.get("timestamp"),
        )
        if self._failure_mode is not None:
            self._failed_calls.append(call)
            raise TelegramTransportError(
                f"FakeTelegramClient injected failure: {self._failure_mode}"
            )
        self._calls.append(call)


class TelegramHttpClient(TelegramOutboundClient):
    """Refusal-only HTTP skeleton.

    The class exists so callers (and type-checkers) have a stable
    surface to reference. Every method refuses with
    :class:`TelegramTransportError` even when both
    ``outbound_enabled=True`` and ``token_provided=True``. The real
    HTTP transport ships behind the Spec §41 Go/No-Go checklist in a
    separate PR.

    Why a refusal-only skeleton instead of an absent class?

      - Phase 10D forbids importing ``aiohttp`` / ``httpx`` /
        ``requests`` / a third-party Telegram bot SDK; any future
        maintainer who quietly imports one fails the AST scan.
      - The skeleton documents the closed surface (``send_message``
        + ``send_document``) so callers cannot accidentally invent a
        third surface.
      - The constructor refuses any ``api_key`` / ``api_secret`` /
        ``bot_token`` parameter or literal; it accepts a single
        ``token_provided: bool`` flag so the caller can prove a
        secret manager is wired in.
    """

    name: str = "telegram_http_skeleton"

    def __init__(
        self,
        *,
        outbound_enabled: bool = False,
        token_provided: bool = False,
    ) -> None:
        # NOTE: this constructor INTENTIONALLY does not accept any
        # credential parameter or read any environment variable. The
        # AST scan in tests/unit/test_phase10d_no_network.py enforces
        # this on every file under app/telegram/.
        self._enabled = bool(outbound_enabled)
        self._token_provided = bool(token_provided)

    @property
    def outbound_enabled(self) -> bool:
        return self._enabled

    @property
    def token_provided(self) -> bool:
        return self._token_provided

    def is_enabled(self) -> bool:
        return False  # Phase 10D refuses every call regardless.

    def send_message(self, chat_id: str, text: str, **kwargs: Any) -> None:
        raise TelegramTransportError(
            "TelegramHttpClient is a refusal-only Phase 10D skeleton. The "
            "real outbound transport ships behind the Spec §41 Go/No-Go "
            "checklist in a separate PR. Use FakeTelegramClient for paper "
            "mode."
        )

    def send_document(
        self,
        chat_id: str,
        document_path: str,
        document_bytes: bytes,
        *,
        filename: str | None = None,
        caption: str | None = None,
        **kwargs: Any,
    ) -> None:
        raise TelegramTransportError(
            "TelegramHttpClient is a refusal-only Phase 10D skeleton. The "
            "real document upload path ships behind the Spec §41 Go/No-Go "
            "checklist in a separate PR. Use FakeTelegramClient for paper "
            "mode."
        )


__all__ = [
    "OutboundSurface",
    "OutboundCall",
    "TelegramOutboundClient",
    "FakeTelegramClient",
    "TelegramHttpClient",
]
