# Phase 11C.1C-C-B-B-B-D-E — Block B Integrated Evidence Checkpoint v0 (*Block B 综合证据检查点 v0*)

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**
>
> **Type:** paper / report / evidence-only Block B aggregation
> checkpoint.
> **Runtime effect on real trading:** **none.**
> **Trade authority granted:** **none.**
> **Auto-tuning authority granted:** **none.**
> **Phase 12:** **FORBIDDEN.**

## 1. Purpose

Block B (the D-A → D-B → B1.1 → B2-A → B2-B → B3 sequence) has
shipped six paper / report / evidence-only slices:

  - **D-A**   `Phase 11C.1C-C-B-B-B-D-A` Historical 60D Mover
    Coverage Backfill Audit v0
    (`ACCEPTED / PARTIAL_QUALITY / TOOLCHAIN_CLOSEOUT_ONLY`).
  - **D-B**   `Phase 11C.1C-C-B-B-B-D-B` Post-Discovery Outcome
    Metrics v0
    (`ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT`).
  - **B1.1**  `Phase 11C.1C-C-B-B-B-D-B.1` Historical Price Path /
    Kline Path Adapter v0
    (`ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`).
  - **B2-A**  `Phase 11C.1C-C-B-B-B-D-C-A` Reject-to-Outcome
    Attribution v0 (`IN_REVIEW`).
  - **B2-B**  `Phase 11C.1C-C-B-B-B-D-C-B` Severe Missed Tail
    Triage v0 (`IN_REVIEW`).
  - **B3**    `Phase 11C.1C-C-B-B-B-D-D` Discovery Quality
    Scorecard v0 (`IN_REVIEW`).

The project still lacked a **single descriptive aggregated
report** that an operator can read at-a-glance to answer:

> "Is Block B *as a whole* in a state where it is sane to open
> the Block C **Replay / Reflection extension for 11C Adaptive
> Events**, or do we need more operator evidence first?"

This slice ships that aggregation as a paper / report /
evidence-only **Block B Integrated Evidence Checkpoint v0**.

It is intentionally **not a strategy profitability proof**, **not
a live-trading approval**, **not an auto-tuning approval**, and
**not a per-phase ACCEPTED gate**. It rolls up the existing
on-disk evidence under `data/reports/` into one descriptive JSON
report and one descriptive Markdown summary so the next phase
gate (Block C Replay / Reflection extension) can reference a
single artefact.

## 2. Inputs

The runner is a **read-only** consumer of artefacts already on
disk. It connects to no network, calls no LLM / DeepSeek, and
opens no Telegram socket.

  - `--reports-dir`              `data/reports`
  - `--exports-dir`              `data/reports/exports`
  - `--post-discovery-dir`       `data/reports/post_discovery_outcome`
  - `--output-dir`               `data/reports/block_b_integrated_evidence`
  - `--reference-window`         `60d` (descriptive only)

The runner walks each input directory recursively for
`events.jsonl` / `*.jsonl` files and counts Block B event types:

  - `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`
  - `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`
  - `MOVER_CAPTURE_RECALL_AUDIT_GENERATED`
  - `MOVER_CAPTURE_PATH_AUDITED`
  - `POST_DISCOVERY_OUTCOME_EVALUATED`
  - `POST_DISCOVERY_OUTCOME_REPORT_GENERATED`
  - `REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED`
  - `REJECT_TO_OUTCOME_CASE_ATTRIBUTED`
  - `FALSE_NEGATIVE_REJECT_DETECTED`
  - `CORRECT_PROTECTIVE_REJECT_CONFIRMED`
  - `SEVERE_MISSED_TAIL_TRIAGE_GENERATED`
  - `SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED`
  - `SEVERE_MISS_ESCALATION_REQUIRED`
  - `DISCOVERY_QUALITY_SCORECARD_GENERATED`
  - `DISCOVERY_QUALITY_BUCKET_EVALUATED`

