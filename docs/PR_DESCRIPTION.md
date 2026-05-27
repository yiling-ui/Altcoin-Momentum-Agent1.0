# Phase 11C.1C-C-B-B-B-D-B.1 Historical Price Path Completeness / Kline Path Adapter v0 evidence closeout: ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY (docs-only)

## Summary

This is a **docs-only** PR. It records the Phase
11C.1C-C-B-B-B-D-B.1 (*Historical Price Path Completeness /
Kline Path Adapter v0 / 历史价格路径完整性 / K线路径适配器 v0*)
evidence closeout based on the **real** D-B evidence runner
output rerun on `main` from the operator VPS, after PR #71
merged the price-path adapter implementation.

The closeout level is **explicitly NOT "intraday 1m / 5m
kline path solved"**. It is:

> **`Phase 11C.1C-C-B-B-B-D-B.1: ACCEPTED_TOOLCHAIN /
> PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`**

This PR also makes the explicit route correction back to the
main route:

> **Next allowed route: B2 — Severe Missed Tail Triage v0.**

B1 is a focused branch off the mainline and is **not** to be
extended indefinitely. B1.1 is the small patch on B1, and
B1.1 closeout returns the project to the main route. The
*Historical Kline Store Builder / Intraday Price Path
Backfill* (sometimes referred to as "B1.2") is **NOT**
started now and is **NOT** the recommended next slice — it
is an **optional future data-quality task only**, available
only if B2 triage proves severe-miss attribution is blocked
by missing intraday price paths, and only with explicit
owner approval.

## Required closeout statements (verbatim)

1. **B1.1 toolchain passed.**
2. **PR #71 evidence runner can evaluate 300 records.**
3. **300 `POST_DISCOVERY_OUTCOME_EVALUATED` events were
   emitted.**
4. **1 `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event was
   emitted.**
5. **The price-path adapter is currently daily-bucket only
   (`kline_interval_used = 1d`).**
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

## B1.1 evidence run output

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

## What this acceptance level MEANS

- **B1.1 toolchain works end-to-end** against the real
  D-A export. The price-path adapter
  (`app/adaptive/post_discovery_price_path_adapter.py`)
  resolves price paths at **record level** (not
  symbol-only and not first-record-wins) and enforces the
  operator-supplied-path Lookahead Guard (no point with
  `timestamp > first_seen_time_utc_ms` may serve as
  `first_seen_price`). The runner emits 300
  `POST_DISCOVERY_OUTCOME_EVALUATED` events plus 1
  `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event under
  `data/reports/post_discovery_outcome/pr71_main_price_path_evidence/`.
- **Coverage is partial.** Only 17 of 300 records have an
  adapter-loaded price path today; 283 of 300 remain
  `absent`. The dominant missing reasons are
  `no_top_mover_row_covering_first_seen_time = 133`,
  `no_first_seen_time = 110`, and
  `insufficient_post_first_seen_points = 40`.
- **The price-path resolution is daily-bucket only.**
  `kline_interval_used = 1d`. For the containing day only
  the close at `day_end_ms` is emitted; for subsequent
  days the daily high / low are stamped at `day_end_ms`,
  surfaced as `approximate_intra_day_timestamps = true`.
  **B1.1 does NOT solve the intraday 1m / 5m kline path
  problem.**

## What this acceptance level does NOT MEAN

- **B1.1 does NOT mean intraday 1m / 5m kline path is
  solved.** It is daily-bucket only.
- **B1.1 does NOT solve direction.** No `long` / `short`
  / `entry` / `exit` / `stop` / `target` /
  `position_size` / `leverage` field is emitted; the
  labels are descriptive only.
- **B1.1 does NOT prove strategy profitability.** No PnL
  was simulated; no order was submitted; no Risk Engine
  decision was reproduced.
- **B1.1 does NOT authorise auto-tuning.** The labels
  MUST NOT drive `symbol_limit` expansion, anomaly
  threshold changes, candidate-pool capacity changes,
  Regime weight changes, or any other runtime knob.
- **B1.1 does NOT authorise DeepSeek trade decisions.**
  DeepSeek remains read-only / sandbox-only / offline
  under the AI Layer Constitution.
- **Phase 12 remains FORBIDDEN.**

## Next allowed route (mainline; back on the main route)

> **Next allowed route: B2 — Severe Missed Tail Triage v0.**

B1 is a focused branch off the mainline and is **not** to
be extended indefinitely. B1.1 is the small patch on B1,
and B1.1 closeout returns the project to the main route.

B2 will perform root-cause triage on unresolved
severe-miss cases such as `RAVEUSDT` and `STOUSDT`,
attributing each into a closed bucket that includes (but
is not limited to):

- `PRICE_PATH_GAP`
- `DATA_UNRELIABLE`
- `EVENT_HISTORY_MISSING`
- `UNIVERSE_GAP`
- `SYMBOL_LIMIT_GAP`
- `CANDIDATE_POOL_EVICTED`
- `THRESHOLD_TOO_STRICT`
- `WS_DATA_GAP`
- `REST_REFERENCE_GAP`
- `RISK_REJECTED_BUT_MOVED`
- `TRUE_DISCOVERY_FAILURE`
- `UNKNOWN`

B2 remains forbidden from authorising:

- auto-tuning;
- any threshold change;
- `symbol_limit` expansion;
- candidate-pool capacity change;
- Regime weight change;
- live trading;
- DeepSeek trade decision;
- Phase 12.

A *Historical Kline Store Builder / Intraday Price Path
Backfill* (sometimes referred to as "B1.2") is **NOT**
started now. It is recorded as an **optional future
data-quality task only**, available **only if** B2 triage
proves severe-miss attribution is blocked by missing
intraday price paths, and **only with explicit owner
approval**. It is **not** the recommended next slice,
**not** a precondition for B2, and **does not** block B2.

## Files changed (docs-only)

- `docs/PROJECT_STATUS.md` — current-phase block flipped
  to B1.1 `ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
  DAILY_BUCKET_ONLY`; the prior D-B block is demoted to
  history.
- `docs/PHASE_GATE.md` — B1.1 added to the Closed phases
  table; the Open / Reserved B1.1 row added; new
  `## Closed phase: Phase 11C.1C-C-B-B-B-D-B.1
  (ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
  DAILY_BUCKET_ONLY)` deep-dive section appended.
- `docs/CHANGELOG.md` — new docs-only-closeout entry
  under `[Unreleased]`, above the existing PR #71
  follow-up fix entry.
- `docs/PR_DESCRIPTION.md` — this file.
- `docs/PHASE_11C_1C_C_B_B_B_D_B_1_HISTORICAL_PRICE_PATH_KLINE_PATH_ADAPTER.md`
  — new B1.1 phase doc (created in this PR).

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
- **B1.1 closeout wording = `ACCEPTED_TOOLCHAIN /
  PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY`.** Confirmed:
  the canonical wording recorded across
  `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
  `docs/CHANGELOG.md`, `docs/PR_DESCRIPTION.md`, and the
  new B1.1 phase doc is `Phase 11C.1C-C-B-B-B-D-B.1:
  ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
  DAILY_BUCKET_ONLY`. B1.1 is **NOT** marked "intraday
  1m / 5m kline path solved" anywhere.
- **Next allowed route = B2 — Severe Missed Tail Triage
  v0.** Confirmed across every modified doc.
- **B1.2 / Historical Kline Store Builder / Intraday
  Price Path Backfill is recorded as an optional future
  data-quality task only, NOT started now, NOT the
  recommended next slice, NOT a precondition for B2.**
  Confirmed across every modified doc.
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
