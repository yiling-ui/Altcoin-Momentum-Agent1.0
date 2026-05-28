# Phase AI-6 - AI Replay / Reflection Integration v0

> **Status:** Paper / report / sandbox-only. **No runtime
> trading effect.** This phase ships the AI Layer's **first
> audit integration** runtime artefact - the AI Replay /
> Reflection Integration v0 - but it is read-only commentary
> substrate, the integration is never consumed by Risk /
> Execution / Strategy / Config / Telegram, and no member of
> :class:`AIReflectionTag` grants trade authority.
> **It does NOT call DeepSeek live. It does NOT authorise
> live trading. It does NOT authorise auto-tuning. It does
> NOT enter Phase 12. It does NOT publish to real Telegram.
> It does NOT make AI text become Truth Layer fact, training
> label, tail label, or strategy validation sample.**

## 1. Purpose

Phase AI-1 built the AI Evidence Bundle - the AI Layer's only
allowed *read* surface. Phase AI-2 built the AI Evidence
Citation Contract - the claim-level rule that every AI claim
MUST cite Truth-Layer evidence via ``evidence_refs``. Phase
AI-3 built the deterministic / statistical Reality Check
Layer - the cross-verifier that demotes / rejects claims that
contradict the bundle's frozen facts or smuggle unverifiable
narrative. Phase AI-4 shipped the DeepSeek Offline Sandbox
runner that emits one schema-checked
:class:`AIIntelligenceOutput`. Phase AI-5 closed the human
loop with the :class:`OperatorBriefing` and
:class:`EvidenceCompressionReport` artefacts. Phase AI-6
closes the **audit loop**:

  - The Phase AI-1 :class:`AIEvidenceBundle`, the Phase AI-4
    :class:`AIIntelligenceOutput`, the Phase AI-5
    :class:`OperatorBriefing`, and the Phase AI-5
    :class:`EvidenceCompressionReport` are projected into
    structural :class:`AIReplayCase` value objects so a
    downstream auditor can walk the AI Layer's commentary
    substrate, count its supported / unsupported /
    contradicted / degraded claims, pin its
    ``evidence_refs`` provenance, and confirm that no AI
    text leaked into Risk / Execution / Strategy / Config
    surfaces.
  - The replay cases are then reflected through the closed
    :class:`AIReflectionTag` vocabulary into deterministic
    :class:`AIReflectionCase` records - one tag per
    structural anomaly the auditor needs to surface
    (``ai_unsupported_claim`` / ``ai_contradicted_by_truth_layer``
    / ``ai_reality_check_failed`` / ``ai_evidence_missing`` /
    ``ai_forbidden_field_stripped`` /
    ``ai_narrative_pollution_risk`` /
    ``ai_degraded_output`` / ``ai_helpful_explanation`` /
    ``ai_operator_briefing_generated`` /
    ``ai_evidence_compression_generated``).
  - Both replay and reflection artefacts are paper /
    report / sandbox-only. They NEVER feed Risk / Execution
    / Strategy / Config / Telegram surfaces. They NEVER
    produce direction, sizing, leverage, stop, target,
    risk-budget, or any runtime-config-patch field.
  - The integration is **disabled-by-default** in the
    project sense: it is never wired into the runtime hot
    path; it is invoked only by offline auditors against
    pre-existing Phase AI-1 / AI-4 / AI-5 JSON artefacts.

Phase AI-6 is the AI Layer's *audit substrate* over its own
commentary output. It is **NOT** the DeepSeek hot path. It is
**NOT** Operator Briefing live publishing (real Telegram
outbound is gated by Spec §41). It is **NOT** auto-tuning. It
is **NOT** Phase 12.

## 2. Relation to ``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md``

