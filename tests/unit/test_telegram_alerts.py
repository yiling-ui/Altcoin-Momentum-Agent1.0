"""Phase 10D - AlertDispatcher tests (Issue #10 Part 4).

Pin throttle / dedupe / severity / cooldown / P0 bypass / aggregation
/ redaction-gate / audit behaviour.
"""

from __future__ import annotations

import pytest

from app.core.events import EventType
from app.telegram.alerts import (
    AlertDispatcher,
    AlertDispatchResult,
    AlertSeverity,
)
from app.telegram.formatter import (
    TAG_CANDIDATE_SYMBOL,
    TAG_CAPITAL_REBASE,
    TAG_INCIDENT_ALERT,
    TAG_RISK_REJECTION,
    TAG_STATE_TRANSITION,
    TAG_SYSTEM_STATUS,
)
from app.telegram.outbound import FakeTelegramClient


def _payload(**extra):
    base = {
        "trading_mode": "paper",
        "live_trading_enabled": False,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Successful dispatch + audit
# ---------------------------------------------------------------------------
def test_dispatch_writes_telegram_message_sent_event(events_repo):
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(
        outbound=fake,
        event_repo=events_repo,
        chat_id="c1",
        outbound_enabled=True,
    )
    res = disp.dispatch(
        tag=TAG_SYSTEM_STATUS,
        payload=_payload(status="running"),
        severity=AlertSeverity.INFO,
    )
    assert res.sent
    assert disp.messages_sent == 1
    [audit] = events_repo.list(event_type=EventType.TELEGRAM_MESSAGE_SENT)
    assert audit.payload["tag"] == TAG_SYSTEM_STATUS
    assert audit.payload["severity"] == "info"
    assert audit.payload["surface"] == "send_message"


def test_dispatch_when_outbound_disabled_audits_only(events_repo):
    """Default Phase 10D path: outbound_enabled=False (the FakeClient
    is in-process recorder only). The dispatcher still writes the
    audit row so paper-mode runs prove the formatter pipeline ran."""
    fake = FakeTelegramClient(outbound_enabled=False)
    disp = AlertDispatcher(
        outbound=fake,
        event_repo=events_repo,
        chat_id="c1",
        outbound_enabled=False,
    )
    res = disp.dispatch(
        tag=TAG_SYSTEM_STATUS,
        payload=_payload(status="running"),
    )
    assert res.sent
    assert res.reason == "audited_only"
    assert fake.call_count == 0  # nothing went through the transport
    assert disp.messages_sent == 1
    assert events_repo.count(event_type=EventType.TELEGRAM_MESSAGE_SENT) == 1


def test_dispatch_with_unknown_tag_returns_unsent_and_does_not_crash(events_repo):
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(
        outbound=fake,
        event_repo=events_repo,
        outbound_enabled=True,
    )
    res = disp.dispatch(tag="not_a_real_tag", payload={})
    assert not res.sent
    assert "unknown_tag" in res.reason
    assert disp.messages_sent == 0


# ---------------------------------------------------------------------------
# Cooldown / dedupe
# ---------------------------------------------------------------------------
def test_repeat_within_cooldown_is_blocked():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    payload = _payload(symbol="BTCUSDT", to="observe", trigger="t")
    r1 = disp.dispatch(
        tag=TAG_STATE_TRANSITION,
        payload=payload,
        severity=AlertSeverity.INFO,
        clock_ms=1_000,
    )
    r2 = disp.dispatch(
        tag=TAG_STATE_TRANSITION,
        payload=payload,
        severity=AlertSeverity.INFO,
        clock_ms=2_000,
    )
    assert r1.sent
    assert not r2.sent
    assert r2.reason == "cooldown_active"
    assert disp.cooldown_blocked == 1
    assert disp.deduped == 1


def test_repeat_after_cooldown_window_is_sent_again():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(
        outbound=fake,
        outbound_enabled=True,
        cooldown_ms={
            AlertSeverity.INFO: 5_000,
            AlertSeverity.WARNING: 5_000,
            AlertSeverity.CRITICAL: 0,
        },
    )
    payload = _payload(symbol="BTCUSDT", to="observe", trigger="t")
    r1 = disp.dispatch(
        tag=TAG_STATE_TRANSITION,
        payload=payload,
        severity=AlertSeverity.INFO,
        clock_ms=0,
    )
    r2 = disp.dispatch(
        tag=TAG_STATE_TRANSITION,
        payload=payload,
        severity=AlertSeverity.INFO,
        clock_ms=10_000,
    )
    assert r1.sent and r2.sent
    assert disp.messages_sent == 2


def test_critical_severity_bypasses_cooldown():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    payload = _payload(symbol="BTCUSDT", level="P0", title="ghost_pos")
    r1 = disp.dispatch(
        tag=TAG_INCIDENT_ALERT,
        payload=payload,
        severity=AlertSeverity.CRITICAL,
        clock_ms=1,
    )
    r2 = disp.dispatch(
        tag=TAG_INCIDENT_ALERT,
        payload=payload,
        severity=AlertSeverity.CRITICAL,
        clock_ms=2,
    )
    r3 = disp.dispatch(
        tag=TAG_INCIDENT_ALERT,
        payload=payload,
        severity=AlertSeverity.CRITICAL,
        clock_ms=3,
    )
    assert r1.sent and r2.sent and r3.sent
    assert disp.messages_sent == 3
    assert disp.cooldown_blocked == 0


def test_critical_overrides_existing_info_cooldown():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    payload = _payload(symbol="BTCUSDT", level="P1", title="ws_drop")
    # First an INFO send under the same key.
    info_payload = _payload(symbol="BTCUSDT", level="info", title="x")
    r1 = disp.dispatch(
        tag=TAG_INCIDENT_ALERT,
        payload=info_payload,
        severity=AlertSeverity.INFO,
        clock_ms=0,
    )
    # Now a CRITICAL incident under the same dedupe key - MUST go through.
    r2 = disp.dispatch(
        tag=TAG_INCIDENT_ALERT,
        payload=payload,
        severity=AlertSeverity.CRITICAL,
        clock_ms=1,
        dedupe_key=disp._default_dedupe_key(  # noqa: SLF001
            TAG_INCIDENT_ALERT, info_payload
        ),
    )
    assert r1.sent and r2.sent


def test_explicit_bypass_throttle_overrides_cooldown():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    payload = _payload(symbol="BTCUSDT", to="observe")
    disp.dispatch(
        tag=TAG_STATE_TRANSITION, payload=payload, severity=AlertSeverity.INFO,
        clock_ms=0,
    )
    res = disp.dispatch(
        tag=TAG_STATE_TRANSITION,
        payload=payload,
        severity=AlertSeverity.INFO,
        bypass_throttle=True,
        clock_ms=1,
    )
    assert res.sent


# ---------------------------------------------------------------------------
# Auto-promotion of stop_unconfirmed / unknown_position to CRITICAL
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reason", ["stop_unconfirmed", "unknown_position"]
)
def test_high_priority_reasons_promote_to_critical_and_bypass_throttle(reason):
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    payload = _payload(
        symbol="BTCUSDT",
        action="attack",
        reasons=[reason],
    )
    r1 = disp.dispatch(
        tag=TAG_RISK_REJECTION,
        payload=payload,
        severity=AlertSeverity.INFO,  # caller-specified INFO
        clock_ms=0,
    )
    r2 = disp.dispatch(
        tag=TAG_RISK_REJECTION,
        payload=payload,
        severity=AlertSeverity.INFO,
        clock_ms=1,
    )
    # Both must go through - auto-promoted to CRITICAL bypasses cooldown.
    assert r1.sent and r2.sent
    assert r1.severity is AlertSeverity.CRITICAL
    assert r2.severity is AlertSeverity.CRITICAL


