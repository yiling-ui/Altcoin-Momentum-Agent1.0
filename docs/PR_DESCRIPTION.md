# Phase 11C.1C-C-B-B-B-D-B Post-Discovery Outcome Metrics v0 evidence runner: real D-A export input adapter

## Summary

The Phase 11C.1C-C-B-B-B-D-B evidence runner used to read D-A
records exclusively from
`HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED.payload.records`.
On the operator VPS the **real** D-A export emits that event
with `records` missing / `None` and ships the per-mover records
on separate `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` events
whose payload **is** the record (not wrapped). Result:

- D-A export input check: PASS (`HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = 2`,
  `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = 300`,
  `D_A_EXPORT_INPUT_CHECK = PASS`)
- D-B runner output: `status = EVIDENCE_GENERATED`,
  `evaluated_count = 0`, `report_generated_count = 1`, no
  `POST_DISCOVERY_OUTCOME_EVALUATED` emitted, closeout final
  check failing with `D_B_EVALUATED_COUNT_ZERO`.

This PR fixes the D-B input adapter so the real D-A export shape
produces `evaluated_count > 0` and emits one
`POST_DISCOVERY_OUTCOME_EVALUATED` per audited mover, while
keeping the existing payload-shape path working.

## What changed

### `scripts/run_post_discovery_outcome_evidence.py`

- Added the `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` event
  type constant (string only; no `EventType` change).
- New `_adapt_record_audited_payload(payload, *, event_symbol=None)`
  helper. Supports both shapes:
  - **Wrapped:** `payload['record']` is the per-mover record.
  - **Flat:** `payload` itself is the per-mover record (real
    D-A export emit).
  - Symbol resolution priority: `record["symbol"]` →
    `record["reference"]["symbol"]` →
    `record["capture_path"]["symbol"]` → event-level `symbol`.
  - All canonical D-A record fields are preserved on the
    adapted output: `coverage_status`, `reference`,
    `capture_path`, `miss_reason`, `miss_reasons`,
    `first_seen_time_utc_ms`, `first_seen_event_type`,
    `first_seen_latency_seconds`, `capture_path_depth`,
    `risk_rejected`, `reached_anomaly`, `reached_label_queue`,
    `reached_tail_label`, `reached_strategy_validation_sample`.
- New `_scan_export_dir_for_d_a_record_audited_events(...)` and
  `_load_d_a_record_audited_events_from_db(...)` helpers that
  collect every adapted record from the operator-supplied
  export dir / events SQLite database.
- `load_d_a_coverage_payload(...)` now returns
  `(payload, audited_records, warnings)`. The runner collects
  RECORD_AUDITED records from every available source so the
  Format B fallback works even when the BACKFILL_GENERATED
  payload was found but has `records=None`.
- `run_evidence_pipeline(...)` priority:
  - If `BACKFILL_GENERATED.payload.records` is non-empty →
    Format A (unchanged behaviour).
  - Else if RECORD_AUDITED records were collected → Format B:
    synthesise a payload re-using the BACKFILL_GENERATED
    report-level fields and populate `records` from the
    RECORD_AUDITED fallback. A warning
    `d_a_backfill_records_missing_using_record_audited_fallback`
    is recorded.
  - Else if no payload and no RECORD_AUDITED records →
    `INSUFFICIENT_EVIDENCE` (existing behaviour).
- Closeout-quality guard: if the export DID carry RECORD_AUDITED
  events but the D-B input adapter produced zero inputs, the
  run is **not** treated as a quiet `EVIDENCE_GENERATED` success.
  - New explicit warning:
    `d_a_records_present_but_no_post_discovery_inputs`.
  - New status: `INSUFFICIENT_EVALUABLE_RECORDS`.
  - CLI exit code is non-zero so closeout tooling refuses
    to mark the phase ACCEPTED.
- `build_post_discovery_inputs_from_d_a_payload(...)` symbol
  resolution now also falls back through
  `reference["symbol"]` and `capture_path["symbol"]`, which
  matches the real D-A record shape.

### `tests/unit/test_post_discovery_outcome_evidence_runner.py`

Extended with the cases mandated by the brief plus adapter-level
coverage:

- **Case A:** `BACKFILL_GENERATED.payload.records` non-empty →
  `evaluated_count > 0`, `POST_DISCOVERY_OUTCOME_EVALUATED`
  emitted (one per record), `POST_DISCOVERY_OUTCOME_REPORT_GENERATED`
  emitted exactly once.
- **Case B:** `BACKFILL_GENERATED.payload.records` missing/None
  plus 2 RECORD_AUDITED events whose payload **is** the record
  (no top-level `symbol`; only `reference.symbol` /
  `capture_path.symbol` available). Asserts:
  - `evaluated_count == 2`
  - `POST_DISCOVERY_OUTCOME_EVALUATED` count == 2
  - `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` count == 1
  - fallback warning recorded
  - notable symbols pinned via the symbol-fallback chain.
- **Case B':** RECORD_AUDITED events whose payload IS wrapped
  in a legacy `record` key are also adapted.
- **Case C:** RECORD_AUDITED events present but unusable - the
  run is **not** an EVIDENCE_GENERATED success, and emits
  warning + appropriate insufficient-evidence status.
- Adapter-level unit tests pin the four symbol-resolution
  branches and the `(payload, audited, warnings)` return shape
  of `load_d_a_coverage_payload`.

## Tests run

```
$ python -m pytest tests/unit/test_post_discovery_outcome_evidence_runner.py -q
21 passed

$ python -m pytest tests/unit/test_post_discovery_outcome_metrics.py -q
20 passed

$ python -m pytest tests/unit -k "post_discovery" -q
41 passed
```

End-to-end sanity check on the exact operator-VPS shape (300
RECORD_AUDITED events, BACKFILL_GENERATED with no `records`,
no top-level event `symbol`):

```
status: EVIDENCE_GENERATED
evaluated_count: 300
report_generated_count: 1
emit POST_DISCOVERY_OUTCOME_EVALUATED: 300
emit POST_DISCOVERY_OUTCOME_REPORT_GENERATED: 1
warnings (first 3): ['d_a_backfill_records_missing_using_record_audited_fallback']
```

## Confirmations

- RECORD_AUDITED fallback: **works** (Case B test +
  end-to-end smoke pass).
- `evaluated_count > 0` in fallback test: **confirmed**
  (`evaluated_count == 2` in Case B; `300` end-to-end).
- Event names changed: **NO** (no `EventType` enum touched;
  only an opaque string constant added in the runner module).
- Schema versions changed: **NO** (no
  `POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION` change).
- Runtime trading behaviour changed: **NO** (only the runner
  script + its tests are modified).
- Risk Engine change: **NO** (`app/risk/` untouched).
- Execution FSM change: **NO** (`app/execution/` untouched).
- Exchange-private call: **NO** (`app/exchanges/` untouched).
- LLM / DeepSeek call: **NO** (`app/llm/` untouched).
- Telegram outbound: **NO** (`app/telegram/` untouched).
- `symbol_limit`, candidate-pool capacity, anomaly thresholds,
  Regime weights: **NO** change.
- Phase 12: remains **FORBIDDEN**.

## Files changed

- `scripts/run_post_discovery_outcome_evidence.py`
- `tests/unit/test_post_discovery_outcome_evidence_runner.py`
- `docs/CHANGELOG.md`
- `docs/PR_DESCRIPTION.md`

Stop here for human review.
