# Phase AI-5 - Operator Briefing / Evidence Compression v0

> **Status:** Paper / report / sandbox-only. **No runtime
> trading effect.** This phase ships the AI Layer's
> first **human-readable operator briefing** runtime
> artefact - but it is read-only commentary substrate, the
> briefing is never consumed by Risk / Execution / Strategy /
> Config / Telegram, and no member of
> `OperatorBriefingAuthorityLevel` grants trade authority.
> **It does NOT call DeepSeek live. It does NOT authorise
> live trading. It does NOT authorise auto-tuning. It does
> NOT enter Phase 12. It does NOT publish to real Telegram.**

## 1. Purpose

Phase AI-1 built the AI Evidence Bundle - the AI Layer's only
allowed *read* surface. Phase AI-2 built the AI Evidence
Citation Contract - the claim-level rule that every AI claim
MUST cite Truth-Layer evidence via `evidence_refs`. Phase
AI-3 built the deterministic / statistical Reality Check
Layer - the cross-verifier that demotes / rejects claims that
contradict the bundle's frozen facts or smuggle unverifiable
narrative. Phase AI-4 shipped the DeepSeek Offline Sandbox
runner that emits one schema-checked
:class:`AIIntelligenceOutput`. Phase AI-5 closes the **human
loop**:

  - The schema-checked AI intelligence output, the Phase
    AI-1 evidence bundle, and the Block C Integrated
    Checkpoint summary are *compressed* into a redacted,
    evidence-cited, claim-classified briefing an operator
    can read end-to-end.
  - Two artefacts are produced: a deterministic
    :class:`OperatorBriefing` (sectioned, operator-facing)
    and a deterministic :class:`EvidenceCompressionReport`
    (machine-readable, compression-only).
  - Both artefacts are paper / report / sandbox-only. They
    NEVER feed Risk / Execution / Strategy / Config /
    Telegram surfaces. They NEVER produce direction,
    sizing, leverage, stop, target, risk-budget, or any
    runtime-config-patch field.
  - The builder is **disabled-by-default** in the project
    sense: it is never wired into the runtime hot path; it
    is invoked only by the offline runner
    `scripts/run_ai_operator_briefing.py` against
    pre-existing JSON files.

Phase AI-5 is the AI Layer's *operator briefing draft* and
*evidence compression* substrate. It is **NOT** the DeepSeek
hot path. It is **NOT** Operator Briefing live publishing
(real Telegram outbound is gated by Spec §41). It is **NOT**
auto-tuning. It is **NOT** Phase 12.

## 2. Relation to `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`

The AI Layer Engineering Spec is the constitution. Phase
AI-5 is its fifth runtime artefact (after Phase AI-1's
Evidence Bundle Builder, Phase AI-2's Evidence Citation
Contract, Phase AI-3's Reality Check Layer, and Phase AI-4's
DeepSeek Offline Sandbox):

  - Spec §1.1 *Responsibility Isolation* is enforced by
    re-using the Phase AI-1 recursive
    `_assert_no_forbidden_fields` guard at every
    `to_dict()` boundary, plus the Phase AI-4
    `strip_forbidden_fields` helper that strips forbidden
    trade-action / runtime-config-patch fields from the AI
    output container and records every stripped path in
    `forbidden_fields_stripped`.
  - Spec §1.2 *Stateless Inference* is enforced by the
    builder. Each `OperatorBriefingBuilder.build(...)` call
    is independent; no instance state is mutated between
    calls; the builder never reads previous AI answers,
    chat history, `listenKey` payloads, signed-endpoint
    payloads, or any private exchange / account state.
  - Spec §1.3 *Hard Rule Anchoring* is enforced by routing
    every claim through the Phase AI-5
    `EvidenceCompressionReportBuilder.classify_claim`
    function. A claim that has no `evidence_refs` is
    classified as `DEGRADED_NO_EVIDENCE` and surfaced in
    the `UNSUPPORTED_CLAIMS` section (never in
    `key_findings`); a claim that the AI-3 Reality Check
    rejected (`REJECTED_LOOKAHEAD` /
    `REJECTED_UNVERIFIABLE_NARRATIVE`) is classified as
    `REJECTED` and surfaced in the same dedicated section;
    a claim that contradicts the bundle is classified as
    `CONTRADICTED` and surfaced in the `CONTRADICTIONS`
    section.
  - Spec §1.4 *Feedback Isolation* is enforced by the
    hard-pinned `trade_authority=False`,
    `auto_tuning_allowed=False`, `phase_12_forbidden=True`,
    `stateless_inference=True`, `feedback_isolation=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False` flags re-emitted
    at every `to_dict()` boundary.

