"""Phase 11C.1C-C-B-B-B-E-C - Evidence Contract Baseline v0.

A unified, deterministic, paper / report / evidence-only
``evidence_refs`` contract for every Block A / Block B output
surface that today carries a free-form ``evidence_refs`` tuple
(report / replay / reflection / discovery-quality /
post-discovery / severe-miss / reject-attribution).

The Evidence Contract Baseline v0 establishes ONE rule:

    Any claim must be traceable to evidence; a claim that lacks
    evidence MUST be degraded, NEVER accepted as fact, and NEVER
    silently dropped.

Evidence reference format
-------------------------

The contract recognises a small, closed namespace vocabulary:

  - ``event:<EVENT_TYPE>:<event_id>``
        e.g. ``event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123``
  - ``symbol:<SYMBOL>``
        e.g. ``symbol:RAVEUSDT``
  - ``opportunity:<opportunity_id>``
        e.g. ``opportunity:opp_123``
  - ``scan_batch:<scan_batch_id>``
        e.g. ``scan_batch:batch_42``
  - ``metric:<metric_name>:<window>``
        e.g. ``metric:capture_rate:24h``
  - ``report:<report_id>``
        e.g. ``report:block_b_integrated_evidence_report``

Every other namespace is parsed into ``ref_type ==
EvidenceRefType.UNKNOWN`` with a warning attached and is treated
as invalid for accept-as-fact purposes.

Claim validation rules
----------------------

For every input claim:

  1. The validator parses every ``raw`` evidence ref string.
  2. A claim with **at least one** valid (parsed, non-UNKNOWN)
     evidence ref is accepted (status = ``ACCEPTED``).
  3. A claim with **no** evidence refs is **degraded** to
     status = ``DEGRADED_NO_EVIDENCE``. The original claim text /
     label is preserved verbatim; the ``confidence_label`` is
     forced to ``insufficient_evidence``; ``degraded`` is set to
     ``True``; a ``degradation_reason`` is recorded.
  4. A claim that ONLY carries invalid evidence refs is
     **rejected** as status = ``REJECTED_INVALID_EVIDENCE``. The
     claim is preserved with all warnings; no inference is
     performed.
  5. A claim that carries a mix of valid + invalid evidence refs
     is recorded as status = ``PARTIAL`` with both the valid
     refs and the warnings preserved.
  6. The validator NEVER infers a missing ``evidence_refs``. It
     NEVER calls an LLM. It NEVER consults chat history. It
     NEVER mutates the input.

Phase 11C.1C-C-B-B-B-E-C boundary
---------------------------------

  - ``mode = paper``
  - ``live_trading = False``
  - ``exchange_live_orders = False``
  - ``right_tail = False``
  - ``llm = False``
  - ``telegram_outbound_enabled = False``
  - ``binance_private_api_enabled = False``
  - no Binance API key / secret / signed endpoint / private
    websocket / ``listenKey``
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**
  - **auto_tuning_allowed = False** on every emitted result

The validator MUST NEVER produce any of:

    buy / sell / long / short / direction / side / entry / exit /
    position_size / leverage / stop / stop_loss / target /
    take_profit / risk_budget / order / execution_command /
    runtime_config_patch / symbol_limit_patch / threshold_patch /
    candidate_pool_patch / regime_weight_patch.

A successful Phase 11C.1C-C-B-B-B-E-C only allows the next
phase's Block C checkpoint or AI Evidence Bundle preparation
to start. It does NOT close out cloud evidence and does NOT
authorise live trading or auto-tuning.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
EVIDENCE_CONTRACT_SOURCE_PHASE: str = "phase_11c_1c_c_b_b_b_e_c"
EVIDENCE_CONTRACT_SOURCE_MODULE: str = "evidence_contract_baseline"
EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Forbidden-payload vocabulary (defensive)
# ---------------------------------------------------------------------------
#: Keys that MUST NEVER appear, at any nesting depth, in any payload
#: this module emits. The set codifies the brief's "no trade
#: decisions, no runtime patches" boundary.
FORBIDDEN_EVIDENCE_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        # Direction / trade-decision keys.
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "side",
        "entry",
        "exit",
        # Sizing / leverage / risk-budget keys.
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "stop_price",
        "target",
        "target_price",
        "take_profit",
        "risk_budget",
        "order",
        "order_type",
        "execution_command",
        # Runtime-config patch keys.
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
    }
)


# ---------------------------------------------------------------------------
# Evidence reference vocabulary
# ---------------------------------------------------------------------------
class EvidenceRefType(str, Enum):
    """Closed enum of evidence-reference namespaces.

    Any token outside this enum is parsed as :attr:`UNKNOWN` and
    a warning is attached. Adding a new namespace requires a
    deliberate code change AND a brief amendment.
    """

    EVENT = "event"
    SYMBOL = "symbol"
    OPPORTUNITY = "opportunity"
    SCAN_BATCH = "scan_batch"
    METRIC = "metric"
    REPORT = "report"
    UNKNOWN = "unknown"


_NAMESPACE_TO_REF_TYPE: Mapping[str, EvidenceRefType] = {
    "event": EvidenceRefType.EVENT,
    "symbol": EvidenceRefType.SYMBOL,
    "opportunity": EvidenceRefType.OPPORTUNITY,
    "scan_batch": EvidenceRefType.SCAN_BATCH,
    "metric": EvidenceRefType.METRIC,
    "report": EvidenceRefType.REPORT,
}


# Closed enum of claim outcomes.
class ClaimStatus(str, Enum):
    """Closed status vocabulary for evaluated claims and results."""

    ACCEPTED = "ACCEPTED"
    DEGRADED_NO_EVIDENCE = "DEGRADED_NO_EVIDENCE"
    REJECTED_INVALID_EVIDENCE = "REJECTED_INVALID_EVIDENCE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


_VALID_CONFIDENCE_LABELS: frozenset[str] = frozenset(
    {"high", "medium", "low", "insufficient_evidence"}
)


# ---------------------------------------------------------------------------
# Forbidden-key recursive guard
# ---------------------------------------------------------------------------
def _assert_no_forbidden_keys_recursive(payload: Any, *, context: str) -> None:
    """Raise :class:`ValueError` if any forbidden key appears at any
    nesting depth.

    The check is paranoid-by-design so a future regression cannot
    silently smuggle a ``buy`` / ``leverage`` /
    ``runtime_config_patch`` / ... key into an evidence-contract
    output.
    """

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_str = str(key)
            if key_str in FORBIDDEN_EVIDENCE_PAYLOAD_KEYS:
                raise ValueError(
                    f"evidence contract produced a forbidden payload "
                    f"key {key_str!r} in {context!r}; this is a hard "
                    "violation of Phase 11C.1C-C-B-B-B-E-C boundary."
                )
            _assert_no_forbidden_keys_recursive(value, context=context)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_no_forbidden_keys_recursive(item, context=context)


# ---------------------------------------------------------------------------
# EvidenceRef
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceRef:
    """Parsed evidence reference.

    ``raw`` carries the verbatim input string. The other fields
    describe what the parser learned. ``valid`` is ``True`` if and
    only if the reference parsed into a known namespace AND every
    required component is present + non-empty.

    The class is descriptive only - it never authorises a real
    trade and never carries direction / sizing / risk fields.
    """

    raw: str
    ref_type: EvidenceRefType
    namespace: str
    identifier: str
    valid: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "raw": str(self.raw),
            "ref_type": self.ref_type.value,
            "namespace": str(self.namespace),
            "identifier": str(self.identifier),
            "valid": bool(self.valid),
            "warnings": list(self.warnings),
        }
        _assert_no_forbidden_keys_recursive(
            payload, context="EvidenceRef.to_dict"
        )
        return payload


def parse_evidence_ref(raw: Any) -> EvidenceRef:
    """Parse a single evidence-reference string.

    The parser is total: every input produces an
    :class:`EvidenceRef`. Invalid inputs are flagged with
    ``valid=False`` and a non-empty ``warnings`` tuple. The
    parser NEVER mutates the input and NEVER infers a missing
    ref. It also NEVER calls an LLM and NEVER consults chat
    history.
    """

    warnings: list[str] = []

    if raw is None:
        return EvidenceRef(
            raw="",
            ref_type=EvidenceRefType.UNKNOWN,
            namespace="",
            identifier="",
            valid=False,
            warnings=("evidence_ref_is_none",),
        )

    if not isinstance(raw, str):
        return EvidenceRef(
            raw=str(raw),
            ref_type=EvidenceRefType.UNKNOWN,
            namespace="",
            identifier="",
            valid=False,
            warnings=("evidence_ref_is_not_string",),
        )

    text = raw.strip()
    if not text:
        return EvidenceRef(
            raw=raw,
            ref_type=EvidenceRefType.UNKNOWN,
            namespace="",
            identifier="",
            valid=False,
            warnings=("evidence_ref_is_blank",),
        )

    if ":" not in text:
        warnings.append("evidence_ref_missing_namespace_separator")
        return EvidenceRef(
            raw=raw,
            ref_type=EvidenceRefType.UNKNOWN,
            namespace="",
            identifier=text,
            valid=False,
            warnings=tuple(warnings),
        )

    namespace, _, remainder = text.partition(":")
    namespace = namespace.strip()
    remainder = remainder.strip()

    if not namespace:
        warnings.append("evidence_ref_blank_namespace")
        return EvidenceRef(
            raw=raw,
            ref_type=EvidenceRefType.UNKNOWN,
            namespace="",
            identifier=remainder,
            valid=False,
            warnings=tuple(warnings),
        )

    if not remainder:
        warnings.append("evidence_ref_blank_identifier")
        return EvidenceRef(
            raw=raw,
            ref_type=_NAMESPACE_TO_REF_TYPE.get(
                namespace, EvidenceRefType.UNKNOWN
            ),
            namespace=namespace,
            identifier="",
            valid=False,
            warnings=tuple(warnings),
        )

    ref_type = _NAMESPACE_TO_REF_TYPE.get(namespace)
    if ref_type is None:
        warnings.append(f"evidence_ref_unknown_namespace:{namespace}")
        return EvidenceRef(
            raw=raw,
            ref_type=EvidenceRefType.UNKNOWN,
            namespace=namespace,
            identifier=remainder,
            valid=False,
            warnings=tuple(warnings),
        )

    if ref_type is EvidenceRefType.EVENT:
        # Format: event:<EVENT_TYPE>:<event_id>
        if ":" not in remainder:
            warnings.append("evidence_ref_event_missing_event_id")
            return EvidenceRef(
                raw=raw,
                ref_type=ref_type,
                namespace=namespace,
                identifier=remainder,
                valid=False,
                warnings=tuple(warnings),
            )
        event_type, _, event_id = remainder.partition(":")
        event_type = event_type.strip()
        event_id = event_id.strip()
        if not event_type:
            warnings.append("evidence_ref_event_blank_event_type")
        if not event_id:
            warnings.append("evidence_ref_event_blank_event_id")
        valid = bool(event_type) and bool(event_id)
        return EvidenceRef(
            raw=raw,
            ref_type=ref_type,
            namespace=namespace,
            identifier=remainder,
            valid=valid,
            warnings=tuple(warnings),
        )

    if ref_type is EvidenceRefType.METRIC:
        # Format: metric:<metric_name>:<window>
        if ":" not in remainder:
            warnings.append("evidence_ref_metric_missing_window")
            return EvidenceRef(
                raw=raw,
                ref_type=ref_type,
                namespace=namespace,
                identifier=remainder,
                valid=False,
                warnings=tuple(warnings),
            )
        metric_name, _, window = remainder.partition(":")
        metric_name = metric_name.strip()
        window = window.strip()
        if not metric_name:
            warnings.append("evidence_ref_metric_blank_metric_name")
        if not window:
            warnings.append("evidence_ref_metric_blank_window")
        valid = bool(metric_name) and bool(window)
        return EvidenceRef(
            raw=raw,
            ref_type=ref_type,
            namespace=namespace,
            identifier=remainder,
            valid=valid,
            warnings=tuple(warnings),
        )

    # Single-identifier namespaces (symbol / opportunity /
    # scan_batch / report).
    return EvidenceRef(
        raw=raw,
        ref_type=ref_type,
        namespace=namespace,
        identifier=remainder,
        valid=True,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceClaimInput:
    """Caller-supplied claim. The ``raw`` evidence-ref strings are
    parsed and validated by :class:`EvidenceContractValidator`.

    The input is descriptive only; it never carries direction /
    sizing / risk fields.
    """

    claim_id: str
    claim_type: str
    text_or_label: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "claim_id": str(self.claim_id),
            "claim_type": str(self.claim_type),
            "text_or_label": str(self.text_or_label),
            "evidence_refs": list(self.evidence_refs),
            "confidence_label": (
                str(self.confidence_label)
                if self.confidence_label is not None
                else None
            ),
        }
        _assert_no_forbidden_keys_recursive(
            payload, context="EvidenceClaimInput.to_dict"
        )
        return payload


@dataclass(frozen=True)
class EvidenceClaim:
    """A claim that has been processed by the validator.

    ``status`` is one of :class:`ClaimStatus`. ``parsed_refs``
    preserves every parsed :class:`EvidenceRef` (valid AND
    invalid) verbatim - the validator never drops a ref. The
    ``evidence_refs`` tuple carries only the *valid* raw strings
    so downstream callers can keep round-tripping the contract
    without re-parsing.
    """

    claim_id: str
    claim_type: str
    text_or_label: str
    evidence_refs: tuple[str, ...]
    parsed_refs: tuple[EvidenceRef, ...]
    confidence_label: str
    degraded: bool
    degradation_reason: str | None
    status: ClaimStatus
    warnings: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "claim_id": str(self.claim_id),
            "claim_type": str(self.claim_type),
            "text_or_label": str(self.text_or_label),
            "evidence_refs": list(self.evidence_refs),
            "parsed_refs": [r.to_dict() for r in self.parsed_refs],
            "confidence_label": str(self.confidence_label),
            "degraded": bool(self.degraded),
            "degradation_reason": self.degradation_reason,
            "status": self.status.value,
            "warnings": list(self.warnings),
        }
        _assert_no_forbidden_keys_recursive(
            payload, context="EvidenceClaim.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# EvidenceContractResult
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceContractResult:
    """Aggregate result of one validator run.

    Every numeric counter is descriptive only. The result is
    paper / report / evidence only and NEVER triggers a real
    trade or modifies a runtime knob. ``auto_tuning_allowed`` is
    hard-pinned to ``False`` by ``to_dict`` even if the dataclass
    field is somehow mutated.
    """

    accepted_claim_count: int
    degraded_claim_count: int
    rejected_claim_count: int
    partial_claim_count: int
    missing_evidence_count: int
    invalid_evidence_count: int
    total_claim_count: int
    overall_status: ClaimStatus
    claims: tuple[EvidenceClaim, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    auto_tuning_allowed: bool = False
    schema_version: str = EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION
    source_phase: str = EVIDENCE_CONTRACT_SOURCE_PHASE
    source_module: str = EVIDENCE_CONTRACT_SOURCE_MODULE

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "accepted_claim_count": int(self.accepted_claim_count),
            "degraded_claim_count": int(self.degraded_claim_count),
            "rejected_claim_count": int(self.rejected_claim_count),
            "partial_claim_count": int(self.partial_claim_count),
            "missing_evidence_count": int(self.missing_evidence_count),
            "invalid_evidence_count": int(self.invalid_evidence_count),
            "total_claim_count": int(self.total_claim_count),
            "overall_status": self.overall_status.value,
            "claims": [c.to_dict() for c in self.claims],
            "warnings": list(self.warnings),
            # auto_tuning_allowed is hard-pinned to False at the
            # serialisation boundary so a future regression cannot
            # silently flip the flag by mutating the dataclass.
            "auto_tuning_allowed": False,
        }
        _assert_no_forbidden_keys_recursive(
            payload, context="EvidenceContractResult.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
class EvidenceContractValidator:
    """Pure, deterministic validator for the Evidence Contract Baseline.

    The validator:

      - parses every evidence-ref string,
      - validates the parsed refs against the closed namespace
        vocabulary,
      - degrades a claim with no evidence to
        ``DEGRADED_NO_EVIDENCE`` (NEVER accepts it as fact),
      - rejects a claim whose every ref is invalid as
        ``REJECTED_INVALID_EVIDENCE``,
      - records a claim with a mix of valid + invalid refs as
        ``PARTIAL``,
      - preserves every valid ref verbatim (multi-ref claims keep
        all valid refs in input order),
      - NEVER infers a missing ``evidence_refs``,
      - NEVER calls an LLM, never consults chat history, never
        mutates the input.
    """

    def __init__(self, *, source_phase: str | None = None) -> None:
        self._source_phase = (
            str(source_phase) if source_phase else EVIDENCE_CONTRACT_SOURCE_PHASE
        )

    @property
    def source_phase(self) -> str:
        return self._source_phase

    # ------------------------------------------------------------------
    # Single-claim validation
    # ------------------------------------------------------------------
    def validate_claim(
        self, claim_input: EvidenceClaimInput | Mapping[str, Any]
    ) -> EvidenceClaim:
        """Validate one claim and return an :class:`EvidenceClaim`.

        Accepts either a dataclass :class:`EvidenceClaimInput` or
        a plain ``Mapping``. The validator is total: every input
        produces a claim record (never raises for missing fields).
        """

        normalised = self._coerce_input(claim_input)

        parsed_refs: list[EvidenceRef] = [
            parse_evidence_ref(ref) for ref in normalised.evidence_refs
        ]

        valid_refs = tuple(
            ref.raw for ref in parsed_refs if ref.valid
        )
        invalid_count = sum(1 for ref in parsed_refs if not ref.valid)

        warnings: list[str] = []
        for ref in parsed_refs:
            for warn in ref.warnings:
                warnings.append(f"ref:{ref.raw}:{warn}")

        # Determine status, degraded flag, confidence label.
        if not parsed_refs:
            status = ClaimStatus.DEGRADED_NO_EVIDENCE
            degraded = True
            degradation_reason = "no_evidence_refs_supplied"
            confidence_label = "insufficient_evidence"
        elif valid_refs and invalid_count == 0:
            status = ClaimStatus.ACCEPTED
            degraded = False
            degradation_reason = None
            confidence_label = self._coerce_confidence_label(
                normalised.confidence_label
            )
        elif valid_refs and invalid_count > 0:
            status = ClaimStatus.PARTIAL
            degraded = True
            degradation_reason = "partial_invalid_evidence_refs"
            confidence_label = "low"
        else:
            # parsed_refs non-empty but no valid refs.
            status = ClaimStatus.REJECTED_INVALID_EVIDENCE
            degraded = True
            degradation_reason = "all_evidence_refs_invalid"
            confidence_label = "insufficient_evidence"

        return EvidenceClaim(
            claim_id=normalised.claim_id,
            claim_type=normalised.claim_type,
            text_or_label=normalised.text_or_label,
            evidence_refs=valid_refs,
            parsed_refs=tuple(parsed_refs),
            confidence_label=confidence_label,
            degraded=degraded,
            degradation_reason=degradation_reason,
            status=status,
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # Many-claim validation
    # ------------------------------------------------------------------
    def validate(
        self,
        claims: Iterable[EvidenceClaimInput | Mapping[str, Any]] | None,
    ) -> EvidenceContractResult:
        """Validate every claim and aggregate counts.

        ``claims=None`` and ``claims=()`` are valid inputs and
        produce an empty result with
        ``overall_status = INSUFFICIENT_EVIDENCE``.
        """

        claim_list: list[EvidenceClaim] = []
        warnings: list[str] = []

        if claims is None:
            claim_list = []
        else:
            for raw_claim in claims:
                claim_list.append(self.validate_claim(raw_claim))

        accepted = sum(
            1 for c in claim_list if c.status is ClaimStatus.ACCEPTED
        )
        degraded = sum(
            1 for c in claim_list if c.status is ClaimStatus.DEGRADED_NO_EVIDENCE
        )
        rejected = sum(
            1
            for c in claim_list
            if c.status is ClaimStatus.REJECTED_INVALID_EVIDENCE
        )
        partial = sum(
            1 for c in claim_list if c.status is ClaimStatus.PARTIAL
        )
        missing_evidence = sum(
            1 for c in claim_list if not c.parsed_refs
        )
        invalid_evidence = sum(
            sum(1 for ref in c.parsed_refs if not ref.valid)
            for c in claim_list
        )
        total = len(claim_list)

        overall_status = self._aggregate_status(
            total=total,
            accepted=accepted,
            degraded=degraded,
            rejected=rejected,
            partial=partial,
        )

        if total == 0:
            warnings.append("no_claims_supplied")

        return EvidenceContractResult(
            accepted_claim_count=accepted,
            degraded_claim_count=degraded,
            rejected_claim_count=rejected,
            partial_claim_count=partial,
            missing_evidence_count=missing_evidence,
            invalid_evidence_count=invalid_evidence,
            total_claim_count=total,
            overall_status=overall_status,
            claims=tuple(claim_list),
            warnings=tuple(warnings),
            auto_tuning_allowed=False,
            source_phase=self._source_phase,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_input(
        claim_input: EvidenceClaimInput | Mapping[str, Any],
    ) -> EvidenceClaimInput:
        if isinstance(claim_input, EvidenceClaimInput):
            return claim_input

        if not isinstance(claim_input, Mapping):
            raise TypeError(
                "EvidenceContractValidator.validate_claim expects an "
                "EvidenceClaimInput or a Mapping; got "
                f"{type(claim_input).__name__}"
            )

        raw_refs = claim_input.get("evidence_refs", ())
        if raw_refs is None:
            refs_tuple: tuple[str, ...] = ()
        elif isinstance(raw_refs, str):
            # A single string is treated as a one-element tuple,
            # but we still warn via the parser when appropriate.
            refs_tuple = (raw_refs,)
        elif isinstance(raw_refs, Sequence):
            refs_tuple = tuple(
                ref if isinstance(ref, str) else str(ref)
                for ref in raw_refs
            )
        else:
            refs_tuple = ()

        confidence_label = claim_input.get("confidence_label")
        confidence_label_str: str | None
        if confidence_label is None:
            confidence_label_str = None
        else:
            confidence_label_str = str(confidence_label)

        return EvidenceClaimInput(
            claim_id=str(claim_input.get("claim_id", "")),
            claim_type=str(claim_input.get("claim_type", "")),
            text_or_label=str(claim_input.get("text_or_label", "")),
            evidence_refs=refs_tuple,
            confidence_label=confidence_label_str,
        )

    @staticmethod
    def _coerce_confidence_label(label: str | None) -> str:
        if label is None:
            return "medium"
        text = str(label).strip().lower()
        if text in _VALID_CONFIDENCE_LABELS:
            return text
        return "medium"

    @staticmethod
    def _aggregate_status(
        *,
        total: int,
        accepted: int,
        degraded: int,
        rejected: int,
        partial: int,
    ) -> ClaimStatus:
        if total == 0:
            return ClaimStatus.INSUFFICIENT_EVIDENCE
        if accepted == total:
            return ClaimStatus.ACCEPTED
        if degraded == total:
            return ClaimStatus.DEGRADED_NO_EVIDENCE
        if rejected == total:
            return ClaimStatus.REJECTED_INVALID_EVIDENCE
        if accepted + partial + rejected + degraded == total and (
            partial > 0 or (accepted > 0 and (degraded > 0 or rejected > 0))
        ):
            return ClaimStatus.PARTIAL
        return ClaimStatus.PARTIAL


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------
def validate_claims(
    claims: Iterable[EvidenceClaimInput | Mapping[str, Any]] | None,
) -> EvidenceContractResult:
    """Validate ``claims`` with a default :class:`EvidenceContractValidator`.

    Equivalent to ``EvidenceContractValidator().validate(claims)``;
    provided for callers that do not need to customise the
    validator's source-phase label.
    """

    return EvidenceContractValidator().validate(claims)


__all__ = [
    "EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION",
    "EVIDENCE_CONTRACT_SOURCE_MODULE",
    "EVIDENCE_CONTRACT_SOURCE_PHASE",
    "FORBIDDEN_EVIDENCE_PAYLOAD_KEYS",
    "ClaimStatus",
    "EvidenceClaim",
    "EvidenceClaimInput",
    "EvidenceContractResult",
    "EvidenceContractValidator",
    "EvidenceRef",
    "EvidenceRefType",
    "parse_evidence_ref",
    "validate_claims",
]
