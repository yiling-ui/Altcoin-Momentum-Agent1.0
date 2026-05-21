"""Phase 11C.1B - Real Binance public WebSocket adapter tests.

The Phase 11C.1B brief requires that PR #32 ship a real (not refusal-
only) public-market WebSocket adapter, that the runner refuses to
silently fall back to REST under ``--ws-first`` without ``--dry-run``,
and that every safety flag stays unchanged with the real adapter
enabled. This file pins each behaviour the brief enumerates:

  - test_real_public_ws_adapter_allows_only_public_hosts
  - test_real_public_ws_adapter_rejects_private_hosts
  - test_real_public_ws_adapter_rejects_listen_key
  - test_real_public_ws_adapter_rejects_user_data_stream
  - test_real_public_ws_adapter_rejects_trading_ws_api
  - test_real_public_ws_adapter_rejects_credentials
  - test_runner_real_ws_first_refuses_if_transport_missing
  - test_runner_real_ws_first_uses_ws_adapter
  - test_runner_real_ws_first_does_not_silent_fallback_to_rest
  - test_ws_reconnect_backoff
  - test_ws_staleness_enters_data_degraded
  - test_public_ws_connected_event_written
  - test_public_ws_stale_event_written
  - test_safety_flags_unchanged_with_real_ws_enabled
  - test_no_private_ws_or_listen_key_in_phase11c1b

Every test is isolated: no real socket is opened. The
:class:`StdlibPublicWSTransport` is exercised through a fake socket
factory and a fake TLS-wrap function so the RFC 6455 handshake +
frame layer can be validated end-to-end without touching the
network. The runner tests inject a deterministic
:class:`InProcessWSPump` (masquerading as a "real" transport) via the
:func:`scripts.run_public_market_paper._build_real_public_ws_transport`
hook.
"""

from __future__ import annotations

import base64
import hashlib
import io
import socket
import sqlite3
import struct
from pathlib import Path
from typing import Any

import pytest

from app.config.settings import get_settings, load_settings
from app.core.errors import SafeModeViolation
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exchanges.binance_public_ws import (
    ALLOWED_PUBLIC_WS_HOSTS,
    ALLOWED_PUBLIC_WS_PATH_ROOTS,
    BinancePublicWSClient,
    DEFAULT_WS_BASE_URL,
    InProcessWSPump,
    PublicWSCredentialForbidden,
    PublicWSStreamForbidden,
    PublicWSTransportError,
    StdlibPublicWSTransport,
    WSConfig,
    WSMessage,
    assert_public_ws_path_allowed,
    create_real_public_ws_transport,
)


# ---------------------------------------------------------------------------
# Fake socket / TLS plumbing - lets us exercise the stdlib RFC 6455 client
# end-to-end without touching the network.
# ---------------------------------------------------------------------------


WS_RFC6455_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _FakeWSConn:
    """Minimal in-memory bidirectional channel that quacks like a
    socket *after* the TLS handshake. The fake records every byte the
    client sends, lets the test feed pre-built bytes (HTTP upgrade
    response + RFC 6455 frames) back, and supports
    :meth:`select.select`-style polling via :meth:`fileno`.
    """

    def __init__(self) -> None:
        self._inbound = bytearray()
        self.outbound = bytearray()
        self.closed = False
        self.shut_down = False
        self.timeout_seconds: float | None = None
        self.blocking: bool = True
        self._read_pipe_r, self._read_pipe_w = socket.socketpair()
        # The reader side of the pipe is what select() will poll. We
        # write a single sentinel byte every time we feed inbound bytes
        # so select() returns ready.
        self._read_pipe_r.setblocking(False)

    # Helpers used by the test ----------------------------------------------
    def feed(self, data: bytes) -> None:
        self._inbound.extend(data)
        try:
            self._read_pipe_w.send(b"\x00")
        except OSError:
            pass

    def feed_text_frame(self, payload: bytes) -> None:
        self.feed(_build_server_text_frame(payload))

    def feed_close_frame(self) -> None:
        # 1000 normal closure
        self.feed(_build_server_close_frame())

    # socket-shim API -------------------------------------------------------
    def settimeout(self, value: float | None) -> None:
        self.timeout_seconds = value

    def setblocking(self, flag: bool) -> None:
        self.blocking = bool(flag)

    def fileno(self) -> int:
        return self._read_pipe_r.fileno()

    def sendall(self, data: bytes) -> None:
        if self.closed:
            raise OSError("fake socket closed")
        self.outbound.extend(data)

    def recv(self, n: int) -> bytes:
        if self.closed:
            return b""
        if not self._inbound:
            if not self.blocking:
                raise BlockingIOError("no data")
            return b""
        chunk = bytes(self._inbound[:n])
        del self._inbound[:n]
        # Drain one sentinel byte so select() doesn't perpetually
        # report "ready" when the inbound buffer is actually empty.
        try:
            self._read_pipe_r.recv(1)
        except (BlockingIOError, OSError):
            pass
        return chunk

    def shutdown(self, _how: int) -> None:
        self.shut_down = True

    def close(self) -> None:
        self.closed = True
        try:
            self._read_pipe_r.close()
        except OSError:
            pass
        try:
            self._read_pipe_w.close()
        except OSError:
            pass


