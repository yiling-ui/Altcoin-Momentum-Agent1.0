# Phase 11C.1C-C-B-B-B-D-B Post-Discovery Outcome Metrics v0 evidence closeout: ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT (docs-only)

## Summary

This is a **docs-only** PR. It records the Phase
11C.1C-C-B-B-B-D-B (*Post-Discovery Outcome Metrics v0 / 发现
后结果度量 v0*) evidence closeout based on the **real** D-A
export evidence rerun on `main` from the operator VPS, after
PR #69 fixed the D-B evidence runner input adapter gap.

The closeout level is **explicitly NOT full quality
accepted**. It is:

> **`Phase 11C.1C-C-B-B-B-D-B: ACCEPTED_TOOLCHAIN /
> PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT`**

## Required closeout statements (verbatim)

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

## Inputs

### D-A export input check (real VPS rerun on `main`)

- `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = 2`
- `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = 300`
- `D_A_EXPORT_INPUT_CHECK = PASS`

## B1 evidence run output

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

## What this acceptance level MEANS

- **The D-B toolchain works end-to-end against real D-A
  export records.** The runner reads the real D-A export,
  adapts the `RECORD_AUDITED` events into post-discovery
  outcome inputs, evaluates each one, emits one
  `POST_DISCOVERY_OUTCOME_EVALUATED` per record, aggregates
  them into one `POST_DISCOVERY_OUTCOME_REPORT_GENERATED`,
  and writes the JSON / JSONL / markdown artefacts under
  `data/reports/post_discovery_outcome/pr69_main_real_d_a_evidence/`.
  This is the **toolchain** half of the acceptance.
- **The output is evidence-generated, but NOT
  direction-quality accepted.** 195/300 records (65%) are
  `INSUFFICIENT_PRICE_PATH` because the D-A export does not
  yet carry post-first-seen K-line price paths for those
  movers; 105/300 records (35%) are `MISSED_STRONG_TAIL`
  (the system never had a first-seen anchor at all). This
  is the **partial quality** half of the acceptance.
- **`RAVEUSDT` and `STOUSDT` remain unresolved by D-B
  alone.** They require price-path completeness or
  explicit data-gap triage before the Severe Missed Tail
  Triage slice can consume them.

## What this acceptance level does NOT MEAN

- **D-B does NOT solve direction.** No `long` / `short` /
  `entry` / `exit` / `stop` / `target` / `position_size` /
  `leverage` field is emitted; the labels are descriptive
  only.
- **D-B does NOT prove strategy profitability.** No PnL
  was simulated; no order was submitted; no Risk Engine
  decision was reproduced.
- **D-B does NOT authorise auto-tuning.** The labels MUST
  NOT drive `symbol_limit` expansion, anomaly threshold
  changes, candidate-pool capacity changes, Regime weight
  changes, or any other runtime knob. "Looking at the
  answer key" against the post-hoc D-A reference set is
  forbidden.
- **D-B does NOT authorise DeepSeek trade decisions.**
  DeepSeek remains read-only / sandbox-only / offline
  under the AI Layer Constitution.
- **Phase 12 remains FORBIDDEN.**

## Next allowed route (paper-only; gated, sequential)

- **B1 (this slice) closeout** — accepted as
  **toolchain + partial quality only**, NOT
  direction-quality.
- Then **either** (operator's choice, gated by an explicit
  kickoff PR per slice):
  - **B1.1** — *Historical Price Path Completeness / Kline
    Path Adapter* — **recommended** next route; needed
    because 195/300 records lack sufficient post-first-seen
    price path, and `RAVEUSDT` / `STOUSDT` remain
    unresolved on price-path / data-gap grounds.
  - **B2** — *Severe Missed Tail Triage* — admissible
    **only with the explicit note that `RAVEUSDT` and
    `STOUSDT` currently require price-path / data-gap
    triage** before they can be classified as severe
    missed tails by D-B alone.
- The **next allowed route is NOT** to start DeepSeek
  directly, and is **NOT** to start blind walk-forward
  directly.
- Recommended next slice after this docs PR: **B1.1 Price
  Path Completeness / Kline Path Adapter.**

## Files changed (docs-only)

- `docs/PROJECT_STATUS.md` — current-phase block flipped to
  D-B `ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
  PRICE_PATH_INSUFFICIENT`; the prior IN_REVIEW block is
  demoted to history.
- `docs/PHASE_GATE.md` — D-B added to the Closed phases
  table; the Open / Reserved D-B row is flipped to point at
  the closed entry; a new `## Closed phase: Phase
  11C.1C-C-B-B-B-D-B (ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY
  / PRICE_PATH_INSUFFICIENT)` deep-dive section is added.
- `docs/CHANGELOG.md` — new docs-only-closeout entry under
  `[Unreleased]`, above the existing PR #69 input-adapter
  entry.
- `docs/PR_DESCRIPTION.md` — this file.
- `docs/PHASE_11C_1C_C_B_B_B_D_B_POST_DISCOVERY_OUTCOME_METRICS.md`
  — new "Evidence closeout (PR after #69) —
  ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
  PRICE_PATH_INSUFFICIENT" section appended.

## Confirmations (per closeout requirements)

- **Docs-only.** Confirmed: only files under `docs/` are
  modified.
- **No runtime files changed.** Confirmed: no file under
  `app/`, `scripts/`, `tests/`, `configs/`, `risk/`,
  `execution/`, `exchanges/`, `llm/`, `telegram/`, or
  database schema is touched by this PR.
- **No event names changed.** Confirmed: no `EventType`
  enum / event-name string is added, removed, or renamed.
- **No tests run.** Confirmed: this PR did not invoke
  `pytest`, `unittest`, or any test runner.
- **D-B closeout wording = `PARTIAL_QUALITY /
  PRICE_PATH_INSUFFICIENT`.** Confirmed: the canonical
  wording recorded across `docs/PROJECT_STATUS.md`,
  `docs/PHASE_GATE.md`, `docs/CHANGELOG.md`,
  `docs/PR_DESCRIPTION.md`, and the D-B phase doc is
  `Phase 11C.1C-C-B-B-B-D-B: ACCEPTED_TOOLCHAIN /
  PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT`. D-B is
  **NOT** marked full quality accepted anywhere.
- **Phase 12 remains FORBIDDEN.** Confirmed across every
  modified doc; no Phase 1 safety flag is loosened.
- **No paper run / export / replay / historical builder
  invoked.** Confirmed.
- **No real API contacted.** Confirmed.

## Safety boundary (held end-to-end)

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

Stop here for human review.
