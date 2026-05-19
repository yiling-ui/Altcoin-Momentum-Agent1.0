"""Phase 10B - mistake-tag vocabulary tests (Issue #10 Part 2).

Pin the frozen vocabulary so a future maintainer cannot silently drop
or rename one of the Issue-required tags.
"""

from __future__ import annotations

import json

from app.reflection.tags import (
    DIAGNOSTIC_MISTAKE_TAGS,
    ISSUE_REQUIRED_MISTAKE_TAGS,
    MistakeTag,
)


# ---------------------------------------------------------------------------
# Issue contract
# ---------------------------------------------------------------------------
ISSUE_REQUIRED_VALUES = {
    "late_entry",
    "early_exit",
    "weak_volume",
    "fake_breakout",
    "high_trap_score",
    "ignored_no_trade_gate",
    "slippage_error",
    "execution_delay",
    "stop_not_confirmed",
    "tail_saved_trade",
    "tail_failed",
    "right_tail_success",
}

DIAGNOSTIC_VALUES = {
    "insufficient_data",
    "no_lifecycle_observed",
    "incident_during_lifecycle",
}


def test_issue_required_mistake_tag_values_pinned():
    """All 12 Issue #10 Part 10B tags are present with exact spellings."""
    assert {t.value for t in ISSUE_REQUIRED_MISTAKE_TAGS} == ISSUE_REQUIRED_VALUES


def test_diagnostic_mistake_tag_values_pinned():
    assert {t.value for t in DIAGNOSTIC_MISTAKE_TAGS} == DIAGNOSTIC_VALUES


def test_mistake_tag_enum_is_exhaustive():
    """The vocabulary is the union of issue-required + diagnostic."""
    expected = ISSUE_REQUIRED_VALUES | DIAGNOSTIC_VALUES
    assert {t.value for t in MistakeTag} == expected


def test_required_and_diagnostic_sets_are_disjoint():
    assert ISSUE_REQUIRED_MISTAKE_TAGS.isdisjoint(DIAGNOSTIC_MISTAKE_TAGS)


def test_mistake_tag_is_str_enum():
    """The ``str`` mixin is what makes the enum JSON-safe."""
    assert isinstance(MistakeTag.LATE_ENTRY, str)
    assert MistakeTag.LATE_ENTRY.value == "late_entry"


def test_mistake_tag_is_json_safe():
    """Every value round-trips through ``json``."""
    payload = {"mistake_tags": [t.value for t in MistakeTag]}
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)
    assert set(decoded["mistake_tags"]) == {t.value for t in MistakeTag}


def test_mistake_tag_value_is_immutable():
    """Members are ``str`` instances - their value cannot change."""
    tag = MistakeTag.LATE_ENTRY
    # The string value is what consumers serialise; it must be stable
    # across calls.
    assert MistakeTag.LATE_ENTRY.value == tag.value == "late_entry"


def test_mistake_tag_membership_is_closed():
    """Cannot construct a MistakeTag from an unknown string."""
    import pytest

    with pytest.raises(ValueError):
        MistakeTag("definitely_not_a_real_tag")


def test_required_set_size_at_least_12():
    """Issue brief: 至少包含 (the 12 listed tags)."""
    assert len(ISSUE_REQUIRED_MISTAKE_TAGS) >= 12


def test_diagnostic_set_size_is_three():
    assert len(DIAGNOSTIC_MISTAKE_TAGS) == 3