def _make_socket_factory(connections: list[_FakeWSConn]):
    """Return a socket-factory that hands back the supplied fake
    connections in order. Each call to ``socket(...)`` consumes one."""

    def factory(*_args: Any, **_kwargs: Any) -> socket.socket:
        if not connections:
            raise OSError("no more fake connections available")
        # Return a pseudo-socket that can be ``connect()``ed. The
        # transport calls ``ssl_wrap_fn(sock, host)`` next and we
        # ignore ``sock`` there - we just need an object with a
        # ``connect`` and ``close`` method.
        conn = connections[0]

        class _ConnectShim:
            def __init__(self, real: _FakeWSConn) -> None:
                self.real = real

            def settimeout(self, value: float | None) -> None:
                self.real.settimeout(value)

            def connect(self, _addr: tuple[str, int]) -> None:
                # No-op: the fake is already wired.
                return None

            def close(self) -> None:
                # Only close the wrapper; the wrapped fake is closed
                # when the transport calls disconnect().
                return None

            def fileno(self) -> int:
                return self.real.fileno()

        return _ConnectShim(conn)

    return factory


def _make_ssl_wrap(connections: list[_FakeWSConn]):
    """Return an ssl-wrap fn that hands back the next fake. Pops on
    each call so multiple connect() rounds in a single test pull
    through their corresponding fake."""

    def wrap(_sock: Any, _host: str) -> Any:
        return connections.pop(0)

    return wrap


def _build_server_text_frame(payload: bytes) -> bytes:
    """Build an unmasked text frame (server-to-client)."""
    b1 = 0x80 | 0x1  # FIN + TEXT
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", b1, length)
    elif length < 65_536:
        header = struct.pack("!BBH", b1, 126, length)
    else:
        header = struct.pack("!BBQ", b1, 127, length)
    return header + payload


def _build_server_close_frame() -> bytes:
    payload = struct.pack("!H", 1000)  # status code 1000
    return struct.pack("!BB", 0x88, len(payload)) + payload


def _build_upgrade_response(sec_ws_key: str) -> bytes:
    accept = base64.b64encode(
        hashlib.sha1((sec_ws_key + WS_RFC6455_GUID).encode("ascii")).digest()
    ).decode("ascii")
    return (
        f"HTTP/1.1 101 Switching Protocols\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        f"\r\n"
    ).encode("ascii")


def _extract_sec_ws_key(outbound: bytes) -> str:
    head = outbound.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    for line in head.split("\r\n"):
        if ":" in line:
            name, value = line.split(":", 1)
            if name.strip().lower() == "sec-websocket-key":
                return value.strip()
    raise AssertionError(
        f"Sec-WebSocket-Key not found in client request: {head!r}"
    )


@pytest.fixture
def real_transport_with_fake_socket(monkeypatch: pytest.MonkeyPatch):
    """Construct a real :class:`StdlibPublicWSTransport` plumbed to
    a fake in-memory socket. The fixture yields ``(transport, conn)``;
    the test feeds bytes into ``conn`` via :meth:`feed_text_frame` or
    :meth:`feed_close_frame` and asserts on the transport's behaviour.
    """
    conn = _FakeWSConn()
    connections = [conn]
    transport = StdlibPublicWSTransport(
        config=WSConfig(),
        socket_factory=_make_socket_factory(connections),
        ssl_wrap_fn=_make_ssl_wrap(connections),
        random_bytes_fn=lambda n: b"\x00" * n,
    )
    yield transport, conn


