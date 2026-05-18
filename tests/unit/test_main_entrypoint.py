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
    assert "Phase 1 - Safety Foundation" in captured
    assert "mode=paper" in captured
    assert "live_trading=False" in captured
    assert "right_tail=False" in captured
    assert "llm=False" in captured

    settings = load_settings()
    db_path = settings.sqlite_dir / "events.db"
    assert db_path.exists()

    conn = open_sqlite(db_path)
    repo = EventRepository(conn)
    try:
        types = {e.event_type for e in repo.list()}
        assert EventType.RISK_APPROVED in types
        assert EventType.STATE_TRANSITION in types
        assert EventType.TELEGRAM_COMMAND_RECEIVED in types
    finally:
        conn.close()
