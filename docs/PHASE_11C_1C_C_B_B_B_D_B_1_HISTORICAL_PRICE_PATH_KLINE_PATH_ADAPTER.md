# Phase 11C.1C-C-B-B-B-D-B.1 — Historical Price Path Completeness / Kline Path Adapter v0

*历史价格路径完整性 / K线路径适配器 v0*

> **Status: `ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE /
> DAILY_BUCKET_ONLY`** — explicitly **NOT** "intraday 1m / 5m
> kline path solved".
>
> **Type:** Paper / report / evidence-only small follow-up
> patch under Phase 11C.1C-C-B-B-B-D-B (Post-Discovery
> Outcome Metrics v0). **NOT** an indefinite extension of
> B1. Closeout returns the project to the main route.
>
> **Next allowed route: B2 — Severe Missed Tail Triage v0.**
>
> **Phase 12: FORBIDDEN.**

## What B1.1 is

B1.1 is the small patch on B1 (Phase 11C.1C-C-B-B-B-D-B
Post-Discovery Outcome Metrics v0) that addresses the two
merge-blocking issues PR #71 review surfaced and provides a
**v0** Historical Price Path Adapter / Kline Path Adapter
that the D-B evidence runner can consume:

  1. **Record-level price-path resolution.**
     `resolve_price_paths_for_records()` previously returned
     `dict[str, PricePathResolution]` keyed by symbol with
     first-record-wins semantics. A symbol that appeared
     more than once in the 60-day audit (different
     `first_seen_time_utc_ms` /
     `mover_window_start_utc_ms` /
     `mover_window_end_utc_ms`) silently shared the FIRST
     record's resolution with every later record. The fix
     changes the return type to
     `list[PricePathResolution | None]` aligned by index
     with the input `records` sequence; each record now
     consumes its **own** resolution.
  2. **Operator-supplied path Lookahead Guard.** Both
     `resolve_price_paths_for_records` and the legacy
     `build_post_discovery_inputs_from_d_a_payload` operator
     branch previously set
     `first_seen_price = float(operator_path[0].price)`
     without checking the timestamp. When
     `operator_path[0].timestamp_utc_ms >
     first_seen_time_utc_ms` this turned a future price
     into the discovery anchor — a classic lookahead leak
     that AMA-RT's hard-rule Lookahead Guard forbids. The
     fix introduces
     `build_operator_supplied_price_path_resolution()` in
     `app/adaptive/post_discovery_price_path_adapter.py`
     which enforces:
       * `first_seen_price` is **only** drawn from a point
         with `timestamp <= first_seen_time_utc_ms` (the
         latest such operator point), or — when no such
         operator point exists — from a
         `fallback_resolution.first_seen_price` (the
         adapter's containing-day open, lookahead-safe by
         construction). Otherwise `first_seen_price = None`
         and `missing_reason =
         OPERATOR_PATH_STARTS_AFTER_FIRST_SEEN`.
       * `price_path` only contains operator points with
         `timestamp > first_seen_time_utc_ms` (strictly
         after).
       * Without `first_seen_time_utc_ms` the operator path
         is rejected wholesale (`missing_reason =
         NO_FIRST_SEEN_TIME`).

## What B1.1 is NOT

  - **NOT** an intraday 1m / 5m kline path adapter.
    `kline_interval_used = 1d`. The adapter resolves
    daily-bucket OHLC from
    `data/historical_market_store/top_movers/*.jsonl`. For
    the containing day only the close at `day_end_ms` is
    emitted; for subsequent days the daily high / low are
    stamped at `day_end_ms`, surfaced as
    `approximate_intra_day_timestamps = true`.
  - **NOT** a direction call (no `long` / `short` /
    `entry` / `exit` / `stop` / `target` /
    `position_size` / `leverage` field).
  - **NOT** a strategy-profitability proof.
  - **NOT** auto-tuning authority (no `symbol_limit`
    expansion, anomaly threshold change, candidate-pool
    capacity change, Regime weight change, or any other
    runtime knob).
  - **NOT** DeepSeek / LLM trade authority.
  - **NOT** Phase 12.
  - **NOT** an indefinite extension of B1. B1.1 closeout
    returns the project to the main route.

## Lookahead Guard reaffirmation (hard rule)

  - `first_seen_time_utc_ms` is read-only and may only
    come from a D-A audited record / EventRepository event
    timestamp.
  - `first_seen_price` is **only** the price observed at
    or before `first_seen_time_utc_ms` (operator anchor /
    capture-path anchor / containing-day open).
  - `price_path_after_first_seen` only carries points
    strictly **after** `first_seen_time_utc_ms`.
  - `peak`, `trough`, `MFE`, `MAE`, `remaining_upside` are
    **post-window** audit metrics only.
  - Future outcome **never** feeds radar score, candidate
    promotion, the Risk Engine, the Execution FSM,
    `symbol_limit`, the candidate pool, anomaly
    thresholds, or Regime weights.
  - DeepSeek / LLM may explain evidence but cannot
    reverse-derive trading decisions from future results.

## Required diagnostic columns (retained)

  - `kline_interval_used`
  - `price_path_source_summary`
  - `price_path_missing_reason_summary`
  - `price_path_records_loaded`
  - `price_path_records_missing`
  - `notable_symbol_price_path_summary`

When the local Historical Market Store has no rows for a
symbol's containing day, the adapter emits a clear missing
reason (`SYMBOL_NOT_IN_HISTORICAL_STORE`,
`NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME`,
`HISTORICAL_STORE_DIR_MISSING`, ...). The runner does NOT
fabricate prices; it surfaces the gap as an explicit
operator-data requirement.

## B1.1 acceptance evidence (operator VPS, real D-A export)

