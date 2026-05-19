"""Phase 8.5 - SignalSnapshot serialisation contract tests (Issue #8.5)."""

from __future__ import annotations

import json

from app.core.enums import (
    ManipulationLevel,
    MarketRegime,
    OpportunityGrade,
    TradeConfirmationLevel,
)
from app.core.models import SignalSnapshot
from app.learning import (
    payload_to_signal_snapshot,
    signal_snapshot_to_payload,
)


def _make_snapshot() -> SignalSnapshot:
    return SignalSnapshot(
        symbol="PEPEUSDT",
        timestamp=1_700_000_000_000,
        regime=MarketRegime.MEME_RISK_ON,
        pre_anomaly_score=42.5,
        anomaly_score=63.0,
        liquidity_score=0.85,
        trade_confirmation_level=TradeConfirmationLevel.T3,
        manipulation_level=ManipulationLevel.M1,
        right_tail_score=12.0,
        opportunity_grade=OpportunityGrade.A,
        no_trade_reason=["macro_observe_only"],
    )


def test_signal_snapshot_payload_has_all_spec_11_2_fields():
    snap = _make_snapshot()
    payload = signal_snapshot_to_payload(snap)
    expected_keys = {
        "symbol",
        "timestamp",
        "regime",
        "pre_anomaly_score",
        "anomaly_score",
        "liquidity_score",
        "trade_confirmation_level",
        "manipulation_level",
        "right_tail_score",
        "opportunity_grade",
        "no_trade_reason",
    }
    assert set(payload.keys()) == expected_keys


def test_signal_snapshot_payload_renders_enums_as_strings():
    payload = signal_snapshot_to_payload(_make_snapshot())
    assert payload["regime"] == "MEME_RISK_ON"
    assert payload["trade_confirmation_level"] == "T3"
    assert payload["manipulation_level"] == "M1"
    assert payload["opportunity_grade"] == "A"


def test_signal_snapshot_payload_is_json_safe():
    payload = signal_snapshot_to_payload(_make_snapshot())
    # JSON round-trip must succeed without errors.
    text = json.dumps(payload, sort_keys=True)
    parsed = json.loads(text)
    assert parsed["pre_anomaly_score"] == 42.5
    assert parsed["no_trade_reason"] == ["macro_observe_only"]


def test_signal_snapshot_round_trip_preserves_fields():
    original = _make_snapshot()
    payload = signal_snapshot_to_payload(original)
    restored = payload_to_signal_snapshot(payload)
    # Pydantic equality covers every field.
    assert restored == original


def test_signal_snapshot_payload_to_round_trip_handles_defaults():
    minimal = SignalSnapshot(
        symbol="BTCUSDT",
        timestamp=0,
        regime=MarketRegime.ALT_RISK_OFF,
    )
    payload = signal_snapshot_to_payload(minimal)
    restored = payload_to_signal_snapshot(payload)
    assert restored.symbol == "BTCUSDT"
    assert restored.regime is MarketRegime.ALT_RISK_OFF
    assert restored.trade_confirmation_level is TradeConfirmationLevel.T0
    assert restored.manipulation_level is ManipulationLevel.M0
    assert restored.opportunity_grade is OpportunityGrade.D
    assert restored.no_trade_reason == []
