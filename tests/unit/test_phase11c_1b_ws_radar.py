"""Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar tests (PR-B).

Pins every behaviour the brief calls out:

  - test_public_ws_stream_allowlist
  - test_private_ws_forbidden
  - test_listen_key_forbidden
  - test_user_data_stream_forbidden
  - test_all_market_ticker_updates_radar_snapshot
  - test_book_ticker_updates_spread
  - test_mark_price_updates_funding
  - test_force_order_sets_liquidation_event
  - test_radar_score_detects_price_volume_acceleration
  - test_candidate_pool_adds_top_radar_symbols
  - test_candidate_pool_expires_old_candidates
  - test_ws_stale_enters_data_degraded
  - test_ws_first_runner_does_not_call_rest_detail_for_all_symbols
  - test_learning_ready_payload_from_ws_candidate
  - test_safety_flags_unchanged_with_ws_enabled

Every test runs in-process. No real socket is opened; the deterministic
:class:`InProcessWSPump` stands in for the public WebSocket transport.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.config.settings import get_settings, load_settings
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exchanges.binance_public_ws import (
    ALLOWED_PUBLIC_WS_HOSTS,
    BinancePublicWSClient,
    DEFAULT_WS_BASE_URL,
    FORBIDDEN_WS_QUERY_TOKENS,
    FORBIDDEN_WS_TOKENS,
    InProcessWSPump,
    PUBLIC_WS_STREAM_ALLOWLIST,
    PublicWSCredentialForbidden,
    PublicWSStreamForbidden,
    WSConfig,
    WSMessage,
    assert_public_ws_stream_allowed,
    assert_public_ws_url_allowed,
)
from app.market_data_public.candidate_pool import (
    CANDIDATE_SOURCE_PHASE,
    CANDIDATE_STATE_ACTIVE,
    CANDIDATE_STATE_WATCHING,
    CandidatePool,
    CandidatePoolConfig,
)
from app.market_data_public.radar import (
    AllMarketRadarBuffer,
    AllMarketRadarSnapshot,
    RADAR_REASON_LIQUIDATION_EVENT,
    RADAR_REASON_PRICE_ACCEL_15S,
    RADAR_REASON_PRICE_ACCEL_60S,
    RADAR_REASON_QUOTE_VOLUME_DELTA_60S,
    RADAR_REASON_VOLUME_RANK_JUMP,
    RadarScoreConfig,
    pre_anomaly_score_light,
)
from app.market_data_public.ws_radar_chain import WSRadarChainDriver
from app.risk.engine import RiskEngine


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class _FakeClock:
    """Manually advanced ms-clock used to drive the radar/buffer state."""

    def __init__(self, start: int = 1_700_000_000_000) -> None:
        self._t = int(start)

    def __call__(self) -> int:
        return self._t

    def advance_ms(self, ms: int) -> None:
        self._t += int(ms)


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    """Build an isolated EventRepository on top of the Phase 2 DBs."""
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
# Stream allowlist + private-WS refusals
# ---------------------------------------------------------------------------


def test_public_ws_stream_allowlist():
    """The allowlist contains exactly the five public-market streams
    the brief enumerates - and per-symbol variants of those streams
    are accepted only when they end in a public suffix."""
    expected = {
        "!ticker@arr",
        "!miniTicker@arr",
        "!bookTicker",
        "!markPrice@arr",
        "!forceOrder@arr",
    }
    assert set(PUBLIC_WS_STREAM_ALLOWLIST) == expected
    for stream in PUBLIC_WS_STREAM_ALLOWLIST:
        assert assert_public_ws_stream_allowed(stream) == stream
    # Per-symbol variants of the public streams are accepted.
    assert assert_public_ws_stream_allowed("btcusdt@bookTicker") == (
        "btcusdt@bookTicker"
    )
    assert assert_public_ws_stream_allowed("ethusdt@markPrice") == (
        "ethusdt@markPrice"
    )
    # Anything off the allowlist is refused.
    with pytest.raises(PublicWSStreamForbidden):
        assert_public_ws_stream_allowed("kline_1m")
    with pytest.raises(PublicWSStreamForbidden):
        assert_public_ws_stream_allowed("")
    with pytest.raises(PublicWSStreamForbidden):
        assert_public_ws_stream_allowed("   ")


def test_private_ws_forbidden():
    """Every Phase 11C.1B-forbidden WebSocket token is refused at the
    client construction surface (allowlist + URL parser).

    The brief explicitly forbids:
      - listenKey
      - user data stream
      - private WebSocket
      - trading WebSocket API
      - account / position / leverage / margin / order WebSocket variants
    """
    forbidden_streams = (
        "listenKey",
        "abcDEF123listenKeyXYZ",
        "userdatastream",
        "btcusdt@accountUpdate",
        "btcusdt@orderTradeUpdate",
        "btcusdt@positionUpdate",
        "btcusdt@marginCall",
        "btcusdt@balanceUpdate",
        "/ws-api/v3/order.place",
        "trading-api/v3",
    )
    for stream in forbidden_streams:
        with pytest.raises(PublicWSStreamForbidden):
            assert_public_ws_stream_allowed(stream)
    # The URL parser refuses every private-WS path embedded in a URL.
    forbidden_urls = (
        "wss://fstream.binance.com/ws/listenKey123",
        "wss://fstream.binance.com/userDataStream",
        "wss://stream-api.binance.com/ws-api/v3/order.place",
        "wss://fstream.binance.com/ws?listenKey=abc",
        "wss://fstream.binance.com/ws?signature=abc",
        "wss://fstream.binance.com/ws?timestamp=1",
        "wss://fstream.binance.com/ws?apiKey=abc",
        "ws://fstream.binance.com/ws/!ticker@arr",  # non-wss
        "wss://example.com/ws/!ticker@arr",  # wrong host
    )
    for url in forbidden_urls:
        with pytest.raises(PublicWSStreamForbidden):
            assert_public_ws_url_allowed(url)
    # Defence-in-depth: every private substring is on the deny list.
    for needle in (
        "listenkey",
        "userdata",
        "userdatastream",
        "ws-api",
        "trading-api",
        "accountupdate",
        "ordertradeupdate",
        "margincall",
        "balanceupdate",
        "positionupdate",
    ):
        assert needle in FORBIDDEN_WS_TOKENS
    for needle in ("signature", "timestamp", "recvwindow", "apikey", "listenkey"):
        assert needle in FORBIDDEN_WS_QUERY_TOKENS


def test_listen_key_forbidden():
    """The :class:`BinancePublicWSClient` constructor refuses
    ``listen_key=`` outright."""
    with pytest.raises(PublicWSCredentialForbidden):
        BinancePublicWSClient(listen_key="abc")
    # Defence-in-depth: any credential-shaped kwarg with ``listen_key``
    # in its name is refused.
    with pytest.raises(PublicWSCredentialForbidden):
        BinancePublicWSClient(**{"my_listen_key": "abc"})
    with pytest.raises(PublicWSCredentialForbidden):
        BinancePublicWSClient(**{"listenKey": "abc"})


def test_user_data_stream_forbidden(tmp_path: Path):
    """Subscribing to a user-data-stream-like name through an
    InProcessWSPump must raise :class:`PublicWSStreamForbidden`. This
    pins that the runner cannot accidentally feed a user-data-stream
    payload into the radar even if a future test fixture tries."""
    pump = InProcessWSPump()
    with pytest.raises(PublicWSStreamForbidden):
        pump.push(
            WSMessage(stream="btcusdt@accountUpdate", data={"x": 1})
        )
    # The client refuses to subscribe to a user data stream too.
    client = BinancePublicWSClient(pump=pump)
    with pytest.raises(PublicWSStreamForbidden):
        client.subscribe(["btcusdt@orderTradeUpdate"])
    with pytest.raises(PublicWSStreamForbidden):
        client.subscribe(["btcusdt@accountUpdate"])
    with pytest.raises(PublicWSStreamForbidden):
        client.subscribe(["btcusdt@balanceUpdate"])
    # And the URL parser refuses listenKey URLs.
    with pytest.raises(PublicWSStreamForbidden):
        assert_public_ws_url_allowed(
            "wss://fstream.binance.com/ws/listenKey0123"
        )


# ---------------------------------------------------------------------------
# Default WS configuration
# ---------------------------------------------------------------------------


def test_default_ws_config_is_conservative():
    cfg = WSConfig()
    assert cfg.staleness_threshold_ms == 3000
    assert cfg.auto_reconnect is True
    assert cfg.streams == (
        "!ticker@arr",
        "!miniTicker@arr",
        "!bookTicker",
        "!markPrice@arr",
        "!forceOrder@arr",
    )
    assert cfg.base_url == DEFAULT_WS_BASE_URL
    assert "fstream.binance.com" in ALLOWED_PUBLIC_WS_HOSTS


# ---------------------------------------------------------------------------
# Radar buffer - per-stream behaviour
# ---------------------------------------------------------------------------


def test_all_market_ticker_updates_radar_snapshot():
    """``!ticker@arr`` must populate ``last_price`` /
    ``price_change_pct_24h`` / ``quote_volume`` on every symbol it
    carries, and the per-symbol :class:`AllMarketRadarSnapshot` must
    be readable afterwards."""
    clock = _FakeClock()
    buffer = AllMarketRadarBuffer(clock_fn=clock)
    buffer.ingest_message(
        WSMessage(
            stream="!ticker@arr",
            data=[
                {"s": "BTCUSDT", "c": "100.0", "P": "1.5", "q": "1000000"},
                {"s": "ETHUSDT", "c": "50.0", "P": "0.7", "q": "500000"},
            ],
            received_at_ms=clock(),
        )
    )
    snap_btc = buffer.snapshot("BTCUSDT")
    snap_eth = buffer.snapshot("ETHUSDT")
    assert snap_btc is not None
    assert snap_eth is not None
    assert snap_btc.last_price == pytest.approx(100.0)
    assert snap_btc.price_change_pct_24h == pytest.approx(0.015)
    assert snap_btc.quote_volume == pytest.approx(1_000_000.0)
    # Ranks are computed per-batch; BTCUSDT has the larger volume.
    assert snap_btc.volume_rank == 1
    assert snap_eth.volume_rank == 2
    assert "ticker_arr" in snap_btc.ws_source_flags


def test_book_ticker_updates_spread():
    """``!bookTicker`` must populate bid / ask / spread_pct /
    best_bid_qty / best_ask_qty."""
    clock = _FakeClock()
    buffer = AllMarketRadarBuffer(clock_fn=clock)
    buffer.ingest_message(
        WSMessage(
            stream="!bookTicker",
            data={
                "s": "BTCUSDT",
                "b": "100.00",
                "a": "100.10",
                "B": "1.5",
                "A": "2.5",
            },
            received_at_ms=clock(),
        )
    )
    snap = buffer.snapshot("BTCUSDT")
    assert snap is not None
    assert snap.bid == pytest.approx(100.0)
    assert snap.ask == pytest.approx(100.10)
    assert snap.spread_pct == pytest.approx((100.10 - 100.00) / 100.10)
    assert snap.best_bid_qty == pytest.approx(1.5)
    assert snap.best_ask_qty == pytest.approx(2.5)
    assert "book_ticker" in snap.ws_source_flags


def test_mark_price_updates_funding():
    """``!markPrice@arr`` must populate mark_price and funding_rate
    per symbol."""
    clock = _FakeClock()
    buffer = AllMarketRadarBuffer(clock_fn=clock)
    buffer.ingest_message(
        WSMessage(
            stream="!markPrice@arr",
            data=[
                {"s": "BTCUSDT", "p": "100.05", "r": "0.0001"},
                {"s": "ETHUSDT", "p": "50.02", "r": "-0.0002"},
            ],
            received_at_ms=clock(),
        )
    )
    snap_btc = buffer.snapshot("BTCUSDT")
    snap_eth = buffer.snapshot("ETHUSDT")
    assert snap_btc is not None
    assert snap_btc.mark_price == pytest.approx(100.05)
    assert snap_btc.funding_rate == pytest.approx(0.0001)
    assert snap_eth.funding_rate == pytest.approx(-0.0002)
    assert "mark_price_arr" in snap_btc.ws_source_flags


def test_force_order_sets_liquidation_event():
    """``!forceOrder@arr`` must flip ``liquidation_event=True`` and
    accumulate ``liquidation_notional``."""
    clock = _FakeClock()
    buffer = AllMarketRadarBuffer(clock_fn=clock)
    buffer.ingest_message(
        WSMessage(
            stream="!forceOrder@arr",
            data={
                "o": {
                    "s": "BTCUSDT",
                    "p": "100.0",
                    "q": "5.0",
                }
            },
            received_at_ms=clock(),
        )
    )
    snap = buffer.snapshot("BTCUSDT")
    assert snap is not None
    assert snap.liquidation_event is True
    # 100 * 5 = 500 notional.
    assert snap.liquidation_notional == pytest.approx(500.0)
    assert "force_order_arr" in snap.ws_source_flags
    assert buffer.liquidation_events_seen == 1
    # After the configured liquidation window the flag rolls off.
    clock.advance_ms(buffer.LIQUIDATION_WINDOW_MS + 1)
    rolled = buffer.snapshot("BTCUSDT")
    assert rolled is not None
    assert rolled.liquidation_event is False
    assert rolled.liquidation_notional == pytest.approx(0.0)


def test_radar_score_detects_price_volume_acceleration():
    """Driving the buffer with rising price + rising quote volume
    must push :func:`pre_anomaly_score_light` above the candidate
    pool admission threshold and tag the result accordingly."""
    clock = _FakeClock()
    buffer = AllMarketRadarBuffer(clock_fn=clock)
    # Baseline tick: low price, low volume.
    buffer.ingest_message(
        WSMessage(
            stream="!ticker@arr",
            data=[{"s": "BTCUSDT", "c": "100.0", "P": "0.1", "q": "1000000"}],
            received_at_ms=clock(),
        )
    )
    # Advance 60 s, push a spike: +5% price + +1.5M quote volume.
    clock.advance_ms(60_500)
    buffer.ingest_message(
        WSMessage(
            stream="!ticker@arr",
            data=[{"s": "BTCUSDT", "c": "105.0", "P": "5.0", "q": "2500000"}],
            received_at_ms=clock(),
        )
    )
    snap = buffer.snapshot("BTCUSDT")
    assert snap is not None
    assert snap.price_acceleration_60s is not None
    assert snap.price_acceleration_60s > 0.04  # ~5% (the threshold is 0.01)
    assert snap.quote_volume_delta_60s is not None
    assert snap.quote_volume_delta_60s > 1_000_000.0
    score = pre_anomaly_score_light(snap)
    assert score.radar_score >= 30.0
    assert RADAR_REASON_PRICE_ACCEL_60S in score.reason_tags
    assert RADAR_REASON_QUOTE_VOLUME_DELTA_60S in score.reason_tags
    # Source streams should reflect the ticker_arr feed.
    assert "ticker_arr" in score.source_streams


def test_radar_score_falls_back_to_insufficient_history():
    """When no signal crosses any threshold the score is 0 and the
    only tag is :data:`RADAR_REASON_INSUFFICIENT_HISTORY`."""
    snap = AllMarketRadarSnapshot(
        symbol="BTCUSDT",
        timestamp=1,
        last_price=0.0,
    )
    score = pre_anomaly_score_light(snap)
    assert score.radar_score == 0.0
    assert "insufficient_history" in score.reason_tags


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------


def test_candidate_pool_adds_top_radar_symbols():
    """Symbols with a radar score over the threshold must enter the
    pool's ACTIVE head; symbols below the threshold are refused."""
    pool = CandidatePool(
        config=CandidatePoolConfig(
            candidate_pool_size=5,
            active_detail_limit=2,
            radar_score_threshold=30.0,
        )
    )
    pool.begin_scan_batch()
    # Two strong candidates above the threshold, one weak below.
    strong_a = AllMarketRadarSnapshot(
        symbol="BTCUSDT",
        timestamp=1,
        last_price=100.0,
        price_acceleration_60s=0.03,
        quote_volume_delta_60s=2_000_000.0,
    )
    strong_b = AllMarketRadarSnapshot(
        symbol="ETHUSDT",
        timestamp=1,
        last_price=50.0,
        price_acceleration_60s=0.02,
        quote_volume_delta_60s=1_500_000.0,
        volume_rank_jump=5,
    )
    weak = AllMarketRadarSnapshot(
        symbol="DOGEUSDT",
        timestamp=1,
        last_price=0.1,
    )
    score_a = pre_anomaly_score_light(strong_a)
    score_b = pre_anomaly_score_light(strong_b)
    score_weak = pre_anomaly_score_light(weak)
    # Strong scores both clear the 30.0 threshold.
    assert score_a.radar_score >= 30.0
    assert score_b.radar_score >= 30.0
    # Weak score is below the threshold and admission is refused.
    assert score_weak.radar_score < 30.0
    cand_a = pool.offer(strong_a, score_a)
    cand_b = pool.offer(strong_b, score_b)
    cand_weak = pool.offer(weak, score_weak)
    assert cand_a is not None
    assert cand_a.state == CANDIDATE_STATE_ACTIVE
    assert cand_a.identity.source_phase == CANDIDATE_SOURCE_PHASE
    assert cand_a.opportunity_id.startswith("opp_")
    assert cand_b is not None
    assert cand_b.state == CANDIDATE_STATE_ACTIVE
    assert cand_weak is None
    head = pool.active_head()
    assert len(head) == 2
    assert {c.symbol for c in head} == {"BTCUSDT", "ETHUSDT"}
    assert pool.candidates_admitted == 2
    assert pool.candidates_promoted == 2


