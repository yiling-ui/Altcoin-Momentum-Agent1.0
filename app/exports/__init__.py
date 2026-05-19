"""Phase 8.5 - Test Data Export Service.

Reads from a Phase-2 :class:`app.database.repositories.EventRepository`
and produces a redacted ``.zip`` bundle under
``data/reports/exports/`` containing manifest + summary + per-type
``.jsonl`` shards. Issue contract is documented in
:mod:`app.exports.service`.

Public surface
--------------

    TestDataExportService            export orchestrator
    ExportResult                     return type from ``service.export(...)``
    ExportError                      typed failure
    ExportManifest                   manifest.json shape
    build_summary_report             summary_report.md builder
    redact / forbidden_substrings    redaction helpers
    parse_iso_date / resolve_time_range  CLI / API plumbing

Phase 8.5 boundary
------------------

Nothing in this package opens a socket, imports an exchange / LLM /
Telegram library, or reads ``os.environ`` for a credential. The
service is read-only against events.db and writes only to the
configured output directory.
"""

from app.exports.manifest import ExportManifest
from app.exports.redaction import (
    REDACTED,
    SENSITIVE_KEY_SUBSTRINGS,
    assert_no_forbidden_substrings,
    forbidden_substrings,
    redact,
)
from app.exports.service import (
    ALLOWED_RANGE_LABELS,
    ALLOWED_TYPE_FILTERS,
    DEFAULT_MAX_ZIP_BYTES,
    ExportError,
    ExportResult,
    TestDataExportService,
    parse_iso_date,
    resolve_time_range,
)
from app.exports.summary import build_summary_report, collect_summary_stats

__all__ = [
    "ExportManifest",
    "ExportResult",
    "ExportError",
    "TestDataExportService",
    "ALLOWED_RANGE_LABELS",
    "ALLOWED_TYPE_FILTERS",
    "DEFAULT_MAX_ZIP_BYTES",
    "parse_iso_date",
    "resolve_time_range",
    "build_summary_report",
    "collect_summary_stats",
    "redact",
    "forbidden_substrings",
    "assert_no_forbidden_substrings",
    "SENSITIVE_KEY_SUBSTRINGS",
    "REDACTED",
]
