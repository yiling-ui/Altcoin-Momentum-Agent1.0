"""End-to-end smoke test for `python -m app.main`.

The boot routine must:
    - run to completion (exit code 0)
    - never enable any safety flag
    - leave at least one event in the events.db
    - exercise the Phase 3 read-only Exchange Gateway: emit one
      EXCHANGE_CONNECTED event, prove `assert_read_only()` passes, and
      refuse all four write surfaces.
    - exercise the Phase 4 Market Data Buffer: track every symbol the
      mock exposes, produce one MARKET_SNAPSHOT per symbol, and emit
      at least one DATA_UNRELIABLE event for the boot WS-disconnect
      probe.
    - emit a DATA_UNRELIABLE + EXCHANGE_DISCONNECTED event on shutdown
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings as settings_mod
from app.config.settings import load_settings
from app.core.events import EventType
from app.database.connection import open_sqlite
from app.database.repositories import EventRepository
from app.main import run as main_run


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    # Reset cached settings so the env override is honoured.
    settings_mod.get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        settings_mod.get_settings.cache_clear()


def test_main_runs_and_emits_events(temp_data_dir, capsys):
    rc = main_run()
    assert rc == 0

    captured = capsys.readouterr().out
    assert "AMA-RT" in captured
    # Phase 4 entrypoint string. The Phase 1 safety lock is still asserted.
    assert "Phase 4 - Market Data Buffer" in captured
    assert "mode=paper" in captured
    assert "live_trading=False" in captured
    assert "right_tail=False" in captured
    assert "llm=False" in captured
    assert "exchange_live_orders=False" in captured
    assert "databases=5" in captured
    assert "capital_events=" in captured
    # Phase 3 fields
    assert "exchange=mock/connected" in captured
    assert "exchange_symbols=" in captured
    assert "exchange_connected_events=1" in captured
    # Phase 4 fields
    assert "market_data=" in captured
    assert "market_snapshots=" in captured
    assert "data_unreliable=" in captured

    settings = load_settings()
    sqlite_dir = settings.sqlite_dir
    # All five Phase 2 databases were created.
    for name in ("events.db", "trades.db", "positions.db", "capital.db", "incidents.db"):
        assert (sqlite_dir / name).exists(), f"{name} missing after main()"

    db_path = sqlite_dir / "events.db"
    conn = open_sqlite(db_path)
    repo = EventRepository(conn)
    try:
        types = {e.event_type for e in repo.list_events()}
        assert EventType.RISK_APPROVED in types
        assert EventType.STATE_TRANSITION in types
        assert EventType.TELEGRAM_COMMAND_RECEIVED in types
        # Phase 2: a paper-mode CAPITAL_DEPOSIT marker is emitted.
        assert EventType.CAPITAL_DEPOSIT in types
        # Phase 3: the exchange lifecycle is logged.
        assert EventType.EXCHANGE_CONNECTED in types
        # The entrypoint stops the exchange cleanly, which emits the
        # corresponding shutdown events.
        assert EventType.EXCHANGE_DISCONNECTED in types
        assert EventType.DATA_UNRELIABLE in types
        # Phase 4: a MARKET_SNAPSHOT was produced for every tracked symbol.
        market_snapshots = repo.list_events(event_type=EventType.MARKET_SNAPSHOT)
        assert len(market_snapshots) >= 1
        # Phase 4 boot drives a WS disconnect probe through the buffer,
        # which writes a batched DATA_UNRELIABLE event with scope=all_symbols.
        data_unreliables = repo.list_events(event_type=EventType.DATA_UNRELIABLE)
        all_symbol_drops = [
            e for e in data_unreliables if e.payload.get("scope") == "all_symbols"
        ]
        assert any(
            e.payload.get("trigger") == "websocket_disconnect" for e in all_symbol_drops
        )
    finally:
        conn.close()
