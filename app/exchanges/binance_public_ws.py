"""Binance public-market WebSocket client (Phase 11C.1B - PR-B).

Why this module exists
----------------------

Phase 11C.1A (PR-A) capped the public REST gateway with a sliding-window
rate-limit governor and shut every per-loop detail REST surface so the
bootstrap path could not trigger HTTP 429 / 418 again. The PR-A
trade-off was that the runner could see *only* the symbols the bootstrap
already knew about; it could not detect a brand-new "demon coin"
(妖币) that suddenly woke up between two bootstrap cadences.

Phase 11C.1B (PR-B) restores the discovery surface by driving an
**all-market radar** off Binance's public WebSocket streams. The
five streams below are the only network surfaces this module is
allowed to subscribe to:

  - ``!ticker@arr``        - 24h rolling stats for every symbol
  - ``!miniTicker@arr``    - light-weight last/volume push
  - ``!bookTicker``        - per-symbol best bid/ask updates
  - ``!markPrice@arr``     - mark price + funding rate per symbol
  - ``!forceOrder@arr``    - liquidation events

Phase 11C.1B boundary
---------------------

This module enforces, at construction time and on every subscribe:

  * NO Binance API key
  * NO Binance API secret
  * NO ``signature`` / ``timestamp`` / ``recvWindow`` / ``apiKey`` query
  * NO ``listenKey`` / user data stream
  * NO private WebSocket / trading WebSocket API
  * NO ``ws/<listenKey>`` / ``userDataStream`` URL
  * NO third-party HTTP / WebSocket / SDK import (stdlib + loguru only)
  * NO write surface (the four ``ExchangeClientBase`` refusals are
    inherited unchanged through the host :class:`BinancePublicClient`)

The default transport is :class:`_RefusalTransport`, which raises
:class:`NotImplementedError` on every attempt to actually open a
socket. Phase 11C.1B does NOT ship a real WS transport; the runner
and CI exercise the client through the deterministic
:class:`InProcessWSPump` (see :class:`WSMessagePump`). A real
WS adapter is a Phase 11C.1B follow-up that lives behind its own
review (PR-B-followup) and the no-network audit pinning a stdlib-only
transport will hold throughout.

Threading
---------

The client is single-threaded by construction. A future async / multi-
threaded runner MUST wrap :meth:`pump_messages` and the heartbeat
helpers with its own mutex. Phase 11C.1B's runner is the same
single-threaded polling loop PR-A introduced.
"""

from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from loguru import logger

from app.core.clock import now_ms
from app.core.errors import SafeModeViolation
from app.core.events import Event, EventType


# ---------------------------------------------------------------------------
# Stream allowlist + denylist
# ---------------------------------------------------------------------------

#: The canonical Phase 11C.1B PUBLIC market WebSocket stream allowlist.
#: Every stream below is documented as "Public" in the Binance USDT-M
#: Futures WebSocket reference and requires NO authentication.
PUBLIC_WS_STREAM_ALLOWLIST: frozenset[str] = frozenset(
    {
        "!ticker@arr",
        "!miniTicker@arr",
        "!bookTicker",
        "!markPrice@arr",
        "!forceOrder@arr",
    }
)

#: Allowlist of allowed stream prefixes for symbol-suffixed streams.
#: Phase 11C.1B does NOT subscribe to per-symbol streams in the
#: default radar but the allowlist keeps the surface small in case a
#: future PR adds e.g. ``btcusdt@bookTicker``. Every entry MUST be
#: PUBLIC.
PUBLIC_WS_STREAM_PREFIX_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Per-symbol equivalents of the array streams above. They are
        # accepted only when they end in one of the public suffixes.
        "@ticker",
        "@miniTicker",
        "@bookTicker",
        "@markPrice",
        "@forceOrder",
        # Liquidation per-symbol stream alias.
        "@forceOrder@1s",
    }
)

