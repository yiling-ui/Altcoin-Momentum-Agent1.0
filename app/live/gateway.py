"""Live Execution Gateway (PR110 - Live Foundation v0).

The single, reserved entry point for the (future) live order path.
PR110 wires the safety gates that protect it but DOES NOT implement
real order placement.

Submission flow:
  1. :class:`app.live.path_isolation.LivePathIsolationGuard` - refuses
     any order intent whose ``source`` is not ``OrderSource.LIVE``
     (blind / replay / sim / paper-shadow are isolated).
  2. :class:`app.live.runtime_mode.LiveModeGuard` - refuses any real
     order unless ``LIVE_LIMITED`` is fully armed via the operator
     confirmation handshake.
  3. PR110 hard stop - even when (1) and (2) pass, PR110 raises
     :class:`SafeModeViolation` because no real ``LiveExchangeAdapter``
     exists yet.

PR110 boundary: no real order is ever placed; no private Binance API is
contacted; no Phase 1 safety flag is flipped.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import SafeModeViolation
from app.live.path_isolation import LiveOrderIntent, LivePathIsolationGuard
from app.live.runtime_mode import LiveModeGuard

LIVE_EXECUTION_GATEWAY_MODULE = "live.gateway"


class LiveExecutionGateway:
    """Reserved entry point for the live order path (PR110: refuses all)."""

    def __init__(
        self,
        *,
        isolation_guard: LivePathIsolationGuard,
        mode_guard: LiveModeGuard,
        event_repo: Any | None = None,
    ) -> None:
        self._isolation = isolation_guard
        self._mode_guard = mode_guard
        self._event_repo = event_repo

    def submit_order(self, intent: LiveOrderIntent) -> None:
        """Attempt to submit a live order intent.

        Always ends in a refusal in PR110:
          - non-LIVE source -> :class:`LivePathIsolationViolation`.
          - LIVE source but mode not armed -> :class:`LiveModeViolation`.
          - LIVE source + armed -> :class:`SafeModeViolation` (no
            execution adapter exists in PR110).
        """
        # 1. Isolation: only OrderSource.LIVE may pass.
        self._isolation.assert_live_path(intent)
        # 2. Mode: LIVE_LIMITED must be armed.
        self._mode_guard.assert_live_orders_allowed()
        # 3. PR110 has no live execution adapter.
        raise SafeModeViolation(
            "LiveExecutionGateway.submit_order is forbidden in PR110: the "
            "live execution adapter is not implemented. PR110 only builds "
            "the live safety foundation (path isolation, runtime mode "
            "guard, capital profile ladder, capital event contract, "
            "right-tail leverage gate, Telegram operator contract). Real "
            "order placement lands in a later PR behind the Risk Engine."
        )


__all__ = [
    "LIVE_EXECUTION_GATEWAY_MODULE",
    "LiveExecutionGateway",
]
