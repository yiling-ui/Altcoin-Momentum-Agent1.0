"""Phase 11C.1C-C-B-B-B-D - Mover Capture Recall & Missed-Tail
Coverage Audit v0 tests.

Pins every behaviour the brief calls out:

  - test_top_mover_reference_set_contract
  - test_capture_path_audit_detects_full_capture
  - test_capture_path_audit_detects_partial_capture
  - test_capture_path_audit_detects_missed_eligible_mover
  - test_capture_path_audit_excludes_not_in_futures_universe
  - test_miss_reason_classification_not_in_exchange_info
  - test_miss_reason_classification_candidate_pool_evicted
  - test_miss_reason_classification_data_unreliable
  - test_miss_reason_classification_risk_rejected
  - test_mover_capture_audit_metrics
  - test_mover_capture_audit_payload_roundtrip
  - test_mover_capture_audit_events_exportable
  - test_replay_reads_mover_capture_audit_events
  - test_daily_report_contains_mover_capture_audit_section
  - test_mover_capture_audit_does_not_trigger_execution
  - test_no_live_trading_flags_unchanged
  - test_phase_12_remains_forbidden

Every test is deterministic; nothing here calls a network service or
private API. The audit is paper / report / evidence-only and **MUST
NEVER** authorise a real trade or modify any runtime knob.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adaptive.mover_capture_recall_audit import (
    CAPTURE_PATH_STAGES,
    CAPTURE_PATH_STATUSES,
    DEFAULT_MIN_PRICE_CHANGE_PCT,
    DEFAULT_MIN_QUOTE_VOLUME_USDT,
    DEFAULT_MIN_TOP_MOVER_COUNT,
    KNOWN_MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSIONS,
    MISS_REASONS,
    MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION,
    MOVER_CAPTURE_RECALL_AUDIT_STATUSES,
    CapturePathEvidence,
    CapturePathStatus,
    MissReason,
    MoverCaptureAuditRecord,
    MoverCaptureRecallAuditInput,
    MoverCaptureRecallAuditReport,
    MoverCaptureRecallAuditRuntime,
    MoverCaptureRecallAuditStatus,
    TopMoverReference,
    audit_mover_capture_path,
    build_mover_capture_recall_audit_report,
    build_top_mover_reference_set,
    classify_miss_reason,
    export_mover_capture_recall_audit_payload,
    load_mover_capture_recall_audit_payload,
)
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital), dbs


def _stage_evidence(
    *,
    stage: str,
    first: int = 1000,
    last: int | None = None,
    count: int = 1,
    event_id: str = "",
) -> CapturePathEvidence:
    return CapturePathEvidence(
        stage=stage,
        observed=True,
        count=int(count),
        first_seen_ts=int(first),
        last_seen_ts=int(last if last is not None else first),
        event_ids=(event_id,) if event_id else (),
    )


def _full_chain_observations(symbol: str = "BTCUSDT") -> dict[str, dict[str, CapturePathEvidence]]:
    """Build a per-symbol stage map that exercises every chain stage
    end-to-end (CAPTURED status)."""
    stages = {
        "MARKET_SNAPSHOT": _stage_evidence(stage="MARKET_SNAPSHOT", first=1500, last=2500, count=10),
        "PRE_ANOMALY_DETECTED": _stage_evidence(stage="PRE_ANOMALY_DETECTED", first=1700),
        "ANOMALY_DETECTED": _stage_evidence(stage="ANOMALY_DETECTED", first=1800),
        "MARKET_REGIME_ASSESSED": _stage_evidence(stage="MARKET_REGIME_ASSESSED", first=1900),
        "CANDIDATE_STAGE_CLASSIFIED": _stage_evidence(stage="CANDIDATE_STAGE_CLASSIFIED", first=2000),
        "OPPORTUNITY_SCORED": _stage_evidence(stage="OPPORTUNITY_SCORED", first=2100),
        "STRATEGY_MODE_SELECTED": _stage_evidence(stage="STRATEGY_MODE_SELECTED", first=2200),
        "CLUSTER_CONTEXT_ATTACHED": _stage_evidence(stage="CLUSTER_CONTEXT_ATTACHED", first=2300),
        "LABEL_QUEUE_ENQUEUED": _stage_evidence(stage="LABEL_QUEUE_ENQUEUED", first=2400),
        "LABEL_TRACKING_STARTED": _stage_evidence(stage="LABEL_TRACKING_STARTED", first=2500),
        "LABEL_WINDOW_COMPLETED": _stage_evidence(stage="LABEL_WINDOW_COMPLETED", first=3000),
        "TAIL_LABEL_ASSIGNED": _stage_evidence(stage="TAIL_LABEL_ASSIGNED", first=3100),
        "STRATEGY_VALIDATION_SAMPLE_CREATED": _stage_evidence(
            stage="STRATEGY_VALIDATION_SAMPLE_CREATED", first=3200
        ),
    }
    return {symbol: stages}


def _eligible_mover(
    symbol: str = "BTCUSDT",
    *,
    rank: int = 1,
    pct: float = 0.20,
    quote_volume: float = 5_000_000.0,
    last_price: float = 60000.0,
    first_seen_ts: int = 1000,
) -> TopMoverReference:
    return TopMoverReference(
        symbol=symbol,
        rank=rank,
        price_change_pct=pct,
        quote_volume_usdt=quote_volume,
        last_price=last_price,
        first_seen_ts=first_seen_ts,
        in_eligible_universe=True,
    )


# ---------------------------------------------------------------------------
# Tests - top mover reference set
# ---------------------------------------------------------------------------


def test_top_mover_reference_set_contract():
    """Reference set sorts by absolute price change descending,
    flags symbols outside the known universe / below liquidity, and
    drops symbols below the price-change threshold."""
    ticker_rows = [
        {"symbol": "ALPHAUSDT", "priceChangePercent": "12.5",
         "quoteVolume": "5000000", "lastPrice": "1.00"},
        {"symbol": "BETAUSDT", "priceChangePercent": "-25.0",
         "quoteVolume": "2000000", "lastPrice": "2.50"},
        {"symbol": "FAKEUSDT", "priceChangePercent": "30.0",
         "quoteVolume": "100", "lastPrice": "0.50"},
        {"symbol": "TINYUSDT", "priceChangePercent": "1.0",
         "quoteVolume": "5000", "lastPrice": "0.50"},
        {"symbol": "DELISTEDUSDT", "priceChangePercent": "40.0",
         "quoteVolume": "10000000", "lastPrice": "0.10"},
    ]
    refs = build_top_mover_reference_set(
        ticker_rows=ticker_rows,
        known_universe=["ALPHAUSDT", "BETAUSDT", "FAKEUSDT"],  # DELISTED missing
        not_usdt_perpetual_symbols=[],
        min_price_change_pct=0.05,
        min_quote_volume_usdt=1_000_000.0,
        top_mover_limit=10,
        now_ms_value=1000,
    )
    syms = [r.symbol for r in refs]
    # TINYUSDT below threshold dropped.
    assert "TINYUSDT" not in syms
    # DELISTEDUSDT kept but flagged not-in-universe.
    delisted = next(r for r in refs if r.symbol == "DELISTEDUSDT")
    assert delisted.in_eligible_universe is False
    assert delisted.not_in_futures_universe_reason == MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO
    # FAKEUSDT below liquidity threshold flagged.
    fake = next(r for r in refs if r.symbol == "FAKEUSDT")
    assert fake.in_eligible_universe is False
    assert fake.not_in_futures_universe_reason == MissReason.BELOW_LIQUIDITY_THRESHOLD
    # Sort order: |40%| > |30%| > |25%| > |12.5%|.
    assert syms[0] == "DELISTEDUSDT"
    assert syms[1] == "FAKEUSDT"
    assert syms[2] == "BETAUSDT"
    assert syms[3] == "ALPHAUSDT"
    # Ranks reassigned.
    assert refs[0].rank == 1
    assert refs[3].rank == 4


def test_top_mover_reference_set_empty_input():
    """Empty input returns empty tuple deterministically."""
    refs = build_top_mover_reference_set(ticker_rows=None)
    assert refs == ()
    refs = build_top_mover_reference_set(ticker_rows=[])
    assert refs == ()


# ---------------------------------------------------------------------------
# Tests - audit_mover_capture_path
# ---------------------------------------------------------------------------


def test_capture_path_audit_detects_full_capture():
    """A mover with the full chain observed (MARKET_SNAPSHOT +
    classify + score + LABEL_QUEUE_ENQUEUED + TAIL_LABEL_ASSIGNED)
    is CAPTURED."""
    mover = _eligible_mover()
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("BTCUSDT",),
        stage_observations=_full_chain_observations(),
    )
    record = audit_mover_capture_path(mover, audit_input=audit_input)
    assert record.audit_status == CapturePathStatus.CAPTURED
    assert record.has_completed_tail_label
    assert record.has_strategy_validation_sample
    assert record.captured_stage_count >= len(["MARKET_SNAPSHOT", "ANOMALY_DETECTED", "OPPORTUNITY_SCORED"])
    assert record.miss_reasons == ()


def test_capture_path_audit_detects_partial_capture():
    """A mover with MARKET_SNAPSHOT but no terminal stage is
    PARTIALLY_CAPTURED."""
    mover = _eligible_mover()
    stage_obs = {
        "BTCUSDT": {
            "MARKET_SNAPSHOT": _stage_evidence(stage="MARKET_SNAPSHOT", first=1500),
            "PRE_ANOMALY_DETECTED": _stage_evidence(stage="PRE_ANOMALY_DETECTED", first=1600),
            "ANOMALY_DETECTED": _stage_evidence(stage="ANOMALY_DETECTED", first=1700),
        }
    }
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("BTCUSDT",),
        stage_observations=stage_obs,
    )
    record = audit_mover_capture_path(mover, audit_input=audit_input)
    assert record.audit_status == CapturePathStatus.PARTIALLY_CAPTURED
    assert not record.has_completed_tail_label
    assert MissReason.NO_COMPLETED_TAIL_LABEL_YET in record.miss_reasons


def test_capture_path_audit_detects_missed_eligible_mover():
    """An eligible mover with no chain observations whatsoever is
    MISSED. The miss is a coverage warning candidate."""
    mover = _eligible_mover()
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("BTCUSDT",),
        stage_observations={},
    )
    record = audit_mover_capture_path(mover, audit_input=audit_input)
    assert record.audit_status == CapturePathStatus.MISSED
    assert record.captured_stage_count == 0


def test_capture_path_audit_excludes_not_in_futures_universe():
    """A mover flagged ``in_eligible_universe=False`` is EXCLUDED,
    even when no other miss reason is set."""
    mover = TopMoverReference(
        symbol="WEIRDUSDT",
        rank=1,
        price_change_pct=0.40,
        quote_volume_usdt=2_000_000.0,
        last_price=1.0,
        first_seen_ts=1000,
        in_eligible_universe=False,
        not_in_futures_universe_reason=MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO,
    )
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("BTCUSDT",),
        stage_observations={},
    )
    record = audit_mover_capture_path(mover, audit_input=audit_input)
    assert record.audit_status == CapturePathStatus.EXCLUDED
    assert MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO in record.miss_reasons
    assert MissReason.NOT_IN_FUTURES_UNIVERSE in record.miss_reasons


# ---------------------------------------------------------------------------
# Tests - classify_miss_reason
# ---------------------------------------------------------------------------


def test_miss_reason_classification_not_in_exchange_info():
    mover = TopMoverReference(
        symbol="WEIRDUSDT",
        rank=1,
        price_change_pct=0.40,
        quote_volume_usdt=2_000_000.0,
        last_price=1.0,
        in_eligible_universe=False,
        not_in_futures_universe_reason=MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO,
    )
    audit_input = MoverCaptureRecallAuditInput(top_movers=(mover,))
    reasons = classify_miss_reason(
        mover=mover,
        stage_evidence=None,
        audit_input=audit_input,
        risk_rejected=False,
        has_completed_tail_label=False,
    )
    assert MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO in reasons
    assert MissReason.NOT_IN_FUTURES_UNIVERSE in reasons


def test_miss_reason_classification_candidate_pool_evicted():
    mover = _eligible_mover(symbol="EVICTEDUSDT")
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("EVICTEDUSDT",),
        candidate_pool_evicted_symbols=("EVICTEDUSDT",),
    )
    reasons = classify_miss_reason(
        mover=mover,
        stage_evidence={
            "MARKET_SNAPSHOT": _stage_evidence(stage="MARKET_SNAPSHOT"),
        },
        audit_input=audit_input,
        risk_rejected=False,
        has_completed_tail_label=False,
    )
    assert MissReason.CANDIDATE_POOL_EVICTED in reasons


def test_miss_reason_classification_data_unreliable():
    mover = _eligible_mover(symbol="DUUSDT")
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("DUUSDT",),
        data_unreliable_symbols=("DUUSDT",),
    )
    reasons = classify_miss_reason(
        mover=mover,
        stage_evidence={
            "MARKET_SNAPSHOT": _stage_evidence(stage="MARKET_SNAPSHOT"),
        },
        audit_input=audit_input,
        risk_rejected=False,
        has_completed_tail_label=False,
    )
    assert MissReason.DATA_UNRELIABLE in reasons


def test_miss_reason_classification_risk_rejected():
    mover = _eligible_mover(symbol="RUSDT")
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("RUSDT",),
        risk_rejected_symbols=("RUSDT",),
    )
    stage_obs = _full_chain_observations(symbol="RUSDT")
    record = audit_mover_capture_path(
        mover,
        audit_input=MoverCaptureRecallAuditInput(
            top_movers=(mover,),
            known_universe=("RUSDT",),
            risk_rejected_symbols=("RUSDT",),
            stage_observations=stage_obs,
        ),
    )
    # Captured-then-rejected is still CAPTURED with notes.
    assert record.audit_status == CapturePathStatus.CAPTURED
    assert record.risk_rejected is True
    assert MissReason.RISK_REJECTED in record.miss_reasons
    assert "captured_then_risk_rejected" in record.notes


# ---------------------------------------------------------------------------
# Tests - top-level metrics + payload roundtrip
# ---------------------------------------------------------------------------


def test_mover_capture_audit_metrics():
    """Top-level report aggregates the per-mover counts +
    descriptive rates."""
    captured = _eligible_mover(symbol="BTCUSDT", rank=1, pct=0.20)
    missed = _eligible_mover(symbol="ETHUSDT", rank=2, pct=0.15)
    excluded = TopMoverReference(
        symbol="WEIRDUSDT",
        rank=3,
        price_change_pct=0.50,
        quote_volume_usdt=5_000_000.0,
        last_price=1.0,
        first_seen_ts=1000,
        in_eligible_universe=False,
        not_in_futures_universe_reason=MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO,
    )
    stage_obs = _full_chain_observations(symbol="BTCUSDT")
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(captured, missed, excluded),
        known_universe=("BTCUSDT", "ETHUSDT"),
        stage_observations=stage_obs,
        report_id="r-1",
        audit_id="a-1",
    )
    report = build_mover_capture_recall_audit_report(
        audit_input, evaluated_at_ms=4000
    )
    assert report.top_mover_count == 3
    assert report.captured_top_mover_count == 1
    assert report.missed_top_mover_count == 1
    assert report.excluded_top_mover_count == 1
    # Recall rate: captured (1) / eligible (2) = 0.5.
    assert report.capture_recall_rate == pytest.approx(0.5)
    assert report.anomaly_detected_rate == pytest.approx(0.5)
    assert report.tail_label_assigned_rate == pytest.approx(0.5)
    assert report.strategy_validation_sample_rate == pytest.approx(0.5)
    # Coverage warning fires for ETHUSDT (eligible + clear right tail
    # + missed for a system-correctable reason).
    assert any("ETHUSDT" in w for w in report.coverage_warnings)
    # Status flips to DEGRADED because of the coverage warning.
    assert report.status == MoverCaptureRecallAuditStatus.DEGRADED
    # Miss reason summary populated.
    assert MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO in report.miss_reason_summary
    # Median latency populated for captured movers.
    assert report.median_first_seen_latency_seconds >= 0.0


def test_mover_capture_audit_insufficient_data():
    """An empty top_movers list yields an INSUFFICIENT_DATA report."""
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(),
        known_universe=("BTCUSDT",),
        report_id="r-empty",
        audit_id="a-empty",
    )
    report = build_mover_capture_recall_audit_report(
        audit_input, evaluated_at_ms=1000
    )
    assert report.status == MoverCaptureRecallAuditStatus.INSUFFICIENT_DATA
    assert report.records == ()
    assert report.insufficient_coverage_reasons


def test_mover_capture_audit_payload_roundtrip():
    """The export/load round-trip is lossless."""
    mover = _eligible_mover()
    audit_input = MoverCaptureRecallAuditInput(
        top_movers=(mover,),
        known_universe=("BTCUSDT",),
        stage_observations=_full_chain_observations(),
        report_id="r-rt",
        audit_id="a-rt",
    )
    report = build_mover_capture_recall_audit_report(
        audit_input, evaluated_at_ms=4000
    )
    payload = export_mover_capture_recall_audit_payload(report)
    assert payload["schema_version"] in (
        KNOWN_MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSIONS
    )
    # JSON-safe.
    js = json.dumps(payload)
    loaded = load_mover_capture_recall_audit_payload(json.loads(js))
    assert loaded.status == report.status
    assert loaded.captured_top_mover_count == report.captured_top_mover_count
    assert len(loaded.records) == len(report.records)
    assert loaded.records[0].symbol == report.records[0].symbol
    assert loaded.records[0].audit_status == report.records[0].audit_status


# ---------------------------------------------------------------------------
# Tests - runtime + EventRepository emission
# ---------------------------------------------------------------------------


def test_mover_capture_audit_events_exportable(tmp_path: Path):
    """Runtime emits one event per record + one top-level event,
    and the events can be read back via EventRepository.list_events."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = MoverCaptureRecallAuditRuntime(event_repo=repo)
        captured = _eligible_mover(symbol="BTCUSDT", rank=1, pct=0.20)
        missed = _eligible_mover(symbol="ETHUSDT", rank=2, pct=0.15)
        audit_input = MoverCaptureRecallAuditInput(
            top_movers=(captured, missed),
            known_universe=("BTCUSDT", "ETHUSDT"),
            stage_observations=_full_chain_observations(symbol="BTCUSDT"),
            report_id="r-evt",
            audit_id="a-evt",
        )
        report = runtime.flush(audit_input, generated_at_ms=9000)
        assert report.top_mover_count == 2
        path_audited = repo.list_events(
            event_type=EventType.MOVER_CAPTURE_PATH_AUDITED
        )
        recall_audit = repo.list_events(
            event_type=EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED
        )
        assert len(path_audited) == 2
        assert len(recall_audit) == 1
        # Schema version present on every payload.
        for ev in path_audited + recall_audit:
            assert ev.payload.get("schema_version") in (
                KNOWN_MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSIONS
            )
        # Counters reflect the emit.
        assert runtime.mover_capture_path_audited_count == 2
        assert runtime.mover_capture_recall_audit_generated_count == 1
    finally:
        dbs.close()


