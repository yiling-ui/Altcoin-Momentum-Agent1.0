"""Phase 11B - cadence-driven Test Data Export scheduler.

Wraps Phase 8.5 :class:`TestDataExportService` with a cadence so
the cloud loop fires one /export_test_data 24h-equivalent on first
boot and then every ``export_interval_hours`` afterward. Each fire
goes through the SAME service the Telegram export bridge uses; the
scheduler does NOT re-implement redaction / manifest / summary.

The scheduler is **never blocking**. The supervisor calls
:meth:`tick(clock_ms=...)` on its own cadence; the scheduler decides
whether the cadence has expired and runs at most one export per
tick.

Phase 11B boundary
------------------

The scheduler:

  - opens NO socket
  - imports NO exchange / LLM / Telegram SDK
  - reads NO ``os.environ``
  - defines NO write surface
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

from app.core.clock import now_ms
from app.exports.service import ExportError, ExportResult, TestDataExportService


@dataclass(frozen=True)
class ExportTick:
    """One scheduler observation. ``ran=True`` iff the scheduler called
    the underlying :class:`TestDataExportService` on this tick."""

    ran: bool
    reason: str
    result: Optional[ExportResult] = None
    next_due_ms: int = 0
    error: Optional[str] = None

    def to_payload(self) -> dict[str, object]:
        return {
            "ran": bool(self.ran),
            "reason": self.reason,
            "next_due_ms": int(self.next_due_ms),
            "error": self.error,
            "result_zip": (
                str(self.result.zip_path) if self.result is not None else None
            ),
            "bytes_written": (
                int(self.result.bytes_written)
                if self.result is not None
                else None
            ),
            "export_id": (
                self.result.manifest.export_id
                if self.result is not None
                else None
            ),
        }


class ExportScheduler:
    """Cadence-driven Phase 8.5 export.

    Construct once per supervisor boot. The first call to
    :meth:`tick` with ``run_on_first_call=True`` fires immediately so
    the operator sees a fresh manifest on day one (per Phase 11B
    brief: "云端首次启动后，立即运行 /export_test_data 24h"). Subsequent
    calls fire every ``interval_hours``.
    """

    def __init__(
        self,
        *,
        service: TestDataExportService,
        interval_hours: int = 24,
        range_label: str = "24h",
        type_filter: str = "all",
        output_dir: Path | None = None,
        run_on_first_call: bool = True,
    ) -> None:
        if interval_hours <= 0:
            raise ValueError(
                f"interval_hours must be > 0; got {interval_hours}"
            )
        self._service = service
        self._interval_ms = int(interval_hours) * 3600 * 1000
        self._range_label = str(range_label)
        self._type_filter = str(type_filter)
        self._output_dir = (
            Path(output_dir) if output_dir is not None else service.output_dir
        )
        self._run_on_first_call = bool(run_on_first_call)
        self._last_run_ms: int | None = None
        self._tick_count: int = 0
        self._success_count: int = 0
        self._failure_count: int = 0
        self._last_result: ExportResult | None = None
        self._last_error: str | None = None

    @property
    def service(self) -> TestDataExportService:
        return self._service

    @property
    def interval_hours(self) -> float:
        return self._interval_ms / 3_600_000.0

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @property
    def last_run_ms(self) -> int | None:
        return self._last_run_ms

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def success_count(self) -> int:
        return self._success_count

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def last_result(self) -> ExportResult | None:
        return self._last_result

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # ------------------------------------------------------------------
    def tick(self, *, clock_ms: int | None = None) -> ExportTick:
        """Possibly run one export. Always returns an :class:`ExportTick`."""
        clock = int(clock_ms) if clock_ms is not None else now_ms()
        self._tick_count += 1
        if not self._should_run(clock):
            return ExportTick(
                ran=False,
                reason="not_due",
                next_due_ms=self._next_due_ms(),
            )
        return self._run_now(clock_ms=clock, reason="cadence")

    def force_run(self, *, clock_ms: int | None = None) -> ExportTick:
        """Run an export NOW regardless of cadence.

        Used by the Phase 11B brief's first-boot rule: "立即运行
        /export_test_data 24h"."""
        clock = int(clock_ms) if clock_ms is not None else now_ms()
        return self._run_now(clock_ms=clock, reason="forced")

    # ------------------------------------------------------------------
    def _should_run(self, clock_ms: int) -> bool:
        if self._last_run_ms is None:
            return self._run_on_first_call
        return (clock_ms - self._last_run_ms) >= self._interval_ms

    def _next_due_ms(self) -> int:
        if self._last_run_ms is None:
            return 0
        return int(self._last_run_ms + self._interval_ms)

    def _run_now(self, *, clock_ms: int, reason: str) -> ExportTick:
        try:
            result = self._service.export(
                range_label=self._range_label,
                type_filter=self._type_filter,
                clock_ms=clock_ms,
            )
        except ExportError as exc:
            self._failure_count += 1
            self._last_error = str(exc)
            logger.warning(
                "ExportScheduler: export failed (range={}, type={}): {}",
                self._range_label,
                self._type_filter,
                exc,
            )
            return ExportTick(
                ran=False,
                reason="export_error",
                next_due_ms=self._next_due_ms(),
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - scheduler must never raise
            self._failure_count += 1
            self._last_error = str(exc)
            logger.error(
                "ExportScheduler: unexpected exception ({}): {}",
                type(exc).__name__,
                exc,
            )
            return ExportTick(
                ran=False,
                reason="unexpected_exception",
                next_due_ms=self._next_due_ms(),
                error=str(exc),
            )
        self._last_run_ms = int(clock_ms)
        self._success_count += 1
        self._last_result = result
        self._last_error = None
        return ExportTick(
            ran=True,
            reason=reason,
            result=result,
            next_due_ms=self._next_due_ms(),
        )


__all__ = [
    "ExportScheduler",
    "ExportTick",
]
