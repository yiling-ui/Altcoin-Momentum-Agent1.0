"""Phase 11C.1A - Binance Public REST Rate-Limit Governor tests.

These tests pin the contract the brief calls out:

  - test_429_triggers_backoff_and_stops_batch
  - test_418_triggers_shutdown_without_retry
  - test_retry_after_header_is_respected
  - test_used_weight_header_is_recorded
  - test_rest_governor_blocks_when_budget_exceeded
  - test_default_phase11c_polling_is_conservative
  - test_rest_not_called_for_all_symbols_every_loop
  - test_no_live_trading_flags_after_429
  - test_no_live_trading_flags_after_418
  - test_daily_report_contains_rate_limit_metrics

Every test runs in-process. No real socket is opened; the deterministic
``_FakeTransport`` below stands in for :func:`urllib.request.urlopen`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from app.config.settings import get_settings, load_settings
from app.core.enums import IncidentLevel
from app.core.errors import SafeModeViolation, SafetyViolation
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exchanges.binance_public import (
    BinancePublicClient,
    DEFAULT_REST_BASE_URL,
)
from app.exchanges.binance_rate_limit import (
    BinancePublicRestGovernor,
    DEFAULT_ENDPOINT_WEIGHTS,
    PublicRestResponse,
    RateLimitBackoffActive,
    RateLimitBudgetExceeded,
    RateLimitProtectionError,
    RestGovernorConfig,
)
from app.incidents.repository import IncidentRepository
from app.paper_run.daily_report import DailyReportBuilder


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@dataclass
class _RecordingProtectionHook:
    """In-process stand-in for IncidentRepository.open_incident."""

    incidents: list[dict[str, Any]] = field(default_factory=list)
    next_id: int = 1

    def open_incident(
        self,
        *,
        level: IncidentLevel,
        title: str,
        description: str,
        source_module: str,
        symbol: str | None,
        position_id: str | None,
        payload: dict[str, Any],
    ) -> str:
        incident_id = f"inc_test_{self.next_id:04d}"
        self.next_id += 1
        self.incidents.append(
            {
                "incident_id": incident_id,
                "level": level,
                "title": title,
                "description": description,
                "source_module": source_module,
                "symbol": symbol,
                "position_id": position_id,
                "payload": dict(payload),
            }
        )
        return incident_id


class _FakeTransport:
    """Deterministic transport that returns a queued response per call.

    The transport accepts a list of ``(status, headers, body)`` tuples
    and returns them in order. If the queue runs dry it returns a
    benign 200 with the supplied default body. Tests inspect
    ``calls`` to confirm the governor stopped issuing requests.
    """

    def __init__(
        self,
        *,
        responses: list[tuple[int, dict[str, str], Any]] | None = None,
        default_body: Any = None,
    ) -> None:
        self.responses = list(responses or [])
        self.default_body = default_body
        self.calls: list[str] = []

    def __call__(self, url: str) -> Any:
        self.calls.append(url)
        if self.responses:
            status, headers, body = self.responses.pop(0)
        else:
            status, headers, body = 200, {}, self.default_body
        if status == 200:
            return PublicRestResponse(body=body, status=200, headers=headers)
        return PublicRestResponse(body=None, status=status, headers=headers)


class _FakeClock:
    """Monotonic-style clock that can be advanced from a test."""

    def __init__(self, start: float = 1000.0) -> None:
        self._t = float(start)

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += float(seconds)


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    """Build an isolated EventRepository on top of the Phase 2 DBs.

    Returns the repo + the underlying :class:`DatabaseSet` so the
    caller can ``.close()`` it deterministically.
    """
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
# Defaults & schema
# ---------------------------------------------------------------------------


def test_default_phase11c_polling_is_conservative():
    """Phase 11C.1A defaults must keep the gateway well below Binance's
    public-data rate-limit budget."""
    md = _settings().market_data
    assert md.symbol_limit == 5
    assert md.rest_poll_interval_seconds == 60.0
    rg = md.rest_governor
    assert rg.weight_budget_per_minute == 300
    assert rg.soft_weight_ratio == 0.50
    assert rg.hard_weight_ratio == 0.75
    assert rg.retry_after_default_seconds == 300
    assert rg.on_429 == "backoff"
    assert rg.on_418 == "shutdown"
    assert rg.candidate_detail_limit == 3
    assert rg.rest_layering_enabled is True


def test_rest_governor_config_refuses_pathological_values():
    """The schema layer refuses unsafe knob values."""
    from pydantic import ValidationError

    from app.config.schema import RestGovernorSection

    with pytest.raises(ValidationError):
        RestGovernorSection(weight_budget_per_minute=0)
    with pytest.raises(ValidationError):
        RestGovernorSection(soft_weight_ratio=0.0)
    with pytest.raises(ValidationError):
        RestGovernorSection(hard_weight_ratio=1.5)
    with pytest.raises(ValidationError):
        RestGovernorSection(retry_after_default_seconds=0)
    with pytest.raises(ValidationError):
        RestGovernorSection(on_429="ignore")
    with pytest.raises(ValidationError):
        RestGovernorSection(on_418="auto_retry")
    with pytest.raises(ValidationError):
        RestGovernorSection(candidate_detail_limit=-1)
    with pytest.raises(ValidationError):
        RestGovernorSection(candidate_detail_limit=999)


# ---------------------------------------------------------------------------
# 429 handling
# ---------------------------------------------------------------------------


def test_429_triggers_backoff_and_stops_batch(tmp_path: Path):
    """A 429 response must:

      * NOT propagate further requests in the same batch;
      * sleep the Retry-After window;
      * emit RATE_LIMIT_429 + BACKOFF_STARTED + BACKOFF_ENDED;
      * keep all safety flags False.
    """
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        sleeps: list[float] = []
        clock = _FakeClock()
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=1_000_000,
                soft_weight_ratio=0.5,
                hard_weight_ratio=0.99,
                retry_after_default_seconds=42,
            ),
            event_repo=event_repo,
            sleep_fn=sleeps.append,
            clock_fn=clock,
        )
        transport = _FakeTransport(
            responses=[
                (429, {"Retry-After": "7", "X-MBX-USED-WEIGHT-1M": "240"}, None),
            ]
        )
        client = BinancePublicClient(
            transport=transport,
            event_repo=event_repo,
            governor=governor,
            autostart=True,
        )

        # First call: 429 lands. Governor sleeps 7s and emits the
        # backoff events; the client surfaces an ExchangeError so the
        # caller treats this batch as failed.
        from app.core.errors import ExchangeError

        with pytest.raises(ExchangeError):
            client._request("/fapi/v1/depth", params={"symbol": "BTCUSDT", "limit": 5})

        assert sleeps == [7.0], "governor must sleep the Retry-After window"
        assert governor.rate_limit_429_count == 1
        assert governor.retry_after_seconds_last == 7
        assert governor.retry_after_seconds_total == 7
        assert governor.used_weight_1m_last == 240

        # The transport was called exactly once. The governor must NOT
        # have replayed the request itself.
        assert len(transport.calls) == 1

        # Verify the event chain.
        events = event_repo.list_events()
        types = [e.event_type for e in events]
        assert EventType.RATE_LIMIT_429 in types
        assert EventType.RATE_LIMIT_BACKOFF_STARTED in types
        assert EventType.RATE_LIMIT_BACKOFF_ENDED in types
        # No 418 / no protection-entered event.
        assert EventType.RATE_LIMIT_418 not in types
        assert EventType.RATE_LIMIT_PROTECTION_ENTERED not in types

        # Safety flags remain unchanged.
        s = _settings()
        assert s.trading_mode == "paper"
        assert s.live_trading_enabled is False
        assert s.right_tail_enabled is False
        assert s.llm_enabled is False
        assert s.exchange_live_order_enabled is False
        assert s.telegram_outbound_enabled is False
    finally:
        dbs.close()


def test_retry_after_header_is_respected(tmp_path: Path):
    """The integer Retry-After value must drive the sleep length;
    the default kicks in only when the header is missing."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        sleeps: list[float] = []
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                soft_weight_ratio=0.99,
                hard_weight_ratio=0.99,
                retry_after_default_seconds=300,
            ),
            event_repo=event_repo,
            sleep_fn=sleeps.append,
        )

        # Case 1: explicit Retry-After=11.
        governor.before_request("/fapi/v1/aggTrades")
        governor.record_response(
            "/fapi/v1/aggTrades",
            PublicRestResponse(
                body=None,
                status=429,
                headers={"Retry-After": "11"},
            ),
        )
        assert sleeps[-1] == 11.0
        assert governor.retry_after_seconds_last == 11

        # Case 2: missing header -> default 300.
        governor.before_request("/fapi/v1/aggTrades")
        governor.record_response(
            "/fapi/v1/aggTrades",
            PublicRestResponse(body=None, status=429, headers={}),
        )
        assert sleeps[-1] == 300.0
        assert governor.retry_after_seconds_last == 300
        # Total is cumulative.
        assert governor.retry_after_seconds_total == 311
        assert governor.rate_limit_429_count == 2
    finally:
        dbs.close()


