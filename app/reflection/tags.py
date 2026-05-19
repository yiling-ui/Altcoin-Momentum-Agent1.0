"""Phase 10B - Reflection Engine mistake-tag vocabulary (Issue #10 Part 2).

A **frozen, deterministic** vocabulary of structured tags the
Reflection Engine attaches to a paper-trade lifecycle. The vocabulary
is intentionally narrow so Phase 10B output is machine-comparable
across runs and across Issue #10 Part 10C / 10D consumers.

Issue #10 Part 10B mandate (excerpt):

    mistake_tags 必须是枚举或固定字符串集合，不允许自由生成。

    至少包含：
        late_entry
        early_exit
        weak_volume
        fake_breakout
        high_trap_score
        ignored_no_trade_gate
        slippage_error
        execution_delay
        stop_not_confirmed
        tail_saved_trade
        tail_failed
        right_tail_success

Phase 10B adds three diagnostic tags so the consumer can tell the
difference between "we observed nothing wrong" and "we did not have
enough data to know":

    insufficient_data           - data quality blocked tag derivation
    no_lifecycle_observed       - the trade has no Phase 9 lifecycle
                                  events (e.g. risk-rejected before
                                  ORDER_SENT)
    incident_during_lifecycle   - a P0 / P1 incident landed inside
                                  the order's window

Phase 10B boundary
------------------

The vocabulary is a Python ``Enum`` of string values. Nothing in this
module:

  - imports an exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads ``os.environ`` for credentials
  - opens a socket
  - calls an LLM
  - defines a write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - mutates global state

Reflection NEVER produces a free-form natural-language reflection -
the Issue brief forbids it. Every observation lands as one of the
values in :class:`MistakeTag`.
"""

from __future__ import annotations

from enum import Enum


class MistakeTag(str, Enum):
    """Structured tag attached to a Reflection result.

    Tags are *additive* - a single ReflectionResult may carry several
    of them (e.g. ``stop_not_confirmed`` + ``slippage_error``). Tags
    are NOT mutually exclusive but the engine uses the same rule for
    every emission so the same lifecycle always produces the same
    tag set.

    The ``str`` mixin makes the enum JSON-safe via ``.value`` so the
    payload is byte-stable across processes.
    """

    # Issue-listed core tags ---------------------------------------------
    LATE_ENTRY = "late_entry"
    EARLY_EXIT = "early_exit"
    WEAK_VOLUME = "weak_volume"
    FAKE_BREAKOUT = "fake_breakout"
    HIGH_TRAP_SCORE = "high_trap_score"
    IGNORED_NO_TRADE_GATE = "ignored_no_trade_gate"
    SLIPPAGE_ERROR = "slippage_error"
    EXECUTION_DELAY = "execution_delay"
    STOP_NOT_CONFIRMED = "stop_not_confirmed"
    TAIL_SAVED_TRADE = "tail_saved_trade"
    TAIL_FAILED = "tail_failed"
    RIGHT_TAIL_SUCCESS = "right_tail_success"

    # Phase 10B diagnostics ---------------------------------------------
    INSUFFICIENT_DATA = "insufficient_data"
    NO_LIFECYCLE_OBSERVED = "no_lifecycle_observed"
    INCIDENT_DURING_LIFECYCLE = "incident_during_lifecycle"


#: Tags that come from the Issue #10 Part 10B brief verbatim. Pinned by
#: tests so a future maintainer cannot silently drop one.
ISSUE_REQUIRED_MISTAKE_TAGS: frozenset[MistakeTag] = frozenset(
    {
        MistakeTag.LATE_ENTRY,
        MistakeTag.EARLY_EXIT,
        MistakeTag.WEAK_VOLUME,
        MistakeTag.FAKE_BREAKOUT,
        MistakeTag.HIGH_TRAP_SCORE,
        MistakeTag.IGNORED_NO_TRADE_GATE,
        MistakeTag.SLIPPAGE_ERROR,
        MistakeTag.EXECUTION_DELAY,
        MistakeTag.STOP_NOT_CONFIRMED,
        MistakeTag.TAIL_SAVED_TRADE,
        MistakeTag.TAIL_FAILED,
        MistakeTag.RIGHT_TAIL_SUCCESS,
    }
)


#: Tags Phase 10B adds for data-quality / diagnostic purposes.
DIAGNOSTIC_MISTAKE_TAGS: frozenset[MistakeTag] = frozenset(
    {
        MistakeTag.INSUFFICIENT_DATA,
        MistakeTag.NO_LIFECYCLE_OBSERVED,
        MistakeTag.INCIDENT_DURING_LIFECYCLE,
    }
)


__all__ = [
    "MistakeTag",
    "ISSUE_REQUIRED_MISTAKE_TAGS",
    "DIAGNOSTIC_MISTAKE_TAGS",
]
