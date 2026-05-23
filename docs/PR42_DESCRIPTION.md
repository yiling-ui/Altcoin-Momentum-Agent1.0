# PR #42 — Phase 11C.1C-C-B-A: Strategy Validation Lab v0 & Cluster Exposure Control Contracts

> **Status: IN_REVIEW (PR #42 open).** **NOT** ACCEPTED yet.
> **NOT** live trading. **NOT** AI Learning. **NOT** the complete
> Strategy Validation Lab. **NOT** automatic parameter
> optimisation. **NOT** Phase 12.
>
> Phase 11C.1C-C-A — *MFE / MAE Label Queue Runtime & Tail Outcome
> Tracking* — merged on 2026-05-23 (PR #40, mergeCommit `75d3c7c`)
> and is the gating predecessor. Phase 11C.1C-C-B-A is the **first
> slice** of the deeper Phase 11C.1C-C-B Strategy Validation Lab
> work; it ships only the data contracts + pure aggregators + the
> runtime that emits the seven typed events.
>
> **Operator-VPS 10 min real public WS smoke PASSED.** The
> operator ran the smoke from a Binance-reachable VPS against the
> PR #42 head (commit `0bedcce`) and the verbatim evidence is
> backfilled below under "Real WS smoke (operator-VPS 10 min,
> PASSED)" and under `docs/PHASE_GATE.md` §"Phase 11C.1C-C-B-A
> acceptance evidence (operator-VPS 10 min real public WS smoke
> PASSED)". **PR #42 is ready for human review and may be merged
> after reviewer confirms docs-only evidence backfill.** Phase
> 11C.1C-C-B-A flips to ACCEPTED only after PR #42 merges, via
> the standard closeout PR pattern (mirroring PR #36 → PR #37,
> PR #38 → PR #39, PR #40 → PR #41); this PR does **NOT**
> self-flip the phase to ACCEPTED.

## Phase

  - **Phase 11C.1C-C-B-A** — paper-only Strategy Validation Lab v0
    + Cluster Exposure Control Contracts on top of the Phase
    11C.1C-C-A `LabelTrackingRecord` outcomes. **IN_REVIEW.**
  - **Phase 11C.1C-C-B-B** — `RESERVED / NOT_STARTED`. Reserved
    for the deeper Lab follow-up (richer cohort comparisons,
    extended cluster heuristics, longer-window correlations). NOT
    authorised by Phase 11C.1C-C-B-A acceptance bypassing the
    standard gate.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock unchanged.

## Branch + commit

  - Branch: `feature/phase-11c1c-c-b-strategy-validation-cluster-control`
  - Targets: `main` (post PR #41 docs closeout, post PR #40 Phase
    11C.1C-C-A merge).

## What ships

The full per-phase brief, including scope, boundary, forbidden
items, and acceptance gate, lives in
`docs/PHASE_11C_1C_C_B_STRATEGY_VALIDATION_CLUSTER_CONTROL.md`.
Headline:

  - `app/adaptive/strategy_validation.py` (NEW) — every
    Phase 11C.1C-C-B-A data contract + pure aggregator:
    `StrategyValidationSample`, `StrategyValidationWindowStats`,
    `StrategyModeValidationStats`, `CandidateStageValidationStats`,
    `OpportunityScoreBucketStats`,
    `EarlyTailScoreBucketStats`, `TailLabelDistribution`,
    `ClusterLeaderValidationStats`, `ClusterExposureAssessment`,
    `StrategyValidationReport`. Pure functions:
    `build_strategy_validation_sample`,
    `aggregate_by_strategy_mode`,
    `aggregate_by_candidate_stage`,
    `aggregate_by_opportunity_score_bucket`,
    `aggregate_by_early_tail_score_bucket`,
    `aggregate_tail_label_distribution`,
    `evaluate_cluster_leader_performance`,
    `assess_cluster_exposure`,
    `build_strategy_validation_report`. Schema version label:
    `phase_11c_1c_c_b_a.strategy_validation.v1`.
  - `app/adaptive/strategy_validation_runtime.py` (NEW) — paper /
    report-only runtime. `StrategyValidationRuntimeConfig` with
    every threshold configurable; `StrategyValidationRuntime` owns
    the in-process sample buffer (idempotent per `opportunity_id`)
    and emits the seven typed events.
  - `app/adaptive/__init__.py` — exposes the new contracts +
    aggregators + runtime.
  - `app/core/events.py` — seven new `EventType` values:
    `STRATEGY_VALIDATION_SAMPLE_CREATED`,
    `STRATEGY_VALIDATION_REPORT_GENERATED`,
    `STRATEGY_MODE_VALIDATED`, `CANDIDATE_STAGE_VALIDATED`,
    `SCORE_BUCKET_VALIDATED`, `CLUSTER_EXPOSURE_ASSESSED`,
    `CLUSTER_LEADER_VALIDATED`. Every payload carries
    `schema_version`, identity (`opportunity_id` / `report_id` /
    `scan_batch_id` / `symbol`), `timestamp`, and the four
    versioning fields (`strategy_version`, `scoring_version`,
    `risk_config_version`, `state_machine_version`) plus
    `validation_version` and `source_phase`.
  - `app/config/schema.py` — `StrategyValidationSection` Pydantic
    schema with field validators on `max_samples`,
    `overexposure_warning_threshold`, `top_symbol_limit`. Wired
    into `DefaultsConfig`.
  - `app/config/defaults.yaml` — new `strategy_validation:` block
    with paper / report-only boundary preamble.
  - `app/config/settings.py` — `Settings.strategy_validation`
    accessor.
  - `app/market_data_public/ws_radar_chain.py` —
    `WSRadarChainDriver` accepts a new
    `strategy_validation_runtime` kwarg. After the Phase 11C.1C-A
    `LABEL_QUEUE_ENQUEUED` lands and the Phase 11C.1C-C-A
    `LabelQueueRuntime.observe(...)` returns the
    `LabelTrackingRecord`, the chain calls
    `runtime.observe_label_record(label_record, adaptive,
    source_event_id, sample_created_ts)`.
  - `app/paper_run/daily_report.py` — `DailyReportSnapshot` +
    `DailyReportBuilder` extended with the new fields and
    section. The Markdown gains
    `## Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster
    Exposure Control Contracts` with a paper / report-only
    boundary preamble, headline counts, per-mode / per-stage /
    per-bucket cohort lines, tail-label distribution, top symbols,
    cluster exposure assessments (showing
    `suggested_cluster_action`), cluster leader validation, and
    flagged findings.
  - `scripts/run_public_market_paper.py` — instantiates
    `StrategyValidationRuntime` from
    `settings.strategy_validation`, snapshots metrics on every
    loop tick, and `flush_report(emit_events=True)` on shutdown.
    `_Phase11CRunStats` carries `strategy_validation_metrics`.
  - `tests/unit/test_phase11c_1c_c_b_strategy_validation.py`
    (NEW, 25 tests) — covers every brief-mandated case.
  - `tests/unit/test_phase11b_no_network.py` — allow-list updated
    with the seven new event types.
  - `docs/PHASE_11C_1C_C_B_STRATEGY_VALIDATION_CLUSTER_CONTROL.md`
    (NEW) — full per-phase brief.
  - `docs/PR42_DESCRIPTION.md` (NEW) — this file.
  - `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md` — phase-state write-throughs.

## What does **NOT** ship

  - **NOT** the complete Strategy Validation Lab (reserved for
    Phase 11C.1C-C-B-B and beyond).
  - **NOT** auto-tuning of adaptive scoring weights.
  - **NOT** reinforcement learning.
  - **NOT** richer cluster taxonomy than Phase 11C.1C-A's
    quote-asset clusters.
  - **NOT** any change to the Risk Engine (it remains the single
    trade-decision gate).
  - **NOT** any private API integration, signed endpoint, listenKey,
    or live trading.
  - **NOT** Telegram outbound, real DeepSeek trade decisions, or
    AI / LLM-driven direction / sizing / leverage / stop / target
    decisions.
  - **NOT** Phase 12.

## Safety boundary (Phase 1 lock unchanged)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

  - **NO** Binance API key / secret loaded.
  - **NO** signed endpoint / private WS / listenKey.
  - **NO** account / order / position / leverage / margin endpoint.
  - **NO** DeepSeek trade decision; **NO** real Telegram outbound.
  - **NO** Phase 12.

The Strategy Validation Lab v0 runtime emits ONLY the seven new
descriptive events. It NEVER emits `ORDER_*`, `POSITION_*`,
`STOP_*`, `EXIT_TRIGGERED`, or `TELEGRAM_MESSAGE_SENT`. The
`suggested_cluster_action` field on every
`ClusterExposureAssessment` is one of `leader_only` /
`observe_followers` / `reject_cluster` / `no_action` — paper labels
for a human reviewer; **MUST NEVER trigger a real trade**. The
Risk Engine remains the single trade-decision gate.

## Tests run

  - `python -m pytest tests/unit/test_phase11c_1c_c_b_strategy_validation.py -q`
    → **25 / 25 PASS** (1 warning, unrelated `asyncio_mode`).
  - `python -m pytest tests/unit/ -k "phase11c_" -q`
    → **312 / 312 PASS** (287 baseline + 25 new). No regression.
  - `python -m pytest tests/ -q`
    → **2286 / 2286 PASS** (2261 baseline + 25 new). No regression.

## Dry-run summary

A 30 s dry-run on the Phase 11C runner is intentionally a
**contract-only** smoke for Phase 11C.1C-C-B-A. The Phase 11C.1C-C-A
runtime opens its smallest tracking window at 5 minutes, so a 30 s
run cannot complete a primary window — and therefore cannot
generate a real `StrategyValidationSample`. The 30 s smoke
verifies:

  - the runner boots cleanly with the new
    `strategy_validation` settings block;
  - `WSRadarChainDriver` is constructed with the new
    `strategy_validation_runtime` kwarg without exception;
  - `metrics_payload()` returns an empty-but-well-formed dict so
    the daily-report builder can render the new section with the
    "(no samples in this window; empty Strategy Validation Lab v0
    report)" line;
  - on shutdown, `flush_report(emit_events=True)` emits one
    `STRATEGY_VALIDATION_REPORT_GENERATED` event with
    `sample_count=0`.

## Real WS smoke (operator-VPS 10 min, PASSED)

The 10 min operator-VPS real public WS smoke **PASSED** on
2026-05-23 against the PR #42 head (commit `0bedcce`,
branch `feature/phase-11c1c-c-b-strategy-validation-cluster-control`).
The Kiro-side sandbox cannot host this smoke (Binance-region
HTTP 451 geoblock — same historical reason previously recorded
for the Phase 11C.1C-B and Phase 11C.1C-C-A closeouts; this is
**not** the current blocker), so the operator ran it from a
Binance-reachable VPS. The verbatim transcript is also filed
under `docs/PHASE_GATE.md` §"Phase 11C.1C-C-B-A acceptance
evidence (operator-VPS 10 min real public WS smoke PASSED)".

