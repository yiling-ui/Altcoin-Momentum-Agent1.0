"""Phase AI-CHECKPOINT - AI Integrated Checkpoint v0 unit tests.

Paper / report / evidence ONLY. None of these tests authorise a
real trade or modify any runtime knob. None of them open the
network, call DeepSeek, or read a private exchange API.

Test plan (the brief's fifteen numbered checks):

  1.  no input -> INSUFFICIENT_EVIDENCE
  2.  partial / fallback input -> PARTIAL_EVIDENCE
  3.  valid AI-1..AI-6 chain input -> EVIDENCE_GENERATED
  4.  ``next_allowed_phase`` is correct for every status (and
      never references Phase 12 / "live" wording)
  5.  ``phase_12_forbidden=True`` on every payload
  6.  ``auto_tuning_allowed=False`` on every payload
  7.  ``trade_authority=False`` on every payload
  8.  ``ai_output_can_be_truth=False`` on every payload
  9.  ``ai_output_can_be_training_label=False`` on every payload
  10. ``ai_output_can_be_tail_label=False`` on every payload
  11. ``ai_output_can_be_strategy_sample=False`` on every payload
  12. forbidden trade-authority / runtime-tuning fields absent at
      every nesting depth
  13. The runner module never imports ``app.risk`` /
      ``app.execution`` / ``app.exchanges`` / ``app.telegram``
  14. No live LLM / DeepSeek network call required - the runner
      module never imports any HTTP / network library either
  15. Output is deterministic across two runs over identical
      input (modulo ``generated_at_utc``)
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

from scripts import run_ai_integrated_checkpoint as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
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


def _write_evidence_bundle(
    path: Path, *, bundle_id: str = "b_test"
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "v0",
        "source_phase": "phase_ai_1",
        "source_module": "ai_evidence_bundle_builder",
        "bundle_id": bundle_id,
        "created_at_utc": "2026-05-28T00:00:00Z",
        "task_type": "MARKET_INTELLIGENCE_SUMMARY",
        "build_status": "SUCCESS",
        "phase_context": {"phase": "phase_ai_checkpoint"},
        "reference_window": "60d",
        "market_facts": [
            {
                "fact_id": "f1",
                "fact_type": "POST_DISCOVERY_OUTCOME",
                "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:e1"],
                "source_report": "post_discovery_outcome",
                "status": "ACCEPTED",
                "degradation_reason": None,
                "content": {"symbol": "BTCUSDT"},
            }
        ],
        "system_behavior_facts": [],
        "outcome_facts": [],
        "replay_facts": [],
        "reflection_facts": [],
        "evidence_contract_facts": [],
        "degraded_facts": [],
        "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:e1"],
        "source_reports": ["post_discovery_outcome"],
        "forbidden_fields": [],
        "lookahead_policy": {
            "frozen_evidence_only": True,
            "no_future_market_data": True,
            "no_training_from_ai_output": True,
            "no_runtime_feedback": True,
            "post_hoc_analysis_only_when_window_closed": True,
        },
        "consumer_contract": {
            "allowed": ["human_operator"],
            "forbidden": ["RiskEngine", "ExecutionFSM"],
        },
        "warnings": [],
        "accepted_fact_count": 1,
        "degraded_fact_count": 0,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_sandbox_output(
    path: Path,
    *,
    bundle_id: str = "b_test",
    citation: str = "SUPPORTED_INTELLIGENCE",
    rc_status: str = "SUPPORTED",
    extra_unsupported: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    claims: list[dict[str, Any]] = [
        {
            "claim_id": "c1",
            "claim_type": "MARKET_OBSERVATION",
            "claim_text": "BTCUSDT moved up over the window",
            "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:e1"],
            "truth_layer_fields_used": ["symbol", "outcome_label"],
            "citation_authority_level": citation,
            "reality_check_status": rc_status,
            "reality_check_authority_level": citation,
            "confidence_raw": 0.7,
            "confidence_reality_checked": 0.6,
            "warnings": [],
        }
    ]
    for i in range(extra_unsupported):
        claims.append(
            {
                "claim_id": f"unsup_{i}",
                "claim_type": "MARKET_OBSERVATION",
                "claim_text": "claim with no evidence",
                "evidence_refs": [],
                "truth_layer_fields_used": [],
                "citation_authority_level": "DEGRADED_NO_EVIDENCE",
                "reality_check_status": "INSUFFICIENT",
                "reality_check_authority_level": (
                    "DEGRADED_NO_EVIDENCE"
                ),
                "confidence_raw": None,
                "confidence_reality_checked": None,
                "warnings": ["no evidence"],
            }
        )

    payload: dict[str, Any] = {
        "schema_version": "v0",
        "source_phase": "phase_ai_4",
        "source_module": "ai_intelligence_output",
        "bundle_id": bundle_id,
        "task_type": "MARKET_INTELLIGENCE_SUMMARY",
        "summary": "deterministic test sandbox output",
        "claims": claims,
        "contradictions": [],
        "unsupported_claims": [],
        "risk_tags": [],
        "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:e1"],
        "reality_check_status": rc_status,
        "authority_level": "SUPPORTED_INTELLIGENCE",
        "status": "GENERATED",
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": [],
        "degraded_reasons": [],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_operator_briefing_dir(
    operator_dir: Path,
    *,
    bundle_id: str = "b_test",
    ai_output_id: str = "intel_test",
) -> None:
    operator_dir.mkdir(parents=True, exist_ok=True)
    briefing: dict[str, Any] = {
        "schema_version": "v0",
        "source_phase": "phase_ai_5",
        "source_module": "ai_operator_briefing",
        "briefing_id": "br_test",
        "created_at_utc": "2026-05-28T00:00:00Z",
        "reference_window": "60d",
        "source_bundle_id": bundle_id,
        "source_ai_output_id": ai_output_id,
        "source_block_c_status": "EVIDENCE_GENERATED",
        "source_report_paths": [],
        "sections": [],
        "key_findings": [],
        "unsupported_claims": [],
        "contradictions": [],
        "data_gaps": [],
        "operator_review_items": [],
        "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:e1"],
        "notable_symbols": ["BTCUSDT"],
        "risk_tags": [],
        "authority_level": "COMMENTARY_SUBSTRATE",
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": [],
        "consumer_contract": {"allowed": ["human_operator"]},
    }
    compression: dict[str, Any] = {
        "schema_version": "v0",
        "source_phase": "phase_ai_5",
        "source_module": "ai_evidence_compression_report",
        "report_id": "cm_test",
        "created_at_utc": "2026-05-28T00:00:00Z",
        "reference_window": "60d",
        "source_bundle_id": bundle_id,
        "source_ai_output_id": ai_output_id,
        "summary": "deterministic test compression report",
        "compressed_claims": [],
        "supported_claims": ["c1"],
        "degraded_claims": [],
        "rejected_claims": [],
        "contradictions": [],
        "unsupported_claims": [],
        "reality_check_summary": {},
        "evidence_quality_summary": {},
        "data_gap_summary": {},
        "notable_symbols": ["BTCUSDT"],
        "risk_tags": [],
        "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:e1"],
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": [],
    }
    (operator_dir / "operator_briefing.json").write_text(
        json.dumps(briefing, indent=2), encoding="utf-8"
    )
    (operator_dir / "evidence_compression_report.json").write_text(
        json.dumps(compression, indent=2), encoding="utf-8"
    )


def _write_block_c_report(
    path: Path, *, status: str = "EVIDENCE_GENERATED"
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": (
            "phase_11c_1c_c_b_b_b_e_d.block_c_integrated_checkpoint.v1"
        ),
        "source_phase": (
            "phase_11c_1c_c_b_b_b_e_d_block_c_integrated_checkpoint_v0"
        ),
        "status": status,
        "reference_window": "60d",
        "phase_12_forbidden": True,
        "auto_tuning_allowed": False,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _full_chain_paths(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    """Lay down a complete AI-1..AI-5 + Block C input set."""

    bundle_path = tmp_path / "bundle.json"
    sandbox_path = tmp_path / "sandbox.json"
    op_dir = tmp_path / "operator_briefing"
    block_c_path = tmp_path / "block_c.json"
    output_dir = tmp_path / "out"

    _write_evidence_bundle(bundle_path)
    _write_sandbox_output(sandbox_path)
    _write_operator_briefing_dir(op_dir)
    _write_block_c_report(block_c_path)

    return bundle_path, sandbox_path, op_dir, block_c_path, output_dir


# ---------------------------------------------------------------------------
# 1. INSUFFICIENT_EVIDENCE
# ---------------------------------------------------------------------------
def test_no_input_yields_insufficient_evidence(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_checkpoint(
        block_c_report=tmp_path / "missing_block_c.json",
        evidence_bundle=tmp_path / "missing_bundle.json",
        sandbox_output=tmp_path / "missing_sandbox.json",
        operator_briefing_dir=tmp_path / "missing_dir",
        output_dir=output_dir,
        reference_window="60d",
    )
    assert result.status == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert (
        result.next_allowed_phase
        == runner.NEXT_PHASE_NEEDS_AI_OPERATOR_EVIDENCE
    )
    payload = result.payload
    assert payload["status"] == runner.INSUFFICIENT_EVIDENCE_STATUS
    # All four stage payloads were synthesised from the fallback
    # fixture, but the per-stage status surfaces FALLBACK_FIXTURE
    # (not PRESENT) so the operator can see what was synthetic.
    for stage in (
        "evidence_bundle_status",
        "deepseek_sandbox_status",
        "operator_briefing_status",
        "evidence_compression_status",
    ):
        assert payload[stage] == runner.COMPONENT_STATUS_FALLBACK_FIXTURE
    assert payload["bundle_count"] == 0
    assert payload["ai_claim_count"] == 0
    assert payload["supported_claim_count"] == 0
    assert payload["phase_12_forbidden"] is True
    assert payload["auto_tuning_allowed"] is False
    assert payload["trade_authority"] is False
    assert payload["ai_output_can_be_truth"] is False
    assert payload["ai_output_can_be_training_label"] is False
    assert payload["ai_output_can_be_tail_label"] is False
    assert payload["ai_output_can_be_strategy_sample"] is False
    assert result.output_report_path.is_file()
    assert result.output_summary_path.is_file()


# ---------------------------------------------------------------------------
# 2. PARTIAL_EVIDENCE
# ---------------------------------------------------------------------------
def test_partial_or_fallback_input_yields_partial_evidence(
    tmp_path: Path,
) -> None:
    """Only the AI-1 evidence bundle is on disk; the AI-4 sandbox
    output, AI-5 operator briefing, and Block C report are
    missing. The runner is expected to fill the missing stages
    with deterministic fallback fixtures and report
    PARTIAL_EVIDENCE.
    """

    bundle_path = tmp_path / "bundle.json"
    _write_evidence_bundle(bundle_path)
    result = runner.run_checkpoint(
        block_c_report=tmp_path / "missing_block_c.json",
        evidence_bundle=bundle_path,
        sandbox_output=tmp_path / "missing_sandbox.json",
        operator_briefing_dir=tmp_path / "missing_dir",
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert result.status == runner.PARTIAL_EVIDENCE_STATUS
    assert (
        result.next_allowed_phase
        == runner.NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY_PREP
    )
    payload = result.payload
    assert payload["evidence_bundle_status"] == runner.COMPONENT_STATUS_PRESENT
    assert (
        payload["deepseek_sandbox_status"]
        == runner.COMPONENT_STATUS_FALLBACK_FIXTURE
    )
    assert (
        payload["operator_briefing_status"]
        == runner.COMPONENT_STATUS_FALLBACK_FIXTURE
    )
    assert (
        payload["evidence_compression_status"]
        == runner.COMPONENT_STATUS_FALLBACK_FIXTURE
    )
    # The fallback gaps must be surfaced.
    assert (
        "deepseek_sandbox_fallback_fixture_used"
        in payload["known_gaps"]
    )
    assert (
        "operator_briefing_fallback_fixture_used"
        in payload["known_gaps"]
    )
    assert (
        "evidence_compression_fallback_fixture_used"
        in payload["known_gaps"]
    )
    # No blocker (the bundle is on disk so PARTIAL is the right
    # roll-up).
    assert payload["known_blockers"] == []


# ---------------------------------------------------------------------------
# 3. EVIDENCE_GENERATED
# ---------------------------------------------------------------------------
def test_valid_ai_chain_input_yields_evidence_generated(
    tmp_path: Path,
) -> None:
    bundle_path, sandbox_path, op_dir, block_c_path, output_dir = (
        _full_chain_paths(tmp_path)
    )
    result = runner.run_checkpoint(
        block_c_report=block_c_path,
        evidence_bundle=bundle_path,
        sandbox_output=sandbox_path,
        operator_briefing_dir=op_dir,
        output_dir=output_dir,
        reference_window="60d",
    )
    assert result.status == runner.EVIDENCE_GENERATED_STATUS
    assert (
        result.next_allowed_phase
        == runner.NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY
    )
    payload = result.payload
    for stage in (
        "evidence_bundle_status",
        "deepseek_sandbox_status",
        "operator_briefing_status",
        "evidence_compression_status",
    ):
        assert payload[stage] == runner.COMPONENT_STATUS_PRESENT
    assert (
        payload["citation_contract_status"]
        == runner.COMPONENT_STATUS_PRESENT
    )
    assert (
        payload["reality_check_status"]
        == runner.COMPONENT_STATUS_PRESENT
    )
    assert (
        payload["ai_replay_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert (
        payload["ai_reflection_status"]
        == runner.COMPONENT_STATUS_EVIDENCE_GENERATED
    )
    assert payload["bundle_count"] == 1
    assert payload["ai_claim_count"] >= 1
    assert payload["supported_claim_count"] >= 1
    assert payload["degraded_claim_count"] == 0
    assert payload["rejected_claim_count"] == 0
    assert payload["reality_check_failed_count"] == 0
    assert payload["replay_case_count"] >= 1
    assert payload["reflection_case_count"] >= 1
    assert payload["known_blockers"] == []
    assert payload["known_gaps"] == []


# ---------------------------------------------------------------------------
# 4. next_allowed_phase mapping
# ---------------------------------------------------------------------------
def test_next_allowed_phase_mapping_is_correct() -> None:
    assert (
        runner._next_allowed_phase(runner.EVIDENCE_GENERATED_STATUS)
        == runner.NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY
    )
    assert (
        runner._next_allowed_phase(runner.PARTIAL_EVIDENCE_STATUS)
        == runner.NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY_PREP
    )
    assert (
        runner._next_allowed_phase(runner.INSUFFICIENT_EVIDENCE_STATUS)
        == runner.NEXT_PHASE_NEEDS_AI_OPERATOR_EVIDENCE
    )

    # Defensive: the next-allowed phase MUST NEVER reference Phase
    # 12, "live trading", "trading approved", "live ready", or any
    # equivalent wording.
    for phase_name in (
        runner.NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY,
        runner.NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY_PREP,
        runner.NEXT_PHASE_NEEDS_AI_OPERATOR_EVIDENCE,
    ):
        lower = phase_name.lower()
        assert "phase 12" not in lower
        assert "phase_12" not in lower
        assert "live trading" not in lower
        assert "trading-approved" not in lower
        assert "trading_approved" not in lower
        assert "live ready" not in lower
        assert "live_ready" not in lower


# ---------------------------------------------------------------------------
# Helper: collect every payload across all status tiers.
# ---------------------------------------------------------------------------
def _payloads_across_all_status_tiers(
    tmp_path: Path,
) -> list[dict[str, Any]]:
    """Run the runner once for each status tier and collect the
    emitted payloads (in-memory + on-disk)."""

    out: list[dict[str, Any]] = []

    # INSUFFICIENT_EVIDENCE
    r1 = runner.run_checkpoint(
        block_c_report=tmp_path / "_a_bc.json",
        evidence_bundle=tmp_path / "_a_bundle.json",
        sandbox_output=tmp_path / "_a_sb.json",
        operator_briefing_dir=tmp_path / "_a_dir",
        output_dir=tmp_path / "_a_out",
        reference_window="60d",
    )
    out.append(dict(r1.payload))
    out.append(json.loads(r1.output_report_path.read_text("utf-8")))

    # PARTIAL_EVIDENCE
    bp = tmp_path / "_b_bundle.json"
    _write_evidence_bundle(bp)
    r2 = runner.run_checkpoint(
        block_c_report=tmp_path / "_b_bc.json",
        evidence_bundle=bp,
        sandbox_output=tmp_path / "_b_sb.json",
        operator_briefing_dir=tmp_path / "_b_dir",
        output_dir=tmp_path / "_b_out",
        reference_window="60d",
    )
    out.append(dict(r2.payload))
    out.append(json.loads(r2.output_report_path.read_text("utf-8")))

    # EVIDENCE_GENERATED
    bundle_path, sandbox_path, op_dir, block_c_path, output_dir = (
        _full_chain_paths(tmp_path / "_c")
    )
    r3 = runner.run_checkpoint(
        block_c_report=block_c_path,
        evidence_bundle=bundle_path,
        sandbox_output=sandbox_path,
        operator_briefing_dir=op_dir,
        output_dir=output_dir,
        reference_window="60d",
    )
    out.append(dict(r3.payload))
    out.append(json.loads(r3.output_report_path.read_text("utf-8")))

    return out


# ---------------------------------------------------------------------------
# 5. phase_12_forbidden=True
# ---------------------------------------------------------------------------
def test_phase_12_forbidden_true_on_every_payload(tmp_path: Path) -> None:
    for payload in _payloads_across_all_status_tiers(tmp_path):
        assert payload["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 6. auto_tuning_allowed=False
# ---------------------------------------------------------------------------
def test_auto_tuning_allowed_false_on_every_payload(tmp_path: Path) -> None:
    for payload in _payloads_across_all_status_tiers(tmp_path):
        assert payload["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 7. trade_authority=False
# ---------------------------------------------------------------------------
def test_trade_authority_false_on_every_payload(tmp_path: Path) -> None:
    for payload in _payloads_across_all_status_tiers(tmp_path):
        assert payload["trade_authority"] is False


# ---------------------------------------------------------------------------
# 8. ai_output_can_be_truth=False
# ---------------------------------------------------------------------------
def test_ai_output_can_be_truth_false_on_every_payload(
    tmp_path: Path,
) -> None:
    for payload in _payloads_across_all_status_tiers(tmp_path):
        assert payload["ai_output_can_be_truth"] is False


# ---------------------------------------------------------------------------
# 9. ai_output_can_be_training_label=False
# ---------------------------------------------------------------------------
def test_ai_output_can_be_training_label_false_on_every_payload(
    tmp_path: Path,
) -> None:
    for payload in _payloads_across_all_status_tiers(tmp_path):
        assert payload["ai_output_can_be_training_label"] is False


# ---------------------------------------------------------------------------
# 10. ai_output_can_be_tail_label=False
# ---------------------------------------------------------------------------
def test_ai_output_can_be_tail_label_false_on_every_payload(
    tmp_path: Path,
) -> None:
    for payload in _payloads_across_all_status_tiers(tmp_path):
        assert payload["ai_output_can_be_tail_label"] is False


# ---------------------------------------------------------------------------
# 11. ai_output_can_be_strategy_sample=False
# ---------------------------------------------------------------------------
def test_ai_output_can_be_strategy_sample_false_on_every_payload(
    tmp_path: Path,
) -> None:
    for payload in _payloads_across_all_status_tiers(tmp_path):
        assert payload["ai_output_can_be_strategy_sample"] is False


# ---------------------------------------------------------------------------
# 12. forbidden trade-authority / runtime-tuning fields absent
# ---------------------------------------------------------------------------
def test_no_forbidden_keys_in_emitted_payload(tmp_path: Path) -> None:
    bundle_path, sandbox_path, op_dir, block_c_path, output_dir = (
        _full_chain_paths(tmp_path)
    )
    result = runner.run_checkpoint(
        block_c_report=block_c_path,
        evidence_bundle=bundle_path,
        sandbox_output=sandbox_path,
        operator_briefing_dir=op_dir,
        output_dir=output_dir,
        reference_window="60d",
    )
    keys = set(_walk_keys(result.payload))
    forbidden = keys & runner._FORBIDDEN_AI_CHECKPOINT_PAYLOAD_KEYS
    assert forbidden == set(), (
        f"forbidden keys leaked into payload: {sorted(forbidden)}"
    )
    on_disk = json.loads(
        result.output_report_path.read_text(encoding="utf-8")
    )
    on_disk_forbidden = (
        set(_walk_keys(on_disk))
        & runner._FORBIDDEN_AI_CHECKPOINT_PAYLOAD_KEYS
    )
    assert on_disk_forbidden == set(), (
        f"forbidden keys leaked to disk: {sorted(on_disk_forbidden)}"
    )


def test_runner_refuses_to_emit_forbidden_payload() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        runner._assert_no_forbidden_keys(
            {"buy": True}, context="unit_test"
        )
    with pytest.raises(ValueError, match="forbidden"):
        runner._assert_no_forbidden_keys(
            {"nested": [{"trading_approved": True}]},
            context="unit_test",
        )


# ---------------------------------------------------------------------------
# 13. Banned imports - app.risk / app.execution / app.exchanges /
#     app.telegram
# ---------------------------------------------------------------------------
_BANNED_IMPORT_PREFIXES: tuple[str, ...] = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.telegram",
    # The brief also forbids modifying app.config; the runner
    # does not need it either.
    "app.config",
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
    suspenders alongside the AST check)."""

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
# 14. No live LLM / DeepSeek network call required
# ---------------------------------------------------------------------------
_BANNED_NETWORK_MODULES: tuple[str, ...] = (
    "openai",
    "anthropic",
    "deepseek",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "websocket",
    "websockets",
    "grpc",
    "boto3",
    "socket",
)


