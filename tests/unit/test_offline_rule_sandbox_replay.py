"""Phase 11C - Offline Rule Sandbox Replay v0 unit tests.

Paper / report / sandbox-only. None of these tests authorise a
real trade or modify any runtime knob. None of them open the
network, call DeepSeek, or read a private exchange API.

Test plan (the brief's fifteen numbered checks):

  1.  builds scenario without writing runtime config
  2.  hypothetical rule change is not a runtime patch
  3.  computes delta metrics deterministically
  4.  missing evidence -> INSUFFICIENT_EVIDENCE / INCONCLUSIVE
  5.  data gap warnings preserved
  6.  recommendation_level never APPLY / DEPLOY / TRADE
  7.  auto_tuning_allowed=False on every payload
  8.  writes_runtime_config=False on every payload
  9.  trade_authority=False on every payload
  10. phase_12_forbidden=True on every payload
  11. forbidden fields absent at every nesting depth
  12. runner does not import app.risk / app.execution /
      app.exchanges / app.telegram / app.config
  13. no DeepSeek / LLM / network call path
  14. JSON output serialisable
  15. deterministic output across two runs
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

from app.sandbox.offline_rule_sandbox import (  # noqa: E402
    FORBIDDEN_SANDBOX_PAYLOAD_KEYS,
    HypotheticalRuleChange,
    OfflineRuleSandboxEngine,
    OfflineRuleSandboxInput,
    OfflineRuleSandboxScenario,
    RECOMMENDATION_LEVELS,
    SANDBOX_EVENT_REPLAY_RUN,
    SANDBOX_EVENT_REPORT_GENERATED,
    SANDBOX_EVENT_SCENARIO_EVALUATED,
    build_example_scenario,
    safety_flags_dict,
)
from scripts import (  # noqa: E402
    run_offline_rule_sandbox_replay as runner,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_FORBIDDEN_RECOMMENDATION_LEVELS: frozenset[str] = frozenset(
    {
        "APPLY",
        "DEPLOY",
        "ENABLE_LIVE",
        "TRADE",
        "BUY",
        "SELL",
    }
)


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


def _walk_strings(node: Any) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str):
                out.append(k)
            out.extend(_walk_strings(v))
    elif isinstance(node, (list, tuple)):
        for item in node:
            out.extend(_walk_strings(item))
    return out


def _make_baseline_dict() -> dict[str, Any]:
    return {
        "coverage_rate": 0.5,
        "usable_discovery_rate": 0.4,
        "severe_miss_rate": 0.1,
        "false_negative_reject_rate": 0.08,
        "late_chase_rate": 0.07,
        "fake_breakout_rate": 0.06,
        "data_gap_rate": 0.05,
        "median_mfe": 0.04,
        "median_mae": 0.03,
    }


def _make_scenario(
    *,
    scenario_id: str = "scn_loosen_early_tail",
    rule_changes: tuple[HypotheticalRuleChange, ...] | None = None,
    evidence_refs: tuple[str, ...] = (
        "report:discovery_quality_scorecard",
    ),
) -> OfflineRuleSandboxScenario:
    if rule_changes is None:
        rule_changes = (
            HypotheticalRuleChange(
                rule_name="early_tail_score_threshold",
                baseline_value=0.5,
                sandbox_value=0.45,
                change_type="loosen",
                rationale=(
                    "test: loosen early-tail-score threshold "
                    "by 10%"
                ),
                evidence_refs=(
                    "report:discovery_quality_scorecard",
                ),
            ),
        )
    return OfflineRuleSandboxScenario(
        scenario_id=scenario_id,
        name=scenario_id,
        reference_window="60d",
        baseline_label="phase_11c_baseline_60d",
        hypothetical_rule_changes=rule_changes,
        evidence_refs=evidence_refs,
        source="operator_supplied",
    )


def _make_input(
    *,
    scenario: OfflineRuleSandboxScenario | None = None,
    baseline: dict[str, Any] | None = None,
) -> OfflineRuleSandboxInput:
    if scenario is None:
        scenario = _make_scenario()
    if baseline is None:
        baseline = _make_baseline_dict()
    return OfflineRuleSandboxInput(
        scenario=scenario,
        baseline_discovery_quality=baseline,
        post_discovery_outcomes={"sample_size": 60},
        reject_attributions={"sample_size": 60},
        severe_miss_triage={"sample_size": 60},
        replay_summary={"total_cases": 60},
        reflection_summary={"total_cases": 60},
        evidence_refs=("report:block_c_integrated_checkpoint",),
    )


# ---------------------------------------------------------------------------
# 1. builds scenario without writing runtime config
# ---------------------------------------------------------------------------
def test_builds_scenario_without_writing_runtime_config(
    tmp_path: Path,
) -> None:
    scenario = _make_scenario()
    payload = scenario.to_dict()
    assert payload["sandbox_only"] is True
    assert payload["writes_runtime_config"] is False
    assert payload["auto_tuning_allowed"] is False
    assert payload["trade_authority"] is False
    assert payload["phase_12_forbidden"] is True
    # Constructing the scenario does not touch tmp_path or any
    # other on-disk runtime config.
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# 2. hypothetical rule change is not a runtime patch
# ---------------------------------------------------------------------------
def test_hypothetical_rule_change_is_not_runtime_patch() -> None:
    hrc = HypotheticalRuleChange(
        rule_name="early_tail_score_threshold",
        baseline_value=0.5,
        sandbox_value=0.45,
        change_type="loosen",
        rationale="test",
        evidence_refs=("report:x",),
    )
    payload = hrc.to_dict()
    keys = set(_walk_keys(payload))
    forbidden_patch_keys = {
        "runtime_config_patch",
        "threshold_patch",
        "symbol_limit_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
    }
    assert keys.isdisjoint(forbidden_patch_keys)
    assert payload["is_runtime_patch"] is False
    assert payload["writes_runtime_config"] is False
    assert payload["auto_tuning_allowed"] is False
    # The dataclass's own attribute names also avoid the
    # ``*_patch`` vocabulary.
    field_names = set(HypotheticalRuleChange.__dataclass_fields__)
    assert field_names.isdisjoint(forbidden_patch_keys)


# ---------------------------------------------------------------------------
# 3. computes delta metrics deterministically
# ---------------------------------------------------------------------------
def test_computes_delta_metrics_deterministically() -> None:
    sandbox_input = _make_input()
    engine = OfflineRuleSandboxEngine()
    r1 = engine.evaluate(sandbox_input).to_dict()
    r2 = engine.evaluate(sandbox_input).to_dict()
    assert r1 == r2
    assert "delta_metrics" in r1
    delta = r1["delta_metrics"]
    # Loosening the early-tail-score threshold should push
    # coverage UP and severe-miss DOWN (deterministic
    # direction baked into the impact table).
    assert delta["coverage_rate_delta"] > 0.0
    assert delta["severe_miss_rate_delta"] < 0.0
    # The closed metric set is fully covered.
    expected_keys = {
        "coverage_rate_delta",
        "usable_discovery_rate_delta",
        "severe_miss_rate_delta",
        "false_negative_reject_rate_delta",
        "late_chase_rate_delta",
        "fake_breakout_rate_delta",
        "data_gap_rate_delta",
        "median_mfe_delta",
        "median_mae_delta",
    }
    assert set(delta.keys()) == expected_keys


# ---------------------------------------------------------------------------
# 4. missing evidence -> INSUFFICIENT_EVIDENCE / INCONCLUSIVE
# ---------------------------------------------------------------------------
def test_missing_evidence_yields_insufficient_or_inconclusive() -> None:
    # Empty baseline + a scenario with NO change_type
    # contributing any rule change.
    no_op_scenario = _make_scenario(
        scenario_id="scn_no_op",
        rule_changes=(
            HypotheticalRuleChange(
                rule_name="early_tail_score_threshold",
                baseline_value=0.5,
                sandbox_value=0.5,
                change_type="no_change",
                rationale="no-op",
                evidence_refs=(),
            ),
        ),
        evidence_refs=(),
    )
    sandbox_input = OfflineRuleSandboxInput(
        scenario=no_op_scenario,
        baseline_discovery_quality={},
        post_discovery_outcomes={},
        reject_attributions={},
        severe_miss_triage={},
        replay_summary={},
        reflection_summary={},
    )
    result = OfflineRuleSandboxEngine().evaluate(sandbox_input)
    assert result.status in {
        "INSUFFICIENT_EVIDENCE",
        "INCONCLUSIVE",
    }
    assert result.recommendation_level == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# 5. data gap warnings preserved
# ---------------------------------------------------------------------------
def test_data_gap_warnings_preserved() -> None:
    scenario = _make_scenario()
    sandbox_input = OfflineRuleSandboxInput(
        scenario=scenario,
        # No baseline discovery quality -> every metric missing.
        baseline_discovery_quality={},
        post_discovery_outcomes={},
        reject_attributions={},
        severe_miss_triage={},
        replay_summary={},
        reflection_summary={},
    )
    result = OfflineRuleSandboxEngine().evaluate(sandbox_input)
    assert result.data_gap_warnings, (
        "data_gap_warnings should be non-empty when baseline "
        "metrics are missing"
    )
    payload = result.to_dict()
    assert payload["data_gap_warnings"]
    assert any(
        "baseline_metric_missing" in warning
        for warning in payload["data_gap_warnings"]
    )


# ---------------------------------------------------------------------------
# 6. recommendation_level never APPLY / DEPLOY / TRADE
# ---------------------------------------------------------------------------
def test_recommendation_level_never_apply_deploy_trade() -> None:
    engine = OfflineRuleSandboxEngine()
    # Test across many different scenarios -> still must stay
    # inside the closed vocabulary.
    inputs: list[OfflineRuleSandboxInput] = []
    for change_type in ("loosen", "tighten", "no_change"):
        for rule_name in (
            "early_tail_score_threshold",
            "candidate_score_cutoff",
            "reject_rule_strictness",
            "anomaly_threshold",
            "liquidity_floor",
            "generic_rule",
            "unknown_rule_name_does_not_exist",
        ):
            scenario = _make_scenario(
                scenario_id=(
                    f"scn_{change_type}_{rule_name}"
                ),
                rule_changes=(
                    HypotheticalRuleChange(
                        rule_name=rule_name,
                        baseline_value=0.5,
                        sandbox_value=0.45,
                        change_type=change_type,
                        rationale="combo",
                        evidence_refs=("report:x",),
                    ),
                ),
            )
            inputs.append(_make_input(scenario=scenario))
    for sandbox_input in inputs:
        result = engine.evaluate(sandbox_input)
        assert result.recommendation_level in (
            RECOMMENDATION_LEVELS
        )
        assert (
            result.recommendation_level
            not in _FORBIDDEN_RECOMMENDATION_LEVELS
        )


# ---------------------------------------------------------------------------
# 7-10. invariant pins on every payload
# ---------------------------------------------------------------------------
def _all_payloads_for_pin_check() -> list[dict[str, Any]]:
    engine = OfflineRuleSandboxEngine()
    sandbox_input = _make_input()
    payloads: list[dict[str, Any]] = []
    payloads.append(sandbox_input.scenario.to_dict())
    payloads.append(sandbox_input.to_dict())
    payloads.append(engine.evaluate(sandbox_input).to_dict())
    payloads.append(
        engine.build_report(
            report_id="r1",
            reference_window="60d",
            sandbox_inputs=(sandbox_input,),
            generated_at_utc="1970-01-01T00:00:00Z",
        ).to_dict()
    )
    return payloads


def test_auto_tuning_allowed_false_on_every_payload() -> None:
    for payload in _all_payloads_for_pin_check():
        assert payload.get("auto_tuning_allowed") is False, (
            payload
        )


def test_writes_runtime_config_false_on_every_payload() -> None:
    for payload in _all_payloads_for_pin_check():
        assert (
            payload.get("writes_runtime_config") is False
        ), payload


def test_trade_authority_false_on_every_payload() -> None:
    for payload in _all_payloads_for_pin_check():
        # Scenario / Input do not surface trade_authority by
        # design (they are not the "live" surface). Result and
        # Report MUST surface ``trade_authority=False``.
        if payload.get("schema_version", "").endswith(
            "result.v1"
        ) or payload.get("schema_version", "").endswith(
            "report.v1"
        ) or "scenario_results" in payload:
            assert (
                payload.get("trade_authority") is False
            ), payload


def test_phase_12_forbidden_true_on_every_payload() -> None:
    for payload in _all_payloads_for_pin_check():
        assert (
            payload.get("phase_12_forbidden") is True
        ), payload


# ---------------------------------------------------------------------------
# 11. forbidden fields absent at every nesting depth
# ---------------------------------------------------------------------------
def test_forbidden_fields_absent_in_every_payload() -> None:
    for payload in _all_payloads_for_pin_check():
        keys = set(_walk_keys(payload))
        offenders = keys & FORBIDDEN_SANDBOX_PAYLOAD_KEYS
        assert offenders == set(), (
            f"forbidden keys leaked into payload: {offenders}"
        )


# ---------------------------------------------------------------------------
# 12. runner does not import app.risk / app.execution /
#     app.exchanges / app.telegram / app.config
# ---------------------------------------------------------------------------
_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.telegram",
    "app.config",
)


def _module_imports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def test_runner_does_not_import_forbidden_packages() -> None:
    runner_path = (
        PROJECT_ROOT
        / "scripts"
        / "run_offline_rule_sandbox_replay.py"
    )
    sandbox_path = (
        PROJECT_ROOT
        / "app"
        / "sandbox"
        / "offline_rule_sandbox.py"
    )
    sandbox_init_path = (
        PROJECT_ROOT
        / "app"
        / "sandbox"
        / "__init__.py"
    )
    for path in (runner_path, sandbox_path, sandbox_init_path):
        imports = _module_imports(path)
        for imp in imports:
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                assert not (
                    imp == prefix
                    or imp.startswith(prefix + ".")
                ), (
                    f"{path.name} imported forbidden module "
                    f"{imp!r}"
                )


# ---------------------------------------------------------------------------
# 13. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------
_FORBIDDEN_NETWORK_IMPORTS: tuple[str, ...] = (
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
    "app.llm",
    "app.ai.deepseek_sandbox",
)


def test_no_deepseek_llm_network_call_path() -> None:
    runner_path = (
        PROJECT_ROOT
        / "scripts"
        / "run_offline_rule_sandbox_replay.py"
    )
    sandbox_path = (
        PROJECT_ROOT
        / "app"
        / "sandbox"
        / "offline_rule_sandbox.py"
    )
    sandbox_init_path = (
        PROJECT_ROOT
        / "app"
        / "sandbox"
        / "__init__.py"
    )
    for path in (runner_path, sandbox_path, sandbox_init_path):
        imports = _module_imports(path)
        for imp in imports:
            for forbidden in _FORBIDDEN_NETWORK_IMPORTS:
                assert imp != forbidden, (
                    f"{path.name} imports forbidden network "
                    f"module {imp!r}"
                )
                assert not imp.startswith(
                    forbidden + "."
                ), (
                    f"{path.name} imports forbidden submodule "
                    f"{imp!r}"
                )


def test_no_socket_open_during_sandbox_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end belt-and-braces: monkeypatch
    :func:`socket.socket` to refuse on call and exercise the
    full runner path. If anything tries to open a socket we
    fail loudly.
    """

    import socket

    def _refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(
            "offline_rule_sandbox runner must not open a "
            "socket"
        )

    monkeypatch.setattr(socket, "socket", _refuse)

    output_dir = tmp_path / "out"
    result = runner.run_sandbox(
        block_b_report=None,
        block_c_report=None,
        ai_checkpoint=None,
        baseline_discovery_quality=None,
        post_discovery_outcomes=None,
        reject_attributions=None,
        severe_miss_triage=None,
        replay_summary=None,
        reflection_summary=None,
        scenario_file=None,
        output_dir=output_dir,
        reference_window="60d",
    )
    assert result.output_report_path.is_file()
    assert result.output_summary_path.is_file()


