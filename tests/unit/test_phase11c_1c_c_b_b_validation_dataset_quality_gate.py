"""Phase 11C.1C-C-B-B-A - Strategy Validation Dataset Builder &
Quality Gate v0 tests.

Pins every behaviour the brief calls out:

  - StrategyValidationDatasetRecord carries every brief-mandated
    field (report_id, opportunity_id, scan_batch_id, symbol,
    candidate_stage, strategy_mode, opportunity_score,
    early_tail_score, late_chase_risk, cluster_id, cluster_leader,
    tail_label, mfe_*/mae_* per window, reached_2r/3r/5r/10r,
    fake_breakout, missed_tail, late_chase_failure, source_event_id,
    schema_version).
  - build_validation_dataset_from_samples / summarize / evaluate /
    export / load round-trip.
  - The quality gate's three statuses (pass / warn / fail) are
    correctly assigned across sample-count + coverage scenarios.
  - The runtime emits the three new event types
    (STRATEGY_VALIDATION_DATASET_BUILT,
    STRATEGY_VALIDATION_DATASET_EXPORTED,
    STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED) with the
    brief-mandated identity block.
  - Phase 8.5 export bundle carries the new event types.
  - ReplayEngine accepts the new event types without raising.
  - Daily report contains the new validation-dataset section.
  - Safety regression: every Phase 1 safety flag remains False;
    the runtime never emits any ORDER_* / POSITION_* / STOP_* /
    TELEGRAM_MESSAGE_SENT event; Phase 12 remains FORBIDDEN.

No real socket is opened. The runtime is paper / report only.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.adaptive.label_runtime import (
    LabelTrackingRecord,
    TrackingWindowState,
)
from app.adaptive.strategy_validation import (
    STRATEGY_VALIDATION_SCHEMA_VERSION,
    StrategyValidationSample,
)
from app.adaptive.strategy_validation_dataset import (
    CANONICAL_CANDIDATE_STAGES,
    CANONICAL_STRATEGY_MODES,
    QUALITY_GATE_STATUSES,
    REQUIRED_DATASET_RECORD_FIELDS,
    STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
    STRATEGY_VALIDATION_DATASET_VERSION,
    StrategyValidationDataset,
    StrategyValidationDatasetRecord,
    StrategyValidationDatasetSummary,
    StrategyValidationQualityGate,
    StrategyValidationQualityGateResult,
    build_validation_dataset_from_samples,
    evaluate_validation_dataset_quality,
    export_validation_dataset_payload,
    load_validation_dataset_payload,
    summarize_validation_dataset,
)
from app.adaptive.strategy_validation_runtime import (
    StrategyValidationRuntime,
    StrategyValidationRuntimeConfig,
)
from app.config.settings import get_settings, load_settings
from app.core.events import Event, EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exports.service import TestDataExportService
from app.paper_run.daily_report import DailyReportBuilder
from app.replay.engine import ReplayEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _settings():
    get_settings.cache_clear()
    return load_settings()


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital), dbs


def _sample(
    *,
    opportunity_id: str = "opp",
    scan_batch_id: str = "batch",
    symbol: str = "EDENUSDT",
    candidate_stage: str = "early",
    strategy_mode: str = "follow",
    opportunity_score: float = 75.0,
    early_tail_score: float = 80.0,
    late_chase_risk: float = 10.0,
    cluster_id: str = "USDT",
    cluster_leader: str | None = "EDENUSDT",
    is_cluster_leader: bool = True,
    tail_label: str = "strong_tail",
    mfe_5m: float = 0.10,
    mae_5m: float = -0.01,
    reached_2r: bool = True,
    reached_3r: bool = True,
    reached_5r: bool = True,
    reached_10r: bool = False,
    fake_breakout: bool = False,
    missed_tail: bool = False,
    late_chase_failure: bool = False,
) -> StrategyValidationSample:
    return StrategyValidationSample(
        opportunity_id=opportunity_id,
        scan_batch_id=scan_batch_id,
        symbol=symbol,
        candidate_stage=candidate_stage,
        strategy_mode=strategy_mode,
        opportunity_score=opportunity_score,
        opportunity_grade="A",
        early_tail_score=early_tail_score,
        late_chase_risk=late_chase_risk,
        cluster_id=cluster_id,
        cluster_leader=cluster_leader,
        is_cluster_leader=is_cluster_leader,
        tail_label=tail_label,
        mfe_5m=mfe_5m,
        mae_5m=mae_5m,
        mfe_15m=mfe_5m * 1.1,
        mae_15m=mae_5m,
        mfe_30m=mfe_5m * 1.2,
        mae_30m=mae_5m,
        mfe_1h=mfe_5m * 1.3,
        mae_1h=mae_5m,
        mfe_4h=mfe_5m * 1.4,
        mae_4h=mae_5m,
        reached_2r=reached_2r,
        reached_3r=reached_3r,
        reached_5r=reached_5r,
        reached_10r=reached_10r,
        fake_breakout=fake_breakout,
        missed_tail=missed_tail,
        late_chase_failure=late_chase_failure,
    )


def _diverse_samples(n: int = 25) -> list[StrategyValidationSample]:
    """Build a sample set that satisfies every coverage threshold."""
    samples: list[StrategyValidationSample] = []
    modes = ("follow", "pullback", "observe", "reject")
    stages = ("early", "mid", "late", "blowoff", "dumped")
    scores = (45.0, 60.0, 70.0, 90.0)
    tail_labels = (
        "strong_tail",
        "moderate_tail",
        "weak_tail",
        "fake_breakout",
        "dumped",
    )
    for i in range(n):
        m = modes[i % len(modes)]
        st = stages[i % len(stages)]
        sc = scores[i % len(scores)]
        tl = tail_labels[i % len(tail_labels)]
        samples.append(
            _sample(
                opportunity_id=f"opp-{i}",
                scan_batch_id=f"batch-{i // 5}",
                symbol=f"SYM{i}USDT",
                candidate_stage=st,
                strategy_mode=m,
                opportunity_score=sc,
                early_tail_score=float(20 * (i % 5) + 10),
                tail_label=tl,
                cluster_id=f"cluster-{i % 3}",
                cluster_leader=f"SYM{i}USDT" if i % 3 == 0 else None,
                is_cluster_leader=(i % 3 == 0),
                fake_breakout=(tl == "fake_breakout"),
                missed_tail=(tl == "weak_tail"),
            )
        )
    return samples


# ---------------------------------------------------------------------------
# 1. Contract: dataset record fields
# ---------------------------------------------------------------------------
def test_strategy_validation_dataset_record_contract():
    """Every brief-mandated field is present + JSON-serialisable."""
    record = StrategyValidationDatasetRecord(
        report_id="rep-1",
        opportunity_id="opp-1",
        scan_batch_id="batch-1",
        symbol="EDENUSDT",
        candidate_stage="early",
        strategy_mode="follow",
        opportunity_score=80.0,
        early_tail_score=85.0,
        late_chase_risk=10.0,
        cluster_id="USDT",
        cluster_leader="EDENUSDT",
        tail_label="strong_tail",
        mfe_5m=0.05,
        mae_5m=-0.01,
        mfe_15m=0.06,
        mae_15m=-0.012,
        mfe_30m=0.07,
        mae_30m=-0.013,
        mfe_1h=0.08,
        mae_1h=-0.014,
        mfe_4h=0.09,
        mae_4h=-0.015,
        reached_2r=True,
        reached_3r=True,
        reached_5r=False,
        reached_10r=False,
        fake_breakout=False,
        missed_tail=False,
        late_chase_failure=False,
        source_event_id="src-evt-id",
    )
    payload = record.to_payload()
    # Brief-mandated fields all present.
    for field in (
        "report_id",
        "opportunity_id",
        "scan_batch_id",
        "symbol",
        "candidate_stage",
        "strategy_mode",
        "opportunity_score",
        "early_tail_score",
        "late_chase_risk",
        "cluster_id",
        "cluster_leader",
        "tail_label",
        "mfe_5m",
        "mae_5m",
        "mfe_15m",
        "mae_15m",
        "mfe_30m",
        "mae_30m",
        "mfe_1h",
        "mae_1h",
        "mfe_4h",
        "mae_4h",
        "reached_2r",
        "reached_3r",
        "reached_5r",
        "reached_10r",
        "fake_breakout",
        "missed_tail",
        "late_chase_failure",
        "source_event_id",
        "schema_version",
    ):
        assert field in payload, f"missing field {field}"
    assert payload["schema_version"] == STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
    # Round-trips through json safely.
    json.dumps(payload, sort_keys=True)


def test_dataset_record_required_fields_constant_matches_payload():
    """REQUIRED_DATASET_RECORD_FIELDS must be a subset of the
    payload keys so the gate's missing-fields check can pin every
    brief-mandated field."""
    record = StrategyValidationDatasetRecord(
        report_id="r",
        opportunity_id="o",
        scan_batch_id="b",
        symbol="s",
        candidate_stage="early",
        strategy_mode="follow",
    )
    payload_keys = set(record.to_payload().keys())
    for field in REQUIRED_DATASET_RECORD_FIELDS:
        if field == "cluster_leader":
            # cluster_leader is allowed to be None; the gate does
            # not require it on the row.
            continue
        assert field in payload_keys


# ---------------------------------------------------------------------------
# 2. Builder + summary
# ---------------------------------------------------------------------------
def test_build_validation_dataset_from_samples():
    """The builder maps every sample into a record, propagates the
    report_id, and computes a summary."""
    samples = _diverse_samples(5)
    ds = build_validation_dataset_from_samples(
        samples,
        report_id="rep-X",
        generated_at_ms=1_700_000_000_000,
        source_event_ids={"opp-0": "evt-0", "opp-1": "evt-1"},
    )
    assert isinstance(ds, StrategyValidationDataset)
    assert ds.report_id == "rep-X"
    assert ds.generated_at_ms == 1_700_000_000_000
    assert len(ds.records) == 5
    # source_event_id propagates from the lookup map.
    by_opp = {r.opportunity_id: r for r in ds.records}
    assert by_opp["opp-0"].source_event_id == "evt-0"
    assert by_opp["opp-1"].source_event_id == "evt-1"
    # Missing entries default to "".
    assert by_opp["opp-2"].source_event_id == ""
    # report_id propagates onto every record.
    assert all(r.report_id == "rep-X" for r in ds.records)
    # JSON-safe payload.
    json.dumps(ds.to_payload(), sort_keys=True)


def test_summarize_validation_dataset():
    samples = _diverse_samples(20)
    ds = build_validation_dataset_from_samples(
        samples, report_id="rep-Y", generated_at_ms=1_700_000_060_000
    )
    summary = summarize_validation_dataset(ds.records)
    assert isinstance(summary, StrategyValidationDatasetSummary)
    assert summary.record_count == 20
    # 5 cycles of 4 modes -> all four modes appear.
    for mode in CANONICAL_STRATEGY_MODES:
        assert summary.strategy_mode_counts.get(mode, 0) >= 1
    # 4 cycles of 5 stages -> all five stages appear.
    for stage in CANONICAL_CANDIDATE_STAGES:
        assert summary.candidate_stage_counts.get(stage, 0) >= 1
    # Tail label counts populated.
    assert summary.tail_label_counts.get("strong_tail", 0) >= 1
    assert summary.tail_label_counts.get("fake_breakout", 0) >= 1
    # fake_breakout / missed_tail flags counted.
    assert summary.fake_breakout_count >= 1
    assert summary.missed_tail_count >= 1
    json.dumps(summary.to_payload(), sort_keys=True)


def test_summarize_empty_dataset_returns_empty_summary():
    ds = build_validation_dataset_from_samples(
        [], report_id="rep-empty", generated_at_ms=1_700_000_000_000
    )
    summary = summarize_validation_dataset(ds.records)
    assert summary.record_count == 0
    assert summary.completed_tail_label_count == 0
    assert summary.symbols == ()
    assert summary.tail_label_counts == {}


# ---------------------------------------------------------------------------
# 3. Quality gate v0 (pass / warn / fail)
# ---------------------------------------------------------------------------
def test_quality_gate_passes_with_sufficient_samples():
    """A sufficiently diverse, well-formed dataset must yield
    ``pass`` with a single ``all_quality_gate_thresholds_met``
    reason."""
    ds = build_validation_dataset_from_samples(
        _diverse_samples(40),
        report_id="rep-pass",
        generated_at_ms=1_700_000_000_000,
    )
    result = evaluate_validation_dataset_quality(ds)
    assert isinstance(result, StrategyValidationQualityGateResult)
    assert result.gate_status == "pass", (
        f"expected pass; reasons={list(result.reasons)}"
    )
    assert result.export_roundtrip_ok is True
    assert result.replay_readable is True
    assert result.missing_required_fields == ()
    assert "all_quality_gate_thresholds_met" in result.reasons


def test_quality_gate_warns_on_low_samples():
    """A small but well-formed dataset (>=half min) must yield
    ``warn``, not ``fail``."""
    # Only 12 samples but with half-min = 10 (default min_total = 20).
    ds = build_validation_dataset_from_samples(
        _diverse_samples(12),
        report_id="rep-warn",
        generated_at_ms=1_700_000_000_000,
    )
    result = evaluate_validation_dataset_quality(ds)
    assert result.gate_status == "warn", (
        f"expected warn; reasons={list(result.reasons)}"
    )
    # The reason includes sample_count_below_min.
    assert any(
        r.startswith("sample_count_below_min=") for r in result.reasons
    )


def test_quality_gate_warns_on_missing_coverage():
    """Even with enough samples, missing canonical mode/stage/bucket
    coverage produces ``warn``."""
    # 40 single-mode, single-stage, single-score samples - lots of
    # rows but no diversity.
    samples = [
        _sample(
            opportunity_id=f"opp-{i}",
            scan_batch_id="batch",
            symbol=f"SYM{i}USDT",
            candidate_stage="early",
            strategy_mode="follow",
            opportunity_score=80.0,
            tail_label="strong_tail",
        )
        for i in range(40)
    ]
    ds = build_validation_dataset_from_samples(
        samples, report_id="rep-warn-cov", generated_at_ms=0
    )
    result = evaluate_validation_dataset_quality(ds)
    assert result.gate_status == "warn"
    # Missing canonical modes / stages / buckets surfaced.
    assert "pullback" in result.missing_modes
    assert "mid" in result.missing_stages
    assert "0-49" in result.missing_buckets


def test_quality_gate_fails_missing_required_fields(tmp_path: Path):
    """When a dataset payload is reconstructed from a corrupt
    record (one of the brief-mandated fields stripped out), the
    gate must emit ``fail``."""
    samples = _diverse_samples(30)
    ds = build_validation_dataset_from_samples(
        samples, report_id="rep-fail", generated_at_ms=0
    )
    # Build a corrupt payload: drop ``schema_version`` from every
    # record and rebuild a Dataset whose payload reflects the
    # corruption. We patch via the underlying dict because the
    # pydantic model defaults the field; we simulate corruption by
    # passing a payload-record dict directly to the gate's
    # internal field check.
    payload = ds.to_payload()
    for row in payload["records"]:
        row.pop("schema_version", None)

    # Build a fake dataset whose payload returns the corrupted dict.
    class _FakeDataset:
        def __init__(self, original: StrategyValidationDataset, payload: dict):
            self._original = original
            self._payload = payload
            self.report_id = original.report_id
            self.generated_at_ms = original.generated_at_ms
            self.records = original.records
            self.summary = original.summary
            self.strategy_version = original.strategy_version
            self.scoring_version = original.scoring_version
            self.risk_config_version = original.risk_config_version
            self.state_machine_version = original.state_machine_version
            self.schema_version = original.schema_version

        def to_payload(self):
            return self._payload

    fake = _FakeDataset(ds, payload)
    result = evaluate_validation_dataset_quality(fake)  # type: ignore[arg-type]
    assert result.gate_status == "fail"
    assert "schema_version" in result.missing_required_fields
    assert any(
        r.startswith("missing_required_fields=") for r in result.reasons
    )


def test_quality_gate_fails_on_empty_dataset_with_default_thresholds():
    """An empty dataset must fail the gate (sample_count below half
    min_total_samples)."""
    ds = build_validation_dataset_from_samples(
        [], report_id="rep-empty", generated_at_ms=0
    )
    result = evaluate_validation_dataset_quality(ds)
    assert result.gate_status == "fail"
    assert any(
        r.startswith("sample_count_below_half_min=")
        for r in result.reasons
    )


def test_quality_gate_status_vocabulary_locked():
    """Phase 11C.1C-C-B-B-A locks the gate vocabulary to exactly
    pass / warn / fail. A future PR cannot expand it without
    bumping the schema."""
    assert QUALITY_GATE_STATUSES == ("pass", "warn", "fail")
    with pytest.raises(ValueError):
        StrategyValidationQualityGateResult(gate_status="approved")


def test_quality_gate_with_relaxed_thresholds_passes_small_dataset():
    """When the operator relaxes the gate thresholds, a small
    dataset can pass. Confirms the thresholds are configurable at
    runtime."""
    ds = build_validation_dataset_from_samples(
        _diverse_samples(8),
        report_id="rep-relaxed",
        generated_at_ms=0,
    )
    relaxed = StrategyValidationQualityGate(
        min_total_samples=5,
        min_completed_tail_labels=1,
        min_strategy_mode_coverage=2,
        min_candidate_stage_coverage=2,
        min_score_bucket_coverage=2,
    )
    result = evaluate_validation_dataset_quality(ds, gate=relaxed)
    assert result.gate_status == "pass"


# ---------------------------------------------------------------------------
# 4. Export / replay round-trip
# ---------------------------------------------------------------------------
def test_dataset_export_roundtrip():
    """``export_validation_dataset_payload`` produces a JSON-safe
    dict that ``load_validation_dataset_payload`` reconstructs into
    an equivalent dataset."""
    ds = build_validation_dataset_from_samples(
        _diverse_samples(15), report_id="rep-rt", generated_at_ms=42
    )
    payload = export_validation_dataset_payload(ds)
    json.dumps(payload, sort_keys=True)
    loaded = load_validation_dataset_payload(payload)
    assert isinstance(loaded, StrategyValidationDataset)
    assert loaded.report_id == ds.report_id
    assert len(loaded.records) == len(ds.records)
    for original, restored in zip(ds.records, loaded.records):
        assert original.opportunity_id == restored.opportunity_id
        assert original.symbol == restored.symbol
        assert original.tail_label == restored.tail_label
        assert original.mfe_5m == pytest.approx(restored.mfe_5m)


def test_load_validation_dataset_payload_tolerates_missing_optional_fields():
    """A future / legacy payload missing optional fields must still
    load."""
    minimal_payload = {
        "report_id": "rep-old",
        "records": [
            {
                "opportunity_id": "opp-1",
                "scan_batch_id": "batch-1",
                "symbol": "EDENUSDT",
                "candidate_stage": "early",
                "strategy_mode": "follow",
                # No schema_version, no per-window MFE/MAE.
            }
        ],
    }
    loaded = load_validation_dataset_payload(minimal_payload)
    assert loaded.report_id == "rep-old"
    assert len(loaded.records) == 1
    assert loaded.records[0].opportunity_id == "opp-1"
    assert (
        loaded.records[0].schema_version
        == STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
    )


def test_load_validation_dataset_payload_rejects_non_mapping():
    with pytest.raises(TypeError):
        load_validation_dataset_payload("not a mapping")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Runtime emits the new event types
# ---------------------------------------------------------------------------
def _seed_runtime_with_diverse_samples(
    runtime: StrategyValidationRuntime,
    *,
    n: int = 30,
) -> None:
    """Seed the runtime with samples by directly registering them.

    We bypass observe_label_record() because that path requires a
    full LabelTrackingRecord + AdaptiveCandidateContext fixture. The
    runtime's _samples_by_opportunity buffer is the same end-state.
    """
    for s in _diverse_samples(n):
        runtime._samples_by_opportunity[s.opportunity_id] = (
            runtime._samples_by_opportunity.get(s.opportunity_id)
        )
        # Use the runtime's internal _SampleEntry indirectly via
        # observe_label_record() with synthesised fixture.
        from app.adaptive.strategy_validation_runtime import _SampleEntry

        runtime._samples_by_opportunity[s.opportunity_id] = _SampleEntry(
            sample=s, source_event_id="", created_at_ms=0
        )


def test_runtime_emits_dataset_built_and_quality_gate_events(tmp_path: Path):
    """Driving flush_report() must emit one
    STRATEGY_VALIDATION_DATASET_BUILT, one
    STRATEGY_VALIDATION_DATASET_EXPORTED, and one
    STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED with the
    brief-mandated identity block."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime_with_diverse_samples(runtime, n=30)

        runtime.flush_report(
            report_id="rep-flush",
            generated_at_ms=1_700_000_000_000,
        )

        for et in (
            EventType.STRATEGY_VALIDATION_DATASET_BUILT,
            EventType.STRATEGY_VALIDATION_DATASET_EXPORTED,
            EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED,
        ):
            events = repo.list_events(event_type=et)
            assert len(events) >= 1, f"missing {et.value}"
            ev = events[-1]
            # Brief-mandated identity block.
            for field in (
                "report_id",
                "timestamp",
                "strategy_version",
                "scoring_version",
                "risk_config_version",
                "state_machine_version",
                "schema_version",
            ):
                assert field in ev.payload, (
                    f"event {et.value} missing payload field {field}"
                )
            assert ev.payload["report_id"] == "rep-flush"
            assert (
                ev.payload["schema_version"]
                == STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
            )
            assert (
                ev.source_module == StrategyValidationRuntime.SOURCE_MODULE
            )
        # The QUALITY_GATE_EVALUATED event carries the gate_status.
        gate_ev = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED
        )[-1]
        assert gate_ev.payload["gate_status"] in QUALITY_GATE_STATUSES
        # Runtime cached the dataset + gate result for the daily
        # report builder.
        assert runtime.latest_dataset is not None
        assert runtime.latest_quality_gate_result is not None
        assert runtime.dataset_built_count >= 1
        assert runtime.dataset_exported_count >= 1
        assert runtime.quality_gate_evaluated_count >= 1
    finally:
        dbs.close()


