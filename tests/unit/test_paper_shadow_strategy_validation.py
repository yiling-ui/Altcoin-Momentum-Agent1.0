"""Unit tests for Phase 11C.1D-B / Paper Shadow Strategy Validation v0.

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
from typing import Any, Dict, List, Mapping

import pytest

from app.paper_shadow import (
    FORBIDDEN_OUTPUT_FIELDS,
    NEXT_ALLOWED_PHASE,
    PHASE_NAME,
    SAFETY_CONTRACT,
    PaperShadowCohortEvaluation,
    PaperShadowCohortKey,
    PaperShadowEvent,
    PaperShadowSample,
    PaperShadowStrategyValidationEngine,
    PaperShadowStrategyValidationReport,
    PaperShadowValidationStatus,
    RecommendationLevel,
    assert_no_forbidden_fields,
    build_samples_from_reports,
    example_fixture_samples,
    render_report_markdown,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _walk_keys(payload: Any):
    """Yield all keys appearing in a nested mapping/list payload."""
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


def _promising_cohort_key() -> PaperShadowCohortKey:
    return PaperShadowCohortKey(
        market_regime="trend",
        cluster_id="cluster_alpha",
        leader_vs_follower="leader",
        candidate_stage="EARLY",
        strategy_mode="continuation",
        opportunity_score_bucket="high",
        early_tail_score_bucket="high",
        post_discovery_outcome_label="EARLY_CONTINUATION",
        reject_attribution_verdict="not_rejected",
        severe_miss_root_cause="none",
        discovery_quality_bucket="high",
    )


def _risky_cohort_key() -> PaperShadowCohortKey:
    return PaperShadowCohortKey(
        market_regime="range",
        cluster_id="cluster_beta",
        leader_vs_follower="follower",
        candidate_stage="LATE",
        strategy_mode="breakout",
        opportunity_score_bucket="medium",
        early_tail_score_bucket="low",
        post_discovery_outcome_label="LATE_TOP_CHASE",
        reject_attribution_verdict="reject_correct",
        severe_miss_root_cause="early_tail_score_too_high",
        discovery_quality_bucket="low",
    )


def _data_gap_cohort_key() -> PaperShadowCohortKey:
    return PaperShadowCohortKey(
        market_regime="chop",
        cluster_id="cluster_delta",
        leader_vs_follower="follower",
        candidate_stage="EARLY",
        strategy_mode="reversion",
        opportunity_score_bucket="low",
        early_tail_score_bucket="low",
        post_discovery_outcome_label="INSUFFICIENT_PRICE_PATH",
        reject_attribution_verdict="not_rejected",
        severe_miss_root_cause="data_gap",
        discovery_quality_bucket="low",
    )


def _make_sample(
    sid: str,
    cohort: PaperShadowCohortKey,
    *,
    late_chase: bool = False,
    fake_breakout: bool = False,
    severe_miss: bool = False,
    false_negative_reject: bool = False,
    data_gap: bool = False,
    mfe: float | None = 0.03,
    mae: float | None = 0.012,
) -> PaperShadowSample:
    return PaperShadowSample(
        sample_id=sid,
        symbol="ABCUSDT",
        reference_window="60d",
        first_seen_time_utc="2026-04-01T00:00:00+00:00",
        cohort_key=cohort,
        post_seen_mfe_pct=mfe,
        post_seen_mae_pct=mae,
        remaining_upside_to_peak_pct=(mfe + 0.02) if mfe is not None else None,
        late_chase=late_chase,
        fake_breakout=fake_breakout,
        severe_miss=severe_miss,
        false_negative_reject=false_negative_reject,
        data_gap=data_gap,
        evidence_refs=("phase_11c_1d_b_v0",),
        source="operator_supplied",
    )


# ---------------------------------------------------------------------------
# 1. builds samples from structured outcome inputs
# ---------------------------------------------------------------------------


def test_builds_samples_from_structured_outcome_inputs():
    block_b = {
        "report_id": "block_b_xyz",
        "post_discovery_outcome_records": [
            {
                "sample_id": "s_b_001",
                "symbol": "AAA",
                "first_seen_time_utc": "2026-04-01T00:00:00+00:00",
                "market_regime": "trend",
                "cluster_id": "cluster_alpha",
                "leader_vs_follower": "leader",
                "candidate_stage": "EARLY",
                "strategy_mode": "continuation",
                "opportunity_score": 0.82,
                "early_tail_score": 0.75,
                "post_discovery_outcome_label": "EARLY_CONTINUATION",
                "reject_attribution_verdict": "not_rejected",
                "severe_miss_root_cause": "none",
                "discovery_quality_bucket": "high",
                "post_seen_mfe_pct": 0.05,
                "post_seen_mae_pct": 0.01,
                "remaining_upside_to_peak_pct": 0.07,
                "late_chase": False,
                "fake_breakout": False,
                "severe_miss": False,
                "false_negative_reject": False,
                "data_gap": False,
            }
        ],
    }
    block_c = {
        "report_id": "block_c_xyz",
        "severe_miss_records": [
            {
                "sample_id": "s_c_001",
                "symbol": "BBB",
                "first_seen_time_utc": "2026-04-02T00:00:00+00:00",
                "market_regime": "range",
                "cluster_id": "cluster_beta",
                "leader_vs_follower": "follower",
                "candidate_stage": "LATE",
                "strategy_mode": "breakout",
                "opportunity_score_bucket": "medium",
                "early_tail_score_bucket": "low",
                "post_discovery_outcome_label": "LATE_TOP_CHASE",
                "reject_attribution_verdict": "reject_correct",
                "severe_miss_root_cause": "early_tail_score_too_high",
                "discovery_quality_bucket": "low",
                "post_seen_mfe_pct": 0.005,
                "post_seen_mae_pct": 0.04,
                "late_chase": True,
                "fake_breakout": True,
                "severe_miss": True,
            }
        ],
    }
    samples = build_samples_from_reports(
        block_b_report=block_b,
        block_c_report=block_c,
        rule_sandbox_report=None,
        reference_window="60d",
    )
    assert len(samples) == 2
    by_id = {s.sample_id: s for s in samples}
    assert "s_b_001" in by_id
    assert "s_c_001" in by_id
    s = by_id["s_b_001"]
    # opportunity_score 0.82 -> "very_high"
    assert s.cohort_key.opportunity_score_bucket == "very_high"
    # early_tail_score 0.75 -> "high"
    assert s.cohort_key.early_tail_score_bucket == "high"
    assert s.cohort_key.market_regime == "trend"
    assert s.symbol == "AAA"
    assert s.post_seen_mfe_pct == 0.05
    # evidence_refs include the source report id
    assert "block_b:block_b_xyz" in s.evidence_refs
    s2 = by_id["s_c_001"]
    assert s2.severe_miss is True
    assert s2.fake_breakout is True
    assert s2.late_chase is True
    assert s2.cohort_key.severe_miss_root_cause == "early_tail_score_too_high"
    assert "block_c:block_c_xyz" in s2.evidence_refs


# ---------------------------------------------------------------------------
# 2. cohort grouping deterministic
# ---------------------------------------------------------------------------


def test_cohort_grouping_deterministic():
    cohort_p = _promising_cohort_key()
    cohort_r = _risky_cohort_key()
    samples_a = [
        _make_sample("s2", cohort_p),
        _make_sample("s1", cohort_p),
        _make_sample("s3", cohort_r, severe_miss=True),
    ]
    samples_b = [
        _make_sample("s3", cohort_r, severe_miss=True),
        _make_sample("s1", cohort_p),
        _make_sample("s2", cohort_p),
    ]
    eng = PaperShadowStrategyValidationEngine()
    g_a = eng.group_into_cohorts(samples_a)
    g_b = eng.group_into_cohorts(samples_b)
    # Order of cohorts is identical regardless of input order.
    assert list(g_a.keys()) == list(g_b.keys())
    # Order of samples within each cohort is identical too.
    for k in g_a:
        ids_a = [s.sample_id for s in g_a[k]]
        ids_b = [s.sample_id for s in g_b[k]]
        assert ids_a == ids_b
    # cohort_id is stable.
    assert cohort_p.cohort_id() == cohort_p.cohort_id()
    # Different cohorts produce different cohort_ids.
    assert cohort_p.cohort_id() != cohort_r.cohort_id()


# ---------------------------------------------------------------------------
# 3. low sample count -> INCONCLUSIVE
# ---------------------------------------------------------------------------


def test_low_sample_count_inconclusive():
    cohort = _promising_cohort_key()
    eng = PaperShadowStrategyValidationEngine()
    samples = [_make_sample(f"s{i}", cohort) for i in range(2)]
    rep = eng.build_report(
        reference_window="60d",
        samples=samples,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert len(rep.cohort_evaluations) == 1
    e = rep.cohort_evaluations[0]
    assert e.sample_count == 2
    assert e.recommendation_level == RecommendationLevel.INCONCLUSIVE
    assert e.cohort_id in rep.inconclusive_cohorts
    assert e.cohort_id not in rep.promising_cohorts


# ---------------------------------------------------------------------------
# 4. high data gap -> INCONCLUSIVE / RISKY
# ---------------------------------------------------------------------------


def test_high_data_gap_inconclusive_or_risky():
    cohort = _data_gap_cohort_key()
    eng = PaperShadowStrategyValidationEngine()

    # Case A: data_gap_rate ~0.40 -> INCONCLUSIVE.
    samples_a = [
        _make_sample(f"a{i}", cohort, data_gap=(i < 4))
        for i in range(10)
    ]
    rep_a = eng.build_report(
        reference_window="60d",
        samples=samples_a,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    e_a = rep_a.cohort_evaluations[0]
    assert e_a.data_gap_rate == pytest.approx(0.40)
    assert e_a.recommendation_level == RecommendationLevel.INCONCLUSIVE

    # Case B: data_gap_rate >= 0.50 -> RISKY.
    samples_b = [
        _make_sample(f"b{i}", cohort, data_gap=(i < 7))
        for i in range(10)
    ]
    rep_b = eng.build_report(
        reference_window="60d",
        samples=samples_b,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    e_b = rep_b.cohort_evaluations[0]
    assert e_b.data_gap_rate >= 0.50
    assert e_b.recommendation_level == RecommendationLevel.RISKY

    # Both rejections must remain in the allowed taxonomy.
    assert e_a.recommendation_level in RecommendationLevel.ALLOWED
    assert e_b.recommendation_level in RecommendationLevel.ALLOWED


# ---------------------------------------------------------------------------
# 5. promising cohort -> PROMISING_FOR_FORWARD_TEST
# ---------------------------------------------------------------------------


def test_promising_cohort_yields_promising_for_forward_test():
    cohort = _promising_cohort_key()
    samples = [_make_sample(f"p{i:02d}", cohort) for i in range(12)]
    eng = PaperShadowStrategyValidationEngine()
    rep = eng.build_report(
        reference_window="60d",
        samples=samples,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    e = rep.cohort_evaluations[0]
    assert e.sample_count == 12
    assert e.usable_discovery_rate == pytest.approx(1.0)
    assert e.severe_miss_rate == pytest.approx(0.0)
    assert e.fake_breakout_rate == pytest.approx(0.0)
    assert e.recommendation_level == RecommendationLevel.PROMISING_FOR_FORWARD_TEST
    assert e.cohort_id in rep.promising_cohorts


# ---------------------------------------------------------------------------
# 6. severe miss / fake breakout heavy cohort -> RISKY or REJECTED_BY_EVIDENCE
# ---------------------------------------------------------------------------


def test_severe_miss_or_fake_breakout_heavy_cohort_risky_or_rejected():
    cohort = _risky_cohort_key()
    eng = PaperShadowStrategyValidationEngine()

    # Severe miss heavy (rate ~0.40, between HIGH=0.30 and REJECT=0.50)
    # -> RISKY.
    samples_risky = [
        _make_sample(
            f"r{i}",
            cohort,
            severe_miss=(i < 4),
        )
        for i in range(10)
    ]
    rep_risky = eng.build_report(
        reference_window="60d",
        samples=samples_risky,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    e_risky = rep_risky.cohort_evaluations[0]
    assert e_risky.severe_miss_rate == pytest.approx(0.40)
    assert e_risky.recommendation_level == RecommendationLevel.RISKY

    # Fake breakout catastrophic (>=0.50) -> REJECTED_BY_EVIDENCE.
    samples_rejected = [
        _make_sample(
            f"x{i}",
            cohort,
            fake_breakout=(i < 6),
        )
        for i in range(10)
    ]
    rep_rejected = eng.build_report(
        reference_window="60d",
        samples=samples_rejected,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    e_rej = rep_rejected.cohort_evaluations[0]
    assert e_rej.fake_breakout_rate >= 0.50
    assert e_rej.recommendation_level == RecommendationLevel.REJECTED_BY_EVIDENCE


# ---------------------------------------------------------------------------
# 7. recommendation_level never APPLY / DEPLOY / TRADE / BUY / SELL
# ---------------------------------------------------------------------------


def test_recommendation_level_never_apply_deploy_trade_buy_sell():
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
    # Sweep many shapes; none should escape ALLOWED.
    eng = PaperShadowStrategyValidationEngine()
    cohort = _promising_cohort_key()
    cohort_r = _risky_cohort_key()
    cohort_d = _data_gap_cohort_key()
    sample_sets = [
        [_make_sample(f"a{i}", cohort) for i in range(12)],
        [_make_sample(f"b{i}", cohort_r, severe_miss=(i < 6)) for i in range(10)],
        [_make_sample(f"c{i}", cohort_d, data_gap=(i < 7)) for i in range(10)],
        [_make_sample(f"d{i}", cohort) for i in range(2)],
        [_make_sample(f"e{i}", cohort, late_chase=(i < 5)) for i in range(10)],
    ]
    for samples in sample_sets:
        rep = eng.build_report(
            reference_window="60d",
            samples=samples,
            now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
        )
        for e in rep.cohort_evaluations:
            assert e.recommendation_level in RecommendationLevel.ALLOWED
            assert e.recommendation_level not in forbidden_levels
    # The dataclass also rejects illegal recommendation levels.
    with pytest.raises(ValueError):
        PaperShadowCohortEvaluation(
            cohort_id="c_x",
            cohort_key=cohort,
            sample_count=10,
            usable_discovery_rate=0.5,
            median_mfe_pct=0.01,
            median_mae_pct=0.01,
            late_chase_rate=0.0,
            fake_breakout_rate=0.0,
            severe_miss_rate=0.0,
            false_negative_reject_rate=0.0,
            data_gap_rate=0.0,
            confidence_bucket="medium",
            quality_bucket="medium",
            recommendation_level="APPLY",  # forbidden
        )


# ---------------------------------------------------------------------------
# 8. auto_tuning_allowed=false
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false():
    eng = PaperShadowStrategyValidationEngine()
    assert eng.auto_tuning_allowed is False
    rep = eng.build_report(
        reference_window="60d",
        samples=example_fixture_samples(),
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    d = rep.to_dict()
    assert d["auto_tuning_allowed"] is False
    assert SAFETY_CONTRACT["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 9. writes_runtime_config=false
# ---------------------------------------------------------------------------


def test_writes_runtime_config_false():
    eng = PaperShadowStrategyValidationEngine()
    assert eng.writes_runtime_config is False
    rep = eng.build_report(
        reference_window="60d",
        samples=example_fixture_samples(),
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    d = rep.to_dict()
    assert d["writes_runtime_config"] is False
    assert SAFETY_CONTRACT["writes_runtime_config"] is False


# ---------------------------------------------------------------------------
# 10. trade_authority=false
# ---------------------------------------------------------------------------


def test_trade_authority_false():
    eng = PaperShadowStrategyValidationEngine()
    assert eng.trade_authority is False
    rep = eng.build_report(
        reference_window="60d",
        samples=example_fixture_samples(),
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    d = rep.to_dict()
    assert d["trade_authority"] is False
    assert SAFETY_CONTRACT["trade_authority"] is False


# ---------------------------------------------------------------------------
# 11. phase_12_forbidden=true
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_true():
    eng = PaperShadowStrategyValidationEngine()
    assert eng.phase_12_forbidden is True
    rep = eng.build_report(
        reference_window="60d",
        samples=example_fixture_samples(),
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    d = rep.to_dict()
    assert d["phase_12_forbidden"] is True
    assert d["next_allowed_phase"] == NEXT_ALLOWED_PHASE
    assert "Phase 12" not in d["next_allowed_phase"]
    assert SAFETY_CONTRACT["phase_12_forbidden"] is True
    # Live-trading-shaped flags are also pinned.
    assert d["live_trading"] is False
    assert d["exchange_live_orders"] is False
    assert d["right_tail"] is False
    assert d["llm"] is False
    assert d["llm_outbound_enabled"] is False
    assert d["telegram_outbound_enabled"] is False
    assert d["binance_private_api_enabled"] is False
    assert d["sandbox_only"] is True


# ---------------------------------------------------------------------------
# 12. forbidden fields absent
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_in_all_outputs():
    eng = PaperShadowStrategyValidationEngine()
    samples = example_fixture_samples()
    rep = eng.build_report(
        reference_window="60d",
        samples=samples,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    payload = rep.to_dict()
    assert_no_forbidden_fields(payload)
    keys = set(_walk_keys(payload))
    assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
    # Sample dicts must also be clean.
    for s in samples:
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


# ---------------------------------------------------------------------------
# 13. runner does not import app.risk / app.execution / app.exchanges /
#     app.telegram / app.config
# ---------------------------------------------------------------------------


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


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_runner_does_not_import_forbidden_modules():
    root = _project_root()
    runner_path = root / "scripts" / "run_paper_shadow_strategy_validation.py"
    engine_path = root / "app" / "paper_shadow" / "strategy_validation.py"
    init_path = root / "app" / "paper_shadow" / "__init__.py"

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
        "_paper_shadow_runner_under_test_phase11c_1d_b", runner_path
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
# 14. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------


def test_no_deepseek_or_llm_or_network_path():
    root = _project_root()
    files = [
        root / "app" / "paper_shadow" / "strategy_validation.py",
        root / "app" / "paper_shadow" / "__init__.py",
        root / "scripts" / "run_paper_shadow_strategy_validation.py",
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
    # these are safety-flag declarations and string-key references on
    # the report payload, NOT network call paths. Each is False by
    # construction (see SAFETY_CONTRACT) and exists precisely to make
    # the safety boundary visible.
    safety_flag_idents = {
        "telegram_outbound_enabled",
        "binance_private_api_enabled",
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
    importlib.import_module("app.paper_shadow.strategy_validation")
    new = set(sys.modules) - pre
    for nm in new:
        low = nm.lower()
        for bad in forbidden_module_prefixes:
            assert not low.startswith(bad), f"unexpected import: {nm}"


# ---------------------------------------------------------------------------
# 15. JSON output serializable
# ---------------------------------------------------------------------------


def test_json_output_serializable():
    eng = PaperShadowStrategyValidationEngine()
    rep = eng.build_report(
        reference_window="60d",
        samples=example_fixture_samples(),
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    payload = rep.to_dict()
    # Must round-trip through JSON cleanly without ``default=str``.
    s = json.dumps(payload, sort_keys=True)
    back = json.loads(s)
    assert back["report_id"] == rep.report_id
    assert back["phase_12_forbidden"] is True
    assert back["next_allowed_phase"] == NEXT_ALLOWED_PHASE
    assert isinstance(back["cohort_evaluations"], list)
    # Cohort evaluations are serializable too.
    for ce in back["cohort_evaluations"]:
        assert "cohort_id" in ce
        assert "cohort_key" in ce
        assert "recommendation_level" in ce
        assert ce["recommendation_level"] in RecommendationLevel.ALLOWED


# ---------------------------------------------------------------------------
# 16. deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output():
    fixed_now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    eng1 = PaperShadowStrategyValidationEngine()
    eng2 = PaperShadowStrategyValidationEngine()
    samples_1 = example_fixture_samples()
    samples_2 = example_fixture_samples()
    r1 = eng1.build_report(
        reference_window="60d", samples=samples_1, now_utc=fixed_now
    )
    r2 = eng2.build_report(
        reference_window="60d", samples=samples_2, now_utc=fixed_now
    )
    p1 = json.dumps(r1.to_dict(), sort_keys=True)
    p2 = json.dumps(r2.to_dict(), sort_keys=True)
    assert p1 == p2
    assert r1.report_id == r2.report_id


# ---------------------------------------------------------------------------
# Extra: runner produces files; example fixture is labeled as such;
#        events are restricted to the allowed set
# ---------------------------------------------------------------------------


def test_runner_writes_files_and_marks_example_fixture(tmp_path):
    from scripts import run_paper_shadow_strategy_validation as runner

    payload = runner.run(
        block_b_report_path=None,
        block_c_report_path=None,
        rule_sandbox_report_path=None,
        output_dir=str(tmp_path),
        reference_window="60d",
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    json_path = tmp_path / "paper_shadow_strategy_validation_report.json"
    md_path = tmp_path / "paper_shadow_strategy_validation_report.md"
    assert json_path.is_file()
    assert md_path.is_file()
    # Example samples must declare source=example_fixture, never
    # "operator_supplied".
    assert payload["used_example_fixture"] is True
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    # Events emitted include exactly the allowed types.
    event_types = {e["event_type"] for e in on_disk.get("events", [])}
    assert event_types <= PaperShadowEvent.ALLOWED
    assert PaperShadowEvent.PAPER_SHADOW_REPORT_GENERATED in event_types
    assert PaperShadowEvent.PAPER_SHADOW_SAMPLE_CREATED in event_types
    assert PaperShadowEvent.PAPER_SHADOW_COHORT_EVALUATED in event_types
    # No forbidden field anywhere on disk.
    keys = set(_walk_keys(on_disk))
    assert keys.isdisjoint(FORBIDDEN_OUTPUT_FIELDS)
    # JSON is byte-identical on a second run with the same fixed clock.
    second = runner.run(
        block_b_report_path=None,
        block_c_report_path=None,
        rule_sandbox_report_path=None,
        output_dir=str(tmp_path),
        reference_window="60d",
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert second["report_id"] == payload["report_id"]
    assert json_path.read_bytes() == json.dumps(
        on_disk, indent=2, sort_keys=True, default=str
    ).encode("utf-8") + b"\n"


# ---------------------------------------------------------------------------
# Extra: example_fixture_samples produces all four verdict paths so the
#        runner output is illustrative
# ---------------------------------------------------------------------------


def test_example_fixture_exercises_all_recommendation_paths():
    eng = PaperShadowStrategyValidationEngine()
    samples = example_fixture_samples()
    # Every fixture sample must declare source=example_fixture.
    for s in samples:
        assert s.source == "example_fixture"
    rep = eng.build_report(
        reference_window="60d",
        samples=samples,
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    levels = {e.recommendation_level for e in rep.cohort_evaluations}
    # PROMISING / RISKY / REJECTED / INCONCLUSIVE all present.
    assert RecommendationLevel.PROMISING_FOR_FORWARD_TEST in levels
    assert RecommendationLevel.RISKY in levels
    assert RecommendationLevel.REJECTED_BY_EVIDENCE in levels
    assert RecommendationLevel.INCONCLUSIVE in levels
    # No forbidden levels ever escape.
    assert levels <= RecommendationLevel.ALLOWED


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
        "next_allowed_phase": NEXT_ALLOWED_PHASE,
    }
    assert SAFETY_CONTRACT == expected


# ---------------------------------------------------------------------------
# Extra: empty samples -> INSUFFICIENT_EVIDENCE status (paper-only safe)
# ---------------------------------------------------------------------------


def test_empty_samples_yields_insufficient_evidence_status():
    eng = PaperShadowStrategyValidationEngine()
    rep = eng.build_report(
        reference_window="60d",
        samples=[],
        now_utc=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert rep.status == PaperShadowValidationStatus.INSUFFICIENT_EVIDENCE
    assert rep.total_samples == 0
    assert rep.evaluated_cohort_count == 0
    assert rep.promising_cohorts == ()
    assert rep.rejected_cohorts == ()
    assert "no_samples_supplied" in rep.known_gaps


# ---------------------------------------------------------------------------
# Extra: build_samples_from_reports tolerates missing reports
# ---------------------------------------------------------------------------


def test_build_samples_from_reports_tolerates_missing_inputs():
    out = build_samples_from_reports(
        block_b_report=None,
        block_c_report=None,
        rule_sandbox_report=None,
        reference_window="60d",
    )
    assert out == []


# ---------------------------------------------------------------------------
# Extra: PaperShadowSample input validation
# ---------------------------------------------------------------------------


def test_paper_shadow_sample_rejects_bad_inputs():
    cohort = _promising_cohort_key()
    with pytest.raises(ValueError):
        PaperShadowSample(
            sample_id="",
            symbol="X",
            reference_window="60d",
            first_seen_time_utc="t",
            cohort_key=cohort,
        )
    with pytest.raises(ValueError):
        PaperShadowSample(
            sample_id="s1",
            symbol="",
            reference_window="60d",
            first_seen_time_utc="t",
            cohort_key=cohort,
        )
    with pytest.raises(ValueError):
        PaperShadowSample(
            sample_id="s1",
            symbol="X",
            reference_window="60d",
            first_seen_time_utc="t",
            cohort_key="not-a-cohort-key",  # type: ignore[arg-type]
        )