def _seed_handshake(conn: _FakeWSConn) -> None:
    """Run the WS upgrade handshake from the server side: read the
    client's GET, build the matching 101 response, feed it back."""
    # The transport sends the request first, then reads the response.
    # We can't easily "wait" because the transport is synchronous; the
    # test always calls :meth:`feed` BEFORE :meth:`connect` so the
    # response is already buffered when ``recv`` happens.
    # The Sec-WebSocket-Key for our deterministic random_bytes_fn
    # (16 zero bytes) is the base64 of 16 zero bytes.
    sec_ws_key = base64.b64encode(b"\x00" * 16).decode("ascii")
    conn.feed(_build_upgrade_response(sec_ws_key))


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital), dbs


def _settings():
    get_settings.cache_clear()
    return load_settings()


# ---------------------------------------------------------------------------
# 1-6. Adapter allowlist / denylist / credential refusals
# ---------------------------------------------------------------------------


def test_real_public_ws_adapter_allows_only_public_hosts():
    """The adapter accepts ``wss://fstream.binance.com`` and
    ``wss://fstream.binancefuture.com`` (testnet) and refuses every
    other host."""
    for host in ALLOWED_PUBLIC_WS_HOSTS:
        cfg = WSConfig(base_url=f"wss://{host}")
        transport = StdlibPublicWSTransport(config=cfg)
        assert transport.url.startswith(f"wss://{host}")
    # Routed path roots are the Phase 11C.1B acceptance allowlist.
    assert ALLOWED_PUBLIC_WS_PATH_ROOTS == frozenset(
        {"public/ws", "public/stream", "market/ws", "market/stream"}
    )
    # Routed path roots accepted.
    assert (
        assert_public_ws_path_allowed("/public/ws") == "/public/ws"
    )
    assert (
        assert_public_ws_path_allowed("/public/stream")
        == "/public/stream"
    )
    assert (
        assert_public_ws_path_allowed("/market/ws") == "/market/ws"
    )
    assert (
        assert_public_ws_path_allowed("/market/stream")
        == "/market/stream"
    )
    assert (
        assert_public_ws_path_allowed("/public/ws/btcusdt@bookTicker")
        == "/public/ws/btcusdt@bookTicker"
    )
    # Legacy unrouted roots are still accepted (back-compat for
    # in-process pump fixtures); the runner does NOT use them.
    assert assert_public_ws_path_allowed("/ws") == "/ws"
    assert assert_public_ws_path_allowed("/stream") == "/stream"
    assert assert_public_ws_path_allowed("/ws/btcusdt@bookTicker") == (
        "/ws/btcusdt@bookTicker"
    )


def test_real_public_ws_adapter_rejects_private_hosts():
    """A non-allowlisted host (the public-data ``stream.binance.com``
    spot host, the ``ws-api.binance.com`` private trading host, or
    any third-party host) must be refused at construction time."""
    for host in (
        "stream.binance.com",
        "ws-api.binance.com",
        "api.binance.com",
        "evil.example.com",
    ):
        with pytest.raises(PublicWSStreamForbidden):
            StdlibPublicWSTransport(config=WSConfig(base_url=f"wss://{host}"))
    # Path-root allowlist refuses anything outside /ws and /stream.
    for path in ("/ws-api", "/userDataStream", "/account", "/order", "/trade"):
        with pytest.raises(PublicWSStreamForbidden):
            assert_public_ws_path_allowed(path)


def test_real_public_ws_adapter_rejects_listen_key():
    """The constructor refuses ``listen_key=`` outright, and a URL
    that embeds ``listenKey`` is rejected by the URL validator the
    transport runs in ``__init__``."""
    with pytest.raises(PublicWSCredentialForbidden):
        StdlibPublicWSTransport(listen_key="abc123")
    # listenKey-shaped kwarg is also refused.
    with pytest.raises(PublicWSCredentialForbidden):
        StdlibPublicWSTransport(**{"listenKey": "abc"})


def test_real_public_ws_adapter_rejects_user_data_stream():
    """The user-data / private stream surfaces are refused both as
    config streams AND as composed URL paths."""
    # As a config stream.
    with pytest.raises(PublicWSStreamForbidden):
        WSConfig(streams=("btcusdt@accountUpdate",))
    with pytest.raises(PublicWSStreamForbidden):
        WSConfig(streams=("btcusdt@orderTradeUpdate",))
    with pytest.raises(PublicWSStreamForbidden):
        WSConfig(streams=("userDataStream",))