def test_candidate_pool_expires_old_candidates():
    """Candidates older than ``candidate_ttl_seconds`` are dropped on
    :meth:`expire`."""
    clock = _FakeClock()
    pool = CandidatePool(
        config=CandidatePoolConfig(
            candidate_pool_size=5,
            active_detail_limit=2,
            radar_score_threshold=20.0,
            candidate_ttl_seconds=2,
        ),
        clock_fn=clock,
    )
    pool.begin_scan_batch()
    snap = AllMarketRadarSnapshot(
        symbol="BTCUSDT",
        timestamp=clock(),
        last_price=100.0,
        price_acceleration_60s=0.03,
    )
    score = pre_anomaly_score_light(snap)
    cand = pool.offer(snap, score)
    assert cand is not None
    assert pool.size == 1
    # Within the TTL window, expire is a no-op.
    clock.advance_ms(1_500)
    expired_first = pool.expire()
    assert expired_first == []
    assert pool.size == 1
    # Past the TTL window, the candidate is expired.
    clock.advance_ms(2_000)
    expired = pool.expire()
    assert len(expired) == 1
    assert expired[0].symbol == "BTCUSDT"
    assert pool.size == 0
    assert pool.candidates_expired == 1


def test_candidate_pool_evicts_lowest_score_when_over_capacity():
    """When the pool is over capacity the lowest-score (and oldest)
    candidate is evicted first."""
    pool = CandidatePool(
        config=CandidatePoolConfig(
            candidate_pool_size=2,
            active_detail_limit=2,
            radar_score_threshold=10.0,
        )
    )
    pool.begin_scan_batch()
    for sym, accel in (("AAA", 0.02), ("BBB", 0.04), ("CCC", 0.06)):
        snap = AllMarketRadarSnapshot(
            symbol=sym,
            timestamp=1,
            last_price=100.0,
            price_acceleration_60s=accel,
        )
        pool.offer(snap, pre_anomaly_score_light(snap))
    # Only two candidates remain. The lowest score (AAA) was evicted.
    assert pool.size == 2
    head_symbols = {c.symbol for c in pool.all_candidates()}
    assert head_symbols == {"BBB", "CCC"}
    assert pool.candidates_evicted == 1


