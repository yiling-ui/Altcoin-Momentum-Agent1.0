"""Phase 8.5 - OpportunityIdentity tests (Issue #8.5)."""

from __future__ import annotations

import pytest

from app.learning import (
    OpportunityIdentity,
    make_opportunity_id,
    make_scan_batch_id,
)
from app.learning.identity import OPPORTUNITY_ID_PREFIX, SCAN_BATCH_ID_PREFIX


def test_make_opportunity_id_generates_unique_prefixed_ids():
    a = make_opportunity_id()
    b = make_opportunity_id()
    assert a != b
    assert a.startswith(OPPORTUNITY_ID_PREFIX)
    assert b.startswith(OPPORTUNITY_ID_PREFIX)


def test_make_opportunity_id_honours_caller_value():
    assert make_opportunity_id(opportunity_id="opp_explicit") == "opp_explicit"


def test_make_scan_batch_id_generates_unique_prefixed_ids():
    a = make_scan_batch_id()
    b = make_scan_batch_id()
    assert a != b
    assert a.startswith(SCAN_BATCH_ID_PREFIX)
    assert b.startswith(SCAN_BATCH_ID_PREFIX)


def test_opportunity_identity_create_fills_in_ids_and_timestamp():
    identity = OpportunityIdentity.create(
        symbol="PEPEUSDT", source_phase="pre_anomaly"
    )
    assert identity.symbol == "PEPEUSDT"
    assert identity.source_phase == "pre_anomaly"
    assert identity.opportunity_id.startswith(OPPORTUNITY_ID_PREFIX)
    assert identity.scan_batch_id.startswith(SCAN_BATCH_ID_PREFIX)
    assert identity.first_seen_ts > 0


def test_opportunity_identity_round_trip_payload():
    original = OpportunityIdentity.create(
        symbol="ETHUSDT", source_phase="anomaly", first_seen_ts=1_700_000_000_000
    )
    payload = original.to_payload()
    assert set(payload.keys()) == {
        "opportunity_id",
        "scan_batch_id",
        "symbol",
        "first_seen_ts",
        "source_phase",
    }
    restored = OpportunityIdentity.from_payload(payload)
    assert restored == original


def test_opportunity_identity_is_frozen():
    identity = OpportunityIdentity.create(symbol="BTCUSDT", source_phase="risk_engine")
    with pytest.raises((TypeError, ValueError)):
        identity.symbol = "ETHUSDT"  # type: ignore[misc]


def test_opportunity_identity_rejects_extra_fields():
    payload = {
        "opportunity_id": "opp_1",
        "scan_batch_id": "scan_1",
        "symbol": "BTCUSDT",
        "first_seen_ts": 0,
        "source_phase": "scanner",
        "unexpected": True,
    }
    with pytest.raises(Exception):
        OpportunityIdentity(**payload)


def test_opportunity_id_format_is_compact_and_url_safe():
    identity = OpportunityIdentity.create(symbol="BTCUSDT", source_phase="phase8_5")
    assert " " not in identity.opportunity_id
    assert " " not in identity.scan_batch_id
    # No characters that confuse URLs / filenames.
    for ch in identity.opportunity_id + identity.scan_batch_id:
        assert ch.isalnum() or ch == "_"
