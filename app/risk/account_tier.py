"""Phase 7 Account Life Tier classifier (Issue #7, Spec §27.4).

The Account Life Tier is a pure function of the equity ratio
``current_equity / initial_capital``:

    tier A:  >= 1.5x   attack + right-tail allowed
    tier B:  1.0-1.5x  normal
    tier C:  0.7-1.0x  reduce frequency
    tier D:  0.5-0.7x  no right-tail
    tier E:  0.3-0.5x  observe / paper only
    tier F:  < 0.3x    halt and review

Phase 7 ships only the classifier and the policy table that the Risk
Engine consults. It does NOT update the equity itself - that is
Issue #8 (Capital Flow Engine). When the entrypoint and tests want a
deterministic classifier they pass an explicit ratio in.

NOT a trade authorisation. The tier is a NECESSARY condition the
Risk Engine reads, not a sufficient one. A request that the tier
would otherwise allow can still be rejected by every other gate
(regime, universe, liquidity, manipulation, confirmation, circuit
breakers, stop-unconfirmed, unknown-position).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import AccountLifeTier


@dataclass(frozen=True)
class AccountTierPolicy:
    """What this tier permits, expressed as a small set of booleans.

    Every field is read by the Risk Engine. A field set to ``False``
    means the gate fires and the corresponding :class:`RiskRejectReason`
    is appended.
    """

    tier: AccountLifeTier
    allow_new_open: bool
    allow_attack: bool
    allow_right_tail_amplify: bool
    allow_live_trading: bool
    halt_only: bool
    paper_only: bool
    notes: str = ""


# Spec §27.4 ladder. The values below are the Phase 7 source of truth.
ACCOUNT_TIER_POLICY: dict[AccountLifeTier, AccountTierPolicy] = {
    AccountLifeTier.A: AccountTierPolicy(
        tier=AccountLifeTier.A,
        allow_new_open=True,
        allow_attack=True,
        allow_right_tail_amplify=True,
        allow_live_trading=True,
        halt_only=False,
        paper_only=False,
        notes="equity >= 1.5x initial capital - full ladder permitted",
    ),
    AccountLifeTier.B: AccountTierPolicy(
        tier=AccountLifeTier.B,
        allow_new_open=True,
        allow_attack=True,
        allow_right_tail_amplify=False,
        allow_live_trading=True,
        halt_only=False,
        paper_only=False,
        notes="1.0-1.5x - normal mode, right-tail still locked",
    ),
    AccountLifeTier.C: AccountTierPolicy(
        tier=AccountLifeTier.C,
        allow_new_open=True,
        allow_attack=True,
        allow_right_tail_amplify=False,
        allow_live_trading=True,
        halt_only=False,
        paper_only=False,
        notes="0.7-1.0x - reduce frequency, no right-tail",
    ),
    AccountLifeTier.D: AccountTierPolicy(
        tier=AccountLifeTier.D,
        allow_new_open=True,
        allow_attack=True,
        allow_right_tail_amplify=False,
        allow_live_trading=True,
        halt_only=False,
        paper_only=False,
        notes="0.5-0.7x - no right-tail, attack still permitted",
    ),
    AccountLifeTier.E: AccountTierPolicy(
        tier=AccountLifeTier.E,
        allow_new_open=False,
        allow_attack=False,
        allow_right_tail_amplify=False,
        allow_live_trading=False,
        halt_only=False,
        paper_only=True,
        notes="0.3-0.5x - observe / paper only",
    ),
    AccountLifeTier.F: AccountTierPolicy(
        tier=AccountLifeTier.F,
        allow_new_open=False,
        allow_attack=False,
        allow_right_tail_amplify=False,
        allow_live_trading=False,
        halt_only=True,
        paper_only=True,
        notes="< 0.3x - halt for review",
    ),
}


def classify_account_tier(
    *, current_equity: float, initial_capital: float
) -> AccountLifeTier:
    """Return the Spec §27.4 tier for the supplied equity ratio.

    A non-positive ``initial_capital`` is treated as F (halt) so a
    misconfigured caller cannot accidentally trade through the gate.
    """
    if initial_capital <= 0:
        return AccountLifeTier.F
    ratio = current_equity / initial_capital
    if ratio >= 1.5:
        return AccountLifeTier.A
    if ratio >= 1.0:
        return AccountLifeTier.B
    if ratio >= 0.7:
        return AccountLifeTier.C
    if ratio >= 0.5:
        return AccountLifeTier.D
    if ratio >= 0.3:
        return AccountLifeTier.E
    return AccountLifeTier.F


def policy_for(tier: AccountLifeTier) -> AccountTierPolicy:
    """Return the Phase 7 policy for the supplied tier."""
    return ACCOUNT_TIER_POLICY[tier]
