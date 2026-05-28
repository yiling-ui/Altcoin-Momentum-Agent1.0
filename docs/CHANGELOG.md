# Changelog

All notable changes to AMA-RT will be recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the project phase plan in `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` §43.

## [Unreleased]

### Phase AI-CHECKPOINT — AI Integrated Checkpoint v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence-only).
**Runtime effect:** **none on real trading.** One new runner
`scripts/run_ai_integrated_checkpoint.py`, one new unit-test
module `tests/unit/test_ai_integrated_checkpoint.py` (22
PASSING tests covering all 15 brief-mandated scenarios plus
output paths, CLI exit codes, the degraded-claim path, and a
`socket.socket`-monkeypatched no-network test), and one new
phase doc `docs/PHASE_AI_INTEGRATED_CHECKPOINT.md`. No file
under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, no file under `app/ai/`,
`app/replay/`, or `app/reflection/`, no event type wired into
the runtime hot path, and no database schema / migration is
touched. The runner reads only local files under
`--block-c-report` / `--evidence-bundle` / `--sandbox-output`
/ `--operator-briefing-dir` and writes only files under
`--output-dir`. The runner aggregates the simplified outputs
of the six already-merged AI-Layer slices (AI-1 Evidence
Bundle Builder, AI-2 Evidence Citation Contract, AI-3
Reality Check Layer, AI-4 DeepSeek Offline Sandbox / Fake
Provider, AI-5 Operator Briefing / Evidence Compression,
AI-6 AI Replay / Reflection Integration) into one
descriptive `ai_integrated_checkpoint_report.json` (plus
its Markdown twin) and surfaces one of three closed
statuses (`INSUFFICIENT_EVIDENCE`, `PARTIAL_EVIDENCE`,
`EVIDENCE_GENERATED`) and the corresponding
`next_allowed_phase`. When an input is missing on disk the
runner substitutes a deterministic fallback fixture marked
`source=fallback_fixture`; the fallback NEVER carries
fabricated market conclusions. The runner imports only
`app.ai.evidence_bundle` (for the canonical forbidden-field
list) and `app.reflection.ai_reflection` (for the AI-6
convenience wrapper); it does **NOT** import `app.risk`,
`app.execution`, `app.exchanges`, `app.telegram`, or
`app.config`; it does **NOT** import any HTTP / network
library (`openai`, `anthropic`, `deepseek`, `httpx`,
`requests`, `aiohttp`, `urllib3`, `websocket`, `websockets`,
`grpc`, `boto3`, `socket`). A unit test additionally
monkeypatches `socket.socket` to refuse-on-call and runs
the full `EVIDENCE_GENERATED` path to prove no socket is
opened. The `--use-fake-provider` flag is descriptive only;
the runner NEVER opens the network regardless of its
value. Every emitted payload re-pins the project-wide
invariants at the serialisation boundary
(`mode=paper`, `live_trading=False`,
`exchange_live_orders=False`, `right_tail=False`,
`llm=False`, `llm_outbound_enabled=False`,
`sandbox_only=True`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`,
`trade_authority=False`, `auto_tuning_allowed=False`,
`phase_12_forbidden=True`, `stateless_inference=True`,
`feedback_isolation=True`,
`ai_output_is_commentary_only=True`,
`ai_output_can_be_truth=False`,
`ai_output_can_be_training_label=False`,
`ai_output_can_be_tail_label=False`,
`ai_output_can_be_strategy_sample=False`); the recursive
`_assert_no_forbidden_keys` guard refuses to emit any
payload that carries a trade-action / runtime-config-patch
/ "live ready" / "trading approved" / "phase_12_allowed"
key at any nesting depth.

**Phase ledger effect:** opens Phase AI-CHECKPOINT as
**`IN_REVIEW`** (not `ACCEPTED` until maintainer review of
the PR). **Safety flag effect:** **none.** The Risk Engine
remains the single trade-decision gate.

**What this PR does NOT do:** it does **NOT** authorise
live trading, **NOT** trade authority, **NOT** auto-
tuning, **NOT** the DeepSeek hot path, **NOT** Telegram
live outbound, **NOT** any live LLM call, **NOT** a Rule
Sandbox, **NOT** a Paper Shadow, **NOT** the AI Layer's
involvement in the Risk Engine / Execution FSM /
StrategyEngine / RuntimeConfig, **NOT** any direction call
(long / short / entry / exit / stop / target / position
size / leverage). **AI output is commentary substrate; AI
output cannot become Truth Layer fact, training label,
tail label, or strategy validation sample.** **NOT** Phase
12. **Phase 12 remains FORBIDDEN.**

**Tests:**
`python -m pytest tests/unit/test_ai_integrated_checkpoint.py -q`
ships 22 PASSING tests.

**Successor allowed by this phase:** only the upcoming
*Offline Rule Sandbox Replay v0* preparation work (paper /
read-only) is unlocked when `status=EVIDENCE_GENERATED`;
*Offline Rule Sandbox Replay preparation / AI operator
evidence run* (paper / read-only) is unlocked when
`status=PARTIAL_EVIDENCE`; `NEEDS_AI_OPERATOR_EVIDENCE` is
the next signal when `status=INSUFFICIENT_EVIDENCE`. No
other phase is unlocked. Phase 12 remains **FORBIDDEN**.

### Phase AI-6 — AI Replay / Reflection Integration v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / sandbox-only).
**Runtime effect:** **none on real trading.** Two new
read-only modules `app/replay/ai_replay.py` and
`app/reflection/ai_reflection.py` are added alongside the
existing Phase 10A / 10B / 11C replay / reflection surfaces,
with `app/replay/__init__.py` and
`app/reflection/__init__.py` extended to re-export the
Phase AI-6 public surface, plus a matching unit-test module
under `tests/unit/test_ai_replay_reflection_integration.py`
(164 tests). No file under `app/risk/`, `app/execution/`,
`app/exchanges/`, `app/telegram/`, `app/config/`, no file
under `app/ai/`, no event type already wired into the
runtime, no database schema / migration is touched. The
modules are read-only at runtime: they never append,
mutate, or reorder rows in `events.db`; they never produce
direction, sizing, leverage, stop, target, or risk-budget
fields; they never produce a `runtime_config_patch`; and
they never call any LLM / DeepSeek / network transport. No
runtime knob (`symbol_limit`, anomaly threshold, candidate
pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase AI-6 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`llm_outbound_enabled=False`, `sandbox_only=True`,
`allow_trade_decision=False`,
`allow_runtime_config_change=False`,
`require_evidence_refs=True`,
`require_reality_check=True`,
`stateless_inference=True`,
`feedback_isolation=True`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no
API secret, no signed endpoint, no private WebSocket, no
`listenKey`, no DeepSeek trade decision, no real DeepSeek
HTTP transport, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.**
`auto_tuning_allowed=False` is hard-pinned at every
`to_dict()` boundary even if a caller flips the dataclass
field. The recursive `_assert_no_forbidden_fields` guard
refuses to emit any payload carrying a `*_patch` key.
**AI output isolation:** every emitted payload re-pins
`ai_output_can_be_truth=False`,
`ai_output_can_be_training_label=False`,
`ai_output_can_be_tail_label=False`,
`ai_output_can_be_strategy_sample=False`,
`ai_output_is_commentary_only=True` at every `to_dict()`
boundary even if a caller flips the dataclass field via
`object.__setattr__`.
**Successor allowed:** later (separately gated) **AI
Integrated Checkpoint** that aggregates Phase AI-1 / AI-2 /
AI-3 / AI-4 / AI-5 / AI-6 outputs into one offline audit
report. **NOT** the real DeepSeek HTTP transport. **NOT**
DeepSeek trade decisions. **NOT** the AI Layer's
involvement in the Risk Engine. **NOT** the AI Layer's
involvement in the Execution FSM. **NOT** auto-tuning.
**NOT** real Telegram outbound. **NOT** Operator Briefing
live publishing. **NOT** Rule Sandbox. **NOT** Paper
Shadow. **NOT** Phase 12.

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).** This slice ships
> the AI Layer's first **audit integration** runtime
> artefact — the AI Replay / Reflection Integration v0.
> The integration consumes the Phase AI-1
> :class:`AIEvidenceBundle`, the Phase AI-4
> :class:`AIIntelligenceOutput`, the Phase AI-5
> :class:`OperatorBriefing`, and the Phase AI-5
> :class:`EvidenceCompressionReport` JSON artefacts and
> projects them into structural :class:`AIReplayCase`
> value objects (one per artefact); aggregates the cases
> into one :class:`AIReplaySummary`; reflects each case
> through the closed :class:`AIReflectionTag` vocabulary
> into one :class:`AIReflectionCase`; and aggregates the
> reflection cases into one
> :class:`AIReflectionSummary`. The integration NEVER
> imports `app.risk` / `app.execution` / `app.exchanges` /
> `app.telegram` / `app.config`; it NEVER reads private
> exchange / account state; it NEVER carries an API
> secret in any logged / exported / serialised payload;
> it NEVER authorises a trade decision or auto-tuning.
> The maximum any case can reach is *commentary
> substrate* — **AI output cannot become Truth Layer
> fact, training label, tail label, or strategy
> validation sample**. The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced
> in code AND in tests. **Phase 12 remains FORBIDDEN.**
> The Risk Engine remains the single trade-decision gate.

#### Added

- `app/replay/ai_replay.py` — paper / pure /
  deterministic replay module. Ships:
  - `AIReplaySourceKind` closed string vocabulary with 4
    values: `evidence_bundle`, `ai_intelligence_output`,
    `operator_briefing`, `evidence_compression_report`.
  - `AIReplayCase` frozen dataclass with the brief-
    mandated fields: `case_id`, `bundle_id`,
    `ai_output_id`, `task_type`, `source_kind`,
    `source_report_paths`, `claim_count`,
    `supported_claim_count`, `unsupported_claim_count`,
    `contradicted_claim_count`, `degraded_claim_count`,
    `rejected_claim_count`,
    `reality_check_status_summary`, `evidence_refs`,
    `forbidden_fields_stripped`,
    `redacted_secret_count`, `risk_tags`,
    `notable_symbols`, `warnings`, `degraded_reasons`,
    `timestamp_utc`, plus the hard-pinned
    `trade_authority=False`,
    `auto_tuning_allowed=False`,
    `phase_12_forbidden=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_truth=False`,
    `ai_output_can_be_training_label=False`,
    `ai_output_can_be_tail_label=False`,
    `ai_output_can_be_strategy_sample=False` flags.
    Re-pinned at every `to_dict()` boundary even if a
    caller flips the dataclass field via
    `object.__setattr__`.
  - `AIReplaySummary` frozen dataclass with the brief-
    mandated counts: `total_cases`,
    `evidence_bundle_count`,
    `ai_intelligence_output_count`,
    `operator_briefing_count`,
    `evidence_compression_count`,
    `supported_claim_count`,
    `unsupported_claim_count`,
    `contradicted_claim_count`,
    `reality_check_failed_count`,
    `missing_evidence_count`,
    `forbidden_field_stripped_count`,
    `degraded_run_count`, `redacted_secret_count`,
    `evidence_refs`, `notable_symbols`, `warnings`,
    `cases`.
  - `AIReplayBuilder` (and the
    `build_ai_replay_case` /
    `build_ai_replay_summary` convenience wrappers) —
    deterministic; auto-detects source kind from the
    artefact's `source_module` / shape; never invents
    a missing `evidence_refs` entry; never paraphrases
    a claim_text; never imports the Risk / Execution /
    Exchange / Telegram / Config / LLM / network
    surfaces; refuses payloads carrying forbidden
    trade-action / runtime-config-patch keys via the
    Phase AI-1 recursive
    `_assert_no_forbidden_fields` guard.
  - Closed event-type string constants
    `AI_REPLAY_CASE_RECONSTRUCTED` and
    `AI_REPLAY_SUMMARY_GENERATED`. Neither is wired
    into the runtime hot path; they are not registered
    in `app.core.events.EventType`.
- `app/reflection/ai_reflection.py` — paper / pure /
  deterministic reflection module. Ships:
  - `AIReflectionTag` closed string enum with 10
    allowed values: `ai_helpful_explanation`,
    `ai_unsupported_claim`,
    `ai_contradicted_by_truth_layer`,
    `ai_reality_check_failed`,
    `ai_evidence_missing`,
    `ai_narrative_pollution_risk`,
    `ai_forbidden_field_stripped`,
    `ai_degraded_output`,
    `ai_operator_briefing_generated`,
    `ai_evidence_compression_generated`. The
    brief-forbidden tags `ai_said_buy`,
    `ai_said_long`, `ai_target_hit`,
    `ai_direction_correct`,
    `ai_trade_signal_correct` are intentionally
    **omitted** from the enum.
  - `FORBIDDEN_REFLECTION_TAGS` frozenset that exposes
    the 5 forbidden tag strings for downstream audit.
  - `AIReflectionSeverity` closed string enum with 5
    values: `info`, `low`, `medium`, `high`,
    `unknown`.
  - `AIReflectionCase` frozen dataclass with
    `case_id`, `bundle_id`, `ai_output_id`,
    `source_kind`, `tags`, `severity`,
    `evidence_refs`, `needs_operator_review`,
    `warnings`, plus the hard-pinned
    `trade_authority=False`,
    `auto_tuning_allowed=False`,
    `phase_12_forbidden=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_truth=False`,
    `ai_output_can_be_training_label=False`,
    `ai_output_can_be_tail_label=False`,
    `ai_output_can_be_strategy_sample=False` flags.
    Re-pinned at every `to_dict()` boundary even if a
    caller flips the dataclass field via
    `object.__setattr__`.
  - `AIReflectionSummary` frozen dataclass with
    `total_cases`, `tag_counts`, `severity_counts`,
    `needs_operator_review_count`, `evidence_refs`,
    `warnings`, `cases`.
  - `AIReplayReflectionEngine` — stateless one-shot
    engine combining replay + reflection. Public
    surface: `reflect_replay_case`,
    `reflect_replay_cases`, `replay_and_reflect`.
    Convenience module-level wrappers:
    `reflect_replay_case`, `reflect_replay_cases`,
    `replay_and_reflect_artefacts`.
  - Closed event-type string constants
    `AI_REFLECTION_CASE_GENERATED` and
    `AI_REFLECTION_SUMMARY_GENERATED`. Neither is
    wired into the runtime hot path; they are not
    registered in `app.core.events.EventType`.
- `app/replay/__init__.py` — extended re-exports for the
  Phase AI-6 public API alongside the existing Phase 10A /
  11C surfaces:
  `AI_REPLAY_CASE_RECONSTRUCTED`,
  `AI_REPLAY_SUMMARY_GENERATED`,
  `AIReplayBuilder`, `AIReplayCase`,
  `AIReplaySourceKind`, `AIReplaySummary`,
  `build_ai_replay_case`, `build_ai_replay_summary`.
- `app/reflection/__init__.py` — extended re-exports for
  the Phase AI-6 public API alongside the existing
  Phase 10B / 11C surfaces:
  `AI_REFLECTION_CASE_GENERATED`,
  `AI_REFLECTION_SUMMARY_GENERATED`,
  `AIReflectionCase`, `AIReflectionSeverity`,
  `AIReflectionSummary`, `AIReflectionTag`,
  `AIReplayReflectionEngine`,
  `FORBIDDEN_REFLECTION_TAGS`,
  `reflect_replay_case`, `reflect_replay_cases`,
  `replay_and_reflect_artefacts`.
- `tests/unit/test_ai_replay_reflection_integration.py`
  (177 cases) covering every brief-mandated scenario:
  builds replay case from operator briefing /
  evidence-compression / AI-intelligence /
  evidence-bundle artefacts; preserves `evidence_refs`
  on replay AND reflection; unsupported claims create
  `AI_UNSUPPORTED_CLAIM` tag; contradicted claims
  create `AI_CONTRADICTED_BY_TRUTH_LAYER` tag; failed
  Reality Check creates `AI_REALITY_CHECK_FAILED` tag
  (parametrised over `CONTRADICTED` and
  `REJECTED_LOOKAHEAD` paths); missing evidence
  creates `AI_EVIDENCE_MISSING` tag (parametrised over
  the degraded-claims path and the no-refs-with-claims
  path); forbidden fields stripped creates
  `AI_FORBIDDEN_FIELD_STRIPPED` tag; AI output cannot
  become truth / training label / tail label /
  strategy validation sample (parametrised over 4
  flags on both replay and reflection cases, with
  mutation defence verified via `object.__setattr__`);
  `trade_authority=False`,
  `auto_tuning_allowed=False`,
  `phase_12_forbidden=True` (asserted on replay,
  reflection, and summary payloads); forbidden fields
  absent at every nesting depth (parametrised over 29
  fields on both replay and reflection); a smuggled
  forbidden key (`leverage` / `runtime_config_patch`)
  in the intake mapping causes `build_ai_replay_case`
  to raise; no Risk / Execution / Exchanges / Telegram
  / Config consumer of Phase AI-6 modules
  (parametrised over 5 packages, AST + string scan);
  JSON output serializable (4 dataclass kinds);
  deterministic output (same input ⇒ identical
  `to_dict()` and `json.dumps()`); forbidden imports
  absent on both Phase AI-6 modules (parametrised over
  13 forbidden packages including `app.risk`,
  `app.execution`, `app.exchanges`, `app.telegram`,
  `app.config`, `openai`, `anthropic`, `deepseek`,
  `httpx`, `requests`, `aiohttp`, `urllib3`,
  `websocket`, `websockets`, `grpc`, `boto3`,
  `socket`); no live LLM / DeepSeek call shape
  (parametrised string scan); forbidden reflection
  tags never emitted (parametrised over 5 forbidden
  tags); allowed reflection tags present in enum
  (parametrised over 10 allowed tags); event-type
  constants are correct strings; replay summary
  evidence_refs de-duplicated; replay builder rejects
  non-Mapping inputs; reflection engine rejects
  non-`AIReplayCase` inputs; replay artefact accepts
  objects with a `to_dict()` method; replay summary
  counts match inputs; reflection summary tag counts
  cover both `OPERATOR_BRIEFING_GENERATED` and
  `EVIDENCE_COMPRESSION_GENERATED`; replay case
  round-trip JSON preserves every documented field.
- `docs/PHASE_AI_6_REPLAY_REFLECTION_INTEGRATION.md` —
  this phase's design document.

#### Changed

- `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
  `docs/CHANGELOG.md` (this entry) updated to reflect
  Phase AI-6 = **IN_REVIEW**.

#### Tests

- `python -m pytest tests/unit/test_ai_replay_reflection_integration.py -q`:
  PASS.
- `python -m pytest tests/unit -q`: 3305 PASS / 0 fail
  (was 3141 before this phase; +164 from this phase).

#### Safety boundary (held end-to-end)

- `mode = paper`
- `live_trading = False`
- `exchange_live_orders = False`
- `right_tail = False`
- `llm = False`
- `llm_outbound_enabled = False`
- `sandbox_only = True`
- `allow_trade_decision = False`
- `allow_runtime_config_change = False`
- `require_evidence_refs = True`
- `require_reality_check = True`
- `stateless_inference = True`
- `feedback_isolation = True`
- `telegram_outbound_enabled = False`
- `binance_private_api_enabled = False`
- no Binance API key / secret
- no signed endpoint
- no private WebSocket
- no `listenKey`
- no real Telegram outbound
- no DeepSeek trade decision
- no real DeepSeek HTTP transport
- **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

#### Phase status

Phase AI-6 = **IN_REVIEW** after this implementation PR.
Not `ACCEPTED`. Not live ready. Not trade authority granted.
Not real DeepSeek HTTP transport. Not Operator Briefing live
publishing. Not Rule Sandbox. Not Paper Shadow. Not
auto-tuning. **Phase 12 = FORBIDDEN.**

### Phase AI-5 — Operator Briefing / Evidence Compression v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / sandbox-only).
**Runtime effect:** **none on real trading.** Two new
read-only modules `app/ai/operator_briefing.py` and
`app/ai/evidence_compression.py` are added alongside the
existing `app/ai/evidence_bundle.py` (Phase AI-1),
`app/ai/claim_contract.py` (Phase AI-2),
`app/ai/reality_check.py` (Phase AI-3),
`app/ai/intelligence_schema.py` (Phase AI-4), and
`app/ai/deepseek_sandbox.py` (Phase AI-4), with
`app/ai/__init__.py` extended to re-export the Phase AI-5
public surface, plus a new offline CLI runner
`scripts/run_ai_operator_briefing.py` and a matching
unit-test module under
`tests/unit/test_ai_operator_briefing.py` (113 tests). No
file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`,
`app/ai/evidence_bundle.py`, `app/ai/claim_contract.py`,
`app/ai/reality_check.py`,
`app/ai/intelligence_schema.py`, or
`app/ai/deepseek_sandbox.py`, no event type already wired
into the runtime, no database schema / migration is touched.
The modules are read-only at runtime: they never append,
mutate, or reorder rows in `events.db`; they never produce
direction, sizing, leverage, stop, target, or risk-budget
fields; they never produce a `runtime_config_patch`; and
they never call any LLM / DeepSeek / network transport. No
runtime knob (`symbol_limit`, anomaly threshold, candidate
pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase AI-5 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`llm_outbound_enabled=False`, `sandbox_only=True`,
`allow_trade_decision=False`,
`allow_runtime_config_change=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no
API secret, no signed endpoint, no private WebSocket, no
`listenKey`, no DeepSeek trade decision, no real DeepSeek
HTTP transport, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.**
`auto_tuning_allowed=False` is hard-pinned at every
`to_dict()` boundary even if a caller flips the dataclass
field. The recursive `_assert_no_forbidden_fields` guard
refuses to emit any payload carrying a `*_patch` key.
**Successor allowed:** later (separately gated) **Phase AI-6
Replay / Reflection Integration of AI outputs** that
consumes the Phase AI-5 `OperatorBriefing` artefact and
records it in the replay / reflection artefacts as an
*annotation* (still paper / report / sandbox-only). **NOT**
the real DeepSeek HTTP transport. **NOT** DeepSeek trade
decisions. **NOT** the AI Layer's involvement in the Risk
Engine. **NOT** the AI Layer's involvement in the Execution
FSM. **NOT** auto-tuning. **NOT** real Telegram outbound.
**NOT** Operator Briefing live publishing. **NOT** Phase 12.

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).** This slice ships
> the AI Layer's first **human-readable operator briefing**
> runtime artefact - the Operator Briefing / Evidence
> Compression v0. The builder consumes a Phase AI-1
> evidence bundle JSON, a Phase AI-4 sandbox output JSON,
> and an optional Block C Integrated Checkpoint report
> JSON; classifies every claim into the closed compression
> vocabulary (`SUPPORTED` / `UNSUPPORTED` /
> `DEGRADED_NO_EVIDENCE` / `REJECTED` / `CONTRADICTED` /
> `COMMENTARY_ONLY`); groups findings into the closed
> :class:`OperatorBriefingSection` vocabulary (12 values:
> `EXECUTIVE_SUMMARY`, `MARKET_INTELLIGENCE`,
> `DISCOVERY_QUALITY`, `COVERAGE_AUDIT`,
> `POST_DISCOVERY_OUTCOME`, `REJECT_ATTRIBUTION`,
> `SEVERE_MISS_TRIAGE`, `REPLAY_REFLECTION`,
> `CONTRADICTIONS`, `UNSUPPORTED_CLAIMS`, `DATA_GAPS`,
> `OPERATOR_ACTION_ITEMS`); strips forbidden trade-action
> / runtime-config-patch fields (defence in depth);
> redacts credential-shaped keys (defence in depth); and
> emits two deterministic, JSON-serialisable artefacts:
> :class:`OperatorBriefing` and
> :class:`EvidenceCompressionReport`. The builder NEVER
> imports `app.risk` / `app.execution` / `app.exchanges` /
> `app.telegram` / `app.config`; it NEVER reads private
> exchange / account state; it NEVER carries an API secret
> in any logged / exported / serialised payload; it NEVER
> authorises a trade decision or auto-tuning. The maximum
> any briefing can reach is `COMMENTARY_SUBSTRATE`, which
> is *commentary substrate* only — **no member of
> `OperatorBriefingAuthorityLevel` grants trade authority**.
> The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced
> in code AND in tests. **Phase 12 remains FORBIDDEN.**
> The Risk Engine remains the single trade-decision gate.

#### Added

- `app/ai/operator_briefing.py` — paper / pure /
  deterministic schema and helpers. Ships:
  - `OperatorBriefingSection` closed enum with 12 values:
    `EXECUTIVE_SUMMARY`, `MARKET_INTELLIGENCE`,
    `DISCOVERY_QUALITY`, `COVERAGE_AUDIT`,
    `POST_DISCOVERY_OUTCOME`, `REJECT_ATTRIBUTION`,
    `SEVERE_MISS_TRIAGE`, `REPLAY_REFLECTION`,
    `CONTRADICTIONS`, `UNSUPPORTED_CLAIMS`, `DATA_GAPS`,
    `OPERATOR_ACTION_ITEMS`.
  - `OperatorBriefingAuthorityLevel` closed enum with 4
    values: `COMMENTARY_SUBSTRATE`,
    `DEGRADED_PARTIAL_EVIDENCE`,
    `DEGRADED_NO_EVIDENCE`, `REJECTED`. **No member
    grants trade authority.**
  - `OperatorBriefingFinding` frozen dataclass with
    `finding_id`, `section`, `headline`, `detail`,
    `classification`, `evidence_refs`,
    `related_claim_ids`, `review_only=True` (hard-pinned
    at every `to_dict()` boundary).
  - `OperatorBriefingSectionRecord` frozen dataclass.
  - `OperatorBriefing` frozen dataclass with
    `briefing_id`, `created_at_utc`, `reference_window`,
    `source_bundle_id`, `source_ai_output_id`,
    `source_block_c_status`, `source_report_paths`,
    `sections`, `key_findings`, `unsupported_claims`,
    `contradictions`, `data_gaps`,
    `operator_review_items`, `evidence_refs`,
    `notable_symbols`, `risk_tags`, `authority_level`,
    `forbidden_fields_stripped`, `redacted_secret_count`,
    `warnings`, `consumer_contract`, plus the
    hard-pinned `trade_authority=False`,
    `auto_tuning_allowed=False`,
    `phase_12_forbidden=True`,
    `stateless_inference=True`,
    `feedback_isolation=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False` flags.
    Re-pinned at every `to_dict()` boundary even if a
    caller flips the dataclass field.
  - `OperatorBriefingBuilder` (and the
    `build_operator_briefing` convenience wrapper) —
    deterministic; classifies every AI-4 claim into the
    closed compression vocabulary; groups findings into
    the closed section vocabulary; never invents a
    missing `evidence_refs` entry; never paraphrases
    `claim_text`; runs `strip_forbidden_fields` and
    `redact_secrets` as defence in depth; never calls an
    LLM / DeepSeek; never opens a network socket; never
    reads or carries API secrets; never reads private
    exchange / account state; never authorises a trade
    decision or auto-tuning.
  - `render_operator_briefing_markdown` helper.
  - Closed event-type constants:
    `AI_OPERATOR_BRIEFING_GENERATED`,
    `AI_EVIDENCE_COMPRESSION_GENERATED`,
    `AI_UNSUPPORTED_CLAIMS_SUMMARIZED`. None are wired
    into the runtime hot path.
- `app/ai/evidence_compression.py` — paper / pure /
  deterministic schema and helpers. Ships:
  - `CompressedClaim` frozen dataclass preserving
    `claim_id`, `claim_type`, `claim_text` (verbatim),
    `evidence_refs`, `truth_layer_fields_used`,
    `citation_authority_level`, `reality_check_status`,
    `reality_check_authority_level`, `classification`,
    `confidence_raw`, `confidence_reality_checked`,
    `warnings`.
  - `EvidenceCompressionReport` frozen dataclass with
    `report_id`, `created_at_utc`, `reference_window`,
    `source_bundle_id`, `source_ai_output_id`,
    `summary`, `compressed_claims`, `supported_claims`,
    `degraded_claims`, `rejected_claims`,
    `contradictions`, `unsupported_claims`,
    `reality_check_summary`,
    `evidence_quality_summary`, `data_gap_summary`,
    `notable_symbols`, `risk_tags`, `evidence_refs`,
    `forbidden_fields_stripped`,
    `redacted_secret_count`, `warnings`, plus the
    hard-pinned `trade_authority=False`,
    `auto_tuning_allowed=False`,
    `phase_12_forbidden=True`,
    `stateless_inference=True`,
    `feedback_isolation=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False` flags.
  - `EvidenceCompressionReportBuilder` (and the
    `build_evidence_compression_report` convenience
    wrapper).
  - `classify_claim` helper that maps Phase AI-2
    citation authority + Phase AI-3 Reality Check status
    into the closed compression vocabulary
    (`CLAIM_CLASS_SUPPORTED`,
    `CLAIM_CLASS_UNSUPPORTED`,
    `CLAIM_CLASS_DEGRADED_NO_EVIDENCE`,
    `CLAIM_CLASS_REJECTED`,
    `CLAIM_CLASS_CONTRADICTED`,
    `CLAIM_CLASS_COMMENTARY_ONLY`).
  - `render_evidence_compression_report_markdown` helper.
- `app/ai/__init__.py` — extended re-exports for the
  Phase AI-5 public API alongside the Phase AI-1 +
  AI-2 + AI-3 + AI-4 surfaces.
- `scripts/run_ai_operator_briefing.py` — paper /
  read-only / no-network offline runner. Reads a Phase
  AI-1 evidence bundle JSON, a Phase AI-4 sandbox output
  JSON, and an optional Block C Integrated Checkpoint
  report JSON; writes
  `<output-dir>/operator_briefing.json`,
  `<output-dir>/operator_briefing.md`,
  `<output-dir>/evidence_compression_report.json`,
  `<output-dir>/evidence_compression_report.md`. Imports
  nothing from `app.risk`, `app.execution`,
  `app.exchanges`, `app.telegram`, or `app.config`.
- `tests/unit/test_ai_operator_briefing.py` — 113 unit
  tests covering every brief-mandated scenario:
  - builds operator briefing from evidence bundle +
    sandbox output;
  - preserves evidence_refs;
  - unsupported claims appear in the
    `UNSUPPORTED_CLAIMS` section, NEVER in
    `key_findings`;
  - rejected / contradicted claims do not become
    supported findings;
  - data gaps surfaced;
  - operator action items are review-only (no
    `buy`/`sell`/`long`/`short`/`enter`/`exit`/
    `place_order`/`open_position`/`close_position`/
    `execute` prefixes);
  - forbidden fields stripped (parametrised over 25
    fields) and absent in clean briefing payloads;
  - `trade_authority=False`, `auto_tuning_allowed=False`,
    `phase_12_forbidden=True`,
    `stateless_inference=True`,
    `feedback_isolation=True` re-pinned at every
    `to_dict()` boundary even if the dataclass field is
    flipped via `object.__setattr__`;
  - no Telegram outbound (AST imports + string scan);
  - no Risk / Execution / Exchanges / Telegram / Config
    consumer of `app.ai` (parametrised over 5 packages);
  - credential-shaped values redacted; private account
    state tokens absent;
  - Markdown output non-empty;
  - JSON round-trips;
  - same input produces same output (deterministic);
  - no live LLM / DeepSeek call shape;
  - defensive companions for `classify_claim` paths,
    authority-level transitions, claim_type → section
    mapping, consumer_contract assertions, notable
    symbol extraction.
- `docs/PHASE_AI_5_OPERATOR_BRIEFING_EVIDENCE_COMPRESSION.md` —
  this phase's design document.

#### Tests

- `python -m pytest tests/unit/test_ai_operator_briefing.py -q`
  → 113/113 PASS.
- `python -m pytest tests/unit -q` → 3128/3128 PASS, no
  regression vs. post-PR-#85 main 3015 baseline; +113 new
  tests on the new modules.

#### Phase status

Phase AI-5 = **IN_REVIEW** after this implementation PR.
Not `ACCEPTED`. Not live ready. Not trade authority granted.
Not real DeepSeek HTTP transport. Not Operator Briefing
live publishing. Not Rule Sandbox. Not Paper Shadow. Not
auto-tuning. **Phase 12 = FORBIDDEN.**

### Phase AI-4 — DeepSeek Offline Sandbox v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / sandbox-only).
**Runtime effect:** **none on real trading.** Two new read-only
modules `app/ai/intelligence_schema.py` and
`app/ai/deepseek_sandbox.py` are added alongside the existing
`app/ai/evidence_bundle.py` (Phase AI-1),
`app/ai/claim_contract.py` (Phase AI-2), and
`app/ai/reality_check.py` (Phase AI-3), with `app/ai/__init__.py`
extended to re-export the Phase AI-4 public surface, plus a new
offline CLI runner `scripts/run_deepseek_offline_sandbox.py` and
a matching unit-test module under
`tests/unit/test_deepseek_offline_sandbox.py` (94 tests). No file
under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`,
`app/ai/evidence_bundle.py`, `app/ai/claim_contract.py`, or
`app/ai/reality_check.py`, no event type, no database schema /
migration is touched. The modules are read-only at runtime: they
never append, mutate, or reorder rows in `events.db`; they never
produce direction, sizing, leverage, stop, target, or risk-budget
fields; they never produce a `runtime_config_patch`; and they
never call the real DeepSeek HTTP transport (the v0 skeleton
refuses to contact the network even when both safety gates are
open). No runtime knob (`symbol_limit`, anomaly threshold,
candidate pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase AI-4 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`llm_outbound_enabled=False`, `sandbox_only=True`,
`allow_trade_decision=False`,
`allow_runtime_config_change=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real DeepSeek HTTP transport, no
real Telegram outbound. **Phase 12 remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=False` is
hard-pinned at every `to_dict()` boundary even if a caller flips
the dataclass field. The recursive `_assert_no_forbidden_fields`
guard refuses to emit any payload carrying a `*_patch` key.
**Successor allowed:** later (separately gated) **Phase AI-5
Operator Briefing / Evidence Compression** that consumes the
schema-checked `AIIntelligenceOutput` and produces a redacted,
operator-facing briefing artefact (still paper / report /
sandbox-only). **NOT** the real DeepSeek HTTP transport. **NOT**
DeepSeek trade decisions. **NOT** the AI Layer's involvement in
the Risk Engine. **NOT** the AI Layer's involvement in the
Execution FSM. **NOT** auto-tuning. **NOT** real Telegram
outbound. **NOT** Phase 12.

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).** This slice ships
> the AI Layer's first **outbound-capable** runtime
> artefact - the DeepSeek Offline Sandbox v0. The runner
> consumes a frozen Phase AI-1 evidence bundle, validates
> every model-emitted claim through the Phase AI-2 citation
> contract, cross-verifies through the Phase AI-3 Reality
> Check engine, strips forbidden trade-action /
> runtime-config-patch fields, redacts credential-shaped
> keys, and emits one schema-checked
> `AIIntelligenceOutput`. The runner NEVER imports
> `app.risk` / `app.execution` / `app.exchanges` /
> `app.telegram` / `app.config`; it NEVER reads private
> exchange / account state; it NEVER carries an API secret
> in any logged / exported / serialised payload; it NEVER
> authorises a trade decision or auto-tuning. The runner is
> **disabled by default** (`enabled=False`) and **outbound
> is closed by default** (`outbound_enabled=False`). Even
> with both gates open the v0
> `OptionalDeepSeekHTTPProvider` skeleton refuses to contact
> the network - the real DeepSeek HTTP transport is gated
> behind a later, separately reviewed PR. The maximum
> authority any output can reach is `SUPPORTED_INTELLIGENCE`,
> which is *commentary substrate* only — **no member of
> `AIIntelligenceAuthorityLevel` grants trade authority**.
> The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced in
> code AND in tests. **Phase 12 remains FORBIDDEN.** The Risk
> Engine remains the single trade-decision gate.

#### Added

- `app/ai/intelligence_schema.py` — paper / pure /
  deterministic schema and helpers. Ships:
  - `AIIntelligenceTaskType` closed enum with 10 values:
    `OPERATOR_BRIEFING_DRAFT`, `MARKET_INTELLIGENCE_SUMMARY`,
    `EVIDENCE_COMPRESSION`, `REPLAY_REFLECTION_SUMMARY`,
    `CONTRADICTION_SUMMARY`, `EVIDENCE_QUALITY_ASSESSMENT`,
    `COVERAGE_AUDIT_INTERPRETATION`,
    `POST_DISCOVERY_OUTCOME_SUMMARY`,
    `REJECT_TO_OUTCOME_SUMMARY`, `SEVERE_MISS_SUMMARY`.
  - `AIIntelligenceAuthorityLevel` closed enum with 5 values:
    `COMMENTARY_ONLY`, `SUPPORTED_INTELLIGENCE`,
    `DEGRADED_NO_EVIDENCE`, `DEGRADED_REALITY_CHECK`,
    `REJECTED`. **No member grants trade authority.**
  - `AIIntelligenceStatus` closed enum with 7 values: `OK`,
    `DEGRADED_OUTBOUND_DISABLED`, `DEGRADED_PROVIDER_ERROR`,
    `DEGRADED_REALITY_CHECK`, `DEGRADED_MISSING_EVIDENCE`,
    `REJECTED_FORBIDDEN_FIELDS`, `REJECTED_INVALID_INPUT`.
  - `AIIntelligenceClaim` / `AIIntelligenceOutput` frozen
    dataclasses preserving `claim_id`, `claim_type`,
    `claim_text`, `evidence_refs`,
    `truth_layer_fields_used`, `citation_authority_level`,
    `reality_check_status`,
    `reality_check_authority_level`, `confidence_raw`,
    `confidence_reality_checked`, `warnings`, plus the
    output-level `summary`, `claims`, `contradictions`,
    `unsupported_claims`, `risk_tags`, `evidence_refs`,
    `forbidden_fields_stripped`, `redacted_secret_count`,
    `degraded_reasons`, `safety_flags`, plus the
    hard-pinned `stateless_inference=True`,
    `feedback_isolation=True`, `trade_authority=False`,
    `auto_tuning_allowed=False`, `phase_12_forbidden=True`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False` flags.
    Re-pinned at every `to_dict()` boundary even if a
    caller flips the dataclass field.
  - `strip_forbidden_fields(payload, *, forbidden=None)` —
    recursive helper that strips forbidden trade-action /
    runtime-config-patch fields and returns
    `(clean_payload, sorted_paths)`. Never mutates the
    input. Records every stripped path so the audit trail
    is never silent.
  - `redact_secrets(payload)` — recursive helper that
    replaces every credential-shaped key's value with
    `<REDACTED>`. Returns `(clean_payload, count)`.
  - `coerce_str_tuple` / `coerce_content` helpers for
    deterministic JSON coercion.
  - Re-uses the recursive `_assert_no_forbidden_fields`
    output guard from `app.ai.evidence_bundle` against
    `buy`, `sell`, `long`, `short`, `direction`, `side`,
    `entry`, `exit`, `position_size`, `leverage`, `stop`,
    `stop_loss`, `stop_price`, `target`, `target_price`,
    `take_profit`, `risk_budget`, `order`, `order_type`,
    `execution_command`, `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`,
    `strategy_parameter_patch`, `signal_to_trade`,
    `should_buy`, `should_short`, plus defensive aliases
    `trading_approved`, `live_ready`, `live_trading_allowed`.
    Re-exported as `FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS`.
- `app/ai/deepseek_sandbox.py` — paper / pure /
  deterministic runner and provider scaffolding. Ships:
  - `DeepSeekSandboxConfig` closed dataclass with 15
    disabled-by-default gates: `enabled=False`,
    `provider="deepseek"`, `outbound_enabled=False`,
    `sandbox_only=True`, `allow_trade_decision=False`
    (validated to remain `False`),
    `allow_runtime_config_change=False` (validated to
    remain `False`), `require_evidence_refs=True`,
    `require_reality_check=True`, `stateless_inference=True`,
    `feedback_isolation=True`, `timeout_seconds=30.0`,
    `max_tokens=2048`, `model="deepseek-chat"`,
    `redaction_enabled=True`. Re-pinned at every
    `to_dict()` boundary.
  - `DeepSeekSandboxInput` closed dataclass carrying the
    frozen Phase AI-1 evidence bundle, the closed task
    type, the operator instruction, the allowed output
    schema, the additive forbidden-fields tuple, and the
    `evidence_refs_required` /
    `reality_check_required` flags.
  - `DeepSeekProviderProtocol` runtime-checkable Protocol
    a transport must implement (a closed
    `generate(prompt, max_tokens, timeout_seconds, model)`
    surface).
  - `FakeDeepSeekProvider` — deterministic in-memory
    provider used by tests AND by every offline run that
    has `outbound_enabled=False`. Three construction modes
    (`payload=...`, `payload_fn=...`, `raise_exc=...`) plus
    a default empty-skeleton response.
  - `OptionalDeepSeekHTTPProvider` — refusal-only skeleton
    for the future real DeepSeek HTTP transport. Imports
    nothing that opens a socket. Reads no process
    environment for credentials. Refuses to be invoked when
    `outbound_enabled=False`. Even with
    `outbound_enabled=True` and
    `credentials_provided=True` raises
    `DeepSeekOutboundDisabledError` in v0.
  - `DeepSeekOfflineSandboxRunner` (and the
    `run_deepseek_offline_sandbox` convenience wrapper) —
    deterministic; scans every input for forbidden /
    credential-shaped keys via the Phase AI-1
    `_scan_for_forbidden_input` guard; builds a redacted,
    deterministic prompt payload (the prompt NEVER carries
    a raw API key, an API secret, a bearer token, a
    `listenKey`, a chat history, or a previous AI answer);
    short-circuits to the in-memory provider when
    `outbound_enabled=False`; calls the configured provider
    when `outbound_enabled=True` AND
    `sandbox_only=True`; strips forbidden trade-action /
    runtime-config-patch fields from the model output;
    validates every model-emitted claim through the Phase
    AI-2 `AIClaimCitationValidator`; cross-verifies through
    the Phase AI-3 `AIRealityCheckEngine`; emits one
    `AIIntelligenceOutput`; converts every provider
    timeout / 429 / 5xx / unexpected error into a degraded
    result, never crashing a hot path.
  - Closed exception hierarchy: `DeepSeekSandboxError`
    (base), `DeepSeekOutboundDisabledError`,
    `DeepSeekProviderTimeoutError`,
    `DeepSeekProviderRateLimitedError`,
    `DeepSeekProviderServerError`.
  - Does NOT import `app.risk`, `app.execution`,
    `app.exchanges`, `app.telegram`, or `app.config`
    (AST-checked). Does NOT import `openai`, `anthropic`,
    `deepseek`, `httpx`, `requests`, `aiohttp`, `urllib3`,
    `websocket`, `websockets`, `grpc`, `boto3`, `socket`
    (AST-checked). Source contains no `deepseek.api` /
    `DeepSeekClient(` / `call_deepseek(` / `requests.get(` /
    `httpx.post(` / `aiohttp.ClientSession(` /
    `websocket.create_connection(` shape (string-checked).
- `app/ai/__init__.py` — extended to re-export the Phase
  AI-4 public API alongside the Phase AI-1 + AI-2 + AI-3
  surfaces: `DeepSeekSandboxConfig`,
  `DeepSeekSandboxInput`, `DeepSeekProviderProtocol`,
  `FakeDeepSeekProvider`, `OptionalDeepSeekHTTPProvider`,
  `DeepSeekOfflineSandboxRunner`, `DeepSeekSandboxError`,
  `DeepSeekOutboundDisabledError`,
  `DeepSeekProviderTimeoutError`,
  `DeepSeekProviderRateLimitedError`,
  `DeepSeekProviderServerError`,
  `run_deepseek_offline_sandbox`, `AIIntelligenceTaskType`,
  `AIIntelligenceAuthorityLevel`, `AIIntelligenceStatus`,
  `AIIntelligenceClaim`, `AIIntelligenceOutput`,
  `FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS`,
  `AI_SECRET_REDACTED_PLACEHOLDER`, `redact_secrets`,
  `strip_forbidden_fields`,
  `AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION`,
  `AI_INTELLIGENCE_OUTPUT_SOURCE_PHASE`,
  `AI_INTELLIGENCE_OUTPUT_SOURCE_MODULE`,
  `DEEPSEEK_SANDBOX_SCHEMA_VERSION`,
  `DEEPSEEK_SANDBOX_SOURCE_PHASE`,
  `DEEPSEEK_SANDBOX_SOURCE_MODULE`.
- `scripts/run_deepseek_offline_sandbox.py` — offline CLI
  runner. Reads a frozen Phase AI-1 evidence bundle JSON,
  hands it to the
  `DeepSeekOfflineSandboxRunner`, and writes
  `deepseek_sandbox_output.json` /
  `deepseek_sandbox_output.md` under `--output-dir`.
  Imports nothing from `app.risk`, `app.execution`,
  `app.exchanges`, `app.telegram`, or `app.config`. Imports
  nothing network-shaped.
- `tests/unit/test_deepseek_offline_sandbox.py` (94 cases)
  covering every brief-mandated scenario: disabled by
  default, fake provider works offline, outbound disabled
  degrades safely (HTTP-shaped provider not invoked),
  `OptionalDeepSeekHTTPProvider` refuses with
  `outbound_enabled=False` AND with `outbound_enabled=True`,
  forbidden trade fields stripped (parametrised over 25
  fields, both top-level and nested), evidence refs
  required, reality check required, stateless inference
  (chat_history / previous_ai_answer rejected at intake),
  feedback isolation invariants pinned, secret redaction
  (api_key / api_secret / deepseek_api_key /
  binance_api_secret / telegram_bot_token / token / secret),
  provider error degrade (timeout / 429 / 5xx / outbound-
  disabled / unexpected), no hot-path imports
  (`app.risk` / `app.execution` / `app.exchanges` /
  `app.telegram` / `app.config`) absent, no network imports
  absent, source contains no live-call shape, Risk /
  Execution / Exchange packages do not import `app.ai`,
  deterministic output (same input ⇒ identical
  `to_dict()` and `json.dumps()`), JSON-serializable output
  (round-trip equals input), output contains no forbidden
  trade-action key at any nesting depth, output pins
  `trade_authority=False` / `auto_tuning_allowed=False` /
  `phase_12_forbidden=True` / safety flags / `mode=paper`,
  `AIIntelligenceAuthorityLevel` has no trade member
  (closed enum coverage), defensive companions (unknown
  task type rejected, non-mapping bundle rejected, non-
  mapping provider response degrades, outbound enabled
  without provider degrades safely, init module re-exports
  the Phase AI-4 surface).
- `docs/PHASE_AI_4_DEEPSEEK_OFFLINE_SANDBOX.md` — new phase
  doc.
- `docs/DEEPSEEK_SANDBOX_RUNBOOK.md` — new operator
  runbook.

#### Changed

- `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
  `docs/CHANGELOG.md` (this entry) updated to reflect Phase
  AI-4 = **IN_REVIEW**.

#### Tests

- `python -m pytest tests/unit/test_deepseek_offline_sandbox.py -q`:
  94 PASS / 0 fail.
- `python -m pytest tests/unit -q`: 3015 PASS / 0 fail (was
  2921 before this phase; +94 from this phase).

#### Safety boundary (held end-to-end)

- `mode = paper`
- `live_trading = False`
- `exchange_live_orders = False`
- `right_tail = False`
- `llm = False`
- `llm_outbound_enabled = False`
- `sandbox_only = True`
- `allow_trade_decision = False`
- `allow_runtime_config_change = False`
- `telegram_outbound_enabled = False`
- `binance_private_api_enabled = False`
- no Binance API key / secret
- no signed endpoint
- no private WebSocket
- no `listenKey`
- no real Telegram outbound
- no DeepSeek trade decision
- no real DeepSeek HTTP transport
- **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

### Phase AI-3 — Reality Check Layer v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / read-only).
**Runtime effect:** **none on real trading.** A new read-only
module `app/ai/reality_check.py` is added alongside the existing
`app/ai/evidence_bundle.py` (Phase AI-1) and
`app/ai/claim_contract.py` (Phase AI-2), with `app/ai/__init__.py`
extended to re-export the Phase AI-3 public surface, and a
matching unit-test module under
`tests/unit/test_ai_reality_check_layer.py` (70 tests). No file
under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, `app/ai/evidence_bundle.py`,
`app/ai/claim_contract.py`, no event type, no database schema /
migration is touched. The module is read-only: it never appends,
mutates, or reorders rows in `events.db`; it never produces
direction, sizing, leverage, stop, target, or risk-budget fields;
it never produces a `runtime_config_patch`; and it never calls an
LLM / DeepSeek / Telegram outbound. No runtime knob
(`symbol_limit`, anomaly threshold, candidate pool capacity,
Regime weights) is changed.
**Phase ledger effect:** opens Phase AI-3 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=false` is
hard-pinned at every `to_dict()` boundary even if a caller flips
the dataclass field. The recursive `_assert_no_forbidden_fields`
guard refuses to emit any payload carrying a `*_patch` key.
**Successor allowed:** later (separately gated) **Phase AI-4
DeepSeek Offline Sandbox** that consumes the Reality Check
substrate plus the Phase AI-1 Evidence Bundle in an offline /
sandboxed environment. **NOT** the runtime hot path. **NOT**
DeepSeek trade decisions. **NOT** the AI Layer's involvement in
the Risk Engine. **NOT** the AI Layer's involvement in the
Execution FSM. **NOT** auto-tuning. **NOT** real Telegram
outbound. **NOT** Phase 12.

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).** This slice ships the
> AI Layer's *deterministic / statistical* Reality Check
> verifier. Having `evidence_refs` is necessary but **not
> sufficient**; an AI claim is also cross-checked against
> the Truth Layer that its `evidence_refs` point at, plus
> the market / system-behavior / outcome facts pinned in the
> Phase AI-1 Evidence Bundle. Reality Check is **not** an
> LLM, **not** a DeepSeek client, **not** a network
> transport, and **not** a prompt template. Claims with
> citations but no facts are demoted to
> `INSUFFICIENT_EVIDENCE`; claims that contradict the bundle
> are demoted to `CONTRADICTED` (or `PARTIALLY_SUPPORTED`
> for single-axis contradictions); claims that smuggle
> unverifiable narrative ("smart money is definitely
> entering" / "whales are accumulating" / "faith is
> returning" / "main force intention is clear") with no
> computable backing are rejected via
> `REJECTED_UNVERIFIABLE_NARRATIVE`; claims that depend on a
> future / unsealed window are rejected via
> `REJECTED_LOOKAHEAD`. Confidence calibration is always
> non-increasing
> (`confidence_reality_checked <= confidence_raw`). The
> maximum authority any claim can reach is
> `SUPPORTED_INTELLIGENCE`, which is *commentary substrate*
> only — **no member of `AIRealityCheckAuthorityLevel`
> grants trade authority**. The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced in
> code AND in tests. **Phase 12 remains FORBIDDEN.** The Risk
> Engine remains the single trade-decision gate.

#### Added

- `app/ai/reality_check.py` — paper / pure / deterministic
  schema, engine, and recursive guards. Ships:
  - `AIRealityCheckStatus` closed enum with 6 values:
    `SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`,
    `INSUFFICIENT_EVIDENCE`, `REJECTED_LOOKAHEAD`,
    `REJECTED_UNVERIFIABLE_NARRATIVE`. **No member carries
    trade-action semantics.**
  - `AIRealityCheckCategory` closed enum with 7 values:
    `STATISTICAL_VERIFICATION`,
    `MICROSTRUCTURE_VALIDATION`, `CONFIDENCE_CALIBRATION`,
    `CONTRADICTION_DETECTION`,
    `ADVERSARIAL_EVIDENCE_CHECK`, `LOOKAHEAD_GUARD`,
    `NARRATIVE_POLLUTION_GUARD`.
  - `AIRealityCheckAuthorityLevel` closed enum with 4
    values: `SUPPORTED_INTELLIGENCE`,
    `UNSUPPORTED_INTELLIGENCE`, `DEGRADED_NO_EVIDENCE`,
    `REJECTED_BY_REALITY_CHECK`. **No member grants trade
    authority.** The maximum any claim can reach is
    `SUPPORTED_INTELLIGENCE`, which is *commentary
    substrate* only.
  - `AIRealityCheckInput` / `AIRealityCheckResult` frozen
    dataclasses preserving `claim_id`, `claim_type`,
    `claim_text`, `evidence_refs`,
    `truth_layer_fields_used`, `authority_level`,
    `confidence_raw`, `evidence_bundle_facts`,
    `market_facts`, `system_behavior_facts`,
    `outcome_facts`, `lookahead_policy`, plus the
    engine-emitted `status`, `categories_checked`,
    `supporting_evidence_refs`,
    `contradicting_evidence_refs`,
    `confidence_reality_checked`,
    `authority_level_after_check`, `degradation_reason`,
    `warnings`, plus the hard-pinned
    `auto_tuning_allowed=false`,
    `phase_12_forbidden=true`,
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False` flags.
    Re-pinned at every `to_dict()` boundary even if the
    dataclass field is mutated.
  - `AIRealityCheckEngine` (and the `reality_check_claim`
    convenience wrapper) — deterministic; coerces every
    input to a JSON-serializable form; runs the seven
    verification axes in fixed order (Lookahead Guard →
    Narrative Pollution Guard → Statistical Verification →
    Contradiction Detection → Microstructure Validation →
    Adversarial Evidence Check → Confidence Calibration);
    emits `confidence_reality_checked <= confidence_raw`
    always; clamps raw confidence to `[0.0, 1.0]` first;
    never invents supporting / contradicting evidence_refs
    beyond what the producer cited; runs the recursive
    `_assert_no_forbidden_fields` guard at the
    serialisation boundary.
  - Closed lookahead-policy vocabulary: required flags
    (`frozen_evidence_only`, `no_future_market_data`,
    `no_training_from_ai_output`, `no_runtime_feedback`,
    `post_hoc_analysis_only_when_window_closed`) MUST be
    `True`; forbidden flags
    (`live_inference_uses_future_outcome`,
    `uses_unsealed_window`, `uses_future_market_data`,
    `trains_from_ai_output`) MUST be absent or `False`.
  - Closed unverifiable-narrative vocabulary
    ("smart money is definitely entering" / "whales are
    accumulating" / "faith is returning" / "main force
    intention is clear" / "definitely entering" /
    "obviously bullish" / "without a doubt" /
    "guaranteed to" plus 8 close variants).
  - Closed contradiction-signal vocabulary tied to the
    Phase AI-1 fact groups (`market_facts.breadth_weak`,
    `market_facts.data_gap_severe`,
    `market_facts.data_gap_rate >= 0.5`,
    `system_behavior_facts.late_chase_high`,
    `system_behavior_facts.late_chase_rate >= 0.5`,
    `system_behavior_facts.fake_breakout_rising`,
    `system_behavior_facts.funding_overheated`,
    `outcome_facts.failed_continuation`,
    `outcome_facts.missed_strong_tail_rate >= 0.5`).
  - Re-uses the recursive `_assert_no_forbidden_fields`
    output guard from `app.ai.evidence_bundle` against
    `buy`, `sell`, `long`, `short`, `direction`, `side`,
    `entry`, `exit`, `position_size`, `leverage`, `stop`,
    `stop_loss`, `stop_price`, `target`, `target_price`,
    `take_profit`, `risk_budget`, `order`, `order_type`,
    `execution_command`, `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`,
    `strategy_parameter_patch`, `signal_to_trade`,
    `should_buy`, `should_short`, plus defensive aliases
    `trading_approved`, `live_ready`,
    `live_trading_allowed`. Re-exported as
    `FORBIDDEN_REALITY_CHECK_FIELDS`.
  - Does NOT import `app.risk`, `app.execution`,
    `app.exchanges`, `app.llm`, `app.telegram`, or
    `app.config` (AST-checked). Does NOT import `openai`,
    `anthropic`, `deepseek`, `httpx`, `requests`, `aiohttp`,
    `urllib3`, `websocket`, `websockets`, `grpc`, `boto3`,
    or `socket` (AST-checked). Source contains no
    `deepseek.` / `DeepSeekClient(` / `call_deepseek(` /
    `requests.get(` / `httpx.post(` /
    `aiohttp.ClientSession(` /
    `websocket.create_connection(` shape (string-checked).
- `app/ai/__init__.py` — extended to re-export the Phase AI-3
  public API alongside the Phase AI-1 + AI-2 surface:
  `AIRealityCheckStatus`, `AIRealityCheckCategory`,
  `AIRealityCheckAuthorityLevel`, `AIRealityCheckInput`,
  `AIRealityCheckResult`, `AIRealityCheckEngine`,
  `reality_check_claim`, `FORBIDDEN_REALITY_CHECK_FIELDS`,
  `AI_REALITY_CHECK_SCHEMA_VERSION`,
  `AI_REALITY_CHECK_SOURCE_PHASE`,
  `AI_REALITY_CHECK_SOURCE_MODULE`.
- `tests/unit/test_ai_reality_check_layer.py` (70 cases)
  covering every brief-mandated scenario: supported claim →
  `SUPPORTED`, partial support → confidence downgrade,
  contradicted → `CONTRADICTED` / `REJECTED_BY_REALITY_CHECK`,
  missing evidence → `INSUFFICIENT_EVIDENCE`, lookahead
  violation → `REJECTED_LOOKAHEAD`, unverifiable narrative →
  `REJECTED_UNVERIFIABLE_NARRATIVE`,
  `confidence_reality_checked <= confidence_raw`, no-trade-
  authority on result, forbidden-fields absent on serialised
  payload (parametrised over 25 fields), forbidden imports
  (`app.risk`/`app.execution`/`app.exchanges`/`app.llm`/
  `app.telegram`/`app.config`) absent, no LLM / DeepSeek /
  HTTP / network call path (AST + source + public-callable
  check), deterministic output across six status classes,
  defensive companions (closed enum coverage, Mapping-input
  coercion, string-flag honoured by Lookahead Guard,
  supporting / contradicting refs are subset of input refs,
  invariants re-pinned at `to_dict()` after dataclass
  mutation).
- `docs/PHASE_AI_3_REALITY_CHECK_LAYER.md` — new phase doc.

#### Changed

- `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
  `docs/CHANGELOG.md` (this entry) updated to reflect Phase
  AI-3 = **IN_REVIEW**.

#### Tests

- `python -m pytest tests/unit/test_ai_reality_check_layer.py -q`:
  70 PASS / 0 fail.
- `python -m pytest tests/unit -q`: 2921 PASS / 0 fail (was
  2851 before this phase; +70 from this phase).

#### Safety boundary (held end-to-end)

- `mode = paper`
- `live_trading = False`
- `exchange_live_orders = False`
- `right_tail = False`
- `llm = False`
- `telegram_outbound_enabled = False`
- `binance_private_api_enabled = False`
- no Binance API key / secret
- no signed endpoint
- no private WebSocket
- no `listenKey`
- no real Telegram outbound
- no DeepSeek trade decision
- **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

### Phase AI-2 — Truth Layer / AI Evidence Citation Contract v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / read-only).
**Runtime effect:** **none on real trading.** A new read-only
module `app/ai/claim_contract.py` is added alongside the existing
`app/ai/evidence_bundle.py` (Phase AI-1), with `app/ai/__init__.py`
extended to re-export the Phase AI-2 public surface, and a
matching unit-test module under
`tests/unit/test_ai_evidence_citation_contract.py` (70 tests). No
file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, no event type, no database schema
/ migration is touched. The module is read-only: it never appends,
mutates, or reorders rows in `events.db`; it never produces
direction, sizing, leverage, stop, target, or risk-budget fields;
it never produces a `runtime_config_patch`; and it never calls an
LLM / DeepSeek / Telegram outbound. No runtime knob (`symbol_limit`,
anomaly threshold, candidate pool capacity, Regime weights) is
changed.
**Phase ledger effect:** opens Phase AI-2 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=false` is
hard-pinned at every `to_dict()` boundary even if a caller flips
the dataclass field. The recursive `_assert_no_forbidden_fields`
guard refuses to emit any payload carrying a `*_patch` key.
**Successor allowed:** later (separately gated) **AI Reality Check
Layer** that cross-verifies an AI claim's `claim_text` against the
Phase AI-1 Evidence Bundle cited in `evidence_refs`, **OR** later
offline AI / operator-briefing report generation that consumes
`AIClaimCitationResult` as a frozen input, **OR** the eventual
**Operator Briefing** layer. No other phase is unlocked.

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).** This slice ships the
> AI Layer's *claim-level* citation contract: every AI claim
> MUST cite Truth-Layer evidence via `evidence_refs`. Claims
> without `evidence_refs` are demoted; claims with malformed
> `evidence_refs` are rejected (strict mode) or demoted
> (non-strict mode); commentary-only claims stay
> commentary-only; trade-action / runtime-config-patch field
> names smuggled into a claim are rejected by schema. The
> maximum authority any claim can reach is
> `SUPPORTED_INTELLIGENCE`, which is *commentary substrate*
> only - **no member of `AIClaimAuthorityLevel` grants trade
> authority**. The four AI root constraints in
> `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` are enforced in
> code AND in tests. **Phase 12 remains FORBIDDEN.** The Risk
> Engine remains the single trade-decision gate.

#### Added

- `app/ai/claim_contract.py` — paper / pure / deterministic
  schema, validator, and recursive guards. Ships:
  - `AIClaimAuthorityLevel` closed enum with 6 values:
    `COMMENTARY_ONLY`, `SUPPORTED_INTELLIGENCE`,
    `UNSUPPORTED_INTELLIGENCE`, `DEGRADED_NO_EVIDENCE`,
    `REJECTED_BY_SCHEMA`, `REJECTED_INVALID_EVIDENCE`. **No
    member grants trade authority.** `UNSUPPORTED_INTELLIGENCE`
    is reserved for the later Reality Check Layer; the v0
    validator never produces it.
  - `AIClaimType` closed enum with 10 values: `REGIME`,
    `NARRATIVE`, `LIQUIDITY`, `RISK`, `COVERAGE`, `OUTCOME`,
    `CONTRADICTION`, `REPLAY_SUMMARY`, `REFLECTION_SUMMARY`,
    `EVIDENCE_QUALITY`.
  - `AIClaimInput` / `AIClaim` frozen dataclasses preserving
    `claim_id`, `claim_type`, `claim_text`, `evidence_refs`,
    `truth_layer_fields_used`, `confidence_raw`, `warnings`,
    `authority_level` (final, set by validator),
    `intended_authority_level` (producer intent, on input
    only), `schema_version`.
  - `AIClaimCitationResult` frozen dataclass carrying
    `claims`, `accepted_claim_count`, `degraded_claim_count`,
    `rejected_claim_count`, `missing_evidence_count`,
    `invalid_evidence_count`, `warnings`, `strict`, plus the
    hard-pinned `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=true`, `auto_tuning_allowed=false`
    flags, the `safety_flags` block, the
    `supported_evidence_ref_formats` /
    `supported_evidence_ref_prefixes` lists, and the
    sorted `forbidden_fields` list. Re-pinned at every
    `to_dict()` boundary even if the dataclass field is
    mutated.
  - `AIClaimCitationValidator` (and the `validate_ai_claims`
    convenience wrapper) — deterministic; coerces every input
    to a JSON-serializable form; rejects unknown
    `claim_type` / missing `claim_id` / missing `claim_text` /
    forbidden-field smuggling via
    `AIClaimAuthorityLevel.REJECTED_BY_SCHEMA`; demotes
    claims without `evidence_refs` via
    `AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE` (NEVER
    inventing a substitute citation); rejects (strict mode)
    or demotes (non-strict mode) claims with malformed
    `evidence_refs`; preserves `evidence_refs` and
    `truth_layer_fields_used` verbatim in input order; runs
    the recursive `_assert_no_forbidden_fields` guard at the
    serialisation boundary.
  - Closed evidence-ref grammar:
    `event:<EVENT_TYPE>:<event_id>`, `symbol:<SYMBOL>`,
    `opportunity:<opportunity_id>`,
    `scan_batch:<scan_batch_id>`,
    `metric:<metric_name>:<window>`, `report:<report_id>`.
    Compiled regex per prefix; total validity check is
    available via `_is_valid_evidence_ref`.
  - `_find_forbidden_field_in_claim` per-claim guard that
    rejects claims whose `claim_id` / `claim_type` /
    `claim_text` / `evidence_refs` /
    `truth_layer_fields_used` contains a forbidden
    trade-action / runtime-config-patch field name verbatim.
    Whole-string match — does NOT do substring scanning of
    free-form prose, so a legitimate narrative containing
    the word `buy` in a sentence is NOT rejected.
  - Re-uses the recursive `_assert_no_forbidden_fields`
    output guard from `app.ai.evidence_bundle` against
    `buy`, `sell`, `long`, `short`, `direction`, `side`,
    `entry`, `exit`, `position_size`, `leverage`, `stop`,
    `stop_loss`, `stop_price`, `target`, `target_price`,
    `take_profit`, `risk_budget`, `order`, `order_type`,
    `execution_command`, `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`,
    `strategy_parameter_patch`, `signal_to_trade`,
    `should_buy`, `should_short`, plus defensive aliases
    `trading_approved`, `live_ready`, `live_trading_allowed`.
    Re-exported as `FORBIDDEN_CLAIM_FIELDS`.
  - Does NOT import `app.risk`, `app.execution`,
    `app.exchanges`, `app.llm`, `app.telegram`, or
    `app.config` (AST-checked). Does NOT import `openai`,
    `anthropic`, `deepseek`, `httpx`, `requests`, `aiohttp`,
    `urllib3`, `websocket`, `websockets`, `grpc`, or `boto3`
    (AST-checked).
- `app/ai/__init__.py` — extended to re-export the Phase AI-2
  public API alongside the Phase AI-1 surface:
  `AIClaimAuthorityLevel`, `AIClaimType`, `AIClaimInput`,
  `AIClaim`, `AIClaimCitationResult`,
  `AIClaimCitationValidator`, `validate_ai_claims`,
  `FORBIDDEN_CLAIM_FIELDS`, `SUPPORTED_EVIDENCE_REF_FORMATS`,
  `SUPPORTED_EVIDENCE_REF_PREFIXES`,
  `AI_CLAIM_CONTRACT_SCHEMA_VERSION`,
  `AI_CLAIM_CONTRACT_SOURCE_PHASE`,
  `AI_CLAIM_CONTRACT_SOURCE_MODULE`.
- `tests/unit/test_ai_evidence_citation_contract.py` (70
  cases) covering every brief-mandated scenario:
  supported-with-valid-refs → `SUPPORTED_INTELLIGENCE`,
  no-refs → `DEGRADED_NO_EVIDENCE`, invalid-ref →
  `REJECTED_INVALID_EVIDENCE` (strict) or degraded
  (non-strict), commentary-only stays commentary-only,
  multiple `evidence_refs` preserved verbatim,
  `truth_layer_fields_used` preserved verbatim, validator
  never invents missing `evidence_refs`, forbidden trade
  fields rejected / stripped / absent (parametrised over 25
  fields), result summary counts correct, deterministic
  output, JSON-serializable output, forbidden imports
  (`app.risk`/`app.execution`/`app.exchanges`/`app.llm`/
  `app.telegram`/`app.config`) absent, no LLM / DeepSeek /
  HTTP call path (AST + public-callable check), defensive
  companions (closed enum coverage, strict-mode default,
  Mapping-input coercion, prefix coverage, phase-12
  invariants smoke).
- `docs/PHASE_AI_2_TRUTH_LAYER_EVIDENCE_CITATION_CONTRACT.md` —
  new phase doc.

#### Changed

- `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
  `docs/CHANGELOG.md` (this entry) updated to reflect Phase
  AI-2 = **IN_REVIEW**.

#### Tests

- `python -m pytest tests/unit/test_ai_evidence_citation_contract.py -q`:
  70 PASS / 0 fail.
- `python -m pytest tests/unit -q`: 2851 PASS / 0 fail (was
  2781 before this phase; +70 from this phase).

#### Safety boundary (held end-to-end)

- `mode = paper`
- `live_trading = False`
- `exchange_live_orders = False`
- `right_tail = False`
- `llm = False`
- `telegram_outbound_enabled = False`
- `binance_private_api_enabled = False`
- no Binance API key / secret
- no signed endpoint
- no private WebSocket
- no `listenKey`
- no real Telegram outbound
- no DeepSeek trade decision
- **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

### Phase AI-1 — AI Evidence Bundle Builder v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / read-only).
**Runtime effect:** **none on real trading.** A new read-only
package `app/ai/` is added with `app/ai/__init__.py` and
`app/ai/evidence_bundle.py`, plus a matching unit-test module
under `tests/unit/test_ai_evidence_bundle_builder.py` (55 tests).
No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, no event type, no database schema
/ migration is touched. The package is read-only: it never
appends, mutates, or reorders rows in `events.db`; it never
produces direction, sizing, leverage, stop, target, or
risk-budget fields; it never produces a `runtime_config_patch`;
and it never calls an LLM / DeepSeek / Telegram outbound. No
runtime knob (`symbol_limit`, anomaly threshold, candidate pool
capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase AI-1 as **`IN_REVIEW`**
(not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=false` is
hard-pinned at every `to_dict()` boundary even if a caller flips
the dataclass field. The recursive `_assert_no_forbidden_fields`
guard refuses to emit any payload carrying a `*_patch` key.
**Successor allowed:** later (separately gated) **offline AI /
operator-briefing report generation** that consumes the bundle
as a frozen input **OR** the eventual **AI Reality Check**
layer that verifies AI commentary against the Truth Layer cited
in the bundle. No other phase is unlocked.

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).** Block A is complete;
> Block B is complete and Block B Integrated Evidence
> Checkpoint = `PARTIAL_EVIDENCE`; Block C is complete (C1 +
> C2 + C3 merged); Block C Integrated Checkpoint has been
> driven on the operator server with
> `status=EVIDENCE_GENERATED`,
> `replay_status=EVIDENCE_GENERATED`,
> `reflection_status=EVIDENCE_GENERATED`,
> `evidence_contract_status=EVIDENCE_GENERATED`,
> `accepted_claim_count=2704`,
> `degraded/rejected/missing/invalid=0`,
> `phase_12_forbidden=true`, `auto_tuning_allowed=false`,
> `known_blockers=[]`. The project is therefore allowed to
> enter AI **read-only** Evidence Bundle preparation. This
> slice ships the AI Evidence Bundle Builder v0 as the AI
> Layer's only allowed read surface. The four AI root
> constraints in `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`
> are enforced in code AND in tests. **Phase 12 remains
> FORBIDDEN.** The Risk Engine remains the single
> trade-decision gate.

#### Added

- `app/ai/__init__.py` — re-exports the public API:
  `AIEvidenceBundleTaskType`, `AIEvidenceBundleBuildStatus`,
  `AIEvidenceBundleFactInput`, `AIEvidenceBundleFact`,
  `AIEvidenceBundle`, `AIEvidenceBundleBuilder`,
  `build_ai_evidence_bundle`, `ForbiddenAIInputError`,
  `FORBIDDEN_AI_OUTPUT_FIELDS`, `FORBIDDEN_INPUT_KEYS`,
  `CREDENTIAL_LIKE_KEY_TOKENS`, `LOOKAHEAD_POLICY_FLAGS`,
  `ALLOWED_CONSUMERS`, `FORBIDDEN_CONSUMERS`,
  `AI_EVIDENCE_BUNDLE_SCHEMA_VERSION`,
  `AI_EVIDENCE_BUNDLE_SOURCE_PHASE`,
  `AI_EVIDENCE_BUNDLE_SOURCE_MODULE`.
- `app/ai/evidence_bundle.py` — paper / pure / deterministic
  schema, builder, and recursive guards. Ships:
  - `AIEvidenceBundleTaskType` closed enum with 10 values:
    `OPERATOR_BRIEFING`, `MARKET_INTELLIGENCE_SUMMARY`,
    `COVERAGE_AUDIT_INTERPRETATION`,
    `POST_DISCOVERY_OUTCOME_SUMMARY`,
    `REJECT_TO_OUTCOME_SUMMARY`, `SEVERE_MISS_SUMMARY`,
    `REPLAY_REFLECTION_SUMMARY`, `EVIDENCE_COMPRESSION`,
    `CONTRADICTION_SUMMARY`, `EVIDENCE_QUALITY_ASSESSMENT`.
  - `AIEvidenceBundleBuildStatus` closed enum:
    `EVIDENCE_BUNDLE_BUILT` / `EVIDENCE_BUNDLE_DEGRADED` /
    `EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE`.
  - `AIEvidenceBundleFactInput` / `AIEvidenceBundleFact`
    frozen dataclasses preserving `fact_id`, `fact_type`,
    `content`, `evidence_refs`, `source_report`, `status`,
    `degradation_reason`, `schema_version`.
  - `AIEvidenceBundle` frozen dataclass carrying
    `bundle_id`, `created_at_utc`, `task_type`,
    `phase_context`, `reference_window`, the six
    accepted-only `*_facts` collections (`market_facts`,
    `system_behavior_facts`, `outcome_facts`, `replay_facts`,
    `reflection_facts`, `evidence_contract_facts`), the
    `degraded_facts` collection, the deduplicated
    `evidence_refs` and `source_reports` lists, the pinned
    `forbidden_fields` / `lookahead_policy` /
    `consumer_contract` blocks, the `warnings` list, the
    `build_status`, the `accepted_fact_count` /
    `degraded_fact_count` counters, and the hard-pinned
    `ai_output_is_commentary_only=True`,
    `ai_output_can_be_training_label=False`,
    `phase_12_forbidden=true`, `auto_tuning_allowed=false`
    flags. Re-pinned at every `to_dict()` boundary even if
    the dataclass field is mutated.
  - `AIEvidenceBundleBuilder` (and the
    `build_ai_evidence_bundle` convenience wrapper) -
    deterministic; coerces every input to a
    JSON-serializable form; rejects forbidden input keys
    with `ForbiddenAIInputError` (a `ValueError` subclass);
    demotes facts without `evidence_refs` to
    `degraded_facts` with
    `degradation_reason="no_evidence_refs_supplied"` plus a
    matching warning; deduplicates `evidence_refs` and
    `source_reports` in first-seen order; runs the recursive
    `_assert_no_forbidden_fields` guard at the serialisation
    boundary.
  - `_scan_for_forbidden_input` recursive intake guard
    rejecting `previous_ai_answer`, `prior_ai_answer`,
    `last_ai_answer`, `ai_session_history`,
    `ai_chat_history`, `chat_history`,
    `conversation_history`, `assistant_history`,
    `previous_briefing`, `previous_summary`,
    `previous_reflection`, `private_account_state`,
    `account_state`, `account_balance`, `account_balances`,
    `account_positions`, `account_orders`,
    `account_leverage`, `account_margin`, `wallet_balance`,
    `binance_account_state`,
    `binance_private_account_state`, `listen_key`,
    `listenkey`, `signed_endpoint_payload`, plus any
    credential-shaped key (substring tokens `api_key`,
    `api_secret`, `private_key`, `secret_key`, `auth_token`,
    `bearer_token`, `access_token`, `refresh_token`,
    `credential`, `password`, `passphrase`, `deepseek_api`,
    `binance_secret`, `telegram_token`,
    `telegram_bot_token`, plus the bare-token names
    `secret`, `secrets`, `token`).
  - `_assert_no_forbidden_fields` recursive output guard
    against `buy`, `sell`, `long`, `short`, `direction`,
    `side`, `entry`, `exit`, `position_size`, `leverage`,
    `stop`, `stop_loss`, `stop_price`, `target`,
    `target_price`, `take_profit`, `risk_budget`, `order`,
    `order_type`, `execution_command`,
    `runtime_config_patch`, `symbol_limit_patch`,
    `threshold_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, `strategy_parameter_patch`,
    `signal_to_trade`, `should_buy`, `should_short`, plus
    defensive aliases `trading_approved`, `live_ready`,
    `live_trading_allowed`.
  - `consumer_contract` block:
    - `allowed_consumers`: `human_operator`,
      `export_bundle`, `replay_annotation`,
      `reflection_annotation`, `operator_briefing_report`.
    - `forbidden_consumers`: `RiskEngine`, `ExecutionFSM`,
      `StrategyEngine`, `ExchangeGateway`, `RuntimeConfig`,
      `TelegramLiveCommand`, `CapitalFlow`,
      `PositionManager`.
  - `lookahead_policy` block (every flag `True`):
    `frozen_evidence_only`, `no_future_market_data`,
    `no_training_from_ai_output`, `no_runtime_feedback`,
    `post_hoc_analysis_only_when_window_closed`.
  - `safety_flags` block re-emitted on every `to_dict()`:
    `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`.
  - Does NOT import `app.risk`, `app.execution`,
    `app.exchanges`, `app.llm`, `app.telegram`, or
    `app.config` (AST-checked). Does NOT import `openai`,
    `anthropic`, `deepseek`, `httpx`, `requests`, `aiohttp`,
    `urllib3`, `websocket`, `websockets`, `grpc`, or
    `boto3` (AST-checked).
- New unit-test module
  `tests/unit/test_ai_evidence_bundle_builder.py` (55 cases)
  covering every brief-mandated scenario: builds bundle
  from valid evidence-cited facts, drops/degrades facts
  without `evidence_refs`, preserves `evidence_refs`,
  injects `forbidden_fields` / `lookahead_policy` /
  `consumer_contract`, rejects `previous_ai_answer` /
  `chat_history` / `private_account_state` /
  credential-like inputs at any nesting depth, no
  forbidden output fields as actionable decisions
  (parametrised over 18 fields), deterministic output,
  JSON-serializable output, forbidden imports
  (`app.risk` / `app.execution` / `app.exchanges` /
  `app.llm` / `app.telegram` / `app.config`) absent, no
  LLM / DeepSeek / HTTP call path (AST + public-callable
  check), AI output cannot become truth / training label
  field.
- New phase doc
  `docs/PHASE_AI_1_EVIDENCE_BUNDLE_BUILDER.md`.

#### Changed

- `docs/PROJECT_STATUS.md` — current phase flipped to
  Phase AI-1 **IN_REVIEW**; the previous Phase
  11C.1C-C-B-B-B-E-D IN_REVIEW entry is preserved for
  history.
- `docs/PHASE_GATE.md` — new IN_REVIEW section for
  Phase AI-1 inserted above the Block C Integrated
  Checkpoint IN_REVIEW section.

#### Tests

- `tests/unit/test_ai_evidence_bundle_builder.py` — 55/55
  PASS.
- Full `tests/unit` suite — 2781/2781 PASS (no regression
  vs. post-PR-#81 main 2726 baseline; +55 new tests on
  the new module).

#### Forbidden surface (verbatim)

  - `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`,
    `app/config/**`.
  - `symbol_limit` / `candidate_pool` / anomaly
    threshold / Regime-weight runtime knobs.
  - Binance private API (no API key, no API secret, no
    signed endpoint, no `listenKey`, no private WS).
  - Live orders.
  - Real Telegram outbound.
  - DeepSeek / LLM trade decisions (direction, position
    size, leverage, stop-loss, target price, execution
    command, runtime config patch).
  - DeepSeek / LLM call path of any kind (no `openai`,
    `anthropic`, `deepseek`, `httpx`, `requests`,
    `aiohttp`, `urllib3`, `websocket`, `websockets`,
    `grpc`, `boto3` import).
  - Automatic parameter tuning.
  - AI Layer reading previous AI answers / chat history /
    private account state / API secrets.
  - Phase 12 (real money / live trading).

#### Why this PR does NOT call DeepSeek

The bundle is the *substrate* a later DeepSeek integration
will read from. The bundle builder itself does not call any
LLM, does not open any network socket, and does not import
any LLM / HTTP / WebSocket client. The unit-test harness
asserts both invariants on every CI run via AST inspection
of the source.

#### Why this PR does NOT authorise live trading

The bundle never carries direction, sizing, leverage, stop,
target, risk-budget, order, or execution-command fields.
The recursive `_assert_no_forbidden_fields` guard refuses
to emit any payload carrying any of those keys at any
nesting depth, both on intake and at the serialisation
boundary. Every emitted bundle re-pins
`mode=paper` / `live_trading=False` /
`exchange_live_orders=False` / `right_tail=False` /
`llm=False` / `telegram_outbound_enabled=False` /
`binance_private_api_enabled=False` in the `safety_flags`
block. Live-trading approval is a Phase 12 concern that
requires the Spec §41 Go/No-Go checklist, and the
checklist has **not** been initiated.

#### Why this PR does NOT authorise auto-tuning

Every emitted bundle carries `auto_tuning_allowed=false`
and `phase_12_forbidden=true`. Both are hard-pinned at
every `to_dict()` boundary even if a downstream caller
flips the dataclass field. The recursive
`_assert_no_forbidden_fields` guard refuses to emit any
payload that contains a `*_patch` key
(`runtime_config_patch`, `symbol_limit_patch`,
`threshold_patch`, `candidate_pool_patch`,
`regime_weight_patch`, `strategy_parameter_patch`).

#### Why a successful Phase AI-1 authorises only later offline AI / Reality Check work

`Phase AI-1 = IN_REVIEW` (and eventually `ACCEPTED`)
opens **only** later (separately gated) offline AI /
operator-briefing report generation that consumes the
bundle as a frozen input AND the eventual AI Reality
Check layer that verifies AI commentary against the
Truth Layer. It does **not** open Phase 12, does
**not** open DeepSeek trade decisions, does **not**
open the AI Layer's involvement in the Risk Engine /
Execution FSM, and does **not** open auto-tuning.

---

### Phase 11C.1C-C-B-B-B-E-D — Block C Integrated Checkpoint v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** **none on real trading.** A new runner
`scripts/run_block_c_integrated_checkpoint.py` is added together
with a matching unit-test module under
`tests/unit/test_block_c_integrated_checkpoint.py` (15 tests). No
file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/llm/`, `app/telegram/`, `app/config/`, or any database schema
/ migration is touched. The runner is read-only: it never appends,
mutates, or reorders rows in `events.db`; it never produces
direction, sizing, leverage, stop, target, or risk-budget fields;
it never produces a `runtime_config_patch`; and it never calls an
LLM / DeepSeek / Telegram outbound. No runtime knob (`symbol_limit`,
anomaly threshold, candidate pool capacity, Regime weights) is
changed. The runner is a thin file-based aggregator that walks
`events.jsonl` / `*.jsonl` files under `--reports-dir` /
`--exports-dir`, loads the most recent
`block_b_integrated_evidence_report.json` under `--block-b-dir`,
drives the already-merged C1 replay builders, the C2
`Reflection11CAdaptiveEngine`, and the C3
`EvidenceContractValidator`, and emits one descriptive
`block_c_integrated_checkpoint_report.json` (plus matching `.md`
summary) under `--output-dir`. The status taxonomy is
intentionally **not** `ACCEPTED`: `INSUFFICIENT_EVIDENCE` /
`PARTIAL_EVIDENCE` / `EVIDENCE_GENERATED`. `next_allowed_phase`
is one of `Phase AI-0 / AI Evidence Bundle preparation (paper /
read-only)` or `NEEDS_OPERATOR_EVIDENCE` — neither string
references Phase 12, "live", or "trading-approved" wording. This
phase does NOT retrofit existing C1 / C2 / C3 surfaces — they
continue to ship exactly as before.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-E-D as
**`IN_REVIEW`** (not `ACCEPTED` until maintainer review of the PR
plus the eventual whole-block Block C closeout).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=False` is
hard-pinned on every emitted Block C checkpoint payload; the
runner asserts the value at the serialisation boundary alongside
a closed forbidden-key vocabulary (direction / sizing /
risk-budget / runtime-config patch keys plus the defensive
aliases `trading_approved`, `live_ready`, `live_trading_allowed`).
**Successor allowed:** only the upcoming **Block C closeout**
(whole-block, after the integrated checkpoint is reviewed) **OR**
the eventual **Phase AI-0 / AI Evidence Bundle preparation**
(paper / read-only). No other phase is unlocked.
**Tests:**
`python -m pytest tests/unit/test_block_c_integrated_checkpoint.py -q`
ships 15 tests, all PASS;
`python -m pytest tests/unit -q` reports 2726 PASS, 0 failures
(was 2711 before this phase; +15 from this phase).

### Phase 11C.1C-C-B-B-B-E-C — Evidence Contract Baseline v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** **none on real trading.** A new read-only
package `app/evidence/` is added with
`app/evidence/evidence_contract.py` and a matching unit-test
module under `tests/unit/test_evidence_contract_baseline.py`.
Three new descriptive event types are registered on
`app.core.events.EventType`: `EVIDENCE_CONTRACT_VALIDATED`,
`EVIDENCE_CLAIM_DEGRADED`, `EVIDENCE_CLAIM_REJECTED`. No file
under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/llm/`, `app/telegram/`, `app/config/`, or any database
schema / migration is touched. The contract is read-only: it
never appends, mutates, or reorders rows in `events.db`; it
never produces direction, sizing, leverage, stop, target, or
risk-budget fields; it never produces a `runtime_config_patch`;
and it never calls an LLM / DeepSeek / Telegram outbound. No
runtime knob (`symbol_limit`, anomaly threshold, candidate pool
capacity, Regime weights) is changed. The validator only emits
structured per-claim statuses, summary counts, and warnings
drawn from closed enums; it never emits free-form
natural-language reasoning. This phase does NOT retrofit
existing Block A / Block B surfaces — their existing
`evidence_refs: tuple[str, ...]` fields continue to ship as
before.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-E-C as
**`IN_REVIEW`** (not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=False` is
hard-pinned on every emitted `EvidenceContractResult`; the value
is re-emitted as `False` from `to_dict()` even if a caller
overrides the dataclass field.
**Successor allowed:** only the upcoming **Block C closeout**
(whole-block, after C1 + C2 + C3 are merged and reviewed) **OR**
the eventual **AI Evidence Bundle preparation**. No other phase is
unlocked.
**Tests:**
`python -m pytest tests/unit/test_evidence_contract_baseline.py -q`
ships 31 tests, all PASS;
`python -m pytest tests/unit -q` reports 2711 PASS, 0 failures
(was 2680 before this phase; +31 from this phase).

### Phase 11C.1C-C-B-B-B-E-B — Reflection Extension for 11C Adaptive Events v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report-only).
**Runtime effect:** **none on real trading.** A new read-only
module `app/reflection/adaptive_11c.py` is added and re-exported
from `app/reflection/__init__.py`. A matching unit-test module
under `tests/unit/test_reflection_11c_adaptive_events.py` is added.
No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/llm/`, `app/telegram/`, `app/config/`, or any database schema
/ migration is touched. The reflection extension is read-only:
it never appends, mutates, or reorders rows in `events.db`; it
never produces direction, sizing, leverage, stop, target, or
risk-budget fields; it never produces a `runtime_config_patch`;
and it never calls an LLM / DeepSeek / Telegram outbound. No
runtime knob (`symbol_limit`, anomaly threshold, candidate pool
capacity, Regime weights) is changed. Reflection only emits
structured tags / summaries / counts / warnings; it never emits
free-form natural-language reflection.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-E-B as
**`IN_REVIEW`** (not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Auto-tuning effect:** **none.** `auto_tuning_allowed=False` is
hard-pinned on every emitted case + summary; the value is
re-emitted as `False` from `to_payload()` even if a caller
overrides the dataclass field.
**Successor allowed:** only Phase 11C.1C-C-B-B-B-E-C *C3 Evidence
Contract Baseline*. No other phase is unlocked.
**Tests:**
`python -m pytest tests/unit/test_reflection_11c_adaptive_events.py -q`
ships 42 tests, all PASS;
`python -m pytest tests/unit -q` reports 2680 PASS, 0 failures.

### Phase 11C.1C-C-B-B-B-E-A — Replay Extension for 11C Adaptive Events v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / replay / report-only).
**Runtime effect:** **none on real trading.** A new read-only
module `app/replay/adaptive_replay_11c.py` is added and re-exported
from `app/replay/__init__.py`. A matching unit-test module under
`tests/unit/test_replay_11c_adaptive_events.py` is added. No file
under `app/risk/`, `app/execution/`, `app/exchanges/`, `app/llm/`,
`app/telegram/`, `app/config/`, or any database schema / migration
is touched. The replay extension is read-only: it never appends,
mutates, or reorders rows in `events.db`; it never produces
direction, sizing, leverage, stop, target, or risk-budget fields;
and it never produces a `runtime_config_patch`. No runtime knob
(`symbol_limit`, anomaly threshold, candidate pool capacity, Regime
weights) is changed.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-E-A as
**`IN_REVIEW`** (not `ACCEPTED` until maintainer review of the PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no API
secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound. **Phase 12
remains FORBIDDEN.**
**Successor allowed:** only Phase 11C.1C-C-B-B-B-E-B *Reflection
Extension for 11C Adaptive Events v0*. No other phase is unlocked.
**Tests:** `python -m pytest tests/unit/test_replay_11c_adaptive_events.py -q`
(25 tests, all pass) and `python -m pytest tests/unit -q` (full
unit suite green).

### Phase 11C.1C-C-B-B-B-D-E — Block B Integrated Evidence Checkpoint v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** **none on real trading.** A new read-only
runner under `scripts/` and a matching unit-test module under
`tests/unit/` are added. No file under `app/risk/`,
`app/execution/`, `app/exchanges/`, `app/llm/`,
`app/telegram/`, `app/config/`, or any database schema /
migration is touched. No new `app/adaptive/` engine is added —
the runner reuses the existing
`app.adaptive.discovery_quality_scorecard` builder + recursive
forbidden-keys guard. No runtime knob (`symbol_limit`, anomaly
threshold, candidate pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-D-E as
**`IN_REVIEW`** (not `ACCEPTED` until evidence closeout).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**
**Auto-tuning authority granted:** **none.**
**Phase 12:** **FORBIDDEN.**

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).** Block B (the
> D-A → D-B → B1.1 → B2-A → B2-B → B3 sequence) has shipped
> six paper / report / evidence-only slices. The project
> still lacked a single descriptive aggregated report that
> an operator can read at-a-glance to answer "Is Block B as
> a whole in a state where it is sane to open the Block C
> Replay / Reflection extension for 11C Adaptive Events, or
> do we need more operator evidence first?". This slice
> ships that aggregation as a paper / report /
> evidence-only Block B Integrated Evidence Checkpoint v0.
> The runner reads only local artefacts under
> `data/reports/`, `data/reports/exports/`, and
> `data/reports/post_discovery_outcome/`, and writes one
> `block_b_integrated_evidence_report.json` plus one
> matching `.md` summary under
> `data/reports/block_b_integrated_evidence/`. Status
> taxonomy is intentionally **not** `ACCEPTED`:
> `INSUFFICIENT_EVIDENCE` / `PARTIAL_EVIDENCE` /
> `EVIDENCE_GENERATED`. `next_allowed_phase` is either
> `Phase 11C.1C-C-B-B-B-E-A Replay Extension for 11C
> Adaptive Events v0` (paper / evidence only) or
> `NEEDS_OPERATOR_EVIDENCE`. **Phase 12 remains FORBIDDEN.**
> `phase_12_forbidden = true` and
> `auto_tuning_allowed = false` are hard-pinned on every
> emitted payload. The Risk Engine remains the single
> trade-decision gate.

#### Added

- `scripts/run_block_b_integrated_evidence_checkpoint.py` —
  paper / report / evidence-only runner that aggregates the
  simplified D-A / D-B / B1.1 / B2-A / B2-B / B3 outputs
  into one Block B Integrated Evidence Report. Ships:
  - CLI flags `--reports-dir` (default `data/reports`),
    `--exports-dir` (default `data/reports/exports`),
    `--post-discovery-dir` (default
    `data/reports/post_discovery_outcome`),
    `--output-dir` (default
    `data/reports/block_b_integrated_evidence`),
    `--reference-window` (default `60d`).
  - Closed status taxonomy
    (`INSUFFICIENT_EVIDENCE` / `PARTIAL_EVIDENCE` /
    `EVIDENCE_GENERATED`) — intentionally **not**
    `ACCEPTED`.
  - Per-component statuses for D-A, D-B, B1.1, B2-A, B2-B,
    B3.
  - Counters: `evaluated_count`, `coverage_record_count`,
    `post_discovery_record_count`,
    `price_path_records_loaded`,
    `price_path_records_missing`, `severe_miss_count`,
    `false_negative_reject_count`,
    `correct_protective_reject_count`, `data_gap_count`,
    `discovery_quality_bucket`.
  - Notable-symbols watchlist (`RAVEUSDT`, `STOUSDT`).
  - `known_blockers` / `known_non_blocking_gaps` operator-
    routing surfaces.
  - Hard-pinned `phase_12_forbidden = true` and
    `auto_tuning_allowed = false` on every emitted
    payload.
  - Reuses the existing
    `app.adaptive.discovery_quality_scorecard.build_discovery_quality_scorecard`
    builder and the existing recursive
    `assert_payload_has_no_forbidden_keys` guard. Refuses
    to emit any payload that contains a forbidden trade-
    authority / runtime-tuning key (`buy` / `sell` /
    `long` / `short` / `direction` / `side` / `entry` /
    `exit` / `position_size` / `leverage` / `stop` /
    `stop_loss` / `target` / `take_profit` /
    `risk_budget` / `order` / `execution_command` /
    `runtime_config_patch` / `symbol_limit_patch` /
    `threshold_patch` / `candidate_pool_patch` /
    `regime_weight_patch`).
  - Does NOT import `app.risk`, `app.execution`,
    `app.exchanges`, `app.llm`, `app.telegram`, or
    `app.config` (AST-checked).
- New unit-test module
  `tests/unit/test_block_b_integrated_evidence_checkpoint.py`
  (13 cases) covering every brief-mandated acceptance
  test: `INSUFFICIENT_EVIDENCE` on empty workspace,
  `PARTIAL_EVIDENCE` when D-B post-discovery is missing OR
  data-gap is high, `EVIDENCE_GENERATED` when every
  component is present, `next_allowed_phase` correct,
  `phase_12_forbidden = true` on every payload,
  `auto_tuning_allowed = false` on every payload, no
  forbidden trade-authority / runtime-tuning keys on any
  payload (recursive walk of the on-disk JSON), no banned
  imports of `app.risk` / `app.execution` /
  `app.exchanges` / `app.llm` / `app.telegram` (AST + raw
  source check), CLI exit-codes correct, notable-symbols
  block always present.
- New phase doc
  `docs/PHASE_11C_1C_C_B_B_B_D_E_BLOCK_B_INTEGRATED_EVIDENCE_CHECKPOINT.md`.

#### Tests

- `tests/unit/test_block_b_integrated_evidence_checkpoint.py` —
  13/13 PASS.
- Full `tests/unit` suite — 2600/2600 PASS (no regression
  vs. post-PR-#75 main 2587 baseline; +13 new tests on the
  new runner).

#### Forbidden surface (verbatim)

  - `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/llm/**`, `app/telegram/**`,
    `app/config/**`.
  - `symbol_limit` / `candidate_pool` / anomaly
    threshold / Regime-weight runtime knobs.
  - Binance private API (no API key, no API secret, no
    signed endpoint, no `listenKey`, no private WS).
  - Live orders.
  - Real Telegram outbound.
  - DeepSeek / LLM trade decisions (direction, position
    size, leverage, stop-loss, target price, execution
    command, runtime config patch).
  - Automatic parameter tuning (incl. `symbol_limit`
    expansion, anomaly threshold change, candidate pool
    capacity change, Regime weight change).
  - Phase 12 (real money / live trading).

#### Why this PR does NOT authorise live trading

The integrated checkpoint answers a coverage / capture /
outcome / attribution / triage / discovery-quality question
at the **evidence aggregation level**. It does not simulate
PnL, never reproduces a Risk Engine decision, never runs an
Execution FSM. A `status = EVIDENCE_GENERATED` does **not**
mean live trading is approved. A
`status = INSUFFICIENT_EVIDENCE` does **not** mean live
trading is *disapproved* either; live-trading approval is a
Phase 12 concern that requires the Spec §41 Go/No-Go
checklist, and the checklist has not been initiated.

#### Why this PR does NOT authorise auto-tuning

Every emitted checkpoint carries
`auto_tuning_allowed = false`. The constant is hard-pinned
in the runner source. The recursive forbidden-keys guard
refuses to emit any payload that contains a `*_patch` key.
A `data_gap_count` counter or a
`false_negative_reject_count` counter does **not**
authorise the Risk Engine, the Execution FSM,
`symbol_limit`, the candidate pool, anomaly thresholds, or
Regime weights to be changed. Routing a case to the
operator review queue is a *human* decision, not an
automated one.

#### Why a successful checkpoint authorises only Block C Replay / Reflection

`status = EVIDENCE_GENERATED` (or `PARTIAL_EVIDENCE`) opens
**only** `Phase 11C.1C-C-B-B-B-E-A Replay Extension for
11C Adaptive Events v0`. That phase is itself paper /
report / evidence-only. It extends the existing Replay
engine to play back the Block B adaptive events
(D-A / D-B / B1.1 / B2-A / B2-B / B3) over previously
captured event streams. It does **not** open Phase 12,
does **not** open DeepSeek trade decisions, and does
**not** open auto-tuning.
`status = INSUFFICIENT_EVIDENCE` opens nothing
automatically — the operator must collect more Block B
evidence before any later phase is reachable.

---

### Phase 11C.1C-C-B-B-B-D-D — Discovery Quality Scorecard v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** **none on real trading.** A new pure /
deterministic engine in `app/adaptive/` and two new typed
events in `app/core/events.py` are added. No file under
`app/risk/`, `app/execution/`, `app/exchanges/`, `app/llm/`,
`app/telegram/`, `app/config/`, or any database schema /
migration is touched. No runtime knob (`symbol_limit`, anomaly
threshold, candidate pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-D-D as
**`IN_REVIEW`** (not `ACCEPTED` until evidence closeout).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**
**Phase 12:** **FORBIDDEN.**

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).** Phase
> 11C.1C-C-B-B-B-D-A audited *discovery* (did we see the
> mover?). Phase 11C.1C-C-B-B-B-D-B audited *post-discovery
> outcome* (how much room remained after first sighting?).
> Phase 11C.1C-C-B-B-B-D-C-A closed the loop on *reject
> correctness*. Phase 11C.1C-C-B-B-B-D-C-B attributed
> *severe misses* to a closed root-cause taxonomy. The
> project still lacked a single descriptive number that an
> operator can read at-a-glance to answer "how healthy was
> discovery quality on this audit window?". This slice
> ships that compression layer as a paper / report /
> evidence-only Discovery Quality Scorecard v0. The
> scorecard takes the simplified outputs of D-A / D-B /
> B2-A / B2-B and emits, per audit window, one descriptive
> `quality_bucket` (`GOOD` / `PARTIAL` / `WEAK` /
> `DEGRADED` / `INSUFFICIENT_EVIDENCE`) plus the per-axis
> rates, the preserved `root_cause_summary`, the
> `notable_warnings`, the operator-routing flags
> (`needs_operator_review` / `needs_data_recovery` /
> `needs_rule_review`), and a hard-pinned
> `auto_tuning_allowed=False` flag. **Phase 12 remains
> FORBIDDEN.**

#### Added

- `app/adaptive/discovery_quality_scorecard.py` — paper /
  pure / deterministic engine that turns one
  `DiscoveryQualityScorecardInput` into one
  `DiscoveryQualityScorecard`. Ships:
  - `DiscoveryQualityBucket` closed string-constant
    taxonomy (`GOOD` / `PARTIAL` / `WEAK` / `DEGRADED` /
    `INSUFFICIENT_EVIDENCE`).
  - `DiscoveryQualityScorecardInput` (frozen dataclass)
    bundling the simplified D-A / D-B / B2-A / B2-B
    outputs.
  - `DiscoveryQualityScorecard` (frozen dataclass) carrying
    the descriptive bucket, per-axis rates,
    operator-routing flags, preserved `root_cause_summary`,
    `notable_warnings`, `evidence_refs`.
  - `DiscoveryQualityScorecardEngine` /
    `DiscoveryQualityScorecardEngineConfig` plus the
    `build_discovery_quality_scorecard` convenience
    builder.
  - `assert_payload_has_no_forbidden_keys` recursive guard
    against any trade-authority / runtime-tuning field
    landing in a payload (`buy` / `sell` / `long` /
    `short` / `direction` / `side` / `entry` / `exit` /
    `position_size` / `leverage` / `stop` / `stop_loss` /
    `target` / `take_profit` / `risk_budget` / `order` /
    `execution_command` / `runtime_config_patch` /
    `symbol_limit_patch` / `threshold_patch` /
    `candidate_pool_patch` / `regime_weight_patch`).
  - Hard-pinned `auto_tuning_allowed=False` on every
    emitted scorecard.
- Two new typed events in `app/core/events.py`:
  - `EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED`
  - `EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED`
- Public exports added to `app/adaptive/__init__.py`.
- New unit-test module
  `tests/unit/test_discovery_quality_scorecard.py` (22
  cases) covering every brief-mandated acceptance test:
  insufficient evidence (when `coverage_total_count=0` or
  `evidence_refs=()`), GOOD / PARTIAL on clean inputs,
  PARTIAL / WEAK / DEGRADED with `needs_data_recovery=True`
  on high data-gap or insufficient-price-path rate,
  WEAK / DEGRADED with `needs_operator_review=True` on
  high severe-miss rate, `needs_rule_review=True` with
  `auto_tuning_allowed=False` on high false-negative-reject
  rate, `root_cause_summary` preserved on output, forbidden
  fields absent on every payload, no forbidden imports of
  `app.risk` / `app.execution` / `app.exchanges` /
  `app.llm` / `app.telegram`.
- New phase doc
  `docs/PHASE_11C_1C_C_B_B_B_D_D_DISCOVERY_QUALITY_SCORECARD.md`.

#### Changed

- `docs/PROJECT_STATUS.md` — current phase flipped to
  Phase 11C.1C-C-B-B-B-D-D **IN_REVIEW**; the previous
  Phase 11C.1C-C-B-B-B-D-C-B IN_REVIEW entry is preserved
  for history.
- `docs/PHASE_GATE.md` — new ledger row for Phase
  11C.1C-C-B-B-B-D-D **IN_REVIEW**.

#### Tests

- `tests/unit/test_discovery_quality_scorecard.py` — 22/22
  PASS.
- Full `tests/unit` suite — 2587/2587 PASS (no regression
  vs. post-PR-#74 main 2565 baseline; +22 new tests on the
  new module).

#### Why this PR does NOT authorise auto-tuning

Every emitted scorecard carries `auto_tuning_allowed=False`,
and the constant is hard-pinned in
`DiscoveryQualityScorecard.to_dict()` so a downstream
serialiser cannot accidentally relax it. A `DEGRADED`
bucket is the strongest signal the layer can emit — and
even there, the bucket reflects **one audit window**, not
a portfolio of cases. Touching `symbol_limit` / anomaly
thresholds / candidate-pool capacity / Regime weights /
Risk Engine on the basis of a scorecard window is **out of
scope** for this phase. A high `false_negative_reject_rate`
flips `needs_rule_review=True`, but `auto_tuning_allowed`
stays `False`; rule review is a *human* decision, not an
automated one.

#### Why GOOD / PARTIAL / DEGRADED are discovery-quality labels, not trade-approval labels

`GOOD` / `PARTIAL` / `WEAK` / `DEGRADED` describe
**discovery health** — how often the discovery pipeline
(radar + filter + candidate pool + first-seen detection)
saw the moves the historical reference set lists. They do
**not** describe *strategy quality* (Phase 11C.1C-C-B-A's
territory), *risk-decision quality* (D-C-A), *outcome
quality* (D-B), or *trade-approval quality* (Phase 12). A
`GOOD` bucket does **not** mean live trading is approved.
A `DEGRADED` bucket does **not** mean live trading is
disapproved. Both are diagnostic signals for a human
operator, not switches the runtime can flip.

### Phase 11C.1C-C-B-B-B-D-C-B — Severe Missed Tail Triage v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** **none on real trading.** A new pure /
deterministic engine in `app/adaptive/` and three new typed
events in `app/core/events.py` are added. No file under
`app/risk/`, `app/execution/`, `app/exchanges/`, `app/llm/`,
`app/telegram/`, `app/config/`, or any database schema /
migration is touched. No runtime knob (`symbol_limit`, anomaly
threshold, candidate pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-D-C-B as
**`IN_REVIEW`** (not `ACCEPTED` until evidence closeout).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**
**Phase 12:** **FORBIDDEN.**

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).** Phase
> 11C.1C-C-B-B-B-D-A described the *discovery* layer (did we
> see the mover, when, how deep). Phase 11C.1C-C-B-B-B-D-B /
> B.1 described the *post-discovery outcome* (how much room
> remained after first sighting, with the daily-bucket
> price-path adapter). Phase 11C.1C-C-B-B-B-D-C-A closed the
> loop between candidate-level reject decisions and the
> post-discovery outcome ("was the reject the right call?").
> The project still lacked one piece: when a meaningful
> mover such as `RAVEUSDT` or `STOUSDT` shows up in the
> historical 60D mover reference set but not in the radar's
> captured set, **why** did we miss it? This slice ships that
> root-cause triage as a paper / report / evidence layer.
> The triage emits, per audited severe miss, a closed
> `SevereMissRootCause` (`UNIVERSE_GAP` / `SYMBOL_LIMIT_GAP`
> / `CANDIDATE_POOL_EVICTED` / `THRESHOLD_TOO_STRICT` /
> `PRE_ANOMALY_WEAK` / `ANOMALY_TOO_LATE` / `WS_DATA_GAP` /
> `REST_REFERENCE_GAP` / `EVENT_HISTORY_MISSING` /
> `PRICE_PATH_MISSING` / `PRICE_PATH_INSUFFICIENT` /
> `NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME` /
> `RISK_REJECTED_PROTECTIVE` /
> `RISK_REJECTED_FALSE_NEGATIVE` /
> `STRATEGY_MODE_FALSE_NEGATIVE` / `LABEL_WINDOW_TOO_SHORT` /
> `TRUE_DISCOVERY_FAILURE` / `INSUFFICIENT_EVIDENCE` /
> `UNKNOWN`) plus a closed `SevereMissSeverity` (`LOW` /
> `MEDIUM` / `HIGH` / `SEVERE` / `CRITICAL` /
> `INSUFFICIENT_EVIDENCE`). Every record / report carries
> `auto_tuning_allowed=False`. **Phase 12 remains FORBIDDEN.**

#### Added

  - `app/adaptive/severe_missed_tail_triage.py` (paper / pure /
    deterministic):
      - `SevereMissTriageInput`, `SevereMissTriageRecord`,
        `SevereMissTriageReport`,
        `SevereMissedTailTriageEngine`,
        `SevereMissedTailTriageEngineConfig`.
      - `SevereMissRootCause` closed string-constant taxonomy:
        `UNIVERSE_GAP`, `SYMBOL_LIMIT_GAP`,
        `CANDIDATE_POOL_EVICTED`, `THRESHOLD_TOO_STRICT`,
        `PRE_ANOMALY_WEAK`, `ANOMALY_TOO_LATE`, `WS_DATA_GAP`,
        `REST_REFERENCE_GAP`, `EVENT_HISTORY_MISSING`,
        `PRICE_PATH_MISSING`, `PRICE_PATH_INSUFFICIENT`,
        `NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME`,
        `RISK_REJECTED_PROTECTIVE`,
        `RISK_REJECTED_FALSE_NEGATIVE`,
        `STRATEGY_MODE_FALSE_NEGATIVE`,
        `LABEL_WINDOW_TOO_SHORT`, `TRUE_DISCOVERY_FAILURE`,
        `INSUFFICIENT_EVIDENCE`, `UNKNOWN`.
      - `SevereMissSeverity` closed string-constant taxonomy:
        `LOW`, `MEDIUM`, `HIGH`, `SEVERE`, `CRITICAL`,
        `INSUFFICIENT_EVIDENCE`.
      - Default severity map (`ROOT_CAUSE_DEFAULT_SEVERITY`)
        binding each root cause to its triage routing severity.
      - `assert_payload_has_no_forbidden_keys` recursive guard
        against any trade-authority / runtime-tuning field
        landing in a payload.
      - Hard-pinned `auto_tuning_allowed=False` on every
        emitted record / report.
      - Triage decision-flow priority: insufficient_evidence →
        universe_gap → symbol_limit_gap →
        candidate_pool_evicted → price_path_missing →
        risk_protective → risk_false_negative →
        strategy_mode_false_negative → true_discovery_failure →
        unknown.
  - Three new typed events in `app/core/events.py` (paper /
    report / evidence only):
      - `EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED`
      - `EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED`
      - `EventType.SEVERE_MISS_ESCALATION_REQUIRED`
  - Public exports added to `app/adaptive/__init__.py`.
  - `tests/unit/test_severe_missed_tail_triage.py` — 22 cases
    covering every brief-mandated acceptance test (price path
    missing RAVE / STO style routes to data-recovery without
    asserting threshold problem, candidate pool evicted,
    symbol limit gap with `needs_rule_review=True` and
    `auto_tuning_allowed=False`, universe gap, risk rejected
    protective parametrised over 5 protective verdicts, risk
    rejected false negative with severity `CRITICAL` and
    `auto_tuning_allowed=False`, strategy mode false negative,
    true discovery failure on positive MFE, insufficient
    evidence refuses to fabricate, forbidden fields absent on
    every record / report payload, no forbidden imports of
    `app.risk` / `app.execution` / `app.exchanges` /
    `app.llm` / `app.telegram`).
  - Phase doc
    `docs/PHASE_11C_1C_C_B_B_B_D_C_B_SEVERE_MISSED_TAIL_TRIAGE.md`.
  - Phase status entry in `docs/PROJECT_STATUS.md`,
    `docs/PHASE_GATE.md` Open / Reserved phases table, and
    this changelog.

#### Tests

  - `python -m pytest tests/unit/test_severe_missed_tail_triage.py -q`
    → **22 passed**.
  - `python -m pytest tests/unit -q` → **2565 passed** (+22
    vs. post-PR-#74 main 2543 baseline; no regression).

#### Forbidden surface (verbatim)

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/llm/**`, `app/telegram/**`, `app/config/**`.
  - `symbol_limit` / `candidate_pool` / anomaly threshold /
    Regime-weight runtime knobs.
  - Binance private API (no API key, no API secret, no signed
    endpoint, no `listenKey`, no private WS).
  - Live orders.
  - Real Telegram outbound.
  - DeepSeek / LLM trade decisions (direction, position size,
    leverage, stop-loss, target price, execution command,
    runtime config patch).
  - Automatic parameter tuning (incl. `symbol_limit`
    expansion, anomaly threshold change, candidate pool
    capacity change, Regime weight change).
  - Phase 12 (real money / live trading).

#### Why this PR does NOT authorise auto-tuning

A `RISK_REJECTED_FALSE_NEGATIVE` verdict (severity
`CRITICAL`) is the strongest signal the layer can emit — and
even there, the verdict reflects ONE candidate's outcome,
not a portfolio of cases. Outcome volatility is high in
altcoin momentum; rule changes affect every future
candidate, not just the one in front of the reviewer.
Touching the rule itself is **out of scope** for this
phase. `auto_tuning_allowed` is hard-pinned to `False` on
every emitted record and on every emitted report; the
recursive `assert_payload_has_no_forbidden_keys` guard
defends every emission point against a planted
trade-authority / runtime-tuning field.

#### Why `RAVEUSDT` / `STOUSDT` cannot yet be classified as parameter errors

Under the B1 / B1.1 closeout, both symbols carry
`price_path_loaded=false`, `source=absent`,
`missing_reason=no_top_mover_row_covering_first_seen_time`.
From that fact alone the layer cannot distinguish a true
discovery failure, a risk-rejected false negative, a
strategy-mode false negative, or a data gap. Asserting "the
threshold is too strict" against a single coin from this
evidence base would be **looking at the answer key** — the
auto-tuning failure mode the brief explicitly forbids. Both
symbols are therefore classified as
`NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME` /
`MEDIUM` / `needs_data_recovery=True` /
`needs_rule_review=False` / `auto_tuning_allowed=False` —
data-gap triage candidates only.

#### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

### Phase 11C.1C-C-B-B-B-D-C-A — Reject-to-Outcome Attribution v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** **none on real trading.** A new pure /
deterministic engine in `app/adaptive/` and four new typed
events in `app/core/events.py` are added. No file under
`app/risk/`, `app/execution/`, `app/exchanges/`, `app/llm/`,
`app/telegram/`, `app/config/`, or any database schema /
migration is touched. No runtime knob (`symbol_limit`, anomaly
threshold, candidate pool capacity, Regime weights) is changed.
**Phase ledger effect:** opens Phase 11C.1C-C-B-B-B-D-C-A as
**`IN_REVIEW`** (not `ACCEPTED` until evidence closeout).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**
**Phase 12:** **FORBIDDEN.**

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).** Phase
> 11C.1C-C-B-B-B-D-A described the *discovery* layer (did we
> see the mover, when, how deep). Phase 11C.1C-C-B-B-B-D-B /
> B.1 described the *post-discovery outcome* (how much room
> remained after first sighting, with the daily-bucket
> price-path adapter). The project still lacked a closed loop
> linking **candidate-level reject decisions** to those
> **outcome labels**. This slice ships that closure as a
> paper / report / evidence attribution layer:
> `opportunity_id` → `risk_reject_reason / no_trade_reason /
> strategy_mode` → `tail_label / post_discovery_outcome` →
> reject correctness verdict. **Phase 12 remains FORBIDDEN.**

#### Added

  - `app/adaptive/reject_to_outcome_attribution.py` (paper /
    pure / deterministic):
      - `RejectAttributionInput`,
        `RejectAttributionRecord`,
        `RejectAttributionReport`,
        `RejectToOutcomeAttributionEngine`,
        `RejectAttributionEngineConfig`.
      - `RejectAttributionVerdict` closed string-constant
        taxonomy: `CORRECT_PROTECTIVE_REJECT`,
        `FALSE_NEGATIVE_REJECT`, `DATA_QUALITY_REJECT`,
        `LIQUIDITY_PROTECTIVE_REJECT`,
        `MANIPULATION_PROTECTIVE_REJECT`,
        `STOP_SAFETY_REJECT`,
        `REBASE_PROTECTIVE_REJECT`,
        `SYSTEM_SAFETY_REJECT`,
        `STRATEGY_MODE_FALSE_NEGATIVE`,
        `NO_REJECT_FOUND`, `INSUFFICIENT_EVIDENCE`,
        `UNKNOWN`.
      - Reason / flag substring taxonomies for stop safety,
        system safety, data quality, liquidity, manipulation,
        and rebase rejects.
      - `assert_payload_has_no_forbidden_keys` recursive
        guard against any trade-authority / runtime-tuning
        field landing in a payload.
      - Hard-pinned `auto_tuning_allowed=False` on every
        emitted record / report.
  - Four new typed events in `app/core/events.py` (paper /
    report / evidence only):
      - `EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED`
      - `EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED`
      - `EventType.FALSE_NEGATIVE_REJECT_DETECTED`
      - `EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED`
  - Public exports added to `app/adaptive/__init__.py`.
  - `tests/unit/test_reject_to_outcome_attribution.py` —
    43 cases covering every brief-mandated acceptance test
    (stop safety reject remains protective even on positive
    MFE, data quality reject `needs_data_recovery=True`,
    liquidity protective reject, manipulation protective
    reject, false negative reject `needs_operator_review=True`
    `needs_rule_review=True` `auto_tuning_allowed=False`,
    strategy mode false negative, no reject found,
    insufficient evidence, forbidden fields absent on every
    record / report payload, no forbidden imports of
    `app.risk` / `app.execution` / `app.exchanges` /
    `app.llm` / `app.telegram`).
  - Phase doc
    `docs/PHASE_11C_1C_C_B_B_B_D_C_A_REJECT_TO_OUTCOME_ATTRIBUTION.md`.
  - Phase status entry in `docs/PROJECT_STATUS.md`,
    `docs/PHASE_GATE.md` Open / Reserved phases table, and
    this changelog.

#### Tests

  - `python -m pytest tests/unit/test_reject_to_outcome_attribution.py -q`
    → **43 passed**.
  - `python -m pytest tests/unit -q` → **2543 passed** (+12
    vs. post-PR-#71 main 2531 baseline; no regression).

#### Forbidden surface (verbatim)

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/llm/**`, `app/telegram/**`, `app/config/**`.
  - Binance private API (no API key, no API secret, no signed
    endpoint, no `listenKey`, no private WS).
  - Live orders.
  - Real Telegram outbound.
  - DeepSeek / LLM trade decisions (direction, position size,
    leverage, stop-loss, target price, execution command,
    runtime config patch).
  - Automatic parameter tuning (incl. `symbol_limit`
    expansion, anomaly threshold change, candidate pool
    capacity change, Regime weight change).
  - Phase 12 (real money / live trading).

#### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account / order / position / leverage / margin endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

**The Risk Engine remains the single trade-decision gate.**

#### Why a `FALSE_NEGATIVE_REJECT` does NOT mean "loosen the Risk Engine"

A false-negative verdict is a single-case observation: at
least one candidate ran upside after a non-hard-safety
reject. It does **NOT** mean the Risk Engine's *policy* is
wrong. It does **NOT** account for the cases the same rule
prevented from going wrong. It does **NOT** guarantee a
similar outcome on the next candidate. It MUST be reviewed by
a human, against a portfolio of cases, before any rule is
touched. The rule-touching itself is **out of scope** for
this phase. Every emitted record carries
`auto_tuning_allowed=False` regardless of verdict; the
aggregate `RejectAttributionReport.auto_tuning_allowed` is
also hard-pinned to `False`.

### Phase 11C.1C-C-B-B-B-D-B.1 — Historical Price Path Completeness / Kline Path Adapter v0 evidence closeout: ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY (docs-only)

**Type:** Docs-only evidence closeout (paper / report /
evidence only).
**Runtime effect:** **none.** No file under `app/`, `scripts/`,
`tests/`, `configs/`, `risk/`, `execution/`, `exchanges/`,
`llm/`, `telegram/`, or database schema is touched. Only
`docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
`docs/CHANGELOG.md`, `docs/PR_DESCRIPTION.md`, and
`docs/PHASE_11C_1C_C_B_B_B_D_B_1_HISTORICAL_PRICE_PATH_KLINE_PATH_ADAPTER.md`
are modified.
**Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-D-B.1 from
`IN_REVIEW` (after PR #71 implementation) to
**`ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
DAILY_BUCKET_ONLY`** — explicitly **NOT** "intraday 1m / 5m
kline path solved".
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**
**Phase 12:** **FORBIDDEN.**

> **Status: ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
> DAILY_BUCKET_ONLY.** PR #71 merged the Historical Price
> Path Adapter v0 / Kline Path Adapter v0 implementation into
> `main` (record-level price-path resolution; operator-
> supplied-path Lookahead Guard; daily-bucket adapter from
> `data/historical_market_store/top_movers/*.jsonl`). The
> real D-B evidence runner was rerun on `main` from the
> operator VPS against the new adapter. This docs-only
> closeout PR records the resulting B1.1 main-evidence run
> and flips the slice to
> `ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
> DAILY_BUCKET_ONLY`. **Next allowed route: B2 — Severe
> Missed Tail Triage v0.** Phase 12 remains **FORBIDDEN**.

#### Required closeout statements (verbatim)

  1. **B1.1 toolchain passed.**
  2. **PR #71 evidence runner can evaluate 300 records.**
  3. **300 `POST_DISCOVERY_OUTCOME_EVALUATED` events were
     emitted.**
  4. **1 `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event was
     emitted.**
  5. **The price-path adapter is currently daily-bucket
     only (`kline_interval_used = 1d`).**
  6. **The local Historical Market Store currently supplies
     a price path for 17 of 300 records.**
  7. **283 of 300 records still lack a price path.**
  8. **`RAVEUSDT` and `STOUSDT` remain unresolved with
     `missing_reason =
     no_top_mover_row_covering_first_seen_time`.**
  9. **B1.1 does NOT mean intraday 1m / 5m kline path is
     solved.**
  10. **B1.1 does NOT solve direction.**
  11. **B1.1 does NOT prove strategy profitability.**
  12. **B1.1 does NOT authorise auto-tuning.**
  13. **B1.1 does NOT authorise DeepSeek trade decisions.**
  14. **Phase 12 remains FORBIDDEN.**

#### B1.1 evidence run output (operator VPS, real D-A export)

Output directory:
`data/reports/post_discovery_outcome/pr71_main_price_path_evidence`

Summary:

  - `status = EVIDENCE_GENERATED`
  - `evaluated_count = 300`
  - `report_generated_count = 1`
  - `event_counts.POST_DISCOVERY_OUTCOME_EVALUATED = 300`
  - `event_counts.POST_DISCOVERY_OUTCOME_REPORT_GENERATED = 1`
  - `kline_interval_used = 1d`

Price path resolution coverage:

  - `price_path_records_loaded = 17`
  - `price_path_records_missing = 283`

Price path source summary:

  - `historical_market_store_daily_top_movers = 17`
  - `absent = 283`

Price path missing-reason summary:

  - `no_top_mover_row_covering_first_seen_time = 133`
  - `no_first_seen_time = 110`
  - `insufficient_post_first_seen_points = 40`

Notable symbol price-path summary:

  - `RAVEUSDT` — `loaded = false`,
    `loaded_record_count = 0`, `record_count = 17`,
    `source = absent`, `missing_reason =
    no_top_mover_row_covering_first_seen_time`.
  - `STOUSDT` — `loaded = false`,
    `loaded_record_count = 0`, `record_count = 3`,
    `source = absent`, `missing_reason =
    no_top_mover_row_covering_first_seen_time`.

Warnings:

  - `d_a_backfill_records_missing_using_record_audited_fallback`
    (Format B fallback engaged; expected for the real D-A
    export shape; carried over from the B1 closeout and
    unchanged in B1.1).

Main-evidence check: **`B1_1_PRICE_PATH_MAIN_EVIDENCE_CHECK
= PASS`**.

#### What this acceptance level MEANS

  - **B1.1 toolchain works end-to-end** against the real
    D-A export. Record-level price-path resolution is
    enforced (no longer symbol-only and no longer
    first-record-wins); the operator-supplied-path
    Lookahead Guard is enforced (no point with `timestamp >
    first_seen_time_utc_ms` may serve as
    `first_seen_price`); the runner emits 300
    `POST_DISCOVERY_OUTCOME_EVALUATED` events plus 1
    `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event under
    `data/reports/post_discovery_outcome/pr71_main_price_path_evidence/`.
  - **Coverage is partial.** Only 17 of 300 records have an
    adapter-loaded price path today; 283 of 300 remain
    `absent`.
  - **The price-path resolution is daily-bucket only.**
    `kline_interval_used = 1d`. **B1.1 does NOT solve the
    intraday 1m / 5m kline path problem.**

#### What this acceptance level does NOT MEAN

  - **B1.1 does NOT mean intraday 1m / 5m kline path is
    solved.** It is daily-bucket only.
  - **B1.1 does NOT solve direction.**
  - **B1.1 does NOT prove strategy profitability.**
  - **B1.1 does NOT authorise auto-tuning.**
  - **B1.1 does NOT authorise DeepSeek trade decisions.**
  - **Phase 12 remains FORBIDDEN.**

#### Next allowed route (mainline; back on the main route)

> **Next allowed route: B2 — Severe Missed Tail Triage v0.**

B1 is a focused branch off the mainline and is **not** to
be extended indefinitely. B1.1 is the small patch on B1,
and B1.1 closeout returns the project to the main route.

B2 will perform root-cause triage on unresolved
severe-miss cases such as `RAVEUSDT` and `STOUSDT`,
attributing each into a closed bucket that includes (but
is not limited to): `PRICE_PATH_GAP`, `DATA_UNRELIABLE`,
`EVENT_HISTORY_MISSING`, `UNIVERSE_GAP`,
`SYMBOL_LIMIT_GAP`, `CANDIDATE_POOL_EVICTED`,
`THRESHOLD_TOO_STRICT`, `WS_DATA_GAP`,
`REST_REFERENCE_GAP`, `RISK_REJECTED_BUT_MOVED`,
`TRUE_DISCOVERY_FAILURE`, `UNKNOWN`.

B2 remains forbidden from authorising auto-tuning, any
threshold change, `symbol_limit` expansion, candidate-pool
capacity change, Regime weight change, live trading,
DeepSeek trade decision, or Phase 12.

A *Historical Kline Store Builder / Intraday Price Path
Backfill* (sometimes referred to as "B1.2") is **NOT**
started now. It is recorded as an **optional future
data-quality task only**, available **only if** B2 triage
proves that severe-miss attribution is blocked by missing
intraday price paths, and **only with explicit owner
approval**. It is **not** the recommended next slice,
**not** a precondition for B2, and **does not** block B2.

#### Out of scope / unchanged (this docs-only closeout PR)

  - **No** file under `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `exchanges/`,
    `llm/`, `telegram/`, or database schema is touched.
  - **No** event name is added, removed, or renamed.
  - **No** schema version is changed.
  - **No** runtime behaviour is changed.
  - **No** test was run by this PR.
  - **No** paper run, export, replay, or historical builder
    was invoked by this PR.
  - **No** real API was contacted by this PR.
  - **No** Risk Engine, Execution FSM, exchange-private,
    LLM, or Telegram surface is touched.
  - **No** change to `symbol_limit`, candidate-pool
    capacity, anomaly thresholds, or Regime weights.
  - **No** Phase 12 work; Phase 12 remains **FORBIDDEN**.

#### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no private API
  - no live orders
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

### Phase 11C.1C-C-B-B-B-D-B.1 (PR #71 follow-up fix) — Historical Price Path Adapter v0 / Kline Path Adapter v0 — record-level resolution + operator-path Lookahead Guard

**Type:** Bugfix on PR #71 (paper / report / evidence ONLY).
**Runtime effect:** **none.** No `app/risk/`, `app/execution/`,
`app/exchanges/`, `app/llm/`, `app/telegram/`, `configs/`,
event-name, schema-version, or runtime-trading-behaviour change.
Only `app/adaptive/post_discovery_price_path_adapter.py`,
`scripts/run_post_discovery_outcome_evidence.py`, and the two
matching unit-test files are touched.
**Phase ledger effect:** keeps Phase 11C.1C-C-B-B-B-D-B.1 in
`IN_REVIEW` — does NOT flip the slice to `ACCEPTED`. The slice
remains `PARTIAL_QUALITY` because the adapter still emits a
**daily-bucket** path, not a precise intraday 1m / 5m kline
path (see "Granularity disclosure" below).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**
**Phase 12:** **FORBIDDEN.**

#### Two merge-blocking issues fixed (per PR71 review)

1. **Record-level price-path resolution.**
   `resolve_price_paths_for_records()` previously returned
   `dict[str, PricePathResolution]` keyed by symbol with
   first-record-wins semantics. A symbol that appeared more
   than once in the 60-day audit (different
   `first_seen_time_utc_ms` /
   `mover_window_start_utc_ms` /
   `mover_window_end_utc_ms`) silently shared the FIRST
   record's resolution with every later record, polluting the
   later record's outcome with the first record's price path.
   The fix changes the return type to
   `list[PricePathResolution | None]` aligned by index with the
   input `records` sequence; each record now consumes ITS OWN
   resolution. The matching `build_post_discovery_inputs_from_d_a_payload`
   accepts `Sequence[PricePathResolution | None]` and looks
   up by record index, not by symbol.

2. **Operator-supplied path Lookahead Guard.**
   Both `resolve_price_paths_for_records` and the legacy
   `build_post_discovery_inputs_from_d_a_payload` operator
   branch previously set
   `first_seen_price = float(operator_path[0].price)` without
   checking the timestamp. When `operator_path[0].timestamp_utc_ms > first_seen_time_utc_ms`
   this turned a future price into the discovery anchor — a
   classic lookahead leak that AMA-RT's hard-rule Lookahead
   Guard forbids. The fix introduces
   `build_operator_supplied_price_path_resolution()` in
   `app/adaptive/post_discovery_price_path_adapter.py`, which
   enforces:
   * `first_seen_price` is **only** drawn from a point with
     `timestamp <= first_seen_time_utc_ms` (the latest such
     operator point), or — when no such operator point exists —
     from a `fallback_resolution.first_seen_price` (the
     adapter's containing-day open, lookahead-safe by
     construction). Otherwise `first_seen_price = None` and
     `missing_reason = OPERATOR_PATH_STARTS_AFTER_FIRST_SEEN`.
   * `price_path` only contains operator points with
     `timestamp > first_seen_time_utc_ms` (strictly after).
   * Without `first_seen_time_utc_ms` the operator path is
     rejected wholesale (`missing_reason = NO_FIRST_SEEN_TIME`).

#### Lookahead Guard reaffirmation (hard rule, NOT a suggestion)

  * `first_seen_time_utc_ms` is read-only and never modified.
  * `first_seen_price` is only the price observed AT or BEFORE
    `first_seen_time_utc_ms` (operator anchor / capture-path
    anchor / containing-day open).
  * `price_path_after_first_seen` only carries points strictly
    AFTER `first_seen_time_utc_ms`.
  * peak / trough / MFE / MAE / remaining_upside are computed
    only post-window for audit.
  * future outcome NEVER feeds radar score, candidate
    promotion, Risk Engine, Execution FSM,
    `symbol_limit`, anomaly threshold, candidate-pool
    capacity, or Regime weights.
  * DeepSeek / LLM may explain evidence but cannot reverse-
    derive trading decisions from future results.

#### Granularity disclosure (NOT precise intraday kline path)

The B1.1 Historical Price Path Adapter v0 still resolves a
**daily-bucket** path from
`data/historical_market_store/top_movers/*.jsonl` (per-day
OHLC). The `kline_interval_used` diagnostic emits `"1d"`. For
the containing day only the close at `day_end_ms` is emitted
(open / high / low intra-day timestamps are unknown and may
have been before `first_seen_time`). For subsequent days the
high / low are stamped at `day_end_ms`, surfaced as
`approximate_intra_day_timestamps = true`. **This is NOT a
1m / 5m intraday kline path.** The slice remains
`PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT` until an operator
supplies precise intraday paths via `--price-paths-json` (with
a pre-first-seen anchor) or a future precise-kline adapter
lands. The adapter never fabricates intraday prices and never
manufactures an anchor that did not exist in lookahead-safe
territory.

#### Required output diagnostic columns retained

  * `kline_interval_used`
  * `price_path_source_summary`
  * `price_path_missing_reason_summary`
  * `price_path_records_loaded`
  * `price_path_records_missing`
  * `notable_symbol_price_path_summary`

When the local Historical Market Store has no rows for a
symbol's containing day, the adapter emits a clear missing
reason (`SYMBOL_NOT_IN_HISTORICAL_STORE`,
`NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME`,
`HISTORICAL_STORE_DIR_MISSING`, ...). The runner does NOT
fabricate prices; it surfaces the gap as an explicit
operator-data requirement.

#### Tests added / updated

  * `tests/unit/test_post_discovery_price_path_adapter.py`:
    8 new tests for `build_operator_supplied_price_path_resolution`
    covering Case 2 (anchor strictly after first_seen, no
    fallback), Case 2 with adapter fallback, Case 3 (anchor at-
    or-before first_seen, post-first-seen path strictly after),
    no-first_seen-time rejection, empty operator path,
    latest-pre-first-seen-anchor selection, never-uses-future-
    as-anchor regression guard, and the closed missing-reason
    taxonomy guard.
  * `tests/unit/test_post_discovery_outcome_evidence_runner.py`:
    3 new end-to-end runner tests:
      * `test_pr71_case_1_duplicate_symbol_distinct_windows_get_distinct_paths`
        — verifies record-level resolution (no first-record-wins).
      * `test_pr71_case_2_operator_path_starts_after_first_seen_no_anchor`
        — verifies the future operator point is NEVER used as
        `first_seen_price` and the missing reason is
        `OPERATOR_PATH_STARTS_AFTER_FIRST_SEEN`.
      * `test_pr71_case_3_operator_path_anchor_at_or_before_first_seen`
        — verifies the lookahead-safe anchor is used and the
        post-first-seen path excludes the anchor.
  * Updated `test_resolve_price_paths_for_records_uses_operator_priority`,
    `test_resolve_price_paths_skips_records_with_no_symbol`,
    `test_runner_operator_price_paths_refine_outcome` to use
    the new `list[PricePathResolution | None]` interface and
    to provide a lookahead-safe anchor where required.

#### Confirmations

  * No `app/risk/` change.
  * No `app/execution/` change (Execution FSM untouched).
  * No `app/exchanges/` change (private API untouched, no
    Binance live orders).
  * No `app/llm/` change (no DeepSeek call).
  * No `app/telegram/` change (no Telegram outbound).
  * No `configs/` change.
  * No event-name change.
  * No schema-version change.
  * No `symbol_limit` / candidate-pool capacity / anomaly
    threshold / Regime weight change.
  * No long / short / buy / sell / position size / leverage /
    stop / target / execution recommendation generated.
  * No future outcome reverse-pollutes `first_seen_time` /
    discovery path / radar score / candidate promotion.
  * Phase 12 remains **FORBIDDEN**.

### Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0 evidence closeout: ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT (docs-only)

**Type:** Docs-only evidence closeout (paper / report / evidence
only).
**Runtime effect:** **none.** No file under `app/`, `scripts/`,
`tests/`, `configs/`, `risk/`, `execution/`, `exchanges/`,
`llm/`, `telegram/`, or database schema is touched. Only
`docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
`docs/CHANGELOG.md`, `docs/PR_DESCRIPTION.md`, and
`docs/PHASE_11C_1C_C_B_B_B_D_B_POST_DISCOVERY_OUTCOME_METRICS.md`
are modified.
**Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-D-B from
`IN_REVIEW / INSUFFICIENT_EVIDENCE / EVIDENCE_CLOSEOUT_ONLY`
(after PR #67 implementation + PR #68 evidence-runner empty
marker) to **`ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
PRICE_PATH_INSUFFICIENT`** — explicitly **NOT** full quality
accepted.
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**

> **Status: ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
> PRICE_PATH_INSUFFICIENT.** PR #69 fixed the D-B evidence
> runner input adapter gap so the runner consumes the **real**
> D-A export shape. The real VPS D-A export evidence was
> rerun on `main`. This docs-only closeout PR records the
> resulting B1 evidence run and flips the slice to
> `ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
> PRICE_PATH_INSUFFICIENT`. Phase 12 remains **FORBIDDEN**.

#### Required closeout statements (verbatim)

  1. **PR #69 fixed the D-B runner input adapter gap.**
  2. **D-B can now consume real D-A export records.**
  3. **300 D-A records were evaluated.**
  4. **`POST_DISCOVERY_OUTCOME_REPORT_GENERATED` was
     produced.**
  5. **The output is evidence-generated, but NOT
     direction-quality accepted.**
  6. **195 / 300 records are `INSUFFICIENT_PRICE_PATH`.**
  7. **105 / 300 records are `MISSED_STRONG_TAIL`.**
  8. **`RAVEUSDT` and `STOUSDT` remain unresolved because
     they are `INSUFFICIENT_PRICE_PATH /
     INSUFFICIENT_DATA`.**
  9. **D-B does NOT solve direction.**
  10. **D-B does NOT prove strategy profitability.**
  11. **D-B does NOT authorise auto-tuning.**
  12. **D-B does NOT authorise DeepSeek trade decisions.**
  13. **Phase 12 remains FORBIDDEN.**

#### D-A export input check (real VPS rerun on `main`)

  - `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = 2`
  - `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = 300`
  - `D_A_EXPORT_INPUT_CHECK = PASS`

#### B1 evidence run output

Output directory:
`data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence`

Summary:

  - `status = EVIDENCE_GENERATED`
  - `reference_window = 60d`
  - `evaluated_count = 300`
  - `report_generated_count = 1`
  - `output_report =
    data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/post_discovery_outcome_report.json`
  - `output_events =
    data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/events.jsonl`

Outcome label summary:

  - `INSUFFICIENT_PRICE_PATH = 195 / 300`
  - `MISSED_STRONG_TAIL = 105 / 300`

Detection timing summary:

  - `INSUFFICIENT_DATA = 195 / 300`
  - `MISSED = 105 / 300`

Notable symbols (still unresolved by D-B alone):

  - `RAVEUSDT` — `INSUFFICIENT_PRICE_PATH /
    INSUFFICIENT_DATA`.
  - `STOUSDT` — `INSUFFICIENT_PRICE_PATH /
    INSUFFICIENT_DATA`.

Warnings:

  - `d_a_backfill_records_missing_using_record_audited_fallback`
    (Format B fallback engaged; expected for the real D-A
    export shape, where
    `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED.payload.records`
    is `None` and the per-mover records ride on
    `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`).

#### Next allowed route (paper-only; gated, sequential)

  - **B1 (this slice) closeout** accepted as **toolchain +
    partial quality only**, NOT direction-quality.
  - Then **either** (operator's choice, gated by an
    explicit kickoff PR per slice):
      - **B1.1** — *Historical Price Path Completeness /
        Kline Path Adapter* — recommended; needed because
        195/300 records lack sufficient post-first-seen
        price path and `RAVEUSDT` / `STOUSDT` remain
        unresolved on price-path / data-gap grounds.
      - **B2** — *Severe Missed Tail Triage* — admissible
        **only with the explicit note that `RAVEUSDT` and
        `STOUSDT` currently require price-path / data-gap
        triage** before they can be classified as severe
        missed tails by D-B alone.
  - The **next allowed route is NOT** to start DeepSeek
    directly, and is **NOT** to start blind walk-forward
    directly.
  - Recommended next slice after this docs PR: **B1.1
    Price Path Completeness / Kline Path Adapter.**

#### Out of scope / unchanged (this docs-only closeout PR)

  - **No** file under `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `exchanges/`,
    `llm/`, `telegram/`, or database schema is touched.
  - **No** event name is added, removed, or renamed.
  - **No** schema version is changed.
  - **No** runtime behaviour is changed.
  - **No** test was run by this PR.
  - **No** paper run, export, replay, or historical builder
    was invoked by this PR.
  - **No** real API was contacted by this PR.
  - **No** Risk Engine, Execution FSM, exchange-private,
    LLM, or Telegram surface is touched.
  - **No** change to `symbol_limit`, candidate-pool
    capacity, anomaly thresholds, or Regime weights.
  - **No** Phase 12 work; Phase 12 remains **FORBIDDEN**.

#### Safety boundary (held end-to-end)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no private API
  - no live orders
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

### Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0 evidence runner: real D-A export input adapter

**Type:** Evidence runner fix (paper / report / evidence only).
**Runtime effect:** none. Only `scripts/run_post_discovery_outcome_evidence.py`
and its unit tests are modified.
**Trade authority granted:** none. Phase 12 remains FORBIDDEN.

The Phase 11C.1C-C-B-B-B-D-B evidence runner used to read D-A
records exclusively from
`HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED.payload.records`.
The real D-A export observed on the operator VPS emits that
event with `records` missing / `None` and ships the per-mover
records on separate `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`
events whose payload **is** the record (not wrapped in a
`record` key). The runner therefore produced
`evaluated_count = 0` despite a passing D-A export input check
(300 audited movers, miss audit ready), and the closeout final
check failed with `D_B_EVALUATED_COUNT_ZERO`.

**Fix:**

- Add a Format B input adapter to
  `scripts/run_post_discovery_outcome_evidence.py`. The runner
  now scans the export dir / events DB for
  `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` events and adapts
  each payload into a D-A record dict.
- The adapter supports both shapes: `payload['record']` (legacy /
  wrapped form) **and** `payload` itself (real D-A export emit).
- Symbol resolution falls back through `record["symbol"]` →
  `record["reference"]["symbol"]` → `record["capture_path"]["symbol"]`
  → event-level `symbol`.
- Priority: if `BACKFILL_GENERATED.payload.records` is non-empty
  it is used as before; otherwise the runner falls back to the
  RECORD_AUDITED records and synthesises a payload that re-uses
  the BACKFILL_GENERATED report-level fields.
- All canonical D-A record fields are preserved on the adapted
  output: `coverage_status`, `reference`, `capture_path`,
  `miss_reason`, `miss_reasons`, `first_seen_time_utc_ms`,
  `first_seen_event_type`, `first_seen_latency_seconds`,
  `capture_path_depth`, `risk_rejected`, `reached_anomaly`,
  `reached_label_queue`, `reached_tail_label`,
  `reached_strategy_validation_sample`.
- Closeout-quality guard: when the export carries
  RECORD_AUDITED events but the D-B input adapter produces zero
  inputs, the runner now emits a new explicit warning
  `d_a_records_present_but_no_post_discovery_inputs` and sets
  status `INSUFFICIENT_EVALUABLE_RECORDS` with non-zero CLI
  exit code so closeout tooling refuses to mark the phase
  ACCEPTED.

**Out of scope / unchanged:**

- No event names changed.
- No schema versions changed.
- No runtime trading behaviour changed.
- No Risk Engine change.
- No Execution FSM change.
- No exchange-private / Binance-private API call.
- No LLM / DeepSeek call.
- No Telegram outbound.
- No change to `symbol_limit`, candidate-pool capacity,
  anomaly thresholds, or Regime weights.
- Phase 12 remains FORBIDDEN.

**Tests:**

- `tests/unit/test_post_discovery_outcome_evidence_runner.py`
  extended with Case A (Format A `records` path), Case B
  (Format B flat-payload RECORD_AUDITED fallback - mirrors the
  operator-VPS shape, asserts `evaluated_count > 0`), Case B'
  (RECORD_AUDITED wrapped-payload fallback), Case C (RECORD_
  AUDITED present but unusable), and adapter-level unit tests
  for the symbol-fallback chain.



**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** new pure module under `app/adaptive/` plus
two new typed `EventType` values. The Phase 11C public-market
paper runner is **NOT** modified by this PR. **No** strategy,
**no** runtime config, **no** threshold, **no** `symbol_limit`,
**no** candidate-pool capacity, **no** Regime weight, and **no**
Risk / Execution / Exchange-private / LLM / Telegram surface is
touched.
**Phase ledger effect:** adds Phase 11C.1C-C-B-B-B-D-B as the
fifth child slice under Phase 11C.1C-C-B-B-B and marks it
**`IN_REVIEW`** (after the implementation PR; not `ACCEPTED`
until a separate evidence-closeout PR).
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**

> **Status: IMPLEMENTATION PR.** This PR ships the v0 engine /
> payload / report / forbidden-fields guard implementation for
> Phase 11C.1C-C-B-B-B-D-B (*Post-Discovery Outcome Metrics v0
> / 发现后结果度量 v0*). The module is paper / report /
> evidence only. **No** real trade is authorised; **no**
> position size, leverage, stop-loss, target price, Risk
> Engine threshold, Execution FSM rule, `symbol_limit`,
> candidate-pool capacity, anomaly threshold, Regime weight,
> or any other runtime knob is modified by this PR or by any
> record / report it produces. The Risk Engine remains the
> single trade-decision gate. Phase 12 remains **FORBIDDEN**.

#### Why this slice

  - Phase 11C.1C-C-B-B-B-D-A only describes the *discovery*
    layer ("did we see this mover, when, how deep").
  - Phase 11C.1C-C-B-B-B-D-A does **NOT** answer how much
    room remained after the first sighting, nor whether
    that sighting was early / late / choppy / fake breakout
    / late reversal / missed strong tail.
  - The operator was doing this cross-check manually against
    K-lines. Phase 11C.1C-C-B-B-B-D-B turns that manual
    cross-check into a structured, exportable, replayable,
    auditable set of **outcome metrics + closed labels**.

#### Implementation summary

  - New module
    `app/adaptive/post_discovery_outcome_metrics.py`
    (paper / pure / deterministic):
      - `PostDiscoveryOutcomeInput` (one mover's
        first-seen + price-path bundle).
      - `PostDiscoveryOutcomeRecord` (one mover's evaluated
        outcome).
      - `PostDiscoveryOutcomeReport` (aggregate roll-up).
      - `PostDiscoveryOutcomeEvaluator` /
        `PostDiscoveryOutcomeEvaluatorConfig`.
      - `DetectionTimingLabel` (`EARLY` /
        `EARLY_BUT_CHOPPY` / `MID_MOVE` / `LATE` /
        `TOO_LATE` / `MISSED` / `INSUFFICIENT_DATA`).
      - `OutcomeLabel` (`EARLY_CONTINUATION` /
        `EARLY_BUT_CHOPPY` / `LATE_TOP_CHASE` /
        `LATE_REVERSAL` / `MISSED_STRONG_TAIL` /
        `FAKE_BREAKOUT` / `DUMPED` /
        `EXHAUSTION_CANDIDATE` / `NO_CLEAR_EDGE` /
        `INSUFFICIENT_PRICE_PATH`).
      - `PricePoint`, `HistoricalMoverReferenceSummary`.
      - `assert_payload_has_no_forbidden_keys` recursive
        guard against `buy` / `sell` / `long` / `short` /
        `direction` / `entry` / `exit` / `position_size` /
        `leverage` / `stop` / `stop_loss` / `target` /
        `take_profit` / `risk_budget` / `order` /
        `execution_command` / `runtime_config_patch` /
        `symbol_limit_patch` / `threshold_patch` /
        `candidate_pool_patch` / `regime_weight_patch`.
  - Two new typed events in `app/core/events.py` (paper /
    report / evidence only):
      - `EventType.POST_DISCOVERY_OUTCOME_EVALUATED`
      - `EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED`
  - `app/adaptive/__init__.py` re-exports the new public
    surface.
  - New unit-test module
    `tests/unit/test_post_discovery_outcome_metrics.py`
    (20 cases) covering all 10 brief-mandated acceptance
    cases (early continuation, early but choppy, late top
    chase, late reversal, missed strong tail, fake
    breakout, insufficient price path, forbidden fields
    absent, no parameter tuning, no Risk / Execution / LLM
    / Telegram imports) plus aggregator + frozen-record
    invariants.
  - New phase doc
    `docs/PHASE_11C_1C_C_B_B_B_D_B_POST_DISCOVERY_OUTCOME_METRICS.md`.

#### Schema versions

  - `phase_11c_1c_c_b_b_b_d_b.post_discovery_outcome_metrics.v1`
    (records / reports payload schema).

#### Boundary (verbatim)

  - **NOT** complete strategy blind replay; **NOT** PnL
    backtest; **NOT** trading module; **NOT** AI Learning;
    **NOT** automatic parameter optimisation; **NOT**
    reinforcement learning; **NOT** the small-money
    live-trading pre-validation gate; **NOT** Severe
    Missed Tail Triage (later slice); **NOT** Replay /
    Reflection extension (later slice); **NOT** the
    DeepSeek integration; **NOT** Phase 12.
  - The detection_timing_label / outcome_label are
    **descriptive labels only**. Neither is an input to a
    trade-decision pipeline; the Risk Engine remains the
    single trade-decision gate.
  - The module MUST NEVER trigger a real trade, modify
    position size, leverage, stop-loss, target price, the
    Risk Engine, the Execution FSM, `symbol_limit`,
    candidate-pool capacity, anomaly thresholds, Regime
    weights, or any other runtime knob.
  - The module MUST NOT import `app.risk` /
    `app.execution` / `app.exchanges.binance` / `app.llm`
    / `app.telegram`.

#### Forbidden surface (verbatim)

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise API keys.
  - It does **NOT** authorise private endpoints.
  - It does **NOT** authorise signed endpoints.
  - It does **NOT** authorise `listenKey` / private
    WebSocket.
  - It does **NOT** authorise account / order / position
    / leverage / margin endpoints.
  - It does **NOT** authorise DeepSeek trade decisions.
  - It does **NOT** authorise real Telegram outbound.
  - It does **NOT** authorise AI Learning.
  - It does **NOT** authorise automatic parameter
    optimisation.
  - It does **NOT** authorise reinforcement learning.
  - It does **NOT** authorise rule relaxation based on
    outcome labels.
  - It does **NOT** authorise automatic `symbol_limit`
    expansion.
  - It does **NOT** authorise automatic anomaly threshold
    changes.
  - It does **NOT** authorise automatic candidate-pool
    capacity changes.
  - It does **NOT** authorise automatic Regime weight
    changes.
  - It does **NOT** authorise changing the Risk Engine
    or the Execution FSM.
  - It does **NOT** authorise direction classification
    (long / short / entry / exit / stop / target /
    position size / leverage).
  - It does **NOT** authorise replacing the D-A
    `PARTIAL_QUALITY` rule with a relaxed rule.
  - It does **NOT** authorise treating Phase
    11C.1C-C-B-B-B-D-B as a Historical 30D+ / 60D
    *complete strategy* blind replay / walk-forward
    validation.

#### Closeout note

  - This PR ships the v0 engine / payload / report /
    forbidden-fields guard implementation. A subsequent
    operator-driven evidence-collection run + a docs-only
    closeout PR will flip the slice to `ACCEPTED`.

### Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0 (evidence-closeout PR)

**Type:** Evidence-closeout PR (paper / report / evidence only).
**Runtime effect:** new paper-only script
`scripts/run_post_discovery_outcome_evidence.py`, an 8-case
runner unit-test module
`tests/unit/test_post_discovery_outcome_evidence_runner.py`,
plus the marker artefacts produced by running the runner
against the empty workspace. **No** strategy, **no** runtime
config, **no** threshold, **no** `symbol_limit`, **no**
candidate-pool capacity, **no** Regime weight, and **no**
Risk / Execution / Exchange-private / LLM / Telegram surface
is touched. **Phase ledger effect:** Phase
11C.1C-C-B-B-B-D-B remains **`IN_REVIEW /
INSUFFICIENT_EVIDENCE / EVIDENCE_CLOSEOUT_ONLY`** because
the workspace does not currently carry real Phase
11C.1C-C-B-B-B-D-A historical mover coverage records
(`data/historical_market_store/`, `data/sqlite/events.db`,
and `data/reports/exports/` are absent or empty). The runner
correctly refused to fabricate D-A records and wrote a marker
report. **Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**

> **Status: EVIDENCE-CLOSEOUT PR.** This PR adds the
> paper-only evidence runner + its tests + an honest
> `INSUFFICIENT_EVIDENCE` evidence run. D-B will be flipped
> to `ACCEPTED` only after a follow-up operator-driven run
> against real D-A artefacts.

#### Implementation summary

  - New paper-only script
    `scripts/run_post_discovery_outcome_evidence.py`. The
    runner consumes a Phase 11C.1C-C-B-B-B-D-A coverage
    payload (via `--coverage-payload`, `--export-dir`, or
    `--events-db`; `--historical-store-dir` recorded as a
    warning when no fresh-audit hook is reachable),
    optionally accepts an operator-supplied
    `--price-paths-json`, calls
    `PostDiscoveryOutcomeEvaluator.evaluate` once per
    audited mover, builds a
    `PostDiscoveryOutcomeReport`, and writes:
      - `events.jsonl` with one
        `POST_DISCOVERY_OUTCOME_EVALUATED` event per record
        and one `POST_DISCOVERY_OUTCOME_REPORT_GENERATED`
        event per batch.
      - `post_discovery_outcome_report.json` (full report
        payload).
      - `post_discovery_outcome_report.md` (markdown
        summary surfacing label / timing / notable-symbol
        / safety-boundary blocks).
  - When no D-A artefact is reachable, the runner writes a
    marker report with status `INSUFFICIENT_EVIDENCE` /
    `NEEDS_OPERATOR_DATA`, an empty `events.jsonl`, and the
    safety-boundary markdown summary; the CLI exits with
    status code `2` so a downstream caller cannot
    mistakenly mark D-B `ACCEPTED`.
  - New unit-test module
    `tests/unit/test_post_discovery_outcome_evidence_runner.py`
    (8 cases): insufficient-evidence path,
    coverage-payload happy path, missed-strong-tail
    surfacing, operator price-paths refinement, export-dir
    fallback, forbidden-key recursive guard on every
    artefact the runner writes, forbidden-imports static
    check on the runner source (`app.risk` /
    `app.execution` / `app.exchanges.binance` /
    `app.exchanges.binance_public_ws` / `app.llm` /
    `app.telegram` are absent), and CLI exit code on
    missing inputs.
  - No change to `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/llm/`, `app/telegram/`,
    `app/config/`, runtime thresholds, `symbol_limit`,
    `candidate_pool`, Regime weights, the DeepSeek
    transport, or the Telegram outbound transport.
  - No change to
    `app/adaptive/post_discovery_outcome_metrics.py` or
    `app/core/events.py`; the implementation surface from
    PR #67 stays intact.

#### Evidence run (this workspace)

The runner was invoked with the operator-style command:

```
python scripts/run_post_discovery_outcome_evidence.py \
  --historical-store-dir data/historical_market_store \
  --events-db data/sqlite/events.db \
  --export-dir data/reports/exports \
  --output-dir data/reports/post_discovery_outcome \
  --reference-window 60d
```

Outcome:

  - `status = INSUFFICIENT_EVIDENCE`,
    `needs_operator_data = true`,
    `evaluated_count = 0`,
    `report_generated_count = 0`,
    warnings:
    `export_dir_no_d_a_payload:data/reports/exports`,
    `events_db_no_d_a_payload:data/sqlite/events.db`,
    `historical_store_dir_missing:data/historical_market_store`,
    `NEEDS_OPERATOR_DATA`.
  - Output artefacts written:
    `data/reports/post_discovery_outcome/post_discovery_outcome_report.json`,
    `data/reports/post_discovery_outcome/post_discovery_outcome_report.md`,
    `data/reports/post_discovery_outcome/events.jsonl`
    (empty).
  - `RAVEUSDT` and `STOUSDT` are recorded as `ABSENT`
    because no D-A payload reached the runner; nothing
    was fabricated.

#### Tests

  - `tests/unit/test_post_discovery_outcome_metrics.py` -
    20/20 pass.
  - `tests/unit/test_post_discovery_outcome_evidence_runner.py`
    - 8/8 pass.
  - Full unit-test suite: `2450 passed`.

#### D-B status

  - **Status: IN_REVIEW / INSUFFICIENT_EVIDENCE /
    EVIDENCE_CLOSEOUT_ONLY.**
  - D-B does **NOT** authorise live trading.
  - D-B does **NOT** prove strategy profitability.
  - D-B does **NOT** solve direction.
  - D-B does **NOT** authorise automatic parameter tuning.
  - D-B does **NOT** authorise DeepSeek trade decisions.
  - Phase 12 remains **FORBIDDEN**.

### docs: Phase 11C.1C-C-B-B-B-D-A closeout

**Type:** docs-only consistency repair PR (paper / report /
evidence only). **Allowed files:** `README.md`,
`docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
`docs/CHANGELOG.md`,
`docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`. **Runtime
effect:** **none.** No file under `app/`, `scripts/`,
`tests/`, `data/`, `configs/`, `pyproject.toml`, or
`requirements.txt` is touched. **Strategy effect:**
**none.** **Config effect:** **none.** **Trade authority
granted:** **none.**

#### Summary

  - Phase 11C.1C-C-B-B-B-D-A (Historical 60D Mover Coverage
    Audit v0) is marked **ACCEPTED / PARTIAL_QUALITY /
    TOOLCHAIN_CLOSEOUT_ONLY** across `README.md`,
    `docs/PROJECT_STATUS.md`, and `docs/PHASE_GATE.md`.
  - 60D Historical Market Store reference data has been
    generated under `data/historical_market_store/` (D-A.1
    is the data-preparation child task and has completed
    its toolchain role).
  - `app.adaptive.historical_mover_coverage_backfill`
    produced D-A audit records against that reference
    store.
  - The Phase 8.5 export bundle now contains the
    `HISTORICAL_MOVER_COVERAGE_*` events that surface
    those records (audit output is replayable and
    externally reviewable).
  - Operator manual review result = **PARTIAL** with the
    following per-symbol verdict (recorded verbatim under
    `docs/PROJECT_STATUS.md` and `docs/PHASE_GATE.md`):
    `PLAYUSDT` qualified; `AGTUSDT` qualified provided
    the system is not shaken off by mid-window chop;
    `BEATUSDT` qualified; `VICUSDT` marginally usable;
    `BIOUSDT` usable; `PROVEUSDT` poor as a long, possibly
    workable as exhaustion / short; `USUSDT` not
    qualified.
  - **`RAVEUSDT` and `STOUSDT` are recorded as severe
    misses.** Severe misses trigger **later triage only**
    (Severe Missed Tail Triage); they do **not** authorise
    any automatic threshold change, `symbol_limit`
    expansion, candidate-pool capacity change, Regime
    weight change, or any other parameter tuning.
  - `docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md` is added
    as the AI-layer constitution docs baseline. It records
    the four root constraints (Responsibility Isolation,
    Stateless Inference, Hard Rule Anchoring, Feedback
    Isolation), the allowed DeepSeek first-version output
    types, the forbidden DeepSeek output fields, and the
    sandbox / offline boundary for any future DeepSeek
    integration.
  - **No runtime changes.**
  - **No config changes.**
  - **No strategy changes.**
  - **No Phase 12.** Phase 12 (real money / live trading)
    remains **FORBIDDEN** under the Phase 1 safety lock;
    Spec §41 Go/No-Go has not been initiated.
  - **No live trading authority** granted by D-A
    acceptance.
  - **No automatic parameter tuning** authorised by D-A
    acceptance.
  - **No DeepSeek trade authority** granted — DeepSeek
    remains read-only / sandbox-only / offline; it must
    not place orders, change position size, change
    leverage, change stop-loss, change target price,
    issue execution commands, or patch runtime config.
  - **No real Telegram outbound** authorised.
  - **No private Binance API** authorised — no API key,
    no API secret, no signed endpoint, no `listenKey`,
    no private WS.

The Risk Engine remains the single trade-decision gate.
Safety flags unchanged: `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`.

### Phase 11C.1C-C-B-B-B-D-A.1 - Historical 60D Mover Reference Store Builder v0 (PR #65)

**Type:** Data-preparation PR (paper / report / evidence only).
**Runtime effect:** new builder script under `scripts/`. The
public-market paper runner is **NOT** touched. The D-A audit
loader is **NOT** touched. The builder produces local artefacts
under `data/historical_market_store/` that the existing
`load_historical_market_store(...)` consumes unchanged.
**Phase ledger effect:** adds Phase 11C.1C-C-B-B-B-D-A.1 as a
data-preparation child task under Phase 11C.1C-C-B-B-B-D-A.
Phase 11C.1C-C-B-B-B-D-A *implementation* has been merged
(PR #64) and the operator-VPS WS paper smoke + Phase 8.5
export evidence has been validated, but Phase
11C.1C-C-B-B-B-D-A itself is **NOT yet `ACCEPTED`** — current
state `NOT_ACCEPTED / HISTORICAL_REFERENCE_DATA_REQUIRED /
CLOSEOUT_PENDING`: real 60D Historical Market Store reference
rows have not yet been generated, so D-A cannot be flipped to
`ACCEPTED`. PR #65 only adds the Historical 60D Mover
Reference Store Builder v0; PR #65 does **NOT** complete the
real 60D backfill; PR #65 does **NOT** flip D-A to
`ACCEPTED`. Real 60D data generation against Binance public
futures endpoints + operator evidence are required after
PR #65 merges before a separate docs-only closeout PR can
mark D-A `ACCEPTED`. **No** previously-`ACCEPTED` phase is
modified.
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**

> **Status: DATA-PREPARATION PR.** This PR ships a minimal,
> public-data-only **Historical 60D Mover Reference Store
> Builder v0** (`scripts/build_historical_mover_reference_store.py`).
> The builder fetches Binance public USDT-M perpetual futures
> `exchangeInfo` + 1 h klines + 24 h tickers, computes per-day
> top movers over the trailing window, and writes JSONL +
> manifest artefacts the existing D-A audit consumes through
> `app.adaptive.historical_mover_coverage_backfill.load_historical_market_store(root)`.
> Paper / report / evidence only. **NOT** strategy blind
> replay. **NOT** PnL backtest. **NOT** trading module. **NOT**
> AI Learning. **NOT** automatic parameter optimisation. **NOT**
> reinforcement learning. **NOT** the small-money live-trading
> pre-validation gate. **NOT** the Phase 11C.1C-C-B-B-B-D-A
> closeout. Phase 12 remains **FORBIDDEN**. The Risk Engine
> remains the single trade-decision gate.

#### Implementation summary

  - New module `scripts/build_historical_mover_reference_store.py`
    with the public-only data source, pure transformations,
    deterministic disk writers, an in-process `--no-network`
    transport, and a CLI:
      - `assert_no_credentials_in_env(env)` refuses to start
        when any of `BINANCE_API_KEY` / `BINANCE_API_SECRET` /
        `BINANCE_KEY` / `BINANCE_SECRET` / `BINANCE_TOKEN` /
        `BINANCE_PASSPHRASE` is set.
      - `BinanceFuturesPublicSource` reuses
        `app.exchanges.binance_public.assert_public_endpoint_allowed`
        and refuses every credential-shaped kwarg + every
        signed-request query parameter
        (`signature` / `timestamp` / `recvWindow` / `apiKey`).
      - `filter_eligible_usdt_perpetual_universe(exchange_info)`,
        `select_symbols_by_volume(...)`,
        `klines_to_daily_top_movers(...)` are pure functions
        used by both the CLI and the test suite.
      - `write_exchange_info_snapshot(...)`,
        `write_top_movers_jsonl(...)`, `write_manifest(...)`
        are no-ops under `--dry-run` and call
        `validate_no_lookahead_fields(...)` on every emitted
        row.
      - `build_no_network_source(...)` returns a deterministic
        in-process source for the `--no-network` smoke path.
      - `run_build(...)` is the single-entry orchestrator.
      - `main(argv)` is the CLI entry point with the
        brief-mandated flags.
  - Two new schema versions:
    `phase_11c_1c_c_b_b_b_d_a_1.historical_60d_mover_reference_store.v0`
    (builder) and
    `phase_11c_1c_c_b_b_b_d_a_1.historical_60d_mover_reference_store_builder.v0`
    (builder version).
  - On-disk layout (matches the existing D-A loader):
    `data/historical_market_store/exchange_info/*.json` +
    `*.jsonl`,
    `data/historical_market_store/top_movers/*.jsonl`,
    `data/historical_market_store/manifests/*.json`.
  - JSONL row schema includes both the brief-mandated columns
    (`symbol`, `mover_window_start_utc`, `mover_window_end_utc`,
    `reference_timestamp_utc`, `top_mover_rank`,
    `window_gain_pct`, `max_24h_gain_pct`, `open_price`,
    `close_price`, `high_price`, `low_price`, `quote_volume`,
    `eligible_usdt_perpetual`,
    `source = binance_public_futures_klines_1h`,
    `lookahead_policy = post_hoc_reference_only`,
    `generated_at_utc`) and the loader-required columns
    (`snapshot_date`, `reference_timestamp_utc_ms`,
    `mover_window_start_utc_ms`, `mover_window_end_utc_ms`,
    `max_window_gain`, `max_24h_gain`, `quote_volume_usdt`,
    `quote_asset`, `contract_type`).
  - Manifest records the public-only invariants
    (`public_endpoint_only=true`, `private_api_used=false`,
    `api_key_loaded=false`, `signed_endpoint_used=false`,
    `binance_private_api_enabled=false`,
    `telegram_outbound_enabled=false`,
    `live_trading_enabled=false`,
    `exchange_live_order_enabled=false`,
    `right_tail_enabled=false`, `llm_enabled=false`,
    `trading_mode="paper"`), the Lookahead Guard label
    (`lookahead_guard=reference_set_is_post_hoc_audit_only`,
    `lookahead_policy=post_hoc_reference_only`,
    `lookahead_forbidden_fields=[...]`), and a verbatim
    `boundary` block listing what the builder is **NOT**.
  - `.gitignore` updated to exclude
    `data/historical_market_store/` (the store is regenerated
    locally and must not be committed).
  - `app/adaptive/historical_mover_coverage_backfill.py` is
    **NOT** modified. The D-A audit's miss-reason taxonomy,
    event types, capture-path order, lookahead-guard helpers,
    and runtime payloads are untouched.

#### New tests

`tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_reference_store.py`
(16 cases):

  - `test_exchange_info_filters_usdt_perpetual_universe`
  - `test_select_symbols_by_volume_ranks_eligible_universe_only`
  - `test_select_symbols_with_no_limit_returns_alphabetical_universe`
  - `test_top_mover_reference_store_schema`
  - `test_window_gain_calculation_is_post_hoc_only`
  - `test_reference_builder_does_not_load_api_keys`
  - `test_reference_builder_does_not_use_signed_endpoints`
  - `test_reference_set_is_post_hoc_only`
  - `test_lookahead_guard_rejects_completed_tail_label_in_builder_output`
  - `test_manifest_records_public_only_invariants`
  - `test_top_movers_can_be_loaded_by_historical_coverage_backfill`
  - `test_missing_event_history_remains_valid_miss_reason`
  - `test_no_live_trading_flags_unchanged`
  - `test_phase_12_remains_forbidden`
  - `test_cli_dry_run_smoke`
  - `test_cli_refuses_with_credentials_in_env`

#### Lookahead Guard (verbatim)

  - `completed_tail_label` MUST NOT drive reference selection.
  - future return / final max gain MUST NOT pollute the
    simulated live-radar score.
  - replay label MUST NOT contaminate `first_seen_time`.
  - reflection / report text / LLM narrative MUST NEVER serve
    as a capture event source.
  - `first_seen_time_utc` MUST come from the timestamp of an
    event that already existed at audit time.
  - the top-mover reference set MUST only be used for post-hoc
    audit; it cannot rewrite past decisions.

The builder enforces the guard at write time:
`validate_no_lookahead_fields(...)` is called on every JSONL
row before the line is appended.

#### Boundary

  - **NOT** complete strategy blind replay; **NOT** PnL
    backtest; **NOT** trading module; **NOT** AI Learning;
    **NOT** automatic parameter optimisation; **NOT**
    reinforcement learning; **NOT** the small-money
    live-trading pre-validation gate; **NOT** Phase 12.
  - The builder's outputs are **post-hoc audit reference
    only**; they MUST NEVER drive live radar score, candidate
    promotion, the Risk Engine, the Execution FSM,
    `symbol_limit`, candidate-pool capacity, anomaly
    thresholds, Regime weights, or any other runtime knob.

#### Closeout note

  - This PR ships the **builder**. Real 60D historical data
    generation against Binance public futures endpoints is
    **required after merge** to flip Phase 11C.1C-C-B-B-B-D-A
    to `ACCEPTED` via a separate docs-only closeout PR (the
    operator must capture the live `HISTORICAL_MOVER_COVERAGE_*`
    event counts, the daily-report excerpt, the Phase 8.5
    export bundle manifest count, and the audit's
    `backfill_status` over the real 60D window).

### Phase 11C.1C-C-B-B-B-D-A implementation - Historical 60D Mover Coverage Backfill Audit v0 (PR #64)

**Type:** Implementation PR (paper / report / evidence only).
**Runtime effect:** new audit module wired into the Phase 11C
public-market paper runner; the runner generates a
`HistoricalMoverCoverageBackfillReport` on shutdown and embeds
the new section in the daily Markdown report. No live trading
behaviour changes.
**Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-D-A from
`NEXT_ALLOWED / NOT_STARTED` to **`IN_REVIEW`** (PR #64). A
separate docs-only closeout PR is required after the operator
captures real 60D backfill evidence.
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False` remain unchanged.
**Trade authority granted:** **none.**

> **Status: IMPLEMENTATION PR.** This PR ships the v0 engine /
> payload / report / lookahead-guard implementation for Phase
> 11C.1C-C-B-B-B-D-A (*Historical 60D Mover Coverage Backfill
> Audit v0 / 历史 60 天异动币覆盖回填审计 v0*). The audit is
> paper / report / evidence only. **No** real trade is
> authorised; **no** position size, leverage, stop-loss, target
> price, Risk Engine threshold, Execution FSM rule,
> `symbol_limit`, candidate-pool capacity, anomaly threshold,
> Regime weight, or any other runtime knob is modified by this
> PR or by any audit result it produces. The Risk Engine
> remains the single trade-decision gate. Phase 12 remains
> **FORBIDDEN**.

#### Implementation summary

  - New module `app/adaptive/historical_mover_coverage_backfill.py`
    with the data models, deterministic pure functions, the
    Lookahead Guard helpers, the Historical Market Store loader,
    and the runtime:
      - `HistoricalMoverCoverageBackfillStatus` (`READY` /
        `PARTIAL` / `DEGRADED` / `INSUFFICIENT_HISTORY` /
        `FAILED_REFERENCE_DATA`).
      - `HistoricalMoverCoverageStatus` (`CAPTURED` /
        `PARTIALLY_CAPTURED` / `MISSED` / `EXCLUDED`).
      - `HistoricalMoverMissReason` taxonomy (15 reasons,
        matching the brief verbatim).
      - `HistoricalMoverReference`,
        `HistoricalMoverReferenceSet`,
        `HistoricalMoverCapturePath`,
        `HistoricalMoverCoverageRecord`,
        `HistoricalMoverCoverageBackfillInput`,
        `HistoricalMoverCoverageBackfillReport`.
      - `build_historical_60d_mover_reference_set(...)` (pure
        function).
      - `audit_historical_mover_capture_path(...)` (pure
        function).
      - `classify_historical_miss_reason(...)` (pure function).
      - `build_historical_mover_coverage_backfill_report(...)`
        (pure function).
      - `export_historical_mover_coverage_payload(...)` /
        `load_historical_mover_coverage_payload(...)`.
      - `validate_no_lookahead_fields(...)` /
        `assert_capture_event_is_past_or_equal_reference_window(...)`
        Lookahead Guard helpers.
      - `load_historical_market_store(root)` reads
        `<root>/top_movers/*.jsonl` and
        `<root>/exchange_info/*.jsonl`.
      - `HistoricalMoverCoverageBackfillRuntime` orchestrates
        per-symbol event walks and emits the new event types.
  - Two new typed events in `app/core/events.py`:
      - `EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`
      - `EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`
  - Daily report (`app/paper_run/daily_report.py`) renders a
    new "Phase 11C.1C-C-B-B-B-D-A Historical 60D Mover
    Coverage Backfill Audit v0" section with status, recall
    rates, latency p50 / p90, miss-reason summary, coverage
    warnings, lookahead-guard warnings, and per-mover sample
    records (capped at 20 rows).
  - Public-market paper runner
    (`scripts/run_public_market_paper.py`) wires the runtime,
    flushes once on shutdown, and threads the metrics into
    the daily report. Two new CLI flags:
    `--historical-mover-store-dir`,
    `--historical-reference-window-days`.
  - Phase 11B no-network audit
    (`tests/unit/test_phase11b_no_network.py`) extended to
    allow the two new event-type symbol references.
  - New unit-test module
    `tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_coverage_backfill.py`
    covering all 18 brief-mandated cases plus a Historical
    Market Store loader contract and a top-level status
    propagation case.

#### Lookahead Guard (verbatim)

  - `completed_tail_label` MUST NOT drive reference selection.
  - future return / final max gain MUST NOT pollute the
    simulated live-radar score.
  - replay label MUST NOT contaminate `first_seen_time`.
  - reflection / report text / LLM narrative MUST NEVER serve
    as a capture event source.
  - `first_seen_time_utc` MUST come from the timestamp of an
    event that already existed at audit time.
  - the top-mover reference set MUST only be used for post-hoc
    audit; it cannot rewrite past decisions.

#### Boundary

  - **NOT** complete strategy blind replay; **NOT** PnL
    backtest; **NOT** trading module; **NOT** AI Learning;
    **NOT** automatic parameter optimisation; **NOT**
    reinforcement learning; **NOT** the small-money
    live-trading pre-validation gate; **NOT** Phase 12.
  - The Historical Market Store serves the right-tail coverage
    audit only - it does NOT serve auto-trading, and audit
    results MUST NEVER trigger real trades, modify positions,
    leverage, stops, targets, the Risk Engine, the Execution
    FSM, `symbol_limit`, candidate-pool capacity, anomaly
    thresholds, Regime weights, or any other runtime knob.

#### Closeout note

  - This PR ships the v0 engine / payload / report / Lookahead
    Guard implementation. Real 60D historical data is not
    bundled and is **not** required for this PR's acceptance.
    A subsequent operator-driven evidence-collection run plus
    a docs-only closeout PR will flip the slice to
    `ACCEPTED`.

### Phase 11C.1C-C-B-B-B-D-A kickoff - Historical 60D Mover Coverage Backfill Audit v0 docs-only kickoff (PR #63)

**Type:** Docs-only kickoff / scope alignment.
**Runtime effect:** **none.**
**Phase ledger effect:** **defines** Phase
11C.1C-C-B-B-B-D-A in place — name, scope, boundary,
allowed outputs, forbidden list, eight audit questions,
60D top-mover reference set fields, per-captured-mover
audit row fields, miss-reason taxonomy, allowed input
sources, audit objects, audit cadence (B1 / B2 with
B3+ reserved; operator-driven, **not** auto-scheduled),
interpretation principles, safety boundary, and
acceptance-gate placeholder. Phase 11C.1C-C-B-B-B-D-A
remains `NEXT_ALLOWED / NOT_STARTED` after this PR (this
PR scopes the slice; it does not flip its state). No
phase's acceptance state is flipped.
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **Status: DOCS-ONLY KICKOFF / SCOPE ALIGNMENT.** This
> PR defines Phase 11C.1C-C-B-B-B-D-A (*Historical 60D
> Mover Coverage Backfill Audit v0 / 历史 60 天异动币覆盖
> 回填审计 v0*) as the **next allowed child slice** under
> the Phase 11C.1C-C-B-B-B parent (on top of the
> `ACCEPTED` Phase 11C.1C-C-B-B-B-D track). The parent
> phase is **not** renamed: Phase 11C.1C-C-B-B-B remains
> *Strategy Validation Lab (deeper) & richer Cluster
> Exposure Control follow-up*. **No runtime code is
> shipped by this PR.** **No phase's acceptance state is
> flipped.** Phase 11C.1C-C-B-B-B-D-A remains
> `NEXT_ALLOWED / NOT_STARTED`; this PR scopes the slice
> in place.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> new strategy. **NOT** a trading module. **NOT** a new
> runtime module. **NOT** a new event type. **NOT** the
> complete Strategy Validation Lab follow-up. **NOT**
> Phase 11C.1C-C-B-B-B-D-A *implementation* (out of
> scope; will be a separate PR cycle if needed). **NOT**
> Phase 11C.1C-C-B-B-B-D-A *closeout* (out of scope; the
> closeout will be a separate docs-only PR after the
> operator captures B1 / B2 backfill audit evidence).
> **NOT** a Historical 30D+ / 60D *complete strategy*
> blind replay / walk-forward validation gate (that gate
> is reserved until small-money live trading prep and is
> **not** in scope here). **NOT** Phase 12.

#### Why next slice is Phase 11C.1C-C-B-B-B-D-A (Historical 60D Mover Coverage Backfill Audit v0)

  - PR #61 proves the Mover Capture Recall & Missed-Tail
    Coverage Audit v0 layer can run in real paper mode
    and export `MOVER_CAPTURE_*` evidence.
  - However, a 10 min live audit window may be too short
    and market-dependent. On a calm day the gainer board
    may show no clear tails; on a noisy day a single coin
    (e.g. SAGAUSDT) may dominate the signal but prove
    nothing about general coverage.
  - Waiting for several "good" market days to accumulate
    enough 10 min windows wastes operator time and risks
    selection bias on the operator's side.
  - Therefore the next slice should evaluate
    discovery-layer coverage **over the past 60 days** as
    a structured **historical backfill audit**, not as
    another series of 10 min live windows.
  - This is **not** complete strategy blind testing.
  - This is **not** Phase 12 pre-live validation.
  - This is **only** a discovery-layer historical
    coverage backfill audit.

#### Phase 11C.1C-C-B-B-B-D-A scope (docs-only kickoff summary)

  - Defines Phase 11C.1C-C-B-B-B-D-A as the *Historical
    60D Mover Coverage Backfill Audit v0 / 历史 60 天异动
    币覆盖回填审计 v0* — the next allowed child slice
    under Phase 11C.1C-C-B-B-B (on top of the `ACCEPTED`
    11C.1C-C-B-B-B-D track).
  - Audit answers eight questions, **and only these
    eight** (see "Phase 11C.1C-C-B-B-B-D-A boundary"
    below).
  - Defines the 60D top-mover reference set fields per
    window / per symbol: `reference_window_start_utc`,
    `reference_window_end_utc`, `top_mover_symbol`,
    `top_mover_rank`, `max_window_gain`, `max_24h_gain`,
    `reference_timestamp_utc`, `eligible_usdt_perpetual`
    (true / false). Excluded: non-futures listings,
    non-USDT-margined, non-perpetual,
    not-in-`exchangeInfo`, delisted / inactive symbols.
  - Defines the per-captured-mover audit row:
    `top_mover_symbol`, `mover_window_start_utc`,
    `mover_window_end_utc`, `top_mover_rank`,
    `max_window_gain`, `max_24h_gain`,
    `eligible_usdt_perpetual`, `system_captured`,
    `first_seen_time_utc`, `first_seen_event_type`,
    `first_seen_latency_seconds` where a mover reference
    timestamp exists, `capture_path_depth`,
    `reached_anomaly`, `reached_label_queue`,
    `reached_tail_label`,
    `reached_strategy_validation_sample`,
    `risk_rejected`, `status` (`captured` /
    `partially_captured` / `missed` / `excluded`),
    `miss_reason`.
  - Defines the fixed `miss_reason` taxonomy:
    `not_in_futures_universe`,
    `symbol_not_in_exchange_info`, `not_usdt_perpetual`,
    `missing_historical_reference_data`,
    `missing_event_history`, `below_liquidity_threshold`,
    `symbol_limit_excluded`, `candidate_pool_evicted`,
    `insufficient_ws_data`, `stale_data`,
    `data_unreliable`, `no_anomaly_threshold_cross`,
    `risk_rejected`, `no_completed_tail_label_yet`,
    `unknown` (and `unknown` is a `review` signal —
    **not** a `relax` signal).
  - Lists the allowed outputs (descriptive templates
    only): `historical_60d_mover_reference_set`,
    `historical_60d_capture_path_audit`,
    `historical_60d_miss_reason_summary`,
    `historical_60d_first_seen_summary`,
    `historical_60d_capture_recall_summary`,
    `historical_60d_coverage_warning`,
    `historical_60d_export_replay_evidence_template`.
  - Defines the audit cadence (operator-driven; **not**
    auto-scheduled): B1 (first end-to-end 60D historical
    backfill audit pass), B2 (second pass against an
    independent operator-VPS replay window), B3+
    reserved for later child slices and out of scope
    here.
  - Lists the allowed input sources (read-only; reuse
    existing surfaces): Binance public 24 h ticker /
    public klines / public market data,
    `EventRepository` / events.db, daily report, Phase
    8.5 export bundle / Phase 10A replay bundle over the
    60D window, `StrategyValidationDataset`,
    `PaperAlphaGateReport`, `RegimeClusterEvidencePack`,
    `MoverCaptureRecallAuditReport`, `SymbolUniverse` /
    `exchangeInfo`-as-truth catalogue, candidate pool
    logs / capacity-eviction evidence.
  - Records the eight interpretation principles
    verbatim (see "Phase 11C.1C-C-B-B-B-D-A
    interpretation principles" below).

#### Phase 11C.1C-C-B-B-B-D-A boundary (must be read verbatim)

D-A is **allowed** to answer:

  1. over the past 60 days, **did AMA-RT discover the
     eligible USDT perpetual movers**?
  2. if discovered, **when was the first detection**
     (`first_seen_time_utc`)?
  3. **what was the first detection event**
     (`first_seen_event_type`)?
  4. **how deep did the capture path go**
     (`capture_path_depth`, `reached_anomaly`,
     `reached_label_queue`, `reached_tail_label`,
     `reached_strategy_validation_sample`)?
  5. if not discovered, **why** (`miss_reason` from the
     fixed taxonomy)?
  6. **is each missed mover a universe-coverage issue
     or a discovery-layer warning**?
  7. **which captured movers were rejected by the Risk
     Engine** (`risk_rejected = true`; conservative
     paper outcome, **not** discovery failure)?
  8. **which captured movers only made it partway**
     (`status = partially_captured`)?

D-A must **NOT** answer:

  - whether the strategy is profitable;
  - whether live trading is allowed;
  - whether leverage / position / stops should change;
  - whether `symbol_limit` should auto-expand;
  - whether anomaly thresholds should auto-change;
  - whether candidate pool capacity should auto-change;
  - whether Regime weights should auto-change;
  - whether Phase 12 can begin.

#### Phase 11C.1C-C-B-B-B-D-A interpretation principles (must be read verbatim)

  1. **Captured ≠ tradable.**
  2. **Captured early ≠ strategy profitable.**
  3. **Missed and not-in-futures-universe ≠ system
     failure** (out of scope by design).
  4. **Missed and in-eligible-universe IS a coverage
     warning** (for human review only).
  5. **`risk_rejected` ≠ discovery failure** (Risk
     Engine remains the single trade-decision gate).
  6. **`missed` and `unknown` are `review` signals**
     (no automatic rule relaxation, no automatic
     `symbol_limit` expansion, no automatic anomaly
     threshold change, no automatic candidate-pool
     capacity change, no automatic Regime weight
     change).
  7. **High `capture_recall_rate` does NOT authorise
     live trading.**
  8. **Low `capture_recall_rate` does NOT authorise
     parameter changes** (no "looking at the answer
     key" — no auto-tuning thresholds against the
     historical reference set).

#### Phase 11C.1C-C-B-B-B-D-A forbidden surface (must be read verbatim)

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise API keys.
  - It does **NOT** authorise private endpoints.
  - It does **NOT** authorise signed endpoints.
  - It does **NOT** authorise `listenKey` / private
    WebSocket.
  - It does **NOT** authorise account / order /
    position / leverage / margin endpoints.
  - It does **NOT** authorise DeepSeek trade decisions.
  - It does **NOT** authorise real Telegram outbound.
  - It does **NOT** authorise AI Learning.
  - It does **NOT** authorise automatic parameter
    optimisation.
  - It does **NOT** authorise reinforcement learning.
  - It does **NOT** authorise rule relaxation based on
    historical movers.
  - It does **NOT** authorise automatic `symbol_limit`
    expansion.
  - It does **NOT** authorise automatic anomaly
    threshold changes.
  - It does **NOT** authorise automatic candidate-pool
    capacity changes.
  - It does **NOT** authorise automatic Regime weight
    changes.
  - It does **NOT** authorise changing the Risk Engine
    or the Execution FSM.
  - It does **NOT** authorise auto-scheduling B1 / B2 /
    B3+ runs.
  - It does **NOT** authorise replacing the Mover
    Capture Recall & Missed-Tail Coverage Audit v0
    `DEGRADED` rule with a relaxed rule.
  - It does **NOT** authorise replacing the Regime &
    Cluster Evidence Pack v0 `INSUFFICIENT_SAMPLE` rule
    with a relaxed rule.
  - It does **NOT** authorise replacing the Paper Alpha
    Gate v0 `INCONCLUSIVE` rule with a relaxed rule.
  - It does **NOT** authorise replacing the Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0
    cadence with a relaxed cadence.
  - It does **NOT** authorise treating Phase
    11C.1C-C-B-B-B-D-A as a Historical 30D+ / 60D
    *complete strategy* blind replay / walk-forward
    validation.
  - It does **NOT** authorise implementing the Phase
    11C.1C-C-B-B-B-D-A backfill as a new runtime module
    (the slice is intentionally docs / evidence-template
    only end-to-end at kickoff).
  - It does **NOT** authorise adding new Python modules
    under `app/`.
  - It does **NOT** authorise adding new event types.
  - It does **NOT** authorise modifying `app/` /
    `scripts/` / `tests/` / `configs/` / `risk/` /
    `execution/` / `llm/` / `telegram/` / `exchange/`.
  - It does **NOT** authorise modifying configuration
    schemas / defaults / YAML.
  - It does **NOT** authorise adding or modifying tests.
  - It does **NOT** authorise running tests.
  - It does **NOT** authorise modifying strategy runtime
    code.
  - It does **NOT** authorise modifying runtime
    behaviour.
  - It does **NOT** authorise implementing new
    functionality.
  - It does **NOT** authorise flipping any phase's
    acceptance state.
  - It does **NOT** authorise renaming Phase
    11C.1C-C-B-B-B.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A
    *implementation* in this PR.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A
    *closeout* in this PR.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D-B /
    further child slices.
  - It does **NOT** authorise Phase 12.

#### Documentation changes

  - `docs/PROJECT_STATUS.md` (modified — docs-only):
    added a new active-phase block for Phase
    11C.1C-C-B-B-B-D-A `NEXT_ALLOWED / NOT_STARTED`
    above the previous active blocks; added a new
    timeline-table row for Phase 11C.1C-C-B-B-B-D-A
    (kickoff) referencing PR #63; marked the prior
    "placeholder; not yet kicked off" row as
    "placeholder; superseded by PR #63 kickoff above".
  - `docs/PHASE_GATE.md` (modified — docs-only): added
    a new D-A kickoff row at the top of the D-A entries
    in the Open / Reserved table referencing PR #63;
    marked the prior D-A row as "placeholder;
    superseded by PR #63 kickoff above"; refreshed the
    `## Open phase: Phase 11C.1C-C-B-B-B-D-A
    (NEXT_ALLOWED / NOT_STARTED)` section header note
    to reference the PR #63 scoping; replaced the
    "acceptance gate (placeholder)" text to reflect
    that this is now the kickoff PR; appended a new
    full `## Phase 11C.1C-C-B-B-B-D-A kickoff (PR #63)`
    section with kickoff scope, safety boundary, and
    confirmation checklist.
  - `docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md`
    (NEW — docs-only): the dedicated phase doc
    recording Phase 11C.1C-C-B-B-B-D-A's full scope,
    eight audit questions, 60D top-mover reference set
    fields, per-captured-mover audit row fields,
    miss-reason taxonomy (14 + `unknown`), allowed
    outputs, audit cadence, allowed input sources,
    audit objects, eight interpretation principles,
    full forbidden list, safety boundary, and
    acceptance-gate placeholder.
  - `docs/CHANGELOG.md` (this entry).
  - **NEW:** `docs/PR63_DESCRIPTION.md` — this PR's
    description.

#### Safety boundary (Phase 1 lock unchanged)

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
real account / order / position / leverage / margin endpoint = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

#### Confirmation checklist

  - [x] Docs-only PR; no runtime code modified.
  - [x] No `app/` / `scripts/` / `tests/` / `configs/`
    changes.
  - [x] No `execution/` / `risk/` / `llm/` / `telegram/`
    / `exchange/` changes.
  - [x] No strategy runtime code changes.
  - [x] No new Python files.
  - [x] No new event types.
  - [x] No new tests.
  - [x] No tests run.
  - [x] No runtime behaviour changed.
  - [x] No phase's acceptance state flipped — Phase
    11C.1C-C-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`;
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-D remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-D-A remains `NEXT_ALLOWED /
    NOT_STARTED` (scoped by this PR; not flipped).
  - [x] Phase 11C.1C-C-B-B-B parent is **not** renamed;
    it remains *Strategy Validation Lab (deeper) &
    richer Cluster Exposure Control follow-up*.
  - [x] Phase 11C.1C-C-B-B-B-D-A is recorded as the next
    allowed child slice on top of the
    Phase 11C.1C-C-B-B-B-D track = Historical 60D Mover
    Coverage Backfill Audit v0 / *历史 60 天异动币覆盖
    回填审计 v0*.
  - [x] D-A rationale recorded (10 min live window short
    / market-dependent; SAGAUSDT can be missed or
    `unknown`; quiet days waste operator time and risk
    selection bias; therefore D-A evaluates 60D
    discovery-layer coverage as a structured backfill
    audit; not complete strategy blind testing; not
    Phase 12 pre-live validation; only discovery-layer
    historical coverage backfill audit).
  - [x] D-A audit cadence recorded (B1 / B2 with B3+
    reserved; operator-driven; not auto-scheduled).
  - [x] D-A allowed input sources recorded (Binance
    public 24 h ticker / public klines / public market
    data, `EventRepository` / events.db, daily report,
    Phase 8.5 export bundle / Phase 10A replay bundle
    over the 60D window, `StrategyValidationDataset`,
    `PaperAlphaGateReport`, `RegimeClusterEvidencePack`,
    `MoverCaptureRecallAuditReport`, `SymbolUniverse` /
    `exchangeInfo`-as-truth catalogue, candidate pool
    logs / capacity-eviction evidence).
  - [x] D-A audit objects recorded (60D top gainers /
    top movers / high-momentum movers in eligible USDT
    perpetual universe, 60D detected anomalies, 60D
    pre-anomaly candidates, 60D label-tracked
    candidates, 60D validation samples, 60D risk-rejected
    captured movers, 60D excluded symbols).
  - [x] D-A 60D top-mover reference set fields recorded
    verbatim (`reference_window_start_utc`,
    `reference_window_end_utc`, `top_mover_symbol`,
    `top_mover_rank`, `max_window_gain`,
    `max_24h_gain`, `reference_timestamp_utc`,
    `eligible_usdt_perpetual`).
  - [x] D-A per-captured-mover audit row recorded
    verbatim (`top_mover_symbol`,
    `mover_window_start_utc`, `mover_window_end_utc`,
    `top_mover_rank`, `max_window_gain`,
    `max_24h_gain`, `eligible_usdt_perpetual`,
    `system_captured`, `first_seen_time_utc`,
    `first_seen_event_type`,
    `first_seen_latency_seconds`,
    `capture_path_depth`, `reached_anomaly`,
    `reached_label_queue`, `reached_tail_label`,
    `reached_strategy_validation_sample`,
    `risk_rejected`, `status`, `miss_reason`).
  - [x] D-A fixed `miss_reason` taxonomy recorded
    verbatim (`not_in_futures_universe`,
    `symbol_not_in_exchange_info`, `not_usdt_perpetual`,
    `missing_historical_reference_data`,
    `missing_event_history`,
    `below_liquidity_threshold`,
    `symbol_limit_excluded`, `candidate_pool_evicted`,
    `insufficient_ws_data`, `stale_data`,
    `data_unreliable`, `no_anomaly_threshold_cross`,
    `risk_rejected`, `no_completed_tail_label_yet`,
    `unknown`).
  - [x] D-A allowed outputs explicitly listed
    (`historical_60d_mover_reference_set`,
    `historical_60d_capture_path_audit`,
    `historical_60d_miss_reason_summary`,
    `historical_60d_first_seen_summary`,
    `historical_60d_capture_recall_summary`,
    `historical_60d_coverage_warning`,
    `historical_60d_export_replay_evidence_template`)
    and marked descriptive only.
  - [x] D-A interpretation principles recorded verbatim
    (captured ≠ tradable; captured early ≠ strategy
    profitable; missed and not-in-futures-universe ≠
    system failure; missed and in-eligible-universe IS a
    coverage warning; `risk_rejected` ≠ discovery
    failure; `missed` and `unknown` are `review`
    signals; high recall does NOT authorise live
    trading; low recall does NOT authorise parameter
    changes / "looking at the answer key").
  - [x] Slice-specific forbidden items recorded verbatim
    (no live trading; no API keys; no private endpoints;
    no signed endpoints; no `listenKey`; no private
    WebSocket; no DeepSeek trade decisions; no real
    Telegram outbound; no AI Learning; no automatic
    parameter optimisation; no reinforcement learning;
    no rule relaxation based on historical movers; no
    auto `symbol_limit` expansion; no auto anomaly
    threshold changes; no auto candidate-pool capacity
    changes; no auto Regime weight changes; no Risk
    Engine / Execution FSM changes; no auto-scheduling
    B1 / B2 / B3+; no replacing existing
    `DEGRADED` / `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE`
    rules with relaxed rules; no replacing Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0
    cadence with a relaxed cadence; no treating D-A as a
    Historical 30D+ / 60D *complete strategy* blind
    replay / walk-forward validation; no implementing
    the D-A backfill as a new runtime module; no adding
    new Python modules under `app/`; no adding new event
    types; no modifying `app/` / `scripts/` / `tests/` /
    `configs/`; no modifying configuration schemas /
    defaults / YAML; no adding or modifying tests; no
    running tests; no modifying strategy runtime code;
    no modifying runtime behaviour; no implementing new
    functionality; no flipping any phase's acceptance
    state; no renaming Phase 11C.1C-C-B-B-B; no Phase
    11C.1C-C-B-B-B-D-A *implementation* in this PR; no
    Phase 11C.1C-C-B-B-B-D-A *closeout* in this PR; no
    Phase 11C.1C-C-B-B-B-D-B / further child slices; no
    Phase 12).
  - [x] Safety boundary held end-to-end (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - [x] Phase 12 remains `FORBIDDEN`.

### Phase 11C.1C-C-B-B-B-D accepted - Mover Capture Recall & Missed-Tail Coverage Audit v0 docs-only closeout (PR #62)

**Type:** Docs-only closeout / acceptance flip.
**Runtime effect:** **none.**
**Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-D from
`IN_REVIEW` (implementation PR #61 merged into `main`) to
`ACCEPTED`; introduces Phase 11C.1C-C-B-B-B-D-A as
`NEXT_ALLOWED / NOT_STARTED` (*Historical 60D Mover
Coverage Backfill Audit v0 / 历史 60 天异动币覆盖回填审
计 v0*).
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **Status: ACCEPTED (closed 2026-05-25; PR #60 docs-only
> kickoff merged into `main`; PR #61 implementation
> merged into `main`; this docs-only closeout PR #62
> records the operator-VPS 10 min WS paper smoke evidence
> + daily report Mover Capture section + `MOVER_CAPTURE_*`
> event counts + Phase 8.5 export bundle + audit result
> `mover_capture_audit_status=DEGRADED` and flips the
> slice to `ACCEPTED`).** Mover Capture Recall &
> Missed-Tail Coverage Audit v0 / *异动币捕捉召回与漏捕
> 右尾覆盖审计 v0* — fourth child slice under the Phase
> 11C.1C-C-B-B-B parent — paper / report / evidence only.
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** rule relaxation based on SAGAUSDT or
> any small number of movers. **NOT** a Risk Engine
> change. **NOT** an Execution FSM change. **NOT**
> automatic `symbol_limit` expansion. **NOT** automatic
> anomaly threshold changes. **NOT** automatic
> candidate-pool capacity changes. **NOT** automatic
> Regime weight changes. **NOT** the complete Strategy
> Validation Lab follow-up. **NOT** Historical 30D+ Blind
> Replay / Walk-forward Validation (that gate is reserved
> for a Phase 12 candidate review and is explicitly out
> of scope here; it belongs after the major paper modules
> and the paper validation chain are complete, before
> small-money live trading). **NOT** Phase 12.

#### PR #61 implementation summary (recorded for closeout audit trail)

  - PR #61 implemented Phase 11C.1C-C-B-B-B-D Mover
    Capture Recall & Missed-Tail Coverage Audit v0.
  - It implemented paper-only / report-only /
    evidence-only audit logic.
  - It does **not** implement a trading strategy.
  - It does **not** authorise live trading.
  - It does **not** authorise AI Learning.
  - It does **not** authorise automatic parameter
    optimisation.
  - It does **not** authorise Phase 12.
  - Implementation included:
      - top mover reference set,
      - capture path audit,
      - miss reason classification,
      - daily report section,
      - export / replay readable audit events,
      - `EventRepository` integration,
      - deterministic unit tests,
      - safety boundary preservation.

#### Operator-VPS 10 min WS paper smoke evidence

```
duration_seconds                = 600.0
dry_run                         = false
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
risk_approved                   = 0
HTTP 429                        = 0
HTTP 418                        = 0
ws_reconnect_count              = 0
ws_stale_count                  = 0
live_trading_enabled            = False
exchange_live_order_enabled     = False
llm_enabled                     = False
right_tail_enabled              = False
```

Mover Capture event counts (events.db, authoritative):

```
MOVER_CAPTURE_RECALL_AUDIT_GENERATED = 1
MOVER_CAPTURE_PATH_AUDITED           = 20
```

Daily report contains the new section verbatim:

```
## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0
```

#### Audit-result interpretation (must be read verbatim)

Audit result for the 10 min smoke window:

```
mover_capture_audit_status      = DEGRADED
top_mover_count                 = 20
captured_top_mover_count        = 4
missed_top_mover_count          = 16
capture_recall_rate             = 0.2000
data_unreliable_count           = 4
risk_rejected_mover_count       = 4
```

  - `DEGRADED` is an **accepted audit output**, **not** a
    runtime failure.
  - `DEGRADED` means the audit layer **successfully
    surfaced** coverage weakness / uncertainty.
  - Captured-but-risk-rejected does **not** mean
    discovery failure (the Risk Engine remains the single
    trade-decision gate).
  - Missed-with-`unknown` reason is a `review` signal,
    **not** permission to loosen rules.
  - Low capture recall does **NOT** authorise automatic
    `symbol_limit` expansion.
  - Low capture recall does **NOT** authorise automatic
    anomaly threshold changes.
  - Low capture recall does **NOT** authorise automatic
    candidate-pool capacity changes.
  - Low capture recall does **NOT** authorise automatic
    Regime weight changes.
  - Low capture recall does **NOT** authorise Risk Engine
    changes.
  - **High capture recall would also NOT authorise live
    trading.**

#### Phase 8.5 export evidence

```
export_test_data                = OK
export zip                      = data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip
manifest_event_count            = 63968
redaction_applied               = True
events.jsonl exists             = True
export contains MOVER_CAPTURE_* events
MOVER_CAPTURE_RECALL_AUDIT_GENERATED = 1
MOVER_CAPTURE_PATH_AUDITED           = 20
EXPORT_MOVER_CAPTURE_RECALL_CHECK = PASS
```

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

#### Why next slice is Phase 11C.1C-C-B-B-B-D-A (Historical 60D Mover Coverage Backfill Audit v0)

  - PR #61 proves the Mover Capture Recall & Missed-Tail
    Coverage Audit v0 layer can run in real paper mode
    and export `MOVER_CAPTURE_*` evidence.
  - However, a 10 min live window may be too short and
    market-dependent.
  - Example: a real mover like SAGAUSDT can be missed or
    classified as `unknown` in a short audit window.
  - Waiting several quiet days may waste time if the
    market is calm.
  - Therefore the next slice should evaluate
    discovery-layer coverage over the past 60 days.
  - This is **not** complete strategy blind testing.
  - This is **not** Phase 12 pre-live validation.
  - This is **only** a discovery-layer coverage backfill
    audit.

D-A must require:

  - a 60D top mover reference set;
  - an eligible USDT-perpetual universe filter;
  - `first_seen_time_utc` for every captured mover;
  - `first_seen_event_type`;
  - `first_seen_latency_seconds` where a mover reference
    timestamp exists;
  - `capture_path_depth`;
  - per-mover status (`captured` / `partially_captured` /
    `missed` / `excluded`);
  - miss-reason classification;
  - report / export / replay evidence.

#### Phase 11C.1C-C-B-B-B-D-A boundary (must be read verbatim)

D-A is **allowed** to answer:

  - over the past 60 days, **which eligible movers did
    AMA-RT detect**;
  - **when did AMA-RT first detect them**;
  - **which capture-path layer did they reach**;
  - **which movers were missed**;
  - **why were they missed**;
  - **which misses are universe-coverage issues** vs.
    discovery-layer warnings.

D-A must **NOT** answer:

  - whether the strategy is profitable;
  - whether live trading is allowed;
  - whether leverage / position / stops should change;
  - whether `symbol_limit` should auto-expand;
  - whether anomaly thresholds should auto-change;
  - whether candidate pool capacity should auto-change;
  - whether Phase 12 can begin.

#### Closeout interpretation (must be read verbatim)

  - **Phase 11C.1C-C-B-B-B-D acceptance is acceptance of
    the Mover Capture Recall & Missed-Tail Coverage Audit
    v0 layer.**
  - It does **NOT** authorise live trading.
  - It does **NOT** authorise API keys.
  - It does **NOT** authorise private endpoints.
  - It does **NOT** authorise DeepSeek trade decisions.
  - It does **NOT** authorise real Telegram outbound.
  - It does **NOT** authorise Phase 12.
  - It does **NOT** authorise automatic parameter
    optimisation.
  - It does **NOT** authorise AI Learning.
  - It does **NOT** authorise rule relaxation based on
    SAGAUSDT or any small number of movers.
  - It does **NOT** authorise changing the Risk Engine or
    the Execution FSM.
  - It does **NOT** authorise automatic `symbol_limit`
    expansion.
  - It does **NOT** authorise automatic anomaly threshold
    changes.
  - It does **NOT** authorise automatic candidate-pool
    capacity changes.
  - It does **NOT** authorise automatic Regime weight
    changes.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A
    kickoff bypassing the standard gate.

#### Documentation changes

  - `docs/PROJECT_STATUS.md` (modified — docs-only):
    flipped Phase 11C.1C-C-B-B-B-D from `IN_REVIEW` to
    `ACCEPTED`; added Phase 11C.1C-C-B-B-B-D-A as
    `NEXT_ALLOWED / NOT_STARTED`; appended the Mover
    Capture closeout summary to the active-phase block;
    appended slice-specific `does NOT authorise` block;
    added new closeout / next-slice rows in the per-phase
    ledger; marked the prior IN_REVIEW row as SUPERSEDED.
  - `docs/PHASE_GATE.md` (modified — docs-only): added a
    new closed-phases row for Phase 11C.1C-C-B-B-B-D
    (ACCEPTED, 2026-05-25); replaced the two B-B-B-D
    NEXT_ALLOWED / IN_REVIEW rows in the Open / Reserved
    table with a single `ACCEPTED — see Closed phases
    table above` row + a new Phase 11C.1C-C-B-B-B-D-A
    NEXT_ALLOWED row; renamed the
    `## Open phase: Phase 11C.1C-C-B-B-B-D` detail section
    to `## Closed phase: Phase 11C.1C-C-B-B-B-D
    (ACCEPTED)` and updated the status note; added a new
    `## Phase 11C.1C-C-B-B-B-D acceptance evidence
    (operator-VPS 10 min WS paper smoke PASSED)` section
    with the operator-VPS transcript, daily-report
    excerpt, MOVER_CAPTURE_* event counts, Phase 8.5
    export evidence, safety-boundary block, and closeout
    interpretation; added a new
    `## Open phase: Phase 11C.1C-C-B-B-B-D-A
    (NEXT_ALLOWED / NOT_STARTED)` section with rationale,
    allowed answers, forbidden answers, required fields,
    inherited forbidden items, and acceptance-gate
    placeholder; updated the Phase 12 row to reference
    PR #62.
  - `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`
    (modified — docs-only): appended a new "Closeout (PR
    #62 — ACCEPTED)" section recording the operator-VPS
    10 min WS paper smoke transcript, the daily-report
    excerpt, the MOVER_CAPTURE_* event counts, the Phase
    8.5 export evidence, the audit-result
    interpretation, the safety-boundary table, the
    forbidden-surface list, and the rationale for opening
    Phase 11C.1C-C-B-B-B-D-A.
  - `docs/CHANGELOG.md` (this entry).
  - **NEW:** `docs/PR62_DESCRIPTION.md` — this PR's
    description.

#### Safety boundary (Phase 1 lock unchanged)

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
real account / order / position / leverage / margin endpoint = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

#### Confirmation checklist

  - [x] Docs-only PR; no runtime code modified.
  - [x] No `app/` / `scripts/` / `tests/` / `configs/`
    changes.
  - [x] No `execution/` / `risk/` / `llm/` / `telegram/`
    / `exchange/` changes.
  - [x] No strategy runtime code changes.
  - [x] No new Python files.
  - [x] No new event types.
  - [x] No new tests.
  - [x] No tests run.
  - [x] No runtime behaviour changed.
  - [x] Phase 11C.1C-C-B-B-B-D = `ACCEPTED`.
  - [x] Phase 11C.1C-C-B-B-B-D-A = `NEXT_ALLOWED /
    NOT_STARTED` (defined as *Historical 60D Mover
    Coverage Backfill Audit v0 / 历史 60 天异动币覆盖回
    填审计 v0*).
  - [x] Phase 12 = `FORBIDDEN`.
  - [x] No live trading.
  - [x] No API key.
  - [x] No private endpoint.
  - [x] No DeepSeek trade decision.
  - [x] No real Telegram outbound.
  - [x] PR #61 implementation summary recorded verbatim.
  - [x] Operator-VPS 10 min WS paper smoke evidence
    recorded verbatim.
  - [x] Daily report Mover Capture section verified.
  - [x] `MOVER_CAPTURE_*` event counts verified
    (`MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`,
    `MOVER_CAPTURE_PATH_AUDITED=20`).
  - [x] Audit result `mover_capture_audit_status=DEGRADED`
    accepted as a valid coverage-audit output (not a
    runtime failure); interpretation rules recorded
    verbatim.
  - [x] Phase 8.5 export bundle verified
    (`data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip`,
    `manifest_event_count=63968`,
    `EXPORT_MOVER_CAPTURE_RECALL_CHECK=PASS`).
  - [x] Phase 11C.1C-C-B-B-B-D-A rationale recorded
    (10 min window short / market-dependent; SAGAUSDT
    example; quiet days waste time; therefore D-A
    evaluates 60D discovery-layer coverage; not complete
    strategy blind testing; not Phase 12 pre-live
    validation; only discovery-layer coverage backfill
    audit).
  - [x] Phase 11C.1C-C-B-B-B-D-A boundary recorded
    (allowed answers, forbidden answers, required
    fields).
  - [x] Slice-specific forbidden items recorded verbatim
    (no live trading; no API keys; no private endpoints;
    no DeepSeek trade decisions; no real Telegram
    outbound; no Phase 12; no AI Learning; no automatic
    parameter optimisation; no rule relaxation based on
    SAGAUSDT / single-coin cases; no Risk Engine /
    Execution FSM changes; no automatic `symbol_limit`
    expansion; no automatic anomaly threshold changes;
    no automatic candidate-pool capacity changes; no
    automatic Regime weight changes).
  - [x] Safety boundary held end-to-end (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - [x] Phase 12 remains `FORBIDDEN`.

### Phase 11C.1C-C-B-B-B-D implementation - Mover Capture Recall & Missed-Tail Coverage Audit v0 (PR #61)

**Type:** Implementation. Paper / report / evidence
only.
**Runtime effect:** new `app/adaptive/mover_capture_recall_audit.py`
module + new
:class:`MoverCaptureRecallAuditRuntime` orchestrator;
runner builds + flushes the audit on shutdown; daily
report renders a new section with every brief-mandated
field; two new typed events
`MOVER_CAPTURE_RECALL_AUDIT_GENERATED` /
`MOVER_CAPTURE_PATH_AUDITED` added to `app/core/events.py`.
**Phase ledger effect:** Phase 11C.1C-C-B-B-B-D moves to
`IN_REVIEW` (implementation PR #61). The slice will move
to `ACCEPTED` after a separate docs-only **closeout** PR
records the operator-VPS paper WS evidence.
**Safety flag effect:** **none.** `mode=paper`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key,
no Binance API secret, no signed endpoint, no
account / order / position / leverage / margin endpoint,
no private WebSocket, no `listenKey`, no DeepSeek trade
decision, no real Telegram outbound. Phase 12 remains
**FORBIDDEN**.
**Trade authority granted:** **none.** Audit results
NEVER trigger orders, NEVER modify position size /
leverage / stop-loss / target price, NEVER modify the
Risk Engine / Execution FSM / `symbol_limit` /
candidate-pool capacity / anomaly thresholds / Regime
weights, NEVER call private API, NEVER touch Telegram
outbound / DeepSeek / live trading.

> **Status: PAPER / REPORT / EVIDENCE ONLY.** This PR
> implements the deterministic, paper-only Mover
> Capture Recall & Missed-Tail Coverage Audit v0 layer
> defined in place by the docs-only kickoff PR #60
> (Phase 11C.1C-C-B-B-B-D). The audit institutionalises
> "operator looks at gainer board vs. did the system
> see it" as a structured coverage protocol, replacing
> ad-hoc human screenshots with deterministic per-mover
> evidence + descriptive ``audit_status`` /
> ``miss_reasons`` taxonomies. **NOT** a new strategy,
> **NOT** a trading module, **NOT** AI Learning, **NOT**
> automatic parameter optimisation, **NOT**
> reinforcement learning, **NOT** a Historical 30D+
> Blind Replay / Walk-forward Validation gate (that
> gate is a Phase 12 candidate pre-gate and is
> explicitly out of scope here), **NOT** the complete
> Strategy Validation Lab follow-up, **NOT** Phase 12.

#### What changed

  - **`app/core/events.py`** - added two new typed
    events: `MOVER_CAPTURE_RECALL_AUDIT_GENERATED` (one
    per audit window) and `MOVER_CAPTURE_PATH_AUDITED`
    (one per audited top mover). Both are paper /
    report / evidence only and **MUST NEVER** be
    consumed by the Risk Engine or the Execution FSM as
    a trade trigger.
  - **`app/adaptive/mover_capture_recall_audit.py`** -
    new module shipping the data models
    (`TopMoverReference`, `CapturePathEvidence`,
    `MoverCaptureAuditRecord`,
    `MoverCaptureRecallAuditInput`,
    `MoverCaptureRecallAuditReport`), the descriptive
    status / miss-reason taxonomies
    (`MoverCaptureRecallAuditStatus` =
    ``OK`` / ``INSUFFICIENT_DATA`` / ``DEGRADED``;
    `CapturePathStatus` = ``CAPTURED`` /
    ``PARTIALLY_CAPTURED`` / ``MISSED`` / ``EXCLUDED``
    / ``INSUFFICIENT_DATA``; `MissReason` =
    13 brief-verbatim reasons), the deterministic pure
    functions (`build_top_mover_reference_set`,
    `audit_mover_capture_path`, `classify_miss_reason`,
    `build_mover_capture_recall_audit_report`,
    `export_mover_capture_recall_audit_payload`,
    `load_mover_capture_recall_audit_payload`), and the
    thin `MoverCaptureRecallAuditRuntime` orchestrator.
  - **`scripts/run_public_market_paper.py`** - the
    runner now builds a
    :class:`MoverCaptureRecallAuditInput` from the
    public radar snapshot + `EventRepository`
    capture-path stages + `SymbolUniverse` exchangeInfo
    bootstrap, calls
    `MoverCaptureRecallAuditRuntime.flush(...)` on
    shutdown, and threads the metrics into the daily
    report via the new `mover_capture_audit_metrics`
    kwarg. Empty input degrades safely to
    ``INSUFFICIENT_DATA``.
  - **`app/paper_run/daily_report.py`** - new
    `mover_capture_audit_metrics` kwarg on `build()` /
    `_aggregate()`. New snapshot fields:
    `mover_capture_recall_audit_generated_count`,
    `mover_capture_path_audited_count`,
    `mover_capture_audit_status`, `top_mover_count`,
    `captured_top_mover_count`,
    `partially_captured_top_mover_count`,
    `missed_top_mover_count`, `excluded_top_mover_count`,
    `insufficient_data_top_mover_count`,
    `capture_recall_rate`, `anomaly_detected_rate`,
    `label_tracking_rate`, `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`,
    `risk_rejected_mover_count`,
    `not_in_universe_count`, `capacity_evicted_count`,
    `data_unreliable_count`,
    `median_first_seen_latency_seconds`,
    `mover_capture_records`, `miss_reason_summary`,
    `coverage_warnings`,
    `mover_capture_audit_insufficient_reasons`,
    `mover_capture_audit_warnings`,
    `mover_capture_audit_report`. New Markdown section
    `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall &
    Missed-Tail Coverage Audit v0` rendered with every
    field + per-mover record table.
  - **`tests/unit/test_phase11c_1c_c_b_b_b_d_mover_capture_recall_audit.py`**
    - 21 new deterministic test cases covering the
    top-mover reference set contract, full / partial /
    missed / excluded capture audit, every miss-reason
    classification, top-level metrics, payload
    round-trip, EventRepository emit, replay, daily-
    report integration, no execution side effects,
    safety-flag invariants, and a Phase 12 surface
    forbidden-list check.
  - **`tests/unit/test_phase11b_no_network.py`** -
    extended the "Phase 11B references unexpected
    EventType values" allowlist to include
    `MOVER_CAPTURE_RECALL_AUDIT_GENERATED` /
    `MOVER_CAPTURE_PATH_AUDITED`. No other test or
    behaviour changed.
  - **`docs/PROJECT_STATUS.md`** - active-phase block
    extended with the Phase 11C.1C-C-B-B-B-D = IN_REVIEW
    line; timeline table extended with the implementation
    PR row.
  - **`docs/PHASE_GATE.md`** - added the Phase
    11C.1C-C-B-B-B-D IN_REVIEW row directly under the
    NEXT_ALLOWED definition row.
  - **`docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`**
    - new "Implementation (PR #61 — IN_REVIEW)" section
    appended at the bottom of the kickoff doc with the
    full implementation summary + safety-boundary table
    + forbidden-surface list.
  - **`docs/PR61_DESCRIPTION.md`** - new PR description
    file.

#### Test summary

| Surface | Result |
| ------- | ------ |
| `tests/unit/test_phase11c_1c_c_b_b_b_d_mover_capture_recall_audit.py` | **21 / 21 PASS** |
| `tests/unit/ -k phase11c_` | **410 / 410 PASS** (post-PR #60 baseline + 21 new) |
| `tests/` (full surface) | **2384 / 2384 PASS** (no regression vs. post-PR #60 main baseline) |
| 30 s `--dry-run` smoke | Daily report contains the new Phase 11C.1C-C-B-B-B-D section; `mover_capture_audit_status=INSUFFICIENT_DATA` (expected for a 30 s dry-run window — the dry-run transport does not push real ticker rows; the audit correctly degrades); explicit `mover_capture_audit_insufficient_reasons` populated; no `ORDER_*` / `POSITION_*` / `STOP_*` / `RISK_APPROVED` events emitted by the audit. |
| Real-WS 10 min smoke | **NOT REQUIRED** for this PR. PR #61 is a deterministic coverage audit layer; non-empty top-mover coverage validation depends on a real WS push and the upstream Phase 11C.1C-C-A primary tracking window resolving. Real coverage validation is reserved for the Phase 11C.1C-C-B-B-B-D **closeout** PR. |

### Phase 11C.1C-C-B-B-B-D kickoff - Mover Capture Recall & Missed-Tail Coverage Audit v0 docs-only kickoff (PR #60)

**Type:** Docs-only kickoff / scope alignment.
**Runtime effect:** **none.**
**Phase ledger effect:** **defines** Phase
11C.1C-C-B-B-B-D in place — name, scope, boundary, allowed
outputs, forbidden list, key metrics, interpretation
principles, audit cadence, audit input sources, audit
objects, and acceptance-gate placeholder. Phase
11C.1C-C-B-B-B-D remains `NEXT_ALLOWED / NOT_STARTED`
after this PR (this PR scopes the slice; it does not flip
its state). No phase's acceptance state is flipped.
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **Status: DOCS-ONLY KICKOFF / SCOPE ALIGNMENT.** This
> PR defines Phase 11C.1C-C-B-B-B-D (*Mover Capture
> Recall & Missed-Tail Coverage Audit v0 / 异动币捕捉召回
> 与漏捕右尾覆盖审计 v0*) as the **fourth child slice**
> under the Phase 11C.1C-C-B-B-B parent. The parent phase
> is **not** renamed: Phase 11C.1C-C-B-B-B remains
> *Strategy Validation Lab (deeper) & richer Cluster
> Exposure Control follow-up*. **No runtime code is
> shipped by this PR.** **No phase's acceptance state is
> flipped.** Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED
> / NOT_STARTED`; this PR scopes the slice in place.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> new strategy. **NOT** a trading module. **NOT** a new
> runtime module. **NOT** the complete Strategy
> Validation Lab follow-up. **NOT** Phase
> 11C.1C-C-B-B-B-D *closeout* (the closeout will be a
> separate docs-only PR after the operator captures A1 /
> A2 audit evidence). **NOT** a Historical 30D+ Blind
> Replay / Walk-forward Validation gate (that gate is
> reserved for a Phase 12 candidate review and is
> explicitly out of scope here; it belongs after the
> major paper modules and the paper validation chain are
> complete, before small-money live trading). **NOT**
> Phase 12.
>
> The Mover Capture Recall & Missed-Tail Coverage Audit
> v0 is **paper-only / report-only / evidence-only** end
> to end. It does not add a new runtime module, a new
> event type, a new strategy, a new execution surface, a
> new optimiser, or a new AI authority. It defines the
> coverage audit cadence (A1 / A2 with A3+ reserved), the
> audit input sources, the audit objects, the per-mover
> evidence shape, the recall metrics, the missed-mover
> reason taxonomy, the eight interpretation rules, and
> the evidence-template shape that any future closeout PR
> must follow. The Risk Engine remains the single
> trade-decision gate.

#### Phase 11C.1C-C-B-B-B-D scope (docs-only kickoff summary)

  - Defines Phase 11C.1C-C-B-B-B-D as the *Mover Capture
    Recall & Missed-Tail Coverage Audit v0 / 异动币捕捉
    召回与漏捕右尾覆盖审计 v0* — the fourth child slice
    under Phase 11C.1C-C-B-B-B.
  - Audit answers seven questions, **and only these
    seven**: (1) did real movers get captured by the
    system, (2) at which discovery layer
    (`MARKET_SNAPSHOT` / `PRE_ANOMALY_DETECTED` /
    `ANOMALY_DETECTED` / `MARKET_REGIME_ASSESSED` /
    `CANDIDATE_STAGE_CLASSIFIED` / `OPPORTUNITY_SCORED` /
    `STRATEGY_MODE_SELECTED` / `CLUSTER_CONTEXT_ATTACHED`
    / `LABEL_QUEUE_ENQUEUED` / `LABEL_TRACKING_STARTED` /
    `LABEL_WINDOW_COMPLETED` / `TAIL_LABEL_ASSIGNED` /
    `STRATEGY_VALIDATION_SAMPLE_CREATED`), (3) if missed,
    why (taxonomy: `not_in_futures_universe`,
    `not_in_exchange_info`, `not_usdt_perpetual`,
    `symbol_limit_excluded`,
    `candidate_pool_capacity_evicted`, `score_too_low`,
    `liquidity_insufficient`,
    `data_stale_or_degraded_or_unreliable`,
    `risk_rejected`, `no_completed_tail_label_yet`), (4)
    whether top movers were captured early enough
    (`first_seen_latency_seconds`,
    `median_first_seen_latency_seconds`), (5) whether
    captured movers proceeded into the label /
    validation pipeline (`label_tracking_rate`,
    `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`), (6) whether
    missed movers are a system-coverage problem or a
    market / exchange-coverage problem, and (7) whether
    captured-but-rejected movers were rejected for sound
    conservative reasons (`risk_rejected_mover_count` is
    **not** treated as a system failure).
  - Trigger context: B-B-B-C proved long-window paper
    data collection works end-to-end; B-B-B-D answers
    "are the samples the right ones — does the discovery
    layer cover real market movers?". Concrete trigger:
    SAGAUSDT showed an obvious move on Binance's public
    24 h gainer board; the system already captured
    SAGAUSDT end-to-end through `PRE_ANOMALY_DETECTED` →
    `ANOMALY_DETECTED` → `MARKET_REGIME_ASSESSED` →
    `CANDIDATE_STAGE_CLASSIFIED` → `OPPORTUNITY_SCORED` →
    `STRATEGY_MODE_SELECTED` → `CLUSTER_CONTEXT_ATTACHED`
    → `LABEL_QUEUE_ENQUEUED` → `LABEL_TRACKING_STARTED` →
    `TAIL_LABEL_ASSIGNED` →
    `STRATEGY_VALIDATION_SAMPLE_CREATED`. One coin proves
    nothing — the audit institutionalises "human looks at
    gainer board vs. did the system see it" as a
    coverage protocol, not as ad-hoc human screenshots.
  - Allowed outputs (descriptive only):
    `top_mover_capture_summary`, `captured_mover_evidence`,
    `missed_mover_audit`, `symbol_universe_exclusion_summary`,
    `candidate_eviction_summary`, `risk_rejection_summary`,
    `first_seen_latency_summary`, `capture_recall_rate`,
    `missed_tail_candidate_list`, `coverage_warning`,
    `insufficient_coverage_reasons`.
  - Allowed input sources (read-only; reuse existing
    surfaces): Binance public 24 h ticker / public market
    data, `EventRepository`, daily report, Phase 8.5
    export / Phase 10A replay, `StrategyValidationDataset`,
    `PaperAlphaGateReport`, `RegimeClusterEvidencePack`,
    `SymbolUniverse` / `exchangeInfo`-as-truth catalogue,
    candidate pool logs / capacity-eviction evidence
    (where available).
  - Audit objects: top gainers / top movers in eligible
    USDT-perpetual universe, detected anomalies,
    pre-anomaly candidates, label-tracked candidates,
    validation samples, risk-rejected movers, movers
    excluded because not in the current tradable
    universe.
  - Key metrics (descriptive only): `top_mover_count`,
    `captured_top_mover_count`, `missed_top_mover_count`,
    `capture_recall_rate`, `anomaly_detected_rate`,
    `label_tracking_rate`, `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`,
    `risk_rejected_mover_count`, `not_in_universe_count`,
    `capacity_evicted_count`, `data_unreliable_count`,
    `median_first_seen_latency_seconds`.
  - Audit cadence (operator-driven; not auto-scheduled):
    A1 (first end-to-end coverage audit pass), A2 (second
    audit pass against an independent paper observation
    window), A3+ reserved for later child slices and out
    of scope for this PR.
  - Interpretation principles (must be read verbatim):
    captured-but-rejected ≠ failure;
    missed-but-not-in-universe ≠ failure; coverage
    warning is only raised when the mover is in the
    eligible universe AND shows clear right-tail
    behaviour AND was missed for a system-correctable
    reason; a single mover proves nothing (SAGAUSDT
    specifically does not authorise rule relaxation);
    capture audit ≠ trading-profit evidence; low coverage
    is a `review` outcome, not a `relax` outcome; high
    coverage does not authorise live trading; single-coin
    / "妖币" reframing is forbidden.

#### What this PR does NOT do (must be read verbatim)

  - It does **NOT** flip any phase's acceptance state.
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED /
    NOT_STARTED` (this PR scopes the slice; it does not
    flip its state). Phase 12 remains `FORBIDDEN`.
  - It does **NOT** rename Phase 11C.1C-C-B-B-B.
  - It does **NOT** implement the Mover Capture Recall &
    Missed-Tail Coverage Audit v0 — the audit is defined
    as docs / evidence templates only, and the slice will
    not introduce any new runtime module or new event
    type at any point in its lifecycle.
  - It does **NOT** auto-schedule A1 / A2 / A3+ runs.
    The cadence is operator-driven.
  - It does **NOT** widen, replace, or relax the existing
    Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` minimums or the Paper Alpha
    Gate v0 `INCONCLUSIVE` minimums or the Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0
    cadence.
  - It does **NOT** authorise live trading, API keys,
    private endpoints, DeepSeek trade decisions, real
    Telegram outbound, AI Learning, automatic parameter
    optimisation, reinforcement learning, the complete
    Strategy Validation Lab follow-up, or Phase 12.
  - It does **NOT** authorise any rule relaxation on the
    basis of single-coin / "妖币" cases (SAGAUSDT or
    otherwise).
  - It does **NOT** stand in for a Historical 30D+ Blind
    Replay / Walk-forward Validation gate (that gate is
    reserved for a Phase 12 candidate review and is
    explicitly out of scope here).
  - It does **NOT** add any new Python module under
    `app/`.
  - It does **NOT** add any new event type.
  - It does **NOT** modify any runtime behaviour.
  - It does **NOT** modify configuration schemas,
    defaults, or YAML.
  - It does **NOT** add or modify tests.
  - It does **NOT** run tests.
  - It does **NOT** modify `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `llm/`,
    `telegram/`, or `exchange/`.

#### Documentation changes

  - **NEW:** `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`
    — Phase 11C.1C-C-B-B-B-D kickoff brief: scope,
    parent / child boundary, AMOS positioning, audit
    cadence (A1 / A2 with A3+ reserved), audit input
    sources, audit objects, allowed outputs, key metrics,
    eight interpretation principles, boundary table,
    slice-specific forbidden items, acceptance-gate
    placeholder, "what this kickoff PR does / does NOT
    do" sections, and Phase 1 safety-flag invariants.
  - **NEW:** `docs/PR60_DESCRIPTION.md` — this PR's
    description.
  - `docs/PROJECT_STATUS.md` (modified — docs-only):
    replaced the B-B-B-D `NEXT_ALLOWED / NOT_STARTED —
    placeholder; not yet defined by name or scope`
    paragraph with a fully scoped definition; added a
    new kickoff row in the per-phase ledger; marked the
    prior B-B-B-D placeholder row as SUPERSEDED.
  - `docs/PHASE_GATE.md` (modified — docs-only): replaced
    the B-B-B-D row in the *Open / Reserved phases* table
    with a fully scoped definition; replaced the
    dedicated `## Open phase: Phase 11C.1C-C-B-B-B-D`
    detail section with full scope, allowed outputs,
    allowed input sources, inherited forbidden items, and
    acceptance gate placeholder; updated the Phase 12
    row to mention "Phase 11C.1C-C-B-B-B-D kickoff via
    PR #60"; updated the *Architecture governance
    (guidance-only; no phase change)* closing paragraph
    to reflect the new B-B-B-D defined-by-name-and-scope
    state.
  - `docs/CHANGELOG.md` (this entry).

#### Safety boundary (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

#### Confirmation checklist

  - [x] Docs-only PR; no runtime code modified.
  - [x] No new Python files.
  - [x] No new event types.
  - [x] No new tests.
  - [x] No tests run.
  - [x] No runtime behaviour changed.
  - [x] No `app/` / `scripts/` / `tests/` / `configs/`
    changes.
  - [x] No `execution/` / `risk/` / `llm/` / `telegram/`
    / `exchange/` changes.
  - [x] No strategy runtime code changes.
  - [x] No phase's acceptance state flipped — Phase
    11C.1C-C-B-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`;
    Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED /
    NOT_STARTED` (scoped by this PR; not flipped).
  - [x] Phase 11C.1C-C-B-B-B parent is **not** renamed;
    it remains *Strategy Validation Lab (deeper) & richer
    Cluster Exposure Control follow-up*.
  - [x] Phase 11C.1C-C-B-B-B-D is recorded as the fourth
    child slice under Phase 11C.1C-C-B-B-B = Mover
    Capture Recall & Missed-Tail Coverage Audit v0 /
    异动币捕捉召回与漏捕右尾覆盖审计 v0.
  - [x] Audit cadence recorded (A1 / A2 with A3+
    reserved; operator-driven; not auto-scheduled).
  - [x] Audit input sources recorded (Binance public 24 h
    ticker / public market data, `EventRepository`, daily
    report, Phase 8.5 export / Phase 10A replay,
    `StrategyValidationDataset`, `PaperAlphaGateReport`,
    `RegimeClusterEvidencePack`, `SymbolUniverse` /
    `exchangeInfo`-as-truth catalogue, candidate pool
    logs / capacity-eviction evidence).
  - [x] Audit objects recorded (top gainers / top movers
    in eligible USDT-perpetual universe, detected
    anomalies, pre-anomaly candidates, label-tracked
    candidates, validation samples, risk-rejected movers,
    movers excluded because not in current tradable
    universe).
  - [x] Allowed outputs explicitly listed
    (`top_mover_capture_summary`,
    `captured_mover_evidence`, `missed_mover_audit`,
    `symbol_universe_exclusion_summary`,
    `candidate_eviction_summary`,
    `risk_rejection_summary`,
    `first_seen_latency_summary`, `capture_recall_rate`,
    `missed_tail_candidate_list`, `coverage_warning`,
    `insufficient_coverage_reasons`) and marked
    descriptive only.
  - [x] Key metrics recorded
    (`top_mover_count`, `captured_top_mover_count`,
    `missed_top_mover_count`, `capture_recall_rate`,
    `anomaly_detected_rate`, `label_tracking_rate`,
    `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`,
    `risk_rejected_mover_count`,
    `not_in_universe_count`, `capacity_evicted_count`,
    `data_unreliable_count`,
    `median_first_seen_latency_seconds`).
  - [x] Eight interpretation principles recorded verbatim
    (captured-but-rejected ≠ failure;
    missed-but-not-in-universe ≠ failure; coverage
    warning only when in eligible universe AND clear
    right-tail AND system-correctable reason; a single
    mover incl. SAGAUSDT proves nothing; capture audit ≠
    trading-profit evidence; low coverage = `review`,
    not `relax`; high coverage does not authorise live
    trading; single-coin / "妖币" reframing is
    forbidden).
  - [x] Slice-specific forbidden items recorded (no
    triggering of real trades; no modifying position
    size, leverage, stop-loss, target price, the Risk
    Engine, or the Execution FSM; no AI / LLM trade
    authority; no auto parameter optimisation; no auto
    rule relaxation on low coverage or single-coin
    cases; no auto-scheduling of A1 / A2 / A3+; no
    promotion of any audit artefact to a real-trade
    authority; no rewriting of Regime & Cluster Evidence
    Pack v0 `INSUFFICIENT_SAMPLE` rule or Paper Alpha
    Gate v0 `INCONCLUSIVE` rule; no new event types in
    this kickoff PR or in any future Phase
    11C.1C-C-B-B-B-D PR; no Historical 30D+ Blind
    Replay / Walk-forward Validation under this slice;
    cannot enter Phase 12).
  - [x] Safety boundary held end-to-end (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - [x] Phase 12 remains `FORBIDDEN`.

### Phase 11C.1C-C-B-B-B-C accepted - Long-Window Cohort Stability & Sample Sufficiency Protocol v0 docs-only closeout (PR #59)

**Type:** Docs-only closeout / acceptance flip.
**Runtime effect:** **none.**
**Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-C from
`NEXT_ALLOWED / NOT_STARTED` (defined in place by PR #58
docs-only kickoff) to `ACCEPTED`; introduces Phase
11C.1C-C-B-B-B-D as `NEXT_ALLOWED / NOT_STARTED`
(placeholder; not yet defined).
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **Status: ACCEPTED (closed 2026-05-25; PR #58 docs-only
> kickoff merged into `main` on 2026-05-25; this docs-only
> closeout PR #59 records the operator-VPS W1 / W1+ 2 h,
> W2 4 h, and W3 24 h upper-bound early-stop paper WS
> evidence and flips the slice to `ACCEPTED`).**
> Long-Window Cohort Stability & Sample Sufficiency
> Protocol v0 / *长窗口 Cohort 稳定性与样本充足协议 v0* —
> third child slice under the Phase 11C.1C-C-B-B-B parent
> — paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT**
> rule relaxation based on low samples. **NOT** a Risk
> Engine change. **NOT** an Execution FSM change. **NOT**
> the complete Strategy Validation Lab follow-up. **NOT**
> Phase 12.

#### Phase 11C.1C-C-B-B-B-C accepted (closeout summary)

  - Long-window cohort stability and sample sufficiency
    protocol completed.
  - W1 / W1+ 2 h paper WS evidence recorded.
  - W2 4 h paper WS evidence recorded.
  - W3 24 h upper-bound early-stop evidence recorded.
  - W3 reached completed-tail-label sufficiency early:
    `total_elapsed_seconds=900`,
    `final_tail_labels_since_start=20>=10`,
    `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`,
    24 h full runtime NOT NEEDED.
  - Export packages verified: W1 `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`
    `manifest_event_count=23001`
    `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`; W2
    `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`
    `manifest_event_count=61546`
    `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`; W3
    `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`
    generated 2026-05-25 12:41 UTC
    `manifest_event_count=62761`
    `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`.
  - `REGIME_CLUSTER_*` and `PAPER_ALPHA_*` events verified
    (2 h: `PAPER_ALPHA_COHORT_EVALUATED=18`,
    `PAPER_ALPHA_GATE_EVALUATED=3`,
    `PAPER_ALPHA_REPORT_GENERATED=3`,
    `PAPER_ALPHA_RULE_EVALUATED=27`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`; 4 h:
    `PAPER_ALPHA_COHORT_EVALUATED=24`,
    `PAPER_ALPHA_GATE_EVALUATED=4`,
    `PAPER_ALPHA_REPORT_GENERATED=4`,
    `PAPER_ALPHA_RULE_EVALUATED=36`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`; W3
    export-range: `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`,
    `PAPER_ALPHA_GATE_EVALUATED=5`,
    `PAPER_ALPHA_RULE_EVALUATED=45`,
    `PAPER_ALPHA_COHORT_EVALUATED=30`,
    `PAPER_ALPHA_REPORT_GENERATED=5`).
  - `TAIL_LABEL_ASSIGNED` and `LABEL_WINDOW_COMPLETED`
    events verified in W3 export-range
    (`TAIL_LABEL_ASSIGNED=495`,
    `LABEL_WINDOW_COMPLETED=495`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED=397`).
  - No runtime behavior changed by closeout.
  - Paper-only, no live trading, Phase 12 forbidden.

#### Closeout interpretation (must be read verbatim)

  - **B-B-B-C acceptance is acceptance of the long-window
    data collection and sample-sufficiency protocol.**
  - It does **NOT** mean any Regime / Cluster has proven
    right-tail advantage yet.
  - It does **NOT** mean strategy effectiveness is proven.
  - It does **NOT** authorise live trading.
  - It does **NOT** authorise Phase 12.
  - It does **NOT** authorise rule relaxation based on low
    samples.
  - It does **NOT** authorise automatic parameter
    optimisation.
  - It does **NOT** authorise AI Learning.
  - It does **NOT** authorise reinforcement learning.
  - It does **NOT** authorise changing the Risk Engine or
    the Execution FSM.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D
    kickoff bypassing the standard gate.
  - It records that:
      - 2 h paper WS run works.
      - 4 h paper WS run works.
      - completed labels begin to appear over longer
        windows.
      - 24 h upper-bound early-stop works.
      - completed-tail-label sufficiency threshold can be
        reached early.
      - export / replay evidence preserves the results.
      - low-sample states remain conservative
        (`INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` are valid
        outputs not failures).
      - no trade authority was granted by any window.

#### Important interpretation of W2

The 4 h window showed **progress** from
`completed_tail_label_count=0` (W1 / W1+ 2 h) to
`completed_tail_label_count=2` (W2 4 h) — completed tail
labels are starting to appear as the observation window
lengthens, exactly as the protocol predicted. However,
`2` is still **below the 10 completed-tail-label
sufficiency threshold**, so
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` and
`paper_alpha_gate_status=INCONCLUSIVE` remained the
**correct** results for W2. **This does NOT indicate
runtime failure.** **This does NOT authorise rule
relaxation** — the protocol's central rule is that low
samples cannot output strong conclusions, and the rule
holds verbatim. The right next step was therefore to
extend the observation window further (W3 24 h
upper-bound), which we did.

#### Important interpretation of W3

W3 was started as a **24 h upper-bound** paper WS run. A
watcher monitored `final_tail_labels_since_start` and
stopped the run early once tail-label sufficiency was
reached (`final_tail_labels_since_start=20>=10`). The run
terminated cleanly at `total_elapsed_seconds=900`; the
full 24 h runtime was **not needed**. **This proves the
B-B-B-C sample sufficiency protocol can save runtime
while preserving evidence.** Clarification on the two W3
numbers: `final_tail_labels_since_start=20` is the
**watcher early-stop condition** for the 900 s live
window; `TAIL_LABEL_ASSIGNED=495` is the **24 h
export-range event count** captured from the Phase 8.5
export bundle — both valid, different scopes. **Do not
confuse the two numbers.**

#### Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise

  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise live trading.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise API keys.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise private endpoints.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise DeepSeek trade decisions.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise real Telegram outbound.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise Phase 12.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise automatic parameter optimisation.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise AI Learning.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise reinforcement learning.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise rule relaxation based on low samples.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise changing the Risk Engine or the Execution
    FSM.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing
    the standard gate.
  - Long-window protocol outputs and per-window outputs
    remain paper-only / report-only / evidence-only.
  - Long-window protocol outputs and per-window outputs
    cannot trigger orders, leverage, position sizing,
    stop changes, target changes, Risk Engine changes, or
    Execution FSM changes.

#### Changed

- **`docs/PROJECT_STATUS.md`** — current-phase block now
  leads with Phase 11C.1C-C-B-B-B-C = `ACCEPTED`; inline
  summary list flips B-B-B-C from `NEXT_ALLOWED /
  NOT_STARTED` to `ACCEPTED` with verbatim W1 / W1+ 2 h,
  W2 4 h, W3 24 h upper-bound early-stop evidence summary
  + adds Phase 11C.1C-C-B-B-B-D = `NEXT_ALLOWED /
  NOT_STARTED` placeholder; "does NOT authorise" block
  extended for B-B-B-C with the verbatim list of
  prohibitions (live trading / API keys / private
  endpoints / DeepSeek / Telegram / Phase 12 / parameter
  optimisation / AI Learning / reinforcement learning /
  rule relaxation / Risk Engine / Execution FSM / B-B-B-D
  bypass) and the W2 progress 0→2 / W3 early-stop
  interpretations. Per-phase table: new 2026-05-25
  B-B-B-C closeout `ACCEPTED` row + new B-B-B-D placeholder
  row inserted (legacy B-B-B-C kickoff row annotated
  `SUPERSEDED`); per-phase prose section converted to
  *ACCEPTED via PR #58 docs-only kickoff + PR #59
  docs-only closeout* with full operator-VPS evidence
  subsection.
- **`docs/PHASE_GATE.md`** — Phase 11C.1C-C-B-B-B-C row
  added to the *Closed phases* table; *Open / Reserved
  phases* table updated (B-B-B-C → `ACCEPTED — see Closed
  phases table above`, B-B-B-D → `NEXT_ALLOWED /
  NOT_STARTED` placeholder); the *Open phase: Phase
  11C.1C-C-B-B-B-C* header replaced with *Closed phase:
  Phase 11C.1C-C-B-B-B-C (ACCEPTED)*; new *Phase
  11C.1C-C-B-B-B-C acceptance evidence (operator-VPS W1
  / W1+ 2 h, W2 4 h, W3 24 h upper-bound early-stop
  paper WS evidence PASSED)* section inserted carrying
  the verbatim W1 / W1+, W2, W3 transcripts + W3 export
  evidence + acceptance criteria + closeout
  interpretation; new *Open phase: Phase 11C.1C-C-B-B-B-D
  (NEXT_ALLOWED / NOT_STARTED)* section + acceptance gate
  placeholder; Phase 12 forbidden row updated to mention
  B-B-B-C and B-B-B-D explicitly; *Architecture
  governance (guidance-only; no phase change)* closing
  paragraph refreshed (B-B-B-A = ACCEPTED; B-B-B-B =
  ACCEPTED; B-B-B-C = ACCEPTED; B-B-B-D = NEXT_ALLOWED /
  NOT_STARTED; Phase 12 = FORBIDDEN).
- **`docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`**
  — status banner flipped from `NEXT_ALLOWED / NOT_STARTED
  (docs-only kickoff / scope alignment)` to `ACCEPTED`;
  parent / child relationship updated to mention B-B-B-D;
  new "Phase 11C.1C-C-B-B-B-C acceptance evidence
  (operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound
  early-stop paper WS evidence) — FILED via PR #59"
  section added with W1 / W1+, W2, W3 verbatim
  transcripts + W3 export-range event counts + W2
  progress / W3 early-stop interpretations + every-gate-met
  acceptance criteria + closeout-does-not-authorise list.
- **`docs/CHANGELOG.md`** — *this entry*.

#### Added

- **`docs/PR59_DESCRIPTION.md`** (NEW) — describes this
  docs-only closeout PR (changed files, allowed /
  forbidden edits, confirmation checklist, acceptance
  evidence).

#### Forbidden by this PR (carries forward verbatim)

- Real trading.
- Live trading.
- Binance API key / secret.
- Signed endpoint / `listenKey` / private WebSocket.
- Account / order / position / leverage / margin endpoint.
- DeepSeek trade decision.
- Real Telegram outbound.
- AI deciding direction / position size / leverage / stop
  / target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- AI Learning that auto-decides trades.
- Auto-rule-relaxation on low samples.
- Risk Engine override / bypass.
- Execution FSM override / bypass.
- Phase Gate override / bypass.
- Modifying `app/`, `scripts/`, `tests/`, `configs/`,
  `risk/`, `execution/`, `llm/`, `telegram/`, or
  `exchange/`.
- Modifying configuration schemas, defaults, or YAML.
- Modifying strategy runtime code.
- Adding or modifying tests.
- Adding new Python modules.
- Adding new event types.
- Modifying runtime behavior.
- Implementing new functionality.
- Phase 11C.1C-C-B-B-B-D implementation (reserved for the
  next child slice; will require its own kickoff PR,
  brief, scope, boundary table, forbidden list, and
  acceptance evidence).
- Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard
  gate.
- Phase 12 / live trading kickoff.

#### Acceptance gate (docs-only closeout)

- Docs-only PR. **No code modified** under `app/`,
  `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
  `llm/`, `telegram/`, or `exchange/`.
- **No new Python files.**
- **No new event types.**
- **No new tests.**
- **No tests run.**
- **No dry-run / smoke required** by this PR (the
  operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound
  early-stop paper WS evidence was captured pre-PR; this
  PR **records** the evidence in the ledger).
- Phase 11C.1C-C-B-B-B-C flipped to `ACCEPTED`.
- Phase 11C.1C-C-B-B-B-D introduced at `NEXT_ALLOWED /
  NOT_STARTED`.
- Safety boundary held end-to-end (`mode=paper`,
  `live_trading=False`, `exchange_live_orders=False`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no API key, no
  signed endpoint, no private WS, no `listenKey`, no
  DeepSeek trade decision, no real Telegram outbound).
- **Phase 12 remains FORBIDDEN.**

#### Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Docs-only - Phase 11C.1C-C-B-B-B-C (Long-Window Cohort Stability & Sample Sufficiency Protocol v0) kickoff / scope alignment (PR #58)

**Type:** Docs-only kickoff / scope-alignment.
**Runtime effect:** **none.**
**Phase ledger effect:** **defines** Phase
11C.1C-C-B-B-B-C in place at `NEXT_ALLOWED / NOT_STARTED`
as the **third child slice** under the Phase
11C.1C-C-B-B-B parent. **No phase's acceptance state is
flipped.** Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`.
Phase 11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`
(parent; **unchanged definition** — *Strategy Validation
Lab (deeper) & richer Cluster Exposure Control
follow-up*). Phase 11C.1C-C-B-B-B-C remains `NEXT_ALLOWED
/ NOT_STARTED` (this PR scopes the slice; it does not
flip its state).
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **This PR is paper / report / evidence only.** **NOT**
> live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning.
> **NOT** a strategy implementation. **NOT** a trading
> module. **NOT** a new runtime module. **NOT** the
> complete Strategy Validation Lab follow-up. **NOT** the
> Phase 11C.1C-C-B-B-B-C *closeout* (the closeout will be
> a separate docs-only PR after the operator captures
> W1 / W2 / W3 paper evidence). **NOT** Phase 12.
>
> The Long-Window Cohort Stability & Sample Sufficiency
> Protocol v0 is **docs / evidence-template only**
> end-to-end. It does not add a new runtime module, a new
> event type, a new strategy, a new execution surface, a
> new optimiser, or a new AI authority. It defines the
> long-window paper data-collection cadence (1 h → 4 h →
> 24 h, with multi-day reserved), the sample sufficiency
> rule, the cohort stability acceptance criteria, and the
> evidence-template shape that any future closeout PR
> must follow. The Risk Engine remains the single
> trade-decision gate.

#### Why this slice exists

PR #56 merged the Regime & Cluster Cohort Evidence Pack
v0 implementation into `main` (mergeCommit `1a9abe2`); PR
#57 merged the docs-only closeout and flipped Phase
11C.1C-C-B-B-B-B to `ACCEPTED`. The operator-VPS 10 min
WS paper smoke evidence was accepted as well-formed
(`duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`,
`ws_real_transport=true`, `ingestion_errors=0`, `HTTP
429=0`, `HTTP 418=0`), and the runtime / daily-report /
Phase 8.5 export pipeline is functional. **However**: the
window's `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
`sample_count=14<20`, `completed_tail_label_count=0<10`.
Runtime / report / export are correct, but the 10 min
observation window is too short to support a Regime /
Cluster right-tail conclusion. The right next step is
**not** to add a new strategy module, a new AI authority,
or a new optimiser; the right next step is to
**accumulate structural data across longer paper
observation windows**. This slice codifies that step as a
**protocol** — a long-window paper data-collection
cadence, a sample sufficiency rule, and cohort stability
acceptance criteria — while keeping all of the Phase 1
safety lock invariants in force.

#### Added

- **`docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`**
  (NEW) — *Phase 11C.1C-C-B-B-B-C — Long-Window Cohort
  Stability & Sample Sufficiency Protocol v0 (docs-only
  kickoff)* / *长窗口 Cohort 稳定性与样本充足协议 v0*.
  Records the parent / child relationship (Phase
  11C.1C-C-B-B-B-C is the **third child slice** under
  Phase 11C.1C-C-B-B-B; the parent phase is **not**
  renamed); the **why** (PR #57 closeout flipped B-B-B-B
  to `ACCEPTED` with `INSUFFICIENT_SAMPLE`; runtime /
  report / export are correct but the observation window
  is too short to support a Regime / Cluster right-tail
  conclusion; the right next step is to accumulate
  structural data across longer paper observation
  windows); the long-window run cadence (W1=1 h, W2=4 h,
  W3=24 h, W4+ multi-day reserved; **operator-driven; not
  auto-scheduled**); the per-window evidence fields the
  operator must capture verbatim
  (`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`,
  `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`,
  `PAPER_ALPHA_GATE_EVALUATED`,
  `PAPER_ALPHA_RULE_EVALUATED`,
  `PAPER_ALPHA_COHORT_EVALUATED`,
  `PAPER_ALPHA_REPORT_GENERATED`, daily report Regime &
  Cluster section, daily report Paper Alpha Gate section,
  `sample_count`, `completed_tail_label_count`,
  `regime_cluster_evidence_status`,
  `paper_alpha_gate_status`, `insufficient_sample_reasons`,
  Phase 8.5 export package, export contains
  `REGIME_CLUSTER_*` events, export contains
  `PAPER_ALPHA_*` events, safety flags); the sample
  sufficiency principle (low samples cannot output
  strong conclusions; `INSUFFICIENT_SAMPLE` /
  `INCONCLUSIVE` are valid outputs not failures; cohort
  signals only allowed once sample-sufficient; cohort
  signals remain paper-only / report-only /
  evidence-only); the cohort stability principle (signals
  must persist across windows to count as evidence;
  inversion is a warning; biased toward "do nothing" when
  stability is unclear); the **allowed outputs** (docs /
  evidence templates only — `long_window_run_plan`,
  `sample_sufficiency_checklist`,
  `cohort_stability_checklist`,
  `operator_vps_evidence_template`,
  `export_replay_evidence_template`,
  `closeout_acceptance_template`); the **boundary table**
  (Phase 1 safety lock + outputs-are-descriptive-only
  invariants); the **forbidden list** (inherited
  verbatim + slice-specific items including no
  auto-scheduling, no new runtime module across the
  slice's lifecycle, no `INSUFFICIENT_SAMPLE` /
  `INCONCLUSIVE` rule replacement); and the
  **acceptance-gate placeholder** for the future closeout
  PR.
- **`docs/PR58_DESCRIPTION.md`** (NEW) — describes this
  docs-only kickoff PR (changed files, allowed /
  forbidden edits, confirmation checklist).

#### Changed

- **`docs/PHASE_GATE.md`** — *Open / Reserved phases*
  table Phase 11C.1C-C-B-B-B-C row redefined from "Next
  child slice (placeholder; not yet defined)" to
  *Long-Window Cohort Stability & Sample Sufficiency
  Protocol v0 (docs / evidence-template-only third child
  slice under Phase 11C.1C-C-B-B-B; docs-only kickoff via
  PR #58)* with full scope language, allowed-outputs
  list, long-window cadence, sample-sufficiency / cohort-
  stability principles, slice-specific forbidden items,
  and inherited-forbidden-list reference. *Open phase:
  Phase 11C.1C-C-B-B-B-C (NEXT_ALLOWED / NOT_STARTED)*
  section rewritten with full scope (long-window cadence,
  per-window evidence fields, sample sufficiency
  principle, cohort stability principle, allowed outputs,
  boundary table, forbidden list, acceptance-gate
  placeholder, kickoff acceptance gate). *Architecture
  governance (guidance-only; no phase change)* closing
  paragraph refreshed to reflect the current open-phase
  state (B-B-A = ACCEPTED; B-B-B = NEXT_ALLOWED /
  NOT_STARTED; B-B-B-A = ACCEPTED; B-B-B-B = ACCEPTED;
  B-B-B-C = NEXT_ALLOWED / NOT_STARTED with full scope;
  Phase 12 = FORBIDDEN).
- **`docs/PROJECT_STATUS.md`** — current-phase block
  B-B-B-C inline summary line refreshed with the new
  defined name (Long-Window Cohort Stability & Sample
  Sufficiency Protocol v0 / 长窗口 Cohort 稳定性与样本
  充足协议 v0), the docs-only-kickoff scope, and the
  paper / report / evidence-only safety language.
  Per-phase table B-B-B-C row redefined with full scope,
  allowed outputs, long-window cadence, per-window
  evidence fields, sample sufficiency / cohort stability
  principles, and the inherited forbidden list reference.
  The B-B-B-C prose subsection rewritten to record
  positioning under AMOS, the **why** (PR #57 closeout
  flipped B-B-B-B to `ACCEPTED` with `INSUFFICIENT_SAMPLE`;
  runtime / report / export are correct but the
  observation window is too short), allowed outputs, the
  long-window cadence, the per-window evidence fields,
  the sample sufficiency principle, the cohort stability
  principle, and the slice-specific forbidden items.
- **`docs/CHANGELOG.md`** — *this entry*.

#### Phase 11C.1C-C-B-B-B-C exists to record the following protocol

  - **Long-window paper data-collection cadence
    (operator-driven; not auto-scheduled):**
      - **W1 — 1 h paper WS run** (first meaningful sample
        window).
      - **W2 — 4 h paper WS run** (cohort stability check).
      - **W3 — 24 h paper WS run** (day-level structural
        evidence).
      - **W4+ — multi-day paper observation** (reserved;
        out of scope; not implemented in this PR; not
        auto-scheduled in this PR).
  - **Per-window evidence the operator must capture:**
      - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`
      - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`
      - `PAPER_ALPHA_GATE_EVALUATED`
      - `PAPER_ALPHA_RULE_EVALUATED`
      - `PAPER_ALPHA_COHORT_EVALUATED`
      - `PAPER_ALPHA_REPORT_GENERATED`
      - daily report Regime & Cluster section
      - daily report Paper Alpha Gate section
      - `sample_count`
      - `completed_tail_label_count`
      - `regime_cluster_evidence_status`
      - `paper_alpha_gate_status`
      - `insufficient_sample_reasons`
      - Phase 8.5 export package
      - export contains `REGIME_CLUSTER_*` events
      - export contains `PAPER_ALPHA_*` events
      - safety flags

#### Sample sufficiency principle (carries forward verbatim)

  - Low samples cannot output strong conclusions.
  - When `completed_tail_label_count` is below the Regime
    & Cluster Evidence Pack v0 minimum, no Regime /
    Cluster right-tail conclusion is permitted.
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
    disappears in the next is **not** treated as evidence.
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

#### Allowed outputs (docs / evidence templates only)

Each is a **descriptive document or evidence template
only**. None has trade authority. None is read by the
Risk Engine or the Execution FSM. None is a new Python
module, a new event type, or a new runtime hook:

  - `long_window_run_plan`
  - `sample_sufficiency_checklist`
  - `cohort_stability_checklist`
  - `operator_vps_evidence_template`
  - `export_replay_evidence_template`
  - `closeout_acceptance_template`

#### Forbidden by this PR (carries forward verbatim + slice-specific items)

- Real trading.
- Live trading.
- Binance API key / secret.
- Signed endpoint / `listenKey` / private WebSocket.
- Account / order / position / leverage / margin endpoint.
- DeepSeek trade decision.
- Real Telegram outbound.
- AI deciding direction / position size / leverage / stop /
  target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- AI Learning that auto-decides trades.
- Auto-rule-relaxation on low samples.
- Auto-scheduling W1 / W2 / W3 / W4+ runs from runtime
  code.
- Risk Engine override / bypass.
- Execution FSM override / bypass.
- Phase Gate override / bypass.
- Triggering a real trade from any protocol artefact.
- Modifying position size / leverage / stop-loss / target
  price from any protocol artefact.
- Modifying the Risk Engine or the Execution FSM from any
  protocol artefact.
- Replacing the Regime & Cluster Cohort Evidence Pack v0
  `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
- Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
  with a relaxed rule.
- Implementing the Long-Window Cohort Stability & Sample
  Sufficiency Protocol v0 as a new runtime module — the
  slice is intentionally **docs / evidence template only**
  end-to-end.
- Adding new event types, new Python modules, or new
  runtime behaviour at any point in this slice's
  lifecycle.
- Modifying `app/`, `scripts/`, `tests/`, `configs/`,
  `risk/`, `execution/`, `llm/`, `telegram/`, or
  `exchange/`.
- Modifying configuration schemas, defaults, or YAML.
- Adding or modifying tests.
- Running tests as part of this kickoff PR.
- Modifying strategy runtime code.
- Modifying runtime behavior.
- Implementing new functionality.
- Flipping any phase's acceptance state. Phase
  11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
  11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
  11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
  Phase 11C.1C-C-B-B-B-C remains `NEXT_ALLOWED /
  NOT_STARTED` (scoped by this PR; not flipped). Phase
  12 remains `FORBIDDEN`.
- Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
  its existing definition — *Strategy Validation Lab
  (deeper) & richer Cluster Exposure Control follow-up*.
- Phase 11C.1C-C-B-B-B-C *closeout* (out of scope; will
  be authored after the operator captures W1 / W2 / W3
  paper evidence and a separate docs-only closeout PR
  flips the slice to `ACCEPTED`).
- Phase 11C.1C-C-B-B-B-D / B-B-B-E / further child
  slices (out of scope; will require their own kickoff
  PRs).
- Phase 12 / live trading kickoff.

#### Acceptance gate (docs-only)

- Docs-only PR. **No code modified** under `app/`,
  `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
  `llm/`, `telegram/`, or `exchange/`.
- **No new Python files.**
- **No new event types.**
- **No new tests.**
- **No tests run.**
- **No dry-run / smoke required** (no runtime change).
- **No phase acceptance state flipped.**
- Safety boundary held end-to-end (`mode=paper`,
  `live_trading=False`, `exchange_live_orders=False`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no Binance API
  key, no Binance API secret, no signed endpoint, no
  account / order / position / leverage / margin
  endpoint, no private WebSocket, no `listenKey`, no
  DeepSeek trade decision, no real Telegram outbound).
- **Phase 12 remains FORBIDDEN.**

#### Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Phase 11C.1C-C-B-B-B-B accepted - Regime & Cluster Cohort Evidence Pack v0 docs-only closeout (PR #57)

**Type:** Docs-only closeout / acceptance flip.
**Runtime effect:** **none.**
**Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-B from
`MERGED / AWAITING_OPERATOR_VPS_EVIDENCE / CLOSEOUT_PENDING`
to `ACCEPTED`; introduces Phase 11C.1C-C-B-B-B-C as
`NEXT_ALLOWED / NOT_STARTED` (placeholder; not yet defined).
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **Status: ACCEPTED (closed 2026-05-24; PR #56 merged into
> `main` on 2026-05-24, mergeCommit `1a9abe2`; this docs-only
> closeout PR #57 records the operator-VPS paper evidence
> that flips Phase 11C.1C-C-B-B-B-B to `ACCEPTED`).** Regime
> & Cluster Cohort Evidence Pack v0 / *Regime 与 Cluster 分组
> 证据包 v0* — second child slice under the Phase
> 11C.1C-C-B-B-B parent — paper / report / evidence only.
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** the complete Strategy Validation Lab
> follow-up. **NOT** Phase 12.

#### Phase 11C.1C-C-B-B-B-B accepted (closeout summary)

  - Regime & Cluster Cohort Evidence Pack v0 implementation
    merged (PR #56 merged into `main` on 2026-05-24,
    mergeCommit `1a9abe2`).
  - operator-VPS 10 min WS paper smoke evidence recorded
    (`duration_seconds=600.0`, `uptime≈608s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`).
  - daily report Regime & Cluster section verified
    (`"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
    Evidence Pack v0"`;
    `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
    `sample_count=14`, `completed_tail_label_count=0`,
    `insufficient_sample_reasons=[sample_count_below_min=14<20,
    completed_tail_label_count_below_min=0<10]`).
  - `REGIME_CLUSTER_*` events verified
    (`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`).
  - export package generated and verified
    (`export_test_data=OK`,
    `data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip`,
    `manifest_event_count=3151`,
    `redaction_applied=True`, `events.jsonl` exists,
    `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK=PASS`).
  - export contains `REGIME_CLUSTER_*` events.
  - export package files observed: `manifest.json`,
    `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`, `virtual_trade_plans.jsonl`.
  - status `INSUFFICIENT_SAMPLE` accepted as expected
    low-sample / low-completed-tail-label result
    (`sample_count=14<20` and
    `completed_tail_label_count=0<10`); the Regime &
    Cluster Evidence Pack correctly refused to overfit or
    force a regime / cluster conclusion when structural
    samples were insufficient. `INSUFFICIENT_SAMPLE` does
    NOT mean runtime failure; `INSUFFICIENT_SAMPLE` does
    NOT authorise strategy changes; `INSUFFICIENT_SAMPLE`
    does NOT authorise rule relaxation;
    `INSUFFICIENT_SAMPLE` does NOT authorise live trading;
    `INSUFFICIENT_SAMPLE` does NOT authorise Phase 12.
  - paper-only, no live trading, Phase 12 forbidden.
  - safety flags unchanged (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`).
  - no Binance API key.
  - no Binance API secret.
  - no signed endpoint.
  - no account / order / position / leverage / margin
    endpoint.
  - no private websocket.
  - no listenKey.
  - no DeepSeek trade decision.
  - no real Telegram outbound.
  - Phase 12 remains FORBIDDEN.

#### Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise

  - Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise
    live trading.
  - Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise
    API keys.
  - Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise
    private endpoints.
  - Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise
    DeepSeek trade decisions.
  - Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise
    real Telegram outbound.
  - Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise
    Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard
    gate.
  - Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise
    Phase 12.
  - Regime & Cluster Evidence Pack outputs remain
    paper-only / report-only / evidence-only.
  - Regime & Cluster Evidence Pack outputs cannot trigger
    orders, leverage, position sizing, stop changes, target
    changes, Risk Engine changes, or Execution FSM changes.

#### Changed

- **`docs/PROJECT_STATUS.md`** — current-phase block now
  leads with Phase 11C.1C-C-B-B-B-B = `ACCEPTED`; inline
  summary list flips B-B-B-B from `NEXT_ALLOWED /
  NOT_STARTED` to `ACCEPTED` and adds Phase
  11C.1C-C-B-B-B-C = `NEXT_ALLOWED / NOT_STARTED`
  placeholder; "does NOT authorise" block extended for
  B-B-B-B with `INSUFFICIENT_SAMPLE` explanation; per-phase
  table: new B-B-B-B (closeout) `ACCEPTED` row + new
  B-B-B-C placeholder row inserted (legacy B-B-B-B kickoff
  + implementation rows annotated `SUPERSEDED`); per-phase
  prose section converted to *ACCEPTED via PR #57
  docs-only closeout* with full operator-VPS evidence
  subsection + new B-B-B-C placeholder section.
- **`docs/PHASE_GATE.md`** — Phase 11C.1C-C-B-B-B-B row
  added to the *Closed phases* table; *Open / Reserved
  phases* table updated (B-B-B-B → `ACCEPTED — see Closed
  phases table above`, B-B-B-C → `NEXT_ALLOWED /
  NOT_STARTED` placeholder); the *Open phase: Phase
  11C.1C-C-B-B-B-B* section converted to a *Closed phase:
  Phase 11C.1C-C-B-B-B-B (ACCEPTED)* section + a *Phase
  11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10
  min WS paper smoke PASSED)* section carrying the
  verbatim runner / events.db / daily-report /
  export-bundle transcript; new *Open phase: Phase
  11C.1C-C-B-B-B-C (NEXT_ALLOWED / NOT_STARTED)* section +
  acceptance gate placeholder; legacy B-B-B-B kickoff
  sub-sections (scope / outputs / questions / principles /
  boundary / forbidden / acceptance gate placeholder) /
  removed (their content is preserved in
  `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`);
  Phase 12 forbidden row updated to mention B-B-B-B and
  B-B-B-C explicitly; *Architecture governance
  (guidance-only; no phase change)* closing paragraph
  refreshed (B-B-B-A = ACCEPTED; B-B-B-B = ACCEPTED;
  B-B-B-C = NEXT_ALLOWED / NOT_STARTED; Phase 12 =
  FORBIDDEN).
- **`docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`**
  — status banner flipped from `NEXT_ALLOWED / NOT_STARTED
  (docs-only kickoff / scope alignment)` to `ACCEPTED`;
  parent / child relationship updated to mention B-B-B-C;
  new "Phase 11C.1C-C-B-B-B-B acceptance evidence
  (operator-VPS 10 min WS paper smoke PASSED + Phase 8.5
  export bundle) — FILED via PR #57" section added.
- **`docs/CHANGELOG.md`** — *this entry*.

#### Added

- **`docs/PR57_DESCRIPTION.md`** (NEW) — describes this
  docs-only closeout PR (changed files, allowed / forbidden
  edits, confirmation checklist, acceptance evidence).

#### Forbidden by this PR (carries forward verbatim)

- Real trading.
- Live trading.
- Binance API key / secret.
- Signed endpoint / `listenKey` / private WebSocket.
- Account / order / position / leverage / margin endpoint.
- DeepSeek trade decision.
- Real Telegram outbound.
- AI deciding direction / position size / leverage / stop /
  target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- AI Learning that auto-decides trades.
- Auto-rule-relaxation on low samples.
- Risk Engine override / bypass.
- Execution FSM override / bypass.
- Phase Gate override / bypass.
- Modifying `app/`, `scripts/`, `tests/`, `configs/`,
  `risk/`, `execution/`, `llm/`, `telegram/`, or
  `exchange/`.
- Modifying configuration schemas, defaults, or YAML.
- Modifying strategy runtime code.
- Adding or modifying tests.
- Adding new Python modules.
- Adding new event types.
- Modifying runtime behavior.
- Implementing new functionality.
- Phase 11C.1C-C-B-B-B-C implementation (reserved for the
  next child slice; will require its own kickoff PR,
  brief, scope, boundary table, forbidden list, and
  acceptance evidence).
- Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard
  gate.
- Phase 12 / live trading kickoff.

#### Acceptance gate (docs-only closeout)

- Docs-only PR. **No code modified** under `app/`,
  `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
  `llm/`, `telegram/`, or `exchange/`.
- **No new Python files.**
- **No new event types.**
- **No new tests.**
- **No dry-run / smoke required** (no runtime change).
- Operator-VPS 10 min WS paper smoke evidence already
  captured pre-PR; this PR **records** the evidence in
  the ledger.
- Phase 11C.1C-C-B-B-B-B flipped to `ACCEPTED`.
- Phase 11C.1C-C-B-B-B-C introduced at `NEXT_ALLOWED /
  NOT_STARTED`.
- Safety boundary held end-to-end (`mode=paper`,
  `live_trading=False`, `exchange_live_orders=False`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no API key, no
  signed endpoint, no private WS, no `listenKey`, no
  DeepSeek trade decision, no real Telegram outbound).
- **Phase 12 remains FORBIDDEN.**

#### Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Phase 11C.1C-C-B-B-B-B (Regime & Cluster Cohort Evidence Pack v0) implementation (PR #56)

**Type:** Implementation PR (paper / report / evidence-only).
**Runtime effect:** the
:class:`StrategyValidationRuntime` now builds a
:class:`RegimeClusterEvidencePack` after every flush_report;
emits two new typed events
(``REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`` /
``REGIME_CLUSTER_COHORT_SUMMARY_GENERATED``); the Phase 11B
daily report renders a new Phase 11C.1C-C-B-B-B-B section.
**Phase ledger effect:** none — Phase 11C.1C-C-B-B-B-B
remains `NEXT_ALLOWED / NOT_STARTED` until operator-VPS
paper smoke + closeout PR. **Phase 11C.1C-C-B-B-B-A remains
`ACCEPTED`. Phase 11C.1C-C-B-B-B remains `NEXT_ALLOWED /
NOT_STARTED` (parent; unchanged definition).**
**Safety flag effect:** **none.** Every Phase 1 safety flag
held throughout the test ladder.
**Trade authority granted:** **none.**

> **This PR is paper / report / evidence only.** **NOT**
> live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning.
> **NOT** a strategy implementation. **NOT** a trading
> module. **NOT** the complete Strategy Validation Lab
> follow-up. **NOT** Phase 12.
>
> The pack's per-cohort `status` is one of
> `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` /
> `EVIDENCE_SIGNAL` and is a **descriptive label only**.
> Every artefact (`regime_cohort_summary`,
> `cluster_cohort_summary`, `score_bucket_summary`,
> `stage_outcome_summary`,
> `strategy_mode_outcome_summary`,
> `regime_cluster_evidence_pack`, `warnings`,
> `insufficient_sample_reasons`) **MUST NEVER** trigger a
> real trade or modify position size, leverage, stop-loss,
> target price, the Risk Engine, or the Execution FSM. The
> Risk Engine remains the single trade-decision gate.

#### Added

- **`app/adaptive/regime_cluster_evidence_pack.py`** (NEW)
  — Phase 11C.1C-C-B-B-B-B value objects + pure functions:
  `RegimeClusterEvidencePackStatus` (with `INSUFFICIENT_SAMPLE`
  / `OBSERVE_ONLY` / `WARNING` / `EVIDENCE_SIGNAL`),
  `RegimeClusterCohortKey`, `RegimeClusterCohortStats`,
  `RegimeClusterEvidenceRecord`,
  `RegimeClusterEvidenceInput`, `RegimeCohortSummary`,
  `ClusterCohortSummary`, `ScoreBucketSummary`,
  `StageOutcomeSummary`, `StrategyModeOutcomeSummary`,
  `RegimeClusterEvidencePack`, plus
  `build_regime_cluster_evidence_input` /
  `build_regime_cohort_summary` /
  `build_cluster_cohort_summary` /
  `build_score_bucket_summary` /
  `build_stage_outcome_summary` /
  `build_strategy_mode_outcome_summary` /
  `build_regime_cluster_evidence_pack` /
  `export_regime_cluster_evidence_payload` /
  `load_regime_cluster_evidence_payload`. Every payload
  carries `schema_version`
  (`phase_11c_1c_c_b_b_b_b.regime_cluster_evidence_pack.v1`)
  + the four canonical Phase 11C.1C-A versioning labels.
  All functions are deterministic / pure: no I/O, no clock
  read, no event emission, no network access, no API key
  read, no exchange call, no Risk Engine / Execution FSM
  mutation. Records whose `market_regime` is missing from
  the upstream snapshot safely degrade to `unknown` per the
  brief's "if a field is missing, do not raise" rule.
- **`app/core/events.py`** — two new typed `EventType`
  members: `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` and
  `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`. Both are
  paper / report / evidence only; their payloads carry
  `evidence_pack_status` (descriptive only) and the full
  identity block. Neither event is consumed by the Risk
  Engine or the Execution FSM.
- **`tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`**
  (NEW, 23 tests covering the brief's mandated cases):
  contract pin (input fields + status vocabulary + cohort
  dimensions), `INSUFFICIENT_SAMPLE` on low-total samples,
  `INSUFFICIENT_SAMPLE` on low-completed-tail-label samples,
  per-regime cohort tail-outcome counting,
  cluster-leader-vs-follower signal detection, score-bucket
  high-vs-low signal detection, stage-outcome
  missed-tail-warning detection, strategy-mode
  fake-breakout warning detection, end-to-end pack builder
  on a real `StrategyValidationDataset`,
  payload roundtrip, exportable through the Phase 8.5 zip
  bundle, replayable through `ReplayEngine`, daily-report
  contains the new section, daily-report renders even on a
  zero-event window, INSUFFICIENT-SAMPLE on empty dataset,
  Phase 1 safety flags unchanged, no live-trading
  side-effects (`ORDER_*` / `POSITION_*` / `STOP_*` /
  `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` events
  remain absent), Phase 12 remains `FORBIDDEN`,
  `regime_cluster_evidence_pack_enabled=False` disables the
  new sub-slice without affecting the parent dataset /
  quality-gate / paper-alpha-gate contracts.
- **`docs/PR56_DESCRIPTION.md`** (NEW) — describes this
  implementation PR (changed files, allowed / forbidden
  edits, test ladder, dry-run summary, safety boundary).

#### Changed

- **`app/adaptive/__init__.py`** — re-exports the new
  symbols from `regime_cluster_evidence_pack` so callers
  can use `from app.adaptive import …`.
- **`app/adaptive/strategy_validation_runtime.py`** —
  `StrategyValidationRuntimeConfig` extended with twelve
  Phase 11C.1C-C-B-B-B-B knobs (defaults match the
  module-level defaults). `StrategyValidationRuntime` gained
  `observe_market_regime(opportunity_id, market_regime)`
  helper, `latest_regime_cluster_evidence_pack` accessor,
  `regime_cluster_evidence_pack_generated_count` /
  `regime_cluster_cohort_summary_generated_count` counters,
  and a new `_build_and_emit_regime_cluster_evidence_events`
  hook that fires after the Phase 11C.1C-C-B-B-B-A Paper
  Alpha Gate evaluation. `metrics_payload()` extended with
  the new Phase 11C.1C-C-B-B-B-B aggregates so the
  daily-report builder can render the section.
- **`app/market_data_public/ws_radar_chain.py`** —
  `WSRadarChainDriver._post_chain` calls
  `strategy_validation_runtime.observe_market_regime` after
  every adaptive context is built so the evidence pack can
  attach `market_regime` per opportunity. Records whose
  regime was not observed safely degrade to
  `unknown`. The driver does NOT trigger any real trade as
  a result of this change.
- **`app/paper_run/daily_report.py`** —
  `DailyReportSnapshot` extended with the
  Phase 11C.1C-C-B-B-B-B fields
  (`regime_cluster_evidence_pack_generated_count`,
  `regime_cluster_cohort_summary_generated_count`,
  `regime_cluster_evidence_status`,
  `regime_cluster_sample_count`,
  `regime_cluster_completed_tail_label_count`,
  `regime_cluster_insufficient_sample_reasons`,
  `regime_cluster_warnings`, `regime_cluster_signals`,
  `regime_cohort_summary`, `cluster_cohort_summary`,
  `score_bucket_summary`, `stage_outcome_summary`,
  `strategy_mode_outcome_summary`,
  `regime_cluster_evidence_pack`). `to_payload()` carries
  every new field; the Markdown body renders a new
  *Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence
  Pack v0* section with the boundary banner ("paper / report
  / evidence-only", "MUST NEVER trigger a real trade",
  "Phase 12 remains FORBIDDEN") and per-cohort row
  rendering across the seven cohort dimensions.
- **`tests/unit/test_phase11b_no_network.py`** —
  `allowed_phase_11b_references` extended with the two new
  EventType labels (mirrors how PAPER_ALPHA_* were added by
  PR #52). The Phase 11B safety / no-network tests continue
  to pass.
- **`docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`**
  — implementation acceptance evidence appended (test
  ladder, dry-run summary, daily-report excerpt, schema
  version, safety-flag invariants).
- **`docs/PHASE_GATE.md`** — Phase 11C.1C-C-B-B-B-B row
  refreshed with the implementation summary (event types,
  schema version, paper-only-safety language); the slice
  remains `NEXT_ALLOWED / NOT_STARTED` until the
  operator-VPS paper smoke + closeout PR. Architecture
  governance closing paragraph refreshed to mention the new
  implementation in flight.
- **`docs/PROJECT_STATUS.md`** — current-phase block /
  per-phase table updated to record that the
  Phase 11C.1C-C-B-B-B-B implementation has shipped via
  PR #56 (paper / report / evidence only). Phase
  acceptance state for B-B-B-B is unchanged
  (`NEXT_ALLOWED / NOT_STARTED`).
- **`docs/CHANGELOG.md`** — *this entry*.

#### Verification

- `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`
  — **23/23 PASS** (brief-mandated cases).
- `tests/unit/ -k phase11c_` — **389/389 PASS** (366
  baseline + 23 new) with no regression vs. the post-PR-#55
  main baseline.
- `tests/` (full surface) — **2363/2363 PASS** with no
  regression vs. the post-PR-#55 main baseline.
- 30 s dry-run smoke produces the new evidence-pack
  section. When samples are below the configured minimums
  (the expected case for a 30 s dry-run / when the upstream
  Phase 11C.1C-C-A primary tracking window has not yet
  resolved), `regime_cluster_evidence_status` correctly
  emits `INSUFFICIENT_SAMPLE` together with explicit
  `insufficient_sample_reasons` rather than silently
  inflating signals on thin data — exactly the brief's "do
  not loosen rules on low samples" requirement.
- Real-WS 10 min smoke is **NOT required** for this PR.
  This PR is a deterministic evidence-compression layer
  over the upstream Phase 11C.1C-C-A label-tracking
  outcomes; non-empty cohort rows depend on the upstream
  primary tracking window resolving. Real non-empty cohort
  validation is reserved for the Phase 11C.1C-C-B-B-B-B
  closeout / operator-VPS run.

#### Safety boundary held

- `mode = paper`
- `live_trading = False`
- `exchange_live_orders = False`
- `right_tail = False`
- `llm = False`
- `telegram_outbound_enabled = False`
- `binance_private_api_enabled = False`
- No Binance API key
- No Binance API secret
- No signed endpoint
- No account / order / position / leverage / margin
  endpoint
- No private WebSocket
- No `listenKey`
- No DeepSeek trade decision
- No real Telegram outbound
- No `ORDER_*` / `POSITION_*` / `STOP_*` /
  `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` emitted by
  the new pipeline
- Phase 12 remains **FORBIDDEN**


### Docs-only - Phase 11C.1C-C-B-B-B-B (Regime & Cluster Cohort Evidence Pack v0) kickoff / scope alignment (PR #55)

**Type:** Docs-only kickoff / scope-alignment.
**Runtime effect:** **none.**
**Phase ledger effect:** introduces Phase 11C.1C-C-B-B-B-B
at `NEXT_ALLOWED / NOT_STARTED` as the **second child slice**
under the Phase 11C.1C-C-B-B-B parent. **No phase's
acceptance state is flipped.** Phase 11C.1C-C-B-B-B-A remains
`ACCEPTED`. Phase 11C.1C-C-B-B-B remains `NEXT_ALLOWED /
NOT_STARTED` (parent; **unchanged definition** —
*Strategy Validation Lab (deeper) & richer Cluster Exposure
Control follow-up*).
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **This PR is paper / report / evidence only.** **NOT** live
> trading. **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> strategy implementation. **NOT** a trading module. **NOT**
> the complete Strategy Validation Lab follow-up. **NOT** the
> Phase 11C.1C-C-B-B-B-B *implementation* (the implementation
> requires a separate PR; this PR is the **docs-only
> kickoff**). **NOT** Phase 12.
>
> Every artefact this slice produces — when implemented —
> (`regime_cohort_summary`, `cluster_cohort_summary`,
> `score_bucket_summary`, `stage_outcome_summary`,
> `strategy_mode_outcome_summary`,
> `regime_cluster_evidence_pack`, `warnings`,
> `insufficient_sample_reasons`) will be a **descriptive
> label** for human review only. Outputs **MUST NEVER**
> trigger a real trade or modify position size, leverage,
> stop-loss, target price, the Risk Engine, or the Execution
> FSM. The Risk Engine remains the single trade-decision
> gate.

#### Added

- **`docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`**
  (NEW) — *Phase 11C.1C-C-B-B-B-B — Regime & Cluster Cohort
  Evidence Pack v0 (docs-only kickoff)* / *Regime 与 Cluster
  分组证据包 v0*. Records the parent / child relationship
  (Phase 11C.1C-C-B-B-B-B is the **second child slice**
  under Phase 11C.1C-C-B-B-B; the parent phase is **not**
  renamed), the scope (read-only / evidence-only compression
  layer that organises upstream artefacts into cohort
  summaries by Regime, Cluster, Stage, Strategy Mode, and
  Score Bucket), the inputs the slice reads (Phase
  11C.1C-C-A label-tracking outcomes, Phase 11C.1C-C-B-A
  validation samples / cluster exposure assessments, Phase
  11C.1C-C-B-B-A validation dataset / quality gate, Phase
  11C.1C-C-B-B-B-A Paper Alpha Gate verdict), the **allowed
  outputs** (`regime_cohort_summary`,
  `cluster_cohort_summary`, `score_bucket_summary`,
  `stage_outcome_summary`, `strategy_mode_outcome_summary`,
  `regime_cluster_evidence_pack`, `warnings`,
  `insufficient_sample_reasons`), the **eight questions to
  be answered by cohort evidence**, the **core principles**
  (add fewer modules / accumulate more structural data;
  verify Regime more / talk less about strategy; prove which
  states carry right-tail value; replayable; reduces human
  interpretation cost; serves Regime / Liquidity / Right
  Tail judgement; forbid unverifiable AI output; forbid
  system-complexity growth; forbid loosening rules on low
  samples), the **boundary table** (Phase 1 safety lock +
  outputs-are-descriptive-only invariants), the **forbidden
  list** (inherited verbatim + slice-specific items), and
  the **acceptance-gate placeholder** for the implementation
  PR.
- **`docs/PR55_DESCRIPTION.md`** (NEW) — describes this
  docs-only kickoff PR (changed files, allowed / forbidden
  edits, confirmation checklist).

#### Changed

- **`docs/PHASE_GATE.md`** — *Open / Reserved phases* table
  Phase 11C.1C-C-B-B-B-B row redefined from "Next child
  slice (placeholder; not yet defined)" to *Regime & Cluster
  Cohort Evidence Pack v0 (paper / report / evidence-only
  second child slice under Phase 11C.1C-C-B-B-B; docs-only
  kickoff via PR #55)* with full scope language,
  allowed-outputs list, and inherited-forbidden-list
  reference. *Reserved phase: Phase 11C.1C-C-B-B-B-B*
  section converted to *Open phase: Phase 11C.1C-C-B-B-B-B
  (NEXT_ALLOWED / NOT_STARTED)* with full scope, the eight
  cohort questions, the core principles, the boundary
  table, the inherited forbidden list, and the
  acceptance-gate placeholder. *Architecture governance
  (guidance-only; no phase change)* closing paragraph
  refreshed to reflect the current open-phase state (B-B-A
  = ACCEPTED; B-B-B = NEXT_ALLOWED / NOT_STARTED; B-B-B-A
  = ACCEPTED; B-B-B-B = NEXT_ALLOWED / NOT_STARTED; Phase
  12 = FORBIDDEN).
- **`docs/PROJECT_STATUS.md`** — current-phase block
  B-B-B-B line refreshed with the new defined name (Regime
  & Cluster Cohort Evidence Pack v0 / Regime 与 Cluster 分组
  证据包 v0), the docs-only-kickoff scope, and the
  paper / report / evidence-only safety language.
  Per-phase table B-B-B-B row redefined with full scope,
  allowed outputs, eight cohort questions, core principles,
  and the inherited forbidden list reference. The B-B-B-B
  prose subsection rewritten to record positioning under
  AMOS, allowed outputs, the eight cohort questions, the
  core principles, and the slice-specific forbidden items.
- **`docs/CHANGELOG.md`** — *this entry*.

#### Phase 11C.1C-C-B-B-B-B exists to make the following questions answerable from data

  1. Which Regimes are more likely to produce
     `strong_tail` / `reached_3r` / `reached_5r`?
  2. Which Regimes are more likely to produce
     `fake_breakout` / `late_chase_failure`?
  3. Is the `cluster_leader` materially better than its
     followers on the same cohort?
  4. Does the high `opportunity_score_bucket` actually
     out-perform the low bucket?
  5. Does the high `early_tail_score_bucket` actually
     out-perform the low bucket?
  6. Do `follow` / `pullback` / `observe` / `reject`
     downstream outcomes match expectations?
  7. Which state combinations deserve continued paper
     observation?
  8. Which state combinations must be down-weighted or
     rejected?

#### Phase 11C.1C-C-B-B-B-B core principles (carried forward verbatim)

  - Add fewer modules; accumulate more structural data.
  - Talk less about "strategy"; verify Regime more.
  - Stop chasing a universal model; prove which states
    really carry right-tail value.
  - All new content must be replayable.
  - All new content must reduce the human-interpretation
    cost.
  - All new content must serve Regime / Liquidity / Right
    Tail judgement.
  - Forbid unverifiable AI output.
  - Forbid system-complexity growth.
  - Forbid loosening rules on low samples.

#### Allowed outputs (paper / report / evidence-only)

Each is a **descriptive label only**. None has trade
authority. None is read by the Risk Engine or the Execution
FSM:

  - `regime_cohort_summary`
  - `cluster_cohort_summary`
  - `score_bucket_summary`
  - `stage_outcome_summary`
  - `strategy_mode_outcome_summary`
  - `regime_cluster_evidence_pack`
  - `warnings`
  - `insufficient_sample_reasons`

#### Forbidden by this PR (carries forward verbatim + slice-specific items)

- Real trading.
- Live trading.
- Binance API key / secret.
- Signed endpoint / `listenKey` / private WebSocket.
- Account / order / position / leverage / margin endpoint.
- DeepSeek trade decision.
- Real Telegram outbound.
- AI deciding direction / position size / leverage / stop /
  target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- AI Learning that auto-decides trades.
- Auto-rule-relaxation on low samples.
- Risk Engine override / bypass.
- Execution FSM override / bypass.
- Phase Gate override / bypass.
- Triggering a real trade from any evidence-pack output.
- Modifying position size / leverage / stop-loss / target
  price from any evidence-pack output.
- Modifying the Risk Engine or the Execution FSM from any
  evidence-pack output.
- Replacing the Paper Alpha Gate v0 verdict with
  evidence-pack output (the evidence pack is *additive*,
  not a replacement).
- Implementing the Regime & Cluster Cohort Evidence Pack v0
  (this PR is docs-only; the implementation lands in a
  separate PR after this kickoff is reviewed).
- Implementing the complete Strategy Validation Lab
  follow-up (reserved for later child slices under Phase
  11C.1C-C-B-B-B).
- Adding new Python modules under `app/`.
- Adding new event types.
- Modifying `app/`, `scripts/`, `tests/`, `configs/`,
  `risk/`, `execution/`, `llm/`, `telegram/`, or
  `exchange/`.
- Modifying configuration schemas, defaults, or YAML.
- Adding or modifying tests.
- Modifying strategy runtime code.
- Modifying runtime behavior.
- Implementing new functionality.
- Flipping any phase's acceptance state. Phase
  11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
  11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
  Phase 11C.1C-C-B-B-B-B is introduced at `NEXT_ALLOWED /
  NOT_STARTED`. Phase 12 remains `FORBIDDEN`.
- Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps its
  existing definition — *Strategy Validation Lab (deeper) &
  richer Cluster Exposure Control follow-up*.
- Phase 11C.1C-C-B-B-B-B implementation (out of scope for
  this kickoff PR).
- Phase 12 / live trading kickoff.

#### Acceptance gate (docs-only)

- Docs-only PR. **No code modified** under `app/`,
  `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
  `llm/`, `telegram/`, or `exchange/`.
- **No new Python files.**
- **No new event types.**
- **No new tests.**
- **No dry-run / smoke required** (no runtime change).
- **No phase acceptance state flipped.**
- Safety boundary held end-to-end (`mode=paper`,
  `live_trading=False`, `exchange_live_orders=False`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no API key, no
  signed endpoint, no private WS, no `listenKey`, no
  DeepSeek trade decision, no real Telegram outbound).
- **Phase 12 remains FORBIDDEN.**

#### Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Phase 11C.1C-C-B-B-B-A accepted - Paper Alpha Gate v0 docs-only closeout (PR #54)

**Type:** Docs-only closeout / acceptance flip.
**Runtime effect:** **none.**
**Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-A from
`MERGED / AWAITING_OPERATOR_VPS_EVIDENCE / CLOSEOUT_PENDING`
to `ACCEPTED`; flips Phase 11C.1C-C-B-B-B-B from `BLOCKED /
NOT_STARTED` to `NEXT_ALLOWED / NOT_STARTED`.
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **Status: ACCEPTED (closed 2026-05-24; PR #52 merged into
> `main` on 2026-05-24, mergeCommit `f8ba315`; this docs-only
> closeout PR #54 records the operator-VPS paper evidence
> that flips Phase 11C.1C-C-B-B-B-A to `ACCEPTED`).** Paper
> Alpha Gate v0 — first child slice under the Phase
> 11C.1C-C-B-B-B parent — paper / report / evidence only.
> **NOT** live trading. **NOT** AI Learning. **NOT**
> automatic parameter optimisation. **NOT** reinforcement
> learning. **NOT** the complete Strategy Validation Lab
> follow-up. **NOT** Phase 12.

#### Phase 11C.1C-C-B-B-B-A accepted (closeout summary)

  - Paper Alpha Gate v0 implementation merged (PR #52
    merged into `main` on 2026-05-24, mergeCommit
    `f8ba315`).
  - operator-VPS 10 min WS paper smoke evidence recorded
    (`duration_seconds=600.0`, `uptime≈608s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`).
  - Paper Alpha Gate daily report section verified
    (`"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"`;
    `paper_alpha_gate_status=INCONCLUSIVE`,
    `paper_alpha_gate_sample_count=20`,
    `reason=completed_tail_label_count_below_min=0<10`).
  - `PAPER_ALPHA_*` events verified
    (`PAPER_ALPHA_GATE_EVALUATED=1`,
    `PAPER_ALPHA_RULE_EVALUATED=9`,
    `PAPER_ALPHA_COHORT_EVALUATED=6`,
    `PAPER_ALPHA_REPORT_GENERATED=1`).
  - export package generated and verified
    (`export_test_data=OK`,
    `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip`,
    `manifest_event_count=1572`,
    `redaction_applied=True`,
    `events.jsonl` exists,
    `EXPORT_PAPER_ALPHA_GATE_CHECK=PASS`).
  - export contains `PAPER_ALPHA_*` events.
  - export package files observed: `manifest.json`,
    `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`, `virtual_trade_plans.jsonl`.
  - status `INCONCLUSIVE` accepted as expected
    low-completed-label result
    (`completed_tail_label_count=0<10`); the Paper Alpha
    Gate correctly refused to overfit or force a `PASS`
    when completed tail labels were insufficient.
    `INCONCLUSIVE` does NOT mean runtime failure;
    `INCONCLUSIVE` does NOT authorise strategy changes;
    `INCONCLUSIVE` does NOT authorise live trading;
    `INCONCLUSIVE` does NOT authorise Phase 12.
  - paper-only, no live trading, Phase 12 forbidden.
  - safety flags unchanged (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`).
  - no Binance API key.
  - no Binance API secret.
  - no signed endpoint.
  - no account / order / position / leverage / margin
    endpoint.
  - no private websocket.
  - no listenKey.
  - no DeepSeek trade decision.
  - no real Telegram outbound.
  - Phase 12 remains FORBIDDEN.

#### Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise

  - Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise
    live trading.
  - Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise
    API keys.
  - Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise
    private endpoints.
  - Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise
    DeepSeek trade decisions.
  - Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise
    real Telegram outbound.
  - Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise
    Phase 12.
  - Paper Alpha Gate verdicts remain paper-only /
    report-only / evidence-only.
  - Paper Alpha Gate verdicts cannot trigger orders,
    leverage, position sizing, stop changes, target changes,
    Risk Engine changes, or Execution FSM changes.

#### Changed

- **`docs/PROJECT_STATUS.md`** — Phase 11C.1C-C-B-B-B-A row
  flipped from `MERGED / AWAITING_OPERATOR_VPS_EVIDENCE /
  CLOSEOUT_PENDING` to `ACCEPTED`; Phase 11C.1C-C-B-B-B-B
  flipped from `BLOCKED / NOT_STARTED` to `NEXT_ALLOWED /
  NOT_STARTED`; current-phase block refreshed; per-phase
  prose updated; new acceptance-evidence subsection added.
- **`docs/PHASE_GATE.md`** — Phase 11C.1C-C-B-B-B-B-A row
  added to the *Closed phases* table; *Open / Reserved
  phases* table updated (B-B-B-A → `ACCEPTED`, B-B-B-B →
  `NEXT_ALLOWED / NOT_STARTED`); the *Open phase: Phase
  11C.1C-C-B-B-B-A* section converted to a
  *Closed phase: Phase 11C.1C-C-B-B-B-A (ACCEPTED)*
  section; *Required operator-VPS paper evidence* section
  replaced with a *Phase 11C.1C-C-B-B-B-A acceptance gate
  (post-merge; operator-VPS evidence filed via PR #54)*
  section + a *Phase 11C.1C-C-B-B-B-A acceptance evidence
  (operator-VPS 10 min WS paper smoke PASSED)* section
  carrying the verbatim runner / events.db / daily-report /
  export-bundle transcript; *Reserved phase: Phase
  11C.1C-C-B-B-B-B* section updated to `NEXT_ALLOWED /
  NOT_STARTED`; Phase 12 forbidden row updated.
- **`docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`** —
  status banner flipped from `MERGED /
  AWAITING_OPERATOR_VPS_EVIDENCE / CLOSEOUT_PENDING` to
  `ACCEPTED`; new "Phase 11C.1C-C-B-B-B-A acceptance
  evidence (operator-VPS 10 min WS paper smoke PASSED)"
  section added; "Required operator-VPS paper evidence
  before closeout `ACCEPTED`" section replaced with a
  "filed via PR #54" record.
- **`docs/CHANGELOG.md`** — *this entry*.

#### Added

- **`docs/PR54_DESCRIPTION.md`** (NEW) — describes this
  docs-only closeout PR (changed files, allowed / forbidden
  edits, confirmation checklist, acceptance evidence).

#### Forbidden by this PR (carries forward verbatim)

- Real trading.
- Live trading.
- Binance API key / secret.
- Signed endpoint / `listenKey` / private WebSocket.
- Account / order / position / leverage / margin endpoint.
- DeepSeek trade decision.
- Real Telegram outbound.
- AI deciding direction / position size / leverage / stop /
  target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- AI Learning that auto-decides trades.
- Risk Engine override / bypass.
- Execution FSM override / bypass.
- Phase Gate override / bypass.
- Modifying `app/`, `scripts/`, `tests/`, `configs/`,
  `risk/`, `execution/`, `llm/`, `telegram/`, or
  `exchange/`.
- Modifying configuration schemas, defaults, or YAML.
- Adding or modifying tests.
- Adding new Python modules.
- Adding new event types.
- Modifying runtime behavior.
- Implementing new functionality.
- Phase 11C.1C-C-B-B-B-B implementation (reserved for the
  next child slice; will require its own kickoff PR,
  brief, scope, boundary table, forbidden list, and
  acceptance evidence).
- Phase 12 / live trading kickoff.

#### Acceptance gate (docs-only closeout)

- Docs-only PR. **No code modified** under `app/`,
  `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
  `llm/`, `telegram/`, or `exchange/`.
- **No new Python files.**
- **No new event types.**
- **No new tests.**
- **No dry-run / smoke required** (no runtime change).
- Operator-VPS 10 min WS paper smoke evidence already
  captured pre-PR; this PR **records** the evidence in the
  ledger.
- Phase 11C.1C-C-B-B-B-A flipped to `ACCEPTED`.
- Phase 11C.1C-C-B-B-B-B flipped to `NEXT_ALLOWED /
  NOT_STARTED`.
- Safety boundary held end-to-end (`mode=paper`,
  `live_trading=False`, `exchange_live_orders=False`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no API key, no
  signed endpoint, no private WS, no `listenKey`, no
  DeepSeek trade decision, no real Telegram outbound).
- **Phase 12 remains FORBIDDEN.**

#### Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 (implementation; PR #52 merged)

**Version:** `1.4.0a11c.1c.c.b.b.b.a` - Phase 11C.1C-C-B-B-B-A.
Tracks the **paper / report / evidence-only first child
slice** under Phase 11C.1C-C-B-B-B (Paper Alpha Gate v0).
Ships `app/adaptive/paper_alpha_gate.py` (pure-function
module + value-object models + nine pure functions), four
new typed events, the `StrategyValidationRuntime` extension
that emits the gate verdict on the same flush as the
dataset / quality-gate emission, and the new "Phase
11C.1C-C-B-B-B-A Paper Alpha Gate v0" section in the Phase
11B daily report.

> **Status: MERGED / AWAITING_OPERATOR_VPS_EVIDENCE /
> CLOSEOUT_PENDING (PR #52 merged into `main` on 2026-05-24,
> mergeCommit `f8ba315`; branch
> `feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`).**
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** the
> complete Strategy Validation Lab follow-up. **NOT** Phase
> 12.
>
> The Paper Alpha Gate v0 implementation is now on `main` —
> but Phase 11C.1C-C-B-B-B-A is **not yet `ACCEPTED`**.
> Closeout to `ACCEPTED` requires a separate docs-only
> closeout PR carrying **operator-VPS paper evidence** (see
> "Acceptance gate (post-merge; operator-VPS evidence
> required)" below). Phase 11C.1C-C-B-B-B-B (the next child
> slice) is therefore `BLOCKED / NOT_STARTED` until that
> closeout merges.
>
> The `paper_alpha_gate_status` field on every
> `PAPER_ALPHA_GATE_EVALUATED` event (`PASS` / `WARN` /
> `FAIL` / `INCONCLUSIVE`) is a **descriptive label** for
> human review and **MUST NEVER trigger a real trade**,
> **MUST NEVER** modify position size, leverage, stop-loss,
> target price, the Risk Engine, or the Execution FSM. The
> Risk Engine remains the single trade-decision gate.

#### Added

- **`app/adaptive/paper_alpha_gate.py`** — new pure-function
  module:
  - Models: `PaperAlphaGateStatus` (string-constant holder
    for `PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`),
    `PaperAlphaGateRule`,
    `PaperAlphaGateRuleResult`,
    `PaperAlphaGateCohortResult`,
    `PaperAlphaGateInput`,
    `PaperAlphaGateReport`.
  - Pure functions:
    `build_paper_alpha_gate_input`,
    `evaluate_paper_alpha_gate`,
    `evaluate_strategy_mode_alpha`,
    `evaluate_candidate_stage_alpha`,
    `evaluate_score_bucket_alpha`,
    `evaluate_cluster_alpha`,
    `build_paper_alpha_gate_report`,
    `export_paper_alpha_gate_payload`,
    `load_paper_alpha_gate_payload`.
  - Schema version
    `phase_11c_1c_c_b_b_b_a.paper_alpha_gate.v1`.
  - The evaluator is **deterministic**. Identical inputs
    always yield identical outputs. No I/O, no clock read,
    no `EventRepository.append_event` call.
- **Four new `EventType` values** in `app/core/events.py`:
  `PAPER_ALPHA_GATE_EVALUATED`,
  `PAPER_ALPHA_RULE_EVALUATED`,
  `PAPER_ALPHA_COHORT_EVALUATED`,
  `PAPER_ALPHA_REPORT_GENERATED`. Every payload carries the
  brief-mandated identity block (`schema_version`,
  `paper_alpha_gate_version`, `source_phase`, `report_id`,
  `dataset_id`, `timestamp`, `gate_status`,
  `strategy_version`, `scoring_version`,
  `risk_config_version`, `state_machine_version`).
- **`StrategyValidationRuntime`** extended:
  - `flush_report()` now also runs Paper Alpha Gate v0 on
    the same flush as the dataset / quality-gate emission
    (only when the dataset was built; otherwise the alpha
    gate is skipped — there is no input to evaluate).
  - New runtime properties:
    `latest_paper_alpha_report`,
    `paper_alpha_gate_evaluated_count`,
    `paper_alpha_rule_evaluated_count`,
    `paper_alpha_cohort_evaluated_count`,
    `paper_alpha_report_generated_count`.
  - `metrics_payload()` exposes the new
    `paper_alpha_*` fields (status, reasons, warnings,
    sample count, per-cohort results, warning / signal
    counts, full report payload).
- **`StrategyValidationRuntimeConfig`** extended with
  `paper_alpha_gate_enabled` (default `True`) and 8
  `paper_alpha_*` thresholds; `from_settings_section()` and
  `from_mapping()` honour all of them. Setting
  `paper_alpha_gate_enabled=False` disables the new
  sub-slice without affecting the parent dataset /
  quality-gate contract.
- **Daily report**:
  - `DailyReportSnapshot` extended with
    `paper_alpha_gate_evaluated_count`,
    `paper_alpha_rule_evaluated_count`,
    `paper_alpha_cohort_evaluated_count`,
    `paper_alpha_report_generated_count`,
    `paper_alpha_gate_status`,
    `paper_alpha_gate_reasons`,
    `paper_alpha_gate_warnings`,
    `paper_alpha_gate_sample_count`,
    `paper_alpha_strategy_mode_results`,
    `paper_alpha_candidate_stage_results`,
    `paper_alpha_score_bucket_results`,
    `paper_alpha_cluster_results`,
    `paper_alpha_missed_alpha_warnings`,
    `paper_alpha_late_chase_warnings`,
    `paper_alpha_follow_risk_warnings`,
    `paper_alpha_leader_preference_signals`,
    `paper_alpha_gate_report`.
  - `DailyReportBuilder.build()` cross-checks the runner
    counters against the events.db type-counts of the four
    new event types so a stale runner counter cannot
    under-report.
  - New Markdown section "Phase 11C.1C-C-B-B-B-A Paper
    Alpha Gate v0" with explicit "the
    `paper_alpha_gate_status` is a descriptive label and
    **MUST NEVER trigger a real trade** and **MUST NEVER**
    modify position size, leverage, stop-loss, target
    price, the Risk Engine, or the Execution FSM. Phase 12
    remains FORBIDDEN" disclaimer.
- **Tests**:
  - `tests/unit/test_phase11c_1c_c_b_b_b_a_paper_alpha_gate.py`
    — 27 brief-mandated cases covering input contract,
    status vocabulary, cohort dimensions, rule definition,
    INCONCLUSIVE on low samples, INCONCLUSIVE/FAIL on QG
    fail, missed_alpha / late_chase / follow_risk warnings,
    high score bucket signal, early tail bucket signal
    (positive + negative), cluster leader signal,
    deterministic, `build_paper_alpha_gate_input` from
    upstream artefacts, payload roundtrip, legacy payload
    tolerance, non-mapping rejected, runtime emits the four
    events, export bundle carries them, replay accepts
    them, daily report metrics + Markdown, empty-state
    INCONCLUSIVE, Phase 1 safety flags unchanged, no
    execution events emitted, Phase 12 forbidden, runtime
    config knob disables the gate.
  - `tests/unit/test_phase11b_no_network.py` allow-list
    extended with the four new event types.
- **Docs**:
  - `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md` —
    docs-only kickoff document (PR #51) replaced with full
    IN_REVIEW spec.
  - `docs/PR52_DESCRIPTION.md` (NEW).
  - `docs/PROJECT_STATUS.md` updated with Phase
    11C.1C-C-B-B-B-A IN_REVIEW.
  - `docs/PHASE_GATE.md` updated with the open phase entry.

#### Changed

- **`StrategyValidationRuntime._build_metrics_payload()`**
  emits the new `paper_alpha_*` block; the empty-payload
  branch in `metrics_payload()` mirrors the structure so the
  daily-report builder can render the new section even when
  no Paper Alpha Gate report has been built yet.

#### Forbidden by this PR

- Real trading.
- Binance private API / signed endpoint / listenKey /
  private WebSocket.
- LLM / DeepSeek trade decision.
- Real Telegram outbound.
- Right-tail score in production scope.
- `paper_alpha_gate_status` triggering real downstream
  execution.
- `paper_alpha_gate_status` modifying position size,
  leverage, stop-loss, target price, the Risk Engine, or
  the Execution FSM.
- AI deciding direction / position size / leverage /
  stop-loss / target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- Risk Engine override (the Risk Engine remains the single
  trade-decision gate).
- Execution FSM override.
- Phase 11C.1C-C-B-B-B-B implementation (reserved for the
  next child slice).
- Complete Strategy Validation Lab follow-up.
- Phase 12 / live trading kickoff.

#### Acceptance gate (post-merge; operator-VPS evidence required before `ACCEPTED`)

PR #52 merged into `main` on 2026-05-24 (mergeCommit
`f8ba315`). The merge does **not** flip Phase
11C.1C-C-B-B-B-A to `ACCEPTED`. Phase 11C.1C-C-B-B-B-A is
recorded as `MERGED / AWAITING_OPERATOR_VPS_EVIDENCE /
CLOSEOUT_PENDING` until a separate docs-only closeout PR
files the operator-VPS paper evidence below (mirroring the
PR #36 → PR #37, PR #38 → PR #39, PR #40 → PR #41, PR #42
→ PR #43, PR #44 → PR #50 docs-only closeout pattern).

Test ladder on the PR branch (already met):

- 27 brief-mandated tests PASS
  (`tests/unit/test_phase11c_1c_c_b_b_b_a_paper_alpha_gate.py`).
- `tests/unit -k phase11c_` PASS (366 = 339 baseline + 27).
- Full `tests/` PASS (2340 = 2313 baseline + 27, no
  regression vs. post-PR-#51 main).
- 30 s dry-run smoke produces an `INCONCLUSIVE` Paper Alpha
  Gate report (the upstream `validation_quality_gate_status=fail`
  because samples are necessarily in-flight in a 30 s
  window — exactly the brief's "sample-insufficient ⇒
  auditable INCONCLUSIVE" requirement).
- Real WS 10 min smoke is **NOT required** for the
  implementation PR (per the brief: this slice is the Paper
  Alpha Gate contract + deterministic evaluation layer;
  non-empty sample verification is reserved for the
  closeout-to-`ACCEPTED` PR).

Required operator-VPS paper evidence before
closeout-to-`ACCEPTED` (still pending):

- `paper_alpha_gate_status` (verbatim from the daily
  report; one of `PASS` / `WARN` / `FAIL` /
  `INCONCLUSIVE`)
- `paper_alpha_gate_sample_count`
- `PAPER_ALPHA_GATE_EVALUATED` event count (runner snapshot
  + events.db type-count cross-check, after shutdown flush)
- `PAPER_ALPHA_RULE_EVALUATED` event count (runner snapshot
  + events.db type-count cross-check, after shutdown flush)
- `PAPER_ALPHA_COHORT_EVALUATED` event count (runner
  snapshot + events.db type-count cross-check, after
  shutdown flush)
- `PAPER_ALPHA_REPORT_GENERATED` event count (runner
  snapshot + events.db type-count cross-check, after
  shutdown flush)
- the daily-report "Phase 11C.1C-C-B-B-B-A Paper Alpha
  Gate v0" section (verbatim Markdown excerpt)
- export bundle / replay readability check, where
  available (the four new event types must round-trip
  through the Phase 8.5 export bundle and the Phase 10A
  replay engine)
- safety flags unchanged across the operator-VPS run
  (`live_trading=False`, `exchange_live_orders=False`,
  `trading_mode_paper=True`, `right_tail=False`,
  `llm=False`, `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no Binance API key,
  no Binance API secret, no signed endpoint, no
  account / order / position / leverage / margin endpoint,
  no private WebSocket, no `listenKey`, no DeepSeek trade
  decision, no real Telegram outbound)
- Phase 12 remains FORBIDDEN

Until that operator-VPS paper evidence is filed and merged
in a separate docs-only closeout PR, Phase 11C.1C-C-B-B-B-A
stays `MERGED / AWAITING_OPERATOR_VPS_EVIDENCE /
CLOSEOUT_PENDING` and Phase 11C.1C-C-B-B-B-B stays `BLOCKED
/ NOT_STARTED`. **No next runtime feature is authorised by
this status repair.**

#### Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Docs-only - Phase 11C.1C-C-B-B-B-A (Paper Alpha Gate v0) kickoff / scope alignment (guidance-only)

**Type:** Docs-only kickoff / scope-alignment.
**Runtime effect:** **none.**
**Phase ledger effect:** introduces Phase 11C.1C-C-B-B-B-A
at `NEXT_ALLOWED / NOT_STARTED` as the **first child slice**
under the Phase 11C.1C-C-B-B-B parent. **No phase's
acceptance state is flipped.** Phase 11C.1C-C-B-B-A remains
`ACCEPTED`. Phase 11C.1C-C-B-B-B remains `NEXT_ALLOWED /
NOT_STARTED` (parent; **unchanged definition** —
*Strategy Validation Lab (deeper) & richer Cluster Exposure
Control follow-up*).
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

> **This PR is paper / report only.** **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** the
> complete Strategy Validation Lab follow-up. **NOT** Phase
> 12. **NOT** the Paper Alpha Gate v0 implementation —
> Paper Alpha Gate v0 is **NOT implemented by Phase
> 11C.1C-C-B-B-A**, **NOT implemented by this kickoff PR**,
> and may only start as the Phase 11C.1C-C-B-B-B-A child
> slice after this docs-only kickoff is reviewed and a
> separate implementation PR is reviewed and merged.
>
> The Paper Alpha Gate v0 verdict, when implemented, will
> be a descriptive label (`PASS` / `WARN` / `FAIL` /
> `INCONCLUSIVE`) for human review only. The verdict
> **MUST NEVER** trigger a real trade or modify position
> size, leverage, stop-loss, target price, the Risk
> Engine, or the Execution FSM. The Risk Engine remains
> the single trade-decision gate.

#### Added

- **`docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`** (NEW)
  — *Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0 (docs-only
  kickoff)*. Records the parent / child relationship
  (Phase 11C.1C-C-B-B-B-A is the first child slice under
  Phase 11C.1C-C-B-B-B; the parent phase is **not**
  renamed), the scope (paper-only / report-only consumer of
  the existing Phase 11C.1C-C-B-B-A `StrategyValidationDataset`
  / `StrategyValidationQualityGate` /
  `StrategyValidationReport` artefacts; descriptive verdict
  `PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`; no execution
  surface reads the verdict), the explicit non-scope (NOT
  live trading, NOT AI Learning, NOT automatic parameter
  optimisation, NOT reinforcement learning, NOT the complete
  Strategy Validation Lab follow-up, NOT a strategy quality /
  profitability oracle, NOT a position-sizing / leverage /
  stop-loss / target-price modifier, NOT a Risk Engine /
  Execution FSM / Phase Gate override, NOT a path into Phase
  12, NOT a real-trade authority of any kind), the boundary
  table (Phase 1 safety lock + verdict-is-descriptive-only
  invariants), and the explicitly-forbidden list (inherited
  verbatim).
- **`docs/PR51_DESCRIPTION.md`** (NEW) — describes this
  docs-only kickoff PR (changed files, allowed / forbidden
  edits, confirmation checklist).
- **`docs/PHASE_GATE.md`** — added a new
  *Open phase: Phase 11C.1C-C-B-B-B-A (NEXT_ALLOWED /
  NOT_STARTED)* section after the existing Phase
  11C.1C-C-B-B-B section; added a new B-B-B-A row to the
  *Open / Reserved phases* table; refined the "Paper Alpha
  Gate v0" boundary lines in the Phase 11C.1C-C-B-B-A and
  Phase 11C.1C-C-B-B-B tables and forbidden lists to be
  more precise (Paper Alpha Gate v0 is NOT implemented by
  Phase 11C.1C-C-B-B-A; Paper Alpha Gate v0 may only start
  as Phase 11C.1C-C-B-B-B-A after this docs-only kickoff
  and a separate implementation PR; Paper Alpha Gate v0
  remains paper-only / report-only and grants no trade
  authority); refreshed the
  *Architecture governance (guidance-only; no phase change)*
  closing paragraph to reflect the current open-phase state
  (B-B-A = ACCEPTED; B-B-B = NEXT_ALLOWED / NOT_STARTED;
  B-B-B-A = NEXT_ALLOWED / NOT_STARTED; Phase 12 =
  FORBIDDEN). Phase 12 row updated to mention Phase
  11C.1C-C-B-B-B-A in the "NOT permitted from any Phase
  11C sub-phase alone" list.
- **`docs/PROJECT_STATUS.md`** — added a Phase
  11C.1C-C-B-B-B-A row to the per-phase table; added a new
  subsection
  *Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0 (first
  child slice; docs-only kickoff)* under the existing
  *Open phase: Phase 11C.1C-C-B-B-B* prose; refined the
  parent B-B-B row to clarify the parent is **not** renamed;
  refined the "Paper Alpha Gate v0" bullet items to be more
  precise; added a Current-phase quick-reference line for
  Phase 11C.1C-C-B-B-B-A.

#### Forbidden by this PR (carries forward verbatim)

- Real trading.
- Live trading.
- Binance API key / secret.
- Signed endpoint / `listenKey` / private WebSocket.
- Account / order / position / leverage / margin endpoint.
- DeepSeek trade decision.
- Real Telegram outbound.
- AI deciding direction / position size / leverage / stop /
  target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- AI Learning that auto-decides trades.
- Risk Engine override / bypass.
- Execution FSM override / bypass.
- Phase Gate override / bypass.
- Implementing Paper Alpha Gate v0 (this PR is docs-only;
  the implementation lands in a separate PR that opens
  Phase 11C.1C-C-B-B-B-A as the first child slice under
  Phase 11C.1C-C-B-B-B).
- Implementing the complete Strategy Validation Lab
  follow-up (reserved for later child slices under Phase
  11C.1C-C-B-B-B).
- Adding new Python modules under `app/`.
- Adding new event types.
- Modifying `app/`, `scripts/`, `tests/`, `configs/`,
  `risk/`, `execution/`, `llm/`, `telegram/`, or
  `exchange/`.
- Modifying configuration schemas, defaults, or YAML.
- Adding or modifying tests.
- Flipping any phase's acceptance state. Phase
  11C.1C-C-B-B-A remains `ACCEPTED`. Phase 11C.1C-C-B-B-B
  remains `NEXT_ALLOWED / NOT_STARTED`. Phase
  11C.1C-C-B-B-B-A is introduced at `NEXT_ALLOWED /
  NOT_STARTED`. Phase 12 remains `FORBIDDEN`.
- Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps its
  existing definition — *Strategy Validation Lab (deeper) &
  richer Cluster Exposure Control follow-up*.
- Phase 11C.1C-C-B-B-B-A implementation (out of scope for
  this kickoff PR).
- Phase 12 / live trading kickoff.

#### Acceptance gate (docs-only)

- Docs-only PR. **No code modified** under `app/`,
  `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
  `llm/`, `telegram/`, or `exchange/`.
- **No new Python files.**
- **No new event types.**
- **No new tests.**
- **No dry-run / smoke required** (no runtime change).
- **No phase acceptance state flipped.**
- Safety boundary held end-to-end (`mode=paper`,
  `live_trading=False`, `exchange_live_orders=False`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no API key, no
  signed endpoint, no private WS, no `listenKey`, no
  DeepSeek trade decision, no real Telegram outbound).
- **Phase 12 remains FORBIDDEN.**

#### Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Docs-only - AMA-RT Adaptive Market Operating System Governance (guidance-only)

**Type:** Docs-only governance addition.
**Runtime effect:** **none.**
**Phase ledger effect:** **none.**
**Safety flag effect:** **none.**
**Trade authority granted:** **none.**

#### Added

- **`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`** (NEW)
  — *AMA-RT Adaptive Market Operating System Governance /
  自适应市场操作系统架构治理文档.* Long-term architecture
  governance document recording:
  - **Core positioning**: AMA-RT is **not** an auto-trading
    bot; AMA-RT is an Adaptive Market Operating System.
  - **Core philosophy**: market is a dynamic adversarial
    system; no fixed strategy is permanently valid; system
    researches capital absorption / liquidity / market
    structure rather than raw price prediction; candles can
    be induced, real fills / volume / OI / funding / spread
    / depth / liquidation / spot-perp divergence are closer
    to truth.
  - **AI authority boundary** (forever): AI / LLM may do
    market explanation, narrative interpretation, regime
    interpretation, structural anomaly explanation,
    replay / reflection summarisation, and evidence
    compression. AI / LLM **MUST NEVER** place an order,
    close a position, modify leverage, modify size, modify
    stop-loss, modify target, bypass the Risk Engine,
    bypass the Execution FSM, bypass the Phase Gate,
    trigger a real trade, or treat its own text as a
    training fact.
  - **Stateless AI cognition**: AI inference must be
    stateless; chat history is not a fact source; previous
    assistant responses are not facts; AI's own past
    analysis is not a training label. Fact-source priority
    (highest first): exchange public market data,
    `EventRepository`, replay / export, structured reports,
    human-approved phase docs, AI text only as commentary
    never as truth.
  - **Truth Layer**: append-only immutable record of
    `price`, `volume`, `OI`, `funding`, `spread`, `depth`,
    `liquidation`, spot/perp divergence, candidate
    `first_seen`, `MFE`, `MAE`, `tail_label`, risk
    rejection reason, `strategy_mode`, cluster context,
    `report_id` / `opportunity_id` / `scan_batch_id`. AI
    judgements must cite Truth Layer fields; no claim of
    strategy effectiveness without Truth Layer evidence.
  - **Reality Check Layer**: hard-rule (not LLM) gate
    that downweights / rejects AI conclusions when funding
    is overheated, spread is widening, depth has collapsed,
    spot volume is falling while perp price rises,
    `late_chase_risk` is high, data is stale or degraded,
    or the Risk Engine has rejected. Reality Check
    priority sits above AI explanation and Strategy
    Selector recommendation; the Risk Engine remains the
    absolute trade-decision gate.
  - **Anti-overfitting governance**: no auto rule
    loosening from small samples; no global change from a
    single 妖币 (demon coin) case; no leverage / size lift
    from historical sample fits; no parameter tuning from
    AI text labels. All strategy adjustments must pass the
    six-gate process (sample-count gate, validation
    quality gate, replay, paper-only shadow validation,
    human review, phase-gate approval).
  - **Feedback isolation**: AI may **not** learn from its
    own narrative, confidence, prior speculative text,
    Telegram copy, or unverified human subjective
    evaluation. AI may only learn from `MFE` / `MAE`,
    `tail_label`, `fake_breakout`, `missed_tail`,
    `late_chase_failure`, risk-rejection outcomes, and
    replay-verified results.
  - **Architecture layers** (annotated with current
    state and trade-authority): Observation Layer
    (partial; NONE), Market Intelligence Layer (partial;
    NONE), Regime Engine (partial; NONE), Strategy
    Orchestrator (partial; paper, NONE), Risk Allocation
    Engine (GATE), Execution FSM (paper today; GATE),
    Replay / Verification Layer (partial; NONE), Truth
    Layer (substrate; NONE), Reality Check Layer (partial;
    DOWNWEIGHT). Only the Risk Engine and the Execution
    FSM are trade-decision gates.
  - **Future backlog (not implemented; no trade
    authority)**: Regime Transition Prediction, Liquidity
    Intelligence, Market Structure Memory, Narrative
    Acceleration, Social Saturation, Bot Amplification,
    Cross-exchange Flow, Lead-lag Relationships,
    Spot/perp Divergence, Stablecoin Inflow, Iceberg /
    Spoof Detection, Narrative-aware Cluster Taxonomy,
    AI Market Intelligence Layer, AI Interpretation
    Sandbox, AI Reality Check Scoring. Each item is
    `NOT_STARTED` or `FUTURE_RESEARCH` with
    `trade_authority = NONE`.
  - **Explicit rejections** (permanent): AI autonomous
    trading, AI direct price prediction, reinforcement
    learning live trading, black-box parameter
    optimisation, infinite auto-optimisation, AI bypassing
    the Risk Engine, AI modifying leverage / size / stop /
    target, direct Phase 12 jump.
- **`docs/PROJECT_STATUS.md`** — appended a guidance-only
  "Architecture governance" section that references the new
  document and explicitly states the document does not
  change the current phase, does not flip any safety flag,
  does not authorise any runtime behavior, does not advance
  Phase 11C.1C-C-B-B-A to ACCEPTED, does not kick off Phase
  11C.1C-C-B-B-B, and does not authorise Phase 12. The Phase
  1 safety lock is restated verbatim.
- **`docs/PHASE_GATE.md`** — appended a guidance-only
  "Architecture governance (guidance-only; no phase change)"
  section at the end. Phase ledger effect: none. Trade
  authority granted: none. Safety flag effect: none. Phase 12
  remains FORBIDDEN. The current open phase remains Phase
  11C.1C-C-B-B-A (IN_REVIEW; PR #44 open).

#### Forbidden by this PR (carries forward verbatim)

- Real trading.
- Live trading.
- Binance API key / secret.
- Signed endpoint / `listenKey` / private WebSocket.
- Account / order / position / leverage / margin endpoint.
- DeepSeek trade decision.
- Real Telegram outbound.
- AI deciding direction / position size / leverage / stop /
  target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- Risk Engine override / bypass.
- Phase 11C.1C-C-B-B-A acceptance flip (this docs-only PR
  is independent of the Phase 11C.1C-C-B-B-A acceptance
  flow).
- Phase 11C.1C-C-B-B-B kickoff.
- Phase 12 / live trading kickoff.

#### Acceptance gate (docs-only)

- Docs-only PR. No code modified under `app/`, `scripts/`,
  `tests/`, `configs/`, `risk/`, `execution/`, `llm/`,
  `telegram/`, or `exchange/`.
- No new tests are required (no runtime / contract change).
- No dry-run / smoke required (no runtime change).
- Safety boundary held end-to-end (`mode=paper`,
  `live_trading=False`, `exchange_live_orders=False`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no API key, no
  signed endpoint, no private WS, no `listenKey`, no
  DeepSeek trade decision, no real Telegram outbound).
- **Phase 12 remains FORBIDDEN.**

### Phase 11C.1C-C-B-B-A - Strategy Validation Dataset Builder & Quality Gate v0

**Version:** `1.4.0a11c.1c.c.b.b.a` - Phase 11C.1C-C-B-B-A.
Tracks the **paper / report-only first slice** of the deeper
Phase 11C.1C-C-B-B work: dataset record / dataset / summary /
quality-gate v0 contracts + pure builders + the runtime hook
that emits three new typed events on top of the Phase
11C.1C-C-B-A `StrategyValidationSample` /
`StrategyValidationReport` / `ClusterExposureAssessment`
artefacts. The dataset is exportable, replayable, and
auditable; the quality gate is a *sample trust* gate, not a
*strategy quality* gate.

> **Status: ACCEPTED (closed 2026-05-23; PR #44 merged into
> `main`, mergeCommit `3ecfc3b`).** Paper / report only.
> NOT live trading. NOT AI Learning. NOT automatic parameter
> optimisation. NOT reinforcement learning. NOT the complete
> Strategy Validation Lab follow-up (Phase 11C.1C-C-B-B-B).
> NOT the Paper Alpha Gate v0. NOT Phase 12.
>
> The `validation_quality_gate_status` field on every
> `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` event
> (`pass` / `warn` / `fail`) is a **descriptive label** for
> human review and **MUST NEVER trigger a real trade**; the
> Risk Engine remains the single trade-decision gate.

#### Phase 11C.1C-C-B-B-A accepted (closeout summary)

  - Strategy Validation Dataset Builder
  - Quality Gate v0
  - validation dataset export / replay compatibility
  - validation dataset summary
  - `validation_quality_gate_status`
  - paper-only, no live trading
  - PR #44 merged into `main` (mergeCommit `3ecfc3b`)
  - 27 brief-mandated tests PASS / 339 phase11c tests PASS /
    2313 full pytest PASS on the PR branch (no regression vs.
    post-PR-#43 main 2286 baseline)
  - 30 s dry-run smoke generated dataset and quality gate
    report
    (`STRATEGY_VALIDATION_DATASET_BUILT=1`,
    `STRATEGY_VALIDATION_DATASET_EXPORTED=1`,
    `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED=1`,
    `validation_dataset_records=2`,
    `validation_dataset_symbols=BTCUSDT,ETHUSDT`,
    `validation_quality_gate_status=fail` — expected for the
    low-sample 30 s window, exactly the brief's "empty or
    low-sample quality gate report" requirement,
    `validation_dataset_export_ready=True`,
    `validation_dataset_replay_ready=True`)
  - `validation_quality_gate_status=fail` is the **expected**
    output for the low-sample 30 s dry-run (smallest Phase
    11C.1C-C-A primary tracking window is 5 minutes; samples
    are necessarily in-flight)
  - `validation_quality_gate_status` is **descriptive only**
    (`pass` / `warn` / `fail`) and **MUST NEVER trigger a real
    trade**; the Risk Engine remains the single trade-decision
    gate
  - real WS 10 min smoke is **NOT required** for this PR
    (smallest Phase 11C.1C-C-A tracking window is 5 min and
    cannot complete in 30 s); reserved for Phase
    11C.1C-C-B-B-B closeout when non-empty datasets are first
    observable end-to-end
  - safety flags unchanged (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`)
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account / order / position / leverage / margin endpoint
  - no private websocket
  - no listenKey
  - no DeepSeek trade decision
  - no real Telegram outbound
  - Phase 12 remains FORBIDDEN

> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live
> trading, API keys, private endpoints, DeepSeek trade
> decisions, real Telegram outbound, Phase 11C.1C-C-B-B-B
> kickoff bypassing the standard gate, the Paper Alpha Gate
> v0, the complete Strategy Validation Lab follow-up, AI
> Learning, automatic parameter optimisation, reinforcement
> learning, or Phase 12.** The Phase 1 safety lock and every
> Phase 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A /
> 11C.1C-C-B-A forbidden item carry over unchanged. The three
> new `STRATEGY_VALIDATION_DATASET_*` /
> `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` events and the
> `validation_quality_gate_status` field are paper /
> report-only descriptive labels: they MUST NEVER trigger a
> real trade. The Risk Engine remains the single
> trade-decision gate.

> **Phase 11C.1C-C-B-B-A is NOT live trading. NOT AI Learning.
> NOT the complete Strategy Validation Lab follow-up. NOT the
> Paper Alpha Gate v0. NOT automatic parameter optimisation.
> NOT reinforcement learning. NOT real Telegram outbound. NOT
> real Binance trading API.** It is the Strategy Validation
> Dataset Builder + Quality Gate v0 first slice on top of the
> Phase 11C.1C-C-B-A artefacts.

#### Safety flags after the PR #44 closeout (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

---

#### Phase 11C.1C-C-B-B-A original IN_REVIEW entry (preserved verbatim for evidence audit trail)

> **Status: IN_REVIEW (PR #44 open).** Paper / report only.
> NOT live trading. NOT AI Learning. NOT automatic parameter
> optimisation. NOT reinforcement learning. NOT the complete
> Strategy Validation Lab follow-up (Phase 11C.1C-C-B-B-B).
> NOT Phase 12.
>
> The `validation_quality_gate_status` field on every
> `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` event
> (`pass` / `warn` / `fail`) is a **descriptive label** for
> human review and **MUST NEVER trigger a real trade**; the
> Risk Engine remains the single trade-decision gate.

#### Added

- **`app/adaptive/strategy_validation_dataset.py`** — new
  pure-function module:
  - Models: `StrategyValidationDatasetRecord`,
    `StrategyValidationDatasetSummary`,
    `StrategyValidationDataset`,
    `StrategyValidationQualityGate`,
    `StrategyValidationQualityGateResult`.
  - Pure functions:
    `build_validation_dataset_from_samples`,
    `summarize_validation_dataset`,
    `evaluate_validation_dataset_quality`,
    `export_validation_dataset_payload`,
    `load_validation_dataset_payload`.
  - Schema version:
    `phase_11c_1c_c_b_b_a.strategy_validation_dataset.v1`.
- **Three new `EventType` values** in `app/core/events.py`:
  `STRATEGY_VALIDATION_DATASET_BUILT`,
  `STRATEGY_VALIDATION_DATASET_EXPORTED`,
  `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`. Every payload
  carries the brief-mandated identity block (`report_id`,
  `timestamp`, `strategy_version`, `scoring_version`,
  `risk_config_version`, `state_machine_version`,
  `schema_version`).
- **`StrategyValidationRuntime`** extended:
  - `flush_report()` now also builds the dataset and evaluates
    the quality gate (under the
    `dataset_enabled` config flag, default True).
  - New runtime properties: `latest_dataset`,
    `latest_quality_gate_result`, `dataset_built_count`,
    `dataset_exported_count`,
    `quality_gate_evaluated_count`.
  - `metrics_payload()` exposes `validation_dataset_records`,
    `validation_dataset_symbols`,
    `validation_dataset_tail_label_counts`,
    `validation_quality_gate_status`,
    `validation_quality_gate_reasons`,
    `validation_dataset_export_ready`,
    `validation_dataset_replay_ready`,
    `validation_quality_gate_result`, plus the three new event
    counters.
- **`StrategyValidationRuntimeConfig`** extended with
  `dataset_enabled` and seven `quality_gate_*` thresholds;
  `from_settings_section()` honours all of them. The new
  `quality_gate()` helper builds the `StrategyValidationQualityGate`
  instance the gate evaluator consumes.
- **`app/config/schema.py > StrategyValidationSection`**
  extended with `dataset_enabled` + seven `quality_gate_*`
  fields + validators (>=0).
- **`app/config/defaults.yaml > strategy_validation`** extended
  with the same keys.
- **Daily report**:
  - `DailyReportSnapshot` extended with
    `validation_dataset_built_count`,
    `validation_dataset_exported_count`,
    `validation_quality_gate_evaluated_count`,
    `validation_dataset_records`,
    `validation_dataset_symbols`,
    `validation_dataset_tail_label_counts`,
    `validation_quality_gate_status`,
    `validation_quality_gate_reasons`,
    `validation_dataset_export_ready`,
    `validation_dataset_replay_ready`,
    `validation_quality_gate_result`.
  - `DailyReportBuilder.build()` cross-checks the runner
    counters against the events.db type-counts of the three
    new event types so a stale runner counter cannot
    under-report.
  - New Markdown section "Phase 11C.1C-C-B-B-A Strategy
    Validation Dataset Builder & Quality Gate v0" with
    explicit "the `validation_quality_gate_status` is
    descriptive and **MUST NEVER trigger a real trade**;
    Phase 12 remains FORBIDDEN" disclaimer.
- **Tests**:
  - `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`
    — 27 brief-mandated cases covering record contract,
    builder, summary, quality gate (pass / warn / fail),
    export round-trip, replay, daily-report integration,
    safety boundary, Phase 12 forbidden.
  - `tests/unit/test_phase11b_no_network.py` allow-list
    extended with the three new event types.
- **Docs**:
  - `docs/PHASE_11C_1C_C_B_B_VALIDATION_DATASET_QUALITY_GATE.md` (new).
  - `docs/PR44_DESCRIPTION.md` (new).
  - `docs/PROJECT_STATUS.md` updated with Phase
    11C.1C-C-B-B-A IN_REVIEW.
  - `docs/PHASE_GATE.md` updated with the open phase entry +
    Phase 11C.1C-C-B-B-B carve-out + open-phases table.

#### Changed

- **`StrategyValidationRuntime._emit()`** now returns the
  `event_id` of the appended event so dataset records can
  carry `source_event_id` cross-references back to events.db.
- **`StrategyValidationRuntime._latest_report_metrics`** is
  rebuilt after the dataset / quality-gate emission so the
  daily-report builder sees the latest dataset / gate fields
  on the same flush.

#### Forbidden by this PR

- Real trading.
- Binance private API / signed endpoint / listenKey / private
  WebSocket.
- LLM / DeepSeek trade decision.
- Real Telegram outbound.
- Right-tail score in production scope.
- `gate_status` triggering real downstream execution.
- AI deciding direction / position size / leverage / stop-loss
  / target / execution.
- Automatic parameter optimisation.
- Reinforcement learning.
- Risk Engine override.
- Phase 11C.1C-C-B-B-B implementation.
- Phase 12 / live trading kickoff.

#### Acceptance gate (status: PR #44 in human review)

- 27 brief-mandated tests PASS.
- `tests/unit -k phase11c_` PASS (339 = 312 baseline + 27).
- Full `tests/` PASS (2313 = 2286 baseline + 27, no
  regression vs. post-PR-#43 main).
- 30 s dry-run smoke produces an empty / low-sample
  quality-gate report (`gate_status=fail` with
  `sample_count_below_half_min` reason and similar — exactly
  what the brief asks for).
- Real WS 10 min smoke is **NOT required** for this PR;
  reserved for Phase 11C.1C-C-B-B-B closeout when non-empty
  datasets are first observable end-to-end.
- Safety boundary held end-to-end (`live_trading=False`,
  `exchange_live_orders=False`, `trading_mode_paper=True`,
  `right_tail=False`, `llm=False`,
  `telegram_outbound_enabled=False`,
  `binance_private_api_enabled=False`, no API key, no signed
  endpoint, no private WS, no listenKey, no DeepSeek trade
  decision, no real Telegram outbound).
- Phase 12 remains FORBIDDEN.

### Phase 11C.1C-C-B-A - Strategy Validation Lab v0 & Cluster Exposure Control Contracts

**Version:** `1.4.0a11c.1c.c.b.a` - Phase 11C.1C-C-B-A. Tracks the
**paper / report-only first slice** of the deeper Phase 11C.1C-C-B
Strategy Validation Lab work. Ships the data contracts + pure
aggregators + the runtime that emits the seven new typed events so
a human reviewer can audit `early_tail_score` /
`opportunity_score` / `strategy_mode` / `candidate_stage` /
cluster-leader behaviour against the Phase 11C.1C-C-A forward
MFE / MAE / `tail_label` outcomes.

> **Status: ACCEPTED (closed 2026-05-23; PR #42 merged into
> `main`, mergeCommit `cc18047`).** PR #42 (branch
> `feature/phase-11c1c-c-b-strategy-validation-cluster-control`,
> PR-head commit `0bedcce`) merged into `main` on 2026-05-23
> (UTC); the operator-VPS 10 min real public WS smoke evidence
> captured under `docs/PHASE_GATE.md` §"Phase 11C.1C-C-B-A
> acceptance evidence (operator-VPS 10 min real public WS
> smoke PASSED)" was accepted; Phase 11C.1C-C-B-A is therefore
> **ACCEPTED**. This docs-only closeout PR mirrors the PR #36
> → PR #37, PR #38 → PR #39, and PR #40 → PR #41 closeout
> pattern. Phase 11C.1C-C-B-B (deeper Strategy Validation Lab
> + richer Cluster Exposure Control follow-up) is now
> **NEXT_ALLOWED / NOT_STARTED**: Phase 11C.1C-C-B-A
> acceptance does **NOT** authorise Phase 11C.1C-C-B-B
> kickoff bypassing the standard gate; Phase 11C.1C-C-B-B
> will require its own kickoff PR, brief, scope, boundary
> table, forbidden list, and acceptance evidence. Phase 12
> remains **FORBIDDEN**.

#### Phase 11C.1C-C-B-A accepted (closeout summary)

  - Strategy Validation Lab v0
  - Cluster Exposure Control Contracts
  - `strategy_mode` validation
  - `candidate_stage` validation
  - `opportunity_score` bucket validation
  - `early_tail_score` bucket validation
  - `tail_label` distribution
  - cluster leader validation
  - cluster exposure assessment
  - paper-only, no live trading
  - PR #42 merged into `main` (mergeCommit `cc18047`)
  - 25 brief-mandated tests PASS / 312 phase11c tests PASS /
    2286 full pytest PASS on the PR branch (no regression vs.
    post-PR-#41 main 2261 baseline)
  - 30 s dry-run smoke contract-only (smallest Phase
    11C.1C-C-A tracking window is 5m; cannot complete in
    30 s)
  - **Operator-VPS 10 min real public WS smoke PASS**
    (`duration_seconds=600.0`, `uptime=611s`,
    `dry_run=false`, `ws_real_transport=true`,
    `ws_messages_received=76324`, `ws_chains_emitted=27`,
    `learning_ready_attached=27`, `snapshots_emitted=27`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED=24`,
    `STRATEGY_VALIDATION_REPORT_GENERATED=1`,
    `STRATEGY_MODE_VALIDATED=4`,
    `CANDIDATE_STAGE_VALIDATED=5`,
    `SCORE_BUCKET_VALIDATED=8`,
    `CLUSTER_EXPOSURE_ASSESSED=1`,
    `CLUSTER_LEADER_VALIDATED=1` from the authoritative
    SQLite `events.db` query captured after shutdown flush;
    daily report contains `"## Phase 11C.1C-C-B-A Strategy
    Validation Lab v0 & Cluster Exposure Control Contracts"`
    with non-empty cohort lines (`strategy_mode=reject n=24`;
    `candidate_stage=early n=24`;
    `opportunity_score_bucket=0-49 n=13` / `50-64 n=11`;
    `early_tail_score_bucket=0-24 n=24`;
    `cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action`);
    `tail_label_distribution = unresolved x 24`;
    `HTTP 429 count=0`, `HTTP 418 count=0`,
    `rate_limit_ban=False`, `ws_reconnect_count=0`,
    `ws_stale_count=0`, `ws_currently_stale=False`,
    `ingestion_errors=0`)
  - safety flags unchanged (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`)
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account / order / position / leverage / margin endpoint
  - no private websocket
  - no listenKey
  - no DeepSeek trade decision
  - no real Telegram outbound
  - Phase 12 remains FORBIDDEN

> **Phase 11C.1C-C-B-A acceptance does NOT authorise live
> trading, API keys, private endpoints, DeepSeek trade
> decisions, real Telegram outbound, Phase 11C.1C-C-B-B
> kickoff bypassing the standard gate, or Phase 12.** The
> Phase 1 safety lock and every Phase 11C.1B / 11C.1C-A /
> 11C.1C-B / 11C.1C-C-A forbidden item carry over unchanged.
> The seven new `STRATEGY_VALIDATION_*` events, the
> `suggested_cluster_action` field
> (`leader_only` / `observe_followers` / `reject_cluster` /
> `no_action`), and the validation cohort statistics are
> paper / report-only descriptive labels: they MUST NEVER
> trigger a real trade. The Risk Engine remains the single
> trade-decision gate.

> **Phase 11C.1C-C-B-A is NOT live trading. NOT AI Learning.
> NOT the complete Strategy Validation Lab. NOT automatic
> parameter optimisation. NOT reinforcement learning. NOT
> real Telegram outbound. NOT real Binance trading API.** It
> is the Strategy Validation Lab v0 + Cluster Exposure
> Control Contracts first slice on top of the Phase
> 11C.1C-C-A `LabelTrackingRecord` outcomes.

#### Safety flags after the PR #42 closeout (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

---

#### Phase 11C.1C-C-B-A original IN_REVIEW entry (preserved verbatim for evidence audit trail)

> **Status: IN_REVIEW (PR #42 open).** **NOT** ACCEPTED yet.
> **NOT** live trading. **NOT** AI Learning. **NOT** the
> complete Strategy Validation Lab. **NOT** automatic
> parameter optimisation. **NOT** Phase 12.
>
> Phase 11C.1C-C-A — *MFE / MAE Label Queue Runtime & Tail
> Outcome Tracking* — merged on 2026-05-23 (PR #40,
> mergeCommit `75d3c7c`) and is the gating predecessor.
> Phase 11C.1C-C-B-A is the **first slice** of the deeper
> Phase 11C.1C-C-B Strategy Validation Lab work; it ships
> only the contracts + aggregators + runtime that emit the
> seven typed events.
>
> **Operator-VPS 10 min real public WS smoke PASSED.** The
> operator ran the smoke from a Binance-reachable VPS
> against the PR #42 head (commit `0bedcce`) and the
> verbatim transcript + the authoritative SQLite event-count
> query are filed under `docs/PHASE_GATE.md` §"Phase
> 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real
> public WS smoke PASSED)" and `docs/PR42_DESCRIPTION.md`
> §"Real WS smoke (operator-VPS 10 min, PASSED)". The Kiro
> sandbox could not host this smoke (Binance-region HTTP
> 451 geoblock — historical context only, not the current
> blocker; same as the Phase 11C.1C-B / Phase 11C.1C-C-A
> closeouts), so the operator ran it from a Binance-reachable
> VPS, mirroring the Phase 11C.1C-C-A closeout pattern.
> **PR #42 is ready for human review and may be merged after
> reviewer confirms the docs-only evidence backfill;** Phase
> 11C.1C-C-B-A flips to ACCEPTED only after PR #42 merges,
> via the standard docs-only closeout PR (mirroring PR #36 →
> PR #37, PR #38 → PR #39, PR #40 → PR #41); this docs-only
> evidence backfill does **not** self-flip the phase to
> ACCEPTED. Phase 11C.1C-C-B-B remains **NOT_STARTED**;
> Phase 12 remains **FORBIDDEN**.

#### Phase 11C.1C-C-B-A scope

  - **Strategy Validation Lab v0 contracts**
    (`app/adaptive/strategy_validation.py`):
    `StrategyValidationSample`,
    `StrategyValidationWindowStats`,
    `StrategyModeValidationStats`,
    `CandidateStageValidationStats`,
    `OpportunityScoreBucketStats`,
    `EarlyTailScoreBucketStats`,
    `TailLabelDistribution`,
    `ClusterLeaderValidationStats`,
    `ClusterExposureAssessment`,
    `StrategyValidationReport`. Schema version
    `phase_11c_1c_c_b_a.strategy_validation.v1`.
  - **Pure aggregators**:
    `build_strategy_validation_sample`,
    `aggregate_by_strategy_mode`,
    `aggregate_by_candidate_stage`,
    `aggregate_by_opportunity_score_bucket`,
    `aggregate_by_early_tail_score_bucket`,
    `aggregate_tail_label_distribution`,
    `evaluate_cluster_leader_performance`,
    `assess_cluster_exposure`,
    `build_strategy_validation_report`.
  - **Runtime**
    (`app/adaptive/strategy_validation_runtime.py`):
    `StrategyValidationRuntimeConfig` (every threshold
    configurable) + `StrategyValidationRuntime` (idempotent
    per `opportunity_id`).
  - **Seven new event types**:
    `STRATEGY_VALIDATION_SAMPLE_CREATED`,
    `STRATEGY_VALIDATION_REPORT_GENERATED`,
    `STRATEGY_MODE_VALIDATED`,
    `CANDIDATE_STAGE_VALIDATED`,
    `SCORE_BUCKET_VALIDATED`,
    `CLUSTER_EXPOSURE_ASSESSED`,
    `CLUSTER_LEADER_VALIDATED`. Every payload carries
    `schema_version` + identity + the four versioning fields.
  - **Wiring**: `WSRadarChainDriver` accepts a
    `strategy_validation_runtime` kwarg and calls
    `runtime.observe_label_record(...)` after the Phase
    11C.1C-C-A `LabelQueueRuntime.observe(...)` returns the
    `LabelTrackingRecord`.
    `scripts/run_public_market_paper.py` instantiates the
    runtime from `settings.strategy_validation`, snapshots
    metrics on every loop tick, and
    `flush_report(emit_events=True)` on shutdown.
  - **Daily-report enhancements**: new section
    `## Phase 11C.1C-C-B-A Strategy Validation Lab v0 &
    Cluster Exposure Control Contracts` with paper / report-only
    boundary preamble, headline counts, per-mode / per-stage /
    per-bucket cohort lines, tail label distribution, top
    symbols, cluster exposure assessments (showing
    `suggested_cluster_action`), cluster leader validation, and
    flagged findings.
  - **Configuration**: `StrategyValidationSection` Pydantic
    schema; `strategy_validation:` block in
    `app/config/defaults.yaml`; `Settings.strategy_validation`
    accessor.
  - **Score buckets**: `opportunity_score`
    `0-49 / 50-64 / 65-79 / 80-100`; `early_tail_score`
    `0-24 / 25-49 / 50-74 / 75-100`.
  - **Cluster actions** (paper / report only):
    `leader_only` / `observe_followers` / `reject_cluster` /
    `no_action`. **MUST NEVER trigger a real trade.**

#### Phase 11C.1C-C-B-A boundary

  - `mode = paper`, `live_trading = False`,
    `exchange_live_orders = False`, `right_tail = False`,
    `llm = False`, `telegram_outbound_enabled = False`,
    `binance_private_api_enabled = False`. Phase 1 safety lock
    unchanged.
  - **NO** Binance API key / secret. **NO** signed endpoint /
    private WS / `listenKey`. **NO** account / order / position
    / leverage / margin endpoint. **NO** DeepSeek trade
    decision. **NO** real Telegram outbound.
  - **NOT** real trading. **NOT** live trading. **NOT** an
    LLM / AI deciding direction / position size / leverage /
    stop / target / execution. **NOT** automatic parameter
    optimisation. **NOT** reinforcement learning. **NOT** a
    validation result triggering a real order. **NOT** the
    complete Strategy Validation Lab. **NOT** Phase 12.

#### Phase 11C.1C-C-B-A tests

  - `tests/unit/test_phase11c_1c_c_b_strategy_validation.py`
    (NEW, 25 tests) — covers: sample creation; runtime
    sample-created event emission with idempotency; cohort
    aggregators (with `observe` + `reject` cohorts); candidate
    stage aggregator (with `dumped`); opportunity / early-tail
    score buckets; tail-label distribution; cluster leader
    validation; cluster exposure (`leader_only`,
    `observe_followers`, `reject_cluster`, `no_action`);
    `dumped` is not a long opportunity; empty report;
    `observe` / `reject` validated without trade authorisation;
    chain wiring; flush_report emits all seven event types;
    daily report contains metrics; events exportable; replay
    reads new events; replay handles missing
    `schema_version`; safety boundary; `phase_12_remains_forbidden`;
    runtime disabled returns None; max_samples capacity bounded.
  - `tests/unit/test_phase11b_no_network.py` allow-list
    updated with the seven new event types.
  - **Test counts**: 25/25 new tests PASS, 312/312 phase11c\_
    tests PASS (287 baseline + 25 new), 2286/2286 full pytest
    PASS (2261 baseline + 25 new). No regression vs. post-PR-#41
    main baseline.

#### Phase 11C.1C-C-B-A acceptance gate

  - `python -m pytest tests/unit/test_phase11c_1c_c_b_strategy_validation.py -q`
    → 25/25 PASS.
  - `python -m pytest tests/unit/ -k "phase11c_" -q`
    → 312/312 PASS.
  - `python -m pytest tests/ -q`
    → 2286/2286 PASS.
  - **30 s dry-run smoke is contract-only** (the smallest Phase
    11C.1C-C-A tracking window is 5 min; a 30 s dry-run cannot
    complete the primary window). The runner explicitly logs an
    "empty Strategy Validation Lab v0 report" line when the
    sample buffer is empty so the daily-report section still
    renders correctly.
  - **Operator-VPS 10 min real public WS smoke PASSED** on
    2026-05-23 against the PR #42 head (commit `0bedcce`,
    branch
    `feature/phase-11c1c-c-b-strategy-validation-cluster-control`).
    Command actually used:

        ```
        python -m scripts.run_public_market_paper \
            --duration 10min \
            --symbol-limit 5 \
            --ws-first
        ```

    > Note: the runner does **not** support `--emit-banner`. The
    > banner is emitted by default; pass `--no-banner` to
    > suppress.

    Headline runner numerics: `duration_seconds=600.0`,
    `uptime=611s`, `dry_run=false`, `ws_real_transport=true`,
    `ws_messages_received=76324`, `ws_chains_emitted=27`,
    `learning_ready_attached=27`, `snapshots_emitted=27`,
    `ingestion_errors=0`, `HTTP 429 count=0`,
    `HTTP 418 count=0`, `rate_limit_ban=False`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `ws_currently_stale=False`.

    Authoritative SQLite event-count query
    (`SELECT event_type, COUNT(*) FROM events GROUP BY event_type;`,
    captured **after** shutdown flush):
    `STRATEGY_VALIDATION_SAMPLE_CREATED=24`,
    `STRATEGY_VALIDATION_REPORT_GENERATED=1`,
    `STRATEGY_MODE_VALIDATED=4`,
    `CANDIDATE_STAGE_VALIDATED=5`,
    `SCORE_BUCKET_VALIDATED=8`,
    `CLUSTER_EXPOSURE_ASSESSED=1`,
    `CLUSTER_LEADER_VALIDATED=1`.

    Daily-report section "Phase 11C.1C-C-B-A Strategy Validation
    Lab v0 & Cluster Exposure Control Contracts" rendered with
    non-empty cohort lines (`strategy_mode=reject n=24`;
    `candidate_stage=early n=24`;
    `opportunity_score_bucket=0-49 n=13` / `50-64 n=11`;
    `early_tail_score_bucket=0-24 n=24`;
    `cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action`);
    `tail_label_distribution = unresolved x 24` (5 m primary
    windows still in-flight at the 10 min boundary, as
    expected).

    > **Important note on the daily report's top event-count
    > lines.** The daily report's top event-count lines may
    > show `STRATEGY_VALIDATION_REPORT_GENERATED` /
    > `STRATEGY_MODE_VALIDATED` /
    > `CANDIDATE_STAGE_VALIDATED` /
    > `SCORE_BUCKET_VALIDATED` / `CLUSTER_*` counts as **0**
    > because those event counters appear to be snapshotted
    > **before** shutdown flush. The **authoritative** event
    > repository SQLite query (above) confirms those events
    > were emitted. The daily report **section itself**
    > rendered the Strategy Validation cohorts non-empty and
    > correctly. This snapshot-vs-flush gap is a daily-report
    > instrumentation nuance that does **not** invalidate the
    > smoke; the SQLite ground truth is conclusive. A future
    > daily-report polish can move the counter snapshot after
    > the shutdown flush; it is **not** in scope for Phase
    > 11C.1C-C-B-A.

    Safety boundary held end-to-end across the smoke run:
    `exchange_live_order_enabled=False`,
    `live_trading_enabled=False`, `llm_enabled=False`,
    `right_tail_enabled=False`, `trading_mode_paper=True`; no
    live trading; no API key; no signed endpoint; no private
    websocket; no listenKey; no DeepSeek trade decision; no
    real Telegram outbound; **Phase 12 remains FORBIDDEN**.

    The Kiro-side sandbox could not host this smoke
    (Binance-region HTTP 451 geoblock — historical context;
    same as the Phase 11C.1C-B / Phase 11C.1C-C-A closeouts),
    so the operator ran it from a Binance-reachable VPS. The
    full verbatim transcript is filed under
    `docs/PHASE_GATE.md` §"Phase 11C.1C-C-B-A acceptance
    evidence (operator-VPS 10 min real public WS smoke
    PASSED)" and the operator-side description is in
    `docs/PR42_DESCRIPTION.md` §"Real WS smoke (operator-VPS
    10 min, PASSED)". **PR #42 is ready for human review and
    may be merged after reviewer confirms docs-only evidence
    backfill;** this docs-only backfill does **not** self-flip
    Phase 11C.1C-C-B-A to ACCEPTED — that flip happens via
    the standard docs-only closeout PR after PR #42 has
    merged.

### Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime & Tail Outcome Tracking

**Version:** `1.4.0a11c.1c.c.a` - Phase 11C.1C-C-A. Tracks the
**paper-only first runtime** that consumes the Phase 11C.1C-A
`LABEL_QUEUE_ENQUEUED` contract and produces forward
MFE / MAE / `tail_label` outcomes per ACTIVE candidate over
five tracking windows (5m primary, 15m / 30m / 1h / 4h
secondary).

> **Status: ACCEPTED (closed 2026-05-23; PR #40 merged into
> `main`, mergeCommit `75d3c7c`).** PR #40 (branch
> `feature/phase-11c1c-c-mfe-mae-label-queue-runtime`, code
> commit `4889087`, docs-gate-fix commit `6d6044d`) merged
> into `main` on 2026-05-23 (UTC); the operator-VPS 10 min
> real public WS smoke evidence captured under
> `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence
> (closeout)" was accepted; Phase 11C.1C-C-A is therefore
> **ACCEPTED**. This docs-only closeout PR mirrors the PR #36
> → PR #37 and PR #38 → PR #39 closeout pattern. Phase
> 11C.1C-C-B (deeper Strategy Validation Lab + Cluster
> Exposure Control) is now **NEXT_ALLOWED / NOT_STARTED**:
> Phase 11C.1C-C-A acceptance does **NOT** authorise Phase
> 11C.1C-C-B kickoff bypassing the standard gate; Phase
> 11C.1C-C-B will require its own kickoff PR, brief, scope,
> boundary table, forbidden list, and acceptance evidence.
> Phase 12 remains **FORBIDDEN**.

#### Phase 11C.1C-C-A accepted (closeout summary)

  - MFE / MAE Label Queue Runtime
  - Tail Outcome Tracking
  - `LABEL_TRACKING_STARTED`
  - `LABEL_WINDOW_UPDATED`
  - `LABEL_WINDOW_COMPLETED`
  - `TAIL_LABEL_ASSIGNED`
  - `missed_tail` / `fake_breakout` event support
    (`MISSED_TAIL_DETECTED` / `FAKE_BREAKOUT_DETECTED`
    independent flags)
  - paper-only, no live trading
  - PR #40 merged into `main` (mergeCommit `75d3c7c`)
  - 30 brief-mandated tests PASS / 287 phase11c tests PASS /
    2261 full pytest PASS on the PR branch (no regression vs.
    post-PR-#38 main 2231 baseline)
  - 30 s dry-run smoke contract-only (smallest tracking
    window is 5m; cannot complete in 30 s)
  - **Operator-VPS 10 min real public WS smoke PASS**
    (`duration_seconds=600.0`, `dry_run=false`,
    `ws_real_transport=true`, `ws_messages_received=56592`,
    `ws_chains_emitted=27`,
    `LABEL_TRACKING_STARTED=19` runner / `36` events.db,
    `LABEL_WINDOW_UPDATED=38` / `82`,
    `LABEL_WINDOW_COMPLETED=11` / `20` (5m primary window
    closed inside the 10 min run),
    `TAIL_LABEL_ASSIGNED=11` / `20`,
    `MISSED_TAIL_DETECTED=0`, `FAKE_BREAKOUT_DETECTED=0`,
    `pending_label_records=8`,
    `completed_label_records=11`,
    `expired_label_records=0`,
    `unresolved_label_records=0`, `HTTP 429 count=0`,
    `HTTP 418 count=0`, `rate_limit_ban=False`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `ws_currently_stale=False`, `ingestion_errors=0`)
  - safety flags unchanged (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`)
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account/order/position/leverage/margin endpoint
  - no private websocket
  - no listenKey
  - no DeepSeek trade decision
  - no real Telegram outbound
  - Phase 12 remains FORBIDDEN

> **Phase 11C.1C-C-A acceptance does NOT authorise live
> trading, API keys, private endpoints, DeepSeek trade
> decisions, real Telegram outbound, Phase 11C.1C-C-B kickoff
> bypassing the standard gate, or Phase 12.** The Phase 1
> safety lock and every Phase 11C.1B / 11C.1C-A / 11C.1C-B
> forbidden item carry over unchanged. The new `mfe_pct` /
> `mae_pct` / `tail_label` / `strategy_mode` /
> `MISSED_TAIL_DETECTED` / `FAKE_BREAKOUT_DETECTED` fields
> are descriptive labels only: they MUST NEVER trigger a real
> trade. The Risk Engine remains the single trade-decision
> gate.

> **Phase 11C.1C-C-A is NOT live trading. NOT AI Learning.
> NOT the complete Strategy Validation Lab. NOT Cluster
> Exposure Control. NOT real Telegram outbound. NOT real
> Binance trading API.** It is the MFE / MAE Label Queue
> Runtime + Tail Outcome Tracking first version on top of the
> Phase 11C.1C-A `LabelQueueContract`.

#### Phase 11C.1C-C-A scope (in PR #40)

  - `app/adaptive/label_runtime.py` (NEW, 1459 LoC):
    `LabelQueueRuntime` + `LabelTrackingRecord` +
    `TrackingWindowState` + `LabelQueueRuntimeConfig` + pure
    helpers (`compute_pct_return`, `update_window_with_price`,
    `assign_tail_label_for_window`). Schema-versioned via
    `LABEL_TRACKING_SCHEMA_VERSION = "phase_11c_1c_c_a.label_tracking.v1"`.
    All thresholds (R-multiples, fake_breakout,
    late_chase_failure, dumped, stopped_before_tail,
    missed_tail) are configurable. Rule-based, no LLM.
  - `app/core/events.py`: six new event types plumbed through
    `EventRepository`: `LABEL_TRACKING_STARTED`,
    `LABEL_WINDOW_UPDATED`, `LABEL_WINDOW_COMPLETED`,
    `TAIL_LABEL_ASSIGNED`, `MISSED_TAIL_DETECTED`,
    `FAKE_BREAKOUT_DETECTED`. Each payload carries identity
    (`tracking_id` / `opportunity_id` / `scan_batch_id` /
    `symbol` / `source_event_id`) plus the `schema_version`
    stamp. Old events without the runtime sub-block remain
    replayable.
  - `app/config/schema.py` + `app/config/defaults.yaml`: new
    `label_queue_runtime` YAML section with every threshold,
    `max_pending_records`, `grace_period_seconds`, and the
    five tracking windows (5m primary; 15m / 30m / 1h / 4h
    secondary).
  - `app/config/settings.py`: settings entry-point exposes the
    `label_queue_runtime` block to the runner.
  - `app/market_data_public/ws_radar_chain.py`:
    `WSRadarChainDriver` accepts an optional
    `label_queue_runtime`; after emitting
    `LABEL_QUEUE_ENQUEUED` it captures the event_id and calls
    `runtime.observe(adaptive, source_event_id)` so a
    `LabelTrackingRecord` is created (idempotent) and price
    ticks advance MFE / MAE on every subsequent chain pass.
  - `app/paper_run/daily_report.py`: `DailyReportSnapshot` +
    Markdown body surface every brief-mandated metric -
    tracking-started / window-updated / window-completed /
    tail-label / missed-tail / fake-breakout counts;
    pending / completed / expired / unresolved records;
    `tail_label_distribution`; `reached_2r` /  `reached_3r` /
    `reached_5r` / `reached_10r` counts; outcomes by
    `early_tail` / `opportunity` / `strategy_mode` /
    `late_chase_risk` bucket; top-MFE / worst-MAE /
    missed-tail / fake-breakout symbol lists.
  - `scripts/run_public_market_paper.py`: instantiates
    `LabelQueueRuntime` from settings, ticks it on every
    loop iteration plus on shutdown, and threads
    `label_runtime_metrics` into the daily report.

Idempotency: `opportunity_id` index, fallback
`(symbol, candidate_first_seen_ts, first_seen_price)`.
`max_pending_records` caps the queue. Records past
`4h + grace_period_seconds` are auto-expired. Missing prices
return `None` instead of raising.

#### Tail label taxonomy (rule-based)

Per window, once observation is complete, one of:

  - `strong_tail`
  - `moderate_tail`
  - `weak_tail`
  - `fake_breakout`
  - `late_chase_failure`
  - `dumped`
  - `stopped_before_tail`
  - `unresolved` (default)

`MISSED_TAIL_DETECTED` is emitted as an independent flag, not
a tail_label value.

#### Phase 11C.1C-C-A explicitly forbids (inherited verbatim)

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority.
  - Implementing the full Strategy Validation Lab.
  - Implementing Cluster Exposure Control.
  - Implementing AI Learning that auto-decides trades.
  - Issuing any real order.
  - Entering Phase 12.

#### Phase 11C.1C-C-A acceptance gate (all met)

The acceptance gate is **fully on file** and was accepted on
merge of PR #40. Phase 11C.1C-C-A is now **ACCEPTED**, mirroring
the PR #36 → PR #37 and PR #38 → PR #39 closeout pattern.

| Gate                                                                                | Status (PR #40 branch)                                              |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `pytest tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`                     | **PASS - 30 / 30**                                                   |
| `pytest tests/unit/ -k phase11c_`                                                   | **PASS - 287 / 287** (no regression vs. post-PR-#38 main 257 baseline; +30 from new file) |
| `pytest tests/`                                                                     | **PASS - 2261 / 2261** (no regression vs. post-PR-#38 main 2231 baseline; +30 from new file) |
| 30 s dry-run smoke (LABEL_TRACKING_STARTED emitted; 5m windows pending)             | claimed by PR #40 commit message; covered by integration tests inside the targeted test file |
| Safety regression (Phase 1 flags unchanged; no `ORDER_*` / `POSITION_*` / `STOP_*` / `TELEGRAM_MESSAGE_SENT`) | **PASS** (covered by `test_no_live_trading_flags_unchanged` and `test_label_runtime_does_not_open_position_or_authorise_trade`) |
| 10 min real public WS smoke from operator VPS                                        | **PASSED.** Run from a Binance-reachable VPS against commit `6d6044d`. Verbatim transcript filed under `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence (closeout)" and `docs/PR40_DESCRIPTION.md` §"10 min real public WS smoke (operator-VPS, PASSED)". Headline numerics below. |

The operator-VPS 10 min real public WS smoke produced, with
the runner output captured verbatim:

  - `dry_run = false`
  - `ws_real_transport = true`
  - `duration_seconds = 600.0`, `uptime = 608s`
  - `ws_messages_received = 56592`
  - `ws_chains_emitted = 27`
  - `learning_ready_attached = 27`
  - `snapshots_emitted = 27`
  - `LABEL_TRACKING_STARTED = 19` (runner) / `36` (events.db)
  - `LABEL_WINDOW_UPDATED = 38` (runner) / `82` (events.db)
  - `LABEL_WINDOW_COMPLETED = 11` (runner) / `20` (events.db)
    — 5m primary window closed inside the 10 min run
  - `TAIL_LABEL_ASSIGNED = 11` (runner) / `20` (events.db)
  - `MISSED_TAIL_DETECTED = 0`, `FAKE_BREAKOUT_DETECTED = 0`
    (valid outcomes for a 10 min window over five seed
    symbols; not gate-blocking)
  - `pending_label_records = 8`,
    `completed_label_records = 11`,
    `expired_label_records = 0`,
    `unresolved_label_records = 0`
  - daily report contains `"## Phase 11C.1C-C-A MFE / MAE
    Label Queue Runtime & Tail Outcome Tracking"`
  - `HTTP 429 count = 0`
  - `HTTP 418 count = 0`
  - `rate_limit_ban = False`
  - `ws_reconnect_count = 0`
  - `ws_stale_count = 0`
  - `ws_currently_stale = False`
  - `ingestion_errors = 0`
  - safety flags unchanged (`live_trading_enabled=False`,
    `right_tail_enabled=False`, `llm_enabled=False`,
    `exchange_live_order_enabled=False`,
    `trading_mode_paper=True`; no API key, no signed
    endpoint, no private websocket, no listenKey, no
    DeepSeek trade decision, no real Telegram outbound,
    Phase 12 remains **FORBIDDEN**)

The Kiro-side sandbox could **not** host this smoke
(Binance-region HTTP 451 geoblock; same as the Phase 11C.1C-B
closeout), so the operator ran it from a Binance-reachable
VPS. A sandbox WS smoke would not have been authoritative
evidence and was not filed as such.

The operator-side runbook for the smoke run is captured in
`docs/PR40_DESCRIPTION.md`. The full Phase 11C.1C-C-A scope,
boundary, and forbidden-item list lives in
`docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md`.

#### Safety flags after the PR-branch test runs

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

### Phase 11C.1C-B - Adaptive Candidate Runtime Calibration & Early Tail Discovery v0

**Version:** `1.4.0a11c.1c.b` - Phase 11C.1C-B. Tracks the
**paper-only first version** of the Adaptive Candidate Runtime
Calibration & Early Tail Discovery layer that builds on top of
the Phase 11C.1C-A contracts.

> **Status: ACCEPTED (closed 2026-05-22; PR #38 merged into
> `main`, mergeCommit `ce4b6de`).** The 30s dry-run + 5min real
> public WS smoke evidence (recorded under
> `docs/PHASE_GATE.md` §"Phase 11C.1C-B acceptance evidence
> (closeout)") was accepted; PR #38 has been merged into
> `main`; Phase 11C.1C-B is therefore **ACCEPTED**. Phase
> 11C.1C-C is now **NEXT_ALLOWED / NOT_STARTED**. Phase 12
> remains **FORBIDDEN**.

#### Phase 11C.1C-B accepted (closeout summary)

  - Adaptive Candidate Runtime Calibration
  - Early Tail Discovery v0
  - `early_tail_score`
  - `late_chase_risk`
  - runtime calibration metrics (15 brief-mandated fields on
    every adaptive event)
  - top early-tail candidate reporting
    (`top_early_tail_candidates` /
    `top_late_chase_risk_candidates` /
    `early_tail_score_top_symbols` /
    `opportunity_score_distribution` in the daily report)
  - paper-only, no live trading
  - PR #38 merged into `main` (mergeCommit `ce4b6de`)
  - 30s dry-run smoke PASS (runtime calibration block + Phase
    11C.1C-B daily-report section)
  - 5min real public WS smoke PASS (`dry_run=false`,
    `ws_real_transport=true`, `ws_messages_received=30526`,
    `ws_chains_emitted=12`, `rate_limit_429_count=0`,
    `rate_limit_418_count=0`, `rate_limit_ban=False`,
    `ws_stale_count=0`, `ws_reconnect_count=0`,
    `ingestion_errors=12` explainable as sandbox-region HTTP
    451 geoblock on Binance REST — NOT a 429/418/ban; WS pump
    ran cleanly throughout)
  - 12 brief-mandated tests PASS / 257 phase11c tests PASS /
    2231 full pytest PASS (no regression vs. post-PR-#37
    main baseline)
  - safety flags unchanged (`mode=paper`, `live_trading=False`,
    `right_tail=False`, `llm=False`, `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`)
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account/order/position/leverage/margin endpoint
  - no private websocket
  - no listenKey
  - no DeepSeek trade decision
  - no real Telegram outbound
  - Phase 12 remains FORBIDDEN

> **Phase 11C.1C-B acceptance does NOT authorise live trading,
> API keys, private endpoints, DeepSeek trade decisions, real
> Telegram outbound, or Phase 12.** The Phase 1 safety lock and
> every Phase 11C.1B / 11C.1C-A forbidden item carry over
> unchanged. The new `early_tail_score` is descriptive only:
> it protects a candidate from capacity-driven eviction in the
> candidate pool but does NOT authorise opening a real
> position. The Risk Engine remains the single trade-decision
> gate.

> **Phase 11C.1C-B is NOT live trading. NOT AI Learning. NOT
> complete strategy validation. NOT the full MFE/MAE processor.
> NOT real Telegram outbound. NOT real Binance trading API. It
> is the runtime calibration metrics + Early Tail Discovery v0 +
> daily-report enhancements first version on top of the Phase
> 11C.1C-A contracts.**

#### `RuntimeCalibrationMetrics` value object (`app/adaptive/models.py`)

A new frozen Pydantic v2 model carrying the brief-mandated
fifteen fields:

  - `candidate_first_seen_ts`
  - `candidate_first_seen_price`
  - `current_price`
  - `price_change_since_first_seen`
  - `quote_volume_acceleration_1m`
  - `quote_volume_acceleration_5m`
  - `price_acceleration_1m`
  - `price_acceleration_5m`
  - `volume_rank`
  - `volume_rank_jump_5m`
  - `distance_to_24h_high`
  - `distance_from_first_seen`
  - `freshness_score`
  - `late_chase_risk`
  - `early_tail_score`

The block is attached to every `AdaptiveCandidateContext` (under
the new `runtime_calibration` field) and rides into the Phase
8.5 `learning_ready.adaptive_candidate.runtime_calibration`
sub-block on every event the WS-radar chain emits, so Phase 8.5
export, Phase 10A replay, and the daily report all pick it up
without schema gymnastics.

#### New `app/adaptive/runtime.py` - pure-function helpers

  - `compute_runtime_calibration(...)` - top-level builder; takes
    raw runtime inputs (first-seen ts/price, current ts/price,
    price + quote-volume rolling history, current rank +
    5m-old rank, candidate stage, blowoff risk) and returns the
    populated `RuntimeCalibrationMetrics`.
  - `compute_early_tail_score(...)` - additive 0..100 score
    derived from `volume_rank_jump_5m` + quote-volume / price
    accelerations + freshness, gated by stage and capped by
    distance from first-seen.
  - `compute_late_chase_risk_score(...)` - 0..100 risk score
    that rises with distance from first-seen, proximity to 24h
    high, and lost freshness; clamped high for `late` /
    `blowoff` and clamped low for `dumped`.
  - `compute_freshness_score(...)` - simple
    `half_life / (half_life + elapsed)` decay.
  - `compute_relative_acceleration(...)` - rolling-history
    helper.

All functions are pure (no I/O, no global state); the source-tree
audit in
`tests/unit/test_phase11c_1c_a_adaptive_candidate.py
::test_adaptive_module_does_not_import_third_party_network_libs`
already covers the new module.

#### `Candidate` baselines + per-symbol rolling history

`app/market_data_public/candidate_pool.py`:

  - **Stable baselines** recorded ONCE at admission:
    `first_seen_price`, `quote_volume_first_seen`,
    `volume_rank_first_seen`. These never get overwritten on
    subsequent `offer()` updates.
  - **Rolling histories** (`price_history`,
    `quote_volume_history`, `volume_rank_history`, oldest -> newest)
    capped at
    `CandidatePoolConfig.per_symbol_history_max_samples` (200)
    and trimmed to the last 10 minutes.
  - **Runtime-layer scores** (`early_tail_score`,
    `late_chase_risk_score`, `freshness_score`,
    `promoted_before_24h_top_move`) written back by the
    WS-radar chain driver via the new
    `CandidatePool.update_runtime_metrics(...)` method.

#### Early Tail Discovery v0 - capacity-protection invariant

`CandidatePool._enforce_capacity` now sorts candidates by a
two-tier eviction key so the brief's "do not evict high
`early_tail_score`" invariant holds:

```
evict_key = (
    1 if early_tail_score >= early_tail_protect_threshold else 0,
    early_tail_score,
    radar_score,
    last_seen_ms,
)
```

UNPROTECTED candidates (early-tail score below threshold) get
evicted first. PROTECTED candidates only get evicted if every
unprotected candidate has already been removed - and the lowest
early-tail score goes first. The default threshold lives in
`DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD = 60.0`.

#### WS-radar chain integration

`WSRadarChainDriver` (`app/market_data_public/ws_radar_chain.py`):

  - Now accepts an optional `candidate_pool=` handle so the
    driver can write runtime metrics back onto the candidate
    after every chain pass.
  - Reads `candidate.first_seen_price` (stable admission
    baseline) instead of the previous "approximate via
    snapshot" path.
  - Threads `candidate.price_history` /
    `candidate.quote_volume_history` /
    `pool.volume_rank_5m_ago(candidate)` into
    `compute_runtime_calibration`.
  - Tracks per-run aggregates surfaced by
    `adaptive_metrics_payload`:
      - `top_early_tail_candidates` (capped at 10)
      - `top_late_chase_risk_candidates` (capped at 10)
      - `early_tail_score_top_symbols`
      - `opportunity_score_distribution` (10-point bins:
        `0-10` ... `90-100`)
      - `symbols_promoted_before_24h_top_move`
      - `eden_alt_near_examples` - candidate symbols whose
        upper-cased name starts with `EDEN`, `ALT`, or `NEAR`
        and whose `early_tail_score > 0`.

#### Daily report enhancement

`DailyReportSnapshot` + the Markdown body
(`app/paper_run/daily_report.py`) now carry the new fields:

  - `top_early_tail_candidates`
  - `top_late_chase_risk_candidates`
  - `early_tail_score_top_symbols`
  - `opportunity_score_distribution`
  - `symbols_promoted_before_24h_top_move`
  - `eden_alt_near_examples`
  - `early_tail_protect_threshold`
  - `candidate_pool_promoted_before_24h_top_move`

The Markdown body adds a new section
`## Phase 11C.1C-B Adaptive Candidate Runtime Calibration & Early
Tail Discovery v0` after the existing Phase 11C.1C-A block,
explicitly noting the paper / virtual nature of the layer.

#### Phase 1 safety lock UNCHANGED

Phase 11C.1C-B does NOT touch the Phase 1 safety lock. After
running the runtime-calibration pipeline end-to-end every flag
below remains:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client.

#### Phase 11C.1C-B explicitly does NOT

- accept any Binance API key / API secret / `listenKey`.
- subscribe to any user data stream / private WebSocket / trading
  WebSocket API / account / margin / position / leverage / balance
  / order private WS variant.
- treat the new `early_tail_score` or the existing
  `strategy_mode` (paper / virtual) field as a real-trade
  authority. The Risk Engine remains the single trade-decision
  gate; `stop_unconfirmed=True` continues to lock the WS-radar
  chain into the typed-reject path.
- implement the full MFE/MAE processor. The
  `LabelQueueContract` is descriptive; the processor is reserved
  for a future PR (Phase 11C.1C-C).
- implement AI Learning. The Phase 11C.1C-B scoring / selector
  is deterministic.
- enable real Telegram outbound, DeepSeek trade decisions, or
  any third-party HTTP / WebSocket / SDK / LLM / Telegram bot
  import on the runtime-calibration surface.
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c_1c_b_runtime_calibration.py` (new,
  12 cases) pinning every brief-mandated behaviour:
  - `test_early_tail_score_detects_volume_rank_jump`
  - `test_freshness_penalizes_late_chase`
  - `test_late_blowoff_never_follow`
  - `test_top_early_tail_candidates_reported`
  - `test_candidate_first_seen_price_preserved`
  - `test_volume_rank_jump_calculated`
  - `test_adaptive_runtime_fields_exportable`
  - `test_no_live_trading_flags_unchanged`
  - `test_runtime_calibration_payload_round_trips`
  - `test_pool_protects_high_early_tail_candidate_from_eviction`
  - `test_eden_alt_near_examples_surfaced`
  - `test_strategy_mode_does_not_authorise_real_trade`

The full Phase 11C.1C-A test suite continues to pass with no
regression vs. the post-PR-#37 main baseline.

### Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector Contracts

**Version:** `1.4.0a11c.1c.a` - Phase 11C.1C-A. Tracks the
**paper-only first version** of the Adaptive Candidate Regime &
Strategy Selector contracts.

> **Status: ACCEPTED (closed 2026-05-22; PR #36 merged; PR #37
> docs closeout).** PR #36 has been merged into `main`; PR #37
> closed out the docs gate. The Phase 11C.1C-A acceptance smoke
> evidence (30s dry-run + 5min real public WS) was accepted; the
> entry below is the closeout record. Phase 11C.1C-B is now
> **IN_REVIEW / PR_OPEN** on PR #38 (see the Phase 11C.1C-B
> entry above).

> **Phase 11C.1C-A is NOT live trading. NOT AI Learning. NOT
> complete strategy validation. NOT the full MFE/MAE processor. It
> is the data-contract + scoring + selector + paper-only routing
> first version.**

#### New package: `app/adaptive/`

Seven Pydantic v2 frozen value objects + six pure
classifier / scorer functions:

- `MarketRegimeAssessment` - regime bucket + confidence + risk
  multiplier + allowed_strategy_modes + no_trade_reason. Buckets:
  `MEME_RISK_ON` / `SECTOR_ROTATION` / `BTC_ABSORPTION` /
  `ALT_RISK_OFF` / `SYSTEMIC_RISK` / `RISK_OFF` / `NO_TRADE` /
  `NEUTRAL`.
- `CandidateStageAssessment` - life-cycle stage (`early` / `mid`
  / `late` / `blowoff` / `dumped`) + freshness +
  late_chase_risk + blowoff_risk + first_seen_ts +
  first_seen_price + current_price + distance_from_first_seen +
  distance_to_24h_high.
- `OpportunityScore` - weighted-sum score + S/A/B/C grade.
- `StrategyModeDecision` - paper / virtual strategy expression
  (`follow` / `pullback` / `observe` / `reject`).
- `ClusterContext` - cluster_id + cluster_leader + cluster_rank
  + cluster_size + cluster_reason. The first-version classifier
  groups by quote-asset suffix.
- `LabelQueueContract` - opportunity_id / scan_batch_id / symbol
  / enqueued_at_ms / mfe_mae_label_pending / future_tail_label_pending
  / tracking_windows / reference_price. Default tracking
  windows: 5m / 15m / 30m / 1h / 4h.
- `AdaptiveCandidateContext` - one-shot bundle of the above plus
  the four version labels (`strategy_version` / `scoring_version`
  / `risk_config_version` / `state_machine_version`).
- `assess_market_regime`, `classify_candidate_stage`,
  `compute_opportunity_score`, `select_strategy_mode`,
  `build_cluster_context`, `build_label_queue_contract`,
  `build_adaptive_candidate_context` (one-shot orchestrator).

#### Six new EventType entries (`app/core/events.py`)

```
MARKET_REGIME_ASSESSED
CANDIDATE_STAGE_CLASSIFIED
OPPORTUNITY_SCORED
STRATEGY_MODE_SELECTED
CLUSTER_CONTEXT_ATTACHED
LABEL_QUEUE_ENQUEUED
```

The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
pipelines accept the new types unchanged. The Phase 8.5 eleven-type
`LEARNING_READY_EVENT_TYPES` tuple is unchanged; the new types are
exposed as the separate `ADAPTIVE_LEARNING_READY_EVENT_TYPES`
tuple so the Phase 8.5 contract stays load-bearing.

#### Scoring formula (first version)

```
score = (
    0.25 * momentum_strength
  + 0.20 * volume_expansion
  + 0.15 * liquidity_quality
  + 0.15 * regime_fit
  + 0.15 * freshness
  - 0.20 * manipulation_risk
  - 0.20 * late_chase_risk
)
```

Inputs clipped to `[0.0, 100.0]`; score clipped to `[0.0, 100.0]`.
Grade boundaries: S>=80, A in [65,80), B in [50,65), C<50.
Tunable via `OpportunityScoreInputs` + `OpportunityScoreWeights`.

#### Strategy selector (first version)

Decision flow (in priority order):

1. `manipulation_risk >= 60` -> **reject**.
2. regime is `RISK_OFF` / `NO_TRADE` / `SYSTEMIC_RISK` ->
   **reject**. `ALT_RISK_OFF` -> **observe**.
3. stage is `dumped` / `blowoff` / `late` -> **observe**.
4. `mid` + strong momentum + late_chase_risk high -> **pullback**.
5. `early` + every "follow" condition holds + regime allows
   follow -> **follow**.
6. otherwise -> **observe**.

The `mode` is a **paper / virtual** field. `follow` does NOT
authorise opening a position; the Risk Engine remains the single
trade-decision gate; `stop_unconfirmed=True` continues to lock the
chain into the typed-reject path.

#### Phase 8.5 contracts extended

- `LearningReadyContext` (Phase 8.5) gained an optional
  `adaptive_candidate` field; `to_event_payload()` renders it
  under the canonical `adaptive_candidate` key.
- `VirtualTradePlan` (Phase 8.5) gained eleven optional adaptive
  fields: `opportunity_score`, `opportunity_grade`,
  `candidate_stage`, `strategy_mode`, `cluster_id`,
  `cluster_leader`, `label_queue_pending`, `follow_allowed`,
  `pullback_allowed`, `observe_only`, `reject_reason`. All default
  to `None` so existing callers continue to work; the round-trip
  helper `payload_to_virtual_trade_plan` preserves them.

#### WS-radar chain wired

`WSRadarChainDriver.drive()` now:

  - builds an `AdaptiveCandidateContext` per ACTIVE candidate via
    `_build_adaptive_context_for_candidate`;
  - emits the six new events alongside the existing
    `PRE_ANOMALY_DETECTED` / `ANOMALY_DETECTED` /
    `STATE_TRANSITION` chain via `_emit_adaptive_events`;
  - attaches the adaptive context to every event's
    `learning_ready.adaptive_candidate`;
  - propagates the adaptive fields onto the paper
    `VirtualTradePlan`;
  - tracks per-regime / per-stage / per-mode / per-grade
    histograms and exposes `adaptive_metrics_payload()` for the
    runner / daily report (counters: `market_regime_counts`,
    `candidate_stage_counts`, `strategy_mode_counts`,
    `opportunity_grade_counts`, `top_opportunity_scores`,
    `follow_count`, `pullback_count`, `observe_count`,
    `reject_count`, `late_chase_rejected_count`,
    `blowoff_observed_count`, `label_queue_enqueued`).

#### Daily report (`app/paper_run/daily_report.py`)

- `DailyReportBuilder.build()` accepts a new `adaptive_metrics`
  kwarg.
- `DailyReportSnapshot` gained the brief-mandated adaptive fields:
  `market_regime_counts`, `candidate_stage_counts`,
  `strategy_mode_counts`, `opportunity_grade_counts`,
  `top_opportunity_scores`, `label_queue_enqueued`,
  `observe_count`, `reject_count`, `follow_count`,
  `pullback_count`, `late_chase_rejected_count`,
  `blowoff_observed_count`, `market_regime_assessed_count`,
  `candidate_stage_classified_count`,
  `opportunity_scored_count`, `strategy_mode_selected_count`,
  `cluster_context_attached_count`, `adaptive_metrics`.
- `_aggregate` cross-checks the event-log counts of the six new
  event types against the runner-side `adaptive_metrics` so a
  stale runner counter cannot under-report a real adaptive event.
- The Markdown body has a new
  `## Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector`
  section with every brief-mandated counter + per-regime,
  per-stage, per-mode, per-grade tables + a top-N opportunity
  score table.

#### Phase 11C runner (`scripts/run_public_market_paper.py`)

The runner populates `_Phase11CRunStats.adaptive_metrics` from
`WSRadarChainDriver.adaptive_metrics_payload()` on every loop tick
and passes the dict through to `DailyReportBuilder.build()` on
shutdown.

#### Phase 1 safety lock UNCHANGED

Phase 11C.1C-A does NOT touch the Phase 1 safety lock. After
running the adaptive pipeline end-to-end (with the six new
adaptive events firing alongside the Phase 11C.1B chain) every
flag below remains:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client.

#### Phase 11C.1C-A explicitly does NOT

- accept any Binance API key / API secret / `listenKey`.
- subscribe to any user data stream / private WebSocket / trading
  WebSocket API / account / margin / position / leverage / balance
  / order private WS variant.
- treat the new `strategy_mode` (paper / virtual) field as a
  real-trade authority. The Risk Engine remains the single
  trade-decision gate; `stop_unconfirmed=True` continues to lock
  the WS-radar chain into the typed-reject path.
- implement the full MFE/MAE processor. The
  `LabelQueueContract` is descriptive; the processor is reserved
  for a future PR (Phase 11C.1C-B).
- implement AI Learning. The Phase 11C.1C-A scoring / selector is
  deterministic; auto-decided trades are reserved for Phase
  11C.1C-B+.
- enable real Telegram outbound, DeepSeek trade decisions, or any
  third-party HTTP / WebSocket / SDK / LLM / Telegram bot import
  on the adaptive surface.
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c_1c_a_adaptive_candidate.py` (new, 31
  cases) pinning every brief-mandated behaviour:
  - `test_market_regime_assessment_contract`
  - `test_candidate_stage_assessment_contract_field_set`
  - `test_opportunity_score_contract_field_set`
  - `test_label_queue_contract_created`
  - `test_cluster_context_groups_by_quote_asset`
  - `test_candidate_stage_classifier_early`
  - `test_candidate_stage_classifier_mid`
  - `test_candidate_stage_classifier_late`
  - `test_candidate_stage_classifier_blowoff`
  - `test_candidate_stage_classifier_dumped`
  - `test_opportunity_score_formula`
  - `test_opportunity_grade_boundaries`
  - `test_strategy_selector_follow`
  - `test_strategy_selector_pullback`
  - `test_strategy_selector_observe_for_late`
  - `test_strategy_selector_observe_for_blowoff`
  - `test_strategy_selector_reject_for_high_manipulation`
  - `test_strategy_selector_reject_for_no_trade_regime`
  - `test_adaptive_candidate_context_payload_round_trips`
  - `test_adaptive_context_attached_to_learning_ready_payload`
  - `test_adaptive_event_types_distinct_from_phase_8_5_set`
  - `test_ws_radar_chain_emits_six_adaptive_events`
  - `test_virtual_trade_plan_contains_adaptive_fields`
  - `test_daily_report_contains_adaptive_candidate_metrics`
  - `test_export_replay_reads_adaptive_candidate_events`
  - `test_no_live_trading_flags_unchanged`
  - `test_no_real_telegram_outbound_flag_unchanged`
  - `test_no_binance_api_key_consumed`
  - `test_phase_12_remains_forbidden`
  - `test_strategy_mode_does_not_authorise_real_trade`
  - `test_adaptive_module_does_not_import_third_party_network_libs`
- `tests/unit/test_phase11b_no_network.py` extended: allowed
  paper_run event-type list grew the six new entries
  (`MARKET_REGIME_ASSESSED` / `CANDIDATE_STAGE_CLASSIFIED` /
  `OPPORTUNITY_SCORED` / `STRATEGY_MODE_SELECTED` /
  `CLUSTER_CONTEXT_ATTACHED` / `LABEL_QUEUE_ENQUEUED`).
- `tests/unit/test_main_entrypoint.py` updated: banner assertion
  now expects the Phase 11C.1C-A label "Adaptive Candidate
  Regime".

Total tests on PR #36: **2219 passed** in `tests/unit/`
(244 phase11c-prefixed cases including the 31 brief-mandated
`test_phase11c_1c_a_adaptive_candidate.py` cases). No regressions
relative to the 2166-test pre-Phase 11C.1C-A baseline. PR #36 has
been merged into `main`; PR #37 closed out the docs gate. The
test count above is the figure measured on the PR branch at
acceptance time.

#### Versions stamped on every adaptive event

```
strategy_version       = phase_11c_1c_a.strategy.v1
scoring_version        = phase_11c_1c_a.scoring.v1
risk_config_version    = phase_11c_1c_a.risk_config.v1
state_machine_version  = phase_11c_1c_a.state_machine.v1
```

A future PR that bumps the formula or the state machine bumps the
version label and Reflection / Replay automatically picks up the
change.

### Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar

**Version:** `1.4.0a11c.1b` - Phase 11C.1B. Tracks the Phase 11C
real-data acceptance recovery PR-B.

#### Phase 11C.1B 5-min real public WS smoke: PASS (2026-05-22)

The 5-min real public WS smoke now reports
`ws_messages_received > 0`, `ws_chains_emitted > 0`,
`PUBLIC_WS_CONNECTED` written, no 429 / 418, every safety flag
unchanged. The original failure was a zero-timeout `recv`
short-circuit in `StdlibPublicWSTransport.poll`; fixed by always
draining the recv buffer non-blockingly at the top of every
`poll` call (and routing the runner's wait window through the WS
pump's blocking timeout instead of an unrelated `time.sleep`).
See `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B and the
new regression tests
`test_real_ws_transport_drains_buffered_bytes_with_zero_timeout`
+ `test_real_ws_runner_loop_pattern_drains_messages_with_zero_timeout`.

#### Phase 11C.1B follow-up: SymbolUniverse (exchangeInfo-as-truth)

Binance USDⓈ-M Futures lists non-ASCII contracts in production -
documented examples include `我踏马来了USDT` and `币安人生USDT`. Each
is a real Binance contract with its own `/fapi/v1/exchangeInfo`
entry, its own all-market WS push, and its own REST detail
endpoints. Phase 11C.1B therefore validates symbols against the
bootstrapped `exchangeInfo` snapshot - NEVER an ASCII-only regex.

  - **New module** `app/market_data_public/symbol_universe.py`
    with `SymbolUniverse.from_exchange_info(symbols)` and
    `SymbolUniverse.empty()` (back-compat admit-all fallback).
  - **New event** `EventType.WS_SYMBOL_REJECTED` for symbols
    refused by the universe gate.
  - **CandidatePool** now consults the universe in `offer()`;
    rejected symbols emit `WS_SYMBOL_REJECTED` and never enter
    the pool's accounting.
  - **Runner** bootstraps the universe from
    `BinancePublicClient.get_symbols()` before constructing the
    candidate pool; falls back to the empty universe on
    bootstrap failure.
  - **Daily-report** payload extended with
    `candidate_pool_rejected_by_universe`,
    `ws_symbol_universe_size`, `ws_symbol_universe_source`,
    `ws_symbol_universe_bootstrapped`,
    `ws_symbol_universe_bootstrap_ts_ms`.
  - **New test file** `tests/unit/test_phase11c_1b_symbol_universe.py`
    with the 4 brief-mandated tests:
    - `test_non_ascii_exchange_symbol_allowed_if_in_exchange_info`
    - `test_non_ascii_ws_symbol_rejected_if_not_in_exchange_info`
    - `test_symbol_validation_uses_exchange_info_not_ascii_regex`
    - `test_empty_universe_is_admit_all_back_compat`

The brief is explicit: **the rejection reason is "not in
exchangeInfo", NEVER "non-ASCII character class".** A pure-ASCII
symbol that is missing from the snapshot is treated identically
to a Chinese symbol that is missing.

Total tests: **2184 passed** (was 2180 before the SymbolUniverse
follow-up; +4 new tests).

#### PR-B revision: routed public/market WebSocket endpoints

PR #32 now connects to the documented Binance USDⓈ-M Futures
*routed* public-market WebSocket endpoints:

```
PUBLIC route :  wss://fstream.binance.com/public/stream?streams=!bookTicker
MARKET route :  wss://fstream.binance.com/market/stream?streams=
                  !ticker@arr/!miniTicker@arr/!markPrice@arr/!forceOrder@arr
PRIVATE route:  wss://fstream.binance.com/private          # FORBIDDEN
```

The unrouted `wss://fstream.binance.com/stream?streams=...` URL
is NOT the acceptance path: per the Binance public-WS reference,
an unrouted connection silently drops market-class streams
(`!markPrice@arr`, `!ticker@arr`, etc.) so a runner that reports
`PUBLIC_WS_CONNECTED` against `/stream` would in fact miss most
of the radar's data. The new
`MultiTransportPublicWSManager` opens one routed
`StdlibPublicWSTransport` per route in parallel, splits the
configured stream set via `classify_stream_route` /
`split_streams_by_route`, and merges per-route messages behind a
single `WSMessagePump` interface so the
`BinancePublicWSClient` and the runner can pump the union without
any awareness of the underlying topology.

The `/private` routed endpoint is on `FORBIDDEN_WS_PATH_ROOTS`;
`assert_public_ws_path_allowed` refuses it explicitly. New
constants:

- `ALLOWED_PUBLIC_WS_PATH_ROOTS` (routed acceptance) =
  `{"public/ws", "public/stream", "market/ws", "market/stream"}`
- `LEGACY_UNROUTED_WS_PATH_ROOTS` (back-compat for in-process
  pump fixtures only) = `{"ws", "stream"}`
- `FORBIDDEN_WS_PATH_ROOTS` =
  `{"private", "ws-api", "ws-fapi", "ws-papi", "trading-api",
  "userdatastream"}`
- `STREAM_ROUTE_PUBLIC` / `STREAM_ROUTE_MARKET` /
  `STREAM_SUFFIX_ROUTE_PUBLIC` / `STREAM_SUFFIX_ROUTE_MARKET`
  - per-stream route classification.

The runner's WS-first acceptance path now uses the
`MultiTransportPublicWSManager` by default; the unrouted
`/stream` path is kept accepted by the URL parser only so the
in-process pump's existing fixtures still validate. The runner
continues to refuse `--ws-first` without `--dry-run` with rc=2 if
the factory cannot produce a real pump - it does NOT silently
fall back to REST.

The new `tests/unit/test_phase11c_1b_routed_public_market_ws.py`
file pins every behaviour the brief's PR #32 merge checklist
calls out (14 tests):

- `test_routed_public_ws_path_allowed`
- `test_routed_market_ws_path_allowed`
- `test_private_routed_ws_forbidden`
- `test_unrouted_market_stream_rejected_or_not_used`
- `test_mark_price_stream_uses_market_route`
- `test_book_ticker_stream_uses_public_route`
- `test_multi_transport_ws_manager_merges_public_and_market_messages`
- `test_multi_transport_ws_manager_subscribe_routes_to_correct_transport`
- `test_multi_transport_ws_manager_refuses_credentials`
- `test_multi_transport_ws_manager_refuses_private_streams_at_construction`
- `test_runner_real_ws_first_uses_routed_public_and_market_transports`
- `test_no_followup_adapter_stale_text_in_docs_or_help`
- `test_safety_flags_unchanged_with_routed_ws`
- `test_no_private_ws_listen_key_or_user_data_stream`

The Phase 1 safety lock continues to hold throughout. No Binance
API key / secret / `listenKey` is read; no signed REST endpoint
is called; the four ExchangeClientBase write surfaces continue
to refuse on the public client; DeepSeek / Square / real Telegram
outbound stay disconnected; Phase 12 is not entered.

#### Original PR-B scope below

Phase 11C.1A (PR-A, merged) capped the public REST gateway with a
sliding-window rate-limit governor and shut every per-loop detail
REST surface so the bootstrap path could not trigger HTTP 429 / 418
again. The PR-A trade-off was that the runner could see *only* the
symbols the bootstrap already knew about; it could not detect a
brand-new "demon coin" that suddenly woke up between two bootstrap
cadences. Phase 11C.1B (PR-B) restores the discovery surface by
driving an all-market radar off Binance's public WebSocket streams.
The goal is **NOT** to lower discovery capability - it is to *raise*
discovery throughput while keeping REST pressure near zero.

#### New module: `app/exchanges/binance_public_ws.py`

- `BinancePublicWSClient` - public-market WebSocket client.
  - Constructor refuses `api_key` / `api_secret` / `listen_key`
    and any credential-shaped `**kwargs`
    (`PublicWSCredentialForbidden`).
  - `connect` / `disconnect` / `reconnect` lifecycle with
    auto-reconnect (default initial backoff 1 s, max 30 s).
  - `pump_messages(timeout_seconds)` drains the pump, updates the
    heartbeat, and emits `PUBLIC_WS_STALE` once the gap between
    messages crosses `staleness_threshold_ms` (default 3000 ms).
  - `subscribe(streams)` runs every stream through
    `assert_public_ws_stream_allowed`.
  - `metrics_payload()` returns `ws_messages_received` /
    `ws_reconnect_count` / `ws_staleness_ms_max` / `ws_stale_count`
    / `ws_connect_count` / `ws_disconnect_count` /
    `ws_messages_received_by_stream` / `ws_streams_subscribed`.
- `WSConfig` - frozen dataclass; defaults match the brief
  (5 ALLOWLIST streams, `staleness_threshold_ms=3000`,
  `auto_reconnect=True`, `max_subscriptions=64`).
- `WSMessage(stream, data, received_at_ms)` - decoded message
  envelope.
- `WSMessagePump` (abstract) + `InProcessWSPump` (deterministic
  test pump) + `_RefusalTransport` (default; raises
  `NotImplementedError` on `connect`) +
  **`StdlibPublicWSTransport`** (real-network RFC 6455 client
  built on the Python standard library only - `socket` + `ssl` +
  `select` + `struct` + `base64` + `hashlib` + `json` +
  `os.urandom`; route-aware via the new `route="public" |
  "market" | None` constructor parameter; refuses every
  credential-shaped kwarg; never reads `BINANCE_API_KEY` /
  `BINANCE_API_SECRET`; only opens connections to allowlisted
  hosts and routed `/public/{ws,stream}` / `/market/{ws,stream}`
  path roots) +
  **`MultiTransportPublicWSManager`** (Phase 11C.1B routed
  public + market connection group; owns one routed
  `StdlibPublicWSTransport` per route; splits the configured
  streams via `classify_stream_route` and `split_streams_by_route`
  - `!bookTicker` -> PUBLIC, the four MARKET array streams ->
  MARKET; presents the union behind a single `WSMessagePump`
  interface; merges `poll()` output PUBLIC-first MARKET-second;
  exposes `routes` / `transports` / `messages_received_by_route`
  / `metrics_payload`).
- `create_real_public_ws_transport(config=WSConfig(), **kwargs)`
  - public factory for the real-network WS pump. Returns a
  `MultiTransportPublicWSManager` (routed PUBLIC + MARKET
  topology). The runner imports this and calls it whenever
  `--ws-first` is set without `--dry-run`.
- `classify_stream_route(stream)` and
  `split_streams_by_route(streams)` - public helpers that map
  each allowlisted stream to its `"public"` / `"market"` route
  per the Binance USDⓈ-M Futures public-WS reference.
- `assert_public_ws_path_allowed(path)` +
  `ALLOWED_PUBLIC_WS_PATH_ROOTS = {"public/ws", "public/stream",
  "market/ws", "market/stream"}` (the routed acceptance set)
  + `LEGACY_UNROUTED_WS_PATH_ROOTS = {"ws", "stream"}` (kept as
  back-compat for the in-process pump fixtures only) +
  `FORBIDDEN_WS_PATH_ROOTS = {"private", "ws-api", "ws-fapi",
  "ws-papi", "trading-api", "userdatastream"}` (refused at the
  path-root layer in addition to the substring deny-list).
  `assert_public_ws_url_allowed` now runs
  `assert_public_ws_path_allowed` so a hand-composed
  `wss://fstream.binance.com/private/...` URL is refused before
  any socket is opened.
- Public allowlist: `!ticker@arr`, `!miniTicker@arr`,
  `!bookTicker`, `!markPrice@arr`, `!forceOrder@arr` plus the
  per-symbol variants of those streams.
- Private deny-list (`FORBIDDEN_WS_TOKENS`): `listenkey`,
  `userdata`, `userdatastream`, `ws-api`, `trading-api`,
  `ws/api`, `ws-fapi`, `ws-papi`, `accountupdate`,
  `ordertradeupdate`, `orderupdate`, `margincall`, `balanceupdate`,
  `positionupdate`, `leverageupdate`, `accountconfigupdate`.
- Allowed hosts: `fstream.binance.com`,
  `fstream.binancefuture.com`. Only `wss://` URLs accepted.

#### New module: `app/market_data_public/radar.py`

- `AllMarketRadarSnapshot` - frozen pydantic v2 model with every
  brief-mandated field: `symbol`, `timestamp`, `last_price`,
  `price_change_pct_24h`, `price_acceleration_15s`,
  `price_acceleration_60s`, `quote_volume`,
  `quote_volume_delta_60s`, `volume_rank`, `volume_rank_jump`,
  `bid`, `ask`, `spread_pct`, `best_bid_qty`, `best_ask_qty`,
  `mark_price`, `funding_rate`, `liquidation_event`,
  `liquidation_notional`, `ws_source_flags`. `to_payload()` returns
  a JSON-safe dict.
- `AllMarketRadarBuffer` - per-symbol rolling state. Ingest
  handlers cover all five public streams. Computes
  `price_acceleration_15s` / `price_acceleration_60s` /
  `quote_volume_delta_60s` over the rolling history. Maintains
  per-batch volume rank + diffs against the previous batch for
  `volume_rank_jump`. Liquidation events roll off after 60 s.
- `pre_anomaly_score_light(snapshot)` - pure additive scoring,
  capped at 100. Reason tags: `price_acceleration_15s`,
  `price_acceleration_60s`, `quote_volume_delta_60s`,
  `volume_rank_jump`, `spread_compression`,
  `mark_price_alignment`, `liquidation_event`,
  `funding_not_overheated`, `insufficient_history`.
- `RadarScoreConfig` - tunable thresholds; defaults conservative.

#### New module: `app/market_data_public/candidate_pool.py`

- `CandidatePool` - bounded, TTL-aware pool fed from the
  all-market radar. Defaults: `candidate_pool_size=20`,
  `active_detail_limit=3`, `candidate_ttl_seconds=900`,
  `radar_score_threshold=30.0`,
  `volume_rank_jump_threshold=3`,
  `price_acceleration_threshold=0.005`,
  `liquidation_promotes=True`.
- Admission rules: `radar_score >= threshold` OR `volume_rank_jump
  >= threshold` OR `|price_acceleration_60s| >= threshold` OR
  `liquidation_event=True`.
- State machine: WATCHING / ACTIVE / EXPIRED. `pool.expire()`
  drops every candidate older than `candidate_ttl_seconds`.
  Eviction by lowest score + oldest when over capacity.
- Each candidate carries a Phase 8.5 `OpportunityIdentity` with
  `source_phase="phase_11c_1b_ws_first_radar"` so Reflection /
  Replay can split WS-radar candidates from REST-bootstrap
  candidates.
- `metrics_payload()` returns `radar_candidates_seen` /
  `candidate_pool_size` / `candidate_pool_size_max` /
  `candidate_pool_admitted` / `candidate_pool_promoted` /
  `candidate_pool_demoted` / `candidate_pool_expired` /
  `candidate_pool_evicted` / `candidate_pool_active_head` /
  `candidate_pool_top_symbols`.

#### New module: `app/market_data_public/ws_radar_chain.py`

- `WSRadarChainDriver` - drives the Phase 11C.1B event chain for
  one ACTIVE candidate.
  - Reuses the candidate's `OpportunityIdentity` so
    `opportunity_id` / `scan_batch_id` continuity is preserved
    across emissions.
  - Emits `PRE_ANOMALY_DETECTED` + `ANOMALY_DETECTED` +
    `STATE_TRANSITION` with a Phase 8.5 `LearningReadyContext`
    attached to each (opportunity + signal_snapshot +
    virtual_trade_plan + config_versions + source_phase).
  - Maps radar reason tags onto the existing Phase 6
    `PreAnomalyReasonTag` / `AnomalyReasonTag` vocabulary so
    Reflection / Replay continue to work unchanged.
  - Calls the live `RiskEngine` with `stop_unconfirmed=True` so
    EVERY decision falls into the typed-reject-reason path. The
    Risk Engine emits `RISK_REJECTED` with the same
    `learning_ready` block.

#### Three new EventType entries (`app/core/events.py`)

```
PUBLIC_WS_CONNECTED
PUBLIC_WS_DISCONNECTED
PUBLIC_WS_STALE
```

The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
pipelines accept the new types unchanged.

#### Layered WS-first runner (`scripts/run_public_market_paper.py`)

- New CLI flags:
  - `--ws-first` / `--ws-disabled` (mutex; default `ws_first=True`).
  - `--candidate-pool-size N` (default 20).
  - `--active-detail-limit N` (default 3).
  - `--ws-staleness-threshold-ms MS` (default 3000).
  - `--candidate-ttl-seconds S` (default 900).
- Default `ws_first=True`. Under `--dry-run` the runner wires an
  `InProcessWSPump` and a `_push_dry_run_ws_messages` helper that
  pushes a deterministic burst of synthetic `!ticker@arr` /
  `!bookTicker` / `!markPrice@arr` per iteration so the radar /
  pool / chain pipeline can exercise every code path without a
  network.
- Without `--dry-run` AND with `--ws-first` (the Phase 11C.1B
  acceptance path): the runner calls
  `_build_real_public_ws_transport(config)` (module-level factory
  defaulting to `MultiTransportPublicWSManager`, which owns one
  routed `StdlibPublicWSTransport` per route - PUBLIC at
  `/public/stream`, MARKET at `/market/stream`). If the factory
  returns `None` or raises, **the runner refuses to start** with
  rc=2 and the message `real public WebSocket transport is
  required for --ws-first without --dry-run`. The runner does NOT
  silently fall back to the PR-A bootstrap-only REST path.
  Operators who cannot reach `fstream.binance.com` use the
  explicit `--ws-disabled` flag, documented as **not** the Phase
  11C.1B all-market demon-radar acceptance path.
- The pre-flight refusal happens BEFORE the REST symbol resolution
  call so a host with no public Binance access at all surfaces the
  refusal cleanly.
- Module-level `_build_rest_transport(*, dry_run)` factory mirrors
  the WS factory; tests monkey-patch both to drive the runner
  end-to-end without any real network.
- Per-loop body:
  1. pump WS messages -> `radar_buffer.ingest_messages`;
  2. score every symbol with new state via
     `pre_anomaly_score_light` and offer to the pool;
  3. `pool.expire()`;
  4. when `ws_client.is_stale=True`: increment
     `ws_data_degraded_ticks` and SKIP the active-head iteration
     (no PRE_ANOMALY_DETECTED / ANOMALY_DETECTED /
     STATE_TRANSITION events on stale data; safety flags
     unchanged);
  5. otherwise drive `WSRadarChainDriver` on the active head;
  6. feed the active head into `PublicMarketIngestor.ingest_many`
     so the existing MARKET_SNAPSHOT / Phase 4 contract continues
     to fire for those symbols (gated by the PR-A rate-limit
     governor).
- Banner: `[AMA-RT] Phase 11C.1B - WebSocket-First All-Market
  Demon Coin Radar v1.4.0a11c.1b ...` now also reports
  `ws_real_transport=...`. Exit banner reports `ws_real_transport`
  + `ws_data_degraded_ticks` + WS metrics + radar candidates +
  governor metrics on shutdown.

#### Daily report (`app/paper_run/daily_report.py`)

- `DailyReportBuilder.build()` accepts new `ws_metrics` +
  `candidate_pool_metrics` kwargs.
- `DailyReportSnapshot` grew the brief-mandated WS / radar fields:
  `ws_messages_received`, `ws_messages_received_by_stream`,
  `ws_reconnect_count`, `ws_staleness_ms_max`, `ws_stale_count`,
  `ws_connect_count`, `ws_disconnect_count`, `ws_is_stale`,
  `radar_candidates_seen`, `candidate_pool_size_max`,
  `pre_anomaly_candidates`, `liquidation_events_seen`,
  `radar_score_top_symbols`, `ws_metrics`,
  `candidate_pool_metrics`.
- `_aggregate` cross-checks the event-log counts of
  `PUBLIC_WS_CONNECTED` / `PUBLIC_WS_DISCONNECTED` /
  `PUBLIC_WS_STALE` against the WS client's `metrics_payload` so a
  stale governor counter cannot hide a real connection event.
- The Markdown body has a new
  `## Phase 11C.1B WebSocket all-market radar` section + per-stream
  message counts + a top-N candidate-symbol table.

#### Phase 1 safety lock UNCHANGED

Phase 11C.1B does NOT touch the Phase 1 safety lock. After running
the WS-first pipeline end-to-end (with PRE_ANOMALY_DETECTED /
ANOMALY_DETECTED / STATE_TRANSITION + RISK_REJECTED chains driven
from real-time WS data) every flag below remains:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client.

#### Phase 11C.1B explicitly does NOT

- accept any Binance API key / API secret / `listenKey`.
- subscribe to any user data stream / private WebSocket / trading
  WebSocket API / account / margin / position / leverage / balance
  / order private WS variant.
- open the routed-private endpoint
  `wss://fstream.binance.com/private` or any
  `/ws-api` / `/ws-fapi` / `/ws-papi` / `/trading-api` /
  `/userDataStream` path-root variant. `/private` is on
  `FORBIDDEN_WS_PATH_ROOTS`; the path-root allowlist refuses it
  before connect runs.
- treat the unrouted `wss://fstream.binance.com/stream` URL as
  the WS-first acceptance path. Binance silently drops
  market-class streams over an unrouted connection (per the
  public-WS reference); the runner therefore opens routed PUBLIC
  + MARKET transports through the `MultiTransportPublicWSManager`.
- call any signed REST endpoint.
- connect to DeepSeek / a real Telegram bot / Binance Square.
- import any third-party HTTP / WebSocket / SDK package. The
  `StdlibPublicWSTransport` and `MultiTransportPublicWSManager`
  are implemented entirely on top of the
  Python standard library (`socket` + `ssl` + `select` + `struct`
  + `base64` + `hashlib` + `json` + `os.urandom`) and the existing
  source-tree audit (`tests/unit/test_phase11c_no_network.py`)
  continues to ban `websockets` / `websocket-client` / `aiohttp`
  / `requests` / `httpx` / `urllib3`.
- silently fall back to REST under `--ws-first` without
  `--dry-run`. The runner refuses with rc=2 if the real public WS
  transport cannot be constructed; only `--ws-disabled` switches
  to the REST-only path (which is **not** the Phase 11C.1B
  acceptance path).
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c_1b_ws_radar.py` (new, 28 cases)
  pinning every brief-mandated behaviour:
  - `test_public_ws_stream_allowlist`
  - `test_private_ws_forbidden`
  - `test_listen_key_forbidden`
  - `test_user_data_stream_forbidden`
  - `test_default_ws_config_is_conservative`
  - `test_all_market_ticker_updates_radar_snapshot`
  - `test_book_ticker_updates_spread`
  - `test_mark_price_updates_funding`
  - `test_force_order_sets_liquidation_event`
  - `test_radar_score_detects_price_volume_acceleration`
  - `test_radar_score_falls_back_to_insufficient_history`
  - `test_candidate_pool_adds_top_radar_symbols`
  - `test_candidate_pool_expires_old_candidates`
  - `test_candidate_pool_evicts_lowest_score_when_over_capacity`
  - `test_ws_stale_enters_data_degraded`
  - `test_ws_disconnect_emits_disconnected_event`
  - `test_ws_reconnect_count_increments`
  - `test_ws_first_runner_does_not_call_rest_detail_for_all_symbols`
  - `test_ws_disabled_runner_falls_back_to_pra`
  - `test_learning_ready_payload_from_ws_candidate`
  - `test_safety_flags_unchanged_with_ws_enabled`
  - `test_default_ws_transport_refuses_to_open_a_real_socket`
  - `test_ws_client_subscribe_refuses_private_streams`
  - `test_ws_metrics_payload_includes_brief_field_set`
  - `test_candidate_pool_metrics_payload_includes_brief_field_set`
  - `test_radar_score_attaches_liquidation_event_tag`
  - `test_volume_rank_jump_admits_into_candidate_pool`
  - `test_phase_11c_1b_files_exist`
- `tests/unit/test_phase11c_no_network.py` extended:
  PHASE_11C_FILES grew the four new files (`binance_public_ws.py`,
  `radar.py`, `candidate_pool.py`, `ws_radar_chain.py`).
  `FORBIDDEN_TOP_LEVEL_PACKAGES` keeps every third-party WS
  package (`websockets`, `websocket`, `websocket_client`) on the
  deny list. New `test_no_private_websocket_artefacts` blocks
  `listenKey` / `userDataStream` / `wss://stream-api` /
  `/ws-api` / `/trading-api` / `/userDataStream` / `/listenKey`
  as non-docstring string literals across the source set.
- `tests/unit/test_phase11b_no_network.py` extended: allowed
  event-type list grew `PUBLIC_WS_CONNECTED` /
  `PUBLIC_WS_DISCONNECTED` / `PUBLIC_WS_STALE` so the
  daily-report aggregator's references pass.
- `tests/unit/test_phase11c1a_rate_limit_governor.py` updated:
  `test_rest_not_called_for_all_symbols_every_loop` now passes
  `--ws-disabled` so the PR-A bootstrap-only assertion holds
  byte-for-byte verbatim.

Full test suite: **2144 passed** with PR-B applied. No
regressions in the existing 2089-test surface; PR-B adds 55 net
new passing tests.

### Phase 11C.1A - Binance Public REST Rate Limit Governor & 418 Protection

**Version:** `1.4.0a11c.1a` - Phase 11C.1A. Tracks the Phase 11C
real-data acceptance recovery PR-A.

The first 24h test of the Phase 11C runner against real Binance
public REST (`fapi.binance.com`) returned HTTP 429 (Too Many
Requests) and then HTTP 418 (I'm a teapot, IP ban) at the original
defaults (`symbol_limit=20`, `rest_poll_interval_seconds=5.0`, six
detail endpoints per symbol per loop). The Phase 1 safety lock held
throughout (`mode=paper`, `live_trading=False`, no API key, no
signed endpoint, no real order, no DeepSeek, no real Telegram
outbound), but the gateway was unusable for real-data acceptance.

This PR-A ships the rate-limit fix in three layers without
reducing妖币-discovery capability or breaking the Phase 11C
boundary.

#### New module: `app/exchanges/binance_rate_limit.py`

- `BinancePublicRestGovernor` - sliding-window weight budget,
  Retry-After respecting backoff, IP-ban protection mode.
  - `before_request(endpoint_path)` - reserves the planned weight,
    refuses the call if the hard budget is exhausted
    (:class:`RateLimitBudgetExceeded`), if a Retry-After backoff
    window is still active (:class:`RateLimitBackoffActive`), or if
    protection mode is latched (:class:`RateLimitProtectionError`).
  - `record_response(endpoint_path, PublicRestResponse)` - reads
    `X-MBX-USED-WEIGHT-1M` (case-insensitive); on HTTP 429 emits
    `RATE_LIMIT_429` + `RATE_LIMIT_BACKOFF_STARTED`, sleeps the
    Retry-After window (300 s default), emits
    `RATE_LIMIT_BACKOFF_ENDED`; on HTTP 418 emits `RATE_LIMIT_418` +
    `RATE_LIMIT_PROTECTION_ENTERED`, opens a P1 incident through
    the configured protection hook (:class:`IncidentRepository`),
    and raises :class:`RateLimitProtectionError`.
  - `record_transport_error(endpoint_path)` - releases the
    reserved weight when the transport raises before producing a
    response so the rolling-window budget does not double-bill.
  - `metrics_payload()` - JSON-safe counters for the daily report.
- `RestGovernorConfig` - frozen dataclass with conservative defaults:
  `weight_budget_per_minute=300`, `soft_weight_ratio=0.50`,
  `hard_weight_ratio=0.75`, `retry_after_default_seconds=300`,
  `on_429="backoff"`, `on_418="shutdown"`,
  `endpoint_weights=DEFAULT_ENDPOINT_WEIGHTS`. Refuses pathological
  values at construction time.
- `PublicRestResponse(body, status, headers)` - transport-agnostic
  response envelope.
- `RateLimitProtectionError` (subclass of `SafeModeViolation`),
  `RateLimitBackoffActive`, `RateLimitBudgetExceeded`.
- `DEFAULT_ENDPOINT_WEIGHTS` for the Phase 11C public-market subset
  (`/fapi/v1/exchangeInfo`=1, `/fapi/v1/ticker/24hr`=40,
  `/fapi/v1/ticker/bookTicker`=5, `/fapi/v1/depth`=20,
  `/fapi/v1/aggTrades`=20, `/fapi/v1/trades`=5, `/fapi/v1/klines`=5,
  `/fapi/v1/fundingRate`=1, `/fapi/v1/openInterest`=1,
  `/fapi/v1/premiumIndex`=1).

The whole module uses only the Python standard library + loguru.
No third-party HTTP / WebSocket / SDK is imported; no `os.environ`
is read; no credential parameter is accepted; no write surface is
defined.

#### Wired into `BinancePublicClient`

- `BinancePublicClient.__init__(governor=...)` - new optional kwarg.
  When wired, every public REST request goes through the governor
  before reaching the transport.
- `_default_transport` upgraded to capture HTTP status + headers
  and return :class:`PublicRestResponse`. HTTP 429 / 418 are NOT
  raised - the envelope is handed to the governor so it can read
  Retry-After / used-weight / decide what to do.
- `_request` flow now: allowlist check -> `governor.before_request`
  -> transport call -> `governor.record_response` -> 200 returns the
  body, 429 raises `ExchangeError` after the governor's backoff,
  418 raises :class:`RateLimitProtectionError`.

#### Conservative new defaults (`app/config/defaults.yaml`)

| Knob                                         | Old   | New (Phase 11C.1A) |
| -------------------------------------------- | ----- | ------------------ |
| `market_data.symbol_limit`                   | 20    | 5                  |
| `market_data.rest_poll_interval_seconds`     | 5.0   | 60.0               |
| `market_data.rest_governor.weight_budget_per_minute` | -     | 300                |
| `market_data.rest_governor.soft_weight_ratio`        | -     | 0.50               |
| `market_data.rest_governor.hard_weight_ratio`        | -     | 0.75               |
| `market_data.rest_governor.retry_after_default_seconds` | -    | 300                |
| `market_data.rest_governor.on_429`           | -     | `backoff`          |
| `market_data.rest_governor.on_418`           | -     | `shutdown`         |
| `market_data.rest_governor.candidate_detail_limit`   | -     | 3                  |
| `market_data.rest_governor.rest_layering_enabled`    | -     | true               |

Each value is enforced by a Pydantic validator on
`RestGovernorSection`; pathological knobs are refused at boot.

#### Layered REST runner (`scripts/run_public_market_paper.py`)

- New `--candidate-detail-limit N` CLI flag (default from settings,
  3).
- New `--legacy-detail-per-loop` flag - off by default; documented
  as the original "every endpoint for every symbol every tick"
  behaviour that triggered the 418. Kept only for back-compat
  smoke tests.
- The runner builds a `BinancePublicRestGovernor` (with the
  `IncidentRepository` as the protection hook) and passes it to
  the public client.
- Bootstrap: one `exchangeInfo` (or one `ticker/24hr`) at boot to
  resolve the symbol list. Per-loop body iterates only the
  candidate symbols (empty in PR-A; populated by Phase 11C.1B
  PR-B), capped at `candidate_detail_limit`.
- Per-loop invariants pinned: `client.assert_public_only()`;
  governor metrics snapshot copied into `_Phase11CRunStats`.
- Hard stop on `governor.in_protection_mode`; runner returns
  `rc=2` when `rate_limit_protection_triggered=True`.
- Default `--symbol-limit` lowered to 5.

#### Daily report (`app/paper_run/daily_report.py`)

- `DailyReportBuilder.build()` now accepts `rate_limit_metrics` and
  `ingestion_errors` kwargs.
- `DailyReportSnapshot` grew the fields the brief calls out:
  `rate_limit_429_count`, `rate_limit_418_count`,
  `retry_after_seconds_last`, `retry_after_seconds_total`,
  `used_weight_1m_last`, `used_weight_1m_max`,
  `rest_requests_total`, `rest_requests_skipped_by_budget`,
  `rate_limit_protection_triggered`, `rate_limit_ban`,
  `rate_limit_backoff_started_count`,
  `rate_limit_backoff_ended_count`, `ingestion_errors`,
  `rate_limit_metrics`.
- `_aggregate` cross-checks the event-log counts (RATE_LIMIT_429,
  RATE_LIMIT_418, RATE_LIMIT_BACKOFF_STARTED,
  RATE_LIMIT_BACKOFF_ENDED, RATE_LIMIT_PROTECTION_ENTERED) against
  the governor's counters and uses the larger value so a stale
  governor cannot hide a real protection event.
- The Markdown body has a new "Phase 11C.1A rate-limit governor"
  section with every required field.

#### Five new EventType entries (`app/core/events.py`)

```
RATE_LIMIT_429
RATE_LIMIT_BACKOFF_STARTED
RATE_LIMIT_BACKOFF_ENDED
RATE_LIMIT_418
RATE_LIMIT_PROTECTION_ENTERED
```

The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
pipelines accept the new types without code changes (asserted by
`test_export_service_handles_rate_limit_events`).

#### Phase 1 safety lock UNCHANGED

Phase 11C.1A does NOT touch the Phase 1 safety lock. After a 429
**or** a 418, the following all remain:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise :class:`SafeModeViolation` even after the governor has
latched into protection mode (asserted by
`test_phase_11c_write_surfaces_still_refuse_after_418`).

#### Phase 11C.1A explicitly does NOT

- ship the WebSocket-first all-market radar (PR-B).
- ship multi-candidate priority ranking (PR-B).
- ship cluster exposure control (PR-C).
- accept any Binance API key / API secret.
- call any signed endpoint.
- call any /order, /account, /position, /leverage, /margin endpoint.
- connect to DeepSeek.
- connect to a real Telegram bot.
- auto-retry after a 418.
- switch endpoints to evade a 418.
- rotate source IP to evade a 418.
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c1a_rate_limit_governor.py` (new, 16 cases)
  - `test_default_phase11c_polling_is_conservative`
  - `test_rest_governor_config_refuses_pathological_values`
  - `test_429_triggers_backoff_and_stops_batch`
  - `test_retry_after_header_is_respected`
  - `test_used_weight_header_is_recorded`
  - `test_418_triggers_shutdown_without_retry`
  - `test_rest_governor_blocks_when_budget_exceeded`
  - `test_governor_refuses_during_active_backoff`
  - `test_rest_not_called_for_all_symbols_every_loop`
  - `test_legacy_detail_per_loop_flag_re_enables_old_behaviour`
  - `test_no_live_trading_flags_after_429`
  - `test_no_live_trading_flags_after_418`
  - `test_phase_11c_write_surfaces_still_refuse_after_418`
  - `test_daily_report_contains_rate_limit_metrics`
  - `test_daily_report_after_418_marks_rate_limit_ban`
  - `test_export_service_handles_rate_limit_events`
- `tests/unit/test_phase11c_safety_flags.py` updated to assert the
  new defaults (`symbol_limit=5`, `rest_poll_interval_seconds=60.0`,
  `rest_governor.*`).
- `tests/unit/test_phase11c_runner.py` updated:
  `test_arg_parser_default_symbol_limit_is_5`.
- `tests/unit/test_phase11b_no_network.py` allow-list extended with
  the five new RATE_LIMIT_* event types (the daily report
  aggregator references but never emits them; emission lives in
  `app/exchanges/binance_rate_limit.py` which is NOT a paper_run
  file).

Full test suite: **2089 passed in 7.17s** with PR-A applied. No
regressions in the existing 2073-test surface.

### Phase 11C - Real Binance Public Market Data Read-Only Paper

**Version:** `1.4.0a11c` - Phase 11C - Real Binance Public Market
Data Read-Only Paper. **Closes Issue #11C.**

Phase 11C is the FIRST phase in the project allowed to talk to a
real exchange. It is **public-market read-only** ingestion of
Binance USDT-M perpetual futures data, driven through the existing
Phase 1 - 11B paper pipeline. Phase 11C is NOT live trading, NOT
connected to the trading API, NOT connected to DeepSeek, NOT
connected to a real Telegram bot, NOT a path into Phase 12.

#### Public surface

- `app/exchanges/binance_public.py`
  - `BinancePublicClient` - public-market read-only Binance USDT-M
    perpetual gateway. Subclasses `ExchangeClientBase`; the four
    write surfaces (`create_order`, `cancel_order`, `set_leverage`,
    `set_margin_mode`) inherit `SafeModeViolation` refusal
    unchanged. `get_account_snapshot` is overridden to raise
    `SafeModeViolation` explicitly. Constructor refuses `api_key` /
    `api_secret` and any credential-shaped `**kwargs`.
  - `assert_public_endpoint_allowed(url)` - hard endpoint allowlist.
    Refuses any path not in the public-market set, any URL on a
    non-Binance host, any `http://` URL, any URL carrying
    `signature` / `timestamp` / `recvWindow` / `apiKey`.
  - `PUBLIC_MARKET_ENDPOINT_ALLOWLIST` - the closed list of paths
    Phase 11C is allowed to call.
  - `FORBIDDEN_PRIVATE_ENDPOINTS` - explicit deny-list of trading /
    account / position / leverage / margin endpoints.
  - `PublicMarkPrice` - mark + index + last funding + next funding
    envelope from `/fapi/v1/premiumIndex`.

- `app/market_data_public/`
  - `PublicMarketIngestor` - drives REST polling against
    `BinancePublicClient`, feeds the `MarketDataBuffer`, and
    produces enriched `MarketSnapshot` objects (mark_price + fresh
    book ticker on top of the Phase 4 contract).
  - `PaperEventChainDriver` - emits the full Phase 11C event chain
    per `(symbol, snapshot)`. Attaches a Phase 8.5
    `LearningReadyContext` (opportunity / signal_snapshot /
    virtual_trade_plan / config_versions) to every `RISK_REJECTED`
    and `STATE_TRANSITION`.

- `scripts/run_public_market_paper.py`
  - `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20`
  - `python -m scripts.run_public_market_paper --duration 6h --symbol-limit 20`
  - `python -m scripts.run_public_market_paper --duration 24h --symbol-limit 20`
  - Runs the Phase 11B `EnvGuard` against `BINANCE_API_KEY`,
    `BINANCE_API_SECRET`, `TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY`,
    ... before opening any database. Refuses to start if any
    forbidden credential env-var is set non-empty.
  - Pins `client.assert_public_only()` on every loop tick.
  - Builds a daily Markdown report at
    `data/reports/phase11c/{date}-phase11c-public-market.md` on
    graceful shutdown.
  - `--dry-run` swaps the default `urllib.request` transport for an
    in-process deterministic transport so CI / smoke tests never
    touch the network.

#### New configuration

`app/config/defaults.yaml` gains two top-level sections, each
strictly validated by Pydantic field-validators in
`app/config/schema.py`:

- `market_data:` - `provider: binance_public` (only allowed value),
  `read_only: true` (cannot be flipped), `symbol_limit: 20` (in
  `(0, 200]`), `rest_base_url: https://fapi.binance.com`, plus
  feature flags for the public surfaces.
- `safety:` - 11 `forbid_*` flags. The schema raises
  `ValidationError` if any of them is loaded as `False`.

`Settings` exposes the Phase 11C convenience accessors
`Settings.market_data`, `Settings.safety`,
`Settings.telegram_outbound_enabled`.

#### No new EventType

Phase 11C reuses the existing Phase 1 - 10D vocabulary. The chain
emits `MARKET_SNAPSHOT`, `PRE_ANOMALY_DETECTED`,
`ANOMALY_DETECTED`, `LIQUIDITY_CHECKED`, `TRADE_CONFIRMED`,
`MANIPULATION_DETECTED`, `RISK_APPROVED` / `RISK_REJECTED`,
`STATE_TRANSITION` per symbol per tick.

#### Phase 11C boundary (every clause enforced by tests)

  1. **No live trading.** The five Phase 1 safety flags remain locked.
     `telegram_outbound_enabled` and `binance_private_api_enabled`
     are both False.
  2. **No API key.** The constructor refuses `api_key` /
     `api_secret`. `tests/unit/test_phase11c_binance_public_client.py`
     pins both refusal paths.
  3. **No signed endpoint.** Every URL goes through
     `assert_public_endpoint_allowed`. The function refuses every
     entry in `FORBIDDEN_PRIVATE_ENDPOINTS` and every URL carrying
     a `signature` / `timestamp` / `recvWindow` / `apiKey` query
     parameter.
  4. **No third-party HTTP / WebSocket / exchange / LLM / Telegram
     SDK.** Phase 11C uses `urllib.request` from the Python standard
     library only. `tests/unit/test_phase3_no_network.py` and
     `tests/unit/test_phase11c_no_network.py` AST-audit the source
     set.
  5. **The four ExchangeClientBase write surfaces remain refused.**
     Inherited from Phase 3.
  6. **`MarketDataConfig.read_only` cannot be set to False** at the
     schema layer.
  7. **`SafetyConfig.forbid_*` cannot be set to False** at the
     schema layer.
  8. **No `os.environ` read** anywhere in the Phase 11C source set.
     Env inspection is delegated to the Phase 11B `EnvGuard`.
  9. **No `create_order` / `cancel_order` / `set_leverage` /
     `set_margin_mode` call.** AST-audited.

#### Phase 11C does NOT implement

  - Real WebSocket transport (the `websocket_enabled` flag is
    accepted as a future-capability hook; Phase 11C ships the REST
    poller only).
  - Real account / position / equity persistence (the public client
    refuses every authenticated endpoint).
  - Any LLM / DeepSeek / Telegram / 币安广场 surface.
  - Phase 12. Passing Phase 11C does NOT authorise Phase 12.

#### Tests

  - `tests/unit/test_phase11c_binance_public_client.py` - construction,
    credential refusal, endpoint allowlist (positive + negative),
    read-only API behaviour, MarketSnapshot serialization.
  - `tests/unit/test_phase11c_event_chain.py` - end-to-end event
    chain + learning-ready payload + STATE_TRANSITION carries
    learning_ready.
  - `tests/unit/test_phase11c_safety_flags.py` - the five Phase 1
    flags + 11 Phase 11C `forbid_*` flags + write-surface refusal
    + LLM-decision boundary + signed-query-parameter refusal.
  - `tests/unit/test_phase11c_runner.py` - argparse, duration parser,
    dry-run smoke, env-guard refusal, host refusal.
  - `tests/unit/test_phase11c_no_network.py` - source-tree audit.
  - `tests/unit/test_phase11c_export_and_replay.py` - Phase 8.5
    export round-trip + Phase 10A replay round-trip + Phase 10B
    Reflection compatibility.
  - `tests/unit/test_phase11c_telegram_outbound.py` - reviewer-
    requested defence-in-depth on the
    `telegram_outbound_enabled` semantics. Pins:
    `Settings.telegram_outbound_enabled` reads
    `defaults.telegram.outbound_enabled`, NOT
    `defaults.telegram.enabled`; the schema refuses
    `outbound_enabled=True`; the Phase 11C runtime source set
    imports no real Telegram transport
    (:class:`TelegramHttpClient` /
    :class:`TelegramExportBridge` /
    :class:`TelegramCommandCenter`).

Total Phase 11C coverage: 112 new tests; 0 failures; full suite
2071 passed.

#### Phase 1 - 10D contracts that remain in force

All Phase 1 - 10D contracts remain in force unchanged. Phase 11C
ADDS one new exchange client + one new ingestion package + one new
runner + four documentation files; it does NOT modify any existing
event type, any existing schema field, or any existing safety
constant.

### Phase 10D - Telegram Outbound + Export Commands (Issue #10 Part 4)

**Version:** `1.4.0a10d` - Phase 10D - Telegram Outbound + Export Commands.

Phase 10D ships the operator-facing :mod:`app.telegram` outbound
layer plus the file-export bridge layered on top of the Phase 8.5
:class:`TestDataExportService`. **Closes Issue #10**.

Public surface
--------------

  - 10 production-grade formatters that replace the Phase 1
    placeholders: ``format_system_status``, ``format_market_regime``,
    ``format_candidate_symbol``, ``format_state_transition``,
    ``format_order_event``, ``format_risk_rejection``,
    ``format_profit_lock``, ``format_capital_rebase``,
    ``format_incident_alert``, ``format_daily_report``. Every
    formatter is a pure function (string in, string out, no IO),
    short, banner-tagged with ``mode=PAPER|LIVE_LIMITED|LIVE``,
    redacted, and free of trade-decision side effects. The
    risk-rejection formatter MUST surface six high-priority reasons
    when present: ``stop_unconfirmed``, ``unknown_position``,
    ``rebase_in_progress``, ``manipulation_m3``, ``data_degraded``,
    ``no_exit_channel``.
  - :class:`TelegramOutboundClient` ABC + :class:`FakeTelegramClient`
    (deterministic in-process recorder; default transport for paper
    mode) + :class:`TelegramHttpClient` (refusal-only HTTP skeleton -
    every call raises :class:`TelegramTransportError`; the real
    transport ships behind Spec §41 Go/No-Go in a separate PR).
  - :class:`AlertDispatcher` proactive push pipeline. Per-key
    cooldown + dedupe; ``AlertSeverity`` ladder (INFO / WARNING /
    CRITICAL); CRITICAL bypasses cooldown; auto-promotion of
    ``stop_unconfirmed`` / ``unknown_position`` to CRITICAL;
    aggregation of low-severity risk rejections into a rolling
    10-minute summary; defence-in-depth redaction gate via
    :func:`app.exports.redaction.assert_no_forbidden_substrings`.
  - :class:`TelegramCommandCenter` 16-command operator surface:
    ``/status`` ``/positions`` ``/pnl`` ``/risk`` ``/capital``
    ``/incidents`` ``/pause`` ``/resume`` ``/kill_all`` ``/rebase``
    + 6 ``/export_*`` commands. Operator allow-list, two-step
    confirmation for ``/resume`` + ``/rebase``, audit events for
    every command (``TELEGRAM_COMMAND_RECEIVED``,
    ``TELEGRAM_COMMAND_REJECTED``).
  - :class:`TelegramExportBridge` connects ``/export_*`` to the
    Phase 8.5 :class:`TestDataExportService`. Sends a SHORT
    generating-summary caption + the redacted ``.zip`` document
    attachment in a single ``send_document`` call. Refuses
    chat-dump of raw JSONL/CSV. Audit events:
    ``DATA_EXPORT_GENERATED`` / ``DATA_EXPORT_FAILED``.

Five new EventType values
-------------------------

  - ``TELEGRAM_COMMAND_REJECTED`` - non-admin / unknown command paths
  - ``TELEGRAM_MESSAGE_SENT`` - every successful proactive push
  - ``TELEGRAM_SEND_FAILED`` - every transport / redaction failure
  - ``DATA_EXPORT_GENERATED`` - successful ``/export_*`` zip + send
  - ``DATA_EXPORT_FAILED`` - every export failure path

Boot drill (`python -m app.main`)
---------------------------------

```
[AMA-RT] Phase 10D - Telegram Outbound + Export Commands v1.4.0a10d \
  mode=paper live_trading=False right_tail=False llm=False \
  exchange_live_orders=False ... (Phase 1-10C fields unchanged) ... \
  telegram_outbound_enabled=False telegram_messages_sent=10 \
  telegram_documents_sent=1 telegram_send_failed_count=0 \
  telegram_redaction_blocked=0 telegram_message_sent_events=11 \
  telegram_send_failed_events=0 telegram_command_rejected_events=1 \
  data_export_generated=1 data_export_failed=0 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

The Phase 10D self-check runs after the Phase 10C self-check. It:

  - dispatches one alert through every formatter (10 messages_sent),
  - drives one ``/export_test_data 24h`` end-to-end through the
    bridge (1 documents_sent + 1 ``DATA_EXPORT_GENERATED``),
  - drives one unauthorised ``/status`` (1 ``TELEGRAM_COMMAND_REJECTED``),
  - asserts zero ``TELEGRAM_SEND_FAILED``, zero ``redaction_blocked``,
  - asserts every recorded outbound call is free of forbidden
    literals (``BINANCE_API_KEY=``, ``TELEGRAM_BOT_TOKEN=``, etc.),
  - registers a new ``telegram_outbound`` health probe (always OK
    when the transport is the FakeClient).

Phase 10D boundary (every clause enforced by tests)
---------------------------------------------------

  1. **No real network call.** The default outbound transport is
     :class:`FakeTelegramClient`. The :class:`TelegramHttpClient` is
     a refusal-only skeleton; even when ``outbound_enabled=True``
     and ``token_provided=True`` it raises
     :class:`TelegramTransportError`.
  2. **No write surface.** No file under ``app/telegram/`` defines
     ``create_order`` / ``cancel_order`` / ``set_leverage`` /
     ``set_margin_mode``.
  3. **No Telegram command bypasses the Risk Engine.** ``/pause`` /
     ``/resume`` flip an in-process advisory flag only.
  4. **``/kill_all``** records audit events but does NOT call any
     real exchange write surface in Phase 10D.
  5. **``/rebase``** does NOT execute a real withdrawal; the Phase 8
     Capital Flow Engine remains the only entry point.
  6. **No state-mutating component import** under
     ``app/telegram/``. AST scan blocks ``RiskEngine`` /
     ``ExecutionFSMDriver`` / ``CapitalFlowEngine`` / etc.
  7. **No third-party Telegram bot library imported.** AST scan
     blocks ``python_telegram_bot`` / ``telebot`` / ``aiogram``.
  8. **No HTTP / WebSocket library imported.** AST scan blocks
     ``aiohttp`` / ``httpx`` / ``requests`` / ``websockets``.
  9. **No exchange / LLM SDK imported.** AST scan blocks ``ccxt`` /
     ``binance`` / ``openai`` / ``anthropic`` / ``deepseek``.
  10. **No ``os.environ`` reads.** Credentials must be passed in
      explicitly. AST scan blocks ``os.environ.get`` / ``os.getenv``
      / bare ``getenv()``.
  11. **No hard-coded secret.** AST scan blocks ``api_key`` /
      ``api_secret`` / ``bot_token`` / ``telegram_token`` parameters
      or concrete env-var literals.
  12. **No exception escapes.** Dispatcher / command center /
      export bridge NEVER raise into the caller.
  13. **No raw chat dump.** The bridge attaches the ``.zip`` as a
      Telegram document; ``ExportError`` / size-cap exceeded paths
      reply with a SHORT error message and write
      ``DATA_EXPORT_FAILED``.
  14. **Defence-in-depth redaction.** Every outbound message goes
      through :func:`app.exports.redaction.assert_no_forbidden_substrings`
      before reaching the transport.
  15. **The Phase 1 safety lock remains in force.**

Tests
-----

Phase 10D adds the following test files under ``tests/unit/``:

  - ``test_telegram_formatter.py`` (rewritten): 10 formatters, every
    mandatory tag, every high-priority risk-rejection reason,
    redaction smoke tests, mode banner + live flag.
  - ``test_telegram_outbound.py``: ABC cannot be instantiated;
    FakeTelegramClient records calls; HTTP refuses; failure
    injection.
  - ``test_telegram_alerts.py``: throttle / dedupe / severity ladder
    / cooldown / P0 bypass / aggregation flush / redaction gate.
  - ``test_telegram_command_center.py`` (extends Phase 1): 16
    commands; allow-list; two-step confirmation; audit events;
    ``/kill_all`` / ``/rebase`` paper-mode safety.
  - ``test_telegram_export_bridge.py``: ``/export_*`` -> service ->
    generating caption + sendDocument; ``DATA_EXPORT_GENERATED`` /
    ``DATA_EXPORT_FAILED``; size-cap refusal path.
  - ``test_phase10d_boundary.py``: cumulative defence-in-depth pins.
  - ``test_phase10d_no_network.py``: per-file AST scan of
    ``app/telegram/``.

Live trading risk: NONE.

  - ``requirements.txt`` and ``pyproject.toml`` contain no exchange
    SDK, no HTTP / WebSocket / LLM client, no Telegram bot library.
  - No source under ``app/telegram/`` imports ``ccxt``, ``binance``,
    ``aiohttp``, ``websockets``, ``requests``, ``httpx``,
    ``openai``, ``anthropic``, ``deepseek``,
    ``python_telegram_bot``, ``telebot``, or ``aiogram``.
  - No source under ``app/telegram/`` defines ``create_order`` /
    ``cancel_order`` / ``set_leverage`` / ``set_margin_mode``.
  - No source under ``app/telegram/`` reads ``os.environ`` or
    declares an ``api_key`` / ``api_secret`` / ``bot_token``
    parameter / concrete env-var literal.
  - The Phase 1 safety lock and every later boundary remain
    unchanged.

Real exchange order risk: NONE. ``/kill_all`` and ``/rebase`` write
audit events only. The four :class:`ExchangeClientBase` write
surfaces continue to raise :class:`SafeModeViolation`.

Telegram token leak risk: NONE. No token parameter or literal
anywhere under ``app/telegram/``. The :class:`TelegramHttpClient`
constructor accepts a boolean ``token_provided`` flag instead of a
real token.

LLM overreach risk: NONE. Phase 10D does NOT call the LLM Guarded
Interpreter; the Risk Engine remains the single trading-decision
gate.

### Phase 10C - LLM Guarded Interpreter (Issue #10 Part 3)

**Version:** `1.4.0a10c` - Phase 10C - LLM Guarded Interpreter.

Phase 10C adds the receive-only :mod:`app.llm` package: a sandboxed,
schema-validated, never-trading LLM intelligence layer that
compresses community / catalyst / narrative text into a small,
strictly typed intelligence payload (Spec §22). The output is
*purely informational*; it never carries a trade direction, a
leverage, a target price, an order, a stop, or any other field that
could move money. The Risk Engine remains the single gate.

Public surface
--------------

  - `LLMGuardedInterpreter` - top-level orchestrator. Constructor
    is keyword-only: `(*, client, event_repo=None, config=None,
    cache=None, llm_enabled=False)`. `interpret(input)` NEVER
    raises into the caller; every transport / schema / guardrail
    failure becomes a degraded :class:`LLMInterpretationResult`.
  - `LLMInterpreterConfig` - tunable thresholds (Spec §22.4
    anomaly-score throttle: <60 -> SKIP, 60-75 -> LIGHT,
    75-90 -> STANDARD, >=90 -> FULL).
  - `LLMTokenBucket` - in-process Spec §22.4 throttle classifier.
  - `LLMInterpretationInput` / `LLMInterpretationResult` - frozen
    dataclasses; `to_payload()` is JSON-safe and provably free of
    forbidden trade-action fields.
  - `FakeLLMClient` - deterministic in-memory transport used by
    tests AND the boot self-check.
  - `DeepSeekClient` - refusal-only skeleton. Refuses unless
    `llm_enabled=True` AND `api_key_provided=True`; refuses anyway
    in Phase 10C. The real adapter ships behind Spec §41 Go/No-Go.
  - `LLMCache` - LRU cache keyed on `(input_hash, prompt_version,
    schema_version, model_name, throttle_tier, symbol)`. **Refuses
    to store credential keys**.
  - `validate_llm_output` - pure-function Spec §22.2 schema
    validator. No external dependency (we deliberately do NOT add
    `jsonschema` to `requirements.txt`).
  - `sanitize_input_text` - light-touch input cleaner (NFC, control
    chars, whitespace, max-len). Preserves prompt-injection markers
    so the detector can still flag them.
  - `detect_prompt_injection` - 12-pattern regex sniffer.
  - `enforce_field_whitelist` - drops any output key outside the
    Spec §22.2 closed schema.
  - `strip_forbidden_fields` - drops + records any trade-action
    key (`direction`, `leverage`, `position_size`, `target_price`,
    `order_type`, `stop_price`, `take_profit`, `should_buy`,
    `should_short`, `trade_decision`, `entry`, `exit`,
    `liquidation_price`, `margin_mode`, `risk_budget`, `order`,
    `signal_to_trade`).
  - Three new EventType values: `LLM_INTERPRETED`, `LLM_DEGRADED`,
    `LLM_SCHEMA_REJECTED`. The interpreter is the only Phase 10C
    write surface; tests assert it is limited to these three event
    types.

Boot drill (`python -m app.main`)
---------------------------------

```
[AMA-RT] Phase 10C - LLM Guarded Interpreter v1.4.0a10c mode=paper \
  live_trading=False right_tail=False llm=False exchange_live_orders=False \
  ... (Phase 1-10B fields unchanged) ... \
  llm_interpreter_degraded=True llm_interpreter_reasons=llm_disabled \
  llm_events=1 llm_degraded_count=1 llm_interpreted_events=0 \
  llm_degraded_events=1 llm_schema_rejected_events=0 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

The boot self-check exercises the interpreter end-to-end against a
deterministic :class:`FakeLLMClient` with `llm_enabled=False`. It
asserts:

  - `result.degraded == True`
  - `'llm_disabled' in result.degraded_reason_values`
  - `result.to_payload()` is free of forbidden trade-action fields
  - `fake_llm_client.calls == 0` (the transport was NOT invoked)
  - exactly one `LLM_DEGRADED` event was written to `events.db`

Phase 10C boundary
------------------

1. **No real network call by default.** No `aiohttp` / `httpx` /
   `requests` / `websockets` / `ccxt` / `binance` / `openai` /
   `anthropic` / `deepseek` import anywhere under `app/llm/`. The
   default transport is `FakeLLMClient`.
2. **No write surface.** No file under `app/llm/` defines
   `create_order` / `cancel_order` / `set_leverage` /
   `set_margin_mode`.
3. **No LLM-driven trade action.** Closed output schema; forbidden
   fields stripped + recorded; result degraded if any forbidden
   field was present.
4. **No state-mutating component import.** No `RiskEngine`,
   `ExecutionFSMDriver`, `Reconciler`, `CapitalFlowEngine`,
   `IncidentRepository`, `MockExchangeClient`, `BinanceClient`,
   `MarketDataBuffer`, `TelegramCommandCenter`, `RegimeEngine`.
5. **No `os.environ` reads.** Credentials must be passed in
   explicitly by the caller.
6. **No hard-coded secret.** No `api_key` / `api_secret` /
   `bot_token` parameter or concrete literal anywhere under
   `app/llm/`.
7. **No exception escapes.** The interpreter NEVER raises into the
   caller.
8. **No Telegram outbound.** Phase 10D owns that surface.
9. **No Issue #10 Part 10D work.**
10. **Phase 1 safety lock unchanged.** `llm_enabled` stays
    `False` at boot.

Tests
-----

Phase 10C adds nine new test files under `tests/unit/`:

  - `test_llm_models.py` - vocabularies + result schema pinned
  - `test_llm_schema.py` - validator behaviour
  - `test_llm_prompts.py` - system prompt content + version pinned
  - `test_llm_guardrails.py` - whitelist / forbidden / injection
    detector / sanitizer
  - `test_llm_cache.py` - LRU + credential refusal
  - `test_llm_client.py` - FakeLLMClient + DeepSeekClient skeleton
  - `test_llm_interpreter.py` - end-to-end (Issue acceptance #1-#18)
  - `test_phase10c_boundary.py` - cumulative defence-in-depth
  - `test_phase10c_no_network.py` - per-file AST scan

`tests/unit/test_main_entrypoint.py` extended to assert the
Phase 10C banner string and the LLM event counts.

Live trading risk
-----------------

**None.** No new exchange SDK, no HTTP / WebSocket / LLM client, no
Telegram bot library is added. The four `ExchangeClientBase` write
surfaces continue to raise `SafeModeViolation`. Phase 1 safety
lock remains in force.

LLM overreach risk
------------------

**None.** Phase 10C does NOT introduce a real LLM transport. The
`DeepSeekClient` is a refusal-only skeleton; even when
`llm_enabled=True` and `api_key_provided=True` it raises
`TransportError`. The result schema is closed; the guardrail
strips every forbidden trade-action field; the orchestrator never
calls the Risk Engine, the Execution FSM, the Capital Flow Engine,
or any write surface.


### Phase 10B - Reflection Engine (Issue #10 Part 2)

Phase 10B delivers the read-only Reflection Engine on top of the
Phase 10A Replay Engine. The engine consumes one
`PaperTradeReplay` plus the surrounding Phase 10A risk / state /
incident replays plus the Phase 8.5 `learning_ready` payload, and
produces one structured `ReflectionResult` per paper-trade
lifecycle. The result carries a typed `mistake_tags` list (drawn
from a frozen 12-issue + 3-diagnostic vocabulary - **no
free-form natural-language reflection** is produced),
deterministic MFE / MAE / `tail_contribution` metrics
(`None` when data is insufficient, NEVER fabricated), and four
`QualityScore` axes. This is **Part 2 of 4** of Issue #10; Parts
10C (LLM Guarded Interpreter) and 10D (Telegram outbound +
Export commands) ship in separate PRs. Issue #10 will be closed
by Part 10D.

#### Added

##### `app/reflection/` - Reflection Engine

- `ReflectionEngine(replay=, event_repo=, config=)` - read-only
  constructor. Construct from a wired `ReplayEngine` (preferred)
  or from an `EventRepository` (the engine will build its own
  ReplayEngine). Phase 10B does NOT re-implement Replay; it
  consumes the existing Phase 10A surface.
- `ReflectionEngine.reflect_paper_trade(client_order_id=,
  opportunity_id=)` - reflect on one paper-trade lifecycle,
  identified by either key. The engine asks Replay for the
  surrounding context (risk decisions for the symbol, state
  transitions for the symbol, P0 incidents in the window).
- `ReflectionEngine.reflect(input)` - lower-level entry point
  taking a `ReflectionInput` directly; tests use this to inject
  hand-crafted context.
- `ReflectionConfig` - tunable thresholds for tag-rule firing
  (`late_entry_pct`, `slippage_overrun_pct`,
  `execution_delay_ms`, `weak_volume_anomaly_threshold`,
  `trap_score_threshold`).

##### Value objects

- `ReflectionResult` - frozen dataclass with the Issue-mandated
  field set: `opportunity_id`, `client_order_id`, `symbol`,
  `setup`, `result`, `mistake_tags`, `mfe`, `mae`,
  `tail_contribution`, `entry_quality`, `exit_quality`,
  `risk_process_quality`, `execution_quality`,
  `data_quality_notes`, `source_event_ids`, `learning_ready`,
  `generated_at`. JSON-safe via `to_payload()`.
- `ReflectionInput` - frozen dataclass bundling
  `paper_trade: PaperTradeReplay` plus optional
  `risk_decisions`, `state_transitions`, `incidents`,
  `learning_ready` so callers can drive the engine without
  Replay re-reading events.db.
- `QualityScore` - HIGH / MEDIUM / LOW / UNKNOWN.
- `TradeOutcome` - WIN / LOSS / BREAKEVEN / PROTECTED / OPEN /
  UNKNOWN.
- `UnknownReason` - typed "data insufficient" reason vocabulary
  (11 reasons; the engine NEVER invents a free-form reason).

##### Mistake-tag vocabulary

- `MistakeTag` - frozen 15-value enum:

  Issue-required (12):
  `late_entry`, `early_exit`, `weak_volume`, `fake_breakout`,
  `high_trap_score`, `ignored_no_trade_gate`, `slippage_error`,
  `execution_delay`, `stop_not_confirmed`, `tail_saved_trade`,
  `tail_failed`, `right_tail_success`.

  Diagnostic (Phase 10B):
  `insufficient_data`, `no_lifecycle_observed`,
  `incident_during_lifecycle`.

- `ISSUE_REQUIRED_MISTAKE_TAGS` / `DIAGNOSTIC_MISTAKE_TAGS`
  frozensets so consumers can iterate / filter without
  re-listing the strings.

##### Metric helpers (deterministic)

- `compute_mfe(events, *, direction_long=, entry_price=)` -
  Maximum Favourable Excursion as an absolute price delta.
  Returns `MetricResult(value=None,
  unknown_reasons=(...))` when fewer than two price observations
  are available (Phase 9 paper-mode landmarks-only case) or
  when no fill price is recorded.
- `compute_mae(events, ...)` - Maximum Adverse Excursion;
  same insufficient-data semantics.
- `compute_tail_contribution(events=, state_transitions=,
  realized_pnl=, virtual_trade_plan=)` - tail PnL attribution.
  Returns 0.0 when no `RIGHT_TAIL_AMPLIFY` lifecycle was
  observed AND a virtual_trade_plan was supplied (we can confidently
  say zero); returns `None` when no RTA was observed AND no plan
  is available.
- `realized_pnl_for(events)` - read realised PnL off the closing
  event payload.
- `MetricResult` - `value: float | None` plus
  `unknown_reasons: tuple[UnknownReason, ...]`.

##### Tag-rule emission rules

- `stop_not_confirmed`: `summary.stop_confirmed == False` OR a
  `STOP_FAILED` event landed in the lifecycle.
- `ignored_no_trade_gate`: a `RISK_REJECTED` for the same
  `opportunity_id` precedes an `ORDER_SENT` for the same
  `opportunity_id`. (This MUST NOT happen in Phase 9; the tag
  fires loudly if it does.)
- `slippage_error`: `|fill_price - limit_price| / limit_price`
  exceeds the request's `max_slippage_pct` AND the engine-level
  threshold (defence in depth).
- `execution_delay`: `ack_ts - sent_ts` exceeds
  `ReflectionConfig.execution_delay_ms` (default 1500ms).
- `late_entry`: `|fill_price - virtual_entry| / virtual_entry`
  exceeds `ReflectionConfig.late_entry_pct` (default 0.5%).
  Requires `virtual_trade_plan`; otherwise unknown.
- `weak_volume`: `signal_snapshot.anomaly_score` below
  `ReflectionConfig.weak_volume_anomaly_threshold` (default
  50.0). Requires `signal_snapshot`; otherwise unknown.
- `high_trap_score`: `signal_snapshot.trap_score` >=
  `ReflectionConfig.trap_score_threshold` (default 0.6) OR
  `signal_snapshot.no_trade_reason` contains a `trap` substring.
- `fake_breakout`: state chain shows a transition INTO
  `confirm` / `attack` followed immediately by a transition INTO
  `observe` / `scout` / `no_trade`.
- `tail_saved_trade`: lifecycle entered `right_tail_amplify`
  AND closed with `realized_pnl > 0`.
- `tail_failed`: lifecycle entered `right_tail_amplify` AND
  closed with `realized_pnl < 0`.
- `right_tail_success`: lifecycle entered `right_tail_amplify`
  AND a recorded mark / last / exit price reached or exceeded
  `virtual_trade_plan.virtual_tp2`.
- `early_exit`: position closed below `virtual_tp1` (LONG plan)
  or above it (SHORT plan). Requires plan + close price.
- `incident_during_lifecycle`: any incident's open / resolve
  timestamp falls inside the lifecycle window, or the incident
  window straddles the lifecycle.
- `insufficient_data`: any data-quality note landed AND no
  Issue-required tag fired.

##### Boot drill (`python -m app.main`)

The entrypoint runs the Phase 10B self-check **after** the
Phase 10A self-check. The self-check reflects on the boot
paper-trade lifecycle and asserts:

  - the result is `breakeven` (boot drill closes at PnL=0);
  - the `client_order_id` matches the boot order;
  - `source_event_ids` is non-empty;
  - no Issue-required `mistake_tag` fires (the diagnostic
    `insufficient_data` tag MAY fire because the boot drill
    does not attach a `virtual_trade_plan` / `signal_snapshot`,
    which is an honest "we cannot tell" signal).

If any of these contracts diverges, the entrypoint refuses to
print the banner and exits non-zero.

The boot banner gains four Phase 10B fields:

```
reflection_setup=unknown reflection_result=breakeven
reflection_mistake_tags=1 reflection_data_quality_notes=4
```

A new `reflection_engine` health probe registers `OK` when no
Issue-required `mistake_tag` fired, `DEGRADED` otherwise.

##### Documentation + version bump

- `app/__init__.py` -> `1.4.0a10b` /
  `Phase 10B - Reflection Engine`.
- `pyproject.toml` -> `1.4.0a10b`.
- `README.md` -> Phase 10B deliverable + boundary section +
  status table updated (Phase 10A marked merged with PR #23,
  Phase 10B = "this branch", Parts 10C / 10D listed as open).
- `docs/CHANGELOG.md` -> Phase 10B entry prepended; Phase 10A
  entry preserved verbatim below.

#### Phase 10B boundary

1. **Read-only.** Reflection imports no state-mutating
   component (no `CapitalFlowEngine`, no `ExecutionFSMDriver`,
   no `Reconciler`, no `RiskEngine`, no `IncidentRepository`,
   no `MockExchangeClient`, no `BinanceClient`, no
   `MarketDataBuffer`, no `TelegramCommandCenter`, no
   `RegimeEngine`). AST scan enforces this on every file under
   `app/reflection/`.
2. **No write surface.** No file under `app/reflection/`
   defines `create_order` / `cancel_order` / `set_leverage` /
   `set_margin_mode`. AST scan enforces this.
3. **No `EventRepository.append_event` / `append_many`** call
   anywhere in `app/reflection/`. AST scan enforces this; the
   boot self-check confirms `events.count` is unchanged after
   the Reflection self-check runs.
4. **No socket / no exchange SDK / no LLM client / no Telegram
   bot library.** AST scan enforces this against every `.py`
   file under `app/reflection/`.
5. **No `os.environ` / `getenv` reads** anywhere in
   `app/reflection/`. AST scan enforces this.
6. **No `api_key` / `api_secret` / `bot_token` parameter or
   concrete literal** anywhere in `app/reflection/`. AST scan
   enforces this.
7. **Read-only against `events.db` only.** No file under
   `app/reflection/` opens any other database directly.
8. **No Issue #10 Part 10C / 10D work.** No LLM client, no
   Telegram outbound, no Export commands.
9. **No free-form natural-language reflection.** Every
   observation lands as one of the values in `MistakeTag`.

#### Defence in depth (cumulative, all unit-tested)

1. `app/config/settings.py::_apply_phase1_safety_lock()`
   overwrites the five flags after YAML + env loading.
2. `app/main.py::_assert_phase1_safety()` raises
   `SafetyViolation` at boot if any flag has drifted.
3. `app/main.py::_assert_phase3_read_only()` probes every
   banned write surface and raises `SafeModeViolation` if any
   of them stops refusing.
4. `app/main.py::_assert_phase9_no_live_writes()` confirms the
   FSM driver constructed under paper-mode flags.
5. `app/risk/engine.py` rejects `live_trading_required=True`,
   `right_tail_amplify=True`, every Phase 6 / 7 / 8 hard-rule
   branch.
6. `app/exchanges/base.py::ExchangeClientBase.{create_order,
   cancel_order, set_leverage, set_margin_mode}` always raise
   `SafeModeViolation`.
7. `app/execution/fsm.py::ExecutionFSMDriver.__init__` raises
   `SafeModeViolation` if any of the three trading flags has
   drifted.
8. `MarginMode` enum cannot construct a cross-margin
   `OrderRequest` even via typo.
9. `StopEvent` cannot construct a non-reduce-only stop even
   via typo.
10. **Phase 10A:** AST scans on every `.py` under
    `app/replay/` enforce no network / no SDK / no API key /
    no write surface / no `os.environ` / no
    `EventRepository.append_event` / no state-mutating
    component import.
11. **Phase 10B adds:** AST scans on every `.py` under
    `app/reflection/` enforce the same set of clauses, plus
    no LLM client import (deferred to Part 10C), no
    `MistakeTag` / `ReflectionResult` mutation surface (the
    value objects are frozen).

#### Live trading risk

**None.** Phase 10B adds no new `create_order` / `cancel_order`
/ `set_leverage` / `set_margin_mode` call site. The four
`SafeModeViolation` refusals on `ExchangeClientBase` continue
to apply.

### Phase 10A - Replay Engine (Issue #10 Part 1)

Phase 10A delivers the read-only Replay Engine on top of every
Phase 1-9 contract. The engine reconstructs paper trade
lifecycles, capital rebases, risk decisions, P0 incidents, trade
state transitions, telegram commands, and Phase 8.5
learning-ready payloads from `events.db`, plus a P0 latched-pause
invariant verifier that audits the Phase 9 fix-up rule (PR #22).
This is **Part 1 of 4** of Issue #10; Parts 10B (Reflection),
10C (LLM Guarded Interpreter) and 10D (Telegram outbound +
Export commands) ship in separate PRs.

#### Added

##### `app/replay/` - Replay Engine

- `ReplayEngine(event_repo)` - read-only constructor. The engine
  holds an :class:`EventRepository` reference but never writes
  through it. The constructor signature is pinned: a single
  keyword-only `event_repo` parameter and nothing else. No
  exchange client, no capital flow engine, no risk engine, no
  market data buffer, no Telegram bot, no LLM client.
- Replay value objects (frozen dataclasses, all expose
  `to_payload()` for JSON-safe serialisation):
    - `PaperTradeReplay` - the Phase 9 paper trade lifecycle
      reconstructed from `events.db`. Carries the
      :class:`PaperLifecycleSummary` produced by the existing
      `reconstruct_paper_lifecycle` helper plus a
      :class:`ReplayDiffReport` that compares the observed event
      chain against the canonical Phase 9 happy-path ordering.
    - `CapitalRebaseReplay` - one capital rebase plus the
      surrounding `CAPITAL_DEPOSIT` / `CAPITAL_WITHDRAWAL` /
      `PROFIT_HARVEST` / `RISK_BUDGET_RECALCULATED` events that
      land within a 50ms window of the rebase.
    - `RiskDecisionReplay` - one `RISK_APPROVED` /
      `RISK_REJECTED` event with every Phase 7 / Phase 8.5
      payload field surfaced as a typed attribute, plus the
      Phase 8.5 `learning_ready` block (read back exactly as
      Phase 8.5 wrote it).
    - `IncidentReplay` - one incident lifecycle (OPEN +
      optional RESOLVE + protection-mode entered/exited window)
      reconstructed from `events.db` alone. The PROTECTION_MODE
      events are scoped to the incident's open-to-resolve
      window when an `incident_id` filter is supplied.
    - `StateTransitionReplay` - the Phase 7 trade-state ladder
      for one symbol (or all symbols).
    - `TelegramCommandReplay` - one
      `TELEGRAM_COMMAND_RECEIVED` event reconstructed; ready
      for Phase 10D.
    - `LearningReadyReplay` - the Phase 8.5 learning-ready
      block extracted from one event, with `has_opportunity` /
      `has_signal_snapshot` / `has_virtual_trade_plan` /
      `has_config_versions` / `has_risk_decision` projections.
    - `P0LatchedPauseInvariantReport` - audit over a sequence
      of `RECONCILIATION_RESOLVED` events. Flags any clean pass
      that reports `has_open_p0_incident=True` /
      `protection_mode_active=True` and
      `new_opens_paused=False`, or `p0_latched_pause=True` with
      any blocker active and `new_opens_paused=False`.
- Diff infrastructure (`app/replay/diff.py`):
    - `DiffKind` (`MATCH`, `MISSING`, `EXTRA`, `REORDERED`).
    - `DiffEntry` and `ReplayDiffReport` (frozen dataclasses).
    - `compare_event_chains(expected, observed, *, label)` -
      pure-function structural diff over two event-type chains.
      Uses :class:`difflib.SequenceMatcher` so the result is
      deterministic across runs.
- Read-only loaders (`app/replay/loaders.py`) - one helper per
  Phase 9 lifecycle group:
    - `load_all_events`, `stream_events` (lazy iterator)
    - `load_events_for_order`, `load_events_for_position`,
      `load_events_for_symbol`, `load_events_for_opportunity`
    - `load_capital_flow_events`, `load_risk_decision_events`,
      `load_incident_lifecycle_events`,
      `load_state_transition_events`,
      `load_telegram_command_events`,
      `load_reconciliation_events`
    - `has_learning_ready`, `extract_learning_ready` (returns a
      shallow copy so callers cannot mutate source payloads),
      `opportunity_id_for`
    - `pair_reconciliation_passes` - groups
      `RECONCILIATION_STARTED` / `RECONCILIATION_MISMATCH` /
      `RECONCILIATION_RESOLVED` triplets by their `started_at`
      payload key.
- Canonical chains pinned at module level so future PRs cannot
  silently drift them: `CANONICAL_CLOSED_PAPER_TRADE_CHAIN`,
  `CANONICAL_OPEN_PAPER_TRADE_CHAIN`. The Replay diff
  normalises the observed chain into canonical progression
  order before comparing because Phase 9 emits the entire paper
  trade lifecycle inside a single millisecond and
  `EventRepository` ties on `(timestamp, event_id)` where the
  secondary sort is a random UUID.

##### Boot drill (`python -m app.main`)

The entrypoint runs the Phase 10A self-check after the Phase 9
paper-trade and reconciliation drill. It exercises every public
replay surface:

  - replay the boot paper trade (must match the canonical chain),
  - confirm at least one capital event landed,
  - replay the bootstrap RISK_APPROVED decision,
  - confirm zero P0 incidents,
  - replay the boot STATE_TRANSITION ladder,
  - replay the boot Telegram /status command,
  - verify the P0 latched-pause invariant against the boot's
    clean reconciliation pass.

The boot banner gains five new fields:

```
replay_paper_trade_matched=True
replay_p0_incidents=0
replay_telegram_commands=1
replay_state_transitions=1
replay_p0_latched_pause_invariant=True
```

#### Phase 10A boundary

Phase 10A is **read-only**:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client /
    Telegram bot library
  - reads NO `os.environ`
  - defines NO `create_order` / `cancel_order` / `set_leverage` /
    `set_margin_mode` method
  - does NOT subclass `ExchangeClientBase`
  - does NOT instantiate any state-mutating component (the AST
    scan in `tests/unit/test_phase10a_boundary.py` enforces
    this against every file under `app/replay/`)
  - does NOT call `EventRepository.append_event` /
    `append_many` (AST scan in
    `tests/unit/test_phase10a_no_network.py`)

#### Tests

`+119` new Phase 10A tests on top of `1130` retained from
Phase 1-9 = **`1249` total**.

| File | Tests | Covers |
| --- | --- | --- |
| `test_replay_diff.py` | 13 | DiffKind vocabulary, DiffEntry payload, identical/empty/missing/extra/reordered combinations, determinism, JSON round-trip, frozen dataclass. |
| `test_replay_loaders.py` | 21 | Every event-type tuple matches its phase, every loader produces the right filter behaviour, learning-ready reads, opportunity_id extraction (top-level + nested in learning_ready), reconciliation pass pairing. |
| `test_replay_engine.py` | 22 | Acceptance criteria 1-7: replay one paper trade, replay capital rebase (event_id and timestamp), replay risk rejection under M3, replay risk decision by event_id, replay P0 incident lifecycle (with protection-mode events scoped to the incident window), replay STATE_TRANSITION ladder, replay TELEGRAM_COMMAND_RECEIVED, read Phase 8.5 learning-ready payload. Plus determinism, JSON-safety, no event-stream writes, constructor pin (event_repo only). |
| `test_replay_p0_latched_pause.py` | 10 | Empty trail / clean passes / P0 latched + pause kept / full operator resume protocol / synthesised violations (blocker_active_but_unpaused, latched_but_unpaused) / window filters / JSON round-trip. |
| `test_phase10a_boundary.py` | 14 | Phase 1 / 3 / 9 invariants, package does not subclass ExchangeClientBase, no write surface method definitions, public exports complete, canonical chains pinned. Replay engine constructor accepts only `event_repo`. |
| `test_phase10a_no_network.py` | ~50 | Per-file AST scan of every `.py` under `app/replay/`: no forbidden import, no write-surface method definition, no `api_key` / `api_secret` / `bot_token` parameter or literal, no `os.environ.get` / `getenv()`, no `send_message` / `send_document` / `send_photo` reference, no other-DB `sqlite3.connect`, no `EventRepository.append_event` / `append_many` call, no state-mutating component import. |

`tests/unit/test_main_entrypoint.py` extended (one assertion
flip) for the Phase 10A boot banner string and the five new
banner fields.

### Issue #10 acceptance criteria (Part 10A subset)

| # | Criterion | Test |
| --- | --- | --- |
| 1 | Replay can rebuild a mock paper trade | `test_replay_paper_trade_returns_summary_and_clean_diff` |
| 2 | Replay can rebuild a Capital Rebase | `test_replay_capital_rebase_after_deposit` |
| 3 | Replay can rebuild a Risk rejection | `test_replay_risk_rejection_under_m3` |
| 4 | Replay can rebuild a P0 incident | `test_replay_p0_incident_reconstructs_open_and_resolve` |
| 5 | Replay can read Phase 8.5 learning-ready payload | `test_replay_reads_learning_ready_block` |
| 6 | Replay does not trigger trading actions | `test_replay_does_not_write_to_events_db` + AST scan |
| 7 | Replay does not depend on real network | `test_phase10a_no_network.py::test_no_forbidden_imports` |
| 8 | pytest 全部通过 | 1249 passed |

### Boundary preserved

  - No new exchange SDK / HTTP / WebSocket / LLM client /
    Telegram bot library in `requirements.txt` /
    `pyproject.toml`.
  - No new `create_order` / `cancel_order` / `set_leverage` /
    `set_margin_mode` call site.
  - No change to the Phase 1 safety lock.
  - No change to the Phase 3 read-only invariant.
  - No change to the Phase 9 Execution FSM driver / Reconciler
    contract. Replay reads but never writes.
  - No real-trade persistence into `trades.db` / `positions.db`.
  - No LLM in trade decisions.
  - No Telegram outbound; the Phase 1 in-process command bus
    skeleton is unchanged.

#### Version

`app/__init__.py` -> `1.4.0a10` /
`Phase 10A - Replay Engine`. `pyproject.toml` -> `1.4.0a10`.

### Phase 9 - Execution FSM + Reconciliation

Phase 9 wires the Execution FSM driver and the Reconciliation
loop on top of every Phase 1-8.5 contract. The driver advances
per-order sessions through the 15 ``ExecutionState`` values, emits
the matching ``ORDER_*`` / ``STOP_*`` / ``POSITION_*`` events,
and consults the Risk Engine on every NEW open AND every
reduce-only / protective-exit / kill_all path. Phase 9 runs
ENTIRELY in paper / mock mode; the four ``ExchangeClientBase``
write surfaces continue to raise ``SafeModeViolation`` and are
NEVER overridden.

#### Added

##### `app/execution/` - Execution FSM driver

- `OrderRequest` (frozen Pydantic v2): `client_order_id`, `symbol`,
  `side`, `kind`, `qty`, `limit_price`, `intent`, `direction`,
  `time_in_force`, `margin_mode`, `leverage`, `reduce_only`,
  `stop_price`, `invalid_price`, `max_slippage_pct`,
  `opportunity_id`, `notes`. Validators enforce `qty > 0`,
  `leverage >= 1.0`, `0 < max_slippage_pct <= 0.10`,
  `margin_mode == ISOLATED` (cross margin is not declared at the
  enum level so a typo cannot construct one). `is_new_open` /
  `is_reduce_only_intent` properties derive from the intent
  vocabulary so callers cannot accidentally swap polarity.
- `OrderIntent` (8 values): `NEW_OPEN`, `SCALE_IN`, `LOCK_PROFIT`,
  `FORCED_EXIT`, `DISTRIBUTION_EXIT`, `PROTECTIVE_CLOSE`,
  `KILL_ALL`, `STOP_ATTACH`. Plus `NEW_OPEN_INTENTS` and
  `REDUCE_ONLY_INTENTS` partition sets that exhaust the enum.
- `OrderKind` (`LIMIT` / `MARKET` / `STOP_MARKET` / `STOP_LIMIT`).
- `OrderSide` (`BUY` / `SELL`) plus the `side_for_direction(direction,
  is_close)` helper that resolves the canonical mapping.
- `MarginMode` - the enum **only** declares `ISOLATED`. Cross
  margin is forbidden in Phase 9 (Spec §13.2 + §30.2 "禁止 cross
  margin") and the enum guarantees it cannot even be constructed.
- `TimeInForce` (`GTC` / `IOC` / `FOK`).
- `FillEvent` (frozen Pydantic v2): one fill applied to a session.
  Validates `fill_qty > 0`, `fill_price > 0`.
- `StopEvent` (frozen Pydantic v2): reduce-only stop attachment
  descriptor. The `reduce_only=True` invariant is enforced at the
  model layer (Spec §30.2 "止盈止损必须 reduce-only") so a stop
  cannot be constructed with `reduce_only=False`.
- `ExecutionSession` (mutable dataclass): per-order lifecycle state
  including `state`, `exchange_order_id`, `stop_order_id`,
  `position_id`, `filled_qty`, `avg_fill_price`, `realized_pnl`,
  transition history, learning-context payload, incident_id,
  protection-mode flag.
- `ExecutionResult` (frozen): return value of `submit_order`
  carrying `accepted`, the session, and the rejection reasons.
- `ExecutionFSMDriver`:
  - `submit_order(...)` drives `IDLE -> SIGNAL_RECEIVED ->
    RISK_CHECKED -> ORDER_SENT`. Calls
    `RiskEngine.evaluate(...)` with `is_new_open` derived from the
    intent. On rejection, the session is reverted to `IDLE` with
    `rejection_reasons` attached and removed from the driver's
    `_sessions` map. On approval, records the order in the paper
    ledger and writes one `ORDER_SENT` event.
  - `on_ack(...)` -> `ACK_RECEIVED` + `ORDER_ACK` event.
  - `on_partial_fill(...)` -> `PARTIAL_FILLED` + `ORDER_PARTIAL_FILLED`
    event. **Recomputes risk on the remaining size** (Spec §30.2
    hard rule "部分成交必须重算风险"); a re-rejection drives the
    session into `ERROR_PROTECTION`.
  - `on_full_fill(...)` -> `FULL_FILLED` + `ORDER_FILLED` event.
    Validates that the cumulative filled qty equals the request
    size.
  - `attach_stop(stop_price=...)` -> `STOP_SENT` + `STOP_SENT`
    event. The stop is constructed with `reduce_only=True`; any
    reduce-only intent (`LOCK_PROFIT` / `FORCED_EXIT` / etc.) is
    refused as a stop attachment target.
  - `on_stop_confirmed(stop=...)` -> `STOP_CONFIRMED` ->
    `POSITION_OPEN`. Records the paper position and writes one
    `POSITION_OPENED` event.
  - `on_stop_failed(reason=...)` -> `STOP_FAILED` ->
    `ERROR_PROTECTION`. Spec §30.3 "止损挂不上：立即保护平仓":
    the driver opens a P0 incident via the protection hook,
    emits `PROTECTION_MODE_ENTERED`, and runs an automatic
    reduce-only protective close on the paper position.
  - `trigger_exit(reason=...)` -> `EXIT_TRIGGERED` ->
    `POSITION_CLOSING`. Calls `RiskEngine.evaluate(...)` with
    `is_new_open=False` so M3 / DATA_DEGRADED / REGIME /
    EXCHANGE_DISCONNECTED / REBASE_IN_PROGRESS gates do NOT block
    the exit (Phase 7 protective-exit caveat; Phase 8 rebase rule).
  - `on_position_closed(realized_pnl=...)` -> `POSITION_CLOSED` ->
    `IDLE`. Removes the paper position from the ledger.
  - `enter_error_protection(...)` / `exit_protection_mode(...)` -
    public entry points for the operator override path.
  - `simulate_paper_lifecycle(...)` - high-level helper used by
    the boot drill.
  - **Construction-time refusal** of `trading_mode != paper`,
    `live_trading_enabled=True`, `exchange_live_order_enabled=True`
    (defence in depth on top of the Phase 1 boot guard).
  - **Every Phase 9 event carries `opportunity_id` and
    `learning_ready`** when the caller supplies them, so future
    Replay / Reflection / Dataset Builder can group every order /
    stop / fill / position event by opportunity (Phase 8.5
    contract).
- `PaperLedger` - in-memory paper-mode store of `PaperOrder` /
  `PaperStop` / `PaperPosition` / `PaperEquity`. Pure data; never
  opens a network surface. Provides observability counters
  (`orders_recorded`, `stops_recorded`, `positions_opened`,
  `positions_closed`).
- The Phase 1 `ExecutionFSM` skeleton + `IllegalTransition` are
  preserved verbatim for back-compat (Phase 1 tests + the boot
  drill still construct it).

##### `app/incidents/` - IncidentRepository

- `Incident` dataclass (`incident_id`, `level`, `title`,
  `description`, `source_module`, `symbol`, `position_id`,
  `opened_at`, `resolved_at`, `resolution`, `payload`).
- `IncidentRecord` dataclass (one row of the `incident_log` table).
- `INCIDENT_STATE_OPENED` / `INCIDENT_STATE_UPDATED` /
  `INCIDENT_STATE_RESOLVED` constants matching the Phase 2
  `incidents.sql` schema.
- `IncidentRepository`:
  - `open_incident(level=, title=, description=, source_module=,
    symbol=, position_id=, payload=, ...)` - writes one row into
    `incidents.incidents` + one row into
    `incidents.incident_log` + one `INCIDENT_OPENED` event.
  - `update_incident(incident_id=, note=, payload=, ...)` -
    appends one `incident_log` row with state=`updated`.
  - `resolve_incident(incident_id=, resolution=, ...)` - updates
    the `incidents` row's `resolved_at` / `resolution` columns +
    appends a `resolved` row + emits one `INCIDENT_RESOLVED`
    event.
  - `enter_protection_mode(reason=, ...)` /
    `exit_protection_mode(reason=, ...)` - emit
    `PROTECTION_MODE_ENTERED` / `PROTECTION_MODE_EXITED` events
    and toggle the `in_protection_mode` flag.
  - Read-only queries: `get_incident(incident_id)`,
    `list_open_incidents(level=, symbol=)`, `list_log_for(incident_id)`.
  - Counters for monitoring: `opened_count`, `resolved_count`,
    `protection_entered_count`, `protection_exited_count`,
    `last_protection_reason`.
- `ProtectionHook` typing.Protocol exposing `open_incident`,
  `enter_protection_mode`, `exit_protection_mode` so the FSM
  driver and the Reconciler stay decoupled from the SQLite layer
  (tests substitute mocks).

Phase 9 is the **first phase that writes to `incidents.db`**.
Earlier phases shipped only the schema; Phase 2 explicitly
forbade writes.

##### `app/reconciliation/` - Reconciliation engine

- `MismatchType` (8 values): `ORDER_MISMATCH`,
  `POSITION_MISMATCH`, `STOP_MISMATCH`, `EQUITY_DRIFT`,
  `WS_REST_CONFLICT` (the 5 mandated by Issue #9), plus three
  P0-promoted sub-types `GHOST_POSITION`,
  `MISSING_REMOTE_POSITION`, `UNATTACHED_STOP` so reflection /
  replay can group P0 incidents by canonical name without
  re-deriving them from the parent payload.
- `MismatchSeverity` (`P0` / `P1` / `P2`).
- `OrderView` / `PositionView` / `StopView` / `EquitySnapshot` /
  `LinkHealth` - frozen value objects describing the two snapshot
  sides.
- `LocalSnapshot` / `RemoteSnapshot` - the two inputs the
  reconciler consumes. Pure functions
  `local_snapshot_from_paper_ledger(...)` /
  `remote_snapshot_from_paper_ledger(...)` build them from the
  in-process paper ledger; tests can construct divergent
  snapshots directly to exercise the mismatch paths.
- `Mismatch` (frozen): one concrete mismatch carrying
  `mismatch_type`, `severity`, `symbol`, `summary`, `details`.
- `ReconciliationDecision` (frozen): result of one pass. Carries
  `started_at`, `finished_at`, `mismatches`, `incidents_opened`,
  `new_opens_paused`, `protection_mode_entered`, `notes`. Plus
  `matched`, `severities`, `has_p0` derived properties.
- `Reconciler`:
  - `reconcile(local=, remote=)` writes one
    `RECONCILIATION_STARTED` event, one
    `RECONCILIATION_MISMATCH` event per mismatch, and one
    `RECONCILIATION_RESOLVED` event with
    `mismatch_count` / `p0_count` / `p1_count` /
    `new_opens_paused` / `incident_ids` / `notes`.
  - Opens a P0 incident via `protection_hook.open_incident(...)`
    on every P0 mismatch.
  - Drives `protection_hook.enter_protection_mode(...)` on any
    P0 mismatch; the boot drill registers an
    `IncidentRepository` as the hook so this lands in
    `incidents.db` AND emits a `PROTECTION_MODE_ENTERED` event.
  - `new_opens_paused=True` on any non-empty mismatch list; the
    flag advises the FSM driver to refuse new `NEW_OPEN` /
    `SCALE_IN` `submit_order` calls until the next clean
    reconciliation.
  - A clean reconciliation clears `new_opens_paused`
    automatically (operator-equivalent of `/resume`).
  - Tunable thresholds: `equity_drift_tolerance_abs=0.01` USDT,
    `equity_drift_tolerance_rel=0.005` (0.5%),
    `qty_tolerance=1e-9`, `stop_price_tolerance_pct=0.001`
    (0.1%). The reconciler treats abs OR rel passing as "within
    tolerance" - both must exceed before the drift fires.

##### Risk Engine integration (Phase 9-only consumer of an existing API)

Phase 9 makes **no** changes to `RiskEngine` / `RiskRequest`. The
existing Phase 7 protective-exit caveat (`is_new_open=False` is
the right way to bypass M3 / DATA_DEGRADED / REGIME /
EXCHANGE_DISCONNECTED gates) and the Phase 8 rebase rule
(`is_rebase_in_progress` blocks new opens but never blocks exits)
already do the right thing. Phase 9 simply derives `is_new_open`
from the `OrderIntent` vocabulary so callers cannot pass the
wrong flag.

Verified by the Phase 9 boundary tests: M3 + protective close
PASSES, DATA_DEGRADED + protective close PASSES,
REBASE_IN_PROGRESS + protective close PASSES; the corresponding
`is_new_open=True` paths are still rejected.

##### Boot drill (`python -m app.main`)

The boot drill now drives ONE paper-mode order through the full
Execution FSM (`NEW_OPEN` -> `POSITION_OPEN` -> `LOCK_PROFIT` exit
-> `POSITION_CLOSED` -> `IDLE`) and runs ONE reconciliation pass
against snapshots built from the same paper ledger. In paper mode
the local view equals the remote view, so the boot reconciliation
is always clean (zero mismatches, zero incidents). The banner
gained 14 new fields (`orders_submitted`, `order_sent_events`,
`order_filled_events`, `stops_confirmed`, `positions_opened`,
`positions_closed`, `reconciliations_run`,
`reconciliation_started_events`, `reconciliation_resolved_events`,
`reconciliation_mismatches`, `new_opens_paused`,
`incidents_opened`, `protection_mode_entered`).

Two new health probes are registered:
  - `execution_driver` - DEGRADED if the driver has entered
    `ERROR_PROTECTION` at least once.
  - `reconciliation` - DEGRADED if `new_opens_paused=True` at the
    end of the boot pass.

##### Documentation + version bump

- `app/__init__.py` -> `1.4.0a9` /
  `Phase 9 - Execution FSM Reconciliation`.
- `pyproject.toml` -> `1.4.0a9`.
- `README.md` -> Phase 9 deliverable + boundary section + status
  table updated (Phase 8.5 marked merged, Phase 9 is "this branch").
- `docs/CHANGELOG.md` -> Phase 9 entry prepended; the Phase 8.5
  entries are preserved verbatim below.

#### Tests

```
$ python3.12 -m pytest tests/unit
1091 passed in 9.28s
```

**+149 new Phase 9 tests on top of 942 retained from Phase 1-8.5 = 1091 total.**

| File | Tests | Covers |
| --- | --- | --- |
| `test_execution_models.py` | 16 | OrderRequest validators (qty / leverage / margin_mode / slippage), `is_new_open` / `is_reduce_only_intent` derivation, intent partition complete, FillEvent / StopEvent validators (incl. `reduce_only` enforcement), `side_for_direction`, OrderKind / MarginMode vocabularies. |
| `test_paper_ledger.py` | 10 | record_order, partial-fill clamping, close_order, stops, positions (incl. cascading stop removal on close), equity snapshot. |
| `test_execution_fsm_driver.py` | 28 | construction guards (3), submit_order happy path + opportunity_id propagation + learning_ready propagation + duplicate refusal, market-order on NEW_OPEN refused vs allowed for protective close, reduce_only auto-resolution, risk rejection paths (M3 new open, M3 protective close PASSES, DATA_DEGRADED protective close PASSES, REBASE_IN_PROGRESS protective close PASSES), full lifecycle event sequence, partial fill recompute (Spec §30.2), VWAP computation, full fill consume remaining, stop attach reduce_only, on_stop_failed -> ERROR_PROTECTION + P0 incident + protective close, on_stop_confirmed -> POSITION_OPENED + paper position, trigger_exit calls Risk Engine with is_new_open=False, M3 protective exit does not open incident, enter / exit_protection_mode lifecycle. |
| `test_incidents_repository.py` | 8 | open_incident writes row + log + INCIDENT_OPENED, update_incident appends log row only, resolve_incident updates row + emits INCIDENT_RESOLVED, get / list helpers, enter / exit protection mode events, ProtectionHook surface. |
| `test_reconciler.py` | 16 | clean recon, paper ledger round trip clean, ghost position P0 + new_opens_paused + protection_hook P0 incident, missing remote position P0, position qty disagreement P0, unattached_stop P0, order local-only P1, order qty disagreement, equity within tolerance / above tolerance, WS-REST conflict P1, both-connected no fire, new_opens_paused state machine clears on clean recon, RECONCILIATION_RESOLVED payload counts, RECONCILIATION_MISMATCH event per mismatch. |
| `test_phase9_boundary.py` | 16 | Phase 1 lock unchanged, Phase 3 write surfaces still refuse on Mock + Binance skeleton, Phase 9 packages don't subclass ExchangeClientBase, no write surface method definitions, OrderIntent / OrderKind / MarginMode / MismatchType / MismatchSeverity vocabularies pinned, driver construction guard, all Phase 9 EventType values reachable, public exports, OrderRequest model-level validators. |
| `test_phase9_no_network.py` | ~50 | per-file AST scan of every `.py` under `app/execution/`, `app/incidents/`, `app/reconciliation/`: no forbidden import (ccxt / binance / aiohttp / websockets / requests / httpx / openai / anthropic / deepseek / telegram), no write-surface method, no `api_key` / `api_secret` / `bot_token` parameter or literal, no `os.environ.get` / `getenv()`, no `send_message` / `send_document` / `send_photo` reference, no other-DB `sqlite3.connect`. |

`tests/unit/test_main_entrypoint.py` was extended (not replaced)
to assert the new Phase 9 banner fields and Phase 9 event counts
(1 each of `ORDER_SENT` / `ORDER_ACK` / `ORDER_FILLED` /
`STOP_SENT` / `STOP_CONFIRMED` / `POSITION_OPENED` /
`EXIT_TRIGGERED` / `POSITION_CLOSED`, 1 `RECONCILIATION_STARTED`
+ `RECONCILIATION_RESOLVED`, 0 `RECONCILIATION_MISMATCH`, 0
`INCIDENT_OPENED`, 0 `PROTECTION_MODE_ENTERED`).

#### Live trading risk

**None.**

  - `requirements.txt` and `pyproject.toml` contain no exchange
    SDK, no HTTP / WebSocket client, no LLM client, no Telegram
    bot library.
  - No source under `app/execution/`, `app/incidents/`,
    `app/reconciliation/` imports `ccxt`, `binance`, `aiohttp`,
    `websockets`, `requests`, `httpx`, `openai`, `anthropic`,
    `deepseek`, or any Telegram library.
  - No source under those packages defines `create_order` /
    `cancel_order` / `set_leverage` / `set_margin_mode`.
  - `MarginMode` enum does not even declare `CROSS`.
  - `ExchangeClientBase.{create_order, cancel_order, set_leverage,
    set_margin_mode}` continue to raise `SafeModeViolation` from
    the base class.
  - The Phase 1 safety lock + the Phase 3 read-only invariant +
    every Phase 4 / 5 / 6 / 7 / 8 / 8.5 contract are unchanged.
    Boot banner still shows
    `mode=paper live_trading=False right_tail=False llm=False
    exchange_live_orders=False`.
  - The `ExecutionFSMDriver` refuses to construct unless the
    Phase 1 safety lock matches paper-mode (defence in depth).

## [Unreleased - prior]

### Phase 8.5 - Learning-Ready Data Contract + Test Data Export Contract

Phase 8.5 lays the **passive data contract** every future phase
will read: Replay (Issue #10), MFE/MAE labelling, Tail labelling,
Dataset Builder, AI Learning. It also ships the cloud-test-friendly
**Test Data Export Service** (zip + manifest + summary + redaction)
plus a CLI. The full AI Learning, Feature Store, model training,
strategy ordering, live trading, real network, LLM and Telegram
outbound are **NOT** implemented in this phase.

#### Added

##### `app/learning/` - Learning-Ready Data Contract

- `OpportunityIdentity` (frozen Pydantic v2): `opportunity_id`,
  `scan_batch_id`, `symbol`, `first_seen_ts`, `source_phase`. Plus
  `make_opportunity_id` / `make_scan_batch_id` factories so a
  scanner / confirmation / risk engine call can generate a stable
  identifier deterministically.
- `signal_snapshot_to_payload` / `payload_to_signal_snapshot`:
  Spec §11.2 SignalSnapshot serialiser/deserialiser. The Phase 1
  `app.core.models.SignalSnapshot` is the single source of truth;
  Phase 8.5 only adds a deterministic JSON-safe serialisation
  contract.
- `VirtualTradePlan` (frozen Pydantic v2): `virtual_entry`,
  `virtual_stop`, `virtual_tp1`, `virtual_tp2`, `invalid_price`,
  `suggested_leverage`, `risk_budget_pct`, `direction`, `setup_type`.
  Validates `suggested_leverage >= 1.0` and `0 <= risk_budget_pct <= 1.0`.
  This is a **paper-only descriptive plan**; constructing one
  triggers no order, ever.
- `ConfigVersions` (frozen Pydantic v2) with the six Issue-mandated
  identifiers: `strategy_version`, `risk_config_version`,
  `scoring_version`, `capital_state_version`, `state_machine_version`,
  `llm_prompt_version`. Defaults are pegged to `v1.4.0a8.5`;
  `llm_prompt_version` defaults to `n/a` because Phase 8.5 forbids
  any LLM trade involvement (Spec rule 7).
- `RiskRejectedLearningPayload`: typed enrichment carrying
  `opportunity_id`, `reject_reasons`, `account_life_tier`, `regime`,
  `universe_eligible`, `liquidity_state`, `trade_confirmation_level`,
  `manipulation_level`, `capital_state_version`, `risk_config_version`,
  plus Phase 7 breaker / `is_new_open` / `attack_intent` context.
- `LearningReadyContext` aggregator + `attach_learning_ready` merge
  helper. Mutation-free: existing event-payload keys are preserved
  bit-for-bit, the enrichment lands under a new `learning_ready`
  sub-key. The Phase 1 `EventRepository.append_event` API is
  unchanged; Phase 8.5 simply makes it possible for emitters to
  carry the contract.
- `LEARNING_READY_KEY = "learning_ready"` and
  `LEARNING_READY_EVENT_TYPES` (the 11 event types Issue #8.5
  requires: `PRE_ANOMALY_DETECTED`, `ANOMALY_DETECTED`,
  `TRADE_CONFIRMED`, `MANIPULATION_DETECTED`, `UNIVERSE_FILTERED`,
  `LIQUIDITY_CHECKED`, `RISK_APPROVED`, `RISK_REJECTED`,
  `STATE_TRANSITION`, `CAPITAL_REBASE`,
  `RISK_BUDGET_RECALCULATED`).

##### Risk Engine integration

- `RiskRequest` gained five **optional** Phase 8.5 fields:
  `opportunity`, `opportunity_id`, `virtual_trade_plan`,
  `config_versions`, `learning_context`. All default to `None`;
  legacy callers retain byte-for-byte compatible audit payloads.
- `RiskEngine._record(...)` now synthesises a
  `RiskRejectedLearningPayload` from the request + decision +
  breaker state and merges a `learning_ready` block into the
  `RISK_APPROVED` / `RISK_REJECTED` payload. A caller-supplied
  `learning_context` always wins over the synthesised one. The
  legacy reasons / account_tier / regime / no_trade_gate audit
  fields stay untouched so Phase 1 / Phase 6 / Phase 7 tests pass
  unchanged.

##### `app/exports/` - Test Data Export Service

- `TestDataExportService.export(...)` produces a redacted `.zip`
  bundle under `data/reports/exports/ama_rt_test_data_<ts>_<id>.zip`.
  Default zip contents (with `type=all`):
    `manifest.json`, `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`, `virtual_trade_plans.jsonl`.
- Time ranges supported: `today`, `24h`, `7d`, `range` (with
  explicit `start_ms` / `end_ms`).
- Type filters supported: `all`, `events`, `opportunities`,
  `rejections`, `capital`, `state`, `learning`.
- `manifest.json` carries every Issue-mandated field
  (`export_id`, `generated_at`, `time_range_start`, `time_range_end`,
  `trading_mode`, `app_version`, `event_count`, `opportunity_count`,
  `risk_rejected_count`, `state_transition_count`,
  `capital_event_count`, `redaction_applied=true`) plus a
  per-export `safety_summary` snapshot of the Phase 1 lock so a
  reviewer can spot a leaked flag at a glance.
- `summary_report.md` includes time range, totals, top reject
  reasons, top symbols by event count, paper PnL (from
  `CAPITAL_REBASE.net_trading_pnl`), and incident / degraded /
  protection-mode flags.
- `redact(...)` walks any JSON-safe value and replaces sensitive
  fields with `[REDACTED]`. The redactor covers (a) sensitive key
  substrings (`api_key`, `api_secret`, `secret`, `token`,
  `password`, `auth`, `credential`, `private_key`, `bot_token`,
  `webhook`, `withdrawal_address`, `address`, `passphrase`,
  `session`, `cookie`, `ssh`, `smtp`, ...), (b) absolute filesystem
  paths (`/home`, `/root`, `/Users`, `C:\Users`, `/etc`, `/var/lib`,
  `/usr/local`, `/.env`), and (c) value patterns (Telegram bot
  tokens `\d{8,12}:[A-Za-z0-9_-]{30,}`, Binance-style 64-char
  keys, AWS `AKIA...` keys, OpenAI/Anthropic/DeepSeek `sk-...`
  tokens, `AMA_*_KEY/SECRET/TOKEN/PASSWORD` env-var literals).
- `assert_no_forbidden_substrings(...)` is a defence-in-depth gate
  on the export path; the service refuses to write the zip if any
  forbidden literal slips through.
- `TestDataExportService.max_zip_bytes` defaults to 50 MiB. Issue
  #10 will add Telegram-side fragmentation; Phase 8.5 just refuses
  to grow beyond the cap and asks the caller to narrow the window.
- CLI: `app/exports/cli.py` + `scripts/export_test_data.py` shim.
  Examples:
    ```
    python -m scripts.export_test_data --range 24h
    python -m scripts.export_test_data --range 7d
    python -m scripts.export_test_data --type rejections
    python -m scripts.export_test_data --start 2026-05-01 --end 2026-05-07
    ```

##### Documentation

- `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`: the future Telegram
  Command Center MUST add `/export_test_data {24h,7d,today}`,
  `/export_rejections 24h`, `/export_report today`,
  `/export_learning_dataset 7d`. The contract spells out: short
  text summary first, then `sendDocument` (NOT raw chat dump),
  paper-mode banner pinned, operator allow-list, refusal on size
  cap. Issue #10 will implement the bot client; Phase 8.5 ships
  ONLY the contract.
- `app/__init__.py` bumped to `1.4.0a8.5` /
  `Phase 8.5 - Learning-Ready Data Contract + Test Data Export Contract`.
- `pyproject.toml` version bumped to `1.4.0a8.5`.

#### Boundary (Phase 8.5 prohibitions, all enforced by tests)

1. **No full AI Learning.** No model training. No Feature Store.
   No complex Data Collection Module.
2. **No Telegram outbound.** The `app/telegram` package remains
   a Phase 1 in-process command-bus skeleton.
3. **No real network.** No exchange SDK, no HTTP / WebSocket
   client, no LLM client imported anywhere under `app/learning/`
   or `app/exports/`.
4. **No API key in process memory.** No `api_key` / `api_secret`
   parameter on any Phase 8.5 surface; no `os.environ` /
   `os.getenv` / bare `getenv` call under `app/learning/` or
   `app/exports/` (AST scan).
5. **No write surface.** No new `create_order`, `cancel_order`,
   `set_leverage`, `set_margin_mode` method. The four
   `SafeModeViolation` refusals on `ExchangeClientBase` are
   unchanged.
6. **No LLM in trade decisions.** `llm_prompt_version` is `"n/a"`
   by default; the LLM prompt label only *records* a version for
   Reflection (Issue #10). Spec rule 7 still bans LLM
   participation in trading actions.
7. **No Issue #9 work.** Execution FSM driver / Reconciliation
   are deferred.
8. **No Issue #10 work.** LLM, Telegram outbound, Replay diff
   reports, Reflection are deferred.

#### Tests

```
$ python3.12 -m pytest tests/unit
933 passed in 7.40s
```

**+150 new Phase 8.5 tests** on top of the 783 retained from
Phase 1-8 = **933 total**:

| File | Tests | What it covers |
| --- | --- | --- |
| `test_opportunity_identity.py` | 8 | factory ids, prefix contract, frozen contract, payload round-trip, extra-field rejection, url-safe characters |
| `test_signal_snapshot_payload.py` | 5 | Spec §11.2 field set, enum-as-string contract, JSON-safe, round-trip preserves fields, defaults round-trip |
| `test_virtual_trade_plan.py` | 8 | required fields present, optional `None`s round-trip, JSON-safe, leverage/risk-budget validators, frozen contract |
| `test_config_versions.py` | 7 | six Issue-mandated fields, `llm_prompt_version='n/a'` default, JSON-safe, round-trip, frozen, legacy-payload back-fill |
| `test_learning_ready_context.py` | 9 | the 11 event types pin, `LEARNING_READY_KEY` constant, mutation-free merge, full-context payload, empty-context emits empty dict |
| `test_risk_rejected_payload.py` | 6 | enum-as-string serialisation, RISK_REJECTED carries learning_ready when supplied, legacy request leaves payload byte-compatible, RISK_APPROVED with explicit `opportunity_id`, explicit-context override beats synthesised |
| `test_event_repository_learning_ready.py` | 3 | round-trip of `learning_ready` block via `EventRepository.append_event` + `list_events`, all 11 event types preserved on disk, JSON-serialisable on disk |
| `test_export_redaction.py` | 12 | top-level keys, nested keys, mutation-free input, value-pattern matching (Telegram, OpenAI), filesystem path stripping, short strings pass through, forbidden-substring gate, sensitive-key contract |
| `test_export_service.py` | 22 | time range helpers (today/24h/7d/range/parse_iso_date), zip materialised, manifest + summary + 7 jsonl shards, redaction end-to-end, type filters (rejections/capital/state/learning), unknown filter rejected, empty window still produces zip, size cap refused, safety_summary on manifest, output filename layout |
| `test_export_cli.py` | 8 | `--range 24h` / `7d` / `today`, `--type rejections`, `--range range --start --end`, missing start/end error, oversized cap error, missing events.db error |
| `test_phase8_5_boundary.py` | 9 | Phase 1 lock unchanged, write surfaces still refuse `SafeModeViolation`, BinanceClient still refuses credentials, learning/exports packages do NOT subclass `ExchangeClientBase`, no write-surface methods on learning/exports, redaction substring contract, default zip cap finite, Telegram contract doc present |
| `test_phase8_5_no_network.py` | ~52 | per-file AST scan of every `.py` under `app/learning/` + `app/exports/`: no forbidden import (ccxt, binance, aiohttp, websockets, requests, httpx, openai, anthropic, deepseek, telegram libraries), no write-surface method definition, no `api_key` / `api_secret` parameter, no concrete `BINANCE_API_KEY=` / `TELEGRAM_BOT_TOKEN=` literal in source, no `os.environ.get` / `os.getenv` / bare `getenv()` call, no `send_message` / `send_document` / `send_photo` reference |

`tests/unit/test_main_entrypoint.py` was extended (one assertion
flip) to expect the Phase 8.5 banner string.

#### Live trading risk

**None.**

- `requirements.txt` and `pyproject.toml` contain no exchange SDK,
  no HTTP client, no LLM client, no Telegram bot library.
- No source file under `app/learning/` or `app/exports/` imports
  `ccxt`, `binance`, `aiohttp`, `websockets`, `requests`, `httpx`,
  `openai`, `anthropic`, `deepseek`, or any Telegram library
  (asserted by `tests/unit/test_phase8_5_no_network.py`).
- No source file under `app/learning/` or `app/exports/` defines
  `create_order` / `cancel_order` / `set_leverage` /
  `set_margin_mode` (asserted by the same test module).
- No source file under `app/learning/` or `app/exports/` reads
  `os.environ` / `os.getenv` / a bare `getenv()` (AST scan).
- The Phase 1 safety lock, Phase 3 read-only invariant, Phase 4
  Market Data Buffer boundary, Phase 5 Regime / Universe /
  Liquidity contract, Phase 6 Scanner / Confirmation /
  Manipulation contract, Phase 7 State Machine + Risk Engine
  contract, and Phase 8 Capital Flow Engine + External Capital
  Flow vocabulary are all unchanged. The boot banner still shows
  `mode=paper live_trading=False right_tail=False llm=False
  exchange_live_orders=False`.
- The export service is **read-only against `events.db`**. It
  never opens a socket, never calls a write surface, never mutates
  any other database, never writes outside the configured output
  directory.
- The CLI refuses to operate when `trading_mode != paper`.

#### Real exchange order risk

**None.** Phase 8.5 adds no new `create_order` / `cancel_order` /
`set_leverage` / `set_margin_mode` call site. The four
`SafeModeViolation` refusals on `ExchangeClientBase` continue to
apply.

---

## [Unreleased - Phase 8 review fix - already in main via PR #19]

### Phase 8 - Issue #8 review fix: External Capital Flow semantics

Issue #8 review pointed out that the Phase-8 PR conflated several
distinct capital concepts. This patch implements the full External
Capital Flow vocabulary so the engine cannot mis-classify principal
withdrawals as profit and cannot mis-classify external deposits as
trading P&L.

#### Capital semantics (hard rules)

1. **External deposit is NOT trading profit.** A `CAPITAL_DEPOSIT`
   bumps `external_deposits_total` and `exchange_equity`; it never
   touches `withdrawn_profit` and never inflates `net_trading_pnl`.
2. **Principal withdrawal is NOT a loss.** When a withdrawal exceeds
   `available_profit` the excess lands in `principal_withdrawn_total`,
   never in `withdrawn_profit`.
3. **Profit withdrawal is NOT a drawdown.** `lifetime_account_value`
   is invariant under withdrawals.
4. **Risk Budget is based ONLY on `trading_capital`.** Already-
   withdrawn profit and historical peaks never re-enter the budget.
5. **Performance / `net_trading_pnl` excludes `external_deposits_total`.**
   Reporting must use `net_trading_pnl`, not `lifetime_equity`, when
   external deposits are present.
6. **`initial_capital` is immutable after construction.** The engine
   raises on any reassignment attempt.

#### Formulas

```
net_contributed_capital = initial_capital
                            + external_deposits_total
                            - principal_withdrawn_total

lifetime_account_value  = exchange_equity
                            + withdrawn_profit
                            + principal_withdrawn_total

net_trading_pnl         = lifetime_account_value
                            - initial_capital
                            - external_deposits_total

trading_capital         = exchange_equity
risk_budget             = trading_capital
```

#### Added

- `CapitalState.external_deposits_total` and
  `CapitalState.principal_withdrawn_total` fields, plus the
  computed properties `lifetime_account_value`,
  `net_contributed_capital`, and `net_trading_pnl`.
- `CapitalSnapshot` mirrors the new fields. The
  `capital.db.capital_snapshots` table gains
  `external_deposits_total` and `principal_withdrawn_total`
  columns; `app/database/migrations.py` ships an idempotent
  ALTER-TABLE for existing Phase-7 capital.db files.
- `RebaseResult` now carries the full External Capital Flow audit
  trail: `profit_part`, `principal_part`, `withdrawal_type`,
  `available_profit_before`, plus before/after values for
  `principal_withdrawn_total`, `external_deposits_total`,
  `lifetime_account_value`, and `net_trading_pnl`.
- `CapitalFlowEngine.deposit()` is now a full external-deposit
  flow: it bumps `external_deposits_total`, sets
  `is_rebase_in_progress=True` for the duration, emits the
  full event trio (CAPITAL_DEPOSIT + CAPITAL_REBASE +
  RISK_BUDGET_RECALCULATED), persists a snapshot, and returns
  a `RebaseResult`. `withdrawn_profit` is never touched by a
  deposit.
- `CapitalFlowEngine.replay_capital_events` /
  `CapitalFlowEngine.reconstruct_current_snapshot` rebuild a
  `CapitalState` from the persisted CAPITAL_* event stream. The
  reconstruction sorts by `(timestamp ASC, rowid ASC)` so events
  emitted within the same millisecond replay in the order they
  were inserted.
- New convenience properties on `CapitalFlowEngine`:
  `lifetime_account_value`, `net_contributed_capital`,
  `net_trading_pnl`, `external_deposits_total`,
  `principal_withdrawn_total`, `withdrawn_profit`. The setter for
  `initial_capital` now raises `AttributeError` so the immutability
  contract is enforced at the language level.
- `CAPITAL_WITHDRAWAL` payload now carries `withdrawal_type`
  (`"profit"` / `"principal"` / `"mixed"`), `profit_part`,
  `principal_part`, `available_profit_before`,
  `lifetime_account_value_before`, `initial_capital`, and
  `external_deposits_total`. `PROFIT_HARVEST` is only emitted
  when `profit_part > 0` so harvest analytics never see pure-
  principal withdrawals. `CAPITAL_REBASE` payloads carry the full
  External Capital Flow snapshot so a Replay engine can rebuild
  state deterministically.
- 25 new tests in `tests/unit/test_capital_flow_engine.py`
  covering: profit-only withdrawal (Test 1), mixed withdrawal
  (Test 2), pure-principal withdrawal, mid-stream deposit (Test 3),
  deposit + trading P&L (Test 4), deposit + profit withdrawal
  (Test 5), withdrawal exceeding available profit (Test 6),
  rebase gating (Test 7 - REBASE_IN_PROGRESS plus
  stop_unconfirmed / unknown_position post-rebase), event-
  sourced reconstruction (Test 8), `initial_capital` immutability,
  deposit-emits-full-event-trio, and CAPITAL_WITHDRAWAL payload
  semantics.

#### Changed

- `app/capital/rebase.py::execute_rebase` now classifies a
  withdrawal *before* mutating state: it computes
  `available_profit = max(0, net_trading_pnl_before)` and splits
  the withdrawal into `profit_part` and `principal_part`. Only
  `profit_part` accumulates onto `withdrawn_profit`; the rest
  lands on `principal_withdrawn_total`.
- `app/capital/profit_harvest.py::suggest_harvest` accepts
  optional `external_deposits_total` and
  `principal_withdrawn_total` parameters. The 2x / 5x / 10x
  multiplier ladder now triggers on the
  `lifetime_account_value / net_contributed_capital` ratio so
  external deposits never mis-trigger a harvest suggestion.
  When both new parameters default to `0` the old formula is
  preserved exactly.
- `Risk Engine` already gates new opens via
  `is_rebase_in_progress`; this remains the only place that
  authorises resume. Clearing the flag does NOT auto-approve
  new opens - the No-Trade Gate (stop_unconfirmed,
  unknown_position, regime, liquidity, account tier, circuit
  breakers, manipulation) still has final authority.

#### Safety

- No real withdrawal API. The engine only RECORDS withdrawals.
- No live trading. Phase 1 safety lock unchanged.
- No exchange write API. Phase 1 safety lock unchanged.
- No LLM. Phase 1 safety lock unchanged.
- No Issue #9 / #10 work shipped here.
- `initial_capital` immutability is enforced at the language
  level (setter raises `AttributeError`).

### Phase 7 - Issue #7 review fix: conservative throughput discount

Issue #7 review pointed out that the original PR deferred the
Phase 5 ``can_exit_position`` upper-bound discount to Issue #8 / #9.
That is wrong - Spec §27.2 + §19.2 require the Risk Engine to apply
the conservative discount itself. This commit moves the discount on
to the Phase 7 No-Trade Gate, where Issue #7 actually wants it.

#### Added

- ``RiskEngine.throughput_safety_factor`` (default ``0.5``) and a
  matching ``throughput_safety_factor: float | None`` field on
  :class:`RiskRequest`. Allowed range is ``(0.0, 1.0]``; the engine
  raises ``ValueError`` outside that range. Per-request overrides
  are honoured.
- ``RiskRequest.max_exit_seconds`` (optional) - ceiling for the
  discounted re-check. When ``None`` the engine derives it from the
  supplied :class:`LiquidityDecision` / :class:`ExitPlan`.
- ``NoTradeGateInput.throughput_safety_factor`` and
  ``NoTradeGateInput.max_exit_seconds`` so the gate can be driven
  directly by tests / replay.
- :attr:`RiskRejectReason.LIQUIDITY_THROUGHPUT_INSUFFICIENT` typed
  reject reason: fires when
  ``estimated_exit_seconds / throughput_safety_factor`` exceeds the
  resolved ``max_exit_seconds`` ceiling on a new opening.
- ``RISK_APPROVED`` / ``RISK_REJECTED`` audit payload now carries
  ``throughput_safety_factor`` and ``max_exit_seconds`` so
  Reflection (Issue #10) can reproduce the decision.
- README "Phase 7 conservative throughput discount" subsection that
  explains the Issue #7 hard rule, the resolution policy
  (``RiskRequest.throughput_safety_factor`` -> engine default), and
  the reuse rule for any future Phase 5
  ``LiquidityConfig.throughput_safety_factor``.

#### Changed

- ``app/risk/no_trade_gate.py`` - the Phase 5 ``can_exit_position``
  output is now treated as an upper bound. The gate runs the raw
  feasibility check first (``NO_EXIT_CHANNEL`` /
  ``LIQUIDITY_REJECTED`` / ``DATA_DEGRADED`` still fire as before)
  and then runs the discounted re-check on every new opening with a
  feasible plan. Step ordering is deterministic so reflective tools
  see the most severe / earliest reason at index 0.
- ``app/risk/engine.py`` - ``RiskEngine.__init__`` accepts the new
  keyword. Audit payload extended.
- README + CHANGELOG explicit: "Risk Engine treats liquidity
  throughput as an upper bound and applies a conservative safety
  factor before allowing ATTACK / RIGHT_TAIL_AMPLIFY."

#### Reuse policy

If a future Phase 5 PR ever adds ``throughput_safety_factor`` to
``LiquidityConfig``, the Phase 7 engine MUST consume that field
directly instead of defining its own. As of this commit no such
field exists on ``LiquidityConfig`` and the
``app/liquidity/`` package is unchanged.

#### Tests

**+9 new tests on top of the 714 from the Phase 7 PR = 723 total,
all passing.**

| Test | Pins |
| --- | --- |
| ``test_throughput_safety_factor_default_is_one_half`` | Default factor is 0.5. |
| ``test_throughput_safety_factor_invalid_rejected`` | (0.0, 1.0] enforced; constructor raises ``ValueError`` outside that range. |
| ``test_raw_feasible_plan_rejected_when_discounted_exceeds_ceiling`` | Issue #7 review fix: 40s raw + factor 0.5 -> 80s discounted -> REJECT with ``liquidity_throughput_insufficient``. |
| ``test_raw_feasible_plan_passes_when_discounted_under_ceiling`` | 10s raw + factor 0.5 -> 20s discounted -> APPROVE. |
| ``test_data_degraded_blocks_even_when_raw_plan_is_feasible`` | Issue #7 review fix: feasible plan + degraded data -> still rejected with ``data_degraded``. |
| ``test_no_trade_gate_throughput_discount_directly`` | Direct ``evaluate_no_trade_gate(...)`` regression so the discount is independently pinned at the gate level. |
| ``test_per_request_safety_factor_override_honoured`` | Per-request ``throughput_safety_factor=1.0`` (no discount) approves the same input that 0.5 would refuse. |
| ``test_engine_level_safety_factor_override_honoured`` | ``RiskEngine(throughput_safety_factor=0.9)`` approves a 40s/60s plan. |
| ``test_audit_payload_includes_throughput_safety_factor`` | The factor is on the persisted ``RISK_APPROVED`` audit row. |

#### Live trading risk

**None.** This commit only adds defensive plumbing: a new
multiplicative discount, a new typed reject reason, two new
optional ``RiskRequest`` fields, and audit-payload entries. No new
mode flag, no loosened safety lock, no new dependency, no new
write surface, no new network surface, no LLM. The Phase 1 safety
lock, the Phase 3 read-only invariant, the Phase 4 / 5 / 6
boundaries remain unchanged.

### Phase 7 - State Machine Risk Engine

#### Added

- **`app/state_machine/` package** (Spec §26, Issue #7).
  - `TradeStateMachine` per-symbol Trade State Machine implementing
    the Spec §26.1 ladder (`NO_TRADE -> OBSERVE -> SCOUT -> CONFIRM
    -> ATTACK -> RIGHT_TAIL_AMPLIFY -> LOCK_PROFIT ->
    DISTRIBUTION_ALERT -> FORCED_EXIT`).
  - Whitelisted transition table forbidding level skipping
    (Issue #7 hard rule 1). OBSERVE cannot directly become
    RIGHT_TAIL_AMPLIFY; SCOUT cannot directly become ATTACK; every
    illegal attempt raises :class:`IllegalStateTransition`.
  - `promote(TradeStateContext)` / `downgrade(reason)` /
    `record_breakout_failure()` / `record_distribution_bar()` /
    `lock_profit()` / `distribution_alert()` / `forced_exit()` /
    `tick(clock_ms)` / `reset()` operations. Each successful
    transition writes one ``STATE_TRANSITION`` event with the
    `from / to / trigger / reasons` payload.
  - Phase 7 hard rules enforced: CONFIRM-failures downgrade to
    SCOUT after the configured threshold; DISTRIBUTION_ALERT
    cannot promote; FORCED_EXIT is sticky (only `reset()` clears
    it); a losing position cannot enter RIGHT_TAIL_AMPLIFY;
    right-tail amplification must come from floating profit.
  - Spec §26.4 timeouts implemented in `tick(clock_ms)`: OBSERVE
    -> NO_TRADE after 30 min, SCOUT -> NO_TRADE after 12 min,
    ATTACK -> LOCK_PROFIT on `cvd_weakening=True`,
    RIGHT_TAIL_AMPLIFY -> LOCK_PROFIT on
    `right_tail_core_failed=True`, DISTRIBUTION_ALERT -> FORCED_EXIT
    after 3 confirming bars.
  - :class:`TimeoutConfig` exposes the timeout policy as a frozen
    dataclass so YAML overrides remain a future, additive change.

- **`app/risk/no_trade_gate.py`** (Spec §27.2, Issue #7).
  - `evaluate_no_trade_gate(NoTradeGateInput) -> NoTradeGateDecision`
    composes every Spec §27.2 condition into a typed
    :class:`RiskRejectReason` list. Walks in stable order so the
    "first" reason in the list is the most severe / earliest.
  - Reads Phase 5 `RegimeSnapshot.risk_permission`,
    `UniverseDecision.eligible`, `LiquidityDecision.passed`, and
    `ExitPlan.feasible`.
  - Reads Phase 6 `ManipulationLevel` and
    `TradeConfirmationLevel`.
  - Reads exchange-link state, market-data degraded view,
    stop-confirmation, position-known flag, and the two circuit
    breaker states.
  - Honours the `is_new_open` flag so Phase 9 can call the gate
    on a protective-exit / reduce-only path without M3 / regime /
    data-degraded firing.

- **`app/risk/account_tier.py`** (Spec §27.4, Issue #7).
  - `classify_account_tier(current_equity, initial_capital) ->
    AccountLifeTier` pure function (A..F by equity ratio).
  - `ACCOUNT_TIER_POLICY` table + `policy_for(tier)` helper. Each
    `AccountTierPolicy` exposes `allow_new_open`, `allow_attack`,
    `allow_right_tail_amplify`, `allow_live_trading`, `halt_only`,
    `paper_only`, `notes`. Tiers D / E / F progressively restrict
    the ladder; tier F is halt-only.

- **`app/risk/circuit_breaker.py`** (Spec §27.2, Issue #7).
  - `ConsecutiveLossCircuitBreaker` opens after N consecutive
    losses (default 5). `record_loss()` / `record_win()` /
    `reset()`. A winning trade does NOT auto-close an opened
    breaker - Phase 7 requires an explicit `reset()`.
  - `DailyLossCircuitBreaker` opens once cumulative gross daily
    loss exceeds `max_daily_loss_pct * initial_capital` (default
    5%). Rolls over on UTC date change. Same explicit-`reset()`
    contract.

- **`app/risk/engine.py` Phase 7 extension** (Spec §27, Issue #7).
  - `RiskRequest` gained ten optional Phase 7 fields:
    `is_new_open` (default `True` for backwards compat),
    `regime_snapshot`, `universe_decision`, `liquidity_decision`,
    `exit_plan`, `is_data_degraded`, `exchange_connection_state`,
    `current_equity`, `initial_capital`, `account_tier_override`.
  - `RiskEngine.evaluate(...)` now composes the Phase 1 hard
    flags + Phase 6 hard rules + the Phase 7 No-Trade Gate +
    Account Life Tier policy + Circuit Breaker state into one
    decision.
  - `RiskEngine.record_loss(loss_amount=)` /
    `record_win(profit_amount=)` /
    `configure_initial_capital(initial_capital=)` are the public
    hooks Issue #8 (Capital Flow Engine) will use to record
    realised PnL onto the breakers without re-instantiating the
    engine.
  - The audit payload extends Phase 6 with `account_tier`,
    `is_new_open`, `regime`, `risk_permission`,
    `exchange_connection_state`, `daily_loss_breaker_state`,
    `consecutive_loss_breaker_state`, `no_trade_gate_reasons`,
    `no_trade_gate_notes`. Reasons are still rendered as
    byte-compatible strings so Phase 1 / Phase 6 Replay code
    keeps working unchanged.

- **`app/core/enums.py`** new vocabulary:
  - `CircuitBreakerState` (`closed`, `open_daily_loss`,
    `open_consecutive_loss`, `cool_down`).
  - `TradeStateTrigger` (`signal`, `promote`, `downgrade`,
    `timeout`, `lock_profit`, `distribution_alert`,
    `forced_exit`, `kill_switch`, `reset`).
  - `RiskRejectReason` typed enum with **23** values covering
    Phase 1 + Phase 6 + Phase 7 reasons. Values match the Phase 1
    / Phase 6 string reasons byte-for-byte so existing tests and
    audit rows stay byte-compatible.

- **Phase 7 boot self-check in `python -m app.main`**.
  - Drives a `TradeStateMachine` `NO_TRADE -> OBSERVE`
    transition for the first mock symbol. One additional
    ``STATE_TRANSITION`` event is written via the state-machine
    module (the Phase 6 boot drill already wrote one
    `IDLE -> IDLE` marker; Phase 7 raises the total to two).
  - Calls `RiskEngine.evaluate(...)` with
    `is_new_open=False`, the Phase 5 regime snapshot, the Phase
    6 manipulation + confirmation levels, and the exchange link
    state. The bootstrap stays a clean approval because every
    `is_new_open=True`-only gate is bypassed.
  - Banner extended with four Phase 7 fields:
    `state_transitions=`, `trade_state=`, `daily_loss_breaker=`,
    `consecutive_loss_breaker=`.

- **Documentation**.
  - `README.md` rewritten: status table updated (Phase 6 ->
    merged, Phase 7 -> this branch); new "Phase 7 deliverable"
    section with the State Machine ladder + transition rules,
    No-Trade Gate composition, Account Life Tier table, Circuit
    Breaker contract, protective-exit caveat, and seven semantic
    locks.
  - `docs/CHANGELOG.md`: this entry. Phase 6 entries are
    preserved below.
  - `app/__init__.py` bumped to `Phase 7 - State Machine Risk
    Engine` / `1.4.0a7`.

#### Phase 7 hard rules enforced

| Rule | Enforcement |
|---|---|
| 1. No trade-state level skipping | `ALLOWED_TRANSITIONS` whitelist + `IllegalStateTransition`. |
| 2. SCOUT cannot become ATTACK directly | SCOUT -> CONFIRM is the only legal step in `ALLOWED_TRANSITIONS`. |
| 3. CONFIRM failures must downgrade | `record_breakout_failure()` after 2 consecutive failures returns SCOUT. |
| 4. DISTRIBUTION_ALERT cannot promote | `promote(...)` refuses with `cannot_promote_from_distribution_alert`. |
| 5. FORCED_EXIT is sticky | `ALLOWED_TRANSITIONS[FORCED_EXIT] = frozenset()`; only `reset()` clears it. |
| 6. Losing position cannot amplify | Refused at promotion; refused at engine via `right_tail_from_principal_forbidden`. |
| 7. SYSTEMIC_RISK -> BLOCK_ALL | `RiskRejectReason.REGIME_BLOCK_ALL` fires for every new opening. |
| 8. ALT_RISK_OFF -> ALLOW_SCOUT no attack | `RiskRejectReason.REGIME_SCOUT_ONLY_FOR_ATTACK` fires for `attack_intent=True`. |
| 9. M3 blocks new open | `RiskRejectReason.MANIPULATION_M3` fires when `is_new_open=True`; protective exits pass with `is_new_open=False`. |
| 10. M2 + attack_intent blocks | `RiskRejectReason.MANIPULATION_M2_ATTACK`. |
| 11. T0/T1 + attack_intent blocks | `RiskRejectReason.TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK`. |
| 12. 5 consecutive losses pause new open | `ConsecutiveLossCircuitBreaker` opens; engine emits `CONSECUTIVE_LOSS_BREAKER_OPEN`. |
| 13. Daily loss threshold pauses new open | `DailyLossCircuitBreaker` opens; engine emits `DAILY_LOSS_BREAKER_OPEN`. |
| 14. State transitions persisted | One `STATE_TRANSITION` event per accepted transition. |
| 15. Reject events carry typed reasons | Every reason is a `RiskRejectReason` value; rendered as its string in the audit row. |

#### Tests

123 new Phase 7 unit tests on top of the 591 retained from
Phase 1-6 = 714 total, all passing.

| File | Tests | What it covers |
| --- | --- | --- |
| `tests/unit/test_state_machine.py` | 27 | Issue #7 acceptance criteria 1+2 (no level skipping, no SCOUT->ATTACK), promotion guards, downgrade ladder, CONFIRM-failure threshold, DISTRIBUTION_ALERT cannot promote, three-bar -> FORCED_EXIT, FORCED_EXIT is sticky / only reset() clears it, Spec §26.4 timeouts (OBSERVE / SCOUT / ATTACK / RIGHT_TAIL_AMPLIFY), `STATE_TRANSITION` events persisted, refusal counter, custom `TimeoutConfig` honoured. |
| `tests/unit/test_account_tier.py` | 12 | Tier A..F classifier boundary tests, F when initial_capital invalid, per-tier `AccountTierPolicy` flags, policy table covers every tier. |
| `tests/unit/test_circuit_breaker.py` | 9 | Issue #7 acceptance criteria 12+13: 5 consecutive losses open the breaker; daily-loss threshold opens the breaker; winning does not auto-close an opened breaker; explicit reset returns to closed; gross daily loss is measured (not net); zero-amount and zero-initial-capital edge cases. |
| `tests/unit/test_no_trade_gate.py` | 23 | Every Spec §27.2 condition individually + composed. Acceptance criteria 4 (M2 + attack), 5 (T0/T1 + attack), 8 (liquidity not exitable), 9 (DATA_DEGRADED), plus the ALLOW_SCOUT-no-attack semantic lock and the M3 protective-exit caveat. |
| `tests/unit/test_risk_engine_phase7.py` | 18 | Liquidity reject, no-exit-channel reject, SYSTEMIC_RISK overrides T4 / M0, ALLOW_ATTACK alone does not authorise live trade, T3 alone does not authorise, M3 protective-exit caveat, DATA_DEGRADED rejects new open / passes protective exit, breakers + tier policies, audit payload exposes Phase 7 fields, Phase 1 + Phase 6 + Phase 7 reasons accumulate, `legacy_request_still_approved`. |
| `tests/unit/test_phase7_boundary.py` | 16 | Phase 1 + Phase 3 invariants unchanged, TradeState / AccountLifeTier / CircuitBreakerState / TradeStateTrigger / `RiskRejectReason` vocabularies pinned, public exports complete (`app.risk.__all__`, `app.state_machine.__all__`), Risk Engine + State Machine expose no write surface, do not subclass ExchangeClientBase, `RiskRequest` Phase 7 fields present, `is_new_open` defaults True. |
| `tests/unit/test_phase7_no_network.py` | 9 | No exchange SDK / LLM import under `app/state_machine/` or `app/risk/`, no `api_key` substring, no `os.environ` / `getenv` (AST scan), no write surface, no Issue #8 / #9 / #10 module imports, no MarketDataBuffer / Mock / Binance constructor call, no stand-alone BTC/ETH module added, no other-DB direct sqlite3.connect. |
| `tests/unit/test_main_entrypoint.py` | extended | Phase 7 banner fields (`Phase 7 - State Machine Risk Engine`, `state_transitions=`, `trade_state=`, `daily_loss_breaker=`, `consecutive_loss_breaker=`). |

#### Issue #7 acceptance criteria

| # | Criterion | Test |
| --- | --- | --- |
| 1 | OBSERVE 不能直接 RIGHT_TAIL_AMPLIFY | `test_observe_cannot_directly_become_right_tail_amplify` |
| 2 | SCOUT 不能直接 ATTACK | `test_scout_cannot_directly_become_attack` |
| 3 | M3 必须禁止新开仓 | `test_m3_blocks_new_open` (gate), `test_m3_does_not_block_protective_exit_when_is_new_open_false` (engine) |
| 4 | M2 + attack_intent 必须禁止 ATTACK / RIGHT_TAIL_AMPLIFY | `test_m2_with_attack_intent_blocks` |
| 5 | T0/T1 + attack_intent 必须拒绝进攻 | `test_t0_with_attack_intent_blocks` / `test_t1_with_attack_intent_blocks` |
| 6 | T3/T4 不得单独批准交易 | `test_t3_alone_does_not_authorise_live_trade` |
| 7 | ALLOW_ATTACK 不得单独批准交易 | `test_allow_attack_alone_does_not_authorise_live_trade` |
| 8 | Liquidity 不可退出时必须拒绝进攻 | `test_liquidity_rejected_blocks_attack` / `test_no_exit_channel_blocks_attack` |
| 9 | DATA_DEGRADED 时必须拒绝或降级 | `test_data_degraded_rejects_new_open` / `test_data_degraded_does_not_block_protective_exit` |
| 10 | stop_unconfirmed 必须拒绝新开仓 | `test_stop_unconfirmed_blocks` (gate) + Phase 1 test still applies |
| 11 | unknown_position 必须拒绝新开仓 | `test_unknown_position_blocks` / `test_unknown_position_rejected_for_new_open` |
| 12 | 连续亏损 5 次必须暂停新开仓 | `test_consecutive_loss_breaker_opens_at_threshold` + `test_consecutive_loss_breaker_blocks_new_open` |
| 13 | 单日亏损触发必须暂停新开仓 | `test_daily_loss_breaker_opens_at_threshold` + `test_daily_loss_breaker_blocks_new_open` |
| 14 | 状态转移事件可回放 | `test_state_transition_event_persisted` / `test_full_ladder_writes_all_transition_events` |
| 15 | 风控拒绝事件包含 reason_tags | `test_audit_payload_includes_phase7_fields` (typed `RiskRejectReason` -> string) |
| 16 | pytest 全部通过 | 714 passed |
| 17 | 不存在 live trading 风险 | Defence-in-depth (see "Live trading risk" below) |
| 18 | 不存在真实交易所下单风险 | Same as 17 |

#### Live trading risk

**None.** Phase 7 is additive on top of the Phase 1 - 6 safety
substrate. No exchange SDK, no HTTP client, no LLM client, no
write surface. The Phase 1 safety lock, the Phase 3 read-only
invariant, the Phase 4 / 5 / 6 boundaries are all unchanged. The
boot banner still shows
`mode=paper live_trading=False right_tail=False llm=False
exchange_live_orders=False`.

#### Real exchange order risk

**None.** No `create_order` / `cancel_order` / `set_leverage` /
`set_margin_mode` call site is added. The four
`SafeModeViolation` refusals on `ExchangeClientBase` continue to
apply.

#### Next-phase recommendation

After this merges, **Issue #8 (Phase 8 - Capital Flow / Profit
Harvest / Rebase)** is the next phase. Issue #8 will:

- Replace the in-memory counters in
  `RiskEngine.consecutive_loss_breaker` / `daily_loss_breaker`
  with `capital.db.capital_snapshots` lookups.
- Drive `RiskEngine.configure_initial_capital(...)` from the
  capital event stream, so Account Tier classification is
  always anchored to the latest `lifetime_equity`.
- Add the `CAPITAL_REBASE` flow: pause new openings, recompute
  `risk_budget`, recompute `account_life_tier`, then resume.
- Land the `withdrawn_profit` invariant so a user-initiated
  withdrawal is NOT misread as a draw-down.

The Phase 7 boundary (no exchange SDK, no real network, no API
key, no write surface, no LLM, no stand-alone BTC/ETH module,
trade-state level whitelist) plus the cumulative defence-in-depth
layers will continue to gate against accidental live trading
until the Go/No-Go checklist (§41) is executed end to end.

### Phase 6 - Scanner Confirmation Manipulation

#### Added

- **`app/scanner/` package** (Spec §17 / §18, Issue #6).
  - `PreAnomalyScanner.evaluate(PreAnomalyInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`PreAnomalyDecision` with `pre_anomaly_score` and
    `reason_tags`. Six Spec §17.2 signals: volume base-expansion,
    spread compression, buy-pressure rising, OI soft-rise,
    funding-not-overheated, minor uptrend.
  - `AnomalyScanner.evaluate(AnomalyInput)` returns
    :class:`AnomalyDecision` with `anomaly_score` (Spec §18.2
    weighted sum) and `reason_tags`. Eight Spec §18.1 signals:
    `OI_SPIKE`, `CVD_SPIKE`, `VOLUME_SPIKE`, `ATR_EXPANSION`,
    `FUNDING_EXTREME`, `LIQUIDATION_SPIKE`, `SWEEP`,
    `MULTI_TIMEFRAME_BREAKOUT`. The Spec §18.2 weights live in
    `AnomalyConfig` and sum to 1.0; sweep + multi-tf-breakout add
    bonuses on top so a clean structural breakout is not missed
    when the underlying spikes are not yet extreme.
  - Emits one ``PRE_ANOMALY_DETECTED`` and one ``ANOMALY_DETECTED``
    event per evaluation. Both event types were already declared
    in the Phase 1 :class:`EventType` vocabulary; Phase 6
    populates them.

- **`app/confirmation/` package - Real Trade Confirmation**
  (Spec §20, Issue #6).
  - `RealTradeConfirmation.evaluate(ConfirmationInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`ConfirmationDecision` mapping fired-signal count to a
    :class:`TradeConfirmationLevel` (T0..T4):
    - 0 signals  -> T0
    - 1 signal   -> T1
    - 2 signals  -> T2
    - 3 signals  -> T3
    - 4+ signals -> T4
  - Five Spec §20.4 signals: CVD-price agreement, breakout hold
    over N bars, large-trade follow-through, trade-efficiency
    above mean, volume-up-price-move.
  - Emits one ``TRADE_CONFIRMED`` event per evaluation.

- **`app/manipulation/` package - Manipulation Detector**
  (Spec §21, Issue #6).
  - `ManipulationDetector.evaluate(ManipulationInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`ManipulationDecision` mapping fired-signal count to a
    :class:`ManipulationLevel` (M0..M3):
    - 0 signals  -> M0
    - 1 signal   -> M1
    - 2 signals  -> M2
    - 3+ signals -> M3
  - Eight Spec §21.2 signals: CVD up + price flat (CVD-price
    divergence), volume up + price no move, OI up + price flat,
    funding hot + price weak, upper-wick growth, buy-pressure-
    no-push, book-wall flicker (caller-supplied count), narrative-
    after-pump.
  - Emits one ``MANIPULATION_DETECTED`` event per evaluation.

- **Risk Engine Phase 6 hooks** (Issue #6 hard rules).
  - `RiskRequest` gained three optional fields:
    - `manipulation_level: ManipulationLevel | None`
    - `trade_confirmation_level: TradeConfirmationLevel | None`
    - `attack_intent: bool` (default `False`)
  - New `RiskRequest.effective_attack_intent` property:
    `right_tail_amplify=True` always implies attack intent.
  - Three new Phase 6 rejection rules in `RiskEngine.evaluate`:
    - `manipulation_m3` -> reject every new opening
      (Spec §21.3 "M3 禁止交易").
    - `manipulation_m2_attack` -> reject ATTACK /
      RIGHT_TAIL_AMPLIFY only (Spec §21.3 "M2 禁止进攻").
    - `trade_confirmation_too_low_for_attack` -> reject ATTACK
      candidates when the level is T0 / T1 (Issue #6 "T0/T1 不
      允许进攻"). Smaller scout / observe actions remain
      allowed; the gate is size-class, not blanket.
  - The ``RISK_REJECTED`` / ``RISK_APPROVED`` audit payload now
    carries `attack_intent`, `manipulation_level`,
    `trade_confirmation_level` so Replay (Issue #10) can
    reconstruct every Phase 6 decision from `events.db` alone.
  - Phase 1 hard rejections (`live_trading_disabled`,
    `right_tail_disabled`, `stop_unconfirmed`, `unknown_position`,
    `trading_mode_inconsistent`) are unchanged. The Phase 6 rules
    are additive.

- **Reason-tag enums in `app/core/enums.py`:**
  - `PreAnomalyReasonTag` (9 values: 6 Spec §17.2 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `AnomalyReasonTag` (11 values: 8 Spec §18.1 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `ConfirmationReasonTag` (8 values: 5 Spec §20.4 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `ManipulationReasonTag` (11 values: 8 Spec §21.2 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).

- **Event-emission throttle**, mirroring the Phase 5 PR #16
  review-fix shape:
  - Each of `PreAnomalyConfig`, `AnomalyConfig`,
    `ConfirmationConfig`, `ManipulationConfig` exposes
    `event_emit_enabled: bool` (default `True`).
  - Every classifier accepts a per-call `emit_event: bool | None`
    on its `evaluate` and `evaluate_snapshot` entry points.
  - Resolution rule: `True` -> always emit, `False` -> always
    skip, `None` -> follow the config flag.
  - Each classifier exposes two counters:
    `<event>_events_emitted` and `<event>_events_skipped`. Issue
    #7's full Top-200 scanner can flip the config flag off and
    confirm via the counter that the event is being skipped.

- **Boot drill in `python -m app.main`:**
  - After the Phase 5 Liquidity loop, runs all four classifiers
    once per mock symbol (3 symbols -> 12 new events: 3
    ``PRE_ANOMALY_DETECTED``, 3 ``ANOMALY_DETECTED``, 3
    ``TRADE_CONFIRMED``, 3 ``MANIPULATION_DETECTED``).
  - Tracks the worst-observed manipulation + confirmation level
    and feeds them into the bootstrap Risk Engine self-check
    with `attack_intent=False` so the bootstrap stays approved.
    The resulting ``RISK_APPROVED`` audit row exercises the new
    payload fields end-to-end.
  - Banner extended with four new fields:
    `pre_anomaly_events`, `anomaly_events`,
    `trade_confirmed_events`, `manipulation_events`.

#### Phase 6 hard rules (per Issue #6)

1. **M2 forbids ATTACK / RIGHT_TAIL_AMPLIFY.** Risk Engine emits
   `manipulation_m2_attack` when `attack_intent=True`.
2. **M3 forbids any new opening.** Risk Engine emits
   `manipulation_m3` regardless of `attack_intent`.
3. **T0 / T1 forbid ATTACK candidates.** Risk Engine emits
   `trade_confirmation_too_low_for_attack` when
   `attack_intent=True`.
4. **All four classifier outputs are persisted as events.** One
   event per evaluation, full payload + reason-tag list, so
   Reflection (Issue #10) and Replay can reconstruct the
   decision from `events.db` alone.
5. **Every reject path carries `reason_tags`.** Tuples of typed
   enum values, never free-form strings.

#### Phase 6 boundary (declared explicitly so the next PR cannot drift)

1. Pre-Anomaly / Anomaly / Real-Trade Confirmation / Manipulation
   ONLY. **No Strategy Engine, no State Machine, no LLM, no
   Capital Flow, no Execution FSM, no Reconciliation.** Those
   land with Issue #7 / #8 / #9 / #10.
2. **No write surface added.** The four `SafeModeViolation`
   refusals on `ExchangeClientBase` are unchanged.
3. **No LLM.** No `app/scanner/`, `app/confirmation/`,
   `app/manipulation/` source file imports `openai`, `anthropic`,
   `deepseek`, or any other LLM client. Issue #6 forbids using an
   LLM to decide direction or to bypass the Risk Engine.
4. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
   `BinanceClient.get_*` continues to raise `NotImplementedError`.
5. **No API key.** No source file under the three new packages
   reads `os.environ` for a credential, accepts an `api_key`
   keyword argument, or persists a key.
6. **No auto-connect.** The classifiers do not own a
   `MarketDataBuffer`, do not own an `ExchangeClientBase`, and
   never instantiate one for themselves.
7. **Phase 1 / 3 / 4 / 5 invariants intact.** The Phase 1 safety
   lock, the Phase 3 read-only invariant, the Phase 4 Market Data
   Buffer boundary, and the Phase 5 Regime / Universe / Liquidity
   contract are unchanged.

#### Tests

`tests/unit/test_pre_anomaly_scanner.py`,
`tests/unit/test_anomaly_scanner.py`,
`tests/unit/test_real_trade_confirmation.py`,
`tests/unit/test_manipulation_detector.py`,
`tests/unit/test_risk_engine_phase6.py`,
`tests/unit/test_phase6_no_network.py`,
`tests/unit/test_phase6_boundary.py`, plus the existing
`tests/unit/test_main_entrypoint.py` extended with the Phase 6
banner + 4 new event-type assertions.

**+117 new Phase 6 tests on top of the 457 retained from Phase
1-5 = 574 total, all passing.**

Issue #6 acceptance criteria covered:

1. **mock 数据能触发 T3** -
   `test_mock_input_triggers_t3` (3 fired signals).
2. **mock 派发数据能触发 M2/M3** -
   `test_distribution_mock_data_triggers_m2`,
   `test_distribution_mock_data_triggers_m3`,
   `test_full_distribution_with_wick_and_flicker_triggers_m3`.
3. **M3 时 Risk Engine 必须拒绝** -
   `test_m3_rejects_observation_request`,
   `test_m3_rejects_attack_request`,
   `test_m3_rejection_writes_audit_event`.
4. **Volume Up + Price No Move 有测试** -
   `test_volume_up_price_no_move_signal_fires`,
   `test_volume_up_price_no_move_does_not_fire_when_price_actually_moves`.
5. **OI Up + Price Flat 有测试** -
   `test_oi_up_price_flat_signal_fires`,
   `test_oi_up_price_flat_does_not_fire_when_price_moves`.
6. **pytest 通过** - 574 passed.

#### Live trading risk

**None.** Phase 6 adds:

- Four pure stateless classifiers (`PreAnomalyScanner`,
  `AnomalyScanner`, `RealTradeConfirmation`,
  `ManipulationDetector`).
- Four reason-tag enums + four event-payload shapes.
- Three new optional fields on `RiskRequest` and three additive
  rejection rules in `RiskEngine.evaluate` that follow the same
  pattern Phase 1 introduced.
- One boot-drill loop that exercises every classifier against
  the deterministic `MockExchangeClient`.
- 117 new unit tests.

What Phase 6 does NOT add:

- No exchange SDK in `requirements.txt` / `pyproject.toml`.
- No outbound HTTP / WebSocket client of any kind in `app/`.
- No LLM client of any kind.
- No `create_order` / `cancel_order` / `set_leverage` /
  `set_margin_mode` call site.
- No new mode flags, no loosened safety lock, no relaxed
  read-only invariant.

The `python -m app.main` boot banner continues to log all five
safety flags every run:

```
mode=paper live_trading=False right_tail=False
llm=False exchange_live_orders=False
```

Sample Phase 6 boot output:

```
[AMA-RT] Phase 6 - Scanner Confirmation Manipulation v1.4.0a6 \
  mode=paper live_trading=False right_tail=False \
  llm=False exchange_live_orders=False \
  databases=5 events_count=31 capital_events=1 \
  exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
  market_data=3/0 market_snapshots=3 data_unreliable=1 \
  regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
  universe=0/3 universe_events=3 liquidity_events=6 \
  pre_anomaly_events=3 anomaly_events=3 trade_confirmed_events=3 \
  manipulation_events=3 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

### Phase 5 - Review fixes (PR #16 review feedback)

The four follow-up clarifications requested on PR #16 are documentation
+ observability only. No mode flag is loosened, no safety lock is
relaxed, no new dependency, no new write surface, no new network
surface. The Phase 1 safety lock and the Phase 3 read-only invariant
are unchanged.

#### Added

- **`UniverseConfig.event_emit_enabled`** (default `True`) -
  construct-time throttle for `UNIVERSE_FILTERED` events. Phase 5's
  boot drill, replay, and reflection paths still observe every
  decision; Issue #6's full Top-200 scanner can flip this to `False`
  to avoid bloating events.db at scan rate. The per-call
  `emit_event=True` override on
  `UniverseFilter.evaluate` / `evaluate_snapshot` / `evaluate_many`
  still lets monitoring write an on-demand audit-trail entry.
  Mirrors Phase 4's
  `MarketDataBufferConfig.market_snapshot_event_emit_enabled`.
- **`LiquidityConfig.event_emit_enabled`** (default `True`) - the
  same construct-time throttle for `LIQUIDITY_CHECKED` events. Two
  events per symbol per tick (one `check="evaluate"` + one
  `check="can_exit_position"`) at Top-200 scan rate would mean
  ~400 events/tick; Issue #6 / #7 high-frequency consumers will flip
  this to `False`.
- **`UniverseFilter.universe_filtered_events_skipped`** property -
  counts decisions that were NOT persisted because either the
  per-call override or the config flag suppressed them. Confirms
  the throttle is doing what it claims.
- **`LiquidityFilter.liquidity_checked_events_skipped`** property -
  the same counter for the Liquidity Filter. Both `evaluate` and
  `can_exit_position` increment it.
- **`emit_event` resolution policy** (mirrors the Phase 4 review
  fix on `MarketDataBuffer.snapshot()`):

  ```text
  emit_event=True   -> always emit (per-call override)
  emit_event=False  -> always skip (per-call override)
  emit_event=None   -> follow config.event_emit_enabled (default)
  ```

  applied on `UniverseFilter.evaluate`,
  `UniverseFilter.evaluate_snapshot`,
  `UniverseFilter.evaluate_many`,
  `LiquidityFilter.evaluate`,
  `LiquidityFilter.evaluate_with_buffer`,
  `LiquidityFilter.can_exit_position`, and the module-level
  `app.liquidity.filter.can_exit_position` free function.

- **`RiskPermission` docstring rewritten** to make the
  regime-cycle-gate vs. trade-approval distinction explicit
  (review items 1 + 2). Key clarifications now part of the
  source:
  1. `ALLOW_ATTACK` is a market-cycle permission, NOT a trade
     approval. A real opening still requires Universe.eligible,
     Liquidity.passed, can_exit_position.feasible, Issue #6 scanners
     (Pre-Anomaly / Anomaly / Real-Trade Confirmation /
     Manipulation), and the Issue #7 Risk Engine's final word.
     The eight-step conjunctive ladder is enumerated in the
     docstring.
  2. `ALLOW_SCOUT` (the `ALT_RISK_OFF` fallback and the unknown-
     inputs default) permits only OBSERVE or a tiny SCOUT
     candidate. Issue #7 MUST further restrict: NO ATTACK, NO
     RIGHT_TAIL_AMPLIFY, SCOUT size capped at the per-trade scout
     budget. The `right_tail_enabled` flag is locked False through
     the limited-live phase regardless.
  3. `OBSERVE_ONLY` blocks new openings; existing positions
     remain managed.
  4. `BLOCK_ALL` is SYSTEMIC_RISK; no new opening of any kind.

- **`REGIME_TO_RISK_PERMISSION` map docstring** in
  `app/regime/models.py` echoes the same warning so anyone reading
  the source-of-truth dict sees the regime-gate vs.
  trade-approval distinction without having to chase the enum.

- **`RegimeSnapshot.risk_permission` docstring warning** -
  pointed at `RiskPermission` for the full ladder. The first
  reader of a `RegimeSnapshot` value will not silently treat
  `ALLOW_ATTACK` as authorisation.

- **`LiquidityFilter.can_exit_position` docstring rewritten** to
  cover the throughput-discount contract (review item 3):
  - The `volume_5m / 300s` fallback is documented as an UPPER
    BOUND, not a conservative estimate. Three reasons are listed
    (calm-tape extrapolation, no-crowding assumption, no ATR / OI
    discount).
  - Issue #7's Risk Engine MUST apply a conservative discount on
    top. Three recommended directions are documented (ATR-scaled
    divisor, fraction-of-average cap, post-discount feasibility
    re-check). Phase 5 ships the gate; sizing decisions are
    Issue #7's job.
  - Degraded-data contract pinned: callers in Phase 7+ MUST pass
    `MarketDataBuffer.is_degraded(symbol)` through, never invert
    `feasible=False`, never feed a stale book with
    `is_data_degraded=False`. The buffer's degraded view is the
    single source of truth.
- **`_VOLUME_WINDOW_5M_SECONDS` module constant** in
  `app/liquidity/filter.py` got its own warning comment block
  describing the same upper-bound assumption set so a future
  reader of the constant does not need to chase the docstring.
- **Free-function `can_exit_position`** docstring restates the
  same throughput-and-degraded contract with a pointer back to
  the method form.

#### Tests

`tests/unit/test_phase5_review_fixes.py` (NEW) covers:
- The two new config flags exist with correct defaults.
- The `*_events_skipped` counters are exposed and start at zero.
- `event_emit_enabled=False` + `emit_event=None` -> emits 0,
  skipped += 1 (Universe and Liquidity).
- `event_emit_enabled=False` + `emit_event=True` -> still emits
  (per-call override beats config).
- `event_emit_enabled=True` + `emit_event=False` -> still skips
  (per-call override beats config).
- `can_exit_position` (both method and free function) honours
  the same `bool | None` resolution rules.
- `RiskPermission` docstring contains the
  "regime-cycle permission" + "NOT a trade approval" wording so
  the regime-gate vs. trade-approval distinction cannot drift.
- `REGIME_TO_RISK_PERMISSION` map docstring contains the same
  warning so a future map mutation cannot silently weaken the
  contract.
- `LiquidityFilter.can_exit_position` docstring contains the
  upper-bound + Issue #7-discount + degraded-data wording.

#### Live trading risk

**None.** This commit only:

- Adds two construct-time throttle flags that default to today's
  behaviour (emit every event).
- Adds two skipped-event counters for monitoring.
- Rewrites three docstrings (`RiskPermission`,
  `REGIME_TO_RISK_PERMISSION`, `RegimeSnapshot.risk_permission`,
  `LiquidityFilter.can_exit_position`) and one constant comment
  (`_VOLUME_WINDOW_5M_SECONDS`).
- Adds one test file pinning the new flags + the docstring
  boundary phrases.

The Phase 1 safety lock, the Phase 3 read-only invariant, the
Phase 4 Market Data Buffer boundary, and the original Phase 5
classifier behaviour are all unchanged.

### Phase 5 - Regime Universe Liquidity

#### Added

- **`app/regime/` package** introducing the Regime Engine (Spec §15).
  - `RegimeConfig`, `RegimeInput`, `RegimeSnapshot` (Pydantic v2 frozen
    value objects).
  - `REGIME_TO_RISK_PERMISSION` static map (Spec §15.3) wired into
    Phase 7's future Risk Engine, the Universe Filter, and the
    Liquidity Filter.
  - `RegimeEngine.evaluate(request=...)` for tests and
    `RegimeEngine.evaluate(buffer=..., btc_symbol=...)` /
    `evaluate_from_buffer()` for the boot path. The classifier walks
    in this order:

      1. **SYSTEMIC_RISK overrides** - explicit flag, BTC return <=
         configured drop threshold, BTC ATR >= configured extreme.
         All three force `MarketRegime.SYSTEMIC_RISK` /
         `RiskPermission.BLOCK_ALL`.
      2. **Data degraded fallback** - any input flagged
         `data_degraded=True` falls back to `MarketRegime.ALT_RISK_OFF`
         / `RiskPermission.ALLOW_SCOUT`.
      3. **Trend / volatility / liquidity classifier** - five regimes:
         `MEME_RISK_ON`, `SECTOR_ROTATION`, `BTC_ABSORPTION`,
         `ALT_RISK_OFF`, `SYSTEMIC_RISK`.
  - One ``REGIME_UPDATED`` event per evaluation, with the full Spec
    §15.1 payload (`market_regime`, `btc_trend`, `btc_volatility`,
    `alt_liquidity`, `risk_permission`, `reason_tags`).

- **`app/universe/` package** introducing the Universe Filter
  (Spec §16).
  - `UniverseConfig`, `UniverseInput`, `UniverseDecision` value
    objects.
  - `UniverseFilter.evaluate(...)` walks **nine** reject conditions in
    a stable order and returns the full reason list:
    `REGIME_BLOCKED`, `DATA_DEGRADED`, `ABNORMAL_DATA_FLAG`,
    `DATA_RELIABILITY_TOO_LOW`, `CONTRACT_NOT_TRADING`,
    `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`, `TRADE_DISCONTINUOUS`,
    `VOLUME_BELOW_MINIMUM`.
  - `evaluate_snapshot(snapshot, symbol_meta=, regime=, ...)`
    convenience helper consumes the Phase 4 `MarketSnapshot` directly.
  - One ``UNIVERSE_FILTERED`` event per symbol with the eligibility
    decision, full reject-reason list, and the input metrics. The
    event is persisted regardless of the eligible / rejected outcome
    so Replay (Issue #10) can rebuild the decision from events.db.

- **`app/liquidity/` package** introducing the Liquidity Filter
  (Spec §19).
  - `LiquidityConfig`, `LiquidityInput`, `LiquidityDecision`,
    `ExitPlan`, `Side` value objects.
  - **`app/liquidity/slippage.py`** - pure helpers: `estimate_book_walk`,
    `estimated_slippage_pct`, `walk_book_for_quote_notional`. Each
    walks the *opposite* side of the order book against a planned qty
    or a planned quote-notional and returns a `BookWalkResult` with
    cleared qty, weighted-average fill price, worst price, slippage
    pct, and an `exhausted` flag. No state, no events, no IO.
  - `LiquidityFilter.evaluate(...)` produces a `LiquidityDecision`
    with `spread_score`, `depth_score`, `estimated_slippage_pct`,
    `estimated_exit_seconds`, `exit_plan`, and the full reject-reason
    list. Reasons: `REGIME_BLOCKED`, `DATA_DEGRADED`, `BOOK_MISSING`,
    `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`, `SLIPPAGE_TOO_HIGH`,
    `NO_EXIT_CHANNEL`, `EXIT_TOO_SLOW`. Spec §19.1.
  - **`LiquidityFilter.can_exit_position(symbol, qty,
    max_slippage_pct, max_seconds, ...)`** (Spec §19.2 - mandatory
    function). Returns an `ExitPlan` describing whether the position
    can be flattened within `max_seconds` at `<= max_slippage_pct`
    given the current book and rolling 5-minute throughput.
    `feasible=False` is the binary the Risk Engine (Issue #7) will
    consult through the No-Trade Gate.
  - Module-level **`can_exit_position(...)` free function** so
    Issue #7's No-Trade Gate can call it without keeping a filter
    instance around.
  - One ``LIQUIDITY_CHECKED`` event per call, tagged
    `check="evaluate"` or `check="can_exit_position"`, with the full
    metric set on the payload.

- **Core vocabulary additions** in `app/core/enums.py`:
  - `BtcTrend` (UP / SIDEWAYS / DOWN / UNKNOWN).
  - `BtcVolatility` (LOW / NORMAL / HIGH / EXTREME / UNKNOWN).
  - `AltLiquidity` (EXPANDING / STABLE / CONTRACTING / DRY / UNKNOWN).
  - `RiskPermission` (ALLOW_ATTACK / ALLOW_SCOUT / OBSERVE_ONLY /
    BLOCK_ALL). Spec §15.3 maps every regime to one of these values.
  - `UniverseRejectReason` - 9 hardcoded reasons.
  - `LiquidityRejectReason` - 8 hardcoded reasons.
  - `MarketRegime` was already declared in Phase 1; the
    `REGIME_UPDATED` / `UNIVERSE_FILTERED` / `LIQUIDITY_CHECKED`
    event types were already declared in Phase 1 too. Phase 5
    populates them.

#### Phase 5 boot self-check in `python -m app.main`

Phase 5 extends the boot drill to drive every new module against the
same deterministic in-process mock + buffer:

  - One ``REGIME_UPDATED`` event written. The default mock seed
    classifies as `ALT_RISK_OFF / ALLOW_SCOUT` (BTC trend cannot be
    derived from the seed - we have no historical bars - so the
    engine falls back to the conservative risk-off label, exactly as
    Issue #5 mandates).
  - One ``UNIVERSE_FILTERED`` event per symbol. The deterministic
    mock book is intentionally shallow, so the boot drill exercises
    the rejection path end-to-end (depth_insufficient,
    trade_discontinuous, regime_blocked when applicable).
  - Two ``LIQUIDITY_CHECKED`` events per symbol: one from
    `LiquidityFilter.evaluate` (`check="evaluate"`) and one from
    `LiquidityFilter.can_exit_position` (`check="can_exit_position"`).
  - A `regime_gate` health probe is registered. It reports
    `DEGRADED` only when `risk_permission` is `BLOCK_ALL`.
  - Banner extended with seven Phase 5 fields:
    `regime=<market_regime>/<risk_permission>`, `regime_events`,
    `universe=<eligible>/<total>`, `universe_events`,
    `liquidity_events`.

  Sample boot output (default mock seed; same shape every run):

  ```
  [AMA-RT] Phase 5 - Regime Universe Liquidity v1.4.0a5 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=19 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
    universe=0/3 universe_events=3 liquidity_events=6 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

#### Phase 5 hard rules enforced

1. **SYSTEMIC_RISK -> BLOCK_ALL** is the only action attached to
   `RiskPermission.BLOCK_ALL`, which sits in
   `UniverseConfig.blocking_risk_permissions` and
   `LiquidityConfig.blocking_risk_permissions` by default. Any new
   opening through either filter is hard-rejected with
   `REGIME_BLOCKED`.
2. **Insufficient liquidity -> reject** with reasons. The Liquidity
   Filter inspects spread, depth, slippage, and exit time;
   any single threshold violation produces a typed reject reason.
3. **No exit channel -> reject the attack candidate.** The
   `can_exit_position` book walk returns `exhausted=True` when the
   book runs out before `qty` is filled; that maps to
   `NO_EXIT_CHANNEL` and `feasible=False` on the `ExitPlan`.
4. **Data degraded -> reject (or downgrade for the regime).** The
   buffer's `is_degraded(symbol)` flows into both filters as
   `is_data_degraded=True`, producing `DATA_DEGRADED` reject reasons.
   The Regime Engine treats the same flag as a fall-back to
   `ALT_RISK_OFF / ALLOW_SCOUT`.
5. **Every reject carries `reject_reasons`.** Both filters return
   `tuple[RejectReason, ...]` plus a free-form `notes` tuple.
6. **Every reject is persisted as one event.** The
   ``UNIVERSE_FILTERED`` and ``LIQUIDITY_CHECKED`` events carry the
   full metric snapshot AND the reason list, so Replay (Issue #10)
   can rebuild the decision from events.db alone.

#### Phase 5 boundary (declared explicitly to avoid drift)

This PR observes the boundary set by Issue #5:

1. **Regime / Universe / Liquidity ONLY.** No anomaly scanner, no
   real-trade confirmation, no manipulation detector, no strategy,
   no state machine. Those land in Issue #6 / #7.
2. The three engines read from the Phase 4 `MarketDataBuffer` and
   the Phase 3 `ExchangeClientBase` only. **They do NOT call any
   write surface; they do NOT add any write surface.** The four
   `SafeModeViolation` refusals on `ExchangeClientBase` are
   unchanged.
3. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
   `BinanceClient.get_*` continues to raise `NotImplementedError`
   for every read method.
4. **No API key.** None of `app/regime/`, `app/universe/`,
   `app/liquidity/` parameterises a credential, reads `os.environ`
   for one, or has an `api_key` keyword argument anywhere.
5. **No write surface.** Same refusal as Phase 3 / Phase 4.
6. **No auto-connect.** The three engines do not own a
   :class:`MarketDataBuffer`, do not own an
   :class:`ExchangeClientBase`, and never instantiate one for
   themselves. Tests pass stub buffers / explicit inputs.
7. **Tests do not depend on real network**
   (`test_phase3_no_network.py`, `test_phase4_no_network.py`, and
   the new `test_phase5_no_network.py`).
8. `BinanceClient.get_account_snapshot` continues to refuse outright
   in Phase 3, Phase 4, **and** Phase 5. No change.

#### Not in Phase 5 (deferred)

- Issue #6 - Pre-anomaly / Anomaly / Real-Trade Confirmation /
  Manipulation Detector.
- Issue #7 - Full Risk Engine + State Machine (will read
  `RegimeSnapshot.risk_permission`, `UniverseDecision.eligible`, and
  `LiquidityFilter.can_exit_position` at the No-Trade Gate).
- Issue #8 - Capital Flow Engine.
- Issue #9 - Real Execution FSM + Reconciliation.
- Issue #10 - LLM, Telegram outbound, Replay diff reports,
  Reflection.

#### Live trading risk

**None.** Phase 5 ships only three pure classifiers (`RegimeEngine`,
`UniverseFilter`, `LiquidityFilter`), pure helpers
(`estimate_book_walk`, `walk_book_for_quote_notional`), three new
event-emission paths through the existing `EventRepository`, and a
boot-time self-check that drives them through one decision per
symbol against the deterministic `MockExchangeClient`. No exchange
SDK is added. No outbound HTTP / WebSocket library is imported. No
API key is read. No write surface is added. The Phase 1 safety
lock, the Phase 3 read-only invariant, and the Phase 4 Market Data
Buffer boundary are unchanged. Seven layers of defence (config
lock, Phase 1 boot assertion, Phase 3 read-only assertion, Risk
Engine refusal, base-class write-surface refusal, Phase 4 no-network
/ no-API-key tests, Phase 5 no-network / no-write-surface / no-API-key
tests) are all unit-tested.

### Phase 4 - Review fixes (PR #15 review feedback)

#### Added

- **`MarketDataBufferConfig.market_snapshot_event_emit_enabled`**
  (default `True`) - construct-time throttle for `MARKET_SNAPSHOT`
  events. Phase 4 keeps the existing per-call
  ``snapshot(symbol, emit_event=...)`` override; this config flag
  lets a Phase 5+ high-frequency consumer (anomaly scanner, regime
  engine) flip the default once instead of having to remember
  ``emit_event=False`` at every call site. The MarketSnapshot return
  value is unchanged - only the events.db append is suppressed -
  so downstream code stays event-shape-stable.
- **`MarketDataBuffer.market_snapshot_events_skipped`** property +
  **`BufferStats.market_snapshot_events_skipped`** field. Confirms
  that the throttle is actually doing what it claims to do.
- **`MarketDataBuffer.late_trades_dropped_total`** property +
  **`BufferStats.late_trades_dropped_total`** field. Aggregates
  `CandleBuilder.dropped_late_trades` across every tracked symbol
  so an out-of-order tape (mis-ordered REST replay, inverted aggTrade
  delivery, producer clock skew) is observable from a single counter.
  Issue #5 / #6 monitoring will alert on this.
- **`refresh_from_exchange` docstring rewritten** to declare the
  Phase 4 boundary verbatim: mock-only / fixture-driven by default,
  no auto-connect to a real public adapter, opt-in only with no API
  key and no write surface, tests must not depend on real network.
  The contract is pinned by
  `tests/unit/test_market_data_buffer_review_fixes.py
  ::test_refresh_from_exchange_docstring_declares_phase4_boundary`.
- **8 new unit tests**
  (`tests/unit/test_market_data_buffer_review_fixes.py`):
  - `test_default_emits_market_snapshot_event`
  - `test_explicit_emit_false_skips_event`
  - `test_config_flag_disables_emit_by_default`
  - `test_config_flag_off_but_explicit_true_still_emits`
  - `test_late_trades_dropped_counter_starts_at_zero`
  - `test_late_trades_dropped_counter_increments_on_out_of_order_tape`
  - `test_late_trades_dropped_counter_isolates_per_symbol_aggregate`
  - `test_refresh_from_exchange_docstring_declares_phase4_boundary`

#### Changed

- `MarketDataBuffer.snapshot()` parameter `emit_event` is now
  `bool | None` (default `None`); `None` resolves to the new config
  flag. `True` / `False` overrides remain available per call. This is
  source-compatible: every existing call site that passed
  `emit_event=True` / `emit_event=False` keeps its old behaviour
  exactly.

#### Tests

**+8 review-fix tests on top of 311 = 319 total. Full suite: 319
passed in 2.21s.**

#### Live trading risk

None. The review fixes only add observability counters, a
construct-time throttle for an existing event emission, and tighten
the docstring of an existing helper. No new mode flag, no loosened
safety lock, no new dependency, no new write surface, no new
network surface.

### Phase 4 - Market Data Buffer

#### Added
- **`app/market_data/` package** introducing the in-process Market
  Data Buffer that every later phase will read from. The package
  never imports an exchange SDK, never opens an outbound socket,
  never reads a credential, never adds a write surface. This is
  asserted by `tests/unit/test_phase4_no_network.py` (and by the
  pre-existing repo-wide `test_phase3_no_network.py`).

- **`app/market_data/models.py`** - frozen Pydantic v2 value objects:
  - `Bar`, `BarInterval` (`M1` / `M5`).
  - `LiquidationEvent`, `LiquidationSide` (data shape only - Phase 4
    does NOT subscribe to a real liquidation feed).
  - `MarketDataBufferConfig`, `MarketDataStalenessConfig` -
    rolling-window widths (1m / 5m / 15m), bar-history sizes, ATR
    windows, per-surface staleness thresholds.
  - `MarketDataDegradedReason` enum: `never_initialised`,
    `exchange_disconnected`, `exchange_degraded`, `trades_stale`,
    `orderbook_stale`, `oi_stale`, `funding_stale`,
    `rest_ws_conflict`, `explicit_mark`. Vocabulary locked by
    `tests/unit/test_market_data_models.py::test_degraded_reason_vocabulary`.
  - `BufferStats` - per-tick observability shape exposed by
    `MarketDataBuffer.stats()`.
  - The Spec §11.1 `MarketSnapshot` model lives in
    `app/core/models.py` (Phase 1) - this PR populates it, it does
    NOT redefine it.

- **`app/market_data/candles.py`** - streaming OHLCV builder with
  buy / sell taker volume split. Late trades (arrived after their
  bucket has already closed) are *dropped*, not back-filled (Spec
  §14.2: silent rewrites are forbidden); the
  `dropped_late_trades` counter exposes the count for monitoring.
  Multi-minute gaps between trades are filled with **flat synthetic
  bars** so ATR sees no missing slots.

- **`app/market_data/cvd.py`** - pure CVD calculator
  (`signed_volume`, `compute_cvd`). Honours Binance's
  `is_buyer_maker=True` convention as "the aggressor was a seller";
  falls back to `RecentTrade.side` when the flag is unset (mock
  fixtures).

- **`app/market_data/atr.py`** - SMA-of-True-Range over closed
  bars. Returns `None` for fewer than two closed bars. Wilder-style
  EMA smoothing is deliberately deferred to Issue #6 / #7 - SMA is
  enough for Phase 4's data-quality role and trivially deterministic
  under replay.

- **`app/market_data/oi.py`** + **`app/market_data/funding.py`** -
  `OpenInterestSnapshotState` and `FundingSnapshotState` keep the
  latest plus previous snapshot per symbol. Out-of-order updates are
  rejected. Cross-symbol updates raise `ValueError`. `delta()` and
  `percent_change()` handle the zero-baseline case explicitly.

- **`app/market_data/liquidation.py`** - bounded
  `LiquidationFeedState` deque per symbol; FIFO eviction with a
  configurable capacity. Phase 4 ships only the data structure and a
  `LiquidationEvent` shape - there is no `get_liquidations` method
  on the gateway, no real-time feed, no auto-subscribe.

- **`app/market_data/buffer.py` - `MarketDataBuffer`**:
  - Lazy per-symbol state via `track(symbol)` or auto-creation on
    first ingest.
  - Rolling trade windows for **1m / 5m / 15m**, anchored to the
    *latest observed timestamp across all surfaces* so the buffer
    is fully deterministic under replay (Spec §14, Issue #4
    "necessary support" list).
  - 1m and 5m candle builders fed by every ingested trade.
  - Latest order book per symbol with reliability tier carried.
  - Latest / previous funding rate and open interest.
  - Bounded liquidation history.
  - **`is_degraded(symbol)` and `degraded_reasons(symbol)`** for the
    future No-Trade Gate (Issue #7) and Reconciliation loop
    (Issue #9). Spec §14.2 + §31: untrustworthy data must NOT feed
    new openings.
  - **`snapshot(symbol)`** returns a Spec §11.1 `MarketSnapshot`
    populated with `last_price`, `bid`, `ask`, `spread_pct`,
    `volume_1m`, `volume_5m`, `cvd_1m`, `cvd_5m`, `atr_1m`,
    `atr_5m`, `oi`, `funding_rate`, `orderbook_depth_usdt`. Emits a
    `MARKET_SNAPSHOT` event when an `EventRepository` is wired in.
  - **`cvd_15m(symbol)`** for the 15-minute window required by
    Issue #4.
  - **REST vs WS conflict detection** (Spec §14.2): when an
    incoming order book has a different `DataReliability` tier than
    the existing one, the buffer emits a single
    `DATA_UNRELIABLE` event tagged
    `MarketDataDegradedReason.REST_WS_CONFLICT` with the previous
    and incoming tiers in the payload, AND keeps the strong-tier
    book on a tier downgrade. A tier upgrade (e.g. REST -> WS) is
    accepted but still counted; the audit trail captures both.
  - **`on_websocket_disconnect(reason=...)`** - marks every tracked
    symbol as `EXCHANGE_DISCONNECTED` and writes one batched
    `DATA_UNRELIABLE` event with `scope=all_symbols`,
    `trigger=websocket_disconnect`, and the full symbol list.
    Issue #4 acceptance criterion 4.
  - **`on_websocket_reconnect(reason=...)`** - clears the explicit
    disconnect / degraded reasons (stale-window reasons are
    recomputed and may legitimately stay set until fresh data
    arrives).
  - **Exchange-link health propagation**: when wired to an
    `ExchangeClientBase`, the gateway's
    `ExchangeConnectionState.{DISCONNECTED, DEGRADED, UNINITIALISED}`
    automatically maps to the corresponding degraded reason on every
    symbol view.
  - **`mark_degraded` / `clear_explicit_degraded`** for manual
    test-driven and Reconciliation-driven transitions.
  - **`refresh_from_exchange(symbol)`** - convenience helper that
    pulls trades, book, funding and OI from the attached client and
    feeds them through the ingest path. **Phase 4 only ever wires a
    `MockExchangeClient`** here; if a `BinanceClient` skeleton ever
    gets wired in, the call surfaces the underlying
    `NotImplementedError` instead of pretending it has data
    (asserted by
    `test_refresh_from_exchange_propagates_notimplementederror_from_binance`).
    The helper batches its emits so a fresh refresh produces at most
    one `DATA_UNRELIABLE` event per symbol regardless of how many
    surfaces it touched.

- **Boot path additions** in `python -m app.main`:
  - `_build_phase4_boot_seed()` constructs a deterministic
    in-process tape anchored at `now_ms()` so the buffer's
    staleness gate sees a fresh window. **No fixture file is read,
    no network call is made, no credential is consumed.**
  - `MarketDataBuffer` is instantiated, every symbol the mock
    exposes is `track`-ed, `refresh_from_exchange`-ed, and
    `snapshot`-ed.
  - One WS disconnect + reconnect probe is driven through the
    buffer so the audit trail at boot includes one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`
    and one recovery.
  - A `market_data_buffer` health probe is registered that goes
    `DEGRADED` if any symbol is degraded.
  - Banner extended with three Phase 4 fields:
    - `market_data=<tracked>/<degraded>`
    - `market_snapshots=<count>`
    - `data_unreliable=<count>`

  Sample boot output:

  ```
  [AMA-RT] Phase 4 - Market Data Buffer v1.4.0a4 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=9 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

- **76 new unit tests**:
  - `tests/unit/test_market_data_models.py` (8) - `Bar` /
    `LiquidationEvent` shape, `BarInterval` widths,
    `MarketDataBufferConfig` defaults, frozen-ness, degraded-reason
    vocabulary.
  - `tests/unit/test_market_data_candles.py` (12) - bucket
    alignment, first-trade live bar, in-place updates, bar
    closing, multi-minute gap filling with flat bars, late-trade
    drop, buy/sell volume split (both `is_buyer_maker` and `side`
    fallback), `force_close` padding, history bound, cross-symbol
    rejection.
  - `tests/unit/test_market_data_cvd.py` (7) - `signed_volume`
    sign, `compute_cvd` empty / pure-buy / pure-sell / mixed,
    Issue #4 acceptance criterion 1.
  - `tests/unit/test_market_data_atr.py` (8) - True Range with /
    without prev close, `compute_atr` `None` cases, simple-average
    correctness, prev-close from history when window is smaller
    than history, unclosed-bar exclusion, Issue #4 acceptance
    criterion 2.
  - `tests/unit/test_market_data_oi_funding_liquidation.py` (12) -
    initial state, advance-on-update, out-of-order rejection,
    cross-symbol rejection, zero-baseline percent change,
    capacity eviction, recent-since-ts filter.
  - `tests/unit/test_market_data_buffer.py` (25) - lazy track,
    never-initialised symbol, rolling-window math, MarketSnapshot
    Spec §11.1 fields, CVD helpers match `compute_cvd`,
    Issue #4 acceptance criterion 3 (no data -> degraded; partial
    data -> stale; fresh data -> clean), live recomputation of
    staleness, Issue #4 acceptance criterion 4 (WS disconnect ->
    DATA_UNRELIABLE), reconnect clears explicit reasons,
    `mark_degraded` / `clear_explicit_degraded` semantics, REST vs
    WS conflict in both directions plus same-tier-newer-wins,
    exchange health propagation (DISCONNECTED, DEGRADED), per-symbol
    liquidation deque, stats consistency, `refresh_from_exchange`
    requires a client, `BinanceClient` skeleton surfaces
    `NotImplementedError`, disconnected-client short-circuit,
    constructor refuses an `api_key` parameter, `BinanceClient`
    still refuses credentials at construction.
  - `tests/unit/test_phase4_no_network.py` (4) - `app/market_data/`
    imports no network library, mentions no `api_key` /
    `api_secret`, never creates `market.db`, and
    `BinanceClient.get_account_snapshot` continues to raise
    `NotImplementedError` with messages that mention "skeleton",
    "phase 4" and "api key".
  - `tests/unit/test_main_entrypoint.py` extended (1 test, now
    Phase 4-aware) - banner contains `Phase 4 - Market Data
    Buffer`, `market_data=...`, `market_snapshots=...`,
    `data_unreliable=...`, and the events DB contains at least one
    `MARKET_SNAPSHOT` event plus one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 4 - Market Data
  Buffer`; `__version__` is `1.4.0a4`.
- `app/main.py` - new `_build_phase4_boot_seed()` helper, boot path
  drives the buffer through one full ingest + snapshot + WS
  disconnect / reconnect cycle. The Phase 1
  `_assert_phase1_safety()` and Phase 3 `_assert_phase3_read_only()`
  guards are unchanged. `STATE_TRANSITION` reason updated to
  `phase4_boot`. Exchange shutdown reason updated to
  `phase4_shutdown`.

#### Phase 4 boundary (declared explicitly to avoid drift)

This PR observes the boundary set by Issue #4 and the user-facing
review of PR #14:

1. **Market Data Buffer ONLY.** No Regime / Universe / Liquidity
   engine, no Scanner, no Confirmation, no Manipulation Detector.
2. The buffer is fed by `MockExchangeClient` / fixture data **by
   default**. The boot path uses the deterministic mock; tests use
   deterministic fixtures.
3. **No real Binance WebSocket and no real REST.** `BinanceClient`
   continues to raise `NotImplementedError` for every read method.
4. **No API key.** `BinanceClient.__init__` still refuses any
   credential. `MarketDataBuffer.__init__` exposes no `api_key`
   parameter (asserted by a test that passes the kwarg and expects
   a `TypeError`).
5. **No write surface.** The four `SafeModeViolation` refusals on
   `ExchangeClientBase` (`create_order`, `cancel_order`,
   `set_leverage`, `set_margin_mode`) are unchanged.
6. **No auto-connect.** `MarketDataBuffer` opens no socket; it only
   receives data via `ingest_*` calls or via
   `refresh_from_exchange` against a deterministic
   `MockExchangeClient`.
7. **Tests do not depend on real network.** Both
   `test_phase3_no_network.py` and the new
   `test_phase4_no_network.py` enforce this.
8. **`BinanceClient.get_account_snapshot` remains mock-only /
   skeleton-only in both Phase 3 and Phase 4.** Real account
   snapshots require an authenticated REST call and an API key,
   forbidden until the limited-live phase. Locked by
   `test_binance_client_get_account_snapshot_remains_skeleton` in
   `test_phase4_no_network.py`.

#### Not in Phase 4 (deferred)
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine (will read `is_degraded` from this
  buffer to drive the No-Trade Gate).
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a
  real `create_order` is *allowed* to exist, behind the Risk
  Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports,
  Reflection.

#### Live trading risk
**None.** Phase 4 ships only an in-process buffer and a
deterministic boot drill. No exchange SDK is added. No outbound
HTTP / WebSocket library is imported. No API key is read. No
write surface is added. The Phase 1 safety lock and Phase 3
read-only invariant are unchanged. Six layers of defence (config
lock, Phase 1 boot assertion, Phase 3 read-only assertion, Risk
Engine refusal, base-class write-surface refusal, Phase 4
no-network / no-api-key tests) are all unit-tested.

### Phase 3 - Review fixes (Issue #3 review feedback)

#### Changed

- **Reliability tier alignment** (review item 1). The default
  `OrderBook.reliability` was tier B; this was inconsistent with
  the rest of the PR description and with the actual Phase 4+ source
  (a WS-maintained depth-diff book is tier A). Updated:
  - `app/exchanges/base.ExchangeClientBase.reliability_tiers` now
    returns `get_orderbook -> A` (was B). The full table is now
    locked: `get_recent_trades=A`, `get_orderbook=A`,
    `get_funding_rate=B`, `get_open_interest=B`, `get_symbols=B`,
    `get_account_snapshot=B`.
  - `app/exchanges/models.OrderBook.reliability` default raised from
    `DataReliability.B` to `DataReliability.A`. Adapters that fall
    back to a REST snapshot when the WS link is degraded must tag
    that response tier B explicitly.
  - `MockExchangeClient.get_orderbook` now stamps its synthetic book
    as tier A (it is the in-memory analogue of a WS-maintained book).
    A tier-B `OrderBook` supplied via `MockExchangeSeed.orderbooks`
    is preserved as-is - the mock does not silently upgrade it.
  - 4 new tests pin the new contract:
    `test_reliability_tiers_contract` (full-table assertion),
    `test_reliability_tiers_lists_all_six_read_methods`,
    `test_orderbook_default_reliability_is_a_at_model_level`,
    `test_orderbook_can_be_tagged_tier_b_for_rest_fallback`,
    `test_mock_synthetic_orderbook_is_tier_a`,
    `test_mock_can_serve_a_tier_b_seed_orderbook`.
- **Phase 4 constraint hardened** (review item 2). The Phase 4
  recommendation in the PR description and the
  `BinanceClient.get_*` `NotImplementedError` messages are reworded:
  Phase 4 (Market Data Buffer) must drive the buffer from
  `MockExchangeClient` / fixture data **by default**; any real public
  read-only WS / REST adapter must be opt-in (off by default),
  require no API key, expose no write surface, and not auto-connect
  to the real exchange. `WebSocketManager`'s docstring is reworded
  for the same reason - it no longer claims Phase 4 will adopt any
  particular network library. New test
  `test_binance_real_market_data_methods_message_is_explicit_about_phase4_constraints`
  asserts every public-data `NotImplementedError` message contains
  the four constraint phrases ("opt-in", "off by default", "no API
  key", "no write surface", "auto-connect").
- **`get_account_snapshot` mock-only / skeleton-only** (review item
  3). The `BinanceClient.get_account_snapshot` `NotImplementedError`
  message is rewritten to say explicitly: real account snapshots
  require authentication and an API key, both of which are forbidden
  until the limited-live phase; the only working implementation is
  `MockExchangeClient.get_account_snapshot`. New test
  `test_binance_get_account_snapshot_message_is_explicit_about_no_api_key`
  asserts the message contains "api key", "authenticated",
  "mockexchangeclient", and "limited-live".
- **README** updated with an explicit "Reliability tier contract"
  table and a "Phase 4 constraints" section that declares the four
  Phase 4 invariants up-front so the next PR cannot drift.

#### Tests
**+7 review-fix tests on top of 97 Phase 3 tests = 104 Phase 3 tests
total. Full suite: 211 passed in 1.87s** (107 retained from
Phase 1 / 2 + 104 Phase 3).

#### Live trading risk
None. The review fixes only adjust default reliability tiers,
strengthen `NotImplementedError` messages, and tighten Phase 4
constraint documentation. No new mode flag, no loosened safety lock,
no new dependency, no new write surface.

### Phase 3 - Exchange Gateway Read-Only

#### Added
- **`app/exchanges/` package** introducing the read-only Exchange Gateway
  abstraction. The package never imports an exchange SDK and never opens
  an outbound socket; this is asserted by
  `tests/unit/test_phase3_no_network.py`.
- **`ExchangeClientBase` abstract class** (`app/exchanges/base.py`):
  - 6 abstract read-only methods: `get_symbols`, `get_orderbook`,
    `get_recent_trades`, `get_funding_rate`, `get_open_interest`,
    `get_account_snapshot`.
  - 4 **concrete** write surfaces (`create_order`, `cancel_order`,
    `set_leverage`, `set_margin_mode`) that **always** raise
    `SafeModeViolation`. Subclasses inherit the refusal.
  - `ExchangeHealth` value-object with state transitions
    (`UNINITIALISED -> CONNECTED -> DEGRADED / RECONNECTING /
    DISCONNECTED`), counters and an `is_data_trustworthy()` predicate.
  - `WebSocketManager` skeleton (`connect / disconnect / subscribe /
    unsubscribe`) that emits `DATA_UNRELIABLE` with the pending
    subscription set on every drop. **No real socket is opened in
    Phase 3.**
  - Health transitions emit `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `EXCHANGE_DEGRADED` events through
    `EventRepository`.
  - `_require_trustworthy(surface=...)` helper raises
    `ExchangeConnectionError` whenever the link is not `CONNECTED`
    (Spec §14.2 + §31).
  - `READ_ONLY_METHODS` and `WRITE_SURFACE_METHODS` module-level
    tuples used by the entrypoint and the test suite to assert the
    Phase 3 contract.
  - `assert_read_only()` boot-time guard.
  - `reliability_tiers` static map documenting the default
    `DataReliability` tier each surface returns (Spec §13.3).
- **`BinanceClient` skeleton** (`app/exchanges/binance.py`):
  - All 6 read methods raise `NotImplementedError` pointing at the
    later phase that owns the real adapter (Phase 4 / 8 / 9).
  - All 4 write methods inherit `SafeModeViolation` from the base
    class (asserted by tests; the skeleton must NOT override them).
  - Constructor refuses any `api_key` / `api_secret` (Spec §37 anti-leak).
- **`MockExchangeClient`** (`app/exchanges/mock.py`):
  - Deterministic in-memory implementation used by the entrypoint and
    the test suite. **No network**.
  - Optional `MockExchangeSeed` for fully predictable test fixtures.
  - `simulate_disconnect` / `simulate_reconnect` /
    `simulate_degraded` test hooks drive the No-Trade Gate paths.
  - Tier-A surfaces refuse when not `CONNECTED`; tier-B REST surfaces
    (`get_symbols`, `get_account_snapshot`) remain usable when
    `DEGRADED` per Spec §13.3.
- **Read-only data models** (`app/exchanges/models.py`): Pydantic v2
  frozen models `ExchangeSymbol`, `OrderBook` (+ `OrderBookLevel`,
  with bid/ask sort validation), `RecentTrade`, `FundingRate`,
  `OpenInterest`, `AccountSnapshot`. Each carries an explicit
  `reliability: DataReliability` field with the default tier per
  surface.
- **New core vocabulary**:
  - `app/core/enums.ExchangeConnectionState` enum (`UNINITIALISED /
    CONNECTED / DEGRADED / RECONNECTING / DISCONNECTED`) with an
    `is_trustworthy` property.
  - `app/core/enums.DataReliability.is_at_least()` helper for
    consistent tier comparisons (Spec §13.3).
  - `app/core/events.EventType.{EXCHANGE_CONNECTED,
    EXCHANGE_DISCONNECTED, EXCHANGE_DEGRADED}`. `DATA_UNRELIABLE` was
    already declared in Phase 1.
  - `app/core/errors.SafeModeViolation` (subclass of
    `SafetyViolation`).
  - `app/core/errors.ExchangeError` and
    `app/core/errors.ExchangeConnectionError`.
- **Phase 3 boot self-check** in `python -m app.main`:
  - Instantiates `MockExchangeClient(event_repo=repo, autostart=True)`,
    runs `assert_read_only()`, **probes every banned write surface**
    and refuses to start unless each one raises `SafeModeViolation`.
  - Calls `get_symbols()` to prove the read path works.
  - Registers an `exchange_link` health probe.
  - Emits `EXCHANGE_CONNECTED` on start and
    `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE` on shutdown so
    replay-based tests can confirm the lifecycle closed.
  - Status banner now reports
    `exchange=<name>/<state> exchange_symbols=N exchange_connected_events=1`.
- **97 new unit tests**:
  - `tests/unit/test_exchange_models.py` (15) - `DataReliability`
    ordering (A>B>C>D), `is_at_least` helper,
    `ExchangeConnectionState.is_trustworthy`, `OrderBook` sort
    validation, frozen models, default reliability tiers per model.
  - `tests/unit/test_exchange_base.py` (20) - cannot instantiate the
    ABC directly; `READ_ONLY_METHODS == __abstractmethods__`; write
    surfaces are concrete on the base class; `SafeModeViolation`
    IS-A `SafetyViolation`; `ExchangeError` IS-A `AMARTError` and is
    NOT a `SafetyViolation`; `assert_read_only` refuses when
    `_live_orders_enabled=True`; `WebSocketManager` connect /
    disconnect lifecycle and the `DATA_UNRELIABLE` event payload;
    `ExchangeHealth` counters; `start` / `stop` / `_mark_degraded`
    emit the matching events through `EventRepository`;
    `_require_trustworthy` refuses when uninitialised / disconnected;
    `reliability_tiers` contract; no network library imports.
  - `tests/unit/test_binance_client.py` (20) - `name='binance'`;
    refuses any `api_key` / `api_secret`; every read method raises
    `NotImplementedError`; every write surface refuses with
    `SafeModeViolation`; every read method is overridden on
    `BinanceClient` itself; write surfaces NOT overridden (inherit
    base refusal); module imports no network library.
  - `tests/unit/test_mock_exchange_client.py` (28) - `autostart`
    emits `EXCHANGE_CONNECTED`; default seed has BTCUSDT, ETHUSDT,
    PEPEUSDT; orderbook / trades / funding / OI / account read
    paths; `MockExchangeSeed` determinism; `simulate_disconnect`
    emits `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE`; tier-A
    surfaces refused when `DEGRADED`; tier-B surfaces (symbols,
    account_snapshot) ALLOWED when `DEGRADED`; both refused when
    `DISCONNECTED`; `simulate_reconnect` restores trust + new
    `EXCHANGE_CONNECTED`; write surfaces refuse; mock does NOT
    override write surfaces; lifecycle smoke; no network library
    imports.
  - `tests/unit/test_phase3_no_network.py` (3) - `requirements.txt`
    and `pyproject.toml` contain no exchange SDK / HTTP client; no
    file under `app/` issues an `import` for any forbidden token.
  - Existing `tests/unit/test_main_entrypoint.py` extended to assert
    the Phase 3 banner fields and the new `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `DATA_UNRELIABLE` events.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 3 - Exchange Gateway
  Read-Only`; `__version__` is `1.4.0a3`.
- `app/main.py` - new `_assert_phase3_read_only(client)` guard that
  probes every entry in `WRITE_SURFACE_METHODS` and raises
  `SafeModeViolation` if any of them stops refusing. The existing
  `_assert_phase1_safety()` check is unchanged. Banner extended with
  `exchange=<name>/<state>`, `exchange_symbols=N`,
  `exchange_connected_events=1`. `STATE_TRANSITION` reason updated to
  `phase3_boot`. The exchange is stopped cleanly on shutdown
  (`reason="phase3_shutdown"`), which emits `DATA_UNRELIABLE` +
  `EXCHANGE_DISCONNECTED`.

#### Not in Phase 3 (deferred)
- Issue #4 - real Market Data Buffer; `BinanceClient` read methods
  remain `NotImplementedError` until then.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine.
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a real
  `create_order` is *allowed* to exist, behind the Risk Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection.

#### Live trading risk
**None.** Phase 3 ships only an abstract read-only gateway plus a
deterministic in-memory mock. The four write surfaces always raise
`SafeModeViolation`; the Phase 1 safety lock is unchanged; no exchange
SDK / HTTP / WebSocket library is installed; no real API key is
accepted by `BinanceClient`. Five layers of defence (config lock, boot
assertion, Phase 3 read-only assertion, Risk Engine refusal, base-class
write-surface refusal) are all unit-tested.

### Phase 2 - Event Sourcing and Database

#### Added
- **Five SQLite databases** (Spec §33.1) opened in WAL mode and migrated
  by an idempotent runner: `events.db`, `trades.db`, `positions.db`,
  `capital.db`, `incidents.db`.
- **New schema files** under `app/database/schemas/`:
  - `trades.sql` - fills (write-once); writers land in Issue #9.
  - `positions.sql` - position lifecycle; writers land in Issues #7/#9.
  - `capital.sql` - `capital_snapshots` (Issue #8) and
    `capital_events_index` (mirror written by Phase 2 EventRepository).
  - `incidents.sql` - `incidents` + `incident_log`; writers land in
    Issues #9/#10.
- **`events.db` schema upgrade**: added the `created_at` column required
  by the Issue #2 field contract; added composite indexes
  `(event_type, timestamp)` and `(symbol, timestamp)` and an
  `order_id` index. The migration auto-upgrades a Phase 1 events.db by
  adding the column and backfilling from `timestamp`.
- **`app/database/connection.DatabaseSet`** - container that opens /
  closes a known set of databases atomically, with typed accessors
  (`.events`, `.trades`, `.positions`, `.capital`, `.incidents`),
  `__iter__`, idempotent `close()`, and an `open_database_set()` context
  manager.
- **`app/database/migrations.migrate_database` and
  `migrate_database_set`** - apply each database's schema; idempotent.
- **`EventRepository` Phase 2 API**:
  - `append_event` / `append_many` (returns events with `created_at`
    populated)
  - `list_events` / `replay_events` (lazy iterator) / `count_events`
  - filters: `event_type`, `event_types` (iterable), `symbol`,
    `source_module`, `position_id`, `order_id`, `since_ts`, `until_ts`,
    `limit`, `offset`
  - persistence failures logged via `loguru` and raised as
    `EventPersistenceError` (no silent loss). Includes a `failed_appends`
    counter for monitoring.
  - capital event helpers: `record_capital_deposit`,
    `record_capital_withdrawal`, `record_profit_harvest`,
    `record_capital_rebase`, `record_risk_budget_recalculated`.
  - **cross-database write**: when constructed with a `capital_conn`
    every `CAPITAL_*` event is mirrored into
    `capital.db.capital_events_index` so Issue #8 has a fast lookup
    table. Mirror failures are logged but do NOT roll back the events
    write (the index is rebuildable from events.db).
- **Phase 1 method aliases preserved** on `EventRepository` (`append`,
  `list`, `replay`, `count`) so the Risk Engine, Telegram bot and
  Execution FSM skeletons keep working unchanged.
- **`scripts/init_db.py`** rewritten to migrate all five databases and
  print each db's journal mode + schema file. Still idempotent.
- **`app/main.py`** opens & migrates all five databases, emits a
  CAPITAL_DEPOSIT marker (paper-mode bookkeeping, amount=0.0) so the
  capital_events_index path is exercised end-to-end. The Phase 1 safety
  lock and `_assert_phase1_safety()` remain unchanged.
- **`app/core/errors.EventPersistenceError`** - typed exception for the
  persistence failure path.
- **`app/core/events.Event.created_at`** - new field; `None` for
  in-memory events, populated by `EventRepository` from the SQLite
  default expression on insert.
- **51 new unit tests**:
  - `tests/unit/test_database_set.py` (12) - DatabaseSet, WAL pragma,
    multi-db migration, Phase-1 -> Phase-2 events.db upgrade.
  - `tests/unit/test_phase2_schemas.py` (8) - column contract for
    trades / positions / capital / incidents tables, event-type
    vocabulary, "no leak from Issue #3/#9/#10" check.
  - `tests/unit/test_event_repository.py` rewritten (31) - full Phase 2
    API surface, filter combinations, persistence failure path, capital
    helpers, capital_events_index mirror.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 2 - Event Sourcing and
  Database`; `__version__` is `1.4.0a2`.
- `tests/conftest.py` - new `phase2_dbs` and `events_repo_with_capital`
  fixtures.

#### Not in Phase 2 (deferred)
- Issue #3 - Exchange Gateway (read-only).
- Issue #4 - Market Data Buffer.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine; uses positions.db.
- Issue #8 - Capital Flow Engine; uses capital_snapshots and the
  capital_events_index table this PR ships.
- Issue #9 - full Execution FSM + Reconciliation; uses trades.db and
  incidents.db.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection;
  uses the incidents tables this PR ships.

#### Live trading risk
None. Phase 2 only adds passive SQLite schemas, a connection helper,
the EventRepository extension and tests. No exchange SDK, no outbound
network, no LLM, no Telegram client. Phase 1 safety lock unchanged.

### Phase 1 - Safety Foundation

#### Added
- Project skeleton under `app/`, `tests/`, `scripts/`, `data/`, `docs/`.
- `pyproject.toml` and `requirements.txt` with a minimal dependency set
  (Pydantic, pydantic-settings, PyYAML, loguru, pytest). No exchange SDK,
  no LLM client, no Telegram client.
- Configuration system (`app/config/`) with `defaults.yaml`, `risk.yaml`,
  `strategy.yaml`, validated by Pydantic schemas in `schema.py`. Loader in
  `settings.py` applies a Phase 1 safety lock that hard-codes:
  `trading_mode=paper`, `live_trading_enabled=false`,
  `right_tail_enabled=false`, `llm_enabled=false`,
  `exchange_live_order_enabled=false`. Even malicious env vars cannot
  flip these flags.
- Core domain types: `app/core/enums.py`, `app/core/events.py`,
  `app/core/models.py`, `app/core/clock.py`, `app/core/errors.py`,
  `app/core/constants.py`. Mirrors Spec §11 / §46 / §12.
- SQLite Event Sourcing substrate: `app/database/schema.sql`,
  `connection.py`, `migrations.py`, `repositories.EventRepository`
  (append, append_many, list, replay, count). WAL mode enforced.
- Init script `scripts/init_db.py`.
- Skeletons (no live behaviour):
  - `app/risk/engine.RiskEngine` - rejects any live or right-tail action.
  - `app/execution/fsm.ExecutionFSM` - typed transition table; refuses
    `request_send_order` without a Risk Engine approval.
  - `app/telegram/bot.TelegramCommandCenter` - in-process command bus,
    audit-logs every command, requires confirmation for `/resume`.
  - `app/monitoring/{metrics,health,alerts}.py` - in-memory only.
- Entrypoint `python -m app.main` - asserts the safety lock, initialises
  the events database, drives one Risk Engine self-check + one Telegram
  `/status` audit event, prints a one-line status banner, exits 0.
- Pytest suite covering enums, models, settings safety lock, event
  repository, Risk Engine, Execution FSM, Telegram bus, monitoring, the
  init script, and the entrypoint smoke test.
- `.env.example` (no real keys), `.gitignore` (excludes `.env`,
  `data/sqlite/*`, `*.db`), `docs/CHANGELOG.md`.
- `README.md` re-written to describe Phase 1 scope, paper-mode default,
  and explicit "no live trading" guarantee.

#### Not in Phase 1 (deferred to later issues)
- Issue #2: full Event Sourcing schema for trades / positions / capital /
  incidents databases, replay across multiple databases.
- Issue #3: any Exchange Gateway code, even read-only.
- Issue #4: Market Data Buffer.
- Issue #5: Regime / Universe / Liquidity engines.
- Issue #6: Pre-anomaly / Anomaly / Confirmation / Manipulation scanners.
- Issue #7: full Risk Engine (No-Trade Gate, Account Life Tier,
  circuit breakers).
- Issue #8: Capital Flow Engine (rebase, harvest).
- Issue #9: full Execution FSM with reconciliation against an exchange.
- Issue #10: LLM Interpreter, Telegram outbound, Replay diff reports,
  Reflection.



### Phase 11C / Offline Rule Sandbox Replay v0 implementation: IN_REVIEW

**Type:** Implementation PR (paper / report / evidence-only).
**Runtime effect:** **none on real trading.** Strictly offline,
deterministic replay over historical evidence reports. No file under
`app/risk/`, `app/execution/`, `app/exchanges/`, `app/telegram/`, or
`app/config/` is modified. No runtime config is written. No event
type is wired into the runtime hot path. No database schema /
migration is touched.

#### Added

- `app/sandbox/__init__.py` — public re-exports for the new sandbox
  package.
- `app/sandbox/offline_rule_sandbox.py` — strictly offline,
  deterministic replay engine. Provides:
  - dataclasses `OfflineRuleSandboxScenario`,
    `HypotheticalRuleChange` (a *hypothetical*, NOT a runtime
    patch — the constructor refuses any `rule_name` containing
    runtime-patch tokens such as `runtime_config_patch`,
    `threshold_patch`, `symbol_limit_patch`,
    `candidate_pool_patch`, `regime_weight_patch`, or
    `strategy_parameter_patch`),
    `OfflineRuleSandboxInput`, `OfflineRuleSandboxResult`,
    `OfflineRuleSandboxReport`;
  - `OfflineRuleSandboxEngine` with deterministic
    `evaluate_scenario` and `build_report`;
  - the `RecommendationLevel` taxonomy `REVIEW_ONLY`,
    `INCONCLUSIVE`, `PROMISING_FOR_PAPER_SHADOW`, `RISKY`,
    `REJECTED_BY_EVIDENCE` (and explicit refusal of `APPLY`,
    `DEPLOY`, `ENABLE_LIVE`, `TRADE`, `BUY`, `SELL`, `GO_LIVE`,
    `AUTO_APPLY`);
  - the `SandboxEvent` taxonomy `OFFLINE_RULE_SANDBOX_REPLAY_RUN`,
    `OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED`,
    `OFFLINE_RULE_SANDBOX_REPORT_GENERATED` (all
    report/export/replay-scope; NO trade-action events);
  - a recursive `assert_no_forbidden_fields` guard run on every
    output payload before serialization, rejecting any payload that
    contains `buy`, `sell`, `long`, `short`, `direction`, `entry`,
    `exit`, `position_size`, `leverage`, `stop`, `stop_loss`,
    `target`, `take_profit`, `risk_budget`, `order`,
    `execution_command`, `runtime_config_patch`,
    `symbol_limit_patch`, `threshold_patch`,
    `candidate_pool_patch`, `regime_weight_patch`,
    `strategy_parameter_patch`, `signal_to_trade`, `should_buy`,
    `should_short`, `apply_change`, `deploy_change`, or
    `enable_live`;
  - a deterministic, auditable first-order sensitivity table
    `_BASE_VECTORS` mapping each `change_type` to a vector over 9
    delta metrics (`coverage_rate_delta`,
    `usable_discovery_rate_delta`, `severe_miss_rate_delta`,
    `false_negative_reject_rate_delta`, `late_chase_rate_delta`,
    `fake_breakout_rate_delta`, `data_gap_rate_delta`,
    `median_mfe_delta`, `median_mae_delta`);
  - `render_report_markdown`, `parse_scenario_dict`,
    `build_input_from_reports`, `example_fixture_scenario`;
  - the frozen `SAFETY_CONTRACT` mirroring every Phase 11C safety
    flag.
- `scripts/run_offline_rule_sandbox_replay.py` — CLI runner producing
  `data/reports/rule_sandbox/offline_rule_sandbox_report.json` and
  `.md`. Imports only `app.sandbox`. Falls back to a deterministic
  `source=example_fixture` scenario when no `--scenario-file` is
  supplied; the fixture is explicitly NOT operator-approved. Emits
  only the three allowed event types.
- `tests/unit/test_offline_rule_sandbox_replay.py` — 19 PASSING tests
  covering: builds scenario without writing runtime config;
  hypothetical rule change is not a runtime patch; deterministic
  delta metrics; missing evidence -> `INSUFFICIENT_EVIDENCE` /
  `INCONCLUSIVE`; data-gap warnings preserved; recommendation level
  never `APPLY` / `DEPLOY` / `TRADE`; `auto_tuning_allowed=False`;
  `writes_runtime_config=False`; `trade_authority=False`;
  `phase_12_forbidden=True`; forbidden fields absent from every
  payload (recursive AST + on-disk check); runner does not import
  `app.risk` / `app.execution` / `app.exchanges` / `app.telegram` /
  `app.config` (AST-based, ignoring docstrings/comments); no
  DeepSeek / LLM / network call path (AST-based); JSON output
  serializable; deterministic output; runner writes both files and
  marks the example fixture; scenario-file parse round-trip;
  `build_input_from_reports` tolerates missing reports;
  `SAFETY_CONTRACT` shape.
- `docs/PHASE_11C_OFFLINE_RULE_SANDBOX_REPLAY.md` — phase rationale,
  schemas, recommendation levels, and explicit "why this is not
  auto-tuning / does not write runtime config / does not authorize
  live trading / does not enter Phase 12" sections.

#### Hard safety boundary (this release)

`mode=paper`, `sandbox_only=True`, `writes_runtime_config=False`,
`auto_tuning_allowed=False`, `trade_authority=False`,
`live_trading=False`, `exchange_live_orders=False`,
`right_tail=False`, `llm=False` (default),
`llm_outbound_enabled=False` (default),
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`,
`phase_12_forbidden=True`.

#### Tests

```
python -m pytest tests/unit/test_offline_rule_sandbox_replay.py -q
# 19 PASSED
python -m pytest tests/unit -q
# 3346 PASSED, 0 failures (no regressions vs. prior baseline)
```

#### Successor allowed by this phase

A successful sandbox run (`recommendation_level=
PROMISING_FOR_PAPER_SHADOW`) only unlocks **Paper Shadow Strategy
Validation preparation**. It does NOT unlock Phase 12, does NOT
authorise live trading, does NOT authorise auto-tuning, does NOT
authorise rule application, does NOT authorise runtime config write.
The Risk Engine remains the single trade-decision gate.