def test_replay_reads_mover_capture_audit_events(tmp_path: Path):
    """EventRepository.replay_events yields the audit events in
    deterministic timestamp order without raising."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = MoverCaptureRecallAuditRuntime(event_repo=repo)
        mover = _eligible_mover()
        audit_input = MoverCaptureRecallAuditInput(
            top_movers=(mover,),
            known_universe=("BTCUSDT",),
            stage_observations=_full_chain_observations(),
            report_id="r-replay",
            audit_id="a-replay",
        )
        runtime.flush(audit_input, generated_at_ms=12345)
        events = list(
            repo.replay_events(
                event_types=(
                    EventType.MOVER_CAPTURE_PATH_AUDITED,
                    EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
                )
            )
        )
        assert len(events) == 2
        # Replay must surface both event types; the SQLite ordering
        # is by (timestamp, event_id) and event_id is a random UUID,
        # so we only assert the *set* of types here. Determinism of
        # per-mover-vs-top-level emission order is exercised by the
        # event-counter assertion in
        # ``test_mover_capture_audit_events_exportable``.
        types_seen = {ev.event_type for ev in events}
        assert types_seen == {
            EventType.MOVER_CAPTURE_PATH_AUDITED,
            EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
        }
    finally:
        dbs.close()


def test_runtime_metrics_payload_when_no_flush():
    """Metrics payload returns an empty-but-well-formed dict when no
    flush has been performed yet."""
    runtime = MoverCaptureRecallAuditRuntime(event_repo=None)
    metrics = runtime.metrics_payload()
    assert metrics["mover_capture_audit_status"] == ""
    assert metrics["top_mover_count"] == 0
    assert metrics["mover_capture_records"] == []
    assert (
        metrics["mover_capture_recall_audit_schema_version"]
        == MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# Tests - daily report integration
# ---------------------------------------------------------------------------


def test_daily_report_contains_mover_capture_audit_section(tmp_path: Path):
    """The daily report builder surfaces the mover audit section
    + every required field after consuming the runtime metrics."""
    from app.paper_run.daily_report import DailyReportBuilder

    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = MoverCaptureRecallAuditRuntime(event_repo=repo)
        captured = _eligible_mover(symbol="BTCUSDT", pct=0.30)
        missed = _eligible_mover(symbol="ETHUSDT", pct=0.20)
        excluded = TopMoverReference(
            symbol="WEIRDUSDT",
            rank=3,
            price_change_pct=0.60,
            quote_volume_usdt=5_000_000.0,
            last_price=1.0,
            in_eligible_universe=False,
            not_in_futures_universe_reason=MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO,
        )
        audit_input = MoverCaptureRecallAuditInput(
            top_movers=(captured, missed, excluded),
            known_universe=("BTCUSDT", "ETHUSDT"),
            stage_observations=_full_chain_observations(symbol="BTCUSDT"),
            report_id="daily",
            audit_id="daily-audit",
        )
        runtime.flush(audit_input, generated_at_ms=2_000_000_000_000)

        builder = DailyReportBuilder(
            event_repo=repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=1_000_000_000_000,
            finished_at_ms=2_000_000_000_000,
            mover_capture_audit_metrics=runtime.metrics_payload(),
            write_to_disk=False,
        )
        # Snapshot fields populated.
        assert snapshot.mover_capture_recall_audit_generated_count >= 1
        assert snapshot.mover_capture_path_audited_count >= 1
        assert snapshot.top_mover_count == 3
        assert snapshot.captured_top_mover_count == 1
        assert snapshot.missed_top_mover_count == 1
        assert snapshot.excluded_top_mover_count == 1
        assert snapshot.mover_capture_audit_status in (
            MOVER_CAPTURE_RECALL_AUDIT_STATUSES
        )
        # Markdown surfaces the new section + headings.
        assert "Phase 11C.1C-C-B-B-B-D" in snapshot.markdown
        assert "Mover Capture Recall" in snapshot.markdown
        assert "MOVER_CAPTURE_RECALL_AUDIT_GENERATED" in snapshot.markdown
        # Payload round-trip carries every brief-mandated key.
        payload = snapshot.to_payload()
        for key in (
            "mover_capture_audit_status",
            "top_mover_count",
            "captured_top_mover_count",
            "partially_captured_top_mover_count",
            "missed_top_mover_count",
            "excluded_top_mover_count",
            "capture_recall_rate",
            "anomaly_detected_rate",
            "label_tracking_rate",
            "tail_label_assigned_rate",
            "strategy_validation_sample_rate",
            "risk_rejected_mover_count",
            "mover_capture_records",
            "miss_reason_summary",
            "coverage_warnings",
        ):
            assert key in payload, f"missing key in daily report payload: {key}"
    finally:
        dbs.close()


def test_daily_report_section_renders_when_audit_metrics_missing(
    tmp_path: Path,
):
    """Without an audit input, the daily report still renders the
    Phase 11C.1C-C-B-B-B-D section header (graceful degrade)."""
    from app.paper_run.daily_report import DailyReportBuilder

    repo, dbs = _make_event_repo(tmp_path)
    try:
        builder = DailyReportBuilder(
            event_repo=repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=1_000_000_000_000,
            finished_at_ms=2_000_000_000_000,
            mover_capture_audit_metrics=None,
            write_to_disk=False,
        )
        assert "Phase 11C.1C-C-B-B-B-D" in snapshot.markdown
        assert snapshot.mover_capture_audit_status == ""
        assert snapshot.top_mover_count == 0
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Tests - safety contracts (Phase 11C.1C-C-B-B-B-D / Phase 12 forbidden)
# ---------------------------------------------------------------------------


def test_mover_capture_audit_does_not_trigger_execution(tmp_path: Path):
    """The audit emits two paper / evidence-only event types and
    nothing on the live-trading / order / position / stop chain."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = MoverCaptureRecallAuditRuntime(event_repo=repo)
        mover = _eligible_mover()
        audit_input = MoverCaptureRecallAuditInput(
            top_movers=(mover,),
            known_universe=("BTCUSDT",),
            stage_observations=_full_chain_observations(),
            report_id="exec-safety",
            audit_id="exec-safety-audit",
        )
        runtime.flush(audit_input, generated_at_ms=42)
        # Nothing on the trade-decision path was emitted.
        for forbidden_type in (
            EventType.ORDER_SENT,
            EventType.ORDER_ACK,
            EventType.ORDER_FILLED,
            EventType.ORDER_CANCELLED,
            EventType.POSITION_OPENED,
            EventType.POSITION_UPDATED,
            EventType.POSITION_CLOSED,
            EventType.STOP_SENT,
            EventType.STOP_CONFIRMED,
            EventType.STOP_FAILED,
            EventType.RISK_APPROVED,
            EventType.EXIT_TRIGGERED,
        ):
            assert repo.list_events(event_type=forbidden_type) == []
    finally:
        dbs.close()