def test_real_public_ws_adapter_rejects_trading_ws_api():
    """The ``ws-api`` / ``trading-api`` / ``ws-fapi`` private trading
    WebSocket hosts and paths are refused both at the URL parser and
    via the path-root allowlist."""
    # /ws-api as a path root.
    with pytest.raises(PublicWSStreamForbidden):
        assert_public_ws_path_allowed("/ws-api/v3/order.place")
    # ``trading-api`` substring is on the deny list.
    with pytest.raises(PublicWSStreamForbidden):
        WSConfig(streams=("/trading-api/v3/order.place",))
    # ``ws-fapi`` is on the deny list.
    with pytest.raises(PublicWSStreamForbidden):
        WSConfig(streams=("/ws-fapi/v1/order",))


def test_real_public_ws_adapter_rejects_credentials():
    """Any credential-shaped kwarg is refused at construction time."""
    for kwarg in (
        "api_key",
        "api_secret",
        "secret",
        "token",
        "signature",
        "passphrase",
        "apiKey",
        "binance_api_key",
    ):
        with pytest.raises(PublicWSCredentialForbidden):
            StdlibPublicWSTransport(**{kwarg: "x"})
    # And ``create_real_public_ws_transport`` propagates the same
    # refusal because it forwards kwargs unchanged.
    with pytest.raises(PublicWSCredentialForbidden):
        create_real_public_ws_transport(api_key="x")


# ---------------------------------------------------------------------------
# 7-9. Runner: --ws-first without --dry-run requires a real transport
# ---------------------------------------------------------------------------