Output directory:
`data/reports/post_discovery_outcome/pr71_main_price_path_evidence`

### Run summary

| Field                                            | Value |
| ------------------------------------------------ | ----- |
| `status`                                         | `EVIDENCE_GENERATED` |
| `evaluated_count`                                | `300` |
| `report_generated_count`                         | `1`   |
| `event_counts.POST_DISCOVERY_OUTCOME_EVALUATED`  | `300` |
| `event_counts.POST_DISCOVERY_OUTCOME_REPORT_GENERATED` | `1` |
| `kline_interval_used`                            | `1d`  |
| `B1_1_PRICE_PATH_MAIN_EVIDENCE_CHECK`            | `PASS` |

### Price path resolution coverage

| Field                              | Value |
| ---------------------------------- | ----- |
| `price_path_records_loaded`        | `17`  |
| `price_path_records_missing`       | `283` |

### Price path source summary

| Source                                          | Count |
| ----------------------------------------------- | ----- |
| `historical_market_store_daily_top_movers`      | `17`  |
| `absent`                                        | `283` |

### Price path missing-reason summary

| Reason                                          | Count |
| ----------------------------------------------- | ----- |
| `no_top_mover_row_covering_first_seen_time`     | `133` |
| `no_first_seen_time`                            | `110` |
| `insufficient_post_first_seen_points`           | `40`  |

### Notable symbol price-path summary

| Symbol     | `loaded` | `loaded_record_count` | `record_count` | `source` | `missing_reason` |
| ---------- | -------- | ---------------------- | --------------- | -------- | ---------------- |
| `RAVEUSDT` | `false`  | `0`                    | `17`            | `absent` | `no_top_mover_row_covering_first_seen_time` |
| `STOUSDT`  | `false`  | `0`                    | `3`             | `absent` | `no_top_mover_row_covering_first_seen_time` |

### Warnings

  - `d_a_backfill_records_missing_using_record_audited_fallback`
    (Format B fallback engaged; expected for the real D-A
    export shape; carried over from the B1 closeout and
    unchanged in B1.1).

## Acceptance interpretation

### What `ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY` means

  - **B1.1 toolchain works end-to-end** against the real
    D-A export. Record-level price-path resolution and the
    operator-path Lookahead Guard are enforced; the runner
    emits 300 `POST_DISCOVERY_OUTCOME_EVALUATED` events
    plus 1 `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` event
    under the output directory above.
  - **Coverage is partial.** Only 17 of 300 records have an
    adapter-loaded price path today; 283 of 300 remain
    `absent`.
  - **The price-path resolution is daily-bucket only.**
    `kline_interval_used = 1d`. **B1.1 does NOT solve the
    intraday 1m / 5m kline path problem.**

### What `ACCEPTED_TOOLCHAIN / PARTIAL_DATA_COVERAGE / DAILY_BUCKET_ONLY` does NOT mean

  - **B1.1 does NOT mean intraday 1m / 5m kline path is
    solved.**
  - **B1.1 does NOT solve direction.**
  - **B1.1 does NOT prove strategy profitability.**
  - **B1.1 does NOT authorise auto-tuning.**
  - **B1.1 does NOT authorise DeepSeek trade decisions.**
  - **Phase 12 remains FORBIDDEN.**

## Next allowed route (mainline; back on the main route)

> **Next allowed route: B2 — Severe Missed Tail Triage v0.**

B1 is a focused branch off the mainline and is **not** to
be extended indefinitely. B1.1 is the small patch on B1,
and B1.1 closeout returns the project to the main route.

B2 will perform root-cause triage on unresolved
severe-miss cases such as `RAVEUSDT` and `STOUSDT`,
attributing each into a **closed bucket** that includes
(but is not limited to):

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

### Why "B1.2" / Historical Kline Store Builder is NOT next

A *Historical Kline Store Builder / Intraday Price Path
Backfill* (sometimes referred to as "B1.2") is **NOT**
started now and is **NOT** the recommended next slice. It
is recorded as an **optional future data-quality task
only**, available **only if** B2 triage proves that
severe-miss attribution is blocked by missing intraday
price paths, and **only with explicit owner approval**. It
is **not** a precondition for B2, and **does not** block
B2.

This explicit ordering is recorded so that B1 / B1.1 are
not extended indefinitely and the project returns to the
main route after this closeout.

## Forbidden (under B1.1 closeout and remaining so)

  - **Phase 12** (real money / live trading) — remains
    **FORBIDDEN**;
  - Binance private API (no API key, no API secret, no
    signed endpoint, no `listenKey`, no private WS);
  - live orders;
  - real Telegram outbound;
  - DeepSeek / LLM trade decisions (direction, position
    size, leverage, stop-loss, target price, execution
    command, runtime config patch);
  - automatic parameter tuning (incl. `symbol_limit`
    expansion, anomaly threshold change, candidate pool
    capacity change, Regime weight change);
  - blind walk-forward via D-B / B1.1 alone;
  - any rule relaxation based on D-B / B1.1 labels;
  - any Telegram command that bypasses the Risk Engine;
  - extending B1 / B1.1 indefinitely instead of returning
    to the main route.

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

## Docs-only invariants (this closeout PR)

  - **Docs-only.** Only files under `docs/` are modified.
  - **No runtime files changed.** No file under `app/`,
    `scripts/`, `tests/`, `configs/`, `risk/`,
    `execution/`, `exchanges/`, `llm/`, `telegram/`, or
    database schema is touched by this PR.
  - **No event names changed.** No `EventType` enum /
    event-name string is added, removed, or renamed.
  - **No tests run.** This PR did not invoke `pytest`,
    `unittest`, or any test runner.
  - **No paper run / export / replay / historical builder
    invoked.**
  - **No real API contacted.**
