"""`scripts/init_db.py` smoke test."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings as settings_mod
from app.config.settings import load_settings
from scripts.init_db import main as init_db_main


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        settings_mod.get_settings.cache_clear()


def test_init_db_creates_events_db(temp_data_dir):
    rc = init_db_main()
    assert rc == 0
    settings = load_settings()
    assert (settings.sqlite_dir / "events.db").exists()
