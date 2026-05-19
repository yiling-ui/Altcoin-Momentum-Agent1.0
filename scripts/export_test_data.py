"""Phase 8.5 CLI entry-point for the Test Data Export Service.

Usage:

    python -m scripts.export_test_data --range 24h
    python -m scripts.export_test_data --range 7d
    python -m scripts.export_test_data --type rejections
    python -m scripts.export_test_data --start 2026-05-01 --end 2026-05-07

The actual logic lives in :mod:`app.exports.cli`; this script is a
1-line shim so the Issue-mandated invocation works out of the box.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.exports.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
