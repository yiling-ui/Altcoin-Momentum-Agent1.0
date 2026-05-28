# Phase AI-3 - Reality Check Layer v0

> **Status:** Paper / report / read-only. **No runtime effect.**
> This phase ships the AI Layer's *deterministic / statistical*
> Reality Check Layer as a closed schema, a deterministic
> verifier, and a unit-test harness. **It does NOT call
> DeepSeek. It does NOT call any LLM. It does NOT open any
> network socket. It does NOT authorise live trading. It does
> NOT authorise auto-tuning. It does NOT implement the
> DeepSeek Offline Sandbox (that is the later, separately
> gated Phase AI-4). Phase 12 remains FORBIDDEN.**

## 1. Purpose

Phase AI-1 built the AI Evidence Bundle - the AI Layer's only
allowed *read* surface. Phase AI-2 built the AI Evidence
Citation Contract - the claim-level rule that every AI claim
MUST cite Truth-Layer evidence via `evidence_refs`. Phase
AI-3 closes the loop:

  - **Having `evidence_refs` is necessary but NOT sufficient.**
  - An AI claim is also cross-checked against the Truth Layer
    that its `evidence_refs` point at, plus the market /
    system-behavior / outcome facts pinned in the Phase AI-1
    Evidence Bundle.
  - Reality Check is a **deterministic / statistical**
    verifier. It is **not** an LLM. It is **not** a DeepSeek
    client. It is **not** a network transport. It is **not**
    a prompt template.
  - Reality Check **never** outputs a trade decision,
    **never** outputs a runtime-config patch, and **never**
    alters any Risk / Execution / Exchange / Telegram / Config
    surface.

