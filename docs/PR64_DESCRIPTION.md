# PR #64 — Phase 11C.1C-C-B-B-B-D-A Historical 60D Mover Coverage Backfill Audit v0 implementation

> **Status: IMPLEMENTATION PR.** Paper / report / evidence only.
> **NOT** live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning. **NOT**
> a strategy implementation. **NOT** a trading module. **NOT** a
> Historical 30D+ / 60D *complete strategy* blind replay /
> walk-forward validation gate. **NOT** the small-money
> live-trading pre-validation gate. **NOT** Phase 12.

## Phase ledger effect

  - Flips Phase 11C.1C-C-B-B-B-D-A from `NEXT_ALLOWED /
    NOT_STARTED` to **`IN_REVIEW`**.
  - A separate docs-only closeout PR is required after the
    operator captures real 60D backfill evidence to flip the
    slice to `ACCEPTED`.

## Safety boundary (carried verbatim into the runtime + every
event payload)

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - No Binance API key / secret. No signed endpoint. No
    `account` / `order` / `position` / `leverage` / `margin`
    endpoint. No private WebSocket. No `listenKey`.
  - No DeepSeek trade decision. No real Telegram outbound.
  - Phase 12 remains **FORBIDDEN**.
  - The audit MUST NEVER trigger a real trade, modify position
    size, leverage, stop-loss, target price, the Risk Engine,
    the Execution FSM, `symbol_limit`, candidate-pool capacity,
    anomaly thresholds, Regime weights, or any other runtime
    knob. The Risk Engine remains the single trade-decision gate.

## What this PR ships

### New module

`app/adaptive/historical_mover_coverage_backfill.py`

  - Status taxonomies: `HistoricalMoverCoverageBackfillStatus`
    (`READY` / `PARTIAL` / `DEGRADED` / `INSUFFICIENT_HISTORY` /
    `FAILED_REFERENCE_DATA`) and `HistoricalMoverCoverageStatus`
    (`CAPTURED` / `PARTIALLY_CAPTURED` / `MISSED` / `EXCLUDED`).
  - Fixed `HistoricalMoverMissReason` taxonomy (15 reasons,
    matching the brief verbatim).
  - Frozen data models: `HistoricalMoverReference`,
    `HistoricalMoverReferenceSet`, `HistoricalMoverCapturePath`,
    `HistoricalMoverCoverageRecord`,
    `HistoricalMoverCoverageBackfillInput`,
    `HistoricalMoverCoverageBackfillReport`.
  - Pure functions:
    `build_historical_60d_mover_reference_set(...)`,
    `audit_historical_mover_capture_path(...)`,
    `classify_historical_miss_reason(...)`,
    `build_historical_mover_coverage_backfill_report(...)`,
    `export_historical_mover_coverage_payload(...)`,
    `load_historical_mover_coverage_payload(...)`.
  - Lookahead Guard helpers:
    `validate_no_lookahead_fields(...)`,
    `assert_capture_event_is_past_or_equal_reference_window(...)`.
  - Historical Market Store loader:
    `load_historical_market_store(root)` reads
    `<root>/top_movers/*.jsonl` and
    `<root>/exchange_info/*.jsonl`. Optional subdirectories
    (`candles/`, `funding/`, `open_interest/`) are tolerated;
    only the columns the audit actually consumes are kept in
    memory.
  - Runtime: `HistoricalMoverCoverageBackfillRuntime` with a
    `flush(...)` orchestration entry point and a
    `metrics_payload()` getter consumed by the daily report
    builder.

### Two new typed events

`app/core/events.py`

  - `EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED` —
    one per audit window; carries the full
    `HistoricalMoverCoverageBackfillReport` payload.
  - `EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` — one
    per audited historical top mover; carries the per-mover
    capture-path evidence + descriptive `coverage_status` +
    miss-reason taxonomy.

Both events are paper / evidence only. Neither one can trigger
orders or modify the Risk Engine / Execution FSM.

### Daily report integration

`app/paper_run/daily_report.py`

  - New "Phase 11C.1C-C-B-B-B-D-A Historical 60D Mover Coverage
    Backfill Audit v0" Markdown section.
  - Surfaces every brief-mandated metric: `backfill_status`,
    `reference_window_days`, `history_days_observed`,
    `top_mover_count`, `eligible_top_mover_count`,
    `captured_top_mover_count`,
    `partially_captured_top_mover_count`,
    `missed_top_mover_count`, `excluded_top_mover_count`,
    `capture_recall_rate`, `partial_capture_rate`, `miss_rate`,
    `anomaly_detected_rate`, `label_tracking_rate`,
    `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`,
    `risk_rejected_mover_count`, `not_in_universe_count`,
    `missing_event_history_count`, `data_unreliable_count`,
    `median_first_seen_latency_seconds`,
    `p90_first_seen_latency_seconds`, `miss_reason_summary`,
    `coverage_warnings`, `lookahead_guard_warnings`, plus
    per-mover sample records (capped at 20 rows for the human
    summary; the full record list remains in the payload and
    in events.jsonl for export / replay).