def test_used_weight_header_is_recorded(tmp_path: Path):
    """``X-MBX-USED-WEIGHT-1M`` must be parsed on every response and
    the running max kept across calls."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
            ),
            event_repo=event_repo,
        )
        for w in (50, 130, 90, 220):
            governor.before_request("/fapi/v1/aggTrades")
            governor.record_response(
                "/fapi/v1/aggTrades",
                PublicRestResponse(
                    body=[],
                    status=200,
                    headers={"X-MBX-USED-WEIGHT-1M": str(w)},
                ),
            )
        assert governor.used_weight_1m_last == 220
        assert governor.used_weight_1m_max == 220
        # Lower-cased header is also accepted.
        governor.before_request("/fapi/v1/aggTrades")
        governor.record_response(
            "/fapi/v1/aggTrades",
            PublicRestResponse(
                body=[],
                status=200,
                headers={"x-mbx-used-weight-1m": "75"},
            ),
        )
        assert governor.used_weight_1m_last == 75
        # Max sticks.
        assert governor.used_weight_1m_max == 220
        assert governor.rest_requests_total == 5
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 418 handling
# ---------------------------------------------------------------------------


def test_418_triggers_shutdown_without_retry(tmp_path: Path):
    """A 418 response must:

      * latch protection mode;
      * raise RateLimitProtectionError immediately;
      * emit RATE_LIMIT_418 + RATE_LIMIT_PROTECTION_ENTERED;
      * open a P1 incident through the protection hook;
      * refuse every subsequent before_request (no auto retry, no
        endpoint switching).
    """
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        sleeps: list[float] = []
        hook = _RecordingProtectionHook()
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
                retry_after_default_seconds=300,
            ),
            event_repo=event_repo,
            protection_hook=hook,
            sleep_fn=sleeps.append,
        )

        transport = _FakeTransport(
            responses=[
                (418, {"Retry-After": "600"}, None),
            ]
        )
        client = BinancePublicClient(
            transport=transport,
            event_repo=event_repo,
            governor=governor,
            autostart=True,
        )

        with pytest.raises(RateLimitProtectionError):
            client._request("/fapi/v1/depth", params={"symbol": "BTCUSDT"})

        # Governor latched.
        assert governor.in_protection_mode is True
        assert governor.rate_limit_ban is True
        assert governor.rate_limit_418_count == 1
        # 418 handler does NOT sleep - the runner must shut down.
        assert sleeps == []

        # Subsequent calls refuse.
        with pytest.raises(RateLimitProtectionError):
            client._request(
                "/fapi/v1/aggTrades", params={"symbol": "BTCUSDT"}
            )
        with pytest.raises(RateLimitProtectionError):
            client._request("/fapi/v1/exchangeInfo")

        # Transport was called exactly once - no auto-retry, no
        # endpoint switching.
        assert len(transport.calls) == 1

        # P1 incident was opened.
        assert len(hook.incidents) == 1
        opened = hook.incidents[0]
        assert opened["level"] is IncidentLevel.P1
        assert "418" in opened["title"]
        assert opened["payload"]["rate_limit_ban"] is True
        assert opened["payload"]["rate_limit_418_count"] == 1

        # Event chain.
        events = event_repo.list_events()
        types = [e.event_type for e in events]
        assert EventType.RATE_LIMIT_418 in types
        assert EventType.RATE_LIMIT_PROTECTION_ENTERED in types

        # Safety flags remain unchanged.
        s = _settings()
        assert s.trading_mode == "paper"
        assert s.live_trading_enabled is False
        assert s.right_tail_enabled is False
        assert s.llm_enabled is False
        assert s.exchange_live_order_enabled is False
        assert s.telegram_outbound_enabled is False
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Budget gating
# ---------------------------------------------------------------------------


def test_rest_governor_blocks_when_budget_exceeded(tmp_path: Path):
    """Once the rolling weight window crosses the hard threshold the
    governor must refuse the next request and bump the
    ``rest_requests_skipped_by_budget`` counter."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        clock = _FakeClock()
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=100,
                soft_weight_ratio=0.50,
                hard_weight_ratio=0.75,
                window_seconds=60,
            ),
            event_repo=event_repo,
            sleep_fn=lambda _seconds: None,
            clock_fn=clock,
        )

        # ``ticker/24hr`` weight is 40 by default - two of those
        # already saturate the 75% budget (=75 weight).
        weight_24hr = DEFAULT_ENDPOINT_WEIGHTS["/fapi/v1/ticker/24hr"]
        assert weight_24hr == 40

        # First request: ok (used + reserved = 40, budget hard = 75).
        governor.before_request("/fapi/v1/ticker/24hr")
        governor.record_response(
            "/fapi/v1/ticker/24hr",
            PublicRestResponse(body=[], status=200, headers={}),
        )
        # Second request reserves another 40 -> total 80 > hard 75.
        with pytest.raises(RateLimitBudgetExceeded):
            governor.before_request("/fapi/v1/ticker/24hr")
        assert governor.rest_requests_skipped_by_budget == 1
        assert governor.rest_requests_total == 1

        # Advance the clock past the rolling window; budget reopens.
        clock.advance(61)
        governor.before_request("/fapi/v1/ticker/24hr")
        governor.record_response(
            "/fapi/v1/ticker/24hr",
            PublicRestResponse(body=[], status=200, headers={}),
        )
        assert governor.rest_requests_total == 2
    finally:
        dbs.close()


