"""Phase AI-1 - AI Evidence Bundle Builder v0.

The AI Layer's only allowed read surface. Every later AI /
DeepSeek / LLM call MUST receive a freshly constructed
``AIEvidenceBundle`` and infer ONLY from that bundle. The bundle:

  - is **read-only** (it never carries an order, a direction,
    a stop, a target, a position size, a leverage, a risk
    budget, a runtime-config patch, or any other actionable
    field);
  - is **stateless** (it never carries previous AI answers,
    chat history, ``listenKey`` payloads, signed-endpoint
    payloads, or other long-lived "memory");
  - is **evidence-cited** (every accepted fact carries
    ``evidence_refs`` that point at Truth Layer artefacts);
  - is **deterministic** (same input -> identical bytes);
  - is **JSON-serializable** (``json.dumps(bundle.to_dict())``
    succeeds without a custom encoder);
  - **never** calls an LLM / DeepSeek;
  - **never** opens a network socket;
  - **never** reads or carries API secrets, private account
    state, account orders, account positions, account margin
    snapshots, or any other private exchange / account state.

The implementation enforces the four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md``:

  1. **Responsibility Isolation** - forbidden output fields
     (``buy`` / ``sell`` / ``long`` / ``short`` /
     ``direction`` / ``entry`` / ``exit`` / ``position_size`` /
     ``leverage`` / ``stop`` / ``stop_loss`` / ``target`` /
     ``take_profit`` / ``risk_budget`` / ``order`` /
     ``execution_command`` / ``runtime_config_patch`` /
     ``symbol_limit_patch`` / ``threshold_patch`` /
     ``candidate_pool_patch`` / ``regime_weight_patch`` /
     ``strategy_parameter_patch`` / ``signal_to_trade`` /
     ``should_buy`` / ``should_short``) are pinned into the
     bundle's ``forbidden_fields`` block and the recursive
     :func:`_assert_no_forbidden_fields` guard refuses to emit
     any payload that contains them at any nesting depth.
  2. **Stateless Inference** - the builder rejects any input
     that smells like ``previous_ai_answer`` /
     ``chat_history`` / ``private_account_state`` /
     credential-like keys.
  3. **Hard Rule Anchoring** - facts without
     ``evidence_refs`` are demoted to ``degraded_facts`` and
     a matching warning is recorded; they NEVER appear in the
     accepted ``*_facts`` collections.
  4. **Feedback Isolation** - the bundle pins
     ``ai_output_is_commentary_only = True`` and
     ``ai_output_can_be_training_label = False`` so an AI
     answer can never become a training label or a runtime
     fact.

The bundle additionally pins the project-wide invariants:

  - ``mode = paper``
  - ``live_trading = False``
  - ``exchange_live_orders = False``
  - ``right_tail = False``
  - ``llm = False``
  - ``telegram_outbound_enabled = False``
  - ``binance_private_api_enabled = False``
  - ``phase_12_forbidden = True``
  - ``auto_tuning_allowed = False``

This module is paper / report / evidence-only. It does NOT
authorise live trading, does NOT authorise auto-tuning, does
NOT call DeepSeek / any LLM, and does NOT open Phase 12.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
AI_EVIDENCE_BUNDLE_SOURCE_PHASE: str = "phase_ai_1"
AI_EVIDENCE_BUNDLE_SOURCE_MODULE: str = "ai_evidence_bundle_builder"
AI_EVIDENCE_BUNDLE_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Forbidden AI output fields
# ---------------------------------------------------------------------------
#: Fields that MUST NEVER appear, at any nesting depth, in any
#: payload an AI consumer reads from / writes back through this
#: bundle. Mirrors §3 of the AI Layer Engineering Spec plus the
#: brief's "additive" list.
FORBIDDEN_AI_OUTPUT_FIELDS: frozenset[str] = frozenset(
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
        "strategy_parameter_patch",
        # Signal-to-trade aliases.
        "signal_to_trade",
        "should_buy",
        "should_short",
        # Defensive aliases for "approved" / "live" wording.
        "trading_approved",
        "live_ready",
        "live_trading_allowed",
    }
)


# ---------------------------------------------------------------------------
# Consumer contract
# ---------------------------------------------------------------------------
#: Consumers that MAY read this bundle.
ALLOWED_CONSUMERS: tuple[str, ...] = (
    "human_operator",
    "export_bundle",
    "replay_annotation",
    "reflection_annotation",
    "operator_briefing_report",
)

#: Consumers that MUST NEVER read this bundle. These are the
#: trade-authority / runtime-config surfaces.
FORBIDDEN_CONSUMERS: tuple[str, ...] = (
    "RiskEngine",
    "ExecutionFSM",
    "StrategyEngine",
    "ExchangeGateway",
    "RuntimeConfig",
    "TelegramLiveCommand",
    "CapitalFlow",
    "PositionManager",
)


# ---------------------------------------------------------------------------
# Lookahead policy
# ---------------------------------------------------------------------------
#: Lookahead-policy flags pinned into every bundle. Each flag is
#: a boolean ``True`` so a consumer can read the bundle and
#: programmatically assert the policy without parsing a string
#: list.
LOOKAHEAD_POLICY_FLAGS: tuple[str, ...] = (
    "frozen_evidence_only",
    "no_future_market_data",
    "no_training_from_ai_output",
    "no_runtime_feedback",
    "post_hoc_analysis_only_when_window_closed",
)


# ---------------------------------------------------------------------------
# Forbidden input keys (defensive intake)
# ---------------------------------------------------------------------------
#: Top-level input keys that, if present anywhere in the bundle
#: builder's input mappings, MUST cause an immediate rejection.
#: The list codifies "AI does not read previous AI answers, chat
#: history, or private account state" from §1.2 / §4 of the AI
#: Layer Engineering Spec.
FORBIDDEN_INPUT_KEYS: frozenset[str] = frozenset(
    {
        # Stateless-Inference violations.
        "previous_ai_answer",
        "prior_ai_answer",
        "last_ai_answer",
        "ai_session_history",
        "ai_chat_history",
        "chat_history",
        "conversation_history",
        "assistant_history",
        "previous_briefing",
        "previous_summary",
        "previous_reflection",
        # Private-account-state violations.
        "private_account_state",
        "account_state",
        "account_balance",
        "account_balances",
        "account_positions",
        "account_orders",
        "account_leverage",
        "account_margin",
        "wallet_balance",
        "binance_account_state",
        "binance_private_account_state",
        "listen_key",
        "listenkey",
        "signed_endpoint_payload",
    }
)


#: Substring tokens that, if found in any input mapping key,
#: MUST cause an immediate rejection. The list codifies the
#: "no API secrets in prompt" boundary from §4 of the AI Layer
#: Engineering Spec; the prompt builder (and therefore the
#: bundle builder) MUST fail closed if a credential-shaped key
#: name is detected.
CREDENTIAL_LIKE_KEY_TOKENS: tuple[str, ...] = (
    "api_key",
    "api_secret",
    "private_key",
    "secret_key",
    "auth_token",
    "bearer_token",
    "access_token",
    "refresh_token",
    "credential",
    "password",
    "passphrase",
    "deepseek_api",
    "binance_secret",
    "telegram_token",
    "telegram_bot_token",
)


# Bare-token forbidden keys that are credential-shaped on their
# own (without needing substring containment). These are checked
# against the lowercased exact key name.
_CREDENTIAL_BARE_KEYS: frozenset[str] = frozenset(
    {
        "secret",
        "secrets",
        "token",
    }
)


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------
class AIEvidenceBundleTaskType(str, Enum):
    """Closed task-type vocabulary for the AI Evidence Bundle.

    Each task type matches one of the §2 "Allowed DeepSeek
    first-version outputs" labels. Adding a new task type is a
    deliberate code change AND a brief amendment.
    """

    OPERATOR_BRIEFING = "OPERATOR_BRIEFING"
    MARKET_INTELLIGENCE_SUMMARY = "MARKET_INTELLIGENCE_SUMMARY"
    COVERAGE_AUDIT_INTERPRETATION = "COVERAGE_AUDIT_INTERPRETATION"
    POST_DISCOVERY_OUTCOME_SUMMARY = "POST_DISCOVERY_OUTCOME_SUMMARY"
    REJECT_TO_OUTCOME_SUMMARY = "REJECT_TO_OUTCOME_SUMMARY"
    SEVERE_MISS_SUMMARY = "SEVERE_MISS_SUMMARY"
    REPLAY_REFLECTION_SUMMARY = "REPLAY_REFLECTION_SUMMARY"
    EVIDENCE_COMPRESSION = "EVIDENCE_COMPRESSION"
    CONTRADICTION_SUMMARY = "CONTRADICTION_SUMMARY"
    EVIDENCE_QUALITY_ASSESSMENT = "EVIDENCE_QUALITY_ASSESSMENT"


class AIEvidenceBundleBuildStatus(str, Enum):
    """Closed build-status vocabulary for one bundle build."""

    EVIDENCE_BUNDLE_BUILT = "EVIDENCE_BUNDLE_BUILT"
    EVIDENCE_BUNDLE_DEGRADED = "EVIDENCE_BUNDLE_DEGRADED"
    EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE = (
        "EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE"
    )


class _FactStatus(str, Enum):
    """Internal per-fact status."""

    ACCEPTED = "ACCEPTED"
    DEGRADED_NO_EVIDENCE = "DEGRADED_NO_EVIDENCE"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ForbiddenAIInputError(ValueError):
    """Raised when the bundle builder detects a forbidden input.

    The builder fails closed - it never silently strips or
    transforms a forbidden input. Subclasses :class:`ValueError`
    so callers can ``except ValueError`` if they prefer.
    """


# ---------------------------------------------------------------------------
# Forbidden-key recursive guard
# ---------------------------------------------------------------------------
def _assert_no_forbidden_fields(payload: Any, *, context: str) -> None:
    """Raise :class:`ValueError` if any forbidden output field
    appears at any nesting depth in ``payload``.

    The check is paranoid-by-design so a future regression cannot
    silently smuggle a ``buy`` / ``leverage`` /
    ``runtime_config_patch`` / ``trading_approved`` key into an
    AI Evidence Bundle output.
    """

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_str = str(key)
            if key_str in FORBIDDEN_AI_OUTPUT_FIELDS:
                raise ValueError(
                    f"AI Evidence Bundle produced a forbidden output "
                    f"field {key_str!r} in {context!r}; this is a hard "
                    "violation of the AI Layer Engineering Spec."
                )
            _assert_no_forbidden_fields(value, context=context)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_no_forbidden_fields(item, context=context)


def _looks_like_credential(key: str) -> bool:
    """Return True if the key name looks credential-shaped."""

    text = str(key).strip().lower()
    if not text:
        return False
    if text in _CREDENTIAL_BARE_KEYS:
        return True
    return any(token in text for token in CREDENTIAL_LIKE_KEY_TOKENS)


def _scan_for_forbidden_input(
    payload: Any,
    *,
    context: str,
    path: tuple[str, ...] = (),
) -> None:
    """Recursively scan ``payload`` for forbidden input keys.

    Raises :class:`ForbiddenAIInputError` on the first hit. The
    walk descends into Mapping / list / tuple but never into
    strings (so a string value containing the substring "secret"
    is allowed - only KEY names are forbidden).
    """

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_str = str(key)
            key_lower = key_str.strip().lower()
            here = path + (key_str,)
            if key_lower in FORBIDDEN_INPUT_KEYS:
                raise ForbiddenAIInputError(
                    f"AI Evidence Bundle builder rejected forbidden "
                    f"input key {key_str!r} at "
                    f"{context}.{'.'.join(here)}; AI is not allowed "
                    "to read previous AI answers, chat history, or "
                    "private account state."
                )
            if _looks_like_credential(key_lower):
                raise ForbiddenAIInputError(
                    f"AI Evidence Bundle builder rejected "
                    f"credential-shaped input key {key_str!r} at "
                    f"{context}.{'.'.join(here)}; the AI Layer must "
                    "fail closed when an API secret / credential-"
                    "like key is detected."
                )
            _scan_for_forbidden_input(value, context=context, path=here)
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            _scan_for_forbidden_input(
                item,
                context=context,
                path=path + (f"[{index}]",),
            )
    # Strings / numbers / booleans / None are leaf values - the
    # builder does NOT inspect string contents, only key names.


# ---------------------------------------------------------------------------
# Fact records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIEvidenceBundleFactInput:
    """Caller-supplied fact intended for one of the bundle's
    ``*_facts`` collections.

    The fact is descriptive only; it never carries direction /
    sizing / risk fields. The builder enforces this with the
    recursive forbidden-fields guard.
    """

    fact_id: str
    fact_type: str
    content: Mapping[str, Any]
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    source_report: str | None = None


@dataclass(frozen=True)
class AIEvidenceBundleFact:
    """A fact that has been processed by the bundle builder.

    ``status`` is one of :class:`_FactStatus`. The ``content``
    dictionary is preserved verbatim (after the forbidden-field
    guard rejects any forbidden output key), and ``evidence_refs``
    is preserved in input order so downstream callers can keep
    round-tripping the bundle without re-parsing.
    """

    fact_id: str
    fact_type: str
    content: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    source_report: str | None
    status: str
    degradation_reason: str | None
    schema_version: str = AI_EVIDENCE_BUNDLE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "fact_id": str(self.fact_id),
            "fact_type": str(self.fact_type),
            "evidence_refs": list(self.evidence_refs),
            "source_report": (
                str(self.source_report)
                if self.source_report is not None
                else None
            ),
            "status": str(self.status),
            "degradation_reason": self.degradation_reason,
            "content": _coerce_content(self.content),
        }
        _assert_no_forbidden_fields(
            payload, context="AIEvidenceBundleFact.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIEvidenceBundle:
    """Frozen, evidence-cited, deterministic AI Evidence Bundle.

    Fields mirror the brief's required schema and pin the
    project-wide invariants
    (``ai_output_is_commentary_only=True``,
    ``ai_output_can_be_training_label=False``,
    ``phase_12_forbidden=True``, ``auto_tuning_allowed=False``).
    The bundle is JSON-serializable via :meth:`to_dict`.
    """

    bundle_id: str
    created_at_utc: str
    task_type: AIEvidenceBundleTaskType
    phase_context: Mapping[str, Any]
    reference_window: str
    market_facts: tuple[AIEvidenceBundleFact, ...]
    system_behavior_facts: tuple[AIEvidenceBundleFact, ...]
    outcome_facts: tuple[AIEvidenceBundleFact, ...]
    replay_facts: tuple[AIEvidenceBundleFact, ...]
    reflection_facts: tuple[AIEvidenceBundleFact, ...]
    evidence_contract_facts: tuple[AIEvidenceBundleFact, ...]
    degraded_facts: tuple[AIEvidenceBundleFact, ...]
    evidence_refs: tuple[str, ...]
    source_reports: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    lookahead_policy: Mapping[str, bool]
    consumer_contract: Mapping[str, Any]
    warnings: tuple[str, ...]
    build_status: AIEvidenceBundleBuildStatus
    accepted_fact_count: int
    degraded_fact_count: int
    schema_version: str = AI_EVIDENCE_BUNDLE_SCHEMA_VERSION
    source_phase: str = AI_EVIDENCE_BUNDLE_SOURCE_PHASE
    source_module: str = AI_EVIDENCE_BUNDLE_SOURCE_MODULE
    # Hard-pinned root-constraint flags. The values below are the
    # *defaults*; ``to_dict`` re-pins them at the serialisation
    # boundary even if the dataclass field is somehow mutated.
    ai_output_is_commentary_only: bool = True
    ai_output_can_be_training_label: bool = False
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for this bundle.

        The payload is built in a fixed key order so two builds
        of the same input produce identical bytes after
        ``json.dumps(..., sort_keys=False)``. The recursive
        forbidden-fields guard refuses to emit any payload that
        carries a trade-action / runtime-config-patch key.
        """

        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "bundle_id": str(self.bundle_id),
            "created_at_utc": str(self.created_at_utc),
            "task_type": self.task_type.value,
            "build_status": self.build_status.value,
            "phase_context": _coerce_content(self.phase_context),
            "reference_window": str(self.reference_window),
            "market_facts": [f.to_dict() for f in self.market_facts],
            "system_behavior_facts": [
                f.to_dict() for f in self.system_behavior_facts
            ],
            "outcome_facts": [f.to_dict() for f in self.outcome_facts],
            "replay_facts": [f.to_dict() for f in self.replay_facts],
            "reflection_facts": [
                f.to_dict() for f in self.reflection_facts
            ],
            "evidence_contract_facts": [
                f.to_dict() for f in self.evidence_contract_facts
            ],
            "degraded_facts": [f.to_dict() for f in self.degraded_facts],
            "evidence_refs": list(self.evidence_refs),
            "source_reports": list(self.source_reports),
            "forbidden_fields": list(self.forbidden_fields),
            "lookahead_policy": dict(self.lookahead_policy),
            "consumer_contract": _coerce_content(self.consumer_contract),
            "warnings": list(self.warnings),
            "accepted_fact_count": int(self.accepted_fact_count),
            "degraded_fact_count": int(self.degraded_fact_count),
            # Hard-pinned root-constraint flags - these MUST NEVER
            # be relaxed by a downstream serialiser. We re-emit
            # the safe values here even if the dataclass field has
            # been mutated.
            "ai_output_is_commentary_only": True,
            "ai_output_can_be_training_label": False,
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
            # Project-wide safety-flag invariants.
            "safety_flags": {
                "mode": "paper",
                "live_trading": False,
                "exchange_live_orders": False,
                "right_tail": False,
                "llm": False,
                "telegram_outbound_enabled": False,
                "binance_private_api_enabled": False,
            },
        }
        _assert_no_forbidden_fields(
            payload, context="AIEvidenceBundle.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_content(payload: Any) -> Any:
    """Recursively coerce ``payload`` into a JSON-serializable
    form. Mappings are turned into ``dict``, sequences into
    ``list``, enums into their ``value``. The recursive
    forbidden-fields guard runs on the result.
    """

    if isinstance(payload, Mapping):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            out[str(key)] = _coerce_content(value)
        return out
    if isinstance(payload, (list, tuple)):
        return [_coerce_content(item) for item in payload]
    if isinstance(payload, Enum):
        return payload.value
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    # Fallback: stringify unknown types so the bundle remains
    # JSON-serializable.
    return str(payload)


def _coerce_evidence_refs(refs: Any) -> tuple[str, ...]:
    if refs is None:
        return ()
    if isinstance(refs, str):
        text = refs.strip()
        return (text,) if text else ()
    if isinstance(refs, Sequence):
        out: list[str] = []
        for ref in refs:
            if ref is None:
                continue
            text = str(ref).strip()
            if text:
                out.append(text)
        return tuple(out)
    return ()


def _coerce_fact_input(
    raw: AIEvidenceBundleFactInput | Mapping[str, Any],
    *,
    fact_index: int,
    group: str,
) -> AIEvidenceBundleFactInput:
    if isinstance(raw, AIEvidenceBundleFactInput):
        return raw

    if not isinstance(raw, Mapping):
        raise TypeError(
            f"AI Evidence Bundle builder expects each fact in "
            f"{group!r} to be an AIEvidenceBundleFactInput or a "
            f"Mapping; got {type(raw).__name__} at index {fact_index}."
        )

    fact_id = str(raw.get("fact_id", f"{group}_fact_{fact_index}"))
    fact_type = str(raw.get("fact_type", group))
    content_raw = raw.get("content", {})
    if content_raw is None:
        content: Mapping[str, Any] = {}
    elif isinstance(content_raw, Mapping):
        content = dict(content_raw)
    else:
        raise TypeError(
            f"AI Evidence Bundle builder expects fact.content to be "
            f"a Mapping; got {type(content_raw).__name__} for fact "
            f"{fact_id!r} in group {group!r}."
        )
    evidence_refs = _coerce_evidence_refs(raw.get("evidence_refs"))
    source_report_raw = raw.get("source_report")
    source_report = (
        str(source_report_raw) if source_report_raw is not None else None
    )

    return AIEvidenceBundleFactInput(
        fact_id=fact_id,
        fact_type=fact_type,
        content=content,
        evidence_refs=evidence_refs,
        source_report=source_report,
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
class AIEvidenceBundleBuilder:
    """Pure, deterministic builder for the AI Evidence Bundle.

    The builder:

      - rejects any input that contains a forbidden top-level
        key (``previous_ai_answer`` / ``chat_history`` /
        ``private_account_state`` / credential-like keys);
      - drops or degrades facts without ``evidence_refs``;
      - preserves ``evidence_refs`` (in input order) for every
        accepted fact;
      - injects ``forbidden_fields`` /
        ``lookahead_policy`` / ``consumer_contract`` into every
        bundle;
      - never calls an LLM,
      - never opens a network socket,
      - never reads or carries API secrets,
      - never reads private exchange / account state,
      - never reads previous AI answers,
      - never reads chat history.
    """

    def __init__(self, *, source_phase: str | None = None) -> None:
        self._source_phase = (
            str(source_phase)
            if source_phase
            else AI_EVIDENCE_BUNDLE_SOURCE_PHASE
        )

    @property
    def source_phase(self) -> str:
        return self._source_phase

    # ------------------------------------------------------------------
    # Build entry point
    # ------------------------------------------------------------------
    def build(
        self,
        *,
        bundle_id: str,
        created_at_utc: str,
        task_type: AIEvidenceBundleTaskType | str,
        phase_context: Mapping[str, Any] | None = None,
        reference_window: str | None = None,
        market_facts: Iterable[
            AIEvidenceBundleFactInput | Mapping[str, Any]
        ]
        | None = None,
        system_behavior_facts: Iterable[
            AIEvidenceBundleFactInput | Mapping[str, Any]
        ]
        | None = None,
        outcome_facts: Iterable[
            AIEvidenceBundleFactInput | Mapping[str, Any]
        ]
        | None = None,
        replay_facts: Iterable[
            AIEvidenceBundleFactInput | Mapping[str, Any]
        ]
        | None = None,
        reflection_facts: Iterable[
            AIEvidenceBundleFactInput | Mapping[str, Any]
        ]
        | None = None,
        evidence_contract_facts: Iterable[
            AIEvidenceBundleFactInput | Mapping[str, Any]
        ]
        | None = None,
        source_reports: Iterable[str] | None = None,
        warnings: Iterable[str] | None = None,
    ) -> AIEvidenceBundle:
        """Build one :class:`AIEvidenceBundle` from frozen
        Truth-Layer inputs.

        Every input is scanned for forbidden keys before any
        further processing. The first forbidden hit raises
        :class:`ForbiddenAIInputError`; the builder NEVER
        silently strips or transforms a forbidden input.
        """

        # ------------------------------------------------------------------
        # 0. Coerce + validate task type
        # ------------------------------------------------------------------
        if isinstance(task_type, AIEvidenceBundleTaskType):
            task_type_enum = task_type
        else:
            try:
                task_type_enum = AIEvidenceBundleTaskType(str(task_type))
            except ValueError as exc:
                raise ValueError(
                    f"AI Evidence Bundle builder received unknown "
                    f"task_type={task_type!r}; allowed values are "
                    f"{[t.value for t in AIEvidenceBundleTaskType]}."
                ) from exc

        bundle_id_str = str(bundle_id).strip()
        if not bundle_id_str:
            raise ValueError(
                "AI Evidence Bundle builder requires a non-empty "
                "bundle_id; deterministic identifiers must be "
                "supplied by the caller."
            )

        created_at_utc_str = str(created_at_utc).strip()
        if not created_at_utc_str:
            raise ValueError(
                "AI Evidence Bundle builder requires a non-empty "
                "created_at_utc string; the AI Layer must not "
                "synthesize timestamps."
            )

        reference_window_str = (
            str(reference_window).strip()
            if reference_window is not None
            else "unspecified"
        )
        if not reference_window_str:
            reference_window_str = "unspecified"

        # ------------------------------------------------------------------
        # 1. Forbidden-input scan on every supplied mapping
        # ------------------------------------------------------------------
        if phase_context is not None and not isinstance(
            phase_context, Mapping
        ):
            raise TypeError(
                "AI Evidence Bundle builder expects phase_context to "
                f"be a Mapping or None; got {type(phase_context).__name__}."
            )
        phase_context_map: Mapping[str, Any] = (
            dict(phase_context) if phase_context is not None else {}
        )
        _scan_for_forbidden_input(
            phase_context_map, context="phase_context"
        )

        accepted_groups: dict[str, list[AIEvidenceBundleFact]] = {
            "market_facts": [],
            "system_behavior_facts": [],
            "outcome_facts": [],
            "replay_facts": [],
            "reflection_facts": [],
            "evidence_contract_facts": [],
        }

        all_degraded: list[AIEvidenceBundleFact] = []
        all_warnings: list[str] = []
        all_evidence_refs: list[str] = []
        seen_refs: set[str] = set()
        all_source_reports: list[str] = []
        seen_source_reports: set[str] = set()

        # Optional caller-supplied warnings (always preserved).
        if warnings is not None:
            for warn in warnings:
                if warn is None:
                    continue
                text = str(warn).strip()
                if text:
                    all_warnings.append(text)

        # Optional caller-supplied source-reports list (always
        # de-duplicated, deterministic order).
        if source_reports is not None:
            for report in source_reports:
                if report is None:
                    continue
                text = str(report).strip()
                if text and text not in seen_source_reports:
                    seen_source_reports.add(text)
                    all_source_reports.append(text)

        # ------------------------------------------------------------------
        # 2. Walk each fact group
        # ------------------------------------------------------------------
        groups: tuple[
            tuple[
                str,
                Iterable[AIEvidenceBundleFactInput | Mapping[str, Any]] | None,
            ],
            ...,
        ] = (
            ("market_facts", market_facts),
            ("system_behavior_facts", system_behavior_facts),
            ("outcome_facts", outcome_facts),
            ("replay_facts", replay_facts),
            ("reflection_facts", reflection_facts),
            ("evidence_contract_facts", evidence_contract_facts),
        )

        for group_name, raw_iter in groups:
            if raw_iter is None:
                continue
            for index, raw_fact in enumerate(raw_iter):
                fact_input = _coerce_fact_input(
                    raw_fact, fact_index=index, group=group_name
                )

                # Defensive: scan fact content for forbidden input
                # keys. The AI Layer NEVER reads previous AI
                # answers / chat history / private account state
                # via any indirect path.
                _scan_for_forbidden_input(
                    fact_input.content,
                    context=f"{group_name}[{fact_input.fact_id}].content",
                )

                # Refuse to admit any forbidden output field even
                # at intake. This guards against a caller
                # smuggling a ``buy`` / ``leverage`` /
                # ``runtime_config_patch`` key into the bundle
                # via the ``content`` payload.
                _assert_no_forbidden_fields(
                    fact_input.content,
                    context=(
                        f"{group_name}[{fact_input.fact_id}].content"
                    ),
                )

                evidence_refs = fact_input.evidence_refs

                if not evidence_refs:
                    # Degraded: no evidence_refs -> NEVER accepted
                    # as fact. Surface as a warning AND a degraded
                    # fact record so downstream callers can audit.
                    degraded_fact = AIEvidenceBundleFact(
                        fact_id=fact_input.fact_id,
                        fact_type=fact_input.fact_type,
                        content=dict(fact_input.content),
                        evidence_refs=(),
                        source_report=fact_input.source_report,
                        status=_FactStatus.DEGRADED_NO_EVIDENCE.value,
                        degradation_reason="no_evidence_refs_supplied",
                    )
                    all_degraded.append(degraded_fact)
                    all_warnings.append(
                        f"degraded:{group_name}:"
                        f"{fact_input.fact_id}:no_evidence_refs_supplied"
                    )
                    continue

                accepted_fact = AIEvidenceBundleFact(
                    fact_id=fact_input.fact_id,
                    fact_type=fact_input.fact_type,
                    content=dict(fact_input.content),
                    evidence_refs=evidence_refs,
                    source_report=fact_input.source_report,
                    status=_FactStatus.ACCEPTED.value,
                    degradation_reason=None,
                )
                accepted_groups[group_name].append(accepted_fact)

                for ref in evidence_refs:
                    if ref not in seen_refs:
                        seen_refs.add(ref)
                        all_evidence_refs.append(ref)

                if (
                    fact_input.source_report is not None
                    and fact_input.source_report not in seen_source_reports
                ):
                    seen_source_reports.add(fact_input.source_report)
                    all_source_reports.append(fact_input.source_report)

        accepted_fact_count = sum(
            len(group) for group in accepted_groups.values()
        )
        degraded_fact_count = len(all_degraded)

        if accepted_fact_count == 0 and degraded_fact_count == 0:
            build_status = (
                AIEvidenceBundleBuildStatus.EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE
            )
            all_warnings.append("no_facts_supplied")
        elif accepted_fact_count == 0 and degraded_fact_count > 0:
            build_status = (
                AIEvidenceBundleBuildStatus.EVIDENCE_BUNDLE_DEGRADED
            )
        elif degraded_fact_count > 0:
            build_status = (
                AIEvidenceBundleBuildStatus.EVIDENCE_BUNDLE_DEGRADED
            )
        else:
            build_status = AIEvidenceBundleBuildStatus.EVIDENCE_BUNDLE_BUILT

        # ------------------------------------------------------------------
        # 3. Pinned blocks
        # ------------------------------------------------------------------
        forbidden_fields_tuple = tuple(sorted(FORBIDDEN_AI_OUTPUT_FIELDS))
        lookahead_policy_map = {
            flag: True for flag in LOOKAHEAD_POLICY_FLAGS
        }
        consumer_contract_map: Mapping[str, Any] = {
            "allowed_consumers": list(ALLOWED_CONSUMERS),
            "forbidden_consumers": list(FORBIDDEN_CONSUMERS),
            "ai_output_is_commentary_only": True,
            "ai_output_can_be_training_label": False,
            "no_trade_authority": True,
            "no_runtime_config_patch_authority": True,
        }

        bundle = AIEvidenceBundle(
            bundle_id=bundle_id_str,
            created_at_utc=created_at_utc_str,
            task_type=task_type_enum,
            phase_context=phase_context_map,
            reference_window=reference_window_str,
            market_facts=tuple(accepted_groups["market_facts"]),
            system_behavior_facts=tuple(
                accepted_groups["system_behavior_facts"]
            ),
            outcome_facts=tuple(accepted_groups["outcome_facts"]),
            replay_facts=tuple(accepted_groups["replay_facts"]),
            reflection_facts=tuple(accepted_groups["reflection_facts"]),
            evidence_contract_facts=tuple(
                accepted_groups["evidence_contract_facts"]
            ),
            degraded_facts=tuple(all_degraded),
            evidence_refs=tuple(all_evidence_refs),
            source_reports=tuple(all_source_reports),
            forbidden_fields=forbidden_fields_tuple,
            lookahead_policy=lookahead_policy_map,
            consumer_contract=consumer_contract_map,
            warnings=tuple(all_warnings),
            build_status=build_status,
            accepted_fact_count=accepted_fact_count,
            degraded_fact_count=degraded_fact_count,
            source_phase=self._source_phase,
        )

        # Final defensive sweep on the serialised payload.
        _assert_no_forbidden_fields(
            bundle.to_dict(),
            context="AIEvidenceBundleBuilder.build.final_payload",
        )
        return bundle


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------
def build_ai_evidence_bundle(
    *,
    bundle_id: str,
    created_at_utc: str,
    task_type: AIEvidenceBundleTaskType | str,
    phase_context: Mapping[str, Any] | None = None,
    reference_window: str | None = None,
    market_facts: Iterable[
        AIEvidenceBundleFactInput | Mapping[str, Any]
    ]
    | None = None,
    system_behavior_facts: Iterable[
        AIEvidenceBundleFactInput | Mapping[str, Any]
    ]
    | None = None,
    outcome_facts: Iterable[
        AIEvidenceBundleFactInput | Mapping[str, Any]
    ]
    | None = None,
    replay_facts: Iterable[
        AIEvidenceBundleFactInput | Mapping[str, Any]
    ]
    | None = None,
    reflection_facts: Iterable[
        AIEvidenceBundleFactInput | Mapping[str, Any]
    ]
    | None = None,
    evidence_contract_facts: Iterable[
        AIEvidenceBundleFactInput | Mapping[str, Any]
    ]
    | None = None,
    source_reports: Iterable[str] | None = None,
    warnings: Iterable[str] | None = None,
) -> AIEvidenceBundle:
    """Build an :class:`AIEvidenceBundle` with a default
    :class:`AIEvidenceBundleBuilder`.

    Equivalent to
    ``AIEvidenceBundleBuilder().build(...)``; provided for
    callers that do not need to customise the builder's
    source-phase label.
    """

    return AIEvidenceBundleBuilder().build(
        bundle_id=bundle_id,
        created_at_utc=created_at_utc,
        task_type=task_type,
        phase_context=phase_context,
        reference_window=reference_window,
        market_facts=market_facts,
        system_behavior_facts=system_behavior_facts,
        outcome_facts=outcome_facts,
        replay_facts=replay_facts,
        reflection_facts=reflection_facts,
        evidence_contract_facts=evidence_contract_facts,
        source_reports=source_reports,
        warnings=warnings,
    )


__all__ = [
    "AI_EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "AI_EVIDENCE_BUNDLE_SOURCE_MODULE",
    "AI_EVIDENCE_BUNDLE_SOURCE_PHASE",
    "ALLOWED_CONSUMERS",
    "CREDENTIAL_LIKE_KEY_TOKENS",
    "FORBIDDEN_AI_OUTPUT_FIELDS",
    "FORBIDDEN_CONSUMERS",
    "FORBIDDEN_INPUT_KEYS",
    "LOOKAHEAD_POLICY_FLAGS",
    "AIEvidenceBundle",
    "AIEvidenceBundleBuilder",
    "AIEvidenceBundleBuildStatus",
    "AIEvidenceBundleFact",
    "AIEvidenceBundleFactInput",
    "AIEvidenceBundleTaskType",
    "ForbiddenAIInputError",
    "build_ai_evidence_bundle",
]