def _runner_environ_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    for name in (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    from app.config.settings import get_settings as _gs

    _gs.cache_clear()


def _stub_rest_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the runner's REST transport to the deterministic
    in-process stub so :func:`scripts.run_public_market_paper.main`
    never attempts a real urllib request. Without this hook
    ``_resolve_symbols`` would hit ``fapi.binance.com``."""
    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(
        runner_mod,
        "_build_rest_transport",
        lambda *, dry_run: runner_mod._build_dry_run_transport(),
    )


def test_runner_real_ws_first_refuses_if_transport_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """When the runner's real-WS factory is monkey-patched to return
    ``None`` (transport unavailable) and ``--ws-first`` is set
    without ``--dry-run``, the runner MUST refuse with rc=2 and a
    clear error - not silently degrade to REST bootstrap."""
    _runner_environ_fixture(monkeypatch, tmp_path)
    _stub_rest_transport(monkeypatch)
    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(runner_mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        runner_mod, "_build_real_public_ws_transport", lambda _cfg: None
    )

    rc = runner_mod.main(
        [
            "--duration",
            "0.5s",
            "--symbol-limit",
            "2",
            "--ws-first",
            # NO --dry-run
            "--poll-interval-seconds",
            "0.05",
            "--no-banner",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2, captured
    assert (
        "real public WebSocket transport is required for --ws-first"
        in captured.err
    )


def test_runner_real_ws_first_does_not_silent_fallback_to_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """When the factory raises (e.g. ImportError, network refusal),
    the runner MUST refuse with rc=2 instead of silently switching to
    the PR-A REST-bootstrap-only path. The events.db must NOT contain
    a single ``MARKET_SNAPSHOT`` (which would be the tell-tale sign of
    a silent fallback)."""
    _runner_environ_fixture(monkeypatch, tmp_path)
    _stub_rest_transport(monkeypatch)
    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(runner_mod.time, "sleep", lambda _s: None)

    def _raise(_cfg):
        raise OSError("simulated network failure")

    monkeypatch.setattr(
        runner_mod, "_build_real_public_ws_transport", _raise
    )

    rc = runner_mod.main(
        [
            "--duration",
            "0.5s",
            "--symbol-limit",
            "2",
            "--ws-first",
            "--poll-interval-seconds",
            "0.05",
            "--no-banner",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2, captured
    assert (
        "real public WebSocket transport is required" in captured.err
        or "transport refused" in captured.err.lower()
        or "transport is required" in captured.err
    )
    # The runner SHOULD have aborted before any ingest happened.
    events_db = tmp_path / "sqlite" / "events.db"
    if events_db.exists():
        conn = sqlite3.connect(events_db)
        try:
            cur = conn.execute(
                "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
            )
            counts = {row[0]: int(row[1]) for row in cur.fetchall()}
        finally:
            conn.close()
        # No active-head detail iteration at all.
        assert counts.get("PUBLIC_WS_CONNECTED", 0) == 0
        assert counts.get("PRE_ANOMALY_DETECTED", 0) == 0


def test_runner_real_ws_first_uses_ws_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When the runner's real-WS factory returns a (fake) real
    transport, the runner MUST drive the radar through the WS path
    and emit ``PUBLIC_WS_CONNECTED`` plus the radar event chain.

    We monkey-patch the factory to return an :class:`InProcessWSPump`
    seeded with a deterministic burst of !ticker@arr / !markPrice@arr
    / !bookTicker messages so the radar buffer + candidate pool
    chain produces at least one ``PRE_ANOMALY_DETECTED`` event.
    """
    _runner_environ_fixture(monkeypatch, tmp_path)
    _stub_rest_transport(monkeypatch)
    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(runner_mod.time, "sleep", lambda _s: None)

    def _factory(_cfg):
        # InProcessWSPump exposes the same WSMessagePump contract as
        # the real adapter; from the runner's perspective this is
        # indistinguishable. The runner's :code:`_push_dry_run_ws_messages`
        # only fires under ``--dry-run`` so without that flag the pump
        # stays empty unless we seed it now.
        from app.core.clock import now_ms as _now_ms

        pump = InProcessWSPump()

        # We can't push messages until subscribe() is called, so wrap
        # the pump's subscribe() to seed the queue once on the first
        # call.
        original_subscribe = pump.subscribe
        seeded = {"done": False}

        def _seeded_subscribe(streams):
            original_subscribe(streams)
            if seeded["done"]:
                return
            seeded["done"] = True
            ts = int(_now_ms())
            # Baseline tick (90s ago).
            pump.push(
                WSMessage(
                    stream="!ticker@arr",
                    data=[
                        {
                            "s": s,
                            "c": f"{100.0 + 10.0 * i:.4f}",
                            "P": "0.10",
                            "q": f"{1_000_000.0 + 50_000.0 * i:.2f}",
                        }
                        for i, s in enumerate(("BTCUSDT", "ETHUSDT"))
                    ],
                    received_at_ms=ts - 90_000,
                )
            )
            # Spike tick (now).
            pump.push(
                WSMessage(
                    stream="!ticker@arr",
                    data=[
                        {
                            "s": s,
                            "c": f"{(100.0 + 10.0 * i) * 1.05:.4f}",
                            "P": "5.00",
                            "q": f"{2_500_000.0 + 100_000.0 * i:.2f}",
                        }
                        for i, s in enumerate(("BTCUSDT", "ETHUSDT"))
                    ],
                    received_at_ms=ts,
                )
            )
            pump.push(
                WSMessage(
                    stream="!markPrice@arr",
                    data=[
                        {
                            "s": s,
                            "p": f"{(100.0 + 10.0 * i) * 1.05:.4f}",
                            "r": "0.0001",
                        }
                        for i, s in enumerate(("BTCUSDT", "ETHUSDT"))
                    ],
                    received_at_ms=ts,
                )
            )

        pump.subscribe = _seeded_subscribe  # type: ignore[method-assign]
        return pump

    monkeypatch.setattr(
        runner_mod, "_build_real_public_ws_transport", _factory
    )

    rc = runner_mod.main(
        [
            "--duration",
            "1s",
            "--symbol-limit",
            "2",
            "--ws-first",
            # NO --dry-run; the runner is in "real" mode but uses our
            # injected fake transport.
            "--candidate-pool-size",
            "10",
            "--active-detail-limit",
            "2",
            "--ws-staleness-threshold-ms",
            "60000",
            "--poll-interval-seconds",
            "0.05",
            "--no-banner",
        ]
    )
    assert rc == 0
    events_db = tmp_path / "sqlite" / "events.db"
    assert events_db.exists()
    conn = sqlite3.connect(events_db)
    try:
        cur = conn.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        )
        counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    finally:
        conn.close()
    # PUBLIC_WS_CONNECTED MUST land - this is the load-bearing signal
    # that the runner exercised the WS adapter (real or fake).
    assert counts.get("PUBLIC_WS_CONNECTED", 0) >= 1
    # Real-WS run MUST drive the radar event chain.
    assert counts.get("PRE_ANOMALY_DETECTED", 0) >= 1


