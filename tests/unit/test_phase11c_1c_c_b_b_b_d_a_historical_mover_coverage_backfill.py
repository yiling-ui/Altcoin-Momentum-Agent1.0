"""Phase 11C.1C-C-B-B-B-D-A - Historical 60D Mover Coverage Backfill
Audit v0 unit tests.

Test plan (mirrors the brief's acceptance list):

  - test_historical_mover_reference_set_contract
  - test_historical_mover_reference_excludes_non_futures
  - test_historical_capture_records_first_seen_time
  - test_historical_capture_path_detects_captured_mover
  - test_historical_capture_path_detects_partially_captured_mover
  - test_historical_capture_path_detects_missed_mover
  - test_historical_miss_reason_missing_event_history
  - test_historical_miss_reason_not_in_exchange_info
  - test_historical_miss_reason_risk_rejected
  - test_historical_mover_coverage_metrics
  - test_historical_mover_payload_roundtrip
  - test_historical_mover_events_exportable
  - test_daily_report_contains_historical_60d_section
  - test_lookahead_guard_rejects_completed_tail_label_as_reference_input
  - test_lookahead_guard_rejects_future_return_in_live_capture_source
  - test_historical_coverage_does_not_trigger_execution
  - test_no_live_trading_flags_unchanged
  - test_phase_12_remains_forbidden

The audit is paper / report / evidence only. None of these tests
authorise a real trade or flip a Phase 1 safety flag.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adaptive.historical_mover_coverage_backfill import (
    DEFAULT_MIN_HISTORY_DAYS,
    DEFAULT_REFERENCE_WINDOW_DAYS,
    HISTORICAL_CAPTURE_EVENT_ORDER,
    HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
    LOOKAHEAD_FORBIDDEN_FIELDS,
    HistoricalMoverCapturePath,
    HistoricalMoverCoverageBackfillInput,
    HistoricalMoverCoverageBackfillRuntime,
    HistoricalMoverCoverageBackfillStatus,
    HistoricalMoverCoverageRecord,
    HistoricalMoverCoverageStatus,
    HistoricalMoverLookaheadGuardError,
    HistoricalMoverMissReason,
    HistoricalMoverReference,
    HistoricalMoverReferenceSet,
    assert_capture_event_is_past_or_equal_reference_window,
    audit_historical_mover_capture_path,
    build_historical_60d_mover_reference_set,
    build_historical_mover_coverage_backfill_report,
    classify_historical_miss_reason,
    export_historical_mover_coverage_payload,
    load_historical_market_store,
    load_historical_mover_coverage_payload,
    validate_no_lookahead_fields,
)
from app.core.events import Event, EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.paper_run.daily_report import DailyReportBuilder


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def events_repo(tmp_path: Path) -> EventRepository:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital)


def _ms(day: int, hour: int = 0) -> int:
    """Return a deterministic UTC ms timestamp anchored at 2026-01-01."""
    base_ms = 1_767_225_600_000  # 2026-01-01T00:00:00Z (approx)
    return base_ms + (day * 24 + hour) * 60 * 60 * 1000


def _build_reference(
    *,
    symbol: str,
    day: int,
    rank: int = 1,
    max_window_gain: float = 0.85,
    eligible: bool = True,
    not_eligible_reason: str | None = None,
) -> HistoricalMoverReference:
    ref_ts = _ms(day, hour=23)
    return HistoricalMoverReference(
        symbol=symbol,
        reference_timestamp_utc_ms=ref_ts,
        mover_window_start_utc_ms=_ms(day, hour=0),
        mover_window_end_utc_ms=ref_ts,
        eligible_usdt_perpetual=eligible,
        not_eligible_reason=not_eligible_reason,
        top_mover_rank=rank,
        max_window_gain=max_window_gain,
        max_24h_gain=0.5,
        quote_volume_usdt=12_000_000.0,
    )


def _seed_events(
    repo: EventRepository,
    *,
    symbol: str,
    day: int,
    types: list[EventType],
) -> None:
    base = _ms(day, hour=8)
    for offset, et in enumerate(types):
        repo.append(
            Event(
                event_type=et,
                source_module="test.fixture",
                payload={"symbol": symbol},
                symbol=symbol,
                timestamp=base + offset * 60_000,
            )
        )


def _build_input(
    *,
    references: list[HistoricalMoverReference],
    audit_end_day: int = 65,
    reference_window_days: int = 60,
    history_days_observed: int = 30,
    exchange_info_symbols: frozenset[str] | None = None,
) -> HistoricalMoverCoverageBackfillInput:
    audit_end_ms = _ms(audit_end_day)
    window_start_ms = (
        audit_end_ms - reference_window_days * 24 * 60 * 60 * 1000
    )
    reference_set = HistoricalMoverReferenceSet(
        reference_window_days=reference_window_days,
        window_start_utc_ms=window_start_ms,
        window_end_utc_ms=audit_end_ms,
        references=tuple(references),
        history_days_observed=history_days_observed,
    )
    return HistoricalMoverCoverageBackfillInput(
        reference_set=reference_set,
        audit_window_end_utc_ms=audit_end_ms,
        reference_window_days=reference_window_days,
        exchange_info_symbols=(
            exchange_info_symbols
            if exchange_info_symbols is not None
            else frozenset({r.symbol for r in references})
        ),
        history_days_observed=history_days_observed,
        min_history_days=DEFAULT_MIN_HISTORY_DAYS,
    )


# ---------------------------------------------------------------------------
# 1. Reference set contract + universe filter
# ---------------------------------------------------------------------------


def test_historical_mover_reference_set_contract() -> None:
    rows = [
        {
            "symbol": "FOOUSDT",
            "snapshot_date": "2026-02-01",
            "reference_timestamp_utc_ms": _ms(31),
            "mover_window_start_utc_ms": _ms(30),
            "mover_window_end_utc_ms": _ms(31),
            "top_mover_rank": 1,
            "max_window_gain": 5.2,
            "max_24h_gain": 0.45,
            "quote_volume_usdt": 81_234_567.0,
            "quote_asset": "USDT",
            "contract_type": "PERPETUAL",
        },
        {
            "symbol": "BARUSDT",
            "snapshot_date": "2026-02-01",
            "reference_timestamp_utc_ms": _ms(31),
            "mover_window_start_utc_ms": _ms(30),
            "mover_window_end_utc_ms": _ms(31),
            "top_mover_rank": 2,
            "max_window_gain": 3.1,
            "quote_asset": "USDT",
            "contract_type": "PERPETUAL",
        },
    ]
    ref_set = build_historical_60d_mover_reference_set(
        top_mover_rows=rows,
        audit_window_end_utc_ms=_ms(60),
        reference_window_days=60,
        exchange_info_symbols=frozenset({"FOOUSDT", "BARUSDT"}),
    )
    assert isinstance(ref_set, HistoricalMoverReferenceSet)
    assert ref_set.reference_window_days == 60
    assert ref_set.total_count == 2
    assert ref_set.eligible_count == 2
    assert ref_set.excluded_count == 0
    payload = ref_set.to_dict()
    assert (
        payload["schema_version"]
        == HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION
    )
    assert len(payload["references"]) == 2
    assert payload["references"][0]["symbol"] in {"FOOUSDT", "BARUSDT"}


def test_historical_mover_reference_excludes_non_futures() -> None:
    rows = [
        {
            "symbol": "FOOUSDT",
            "snapshot_date": "2026-02-01",
            "reference_timestamp_utc_ms": _ms(31),
            "top_mover_rank": 1,
            "max_window_gain": 5.2,
            "quote_asset": "USDT",
            "contract_type": "PERPETUAL",
        },
        {
            "symbol": "ALIENBTC",
            "snapshot_date": "2026-02-01",
            "reference_timestamp_utc_ms": _ms(31),
            "top_mover_rank": 2,
            "max_window_gain": 3.1,
            "quote_asset": "BTC",
            "contract_type": "PERPETUAL",
        },
        {
            "symbol": "GHOSTUSDT",
            "snapshot_date": "2026-02-01",
            "reference_timestamp_utc_ms": _ms(31),
            "top_mover_rank": 3,
            "max_window_gain": 2.0,
            "quote_asset": "USDT",
            "contract_type": "PERPETUAL",
        },
    ]
    # GHOSTUSDT is NOT in exchangeInfo - should be excluded.
    ref_set = build_historical_60d_mover_reference_set(
        top_mover_rows=rows,
        audit_window_end_utc_ms=_ms(60),
        reference_window_days=60,
        exchange_info_symbols=frozenset({"FOOUSDT", "ALIENBTC"}),
    )
    by_symbol = {r.symbol: r for r in ref_set.references}
    assert by_symbol["FOOUSDT"].eligible_usdt_perpetual is True
    assert by_symbol["ALIENBTC"].eligible_usdt_perpetual is False
    assert (
        by_symbol["ALIENBTC"].not_eligible_reason
        == HistoricalMoverMissReason.NOT_USDT_PERPETUAL
    )
    assert by_symbol["GHOSTUSDT"].eligible_usdt_perpetual is False
    assert (
        by_symbol["GHOSTUSDT"].not_eligible_reason
        == HistoricalMoverMissReason.SYMBOL_NOT_IN_EXCHANGE_INFO
    )


# ---------------------------------------------------------------------------
# 2. Capture path
# ---------------------------------------------------------------------------


def test_historical_capture_records_first_seen_time(
    events_repo: EventRepository,
) -> None:
    ref = _build_reference(symbol="EARLYUSDT", day=20)
    _seed_events(
        events_repo,
        symbol="EARLYUSDT",
        day=20,
        types=[
            EventType.MARKET_SNAPSHOT,
            EventType.PRE_ANOMALY_DETECTED,
            EventType.ANOMALY_DETECTED,
            EventType.MARKET_REGIME_ASSESSED,
            EventType.CANDIDATE_STAGE_CLASSIFIED,
            EventType.OPPORTUNITY_SCORED,
            EventType.STRATEGY_MODE_SELECTED,
            EventType.LABEL_QUEUE_ENQUEUED,
            EventType.LABEL_TRACKING_STARTED,
            EventType.TAIL_LABEL_ASSIGNED,
        ],
    )
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    assert len(report.records) == 1
    record = report.records[0]
    cap = record.capture_path
    assert cap.first_seen_event_type == EventType.MARKET_SNAPSHOT.value
    assert cap.first_seen_time_utc_ms is not None
    assert cap.first_seen_latency_seconds is not None
    # Saw it earlier than reference timestamp -> negative latency.
    assert cap.first_seen_latency_seconds < 0
    # All event types expected -> capture_path_depth equals the
    # zero-based index of the deepest hit.
    assert cap.capture_path_depth >= len(HISTORICAL_CAPTURE_EVENT_ORDER) - 5


def test_historical_capture_path_detects_captured_mover(
    events_repo: EventRepository,
) -> None:
    ref = _build_reference(symbol="WINUSDT", day=10)
    _seed_events(
        events_repo,
        symbol="WINUSDT",
        day=10,
        types=[
            EventType.PRE_ANOMALY_DETECTED,
            EventType.ANOMALY_DETECTED,
            EventType.LABEL_QUEUE_ENQUEUED,
            EventType.LABEL_TRACKING_STARTED,
            EventType.TAIL_LABEL_ASSIGNED,
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
        ],
    )
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    record = report.records[0]
    assert record.coverage_status == HistoricalMoverCoverageStatus.CAPTURED
    assert record.miss_reason is None
    assert record.miss_reasons == ()
    assert record.capture_path.reached_anomaly is True
    assert record.capture_path.reached_label_queue is True
    assert record.capture_path.reached_tail_label is True
    assert record.capture_path.reached_strategy_validation_sample is True


def test_historical_capture_path_detects_partially_captured_mover(
    events_repo: EventRepository,
) -> None:
    ref = _build_reference(symbol="HALFUSDT", day=15)
    _seed_events(
        events_repo,
        symbol="HALFUSDT",
        day=15,
        types=[
            EventType.PRE_ANOMALY_DETECTED,
            EventType.ANOMALY_DETECTED,
        ],
    )
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    record = report.records[0]
    assert (
        record.coverage_status
        == HistoricalMoverCoverageStatus.PARTIALLY_CAPTURED
    )
    assert record.capture_path.reached_anomaly is True
    assert record.capture_path.reached_label_queue is False
    # The classifier should call out "anomaly seen but never enqueued".
    assert HistoricalMoverMissReason.UNKNOWN in record.miss_reasons


def test_historical_capture_path_detects_missed_mover(
    events_repo: EventRepository,
) -> None:
    ref = _build_reference(symbol="MISSUSDT", day=25)
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    record = report.records[0]
    assert record.coverage_status == HistoricalMoverCoverageStatus.MISSED
    assert record.capture_path.observed_event_count == 0
    assert (
        record.miss_reason == HistoricalMoverMissReason.MISSING_EVENT_HISTORY
    )


# ---------------------------------------------------------------------------
# 3. Miss reason taxonomy
# ---------------------------------------------------------------------------


def test_historical_miss_reason_missing_event_history() -> None:
    ref = _build_reference(symbol="VOIDUSDT", day=5)
    cap = HistoricalMoverCapturePath(
        symbol="VOIDUSDT",
        first_seen_time_utc_ms=None,
        first_seen_event_type=None,
        first_seen_latency_seconds=None,
        capture_path_depth=0,
        reached_anomaly=False,
        reached_label_queue=False,
        reached_tail_label=False,
        reached_strategy_validation_sample=False,
        risk_rejected=False,
        data_unreliable=False,
        observed_event_types=(),
        observed_event_count=0,
    )
    primary, reasons = classify_historical_miss_reason(
        reference=ref, capture_path=cap
    )
    assert primary == HistoricalMoverMissReason.MISSING_EVENT_HISTORY
    assert reasons == (HistoricalMoverMissReason.MISSING_EVENT_HISTORY,)


def test_historical_miss_reason_not_in_exchange_info() -> None:
    ref = _build_reference(
        symbol="GHOSTUSDT",
        day=5,
        eligible=False,
        not_eligible_reason=HistoricalMoverMissReason.SYMBOL_NOT_IN_EXCHANGE_INFO,
    )
    cap = HistoricalMoverCapturePath(
        symbol="GHOSTUSDT",
        first_seen_time_utc_ms=None,
        first_seen_event_type=None,
        first_seen_latency_seconds=None,
        capture_path_depth=0,
        reached_anomaly=False,
        reached_label_queue=False,
        reached_tail_label=False,
        reached_strategy_validation_sample=False,
        risk_rejected=False,
        data_unreliable=False,
        observed_event_types=(),
        observed_event_count=0,
    )
    primary, reasons = classify_historical_miss_reason(
        reference=ref, capture_path=cap
    )
    assert primary == HistoricalMoverMissReason.SYMBOL_NOT_IN_EXCHANGE_INFO
    assert HistoricalMoverMissReason.SYMBOL_NOT_IN_EXCHANGE_INFO in reasons


def test_historical_miss_reason_risk_rejected(
    events_repo: EventRepository,
) -> None:
    ref = _build_reference(symbol="RJCTUSDT", day=12)
    _seed_events(
        events_repo,
        symbol="RJCTUSDT",
        day=12,
        types=[
            EventType.PRE_ANOMALY_DETECTED,
            EventType.ANOMALY_DETECTED,
            EventType.LABEL_QUEUE_ENQUEUED,
            EventType.RISK_REJECTED,
        ],
    )
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    record = report.records[0]
    assert record.capture_path.risk_rejected is True
    assert HistoricalMoverMissReason.RISK_REJECTED in record.miss_reasons
    assert report.risk_rejected_mover_count == 1


# ---------------------------------------------------------------------------
# 4. Metric roll-up
# ---------------------------------------------------------------------------


def test_historical_mover_coverage_metrics(
    events_repo: EventRepository,
) -> None:
    captured = _build_reference(symbol="CAPUSDT", day=10)
    _seed_events(
        events_repo,
        symbol="CAPUSDT",
        day=10,
        types=[
            EventType.ANOMALY_DETECTED,
            EventType.LABEL_QUEUE_ENQUEUED,
            EventType.LABEL_TRACKING_STARTED,
            EventType.TAIL_LABEL_ASSIGNED,
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
        ],
    )
    partial = _build_reference(symbol="PARTUSDT", day=12)
    _seed_events(
        events_repo,
        symbol="PARTUSDT",
        day=12,
        types=[
            EventType.PRE_ANOMALY_DETECTED,
            EventType.ANOMALY_DETECTED,
        ],
    )
    missed = _build_reference(symbol="MISSUSDT", day=14)
    excluded = _build_reference(
        symbol="EXCLUDED1USDT",
        day=16,
        eligible=False,
        not_eligible_reason=HistoricalMoverMissReason.SYMBOL_NOT_IN_EXCHANGE_INFO,
    )
    audit_input = _build_input(
        references=[captured, partial, missed, excluded]
    )
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)

    assert report.top_mover_count == 4
    assert report.eligible_top_mover_count == 3
    assert report.captured_top_mover_count == 1
    assert report.partially_captured_top_mover_count == 1
    assert report.missed_top_mover_count == 1
    assert report.excluded_top_mover_count == 1
    assert 0.0 <= report.capture_recall_rate <= 1.0
    assert pytest.approx(report.capture_recall_rate, abs=1e-9) == 1.0 / 3.0
    assert pytest.approx(report.partial_capture_rate, abs=1e-9) == 1.0 / 3.0
    assert pytest.approx(report.miss_rate, abs=1e-9) == 1.0 / 3.0

    metrics = runtime.metrics_payload()
    assert metrics["captured_top_mover_count"] == 1
    assert metrics["historical_mover_coverage_backfill_generated_count"] == 0
    assert metrics["report"]["captured_top_mover_count"] == 1


# ---------------------------------------------------------------------------
# 5. Payload roundtrip
# ---------------------------------------------------------------------------


def test_historical_mover_payload_roundtrip(
    events_repo: EventRepository,
) -> None:
    ref = _build_reference(symbol="ROUNDUSDT", day=10)
    _seed_events(
        events_repo,
        symbol="ROUNDUSDT",
        day=10,
        types=[EventType.ANOMALY_DETECTED, EventType.LABEL_QUEUE_ENQUEUED],
    )
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    payload = export_historical_mover_coverage_payload(report)
    rebuilt = load_historical_mover_coverage_payload(payload)
    assert rebuilt.schema_version == report.schema_version
    assert rebuilt.backfill_status == report.backfill_status
    assert rebuilt.top_mover_count == report.top_mover_count
    assert rebuilt.captured_top_mover_count == report.captured_top_mover_count
    assert (
        rebuilt.partially_captured_top_mover_count
        == report.partially_captured_top_mover_count
    )
    assert len(rebuilt.records) == len(report.records)
    assert rebuilt.records[0].symbol == "ROUNDUSDT"
    # JSON-roundtrip too.
    rejson = json.loads(json.dumps(payload))
    rebuilt2 = load_historical_mover_coverage_payload(rejson)
    assert rebuilt2.records[0].symbol == "ROUNDUSDT"


# ---------------------------------------------------------------------------
# 6. Event emission + export
# ---------------------------------------------------------------------------


def test_historical_mover_events_exportable(
    events_repo: EventRepository,
) -> None:
    refs = [
        _build_reference(symbol="ALPHAUSDT", day=10),
        _build_reference(symbol="BETAUSDT", day=12),
    ]
    _seed_events(
        events_repo,
        symbol="ALPHAUSDT",
        day=10,
        types=[EventType.ANOMALY_DETECTED, EventType.LABEL_QUEUE_ENQUEUED],
    )
    audit_input = _build_input(references=refs)
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=True)
    assert report.top_mover_count == 2

    backfill_events = events_repo.list_events(
        event_type=EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED
    )
    record_events = events_repo.list_events(
        event_type=EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED
    )
    assert len(backfill_events) == 1
    assert len(record_events) == 2
    # Payload schema version must travel verbatim with the event.
    assert (
        backfill_events[0].payload["schema_version"]
        == HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION
    )
    # Per-record events carry the per-mover symbol.
    record_symbols = {ev.symbol for ev in record_events}
    assert record_symbols == {"ALPHAUSDT", "BETAUSDT"}


# ---------------------------------------------------------------------------
# 7. Daily report integration
# ---------------------------------------------------------------------------


def test_daily_report_contains_historical_60d_section(
    tmp_path: Path,
    events_repo: EventRepository,
) -> None:
    ref = _build_reference(symbol="REPORTUSDT", day=10)
    _seed_events(
        events_repo,
        symbol="REPORTUSDT",
        day=10,
        types=[
            EventType.ANOMALY_DETECTED,
            EventType.LABEL_QUEUE_ENQUEUED,
            EventType.TAIL_LABEL_ASSIGNED,
        ],
    )
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    runtime.flush(audit_input, emit_events=True)
    metrics = runtime.metrics_payload()

    out_dir = tmp_path / "reports"
    builder = DailyReportBuilder(
        event_repo=events_repo,
        output_dir=out_dir,
    )
    snapshot = builder.build(
        started_at_ms=_ms(0),
        finished_at_ms=_ms(60),
        write_to_disk=False,
        historical_mover_coverage_metrics=metrics,
    )

    text = snapshot.markdown
    assert "Historical 60D Mover Coverage Backfill Audit" in text
    assert "HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED" in text
    assert "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED" in text
    assert "Historical capture recall rate" in text
    assert "Lookahead Guard" in text or "lookahead-guard" in text.lower()
    assert "first_seen_time_utc" in text
    assert "REPORTUSDT" in text


# ---------------------------------------------------------------------------
# 8. Lookahead Guard
# ---------------------------------------------------------------------------


def test_lookahead_guard_rejects_completed_tail_label_as_reference_input() -> None:
    bad_row = {
        "symbol": "FUTUREUSDT",
        "snapshot_date": "2026-02-01",
        "reference_timestamp_utc_ms": _ms(31),
        "top_mover_rank": 1,
        "max_window_gain": 5.2,
        "completed_tail_label": "strong_tail",  # forbidden lookahead column
    }
    with pytest.raises(HistoricalMoverLookaheadGuardError):
        validate_no_lookahead_fields(bad_row, context="reference[FUTUREUSDT]")
    with pytest.raises(HistoricalMoverLookaheadGuardError):
        build_historical_60d_mover_reference_set(
            top_mover_rows=[bad_row],
            audit_window_end_utc_ms=_ms(60),
            reference_window_days=60,
            exchange_info_symbols=frozenset({"FUTUREUSDT"}),
        )


def test_lookahead_guard_rejects_future_return_in_live_capture_source() -> None:
    bad_row = {
        "symbol": "POSTUSDT",
        "future_return": 4.5,  # forbidden lookahead column
    }
    with pytest.raises(HistoricalMoverLookaheadGuardError):
        validate_no_lookahead_fields(bad_row, context="capture_source")

    # Likewise the per-event window assertion rejects events past the
    # reference-window end with no grace period.
    with pytest.raises(HistoricalMoverLookaheadGuardError):
        assert_capture_event_is_past_or_equal_reference_window(
            event_timestamp_ms=_ms(120),
            reference_window_start_ms=_ms(0),
            reference_window_end_ms=_ms(60),
            grace_seconds_after=60,
            context="late-event",
        )


def test_forbidden_lookahead_field_list_is_complete() -> None:
    must_have = {
        "completed_tail_label",
        "final_max_gain",
        "future_return",
        "settled_tail_outcome",
    }
    assert must_have.issubset(set(LOOKAHEAD_FORBIDDEN_FIELDS))


# ---------------------------------------------------------------------------
# 9. Historical Market Store loader
# ---------------------------------------------------------------------------


def test_load_historical_market_store_reads_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "store"
    (root / "top_movers").mkdir(parents=True)
    (root / "exchange_info").mkdir(parents=True)
    (root / "top_movers" / "2026-02-01.jsonl").write_text(
        json.dumps(
            {
                "symbol": "FOOUSDT",
                "snapshot_date": "2026-02-01",
                "reference_timestamp_utc_ms": _ms(31),
                "top_mover_rank": 1,
                "max_window_gain": 4.2,
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "exchange_info" / "2026-02-01.jsonl").write_text(
        json.dumps(
            {"symbols": ["FOOUSDT", "BARUSDT"]}
        )
        + "\n",
        encoding="utf-8",
    )
    snap = load_historical_market_store(root)
    assert snap.history_days_observed == 1
    assert "FOOUSDT" in snap.exchange_info_symbols
    assert any(row["symbol"] == "FOOUSDT" for row in snap.top_mover_rows)


def test_load_historical_market_store_rejects_lookahead_jsonl(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    (root / "top_movers").mkdir(parents=True)
    (root / "top_movers" / "bad.jsonl").write_text(
        json.dumps(
            {
                "symbol": "BADUSDT",
                "completed_tail_label": "strong_tail",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(HistoricalMoverLookaheadGuardError):
        load_historical_market_store(root)


# ---------------------------------------------------------------------------
# 10. Boundary / safety
# ---------------------------------------------------------------------------


def test_historical_coverage_does_not_trigger_execution(
    events_repo: EventRepository,
) -> None:
    """The audit must NEVER emit a trade-decision event."""

    ref = _build_reference(symbol="SAFEUSDT", day=10)
    _seed_events(
        events_repo,
        symbol="SAFEUSDT",
        day=10,
        types=[EventType.ANOMALY_DETECTED, EventType.LABEL_QUEUE_ENQUEUED],
    )
    audit_input = _build_input(references=[ref])
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    runtime.flush(audit_input, emit_events=True)

    # No trade / order / position / risk-decision event must have been
    # appended by the audit runtime.
    forbidden_types = {
        EventType.ORDER_SENT,
        EventType.ORDER_ACK,
        EventType.ORDER_FILLED,
        EventType.STOP_SENT,
        EventType.POSITION_OPENED,
        EventType.RISK_APPROVED,
        EventType.STATE_TRANSITION,
        EventType.CAPITAL_REBASE,
    }
    for et in forbidden_types:
        rows = events_repo.list_events(event_type=et)
        for ev in rows:
            assert ev.source_module != (
                "app.adaptive.historical_mover_coverage_backfill"
            ), (
                f"audit must not emit {et.value} events, but found one "
                f"sourced from the audit module"
            )


def test_no_live_trading_flags_unchanged() -> None:
    """The Phase 1 safety flags MUST remain off after running the
    audit. We assert the import-time defaults of
    :mod:`app.config.settings` to belt-and-braces the boundary."""

    from app.config import settings as settings_mod

    settings = settings_mod.get_settings()
    assert settings.trading_mode == "paper"
    assert bool(settings.live_trading_enabled) is False
    assert bool(settings.right_tail_enabled) is False
    assert bool(settings.llm_enabled) is False
    assert bool(settings.exchange_live_order_enabled) is False
    # The brief mandates these flags remain off; the Settings object
    # exposes the ones the Phase 1 safety lock actually owns. Any
    # additional brief-mandated boundary (binance_private_api,
    # telegram_outbound) is enforced separately by the env-guard +
    # paper_run no-network test suite, not by the Settings accessor.


def test_phase_12_remains_forbidden() -> None:
    """The phase-gate documents must continue to mark Phase 12 as
    FORBIDDEN."""

    project_root = Path(__file__).resolve().parents[2]
    phase_gate = (project_root / "docs" / "PHASE_GATE.md").read_text(
        encoding="utf-8"
    )
    assert "Phase 12" in phase_gate
    # The phase-gate document MUST still flag Phase 12 as forbidden /
    # not authorised.
    assert (
        "FORBIDDEN" in phase_gate
        or "forbidden" in phase_gate
        or "NOT_AUTHORISED" in phase_gate
        or "not authorised" in phase_gate.lower()
    )


def test_top_level_status_is_insufficient_history_when_short(
    events_repo: EventRepository,
) -> None:
    """If the local Historical Market Store covers fewer days than
    ``min_history_days``, the runtime emits ``INSUFFICIENT_HISTORY``."""

    ref = _build_reference(symbol="SHORTUSDT", day=5)
    audit_input = _build_input(references=[ref], history_days_observed=2)
    runtime = HistoricalMoverCoverageBackfillRuntime(event_repo=events_repo)
    report = runtime.flush(audit_input, emit_events=False)
    assert (
        report.backfill_status
        == HistoricalMoverCoverageBackfillStatus.INSUFFICIENT_HISTORY
    )
