# Phase AI-4 - DeepSeek Offline Sandbox v0

> **Status:** Paper / report / sandbox-only. **No runtime
> trading effect.** This phase ships the AI Layer's
> first **outbound-capable** runtime artefact - but the
> outbound transport is a refusal-only skeleton, the master
> gate is `enabled=False` by default, the outbound gate is
> `outbound_enabled=False` by default, and the runner short-
> circuits to a deterministic in-memory provider whenever
> either gate is closed. **It does NOT call DeepSeek live.
> It does NOT authorise live trading. It does NOT authorise
> auto-tuning. It does NOT enter Phase 12.**

## 1. Purpose

Phase AI-1 built the AI Evidence Bundle - the AI Layer's only
allowed *read* surface. Phase AI-2 built the AI Evidence
Citation Contract - the claim-level rule that every AI claim
MUST cite Truth-Layer evidence via `evidence_refs`. Phase
AI-3 built the deterministic / statistical Reality Check
Layer - the cross-verifier that demotes / rejects claims
which contradict the bundle's frozen facts or smuggle
unverifiable narrative. Phase AI-4 closes the cognition
substrate:

  - **The DeepSeek Offline Sandbox v0** consumes a frozen
    Phase AI-1 evidence bundle, runs the operator's task
    against it through a closed schema, and emits one
    schema-checked, evidence-cited, redacted, commentary-
    only :class:`AIIntelligenceOutput`.
  - The runner NEVER enters the trading hot path. It NEVER
    imports `app.risk`, `app.execution`, `app.exchanges`,
    `app.telegram`, or `app.config`. It NEVER reads private
    exchange / account state. It NEVER carries an API
    secret in any logged / exported / serialised payload.
  - The runner is **disabled by default**. Even when the
    master gate is opened, the *outbound* gate remains
    closed by default. Even when both gates are opened, the
    v0 :class:`OptionalDeepSeekHTTPProvider` skeleton
    refuses to actually contact the network - the real
    transport lands behind a later, separately gated PR.

Phase AI-4 is the AI Layer's *evidence compression* and
*operator briefing draft* substrate. It is **NOT** the
DeepSeek hot path. It is **NOT** Operator Briefing live
publishing. It is **NOT** auto-tuning. It is **NOT** Phase
12.

## 2. Relation to `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`

