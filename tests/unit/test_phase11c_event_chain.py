"""Phase 11C - Event-chain + ingestor + learning-ready integration tests.

Covers:

  - test_public_market_event_repository_roundtrip
  - test_learning_ready_payload_from_real_market_snapshot
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from app.core.events import EventType
from app.database.repositories import EventRepository
from app.exchanges.binance_public import BinancePublicClient
from app.market_data.buffer import MarketDataBuffer
from app.market_data.models import MarketDataBufferConfig
from app.market_data_public import (
    PaperEventChainDriver,
    PublicMarketIngestor,
)
from app.risk.engine import RiskEngine


def _build_static_transport(symbol: str = "BTCUSDT", ts: int = 1700000000000):
    bodies = {
        "/fapi/v1/exchangeInfo": {
            "symbols": [
                {
                    "symbol": symbol,
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                    "filters": [],
                }
            ]
        },
        "/fapi/v1/ticker/24hr": [{"symbol": symbol, "quoteVolume": "1000"}],
        "/fapi/v1/ticker/bookTicker": {
            "symbol": symbol,
            "bidPrice": "100.0",
            "askPrice": "100.1",
            "time": ts,
        },
        "/fapi/v1/depth": {
            "E": ts,
            "T": ts,
            "bids": [["100.0", "1.0"], ["99.9", "2.0"]],
            "asks": [["100.1", "1.0"], ["100.2", "2.0"]],
        },
        "/fapi/v1/aggTrades": [
            {"a": "1", "p": "100.05", "q": "0.5", "T": ts - 1000, "m": False},
            {"a": "2", "p": "100.10", "q": "0.4", "T": ts - 500, "m": True},
        ],
        "/fapi/v1/fundingRate": [{"fundingTime": ts, "fundingRate": "0.0001"}],
        "/fapi/v1/openInterest": {"time": ts, "openInterest": "12345.0"},
        "/fapi/v1/premiumIndex": {
            "symbol": symbol,
            "markPrice": "100.05",
            "indexPrice": "100.04",
            "lastFundingRate": "0.0001",
            "nextFundingTime": ts + 1,
            "time": ts,
        },
    }

    def _fetch(url: str) -> Any:
        from urllib.parse import urlsplit

        path = urlsplit(url).path
        return bodies.get(path, {})

    return _fetch


def test_public_market_event_repository_roundtrip(events_repo: EventRepository):
    """Drive ONE chain end-to-end and confirm every Phase 11C event is
    persisted and re-readable."""
    client = BinancePublicClient(transport=_build_static_transport())
    try:
        buffer = MarketDataBuffer(
            exchange=client,
            event_repo=events_repo,
            config=MarketDataBufferConfig(market_snapshot_event_emit_enabled=False),
            source_module="market_data_public.buffer",
        )
        ingestor = PublicMarketIngestor(
            client=client,
            buffer=buffer,
            event_repo=events_repo,
            depth_limit=2,
            trades_limit=10,
            emit_market_snapshot_event=True,
        )
        risk = RiskEngine(event_repo=events_repo)
        chain = PaperEventChainDriver(
            risk_engine=risk,
            event_repo=events_repo,
            public_client=client,
        )
        chain.begin_scan_batch()
        symbol_snap = ingestor.ingest_symbol("BTCUSDT")
        result = chain.drive(symbol_snap)
    finally:
        client.stop()

    assert result.symbol == "BTCUSDT"
    assert result.opportunity_id.startswith("opp_")
    assert result.scan_batch_id.startswith("scan_")
    assert result.risk_approved is False
    assert "stop_unconfirmed" in result.reject_reasons

    # Every Phase 11C event type is present in events.db.
    expected_types = (
        EventType.MARKET_SNAPSHOT,
        EventType.PRE_ANOMALY_DETECTED,
        EventType.ANOMALY_DETECTED,
        EventType.LIQUIDITY_CHECKED,
        EventType.TRADE_CONFIRMED,
        EventType.MANIPULATION_DETECTED,
        EventType.RISK_REJECTED,
        EventType.STATE_TRANSITION,
    )
    for et in expected_types:
        count = events_repo.count_events(event_type=et)
        assert count >= 1, f"missing event type {et.value}"

    # The MARKET_SNAPSHOT event carries the Phase 11C provider tag and
    # the mark_price field.
    snapshots = events_repo.list_events(event_type=EventType.MARKET_SNAPSHOT)
    assert snapshots, "expected at least one MARKET_SNAPSHOT event"
    snapshot_payload = snapshots[0].payload
    assert snapshot_payload.get("provider") == "binance_public"
    assert snapshot_payload.get("mark_price") == pytest.approx(100.05)
    assert snapshot_payload.get("phase") == "11C"


def test_learning_ready_payload_from_real_market_snapshot(
    events_repo: EventRepository,
):
    """The RISK_REJECTED event must carry the full Phase 8.5
    learning-ready block: opportunity, signal_snapshot, virtual_trade_plan,
    config_versions, risk_decision, source_phase."""
    client = BinancePublicClient(transport=_build_static_transport())
    try:
        buffer = MarketDataBuffer(
            exchange=client,
            event_repo=events_repo,
            config=MarketDataBufferConfig(market_snapshot_event_emit_enabled=False),
            source_module="market_data_public.buffer",
        )
        ingestor = PublicMarketIngestor(
            client=client,
            buffer=buffer,
            event_repo=events_repo,
            depth_limit=2,
            trades_limit=10,
            emit_market_snapshot_event=False,
        )
        risk = RiskEngine(event_repo=events_repo)
        chain = PaperEventChainDriver(
            risk_engine=risk,
            event_repo=events_repo,
            public_client=client,
        )
        chain.begin_scan_batch()
        symbol_snap = ingestor.ingest_symbol("BTCUSDT")
        result = chain.drive(symbol_snap)
    finally:
        client.stop()

    rejected = events_repo.list_events(event_type=EventType.RISK_REJECTED)
    assert rejected, "RISK_REJECTED event was not persisted"
    payload = rejected[0].payload
    assert "learning_ready" in payload
    learning_ready = payload["learning_ready"]

    # Phase 8.5 contract: opportunity_id + scan_batch_id + symbol +
    # source_phase live under opportunity{}.
    assert "opportunity" in learning_ready
    op = learning_ready["opportunity"]
    assert op["opportunity_id"] == result.opportunity_id
    assert op["scan_batch_id"] == result.scan_batch_id
    assert op["symbol"] == "BTCUSDT"
    assert op["source_phase"] == "phase_11c_public_market_paper"

    # SignalSnapshot is recorded with the Phase 1 §11.2 fields.
    assert "signal_snapshot" in learning_ready
    signal = learning_ready["signal_snapshot"]
    for key in (
        "symbol",
        "regime",
        "pre_anomaly_score",
        "anomaly_score",
        "liquidity_score",
        "trade_confirmation_level",
        "manipulation_level",
        "right_tail_score",
        "opportunity_grade",
        "no_trade_reason",
    ):
        assert key in signal

    # VirtualTradePlan is recorded.
    assert "virtual_trade_plan" in learning_ready
    plan = learning_ready["virtual_trade_plan"]
    for key in (
        "virtual_entry",
        "virtual_stop",
        "virtual_tp1",
        "direction",
        "setup_type",
    ):
        assert key in plan

    # ConfigVersions are recorded.
    assert "config_versions" in learning_ready
    versions = learning_ready["config_versions"]
    for key in (
        "strategy_version",
        "risk_config_version",
        "scoring_version",
        "capital_state_version",
        "state_machine_version",
        "llm_prompt_version",
    ):
        assert key in versions

    # Risk decision sub-block carries the typed reject_reasons.
    assert "risk_decision" in learning_ready
    decision = learning_ready["risk_decision"]
    assert "reject_reasons" in decision
    assert "stop_unconfirmed" in decision["reject_reasons"]


def test_state_transition_carries_learning_ready(events_repo: EventRepository):
    """The Phase 11C STATE_TRANSITION event also carries the
    learning_ready block so Reflection can group on opportunity_id."""
    client = BinancePublicClient(transport=_build_static_transport())
    try:
        buffer = MarketDataBuffer(
            exchange=client,
            event_repo=events_repo,
            config=MarketDataBufferConfig(market_snapshot_event_emit_enabled=False),
            source_module="market_data_public.buffer",
        )
        ingestor = PublicMarketIngestor(
            client=client,
            buffer=buffer,
            event_repo=events_repo,
            depth_limit=2,
            trades_limit=10,
            emit_market_snapshot_event=False,
        )
        risk = RiskEngine(event_repo=events_repo)
        chain = PaperEventChainDriver(
            risk_engine=risk,
            event_repo=events_repo,
            public_client=client,
        )
        chain.begin_scan_batch()
        symbol_snap = ingestor.ingest_symbol("BTCUSDT")
        chain.drive(symbol_snap)
    finally:
        client.stop()

    transitions = events_repo.list_events(event_type=EventType.STATE_TRANSITION)
    assert transitions
    payload = transitions[0].payload
    assert payload.get("phase") == "11C"
    assert payload.get("source_phase") == "phase_11c_public_market_paper"
    assert "learning_ready" in payload
    assert "opportunity" in payload["learning_ready"]


def test_ingestor_skips_event_when_disabled(events_repo: EventRepository):
    client = BinancePublicClient(transport=_build_static_transport())
    try:
        buffer = MarketDataBuffer(
            exchange=client,
            event_repo=events_repo,
            config=MarketDataBufferConfig(market_snapshot_event_emit_enabled=False),
            source_module="market_data_public.buffer",
        )
        ingestor = PublicMarketIngestor(
            client=client,
            buffer=buffer,
            event_repo=events_repo,
            depth_limit=2,
            trades_limit=10,
            emit_market_snapshot_event=False,
        )
        snap = ingestor.ingest_symbol("BTCUSDT")
        assert snap.snapshot.symbol == "BTCUSDT"
    finally:
        client.stop()
    assert events_repo.count_events(event_type=EventType.MARKET_SNAPSHOT) == 0
