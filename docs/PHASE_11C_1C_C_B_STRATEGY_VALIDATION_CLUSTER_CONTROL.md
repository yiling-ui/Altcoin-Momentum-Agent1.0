# Phase 11C.1C-C-B-A — Strategy Validation Lab v0 & Cluster Exposure Control Contracts

> **Status:** ACCEPTED (closed 2026-05-23; PR #42 merged into `main`,
> mergeCommit `cc18047`). **NOT** live trading. **NOT** AI Learning.
> **NOT** the complete Strategy Validation Lab. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning. **NOT**
> Phase 12. Paper / report only.
>
> Phase 11C.1C-C-A — *MFE / MAE Label Queue Runtime & Tail Outcome
> Tracking* — is the gating predecessor; it merged on 2026-05-23 as
> PR #40 (mergeCommit `75d3c7c`). Phase 11C.1C-C-B-A is the **first
> slice** of the deeper Phase 11C.1C-C-B Strategy Validation Lab
> work and ships only the data contracts + pure aggregators + the
> seven typed events that let the Lab v0 run through the existing
> Phase 8.5 export + Phase 10A replay machinery without inventing a
> new pipeline.
>
> The acceptance gate is **fully on file**: 25/25 brief-mandated
> tests + 312/312 phase11c\_ tests + 2286/2286 full pytest PASS on
> the PR branch (no regression vs. the post-PR-#41 main 2261
> baseline); the **operator-VPS 10 min real public WS smoke
> PASSED** on 2026-05-23 against the PR #42 head (commit
> `0bedcce`); PR #42 has merged into `main` (mergeCommit
> `cc18047`); the smoke evidence was accepted; this docs-only
> closeout PR records Phase 11C.1C-C-B-A as **ACCEPTED**, mirroring
> the PR #36 → PR #37, PR #38 → PR #39, and PR #40 → PR #41
> closeout pattern. Phase 11C.1C-C-B-B is now **NEXT_ALLOWED /
> NOT_STARTED**: Phase 11C.1C-C-B-A acceptance does **NOT**
> authorise Phase 11C.1C-C-B-B kickoff bypassing the standard
> gate. Phase 12 remains **FORBIDDEN**.

## Phase

  - **Phase 11C.1C-C-B-A** — Strategy Validation Lab v0 + Cluster
    Exposure Control Contracts on top of the Phase 11C.1C-C-A
    `LabelTrackingRecord` outcomes. **Paper / report only.**
    **ACCEPTED (closed 2026-05-23; PR #42 merged into `main`,
    mergeCommit `cc18047`).**
  - **Phase 11C.1C-C-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    Reserved for the deeper Lab follow-up (richer cohort
    comparisons, extended cluster heuristics, longer-window
    correlations). **NOT** authorised by Phase 11C.1C-C-B-A
    acceptance bypassing the standard gate.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock unchanged.

## Goal

Phase 11C.1C-C-A produces forward MFE / MAE / `tail_label` outcomes
per ACTIVE candidate. Phase 11C.1C-C-B-A turns those outcomes into
the first version of the data substrate a human reviewer can use to
answer:

  - is `early_tail_score` actually catching demon coins earlier?
  - does `opportunity_score` correlate with later realised MFE / MAE?
  - is `strategy_mode` (`follow` / `pullback` / `observe` / `reject`)
    making the right call — including "did we correctly refuse"?
  - is `candidate_stage` (`early` / `mid` / `late` / `blowoff` /
    `dumped`) informative?
  - did the cluster *leader* outperform its followers?
  - are simultaneous candidates inside one cluster building unsafe
    exposure for a future PR to consider capping?

## Boundary

This phase ships contracts + pure aggregation + the runtime that
emits the seven new typed events. Specifically:

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - **NO** Binance API key
  - **NO** Binance API secret
  - **NO** signed endpoint
  - **NO** account / order / position / leverage / margin endpoint
  - **NO** private WebSocket
  - **NO** `listenKey`
  - **NO** DeepSeek trade decision
  - **NO** real Telegram outbound
  - **NO** Phase 12