The AI Layer Engineering Spec is the constitution. Phase
AI-6 is its sixth runtime artefact (after Phase AI-1's
Evidence Bundle Builder, Phase AI-2's Evidence Citation
Contract, Phase AI-3's Reality Check Layer, Phase AI-4's
DeepSeek Offline Sandbox, and Phase AI-5's Operator
Briefing / Evidence Compression):

  - Spec §1.1 *Responsibility Isolation* is enforced by
    re-using the Phase AI-1 recursive
    ``_assert_no_forbidden_fields`` guard at every
    ``to_dict()`` boundary on every Phase AI-6 dataclass
    (:class:`AIReplayCase`, :class:`AIReplaySummary`,
    :class:`AIReflectionCase`, :class:`AIReflectionSummary`).
    The guard refuses to emit any payload carrying
    ``buy`` / ``sell`` / ``long`` / ``short`` /
    ``direction`` / ``side`` / ``entry`` / ``exit`` /
    ``position_size`` / ``leverage`` / ``stop`` /
    ``stop_loss`` / ``target`` / ``take_profit`` /
    ``risk_budget`` / ``order`` / ``execution_command`` /
    ``runtime_config_patch`` / ``symbol_limit_patch`` /
    ``threshold_patch`` / ``candidate_pool_patch`` /
    ``regime_weight_patch`` / ``strategy_parameter_patch``.
  - Spec §1.2 *Stateless Inference* is enforced by the
    builder. Each :meth:`AIReplayBuilder.replay_artefact`
    call is independent; each
    :meth:`AIReplayReflectionEngine.reflect_replay_case`
    call is independent. The engine carries no instance
    state; it never reads previous AI answers, chat
    history, ``listenKey`` payloads, signed-endpoint
    payloads, or any private exchange / account state.
  - Spec §1.3 *Hard Rule Anchoring* is enforced by the
    reflection tag derivation. A replay case whose
    ``evidence_refs`` are empty AND whose ``claim_count``
    is non-zero is tagged ``ai_evidence_missing``. A replay
    case whose Reality Check histogram contains
    ``CONTRADICTED`` / ``REJECTED_LOOKAHEAD`` /
    ``REJECTED_UNVERIFIABLE_NARRATIVE`` /
    ``INSUFFICIENT_EVIDENCE`` entries is tagged
    ``ai_reality_check_failed``. A replay case whose
    ``forbidden_fields_stripped`` list is non-empty is
    tagged ``ai_forbidden_field_stripped`` (defence in
    depth: any forbidden trade-action /
    runtime-config-patch field that *was* stripped at the
    AI-4 / AI-5 boundary is preserved as audit evidence
    here).
  - Spec §1.4 *Feedback Isolation* is enforced by hard-
    pinning ``ai_output_can_be_truth=False`` /
    ``ai_output_can_be_training_label=False`` /
    ``ai_output_can_be_tail_label=False`` /
    ``ai_output_can_be_strategy_sample=False`` at every
    ``to_dict()`` boundary - even if a downstream caller
    flips the dataclass field via ``object.__setattr__``,
    the serialiser re-emits the safe values.

The artefact additionally pins the project-wide invariants:
``mode=paper``, ``live_trading=False``,
``exchange_live_orders=False``, ``right_tail=False``,
``llm=False``, ``llm_outbound_enabled=False``,
``sandbox_only=True``, ``telegram_outbound_enabled=False``,
``binance_private_api_enabled=False``.

## 3. Replay contract for AI outputs

