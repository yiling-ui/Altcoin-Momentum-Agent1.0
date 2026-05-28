# AMA-RT Project Status

This document is the at-a-glance status board for AMA-RT V1.4. It is
intentionally short. The full phase-gate ledger lives in
`docs/PHASE_GATE.md`; per-phase deep dives live in their own
`PHASE_*` documents.

## Current phase

> **Phase AI-3 — Reality Check Layer v0
> (*现实检查层 v0*).**
> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).**
>
> Block A is complete. Block B is complete and the Block B
> Integrated Evidence Checkpoint is `PARTIAL_EVIDENCE` (advance
> allowed). Block C is complete: C1 / C2 / C3 merged. The Block C
> Integrated Checkpoint produced
> `status=EVIDENCE_GENERATED`,
> `replay_status=EVIDENCE_GENERATED`,
> `reflection_status=EVIDENCE_GENERATED`,
> `evidence_contract_status=EVIDENCE_GENERATED`,
> `accepted_claim_count=2704`,
> `degraded/rejected/missing/invalid=0`,
> `phase_12_forbidden=true`, `auto_tuning_allowed=false`,
> `known_blockers=[]`. Phase AI-1 (the AI Evidence Bundle
> Builder v0) is `IN_REVIEW` after PR #82 was merged. Phase
> AI-2 (the Truth Layer / AI Evidence Citation Contract v0)
> is `IN_REVIEW` after PR #83 was merged. The project is
> therefore allowed to enter the AI **deterministic /
> statistical** Reality Check Layer. The project is still
> **paper only** and Phase 12 remains **FORBIDDEN**.
>
> This slice ships the **AI Reality Check Layer v0** —
> the AI Layer's deterministic / statistical cross-verifier.
> Phase AI-1 built the AI Evidence Bundle (the only allowed
> read surface). Phase AI-2 built the AI Evidence Citation
> Contract (every claim must cite Truth-Layer evidence via
> `evidence_refs`). Phase AI-3 closes the loop: having
> `evidence_refs` is necessary but **not sufficient**; an AI
> claim is also cross-checked against the Truth Layer that
> its `evidence_refs` point at, plus the market /
> system-behavior / outcome facts pinned in the Phase AI-1
> Evidence Bundle. Reality Check is **not** an LLM, **not** a
> DeepSeek client, **not** a network transport, and **not** a
> prompt template. It is a closed, deterministic, statistical
> verifier that runs offline against the bundle's frozen
> facts.
>
> The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced *in
> code* and *in tests*:
>
>   1. **Responsibility Isolation** — claims and result
>      payloads are scrubbed of every forbidden trade-action /
>      runtime-config-patch field via the recursive
>      `_assert_no_forbidden_fields` guard re-used from the
>      Phase AI-1 module.
>   2. **Stateless Inference** — each
>      `AIRealityCheckEngine.check(...)` call is independent;
>      no instance state is mutated between calls; the engine
>      never reads previous AI answers, chat history,
>      `listenKey` payloads, signed-endpoint payloads, or any
>      private exchange / account state.
>   3. **Hard Rule Anchoring** — *no `evidence_refs` AND no
>      Truth-Layer facts ⇒ no accepted AI conclusion*. Claims
>      with citations but no facts are demoted to
>      `INSUFFICIENT_EVIDENCE`. Claims that contradict the
>      bundle's market / outcome facts are demoted to
>      `CONTRADICTED` (or `PARTIALLY_SUPPORTED` for
>      single-axis contradictions). Claims that smuggle
>      unverifiable narrative ("smart money is definitely
>      entering" / "whales are accumulating" / "faith is
>      returning" / "main force intention is clear") with no
>      computable backing are rejected via
>      `REJECTED_UNVERIFIABLE_NARRATIVE`. Claims that depend
>      on a future / unsealed window are rejected via
>      `REJECTED_LOOKAHEAD`.
>   4. **Feedback Isolation** — every emitted result re-pins
>      `ai_output_is_commentary_only=True`,
>      `ai_output_can_be_training_label=False`,
>      `phase_12_forbidden=true`, `auto_tuning_allowed=false`
>      so AI text can never become a training label or a
>      runtime fact, even if a downstream caller flips the
>      dataclass field.
>
> The result additionally pins the project-wide invariants:
> `mode=paper`, `live_trading=False`,
> `exchange_live_orders=False`, `right_tail=False`,
> `llm=False`, `telegram_outbound_enabled=False`,
> `binance_private_api_enabled=False`.
>
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** rule relaxation. **NOT** automatic
> `symbol_limit` expansion. **NOT** automatic anomaly
> threshold changes. **NOT** automatic candidate-pool
> capacity changes. **NOT** automatic Regime weight changes.
> **NOT** a Risk Engine change. **NOT** an Execution FSM
> change. **NOT** a direction call (long / short / entry /
> exit / stop / target / position size / leverage).
> **NOT** a runtime-config patch. **NOT** the DeepSeek
> integration (this phase does not call DeepSeek and does
> not call any LLM). **NOT** the DeepSeek Offline Sandbox
> (separate later Phase AI-4). **NOT** Operator Briefing.
> **NOT** Rule Sandbox. **NOT** any trading logic. **NOT**
> Phase 12. The Risk Engine remains the single
> trade-decision gate.
>
> ### What this PR ships
>
>   - `app/ai/reality_check.py` — the schema, deterministic
>     engine, recursive forbidden-field guards, and closed
>     contradiction-signal vocabulary.
>   - `app/ai/__init__.py` — extended re-exports for the
>     Phase AI-3 public API.
>   - `AIRealityCheckStatus` closed enum (6 values:
>     `SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`,
>     `INSUFFICIENT_EVIDENCE`, `REJECTED_LOOKAHEAD`,
>     `REJECTED_UNVERIFIABLE_NARRATIVE`).
>   - `AIRealityCheckCategory` closed enum (7 values:
>     `STATISTICAL_VERIFICATION`,
>     `MICROSTRUCTURE_VALIDATION`,
>     `CONFIDENCE_CALIBRATION`,
>     `CONTRADICTION_DETECTION`,
>     `ADVERSARIAL_EVIDENCE_CHECK`, `LOOKAHEAD_GUARD`,
>     `NARRATIVE_POLLUTION_GUARD`).
>   - `AIRealityCheckAuthorityLevel` closed enum (4 values:
>     `SUPPORTED_INTELLIGENCE`,
>     `UNSUPPORTED_INTELLIGENCE`,
>     `DEGRADED_NO_EVIDENCE`,
>     `REJECTED_BY_REALITY_CHECK`). **No member grants trade
>     authority.** The maximum any claim can reach is
>     `SUPPORTED_INTELLIGENCE`, which is *commentary
>     substrate* only.
>   - `AIRealityCheckInput` / `AIRealityCheckResult` frozen
>     dataclasses preserving `claim_id`, `claim_type`,
>     `claim_text`, `evidence_refs`,
>     `truth_layer_fields_used`, `authority_level`,
>     `confidence_raw`, `evidence_bundle_facts`,
>     `market_facts`, `system_behavior_facts`,
>     `outcome_facts`, `lookahead_policy`, plus the
>     engine-emitted `status`, `categories_checked`,
>     `supporting_evidence_refs`,
>     `contradicting_evidence_refs`,
>     `confidence_reality_checked`,
>     `authority_level_after_check`, `degradation_reason`,
>     `warnings`, plus the hard-pinned
>     `auto_tuning_allowed=false`, `phase_12_forbidden=true`,
>     `ai_output_is_commentary_only=True`,
>     `ai_output_can_be_training_label=False` flags.
>   - `AIRealityCheckEngine` (and the `reality_check_claim`
>     convenience wrapper) — deterministic; coerces every
>     input to a JSON-serializable form; runs the seven
>     verification axes in fixed order (Lookahead Guard →
>     Narrative Pollution Guard → Statistical Verification →
>     Contradiction Detection → Microstructure Validation →
>     Adversarial Evidence Check → Confidence Calibration);
>     emits `confidence_reality_checked <= confidence_raw`
>     always; clamps raw confidence to `[0.0, 1.0]` first;
>     never invents supporting / contradicting evidence_refs
>     beyond what the producer cited; runs the recursive
>     `_assert_no_forbidden_fields` guard at the
>     serialisation boundary.
>   - Closed lookahead-policy vocabulary: required flags
>     (`frozen_evidence_only`, `no_future_market_data`,
>     `no_training_from_ai_output`, `no_runtime_feedback`,
>     `post_hoc_analysis_only_when_window_closed`) MUST be
>     `True`; forbidden flags
>     (`live_inference_uses_future_outcome`,
>     `uses_unsealed_window`, `uses_future_market_data`,
>     `trains_from_ai_output`) MUST be absent or `False`.
>   - Closed unverifiable-narrative vocabulary
>     ("smart money is definitely entering" / "whales are
>     accumulating" / "faith is returning" / "main force
>     intention is clear" / "definitely entering" /
>     "obviously bullish" / "without a doubt" /
>     "guaranteed to" plus 8 close variants).
>   - Closed contradiction-signal vocabulary tied to the
>     Phase AI-1 fact groups (`market_facts.breadth_weak`,
>     `market_facts.data_gap_severe`,
>     `market_facts.data_gap_rate >= 0.5`,
>     `system_behavior_facts.late_chase_high`,
>     `system_behavior_facts.late_chase_rate >= 0.5`,
>     `system_behavior_facts.fake_breakout_rising`,
>     `system_behavior_facts.funding_overheated`,
>     `outcome_facts.failed_continuation`,
>     `outcome_facts.missed_strong_tail_rate >= 0.5`).
>   - New unit-test module
>     `tests/unit/test_ai_reality_check_layer.py`
>     (70 cases) covering every brief-mandated scenario:
>     supported claim → `SUPPORTED`, partial → confidence
>     downgrade, contradicted → `CONTRADICTED` /
>     `REJECTED_BY_REALITY_CHECK`, missing → `INSUFFICIENT_EVIDENCE`,
>     lookahead violation → `REJECTED_LOOKAHEAD`,
>     unverifiable narrative → `REJECTED_UNVERIFIABLE_NARRATIVE`,
>     `confidence_reality_checked <= confidence_raw`,
>     no-trade-authority on result, forbidden-fields absent
>     on serialised payload (parametrised over 25 fields),
>     forbidden imports
>     (`app.risk`/`app.execution`/`app.exchanges`/`app.llm`/
>     `app.telegram`/`app.config`) absent, no LLM /
>     DeepSeek / HTTP / network call path (AST + source +
>     public-callable check), deterministic output across
>     six status classes.
>   - New phase doc
>     `docs/PHASE_AI_3_REALITY_CHECK_LAYER.md`.
>
> ### What this PR does NOT ship
>
>   - No change to `app/risk/`, `app/execution/`,
>     `app/exchanges/`, `app/telegram/`, `app/config/`.
>   - No change to `app/ai/evidence_bundle.py` or
>     `app/ai/claim_contract.py`.
>   - No change to `symbol_limit`, anomaly thresholds,
>     candidate-pool capacity, Regime weights, or any
>     other runtime knob.
>   - No new private API surface, no signed endpoint, no
>     `listenKey`, no real Telegram outbound, no DeepSeek
>     trade decision, no LLM call path.
>   - No new event type, no new database schema, no new
>     migration.
>   - No new strategy. No new trading module. No new
>     direction classification. No new sizing rule.
>   - No Operator Briefing. No DeepSeek Offline Sandbox. No
>     Rule Sandbox. No trading logic.
>   - No automatic parameter tuning.
>   - **No Phase 12.**
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no Binance API key / secret
>   - no signed endpoint
>   - no private websocket
>   - no `listenKey`
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> ### Tests
>
>   - `tests/unit/test_ai_reality_check_layer.py` —
>     70/70 PASS.
>   - Full `tests/unit` suite — 2921/2921 PASS (no
>     regression vs. post-PR-#83 main 2851 baseline; +70
>     new tests on the new module).
>
> ### Why Phase AI-3 does NOT authorise live trading
>
> No member of `AIRealityCheckStatus` carries trade-action
> semantics. No member of `AIRealityCheckAuthorityLevel`
> grants trade authority. Even `SUPPORTED` /
> `SUPPORTED_INTELLIGENCE` is *commentary substrate* only —
> it does NOT direct the Risk Engine, the Execution FSM, the
> Capital Flow Engine, the Reconciler, or any other
> trade-authority surface. The result's `safety_flags` block
> re-pins `mode=paper` / `live_trading=False` /
> `exchange_live_orders=False` / `llm=False` etc. on every
> emission. Live-trading approval is a Phase 12 concern that
> requires the Spec §41 Go/No-Go checklist, and the
> checklist has **not** been initiated.
>
> ### Why Phase AI-3 does NOT authorise auto-tuning
>
> Every emitted result carries `auto_tuning_allowed=false`.
> The constant is hard-pinned at every `to_dict()` boundary
> even if a caller flips the dataclass field. The recursive
> `_assert_no_forbidden_fields` guard refuses to emit any
> payload that contains a `*_patch` key
> (`runtime_config_patch`, `symbol_limit_patch`,
> `threshold_patch`, `candidate_pool_patch`,
> `regime_weight_patch`, `strategy_parameter_patch`).
>
> ### Why Phase AI-3 does NOT call DeepSeek
>
> The `app/ai/reality_check.py` module imports nothing from
> `openai`, `anthropic`, `deepseek`, `httpx`, `requests`,
> `aiohttp`, `urllib3`, `websocket`, `websockets`, `grpc`,
> `boto3`, `socket`, `app.llm`, `app.telegram`,
> `app.exchanges`, `app.risk`, `app.execution`, or
> `app.config`. The unit-test harness asserts both
> invariants on every CI run via AST inspection of the
> source AND a string scan for any
> `deepseek.` / `DeepSeekClient(` / `call_deepseek(` /
> `requests.get(` / `httpx.post(` /
> `aiohttp.ClientSession(` /
> `websocket.create_connection(` shape.
>
> ### Successor allowed by this phase
>
> Only the later (separately gated) **Phase AI-4 — DeepSeek
> Offline Sandbox** that consumes the Reality Check
> substrate plus the Phase AI-1 Evidence Bundle and
> produces redacted, evidence-cited, commentary-only output
> in an offline / sandboxed environment. **NOT** the runtime
> hot path. **NOT** DeepSeek trade decisions. **NOT** the
> AI Layer's involvement in the Risk Engine. **NOT** the AI
> Layer's involvement in the Execution FSM. **NOT**
> auto-tuning. **NOT** real Telegram outbound. **NOT**
> Phase 12.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase AI-2 — Truth Layer / AI Evidence Citation Contract v0
> (*真相层 / AI 证据引用契约 v0*).**
> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).**
>
> Block A is complete. Block B is complete and the Block B
> Integrated Evidence Checkpoint is `PARTIAL_EVIDENCE` (advance
> allowed). Block C is complete: C1 / C2 / C3 merged. The Block C
> Integrated Checkpoint produced
> `status=EVIDENCE_GENERATED`,
> `replay_status=EVIDENCE_GENERATED`,
> `reflection_status=EVIDENCE_GENERATED`,
> `evidence_contract_status=EVIDENCE_GENERATED`,
> `accepted_claim_count=2704`,
> `degraded/rejected/missing/invalid=0`,
> `phase_12_forbidden=true`, `auto_tuning_allowed=false`,
> `known_blockers=[]`. Phase AI-1 (the AI Evidence Bundle
> Builder v0) is `IN_REVIEW` after PR #82 was merged. The
> project is therefore allowed to enter the AI **claim-level**
> citation contract. The project is still **paper only** and
> Phase 12 remains **FORBIDDEN**.
>
> This slice ships the **AI Evidence Citation Contract v0** —
> the AI Layer's claim-level rule that *every* AI claim MUST
> cite Truth-Layer evidence via `evidence_refs`. Without this
> contract a downstream AI / DeepSeek integration could emit
> free-form prose and have it consumed as truth. The citation
> contract makes the producer's evidence the *only* path to
> commentary authority, demotes claims that fail to cite, and
> rejects claims that cite malformed references.
>
> The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced *in
> code* and *in tests*:
>
>   1. **Responsibility Isolation** — claims and result
>      payloads are scrubbed of every forbidden trade-action /
>      runtime-config-patch field via the recursive
>      `_assert_no_forbidden_fields` guard re-used from the
>      Phase AI-1 module, plus the per-claim
>      `_find_forbidden_field_in_claim` check that rejects
>      claims smuggling forbidden field names into a
>      citation-grammar slot.
>   2. **Stateless Inference** — each
>      `AIClaimCitationValidator.validate(...)` call is
>      independent; no instance state is mutated between
>      calls; the validator never reads previous AI answers,
>      chat history, `listenKey` payloads, signed-endpoint
>      payloads, or any private exchange / account state.
>   3. **Hard Rule Anchoring** — *no `evidence_refs` => no
>      accepted AI conclusion*. Claims without
>      `evidence_refs` are demoted to
>      `AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`; claims
>      with malformed `evidence_refs` are rejected
>      (`REJECTED_INVALID_EVIDENCE`) in strict mode or demoted
>      in non-strict mode. The validator NEVER invents a
>      missing `evidence_refs` entry.
>   4. **Feedback Isolation** — every emitted result re-pins
>      `ai_output_is_commentary_only=True`,
>      `ai_output_can_be_training_label=False`,
>      `phase_12_forbidden=true`, `auto_tuning_allowed=false`
>      so AI text can never become a training label or a
>      runtime fact, even if a downstream caller flips the
>      dataclass field.
>
> The result additionally pins the project-wide invariants:
> `mode=paper`, `live_trading=False`,
> `exchange_live_orders=False`, `right_tail=False`,
> `llm=False`, `telegram_outbound_enabled=False`,
> `binance_private_api_enabled=False`.
>
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** rule relaxation. **NOT** automatic
> `symbol_limit` expansion. **NOT** automatic anomaly
> threshold changes. **NOT** automatic candidate-pool
> capacity changes. **NOT** automatic Regime weight changes.
> **NOT** a Risk Engine change. **NOT** an Execution FSM
> change. **NOT** a direction call (long / short / entry /
> exit / stop / target / position size / leverage).
> **NOT** a runtime-config patch. **NOT** the DeepSeek
> integration (this phase does not call DeepSeek and does
> not call any LLM). **NOT** the Reality Check Layer (a
> separate later phase). **NOT** Operator Briefing. **NOT**
> Rule Sandbox. **NOT** any trading logic. **NOT** Phase 12.
> The Risk Engine remains the single trade-decision gate.
>
> ### What this PR ships
>
>   - `app/ai/claim_contract.py` — the schema, validator,
>     forbidden-field guards, and supported evidence-ref
>     grammar.
>   - `app/ai/__init__.py` — extended re-exports for the
>     Phase AI-2 public API.
>   - `AIClaimAuthorityLevel` closed enum (6 values:
>     `COMMENTARY_ONLY`, `SUPPORTED_INTELLIGENCE`,
>     `UNSUPPORTED_INTELLIGENCE`, `DEGRADED_NO_EVIDENCE`,
>     `REJECTED_BY_SCHEMA`, `REJECTED_INVALID_EVIDENCE`).
>     **No member grants trade authority.** The maximum any
>     claim can reach is `SUPPORTED_INTELLIGENCE`, which is
>     *commentary substrate* only.
>   - `AIClaimType` closed enum (10 values: `REGIME`,
>     `NARRATIVE`, `LIQUIDITY`, `RISK`, `COVERAGE`,
>     `OUTCOME`, `CONTRADICTION`, `REPLAY_SUMMARY`,
>     `REFLECTION_SUMMARY`, `EVIDENCE_QUALITY`).
>   - `AIClaimInput` / `AIClaim` frozen dataclasses
>     preserving `claim_id`, `claim_type`, `claim_text`,
>     `evidence_refs`, `truth_layer_fields_used`,
>     `authority_level`, `confidence_raw`, `warnings`,
>     `schema_version`. The validator NEVER paraphrases
>     `claim_text`, NEVER invents a missing
>     `evidence_refs`, NEVER fabricates a
>     `truth_layer_fields_used` entry.
>   - `AIClaimCitationResult` frozen dataclass carrying
>     `claims`, `accepted_claim_count`,
>     `degraded_claim_count`, `rejected_claim_count`,
>     `missing_evidence_count`, `invalid_evidence_count`,
>     `warnings`, `strict`, plus the hard-pinned
>     `ai_output_is_commentary_only=True`,
>     `ai_output_can_be_training_label=False`,
>     `phase_12_forbidden=true`,
>     `auto_tuning_allowed=false` flags.
>   - `AIClaimCitationValidator` (and the
>     `validate_ai_claims` convenience wrapper) —
>     deterministic; coerces every input to a
>     JSON-serializable form; rejects unknown `claim_type` /
>     missing `claim_id` / missing `claim_text` /
>     forbidden-field smuggling via `REJECTED_BY_SCHEMA`;
>     demotes claims without `evidence_refs` via
>     `DEGRADED_NO_EVIDENCE`; rejects (strict) or demotes
>     (non-strict) claims with malformed `evidence_refs`;
>     runs the recursive `_assert_no_forbidden_fields`
>     guard at the serialisation boundary.
>   - Closed evidence-ref grammar:
>     `event:<EVENT_TYPE>:<event_id>`, `symbol:<SYMBOL>`,
>     `opportunity:<opportunity_id>`,
>     `scan_batch:<scan_batch_id>`,
>     `metric:<metric_name>:<window>`,
>     `report:<report_id>`. Adding a new prefix is a
>     deliberate code change AND a brief amendment.
>   - New unit-test module
>     `tests/unit/test_ai_evidence_citation_contract.py`
>     (70 cases) covering every brief-mandated scenario:
>     supported-with-valid-refs → `SUPPORTED_INTELLIGENCE`,
>     no-refs → `DEGRADED_NO_EVIDENCE`, invalid-ref →
>     `REJECTED_INVALID_EVIDENCE` (strict) or degraded
>     (non-strict), commentary-only stays commentary-only,
>     multiple `evidence_refs` preserved verbatim,
>     `truth_layer_fields_used` preserved verbatim,
>     validator never invents missing `evidence_refs`,
>     forbidden trade fields rejected / stripped / absent
>     (parametrised over 25 fields), result summary counts
>     correct, deterministic output, JSON-serializable
>     output, forbidden imports
>     (`app.risk`/`app.execution`/`app.exchanges`/`app.llm`/
>     `app.telegram`/`app.config`) absent, no LLM /
>     DeepSeek / HTTP call path (AST + public-callable
>     check).
>   - New phase doc
>     `docs/PHASE_AI_2_TRUTH_LAYER_EVIDENCE_CITATION_CONTRACT.md`.
>
> ### What this PR does NOT ship
>
>   - No change to `app/risk/`, `app/execution/`,
>     `app/exchanges/`, `app/telegram/`, `app/config/`.
>   - No change to `symbol_limit`, anomaly thresholds,
>     candidate-pool capacity, Regime weights, or any
>     other runtime knob.
>   - No new private API surface, no signed endpoint, no
>     `listenKey`, no real Telegram outbound, no DeepSeek
>     trade decision, no LLM call path.
>   - No new event type, no new database schema, no new
>     migration.
>   - No new strategy. No new trading module. No new
>     direction classification. No new sizing rule.
>   - No Operator Briefing. No Reality Check engine. No
>     Rule Sandbox. No trading logic.
>   - No automatic parameter tuning.
>   - **No Phase 12.**
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no Binance API key / secret
>   - no signed endpoint
>   - no private websocket
>   - no `listenKey`
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> ### Tests
>
>   - `tests/unit/test_ai_evidence_citation_contract.py` —
>     70/70 PASS.
>   - Full `tests/unit` suite — 2851/2851 PASS (no
>     regression vs. post-PR-#82 main 2781 baseline; +70
>     new tests on the new module).
>
> ### Why Phase AI-2 does NOT authorise live trading
>
> No member of `AIClaimAuthorityLevel` grants trade
> authority. Even `SUPPORTED_INTELLIGENCE` is *commentary
> substrate* only — it does NOT direct the Risk Engine, the
> Execution FSM, the Capital Flow Engine, the Reconciler, or
> any other trade-authority surface. The result's
> `safety_flags` block re-pins
> `mode=paper` / `live_trading=False` /
> `exchange_live_orders=False` / `llm=False` etc. on every
> emission. Live-trading approval is a Phase 12 concern
> that requires the Spec §41 Go/No-Go checklist, and the
> checklist has **not** been initiated.
>
> ### Why Phase AI-2 does NOT authorise auto-tuning
>
> Every emitted result carries `auto_tuning_allowed=false`.
> The constant is hard-pinned at every `to_dict()` boundary
> even if a caller flips the dataclass field. The recursive
> `_assert_no_forbidden_fields` guard refuses to emit any
> payload that contains a `*_patch` key
> (`runtime_config_patch`, `symbol_limit_patch`,
> `threshold_patch`, `candidate_pool_patch`,
> `regime_weight_patch`, `strategy_parameter_patch`); a
> claim that smuggles such a field via `claim_id` /
> `claim_type` / `claim_text` / `evidence_refs` /
> `truth_layer_fields_used` is rejected via
> `REJECTED_BY_SCHEMA`.
>
> ### Why Phase AI-2 does NOT implement Reality Check
>
> Reality Check is a later, separately gated phase. Phase
> AI-2 only validates the *citation contract*: presence,
> prefix grammar, schema, forbidden-field absence. It does
> NOT cross-verify a claim's `claim_text` against the
> *content* of the cited evidence. The
> `UNSUPPORTED_INTELLIGENCE` member of
> `AIClaimAuthorityLevel` is reserved for the Reality Check
> Layer; the v0 validator never produces it.
>
> ### Successor allowed by this phase
>
> Only the later (separately gated) **AI Reality Check
> Layer** that cross-verifies an AI claim's `claim_text`
> against the Phase AI-1 Evidence Bundle, **OR** later
> offline AI / operator-briefing report generation that
> consumes `AIClaimCitationResult` as a frozen input,
> **OR** the eventual Operator Briefing layer (separate
> later phase). **NOT** DeepSeek trade decisions. **NOT**
> the AI Layer's involvement in the Risk Engine. **NOT**
> the AI Layer's involvement in the Execution FSM. **NOT**
> auto-tuning. **NOT** real Telegram outbound. **NOT**
> Phase 12.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase AI-1 — AI Evidence Bundle Builder v0
> (*AI 证据包构建器 v0*).**
> **Status: IN_REVIEW** (after PR #82 was merged into
> `main`; not `ACCEPTED` until maintainer review). Phase
> AI-1 ships the AI Evidence Bundle Builder v0 — the AI
> Layer's only allowed read surface — as a closed schema, a
> deterministic builder, a paranoid intake guard, and a
> 55-test unit harness. The builder constructs frozen,
> evidence-cited, deterministic, JSON-serializable
> `AIEvidenceBundle` objects from Truth-Layer facts at call
> time. The bundle is the substrate any later AI / DeepSeek
> / LLM call MUST receive *as the only input* and infer
> *only* from. The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced
> in code AND in tests. Full deep-dive in
> `docs/PHASE_AI_1_EVIDENCE_BUNDLE_BUILDER.md`. **Phase 12
> remains FORBIDDEN.**

---

## Previous phase