The runner also:

  - reads the most recent
    `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED` payload it
    finds across every input directory (D-A coverage report);
  - reads the most recent
    `post_discovery_outcome_report.json` it finds under
    `--post-discovery-dir` (D-B + B1.1 report).

If neither input is reachable the runner emits an
`INSUFFICIENT_EVIDENCE` checkpoint and refuses to fabricate
any field.

## 3. Outputs

  - `<output-dir>/block_b_integrated_evidence_report.json`
  - `<output-dir>/block_b_integrated_evidence_report.md`

The JSON report carries (descriptive only):

  - `schema_version`, `source_phase`, `source_module`
  - `reference_window`
  - `generated_at_utc`
  - `status` ∈ {`INSUFFICIENT_EVIDENCE`, `PARTIAL_EVIDENCE`,
    `EVIDENCE_GENERATED`}
  - `next_allowed_phase`
  - `phase_12_forbidden = true`            *(hard-pinned)*
  - `auto_tuning_allowed = false`          *(hard-pinned)*
  - per-component statuses: `d_a_status`, `d_b_status`,
    `b1_1_price_path_status`,
    `reject_attribution_status`,
    `severe_miss_triage_status`,
    `discovery_quality_scorecard_status`
  - counters: `evaluated_count`,
    `coverage_record_count`,
    `post_discovery_record_count`,
    `price_path_records_loaded`,
    `price_path_records_missing`,
    `severe_miss_count`,
    `false_negative_reject_count`,
    `correct_protective_reject_count`,
    `data_gap_count`,
    `discovery_quality_bucket`
  - per-component diagnostic blocks: `d_a_diagnostics`,
    `d_b_diagnostics`, `b1_1_diagnostics`,
    `discovery_quality_scorecard`, `derived_counts`
  - `notable_symbols` (operator watchlist: `RAVEUSDT`,
    `STOUSDT`)
  - `block_b_event_counts`
  - `evidence_refs`
  - `known_blockers`
  - `known_non_blocking_gaps`
  - source-pointer fields:
    `post_discovery_report_path`

No payload field carries any direction, sizing, stop, target,
risk-budget, order, execution-command, or runtime-config-patch
key. The recursive
:func:`assert_payload_has_no_forbidden_keys` guard refuses to
emit such a payload at build time.

## 4. Status taxonomy

The integrated checkpoint uses a closed three-label set
(intentionally **not** `ACCEPTED`):

  - `INSUFFICIENT_EVIDENCE` — every component is
    `INSUFFICIENT_EVIDENCE`; no D-A coverage payload, no D-B
    post-discovery report, and no Block B events on disk.
  - `PARTIAL_EVIDENCE` — at least one component has produced
    evidence, but D-B post-discovery is missing OR the data-gap
    counter is high (≥ `DEFAULT_DATA_GAP_PARTIAL_RATE` of
    coverage records or ≥ `DEFAULT_DATA_GAP_HIGH_ABSOLUTE`
    absolute) OR the discovery-quality bucket cannot be
    computed.
  - `EVIDENCE_GENERATED` — D-A coverage report present, D-B
    post-discovery report present and `EVIDENCE_GENERATED`,
    data-gap rate below the partial threshold, and a
    discovery-quality bucket is computable.

`ACCEPTED` is intentionally NOT used here. The per-phase
closeout PRs (D-A, D-B, B1.1) carry their own
`ACCEPTED_TOOLCHAIN` / `PARTIAL_QUALITY` /
`BLOCK_B_CHECKPOINT_ONLY` labels — the integrated checkpoint
defers to those labels and never overrides them.

## 5. `next_allowed_phase` mapping

  - `EVIDENCE_GENERATED` → `Phase 11C.1C-C-B-B-B-E-A Replay
    Extension for 11C Adaptive Events v0`.
  - `PARTIAL_EVIDENCE` → `Phase 11C.1C-C-B-B-B-E-A Replay
    Extension for 11C Adaptive Events v0` (paper / evidence
    only; partial coverage is recorded as a non-blocking gap).
  - `INSUFFICIENT_EVIDENCE` → `NEEDS_OPERATOR_EVIDENCE`.

