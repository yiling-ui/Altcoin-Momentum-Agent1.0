"""Event Sourcing repository tests (Phase 1 minimum)."""

from __future__ import annotations

from app.core.events import Event, EventType


def test_append_and_count(events_repo):
    events_repo.append(
        Event(
            event_type=EventType.STATE_TRANSITION,
            source_module="test",
            payload={"from": "idle", "to": "idle"},
        )
    )
    assert events_repo.count() == 1


def test_required_field_contract(events_repo):
    """Spec §12.1 says every event must carry the same field set."""
    events_repo.append(
        Event(
            event_type=EventType.RISK_APPROVED,
            source_module="risk_engine",
            symbol="BTCUSDT",
            position_id="pos-1",
            order_id="ord-1",
            payload={"reasons": ["paper_only_skeleton_approval"]},
        )
    )
    [event] = events_repo.list()
    assert event.symbol == "BTCUSDT"
    assert event.position_id == "pos-1"
    assert event.order_id == "ord-1"
    assert event.event_type is EventType.RISK_APPROVED
    assert event.payload == {"reasons": ["paper_only_skeleton_approval"]}
    assert event.event_id  # uuid4 generated
    assert event.timestamp > 0


def test_replay_is_ordered_by_timestamp(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.STATE_TRANSITION, source_module="test", timestamp=300),
            Event(event_type=EventType.STATE_TRANSITION, source_module="test", timestamp=100),
            Event(event_type=EventType.STATE_TRANSITION, source_module="test", timestamp=200),
        ]
    )
    timestamps = [e.timestamp for e in events_repo.replay()]
    assert timestamps == [100, 200, 300]


def test_filter_by_event_type(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.RISK_APPROVED, source_module="r"),
            Event(event_type=EventType.RISK_REJECTED, source_module="r"),
            Event(event_type=EventType.RISK_REJECTED, source_module="r"),
        ]
    )
    rejects = events_repo.list(event_type=EventType.RISK_REJECTED)
    assert len(rejects) == 2
    assert all(e.event_type is EventType.RISK_REJECTED for e in rejects)