Each Phase AI-1 / AI-4 / AI-5 JSON artefact is projected
into one :class:`AIReplayCase` carrying the following
fields:

  - ``case_id``: deterministic identifier for the replay
    case;
  - ``bundle_id``: the source Phase AI-1 bundle's
    ``bundle_id``;
  - ``ai_output_id``: a stable identifier for the AI
    artefact under replay (Phase AI-5's ``briefing_id`` /
    ``report_id`` when present, otherwise a deterministic
    fallback);
  - ``task_type``: the AI task type pinned in the source
    artefact (``OPERATOR_BRIEFING_DRAFT`` /
    ``EVIDENCE_COMPRESSION`` / ``MARKET_INTELLIGENCE_SUMMARY``
    / ...);
  - ``source_kind``: one of
    :class:`AIReplaySourceKind.EVIDENCE_BUNDLE` /
    :class:`AIReplaySourceKind.AI_INTELLIGENCE_OUTPUT` /
    :class:`AIReplaySourceKind.OPERATOR_BRIEFING` /
    :class:`AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT`;
  - ``source_report_paths``: the source artefact's report
    paths (Phase AI-5 carries this verbatim);
  - ``claim_count`` / ``supported_claim_count`` /
    ``unsupported_claim_count`` /
    ``contradicted_claim_count`` /
    ``degraded_claim_count`` /
    ``rejected_claim_count``: deterministic counts derived
    from the artefact's per-claim classification;
  - ``reality_check_status_summary``: histogram of
    ``reality_check_status`` values across claims;
  - ``evidence_refs``: every cited evidence_ref preserved
    verbatim (no fabrication);
  - ``forbidden_fields_stripped``: the list of forbidden
    trade-action / runtime-config-patch fields the AI-4 /
    AI-5 boundary already stripped; preserved here so the
    auditor can confirm the strip happened;
  - ``redacted_secret_count``: the count of credential-
    shaped keys redacted at the AI-4 boundary;
  - ``risk_tags`` / ``notable_symbols`` / ``warnings`` /
    ``degraded_reasons``: descriptive labels preserved
    verbatim;
  - ``trade_authority=False``,
    ``auto_tuning_allowed=False``,
    ``phase_12_forbidden=True``,
    ``ai_output_is_commentary_only=True``,
    ``ai_output_can_be_truth=False``,
    ``ai_output_can_be_training_label=False``,
    ``ai_output_can_be_tail_label=False``,
    ``ai_output_can_be_strategy_sample=False``: hard-pinned
    flags re-emitted at every ``to_dict()`` boundary.

The :class:`AIReplaySummary` aggregates many cases into one
deterministic summary with the brief-mandated counts:
``total_cases`` / ``operator_briefing_count`` /
``evidence_compression_count`` /
``unsupported_claim_count`` / ``contradicted_claim_count``
/ ``reality_check_failed_count`` /
``missing_evidence_count`` /
``forbidden_field_stripped_count``, plus the union of every
case's ``evidence_refs`` and ``warnings``.

## 4. Reflection contract for AI outputs

Each :class:`AIReplayCase` is reflected into one
:class:`AIReflectionCase` carrying:

  - ``case_id`` / ``bundle_id`` / ``ai_output_id`` /
    ``source_kind``: identity propagated from the replay
    case;
  - ``tags``: a sorted tuple of :class:`AIReflectionTag`
    string values drawn from the closed allow-list;
  - ``severity``: one of ``info`` / ``low`` / ``medium`` /
    ``high`` / ``unknown`` (closed
    :class:`AIReflectionSeverity` vocabulary);
  - ``evidence_refs``: preserved verbatim from the replay
    case;
  - ``needs_operator_review``: actionable boolean (``True``
    when any of ``ai_reality_check_failed`` /
    ``ai_contradicted_by_truth_layer`` /
    ``ai_unsupported_claim`` /
    ``ai_forbidden_field_stripped`` /
    ``ai_narrative_pollution_risk`` /
    ``ai_evidence_missing`` is attached);
  - ``warnings``: preserved verbatim plus internal
    deterministic strings (no natural-language
    hallucination);
  - ``trade_authority=False``,
    ``auto_tuning_allowed=False``,
    ``phase_12_forbidden=True``,
    ``ai_output_is_commentary_only=True``,
    ``ai_output_can_be_truth=False``,
    ``ai_output_can_be_training_label=False``,
    ``ai_output_can_be_tail_label=False``,
    ``ai_output_can_be_strategy_sample=False``: hard-pinned
    flags re-emitted at every ``to_dict()`` boundary.

## 5. Allowed reflection tags