#: The full Phase 11C.1B refusal list. Any stream / URL / parameter
#: that matches one of these substrings is refused with
#: :class:`SafeModeViolation` regardless of how the caller composed
#: it. Every entry is deliberately specific enough to NOT clash with
#: an allowlisted public stream (``!forceOrder@arr`` contains the
#: substring ``order``, but ``order`` is NOT on this list - we use
#: the private-event-type patterns ``ordertradeupdate`` /
#: ``orderupdate`` instead).
FORBIDDEN_WS_TOKENS: frozenset[str] = frozenset(
    {
        # User data streams (private; require listenKey).
        "userdatastream",
        "userdata",
        "listenkey",
        # Trading WebSocket API (signed orders over WS).
        "ws-api",
        "trading-api",
        "ws/api",
        "ws-fapi",
        "ws-papi",
        # User-data event types delivered over the listenKey channel.
        # These never appear as public subscribe-stream names; we list
        # them here so a misconfigured caller cannot smuggle one
        # through.
        "accountupdate",
        "ordertradeupdate",
        "orderupdate",
        "margincall",
        "balanceupdate",
        "positionupdate",
        "leverageupdate",
        "accountconfigupdate",
    }
)

#: Forbidden substrings inside a query string. ``apiKey`` etc. are
#: refused even when a stream name happens to be allowlisted -
#: defence-in-depth above the URL parser.
FORBIDDEN_WS_QUERY_TOKENS: frozenset[str] = frozenset(
    {"signature", "timestamp", "recvwindow", "apikey", "listenkey"}
)

#: Hosts the public WebSocket client is permitted to talk to.
ALLOWED_PUBLIC_WS_HOSTS: frozenset[str] = frozenset(
    {
        "fstream.binance.com",
        "fstream.binancefuture.com",
    }
)

#: Default WebSocket base URL for Binance USDT-M perpetual futures
#: public-market streams.
DEFAULT_WS_BASE_URL: str = "wss://fstream.binance.com"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class PublicWSError(SafeModeViolation):
    """Base for Phase 11C.1B public-WS refusals.

    A :class:`SafeModeViolation` subclass so the existing Phase 11C
    runner code paths that already catch ``SafeModeViolation`` (env
    guard, allowlist refusal, rate-limit governor protection mode)
    catch the WebSocket refusals too without an additional ``except``.
    """


class PublicWSStreamForbidden(PublicWSError):
    """The caller asked for a stream that is not on the public allowlist
    (or that matches the private-stream denylist)."""


class PublicWSCredentialForbidden(PublicWSError):
    """The caller passed a credential-shaped parameter
    (``api_key`` / ``api_secret`` / ``listen_key`` / ``token`` /
    ``signature`` / ``passphrase``)."""


# ---------------------------------------------------------------------------
# Stream validation
# ---------------------------------------------------------------------------
def assert_public_ws_stream_allowed(stream: str) -> str:
    """Validate ``stream`` against the Phase 11C.1B public allowlist.

    Returns the canonical stream string on success. Raises
    :class:`PublicWSStreamForbidden` if:

      - the stream is empty;
      - the stream contains any of :data:`FORBIDDEN_WS_TOKENS`;
      - the stream is not exactly one of
        :data:`PUBLIC_WS_STREAM_ALLOWLIST` AND does not end in one of
        :data:`PUBLIC_WS_STREAM_PREFIX_ALLOWLIST`.

    The check is deliberately conservative: if a future Binance change
    adds a private stream that happens to share a public prefix, the
    next operator must update the denylist explicitly.
    """
    if not stream:
        raise PublicWSStreamForbidden(
            "BinancePublicWS: empty stream name; refusing"
        )
    text = str(stream).strip()
    if not text:
        raise PublicWSStreamForbidden(
            "BinancePublicWS: blank stream name; refusing"
        )
    lowered = text.lower()
    for needle in FORBIDDEN_WS_TOKENS:
        if needle in lowered:
            raise PublicWSStreamForbidden(
                f"BinancePublicWS: refused stream {stream!r}; the "
                f"substring {needle!r} is on the Phase 11C.1B private "
                "denylist (listenKey / user data / trading WS API / "
                "private margin / position / account / balance / order)."
            )
    if text in PUBLIC_WS_STREAM_ALLOWLIST:
        return text
    # Per-symbol streams are accepted only if they end in one of the
    # public suffixes. The allowlist intentionally does NOT include any
    # auth-required suffix.
    for suffix in PUBLIC_WS_STREAM_PREFIX_ALLOWLIST:
        if text.endswith(suffix):
            # ``btcusdt@bookTicker`` style. Reject any embedded ``/`` or
            # query parameter to keep the surface tight.
            if "/" in text or "?" in text or " " in text:
                raise PublicWSStreamForbidden(
                    f"BinancePublicWS: refused malformed per-symbol "
                    f"stream {stream!r}."
                )
            return text
    raise PublicWSStreamForbidden(
        f"BinancePublicWS: stream {stream!r} is not on the Phase 11C.1B "
        "public allowlist. Allowed: "
        f"{sorted(PUBLIC_WS_STREAM_ALLOWLIST)} or any per-symbol stream "
        f"ending in one of {sorted(PUBLIC_WS_STREAM_PREFIX_ALLOWLIST)}."
    )