def test_other_high_priority_reasons_promote_to_warning():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    payload = _payload(
        symbol="BTCUSDT",
        action="attack",
        reasons=["manipulation_m3"],
    )
    res = disp.dispatch(
        tag=TAG_RISK_REJECTION, payload=payload, severity=AlertSeverity.INFO
    )
    assert res.sent
    assert res.severity is AlertSeverity.WARNING


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def test_low_severity_risk_rejections_aggregate_into_summary():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(
        outbound=fake,
        outbound_enabled=True,
        aggregation_window_ms=10_000,
    )
    for i in range(5):
        res = disp.dispatch(
            tag=TAG_RISK_REJECTION,
            payload=_payload(
                symbol="BTCUSDT",
                action="scout",
                reasons=["minor_tilt"],
            ),
            severity=AlertSeverity.INFO,
            clock_ms=1_000 + i * 100,
        )
        # No actual send - they were aggregated.
        assert not res.sent
        assert res.reason == "aggregated"
    assert disp.aggregated == 5
    assert disp.messages_sent == 0
    # Force flush the bucket and confirm a single summary lands.
    flushed = disp.force_flush_aggregations(clock_ms=100_000)
    assert len(flushed) == 1
    assert flushed[0].sent
    assert disp.messages_sent == 1
    assert "risk_rejection_summary" in flushed[0].text
    assert "minor_tilt" in flushed[0].text


def test_aggregation_does_not_apply_to_high_priority_reasons():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    res = disp.dispatch(
        tag=TAG_RISK_REJECTION,
        payload=_payload(
            symbol="BTCUSDT",
            action="attack",
            reasons=["stop_unconfirmed"],
        ),
        severity=AlertSeverity.INFO,
    )
    # Auto-promoted to CRITICAL -> does NOT enter aggregation.
    assert res.sent
    assert res.reason != "aggregated"