The AI Layer Engineering Spec is the constitution. Phase
AI-4 is its fourth runtime artefact (after Phase AI-1's
Evidence Bundle Builder, Phase AI-2's Evidence Citation
Contract, and Phase AI-3's Reality Check Layer):

  - Spec §1.1 *Responsibility Isolation* is enforced by
    re-using the Phase AI-1 recursive
    `_assert_no_forbidden_fields` guard at every
    `to_dict()` boundary, plus the
    :func:`strip_forbidden_fields` helper that strips
    forbidden trade-action / runtime-config-patch fields
    from the model output and records every stripped path
    in `forbidden_fields_stripped`.
  - Spec §1.2 *Stateless Inference* is enforced by the
    runner re-using the Phase AI-1
    `_scan_for_forbidden_input` intake guard. Any input
    that smuggles `previous_ai_answer`, `chat_history`,
    `private_account_state`, or a credential-shaped key is
    rejected via :class:`AIIntelligenceStatus.REJECTED_INVALID_INPUT`.
  - Spec §1.3 *Hard Rule Anchoring* is enforced by routing
    every model-emitted claim through the Phase AI-2
    `AIClaimCitationValidator` and the Phase AI-3
    `AIRealityCheckEngine`. A claim without
    `evidence_refs` is demoted; a claim that contradicts
    the bundle is demoted; an unsupported run downgrades
    the overall `authority_level` and records a
    matching `degraded_reasons` entry.
  - Spec §1.4 *Feedback Isolation* is enforced by the
    hard-pinned `stateless_inference=True`,
    `feedback_isolation=True`, `trade_authority=False`,
    `auto_tuning_allowed=False`, `phase_12_forbidden=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False` flags re-emitted
    at every `to_dict()` boundary.

Spec §2 *Allowed DeepSeek first-version outputs* is the
closed task-type vocabulary the runner accepts; Spec §3
*Forbidden DeepSeek outputs* is the recursive-stripping
target.

## 3. AI role - read-only cognition / evidence compression

The runner's role is *cognition*, not *control*. It:

  - reads the bundle's facts;
  - asks the model to compress them into a summary plus a
    set of cited claims;
  - validates citations through the Phase AI-2 contract;
  - cross-verifies through the Phase AI-3 Reality Check
    Layer;
  - emits commentary substrate, never a trade decision.

The Risk Engine remains the single trade-decision gate. The
Execution FSM remains independent of any AI / LLM signal.

## 4. Allowed inputs

  - One frozen Phase AI-1 :class:`AIEvidenceBundle` (handed
    in as a `Mapping`, typically the JSON view of
    `AIEvidenceBundle.to_dict()`).
  - One closed `AIIntelligenceTaskType` (`OPERATOR_BRIEFING_DRAFT`,
    `MARKET_INTELLIGENCE_SUMMARY`, `EVIDENCE_COMPRESSION`,
    `REPLAY_REFLECTION_SUMMARY`, `CONTRADICTION_SUMMARY`,
    `EVIDENCE_QUALITY_ASSESSMENT`, `COVERAGE_AUDIT_INTERPRETATION`,
    `POST_DISCOVERY_OUTCOME_SUMMARY`, `REJECT_TO_OUTCOME_SUMMARY`,
    `SEVERE_MISS_SUMMARY`).
  - One operator-supplied free-form instruction (paper /
    report / sandbox-only).
  - An optional `allowed_output_schema` shape (a `Mapping`).
  - An optional caller-supplied `forbidden_fields` tuple
    (additive on top of the canonical
    `FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS` set).

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

The intake guard is the same recursive
`_scan_for_forbidden_input` helper Phase AI-1 ships, applied
to the bundle, the operator instruction container, and the
allowed output schema container.

## 6. Allowed outputs

  - `summary` (a free-form commentary string).
  - `claims` (a list of :class:`AIIntelligenceClaim` objects,
    each with `evidence_refs`, `truth_layer_fields_used`,
    `citation_authority_level`, `reality_check_status`,
    `reality_check_authority_level`, `confidence_raw`,
    `confidence_reality_checked`).
  - `contradictions` (a list of claim ids the Reality Check
    Layer flagged).
  - `unsupported_claims` (a list of claim ids without
    sufficient evidence).
  - `risk_tags` (descriptive tags only - e.g.
    `breadth_weak`, `late_chase_high`,
    `funding_overheated`; **never** trade actions).
  - `evidence_refs` (deduplicated union of every claim's
    `evidence_refs`).
  - `forbidden_fields_stripped` (the audit trail).
  - `redacted_secret_count` (defensive count of
    credential-shaped keys redacted from the model output).
  - `warnings`, `degraded_reasons` (audit trail).
  - `safety_flags` block re-emitted on every `to_dict()`:
    `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `llm_outbound_enabled=False`,
    `sandbox_only=True`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`.

## 7. Forbidden outputs

A run output MUST NOT carry any of the following fields at
any nesting depth (recursive `_assert_no_forbidden_fields`
guard imported from `app.ai.evidence_bundle`, re-exported as
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

If a model emits any of these the runner:

  1. strips them via :func:`strip_forbidden_fields`,
  2. records every stripped path in
     `forbidden_fields_stripped`,
  3. flips the run to
     :class:`AIIntelligenceStatus.REJECTED_FORBIDDEN_FIELDS`,
  4. demotes the authority to
     :class:`AIIntelligenceAuthorityLevel.REJECTED`.

## 8. Config gates

`DeepSeekSandboxConfig` is closed and disabled-by-default.
Every gate must be flipped *explicitly* by the caller; the
runner NEVER reads the process environment to relax a gate.

| Field | Default | Notes |
| --- | --- | --- |
| `enabled` | `False` | Master gate. When `False` the runner short-circuits to a degraded result. |
| `provider` | `"deepseek"` | Provider name. Descriptive only. |
| `outbound_enabled` | `False` | Outbound gate. When `False` the runner uses :class:`FakeDeepSeekProvider` regardless of what was passed in. |
| `sandbox_only` | `True` | MUST remain `True` in v0. |
| `allow_trade_decision` | `False` | MUST remain `False` in v0. Validation raises if flipped. |
| `allow_runtime_config_change` | `False` | MUST remain `False` in v0. Validation raises if flipped. |
| `require_evidence_refs` | `True` | When `True` a claim without `evidence_refs` demotes the run. |
| `require_reality_check` | `True` | When `True` a claim that fails Reality Check demotes the run. |
| `stateless_inference` | `True` | Pinned in the output. |
| `feedback_isolation` | `True` | Pinned in the output. |
| `timeout_seconds` | `30.0` | Provider timeout budget. Must be > 0. |
| `max_tokens` | `2048` | Provider max-tokens budget. Must be > 0. |
| `model` | `"deepseek-chat"` | Provider model id. |
| `redaction_enabled` | `True` | When `True` credential-shaped keys are replaced with `<REDACTED>`. |

## 9. Secret handling

The runner NEVER carries an API secret in any logged /
exported / serialised payload:

  - the **intake guard** (`_scan_for_forbidden_input`)
    rejects any input mapping that contains a
    credential-shaped key at any nesting depth;
  - the **prompt builder** runs `redact_secrets` over the
    bundle and the allowed output schema before the prompt
    is constructed;
  - the **output redactor** runs `redact_secrets` over the
    model output and replaces credential-shaped values with
    the `<REDACTED>` sentinel;
  - the **audit trail** records `redacted_secret_count` so
    the operator can see how many credential-shaped values
    were redacted (the count never carries the values
    themselves).

Credential-shaped key tokens are imported from Phase AI-1's
`CREDENTIAL_LIKE_KEY_TOKENS` constant: `api_key`,
`api_secret`, `private_key`, `secret_key`, `auth_token`,
`bearer_token`, `access_token`, `refresh_token`,
`credential`, `password`, `passphrase`, `deepseek_api`,
`binance_secret`, `telegram_token`, `telegram_bot_token`,
plus the bare names `secret`, `secrets`, `token`.

## 10. Degraded mode

The runner converts every exceptional path into a degraded
:class:`AIIntelligenceOutput`, never a crash:

| Trigger | Status | Authority |
| --- | --- | --- |
| `config.enabled=False` | `DEGRADED_OUTBOUND_DISABLED` | `DEGRADED_NO_EVIDENCE` |
| `config.outbound_enabled=True` but no provider | `DEGRADED_OUTBOUND_DISABLED` | `DEGRADED_NO_EVIDENCE` |
| Provider raises :class:`DeepSeekOutboundDisabledError` | `DEGRADED_OUTBOUND_DISABLED` | `DEGRADED_NO_EVIDENCE` |
| Provider raises :class:`DeepSeekProviderTimeoutError` | `DEGRADED_PROVIDER_ERROR` | `DEGRADED_NO_EVIDENCE` |
| Provider raises :class:`DeepSeekProviderRateLimitedError` | `DEGRADED_PROVIDER_ERROR` | `DEGRADED_NO_EVIDENCE` |
| Provider raises :class:`DeepSeekProviderServerError` | `DEGRADED_PROVIDER_ERROR` | `DEGRADED_NO_EVIDENCE` |
| Provider raises any other exception | `DEGRADED_PROVIDER_ERROR` | `DEGRADED_NO_EVIDENCE` |
| Provider returns a non-mapping | `DEGRADED_PROVIDER_ERROR` | `DEGRADED_NO_EVIDENCE` |
| Forbidden field smuggled in model output | `REJECTED_FORBIDDEN_FIELDS` | `REJECTED` |
| Forbidden / credential-shaped key in input | `REJECTED_INVALID_INPUT` | `REJECTED` |
| Unknown task type | `REJECTED_INVALID_INPUT` | `REJECTED` |
| Missing evidence refs (with `require_evidence_refs=True`) | `DEGRADED_MISSING_EVIDENCE` | `DEGRADED_NO_EVIDENCE` |
| Reality Check failed / unsupported (with `require_reality_check=True`) | `DEGRADED_REALITY_CHECK` | `DEGRADED_REALITY_CHECK` |

In every case the runner emits one well-formed
:class:`AIIntelligenceOutput`; it never raises out of
:meth:`DeepSeekOfflineSandboxRunner.run`.

## 11. Timeout / 429 / 5xx handling

The runner catches every provider exception and converts it
into a degraded result. The closed exception hierarchy is:

  - :class:`DeepSeekSandboxError` (base)
    - :class:`DeepSeekOutboundDisabledError`
    - :class:`DeepSeekProviderTimeoutError`
    - :class:`DeepSeekProviderRateLimitedError`
    - :class:`DeepSeekProviderServerError`

A future real transport raises one of the four typed errors
on its respective failure mode. The runner's behaviour is
identical regardless of which transport raised - it always
returns a degraded :class:`AIIntelligenceOutput`, never a
crash, never a trade decision.

## 12. No hot path

The Phase AI-4 modules import nothing from the trading hot
path or the network:

  - `app/ai/intelligence_schema.py` imports nothing from
    `app.risk`, `app.execution`, `app.exchanges`,
    `app.telegram`, or `app.config` (AST-checked); imports
    nothing from `openai`, `anthropic`, `deepseek`, `httpx`,
    `requests`, `aiohttp`, `urllib3`, `websocket`,
    `websockets`, `grpc`, `boto3`, `socket` (AST-checked).
  - `app/ai/deepseek_sandbox.py` imports nothing from
    `app.risk`, `app.execution`, `app.exchanges`,
    `app.telegram`, or `app.config` (AST-checked); imports
    nothing from `openai`, `anthropic`, `deepseek`, `httpx`,
    `requests`, `aiohttp`, `urllib3`, `websocket`,
    `websockets`, `grpc`, `boto3`, `socket` (AST-checked).
  - `scripts/run_deepseek_offline_sandbox.py` imports
    nothing from `app.risk`, `app.execution`,
    `app.exchanges`, `app.telegram`, or `app.config`
    (AST-checked); imports nothing network-shaped
    (AST-checked).
  - `app/risk/`, `app/execution/`, `app/exchanges/` import
    nothing from `app.ai` or any submodule (AST-checked
    over every `.py` file in the three packages).

The unit-test harness asserts each of these invariants via
AST inspection on every CI run.

## 13. No Risk / Execution / Strategy / Telegram live consumer

The trade-authority surfaces (`app.risk`, `app.execution`,
`app.exchanges`, `app.telegram`, `app.config`) NEVER consume
:class:`AIIntelligenceOutput`. The output is *commentary
substrate* only:

  - Risk Engine remains the single trade-decision gate.
  - Execution FSM remains independent of any AI / LLM signal.
  - Capital Flow Engine remains independent of any AI / LLM
    signal.
  - Real Telegram outbound remains gated by Spec §41
    Go/No-Go.
  - Runtime config remains independent of any AI / LLM
    signal.

## 14. This phase does NOT authorise live trading

  - No member of `AIIntelligenceAuthorityLevel` carries
    trade-action semantics.
  - The maximum any output can reach is
    `SUPPORTED_INTELLIGENCE`, which is *commentary
    substrate* only.
  - `trade_authority=False` is hard-pinned at every
    `to_dict()` boundary.
  - `safety_flags.live_trading=False` is hard-pinned at
    every `to_dict()` boundary.
  - `safety_flags.exchange_live_orders=False` is hard-pinned
    at every `to_dict()` boundary.
  - The Risk Engine remains the single trade-decision gate.

## 15. This phase does NOT authorise auto-tuning

  - `auto_tuning_allowed=False` is hard-pinned at every
    `to_dict()` boundary.
  - The recursive `_assert_no_forbidden_fields` guard
    refuses to emit any payload carrying a `*_patch` key
    (`runtime_config_patch`, `symbol_limit_patch`,
    `threshold_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, `strategy_parameter_patch`).
  - The runner never produces `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`, or any
    other knob that would touch the runtime.

## 16. This phase does NOT enter Phase 12

  - `phase_12_forbidden=True` is hard-pinned at every
    `to_dict()` boundary.
  - `safety_flags.binance_private_api_enabled=False` is
    hard-pinned at every `to_dict()` boundary.
  - `safety_flags.telegram_outbound_enabled=False` is
    hard-pinned at every `to_dict()` boundary.
  - The runner never reads or carries an API key, an API
    secret, a `listenKey`, or a signed-endpoint payload.

## 17. Successor allowed by this phase

Phase AI-4 unlocks ONLY the following later (separately
gated) work:

  - **Phase AI-5 - Operator Briefing / Evidence Compression**
    that consumes the schema-checked
    :class:`AIIntelligenceOutput` and produces a redacted,
    operator-facing briefing artefact (still paper / report
    / sandbox-only).

It does **NOT** unlock:

  - DeepSeek trade decisions;
  - the AI Layer's involvement in the Risk Engine;
  - the AI Layer's involvement in the Execution FSM;
  - auto-tuning (`symbol_limit` / anomaly thresholds /
    candidate-pool capacity / Regime weights);
  - real Telegram outbound (live publishing of the briefing
    is a later phase);
  - the AI Layer's involvement in the runtime hot path;
  - the real DeepSeek HTTP transport (refusal-only skeleton
    only);
  - **Phase 12**.

## 18. Files shipped

  - `app/ai/intelligence_schema.py` - the closed
    :class:`AIIntelligenceOutput` schema, the
    redaction / forbidden-field-stripping helpers, the
    closed enums.
  - `app/ai/deepseek_sandbox.py` - the closed
    :class:`DeepSeekSandboxConfig`,
    :class:`DeepSeekSandboxInput`,
    :class:`DeepSeekProviderProtocol`,
    :class:`FakeDeepSeekProvider`,
    :class:`OptionalDeepSeekHTTPProvider`, and
    :class:`DeepSeekOfflineSandboxRunner`.
  - `app/ai/__init__.py` - extended re-exports for the
    Phase AI-4 public API alongside the Phase AI-1 +
    AI-2 + AI-3 surfaces.
  - `scripts/run_deepseek_offline_sandbox.py` - the offline
    runner script. Reads a frozen Phase AI-1 evidence
    bundle JSON from disk and writes the resulting
    :class:`AIIntelligenceOutput` to disk as JSON +
    Markdown.
  - `tests/unit/test_deepseek_offline_sandbox.py` - unit
    tests covering every brief-mandated scenario plus
    defensive companions.
  - `docs/PHASE_AI_4_DEEPSEEK_OFFLINE_SANDBOX.md` - this
    document.
  - `docs/DEEPSEEK_SANDBOX_RUNBOOK.md` - operator runbook.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` - status updates marking Phase
    AI-4 as **IN_REVIEW**.

## 19. Tests

```
python -m pytest tests/unit/test_deepseek_offline_sandbox.py -q
```

ships 94 PASS / 0 fail.

```
python -m pytest tests/unit -q
```

reports 3015 PASS / 0 fail (was 2921 before this phase;
+94 from this phase).

## 20. Phase status

**Phase AI-4 = IN_REVIEW** after this implementation PR.

  - **NOT** `ACCEPTED`.
  - **NOT** live ready.
  - **NOT** trade authority granted.
  - **NOT** real DeepSeek HTTP transport.
  - **NOT** Operator Briefing live publishing.
  - **NOT** Rule Sandbox.
  - **NOT** auto-tuning.
  - **Phase 12 = FORBIDDEN.**