def assert_public_ws_url_allowed(url: str) -> str:
    """Validate ``url`` against the Phase 11C.1B public-WS allowlist.

    Returns the URL on success. Raises :class:`PublicWSStreamForbidden`
    on any refusal. The check covers scheme (``wss`` only), host
    (Binance public WS hosts only), path (``/ws`` or ``/stream``),
    embedded private tokens (denylist), and forbidden query parameters
    (``signature`` / ``timestamp`` / ``recvWindow`` / ``apiKey`` /
    ``listenKey``).
    """
    if not url:
        raise PublicWSStreamForbidden(
            "BinancePublicWS: empty URL; refusing"
        )
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"wss"}:
        raise PublicWSStreamForbidden(
            f"BinancePublicWS: refused non-wss WebSocket URL {url!r}; "
            "Phase 11C.1B requires wss://."
        )
    host = (parsed.netloc or "").split(":", 1)[0].lower()
    if host not in ALLOWED_PUBLIC_WS_HOSTS:
        raise PublicWSStreamForbidden(
            f"BinancePublicWS: refused WS host {host!r}; "
            "Phase 11C.1B only allows Binance public WS hosts "
            f"({sorted(ALLOWED_PUBLIC_WS_HOSTS)})."
        )
    path = parsed.path or ""
    lowered = (path + "?" + (parsed.query or "")).lower()
    for needle in FORBIDDEN_WS_TOKENS:
        if needle in lowered:
            raise PublicWSStreamForbidden(
                f"BinancePublicWS: refused URL {url!r}; the substring "
                f"{needle!r} is on the Phase 11C.1B private denylist."
            )
    if parsed.query:
        for name, _ in urllib.parse.parse_qsl(
            parsed.query, keep_blank_values=True
        ):
            if name.lower() in FORBIDDEN_WS_QUERY_TOKENS:
                raise PublicWSStreamForbidden(
                    f"BinancePublicWS: refused URL {url!r}; signed-WS "
                    f"query parameter {name!r} is forbidden."
                )
    return url


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WSConfig:
    """Operator-facing configuration knobs for the public WS client.

    Defaults are conservative. The Phase 11C runner reads these from
    ``app.config.settings`` so a YAML / env override flows through
    automatically; tests construct the dataclass inline.
    """

    base_url: str = DEFAULT_WS_BASE_URL
    streams: tuple[str, ...] = (
        "!ticker@arr",
        "!miniTicker@arr",
        "!bookTicker",
        "!markPrice@arr",
        "!forceOrder@arr",
    )
    #: Maximum allowed gap between two messages before the manager
    #: emits ``PUBLIC_WS_STALE`` and downgrades data quality.
    staleness_threshold_ms: int = 3000
    #: Initial backoff (seconds) after a disconnect before attempting a
    #: reconnect. Doubles up to ``reconnect_backoff_max_seconds``.
    reconnect_backoff_initial_seconds: float = 1.0
    reconnect_backoff_max_seconds: float = 30.0
    #: Whether the client may attempt to reconnect on disconnect. The
    #: refusal transport ignores this.
    auto_reconnect: bool = True
    #: Hard ceiling on subscriptions; defends against accidental
    #: explosion when a future caller adds many per-symbol streams.
    max_subscriptions: int = 64

    def __post_init__(self) -> None:
        if self.staleness_threshold_ms <= 0:
            raise ValueError(
                "WSConfig.staleness_threshold_ms must be > 0"
            )
        if self.reconnect_backoff_initial_seconds <= 0:
            raise ValueError(
                "WSConfig.reconnect_backoff_initial_seconds must be > 0"
            )
        if self.reconnect_backoff_max_seconds <= 0:
            raise ValueError(
                "WSConfig.reconnect_backoff_max_seconds must be > 0"
            )
        if (
            self.reconnect_backoff_initial_seconds
            > self.reconnect_backoff_max_seconds
        ):
            raise ValueError(
                "WSConfig: reconnect_backoff_initial_seconds must be "
                "<= reconnect_backoff_max_seconds"
            )
        if self.max_subscriptions <= 0:
            raise ValueError(
                "WSConfig.max_subscriptions must be > 0"
            )
        for stream in self.streams:
            assert_public_ws_stream_allowed(stream)
        assert_public_ws_url_allowed(
            self.base_url + "/stream?streams=" + self.streams[0]
        )