Closed allow-list - the engine MUST NEVER emit a tag outside
this set. The list is pinned in code as the
:class:`AIReflectionTag` enum.

  - ``ai_helpful_explanation`` - the AI artefact carried
    at least one supported claim and no critical anomaly.
    Informational only; never authority-granting.
  - ``ai_unsupported_claim`` - the AI artefact carried at
    least one claim listed in the union view of
    ``unsupported_claims`` (Phase AI-5 compression
    semantics).
  - ``ai_contradicted_by_truth_layer`` - the AI artefact
    carried at least one claim flagged
    ``CONTRADICTED`` by the Phase AI-3 Reality Check
    Layer.
  - ``ai_reality_check_failed`` - the AI artefact's
    Reality Check histogram contains
    ``CONTRADICTED`` / ``REJECTED_LOOKAHEAD`` /
    ``REJECTED_UNVERIFIABLE_NARRATIVE`` /
    ``INSUFFICIENT_EVIDENCE``.
  - ``ai_evidence_missing`` - the AI artefact has
    ``degraded_claim_count > 0`` OR has claims with no
    ``evidence_refs`` at all.
  - ``ai_narrative_pollution_risk`` - the AI artefact's
    Reality Check rejected an unverifiable-narrative
    claim, OR its warnings / degraded_reasons mention
    one of the closed narrative-pollution tokens
    (``narrative`` / ``unverifiable`` / ``smart_money`` /
    ``main force`` / ``whale*`` / ``definitely`` /
    ``guaranteed`` / ``obviously``).
  - ``ai_forbidden_field_stripped`` - the AI artefact's
    ``forbidden_fields_stripped`` list is non-empty,
    i.e. the AI-4 / AI-5 boundary already stripped a
    forbidden trade-action / runtime-config-patch field.
    The tag preserves the audit trail.
  - ``ai_degraded_output`` - the AI artefact carries one
    or more ``degraded_reasons``.
  - ``ai_operator_briefing_generated`` - the AI artefact
    is a Phase AI-5 :class:`OperatorBriefing`.
    Informational only.
  - ``ai_evidence_compression_generated`` - the AI artefact
    is a Phase AI-5 :class:`EvidenceCompressionReport`.
    Informational only.

## 6. Forbidden reflection tags

Closed forbid-list - the engine MUST NEVER emit any of these
strings. The :class:`AIReflectionTag` enum intentionally
**omits** them; they are exposed as the
:data:`FORBIDDEN_REFLECTION_TAGS` frozenset for downstream
audit.

  - ``ai_said_buy``
  - ``ai_said_long``
  - ``ai_target_hit``
  - ``ai_direction_correct``
  - ``ai_trade_signal_correct``

These tags are forbidden because they would imply the AI
text is itself a *direction call*, a *trade signal*, or a
*post-hoc verdict on direction correctness*. AMA-RT's AI
Layer is observer + commentary only; the Risk Engine
remains the single trade-decision gate.

## 7. AI output is commentary, not truth

  - AI output is **commentary substrate**.
  - AI output is **never** a Truth Layer fact.
  - AI output is **never** a training label.
  - AI output is **never** a tail label.
  - AI output is **never** a strategy validation sample.

These four guarantees are pinned on every
:class:`AIReplayCase` and every :class:`AIReflectionCase`
via:

  - ``ai_output_is_commentary_only=True``;
  - ``ai_output_can_be_truth=False``;
  - ``ai_output_can_be_training_label=False``;
  - ``ai_output_can_be_tail_label=False``;
  - ``ai_output_can_be_strategy_sample=False``.

The :meth:`to_dict` boundary re-pins the safe values even if
a downstream caller flips the dataclass field via
``object.__setattr__``.

## 8. No Risk / Execution / Strategy / Config consumer

Neither :mod:`app.replay.ai_replay` nor
:mod:`app.reflection.ai_reflection` imports
:mod:`app.risk` / :mod:`app.execution` /
:mod:`app.exchanges` / :mod:`app.telegram` /
:mod:`app.config`. The test suite asserts this *both* via
AST-checked import lists *and* via a string scan that
ensures Risk / Execution / Exchanges / Telegram / Config
packages do NOT reference Phase AI-6 modules either.

