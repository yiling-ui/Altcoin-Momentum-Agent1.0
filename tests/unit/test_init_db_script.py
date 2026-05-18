"""`scripts/init_db.py` smoke test (Phase 2 - Event Sourcing and Database)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings as settings_mod
from app.config.settings import load_settings
from app.database.connection import PHASE2_DATABASES
from scripts.init_db import main as init_db_main


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        settings_mod.get_settings.cache_clear()


def test_init_db_creates_all_phase2_databases(temp_data_dir, capsys):
    rc = init_db_main()
    assert rc == 0
    settings = load_settings()
    for name in PHASE2_DATABASES:
        assert (settings.sqlite_dir / name).exists(), f"{name} missing"

    captured = capsys.readouterr().out
    assert "trading_mode=paper" in captured
    # The summary lists each database with its journal mode.
    for name in PHASE2_DATABASES:
        assert name in captured


def test_init_db_is_idempotent(temp_data_dir):
    assert init_db_main() == 0
    # Running a second time must not fail and must not duplicate tables.
    assert init_db_main() == 0