# ---------------------------------------------------------------------------
# Message envelope
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WSMessage:
    """One decoded message from a public WebSocket stream.

    The ``stream`` field is always one of the entries from
    :data:`PUBLIC_WS_STREAM_ALLOWLIST` (or a per-symbol variant). The
    ``data`` payload is the raw decoded JSON body Binance pushed -
    callers are responsible for the schema-by-stream parsing because
    it is stream-specific (``!ticker@arr`` returns a list,
    ``!bookTicker`` returns a dict).

    ``received_at_ms`` is set by :class:`BinancePublicWSClient` on
    every message handed up; tests use it to drive the staleness
    detector.
    """

    stream: str
    data: Any
    received_at_ms: int = field(default_factory=now_ms)


# ---------------------------------------------------------------------------
# Transport abstraction
# ---------------------------------------------------------------------------
class WSMessagePump:
    """Abstract message pump.

    Concrete pumps deliver messages to the client. The Phase 11C.1B
    boundary forbids any third-party WebSocket library, so the only
    real-network pump permitted under PR-B is :class:`_RefusalTransport`
    (which refuses to open a socket); tests inject the deterministic
    :class:`InProcessWSPump`. A real stdlib WS adapter lives in a
    separate review and is NOT shipped here.
    """

    def connect(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def disconnect(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def subscribe(self, streams: Sequence[str]) -> None:  # pragma: no cover
        raise NotImplementedError

    def poll(
        self, *, timeout_seconds: float
    ) -> list[WSMessage]:  # pragma: no cover - abstract
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:  # pragma: no cover - abstract
        return False


class InProcessWSPump(WSMessagePump):
    """Deterministic in-process pump used by tests + ``--ws-disabled``.

    Hands out a static, caller-supplied message queue. Never opens a
    socket. The pump enforces the same allowlist as the live transport
    so a test cannot accidentally inject a private-stream message and
    have the rest of the pipeline accept it.
    """

    def __init__(
        self,
        *,
        messages: Iterable[WSMessage] | None = None,
    ) -> None:
        self._queue: list[WSMessage] = []
        self._connected: bool = False
        self._subscribed: tuple[str, ...] = ()
        if messages is not None:
            for msg in messages:
                self.push(msg)

    def push(self, message: WSMessage) -> None:
        """Queue a message for the next :meth:`poll` call.

        Refuses any message whose ``stream`` is not on the public
        allowlist. This mirrors the real transport's filter so tests
        cannot smuggle a private-stream sample into the rest of the
        pipeline.
        """
        assert_public_ws_stream_allowed(message.stream)
        self._queue.append(message)

    def push_many(self, messages: Iterable[WSMessage]) -> None:
        for msg in messages:
            self.push(msg)

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def subscribe(self, streams: Sequence[str]) -> None:
        for stream in streams:
            assert_public_ws_stream_allowed(stream)
        self._subscribed = tuple(streams)

    def poll(self, *, timeout_seconds: float) -> list[WSMessage]:
        del timeout_seconds  # the in-process pump never blocks
        if not self._connected:
            return []
        out = list(self._queue)
        self._queue.clear()
        return out

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def subscribed_streams(self) -> tuple[str, ...]:
        return self._subscribed


class _RefusalTransport(WSMessagePump):
    """Default transport used when no pump is supplied.

    Phase 11C.1B refuses to open any real socket; this class makes the
    refusal explicit instead of silently no-op'ing. The runner injects
    :class:`InProcessWSPump` for ``--dry-run`` / ``--ws-disabled``;
    production deployments wait for the follow-up PR that ships a
    stdlib WS adapter.
    """

    def connect(self) -> None:
        raise NotImplementedError(
            "BinancePublicWSClient: the default transport refuses to "
            "open a real WebSocket. Phase 11C.1B does NOT ship a "
            "third-party WS library; the runner uses the in-process "
            "pump for --dry-run and is expected to wire a stdlib WS "
            "adapter in the follow-up PR."
        )

    def disconnect(self) -> None:
        return None

    def subscribe(self, streams: Sequence[str]) -> None:
        for stream in streams:
            assert_public_ws_stream_allowed(stream)

    def poll(self, *, timeout_seconds: float) -> list[WSMessage]:
        del timeout_seconds
        return []

    @property
    def is_connected(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class BinancePublicWSClient:
    """Binance USDT-M perpetual futures public-market WebSocket client.

    The client is intentionally minimal: it owns the message pump, the
    subscription allowlist, the heartbeat / staleness detector, and
    emits the Phase 11C.1B WS lifecycle events. Decoding stream-specific
    payloads (ticker / mini-ticker / book-ticker / mark-price / force-
    order) is the radar's job, not the client's; this keeps the
    audit-able surface narrow.

    Phase 11C.1B contract:

      - construct refuses ``api_key`` / ``api_secret`` /
        ``listen_key`` / ``token`` etc. (every call pattern that
        smuggles a private credential is refused);
      - every :meth:`subscribe` is run through
        :func:`assert_public_ws_stream_allowed`;
      - every URL is run through :func:`assert_public_ws_url_allowed`;
      - the four ``ExchangeClientBase`` write surfaces remain refused
        on the host :class:`BinancePublicClient` (this client is NOT a
        subclass of the base; it composes alongside it);
      - the heartbeat / staleness detector emits
        ``PUBLIC_WS_CONNECTED`` / ``PUBLIC_WS_DISCONNECTED`` /
        ``PUBLIC_WS_STALE`` so the daily report and Reflection can
        rebuild the link timeline from events.db alone.
    """

    SOURCE_MODULE = "exchanges.binance_public_ws"

    def __init__(
        self,
        *,
        config: WSConfig | None = None,
        pump: WSMessagePump | None = None,
        event_repo: Any = None,
        clock_fn: Callable[[], int] = now_ms,
        sleep_fn: Callable[[float], None] = time.sleep,
        # The kw-only refusal guards mirror BinancePublicClient.
        api_key: str | None = None,
        api_secret: str | None = None,
        listen_key: str | None = None,
        **forbidden_credentials: Any,
    ) -> None:
        if (
            api_key is not None
            or api_secret is not None
            or listen_key is not None
        ):
            raise PublicWSCredentialForbidden(
                "BinancePublicWSClient must not be instantiated with "
                "api_key / api_secret / listen_key. Phase 11C.1B is "
                "public-market read-only; credentials and listenKey "
                "are forbidden."
            )
        for name in forbidden_credentials:
            lowered = name.lower()
            if any(
                needle in lowered
                for needle in (
                    "api_key",
                    "api_secret",
                    "apikey",
                    "secret",
                    "token",
                    "signature",
                    "passphrase",
                    "listen_key",
                    "listenkey",
                )
            ):
                raise PublicWSCredentialForbidden(
                    f"BinancePublicWSClient: refused credential-shaped "
                    f"keyword argument {name!r}."
                )
        if forbidden_credentials:
            raise TypeError(
                f"BinancePublicWSClient got unexpected keyword "
                f"argument(s): {sorted(forbidden_credentials)}"
            )

        self._config = config or WSConfig()
        # Re-validate the configured streams + base URL as
        # defence-in-depth: a future caller could mutate the dataclass
        # via ``__post_init__``-bypassing tricks (frozen=True helps but
        # doesn't make ``__class__`` swaps impossible).
        for stream in self._config.streams:
            assert_public_ws_stream_allowed(stream)
        assert_public_ws_url_allowed(
            self._config.base_url
            + "/stream?streams="
            + self._config.streams[0]
        )
        self._pump: WSMessagePump = pump or _RefusalTransport()
        self._event_repo = event_repo
        self._clock_fn = clock_fn
        self._sleep_fn = sleep_fn

        self._subscriptions: set[str] = set()
        self._is_connected: bool = False
        self._is_stale: bool = False
        self._last_message_ts_ms: int | None = None
        self._last_connect_ts_ms: int | None = None
        self._last_disconnect_ts_ms: int | None = None

        # JSON-safe counters for the daily report.
        self._messages_received: int = 0
        self._messages_received_by_stream: dict[str, int] = {}
        self._reconnect_count: int = 0
        self._stale_count: int = 0
        self._ws_staleness_ms_max: int = 0
        self._connect_count: int = 0
        self._disconnect_count: int = 0
        self._last_subscribe_ack: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Properties / introspection
    # ------------------------------------------------------------------
    @property
    def config(self) -> WSConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_stale(self) -> bool:
        return self._is_stale

    @property
    def subscriptions(self) -> frozenset[str]:
        return frozenset(self._subscriptions)

    @property
    def messages_received(self) -> int:
        return self._messages_received

    @property
    def messages_received_by_stream(self) -> Mapping[str, int]:
        return dict(self._messages_received_by_stream)

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def stale_count(self) -> int:
        return self._stale_count

    @property
    def ws_staleness_ms_max(self) -> int:
        return self._ws_staleness_ms_max

    @property
    def connect_count(self) -> int:
        return self._connect_count

    @property
    def disconnect_count(self) -> int:
        return self._disconnect_count

    @property
    def last_message_ts_ms(self) -> int | None:
        return self._last_message_ts_ms

    @property
    def staleness_ms_now(self) -> int:
        """Return ``now - last_message_ts_ms`` in ms (or 0 if never)."""
        if self._last_message_ts_ms is None:
            return 0
        return max(0, int(self._clock_fn()) - int(self._last_message_ts_ms))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open the pump and emit ``PUBLIC_WS_CONNECTED``."""
        try:
            self._pump.connect()
        except NotImplementedError:
            # Re-raise so the runner knows the default refusal is in
            # play; the runner downgrades to ws-disabled mode.
            raise
        self._is_connected = True
        self._is_stale = False
        self._connect_count += 1
        self._last_connect_ts_ms = int(self._clock_fn())
        # Re-subscribe to the configured stream set after every
        # (re)connect.
        if self._config.streams:
            self.subscribe(list(self._config.streams))
        self._emit(
            EventType.PUBLIC_WS_CONNECTED,
            payload={
                "base_url": self._config.base_url,
                "streams": sorted(self._subscriptions),
                "connect_count": self._connect_count,
                "reconnect_count": self._reconnect_count,
            },
        )
        logger.info(
            "[phase11c.1b] PUBLIC WS connected; streams={}",
            sorted(self._subscriptions),
        )

    def disconnect(self, *, reason: str = "manual") -> None:
        """Close the pump and emit ``PUBLIC_WS_DISCONNECTED``."""
        was_connected = self._is_connected
        try:
            self._pump.disconnect()
        except Exception as exc:  # pragma: no cover - protective
            logger.warning(
                "[phase11c.1b] pump disconnect raised: {}", exc
            )
        self._is_connected = False
        self._last_disconnect_ts_ms = int(self._clock_fn())
        if was_connected:
            self._disconnect_count += 1
        self._emit(
            EventType.PUBLIC_WS_DISCONNECTED,
            payload={
                "reason": reason,
                "disconnect_count": self._disconnect_count,
                "messages_received": self._messages_received,
            },
        )
        logger.warning(
            "[phase11c.1b] PUBLIC WS disconnected; reason={}", reason
        )

    def reconnect(self, *, reason: str = "auto") -> None:
        """Disconnect + reconnect with backoff. Increments
        ``reconnect_count`` exactly once."""
        if self._is_connected:
            self.disconnect(reason=reason)
        if not self._config.auto_reconnect:
            return
        backoff = float(self._config.reconnect_backoff_initial_seconds)
        cap = float(self._config.reconnect_backoff_max_seconds)
        # Phase 11C.1B keeps the reconnect path single-shot; the runner
        # owns the larger retry loop. We sleep once at most.
        try:
            self._sleep_fn(min(backoff, cap))
        except Exception:  # pragma: no cover - sleep can be a no-op
            pass
        self._reconnect_count += 1
        try:
            self.connect()
        except NotImplementedError:
            # The default refusal transport will land here on every
            # reconnect attempt; we re-raise so the runner can degrade
            # gracefully (see ``--ws-disabled``).
            raise

    # ------------------------------------------------------------------
    # Subscription handling
    # ------------------------------------------------------------------
    def subscribe(self, streams: Sequence[str]) -> None:
        """Subscribe to a list of streams.

        Every stream is run through
        :func:`assert_public_ws_stream_allowed` BEFORE it reaches the
        pump.
        """
        canonical: list[str] = []
        for stream in streams:
            canonical.append(assert_public_ws_stream_allowed(stream))
        if (
            len(self._subscriptions) + len(canonical)
            > self._config.max_subscriptions
        ):
            raise PublicWSStreamForbidden(
                "BinancePublicWSClient: refused subscribe; would "
                "exceed max_subscriptions="
                f"{self._config.max_subscriptions}."
            )
        self._pump.subscribe(canonical)
        self._subscriptions.update(canonical)
        self._last_subscribe_ack = tuple(canonical)

    def unsubscribe(self, streams: Sequence[str]) -> None:
        for stream in streams:
            self._subscriptions.discard(stream)

    # ------------------------------------------------------------------
    # Message pumping
    # ------------------------------------------------------------------
    def pump_messages(
        self,
        *,
        timeout_seconds: float = 0.0,
    ) -> list[WSMessage]:
        """Pull messages from the pump and update the heartbeat.

        Returns the (possibly empty) list of fresh :class:`WSMessage`
        envelopes. The runner calls this on every loop tick. The
        method ALSO drives the staleness detector + the auto-reconnect
        if the pump dropped underneath us.
        """
        # Detect a pump-side disconnect that the caller did not see.
        if self._is_connected and not self._pump.is_connected:
            self.disconnect(reason="pump_dropped")
        if not self._is_connected:
            self._update_staleness()
            return []
        try:
            messages = self._pump.poll(timeout_seconds=timeout_seconds)
        except Exception as exc:
            logger.warning(
                "[phase11c.1b] pump.poll raised: {}", exc
            )
            self.disconnect(reason=f"pump_error:{type(exc).__name__}")
            return []
        if not messages:
            self._update_staleness()
            return []
        out: list[WSMessage] = []
        latest_ts: int | None = None
        for msg in messages:
            stream = assert_public_ws_stream_allowed(msg.stream)
            envelope = msg if msg.received_at_ms else WSMessage(
                stream=stream,
                data=msg.data,
                received_at_ms=int(self._clock_fn()),
            )
            self._messages_received += 1
            self._messages_received_by_stream[stream] = (
                self._messages_received_by_stream.get(stream, 0) + 1
            )
            latest_ts = max(latest_ts or 0, int(envelope.received_at_ms))
            out.append(envelope)
        if latest_ts is not None:
            self._last_message_ts_ms = latest_ts
            if self._is_stale:
                # Recovered from staleness. The runner's MARKET_SNAPSHOT
                # / RADAR pipeline will re-engage; we do NOT emit a
                # dedicated "stale_recovered" event because Phase 11C
                # already has DATA_UNRELIABLE for that.
                self._is_stale = False
        return out

    def _update_staleness(self) -> None:
        if self._last_message_ts_ms is None:
            # Never saw a message; staleness is undefined.
            return
        gap = int(self._clock_fn()) - int(self._last_message_ts_ms)
        if gap > self._ws_staleness_ms_max:
            self._ws_staleness_ms_max = gap
        if gap >= int(self._config.staleness_threshold_ms) and not self._is_stale:
            self._is_stale = True
            self._stale_count += 1
            self._emit(
                EventType.PUBLIC_WS_STALE,
                payload={
                    "staleness_ms": int(gap),
                    "threshold_ms": int(self._config.staleness_threshold_ms),
                    "last_message_ts_ms": int(self._last_message_ts_ms),
                    "stale_count": self._stale_count,
                    "messages_received": self._messages_received,
                },
            )
            logger.warning(
                "[phase11c.1b] PUBLIC WS stale; gap={}ms threshold={}ms",
                gap,
                self._config.staleness_threshold_ms,
            )

    # ------------------------------------------------------------------
    # Daily-report payload
    # ------------------------------------------------------------------
    def metrics_payload(self) -> dict[str, Any]:
        """Return the JSON-safe metrics block.

        Field names match the Phase 11C.1B daily-report spec verbatim.
        """
        return {
            "ws_messages_received": int(self._messages_received),
            "ws_messages_received_by_stream": dict(
                self._messages_received_by_stream
            ),
            "ws_reconnect_count": int(self._reconnect_count),
            "ws_staleness_ms_max": int(self._ws_staleness_ms_max),
            "ws_stale_count": int(self._stale_count),
            "ws_connect_count": int(self._connect_count),
            "ws_disconnect_count": int(self._disconnect_count),
            "ws_is_connected": bool(self._is_connected),
            "ws_is_stale": bool(self._is_stale),
            "ws_last_message_ts_ms": (
                int(self._last_message_ts_ms)
                if self._last_message_ts_ms is not None
                else None
            ),
            "ws_streams_subscribed": sorted(self._subscriptions),
        }

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------
    def _emit(
        self,
        event_type: EventType,
        *,
        payload: dict[str, Any],
    ) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=self.SOURCE_MODULE,
                    symbol=None,
                    timestamp=int(self._clock_fn()),
                    payload=dict(payload),
                )
            )
        except Exception as exc:  # pragma: no cover - protective
            logger.error(
                "[phase11c.1b] failed to emit {}: {}",
                event_type.value,
                exc,
            )


__all__ = [
    "ALLOWED_PUBLIC_WS_HOSTS",
    "BinancePublicWSClient",
    "DEFAULT_WS_BASE_URL",
    "FORBIDDEN_WS_QUERY_TOKENS",
    "FORBIDDEN_WS_TOKENS",
    "InProcessWSPump",
    "PUBLIC_WS_STREAM_ALLOWLIST",
    "PUBLIC_WS_STREAM_PREFIX_ALLOWLIST",
    "PublicWSCredentialForbidden",
    "PublicWSError",
    "PublicWSStreamForbidden",
    "WSConfig",
    "WSMessage",
    "WSMessagePump",
    "assert_public_ws_stream_allowed",
    "assert_public_ws_url_allowed",
]