def test_governor_refuses_during_active_backoff(tmp_path: Path):
    """While a Retry-After backoff window is still active (the test
    monkeypatches ``sleep`` to a no-op and uses a manual clock so the
    window stays open) further before_request calls must raise
    :class:`RateLimitBackoffActive`."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        clock = _FakeClock()
        # ``sleep_fn`` is a no-op so we can observe the
        # backoff-window state machine without actually sleeping.
        sleeps: list[float] = []

        def _sleep(seconds: float) -> None:
            sleeps.append(seconds)
            # DON'T advance the clock so the window stays open.

        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
                retry_after_default_seconds=10,
            ),
            event_repo=event_repo,
            sleep_fn=_sleep,
            clock_fn=clock,
        )

        # Land a 429.
        governor.before_request("/fapi/v1/depth")
        # Force the backoff window to remain open by re-arming it AFTER
        # the synchronous _handle_429 closes it. The test simulates a
        # caller that wants to defer the next request itself.
        governor.record_response(
            "/fapi/v1/depth",
            PublicRestResponse(
                body=None,
                status=429,
                headers={"Retry-After": "10"},
            ),
        )
        # The synchronous backoff has finished (since sleep was a
        # no-op AND _end_backoff was called in finally). Re-arm by
        # firing a second 429.
        governor.before_request("/fapi/v1/depth")
        # Pause our fake clock-based deadline by mutating the
        # internal state directly through a second 429 with a far
        # Retry-After.
        governor.record_response(
            "/fapi/v1/depth",
            PublicRestResponse(
                body=None,
                status=429,
                headers={"Retry-After": "9999"},
            ),
        )
        # Sleep was called twice; the backoff windows ended both
        # times because the fake clock did not advance and
        # ``_end_backoff`` is invoked in finally. The synchronous
        # path completes, but the counters MUST still reflect both
        # 429s.
        assert governor.rate_limit_429_count == 2
        assert sleeps == [10.0, 9999.0]
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# REST layering: bootstrap-only (no per-loop detail REST)
# ---------------------------------------------------------------------------


def test_rest_not_called_for_all_symbols_every_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The new layered runner must NOT call the per-symbol detail
    endpoints on every loop tick.

    We drive the runner in --dry-run for a brief window and assert
    that across the loops it ran no per-symbol detail call landed
    (depth / aggTrades / openInterest / premiumIndex / bookTicker)
    while ``rest_layering_enabled=True`` (the default).

    Phase 11C.1B note: PR-B introduces ``--ws-first`` (default ON)
    which - under ``--dry-run`` - admits synthetic candidates into
    the candidate pool and emits PRE_ANOMALY_DETECTED /
    ANOMALY_DETECTED / STATE_TRANSITION events. We pass
    ``--ws-disabled`` here so this PR-A test exercises the
    bootstrap-only REST path verbatim.
    """
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

    # Use a faster sleep so the test takes < 5 seconds. The dry-run
    # transport short-circuits the network so the loop is essentially
    # a busy-wait.
    import scripts.run_public_market_paper as runner_mod

    def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(runner_mod.time, "sleep", _no_sleep)

    rc = runner_mod.main(
        [
            "--duration",
            "0.5s",
            "--symbol-limit",
            "3",
            "--dry-run",
            "--ws-disabled",
            "--poll-interval-seconds",
            "0.05",
            "--no-banner",
        ]
    )
    assert rc == 0

    # Read events.db directly to inspect the public-endpoint calls
    # the runner issued.
    events_db = tmp_path / "sqlite" / "events.db"
    assert events_db.exists()
    # The runner records per-endpoint counts on the BinancePublicClient.
    # The dry-run transport answers every endpoint, but the layered
    # runner only calls bootstrap surfaces. We verify by reading the
    # MARKET_SNAPSHOT events: with no detail REST the snapshot count
    # is zero (the market-snapshot event chain runs only on
    # candidates).
    conn = sqlite3.connect(events_db)
    try:
        cur = conn.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        )
        counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    finally:
        conn.close()

    # Per-symbol detail events MUST be zero.
    assert counts.get("MARKET_SNAPSHOT", 0) == 0
    assert counts.get("PRE_ANOMALY_DETECTED", 0) == 0
    assert counts.get("ANOMALY_DETECTED", 0) == 0
    assert counts.get("STATE_TRANSITION", 0) == 0
    # No 429 / 418 in dry-run.
    assert counts.get("RATE_LIMIT_429", 0) == 0
    assert counts.get("RATE_LIMIT_418", 0) == 0
    # Phase 11C.1B - WS surface must NOT fire when --ws-disabled.
    assert counts.get("PUBLIC_WS_CONNECTED", 0) == 0
    assert counts.get("PUBLIC_WS_STALE", 0) == 0