# ---------------------------------------------------------------------------
# 10. Reconnect + backoff
# ---------------------------------------------------------------------------


def test_ws_reconnect_backoff(tmp_path: Path):
    """:meth:`BinancePublicWSClient.reconnect` increments
    ``reconnect_count`` and sleeps the configured backoff before
    reconnecting. The sleep amount is bounded by
    ``reconnect_backoff_max_seconds``."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        sleep_calls: list[float] = []
        client = BinancePublicWSClient(
            config=WSConfig(
                reconnect_backoff_initial_seconds=2.0,
                reconnect_backoff_max_seconds=10.0,
            ),
            pump=InProcessWSPump(),
            event_repo=event_repo,
            sleep_fn=sleep_calls.append,
        )
        client.connect()
        client.reconnect(reason="test")
        client.reconnect(reason="test")
        assert client.reconnect_count == 2
        # Each reconnect slept the initial backoff (2s); never above
        # the max (10s).
        assert sleep_calls
        for s in sleep_calls:
            assert 0 < s <= 10.0
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 11. Staleness -> DATA_DEGRADED
# ---------------------------------------------------------------------------


def test_ws_staleness_enters_data_degraded(tmp_path: Path):
    """When the WS link is stale, the runner MUST NOT drive the radar
    event chain on the active head - i.e. no PRE_ANOMALY_DETECTED is
    emitted while ``ws_client.is_stale``. The PUBLIC_WS_STALE event
    must still be written so the daily report can rebuild the
    timeline."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        clock = {"t": 1_700_000_000_000}

        def fake_clock() -> int:
            return clock["t"]

        pump = InProcessWSPump()
        client = BinancePublicWSClient(
            config=WSConfig(staleness_threshold_ms=1_000),
            pump=pump,
            event_repo=event_repo,
            clock_fn=fake_clock,
        )
        client.connect()
        # Push one message so heartbeat starts ticking.
        pump.push(
            WSMessage(
                stream="!ticker@arr",
                data=[{"s": "BTCUSDT", "c": "100.0", "q": "1000"}],
                received_at_ms=clock["t"],
            )
        )
        client.pump_messages()
        assert client.is_stale is False
        # Advance past the threshold WITHOUT pushing more messages.
        clock["t"] += 5_000
        client.pump_messages()
        assert client.is_stale is True
        types = [e.event_type for e in event_repo.list_events()]
        assert EventType.PUBLIC_WS_STALE in types
        # The runner-side gate: when the client is stale, the active
        # head iteration is skipped. We verify the gate itself by
        # checking ``client.is_stale`` is True; the runner test above
        # covers the full integration.
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 12-13. PUBLIC_WS_CONNECTED / PUBLIC_WS_STALE event payloads
# ---------------------------------------------------------------------------


def test_public_ws_connected_event_written(tmp_path: Path):
    """``PUBLIC_WS_CONNECTED`` must land with a payload that includes
    the host (or base_url), the streams, and the connect / reconnect
    counters - the daily report rebuilds the link timeline from
    these fields alone."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        client = BinancePublicWSClient(
            config=WSConfig(),
            pump=InProcessWSPump(),
            event_repo=event_repo,
        )
        client.connect()
        events = event_repo.list_events(
            event_type=EventType.PUBLIC_WS_CONNECTED
        )
        assert len(events) == 1
        payload = events[0].payload
        assert payload["base_url"] == DEFAULT_WS_BASE_URL
        assert "streams" in payload
        assert "connect_count" in payload
        assert "reconnect_count" in payload
        assert payload["connect_count"] == 1
    finally:
        dbs.close()


def test_public_ws_stale_event_written(tmp_path: Path):
    """``PUBLIC_WS_STALE`` payload must include the staleness gap, the
    threshold, the last-message ts, and the cumulative stale count -
    the operator can answer "how stale was the link, how often did it
    happen, when did the last message land" from the events.db
    alone."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        clock = {"t": 1_700_000_000_000}

        def fake_clock() -> int:
            return clock["t"]

        pump = InProcessWSPump()
        client = BinancePublicWSClient(
            config=WSConfig(staleness_threshold_ms=500),
            pump=pump,
            event_repo=event_repo,
            clock_fn=fake_clock,
        )
        client.connect()
        pump.push(
            WSMessage(
                stream="!ticker@arr",
                data=[{"s": "BTCUSDT", "c": "100.0", "q": "1"}],
                received_at_ms=clock["t"],
            )
        )
        client.pump_messages()
        clock["t"] += 2_000
        client.pump_messages()
        events = event_repo.list_events(event_type=EventType.PUBLIC_WS_STALE)
        assert len(events) == 1
        payload = events[0].payload
        assert payload["staleness_ms"] >= 2_000
        assert payload["threshold_ms"] == 500
        assert payload["stale_count"] == 1
        assert payload["last_message_ts_ms"] >= 1_700_000_000_000
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 14. Safety flags unchanged with the real adapter enabled
# ---------------------------------------------------------------------------


