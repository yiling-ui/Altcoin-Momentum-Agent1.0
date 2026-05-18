"""End-to-end smoke test for `python -m app.main`.

The boot routine must:
    - run to completion (exit code 0)
    - never enable any safety flag
    - leave at least one event in the events.db
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
    # Phase 2 entrypoint string. The Phase 1 safety lock is still asserted.
    assert "Phase 2 - Event Sourcing and Database" in captured
    assert "mode=paper" in captured
    assert "live_trading=False" in captured
    assert "right_tail=False" in captured
    assert "llm=False" in captured
    assert "exchange_live_orders=False" in captured
    assert "databases=5" in captured
    assert "capital_events=" in captured

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
    finally:
        conn.close()



# ---------------------------------------------------------------------------
# Phase 2 PR self-audit (round 2) - boot-path safety contracts
#
# Item #1: the paper-mode CAPITAL_DEPOSIT marker emitted by `app.main` is
#          a boot probe, not an accounting entry. Pin amount=0 and the
#          recognisable note so Issue #8 (Capital Flow Engine) can skip
#          it when computing initial_capital / lifetime_equity / etc.
#
# Item #4: the `risk_decision=True/paper_only_skeleton_approval` line in
#          the boot banner is a paper-mode self-check, NOT a real-trade
#          approval. The same Risk Engine must continue to hard-reject
#          live_trading_required / right_tail_amplify / stop_unconfirmed
#          / unknown_position with the same source code path used at boot.
# ---------------------------------------------------------------------------
def test_capital_boot_marker_contract_is_safe_for_issue8(temp_data_dir):
    """app.main must emit a CAPITAL_DEPOSIT marker that Issue #8 can skip.

    Pinned contract:
      - event_type = CAPITAL_DEPOSIT
      - amount     = 0.0  (cannot move initial_capital, lifetime_equity,
                           withdrawn_profit, trading_capital or any PnL)
      - source_module = 'bootstrap'
      - payload['note'] = 'phase2_boot_paper_marker'
    """
    from app.config.settings import load_settings
    from app.core.events import EventType
    from app.database.connection import open_sqlite
    from app.database.repositories import EventRepository

    main_run()  # already imported at top of file

    settings = load_settings()
    conn = open_sqlite(settings.sqlite_dir / "events.db")
    try:
        repo = EventRepository(conn)
        deposits = repo.list_events(event_type=EventType.CAPITAL_DEPOSIT)
    finally:
        conn.close()

    assert len(deposits) == 1, "Boot must emit exactly one CAPITAL_DEPOSIT marker"
    marker = deposits[0]
    assert marker.payload["amount"] == 0.0, (
        "Boot marker amount MUST be 0.0; non-zero would corrupt Issue #8 PnL math."
    )
    assert marker.source_module == "bootstrap", (
        "Boot marker source_module MUST be 'bootstrap' so Issue #8 can recognise it."
    )
    assert marker.payload["note"] == "phase2_boot_paper_marker", (
        "Boot marker note MUST be 'phase2_boot_paper_marker' (Issue #8 skip key)."
    )


def test_phase2_boot_risk_engine_still_rejects_live_trading(temp_data_dir):
    """The same RiskEngine + Settings used at boot must hard-reject live."""
    from app.config.settings import get_settings
    from app.database.connection import DatabaseSet, PHASE2_DATABASES
    from app.database.migrations import migrate_database_set
    from app.database.repositories import EventRepository
    from app.risk.engine import RiskEngine, RiskRequest

    settings = get_settings()
    dbs = DatabaseSet.open(
        settings.sqlite_dir, wal=True, databases=PHASE2_DATABASES
    )
    try:
        migrate_database_set(dbs)
        repo = EventRepository(dbs.events, capital_conn=dbs.capital)
        engine = RiskEngine(settings=settings, event_repo=repo)

        # Each of the four hard-rejection flags must be refused, even
        # though the boot self-check (no flags set) is approved.
        for flag, expected_reason in [
            ("live_trading_required", "live_trading_disabled"),
            ("right_tail_amplify",    "right_tail_disabled"),
            ("stop_unconfirmed",      "stop_unconfirmed"),
            ("unknown_position",      "unknown_position"),
        ]:
            kwargs = {flag: True}
            decision = engine.evaluate(
                RiskRequest(
                    source_module="audit_test",
                    action="should_be_rejected",
                    symbol="BTCUSDT",
                    **kwargs,
                )
            )
            assert decision.approved is False, (
                f"Boot-path RiskEngine wrongly approved request with {flag}=True"
            )
            assert expected_reason in decision.reasons
    finally:
        dbs.close()


def test_phase2_boot_banner_says_paper_self_check_not_trade_approval(
    temp_data_dir, capsys
):
    """The boot banner must clearly mark the Risk decision as a self-check."""
    rc = main_run()
    assert rc == 0
    out = capsys.readouterr().out
    # The marker substring is what makes the banner unambiguous: the
    # decision is the paper-mode self-check, NOT a trade approval.
    assert "paper_only_skeleton_approval" in out
    assert "paper_self_check_only" in out
    # And it must NOT claim any live/right-tail/llm capability.
    assert "live_trading=False" in out
    assert "right_tail=False" in out
    assert "llm=False" in out
    assert "exchange_live_orders=False" in out
