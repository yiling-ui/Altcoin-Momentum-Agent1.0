# Phase AI-1 - AI Evidence Bundle Builder v0

> **Status:** Paper / report / read-only. **No runtime effect.**
> This phase ships the AI Layer's only allowed read surface as a
> closed schema, a deterministic builder, a paranoid intake guard,
> and a unit-test harness. **It does NOT call DeepSeek. It does
> NOT call any LLM. It does NOT open any network socket. It does
> NOT authorise live trading. It does NOT authorise auto-tuning.
> Phase 12 remains FORBIDDEN.**

## 1. Purpose

Phase AI-1 builds the *AI Evidence Bundle*: a frozen,
evidence-cited, deterministic, JSON-serializable record that any
later AI / DeepSeek / LLM call MUST receive *as the only input*
and infer *only* from. Without this layer, a downstream AI
integration would be tempted to pull from `events.db`, the
runtime config, the Telegram channel, the Binance private API,
or its own previous answers - every one of which violates the
AI four root constraints in
`docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`.

Phase AI-1 makes the bundle the *only* read surface and refuses,
at the source level and at the test level, to expose anything
else.

## 2. Relation to `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`

The AI Layer Engineering Spec is the constitution. Phase AI-1 is
its first runtime artefact:

  - Spec §1.1 *Responsibility Isolation* is enforced by the
    bundle's `forbidden_fields` block (a sorted tuple of every
    trade-action / runtime-config-patch field name) and by the
    recursive `_assert_no_forbidden_fields` guard that refuses
    to emit any payload carrying such a key at any nesting
    depth.
  - Spec §1.2 *Stateless Inference* is enforced by the bundle
    builder's `_scan_for_forbidden_input` guard that rejects
    `previous_ai_answer` / `chat_history` /
    `private_account_state` / credential-shaped key names at
    any nesting depth in any input mapping.
  - Spec §1.3 *Hard Rule Anchoring* is enforced by demoting any
    fact without `evidence_refs` to `degraded_facts` and
    surfacing the demotion as a warning. Such facts NEVER
    appear in the accepted `*_facts` collections.
  - Spec §1.4 *Feedback Isolation* is enforced by the
    hard-pinned `ai_output_is_commentary_only=True` and
    `ai_output_can_be_training_label=False` flags re-emitted at
    every `to_dict()` boundary, even if a downstream caller
    flips the dataclass field.

## 3. AI role in AMA-RT trading workflow

AI in AMA-RT is the **read-only Market Cognition & Evidence
Compression Layer**:

  - AI is responsible for *market intelligence*, *evidence
    compression*, *contradiction discovery*, *replay /
    reflection summarisation*, *operator-briefing input*,
    *regime / narrative / catalyst explanation*, and
    *coverage / post-discovery / severe-miss interpretation*.
  - AI is **NOT** responsible for direction, position size,
    leverage, stop-loss, target / take-profit, risk budget,
    order, execution, runtime-config patch, auto-tuning, or
    live trading.

The bundle is therefore a *commentary substrate*, not a
trade-decision input. The Risk Engine remains the single
trade-decision gate.

## 4. Inputs

The builder is called as
`AIEvidenceBundleBuilder().build(...)` (or via the convenience
wrapper `build_ai_evidence_bundle(...)`) with:

  - `bundle_id` *(str, required)* - caller-supplied
    deterministic identifier.
  - `created_at_utc` *(str, required)* - caller-supplied UTC
    timestamp string. The AI Layer must NOT synthesize
    timestamps.
  - `task_type` *(`AIEvidenceBundleTaskType` or str, required)*.
  - `phase_context` *(Mapping, optional)* - read-only frozen
    metadata about the current phase.
  - `reference_window` *(str, optional)* - the audit window the
    bundle references (e.g. `"60d"`).
  - `market_facts`, `system_behavior_facts`, `outcome_facts`,
    `replay_facts`, `reflection_facts`,
    `evidence_contract_facts` *(Iterable of
    `AIEvidenceBundleFactInput` or Mapping, optional)* - the
    Truth-Layer-cited facts to compress.
  - `source_reports` *(Iterable[str], optional)* - report
    identifiers cited by the bundle.
  - `warnings` *(Iterable[str], optional)* - operator-supplied
    warnings preserved verbatim.

## 5. Outputs

`AIEvidenceBundleBuilder.build(...)` returns one
`AIEvidenceBundle`. The bundle is JSON-serializable via
`bundle.to_dict()`. The serialised payload contains, in fixed
key order:

  - `schema_version`, `source_phase`, `source_module`,
    `bundle_id`, `created_at_utc`, `task_type`, `build_status`.
  - `phase_context`, `reference_window`.
  - `market_facts`, `system_behavior_facts`, `outcome_facts`,
    `replay_facts`, `reflection_facts`,
    `evidence_contract_facts` (accepted facts only).
  - `degraded_facts` (facts without `evidence_refs`).
  - `evidence_refs` (deduplicated union, first-seen order).
  - `source_reports` (deduplicated, first-seen order).
  - `forbidden_fields` (sorted tuple).
  - `lookahead_policy` (boolean flag map).
  - `consumer_contract` (allowed / forbidden consumers +
    commentary-only / no-trade-authority pins).
  - `warnings`, `accepted_fact_count`, `degraded_fact_count`.
  - `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=True`, `auto_tuning_allowed=False`.
  - `safety_flags` (the project-wide invariants:
    `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`).