def test_flush_only_flushes_buckets_older_than_window():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(
        outbound=fake,
        outbound_enabled=True,
        aggregation_window_ms=10_000,
    )
    disp.dispatch(
        tag=TAG_RISK_REJECTION,
        payload=_payload(
            symbol="BTCUSDT", action="scout", reasons=["minor_tilt"]
        ),
        severity=AlertSeverity.INFO,
        clock_ms=1_000,
    )
    flushed_too_early = disp.flush_aggregations(clock_ms=2_000)
    assert flushed_too_early == []
    flushed_in_time = disp.flush_aggregations(clock_ms=20_000)
    assert len(flushed_in_time) == 1


# ---------------------------------------------------------------------------
# Failure path - audit + safe degradation
# ---------------------------------------------------------------------------
def test_transport_failure_writes_telegram_send_failed_event(events_repo):
    fake = FakeTelegramClient(outbound_enabled=True, failure_mode="drop")
    disp = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=True
    )
    res = disp.dispatch(
        tag=TAG_SYSTEM_STATUS,
        payload=_payload(status="running"),
    )
    assert not res.sent
    assert res.reason == "transport_failed"
    assert disp.send_failed == 1
    assert events_repo.count(event_type=EventType.TELEGRAM_SEND_FAILED) == 1
    sent = events_repo.list(event_type=EventType.TELEGRAM_SEND_FAILED)[0]
    assert sent.payload["reason"] == "transport_error"


def test_dispatcher_never_raises_on_formatter_exception(events_repo):
    """The dispatcher must NEVER raise into the caller; a buggy
    formatter must convert to a TELEGRAM_SEND_FAILED audit event."""
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=True
    )

    # Monkey-patch a formatter-key registry to raise. We replace just
    # this call site rather than the global registry.
    from app.telegram import alerts as alerts_mod

    original = alerts_mod.FORMATTERS[TAG_SYSTEM_STATUS]

    def _broken(payload):
        raise RuntimeError("synthetic failure")

    alerts_mod.FORMATTERS[TAG_SYSTEM_STATUS] = _broken
    try:
        res = disp.dispatch(
            tag=TAG_SYSTEM_STATUS,
            payload=_payload(status="running"),
        )
    finally:
        alerts_mod.FORMATTERS[TAG_SYSTEM_STATUS] = original

    assert not res.sent
    assert res.reason == "formatter_exception"
    assert (
        events_repo.count(event_type=EventType.TELEGRAM_SEND_FAILED) >= 1
    )


# ---------------------------------------------------------------------------
# Document send (Phase 10D bridge entry point)
# ---------------------------------------------------------------------------
def test_send_document_path_emits_telegram_message_sent(events_repo, tmp_path):
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=True
    )
    payload = b"PK\x03\x04zip-bytes"
    res = disp.send_document(
        document_path=str(tmp_path / "x.zip"),
        document_bytes=payload,
        caption="[ama-rt:export] mode=PAPER ok",
    )
    assert res.sent
    assert disp.documents_sent == 1
    audits = events_repo.list(event_type=EventType.TELEGRAM_MESSAGE_SENT)
    assert any(a.payload["surface"] == "send_document" for a in audits)
    [call] = fake.calls
    assert call.document_size_bytes == len(payload)


def test_send_document_under_disabled_outbound_does_not_call_transport(
    events_repo, tmp_path
):
    fake = FakeTelegramClient(outbound_enabled=False)
    disp = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=False
    )
    res = disp.send_document(
        document_path=str(tmp_path / "x.zip"),
        document_bytes=b"PK",
        caption="[ama-rt:export] mode=PAPER ok",
    )
    assert res.sent
    assert disp.documents_sent == 1
    assert fake.call_count == 0


def test_send_document_failure_writes_telegram_send_failed(events_repo, tmp_path):
    fake = FakeTelegramClient(outbound_enabled=True, failure_mode="drop")
    disp = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=True
    )
    res = disp.send_document(
        document_path=str(tmp_path / "x.zip"),
        document_bytes=b"PK",
        caption="[ama-rt:export] mode=PAPER ok",
    )
    assert not res.sent
    assert disp.send_failed == 1
    assert events_repo.count(event_type=EventType.TELEGRAM_SEND_FAILED) == 1


# ---------------------------------------------------------------------------
# Counters reset on .reset()
# ---------------------------------------------------------------------------
def test_reset_clears_state_and_counters():
    fake = FakeTelegramClient(outbound_enabled=True)
    disp = AlertDispatcher(outbound=fake, outbound_enabled=True)
    disp.dispatch(
        tag=TAG_SYSTEM_STATUS,
        payload=_payload(status="running"),
    )
    disp.reset()
    assert disp.messages_sent == 0
    assert disp.deduped == 0
    assert disp.cooldown_blocked == 0
    assert fake.call_count == 0


def test_severity_enum_values_pinned():
    assert {s.value for s in AlertSeverity} == {"info", "warning", "critical"}