# ---------------------------------------------------------------------------
# 14. JSON output serialisable
# ---------------------------------------------------------------------------
def test_json_output_serialisable(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_sandbox(
        block_b_report=None,
        block_c_report=None,
        ai_checkpoint=None,
        baseline_discovery_quality=None,
        post_discovery_outcomes=None,
        reject_attributions=None,
        severe_miss_triage=None,
        replay_summary=None,
        reflection_summary=None,
        scenario_file=None,
        output_dir=output_dir,
        reference_window="60d",
    )
    text = result.output_report_path.read_text(
        encoding="utf-8"
    )
    parsed = json.loads(text)
    # Round-trip dump (round-trip json.dumps with sort_keys
    # confirms full serialisability).
    json.dumps(parsed, sort_keys=True)
    assert parsed["report_id"]
    # Markdown twin exists too.
    assert result.output_summary_path.is_file()
    assert (
        result.output_summary_path.read_text(encoding="utf-8")
        .strip()
        .startswith(
            "# Phase 11C Offline Rule Sandbox Replay v0"
        )
    )


# ---------------------------------------------------------------------------
# 15. deterministic output across two runs
# ---------------------------------------------------------------------------
def test_runner_output_deterministic(tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    fixed_time = "2026-05-28T00:00:00Z"

    def _run_with_fixed_time(out: Path) -> dict[str, Any]:
        from scripts import (
            run_offline_rule_sandbox_replay as inner_runner,
        )

        # Patch the timestamp helper so both runs produce
        # identical ``generated_at_utc`` and the JSON
        # round-trips byte-for-byte.
        original = inner_runner._now_utc_iso
        inner_runner._now_utc_iso = lambda: fixed_time
        try:
            inner_runner.run_sandbox(
                block_b_report=None,
                block_c_report=None,
                ai_checkpoint=None,
                baseline_discovery_quality=None,
                post_discovery_outcomes=None,
                reject_attributions=None,
                severe_miss_triage=None,
                replay_summary=None,
                reflection_summary=None,
                scenario_file=None,
                output_dir=out,
                reference_window="60d",
            )
        finally:
            inner_runner._now_utc_iso = original
        return json.loads(
            (
                out
                / "offline_rule_sandbox_report.json"
            ).read_text(encoding="utf-8")
        )

    a = _run_with_fixed_time(out_a)
    b = _run_with_fixed_time(out_b)
    assert a == b


# ---------------------------------------------------------------------------
# Additional sanity tests
# ---------------------------------------------------------------------------
def test_recommendation_levels_vocabulary_is_closed() -> None:
    expected = {
        "REVIEW_ONLY",
        "INCONCLUSIVE",
        "PROMISING_FOR_PAPER_SHADOW",
        "RISKY",
        "REJECTED_BY_EVIDENCE",
    }
    assert set(RECOMMENDATION_LEVELS) == expected


def test_recommendation_levels_does_not_contain_forbidden() -> None:
    assert (
        set(RECOMMENDATION_LEVELS)
        & _FORBIDDEN_RECOMMENDATION_LEVELS
        == set()
    )


def test_event_names_are_report_only() -> None:
    # The three event names defined for this slice are pure
    # strings and are NOT wired into ``app.core.events.EventType``
    # (the brief restricts allowed file modifications).
    assert SANDBOX_EVENT_REPLAY_RUN.startswith(
        "OFFLINE_RULE_SANDBOX_"
    )
    assert SANDBOX_EVENT_SCENARIO_EVALUATED.startswith(
        "OFFLINE_RULE_SANDBOX_"
    )
    assert SANDBOX_EVENT_REPORT_GENERATED.startswith(
        "OFFLINE_RULE_SANDBOX_"
    )
    # Importing the canonical EventType enum and checking it
    # does NOT carry these names.
    from app.core.events import EventType  # noqa: WPS433

    existing = {member.value for member in EventType}
    assert SANDBOX_EVENT_REPLAY_RUN not in existing
    assert SANDBOX_EVENT_SCENARIO_EVALUATED not in existing
    assert SANDBOX_EVENT_REPORT_GENERATED not in existing


def test_safety_flags_dict_pins_paper_only() -> None:
    flags = safety_flags_dict()
    assert flags["mode"] == "paper"
    assert flags["live_trading"] is False
    assert flags["exchange_live_orders"] is False
    assert flags["right_tail"] is False
    assert flags["llm"] is False
    assert flags["llm_outbound_enabled"] is False
    assert flags["sandbox_only"] is True
    assert flags["allow_trade_decision"] is False
    assert flags["allow_runtime_config_change"] is False
    assert flags["auto_tuning_allowed"] is False
    assert flags["telegram_outbound_enabled"] is False
    assert flags["binance_private_api_enabled"] is False


def test_example_scenario_is_marked_example_fixture() -> None:
    scenario = build_example_scenario()
    payload = scenario.to_dict()
    assert payload["source"] == "example_fixture"
    # And it must NOT pretend to be operator-supplied.
    assert payload["source"] != "operator_supplied"


def test_runner_falls_back_to_example_fixture_when_scenario_missing(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_sandbox(
        block_b_report=None,
        block_c_report=None,
        ai_checkpoint=None,
        baseline_discovery_quality=None,
        post_discovery_outcomes=None,
        reject_attributions=None,
        severe_miss_triage=None,
        replay_summary=None,
        reflection_summary=None,
        scenario_file=tmp_path / "does_not_exist.json",
        output_dir=output_dir,
        reference_window="60d",
    )
    parsed = json.loads(
        result.output_report_path.read_text(encoding="utf-8")
    )
    assert parsed["scenario_source"] == "example_fixture"


def test_runner_loads_operator_supplied_scenario(
    tmp_path: Path,
) -> None:
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(
        json.dumps(
            {
                "scenario_id": "op_scn_loosen",
                "name": "operator scenario",
                "reference_window": "60d",
                "baseline_label": "operator_baseline",
                "hypothetical_rule_changes": [
                    {
                        "rule_name": (
                            "early_tail_score_threshold"
                        ),
                        "baseline_value": 0.5,
                        "sandbox_value": 0.45,
                        "change_type": "loosen",
                        "rationale": "operator review",
                        "evidence_refs": ["report:x"],
                    }
                ],
                "evidence_refs": ["report:y"],
                "source": "operator_supplied",
            }
        ),
        encoding="utf-8",
    )

    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(_make_baseline_dict()), encoding="utf-8"
    )

    output_dir = tmp_path / "out"
    result = runner.run_sandbox(
        block_b_report=None,
        block_c_report=None,
        ai_checkpoint=None,
        baseline_discovery_quality=baseline_path,
        post_discovery_outcomes=None,
        reject_attributions=None,
        severe_miss_triage=None,
        replay_summary=None,
        reflection_summary=None,
        scenario_file=scenario_file,
        output_dir=output_dir,
        reference_window="60d",
    )
    parsed = json.loads(
        result.output_report_path.read_text(encoding="utf-8")
    )
    assert parsed["scenario_source"] == "operator_supplied"
    assert parsed["scenarios"][0]["scenario_id"] == (
        "op_scn_loosen"
    )


def test_runner_main_emits_clean_summary_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "out"
    rc = runner.main(
        [
            "--block-b-report",
            str(tmp_path / "missing_b.json"),
            "--block-c-report",
            str(tmp_path / "missing_c.json"),
            "--ai-checkpoint",
            str(tmp_path / "missing_ai.json"),
            "--scenario-file",
            str(tmp_path / "missing_scenario.json"),
            "--output-dir",
            str(output_dir),
            "--reference-window",
            "60d",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["report_id"]
    forbidden_rec_levels = (
        _FORBIDDEN_RECOMMENDATION_LEVELS
    )
    for sc_id in parsed.get(
        "best_review_candidates"
    ) or []:
        assert sc_id not in forbidden_rec_levels
    for sc_id in parsed.get("rejected_scenarios") or []:
        assert sc_id not in forbidden_rec_levels


def test_no_apply_or_deploy_strings_in_emitted_report(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_sandbox(
        block_b_report=None,
        block_c_report=None,
        ai_checkpoint=None,
        baseline_discovery_quality=None,
        post_discovery_outcomes=None,
        reject_attributions=None,
        severe_miss_triage=None,
        replay_summary=None,
        reflection_summary=None,
        scenario_file=None,
        output_dir=output_dir,
        reference_window="60d",
    )
    parsed = json.loads(
        result.output_report_path.read_text(encoding="utf-8")
    )
    # The recommendation_level vocabulary already constrains
    # this, but a belt-and-braces scan for the forbidden
    # *recommendation strings* makes the contract explicit.
    forbidden_strings = {
        "APPLY",
        "DEPLOY",
        "ENABLE_LIVE",
        "TRADE",
        "BUY",
        "SELL",
    }
    # We only forbid these as full STRING VALUES, not as
    # substrings (e.g. ``OFFLINE_RULE_SANDBOX_REPLAY_RUN``
    # contains the substring "REPLAY" which is fine, and the
    # word ``deploy_change`` could legitimately appear inside
    # the forbidden_fields catalogue itself).
    for s in _walk_strings(parsed):
        if s in forbidden_strings:
            raise AssertionError(
                f"forbidden trade-action recommendation string "
                f"appeared in payload: {s!r}"
            )


def test_engine_recommends_paper_shadow_for_promising_change() -> None:
    # A meaningful loosen with explicit evidence and not too
    # many side-effects -> PROMISING_FOR_PAPER_SHADOW.
    scenario = _make_scenario(
        scenario_id="scn_promising",
        rule_changes=(
            HypotheticalRuleChange(
                rule_name="early_tail_score_threshold",
                baseline_value=0.5,
                sandbox_value=0.45,  # 10% loosen
                change_type="loosen",
                rationale="modest loosen",
                evidence_refs=("report:a", "report:b"),
            ),
        ),
        evidence_refs=("report:c",),
    )
    sandbox_input = _make_input(scenario=scenario)
    result = OfflineRuleSandboxEngine().evaluate(sandbox_input)
    # The engine should not flag overfit warnings for a
    # single small loosen with explicit evidence refs, and
    # coverage should improve enough to clear the promising
    # threshold.
    assert (
        result.recommendation_level
        == "PROMISING_FOR_PAPER_SHADOW"
    )


def test_engine_rejects_high_severe_miss_increase() -> None:
    # A heavy tighten of the early-tail-score threshold drives
    # severe-miss UP past the risky threshold -> REJECTED.
    scenario = _make_scenario(
        scenario_id="scn_reject",
        rule_changes=(
            HypotheticalRuleChange(
                rule_name="early_tail_score_threshold",
                baseline_value=0.1,
                sandbox_value=1.0,  # huge tighten
                change_type="tighten",
                rationale="severe tighten",
                evidence_refs=("report:a",),
            ),
        ),
        evidence_refs=("report:b",),
    )
    sandbox_input = _make_input(scenario=scenario)
    result = OfflineRuleSandboxEngine().evaluate(sandbox_input)
    assert result.recommendation_level == (
        "REJECTED_BY_EVIDENCE"
    )


def test_engine_marks_overfit_when_too_many_changes() -> None:
    rule_changes = tuple(
        HypotheticalRuleChange(
            rule_name=f"rule_{i}",
            baseline_value=0.5,
            sandbox_value=0.45,
            change_type="loosen",
            rationale="overfit candidate",
            evidence_refs=("report:x",),
        )
        for i in range(5)
    )
    scenario = _make_scenario(
        scenario_id="scn_overfit",
        rule_changes=rule_changes,
        evidence_refs=("report:y",),
    )
    sandbox_input = _make_input(scenario=scenario)
    result = OfflineRuleSandboxEngine().evaluate(sandbox_input)
    assert result.overfit_warnings
    assert any(
        "too_many_rule_changes" in w
        for w in result.overfit_warnings
    )


def test_report_aggregates_best_review_and_rejected() -> None:
    engine = OfflineRuleSandboxEngine()
    promising_input = _make_input(
        scenario=_make_scenario(
            scenario_id="scn_promising",
            rule_changes=(
                HypotheticalRuleChange(
                    rule_name=(
                        "early_tail_score_threshold"
                    ),
                    baseline_value=0.5,
                    sandbox_value=0.45,  # 10% loosen
                    change_type="loosen",
                    rationale="modest",
                    evidence_refs=("report:a",),
                ),
            ),
            evidence_refs=("report:b",),
        )
    )
    rejected_input = _make_input(
        scenario=_make_scenario(
            scenario_id="scn_rejected",
            rule_changes=(
                HypotheticalRuleChange(
                    rule_name=(
                        "early_tail_score_threshold"
                    ),
                    baseline_value=0.1,
                    sandbox_value=1.0,
                    change_type="tighten",
                    rationale="severe",
                    evidence_refs=("report:a",),
                ),
            ),
            evidence_refs=("report:b",),
        )
    )
    report = engine.build_report(
        report_id="r_aggregate",
        reference_window="60d",
        sandbox_inputs=(promising_input, rejected_input),
        generated_at_utc="1970-01-01T00:00:00Z",
    )
    payload = report.to_dict()
    assert "scn_promising" in payload[
        "best_review_candidates"
    ]
    assert "scn_rejected" in payload["rejected_scenarios"]
    assert payload["next_allowed_phase"].startswith(
        "Paper Shadow Strategy Validation preparation"
    )


def test_runner_module_re_pins_safety_flags(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    result = runner.run_sandbox(
        block_b_report=None,
        block_c_report=None,
        ai_checkpoint=None,
        baseline_discovery_quality=None,
        post_discovery_outcomes=None,
        reject_attributions=None,
        severe_miss_triage=None,
        replay_summary=None,
        reflection_summary=None,
        scenario_file=None,
        output_dir=output_dir,
        reference_window="60d",
    )
    parsed = json.loads(
        result.output_report_path.read_text(encoding="utf-8")
    )
    flags = parsed["safety_flags"]
    assert flags["mode"] == "paper"
    assert flags["live_trading"] is False
    assert flags["exchange_live_orders"] is False
    assert flags["right_tail"] is False
    assert flags["llm"] is False
    assert flags["sandbox_only"] is True
    assert parsed["phase_12_forbidden"] is True
    assert parsed["auto_tuning_allowed"] is False
    assert parsed["writes_runtime_config"] is False
    assert parsed["trade_authority"] is False