`build_status` is one of `EVIDENCE_BUNDLE_BUILT` /
`EVIDENCE_BUNDLE_DEGRADED` /
`EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE`.

## 6. Bundle schema (closed)

  - `AIEvidenceBundleTaskType`: closed enum with
    `OPERATOR_BRIEFING`, `MARKET_INTELLIGENCE_SUMMARY`,
    `COVERAGE_AUDIT_INTERPRETATION`,
    `POST_DISCOVERY_OUTCOME_SUMMARY`,
    `REJECT_TO_OUTCOME_SUMMARY`, `SEVERE_MISS_SUMMARY`,
    `REPLAY_REFLECTION_SUMMARY`, `EVIDENCE_COMPRESSION`,
    `CONTRADICTION_SUMMARY`, `EVIDENCE_QUALITY_ASSESSMENT`.
    Adding a new task type is a deliberate code change AND
    a brief amendment.
  - `AIEvidenceBundleBuildStatus`: closed enum with
    `EVIDENCE_BUNDLE_BUILT`, `EVIDENCE_BUNDLE_DEGRADED`,
    `EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE`.
  - `AIEvidenceBundleFactInput` / `AIEvidenceBundleFact`:
    fact records with `fact_id`, `fact_type`, `content`,
    `evidence_refs`, `source_report`, `status`,
    `degradation_reason`, `schema_version`.

## 7. Consumer contract

The bundle's `consumer_contract` block names every consumer the
bundle is read-allowed by and every consumer the bundle is
forbidden to be read by:

  - `allowed_consumers`: `human_operator`, `export_bundle`,
    `replay_annotation`, `reflection_annotation`,
    `operator_briefing_report`.
  - `forbidden_consumers`: `RiskEngine`, `ExecutionFSM`,
    `StrategyEngine`, `ExchangeGateway`, `RuntimeConfig`,
    `TelegramLiveCommand`, `CapitalFlow`, `PositionManager`.

The two lists are *disjoint*. The runtime trade-authority and
runtime-config surfaces are explicitly named as *forbidden*
consumers - even structurally, the bundle MUST NEVER be wired
into the Risk Engine, the Execution FSM, or any
runtime-config-patch path.

## 8. Forbidden inputs

The builder rejects (`ForbiddenAIInputError`) at intake any
input mapping whose key (at any nesting depth) is one of:

  - **Stateless-Inference violations:**
    `previous_ai_answer`, `prior_ai_answer`,
    `last_ai_answer`, `ai_session_history`,
    `ai_chat_history`, `chat_history`,
    `conversation_history`, `assistant_history`,
    `previous_briefing`, `previous_summary`,
    `previous_reflection`.
  - **Private-account-state violations:**
    `private_account_state`, `account_state`,
    `account_balance`, `account_balances`,
    `account_positions`, `account_orders`,
    `account_leverage`, `account_margin`, `wallet_balance`,
    `binance_account_state`, `binance_private_account_state`,
    `listen_key`, `listenkey`, `signed_endpoint_payload`.
  - **Credential-shaped keys** (substring match against the
    lowercased key name): `api_key`, `api_secret`,
    `private_key`, `secret_key`, `auth_token`,
    `bearer_token`, `access_token`, `refresh_token`,
    `credential`, `password`, `passphrase`, `deepseek_api`,
    `binance_secret`, `telegram_token`,
    `telegram_bot_token`, plus the bare-token names
    `secret`, `secrets`, `token`.

The builder fails *closed*: it never silently strips or
transforms a forbidden input. The first hit raises
`ForbiddenAIInputError` (a `ValueError` subclass) with the
offending key path.

## 9. Forbidden outputs

The bundle's `forbidden_fields` block names every field name an
AI consumer MUST NEVER produce:

  - Direction / trade-decision: `buy`, `sell`, `long`, `short`,
    `direction`, `side`, `entry`, `exit`.
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