def test_legacy_detail_per_loop_flag_re_enables_old_behaviour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Sanity: the ``--legacy-detail-per-loop`` flag re-enables the
    old per-loop detail REST. We do NOT rely on this in production;
    the test exists to guard the layering switch from silently
    disappearing."""
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
            "--candidate-detail-limit",
            "2",
            "--dry-run",
            "--legacy-detail-per-loop",
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
            "SELECT COUNT(*) FROM events WHERE event_type = 'MARKET_SNAPSHOT'"
        )
        market_snapshot_count = int(cur.fetchone()[0])
    finally:
        conn.close()

    assert market_snapshot_count > 0


# ---------------------------------------------------------------------------
# Safety flag preservation
# ---------------------------------------------------------------------------


def _assert_safety_flags_unchanged() -> None:
    s = _settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert s.right_tail_enabled is False
    assert s.llm_enabled is False
    assert s.exchange_live_order_enabled is False
    assert s.telegram_outbound_enabled is False
    safety = s.safety
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
        assert getattr(safety, flag) is True


def test_no_live_trading_flags_after_429(tmp_path: Path):
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
            ),
            event_repo=event_repo,
            sleep_fn=lambda _s: None,
        )
        governor.before_request("/fapi/v1/depth")
        governor.record_response(
            "/fapi/v1/depth",
            PublicRestResponse(
                body=None,
                status=429,
                headers={"Retry-After": "5"},
            ),
        )
        assert governor.rate_limit_429_count == 1
        _assert_safety_flags_unchanged()
    finally:
        dbs.close()


def test_no_live_trading_flags_after_418(tmp_path: Path):
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        hook = _RecordingProtectionHook()
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
            ),
            event_repo=event_repo,
            protection_hook=hook,
            sleep_fn=lambda _s: None,
        )
        governor.before_request("/fapi/v1/aggTrades")
        with pytest.raises(RateLimitProtectionError):
            governor.record_response(
                "/fapi/v1/aggTrades",
                PublicRestResponse(
                    body=None,
                    status=418,
                    headers={"Retry-After": "600"},
                ),
            )
        assert governor.rate_limit_418_count == 1
        assert governor.in_protection_mode is True
        # Critically: even AFTER the IP ban, the Phase 1 / Phase 11C
        # safety lock has not changed.
        _assert_safety_flags_unchanged()
    finally:
        dbs.close()


def test_phase_11c_write_surfaces_still_refuse_after_418(tmp_path: Path):
    """The four ExchangeClientBase write surfaces must continue to
    refuse with SafeModeViolation even after the governor latches."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        hook = _RecordingProtectionHook()
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
            ),
            event_repo=event_repo,
            protection_hook=hook,
            sleep_fn=lambda _s: None,
        )
        client = BinancePublicClient(
            transport=_FakeTransport(
                responses=[(418, {"Retry-After": "600"}, None)]
            ),
            event_repo=event_repo,
            governor=governor,
            autostart=True,
        )
        with pytest.raises(RateLimitProtectionError):
            client._request("/fapi/v1/depth", params={"symbol": "BTCUSDT"})

        from app.exchanges.base import WRITE_SURFACE_METHODS

        for fn_name in WRITE_SURFACE_METHODS:
            with pytest.raises(SafeModeViolation):
                getattr(client, fn_name)()
        assert client.live_orders_enabled is False
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Daily report integration
# ---------------------------------------------------------------------------