> **Phase 11C.1C-C-B-B-B-D-E — Block B Integrated Evidence
> Checkpoint v0 (*Block B 综合证据检查点 v0*).**
> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**
>
> Block B (the D-A → D-B → B1.1 → B2-A → B2-B → B3 sequence)
> has shipped six paper / report / evidence-only slices: D-A
> Historical 60D Mover Coverage Backfill Audit
> (`ACCEPTED / PARTIAL_QUALITY / TOOLCHAIN_CLOSEOUT_ONLY`),
> D-B Post-Discovery Outcome Metrics
> (`ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT`),
> B1.1 Historical Price Path / Kline Path Adapter
> (`ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`),
> B2-A Reject-to-Outcome Attribution (IN_REVIEW), B2-B Severe
> Missed Tail Triage (IN_REVIEW), and B3 Discovery Quality
> Scorecard (IN_REVIEW). The project still lacked a single
> descriptive aggregated report that an operator can read at-
> a-glance to answer: "Is Block B *as a whole* in a state where
> it is sane to open the Block C Replay / Reflection extension
> for 11C Adaptive Events, or do we need more operator evidence
> first?". This slice ships that aggregation as a paper /
> report / evidence-only Block B Integrated Evidence Checkpoint
> v0.
>
> The checkpoint reads only local artefacts under
> `data/reports/`, `data/reports/exports/`, and
> `data/reports/post_discovery_outcome/`. It connects to no
> network, calls no LLM / DeepSeek, and opens no Telegram
> socket. It produces one
> `block_b_integrated_evidence_report.json` and one
> `block_b_integrated_evidence_report.md` under
> `data/reports/block_b_integrated_evidence/`.
>
> Status taxonomy is intentionally **not** `ACCEPTED`:
> `INSUFFICIENT_EVIDENCE` / `PARTIAL_EVIDENCE` /
> `EVIDENCE_GENERATED`. `next_allowed_phase` is either
> `Phase 11C.1C-C-B-B-B-E-A Replay Extension for 11C Adaptive
> Events v0` (paper / evidence only) or
> `NEEDS_OPERATOR_EVIDENCE`. The runner **never** authorises
> Phase 12 and **never** authorises auto-tuning;
> `phase_12_forbidden = true` and `auto_tuning_allowed = false`
> are hard-pinned on every emitted payload.
>
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** rule relaxation based on the integrated
> status. **NOT** automatic `symbol_limit` expansion.
> **NOT** automatic anomaly threshold changes. **NOT**
> automatic candidate-pool capacity changes. **NOT**
> automatic Regime weight changes. **NOT** a Risk Engine
> change. **NOT** an Execution FSM change. **NOT** a
> direction call (long / short / entry / exit / stop /
> target / position size / leverage). **NOT** a per-phase
> `ACCEPTED` gate (per-phase closeouts retain their own
> `ACCEPTED_TOOLCHAIN` / `PARTIAL_QUALITY` /
> `BLOCK_B_CHECKPOINT_ONLY` labels). **NOT** evidence
> closeout (separate later PR). **NOT** the Block C Replay /
> Reflection extension implementation (that is the
> *next-allowed* phase, not part of this PR). **NOT** the
> DeepSeek integration. **NOT** Phase 12. The Risk Engine
> remains the single trade-decision gate.
>
> ### What this PR ships
>
>   - New runner
>     `scripts/run_block_b_integrated_evidence_checkpoint.py`
>     (paper / report / evidence only):
>       - reads existing `events.jsonl` / `*.jsonl` files
>         under `--reports-dir` / `--exports-dir` /
>         `--post-discovery-dir`;
>       - reads the most recent
>         `post_discovery_outcome_report.json`;
>       - aggregates the simplified D-A / D-B / B1.1 / B2-A /
>         B2-B / B3 outputs into one descriptive
>         `block_b_integrated_evidence_report.json` (and
>         matching `.md` summary);
>       - emits one of the three closed statuses
>         (`INSUFFICIENT_EVIDENCE` / `PARTIAL_EVIDENCE` /
>         `EVIDENCE_GENERATED`);
>       - emits the corresponding `next_allowed_phase`
>         (Block C Replay / Reflection extension or
>         `NEEDS_OPERATOR_EVIDENCE`);
>       - never imports `app.risk` / `app.execution` /
>         `app.exchanges` / `app.llm` / `app.telegram`;
>       - reuses the existing
>         `app.adaptive.discovery_quality_scorecard`
>         engine + the recursive
>         `assert_payload_has_no_forbidden_keys` guard.
>   - New unit-test module
>     `tests/unit/test_block_b_integrated_evidence_checkpoint.py`
>     (13 cases) covering every brief-mandated acceptance
>     test: `INSUFFICIENT_EVIDENCE` on empty workspace,
>     `PARTIAL_EVIDENCE` when D-B post-discovery is missing
>     OR data-gap is high, `EVIDENCE_GENERATED` when every
>     component is present, `next_allowed_phase` correct,
>     `phase_12_forbidden = true` on every payload,
>     `auto_tuning_allowed = false` on every payload, no
>     forbidden trade-authority / runtime-tuning keys on any
>     payload, no banned imports
>     (`app.risk` / `app.execution` / `app.exchanges` /
>     `app.llm` / `app.telegram`), CLI exit-codes correct.
>   - New phase doc
>     `docs/PHASE_11C_1C_C_B_B_B_D_E_BLOCK_B_INTEGRATED_EVIDENCE_CHECKPOINT.md`.
>
> ### What this PR does NOT ship
>
>   - No change to `app/risk/`, `app/execution/`,
>     `app/exchanges/`, `app/llm/`, `app/telegram/`,
>     `app/config/`.
>   - No change to `symbol_limit`, anomaly thresholds,
>     candidate-pool capacity, Regime weights, or any
>     other runtime knob.
>   - No new private API surface, no signed endpoint, no
>     `listenKey`, no real Telegram outbound, no DeepSeek
>     trade decision.
>   - No automatic parameter tuning. No "looking at the
>     answer key" against the post-hoc D-A reference set.
>   - No new `app/adaptive/` engine. The runner reuses the
>     existing `build_discovery_quality_scorecard` builder
>     and the existing
>     `assert_payload_has_no_forbidden_keys` guard.
>   - No new strategy. No new trading module. No new
>     direction classification. No new sizing rule.
>   - No real evidence closeout.
>   - No Block C Replay / Reflection extension
>     implementation (the *next-allowed* phase, not part of
>     this PR).
>   - No DeepSeek integration.
>   - **No Phase 12.**
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no Binance API key / secret
>   - no signed endpoint
>   - no private websocket
>   - no `listenKey`
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> ### Tests
>
>   - `tests/unit/test_block_b_integrated_evidence_checkpoint.py` —
>     13/13 PASS.
>   - Full `tests/unit` suite — 2600/2600 PASS (no
>     regression vs. post-PR-#75 main 2587 baseline; +13
>     new tests on the new module).
>
> ### Why the integrated checkpoint does NOT authorise live trading
>
> The checkpoint answers a *coverage / capture / outcome /
> attribution / triage / discovery-quality* question at the
> **evidence aggregation level**. It does **not** simulate
> PnL, never reproduces a Risk Engine decision, never runs
> an Execution FSM. A `status = EVIDENCE_GENERATED` does
> **not** mean live trading is approved. A
> `status = INSUFFICIENT_EVIDENCE` does **not** mean live
> trading is *disapproved* either; live-trading approval is
> a Phase 12 concern that requires the Spec §41 Go/No-Go
> checklist, and the checklist has **not** been initiated.
>
> ### Why the integrated checkpoint does NOT authorise auto-tuning
>
> Every emitted checkpoint carries
> `auto_tuning_allowed = false`. The constant is hard-pinned
> in the runner source, the recursive forbidden-keys guard
> refuses to emit any payload that contains a `*_patch`
> key, and the runner never imports `app.risk` /
> `app.execution` / `app.exchanges` / `app.llm` /
> `app.telegram` / `app.config`. A `data_gap_count` counter
> or a `false_negative_reject_count` counter does **not**
> authorise the Risk Engine, the Execution FSM,
> `symbol_limit`, the candidate pool, anomaly thresholds, or
> Regime weights to be changed. Routing a case to the
> operator review queue is a *human* decision, not an
> automated one.
>
> ### Why a successful checkpoint authorises only Block C Replay / Reflection
>
> `status = EVIDENCE_GENERATED` (or `PARTIAL_EVIDENCE`)
> opens **only** `Phase 11C.1C-C-B-B-B-E-A Replay
> Extension for 11C Adaptive Events v0`. That phase is
> itself paper / report / evidence-only. It extends the
> existing Replay engine to play back the Block B adaptive
> events (D-A / D-B / B1.1 / B2-A / B2-B / B3) over
> previously captured event streams. It does **not** open
> Phase 12, does **not** open DeepSeek trade decisions,
> and does **not** open auto-tuning.
> `status = INSUFFICIENT_EVIDENCE` opens nothing
> automatically — the operator must collect more Block B
> evidence before any later phase is reachable.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-D — Discovery Quality
> Scorecard v0 (*发现质量评分板 v0*).**
> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**
>
> Phase 11C.1C-C-B-B-B-D-A audited *discovery* (did we see
> the mover?). Phase 11C.1C-C-B-B-B-D-B audited
> *post-discovery outcome* (how much room remained after
> first sighting?). Phase 11C.1C-C-B-B-B-D-C-A closed the
> loop on *reject correctness*. Phase
> 11C.1C-C-B-B-B-D-C-B attributed *severe misses* to a
> closed root-cause taxonomy. The project still lacked a
> single descriptive number that an operator can read
> at-a-glance to answer "how healthy was discovery quality
> on this audit window?".
>
> This slice ships that compression layer as a paper /
> report / evidence-only **Discovery Quality Scorecard v0**.
> The scorecard takes the simplified outputs of D-A / D-B /
> B2-A / B2-B and emits, per audit window:
>
>   - one descriptive `quality_bucket` (`GOOD` / `PARTIAL` /
>     `WEAK` / `DEGRADED` / `INSUFFICIENT_EVIDENCE`);
>   - per-axis rates (coverage / usable / early / late /
>     severe / insufficient-price-path / false-negative
>     reject / correct-protective reject / data-gap);
>   - a preserved `root_cause_summary` from the upstream
>     Severe Missed Tail Triage report;
>   - the `needs_operator_review` / `needs_data_recovery` /
>     `needs_rule_review` operator-routing flags;
>   - a hard-pinned `auto_tuning_allowed=False` flag on
>     every payload.
>
> The scorecard is intentionally **non-actionable**: it is a
> routing signal for human operators and **never** a knob
> the runtime can turn.
>
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** rule relaxation based on bucket
> verdicts. **NOT** automatic `symbol_limit` expansion.
> **NOT** automatic anomaly threshold changes. **NOT**
> automatic candidate-pool capacity changes. **NOT**
> automatic Regime weight changes. **NOT** a Risk Engine
> change. **NOT** an Execution FSM change. **NOT** a
> direction call (long / short / entry / exit / stop /
> target / position size / leverage). **NOT** evidence
> closeout (separate later PR). **NOT** Replay / Reflection
> extension (later slice). **NOT** the DeepSeek
> integration. **NOT** Phase 12. The Risk Engine remains
> the single trade-decision gate.
>
> ### What this PR ships
>
>   - New module
>     `app/adaptive/discovery_quality_scorecard.py` (paper
>     / pure / deterministic):
>       - `DiscoveryQualityBucket` closed string-constant
>         taxonomy (5 labels: `GOOD` / `PARTIAL` / `WEAK` /
>         `DEGRADED` / `INSUFFICIENT_EVIDENCE`).
>       - `DiscoveryQualityScorecardInput` (frozen
>         dataclass) bundling the simplified D-A / D-B /
>         B2-A / B2-B outputs.
>       - `DiscoveryQualityScorecard` (frozen dataclass)
>         carrying the descriptive bucket, per-axis rates,
>         operator-routing flags, preserved
>         `root_cause_summary`, `notable_warnings`, and
>         `evidence_refs`.
>       - `DiscoveryQualityScorecardEngine` /
>         `DiscoveryQualityScorecardEngineConfig` plus the
>         `build_discovery_quality_scorecard` convenience
>         builder.
>       - `assert_payload_has_no_forbidden_keys` recursive
>         guard against any trade-authority /
>         runtime-tuning field landing in a payload.
>       - Hard-pinned `auto_tuning_allowed=False` on every
>         emitted scorecard.
>   - Two new typed events in `app/core/events.py` (paper /
>     report / evidence only):
>       - `EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED`
>       - `EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED`
>   - Public exports added to `app/adaptive/__init__.py`.
>   - New unit-test module
>     `tests/unit/test_discovery_quality_scorecard.py` (22
>     cases) covering every brief-mandated acceptance test
>     (insufficient evidence, GOOD / PARTIAL on clean
>     inputs, PARTIAL / WEAK / DEGRADED with
>     `needs_data_recovery=True` on data gap or
>     insufficient-price-path, WEAK / DEGRADED with
>     `needs_operator_review=True` on severe miss,
>     `needs_rule_review=True` with
>     `auto_tuning_allowed=False` on false-negative reject,
>     `root_cause_summary` preserved on output, forbidden
>     fields absent on every payload, no forbidden imports
>     of `app.risk` / `app.execution` / `app.exchanges` /
>     `app.llm` / `app.telegram`).
>   - New phase doc
>     `docs/PHASE_11C_1C_C_B_B_B_D_D_DISCOVERY_QUALITY_SCORECARD.md`.
>
> ### What this PR does NOT ship
>
>   - No change to `app/risk/`, `app/execution/`,
>     `app/exchanges/`, `app/llm/`, `app/telegram/`,
>     `app/config/`.
>   - No change to `symbol_limit`, anomaly thresholds,
>     candidate-pool capacity, Regime weights, or any
>     other runtime knob.
>   - No new private API surface, no signed endpoint, no
>     `listenKey`, no real Telegram outbound, no DeepSeek
>     trade decision.
>   - No automatic parameter tuning. No "looking at the
>     answer key" against the post-hoc D-A reference set.
>   - No new strategy. No new trading module. No new
>     direction classification. No new sizing rule.
>   - No real evidence closeout.
>   - No Replay / Reflection extension for the new events.
>   - No DeepSeek integration.
>   - **No Phase 12.**
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no Binance API key / secret
>   - no signed endpoint
>   - no private websocket
>   - no `listenKey`
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> ### Tests
>
>   - `tests/unit/test_discovery_quality_scorecard.py` —
>     22/22 PASS.
>   - Full `tests/unit` suite — 2587/2587 PASS (no
>     regression vs. post-PR-#74 main 2565 baseline; +22
>     new tests on the new module).
>
> ### Why GOOD / PARTIAL / DEGRADED are discovery-quality labels, not trade-approval labels
>
> `GOOD` / `PARTIAL` / `WEAK` / `DEGRADED` describe
> **discovery health** — how often the discovery pipeline
> (radar + filter + candidate pool + first-seen detection)
> saw the moves the historical reference set lists. They do
> **not** describe *strategy quality*, *risk-decision
> quality*, *outcome quality*, or *trade-approval quality*.
> A `GOOD` bucket does **not** mean live trading is
> approved. A `DEGRADED` bucket does **not** mean live
> trading is disapproved. Both are diagnostic signals for a
> human operator, not switches the runtime can flip.
>
> ### Why this phase does NOT authorise auto-tuning
>
> Every emitted scorecard carries
> `auto_tuning_allowed=False`. A `DEGRADED` bucket reflects
> **one audit window**, not a portfolio of cases. Touching
> `symbol_limit` / anomaly thresholds / candidate-pool
> capacity / Regime weights / Risk Engine on the basis of a
> scorecard window is **out of scope**. A high
> `false_negative_reject_rate` flips
> `needs_rule_review=True`, but `auto_tuning_allowed` stays
> `False`; rule review is a *human* decision, not an
> automated one.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-C-B — Severe Missed Tail
> Triage v0 (*严重漏捕右尾归因 v0*).**
> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**
>
> Phase 11C.1C-C-B-B-B-D-A described the *discovery* layer
> ("did we see the mover?"). Phase 11C.1C-C-B-B-B-D-B / B.1
> described the *post-discovery outcome* ("how much room
> remained, and was the price path even available?"). Phase
> 11C.1C-C-B-B-B-D-C-A closed the loop between
> candidate-level reject decisions and the post-discovery
> outcome ("was the reject the right call?"). The project
> still lacked one piece: when a meaningful mover such as
> `RAVEUSDT` or `STOUSDT` shows up in the historical 60D
> mover reference set but not in the radar's captured set,
> **why** did we miss it?
>
> This slice ships that root-cause triage as a paper /
> report / evidence layer. The layer consumes the
> simplified outputs of D-A / D-B / B1.1 / B2-A and emits,
> per audited severe miss, a closed `SevereMissRootCause`
> + closed `SevereMissSeverity` plus the
> `needs_operator_review` / `needs_data_recovery` /
> `needs_rule_review` flags. `auto_tuning_allowed` is
> hard-pinned to `False` on every emitted record / report.
>
> The phase is **strictly attribution only** — no parameter
> changes, no trade suggestions, no rule modifications.
>
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** rule relaxation based on triage
> verdicts. **NOT** automatic `symbol_limit` expansion.
> **NOT** automatic anomaly threshold changes. **NOT**
> automatic candidate-pool capacity changes. **NOT**
> automatic Regime weight changes. **NOT** a Risk Engine
> change. **NOT** an Execution FSM change. **NOT** a
> direction call (long / short / entry / exit / stop /
> target / position size / leverage). **NOT** evidence
> closeout (separate later PR). **NOT** Replay /
> Reflection extension (later slice). **NOT** the DeepSeek
> integration. **NOT** Phase 12. The Risk Engine remains
> the single trade-decision gate.
>
> ### What this PR ships
>
>   - New module
>     `app/adaptive/severe_missed_tail_triage.py`
>     (paper / pure / deterministic):
>       - `SevereMissTriageInput`, `SevereMissTriageRecord`,
>         `SevereMissTriageReport`,
>         `SevereMissedTailTriageEngine`,
>         `SevereMissedTailTriageEngineConfig`.
>       - `SevereMissRootCause` closed string-constant
>         taxonomy (19 root-cause labels including
>         `UNIVERSE_GAP`, `SYMBOL_LIMIT_GAP`,
>         `CANDIDATE_POOL_EVICTED`,
>         `THRESHOLD_TOO_STRICT`, `PRE_ANOMALY_WEAK`,
>         `ANOMALY_TOO_LATE`, `WS_DATA_GAP`,
>         `REST_REFERENCE_GAP`, `EVENT_HISTORY_MISSING`,
>         `PRICE_PATH_MISSING`,
>         `PRICE_PATH_INSUFFICIENT`,
>         `NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME`,
>         `RISK_REJECTED_PROTECTIVE`,
>         `RISK_REJECTED_FALSE_NEGATIVE`,
>         `STRATEGY_MODE_FALSE_NEGATIVE`,
>         `LABEL_WINDOW_TOO_SHORT`,
>         `TRUE_DISCOVERY_FAILURE`,
>         `INSUFFICIENT_EVIDENCE`, `UNKNOWN`).
>       - `SevereMissSeverity` closed string-constant
>         taxonomy (`LOW` / `MEDIUM` / `HIGH` / `SEVERE` /
>         `CRITICAL` / `INSUFFICIENT_EVIDENCE`).
>       - `assert_payload_has_no_forbidden_keys` recursive
>         guard against any trade-authority / runtime-tuning
>         field landing in a payload.
>       - Hard-pinned `auto_tuning_allowed=False` on every
>         emitted record / report.
>   - Three new typed events in `app/core/events.py`
>     (paper / report / evidence only):
>       - `EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED`
>       - `EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED`
>       - `EventType.SEVERE_MISS_ESCALATION_REQUIRED`
>   - Public exports added to
>     `app/adaptive/__init__.py`.
>   - New unit-test module
>     `tests/unit/test_severe_missed_tail_triage.py` (22
>     cases) covering every brief-mandated acceptance test
>     (price path missing RAVE / STO style routes to
>     data-recovery without asserting any threshold
>     problem, candidate pool evicted, symbol limit gap
>     with `needs_rule_review=True` and
>     `auto_tuning_allowed=False`, universe gap, risk
>     rejected protective, risk rejected false negative
>     with severity `CRITICAL` and
>     `auto_tuning_allowed=False`, strategy mode false
>     negative, true discovery failure, insufficient
>     evidence refuses to fabricate, forbidden fields
>     absent on every record / report payload, no
>     forbidden imports).
>   - New phase doc
>     `docs/PHASE_11C_1C_C_B_B_B_D_C_B_SEVERE_MISSED_TAIL_TRIAGE.md`.
>
> ### What this PR does NOT ship
>
>   - No change to `app/risk/`, `app/execution/`,
>     `app/exchanges/`, `app/llm/`, `app/telegram/`,
>     `app/config/`.
>   - No change to live trading flag, runtime config,
>     thresholds, `symbol_limit`, `candidate_pool`, Regime
>     weights, the DeepSeek transport, or the Telegram
>     outbound transport.
>   - No new private API surface, no signed endpoint, no
>     `listenKey`, no real Telegram outbound, no DeepSeek
>     trade decision.
>   - No automatic parameter tuning. No "looking at the
>     answer key" against the post-hoc reference set.
>   - No new strategy. No new trading module. No new
>     direction classification. No new sizing rule.
>   - No real evidence closeout. No real-data run is
>     performed by this PR; the implementation is
>     evidence-ready but the closeout is a separate later
>     PR.
>   - No Replay / Reflection extension for the new events
>     (separate slice).
>   - No DeepSeek integration (separate phase).
>   - No Phase 12.
>
> ### Forbidden surface (verbatim)
>
>   - `app/risk/**`, `app/execution/**`,
>     `app/exchanges/**`, `app/llm/**`, `app/telegram/**`,
>     `app/config/**`.
>   - `symbol_limit` / `candidate_pool` / anomaly
>     threshold / Regime-weight runtime knobs.
>   - Binance private API (no API key, no API secret, no
>     signed endpoint, no `listenKey`, no private WS).
>   - Live orders.
>   - Real Telegram outbound.
>   - DeepSeek / LLM trade decisions (direction, position
>     size, leverage, stop-loss, target price, execution
>     command, runtime config patch).
>   - Automatic parameter tuning (incl. `symbol_limit`
>     expansion, anomaly threshold change, candidate pool
>     capacity change, Regime weight change).
>   - Phase 12 (real money / live trading).
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no Binance API key / secret
>   - no signed endpoint
>   - no private websocket
>   - no `listenKey`
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> ### Tests
>
>   - `tests/unit/test_severe_missed_tail_triage.py` —
>     22 / 22 PASS.
>   - Full `tests/unit` suite — 2565 / 2565 PASS (no
>     regression vs. post-PR-#74 main 2543 baseline; +22
>     new tests on the new module).
>
> ### Why this phase does NOT authorise auto-tuning
>
> The brief's hardest invariant is that root-cause triage
> MUST NEVER drive an automatic parameter change. Every
> emitted record and every emitted report carries
> `auto_tuning_allowed=False`; the constant is hard-pinned
> in `to_dict()` so a downstream serialiser cannot
> accidentally relax it. A `RISK_REJECTED_FALSE_NEGATIVE`
> verdict (severity `CRITICAL`) is the strongest signal
> the layer can emit — and even there, the verdict
> reflects ONE candidate's outcome, not a portfolio of
> cases. Outcome volatility is high in altcoin momentum;
> rule changes affect every future candidate, not just
> the one in front of the reviewer. Touching the rule
> itself is **out of scope** for this phase. A `CRITICAL`
> severity routes to operator review and rule review
> queues only.
>
> ### Why `RAVEUSDT` / `STOUSDT` are data-gap triage candidates only
>
> Under the B1 / B1.1 closeout, both symbols carry
> `price_path_loaded=false`, `source=absent`,
> `missing_reason=no_top_mover_row_covering_first_seen_time`.
> From that fact alone the layer cannot distinguish a
> true discovery failure, a risk-rejected false negative,
> a strategy-mode false negative, or a data gap. Asserting
> "RAVEUSDT proves the threshold is too strict" against
> this evidence base would be **looking at the answer
> key** — the auto-tuning failure mode the brief
> explicitly forbids. Both symbols are therefore
> classified as
> `NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME` / `MEDIUM` /
> `needs_data_recovery=True` /
> `needs_rule_review=False` / `auto_tuning_allowed=False`
> — data-gap triage candidates only. Once price-path
> completeness is restored (later optional task), the
> engine can re-attribute the same case to whichever
> world the new evidence supports. **Until then**,
> asserting a parameter error from a single coin is
> forbidden.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-C-A — Reject-to-Outcome
> Attribution v0 (*拒绝决策到结果归因 v0*).**
> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**
>
> Phase 11C.1C-C-B-B-B-D-A described the *discovery* layer
> (did we see the mover, when, how deep). Phase
> 11C.1C-C-B-B-B-D-B / B.1 described the *post-discovery
> outcome* (how much room remained after first sighting,
> with the daily-bucket price-path adapter). The project
> still lacked a closed loop linking **candidate-level
> reject decisions** to those **outcome labels**.
>
> This slice ships that closure as a paper / report /
> evidence attribution layer:
>
> ```
> opportunity_id
>     -> risk_reject_reason / no_trade_reason / strategy_mode
>     -> tail_label / post_discovery_outcome
>     -> reject correctness verdict
> ```
>
> For every audited candidate the runtime emits a closed
> `RejectAttributionVerdict`
> (`CORRECT_PROTECTIVE_REJECT` /
> `FALSE_NEGATIVE_REJECT` /
> `DATA_QUALITY_REJECT` /
> `LIQUIDITY_PROTECTIVE_REJECT` /
> `MANIPULATION_PROTECTIVE_REJECT` /
> `STOP_SAFETY_REJECT` /
> `REBASE_PROTECTIVE_REJECT` /
> `SYSTEM_SAFETY_REJECT` /
> `STRATEGY_MODE_FALSE_NEGATIVE` /
> `NO_REJECT_FOUND` /
> `INSUFFICIENT_EVIDENCE` /
> `UNKNOWN`). The verdict is descriptive only.
>
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** rule relaxation based on outcome
> labels. **NOT** automatic `symbol_limit` expansion.
> **NOT** automatic anomaly threshold changes. **NOT**
> automatic candidate-pool capacity changes. **NOT**
> automatic Regime weight changes. **NOT** a Risk Engine
> change. **NOT** an Execution FSM change. **NOT** a
> direction call (long / short / entry / exit / stop /
> target / position size / leverage). **NOT** Severe
> Missed Tail Triage (B2; later slice). **NOT** Replay /
> Reflection extension (later slice). **NOT** the DeepSeek
> integration. **NOT** Phase 12. The Risk Engine remains
> the single trade-decision gate.
>
> ### What this PR ships
>
>   - New module
>     `app/adaptive/reject_to_outcome_attribution.py`
>     (paper / pure / deterministic):
>       - `RejectAttributionInput`,
>         `RejectAttributionRecord`,
>         `RejectAttributionReport`,
>         `RejectToOutcomeAttributionEngine`,
>         `RejectAttributionEngineConfig`.
>       - `RejectAttributionVerdict` closed string-constant
>         taxonomy (12 verdict labels + `PROTECTIVE` /
>         `FALSE_NEGATIVE` groupings).
>       - Reason / flag substring taxonomies for stop
>         safety, system safety, data quality, liquidity,
>         manipulation, and rebase rejects.
>       - `assert_payload_has_no_forbidden_keys` recursive
>         guard against any trade-authority / runtime-tuning
>         field landing in a payload.
>       - Hard-pinned `auto_tuning_allowed=False` on every
>         emitted record / report.
>   - Four new typed events in `app/core/events.py`
>     (paper / report / evidence only):
>       - `EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED`
>       - `EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED`
>       - `EventType.FALSE_NEGATIVE_REJECT_DETECTED`
>       - `EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED`
>   - Public exports added to
>     `app/adaptive/__init__.py`.
>   - New unit-test module
>     `tests/unit/test_reject_to_outcome_attribution.py`
>     covering every brief-mandated acceptance test (stop
>     safety reject remains protective, data quality
>     reject, liquidity protective reject, manipulation
>     protective reject, false negative reject, strategy
>     mode false negative, no reject found, insufficient
>     evidence, forbidden fields absent, no forbidden
>     imports).
>   - New phase doc
>     `docs/PHASE_11C_1C_C_B_B_B_D_C_A_REJECT_TO_OUTCOME_ATTRIBUTION.md`.
>
> ### What this PR does NOT ship
>
>   - No change to `app/risk/`, `app/execution/`,
>     `app/exchanges/`, `app/llm/`, `app/telegram/`,
>     `app/config/`.
>   - No change to live trading flag, runtime config,
>     thresholds, `symbol_limit`, `candidate_pool`, Regime
>     weights, the DeepSeek transport, or the Telegram
>     outbound transport.
>   - No new private API surface, no signed endpoint, no
>     `listenKey`, no real Telegram outbound, no DeepSeek
>     trade decision.
>   - No automatic parameter tuning. No "looking at the
>     answer key" against the post-hoc reference set.
>   - No new strategy. No new trading module. No new
>     direction classification. No new sizing rule.
>   - No Severe Missed Tail Triage slice (B2 — separate
>     slice).
>   - No real evidence closeout. No real-data run is
>     performed by this PR; the implementation is
>     evidence-ready but the closeout is a separate later
>     PR.
>   - No Replay / Reflection extension for the new events
>     (separate slice).
>   - No DeepSeek integration (separate phase).
>   - No Phase 12.
>
> ### Forbidden surface (verbatim)
>
>   - `app/risk/**`, `app/execution/**`,
>     `app/exchanges/**`, `app/llm/**`, `app/telegram/**`,
>     `app/config/**`.
>   - Binance private API (no API key, no API secret, no
>     signed endpoint, no `listenKey`, no private WS).
>   - Live orders.
>   - Real Telegram outbound.
>   - DeepSeek / LLM trade decisions (direction, position
>     size, leverage, stop-loss, target price, execution
>     command, runtime config patch).
>   - Automatic parameter tuning (incl. `symbol_limit`
>     expansion, anomaly threshold change, candidate pool
>     capacity change, Regime weight change).
>   - Phase 12 (real money / live trading).
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no Binance API key
>   - no Binance API secret
>   - no signed endpoint
>   - no account / order / position / leverage / margin
>     endpoint
>   - no private websocket
>   - no `listenKey`
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> ### Tests
>
>   - `tests/unit/test_reject_to_outcome_attribution.py` —
>     43 / 43 PASS.
>   - Full `tests/unit` suite — 2543 / 2543 PASS (no
>     regression vs. post-PR-#71 main 2531 baseline; +12
>     new tests on the new module).
>
> ### Why a `FALSE_NEGATIVE_REJECT` does NOT mean "loosen the Risk Engine"
>
> A false-negative verdict is a single-case observation:
> at least one candidate ran upside after a non-hard-safety
> reject. It does **NOT** mean the Risk Engine's *policy*
> is wrong. It does **NOT** account for the cases the same
> rule prevented from going wrong — those are also
> non-trades, and they are also part of the rule's value.
> It does **NOT** guarantee a similar outcome on the next
> candidate; outcome volatility is high in altcoin
> momentum. It MUST be reviewed by a human, against a
> portfolio of cases, before any rule is touched. The
> rule-touching itself is **out of scope** for this phase.
> Every emitted record carries `auto_tuning_allowed=False`
> regardless of the verdict; the aggregate
> `RejectAttributionReport.auto_tuning_allowed` is also
> hard-pinned to `False`.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-B.1 — Historical Price Path
> Completeness / Kline Path Adapter v0 (*历史价格路径完整性 /
> K线路径适配器 v0*).**
> **Status: ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
> DAILY_BUCKET_ONLY.**
>
> B1.1 is the small follow-up patch on B1
> (Phase 11C.1C-C-B-B-B-D-B Post-Discovery Outcome Metrics
> v0). It does **NOT** extend B1 indefinitely. PR #71
> merged the Historical Price Path Adapter v0 / Kline Path
> Adapter v0 implementation into `main` and the real D-B
> evidence runner was rerun on `main` from the operator
> VPS against the new adapter. This docs-only closeout
> records the resulting B1.1 main-evidence run and flips
> the slice to **`ACCEPTED_TOOLCHAIN /
> PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`** —
> explicitly **NOT** "intraday 1m / 5m kline path solved".
>
> ### What this docs-only closeout records
>
>   - **B1.1 toolchain passed.** The price-path adapter
>     (`app/adaptive/post_discovery_price_path_adapter.py`)
>     resolves price paths at **record level** (no longer
>     symbol-only and no longer first-record-wins),
>     enforces the operator-supplied-path Lookahead Guard
>     (no point with `timestamp >
>     first_seen_time_utc_ms` may serve as
>     `first_seen_price`), and reads the local
>     `data/historical_market_store/top_movers/*.jsonl`
>     daily-bucket reference.
>   - **PR #71 evidence runner can evaluate 300 records
>     against the real D-A export rerun on `main`.**
>   - **300 `POST_DISCOVERY_OUTCOME_EVALUATED` events were
>     emitted** (one per record).
>   - **1 `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event
>     was emitted** (one report per batch).
>   - **The price-path adapter is currently
>     daily-bucket only (`kline_interval_used = 1d`).** It
>     is **NOT** an intraday 1m / 5m kline path adapter.
>     For the containing day only the close at
>     `day_end_ms` is emitted; for subsequent days the
>     daily high / low are stamped at `day_end_ms`,
>     surfaced as
>     `approximate_intra_day_timestamps = true`.
>   - **The local Historical Market Store currently
>     supplies a price path for 17 of 300 records.** 283
>     of 300 remain `absent`.
>   - **`RAVEUSDT` and `STOUSDT` remain unresolved** with
>     `missing_reason =
>     no_top_mover_row_covering_first_seen_time` (the
>     local daily-bucket store does not yet contain a
>     top-mover row whose day window covers the record's
>     `first_seen_time_utc_ms`).
>
> ### Lookahead Guard reaffirmation (hard rule)
>
>   - `first_seen_time_utc_ms` is read-only and may only
>     come from a D-A audited record / EventRepository
>     event timestamp.
>   - `first_seen_price` is **only** the price observed at
>     or before `first_seen_time_utc_ms` (operator anchor /
>     capture-path anchor / containing-day open).
>   - `price_path_after_first_seen` only carries points
>     strictly **after** `first_seen_time_utc_ms`.
>   - `peak`, `trough`, `MFE`, `MAE`, `remaining_upside`
>     are **post-window** audit metrics only.
>   - Future outcome **never** feeds radar score, candidate
>     promotion, the Risk Engine, the Execution FSM,
>     `symbol_limit`, the candidate pool, anomaly
>     thresholds, or Regime weights.
>
> ### B1.1 evidence run output (operator VPS, real D-A export)
>
> Output directory:
> `data/reports/post_discovery_outcome/pr71_main_price_path_evidence`
>
> Summary:
>
>   - `status = EVIDENCE_GENERATED`
>   - `evaluated_count = 300`
>   - `report_generated_count = 1`
>   - `event_counts.POST_DISCOVERY_OUTCOME_EVALUATED = 300`
>   - `event_counts.POST_DISCOVERY_OUTCOME_REPORT_GENERATED
>     = 1`
>   - `kline_interval_used = 1d`
>
> Price path resolution coverage:
>
>   - `price_path_records_loaded = 17`
>   - `price_path_records_missing = 283`
>
> Price path source summary:
>
>   - `historical_market_store_daily_top_movers = 17`
>   - `absent = 283`
>
> Price path missing-reason summary:
>
>   - `no_top_mover_row_covering_first_seen_time = 133`
>   - `no_first_seen_time = 110`
>   - `insufficient_post_first_seen_points = 40`
>
> Notable symbol price-path summary:
>
>   - `RAVEUSDT` — `loaded = false`,
>     `loaded_record_count = 0`, `record_count = 17`,
>     `source = absent`, `missing_reason =
>     no_top_mover_row_covering_first_seen_time`.
>   - `STOUSDT` — `loaded = false`,
>     `loaded_record_count = 0`, `record_count = 3`,
>     `source = absent`, `missing_reason =
>     no_top_mover_row_covering_first_seen_time`.
>
> Warnings:
>
>   - `d_a_backfill_records_missing_using_record_audited_fallback`
>     (Format B fallback engaged; expected for the real
>     D-A export shape; carried over from the B1 closeout
>     and unchanged in B1.1).
>
> Main-evidence check: **`B1_1_PRICE_PATH_MAIN_EVIDENCE_CHECK
> = PASS`**.
>
> ### What this acceptance level MEANS
>
>   - **The B1.1 toolchain works end-to-end against the
>     real D-A export.** The adapter resolves price paths
>     at record level, enforces the operator-path
>     Lookahead Guard, and the runner emits 300
>     `POST_DISCOVERY_OUTCOME_EVALUATED` events plus 1
>     `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event.
>   - **Coverage is partial.** Only 17 of 300 records have
>     an adapter-loaded price path today; 283 of 300
>     remain absent.
>   - **The price-path resolution is daily-bucket only.**
>     `kline_interval_used = 1d`. **B1.1 does NOT solve
>     the intraday 1m / 5m kline path problem.**
>
> ### What this acceptance level does NOT MEAN
>
>   - **B1.1 does NOT mean the intraday 1m / 5m kline
>     path is solved.** It is daily-bucket only.
>   - **B1.1 does NOT solve direction.** No `long` /
>     `short` / `entry` / `exit` / `stop` / `target` /
>     `position_size` / `leverage` field is emitted.
>   - **B1.1 does NOT prove strategy profitability.** No
>     PnL was simulated; no order was submitted; no Risk
>     Engine decision was reproduced.
>   - **B1.1 does NOT authorise auto-tuning.** No
>     `symbol_limit` expansion, anomaly threshold change,
>     candidate-pool capacity change, Regime weight
>     change, or any other runtime knob is authorised by
>     this closeout.
>   - **B1.1 does NOT authorise DeepSeek trade
>     decisions.** DeepSeek remains read-only /
>     sandbox-only / offline under the AI Layer
>     Constitution.
>   - **Phase 12 remains FORBIDDEN.**
>
> ### Next allowed route (mainline; back on the main route)
>
> > **Next allowed route: B2 — Severe Missed Tail Triage
> > v0.**
>
> B1 is a focused branch off the mainline; it is **not**
> to be extended indefinitely. B1.1 is the small patch on
> B1, and B1.1 closeout returns the project to the main
> route. The next allowed slice is **B2 — Severe Missed
> Tail Triage v0**.
>
> B2 will perform root-cause triage on unresolved
> severe-miss cases such as `RAVEUSDT` and `STOUSDT`,
> attributing each one into a **closed bucket** that
> includes (but is not limited to):
>
>   - `PRICE_PATH_GAP`
>   - `DATA_UNRELIABLE`
>   - `EVENT_HISTORY_MISSING`
>   - `UNIVERSE_GAP`
>   - `SYMBOL_LIMIT_GAP`
>   - `CANDIDATE_POOL_EVICTED`
>   - `THRESHOLD_TOO_STRICT`
>   - `WS_DATA_GAP`
>   - `REST_REFERENCE_GAP`
>   - `RISK_REJECTED_BUT_MOVED`
>   - `TRUE_DISCOVERY_FAILURE`
>   - `UNKNOWN`
>
> B2 remains forbidden from authorising:
>
>   - auto-tuning;
>   - any threshold change;
>   - `symbol_limit` expansion;
>   - candidate-pool capacity change;
>   - Regime weight change;
>   - live trading;
>   - DeepSeek trade decision;
>   - Phase 12.
>
> A *Historical Kline Store Builder / Intraday Price Path
> Backfill* (sometimes referred to as "B1.2") is **NOT**
> started now. It is recorded as an **optional future
> data-quality task only**, available **only if** B2
> triage proves that severe-miss attribution is blocked
> by missing intraday price paths, and **only with
> explicit owner approval**. It is **not** the
> recommended next slice, it is **not** a precondition
> for B2, and it does **not** block B2.
>
> ### Forbidden (under B1.1 closeout and remaining so)
>
>   - **Phase 12** (real money / live trading) — remains
>     **FORBIDDEN**;
>   - Binance private API (no API key, no API secret, no
>     signed endpoint, no `listenKey`, no private WS);
>   - live orders;
>   - real Telegram outbound;
>   - DeepSeek / LLM trade decisions (direction, position
>     size, leverage, stop-loss, target price, execution
>     command, runtime config patch);
>   - automatic parameter tuning (incl. `symbol_limit`
>     expansion, anomaly threshold change, candidate pool
>     capacity change, Regime weight change);
>   - blind walk-forward via D-B / B1.1 alone;
>   - any rule relaxation based on D-B / B1.1 labels;
>   - any Telegram command that bypasses the Risk Engine.
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no private API
>   - no live orders
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-B — Post-Discovery Outcome Metrics
> v0 (*发现后结果度量 v0*).**
> **Status: ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
> PRICE_PATH_INSUFFICIENT.**
>
> The D-B layer has now produced its first **real** evidence
> output against the Phase 11C.1C-C-B-B-B-D-A export that was
> rerun on `main` from the operator VPS. The closeout level
> below is **explicitly NOT full quality accepted** — it
> records that the toolchain works end-to-end against real
> D-A export records, while the outcome quality is bounded
> by missing post-first-seen price-path data.
>
> ### What this docs-only closeout records
>
>   - **PR #69 fixed the D-B evidence runner input adapter
>     gap.** The runner now consumes the real D-A export
>     shape: `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`
>     events whose payload **is** the per-mover record (not
>     wrapped in a `record` key), with the symbol-fallback
>     chain `record["symbol"]` →
>     `record["reference"]["symbol"]` →
>     `record["capture_path"]["symbol"]` → event-level
>     `symbol`.
>   - **D-B can now consume real D-A export records.** The
>     D-A export input check passed:
>     `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = 2`,
>     `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = 300`,
>     `D_A_EXPORT_INPUT_CHECK = PASS`.
>   - **300 D-A records were evaluated** by the D-B runner
>     against the real D-A export rerun on `main`.
>   - **`POST_DISCOVERY_OUTCOME_REPORT_GENERATED` was
>     produced** (one report per batch), alongside 300
>     `POST_DISCOVERY_OUTCOME_EVALUATED` events (one per
>     record).
>   - **The output is evidence-generated, but NOT
>     direction-quality accepted.** See the outcome / timing
>     summary below for the reason.
>
> ### B1 evidence run output (operator VPS, real D-A export)
>
> Output directory:
> `data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence`
>
> Summary:
>
>   - `status = EVIDENCE_GENERATED`
>   - `reference_window = 60d`
>   - `evaluated_count = 300`
>   - `report_generated_count = 1`
>   - output report:
>     `data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/post_discovery_outcome_report.json`
>   - output events:
>     `data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/events.jsonl`
>
> Outcome label summary:
>
>   - `INSUFFICIENT_PRICE_PATH = 195 / 300`
>   - `MISSED_STRONG_TAIL = 105 / 300`
>
> Detection timing summary:
>
>   - `INSUFFICIENT_DATA = 195 / 300`
>   - `MISSED = 105 / 300`
>
> Notable symbols (still unresolved by D-B alone):
>
>   - `RAVEUSDT` — `INSUFFICIENT_PRICE_PATH /
>     INSUFFICIENT_DATA`.
>   - `STOUSDT` — `INSUFFICIENT_PRICE_PATH /
>     INSUFFICIENT_DATA`.
>
> Warnings:
>
>   - `d_a_backfill_records_missing_using_record_audited_fallback`
>     (Format B fallback engaged; expected for the real
>     D-A export shape, where
>     `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED.payload.records`
>     is `None` and the per-mover records ride on
>     `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`).
>
> ### What this acceptance level MEANS
>
>   - **The D-B toolchain works end-to-end against real
>     D-A export records.** The runner reads the real D-A
>     export, adapts the `RECORD_AUDITED` events into
>     post-discovery outcome inputs, evaluates each one,
>     emits one `POST_DISCOVERY_OUTCOME_EVALUATED` per
>     record, aggregates them into one
>     `POST_DISCOVERY_OUTCOME_REPORT_GENERATED`, and writes
>     the JSON / JSONL / markdown artefacts under
>     `data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/`.
>     This is the **toolchain** half of the acceptance.
>   - **The output is evidence-generated, but NOT
>     direction-quality accepted.** 195/300 records (65%)
>     are `INSUFFICIENT_PRICE_PATH` because the D-A export
>     does not yet carry post-first-seen K-line price paths
>     for those movers; 105/300 records (35%) are
>     `MISSED_STRONG_TAIL` (the system never had a
>     first-seen anchor at all). Neither outcome class lets
>     the report classify the *quality* of the system's
>     timing — we cannot tell from this run whether the
>     first sighting was early, late, choppy, late-reversal,
>     or fake-breakout, because the price path that would
>     allow that classification is missing for every
>     evaluable record. This is the **partial quality**
>     half of the acceptance.
>   - **`RAVEUSDT` and `STOUSDT` remain unresolved** because
>     they are `INSUFFICIENT_PRICE_PATH /
>     INSUFFICIENT_DATA`. They cannot be triaged as severe
>     missed tails by D-B alone yet; they require
>     price-path completeness or explicit data-gap triage
>     before the Severe Missed Tail Triage slice can
>     consume them.
>
> ### What this acceptance level does NOT MEAN
>
>   - **D-B does NOT solve direction.** The runner does
>     not emit, and is forbidden to emit, any
>     `long` / `short` / `entry` / `exit` / `stop` /
>     `target` / `position_size` / `leverage` field. The
>     two label sets (`detection_timing_label`,
>     `outcome_label`) are descriptive only.
>   - **D-B does NOT prove strategy profitability.** No
>     PnL was simulated; no order was submitted; no Risk
>     Engine decision was reproduced. The labels describe
>     what the reference set already recorded; they do
>     not measure P&L.
>   - **D-B does NOT authorise auto-tuning.** The labels
>     MUST NOT drive `symbol_limit` expansion, anomaly
>     threshold changes, candidate-pool capacity changes,
>     Regime weight changes, or any other runtime knob.
>     "Looking at the answer key" against the post-hoc
>     D-A reference set is forbidden.
>   - **D-B does NOT authorise DeepSeek trade decisions.**
>     DeepSeek remains read-only / sandbox-only / offline
>     under the AI Layer Constitution; D-B's labels are
>     **not** trade authorisation surface for DeepSeek or
>     any other LLM.
>   - **Phase 12 remains FORBIDDEN.** No Phase 1 safety
>     flag is loosened by this closeout; Spec §41 Go/No-Go
>     has not been initiated.
>
> ### Next allowed route (paper-only; gated, sequential)
>
>   - **B1 (this slice) closeout** — accepted as
>     **toolchain + partial quality only**, NOT
>     direction-quality. This is the closeout currently
>     being recorded.
>   - Then **either** (operator's choice, gated by an
>     explicit kickoff PR per slice):
>       - **B1.1** — *Historical Price Path Completeness /
>         Kline Path Adapter* — likely needed because
>         195/300 records lack sufficient post-first-seen
>         price path, and `RAVEUSDT` / `STOUSDT` remain
>         unresolved on price-path / data-gap grounds.
>         Improving D-B outcome quality before B2 is the
>         **recommended** next route.
>       - **B2** — *Severe Missed Tail Triage* —
>         admissible **only with the explicit note that
>         `RAVEUSDT` and `STOUSDT` currently require
>         price-path / data-gap triage** before they can
>         be classified as severe missed tails by D-B
>         alone.
>   - The **next allowed route is NOT** to start DeepSeek
>     directly, and is **NOT** to start blind walk-forward
>     directly.
>   - Recommended next slice after this docs PR: **B1.1
>     Price Path Completeness / Kline Path Adapter.**
>
> ### Forbidden (under D-B PARTIAL_QUALITY closeout and
> remaining so)
>
>   - **Phase 12** (real money / live trading) — remains
>     **FORBIDDEN**;
>   - Binance private API (no API key, no API secret, no
>     signed endpoint, no `listenKey`, no private WS);
>   - live orders;
>   - real Telegram outbound;
>   - DeepSeek / LLM trade decisions (direction, position
>     size, leverage, stop-loss, target price, execution
>     command, runtime config patch);
>   - automatic parameter tuning (incl. `symbol_limit`
>     expansion, anomaly threshold change, candidate pool
>     capacity change, Regime weight change);
>   - blind walk-forward via D-B alone;
>   - any rule relaxation based on D-B labels;
>   - any Telegram command that bypasses the Risk Engine.
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - no private API
>   - no live orders
>   - no real Telegram outbound
>   - no DeepSeek trade decision
>   - **Phase 12 = FORBIDDEN**
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-B — Post-Discovery Outcome Metrics
> v0 (*发现后结果度量 v0*).**
> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**
>
> Phase 11C.1C-C-B-B-B-D-A only describes the *discovery* layer
> ("did we see this mover, when, how deep"). Phase
> 11C.1C-C-B-B-B-D-B answers the *next* question: once the
> system first saw a mover, **how much room remained to be
> captured?** Was the first sighting **early**, **late**,
> **choppy**, **fake breakout**, **late reversal**, or **missed
> strong tail**?
>
> This slice turns the manual K-line cross-check the operator
> was doing into a structured, exportable, replayable,
> auditable set of **outcome metrics + closed labels**. Paper
> / report / evidence only.
>
> **NOT** live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning.
> **NOT** rule relaxation based on outcome labels. **NOT**
> automatic `symbol_limit` expansion. **NOT** automatic
> anomaly threshold changes. **NOT** automatic candidate-pool
> capacity changes. **NOT** automatic Regime weight changes.
> **NOT** a Risk Engine change. **NOT** an Execution FSM
> change. **NOT** a strategy implementation. **NOT** a
> trading module. **NOT** a direction call (long / short /
> entry / exit / stop / target / position size / leverage).
> **NOT** Severe Missed Tail Triage (later slice). **NOT**
> Replay / Reflection extension (later slice). **NOT** the
> DeepSeek integration. **NOT** Phase 12. The Risk Engine
> remains the single trade-decision gate.
>
> ### What this PR ships
>
>   - New module
>     `app/adaptive/post_discovery_outcome_metrics.py`
>     (paper / pure / deterministic):
>       - `PostDiscoveryOutcomeInput`,
>         `PostDiscoveryOutcomeRecord`,
>         `PostDiscoveryOutcomeReport`,
>         `PostDiscoveryOutcomeEvaluator`,
>         `PostDiscoveryOutcomeEvaluatorConfig`,
>         `PricePoint`, `HistoricalMoverReferenceSummary`.
>       - `DetectionTimingLabel` enum (`EARLY` /
>         `EARLY_BUT_CHOPPY` / `MID_MOVE` / `LATE` /
>         `TOO_LATE` / `MISSED` / `INSUFFICIENT_DATA`).
>       - `OutcomeLabel` enum (`EARLY_CONTINUATION` /
>         `EARLY_BUT_CHOPPY` / `LATE_TOP_CHASE` /
>         `LATE_REVERSAL` / `MISSED_STRONG_TAIL` /
>         `FAKE_BREAKOUT` / `DUMPED` / `EXHAUSTION_CANDIDATE`
>         / `NO_CLEAR_EDGE` / `INSUFFICIENT_PRICE_PATH`).
>       - `assert_payload_has_no_forbidden_keys` recursive
>         guard against any trade-authority / runtime-tuning
>         field landing in a payload.
>   - Two new typed events in `app/core/events.py` (paper /
>     report / evidence only):
>       - `EventType.POST_DISCOVERY_OUTCOME_EVALUATED`
>       - `EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED`
>   - New unit-test module
>     `tests/unit/test_post_discovery_outcome_metrics.py` (20
>     cases) covering every brief-mandated acceptance test
>     (early continuation, early but choppy, late top chase,
>     late reversal, missed strong tail, fake breakout,
>     insufficient price path, forbidden fields absent, no
>     parameter tuning, no Risk / Execution / LLM / Telegram
>     imports).
>   - New phase doc
>     `docs/PHASE_11C_1C_C_B_B_B_D_B_POST_DISCOVERY_OUTCOME_METRICS.md`.
>
> ### What this PR does NOT ship
>
>   - No change to `app/risk/`, `app/execution/`,
>     `app/exchanges/`, `app/llm/`, `app/telegram/`.
>   - No change to live trading flag, runtime config,
>     thresholds, `symbol_limit`, `candidate_pool`, Regime
>     weights, the DeepSeek transport, or the Telegram
>     outbound transport.
>   - No new private API surface, no signed endpoint, no
>     `listenKey`, no real Telegram outbound, no DeepSeek
>     trade decision.
>   - No automatic parameter tuning. No "looking at the
>     answer key" against the post-hoc reference set.
>   - No new strategy. No new trading module. No new
>     direction classification. No new sizing rule.
>   - No Severe Missed Tail Triage slice (a later slice will
>     consume the `RAVEUSDT` / `STOUSDT` severe misses
>     recorded under D-A).
>   - No Replay / Reflection extension for the new events
>     (a later slice will fold them into Replay / Reflection).
>
> ### Forbidden surface (verbatim)
>
>   - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
>     `app/llm/**`, `app/telegram/**`.
>   - Binance private API (no API key, no API secret, no
>     signed endpoint, no `listenKey`, no private WS).
>   - Live orders.
>   - Real Telegram outbound.
>   - DeepSeek / LLM trade decisions (direction, position
>     size, leverage, stop-loss, target price, execution
>     command, runtime config patch).
>   - Automatic parameter tuning (incl. `symbol_limit`
>     expansion, anomaly threshold change, candidate pool
>     capacity change, Regime weight change).
>   - Phase 12 (real money / live trading).
>
> ### Safety boundary (held end-to-end)
>
>   - `mode = paper`
>   - `live_trading = False`
>   - `exchange_live_orders = False`
>   - `right_tail = False`
>   - `llm = False`
>   - `telegram_outbound_enabled = False`
>   - `binance_private_api_enabled = False`
>   - **Phase 12 = FORBIDDEN**
>
> ### Evidence closeout (this PR)
>
> **Status remains IN_REVIEW / INSUFFICIENT_EVIDENCE /
> EVIDENCE_CLOSEOUT_ONLY.** The D-B implementation PR (#67)
> is merged into `main`. This evidence-closeout PR adds a
> paper-only evidence runner
> (`scripts/run_post_discovery_outcome_evidence.py`), an
> 8-case runner unit-test module
> (`tests/unit/test_post_discovery_outcome_evidence_runner.py`),
> and an honest evidence run against the empty
> `data/historical_market_store/` /
> `data/sqlite/events.db` / `data/reports/exports/` paths in
> this workspace. The runner correctly refused to fabricate
> D-A records and produced:
>
>   - `data/reports/post_discovery_outcome/post_discovery_outcome_report.json`
>     with `status = INSUFFICIENT_EVIDENCE`,
>     `needs_operator_data = true`,
>     `evaluated_count = 0`,
>     `report_generated_count = 0`, warnings
>     `export_dir_no_d_a_payload`,
>     `events_db_no_d_a_payload`,
>     `historical_store_dir_missing`, `NEEDS_OPERATOR_DATA`.
>   - `data/reports/post_discovery_outcome/events.jsonl` -
>     empty (zero events).
>   - `data/reports/post_discovery_outcome/post_discovery_outcome_report.md`
>     - markdown summary that surfaces `RAVEUSDT: ABSENT`,
>     `STOUSDT: ABSENT`, and the safety-boundary block
>     verbatim.
>
> Tests:
>
>   - `tests/unit/test_post_discovery_outcome_metrics.py` -
>     20/20 pass.
>   - `tests/unit/test_post_discovery_outcome_evidence_runner.py`
>     - 8/8 pass.
>   - Full `tests/unit` suite - `2450 passed`.
>
> D-B will be flipped to `ACCEPTED` only after a follow-up
> operator-driven run that supplies a real Phase
> 11C.1C-C-B-B-B-D-A historical mover coverage payload via
> `--coverage-payload` / `--export-dir` / `--events-db`. D-B
> does **NOT** authorise live trading. D-B does **NOT**
> prove strategy profitability. D-B does **NOT** solve
> direction. D-B does **NOT** authorise automatic parameter
> tuning. D-B does **NOT** authorise DeepSeek trade
> decisions. Phase 12 remains **FORBIDDEN**.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-A — Historical 60D Mover Coverage
> Audit v0.**
> **Status: ACCEPTED / PARTIAL_QUALITY /
> TOOLCHAIN_CLOSEOUT_ONLY.**
>
> The D-A audit toolchain has been exercised end-to-end:
>
>   - the 60D Historical Market Store reference data has
>     been generated under `data/historical_market_store/`
>     (D-A.1 *Historical 60D Mover Reference Store Builder
>     v0* is the data-preparation child task under D-A and
>     has completed its toolchain role);
>   - `app.adaptive.historical_mover_coverage_backfill`
>     produced D-A audit records against that reference
>     store;
>   - the Phase 8.5 export bundle now contains the
>     `HISTORICAL_MOVER_COVERAGE_*` events that surface
>     those records, so the audit output is replayable and
>     externally reviewable;
>   - the operator's manual review of the audit output is
>     **PARTIAL** (per-symbol verdict recorded below);
>   - **`RAVEUSDT` and `STOUSDT` are recorded as severe
>     misses.**
>
> **D-A manual review (operator sample, recorded verbatim):**
>
>   - `PLAYUSDT` — qualified.
>   - `AGTUSDT` — discovered ~2 days ahead; mid-window chop
>     is small; qualified provided the system is not shaken
>     off by the chop.
>   - `BEATUSDT` — qualified.
>   - `VICUSDT` — marginally usable.
>   - `BIOUSDT` — usable, including the subsequent rally.
>   - `PROVEUSDT` — long-side entry was poor; if the system
>     had classified it as exhaustion / short, the result
>     could have been positive.
>   - `USUSDT` — not qualified.
>   - `RAVEUSDT` — **severely missed** (not qualified).
>   - `STOUSDT` — **severely missed** (not qualified).
>
> **Manual review result: PARTIAL.**
>
> ### D-A Interpretation / Non-Authority
>
> **D-A acceptance means:**
>
>   - the coverage-audit toolchain works end-to-end;
>   - audit records can be generated and persisted;
>   - export / replay evidence surface exists.
>
> **D-A acceptance does NOT mean:**
>
>   - discovery quality is fully acceptable;
>   - strategy profitability is proven;
>   - direction classification (long / short / exhaustion)
>     is solved;
>   - live trading is allowed;
>   - parameter relaxation is allowed;
>   - DeepSeek (or any LLM) can make trade decisions;
>   - automatic parameter tuning is allowed (no
>     "looking at the answer key" against the D-A
>     reference set).
>
> ### Next allowed work (paper-only; gated, sequential)
>
>   - docs status unification closeout (this PR);
>   - Post-Discovery Outcome Metrics;
>   - Severe Missed Tail Triage (covers `RAVEUSDT`,
>     `STOUSDT`, and any later additions);
>   - Replay / Reflection extension for 11C events;
>   - AI Layer Constitution docs baseline (see
>     `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`).
>
> ### Forbidden (under D-A acceptance and remaining so)
>
>   - **Phase 12** (real money / live trading) — remains
>     **FORBIDDEN**;
>   - Binance private API (no API key, no API secret,
>     no signed endpoint, no `listenKey`, no private WS);
>   - live orders;
>   - real Telegram outbound;
>   - DeepSeek / LLM trade decisions (direction, position
>     size, leverage, stop-loss, target price, execution
>     command, runtime config patch);
>   - automatic parameter tuning (incl. `symbol_limit`
>     expansion, anomaly threshold change, candidate pool
>     capacity change, Regime weight change);
>   - any Telegram command that bypasses the Risk Engine.
>
> **The Risk Engine remains the single trade-decision
> gate.**
>
> *Prior status (kept for history; superseded by the
> entry above):*
>
> **Phase 11C.1C-C-B-B-B-D-A.1 = IN_REVIEW (PR #65; data
> preparation child task under Phase 11C.1C-C-B-B-B-D-A,
> whose implementation has been merged via PR #64 and whose
> operator-VPS WS paper smoke + Phase 8.5 export evidence
> has been validated, but which itself is **NOT yet
> `ACCEPTED`** — current state `NOT_ACCEPTED /
> HISTORICAL_REFERENCE_DATA_REQUIRED / CLOSEOUT_PENDING`).**
> Historical 60D Mover Reference Store
> Builder v0 — public-data-only builder
> (`scripts/build_historical_mover_reference_store.py`) that
> produces local `data/historical_market_store/` artefacts the
> existing D-A audit's
> `app.adaptive.historical_mover_coverage_backfill.load_historical_market_store(root)`
> consumes unchanged. Paper / report / evidence only. **NOT**
> live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning.
> **NOT** a strategy implementation. **NOT** a trading module.
> **NOT** a Historical 30D+ / 60D *complete strategy* blind
> replay / walk-forward validation gate. **NOT** the
> small-money live-trading pre-validation gate. **NOT** the
> Phase 11C.1C-C-B-B-B-D-A *closeout* (the closeout will be a
> separate docs-only PR after the operator captures real 60D
> backfill audit evidence). **NOT** Phase 12. The Risk Engine
> remains the single trade-decision gate. The builder reuses
> the Phase 11C public allowlist
> (`assert_public_endpoint_allowed`), refuses every
> credential-shaped kwarg + every signed-request query
> parameter, and refuses to start when any of
> `BINANCE_API_KEY` / `BINANCE_API_SECRET` / `BINANCE_KEY` /
> `BINANCE_SECRET` / `BINANCE_TOKEN` / `BINANCE_PASSPHRASE` is
> set. Every emitted JSONL row is validated against the
> Lookahead Guard (`completed_tail_label` /
> `final_max_gain` / `future_return` / ...) before being
> appended. Phase 11C.1C-C-B-B-B-D-A *implementation* has
> been merged (PR #64) and the operator-VPS WS paper smoke
> + Phase 8.5 export evidence has been validated, but Phase
> 11C.1C-C-B-B-B-D-A itself is **NOT yet `ACCEPTED`** —
> current state `NOT_ACCEPTED /
> HISTORICAL_REFERENCE_DATA_REQUIRED / CLOSEOUT_PENDING`:
> real 60D Historical Market Store reference rows have not
> yet been generated, so D-A cannot be flipped to
> `ACCEPTED`. PR #65 only adds the Historical 60D Mover
> Reference Store Builder v0; PR #65 does **NOT** complete
> the real 60D backfill; PR #65 does **NOT** flip D-A to
> `ACCEPTED`. Real 60D data generation against Binance
> public futures endpoints + operator evidence are required
> after PR #65 merges before a separate docs-only closeout
> PR can mark D-A `ACCEPTED`. **No** previously-`ACCEPTED`
> phase is modified by this PR. Phase 12 remains
> **FORBIDDEN**.
>
> *Prior status (kept for history; superseded by the entry
> above):*
>
> **Phase 11C.1C-C-B-B-B-D-A = IN_REVIEW (PR #64; flipped
> 2026-05-25).** Historical 60D Mover Coverage Backfill
> Audit v0 / *历史 60 天异动币覆盖回填审计 v0* — v0
> engine / payload / report / Lookahead Guard
> implementation landed by PR #64. Paper / report /
> evidence only. **NOT** live trading. **NOT** AI
> Learning. **NOT** automatic parameter optimisation.
> **NOT** reinforcement learning. **NOT** rule
> relaxation based on historical movers. **NOT**
> automatic `symbol_limit` expansion. **NOT** automatic
> anomaly threshold changes. **NOT** automatic
> candidate-pool capacity changes. **NOT** automatic
> Regime weight changes. **NOT** a Risk Engine change.
> **NOT** an Execution FSM change. **NOT** a strategy
> implementation. **NOT** a trading module. **NOT** a
> Historical 30D+ / 60D *complete strategy* blind replay
> / walk-forward validation gate (that gate is reserved
> until small-money live trading prep and is **out of
> scope** here). **NOT** the Phase 11C.1C-C-B-B-B-D-A
> *closeout* (the closeout will be a separate docs-only
> PR after the operator captures real 60D backfill audit
> evidence). **NOT** Phase 12. The Risk Engine remains
> the single trade-decision gate. The audit answers
> eight explicit questions about the past 60 days of
> eligible USDT perpetual movers — and **only** those
> eight. `first_seen_time_utc` is the core acceptance
> field. Lookahead Guard is enforced in code:
> `completed_tail_label` / `final_max_gain` / future
> return MUST NOT drive reference selection or pollute
> the simulated live-radar score.
>
> *Prior status (kept for history; superseded by the
> entry above):*
>
> **Phase 11C.1C-C-B-B-B-D-A = NEXT_ALLOWED / NOT_STARTED
> (defined in place by docs-only kickoff PR #63; this PR
> scopes the slice; it does not flip its state).**
> Historical 60D Mover Coverage Backfill Audit v0 / *历史
> 60 天异动币覆盖回填审计 v0* — next allowed child slice
> under the Phase 11C.1C-C-B-B-B parent (on top of the
> `ACCEPTED` Phase 11C.1C-C-B-B-B-D track) — paper /
> report / evidence only. **NOT** live trading, **NOT**
> AI Learning, **NOT** automatic parameter optimisation,
> **NOT** reinforcement learning, **NOT** rule relaxation
> based on historical movers, **NOT** automatic
> `symbol_limit` expansion, **NOT** automatic anomaly
> threshold changes, **NOT** automatic candidate-pool
> capacity changes, **NOT** automatic Regime weight
> changes, **NOT** a Risk Engine change, **NOT** an
> Execution FSM change, **NOT** a strategy
> implementation, **NOT** a trading module, **NOT** a new
> runtime module, **NOT** a new event type, **NOT** the
> complete Strategy Validation Lab follow-up, **NOT** a
> Historical 30D+ / 60D *complete strategy* blind replay /
> walk-forward validation gate (that gate is reserved
> until small-money live trading prep and is **out of
> scope** here), **NOT** the Phase 11C.1C-C-B-B-B-D-A
> *implementation* (the implementation, if any, requires
> a separate PR cycle), **NOT** the Phase
> 11C.1C-C-B-B-B-D-A *closeout* (the closeout will be a
> separate docs-only PR after the operator captures the
> B1 / B2 backfill audit evidence), **NOT** Phase 12.
> Discovery-layer historical coverage audit only. The
> audit answers eight explicit questions about the past
> 60 days of eligible USDT perpetual movers — and only
> those eight: (1) over the past 60 days, did AMA-RT
> discover the eligible USDT perpetual movers; (2) if
> discovered, when was the first detection
> (`first_seen_time_utc`); (3) what was the first
> detection event (`first_seen_event_type`); (4) how deep
> did the capture path go (`capture_path_depth`,
> `reached_anomaly`, `reached_label_queue`,
> `reached_tail_label`,
> `reached_strategy_validation_sample`); (5) if not
> discovered, why (`miss_reason` from the fixed
> taxonomy); (6) is each missed mover a
> universe-coverage issue or a discovery-layer warning;
> (7) which captured movers were rejected by the Risk
> Engine (`risk_rejected = true`; recorded as a
> conservative paper outcome, **not** a discovery
> failure); (8) which captured movers only made it
> partway and never entered the label / validation chain
> (`status = partially_captured`). The 60D top-mover
> reference set must record per-window /
> per-symbol: `reference_window_start_utc`,
> `reference_window_end_utc`, `top_mover_symbol`,
> `top_mover_rank`, `max_window_gain`, `max_24h_gain`,
> `reference_timestamp_utc`,
> `eligible_usdt_perpetual = true / false`. The
> per-captured-mover audit row must record:
> `top_mover_symbol`, `mover_window_start_utc`,
> `mover_window_end_utc`, `top_mover_rank`,
> `max_window_gain`, `max_24h_gain`,
> `eligible_usdt_perpetual`, `system_captured`,
> `first_seen_time_utc`, `first_seen_event_type`,
> `first_seen_latency_seconds` where a mover reference
> timestamp exists, `capture_path_depth`,
> `reached_anomaly`, `reached_label_queue`,
> `reached_tail_label`,
> `reached_strategy_validation_sample`, `risk_rejected`,
> `status` (`captured` / `partially_captured` / `missed`
> / `excluded`), `miss_reason`. The fixed `miss_reason`
> taxonomy is exactly: `not_in_futures_universe`,
> `symbol_not_in_exchange_info`, `not_usdt_perpetual`,
> `missing_historical_reference_data`,
> `missing_event_history`, `below_liquidity_threshold`,
> `symbol_limit_excluded`, `candidate_pool_evicted`,
> `insufficient_ws_data`, `stale_data`,
> `data_unreliable`, `no_anomaly_threshold_cross`,
> `risk_rejected`, `no_completed_tail_label_yet`,
> `unknown` (and `unknown` is a `review` signal — **not**
> a `relax` signal). Allowed outputs (descriptive
> templates only):
> `historical_60d_mover_reference_set`,
> `historical_60d_capture_path_audit`,
> `historical_60d_miss_reason_summary`,
> `historical_60d_first_seen_summary`,
> `historical_60d_capture_recall_summary`,
> `historical_60d_coverage_warning`,
> `historical_60d_export_replay_evidence_template`. All
> outputs are **descriptive only** for human review and
> **MUST NEVER trigger a real trade**, **MUST NEVER**
> modify position size, leverage, stop-loss, target
> price, the Risk Engine, the Execution FSM,
> `symbol_limit`, the candidate pool capacity, anomaly
> thresholds, or Regime weights. Interpretation
> principles (must be read verbatim): captured ≠
> tradable; captured early ≠ strategy profitable; missed
> and not-in-futures-universe ≠ system failure; missed
> and in-eligible-universe IS a coverage warning (for
> human review only); `risk_rejected` ≠ discovery
> failure; `missed` and `unknown` are `review` signals
> (no automatic rule relaxation, no automatic
> `symbol_limit` expansion, no automatic anomaly
> threshold change, no automatic candidate-pool capacity
> change, no automatic Regime weight change); high
> `capture_recall_rate` does NOT authorise live trading;
> low `capture_recall_rate` does NOT authorise parameter
> changes (no "looking at the answer key" — no
> auto-tuning thresholds against the historical
> reference set). Phase 11C.1C-C-B-B-B-D acceptance does
> **NOT** authorise Phase 11C.1C-C-B-B-B-D-A kickoff
> bypassing the standard gate; this docs-only kickoff PR
> #63 scopes the slice in place but does not flip its
> state — a separate docs-only closeout PR will be
> authored after the operator captures B1 / B2 backfill
> audit evidence and will flip the slice to `ACCEPTED`.
> The Risk Engine remains the single trade-decision
> gate. Inherits every Phase 1 / 11C.1B / 11C.1C-A /
> 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A /
> 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C
> / 11C.1C-C-B-B-B-D forbidden item verbatim. Phase 12
> remains **FORBIDDEN**.
>
> **Phase 11C.1C-C-B-B-B-D = ACCEPTED (closed 2026-05-25;
> PR #60 docs-only kickoff merged into `main`; PR #61
> implementation merged into `main`; PR #62 docs-only
> closeout records the operator-VPS 10 min WS paper
> smoke evidence + daily report Mover Capture section +
> `MOVER_CAPTURE_*` event counts + Phase 8.5 export
> bundle + audit result `mover_capture_audit_status=DEGRADED`
> and flips the slice to `ACCEPTED`).** Mover Capture
> Recall & Missed-Tail Coverage Audit v0 / *异动币捕捉
> 召回与漏捕右尾覆盖审计 v0* — fourth child slice under
> the Phase 11C.1C-C-B-B-B parent — paper / report /
> evidence only. The Risk Engine remains the single
> trade-decision gate. **NOT** live trading, **NOT** AI
> Learning, **NOT** automatic parameter optimisation,
> **NOT** reinforcement learning, **NOT** rule
> relaxation based on SAGAUSDT or any small number of
> movers, **NOT** Phase 12.
>
> **Phase 11C.1C-C-B-B-B-C = ACCEPTED (closed 2026-05-25;
> PR #58 docs-only kickoff merged into `main` on
> 2026-05-25; this docs-only closeout PR #59 records the
> operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h
> upper-bound early-stop paper WS evidence and flips the
> slice to `ACCEPTED`).** Long-Window Cohort Stability &
> Sample Sufficiency Protocol v0 / *长窗口 Cohort 稳定性
> 与样本充足协议 v0* — third child slice under the Phase
> 11C.1C-C-B-B-B parent — paper / report / evidence only.
> **NOT** live trading, **NOT** AI Learning, **NOT**
> automatic parameter optimisation, **NOT** reinforcement
> learning, **NOT** rule relaxation based on low samples,
> **NOT** a Risk Engine change, **NOT** an Execution FSM
> change, **NOT** a strategy implementation, **NOT** a
> trading module, **NOT** a new runtime module, **NOT**
> the complete Strategy Validation Lab follow-up, **NOT**
> Phase 12. **B-B-B-C acceptance is acceptance of the
> long-window data collection and sample-sufficiency
> protocol — it does NOT mean any Regime / Cluster has
> proven right-tail advantage yet, and it does NOT mean
> strategy effectiveness is proven.** The long-window
> protocol artefacts (`long_window_run_plan`,
> `sample_sufficiency_checklist`,
> `cohort_stability_checklist`,
> `operator_vps_evidence_template`,
> `export_replay_evidence_template`,
> `closeout_acceptance_template`) and the per-window
> outputs (`paper_alpha_gate_status`,
> `regime_cluster_evidence_status`,
> `insufficient_sample_reasons`, daily-report Paper Alpha
> Gate section, daily-report Regime & Cluster Cohort
> Evidence Pack section, `PAPER_ALPHA_*` and
> `REGIME_CLUSTER_*` event counts, Phase 8.5 export
> bundles) produced by this slice are **descriptive
> labels / artefacts only** for human review and **MUST
> NEVER trigger a real trade**, **MUST NEVER** modify
> position size, leverage, stop-loss, target price, the
> Risk Engine, or the Execution FSM; the Risk Engine
> remains the single trade-decision gate.
>
> **Phase 11C.1C-C-B-B-B-B = ACCEPTED (closed 2026-05-24; PR
> #56 merged into `main`, mergeCommit `1a9abe2`; operator-VPS
> 10 min WS paper smoke evidence + Regime & Cluster Cohort
> Evidence Pack daily report + two `REGIME_CLUSTER_*` event
> counts + Phase 8.5 export bundle accepted via this docs-only
> closeout PR #57).** Regime & Cluster Cohort Evidence Pack v0
> / *Regime 与 Cluster 分组证据包 v0* — second child slice
> under the Phase 11C.1C-C-B-B-B parent — paper / report /
> evidence only. **NOT** live trading, **NOT** AI Learning,
> **NOT** automatic parameter optimisation, **NOT**
> reinforcement learning, **NOT** the complete Strategy
> Validation Lab follow-up, **NOT** Phase 12. The per-cohort
> `status` (`INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING`
> / `EVIDENCE_SIGNAL`) and the top-level
> `regime_cluster_evidence_status` produced by this slice are
> **descriptive labels** for human review and **MUST NEVER
> trigger a real trade**, **MUST NEVER** modify position size,
> leverage, stop-loss, target price, the Risk Engine, or the
> Execution FSM; the Risk Engine remains the single
> trade-decision gate.
>
> **Phase 11C.1C-C-B-B-B-A = ACCEPTED (closed 2026-05-24; PR
> #52 merged into `main`, mergeCommit `f8ba315`; operator-VPS
> 10 min WS paper smoke evidence + Paper Alpha Gate daily
> report + four `PAPER_ALPHA_*` event counts + Phase 8.5
> export bundle accepted via docs-only closeout PR #54).**
> Paper Alpha Gate v0 — first child slice under the Phase
> 11C.1C-C-B-B-B parent — paper / report / evidence only.
> **NOT** live trading, **NOT** AI Learning, **NOT** automatic
> parameter optimisation, **NOT** reinforcement learning,
> **NOT** the complete Strategy Validation Lab follow-up,
> **NOT** Phase 12. The `paper_alpha_gate_status` produced by
> this slice (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) is a
> **descriptive label** for human review and **MUST NEVER
> trigger a real trade**, **MUST NEVER** modify position size,
> leverage, stop-loss, target price, the Risk Engine, or the
> Execution FSM; the Risk Engine remains the single
> trade-decision gate.
>
> **Phase 11C.1C-C-B-B-A = ACCEPTED (closed 2026-05-23; PR #44
> merged into `main`, mergeCommit `3ecfc3b`).** Strategy
> Validation Dataset Builder & Quality Gate v0 on top of the
> Phase 11C.1C-C-B-A `StrategyValidationSample` /
> `StrategyValidationReport` / `ClusterExposureAssessment`
> artefacts. Paper / report only. **NOT** live trading, **NOT**
> AI Learning, **NOT** the complete Strategy Validation Lab
> follow-up (Phase 11C.1C-C-B-B-B), **NOT** automatic parameter
> optimisation, **NOT** Phase 12. The
> ``validation_quality_gate_status`` produced by this slice
> (``pass`` / ``warn`` / ``fail``) is a **descriptive label**
> for human review and **MUST NEVER trigger a real trade**; the
> Risk Engine remains the single trade-decision gate.
>
> Phase 11C.1C-C-B-A — *Strategy Validation Lab v0 & Cluster
> Exposure Control Contracts* — was accepted on 2026-05-23
> (PR #42 merged into `main`, mergeCommit `cc18047`) and is the
> gating predecessor. PR #44 shipped the **first slice** of the
> deeper Phase 11C.1C-C-B-B work: dataset contract + builder +
> quality gate v0 + three new typed events
> (`STRATEGY_VALIDATION_DATASET_BUILT`,
> `STRATEGY_VALIDATION_DATASET_EXPORTED`,
> `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`). The dataset is
> exportable + replayable + auditable. Real WS 10 min smoke was
> NOT required for this PR (the smallest Phase 11C.1C-C-A
> tracking window is 5 min and cannot complete in a 30 s
> dry-run); reserved for Phase 11C.1C-C-B-B-B closeout when
> non-empty datasets are first observable end-to-end.
> `validation_quality_gate_status=fail` is the **expected**
> output for the 30 s dry-run because samples are necessarily
> in-flight in a low-sample window; the field is descriptive
> only and cannot trigger real trading.
>
> **Phase 11C.1C-C-B-B-A = ACCEPTED (closed 2026-05-23; PR #44 merged into `main`, mergeCommit `3ecfc3b`).**
> **Phase 11C.1C-C-B-B-B = NEXT_ALLOWED / NOT_STARTED (parent; unchanged definition — *Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up*; will require its own kickoff PRs (one per child slice), brief, scope, boundary table, forbidden list, and acceptance evidence).**
> **Phase 11C.1C-C-B-B-B-A = ACCEPTED (closed 2026-05-24; PR #52 merged into `main` on 2026-05-24, mergeCommit `f8ba315`; operator-VPS 10 min WS paper smoke evidence + Paper Alpha Gate daily report + four `PAPER_ALPHA_*` event counts + Phase 8.5 export bundle accepted via docs-only closeout PR #54; first child slice under Phase 11C.1C-C-B-B-B — *Paper Alpha Gate v0*; verdict `INCONCLUSIVE` with `paper_alpha_gate_sample_count=20`, `completed_tail_label_count_below_min=0<10`, expected and accepted as a low-completed-label result).**
> **Phase 11C.1C-C-B-B-B-B = ACCEPTED (closed 2026-05-24; PR #56 merged into `main` on 2026-05-24, mergeCommit `1a9abe2`; operator-VPS 10 min WS paper smoke evidence + Regime & Cluster Cohort Evidence Pack daily report + two `REGIME_CLUSTER_*` event counts + Phase 8.5 export bundle accepted via this docs-only closeout PR #57; second child slice under Phase 11C.1C-C-B-B-B — *Regime & Cluster Cohort Evidence Pack v0 / Regime 与 Cluster 分组证据包 v0*; status `INSUFFICIENT_SAMPLE` with `sample_count=14<20` and `completed_tail_label_count=0<10`, expected and accepted as a low-sample / low-completed-tail-label result; the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient. Paper / report / evidence-only — allowed outputs `regime_cohort_summary` / `cluster_cohort_summary` / `score_bucket_summary` / `stage_outcome_summary` / `strategy_mode_outcome_summary` / `regime_cluster_evidence_pack` / `warnings` / `insufficient_sample_reasons` are descriptive labels only, MUST NEVER trigger a real trade, and grant no trade authority. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item verbatim.**
> **Phase 11C.1C-C-B-B-B-C = ACCEPTED (closed 2026-05-25; PR #58 docs-only kickoff merged into `main`; this docs-only closeout PR #59 records the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence and flips the slice to `ACCEPTED`; third child slice under Phase 11C.1C-C-B-B-B — *Long-Window Cohort Stability & Sample Sufficiency Protocol v0 / 长窗口 Cohort 稳定性与样本充足协议 v0*; W1 / W1+ 2 h paper WS run PASSED with `duration_seconds=7200.0`, `uptime≈7238s`, 2 h event counts `PAPER_ALPHA_*` 18/3/3/27 + `REGIME_CLUSTER_*` 10/2, daily report `regime_cluster_sample_count=189`, `completed_tail_label_count=0`, status `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` accepted as valid low-completed-label evidence (not runtime failure), 2 h export `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip` `manifest_event_count=23001` `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`; W2 4 h paper WS run PASSED with configured `duration_seconds=14400.0` actual runtime ≈ `14417s`, `iterations=237`, `chains_emitted=704`, `ws_messages_received=1324423`, `radar_candidates_seen=152221`, `liquidation_events_seen=4076`, 4 h event counts `PAPER_ALPHA_*` 24/4/4/36 + `REGIME_CLUSTER_*` 15/3, `paper_alpha_gate_status=INCONCLUSIVE` `sample_count=164` reason `completed_tail_label_count_below_min=2<10`, `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` `completed_tail_label_count=2` (progress from 0 to 2 completed labels still below 10-label threshold — `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct result, does NOT indicate runtime failure, does NOT authorise rule relaxation), 4 h export `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip` `manifest_event_count=61546` `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`; W3 24 h upper-bound run PASSED with watcher early-stop at `total_elapsed_seconds=900`, `final_tail_labels_since_start=20>=10`, `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`, 24 h full runtime NOT NEEDED — proves the B-B-B-C sample sufficiency protocol can save runtime while preserving evidence; W3 export PASSED with latest export zip after W3 early-stop `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip` generated 2026-05-25 12:41 UTC `manifest_event_count=62761` `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3 export-range event counts `TAIL_LABEL_ASSIGNED=495`, `LABEL_WINDOW_COMPLETED=495`, `STRATEGY_VALIDATION_SAMPLE_CREATED=397`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`, `PAPER_ALPHA_GATE_EVALUATED=5`, `PAPER_ALPHA_RULE_EVALUATED=45`, `PAPER_ALPHA_COHORT_EVALUATED=30`, `PAPER_ALPHA_REPORT_GENERATED=5` (clarification: `final_tail_labels_since_start=20` is the watcher early-stop condition for the 900 s live window; `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range event count — both valid, different scopes); B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol, does NOT mean any Regime / Cluster has proven right-tail advantage yet, does NOT authorise live trading, does NOT authorise rule relaxation, does NOT authorise automatic parameter optimisation, does NOT authorise AI Learning, does NOT authorise changing the Risk Engine or the Execution FSM, does NOT authorise Phase 12. Paper / report / evidence-only; grants no trade authority. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim).**
> **Phase 11C.1C-C-B-B-B-D = ACCEPTED (closed 2026-05-25; PR #60 docs-only kickoff merged into `main`; PR #61 implementation merged into `main`; this docs-only closeout PR #62 records the operator-VPS 10 min WS paper smoke evidence + daily report Mover Capture section + `MOVER_CAPTURE_*` event counts + Phase 8.5 export bundle + audit result `mover_capture_audit_status=DEGRADED` and flips the slice to `ACCEPTED`; fourth child slice under Phase 11C.1C-C-B-B-B — *Mover Capture Recall & Missed-Tail Coverage Audit v0 / 异动币捕捉召回与漏捕右尾覆盖审计 v0*; operator-VPS 10 min WS paper smoke PASSED with `duration_seconds=600.0`, `dry_run=false`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `risk_approved=0`, `HTTP 429=0`, `HTTP 418=0`, `ws_reconnect_count=0`, `ws_stale_count=0`, `live_trading_enabled=False`, `exchange_live_order_enabled=False`, `llm_enabled=False`, `right_tail_enabled=False`; Mover Capture event counts `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`, `MOVER_CAPTURE_PATH_AUDITED=20`; daily report contains `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0` section; audit result `mover_capture_audit_status=DEGRADED`, `top_mover_count=20`, `captured_top_mover_count=4`, `missed_top_mover_count=16`, `capture_recall_rate=0.2000`, `data_unreliable_count=4`, `risk_rejected_mover_count=4`; `DEGRADED` is the **expected and accepted** audit output for this smoke window because the audit layer successfully surfaced coverage weakness / uncertainty — `DEGRADED` is NOT a runtime failure, captured-but-risk-rejected does NOT mean discovery failure, missed-with-unknown reason is a `review` signal not permission to loosen rules, low capture recall does NOT authorise automatic `symbol_limit` expansion / anomaly threshold changes / candidate pool capacity changes / Regime weight changes / Risk Engine changes, and high capture recall would also NOT authorise live trading; Phase 8.5 export bundle: `data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip`, `manifest_event_count=63968`, `redaction_applied=True`, `events.jsonl` exists, export contains `MOVER_CAPTURE_*` events, `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`, `MOVER_CAPTURE_PATH_AUDITED=20`, `EXPORT_MOVER_CAPTURE_RECALL_CHECK=PASS`; export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. Paper / report / evidence-only — allowed outputs (`top_mover_capture_summary` / `captured_mover_evidence` / `missed_mover_audit` / `symbol_universe_exclusion_summary` / `candidate_eviction_summary` / `risk_rejection_summary` / `first_seen_latency_summary` / `capture_recall_rate` / `missed_tail_candidate_list` / `coverage_warning` / `insufficient_coverage_reasons`) are descriptive labels only, MUST NEVER trigger a real trade, and grant no trade authority. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C forbidden item verbatim).**
> **Phase 11C.1C-C-B-B-B-D-A = NEXT_ALLOWED / NOT_STARTED — *Historical 60D Mover Coverage Backfill Audit v0 / 历史 60 天异动币覆盖回填审计 v0*.** Next allowed child slice under Phase 11C.1C-C-B-B-B (or under the B-B-B-D parent track), opened by Phase 11C.1C-C-B-B-B-D acceptance via this docs-only closeout PR #62. Discovery-layer coverage backfill audit only — **not** complete strategy blind testing, **not** Phase 12 pre-live validation. Rationale: PR #61 proved the audit layer can run in real paper mode and export `MOVER_CAPTURE_*` evidence; however, a 10 min live window may be too short and market-dependent (e.g. a real mover like SAGAUSDT can be missed or classified as `unknown` in a short audit window), and waiting several quiet days may waste time if the market is calm. Therefore the next slice evaluates discovery-layer coverage over the past 60 days. D-A is allowed to answer: which eligible movers did AMA-RT detect over the past 60 days; when did AMA-RT first detect them; which capture-path layer did they reach; which movers were missed; why were they missed; and which misses are universe coverage issues versus discovery-layer warnings. D-A must NOT answer: whether the strategy is profitable; whether live trading is allowed; whether leverage / position / stops should change; whether `symbol_limit` should auto-expand; whether anomaly thresholds should auto-change; whether candidate pool capacity should auto-change; whether Phase 12 can begin. D-A must require: a 60D top mover reference set; an eligible USDT-perpetual universe filter; `first_seen_time_utc` for every captured mover; `first_seen_event_type`; `first_seen_latency_seconds` where a mover reference timestamp exists; `capture_path_depth`; per-mover status (`captured` / `partially_captured` / `missed` / `excluded`); miss-reason classification; report / export / replay evidence. Historical 30D+ full blind replay / complete strategy walk-forward validation remains reserved until small-money live trading prep and is **not** in scope for D-A. Phase 11C.1C-C-B-B-B-D acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A kickoff bypassing the standard gate; Phase 11C.1C-C-B-B-B-D-A will require its own kickoff PR, brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C / 11C.1C-C-B-B-B-D forbidden item verbatim. Paper / report / evidence-only; grants no trade authority.**
>
> *(Phase 11C.1C-C-B-B-B-D pre-closeout history; superseded by the `ACCEPTED` block above. Recorded for audit trail.)*
> ~~Phase 11C.1C-C-B-B-B-D = NEXT_ALLOWED / NOT_STARTED — *Mover Capture Recall & Missed-Tail Coverage Audit v0 / 异动币捕捉召回与漏捕右尾覆盖审计 v0* (defined in place by docs-only kickoff PR #60; this PR scopes the slice; it does not flip its state).~~ Fourth child slice under the Phase 11C.1C-C-B-B-B parent. Paper-only / report-only / evidence-only coverage audit protocol that asks (1) whether real market movers got captured by the system, (2) at which discovery layer (`MARKET_SNAPSHOT` / `PRE_ANOMALY_DETECTED` / `ANOMALY_DETECTED` / `MARKET_REGIME_ASSESSED` / `CANDIDATE_STAGE_CLASSIFIED` / `OPPORTUNITY_SCORED` / `STRATEGY_MODE_SELECTED` / `CLUSTER_CONTEXT_ATTACHED` / `LABEL_QUEUE_ENQUEUED` / `LABEL_TRACKING_STARTED` / `LABEL_WINDOW_COMPLETED` / `TAIL_LABEL_ASSIGNED` / `STRATEGY_VALIDATION_SAMPLE_CREATED`), (3) if missed, why (taxonomy: `not_in_futures_universe` / `not_in_exchange_info` / `not_usdt_perpetual` / `symbol_limit_excluded` / `candidate_pool_capacity_evicted` / `score_too_low` / `liquidity_insufficient` / `data_stale_or_degraded_or_unreliable` / `risk_rejected` / `no_completed_tail_label_yet`), (4) whether top movers were captured early enough (`first_seen_latency_seconds`), (5) whether captured movers proceeded into the label / validation pipeline, (6) whether missed movers are a system-coverage problem or a market / exchange-coverage problem, and (7) whether captured-but-rejected movers were rejected for sound conservative reasons. Allowed outputs (descriptive only): `top_mover_capture_summary`, `captured_mover_evidence`, `missed_mover_audit`, `symbol_universe_exclusion_summary`, `candidate_eviction_summary`, `risk_rejection_summary`, `first_seen_latency_summary`, `capture_recall_rate`, `missed_tail_candidate_list`, `coverage_warning`, `insufficient_coverage_reasons`. Trigger context: B-B-B-C proved long-window paper data collection works end-to-end; the next question is whether the discovery layer covers real market movers — codifying "operator looks at gainer board vs. did the system see it" as a coverage audit instead of relying on ad-hoc human screenshots. Concrete trigger: SAGAUSDT showed an obvious move on Binance's public 24 h gainer board; the system already captured SAGAUSDT end-to-end (`PRE_ANOMALY_DETECTED` → `ANOMALY_DETECTED` → `MARKET_REGIME_ASSESSED` → `CANDIDATE_STAGE_CLASSIFIED` → `OPPORTUNITY_SCORED` → `STRATEGY_MODE_SELECTED` → `CLUSTER_CONTEXT_ATTACHED` → `LABEL_QUEUE_ENQUEUED` → `LABEL_TRACKING_STARTED` → `TAIL_LABEL_ASSIGNED` → `STRATEGY_VALIDATION_SAMPLE_CREATED`), but a single coin proves nothing — the audit institutionalises this comparison. Allowed input sources (read-only; reuse existing surfaces): Binance public 24 h ticker / public market data, `EventRepository`, daily report, Phase 8.5 export / Phase 10A replay, `StrategyValidationDataset`, `PaperAlphaGateReport`, `RegimeClusterEvidencePack`, `SymbolUniverse` / `exchangeInfo`-as-truth catalogue, candidate pool logs / capacity-eviction evidence (where available). Audit objects: top gainers / top movers in eligible USDT-perpetual universe, detected anomalies, pre-anomaly candidates, label-tracked candidates, validation samples, risk-rejected movers, movers excluded because not in the current tradable universe. Key metrics (descriptive only): `top_mover_count`, `captured_top_mover_count`, `missed_top_mover_count`, `capture_recall_rate`, `anomaly_detected_rate`, `label_tracking_rate`, `tail_label_assigned_rate`, `strategy_validation_sample_rate`, `risk_rejected_mover_count`, `not_in_universe_count`, `capacity_evicted_count`, `data_unreliable_count`, `median_first_seen_latency_seconds`. Interpretation principles (must be read verbatim): captured-but-rejected ≠ failure; missed-but-not-in-universe ≠ failure; coverage warning is only raised when the mover is in the eligible universe AND shows clear right-tail behaviour AND was missed for a system-correctable reason; a single mover proves nothing (SAGAUSDT specifically does not authorise rule relaxation); capture audit ≠ trading-profit evidence; low coverage is a `review` outcome, not a `relax` outcome; high coverage does not authorise live trading; single-coin / "妖币" reframing is forbidden. **NOT** a new strategy. **NOT** a trading module. **NOT** AI Learning. **NOT** automatic parameter optimisation. **NOT** Historical 30D+ Blind Replay / Walk-forward Validation (that gate is reserved for a Phase 12 candidate review and is explicitly out of scope here; it belongs after the major paper modules and the paper validation chain are complete, before small-money live trading). **NOT** a continued widening of system complexity. **NOT** Phase 12. Phase 11C.1C-C-B-B-B-C acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard gate; this docs-only kickoff PR scopes the slice in place but does not flip its state — a separate docs-only closeout PR will be authored after the operator captures A1 / A2 audit evidence and will flip the slice to `ACCEPTED`. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C forbidden item verbatim. Paper / report / evidence-only; grants no trade authority.**
> *(Phase 11C.1C-C-B-B-B-D IN_REVIEW history; superseded by the `ACCEPTED` block above. Recorded for audit trail.)*
> ~~Phase 11C.1C-C-B-B-B-D = IN_REVIEW (implementation PR #61).~~ Implementation of the Mover Capture Recall & Missed-Tail Coverage Audit v0 layer landed in `app/adaptive/mover_capture_recall_audit.py` (data models + descriptive status/miss-reason taxonomies + deterministic pure functions + thin `MoverCaptureRecallAuditRuntime` orchestrator), the runner (`scripts/run_public_market_paper.py`) wires the audit into the shutdown path, and the daily report (`app/paper_run/daily_report.py`) renders a new `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0` section with every brief-mandated field. Two new typed events `MOVER_CAPTURE_RECALL_AUDIT_GENERATED` / `MOVER_CAPTURE_PATH_AUDITED` added to `app/core/events.py`. The IN_REVIEW state has now been **superseded** by the docs-only closeout PR #62 above which records the operator-VPS evidence and flips the slice to `ACCEPTED`. Phase 12 remains **FORBIDDEN**.
> **Phase 11C.1C-C-B-A = ACCEPTED (closed 2026-05-23; PR #42 merged into `main`, mergeCommit `cc18047`).**
> **Phase 11C.1C-C-A = ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`).**
> **Phase 11C.1C-B = ACCEPTED (closed 2026-05-22; PR #38 merged into `main`).**
> **Phase 11C.1C-A = ACCEPTED (closed 2026-05-22; PR #36 merged via PR #37 docs closeout).**
> **Phase 11C.1B = ACCEPTED (closed 2026-05-22).**
> **Phase 12 (real money / live trading) = FORBIDDEN.**
> **We are still in paper mode.**
>
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-A does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-A does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-A does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-A does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-A does NOT authorise Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-A does NOT authorise Phase 12.**
> **`validation_quality_gate_status` cannot trigger real trading.**
> **The Risk Engine remains the single trade-decision gate.**
>
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise Phase 12.**
> **Paper Alpha Gate verdicts remain paper-only / report-only / evidence-only.**
> **Paper Alpha Gate verdicts cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **`paper_alpha_gate_status=INCONCLUSIVE` is an expected and accepted result for this smoke window because `completed_tail_label_count=0<10`.** This means the Paper Alpha Gate correctly refused to overfit or force a `PASS` when completed tail labels were insufficient. **`INCONCLUSIVE` does NOT mean runtime failure. `INCONCLUSIVE` does NOT authorise strategy changes. `INCONCLUSIVE` does NOT authorise live trading. `INCONCLUSIVE` does NOT authorise Phase 12.**
>
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 12.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only.**
> **Regime & Cluster Evidence Pack outputs cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` is an expected and accepted result for this smoke window because `sample_count=14<20` and `completed_tail_label_count=0<10`.** This means the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient. **`INSUFFICIENT_SAMPLE` does NOT mean runtime failure. `INSUFFICIENT_SAMPLE` does NOT authorise strategy changes. `INSUFFICIENT_SAMPLE` does NOT authorise rule relaxation. `INSUFFICIENT_SAMPLE` does NOT authorise live trading. `INSUFFICIENT_SAMPLE` does NOT authorise Phase 12.**
>
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise Phase 12.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise rule relaxation based on low samples.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise changing the Risk Engine or the Execution FSM.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard gate.**
> **B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol — it does NOT mean any Regime / Cluster has proven right-tail advantage yet, and it does NOT mean strategy effectiveness is proven.**
> **Long-window protocol outputs (`long_window_run_plan`, `sample_sufficiency_checklist`, `cohort_stability_checklist`, `operator_vps_evidence_template`, `export_replay_evidence_template`, `closeout_acceptance_template`) and per-window outputs (`paper_alpha_gate_status`, `regime_cluster_evidence_status`, `insufficient_sample_reasons`, daily-report Paper Alpha Gate section, daily-report Regime & Cluster Cohort Evidence Pack section, `PAPER_ALPHA_*` and `REGIME_CLUSTER_*` event counts, Phase 8.5 export bundles) remain paper-only / report-only / evidence-only.**
> **Long-window protocol outputs and per-window outputs cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **The W2 4 h window's progress from `completed_tail_label_count=0` to `completed_tail_label_count=2` is real progress but still below the 10-label sufficiency threshold; therefore `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct W2 result. This does NOT indicate runtime failure. This does NOT authorise rule relaxation.**
> **The W3 24 h upper-bound watcher early-stop at `total_elapsed_seconds=900`, `final_tail_labels_since_start=20>=10` proves the B-B-B-C sample sufficiency protocol can save runtime while preserving evidence; the full 24 h runtime was NOT NEEDED. This does NOT authorise live trading. This does NOT authorise Phase 12.**
>
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise Phase 12.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise rule relaxation based on SAGAUSDT or any small number of movers.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise changing the Risk Engine or the Execution FSM.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise automatic `symbol_limit` expansion.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise automatic anomaly threshold changes.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise automatic candidate pool capacity changes.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise automatic Regime weight changes.**
> **Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise Phase 11C.1C-C-B-B-B-D-A kickoff bypassing the standard gate.**
> **Mover Capture Recall & Missed-Tail Coverage Audit v0 outputs (`top_mover_capture_summary` / `captured_mover_evidence` / `missed_mover_audit` / `symbol_universe_exclusion_summary` / `candidate_eviction_summary` / `risk_rejection_summary` / `first_seen_latency_summary` / `capture_recall_rate` / `missed_tail_candidate_list` / `coverage_warning` / `insufficient_coverage_reasons`) remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **`mover_capture_audit_status=DEGRADED` is an expected and accepted audit output for this smoke window — it means the audit layer successfully surfaced coverage weakness / uncertainty.** **`DEGRADED` does NOT mean runtime failure. captured-but-risk-rejected does NOT mean discovery failure. missed-with-unknown reason is a `review` signal, not permission to loosen rules. Low capture recall does NOT authorise automatic `symbol_limit` expansion / anomaly threshold changes / candidate pool capacity changes / Regime weight changes / Risk Engine changes. High capture recall would also NOT authorise live trading.**
>
> PR #42 — the Phase 11C.1C-C-B-A *Strategy Validation Lab v0
> & Cluster Exposure Control Contracts* branch
> (`feature/phase-11c1c-c-b-strategy-validation-cluster-control`)
> — has **merged into `main`** (mergeCommit `cc18047`). The
> branch shipped the data contracts
> (`StrategyValidationSample`, `StrategyValidationReport`,
> `ClusterExposureAssessment`, …), the pure aggregators
> (`build_strategy_validation_report`, `aggregate_by_strategy_mode`,
> `aggregate_by_candidate_stage`,
> `aggregate_by_opportunity_score_bucket`,
> `aggregate_by_early_tail_score_bucket`,
> `aggregate_tail_label_distribution`,
> `evaluate_cluster_leader_performance`,
> `assess_cluster_exposure`), the runtime
> (`StrategyValidationRuntime`), the seven new typed events
> (`STRATEGY_VALIDATION_SAMPLE_CREATED` /
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_EXPOSURE_ASSESSED` /
> `CLUSTER_LEADER_VALIDATED`), the daily-report section, and
> the wiring through `WSRadarChainDriver` +
> `scripts/run_public_market_paper.py`. **Phase 11C.1C-C-B-A
> is paper-only**: the `suggested_cluster_action` field on every
> `ClusterExposureAssessment` is one of `leader_only` /
> `observe_followers` / `reject_cluster` / `no_action` and
> **MUST NEVER trigger a real trade**; the Risk Engine remains
> the single trade-decision gate. Phase 11C.1C-C-B-A acceptance
> does **NOT** authorise live trading, API keys, private
> endpoints, DeepSeek trade decisions, real Telegram outbound,
> Phase 11C.1C-C-B-B kickoff bypassing the standard gate, or
> Phase 12. **Tests:** 25/25 brief-mandated tests PASS,
> 312/312 phase11c\_ tests PASS, 2286/2286 full pytest PASS on
> the PR branch (no regression vs. the post-PR-#41 main 2261
> baseline). The 30 s dry-run is **contract-only** (the
> smallest Phase 11C.1C-C-A tracking window is 5 min; a 30 s
> run cannot complete a primary window). The
> **operator-VPS 10 min real public WS smoke PASSED** with
> `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`,
> `ws_real_transport=true`,
> `ws_messages_received=76324`, `ws_chains_emitted=27`,
> `learning_ready_attached=27`, `snapshots_emitted=27`,
> `ingestion_errors=0`,
> `STRATEGY_VALIDATION_SAMPLE_CREATED=24`,
> `STRATEGY_VALIDATION_REPORT_GENERATED=1`,
> `STRATEGY_MODE_VALIDATED=4`,
> `CANDIDATE_STAGE_VALIDATED=5`,
> `SCORE_BUCKET_VALIDATED=8`,
> `CLUSTER_EXPOSURE_ASSESSED=1`,
> `CLUSTER_LEADER_VALIDATED=1` (authoritative SQLite query;
> see daily-report counter snapshot caveat below), non-empty
> daily-report cohort lines, `HTTP 429 count=0`,
> `HTTP 418 count=0`, `rate_limit_ban=False`,
> `ws_reconnect_count=0`, `ws_stale_count=0`,
> `ws_currently_stale=False`, and Phase 1 safety lock
> unchanged. PR #42 has **merged into `main`** (mergeCommit
> `cc18047`, merged 2026-05-23 UTC); the smoke evidence above
> was accepted; this docs-only closeout PR therefore records
> Phase 11C.1C-C-B-A as **ACCEPTED**. Phase 11C.1C-C-B-B is
> now **NEXT_ALLOWED / NOT_STARTED**: Phase 11C.1C-C-B-A
> acceptance does **NOT** authorise Phase 11C.1C-C-B-B
> kickoff bypassing the standard gate; Phase 11C.1C-C-B-B
> will require its own kickoff PR, brief, scope, boundary
> table, forbidden list, and acceptance evidence. Phase 12
> remains **FORBIDDEN**.
>
> *Daily-report counter snapshot caveat.* The daily report's
> top event-count lines may show
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_*` counts as **0**
> because those event counters appear to be snapshotted
> **before** shutdown flush. The authoritative event
> repository SQLite query confirms those events were
> emitted; the daily report **section itself** rendered the
> Strategy Validation cohorts non-empty and correctly. This
> is a daily-report instrumentation nuance and does **not**
> invalidate the smoke; a future polish can move the counter
> snapshot after the shutdown flush, but it is **not** in
> scope for Phase 11C.1C-C-B-A.

The Phase 1 safety lock held end-to-end across the Phase 11C.1C-B
acceptance evidence runs and remains in force on `main`:
`mode=paper`, `live_trading=False`, `right_tail=False`,
`llm=False`, `exchange_live_orders=False`,
`telegram_outbound_enabled=False`, `binance_private_api_enabled=False`.
No Binance API key, no Binance API secret, no signed endpoint, no
private WebSocket, no `listenKey`, no DeepSeek trade decision, no
real Telegram outbound, no Phase 12. Phase 11C.1C-B is **paper /
virtual** only: the new `early_tail_score` and `runtime_calibration`
block are paper / descriptive fields; the Risk Engine remains the
single trade-decision gate.

| Date (UTC) | Phase    | Tag                                        | State   | Evidence                                                |
| ---------- | -------- | ------------------------------------------ | ------- | ------------------------------------------------------- |
| 2026-05-23 | Phase 11C.1C-C-B-B-B | Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up (parent; unchanged definition; reserved for the deeper Phase 11C.1C-C-B-B follow-up after Phase 11C.1C-C-B-B-A is ACCEPTED) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-A is now **ACCEPTED** (PR #44 merged into `main`, mergeCommit `3ecfc3b`), so Phase 11C.1C-C-B-B-B is now **NEXT_ALLOWED**; no implementation has started. The parent phase is **not** renamed by Paper Alpha Gate v0; the Paper Alpha Gate v0 is one *child slice* under this parent (Phase 11C.1C-C-B-B-B-A), not the parent itself. Phase 11C.1C-C-B-B-A acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate; Phase 11C.1C-C-B-B-B will require its own kickoff PRs (one per child slice), brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-A | Paper Alpha Gate v0 (paper / report-only first child slice under Phase 11C.1C-C-B-B-B; implementation + closeout) | **ACCEPTED (closed 2026-05-24; PR #52 merged into `main` on 2026-05-24, mergeCommit `f8ba315`; this docs-only closeout PR #54 records the operator-VPS evidence)** — branch (implementation) `feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`. Implementation PR shipped `app/adaptive/paper_alpha_gate.py` (pure-function module: `PaperAlphaGateStatus`, `PaperAlphaGateRule`, `PaperAlphaGateRuleResult`, `PaperAlphaGateCohortResult`, `PaperAlphaGateInput`, `PaperAlphaGateReport`, plus the nine pure functions `build_paper_alpha_gate_input` / `evaluate_paper_alpha_gate` / `evaluate_strategy_mode_alpha` / `evaluate_candidate_stage_alpha` / `evaluate_score_bucket_alpha` / `evaluate_cluster_alpha` / `build_paper_alpha_gate_report` / `export_paper_alpha_gate_payload` / `load_paper_alpha_gate_payload`); four new typed events (`PAPER_ALPHA_GATE_EVALUATED`, `PAPER_ALPHA_RULE_EVALUATED`, `PAPER_ALPHA_COHORT_EVALUATED`, `PAPER_ALPHA_REPORT_GENERATED`); `StrategyValidationRuntime` extended to evaluate the gate on the same flush as the dataset / quality-gate emission; Phase 11B daily-report section. Schema version `phase_11c_1c_c_b_b_b_a.paper_alpha_gate.v1`. The verdict (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) is **descriptive only** for human review and **MUST NEVER trigger a real trade**, **MUST NEVER** modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM. **Operator-VPS 10 min WS paper smoke PASSED**: `duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`. Daily report contains `"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"` with `paper_alpha_gate_status=INCONCLUSIVE`, `paper_alpha_gate_sample_count=20`, reason `completed_tail_label_count_below_min=0<10`. `PAPER_ALPHA_GATE_EVALUATED=1`, `PAPER_ALPHA_RULE_EVALUATED=9`, `PAPER_ALPHA_COHORT_EVALUATED=6`, `PAPER_ALPHA_REPORT_GENERATED=1`. Phase 8.5 export bundle generated at `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip` (`export_test_data=OK`, `manifest_event_count=1572`, `redaction_applied=True`, `events.jsonl` exists, export contains `PAPER_ALPHA_*` events, `EXPORT_PAPER_ALPHA_GATE_CHECK=PASS`); export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. `paper_alpha_gate_status=INCONCLUSIVE` is the **expected and accepted** result for this smoke window because `completed_tail_label_count=0<10` — the Paper Alpha Gate correctly refused to overfit or force a `PASS` when completed tail labels were insufficient; `INCONCLUSIVE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise live trading, does NOT authorise Phase 12. Safety flags unchanged across the operator-VPS run (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`; `docs/PR52_DESCRIPTION.md`; `docs/PR54_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_b_a_paper_alpha_gate.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-A (ACCEPTED)" + §"Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-A (kickoff) | Paper Alpha Gate v0 (docs-only kickoff / scope alignment, superseded by the PR #52 implementation; closed via PR #54 docs-only closeout) | **SUPERSEDED by PR #52 (now ACCEPTED via this docs-only closeout PR #54).** PR #51 (the docs-only kickoff) merged into `main` on 2026-05-24 and recorded the parent / child relationship + boundary table + forbidden list. The ACCEPTED row above tracks the implementation PR (PR #52, merged 2026-05-24, mergeCommit `f8ba315`) and this docs-only closeout PR (PR #54). | `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`; `docs/PR51_DESCRIPTION.md`; `docs/PR54_DESCRIPTION.md` |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-B (closeout) | Regime & Cluster Cohort Evidence Pack v0 docs-only closeout / acceptance flip (paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B; closeout via PR #57) | **ACCEPTED (closed 2026-05-24; PR #56 merged into `main` on 2026-05-24, mergeCommit `1a9abe2`; this docs-only closeout PR #57 records the operator-VPS paper evidence and flips the slice to `ACCEPTED`)**. **Operator-VPS 10 min WS paper smoke PASSED**: `duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`. Daily report contains `"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"` with `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`, `sample_count=14`, `completed_tail_label_count=0`, `insufficient_sample_reasons=[sample_count_below_min=14<20, completed_tail_label_count_below_min=0<10]`. `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`. Phase 8.5 export bundle generated at `data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip` (`export_test_data=OK`, `manifest_event_count=3151`, `redaction_applied=True`, `events.jsonl` exists, export contains `REGIME_CLUSTER_*` events, `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK=PASS`); export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` is the **expected and accepted** result for this smoke window because `sample_count=14<20` and `completed_tail_label_count=0<10` — the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient; `INSUFFICIENT_SAMPLE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise rule relaxation, does NOT authorise live trading, does NOT authorise Phase 12. Safety flags unchanged across the operator-VPS run (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** a strategy implementation, **NOT** a trading module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`; `docs/PR56_DESCRIPTION.md`; `docs/PR57_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" + §"Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-D-A (kickoff) | Historical 60D Mover Coverage Backfill Audit v0 / *历史 60 天异动币覆盖回填审计 v0* (docs / evidence-template-only next allowed child slice under Phase 11C.1C-C-B-B-B; docs-only kickoff via PR #63) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-B-D is `ACCEPTED` (PR #60 docs-only kickoff + PR #61 implementation + PR #62 docs-only closeout merged into `main`), so Phase 11C.1C-C-B-B-B-D-A is **NEXT_ALLOWED**. This docs-only kickoff PR #63 **defines** the slice in place — name, scope, boundary, allowed outputs, forbidden list, eight audit questions, 60D top-mover reference set fields, per-captured-mover audit row fields, miss-reason taxonomy, allowed input sources, audit objects, audit cadence (B1 / B2 with B3+ reserved; operator-driven, **not** auto-scheduled), interpretation principles, safety boundary, and acceptance-gate placeholder — but **does NOT flip its state**. Discovery-layer historical coverage audit only. **Not** complete strategy blind testing. **Not** Phase 12 pre-live validation. **Not** Historical 30D+ / 60D *complete strategy* blind replay / walk-forward validation (that gate remains reserved until small-money live trading prep and is **out of scope** for D-A). **Not** the Phase 11C.1C-C-B-B-B-D-A *implementation* (out of scope; will be a separate PR if needed). **Not** the Phase 11C.1C-C-B-B-B-D-A *closeout* (out of scope; will be a separate docs-only closeout PR after the operator captures B1 / B2 backfill audit evidence). **Audit answers eight questions and only these eight:** (1) over the past 60 days, did AMA-RT discover the eligible USDT perpetual movers; (2) if discovered, when was the first detection (`first_seen_time_utc`); (3) what was the first detection event (`first_seen_event_type`); (4) how deep did the capture path go (`capture_path_depth`, `reached_anomaly`, `reached_label_queue`, `reached_tail_label`, `reached_strategy_validation_sample`); (5) if not discovered, why (`miss_reason` from the fixed taxonomy); (6) is each missed mover a universe-coverage issue or a discovery-layer warning; (7) which captured movers were rejected by the Risk Engine (`risk_rejected = true`; conservative paper outcome, **not** discovery failure); (8) which captured movers only made it partway (`status = partially_captured`). **60D top-mover reference set fields:** `reference_window_start_utc`, `reference_window_end_utc`, `top_mover_symbol`, `top_mover_rank`, `max_window_gain`, `max_24h_gain`, `reference_timestamp_utc`, `eligible_usdt_perpetual` (true / false). **Per-captured-mover audit row fields:** `top_mover_symbol`, `mover_window_start_utc`, `mover_window_end_utc`, `top_mover_rank`, `max_window_gain`, `max_24h_gain`, `eligible_usdt_perpetual`, `system_captured`, `first_seen_time_utc`, `first_seen_event_type`, `first_seen_latency_seconds` where a mover reference timestamp exists, `capture_path_depth`, `reached_anomaly`, `reached_label_queue`, `reached_tail_label`, `reached_strategy_validation_sample`, `risk_rejected`, `status` (`captured` / `partially_captured` / `missed` / `excluded`), `miss_reason`. **Fixed `miss_reason` taxonomy:** `not_in_futures_universe`, `symbol_not_in_exchange_info`, `not_usdt_perpetual`, `missing_historical_reference_data`, `missing_event_history`, `below_liquidity_threshold`, `symbol_limit_excluded`, `candidate_pool_evicted`, `insufficient_ws_data`, `stale_data`, `data_unreliable`, `no_anomaly_threshold_cross`, `risk_rejected`, `no_completed_tail_label_yet`, `unknown` (`unknown` is a `review` signal — **not** a `relax` signal). **Allowed outputs (descriptive templates only):** `historical_60d_mover_reference_set`, `historical_60d_capture_path_audit`, `historical_60d_miss_reason_summary`, `historical_60d_first_seen_summary`, `historical_60d_capture_recall_summary`, `historical_60d_coverage_warning`, `historical_60d_export_replay_evidence_template`. **Allowed input sources (read-only; reuse existing surfaces):** Binance public 24 h ticker / public klines / public market data, `EventRepository` / events.db, daily report, Phase 8.5 export bundle / Phase 10A replay bundle over the 60D window, `StrategyValidationDataset`, `PaperAlphaGateReport`, `RegimeClusterEvidencePack`, `MoverCaptureRecallAuditReport`, `SymbolUniverse` / `exchangeInfo`-as-truth catalogue, candidate pool logs / capacity-eviction evidence. **Interpretation principles (verbatim):** captured ≠ tradable; captured early ≠ strategy profitable; missed and not-in-futures-universe ≠ system failure; missed and in-eligible-universe IS a coverage warning (for human review only); `risk_rejected` ≠ discovery failure; `missed` and `unknown` are `review` signals (no automatic rule relaxation, no automatic `symbol_limit` expansion, no automatic anomaly threshold change, no automatic candidate-pool capacity change, no automatic Regime weight change); high `capture_recall_rate` does NOT authorise live trading; low `capture_recall_rate` does NOT authorise parameter changes (no "looking at the answer key" — no auto-tuning thresholds against the historical reference set). **Slice-specific forbidden items recorded verbatim:** cannot trigger real trades / modify position size / modify leverage / modify stops / modify targets / modify Risk Engine / modify Execution FSM; cannot let AI decide direction or sizing or leverage or stops or targets or execution; cannot auto-optimise parameters; cannot auto-relax rules; cannot auto-expand `symbol_limit`; cannot auto-change anomaly thresholds; cannot auto-change candidate-pool capacity; cannot auto-change Regime weights; cannot use historical results to retro-tune any threshold; cannot peek at future and revise rules; cannot treat high recall as live-trade authorisation; cannot treat low recall as rule-relaxation authorisation; cannot replace Mover Capture Recall & Missed-Tail Coverage Audit v0 `DEGRADED` rule with a relaxed rule; cannot replace Regime & Cluster Evidence Pack v0 `INSUFFICIENT_SAMPLE` rule with a relaxed rule; cannot replace Paper Alpha Gate v0 `INCONCLUSIVE` rule with a relaxed rule; cannot replace Long-Window Cohort Stability & Sample Sufficiency Protocol v0 cadence; cannot stand in for Historical 30D+ / 60D *complete strategy* blind replay / walk-forward validation; cannot enter Phase 12. Phase 11C.1C-C-B-B-B-D acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A kickoff bypassing the standard gate; this kickoff PR #63 scopes the slice in place but does not flip its state — a separate docs-only closeout PR will be authored after the operator captures B1 / B2 backfill audit evidence and will flip the slice to `ACCEPTED`. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C / 11C.1C-C-B-B-B-D forbidden item verbatim. Paper / report / evidence-only; grants no trade authority. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md`; `docs/PR63_DESCRIPTION.md`; `docs/PROJECT_STATUS.md`; `docs/PHASE_GATE.md`; `docs/CHANGELOG.md` |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-D-A (placeholder; superseded by PR #63 kickoff above) | Historical 60D Mover Coverage Backfill Audit v0 / *历史 60 天异动币覆盖回填审计 v0* (paper / report / evidence-only next child slice opened by Phase 11C.1C-C-B-B-B-D acceptance via PR #62) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-B-D is now `ACCEPTED` (PR #60 docs-only kickoff + PR #61 implementation + PR #62 docs-only closeout merged into `main`), so Phase 11C.1C-C-B-B-B-D-A is **NEXT_ALLOWED**. **Not** complete strategy blind testing. **Not** Phase 12 pre-live validation. **Not** Historical 30D+ full blind replay / complete strategy walk-forward validation (that gate remains reserved until small-money live trading prep and is **out of scope** for D-A). Discovery-layer coverage backfill audit only. **Rationale:** PR #61 proved the audit layer can run in real paper mode and export `MOVER_CAPTURE_*` evidence; however a 10 min live window may be too short and market-dependent (e.g. SAGAUSDT can be missed or classified as `unknown` in a short audit window), and waiting several quiet days may waste time if the market is calm — therefore the next slice evaluates discovery-layer coverage over the past 60 days. **D-A is allowed to answer:** which eligible movers AMA-RT detected over the past 60 days, when AMA-RT first detected them, which capture-path layer they reached, which movers were missed, why they were missed, which misses are universe-coverage issues vs. discovery-layer warnings. **D-A must NOT answer:** whether the strategy is profitable; whether live trading is allowed; whether leverage / position / stops should change; whether `symbol_limit` should auto-expand; whether anomaly thresholds should auto-change; whether candidate pool capacity should auto-change; whether Phase 12 can begin. **D-A must require:** a 60D top mover reference set; an eligible USDT-perpetual universe filter; `first_seen_time_utc` for every captured mover; `first_seen_event_type`; `first_seen_latency_seconds` where a mover reference timestamp exists; `capture_path_depth`; per-mover status (`captured` / `partially_captured` / `missed` / `excluded`); miss-reason classification; report / export / replay evidence. Phase 11C.1C-C-B-B-B-D acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A kickoff bypassing the standard gate; Phase 11C.1C-C-B-B-B-D-A will require its own kickoff PR, brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C / 11C.1C-C-B-B-B-D forbidden item verbatim. Paper / report / evidence-only; grants no trade authority. Phase 12 remains **FORBIDDEN**. | `docs/PROJECT_STATUS.md`; `docs/PHASE_GATE.md`; `docs/CHANGELOG.md`; `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`; `docs/PR62_DESCRIPTION.md` |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-D (closeout) | Mover Capture Recall & Missed-Tail Coverage Audit v0 docs-only closeout / acceptance flip (paper / report / evidence-only fourth child slice under Phase 11C.1C-C-B-B-B; closeout via PR #62) | **ACCEPTED (closed 2026-05-25; PR #60 docs-only kickoff merged into `main`; PR #61 implementation merged into `main`; this docs-only closeout PR #62 records the operator-VPS 10 min WS paper smoke evidence + daily report Mover Capture section + `MOVER_CAPTURE_*` event counts + Phase 8.5 export bundle + audit result `mover_capture_audit_status=DEGRADED` and flips the slice to `ACCEPTED`)**. **Operator-VPS 10 min WS paper smoke PASSED**: `duration_seconds=600.0`, `dry_run=false`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `risk_approved=0`, `HTTP 429=0`, `HTTP 418=0`, `ws_reconnect_count=0`, `ws_stale_count=0`, `live_trading_enabled=False`, `exchange_live_order_enabled=False`, `llm_enabled=False`, `right_tail_enabled=False`. **Mover Capture event counts**: `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`, `MOVER_CAPTURE_PATH_AUDITED=20`. **Daily report** contains `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0` section. **Audit result**: `mover_capture_audit_status=DEGRADED`, `top_mover_count=20`, `captured_top_mover_count=4`, `missed_top_mover_count=16`, `capture_recall_rate=0.2000`, `data_unreliable_count=4`, `risk_rejected_mover_count=4`. `DEGRADED` is the **expected and accepted** audit output for this smoke window because the audit layer successfully surfaced coverage weakness / uncertainty — `DEGRADED` is **NOT** a runtime failure. Captured-but-risk-rejected does **NOT** mean discovery failure. Missed-with-unknown reason is a `review` signal, **not** permission to loosen rules. Low capture recall does **NOT** authorise automatic `symbol_limit` expansion / anomaly threshold changes / candidate pool capacity changes / Regime weight changes / Risk Engine changes; high capture recall would also **NOT** authorise live trading. **Phase 8.5 export bundle**: `data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip` (`export_test_data=OK`, `manifest_event_count=63968`, `redaction_applied=True`, `events.jsonl` exists, export contains `MOVER_CAPTURE_*` events, `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`, `MOVER_CAPTURE_PATH_AUDITED=20`, `EXPORT_MOVER_CAPTURE_RECALL_CHECK=PASS`); export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. Safety flags unchanged across the operator-VPS run (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** rule relaxation based on SAGAUSDT or any small number of movers, **NOT** Risk Engine change, **NOT** Execution FSM change, **NOT** automatic `symbol_limit` expansion, **NOT** automatic anomaly threshold changes, **NOT** automatic candidate pool capacity changes, **NOT** automatic Regime weight changes, **NOT** Phase 11C.1C-C-B-B-B-D-A kickoff bypassing the standard gate, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C forbidden item verbatim. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`; `docs/PR62_DESCRIPTION.md`; `docs/PROJECT_STATUS.md`; `docs/PHASE_GATE.md`; `docs/CHANGELOG.md` |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-D (implementation) | Mover Capture Recall & Missed-Tail Coverage Audit v0 — implementation PR landing the deterministic, paper-only audit layer (data models + descriptive status / miss-reason taxonomies + pure functions + thin runtime orchestrator + runner wiring + daily-report section + 21 new tests) | **MERGED — SUPERSEDED by the closeout row above (Phase 11C.1C-C-B-B-B-D = ACCEPTED via PR #62; PR #61 implementation merged into `main`).** Implementation PR (PR #61) wired the deterministic, paper-only audit layer into the runtime: `app/adaptive/mover_capture_recall_audit.py` ships the `TopMoverReference` / `CapturePathEvidence` / `MoverCaptureAuditRecord` / `MoverCaptureRecallAuditInput` / `MoverCaptureRecallAuditReport` data models, the `MoverCaptureRecallAuditStatus` (`OK` / `INSUFFICIENT_DATA` / `DEGRADED`) and `CapturePathStatus` (`CAPTURED` / `PARTIALLY_CAPTURED` / `MISSED` / `EXCLUDED` / `INSUFFICIENT_DATA`) descriptive taxonomies, the structured `MissReason` taxonomy (`not_in_futures_universe` / `symbol_not_in_exchange_info` / `not_usdt_perpetual` / `below_liquidity_threshold` / `symbol_limit_excluded` / `candidate_pool_evicted` / `insufficient_ws_data` / `stale_data` / `data_unreliable` / `no_anomaly_threshold_cross` / `risk_rejected` / `no_completed_tail_label_yet` / `unknown`), the deterministic pure functions (`build_top_mover_reference_set`, `audit_mover_capture_path`, `classify_miss_reason`, `build_mover_capture_recall_audit_report`, `export_mover_capture_recall_audit_payload`, `load_mover_capture_recall_audit_payload`), and a thin `MoverCaptureRecallAuditRuntime` orchestrator that emits two new typed events `MOVER_CAPTURE_RECALL_AUDIT_GENERATED` / `MOVER_CAPTURE_PATH_AUDITED` through `EventRepository`. The runner (`scripts/run_public_market_paper.py`) builds the audit input from the public radar snapshot + `EventRepository` capture-path stages + `SymbolUniverse` exchangeInfo-as-truth catalogue, calls `MoverCaptureRecallAuditRuntime.flush(...)` on shutdown, and threads the resulting `metrics_payload()` into the daily report via the new `mover_capture_audit_metrics` kwarg. The daily report (`app/paper_run/daily_report.py`) renders a new `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0` section with every brief-mandated field (`mover_capture_audit_status`, `top_mover_count`, `captured_top_mover_count`, `partially_captured_top_mover_count`, `missed_top_mover_count`, `excluded_top_mover_count`, `capture_recall_rate`, `anomaly_detected_rate`, `label_tracking_rate`, `tail_label_assigned_rate`, `strategy_validation_sample_rate`, `risk_rejected_mover_count`, `mover_capture_records`, `miss_reason_summary`, `coverage_warnings`). Empty `top_mover_count` produces an `INSUFFICIENT_DATA` report (does NOT skip). Captured-but-risk-rejected ≠ failure; missed-but-not-in-eligible-universe ≠ failure; coverage warnings only fire when the mover is eligible AND shows a clear right-tail signal AND was missed for a system-correctable reason; a single coin proves nothing and does NOT authorise rule relaxation. **`tests/unit/test_phase11c_1c_c_b_b_b_d_mover_capture_recall_audit.py 21/21 PASS`**, **`tests/unit/ -k phase11c_ 410/410 PASS`**, **`tests/ 2384/2384 PASS`**. 30 s `--dry-run` smoke writes the new daily-report section with `mover_capture_audit_status=INSUFFICIENT_DATA` (expected — the dry-run transport does not push real ticker rows; the audit correctly degrades). The closeout PR #62 above records the operator-VPS paper smoke + daily report excerpt + Phase 8.5 export evidence + safety-flag invariants and flips the slice to `ACCEPTED`. Phase 12 remains **FORBIDDEN**. | `app/adaptive/mover_capture_recall_audit.py`; `app/core/events.py`; `app/paper_run/daily_report.py`; `scripts/run_public_market_paper.py`; `tests/unit/test_phase11c_1c_c_b_b_b_d_mover_capture_recall_audit.py`; `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`; `docs/PR61_DESCRIPTION.md` |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-C (closeout) | Long-Window Cohort Stability & Sample Sufficiency Protocol v0 docs-only closeout / acceptance flip (paper / report / evidence-only third child slice under Phase 11C.1C-C-B-B-B; closeout via PR #59) | **ACCEPTED (closed 2026-05-25; PR #58 docs-only kickoff merged into `main`; this docs-only closeout PR #59 records the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence and flips the slice to `ACCEPTED`)**. **W1 / W1+ 2 h paper WS run PASSED**: `duration_seconds=7200.0`, `uptime≈7238s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`, `risk_approved=0`, live trading disabled. 2 h event counts: `PAPER_ALPHA_COHORT_EVALUATED=18`, `PAPER_ALPHA_GATE_EVALUATED=3`, `PAPER_ALPHA_REPORT_GENERATED=3`, `PAPER_ALPHA_RULE_EVALUATED=27`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`. 2 h daily report contains both the Paper Alpha Gate section and the Regime & Cluster Cohort Evidence Pack section; `regime_cluster_sample_count=189`, `regime_cluster_completed_tail_label_count=0`, status remained `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` because `completed_tail_label_count=0<10` (accepted as valid low-completed-label evidence, not runtime failure). 2 h export bundle generated at `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip` (`export_test_data=OK`, `manifest_event_count=23001`, `redaction_applied=True`, `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`). **W2 4 h paper WS run PASSED**: configured `duration_seconds=14400.0`, actual runtime ≈ `14417s`, `iterations=237`, `chains_emitted=704`, `ws_chains_emitted=704`, `ws_real_transport=True`, `ws_reconnect_count=0`, `ws_staleness_ms_max=0`, `ws_stale_count=0`, `ingestion_errors=0`, `public_endpoint_calls=4226`, `ws_messages_received=1324423`, `radar_candidates_seen=152221`, `candidate_pool_size_max=20`, `liquidation_events_seen=4076`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `rate_limit_ban=False`, `risk_approved=0`, `risk_rejected=704`. 4 h event counts: `PAPER_ALPHA_COHORT_EVALUATED=24`, `PAPER_ALPHA_GATE_EVALUATED=4`, `PAPER_ALPHA_REPORT_GENERATED=4`, `PAPER_ALPHA_RULE_EVALUATED=36`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`. 4 h daily report: `paper_alpha_gate_status=INCONCLUSIVE`, `paper_alpha_gate_sample_count=164`, reason `completed_tail_label_count_below_min=2<10`; `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`, `regime_cluster_sample_count=164`, `regime_cluster_completed_tail_label_count=2`, reason `completed_tail_label_count_below_min=2<10` — progress from 0 to 2 completed labels still below the 10-label threshold; `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct W2 result, does NOT indicate runtime failure, does NOT authorise rule relaxation. 4 h export bundle at `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip` (`export_test_data=OK`, `manifest_event_count=61546`, `redaction_applied=True`, `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`). **W3 24 h upper-bound run PASSED with watcher early-stop**: `total_elapsed_seconds=900`, `final_tail_labels_since_start=20`, `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`, 24 h full runtime NOT NEEDED — proves the B-B-B-C sample sufficiency protocol can save runtime while preserving evidence. W3 safety summary held end-to-end (`mode=paper`, `live_trading=False`, `right_tail=False`, `llm=False`, `exchange_live_orders=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, `risk_approved=0`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_real_transport=True`); watcher logs `data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`, `data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`. **W3 export PASSED**: latest export zip after W3 early-stop `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`, generated 2026-05-25 12:41 UTC, `manifest_event_count=62761`, `redaction_applied=True`, `events.jsonl` exists, `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3 export-range event counts `TAIL_LABEL_ASSIGNED=495`, `LABEL_WINDOW_COMPLETED=495`, `STRATEGY_VALIDATION_SAMPLE_CREATED=397`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`, `PAPER_ALPHA_GATE_EVALUATED=5`, `PAPER_ALPHA_RULE_EVALUATED=45`, `PAPER_ALPHA_COHORT_EVALUATED=30`, `PAPER_ALPHA_REPORT_GENERATED=5` (clarification: `final_tail_labels_since_start=20` is the watcher early-stop condition for the 900 s live window; `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range event count — both valid, different scopes, do not confuse the two numbers). **B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol** — it does **NOT** mean any Regime / Cluster has proven right-tail advantage yet, does **NOT** mean strategy effectiveness is proven, does **NOT** authorise live trading, does **NOT** authorise rule relaxation based on low samples, does **NOT** authorise automatic parameter optimisation, does **NOT** authorise AI Learning, does **NOT** authorise changing the Risk Engine or the Execution FSM, does **NOT** authorise Phase 12. It records that 2 h works, 4 h works, completed labels begin to appear over longer windows, 24 h upper-bound early-stop works, completed-tail-label sufficiency threshold can be reached early, export / replay evidence preserves the results, low-sample states remain conservative, and no trade authority was granted. Long-window protocol outputs (`long_window_run_plan`, `sample_sufficiency_checklist`, `cohort_stability_checklist`, `operator_vps_evidence_template`, `export_replay_evidence_template`, `closeout_acceptance_template`) and per-window outputs (`paper_alpha_gate_status`, `regime_cluster_evidence_status`, `insufficient_sample_reasons`, daily-report Paper Alpha Gate section, daily-report Regime & Cluster Cohort Evidence Pack section, `PAPER_ALPHA_*` and `REGIME_CLUSTER_*` event counts, Phase 8.5 export bundles) remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. Safety flags unchanged across W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop runs (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** rule relaxation based on low samples, **NOT** Risk Engine change, **NOT** Execution FSM change, **NOT** a strategy implementation, **NOT** a trading module, **NOT** a new runtime module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`; `docs/PR58_DESCRIPTION.md`; `docs/PR59_DESCRIPTION.md`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-C (ACCEPTED)" + §"Phase 11C.1C-C-B-B-B-C acceptance evidence (operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound early-stop paper WS evidence PASSED)" |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-D (kickoff) | Mover Capture Recall & Missed-Tail Coverage Audit v0 / *异动币捕捉召回与漏捕右尾覆盖审计 v0* (docs / evidence-template-only fourth child slice under Phase 11C.1C-C-B-B-B; docs-only kickoff via PR #60) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-B-C is `ACCEPTED` (PR #58 docs-only kickoff + PR #59 docs-only closeout merged into `main`), so Phase 11C.1C-C-B-B-B-D is **NEXT_ALLOWED**. This docs-only kickoff PR #60 **defines** the slice in place — name, scope, boundary, allowed outputs, forbidden list, key metrics, interpretation principles, audit cadence (A1 / A2 with A3+ reserved), audit input sources (Binance public 24 h ticker, `EventRepository`, daily report, Phase 8.5 export / Phase 10A replay, `StrategyValidationDataset`, `PaperAlphaGateReport`, `RegimeClusterEvidencePack`, `SymbolUniverse` / `exchangeInfo`-as-truth, candidate pool logs / capacity-eviction evidence), audit objects, and acceptance-gate placeholder — but **does NOT flip its state**. The slice is paper-only / report-only / evidence-only and answers the seven coverage questions: (1) did real movers get captured, (2) at which discovery layer (`MARKET_SNAPSHOT` / `PRE_ANOMALY_DETECTED` / `ANOMALY_DETECTED` / `MARKET_REGIME_ASSESSED` / `CANDIDATE_STAGE_CLASSIFIED` / `OPPORTUNITY_SCORED` / `STRATEGY_MODE_SELECTED` / `CLUSTER_CONTEXT_ATTACHED` / `LABEL_QUEUE_ENQUEUED` / `LABEL_TRACKING_STARTED` / `LABEL_WINDOW_COMPLETED` / `TAIL_LABEL_ASSIGNED` / `STRATEGY_VALIDATION_SAMPLE_CREATED`), (3) if missed, why (taxonomy of 10 missed-mover reasons), (4) whether top movers were captured early enough, (5) whether captured movers proceeded into the label / validation pipeline, (6) whether missed movers are a system-coverage problem or a market / exchange-coverage problem, and (7) whether captured-but-rejected movers were rejected for sound conservative reasons. Allowed outputs (descriptive only): `top_mover_capture_summary`, `captured_mover_evidence`, `missed_mover_audit`, `symbol_universe_exclusion_summary`, `candidate_eviction_summary`, `risk_rejection_summary`, `first_seen_latency_summary`, `capture_recall_rate`, `missed_tail_candidate_list`, `coverage_warning`, `insufficient_coverage_reasons`. Trigger context: SAGAUSDT showed an obvious move on Binance's public 24 h gainer board; the system already captured SAGAUSDT end-to-end; one coin proves nothing — the audit institutionalises "human looks at gainer board vs. did the system see it" instead of relying on ad-hoc human screenshots. **NOT** a new strategy. **NOT** a trading module. **NOT** AI Learning. **NOT** automatic parameter optimisation. **NOT** Historical 30D+ Blind Replay / Walk-forward Validation (that gate is reserved for a Phase 12 candidate review and is explicitly out of scope here; it belongs after the major paper modules and the paper validation chain are complete, before small-money live trading). **NOT** a continued widening of system complexity. Phase 11C.1C-C-B-B-B-C acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard gate; Phase 11C.1C-C-B-B-B-D *closeout* will be a separate docs-only PR after the operator captures A1 / A2 audit evidence. The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B remains *Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up*. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C forbidden item verbatim. Paper / report / evidence-only; grants no trade authority. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`; `docs/PR60_DESCRIPTION.md`; `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B-D (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-D | Next child slice (placeholder; superseded by the kickoff row above — slice is now defined by name and scope as *Mover Capture Recall & Missed-Tail Coverage Audit v0 / 异动币捕捉召回与漏捕右尾覆盖审计 v0*) | **SUPERSEDED by the kickoff row above (Phase 11C.1C-C-B-B-B-D = NEXT_ALLOWED / NOT_STARTED, defined in place by PR #60).** Originally recorded as a placeholder when PR #59 closed Phase 11C.1C-C-B-B-B-C; this docs-only kickoff PR #60 supersedes the placeholder by defining Phase 11C.1C-C-B-B-B-D's name, scope, allowed outputs, forbidden list, boundary table, key metrics, interpretation principles, and audit cadence — without flipping the slice's state. Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED / NOT_STARTED`. | `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B-D (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-C (kickoff) | Long-Window Cohort Stability & Sample Sufficiency Protocol v0 (docs / evidence-template-only third child slice under Phase 11C.1C-C-B-B-B; docs-only kickoff via PR #58) | **SUPERSEDED by the closeout row above (Phase 11C.1C-C-B-B-B-C = ACCEPTED via PR #59).** PR #58 (the docs-only kickoff) merged into `main` on 2026-05-25 and recorded the parent / child relationship + boundary table + forbidden list + long-window run cadence + sample sufficiency / cohort stability principles + allowed outputs. The ACCEPTED row above tracks the W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence captured by the operator-VPS and recorded by this docs-only closeout PR (PR #59). | `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`; `docs/PR58_DESCRIPTION.md`; `docs/PR59_DESCRIPTION.md` |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-B | Regime & Cluster Cohort Evidence Pack v0 (*Regime 与 Cluster 分组证据包 v0*; paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B; docs-only kickoff via PR #55) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-B-A is `ACCEPTED` (PR #52 merged into `main` on 2026-05-24, mergeCommit `f8ba315`; closeout via PR #54), so Phase 11C.1C-C-B-B-B-B is **NEXT_ALLOWED**. PR #55 is the **docs-only kickoff / scope alignment** for this slice; **no runtime code is shipped by the kickoff PR**. The substantive Phase 11C.1C-C-B-B-B-B implementation requires a **separate implementation PR**. Allowed outputs (paper / report / evidence-only): `regime_cohort_summary`, `cluster_cohort_summary`, `score_bucket_summary`, `stage_outcome_summary`, `strategy_mode_outcome_summary`, `regime_cluster_evidence_pack`, `warnings`, `insufficient_sample_reasons` — each is a descriptive label only and **MUST NEVER trigger a real trade**, **MUST NEVER** modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM; the Risk Engine remains the single trade-decision gate. Slice exists to make eight cohort questions answerable from data (which Regimes produce `strong_tail` / `reached_3r` / `reached_5r`; which Regimes produce `fake_breakout` / `late_chase_failure`; whether `cluster_leader` beats followers; whether high `opportunity_score_bucket` beats low; whether high `early_tail_score_bucket` beats low; whether `follow` / `pullback` / `observe` / `reject` outcomes match expectations; which state combinations deserve continued paper observation; which must be down-weighted or rejected). Core principles: add fewer modules / accumulate more structural data; verify Regime more / talk less about strategy; prove which states carry right-tail value; replayable; reduces human-interpretation cost; serves Regime / Liquidity / Right Tail judgement; forbid unverifiable AI output; forbid system-complexity growth; forbid loosening rules on low samples. **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** a strategy implementation, **NOT** a trading module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item verbatim. Phase 12 remains **FORBIDDEN**. **SUPERSEDED by the closeout row above (Phase 11C.1C-C-B-B-B-B = ACCEPTED via PR #57).** | `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`; `docs/PR55_DESCRIPTION.md`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-B (implementation) | Regime & Cluster Cohort Evidence Pack v0 implementation (paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B; implementation via PR #56) | **MERGED — superseded by the closeout row above (Phase 11C.1C-C-B-B-B-B = ACCEPTED via PR #57; PR #56 mergeCommit `1a9abe2`)** — branch (implementation) `feature/phase-11c1c-c-b-b-b-b-regime-cluster-evidence-pack-v0`. PR #56 ships `app/adaptive/regime_cluster_evidence_pack.py` (pure-function module: `RegimeClusterEvidencePackStatus`, `RegimeClusterCohortKey`, `RegimeClusterCohortStats`, `RegimeClusterEvidenceRecord`, `RegimeClusterEvidenceInput`, `RegimeCohortSummary`, `ClusterCohortSummary`, `ScoreBucketSummary`, `StageOutcomeSummary`, `StrategyModeOutcomeSummary`, `RegimeClusterEvidencePack`, plus the nine pure functions `build_regime_cluster_evidence_input` / `build_regime_cohort_summary` / `build_cluster_cohort_summary` / `build_score_bucket_summary` / `build_stage_outcome_summary` / `build_strategy_mode_outcome_summary` / `build_regime_cluster_evidence_pack` / `export_regime_cluster_evidence_payload` / `load_regime_cluster_evidence_payload`); two new typed events (`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`); `StrategyValidationRuntime` extended to build / emit / cache the pack on the same flush as the dataset / quality-gate / Paper Alpha Gate emission; `WSRadarChainDriver._post_chain` wires `observe_market_regime` per opportunity; Phase 11B daily-report section. Schema version `phase_11c_1c_c_b_b_b_b.regime_cluster_evidence_pack.v1`. The per-cohort `status` (`INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` / `EVIDENCE_SIGNAL`) and the top-level `regime_cluster_evidence_status` are **descriptive only** for human review and **MUST NEVER trigger a real trade**, **MUST NEVER** modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM. Tests: 23/23 brief-mandated + 389/389 phase11c_ + 2363/2363 full pytest PASS on the PR branch (no regression vs. post-PR-#55 main baseline). 30 s dry-run smoke produces the new section with `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` (expected — Phase 11C.1C-C-A primary tracking window is 5 minutes; the brief's "do not loosen rules on low samples" rule is honoured); explicit `regime_cluster_insufficient_sample_reasons` populated; no `ORDER_*` / `POSITION_*` / `STOP_*` / `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` events emitted. Real-WS 10 min smoke is **NOT REQUIRED** for PR #56 (this PR is a deterministic evidence-compression layer; non-empty cohort rows depend on the upstream Phase 11C.1C-C-A primary tracking window resolving — reserved for the closeout PR). The slice remains **NEXT_ALLOWED / NOT_STARTED** until the operator-VPS paper smoke + closeout PR records the acceptance evidence. Safety flags unchanged across the run (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** a strategy implementation, **NOT** a trading module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`; `docs/PR56_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`; `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B-B (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-23 | Phase 11C.1C-C-B-B-A | Strategy Validation Dataset Builder & Quality Gate v0 (paper / report-only first slice of Phase 11C.1C-C-B-B; ships dataset record / dataset / summary / quality-gate contracts + pure functions + the runtime hook that emits three new typed events on top of the Phase 11C.1C-C-B-A `StrategyValidationSample` / `StrategyValidationReport` / `ClusterExposureAssessment` artefacts) | **ACCEPTED (closed 2026-05-23; PR #44 merged into `main`, mergeCommit `3ecfc3b`)** — `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py` 27/27 PASS (brief-mandated cases); `tests/unit -k phase11c_` 339/339 PASS (312 baseline + 27 new); full `tests/` 2313/2313 PASS on the PR branch (no regression vs. post-PR-#43 main 2286 baseline). 30 s dry-run smoke produced an empty / low-sample report at `data/reports/phase11c/2026-05-23-phase11c-public-market.md` with the new "Phase 11C.1C-C-B-B-A Strategy Validation Dataset Builder & Quality Gate v0" section: `STRATEGY_VALIDATION_DATASET_BUILT=1`, `STRATEGY_VALIDATION_DATASET_EXPORTED=1`, `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED=1`, `validation_dataset_records=2`, `validation_dataset_symbols=BTCUSDT,ETHUSDT`, `validation_quality_gate_status=fail` (expected — the smallest Phase 11C.1C-C-A tracking window is 5 minutes; samples are necessarily in-flight in a 30 s smoke), `validation_dataset_export_ready=True`, `validation_dataset_replay_ready=True`. Real WS 10 min smoke is **NOT required** for this PR — the smallest Phase 11C.1C-C-A tracking window is 5 minutes and cannot complete in 30 s; reserved for Phase 11C.1C-C-B-B-B closeout when non-empty datasets are first observable end-to-end. Safety flags unchanged (`live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `trading_mode_paper=True`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no API key, no signed endpoint, no private WS, no listenKey, no DeepSeek trade decision, no real Telegram outbound). The `validation_quality_gate_status` field on every `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` event is descriptive only (`pass` / `warn` / `fail`) and **MUST NEVER trigger a real trade**; the Risk Engine remains the single trade-decision gate. PR #44 has merged into `main` (mergeCommit `3ecfc3b`, merged 2026-05-23 UTC); the dry-run smoke evidence above was accepted; Phase 11C.1C-C-B-B-A is therefore **ACCEPTED**. Phase 11C.1C-C-B-B-B is now **NEXT_ALLOWED / NOT_STARTED**; Phase 11C.1C-C-B-B-A acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_VALIDATION_DATASET_QUALITY_GATE.md`; `docs/PR44_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-A (ACCEPTED)" + §"Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-23 | Phase 11C.1C-C-B-A | Strategy Validation Lab v0 & Cluster Exposure Control Contracts (paper / report-only first slice of Phase 11C.1C-C-B; ships data contracts + pure aggregators + runtime that emits seven new typed events on top of the Phase 11C.1C-C-A `LabelTrackingRecord` outcomes) | **ACCEPTED (closed 2026-05-23; PR #42 merged into `main`, mergeCommit `cc18047`)** — `tests/unit/test_phase11c_1c_c_b_strategy_validation.py` 25 PASS (brief-mandated cases); `tests/unit -k phase11c_` 312 PASS (287 baseline + 25 new); full `tests/` 2286 PASS on the PR branch (no regression vs. post-PR-#41 main 2261 baseline). 30 s dry-run smoke is contract-only (smallest Phase 11C.1C-C-A tracking window is 5m and cannot complete in 30 s); the runtime emits an empty-but-well-formed `STRATEGY_VALIDATION_REPORT_GENERATED` so the daily report still renders the new section. **Operator-VPS 10 min real public WS smoke PASSED** on 2026-05-23 against PR #42 head (commit `0bedcce`): `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=76324`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `ingestion_errors=0`, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`. Authoritative SQLite event-count query (captured after shutdown flush): `STRATEGY_VALIDATION_SAMPLE_CREATED=24`, `STRATEGY_VALIDATION_REPORT_GENERATED=1`, `STRATEGY_MODE_VALIDATED=4`, `CANDIDATE_STAGE_VALIDATED=5`, `SCORE_BUCKET_VALIDATED=8`, `CLUSTER_EXPOSURE_ASSESSED=1`, `CLUSTER_LEADER_VALIDATED=1`. Daily report contains the new "Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster Exposure Control Contracts" section with non-empty cohort lines (`strategy_mode=reject n=24`; `candidate_stage=early n=24`; `opportunity_score_bucket=0-49 n=13` / `50-64 n=11`; `early_tail_score_bucket=0-24 n=24`; `cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action`); `tail_label_distribution = unresolved x 24` (5m primary windows still in-flight at the 10 min boundary, as expected). Daily-report counter snapshot caveat: top event-count lines may show 0 because counters are snapshotted before shutdown flush; SQLite query is authoritative and confirms emission. Safety flags unchanged (`live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `trading_mode_paper=True`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no API key, no signed endpoint, no private WS, no listenKey, no DeepSeek trade decision, no real Telegram outbound). The Kiro-side sandbox cannot host this smoke (Binance-region HTTP 451 geoblock — historical context only, not the current blocker; same as the Phase 11C.1C-B / Phase 11C.1C-C-A closeouts). The `suggested_cluster_action` field on every `ClusterExposureAssessment` is paper / report only (`leader_only` / `observe_followers` / `reject_cluster` / `no_action`) and **MUST NEVER trigger a real trade**; the Risk Engine remains the single trade-decision gate. PR #42 has merged into `main` (mergeCommit `cc18047`, merged 2026-05-23 UTC); the smoke evidence above was accepted; this docs-only closeout PR therefore flips Phase 11C.1C-C-B-A to **ACCEPTED**, mirroring the PR #36 → PR #37, PR #38 → PR #39, and PR #40 → PR #41 closeout pattern. Phase 11C.1C-C-B-B is now **NEXT_ALLOWED / NOT_STARTED**; Phase 11C.1C-C-B-A acceptance does **NOT** authorise Phase 11C.1C-C-B-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_STRATEGY_VALIDATION_CLUSTER_CONTROL.md`; `docs/PR42_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_strategy_validation.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-A (ACCEPTED)" + §"Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)" |
| 2026-05-23 | Phase 11C.1C-C-A | MFE / MAE Label Queue Runtime & Tail Outcome Tracking (paper-only runtime that consumes the Phase 11C.1C-A `LABEL_QUEUE_ENQUEUED` contract and produces forward MFE / MAE / `tail_label` outcomes per ACTIVE candidate) | **ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`)** — `tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py` 30 PASS (brief-mandated cases); `tests/unit -k phase11c_` 287 PASS; full `tests/` 2261 PASS on the PR branch (no regression vs. post-PR-#38 main baseline). 30 s dry-run smoke is contract-only (the smallest tracking window is 5m and cannot complete in 30 s). **Operator-VPS 10 min real public WS smoke PASSED** (`duration_seconds=600.0`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=56592`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `LABEL_TRACKING_STARTED=19` runner / `36` events.db, `LABEL_WINDOW_UPDATED=38` / `82`, `LABEL_WINDOW_COMPLETED=11` / `20`, `TAIL_LABEL_ASSIGNED=11` / `20`, `MISSED_TAIL_DETECTED=0`, `FAKE_BREAKOUT_DETECTED=0`, pending=8 / completed=11 / expired=0 / unresolved=0, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`, `ingestion_errors=0`, safety flags unchanged); the Kiro sandbox could not host the smoke (Binance-region HTTP 451 geoblock, same as the Phase 11C.1C-B closeout), so the operator ran it from a Binance-reachable VPS. PR #40 has merged into `main` (mergeCommit `75d3c7c`); the smoke evidence above was accepted; Phase 11C.1C-C-A is therefore **ACCEPTED**. Phase 11C.1C-C-A acceptance does **NOT** authorise Phase 11C.1C-C-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md`; `docs/PR40_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-A (ACCEPTED)" + §"Phase 11C.1C-C-A acceptance evidence (closeout)" |
| 2026-05-22 | Phase 11C.1C-B | Adaptive Candidate Runtime Calibration & Early Tail Discovery v0 (paper-only runtime calibration metrics + Early Tail Discovery v0 + daily-report enhancements) | **ACCEPTED (closed 2026-05-22; PR #38 merged into `main`)** — `tests/unit/test_phase11c_1c_b_runtime_calibration.py` 12 PASS; `tests/unit -k phase11c_` 257 PASS; full `tests/` 2231 PASS with no regression vs. the post-PR-#37 main baseline; 30s dry-run produced a `runtime_calibration` block with all 15 fields on every adaptive event and `early_tail_score` per ACTIVE candidate; 5min real public WS smoke (`--ws-first`, no `--dry-run`) confirmed `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=30526`, `ws_chains_emitted=12`, runtime calibration block present on every adaptive event, daily report contains `top_early_tail_candidates` / `top_late_chase_risk_candidates` / `early_tail_score_top_symbols` / `opportunity_score_distribution`, `label_queue` remains contract-only, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `rate_limit_ban=False`, `ws_stale_count=0`, `ws_reconnect_count=0`, `ingestion_errors=12` (explainable: sandbox-region geoblock HTTP 451 on Binance REST; NOT a 429/418/ban; WS pump ran cleanly), safety flags unchanged. PR #38 merged into `main` (mergeCommit `ce4b6de`); the smoke evidence above was accepted; Phase 11C.1C-B is therefore **ACCEPTED**. Phase 11C.1C-C is now **NEXT_ALLOWED / NOT_STARTED**. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_B_RUNTIME_CALIBRATION.md`; `tests/unit/test_phase11c_1c_b_runtime_calibration.py`; `docs/PHASE_GATE.md` §"Phase 11C.1C-B acceptance evidence (closeout)" |
| 2026-05-22 | Phase 11C.1C-A | Adaptive Candidate Regime & Strategy Selector Contracts (paper-only data contracts + scoring + selector + paper-only routing first version) | **ACCEPTED (PR #36 merged; PR #37 docs closeout)** — 244/244 phase11c tests + 2219/2219 full pytest pass on the PR branch; 30s dry-run produces the six adaptive events per ACTIVE candidate; 5min real public WS smoke produced 32842 real WS messages, 12 chains, 12 each of the six adaptive event types, 0 stales, 0 reconnects, 0 rate-limit 429/418/ban; daily report contains the Phase 11C.1C-A adaptive section; safety flags unchanged. PR #36 merged into `main`; PR #37 closed the Phase 11C.1C-A docs gate. | `docs/PHASE_11C_1C_ADAPTIVE_CANDIDATE_REGIME_STRATEGY_SELECTOR.md`; `tests/unit/test_phase11c_1c_a_adaptive_candidate.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-A (ACCEPTED)" |
| 2026-05-22 | Phase 11C.1B | WebSocket-First All-Market Demon Coin Radar (incl. SymbolUniverse exchangeInfo-as-truth, non-ASCII contracts allowed) | **ACCEPTED** — 5min / 10min / 1h real WS smoke PASS (no 429, no 418, no stale, no ingestion errors); export zip generated; events.db readable; PRs #31 / #32 / #33 / #34 merged; safety flags unchanged | `docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B |
| 2026-05-21 | Phase 11C.1A | Binance Public REST Rate Limit Governor & 418 Protection | merged        | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1A     |
| 2026-05-21 | Phase 11C | Real Binance Public Market Data Read-Only Paper | open (parent); Phase 11C.1B (5min / 10min / 1h smoke) ACCEPTED 2026-05-22; longer-window (6h / 24h) acceptance still optional / not yet run | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md`             |
| 2026-05-19 | Phase 11B-HF | Cloud Paper - High-Frequency observation     | accepted (GO) | 30/30 dry-run PASS, 648/648 24h@2min observations PASS |
| 2026-05-19 | Phase 11B | Cloud Paper Acceptance                       | accepted (GO) | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`            |
| ...        | Phase 10D | Telegram Outbound + Export Commands          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10C | LLM Guarded Interpreter (receive-only)       | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10B | Reflection + Replay engines (read-only)      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10A | Replay engine substrate                      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 9   | Execution FSM + Reconciliation               | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 8.5 | Learning-Ready Data Contract                 | merged        | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`           |
| ...        | Phase 8   | Capital Flow Engine                          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 7   | Risk Engine + No-Trade Gate                  | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 6   | Pre-Anomaly + Anomaly + Confirmation + Manipulation | merged | `docs/CHANGELOG.md`                                  |
| ...        | Phase 5   | Regime + Universe + Liquidity                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 4   | Market Data Buffer                           | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 3   | Exchange Gateway (read-only abstract)        | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 2   | Event Sourcing + Database Set                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 1   | Safety Foundation                            | merged        | `docs/CHANGELOG.md`                                    |

## Live safety flags (Phase 1 lock)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

The Phase 1 safety lock in `app/config/settings.py::_apply_phase1_safety_lock`
hard-coerces the first five flags. The Phase 11C
`MarketDataConfig` and `SafetyConfig` schemas refuse to load any
deployment that flips a `forbid_*` flag.

## Why the Phase 11C real-data acceptance was paused (historical, RESOLVED)

The first 24h test against the real Binance public REST endpoints
(`fapi.binance.com`) exposed two failure modes the original Phase 11C
runner did not protect against:

  1. HTTP 429 (Too Many Requests). Binance returned this once the
     per-IP weight budget was exceeded. The runner kept polling and
     escalated to:
  2. HTTP 418 (I'm a teapot). Binance uses 418 to signal a real IP
     ban.

Phase 11C's safety lock held throughout (`mode=paper`,
`live_trading=False`, no API key, no signed endpoint, no real order),
but the gateway was unusable for real-data acceptance until the
rate-limit problem is fixed.

**Phase 11C.1A** (PR #31) shipped the fix in three layers:

  - a new `BinancePublicRestGovernor`
    (`app/exchanges/binance_rate_limit.py`) that wraps every public
    REST call, tracks the rolling weight budget, sleeps the
    `Retry-After` window on 429, latches into protection mode on
    418, and opens a P1 incident;
  - lower defaults (`symbol_limit=5`, `rest_poll_interval_seconds=60`,
    `weight_budget_per_minute=300`, soft 0.50 / hard 0.75);
  - a layered REST runner that does `exchangeInfo` / `ticker/24hr`
    only at bootstrap and refuses per-symbol detail REST calls
    unless a candidate ranking selects them.

**Phase 11C.1B** (PRs #32 / #33 / #34) then shipped the WebSocket-first
all-market radar + the routed real-network public WS adapter + the
WS poll fix + the SymbolUniverse exchangeInfo-as-truth gate (non-ASCII
contracts admitted; ASCII-only regex banned). The 5min / 10min / 1h
real-WS smoke ladder now passes cleanly with zero 429 / 418 / stale /
ingestion errors. See "Phase 11C.1B acceptance evidence (closeout)"
below for the headline numerics.

PR-C (cluster exposure control + multi-candidate priority ranking)
remains a separate, future scope item and is **not** required for the
Phase 11C.1B closeout; it is tracked alongside the future
Phase 11C.1C — Adaptive Candidate Regime & Strategy Selector work.

## What Phase 11C is

Phase 11C is real **Binance public market data** read-only paper.
It connects to public REST endpoints (`/fapi/v1/exchangeInfo`,
`/fapi/v1/ticker/24hr`, `/fapi/v1/klines`, `/fapi/v1/aggTrades`,
`/fapi/v1/depth`, `/fapi/v1/fundingRate`, `/fapi/v1/openInterest`,
`/fapi/v1/premiumIndex`, `/fapi/v1/ticker/bookTicker`), feeds the
data through the existing `MarketDataBuffer` and Risk Engine, and
emits the full Phase 11C event chain into `events.db`.

## What Phase 11C is NOT

- NOT live trading
- NOT connected to the Binance trading API
- NOT consuming any Binance API key / API secret
- NOT calling any signed endpoint
- NOT calling any account / position / leverage / margin endpoint
- NOT connected to DeepSeek
- NOT connected to a real Telegram bot
- NOT connected to 币安广场
- NOT a path into Phase 12

## Open phase

**Phase 11C.1C-C-B-B-B — Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up.** Status:
**NEXT_ALLOWED / NOT_STARTED.** Phase 11C.1C-C-B-B-A (PR #44)
merged into `main` on 2026-05-23 (mergeCommit `3ecfc3b`); the
30 s dry-run smoke evidence (empty / low-sample quality-gate
report with `validation_quality_gate_status=fail`, exactly the
brief's expectation for a low-sample window) was accepted;
Phase 11C.1C-C-B-B-A is therefore **ACCEPTED**, and Phase
11C.1C-C-B-B-B is now **NEXT_ALLOWED**. No implementation has
started in this repo state; Phase 11C.1C-C-B-B-B will require
its own kickoff PR, brief, scope, boundary table, forbidden
list, and acceptance evidence.

> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise Phase
> 11C.1C-C-B-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise private
> endpoints.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise DeepSeek
> trade decisions.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise real
> Telegram outbound.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise Phase 12.**
> **`validation_quality_gate_status` (`pass` / `warn` / `fail`)
> cannot trigger real trading** — it is a descriptive label
> only; the Risk Engine remains the single trade-decision
> gate.
> **Validation result / cluster action / `strategy_mode` /
> `suggested_cluster_action` / `mfe_pct` / `mae_pct` /
> `tail_label` cannot trigger real trading** — they are
> descriptive labels only; the Risk Engine remains the
> single trade-decision gate.
> **Phase 12 (real money / live trading) remains FORBIDDEN.**

Phase 11C.1C-C-B-B-B inherits every Phase 1 + Phase 11C.1B +
Phase 11C.1C-A + Phase 11C.1C-B + Phase 11C.1C-C-A +
Phase 11C.1C-C-B-A + Phase 11C.1C-C-B-B-A forbidden item:

  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`, the
    seven `STRATEGY_VALIDATION_*` events, validation cohort
    stats, `suggested_cluster_action`,
    `validation_quality_gate_status`,
    `STRATEGY_VALIDATION_DATASET_BUILT`,
    `STRATEGY_VALIDATION_DATASET_EXPORTED`,
    `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`) to a
    real-trade authority
  - automatic parameter optimisation that self-modifies the
    runtime configuration
  - reinforcement learning that drives trade decisions
  - AI Learning that auto-decides trades
  - the complete Strategy Validation Lab follow-up
  - the Paper Alpha Gate v0 (Paper Alpha Gate v0 is NOT
    implemented by Phase 11C.1C-C-B-B-A; it may only start
    as the Phase 11C.1C-C-B-B-B-A child slice after this
    docs-only kickoff and a separate implementation PR;
    Paper Alpha Gate v0 remains paper-only / report-only
    and grants no trade authority — verdict (`PASS` /
    `WARN` / `FAIL` / `INCONCLUSIVE`) MUST NEVER trigger a
    real trade or modify position size, leverage,
    stop-loss, target price, the Risk Engine, or the
    Execution FSM)

See `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B
(NEXT_ALLOWED / NOT_STARTED)" for the inherited boundary
table.

### Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0 (first child slice; ACCEPTED via PR #54 docs-only closeout)

**Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0.** Status:
**ACCEPTED (closed 2026-05-24; PR #52 merged into `main` on
2026-05-24, mergeCommit `f8ba315`; this docs-only closeout PR
#54 records the operator-VPS paper evidence that flips the
slice to `ACCEPTED`).** Phase 11C.1C-C-B-B-B-A is the
**first child slice** under the Phase 11C.1C-C-B-B-B parent.
The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B
remains *Strategy Validation Lab (deeper) & richer Cluster
Exposure Control follow-up*. Phase 11C.1C-C-B-B-B-A carves
out **only** the *Paper Alpha Gate v0* — the smallest
auditable evidence-gate on top of the Phase 11C.1C-C-B-B-A
artefacts — leaving the remaining deeper Lab follow-up work
for later child slices (B-B-B-B, B-B-B-C, …) under the same
parent.

PR #52 (branch
`feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`) merged
the Paper Alpha Gate v0 implementation into `main` on
2026-05-24. PR #54 (this docs-only closeout) records the
operator-VPS paper evidence and flips Phase 11C.1C-C-B-B-B-A
to `ACCEPTED`, mirroring the PR #36 → PR #37, PR #38 → PR
#39, PR #40 → PR #41, PR #42 → PR #43, PR #44 → PR #50, and
PR #52 → PR #53 → PR #54 docs-only closeout pattern.

The full Phase 11C.1C-C-B-B-B-A scope, boundary, and
forbidden-item list are recorded in
`docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`,
`docs/PR52_DESCRIPTION.md`, and
`docs/PR54_DESCRIPTION.md`.

> **Phase 11C.1C-C-B-B-B-A is paper / report / evidence only.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise Phase 12.**
> **Paper Alpha Gate v0 verdict (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) cannot trigger real trading**, modify position size, modify leverage, modify stop-loss, modify target price, modify the Risk Engine, or modify the Execution FSM — it is a descriptive label only.
> **Paper Alpha Gate verdicts remain paper-only / report-only / evidence-only.**
> **Paper Alpha Gate verdicts cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **Risk Engine remains the single trade-decision gate.**
> **Execution FSM remains paper today.**
> **Phase 12 (real money / live trading) remains FORBIDDEN.**

Phase 11C.1C-C-B-B-B-A is paper / report / evidence-only and:

  - is **NOT** real / live trading;
  - is **NOT** AI Learning;
  - is **NOT** automatic parameter optimisation;
  - is **NOT** reinforcement learning;
  - is **NOT** the complete Strategy Validation Lab
    follow-up (reserved for later child slices under Phase
    11C.1C-C-B-B-B);
  - is **NOT** a strategy-quality / profitability oracle;
  - is **NOT** a strategy autonomous optimisation loop;
  - is **NOT** a position-sizing / leverage / stop-loss /
    target-price modifier;
  - is **NOT** a Risk Engine override / bypass;
  - is **NOT** an Execution FSM override / bypass;
  - is **NOT** a Phase Gate override / bypass;
  - is **NOT** a path into Phase 12;
  - is **NOT** a sample-trust gate (the existing Phase
    11C.1C-C-B-B-A `validation_quality_gate_status` field is
    the sample-trust gate; Paper Alpha Gate v0 *consumes*
    that field as an input);
  - is **NOT** a real-trade authority of any kind.

#### Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min WS paper smoke PASSED + Phase 8.5 export bundle)

Operator-VPS 10 min WS paper smoke:

  - `duration_seconds = 600.0`
  - `uptime ≈ 608s`
  - `ws_first = true`
  - `ws_real_transport = true`
  - `ingestion_errors = 0`
  - `HTTP 429 = 0`
  - `HTTP 418 = 0`

Paper Alpha Gate daily report:

  - Daily report contains `"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"`
  - `paper_alpha_gate_status = INCONCLUSIVE`
  - `paper_alpha_gate_sample_count = 20`
  - reason: `completed_tail_label_count_below_min=0<10`

Paper Alpha Gate events (runner snapshot + events.db
type-count cross-check, after shutdown flush):

  - `PAPER_ALPHA_GATE_EVALUATED = 1`
  - `PAPER_ALPHA_RULE_EVALUATED = 9`
  - `PAPER_ALPHA_COHORT_EVALUATED = 6`
  - `PAPER_ALPHA_REPORT_GENERATED = 1`

Export evidence (Phase 8.5 export bundle):

  - `export_test_data = OK`
  - export zip generated: `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip`
  - `manifest_event_count = 1572`
  - `redaction_applied = True`
  - `events.jsonl` exists
  - export contains `PAPER_ALPHA_*` events
  - `EXPORT_PAPER_ALPHA_GATE_CHECK = PASS`

Export package files observed:

  - `manifest.json`
  - `summary_report.md`
  - `events.jsonl`
  - `opportunities.jsonl`
  - `signal_snapshots.jsonl`
  - `risk_decisions.jsonl`
  - `state_transitions.jsonl`
  - `capital_events.jsonl`
  - `virtual_trade_plans.jsonl`

`paper_alpha_gate_status = INCONCLUSIVE` is an **expected
and accepted** result for this smoke window because
`completed_tail_label_count = 0 < 10`. This means the Paper
Alpha Gate correctly refused to overfit or force a `PASS`
when completed tail labels were insufficient. **`INCONCLUSIVE`
does NOT mean runtime failure. `INCONCLUSIVE` does NOT
authorise strategy changes. `INCONCLUSIVE` does NOT authorise
live trading. `INCONCLUSIVE` does NOT authorise Phase 12.**

Safety boundary held end-to-end across the operator-VPS run:

```
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN
```

See `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md` for the
full Phase 11C.1C-C-B-B-B-A scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Closed
phase: Phase 11C.1C-C-B-B-B-B-A (ACCEPTED)" + §"Phase
11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min
WS paper smoke PASSED)" for the verbatim transcript; see
`docs/PR51_DESCRIPTION.md` for the docs-only kickoff PR; see
`docs/PR52_DESCRIPTION.md` for the merged implementation PR;
see `docs/PR54_DESCRIPTION.md` for this docs-only closeout
PR.

### Phase 11C.1C-C-B-B-B-B — Regime & Cluster Cohort Evidence Pack v0 (second child slice; ACCEPTED via PR #57 docs-only closeout)

**Phase 11C.1C-C-B-B-B-B — *Regime & Cluster Cohort Evidence
Pack v0 / Regime 与 Cluster 分组证据包 v0*.** Status:
**ACCEPTED (closed 2026-05-24; PR #56 merged into `main` on
2026-05-24, mergeCommit `1a9abe2`; this docs-only closeout PR
#57 records the operator-VPS paper evidence that flips the
slice to `ACCEPTED`).** Phase 11C.1C-C-B-B-B-B is the
**second child slice** under the Phase 11C.1C-C-B-B-B
parent. The parent phase is **not** renamed: Phase
11C.1C-C-B-B-B remains *Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up*. Phase
11C.1C-C-B-B-B-B carved out **only** the *Regime & Cluster
Cohort Evidence Pack v0* — a read-only / evidence-only
compression layer on top of the Phase 11C.1C-C-B-B-A
artefacts — leaving the remaining deeper Lab follow-up
work for later child slices (B-B-B-C, …) under the same
parent.

PR #55 (docs-only kickoff) recorded the scope, boundary,
forbidden list, and allowed outputs. PR #56 (branch
`feature/phase-11c1c-c-b-b-b-b-regime-cluster-evidence-pack-v0`)
merged the substantive Regime & Cluster Cohort Evidence
Pack v0 implementation into `main` on 2026-05-24
(mergeCommit `1a9abe2`). PR #57 (this docs-only closeout)
records the operator-VPS paper evidence and flips Phase
11C.1C-C-B-B-B-B to `ACCEPTED`, mirroring the PR #36 → PR
#37, PR #38 → PR #39, PR #40 → PR #41, PR #42 → PR #43, PR
#44 → PR #50, and PR #52 → PR #54 docs-only closeout
pattern.

The full Phase 11C.1C-C-B-B-B-B scope, boundary, and
forbidden-item list are recorded in
`docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`,
`docs/PR55_DESCRIPTION.md`,
`docs/PR56_DESCRIPTION.md`, and
`docs/PR57_DESCRIPTION.md`.

> **Phase 11C.1C-C-B-B-B-B is paper / report / evidence only.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 12.**
> **Regime & Cluster Evidence Pack outputs (per-cohort `status` and top-level `regime_cluster_evidence_status` — `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` / `EVIDENCE_SIGNAL`) cannot trigger real trading**, modify position size, modify leverage, modify stop-loss, modify target price, modify the Risk Engine, or modify the Execution FSM — they are descriptive labels only.
> **Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only.**
> **Regime & Cluster Evidence Pack outputs cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **Risk Engine remains the single trade-decision gate.**
> **Execution FSM remains paper today.**
> **Phase 12 (real money / live trading) remains FORBIDDEN.**

Phase 11C.1C-C-B-B-B-B is paper / report / evidence-only and:

  - is **NOT** real / live trading;
  - is **NOT** AI Learning;
  - is **NOT** automatic parameter optimisation;
  - is **NOT** reinforcement learning;
  - is **NOT** the complete Strategy Validation Lab
    follow-up (reserved for later child slices under Phase
    11C.1C-C-B-B-B);
  - is **NOT** a strategy implementation;
  - is **NOT** a trading module;
  - is **NOT** a position-sizing / leverage / stop-loss /
    target-price modifier;
  - is **NOT** a Risk Engine override / bypass;
  - is **NOT** an Execution FSM override / bypass;
  - is **NOT** a Phase Gate override / bypass;
  - is **NOT** a path into Phase 12;
  - is **NOT** a replacement for the Phase 11C.1C-C-B-B-B-A
    Paper Alpha Gate v0 verdict (the evidence pack is
    *additive*, not a replacement);
  - is **NOT** a real-trade authority of any kind.

**Why this slice exists (positioning under AMOS).** This
slice is a direct application of the
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` governance
to the next concrete step under Phase 11C.1C-C-B-B-B. The
project's main line must converge on: add fewer modules /
accumulate more structural data; verify Regime more / talk
less about strategy; prove which states really carry
right-tail value rather than chase a universal model. Phase
11C.1C-C-B-B-B-B is exactly that step — a **read-only /
evidence-only compression layer** that organises the
artefacts already produced by upstream slices (Phase
11C.1C-C-A label-tracking outcomes, Phase 11C.1C-C-B-A
validation samples / cluster exposure assessments, Phase
11C.1C-C-B-B-A validation dataset / quality gate, Phase
11C.1C-C-B-B-B-A Paper Alpha Gate verdict) into cohort
summaries by Regime, Cluster, Stage, Strategy Mode, and
Score Bucket.

**Allowed outputs (paper / report / evidence-only).** Each
is a **descriptive label only**. None has trade authority.
None is read by the Risk Engine or the Execution FSM:

  - `regime_cohort_summary`
  - `cluster_cohort_summary`
  - `score_bucket_summary`
  - `stage_outcome_summary`
  - `strategy_mode_outcome_summary`
  - `regime_cluster_evidence_pack`
  - `warnings`
  - `insufficient_sample_reasons`

#### Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED + Phase 8.5 export bundle)

Operator-VPS 10 min WS paper smoke:

  - `duration_seconds = 600.0`
  - `uptime ≈ 608s`
  - `ws_first = true`
  - `ws_real_transport = true`
  - `ingestion_errors = 0`
  - `HTTP 429 = 0`
  - `HTTP 418 = 0`

Regime & Cluster Cohort Evidence Pack daily report:

  - Daily report contains `"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"`
  - `regime_cluster_evidence_status = INSUFFICIENT_SAMPLE`
  - `sample_count = 14`
  - `completed_tail_label_count = 0`
  - `insufficient_sample_reasons`:
      - `sample_count_below_min=14<20`
      - `completed_tail_label_count_below_min=0<10`

Regime & Cluster Cohort Evidence Pack events (runner
snapshot + events.db type-count cross-check, after shutdown
flush):

  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = 1`
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 5`

Export evidence (Phase 8.5 export bundle):

  - `export_test_data = OK`
  - export zip generated:
    `data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip`
  - `manifest_event_count = 3151`
  - `redaction_applied = True`
  - `events.jsonl` exists
  - export contains `REGIME_CLUSTER_*` events
  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = 1` (in export)
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 5` (in export)
  - `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK = PASS`

Export package files observed:

  - `manifest.json`
  - `summary_report.md`
  - `events.jsonl`
  - `opportunities.jsonl`
  - `signal_snapshots.jsonl`
  - `risk_decisions.jsonl`
  - `state_transitions.jsonl`
  - `capital_events.jsonl`
  - `virtual_trade_plans.jsonl`

`regime_cluster_evidence_status = INSUFFICIENT_SAMPLE` is
an **expected and accepted** result for this smoke window
because `sample_count = 14 < 20` and
`completed_tail_label_count = 0 < 10`. This means the
Regime & Cluster Evidence Pack **correctly refused to
overfit or force a regime / cluster conclusion when
structural samples were insufficient**. **`INSUFFICIENT_SAMPLE`
does NOT mean runtime failure. `INSUFFICIENT_SAMPLE` does
NOT authorise strategy changes. `INSUFFICIENT_SAMPLE` does
NOT authorise rule relaxation. `INSUFFICIENT_SAMPLE` does
NOT authorise live trading. `INSUFFICIENT_SAMPLE` does NOT
authorise Phase 12.**

Safety boundary held end-to-end across the operator-VPS run:

```
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN
```

See `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`
for the full Phase 11C.1C-C-B-B-B-B scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Closed
phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" + §"Phase
11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min
WS paper smoke PASSED)" for the verbatim transcript; see
`docs/PR55_DESCRIPTION.md` for the docs-only kickoff PR; see
`docs/PR56_DESCRIPTION.md` for the merged implementation
PR; see `docs/PR57_DESCRIPTION.md` for this docs-only
closeout PR.

### Phase 11C.1C-C-B-B-B-C — Long-Window Cohort Stability & Sample Sufficiency Protocol v0 (*长窗口 Cohort 稳定性与样本充足协议 v0*; docs / evidence-template-only third child slice under Phase 11C.1C-C-B-B-B; ACCEPTED via PR #58 docs-only kickoff + PR #59 docs-only closeout)

**Phase 11C.1C-C-B-B-B-C — Long-Window Cohort Stability &
Sample Sufficiency Protocol v0 / 长窗口 Cohort 稳定性与样
本充足协议 v0.** Status: **ACCEPTED (closed 2026-05-25;
PR #58 docs-only kickoff merged into `main`; this
docs-only closeout PR #59 records the operator-VPS W1 /
W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper
WS evidence and flips the slice to `ACCEPTED`).** Phase
11C.1C-C-B-B-B-B (*Regime & Cluster Cohort Evidence Pack
v0*) is `ACCEPTED` (PR #56 merged into `main` on
2026-05-24, mergeCommit `1a9abe2`; closeout via PR #57);
PR #58 was the docs-only kickoff for B-B-B-C; PR #59
records the W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound
early-stop paper WS evidence and flips Phase
11C.1C-C-B-B-B-C to `ACCEPTED`. The slice remains
intentionally **docs / evidence-template only** end-to-end
(no future implementation PR added a new runtime module
under this slice — it consumed the existing Regime &
Cluster Cohort Evidence Pack v0 and Paper Alpha Gate v0
runtime + daily-report + Phase 8.5 export pipeline). Phase
11C.1C-C-B-B-B-D is now **NEXT_ALLOWED / NOT_STARTED**
(placeholder; not yet defined; will require its own
kickoff PR, brief, scope, boundary table, forbidden list,
and acceptance evidence).

The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B
remains *Strategy Validation Lab (deeper) & richer Cluster
Exposure Control follow-up*. Phase 11C.1C-C-B-B-B-C carved
out the third small, auditable slice under that parent —
following B-B-B-A (Paper Alpha Gate v0) and B-B-B-B
(Regime & Cluster Cohort Evidence Pack v0).

**B-B-B-C acceptance is acceptance of the long-window data
collection and sample-sufficiency protocol.** It does
**NOT** mean any Regime / Cluster has proven right-tail
advantage yet, does **NOT** mean strategy effectiveness is
proven, does **NOT** authorise live trading, API keys,
private endpoints, DeepSeek trade decisions, real Telegram
outbound, AI Learning, automatic parameter optimisation,
reinforcement learning, rule relaxation based on low
samples, Risk Engine changes, Execution FSM changes, or
Phase 12. It records that 2 h works, 4 h works, completed
labels begin to appear over longer windows, the 24 h
upper-bound early-stop works, the completed-tail-label
sufficiency threshold can be reached early, export /
replay evidence preserves the results, low-sample states
remain conservative (`INSUFFICIENT_SAMPLE` /
`INCONCLUSIVE` are valid outputs not failures), and no
trade authority was granted by any window.

#### Phase 11C.1C-C-B-B-B-C operator-VPS evidence (recorded by PR #59)

  - **W1 / W1+ — 2 h Long-Window Paper WS Run (PASS):**
    `duration_seconds=7200.0`, `uptime≈7238s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`,
    `risk_approved=0`, live trading disabled. 2 h event
    counts: `PAPER_ALPHA_COHORT_EVALUATED=18`,
    `PAPER_ALPHA_GATE_EVALUATED=3`,
    `PAPER_ALPHA_REPORT_GENERATED=3`,
    `PAPER_ALPHA_RULE_EVALUATED=27`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`. 2 h daily
    report contains both the Paper Alpha Gate section and
    the Regime & Cluster Cohort Evidence Pack section;
    `regime_cluster_sample_count=189`,
    `regime_cluster_completed_tail_label_count=0`, status
    remained `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE`
    because `completed_tail_label_count=0<10` (accepted
    as valid low-completed-label evidence, not runtime
    failure). 2 h export bundle:
    `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`,
    `manifest_event_count=23001`, `redaction_applied=True`,
    `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`.
  - **W2 — 4 h Long-Window Paper WS Run (PASS):**
    configured `duration_seconds=14400.0`, actual runtime
    ≈ `14417s`, `iterations=237`, `chains_emitted=704`,
    `ws_chains_emitted=704`, `ws_real_transport=True`,
    `ws_reconnect_count=0`, `ws_staleness_ms_max=0`,
    `ws_stale_count=0`, `ingestion_errors=0`,
    `public_endpoint_calls=4226`,
    `ws_messages_received=1324423`,
    `radar_candidates_seen=152221`,
    `candidate_pool_size_max=20`,
    `liquidation_events_seen=4076`,
    `rate_limit_429_count=0`, `rate_limit_418_count=0`,
    `rate_limit_ban=False`, `risk_approved=0`,
    `risk_rejected=704`. 4 h event counts:
    `PAPER_ALPHA_COHORT_EVALUATED=24`,
    `PAPER_ALPHA_GATE_EVALUATED=4`,
    `PAPER_ALPHA_REPORT_GENERATED=4`,
    `PAPER_ALPHA_RULE_EVALUATED=36`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`. 4 h daily
    report: `paper_alpha_gate_status=INCONCLUSIVE`,
    `paper_alpha_gate_sample_count=164`, reason
    `completed_tail_label_count_below_min=2<10`;
    `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
    `regime_cluster_sample_count=164`,
    `regime_cluster_completed_tail_label_count=2`, reason
    `completed_tail_label_count_below_min=2<10` —
    progress from 0 to 2 completed labels still below the
    10-label sufficiency threshold; `INCONCLUSIVE` /
    `INSUFFICIENT_SAMPLE` remained the correct W2 result;
    does **NOT** indicate runtime failure; does **NOT**
    authorise rule relaxation. 4 h export bundle:
    `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`,
    `manifest_event_count=61546`, `redaction_applied=True`,
    `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`.
  - **W3 — 24 h upper-bound run with watcher early-stop
    (PASS):** `total_elapsed_seconds=900`,
    `final_tail_labels_since_start=20`,
    `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`,
    24 h full runtime NOT NEEDED — proves the B-B-B-C
    sample sufficiency protocol can save runtime while
    preserving evidence. W3 safety summary held end-to-end
    (`mode=paper`, `live_trading=False`, `right_tail=False`,
    `llm=False`, `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`,
    `risk_approved=0`, `ingestion_errors=0`,
    `rate_limit_429_count=0`, `rate_limit_418_count=0`,
    `ws_real_transport=True`); watcher logs
    `data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`,
    `data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`.
  - **W3 export evidence (PASS):** latest export zip after
    W3 early-stop
    `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`,
    generated 2026-05-25 12:41 UTC,
    `manifest_event_count=62761`,
    `redaction_applied=True`, `events.jsonl` exists,
    `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`. W3
    export-range event counts: `TAIL_LABEL_ASSIGNED=495`,
    `LABEL_WINDOW_COMPLETED=495`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED=397`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`,
    `PAPER_ALPHA_GATE_EVALUATED=5`,
    `PAPER_ALPHA_RULE_EVALUATED=45`,
    `PAPER_ALPHA_COHORT_EVALUATED=30`,
    `PAPER_ALPHA_REPORT_GENERATED=5`. **Clarification:**
    `final_tail_labels_since_start=20` is the watcher
    early-stop condition for the 900 s live window;
    `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range
    event count — both valid, different scopes (live-run
    window vs. export-range window). **Do not confuse
    the two numbers.**
  - **Safety boundary held end-to-end** across W1 / W1+
    2 h, W2 4 h, and W3 24 h upper-bound early-stop:
    `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound,
    Phase 12 stayed **FORBIDDEN**.

This slice exists because PR #57 closeout flipped B-B-B-B
to `ACCEPTED` with
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`
(`sample_count=14<20`, `completed_tail_label_count=0<10`)
— **runtime / report / export are correct, but the 10
min observation window is too short to support a Regime /
Cluster right-tail conclusion**. The right next step is
**not** to add a new strategy module, a new AI authority,
or a new optimiser; the right next step is to
**accumulate structural data across longer paper
observation windows** until cohort samples are large
enough for the Regime & Cluster Cohort Evidence Pack and
the Paper Alpha Gate to produce non-`INSUFFICIENT_SAMPLE`
/ non-`INCONCLUSIVE` verdicts that a human can act on as
evidence. This slice codifies that step as a **protocol**
— a long-window paper data-collection cadence (W1 = 1 h,
W2 = 4 h, W3 = 24 h, W4+ multi-day reserved;
**operator-driven; not auto-scheduled**), a sample
sufficiency rule, and cohort stability acceptance
criteria — while keeping all of the Phase 1 safety lock
invariants in force.

> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-B-C is paper / report / evidence-only.**
> **Phase 11C.1C-C-B-B-B-C grants no trade authority.**
> **Phase 11C.1C-C-B-B-B-C is NOT a strategy implementation.**
> **Phase 11C.1C-C-B-B-B-C is NOT a trading module.**
> **Phase 11C.1C-C-B-B-B-C is NOT a new runtime module.**
> **Phase 11C.1C-C-B-B-B-C is NOT AI Learning.**
> **Phase 11C.1C-C-B-B-B-C is NOT automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-C is NOT reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-C is NOT the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-C is NOT Phase 12.**
> **Phase 11C.1C-C-B-B-B-C inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim.**

The full kickoff scope (long-window run cadence,
per-window evidence fields, sample sufficiency principle,
cohort stability principle, allowed outputs, boundary
table, slice-specific forbidden items, and acceptance-gate
placeholder) is recorded in
`docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`
and the kickoff PR description is in
`docs/PR58_DESCRIPTION.md`; the corresponding
`docs/PHASE_GATE.md` *Open phase: Phase 11C.1C-C-B-B-B-C
(NEXT_ALLOWED / NOT_STARTED)* section carries the same
content for the canonical phase ledger.

#### Allowed outputs (docs / evidence templates only)

  - `long_window_run_plan` — operator-facing run plan for
    W1 (1 h) / W2 (4 h) / W3 (24 h); recorded in
    `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`.
  - `sample_sufficiency_checklist` — verbatim checklist
    of `sample_count`, `completed_tail_label_count`,
    `*_status` fields, and `insufficient_sample_reasons`
    that must be captured per window.
  - `cohort_stability_checklist` — verbatim checklist of
    cross-window comparisons (signal persistence, signal
    inversion, warning persistence) that may be captured
    after consecutive windows.
  - `operator_vps_evidence_template` — verbatim shape of
    the runner / events.db / daily-report / export
    transcript the operator must record per window.
  - `export_replay_evidence_template` — verbatim shape of
    the Phase 8.5 export bundle / Phase 10A replay
    invariants per window.
  - `closeout_acceptance_template` — verbatim shape of
    the docs-only closeout PR that would flip Phase
    11C.1C-C-B-B-B-C to `ACCEPTED` (mirrors the PR #54 /
    PR #57 pattern).

#### Per-window evidence fields the operator must capture verbatim

  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` count.
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED` count.
  - `PAPER_ALPHA_GATE_EVALUATED` count.
  - `PAPER_ALPHA_RULE_EVALUATED` count.
  - `PAPER_ALPHA_COHORT_EVALUATED` count.
  - `PAPER_ALPHA_REPORT_GENERATED` count.
  - daily report Regime & Cluster section
    (`## Phase 11C.1C-C-B-B-B-B …`).
  - daily report Paper Alpha Gate section
    (`## Phase 11C.1C-C-B-B-B-A …`).
  - `sample_count`.
  - `completed_tail_label_count`.
  - `regime_cluster_evidence_status` (one of
    `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` /
    `EVIDENCE_SIGNAL`).
  - `paper_alpha_gate_status` (one of `PASS` / `WARN` /
    `FAIL` / `INCONCLUSIVE`).
  - `insufficient_sample_reasons` (verbatim list).
  - Phase 8.5 export package (zip generated, manifest
    event count sane, redaction applied, `events.jsonl`
    exists).
  - export contains `REGIME_CLUSTER_*` events.
  - export contains `PAPER_ALPHA_*` events.
  - safety flags (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no API key, no
    signed endpoint, no private WS, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).

#### Sample sufficiency principle (carries forward verbatim)

  - Low samples cannot output strong conclusions.
  - When `completed_tail_label_count` is below the Regime
    & Cluster Evidence Pack v0 minimum, no Regime /
    Cluster right-tail conclusion is permitted from the
    cohort rows.
  - `INSUFFICIENT_SAMPLE` (Regime & Cluster) and
    `INCONCLUSIVE` (Paper Alpha Gate) are **valid
    outputs, not failures**.
  - Cohort signals are only allowed once samples are
    sufficient.
  - Cohort signals — even when sample-sufficient — remain
    paper-only / report-only / evidence-only.
  - Cohort signals cannot trigger trades, modify
    parameters, relax rules, or enter Phase 12.

#### Cohort stability principle (carries forward verbatim)

  - A signal that appears in one short window and
    disappears in the next is **not** treated as
    evidence.
  - A signal that persists across W1 / W2 / W3 *and*
    survives the Phase 8.5 export / Phase 10A replay
    round-trip is treated as a **paper-only candidate
    signal worth continued observation** — but it still
    does not authorise any runtime change, parameter
    optimisation, rule relaxation, or trade.
  - A signal whose direction inverts across consecutive
    windows is logged as `regime_outcome_inverted_warning`
    and is **not** acted on.
  - The protocol is biased toward "do nothing" when
    stability is unclear.

#### Slice-specific forbidden items

This slice carries forward every Phase 1 / 11C.1B /
11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A /
11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B
forbidden item verbatim, and adds the following
slice-specific forbidden items:

  - Triggering a real trade.
  - Modifying position size / leverage / stop-loss /
    target price / Risk Engine / Execution FSM.
  - Letting AI / LLM decide direction, position size,
    leverage, stop-loss, target price, or execution.
  - Auto-optimising parameters in response to long-window
    cohort signals.
  - Auto-relaxing rules in response to low-sample windows.
  - Auto-scheduling W1 / W2 / W3 / W4+ runs from runtime
    code.
  - Replacing the Regime & Cluster Cohort Evidence Pack
    v0 `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
    with a relaxed rule.
  - Implementing the protocol as a new runtime module —
    the slice is intentionally **docs / evidence template
    only** end-to-end.
  - Adding new event types, new Python modules, or new
    runtime behaviour at any point in this slice's
    lifecycle.
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/`.
  - Running tests as part of this kickoff PR.
  - Phase 12 / live trading kickoff.

### Required operator-VPS paper evidence before Phase 11C.1C-C-B-B-B-A closeout `ACCEPTED` — FILED via PR #54

Phase 11C.1C-C-B-B-B-A closeout from
`MERGED / AWAITING_OPERATOR_VPS_EVIDENCE / CLOSEOUT_PENDING`
to `ACCEPTED` required the operator to file the following
**operator-VPS paper evidence** in a separate docs-only
closeout PR (mirroring the PR #36 → PR #37, PR #38 → PR
#39, PR #40 → PR #41, PR #42 → PR #43, PR #44 → PR #50
docs-only closeout pattern). **All required evidence has been
filed via this docs-only closeout PR #54** (see
"Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS
10 min WS paper smoke PASSED + Phase 8.5 export bundle)"
above):

  - `paper_alpha_gate_status` (verbatim from the daily
    report; one of `PASS` / `WARN` / `FAIL` /
    `INCONCLUSIVE`) ✅ filed: `INCONCLUSIVE`
  - `paper_alpha_gate_sample_count` ✅ filed: `20`
  - `PAPER_ALPHA_GATE_EVALUATED` event count ✅ filed: `1`
  - `PAPER_ALPHA_RULE_EVALUATED` event count ✅ filed: `9`
  - `PAPER_ALPHA_COHORT_EVALUATED` event count ✅ filed: `6`
  - `PAPER_ALPHA_REPORT_GENERATED` event count ✅ filed: `1`
  - the daily-report "Phase 11C.1C-C-B-B-B-A Paper Alpha
    Gate v0" section ✅ filed
  - export bundle / replay readability check ✅ filed:
    `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip`,
    `manifest_event_count=1572`, `redaction_applied=True`,
    `events.jsonl` exists, export contains `PAPER_ALPHA_*`
    events, `EXPORT_PAPER_ALPHA_GATE_CHECK=PASS`
  - safety flags unchanged across the operator-VPS run ✅
    filed (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound)
  - **Phase 12 remains FORBIDDEN** across the operator-VPS
    run ✅ filed

This docs-only closeout PR #54 is therefore complete; Phase
11C.1C-C-B-B-B-A is now **ACCEPTED**; Phase 11C.1C-C-B-B-B-B
is now **NEXT_ALLOWED / NOT_STARTED**; Phase 12 remains
**FORBIDDEN**.

## Closed phase: Phase 11C.1C-C-B-B-A (acceptance closeout)

**Phase 11C.1C-C-B-B-A — Strategy Validation Dataset Builder
& Quality Gate v0 (PR #44).** Status: **ACCEPTED (closed
2026-05-23; PR #44 merged into `main`, mergeCommit
`3ecfc3b`).** Phase 11C.1C-C-B-B-A shipped the **paper /
report-only first slice** of the deeper Phase 11C.1C-C-B-B
work on top of the Phase 11C.1C-C-B-A
`StrategyValidationSample` / `StrategyValidationReport` /
`ClusterExposureAssessment` artefacts: the dataset record /
dataset / summary / quality-gate v0 contracts + pure builders
+ the runtime hook that emits three new typed events
(`STRATEGY_VALIDATION_DATASET_BUILT`,
`STRATEGY_VALIDATION_DATASET_EXPORTED`,
`STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`). It does **NOT**
ship the complete Strategy Validation Lab follow-up, the
Paper Alpha Gate v0, AI Learning, automatic parameter
optimisation, reinforcement learning, or richer cluster
heuristics — those are reserved for Phase 11C.1C-C-B-B-B and
now sit at **NEXT_ALLOWED / NOT_STARTED**.

The acceptance evidence is **fully on file**:

  - PR #44 merged into `main` (mergeCommit `3ecfc3b`,
    merged 2026-05-23 UTC).
  - **Strategy Validation Dataset Builder implemented.**
  - **Quality Gate v0 implemented.**
  - **`STRATEGY_VALIDATION_DATASET_BUILT` emitted.**
  - **`STRATEGY_VALIDATION_DATASET_EXPORTED` emitted.**
  - **`STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` emitted.**
  - Targeted tests:
    `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`
    **27 / 27 PASS** (brief-mandated cases).
  - Phase 11C focus filter: `tests/unit -k phase11c_`
    **339 / 339 PASS** (312 baseline + 27 new).
  - Full pytest: `tests/` **2313 / 2313 PASS** on the PR
    branch (no regression vs. post-PR-#43 main 2286
    baseline).
  - 30 s dry-run smoke generated the dataset and the
    quality-gate report at
    `data/reports/phase11c/2026-05-23-phase11c-public-market.md`
    with the new "Phase 11C.1C-C-B-B-A Strategy Validation
    Dataset Builder & Quality Gate v0" section:
    `STRATEGY_VALIDATION_DATASET_BUILT=1`,
    `STRATEGY_VALIDATION_DATASET_EXPORTED=1`,
    `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED=1`,
    `validation_dataset_records=2`,
    `validation_dataset_symbols=BTCUSDT,ETHUSDT`,
    `validation_quality_gate_status=fail`,
    `validation_dataset_export_ready=True`,
    `validation_dataset_replay_ready=True`.
  - **`validation_quality_gate_status=fail` is the EXPECTED
    output for the low-sample 30 s dry-run** — the smallest
    Phase 11C.1C-C-A primary tracking window is 5 minutes,
    so samples that landed in the 30 s window are necessarily
    in-flight / unresolved. The quality gate correctly
    classifies the dataset as too thin for downstream
    review — exactly the brief's "empty or low-sample
    quality gate report" requirement.
  - **`validation_quality_gate_status` is descriptive only**
    (`pass` / `warn` / `fail`) and **MUST NEVER trigger a
    real trade**; the Risk Engine remains the single
    trade-decision gate. No module reads `gate_status` to
    drive execution; this is pinned by every quality-gate
    test case.
  - **No live trading.** No `ORDER_*` / `POSITION_*` /
    `STOP_*` / `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED`
    event was emitted by the dataset / quality-gate slice.
  - **No API key.** No Binance API key / API secret was
    loaded; the runner's `EnvGuard` refuses to boot if any
    forbidden credential env-var is set non-empty.
  - **No private endpoint.** No signed endpoint, no account
    / order / position / leverage / margin endpoint, no
    private WebSocket, no `listenKey`, no DeepSeek trade
    decision, no real Telegram outbound.

Real WS 10 min smoke was **NOT required** for this PR — the
smallest Phase 11C.1C-C-A primary tracking window is 5
minutes and cannot complete in a 30 s dry-run; it is reserved
for Phase 11C.1C-C-B-B-B closeout when non-empty datasets are
first observable end-to-end.

Safety boundary held end-to-end across the Phase 11C.1C-C-B-B-A
acceptance evidence runs:

```
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN
```

Phase 11C.1C-C-B-B-A acceptance does **NOT** authorise:

  - Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate.
  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting `validation_quality_gate_status` /
    `STRATEGY_VALIDATION_DATASET_*` / any other paper / virtual
    signal to a real-trade authority
  - AI Learning that auto-decides trades
  - automatic parameter optimisation
  - reinforcement learning
  - Paper Alpha Gate v0 (Paper Alpha Gate v0 is NOT
    implemented by Phase 11C.1C-C-B-B-A; it may only start
    as the Phase 11C.1C-C-B-B-B-A child slice after this
    docs-only kickoff and a separate implementation PR;
    Paper Alpha Gate v0 remains paper-only / report-only
    and grants no trade authority)
  - the complete Strategy Validation Lab follow-up

The `validation_quality_gate_status` field on every
`STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` event is one of
`pass` / `warn` / `fail` — paper / report-only descriptive
labels for a human reviewer; **MUST NEVER trigger a real
trade.** The Risk Engine remains the single trade-decision
gate.

See
`docs/PHASE_11C_1C_C_B_B_VALIDATION_DATASET_QUALITY_GATE.md`
for the full Phase 11C.1C-C-B-B-A scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Closed
phase: Phase 11C.1C-C-B-B-A (ACCEPTED)" for the acceptance
gate, and §"Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED /
NOT_STARTED)" for the inherited boundary table.

## Closed phase: Phase 11C.1C-C-B-A (acceptance closeout)

**Phase 11C.1C-C-B-A — Strategy Validation Lab v0 & Cluster
Exposure Control Contracts (PR #42).** Status: **ACCEPTED
(closed 2026-05-23; PR #42 merged into `main`, mergeCommit
`cc18047`).** Phase 11C.1C-C-B-A shipped the **paper /
report-only first slice** of the deeper Phase 11C.1C-C-B
Strategy Validation Lab work on top of the Phase 11C.1C-C-A
`LabelTrackingRecord` outcomes. It does **NOT** ship the
complete Strategy Validation Lab, AI Learning, automatic
parameter optimisation, reinforcement learning, or richer
cluster heuristics — those are reserved for Phase
11C.1C-C-B-B and now sit at **NEXT_ALLOWED / NOT_STARTED**.

The acceptance gate is **fully on file**:

  - Test ladder green: 25 brief-mandated tests + 312 phase11c
    tests + 2286 full pytest, no regression vs. the
    post-PR-#41 main 2261 baseline.
  - **Operator-VPS 10 min real public WS smoke PASSED** (run
    from a Binance-reachable VPS against commit `0bedcce`):
    `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`,
    `ws_real_transport=true`,
    `ws_messages_received=76324`, `ws_chains_emitted=27`,
    `learning_ready_attached=27`, `snapshots_emitted=27`,
    `ingestion_errors=0`, `HTTP 429 count=0`,
    `HTTP 418 count=0`, `rate_limit_ban=False`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `ws_currently_stale=False`. Authoritative SQLite
    event-count query (captured **after** shutdown flush):
    `STRATEGY_VALIDATION_SAMPLE_CREATED=24`,
    `STRATEGY_VALIDATION_REPORT_GENERATED=1`,
    `STRATEGY_MODE_VALIDATED=4`,
    `CANDIDATE_STAGE_VALIDATED=5`,
    `SCORE_BUCKET_VALIDATED=8`,
    `CLUSTER_EXPOSURE_ASSESSED=1`,
    `CLUSTER_LEADER_VALIDATED=1`. Safety flags unchanged.
  - Daily report contains `"## Phase 11C.1C-C-B-A Strategy
    Validation Lab v0 & Cluster Exposure Control Contracts"`
    with non-empty cohort lines (`strategy_mode=reject n=24`;
    `candidate_stage=early n=24`;
    `opportunity_score_bucket=0-49 n=13` / `50-64 n=11`;
    `early_tail_score_bucket=0-24 n=24`;
    `cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action`);
    `tail_label_distribution = unresolved x 24` (5m primary
    windows still in-flight at the 10 min boundary, as
    expected). Daily-report counter snapshot caveat: top
    event-count lines may show 0 because counters are
    snapshotted before shutdown flush; SQLite query is
    authoritative and confirms emission.
  - Safety boundary held end-to-end: `mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`; no Binance API key,
    no Binance API secret, no signed endpoint, no account /
    order / position / leverage / margin endpoint, no private
    WebSocket, no `listenKey`, no DeepSeek trade decision, no
    real Telegram outbound; Phase 12 remained **FORBIDDEN**.

The Kiro-side sandbox could **not** host the smoke (the same
Binance-region HTTP 451 geoblock recorded under the Phase
11C.1C-B / Phase 11C.1C-C-A closeouts still applies to the
Kiro sandbox), so the operator ran it from a Binance-reachable
VPS and back-filled the verbatim transcript under
`docs/PHASE_GATE.md` §"Phase 11C.1C-C-B-A acceptance evidence
(operator-VPS 10 min real public WS smoke PASSED)". A sandbox
WS smoke would **not** have been authoritative evidence and
was **not** filed as such.

PR #42 has **merged into `main`** (mergeCommit `cc18047`,
merged 2026-05-23 UTC); the smoke evidence above was
accepted; this docs-only closeout PR therefore flips Phase
11C.1C-C-B-A to **ACCEPTED** under `docs/PROJECT_STATUS.md` /
`docs/PHASE_GATE.md` / `docs/CHANGELOG.md`, mirroring the PR
#36 → PR #37, PR #38 → PR #39, and PR #40 → PR #41 closeout
pattern.

Phase 11C.1C-C-B-A acceptance does **NOT** authorise:

  - Phase 11C.1C-C-B-B kickoff bypassing the standard gate.
  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`, the
    seven `STRATEGY_VALIDATION_*` events, validation cohort
    stats, `suggested_cluster_action`) to a real-trade
    authority
  - automatic parameter optimisation that self-modifies the
    runtime configuration
  - reinforcement learning that drives trade decisions
  - AI Learning that auto-decides trades

The `suggested_cluster_action` field on every
`ClusterExposureAssessment` is one of `leader_only` /
`observe_followers` / `reject_cluster` / `no_action` —
paper / report-only labels for a human reviewer; **MUST
NEVER trigger a real trade.** The Risk Engine remains the
single trade-decision gate.

See `docs/PHASE_11C_1C_C_B_STRATEGY_VALIDATION_CLUSTER_CONTROL.md`
for the full Phase 11C.1C-C-B-A scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Phase
11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real
public WS smoke PASSED)" for the verbatim operator-VPS smoke
transcript.

## Closed phase: Phase 11C.1C-C-A (acceptance closeout)

**Phase 11C.1C-C-A — MFE / MAE Label Queue Runtime & Tail
Outcome Tracking (PR #40).** Status: **ACCEPTED (closed
2026-05-23; PR #40 merged into `main`, mergeCommit
`75d3c7c`).** Phase 11C.1C-C-A shipped the **paper-only first
runtime** that consumes the Phase 11C.1C-A
`LABEL_QUEUE_ENQUEUED` contract and produces forward
MFE / MAE / `tail_label` outcomes per ACTIVE candidate over
five tracking windows (5m primary, 15m / 30m / 1h / 4h
secondary). It does **NOT** ship the deeper Strategy
Validation Lab, AI Learning, or Cluster Exposure Control —
those are reserved for Phase 11C.1C-C-B and now sit at
**NEXT_ALLOWED / NOT_STARTED**.

The acceptance gate is **fully on file**:

  - Test ladder green: 30 brief-mandated tests + 287 phase11c
    tests + 2261 full pytest, no regression vs. the
    post-PR-#38 main baseline.
  - **Operator-VPS 10 min real public WS smoke PASSED** (run
    from a Binance-reachable VPS against commit `6d6044d`):
    `dry_run=false`, `ws_real_transport=true`,
    `ws_messages_received=56592`, `ws_chains_emitted=27`,
    `learning_ready_attached=27`, `snapshots_emitted=27`,
    `LABEL_TRACKING_STARTED=19` (runner) / `36` (events.db),
    `LABEL_WINDOW_UPDATED=38` / `82`,
    `LABEL_WINDOW_COMPLETED=11` / `20` (5m primary window
    closed inside the 10 min run), `TAIL_LABEL_ASSIGNED=11`
    / `20`, `MISSED_TAIL_DETECTED=0`,
    `FAKE_BREAKOUT_DETECTED=0`, `pending_label_records=8`,
    `completed_label_records=11`, `expired_label_records=0`,
    `unresolved_label_records=0`, `HTTP 429 count=0`,
    `HTTP 418 count=0`, `rate_limit_ban=False`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `ws_currently_stale=False`, `ingestion_errors=0`,
    safety flags unchanged.
  - Daily report contains `"## Phase 11C.1C-C-A MFE / MAE
    Label Queue Runtime & Tail Outcome Tracking"`.
  - Safety boundary held end-to-end: no API key, no signed
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound, Phase
    12 remained **FORBIDDEN**.

The Kiro-side sandbox could **not** host the smoke (the same
Binance-region HTTP 451 geoblock recorded under the Phase
11C.1C-B closeout still applies to the Kiro sandbox), so the
operator ran it from a Binance-reachable VPS and back-filled
the verbatim transcript under `docs/PHASE_GATE.md` §"Phase
11C.1C-C-A acceptance evidence (closeout)". A sandbox WS
smoke would **not** have been authoritative evidence and was
**not** filed as such.

PR #40 has **merged into `main`** (mergeCommit `75d3c7c`,
merged 2026-05-23 UTC); the smoke evidence above was
accepted; this docs-only closeout PR therefore flips Phase
11C.1C-C-A to **ACCEPTED** under `docs/PROJECT_STATUS.md` /
`docs/PHASE_GATE.md` / `docs/CHANGELOG.md`, mirroring the PR
#36 → PR #37 and PR #38 → PR #39 closeout pattern.

Phase 11C.1C-C-A acceptance does **NOT** authorise:

  - Phase 11C.1C-C-B kickoff bypassing the standard gate.
  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority

See `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md` for
the full Phase 11C.1C-C-A scope, boundary, and forbidden-item
list; see `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance
evidence (closeout)" for the verbatim operator-VPS smoke
transcript.

## Closed phase: Phase 11C.1C-B (acceptance closeout)

**Phase 11C.1C-B — Adaptive Candidate Runtime Calibration &
Early Tail Discovery v0 (PR #38).** Status: **ACCEPTED (closed
2026-05-22; PR #38 merged into `main`, mergeCommit
`ce4b6de`).** Phase 11C.1C-B shipped the **paper-only first
version** of the Adaptive Candidate Runtime Calibration & Early
Tail Discovery layer on top of the Phase 11C.1C-A contracts
(`AdaptiveCandidateContext`, the six adaptive event types,
`MarketRegimeAssessment` / `CandidateStageAssessment` /
`OpportunityScore` / `StrategyModeDecision` / `ClusterContext` /
`LabelQueueContract`). The 30s dry-run + 5min real public WS
smoke evidence captured under `docs/PHASE_GATE.md` §"Phase
11C.1C-B acceptance evidence (closeout)" was accepted; PR #38
has merged into `main`. Every Phase 1 safety flag remained
`False` end-to-end across the acceptance runs. Phase 11C.1C-B
is **NOT** live trading, **NOT** AI Learning, **NOT** complete
Strategy Validation, **NOT** the full MFE/MAE processor — those
are reserved for Phase 11C.1C-C. The Phase 1 safety lock and
every Phase 11C.1B / 11C.1C-A forbidden item carry over
unchanged; Phase 12 (live trading) stays `FORBIDDEN`.

Phase 11C.1C-B shipped:

  - **Runtime calibration metrics** attached to every adaptive
    candidate: `candidate_first_seen_ts`,
    `candidate_first_seen_price`, `current_price`,
    `price_change_since_first_seen`,
    `quote_volume_acceleration_1m`,
    `quote_volume_acceleration_5m`, `price_acceleration_1m`,
    `price_acceleration_5m`, `volume_rank`, `volume_rank_jump_5m`,
    `distance_to_24h_high`, `distance_from_first_seen`,
    `freshness_score`, `late_chase_risk`, `early_tail_score`.
  - **Early Tail Discovery v0.** The candidate pool's capacity
    eviction does NOT discard candidates with high
    `early_tail_score`. The radar surfaces volume-rank jumps,
    quote-volume accelerations, and price accelerations on
    EDEN / ALT / NEAR-style demon-coin starts EARLIER than
    Phase 11C.1B's flat radar score.
  - **Stage calibration.** ``early`` + high volume expansion +
    high freshness MAY enter ``follow`` / ``pullback`` (paper /
    virtual). ``late`` / ``blowoff`` MUST NEVER upgrade to
    ``follow``. ``manipulation_risk`` high MUST ``reject`` or
    ``observe``.
  - **Daily-report enhancements.** New fields:
    `top_early_tail_candidates`, `top_late_chase_risk_candidates`,
    `early_tail_score_top_symbols`,
    `opportunity_score_distribution`,
    `symbols_promoted_before_24h_top_move`, plus EDEN / ALT /
    NEAR style candidate examples when present.
  - **Event / export compatibility.** Every new field lands in
    `EventRepository`, the Phase 8.5 learning-ready payload, the
    daily report, and the Phase 8.5 export. Phase 10A replay
    accepts the new fields without failure.

Phase 11C.1C-B is **paper-mode only**. The new
`early_tail_score` is a descriptive / paper field that protects
a candidate from capacity-driven eviction in the candidate pool
but does NOT authorise opening a real position. The Risk Engine
remains the single trade-decision gate; `stop_unconfirmed=True`
continues to lock the WS-radar chain into the typed-reject path.

> Phase 11C.1C-B specifically does NOT authorise:
>
>   - live trading
>   - Binance API key / secret
>   - signed endpoint
>   - private websocket
>   - listenKey
>   - account / order / position / leverage / margin endpoint
>   - DeepSeek trade decision
>   - real Telegram outbound
>   - Phase 12
>   - AI Learning
>   - the full MFE/MAE processor
>   - real orders
>   - promoting `early_tail_score` / `strategy_mode` to a
>     real-trade authority

See `docs/PHASE_11C_1C_B_RUNTIME_CALIBRATION.md` for the full
runtime-calibration first-version contract; see
`docs/PHASE_GATE.md` §"Phase 11C.1C-B acceptance evidence
(closeout)" for the acceptance smoke evidence numerics.

## Closed phase: Phase 11C.1C-A (acceptance closeout)

**Phase 11C.1C-A — Adaptive Candidate Regime & Strategy Selector
Contracts (PR #36).** Status: **ACCEPTED (closed 2026-05-22; PR
#36 merged; PR #37 docs closeout).** Phase 11C.1C-A shipped the
**paper-only first version** of the data contracts + scoring +
selector + paper-only routing for the Adaptive Candidate Regime &
Strategy Selector. The 30s dry-run + 5min real public WS smoke
evidence captured under `docs/PHASE_GATE.md` §"Phase 11C.1C-A
acceptance evidence" was accepted; PR #36 has merged into
`main`; PR #37 closed out the docs gate. Every Phase 1 safety
flag remained `False` end-to-end across the acceptance runs.
Phase 11C.1C-A is **NOT** live trading, **NOT** AI Learning,
**NOT** complete Strategy Validation, **NOT** the full MFE/MAE
processor — those are reserved for later PRs (Phase 11C.1C-B /
11C.1C-C). The Phase 1 safety lock and every Phase 11C.1B
forbidden item carry over unchanged; Phase 12 (live trading)
stays `FORBIDDEN`.

See `docs/PHASE_11C_1C_ADAPTIVE_CANDIDATE_REGIME_STRATEGY_SELECTOR.md`
for the full first-version contract.

## Phase 11C.1B acceptance evidence (closeout)

Phase 11C.1B closed on **2026-05-22 (UTC)** with the following
evidence on file. Full numerics live in
`docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; this section
is the at-a-glance summary.

### PRs that compose Phase 11C.1B

| PR    | Scope                                                                                                | Status |
| ----- | ---------------------------------------------------------------------------------------------------- | ------ |
| #31   | Phase 11C.1A — Binance Public REST Governor / 429 backoff / 418 shutdown protection                  | merged |
| #32   | Phase 11C.1B PR-B — WebSocket-first all-market radar; real `StdlibPublicWSTransport`; routed `/public/stream` + `/market/stream` | merged |
| #33   | Phase 11C.1B follow-up — fix real WS poll zero-timeout that left `ws_messages_received=0`             | merged |
| #34   | Phase 11C.1B follow-up — `SymbolUniverse` / exchangeInfo-as-truth; non-ASCII contracts admitted; ASCII-only regex banned | merged |

### Real-WS smoke ladder (PASS)

| Smoke run        | Duration | Outcome | Headline metrics                                                                                                              |
| ---------------- | -------- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 5 min real WS    | 5 min    | PASS    | `ws_messages_received=30317`, `ws_chains_emitted=12`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 10 min real WS   | 608 s    | PASS    | `ws_messages_received=59644`, `ws_chains_emitted=27`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 1 h real WS (clean) | 3600 s | PASS    | `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=349134`, `ws_chains_emitted=177`, `ws_learning_ready_attached=177`, `snapshots_emitted=177`, `ingestion_errors=0`, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_staleness_ms_max=0`, `ws_stale_count=0`, `ws_currently_stale=False` |

### Persistence + export evidence

  - `events.db` readable: `events_count=56644`. The event-aggregation
    query passed without traceback.
  - Phase 8.5 export: generated successfully; export files are zip
    archives.
  - Demon-coin discovery sanity: `EDENUSDT` appeared in the radar
    top-symbols list AND in the top event-volume aggregation, which
    is the qualitative evidence that the WS-first all-market radar
    is functioning end-to-end.

### Safety boundary held throughout the Phase 11C.1B acceptance run

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none (`/private` refused at allowlist)
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

## Phase 11C.1B — what it ships (closeout reference)

PR-B adds three new modules + extends two existing ones:

  - `app/exchanges/binance_public_ws.py` -
    `BinancePublicWSClient` + `WSConfig` + `WSMessage` +
    `WSMessagePump` + `InProcessWSPump` + `_RefusalTransport`
    (default; refuses any real-network call) +
    **`StdlibPublicWSTransport`** (real-network RFC 6455 client
    built on the Python standard library only, route-aware) +
    **`MultiTransportPublicWSManager`** (owns one routed
    `StdlibPublicWSTransport` per route - PUBLIC + MARKET - and
    merges their messages behind a single `WSMessagePump`
    interface) + `create_real_public_ws_transport` factory +
    `classify_stream_route` + `split_streams_by_route` +
    `assert_public_ws_stream_allowed` +
    `assert_public_ws_url_allowed` +
    `assert_public_ws_path_allowed`. Stream allowlist:
    `!ticker@arr`, `!miniTicker@arr`, `!bookTicker`,
    `!markPrice@arr`, `!forceOrder@arr`. Stream-route
    classification: `!bookTicker` is the PUBLIC route;
    `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` /
    `!forceOrder@arr` are the MARKET route. Path-root
    acceptance allowlist: `/public/ws`, `/public/stream`,
    `/market/ws`, `/market/stream` (legacy unrouted `/ws` /
    `/stream` are kept as back-compat for the in-process pump
    fixtures only). Forbidden path roots: `/private`, `/ws-api`,
    `/ws-fapi`, `/ws-papi`, `/trading-api`, `/userDataStream`.
    Host allowlist: `fstream.binance.com`,
    `fstream.binancefuture.com`. The transport refuses every
    credential-shaped kwarg (`api_key` / `api_secret` /
    `listen_key` / `token` / `signature` / `passphrase`) and
    never reads `BINANCE_API_KEY` / `BINANCE_API_SECRET`.
  - `app/market_data_public/radar.py` -
    `AllMarketRadarSnapshot` (frozen pydantic model) +
    `AllMarketRadarBuffer` (per-symbol rolling state) +
    `pre_anomaly_score_light` (pure additive scoring with
    deterministic reason tags).
  - `app/market_data_public/candidate_pool.py` - `CandidatePool`
    with default `candidate_pool_size=20`, `active_detail_limit=3`,
    `candidate_ttl_seconds=900`. Each candidate carries a
    Phase 8.5 `OpportunityIdentity` with
    `source_phase="phase_11c_1b_ws_first_radar"`.
  - `app/market_data_public/ws_radar_chain.py` -
    `WSRadarChainDriver` emits PRE_ANOMALY_DETECTED ->
    ANOMALY_DETECTED -> STATE_TRANSITION (+ Phase 8.5
    LearningReadyContext on each, + RISK_REJECTED via the live
    RiskEngine) per ACTIVE candidate.
  - `app/core/events.py` - three new EventType entries:
    `PUBLIC_WS_CONNECTED`, `PUBLIC_WS_DISCONNECTED`,
    `PUBLIC_WS_STALE`.
  - `app/paper_run/daily_report.py` - `DailyReportSnapshot` +
    `DailyReportBuilder` extended with WS + radar metrics; new
    `Phase 11C.1B WebSocket all-market radar` Markdown section.
  - `scripts/run_public_market_paper.py` - new CLI flags
    `--ws-first` (default ON) / `--ws-disabled` (mutex),
    `--candidate-pool-size`, `--active-detail-limit`,
    `--ws-staleness-threshold-ms`, `--candidate-ttl-seconds`. The
    runner pumps WS -> ingest into radar -> score every snapshot
    -> offer to pool -> expire stale candidates -> drive
    WSRadarChainDriver on the active head (skipped while
    `ws_client.is_stale=True`, the data-degraded gate); the
    active head also receives REST detail through the existing
    PR-A governor.

### Real routed public WS adapter

PR #32 ships the real-network public WebSocket adapter inline.
**`StdlibPublicWSTransport`** is a single-class, stdlib-only RFC
6455 client; **`MultiTransportPublicWSManager`** owns one of those
adapters per route (PUBLIC + MARKET) and presents them behind a
single `WSMessagePump` interface. The pair targets the documented
Binance USDⓈ-M Futures routed endpoints
(`wss://fstream.binance.com/public/stream` and
`wss://fstream.binance.com/market/stream`). The unrouted
`wss://fstream.binance.com/stream?streams=...` path silently
drops market-class streams (per the Binance public-WS reference)
and is therefore NOT the acceptance path; the routed-private
endpoint `wss://fstream.binance.com/private` is forbidden at the
path-root allowlist (`FORBIDDEN_WS_PATH_ROOTS`). The adapter
performs the HTTP/1.1 Upgrade handshake (`GET <route>/stream` with
`Sec-WebSocket-Key` / `Sec-WebSocket-Version: 13`), validates the
server's `Sec-WebSocket-Accept`, parses RFC 6455 text frames, and
surfaces decoded `WSMessage` envelopes. The third-party WebSocket
package deny-list (`websockets` / `websocket-client` / `aiohttp` /
`requests` / `httpx` / `urllib3`) in
`tests/unit/test_phase11c_no_network.py` continues to hold.

The runner refuses to silently fall back to the PR-A
bootstrap-only REST path: `--ws-first` without `--dry-run`
**requires** a real public WS pump. If the factory returns
`None` or raises, the runner exits with `rc=2` and the message
`real public WebSocket transport is required for --ws-first
without --dry-run`. The only path to REST-only operation is the
explicit `--ws-disabled` flag, documented as NOT the Phase 11C.1B
acceptance path.

## Phase 11C.1B execution modes

| CLI                                       | Behaviour                                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `--ws-first --dry-run` (default)          | In-process pump, deterministic synthetic messages, no socket, full event chain.                                        |
| `--ws-first` (no `--dry-run`)             | Real `MultiTransportPublicWSManager` opening routed PUBLIC (`/public/stream`) + MARKET (`/market/stream`) endpoints. RC=2 if the factory cannot produce one - never silently falls back to REST. |
| `--ws-disabled`                           | PR-A bootstrap-only REST path. Documented as **not** the Phase 11C.1B all-market demon-radar acceptance path.          |


## Architecture governance (guidance-only)

A new architecture governance document has been added to the
repository:

  - `docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` —
    *AMA-RT Adaptive Market Operating System Governance /
    自适应市场操作系统架构治理文档.*

This document is **guidance-only**. It records the long-term
architectural rails of AMA-RT: core positioning ("AMA-RT is
not an auto-trading bot, AMA-RT is an Adaptive Market
Operating System"), AI authority boundaries (LLMs may explain,
LLMs may **not** trade / size / leverage / stop / target),
stateless AI cognition, the Truth Layer, the Reality Check
Layer, anti-overfitting governance, feedback isolation, the
nine-layer architecture, the not-implemented-yet backlog, and
the explicit rejections list (incl. AI autonomous trading,
direct price prediction, RL live trading, black-box parameter
optimisation, AI bypassing the Risk Engine, direct Phase 12
jump).

The governance document **does NOT**:

  - change the current phase,
  - flip any safety flag,
  - authorise any runtime behavior,
  - authorise live trading, API keys, signed endpoints,
    private WebSockets, `listenKey`, DeepSeek trade
    decisions, or real Telegram outbound,
  - advance any later phase to ACCEPTED,
  - kick off Phase 11C.1C-C-B-B-B,
  - authorise Phase 12.

Current phase is now **Phase 11C.1C-C-B-B-B**
(NEXT_ALLOWED / NOT_STARTED) per `docs/PHASE_GATE.md`. Phase
11C.1C-C-B-B-A is **ACCEPTED** (PR #44 merged into `main`,
mergeCommit `3ecfc3b`, 2026-05-23 UTC); current work focus
remains *validation / dataset / quality gate / replay
verification*, and **Phase 12 (real money / live trading)
remains FORBIDDEN**. The Phase 1 safety lock continues to
hold: `mode=paper`, `live_trading=False`, `right_tail=False`,
`llm=False`, `exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no
Binance API secret, no signed endpoint, no private WebSocket,
no `listenKey`, no DeepSeek trade decision, no real Telegram
outbound.




## Phase 11C.1C-C-B-B-B-E-B — Reflection Extension for 11C Adaptive Events v0 (IN_REVIEW)

Phase 11C.1C-C-B-B-B-E-B *Reflection Extension for 11C Adaptive
Events v0* opens as **IN_REVIEW** with this implementation PR. The
phase is the second block of Block C (Block C2 — Reflection
Extension) and is the only phase the C1 Replay Extension PR (PR #78)
authorised.

### What changed

  - Added `app/reflection/adaptive_11c.py`, a read-only reflection
    extension that turns every supported Phase 11C adaptive event
    into one deterministic `AdaptiveReflectionCase` (and aggregates
    them into one `AdaptiveReflectionSummary`). Public surface:
    `AdaptiveReflectionTag` (closed enum of 19 tags including the
    18 brief-mandated tags + `late_discovery`),
    `AdaptiveReflectionSeverity` (closed enum), `Reflection11CAdaptiveEngine`
    (pure stateless engine), `AdaptiveReflectionInput` /
    `AdaptiveReflectionCase` / `AdaptiveReflectionSummary`
    (frozen dataclasses with `to_payload()` plus a recursive
    forbidden-key guard).
  - Wired the new symbols through `app/reflection/__init__.py`.
  - Added `tests/unit/test_reflection_11c_adaptive_events.py`
    covering the brief's required test surface (POST_DISCOVERY_OUTCOME
    tags, REJECT_TO_OUTCOME tags, SEVERE_MISSED_TAIL tags,
    DISCOVERY_QUALITY DEGRADED tag, HISTORICAL_MOVER_COVERAGE missed
    tag, missing-fields-do-not-crash, evidence_refs-preserved,
    auto_tuning_allowed=false on every payload, forbidden-imports
    static check, forbidden-fields-absent guard, deterministic ordering).
  - Added `docs/PHASE_11C_1C_C_B_B_B_E_B_REFLECTION_EXTENSION_11C_EVENTS.md`
    as the phase design / acceptance doc.

### Forbidden / not done in this phase

  - Stage closeout is **not** done.
  - DeepSeek is **not** wired in.
  - Phase 12 is **not** entered.
  - Auto-tuning is **not** enabled. Every emitted case + summary
    carries `auto_tuning_allowed=False`. `to_payload()` hard-pins
    the value to `False` even if a caller overrides it.
  - LLM / natural-language reflection is **not** produced. Tags are
    drawn from a closed enum only.
  - Reflection does **not** depend on chat history or external state.
  - No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
    `app/llm/`, `app/telegram/`, or `app/config/` is touched.
  - No change to `symbol_limit`, anomaly thresholds,
    `candidate_pool`, or regime weights.
  - No `runtime_config_patch` is produced.
  - No `buy` / `sell` / `long` / `short` / `position_size` /
    `leverage` / `stop` / `target` / `risk_budget` field is produced.
  - **Phase 12 remains FORBIDDEN.**

### Safety boundary (held)

`mode=paper`, `live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`, no Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`, no
real Telegram outbound, no DeepSeek trade decision. The Risk Engine
remains the single trade-decision gate.

### Tests

`python -m pytest tests/unit/test_reflection_11c_adaptive_events.py -q`
ships 42 PASSING tests; `python -m pytest tests/unit -q` reports
2680 PASSING tests, 0 failures.

### Successor allowed by this phase

Only **Phase 11C.1C-C-B-B-B-E-C "C3 Evidence Contract Baseline"**
is unlocked by a successful Phase 11C.1C-C-B-B-B-E-B. No other
phase is unlocked. Phase 12 remains **FORBIDDEN**.




## Phase 11C.1C-C-B-B-B-E-A — Replay Extension for 11C Adaptive Events v0 (IN_REVIEW)

Phase 11C.1C-C-B-B-B-E-A *Replay Extension for 11C Adaptive Events
v0* opens as **IN_REVIEW** with this implementation PR. The phase is
the first block of Block C1 (Replay Extension) and is the only phase
the Block B Integrated Evidence Checkpoint
(`PARTIAL_EVIDENCE`, `next_allowed_phase = Phase 11C.1C-C-B-B-B-E-A`)
authorised.

### What changed

  - Added `app/replay/adaptive_replay_11c.py`, a read-only replay
    extension that reconstructs the Phase 11C adaptive / discovery /
    evidence event chain into eight deterministic value objects
    (`ReplayDiscoveryTimeline`, `ReplayCandidateLifecycle`,
    `ReplayTailOutcome`, `ReplayMoverCoverageCase`,
    `ReplayPostDiscoveryOutcomeCase`, `ReplayRejectAttributionCase`,
    `ReplaySevereMissCase`, `ReplayDiscoveryQualityCase`) plus an
    aggregate `AdaptiveReplayBundle`.
  - Wired the new symbols through `app/replay/__init__.py`.
  - Added `tests/unit/test_replay_11c_adaptive_events.py` covering
    the brief's ten required tests (LABEL / TAIL_LABEL,
    HISTORICAL_MOVER_COVERAGE, POST_DISCOVERY_OUTCOME,
    REJECT_TO_OUTCOME, SEVERE_MISSED_TAIL, DISCOVERY_QUALITY,
    missing-fields-do-not-crash, replay-count-equals-input-count,
    forbidden-imports, forbidden-fields-absent).
  - Added `docs/PHASE_11C_1C_C_B_B_B_E_A_REPLAY_EXTENSION_11C_EVENTS.md`
    as the phase design / acceptance doc.

### Forbidden / not done in this phase

  - Reflection (Phase 11C.1C-C-B-B-B-E-B) is **not** started.
  - DeepSeek is **not** wired in.
  - Auto-tuning is **not** enabled (replay payloads explicitly carry
    `auto_tuning_allowed=False` where applicable).
  - No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
    `app/llm/`, `app/telegram/`, or `app/config/` is touched.
  - No change to `symbol_limit`, anomaly thresholds, `candidate_pool`,
    or regime weights.
  - No `runtime_config_patch` is produced.
  - No `buy` / `sell` / `long` / `short` / `position_size` /
    `leverage` / `stop` / `target` / `risk_budget` field is produced.
  - **Phase 12 remains FORBIDDEN.**

### Safety boundary (held)

`mode=paper`, `live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`, no Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`, no
real Telegram outbound, no DeepSeek trade decision. The Risk Engine
remains the single trade-decision gate.

### Successor allowed by this phase

Only **Phase 11C.1C-C-B-B-B-E-B Reflection Extension for 11C
Adaptive Events v0** is unlocked by a successful Phase
11C.1C-C-B-B-B-E-A. No other phase is unlocked. Phase 12 remains
**FORBIDDEN**.




## Phase 11C.1C-C-B-B-B-E-C — Evidence Contract Baseline v0 (IN_REVIEW)

Phase 11C.1C-C-B-B-B-E-C *Evidence Contract Baseline v0* opens as
**IN_REVIEW** with this implementation PR. The phase is the third
block of Block C (Block C3) and is the only phase the merged Block
C1 + Block C2 implementations authorised next.

### What changed

  - Added `app/evidence/` (new package) with
    `app/evidence/evidence_contract.py`. The module ships:
    `EvidenceRefType` (closed enum), `ClaimStatus` (closed enum),
    `EvidenceRef`, `EvidenceClaimInput`, `EvidenceClaim`,
    `EvidenceContractResult` value objects,
    `parse_evidence_ref(raw)`, `EvidenceContractValidator`,
    `validate_claims(claims)` convenience wrapper, and a
    recursive `FORBIDDEN_EVIDENCE_PAYLOAD_KEYS` guard invoked from
    every `to_dict()` boundary.
  - `app/core/events.py` — added three descriptive event types:
    `EVIDENCE_CONTRACT_VALIDATED`, `EVIDENCE_CLAIM_DEGRADED`,
    `EVIDENCE_CLAIM_REJECTED`. No trade-action / position /
    sizing / risk-budget event was added.
  - Added `tests/unit/test_evidence_contract_baseline.py` covering
    the brief's ten required tests (event ref parses, symbol /
    opportunity / report ref parses, claim without refs degraded,
    invalid ref rejected / degraded, multi-ref preserved,
    no-hallucinated-refs, summary counts correct, forbidden
    fields absent, forbidden imports, deterministic output) plus
    closed-vocabulary integrity and Mapping-input compatibility.
    The new test module ships **31 PASSING** tests.
  - Added
    `docs/PHASE_11C_1C_C_B_B_B_E_C_EVIDENCE_CONTRACT_BASELINE.md`
    as the phase design / acceptance doc.

### Forbidden / not done in this phase

  - Block C closeout is **not** done. Closeout is done per-block,
    not per-PR.
  - DeepSeek is **not** wired in.
  - Phase 12 is **not** entered. **Phase 12 remains FORBIDDEN.**
  - Auto-tuning is **not** enabled. Every emitted
    `EvidenceContractResult` carries `auto_tuning_allowed=False`;
    `to_dict()` hard-pins the value to `False` even if a caller
    overrides it.
  - LLM / natural-language reasoning is **not** produced. Statuses
    are drawn from a closed enum only.
  - The validator does **not** depend on chat history or external
    state.
  - No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
    `app/llm/`, `app/telegram/`, or `app/config/` is touched.
  - No change to `symbol_limit`, anomaly thresholds,
    `candidate_pool`, or regime weights.
  - No `runtime_config_patch` is produced.
  - No `buy` / `sell` / `long` / `short` / `position_size` /
    `leverage` / `stop` / `target` / `risk_budget` field is
    produced.
  - This phase does **NOT** retrofit existing Block A / Block B
    surfaces. Their `evidence_refs: tuple[str, ...]` fields
    continue to ship as before.

### Safety boundary (held)

`mode=paper`, `live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`, no Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`, no
real Telegram outbound, no DeepSeek trade decision. The Risk Engine
remains the single trade-decision gate.

### Tests

`python -m pytest tests/unit/test_evidence_contract_baseline.py -q`
ships **31 PASSING** tests; `python -m pytest tests/unit -q`
reports **2711 PASSING** tests, 0 failures (was 2680 before this
phase; +31 from this phase).

### Successor allowed by this phase

Only the upcoming **Block C closeout** (whole-block, after C1 + C2
+ C3 are merged and reviewed) **OR** the eventual **AI Evidence
Bundle preparation** is unlocked by a successful Phase
11C.1C-C-B-B-B-E-C. No other phase is unlocked. Phase 12 remains
**FORBIDDEN**.
