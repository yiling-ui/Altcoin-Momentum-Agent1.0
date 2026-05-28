# Phase AI-2 - Truth Layer / AI Evidence Citation Contract v0

> **Status:** Paper / report / read-only. **No runtime effect.**
> This phase ships the AI Layer's *claim-level* citation
> contract as a closed schema, a deterministic validator, a
> closed evidence-ref grammar, and a unit-test harness. **It
> does NOT call DeepSeek. It does NOT call any LLM. It does
> NOT open any network socket. It does NOT authorise live
> trading. It does NOT authorise auto-tuning. It does NOT
> implement Reality Check (that is a later, separately gated
> phase). Phase 12 remains FORBIDDEN.**

## 1. Purpose

Phase AI-2 builds the *AI Evidence Citation Contract*: the
claim-level rule that every AI claim MUST cite Truth-Layer
evidence via `evidence_refs`. Without this contract a
downstream AI / DeepSeek integration could emit free-form
"the regime is bullish" / "RAVEUSDT is a buy" prose and have
it consumed as truth. The citation contract makes the
producer's evidence the *only* path to commentary authority,
demotes claims that fail to cite, and rejects claims that
cite malformed references.

Phase AI-2 is the cognitive contract for the AI Layer:

  - **No `evidence_refs` => no accepted AI conclusion.**
  - **Malformed `evidence_refs` => rejected (strict) or
    demoted (non-strict).**
  - **Commentary-only claims stay commentary-only.**
  - **Trade-action / runtime-config-patch field names smuggled
    into a claim => rejected by schema.**
  - **The maximum authority any claim can reach is
    `SUPPORTED_INTELLIGENCE`, which is *commentary substrate*
    only.** No member of the closed
    `AIClaimAuthorityLevel` enum grants trade authority.

## 2. Relation to `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`

The AI Layer Engineering Spec is the constitution. Phase AI-2
is its second runtime artefact (after Phase AI-1's Evidence
Bundle Builder):

  - Spec §1.1 *Responsibility Isolation* is enforced by
    re-using the Phase AI-1 recursive
    `_assert_no_forbidden_fields` guard at the
    serialisation boundary of every `AIClaim.to_dict()` /
    `AIClaimCitationResult.to_dict()` call, plus the
    per-claim `_find_forbidden_field_in_claim` check that
    rejects claims whose `claim_id` / `claim_type` /
    `claim_text` / `evidence_refs` / `truth_layer_fields_used`
    contains a forbidden trade-action / runtime-config-patch
    field name verbatim.
  - Spec §1.2 *Stateless Inference* is enforced by the
    validator carrying no instance state between calls. Each
    `AIClaimCitationValidator.validate(...)` call is
    independent. The validator never reads previous AI
    answers, chat history, `listenKey` payloads,
    signed-endpoint payloads, or any private exchange /
    account state.
  - Spec §1.3 *Hard Rule Anchoring* is enforced by demoting
    every claim without `evidence_refs` to
    `AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`, never
    silently rewriting it. Claims with malformed citations
    are rejected (strict mode) or demoted (non-strict mode).
    `evidence_refs` are preserved verbatim - the validator
    NEVER invents a substitute.
  - Spec §1.4 *Feedback Isolation* is enforced by the
    hard-pinned `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=True`, `auto_tuning_allowed=False`
    flags re-emitted at every `to_dict()` boundary, even if a
    downstream caller flips the dataclass field.

## 3. Truth Layer role

The Truth Layer (`events.db`, replay artefacts, reflection
artefacts, evidence-contract artefacts, post-discovery outcome
reports, mover-capture audit reports, etc.) is the
**authoritative substrate**. The AI Layer is *commentary*,
not truth. Phase AI-2 enforces the boundary at the claim
level:

  - The `evidence_refs` of a claim point at concrete
    Truth-Layer artefacts (event ids, symbols,
    opportunity ids, scan-batch ids, metric ids, report ids).
  - The `truth_layer_fields_used` of a claim names the
    specific Phase AI-1 Evidence Bundle fields the claim is
    derived from (`market_facts.regime`,
    `outcome_facts.outcome_label`, etc.).
  - The validator does **not** cross-verify the claim's
    `claim_text` against the cited evidence's *content* -
    that is the Reality Check Layer's job (a later,
    separately gated phase). Phase AI-2 only validates the
    *citation contract*: structure, prefix grammar, presence,
    forbidden-field absence.

