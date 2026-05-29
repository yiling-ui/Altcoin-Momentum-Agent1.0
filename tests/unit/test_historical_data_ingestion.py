"""Unit tests for Phase 11C.1D-D-H / PR101 / Historical Data
Ingestion / Backfill v0.

These tests are the safety contract for this PR. If any of them fails
the module is not safe to merge.

Hard safety boundary covered by these tests:

  - mode = historical_blind_sim_live
  - sandbox_only = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - telegram_outbound_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

The tests also assert that the new modules:

  - do NOT import app.risk / app.execution / app.exchanges /
    app.telegram / app.config
  - do NOT pull any DeepSeek / LLM / Telegram / Binance / network
    transport
  - emit no forbidden trade / runtime-config / live-ready field, and
    no api_key / api_secret / listenKey / signed_endpoint /
    private_websocket / real_order_id / exchange_order_id field
  - never fabricate real market data on missing input
  - never present a coverage report as a strategy-effectiveness
    conclusion
  - are deterministic
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

import pytest

from app.sim import (
    FORBIDDEN_OUTPUT_FIELDS,
    HISTORICAL_DATA_INGESTION_PHASE_NAME,
    DataCompletenessState,
    DataIngestionStatus,
    DataQualityFlag,
    HistoricalDataIngestion,
    HistoricalDataIngestionConfig,
    HistoricalDataIngestionResult,
    HistoricalDataManifest,
    HistoricalDataSourceType,
    HistoricalKlineRecord,
    HistoricalMarketRecord,
    HistoricalMarketRecordType,
    HistoricalMarketStore,
    IngestionSchemaError,
    IngestionTimeFieldError,
    SymbolStatus,
    SymbolStatusRecord,
    UniverseManifest,
    parse_funding_row,
    parse_kline_row,
    parse_open_interest_row,
    parse_symbol_status_row,
    parse_ticker_24h_row,
)
from app.sim.historical_data_ingestion import SUPPORTED_KLINE_INTERVALS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
_GEN = datetime(2026, 5, 29, 0, 0, 0, tzinfo=timezone.utc)

# Fields that MUST NEVER appear as a key in any PR101 output payload,
# in addition to the project-wide FORBIDDEN_OUTPUT_FIELDS.
PR101_EXTRA_FORBIDDEN_FIELDS = frozenset(
    {
        "api_key",
        "api_secret",
        "listenKey",
        "signed_endpoint",
        "private_websocket",
        "real_order_id",
        "exchange_order_id",
        "runtime_config_patch",
        "threshold_patch",
        "symbol_limit_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        "enable_live",
        "live_ready",
        "trading_approved",
    }
)

ALL_FORBIDDEN_KEYS = FORBIDDEN_OUTPUT_FIELDS | PR101_EXTRA_FORBIDDEN_FIELDS


def _walk_keys(payload: Any):
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


def _walk_values(payload: Any):
    if isinstance(payload, Mapping):
        for v in payload.values():
            yield from _walk_values(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_values(v)
    else:
        yield payload


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_imported_modules(source_text: str) -> set:
    tree = ast.parse(source_text)
    mods: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def _collect_dotted_calls(source_text: str) -> set:
    """Collect dotted attribute chains used as the *function* of a
    call (e.g. ``requests.get`` / ``socket.connect``).

    We deliberately do NOT collect bare class-attribute names because
    the public-file source taxonomy legitimately contains members such
    as ``BINANCE_PUBLIC_KLINE_FILE`` (a file source type, never a
    network identifier).
    """
    tree = ast.parse(source_text)
    out: set = set()

    def attr_chain(n):
        parts: List[str] = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            chain = attr_chain(node.func)
            if chain:
                out.add(chain)
    return out


def _make_kline_row(
    *,
    open_time: datetime,
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 95.0,
    close: float = 105.0,
    volume: float = 1000.0,
    **extra: Any,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "open_time": open_time.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
    row.update(extra)
    return row


def _write_jsonl(path: Path, rows: List[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def _build_input_tree(
    root: Path,
    *,
    symbols: List[str],
    intervals: List[str],
    klines_per_interval: int,
    start: datetime = _T0,
    with_funding: bool = True,
    with_oi: bool = True,
    with_ticker: bool = True,
    with_symbol_status: bool = True,
    kline_skip: int = 0,
) -> None:
    """Write a deterministic local input tree."""
    for symbol in symbols:
        for interval in intervals:
            seconds = 60 if interval == "1m" else 300
            rows = []
            for i in range(klines_per_interval):
                if i < kline_skip:
                    continue  # create a leading gap
                ot = start + timedelta(seconds=seconds * i)
                rows.append(
                    _make_kline_row(
                        open_time=ot,
                        open_=100.0 + i,
                        high=101.0 + i,
                        low=99.0 + i,
                        close=100.5 + i,
                        volume=1000.0 + i,
                    )
                )
            _write_jsonl(
                root / "klines" / symbol / f"{interval}.jsonl", rows
            )
        if with_funding:
            _write_jsonl(
                root / "funding" / f"{symbol}.jsonl",
                [
                    {
                        "symbol": symbol,
                        "event_time": start.isoformat(),
                        "funding_rate": 0.0001,
                    }
                ],
            )
        if with_oi:
            _write_jsonl(
                root / "open_interest" / f"{symbol}.jsonl",
                [
                    {
                        "symbol": symbol,
                        "event_time": start.isoformat(),
                        "open_interest": 1_000_000.0,
                    }
                ],
            )
        if with_ticker:
            _write_jsonl(
                root / "ticker_24h" / f"{symbol}.jsonl",
                [
                    {
                        "symbol": symbol,
                        "event_time": start.isoformat(),
                        "last_price": 100.0,
                    }
                ],
            )
    if with_symbol_status:
        _write_jsonl(
            root / "symbol_status.jsonl",
            [
                {
                    "symbol": symbol,
                    "market_type": "PERP",
                    "status": SymbolStatus.TRADING,
                    "listed_at": (start - timedelta(days=1)).isoformat(),
                    "available_at": (
                        start - timedelta(days=1)
                    ).isoformat(),
                }
                for symbol in symbols
            ],
        )


def _config(
    tmp_path: Path,
    *,
    input_root: Path = None,
    symbols=("BTCUSDT",),
    intervals=("1m",),
    end: datetime = None,
    fixture_mode: bool = False,
    lag: float = 0.0,
) -> HistoricalDataIngestionConfig:
    return HistoricalDataIngestionConfig(
        input_root=str(input_root or (tmp_path / "in")),
        output_root=str(tmp_path / "out"),
        start_time=_T0,
        end_time=end or (_T0 + timedelta(minutes=5)),
        symbols=tuple(symbols),
        intervals=tuple(intervals),
        default_availability_lag_seconds=lag,
        fixture_mode=fixture_mode,
    )


# ---------------------------------------------------------------------------
# 1. parses 1m kline fixture into HistoricalKlineRecord
# ---------------------------------------------------------------------------


def test_parses_1m_kline_into_kline_record():
    rec = parse_kline_row(
        _make_kline_row(open_time=_T0),
        symbol="BTCUSDT",
        interval="1m",
        source=HistoricalDataSourceType.BINANCE_PUBLIC_KLINE_FILE,
    )
    assert isinstance(rec, HistoricalKlineRecord)
    assert rec.symbol == "BTCUSDT"
    assert rec.interval == "1m"
    assert rec.record_type == HistoricalMarketRecordType.KLINE_1M
    assert rec.open == 100.0
    assert rec.high == 110.0
    assert rec.low == 95.0
    assert rec.close == 105.0
    assert rec.volume == 1000.0
    assert rec.close_time == _T0 + timedelta(minutes=1)


def test_parses_binance_array_kline_row():
    # Binance public kline array: [open_time_ms, o, h, l, c, v, close_time_ms]
    open_ms = int(_T0.timestamp() * 1000)
    close_ms = int((_T0 + timedelta(minutes=1)).timestamp() * 1000) - 1
    rec = parse_kline_row(
        [open_ms, "100.0", "110.0", "95.0", "105.0", "1000.0", close_ms],
        symbol="BTCUSDT",
        interval="1m",
    )
    assert isinstance(rec, HistoricalKlineRecord)
    assert rec.open_time == _T0
    assert rec.close == 105.0


# ---------------------------------------------------------------------------
# 2. parses 5m kline fixture into HistoricalKlineRecord
# ---------------------------------------------------------------------------


def test_parses_5m_kline_into_kline_record():
    rec = parse_kline_row(
        _make_kline_row(open_time=_T0),
        symbol="ETHUSDT",
        interval="5m",
    )
    assert isinstance(rec, HistoricalKlineRecord)
    assert rec.interval == "5m"
    assert rec.record_type == HistoricalMarketRecordType.KLINE_5M
    assert rec.close_time == _T0 + timedelta(minutes=5)


# ---------------------------------------------------------------------------
# 3. available_at is preserved and timezone-aware UTC
# ---------------------------------------------------------------------------


def test_available_at_is_preserved_and_utc_aware():
    explicit = _T0 + timedelta(minutes=10)
    rec = parse_kline_row(
        _make_kline_row(
            open_time=_T0, available_at=explicit.isoformat()
        ),
        symbol="BTCUSDT",
        interval="1m",
    )
    assert rec.available_at == explicit
    assert rec.available_at.tzinfo is not None
    assert rec.available_at.utcoffset() == timedelta(0)

    # Without an explicit available_at, it is derived from close_time
    # plus lag (still UTC-aware), never naive.
    rec2 = parse_kline_row(
        _make_kline_row(open_time=_T0),
        symbol="BTCUSDT",
        interval="1m",
        default_availability_lag_seconds=30,
    )
    assert rec2.available_at == _T0 + timedelta(minutes=1, seconds=30)
    assert rec2.available_at.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# 4. ingested_at is not used as available_at
# ---------------------------------------------------------------------------


def test_ingested_at_is_never_used_as_available_at():
    # ingested_at is far in the past relative to the derived
    # available_at; the parser must NOT substitute it.
    ingested = _T0 - timedelta(days=5)
    rec = parse_kline_row(
        _make_kline_row(
            open_time=_T0, ingested_at=ingested.isoformat()
        ),
        symbol="BTCUSDT",
        interval="1m",
        default_availability_lag_seconds=0,
    )
    assert rec.ingested_at == ingested
    assert rec.available_at == _T0 + timedelta(minutes=1)
    assert rec.available_at != rec.ingested_at

    # Same for non-kline records.
    frec = parse_funding_row(
        {
            "symbol": "BTCUSDT",
            "event_time": _T0.isoformat(),
            "ingested_at": ingested.isoformat(),
            "funding_rate": 0.0001,
        }
    )
    assert frec.ingested_at == ingested
    assert frec.available_at == _T0
    assert frec.available_at != frec.ingested_at


# ---------------------------------------------------------------------------
# 5. rejects invalid time fields
# ---------------------------------------------------------------------------


def test_rejects_naive_and_malformed_time_fields():
    # Naive ISO string (no tz).
    with pytest.raises(IngestionTimeFieldError):
        parse_kline_row(
            {
                "open_time": "2026-05-01T00:00:00",
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 1,
            },
            symbol="BTCUSDT",
            interval="1m",
        )
    # Garbage string.
    with pytest.raises(IngestionTimeFieldError):
        parse_funding_row(
            {
                "symbol": "BTCUSDT",
                "event_time": "not-a-date",
                "funding_rate": 0.1,
            }
        )
    # Missing required time field.
    with pytest.raises(IngestionTimeFieldError):
        parse_open_interest_row(
            {"symbol": "BTCUSDT", "open_interest": 1.0}
        )


def test_engine_reports_invalidated_time_fields(tmp_path):
    root = tmp_path / "in"
    # Valid + one naive-time row in the same kline file.
    _write_jsonl(
        root / "klines" / "BTCUSDT" / "1m.jsonl",
        [
            _make_kline_row(open_time=_T0),
            {
                "open_time": "2026-05-01T00:01:00",  # naive -> rejected
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 1,
            },
        ],
    )
    cfg = _config(tmp_path, input_root=root)
    result = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    assert result.status == DataIngestionStatus.INVALIDATED_TIME_FIELDS
    assert result.rejected_record_count >= 1


# ---------------------------------------------------------------------------
# 6/7/8. funding / OI / ticker fixture becomes HistoricalMarketRecord
# ---------------------------------------------------------------------------


def test_funding_row_becomes_market_record():
    rec = parse_funding_row(
        {
            "symbol": "BTCUSDT",
            "event_time": _T0.isoformat(),
            "funding_rate": 0.0001,
            "funding_interval_hours": 8,
        }
    )
    assert isinstance(rec, HistoricalMarketRecord)
    assert rec.record_type == HistoricalMarketRecordType.FUNDING_RATE
    assert rec.payload["funding_rate"] == 0.0001
    assert rec.event_time == _T0


def test_open_interest_row_becomes_market_record():
    rec = parse_open_interest_row(
        {
            "symbol": "BTCUSDT",
            "event_time": _T0.isoformat(),
            "open_interest": 1234.5,
        }
    )
    assert isinstance(rec, HistoricalMarketRecord)
    assert rec.record_type == HistoricalMarketRecordType.OPEN_INTEREST
    assert rec.payload["open_interest"] == 1234.5


def test_ticker_24h_row_becomes_market_record():
    rec = parse_ticker_24h_row(
        {
            "symbol": "BTCUSDT",
            "event_time": _T0.isoformat(),
            "last_price": 105.0,
            "price_change_percent": 2.5,
        }
    )
    assert isinstance(rec, HistoricalMarketRecord)
    assert rec.record_type == HistoricalMarketRecordType.TICKER_24H
    assert rec.payload["last_price"] == 105.0


# ---------------------------------------------------------------------------
# 9. symbol status fixture becomes SymbolStatusRecord
# ---------------------------------------------------------------------------


def test_symbol_status_row_becomes_symbol_status_record():
    rec = parse_symbol_status_row(
        {
            "symbol": "BTCUSDT",
            "market_type": "PERP",
            "status": SymbolStatus.TRADING,
            "listed_at": _T0.isoformat(),
            "available_at": _T0.isoformat(),
            "contract_type": "PERPETUAL",
        }
    )
    assert isinstance(rec, SymbolStatusRecord)
    assert rec.symbol == "BTCUSDT"
    assert rec.status == SymbolStatus.TRADING
    assert rec.record_type == HistoricalMarketRecordType.SYMBOL_STATUS


# ---------------------------------------------------------------------------
# 10. universe manifest prevents survivorship bias
# ---------------------------------------------------------------------------


def test_universe_manifest_prevents_survivorship_bias():
    listed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    delist_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    btc = parse_symbol_status_row(
        {
            "symbol": "BTCUSDT",
            "market_type": "PERP",
            "status": SymbolStatus.TRADING,
            "listed_at": listed_at.isoformat(),
            "available_at": listed_at.isoformat(),
        }
    )
    oldcoin = parse_symbol_status_row(
        {
            "symbol": "OLDCOIN",
            "market_type": "PERP",
            "status": SymbolStatus.TRADING,
            "listed_at": listed_at.isoformat(),
            "available_at": listed_at.isoformat(),
            "delisted_at": delist_at.isoformat(),
        }
    )
    um = UniverseManifest(
        start_time=listed_at,
        end_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
        symbol_status_records=(btc, oldcoin),
        generated_at_utc=_GEN,
    )
    # The delisted symbol is NEVER erased from the manifest.
    assert "OLDCOIN" in um.symbols
    assert um.delisted_count == 1
    assert um.listed_count == 1
    assert um.to_dict()["survivorship_bias_guard"] is True

    # As-of universe is reconstructed from the listing/delisting
    # timeline, not the current symbol list.
    before = um.asof_universe_symbols(
        datetime(2026, 2, 1, tzinfo=timezone.utc)
    )
    after = um.asof_universe_symbols(
        datetime(2026, 4, 1, tzinfo=timezone.utc)
    )
    assert "OLDCOIN" in before  # listed, not yet delisted
    assert "OLDCOIN" not in after  # delisted by this time
    assert "BTCUSDT" in before and "BTCUSDT" in after


# ---------------------------------------------------------------------------
# 11. coverage report counts records by type/symbol
# ---------------------------------------------------------------------------


def test_coverage_report_counts_records_by_type_and_symbol(tmp_path):
    root = tmp_path / "in"
    _build_input_tree(
        root,
        symbols=["BTCUSDT", "ETHUSDT"],
        intervals=["1m"],
        klines_per_interval=5,
    )
    cfg = _config(
        tmp_path, input_root=root, symbols=("BTCUSDT", "ETHUSDT")
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    assert result.status == DataIngestionStatus.EVIDENCE_GENERATED

    counts = result.manifest.record_counts_by_type
    assert counts[HistoricalMarketRecordType.KLINE_1M] == 10
    assert counts[HistoricalMarketRecordType.FUNDING_RATE] == 2

    cov = engine.coverage_report()["coverage_by_symbol"]
    assert (
        cov["BTCUSDT"]["record_counts_by_type"][
            HistoricalMarketRecordType.KLINE_1M
        ]
        == 5
    )
    assert (
        cov["BTCUSDT"]["kline_coverage"]["1m"]["completeness_bucket"]
        == "COMPLETE"
    )


# ---------------------------------------------------------------------------
# 12. missing kline intervals become data gap warnings
# ---------------------------------------------------------------------------


def test_missing_kline_intervals_become_data_gap_warnings(tmp_path):
    root = tmp_path / "in"
    # expected 5 1m klines over the window, but skip the first 2.
    _build_input_tree(
        root,
        symbols=["BTCUSDT"],
        intervals=["1m"],
        klines_per_interval=5,
        kline_skip=2,
    )
    cfg = _config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    assert result.status == DataIngestionStatus.PARTIAL_EVIDENCE

    gap = engine.data_gap_report()["data_gap_summary"]
    assert gap["total_missing_kline_count"] == 2
    assert "BTCUSDT|1m" in gap["gaps_by_symbol_interval"]
    assert len(gap["gaps_by_symbol_interval"]["BTCUSDT|1m"]) == 2
    assert any(
        "kline_gap" in w for w in result.warnings
    )


# ---------------------------------------------------------------------------
# 13. late-arriving record visible only after available_at
# ---------------------------------------------------------------------------


def test_late_arriving_record_visible_only_after_available_at():
    late_available = _T0 + timedelta(days=10)
    rec = parse_funding_row(
        {
            "symbol": "BTCUSDT",
            "event_time": _T0.isoformat(),
            "available_at": late_available.isoformat(),
            "funding_rate": 0.0001,
            "late_arrival": True,
            "data_quality_flags": [DataQualityFlag.LATE_ARRIVAL],
        }
    )
    assert rec.late_arrival is True
    store = HistoricalMarketStore()
    store.add_record(rec)

    # Just after the event but well before available_at: invisible.
    visible_early = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        symbol="BTCUSDT",
        simulated_time=_T0 + timedelta(minutes=1),
    )
    assert visible_early == []

    # After available_at: visible.
    visible_late = store.query_records(
        HistoricalMarketRecordType.FUNDING_RATE,
        symbol="BTCUSDT",
        simulated_time=late_available + timedelta(minutes=1),
    )
    assert len(visible_late) == 1


# ---------------------------------------------------------------------------
# 14. revised record preserves revised_from_record_id / revision_time
# ---------------------------------------------------------------------------


def test_revised_record_preserves_revision_metadata():
    rev_time = _T0 + timedelta(hours=1)
    rec = parse_open_interest_row(
        {
            "symbol": "BTCUSDT",
            "event_time": _T0.isoformat(),
            "open_interest": 999.0,
            "revised_from_record_id": "oi:BTCUSDT:original",
            "revision_time": rev_time.isoformat(),
            "data_quality_flags": [DataQualityFlag.REVISED_RECORD],
        }
    )
    assert rec.revised_from_record_id == "oi:BTCUSDT:original"
    assert rec.revision_time == rev_time
    assert DataQualityFlag.REVISED_RECORD in rec.data_quality_flags


# ---------------------------------------------------------------------------
# 15. manifest hash deterministic
# ---------------------------------------------------------------------------


def test_manifest_hash_is_deterministic(tmp_path):
    cfg = _config(
        tmp_path,
        symbols=("BTCUSDT", "ETHUSDT"),
        intervals=("1m", "5m"),
        end=_T0 + timedelta(minutes=10),
        fixture_mode=True,
    )
    r1 = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    # Different generated_at_utc must NOT change the content hash.
    r2 = HistoricalDataIngestion(
        cfg,
        generated_at_utc=_GEN + timedelta(days=3),
    ).ingest()
    assert (
        r1.manifest.data_manifest_hash
        == r2.manifest.data_manifest_hash
    )
    assert (
        r1.universe_manifest.universe_manifest_hash
        == r2.universe_manifest.universe_manifest_hash
    )

    # A different window changes the hash.
    cfg3 = _config(
        tmp_path,
        symbols=("BTCUSDT", "ETHUSDT"),
        intervals=("1m", "5m"),
        end=_T0 + timedelta(minutes=20),
        fixture_mode=True,
    )
    r3 = HistoricalDataIngestion(cfg3, generated_at_utc=_GEN).ingest()
    assert (
        r3.manifest.data_manifest_hash
        != r1.manifest.data_manifest_hash
    )


# ---------------------------------------------------------------------------
# 16. runner with missing input returns INSUFFICIENT_EVIDENCE,
#     not fake data
# ---------------------------------------------------------------------------


def test_missing_input_returns_insufficient_evidence_not_fake_data(
    tmp_path,
):
    cfg = _config(
        tmp_path,
        input_root=tmp_path / "does_not_exist",
        symbols=("BTCUSDT",),
        fixture_mode=False,
    )
    result = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    assert result.status == DataIngestionStatus.INSUFFICIENT_EVIDENCE
    assert result.ingested_record_count == 0
    # No fabricated records.
    assert result.manifest.record_counts_by_type == {}
    assert any(
        "NOT fabricating real market data" in w
        for w in result.warnings
    )


# ---------------------------------------------------------------------------
# 17. explicit fixture mode can generate deterministic fixture output
# ---------------------------------------------------------------------------


def test_explicit_fixture_mode_generates_deterministic_output(tmp_path):
    cfg = _config(
        tmp_path,
        symbols=("BTCUSDT",),
        intervals=("1m",),
        end=_T0 + timedelta(minutes=5),
        fixture_mode=True,
    )
    result = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    assert result.status == DataIngestionStatus.EVIDENCE_GENERATED
    assert result.ingested_record_count > 0
    # Fixture output must be clearly marked synthetic.
    assert any(
        "SYNTHETIC_FIXTURE_NOT_REAL_MARKET_DATA" in w
        for w in result.warnings
    )


# ---------------------------------------------------------------------------
# 18. output JSON serializable
# ---------------------------------------------------------------------------


def test_all_outputs_are_json_serializable(tmp_path):
    cfg = _config(
        tmp_path, fixture_mode=True, end=_T0 + timedelta(minutes=5)
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    for payload in (
        result.to_dict(),
        result.manifest.to_dict(),
        result.universe_manifest.to_dict(),
        engine.coverage_report(),
        engine.data_gap_report(),
        cfg.to_dict(),
    ):
        # Round-trips without error.
        text = json.dumps(payload, sort_keys=True)
        assert json.loads(text) == json.loads(text)

    # write_outputs produces readable JSON files + records.jsonl.
    written = engine.write_outputs()
    for p in (
        written.coverage_report_path,
        written.data_gap_report_path,
        written.records_path,
    ):
        assert Path(p).exists()
    json.loads(
        Path(tmp_path / "out" / "historical_data_manifest.json").read_text()
    )


# ---------------------------------------------------------------------------
# 19/20/21. phase_12_forbidden / auto_tuning_allowed / trade_authority
# ---------------------------------------------------------------------------


def _all_output_payloads(tmp_path) -> List[Dict[str, Any]]:
    cfg = _config(
        tmp_path, fixture_mode=True, end=_T0 + timedelta(minutes=5)
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    return [
        result.to_dict(),
        result.manifest.to_dict(),
        result.universe_manifest.to_dict(),
        engine.coverage_report(),
        engine.data_gap_report(),
        cfg.to_dict(),
        engine.safety_payload(),
    ]


def test_phase_12_forbidden_in_every_payload(tmp_path):
    for payload in _all_output_payloads(tmp_path):
        assert payload["phase_12_forbidden"] is True


def test_auto_tuning_allowed_false_in_every_payload(tmp_path):
    for payload in _all_output_payloads(tmp_path):
        assert payload["auto_tuning_allowed"] is False


def test_trade_authority_false_in_every_payload(tmp_path):
    for payload in _all_output_payloads(tmp_path):
        assert payload["trade_authority"] is False
        assert payload["live_trading"] is False
        assert payload["exchange_live_orders"] is False
        assert payload["binance_private_api_enabled"] is False
        assert payload["telegram_outbound_enabled"] is False
        assert payload["ai_trade_authority"] is False
        # A coverage report is NOT a strategy-effectiveness conclusion.
        assert (
            payload.get("is_strategy_effectiveness_conclusion", False)
            is False
        )


# ---------------------------------------------------------------------------
# 22. module does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports():
    root = _project_root()
    files = [
        root / "app" / "sim" / "__init__.py",
        root / "app" / "sim" / "historical_data_ingestion.py",
        root / "app" / "sim" / "historical_data_manifest.py",
        root / "scripts" / "run_historical_data_ingestion.py",
    ]
    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in files:
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            for bad in forbidden_prefixes:
                assert not mod.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
    # Importing the modules does NOT pull a forbidden module into
    # sys.modules.
    before = set(sys.modules)
    importlib.import_module("app.sim.historical_data_ingestion")
    importlib.import_module("app.sim.historical_data_manifest")
    new = set(sys.modules) - before
    for nm in new:
        for bad in forbidden_prefixes:
            assert not nm.startswith(bad), (
                f"importing pulled forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 23. no private API / signed endpoint / Telegram / DeepSeek / LLM /
#     network call path
# ---------------------------------------------------------------------------


def test_no_network_or_private_api_call_path():
    root = _project_root()
    files = [
        root / "app" / "sim" / "historical_data_ingestion.py",
        root / "app" / "sim" / "historical_data_manifest.py",
        root / "scripts" / "run_historical_data_ingestion.py",
    ]
    forbidden_module_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        "telegram",
        "binance",
        "ccxt",
        "websocket",
        "websockets",
        "httpx",
        "aiohttp",
        "requests",
        "urllib.request",
        "http.client",
        "grpc",
        "boto3",
        "socket",
    )
    forbidden_call_prefixes = (
        "requests.",
        "httpx.",
        "aiohttp.",
        "socket.connect",
        "socket.create_connection",
        "urllib.request",
        "websocket.",
        "telegram.",
        "binance.",
        "openai.",
        "deepseek.",
    )
    for path in files:
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            low = mod.lower()
            for bad in forbidden_module_prefixes:
                assert not low.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
        calls = _collect_dotted_calls(src)
        for call in calls:
            low = call.lower()
            for bad in forbidden_call_prefixes:
                assert not low.startswith(bad), (
                    f"{path} contains forbidden call {call!r}"
                )


# ---------------------------------------------------------------------------
# 24. forbidden fields absent
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_in_all_outputs(tmp_path):
    for payload in _all_output_payloads(tmp_path):
        for key in _walk_keys(payload):
            assert key not in ALL_FORBIDDEN_KEYS, (
                f"forbidden field {key!r} present in output payload"
            )

    # Also exercise the per-record serialisation path.
    cfg = _config(
        tmp_path, fixture_mode=True, end=_T0 + timedelta(minutes=5)
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    engine.ingest()
    for rec in engine.records:
        for key in _walk_keys(rec.to_dict()):
            assert key not in ALL_FORBIDDEN_KEYS


# ---------------------------------------------------------------------------
# 25. deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output(tmp_path):
    cfg = _config(
        tmp_path,
        symbols=("BTCUSDT", "ETHUSDT"),
        intervals=("1m", "5m"),
        end=_T0 + timedelta(minutes=10),
        fixture_mode=True,
    )
    a = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    b = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    assert a.to_dict() == b.to_dict()


# ---------------------------------------------------------------------------
# Extras: taxonomies + phase name + status from a real input tree
# ---------------------------------------------------------------------------


def test_closed_taxonomies_and_phase_name():
    assert HistoricalDataSourceType.ALLOWED == frozenset(
        {
            "BINANCE_PUBLIC_KLINE_FILE",
            "BINANCE_PUBLIC_FUNDING_FILE",
            "BINANCE_PUBLIC_OPEN_INTEREST_FILE",
            "BINANCE_PUBLIC_TICKER_FILE",
            "EXCHANGE_INFO_FILE",
            "SYMBOL_STATUS_FILE",
            "MANUAL_FIXTURE_FILE",
        }
    )
    assert DataIngestionStatus.ALLOWED == frozenset(
        {
            "EVIDENCE_GENERATED",
            "PARTIAL_EVIDENCE",
            "INSUFFICIENT_EVIDENCE",
            "FAILED_SCHEMA_VALIDATION",
            "INVALIDATED_TIME_FIELDS",
        }
    )
    assert SUPPORTED_KLINE_INTERVALS == ("1m", "5m")
    assert "PR101" in HISTORICAL_DATA_INGESTION_PHASE_NAME


def test_full_input_tree_evidence_generated_and_store_roundtrip(tmp_path):
    root = tmp_path / "in"
    _build_input_tree(
        root,
        symbols=["BTCUSDT"],
        intervals=["1m", "5m"],
        klines_per_interval=5,
    )
    cfg = _config(
        tmp_path,
        input_root=root,
        symbols=("BTCUSDT",),
        intervals=("1m", "5m"),
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    assert isinstance(result, HistoricalDataIngestionResult)
    assert isinstance(result.manifest, HistoricalDataManifest)
    assert result.status == DataIngestionStatus.EVIDENCE_GENERATED
    assert (
        result.manifest.coverage_by_symbol["BTCUSDT"][
            "completeness_state"
        ]
        == DataCompletenessState.OK
    )

    # The ingested records load into a real HistoricalMarketStore
    # under its strict available_at <= simulated_time gate.
    store = engine.build_store()
    sim = _T0 + timedelta(days=1)
    klines = store.query_klines(
        "BTCUSDT", "1m", simulated_time=sim
    )
    assert len(klines) == 5
    universe = store.query_asof_universe(sim)
    assert any(s.symbol == "BTCUSDT" for s in universe)


def test_schema_error_on_missing_required_numeric_field():
    # A non-time schema problem (missing funding_rate) raises the
    # schema error, distinct from the time-field error taxonomy.
    with pytest.raises(IngestionSchemaError):
        parse_funding_row(
            {"symbol": "BTCUSDT", "event_time": _T0.isoformat()}
        )



# ---------------------------------------------------------------------------
# PR101-A: Binance public futures kline daily-CSV file adapter
#
# Real-file adaptation for Binance public futures kline dumps laid out
# as klines/<SYMBOL>/<INTERVAL>/<SYMBOL>-<INTERVAL>-YYYY-MM-DD.csv with
# the 12-column header:
#   open_time,open,high,low,close,volume,close_time,quote_volume,count,
#   taker_buy_volume,taker_buy_quote_volume,ignore
# ---------------------------------------------------------------------------

_BINANCE_KLINE_CSV_HEADER = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,"
    "count,taker_buy_volume,taker_buy_quote_volume,ignore"
)


def _binance_kline_csv_text(
    *,
    start: datetime = _T0,
    interval: str = "1m",
    count: int = 5,
    with_header: bool = True,
    base_price: float = 100.0,
    extra_data_lines: List[str] = None,
) -> str:
    """Build the text of a real-shaped Binance public futures kline
    daily CSV (12 columns, optional header, millisecond timestamps)."""
    seconds = 60 if interval == "1m" else 300
    lines: List[str] = []
    if with_header:
        lines.append(_BINANCE_KLINE_CSV_HEADER)
    for i in range(count):
        ot = start + timedelta(seconds=seconds * i)
        open_ms = int(ot.timestamp() * 1000)
        # Binance close_time is the last millisecond of the candle.
        close_ms = open_ms + seconds * 1000 - 1
        price = base_price + float(i)
        lines.append(
            f"{open_ms},{price},{price + 1.0},{price - 1.0},"
            f"{price + 0.5},{1000.0 + float(i)},{close_ms},"
            f"{price * 1000.0},{50 + i},{500.0 + float(i)},"
            f"{50000.0 + float(i)},0"
        )
    if extra_data_lines:
        lines.extend(extra_data_lines)
    return "\n".join(lines) + "\n"


def _write_binance_kline_csv(
    root: Path,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    count: int = 5,
    start: datetime = _T0,
    date_str: str = "2026-05-01",
    with_header: bool = True,
    base_price: float = 100.0,
    extra_data_lines: List[str] = None,
    base_subdir: str = None,
) -> Path:
    """Write a Binance public futures kline daily CSV under the real
    nested layout and return the file path."""
    base = root if base_subdir is None else (root / base_subdir)
    interval_dir = base / "klines" / symbol / interval
    interval_dir.mkdir(parents=True, exist_ok=True)
    path = interval_dir / f"{symbol}-{interval}-{date_str}.csv"
    path.write_text(
        _binance_kline_csv_text(
            start=start,
            interval=interval,
            count=count,
            with_header=with_header,
            base_price=base_price,
            extra_data_lines=extra_data_lines,
        ),
        encoding="utf-8",
    )
    return path


def _binance_config(
    tmp_path: Path,
    *,
    input_root: Path,
    symbols=("BTCUSDT",),
    intervals=("1m",),
    end: datetime = None,
    lag: float = 0.0,
) -> HistoricalDataIngestionConfig:
    return HistoricalDataIngestionConfig(
        input_root=str(input_root),
        output_root=str(tmp_path / "out"),
        start_time=_T0,
        end_time=end or (_T0 + timedelta(minutes=5)),
        symbols=tuple(symbols),
        intervals=tuple(intervals),
        include_funding=False,
        include_open_interest=False,
        include_ticker_24h=False,
        include_exchange_info=False,
        include_symbol_status=False,
        default_availability_lag_seconds=lag,
        source_type=HistoricalDataSourceType.BINANCE_PUBLIC_KLINE_FILE,
    )


def _klines_of(engine: HistoricalDataIngestion) -> List[HistoricalKlineRecord]:
    return [
        r for r in engine.records
        if isinstance(r, HistoricalKlineRecord)
    ]


# --- 1. scans nested Binance public kline path ---------------------------


def test_binance_csv_scans_nested_kline_path(tmp_path):
    root = tmp_path / "in"
    csv_path = _write_binance_kline_csv(
        root, symbol="BTCUSDT", interval="1m", count=5
    )
    assert csv_path.name == "BTCUSDT-1m-2026-05-01.csv"
    cfg = _binance_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    assert result.status == DataIngestionStatus.EVIDENCE_GENERATED
    assert str(csv_path) in result.manifest.source_files


def test_binance_csv_scans_binance_um_layout_and_discovers_symbols(
    tmp_path,
):
    # input_root points at data/historical_raw; data lives under the
    # binance_um/ subtree, symbols are auto-discovered.
    root = tmp_path / "data" / "historical_raw"
    _write_binance_kline_csv(
        root,
        symbol="BTCUSDT",
        interval="1m",
        count=5,
        base_subdir="binance_um",
    )
    cfg = HistoricalDataIngestionConfig(
        input_root=str(root),
        output_root=str(tmp_path / "out"),
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=5),
        symbols=(),  # force auto-discovery
        intervals=("1m",),
        include_funding=False,
        include_open_interest=False,
        include_ticker_24h=False,
        include_exchange_info=False,
        include_symbol_status=False,
        source_type=HistoricalDataSourceType.BINANCE_PUBLIC_KLINE_FILE,
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    assert result.ingested_record_count == 5
    assert all(k.symbol == "BTCUSDT" for k in _klines_of(engine))


# --- 2. parses 12-column header CSV correctly ----------------------------


def test_binance_csv_parses_12_column_header_row(tmp_path):
    root = tmp_path / "in"
    _write_binance_kline_csv(root, count=3)
    cfg = _binance_config(
        tmp_path, input_root=root, end=_T0 + timedelta(minutes=3)
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    engine.ingest()
    klines = sorted(_klines_of(engine), key=lambda k: k.open_time)
    assert len(klines) == 3
    first = klines[0]
    assert first.open == 100.0
    assert first.high == 101.0
    assert first.low == 99.0
    assert first.close == 100.5
    assert first.volume == 1000.0


# --- 3. skips the header row (never parsed as data) ----------------------


def test_binance_csv_skips_header_row(tmp_path):
    root = tmp_path / "in"
    _write_binance_kline_csv(root, count=5)
    cfg = _binance_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    # Exactly 5 data rows ingested; the header row is NOT a record and
    # is not counted as a rejection.
    assert result.ingested_record_count == 5
    assert result.rejected_record_count == 0
    for k in _klines_of(engine):
        assert isinstance(k.open, float)


# --- 4. converts open_time / close_time milliseconds to UTC datetime -----


def test_binance_csv_converts_ms_timestamps_to_utc(tmp_path):
    root = tmp_path / "in"
    _write_binance_kline_csv(root, interval="1m", count=1)
    cfg = _binance_config(
        tmp_path, input_root=root, end=_T0 + timedelta(minutes=1)
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    engine.ingest()
    k = _klines_of(engine)[0]
    assert k.open_time == _T0
    assert k.open_time.tzinfo is not None
    assert k.open_time.utcoffset() == timedelta(0)
    assert k.close_time == _T0 + timedelta(minutes=1)
    assert k.close_time.utcoffset() == timedelta(0)
    # event_time is pinned to the candle close_time.
    assert k.event_time == k.close_time


# --- 5. creates HistoricalKlineRecord for 1m -----------------------------


def test_binance_csv_creates_kline_record_1m(tmp_path):
    root = tmp_path / "in"
    _write_binance_kline_csv(root, interval="1m", count=2)
    cfg = _binance_config(
        tmp_path,
        input_root=root,
        intervals=("1m",),
        end=_T0 + timedelta(minutes=2),
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    engine.ingest()
    klines = _klines_of(engine)
    assert klines
    for k in klines:
        assert isinstance(k, HistoricalKlineRecord)
        assert k.interval == "1m"
        assert k.record_type == HistoricalMarketRecordType.KLINE_1M
        assert (
            k.source
            == HistoricalDataSourceType.BINANCE_PUBLIC_KLINE_FILE
        )


# --- 6. creates HistoricalKlineRecord for 5m -----------------------------


def test_binance_csv_creates_kline_record_5m(tmp_path):
    root = tmp_path / "in"
    _write_binance_kline_csv(root, interval="5m", count=3)
    cfg = _binance_config(
        tmp_path,
        input_root=root,
        intervals=("5m",),
        end=_T0 + timedelta(minutes=15),
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    engine.ingest()
    klines = sorted(_klines_of(engine), key=lambda k: k.open_time)
    assert len(klines) == 3
    for k in klines:
        assert k.interval == "5m"
        assert k.record_type == HistoricalMarketRecordType.KLINE_5M
    assert klines[0].close_time == _T0 + timedelta(minutes=5)


# --- 7. source_files is non-empty for real file mode ---------------------


def test_binance_csv_source_files_non_empty(tmp_path):
    root = tmp_path / "in"
    csv_path = _write_binance_kline_csv(root, count=5)
    cfg = _binance_config(tmp_path, input_root=root)
    result = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    assert result.manifest.source_files  # non-empty
    assert str(csv_path) in result.manifest.source_files


# --- 8. ingested_record_count > 0 for a Binance CSV directory ------------


def test_binance_csv_ingested_record_count_positive(tmp_path):
    root = tmp_path / "in"
    _write_binance_kline_csv(root, count=5)
    cfg = _binance_config(tmp_path, input_root=root)
    result = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    assert result.ingested_record_count == 5
    assert result.status == DataIngestionStatus.EVIDENCE_GENERATED


# --- 9. available_at = close_time + lag, never ingested_at ---------------


def test_binance_csv_available_at_is_close_time_plus_lag(tmp_path):
    root = tmp_path / "in"
    lag = 30.0
    _write_binance_kline_csv(root, interval="1m", count=1)
    cfg = _binance_config(
        tmp_path,
        input_root=root,
        end=_T0 + timedelta(minutes=1),
        lag=lag,
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    engine.ingest()
    k = _klines_of(engine)[0]
    assert k.available_at == k.close_time + timedelta(seconds=lag)
    assert k.available_at == _T0 + timedelta(minutes=1, seconds=30)
    # Binance public CSV carries no ingested_at; available_at is never
    # derived from ingestion time.
    assert k.ingested_at is None
    assert k.available_at != k.ingested_at


# --- 10. malformed rows are skipped/rejected with warnings ---------------


def test_binance_csv_malformed_rows_rejected_not_fabricated(tmp_path):
    root = tmp_path / "in"
    bad_open_ms = int((_T0 + timedelta(minutes=2)).timestamp() * 1000)
    bad_close_ms = bad_open_ms + 60_000 - 1
    malformed = [
        # non-numeric volume -> schema error, rejected.
        f"{bad_open_ms},100.0,101.0,99.0,100.5,NOT_A_NUMBER,"
        f"{bad_close_ms},0,0,0,0,0",
        # too few columns -> schema error, rejected.
        "1,2,3",
    ]
    _write_binance_kline_csv(root, count=5, extra_data_lines=malformed)
    cfg = _binance_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    # Valid rows still ingested; malformed rows rejected, never invented.
    assert result.ingested_record_count == 5
    assert result.rejected_record_count == 2
    assert any("rejected_row" in w for w in result.warnings)
    assert result.status == DataIngestionStatus.PARTIAL_EVIDENCE


# --- 11. missing input still returns INSUFFICIENT_EVIDENCE ---------------


def test_binance_csv_missing_input_returns_insufficient_evidence(
    tmp_path,
):
    cfg = _binance_config(
        tmp_path, input_root=tmp_path / "does_not_exist"
    )
    result = HistoricalDataIngestion(cfg, generated_at_utc=_GEN).ingest()
    assert result.status == DataIngestionStatus.INSUFFICIENT_EVIDENCE
    assert result.ingested_record_count == 0
    assert result.manifest.source_files == ()
    assert result.manifest.record_counts_by_type == {}


# --- 12. safety flags remain pinned for the Binance CSV path -------------


def test_binance_csv_safety_flags_remain(tmp_path):
    root = tmp_path / "in"
    _write_binance_kline_csv(root, count=5)
    cfg = _binance_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    for payload in (
        result.to_dict(),
        result.manifest.to_dict(),
        engine.coverage_report(),
        engine.data_gap_report(),
        cfg.to_dict(),
        engine.safety_payload(),
    ):
        assert payload["phase_12_forbidden"] is True
        assert payload["live_trading"] is False
        assert payload["exchange_live_orders"] is False
        assert payload["binance_private_api_enabled"] is False
        assert payload["auto_tuning_allowed"] is False
        assert payload["trade_authority"] is False


# --- 13. CSV adapter uses only the stdlib csv module, no network ----------


def test_binance_csv_adapter_uses_only_stdlib_csv_no_network():
    root = _project_root()
    src = (
        root / "app" / "sim" / "historical_data_ingestion.py"
    ).read_text(encoding="utf-8")
    imported = _collect_imported_modules(src)
    # The CSV adapter relies on the standard-library csv module only.
    assert "csv" in imported
    forbidden = (
        "binance",
        "ccxt",
        "requests",
        "httpx",
        "aiohttp",
        "websocket",
        "websockets",
        "telegram",
        "deepseek",
        "openai",
        "anthropic",
        "socket",
        "urllib.request",
        "http.client",
        "grpc",
        "boto3",
    )
    for mod in imported:
        low = mod.lower()
        for bad in forbidden:
            assert not low.startswith(bad), (
                f"forbidden import {mod!r} in CSV adapter"
            )



# ---------------------------------------------------------------------------
# PR105: SYMBOL_STATUS_FILE source-type routing / scanner +
# kline symbol_status sidecar merge.
#
# Cloud reality this fixes: a 30D multi-symbol kline ingestion produced
# 466560 kline records; the operator then dropped a symbol-status JSONL
# sidecar at
#   data/historical_raw/binance_um/symbol_status/
#       symbol_status_<from>_<to>.jsonl
# but `--source-type SYMBOL_STATUS_FILE` still returned the 466560 kline
# records (SYMBOL_STATUS=0, symbol_status_file_missing). The scanner now
# routes by source_type and discovers the nested sidecar.
# ---------------------------------------------------------------------------


def _sidecar_status_row(
    symbol: str,
    status: str = SymbolStatus.TRADING,
    *,
    event_time: datetime = None,
    available_at: datetime = None,
    ingested_at: datetime = None,
) -> Dict[str, Any]:
    """Build one row in the PR105 sidecar schema:
    {symbol, status, event_time, available_at, ingested_at, source}.

    Deliberately carries NO ``listed_at`` and NO ``market_type`` so the
    parser's event_time anchoring / UNKNOWN-market default is exercised.
    """
    et = event_time or (_T0 - timedelta(days=1))
    av = available_at or et
    ing = ingested_at or _GEN
    return {
        "symbol": symbol,
        "status": status,
        "event_time": et.isoformat(),
        "available_at": av.isoformat(),
        "ingested_at": ing.isoformat(),
        "source": "BINANCE_PUBLIC_EXCHANGE_INFO_FILE",
    }


def _write_symbol_status_sidecar(
    root: Path,
    rows: List[Dict[str, Any]],
    *,
    base_subdir: str = "binance_um",
    filename: str = "symbol_status_2026-04-08_2026-05-08.jsonl",
) -> Path:
    """Write a symbol-status JSONL sidecar under the real Binance public
    dump layout (``<root>/<base_subdir>/symbol_status/<filename>``) and
    return the file path."""
    base = root if base_subdir is None else (root / base_subdir)
    status_dir = base / "symbol_status"
    status_dir.mkdir(parents=True, exist_ok=True)
    path = status_dir / filename
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _symbol_status_config(
    tmp_path: Path,
    *,
    input_root: Path,
    symbols=(),
    intervals=("1m",),
    end: datetime = None,
) -> HistoricalDataIngestionConfig:
    return HistoricalDataIngestionConfig(
        input_root=str(input_root),
        output_root=str(tmp_path / "out"),
        start_time=_T0,
        end_time=end or (_T0 + timedelta(minutes=5)),
        symbols=tuple(symbols),
        intervals=tuple(intervals),
        include_funding=False,
        include_open_interest=False,
        include_ticker_24h=False,
        source_type=HistoricalDataSourceType.SYMBOL_STATUS_FILE,
    )


# --- 1. SYMBOL_STATUS_FILE only fixture -> SYMBOL_STATUS=9, no klines --


def test_symbol_status_file_only_yields_symbol_status_no_klines(tmp_path):
    root = tmp_path / "data" / "historical_raw"
    # Kline CSVs are present but MUST NOT be scanned for this source
    # type (this is exactly the cloud bug: SYMBOL_STATUS_FILE was still
    # returning the kline records).
    _write_binance_kline_csv(
        root,
        symbol="BTCUSDT",
        interval="1m",
        count=5,
        base_subdir="binance_um",
    )
    symbols = [f"COIN{i:02d}USDT" for i in range(9)]
    sidecar = _write_symbol_status_sidecar(
        root, [_sidecar_status_row(s) for s in symbols]
    )
    cfg = _symbol_status_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()

    counts = result.manifest.record_counts_by_type
    assert counts.get(HistoricalMarketRecordType.SYMBOL_STATUS) == 9
    # NO kline records, despite the kline CSV files being on disk.
    assert HistoricalMarketRecordType.KLINE_1M not in counts
    assert HistoricalMarketRecordType.KLINE_5M not in counts
    assert not any(
        isinstance(r, HistoricalKlineRecord) for r in engine.records
    )
    # The nested, date-stamped sidecar was the file actually scanned.
    assert str(sidecar) in result.manifest.source_files
    assert not any(
        s.endswith(".csv") for s in result.manifest.source_files
    )
    # No fabrication / no "missing" warning when the sidecar is found.
    assert "symbol_status_file_missing" not in result.warnings


# --- 2. kline + sidecar fixture -> KLINE + SYMBOL_STATUS both present --


def test_kline_source_type_merges_symbol_status_sidecar(tmp_path):
    root = tmp_path / "data" / "historical_raw"
    _write_binance_kline_csv(
        root,
        symbol="BTCUSDT",
        interval="1m",
        count=5,
        base_subdir="binance_um",
    )
    sidecar = _write_symbol_status_sidecar(
        root,
        [
            _sidecar_status_row("BTCUSDT"),
            _sidecar_status_row("ETHUSDT"),
        ],
    )
    cfg = HistoricalDataIngestionConfig(
        input_root=str(root),
        output_root=str(tmp_path / "out"),
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=5),
        symbols=("BTCUSDT",),
        intervals=("1m",),
        include_funding=False,
        include_open_interest=False,
        include_ticker_24h=False,
        include_exchange_info=False,
        include_symbol_status=True,
        source_type=HistoricalDataSourceType.BINANCE_PUBLIC_KLINE_FILE,
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()

    counts = result.manifest.record_counts_by_type
    assert counts[HistoricalMarketRecordType.KLINE_1M] == 5
    assert counts[HistoricalMarketRecordType.SYMBOL_STATUS] == 2
    assert any(
        isinstance(r, HistoricalKlineRecord) for r in engine.records
    )
    assert any(
        isinstance(r, SymbolStatusRecord) for r in engine.records
    )
    assert str(sidecar) in result.manifest.source_files

    # Both record types are merged into the same records.jsonl.
    written = engine.write_outputs()
    lines = [
        json.loads(ln)
        for ln in Path(written.records_path)
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    types = {ln["record_type"] for ln in lines}
    assert HistoricalMarketRecordType.KLINE_1M in types
    assert HistoricalMarketRecordType.SYMBOL_STATUS in types


# --- 3. missing sidecar -> warning, no fabrication -----------------------


def test_kline_source_missing_sidecar_warns_no_fabrication(tmp_path):
    root = tmp_path / "data" / "historical_raw"
    _write_binance_kline_csv(
        root,
        symbol="BTCUSDT",
        interval="1m",
        count=5,
        base_subdir="binance_um",
    )
    cfg = HistoricalDataIngestionConfig(
        input_root=str(root),
        output_root=str(tmp_path / "out"),
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=5),
        symbols=("BTCUSDT",),
        intervals=("1m",),
        include_funding=False,
        include_open_interest=False,
        include_ticker_24h=False,
        include_exchange_info=False,
        include_symbol_status=True,
        source_type=HistoricalDataSourceType.BINANCE_PUBLIC_KLINE_FILE,
    )
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()

    # The sidecar is missing: warn, never fabricate a status record.
    assert "symbol_status_file_missing" in result.warnings
    assert (
        HistoricalMarketRecordType.SYMBOL_STATUS
        not in result.manifest.record_counts_by_type
    )
    assert not any(
        isinstance(r, SymbolStatusRecord) for r in engine.records
    )
    # Klines are still ingested - a missing sidecar never blocks them.
    assert result.manifest.record_counts_by_type[
        HistoricalMarketRecordType.KLINE_1M
    ] == 5


def test_symbol_status_file_missing_returns_insufficient_evidence(
    tmp_path,
):
    root = tmp_path / "data" / "historical_raw"
    root.mkdir(parents=True, exist_ok=True)
    cfg = _symbol_status_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    assert result.status == DataIngestionStatus.INSUFFICIENT_EVIDENCE
    assert result.ingested_record_count == 0
    assert result.manifest.record_counts_by_type == {}
    assert "symbol_status_file_missing" in result.warnings
    assert any(
        "NOT fabricating real market data" in w
        for w in result.warnings
    )


# --- 4. universe_manifest symbols / listed_count / unknown correct -------


def test_symbol_status_file_universe_manifest_counts(tmp_path):
    root = tmp_path / "data" / "historical_raw"
    symbols = [f"COIN{i:02d}USDT" for i in range(9)]
    rows = [_sidecar_status_row(s) for s in symbols[:8]]
    # One symbol with an UNKNOWN status -> status_unknown_count == 1.
    rows.append(
        _sidecar_status_row(symbols[8], status=SymbolStatus.UNKNOWN)
    )
    _write_symbol_status_sidecar(root, rows)
    cfg = _symbol_status_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()

    um = result.universe_manifest
    assert list(um.symbols) == sorted(symbols)
    assert um.listed_count == 8
    assert um.status_unknown_count == 1
    assert um.delisted_count == 0
    # The universe manifest carries the 9 status records and is not
    # empty (the empty-universe warning must be absent).
    assert len(um.symbol_status_records) == 9
    udict = um.to_dict()
    assert udict["listed_count"] == 8
    assert udict["status_unknown_count"] == 1
    assert udict["symbols"] == sorted(symbols)
    assert not any(
        "universe_empty" in w for w in um.warnings
    )


# --- direct parser: sidecar schema without listed_at --------------------


def test_parse_symbol_status_sidecar_schema_anchors_to_event_time():
    et = _T0 - timedelta(days=2)
    av = _T0 - timedelta(days=1)
    rec = parse_symbol_status_row(
        {
            "symbol": "BTCUSDT",
            "status": SymbolStatus.TRADING,
            "event_time": et.isoformat(),
            "available_at": av.isoformat(),
            "ingested_at": _GEN.isoformat(),
            "source": "ignored-by-parser",
        }
    )
    assert isinstance(rec, SymbolStatusRecord)
    assert rec.symbol == "BTCUSDT"
    assert rec.status == SymbolStatus.TRADING
    # listed_at is anchored to event_time (never fabricated, never
    # derived from ingested_at) and market_type defaults to UNKNOWN.
    assert rec.listed_at == et
    assert rec.event_time == et
    assert rec.available_at == av
    assert rec.ingested_at == _GEN
    assert rec.market_type == "UNKNOWN"
    assert rec.record_type == HistoricalMarketRecordType.SYMBOL_STATUS


def test_parse_symbol_status_row_without_any_time_is_rejected():
    # No listed_at / event_time / available_at -> cannot anchor a real
    # listing time; reject rather than fabricate.
    with pytest.raises(IngestionTimeFieldError):
        parse_symbol_status_row(
            {"symbol": "BTCUSDT", "status": SymbolStatus.TRADING}
        )


# --- 5. safety flags intact for the SYMBOL_STATUS_FILE path --------------


def test_symbol_status_file_safety_flags_intact(tmp_path):
    root = tmp_path / "data" / "historical_raw"
    _write_symbol_status_sidecar(
        root,
        [
            _sidecar_status_row("BTCUSDT"),
            _sidecar_status_row("ETHUSDT"),
        ],
    )
    cfg = _symbol_status_config(tmp_path, input_root=root)
    engine = HistoricalDataIngestion(cfg, generated_at_utc=_GEN)
    result = engine.ingest()
    for payload in (
        result.to_dict(),
        result.manifest.to_dict(),
        result.universe_manifest.to_dict(),
        engine.coverage_report(),
        engine.data_gap_report(),
        cfg.to_dict(),
        engine.safety_payload(),
    ):
        assert payload["phase_12_forbidden"] is True
        assert payload["live_trading"] is False
        assert payload["exchange_live_orders"] is False
        assert payload["binance_private_api_enabled"] is False
        assert payload["telegram_outbound_enabled"] is False
        assert payload["ai_trade_authority"] is False
        assert payload["auto_tuning_allowed"] is False
        assert payload["trade_authority"] is False
    # No forbidden field keys leak into any SYMBOL_STATUS_FILE payload.
    for payload in (
        result.to_dict(),
        result.manifest.to_dict(),
        result.universe_manifest.to_dict(),
    ):
        for key in _walk_keys(payload):
            assert key not in ALL_FORBIDDEN_KEYS


# --- scanner: flat-root and direct symbol_status/ layouts also work ------


def test_symbol_status_scanner_flat_and_direct_subdir_layouts(tmp_path):
    # Flat root file (legacy fixture layout) is still discovered.
    flat_root = tmp_path / "flat"
    flat_root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        flat_root / "symbol_status.jsonl",
        [_sidecar_status_row("BTCUSDT")],
    )
    cfg_flat = _symbol_status_config(tmp_path, input_root=flat_root)
    res_flat = HistoricalDataIngestion(
        cfg_flat, generated_at_utc=_GEN
    ).ingest()
    assert (
        res_flat.manifest.record_counts_by_type[
            HistoricalMarketRecordType.SYMBOL_STATUS
        ]
        == 1
    )

    # Direct <root>/symbol_status/*.jsonl layout (no nesting).
    direct_root = tmp_path / "direct"
    _write_symbol_status_sidecar(
        direct_root,
        [_sidecar_status_row("BTCUSDT"), _sidecar_status_row("ETHUSDT")],
        base_subdir=None,
    )
    cfg_direct = _symbol_status_config(
        tmp_path, input_root=direct_root
    )
    res_direct = HistoricalDataIngestion(
        cfg_direct, generated_at_utc=_GEN
    ).ingest()
    assert (
        res_direct.manifest.record_counts_by_type[
            HistoricalMarketRecordType.SYMBOL_STATUS
        ]
        == 2
    )
