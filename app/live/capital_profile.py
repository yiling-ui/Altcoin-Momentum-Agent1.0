"""Capital Profile Ladder (PR110 - Live Foundation v0).

AMA-RT is a crypto altcoin right-tail capture / adaptive market
operating system. Its capital base must be able to scale from a 1 USDT
micro-probe all the way to a 10,000,000 USDT capital-preservation
account WITHOUT re-using the 10U method at every scale. A 10U probe can
be aggressive (concentrate, push leverage on a strong right-tail
structure). A 10,000,000U account cannot: fill depth, slippage,
staged exit, profit harvesting and withdrawal all dominate.

This module ships:

  - :class:`CapitalProfileId` - the closed ladder of profile ids.
  - :class:`CapitalProfile` - the per-stage constraint bundle.
  - :data:`CAPITAL_PROFILE_LADDER` - the default ladder (L0 .. L8).
  - deterministic helpers to look a profile up, detect a
    profile / equity mismatch, and *suggest* (never auto-apply) an
    escalation / de-escalation.

PR110 boundary
--------------
- The ladder is a CONSTRAINT model, not a trade engine. Nothing here
  places an order, moves capital, or flips a Phase 1 safety flag.
- Capital profile escalation is NEVER automatic. The system may DETECT
  a mismatch and SUGGEST a change, but the operator must explicitly
  re-select the profile. A bare restart can never silently escalate.
- ``L0_SHADOW`` never allows real orders.
- ``L1_10U_PROBE`` allows only a tiny real capital base
  (``max_account_capital_usdt = 10``).
- Larger profiles are defined (schema + default constraints) but NOT
  auto-enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.enums import LiveRuntimeMode

# A sentinel for "no upper bound" on a profile's equity band. Kept as a
# real float so comparisons and JSON serialisation stay simple.
EQUITY_UNBOUNDED: float = float("inf")

# Hard rule, surfaced as a module constant so tests and reviewers can
# assert it directly: capital profile escalation is NEVER automatic.
AUTO_ESCALATION_ALLOWED: bool = False


class CapitalProfileId(str, Enum):
    """Closed ladder of capital-stage profile ids (PR110).

    The ladder spans a 1 USDT micro-probe to a 10,000,000 USDT
    capital-preservation account. The ids are ordered; the order is
    used to decide escalation (up) vs. de-escalation (down). NONE of
    the transitions happen automatically.
    """

    L0_SHADOW = "L0_SHADOW"
    L1_1U_MICRO_PROBE = "L1_1U_MICRO_PROBE"
    L1_10U_PROBE = "L1_10U_PROBE"
    L2_25U_50U_SCOUT = "L2_25U_50U_SCOUT"
    L3_100U_ATTACK_TEST = "L3_100U_ATTACK_TEST"
    L4_1K_GROWTH = "L4_1K_GROWTH"
    L5_10K_PROFIT_PROTECTION = "L5_10K_PROFIT_PROTECTION"
    L6_100K_LIQUIDITY_CONSTRAINED = "L6_100K_LIQUIDITY_CONSTRAINED"
    L7_1M_INSTITUTIONAL_STYLE = "L7_1M_INSTITUTIONAL_STYLE"
    L8_10M_CAPITAL_PRESERVATION = "L8_10M_CAPITAL_PRESERVATION"


# Canonical ladder order (ascending capital). Used by escalation /
# de-escalation logic and by the mismatch detector.
CAPITAL_PROFILE_ORDER: tuple[CapitalProfileId, ...] = (
    CapitalProfileId.L0_SHADOW,
    CapitalProfileId.L1_1U_MICRO_PROBE,
    CapitalProfileId.L1_10U_PROBE,
    CapitalProfileId.L2_25U_50U_SCOUT,
    CapitalProfileId.L3_100U_ATTACK_TEST,
    CapitalProfileId.L4_1K_GROWTH,
    CapitalProfileId.L5_10K_PROFIT_PROTECTION,
    CapitalProfileId.L6_100K_LIQUIDITY_CONSTRAINED,
    CapitalProfileId.L7_1M_INSTITUTIONAL_STYLE,
    CapitalProfileId.L8_10M_CAPITAL_PRESERVATION,
)


@dataclass(frozen=True)
class CapitalProfile:
    """Per-stage capital constraint bundle.

    Every field is a constraint or an awareness flag. The profile does
    NOT decide a trade; it bounds what the deterministic Risk Engine +
    leverage gate are allowed to consider at a given capital stage.
    """

    profile_id: CapitalProfileId
    description: str
    min_equity_usdt: float
    max_equity_usdt: float
    mode_allowed: tuple[LiveRuntimeMode, ...]
    real_orders_allowed: bool
    max_account_capital_usdt: float
    max_position_notional_usdt: float
    max_position_pct_of_equity: float
    max_active_positions: int
    max_symbol_exposure_pct: float
    max_daily_loss_usdt: float
    max_daily_loss_pct: float
    max_total_loss_usdt: float
    max_total_loss_pct: float
    kill_switch_drawdown_pct: float
    base_leverage: float
    max_leverage: float
    right_tail_boost_allowed: bool
    right_tail_max_leverage: float
    require_floating_profit_for_boost: bool
    liquidity_floor_usdt: float
    max_slippage_bps: float
    min_exit_liquidity_score: float
    profit_harvest_enabled: bool
    withdrawal_awareness_enabled: bool
    deposit_awareness_enabled: bool
    escalation_requirements: tuple[str, ...] = field(default_factory=tuple)
    deescalation_rules: tuple[str, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------
    # Equity-band helpers
    # ------------------------------------------------------------------
    def contains_equity(self, equity_usdt: float) -> bool:
        """True if ``equity_usdt`` falls inside this profile's band."""
        return self.min_equity_usdt <= float(equity_usdt) < self.max_equity_usdt

    def allows_mode(self, mode: LiveRuntimeMode) -> bool:
        return mode in self.mode_allowed

    # ------------------------------------------------------------------
    # Order-notional gate
    # ------------------------------------------------------------------
    def check_order_notional(self, notional_usdt: float) -> bool:
        """True if a notional is within ``max_position_notional_usdt``.

        ``L0_SHADOW`` (and any profile whose ``real_orders_allowed`` is
        False) refuses every positive notional outright.
        """
        n = float(notional_usdt)
        if n <= 0:
            return False
        if not self.real_orders_allowed:
            return False
        return n <= self.max_position_notional_usdt

    def reject_reason_for_notional(self, notional_usdt: float) -> str | None:
        """Return a typed reason string when a notional is rejected."""
        n = float(notional_usdt)
        if n <= 0:
            return "non_positive_notional"
        if not self.real_orders_allowed:
            return "real_orders_not_allowed_for_profile"
        if n > self.max_position_notional_usdt:
            return "order_notional_exceeds_profile_max"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id.value,
            "description": self.description,
            "min_equity_usdt": self.min_equity_usdt,
            "max_equity_usdt": (
                None
                if self.max_equity_usdt == EQUITY_UNBOUNDED
                else self.max_equity_usdt
            ),
            "mode_allowed": [m.value for m in self.mode_allowed],
            "real_orders_allowed": self.real_orders_allowed,
            "max_account_capital_usdt": self.max_account_capital_usdt,
            "max_position_notional_usdt": self.max_position_notional_usdt,
            "max_position_pct_of_equity": self.max_position_pct_of_equity,
            "max_active_positions": self.max_active_positions,
            "max_symbol_exposure_pct": self.max_symbol_exposure_pct,
            "max_daily_loss_usdt": self.max_daily_loss_usdt,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_total_loss_usdt": self.max_total_loss_usdt,
            "max_total_loss_pct": self.max_total_loss_pct,
            "kill_switch_drawdown_pct": self.kill_switch_drawdown_pct,
            "base_leverage": self.base_leverage,
            "max_leverage": self.max_leverage,
            "right_tail_boost_allowed": self.right_tail_boost_allowed,
            "right_tail_max_leverage": self.right_tail_max_leverage,
            "require_floating_profit_for_boost": (
                self.require_floating_profit_for_boost
            ),
            "liquidity_floor_usdt": self.liquidity_floor_usdt,
            "max_slippage_bps": self.max_slippage_bps,
            "min_exit_liquidity_score": self.min_exit_liquidity_score,
            "profit_harvest_enabled": self.profit_harvest_enabled,
            "withdrawal_awareness_enabled": self.withdrawal_awareness_enabled,
            "deposit_awareness_enabled": self.deposit_awareness_enabled,
            "escalation_requirements": list(self.escalation_requirements),
            "deescalation_rules": list(self.deescalation_rules),
        }


