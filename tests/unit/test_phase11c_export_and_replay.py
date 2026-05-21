"""Phase 11C - Export + Replay round-trip on real-data events.

Confirms that the Phase 11C event chain (driven by
:class:`PaperEventChainDriver` from a real
:class:`BinancePublicClient` against a deterministic in-process
transport) round-trips cleanly through:

  - the Phase 8.5 :class:`TestDataExportService` (zip with the
    redacted JSONL streams)
  - the Phase 10A :class:`ReplayEngine`
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.core.events import EventType
from app.database.repositories import EventRepository
from app.exchanges.binance_public import BinancePublicClient
from app.exports.service import TestDataExportService
from app.market_data.buffer import MarketDataBuffer
from app.market_data.models import MarketDataBufferConfig
from app.market_data_public import (
    PaperEventChainDriver,
    PublicMarketIngestor,
)
from app.replay.engine import ReplayEngine
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
            "bids": [["100.0", "1.0"]],
            "asks": [["100.1", "1.0"]],
        },
        "/fapi/v1/aggTrades": [
            {"a": "1", "p": "100.05", "q": "0.5", "T": ts, "m": False},
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

        return bodies.get(urlsplit(url).path, {})

    return _fetch


def _drive_one_chain(events_repo: EventRepository) -> str:
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
            depth_limit=1,
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
        snap = ingestor.ingest_symbol("BTCUSDT")
        result = chain.drive(snap)
    finally:
        client.stop()
    return result.opportunity_id


def test_phase11c_events_round_trip_through_export(
    events_repo: EventRepository, tmp_path: Path
):
    """Drive ONE Phase 11C event chain and export it as a redacted
    zip. The zip must contain dedicated jsonl streams for the
    learning-ready surfaces."""
    opp_id = _drive_one_chain(events_repo)

    out_dir = tmp_path / "exports"
    out_dir.mkdir()
    service = TestDataExportService(
        event_repo=events_repo,
        trading_mode="paper",
        output_dir=out_dir,
    )
    result = service.export(range_label="24h", type_filter="all")
    assert result.zip_path.exists()

    with zipfile.ZipFile(result.zip_path) as zf:
        names = set(zf.namelist())
        # Phase 8.5 dedicated streams must all be present.
        assert "events.jsonl" in names
        assert "manifest.json" in names
        assert "summary_report.md" in names
        for stream in (
            "opportunities.jsonl",
            "signal_snapshots.jsonl",
            "virtual_trade_plans.jsonl",
            "risk_decisions.jsonl",
            "state_transitions.jsonl",
        ):
            assert stream in names, f"missing learning-ready stream {stream}"

        # Confirm every Phase 11C event type made it into events.jsonl.
        seen_types: set[str] = set()
        for line in zf.read("events.jsonl").decode("utf-8").splitlines():
            row = json.loads(line)
            seen_types.add(row.get("event_type"))
        assert "MARKET_SNAPSHOT" in seen_types
        assert "PRE_ANOMALY_DETECTED" in seen_types
        assert "ANOMALY_DETECTED" in seen_types
        assert "LIQUIDITY_CHECKED" in seen_types
        assert "TRADE_CONFIRMED" in seen_types
        assert "MANIPULATION_DETECTED" in seen_types
        assert "RISK_REJECTED" in seen_types
        assert "STATE_TRANSITION" in seen_types

        # The opportunity_id is recorded in opportunities.jsonl. The
        # Phase 8.5 export wraps the original event row, so the
        # opportunity identity lives at
        # ``payload.learning_ready.opportunity.opportunity_id``.
        opps = [
            json.loads(line)
            for line in zf.read("opportunities.jsonl").decode("utf-8").splitlines()
            if line.strip()
        ]

        def _opp_id_from(row: dict) -> str | None:
            payload = row.get("payload") or {}
            lr = payload.get("learning_ready") or {}
            opp = lr.get("opportunity") or {}
            return (
                opp.get("opportunity_id")
                or row.get("opportunity_id")
                or payload.get("opportunity_id")
            )

        assert any(
            _opp_id_from(o) == opp_id for o in opps
        ), "exported opportunities stream missing the opportunity id"


def test_phase11c_events_round_trip_through_replay(events_repo: EventRepository):
    """Replay every RISK_REJECTED produced by Phase 11C; the replayed
    decisions must carry the typed reject reasons."""
    _drive_one_chain(events_repo)
    eng = ReplayEngine(event_repo=events_repo)
    rejects = list(eng.replay_risk_rejections())
    assert rejects, "ReplayEngine returned no Phase 11C RISK_REJECTED"
    assert all("stop_unconfirmed" in r.reasons for r in rejects)


def test_phase11c_reflection_does_not_crash_on_real_market_event_chain(
    events_repo: EventRepository,
):
    """Reflection's ReplayEngine surface must read every Phase 11C
    event type without raising. We don't assert specific Reflection
    output here - the Phase 11C chain has no closed paper trade - we
    just confirm the read pipeline does not blow up on the new
    event-payload shape."""
    _drive_one_chain(events_repo)
    eng = ReplayEngine(event_repo=events_repo)
    # Iterate every category. The methods must return without raising.
    list(eng.replay_risk_rejections())
    # state-transition replay returns ONE per matching event_id; we
    # iterate raw events and call the per-event surface to cover the
    # Phase 11C STATE_TRANSITION payload.
    for ev in events_repo.list_events(event_type=EventType.STATE_TRANSITION):
        replay = eng.replay_state_transitions(symbol=ev.symbol)
        # The replay surface returns a typed object whose payload
        # serialisation must succeed.
        assert replay.to_payload() is not None
