# Phase 11C.1C-C-B-B-B-E-D — Block C Integrated Checkpoint v0

> **Phase ledger status: `IN_REVIEW` (after this implementation PR;
> `ACCEPTED` requires maintainer review of the PR plus the eventual
> Block C closeout).**
>
> Block: Block C wrap-up checkpoint.
> Predecessors: Block A complete; Block B complete and Block B
> Integrated Evidence Checkpoint = `PARTIAL_EVIDENCE` (advance
> allowed); Block C1 (Replay Extension for 11C Adaptive Events v0)
> merged; Block C2 (Reflection Extension for 11C Adaptive Events v0)
> merged; Block C3 (Evidence Contract Baseline v0) merged.
> Successor allowed by this phase: **Phase AI-0 / AI Evidence Bundle
> preparation only (paper / read-only).** Phase 12 remains
> **FORBIDDEN**.

## Purpose

Block C ships three independent paper / report / evidence-only
slices:

  * **C1** *Replay Extension for 11C Adaptive Events v0*
    (`app/replay/adaptive_replay_11c.py`).
  * **C2** *Reflection Extension for 11C Adaptive Events v0*
    (`app/reflection/adaptive_11c.py`).
  * **C3** *Evidence Contract Baseline v0*
    (`app/evidence/evidence_contract.py`).

Up to and including C3 the project still lacked a single
descriptive aggregated report that an operator can read at-a-glance
to answer:

> **"Are Replay + Reflection + Evidence Contract chained together
> end-to-end well enough to start the next-allowed phase (the AI
> read-only evidence-bundle prep, AKA Block D Phase AI-0), or do we
> need more operator evidence first?"**

This slice ships that aggregation as a paper / report /
evidence-only Block C Integrated Checkpoint v0. The checkpoint is
**not** Block C closeout (closeout is done per-block, after the
checkpoint is reviewed). The checkpoint is also **not** an AI /
DeepSeek integration; it does not call any LLM.

## Inputs

The runner is a thin file-based aggregator — it does not connect to
the network, it does not read `events.db`, it does not read
secrets or environment variables. It accepts (all optional; the
runner is tolerant of missing / partial inputs):

  * `--reports-dir`        — default `data/reports`
  * `--exports-dir`        — default `data/reports/exports`
  * `--block-b-dir`        — default
    `data/reports/block_b_integrated_evidence`
  * `--output-dir`         — default
    `data/reports/block_c_integrated_checkpoint`
  * `--reference-window`   — default `60d` (descriptive label only)

The runner walks every `events.jsonl` / `*.jsonl` file under
`--reports-dir` and `--exports-dir` and converts the rows whose
`event_type` is one of the C1 / C2 supported adaptive event types
into in-memory `app.core.events.Event` objects. It then loads the
most recent
`<--block-b-dir>/**/block_b_integrated_evidence_report.json`. No
other input is consulted.

## Outputs

The runner writes exactly two files under `--output-dir`:

  * `block_c_integrated_checkpoint_report.json`
  * `block_c_integrated_checkpoint_report.md`

Both files are deterministic across runs over identical input
(modulo the `generated_at_utc` stamp).

### JSON payload fields

Top-level keys (descriptive only — no key authorises a real
trade and no key is a runtime-tuning patch):

  * `schema_version`
  * `source_phase`
  * `source_module`
  * `reference_window`
  * `generated_at_utc`
  * `status`                          — one of `INSUFFICIENT_EVIDENCE`
                                        / `PARTIAL_EVIDENCE` /
                                        `EVIDENCE_GENERATED`
  * `next_allowed_phase`              — see "Status taxonomy" below
  * `phase_12_forbidden`              — hard-pinned `true`
  * `auto_tuning_allowed`             — hard-pinned `false`
  * `replay_status`                   — per-component status (closed)
  * `reflection_status`               — per-component status (closed)
  * `evidence_contract_status`        — per-component status (closed)
  * `replay_case_count`
  * `reflection_case_count`
  * `evidence_claim_count`
  * `accepted_claim_count`
  * `degraded_claim_count`
  * `rejected_claim_count`
  * `partial_claim_count`
  * `missing_evidence_count`
  * `invalid_evidence_count`
  * `supported_event_groups`          — replay groups with ≥1 event
  * `unsupported_event_groups`        — replay groups with 0 events
  * `known_gaps`                      — descriptive non-blocking gaps
  * `known_blockers`                  — descriptive blockers
  * `replay_summary`                  — per-builder / per-group counts
  * `reflection_summary`              — C2 summary counts
  * `evidence_contract_overall_status`
  * `evidence_contract_warnings`
  * `block_b_report_path`             — absolute path of the most
                                        recent loaded Block B
                                        report (or `null`)
  * `block_b_status`                  — Block B status as loaded
  * `schema_versions`                 — dict of upstream schema
                                        versions
  * `source_phases`                   — dict of upstream source
                                        phases