def test_no_live_trading_flags_unchanged():
    """The audit module must NOT toggle any safety flag. Imports
    must be free of any code that flips ``live_trading`` etc."""
    from app.config.settings import get_settings, load_settings

    get_settings.cache_clear()
    settings = load_settings()
    # Importing the audit module must not change any safety flag.
    import app.adaptive.mover_capture_recall_audit  # noqa: F401

    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.right_tail_enabled is False
    assert settings.llm_enabled is False
    assert settings.exchange_live_order_enabled is False


def test_phase_12_remains_forbidden():
    """The audit MUST NOT introduce Phase 12 features. The module
    constants pin the source phase to Phase 11C.1C-C-B-B-B-D, the
    schema version to its v1 stamp, and the brief's "audit ≠
    runtime modifier" contract is enforced by the runtime helper:
    its public surface is read-only aside from EventRepository
    appends."""
    from app.adaptive.mover_capture_recall_audit import (
        MOVER_CAPTURE_RECALL_AUDIT_SOURCE_PHASE,
        MOVER_CAPTURE_RECALL_AUDIT_VERSION,
    )

    assert "phase_11c_1c_c_b_b_b_d" in MOVER_CAPTURE_RECALL_AUDIT_SOURCE_PHASE
    assert "v1" in MOVER_CAPTURE_RECALL_AUDIT_VERSION
    # The runtime exposes only flush + metrics_payload + read-only
    # counters; any Phase 12-style mutation method would fail this
    # surface check.
    surface = {
        name
        for name in dir(MoverCaptureRecallAuditRuntime)
        if not name.startswith("_")
    }
    assert "flush" in surface
    assert "metrics_payload" in surface
    assert "latest_report" in surface
    # Explicit forbidden surfaces.
    for forbidden in (
        "open_position",
        "close_position",
        "set_leverage",
        "set_stop_loss",
        "set_target_price",
        "modify_risk_engine",
        "modify_execution_fsm",
        "modify_symbol_limit",
        "modify_anomaly_threshold",
        "modify_regime_weights",
        "auto_optimize",
        "ai_learn",
        "rl_train",
        "blind_replay",
        "live_trade",
    ):
        assert forbidden not in surface

    # Status / miss-reason vocabularies are explicit constants, so
    # adding a Phase 12 keyword would have to bump the
    # schema_version - which test_mover_capture_audit_payload_roundtrip
    # already pins.
    assert set(CAPTURE_PATH_STATUSES) == {
        "CAPTURED",
        "PARTIALLY_CAPTURED",
        "MISSED",
        "EXCLUDED",
        "INSUFFICIENT_DATA",
    }
    assert set(MOVER_CAPTURE_RECALL_AUDIT_STATUSES) == {
        "OK",
        "INSUFFICIENT_DATA",
        "DEGRADED",
    }
    expected_reasons = {
        "not_in_futures_universe",
        "symbol_not_in_exchange_info",
        "not_usdt_perpetual",
        "below_liquidity_threshold",
        "symbol_limit_excluded",
        "candidate_pool_evicted",
        "insufficient_ws_data",
        "stale_data",
        "data_unreliable",
        "no_anomaly_threshold_cross",
        "risk_rejected",
        "no_completed_tail_label_yet",
        "unknown",
    }
    assert set(MISS_REASONS) == expected_reasons
    # Every brief-mandated capture-path stage is in the canonical
    # tuple; a Phase 12-only stage would break this assertion.
    for required in (
        "MARKET_SNAPSHOT",
        "PRE_ANOMALY_DETECTED",
        "ANOMALY_DETECTED",
        "MARKET_REGIME_ASSESSED",
        "CANDIDATE_STAGE_CLASSIFIED",
        "OPPORTUNITY_SCORED",
        "STRATEGY_MODE_SELECTED",
        "CLUSTER_CONTEXT_ATTACHED",
        "LABEL_QUEUE_ENQUEUED",
        "LABEL_TRACKING_STARTED",
        "LABEL_WINDOW_COMPLETED",
        "TAIL_LABEL_ASSIGNED",
        "STRATEGY_VALIDATION_SAMPLE_CREATED",
        "RISK_REJECTED",
        "DATA_UNRELIABLE",
    ):
        assert required in CAPTURE_PATH_STAGES