The runner **never** emits `Phase 12` as a next-allowed phase.
The Block C Replay / Reflection extension is itself a paper /
report / evidence-only phase, so the next-allowed-phase mapping
preserves the safety boundary end-to-end.

## 6. Acceptance criteria

  1. Module imports cleanly under Python 3.11+.
  2. Runs end-to-end with **no Block B inputs on disk** and
     emits `status = INSUFFICIENT_EVIDENCE` with
     `next_allowed_phase = NEEDS_OPERATOR_EVIDENCE`.
  3. Runs end-to-end with **only a D-A export on disk** (no D-B
     report) and emits `status = PARTIAL_EVIDENCE` with
     `next_allowed_phase = Phase 11C.1C-C-B-B-B-E-A Replay
     Extension for 11C Adaptive Events v0`.
  4. Runs end-to-end with **D-A coverage payload + D-B
     post-discovery report + B2-A / B2-B / B3 events** present
     and emits `status = EVIDENCE_GENERATED` with the same
     `next_allowed_phase`.
  5. Every emitted JSON payload carries
     `phase_12_forbidden = true` and
     `auto_tuning_allowed = false`. Both flags are hard-pinned
     and cannot be relaxed without changing the runner source.
  6. No emitted payload contains any forbidden trade-authority
     / runtime-tuning key (recursive guard via
     :func:`assert_payload_has_no_forbidden_keys`).
  7. The runner module does NOT import
     `app.risk` / `app.execution` / `app.exchanges` /
     `app.llm` / `app.telegram` (AST-checked).
  8. The runner module does NOT modify `app.config`.
  9. The runner connects to no network and signs no request.

The :file:`tests/unit/test_block_b_integrated_evidence_checkpoint.py`
unit-test module enforces criteria 2 — 9.

## 7. Safety boundary (held end-to-end)

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

## 8. This does NOT authorise live trading

The integrated checkpoint answers *coverage / capture / outcome
/ attribution / triage / discovery-quality* questions at the
**evidence aggregation level**. It does **not** answer:

  - Was the strategy profitable on this window? (No — the
    checkpoint never simulates PnL, never reproduces a Risk
    Engine decision, never runs an Execution FSM.)
  - Should we open a position? (No — direction / sizing /
    stop / target are NEVER fields of the checkpoint payload.)
  - Should we increase `symbol_limit` or relax the anomaly
    threshold? (No — runtime knobs are out of scope, and the
    recursive forbidden-keys guard refuses to emit a payload
    that contains a `*_patch` key.)

A checkpoint with `status = EVIDENCE_GENERATED` does **not**
mean live trading is approved. A checkpoint with
`status = INSUFFICIENT_EVIDENCE` does **not** mean live trading
is *disapproved* either; live-trading approval is a Phase 12
concern that requires the Spec §41 Go/No-Go checklist, and the
checklist has **not** been initiated.

## 9. This does NOT authorise auto-tuning

Every emitted checkpoint carries `auto_tuning_allowed = false`.
The constant is hard-pinned in the runner source and the
recursive forbidden-keys guard refuses to emit any payload that
carries a `*_patch` key.

A `data_gap_count` counter or a `false_negative_reject_count`
counter does **not** authorise the Risk Engine, the Execution
FSM, `symbol_limit`, the candidate pool, anomaly thresholds, or
Regime weights to be changed. Routing a case to the operator
review queue is a *human* decision, not an automated one.

## 10. This is a Block B checkpoint, not a strategy profitability proof

`EVIDENCE_GENERATED` describes **evidence aggregation health**:

  - the D-A coverage audit produced records;
  - the D-B post-discovery report loaded;
  - B1.1 produced a price-path coverage block;
  - B2-A / B2-B / B3 emitted at least one report event;
  - the discovery-quality bucket is computable.