The recursive `_assert_no_forbidden_fields` guard rejects any
payload carrying any of these keys at any nesting depth, both
on intake (so a caller cannot smuggle a `buy` key through a
fact's `content` payload) and at the serialisation boundary
(so a regression cannot accidentally leak one).

## 10. AI four root constraints

  1. **Responsibility Isolation** - enforced by the
     `forbidden_fields` block + the recursive
     `_assert_no_forbidden_fields` guard.
  2. **Stateless Inference** - enforced by the
     `_scan_for_forbidden_input` guard rejecting
     `previous_ai_answer` / `chat_history` /
     `private_account_state` / credential-shaped keys.
  3. **Hard Rule Anchoring** - enforced by demoting any fact
     without `evidence_refs` to `degraded_facts` plus a
     warning entry; such facts NEVER appear in the accepted
     `*_facts` collections.
  4. **Feedback Isolation** - enforced by the hard-pinned
     `ai_output_is_commentary_only=True` and
     `ai_output_can_be_training_label=False` flags
     re-emitted at every `to_dict()` boundary.

## 11. `evidence_refs` requirement

Every accepted fact MUST carry at least one
`evidence_refs` entry. The strings are preserved verbatim, in
input order, on every accepted fact; the bundle-level
`evidence_refs` is the deduplicated union in first-seen order.
A fact without `evidence_refs` is demoted to `degraded_facts`
with `degradation_reason="no_evidence_refs_supplied"` and a
matching warning entry is recorded.

## 12. Lookahead policy

The bundle pins the following lookahead-policy flags as
boolean `True`:

  - `frozen_evidence_only`
  - `no_future_market_data`
  - `no_training_from_ai_output`
  - `no_runtime_feedback`
  - `post_hoc_analysis_only_when_window_closed`

A consumer can read the bundle and assert the policy
programmatically without parsing a string list.

## 13. Stateless inference

Each call to `AIEvidenceBundleBuilder().build(...)` is
independent. The builder carries no instance state between
calls, never reads previous AI answers, never reads chat
history, never reads previous briefings or reflections it
itself produced. If a downstream consumer wants context
across calls, the consumer MUST re-derive the context from
the Truth Layer at each call.

## 14. Feedback isolation

AI output is *commentary*, not truth. The bundle is the
*input* to AI; the AI's text output is **not** a training
label, **not** a runtime fact, **not** a Risk Engine input.
The bundle pins `ai_output_is_commentary_only=True` and
`ai_output_can_be_training_label=False` at the top level, in
the consumer contract, and re-emits both flags at the
serialisation boundary.

## 15. This phase does NOT call DeepSeek

The `app/ai/` package imports nothing from `app.llm`,
`app.telegram`, `app.exchanges`, `app.risk`, `app.execution`,
`app.config`. It does not import `openai`, `anthropic`,
`deepseek`, `httpx`, `requests`, `aiohttp`, `urllib3`,
`websocket`, `websockets`, `grpc`, or `boto3`. The unit-test
harness asserts both invariants on every CI run.

The bundle is the *substrate* a later DeepSeek integration
will read from. The bundle itself does not call any LLM.

## 16. This phase does NOT authorise live trading

  - `mode=paper`
  - `live_trading=False`
  - `exchange_live_orders=False`
  - `right_tail=False`
  - `llm=False`
  - `telegram_outbound_enabled=False`
  - `binance_private_api_enabled=False`

The above invariants are pinned in every emitted bundle's
`safety_flags` block and asserted at the serialisation
boundary.

## 17. This phase does NOT authorise auto-tuning

  - `auto_tuning_allowed=False` is hard-pinned at the
    top level and re-emitted at every `to_dict()` boundary.
  - The recursive `_assert_no_forbidden_fields` guard
    refuses to emit any payload carrying a `*_patch` key.

## 18. Allowed successor work

Phase AI-1 unlocks ONLY the following later (separately
gated) work:

  - offline AI / operator-briefing report generation that
    consumes the bundle as a frozen input and produces
    redacted, evidence-cited, commentary-only output;
  - the Phase AI-2 *AI Reality Check* layer that verifies
    AI commentary against the Truth Layer cited in the
    bundle.

It does **NOT** unlock DeepSeek trade decisions, the AI
Layer's involvement in the Risk Engine, the AI Layer's
involvement in the Execution FSM, auto-tuning, real Telegram
outbound, or Phase 12.

## 19. Files shipped

  - `app/ai/__init__.py` - re-exports the public API.
  - `app/ai/evidence_bundle.py` - the schema, builder,
    forbidden-input guard, and forbidden-output guard.
  - `tests/unit/test_ai_evidence_bundle_builder.py` -
    55 unit tests covering every brief-mandated scenario
    plus defensive companions.
  - `docs/PHASE_AI_1_EVIDENCE_BUNDLE_BUILDER.md` - this
    document.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` - status updates marking Phase
    AI-1 as **IN_REVIEW**.

## 20. Tests

```
python -m pytest tests/unit/test_ai_evidence_bundle_builder.py -q
```

ships 55 PASS / 0 fail.

```
python -m pytest tests/unit -q
```

reports 2781 PASS / 0 fail (was 2726 before this phase;
+55 from this phase).

## 21. Phase status

**Phase AI-1 = IN_REVIEW** after this implementation PR.

  - **NOT** `ACCEPTED`.
  - **NOT** live ready.
  - **NOT** trade authority granted.
  - **NOT** DeepSeek integration.
  - **Phase 12 = FORBIDDEN.**