## Forbidden in this phase

  - **NOT** real trading, **NOT** Binance private API, **NOT** live
    trading.
  - **NOT** an AI / LLM that decides direction, position size,
    leverage, stop, target price, or execution.
  - **NOT** automatic parameter optimisation; **NOT** reinforcement
    learning.
  - **NOT** allowed: a validation result triggering a real order or
    modifying any real position.
  - **NOT** the complete Strategy Validation Lab; this is **v0**.
  - **NOT** Phase 12.
  - The Risk Engine remains the single trade-decision gate. Nothing
    in this phase changes that.

## What ships

### Data contracts (`app/adaptive/strategy_validation.py`)

  - `StrategyValidationSample` — one immutable sample per
    opportunity outcome. Carries identity (`opportunity_id` /
    `scan_batch_id` / `symbol`), the adaptive snapshot
    (`candidate_stage`, `strategy_mode`, `opportunity_score` /
    `opportunity_grade`, `early_tail_score`, `late_chase_risk`),
    the cluster context (`cluster_id`, `cluster_leader`,
    `is_cluster_leader`), the Phase 11C.1C-C-A `tail_label`, the
    five-window MFE / MAE pairs (`mfe_5m` / `mae_5m`, `mfe_15m` /
    `mae_15m`, `mfe_30m` / `mae_30m`, `mfe_1h` / `mae_1h`,
    `mfe_4h` / `mae_4h`), the R-multiple flags
    (`reached_2r` / `3r` / `5r` / `10r`), and the outcome flags
    (`fake_breakout`, `missed_tail`, `late_chase_failure`).
  - `StrategyValidationWindowStats` — per-window cohort
    aggregate (avg / median MFE + MAE).
  - `StrategyModeValidationStats` — per-mode cohort aggregate
    with the brief-mandated rate set (`avg_mfe`, `avg_mae`,
    `median_mfe`, `median_mae`, `p_reached_2r`, `p_reached_3r`,
    `p_reached_5r`, `p_reached_10r`, `fake_breakout_rate`,
    `missed_tail_rate`, `late_chase_failure_rate`,
    `strong_tail_rate`, `weak_tail_rate`).
  - `CandidateStageValidationStats` — per-stage cohort aggregate.
  - `OpportunityScoreBucketStats` — per-bucket cohort aggregate.
    Buckets: `0-49` / `50-64` / `65-79` / `80-100`.
  - `EarlyTailScoreBucketStats` — per-bucket cohort aggregate.
    Buckets: `0-24` / `25-49` / `50-74` / `75-100`.
  - `TailLabelDistribution` — sample-level tail-label counts +
    rates.
  - `ClusterLeaderValidationStats` — per-cluster leader-vs-follower
    comparison.
  - `ClusterExposureAssessment` — per-cluster exposure record.
    Fields: `cluster_id`, `symbols`, `leader_symbol`,
    `follower_symbols`, `leader_score`, `cluster_size`,
    `correlated_candidate_count`, `cluster_mfe_mean`,
    `leader_outperformed_followers`, `overexposure_warning`,
    `suggested_cluster_action` (`leader_only` /
    `observe_followers` / `reject_cluster` / `no_action`).
    **`suggested_cluster_action` is paper / report only — it MUST
    NEVER trigger a real trade.**
  - `StrategyValidationReport` — top-level report with every
    sub-aggregate, plus `top_strategy_validation_symbols` and a
    `flagged_findings` tuple.

### Pure aggregators (`app/adaptive/strategy_validation.py`)

  - `build_strategy_validation_sample(...)`
  - `aggregate_by_strategy_mode(...)`
  - `aggregate_by_candidate_stage(...)`
  - `aggregate_by_opportunity_score_bucket(...)`
  - `aggregate_by_early_tail_score_bucket(...)`
  - `aggregate_tail_label_distribution(...)`
  - `evaluate_cluster_leader_performance(...)`
  - `assess_cluster_exposure(...)`
  - `build_strategy_validation_report(...)`

All functions are pure (no I/O, no clock read, no
`EventRepository.append`). The runtime that wires them through to
events.db is in `app/adaptive/strategy_validation_runtime.py`.

