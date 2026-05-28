"""Phase 11C.1C-C-B-B-B-D-E - Block B Integrated Evidence Checkpoint v0
unit tests.

Paper / report / evidence ONLY. None of these tests authorise a
real trade or modify any runtime knob.

Test plan:

  1. ``no_evidence_run`` - empty workspace yields
     ``status=INSUFFICIENT_EVIDENCE``, ``next_allowed_phase``
     equals ``NEEDS_OPERATOR_EVIDENCE``, and every component
     status is ``INSUFFICIENT_EVIDENCE``.
  2. ``partial_evidence_run`` - some D-A records exist but the
     post-discovery report is missing -> ``PARTIAL_EVIDENCE``.
  3. ``evidence_generated_run`` - D-A + D-B reports + B2-A / B2-B
     / B3 events are present -> ``EVIDENCE_GENERATED``.
  4. ``next_allowed_phase`` is correct for every status.
  5. Every emitted payload has ``phase_12_forbidden=True`` and
     ``auto_tuning_allowed=False``.
  6. Every emitted payload has none of the forbidden trade-authority
     / runtime-tuning keys.
  7. The runner module never imports
     ``app.risk`` / ``app.execution`` / ``app.exchanges`` /
     ``app.llm`` / ``app.telegram``.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adaptive.discovery_quality_scorecard import (  # noqa: E402
    DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS,
    DiscoveryQualityBucket,
)
from scripts import run_block_b_integrated_evidence_checkpoint as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            fh.write("\n")


def _write_post_discovery_report(
    path: Path,
    *,
    status: str,
    evaluated_count: int,
    price_path_records_loaded: int = 0,
    price_path_records_missing: int = 0,
    kline_interval_used: str = "1d",
    label_summary: dict[str, int] | None = None,
    notable: dict[str, dict[str, str]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "phase_11c_1c_c_b_b_b_d_b.post_discovery_outcome.v1",
        "source_phase": "phase_11c_1c_c_b_b_b_d_b",
        "status": status,
        "reference_window": "60d",
        "evaluated_count": evaluated_count,
        "report_generated_count": 1 if evaluated_count > 0 else 0,
        "price_path_records_loaded": price_path_records_loaded,
        "price_path_records_missing": price_path_records_missing,
        "kline_interval_used": kline_interval_used,
        "price_path_source_summary": {},
        "price_path_missing_reason_summary": {},
        "approximate_intra_day_timestamp_count": 0,
        "notable_symbol_price_path_summary": notable
        or {
            "RAVEUSDT": {
                "source": "absent",
                "missing_reason": "no_top_mover_row_covering_first_seen_time",
                "loaded": "false",
                "record_count": "0",
                "loaded_record_count": "0",
            },
            "STOUSDT": {
                "source": "absent",
                "missing_reason": "no_top_mover_row_covering_first_seen_time",
                "loaded": "false",
                "record_count": "0",
                "loaded_record_count": "0",
            },
        },
    }
    if evaluated_count > 0:
        payload["report"] = {
            "outcome_label_summary": label_summary
            or {
                "USABLE_UPSIDE": 30,
                "EARLY_DISCOVERY": 30,
                "LATE_CHASE": 5,
                "MISSED_STRONG_TAIL": 0,
                "INSUFFICIENT_PRICE_PATH": 0,
            },
            "detection_timing_label_summary": {
                "EARLY": 30,
                "ON_TIME": 30,
                "LATE": 5,
            },
        }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_d_a_event(*, records: int) -> dict[str, Any]:
    return {
        "event_type": runner.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
        "timestamp": 1_768_000_000_000,
        "payload": {
            "schema_version": (
                "phase_11c_1c_c_b_b_b_d_a.historical_mover_coverage_backfill.v1"
            ),
            "source_phase": "phase_11c_1c_c_b_b_b_d_a",
            "backfill_status": "READY",
            "reference_window_days": 60,
            "window_start_utc_ms": 1_762_000_000_000,
            "window_end_utc_ms": 1_768_000_000_000,
            "top_mover_count": records,
            "captured_top_mover_count": records // 4,
            "missed_top_mover_count": records - (records // 4),
            "records": [
                {
                    "symbol": f"SYM{i:03d}USDT",
                    "coverage_status": "missed",
                }
                for i in range(records)
            ],
            "miss_reason_summary": {},
        },
    }


def _make_record_audited_events(count: int) -> list[dict[str, Any]]:
    return [
        {
            "event_type": runner.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
            "timestamp": 1_768_000_000_000 + i,
            "symbol": f"SYM{i:03d}USDT",
            "payload": {
                "symbol": f"SYM{i:03d}USDT",
                "coverage_status": "missed",
            },
        }
        for i in range(count)
    ]


def _make_simple_event(event_type: str, *, count: int) -> list[dict[str, Any]]:
    return [
        {
            "event_type": event_type,
            "timestamp": 1_768_000_000_000 + i,
            "payload": {"index": i},
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# 1. Insufficient evidence
# ---------------------------------------------------------------------------


def test_no_evidence_yields_insufficient_evidence(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_checkpoint(
        reports_dir=tmp_path / "reports",
        exports_dir=tmp_path / "reports" / "exports",
        post_discovery_dir=tmp_path / "reports" / "post_discovery_outcome",
        output_dir=output_dir,
        reference_window="60d",
    )
    assert result.status == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert result.next_allowed_phase == runner.NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE
    payload = result.payload
    assert payload["status"] == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert payload["d_a_status"] == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    assert payload["d_b_status"] == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    assert (
        payload["b1_1_price_path_status"]
        == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    )
    assert (
        payload["reject_attribution_status"]
        == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    )
    assert (
        payload["severe_miss_triage_status"]
        == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    )
    assert (
        payload["discovery_quality_scorecard_status"]
        == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    )
    assert payload["evaluated_count"] == 0
    assert payload["coverage_record_count"] == 0
    assert payload["post_discovery_record_count"] == 0
    assert payload["price_path_records_loaded"] == 0
    assert payload["price_path_records_missing"] == 0
    assert payload["severe_miss_count"] == 0
    assert payload["false_negative_reject_count"] == 0
    assert payload["data_gap_count"] == 0
    assert (
        payload["discovery_quality_bucket"]
        == DiscoveryQualityBucket.INSUFFICIENT_EVIDENCE
    )
    assert payload["phase_12_forbidden"] is True
    assert payload["auto_tuning_allowed"] is False
    assert "RAVEUSDT" in payload["notable_symbols"]
    assert "STOUSDT" in payload["notable_symbols"]
    assert result.output_report_path.is_file()
    assert result.output_summary_path.is_file()


# ---------------------------------------------------------------------------
# 2. Partial evidence
# ---------------------------------------------------------------------------


def test_partial_evidence_when_d_b_missing(tmp_path: Path) -> None:
    """D-A export is present but no D-B post-discovery report
    can be loaded -> PARTIAL_EVIDENCE."""

    exports_dir = tmp_path / "exports"
    events: list[dict[str, Any]] = []
    events.append(_make_d_a_event(records=300))
    events.extend(_make_record_audited_events(300))
    _write_jsonl(exports_dir / "events.jsonl", events)

    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        post_discovery_dir=tmp_path / "missing_post_discovery",
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert result.status == runner.PARTIAL_EVIDENCE_STATUS
    assert result.next_allowed_phase == runner.NEXT_PHASE_REPLAY_REFLECTION
    payload = result.payload
    assert payload["d_a_status"] == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    assert payload["d_b_status"] == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    assert payload["coverage_record_count"] == 300
    assert payload["phase_12_forbidden"] is True
    assert payload["auto_tuning_allowed"] is False


def test_partial_evidence_when_data_gap_high(tmp_path: Path) -> None:
    """All component evidence present but data gap rate / absolute
    is high -> PARTIAL_EVIDENCE."""

    exports_dir = tmp_path / "exports"
    post_dir = tmp_path / "post"
    events: list[dict[str, Any]] = []
    events.append(_make_d_a_event(records=300))
    events.extend(_make_record_audited_events(300))
    events.extend(
        _make_simple_event(
            runner.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED, count=1
        )
    )
    events.extend(
        _make_simple_event(
            runner.SEVERE_MISSED_TAIL_TRIAGE_GENERATED, count=1
        )
    )
    events.extend(
        _make_simple_event(
            runner.DISCOVERY_QUALITY_SCORECARD_GENERATED, count=1
        )
    )
    _write_jsonl(exports_dir / "events.jsonl", events)
    _write_post_discovery_report(
        post_dir / "post_discovery_outcome_report.json",
        status="EVIDENCE_GENERATED",
        evaluated_count=300,
        price_path_records_loaded=17,
        price_path_records_missing=283,
    )

    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        post_discovery_dir=post_dir,
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert result.status == runner.PARTIAL_EVIDENCE_STATUS
    assert result.next_allowed_phase == runner.NEXT_PHASE_REPLAY_REFLECTION
    payload = result.payload
    assert payload["data_gap_count"] >= 100
    assert payload["price_path_records_missing"] == 283
    assert payload["price_path_records_loaded"] == 17


# ---------------------------------------------------------------------------
# 3. Evidence generated
# ---------------------------------------------------------------------------


def test_evidence_generated_when_all_components_present(tmp_path: Path) -> None:
    exports_dir = tmp_path / "exports"
    post_dir = tmp_path / "post"
    events: list[dict[str, Any]] = []
    events.append(_make_d_a_event(records=300))
    events.extend(_make_record_audited_events(300))
    events.extend(
        _make_simple_event(
            runner.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED, count=1
        )
    )
    events.extend(
        _make_simple_event(
            runner.REJECT_TO_OUTCOME_CASE_ATTRIBUTED, count=12
        )
    )
    events.extend(
        _make_simple_event(
            runner.CORRECT_PROTECTIVE_REJECT_CONFIRMED, count=8
        )
    )
    events.extend(
        _make_simple_event(
            runner.FALSE_NEGATIVE_REJECT_DETECTED, count=2
        )
    )
    events.extend(
        _make_simple_event(
            runner.SEVERE_MISSED_TAIL_TRIAGE_GENERATED, count=1
        )
    )
    events.extend(
        _make_simple_event(
            runner.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED, count=15
        )
    )
    events.extend(
        _make_simple_event(
            runner.DISCOVERY_QUALITY_SCORECARD_GENERATED, count=1
        )
    )
    events.extend(
        _make_simple_event(
            runner.DISCOVERY_QUALITY_BUCKET_EVALUATED, count=1
        )
    )
    _write_jsonl(exports_dir / "events.jsonl", events)
    _write_post_discovery_report(
        post_dir / "post_discovery_outcome_report.json",
        status="EVIDENCE_GENERATED",
        evaluated_count=300,
        price_path_records_loaded=290,
        price_path_records_missing=10,
        label_summary={
            "USABLE_UPSIDE": 200,
            "EARLY_DISCOVERY": 50,
            "LATE_CHASE": 20,
            "MISSED_STRONG_TAIL": 20,
            "INSUFFICIENT_PRICE_PATH": 10,
        },
    )

    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        post_discovery_dir=post_dir,
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert result.status == runner.EVIDENCE_GENERATED_STATUS
    assert result.next_allowed_phase == runner.NEXT_PHASE_REPLAY_REFLECTION
    payload = result.payload
    assert payload["d_a_status"] == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    assert payload["d_b_status"] == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    assert (
        payload["b1_1_price_path_status"]
        == runner.COMPONENT_STATUS_PARTIAL_EVIDENCE
    )
    assert (
        payload["reject_attribution_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert (
        payload["severe_miss_triage_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert (
        payload["discovery_quality_scorecard_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert payload["coverage_record_count"] == 300
    assert payload["post_discovery_record_count"] == 300
    assert payload["evaluated_count"] == 300
    assert payload["severe_miss_count"] == 15
    assert payload["false_negative_reject_count"] == 2
    assert payload["data_gap_count"] == 10
    assert payload["discovery_quality_bucket"] in DiscoveryQualityBucket.ALL
    assert (
        payload["discovery_quality_bucket"]
        != DiscoveryQualityBucket.INSUFFICIENT_EVIDENCE
    )
    assert payload["phase_12_forbidden"] is True
    assert payload["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 4. Next-allowed-phase mapping
# ---------------------------------------------------------------------------


def test_next_allowed_phase_mapping() -> None:
    assert (
        runner._next_allowed_phase(runner.EVIDENCE_GENERATED_STATUS)
        == runner.NEXT_PHASE_REPLAY_REFLECTION
    )
    assert (
        runner._next_allowed_phase(runner.PARTIAL_EVIDENCE_STATUS)
        == runner.NEXT_PHASE_REPLAY_REFLECTION
    )
    assert (
        runner._next_allowed_phase(runner.INSUFFICIENT_EVIDENCE_STATUS)
        == runner.NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE
    )
    # The runner MUST refuse to authorise Phase 12.
    assert runner.NEXT_PHASE_REPLAY_REFLECTION.startswith(
        "Phase 11C.1C-C-B-B-B-E-A"
    )


# ---------------------------------------------------------------------------
# 5. phase_12_forbidden / auto_tuning_allowed pinned on every payload
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_and_auto_tuning_disallowed_on_every_payload(
    tmp_path: Path,
) -> None:
    # Insufficient run.
    r1 = runner.run_checkpoint(
        reports_dir=tmp_path / "a" / "reports",
        exports_dir=tmp_path / "a" / "exports",
        post_discovery_dir=tmp_path / "a" / "post",
        output_dir=tmp_path / "a" / "out",
        reference_window="60d",
    )
    assert r1.payload["phase_12_forbidden"] is True
    assert r1.payload["auto_tuning_allowed"] is False

    # Evidence generated run.
    exports_dir = tmp_path / "b" / "exports"
    post_dir = tmp_path / "b" / "post"
    events: list[dict[str, Any]] = []
    events.append(_make_d_a_event(records=20))
    events.extend(_make_record_audited_events(20))
    events.extend(
        _make_simple_event(
            runner.DISCOVERY_QUALITY_SCORECARD_GENERATED, count=1
        )
    )
    _write_jsonl(exports_dir / "events.jsonl", events)
    _write_post_discovery_report(
        post_dir / "post_discovery_outcome_report.json",
        status="EVIDENCE_GENERATED",
        evaluated_count=20,
        price_path_records_loaded=20,
        price_path_records_missing=0,
        label_summary={
            "USABLE_UPSIDE": 18,
            "EARLY_DISCOVERY": 0,
            "LATE_CHASE": 1,
            "MISSED_STRONG_TAIL": 1,
            "INSUFFICIENT_PRICE_PATH": 0,
        },
    )
    r2 = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        post_discovery_dir=post_dir,
        output_dir=tmp_path / "b" / "out",
        reference_window="60d",
    )
    assert r2.payload["phase_12_forbidden"] is True
    assert r2.payload["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 6. Forbidden trade-authority / runtime-tuning fields absent
# ---------------------------------------------------------------------------


def _walk_keys(node: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            keys.append(str(k))
            keys.extend(_walk_keys(v))
    elif isinstance(node, (list, tuple)):
        for item in node:
            keys.extend(_walk_keys(item))
    return keys


def test_no_forbidden_keys_in_emitted_payload(tmp_path: Path) -> None:
    exports_dir = tmp_path / "exports"
    post_dir = tmp_path / "post"
    events: list[dict[str, Any]] = []
    events.append(_make_d_a_event(records=50))
    events.extend(_make_record_audited_events(50))
    events.extend(
        _make_simple_event(
            runner.SEVERE_MISSED_TAIL_TRIAGE_GENERATED, count=1
        )
    )
    _write_jsonl(exports_dir / "events.jsonl", events)
    _write_post_discovery_report(
        post_dir / "post_discovery_outcome_report.json",
        status="EVIDENCE_GENERATED",
        evaluated_count=50,
        price_path_records_loaded=40,
        price_path_records_missing=10,
    )

    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        post_discovery_dir=post_dir,
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    keys = set(_walk_keys(result.payload))
    forbidden_observed = keys & DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS
    assert forbidden_observed == set(), (
        f"forbidden keys leaked into payload: {sorted(forbidden_observed)}"
    )

    # Also verify on disk.
    on_disk = json.loads(result.output_report_path.read_text(encoding="utf-8"))
    assert (
        set(_walk_keys(on_disk)) & DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS
        == set()
    )


# ---------------------------------------------------------------------------
# 7. No banned imports
# ---------------------------------------------------------------------------


_BANNED_IMPORT_PREFIXES: tuple[str, ...] = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.llm",
    "app.telegram",
)


def test_runner_module_does_not_import_banned_modules() -> None:
    runner_path = Path(runner.__file__)
    source = runner_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if any(
                    name == p or name.startswith(p + ".")
                    for p in _BANNED_IMPORT_PREFIXES
                ):
                    banned.append(name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                module == p or module.startswith(p + ".")
                for p in _BANNED_IMPORT_PREFIXES
            ):
                banned.append(module)
    assert banned == [], f"banned imports observed: {banned}"


def test_runner_module_does_not_import_app_config_or_risk_dynamically() -> None:
    """Defensive: even string occurrences of forbidden module
    paths should not appear in the runner source as actual import
    statements (cheap belt-and-suspenders alongside the AST check).
    """

    runner_path = Path(runner.__file__)
    source = runner_path.read_text(encoding="utf-8")
    for banned_prefix in _BANNED_IMPORT_PREFIXES + ("app.config",):
        assert (
            f"import {banned_prefix}" not in source
        ), f"runner contains banned 'import {banned_prefix}' statement"
        assert (
            f"from {banned_prefix}" not in source
        ), f"runner contains banned 'from {banned_prefix}' statement"


# ---------------------------------------------------------------------------
# 8. Report files written deterministically
# ---------------------------------------------------------------------------


def test_outputs_written_to_expected_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_checkpoint(
        reports_dir=tmp_path / "reports",
        exports_dir=tmp_path / "exports",
        post_discovery_dir=tmp_path / "post",
        output_dir=output_dir,
        reference_window="60d",
    )
    assert (
        result.output_report_path
        == output_dir / "block_b_integrated_evidence_report.json"
    )
    assert (
        result.output_summary_path
        == output_dir / "block_b_integrated_evidence_report.md"
    )
    assert result.output_report_path.is_file()
    assert result.output_summary_path.is_file()
    md = result.output_summary_path.read_text(encoding="utf-8")
    assert "Block B Integrated Evidence Checkpoint" in md
    assert "Phase 12 remains FORBIDDEN" in md


# ---------------------------------------------------------------------------
# 9. Notable-symbols watchlist surfaced even when post-discovery missing
# ---------------------------------------------------------------------------


def test_notable_symbols_block_always_present(tmp_path: Path) -> None:
    result = runner.run_checkpoint(
        reports_dir=tmp_path / "a",
        exports_dir=tmp_path / "b",
        post_discovery_dir=tmp_path / "c",
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    notable = result.payload["notable_symbols"]
    assert "RAVEUSDT" in notable
    assert "STOUSDT" in notable
    for entry in notable.values():
        assert "loaded" in entry
        assert "source" in entry
        assert "missing_reason" in entry


# ---------------------------------------------------------------------------
# 10. CLI exit codes
# ---------------------------------------------------------------------------


def test_main_returns_nonzero_on_insufficient_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "out"
    rc = runner.main(
        [
            "--reports-dir",
            str(tmp_path / "reports"),
            "--exports-dir",
            str(tmp_path / "exports"),
            "--post-discovery-dir",
            str(tmp_path / "post"),
            "--output-dir",
            str(output_dir),
            "--reference-window",
            "60d",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert parsed["next_allowed_phase"] == runner.NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE


def test_main_returns_zero_on_evidence_generated(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exports_dir = tmp_path / "exports"
    post_dir = tmp_path / "post"
    events: list[dict[str, Any]] = []
    events.append(_make_d_a_event(records=20))
    events.extend(_make_record_audited_events(20))
    events.extend(
        _make_simple_event(
            runner.DISCOVERY_QUALITY_SCORECARD_GENERATED, count=1
        )
    )
    _write_jsonl(exports_dir / "events.jsonl", events)
    _write_post_discovery_report(
        post_dir / "post_discovery_outcome_report.json",
        status="EVIDENCE_GENERATED",
        evaluated_count=20,
        price_path_records_loaded=20,
        price_path_records_missing=0,
        label_summary={
            "USABLE_UPSIDE": 18,
            "EARLY_DISCOVERY": 0,
            "LATE_CHASE": 1,
            "MISSED_STRONG_TAIL": 1,
            "INSUFFICIENT_PRICE_PATH": 0,
        },
    )
    rc = runner.main(
        [
            "--reports-dir",
            str(exports_dir),
            "--exports-dir",
            str(exports_dir),
            "--post-discovery-dir",
            str(post_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--reference-window",
            "60d",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == runner.EVIDENCE_GENERATED_STATUS
    assert parsed["next_allowed_phase"] == runner.NEXT_PHASE_REPLAY_REFLECTION
