"""Phase 11C.1C-C-B-B-B-D-C-A - Reject-to-Outcome Attribution v0.

This module ships a paper / report / evidence-only attribution
layer that closes the loop between:

    opportunity_id
        -> risk_reject_reason / no_trade_reason / strategy_mode
        -> tail_label / post_discovery_outcome
        -> reject correctness verdict

For every audited candidate, it answers: *was the reject the right
call?*  Possible verdicts:

    * CORRECT_PROTECTIVE_REJECT     - the reject was correct given
      the outcome.
    * FALSE_NEGATIVE_REJECT         - the reject was wrong; the
      candidate ran a meaningful upside that we did not capture
      AND the reject reason was NOT a hard-safety / data-quality /
      liquidity / manipulation / rebase protective reason.
    * DATA_QUALITY_REJECT           - the reject was driven by
      data-quality flags; needs data recovery, not rule
      relaxation.
    * LIQUIDITY_PROTECTIVE_REJECT   - spread / depth / slippage /
      exit-liquidity protective reject.
    * MANIPULATION_PROTECTIVE_REJECT - manipulation / fake-breakout
      / M2 / M3 protective reject.
    * STOP_SAFETY_REJECT            - stop-related safety reject
      (stop_unconfirmed / missing_stop / stop_failed). Even when
      the candidate later runs upside, this stays protective.
    * REBASE_PROTECTIVE_REJECT      - capital rebase / harvest
      protective reject.
    * SYSTEM_SAFETY_REJECT          - protection_mode /
      unknown_position / system safety reject. Stays protective
      even on positive outcome.
    * STRATEGY_MODE_FALSE_NEGATIVE  - no Risk Engine reject; the
      strategy_mode itself produced a no-trade outcome
      (``reject`` / ``observe``) and the candidate later ran
      strong tail.
    * NO_REJECT_FOUND               - the candidate has no reject
      reason and no no-trade strategy_mode; nothing to attribute.
    * INSUFFICIENT_EVIDENCE         - missing evidence_refs /
      missing outcome fields. Refuses to fabricate a verdict.
    * UNKNOWN                       - everything else. Sent to
      operator review.

Phase 11C.1C-C-B-B-B-D-C-A boundary
-----------------------------------

The whole module is paper / report / evidence only. It does
NOT and CANNOT:

    * authorise a real trade,
    * modify a real position,
    * read a private exchange API,
    * sign a request,
    * call an LLM, DeepSeek, or Telegram outbound transport,
    * change ``symbol_limit``, candidate-pool capacity, anomaly
      thresholds, Regime weights, runtime config, or any other
      runtime knob,
    * recommend a direction (long / short / entry / exit / stop /
      target / position size / leverage),
    * loosen the Risk Engine on the basis of any verdict it
      emits. ``FALSE_NEGATIVE_REJECT`` does **not** mean the Risk
      Engine should be relaxed; it means a human must review.

Phase 12 remains FORBIDDEN. The Risk Engine remains the single
trade-decision gate.

Public surface
--------------

    RejectAttributionVerdict        closed string-constant holder.
    RejectAttributionInput          one candidate's input bundle.
    RejectAttributionRecord         one attributed verdict.
    RejectAttributionReport         aggregate roll-up.
    RejectToOutcomeAttributionEngine
                                    pure engine that turns inputs
                                    into records + a report.
    RejectAttributionEngineConfig   tunable thresholds (descriptive
                                    only; never a runtime knob).

    REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS
                                    keys that MUST NEVER appear in
                                    any payload this module emits.
    assert_payload_has_no_forbidden_keys
                                    recursive guard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

REJECT_TO_OUTCOME_ATTRIBUTION_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_c_a.reject_to_outcome_attribution.v0"
)
REJECT_TO_OUTCOME_ATTRIBUTION_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_c_a_reject_to_outcome_attribution_v0"
)
REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_c_a.reject_to_outcome_attribution.v1"
)
KNOWN_REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSIONS: tuple[str, ...] = (
    REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Closed verdict taxonomy
# ---------------------------------------------------------------------------


class RejectAttributionVerdict:
    """Closed string-constant taxonomy of reject-attribution verdicts.

    Implemented as plain string constants on a holder class (not an
    Enum) so payload dictionaries round-trip through JSON without
    losing the literal label.

    Every label is descriptive only - **none** of them authorises a
    real trade, a runtime-knob change, or any rule relaxation. The
    Risk Engine remains the single trade-decision gate.
    """

    CORRECT_PROTECTIVE_REJECT: str = "CORRECT_PROTECTIVE_REJECT"
    FALSE_NEGATIVE_REJECT: str = "FALSE_NEGATIVE_REJECT"
    DATA_QUALITY_REJECT: str = "DATA_QUALITY_REJECT"
    LIQUIDITY_PROTECTIVE_REJECT: str = "LIQUIDITY_PROTECTIVE_REJECT"
    MANIPULATION_PROTECTIVE_REJECT: str = "MANIPULATION_PROTECTIVE_REJECT"
    STOP_SAFETY_REJECT: str = "STOP_SAFETY_REJECT"
    REBASE_PROTECTIVE_REJECT: str = "REBASE_PROTECTIVE_REJECT"
    SYSTEM_SAFETY_REJECT: str = "SYSTEM_SAFETY_REJECT"
    STRATEGY_MODE_FALSE_NEGATIVE: str = "STRATEGY_MODE_FALSE_NEGATIVE"
    NO_REJECT_FOUND: str = "NO_REJECT_FOUND"
    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"
    UNKNOWN: str = "UNKNOWN"

    ALL: tuple[str, ...] = (
        CORRECT_PROTECTIVE_REJECT,
        FALSE_NEGATIVE_REJECT,
        DATA_QUALITY_REJECT,
        LIQUIDITY_PROTECTIVE_REJECT,
        MANIPULATION_PROTECTIVE_REJECT,
        STOP_SAFETY_REJECT,
        REBASE_PROTECTIVE_REJECT,
        SYSTEM_SAFETY_REJECT,
        STRATEGY_MODE_FALSE_NEGATIVE,
        NO_REJECT_FOUND,
        INSUFFICIENT_EVIDENCE,
        UNKNOWN,
    )

    PROTECTIVE: tuple[str, ...] = (
        CORRECT_PROTECTIVE_REJECT,
        STOP_SAFETY_REJECT,
        SYSTEM_SAFETY_REJECT,
        DATA_QUALITY_REJECT,
        LIQUIDITY_PROTECTIVE_REJECT,
        MANIPULATION_PROTECTIVE_REJECT,
        REBASE_PROTECTIVE_REJECT,
    )

    FALSE_NEGATIVE: tuple[str, ...] = (
        FALSE_NEGATIVE_REJECT,
        STRATEGY_MODE_FALSE_NEGATIVE,
    )


# ---------------------------------------------------------------------------
# Reason / flag taxonomy (substring matchers, case-insensitive)
# ---------------------------------------------------------------------------

#: Substrings (matched case-insensitively) that mark a reject reason
#: as **stop-safety** related. A stop-safety reject stays protective
#: even if the candidate later ran upside - we cannot trade without
#: a confirmed stop, full stop.
STOP_SAFETY_REASON_PATTERNS: tuple[str, ...] = (
    "stop_unconfirmed",
    "missing_stop",
    "no_stop",
    "stop_failed",
    "stop_safety",
    "stop_loss_missing",
    "stop_not_set",
)

#: Substrings that mark a reject reason as **system-safety** related.
#: ``unknown_position`` belongs here: trading into an unknown ledger
#: state is unsafe regardless of upside.
SYSTEM_SAFETY_REASON_PATTERNS: tuple[str, ...] = (
    "unknown_position",
    "protection_mode",
    "system_safety",
    "safety_pause",
    "safety_latch",
    "kill_switch",
    "p0_latched_pause",
    "incident_open",
)

#: Substrings that mark a reject reason / data-quality flag as
#: **data-quality** related. These ALWAYS need data recovery, never
#: rule relaxation.
DATA_QUALITY_REASON_PATTERNS: tuple[str, ...] = (
    "data_degraded",
    "data_unreliable",
    "data_quality",
    "ws_stale",
    "ws_data_gap",
    "rest_reference_gap",
    "insufficient_price_path",
    "price_path_gap",
    "stale_data",
    "missing_data",
)

#: Substrings that mark a reject reason as **liquidity-protective**.
LIQUIDITY_REASON_PATTERNS: tuple[str, ...] = (
    "spread",
    "depth",
    "slippage",
    "exit_liquidity",
    "liquidity",
    "thin_book",
    "low_volume",
    "low_liquidity",
)

#: Substrings that mark a reject reason as **manipulation-protective**.
MANIPULATION_REASON_PATTERNS: tuple[str, ...] = (
    "manipulation",
    "fake_breakout",
    "spoof",
    "wash",
    "pump_dump",
    "m2_pattern",
    "m3_pattern",
    "m2_signal",
    "m3_signal",
)

#: Substrings that mark a reject reason as **rebase-protective**.
REBASE_REASON_PATTERNS: tuple[str, ...] = (
    "rebase",
    "capital_rebase",
    "harvest_pause",
    "profit_harvest",
)

#: Strategy modes that signal a no-trade outcome. The candidate
#: never went through the Risk Engine *because* the strategy
#: expression said so.
NO_TRADE_STRATEGY_MODES: frozenset[str] = frozenset(
    {"reject", "observe", "hold", "no_trade", "none"}
)

#: Outcome labels that count as a "strong" upside outcome. Sourced
#: from the Phase 11C.1C-C-A label-tracking taxonomy
#: (``strong_tail``) and the Phase 11C.1C-C-B-B-B-D-B post-discovery
#: outcome taxonomy
#: (``EARLY_CONTINUATION`` / ``MISSED_STRONG_TAIL``).
STRONG_OUTCOME_LABELS: frozenset[str] = frozenset(
    {
        "strong_tail",
        "STRONG_TAIL",
        "early_continuation",
        "EARLY_CONTINUATION",
        "missed_strong_tail",
        "MISSED_STRONG_TAIL",
    }
)

#: Outcome labels that explicitly indicate the candidate did NOT run
#: a strong tail. A reject that aligns with one of these is
#: ``CORRECT_PROTECTIVE_REJECT``.
WEAK_OR_FAIL_OUTCOME_LABELS: frozenset[str] = frozenset(
    {
        "weak_tail",
        "WEAK_TAIL",
        "fake_breakout",
        "FAKE_BREAKOUT",
        "late_chase_failure",
        "LATE_CHASE_FAILURE",
        "dumped",
        "DUMPED",
        "late_reversal",
        "LATE_REVERSAL",
        "exhaustion_candidate",
        "EXHAUSTION_CANDIDATE",
        "no_clear_edge",
        "NO_CLEAR_EDGE",
    }
)


# ---------------------------------------------------------------------------
# Forbidden-payload guard
# ---------------------------------------------------------------------------


#: Keys that MUST NEVER appear in any payload this module emits. The
#: list is intentionally defensive: it is easier to extend the
#: forbidden set in a follow-up brief than to silently let a
#: trade-authority key slip into a paper / report payload.
REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        # Direction / side.
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "side",
        # Order plumbing.
        "entry",
        "entry_price",
        "exit",
        "exit_price",
        "order",
        "order_type",
        "execution_command",
        # Sizing / risk.
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "stop_price",
        "target",
        "target_price",
        "take_profit",
        "risk_budget",
        # Runtime tuning.
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
    }
)


class RejectAttributionForbiddenFieldError(ValueError):
    """Raised when a payload contains one of the
    :data:`REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS`.
    """


def assert_payload_has_no_forbidden_keys(
    payload: Mapping[str, Any] | None,
    *,
    context: str = "",
    forbidden_keys: Iterable[str] = REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS,
) -> None:
    """Recursively raise if ``payload`` contains any forbidden key.

    Walks ``Mapping`` instances and ``list`` / ``tuple`` collections
    inside ``payload``; never recurses into freeform string blobs.
    """

    if payload is None:
        return
    forbidden_set = frozenset(forbidden_keys)

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_str = str(key)
                if key_str in forbidden_set:
                    raise RejectAttributionForbiddenFieldError(
                        "reject_to_outcome_attribution: payload "
                        f"{context or '<unnamed>'} at {path}.{key_str} "
                        "contains forbidden key; the module is paper / "
                        "report / evidence only and MUST NOT carry "
                        "trade-authority or runtime-tuning fields"
                    )
                _walk(value, f"{path}.{key_str}")
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                _walk(item, f"{path}[{index}]")

    _walk(payload, context or "<root>")


# ---------------------------------------------------------------------------
# Default thresholds (descriptive only)
# ---------------------------------------------------------------------------

#: Minimum ``post_seen_mfe_pct`` for a reject to be considered a
#: ``FALSE_NEGATIVE_REJECT``. 5% is conservative; the brief calls it
#: "明显为正". Changing this constant does NOT and CANNOT change any
#: runtime knob, the Risk Engine, the Execution FSM, ``symbol_limit``,
#: candidate-pool capacity, anomaly thresholds, or Regime weights.
DEFAULT_FALSE_NEGATIVE_MFE_THRESHOLD: float = 0.05

#: Minimum ``remaining_upside_to_peak_pct`` that, on its own, would
#: justify treating the outcome as "strong" (in the absence of an
#: explicit outcome label). Used only as a fallback signal.
DEFAULT_STRONG_REMAINING_UPSIDE_PCT: float = 0.20


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


def _normalise_reasons(values: Iterable[str] | None) -> tuple[str, ...]:
    """Return a deduplicated lowercase tuple of non-empty reasons."""

    if not values:
        return ()
    seen: dict[str, None] = {}
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if not text:
            continue
        if text not in seen:
            seen[text] = None
    return tuple(seen.keys())


@dataclass(frozen=True)
class RejectAttributionInput:
    """One candidate's reject-attribution input bundle.

    Carries the identity columns (``opportunity_id``, ``symbol``,
    ``reference_window``, ``first_seen_time_utc_ms``), the reject /
    no-trade signals (``risk_reject_reasons`` / ``no_trade_reasons``
    / ``strategy_mode`` / ``candidate_stage`` /
    ``opportunity_score_bucket``), the outcome surface (``tail_label``
    / ``post_discovery_outcome_label`` / ``detection_timing_label`` /
    ``post_seen_mfe_pct`` / ``post_seen_mae_pct`` /
    ``remaining_upside_to_peak_pct`` / ``price_path_status``), the
    data-quality flags, and the ``evidence_refs`` (links to the
    originating audit records).

    The bundle is paper / report / evidence only. **No field
    authorises a real trade or modifies any runtime knob.**
    """

    opportunity_id: str
    symbol: str = ""
    reference_window: str = ""
    first_seen_time_utc_ms: int | None = None

    risk_reject_reasons: tuple[str, ...] = field(default_factory=tuple)
    no_trade_reasons: tuple[str, ...] = field(default_factory=tuple)
    strategy_mode: str | None = None
    candidate_stage: str | None = None
    opportunity_score_bucket: str | None = None

    tail_label: str | None = None
    post_discovery_outcome_label: str | None = None
    detection_timing_label: str | None = None
    post_seen_mfe_pct: float | None = None
    post_seen_mae_pct: float | None = None
    remaining_upside_to_peak_pct: float | None = None
    price_path_status: str | None = None

    data_quality_flags: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None
    schema_version: str = REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "opportunity_id": str(self.opportunity_id),
            "symbol": str(self.symbol),
            "reference_window": str(self.reference_window),
            "first_seen_time_utc_ms": self.first_seen_time_utc_ms,
            "risk_reject_reasons": list(self.risk_reject_reasons),
            "no_trade_reasons": list(self.no_trade_reasons),
            "strategy_mode": self.strategy_mode,
            "candidate_stage": self.candidate_stage,
            "opportunity_score_bucket": self.opportunity_score_bucket,
            "tail_label": self.tail_label,
            "post_discovery_outcome_label": self.post_discovery_outcome_label,
            "detection_timing_label": self.detection_timing_label,
            "post_seen_mfe_pct": self.post_seen_mfe_pct,
            "post_seen_mae_pct": self.post_seen_mae_pct,
            "remaining_upside_to_peak_pct": self.remaining_upside_to_peak_pct,
            "price_path_status": self.price_path_status,
            "data_quality_flags": list(self.data_quality_flags),
            "evidence_refs": list(self.evidence_refs),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class RejectAttributionRecord:
    """One attributed reject-to-outcome record.

    Carries the identity columns, the closed
    :class:`RejectAttributionVerdict`, the primary / secondary
    reasons, the ``was_reject_protective`` / ``was_false_negative``
    booleans, the operator-review / data-recovery / rule-review
    flags, and the ``evidence_refs``.

    ``auto_tuning_allowed`` is **always** ``False`` on this record.
    A ``FALSE_NEGATIVE_REJECT`` verdict does **NOT** authorise the
    Risk Engine to be loosened; it routes the case to a human.

    The record is paper / report / evidence only. **No field
    authorises a real trade or modifies any runtime knob.**
    """

    opportunity_id: str
    symbol: str
    reference_window: str
    verdict: str
    primary_reason: str
    secondary_reasons: tuple[str, ...] = field(default_factory=tuple)
    was_reject_protective: bool = False
    was_false_negative: bool = False
    needs_operator_review: bool = False
    needs_data_recovery: bool = False
    needs_rule_review: bool = False
    auto_tuning_allowed: bool = False
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION
    source_phase: str = REJECT_TO_OUTCOME_ATTRIBUTION_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        # ``auto_tuning_allowed`` is hard-pinned to False on every
        # serialised record. A future PR that wants to change this
        # MUST update the brief and the Spec §41 Go/No-Go checklist.
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "opportunity_id": str(self.opportunity_id),
            "symbol": str(self.symbol),
            "reference_window": str(self.reference_window),
            "verdict": str(self.verdict),
            "primary_reason": str(self.primary_reason),
            "secondary_reasons": list(self.secondary_reasons),
            "was_reject_protective": bool(self.was_reject_protective),
            "was_false_negative": bool(self.was_false_negative),
            "needs_operator_review": bool(self.needs_operator_review),
            "needs_data_recovery": bool(self.needs_data_recovery),
            "needs_rule_review": bool(self.needs_rule_review),
            "auto_tuning_allowed": False,
            "evidence_refs": list(self.evidence_refs),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RejectAttributionReport:
    """Aggregate roll-up across many :class:`RejectAttributionRecord`.

    Every field is descriptive only. The report MUST NEVER trigger
    a real trade or modify any runtime knob.
    """

    reference_window: str
    total_records: int
    false_negative_reject_count: int
    correct_protective_reject_count: int
    insufficient_evidence_count: int
    verdict_summary: dict[str, int]
    reason_summary: dict[str, int]
    needs_operator_review_symbols: tuple[str, ...] = field(default_factory=tuple)
    needs_rule_review_symbols: tuple[str, ...] = field(default_factory=tuple)
    needs_data_recovery_symbols: tuple[str, ...] = field(default_factory=tuple)
    records: tuple[RejectAttributionRecord, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    auto_tuning_allowed: bool = False
    schema_version: str = REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION
    source_phase: str = REJECT_TO_OUTCOME_ATTRIBUTION_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "reference_window": str(self.reference_window),
            "total_records": int(self.total_records),
            "false_negative_reject_count": int(self.false_negative_reject_count),
            "correct_protective_reject_count": int(
                self.correct_protective_reject_count
            ),
            "insufficient_evidence_count": int(self.insufficient_evidence_count),
            "verdict_summary": dict(sorted(self.verdict_summary.items())),
            "reason_summary": dict(sorted(self.reason_summary.items())),
            "needs_operator_review_symbols": list(
                self.needs_operator_review_symbols
            ),
            "needs_rule_review_symbols": list(self.needs_rule_review_symbols),
            "needs_data_recovery_symbols": list(self.needs_data_recovery_symbols),
            "records": [r.to_dict() for r in self.records],
            "warnings": list(self.warnings),
            "evidence_refs": list(self.evidence_refs),
            # ``auto_tuning_allowed`` is hard-pinned to False on every
            # serialised report. A FALSE_NEGATIVE_REJECT count > 0
            # routes to operator review, NEVER to auto-tuning.
            "auto_tuning_allowed": False,
        }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    """Return True if any pattern is a substring of ``text``
    (already lowercased by the caller).
    """

    for pattern in patterns:
        if pattern and pattern in text:
            return True
    return False


def _classify_reason_category(
    reasons: Sequence[str],
    data_quality_flags: Sequence[str],
) -> str | None:
    """Return the first matching reason-category label, or None.

    Priority ordering enforces the brief's hard-safety priority:

        STOP_SAFETY > SYSTEM_SAFETY > DATA_QUALITY > LIQUIDITY
        > MANIPULATION > REBASE
    """

    haystack = " ".join(list(reasons) + list(data_quality_flags))
    if not haystack:
        return None
    if _matches_any(haystack, STOP_SAFETY_REASON_PATTERNS):
        return RejectAttributionVerdict.STOP_SAFETY_REJECT
    if _matches_any(haystack, SYSTEM_SAFETY_REASON_PATTERNS):
        return RejectAttributionVerdict.SYSTEM_SAFETY_REJECT
    if _matches_any(haystack, DATA_QUALITY_REASON_PATTERNS):
        return RejectAttributionVerdict.DATA_QUALITY_REJECT
    if _matches_any(haystack, LIQUIDITY_REASON_PATTERNS):
        return RejectAttributionVerdict.LIQUIDITY_PROTECTIVE_REJECT
    if _matches_any(haystack, MANIPULATION_REASON_PATTERNS):
        return RejectAttributionVerdict.MANIPULATION_PROTECTIVE_REJECT
    if _matches_any(haystack, REBASE_REASON_PATTERNS):
        return RejectAttributionVerdict.REBASE_PROTECTIVE_REJECT
    return None


def _is_strong_outcome(
    *,
    post_discovery_outcome_label: str | None,
    tail_label: str | None,
    remaining_upside_to_peak_pct: float | None,
    strong_remaining_upside_pct: float,
) -> bool:
    """Return True if the outcome surface signals a meaningful upside."""

    if post_discovery_outcome_label and (
        str(post_discovery_outcome_label) in STRONG_OUTCOME_LABELS
    ):
        return True
    if tail_label and (str(tail_label) in STRONG_OUTCOME_LABELS):
        return True
    if (
        remaining_upside_to_peak_pct is not None
        and float(remaining_upside_to_peak_pct) >= float(strong_remaining_upside_pct)
    ):
        return True
    return False


def _is_weak_or_fail_outcome(
    *,
    post_discovery_outcome_label: str | None,
    tail_label: str | None,
) -> bool:
    """Return True if the outcome surface signals "no real edge" /
    "fake breakout" / "dumped".

    Used to confirm that a non-hard-safety reject was actually
    correct (``CORRECT_PROTECTIVE_REJECT``).
    """

    if post_discovery_outcome_label and (
        str(post_discovery_outcome_label) in WEAK_OR_FAIL_OUTCOME_LABELS
    ):
        return True
    if tail_label and (str(tail_label) in WEAK_OR_FAIL_OUTCOME_LABELS):
        return True
    return False


def _has_outcome_signal(inp: RejectAttributionInput) -> bool:
    """Return True if the input carries at least one outcome field."""

    return any(
        (
            inp.post_discovery_outcome_label is not None,
            inp.detection_timing_label is not None,
            inp.tail_label is not None,
            inp.post_seen_mfe_pct is not None,
            inp.post_seen_mae_pct is not None,
            inp.remaining_upside_to_peak_pct is not None,
        )
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RejectAttributionEngineConfig:
    """Tunable thresholds for :class:`RejectToOutcomeAttributionEngine`.

    The defaults mirror the module-level ``DEFAULT_*`` constants.
    They are descriptive only - changing them does NOT and CANNOT
    change any runtime knob, the Risk Engine, the Execution FSM,
    ``symbol_limit``, candidate-pool capacity, anomaly thresholds,
    or Regime weights.
    """

    false_negative_mfe_threshold: float = DEFAULT_FALSE_NEGATIVE_MFE_THRESHOLD
    strong_remaining_upside_pct: float = DEFAULT_STRONG_REMAINING_UPSIDE_PCT


class RejectToOutcomeAttributionEngine:
    """Pure engine that turns one :class:`RejectAttributionInput` into
    one :class:`RejectAttributionRecord`, and aggregates a sequence
    of inputs / records into one :class:`RejectAttributionReport`.

    The engine does NOT make a network call, NEVER consults a
    private API, NEVER calls an LLM, and NEVER opens a Telegram
    socket. Every output field is derived deterministically from
    the input.

    Every emitted record / report is paper / report / evidence
    only. ``auto_tuning_allowed`` is hard-pinned to ``False``.
    """

    def __init__(
        self,
        config: RejectAttributionEngineConfig | None = None,
    ) -> None:
        self._config: RejectAttributionEngineConfig = (
            config or RejectAttributionEngineConfig()
        )

    # ----- public

    def attribute(
        self,
        attribution_input: RejectAttributionInput,
    ) -> RejectAttributionRecord:
        """Attribute one input. Always returns a record.

        The method is total: even on missing evidence it emits a
        record with verdict ``INSUFFICIENT_EVIDENCE`` and the
        relevant warnings.
        """

        cfg = self._config
        warnings: list[str] = []

        risk_reasons = _normalise_reasons(attribution_input.risk_reject_reasons)
        no_trade_reasons = _normalise_reasons(attribution_input.no_trade_reasons)
        data_quality_flags = _normalise_reasons(
            attribution_input.data_quality_flags
        )
        all_reasons = tuple(dict.fromkeys(risk_reasons + no_trade_reasons))
        strategy_mode = (
            str(attribution_input.strategy_mode).strip().lower()
            if attribution_input.strategy_mode
            else None
        )
        mode_indicates_no_trade = (
            strategy_mode in NO_TRADE_STRATEGY_MODES if strategy_mode else False
        )

        has_explicit_reject = bool(all_reasons) or bool(data_quality_flags)
        has_no_trade_signal = has_explicit_reject or mode_indicates_no_trade

        evidence_refs = tuple(attribution_input.evidence_refs or ())
        outcome_signal_present = _has_outcome_signal(attribution_input)

        # ---- Step 1: no reject signal at all -> NO_REJECT_FOUND ----
        if not has_no_trade_signal:
            return self._build_record(
                attribution_input=attribution_input,
                verdict=RejectAttributionVerdict.NO_REJECT_FOUND,
                primary_reason="no_reject_or_no_trade_signal",
                secondary_reasons=(),
                was_reject_protective=False,
                was_false_negative=False,
                needs_operator_review=False,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 2: insufficient evidence ----
        if not evidence_refs:
            warnings.append("missing_evidence_refs")
            return self._build_record(
                attribution_input=attribution_input,
                verdict=RejectAttributionVerdict.INSUFFICIENT_EVIDENCE,
                primary_reason="missing_evidence_refs",
                secondary_reasons=tuple(all_reasons[:3]),
                was_reject_protective=False,
                was_false_negative=False,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=(),
                warnings=tuple(warnings),
            )
        if not outcome_signal_present:
            warnings.append("missing_outcome_signal")
            return self._build_record(
                attribution_input=attribution_input,
                verdict=RejectAttributionVerdict.INSUFFICIENT_EVIDENCE,
                primary_reason="missing_outcome_signal",
                secondary_reasons=tuple(all_reasons[:3]),
                was_reject_protective=False,
                was_false_negative=False,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 3: hard-safety priority ----
        if has_explicit_reject:
            category = _classify_reason_category(all_reasons, data_quality_flags)
            if category is not None:
                return self._build_protective_record(
                    attribution_input=attribution_input,
                    verdict=category,
                    all_reasons=all_reasons,
                    data_quality_flags=data_quality_flags,
                    evidence_refs=evidence_refs,
                    warnings=tuple(warnings),
                )

        # ---- Step 4: strong-outcome detection ----
        is_strong_outcome = _is_strong_outcome(
            post_discovery_outcome_label=(
                attribution_input.post_discovery_outcome_label
            ),
            tail_label=attribution_input.tail_label,
            remaining_upside_to_peak_pct=(
                attribution_input.remaining_upside_to_peak_pct
            ),
            strong_remaining_upside_pct=cfg.strong_remaining_upside_pct,
        )
        is_positive_mfe = (
            attribution_input.post_seen_mfe_pct is not None
            and float(attribution_input.post_seen_mfe_pct)
            >= float(cfg.false_negative_mfe_threshold)
        )
        is_weak_outcome = _is_weak_or_fail_outcome(
            post_discovery_outcome_label=(
                attribution_input.post_discovery_outcome_label
            ),
            tail_label=attribution_input.tail_label,
        )

        # ---- Step 5: false-negative reject (explicit reject path) ----
        if has_explicit_reject and is_strong_outcome and is_positive_mfe:
            return self._build_record(
                attribution_input=attribution_input,
                verdict=RejectAttributionVerdict.FALSE_NEGATIVE_REJECT,
                primary_reason=(all_reasons[0] if all_reasons else "unknown_reason"),
                secondary_reasons=tuple(all_reasons[1:4]),
                was_reject_protective=False,
                was_false_negative=True,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=True,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 6: strategy-mode false negative ----
        # Triggered when the candidate never went through the Risk
        # Engine because the strategy_mode itself said "reject" /
        # "observe", AND the candidate later ran a strong tail.
        # The brief explicitly requires NO hard-safety reject for
        # this verdict; the hard-safety check above already
        # short-circuits when one is present.
        if mode_indicates_no_trade and is_strong_outcome:
            primary = f"strategy_mode={strategy_mode}"
            return self._build_record(
                attribution_input=attribution_input,
                verdict=RejectAttributionVerdict.STRATEGY_MODE_FALSE_NEGATIVE,
                primary_reason=primary,
                secondary_reasons=tuple(all_reasons[:3]),
                was_reject_protective=False,
                was_false_negative=True,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 7: correct protective reject ----
        # Reached when there IS a reject signal, the outcome did
        # NOT run a strong tail, and the outcome surface explicitly
        # marked the candidate as weak / fake / dumped. The reject
        # was the right call.
        if has_explicit_reject and is_weak_outcome and not is_strong_outcome:
            return self._build_record(
                attribution_input=attribution_input,
                verdict=RejectAttributionVerdict.CORRECT_PROTECTIVE_REJECT,
                primary_reason=(all_reasons[0] if all_reasons else "no_strong_outcome"),
                secondary_reasons=tuple(all_reasons[1:4]),
                was_reject_protective=True,
                was_false_negative=False,
                needs_operator_review=False,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 8: fall-through -> UNKNOWN, route to operator ----
        warnings.append("unmatched_attribution_pattern")
        return self._build_record(
            attribution_input=attribution_input,
            verdict=RejectAttributionVerdict.UNKNOWN,
            primary_reason=(
                all_reasons[0]
                if all_reasons
                else (f"strategy_mode={strategy_mode}" if strategy_mode else "unknown")
            ),
            secondary_reasons=tuple(all_reasons[1:4]),
            was_reject_protective=False,
            was_false_negative=False,
            needs_operator_review=True,
            needs_data_recovery=False,
            needs_rule_review=False,
            evidence_refs=evidence_refs,
            warnings=tuple(warnings),
        )

    def attribute_many(
        self,
        inputs: Sequence[RejectAttributionInput],
    ) -> tuple[RejectAttributionRecord, ...]:
        """Attribute every input in ``inputs`` independently."""

        return tuple(self.attribute(i) for i in inputs)

    # ----- internal builders

    def _build_protective_record(
        self,
        *,
        attribution_input: RejectAttributionInput,
        verdict: str,
        all_reasons: Sequence[str],
        data_quality_flags: Sequence[str],
        evidence_refs: tuple[str, ...],
        warnings: tuple[str, ...],
    ) -> RejectAttributionRecord:
        """Build a record for a hard-safety / protective verdict.

        ``DATA_QUALITY_REJECT`` flips ``needs_data_recovery=True``;
        every other protective verdict flips
        ``was_reject_protective=True`` only.
        """

        is_data_quality = verdict == RejectAttributionVerdict.DATA_QUALITY_REJECT
        secondary = tuple(
            list(all_reasons[:3]) + [f"data_quality_flag={f}" for f in data_quality_flags[:2]]
        )
        primary = (
            all_reasons[0]
            if all_reasons
            else (data_quality_flags[0] if data_quality_flags else "protective")
        )
        return self._build_record(
            attribution_input=attribution_input,
            verdict=verdict,
            primary_reason=primary,
            secondary_reasons=secondary,
            was_reject_protective=True,
            was_false_negative=False,
            needs_operator_review=False,
            needs_data_recovery=is_data_quality,
            needs_rule_review=False,
            evidence_refs=evidence_refs,
            warnings=warnings,
        )

    def _build_record(
        self,
        *,
        attribution_input: RejectAttributionInput,
        verdict: str,
        primary_reason: str,
        secondary_reasons: tuple[str, ...],
        was_reject_protective: bool,
        was_false_negative: bool,
        needs_operator_review: bool,
        needs_data_recovery: bool,
        needs_rule_review: bool,
        evidence_refs: tuple[str, ...],
        warnings: tuple[str, ...],
    ) -> RejectAttributionRecord:
        record = RejectAttributionRecord(
            opportunity_id=str(attribution_input.opportunity_id),
            symbol=str(attribution_input.symbol),
            reference_window=str(attribution_input.reference_window),
            verdict=verdict,
            primary_reason=primary_reason,
            secondary_reasons=tuple(secondary_reasons),
            was_reject_protective=was_reject_protective,
            was_false_negative=was_false_negative,
            needs_operator_review=needs_operator_review,
            needs_data_recovery=needs_data_recovery,
            needs_rule_review=needs_rule_review,
            auto_tuning_allowed=False,
            evidence_refs=tuple(evidence_refs),
            warnings=tuple(warnings),
        )
        # Defensive: refuse to emit a record whose payload contains a
        # forbidden trade-authority / runtime-tuning key.
        assert_payload_has_no_forbidden_keys(
            record.to_dict(),
            context=f"record:{record.opportunity_id}",
        )
        return record


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_reject_attribution_report(
    records: Sequence[RejectAttributionRecord],
    *,
    reference_window: str = "",
    extra_warnings: Sequence[str] = (),
) -> RejectAttributionReport:
    """Aggregate ``records`` into a :class:`RejectAttributionReport`.

    The function is pure; it does not call any network service,
    LLM, or Telegram transport. Every emitted field is descriptive
    paper / report / evidence only. ``auto_tuning_allowed`` is
    hard-pinned to ``False`` regardless of any
    ``FALSE_NEGATIVE_REJECT`` count.
    """

    record_tuple = tuple(records)

    verdict_summary: dict[str, int] = {}
    reason_summary: dict[str, int] = {}
    false_negative = 0
    correct_protective = 0
    insufficient = 0
    review_symbols: list[str] = []
    rule_review_symbols: list[str] = []
    data_recovery_symbols: list[str] = []
    evidence_refs: list[str] = []

    for record in record_tuple:
        verdict = str(record.verdict)
        verdict_summary[verdict] = verdict_summary.get(verdict, 0) + 1
        primary = str(record.primary_reason)
        reason_summary[primary] = reason_summary.get(primary, 0) + 1

        if verdict in (
            RejectAttributionVerdict.FALSE_NEGATIVE_REJECT,
            RejectAttributionVerdict.STRATEGY_MODE_FALSE_NEGATIVE,
        ):
            false_negative += 1
        if verdict == RejectAttributionVerdict.CORRECT_PROTECTIVE_REJECT:
            correct_protective += 1
        # Hard-safety protective verdicts also count as "correct
        # protective" for the aggregate-only counter, since the
        # reject was the right call by safety policy.
        if verdict in (
            RejectAttributionVerdict.STOP_SAFETY_REJECT,
            RejectAttributionVerdict.SYSTEM_SAFETY_REJECT,
            RejectAttributionVerdict.LIQUIDITY_PROTECTIVE_REJECT,
            RejectAttributionVerdict.MANIPULATION_PROTECTIVE_REJECT,
            RejectAttributionVerdict.REBASE_PROTECTIVE_REJECT,
        ):
            correct_protective += 1
        if verdict == RejectAttributionVerdict.INSUFFICIENT_EVIDENCE:
            insufficient += 1
        if record.needs_operator_review:
            review_symbols.append(str(record.symbol or record.opportunity_id))
        if record.needs_rule_review:
            rule_review_symbols.append(str(record.symbol or record.opportunity_id))
        if record.needs_data_recovery:
            data_recovery_symbols.append(str(record.symbol or record.opportunity_id))
        evidence_refs.extend(record.evidence_refs)

    report = RejectAttributionReport(
        reference_window=str(reference_window),
        total_records=len(record_tuple),
        false_negative_reject_count=false_negative,
        correct_protective_reject_count=correct_protective,
        insufficient_evidence_count=insufficient,
        verdict_summary=verdict_summary,
        reason_summary=reason_summary,
        needs_operator_review_symbols=tuple(dict.fromkeys(review_symbols)),
        needs_rule_review_symbols=tuple(dict.fromkeys(rule_review_symbols)),
        needs_data_recovery_symbols=tuple(dict.fromkeys(data_recovery_symbols)),
        records=record_tuple,
        warnings=tuple(extra_warnings),
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        auto_tuning_allowed=False,
    )

    assert_payload_has_no_forbidden_keys(
        report.to_dict(), context=f"report:{reference_window}"
    )
    return report


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = [
    "REJECT_TO_OUTCOME_ATTRIBUTION_VERSION",
    "REJECT_TO_OUTCOME_ATTRIBUTION_SOURCE_PHASE",
    "REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION",
    "KNOWN_REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSIONS",
    "REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS",
    "DEFAULT_FALSE_NEGATIVE_MFE_THRESHOLD",
    "DEFAULT_STRONG_REMAINING_UPSIDE_PCT",
    "STOP_SAFETY_REASON_PATTERNS",
    "SYSTEM_SAFETY_REASON_PATTERNS",
    "DATA_QUALITY_REASON_PATTERNS",
    "LIQUIDITY_REASON_PATTERNS",
    "MANIPULATION_REASON_PATTERNS",
    "REBASE_REASON_PATTERNS",
    "NO_TRADE_STRATEGY_MODES",
    "STRONG_OUTCOME_LABELS",
    "WEAK_OR_FAIL_OUTCOME_LABELS",
    "RejectAttributionVerdict",
    "RejectAttributionForbiddenFieldError",
    "RejectAttributionInput",
    "RejectAttributionRecord",
    "RejectAttributionReport",
    "RejectAttributionEngineConfig",
    "RejectToOutcomeAttributionEngine",
    "build_reject_attribution_report",
    "assert_payload_has_no_forbidden_keys",
]
