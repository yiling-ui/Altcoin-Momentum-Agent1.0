"""Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0 evidence
runner unit tests.

Paper / report / evidence ONLY. None of these tests authorise a
real trade or modify any runtime knob.

Test plan:

  1. Insufficient-evidence path: runner exits status=INSUFFICIENT_EVIDENCE
     when no D-A coverage payload is reachable, writes the marker
     report + empty events.jsonl, and never touches a forbidden key.
  2. Coverage-payload path: runner consumes a real-shape D-A payload
     and emits one POST_DISCOVERY_OUTCOME_EVALUATED per record + one
     POST_DISCOVERY_OUTCOME_REPORT_GENERATED.
  3. MISSED_STRONG_TAIL surfacing: a missed mover with a strong
     reference tail produces an outcome_label = MISSED_STRONG_TAIL
     record even without a price path.
  4. Operator price-paths: an operator-supplied price path is
     applied to the matching symbol, refining the outcome label.
  5. Forbidden-key guard: the runner refuses to ever write a
     forbidden trade-authority key.
  6. No banned imports: the runner module never imports Risk /
     Execution / Exchange private / LLM / Telegram modules.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adaptive.post_discovery_outcome_metrics import (  # noqa: E402
    OutcomeLabel,
    POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS,
)
from scripts import run_post_discovery_outcome_evidence as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ms(day: int, hour: int = 0) -> int:
    base = 1_767_225_600_000  # ~ 2026-01-01T00:00:00Z
    return base + day * 86_400_000 + hour * 3_600_000


def _build_d_a_payload(
    *,
    records: list[dict[str, object]],
) -> dict[str, object]:
    """Return a minimal but real-shape D-A coverage payload."""

    return {
        "schema_version": "phase_11c_1c_c_b_b_b_d_a.historical_mover_coverage_backfill.v1",
        "source_phase": "phase_11c_1c_c_b_b_b_d_a",
        "backfill_status": "READY",
        "reference_window_days": 60,
        "window_start_utc_ms": _ms(0),
        "window_end_utc_ms": _ms(60),
        "history_days_observed": 60,
        "top_mover_count": len(records),
        "eligible_top_mover_count": len(records),
        "captured_top_mover_count": 0,
        "partially_captured_top_mover_count": 0,
        "missed_top_mover_count": len(records),
        "excluded_top_mover_count": 0,
        "capture_recall_rate": 0.0,
        "partial_capture_rate": 0.0,
        "miss_rate": 1.0,
        "anomaly_detected_rate": 0.0,
        "label_tracking_rate": 0.0,
        "tail_label_assigned_rate": 0.0,
        "strategy_validation_sample_rate": 0.0,
        "risk_rejected_mover_count": 0,
        "not_in_universe_count": 0,
        "missing_event_history_count": 0,
        "data_unreliable_count": 0,
        "median_first_seen_latency_seconds": None,
        "p90_first_seen_latency_seconds": None,
        "records": records,
        "miss_reason_summary": {},
        "coverage_warnings": [],
        "lookahead_guard_warnings": [],
        "generated_at_ms": _ms(60),
    }


def _strong_tail_record(symbol: str, *, gain: float = 0.50) -> dict[str, object]:
    return {
        "schema_version": "phase_11c_1c_c_b_b_b_d_a.historical_mover_coverage_backfill.v1",
        "symbol": symbol,
        "coverage_status": "missed",
        "miss_reason": "not_in_universe",
        "miss_reasons": ["not_in_universe"],
        "notes": None,
        "reference": {
            "symbol": symbol,
            "reference_timestamp_utc_ms": _ms(7),
            "mover_window_start_utc_ms": _ms(0),
            "mover_window_end_utc_ms": _ms(7),
            "eligible_usdt_perpetual": True,
            "not_eligible_reason": None,
            "top_mover_rank": 1,
            "max_window_gain": gain,
            "max_24h_gain": gain * 0.4,
            "quote_volume_usdt": 1_000_000.0,
            "notes": None,
        },
        "capture_path": {
            "symbol": symbol,
            "first_seen_time_utc_ms": None,
            "first_seen_event_type": None,
            "first_seen_latency_seconds": None,
            "capture_path_depth": 0,
            "reached_anomaly": False,
            "reached_label_queue": False,
            "reached_tail_label": False,
            "reached_strategy_validation_sample": False,
            "risk_rejected": False,
            "data_unreliable": False,
            "observed_event_types": [],
            "observed_event_count": 0,
        },
    }


def _captured_early_record(
    symbol: str,
    *,
    first_seen_time_ms: int,
    first_seen_event: str = "ANOMALY_DETECTED",
    capture_path_depth: int = 5,
) -> dict[str, object]:
    return {
        "schema_version": "phase_11c_1c_c_b_b_b_d_a.historical_mover_coverage_backfill.v1",
        "symbol": symbol,
        "coverage_status": "captured",
        "miss_reason": None,
        "miss_reasons": [],
        "notes": None,
        "reference": {
            "symbol": symbol,
            "reference_timestamp_utc_ms": _ms(7),
            "mover_window_start_utc_ms": _ms(0),
            "mover_window_end_utc_ms": _ms(7),
            "eligible_usdt_perpetual": True,
            "not_eligible_reason": None,
            "top_mover_rank": 2,
            "max_window_gain": 0.40,
            "max_24h_gain": 0.20,
            "quote_volume_usdt": 5_000_000.0,
            "notes": None,
        },
        "capture_path": {
            "symbol": symbol,
            "first_seen_time_utc_ms": first_seen_time_ms,
            "first_seen_event_type": first_seen_event,
            "first_seen_latency_seconds": 30.0,
            "capture_path_depth": capture_path_depth,
            "reached_anomaly": True,
            "reached_label_queue": True,
            "reached_tail_label": True,
            "reached_strategy_validation_sample": True,
            "risk_rejected": False,
            "data_unreliable": False,
            "observed_event_types": [first_seen_event, "OPPORTUNITY_GRADED"],
            "observed_event_count": 8,
        },
    }


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_runner_insufficient_evidence_when_no_input(tmp_path: Path) -> None:
    """No coverage payload, no export dir, no events DB, no store -
    runner returns INSUFFICIENT_EVIDENCE and never fabricates."""

    output_dir = tmp_path / "out"
    result = runner.run_evidence_pipeline(
        coverage_payload=None,
        export_dir=None,
        events_db=None,
        historical_store_dir=None,
        price_paths_json=None,
        output_dir=output_dir,
        reference_window="60d",
    )
    assert result.status == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert result.evaluated_count == 0
    assert result.report_generated_count == 0
    assert result.output_report_path.is_file()
    assert result.output_events_path.is_file()
    assert result.output_summary_path.is_file()

    # Empty events file.
    events_text = result.output_events_path.read_text(encoding="utf-8")
    assert events_text == ""

    # Marker JSON.
    marker = json.loads(result.output_report_path.read_text(encoding="utf-8"))
    assert marker["status"] == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert marker["needs_operator_data"] is True
    assert marker["evaluated_count"] == 0
    assert marker["report_generated_count"] == 0
    assert marker["reference_window"] == "60d"
    assert any(
        runner.NEEDS_OPERATOR_DATA_STATUS in str(w)
        for w in marker["warnings"]
    )

    # Markdown surfaces the safety boundary.
    md = result.output_summary_path.read_text(encoding="utf-8")
    assert "Phase 12 remains FORBIDDEN" in md
    assert "INSUFFICIENT_EVIDENCE" in md


def test_runner_consumes_d_a_payload_and_emits_events(tmp_path: Path) -> None:
    """A real-shape D-A coverage payload yields one EVALUATED event
    per record + one REPORT_GENERATED event."""

    payload = _build_d_a_payload(
        records=[
            _strong_tail_record("RAVEUSDT", gain=0.60),
            _strong_tail_record("STOUSDT", gain=0.45),
        ]
    )
    payload_path = tmp_path / "d_a_payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    output_dir = tmp_path / "out"
    result = runner.run_evidence_pipeline(
        coverage_payload=payload_path,
        export_dir=None,
        events_db=None,
        historical_store_dir=None,
        price_paths_json=None,
        output_dir=output_dir,
        reference_window="60d",
    )

    assert result.status == runner.EVIDENCE_GENERATED_STATUS
    assert result.evaluated_count == 2
    assert result.report_generated_count == 1

    events_lines = [
        line
        for line in result.output_events_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    parsed = [json.loads(line) for line in events_lines]
    evaluated = [
        e
        for e in parsed
        if e["event_type"] == "POST_DISCOVERY_OUTCOME_EVALUATED"
    ]
    reports = [
        e
        for e in parsed
        if e["event_type"] == "POST_DISCOVERY_OUTCOME_REPORT_GENERATED"
    ]
    assert len(evaluated) == 2
    assert len(reports) == 1

    # Notable symbols pinned.
    assert result.notable_symbols["RAVEUSDT"].startswith("MISSED_STRONG_TAIL")
    assert result.notable_symbols["STOUSDT"].startswith("MISSED_STRONG_TAIL")

    # Outcome label summary contains MISSED_STRONG_TAIL.
    assert (
        result.label_summary.get(OutcomeLabel.MISSED_STRONG_TAIL, 0) == 2
    )


def test_runner_missed_strong_tail_surfaces_in_report(tmp_path: Path) -> None:
    """A missed mover with a strong reference tail produces a
    MISSED_STRONG_TAIL outcome_label without any price path."""

    payload = _build_d_a_payload(
        records=[_strong_tail_record("MEMEUSDT", gain=0.80)]
    )
    payload_path = tmp_path / "d_a_payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    output_dir = tmp_path / "out"
    result = runner.run_evidence_pipeline(
        coverage_payload=payload_path,
        export_dir=None,
        events_db=None,
        historical_store_dir=None,
        price_paths_json=None,
        output_dir=output_dir,
        reference_window="60d",
    )
    report = json.loads(
        result.output_report_path.read_text(encoding="utf-8")
    )
    assert report["status"] == runner.EVIDENCE_GENERATED_STATUS
    assert report["report"]["missed_strong_tail_count"] == 1
    summary = report["report"]["outcome_label_summary"]
    assert summary.get(OutcomeLabel.MISSED_STRONG_TAIL, 0) == 1


def test_runner_operator_price_paths_refine_outcome(tmp_path: Path) -> None:
    """An operator-supplied price path overrides the
    INSUFFICIENT_PRICE_PATH fallback for a captured mover."""

    first_seen = _ms(1, hour=2)
    payload = _build_d_a_payload(
        records=[
            _captured_early_record(
                "EARLYUSDT", first_seen_time_ms=first_seen
            ),
        ]
    )
    payload_path = tmp_path / "d_a_payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    price_paths = {
        "EARLYUSDT": [
            {"timestamp_utc_ms": _ms(1, hour=3), "price": 1.05},
            {"timestamp_utc_ms": _ms(1, hour=4), "price": 1.20},
            {"timestamp_utc_ms": _ms(1, hour=5), "price": 1.40},
            {"timestamp_utc_ms": _ms(1, hour=6), "price": 1.50},
        ]
    }
    paths_path = tmp_path / "price_paths.json"
    paths_path.write_text(json.dumps(price_paths), encoding="utf-8")

    output_dir = tmp_path / "out"
    result = runner.run_evidence_pipeline(
        coverage_payload=payload_path,
        export_dir=None,
        events_db=None,
        historical_store_dir=None,
        price_paths_json=paths_path,
        output_dir=output_dir,
        reference_window="60d",
    )

    assert result.evaluated_count == 1
    # The captured record now has a real price path - it should NOT
    # be INSUFFICIENT_PRICE_PATH.
    assert (
        OutcomeLabel.INSUFFICIENT_PRICE_PATH not in result.label_summary
        or result.label_summary[OutcomeLabel.INSUFFICIENT_PRICE_PATH] == 0
    )


def test_runner_export_dir_fallback(tmp_path: Path) -> None:
    """When the runner cannot find --coverage-payload, it falls back
    to scanning --export-dir for a HISTORICAL_MOVER_COVERAGE_BACKFILL_
    GENERATED event."""

    payload = _build_d_a_payload(
        records=[_strong_tail_record("RAVEUSDT", gain=0.50)]
    )
    export_dir = tmp_path / "exports" / "20260101"
    export_dir.mkdir(parents=True)
    events_path = export_dir / "events.jsonl"
    events_path.write_text(
        json.dumps(
            {
                "event_id": "deadbeef",
                "timestamp": _ms(60),
                "event_type": runner.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
                "source_module": "app.adaptive.historical_mover_coverage_backfill",
                "symbol": None,
                "position_id": None,
                "order_id": None,
                "payload": payload,
                "created_at": _ms(60),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "out"
    result = runner.run_evidence_pipeline(
        coverage_payload=None,
        export_dir=tmp_path / "exports",
        events_db=None,
        historical_store_dir=None,
        price_paths_json=None,
        output_dir=output_dir,
        reference_window="60d",
    )
    assert result.status == runner.EVIDENCE_GENERATED_STATUS
    assert result.evaluated_count == 1


def test_runner_payload_never_contains_forbidden_keys(
    tmp_path: Path,
) -> None:
    """The runner's emitted artefacts never carry trade-authority
    keys (buy / sell / direction / position_size / leverage / ...)."""

    payload = _build_d_a_payload(
        records=[
            _strong_tail_record("RAVEUSDT", gain=0.60),
            _captured_early_record(
                "EARLYUSDT", first_seen_time_ms=_ms(1, hour=2)
            ),
        ]
    )
    payload_path = tmp_path / "d_a_payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    output_dir = tmp_path / "out"
    result = runner.run_evidence_pipeline(
        coverage_payload=payload_path,
        export_dir=None,
        events_db=None,
        historical_store_dir=None,
        price_paths_json=None,
        output_dir=output_dir,
        reference_window="60d",
    )

    def _walk(node: object, path: str = "<root>") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_str = str(key)
                assert key_str not in POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS, (
                    f"forbidden key {key_str!r} found at {path}"
                )
                _walk(value, f"{path}.{key_str}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                _walk(item, f"{path}[{index}]")

    full = json.loads(
        result.output_report_path.read_text(encoding="utf-8")
    )
    _walk(full)

    for raw_line in result.output_events_path.read_text(
        encoding="utf-8"
    ).splitlines():
        if not raw_line.strip():
            continue
        _walk(json.loads(raw_line))


def test_runner_module_does_not_import_forbidden_modules() -> None:
    """The runner module MUST NOT import Risk / Execution / Exchange
    private / LLM / Telegram modules."""

    runner_path = (
        PROJECT_ROOT
        / "scripts"
        / "run_post_discovery_outcome_evidence.py"
    )
    source = runner_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges.binance",
        "app.exchanges.binance_public_ws",
        "app.llm",
        "app.telegram",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    assert not alias.name.startswith(prefix), (
                        f"runner imports forbidden module {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in forbidden_prefixes:
                assert not module.startswith(prefix), (
                    f"runner imports forbidden module {module!r}"
                )


def test_runner_main_returns_nonzero_on_insufficient_evidence(
    tmp_path: Path,
) -> None:
    """The CLI entry returns exit code 2 when no D-A evidence is
    reachable, so a downstream caller can refuse to mark ACCEPTED."""

    output_dir = tmp_path / "out"
    rc = runner.main(
        [
            "--output-dir",
            str(output_dir),
            "--reference-window",
            "60d",
        ]
    )
    assert rc == 2
    assert (output_dir / "post_discovery_outcome_report.json").is_file()
