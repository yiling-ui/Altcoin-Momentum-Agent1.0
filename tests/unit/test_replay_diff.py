"""Phase 10A - Replay diff value objects (Issue #10 Part 1)."""

from __future__ import annotations

from app.replay.diff import (
    DiffEntry,
    DiffKind,
    ReplayDiffReport,
    compare_event_chains,
)


# ---------------------------------------------------------------------------
# DiffKind / DiffEntry surface
# ---------------------------------------------------------------------------
def test_diff_kind_vocabulary_is_complete():
    assert {k.value for k in DiffKind} == {
        "match",
        "missing",
        "extra",
        "reordered",
    }


def test_diff_entry_to_payload_round_trip():
    entry = DiffEntry(
        kind=DiffKind.MATCH,
        expected_index=0,
        observed_index=0,
        expected_value="ORDER_SENT",
        observed_value="ORDER_SENT",
        summary="match 'ORDER_SENT' at expected=0 observed=0",
    )
    payload = entry.to_payload()
    assert payload["kind"] == "match"
    assert payload["expected_index"] == 0
    assert payload["observed_index"] == 0
    assert payload["expected_value"] == "ORDER_SENT"
    assert payload["observed_value"] == "ORDER_SENT"


# ---------------------------------------------------------------------------
# Identical chains -> matched
# ---------------------------------------------------------------------------
def test_identical_chains_match_cleanly():
    expected = ["ORDER_SENT", "ORDER_ACK", "ORDER_FILLED"]
    observed = ["ORDER_SENT", "ORDER_ACK", "ORDER_FILLED"]
    diff = compare_event_chains(expected, observed)
    assert diff.matched is True
    assert diff.divergence_count() == 0
    assert all(e.kind is DiffKind.MATCH for e in diff.entries)
    assert len(diff.entries) == 3


def test_empty_chains_match():
    diff = compare_event_chains([], [])
    assert diff.matched is True
    assert diff.entries == ()


# ---------------------------------------------------------------------------
# Missing events
# ---------------------------------------------------------------------------
def test_missing_events_produce_missing_entries():
    expected = ["ORDER_SENT", "ORDER_ACK", "ORDER_FILLED"]
    observed = ["ORDER_SENT"]
    diff = compare_event_chains(expected, observed)
    assert diff.matched is False
    missing = [e for e in diff.entries if e.kind is DiffKind.MISSING]
    assert {m.expected_value for m in missing} == {"ORDER_ACK", "ORDER_FILLED"}
    assert diff.divergence_count(DiffKind.MISSING) == 2


def test_completely_disjoint_chains():
    expected = ["A", "B"]
    observed = ["C", "D"]
    diff = compare_event_chains(expected, observed)
    assert diff.matched is False
    # SequenceMatcher with no common elements emits a single REPLACE,
    # which compare_event_chains pairs as REORDERED rows.
    kinds = {e.kind for e in diff.entries}
    assert DiffKind.REORDERED in kinds


# ---------------------------------------------------------------------------
# Extra events
# ---------------------------------------------------------------------------
def test_extra_events_produce_extra_entries():
    expected = ["ORDER_SENT", "ORDER_FILLED"]
    observed = ["ORDER_SENT", "ORDER_ACK", "ORDER_FILLED"]
    diff = compare_event_chains(expected, observed)
    extras = [e for e in diff.entries if e.kind is DiffKind.EXTRA]
    assert len(extras) == 1
    assert extras[0].observed_value == "ORDER_ACK"
    assert extras[0].observed_index == 1


def test_extra_at_end():
    expected = ["A"]
    observed = ["A", "B", "C"]
    diff = compare_event_chains(expected, observed)
    assert diff.matched is False
    extras = [e for e in diff.entries if e.kind is DiffKind.EXTRA]
    assert {e.observed_value for e in extras} == {"B", "C"}


# ---------------------------------------------------------------------------
# Reordered events (REPLACE opcode)
# ---------------------------------------------------------------------------
def test_swapped_pair_is_flagged_as_diverged():
    """``[A, B]`` vs ``[B, A]`` is structurally different.

    The ``compare_event_chains`` algorithm uses :class:`difflib.SequenceMatcher`
    so the exact opcode mix (replace vs delete+insert) depends on
    Python's stdlib implementation. We pin the contract: the diff
    must NOT match, and at least one of MISSING / EXTRA / REORDERED
    must fire to surface the divergence.
    """
    expected = ["A", "B"]
    observed = ["B", "A"]
    diff = compare_event_chains(expected, observed)
    assert diff.matched is False
    kinds = {e.kind for e in diff.entries}
    assert kinds & {DiffKind.MISSING, DiffKind.EXTRA, DiffKind.REORDERED}


def test_reordered_block_with_uneven_tail():
    """A 2-vs-3 swapped block must surface as a non-match diff."""
    expected = ["A", "B"]
    observed = ["X", "Y", "Z"]
    diff = compare_event_chains(expected, observed)
    assert diff.matched is False
    # Every expected element must show up as MISSING somewhere in the
    # diff, and at least one of the observed-only elements must show
    # up as EXTRA / REORDERED.
    expected_in_diff = {e.expected_value for e in diff.entries if e.expected_value is not None}
    observed_in_diff = {e.observed_value for e in diff.entries if e.observed_value is not None}
    assert {"A", "B"}.issubset(expected_in_diff)
    assert observed_in_diff & {"X", "Y", "Z"}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_compare_event_chains_is_deterministic():
    expected = ["ORDER_SENT", "ORDER_ACK", "ORDER_FILLED"]
    observed = ["ORDER_SENT", "ORDER_FILLED", "STOP_FAILED"]
    a = compare_event_chains(expected, observed)
    b = compare_event_chains(expected, observed)
    assert a.to_payload() == b.to_payload()


def test_label_is_carried_into_report():
    diff = compare_event_chains(["A"], ["A"], label="self_check")
    assert diff.label == "self_check"
    payload = diff.to_payload()
    assert payload["label"] == "self_check"


# ---------------------------------------------------------------------------
# ReplayDiffReport derived properties
# ---------------------------------------------------------------------------
def test_divergences_property_filters_matches():
    expected = ["ORDER_SENT", "ORDER_ACK", "ORDER_FILLED"]
    observed = ["ORDER_SENT", "ORDER_FILLED"]
    diff = compare_event_chains(expected, observed)
    assert diff.matched is False
    assert all(e.kind is not DiffKind.MATCH for e in diff.divergences)
    assert diff.divergence_count() == len(diff.divergences)


def test_to_payload_is_json_safe():
    """The diff payload must be JSON-safe so Issue #10 Part 10D can ship it."""
    import json

    expected = ["ORDER_SENT", "ORDER_ACK", "ORDER_FILLED"]
    observed = ["ORDER_SENT", "STOP_FAILED"]
    diff = compare_event_chains(expected, observed, label="test")
    payload = diff.to_payload()
    # Round-trip through JSON to confirm.
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["label"] == "test"
    assert decoded["matched"] is False
    assert isinstance(decoded["entries"], list)
    assert isinstance(decoded["divergences"], list)


def test_diff_report_immutable_dataclass():
    """The ReplayDiffReport is a frozen dataclass - no in-place mutation."""
    import dataclasses

    diff = compare_event_chains(["A"], ["A"])
    assert isinstance(diff, ReplayDiffReport)
    # frozen=True on the dataclass -> assignment raises FrozenInstanceError
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        diff.label = "mutated"  # type: ignore[misc]
