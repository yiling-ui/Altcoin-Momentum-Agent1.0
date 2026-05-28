# Phase AI-CHECKPOINT — AI Integrated Checkpoint v0

**Phase name:** Phase AI-CHECKPOINT.
**Slice:** AI Integrated Checkpoint v0 (*AI 综合检查点 v0*).
**Status:** **IN_REVIEW** after this implementation PR. **NOT
ACCEPTED.** **NOT** live trading. **NOT** trade authority.
**NOT** auto-tuning. **NOT** the DeepSeek hot path. **NOT** real
Telegram outbound. **NOT** Phase 12. **Phase 12 remains
FORBIDDEN.**

This document is the design / acceptance brief for the AI
Integrated Checkpoint v0. It is intentionally narrow: the only
artefact this phase produces is a single descriptive **AI
integrated checkpoint report** that proves the AI-1 → AI-6 chain
runs end-to-end on the operator's local report directory. The
report grants no trade authority and authorises no runtime knob
change. The Risk Engine remains the single trade-decision gate.

## Purpose

Verify that the six already-merged AI-Layer slices

  * **AI-1** AI Evidence Bundle Builder
    (PR #82, `app/ai/evidence_bundle.py`)
  * **AI-2** AI Claim Citation Contract
    (PR #83, `app/ai/claim_contract.py`)
  * **AI-3** Reality Check Layer
    (PR #84, `app/ai/reality_check.py`)
  * **AI-4** DeepSeek Offline Sandbox / Fake Provider
    (PR #85, `app/ai/deepseek_sandbox.py`)
  * **AI-5** Operator Briefing / Evidence Compression
    (PR #86, `app/ai/operator_briefing.py`,
    `app/ai/evidence_compression.py`)
  * **AI-6** AI Replay / Reflection Integration
    (PR #87, `app/replay/ai_replay.py`,
    `app/reflection/ai_reflection.py`)

can be exercised back-to-back over the operator-supplied report
artefacts without

  * placing an order or closing a position;
  * reading a private exchange API or signing a request;
  * calling a live LLM, a live DeepSeek transport, or a live
    Telegram outbound transport;
  * altering runtime configuration (`symbol_limit` /
    candidate-pool capacity / anomaly thresholds / Regime
    weights / strategy parameters);
  * automatically tuning any parameter on the basis of any
    field the report emits;
  * feeding AI output back into Risk / Execution / Strategy /
    Config;
  * treating AI output as truth, training label, tail label
    or strategy-validation sample;
  * recommending a direction (long / short / entry / exit /
    stop / target / position size / leverage);
  * opening Phase 12.

The chain that must be verified is:

```
AI Evidence Bundle (AI-1)
  -> AI Claim Citation Contract (AI-2)
  -> Reality Check Layer (AI-3)
  -> DeepSeek Offline Sandbox / Fake Provider (AI-4)
  -> Operator Briefing / Evidence Compression (AI-5)
  -> AI Replay (AI-6)
  -> AI Reflection (AI-6)
  -> AI Integrated Checkpoint Report
```

A successful AI integrated checkpoint only authorises the next
allowed paper-only step (the *Offline Rule Sandbox Replay v0*
preparation work). It does **NOT** authorise live trading. It
does **NOT** authorise auto-tuning. It does **NOT** authorise
the DeepSeek hot path. It does **NOT** authorise Telegram live
outbound. It does **NOT** open Phase 12.

## Inputs

The runner accepts (all optional; the runner is tolerant of
missing / partial inputs):

| Flag | Default |
|---|---|
| `--block-c-report` | `data/reports/block_c_integrated_checkpoint/block_c_integrated_checkpoint_report.json` |
| `--evidence-bundle` | `data/reports/ai/evidence_bundle/ai_evidence_bundle.json` |
| `--sandbox-output` | `data/reports/ai/deepseek_sandbox/deepseek_sandbox_output.json` |
| `--operator-briefing-dir` | `data/reports/ai/operator_briefing` (looks for `operator_briefing.json` and `evidence_compression_report.json`) |
| `--output-dir` | `data/reports/ai/integrated_checkpoint` |
| `--reference-window` | `60d` (descriptive only) |
| `--use-fake-provider` | `true` (descriptive only — the runner NEVER opens the network regardless of the value) |

If a key input is absent on disk the runner falls back to a
deterministic minimal fixture derived from the local Phase AI-1
forbidden-fields contract; the resulting payload is marked
`source=fallback_fixture` and **never carries fabricated market
conclusions**.

## Outputs

  - `<output-dir>/ai_integrated_checkpoint_report.json`
  - `<output-dir>/ai_integrated_checkpoint_report.md`

### Top-level fields (JSON)

  - `schema_version` — `phase_ai_checkpoint.ai_integrated_checkpoint.v1`
  - `source_phase` — `phase_ai_checkpoint_ai_integrated_checkpoint_v0`
  - `source_module` — `scripts.run_ai_integrated_checkpoint`
  - `generated_at_utc`, `reference_window`
  - `status` (rolled-up; one of `INSUFFICIENT_EVIDENCE`,
    `PARTIAL_EVIDENCE`, `EVIDENCE_GENERATED`)
  - `next_allowed_phase`
  - **Per-stage statuses** (each one of `PRESENT` /
    `FALLBACK_FIXTURE` / `MISSING`, except the AI-6 axes which
    use `EVIDENCE_GENERATED` / `PARTIAL_EVIDENCE` /
    `INSUFFICIENT_EVIDENCE`):
    - `evidence_bundle_status`
    - `citation_contract_status`
    - `reality_check_status`
    - `deepseek_sandbox_status`
    - `operator_briefing_status`
    - `evidence_compression_status`
    - `ai_replay_status`
    - `ai_reflection_status`
  - **Counters**:
    - `bundle_count` (0 or 1)
    - `ai_claim_count`, `supported_claim_count`,
      `degraded_claim_count`, `rejected_claim_count`,
      `reality_check_failed_count`,
      `unsupported_claim_count`,
      `forbidden_field_stripped_count`
    - `replay_case_count`, `reflection_case_count`
  - **Hard-pinned safety invariants** (re-pinned at every
    serialisation boundary):
    - `ai_output_can_be_truth=false`
    - `ai_output_can_be_training_label=false`
    - `ai_output_can_be_tail_label=false`
    - `ai_output_can_be_strategy_sample=false`
    - `ai_output_is_commentary_only=true`
    - `trade_authority=false`
    - `auto_tuning_allowed=false`
    - `phase_12_forbidden=true`
    - `stateless_inference=true`
    - `feedback_isolation=true`
  - `known_blockers`, `known_gaps`
  - `inputs` (the operator-supplied paths plus the per-stage
    `*_source` labels — `PRESENT` / `FALLBACK_FIXTURE` /
    `MISSING`)
  - `replay_summary`, `reflection_summary` (small headline
    summaries; the full per-case lists live in the AI-6
    outputs themselves)
  - `safety_flags` (the project-wide invariants)
  - `forbidden_fields` (the canonical AI-1 forbidden-field
    reference list, exposed so a downstream consumer can
    audit the schema without parsing the source)

The recursive forbidden-fields guard
(`_assert_no_forbidden_keys`) refuses to emit a payload that
carries a trade-action / runtime-config-patch / "live ready" /
"trading approved" / "phase_12_allowed" key at any nesting
depth.

## Status taxonomy

  * **`INSUFFICIENT_EVIDENCE`** — none of the AI-1 / AI-4 /
    AI-5 artefacts are on disk AND no Block C report is on disk;
    `next_allowed_phase = NEEDS_AI_OPERATOR_EVIDENCE`.
  * **`PARTIAL_EVIDENCE`** — the AI-1 → AI-6 chain runs end-to-
    end but at least one stage uses
    `source=fallback_fixture`, OR the AI-4 sandbox output
    carries degraded / rejected / reality-check-failed claims,
    OR the AI-6 replay / reflection axes did not produce a
    case; `next_allowed_phase = Offline Rule Sandbox Replay
    preparation / AI operator evidence run (paper /
    read-only)`.
  * **`EVIDENCE_GENERATED`** — the AI-1 → AI-6 chain runs end-
    to-end with operator-supplied artefacts, no fallback
    fixture is in the chain, the AI-4 sandbox claims are
    `SUPPORTED_INTELLIGENCE` / `reality_check_status=SUPPORTED`,
    and AI-6 produced ≥1 replay case AND ≥1 reflection case;
    `next_allowed_phase = Offline Rule Sandbox Replay v0
    preparation (paper / read-only)`.

The status taxonomy is intentionally **not** `ACCEPTED`. The
checkpoint never grants live-trading approval, never grants
auto-tuning approval, never authorises the DeepSeek hot path,
never authorises Telegram live outbound, and never opens Phase
12. The `next_allowed_phase` strings never reference Phase 12,
"live ready", "trading approved", "live trading allowed", or any
equivalent wording.

## AI-1 → AI-6 chain

The runner stitches the six already-merged slices together
**without changing any of them**. Per-stage role:

  - **AI-1** (evidence bundle) — frozen, evidence-cited,
    deterministic JSON view of the Truth Layer. The runner
    reads the bundle as commentary substrate; it never builds
    a fresh bundle from runtime state.
  - **AI-2** (citation contract) — every claim emitted by the
    AI-4 sandbox carries a `citation_authority_level`. The
    runner counts `SUPPORTED_INTELLIGENCE`,
    `DEGRADED_NO_EVIDENCE`, `UNSUPPORTED_INTELLIGENCE`,
    `REJECTED_BY_SCHEMA`, `REJECTED_INVALID_EVIDENCE` to
    populate the headline counters.
  - **AI-3** (reality check) — every claim also carries a
    `reality_check_status` (`SUPPORTED`, `PARTIAL`,
    `CONTRADICTED`, `INSUFFICIENT`, `REJECTED`). The runner
    folds `CONTRADICTED` / `INSUFFICIENT` / `REJECTED` into
    `reality_check_failed_count`.
  - **AI-4** (DeepSeek offline sandbox) — the runner reads the
    serialised `AIIntelligenceOutput` JSON. **It NEVER calls
    the real DeepSeek transport.** The `--use-fake-provider`
    flag is descriptive only.
  - **AI-5** (operator briefing + evidence compression) — the
    runner reads `operator_briefing.json` and
    `evidence_compression_report.json` as paper / read-only
    inputs.
  - **AI-6** (replay + reflection) — the runner calls the
    pure / offline `replay_and_reflect_artefacts()`
    convenience wrapper over the AI-1 + AI-4 + AI-5 + AI-5
    artefacts to produce one `AIReplaySummary` and one
    `AIReflectionSummary`. The wrapper never opens the
    network and never emits any of the `FORBIDDEN_REFLECTION_TAGS`.

If any stage's input is missing on disk the runner substitutes
a deterministic minimal fallback fixture (marked
`source=fallback_fixture`) so the AI-6 layer can still be
exercised; the operator can then re-run the upstream slices and
re-issue the checkpoint with `source=PRESENT` everywhere.

## Safety boundary (held end-to-end)

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
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - no real DeepSeek HTTP transport
  - **Phase 12 = FORBIDDEN**

### Forbidden modifications (held end-to-end)

  - no edit under `app/risk/**`
  - no edit under `app/execution/**`
  - no edit under `app/exchanges/**`
  - no edit under `app/telegram/**`
  - no edit under `app/config/**`
  - no edit under `app/ai/evidence_bundle.py`,
    `app/ai/claim_contract.py`,
    `app/ai/reality_check.py`,
    `app/ai/deepseek_sandbox.py`,
    `app/ai/operator_briefing.py`,
    `app/ai/evidence_compression.py`
  - no edit under `app/replay/ai_replay.py` or
    `app/reflection/ai_reflection.py`
  - no change to `symbol_limit`
  - no change to anomaly thresholds
  - no change to `candidate_pool`
  - no change to regime weights
  - no `runtime_config_patch` produced
  - no buy / sell / long / short / position_size /
    leverage / stop / target / risk_budget produced
  - no Telegram outbound message produced
  - no real DeepSeek HTTP request produced

### What this checkpoint does NOT authorise

  - **NOT** live trading.
  - **NOT** trade authority.
  - **NOT** auto-tuning.
  - **NOT** the DeepSeek hot path. The DeepSeek transport in
    `app/ai/deepseek_sandbox.py` remains a refusal-only
    skeleton; the runner only reads the serialised offline
    sandbox output produced by the existing
    `scripts/run_deepseek_offline_sandbox.py`.
  - **NOT** Telegram live outbound. The runner never imports
    `app.telegram` and never calls a Telegram transport.
  - **NOT** any live LLM call. The runner does not import
    `openai`, `anthropic`, `deepseek`, `httpx`, `requests`,
    `aiohttp`, `urllib3`, `websocket`, `websockets`, `grpc`,
    `boto3`, or `socket`. A unit test additionally
    monkeypatches `socket.socket` to refuse-on-call and runs
    the full `EVIDENCE_GENERATED` path to prove no socket
    is opened.
  - **NOT** Phase 12. **Phase 12 remains FORBIDDEN.**

### AI output is commentary, not truth

The integrated checkpoint re-pins every AI-output authority pin
at the serialisation boundary:

  - `ai_output_can_be_truth = False`
  - `ai_output_can_be_training_label = False`
  - `ai_output_can_be_tail_label = False`
  - `ai_output_can_be_strategy_sample = False`
  - `ai_output_is_commentary_only = True`

A unit test parametrises across all four flags and asserts the
re-pinned value at every status tier (`INSUFFICIENT_EVIDENCE`,
`PARTIAL_EVIDENCE`, `EVIDENCE_GENERATED`) on the in-memory
payload AND on the on-disk JSON.

### Successor allowed

A successful AI integrated checkpoint only authorises the next
allowed paper-only step:

  - **`Offline Rule Sandbox Replay v0` preparation (paper /
    read-only)** when `status=EVIDENCE_GENERATED`.
  - **`Offline Rule Sandbox Replay preparation / AI operator
    evidence run` (paper / read-only)** when
    `status=PARTIAL_EVIDENCE`.
  - **`NEEDS_AI_OPERATOR_EVIDENCE`** when
    `status=INSUFFICIENT_EVIDENCE`.

No other phase is unlocked. Phase 12 remains **FORBIDDEN**.

## Files shipped

  - `scripts/run_ai_integrated_checkpoint.py` — the runner.
    Argparse CLI with `--block-c-report` /
    `--evidence-bundle` / `--sandbox-output` /
    `--operator-briefing-dir` / `--output-dir` /
    `--reference-window` / `--use-fake-provider`. Reads
    only local files; writes only files under
    `--output-dir`. Imports only `app.ai.evidence_bundle`
    (for the canonical forbidden-field list) and
    `app.reflection.ai_reflection` (for the AI-6
    convenience wrapper); does NOT import `app.risk`,
    `app.execution`, `app.exchanges`, `app.telegram`, or
    `app.config`.
  - `tests/unit/test_ai_integrated_checkpoint.py` — 22
    PASSING unit tests covering all 15 brief-mandated
    scenarios plus the output paths, the CLI exit codes
    (`INSUFFICIENT_EVIDENCE` → 1, `EVIDENCE_GENERATED` →
    0), the degraded-claim path, and a
    `socket.socket`-monkeypatched run that proves the
    runner opens no network socket.
  - `docs/PHASE_AI_INTEGRATED_CHECKPOINT.md` — this
    document.

## Tests

```
python -m pytest tests/unit/test_ai_integrated_checkpoint.py -q
```

ships 22 PASSING tests. The full unit suite continues to pass.

## Acceptance signal

Acceptance of this phase is **report-only**. The phase is
marked **IN_REVIEW** here. Maintainer-led review of the
implementation PR is the only path to **ACCEPTED**. A
maintainer's `ACCEPTED` decision authorises only the next
allowed paper-only step (the *Offline Rule Sandbox Replay v0*
preparation work). It does NOT authorise live trading. It does
NOT authorise auto-tuning. It does NOT authorise the DeepSeek
hot path. It does NOT authorise Telegram live outbound. It
does NOT open Phase 12. **Phase 12 remains FORBIDDEN.**