The set `_FORBIDDEN_BLOCK_C_PAYLOAD_KEYS` contains every direction
/ sizing / risk-budget / runtime-config key plus the defensive
aliases `trading_approved`, `live_ready`, `live_trading_allowed`,
and is asserted recursively at the serialisation boundary so a
future regression cannot smuggle a forbidden key into the report.

## Status taxonomy

> The status taxonomy is intentionally **not** `ACCEPTED`. The
> checkpoint never grants live-trading approval and never grants
> auto-tuning approval.

Per-component statuses (closed enum):

  * `EVIDENCE_GENERATED`              — component produced output
                                        and no blocker remains.
  * `PARTIAL_EVIDENCE`                — component produced partial
                                        output (e.g. events but no
                                        replay records, or accepted
                                        + degraded claims).
  * `INSUFFICIENT_EVIDENCE`           — component had no usable
                                        input.

Block-C-level rollup:

  * `INSUFFICIENT_EVIDENCE`           — no adaptive events were
                                        loaded **and** no Block B
                                        report was loaded;
                                        `next_allowed_phase =
                                        NEEDS_OPERATOR_EVIDENCE`.
  * `PARTIAL_EVIDENCE`                — at least one of Replay /
                                        Reflection / Evidence
                                        Contract is partial, **or**
                                        a `known_blockers` entry is
                                        present (e.g. Block B
                                        report missing); the next
                                        allowed phase is **only**
                                        the AI Evidence Bundle
                                        preparation (paper /
                                        read-only).
  * `EVIDENCE_GENERATED`              — Replay, Reflection and the
                                        Evidence Contract all
                                        produce valid output and
                                        no blocker remains; the
                                        next allowed phase is
                                        the AI Evidence Bundle
                                        Builder preparation
                                        (paper / read-only).

`next_allowed_phase` is one of the two strings
`Phase AI-0 / AI Evidence Bundle preparation (paper / read-only)`
or `NEEDS_OPERATOR_EVIDENCE`. Neither string contains the words
"Phase 12", "live", "trading-approved", or "trading_approved".

## Acceptance criteria

This phase is `IN_REVIEW` once the implementation PR ships:

  * `scripts/run_block_c_integrated_checkpoint.py`
    (the new runner, paper / report / evidence only).
  * `tests/unit/test_block_c_integrated_checkpoint.py`
    (15 tests — covers the brief's 10 numbered checks plus
    output-path / CLI exit-code / event-group surfacing).
  * `docs/PHASE_11C_1C_C_B_B_B_E_D_BLOCK_C_INTEGRATED_CHECKPOINT.md`
    (this document).
  * `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` updates.

Test command:
`python -m pytest tests/unit/test_block_c_integrated_checkpoint.py -q`
ships **15 PASSING** tests; the full unit suite ships **2726
PASSING** tests, 0 failures (was 2711 before this phase).

The brief's ten numbered acceptance checks map to
`tests/unit/test_block_c_integrated_checkpoint.py` as follows:

