"""Phase 8.5 - Test Data Export CLI.

Lives under ``app/exports`` so it is testable in isolation; the
entry-point script ``scripts/export_test_data.py`` just imports
:func:`main` and forwards the command line.

Issue contract examples:

    python -m scripts.export_test_data --range 24h
    python -m scripts.export_test_data --range 7d
    python -m scripts.export_test_data --type rejections
    python -m scripts.export_test_data --start 2026-05-01 --end 2026-05-07

Output:

    data/reports/exports/ama_rt_test_data_<timestamp>.zip

Phase 8.5 boundary
------------------

The CLI never opens a socket, never reads ``os.environ`` for a
credential, never instantiates an exchange / LLM / Telegram client,
and never modifies the Phase 1 safety lock.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from app.config.settings import get_settings
from app.database.connection import open_sqlite
from app.database.repositories import EventRepository
from app.exports.service import (
    ALLOWED_RANGE_LABELS,
    ALLOWED_TYPE_FILTERS,
    DEFAULT_MAX_ZIP_BYTES,
    ExportError,
    TestDataExportService,
    parse_iso_date,
)


# Default landing pad for exports (Issue contract).
EXPORT_SUBDIR = Path("reports") / "exports"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_test_data",
        description=(
            "AMA-RT Phase 8.5 - Test Data Export. Reads events.db and "
            "writes a redacted .zip bundle to data/reports/exports/. "
            "Paper-mode only; no live trading; no real network."
        ),
    )
    parser.add_argument(
        "--range",
        dest="range_label",
        choices=sorted(ALLOWED_RANGE_LABELS),
        default="24h",
        help="Time range. Default: 24h.",
    )
    parser.add_argument(
        "--start",
        dest="start",
        default=None,
        help=(
            "Range start (ISO 8601 date or datetime UTC). Required when "
            "--range range; ignored otherwise."
        ),
    )
    parser.add_argument(
        "--end",
        dest="end",
        default=None,
        help=(
            "Range end (ISO 8601 date or datetime UTC). Required when "
            "--range range; ignored otherwise."
        ),
    )
    parser.add_argument(
        "--type",
        dest="type_filter",
        choices=sorted(ALLOWED_TYPE_FILTERS),
        default="all",
        help="Type filter. Default: all.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help=(
            "Override the output directory. Defaults to "
            "<settings.data_dir>/reports/exports."
        ),
    )
    parser.add_argument(
        "--max-zip-bytes",
        dest="max_zip_bytes",
        type=int,
        default=DEFAULT_MAX_ZIP_BYTES,
        help=(
            "Refuse to ship a bundle larger than this. The Issue "
            "contract reserves Telegram-side fragmentation for "
            "Issue #10."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Returns 0 on success, non-zero on error.
    """
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    settings = get_settings()

    # Refuse to operate if the Phase 1 safety lock has drifted - the
    # CLI is read-only but we still want to fail loudly under a bad
    # config.
    if settings.trading_mode != "paper":
        print(
            "[ama-rt][export] refusing: trading_mode != paper",
            file=sys.stderr,
        )
        return 2

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else (settings.data_dir / EXPORT_SUBDIR)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    sqlite_dir = settings.sqlite_dir
    events_db = sqlite_dir / "events.db"
    if not events_db.exists():
        print(
            f"[ama-rt][export] events.db not found at {events_db}; "
            f"run `python -m scripts.init_db` first.",
            file=sys.stderr,
        )
        return 3

    start_ms: int | None = None
    end_ms: int | None = None
    if args.range_label == "range":
        if args.start is None or args.end is None:
            print(
                "[ama-rt][export] --range range requires --start and --end",
                file=sys.stderr,
            )
            return 4
        try:
            start_ms = parse_iso_date(args.start)
            end_ms = parse_iso_date(args.end)
        except ExportError as exc:
            print(f"[ama-rt][export] {exc}", file=sys.stderr)
            return 4

    conn = open_sqlite(events_db)
    try:
        repo = EventRepository(conn)
        service = TestDataExportService(
            event_repo=repo,
            trading_mode=settings.trading_mode,
            output_dir=output_dir,
            max_zip_bytes=args.max_zip_bytes,
        )
        try:
            result = service.export(
                range_label=args.range_label,
                start_ms=start_ms,
                end_ms=end_ms,
                type_filter=args.type_filter,
            )
        except ExportError as exc:
            print(f"[ama-rt][export] {exc}", file=sys.stderr)
            return 5

        manifest = result.manifest
        print(
            f"[ama-rt][export] OK file={result.zip_path} "
            f"bytes={result.bytes_written} events={manifest.event_count} "
            f"opportunities={manifest.opportunity_count} "
            f"rejected={manifest.risk_rejected_count} "
            f"capital={manifest.capital_event_count} "
            f"state_transitions={manifest.state_transition_count} "
            f"redaction_applied={manifest.redaction_applied}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover - exercised via scripts/
    raise SystemExit(main())