# ---------------------------------------------------------------------------
# Default ladder (L0 .. L8).
#
# The ladder is intentionally monotonic in the directions that matter:
#   - small profiles MAY be aggressive: higher max_position_pct,
#     higher max_symbol_exposure_pct, higher max_leverage, more slippage
#     tolerance, lower min_exit_liquidity_score, no liquidity floor.
#   - large profiles MUST be conservative: tiny max_position_pct,
#     tiny max_symbol_exposure_pct, low max_leverage, tight slippage,
#     high min_exit_liquidity_score, large liquidity floor, right-tail
#     boost progressively switched off, profit harvest / withdrawal /
#     deposit awareness switched on.
# ---------------------------------------------------------------------------
_SHADOW_AND_LIMITED = (LiveRuntimeMode.LIVE_SHADOW, LiveRuntimeMode.LIVE_LIMITED)


CAPITAL_PROFILE_LADDER: dict[CapitalProfileId, CapitalProfile] = {
    CapitalProfileId.L0_SHADOW: CapitalProfile(
        profile_id=CapitalProfileId.L0_SHADOW,
        description="Shadow / empty-account run. Read-only live context, no real orders ever.",
        min_equity_usdt=0.0,
        max_equity_usdt=EQUITY_UNBOUNDED,
        mode_allowed=(LiveRuntimeMode.LIVE_SHADOW,),
        real_orders_allowed=False,
        max_account_capital_usdt=0.0,
        max_position_notional_usdt=0.0,
        max_position_pct_of_equity=0.0,
        max_active_positions=0,
        max_symbol_exposure_pct=0.0,
        max_daily_loss_usdt=0.0,
        max_daily_loss_pct=0.0,
        max_total_loss_usdt=0.0,
        max_total_loss_pct=0.0,
        kill_switch_drawdown_pct=0.0,
        base_leverage=1.0,
        max_leverage=1.0,
        right_tail_boost_allowed=False,
        right_tail_max_leverage=1.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=0.0,
        max_slippage_bps=0.0,
        min_exit_liquidity_score=0.0,
        profit_harvest_enabled=False,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "operator_funds_account",
            "operator_explicitly_selects_a_funded_profile",
        ),
        deescalation_rules=(
            "always_safe_to_return_to_shadow",
        ),
    ),
    CapitalProfileId.L1_1U_MICRO_PROBE: CapitalProfile(
        profile_id=CapitalProfileId.L1_1U_MICRO_PROBE,
        description="1 USDT micro probe. Plumbing test with negligible real capital.",
        min_equity_usdt=0.5,
        max_equity_usdt=5.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=1.0,
        max_position_notional_usdt=3.0,
        max_position_pct_of_equity=1.0,
        max_active_positions=1,
        max_symbol_exposure_pct=1.0,
        max_daily_loss_usdt=1.0,
        max_daily_loss_pct=1.0,
        max_total_loss_usdt=1.0,
        max_total_loss_pct=1.0,
        kill_switch_drawdown_pct=0.6,
        base_leverage=1.0,
        max_leverage=3.0,
        right_tail_boost_allowed=True,
        right_tail_max_leverage=5.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=0.0,
        max_slippage_bps=120.0,
        min_exit_liquidity_score=0.2,
        profit_harvest_enabled=False,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "plumbing_proven",
            "operator_explicitly_selects_L1_10U_PROBE",
        ),
        deescalation_rules=(
            "drawdown_to_shadow_on_kill_switch",
        ),
    ),
    CapitalProfileId.L1_10U_PROBE: CapitalProfile(
        profile_id=CapitalProfileId.L1_10U_PROBE,
        description="10 USDT probe. First funded right-tail probe; aggressive but tiny absolute risk.",
        min_equity_usdt=5.0,
        max_equity_usdt=25.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=10.0,
        max_position_notional_usdt=20.0,
        max_position_pct_of_equity=1.0,
        max_active_positions=1,
        max_symbol_exposure_pct=1.0,
        max_daily_loss_usdt=10.0,
        max_daily_loss_pct=1.0,
        max_total_loss_usdt=10.0,
        max_total_loss_pct=1.0,
        kill_switch_drawdown_pct=0.5,
        base_leverage=2.0,
        max_leverage=5.0,
        right_tail_boost_allowed=True,
        right_tail_max_leverage=10.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=0.0,
        max_slippage_bps=80.0,
        min_exit_liquidity_score=0.3,
        profit_harvest_enabled=False,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "positive_expectancy_over_probe_window",
            "operator_explicitly_selects_L2_25U_50U_SCOUT",
        ),
        deescalation_rules=(
            "drawdown_to_shadow_on_kill_switch",
            "deescalate_if_equity_below_min_band",
        ),
    ),
    CapitalProfileId.L2_25U_50U_SCOUT: CapitalProfile(
        profile_id=CapitalProfileId.L2_25U_50U_SCOUT,
        description="25-50 USDT scout. Slightly larger, still right-tail aggressive.",
        min_equity_usdt=25.0,
        max_equity_usdt=100.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=50.0,
        max_position_notional_usdt=100.0,
        max_position_pct_of_equity=0.8,
        max_active_positions=2,
        max_symbol_exposure_pct=0.8,
        max_daily_loss_usdt=25.0,
        max_daily_loss_pct=0.5,
        max_total_loss_usdt=40.0,
        max_total_loss_pct=0.8,
        kill_switch_drawdown_pct=0.45,
        base_leverage=2.0,
        max_leverage=5.0,
        right_tail_boost_allowed=True,
        right_tail_max_leverage=8.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=0.0,
        max_slippage_bps=60.0,
        min_exit_liquidity_score=0.35,
        profit_harvest_enabled=False,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "stable_scout_performance",
            "operator_explicitly_selects_L3_100U_ATTACK_TEST",
        ),
        deescalation_rules=("deescalate_if_equity_below_min_band",),
    ),
    CapitalProfileId.L3_100U_ATTACK_TEST: CapitalProfile(
        profile_id=CapitalProfileId.L3_100U_ATTACK_TEST,
        description="100 USDT attack test. First profile sized for full attack-state trades.",
        min_equity_usdt=100.0,
        max_equity_usdt=500.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=100.0,
        max_position_notional_usdt=200.0,
        max_position_pct_of_equity=0.6,
        max_active_positions=3,
        max_symbol_exposure_pct=0.6,
        max_daily_loss_usdt=30.0,
        max_daily_loss_pct=0.3,
        max_total_loss_usdt=60.0,
        max_total_loss_pct=0.6,
        kill_switch_drawdown_pct=0.4,
        base_leverage=2.0,
        max_leverage=4.0,
        right_tail_boost_allowed=True,
        right_tail_max_leverage=6.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=50_000.0,
        max_slippage_bps=40.0,
        min_exit_liquidity_score=0.45,
        profit_harvest_enabled=True,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "attack_test_profitable",
            "operator_explicitly_selects_L4_1K_GROWTH",
        ),
        deescalation_rules=("deescalate_if_equity_below_min_band",),
    ),
    CapitalProfileId.L4_1K_GROWTH: CapitalProfile(
        profile_id=CapitalProfileId.L4_1K_GROWTH,
        description="1,000 USDT growth. Position sizing begins to feel real fill depth.",
        min_equity_usdt=500.0,
        max_equity_usdt=5_000.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=1_000.0,
        max_position_notional_usdt=1_500.0,
        max_position_pct_of_equity=0.4,
        max_active_positions=4,
        max_symbol_exposure_pct=0.4,
        max_daily_loss_usdt=150.0,
        max_daily_loss_pct=0.15,
        max_total_loss_usdt=400.0,
        max_total_loss_pct=0.4,
        kill_switch_drawdown_pct=0.35,
        base_leverage=2.0,
        max_leverage=3.0,
        right_tail_boost_allowed=True,
        right_tail_max_leverage=4.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=250_000.0,
        max_slippage_bps=25.0,
        min_exit_liquidity_score=0.55,
        profit_harvest_enabled=True,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "growth_proven_with_acceptable_drawdown",
            "operator_explicitly_selects_L5_10K_PROFIT_PROTECTION",
        ),
        deescalation_rules=("deescalate_if_equity_below_min_band",),
    ),
    CapitalProfileId.L5_10K_PROFIT_PROTECTION: CapitalProfile(
        profile_id=CapitalProfileId.L5_10K_PROFIT_PROTECTION,
        description="10,000 USDT profit protection. Profit harvest and staged exit dominate.",
        min_equity_usdt=5_000.0,
        max_equity_usdt=50_000.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=10_000.0,
        max_position_notional_usdt=12_000.0,
        max_position_pct_of_equity=0.25,
        max_active_positions=5,
        max_symbol_exposure_pct=0.25,
        max_daily_loss_usdt=800.0,
        max_daily_loss_pct=0.08,
        max_total_loss_usdt=2_500.0,
        max_total_loss_pct=0.25,
        kill_switch_drawdown_pct=0.3,
        base_leverage=1.5,
        max_leverage=3.0,
        right_tail_boost_allowed=True,
        right_tail_max_leverage=3.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=1_000_000.0,
        max_slippage_bps=15.0,
        min_exit_liquidity_score=0.65,
        profit_harvest_enabled=True,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "profit_protection_discipline_proven",
            "operator_explicitly_selects_L6_100K_LIQUIDITY_CONSTRAINED",
        ),
        deescalation_rules=("deescalate_if_equity_below_min_band",),
    ),
    CapitalProfileId.L6_100K_LIQUIDITY_CONSTRAINED: CapitalProfile(
        profile_id=CapitalProfileId.L6_100K_LIQUIDITY_CONSTRAINED,
        description="100,000 USDT. Fill depth / slippage now constrain symbol choice.",
        min_equity_usdt=50_000.0,
        max_equity_usdt=500_000.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=100_000.0,
        max_position_notional_usdt=80_000.0,
        max_position_pct_of_equity=0.12,
        max_active_positions=6,
        max_symbol_exposure_pct=0.12,
        max_daily_loss_usdt=5_000.0,
        max_daily_loss_pct=0.05,
        max_total_loss_usdt=20_000.0,
        max_total_loss_pct=0.2,
        kill_switch_drawdown_pct=0.25,
        base_leverage=1.5,
        max_leverage=2.0,
        right_tail_boost_allowed=False,
        right_tail_max_leverage=2.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=5_000_000.0,
        max_slippage_bps=10.0,
        min_exit_liquidity_score=0.75,
        profit_harvest_enabled=True,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "liquidity_constrained_execution_proven",
            "operator_explicitly_selects_L7_1M_INSTITUTIONAL_STYLE",
        ),
        deescalation_rules=("deescalate_if_equity_below_min_band",),
    ),
    CapitalProfileId.L7_1M_INSTITUTIONAL_STYLE: CapitalProfile(
        profile_id=CapitalProfileId.L7_1M_INSTITUTIONAL_STYLE,
        description="1,000,000 USDT institutional style. Staged entry/exit mandatory; right-tail boost off.",
        min_equity_usdt=500_000.0,
        max_equity_usdt=5_000_000.0,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=1_000_000.0,
        max_position_notional_usdt=500_000.0,
        max_position_pct_of_equity=0.06,
        max_active_positions=8,
        max_symbol_exposure_pct=0.06,
        max_daily_loss_usdt=30_000.0,
        max_daily_loss_pct=0.03,
        max_total_loss_usdt=120_000.0,
        max_total_loss_pct=0.12,
        kill_switch_drawdown_pct=0.2,
        base_leverage=1.0,
        max_leverage=2.0,
        right_tail_boost_allowed=False,
        right_tail_max_leverage=1.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=20_000_000.0,
        max_slippage_bps=6.0,
        min_exit_liquidity_score=0.85,
        profit_harvest_enabled=True,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "institutional_execution_proven",
            "operator_explicitly_selects_L8_10M_CAPITAL_PRESERVATION",
        ),
        deescalation_rules=("deescalate_if_equity_below_min_band",),
    ),
    CapitalProfileId.L8_10M_CAPITAL_PRESERVATION: CapitalProfile(
        profile_id=CapitalProfileId.L8_10M_CAPITAL_PRESERVATION,
        description="10,000,000 USDT capital preservation. Defensive; no right-tail boost; harvest/withdraw first.",
        min_equity_usdt=5_000_000.0,
        max_equity_usdt=EQUITY_UNBOUNDED,
        mode_allowed=_SHADOW_AND_LIMITED,
        real_orders_allowed=True,
        max_account_capital_usdt=10_000_000.0,
        max_position_notional_usdt=2_000_000.0,
        max_position_pct_of_equity=0.03,
        max_active_positions=10,
        max_symbol_exposure_pct=0.03,
        max_daily_loss_usdt=150_000.0,
        max_daily_loss_pct=0.015,
        max_total_loss_usdt=500_000.0,
        max_total_loss_pct=0.05,
        kill_switch_drawdown_pct=0.15,
        base_leverage=1.0,
        max_leverage=1.0,
        right_tail_boost_allowed=False,
        right_tail_max_leverage=1.0,
        require_floating_profit_for_boost=True,
        liquidity_floor_usdt=50_000_000.0,
        max_slippage_bps=4.0,
        min_exit_liquidity_score=0.9,
        profit_harvest_enabled=True,
        withdrawal_awareness_enabled=True,
        deposit_awareness_enabled=True,
        escalation_requirements=(
            "top_of_ladder_no_further_escalation",
        ),
        deescalation_rules=("deescalate_if_equity_below_min_band",),
    ),
}