### Command actually used

```
python -m scripts.run_public_market_paper \
    --duration 10min \
    --symbol-limit 5 \
    --ws-first
```

> **Note on `--emit-banner`.** The runner does **not** support
> `--emit-banner`. The banner is emitted **by default**; pass
> `--no-banner` only if you want to suppress it. Earlier drafts
> of this document referenced `--emit-banner`; that flag was
> never on the runner and the operator-VPS smoke uses the actual
> command above.

### Runner-level numerics (PASS)

```
duration_seconds                = 600.0
uptime                          = 611s
dry_run                         = false
ws_real_transport               = true
ws_messages_received            = 76324
ws_chains_emitted               = 27
learning_ready_attached         = 27
snapshots_emitted               = 27
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
rate_limit_ban                  = False
ws_reconnect_count              = 0
ws_stale_count                  = 0
ws_currently_stale              = False
```

### Strategy Validation events (authoritative, from SQLite)

The authoritative source for the new event counts is the
`events.db` SQLite query against
`SELECT event_type, COUNT(*) FROM events GROUP BY event_type`,
captured **after** shutdown flush:

```
STRATEGY_VALIDATION_SAMPLE_CREATED       | 24
STRATEGY_VALIDATION_REPORT_GENERATED     |  1
STRATEGY_MODE_VALIDATED                  |  4
CANDIDATE_STAGE_VALIDATED                |  5
SCORE_BUCKET_VALIDATED                   |  8
CLUSTER_EXPOSURE_ASSESSED                |  1
CLUSTER_LEADER_VALIDATED                 |  1
```

