"""Phase 11C.1C-C-B-B-B-E-D - Block C Integrated Checkpoint v0
unit tests.

Paper / report / evidence ONLY. None of these tests authorise a
real trade or modify any runtime knob.

Test plan (the brief's ten numbered checks):

  1. ``no input -> INSUFFICIENT_EVIDENCE``
  2. ``partial replay/reflection/evidence -> PARTIAL_EVIDENCE``
  3. ``valid replay/reflection/evidence -> EVIDENCE_GENERATED``
  4. ``next_allowed_phase`` is correct for every status.
  5. ``phase_12_forbidden=true`` on every payload.
  6. ``auto_tuning_allowed=false`` on every payload.
  7. forbidden trade-authority / runtime-tuning fields absent.
  8. The runner module never imports
     ``app.risk`` / ``app.execution`` / ``app.exchanges`` /
     ``app.llm`` / ``app.telegram``.
  9. The evidence-contract degraded-claim count is reported
     correctly.
  10. The output is deterministic across two runs over identical
      input (modulo the ``generated_at_utc`` stamp).
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

from scripts import run_block_c_integrated_checkpoint as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            fh.write("\n")


def _make_event_row(
    event_type: str,
    *,
    event_id: str,
    timestamp: int = 1_768_000_000_000,
    symbol: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type,
        "source_module": "block_c_test_fixture",
        "timestamp": timestamp,
        "payload": payload or {},
    }
    if symbol is not None:
        row["symbol"] = symbol
    return row


def _write_block_b_report(
    path: Path,
    *,
    status: str = "EVIDENCE_GENERATED",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": (
            "phase_11c_1c_c_b_b_b_d_e.block_b_integrated_evidence_checkpoint.v1"
        ),
        "source_phase": (
            "phase_11c_1c_c_b_b_b_d_e_block_b_integrated_evidence_checkpoint_v0"
        ),
        "status": status,
        "reference_window": "60d",
        "phase_12_forbidden": True,
        "auto_tuning_allowed": False,
        "evaluated_count": 300,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_full_event_stream(exports_dir: Path) -> None:
    """Write a JSONL event stream covering every replay event group
    so the EVIDENCE_GENERATED scenario can be exercised end-to-end.
    """

    rows: list[dict[str, Any]] = []
    base_ts = 1_768_000_000_000

    # DISCOVERY_TIMELINE: full canonical chain for one opportunity.
    timeline_chain = [
        ("MARKET_REGIME_ASSESSED", {"regime": "TREND_UP"}),
        (
            "CANDIDATE_STAGE_CLASSIFIED",
            {"candidate_stage": "STAGE_2", "opportunity_id": "opp1"},
        ),
        (
            "OPPORTUNITY_SCORED",
            {"opportunity_id": "opp1", "opportunity_score": 0.75},
        ),
        (
            "STRATEGY_MODE_SELECTED",
            {"opportunity_id": "opp1", "strategy_mode": "MOMENTUM"},
        ),
        (
            "CLUSTER_CONTEXT_ATTACHED",
            {"opportunity_id": "opp1", "cluster_id": "C1"},
        ),
        (
            "LABEL_QUEUE_ENQUEUED",
            {"opportunity_id": "opp1", "windows": ["1h", "4h"]},
        ),
    ]
    for i, (et, payload) in enumerate(timeline_chain):
        payload.setdefault("symbol", "BTCUSDT")
        rows.append(
            _make_event_row(
                et,
                event_id=f"timeline_{i}",
                timestamp=base_ts + i,
                symbol="BTCUSDT",
                payload=payload,
            )
        )

    # CANDIDATE_LIFECYCLE.
    rows.append(
        _make_event_row(
            "LABEL_TRACKING_STARTED",
            event_id="lifecycle_started",
            timestamp=base_ts + 100,
            symbol="BTCUSDT",
            payload={
                "opportunity_id": "opp1",
                "tracking_id": "track1",
                "symbol": "BTCUSDT",
            },
        )
    )
    rows.append(
        _make_event_row(
            "LABEL_WINDOW_UPDATED",
            event_id="lifecycle_updated",
            timestamp=base_ts + 110,
            symbol="BTCUSDT",
            payload={
                "opportunity_id": "opp1",
                "tracking_id": "track1",
                "window_name": "1h",
            },
        )
    )
    rows.append(
        _make_event_row(
            "LABEL_WINDOW_COMPLETED",
            event_id="lifecycle_completed",
            timestamp=base_ts + 120,
            symbol="BTCUSDT",
            payload={
                "opportunity_id": "opp1",
                "tracking_id": "track1",
                "window_name": "1h",
                "tail_label": "USABLE_UPSIDE",
            },
        )
    )

    # TAIL_OUTCOME.
    rows.append(
        _make_event_row(
            "TAIL_LABEL_ASSIGNED",
            event_id="tail_assigned",
            timestamp=base_ts + 130,
            symbol="BTCUSDT",
            payload={
                "opportunity_id": "opp1",
                "symbol": "BTCUSDT",
                "window_name": "1h",
                "tail_label": "USABLE_UPSIDE",
                "mfe_pct": 4.2,
                "mae_pct": -1.0,
            },
        )
    )
    rows.append(
        _make_event_row(
            "MISSED_TAIL_DETECTED",
            event_id="missed_tail",
            timestamp=base_ts + 131,
            symbol="ETHUSDT",
            payload={"opportunity_id": "opp2", "symbol": "ETHUSDT"},
        )
    )
    rows.append(
        _make_event_row(
            "FAKE_BREAKOUT_DETECTED",
            event_id="fake_breakout",
            timestamp=base_ts + 132,
            symbol="ETHUSDT",
            payload={"opportunity_id": "opp2", "symbol": "ETHUSDT"},
        )
    )

    # MOVER_COVERAGE.
    rows.append(
        _make_event_row(
            "HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED",
            event_id="mover_backfill",
            timestamp=base_ts + 200,
            payload={
                "schema_version": (
                    "phase_11c_1c_c_b_b_b_d_a"
                    ".historical_mover_coverage_backfill.v1"
                ),
                "backfill_status": "READY",
                "reference_window_days": 60,
                "top_mover_count": 1,
            },
        )
    )
    rows.append(
        _make_event_row(
            "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED",
            event_id="mover_record",
            timestamp=base_ts + 201,
            symbol="RAVEUSDT",
            payload={
                "symbol": "RAVEUSDT",
                "audit_status": "missed",
                "rank": 1,
            },
        )
    )
    rows.append(
        _make_event_row(
            "MOVER_CAPTURE_PATH_AUDITED",
            event_id="mover_capture",
            timestamp=base_ts + 202,
            symbol="RAVEUSDT",
            payload={"symbol": "RAVEUSDT", "audit_status": "missed"},
        )
    )

    # POST_DISCOVERY_OUTCOME.
    rows.append(
        _make_event_row(
            "POST_DISCOVERY_OUTCOME_EVALUATED",
            event_id="post_discovery_evaluated",
            timestamp=base_ts + 300,
            symbol="BTCUSDT",
            payload={
                "symbol": "BTCUSDT",
                "record": {
                    "symbol": "BTCUSDT",
                    "outcome_label": "USABLE_UPSIDE",
                    "detection_timing_label": "EARLY",
                },
            },
        )
    )
    rows.append(
        _make_event_row(
            "POST_DISCOVERY_OUTCOME_REPORT_GENERATED",
            event_id="post_discovery_report",
            timestamp=base_ts + 301,
            payload={"reference_window": "60d", "evaluated_count": 1},
        )
    )

    # REJECT_ATTRIBUTION.
    rows.append(
        _make_event_row(
            "REJECT_TO_OUTCOME_CASE_ATTRIBUTED",
            event_id="reject_case",
            timestamp=base_ts + 400,
            symbol="LINKUSDT",
            payload={
                "symbol": "LINKUSDT",
                "verdict": "CORRECT_PROTECTIVE_REJECT",
                "primary_reason": "LIQUIDITY_TOO_THIN",
            },
        )
    )
    rows.append(
        _make_event_row(
            "REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED",
            event_id="reject_attribution_report",
            timestamp=base_ts + 401,
            payload={"reference_window": "60d"},
        )
    )

    # SEVERE_MISS.
    rows.append(
        _make_event_row(
            "SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED",
            event_id="severe_root",
            timestamp=base_ts + 500,
            symbol="STOUSDT",
            payload={
                "symbol": "STOUSDT",
                "root_cause": "DATA_GAP",
                "severity": "high",
            },
        )
    )
    rows.append(
        _make_event_row(
            "SEVERE_MISSED_TAIL_TRIAGE_GENERATED",
            event_id="severe_triage",
            timestamp=base_ts + 501,
            payload={"reference_window": "60d"},
        )
    )

    # DISCOVERY_QUALITY.
    rows.append(
        _make_event_row(
            "DISCOVERY_QUALITY_BUCKET_EVALUATED",
            event_id="quality_bucket",
            timestamp=base_ts + 600,
            payload={
                "quality_bucket": "ADEQUATE_FOR_PAPER",
                "capture_recall_rate": 0.5,
            },
        )
    )
    rows.append(
        _make_event_row(
            "DISCOVERY_QUALITY_SCORECARD_GENERATED",
            event_id="quality_scorecard",
            timestamp=base_ts + 601,
            payload={"reference_window": "60d"},
        )
    )

    # STRATEGY_VALIDATION.
    rows.append(
        _make_event_row(
            "STRATEGY_VALIDATION_SAMPLE_CREATED",
            event_id="sv_sample",
            timestamp=base_ts + 700,
            symbol="BTCUSDT",
            payload={"opportunity_id": "opp1"},
        )
    )

    # PAPER_ALPHA.
    rows.append(
        _make_event_row(
            "PAPER_ALPHA_GATE_EVALUATED",
            event_id="paper_alpha_gate",
            timestamp=base_ts + 800,
            payload={"gate": "v0"},
        )
    )

    # REGIME_CLUSTER.
    rows.append(
        _make_event_row(
            "REGIME_CLUSTER_EVIDENCE_PACK_GENERATED",
            event_id="regime_cluster",
            timestamp=base_ts + 900,
            payload={"reference_window": "60d"},
        )
    )

    _write_jsonl(exports_dir / "events.jsonl", rows)


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


# ---------------------------------------------------------------------------
# 1. INSUFFICIENT_EVIDENCE
# ---------------------------------------------------------------------------
def test_no_input_yields_insufficient_evidence(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_checkpoint(
        reports_dir=tmp_path / "reports",
        exports_dir=tmp_path / "exports",
        block_b_dir=tmp_path / "block_b",
        output_dir=output_dir,
        reference_window="60d",
    )
    assert result.status == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert result.next_allowed_phase == runner.NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE
    payload = result.payload
    assert payload["status"] == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert payload["replay_status"] == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    assert (
        payload["reflection_status"]
        == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    )
    assert (
        payload["evidence_contract_status"]
        == runner.COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    )
    assert payload["replay_case_count"] == 0
    assert payload["reflection_case_count"] == 0
    # The evidence contract still emits at least the
    # ``replay_layer_overall`` and ``block_b`` claims so the operator
    # has a record of what was attempted.
    assert payload["evidence_claim_count"] >= 2
    assert payload["accepted_claim_count"] == 0
    assert payload["degraded_claim_count"] >= 1
    assert payload["phase_12_forbidden"] is True
    assert payload["auto_tuning_allowed"] is False
    assert "block_b_integrated_evidence_report_missing" in payload[
        "known_blockers"
    ]
    assert result.output_report_path.is_file()
    assert result.output_summary_path.is_file()


# ---------------------------------------------------------------------------
# 2. PARTIAL_EVIDENCE
# ---------------------------------------------------------------------------
def test_partial_replay_reflection_evidence_yields_partial(
    tmp_path: Path,
) -> None:
    """Adaptive events are present and the replay + reflection layers
    produce records, but the Block B report is missing -> the
    ``block_b_integrated_evidence_report_missing`` blocker forces
    the run to PARTIAL_EVIDENCE.
    """

    exports_dir = tmp_path / "exports"
    rows = [
        _make_event_row(
            "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED",
            event_id="mover_record_1",
            timestamp=1_768_000_000_000,
            symbol="RAVEUSDT",
            payload={
                "symbol": "RAVEUSDT",
                "audit_status": "missed",
                "rank": 1,
            },
        ),
        _make_event_row(
            "POST_DISCOVERY_OUTCOME_EVALUATED",
            event_id="post_discovery_1",
            timestamp=1_768_000_000_010,
            symbol="BTCUSDT",
            payload={
                "symbol": "BTCUSDT",
                "record": {
                    "symbol": "BTCUSDT",
                    "outcome_label": "USABLE_UPSIDE",
                    "detection_timing_label": "EARLY",
                },
            },
        ),
    ]
    _write_jsonl(exports_dir / "events.jsonl", rows)

    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=tmp_path / "missing_block_b",
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert result.status == runner.PARTIAL_EVIDENCE_STATUS
    assert (
        result.next_allowed_phase
        == runner.NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP
    )
    payload = result.payload
    assert payload["replay_status"] == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    assert (
        payload["reflection_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert (
        payload["evidence_contract_status"]
        == runner.COMPONENT_STATUS_PARTIAL_EVIDENCE
    )
    assert payload["replay_case_count"] >= 2
    assert payload["reflection_case_count"] >= 2
    assert payload["accepted_claim_count"] >= 1
    assert payload["degraded_claim_count"] >= 1
    assert (
        "block_b_integrated_evidence_report_missing"
        in payload["known_blockers"]
    )


# ---------------------------------------------------------------------------
# 3. EVIDENCE_GENERATED
# ---------------------------------------------------------------------------
def test_valid_replay_reflection_evidence_yields_evidence_generated(
    tmp_path: Path,
) -> None:
    exports_dir = tmp_path / "exports"
    block_b_dir = tmp_path / "block_b"
    _write_full_event_stream(exports_dir)
    _write_block_b_report(
        block_b_dir / "block_b_integrated_evidence_report.json",
        status="EVIDENCE_GENERATED",
    )

    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=block_b_dir,
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert result.status == runner.EVIDENCE_GENERATED_STATUS
    assert (
        result.next_allowed_phase
        == runner.NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP
    )
    payload = result.payload
    assert payload["replay_status"] == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    assert (
        payload["reflection_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert (
        payload["evidence_contract_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert payload["replay_case_count"] >= 1
    assert payload["reflection_case_count"] >= 1
    assert payload["accepted_claim_count"] == payload["evidence_claim_count"]
    assert payload["degraded_claim_count"] == 0
    assert payload["rejected_claim_count"] == 0
    assert payload["missing_evidence_count"] == 0
    assert payload["invalid_evidence_count"] == 0
    assert payload["known_blockers"] == []


# ---------------------------------------------------------------------------
# 4. next_allowed_phase mapping
# ---------------------------------------------------------------------------
def test_next_allowed_phase_mapping() -> None:
    assert (
        runner._next_allowed_phase(runner.EVIDENCE_GENERATED_STATUS)
        == runner.NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP
    )
    assert (
        runner._next_allowed_phase(runner.PARTIAL_EVIDENCE_STATUS)
        == runner.NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP
    )
    assert (
        runner._next_allowed_phase(runner.INSUFFICIENT_EVIDENCE_STATUS)
        == runner.NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE
    )

    # Defensive: the next-allowed phase MUST NEVER reference Phase 12
    # nor any "live trading" / "trading approved" wording.
    for phase_name in (
        runner.NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP,
        runner.NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE,
    ):
        lower = phase_name.lower()
        assert "phase 12" not in lower
        assert "live" not in lower
        assert "trading-approved" not in lower
        assert "trading_approved" not in lower


# ---------------------------------------------------------------------------
# 5. phase_12_forbidden=true on every payload
# ---------------------------------------------------------------------------
def test_phase_12_forbidden_true_on_every_payload(tmp_path: Path) -> None:
    # Insufficient run.
    r1 = runner.run_checkpoint(
        reports_dir=tmp_path / "a" / "reports",
        exports_dir=tmp_path / "a" / "exports",
        block_b_dir=tmp_path / "a" / "block_b",
        output_dir=tmp_path / "a" / "out",
        reference_window="60d",
    )
    assert r1.payload["phase_12_forbidden"] is True

    # Evidence-generated run.
    exports_dir = tmp_path / "b" / "exports"
    block_b_dir = tmp_path / "b" / "block_b"
    _write_full_event_stream(exports_dir)
    _write_block_b_report(
        block_b_dir / "block_b_integrated_evidence_report.json"
    )
    r2 = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=block_b_dir,
        output_dir=tmp_path / "b" / "out",
        reference_window="60d",
    )
    assert r2.payload["phase_12_forbidden"] is True
    on_disk = json.loads(r2.output_report_path.read_text(encoding="utf-8"))
    assert on_disk["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 6. auto_tuning_allowed=false on every payload
# ---------------------------------------------------------------------------
def test_auto_tuning_allowed_false_on_every_payload(tmp_path: Path) -> None:
    r1 = runner.run_checkpoint(
        reports_dir=tmp_path / "a" / "reports",
        exports_dir=tmp_path / "a" / "exports",
        block_b_dir=tmp_path / "a" / "block_b",
        output_dir=tmp_path / "a" / "out",
        reference_window="60d",
    )
    assert r1.payload["auto_tuning_allowed"] is False

    exports_dir = tmp_path / "b" / "exports"
    block_b_dir = tmp_path / "b" / "block_b"
    _write_full_event_stream(exports_dir)
    _write_block_b_report(
        block_b_dir / "block_b_integrated_evidence_report.json"
    )
    r2 = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=block_b_dir,
        output_dir=tmp_path / "b" / "out",
        reference_window="60d",
    )
    assert r2.payload["auto_tuning_allowed"] is False
    # The reflection summary embedded in the payload also pins the flag.
    assert (
        r2.payload["reflection_summary"]["auto_tuning_allowed"] is False
    )


# ---------------------------------------------------------------------------
# 7. Forbidden trade-authority / runtime-tuning fields absent
# ---------------------------------------------------------------------------
def test_no_forbidden_keys_in_emitted_payload(tmp_path: Path) -> None:
    exports_dir = tmp_path / "exports"
    block_b_dir = tmp_path / "block_b"
    _write_full_event_stream(exports_dir)
    _write_block_b_report(
        block_b_dir / "block_b_integrated_evidence_report.json"
    )
    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=block_b_dir,
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    keys = set(_walk_keys(result.payload))
    forbidden = keys & runner._FORBIDDEN_BLOCK_C_PAYLOAD_KEYS
    assert forbidden == set(), f"forbidden keys leaked: {sorted(forbidden)}"
    on_disk = json.loads(result.output_report_path.read_text(encoding="utf-8"))
    assert (
        set(_walk_keys(on_disk)) & runner._FORBIDDEN_BLOCK_C_PAYLOAD_KEYS
        == set()
    )


# ---------------------------------------------------------------------------
# 8. No banned imports
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


def test_runner_module_does_not_import_banned_modules_textual() -> None:
    """Defensive: even string occurrences of forbidden module paths
    should not appear as actual import statements (cheap belt-and-
    suspenders alongside the AST check).
    """

    runner_path = Path(runner.__file__)
    source = runner_path.read_text(encoding="utf-8")
    for banned_prefix in _BANNED_IMPORT_PREFIXES:
        assert (
            f"import {banned_prefix}" not in source
        ), f"runner contains banned 'import {banned_prefix}' statement"
        assert (
            f"from {banned_prefix}" not in source
        ), f"runner contains banned 'from {banned_prefix}' statement"


# ---------------------------------------------------------------------------
# 9. Evidence-contract degraded-claim count is correct
# ---------------------------------------------------------------------------
def test_evidence_contract_degraded_claim_count_reported_correctly(
    tmp_path: Path,
) -> None:
    # Scenario A: no input -> at least the replay_layer_overall +
    # block_b claims are degraded.
    r_empty = runner.run_checkpoint(
        reports_dir=tmp_path / "a",
        exports_dir=tmp_path / "a",
        block_b_dir=tmp_path / "a_block_b",
        output_dir=tmp_path / "a_out",
        reference_window="60d",
    )
    assert r_empty.payload["accepted_claim_count"] == 0
    assert r_empty.payload["degraded_claim_count"] >= 2

    # Scenario B: events present but block_b missing -> block_b
    # claim is the only degraded one; all replay / reflection
    # claims are accepted.
    exports_dir = tmp_path / "b" / "exports"
    rows = [
        _make_event_row(
            "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED",
            event_id="mover_b1",
            timestamp=1_768_000_000_000,
            symbol="RAVEUSDT",
            payload={"symbol": "RAVEUSDT", "audit_status": "missed"},
        ),
        _make_event_row(
            "POST_DISCOVERY_OUTCOME_EVALUATED",
            event_id="post_b1",
            timestamp=1_768_000_000_010,
            symbol="BTCUSDT",
            payload={
                "symbol": "BTCUSDT",
                "record": {
                    "symbol": "BTCUSDT",
                    "outcome_label": "USABLE_UPSIDE",
                    "detection_timing_label": "EARLY",
                },
            },
        ),
    ]
    _write_jsonl(exports_dir / "events.jsonl", rows)
    r_partial = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=tmp_path / "b_block_b",  # missing
        output_dir=tmp_path / "b" / "out",
        reference_window="60d",
    )
    assert r_partial.payload["degraded_claim_count"] == 1
    assert r_partial.payload["rejected_claim_count"] == 0

    # Scenario C: events + block_b -> zero degraded.
    exports_c = tmp_path / "c" / "exports"
    block_b_c = tmp_path / "c" / "block_b"
    _write_full_event_stream(exports_c)
    _write_block_b_report(
        block_b_c / "block_b_integrated_evidence_report.json"
    )
    r_full = runner.run_checkpoint(
        reports_dir=exports_c,
        exports_dir=exports_c,
        block_b_dir=block_b_c,
        output_dir=tmp_path / "c" / "out",
        reference_window="60d",
    )
    assert r_full.payload["degraded_claim_count"] == 0


# ---------------------------------------------------------------------------
# 10. Deterministic output across two runs
# ---------------------------------------------------------------------------
def test_output_is_deterministic_modulo_generated_at_utc(
    tmp_path: Path,
) -> None:
    exports_dir = tmp_path / "exports"
    block_b_dir = tmp_path / "block_b"
    _write_full_event_stream(exports_dir)
    _write_block_b_report(
        block_b_dir / "block_b_integrated_evidence_report.json"
    )

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    r1 = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=block_b_dir,
        output_dir=out1,
        reference_window="60d",
    )
    r2 = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=block_b_dir,
        output_dir=out2,
        reference_window="60d",
    )
    p1 = dict(r1.payload)
    p2 = dict(r2.payload)
    p1.pop("generated_at_utc", None)
    p2.pop("generated_at_utc", None)
    assert (
        json.dumps(p1, sort_keys=True)
        == json.dumps(p2, sort_keys=True)
    ), "Block C report must be deterministic across runs over identical input"


# ---------------------------------------------------------------------------
# Extra: output paths and CLI exit codes
# ---------------------------------------------------------------------------
def test_outputs_written_to_expected_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_checkpoint(
        reports_dir=tmp_path / "reports",
        exports_dir=tmp_path / "exports",
        block_b_dir=tmp_path / "block_b",
        output_dir=output_dir,
        reference_window="60d",
    )
    assert (
        result.output_report_path
        == output_dir / "block_c_integrated_checkpoint_report.json"
    )
    assert (
        result.output_summary_path
        == output_dir / "block_c_integrated_checkpoint_report.md"
    )
    assert result.output_report_path.is_file()
    assert result.output_summary_path.is_file()
    md = result.output_summary_path.read_text(encoding="utf-8")
    assert "Block C Integrated Checkpoint" in md
    assert "Phase 12 remains FORBIDDEN" in md


def test_main_exit_code_insufficient_evidence(
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
            "--block-b-dir",
            str(tmp_path / "block_b"),
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
    assert (
        parsed["next_allowed_phase"]
        == runner.NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE
    )


def test_main_exit_code_evidence_generated(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exports_dir = tmp_path / "exports"
    block_b_dir = tmp_path / "block_b"
    _write_full_event_stream(exports_dir)
    _write_block_b_report(
        block_b_dir / "block_b_integrated_evidence_report.json"
    )
    rc = runner.main(
        [
            "--reports-dir",
            str(exports_dir),
            "--exports-dir",
            str(exports_dir),
            "--block-b-dir",
            str(block_b_dir),
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
    assert (
        parsed["next_allowed_phase"]
        == runner.NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP
    )


# ---------------------------------------------------------------------------
# Extra: supported / unsupported event groups surface
# ---------------------------------------------------------------------------
def test_supported_and_unsupported_event_groups_surface(
    tmp_path: Path,
) -> None:
    exports_dir = tmp_path / "exports"
    rows = [
        _make_event_row(
            "POST_DISCOVERY_OUTCOME_EVALUATED",
            event_id="post_only",
            timestamp=1_768_000_000_010,
            symbol="BTCUSDT",
            payload={
                "symbol": "BTCUSDT",
                "record": {
                    "symbol": "BTCUSDT",
                    "outcome_label": "USABLE_UPSIDE",
                    "detection_timing_label": "EARLY",
                },
            },
        ),
    ]
    _write_jsonl(exports_dir / "events.jsonl", rows)

    result = runner.run_checkpoint(
        reports_dir=exports_dir,
        exports_dir=exports_dir,
        block_b_dir=tmp_path / "block_b",
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert "POST_DISCOVERY_OUTCOME" in result.payload["supported_event_groups"]
    # Many groups are not covered by this minimal fixture.
    assert "DISCOVERY_TIMELINE" in result.payload["unsupported_event_groups"]
    assert (
        "replay_event_group_coverage_partial" in result.payload["known_gaps"]
    )