## 4. AI claim schema (closed)

  - **`AIClaimType`** - closed enum:
    `REGIME`, `NARRATIVE`, `LIQUIDITY`, `RISK`, `COVERAGE`,
    `OUTCOME`, `CONTRADICTION`, `REPLAY_SUMMARY`,
    `REFLECTION_SUMMARY`, `EVIDENCE_QUALITY`. Adding a new
    claim type is a deliberate code change AND a brief
    amendment.
  - **`AIClaimAuthorityLevel`** - closed enum:
    `COMMENTARY_ONLY`, `SUPPORTED_INTELLIGENCE`,
    `UNSUPPORTED_INTELLIGENCE`, `DEGRADED_NO_EVIDENCE`,
    `REJECTED_BY_SCHEMA`, `REJECTED_INVALID_EVIDENCE`. **No
    member grants trade authority.** `UNSUPPORTED_INTELLIGENCE`
    is reserved for the later Reality Check Layer; the v0
    validator never produces it.
  - **`AIClaimInput`** - producer-supplied frozen dataclass:
    `claim_id`, `claim_type`, `claim_text`, `evidence_refs`,
    `truth_layer_fields_used`, `confidence_raw`,
    `intended_authority_level`, `warnings`. Plain `Mapping`
    records are accepted and coerced.
  - **`AIClaim`** - validator-emitted frozen dataclass with the
    final `authority_level` plus the original claim fields
    preserved verbatim. The validator NEVER paraphrases
    `claim_text`, NEVER invents a missing `evidence_refs`,
    NEVER fabricates a `truth_layer_fields_used` entry.
  - **`AIClaimCitationResult`** - validator-emitted frozen
    dataclass: `claims`, `accepted_claim_count`,
    `degraded_claim_count`, `rejected_claim_count`,
    `missing_evidence_count`, `invalid_evidence_count`,
    `warnings`, `strict`, plus the hard-pinned
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=True`, `auto_tuning_allowed=False`
    flags.

## 5. `evidence_refs` requirement

Every claim that wants to reach
`AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE` MUST cite at
least one well-formed `evidence_refs` entry. A claim that
supplies no `evidence_refs` (or whose `evidence_refs` are
filtered to empty by the intake guard) is demoted to
`AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`. The validator
NEVER invents a substitute citation.

### 5.1 Supported evidence-ref grammar

The closed citation grammar is:

  - `event:<EVENT_TYPE>:<event_id>` -
    e.g. `event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123`.
    `EVENT_TYPE` is uppercase identifier with underscores;
    `event_id` is alphanumeric / underscore / dash.
  - `symbol:<SYMBOL>` - e.g. `symbol:RAVEUSDT`.
    `SYMBOL` is uppercase alphanumeric.
  - `opportunity:<opportunity_id>` -
    e.g. `opportunity:opp_42`. `opportunity_id` is
    alphanumeric / underscore / dash.
  - `scan_batch:<scan_batch_id>` -
    e.g. `scan_batch:batch_2026_05_28_001`.
  - `metric:<metric_name>:<window>` -
    e.g. `metric:capture_recall_rate:60d`.
  - `report:<report_id>` -
    e.g. `report:post_discovery_outcome_report`.

Adding a new prefix is a deliberate code change AND a brief
amendment.

### 5.2 Strict vs. non-strict mode

  - **Strict mode** (default): a claim with at least one
    malformed `evidence_refs` entry is rejected via
    `AIClaimAuthorityLevel.REJECTED_INVALID_EVIDENCE`. The
    original `evidence_refs` is preserved verbatim so the
    audit trail records exactly what the producer attempted
    to cite.
  - **Non-strict mode**: a claim with at least one valid
    `evidence_refs` entry stays
    `AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE` (with a
    warning); a claim with no valid entries is demoted to
    `AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`. The
    original `evidence_refs` is again preserved verbatim.

## 6. Authority levels

  - `COMMENTARY_ONLY` - producer-declared. Stays
    commentary-only regardless of citation strength. Counts
    as accepted.
  - `SUPPORTED_INTELLIGENCE` - cited at least one well-formed
    Truth-Layer reference and passed every schema check.
    Counts as accepted. **Commentary substrate only - does
    NOT grant trade authority.**
  - `UNSUPPORTED_INTELLIGENCE` - reserved for the later
    Reality Check Layer. Counts as degraded.
  - `DEGRADED_NO_EVIDENCE` - no `evidence_refs` (or all
    filtered out by non-strict mode). Counts as degraded.
  - `REJECTED_BY_SCHEMA` - unknown `claim_type`, missing
    `claim_id` / `claim_text`, or forbidden trade-action /
    runtime-config-patch field smuggled into a claim. Counts
    as rejected.
  - `REJECTED_INVALID_EVIDENCE` - strict mode with at least
    one malformed `evidence_refs` entry. Counts as rejected.

## 7. Degradation / rejection rules

| Condition | Strict mode result | Non-strict mode result |
| --- | --- | --- |
| Forbidden trade-action / config-patch field anywhere in claim | `REJECTED_BY_SCHEMA` | `REJECTED_BY_SCHEMA` |
| Missing `claim_id` / `claim_text` / unknown `claim_type` | `REJECTED_BY_SCHEMA` | `REJECTED_BY_SCHEMA` |
| Producer asked for `COMMENTARY_ONLY` | `COMMENTARY_ONLY` | `COMMENTARY_ONLY` |
| `evidence_refs` empty (or all blank) | `DEGRADED_NO_EVIDENCE` | `DEGRADED_NO_EVIDENCE` |
| All `evidence_refs` malformed | `REJECTED_INVALID_EVIDENCE` | `DEGRADED_NO_EVIDENCE` |
| Some `evidence_refs` malformed, some valid | `REJECTED_INVALID_EVIDENCE` | `SUPPORTED_INTELLIGENCE` (with warning) |
| All `evidence_refs` valid | `SUPPORTED_INTELLIGENCE` | `SUPPORTED_INTELLIGENCE` |

## 8. Forbidden output fields

Mirrors the `FORBIDDEN_AI_OUTPUT_FIELDS` set from Phase AI-1.
A claim's `claim_id` / `claim_type` / `claim_text` /
`evidence_refs` / `truth_layer_fields_used` MUST NOT contain
any of the following as a verbatim string:

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

A claim that smuggles any such name is rejected via
`AIClaimAuthorityLevel.REJECTED_BY_SCHEMA`. The recursive
`_assert_no_forbidden_fields` guard imported from
`app.ai.evidence_bundle` ALSO refuses to emit the resulting
serialised payload if any forbidden key appears at any
nesting depth.

The check is whole-string against forbidden field names so a
legitimate narrative containing the word `buy` in a sentence
(e.g. `"the team kept their roadmap secret"`) is **not**
rejected - only structural smuggling of forbidden field names
into citation-grammar slots is rejected.

## 9. AI four root constraints

  1. **Responsibility Isolation** - enforced by
     `_find_forbidden_field_in_claim` (per-claim) +
     `_assert_no_forbidden_fields` (per-payload, recursive,
     re-used from Phase AI-1).
  2. **Stateless Inference** - enforced by the validator's
     stateless implementation (no instance state between
     calls); the validator never reads previous AI answers,
     chat history, `listenKey` payloads, signed-endpoint
     payloads, or private account state.
  3. **Hard Rule Anchoring** - enforced by demoting any
     claim without `evidence_refs` to
     `DEGRADED_NO_EVIDENCE`; rejecting / demoting any claim
     with malformed `evidence_refs`; preserving
     `evidence_refs` verbatim (NEVER invented or rewritten).
  4. **Feedback Isolation** - enforced by hard-pinned
     `ai_output_is_commentary_only=True`,
     `ai_output_can_be_training_label=False`,
     `phase_12_forbidden=True`, `auto_tuning_allowed=False`
     flags re-emitted at every `to_dict()` boundary, even if
     a downstream caller flips the dataclass field via
     `object.__setattr__`.

## 10. Safety boundary

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

## 11. This phase does NOT call DeepSeek

The `app/ai/claim_contract.py` module imports nothing from
`app.llm`, `app.telegram`, `app.exchanges`, `app.risk`,
`app.execution`, `app.config`. It does not import `openai`,
`anthropic`, `deepseek`, `httpx`, `requests`, `aiohttp`,
`urllib3`, `websocket`, `websockets`, `grpc`, or `boto3`. The
unit-test harness asserts both invariants on every CI run via
an AST walk over the source.

The validator NEVER calls an LLM. It is offline,
deterministic, and has no transport. The claim citation
contract is the **substrate** a later DeepSeek integration
will MUST conform to; this module never speaks to DeepSeek
itself.

## 12. This phase does NOT authorise live trading

  - No member of `AIClaimAuthorityLevel` grants trade
    authority.
  - Even `SUPPORTED_INTELLIGENCE` is *commentary substrate*
    only.
  - The Risk Engine remains the single trade-decision gate.
  - The Execution FSM remains independent of any AI / LLM
    signal.
  - `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False` are pinned at every
    `to_dict()` boundary.

## 13. This phase does NOT authorise auto-tuning

  - `auto_tuning_allowed=False` is hard-pinned at every
    `to_dict()` boundary.
  - The recursive `_assert_no_forbidden_fields` guard
    refuses to emit any payload carrying a `*_patch` key.
  - No claim can produce `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`,
    `strategy_parameter_patch`. Any such smuggling is
    rejected by schema.

## 14. This phase does NOT implement Reality Check

Reality Check is a later, separately gated phase. Phase AI-2
only validates the *citation contract*: presence, prefix
grammar, schema, forbidden-field absence. Phase AI-2 does NOT
cross-verify a claim's `claim_text` against the *content* of
the cited evidence. The `UNSUPPORTED_INTELLIGENCE` member of
`AIClaimAuthorityLevel` is reserved for the Reality Check
Layer; the v0 validator never produces it.

## 15. Allowed successor work

Phase AI-2 unlocks ONLY the following later (separately
gated) work:

  - the **AI Reality Check Layer** that cross-verifies an AI
    claim's `claim_text` against the Phase AI-1 Evidence
    Bundle cited in `evidence_refs`, producing
    `UNSUPPORTED_INTELLIGENCE` for claims that pass the
    citation contract but do not survive content
    verification;
  - offline AI / operator-briefing report generation that
    consumes `AIClaimCitationResult` as a frozen input and
    produces redacted, evidence-cited, commentary-only
    output;
  - the **Operator Briefing** layer (separate later phase)
    that surfaces validated claims to the human operator
    via the existing redacted export surface.

It does **NOT** unlock DeepSeek trade decisions, the AI
Layer's involvement in the Risk Engine, the AI Layer's
involvement in the Execution FSM, auto-tuning, real Telegram
outbound, or Phase 12.

## 16. Files shipped

  - `app/ai/__init__.py` - re-exports the Phase AI-1 + Phase
    AI-2 public API.
  - `app/ai/claim_contract.py` - the schema, validator,
    forbidden-field guards, and supported evidence-ref
    grammar.
  - `tests/unit/test_ai_evidence_citation_contract.py` -
    70 unit tests covering every brief-mandated scenario
    plus defensive companions.
  - `docs/PHASE_AI_2_TRUTH_LAYER_EVIDENCE_CITATION_CONTRACT.md` -
    this document.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` - status updates marking Phase
    AI-2 as **IN_REVIEW**.

## 17. Tests

```
python -m pytest tests/unit/test_ai_evidence_citation_contract.py -q
```

ships 70 PASS / 0 fail.

```
python -m pytest tests/unit -q
```

reports 2851 PASS / 0 fail (was 2781 before this phase;
+70 from this phase).

## 18. Phase status

**Phase AI-2 = IN_REVIEW** after this implementation PR.

  - **NOT** `ACCEPTED`.
  - **NOT** live ready.
  - **NOT** trade authority granted.
  - **NOT** DeepSeek integration.
  - **NOT** Reality Check Layer.
  - **NOT** Operator Briefing.
  - **NOT** Rule Sandbox.
  - **NOT** auto-tuning.
  - **Phase 12 = FORBIDDEN.**