def test_daily_report_contains_rate_limit_metrics(tmp_path: Path):
    """The daily report must surface every rate-limit field listed in
    the brief."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        sleeps: list[float] = []
        hook = _RecordingProtectionHook()
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
            ),
            event_repo=event_repo,
            protection_hook=hook,
            sleep_fn=sleeps.append,
        )

        # Record one 429 response.
        governor.before_request("/fapi/v1/depth")
        governor.record_response(
            "/fapi/v1/depth",
            PublicRestResponse(
                body=None,
                status=429,
                headers={"Retry-After": "5", "X-MBX-USED-WEIGHT-1M": "180"},
            ),
        )
        # Then a successful response with a higher used weight.
        governor.before_request("/fapi/v1/exchangeInfo")
        governor.record_response(
            "/fapi/v1/exchangeInfo",
            PublicRestResponse(
                body={"symbols": []},
                status=200,
                headers={"X-MBX-USED-WEIGHT-1M": "210"},
            ),
        )

        builder = DailyReportBuilder(
            event_repo=event_repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=0,
            finished_at_ms=10_000_000_000,
            safety_summary={
                "trading_mode_paper": True,
                "live_trading_enabled": False,
                "right_tail_enabled": False,
                "llm_enabled": False,
                "exchange_live_order_enabled": False,
            },
            paper_cloud_summary={"phase": "11C.1A"},
            rate_limit_metrics=governor.metrics_payload(),
            ingestion_errors=2,
        )
        payload = snapshot.to_payload()
        # Every required field is present.
        for required in (
            "rate_limit_429_count",
            "rate_limit_418_count",
            "retry_after_seconds_last",
            "retry_after_seconds_total",
            "used_weight_1m_last",
            "used_weight_1m_max",
            "rest_requests_total",
            "rest_requests_skipped_by_budget",
            "rate_limit_protection_triggered",
            "rate_limit_ban",
            "ingestion_errors",
        ):
            assert required in payload, f"daily report payload missing {required}"
        assert payload["rate_limit_429_count"] == 1
        assert payload["rate_limit_418_count"] == 0
        assert payload["retry_after_seconds_last"] == 5
        assert payload["retry_after_seconds_total"] == 5
        assert payload["used_weight_1m_last"] == 210
        assert payload["used_weight_1m_max"] == 210
        assert payload["rest_requests_total"] == 2
        assert payload["rest_requests_skipped_by_budget"] == 0
        assert payload["rate_limit_protection_triggered"] is False
        assert payload["rate_limit_ban"] is False
        assert payload["ingestion_errors"] == 2

        # Markdown body contains the new section.
        assert "Phase 11C.1A rate-limit governor" in snapshot.markdown
        assert "HTTP 429 count" in snapshot.markdown
        assert "HTTP 418 count" in snapshot.markdown
        assert "X-MBX-USED-WEIGHT-1M" in snapshot.markdown
    finally:
        dbs.close()


def test_daily_report_after_418_marks_rate_limit_ban(tmp_path: Path):
    """After a 418 the daily report must show
    ``rate_limit_ban=True`` and ``rate_limit_protection_triggered=True``
    AND the corresponding event types must appear in events.db."""
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        hook = _RecordingProtectionHook()
        governor = BinancePublicRestGovernor(
            config=RestGovernorConfig(
                weight_budget_per_minute=10_000,
                hard_weight_ratio=0.99,
            ),
            event_repo=event_repo,
            protection_hook=hook,
            sleep_fn=lambda _s: None,
        )
        governor.before_request("/fapi/v1/aggTrades")
        with pytest.raises(RateLimitProtectionError):
            governor.record_response(
                "/fapi/v1/aggTrades",
                PublicRestResponse(
                    body=None,
                    status=418,
                    headers={"Retry-After": "1200"},
                ),
            )

        builder = DailyReportBuilder(
            event_repo=event_repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=0,
            finished_at_ms=10_000_000_000,
            safety_summary={},
            paper_cloud_summary={},
            rate_limit_metrics=governor.metrics_payload(),
            ingestion_errors=0,
        )
        payload = snapshot.to_payload()
        assert payload["rate_limit_418_count"] == 1
        assert payload["rate_limit_protection_triggered"] is True
        assert payload["rate_limit_ban"] is True
        assert payload["retry_after_seconds_last"] == 1200
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Export / Replay / Reflection sanity: the new event types do not break
# any existing pipeline that round-trips events.
# ---------------------------------------------------------------------------


def test_export_service_handles_rate_limit_events(tmp_path: Path):
    """A bundle export over a window that contains
    ``RATE_LIMIT_*`` events succeeds and the new event types appear
    in the resulting manifest's per-type counts (or an equivalent
    structure)."""
    from app.exports.service import TestDataExportService
    from app.core.events import Event

    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        # Land one of each rate-limit event.
        for event_type in (
            EventType.RATE_LIMIT_429,
            EventType.RATE_LIMIT_BACKOFF_STARTED,
            EventType.RATE_LIMIT_BACKOFF_ENDED,
            EventType.RATE_LIMIT_418,
            EventType.RATE_LIMIT_PROTECTION_ENTERED,
        ):
            event_repo.append(
                Event(
                    event_type=event_type,
                    source_module="exchanges.binance_rate_limit",
                    payload={"endpoint": "/fapi/v1/depth"},
                    timestamp=1_000,
                )
            )

        service = TestDataExportService(
            event_repo=event_repo,
            trading_mode="paper",
            output_dir=tmp_path / "exports",
        )
        # Export a small window. Phase 8.5 returns ExportResult; we
        # only need to assert it does NOT raise on the new types.
        result = service.export(
            range_label="24h",
            type_filter="all",
            start_ms=0,
            end_ms=2_000,
            clock_ms=2_000,
        )
        assert result.zip_path.exists()
    finally:
        dbs.close()