Spec §2 *Allowed DeepSeek first-version outputs* is the
closed task-type vocabulary the underlying AI-4 sandbox
emits; Spec §3 *Forbidden DeepSeek outputs* is the recursive
stripping target. Phase AI-5 ADDS its own closed
:class:`OperatorBriefingSection` vocabulary (12 values) so
the operator briefing has a deterministic structure.

## 3. AI role - read-only cognition / evidence compression

The builder's role is *cognition*, not *control*. It:

  - reads the bundle's facts, the AI-4 output's claims, and
    the Block C report's status;
  - classifies every claim into the closed compression
    vocabulary (`SUPPORTED` / `UNSUPPORTED` /
    `DEGRADED_NO_EVIDENCE` / `REJECTED` / `CONTRADICTED` /
    `COMMENTARY_ONLY`);
  - groups claims into the closed
    :class:`OperatorBriefingSection` vocabulary;
  - surfaces data-gap signals from the bundle's facts;
  - surfaces Block C blockers as review-only operator
    action items;
  - emits commentary substrate, never a trade decision.

The Risk Engine remains the single trade-decision gate. The
Execution FSM remains independent of any AI / LLM signal.

## 4. Allowed inputs

  - One frozen Phase AI-1 :class:`AIEvidenceBundle` (handed
    in as a `Mapping`, typically the JSON view of
    `AIEvidenceBundle.to_dict()`).
  - One serialised Phase AI-4 :class:`AIIntelligenceOutput`
    (or any structurally compatible offline / fake
    intelligence payload). The runner accepts the JSON view
    of `AIIntelligenceOutput.to_dict()`.
  - An optional Block C Integrated Checkpoint report JSON
    (the JSON view of the
    `block_c_integrated_checkpoint_report.json` produced
    by `scripts/run_block_c_integrated_checkpoint.py`).
  - An optional reference-window string (default `60d`).
  - An optional briefing-id string.

## 5. Forbidden inputs

  - Any private exchange / account state (`account_balance`,
    `account_orders`, `account_positions`,
    `account_leverage`, `account_margin`, `wallet_balance`,
    `binance_account_state`, `listenKey`,
    `signed_endpoint_payload`).
  - Any chat history / previous AI answer
    (`previous_ai_answer`, `chat_history`,
    `conversation_history`, `assistant_history`,
    `previous_briefing`, `previous_summary`).
  - Any API secret / credential-shaped key (`api_key`,
    `api_secret`, `private_key`, `secret_key`,
    `bearer_token`, `auth_token`, `access_token`,
    `refresh_token`, `deepseek_api_key`,
    `binance_api_secret`, `telegram_bot_token`, plus
    `secret` / `secrets` / `token` bare names).
  - Live order state, live position state, live runtime
    config, live trade plan.

The Phase AI-5 builder relies on the underlying Phase AI-1
forbidden-input guard (the `_scan_for_forbidden_input`
helper). Any input that smuggles a forbidden / credential-
shaped key into a *bundle* mapping is rejected upstream by
the AI-1 builder; on the AI-5 side, the
`strip_forbidden_fields` helper plus the `redact_secrets`
helper run again as defence in depth and record every
stripped path / redacted count in the briefing's audit
trail.

## 6. Allowed outputs

The Phase AI-5 builder produces TWO artefacts:

### 6.1 :class:`OperatorBriefing`

  - `briefing_id` - deterministic identifier supplied by
    the caller.
  - `created_at_utc` - ISO-8601 timestamp supplied by the
    caller.
  - `reference_window` - reference window label (default
    `60d`).
  - `source_bundle_id`, `source_ai_output_id`,
    `source_block_c_status` - upstream artefact identifiers.
  - `source_report_paths` - list of file references the
    runner consumed.
  - `sections` - a list of
    :class:`OperatorBriefingSectionRecord` objects, one for
    each member of :class:`OperatorBriefingSection`. Order
    is the enum declaration order; findings inside a
    section are sorted by `finding_id`.
  - `key_findings` - claim ids that were classified as
    `SUPPORTED` after Phase AI-2 + AI-3. **Unsupported /
    degraded / rejected / contradicted claim ids NEVER
    appear here.**
  - `unsupported_claims` - claim ids classified as
    `UNSUPPORTED` / `DEGRADED_NO_EVIDENCE` / `REJECTED` /
    `CONTRADICTED` (each is also surfaced in the matching
    section).
  - `contradictions` - claim ids classified as
    `CONTRADICTED`.
  - `data_gaps` - flat string list of data-gap signals
    surfaced from the bundle's market / system-behavior /
    outcome facts.
  - `operator_review_items` - review-only operator action
    items (review-shaped strings only, e.g.
    `review_unsupported_claim:claim-1`,
    `block_c_blocker:replay_blocker_a`). Each item is also
    surfaced as an `OperatorBriefingFinding` in the
    `OPERATOR_ACTION_ITEMS` section with `review_only=True`
    pinned.
  - `evidence_refs` - deduplicated union of every claim's
    `evidence_refs` plus the AI-4 output's top-level
    `evidence_refs`.
  - `notable_symbols` - the `symbol:<SYMBOL>` references
    extracted (in input order) from the deduplicated
    `evidence_refs`.
  - `risk_tags` - descriptive risk tags from the AI-4
    output (`breadth_weak`, `late_chase_high`,
    `funding_overheated`; **never** trade actions).
  - `authority_level` - one of
    :class:`OperatorBriefingAuthorityLevel`
    (`COMMENTARY_SUBSTRATE` / `DEGRADED_PARTIAL_EVIDENCE` /
    `DEGRADED_NO_EVIDENCE` / `REJECTED`). **No member
    grants trade authority.**
  - `forbidden_fields_stripped` - audit trail of every
    forbidden trade-action / runtime-config-patch field
    stripped from the input AI output.
  - `redacted_secret_count` - defensive count of
    credential-shaped keys redacted from the input AI
    output.
  - `warnings` - audit trail (carries warnings from the
    bundle, the AI output, the compression report, and the
    briefing builder).
  - `consumer_contract` - re-emitted closed
    `allowed_consumers` / `forbidden_consumers` /
    `lookahead_policy_flags` lists.
  - `safety_flags` block re-emitted on every `to_dict()`:
    `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `llm_outbound_enabled=False`,
    `sandbox_only=True`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`.
  - Hard-pinned root-constraint flags re-emitted on every
    `to_dict()`: `trade_authority=False`,
    `auto_tuning_allowed=False`,
    `phase_12_forbidden=True`,
    `stateless_inference=True`,
    `feedback_isolation=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`.

### 6.2 :class:`EvidenceCompressionReport`

  - `report_id`, `created_at_utc`, `reference_window`,
    `source_bundle_id`, `source_ai_output_id` -
    deterministic identifiers.
  - `summary` - free-form commentary string (deterministic
    operator-readable header followed by the AI-4 output's
    summary verbatim).
  - `compressed_claims` - list of
    :class:`CompressedClaim` objects, one per AI-4 claim.
    Each carries `claim_id`, `claim_type`, `claim_text`
    (preserved verbatim), `evidence_refs`,
    `truth_layer_fields_used`, `citation_authority_level`,
    `reality_check_status`, `reality_check_authority_level`,
    `classification`, `confidence_raw`,
    `confidence_reality_checked`, `warnings`.
  - `supported_claims`, `degraded_claims`,
    `rejected_claims`, `contradictions`,
    `unsupported_claims` - claim id buckets.
  - `reality_check_summary` - claim-classification counts.
  - `evidence_quality_summary` - bundle build status, AI
    output status, forbidden-fields-stripped audit trail.
  - `data_gap_summary` - flagged data-gap signals plus
    bundle-level `degraded_fact_count`.
  - `notable_symbols`, `risk_tags`, `evidence_refs` -
    same semantics as the briefing.
  - `forbidden_fields_stripped`, `redacted_secret_count`,
    `warnings` - audit trail.
  - Hard-pinned root-constraint flags + safety flags as
    per the briefing.

