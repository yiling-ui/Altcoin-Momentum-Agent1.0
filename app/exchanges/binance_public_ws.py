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

  - ``!ticker@arr``        - 24h rolling stats for every symbol  (MARKET route)
  - ``!miniTicker@arr``    - light-weight last/volume push       (MARKET route)
  - ``!bookTicker``        - per-symbol best bid/ask updates     (PUBLIC route)
  - ``!markPrice@arr``     - mark price + funding rate per symbol(MARKET route)
  - ``!forceOrder@arr``    - liquidation events                  (MARKET route)

Routed public / market endpoints
--------------------------------

The Binance USDⓈ-M Futures public WebSocket reference exposes three
routed endpoints:

  - ``wss://fstream.binance.com/public``  - Public surface (best bid /
    ask, public depth).
  - ``wss://fstream.binance.com/market``  - Market data surface
    (``!ticker@arr``, ``!miniTicker@arr``, ``!markPrice@arr``,
    ``!forceOrder@arr``).
  - ``wss://fstream.binance.com/private`` - PRIVATE: signed user
    data only. **Forbidden in Phase 11C.1B.**

A connection that does NOT include ``/public`` / ``/market`` /
``/private`` in the path is "unrouted" and will only surface a
subset of public-only data; market-class streams such as
``!markPrice@arr`` are silently NOT pushed. Phase 11C.1B therefore
treats the routed roots as the acceptance path and routes each
allowlisted stream to its appropriate transport via
:func:`classify_stream_route`. The legacy unrouted ``/ws`` /
``/stream`` paths remain accepted by the URL parser for back-compat
with the existing in-process tests, but the runner only opens
routed transports in the production WS-first path.

The :class:`MultiTransportPublicWSManager` below owns one
:class:`StdlibPublicWSTransport` per route and merges their message
streams behind a single :class:`WSMessagePump` interface so
:class:`BinancePublicWSClient` can pump the union without any
awareness of the underlying topology.

Phase 11C.1B boundary
---------------------

This module enforces, at construction time and on every subscribe:

  * NO Binance API key
  * NO Binance API secret
  * NO ``signature`` / ``timestamp`` / ``recvWindow`` / ``apiKey`` query
  * NO ``listenKey`` / user data stream
  * NO private WebSocket / trading WebSocket API
  * NO ``/private`` routed endpoint
  * NO ``ws-api`` / ``trading-api`` / ``ws-fapi`` / ``ws-papi`` path
  * NO ``ws/<listenKey>`` / ``userDataStream`` URL
  * NO third-party HTTP / WebSocket / SDK import (stdlib + loguru only)
  * NO write surface (the four ``ExchangeClientBase`` refusals are
    inherited unchanged through the host :class:`BinancePublicClient`)

The default transport for the in-process / dry-run path is
:class:`_RefusalTransport`, which raises :class:`NotImplementedError`
on every attempt to actually open a socket. The real-network
transport is :class:`StdlibPublicWSTransport`; the runner combines
two of those (one PUBLIC, one MARKET) inside
:class:`MultiTransportPublicWSManager` for the WS-first acceptance
path. The no-network audit pinning a stdlib-only transport
(``tests.unit.test_phase11c_no_network``) holds throughout.

Threading
---------

The client is single-threaded by construction. A future async / multi-
threaded runner MUST wrap :meth:`pump_messages` and the heartbeat
helpers with its own mutex. Phase 11C.1B's runner is the same
single-threaded polling loop PR-A introduced.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import socket
import ssl
import struct
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

#: Allowed top-level path roots for the Phase 11C.1B routed public
#: WebSocket client. The Binance USDⓈ-M Futures public WebSocket
#: reference exposes routed endpoints:
#:
#:   - ``wss://fstream.binance.com/public/ws/<stream>`` (single)
#:   - ``wss://fstream.binance.com/public/stream?streams=<a>/<b>``
#:     (combined PUBLIC route - bookTicker / public depth)
#:   - ``wss://fstream.binance.com/market/ws/<stream>`` (single)
#:   - ``wss://fstream.binance.com/market/stream?streams=<a>/<b>``
#:     (combined MARKET route - !ticker@arr / !miniTicker@arr /
#:     !markPrice@arr / !forceOrder@arr)
#:   - ``wss://fstream.binance.com/private/...`` - PRIVATE / signed
#:     user-data only. **Forbidden** in Phase 11C.1B.
#:
#: A connection that omits the ``/public`` / ``/market`` / ``/private``
#: route prefix is "unrouted" and Binance will only surface a subset
#: of public-only data; market-class streams (``!markPrice@arr`` etc.)
#: are silently NOT pushed. The Phase 11C.1B acceptance path therefore
#: routes each allowlisted stream through its proper routed
#: transport. The legacy unrouted roots ``/ws`` / ``/stream`` are
#: accepted by the URL parser for back-compat (the in-process pump
#: still works against them) but the production runner only opens
#: routed transports.
ALLOWED_PUBLIC_WS_PATH_ROOTS: frozenset[str] = frozenset(
    {
        "public/ws",
        "public/stream",
        "market/ws",
        "market/stream",
    }
)

#: Legacy unrouted path roots. Accepted by :func:`assert_public_ws_path_allowed`
#: for back-compat (test fixtures, dry-run InProcess pump configs);
#: NOT the Phase 11C.1B WS-first acceptance path.
LEGACY_UNROUTED_WS_PATH_ROOTS: frozenset[str] = frozenset({"ws", "stream"})

#: Hard-forbidden path roots. The ``private`` route is the
#: documented user-data / signed surface and is NEVER accepted in
#: Phase 11C.1B even if a future caller composes the URL by hand.
#: ``ws-api`` / ``ws-fapi`` / ``ws-papi`` / ``trading-api`` /
#: ``userDataStream`` are also blocked at the path-root level
#: in addition to the substring deny-list.
FORBIDDEN_WS_PATH_ROOTS: frozenset[str] = frozenset(
    {
        "private",
        "ws-api",
        "ws-fapi",
        "ws-papi",
        "trading-api",
        "userdatastream",
    }
)

#: Per-stream route classification. Mirrors the Binance USDⓈ-M
#: Futures public WebSocket reference. ``!bookTicker`` is a PUBLIC
#: surface (best bid / ask is exposed under ``/public``); the other
#: four allowlisted array streams are MARKET surfaces (mark-price,
#: funding, ticker statistics, liquidations are exposed under
#: ``/market``).
STREAM_ROUTE_PUBLIC: frozenset[str] = frozenset(
    {
        "!bookTicker",
    }
)
STREAM_ROUTE_MARKET: frozenset[str] = frozenset(
    {
        "!ticker@arr",
        "!miniTicker@arr",
        "!markPrice@arr",
        "!forceOrder@arr",
    }
)
#: Per-symbol suffix -> route classification.
STREAM_SUFFIX_ROUTE_PUBLIC: frozenset[str] = frozenset({"@bookTicker"})
STREAM_SUFFIX_ROUTE_MARKET: frozenset[str] = frozenset(
    {
        "@ticker",
        "@miniTicker",
        "@markPrice",
        "@forceOrder",
        "@forceOrder@1s",
    }
)

