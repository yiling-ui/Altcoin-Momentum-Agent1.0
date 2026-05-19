"""Phase 7 - Circuit Breaker tests (Issue #7, Spec §27.2)."""

from __future__ import annotations

from app.core.enums import CircuitBreakerState
from app.risk.circuit_breaker import (
    ConsecutiveLossCircuitBreaker,
    DailyLossCircuitBreaker,
)


# ---------------------------------------------------------------------------
# Consecutive losses
# ---------------------------------------------------------------------------
def test_consecutive_loss_breaker_opens_at_threshold():
    """Issue #7 acceptance criterion 12: 5 consecutive losses must
    open the breaker."""
    breaker = ConsecutiveLossCircuitBreaker(threshold=5)
    for _ in range(4):
        assert breaker.record_loss() is CircuitBreakerState.CLOSED
    assert breaker.record_loss() is CircuitBreakerState.OPEN_CONSECUTIVE_LOSS
    assert breaker.state.is_open
    assert breaker.consecutive_losses == 5


def test_consecutive_loss_breaker_winning_resets_counter_when_closed():
    breaker = ConsecutiveLossCircuitBreaker(threshold=5)
    breaker.record_loss()
    breaker.record_loss()
    breaker.record_win()
    assert breaker.consecutive_losses == 0
    assert breaker.state is CircuitBreakerState.CLOSED


def test_consecutive_loss_breaker_remains_open_after_win():
    """Phase 7 hard rule: a winning trade does NOT auto-close the
    breaker. Only an explicit reset() does."""
    breaker = ConsecutiveLossCircuitBreaker(threshold=2)
    breaker.record_loss()
    breaker.record_loss()
    assert breaker.state is CircuitBreakerState.OPEN_CONSECUTIVE_LOSS
    breaker.record_win()
    assert breaker.state is CircuitBreakerState.OPEN_CONSECUTIVE_LOSS


def test_consecutive_loss_breaker_reset_returns_to_closed():
    breaker = ConsecutiveLossCircuitBreaker(threshold=2)
    breaker.record_loss()
    breaker.record_loss()
    breaker.reset()
    assert breaker.state is CircuitBreakerState.CLOSED
    assert breaker.consecutive_losses == 0


# ---------------------------------------------------------------------------
# Daily loss
# ---------------------------------------------------------------------------
def test_daily_loss_breaker_opens_at_threshold():
    """Issue #7 acceptance criterion 13: single-day loss reaches the
    threshold, breaker opens."""
    breaker = DailyLossCircuitBreaker(
        max_daily_loss_pct=0.05, initial_capital=1000.0
    )
    assert breaker.record_loss(loss_amount=20) is CircuitBreakerState.CLOSED
    assert breaker.record_loss(loss_amount=20) is CircuitBreakerState.CLOSED
    assert (
        breaker.record_loss(loss_amount=20)
        is CircuitBreakerState.OPEN_DAILY_LOSS
    )


def test_daily_loss_breaker_closed_when_below_threshold():
    breaker = DailyLossCircuitBreaker(
        max_daily_loss_pct=0.05, initial_capital=1000.0
    )
    breaker.record_loss(loss_amount=20)
    assert breaker.cumulative_loss_today == 20
    assert breaker.state is CircuitBreakerState.CLOSED


def test_daily_loss_breaker_does_not_open_with_zero_initial_capital():
    """Defensive: a misconfigured caller must not get a free pass.

    With initial_capital=0 the breaker stays CLOSED but the engine's
    other gates (live_trading_disabled etc) catch the request first.
    """
    breaker = DailyLossCircuitBreaker(
        max_daily_loss_pct=0.05, initial_capital=0.0
    )
    breaker.record_loss(loss_amount=1000)
    assert breaker.state is CircuitBreakerState.CLOSED


def test_daily_loss_breaker_record_win_does_not_reduce_loss():
    """Spec §27.2 measures GROSS daily loss, not net PnL."""
    breaker = DailyLossCircuitBreaker(
        max_daily_loss_pct=0.05, initial_capital=1000.0
    )
    breaker.record_loss(loss_amount=30)
    breaker.record_win(profit_amount=50)
    assert breaker.cumulative_loss_today == 30


def test_daily_loss_breaker_remains_open_after_reset_until_explicit_reset():
    breaker = DailyLossCircuitBreaker(
        max_daily_loss_pct=0.05, initial_capital=1000.0
    )
    breaker.record_loss(loss_amount=60)
    assert breaker.state.is_open
    # A new loss does not change the state.
    breaker.record_loss(loss_amount=10)
    assert breaker.state.is_open
    breaker.reset()
    assert breaker.state is CircuitBreakerState.CLOSED
    assert breaker.cumulative_loss_today == 0.0


def test_daily_loss_breaker_zero_amount_is_no_op():
    breaker = DailyLossCircuitBreaker(
        max_daily_loss_pct=0.05, initial_capital=1000.0
    )
    breaker.record_loss(loss_amount=0.0)
    assert breaker.cumulative_loss_today == 0
