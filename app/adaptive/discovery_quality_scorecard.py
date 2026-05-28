"""Phase 11C.1C-C-B-B-B-D-D - Discovery Quality Scorecard v0.

This module ships a paper / report / evidence-only **discovery
quality scorecard** that compresses the simplified outputs of:

    * Phase 11C.1C-C-B-B-B-D-A  Historical 60D Mover Coverage
      Backfill Audit (capture / miss / data-gap counts),
    * Phase 11C.1C-C-B-B-B-D-B  Post-Discovery Outcome Metrics
      (usable / early / late / severe-miss / insufficient-price-path
      counts),
    * Phase 11C.1C-C-B-B-B-D-C-A Reject-to-Outcome Attribution
      (false-negative reject / correct protective reject counts),
    * Phase 11C.1C-C-B-B-B-D-C-B Severe Missed Tail Triage
      (root-cause summary, severity counts),

into one descriptive :class:`DiscoveryQualityScorecard` per audit
window. The scorecard is a *discovery-quality* signal, **not** a
strategy-quality signal and **not** a trade-approval signal.

Phase 11C.1C-C-B-B-B-D-D boundary
---------------------------------

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
      bucket / rate it emits. ``GOOD`` / ``PARTIAL`` / ``WEAK`` /
      ``DEGRADED`` / ``INSUFFICIENT_EVIDENCE`` are *discovery
      quality* labels, **not** trade-approval labels.

Phase 12 remains FORBIDDEN. The Risk Engine remains the single
trade-decision gate. The scorecard is intentionally *non-actionable*:
it is a routing signal for human operators (review queue, data-recovery
queue, rule-review queue) and never a knob the runtime can turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

DISCOVERY_QUALITY_SCORECARD_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_d.discovery_quality_scorecard.v0"
)
DISCOVERY_QUALITY_SCORECARD_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_d_discovery_quality_scorecard_v0"
)
DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_d.discovery_quality_scorecard.v1"
)
KNOWN_DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSIONS: tuple[str, ...] = (
    DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Closed quality-bucket taxonomy
# ---------------------------------------------------------------------------


class DiscoveryQualityBucket:
    """Closed string-constant taxonomy of discovery-quality buckets.

    Implemented as plain string constants on a holder class (not an
    Enum) so payload dictionaries round-trip through JSON without
    losing the literal label.

    Every label is a *discovery-quality* roll-up only. **None** of
    them is an input to a trade-decision pipeline; the Risk Engine
    remains the single trade-decision gate. ``GOOD`` does NOT mean
    "the strategy is profitable", and ``DEGRADED`` does NOT mean
    "stop trading"; both labels describe the *coverage / capture
    quality* of the discovery layer over the audit window.
    """

    GOOD: str = "GOOD"
    PARTIAL: str = "PARTIAL"
    WEAK: str = "WEAK"
    DEGRADED: str = "DEGRADED"
    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"

    ALL: tuple[str, ...] = (
        GOOD,
        PARTIAL,
        WEAK,
        DEGRADED,
        INSUFFICIENT_EVIDENCE,
    )


# ---------------------------------------------------------------------------
# Forbidden-payload guard
# ---------------------------------------------------------------------------


#: Keys that MUST NEVER appear in any payload this module emits. The
#: list is intentionally defensive: it is easier to extend the
#: forbidden set in a follow-up brief than to silently let a
#: trade-authority key slip into a paper / report payload.
DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
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


class DiscoveryQualityScorecardForbiddenFieldError(ValueError):
    """Raised when a payload contains one of the
    :data:`DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS`.
    """


def assert_payload_has_no_forbidden_keys(
    payload: Mapping[str, Any] | None,
    *,
    context: str = "",
    forbidden_keys: Iterable[str] = (
        DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS
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
                    raise DiscoveryQualityScorecardForbiddenFieldError(
                        "discovery_quality_scorecard: payload "
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

#: Coverage-rate thresholds (descriptive only - changing them does
#: NOT and CANNOT change any runtime knob).
DEFAULT_GOOD_COVERAGE_RATE: float = 0.80
DEFAULT_PARTIAL_COVERAGE_RATE: float = 0.50

#: Usable-discovery-rate thresholds.
DEFAULT_GOOD_USABLE_DISCOVERY_RATE: float = 0.50
DEFAULT_PARTIAL_USABLE_DISCOVERY_RATE: float = 0.25

#: Severe-miss-rate thresholds (lower = healthier).
DEFAULT_SEVERE_MISS_RATE_WARN: float = 0.10
DEFAULT_SEVERE_MISS_RATE_DEGRADED: float = 0.25

#: Data-gap / insufficient-price-path thresholds (lower = healthier).
DEFAULT_DATA_GAP_RATE_WARN: float = 0.20
DEFAULT_DATA_GAP_RATE_DEGRADED: float = 0.50
DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_WARN: float = 0.30
DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_DEGRADED: float = 0.60

#: Late-chase-rate thresholds (lower = healthier).
DEFAULT_LATE_CHASE_RATE_WARN: float = 0.40

#: False-negative reject-rate thresholds.
DEFAULT_FALSE_NEGATIVE_REJECT_RATE_WARN: float = 0.10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_rate(numerator: float | int | None, denominator: float | int | None) -> float:
    """Return ``num / den`` clamped to ``[0.0, 1.0]``; 0.0 if denom is
    zero or either operand is ``None`` / negative.
    """

    if numerator is None or denominator is None:
        return 0.0
    try:
        n = float(numerator)
        d = float(denominator)
    except (TypeError, ValueError):
        return 0.0
    if d <= 0.0:
        return 0.0
    if n <= 0.0:
        return 0.0
    rate = n / d
    if rate < 0.0:
        return 0.0
    if rate > 1.0:
        return 1.0
    return rate


def _normalise_str_tuple(values: Iterable[Any] | None) -> tuple[str, ...]:
    """Return a deduplicated tuple of non-empty stringified values."""

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


def _normalise_root_cause_summary(
    summary: Mapping[str, Any] | None,
) -> dict[str, int]:
    """Return a sorted ``{root_cause_label: count}`` dict.

    The function is defensive: it ignores non-int / negative counts
    and stringifies every key so the dict round-trips through JSON.
    """

    if not summary:
        return {}
    out: dict[str, int] = {}
    for key, value in summary.items():
        if key is None:
            continue
        text = str(key).strip()
        if not text:
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count < 0:
            continue
        out[text] = out.get(text, 0) + count
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscoveryQualityScorecardInput:
    """One audit-window's discovery-quality scorecard input bundle.

    Carries simplified outputs of D-A / D-B / B2-A / B2-B for one
    audit window. Every field is paper / report / evidence only.
    **No field authorises a real trade or modifies any runtime
    knob.**

    Conventions:
      - Counts default to ``0``. The engine's
        ``INSUFFICIENT_EVIDENCE`` guard fires when
        ``coverage_total_count == 0`` *or* ``evidence_refs`` is
        empty.
      - ``root_cause_summary`` is a free-form ``{label: count}``
        dict from the Phase 11C.1C-C-B-B-B-D-C-B Severe Miss
        Triage report (or any other compatible producer).
      - ``evidence_refs`` MUST contain at least one
        ``evt://...`` reference anchoring the scorecard to a
        replayable audit record. The engine refuses to fabricate a
        bucket without such evidence.
    """

    reference_window: str
    coverage_total_count: int = 0
    captured_count: int = 0
    missed_count: int = 0
    usable_discovery_count: int = 0
    early_discovery_count: int = 0
    late_chase_count: int = 0
    severe_miss_count: int = 0
    insufficient_price_path_count: int = 0
    false_negative_reject_count: int = 0
    correct_protective_reject_count: int = 0
    data_gap_count: int = 0
    root_cause_summary: Mapping[str, int] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None
    schema_version: str = DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reference_window": str(self.reference_window),
            "coverage_total_count": int(self.coverage_total_count),
            "captured_count": int(self.captured_count),
            "missed_count": int(self.missed_count),
            "usable_discovery_count": int(self.usable_discovery_count),
            "early_discovery_count": int(self.early_discovery_count),
            "late_chase_count": int(self.late_chase_count),
            "severe_miss_count": int(self.severe_miss_count),
            "insufficient_price_path_count": int(
                self.insufficient_price_path_count
            ),
            "false_negative_reject_count": int(
                self.false_negative_reject_count
            ),
            "correct_protective_reject_count": int(
                self.correct_protective_reject_count
            ),
            "data_gap_count": int(self.data_gap_count),
            "root_cause_summary": _normalise_root_cause_summary(
                self.root_cause_summary
            ),
            "evidence_refs": list(self.evidence_refs),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DiscoveryQualityScorecard:
    """Compressed discovery-quality scorecard for one audit window.

    Every field is descriptive. ``auto_tuning_allowed`` is
    hard-pinned to ``False`` on every serialised payload. A
    ``DEGRADED`` bucket does NOT authorise the Risk Engine to be
    loosened; it routes the case to a human reviewer.
    """

    reference_window: str
    quality_bucket: str
    coverage_rate: float
    usable_discovery_rate: float
    early_discovery_rate: float
    late_chase_rate: float
    severe_miss_rate: float
    insufficient_price_path_rate: float
    false_negative_reject_rate: float
    correct_protective_reject_rate: float
    data_gap_rate: float
    root_cause_summary: Mapping[str, int] = field(default_factory=dict)
    notable_warnings: tuple[str, ...] = field(default_factory=tuple)
    needs_operator_review: bool = False
    needs_data_recovery: bool = False
    needs_rule_review: bool = False
    auto_tuning_allowed: bool = False
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION
    source_phase: str = DISCOVERY_QUALITY_SCORECARD_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        # ``auto_tuning_allowed`` is hard-pinned to False on every
        # serialised scorecard. A future PR that wants to change
        # this MUST update the brief and the Spec §41 Go/No-Go
        # checklist.
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "reference_window": str(self.reference_window),
            "quality_bucket": str(self.quality_bucket),
            "coverage_rate": float(self.coverage_rate),
            "usable_discovery_rate": float(self.usable_discovery_rate),
            "early_discovery_rate": float(self.early_discovery_rate),
            "late_chase_rate": float(self.late_chase_rate),
            "severe_miss_rate": float(self.severe_miss_rate),
            "insufficient_price_path_rate": float(
                self.insufficient_price_path_rate
            ),
            "false_negative_reject_rate": float(
                self.false_negative_reject_rate
            ),
            "correct_protective_reject_rate": float(
                self.correct_protective_reject_rate
            ),
            "data_gap_rate": float(self.data_gap_rate),
            "root_cause_summary": _normalise_root_cause_summary(
                self.root_cause_summary
            ),
            "notable_warnings": list(self.notable_warnings),
            "needs_operator_review": bool(self.needs_operator_review),
            "needs_data_recovery": bool(self.needs_data_recovery),
            "needs_rule_review": bool(self.needs_rule_review),
            # Hard-pinned False. Discovery-quality bucket is NEVER
            # an input to an automated parameter change.
            "auto_tuning_allowed": False,
            "evidence_refs": list(self.evidence_refs),
        }


# ---------------------------------------------------------------------------
# Engine config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscoveryQualityScorecardEngineConfig:
    """Tunable thresholds for :class:`DiscoveryQualityScorecardEngine`.

    The defaults mirror the module-level ``DEFAULT_*`` constants.
    They are descriptive only - changing them does NOT and CANNOT
    change any runtime knob, the Risk Engine, the Execution FSM,
    ``symbol_limit``, candidate-pool capacity, anomaly thresholds,
    or Regime weights.
    """

    good_coverage_rate: float = DEFAULT_GOOD_COVERAGE_RATE
    partial_coverage_rate: float = DEFAULT_PARTIAL_COVERAGE_RATE
    good_usable_discovery_rate: float = DEFAULT_GOOD_USABLE_DISCOVERY_RATE
    partial_usable_discovery_rate: float = (
        DEFAULT_PARTIAL_USABLE_DISCOVERY_RATE
    )
    severe_miss_rate_warn: float = DEFAULT_SEVERE_MISS_RATE_WARN
    severe_miss_rate_degraded: float = DEFAULT_SEVERE_MISS_RATE_DEGRADED
    data_gap_rate_warn: float = DEFAULT_DATA_GAP_RATE_WARN
    data_gap_rate_degraded: float = DEFAULT_DATA_GAP_RATE_DEGRADED
    insufficient_price_path_rate_warn: float = (
        DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_WARN
    )
    insufficient_price_path_rate_degraded: float = (
        DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_DEGRADED
    )
    late_chase_rate_warn: float = DEFAULT_LATE_CHASE_RATE_WARN
    false_negative_reject_rate_warn: float = (
        DEFAULT_FALSE_NEGATIVE_REJECT_RATE_WARN
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


# Quality-bucket ordering used to combine multiple bucket signals
# into a single worst-case bucket. Higher index == worse quality.
_BUCKET_RANK: dict[str, int] = {
    DiscoveryQualityBucket.GOOD: 0,
    DiscoveryQualityBucket.PARTIAL: 1,
    DiscoveryQualityBucket.WEAK: 2,
    DiscoveryQualityBucket.DEGRADED: 3,
    DiscoveryQualityBucket.INSUFFICIENT_EVIDENCE: 4,
}


def _worst_bucket(*buckets: str) -> str:
    """Return the worst (highest-rank) bucket from ``buckets``.

    Unknown labels are treated as ``WEAK`` so a stray label cannot
    falsely upgrade the scorecard to ``GOOD``.
    """

    worst = DiscoveryQualityBucket.GOOD
    worst_rank = _BUCKET_RANK[worst]
    for bucket in buckets:
        rank = _BUCKET_RANK.get(bucket, _BUCKET_RANK[DiscoveryQualityBucket.WEAK])
        if rank > worst_rank:
            worst_rank = rank
            worst = bucket if bucket in _BUCKET_RANK else DiscoveryQualityBucket.WEAK
    return worst


class DiscoveryQualityScorecardEngine:
    """Pure engine that turns one
    :class:`DiscoveryQualityScorecardInput` into one
    :class:`DiscoveryQualityScorecard`.

    The engine does NOT make a network call, NEVER consults a
    private API, NEVER calls an LLM, and NEVER opens a Telegram
    socket. Every output field is derived deterministically from
    the input.

    Every emitted scorecard is paper / report / evidence only.
    ``auto_tuning_allowed`` is hard-pinned to ``False``.
    """

    def __init__(
        self,
        config: DiscoveryQualityScorecardEngineConfig | None = None,
    ) -> None:
        self._config: DiscoveryQualityScorecardEngineConfig = (
            config or DiscoveryQualityScorecardEngineConfig()
        )

    # ----- public

    def evaluate(
        self,
        scorecard_input: DiscoveryQualityScorecardInput,
    ) -> DiscoveryQualityScorecard:
        """Evaluate one input. Always returns a scorecard.

        The method is total: even on missing evidence it emits a
        scorecard with bucket ``INSUFFICIENT_EVIDENCE`` and a
        ``needs_operator_review=True`` flag.
        """

        cfg = self._config

        reference_window = str(scorecard_input.reference_window or "")
        evidence_refs = _normalise_str_tuple(scorecard_input.evidence_refs)
        root_cause_summary = _normalise_root_cause_summary(
            scorecard_input.root_cause_summary
        )

        coverage_total = max(int(scorecard_input.coverage_total_count or 0), 0)
        captured = max(int(scorecard_input.captured_count or 0), 0)
        usable = max(int(scorecard_input.usable_discovery_count or 0), 0)
        early = max(int(scorecard_input.early_discovery_count or 0), 0)
        late_chase = max(int(scorecard_input.late_chase_count or 0), 0)
        severe = max(int(scorecard_input.severe_miss_count or 0), 0)
        ipp = max(int(scorecard_input.insufficient_price_path_count or 0), 0)
        fn_reject = max(
            int(scorecard_input.false_negative_reject_count or 0), 0
        )
        cp_reject = max(
            int(scorecard_input.correct_protective_reject_count or 0), 0
        )
        data_gap = max(int(scorecard_input.data_gap_count or 0), 0)

        # ---- Step 0: insufficient evidence guard ------------------
        if coverage_total <= 0 or not evidence_refs:
            return self._insufficient_evidence(
                reference_window=reference_window,
                root_cause_summary=root_cause_summary,
                evidence_refs=evidence_refs,
            )

        # ---- Step 1: compute rates --------------------------------
        coverage_rate = _safe_rate(captured, coverage_total)
        usable_discovery_rate = _safe_rate(usable, coverage_total)
        early_discovery_rate = _safe_rate(early, coverage_total)
        late_chase_rate = _safe_rate(late_chase, coverage_total)
        severe_miss_rate = _safe_rate(severe, coverage_total)
        insufficient_price_path_rate = _safe_rate(ipp, coverage_total)
        false_negative_reject_rate = _safe_rate(fn_reject, coverage_total)
        correct_protective_reject_rate = _safe_rate(
            cp_reject, coverage_total
        )
        data_gap_rate = _safe_rate(data_gap, coverage_total)

        # ---- Step 2: per-axis bucket signals ----------------------
        warnings: list[str] = []
        needs_operator_review = False
        needs_data_recovery = False
        needs_rule_review = False

        # 2a. coverage / usable-discovery axis (positive signal)
        if (
            coverage_rate >= cfg.good_coverage_rate
            and usable_discovery_rate >= cfg.good_usable_discovery_rate
        ):
            quality_axis_bucket = DiscoveryQualityBucket.GOOD
        elif (
            coverage_rate >= cfg.partial_coverage_rate
            and usable_discovery_rate >= cfg.partial_usable_discovery_rate
        ):
            quality_axis_bucket = DiscoveryQualityBucket.PARTIAL
        elif coverage_rate >= cfg.partial_coverage_rate:
            quality_axis_bucket = DiscoveryQualityBucket.PARTIAL
            warnings.append("usable_discovery_rate_below_partial_threshold")
        else:
            quality_axis_bucket = DiscoveryQualityBucket.WEAK
            warnings.append("coverage_rate_below_partial_threshold")

        # 2b. data-gap / insufficient-price-path axis (B-rule)
        data_axis_bucket = DiscoveryQualityBucket.GOOD
        if data_gap_rate >= cfg.data_gap_rate_degraded:
            data_axis_bucket = DiscoveryQualityBucket.DEGRADED
            warnings.append("data_gap_rate_severe")
            needs_data_recovery = True
        elif data_gap_rate >= cfg.data_gap_rate_warn:
            data_axis_bucket = DiscoveryQualityBucket.PARTIAL
            warnings.append("data_gap_rate_warn")
            needs_data_recovery = True

        if insufficient_price_path_rate >= cfg.insufficient_price_path_rate_degraded:
            data_axis_bucket = _worst_bucket(
                data_axis_bucket, DiscoveryQualityBucket.DEGRADED
            )
            warnings.append("insufficient_price_path_rate_severe")
            needs_data_recovery = True
        elif insufficient_price_path_rate >= cfg.insufficient_price_path_rate_warn:
            data_axis_bucket = _worst_bucket(
                data_axis_bucket, DiscoveryQualityBucket.PARTIAL
            )
            warnings.append("insufficient_price_path_rate_warn")
            needs_data_recovery = True

        # 2c. severe-miss axis (C-rule)
        severe_axis_bucket = DiscoveryQualityBucket.GOOD
        if severe_miss_rate >= cfg.severe_miss_rate_degraded:
            severe_axis_bucket = DiscoveryQualityBucket.DEGRADED
            warnings.append("severe_miss_rate_severe")
            needs_operator_review = True
        elif severe_miss_rate >= cfg.severe_miss_rate_warn:
            severe_axis_bucket = DiscoveryQualityBucket.WEAK
            warnings.append("severe_miss_rate_warn")
            needs_operator_review = True

        # 2d. late-chase axis (informational; bumps PARTIAL ceiling)
        late_axis_bucket = DiscoveryQualityBucket.GOOD
        if late_chase_rate >= cfg.late_chase_rate_warn:
            late_axis_bucket = DiscoveryQualityBucket.PARTIAL
            warnings.append("late_chase_rate_warn")

        # 2e. false-negative reject axis (D-rule)
        if false_negative_reject_rate >= cfg.false_negative_reject_rate_warn:
            warnings.append("false_negative_reject_rate_warn")
            needs_rule_review = True

        # ---- Step 3: combine into final bucket --------------------
        bucket = _worst_bucket(
            quality_axis_bucket,
            data_axis_bucket,
            severe_axis_bucket,
            late_axis_bucket,
        )

        # Insufficient evidence cannot fall out of step 3 because
        # the step 0 guard above intercepts that case.
        scorecard = DiscoveryQualityScorecard(
            reference_window=reference_window,
            quality_bucket=bucket,
            coverage_rate=coverage_rate,
            usable_discovery_rate=usable_discovery_rate,
            early_discovery_rate=early_discovery_rate,
            late_chase_rate=late_chase_rate,
            severe_miss_rate=severe_miss_rate,
            insufficient_price_path_rate=insufficient_price_path_rate,
            false_negative_reject_rate=false_negative_reject_rate,
            correct_protective_reject_rate=correct_protective_reject_rate,
            data_gap_rate=data_gap_rate,
            root_cause_summary=root_cause_summary,
            notable_warnings=tuple(dict.fromkeys(warnings)),
            needs_operator_review=needs_operator_review,
            needs_data_recovery=needs_data_recovery,
            needs_rule_review=needs_rule_review,
            auto_tuning_allowed=False,
            evidence_refs=evidence_refs,
        )

        # Defensive: refuse to emit a scorecard whose payload
        # contains a forbidden trade-authority / runtime-tuning
        # key.
        assert_payload_has_no_forbidden_keys(
            scorecard.to_dict(),
            context=f"scorecard:{scorecard.reference_window}",
        )
        return scorecard

    # ----- internal builders

    def _insufficient_evidence(
        self,
        *,
        reference_window: str,
        root_cause_summary: Mapping[str, int],
        evidence_refs: tuple[str, ...],
    ) -> DiscoveryQualityScorecard:
        """Build an INSUFFICIENT_EVIDENCE scorecard.

        Triggered when ``coverage_total_count == 0`` or
        ``evidence_refs`` is empty. Routes the case to operator
        review only; never to data-recovery / rule-review (we
        cannot tell what is missing without evidence).
        """

        scorecard = DiscoveryQualityScorecard(
            reference_window=reference_window,
            quality_bucket=DiscoveryQualityBucket.INSUFFICIENT_EVIDENCE,
            coverage_rate=0.0,
            usable_discovery_rate=0.0,
            early_discovery_rate=0.0,
            late_chase_rate=0.0,
            severe_miss_rate=0.0,
            insufficient_price_path_rate=0.0,
            false_negative_reject_rate=0.0,
            correct_protective_reject_rate=0.0,
            data_gap_rate=0.0,
            root_cause_summary=root_cause_summary,
            notable_warnings=("insufficient_evidence",),
            needs_operator_review=True,
            needs_data_recovery=False,
            needs_rule_review=False,
            auto_tuning_allowed=False,
            evidence_refs=evidence_refs,
        )
        assert_payload_has_no_forbidden_keys(
            scorecard.to_dict(),
            context=f"scorecard:{reference_window}:insufficient_evidence",
        )
        return scorecard


# ---------------------------------------------------------------------------
# Convenience builder
# ---------------------------------------------------------------------------


def build_discovery_quality_scorecard(
    scorecard_input: DiscoveryQualityScorecardInput,
    *,
    config: DiscoveryQualityScorecardEngineConfig | None = None,
) -> DiscoveryQualityScorecard:
    """Build one :class:`DiscoveryQualityScorecard` from one input.

    Convenience wrapper around :class:`DiscoveryQualityScorecardEngine`
    so callers (daily report, export bundle, replay tests) do not
    need to instantiate the engine themselves.
    """

    return DiscoveryQualityScorecardEngine(config=config).evaluate(
        scorecard_input
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = [
    "DISCOVERY_QUALITY_SCORECARD_VERSION",
    "DISCOVERY_QUALITY_SCORECARD_SOURCE_PHASE",
    "DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION",
    "KNOWN_DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSIONS",
    "DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS",
    "DEFAULT_GOOD_COVERAGE_RATE",
    "DEFAULT_PARTIAL_COVERAGE_RATE",
    "DEFAULT_GOOD_USABLE_DISCOVERY_RATE",
    "DEFAULT_PARTIAL_USABLE_DISCOVERY_RATE",
    "DEFAULT_SEVERE_MISS_RATE_WARN",
    "DEFAULT_SEVERE_MISS_RATE_DEGRADED",
    "DEFAULT_DATA_GAP_RATE_WARN",
    "DEFAULT_DATA_GAP_RATE_DEGRADED",
    "DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_WARN",
    "DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_DEGRADED",
    "DEFAULT_LATE_CHASE_RATE_WARN",
    "DEFAULT_FALSE_NEGATIVE_REJECT_RATE_WARN",
    "DiscoveryQualityBucket",
    "DiscoveryQualityScorecardForbiddenFieldError",
    "DiscoveryQualityScorecardInput",
    "DiscoveryQualityScorecard",
    "DiscoveryQualityScorecardEngineConfig",
    "DiscoveryQualityScorecardEngine",
    "build_discovery_quality_scorecard",
    "assert_payload_has_no_forbidden_keys",
]
