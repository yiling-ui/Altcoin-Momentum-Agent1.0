"""Phase 11B - Cloud Paper Trading supervisor (Issue #11B).

This package adds the cloud-side run loop that exercises the
Phase 1 - 10D pipeline in paper mode. It is **additive** - every
contract that landed in earlier phases stays unchanged:

  - The five Phase 1 safety flags remain locked.
  - The four ExchangeClientBase write surfaces still raise
    SafeModeViolation (Phase 3).
  - Risk Engine is the single trading-decision gate (Phase 7).
  - LLM stays disabled at boot; LLMGuardedInterpreter short-circuits
    to a degraded result (Phase 10C).
  - Telegram outbound defaults to :class:`FakeTelegramClient`
    (Phase 10D); the refusal-only HTTP skeleton stays intact.
  - Replay (10A) + Reflection (10B) remain read-only.
  - Phase 8.5 :class:`TestDataExportService` is the only path that
    produces a redacted ``.zip`` bundle.

Phase 11B boundary
------------------

Nothing in this package:

  - imports an exchange / LLM / third-party Telegram bot SDK
  - opens a real network socket
  - defines ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - reads ``os.environ`` for credentials (the env-guard reads the
    same ``AMA_*`` runtime flags Phase 1 ``settings.py`` already
    consumes; it never reads an ``api_key`` / ``api_secret`` /
    ``bot_token`` value)
  - mutates the Phase 1 safety lock
  - bypasses the Risk Engine
  - flips ``trading_mode`` to anything other than ``paper``

Public surface
--------------

    PaperCloudConfig            Config loader for app/config/paper_cloud.yaml
    PaperCloudSupervisor        Orchestrator
    PaperCloudSupervisorReport  Result of one acceptance run
    DailyReportBuilder          Daily Markdown report builder
    DailyReportSnapshot         The numbers + Markdown body
    ExportScheduler             Wraps TestDataExportService for cadence
    ExportTick                  One scheduled export
    EnvGuard                    Pre-flight env-var inspection
    EnvGuardReport              Env-guard result
    IncidentDrillHarness        Runs the 8 mandated drills
    IncidentDrillResult         One drill outcome
    DrillStatus                 Pass / fail / skipped
    assert_paper_cloud_safety   Defence-in-depth at every boot
"""

from app.paper_run.config import PaperCloudConfig
from app.paper_run.daily_report import DailyReportBuilder, DailyReportSnapshot
from app.paper_run.env_guard import EnvGuard, EnvGuardReport
from app.paper_run.export_scheduler import ExportScheduler, ExportTick
from app.paper_run.incident_drill import (
    DrillStatus,
    IncidentDrillHarness,
    IncidentDrillResult,
)
from app.paper_run.safety_assert import assert_paper_cloud_safety
from app.paper_run.supervisor import (
    PaperCloudSupervisor,
    PaperCloudSupervisorReport,
)


__all__ = [
    "PaperCloudConfig",
    "PaperCloudSupervisor",
    "PaperCloudSupervisorReport",
    "DailyReportBuilder",
    "DailyReportSnapshot",
    "ExportScheduler",
    "ExportTick",
    "EnvGuard",
    "EnvGuardReport",
    "IncidentDrillHarness",
    "IncidentDrillResult",
    "DrillStatus",
    "assert_paper_cloud_safety",
]