Neither module imports any network library
(``openai`` / ``anthropic`` / ``deepseek`` / ``httpx`` /
``requests`` / ``aiohttp`` / ``urllib3`` / ``websocket`` /
``websockets`` / ``grpc`` / ``boto3`` / ``socket``). The
modules contain no live-call shape (no
``DeepSeekClient(...)`` / ``openai.ChatCompletion`` /
``call_deepseek(...)`` / ``requests.get(...)`` /
``httpx.post(...)`` / ``aiohttp.ClientSession(...)`` /
``websocket.create_connection(...)`` /
``telegram.Bot(...)`` / ``TelegramClient(...)``). The test
suite asserts this via string scan.

## 9. No Telegram live outbound

Phase AI-6 does NOT publish to Telegram. The replay /
reflection artefacts are read-only commentary substrate; an
operator can read them via the existing Phase 8.5 export
bundles, never via real Telegram outbound. Real Telegram
outbound is gated by Spec §41 and remains forbidden.

## 10. No trading authority

The maximum any :class:`AIReplayCase` /
:class:`AIReflectionCase` / :class:`AIReplaySummary` /
:class:`AIReflectionSummary` reaches is **commentary
substrate**. There is no member of any Phase AI-6 enum or
dataclass that grants trade authority. The Risk Engine
remains the single trade-decision gate.

## 11. No auto-tuning

Every Phase AI-6 dataclass hard-pins
``auto_tuning_allowed=False`` at every ``to_dict()``
boundary. The recursive ``_assert_no_forbidden_fields`` guard
refuses to emit any payload carrying a ``*_patch`` key.
Phase AI-6 does NOT change ``symbol_limit``, anomaly
thresholds, candidate-pool capacity, Regime weights, or any
other runtime knob.

## 12. No Phase 12

Every Phase AI-6 dataclass hard-pins
``phase_12_forbidden=True`` at every ``to_dict()`` boundary.
**Phase 12 remains FORBIDDEN.** A successful Phase AI-6
acceptance only allows the AI Layer's own audit substrate to
be reviewed; it does NOT authorise live trading, does NOT
authorise the real DeepSeek HTTP transport, does NOT
authorise auto-tuning, does NOT open Phase 12.

## 13. Successful AI-6 only allows AI integrated checkpoint

A successful Phase AI-6 acceptance only allows the project
to advance to a later, separately gated **AI Integrated
Checkpoint** that aggregates Phase AI-1 / AI-2 / AI-3 / AI-4
/ AI-5 / AI-6 outputs into one offline audit report. It does
NOT allow the project to advance to Phase 12. It does NOT
enable the real DeepSeek HTTP transport. It does NOT enable
real Telegram outbound. It does NOT change any runtime
configuration knob. The Risk Engine remains the single
trade-decision gate.

## 14. Safety boundary (held end-to-end)

  - ``mode = paper``
  - ``live_trading = False``
  - ``exchange_live_orders = False``
  - ``right_tail = False``
  - ``llm = False``
  - ``llm_outbound_enabled = False`` (default; sandbox-only
    operator runs may set it ``True`` for the AI-4
    skeleton, but Phase AI-6 itself never opens any
    network)
  - ``sandbox_only = True``
  - ``allow_trade_decision = False``
  - ``allow_runtime_config_change = False``
  - ``require_evidence_refs = True``
  - ``require_reality_check = True``
  - ``stateless_inference = True``
  - ``feedback_isolation = True``
  - ``telegram_outbound_enabled = False``
  - ``binance_private_api_enabled = False``
  - no Binance API key / secret
  - no signed endpoint
  - no private WebSocket
  - no ``listenKey``
  - no real Telegram outbound
  - no DeepSeek trade decision
  - no real DeepSeek HTTP transport
  - **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

## 15. Tests

  - ``python -m pytest tests/unit/test_ai_replay_reflection_integration.py -q``
    PASS.
  - ``python -m pytest tests/unit -q`` PASS, no regression
    vs. the post-PR-#86 main baseline.

## 16. Phase status

**Phase AI-6 = IN_REVIEW after this implementation PR.**
Not ``ACCEPTED``. Not live ready. Not trade authority
granted. Not real DeepSeek HTTP transport. Not Operator
Briefing live publishing. Not Rule Sandbox. Not Paper
Shadow. Not auto-tuning. **Phase 12 = FORBIDDEN.**