## 7. Forbidden outputs

A briefing / compression-report output MUST NOT carry any of
the following fields at any nesting depth (recursive
`_assert_no_forbidden_fields` guard imported from
`app.ai.evidence_bundle`, re-exported as
`FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS`):

  - Direction / trade-decision: `buy`, `sell`, `long`,
    `short`, `direction`, `side`, `entry`, `exit`.
  - Sizing / leverage / risk-budget: `position_size`,
    `leverage`, `stop`, `stop_loss`, `stop_price`, `target`,
    `target_price`, `take_profit`, `risk_budget`, `order`,
    `order_type`, `execution_command`.
  - Runtime-config patch: `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`,
    `strategy_parameter_patch`.
  - Signal-to-trade aliases: `signal_to_trade`, `should_buy`,
    `should_short`.
  - Defensive aliases: `trading_approved`, `live_ready`,
    `live_trading_allowed`.

If the input AI output smuggles any of these the builder:

  1. strips them via `strip_forbidden_fields`,
  2. records every stripped path in
     `forbidden_fields_stripped`,
  3. re-pins all root-constraint flags at the next
     `to_dict()` boundary.

## 8. Operator briefing sections

The closed :class:`OperatorBriefingSection` vocabulary
(declaration order is the rendered order):

| Enum | Title | Purpose |
| --- | --- | --- |
| `EXECUTIVE_SUMMARY` | Executive summary | Claim-count breakdown + Block C status |
| `MARKET_INTELLIGENCE` | Market intelligence | `REGIME` / `NARRATIVE` / `LIQUIDITY` claims |
| `DISCOVERY_QUALITY` | Discovery quality | `EVIDENCE_QUALITY` claims + Block C evidence-contract status |
| `COVERAGE_AUDIT` | Coverage audit interpretation | `COVERAGE` claims |
| `POST_DISCOVERY_OUTCOME` | Post-discovery outcome | `OUTCOME` claims |
| `REJECT_ATTRIBUTION` | Reject-to-outcome attribution | reject-to-outcome attribution claims |
| `SEVERE_MISS_TRIAGE` | Severe missed-tail triage | severe missed-tail triage claims |
| `REPLAY_REFLECTION` | Replay / reflection summary | `REPLAY_SUMMARY` / `REFLECTION_SUMMARY` claims + Block C replay / reflection statuses |
| `CONTRADICTIONS` | Contradictions | claims classified as `CONTRADICTED` |
| `UNSUPPORTED_CLAIMS` | Unsupported claims | claims classified as `UNSUPPORTED` / `DEGRADED_NO_EVIDENCE` / `REJECTED` |
| `DATA_GAPS` | Data gaps | flagged data-gap signals from the bundle |
| `OPERATOR_ACTION_ITEMS` | Operator review items (review-only) | review-only operator action items |

