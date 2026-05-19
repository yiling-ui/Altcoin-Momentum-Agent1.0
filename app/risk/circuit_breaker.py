"""Phase 7 Circuit Breakers (Issue #7, Spec §27.2).

Two breakers, both stateless except for an in-memory counter / sum:

  - :class:`ConsecutiveLossCircuitBreaker` opens after N consecutive
    losing trades (Spec §27.2 hard rule "连续亏损达到阈值"). Default
    threshold is the YAML default (5).
  - :class:`DailyLossCircuitBreaker` opens once today's cumulative
    realised loss has exceeded ``max_daily_loss_pct * initial_capital``
    (Spec §27.2 hard rule "单日回撤达到阈值"). Default threshold is the
    YAML default (5%).

Phase 7 ships the breakers and lets the Risk Engine read their state
through ``state``. Updating the breakers from realised-PnL events is
the responsibility of Issue #8 (Capital Flow Engine) and Issue #9
(Reconciliation): they call :meth:`record_loss` and
:meth:`record_win` whenever a position is closed. Phase 7 keeps the
counters in process memory; they will be persisted properly with
``capital.db`` in Issue #8.

A breaker that has been opened MUST be re-armed explicitly via
:meth:`reset` (Reconciliation / human, Issue #9 / #10). It cannot
be un-blocked just because the next trade happened to win.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.enums import CircuitBreakerState


# ---------------------------------------------------------------------------
# Consecutive-loss breaker
# ---------------------------------------------------------------------------
@dataclass
class ConsecutiveLossCircuitBreaker:
    """Open after ``threshold`` consecutive losing trades.

    Phase 7 hard rule "止损未确认禁止新开仓" + "持仓未知禁止新开仓"
    are enforced separately on :class:`RiskRequest`; this breaker
    only counts realised losses.
    """

    threshold: int = 5
    consecutive_losses: int = 0
    state: CircuitBreakerState = CircuitBreakerState.CLOSED

    def record_loss(self) -> CircuitBreakerState:
        if self.state.is_open:
            return self.state
        self.consecutive_losses += 1
        if self.consecutive_losses >= self.threshold:
            self.state = CircuitBreakerState.OPEN_CONSECUTIVE_LOSS
        return self.state

    def record_win(self) -> CircuitBreakerState:
        # A winning trade resets the counter (but never closes an
        # already-open breaker - Phase 7 requires an explicit reset).
        if not self.state.is_open:
            self.consecutive_losses = 0
        return self.state

    def reset(self) -> None:
        self.consecutive_losses = 0
        self.state = CircuitBreakerState.CLOSED


# ---------------------------------------------------------------------------
# Daily-loss breaker
# ---------------------------------------------------------------------------
def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class DailyLossCircuitBreaker:
    """Open once cumulative realised loss for the current UTC day
    exceeds ``max_daily_loss_pct * initial_capital``.

    The breaker rolls over on UTC date change automatically (i.e. a
    new day starts with cumulative_loss=0). Phase 7 ships the breaker;
    Issue #8 will replace the in-memory counter with the
    ``capital.db.capital_snapshots`` lookup.
    """

    max_daily_loss_pct: float = 0.05
    initial_capital: float = 0.0
    today_utc: str = ""
    cumulative_loss_today: float = 0.0
    state: CircuitBreakerState = CircuitBreakerState.CLOSED

    def __post_init__(self) -> None:
        if not self.today_utc:
            self.today_utc = _utc_today()

    def _maybe_rollover(self) -> None:
        today = _utc_today()
        if today != self.today_utc:
            self.today_utc = today
            self.cumulative_loss_today = 0.0
            # Date change does NOT auto-close an already-open breaker;
            # Phase 7 requires an explicit reset.

    def record_loss(self, *, loss_amount: float) -> CircuitBreakerState:
        if loss_amount <= 0:
            return self.state
        self._maybe_rollover()
        if self.state.is_open:
            return self.state
        self.cumulative_loss_today += loss_amount
        if self.initial_capital > 0:
            ratio = self.cumulative_loss_today / self.initial_capital
            if ratio >= self.max_daily_loss_pct:
                self.state = CircuitBreakerState.OPEN_DAILY_LOSS
        return self.state

    def record_win(self, *, profit_amount: float) -> CircuitBreakerState:
        # A winning trade does NOT reduce ``cumulative_loss_today`` -
        # the spec measures *gross* daily loss, not net daily PnL.
        self._maybe_rollover()
        return self.state

    def reset(self) -> None:
        self.cumulative_loss_today = 0.0
        self.today_utc = _utc_today()
        self.state = CircuitBreakerState.CLOSED
