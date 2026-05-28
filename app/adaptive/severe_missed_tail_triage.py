"""Phase 11C.1C-C-B-B-B-D-C-B - Severe Missed Tail Triage v0.

This module ships a paper / report / evidence-only **root-cause
triage** layer that converts severe-miss cases (e.g. ``RAVEUSDT`` /
``STOUSDT``) from "we missed it" into **auditable root cause**.

The layer consumes the simplified outputs of:

    * Phase 11C.1C-C-B-B-B-D-A  Historical 60D Mover Coverage Audit
      (capture_status, miss reason, candidate-pool / universe /
      symbol-limit gating signals, data-gap flags),
    * Phase 11C.1C-C-B-B-B-D-B  Post-Discovery Outcome Metrics
      (outcome label, detection-timing label, post-seen MFE / MAE,
      remaining-upside-to-peak),
    * Phase 11C.1C-C-B-B-B-D-B.1 Historical Price Path /
      Kline-Path Adapter (price_path_status,
      price_path_missing_reason),
    * Phase 11C.1C-C-B-B-B-D-C-A Reject-to-Outcome Attribution
      (reject_attribution_verdict, primary reason),

and emits, per audited candidate, a closed
:class:`SevereMissRootCause` and :class:`SevereMissSeverity` plus
the ``needs_operator_review`` / ``needs_data_recovery`` /
``needs_rule_review`` flags. ``auto_tuning_allowed`` is hard-pinned
to ``False`` on every emitted record / report.

Phase 11C.1C-C-B-B-B-D-C-B boundary
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
    * automatically adjust any parameter on the basis of any
      severity / root_cause label it emits. A
      ``RISK_REJECTED_FALSE_NEGATIVE`` does **not** authorise the
      Risk Engine to be relaxed; it routes the case to a human
      reviewer.

Phase 12 remains FORBIDDEN. The Risk Engine remains the single
trade-decision gate. ``RAVEUSDT`` / ``STOUSDT`` and similar
severe-miss candidates are recorded as **data-gap or severe-miss
triage candidates only**; this module never asserts a parameter
error from a single coin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

SEVERE_MISSED_TAIL_TRIAGE_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_c_b.severe_missed_tail_triage.v0"
)
SEVERE_MISSED_TAIL_TRIAGE_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_c_b_severe_missed_tail_triage_v0"
)
SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_c_b.severe_missed_tail_triage.v1"
)
KNOWN_SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSIONS: tuple[str, ...] = (
    SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Closed root-cause taxonomy
# ---------------------------------------------------------------------------


class SevereMissRootCause:
    """Closed string-constant taxonomy of severe-miss root causes.

    Implemented as plain string constants on a holder class (not an
    Enum) so payload dictionaries round-trip through JSON without
    losing the literal label.

    Every label is descriptive only - **none** of them authorises a
    real trade, a runtime-knob change, or any rule relaxation.
    """

    UNIVERSE_GAP: str = "UNIVERSE_GAP"
    SYMBOL_LIMIT_GAP: str = "SYMBOL_LIMIT_GAP"
    CANDIDATE_POOL_EVICTED: str = "CANDIDATE_POOL_EVICTED"
    THRESHOLD_TOO_STRICT: str = "THRESHOLD_TOO_STRICT"
    PRE_ANOMALY_WEAK: str = "PRE_ANOMALY_WEAK"
    ANOMALY_TOO_LATE: str = "ANOMALY_TOO_LATE"
    WS_DATA_GAP: str = "WS_DATA_GAP"
    REST_REFERENCE_GAP: str = "REST_REFERENCE_GAP"
    EVENT_HISTORY_MISSING: str = "EVENT_HISTORY_MISSING"
    PRICE_PATH_MISSING: str = "PRICE_PATH_MISSING"
    PRICE_PATH_INSUFFICIENT: str = "PRICE_PATH_INSUFFICIENT"
    NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME: str = (
        "NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME"
    )
    RISK_REJECTED_PROTECTIVE: str = "RISK_REJECTED_PROTECTIVE"
    RISK_REJECTED_FALSE_NEGATIVE: str = "RISK_REJECTED_FALSE_NEGATIVE"
    STRATEGY_MODE_FALSE_NEGATIVE: str = "STRATEGY_MODE_FALSE_NEGATIVE"
    LABEL_WINDOW_TOO_SHORT: str = "LABEL_WINDOW_TOO_SHORT"
    TRUE_DISCOVERY_FAILURE: str = "TRUE_DISCOVERY_FAILURE"
    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"
    UNKNOWN: str = "UNKNOWN"

    ALL: tuple[str, ...] = (
        UNIVERSE_GAP,
        SYMBOL_LIMIT_GAP,
        CANDIDATE_POOL_EVICTED,
        THRESHOLD_TOO_STRICT,
        PRE_ANOMALY_WEAK,
        ANOMALY_TOO_LATE,
        WS_DATA_GAP,
        REST_REFERENCE_GAP,
        EVENT_HISTORY_MISSING,
        PRICE_PATH_MISSING,
        PRICE_PATH_INSUFFICIENT,
        NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME,
        RISK_REJECTED_PROTECTIVE,
        RISK_REJECTED_FALSE_NEGATIVE,
        STRATEGY_MODE_FALSE_NEGATIVE,
        LABEL_WINDOW_TOO_SHORT,
        TRUE_DISCOVERY_FAILURE,
        INSUFFICIENT_EVIDENCE,
        UNKNOWN,
    )

    DATA_GAP: tuple[str, ...] = (
        WS_DATA_GAP,
        REST_REFERENCE_GAP,
        EVENT_HISTORY_MISSING,
        PRICE_PATH_MISSING,
        PRICE_PATH_INSUFFICIENT,
        NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME,
        LABEL_WINDOW_TOO_SHORT,
    )

    SYSTEM_RULE_GAP: tuple[str, ...] = (
        UNIVERSE_GAP,
        SYMBOL_LIMIT_GAP,
        CANDIDATE_POOL_EVICTED,
        THRESHOLD_TOO_STRICT,
        PRE_ANOMALY_WEAK,
        ANOMALY_TOO_LATE,
    )

    RISK_RELATED: tuple[str, ...] = (
        RISK_REJECTED_PROTECTIVE,
        RISK_REJECTED_FALSE_NEGATIVE,
        STRATEGY_MODE_FALSE_NEGATIVE,
    )


# ---------------------------------------------------------------------------
# Closed severity taxonomy
# ---------------------------------------------------------------------------


class SevereMissSeverity:
    """Closed string-constant taxonomy of severe-miss severities.

    The labels are descriptive only. Severity drives **operator
    routing** (review queue, data-recovery queue, rule-review
    queue), NEVER a runtime knob change. ``CRITICAL`` is **not**
    permission to relax the Risk Engine; it is an escalation
    signal for a human reviewer.
    """

    LOW: str = "LOW"
    MEDIUM: str = "MEDIUM"
    HIGH: str = "HIGH"
    SEVERE: str = "SEVERE"
    CRITICAL: str = "CRITICAL"
    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"

    ALL: tuple[str, ...] = (
        LOW,
        MEDIUM,
        HIGH,
        SEVERE,
        CRITICAL,
        INSUFFICIENT_EVIDENCE,
    )


# Map every root-cause label to its default severity. Severity is a
# *triage routing* signal, not a quantitative quality metric.
ROOT_CAUSE_DEFAULT_SEVERITY: dict[str, str] = {
    SevereMissRootCause.UNIVERSE_GAP: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.SYMBOL_LIMIT_GAP: SevereMissSeverity.HIGH,
    SevereMissRootCause.CANDIDATE_POOL_EVICTED: SevereMissSeverity.HIGH,
    SevereMissRootCause.THRESHOLD_TOO_STRICT: SevereMissSeverity.HIGH,
    SevereMissRootCause.PRE_ANOMALY_WEAK: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.ANOMALY_TOO_LATE: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.WS_DATA_GAP: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.REST_REFERENCE_GAP: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.EVENT_HISTORY_MISSING: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.PRICE_PATH_MISSING: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.PRICE_PATH_INSUFFICIENT: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME: (
        SevereMissSeverity.MEDIUM
    ),
    SevereMissRootCause.RISK_REJECTED_PROTECTIVE: SevereMissSeverity.LOW,
    SevereMissRootCause.RISK_REJECTED_FALSE_NEGATIVE: SevereMissSeverity.CRITICAL,
    SevereMissRootCause.STRATEGY_MODE_FALSE_NEGATIVE: SevereMissSeverity.HIGH,
    SevereMissRootCause.LABEL_WINDOW_TOO_SHORT: SevereMissSeverity.MEDIUM,
    SevereMissRootCause.TRUE_DISCOVERY_FAILURE: SevereMissSeverity.SEVERE,
    SevereMissRootCause.INSUFFICIENT_EVIDENCE: (
        SevereMissSeverity.INSUFFICIENT_EVIDENCE
    ),
    SevereMissRootCause.UNKNOWN: SevereMissSeverity.INSUFFICIENT_EVIDENCE,
}


# ---------------------------------------------------------------------------
# Reject-attribution verdict reference set (string-only; we DO NOT
# import the B2-A engine — only the canonical verdict labels).
# ---------------------------------------------------------------------------

#: B2-A reject-attribution verdict labels that this module treats as
#: *protective*. These are **string** labels intentionally — to avoid
#: importing the B2-A module and risking a circular import.
PROTECTIVE_REJECT_ATTRIBUTION_VERDICTS: frozenset[str] = frozenset(
    {
        "CORRECT_PROTECTIVE_REJECT",
        "STOP_SAFETY_REJECT",
        "DATA_QUALITY_REJECT",
        "LIQUIDITY_PROTECTIVE_REJECT",
        "MANIPULATION_PROTECTIVE_REJECT",
        "REBASE_PROTECTIVE_REJECT",
        "SYSTEM_SAFETY_REJECT",
    }
)

#: B2-A verdict label that this module treats as a **false-negative**
#: risk reject. A false-negative reject is a candidate where the Risk
#: Engine refused entry on a non-hard-safety reason and the candidate
#: later ran a meaningful upside.
FALSE_NEGATIVE_REJECT_ATTRIBUTION_VERDICT: str = "FALSE_NEGATIVE_REJECT"

#: B2-A verdict label that signals the strategy_mode itself produced
#: a no-trade outcome (``observe`` / ``reject`` / ``hold``) and the
#: candidate later ran a meaningful upside.
STRATEGY_MODE_FALSE_NEGATIVE_VERDICT: str = "STRATEGY_MODE_FALSE_NEGATIVE"


# ---------------------------------------------------------------------------
# Capture-status labels (D-A / Mover Capture Recall taxonomy)
# ---------------------------------------------------------------------------

#: Audit-status labels that mean the candidate was missed.
MISSED_CAPTURE_STATUSES: frozenset[str] = frozenset(
    {"missed", "MISSED", "partially_captured", "PARTIALLY_CAPTURED"}
)

#: Audit-status labels that explicitly mark the candidate as
#: ``EXCLUDED`` (e.g. delisted / non-USDT-perpetual / out of scope).
EXCLUDED_CAPTURE_STATUSES: frozenset[str] = frozenset(
    {"excluded", "EXCLUDED"}
)

#: Audit-status labels that mark the candidate as captured
#: successfully (used for negative checks only).
CAPTURED_CAPTURE_STATUSES: frozenset[str] = frozenset(
    {"captured", "CAPTURED"}
)


# ---------------------------------------------------------------------------
# Price-path status labels (D-B / B1.1 taxonomy)
# ---------------------------------------------------------------------------

#: Price-path status labels that mean **no usable post-first-seen
#: price path is available**. Triggers the ``PRICE_PATH_MISSING`` /
#: ``NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME`` rule.
PRICE_PATH_MISSING_STATUSES: frozenset[str] = frozenset(
    {
        "missing",
        "MISSING",
        "absent",
        "ABSENT",
        "insufficient",
        "INSUFFICIENT",
        "insufficient_post_first_seen_points",
        "INSUFFICIENT_POST_FIRST_SEEN_POINTS",
    }
)


# ---------------------------------------------------------------------------
# Forbidden-payload guard
# ---------------------------------------------------------------------------


#: Keys that MUST NEVER appear in any payload this module emits. The
#: list is intentionally defensive: it is easier to extend the
#: forbidden set in a follow-up brief than to silently let a
#: trade-authority key slip into a paper / report payload.
SEVERE_MISSED_TAIL_TRIAGE_FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
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


class SevereMissedTailTriageForbiddenFieldError(ValueError):
    """Raised when a payload contains one of the
    :data:`SEVERE_MISSED_TAIL_TRIAGE_FORBIDDEN_PAYLOAD_KEYS`.
    """


def assert_payload_has_no_forbidden_keys(
    payload: Mapping[str, Any] | None,
    *,
    context: str = "",
    forbidden_keys: Iterable[str] = (
        SEVERE_MISSED_TAIL_TRIAGE_FORBIDDEN_PAYLOAD_KEYS
    ),
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
                    raise SevereMissedTailTriageForbiddenFieldError(
                        "severe_missed_tail_triage: payload "
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

#: Minimum ``post_seen_mfe_pct`` for the ``TRUE_DISCOVERY_FAILURE``
#: fall-through rule. The value is descriptive only - changing it
#: does NOT and CANNOT change any runtime knob.
DEFAULT_TRUE_DISCOVERY_FAILURE_MFE_THRESHOLD: float = 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_str_tuple(values: Iterable[Any] | None) -> tuple[str, ...]:
    """Return a deduplicated lowercase tuple of non-empty strings."""

    if not values:
        return ()
    seen: dict[str, None] = {}
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if text not in seen:
            seen[text] = None
    return tuple(seen.keys())


def _normalise_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SevereMissTriageInput:
    """One severe-miss candidate's triage input bundle.

    Carries simplified outputs of D-A / D-B / B1.1 / B2-A. Every
    field is paper / report / evidence only. **No field authorises
    a real trade or modifies any runtime knob.**

    Conventions:
      - ``capture_status`` follows the Mover Capture Recall taxonomy
        (``captured`` / ``partially_captured`` / ``missed`` /
        ``excluded`` / ``insufficient_data``); case is normalised.
      - ``price_path_status`` / ``price_path_missing_reason``
        follow the Phase 11C.1C-C-B-B-B-D-B.1 daily-bucket adapter
        taxonomy.
      - ``reject_attribution_verdict`` is a string label from the
        Phase 11C.1C-C-B-B-B-D-C-A
        :class:`RejectAttributionVerdict` taxonomy. We do NOT
        import that module here - the labels are checked by string
        equality to keep the dependency one-way.
    """

    symbol: str
    reference_window: str = ""
    capture_status: str | None = None
    d_a_miss_reason: str | None = None
    d_b_outcome_label: str | None = None
    d_b_detection_timing_label: str | None = None
    price_path_status: str | None = None
    price_path_missing_reason: str | None = None
    post_seen_mfe_pct: float | None = None
    post_seen_mae_pct: float | None = None
    remaining_upside_to_peak_pct: float | None = None
    candidate_pool_seen: bool | None = None
    candidate_pool_evicted: bool | None = None
    universe_eligible: bool | None = None
    symbol_limit_included: bool | None = None
    reject_attribution_verdict: str | None = None
    reject_attribution_primary_reason: str | None = None
    data_gap_flags: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None
    schema_version: str = SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": str(self.symbol),
            "reference_window": str(self.reference_window),
            "capture_status": self.capture_status,
            "d_a_miss_reason": self.d_a_miss_reason,
            "d_b_outcome_label": self.d_b_outcome_label,
            "d_b_detection_timing_label": self.d_b_detection_timing_label,
            "price_path_status": self.price_path_status,
            "price_path_missing_reason": self.price_path_missing_reason,
            "post_seen_mfe_pct": self.post_seen_mfe_pct,
            "post_seen_mae_pct": self.post_seen_mae_pct,
            "remaining_upside_to_peak_pct": self.remaining_upside_to_peak_pct,
            "candidate_pool_seen": self.candidate_pool_seen,
            "candidate_pool_evicted": self.candidate_pool_evicted,
            "universe_eligible": self.universe_eligible,
            "symbol_limit_included": self.symbol_limit_included,
            "reject_attribution_verdict": self.reject_attribution_verdict,
            "reject_attribution_primary_reason": (
                self.reject_attribution_primary_reason
            ),
            "data_gap_flags": list(self.data_gap_flags),
            "evidence_refs": list(self.evidence_refs),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SevereMissTriageRecord:
    """One triaged severe-miss record.

    Every field is descriptive. ``auto_tuning_allowed`` is
    hard-pinned to ``False`` on every serialised payload. A
    ``CRITICAL`` severity does **NOT** authorise the Risk Engine
    to be loosened; it routes the case to a human.
    """

    symbol: str
    reference_window: str
    severity: str
    root_cause: str
    secondary_causes: tuple[str, ...] = field(default_factory=tuple)
    needs_operator_review: bool = False
    needs_data_recovery: bool = False
    needs_rule_review: bool = False
    auto_tuning_allowed: bool = False
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSION
    source_phase: str = SEVERE_MISSED_TAIL_TRIAGE_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        # ``auto_tuning_allowed`` is hard-pinned to False on every
        # serialised record. A future PR that wants to change this
        # MUST update the brief and the Spec §41 Go/No-Go checklist.
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "symbol": str(self.symbol),
            "reference_window": str(self.reference_window),
            "severity": str(self.severity),
            "root_cause": str(self.root_cause),
            "secondary_causes": list(self.secondary_causes),
            "needs_operator_review": bool(self.needs_operator_review),
            "needs_data_recovery": bool(self.needs_data_recovery),
            "needs_rule_review": bool(self.needs_rule_review),
            "auto_tuning_allowed": False,
            "evidence_refs": list(self.evidence_refs),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SevereMissTriageReport:
    """Aggregate roll-up across many :class:`SevereMissTriageRecord`.

    Every field is descriptive only. The report MUST NEVER trigger
    a real trade or modify any runtime knob. ``auto_tuning_allowed``
    is hard-pinned to ``False`` regardless of any
    ``CRITICAL`` / ``SEVERE`` count.
    """

    reference_window: str
    total_records: int
    severe_count: int
    critical_count: int
    insufficient_evidence_count: int
    root_cause_summary: dict[str, int]
    needs_operator_review_symbols: tuple[str, ...] = field(default_factory=tuple)
    needs_data_recovery_symbols: tuple[str, ...] = field(default_factory=tuple)
    needs_rule_review_symbols: tuple[str, ...] = field(default_factory=tuple)
    notable_symbols: tuple[str, ...] = field(default_factory=tuple)
    records: tuple[SevereMissTriageRecord, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    auto_tuning_allowed: bool = False
    schema_version: str = SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSION
    source_phase: str = SEVERE_MISSED_TAIL_TRIAGE_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "reference_window": str(self.reference_window),
            "total_records": int(self.total_records),
            "severe_count": int(self.severe_count),
            "critical_count": int(self.critical_count),
            "insufficient_evidence_count": int(self.insufficient_evidence_count),
            "root_cause_summary": dict(sorted(self.root_cause_summary.items())),
            "needs_operator_review_symbols": list(
                self.needs_operator_review_symbols
            ),
            "needs_data_recovery_symbols": list(
                self.needs_data_recovery_symbols
            ),
            "needs_rule_review_symbols": list(self.needs_rule_review_symbols),
            "notable_symbols": list(self.notable_symbols),
            "records": [r.to_dict() for r in self.records],
            "warnings": list(self.warnings),
            "evidence_refs": list(self.evidence_refs),
            # ``auto_tuning_allowed`` is hard-pinned to False on every
            # serialised report. SEVERE / CRITICAL counts route to
            # operator review, NEVER to auto-tuning.
            "auto_tuning_allowed": False,
        }


# ---------------------------------------------------------------------------
# Engine config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SevereMissedTailTriageEngineConfig:
    """Tunable thresholds for :class:`SevereMissedTailTriageEngine`.

    The defaults mirror the module-level ``DEFAULT_*`` constants.
    They are descriptive only - changing them does NOT and CANNOT
    change any runtime knob, the Risk Engine, the Execution FSM,
    ``symbol_limit``, candidate-pool capacity, anomaly thresholds,
    or Regime weights.
    """

    true_discovery_failure_mfe_threshold: float = (
        DEFAULT_TRUE_DISCOVERY_FAILURE_MFE_THRESHOLD
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SevereMissedTailTriageEngine:
    """Pure engine that turns one :class:`SevereMissTriageInput`
    into one :class:`SevereMissTriageRecord`, and aggregates a
    sequence of inputs / records into one
    :class:`SevereMissTriageReport`.

    The engine does NOT make a network call, NEVER consults a
    private API, NEVER calls an LLM, and NEVER opens a Telegram
    socket. Every output field is derived deterministically from
    the input.

    Every emitted record / report is paper / report / evidence
    only. ``auto_tuning_allowed`` is hard-pinned to ``False``.
    """

    def __init__(
        self,
        config: SevereMissedTailTriageEngineConfig | None = None,
    ) -> None:
        self._config: SevereMissedTailTriageEngineConfig = (
            config or SevereMissedTailTriageEngineConfig()
        )

    # ----- public

    def triage(
        self,
        triage_input: SevereMissTriageInput,
    ) -> SevereMissTriageRecord:
        """Triage one input. Always returns a record.

        The method is total: even on missing evidence it emits a
        record with root_cause / severity ``INSUFFICIENT_EVIDENCE``
        and the relevant warnings.
        """

        cfg = self._config
        warnings: list[str] = []

        symbol = str(triage_input.symbol or "").strip()
        reference_window = str(triage_input.reference_window or "")
        evidence_refs = tuple(triage_input.evidence_refs or ())
        data_gap_flags = _normalise_str_tuple(triage_input.data_gap_flags)

        capture_status = _normalise_optional_str(triage_input.capture_status)
        price_path_status = _normalise_optional_str(triage_input.price_path_status)
        price_path_missing_reason = _normalise_optional_str(
            triage_input.price_path_missing_reason
        )
        verdict = _normalise_optional_str(triage_input.reject_attribution_verdict)
        verdict_primary = _normalise_optional_str(
            triage_input.reject_attribution_primary_reason
        )
        d_a_miss_reason = _normalise_optional_str(triage_input.d_a_miss_reason)
        d_b_outcome_label = _normalise_optional_str(triage_input.d_b_outcome_label)
        d_b_detection_timing_label = _normalise_optional_str(
            triage_input.d_b_detection_timing_label
        )

        # ---- Step 0: insufficient evidence guard -------------------
        # We refuse to fabricate a root_cause if we lack the
        # evidence_refs that anchor this case to an upstream audit
        # record. We also refuse if every meaningful signal is
        # absent — there is literally nothing to attribute.
        if not symbol:
            warnings.append("missing_symbol")
        if not evidence_refs:
            warnings.append("missing_evidence_refs")

        has_any_signal = any(
            (
                capture_status is not None,
                price_path_status is not None,
                price_path_missing_reason is not None,
                triage_input.candidate_pool_seen is not None,
                triage_input.candidate_pool_evicted is not None,
                triage_input.universe_eligible is not None,
                triage_input.symbol_limit_included is not None,
                verdict is not None,
                d_a_miss_reason is not None,
                d_b_outcome_label is not None,
                d_b_detection_timing_label is not None,
                triage_input.post_seen_mfe_pct is not None,
                bool(data_gap_flags),
            )
        )
        if not has_any_signal:
            warnings.append("missing_triage_signals")

        if (not evidence_refs) or (not symbol) or (not has_any_signal):
            return self._build_record(
                symbol=symbol or "<unknown>",
                reference_window=reference_window,
                root_cause=SevereMissRootCause.INSUFFICIENT_EVIDENCE,
                severity=SevereMissSeverity.INSUFFICIENT_EVIDENCE,
                secondary_causes=(),
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 1: universe gap ---------------------------------
        # Most fundamental: the candidate was never even part of the
        # eligible universe.
        if triage_input.universe_eligible is False:
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=SevereMissRootCause.UNIVERSE_GAP,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=SevereMissRootCause.UNIVERSE_GAP,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[
                    SevereMissRootCause.UNIVERSE_GAP
                ],
                secondary_causes=secondary,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 2: symbol-limit gap -----------------------------
        # Universe-eligible but excluded by ``symbol_limit``.
        if triage_input.symbol_limit_included is False:
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=SevereMissRootCause.SYMBOL_LIMIT_GAP,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=SevereMissRootCause.SYMBOL_LIMIT_GAP,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[
                    SevereMissRootCause.SYMBOL_LIMIT_GAP
                ],
                secondary_causes=secondary,
                needs_operator_review=False,
                needs_data_recovery=False,
                needs_rule_review=True,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 3: candidate pool evicted -----------------------
        # The candidate WAS observed by the radar / candidate pool
        # but was evicted (capacity, scoring tie-break, etc.). This
        # is a system-correctable miss, but does NOT authorise
        # automatic capacity expansion.
        if (
            triage_input.candidate_pool_seen is True
            and triage_input.candidate_pool_evicted is True
        ):
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=SevereMissRootCause.CANDIDATE_POOL_EVICTED,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=SevereMissRootCause.CANDIDATE_POOL_EVICTED,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[
                    SevereMissRootCause.CANDIDATE_POOL_EVICTED
                ],
                secondary_causes=secondary,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 4: price path missing ---------------------------
        # The brief is explicit: when price-path data is missing, do
        # NOT directly assert a threshold problem - we cannot tell
        # what happened from missing data. Route to data-recovery
        # only.
        price_path_is_missing = (
            (price_path_status is not None and price_path_status in PRICE_PATH_MISSING_STATUSES)
            or price_path_missing_reason is not None
        )
        if price_path_is_missing:
            primary_cause = SevereMissRootCause.PRICE_PATH_MISSING
            if price_path_missing_reason is not None and (
                "no_top_mover_row_covering_first_seen_time"
                in price_path_missing_reason.lower()
            ):
                primary_cause = (
                    SevereMissRootCause.NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME
                )
            elif price_path_missing_reason is not None and (
                "insufficient_post_first_seen_points"
                in price_path_missing_reason.lower()
            ):
                primary_cause = SevereMissRootCause.PRICE_PATH_INSUFFICIENT
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=primary_cause,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=primary_cause,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[primary_cause],
                secondary_causes=secondary,
                needs_operator_review=False,
                needs_data_recovery=True,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 5: risk-rejected protective ---------------------
        if verdict is not None and verdict in PROTECTIVE_REJECT_ATTRIBUTION_VERDICTS:
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=SevereMissRootCause.RISK_REJECTED_PROTECTIVE,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=SevereMissRootCause.RISK_REJECTED_PROTECTIVE,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[
                    SevereMissRootCause.RISK_REJECTED_PROTECTIVE
                ],
                secondary_causes=secondary,
                needs_operator_review=False,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 6: risk-rejected false negative -----------------
        if (
            verdict is not None
            and verdict == FALSE_NEGATIVE_REJECT_ATTRIBUTION_VERDICT
        ):
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=SevereMissRootCause.RISK_REJECTED_FALSE_NEGATIVE,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=SevereMissRootCause.RISK_REJECTED_FALSE_NEGATIVE,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[
                    SevereMissRootCause.RISK_REJECTED_FALSE_NEGATIVE
                ],
                secondary_causes=secondary,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=True,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 7: strategy-mode false negative -----------------
        if (
            verdict is not None
            and verdict == STRATEGY_MODE_FALSE_NEGATIVE_VERDICT
        ):
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=SevereMissRootCause.STRATEGY_MODE_FALSE_NEGATIVE,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=SevereMissRootCause.STRATEGY_MODE_FALSE_NEGATIVE,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[
                    SevereMissRootCause.STRATEGY_MODE_FALSE_NEGATIVE
                ],
                secondary_causes=secondary,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=True,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 8: true discovery failure -----------------------
        # No universe / symbol-limit / pool / price-path / risk
        # gap. Capture status says missed AND post-seen MFE is
        # meaningfully positive. The system genuinely failed to
        # discover the mover; route to operator review.
        capture_is_missed = (
            capture_status is not None
            and capture_status in MISSED_CAPTURE_STATUSES
        )
        mfe = triage_input.post_seen_mfe_pct
        mfe_is_clearly_positive = (
            mfe is not None
            and float(mfe) >= float(cfg.true_discovery_failure_mfe_threshold)
        )
        if capture_is_missed and mfe_is_clearly_positive:
            secondary = self._collect_secondary_causes(
                triage_input,
                primary=SevereMissRootCause.TRUE_DISCOVERY_FAILURE,
                data_gap_flags=data_gap_flags,
            )
            return self._build_record(
                symbol=symbol,
                reference_window=reference_window,
                root_cause=SevereMissRootCause.TRUE_DISCOVERY_FAILURE,
                severity=ROOT_CAUSE_DEFAULT_SEVERITY[
                    SevereMissRootCause.TRUE_DISCOVERY_FAILURE
                ],
                secondary_causes=secondary,
                needs_operator_review=True,
                needs_data_recovery=False,
                needs_rule_review=False,
                evidence_refs=evidence_refs,
                warnings=tuple(warnings),
            )

        # ---- Step 9: fall-through -> UNKNOWN ----------------------
        warnings.append("unmatched_triage_pattern")
        secondary = self._collect_secondary_causes(
            triage_input,
            primary=SevereMissRootCause.UNKNOWN,
            data_gap_flags=data_gap_flags,
        )
        return self._build_record(
            symbol=symbol,
            reference_window=reference_window,
            root_cause=SevereMissRootCause.UNKNOWN,
            severity=ROOT_CAUSE_DEFAULT_SEVERITY[SevereMissRootCause.UNKNOWN],
            secondary_causes=secondary,
            needs_operator_review=True,
            needs_data_recovery=False,
            needs_rule_review=False,
            evidence_refs=evidence_refs,
            warnings=tuple(warnings),
        )

    def triage_many(
        self,
        inputs: Sequence[SevereMissTriageInput],
    ) -> tuple[SevereMissTriageRecord, ...]:
        """Triage every input in ``inputs`` independently."""

        return tuple(self.triage(i) for i in inputs)

    # ----- internal builders

    def _collect_secondary_causes(
        self,
        triage_input: SevereMissTriageInput,
        *,
        primary: str,
        data_gap_flags: Sequence[str],
    ) -> tuple[str, ...]:
        """Return up to a small set of *additional* signals that can
        complement the primary root cause for human review.

        Secondary causes are descriptive only and do NOT change
        ``auto_tuning_allowed``.
        """

        seen: dict[str, None] = {}

        def _add(label: str | None) -> None:
            if not label:
                return
            text = str(label).strip()
            if not text:
                return
            if text == primary:
                return
            if text in seen:
                return
            seen[text] = None

        if triage_input.candidate_pool_seen is False:
            _add("candidate_pool_not_seen")
        if (
            triage_input.candidate_pool_seen is True
            and triage_input.candidate_pool_evicted is True
            and primary != SevereMissRootCause.CANDIDATE_POOL_EVICTED
        ):
            _add(SevereMissRootCause.CANDIDATE_POOL_EVICTED)
        if (
            triage_input.symbol_limit_included is False
            and primary != SevereMissRootCause.SYMBOL_LIMIT_GAP
        ):
            _add(SevereMissRootCause.SYMBOL_LIMIT_GAP)
        if (
            triage_input.universe_eligible is False
            and primary != SevereMissRootCause.UNIVERSE_GAP
        ):
            _add(SevereMissRootCause.UNIVERSE_GAP)

        if triage_input.price_path_status:
            _add(f"price_path_status={triage_input.price_path_status}")
        if triage_input.price_path_missing_reason:
            _add(
                f"price_path_missing_reason={triage_input.price_path_missing_reason}"
            )
        if triage_input.d_a_miss_reason:
            _add(f"d_a_miss_reason={triage_input.d_a_miss_reason}")
        if triage_input.d_b_outcome_label:
            _add(f"d_b_outcome_label={triage_input.d_b_outcome_label}")
        if triage_input.d_b_detection_timing_label:
            _add(
                f"d_b_detection_timing_label={triage_input.d_b_detection_timing_label}"
            )
        if triage_input.reject_attribution_verdict:
            _add(
                f"reject_attribution_verdict={triage_input.reject_attribution_verdict}"
            )
        if triage_input.reject_attribution_primary_reason:
            _add(
                "reject_attribution_primary_reason="
                f"{triage_input.reject_attribution_primary_reason}"
            )

        for flag in data_gap_flags[:3]:
            _add(f"data_gap_flag={flag}")

        # Cap secondary causes at 6 so the record stays compact.
        return tuple(list(seen.keys())[:6])

    def _build_record(
        self,
        *,
        symbol: str,
        reference_window: str,
        root_cause: str,
        severity: str,
        secondary_causes: tuple[str, ...],
        needs_operator_review: bool,
        needs_data_recovery: bool,
        needs_rule_review: bool,
        evidence_refs: tuple[str, ...],
        warnings: tuple[str, ...],
    ) -> SevereMissTriageRecord:
        record = SevereMissTriageRecord(
            symbol=str(symbol),
            reference_window=str(reference_window),
            severity=severity,
            root_cause=root_cause,
            secondary_causes=tuple(secondary_causes),
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
            context=f"record:{record.symbol}",
        )
        return record


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_severe_missed_tail_triage_report(
    records: Sequence[SevereMissTriageRecord],
    *,
    reference_window: str = "",
    extra_warnings: Sequence[str] = (),
) -> SevereMissTriageReport:
    """Aggregate ``records`` into a :class:`SevereMissTriageReport`.

    The function is pure; it does not call any network service,
    LLM, or Telegram transport. Every emitted field is descriptive
    paper / report / evidence only. ``auto_tuning_allowed`` is
    hard-pinned to ``False`` regardless of any
    ``CRITICAL`` / ``SEVERE`` count.
    """

    record_tuple = tuple(records)

    root_cause_summary: dict[str, int] = {}
    severe = 0
    critical = 0
    insufficient = 0
    review_symbols: list[str] = []
    rule_review_symbols: list[str] = []
    data_recovery_symbols: list[str] = []
    notable_symbols: list[str] = []
    evidence_refs: list[str] = []

    for record in record_tuple:
        cause = str(record.root_cause)
        root_cause_summary[cause] = root_cause_summary.get(cause, 0) + 1

        severity = str(record.severity)
        if severity == SevereMissSeverity.SEVERE:
            severe += 1
        if severity == SevereMissSeverity.CRITICAL:
            critical += 1
        if severity == SevereMissSeverity.INSUFFICIENT_EVIDENCE:
            insufficient += 1

        if record.needs_operator_review:
            review_symbols.append(str(record.symbol))
        if record.needs_rule_review:
            rule_review_symbols.append(str(record.symbol))
        if record.needs_data_recovery:
            data_recovery_symbols.append(str(record.symbol))

        # Notable: any record that is SEVERE / CRITICAL or whose
        # root_cause is a system-rule gap or a risk-related label.
        if (
            severity in (SevereMissSeverity.SEVERE, SevereMissSeverity.CRITICAL)
            or cause in SevereMissRootCause.SYSTEM_RULE_GAP
            or cause in SevereMissRootCause.RISK_RELATED
        ):
            notable_symbols.append(str(record.symbol))

        evidence_refs.extend(record.evidence_refs)

    report = SevereMissTriageReport(
        reference_window=str(reference_window),
        total_records=len(record_tuple),
        severe_count=severe,
        critical_count=critical,
        insufficient_evidence_count=insufficient,
        root_cause_summary=root_cause_summary,
        needs_operator_review_symbols=tuple(dict.fromkeys(review_symbols)),
        needs_rule_review_symbols=tuple(dict.fromkeys(rule_review_symbols)),
        needs_data_recovery_symbols=tuple(dict.fromkeys(data_recovery_symbols)),
        notable_symbols=tuple(dict.fromkeys(notable_symbols)),
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
    "SEVERE_MISSED_TAIL_TRIAGE_VERSION",
    "SEVERE_MISSED_TAIL_TRIAGE_SOURCE_PHASE",
    "SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSION",
    "KNOWN_SEVERE_MISSED_TAIL_TRIAGE_SCHEMA_VERSIONS",
    "SEVERE_MISSED_TAIL_TRIAGE_FORBIDDEN_PAYLOAD_KEYS",
    "DEFAULT_TRUE_DISCOVERY_FAILURE_MFE_THRESHOLD",
    "PROTECTIVE_REJECT_ATTRIBUTION_VERDICTS",
    "FALSE_NEGATIVE_REJECT_ATTRIBUTION_VERDICT",
    "STRATEGY_MODE_FALSE_NEGATIVE_VERDICT",
    "MISSED_CAPTURE_STATUSES",
    "EXCLUDED_CAPTURE_STATUSES",
    "CAPTURED_CAPTURE_STATUSES",
    "PRICE_PATH_MISSING_STATUSES",
    "ROOT_CAUSE_DEFAULT_SEVERITY",
    "SevereMissRootCause",
    "SevereMissSeverity",
    "SevereMissedTailTriageForbiddenFieldError",
    "SevereMissTriageInput",
    "SevereMissTriageRecord",
    "SevereMissTriageReport",
    "SevereMissedTailTriageEngineConfig",
    "SevereMissedTailTriageEngine",
    "build_severe_missed_tail_triage_report",
    "assert_payload_has_no_forbidden_keys",
]