#: Default WebSocket base URL for Binance USDT-M perpetual futures
#: public-market streams.
DEFAULT_WS_BASE_URL: str = "wss://fstream.binance.com"

#: RFC 6455 magic GUID. Used to build the ``Sec-WebSocket-Accept``
#: header from the ``Sec-WebSocket-Key`` we send during the upgrade
#: handshake. This is a fixed protocol constant, NOT a credential.
_WS_RFC6455_GUID: str = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


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
    (Binance public WS hosts only), path (routed
    ``/public/ws`` / ``/public/stream`` / ``/market/ws`` /
    ``/market/stream`` or legacy ``/ws`` / ``/stream``; ``/private``
    and friends refused via :func:`assert_public_ws_path_allowed`),
    embedded private tokens (denylist), and forbidden query
    parameters (``signature`` / ``timestamp`` / ``recvWindow`` /
    ``apiKey`` / ``listenKey``).
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
    # Defence-in-depth: refuse the routed-private path even if a
    # later substring search would also catch it. The path-root
    # allowlist is authoritative for the WS-first acceptance path.
    if path:
        assert_public_ws_path_allowed(path)
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


def assert_public_ws_path_allowed(path: str) -> str:
    """Phase 11C.1B path-root allowlist.

    Stricter than :func:`assert_public_ws_url_allowed`: the path must
    begin with one of the routed acceptance roots
    (``/public/ws`` / ``/public/stream`` / ``/market/ws`` /
    ``/market/stream``) OR one of the legacy unrouted back-compat
    roots (``/ws`` / ``/stream``). The ``/private`` routed root is
    EXPLICITLY refused at the path level so a future caller cannot
    smuggle a user-data / signed connection past the URL parser by
    hand-composing the URL. ``/ws-api`` / ``/ws-fapi`` / ``/ws-papi`` /
    ``/trading-api`` / ``/userDataStream`` are likewise refused.

    The Binance USDⓈ-M Futures public WebSocket reference exposes
    exactly the routed roots above for public-market data; the
    routed acceptance roots are the production WS-first path. The
    legacy unrouted ``/ws`` / ``/stream`` are kept as accepted only
    so the in-process pump and existing fixtures still validate; the
    runner does NOT open a real network connection against them.
    """
    if not path:
        raise PublicWSStreamForbidden(
            "BinancePublicWS: refused empty WS path"
        )
    # Strip a query / fragment if the caller passed a path-with-query
    # (e.g. ``/public/stream?streams=!bookTicker``). The path-root
    # allowlist only cares about the path component.
    path_only = path.split("?", 1)[0].split("#", 1)[0]
    cleaned = path_only.lstrip("/")
    if not cleaned:
        raise PublicWSStreamForbidden(
            f"BinancePublicWS: refused WS path {path!r}; empty root"
        )
    parts = cleaned.split("/")
    head = parts[0].lower() if parts else ""
    second = parts[1].lower() if len(parts) >= 2 else ""
    # 1. Routed-private and other forbidden top-level roots are
    #    refused before anything else, even when a later layer of
    #    the path name-collides with a legitimate public stream.
    if head in FORBIDDEN_WS_PATH_ROOTS:
        raise PublicWSStreamForbidden(
            f"BinancePublicWS: refused WS path {path!r}; the path "
            f"root {head!r} is on the Phase 11C.1B private / signed "
            "deny-list (private / ws-api / ws-fapi / ws-papi / "
            "trading-api / userDataStream)."
        )
    # 2. Routed acceptance roots: ``/<route>/<surface>`` where
    #    ``<route>`` is ``public`` / ``market`` and ``<surface>`` is
    #    ``ws`` / ``stream``. The combined value
    #    ``f"{head}/{second}"`` is matched against
    #    :data:`ALLOWED_PUBLIC_WS_PATH_ROOTS`.
    if head in {"public", "market"}:
        combined = f"{head}/{second}"
        if combined not in ALLOWED_PUBLIC_WS_PATH_ROOTS:
            raise PublicWSStreamForbidden(
                f"BinancePublicWS: refused WS path {path!r}; "
                f"routed surface {second!r} is not on the routed "
                "acceptance allowlist (only "
                f"{sorted(ALLOWED_PUBLIC_WS_PATH_ROOTS)})."
            )
        return path
    # 3. Legacy unrouted back-compat roots.
    if head in LEGACY_UNROUTED_WS_PATH_ROOTS:
        return path
    raise PublicWSStreamForbidden(
        f"BinancePublicWS: refused WS path {path!r}; only routed "
        f"{sorted(ALLOWED_PUBLIC_WS_PATH_ROOTS)} or legacy "
        f"{sorted(LEGACY_UNROUTED_WS_PATH_ROOTS)} are allowed roots."
    )


def classify_stream_route(stream: str) -> str:
    """Classify ``stream`` as ``"public"`` or ``"market"``.

    Mirrors the Binance USDⓈ-M Futures public WebSocket reference:

      - ``!bookTicker`` (and per-symbol ``btcusdt@bookTicker``) is a
        PUBLIC surface (best bid / ask).
      - ``!ticker@arr`` / ``!miniTicker@arr`` / ``!markPrice@arr`` /
        ``!forceOrder@arr`` (and per-symbol equivalents) are MARKET
        surfaces.

    Raises :class:`PublicWSStreamForbidden` if ``stream`` is not on
    the public allowlist; this also covers the deny-list (which
    :func:`assert_public_ws_stream_allowed` enforces first).
    """
    canonical = assert_public_ws_stream_allowed(stream)
    if canonical in STREAM_ROUTE_PUBLIC:
        return "public"
    if canonical in STREAM_ROUTE_MARKET:
        return "market"
    for suffix in STREAM_SUFFIX_ROUTE_PUBLIC:
        if canonical.endswith(suffix):
            return "public"
    for suffix in STREAM_SUFFIX_ROUTE_MARKET:
        if canonical.endswith(suffix):
            return "market"
    raise PublicWSStreamForbidden(
        f"BinancePublicWS: stream {stream!r} cannot be classified "
        "as PUBLIC or MARKET; refusing."
    )