| # | Acceptance check                                          | Test |
|---|-----------------------------------------------------------|------|
| 1 | no input → `INSUFFICIENT_EVIDENCE`                        | `test_no_input_yields_insufficient_evidence` |
| 2 | partial replay/reflection/evidence → `PARTIAL_EVIDENCE`   | `test_partial_replay_reflection_evidence_yields_partial` |
| 3 | valid replay/reflection/evidence → `EVIDENCE_GENERATED`   | `test_valid_replay_reflection_evidence_yields_evidence_generated` |
| 4 | `next_allowed_phase` is correct                           | `test_next_allowed_phase_mapping` |
| 5 | `phase_12_forbidden=true`                                 | `test_phase_12_forbidden_true_on_every_payload` |
| 6 | `auto_tuning_allowed=false`                               | `test_auto_tuning_allowed_false_on_every_payload` |
| 7 | forbidden fields absent                                   | `test_no_forbidden_keys_in_emitted_payload` |
| 8 | runner does not import `app.risk` / `app.execution` / `app.exchanges` / `app.llm` / `app.telegram` | `test_runner_module_does_not_import_banned_modules` (+ textual variant) |
| 9 | evidence-contract degraded-claim count is correct         | `test_evidence_contract_degraded_claim_count_reported_correctly` |
| 10| deterministic output                                      | `test_output_is_deterministic_modulo_generated_at_utc` |

## Safety boundary (held end-to-end)

  * `mode = paper`
  * `live_trading = False`
  * `exchange_live_orders = False`
  * `right_tail = False`
  * `llm = False`
  * `telegram_outbound_enabled = False`
  * `binance_private_api_enabled = False`
  * no Binance API key / secret
  * no signed endpoint
  * no private websocket
  * no `listenKey`
  * no real Telegram outbound
  * no DeepSeek trade decision
  * **Phase 12 = FORBIDDEN**

### This does NOT authorise live trading

The Block C Integrated Checkpoint is a descriptive aggregator. It
emits structured statuses, counts, and a `next_allowed_phase`
label drawn from a closed two-element vocabulary. It NEVER emits
`buy` / `sell` / `long` / `short` / `direction` / `side` /
`entry` / `exit` / `position_size` / `leverage` / `stop` /
`stop_loss` / `target` / `take_profit` / `risk_budget` /
`order` / `execution_command`. The Risk Engine remains the
single trade-decision gate.

### This does NOT authorise auto-tuning

`auto_tuning_allowed = false` is hard-pinned on every emitted
payload (the runner asserts the field's value at the
serialisation boundary). The checkpoint NEVER emits
`runtime_config_patch` / `symbol_limit_patch` /
`threshold_patch` / `candidate_pool_patch` /
`regime_weight_patch`. No file under `app/config/`,
`app/risk/`, `app/execution/`, `app/exchanges/`, `app/llm/`,
or `app/telegram/` is touched by this phase.

### This does NOT use AI / DeepSeek

The checkpoint is rule-based and deterministic. It does NOT call
DeepSeek, does NOT call any LLM, does NOT consume chat history,
and does NOT produce any natural-language reasoning. Every status
/ tag / phase label is drawn from a closed enum or a fixed string
constant inside the runner module.

### Successor allowed by a successful Block C checkpoint

A successful Block C checkpoint (`status=EVIDENCE_GENERATED`)
allows ONLY the AI **read-only** evidence-bundle preparation —
i.e. the next-allowed phase is the Block D *Phase AI-0 / AI
Evidence Bundle preparation* engineering pre-work. It does **NOT**
authorise the DeepSeek hot path. It does **NOT** authorise Phase
12. It does **NOT** authorise live trading. It does **NOT**
authorise auto-tuning. A `PARTIAL_EVIDENCE` checkpoint authorises
the same AI Evidence Bundle preparation pre-work; an
`INSUFFICIENT_EVIDENCE` checkpoint authorises only operator
follow-up (`NEEDS_OPERATOR_EVIDENCE`).

## Forbidden modifications (held end-to-end)

  * no edit under `app/risk/**`
  * no edit under `app/execution/**`
  * no edit under `app/exchanges/**`
  * no edit under `app/llm/**`
  * no edit under `app/telegram/**`
  * no edit under `app/config/**`
  * no change to `symbol_limit`
  * no change to anomaly thresholds
  * no change to `candidate_pool`
  * no change to regime weights
  * no `runtime_config_patch` produced
  * no buy / sell / long / short / position_size / leverage /
    stop / target / risk_budget produced
  * no AI Evidence Bundle is built by this phase (that is the
    *next-allowed* phase, not part of this PR)
  * no Paper Shadow / Rule Sandbox is built by this phase
  * no DeepSeek integration; no LLM call

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR plus the Block C closeout PR are the only
paths to **ACCEPTED**.
