# PR #44 — Phase 11C.1C-C-B-B-A: Strategy Validation Dataset Builder & Quality Gate v0

> **Status: MERGED / ACCEPTED.** PR #44 merged into `main` on
> 2026-05-23 (UTC) at mergeCommit `3ecfc3b`; Phase
> 11C.1C-C-B-B-A is **ACCEPTED**. Paper / report only. **NOT**
> live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning.
> **NOT** the complete Strategy Validation Lab follow-up
> (Phase 11C.1C-C-B-B-B). **NOT** the Paper Alpha Gate v0.
> **NOT** Phase 12.
>
> Phase 11C.1C-C-B-A — *Strategy Validation Lab v0 & Cluster
> Exposure Control Contracts* — merged on 2026-05-23 (PR #42,
> mergeCommit `cc18047`) and is the gating predecessor. This
> PR shipped the **first slice** of the deeper Phase
> 11C.1C-C-B-B work: the Strategy Validation Dataset Builder +
> Quality Gate v0 on top of the Phase 11C.1C-C-B-A
> `StrategyValidationSample` / `StrategyValidationReport` /
> `ClusterExposureAssessment` artefacts.

## Phase

  - **Phase 11C.1C-C-B-A** — `ACCEPTED` (PR #42 merged into
    `main`, 2026-05-23, mergeCommit `cc18047`).
  - **Phase 11C.1C-C-B-B-A** — *this PR*. **`ACCEPTED`** (PR
    #44 merged into `main`, 2026-05-23, mergeCommit
    `3ecfc3b`). Paper / report only. Three new typed events.
    Dataset is exportable + replayable + auditable. Quality
    gate is a *sample trust* gate, NOT a *strategy quality*
    gate.
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    Reserved for the deeper Lab follow-up. Phase
    11C.1C-C-B-B-A acceptance does NOT authorise Phase
    11C.1C-C-B-B-B kickoff bypassing the standard gate.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock unchanged.