### Runtime (`app/adaptive/strategy_validation_runtime.py`)

  - `StrategyValidationRuntimeConfig` — `enabled` / `max_samples` /
    `primary_window` / `overexposure_warning_threshold` /
    `top_symbol_limit`. All thresholds configurable, not hard-coded.
  - `StrategyValidationRuntime` — owns the in-process sample
    buffer; `observe_label_record(label_record, adaptive, ...)` is
    idempotent per `opportunity_id`; `flush_report(...)` emits the
    seven typed events.

### Seven new event types (`app/core/events.py`)

  - `STRATEGY_VALIDATION_SAMPLE_CREATED`
  - `STRATEGY_VALIDATION_REPORT_GENERATED`
  - `STRATEGY_MODE_VALIDATED`
  - `CANDIDATE_STAGE_VALIDATED`
  - `SCORE_BUCKET_VALIDATED`
  - `CLUSTER_EXPOSURE_ASSESSED`
  - `CLUSTER_LEADER_VALIDATED`

Every payload carries `schema_version`
(`phase_11c_1c_c_b_a.strategy_validation.v1`), `report_id` and / or
`opportunity_id`, `scan_batch_id`, `symbol` (when applicable),
`timestamp`, `strategy_version`, `scoring_version`,
`risk_config_version`, `state_machine_version`,
`validation_version`, and `source_phase`.

### Wiring

  - `WSRadarChainDriver` — accepts a new
    `strategy_validation_runtime` kwarg. After the Phase 11C.1C-A
    `LABEL_QUEUE_ENQUEUED` lands and the Phase 11C.1C-C-A
    `LabelQueueRuntime.observe(...)` returns the
    `LabelTrackingRecord`, the chain calls
    `runtime.observe_label_record(label_record, adaptive, ...)`.
  - `scripts/run_public_market_paper.py` — instantiates the
    runtime from `settings.strategy_validation`, snapshots metrics
    on every loop tick, and `flush_report(emit_events=True)` on
    shutdown.
  - `app/paper_run/daily_report.py` — `DailyReportBuilder` accepts
    `strategy_validation_metrics`; the snapshot carries every
    brief-mandated field; the rendered Markdown gains a new
    section, `## Phase 11C.1C-C-B-A Strategy Validation Lab v0 &
    Cluster Exposure Control Contracts`, with a paper / report-only
    boundary preamble.

### Configuration (`app/config/schema.py`, `app/config/defaults.yaml`)

  - `StrategyValidationSection` Pydantic schema with field
    validators on `max_samples`, `overexposure_warning_threshold`,
    `top_symbol_limit`.
  - `defaults.yaml` ships the default block: `enabled: true`,
    `max_samples: 2000`, `primary_window: "5m"`,
    `overexposure_warning_threshold: 3`, `top_symbol_limit: 10`.
  - `Settings.strategy_validation` accessor.

### Daily-report fields

  - `strategy_validation_sample_count`
  - `strategy_validation_sample_created_count`
  - `strategy_validation_report_generated_count`
  - `strategy_mode_validated_count`
  - `candidate_stage_validated_count`
  - `score_bucket_validated_count`
  - `cluster_exposure_assessed_count`
  - `cluster_leader_validated_count`
  - `strategy_mode_validation`
  - `candidate_stage_validation`
  - `opportunity_score_bucket_validation`
  - `early_tail_score_bucket_validation`
  - `strategy_validation_tail_label_distribution`
  - `top_strategy_validation_symbols`
  - `cluster_exposure_assessments`
  - `cluster_leader_validation`
  - `cluster_leader_outperformance_count`
  - `overexposure_warning_count`
  - `strategy_validation_flagged_findings`
  - `strategy_validation_metrics`

The builder cross-checks the runner-side metrics against
`type_counts` from events.db so a stale runner counter cannot
under-report a real validation event.

### Tests (`tests/unit/test_phase11c_1c_c_b_strategy_validation.py`)