# ---------------------------------------------------------------------------
# Lookup + mismatch + escalation helpers (all deterministic, no IO).
# ---------------------------------------------------------------------------
def get_profile(profile_id: CapitalProfileId | str) -> CapitalProfile:
    """Return the :class:`CapitalProfile` for ``profile_id``.

    Accepts either a :class:`CapitalProfileId` or its string value.
    Raises ``KeyError`` for an unknown id.
    """
    if isinstance(profile_id, str) and not isinstance(profile_id, CapitalProfileId):
        profile_id = CapitalProfileId(profile_id)
    return CAPITAL_PROFILE_LADDER[profile_id]


def _profile_index(profile_id: CapitalProfileId) -> int:
    return CAPITAL_PROFILE_ORDER.index(profile_id)


def suggest_profile_for_equity(equity_usdt: float) -> CapitalProfileId:
    """Suggest (NOT apply) the funded profile whose band contains equity.

    Skips ``L0_SHADOW`` (it is the empty-account profile, not an
    equity band). Falls back to the top of the ladder when equity
    exceeds every funded band. This is a SUGGESTION only - the operator
    must explicitly select the profile; nothing here auto-applies.
    """
    eq = float(equity_usdt)
    for pid in CAPITAL_PROFILE_ORDER:
        if pid is CapitalProfileId.L0_SHADOW:
            continue
        profile = CAPITAL_PROFILE_LADDER[pid]
        if profile.contains_equity(eq):
            return pid
    # Above the highest funded band -> top of ladder.
    return CapitalProfileId.L8_10M_CAPITAL_PRESERVATION