## 9. Evidence compression report schema

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `str` | Always `"v0"` in this phase. |
| `source_phase` | `str` | Always `"phase_ai_5"`. |
| `source_module` | `str` | Always `"ai_evidence_compression_report"`. |
| `report_id` | `str` | Deterministic identifier. |
| `created_at_utc` | `str` | ISO-8601 timestamp. |
| `reference_window` | `str` | Window label, default `"60d"`. |
| `source_bundle_id` | `str` | Phase AI-1 bundle id. |
| `source_ai_output_id` | `str` | Phase AI-4 output bundle id (mirrors `source_bundle_id` when absent). |
| `summary` | `str` | Deterministic header + AI-4 summary verbatim. |
| `compressed_claims` | `list[CompressedClaim]` | One entry per AI-4 claim. |
| `supported_claims` | `list[str]` | Claim ids classified `SUPPORTED`. |
| `degraded_claims` | `list[str]` | Claim ids classified `DEGRADED_NO_EVIDENCE`. |
| `rejected_claims` | `list[str]` | Claim ids classified `REJECTED` / `CONTRADICTED`. |
| `contradictions` | `list[str]` | Claim ids classified `CONTRADICTED`. |
| `unsupported_claims` | `list[str]` | Union of unsupported / degraded / rejected / contradicted. |
| `reality_check_summary` | `dict` | Claim-classification counts. |
| `evidence_quality_summary` | `dict` | Bundle / AI-output statuses + forbidden-fields-stripped audit. |
| `data_gap_summary` | `dict` | Flagged signals + bundle-level `degraded_fact_count`. |
| `notable_symbols` | `list[str]` | `symbol:<SYMBOL>` references. |
| `risk_tags` | `list[str]` | Descriptive risk tags only. |
| `evidence_refs` | `list[str]` | Deduplicated union. |
| `forbidden_fields_stripped` | `list[str]` | Audit trail. |
| `redacted_secret_count` | `int` | Redacted credential-shaped key count. |
| `warnings` | `list[str]` | Audit trail. |
| `safety_flags` | `dict` | Hard-pinned safety invariants. |
| `forbidden_fields` | `list[str]` | Reference list of forbidden field names. |
| `trade_authority` | `bool` | Hard-pinned `False`. |
| `auto_tuning_allowed` | `bool` | Hard-pinned `False`. |
| `phase_12_forbidden` | `bool` | Hard-pinned `True`. |
| `stateless_inference` | `bool` | Hard-pinned `True`. |
| `feedback_isolation` | `bool` | Hard-pinned `True`. |
| `ai_output_is_commentary_only` | `bool` | Hard-pinned `True`. |
| `ai_output_can_be_training_label` | `bool` | Hard-pinned `False`. |

## 10. Consumer contract

### 10.1 Allowed consumers

  - `human_operator`
  - `export_bundle`
  - `replay_annotation`
  - `reflection_annotation`
  - `operator_briefing_report`

The closed list is re-emitted in the briefing's
`consumer_contract.allowed_consumers` block on every
`to_dict()` boundary.

### 10.2 Forbidden consumers

  - `RiskEngine`
  - `ExecutionFSM`
  - `StrategyEngine`
  - `ExchangeGateway`
  - `RuntimeConfig`
  - `TelegramLiveCommand`
  - `CapitalFlow`
  - `PositionManager`

The closed list is re-emitted in the briefing's
`consumer_contract.forbidden_consumers` block on every
`to_dict()` boundary. The unit-test harness asserts on
every CI run that no file under `app/risk/`,
`app/execution/`, `app/exchanges/`, `app/telegram/`, or
`app/config/` imports `app.ai` (any submodule) via AST
inspection.

## 11. No Telegram live outbound

The Phase AI-5 modules (`app/ai/operator_briefing.py`,
`app/ai/evidence_compression.py`,
`scripts/run_ai_operator_briefing.py`) import nothing from
`app.telegram` (AST-checked); they import nothing from
`requests`, `httpx`, `aiohttp`, `urllib3`, `websocket`,
`websockets`, `grpc`, `boto3`, `socket` (AST-checked); the
source contains no `telegram.send(` /
`send_telegram_message(` / `post_to_chat_id(` /
`call_telegram(` shape (string-scanned).

The unit-test harness asserts these invariants on every CI
run.

## 12. No trading authority

  - No member of `OperatorBriefingAuthorityLevel` carries
    trade-action semantics.
  - The maximum any briefing can reach is
    `COMMENTARY_SUBSTRATE`, which is *commentary substrate*
    only.
  - `trade_authority=False` is hard-pinned at every
    `to_dict()` boundary.
  - `safety_flags.live_trading=False` is hard-pinned at
    every `to_dict()` boundary.
  - `safety_flags.exchange_live_orders=False` is hard-pinned
    at every `to_dict()` boundary.
  - The Risk Engine remains the single trade-decision gate.