> **Important note on the daily report's top event-count
> lines.** The daily report's top event-count lines may show
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_*` counts as **0**
> because those event counters appear to be snapshotted
> **before** shutdown flush. The **authoritative** event
> repository SQLite query (above) confirms those events were
> emitted. The daily report **section itself** rendered the
> Strategy Validation cohorts non-empty and correctly. This
> snapshot-vs-flush gap is a daily-report instrumentation
> nuance that does **not** invalidate the smoke; the SQLite
> ground truth is conclusive. A future daily-report polish
> can move the counter snapshot after the shutdown flush; it
> is **not** in scope for Phase 11C.1C-C-B-A.

### Daily report content (PASS)

The daily report Markdown contains the new Phase 11C.1C-C-B-A
section:

```
Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster Exposure Control Contracts
```

with non-empty cohort lines confirmed for the 10 min run:

```
strategy_mode=reject                  n=24
candidate_stage=early                 n=24
opportunity_score_bucket=0-49         n=13
opportunity_score_bucket=50-64        n=11
early_tail_score_bucket=0-24          n=24
cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action
```

`tail_label_distribution`:

```
unresolved x 24
```

(The 5 min primary tracking windows that opened during the
10 min run had not all completed by the time of shutdown, so
`unresolved` is the expected dominant label for a 10 min run;
`STRATEGY_VALIDATION_SAMPLE_CREATED = 24` confirms the runtime
fired.)

### Safety (PASS — Phase 1 lock unchanged end-to-end)

```
exchange_live_order_enabled     = False
live_trading_enabled            = False
llm_enabled                     = False
right_tail_enabled              = False
trading_mode_paper              = True
no live trading                 : confirmed
no API key                      : confirmed
no signed endpoint              : confirmed
no private websocket            : confirmed
no listenKey                    : confirmed
no DeepSeek trade decision      : confirmed
no real Telegram outbound       : confirmed
Phase 12                        : remains FORBIDDEN
```

### Acceptance criteria — every gate met

  - `dry_run = false` ✅
  - `ws_real_transport = true` ✅
  - `ws_messages_received = 76324` (≥ 5000) ✅
  - `ws_chains_emitted = 27` (≥ 1) ✅
  - `STRATEGY_VALIDATION_SAMPLE_CREATED = 24` (≥ 1) ✅
  - `STRATEGY_VALIDATION_REPORT_GENERATED = 1` (≥ 1) ✅
  - `STRATEGY_MODE_VALIDATED = 4` ✅ (the four canonical modes
    `follow` / `pullback` / `observe` / `reject` are emitted
    even when a cohort is empty — observed `reject` cohort
    `n=24`)
  - `CANDIDATE_STAGE_VALIDATED = 5` ✅
  - `SCORE_BUCKET_VALIDATED = 8` ✅
  - `CLUSTER_EXPOSURE_ASSESSED = 1` ✅
  - `CLUSTER_LEADER_VALIDATED = 1` ✅
  - Daily report contains the new Phase 11C.1C-C-B-A section
    with non-empty `strategy_mode` and `candidate_stage`
    cohort lines ✅
  - Safety flags unchanged ✅
  - `HTTP 429 count = 0`, `HTTP 418 count = 0`,
    `rate_limit_ban = False` ✅
  - `ws_reconnect_count = 0`, `ws_stale_count = 0`,
    `ws_currently_stale = False`, `ingestion_errors = 0` ✅

## Safety boundary confirmation

  - Phase 1 safety lock invariants — `mode=paper`,
    `live_trading=False`, `right_tail=False`, `llm=False`,
    `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False` — all confirmed by
    `test_no_live_trading_flags_unchanged` in the new test file.
  - The validation runtime never emits any trading event
    (`ORDER_*`, `POSITION_*`, `STOP_*`, `EXIT_TRIGGERED`,
    `TELEGRAM_MESSAGE_SENT`) — confirmed by
    `test_strategy_validation_does_not_trigger_execution`.
  - `suggested_cluster_action` vocabulary is restricted to four
    paper / report-only values — confirmed by the runtime config
    schema + `test_phase_12_remains_forbidden`.
  - Phase 12 remains FORBIDDEN — confirmed by
    `test_phase_12_remains_forbidden`.

## Remaining risk

  - The cluster taxonomy is still the Phase 11C.1C-A
    quote-asset-only classifier, so cluster cohorts in production
    will be coarse (e.g. every `*USDT` perp lands in one cluster).
    The Lab v0 still produces a meaningful per-cluster summary, but
    the deeper "narrative-aware" cluster heuristics are reserved
    for a later PR.
  - Validation cohorts can be sparse for short runs. The
    `flagged_findings` heuristic uses a 20% rate threshold, so
    cohorts with <5 samples may not flip a flag even when the
    underlying signal is meaningful. Operators reviewing short runs
    should consult the per-cohort cohort lines directly.
  - **Daily-report counter snapshot timing.** The daily report's
    top event-count lines may show
    `STRATEGY_VALIDATION_REPORT_GENERATED` /
    `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
    `SCORE_BUCKET_VALIDATED` / `CLUSTER_*` counts as **0**
    because those event counters appear to be snapshotted
    **before** shutdown flush. The authoritative event repository
    SQLite query confirms those events were emitted (see "Real WS
    smoke (operator-VPS 10 min, PASSED)" above). The daily report
    section itself rendered the Strategy Validation cohorts
    correctly. A future daily-report polish can move the counter
    snapshot after the shutdown flush; it is **not** in scope for
    Phase 11C.1C-C-B-A.

## Whether PR is ready for human review

**Yes.** Every brief-mandated test passes; the full pytest suite
shows no regression vs. the post-PR-#41 main baseline; the new
section renders correctly in the daily-report Markdown body; the
Phase 1 safety lock is unchanged; Phase 12 remains FORBIDDEN. The
**operator-VPS 10 min real public WS smoke PASSED** (commit
`0bedcce`; verbatim evidence backfilled above) and confirms the
runtime emits real `STRATEGY_VALIDATION_SAMPLE_CREATED` /
`STRATEGY_VALIDATION_REPORT_GENERATED` /
`STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
`SCORE_BUCKET_VALIDATED` / `CLUSTER_EXPOSURE_ASSESSED` /
`CLUSTER_LEADER_VALIDATED` events end-to-end on real Binance
public WS data. **PR #42 is ready for human review and may be
merged after reviewer confirms the docs-only evidence
backfill.** This PR does **not** flip Phase 11C.1C-C-B-A to
ACCEPTED; the standard closeout PR (mirroring PR #36 → PR #37,
PR #38 → PR #39, PR #40 → PR #41) records ACCEPTED only after
PR #42 has merged. Phase 11C.1C-C-B-B remains **NOT_STARTED**;
Phase 12 remains **FORBIDDEN**.