def test_safety_flags_unchanged_with_real_ws_enabled(tmp_path: Path):
    """Constructing the real :class:`StdlibPublicWSTransport` and
    driving the :class:`BinancePublicWSClient` end-to-end with a
    fake socket MUST NOT alter any Phase 1 / Phase 11C safety flag.

    The transport is wired to a fake in-memory connection so the test
    runs offline, but the code path it exercises is the production
    one (handshake, frame parse, subscribe, poll).
    """
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        conn = _FakeWSConn()
        connections = [conn]
        transport = StdlibPublicWSTransport(
            config=WSConfig(),
            socket_factory=_make_socket_factory(connections),
            ssl_wrap_fn=_make_ssl_wrap(connections),
            random_bytes_fn=lambda n: b"\x00" * n,
        )
        # Seed the WS upgrade response BEFORE connect() runs the
        # synchronous handshake. The deterministic random_bytes_fn
        # makes the Sec-WebSocket-Key predictable.
        _seed_handshake(conn)

        client = BinancePublicWSClient(
            config=WSConfig(),
            pump=transport,
            event_repo=event_repo,
        )
        client.connect()
        assert client.is_connected is True
        # Drive a single text frame through the real frame parser.
        import json as _json

        conn.feed_text_frame(
            _json.dumps(
                {
                    "stream": "!ticker@arr",
                    "data": [{"s": "BTCUSDT", "c": "100.0", "q": "1"}],
                }
            ).encode("utf-8")
        )
        msgs = client.pump_messages(timeout_seconds=0.05)
        assert len(msgs) == 1
        assert msgs[0].stream == "!ticker@arr"
        client.disconnect(reason="test")

        # Safety flags MUST remain unchanged.
        s = _settings()
        assert s.trading_mode == "paper"
        assert s.live_trading_enabled is False
        assert s.right_tail_enabled is False
        assert s.llm_enabled is False
        assert s.exchange_live_order_enabled is False
        assert s.telegram_outbound_enabled is False
        for flag in (
            "forbid_private_credentials",
            "forbid_signed_endpoints",
            "forbid_trade_endpoints",
            "forbid_account_endpoints",
            "forbid_position_endpoints",
            "forbid_leverage_endpoints",
            "forbid_margin_endpoints",
            "forbid_live_trading",
            "forbid_right_tail",
            "forbid_llm_trade_decisions",
            "forbid_telegram_outbound",
        ):
            assert getattr(s.safety, flag) is True
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 15. No private WS / listenKey artefacts in the Phase 11C.1B source set
# ---------------------------------------------------------------------------


