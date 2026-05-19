"""Phase 8.5 - CLI tests (Issue #8.5).

Drives ``app.exports.cli.main`` end-to-end against a fresh on-disk
events.db and asserts the resulting zip is well-formed.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app.config import settings as settings_mod
from app.core.events import Event, EventType
from app.database.connection import open_sqlite
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.exports.cli import main as cli_main


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    events_db = sqlite_dir / "events.db"
    conn = open_sqlite(events_db)
    apply_schema(conn)
    repo = EventRepository(conn)
    repo.append_event(
        Event(
            event_type=EventType.RISK_REJECTED,
            source_module="phase8_5_test",
            symbol="PEPEUSDT",
            payload={"reasons": ["live_trading_disabled"]},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.STATE_TRANSITION,
            source_module="state_machine",
            symbol="PEPEUSDT",
            payload={"from": "no_trade", "to": "observe"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.CAPITAL_DEPOSIT,
            source_module="capital",
            payload={"amount": 100.0, "currency": "USDT"},
        )
    )
    conn.close()
    try:
        yield tmp_path
    finally:
        settings_mod.get_settings.cache_clear()


def _newest_zip(directory: Path) -> Path:
    zips = sorted(directory.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    assert zips, f"no zip produced in {directory}"
    return zips[-1]


def test_cli_24h_creates_zip(temp_data_dir):
    rc = cli_main(["--range", "24h"])
    assert rc == 0
    out_dir = temp_data_dir / "reports" / "exports"
    assert out_dir.exists()
    zip_path = _newest_zip(out_dir)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "summary_report.md" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["redaction_applied"] is True


def test_cli_7d_creates_zip(temp_data_dir):
    rc = cli_main(["--range", "7d"])
    assert rc == 0
    zip_path = _newest_zip(temp_data_dir / "reports" / "exports")
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["type_filter"] == "all"


def test_cli_today_filter_includes_recent_events(temp_data_dir):
    rc = cli_main(["--range", "today"])
    assert rc == 0


def test_cli_type_rejections_emits_only_rejected(temp_data_dir):
    rc = cli_main(["--type", "rejections", "--range", "24h"])
    assert rc == 0
    zip_path = _newest_zip(temp_data_dir / "reports" / "exports")
    with zipfile.ZipFile(zip_path) as zf:
        body = zf.read("risk_decisions.jsonl").decode("utf-8")
        assert "RISK_REJECTED" in body
        assert "RISK_APPROVED" not in body


def test_cli_range_with_explicit_start_end(temp_data_dir):
    rc = cli_main(
        [
            "--range",
            "range",
            "--start",
            "2025-01-01",
            "--end",
            "2030-01-01",
            "--type",
            "all",
        ]
    )
    assert rc == 0
    zip_path = _newest_zip(temp_data_dir / "reports" / "exports")
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["time_range_start"] < manifest["time_range_end"]


def test_cli_range_without_start_or_end_returns_error(temp_data_dir, capsys):
    rc = cli_main(["--range", "range"])
    assert rc == 4


def test_cli_oversized_zip_returns_error(temp_data_dir, capsys):
    rc = cli_main(["--range", "24h", "--max-zip-bytes", "1"])
    assert rc == 5


def test_cli_missing_events_db_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    try:
        rc = cli_main(["--range", "24h"])
        assert rc == 3
    finally:
        settings_mod.get_settings.cache_clear()