It does **not** describe:

  - **Strategy quality** — whether a follow / pullback /
    observe / reject decision after first sighting was
    profitable. That is Phase 11C.1C-C-B-A's territory.
  - **Risk-decision quality** — whether the Risk Engine made
    the right reject / approve decision. That is Phase
    11C.1C-C-B-B-B-D-C-A's territory.
  - **Outcome quality** — whether the candidate ran or dumped
    after first sighting. That is Phase
    11C.1C-C-B-B-B-D-B's territory.
  - **Trade-approval quality** — whether live trading should
    be enabled. That is a Phase 12 decision and is
    **forbidden** on every Phase 11C sub-phase.

The checkpoint is a Block B aggregation; per-phase ACCEPTANCE
labels remain authoritative for their respective scopes.

## 11. A successful checkpoint authorises **only** the Block C Replay / Reflection extension

`status = EVIDENCE_GENERATED` (or `PARTIAL_EVIDENCE`) opens the
next-allowed phase:

> **Phase 11C.1C-C-B-B-B-E-A — Replay Extension for 11C Adaptive
> Events v0**

That phase is itself paper / report / evidence-only. It extends
the existing Replay engine to play back the Block B adaptive
events (D-A / D-B / B1.1 / B2-A / B2-B / B3) over previously
captured event streams. It does **not** open Phase 12, does
**not** open DeepSeek trade decisions, and does **not** open
auto-tuning.

`status = INSUFFICIENT_EVIDENCE` opens nothing automatically —
the operator must collect more Block B evidence before any
later phase is reachable.

## 12. What this PR does NOT ship

  - No change to `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/llm/`, `app/telegram/`,
    `app/config/`.
  - No change to `symbol_limit`, anomaly thresholds,
    candidate-pool capacity, Regime weights, or any other
    runtime knob.
  - No new private API surface, no signed endpoint, no
    `listenKey`, no real Telegram outbound, no DeepSeek trade
    decision.
  - No automatic parameter tuning. No "looking at the answer
    key" against the post-hoc D-A reference set.
  - No new strategy. No new trading module. No new direction
    classification. No new sizing rule.
  - No new `app/adaptive/` engine. The runner reuses the
    existing :func:`build_discovery_quality_scorecard` builder
    and the existing
    :func:`assert_payload_has_no_forbidden_keys` guard.
  - No real evidence closeout. No real-data run is performed
    by this PR; the implementation is evidence-ready but the
    closeout is a separate later PR.
  - No Replay / Reflection extension implementation (separate
    slice; the *next-allowed* phase, not part of this PR).
  - No DeepSeek integration (separate phase).
  - **No Phase 12.**

## 13. References

  - `docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md` — D-A.
  - `docs/PHASE_11C_1C_C_B_B_B_D_B_POST_DISCOVERY_OUTCOME_METRICS.md` — D-B.
  - `docs/PHASE_11C_1C_C_B_B_B_D_B_1_HISTORICAL_PRICE_PATH_KLINE_PATH_ADAPTER.md` — B1.1.
  - `docs/PHASE_11C_1C_C_B_B_B_D_C_A_REJECT_TO_OUTCOME_ATTRIBUTION.md` — B2-A.
  - `docs/PHASE_11C_1C_C_B_B_B_D_C_B_SEVERE_MISSED_TAIL_TRIAGE.md` — B2-B.
  - `docs/PHASE_11C_1C_C_B_B_B_D_D_DISCOVERY_QUALITY_SCORECARD.md` — B3.
  - `docs/PHASE_GATE.md` — phase-gate ledger.
  - `docs/PROJECT_STATUS.md` — at-a-glance status board.
  - `docs/CHANGELOG.md` — release notes.
  - Runner: `scripts/run_block_b_integrated_evidence_checkpoint.py`.
  - Tests: `tests/unit/test_block_b_integrated_evidence_checkpoint.py`.