def split_streams_by_route(
    streams: Iterable[str],
) -> dict[str, list[str]]:
    """Split ``streams`` into ``{"public": [...], "market": [...]}``.

    Raises :class:`PublicWSStreamForbidden` if any stream is not on
    the public allowlist or cannot be classified.
    """
    out: dict[str, list[str]] = {"public": [], "market": []}
    for stream in streams:
        route = classify_stream_route(stream)
        out[route].append(assert_public_ws_stream_allowed(stream))
    return out


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

    The :class:`BinancePublicWSClient` constructor falls back to this
    transport when the caller supplies neither a real network adapter
    (:class:`StdlibPublicWSTransport` /
    :class:`MultiTransportPublicWSManager`) nor an in-process pump
    (:class:`InProcessWSPump`). The refusal is explicit instead of a
    silent no-op so an accidentally-default-constructed client cannot
    masquerade as "connected" when no socket has actually been opened.

    The runner injects :class:`InProcessWSPump` for ``--dry-run`` /
    ``--ws-disabled`` and the real :class:`MultiTransportPublicWSManager`
    (which owns the routed PUBLIC + MARKET
    :class:`StdlibPublicWSTransport` adapters) for ``--ws-first``
    without ``--dry-run``.
    """

    def connect(self) -> None:
        raise NotImplementedError(
            "BinancePublicWSClient: the default transport refuses to "
            "open a real WebSocket. Pass an explicit pump: "
            "InProcessWSPump for dry-run / fixtures, "
            "MultiTransportPublicWSManager (routed public + market "
            "StdlibPublicWSTransport) for the WS-first acceptance path."
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


# ---------------------------------------------------------------------------
# Real-network transport (stdlib-only RFC 6455 client)
# ---------------------------------------------------------------------------
#
# Phase 11C.1B promotes the runner from "scaffold + dry-run pump" to
# "real all-market WS-first radar". The real-network adapter below is
# implemented entirely on top of the Python standard library
# (``socket`` + ``ssl`` + ``select`` + ``struct`` + ``base64`` +
# ``hashlib`` + ``json`` + ``os.urandom``). NO third-party WebSocket
# library is imported; the Phase 11C source-tree audit
# (:mod:`tests.unit.test_phase11c_no_network`) keeps the
# ``websockets`` / ``websocket-client`` / ``aiohttp`` / ``requests``
# packages on the deny-list and this module continues to satisfy that
# audit.
#
# The transport's responsibilities:
#
#   * connect to ``wss://fstream.binance.com`` (or
#     ``wss://fstream.binancefuture.com`` for the testnet) ONLY;
#   * speak only the public path roots ``/ws`` and ``/stream``;
#   * subscribe ONLY to streams on
#     :data:`PUBLIC_WS_STREAM_ALLOWLIST`;
#   * refuse every credential-shaped kwarg (``api_key`` /
#     ``api_secret`` / ``listen_key`` / ``token`` / ``signature`` /
#     ``passphrase``) at construction time;
#   * never read ``BINANCE_API_KEY`` / ``BINANCE_API_SECRET`` (the
#     adapter does not import ``os.environ`` and the source-tree audit
#     blocks any ``os.environ.get`` / ``os.getenv`` call in this
#     file);
#   * never connect to a private host, ``/ws-api`` /
#     ``/userDataStream`` / ``/listenKey/...`` path, or send a
#     signed-WS query parameter (``signature`` / ``timestamp`` /
#     ``recvWindow`` / ``apiKey`` / ``listenKey``);
#   * never send a frame with the ``ws-api`` / ``trading-api`` /
#     account / order / position / balance / margin / leverage shapes.
#
# The adapter is single-threaded; the host
# :class:`BinancePublicWSClient` already documents that constraint
# and the runner already calls into one client from one thread.
# ---------------------------------------------------------------------------


class PublicWSTransportError(PublicWSError):
    """The transport could not connect / handshake / read a frame."""


class StdlibPublicWSTransport(WSMessagePump):
    """Phase 11C.1B real-network public-market WebSocket adapter.

    The class implements the RFC 6455 client handshake + frame
    layer using only the Python standard library. It is the default
    transport the runner injects into :class:`BinancePublicWSClient`
    when ``--ws-first`` is set without ``--dry-run``.

    Construction-time refusals (Phase 11C.1B boundary):

      - any non-``None`` ``api_key`` / ``api_secret`` /
        ``listen_key`` argument raises
        :class:`PublicWSCredentialForbidden`;
      - any extra kwarg whose name matches the credential pattern
        (``api_key`` / ``api_secret`` / ``apikey`` / ``secret`` /
        ``token`` / ``signature`` / ``passphrase`` / ``listen_key`` /
        ``listenkey``) raises :class:`PublicWSCredentialForbidden`;
      - the configured ``base_url`` MUST resolve to one of
        :data:`ALLOWED_PUBLIC_WS_HOSTS`;
      - the resulting subscribe URL MUST pass
        :func:`assert_public_ws_url_allowed` AND
        :func:`assert_public_ws_path_allowed`;
      - every entry in ``config.streams`` MUST pass
        :func:`assert_public_ws_stream_allowed`.

    The adapter is intentionally minimal: it can subscribe to the
    five public array streams (``!ticker@arr`` / ``!miniTicker@arr``
    / ``!bookTicker`` / ``!markPrice@arr`` / ``!forceOrder@arr``)
    and per-symbol public variants. It does NOT implement
    fragmentation, compression, or any signed-WS feature.
    """

    OPCODE_CONTINUATION = 0x0
    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    DEFAULT_CONNECT_TIMEOUT_SECONDS: float = 10.0
    DEFAULT_RECV_CHUNK_SIZE: int = 65_536
    MAX_HANDSHAKE_BYTES: int = 65_536

    def __init__(
        self,
        *,
        config: WSConfig | None = None,
        route: str | None = None,
        connect_timeout_seconds: float | None = None,
        recv_chunk_size: int | None = None,
        ssl_context: ssl.SSLContext | None = None,
        socket_factory: Callable[..., socket.socket] | None = None,
        ssl_wrap_fn: Callable[[socket.socket, str], socket.socket]
        | None = None,
        random_bytes_fn: Callable[[int], bytes] = os.urandom,
        # Refusal sentinels - same pattern as BinancePublicWSClient.
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
                "StdlibPublicWSTransport must not be instantiated with "
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
                    f"StdlibPublicWSTransport: refused credential-shaped "
                    f"keyword argument {name!r}."
                )
        if forbidden_credentials:
            raise TypeError(
                "StdlibPublicWSTransport got unexpected keyword "
                f"argument(s): {sorted(forbidden_credentials)}"
            )

        # Resolve and validate the route. ``None`` keeps the legacy
        # unrouted behaviour (``/stream?streams=...``); the routed
        # values ``"public"`` and ``"market"`` produce
        # ``/public/stream?streams=...`` and
        # ``/market/stream?streams=...`` respectively. The
        # routed-private surface (``/private``) is never reachable
        # from this transport: it is on
        # :data:`FORBIDDEN_WS_PATH_ROOTS` and the path-root
        # allowlist refuses it before connect even gets a chance.
        if route is not None:
            normalised_route = str(route).strip().lower()
            if normalised_route not in {"public", "market"}:
                raise PublicWSStreamForbidden(
                    f"StdlibPublicWSTransport: refused route "
                    f"{route!r}; only 'public' / 'market' are allowed "
                    "(the 'private' route is reserved for signed "
                    "user-data and is forbidden in Phase 11C.1B)."
                )
            self._route: str | None = normalised_route
        else:
            self._route = None

        self._config = config or WSConfig()
        # Validate every stream against the allowlist.
        for stream in self._config.streams:
            assert_public_ws_stream_allowed(stream)
        # Build + validate the subscribe URL. The combined endpoint
        # ``/<route>/stream?streams=<a>/<b>`` (or the legacy
        # ``/stream?streams=...`` when ``route is None``) lets us
        # subscribe to every allowlisted stream over a single
        # connection per route.
        self._url = self._build_subscribe_url(self._config, self._route)
        assert_public_ws_url_allowed(self._url)
        parsed = urllib.parse.urlsplit(self._url)
        host = (parsed.netloc or "").split(":", 1)[0].lower()
        if host not in ALLOWED_PUBLIC_WS_HOSTS:
            raise PublicWSStreamForbidden(
                f"StdlibPublicWSTransport: refused host {host!r}; "
                "Phase 11C.1B only allows Binance public WS hosts "
                f"({sorted(ALLOWED_PUBLIC_WS_HOSTS)})."
            )
        assert_public_ws_path_allowed(parsed.path or "")
        self._host = host
        self._port = int(parsed.port or 443)
        self._path = parsed.path or "/stream"
        if parsed.query:
            self._path = f"{self._path}?{parsed.query}"

        self._connect_timeout_seconds = float(
            connect_timeout_seconds
            if connect_timeout_seconds is not None
            else self.DEFAULT_CONNECT_TIMEOUT_SECONDS
        )
        self._recv_chunk_size = int(
            recv_chunk_size
            if recv_chunk_size is not None
            else self.DEFAULT_RECV_CHUNK_SIZE
        )
        self._ssl_context = ssl_context
        self._socket_factory = socket_factory or socket.socket
        self._ssl_wrap_fn = ssl_wrap_fn
        self._random_bytes_fn = random_bytes_fn

        self._sock: socket.socket | None = None
        self._connected: bool = False
        self._closed: bool = False
        self._recv_buffer: bytearray = bytearray()
        self._subscribed_streams: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # URL construction
    # ------------------------------------------------------------------
    @staticmethod
    def _build_subscribe_url(
        config: WSConfig, route: str | None = None
    ) -> str:
        """Build the canonical combined-subscribe URL.

        Returns
        ``<base_url>/<route>/stream?streams=<a>/<b>/...`` when
        ``route`` is ``"public"`` or ``"market"``, and
        ``<base_url>/stream?streams=<a>/<b>/...`` (legacy unrouted)
        when ``route`` is ``None``. Every ``<>`` entry MUST be on
        the public stream allowlist; the combined endpoint is
        preferred over per-stream ``/ws/<x>`` because it keeps the
        connection count to one per route.
        """
        streams = list(config.streams)
        if not streams:
            raise PublicWSStreamForbidden(
                "StdlibPublicWSTransport: refused empty stream set"
            )
        for stream in streams:
            assert_public_ws_stream_allowed(stream)
        joined = "/".join(streams)
        if route in {"public", "market"}:
            return f"{config.base_url}/{route}/stream?streams={joined}"
        return f"{config.base_url}/stream?streams={joined}"

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open a real TCP+TLS+WebSocket connection.

        Raises :class:`PublicWSTransportError` (a
        :class:`SafeModeViolation` subclass) on every failure mode:
        DNS error, refused connection, TLS handshake error, malformed
        upgrade response, missing / wrong ``Sec-WebSocket-Accept``.
        """
        if self._connected:
            return
        if self._closed:
            # Allow re-connect after a close.
            self._closed = False
        sock: socket.socket | None = None
        try:
            sock = self._socket_factory(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self._connect_timeout_seconds)
            try:
                sock.connect((self._host, self._port))
            except OSError as exc:
                raise PublicWSTransportError(
                    f"StdlibPublicWSTransport: TCP connect to "
                    f"{self._host}:{self._port} failed: {exc}"
                ) from exc

            if self._ssl_wrap_fn is not None:
                wrapped = self._ssl_wrap_fn(sock, self._host)
            else:
                ctx = self._ssl_context or ssl.create_default_context()
                try:
                    wrapped = ctx.wrap_socket(
                        sock, server_hostname=self._host
                    )
                except ssl.SSLError as exc:
                    raise PublicWSTransportError(
                        f"StdlibPublicWSTransport: TLS handshake to "
                        f"{self._host}:{self._port} failed: {exc}"
                    ) from exc

            # Build + send the WebSocket upgrade request.
            random_key_bytes = self._random_bytes_fn(16)
            sec_ws_key = base64.b64encode(random_key_bytes).decode(
                "ascii"
            )
            request = (
                f"GET {self._path} HTTP/1.1\r\n"
                f"Host: {self._host}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {sec_ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "User-Agent: ama-rt-phase11c1b/1.0 (+stdlib)\r\n"
                "\r\n"
            )
            wrapped.settimeout(self._connect_timeout_seconds)
            try:
                wrapped.sendall(request.encode("ascii"))
            except OSError as exc:
                raise PublicWSTransportError(
                    f"StdlibPublicWSTransport: send upgrade failed: {exc}"
                ) from exc

            response = bytearray()
            while b"\r\n\r\n" not in response:
                try:
                    chunk = wrapped.recv(4096)
                except OSError as exc:
                    raise PublicWSTransportError(
                        "StdlibPublicWSTransport: read upgrade response "
                        f"failed: {exc}"
                    ) from exc
                if not chunk:
                    raise PublicWSTransportError(
                        "StdlibPublicWSTransport: upgrade response "
                        "truncated; server closed before \\r\\n\\r\\n"
                    )
                response.extend(chunk)
                if len(response) > self.MAX_HANDSHAKE_BYTES:
                    raise PublicWSTransportError(
                        "StdlibPublicWSTransport: upgrade response too "
                        f"large (>{self.MAX_HANDSHAKE_BYTES} bytes)"
                    )

            header_end = response.index(b"\r\n\r\n")
            head = bytes(response[:header_end]).decode(
                "latin-1", errors="replace"
            )
            lines = head.split("\r\n")
            status_line = lines[0] if lines else ""
            # "HTTP/1.1 101 Switching Protocols"
            status_parts = status_line.split(" ", 2)
            if (
                len(status_parts) < 2
                or not status_parts[1].strip() == "101"
            ):
                raise PublicWSTransportError(
                    "StdlibPublicWSTransport: unexpected upgrade "
                    f"response status {status_line!r}"
                )
            accept_header: str | None = None
            for line in lines[1:]:
                if ":" in line:
                    name, value = line.split(":", 1)
                    if name.strip().lower() == "sec-websocket-accept":
                        accept_header = value.strip()
                        break
            expected_accept = base64.b64encode(
                hashlib.sha1(
                    (sec_ws_key + _WS_RFC6455_GUID).encode("ascii")
                ).digest()
            ).decode("ascii")
            if accept_header != expected_accept:
                raise PublicWSTransportError(
                    "StdlibPublicWSTransport: Sec-WebSocket-Accept "
                    f"mismatch (got {accept_header!r}, expected "
                    f"{expected_accept!r})"
                )

            # Save any bytes after the handshake into the recv buffer.
            self._recv_buffer = bytearray(response[header_end + 4 :])
            wrapped.setblocking(False)
            self._sock = wrapped
            self._connected = True
            self._closed = False
            self._subscribed_streams = tuple(self._config.streams)
            sock = None  # ownership transferred
            logger.info(
                "[phase11c.1b] StdlibPublicWSTransport connected "
                "host={} path={} streams={}",
                self._host,
                self._path.split("?", 1)[0],
                len(self._config.streams),
            )
        finally:
            if sock is not None and not self._connected:
                try:
                    sock.close()
                except Exception:  # pragma: no cover - protective
                    pass

    def disconnect(self) -> None:
        """Send a CLOSE frame and tear the socket down."""
        sock = self._sock
        self._sock = None
        self._connected = False
        self._closed = True
        if sock is not None:
            try:
                self._send_frame(self.OPCODE_CLOSE, b"\x03\xe8", sock=sock)
            except Exception:  # pragma: no cover - protective
                pass
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:  # pragma: no cover - protective
                pass
            try:
                sock.close()
            except Exception:  # pragma: no cover - protective
                pass

    # ------------------------------------------------------------------
    # Subscribe (SUBSCRIBE method on /stream endpoint)
    # ------------------------------------------------------------------
    def subscribe(self, streams: Sequence[str]) -> None:
        """Send a JSON SUBSCRIBE message for the given streams.

        Every stream is run through
        :func:`assert_public_ws_stream_allowed` before the frame goes
        out. The combined ``/stream?streams=<>`` URL we used for the
        initial subscribe still works; this method is for additional
        per-symbol subscribes a future runner may add.
        """
        canonical: list[str] = []
        for stream in streams:
            canonical.append(assert_public_ws_stream_allowed(stream))
        if not canonical:
            return
        if self._sock is None:
            self._subscribed_streams = tuple(canonical)
            return
        # JSON subscribe message - public-only payload.
        payload = json.dumps(
            {
                "method": "SUBSCRIBE",
                "params": canonical,
                "id": int(now_ms() % 1_000_000),
            }
        ).encode("utf-8")
        self._send_frame(self.OPCODE_TEXT, payload)
        # Merge with the URL-side subscriptions.
        merged = list(self._subscribed_streams)
        for s in canonical:
            if s not in merged:
                merged.append(s)
        self._subscribed_streams = tuple(merged)

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------
    def poll(self, *, timeout_seconds: float) -> list[WSMessage]:
        """Drain currently-buffered frames + read up to
        ``timeout_seconds`` seconds of new bytes from the socket.

        Returns the list of fresh :class:`WSMessage` envelopes; an
        empty list means "no traffic yet, try again". Frames that
        arrive but fail the public allowlist are silently dropped
        (we already refuse them at subscribe time; this is
        defence-in-depth against a server that pushes an unsolicited
        private-shaped event).

        Phase 11C.1B PR-B fix
        ---------------------

        The first incarnation of this method gated EVERY ``recv``
        call behind a ``remaining = deadline - time.monotonic()``
        check. With ``timeout_seconds=0.0`` (the runner's per-tick
        non-blocking probe) ``remaining`` was already negative on
        the first iteration so the loop broke before any bytes were
        read off the socket. Bytes piled up in the kernel TCP
        buffer between ticks but Python's ``_recv_buffer`` stayed
        empty - the routed connections succeeded but
        ``ws_messages_received`` stuck at 0. The 5-min real-WS
        smoke test reproduced this exactly. We now ALWAYS attempt
        one non-blocking drain at the top of the call (regardless
        of ``timeout_seconds``) so a caller that passes 0.0 still
        picks up every byte the kernel buffered for us since the
        previous poll.
        """
        if self._sock is None or self._closed:
            return []
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        out: list[WSMessage] = []
        # Pass 1: drain whatever bytes the kernel has already
        # buffered, regardless of ``timeout_seconds``. This is the
        # load-bearing change for the Phase 11C.1B PR-B real-WS
        # smoke test - the runner calls ``pump_messages
        # (timeout_seconds=0.0)`` on every loop tick and then
        # sleeps; without this drain the socket's recv path was
        # never entered.
        if not self._drain_recv_buffer_nonblocking():
            # Socket closed during the non-blocking drain. Surface
            # whatever frames were already in ``_recv_buffer``.
            while True:
                msg = self._try_extract_message()
                if msg is None:
                    break
                out.append(msg)
            return out
        while True:
            msg = self._try_extract_message()
            if msg is not None:
                out.append(msg)
                continue
            if not self._connected:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # No more time; return what we have. The pre-loop
                # non-blocking drain above guarantees we have
                # already surfaced every kernel-buffered byte even
                # when ``timeout_seconds=0.0``.
                break
            try:
                ready, _, _ = select.select(
                    [self._sock], [], [], remaining
                )
            except (OSError, ValueError):
                self._connected = False
                break
            if not ready:
                break
            if not self._drain_recv_buffer_nonblocking():
                break
        return out

    def _drain_recv_buffer_nonblocking(self) -> bool:
        """Read everything the socket has currently buffered into
        ``_recv_buffer`` without blocking.

        Returns ``True`` if the socket is still healthy after the
        drain (whether or not bytes were read), ``False`` if the
        socket closed or errored. The socket is set to non-blocking
        mode at the end of :meth:`connect` so ``recv`` raises
        :class:`BlockingIOError` / :class:`ssl.SSLWantReadError`
        when no bytes are available - we treat that as "drain
        complete" and return ``True``.

        This helper is the single point where the WS adapter pulls
        bytes off the socket. Centralising it makes the
        Phase 11C.1B PR-B fix (drain on every poll regardless of
        ``timeout_seconds``) observable in one place; any future
        reconnect / framing change only has to touch this method.
        """
        sock = self._sock
        if sock is None:
            return False
        while True:
            try:
                chunk = sock.recv(self._recv_chunk_size)
            except (BlockingIOError, ssl.SSLWantReadError):
                return True  # no more data right now; socket healthy
            except (OSError, ssl.SSLError):
                self._connected = False
                return False
            if not chunk:
                # Server closed the connection cleanly.
                self._connected = False
                return False
            self._recv_buffer.extend(chunk)

    @property
    def is_connected(self) -> bool:
        return self._connected and not self._closed

    @property
    def url(self) -> str:
        return self._url

    @property
    def route(self) -> str | None:
        """Return the routed-endpoint group this transport targets.

        ``"public"`` and ``"market"`` are the Phase 11C.1B routed
        acceptance values; ``None`` means the transport is using the
        legacy unrouted ``/stream`` path (back-compat fixtures only;
        not the production WS-first acceptance path).
        """
        return self._route

    @property
    def subscribed_streams(self) -> tuple[str, ...]:
        return self._subscribed_streams

    # ------------------------------------------------------------------
    # Frame helpers
    # ------------------------------------------------------------------
    def _send_frame(
        self,
        opcode: int,
        data: bytes,
        *,
        sock: socket.socket | None = None,
    ) -> None:
        target = sock if sock is not None else self._sock
        if target is None:
            return
        # FIN=1, RSV=0, opcode in low 4 bits.
        b1 = 0x80 | (opcode & 0x0F)
        length = len(data)
        if length < 126:
            header = struct.pack("!BB", b1, 0x80 | length)
        elif length < 65_536:
            header = struct.pack("!BBH", b1, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", b1, 0x80 | 127, length)
        mask_key = self._random_bytes_fn(4)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        try:
            target.sendall(header + mask_key + masked)
        except (OSError, ssl.SSLError):
            self._connected = False

    def _try_extract_message(self) -> WSMessage | None:
        """Try to consume one complete message from ``_recv_buffer``.

        Returns ``None`` if no complete frame is available. Pings are
        answered with a pong inline. Close frames flip ``_connected``
        off. Fragmented and binary frames are skipped (the public
        allowlist endpoints only push complete text frames).
        """
        buf = self._recv_buffer
        while True:
            if len(buf) < 2:
                return None
            b0 = buf[0]
            b1 = buf[1]
            fin = (b0 >> 7) & 1
            opcode = b0 & 0x0F
            masked = (b1 >> 7) & 1
            length = b1 & 0x7F
            offset = 2
            if length == 126:
                if len(buf) < 4:
                    return None
                length = struct.unpack("!H", bytes(buf[2:4]))[0]
                offset = 4
            elif length == 127:
                if len(buf) < 10:
                    return None
                length = struct.unpack("!Q", bytes(buf[2:10]))[0]
                offset = 10
            mask_key = b""
            if masked:
                if len(buf) < offset + 4:
                    return None
                mask_key = bytes(buf[offset : offset + 4])
                offset += 4
            if len(buf) < offset + length:
                return None
            payload = bytes(buf[offset : offset + length])
            if masked and mask_key:
                payload = bytes(
                    p ^ mask_key[i % 4] for i, p in enumerate(payload)
                )
            del buf[: offset + length]

            if opcode == self.OPCODE_PING:
                # Echo the payload back as a pong.
                self._send_frame(self.OPCODE_PONG, payload)
                continue
            if opcode == self.OPCODE_PONG:
                continue
            if opcode == self.OPCODE_CLOSE:
                self._connected = False
                return None
            if opcode != self.OPCODE_TEXT:
                # We don't accept binary or continuation frames in the
                # public-market endpoint; silently skip.
                continue
            if not fin:
                # The public endpoints don't fragment; if Binance ever
                # changes that we re-implement reassembly. For now we
                # skip the partial frame.
                continue
            try:
                decoded = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            stream, data = self._extract_stream_and_data(decoded)
            try:
                stream = assert_public_ws_stream_allowed(stream)
            except PublicWSStreamForbidden:
                # Defence-in-depth: drop any stream the server sent that
                # didn't match the public allowlist.
                continue
            return WSMessage(stream=stream, data=data)

    def _extract_stream_and_data(
        self, decoded: Any
    ) -> tuple[str, Any]:
        """Map a decoded WS message to ``(stream, data)``.

        The combined ``/stream?streams=`` endpoint wraps each push in
        ``{"stream": "<name>", "data": <payload>}``. Single-stream
        ``/ws/<name>`` connections push the bare payload; the caller
        knows the stream from the URL so we fall back to the first
        configured subscription. Defensive against unexpected shapes.
        """
        if isinstance(decoded, dict):
            if "stream" in decoded and "data" in decoded:
                return str(decoded.get("stream", "")), decoded.get("data")
            # Some Binance pushes (e.g. !forceOrder@arr) deliver a
            # raw object whose ``e`` field is the event type.
            event_type = decoded.get("e") if isinstance(decoded, dict) else None
            if event_type == "forceOrder":
                return "!forceOrder@arr", decoded
            if event_type == "markPriceUpdate":
                return "!markPrice@arr", decoded
            if event_type == "24hrTicker":
                return "!ticker@arr", decoded
            if event_type == "24hrMiniTicker":
                return "!miniTicker@arr", decoded
            if event_type == "bookTicker":
                return "!bookTicker", decoded
        if (
            isinstance(decoded, list)
            and decoded
            and isinstance(decoded[0], dict)
        ):
            event_type = decoded[0].get("e")
            if event_type == "24hrTicker":
                return "!ticker@arr", decoded
            if event_type == "24hrMiniTicker":
                return "!miniTicker@arr", decoded
            if event_type == "markPriceUpdate":
                return "!markPrice@arr", decoded
        # Fall back to the first configured stream so the message
        # is at least attributed to the radar buffer.
        fallback = (
            self._subscribed_streams[0]
            if self._subscribed_streams
            else "!ticker@arr"
        )
        return fallback, decoded


# ---------------------------------------------------------------------------
# Multi-transport routed public/market WS manager
# ---------------------------------------------------------------------------
class MultiTransportPublicWSManager(WSMessagePump):
    """Phase 11C.1B routed public + market WebSocket connection group.

    The Binance USDⓈ-M Futures public WebSocket reference splits the
    public surface into two routed endpoints:

      - ``wss://fstream.binance.com/public/stream?streams=<a>/<b>``
        for the ``!bookTicker`` (best bid / ask) family.
      - ``wss://fstream.binance.com/market/stream?streams=<a>/<b>``
        for the ``!ticker@arr`` / ``!miniTicker@arr`` /
        ``!markPrice@arr`` / ``!forceOrder@arr`` (market data
        statistics + funding + liquidations) family.

    A single unrouted ``wss://fstream.binance.com/stream?streams=...``
    connection silently drops the market-class streams (Binance only
    pushes the public-only subset over the unrouted endpoint). The
    Phase 11C.1B WS-first acceptance path therefore opens TWO routed
    transports - one per route - and merges their messages behind
    this single :class:`WSMessagePump` interface so
    :class:`BinancePublicWSClient` and the runner can pump the union
    without any awareness of the underlying topology.

    Construction-time refusals match
    :class:`StdlibPublicWSTransport`:

      - any non-``None`` ``api_key`` / ``api_secret`` /
        ``listen_key`` raises :class:`PublicWSCredentialForbidden`;
      - any extra credential-shaped kwarg likewise refuses;
      - the configured streams MUST split cleanly into the public
        and market route groups via :func:`split_streams_by_route`;
      - the routed-private surface (``/private``) is never
        reachable: it is on :data:`FORBIDDEN_WS_PATH_ROOTS` and
        the URL parser refuses it before connect runs.

    The manager owns one transport per route. A route with no
    streams (e.g. an operator who explicitly lists only
    ``!bookTicker``) is left without a transport - the manager only
    opens the routes it actually needs.
    """

    SOURCE_MODULE = "exchanges.binance_public_ws.multi_transport_manager"

    def __init__(
        self,
        *,
        config: WSConfig | None = None,
        public_transport: WSMessagePump | None = None,
        market_transport: WSMessagePump | None = None,
        transport_factory: (
            Callable[[WSConfig, str], WSMessagePump] | None
        ) = None,
        # Refusal sentinels - same pattern as
        # StdlibPublicWSTransport / BinancePublicWSClient.
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
                "MultiTransportPublicWSManager must not be "
                "instantiated with api_key / api_secret / "
                "listen_key. Phase 11C.1B is public-market "
                "read-only; credentials and listenKey are forbidden."
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
                    f"MultiTransportPublicWSManager: refused "
                    f"credential-shaped keyword argument {name!r}."
                )
        if forbidden_credentials:
            raise TypeError(
                "MultiTransportPublicWSManager got unexpected "
                f"keyword argument(s): {sorted(forbidden_credentials)}"
            )

        self._config = config or WSConfig()
        # Validate every stream against the allowlist + classify
        # each into ``public`` / ``market``. This refuses any
        # private-WS / listenKey / user-data / trading-WS-API surface
        # before any socket is opened.
        split = split_streams_by_route(self._config.streams)
        self._public_streams: tuple[str, ...] = tuple(split["public"])
        self._market_streams: tuple[str, ...] = tuple(split["market"])
        if not self._public_streams and not self._market_streams:
            raise PublicWSStreamForbidden(
                "MultiTransportPublicWSManager: refused empty stream "
                "set; configure at least one PUBLIC or MARKET stream."
            )

        # Build per-route configs. Each routed transport owns a
        # config whose ``streams`` is the route-restricted subset
        # AND whose post-init validation runs through the same
        # allowlist.
        def _make_route_config(streams: tuple[str, ...]) -> WSConfig:
            return WSConfig(
                base_url=self._config.base_url,
                streams=streams,
                staleness_threshold_ms=self._config.staleness_threshold_ms,
                reconnect_backoff_initial_seconds=(
                    self._config.reconnect_backoff_initial_seconds
                ),
                reconnect_backoff_max_seconds=(
                    self._config.reconnect_backoff_max_seconds
                ),
                auto_reconnect=self._config.auto_reconnect,
                max_subscriptions=self._config.max_subscriptions,
            )

        # Default factory builds real :class:`StdlibPublicWSTransport`
        # adapters bound to the routed endpoint. Tests inject a
        # deterministic factory (or pre-built fakes) instead.
        def _default_factory(cfg: WSConfig, route: str) -> WSMessagePump:
            return StdlibPublicWSTransport(config=cfg, route=route)

        factory = transport_factory or _default_factory

        self._transports: dict[str, WSMessagePump] = {}
        if self._public_streams:
            if public_transport is not None:
                self._transports["public"] = public_transport
            else:
                self._transports["public"] = factory(
                    _make_route_config(self._public_streams), "public"
                )
        if self._market_streams:
            if market_transport is not None:
                self._transports["market"] = market_transport
            else:
                self._transports["market"] = factory(
                    _make_route_config(self._market_streams), "market"
                )

        self._connected: bool = False
        self._closed: bool = False
        self._subscribed_streams: tuple[str, ...] = (
            self._public_streams + self._market_streams
        )
        # Per-route message counters - merged into the metrics
        # payload the runner picks up for the daily report.
        self._messages_received_by_route: dict[str, int] = {
            route: 0 for route in self._transports
        }

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def routes(self) -> tuple[str, ...]:
        """Return the tuple of routes the manager actually opened.

        ``("public", "market")`` in the canonical Phase 11C.1B
        five-stream config; subsets are possible if the operator
        explicitly narrows the stream list.
        """
        return tuple(sorted(self._transports.keys()))

    @property
    def public_streams(self) -> tuple[str, ...]:
        return self._public_streams

    @property
    def market_streams(self) -> tuple[str, ...]:
        return self._market_streams

    @property
    def transports(self) -> Mapping[str, WSMessagePump]:
        """Return the read-only ``{route -> transport}`` mapping.

        Tests use this to assert routed URLs / introspect per-route
        state. Production code SHOULD pump through :meth:`poll` so
        the manager owns the merge ordering.
        """
        return dict(self._transports)

    @property
    def messages_received_by_route(self) -> Mapping[str, int]:
        return dict(self._messages_received_by_route)

    @property
    def subscribed_streams(self) -> tuple[str, ...]:
        return self._subscribed_streams

    # ------------------------------------------------------------------
    # WSMessagePump implementation
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open every routed transport in turn.

        If any single route fails the manager re-raises the failure
        AFTER tearing down whichever transports already connected.
        Phase 11C.1B does NOT silently degrade: a partial-route open
        would mean missing market-class streams without telling the
        operator.
        """
        opened: list[str] = []
        try:
            for route in ("public", "market"):
                transport = self._transports.get(route)
                if transport is None:
                    continue
                transport.connect()
                opened.append(route)
        except Exception:
            for route in opened:
                try:
                    self._transports[route].disconnect()
                except Exception:  # pragma: no cover - protective
                    pass
            self._connected = False
            self._closed = True
            raise
        self._connected = bool(opened)
        self._closed = not self._connected

    def disconnect(self) -> None:
        for route, transport in list(self._transports.items()):
            try:
                transport.disconnect()
            except Exception as exc:  # pragma: no cover - protective
                logger.warning(
                    "[phase11c.1b] multi-transport route {} "
                    "disconnect raised: {}",
                    route,
                    exc,
                )
        self._connected = False
        self._closed = True

    def subscribe(self, streams: Sequence[str]) -> None:
        """Route a subscribe call to the matching per-route transport.

        Every stream is run through the allowlist + route classifier
        BEFORE any frame goes out. A subscribe that mixes public /
        market streams is split per-route automatically.
        """
        if not streams:
            return
        for stream in streams:
            assert_public_ws_stream_allowed(stream)
        split = split_streams_by_route(streams)
        for route, route_streams in split.items():
            if not route_streams:
                continue
            transport = self._transports.get(route)
            if transport is None:
                raise PublicWSStreamForbidden(
                    f"MultiTransportPublicWSManager: refused "
                    f"subscribe for {route!r} route; that route was "
                    "not opened by this manager. Reconfigure "
                    "WSConfig.streams to include the route's streams "
                    "at construction time."
                )
            transport.subscribe(route_streams)
        merged = list(self._subscribed_streams)
        for stream in streams:
            if stream not in merged:
                merged.append(stream)
        self._subscribed_streams = tuple(merged)

    def poll(self, *, timeout_seconds: float) -> list[WSMessage]:
        """Drain every routed transport and return the merged list.

        The merge order is deterministic: PUBLIC route first (best
        bid / ask updates), MARKET route second
        (ticker / mini-ticker / mark-price / liquidations). The
        radar buffer is order-insensitive within a single tick so
        this only matters for snapshot tracing.
        """
        # Spread the budget across the routes opened. Each route
        # receives an equal slice; a fractional split is fine
        # because the underlying ``select`` honours a 0-second
        # timeout and the call returns immediately when there are
        # no buffered bytes left.
        if not self._transports:
            return []
        slice_seconds = max(
            0.0, float(timeout_seconds) / max(1, len(self._transports))
        )
        out: list[WSMessage] = []
        for route in ("public", "market"):
            transport = self._transports.get(route)
            if transport is None:
                continue
            try:
                msgs = transport.poll(timeout_seconds=slice_seconds)
            except Exception as exc:
                logger.warning(
                    "[phase11c.1b] multi-transport route {} "
                    "poll raised: {}",
                    route,
                    exc,
                )
                continue
            if msgs:
                out.extend(msgs)
                self._messages_received_by_route[route] = (
                    self._messages_received_by_route.get(route, 0)
                    + len(msgs)
                )
        return out

    @property
    def is_connected(self) -> bool:
        if not self._transports:
            return False
        return all(
            getattr(t, "is_connected", False)
            for t in self._transports.values()
        )

    # ------------------------------------------------------------------
    # Daily-report payload (route-level counters)
    # ------------------------------------------------------------------
    def metrics_payload(self) -> dict[str, Any]:
        """Return the JSON-safe per-route metrics block.

        The :class:`BinancePublicWSClient` already exports
        connection / staleness counters; this payload exposes the
        per-route message counts so the daily-report aggregator can
        cross-check that BOTH public and market routes actually
        pushed data during the run.
        """
        per_route_urls: dict[str, str] = {}
        for route, transport in self._transports.items():
            url = getattr(transport, "url", None)
            if url is not None:
                per_route_urls[route] = str(url)
        return {
            "ws_routes_opened": list(self.routes),
            "ws_route_urls": per_route_urls,
            "ws_messages_by_route": dict(self._messages_received_by_route),
            "ws_public_streams": list(self._public_streams),
            "ws_market_streams": list(self._market_streams),
        }


def create_real_public_ws_transport(
    *,
    config: WSConfig | None = None,
    **kwargs: Any,
) -> WSMessagePump:
    """Public factory for the Phase 11C.1B real-network WS pump.

    Returns a :class:`MultiTransportPublicWSManager` bound to the
    supplied configuration. The manager owns one routed
    :class:`StdlibPublicWSTransport` per route (PUBLIC + MARKET) and
    presents them behind a single :class:`WSMessagePump` interface
    so the runner / :class:`BinancePublicWSClient` can pump the
    union without any awareness of the topology.

    The runner calls this when ``--ws-first`` is set without
    ``--dry-run``. Tests can monkey-patch the runner-side reference
    to inject a fake pump without touching the production
    constructor. The factory itself refuses every credential-shaped
    kwarg (forwarded to the manager) and never reads
    ``BINANCE_API_KEY`` / ``BINANCE_API_SECRET`` (the implementation
    does not import ``os.environ``).
    """
    return MultiTransportPublicWSManager(config=config, **kwargs)


__all__ = [
    "ALLOWED_PUBLIC_WS_HOSTS",
    "ALLOWED_PUBLIC_WS_PATH_ROOTS",
    "BinancePublicWSClient",
    "DEFAULT_WS_BASE_URL",
    "FORBIDDEN_WS_PATH_ROOTS",
    "FORBIDDEN_WS_QUERY_TOKENS",
    "FORBIDDEN_WS_TOKENS",
    "InProcessWSPump",
    "LEGACY_UNROUTED_WS_PATH_ROOTS",
    "MultiTransportPublicWSManager",
    "PUBLIC_WS_STREAM_ALLOWLIST",
    "PUBLIC_WS_STREAM_PREFIX_ALLOWLIST",
    "PublicWSCredentialForbidden",
    "PublicWSError",
    "PublicWSStreamForbidden",
    "PublicWSTransportError",
    "STREAM_ROUTE_MARKET",
    "STREAM_ROUTE_PUBLIC",
    "STREAM_SUFFIX_ROUTE_MARKET",
    "STREAM_SUFFIX_ROUTE_PUBLIC",
    "StdlibPublicWSTransport",
    "WSConfig",
    "WSMessage",
    "WSMessagePump",
    "assert_public_ws_path_allowed",
    "assert_public_ws_stream_allowed",
    "assert_public_ws_url_allowed",
    "classify_stream_route",
    "create_real_public_ws_transport",
    "split_streams_by_route",
]
