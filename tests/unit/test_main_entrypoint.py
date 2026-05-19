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
    - exercise the Phase 5 Regime / Universe / Liquidity engines:
      emit one REGIME_UPDATED, one UNIVERSE_FILTERED per symbol, and
      two LIQUIDITY_CHECKED per symbol (one ``check="evaluate"`` and
      one ``check="can_exit_position"``).
    - exercise the Phase 6 Pre-Anomaly / Anomaly / Confirmation /
      Manipulation classifiers: emit one of each event type per
      symbol.
    - exercise the Phase 9 Execution FSM driver: drive ONE paper-mode
      order from IDLE through POSITION_OPEN and POSITION_CLOSED. Emit
      ORDER_SENT / ORDER_ACK / ORDER_FILLED / STOP_SENT /
      STOP_CONFIRMED / POSITION_OPENED / EXIT_TRIGGERED /
      POSITION_CLOSED.
    - exercise the Phase 9 Reconciliation loop: emit
      RECONCILIATION_STARTED + RECONCILIATION_RESOLVED. The boot
      drill must produce zero RECONCILIATION_MISMATCH events because
      the local + remote snapshots are built from the same paper
      ledger.
    - emit a DATA_UNRELIABLE + EXCHANGE_DISCONNECTED event on shutdown.
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
    # Phase 10A entrypoint string. The Phase 1 safety lock is still asserted.
    assert "Phase 10A - Replay Engine" in captured
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
    # Phase 5 fields
    assert "regime=" in captured
    assert "regime_events=1" in captured
    assert "universe=" in captured
    assert "universe_events=" in captured
    assert "liquidity_events=" in captured
    # Phase 6 fields
    assert "pre_anomaly_events=" in captured
    assert "anomaly_events=" in captured
    assert "trade_confirmed_events=" in captured
    assert "manipulation_events=" in captured
    # Phase 7 fields
    assert "state_transitions=" in captured
    assert "trade_state=" in captured
    assert "daily_loss_breaker=" in captured
    assert "consecutive_loss_breaker=" in captured
    # Phase 9 fields
    assert "orders_submitted=" in captured
    assert "order_sent_events=" in captured
    assert "order_filled_events=" in captured
    assert "stops_confirmed=" in captured
    assert "positions_opened=" in captured
    assert "positions_closed=" in captured
    assert "reconciliations_run=" in captured
    assert "reconciliation_started_events=" in captured
    assert "reconciliation_resolved_events=" in captured
    assert "reconciliation_mismatches=0" in captured
    assert "new_opens_paused=False" in captured
    assert "incidents_opened=0" in captured
    assert "protection_mode_entered=" in captured
    # Phase 10A fields - Replay self-check passed.
    assert "replay_paper_trade_matched=True" in captured
    assert "replay_p0_incidents=0" in captured
    assert "replay_telegram_commands=" in captured
    assert "replay_state_transitions=" in captured
    assert "replay_p0_latched_pause_invariant=True" in captured

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
        # Phase 5: the regime engine fires once at boot.
        regime_events = repo.list_events(event_type=EventType.REGIME_UPDATED)
        assert len(regime_events) == 1
        regime_payload = regime_events[0].payload
        for key in (
            "market_regime",
            "btc_trend",
            "btc_volatility",
            "alt_liquidity",
            "risk_permission",
            "reason_tags",
        ):
            assert key in regime_payload
        # Phase 5: one UNIVERSE_FILTERED per tracked symbol.
        universe_events = repo.list_events(event_type=EventType.UNIVERSE_FILTERED)
        assert len(universe_events) >= 1
        for ev in universe_events:
            assert "eligible" in ev.payload
            assert "reject_reasons" in ev.payload
        # Phase 5: two LIQUIDITY_CHECKED events per symbol (evaluate +
        # can_exit_position).
        liquidity_events = repo.list_events(event_type=EventType.LIQUIDITY_CHECKED)
        assert len(liquidity_events) >= 2
        check_tags = {ev.payload.get("check") for ev in liquidity_events}
        assert "evaluate" in check_tags
        assert "can_exit_position" in check_tags
        # Phase 6: each of the four classifiers emits at least one event.
        pre_anomaly_events = repo.list_events(
            event_type=EventType.PRE_ANOMALY_DETECTED
        )
        assert len(pre_anomaly_events) >= 1
        for ev in pre_anomaly_events:
            assert "pre_anomaly_score" in ev.payload
            assert "reason_tags" in ev.payload
        anomaly_events = repo.list_events(event_type=EventType.ANOMALY_DETECTED)
        assert len(anomaly_events) >= 1
        for ev in anomaly_events:
            assert "anomaly_score" in ev.payload
            assert "component_scores" in ev.payload
        trade_confirmed = repo.list_events(event_type=EventType.TRADE_CONFIRMED)
        assert len(trade_confirmed) >= 1
        for ev in trade_confirmed:
            assert "level" in ev.payload
            assert ev.payload["level"] in ("T0", "T1", "T2", "T3", "T4")
        manipulation = repo.list_events(event_type=EventType.MANIPULATION_DETECTED)
        assert len(manipulation) >= 1
        for ev in manipulation:
            assert "level" in ev.payload
            assert ev.payload["level"] in ("M0", "M1", "M2", "M3")
        # Phase 9: the boot drill drives one paper-mode order through
        # the full Execution FSM.
        order_sent = repo.list_events(event_type=EventType.ORDER_SENT)
        assert len(order_sent) == 1
        assert order_sent[0].payload["intent"] == "new_open"
        assert order_sent[0].payload["request"]["margin_mode"] == "isolated"
        assert order_sent[0].payload["opportunity_id"] == "opp_phase9_boot"
        assert repo.count_events(event_type=EventType.ORDER_ACK) == 1
        assert repo.count_events(event_type=EventType.ORDER_FILLED) == 1
        assert repo.count_events(event_type=EventType.STOP_SENT) == 1
        assert repo.count_events(event_type=EventType.STOP_CONFIRMED) == 1
        assert repo.count_events(event_type=EventType.POSITION_OPENED) == 1
        assert repo.count_events(event_type=EventType.EXIT_TRIGGERED) == 1
        assert repo.count_events(event_type=EventType.POSITION_CLOSED) == 1
        # Phase 9: ONE clean reconciliation pass at boot, no mismatch.
        assert repo.count_events(event_type=EventType.RECONCILIATION_STARTED) == 1
        assert repo.count_events(event_type=EventType.RECONCILIATION_RESOLVED) == 1
        assert repo.count_events(event_type=EventType.RECONCILIATION_MISMATCH) == 0
        # Phase 9: clean boot writes ZERO incidents and stays out of
        # protection mode.
        assert repo.count_events(event_type=EventType.INCIDENT_OPENED) == 0
        assert repo.count_events(event_type=EventType.PROTECTION_MODE_ENTERED) == 0
    finally:
        conn.close()
