"""Phase 11C.1C-C-B-B-B-D-A.1 - Historical 60D Mover Reference
Store Builder v0 unit tests.

Test plan (mirrors the brief's acceptance list):

  - test_exchange_info_filters_usdt_perpetual_universe
  - test_top_mover_reference_store_schema
  - test_manifest_records_public_only_invariants
  - test_reference_builder_does_not_load_api_keys
  - test_reference_builder_does_not_use_signed_endpoints
  - test_reference_set_is_post_hoc_only
  - test_top_movers_can_be_loaded_by_historical_coverage_backfill
  - test_missing_event_history_remains_valid_miss_reason
  - test_no_live_trading_flags_unchanged
  - test_phase_12_remains_forbidden

The builder writes paper / report / evidence-only artefacts. None of
these tests authorise a real trade or flip a Phase 1 safety flag.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from app.adaptive.historical_mover_coverage_backfill import (
    DEFAULT_MIN_HISTORY_DAYS,
    DEFAULT_REFERENCE_WINDOW_DAYS,
    HistoricalMoverCoverageBackfillInput,
    HistoricalMoverCoverageBackfillRuntime,
    HistoricalMoverCoverageStatus,
    HistoricalMoverLookaheadGuardError,
    HistoricalMoverMissReason,
    LOOKAHEAD_FORBIDDEN_FIELDS,
    build_historical_60d_mover_reference_set,
    load_historical_market_store,
)
from app.core.errors import SafeModeViolation
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository

from scripts.build_historical_mover_reference_store import (
    BUILDER_SCHEMA_VERSION,
    BUILDER_VERSION,
    DEFAULT_OUTPUT_DIR,
    LOOKAHEAD_POLICY,
    REFERENCE_SOURCE,
    BinanceFuturesPublicSource,
    PublicCallRecord,
    assert_no_credentials_in_env,
    build_no_network_source,
    filter_eligible_usdt_perpetual_universe,
    klines_to_daily_top_movers,
    main,
    run_build,
    select_symbols_by_volume,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

DAY_MS = 24 * 60 * 60 * 1000
HOUR_MS = 60 * 60 * 1000


def _audit_window_end_ms() -> int:
    """Deterministic UTC midnight anchor for tests."""
    return 1_767_225_600_000  # 2026-01-01T00:00:00Z


def _build_exchange_info_payload() -> dict:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            },
            {
                "symbol": "ETHUSDT",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            },
            {
                # USD-margined coin contract - must be excluded.
                "symbol": "BTCUSD_PERP",
                "baseAsset": "BTC",
                "quoteAsset": "USD",
                "contractType": "PERPETUAL",
                "status": "TRADING",
            },
            {
                # Quarterly contract - must be excluded.
                "symbol": "BTCUSDT_220325",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "contractType": "CURRENT_QUARTER",
                "status": "TRADING",
            },
            {
                # Non-trading symbol - must be excluded.
                "symbol": "OLDUSDT",
                "baseAsset": "OLD",
                "quoteAsset": "USDT",
                "contractType": "PERPETUAL",
                "status": "BREAK",
            },
        ]
    }


@pytest.fixture
def events_repo(tmp_path: Path) -> EventRepository:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital)


# ---------------------------------------------------------------------------
# 1. Universe filtering
# ---------------------------------------------------------------------------


def test_exchange_info_filters_usdt_perpetual_universe() -> None:
    eligible = filter_eligible_usdt_perpetual_universe(
        _build_exchange_info_payload()
    )
    symbols = sorted({row["symbol"] for row in eligible})
    assert symbols == ["BTCUSDT", "ETHUSDT"]
    for row in eligible:
        assert row["quote_asset"] == "USDT"
        assert row["contract_type"] == "PERPETUAL"
        assert row["status"] == "TRADING"


def test_select_symbols_by_volume_ranks_eligible_universe_only() -> None:
    eligible = filter_eligible_usdt_perpetual_universe(
        _build_exchange_info_payload()
    )
    tickers = [
        {"symbol": "ETHUSDT", "quoteVolume": "5000000000"},
        {"symbol": "BTCUSDT", "quoteVolume": "1000000000"},
        # Ineligible symbols must be ignored even when they top the
        # 24h-volume board.
        {"symbol": "BTCUSD_PERP", "quoteVolume": "9999999999"},
    ]
    selected = select_symbols_by_volume(
        eligible_universe=eligible,
        tickers_24h=tickers,
        symbol_limit=2,
    )
    assert selected == ["ETHUSDT", "BTCUSDT"]


def test_select_symbols_with_no_limit_returns_alphabetical_universe() -> None:
    eligible = filter_eligible_usdt_perpetual_universe(
        _build_exchange_info_payload()
    )
    selected = select_symbols_by_volume(
        eligible_universe=eligible,
        tickers_24h=[],
        symbol_limit=None,
    )
    assert selected == sorted({"BTCUSDT", "ETHUSDT"})


# ---------------------------------------------------------------------------
# 2. Top-mover schema + ranking
# ---------------------------------------------------------------------------


def _kline(open_ms: int, open_p: float, close_p: float, high_p: float | None = None,
           low_p: float | None = None, volume: float = 100.0,
           quote_volume: float | None = None) -> list:
    high_p = high_p if high_p is not None else max(open_p, close_p) * 1.01
    low_p = low_p if low_p is not None else min(open_p, close_p) * 0.99
    qv = (
        quote_volume
        if quote_volume is not None
        else volume * (open_p + close_p) / 2.0
    )
    return [
        open_ms,
        f"{open_p:.4f}",
        f"{high_p:.4f}",
        f"{low_p:.4f}",
        f"{close_p:.4f}",
        f"{volume:.4f}",
        open_ms + HOUR_MS - 1,
        f"{qv:.4f}",
        1,
        f"{volume / 2.0:.4f}",
        f"{qv / 2.0:.4f}",
        "0",
    ]


def _day_klines(day_start_ms: int, *, open_p: float, close_p: float) -> list:
    """Return 24 1h klines spanning the given UTC day."""
    klines: list = []
    for hour in range(24):
        progress = hour / 24.0
        next_progress = (hour + 1) / 24.0
        o = open_p + (close_p - open_p) * progress
        c = open_p + (close_p - open_p) * next_progress
        klines.append(
            _kline(
                open_ms=day_start_ms + hour * HOUR_MS,
                open_p=o,
                close_p=c,
                high_p=max(o, c) * 1.005,
                low_p=min(o, c) * 0.995,
                volume=100.0 + hour,
            )
        )
    return klines


def test_top_mover_reference_store_schema(tmp_path: Path) -> None:
    end_ms = _audit_window_end_ms()
    day0 = end_ms - DAY_MS
    klines_by_symbol = {
        "AAAUSDT": _day_klines(day0, open_p=100.0, close_p=120.0),  # +20 %
        "BBBUSDT": _day_klines(day0, open_p=100.0, close_p=110.0),  # +10 %
        "CCCUSDT": _day_klines(day0, open_p=100.0, close_p=98.0),   # -2 %
    }
    metadata = {
        sym: {
            "quote_asset": "USDT",
            "contract_type": "PERPETUAL",
            "eligible_usdt_perpetual": True,
        }
        for sym in klines_by_symbol
    }
    rows = klines_to_daily_top_movers(
        klines_by_symbol=klines_by_symbol,
        days=1,
        top_n=3,
        audit_window_end_ms=end_ms,
        timeframe="1h",
        symbol_metadata=metadata,
    )
    assert len(rows) == 3
    # Verify ranking order.
    ranked = [r["symbol"] for r in rows]
    assert ranked == ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
    # Top-mover rank starts at 1.
    assert [r["top_mover_rank"] for r in rows] == [1, 2, 3]
    # Schema completeness: every brief-mandated field is present.
    required = {
        "symbol",
        "mover_window_start_utc",
        "mover_window_end_utc",
        "reference_timestamp_utc",
        "top_mover_rank",
        "window_gain_pct",
        "max_24h_gain_pct",
        "open_price",
        "close_price",
        "high_price",
        "low_price",
        "quote_volume",
        "eligible_usdt_perpetual",
        "source",
        "lookahead_policy",
    }
    # Loader-compatibility fields (consumed by
    # ``build_historical_60d_mover_reference_set``).
    loader_required = {
        "snapshot_date",
        "reference_timestamp_utc_ms",
        "mover_window_start_utc_ms",
        "mover_window_end_utc_ms",
        "max_window_gain",
        "max_24h_gain",
        "quote_volume_usdt",
        "quote_asset",
        "contract_type",
    }
    for row in rows:
        assert required.issubset(row.keys()), sorted(required - row.keys())
        assert loader_required.issubset(row.keys()), (
            sorted(loader_required - row.keys())
        )
        assert row["source"] == REFERENCE_SOURCE
        assert row["lookahead_policy"] == LOOKAHEAD_POLICY
        assert row["eligible_usdt_perpetual"] is True
        # No forbidden lookahead column may appear.
        for forbidden in LOOKAHEAD_FORBIDDEN_FIELDS:
            assert forbidden not in row


def test_window_gain_calculation_is_post_hoc_only() -> None:
    """``window_gain_pct`` must be derived from kline data only -
    never from a future return / settled outcome column."""
    end_ms = _audit_window_end_ms()
    day0 = end_ms - DAY_MS
    klines = {
        "ZZZUSDT": _day_klines(day0, open_p=200.0, close_p=300.0),  # +50 %
    }
    rows = klines_to_daily_top_movers(
        klines_by_symbol=klines,
        days=1,
        top_n=1,
        audit_window_end_ms=end_ms,
        timeframe="1h",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["window_gain_pct"] == pytest.approx(0.5, rel=1e-6)
    # ``max_24h_gain_pct`` must equal max(window_gain, intraday_high_gain).
    assert row["max_24h_gain_pct"] >= row["window_gain_pct"]
    assert row["max_window_gain"] == pytest.approx(row["window_gain_pct"])
    assert row["max_24h_gain"] == pytest.approx(row["max_24h_gain_pct"])


# ---------------------------------------------------------------------------
# 3. Public-only invariants
# ---------------------------------------------------------------------------


def test_reference_builder_does_not_load_api_keys() -> None:
    """The :class:`BinanceFuturesPublicSource` constructor refuses any
    credential-shaped kwarg or env var."""

    # Direct kwargs.
    with pytest.raises(SafeModeViolation):
        BinanceFuturesPublicSource(api_key="not-a-real-key")
    with pytest.raises(SafeModeViolation):
        BinanceFuturesPublicSource(api_secret="not-a-real-secret")
    with pytest.raises(SafeModeViolation):
        BinanceFuturesPublicSource(token="not-a-real-token")
    with pytest.raises(SafeModeViolation):
        BinanceFuturesPublicSource(passphrase="not-a-real-pass")

    # Env-var pre-flight.
    with pytest.raises(SafeModeViolation):
        assert_no_credentials_in_env({"BINANCE_API_KEY": "leaked"})
    with pytest.raises(SafeModeViolation):
        assert_no_credentials_in_env({"BINANCE_API_SECRET": "leaked"})

    # The defensive flags on the source object always read False even
    # when an instance was constructed.
    src = build_no_network_source(
        audit_window_end_ms=_audit_window_end_ms(),
        days=2,
    )
    assert src.api_key_loaded is False
    assert src.signed_endpoint_used is False


def test_reference_builder_does_not_use_signed_endpoints() -> None:
    """The builder must never call a signed endpoint, never pass a
    signed query parameter, and never use a non-allowlisted host."""

    src = build_no_network_source(
        audit_window_end_ms=_audit_window_end_ms(),
        days=2,
    )

    with pytest.raises(SafeModeViolation):
        src._request("/fapi/v1/order")  # private endpoint
    with pytest.raises(SafeModeViolation):
        src._request("/fapi/v2/account")  # private endpoint
    with pytest.raises(SafeModeViolation):
        src._request("/fapi/v1/listenKey")  # private endpoint
    with pytest.raises(SafeModeViolation):
        src._request("/fapi/v1/leverage")  # private endpoint
    with pytest.raises(SafeModeViolation):
        src._request("/fapi/v1/marginType")  # private endpoint
    with pytest.raises(SafeModeViolation):
        src._request(
            "/fapi/v1/exchangeInfo",
            params={"signature": "0xdeadbeef"},
        )
    with pytest.raises(SafeModeViolation):
        src._request(
            "/fapi/v1/exchangeInfo",
            params={"timestamp": "1700000000000"},
        )

    # An end-to-end build run only ever touches allowlisted endpoints.
    result = run_build(
        output_dir="data/historical_market_store",  # ignored under dry_run
        days=2,
        timeframe="1h",
        top_n=3,
        symbol_limit=2,
        no_network=True,
        dry_run=True,
        audit_window_end_ms=_audit_window_end_ms(),
        request_sleep_seconds=0.0,
    )
    paths = {rec.path for rec in result.public_call_records}
    allowed = {"/fapi/v1/exchangeInfo", "/fapi/v1/ticker/24hr", "/fapi/v1/klines"}
    assert paths.issubset(allowed), paths
    assert all(rec.status == "ok" for rec in result.public_call_records)


def test_reference_set_is_post_hoc_only(tmp_path: Path) -> None:
    """Every emitted JSONL row must carry the post-hoc lookahead
    policy and must not contain any forbidden lookahead column."""

    end_ms = _audit_window_end_ms()
    result = run_build(
        output_dir=tmp_path / "store",
        days=2,
        timeframe="1h",
        top_n=3,
        symbol_limit=3,
        no_network=True,
        dry_run=False,
        audit_window_end_ms=end_ms,
        request_sleep_seconds=0.0,
    )
    assert result.artefacts.written is True
    top_movers_path = result.artefacts.top_movers_path
    assert top_movers_path.exists()
    rows = [
        json.loads(line)
        for line in top_movers_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows, "builder produced an empty top-mover JSONL"
    for row in rows:
        assert row["lookahead_policy"] == LOOKAHEAD_POLICY
        assert row["source"] == REFERENCE_SOURCE
        assert row.get("schema_version") == BUILDER_SCHEMA_VERSION
        for forbidden in LOOKAHEAD_FORBIDDEN_FIELDS:
            assert forbidden not in row


def test_lookahead_guard_rejects_completed_tail_label_in_builder_output(
    tmp_path: Path,
) -> None:
    """Defence-in-depth: a malicious row injected into the writer
    path must be rejected by the lookahead guard."""

    from scripts.build_historical_mover_reference_store import (
        write_top_movers_jsonl,
    )

    bad_row = {
        "symbol": "FUTUREUSDT",
        "snapshot_date": "2026-02-01",
        "reference_timestamp_utc_ms": _audit_window_end_ms(),
        "mover_window_start_utc_ms": _audit_window_end_ms() - DAY_MS,
        "mover_window_end_utc_ms": _audit_window_end_ms(),
        "top_mover_rank": 1,
        "max_window_gain": 5.2,
        # Forbidden lookahead column - the writer must refuse.
        "completed_tail_label": "strong_tail",
    }
    with pytest.raises(HistoricalMoverLookaheadGuardError):
        write_top_movers_jsonl(
            output_root=tmp_path / "store",
            rows=[bad_row],
            days=2,
            generated_at_ms=_audit_window_end_ms(),
            dry_run=False,
        )


# ---------------------------------------------------------------------------
# 4. Manifest invariants
# ---------------------------------------------------------------------------


def test_manifest_records_public_only_invariants(tmp_path: Path) -> None:
    end_ms = _audit_window_end_ms()
    result = run_build(
        output_dir=tmp_path / "store",
        days=2,
        timeframe="1h",
        top_n=5,
        symbol_limit=3,
        no_network=True,
        dry_run=False,
        audit_window_end_ms=end_ms,
        request_sleep_seconds=0.0,
    )
    manifest_path = result.artefacts.manifest_path
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # ----- Public-only invariants -----
    assert manifest["public_endpoint_only"] is True
    assert manifest["private_api_used"] is False
    assert manifest["api_key_loaded"] is False
    assert manifest["signed_endpoint_used"] is False
    assert manifest["binance_private_api_enabled"] is False
    assert manifest["telegram_outbound_enabled"] is False
    assert manifest["live_trading_enabled"] is False
    assert manifest["exchange_live_order_enabled"] is False
    assert manifest["right_tail_enabled"] is False
    assert manifest["llm_enabled"] is False
    assert manifest["trading_mode"] == "paper"

    # ----- Lookahead Guard invariant -----
    assert manifest["lookahead_policy"] == LOOKAHEAD_POLICY
    assert (
        manifest["lookahead_guard"]
        == "reference_set_is_post_hoc_audit_only"
    )
    for forbidden in LOOKAHEAD_FORBIDDEN_FIELDS:
        assert forbidden in manifest["lookahead_forbidden_fields"]

    # ----- Run mode -----
    assert manifest["no_network_test_mode"] is True
    assert manifest["dry_run"] is False

    # ----- Schema versions -----
    assert manifest["schema_version"] == BUILDER_SCHEMA_VERSION
    assert manifest["builder_version"] == BUILDER_VERSION
    assert manifest["timeframe"] == "1h"
    assert manifest["days_requested"] == 2
    assert manifest["top_n"] == 5

    # ----- Output files -----
    assert "exchange_info" in manifest["output_files"]
    assert "top_movers" in manifest["output_files"]

    # ----- Boundary invariants -----
    boundary = manifest["boundary"]
    assert boundary["is_strategy_blind_replay"] is False
    assert boundary["is_pnl_backtest"] is False
    assert boundary["is_trading_module"] is False
    assert boundary["is_ai_learning"] is False
    assert boundary["is_parameter_optimisation"] is False
    assert boundary["is_reinforcement_learning"] is False
    assert boundary["is_phase_12"] is False
    assert boundary["is_post_hoc_audit_reference_only"] is True
    assert boundary["phase_12_remains_forbidden"] is True


# ---------------------------------------------------------------------------
# 5. Integration with the existing D-A loader
# ---------------------------------------------------------------------------


def test_top_movers_can_be_loaded_by_historical_coverage_backfill(
    tmp_path: Path,
) -> None:
    """The artefacts the builder writes must round-trip through
    :func:`load_historical_market_store` and
    :func:`build_historical_60d_mover_reference_set` without any
    loader change."""

    end_ms = _audit_window_end_ms()
    result = run_build(
        output_dir=tmp_path / "store",
        days=3,
        timeframe="1h",
        top_n=4,
        symbol_limit=4,
        no_network=True,
        dry_run=False,
        audit_window_end_ms=end_ms,
        request_sleep_seconds=0.0,
    )
    snap = load_historical_market_store(tmp_path / "store")
    assert snap.history_days_observed >= 3
    # The loader-side eligible universe must include the symbols we
    # processed.
    for sym in result.symbols_processed:
        assert sym in snap.exchange_info_symbols
    # Reference-set construction.
    ref_set = build_historical_60d_mover_reference_set(
        top_mover_rows=snap.top_mover_rows,
        audit_window_end_utc_ms=end_ms,
        reference_window_days=3,
        exchange_info_symbols=snap.exchange_info_symbols,
        history_days_observed=snap.history_days_observed,
    )
    assert ref_set.total_count > 0
    assert ref_set.eligible_count == ref_set.total_count
    # Every reference row must remain post-hoc-only and inside the
    # window.
    for row in ref_set.references:
        assert row.eligible_usdt_perpetual is True
        assert row.reference_timestamp_utc_ms <= end_ms + DAY_MS
        assert row.reference_timestamp_utc_ms >= end_ms - 4 * DAY_MS


def test_missing_event_history_remains_valid_miss_reason(
    tmp_path: Path,
    events_repo: EventRepository,
) -> None:
    """Building the reference store does NOT change the audit's
    miss-reason taxonomy: a top mover whose symbol has no events in
    EventRepository remains classified as
    ``MISSING_EVENT_HISTORY``."""

    end_ms = _audit_window_end_ms()
    run_build(
        output_dir=tmp_path / "store",
        days=2,
        timeframe="1h",
        top_n=3,
        symbol_limit=3,
        no_network=True,
        dry_run=False,
        audit_window_end_ms=end_ms,
        request_sleep_seconds=0.0,
    )
    snap = load_historical_market_store(tmp_path / "store")
    ref_set = build_historical_60d_mover_reference_set(
        top_mover_rows=snap.top_mover_rows,
        audit_window_end_utc_ms=end_ms,
        reference_window_days=2,
        exchange_info_symbols=snap.exchange_info_symbols,
        history_days_observed=snap.history_days_observed,
    )
    audit_input = HistoricalMoverCoverageBackfillInput(
        reference_set=ref_set,
        audit_window_end_utc_ms=end_ms,
        reference_window_days=2,
        exchange_info_symbols=snap.exchange_info_symbols,
        history_days_observed=snap.history_days_observed,
        min_history_days=1,
    )
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    # We never seeded any events for these symbols, so every record
    # must be MISSED with miss_reason=MISSING_EVENT_HISTORY.
    assert report.records, "audit produced no records"
    for record in report.records:
        assert record.coverage_status == HistoricalMoverCoverageStatus.MISSED
        assert (
            record.miss_reason
            == HistoricalMoverMissReason.MISSING_EVENT_HISTORY
        )


# ---------------------------------------------------------------------------
# 6. Boundary / safety
# ---------------------------------------------------------------------------


def test_no_live_trading_flags_unchanged() -> None:
    """The Phase 1 safety flags MUST remain off after running the
    builder. The builder never touches ``Settings``; we still re-read
    it to belt-and-braces the boundary."""

    from app.config import settings as settings_mod

    # Build something so the run-path is exercised.
    run_build(
        output_dir="data/historical_market_store",  # ignored under dry-run
        days=1,
        timeframe="1h",
        top_n=2,
        symbol_limit=2,
        no_network=True,
        dry_run=True,
        audit_window_end_ms=_audit_window_end_ms(),
        request_sleep_seconds=0.0,
    )

    settings = settings_mod.get_settings()
    assert settings.trading_mode == "paper"
    assert bool(settings.live_trading_enabled) is False
    assert bool(settings.right_tail_enabled) is False
    assert bool(settings.llm_enabled) is False
    assert bool(settings.exchange_live_order_enabled) is False


def test_phase_12_remains_forbidden() -> None:
    """The phase-gate documents must continue to mark Phase 12 as
    FORBIDDEN."""

    project_root = Path(__file__).resolve().parents[2]
    phase_gate = (project_root / "docs" / "PHASE_GATE.md").read_text(
        encoding="utf-8"
    )
    assert "Phase 12" in phase_gate
    assert (
        "FORBIDDEN" in phase_gate
        or "forbidden" in phase_gate
        or "NOT_AUTHORISED" in phase_gate
        or "not authorised" in phase_gate
    )


# ---------------------------------------------------------------------------
# 7. CLI smoke
# ---------------------------------------------------------------------------


def test_cli_dry_run_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Smoke-test the CLI under ``--dry-run`` + ``--no-network``."""
    rc = main(
        [
            "--days",
            "2",
            "--symbol-limit",
            "3",
            "--top-n",
            "5",
            "--dry-run",
            "--no-network",
            "--output-dir",
            str(tmp_path / "store"),
            "--audit-window-end-utc-ms",
            str(_audit_window_end_ms()),
            "--request-sleep-seconds",
            "0",
            "--quiet",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["public_endpoint_only"] is True
    assert summary["private_api_used"] is False
    assert summary["api_key_loaded"] is False
    assert summary["signed_endpoint_used"] is False
    assert summary["lookahead_policy"] == LOOKAHEAD_POLICY
    assert summary["dry_run"] is True
    assert summary["no_network_test_mode"] is True
    assert summary["days_requested"] == 2
    assert summary["top_n"] == 5
    # The top-mover record count is the per-day top-N times the days
    # observed (deterministic in --no-network mode).
    assert summary["top_mover_record_count"] >= 1


def test_cli_refuses_with_credentials_in_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI refuses to start when a Binance credential env var is
    present, regardless of the other flags."""
    monkeypatch.setenv("BINANCE_API_KEY", "leaked-fake-key")
    rc = main(
        [
            "--days",
            "1",
            "--symbol-limit",
            "1",
            "--top-n",
            "1",
            "--dry-run",
            "--no-network",
            "--output-dir",
            str(tmp_path / "store"),
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "REFUSED" in captured.err
