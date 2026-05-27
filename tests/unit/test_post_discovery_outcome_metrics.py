"""Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0 unit tests.

Test plan (mirrors the brief's acceptance list):

  1. early continuation
  2. early but choppy
  3. late top chase
  4. late reversal
  5. missed strong tail
  6. fake breakout
  7. insufficient price path
  8. forbidden fields absent
  9. no parameter tuning
 10. no Risk / Execution / LLM / Telegram imports

The module is paper / report / evidence only. None of these tests
authorise a real trade or flip a Phase 1 safety flag.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.adaptive.post_discovery_outcome_metrics import (
    DetectionTimingLabel,
    HistoricalMoverReferenceSummary,
    OutcomeLabel,
    POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS,
    POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
    PostDiscoveryOutcomeEvaluator,
    PostDiscoveryOutcomeForbiddenFieldError,
    PostDiscoveryOutcomeInput,
    PostDiscoveryOutcomeRecord,
    PricePoint,
    assert_payload_has_no_forbidden_keys,
    build_post_discovery_outcome_report,
)
from app.core.events import EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms(day: int, hour: int = 0, minute: int = 0) -> int:
    """Return a deterministic UTC ms timestamp anchored at 2026-01-01."""

    base_ms = 1_767_225_600_000  # ~ 2026-01-01T00:00:00Z
    return (
        base_ms
        + (day * 24 * 60 * 60 * 1000)
        + (hour * 60 * 60 * 1000)
        + (minute * 60 * 1000)
    )


def _path(points: list[tuple[int, float]]) -> tuple[PricePoint, ...]:
    return tuple(
        PricePoint(timestamp_utc_ms=ts, price=price) for ts, price in points
    )


def _ref(
    *,
    symbol: str = "TESTUSDT",
    prior_high_price: float | None = 1.00,
    prior_high_time_ms: int | None = None,
    reference_peak_price: float | None = None,
    reference_peak_time_ms: int | None = None,
    max_window_gain_pct: float | None = 0.50,
) -> HistoricalMoverReferenceSummary:
    return HistoricalMoverReferenceSummary(
        symbol=symbol,
        reference_window="60D",
        mover_window_start_utc_ms=_ms(0),
        mover_window_end_utc_ms=_ms(7),
        prior_high_time_utc_ms=prior_high_time_ms or _ms(0, hour=23),
        prior_high_price=prior_high_price,
        reference_peak_price=reference_peak_price,
        reference_peak_time_utc_ms=reference_peak_time_ms,
        reference_max_window_gain_pct=max_window_gain_pct,
    )


# ---------------------------------------------------------------------------
# 1. Early continuation
# ---------------------------------------------------------------------------


def test_early_continuation_label() -> None:
    """First-seen well below peak; price keeps rising; outcome =
    EARLY_CONTINUATION."""

    first_seen_time = _ms(1, hour=2)
    inp = PostDiscoveryOutcomeInput(
        symbol="EARLYUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=first_seen_time,
        first_seen_event_type="ANOMALY_DETECTED",
        first_seen_price=1.00,
        price_path_after_first_seen=_path(
            [
                (_ms(1, hour=3), 1.05),
                (_ms(1, hour=4), 1.20),
                (_ms(1, hour=5), 1.40),
                (_ms(1, hour=6), 1.50),
            ]
        ),
        historical_mover_reference=_ref(
            reference_peak_price=1.50,
            reference_peak_time_ms=_ms(1, hour=6),
            max_window_gain_pct=0.50,
        ),
        capture_status="captured",
        capture_path_depth=5,
        evidence_refs=("audit:earlyusdt:1",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.detection_timing_label == DetectionTimingLabel.EARLY
    assert record.outcome_label == OutcomeLabel.EARLY_CONTINUATION
    assert record.remaining_upside_to_peak_pct is not None
    assert record.remaining_upside_to_peak_pct > 0.0
    assert record.mfe_pct is not None and record.mfe_pct > 0.0
    assert record.evidence_refs == ("audit:earlyusdt:1",)


# ---------------------------------------------------------------------------
# 2. Early but choppy
# ---------------------------------------------------------------------------


def test_early_but_choppy_label() -> None:
    """First-seen relatively early but mid-window draws down before
    peak; outcome = EARLY_BUT_CHOPPY."""

    first_seen_time = _ms(2, hour=1)
    inp = PostDiscoveryOutcomeInput(
        symbol="CHOPPYUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=first_seen_time,
        first_seen_event_type="ANOMALY_DETECTED",
        first_seen_price=1.00,
        price_path_after_first_seen=_path(
            [
                (_ms(2, hour=2), 1.04),
                (_ms(2, hour=3), 0.85),  # MAE = -15%
                (_ms(2, hour=4), 0.92),
                (_ms(2, hour=5), 1.10),
                (_ms(2, hour=6), 1.20),  # MFE = +20%
            ]
        ),
        historical_mover_reference=_ref(
            reference_peak_price=1.20,
            reference_peak_time_ms=_ms(2, hour=6),
            max_window_gain_pct=0.20,
        ),
        capture_status="captured",
        capture_path_depth=5,
        evidence_refs=("audit:choppyusdt:1",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.detection_timing_label == DetectionTimingLabel.EARLY_BUT_CHOPPY
    assert record.outcome_label == OutcomeLabel.EARLY_BUT_CHOPPY
    # Sanity: MAE significant relative to MFE.
    assert record.mae_pct is not None and record.mae_pct < 0.0
    assert record.mfe_pct is not None and record.mfe_pct > 0.0


# ---------------------------------------------------------------------------
# 3. Late top chase
# ---------------------------------------------------------------------------


def test_late_top_chase_label() -> None:
    """First-seen close to the reference peak; little upside
    remaining; some run; outcome = LATE_TOP_CHASE."""

    first_seen_time = _ms(3, hour=10)
    inp = PostDiscoveryOutcomeInput(
        symbol="LATEUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=first_seen_time,
        first_seen_event_type="ANOMALY_DETECTED",
        first_seen_price=1.45,
        price_path_after_first_seen=_path(
            [
                (_ms(3, hour=11), 1.46),
                (_ms(3, hour=12), 1.48),  # +2.07% MFE
                (_ms(3, hour=13), 1.47),
                (_ms(3, hour=14), 1.46),
            ]
        ),
        historical_mover_reference=_ref(
            reference_peak_price=1.50,  # only ~3.4% remaining
            reference_peak_time_ms=_ms(3, hour=12),
            max_window_gain_pct=0.50,
        ),
        capture_status="captured",
        capture_path_depth=5,
        evidence_refs=("audit:lateusdt:1",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.detection_timing_label == DetectionTimingLabel.LATE
    assert record.outcome_label == OutcomeLabel.LATE_TOP_CHASE
    assert record.remaining_upside_to_peak_pct is not None
    assert record.remaining_upside_to_peak_pct < 0.05


# ---------------------------------------------------------------------------
# 4. Late reversal
# ---------------------------------------------------------------------------


def test_late_reversal_label() -> None:
    """First-seen near peak; price reverses sharply; outcome =
    LATE_REVERSAL."""

    first_seen_time = _ms(4, hour=8)
    inp = PostDiscoveryOutcomeInput(
        symbol="LATEREVUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=first_seen_time,
        first_seen_event_type="ANOMALY_DETECTED",
        first_seen_price=1.50,
        price_path_after_first_seen=_path(
            [
                (_ms(4, hour=9), 1.51),  # tiny MFE
                (_ms(4, hour=10), 1.45),
                (_ms(4, hour=11), 1.30),  # MAE -13.3%
                (_ms(4, hour=12), 1.25),  # MAE -16.7%
            ]
        ),
        historical_mover_reference=_ref(
            reference_peak_price=1.51,  # essentially at peak
            reference_peak_time_ms=_ms(4, hour=9),
            max_window_gain_pct=0.50,
        ),
        capture_status="captured",
        capture_path_depth=5,
        evidence_refs=("audit:laterevusdt:1",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.detection_timing_label in (
        DetectionTimingLabel.LATE,
        DetectionTimingLabel.TOO_LATE,
    )
    assert record.outcome_label == OutcomeLabel.LATE_REVERSAL
    assert record.mae_pct is not None and record.mae_pct < 0.0


# ---------------------------------------------------------------------------
# 5. Missed strong tail
# ---------------------------------------------------------------------------


def test_missed_strong_tail_label() -> None:
    """capture_status=missed and reference recorded a strong tail;
    label = MISSED_STRONG_TAIL even when no price path is supplied."""

    inp = PostDiscoveryOutcomeInput(
        symbol="RAVEUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=None,
        first_seen_event_type=None,
        first_seen_price=None,
        price_path_after_first_seen=tuple(),
        historical_mover_reference=_ref(
            symbol="RAVEUSDT",
            prior_high_price=1.00,
            reference_peak_price=2.50,
            reference_peak_time_ms=_ms(5, hour=12),
            max_window_gain_pct=1.50,
        ),
        capture_status="missed",
        capture_path_depth=0,
        evidence_refs=("audit:raveusdt:miss",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.detection_timing_label == DetectionTimingLabel.MISSED
    assert record.outcome_label == OutcomeLabel.MISSED_STRONG_TAIL
    assert record.evidence_refs == ("audit:raveusdt:miss",)


def test_missed_strong_tail_with_first_seen_but_no_path() -> None:
    """Even when there is a first_seen_price recorded, a captured-then-
    missed reference with strong tail is MISSED_STRONG_TAIL when
    capture_status=missed."""

    inp = PostDiscoveryOutcomeInput(
        symbol="STOUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=_ms(6, hour=1),
        first_seen_event_type="MARKET_SNAPSHOT",
        first_seen_price=1.00,
        # provide a path long enough so insufficient-data does not fire,
        # but capture_status=missed still wins.
        price_path_after_first_seen=_path(
            [(_ms(6, hour=2), 1.02), (_ms(6, hour=3), 1.03)]
        ),
        historical_mover_reference=_ref(
            symbol="STOUSDT",
            reference_peak_price=2.00,
            reference_peak_time_ms=_ms(6, hour=10),
            max_window_gain_pct=1.00,
        ),
        capture_status="missed",
        capture_path_depth=1,
        evidence_refs=("audit:stousdt:miss",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)
    assert record.outcome_label == OutcomeLabel.MISSED_STRONG_TAIL
    assert record.detection_timing_label == DetectionTimingLabel.MISSED


# ---------------------------------------------------------------------------
# 6. Fake breakout
# ---------------------------------------------------------------------------


def test_fake_breakout_label() -> None:
    """First-seen early; price briefly makes a new high then gives
    back most of the gain; outcome = FAKE_BREAKOUT."""

    first_seen_time = _ms(7, hour=2)
    inp = PostDiscoveryOutcomeInput(
        symbol="FAKEUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=first_seen_time,
        first_seen_event_type="ANOMALY_DETECTED",
        first_seen_price=1.00,
        price_path_after_first_seen=_path(
            [
                (_ms(7, hour=3), 1.02),
                (_ms(7, hour=4), 1.20),  # high - +20%
                (_ms(7, hour=5), 1.10),
                (_ms(7, hour=6), 1.03),  # gave back ~85% of gain
            ]
        ),
        historical_mover_reference=_ref(
            reference_peak_price=1.25,
            reference_peak_time_ms=_ms(7, hour=4),
            max_window_gain_pct=0.25,
        ),
        capture_status="captured",
        capture_path_depth=5,
        evidence_refs=("audit:fakeusdt:1",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.outcome_label == OutcomeLabel.FAKE_BREAKOUT
    # The detection_timing_label should be EARLY (large remaining
    # upside relative to first_seen_price).
    assert record.detection_timing_label == DetectionTimingLabel.EARLY


# ---------------------------------------------------------------------------
# 7. Insufficient price path
# ---------------------------------------------------------------------------


def test_insufficient_price_path_no_first_seen_price() -> None:
    """Missing first_seen_price -> evaluator must NOT fabricate
    metrics; outcome = INSUFFICIENT_PRICE_PATH."""

    inp = PostDiscoveryOutcomeInput(
        symbol="NOFIRSTUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=_ms(8),
        first_seen_event_type="MARKET_SNAPSHOT",
        first_seen_price=None,
        price_path_after_first_seen=_path(
            [(_ms(8, hour=1), 1.05), (_ms(8, hour=2), 1.10)]
        ),
        historical_mover_reference=_ref(),
        capture_status="captured",
        capture_path_depth=1,
        evidence_refs=("audit:nofirstusdt:1",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.detection_timing_label == DetectionTimingLabel.INSUFFICIENT_DATA
    assert record.outcome_label == OutcomeLabel.INSUFFICIENT_PRICE_PATH
    assert record.mfe_pct is None
    assert record.mae_pct is None
    assert record.remaining_upside_to_peak_pct is None
    assert "missing_first_seen_price" in record.warnings


def test_insufficient_price_path_no_path_points() -> None:
    """No price-path points and not a missed strong tail -> outcome
    = INSUFFICIENT_PRICE_PATH (no fabrication)."""

    inp = PostDiscoveryOutcomeInput(
        symbol="NOPATHUSDT",
        reference_window="60D",
        first_seen_time_utc_ms=_ms(9),
        first_seen_event_type="MARKET_SNAPSHOT",
        first_seen_price=1.00,
        price_path_after_first_seen=tuple(),  # empty
        historical_mover_reference=_ref(max_window_gain_pct=0.05),
        capture_status="captured",
        capture_path_depth=1,
        evidence_refs=("audit:nopathusdt:1",),
    )

    record = PostDiscoveryOutcomeEvaluator().evaluate(inp)

    assert record.detection_timing_label == DetectionTimingLabel.INSUFFICIENT_DATA
    assert record.outcome_label == OutcomeLabel.INSUFFICIENT_PRICE_PATH
    assert record.mfe_pct is None
    assert record.remaining_upside_to_peak_pct is None
    assert "insufficient_price_path" in record.warnings


# ---------------------------------------------------------------------------
# 8. Forbidden fields absent
# ---------------------------------------------------------------------------


_FORBIDDEN_KEYS_REQUIRED = (
    "buy",
    "sell",
    "long",
    "short",
    "direction",
    "entry",
    "exit",
    "position_size",
    "leverage",
    "stop",
    "stop_loss",
    "target",
    "take_profit",
    "risk_budget",
    "order",
    "execution_command",
    "runtime_config_patch",
    "symbol_limit_patch",
    "threshold_patch",
    "candidate_pool_patch",
    "regime_weight_patch",
)


def test_forbidden_keys_set_covers_brief_keys() -> None:
    for key in _FORBIDDEN_KEYS_REQUIRED:
        assert key in POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS, (
            f"forbidden-keys set must contain '{key}' per the brief"
        )


def test_evaluator_payloads_contain_no_forbidden_keys() -> None:
    """All payloads emitted by the evaluator must have no forbidden
    keys recursively."""

    inputs = [
        PostDiscoveryOutcomeInput(
            symbol="EARLYUSDT",
            reference_window="60D",
            first_seen_time_utc_ms=_ms(1, hour=2),
            first_seen_event_type="ANOMALY_DETECTED",
            first_seen_price=1.00,
            price_path_after_first_seen=_path(
                [(_ms(1, hour=3), 1.10), (_ms(1, hour=4), 1.40)]
            ),
            historical_mover_reference=_ref(
                reference_peak_price=1.50,
                reference_peak_time_ms=_ms(1, hour=4),
                max_window_gain_pct=0.50,
            ),
            capture_status="captured",
            capture_path_depth=5,
            evidence_refs=("audit:earlyusdt:1",),
        ),
        PostDiscoveryOutcomeInput(
            symbol="RAVEUSDT",
            reference_window="60D",
            first_seen_time_utc_ms=None,
            first_seen_event_type=None,
            first_seen_price=None,
            price_path_after_first_seen=tuple(),
            historical_mover_reference=_ref(
                reference_peak_price=2.50,
                reference_peak_time_ms=_ms(5),
                max_window_gain_pct=1.50,
            ),
            capture_status="missed",
            capture_path_depth=0,
            evidence_refs=("audit:raveusdt:miss",),
        ),
    ]

    evaluator = PostDiscoveryOutcomeEvaluator()
    records = [evaluator.evaluate(i) for i in inputs]

    for record in records:
        payload = record.to_dict()
        for forbidden in _FORBIDDEN_KEYS_REQUIRED:
            assert forbidden not in payload

    report = build_post_discovery_outcome_report(records, reference_window="60D")
    report_payload = report.to_dict()
    for forbidden in _FORBIDDEN_KEYS_REQUIRED:
        assert forbidden not in report_payload
        assert forbidden not in report_payload.get("outcome_label_summary", {})
        assert forbidden not in report_payload.get(
            "detection_timing_label_summary", {}
        )


def test_assert_payload_has_no_forbidden_keys_raises_on_forbidden_key() -> None:
    payload = {
        "symbol": "X",
        "buy": True,  # forbidden
    }
    with pytest.raises(PostDiscoveryOutcomeForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(payload, context="test")


def test_assert_payload_has_no_forbidden_keys_recurses_into_nested() -> None:
    payload = {
        "symbol": "X",
        "nested": {
            "deeper": {"runtime_config_patch": {"foo": 1}},  # forbidden, nested
        },
    }
    with pytest.raises(PostDiscoveryOutcomeForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(payload, context="test")


# ---------------------------------------------------------------------------
# 9. No parameter tuning
# ---------------------------------------------------------------------------


def test_module_does_not_modify_runtime_parameters() -> None:
    """The module must NOT export any function or symbol whose name
    suggests modifying a runtime knob (symbol_limit, threshold,
    candidate_pool, regime weights)."""

    import app.adaptive.post_discovery_outcome_metrics as module

    forbidden_substrings = (
        "set_symbol_limit",
        "patch_symbol_limit",
        "update_symbol_limit",
        "set_threshold",
        "patch_threshold",
        "update_threshold",
        "set_candidate_pool",
        "patch_candidate_pool",
        "update_candidate_pool",
        "set_regime_weight",
        "patch_regime_weight",
        "update_regime_weight",
        "patch_runtime_config",
        "update_runtime_config",
    )
    public_names = [n for n in dir(module) if not n.startswith("_")]
    lowercased = {n.lower() for n in public_names}
    for substring in forbidden_substrings:
        for name in lowercased:
            assert substring not in name, (
                f"Post-Discovery Outcome Metrics module must not export "
                f"'{name}' (matches forbidden substring '{substring}')"
            )


def test_record_dataclass_is_frozen_so_no_runtime_mutation() -> None:
    """The output records are frozen dataclasses; nobody downstream
    can mutate label / metrics in place to feed back into runtime
    config."""

    record = PostDiscoveryOutcomeEvaluator().evaluate(
        PostDiscoveryOutcomeInput(
            symbol="EARLYUSDT",
            reference_window="60D",
            first_seen_time_utc_ms=_ms(1, hour=2),
            first_seen_event_type="ANOMALY_DETECTED",
            first_seen_price=1.00,
            price_path_after_first_seen=_path(
                [(_ms(1, hour=3), 1.10), (_ms(1, hour=4), 1.40)]
            ),
            historical_mover_reference=_ref(
                reference_peak_price=1.50,
                reference_peak_time_ms=_ms(1, hour=4),
                max_window_gain_pct=0.50,
            ),
            capture_status="captured",
            capture_path_depth=5,
            evidence_refs=("audit:earlyusdt:1",),
        )
    )

    with pytest.raises(Exception):
        record.outcome_label = OutcomeLabel.LATE_TOP_CHASE  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 10. No Risk / Execution / LLM / Telegram imports
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_PREFIXES = (
    "app.risk",
    "app.execution",
    "app.exchanges.binance",
    "app.llm",
    "app.telegram",
)


def _module_source_path() -> Path:
    import app.adaptive.post_discovery_outcome_metrics as module

    src_path = inspect.getsourcefile(module)
    assert src_path is not None
    return Path(src_path)


def _all_imports(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
    return imports


def test_module_does_not_import_forbidden_subsystems() -> None:
    imports = _all_imports(_module_source_path())
    for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
        for imp in imports:
            assert not imp.startswith(forbidden), (
                f"Post-Discovery Outcome Metrics module must not import "
                f"'{imp}' (forbidden prefix '{forbidden}')"
            )


def test_module_does_not_import_exchange_private_or_real_trade_layers() -> None:
    """Belt-and-suspenders: also forbid generic Binance private API,
    confirmation/real_trade, and live-order shaped names."""

    extra_forbidden = (
        "app.exchanges.binance",  # the live private gateway
        "app.confirmation.real_trade",
        "app.execution.fsm",
        "app.execution.lifecycle",
        "app.execution.paper_ledger",
    )
    imports = _all_imports(_module_source_path())
    for forbidden in extra_forbidden:
        for imp in imports:
            assert not imp.startswith(forbidden), (
                f"Post-Discovery Outcome Metrics module must not import "
                f"'{imp}'"
            )


# ---------------------------------------------------------------------------
# Extra invariants
# ---------------------------------------------------------------------------


def test_event_types_registered() -> None:
    """The two new EventTypes must be registered in app.core.events."""

    names = {member.name for member in EventType}
    assert "POST_DISCOVERY_OUTCOME_EVALUATED" in names
    assert "POST_DISCOVERY_OUTCOME_REPORT_GENERATED" in names


def test_record_carries_schema_version_and_evidence_refs() -> None:
    record = PostDiscoveryOutcomeEvaluator().evaluate(
        PostDiscoveryOutcomeInput(
            symbol="EARLYUSDT",
            reference_window="60D",
            first_seen_time_utc_ms=_ms(1, hour=2),
            first_seen_event_type="ANOMALY_DETECTED",
            first_seen_price=1.00,
            price_path_after_first_seen=_path(
                [(_ms(1, hour=3), 1.10), (_ms(1, hour=4), 1.40)]
            ),
            historical_mover_reference=_ref(
                reference_peak_price=1.50,
                reference_peak_time_ms=_ms(1, hour=4),
                max_window_gain_pct=0.50,
            ),
            capture_status="captured",
            capture_path_depth=5,
            evidence_refs=("audit:earlyusdt:1",),
        )
    )
    payload = record.to_dict()
    assert payload["schema_version"] == POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION
    assert payload["evidence_refs"] == ["audit:earlyusdt:1"]
    assert "source_phase" in payload


def test_report_aggregates_counts_and_medians() -> None:
    evaluator = PostDiscoveryOutcomeEvaluator()
    records = [
        evaluator.evaluate(
            PostDiscoveryOutcomeInput(
                symbol=f"SYM{idx}USDT",
                reference_window="60D",
                first_seen_time_utc_ms=_ms(10 + idx, hour=2),
                first_seen_event_type="ANOMALY_DETECTED",
                first_seen_price=1.00,
                price_path_after_first_seen=_path(
                    [
                        (_ms(10 + idx, hour=3), 1.10),
                        (_ms(10 + idx, hour=4), 1.40),
                    ]
                ),
                historical_mover_reference=_ref(
                    reference_peak_price=1.50,
                    reference_peak_time_ms=_ms(10 + idx, hour=4),
                    max_window_gain_pct=0.50,
                ),
                capture_status="captured",
                capture_path_depth=5,
                evidence_refs=(f"audit:sym{idx}:1",),
            )
        )
        for idx in range(3)
    ]
    # Add a missed strong tail.
    records.append(
        evaluator.evaluate(
            PostDiscoveryOutcomeInput(
                symbol="MISSED1USDT",
                reference_window="60D",
                first_seen_time_utc_ms=None,
                first_seen_event_type=None,
                first_seen_price=None,
                price_path_after_first_seen=tuple(),
                historical_mover_reference=_ref(
                    reference_peak_price=2.50,
                    reference_peak_time_ms=_ms(20),
                    max_window_gain_pct=1.50,
                ),
                capture_status="missed",
                capture_path_depth=0,
                evidence_refs=("audit:missed1:miss",),
            )
        )
    )
    # Add an insufficient one.
    records.append(
        evaluator.evaluate(
            PostDiscoveryOutcomeInput(
                symbol="NOPATHUSDT",
                reference_window="60D",
                first_seen_time_utc_ms=_ms(30),
                first_seen_event_type="MARKET_SNAPSHOT",
                first_seen_price=1.00,
                price_path_after_first_seen=tuple(),
                historical_mover_reference=_ref(max_window_gain_pct=0.05),
                capture_status="captured",
                capture_path_depth=1,
                evidence_refs=("audit:nopath:1",),
            )
        )
    )

    report = build_post_discovery_outcome_report(records, reference_window="60D")
    payload = report.to_dict()

    assert payload["total_records"] == 5
    assert payload["early_count"] == 3
    assert payload["missed_strong_tail_count"] == 1
    assert payload["insufficient_data_count"] == 1
    assert payload["median_remaining_upside_pct"] is not None
    assert payload["median_mfe_pct"] is not None
    # Records preserved.
    assert len(payload["records"]) == 5
    # Detection summary keys are valid labels.
    for key in payload["detection_timing_label_summary"]:
        assert key in DetectionTimingLabel.ALL
    for key in payload["outcome_label_summary"]:
        assert key in OutcomeLabel.ALL
