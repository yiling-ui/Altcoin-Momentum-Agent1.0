"""Phase 8.5 - EventRepository round-trip of learning-ready payloads
(Issue #8.5).

Acceptance criterion 6: "EventRepository 可以写入并读取
learning-ready payload."
"""

from __future__ import annotations

import json
import sqlite3

from app.core.enums import (
    AccountLifeTier,
    Direction,
    ManipulationLevel,
    MarketRegime,
    TradeConfirmationLevel,
)
from app.core.events import Event, EventType
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.learning import (
    LEARNING_READY_KEY,
    ConfigVersions,
    LearningReadyContext,
    OpportunityIdentity,
    RiskRejectedLearningPayload,
    VirtualTradePlan,
    attach_learning_ready,
)


def _open_repo() -> EventRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return EventRepository(conn)


def _full_context() -> LearningReadyContext:
    return LearningReadyContext(
        opportunity=OpportunityIdentity.create(
            symbol="PEPEUSDT", source_phase="pre_anomaly"
        ),
        virtual_trade_plan=VirtualTradePlan(
            virtual_entry=100.0, virtual_stop=95.0, virtual_tp1=110.0,
            direction=Direction.LONG, setup_type="scout_breakout",
        ),
        config_versions=ConfigVersions.defaults(),
        risk_decision=RiskRejectedLearningPayload(
            opportunity_id="opp_1",
            reject_reasons=("manipulation_m3",),
            account_life_tier=AccountLifeTier.B,
            regime=MarketRegime.MEME_RISK_ON,
            universe_eligible=True,
            liquidity_state="passed",
            trade_confirmation_level=TradeConfirmationLevel.T2,
            manipulation_level=ManipulationLevel.M0,
            capital_state_version="capital-x",
            risk_config_version="risk-x",
            is_new_open=True,
            attack_intent=False,
        ),
        source_phase="phase8_5_test",
    )


def test_event_repository_round_trips_learning_ready_block():
    repo = _open_repo()
    ctx = _full_context()
    payload = attach_learning_ready({"reasons": ["live_trading_disabled"]}, ctx)
    repo.append_event(
        Event(
            event_type=EventType.RISK_REJECTED,
            source_module="phase8_5_test",
            symbol="PEPEUSDT",
            payload=payload,
        )
    )
    rows = repo.list_events(event_type=EventType.RISK_REJECTED)
    assert len(rows) == 1
    out_payload = rows[0].payload
    assert out_payload["reasons"] == ["live_trading_disabled"]
    assert LEARNING_READY_KEY in out_payload
    learn = out_payload[LEARNING_READY_KEY]
    assert learn["opportunity"]["symbol"] == "PEPEUSDT"
    assert learn["virtual_trade_plan"]["virtual_entry"] == 100.0
    assert learn["risk_decision"]["opportunity_id"] == "opp_1"
    assert learn["config_versions"]["strategy_version"]


def test_event_repository_round_trips_each_of_eleven_event_types():
    """Verify every Issue-listed event type can carry learning_ready
    end-to-end."""
    from app.learning import LEARNING_READY_EVENT_TYPES

    repo = _open_repo()
    ctx = _full_context()
    for et in LEARNING_READY_EVENT_TYPES:
        payload = attach_learning_ready({"sentinel": et.value}, ctx)
        repo.append_event(
            Event(
                event_type=et,
                source_module="phase8_5_round_trip",
                symbol="ETHUSDT",
                payload=payload,
            )
        )
    for et in LEARNING_READY_EVENT_TYPES:
        rows = repo.list_events(event_type=et)
        assert len(rows) >= 1, f"missing round-trip for {et.value}"
        assert LEARNING_READY_KEY in rows[0].payload


def test_event_repository_payload_is_json_serialisable_on_disk():
    """The repository SHA-style serialiser uses ``json.dumps`` under
    the hood; this test guarantees that no Phase 8.5 enrichment
    contains a non-JSON value."""
    repo = _open_repo()
    ctx = _full_context()
    payload = attach_learning_ready({"foo": 1}, ctx)
    repo.append_event(
        Event(
            event_type=EventType.STATE_TRANSITION,
            source_module="phase8_5_test",
            payload=payload,
        )
    )
    row = repo.list_events(event_type=EventType.STATE_TRANSITION)[0]
    json.dumps(row.payload)
