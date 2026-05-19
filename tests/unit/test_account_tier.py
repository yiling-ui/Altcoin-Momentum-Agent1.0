"""Phase 7 - Account Life Tier classifier tests (Spec §27.4)."""

from __future__ import annotations

from app.core.enums import AccountLifeTier
from app.risk.account_tier import (
    ACCOUNT_TIER_POLICY,
    classify_account_tier,
    policy_for,
)


def test_tier_a_at_or_above_one_point_five_x():
    assert classify_account_tier(current_equity=150, initial_capital=100) == AccountLifeTier.A
    assert classify_account_tier(current_equity=300, initial_capital=100) == AccountLifeTier.A


def test_tier_b_between_one_x_and_one_point_five_x():
    assert classify_account_tier(current_equity=100, initial_capital=100) == AccountLifeTier.B
    assert classify_account_tier(current_equity=149, initial_capital=100) == AccountLifeTier.B


def test_tier_c_between_zero_point_seven_x_and_one_x():
    assert classify_account_tier(current_equity=80, initial_capital=100) == AccountLifeTier.C
    assert classify_account_tier(current_equity=70, initial_capital=100) == AccountLifeTier.C


def test_tier_d_between_zero_point_five_x_and_zero_point_seven_x():
    assert classify_account_tier(current_equity=60, initial_capital=100) == AccountLifeTier.D
    assert classify_account_tier(current_equity=50, initial_capital=100) == AccountLifeTier.D


def test_tier_e_between_zero_point_three_x_and_zero_point_five_x():
    assert classify_account_tier(current_equity=40, initial_capital=100) == AccountLifeTier.E
    assert classify_account_tier(current_equity=30, initial_capital=100) == AccountLifeTier.E


def test_tier_f_below_zero_point_three_x():
    assert classify_account_tier(current_equity=29, initial_capital=100) == AccountLifeTier.F
    assert classify_account_tier(current_equity=10, initial_capital=100) == AccountLifeTier.F


def test_tier_f_when_initial_capital_invalid():
    assert classify_account_tier(current_equity=100, initial_capital=0) == AccountLifeTier.F
    assert classify_account_tier(current_equity=100, initial_capital=-1) == AccountLifeTier.F


def test_tier_a_policy_permits_full_ladder():
    p = policy_for(AccountLifeTier.A)
    assert p.allow_new_open
    assert p.allow_attack
    assert p.allow_right_tail_amplify
    assert not p.halt_only
    assert not p.paper_only


def test_tier_b_disallows_right_tail_only():
    p = policy_for(AccountLifeTier.B)
    assert p.allow_new_open
    assert p.allow_attack
    assert not p.allow_right_tail_amplify


def test_tier_d_disallows_right_tail():
    p = policy_for(AccountLifeTier.D)
    assert p.allow_new_open
    assert p.allow_attack
    assert not p.allow_right_tail_amplify


def test_tier_e_disallows_new_open_and_attack():
    p = policy_for(AccountLifeTier.E)
    assert not p.allow_new_open
    assert not p.allow_attack
    assert p.paper_only


def test_tier_f_halts():
    p = policy_for(AccountLifeTier.F)
    assert p.halt_only
    assert not p.allow_new_open
    assert not p.allow_live_trading


def test_policy_table_covers_every_tier():
    for tier in AccountLifeTier:
        assert tier in ACCOUNT_TIER_POLICY
        assert ACCOUNT_TIER_POLICY[tier].tier is tier