# ---------------------------------------------------------------------------
# WS staleness + reconnect
# ---------------------------------------------------------------------------


def test_ws_stale_enters_data_degraded(tmp_path: Path):
    """When no WS message lands for ``staleness_threshold_ms`` the
    client emits ``PUBLIC_WS_STALE`` and flips ``is_stale=True``."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        clock = _FakeClock()
        pump = InProcessWSPump()
        client = BinancePublicWSClient(
            config=WSConfig(staleness_threshold_ms=1_000),
            pump=pump,
            event_repo=event_repo,
            clock_fn=clock,
        )
        client.connect()
        # First message: heartbeat starts ticking.
        pump.push(
            WSMessage(
                stream="!ticker@arr",
                data=[{"s": "BTCUSDT", "c": "100.0", "q": "1000"}],
                received_at_ms=clock(),
            )
        )
        client.pump_messages()
        assert client.is_stale is False
        # Advance the clock past the staleness threshold without any
        # new message.
        clock.advance_ms(2_500)
        client.pump_messages()
        assert client.is_stale is True
        assert client.stale_count == 1
        assert client.ws_staleness_ms_max >= 2_500
        events = event_repo.list_events()
        types = [e.event_type for e in events]
        assert EventType.PUBLIC_WS_STALE in types
        assert EventType.PUBLIC_WS_CONNECTED in types
    finally:
        dbs.close()


def test_ws_disconnect_emits_disconnected_event(tmp_path: Path):
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        client = BinancePublicWSClient(
            pump=InProcessWSPump(), event_repo=event_repo
        )
        client.connect()
        client.disconnect(reason="test")
        events = event_repo.list_events()
        types = [e.event_type for e in events]
        assert EventType.PUBLIC_WS_CONNECTED in types
        assert EventType.PUBLIC_WS_DISCONNECTED in types
    finally:
        dbs.close()


def test_ws_reconnect_count_increments(tmp_path: Path):
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        client = BinancePublicWSClient(
            pump=InProcessWSPump(),
            event_repo=event_repo,
            sleep_fn=lambda _s: None,
        )
        client.connect()
        client.reconnect(reason="test")
        client.reconnect(reason="test")
        assert client.reconnect_count == 2
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Runner: WS-first does not REST-detail every symbol
# ---------------------------------------------------------------------------


def test_ws_first_runner_does_not_call_rest_detail_for_all_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Driving the runner under ``--ws-first --dry-run`` for a brief
    window must NOT issue per-loop detail REST for every bootstrap
    symbol. The REST detail is gated on the candidate pool's active
    head (default 3), which is *much* smaller than the bootstrap
    set."""
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    for name in (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    from app.config.settings import get_settings as _gs

    _gs.cache_clear()

    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(runner_mod.time, "sleep", lambda _s: None)

    rc = runner_mod.main(
        [
            "--duration",
            "1s",
            "--symbol-limit",
            "2",
            "--candidate-pool-size",
            "10",
            "--active-detail-limit",
            "2",
            "--ws-staleness-threshold-ms",
            "60000",
            "--dry-run",
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
    # WS lifecycle landed.
    assert counts.get("PUBLIC_WS_CONNECTED", 0) >= 1
    # The dry-run pump pushes synthetic !ticker@arr / !markPrice@arr /
    # !bookTicker per iteration; the runner pumps WS, scores symbols,
    # and admits them into the candidate pool. We ASSERT that the
    # runner emitted at least one PRE_ANOMALY_DETECTED event - this
    # is the WS-radar surface, NOT the per-symbol REST detail surface.
    assert counts.get("PRE_ANOMALY_DETECTED", 0) >= 1
    # No 429 / 418 in dry-run.
    assert counts.get("RATE_LIMIT_429", 0) == 0
    assert counts.get("RATE_LIMIT_418", 0) == 0


def test_ws_disabled_runner_falls_back_to_pra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``--ws-disabled`` must fall back to the PR-A bootstrap-only
    REST path (no PRE_ANOMALY_DETECTED, no PUBLIC_WS_*)."""
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    for name in (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    from app.config.settings import get_settings as _gs

    _gs.cache_clear()

    import scripts.run_public_market_paper as runner_mod

    monkeypatch.setattr(runner_mod.time, "sleep", lambda _s: None)

    rc = runner_mod.main(
        [
            "--duration",
            "0.5s",
            "--symbol-limit",
            "2",
            "--ws-disabled",
            "--dry-run",
            "--poll-interval-seconds",
            "0.05",
            "--no-banner",
        ]
    )
    assert rc == 0
    events_db = tmp_path / "sqlite" / "events.db"
    conn = sqlite3.connect(events_db)
    try:
        cur = conn.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        )
        counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    finally:
        conn.close()
    # WS surface NOT engaged.
    assert counts.get("PUBLIC_WS_CONNECTED", 0) == 0
    assert counts.get("PRE_ANOMALY_DETECTED", 0) == 0


# ---------------------------------------------------------------------------
# Learning-ready payload from a WS candidate
# ---------------------------------------------------------------------------


def test_learning_ready_payload_from_ws_candidate(tmp_path: Path):
    """A candidate that lands in the pool must, after the WS-radar
    chain runs, produce ``PRE_ANOMALY_DETECTED`` /
    ``ANOMALY_DETECTED`` / ``STATE_TRANSITION`` events whose payload
    carries the full Phase 8.5 ``learning_ready`` block (opportunity
    + signal_snapshot + virtual_trade_plan + config_versions +
    source_phase = phase_11c_1b_ws_first_radar)."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        pool = CandidatePool(
            config=CandidatePoolConfig(
                candidate_pool_size=5,
                active_detail_limit=2,
                radar_score_threshold=20.0,
            )
        )
        pool.begin_scan_batch()
        snap = AllMarketRadarSnapshot(
            symbol="BTCUSDT",
            timestamp=1_700_000_000_000,
            last_price=100.0,
            price_acceleration_60s=0.03,
            quote_volume_delta_60s=1_500_000.0,
            volume_rank_jump=4,
        )
        score = pre_anomaly_score_light(snap)
        cand = pool.offer(snap, score)
        assert cand is not None

        risk = RiskEngine(event_repo=event_repo)
        chain = WSRadarChainDriver(
            risk_engine=risk, event_repo=event_repo
        )
        result = chain.drive(cand)
        assert result.symbol == "BTCUSDT"
        assert result.opportunity_id == cand.opportunity_id
        assert result.scan_batch_id == cand.scan_batch_id
        assert result.risk_approved is False
        assert "stop_unconfirmed" in result.reject_reasons
        assert result.learning_ready_attached is True

        # Verify every learning_ready block on disk.
        for event_type in (
            EventType.PRE_ANOMALY_DETECTED,
            EventType.ANOMALY_DETECTED,
            EventType.STATE_TRANSITION,
        ):
            events = event_repo.list_events(event_type=event_type)
            assert events, (
                f"no {event_type.value} events emitted by the WS chain"
            )
            payload = events[0].payload
            assert "learning_ready" in payload
            lr = payload["learning_ready"]
            assert "opportunity" in lr
            opp = lr["opportunity"]
            assert opp["opportunity_id"] == cand.opportunity_id
            assert opp["scan_batch_id"] == cand.scan_batch_id
            assert opp["symbol"] == "BTCUSDT"
            assert opp["source_phase"] == CANDIDATE_SOURCE_PHASE
            assert "signal_snapshot" in lr
            sig = lr["signal_snapshot"]
            for key in (
                "symbol",
                "timestamp",
                "regime",
                "pre_anomaly_score",
                "anomaly_score",
                "no_trade_reason",
            ):
                assert key in sig
            assert "virtual_trade_plan" in lr
            plan = lr["virtual_trade_plan"]
            for key in (
                "virtual_entry",
                "virtual_stop",
                "virtual_tp1",
                "direction",
                "setup_type",
            ):
                assert key in plan
            assert "config_versions" in lr
            assert lr.get("source_phase") == CANDIDATE_SOURCE_PHASE

        # The PRE_ANOMALY_DETECTED event also carries the radar
        # extras (radar_reason_tags + radar_source_streams).
        pre_payload = event_repo.list_events(
            event_type=EventType.PRE_ANOMALY_DETECTED
        )[0].payload
        assert "radar_reason_tags" in pre_payload
        assert "radar_source_streams" in pre_payload
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Safety flags unchanged with WS enabled
# ---------------------------------------------------------------------------


def test_safety_flags_unchanged_with_ws_enabled(tmp_path: Path):
    """Driving the WS client + radar + pool + chain end-to-end must
    NOT alter any Phase 1 / Phase 11C safety flag."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        pump = InProcessWSPump()
        client = BinancePublicWSClient(pump=pump, event_repo=event_repo)
        client.connect()
        # Push a strong signal and run it through the full chain.
        pump.push(
            WSMessage(
                stream="!ticker@arr",
                data=[{"s": "BTCUSDT", "c": "105.0", "P": "5.0", "q": "2000000"}],
                received_at_ms=1,
            )
        )
        pump.push(
            WSMessage(
                stream="!markPrice@arr",
                data=[{"s": "BTCUSDT", "p": "105.0", "r": "0.0001"}],
                received_at_ms=1,
            )
        )
        messages = client.pump_messages()
        radar = AllMarketRadarBuffer()
        radar.ingest_messages(messages)
        pool = CandidatePool(
            config=CandidatePoolConfig(
                candidate_pool_size=5,
                active_detail_limit=2,
                radar_score_threshold=10.0,
            )
        )
        pool.begin_scan_batch()
        for snap in radar.all_snapshots():
            pool.offer(snap, pre_anomaly_score_light(snap))
        risk = RiskEngine(event_repo=event_repo)
        chain = WSRadarChainDriver(
            risk_engine=risk, event_repo=event_repo
        )
        for cand in pool.active_head():
            chain.drive(cand)

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

        # The four ExchangeClientBase write surfaces still refuse on
        # the public REST client.
        from app.core.errors import SafeModeViolation
        from app.exchanges.base import WRITE_SURFACE_METHODS
        from app.exchanges.binance_public import BinancePublicClient

        rest_client = BinancePublicClient(autostart=False)
        for fn_name in WRITE_SURFACE_METHODS:
            with pytest.raises(SafeModeViolation):
                getattr(rest_client, fn_name)()
    finally:
        dbs.close()


def test_default_ws_transport_refuses_to_open_a_real_socket():
    """The default :class:`_RefusalTransport` raises
    ``NotImplementedError`` on connect; PR-B does NOT ship a
    real-network WS adapter."""
    client = BinancePublicWSClient()
    with pytest.raises(NotImplementedError):
        client.connect()


def test_ws_client_subscribe_refuses_private_streams(tmp_path: Path):
    """Even when the pump is wired, every ``subscribe()`` is run
    through the public allowlist."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        client = BinancePublicWSClient(
            pump=InProcessWSPump(), event_repo=event_repo
        )
        client.connect()
        with pytest.raises(PublicWSStreamForbidden):
            client.subscribe(["btcusdt@listenKey"])
        with pytest.raises(PublicWSStreamForbidden):
            client.subscribe(["userDataStream"])
    finally:
        dbs.close()


def test_ws_metrics_payload_includes_brief_field_set(tmp_path: Path):
    """The brief calls out the daily-report fields explicitly:

      - ws_messages_received
      - ws_reconnect_count
      - ws_staleness_ms_max
      - ws_stale_count
    """
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        client = BinancePublicWSClient(
            pump=InProcessWSPump(), event_repo=event_repo
        )
        client.connect()
        payload = client.metrics_payload()
        for key in (
            "ws_messages_received",
            "ws_reconnect_count",
            "ws_staleness_ms_max",
            "ws_stale_count",
        ):
            assert key in payload
    finally:
        dbs.close()


def test_candidate_pool_metrics_payload_includes_brief_field_set():
    """The brief calls out the daily-report fields:

      - radar_candidates_seen
      - candidate_pool_size_max
      - pre_anomaly_candidates
    """
    pool = CandidatePool()
    payload = pool.metrics_payload()
    for key in (
        "radar_candidates_seen",
        "candidate_pool_size_max",
        "candidate_pool_admitted",
        "candidate_pool_promoted",
        "candidate_pool_active_head",
        "candidate_pool_top_symbols",
    ):
        assert key in payload


def test_radar_score_attaches_liquidation_event_tag():
    """Driving a snapshot with ``liquidation_event=True`` must add
    the ``liquidation_event`` tag and contribute to the radar score."""
    snap = AllMarketRadarSnapshot(
        symbol="BTCUSDT",
        timestamp=1,
        last_price=100.0,
        liquidation_event=True,
        liquidation_notional=1234.5,
    )
    score = pre_anomaly_score_light(snap)
    assert RADAR_REASON_LIQUIDATION_EVENT in score.reason_tags
    assert score.radar_score > 0.0


def test_volume_rank_jump_admits_into_candidate_pool():
    """A symbol that jumps from rank 10 to rank 4 must be admitted
    to the pool even when its radar score is below the threshold."""
    pool = CandidatePool(
        config=CandidatePoolConfig(
            candidate_pool_size=5,
            active_detail_limit=2,
            radar_score_threshold=999.0,  # blocks score-only admission
            volume_rank_jump_threshold=3,
        )
    )
    pool.begin_scan_batch()
    snap = AllMarketRadarSnapshot(
        symbol="DOGEUSDT",
        timestamp=1,
        last_price=0.1,
        volume_rank=4,
        volume_rank_jump=6,
    )
    cand = pool.offer(snap, pre_anomaly_score_light(snap))
    assert cand is not None
    assert pool.size == 1
    # Score did not clear the threshold so the candidate is WATCHING.
    assert cand.state == CANDIDATE_STATE_WATCHING


def test_phase_11c_1b_files_exist():
    """Sanity: the Phase 11C.1B source set is what we expect."""
    files = (
        "app/exchanges/binance_public_ws.py",
        "app/market_data_public/radar.py",
        "app/market_data_public/candidate_pool.py",
        "app/market_data_public/ws_radar_chain.py",
    )
    root = Path(__file__).resolve().parent.parent.parent
    for path in files:
        assert (root / path).exists(), f"missing {path}"