Reality Check is the cognitive *guard rail* for the AI Layer:
even a well-cited AI claim is downgraded or rejected if it
contradicts the Truth Layer, depends on a future / unsealed
window, or smuggles unverifiable narrative ("smart money is
definitely entering", "whales are accumulating", "faith is
returning", "main force intention is clear") with no
computable backing.

## 2. Relation to `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`

The AI Layer Engineering Spec is the constitution. Phase AI-3
is its third runtime artefact (after Phase AI-1's Evidence
Bundle Builder and Phase AI-2's Evidence Citation Contract):

  - Spec §1.1 *Responsibility Isolation* is enforced by
    re-using the Phase AI-1 recursive
    `_assert_no_forbidden_fields` guard at the
    serialisation boundary of every
    `AIRealityCheckResult.to_dict()` call.
  - Spec §1.2 *Stateless Inference* is enforced by the
    engine carrying no instance state between calls. Each
    `AIRealityCheckEngine.check(...)` call is independent.
    The engine never reads previous AI answers, chat
    history, `listenKey` payloads, signed-endpoint payloads,
    or any private exchange / account state.
  - Spec §1.3 *Hard Rule Anchoring* is the entire point of
    Phase AI-3: a claim with `evidence_refs` is **not**
    accepted on the strength of its citations alone. It must
    survive Reality Check (Lookahead Guard, Statistical
    Verification, Narrative Pollution Guard, Contradiction
    Detection, Microstructure Validation, Adversarial
    Evidence Check, Confidence Calibration).
  - Spec §1.4 *Feedback Isolation* is enforced by the
    hard-pinned `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=True`, `auto_tuning_allowed=False`
    flags re-emitted at every `to_dict()` boundary.

## 3. Reality Check is deterministic / statistical, not LLM

Reality Check is implemented as a pure Python module with no
network transport, no LLM client, and no prompt template:

  - the `app/ai/reality_check.py` module imports nothing
    from `openai`, `anthropic`, `deepseek`, `httpx`,
    `requests`, `aiohttp`, `urllib3`, `websocket`,
    `websockets`, `grpc`, `boto3`, or `socket` (AST-checked);
  - the module imports nothing from `app.risk`,
    `app.execution`, `app.exchanges`, `app.llm`,
    `app.telegram`, or `app.config` (AST-checked);
  - the module exposes no public callable whose name suggests
    an LLM client, an HTTP transport, a WebSocket, or an
    outbound channel (AST-checked);
  - the module source contains no `deepseek.` /
    `DeepSeekClient(` / `call_deepseek(` / `requests.get(` /
    `httpx.post(` / `aiohttp.ClientSession(` /
    `websocket.create_connection(` shape (string-checked).

Same input ⇒ identical output. Identical input on a second
engine instance ⇒ identical output. JSON round-trip without a
custom encoder is supported.

## 4. Supported categories

`AIRealityCheckCategory` is a closed enum with **seven**
verification axes. Adding a new category is a deliberate code
change AND a brief amendment.

| Category | What it checks |
| --- | --- |
| `STATISTICAL_VERIFICATION` | `evidence_refs` and `evidence_bundle_facts` are non-empty and statistically referenced by the claim. |
| `MICROSTRUCTURE_VALIDATION` | The bundle's market / system-behavior facts (breadth, data-gap, late-chase, fake-breakout, funding) are consistent with the claim. |
| `CONFIDENCE_CALIBRATION` | `confidence_reality_checked <= confidence_raw` (always). Raw confidence is clamped to `[0.0, 1.0]` first so a producer cannot smuggle confidence > 1.0. |
| `CONTRADICTION_DETECTION` | Direct contradictions between the claim and the bundle's market / outcome facts. |
| `ADVERSARIAL_EVIDENCE_CHECK` | Outcome-fact signals (`failed_continuation`, `missed_strong_tail_rate`, `fake_breakout_rising`) that argue *against* the claim. |
| `LOOKAHEAD_GUARD` | The bundle's lookahead policy (`frozen_evidence_only`, `no_future_market_data`, `no_training_from_ai_output`, `no_runtime_feedback`, `post_hoc_analysis_only_when_window_closed`); rejection on explicit `live_inference_uses_future_outcome=True` / `uses_unsealed_window=True` / `uses_future_market_data=True` / `trains_from_ai_output=True`. |
| `NARRATIVE_POLLUTION_GUARD` | Substring scan for unverifiable narrative phrases ("smart money is definitely entering", "whales are accumulating", "faith is returning", "main force intention is clear", "definitely entering", "obviously bullish", "without a doubt", "guaranteed to") combined with absence of computable backing. |

## 5. Status taxonomy

`AIRealityCheckStatus` is a closed enum with **six** values.
**No member grants trade authority.** Even `SUPPORTED` is
*commentary substrate* only.

| Status | Meaning |
| --- | --- |
| `SUPPORTED` | Claim is consistent with the cited Truth-Layer evidence and with the bundle's market / outcome facts. Authority: `SUPPORTED_INTELLIGENCE`. |
| `PARTIALLY_SUPPORTED` | Some support, but at least one supporting axis is weak / incomplete / invalid. Confidence is downgraded. Authority: `SUPPORTED_INTELLIGENCE` (no partial warning) or `UNSUPPORTED_INTELLIGENCE` (with partial warning). |
| `CONTRADICTED` | Claim asserts something the bundle's market / outcome facts directly contradict (e.g. "risk appetite expanding" vs. `breadth_weak=True` / `data_gap_severe=True` / `late_chase_high=True` / `fake_breakout_rising=True` / `funding_overheated=True` / `failed_continuation=True`). Authority: `REJECTED_BY_REALITY_CHECK`. |
| `INSUFFICIENT_EVIDENCE` | Claim has `evidence_refs` but lacks the Truth-Layer facts (or fact fields) needed to verify it. Authority: `DEGRADED_NO_EVIDENCE`. |
| `REJECTED_LOOKAHEAD` | Claim relies on a future / unsealed window or otherwise violates the AI Layer's lookahead policy. Authority: `REJECTED_BY_REALITY_CHECK`. |
| `REJECTED_UNVERIFIABLE_NARRATIVE` | Claim is written as unverifiable narrative with no computable backing. Authority: `REJECTED_BY_REALITY_CHECK`. |

## 6. Confidence calibration

The engine emits two confidence values per claim:

  - `confidence_raw` - the producer-supplied confidence
    (preserved verbatim, even if `> 1.0`).
  - `confidence_reality_checked` - the Reality-Checked
    confidence, ALWAYS less than or equal to the clamped raw
    value.

Calibration policy:

| Status | Calibration factor (applied to clamped raw) |
| --- | --- |
| `SUPPORTED` | 1.0 |
| `PARTIALLY_SUPPORTED` (no contradiction) | 0.7 |
| `PARTIALLY_SUPPORTED` (with contradiction signal) | 0.5 |
| `CONTRADICTED` | 0.0 |
| `INSUFFICIENT_EVIDENCE` | 0.0 (`None` if `confidence_raw` is `None`) |
| `REJECTED_LOOKAHEAD` | 0.0 (`None` if `confidence_raw` is `None`) |
| `REJECTED_UNVERIFIABLE_NARRATIVE` | 0.0 (`None` if `confidence_raw` is `None`) |

The engine clamps `confidence_raw` to `[0.0, 1.0]` before
applying the factor, so a producer that smuggles confidence
`> 1.0` cannot use it as a back-door. The
`confidence_reality_checked` field is also bounded by the raw
value at the result-construction boundary as a defensive
double-check.

## 7. Lookahead Guard

The Lookahead Guard runs **first**, before every other axis.
A claim that violates the lookahead policy is rejected with
`REJECTED_LOOKAHEAD` regardless of its citations or facts.

The guard reads `lookahead_policy: Mapping[str, Any]` and:

  - rejects if any required flag is explicitly `False`
    (`frozen_evidence_only`, `no_future_market_data`,
    `no_training_from_ai_output`, `no_runtime_feedback`,
    `post_hoc_analysis_only_when_window_closed`);
  - rejects if any forbidden flag is explicitly `True`
    (`live_inference_uses_future_outcome`,
    `uses_unsealed_window`, `uses_future_market_data`,
    `trains_from_ai_output`).

A flag that is *absent* from the policy mapping defaults to
the safe value (required flag = `True`, forbidden flag =
`False`). String values `"true"` / `"false"` (case-insensitive)
are honoured so a producer cannot bypass the guard with
string-typed flags.

## 8. Narrative Pollution Guard

The Narrative Pollution Guard runs **after** Lookahead but
**before** Statistical Verification, so a claim that smuggles
unverifiable narrative with no computable backing is rejected
as `REJECTED_UNVERIFIABLE_NARRATIVE` rather than the more
lenient `INSUFFICIENT_EVIDENCE`.

Detection is case-insensitive substring containment against a
closed vocabulary:

  - "smart money is definitely entering" / "smart money
    definitely entering" / "smart money entering";
  - "whales are accumulating" / "whales accumulating";
  - "faith is returning" / "faith returning";
  - "main force intention is clear" / "main force intention" /
    "main force is in control" / "main force in control" /
    "the main force" / "main force";
  - "definitely entering" / "obviously bullish" /
    "without a doubt" / "guaranteed to".

A narrative phrase is **only fatal** when the claim has no
computable backing (no `truth_layer_fields_used`, no
`market_facts`, no `system_behavior_facts`, no
`outcome_facts`). A narrative phrase paired with computable
backing is recorded as the
`narrative_phrase_present_but_facts_supplied` warning and
the claim is processed normally.

## 9. Forbidden outputs

A Reality Check result MUST NOT carry any of the following
fields at any nesting depth (recursive
`_assert_no_forbidden_fields` guard imported from
`app.ai.evidence_bundle`, re-exported as
`FORBIDDEN_REALITY_CHECK_FIELDS`):

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

The recursive guard runs at every `to_dict()` boundary and
raises `ValueError` if any forbidden key is present.

## 10. AI four root constraints

  1. **Responsibility Isolation** - enforced by the
     `_assert_no_forbidden_fields` recursive guard re-used
     from Phase AI-1.
  2. **Stateless Inference** - enforced by the engine's
     stateless implementation; the engine never reads
     previous AI answers, chat history, `listenKey`
     payloads, signed-endpoint payloads, or private
     account state.
  3. **Hard Rule Anchoring** - enforced by the closed status
     taxonomy: a claim with no `evidence_refs` is demoted
     to `INSUFFICIENT_EVIDENCE`; a claim that contradicts
     the bundle is demoted to `CONTRADICTED`; a claim with
     unverifiable narrative is rejected with
     `REJECTED_UNVERIFIABLE_NARRATIVE`; a claim that
     depends on a future window is rejected with
     `REJECTED_LOOKAHEAD`.
  4. **Feedback Isolation** - enforced by hard-pinned
     `ai_output_is_commentary_only=True`,
     `ai_output_can_be_training_label=False`,
     `phase_12_forbidden=True`, `auto_tuning_allowed=False`
     flags re-emitted at every `to_dict()` boundary, even if
     a downstream caller flips the dataclass field via
     `object.__setattr__`.

## 11. Safety boundary

Every emitted result re-pins the project-wide invariants:

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - `phase_12_forbidden = True`
  - `auto_tuning_allowed = False`

No Binance API key, no Binance API secret, no signed
endpoint, no account / order / position / leverage / margin
endpoint, no private WebSocket, no `listenKey`, no real
Telegram outbound, no DeepSeek trade decision.

## 12. This phase does NOT call DeepSeek

The `app/ai/reality_check.py` module imports nothing from
`app.llm`, `app.telegram`, `app.exchanges`, `app.risk`,
`app.execution`, `app.config`. It does not import `openai`,
`anthropic`, `deepseek`, `httpx`, `requests`, `aiohttp`,
`urllib3`, `websocket`, `websockets`, `grpc`, `boto3`, or
`socket`. The unit-test harness asserts both invariants on
every CI run via an AST walk over the source.

The engine NEVER calls an LLM. It is offline, deterministic,
statistical, and has no transport. The Reality Check Layer
is the **substrate** the later Phase AI-4 DeepSeek Offline
Sandbox will consume; this module never speaks to DeepSeek
itself.

## 13. This phase does NOT authorise live trading

  - No member of `AIRealityCheckStatus` carries trade-action
    semantics.
  - No member of `AIRealityCheckAuthorityLevel` grants trade
    authority.
  - Even `SUPPORTED` / `SUPPORTED_INTELLIGENCE` is
    *commentary substrate* only.
  - The Risk Engine remains the single trade-decision gate.
  - The Execution FSM remains independent of any AI / LLM
    signal.
  - `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False` are pinned at every
    `to_dict()` boundary.

## 14. This phase does NOT authorise auto-tuning

  - `auto_tuning_allowed=False` is hard-pinned at every
    `to_dict()` boundary.
  - The recursive `_assert_no_forbidden_fields` guard
    refuses to emit any payload carrying a `*_patch` key
    (`runtime_config_patch`, `symbol_limit_patch`,
    `threshold_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, `strategy_parameter_patch`).
  - The engine never produces `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`, or any
    other knob that would touch the runtime.

## 15. Successor allowed by this phase

Phase AI-3 unlocks ONLY the following later (separately
gated) work:

  - **Phase AI-4 - DeepSeek Offline Sandbox** that consumes
    the Reality Check substrate plus the Phase AI-1 Evidence
    Bundle and produces redacted, evidence-cited,
    commentary-only output in an offline / sandboxed
    environment. The Offline Sandbox is **NOT** the runtime
    hot path, **NOT** Phase 12, **NOT** trade authority.

It does **NOT** unlock:

  - DeepSeek trade decisions;
  - the AI Layer's involvement in the Risk Engine;
  - the AI Layer's involvement in the Execution FSM;
  - auto-tuning (`symbol_limit` / anomaly thresholds /
    candidate-pool capacity / Regime weights);
  - real Telegram outbound;
  - the AI Layer's involvement in the runtime hot path;
  - **Phase 12**.

## 16. Files shipped

  - `app/ai/reality_check.py` - the closed schema, the
    deterministic engine, the recursive guards, and the
    closed contradiction-signal vocabulary.
  - `app/ai/__init__.py` - extended re-exports for the Phase
    AI-3 public API alongside the Phase AI-1 + AI-2 surfaces.
  - `tests/unit/test_ai_reality_check_layer.py` - 70 unit
    tests covering every brief-mandated scenario plus
    defensive companions.
  - `docs/PHASE_AI_3_REALITY_CHECK_LAYER.md` - this document.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` - status updates marking Phase AI-3
    as **IN_REVIEW**.

## 17. Tests

```
python -m pytest tests/unit/test_ai_reality_check_layer.py -q
```

ships 70 PASS / 0 fail.

```
python -m pytest tests/unit -q
```

reports 2921 PASS / 0 fail (was 2851 before this phase;
+70 from this phase).

## 18. Phase status

**Phase AI-3 = IN_REVIEW** after this implementation PR.

  - **NOT** `ACCEPTED`.
  - **NOT** live ready.
  - **NOT** trade authority granted.
  - **NOT** DeepSeek integration.
  - **NOT** DeepSeek Offline Sandbox (separate later phase
    AI-4).
  - **NOT** Operator Briefing.
  - **NOT** Rule Sandbox.
  - **NOT** auto-tuning.
  - **Phase 12 = FORBIDDEN.**