def test_runner_module_does_not_import_any_network_library() -> None:
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
                    for p in _BANNED_NETWORK_MODULES
                ):
                    banned.append(name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                module == p or module.startswith(p + ".")
                for p in _BANNED_NETWORK_MODULES
            ):
                banned.append(module)
    assert banned == [], (
        "runner must not import any HTTP / network library; "
        f"observed: {banned}"
    )


def test_runner_does_not_open_a_network_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boot the runner with a monkeypatched ``socket.socket`` that
    raises if called. The runner must complete the
    EVIDENCE_GENERATED case without ever opening a socket.
    """

    import socket as _socket  # noqa: WPS433 - test-local import

    real_socket = _socket.socket

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "runner attempted to open a network socket; "
            "this is forbidden under the AI checkpoint boundary."
        )

    monkeypatch.setattr(_socket, "socket", _refuse)
    try:
        bundle_path, sandbox_path, op_dir, block_c_path, output_dir = (
            _full_chain_paths(tmp_path)
        )
        result = runner.run_checkpoint(
            block_c_report=block_c_path,
            evidence_bundle=bundle_path,
            sandbox_output=sandbox_path,
            operator_briefing_dir=op_dir,
            output_dir=output_dir,
            reference_window="60d",
        )
        assert result.status == runner.EVIDENCE_GENERATED_STATUS
    finally:
        monkeypatch.setattr(_socket, "socket", real_socket)


# ---------------------------------------------------------------------------
# 15. Deterministic output across two runs
# ---------------------------------------------------------------------------
def test_output_is_deterministic_modulo_generated_at_utc(
    tmp_path: Path,
) -> None:
    bundle_path, sandbox_path, op_dir, block_c_path, _ = (
        _full_chain_paths(tmp_path)
    )
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    r1 = runner.run_checkpoint(
        block_c_report=block_c_path,
        evidence_bundle=bundle_path,
        sandbox_output=sandbox_path,
        operator_briefing_dir=op_dir,
        output_dir=out1,
        reference_window="60d",
    )
    r2 = runner.run_checkpoint(
        block_c_report=block_c_path,
        evidence_bundle=bundle_path,
        sandbox_output=sandbox_path,
        operator_briefing_dir=op_dir,
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
    ), (
        "AI integrated checkpoint report must be deterministic "
        "across runs over identical input"
    )


# ---------------------------------------------------------------------------
# Extra: output paths and CLI exit code
# ---------------------------------------------------------------------------
def test_outputs_written_to_expected_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_checkpoint(
        block_c_report=tmp_path / "missing_bc.json",
        evidence_bundle=tmp_path / "missing_bundle.json",
        sandbox_output=tmp_path / "missing_sb.json",
        operator_briefing_dir=tmp_path / "missing_dir",
        output_dir=output_dir,
        reference_window="60d",
    )
    assert (
        result.output_report_path
        == output_dir / "ai_integrated_checkpoint_report.json"
    )
    assert (
        result.output_summary_path
        == output_dir / "ai_integrated_checkpoint_report.md"
    )
    assert result.output_report_path.is_file()
    assert result.output_summary_path.is_file()
    md = result.output_summary_path.read_text(encoding="utf-8")
    assert "AI Integrated Checkpoint" in md
    assert "Phase 12 remains FORBIDDEN" in md


def test_main_exit_code_insufficient_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "out"
    rc = runner.main(
        [
            "--block-c-report",
            str(tmp_path / "missing_bc.json"),
            "--evidence-bundle",
            str(tmp_path / "missing_bundle.json"),
            "--sandbox-output",
            str(tmp_path / "missing_sb.json"),
            "--operator-briefing-dir",
            str(tmp_path / "missing_dir"),
            "--output-dir",
            str(output_dir),
            "--reference-window",
            "60d",
            "--use-fake-provider",
            "true",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == runner.INSUFFICIENT_EVIDENCE_STATUS
    assert (
        parsed["next_allowed_phase"]
        == runner.NEXT_PHASE_NEEDS_AI_OPERATOR_EVIDENCE
    )


def test_main_exit_code_evidence_generated(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_path, sandbox_path, op_dir, block_c_path, output_dir = (
        _full_chain_paths(tmp_path)
    )
    rc = runner.main(
        [
            "--block-c-report",
            str(block_c_path),
            "--evidence-bundle",
            str(bundle_path),
            "--sandbox-output",
            str(sandbox_path),
            "--operator-briefing-dir",
            str(op_dir),
            "--output-dir",
            str(output_dir),
            "--reference-window",
            "60d",
            "--use-fake-provider",
            "true",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == runner.EVIDENCE_GENERATED_STATUS
    assert (
        parsed["next_allowed_phase"]
        == runner.NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY
    )


# ---------------------------------------------------------------------------
# Extra: degraded sandbox claims drag EVIDENCE_GENERATED -> PARTIAL
# ---------------------------------------------------------------------------
def test_degraded_claims_keep_status_at_partial(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    sandbox_path = tmp_path / "sandbox.json"
    op_dir = tmp_path / "operator_briefing"
    block_c_path = tmp_path / "block_c.json"
    _write_evidence_bundle(bundle_path)
    _write_sandbox_output(
        sandbox_path,
        citation="DEGRADED_NO_EVIDENCE",
        rc_status="INSUFFICIENT",
    )
    _write_operator_briefing_dir(op_dir)
    _write_block_c_report(block_c_path)

    result = runner.run_checkpoint(
        block_c_report=block_c_path,
        evidence_bundle=bundle_path,
        sandbox_output=sandbox_path,
        operator_briefing_dir=op_dir,
        output_dir=tmp_path / "out",
        reference_window="60d",
    )
    assert result.status == runner.PARTIAL_EVIDENCE_STATUS
    assert result.payload["degraded_claim_count"] >= 1
    assert result.payload["reality_check_failed_count"] >= 1
    assert "ai_claims_degraded_present" in result.payload["known_gaps"]
    assert (
        "ai_claims_reality_check_failed_present"
        in result.payload["known_gaps"]
    )