25 tests covering every brief-mandated case:

  - `test_strategy_validation_sample_created`
  - `test_runtime_emits_strategy_validation_sample_created`
  - `test_aggregate_by_strategy_mode` (with `observe` + `reject`
    cohorts)
  - `test_aggregate_by_candidate_stage` (with `dumped`)
  - `test_opportunity_score_bucket_validation`
  - `test_early_tail_score_bucket_validation`
  - `test_tail_label_distribution`
  - `test_cluster_leader_validation`
  - `test_cluster_exposure_assessment_leader_only`
  - `test_cluster_exposure_assessment_observe_followers`
  - `test_cluster_exposure_assessment_reject_cluster_when_all_dumped`
  - `test_dumped_stage_is_not_a_long_opportunity`
  - `test_build_strategy_validation_report_empty_samples`
  - `test_observe_and_reject_are_validated_without_trade_authorization`
  - `test_chain_driver_wires_strategy_validation`
  - `test_flush_report_emits_all_event_types`
  - `test_daily_report_contains_strategy_validation_metrics`
  - `test_strategy_validation_events_exportable`
  - `test_replay_reads_strategy_validation_events`
  - `test_replay_handles_missing_schema_version_field`
  - `test_no_live_trading_flags_unchanged`
  - `test_strategy_validation_does_not_trigger_execution`
  - `test_phase_12_remains_forbidden`
  - `test_runtime_disabled_returns_none`
  - `test_max_samples_capacity_bounded`

## Acceptance gate

  - `tests/unit/test_phase11c_1c_c_b_strategy_validation.py` —
    every brief-mandated test passes.
  - `tests/unit -k phase11c_` — full phase 11C suite passes with
    no regression.
  - `tests/` — full pytest passes with no regression.
  - 30 s dry-run smoke produces a `StrategyValidationReport`
    (typically empty in 30 s — the smallest tracking window the
    Phase 11C.1C-C-A runtime opens is 5 min, so a 30 s dry-run
    cannot complete a primary window). The runner explicitly
    logs an "empty Strategy Validation Lab v0 report" line so the
    operator sees the section render correctly even on a short
    smoke.
  - 5 min / 10 min operator-VPS real public WS smoke is
    **required before merge** to confirm the runtime emits real
    `STRATEGY_VALIDATION_SAMPLE_CREATED` events for at least one
    completed primary 5 min window. The Kiro-side sandbox cannot
    host this smoke (Binance-region HTTP 451 geoblock; same as the
    Phase 11C.1C-B / Phase 11C.1C-C-A closeouts).

## Why this phase is paper / report only

  - The Strategy Validation Lab v0 builds **descriptive cohort
    statistics**. The `suggested_cluster_action` it produces is one
    of `leader_only` / `observe_followers` / `reject_cluster` /
    `no_action` — these are paper labels for a human reviewer; they
    do not flip a Phase 1 safety flag, never call the Risk Engine
    with a different request, and never authorise a real trade.
  - Validation samples live in events.db and the daily report
    Markdown body. The Phase 8.5 export and the Phase 10A replay
    can carry them forward without changes; nothing about how an
    order is submitted, validated, or stopped is altered.
  - Every threshold is configurable through
    `app/config/defaults.yaml::strategy_validation`; an operator
    can raise `overexposure_warning_threshold` or shrink the
    sample buffer without touching code.

## Why this is **NOT** the complete Strategy Validation Lab

  - **NO** auto-tuning of the adaptive scoring weights.
  - **NO** reinforcement learning.
  - **NO** richer correlation analysis beyond simple cohort
    averages and counts.
  - **NO** smarter cluster taxonomy than the Phase 11C.1C-A
    quote-asset clustering. Cluster narratives / sectors /
    leaders are still derived from the existing
    `ClusterContext`; deeper cluster heuristics are reserved for a
    later PR.
  - **NO** schema-stable contract migration story; the schema
    version label
    (`phase_11c_1c_c_b_a.strategy_validation.v1`) explicitly marks
    this as v0 / v1 of the contract so the next PR can bump it.

## Why Phase 12 remains FORBIDDEN

Phase 11C.1C-C-B-A acceptance does **NOT** authorise live trading,
API keys, private endpoints, DeepSeek trade decisions, real Telegram
outbound, or Phase 12. The Phase 1 safety lock in
`app/config/settings.py::_apply_phase1_safety_lock` continues to
hard-coerce the first five flags. The Phase 11C
`MarketDataConfig` and `SafetyConfig` schemas refuse to load any
deployment that flips a `forbid_*` flag. Spec §41 Go/No-Go remains
the only path forward and has not been initiated.