## Branch + base

  - Branch: `feature/phase-11c1c-c-b-b-validation-dataset-quality-gate`
  - Base: `main` (post PR #43 closeout).

## What ships

### 1. Strategy Validation Dataset Builder

  - **New module** `app/adaptive/strategy_validation_dataset.py`
    — pure-function module.
  - **Models**: `StrategyValidationDatasetRecord`,
    `StrategyValidationDatasetSummary`,
    `StrategyValidationDataset`.
  - **Pure functions**:
    `build_validation_dataset_from_samples`,
    `summarize_validation_dataset`,
    `export_validation_dataset_payload`,
    `load_validation_dataset_payload`.
  - Every record carries the brief-mandated fields: `report_id`,
    `opportunity_id`, `scan_batch_id`, `symbol`, `candidate_stage`,
    `strategy_mode`, `opportunity_score`, `early_tail_score`,
    `late_chase_risk`, `cluster_id`, `cluster_leader`,
    `tail_label`, per-window `mfe_5m / mae_5m / … / mfe_4h /
    mae_4h`, `reached_2r / 3r / 5r / 10r`, `fake_breakout`,
    `missed_tail`, `late_chase_failure`, `source_event_id`,
    `schema_version`.
  - Schema version: `phase_11c_1c_c_b_b_a.strategy_validation_dataset.v1`.

### 2. Quality Gate v0

  - **Models**: `StrategyValidationQualityGate`,
    `StrategyValidationQualityGateResult`.
  - **Pure function**:
    `evaluate_validation_dataset_quality(dataset, *, gate=None)`.
  - Threshold fields: `min_total_samples`,
    `min_completed_tail_labels`, `min_strategy_mode_coverage`,
    `min_candidate_stage_coverage`, `min_score_bucket_coverage`,
    `require_export_roundtrip`, `require_replay_readable`.
  - Output fields: `gate_status` (`pass` / `warn` / `fail` —
    descriptive only), `reasons`, `sample_count`,
    `completed_tail_label_count`, `missing_modes`,
    `missing_stages`, `missing_buckets`,
    `missing_required_fields`, `export_roundtrip_ok`,
    `replay_readable`.
  - First version is a **sample trust** gate, not a *strategy
    quality* gate. It only judges whether the dataset is
    trustworthy enough for downstream review. It does NOT judge
    whether the strategy is profitable.

### 3. Three new typed events

  - `STRATEGY_VALIDATION_DATASET_BUILT`
  - `STRATEGY_VALIDATION_DATASET_EXPORTED`
  - `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`

Every payload carries the brief-mandated identity block:
`report_id`, `timestamp`, `strategy_version`, `scoring_version`,
`risk_config_version`, `state_machine_version`, `schema_version`.

### 4. Runtime integration

  - `StrategyValidationRuntime.flush_report()` now also builds
    the dataset and evaluates the gate when the runtime config
    opts in (default `dataset_enabled=True`).
  - `StrategyValidationRuntimeConfig` extended with
    `dataset_enabled` + seven `quality_gate_*` fields. Defaults
    match the gate defaults.
  - `app/config/schema.py > StrategyValidationSection` and
    `app/config/defaults.yaml > strategy_validation` extended
    with the same fields + validators.
  - `metrics_payload()` now exposes
    `validation_dataset_records`, `validation_dataset_symbols`,
    `validation_dataset_tail_label_counts`,
    `validation_quality_gate_status`,
    `validation_quality_gate_reasons`,
    `validation_dataset_export_ready`,
    `validation_dataset_replay_ready`, plus the three new event
    counters.

### 5. Daily report

  - New `DailyReportSnapshot` fields:
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
  - New Markdown section "Phase 11C.1C-C-B-B-A Strategy
    Validation Dataset Builder & Quality Gate v0" with explicit
    "the `validation_quality_gate_status` is descriptive and
    **MUST NEVER trigger a real trade**; Phase 12 remains
    FORBIDDEN" disclaimer.
  - `DailyReportBuilder.build()` cross-checks the runner counters
    against the events.db type-counts of the three new event
    types so a stale runner counter cannot under-report.

### 6. Export / replay

  - The Phase 8.5 export bundle's `events.jsonl` carries every
    new event type automatically (the export service streams
    every row from events.db).
  - The Phase 10A replay engine accepts the new rows without
    raising; legacy / future rows missing `schema_version` are
    tolerated. A regression test pins this.

### 7. Tests

  - `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`
    — **27 brief-mandated cases**:
      - `test_strategy_validation_dataset_record_contract`
      - `test_dataset_record_required_fields_constant_matches_payload`
      - `test_build_validation_dataset_from_samples`
      - `test_summarize_validation_dataset`
      - `test_summarize_empty_dataset_returns_empty_summary`
      - `test_quality_gate_passes_with_sufficient_samples`
      - `test_quality_gate_warns_on_low_samples`
      - `test_quality_gate_warns_on_missing_coverage`
      - `test_quality_gate_fails_missing_required_fields`
      - `test_quality_gate_fails_on_empty_dataset_with_default_thresholds`
      - `test_quality_gate_status_vocabulary_locked`
      - `test_quality_gate_with_relaxed_thresholds_passes_small_dataset`
      - `test_dataset_export_roundtrip`
      - `test_load_validation_dataset_payload_tolerates_missing_optional_fields`
      - `test_load_validation_dataset_payload_rejects_non_mapping`
      - `test_runtime_emits_dataset_built_and_quality_gate_events`
      - `test_runtime_disabled_dataset_skips_dataset_events`
      - `test_runtime_quality_gate_uses_config_thresholds`
      - `test_export_bundle_contains_new_event_types`
      - `test_replay_reads_validation_dataset_events`
      - `test_replay_handles_dataset_events_missing_schema_version`
      - `test_daily_report_contains_validation_dataset_metrics`
      - `test_daily_report_renders_when_no_dataset`
      - `test_no_live_trading_flags_unchanged`
      - `test_validation_dataset_does_not_trigger_execution`
      - `test_phase_12_remains_forbidden`
      - `test_runtime_config_quality_gate_thresholds_round_trip`
  - `tests/unit/test_phase11b_no_network.py >
    test_phase11b_event_emission_does_not_invent_new_event_types`
    extended to allow the three new event types.
  - **Full pytest** run: **2313 passed** (2286 baseline + 27
    new). No regression.
  - **`tests/unit/ -k phase11c_`** filter: **339 passed**
    (312 baseline + 27 new).

### 8. Docs

  - **New**:
    - `docs/PHASE_11C_1C_C_B_B_VALIDATION_DATASET_QUALITY_GATE.md`
    - `docs/PR44_DESCRIPTION.md`
  - **Updated**:
    - `docs/PROJECT_STATUS.md` (mark Phase 11C.1C-C-B-B-A as
      `IN_REVIEW`).
    - `docs/PHASE_GATE.md` (move Phase 11C.1C-C-B-B-A from
      `NEXT_ALLOWED / NOT_STARTED` to `IN_REVIEW`).
    - `docs/CHANGELOG.md` (Phase 11C.1C-C-B-B-A entry).

## What does NOT ship

  - **Real trading**.
  - **Binance private API / signed endpoint / listenKey / private
    WebSocket**.
  - **LLM / DeepSeek trade decision**.
  - **Real Telegram outbound**.
  - **Right-tail in production scope**.
  - **Validation result triggering real downstream execution**.
  - **AI deciding direction / position / leverage / stop-loss /
    target / execution**.
  - **Automatic parameter optimisation**.
  - **Reinforcement learning**.
  - **Risk Engine override**. The Risk Engine remains the single
    trade-decision gate.
  - **Phase 11C.1C-C-B-B-B implementation**.
  - **Phase 12 / live trading kickoff**.

## Real-WS smoke

**Not required for this PR.** Phase 11C.1C-C-B-B-A scope is
**dataset / quality-gate contract**. The smallest Phase
11C.1C-C-A tracking window is 5 minutes; a 30 s dry-run cannot
complete a primary window and therefore cannot produce a non-empty
dataset. The brief asks the PR to surface an *empty-but-well-
formed* quality-gate report under the 30 s smoke; that is what
ships. A real public WS 10-minute smoke is reserved for Phase
11C.1C-C-B-B-B closeout when non-empty datasets are first
observable end-to-end.

## Dry-run smoke (30 s, captured 2026-05-23 09:25:58)

```
duration_seconds                = 30
dry_run                         = True
ws_real_transport               = False
chains_emitted                  = 2
ws_chains_emitted               = 2
risk_approved                   = 0
risk_rejected                   = 2
learning_ready_attached         = 2
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
rate_limit_ban                  = False
ws_reconnect_count              = 0
ws_stale_count                  = 0

# Phase 11C.1C-C-B-B-A new section in daily report
STRATEGY_VALIDATION_DATASET_BUILT count       = 1
STRATEGY_VALIDATION_DATASET_EXPORTED count    = 1
STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED    = 1
validation_dataset_records                     = 2
validation_dataset_symbols                     = 2  (BTCUSDT, ETHUSDT)
quality_gate_status                            = fail
validation_dataset_export_ready                = True
validation_dataset_replay_ready                = True
quality_gate_reasons:
  - sample_count_below_half_min=2<10
  - completed_tail_labels_below_min=0<10
  - strategy_mode_coverage_below_min=1<2
  - candidate_stage_coverage_below_min=1<2
  - score_bucket_coverage_below_min=1<2

# Safety boundary held
mode                            = paper
exchange_live_order_enabled     = False
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
trading_mode_paper              = True
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no API key                      = confirmed
no signed endpoint              = confirmed
no private websocket            = confirmed
no listenKey                    = confirmed
no DeepSeek trade decision      = confirmed
no real Telegram outbound       = confirmed
Phase 12                        = FORBIDDEN (gate unchanged)
```

`gate_status=fail` is the **expected** output: the smallest
Phase 11C.1C-C-A tracking window is 5 minutes, so the samples
that landed in the 30 s window are necessarily in-flight /
unresolved. The quality gate correctly classifies the dataset as
too thin for downstream review — exactly the brief's "empty or
low-sample quality gate report" requirement.

## Acceptance gate (status: ALL GATES MET; PR #44 merged into `main`)

  - 27 brief-mandated tests PASS.
  - phase11c_ filter PASS (339).
  - Full pytest PASS (2313, no regression vs. PR #43 baseline).
  - 30 s dry-run smoke PASS with empty / low-sample
    quality-gate report (`gate_status=fail` is the **expected**
    output for the low-sample 30 s window — exactly the brief's
    "empty or low-sample quality gate report" requirement).
  - Real WS 10 min smoke is **not required** for this PR;
    reserved for Phase 11C.1C-C-B-B-B closeout.
  - Phase 1 safety flags all confirmed False.
  - Phase 12 remains FORBIDDEN.

PR #44 has merged into `main` (mergeCommit `3ecfc3b`, merged
2026-05-23 UTC); the dry-run smoke evidence above was
accepted; this docs-only closeout PR therefore flips Phase
11C.1C-C-B-B-A to **ACCEPTED**, mirroring the PR #36 → PR
#37, PR #38 → PR #39, PR #40 → PR #41, and PR #42 → PR #43
closeout pattern.

## Remaining risk

  - Quality gate is descriptive only; nothing in this PR can
    accidentally turn it into a trade-authorisation signal because
    no module reads `gate_status` to drive execution. All test
    cases pin this.
  - Dataset payloads can grow unbounded with `max_samples=2000`
    (Phase 11C.1C-C-B-A bound); the gate sits on top of that
    bound. No new memory pressure introduced.
  - Schema version bump is forward-incompatible; legacy / future
    payloads missing the field are tolerated by the loader and
    the replay engine.
