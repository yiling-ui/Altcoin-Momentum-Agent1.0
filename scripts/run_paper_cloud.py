"""Phase 11B - Cloud Paper Trading entry point.

Boots the :class:`PaperCloudSupervisor` in paper mode and runs the
acceptance dry-run end-to-end. The script:

  - Refuses to start unless the Phase 1 safety lock is in force
    (``trading_mode=paper``, ``live_trading_enabled=False``,
    ``right_tail_enabled=False``, ``llm_enabled=False``,
    ``exchange_live_order_enabled=False``).
  - Refuses to start if the env-guard observes a forbidden credential
    env-var or a dangerous ``AMA_*_ENABLED`` truthy value.
  - Drives one paper trade lifecycle, runs the eight incident drills,
    forces a /export_test_data 24h on first boot, builds the daily
    Markdown report, and writes
    ``docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md``.
  - Prints a structured banner and exits 0 on GO, non-zero on
    NO-GO / unexpected exception.

Usage::

    python -m scripts.run_paper_cloud
    python -m scripts.run_paper_cloud --acceptance-dry-run
    python -m scripts.run_paper_cloud --no-banner
    python -m scripts.run_paper_cloud --paper-cloud-config path/to/paper_cloud.yaml

The script never opens a real socket, never imports an exchange /
LLM / Telegram SDK, never reads a credential value.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings  # noqa: E402
from app.core.errors import SafeModeViolation, SafetyViolation  # noqa: E402
from app.paper_run.config import PaperCloudConfig  # noqa: E402
from app.paper_run.supervisor import PaperCloudSupervisor  # noqa: E402


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_paper_cloud",
        description=(
            "Phase 11B Cloud Paper Trading supervisor. Paper mode only. "
            "No live trading. No real exchange order. No credential is "
            "read by this script."
        ),
    )
    parser.add_argument(
        "--paper-cloud-config",
        dest="paper_cloud_config",
        default=None,
        help=(
            "Path to paper_cloud.yaml. Defaults to "
            "app/config/paper_cloud.yaml."
        ),
    )
    parser.add_argument(
        "--acceptance-dry-run",
        dest="acceptance_dry_run",
        action="store_true",
        default=True,
        help=(
            "Run the full Phase 11B acceptance dry-run (default). "
            "Drives one paper trade, eight incident drills, the "
            "first-boot export, the daily report, and the acceptance "
            "report - all in under a minute on CI."
        ),
    )
    parser.add_argument(
        "--no-banner",
        dest="emit_banner",
        action="store_false",
        default=True,
        help="Suppress the boot banner (CI-friendly).",
    )
    parser.add_argument(
        "--no-acceptance-report",
        dest="write_acceptance_report",
        action="store_false",
        default=True,
        help="Do not write docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    paper_cloud = PaperCloudConfig.load(args.paper_cloud_config)

    supervisor = PaperCloudSupervisor(
        settings=settings,
        paper_cloud=paper_cloud,
    )
    try:
        report = supervisor.acceptance_dry_run(
            emit_banner=args.emit_banner,
            write_acceptance_report=args.write_acceptance_report,
        )
    except (SafetyViolation, SafeModeViolation) as exc:
        # The supervisor refuses to start when a safety invariant has
        # drifted. Emit a SHORT message - we never log a credential
        # value - and exit non-zero.
        print(
            f"[AMA-RT] Phase 11B refused to boot: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    if not report.accepted:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
