# Phase 11C.1C-C-B-B-A — Strategy Validation Dataset Builder & Quality Gate v0

> **Status: ACCEPTED (closed 2026-05-23; PR #44 merged into
> `main`, mergeCommit `3ecfc3b`).**
>
> **Phase 11C.1C-C-B-B-A is paper / report only.** **NOT** live
> trading. **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** the
> complete Strategy Validation Lab follow-up
> (Phase 11C.1C-C-B-B-B). **NOT** the Paper Alpha Gate v0.
> **NOT** Phase 12.
>
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live
> trading, API keys, private endpoints, DeepSeek trade
> decisions, real Telegram outbound, Phase 11C.1C-C-B-B-B
> kickoff bypassing the standard gate, the Paper Alpha Gate
> v0, the complete Strategy Validation Lab follow-up, AI
> Learning, automatic parameter optimisation, reinforcement
> learning, or Phase 12.**
>
> The Risk Engine remains the single trade-decision gate. The
> ``validation_quality_gate_status`` produced by this slice
> (``pass`` / ``warn`` / ``fail``) is a **descriptive label**
> for human review and **MUST NEVER trigger a real trade**.
> ``validation_quality_gate_status=fail`` is the **expected**
> output for the low-sample 30 s dry-run because the smallest
> Phase 11C.1C-C-A primary tracking window is 5 minutes and
> samples that landed in the 30 s window are necessarily
> in-flight / unresolved.

## Phase boundary

  - **Phase 11C.1C-C-B-A** — `ACCEPTED` (PR #42 merged into
    `main`, 2026-05-23, mergeCommit `cc18047`). Ships the
    Strategy Validation Lab v0 contracts + aggregators + the
    runtime that emits the seven typed events.
  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 merged into
    `main`, 2026-05-23, mergeCommit `3ecfc3b`). Ships the
    Strategy Validation Dataset Builder & Quality Gate v0 on
    top of the Phase 11C.1C-C-B-A
    `StrategyValidationSample` / `StrategyValidationReport` /
    `ClusterExposureAssessment` artefacts. Three new typed
    events. The dataset is exportable + replayable +
    auditable. The quality gate is a *sample trust* gate, not
    a *strategy quality* gate.
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    Reserved for the deeper Strategy Validation Lab follow-up
    (richer cohort comparisons, extended cluster heuristics,
    longer-window correlations, dataset-driven retrospective
    audits). Phase 11C.1C-C-B-B-A acceptance does NOT
    authorise Phase 11C.1C-C-B-B-B kickoff bypassing the
    standard gate; will require its own kickoff PR, brief,
    scope, boundary table, forbidden list, and acceptance
    evidence.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock unchanged.

## What ships

### 1. New module — `app/adaptive/strategy_validation_dataset.py`

Pure-function module. Models:

  - `StrategyValidationDatasetRecord` — one row per Phase
    11C.1C-C-B-A `StrategyValidationSample` carrying every
    brief-mandated field (`report_id`, `opportunity_id`,
    `scan_batch_id`, `symbol`, `candidate_stage`, `strategy_mode`,
    `opportunity_score`, `early_tail_score`, `late_chase_risk`,
    `cluster_id`, `cluster_leader`, `tail_label`, per-window
    `mfe_5m / mae_5m / … / mfe_4h / mae_4h`, R-multiple flags,
    outcome flags, `source_event_id`, `schema_version`).
  - `StrategyValidationDatasetSummary` — record / completed /
    symbols / per-mode / per-stage / per-bucket / tail-label
    counts.
  - `StrategyValidationDataset` — top-level container (records +
    summary + report identity + version labels + schema_version).
  - `StrategyValidationQualityGate` — gate thresholds.
  - `StrategyValidationQualityGateResult` — gate output.

