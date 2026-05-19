"""Phase 10A Replay Engine - internal diff report (Issue #10 Part 1).

A small, self-contained value-object module for comparing an
**expected** event chain against an **observed** event chain.

This is a deliberately narrow surface:

  - Phase 10A ships ONLY the structural diff used by the Replay
    Engine's own self-checks (e.g. "does the paper trade lifecycle
    match the canonical Phase 9 order?", "did the P0 latched-pause
    invariant hold across this reconciliation pass?").
  - Phase 10A does **NOT** ship a Reflection / mistake-tag report -
    that is Part 10B's job (Reflection Engine), explicitly out of
    scope for Part 10A.
  - Phase 10A does **NOT** ship an LLM-driven natural-language diff -
    Part 10C will land the LLM Guarded Interpreter under strict
    guardrails. Replay never calls an LLM.

The diff operates on lists of strings (event-type values, lifecycle
markers, etc.) so it can be reused for any expected-vs-observed
comparison Phase 10A needs without coupling to the Phase 9 event
class itself.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiffKind(str, Enum):
    """Why a diff entry was emitted.

    The vocabulary is deliberately small: Replay Engine only needs to
    classify each entry as a match, an unexpected addition, a missing
    expected element, or a positional reorder. Anything richer belongs
    to Reflection (Part 10B).
    """

    MATCH = "match"
    MISSING = "missing"            # expected has it, observed does not
    EXTRA = "extra"                # observed has it, expected does not
    REORDERED = "reordered"        # both sides have it, in different order


@dataclass(frozen=True)
class DiffEntry:
    """One row in a :class:`ReplayDiffReport`."""

    kind: DiffKind
    expected_index: int | None
    observed_index: int | None
    expected_value: str | None
    observed_value: str | None
    summary: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "expected_index": self.expected_index,
            "observed_index": self.observed_index,
            "expected_value": self.expected_value,
            "observed_value": self.observed_value,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ReplayDiffReport:
    """Result of comparing an expected event chain against an observed one.

    Two sequences match when every entry is :class:`DiffKind.MATCH`,
    captured by :attr:`matched`. Otherwise :attr:`entries` contains one
    row per divergence; the entries are ordered to match the original
    expected sequence to make reading the report deterministic.
    """

    expected_chain: tuple[str, ...]
    observed_chain: tuple[str, ...]
    entries: tuple[DiffEntry, ...] = field(default_factory=tuple)
    label: str | None = None

    @property
    def matched(self) -> bool:
        """True iff every entry is a MATCH (or there are no entries)."""
        return all(e.kind is DiffKind.MATCH for e in self.entries)

    @property
    def divergences(self) -> tuple[DiffEntry, ...]:
        """Subset of :attr:`entries` with kind != MATCH."""
        return tuple(e for e in self.entries if e.kind is not DiffKind.MATCH)

    def divergence_count(self, kind: DiffKind | None = None) -> int:
        if kind is None:
            return len(self.divergences)
        return sum(1 for e in self.entries if e.kind is kind)

    def to_payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "matched": self.matched,
            "expected_chain": list(self.expected_chain),
            "observed_chain": list(self.observed_chain),
            "entries": [e.to_payload() for e in self.entries],
            "divergences": [e.to_payload() for e in self.divergences],
            "divergence_count": self.divergence_count(),
        }


def compare_event_chains(
    expected: list[str] | tuple[str, ...],
    observed: list[str] | tuple[str, ...],
    *,
    label: str | None = None,
) -> ReplayDiffReport:
    """Compare ``expected`` against ``observed`` element-by-element.

    The diff uses :class:`difflib.SequenceMatcher` so the result is
    deterministic: identical inputs produce identical reports across
    Python versions.

    Algorithm:
      - SequenceMatcher walks both sides emitting opcodes:
          - ``equal``    -> one MATCH per element pair
          - ``insert``   -> one EXTRA per observed-only element
          - ``delete``   -> one MISSING per expected-only element
          - ``replace``  -> one REORDERED + EXTRA / MISSING fallback
                            depending on which side runs longer

    The output preserves the ordering of the expected sequence so
    reading the report top-to-bottom mirrors reading the expected
    chain.
    """
    expected_t = tuple(expected)
    observed_t = tuple(observed)
    matcher = difflib.SequenceMatcher(a=expected_t, b=observed_t, autojunk=False)
    entries: list[DiffEntry] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                ei = i1 + offset
                oi = j1 + offset
                entries.append(
                    DiffEntry(
                        kind=DiffKind.MATCH,
                        expected_index=ei,
                        observed_index=oi,
                        expected_value=expected_t[ei],
                        observed_value=observed_t[oi],
                        summary=f"match {expected_t[ei]!r} at expected={ei} observed={oi}",
                    )
                )
        elif tag == "insert":
            for offset in range(j2 - j1):
                oi = j1 + offset
                entries.append(
                    DiffEntry(
                        kind=DiffKind.EXTRA,
                        expected_index=None,
                        observed_index=oi,
                        expected_value=None,
                        observed_value=observed_t[oi],
                        summary=f"extra observed value {observed_t[oi]!r} at observed={oi}",
                    )
                )
        elif tag == "delete":
            for offset in range(i2 - i1):
                ei = i1 + offset
                entries.append(
                    DiffEntry(
                        kind=DiffKind.MISSING,
                        expected_index=ei,
                        observed_index=None,
                        expected_value=expected_t[ei],
                        observed_value=None,
                        summary=f"missing expected value {expected_t[ei]!r} at expected={ei}",
                    )
                )
        elif tag == "replace":
            # Pair up replacements; treat each pair as a REORDERED row,
            # then fall back to EXTRA / MISSING for any tail.
            replace_len = min(i2 - i1, j2 - j1)
            for offset in range(replace_len):
                ei = i1 + offset
                oi = j1 + offset
                entries.append(
                    DiffEntry(
                        kind=DiffKind.REORDERED,
                        expected_index=ei,
                        observed_index=oi,
                        expected_value=expected_t[ei],
                        observed_value=observed_t[oi],
                        summary=(
                            f"reordered: expected {expected_t[ei]!r} at "
                            f"expected={ei}, observed {observed_t[oi]!r} at observed={oi}"
                        ),
                    )
                )
            # Any expected-side tail
            for offset in range(replace_len, i2 - i1):
                ei = i1 + offset
                entries.append(
                    DiffEntry(
                        kind=DiffKind.MISSING,
                        expected_index=ei,
                        observed_index=None,
                        expected_value=expected_t[ei],
                        observed_value=None,
                        summary=f"missing expected value {expected_t[ei]!r} at expected={ei}",
                    )
                )
            # Any observed-side tail
            for offset in range(replace_len, j2 - j1):
                oi = j1 + offset
                entries.append(
                    DiffEntry(
                        kind=DiffKind.EXTRA,
                        expected_index=None,
                        observed_index=oi,
                        expected_value=None,
                        observed_value=observed_t[oi],
                        summary=f"extra observed value {observed_t[oi]!r} at observed={oi}",
                    )
                )

    return ReplayDiffReport(
        expected_chain=expected_t,
        observed_chain=observed_t,
        entries=tuple(entries),
        label=label,
    )


__all__ = [
    "DiffKind",
    "DiffEntry",
    "ReplayDiffReport",
    "compare_event_chains",
]
