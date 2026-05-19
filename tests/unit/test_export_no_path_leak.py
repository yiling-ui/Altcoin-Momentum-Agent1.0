"""Phase 8.5 - end-to-end path-leak guard for the export bundle (Issue #8.5).

The Phase 8.5 production self-check (#2) requires the zip filename,
``manifest.json``, ``summary_report.md``, and every per-type
``.jsonl`` file inside the bundle to be free of server-side absolute
paths. This test seeds an :class:`EventRepository` with payloads
that *deliberately* contain path-shaped strings, runs a real export
end-to-end, and asserts every byte of the bundle survives the
redaction layer.

The redactor strips any string starting with one of the well-known
absolute-path prefixes (``/home/``, ``/root/``, ``/Users/``,
``/projects/``, ``/data/``, ``/tmp/``, ``/var/``, ``/etc/``,
``/usr/``, ``/opt/``, ``/srv/``, ``/mnt/``, ``/private/var/``,
``/private/etc/``, ``/workspace/``, ``/app/``), Windows drive paths
(``C:\\...``, ``D:/...``), UNC shares (``\\\\server\\share``), and
``~/`` user-home expansions. This test pins the contract.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

from app.core.events import Event, EventType
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.exports import TestDataExportService


# Ten path-shaped substrings the export bundle MUST never contain
# verbatim after redaction. The list intentionally over-covers the
# shapes operators are likely to find in production logs (operator
# home, sandbox root, deployment root, transient dir, system
# config, Windows drive, UNC).
PATH_LEAK_NEEDLES: tuple[str, ...] = (
    "/home/operator/",
    "/root/.ssh/",
    "/Users/alice/",
    "/projects/sandbox/",
    "/data/operator/",
    "/tmp/ama-rt-cache/",
    "/var/lib/ama/",
    "/etc/secrets/",
    "/opt/ama/",
    "/srv/exports/",
    "C:\\Users\\Alice\\",
    "D:/private/",
    "\\\\fileserver\\share\\",
)


def _open_repo() -> EventRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return EventRepository(conn)


def _seed_payloads_with_paths(repo: EventRepository, base_ts: int) -> None:
    """Seed every Phase 8.5 export shard with at least one event
    that *claims* to carry a server-side path so we can confirm
    redaction strips it before the bundle is written."""
    # RISK_REJECTED -> risk_decisions.jsonl
    repo.append_event(Event(
        event_type=EventType.RISK_REJECTED,
        source_module="phase8_5_path_leak_test",
        symbol="BTCUSDT",
        timestamp=base_ts,
        payload={
            "reasons": ["live_trading_disabled"],
            "operator_home": "/home/operator/secret.db",
            "sandbox_path": "/projects/sandbox/Altcoin-Momentum-Agent1.0/data/sqlite/events.db",
            "windows_path": "C:\\Users\\Alice\\AppData\\config",
            "unc_path": "\\\\fileserver\\share\\secret",
        },
    ))
    # STATE_TRANSITION -> state_transitions.jsonl
    repo.append_event(Event(
        event_type=EventType.STATE_TRANSITION,
        source_module="phase8_5_path_leak_test",
        symbol="BTCUSDT",
        timestamp=base_ts + 1,
        payload={
            "from": "no_trade",
            "to": "observe",
            "trace_dir": "/tmp/ama-rt-cache/run-1234/",
            "log_path": "/var/lib/ama/state.log",
        },
    ))
    # CAPITAL_DEPOSIT -> capital_events.jsonl
    repo.append_event(Event(
        event_type=EventType.CAPITAL_DEPOSIT,
        source_module="phase8_5_path_leak_test",
        timestamp=base_ts + 2,
        payload={
            "amount": 0.0,
            "deposit_type": "external",
            "audit_dir": "/data/operator/state",
            "linux_etc": "/etc/secrets/api.yaml",
            "tilde": "~/secrets/key",
        },
    ))


def _all_bundle_files(zip_path: Path) -> dict[str, str]:
    """Return ``{name: utf8_text}`` for every member of the zip."""
    contents: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            contents[name] = zf.read(name).decode("utf-8")
    return contents


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_export_zip_filename_does_not_contain_absolute_paths(tmp_path):
    """The ``zip_path.name`` is the filename only - it is the only
    string a Telegram caption / log line will publish. It MUST be a
    bare basename (``ama_rt_test_data_<ts>_<id>.zip``)."""
    repo = _open_repo()
    service = TestDataExportService(
        event_repo=repo,
        trading_mode="paper",
        app_version="phase8_5_path_leak_test",
        output_dir=tmp_path / "exports",
    )
    result = service.export(
        range_label="range",
        start_ms=0,
        end_ms=10_000,
        type_filter="all",
    )
    name = result.zip_path.name
    for char in (":", "\\"):
        assert char not in name, (
            f"zip filename {name!r} contains path separator {char!r}"
        )
    # filename must NOT contain any of the path-leak needles either
    # (paranoid; the zip basename is generated from a uuid so this is
    # belt-and-braces).
    for needle in PATH_LEAK_NEEDLES:
        assert needle not in name, (
            f"zip filename {name!r} leaks server path {needle!r}"
        )


def test_manifest_json_does_not_contain_absolute_paths(tmp_path):
    repo = _open_repo()
    _seed_payloads_with_paths(repo, base_ts=1_700_000_000_000)
    service = TestDataExportService(
        event_repo=repo,
        trading_mode="paper",
        app_version="phase8_5_path_leak_test",
        output_dir=tmp_path / "exports",
    )
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_000_000 + 1_000_000,
        type_filter="all",
    )
    contents = _all_bundle_files(result.zip_path)
    manifest = contents["manifest.json"]
    # parse to make sure files[].name is a basename
    parsed = json.loads(manifest)
    for entry in parsed.get("files", []):
        n = entry.get("name", "")
        assert "/" not in n and "\\" not in n, (
            f"manifest.files[].name leaks a path: {n!r}"
        )
    # raw substring check on the manifest text
    for needle in PATH_LEAK_NEEDLES:
        assert needle not in manifest, (
            f"manifest.json leaks path {needle!r}"
        )


def test_summary_report_does_not_contain_absolute_paths(tmp_path):
    repo = _open_repo()
    _seed_payloads_with_paths(repo, base_ts=1_700_000_000_000)
    service = TestDataExportService(
        event_repo=repo,
        trading_mode="paper",
        app_version="phase8_5_path_leak_test",
        output_dir=tmp_path / "exports",
    )
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_000_000 + 1_000_000,
        type_filter="all",
    )
    contents = _all_bundle_files(result.zip_path)
    summary = contents["summary_report.md"]
    for needle in PATH_LEAK_NEEDLES:
        assert needle not in summary, (
            f"summary_report.md leaks path {needle!r}"
        )


def test_every_jsonl_shard_does_not_contain_absolute_paths(tmp_path):
    """The per-type ``.jsonl`` shards are where event payloads land.
    Even when an event author accidentally serialises an absolute
    path, the redaction layer must strip it before the shard is
    written."""
    repo = _open_repo()
    _seed_payloads_with_paths(repo, base_ts=1_700_000_000_000)
    service = TestDataExportService(
        event_repo=repo,
        trading_mode="paper",
        app_version="phase8_5_path_leak_test",
        output_dir=tmp_path / "exports",
    )
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_000_000 + 1_000_000,
        type_filter="all",
    )
    contents = _all_bundle_files(result.zip_path)
    jsonl_files = {
        name: text for name, text in contents.items() if name.endswith(".jsonl")
    }
    assert jsonl_files, "expected at least one .jsonl in the bundle"
    for name, text in jsonl_files.items():
        # Every string under each event payload must be redacted
        # before it lands here. Spot-check by raw substring.
        for needle in PATH_LEAK_NEEDLES:
            assert needle not in text, (
                f"{name} leaks server path {needle!r}"
            )


def test_redacted_paths_are_replaced_by_redacted_marker(tmp_path):
    """Companion check: confirm the redaction *did* fire (rather than
    the test trivially passing because the seeded paths never reached
    the bundle for some unrelated reason)."""
    repo = _open_repo()
    _seed_payloads_with_paths(repo, base_ts=1_700_000_000_000)
    service = TestDataExportService(
        event_repo=repo,
        trading_mode="paper",
        app_version="phase8_5_path_leak_test",
        output_dir=tmp_path / "exports",
    )
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_000_000 + 1_000_000,
        type_filter="all",
    )
    contents = _all_bundle_files(result.zip_path)
    events_text = contents["events.jsonl"]
    # The seeded RISK_REJECTED carries operator_home / sandbox_path /
    # windows_path / unc_path - all four must show up redacted in
    # events.jsonl.
    assert events_text.count("[REDACTED]") >= 4