def test_runtime_disabled_dataset_skips_dataset_events(tmp_path: Path):
    """When dataset_enabled=False the runtime emits the seven
    Phase 11C.1C-C-B-A events but NOT the three new dataset
    events."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(
            event_repo=repo,
            config=StrategyValidationRuntimeConfig(dataset_enabled=False),
        )
        _seed_runtime_with_diverse_samples(runtime, n=30)
        runtime.flush_report(
            report_id="rep-no-dataset",
            generated_at_ms=1_700_000_000_000,
        )
        for et in (
            EventType.STRATEGY_VALIDATION_DATASET_BUILT,
            EventType.STRATEGY_VALIDATION_DATASET_EXPORTED,
            EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED,
        ):
            assert repo.count_events(event_type=et) == 0
        # Phase 11C.1C-C-B-A events still flow.
        assert (
            repo.count_events(
                event_type=EventType.STRATEGY_VALIDATION_REPORT_GENERATED
            )
            >= 1
        )
    finally:
        dbs.close()


def test_runtime_quality_gate_uses_config_thresholds(tmp_path: Path):
    """Custom quality_gate_* config values flow through to the
    emitted gate event."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        cfg = StrategyValidationRuntimeConfig(
            quality_gate_min_total_samples=1,
            quality_gate_min_completed_tail_labels=1,
            quality_gate_min_strategy_mode_coverage=1,
            quality_gate_min_candidate_stage_coverage=1,
            quality_gate_min_score_bucket_coverage=1,
        )
        runtime = StrategyValidationRuntime(event_repo=repo, config=cfg)
        _seed_runtime_with_diverse_samples(runtime, n=30)
        runtime.flush_report(
            report_id="rep-tight",
            generated_at_ms=1_700_000_000_000,
        )
        gate_ev = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED
        )[-1]
        gate_block = gate_ev.payload["gate"]
        assert gate_block["min_total_samples"] == 1
        assert gate_block["min_strategy_mode_coverage"] == 1
        assert gate_ev.payload["gate_status"] == "pass"
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 6. Export bundle + replay
# ---------------------------------------------------------------------------
def test_export_bundle_contains_new_event_types(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime_with_diverse_samples(runtime, n=30)
        runtime.flush_report(
            report_id="rep-export",
            generated_at_ms=1_700_000_000_000,
        )
        out_dir = tmp_path / "exports"
        out_dir.mkdir()
        service = TestDataExportService(
            event_repo=repo, trading_mode="paper", output_dir=out_dir
        )
        result = service.export(
            range_label="range",
            start_ms=1_699_000_000_000,
            end_ms=2_000_000_000_000,
            type_filter="all",
        )
        with zipfile.ZipFile(result.zip_path) as zf:
            seen = {
                et.value: 0
                for et in (
                    EventType.STRATEGY_VALIDATION_DATASET_BUILT,
                    EventType.STRATEGY_VALIDATION_DATASET_EXPORTED,
                    EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED,
                )
            }
            for line in zf.read("events.jsonl").decode("utf-8").splitlines():
                row = json.loads(line)
                if row.get("event_type") in seen:
                    seen[row["event_type"]] += 1
            for k, v in seen.items():
                assert v >= 1, f"export missing event {k}"
    finally:
        dbs.close()


def test_replay_reads_validation_dataset_events(tmp_path: Path):
    """ReplayEngine accepts events.db containing the three new
    dataset events without raising; replay_risk_rejections walks
    every event including unknown types."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        # Old-style legacy event first.
        repo.append(
            Event(
                event_type=EventType.MARKET_SNAPSHOT,
                source_module="legacy",
                symbol="LEGACYUSDT",
                timestamp=1_700_000_000_000,
                payload={"hello": "world"},
            )
        )
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime_with_diverse_samples(runtime, n=30)
        runtime.flush_report(
            report_id="rep-replay",
            generated_at_ms=1_700_000_000_000,
        )
        engine = ReplayEngine(event_repo=repo)
        rejects = engine.replay_risk_rejections()
        assert isinstance(rejects, list)
        for et in (
            EventType.STRATEGY_VALIDATION_DATASET_BUILT,
            EventType.STRATEGY_VALIDATION_DATASET_EXPORTED,
            EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED,
        ):
            assert repo.count_events(event_type=et) >= 1
    finally:
        dbs.close()


def test_replay_handles_dataset_events_missing_schema_version(tmp_path: Path):
    """A legacy / future dataset event row without ``schema_version``
    must NOT crash replay."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        repo.append(
            Event(
                event_type=EventType.STRATEGY_VALIDATION_DATASET_BUILT,
                source_module="legacy_dataset",
                symbol=None,
                timestamp=1_700_000_000_000,
                payload={
                    "report_id": "legacy-rep",
                    "record_count": 5,
                    # schema_version intentionally missing
                },
            )
        )
        rows = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_DATASET_BUILT
        )
        assert len(rows) == 1
        engine = ReplayEngine(event_repo=repo)
        engine.replay_risk_rejections()
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 7. Daily report integration
# ---------------------------------------------------------------------------
def test_daily_report_contains_validation_dataset_metrics(tmp_path: Path):
    """The Phase 11B daily report's snapshot + Markdown carry the
    Phase 11C.1C-C-B-B-A dataset / quality-gate fields."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime_with_diverse_samples(runtime, n=40)
        runtime.flush_report(
            report_id="rep-daily",
            generated_at_ms=1_700_000_000_000,
        )

        builder = DailyReportBuilder(
            event_repo=repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=1_699_000_000_000,
            finished_at_ms=2_000_000_000_000,
            write_to_disk=False,
            strategy_validation_metrics=runtime.metrics_payload(),
        )
        # Snapshot fields populated.
        assert snapshot.validation_dataset_records >= 1
        assert snapshot.validation_dataset_built_count >= 1
        assert snapshot.validation_dataset_exported_count >= 1
        assert snapshot.validation_quality_gate_evaluated_count >= 1
        assert snapshot.validation_quality_gate_status in QUALITY_GATE_STATUSES
        assert isinstance(snapshot.validation_dataset_symbols, list)
        assert isinstance(
            snapshot.validation_dataset_tail_label_counts, dict
        )
        # Markdown body contains the new section header.
        assert (
            "Phase 11C.1C-C-B-B-A Strategy Validation Dataset Builder"
            in snapshot.markdown
        )
        assert "Quality gate status" in snapshot.markdown
        assert "Validation dataset records" in snapshot.markdown
        assert "Phase 12 remains FORBIDDEN" in snapshot.markdown
        # Payload also carries the new keys.
        payload = snapshot.to_payload()
        for key in (
            "validation_dataset_records",
            "validation_dataset_symbols",
            "validation_dataset_tail_label_counts",
            "validation_quality_gate_status",
            "validation_quality_gate_reasons",
            "validation_dataset_export_ready",
            "validation_dataset_replay_ready",
        ):
            assert key in payload
    finally:
        dbs.close()


def test_daily_report_renders_when_no_dataset(tmp_path: Path):
    """Even with no dataset events, the Markdown still renders."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        builder = DailyReportBuilder(
            event_repo=repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=1_699_000_000_000,
            finished_at_ms=2_000_000_000_000,
            write_to_disk=False,
        )
        assert "Phase 11C.1C-C-B-B-A" in snapshot.markdown
        assert snapshot.validation_dataset_records == 0
        assert snapshot.validation_quality_gate_status == ""
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 8. Safety boundary
# ---------------------------------------------------------------------------
def test_no_live_trading_flags_unchanged():
    """Phase 1 safety lock invariants. The dataset / quality gate
    cannot loosen them."""
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


