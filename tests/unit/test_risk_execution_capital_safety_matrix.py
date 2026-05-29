"""Unit tests for Phase 11C.1D-C / Risk / Execution / Capital Safety
Matrix v0.

These tests are the safety contract for this phase. If any of them
fails, the module is not safe to merge.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Mapping

import pytest

from app.safety import (
    FORBIDDEN_OUTPUT_FIELDS,
    NEXT_ALLOWED_PHASE_NO_BLOCKERS,
    NEXT_ALLOWED_PHASE_WITH_BLOCKERS,
    PHASE_NAME,
    SAFETY_CONTRACT,
    SafetyMatrixEngine,
    SafetyMatrixEvent,
    SafetyMatrixExpectedAction,
    SafetyMatrixReport,
    SafetyMatrixResult,
    SafetyMatrixResultStatus,
    SafetyMatrixScenario,
    SafetyMatrixScenarioType,
    SafetyMatrixSeverity,
    assert_no_forbidden_fields,
    default_scenario_set,
    render_report_markdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FIXED_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)


def _walk_keys(payload: Any):
    """Yield all keys appearing in a nested mapping/list payload."""
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


def _scenario_by_id(report: SafetyMatrixReport, sid: str) -> SafetyMatrixResult:
    for r in report.scenario_results:
        if r.scenario_id == sid:
            return r
    raise AssertionError(f"scenario {sid!r} not in report")


def _scenarios_by_type(
    scenarios, scenario_type: str
) -> List[SafetyMatrixScenario]:
    return [s for s in scenarios if s.scenario_type == scenario_type]


def _build_default_report() -> SafetyMatrixReport:
    eng = SafetyMatrixEngine()
    return eng.build_report(
        reference_window="60d",
        scenarios=default_scenario_set(),
        now_utc=_FIXED_NOW,
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _collect_imported_modules(source_text: str) -> set:
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
    import ast

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
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            chain = attr_chain(node)
            if chain:
                out.add(chain)
    return out


# ---------------------------------------------------------------------------
# 1. STOP_FAILED -> PAUSE_NEW_OPENS / REQUIRE_OPERATOR_REVIEW
# ---------------------------------------------------------------------------


def test_stop_failed_pauses_new_opens_and_requires_operator_review():
    rep = _build_default_report()
    [s] = _scenarios_by_type(
        default_scenario_set(), SafetyMatrixScenarioType.STOP_FAILED
    )
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.status == SafetyMatrixResultStatus.PASS
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.PAUSE_NEW_OPENS in obs
    assert SafetyMatrixExpectedAction.REQUIRE_OPERATOR_REVIEW in obs
    assert r.requires_operator_review is True


# ---------------------------------------------------------------------------
# 2. STOP_UNCONFIRMED -> REJECT_UNSAFE_ACTION
# ---------------------------------------------------------------------------


def test_stop_unconfirmed_rejects_unsafe_action():
    rep = _build_default_report()
    [s] = _scenarios_by_type(
        default_scenario_set(), SafetyMatrixScenarioType.STOP_UNCONFIRMED
    )
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.REJECT_UNSAFE_ACTION in obs


# ---------------------------------------------------------------------------
# 3. GHOST_POSITION -> PAUSE_NEW_OPENS / REQUIRE_OPERATOR_RESUME
# ---------------------------------------------------------------------------


def test_ghost_position_pauses_and_requires_operator_resume():
    rep = _build_default_report()
    [s] = _scenarios_by_type(
        default_scenario_set(), SafetyMatrixScenarioType.GHOST_POSITION
    )
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.PAUSE_NEW_OPENS in obs
    assert SafetyMatrixExpectedAction.REQUIRE_OPERATOR_RESUME in obs
    assert r.requires_operator_resume is True


# ---------------------------------------------------------------------------
# 4. RECONCILIATION_MISMATCH -> REQUIRE_OPERATOR_REVIEW
# ---------------------------------------------------------------------------


def test_reconciliation_mismatch_requires_operator_review():
    rep = _build_default_report()
    [s] = _scenarios_by_type(
        default_scenario_set(),
        SafetyMatrixScenarioType.RECONCILIATION_MISMATCH,
    )
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.REQUIRE_OPERATOR_REVIEW in obs
    assert SafetyMatrixExpectedAction.PAUSE_NEW_OPENS in obs


# ---------------------------------------------------------------------------
# 5. DATA_DEGRADED / WS_STALE -> DEGRADE_TO_REPORT_ONLY
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stype",
    [
        SafetyMatrixScenarioType.DATA_DEGRADED,
        SafetyMatrixScenarioType.WS_STALE,
    ],
)
def test_data_degraded_and_ws_stale_degrade_to_report_only(stype):
    rep = _build_default_report()
    [s] = _scenarios_by_type(default_scenario_set(), stype)
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.DEGRADE_TO_REPORT_ONLY in obs


# ---------------------------------------------------------------------------
# 6. REST_429 / REST_418 -> DEGRADE_TO_REPORT_ONLY or REQUIRE_OPERATOR_REVIEW
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stype",
    [
        SafetyMatrixScenarioType.REST_429,
        SafetyMatrixScenarioType.REST_418,
    ],
)
def test_rest_429_and_418_degrade_or_require_review(stype):
    rep = _build_default_report()
    [s] = _scenarios_by_type(default_scenario_set(), stype)
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert (
        SafetyMatrixExpectedAction.DEGRADE_TO_REPORT_ONLY in obs
        or SafetyMatrixExpectedAction.REQUIRE_OPERATOR_REVIEW in obs
    )
    # The default decision table observes BOTH actions.
    assert SafetyMatrixExpectedAction.DEGRADE_TO_REPORT_ONLY in obs
    assert SafetyMatrixExpectedAction.REQUIRE_OPERATOR_REVIEW in obs


# ---------------------------------------------------------------------------
# 7. TELEGRAM outbound blocked -> BLOCK_TELEGRAM_OUTBOUND
# ---------------------------------------------------------------------------


def test_telegram_outbound_blocked_action_present():
    rep = _build_default_report()
    [s] = _scenarios_by_type(
        default_scenario_set(),
        SafetyMatrixScenarioType.TELEGRAM_OUTBOUND_BLOCKED,
    )
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.BLOCK_TELEGRAM_OUTBOUND in obs
    # Universal flag too:
    assert r.telegram_outbound_blocked is True
    # And on every other scenario, BLOCK_TELEGRAM_OUTBOUND is also
    # observed as a universal block:
    for r2 in rep.scenario_results:
        assert (
            SafetyMatrixExpectedAction.BLOCK_TELEGRAM_OUTBOUND
            in set(r2.observed_actions)
        )
        assert r2.telegram_outbound_blocked is True


# ---------------------------------------------------------------------------
# 8. AI degraded / DeepSeek timeout -> BLOCK_AI_TRADE_AUTHORITY /
#    DEGRADE_TO_REPORT_ONLY
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stype",
    [
        SafetyMatrixScenarioType.LLM_DEGRADED,
        SafetyMatrixScenarioType.DEEPSEEK_TIMEOUT,
    ],
)
def test_ai_degraded_and_deepseek_timeout_block_ai_and_degrade(stype):
    rep = _build_default_report()
    [s] = _scenarios_by_type(default_scenario_set(), stype)
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.BLOCK_AI_TRADE_AUTHORITY in obs
    assert SafetyMatrixExpectedAction.DEGRADE_TO_REPORT_ONLY in obs
    assert r.ai_trade_authority_blocked is True


# ---------------------------------------------------------------------------
# 9. CAPITAL_REBASE_IN_PROGRESS -> PAUSE_NEW_OPENS / PAPER_LEDGER_ONLY
# ---------------------------------------------------------------------------


def test_capital_rebase_in_progress_pauses_and_paper_ledger_only():
    rep = _build_default_report()
    [s] = _scenarios_by_type(
        default_scenario_set(),
        SafetyMatrixScenarioType.CAPITAL_REBASE_IN_PROGRESS,
    )
    r = _scenario_by_id(rep, s.scenario_id)
    assert r.passed is True
    obs = set(r.observed_actions)
    assert SafetyMatrixExpectedAction.PAUSE_NEW_OPENS in obs
    assert SafetyMatrixExpectedAction.PAPER_LEDGER_ONLY in obs


# ---------------------------------------------------------------------------
# 10. all scenarios must keep live_order_blocked=True
# ---------------------------------------------------------------------------


def test_all_scenarios_keep_live_order_blocked_true():
    rep = _build_default_report()
    assert rep.scenario_results, "must evaluate at least one scenario"
    for r in rep.scenario_results:
        assert r.live_order_blocked is True
        d = r.to_dict()
        assert d["live_order_blocked"] is True
        # And the universal block action is observed on every result.
        assert (
            SafetyMatrixExpectedAction.BLOCK_LIVE_ORDER
            in set(r.observed_actions)
        )
    # Also at the report level: live_trading=False,
    # exchange_live_orders=False, binance_private_api_enabled=False.
    rd = rep.to_dict()
    assert rd["live_trading"] is False
    assert rd["exchange_live_orders"] is False
    assert rd["binance_private_api_enabled"] is False


# ---------------------------------------------------------------------------
# 11. all scenarios must keep runtime_config_unchanged=True
# ---------------------------------------------------------------------------


def test_all_scenarios_keep_runtime_config_unchanged_true():
    rep = _build_default_report()
    for r in rep.scenario_results:
        assert r.runtime_config_unchanged is True
        d = r.to_dict()
        assert d["runtime_config_unchanged"] is True
        assert (
            SafetyMatrixExpectedAction.BLOCK_RUNTIME_CONFIG_CHANGE
            in set(r.observed_actions)
        )
    rd = rep.to_dict()
    assert rd["writes_runtime_config"] is False
    assert rd["allow_runtime_config_change"] is False


# ---------------------------------------------------------------------------
# 12. all scenarios must keep phase_12_forbidden=True
# ---------------------------------------------------------------------------


def test_all_scenarios_keep_phase_12_forbidden_true():
    rep = _build_default_report()
    for r in rep.scenario_results:
        assert r.phase_12_forbidden is True
        d = r.to_dict()
        assert d["phase_12_forbidden"] is True
    rd = rep.to_dict()
    assert rd["phase_12_forbidden"] is True
    # The literal "Phase 12" is intentionally NOT a substring of the
    # next_allowed_phase string (no advancement to Phase 12).
    assert "Phase 12" not in rd["next_allowed_phase"]
    # And for the with-blockers fallback string too.
    assert "Phase 12" not in NEXT_ALLOWED_PHASE_NO_BLOCKERS
    assert "Phase 12" not in NEXT_ALLOWED_PHASE_WITH_BLOCKERS


# ---------------------------------------------------------------------------
# 13. auto_tuning_allowed=False
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_everywhere():
    rep = _build_default_report()
    for r in rep.scenario_results:
        d = r.to_dict()
        assert d["auto_tuning_allowed"] is False
    rd = rep.to_dict()
    assert rd["auto_tuning_allowed"] is False
    assert SAFETY_CONTRACT["auto_tuning_allowed"] is False
    eng = SafetyMatrixEngine()
    assert eng.auto_tuning_allowed is False


# ---------------------------------------------------------------------------
# 14. trade_authority=False
# ---------------------------------------------------------------------------


def test_trade_authority_false_everywhere():
    rep = _build_default_report()
    for r in rep.scenario_results:
        d = r.to_dict()
        assert d["trade_authority"] is False
        assert d["ai_trade_authority_blocked"] is True
    rd = rep.to_dict()
    assert rd["trade_authority"] is False
    assert rd["allow_trade_decision"] is False
    assert SAFETY_CONTRACT["trade_authority"] is False
    eng = SafetyMatrixEngine()
    assert eng.trade_authority is False
    assert eng.allow_trade_decision is False


# ---------------------------------------------------------------------------
# 15. forbidden fields absent in all output payloads
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_in_all_outputs():
    rep = _build_default_report()
    payload = rep.to_dict()
    assert_no_forbidden_fields(payload)
    keys = set(_walk_keys(payload))
    assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
    # Scenario dicts must also be clean.
    for s in default_scenario_set():
        assert_no_forbidden_fields(s.to_dict())
        assert set(_walk_keys(s.to_dict())).isdisjoint(
            FORBIDDEN_OUTPUT_FIELDS
        )
    # Markdown rendering must avoid the literal forbidden field names
    # as JSON-style keys.
    md = render_report_markdown(rep)
    for forbidden in FORBIDDEN_OUTPUT_FIELDS:
        assert f'"{forbidden}"' not in md
    # Forbidden field guard rejects hostile payloads.
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"runtime_config_patch": {"x": 1}})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"nested": [{"buy": True}]})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"deep": [{"inner": {"leverage": 5}}]})
    with pytest.raises(ValueError):
        assert_no_forbidden_fields(
            {"top": {"trading_approved": True}}
        )
    with pytest.raises(ValueError):
        assert_no_forbidden_fields({"top": {"live_ready": True}})


# ---------------------------------------------------------------------------
# 16. runner does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


def test_no_forbidden_app_imports_in_runner_engine_or_init():
    root = _project_root()
    runner_path = (
        root / "scripts" / "run_risk_execution_capital_safety_matrix.py"
    )
    engine_path = (
        root / "app" / "safety" / "risk_execution_capital_matrix.py"
    )
    init_path = root / "app" / "safety" / "__init__.py"

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
        idents = _collect_code_identifiers(src)
        for ident in idents:
            for bad in forbidden_prefixes:
                assert not ident.startswith(bad), (
                    f"{path} references forbidden identifier {ident!r}"
                )

    # Sanity: importing the runner module does not pull forbidden modules.
    spec = importlib.util.spec_from_file_location(
        "_safety_matrix_runner_under_test_phase11c_1d_c",
        runner_path,
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
# 17. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_or_llm_or_network_path():
    root = _project_root()
    files = [
        root / "app" / "safety" / "risk_execution_capital_matrix.py",
        root / "app" / "safety" / "__init__.py",
        root / "scripts" / "run_risk_execution_capital_safety_matrix.py",
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
    )
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
    # Identifiers we ALLOW even though they share a forbidden prefix:
    # these are safety-flag declarations, scenario-type label
    # constants, and string-key references on the report payload, NOT
    # network call paths. Each is False / descriptive by construction
    # (see SAFETY_CONTRACT and SafetyMatrixScenarioType) and exists
    # precisely to make the safety boundary visible.
    safety_flag_idents = {
        # Hard-pinned safety flags:
        "telegram_outbound_enabled",
        "telegram_outbound_blocked",
        "binance_private_api_enabled",
        # Closed-taxonomy scenario type labels (descriptive only):
        "deepseek_timeout",
        "telegram_outbound_blocked",
        "telegram_export_failure",
        # Fixture key labels appearing in simulated_inputs / events:
        "telegram_outbound_enabled_fixture",
        "deepseek_provider_fixture",
        "deepseek_status_fixture",
    }
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
            if low in safety_flag_idents:
                continue
            for bad in forbidden_identifier_prefixes:
                assert not low.startswith(bad), (
                    f"{path} references forbidden code identifier "
                    f"{ident!r}"
                )

    # Defensive: ensure runtime evaluation does not import network libs.
    pre = set(sys.modules)
    importlib.import_module("app.safety.risk_execution_capital_matrix")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), f"unexpected import: {nm}"


# ---------------------------------------------------------------------------
# 18. JSON output serializable
# ---------------------------------------------------------------------------


def test_json_output_serializable():
    rep = _build_default_report()
    payload = rep.to_dict()
    # Must round-trip through JSON cleanly without ``default=str``.
    s = json.dumps(payload, sort_keys=True)
    back = json.loads(s)
    assert back["report_id"] == rep.report_id
    assert back["phase_12_forbidden"] is True
    assert back["next_allowed_phase"] in (
        NEXT_ALLOWED_PHASE_NO_BLOCKERS,
        NEXT_ALLOWED_PHASE_WITH_BLOCKERS,
    )
    assert isinstance(back["scenario_results"], list)
    for sr in back["scenario_results"]:
        assert "scenario_id" in sr
        assert "scenario_type" in sr
        assert "status" in sr
        assert sr["status"] in SafetyMatrixResultStatus.ALLOWED
        assert sr["scenario_type"] in SafetyMatrixScenarioType.ALLOWED


# ---------------------------------------------------------------------------
# 19. deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output():
    eng1 = SafetyMatrixEngine()
    eng2 = SafetyMatrixEngine()
    r1 = eng1.build_report(
        reference_window="60d",
        scenarios=default_scenario_set(),
        now_utc=_FIXED_NOW,
    )
    r2 = eng2.build_report(
        reference_window="60d",
        scenarios=default_scenario_set(),
        now_utc=_FIXED_NOW,
    )
    p1 = json.dumps(r1.to_dict(), sort_keys=True)
    p2 = json.dumps(r2.to_dict(), sort_keys=True)
    assert p1 == p2
    assert r1.report_id == r2.report_id


# ---------------------------------------------------------------------------
# 20. next_allowed_phase = Strict Blind Walk-forward design checkpoint
#     ONLY when no P0/P1 blockers
# ---------------------------------------------------------------------------


def test_next_allowed_phase_only_strict_blind_walk_forward_design_checkpoint():
    # Default scenario set must produce zero P0 / P1 failures, so the
    # report's next_allowed_phase must be the design-checkpoint string,
    # NOT the remediation string, NOT live trading, NOT Phase 12, NOT
    # Blind Walk-forward implementation.
    rep = _build_default_report()
    assert rep.failed_count == 0
    assert rep.p0_failures == ()
    assert rep.p1_failures == ()
    assert rep.next_allowed_phase == NEXT_ALLOWED_PHASE_NO_BLOCKERS
    assert (
        "Strict Blind Walk-forward design checkpoint"
        in rep.next_allowed_phase
    )
    # The string must NOT promise Blind Walk-forward IMPLEMENTATION.
    assert "implementation" not in rep.next_allowed_phase.lower() or (
        "Blind Walk-forward implementation".lower()
        not in rep.next_allowed_phase.lower()
    )
    # Conservative assertion: we explicitly forbid the literal
    # "Blind Walk-forward implementation" substring as the destination.
    assert (
        "Blind Walk-forward implementation"
        not in rep.next_allowed_phase
    )
    # And NOT Phase 12.
    assert "Phase 12" not in rep.next_allowed_phase

    # If we INTRODUCE a P1 failure (by injecting a scenario whose
    # expected_actions include an action the decision table will not
    # observe), next_allowed_phase MUST flip to remediation-required,
    # NOT the design-checkpoint string.
    bad_scenario = SafetyMatrixScenario(
        scenario_id="sm_synthetic_p1_failure",
        scenario_type=SafetyMatrixScenarioType.DATA_DEGRADED,
        description="synthetic P1 failure: requires an action the "
        "decision table will not observe for this type.",
        simulated_inputs={"is_paper": True},
        expected_actions=(
            SafetyMatrixExpectedAction.DEGRADE_TO_REPORT_ONLY,
            # PAUSE_NEW_OPENS is NOT observed for DATA_DEGRADED in
            # the decision table, so this scenario will fail.
            SafetyMatrixExpectedAction.PAUSE_NEW_OPENS,
        ),
        severity=SafetyMatrixSeverity.P1,
    )
    eng = SafetyMatrixEngine()
    rep2 = eng.build_report(
        reference_window="60d",
        scenarios=default_scenario_set() + [bad_scenario],
        now_utc=_FIXED_NOW,
    )
    assert rep2.failed_count >= 1
    assert "sm_synthetic_p1_failure" in rep2.p1_failures
    assert rep2.next_allowed_phase == NEXT_ALLOWED_PHASE_WITH_BLOCKERS
    assert (
        "Strict Blind Walk-forward design checkpoint"
        not in rep2.next_allowed_phase
    )


# ---------------------------------------------------------------------------
# Extra: scenarios whose expected_actions include illegal values are
#        rejected at construction time
# ---------------------------------------------------------------------------


def test_scenario_rejects_illegal_expected_action():
    with pytest.raises(ValueError):
        SafetyMatrixScenario(
            scenario_id="sm_illegal_action",
            scenario_type=SafetyMatrixScenarioType.STOP_FAILED,
            description="x",
            simulated_inputs={"is_paper": True},
            expected_actions=("APPLY",),  # not in ALLOWED
        )
    with pytest.raises(ValueError):
        SafetyMatrixScenario(
            scenario_id="sm_illegal_type",
            scenario_type="ENABLE_LIVE",
            description="x",
            simulated_inputs={"is_paper": True},
            expected_actions=(
                SafetyMatrixExpectedAction.NO_ACTION_REQUIRED,
            ),
        )
    with pytest.raises(ValueError):
        SafetyMatrixScenario(
            scenario_id="",
            scenario_type=SafetyMatrixScenarioType.STOP_FAILED,
            description="x",
            simulated_inputs={"is_paper": True},
            expected_actions=(),
        )
    # simulated_inputs containing a forbidden field is rejected.
    with pytest.raises(ValueError):
        SafetyMatrixScenario(
            scenario_id="sm_smuggled_field",
            scenario_type=SafetyMatrixScenarioType.STOP_FAILED,
            description="smuggled forbidden field in simulated_inputs",
            simulated_inputs={"runtime_config_patch": {"foo": 1}},
            expected_actions=(
                SafetyMatrixExpectedAction.RECORD_AUDIT_EVENT,
            ),
        )


# ---------------------------------------------------------------------------
# Extra: every scenario type from the closed taxonomy is exercised by
#        the default scenario set
# ---------------------------------------------------------------------------


def test_default_scenario_set_covers_full_taxonomy():
    types_seen = {s.scenario_type for s in default_scenario_set()}
    assert types_seen == SafetyMatrixScenarioType.ALLOWED


# ---------------------------------------------------------------------------
# Extra: SAFETY_CONTRACT shape is exactly the locked contract
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
        "allow_trade_decision": False,
        "allow_runtime_config_change": False,
        "next_allowed_phase_no_blockers": (
            NEXT_ALLOWED_PHASE_NO_BLOCKERS
        ),
        "next_allowed_phase_with_blockers": (
            NEXT_ALLOWED_PHASE_WITH_BLOCKERS
        ),
    }
    assert SAFETY_CONTRACT == expected


# ---------------------------------------------------------------------------
# Extra: empty scenarios -> INSUFFICIENT_EVIDENCE status
# ---------------------------------------------------------------------------


def test_empty_scenarios_yields_insufficient_evidence_status():
    eng = SafetyMatrixEngine()
    rep = eng.build_report(
        reference_window="60d",
        scenarios=[],
        now_utc=_FIXED_NOW,
    )
    assert rep.status == SafetyMatrixResultStatus.INSUFFICIENT_EVIDENCE
    assert rep.total_scenarios == 0
    assert rep.passed_count == 0
    assert rep.failed_count == 0
    assert rep.warning_count == 0
    assert rep.p0_failures == ()
    assert rep.p1_failures == ()
    # Empty scenario set is NOT a successful run, so the next allowed
    # phase remains the remediation-required string.
    assert rep.next_allowed_phase == NEXT_ALLOWED_PHASE_WITH_BLOCKERS


# ---------------------------------------------------------------------------
# Extra: P0 failure -> overall status FAIL and next_allowed_phase
#        flips to remediation-required
# ---------------------------------------------------------------------------


def test_p0_failure_flips_overall_status_and_next_allowed_phase():
    bad_scenario = SafetyMatrixScenario(
        scenario_id="sm_synthetic_p0_failure",
        scenario_type=SafetyMatrixScenarioType.STOP_FAILED,
        description="synthetic P0 failure",
        simulated_inputs={"is_paper": True},
        expected_actions=(
            # The decision table for STOP_FAILED does NOT include
            # PAPER_LEDGER_ONLY, so this synthetic scenario will fail.
            SafetyMatrixExpectedAction.PAPER_LEDGER_ONLY,
        ),
        severity=SafetyMatrixSeverity.P0,
    )
    eng = SafetyMatrixEngine()
    rep = eng.build_report(
        reference_window="60d",
        scenarios=[bad_scenario],
        now_utc=_FIXED_NOW,
    )
    assert rep.failed_count == 1
    assert rep.status == SafetyMatrixResultStatus.FAIL
    assert "sm_synthetic_p0_failure" in rep.p0_failures
    assert rep.next_allowed_phase == NEXT_ALLOWED_PHASE_WITH_BLOCKERS
    # Even on FAIL, the safety flags must remain pinned at False / True.
    rd = rep.to_dict()
    assert rd["live_trading"] is False
    assert rd["exchange_live_orders"] is False
    assert rd["binance_private_api_enabled"] is False
    assert rd["telegram_outbound_enabled"] is False
    assert rd["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# Extra: runner produces files; events restricted to allowed set;
#        deterministic byte-identical re-run with fixed clock
# ---------------------------------------------------------------------------


def test_runner_writes_files_and_emits_only_allowed_events(tmp_path):
    from scripts import run_risk_execution_capital_safety_matrix as runner

    payload = runner.run(
        output_dir=str(tmp_path),
        reference_window="60d",
        scenario_set="default",
        now_utc=_FIXED_NOW,
    )
    json_path = (
        tmp_path / "risk_execution_capital_safety_matrix_report.json"
    )
    md_path = tmp_path / "risk_execution_capital_safety_matrix_report.md"
    assert json_path.is_file()
    assert md_path.is_file()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    # Events emitted include exactly the allowed types.
    event_types = {e["event_type"] for e in on_disk.get("events", [])}
    assert event_types <= SafetyMatrixEvent.ALLOWED
    assert (
        SafetyMatrixEvent.SAFETY_MATRIX_REPORT_GENERATED in event_types
    )
    assert (
        SafetyMatrixEvent.SAFETY_MATRIX_SCENARIO_EVALUATED
        in event_types
    )
    # No forbidden field anywhere on disk.
    keys = set(_walk_keys(on_disk))
    assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
    # JSON is byte-identical on a second run with the same fixed clock.
    second = runner.run(
        output_dir=str(tmp_path),
        reference_window="60d",
        scenario_set="default",
        now_utc=_FIXED_NOW,
    )
    assert second["report_id"] == payload["report_id"]
    assert json_path.read_bytes() == json.dumps(
        on_disk, indent=2, sort_keys=True, default=str
    ).encode("utf-8") + b"\n"
    # next_allowed_phase MUST be the design-checkpoint string for the
    # default scenario set.
    assert (
        on_disk["next_allowed_phase"]
        == NEXT_ALLOWED_PHASE_NO_BLOCKERS
    )


# ---------------------------------------------------------------------------
# Extra: runner rejects unsupported scenario_set values
# ---------------------------------------------------------------------------


def test_runner_rejects_unsupported_scenario_set(tmp_path):
    from scripts import run_risk_execution_capital_safety_matrix as runner

    with pytest.raises(ValueError):
        runner.run(
            output_dir=str(tmp_path),
            reference_window="60d",
            scenario_set="custom",  # not allowed in this phase
            now_utc=_FIXED_NOW,
        )


# ---------------------------------------------------------------------------
# Extra: each result status value lives in the closed enum
# ---------------------------------------------------------------------------


def test_result_status_closed_enum():
    forbidden_statuses = {
        "ACCEPTED",
        "TRADE",
        "BUY",
        "SELL",
        "GO_LIVE",
        "ENABLE_LIVE",
        "APPLY",
        "DEPLOY",
    }
    assert SafetyMatrixResultStatus.ALLOWED.isdisjoint(
        forbidden_statuses
    )
    rep = _build_default_report()
    for r in rep.scenario_results:
        assert r.status in SafetyMatrixResultStatus.ALLOWED
        assert r.status not in forbidden_statuses


# ---------------------------------------------------------------------------
# Extra: SafetyMatrixExpectedAction.ALLOWED never includes trade-action
#        verbs
# ---------------------------------------------------------------------------


def test_expected_actions_never_include_trade_verbs():
    forbidden_actions = {
        "APPLY",
        "DEPLOY",
        "ENABLE_LIVE",
        "GO_LIVE",
        "AUTO_APPLY",
        "BUY",
        "SELL",
        "OPEN_POSITION",
        "CLOSE_POSITION",
        "PLACE_ORDER",
        "SUBMIT_ORDER",
    }
    assert SafetyMatrixExpectedAction.ALLOWED.isdisjoint(
        forbidden_actions
    )
