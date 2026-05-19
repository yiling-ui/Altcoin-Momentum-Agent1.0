"""Phase 10B - ReflectionResult / ReflectionInput / quality enums tests
(Issue #10 Part 2).

Pin the field set on :class:`ReflectionResult` and confirm the value
objects are frozen + JSON-safe.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from app.reflection.models import (
    QualityScore,
    ReflectionInput,
    ReflectionResult,
    TradeOutcome,
    UnknownReason,
)
from app.reflection.tags import MistakeTag


def _build_minimal_result() -> ReflectionResult:
    return ReflectionResult(
        opportunity_id="opp_x",
        client_order_id="coid_x",
        symbol="PEPEUSDT",
        setup="breakout_momentum",
        result=TradeOutcome.WIN,
        mistake_tags=(MistakeTag.STOP_NOT_CONFIRMED,),
        mfe=12.5,
        mae=3.5,
        tail_contribution=0.0,
        entry_quality=QualityScore.MEDIUM,
        exit_quality=QualityScore.HIGH,
        risk_process_quality=QualityScore.HIGH,
        execution_quality=QualityScore.HIGH,
        data_quality_notes=(),
        source_event_ids=("e1", "e2", "e3"),
        learning_ready=None,
    )


# ---------------------------------------------------------------------------
# Field set
# ---------------------------------------------------------------------------
def test_reflection_result_field_set_pinned():
    """The Issue #10 Part 10B contract pins this exact field set."""
    expected = {
        "opportunity_id",
        "client_order_id",
        "symbol",
        "setup",
        "result",
        "mistake_tags",
        "mfe",
        "mae",
        "tail_contribution",
        "entry_quality",
        "exit_quality",
        "risk_process_quality",
        "execution_quality",
        "data_quality_notes",
        "source_event_ids",
        "learning_ready",
        "generated_at",
    }
    actual = {f.name for f in dataclasses.fields(ReflectionResult)}
    assert actual == expected


def test_reflection_result_to_payload_round_trips_through_json():
    result = _build_minimal_result()
    payload = result.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)
    # Every value MUST be JSON-stable.
    assert decoded["opportunity_id"] == "opp_x"
    assert decoded["mfe"] == 12.5
    assert decoded["mae"] == 3.5
    assert decoded["tail_contribution"] == 0.0
    assert decoded["mistake_tags"] == ["stop_not_confirmed"]
    assert decoded["result"] == "win"
    assert decoded["entry_quality"] == "medium"
    assert decoded["exit_quality"] == "high"
    assert decoded["risk_process_quality"] == "high"
    assert decoded["execution_quality"] == "high"
    assert decoded["data_quality_notes"] == []
    assert decoded["source_event_ids"] == ["e1", "e2", "e3"]
    assert decoded["learning_ready_present"] is False


def test_reflection_result_to_payload_renders_none_metrics():
    result = ReflectionResult(
        opportunity_id=None,
        client_order_id=None,
        symbol=None,
        setup="unknown",
        result=TradeOutcome.UNKNOWN,
        mistake_tags=(),
        mfe=None,
        mae=None,
        tail_contribution=None,
        entry_quality=QualityScore.UNKNOWN,
        exit_quality=QualityScore.UNKNOWN,
        risk_process_quality=QualityScore.UNKNOWN,
        execution_quality=QualityScore.UNKNOWN,
        data_quality_notes=(UnknownReason.NO_LIFECYCLE_EVENTS,),
        source_event_ids=(),
        learning_ready=None,
    )
    payload = result.to_payload()
    assert payload["mfe"] is None
    assert payload["mae"] is None
    assert payload["tail_contribution"] is None
    assert payload["data_quality_notes"] == ["no_lifecycle_events"]


def test_reflection_result_is_frozen():
    """Frozen dataclass: re-assignment raises FrozenInstanceError."""
    result = _build_minimal_result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.opportunity_id = "x"  # type: ignore[misc]


def test_mistake_tag_values_helper_returns_strings():
    result = _build_minimal_result()
    assert result.mistake_tag_values == ("stop_not_confirmed",)


def test_has_data_quality_notes_helper():
    clean = _build_minimal_result()
    assert clean.has_data_quality_notes is False
    flagged = dataclasses.replace(
        clean, data_quality_notes=(UnknownReason.NO_FILL_RECORDED,)
    )
    assert flagged.has_data_quality_notes is True


def test_quality_score_vocabulary_pinned():
    assert {s.value for s in QualityScore} == {
        "high",
        "medium",
        "low",
        "unknown",
    }


def test_trade_outcome_vocabulary_pinned():
    assert {t.value for t in TradeOutcome} == {
        "win",
        "loss",
        "breakeven",
        "protected",
        "open",
        "unknown",
    }


def test_unknown_reason_vocabulary_pinned():
    """The UnknownReason vocabulary is the only admissible "we don't
    know" labels - the engine NEVER invents a free-form reason."""
    expected = {
        "insufficient_price_path",
        "no_fill_recorded",
        "no_virtual_trade_plan",
        "no_signal_snapshot",
        "no_right_tail_amplify_lifecycle",
        "no_opportunity_id",
        "no_lifecycle_events",
        "no_realised_pnl",
        "no_risk_decision_trail",
        "no_state_transition_trail",
        "no_config_versions",
    }
    assert {r.value for r in UnknownReason} == expected


def test_reflection_input_is_frozen():
    inp = ReflectionInput(paper_trade=object())
    with pytest.raises(dataclasses.FrozenInstanceError):
        inp.paper_trade = object()  # type: ignore[misc]


def test_reflection_input_defaults_are_safe():
    inp = ReflectionInput(paper_trade=object())
    assert inp.risk_decisions == ()
    assert inp.state_transitions is None
    assert inp.incidents == ()
    assert inp.learning_ready is None