def test_validation_dataset_does_not_trigger_execution(tmp_path: Path):
    """Building the dataset + evaluating the gate MUST never emit
    any of the trading event types and never call Telegram outbound.
    The gate_status MUST NEVER trigger a real trade."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime_with_diverse_samples(runtime, n=40)
        runtime.flush_report(
            report_id="rep-safety",
            generated_at_ms=1_700_000_000_000,
        )
        forbidden = {
            EventType.ORDER_SENT,
            EventType.ORDER_FILLED,
            EventType.ORDER_PARTIAL_FILLED,
            EventType.ORDER_ACK,
            EventType.ORDER_CANCELLED,
            EventType.POSITION_OPENED,
            EventType.POSITION_CLOSED,
            EventType.POSITION_UPDATED,
            EventType.STOP_SENT,
            EventType.STOP_CONFIRMED,
            EventType.STOP_FAILED,
            EventType.TELEGRAM_MESSAGE_SENT,
            EventType.EXIT_TRIGGERED,
        }
        for et in forbidden:
            assert (
                repo.count_events(event_type=et) == 0
            ), f"dataset/gate emitted forbidden {et.value}"
        # The gate result vocabulary is fixed and descriptive only.
        gate_evs = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED
        )
        assert gate_evs
        for ev in gate_evs:
            assert ev.payload["gate_status"] in QUALITY_GATE_STATUSES
        # All three new event types attribute to the runtime
        # source_module - no other module is allowed to emit them.
        for et in (
            EventType.STRATEGY_VALIDATION_DATASET_BUILT,
            EventType.STRATEGY_VALIDATION_DATASET_EXPORTED,
            EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED,
        ):
            for ev in repo.list_events(event_type=et):
                assert (
                    ev.source_module
                    == StrategyValidationRuntime.SOURCE_MODULE
                )
    finally:
        dbs.close()


def test_phase_12_remains_forbidden(tmp_path: Path):
    """Phase 12 is FORBIDDEN under the Phase 1 safety lock; the
    dataset / quality gate cannot change that."""
    s = _settings()
    assert s.live_trading_enabled is False
    assert s.exchange_live_order_enabled is False
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime_with_diverse_samples(runtime, n=40)
        runtime.flush_report(
            report_id="rep-phase12",
            generated_at_ms=1_700_000_000_000,
        )
        # Schema version still belongs to Phase 11C.1C-C-B-B-A.
        ev = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_DATASET_BUILT
        )[-1]
        assert "phase_11c_1c_c_b_b_a" in ev.payload["schema_version"]
        # The dataset version label likewise.
        assert ev.payload["dataset_version"] == STRATEGY_VALIDATION_DATASET_VERSION
        # The runtime cached gate vocabulary cannot include anything
        # that implies trade authorisation.
        gate_status = runtime.latest_quality_gate_result.gate_status
        assert gate_status in QUALITY_GATE_STATUSES
        assert gate_status not in {
            "approved",
            "trade",
            "open",
            "buy",
            "sell",
            "live",
        }
    finally:
        dbs.close()


def test_runtime_config_quality_gate_thresholds_round_trip():
    """Settings -> config -> StrategyValidationQualityGate must
    preserve the quality-gate thresholds end-to-end so a YAML
    operator override actually reaches the gate evaluation."""
    s = _settings()
    cfg = StrategyValidationRuntimeConfig.from_settings_section(
        s.strategy_validation
    )
    gate = cfg.quality_gate()
    assert gate.min_total_samples == s.strategy_validation.quality_gate_min_total_samples
    assert (
        gate.require_export_roundtrip
        == s.strategy_validation.quality_gate_require_export_roundtrip
    )
    # And the parent runtime config has the same flag.
    assert cfg.dataset_enabled == s.strategy_validation.dataset_enabled