### Public-market paper runner integration

`scripts/run_public_market_paper.py`

  - Two new CLI flags: `--historical-mover-store-dir`,
    `--historical-reference-window-days`.
  - Wires the runtime into the Phase 11C public-market paper
    loop: at shutdown the runner reads the local Historical
    Market Store (or runs against an empty reference set with
    an `INSUFFICIENT_HISTORY` status if no store is supplied),
    builds the reference set, walks the per-symbol event
    streams, classifies miss reasons, emits the two new events,
    and threads the metrics into the daily report.
  - Defensive `try` / `except` around the audit path: an
    audit-side failure cannot crash the public-market paper run.

### Lookahead Guard (verbatim, enforced in code)

  - `completed_tail_label` MUST NOT drive reference selection.
  - future return / final max gain MUST NOT pollute the
    simulated live-radar score.
  - replay label MUST NOT contaminate `first_seen_time`.
  - reflection / report text / LLM narrative MUST NEVER serve as
    a capture event source.
  - `first_seen_time_utc` MUST come from the timestamp of an
    event that already existed at audit time.
  - the top-mover reference set MUST only be used for post-hoc
    audit; it cannot rewrite past decisions.

### Tests

  - New module
    `tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_coverage_backfill.py`
    (22 tests):
    - `test_historical_mover_reference_set_contract`
    - `test_historical_mover_reference_excludes_non_futures`
    - `test_historical_capture_records_first_seen_time`
    - `test_historical_capture_path_detects_captured_mover`
    - `test_historical_capture_path_detects_partially_captured_mover`
    - `test_historical_capture_path_detects_missed_mover`
    - `test_historical_miss_reason_missing_event_history`
    - `test_historical_miss_reason_not_in_exchange_info`
    - `test_historical_miss_reason_risk_rejected`
    - `test_historical_mover_coverage_metrics`
    - `test_historical_mover_payload_roundtrip`
    - `test_historical_mover_events_exportable`
    - `test_daily_report_contains_historical_60d_section`
    - `test_lookahead_guard_rejects_completed_tail_label_as_reference_input`
    - `test_lookahead_guard_rejects_future_return_in_live_capture_source`
    - `test_forbidden_lookahead_field_list_is_complete`
    - `test_load_historical_market_store_reads_jsonl`
    - `test_load_historical_market_store_rejects_lookahead_jsonl`
    - `test_historical_coverage_does_not_trigger_execution`
    - `test_no_live_trading_flags_unchanged`
    - `test_phase_12_remains_forbidden`
    - `test_top_level_status_is_insufficient_history_when_short`
  - Phase 11B no-network audit
    (`tests/unit/test_phase11b_no_network.py`) extended to
    allow the two new event-type symbol references.

### Acceptance evidence (this PR)

  - `python -m pytest tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_coverage_backfill.py -q`
    — 22 / 22 PASS.
  - `python -m pytest tests/unit/ -k "phase11c_" -q` — 432 / 432
    PASS.
  - `python -m pytest tests/ -q` — full repo suite PASS (no
    regressions).
  - `python -m scripts.run_public_market_paper --duration 30s --symbol-limit 3 --dry-run`
    — generates the new "Phase 11C.1C-C-B-B-B-D-A Historical
    60D Mover Coverage Backfill Audit v0" section in the daily
    report; with no Historical Market Store configured the
    `historical_mover_backfill_status` is `INSUFFICIENT_HISTORY`
    and the section flags a coverage warning identifying the
    missing store directory.

### Out of scope (must NOT be relaxed by closeout PR)

  - **NOT** complete strategy blind replay.
  - **NOT** PnL backtest.
  - **NOT** trading module.
  - **NOT** AI Learning.
  - **NOT** automatic parameter optimisation.
  - **NOT** reinforcement learning.
  - **NOT** the small-money live-trading pre-validation gate.
  - **NOT** Phase 12.
  - The Historical Market Store serves the right-tail coverage
    audit only. It does **NOT** serve auto-trading. Audit
    results MUST NEVER trigger real trades or modify any
    runtime knob.

### Closeout note (not in this PR)

  - This PR is the v0 implementation. Real 60D historical data
    is **not** bundled and is **not** required for this PR's
    acceptance.
  - A subsequent operator-driven evidence-collection run (real
    60D top-mover snapshots + real exchangeInfo snapshots in
    `data/historical_market_store/`) plus a docs-only closeout
    PR is required to flip Phase 11C.1C-C-B-B-B-D-A to
    `ACCEPTED`.
  - The closeout PR MUST NOT relax thresholds, expand
    `symbol_limit`, modify candidate-pool capacity, modify
    anomaly thresholds, or modify Regime weights based on the
    historical audit numbers.