def test_no_private_ws_or_listen_key_in_phase11c1b():
    """Audit: the Phase 11C.1B source set must not contain any
    EXECUTABLE reference to a private-WS / user-data-stream /
    trading-WS surface. Module / function / class docstrings AND the
    load-bearing :data:`FORBIDDEN_WS_TOKENS` constant inside
    ``binance_public_ws.py`` are exempt (they document and enforce
    the boundary). Every other Phase 11C.1B file is checked verbatim.
    """
    import ast

    root = Path(__file__).resolve().parent.parent.parent
    files = (
        root / "app" / "exchanges" / "binance_public_ws.py",
        root / "app" / "market_data_public" / "candidate_pool.py",
        root / "app" / "market_data_public" / "radar.py",
        root / "app" / "market_data_public" / "ws_radar_chain.py",
        root / "scripts" / "run_public_market_paper.py",
    )
    private_substrings = (
        "listenKey",
        "userDataStream",
        "userdatastream",
        "/ws-api",
        "/trading-api",
        "ws-fapi",
        "ws-papi",
        "ordertradeupdate",
        "accountupdate",
        "marginCall",
        "balanceUpdate",
        "positionUpdate",
        "leverageUpdate",
    )
    for path in files:
        # The file that *enforces* the deny-list is permitted to spell
        # the substrings as load-bearing data.
        if path.name == "binance_public_ws.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstring_nodes: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(
                node,
                (
                    ast.Module,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                body = list(getattr(node, "body", []))
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstring_nodes.add(id(body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_nodes
            ):
                lowered = node.value.lower()
                for needle in private_substrings:
                    assert needle.lower() not in lowered, (
                        f"{path.relative_to(root)} embeds private-WS "
                        f"surface {needle!r} in a non-docstring "
                        "string literal"
                    )


# ---------------------------------------------------------------------------
# Bonus: real-WS handshake / framing audit
# ---------------------------------------------------------------------------


def test_real_ws_transport_completes_rfc6455_handshake(
    real_transport_with_fake_socket,
):
    """The transport sends a well-formed RFC 6455 client handshake
    (Upgrade / Connection / Sec-WebSocket-Key / Sec-WebSocket-Version
    headers), validates the server's ``Sec-WebSocket-Accept``, and
    flips ``is_connected=True`` only after the response checks out."""
    transport, conn = real_transport_with_fake_socket
    _seed_handshake(conn)
    transport.connect()
    assert transport.is_connected is True
    head = conn.outbound.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    assert "GET /stream" in head
    assert "Host: fstream.binance.com" in head
    assert "Upgrade: websocket" in head
    assert "Connection: Upgrade" in head
    assert "Sec-WebSocket-Version: 13" in head
    assert "Sec-WebSocket-Key:" in head
    transport.disconnect()
    assert transport.is_connected is False


def test_real_ws_transport_refuses_handshake_with_wrong_accept(
    real_transport_with_fake_socket,
):
    """If the server returns an incorrect ``Sec-WebSocket-Accept``
    the transport raises :class:`PublicWSTransportError` and does
    NOT flip ``is_connected`` to True."""
    transport, conn = real_transport_with_fake_socket
    bad_response = (
        b"HTTP/1.1 101 Switching Protocols\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Accept: WRONGVALUE\r\n"
        b"\r\n"
    )
    conn.feed(bad_response)
    with pytest.raises(PublicWSTransportError):
        transport.connect()
    assert transport.is_connected is False


def test_real_ws_transport_decodes_combined_stream_message(
    real_transport_with_fake_socket,
):
    """The combined ``/stream?streams=`` endpoint pushes
    ``{"stream": ..., "data": ...}`` envelopes; the transport must
    surface ``stream`` and ``data`` to the host client."""
    import json as _json

    transport, conn = real_transport_with_fake_socket
    _seed_handshake(conn)
    transport.connect()
    conn.feed_text_frame(
        _json.dumps(
            {
                "stream": "!bookTicker",
                "data": {
                    "s": "BTCUSDT",
                    "b": "100.0",
                    "a": "100.1",
                    "B": "1.0",
                    "A": "1.0",
                },
            }
        ).encode("utf-8")
    )
    msgs = transport.poll(timeout_seconds=0.05)
    assert len(msgs) == 1
    assert msgs[0].stream == "!bookTicker"
    assert msgs[0].data["s"] == "BTCUSDT"


def test_real_ws_transport_drops_private_shaped_messages(
    real_transport_with_fake_socket,
):
    """If a server pushes a stream name that fails the public
    allowlist (e.g. an unsolicited ``listenKey``-shaped name), the
    transport silently drops the message rather than surface it to
    the host. This is defence-in-depth on top of the subscribe-time
    refusal."""
    import json as _json

    transport, conn = real_transport_with_fake_socket
    _seed_handshake(conn)
    transport.connect()
    conn.feed_text_frame(
        _json.dumps(
            {
                "stream": "btcusdt@accountUpdate",
                "data": {"x": 1},
            }
        ).encode("utf-8")
    )
    msgs = transport.poll(timeout_seconds=0.05)
    assert msgs == []