Pure functions:

  - `build_validation_dataset_from_samples(samples, *, report_id,
    generated_at_ms, source_event_ids=None, …)` → builds a
    `StrategyValidationDataset` from Phase 11C.1C-C-B-A samples.
    No I/O.
  - `summarize_validation_dataset(records)` → builds the summary.
    No I/O.
  - `evaluate_validation_dataset_quality(dataset, *, gate=None)` →
    `StrategyValidationQualityGateResult` (pass / warn / fail).
    No I/O.
  - `export_validation_dataset_payload(dataset)` → JSON-safe dict.
    No disk write; the runner is responsible for serialising the
    bytes.
  - `load_validation_dataset_payload(payload)` → reconstructs a
    `StrategyValidationDataset`. Tolerates missing optional fields
    (legacy / future payloads).

### 2. Quality gate v0 thresholds

The gate is a *sample trust* gate. It does NOT judge whether the
strategy is profitable. The default thresholds:

  - `min_total_samples = 20`
  - `min_completed_tail_labels = 10`
  - `min_strategy_mode_coverage = 2`  (out of follow / pullback /
    observe / reject)
  - `min_candidate_stage_coverage = 2`  (out of early / mid /
    late / blowoff / dumped)
  - `min_score_bucket_coverage = 2`  (out of 0-49 / 50-64 /
    65-79 / 80-100)
  - `require_export_roundtrip = True`
  - `require_replay_readable = True`

Output:

  - `gate_status`: `pass` / `warn` / `fail` (descriptive label
    only — **NEVER** an input to a trade-decision pipeline).
  - `reasons`: tuple of human-readable reason tags.
  - `sample_count`, `completed_tail_label_count`.
  - `missing_modes`, `missing_stages`, `missing_buckets`,
    `missing_required_fields`.
  - `export_roundtrip_ok`, `replay_readable`.

Status hierarchy:

  - `fail` — structural integrity broken (required field
    missing, export round-trip broken when required, dataset
    not replay-readable when required, sample count below half
    `min_total_samples`).
  - `warn` — acceptable structurally but coverage / sample count
    below thresholds.
  - `pass` — every threshold met.

### 3. New event types

Three new typed events emitted through `EventRepository` with the
brief-mandated identity block (`report_id`, `timestamp`,
`strategy_version`, `scoring_version`, `risk_config_version`,
`state_machine_version`, `schema_version`):

  - `STRATEGY_VALIDATION_DATASET_BUILT`
  - `STRATEGY_VALIDATION_DATASET_EXPORTED`
  - `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`

Schema version: `phase_11c_1c_c_b_b_a.strategy_validation_dataset.v1`.

### 4. Daily report

The Phase 11B daily report carries a new section
"Phase 11C.1C-C-B-B-A Strategy Validation Dataset Builder &
Quality Gate v0" with:

  - `STRATEGY_VALIDATION_DATASET_BUILT` count (event-log +
    runner counter cross-check).
  - `STRATEGY_VALIDATION_DATASET_EXPORTED` count.
  - `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` count.
  - `validation_dataset_records`, `validation_dataset_symbols`,
    `validation_dataset_tail_label_counts`.
  - `validation_quality_gate_status`,
    `validation_quality_gate_reasons`.
  - `validation_dataset_export_ready`,
    `validation_dataset_replay_ready`.

The Markdown body explicitly disclaims the descriptive nature of
`gate_status` and reiterates **Phase 12 remains FORBIDDEN**.

### 5. Export / replay

The Phase 8.5 export bundle `events.jsonl` carries the three new
event types automatically (the export service streams every row
from events.db). The Phase 10A replay engine accepts the rows
without raising; legacy / future rows missing `schema_version` are
tolerated.

### 6. Runtime configuration

The Phase 11C.1C-C-B-A `StrategyValidationRuntimeConfig` is
extended with a `dataset_enabled` flag and the seven
`quality_gate_*` thresholds. Defaults match the
`StrategyValidationQualityGate` defaults. The runner reads the
values from `app/config/defaults.yaml > strategy_validation`.
Setting `dataset_enabled: false` disables the new slice without
affecting the Phase 11C.1C-C-B-A Lab v0 contracts.

