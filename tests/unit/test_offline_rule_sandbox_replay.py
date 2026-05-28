"""Unit tests for Phase 11C / Offline Rule Sandbox Replay v0.

These tests are the safety contract for this phase. If any of them fails,
the module is not safe to merge.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

import pytest

from app.sandbox.offline_rule_sandbox import (
    FORBIDDEN_OUTPUT_FIELDS,
    NEXT_ALLOWED_PHASE,
    PHASE_NAME,
    SAFETY_CONTRACT,
    HypotheticalRuleChange,
    OfflineRuleSandboxEngine,
    OfflineRuleSandboxInput,
    OfflineRuleSandboxReport,
    OfflineRuleSandboxResult,
    OfflineRuleSandboxScenario,
    RecommendationLevel,
    SandboxEvent,
    SandboxStatus,
    assert_no_forbidden_fields,
    build_input_from_reports,
    example_fixture_scenario,
    parse_scenario_dict,
    render_report_markdown,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _good_baseline() -> Dict[str, float]:
    return {
        "coverage_rate": 0.62,
        "usable_discovery_rate": 0.41,
        "severe_miss_rate": 0.08,
        "false_negative_reject_rate": 0.05,
        "late_chase_rate": 0.07,
        "fake_breakout_rate": 0.06,
        "data_gap_rate": 0.03,
        "median_mfe": 0.012,
        "median_mae": 0.009,
    }


def _scenario_two_changes() -> OfflineRuleSandboxScenario:
    return OfflineRuleSandboxScenario(
        scenario_id="scn_two_changes",
        name="lower threshold + cutoff",
        reference_window="60d",
        baseline_label="block_b_block_c_ai",
        hypothetical_rule_changes=(
            HypotheticalRuleChange(
                rule_name="early_tail_score_threshold",
                baseline_value=0.65,
                sandbox_value=0.55,
                change_type="threshold_decrease",
                rationale="probe miss reduction",
                evidence_refs=("block_b:severe_miss_triage",),
            ),
            HypotheticalRuleChange(
                rule_name="candidate_score_cutoff",
                baseline_value=0.70,
                sandbox_value=0.68,
                change_type="score_cutoff_decrease",
                rationale="probe late chase sensitivity",
                evidence_refs=("block_c:reject_attributions",),
            ),
        ),
        cohort_filters={"regime": "trend"},
        source_reports=("block_b.json", "block_c.json"),
        evidence_refs=("phase_11c_v0",),
    )


def _full_input(
    scenario: OfflineRuleSandboxScenario | None = None,
) -> OfflineRuleSandboxInput:
    return OfflineRuleSandboxInput(
        baseline_discovery_quality=_good_baseline(),
        post_discovery_outcomes={"window": "60d", "n": 1234},
        reject_attributions={"reject_rule_a": 0.4, "reject_rule_b": 0.6},
        severe_miss_triage={"top_cause": "early_tail_score_too_high"},
        replay_summary={"runs": 3, "ok": True},
        reflection_summary={"reviewer": "ai_integrated_checkpoint"},
        scenario=scenario or _scenario_two_changes(),
        evidence_refs=("phase_11c_v0",),
    )


def _walk_keys(payload: Any):
    """Yield all (path, key) tuples in a nested mapping/list payload."""
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


# ---------------------------------------------------------------------------
# 1. builds scenario without writing runtime config
# ---------------------------------------------------------------------------


def test_builds_scenario_without_writing_runtime_config(tmp_path):
    scen = _scenario_two_changes()
    d = scen.to_dict()
    assert d["sandbox_only"] is True
    assert d["writes_runtime_config"] is False
    assert d["auto_tuning_allowed"] is False
    # No file IO is triggered by constructing a scenario.
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# 2. hypothetical rule change is not runtime patch
# ---------------------------------------------------------------------------


def test_hypothetical_rule_change_is_not_runtime_patch():
    c = HypotheticalRuleChange(
        rule_name="early_tail_score_threshold",
        baseline_value=0.65,
        sandbox_value=0.55,
        change_type="threshold_decrease",
    )
    payload = c.to_dict()
    assert payload["is_hypothetical"] is True
    assert payload["is_runtime_patch"] is False
    # Must not embed any patch-style key.
    forbidden_patch_keys = {
        "runtime_config_patch",
        "threshold_patch",
        "symbol_limit_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
    }
    assert not (forbidden_patch_keys & set(payload.keys()))
    # Constructor must reject patch-named rules.
    with pytest.raises(ValueError):
        HypotheticalRuleChange(
            rule_name="some_threshold_patch",
            baseline_value=1,
            sandbox_value=2,
            change_type="threshold_decrease",
        )


# ---------------------------------------------------------------------------
# 3. computes delta metrics deterministically
# ---------------------------------------------------------------------------


def test_computes_delta_metrics_deterministically():
    eng = OfflineRuleSandboxEngine()
    si = _full_input()
    r1 = eng.evaluate_scenario(si)
    r2 = eng.evaluate_scenario(si)
    assert r1.delta_metrics == r2.delta_metrics
    assert r1.sandbox_metrics == r2.sandbox_metrics
    assert r1.recommendation_level == r2.recommendation_level
    # Direction sanity: lower threshold + lower cutoff => coverage up,
    # severe miss down, but late chase + fake breakout up.
    assert r1.delta_metrics["coverage_rate_delta"] > 0
    assert r1.delta_metrics["severe_miss_rate_delta"] < 0
    assert r1.delta_metrics["late_chase_rate_delta"] > 0
    assert r1.delta_metrics["fake_breakout_rate_delta"] > 0


# ---------------------------------------------------------------------------
# 4. missing evidence -> INSUFFICIENT_EVIDENCE / INCONCLUSIVE
# ---------------------------------------------------------------------------


def test_missing_evidence_yields_inconclusive():
    eng = OfflineRuleSandboxEngine()
    empty_si = OfflineRuleSandboxInput(
        baseline_discovery_quality={},
        post_discovery_outcomes={},
        reject_attributions={},
        severe_miss_triage={},
        replay_summary={},
        reflection_summary={},
        scenario=_scenario_two_changes(),
        evidence_refs=(),
    )
    r = eng.evaluate_scenario(empty_si)
    assert r.status == SandboxStatus.INSUFFICIENT_EVIDENCE
    assert r.recommendation_level == RecommendationLevel.INCONCLUSIVE
    assert r.sandbox_metrics == {}
    # Must NOT recommend APPLY/DEPLOY/TRADE/etc.
    assert r.recommendation_level in RecommendationLevel.ALLOWED


# ---------------------------------------------------------------------------
# 5. data gap warnings preserved
# ---------------------------------------------------------------------------


def test_data_gap_warnings_preserved():
    eng = OfflineRuleSandboxEngine()
    baseline = _good_baseline()
    baseline["data_gap_rate"] = 0.25  # high
    si = OfflineRuleSandboxInput(
        baseline_discovery_quality=baseline,
        post_discovery_outcomes={},
        reject_attributions={},
        severe_miss_triage={"top": "x"},
        replay_summary={
            "runs": 1,
            "data_gap_warnings": ["replay_window_truncated"],
        },
        reflection_summary={"data_gap_warnings": ["reflection_thin"]},
        scenario=_scenario_two_changes(),
        evidence_refs=(),
    )
    r = eng.evaluate_scenario(si)
    assert any("baseline_data_gap_rate_high" in w for w in r.data_gap_warnings)
    assert "replay_summary:replay_window_truncated" in r.data_gap_warnings
    assert (
        "reflection_summary:reflection_thin" in r.data_gap_warnings
    )
    # With multiple data-gap warnings, recommendation is conservative.
    assert r.recommendation_level in RecommendationLevel.ALLOWED


# ---------------------------------------------------------------------------
# 6. recommendation_level never APPLY / DEPLOY / TRADE
# ---------------------------------------------------------------------------


def test_recommendation_level_never_apply_deploy_trade():
    forbidden_levels = {
        "APPLY",
        "DEPLOY",
        "ENABLE_LIVE",
        "TRADE",
        "BUY",
        "SELL",
        "GO_LIVE",
        "AUTO_APPLY",
    }
    assert RecommendationLevel.ALLOWED.isdisjoint(forbidden_levels)
    eng = OfflineRuleSandboxEngine()
    # Sweep many baselines and scenarios; none should ever escape ALLOWED.
    scenarios = [
        _scenario_two_changes(),
        OfflineRuleSandboxScenario(
            scenario_id="scn_relax",
            name="relax reject rule a",
            reference_window="60d",
            baseline_label="b",
            hypothetical_rule_changes=(
                HypotheticalRuleChange(
                    rule_name="reject_rule_a",
                    baseline_value=1,
                    sandbox_value=0,
                    change_type="reject_rule_relax",
                ),
            ),
        ),
        OfflineRuleSandboxScenario(
            scenario_id="scn_tight",
            name="tighten reject rule b",
            reference_window="60d",
            baseline_label="b",
            hypothetical_rule_changes=(
                HypotheticalRuleChange(
                    rule_name="reject_rule_b",
                    baseline_value=0,
                    sandbox_value=1,
                    change_type="reject_rule_tighten",
                ),
            ),
        ),
        OfflineRuleSandboxScenario(
            scenario_id="scn_noop",
            name="noop",
            reference_window="60d",
            baseline_label="b",
            hypothetical_rule_changes=(
                HypotheticalRuleChange(
                    rule_name="placeholder",
                    baseline_value=0,
                    sandbox_value=0,
                    change_type="noop",
                ),
            ),
        ),
    ]
    for s in scenarios:
        r = eng.evaluate_scenario(_full_input(s))
        assert r.recommendation_level in RecommendationLevel.ALLOWED
        assert r.recommendation_level not in forbidden_levels


# ---------------------------------------------------------------------------
# 7. auto_tuning_allowed=false
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false():
    eng = OfflineRuleSandboxEngine()
    assert eng.auto_tuning_allowed is False
    rep = eng.build_report(
        reference_window="60d",
        sandbox_inputs=[_full_input()],
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert rep.auto_tuning_allowed is False
    assert rep.to_dict()["auto_tuning_allowed"] is False
    assert SAFETY_CONTRACT["auto_tuning_allowed"] is False
    # Scenario also asserts auto_tuning_allowed=False.
    with pytest.raises(ValueError):
        OfflineRuleSandboxScenario(
            scenario_id="bad",
            name="bad",
            reference_window="60d",
            baseline_label="b",
            auto_tuning_allowed=True,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# 8. writes_runtime_config=false
# ---------------------------------------------------------------------------


def test_writes_runtime_config_false():
    eng = OfflineRuleSandboxEngine()
    assert eng.writes_runtime_config is False
    rep = eng.build_report(
        reference_window="60d",
        sandbox_inputs=[_full_input()],
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    d = rep.to_dict()
    assert d["writes_runtime_config"] is False
    assert SAFETY_CONTRACT["writes_runtime_config"] is False
    # Scenario flag is also enforced.
    with pytest.raises(ValueError):
        OfflineRuleSandboxScenario(
            scenario_id="bad",
            name="bad",
            reference_window="60d",
            baseline_label="b",
            writes_runtime_config=True,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# 9. trade_authority=false
# ---------------------------------------------------------------------------


def test_trade_authority_false():
    eng = OfflineRuleSandboxEngine()
    assert eng.trade_authority is False
    rep = eng.build_report(
        reference_window="60d",
        sandbox_inputs=[_full_input()],
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert rep.trade_authority is False
    assert rep.to_dict()["trade_authority"] is False
    assert SAFETY_CONTRACT["trade_authority"] is False


# ---------------------------------------------------------------------------
# 10. phase_12_forbidden=true
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_true():
    eng = OfflineRuleSandboxEngine()
    assert eng.phase_12_forbidden is True
    rep = eng.build_report(
        reference_window="60d",
        sandbox_inputs=[_full_input()],
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    d = rep.to_dict()
    assert d["phase_12_forbidden"] is True
    assert d["next_allowed_phase"] == NEXT_ALLOWED_PHASE
    assert "Phase 12" not in d["next_allowed_phase"]
    assert SAFETY_CONTRACT["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 11. forbidden fields absent
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_in_all_outputs():
    eng = OfflineRuleSandboxEngine()
    rep = eng.build_report(
        reference_window="60d",
        sandbox_inputs=[_full_input()],
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    payload = rep.to_dict()
    # Engine guard already validated this internally; re-validate here.
    assert_no_forbidden_fields(payload)
    keys = set(_walk_keys(payload))
    assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
    # Markdown rendering must also avoid the literal forbidden field names
    # as keys (they may appear nowhere as field names).
    md = render_report_markdown(rep)
    # We allow the words 'stop' or 'target' to appear nowhere as JSON keys;
    # in markdown narrative we still avoid them outright for safety.
    for forbidden in FORBIDDEN_OUTPUT_FIELDS:
        # "exit" and "stop" are short words; we check only for them as
        # JSON-style keys in the markdown.
        assert f'"{forbidden}"' not in md
    # Forbidden field guard rejects hostile payloads.
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"runtime_config_patch": {"x": 1}})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"nested": [{"buy": True}]})


# ---------------------------------------------------------------------------
# 12. runner does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def _collect_imported_modules(source_text: str) -> set:
    """Return the set of module names imported by `source_text` via AST.

    Includes both `import X[.Y]` and `from X[.Y] import ...` statements.
    Excludes anything appearing only inside docstrings, comments, or
    string literals.
    """
    import ast

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


def _collect_code_identifiers(source_text: str) -> set:
    """Return Name and Attribute identifiers used in code (not strings)."""
    import ast

    tree = ast.parse(source_text)
    out: set = set()

    def attr_chain(n):
        parts = []
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            chain = attr_chain(node)
            if chain:
                out.add(chain)
    return out


def test_runner_does_not_import_forbidden_modules():
    here = Path(__file__).resolve()
    root = here.parents[2]
    runner_path = root / "scripts" / "run_offline_rule_sandbox_replay.py"
    engine_path = root / "app" / "sandbox" / "offline_rule_sandbox.py"
    init_path = root / "app" / "sandbox" / "__init__.py"

    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in (runner_path, engine_path, init_path):
        src = path.read_text(encoding="utf-8")
        imported = _collect_imported_modules(src)
        for mod in imported:
            for bad in forbidden_prefixes:
                assert not mod.startswith(bad), (
                    f"{path} imports forbidden module {mod!r}"
                )
        # Code identifiers must not reference these subpackages either.
        idents = _collect_code_identifiers(src)
        for ident in idents:
            for bad in forbidden_prefixes:
                assert not ident.startswith(bad), (
                    f"{path} references forbidden identifier {ident!r}"
                )

    # Sanity: importing the runner module does not pull forbidden modules.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_runner_under_test_phase11c", runner_path
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    before = set(sys.modules)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    new_modules = set(sys.modules) - before
    for nm in new_modules:
        for f in forbidden_prefixes:
            assert not nm.startswith(f), (
                f"runner imported forbidden module {nm}"
            )


# ---------------------------------------------------------------------------
# 13. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_or_llm_or_network_path():
    here = Path(__file__).resolve()
    root = here.parents[2]
    files = [
        root / "app" / "sandbox" / "offline_rule_sandbox.py",
        root / "app" / "sandbox" / "__init__.py",
        root / "scripts" / "run_offline_rule_sandbox_replay.py",
    ]
    # Forbidden as IMPORTED MODULE NAMES (any prefix of the module path).
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
    )
    # Forbidden as CODE IDENTIFIERS (Names / Attribute chains used in code,
    # not in docstrings or comments).
    forbidden_identifier_prefixes = (
        "deepseek",
        "openai",
        "anthropic",
        "telegram",
        "binance",
        "ccxt",
        "websocket",
        "httpx",
        "aiohttp",
        "requests.get",
        "requests.post",
        "urllib.request",
        "socket.connect",
        "socket.create_connection",
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
        idents = _collect_code_identifiers(src)
        for ident in idents:
            low = ident.lower()
            for bad in forbidden_identifier_prefixes:
                assert not low.startswith(bad), (
                    f"{path} references forbidden code identifier "
                    f"{ident!r}"
                )

    # Defensive: ensure runtime evaluation does not import network libs.
    import importlib

    pre = set(sys.modules)
    importlib.import_module("app.sandbox.offline_rule_sandbox")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), f"unexpected import: {nm}"


# ---------------------------------------------------------------------------
# 14. JSON output serializable
# ---------------------------------------------------------------------------


def test_json_output_serializable(tmp_path):
    eng = OfflineRuleSandboxEngine()
    rep = eng.build_report(
        reference_window="60d",
        sandbox_inputs=[_full_input()],
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    payload = rep.to_dict()
    # Must round-trip through JSON cleanly without `default=str`.
    s = json.dumps(payload, sort_keys=True)
    back = json.loads(s)
    assert back["report_id"] == rep.report_id
    assert back["phase_12_forbidden"] is True
    assert back["next_allowed_phase"] == NEXT_ALLOWED_PHASE
    assert isinstance(back["scenario_results"], list)


# ---------------------------------------------------------------------------
# 15. deterministic output (twice in a row, different engine instances)
# ---------------------------------------------------------------------------


def test_deterministic_output():
    fixed_now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    eng1 = OfflineRuleSandboxEngine()
    eng2 = OfflineRuleSandboxEngine()
    si = _full_input()
    r1 = eng1.build_report(
        reference_window="60d",
        sandbox_inputs=[si],
        now_utc=fixed_now,
    )
    r2 = eng2.build_report(
        reference_window="60d",
        sandbox_inputs=[si],
        now_utc=fixed_now,
    )
    p1 = json.dumps(r1.to_dict(), sort_keys=True)
    p2 = json.dumps(r2.to_dict(), sort_keys=True)
    assert p1 == p2
    assert r1.report_id == r2.report_id


# ---------------------------------------------------------------------------
# Extra: runner produces files; example fixture is labeled as such
# ---------------------------------------------------------------------------


def test_runner_writes_files_and_marks_example_fixture(tmp_path):
    from scripts import run_offline_rule_sandbox_replay as runner

    payload = runner.run(
        block_b_report_path=None,
        block_c_report_path=None,
        ai_checkpoint_path=None,
        scenario_file=None,
        output_dir=str(tmp_path),
        reference_window="60d",
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    json_path = tmp_path / "offline_rule_sandbox_report.json"
    md_path = tmp_path / "offline_rule_sandbox_report.md"
    assert json_path.is_file()
    assert md_path.is_file()
    # Example scenario must declare source=example_fixture, never
    # "operator_supplied".
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    sources = {s["source"] for s in on_disk["scenarios"]}
    assert sources == {"example_fixture"}
    # Events emitted include exactly the allowed types.
    event_types = {e["event_type"] for e in on_disk.get("events", [])}
    allowed_event_types = {
        SandboxEvent.OFFLINE_RULE_SANDBOX_REPLAY_RUN,
        SandboxEvent.OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED,
        SandboxEvent.OFFLINE_RULE_SANDBOX_REPORT_GENERATED,
    }
    assert event_types <= allowed_event_types
    # No forbidden field anywhere on disk.
    keys = set(_walk_keys(on_disk))
    assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
    # JSON is byte-identical on a second run with the same fixed clock.
    runner.run(
        block_b_report_path=None,
        block_c_report_path=None,
        ai_checkpoint_path=None,
        scenario_file=None,
        output_dir=str(tmp_path),
        reference_window="60d",
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert json_path.read_bytes() == json.dumps(
        on_disk, indent=2, sort_keys=True, default=str
    ).encode("utf-8") + b"\n"


# ---------------------------------------------------------------------------
# Extra: scenario-file parsing round-trip
# ---------------------------------------------------------------------------


def test_parse_scenario_dict_round_trip():
    src = {
        "scenario_id": "scn_x",
        "name": "x",
        "reference_window": "30d",
        "baseline_label": "bl",
        "hypothetical_rule_changes": [
            {
                "rule_name": "early_tail_score_threshold",
                "baseline_value": 0.6,
                "sandbox_value": 0.5,
                "change_type": "threshold_decrease",
                "rationale": "r",
                "evidence_refs": ["e1"],
            }
        ],
        "cohort_filters": {"k": "v"},
        "source_reports": ["a"],
        "evidence_refs": ["b"],
        "source": "operator_supplied",
    }
    s = parse_scenario_dict(src)
    assert s.scenario_id == "scn_x"
    assert s.source == "operator_supplied"
    assert s.sandbox_only is True
    assert s.writes_runtime_config is False
    # Round-trip cleanly to JSON.
    json.dumps(s.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# Extra: build_input_from_reports tolerates missing reports
# ---------------------------------------------------------------------------


def test_build_input_tolerates_missing_reports():
    si = build_input_from_reports(
        scenario=_scenario_two_changes(),
        block_b_report=None,
        block_c_report=None,
        ai_checkpoint_report=None,
    )
    eng = OfflineRuleSandboxEngine()
    r = eng.evaluate_scenario(si)
    # No baseline => INSUFFICIENT_EVIDENCE / INCONCLUSIVE.
    assert r.status == SandboxStatus.INSUFFICIENT_EVIDENCE
    assert r.recommendation_level == RecommendationLevel.INCONCLUSIVE


# ---------------------------------------------------------------------------
# Extra: SAFETY_CONTRACT shape
# ---------------------------------------------------------------------------


def test_safety_contract_shape():
    expected = {
        "phase": PHASE_NAME,
        "sandbox_only": True,
        "writes_runtime_config": False,
        "auto_tuning_allowed": False,
        "trade_authority": False,
        "phase_12_forbidden": True,
        "live_trading": False,
        "exchange_live_orders": False,
        "right_tail": False,
        "llm": False,
        "llm_outbound_enabled": False,
        "telegram_outbound_enabled": False,
        "binance_private_api_enabled": False,
        "next_allowed_phase": NEXT_ALLOWED_PHASE,
    }
    assert SAFETY_CONTRACT == expected