@dataclass(frozen=True)
class ProfileMismatch:
    """Result of comparing an active profile against the adjusted equity.

    ``mismatch`` is True when the equity has left the active profile's
    band. ``direction`` is ``"escalate"`` (equity grew past the band),
    ``"deescalate"`` (equity fell below the band), or ``"none"``.
    ``suggested_profile_id`` is what the operator SHOULD consider; the
    system never applies it automatically.
    """

    active_profile_id: CapitalProfileId
    adjusted_equity_usdt: float
    mismatch: bool
    direction: str
    suggested_profile_id: CapitalProfileId
    requires_operator_action: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_profile_id": self.active_profile_id.value,
            "adjusted_equity_usdt": self.adjusted_equity_usdt,
            "mismatch": self.mismatch,
            "direction": self.direction,
            "suggested_profile_id": self.suggested_profile_id.value,
            "requires_operator_action": self.requires_operator_action,
            "reason": self.reason,
            "auto_escalation_allowed": AUTO_ESCALATION_ALLOWED,
        }


def detect_profile_mismatch(
    active_profile_id: CapitalProfileId | str,
    adjusted_equity_usdt: float,
) -> ProfileMismatch:
    """Detect (never fix) a profile / equity mismatch.

    The check is run against the *adjusted* equity (i.e. equity with
    external deposits / withdrawals already separated out by the
    Capital Event Contract) so an external deposit can never be
    mistaken for strategy growth that justifies an escalation.

    Example (the brief's scenario): a 10U account that has rocketed to
    10,000U is still on ``L1_10U_PROBE``; this returns ``mismatch=True``,
    ``direction="escalate"`` and a suggested profile, and demands
    operator action. It does NOT change the profile.
    """
    if isinstance(active_profile_id, str) and not isinstance(
        active_profile_id, CapitalProfileId
    ):
        active_profile_id = CapitalProfileId(active_profile_id)
    profile = CAPITAL_PROFILE_LADDER[active_profile_id]
    eq = float(adjusted_equity_usdt)

    # Shadow profile has an unbounded band: it never "mismatches" on
    # equity, but if the operator funded the account they should leave
    # shadow explicitly.
    if profile.contains_equity(eq) and active_profile_id is not CapitalProfileId.L0_SHADOW:
        return ProfileMismatch(
            active_profile_id=active_profile_id,
            adjusted_equity_usdt=eq,
            mismatch=False,
            direction="none",
            suggested_profile_id=active_profile_id,
            requires_operator_action=False,
            reason="equity_within_profile_band",
        )

    suggested = suggest_profile_for_equity(eq)
    if active_profile_id is CapitalProfileId.L0_SHADOW:
        if eq <= 0:
            return ProfileMismatch(
                active_profile_id=active_profile_id,
                adjusted_equity_usdt=eq,
                mismatch=False,
                direction="none",
                suggested_profile_id=active_profile_id,
                requires_operator_action=False,
                reason="shadow_empty_account",
            )
        return ProfileMismatch(
            active_profile_id=active_profile_id,
            adjusted_equity_usdt=eq,
            mismatch=True,
            direction="escalate",
            suggested_profile_id=suggested,
            requires_operator_action=True,
            reason="shadow_account_has_real_equity_operator_must_select_profile",
        )

    if eq >= profile.max_equity_usdt:
        direction = "escalate"
        reason = "equity_exceeds_profile_band_operator_must_reselect_profile"
    else:
        direction = "deescalate"
        reason = "equity_below_profile_band_operator_must_reselect_profile"

    return ProfileMismatch(
        active_profile_id=active_profile_id,
        adjusted_equity_usdt=eq,
        mismatch=True,
        direction=direction,
        suggested_profile_id=suggested,
        requires_operator_action=True,
        reason=reason,
    )