## What does NOT ship

  - **Real trading**. The dataset / gate slice is paper / report
    only. No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event is ever
    emitted by this slice.
  - **AI Learning** (Phase 12). FORBIDDEN.
  - **Automatic parameter optimisation**. FORBIDDEN.
  - **Reinforcement learning**. FORBIDDEN.
  - **Complete Strategy Validation Lab follow-up
    (Phase 11C.1C-C-B-B-B)**. Reserved for the next gate.
  - **Profitability judgement**. The gate is a *sample trust*
    gate; whether the strategy makes money is out of scope.
  - **Trade decisions driven by gate status**. The Risk Engine
    remains the single trade-decision gate. `gate_status` cannot
    enable / disable orders.

## Real-WS smoke not required for this PR

The Phase 11C.1C-C-B-B-A scope is **dataset / quality-gate
contract**. The smallest Phase 11C.1C-C-A primary tracking window
is 5 minutes; a 30 s dry-run cannot complete a primary window and
therefore cannot produce a non-empty dataset. The brief asks the
PR to surface an *empty-but-well-formed* quality-gate report under
the 30 s smoke; that is what ships. A real public WS 10-minute
smoke is reserved for the Phase 11C.1C-C-B-B-B closeout when
non-empty datasets are first observable end-to-end.

## Safety boundary (held end-to-end)

```
mode                            = paper
live_trading_enabled            = False
exchange_live_order_enabled     = False
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
Phase 12                        = FORBIDDEN
```

## Tests

  - `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`
    — 27 brief-mandated cases (record contract, builder, summary,
    quality gate pass/warn/fail, export round-trip, replay,
    daily-report integration, safety boundary, Phase 12 forbidden).
  - `tests/unit/test_phase11b_no_network.py` —
    `test_phase11b_event_emission_does_not_invent_new_event_types`
    extended to allow the three new event types.
  - Full pytest run: 2313 passed (2286 baseline + 27 new). No
    regression.
  - `tests/unit/ -k phase11c_` filter: 339 passed (312 baseline +
    27 new).

## Dry-run smoke (30 s)

```
2026-05-23 09:25:58 dry-run start
2026-05-23 09:26:58 dry-run finish (60 s elapsed including teardown)

dry_run                         = True
ws_real_transport               = False
chains_emitted                  = 2
ws_chains_emitted               = 2
risk_approved                   = 0
risk_rejected                   = 2
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
rate_limit_ban                  = False
ws_reconnect_count              = 0
ws_stale_count                  = 0

# Phase 11C.1C-C-B-B-A daily report (empty / low-sample)
STRATEGY_VALIDATION_DATASET_BUILT count       = 1
STRATEGY_VALIDATION_DATASET_EXPORTED count    = 1
STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED    = 1
validation_dataset_records                     = 2
validation_dataset_symbols                     = 2
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
exchange_live_order_enabled     = False
live_trading_enabled            = False
trading_mode_paper              = True
```

`gate_status=fail` is the **expected** output for a 30 s dry-run:
the smallest Phase 11C.1C-C-A tracking window is 5 minutes, so the
samples that landed in the 30 s window are necessarily
in-flight / unresolved. The quality gate correctly classifies the
dataset as too thin for downstream review — exactly the brief's
"empty or low-sample quality gate report" requirement.

## Forbidden by this PR

  - Live trading (`live_trading_enabled=False` cannot flip to
    `True`).
  - Binance private API / signed endpoint / listenKey / private
    WebSocket.
  - LLM / DeepSeek trade decision.
  - Real Telegram outbound.
  - Right-tail score in production scope (Phase 1 safety lock).
  - Validation result triggering real downstream execution.
  - AI deciding direction / position size / leverage / stop-loss /
    target / execution.
  - Automatic parameter optimisation.
  - Reinforcement learning.
  - Risk Engine override (the Risk Engine remains the single
    trade-decision gate).
  - Phase 11C.1C-C-B-B-B implementation.
  - Phase 12 / live trading kickoff.
