"""Profit Harvest suggestion rules (Phase 8, Spec §28.5).

Rules:
  - Account 2x (equity >= 2 * initial): suggest withdraw 30%-50% of profit
  - Account 5x (equity >= 5 * initial): suggest withdraw 50%-70% of profit
  - Account 10x (equity >= 10 * initial): suggest withdraw most principal + some profit

Hard rules:
  - This module ONLY produces suggestions.
  - It NEVER executes real withdrawals.
  - It NEVER calls any exchange API.
  - Suggestions are informational only.
"""

from __future__ import annotations

from app.capital.models import HarvestSuggestion


def suggest_harvest(
    *,
    current_equity: float,
    initial_capital: float,
    withdrawn_profit: float = 0.0,
) -> HarvestSuggestion | None:
    """Compute a profit-harvest suggestion based on account multiplier.

    Returns None if the account is not at 2x or above (no suggestion).

    Spec §28.5:
      - 2x: suggest 30%-50% of profit
      - 5x: suggest 50%-70% of profit
      - 10x: suggest most principal + some profit

    The ``profit`` used for calculation is:
        lifetime_equity - initial_capital
    where lifetime_equity = current_equity + withdrawn_profit.
    """
    if initial_capital <= 0:
        return None

    lifetime_equity = current_equity + withdrawn_profit
    multiplier = lifetime_equity / initial_capital
    profit = lifetime_equity - initial_capital

    if multiplier < 2.0 or profit <= 0:
        return None

    if multiplier >= 10.0:
        # Suggest withdrawing most of principal + some profit
        # "提现大部分本金 + 部分利润"
        suggested_min_pct = 0.70
        suggested_max_pct = 0.90
        # Base: principal + portion of profit
        base_amount = initial_capital * 0.8 + profit * 0.3
        suggested_min_amount = min(base_amount * 0.8, current_equity * 0.9)
        suggested_max_amount = min(base_amount * 1.2, current_equity * 0.95)
        message = (
            f"Account at {multiplier:.1f}x. Strongly recommend harvesting "
            f"most of principal + partial profit. "
            f"Suggested range: {suggested_min_amount:.2f} - {suggested_max_amount:.2f} USDT."
        )
    elif multiplier >= 5.0:
        # 50%-70% of profit
        suggested_min_pct = 0.50
        suggested_max_pct = 0.70
        suggested_min_amount = profit * suggested_min_pct
        suggested_max_amount = profit * suggested_max_pct
        # Cap at current equity (can't withdraw more than what's on exchange)
        suggested_min_amount = min(suggested_min_amount, current_equity * 0.9)
        suggested_max_amount = min(suggested_max_amount, current_equity * 0.9)
        message = (
            f"Account at {multiplier:.1f}x. Recommend harvesting "
            f"50%-70% of profit ({suggested_min_amount:.2f} - "
            f"{suggested_max_amount:.2f} USDT)."
        )
    else:
        # 2x-5x: 30%-50% of profit
        suggested_min_pct = 0.30
        suggested_max_pct = 0.50
        suggested_min_amount = profit * suggested_min_pct
        suggested_max_amount = profit * suggested_max_pct
        suggested_min_amount = min(suggested_min_amount, current_equity * 0.9)
        suggested_max_amount = min(suggested_max_amount, current_equity * 0.9)
        message = (
            f"Account at {multiplier:.1f}x. Consider harvesting "
            f"30%-50% of profit ({suggested_min_amount:.2f} - "
            f"{suggested_max_amount:.2f} USDT)."
        )

    return HarvestSuggestion(
        current_equity=current_equity,
        initial_capital=initial_capital,
        lifetime_equity=lifetime_equity,
        multiplier=multiplier,
        suggested_min_pct=suggested_min_pct,
        suggested_max_pct=suggested_max_pct,
        suggested_min_amount=suggested_min_amount,
        suggested_max_amount=suggested_max_amount,
        profit=profit,
        message=message,
    )