@dataclass(frozen=True)
class ProfileChangeRequest:
    """An explicit operator request to change the active capital profile.

    PR110 contract: a profile change is ALWAYS operator-initiated. This
    object records the request; applying it requires an explicit,
    audited operator action elsewhere (it is never produced by the
    system as a side effect of equity growth).
    """

    from_profile_id: CapitalProfileId
    to_profile_id: CapitalProfileId
    requested_by: str
    is_escalation: bool
    requires_operator_ack: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_profile_id": self.from_profile_id.value,
            "to_profile_id": self.to_profile_id.value,
            "requested_by": self.requested_by,
            "is_escalation": self.is_escalation,
            "requires_operator_ack": self.requires_operator_ack,
            "auto_escalation_allowed": AUTO_ESCALATION_ALLOWED,
        }


def build_profile_change_request(
    from_profile_id: CapitalProfileId | str,
    to_profile_id: CapitalProfileId | str,
    *,
    requested_by: str,
) -> ProfileChangeRequest:
    """Build an operator profile-change request (never auto-applied)."""
    if isinstance(from_profile_id, str) and not isinstance(
        from_profile_id, CapitalProfileId
    ):
        from_profile_id = CapitalProfileId(from_profile_id)
    if isinstance(to_profile_id, str) and not isinstance(
        to_profile_id, CapitalProfileId
    ):
        to_profile_id = CapitalProfileId(to_profile_id)
    is_escalation = _profile_index(to_profile_id) > _profile_index(from_profile_id)
    return ProfileChangeRequest(
        from_profile_id=from_profile_id,
        to_profile_id=to_profile_id,
        requested_by=str(requested_by),
        is_escalation=is_escalation,
    )


__all__ = [
    "EQUITY_UNBOUNDED",
    "AUTO_ESCALATION_ALLOWED",
    "CapitalProfileId",
    "CAPITAL_PROFILE_ORDER",
    "CapitalProfile",
    "CAPITAL_PROFILE_LADDER",
    "get_profile",
    "suggest_profile_for_equity",
    "ProfileMismatch",
    "detect_profile_mismatch",
    "ProfileChangeRequest",
    "build_profile_change_request",
]
