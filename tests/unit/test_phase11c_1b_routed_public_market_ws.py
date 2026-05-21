"""Phase 11C.1B - Routed public / market WebSocket endpoint tests.

The Phase 11C.1B brief mandates that PR #32 connect to the documented
Binance USDⓈ-M Futures *routed* public-market WebSocket endpoints

    wss://fstream.binance.com/public/stream?streams=...
    wss://fstream.binance.com/market/stream?streams=...

and never to the *routed-private* surface

    wss://fstream.binance.com/private/...   # FORBIDDEN

The unrouted ``/stream?streams=...`` path is NOT the acceptance path:
Binance silently drops market-class streams (``!markPrice@arr``,
``!ticker@arr`` etc.) over an unrouted connection so a runner that
reports ``PUBLIC_WS_CONNECTED`` against ``/stream`` would in fact
miss most of the radar's data.

This file pins, at the unit level, every behaviour the brief calls
out (and is referenced verbatim by the merge checklist):

  - test_routed_public_ws_path_allowed
  - test_routed_market_ws_path_allowed
  - test_private_routed_ws_forbidden
  - test_unrouted_market_stream_rejected_or_not_used
  - test_mark_price_stream_uses_market_route
  - test_book_ticker_stream_uses_public_route
  - test_multi_transport_ws_manager_merges_public_and_market_messages
  - test_runner_real_ws_first_uses_routed_public_and_market_transports
  - test_no_followup_adapter_stale_text_in_docs_or_help
  - test_safety_flags_unchanged_with_routed_ws
  - test_no_private_ws_listen_key_or_user_data_stream

Every test is offline: the multi-transport manager is exercised
through a deterministic in-process pump (not a real socket), and the
runner test injects the same pump through the
``_build_real_public_ws_transport`` factory hook so no network call
ever fires.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.config.settings import get_settings, load_settings
from app.exchanges.binance_public_ws import (
    ALLOWED_PUBLIC_WS_PATH_ROOTS,
    DEFAULT_WS_BASE_URL,
    FORBIDDEN_WS_PATH_ROOTS,
    LEGACY_UNROUTED_WS_PATH_ROOTS,
    BinancePublicWSClient,
    InProcessWSPump,
    MultiTransportPublicWSManager,
    PublicWSCredentialForbidden,
    PublicWSStreamForbidden,
    StdlibPublicWSTransport,
    WSConfig,
    WSMessage,
    WSMessagePump,
    assert_public_ws_path_allowed,
    classify_stream_route,
    create_real_public_ws_transport,
    split_streams_by_route,
)
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# 1. Routed public path is on the acceptance allowlist
# ---------------------------------------------------------------------------


def test_routed_public_ws_path_allowed():
    """``/public/ws`` and ``/public/stream`` are documented Binance
    routed public-market endpoints and MUST be on the Phase 11C.1B
    acceptance path-root allowlist."""
    assert "public/ws" in ALLOWED_PUBLIC_WS_PATH_ROOTS
    assert "public/stream" in ALLOWED_PUBLIC_WS_PATH_ROOTS
    # The path validator accepts them.
    for path in (
        "/public/ws",
        "/public/stream",
        "/public/ws/btcusdt@bookTicker",
        "/public/stream?streams=!bookTicker",
    ):
        assert assert_public_ws_path_allowed(path) == path
    # And the legacy unrouted roots are NOT the routed acceptance set.
    assert "ws" in LEGACY_UNROUTED_WS_PATH_ROOTS
    assert "stream" in LEGACY_UNROUTED_WS_PATH_ROOTS
    assert "ws" not in ALLOWED_PUBLIC_WS_PATH_ROOTS
    assert "stream" not in ALLOWED_PUBLIC_WS_PATH_ROOTS


# ---------------------------------------------------------------------------
# 2. Routed market path is on the acceptance allowlist
# ---------------------------------------------------------------------------


def test_routed_market_ws_path_allowed():
    """``/market/ws`` and ``/market/stream`` are the documented
    Binance routed market-data endpoints and MUST be on the
    Phase 11C.1B acceptance path-root allowlist."""
    assert "market/ws" in ALLOWED_PUBLIC_WS_PATH_ROOTS
    assert "market/stream" in ALLOWED_PUBLIC_WS_PATH_ROOTS
    for path in (
        "/market/ws",
        "/market/stream",
        "/market/stream?streams=!markPrice@arr/!ticker@arr",
    ):
        assert assert_public_ws_path_allowed(path) == path


# ---------------------------------------------------------------------------
# 3. /private routed surface is FORBIDDEN
# ---------------------------------------------------------------------------


def test_private_routed_ws_forbidden():
    """The Binance routed-private surface is the documented signed /
    user-data channel. Phase 11C.1B refuses it at the path-root
    allowlist AND via the URL parser, regardless of how the caller
    composes the path."""
    assert "private" in FORBIDDEN_WS_PATH_ROOTS
    for path in (
        "/private",
        "/private/ws",
        "/private/stream",
        "/private/stream?streams=!ticker@arr",
        "/private/userDataStream",
        "/PRIVATE/ws",  # case-insensitive
    ):
        with pytest.raises(PublicWSStreamForbidden):
            assert_public_ws_path_allowed(path)
    # Other routed-private / signed surfaces are also blocked.
    for path in (
        "/ws-api/v3/order.place",
        "/ws-fapi/v1/order",
        "/ws-papi/v1/account",
        "/trading-api/v3",
        "/userDataStream",
    ):
        with pytest.raises(PublicWSStreamForbidden):
            assert_public_ws_path_allowed(path)


# ---------------------------------------------------------------------------
# 4. The unrouted production path is NOT the acceptance path
# ---------------------------------------------------------------------------


def test_unrouted_market_stream_rejected_or_not_used():
    """The legacy unrouted ``/stream?streams=`` URL silently drops
    market-class streams (per the Binance public-WS reference). The
    Phase 11C.1B real-network factory returns a
    :class:`MultiTransportPublicWSManager` that ALWAYS opens a
    routed PUBLIC + MARKET pair instead. The unrouted URL is kept
    accepted by :func:`assert_public_ws_path_allowed` only for the
    in-process pump's back-compat fixtures and is NOT the
    acceptance path."""
    cfg = WSConfig()
    pump = create_real_public_ws_transport(config=cfg)
    assert isinstance(pump, MultiTransportPublicWSManager)
    # The manager opened both routes - none of its child transports
    # is unrouted.
    assert set(pump.routes) == {"public", "market"}
    for route, transport in pump.transports.items():
        # Each child is a routed StdlibPublicWSTransport whose URL
        # explicitly carries the route prefix.
        assert isinstance(transport, StdlibPublicWSTransport)
        assert transport.route == route
        # Routed URL: ``wss://<host>/<route>/stream?streams=...``.
        assert transport.url.startswith(
            f"{DEFAULT_WS_BASE_URL}/{route}/stream"
        )
        # The unrouted ``/stream?`` URL is NEVER what the routed
        # transport opened: the route prefix is always present.
        assert (
            f"/{route}/stream" in transport.url
        ), transport.url


# ---------------------------------------------------------------------------
# 5. Stream classification: market route
# ---------------------------------------------------------------------------


def test_mark_price_stream_uses_market_route():
    """``!markPrice@arr`` (and per-symbol ``btcusdt@markPrice``) is a
    MARKET-route stream per the Binance USDⓈ-M Futures public-WS
    reference. Same for ``!ticker@arr`` / ``!miniTicker@arr`` /
    ``!forceOrder@arr``."""
    for stream in (
        "!ticker@arr",
        "!miniTicker@arr",
        "!markPrice@arr",
        "!forceOrder@arr",
        "btcusdt@markPrice",
        "ethusdt@ticker",
        "btcusdt@miniTicker",
        "btcusdt@forceOrder",
    ):
        assert classify_stream_route(stream) == "market"
    # split_streams_by_route routes the canonical five-stream set
    # the same way.
    split = split_streams_by_route(
        (
            "!ticker@arr",
            "!miniTicker@arr",
            "!bookTicker",
            "!markPrice@arr",
            "!forceOrder@arr",
        )
    )
    assert set(split["market"]) == {
        "!ticker@arr",
        "!miniTicker@arr",
        "!markPrice@arr",
        "!forceOrder@arr",
    }
    # Manager opened a market-route StdlibPublicWSTransport.
    pump = create_real_public_ws_transport(config=WSConfig())
    assert isinstance(pump, MultiTransportPublicWSManager)
    market = pump.transports["market"]
    assert isinstance(market, StdlibPublicWSTransport)
    assert market.route == "market"
    assert "/market/stream" in market.url
    assert "!markPrice%40arr" in market.url or "!markPrice@arr" in market.url


# ---------------------------------------------------------------------------
# 6. Stream classification: public route
# ---------------------------------------------------------------------------


def test_book_ticker_stream_uses_public_route():
    """``!bookTicker`` (best bid / ask) is a PUBLIC-route stream."""
    assert classify_stream_route("!bookTicker") == "public"
    assert classify_stream_route("btcusdt@bookTicker") == "public"
    split = split_streams_by_route(("!bookTicker", "btcusdt@bookTicker"))
    assert set(split["public"]) == {"!bookTicker", "btcusdt@bookTicker"}
    assert split["market"] == []
    # Manager opened a public-route transport.
    pump = create_real_public_ws_transport(config=WSConfig())
    assert isinstance(pump, MultiTransportPublicWSManager)
    public = pump.transports["public"]
    assert isinstance(public, StdlibPublicWSTransport)
    assert public.route == "public"
    assert "/public/stream" in public.url
    assert (
        "!bookTicker" in public.url or "%21bookTicker" in public.url
    )


# ---------------------------------------------------------------------------
# 7. MultiTransportPublicWSManager merges PUBLIC + MARKET messages
# ---------------------------------------------------------------------------


class _FakeTransportFactory:
    """Hand back deterministic :class:`InProcessWSPump` adapters
    keyed by route. Mirrors the real factory signature so the
    manager can be exercised offline."""

    def __init__(self) -> None:
        self.public_pump = InProcessWSPump()
        self.market_pump = InProcessWSPump()
        self._by_route = {
            "public": self.public_pump,
            "market": self.market_pump,
        }
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __call__(self, cfg: WSConfig, route: str) -> WSMessagePump:
        self.calls.append((route, tuple(cfg.streams)))
        return self._by_route[route]


def test_multi_transport_ws_manager_merges_public_and_market_messages():
    """The manager opens one transport per route, accepts subscribes
    on the union, drains both routes on :meth:`poll`, and exposes
    per-route counters via :meth:`metrics_payload`."""
    factory = _FakeTransportFactory()
    cfg = WSConfig()
    manager = MultiTransportPublicWSManager(
        config=cfg,
        transport_factory=factory,
    )
    # The manager partitioned the canonical five-stream config into
    # one PUBLIC and four MARKET streams.
    assert set(manager.public_streams) == {"!bookTicker"}
    assert set(manager.market_streams) == {
        "!ticker@arr",
        "!miniTicker@arr",
        "!markPrice@arr",
        "!forceOrder@arr",
    }
    # The factory was called once per route with the route-restricted
    # subset.
    factory_routes = {route for route, _ in factory.calls}
    assert factory_routes == {"public", "market"}
    factory_streams_by_route = {route: streams for route, streams in factory.calls}
    assert set(factory_streams_by_route["public"]) == {"!bookTicker"}
    assert set(factory_streams_by_route["market"]) == {
        "!ticker@arr",
        "!miniTicker@arr",
        "!markPrice@arr",
        "!forceOrder@arr",
    }
    # Connect lifts every child + flips is_connected to True.
    manager.connect()
    assert manager.is_connected is True
    assert factory.public_pump.is_connected
    assert factory.market_pump.is_connected
    # Push messages on each route. The manager drains them in
    # PUBLIC-first, MARKET-second order on poll().
    factory.public_pump.push(
        WSMessage(
            stream="!bookTicker",
            data={
                "s": "BTCUSDT",
                "b": "100.0",
                "a": "100.1",
                "B": "1.0",
                "A": "1.0",
            },
        )
    )
    factory.market_pump.push(
        WSMessage(
            stream="!markPrice@arr",
            data=[{"s": "BTCUSDT", "p": "100.05", "r": "0.0001"}],
        )
    )
    factory.market_pump.push(
        WSMessage(
            stream="!ticker@arr",
            data=[{"s": "BTCUSDT", "c": "100.0", "q": "1000.0"}],
        )
    )
    merged = manager.poll(timeout_seconds=0.0)
    streams = [m.stream for m in merged]
    assert streams == ["!bookTicker", "!markPrice@arr", "!ticker@arr"]
    # Per-route counters track what landed.
    assert manager.messages_received_by_route["public"] == 1
    assert manager.messages_received_by_route["market"] == 2
    # Metrics payload is JSON-safe and includes the per-route URLs
    # (None here because the in-process pump exposes no URL).
    metrics = manager.metrics_payload()
    assert set(metrics["ws_routes_opened"]) == {"public", "market"}
    assert metrics["ws_messages_by_route"] == {"public": 1, "market": 2}
    assert metrics["ws_public_streams"] == ["!bookTicker"]
    assert sorted(metrics["ws_market_streams"]) == [
        "!forceOrder@arr",
        "!markPrice@arr",
        "!miniTicker@arr",
        "!ticker@arr",
    ]
    # Disconnect tears every child down + flips is_connected back.
    manager.disconnect()
    assert manager.is_connected is False
    assert factory.public_pump.is_connected is False
    assert factory.market_pump.is_connected is False


def test_multi_transport_ws_manager_subscribe_routes_to_correct_transport():
    """A mid-run :meth:`subscribe` of new streams routes each stream
    to its proper child transport. Nothing leaks to the wrong route."""
    factory = _FakeTransportFactory()
    manager = MultiTransportPublicWSManager(
        config=WSConfig(streams=("!bookTicker", "!markPrice@arr")),
        transport_factory=factory,
    )
    manager.connect()
    manager.subscribe(["btcusdt@bookTicker", "ethusdt@markPrice"])
    assert "btcusdt@bookTicker" in factory.public_pump.subscribed_streams
    assert "ethusdt@markPrice" in factory.market_pump.subscribed_streams
    # The reverse never holds.
    assert (
        "ethusdt@markPrice"
        not in factory.public_pump.subscribed_streams
    )
    assert (
        "btcusdt@bookTicker"
        not in factory.market_pump.subscribed_streams
    )


def test_multi_transport_ws_manager_refuses_credentials():
    """The manager refuses every credential-shaped kwarg at
    construction time, exactly like
    :class:`StdlibPublicWSTransport`."""
    for kwarg in (
        "api_key",
        "api_secret",
        "secret",
        "token",
        "signature",
        "passphrase",
        "apiKey",
        "binance_api_key",
        "listenKey",
    ):
        with pytest.raises(PublicWSCredentialForbidden):
            MultiTransportPublicWSManager(**{kwarg: "x"})
    # And ``create_real_public_ws_transport`` propagates the same
    # refusal because it forwards kwargs unchanged.
    with pytest.raises(PublicWSCredentialForbidden):
        create_real_public_ws_transport(api_key="x")


def test_multi_transport_ws_manager_refuses_private_streams_at_construction():
    """If a caller hand-builds a :class:`WSConfig` whose ``streams``
    list contains a private / listenKey / user-data surface (which
    would already fail :func:`assert_public_ws_stream_allowed`), the
    manager re-runs the allowlist via
    :func:`split_streams_by_route` and refuses BEFORE any socket is
    opened."""
    # WSConfig itself refuses these in __post_init__, so we craft
    # a config first with only public streams and then confirm the
    # manager surface refuses any subscribe attempt that smuggles
    # one in mid-run.
    factory = _FakeTransportFactory()
    manager = MultiTransportPublicWSManager(
        config=WSConfig(),
        transport_factory=factory,
    )
    manager.connect()
    for forbidden in (
        "btcusdt@accountUpdate",
        "btcusdt@orderTradeUpdate",
        "userDataStream",
        "listenKey",
        "btcusdt@positionUpdate",
        "btcusdt@balanceUpdate",
        "btcusdt@marginCall",
        "btcusdt@leverageUpdate",
    ):
        with pytest.raises(PublicWSStreamForbidden):
            manager.subscribe([forbidden])


# ---------------------------------------------------------------------------
# 8. Runner: --ws-first without --dry-run uses BOTH routes
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
    get_settings.cache_clear()


def _stub_rest_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(
        runner_mod,
        "_build_rest_transport",
        lambda *, dry_run: runner_mod._build_dry_run_transport(),
    )


def test_runner_real_ws_first_uses_routed_public_and_market_transports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When the runner is invoked with ``--ws-first`` but without
    ``--dry-run``, the factory MUST hand it a real-shaped pump that
    opens BOTH the routed public AND routed market transports. The
    runner MUST drive the radar through the merged stream and emit
    the Phase 11C event chain.

    We monkey-patch the factory to return a
    :class:`MultiTransportPublicWSManager` whose two child pumps are
    in-process so no real network is touched. The test asserts that
    both routes were opened, both routes received their proper
    streams, and that PUBLIC_WS_CONNECTED + PRE_ANOMALY_DETECTED
    landed in events.db.
    """
    _runner_environ_fixture(monkeypatch, tmp_path)
    _stub_rest_transport(monkeypatch)
    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(runner_mod.time, "sleep", lambda _s: None)

    seen_factory_calls: list[tuple[str, tuple[str, ...]]] = []
    captured_manager: dict[str, MultiTransportPublicWSManager] = {}

    def _factory(cfg: WSConfig):
        from app.core.clock import now_ms as _now_ms

        # Per-route in-process pumps. We pre-seed them with a burst
        # of messages so the radar buffer + candidate pool can fire
        # at least one PRE_ANOMALY_DETECTED chain on a fresh DB.
        public_pump = InProcessWSPump()
        market_pump = InProcessWSPump()

        def _record(c: WSConfig, route: str):
            seen_factory_calls.append((route, tuple(c.streams)))
            return {
                "public": public_pump,
                "market": market_pump,
            }[route]

        manager = MultiTransportPublicWSManager(
            config=cfg, transport_factory=_record
        )

        original_subscribe = manager.subscribe
        seeded = {"done": False}

        def _seeded_subscribe(streams):
            original_subscribe(streams)
            if seeded["done"]:
                return
            seeded["done"] = True
            ts = int(_now_ms())
            # Baseline + spike on the MARKET route (ticker / mark).
            market_pump.push(
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
            market_pump.push(
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
            market_pump.push(
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
            # Best bid / ask on the PUBLIC route.
            for i, s in enumerate(("BTCUSDT", "ETHUSDT")):
                ref = (100.0 + 10.0 * i) * 1.05
                public_pump.push(
                    WSMessage(
                        stream="!bookTicker",
                        data={
                            "s": s,
                            "b": f"{ref:.4f}",
                            "a": f"{ref + 0.05:.4f}",
                            "B": "1.0",
                            "A": "1.0",
                        },
                        received_at_ms=ts,
                    )
                )

        manager.subscribe = _seeded_subscribe  # type: ignore[method-assign]
        captured_manager["m"] = manager
        return manager

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
    # The factory was called for BOTH routes (sub-factory inside
    # the manager was invoked once per route at construction time).
    factory_routes = {route for route, _ in seen_factory_calls}
    assert factory_routes == {"public", "market"}
    factory_streams_by_route = dict(seen_factory_calls)
    assert set(factory_streams_by_route["public"]) == {"!bookTicker"}
    assert set(factory_streams_by_route["market"]) == {
        "!ticker@arr",
        "!miniTicker@arr",
        "!markPrice@arr",
        "!forceOrder@arr",
    }
    # The manager exposed both routes after construction.
    manager = captured_manager["m"]
    assert set(manager.routes) == {"public", "market"}
    # And the runner wrote PUBLIC_WS_CONNECTED + PRE_ANOMALY_DETECTED.
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
    assert counts.get("PUBLIC_WS_CONNECTED", 0) >= 1
    assert counts.get("PRE_ANOMALY_DETECTED", 0) >= 1


# ---------------------------------------------------------------------------
# 9. No stale "follow-up adapter" wording in code or runner help
# ---------------------------------------------------------------------------


def test_no_followup_adapter_stale_text_in_docs_or_help():
    """The Phase 11C.1B brief requires that PR #32 ship the real
    routed WebSocket adapter inline. Any "follow-up adapter" /
    "Phase 11C.1B does NOT ship a real WS" / "real-network WS adapter
    ships in a follow-up PR" wording in the load-bearing source files
    (the WS module, the runner, and the WS-first acceptance docs)
    is therefore wrong and MUST NOT appear.

    We scan for the brief-flagged phrases verbatim. The check is
    deliberately tight (substrings, lowercased) so a future doc
    refactor can't sneak the wording back in.
    """
    root = Path(__file__).resolve().parent.parent.parent
    files = (
        root / "app" / "exchanges" / "binance_public_ws.py",
        root / "scripts" / "run_public_market_paper.py",
        root / "docs" / "PROJECT_STATUS.md",
        root / "docs" / "PHASE_GATE.md",
        root / "docs" / "PHASE_11C_PUBLIC_MARKET_READONLY.md",
        root / "docs" / "CHANGELOG.md",
    )
    forbidden_phrases = (
        "phase 11c.1b does not ship a real ws",
        "real-network ws adapter ships in a follow-up pr",
        "real ws adapter is a phase 11c.1b follow-up",
        "wait for the follow-up pr that ships a stdlib ws",
        "follow-up adapter",
        "pr-b-followup",
    )
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden_phrases:
            assert phrase not in text, (
                f"{path.relative_to(root)} still contains the stale "
                f"phrase {phrase!r}; PR #32 ships the real routed WS "
                "adapter inline and this wording must be removed."
            )


# ---------------------------------------------------------------------------
# 10. Safety flags unchanged with the routed WS manager enabled
# ---------------------------------------------------------------------------


def test_safety_flags_unchanged_with_routed_ws(tmp_path: Path):
    """Constructing the :class:`MultiTransportPublicWSManager` and
    driving the :class:`BinancePublicWSClient` end-to-end through it
    MUST NOT alter any Phase 1 / Phase 11C safety flag.

    The manager is wired to two in-process pumps so the test runs
    offline; the code path it exercises is the production one
    (construct, connect every route, subscribe per route, pump,
    disconnect)."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        factory = _FakeTransportFactory()
        manager = MultiTransportPublicWSManager(
            config=WSConfig(),
            transport_factory=factory,
        )
        client = BinancePublicWSClient(
            config=WSConfig(),
            pump=manager,
            event_repo=event_repo,
        )
        client.connect()
        assert client.is_connected is True
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
        client.disconnect(reason="test")
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 11. No private WS / listenKey / user-data artefacts under routed mode
# ---------------------------------------------------------------------------


def test_no_private_ws_listen_key_or_user_data_stream():
    """Even when the routed PUBLIC + MARKET endpoints are wired, no
    file in the Phase 11C.1B source set may *use* a routed-private
    surface, listenKey, user-data stream, or trading-WS API. The
    audit:

      - rejects a stream whose name embeds ``listenKey`` /
        ``userDataStream`` / ``ws-api`` / ``trading-api`` /
        ``accountUpdate`` / ``orderTradeUpdate`` / ``marginCall`` /
        ``balanceUpdate`` / ``positionUpdate`` / ``leverageUpdate``;
      - rejects a URL that opens the routed-private endpoint
        ``wss://fstream.binance.com/private``;
      - rejects a kwarg shaped like a private credential
        (``api_key`` / ``listen_key`` / ``token`` / ``signature``);
      - rejects a manager constructed with one of those kwargs.
    """
    private_streams = (
        "btcusdt@accountUpdate",
        "btcusdt@orderTradeUpdate",
        "btcusdt@balanceUpdate",
        "btcusdt@positionUpdate",
        "btcusdt@marginCall",
        "btcusdt@leverageUpdate",
        "userDataStream",
        "listenKey",
        "ws-api/v3/order.place",
        "trading-api/v3/order",
    )
    for stream in private_streams:
        with pytest.raises(PublicWSStreamForbidden):
            classify_stream_route(stream)
    # Routed-private URL is refused at the URL parser level.
    from app.exchanges.binance_public_ws import (
        assert_public_ws_url_allowed,
    )

    for url in (
        "wss://fstream.binance.com/private",
        "wss://fstream.binance.com/private/ws",
        "wss://fstream.binance.com/private/stream?streams=!ticker@arr",
        "wss://fstream.binance.com/userDataStream",
        "wss://fstream.binance.com/ws-api/v3/order.place",
    ):
        with pytest.raises(PublicWSStreamForbidden):
            assert_public_ws_url_allowed(url)
    # Manager refuses listenKey / api_key kwargs even if the stream
    # set is otherwise valid.
    for kwarg in ("api_key", "api_secret", "listen_key", "listenKey"):
        with pytest.raises(PublicWSCredentialForbidden):
            MultiTransportPublicWSManager(**{kwarg: "x"})
    # Default factory propagates the refusal.
    with pytest.raises(PublicWSCredentialForbidden):
        create_real_public_ws_transport(listen_key="abc")