## 13. No auto-tuning

  - `auto_tuning_allowed=False` is hard-pinned at every
    `to_dict()` boundary.
  - The recursive `_assert_no_forbidden_fields` guard
    refuses to emit any payload carrying a `*_patch` key
    (`runtime_config_patch`, `symbol_limit_patch`,
    `threshold_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, `strategy_parameter_patch`).
  - The builder never produces `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`, or any
    other knob that would touch the runtime.

## 14. No Phase 12

  - `phase_12_forbidden=True` is hard-pinned at every
    `to_dict()` boundary.
  - `safety_flags.binance_private_api_enabled=False` is
    hard-pinned at every `to_dict()` boundary.
  - `safety_flags.telegram_outbound_enabled=False` is
    hard-pinned at every `to_dict()` boundary.
  - The builder never reads or carries an API key, an API
    secret, a `listenKey`, or a signed-endpoint payload.

## 15. Successor allowed by this phase

Phase AI-5 unlocks ONLY the following later (separately
gated) work:

  - **Phase AI-6 - Replay / Reflection Integration of AI
    outputs** that consumes the Phase AI-5 operator
    briefing artefact and records it in the replay /
    reflection artefacts as an *annotation*. Still paper /
    report / sandbox-only.

It does **NOT** unlock:

  - DeepSeek trade decisions;
  - the AI Layer's involvement in the Risk Engine;
  - the AI Layer's involvement in the Execution FSM;
  - auto-tuning (`symbol_limit` / anomaly thresholds /
    candidate-pool capacity / Regime weights);
  - Operator Briefing live publishing (real Telegram
    outbound is gated by Spec §41);
  - the AI Layer's involvement in the runtime hot path;
  - the real DeepSeek HTTP transport (refusal-only skeleton
    only);
  - **Phase 12**.

## 16. Files shipped

  - `app/ai/operator_briefing.py` - the closed
    :class:`OperatorBriefingSection` enum,
    :class:`OperatorBriefingAuthorityLevel` enum,
    :class:`OperatorBriefingFinding`,
    :class:`OperatorBriefingSectionRecord`,
    :class:`OperatorBriefing` dataclasses, the
    :class:`OperatorBriefingBuilder`, and
    :func:`render_operator_briefing_markdown`.
  - `app/ai/evidence_compression.py` - the closed
    :class:`CompressedClaim` and
    :class:`EvidenceCompressionReport` dataclasses, the
    :class:`EvidenceCompressionReportBuilder`, the closed
    `CLAIM_CLASS_*` vocabulary, the
    :func:`classify_claim` helper, and
    :func:`render_evidence_compression_report_markdown`.
  - `app/ai/__init__.py` - extended re-exports for the
    Phase AI-5 public API alongside the Phase AI-1 + AI-2 +
    AI-3 + AI-4 surfaces.
  - `scripts/run_ai_operator_briefing.py` - the offline
    runner script. Reads the AI-1 bundle JSON, the AI-4
    sandbox output JSON, and an optional Block C report
    JSON; writes
    `<output-dir>/operator_briefing.json` /
    `<output-dir>/operator_briefing.md` and
    `<output-dir>/evidence_compression_report.json` /
    `<output-dir>/evidence_compression_report.md`.
  - `tests/unit/test_ai_operator_briefing.py` - 113 unit
    tests covering every brief-mandated scenario plus
    defensive companions.
  - `docs/PHASE_AI_5_OPERATOR_BRIEFING_EVIDENCE_COMPRESSION.md` -
    this document.

## 17. Tests

```
python -m pytest tests/unit/test_ai_operator_briefing.py -q
```

ships 113 PASS / 0 fail.

```
python -m pytest tests/unit -q
```

reports 3128 PASS / 0 fail (was 3015 before this phase;
+113 from this phase).

## 18. Phase status

**Phase AI-5 = IN_REVIEW** after this implementation PR.

  - **NOT** `ACCEPTED`.
  - **NOT** live ready.
  - **NOT** trade authority granted.
  - **NOT** real DeepSeek HTTP transport.
  - **NOT** Operator Briefing live publishing.
  - **NOT** Rule Sandbox.
  - **NOT** Paper Shadow.
  - **NOT** auto-tuning.
  - **Phase 12 = FORBIDDEN.**
