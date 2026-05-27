# Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0

> *发现后结果度量 v0*

**Status: IN_REVIEW (after the implementation PR; not `ACCEPTED`
until evidence closeout).**

This document is the canonical brief for the Post-Discovery
Outcome Metrics v0 layer. It is **paper / report / evidence
only** and grants **no trade authority**.

## Purpose

Phase 11C.1C-C-B-B-B-D-A only describes the *discovery* layer:

  - did the system see the mover?
  - when was the first sighting?
  - how deep did the capture path go?
  - if missed, why?

D-A acceptance only means the coverage-audit toolchain works.
**D-A does NOT prove discovery quality. D-A does NOT prove
strategy profitability. D-A does NOT solve direction
classification. D-A does NOT authorise live trading. D-A does
NOT authorise automatic parameter tuning.**

Phase 11C.1C-C-B-B-B-D-B answers the *next* question:

> Once the system first saw a mover, **how much room remained
> to be captured**? Was the first sighting **early**, **late**,
> **choppy**, **fake breakout**, **late reversal**, or **missed
> strong tail**?

D-B turns the manual K-line cross-check the operator was doing
into a structured, exportable, replayable, auditable set of
**outcome metrics + closed labels**. It does **not** trade. It
does **not** tune anything. It does **not** issue direction
calls (long / short / entry / exit / stop / target / position
size / leverage).

## Inputs

`PostDiscoveryOutcomeInput` (one per audited mover):

  - `symbol`
  - `reference_window`
  - `first_seen_time_utc_ms` (the timestamp of the event that
    *already existed* at audit time - **MUST NOT** be derived
    from a future return / completed tail label / settled
    outcome)
  - `first_seen_event_type` (e.g. `MARKET_SNAPSHOT`,
    `ANOMALY_DETECTED`, `LABEL_QUEUE_ENQUEUED`)
  - `first_seen_price`
  - `price_path_after_first_seen` (sequence of `PricePoint`
    observations *after* the first sighting; the evaluator
    never fabricates a price)
  - `historical_mover_reference` (a
    `HistoricalMoverReferenceSummary` that carries the prior
    high anchor, the reference peak, and the reference window's
    max gain - it is the post-hoc reference set produced by
    Phase 11C.1C-C-B-B-B-D-A; the audit MUST NOT use it to
    rewrite past decisions)
  - `capture_status` (one of `captured` / `partially_captured`
    / `missed` / `excluded`, mirrors D-A)
  - `capture_path_depth`
  - `evidence_refs` (links back to the originating D-A audit
    records)

## Outputs

`PostDiscoveryOutcomeRecord` (one per audited mover):

  - `symbol`, `reference_window`
  - `first_seen_time_utc_ms`, `first_seen_event_type`,
    `first_seen_price`
  - `prior_high_time_utc_ms`, `prior_high_price`,
    `distance_to_prior_high_pct`
  - `post_seen_high_time_utc_ms`, `post_seen_high_price`
  - `post_seen_low_time_utc_ms`, `post_seen_low_price`
  - `remaining_upside_to_peak_pct`, `post_seen_drawdown_pct`,
    `mfe_pct`, `mae_pct`, `time_to_peak_seconds`
  - `detection_timing_label`
  - `outcome_label`
  - `capture_status`, `capture_path_depth`
  - `evidence_refs`, `warnings`
  - `schema_version`, `source_phase`

`PostDiscoveryOutcomeReport` (one per evaluation batch):

  - `reference_window`
  - `total_records`
  - `early_count`, `late_count`,
    `missed_strong_tail_count`,
    `fake_breakout_count`,
    `insufficient_data_count`
  - `median_remaining_upside_pct`,
    `median_mfe_pct`, `median_mae_pct`
  - `detection_timing_label_summary` (label -> count)
  - `outcome_label_summary` (label -> count)
  - `records`, `warnings`, `evidence_refs`
  - `schema_version`, `source_phase`

## Event types

Two new typed events are emitted - **paper / report / evidence
only**:

  - `EventType.POST_DISCOVERY_OUTCOME_EVALUATED` - one per
    evaluated mover. Carries the descriptive labels + metrics +
    `evidence_refs`.
  - `EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED` - one
    per evaluation batch. Carries the aggregate counts +
    medians.

Both payloads:

  - are deterministic + closed (every dict written by the
    module passes a recursive `assert_payload_has_no_forbidden_keys`
    guard);
  - carry a `schema_version` + `source_phase` so old payloads
    remain replayable verbatim;
  - carry `evidence_refs` linking back to the originating D-A
    audit record.

## Labels

`detection_timing_label` (closed enum):

  - `EARLY` - first sighting well below peak; meaningful upside
    remains.
  - `EARLY_BUT_CHOPPY` - first sighting early, but mid-window
    drawdown is non-trivial relative to the upside leg.
  - `MID_MOVE` - somewhere in between.
  - `LATE` - first sighting close to peak; little upside
    remains.
  - `TOO_LATE` - essentially at the peak.
  - `MISSED` - the system never saw the mover.
  - `INSUFFICIENT_DATA` - missing first_seen_price or
    insufficient post-first-seen path to classify.

`outcome_label` (closed enum):

  - `EARLY_CONTINUATION` - early sighting that kept running
    without giving back most of the gain.
  - `EARLY_BUT_CHOPPY` - early sighting that ran but with a
    significant adverse leg.
  - `LATE_TOP_CHASE` - late sighting that still ran a little.
  - `LATE_REVERSAL` - late sighting that reversed adversely.
  - `MISSED_STRONG_TAIL` - missed mover whose reference
    recorded a meaningful tail; severe-miss signal for later
    triage.
  - `FAKE_BREAKOUT` - first sighting briefly made a new high
    then gave back most of the gain.
  - `DUMPED` - no upside leg observed; meaningful drawdown
    after first sighting.
  - `EXHAUSTION_CANDIDATE` - first sighting essentially at peak
    with no further movement; descriptive only - **not** a
    direction call.
  - `NO_CLEAR_EDGE` - none of the above clearly applies.
  - `INSUFFICIENT_PRICE_PATH` - missing first_seen_price or
    insufficient post-first-seen path.

Both label sets are **descriptive only**. Neither is an input
to a trade-decision pipeline. Neither modifies any runtime knob.

## Acceptance criteria

  1. `tests/unit/test_post_discovery_outcome_metrics.py`
     passes, covering at least:
       1. early continuation
       2. early but choppy
       3. late top chase
       4. late reversal
       5. missed strong tail
       6. fake breakout
       7. insufficient price path
       8. forbidden fields absent
       9. no parameter tuning
      10. no Risk / Execution / LLM / Telegram imports
  2. The module emits `POST_DISCOVERY_OUTCOME_EVALUATED` and
     `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` only.
  3. Every output payload contains `schema_version`,
     `source_phase`, `evidence_refs`.
  4. Every output payload is rejected by
     `assert_payload_has_no_forbidden_keys` if any forbidden
     trade-authority / runtime-tuning key is present.

After the implementation PR merges, the slice remains
`IN_REVIEW`. A separate evidence-collection run + closeout PR
is required before the slice can be flipped to `ACCEPTED`.

## Forbidden items

Every payload, every event, every record, every test fixture
**MUST NOT** contain:

  - `buy`, `sell`, `long`, `short`, `direction`, `side`
  - `entry`, `entry_price`, `exit`, `exit_price`, `order`,
    `order_type`, `execution_command`
  - `position_size`, `leverage`, `stop`, `stop_loss`,
    `stop_price`, `target`, `target_price`, `take_profit`,
    `risk_budget`
  - `runtime_config_patch`, `symbol_limit_patch`,
    `threshold_patch`, `candidate_pool_patch`,
    `regime_weight_patch`

The module **MUST NOT** import:

  - `app.risk`
  - `app.execution`
  - `app.exchanges.binance` (private gateway)
  - `app.llm`
  - `app.telegram`

The module **MUST NOT** modify:

  - `symbol_limit`
  - anomaly thresholds
  - candidate-pool capacity
  - Regime weights
  - any other runtime knob

## Safety boundary

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account / order / position / leverage / margin endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

## Why this does not authorise live trading

  - The module is purely descriptive. Every output is a label
    or a metric; no field is a direction call, an order, a
    sizing decision, or a stop / target.
  - The Risk Engine remains the single trade-decision gate.
  - The Phase 1 safety flags remain locked. None of them is
    flipped by D-B.
  - The reference set this layer consumes is the same
    post-hoc D-A reference set, which by construction MUST NOT
    rewrite past decisions or pollute the simulated live-radar
    score with future-knowledge.
  - The labels do not "look at the answer key" against future
    returns to retune any threshold - they only describe the
    timing of the first sighting relative to the recorded
    move.
  - Severe misses (`RAVEUSDT`, `STOUSDT`, ...) recorded by
    D-A continue to flow into a later **Severe Missed Tail
    Triage** slice for human review only; D-B does not change
    that authority surface.
  - Phase 12 (real money / live trading) remains FORBIDDEN
    under the Phase 1 safety lock; Spec §41 Go/No-Go has not
    been initiated.

## Integration boundary

  - Allowed file changes: `app/adaptive/`,
    `app/core/events.py` (new EventType only),
    `app/exports/` (only if needed to register the new
    EventType), `app/paper_run/daily_report.py` (only if a
    summary section is needed), `tests/unit/`,
    `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
    `docs/CHANGELOG.md`, `docs/PHASE_11C_1C_C_B_B_B_D_B_POST_DISCOVERY_OUTCOME_METRICS.md`.
  - Forbidden file changes: `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/llm/`, `app/telegram/`, anything
    Binance private API, the live trading flag, runtime
    config / thresholds / `symbol_limit` / `candidate_pool` /
    Regime weights, the DeepSeek transport, the Telegram
    outbound transport.



## Evidence closeout (PR after #67)

> **Status: IN_REVIEW / INSUFFICIENT_EVIDENCE.** The D-B
> implementation PR (#67) is merged into `main` and the v0
> module + the two typed `EventType` values + the 20-case
> unit-test module are present. This evidence-closeout PR adds
> the paper-only evidence runner
> `scripts/run_post_discovery_outcome_evidence.py`, an 8-case
> runner unit-test module
> `tests/unit/test_post_discovery_outcome_evidence_runner.py`,
> and an honest `INSUFFICIENT_EVIDENCE` /
> `NEEDS_OPERATOR_DATA` evidence run against the empty
> `data/historical_market_store/` + `data/sqlite/events.db` +
> `data/reports/exports/` paths in this workspace. The runner
> refused to fabricate D-A records and wrote the marker
> report + empty events.jsonl + markdown summary to
> `data/reports/post_discovery_outcome/`. Therefore D-B
> **CANNOT** be marked `ACCEPTED` in this PR. D-B will move
> from `IN_REVIEW` to `ACCEPTED` only after a follow-up PR
> that runs the same runner against operator-supplied real
> Phase 11C.1C-C-B-B-B-D-A historical mover coverage records.

### Evidence runner

  - New paper-only script
    `scripts/run_post_discovery_outcome_evidence.py`. The
    runner consumes the artefacts produced by Phase
    11C.1C-C-B-B-B-D-A and turns each audited mover into one
    `PostDiscoveryOutcomeRecord` via
    `PostDiscoveryOutcomeEvaluator`, then aggregates the
    records into one `PostDiscoveryOutcomeReport`. Inputs are
    accepted in priority order:
      1. `--coverage-payload` - a Phase 11C.1C-C-B-B-B-D-A
         `HistoricalMoverCoverageBackfillReport` payload
         (`.json` or `.jsonl`).
      2. `--export-dir` - directory of exported
         `events.jsonl` files; the runner picks the most
         recent
         `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`
         event.
      3. `--events-db` - read-only SQLite events DB.
      4. `--historical-store-dir` - recorded as a warning
         when no fresh-audit hook is reachable. The runner
         does **NOT** trigger a fresh D-A audit by itself.
    Optional `--price-paths-json` accepts an operator-supplied
    JSON file mapping each symbol to a sequence of post
    first-seen `{timestamp_utc_ms, price}` observations. When
    omitted, the runner emits `MISSED_STRONG_TAIL` for records
    whose D-A reference recorded a strong tail
    (`max_window_gain >= 0.20`) and `INSUFFICIENT_PRICE_PATH`
    for the rest. When all input sources are unreachable the
    runner writes a marker report with status
    `INSUFFICIENT_EVIDENCE` / `NEEDS_OPERATOR_DATA` and exits
    with code `2` so a downstream caller cannot mistakenly
    flip D-B to `ACCEPTED`.
  - The runner emits two paper-only event payloads to
    `<output-dir>/events.jsonl`:
      - `POST_DISCOVERY_OUTCOME_EVALUATED` (one per record).
      - `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` (one per
        batch).
    Plus `<output-dir>/post_discovery_outcome_report.json`
    and `<output-dir>/post_discovery_outcome_report.md`
    (markdown summary).
  - Runner module-level invariants (enforced by tests):
      - **Forbidden imports absent**: the runner does not
        import `app.risk`, `app.execution`,
        `app.exchanges.binance`, `app.exchanges.binance_public_ws`,
        `app.llm`, `app.telegram`.
      - **Forbidden keys absent**: every artefact the runner
        writes is recursively walked by
        `assert_payload_has_no_forbidden_keys`; no `buy` /
        `sell` / `direction` / `order` / `position_size` /
        `leverage` / `stop` / `stop_loss` / `target` /
        `take_profit` / `risk_budget` / runtime-tuning patch
        is ever written.
      - **No fabrication**: when no D-A artefact is
        reachable, the runner refuses to invent records and
        marks the run `INSUFFICIENT_EVIDENCE`.

### Evidence run (this workspace)

`data/historical_market_store/`, `data/sqlite/events.db`, and
`data/reports/exports/` are absent in this workspace. The
runner correctly produced:

  - `data/reports/post_discovery_outcome/post_discovery_outcome_report.json`
    with `status = INSUFFICIENT_EVIDENCE`,
    `needs_operator_data = true`, `evaluated_count = 0`,
    `report_generated_count = 0`, and warnings
    `export_dir_no_d_a_payload`, `events_db_no_d_a_payload`,
    `historical_store_dir_missing`, `NEEDS_OPERATOR_DATA`.
  - `data/reports/post_discovery_outcome/events.jsonl` -
    empty (zero events).
  - `data/reports/post_discovery_outcome/post_discovery_outcome_report.md`
    - markdown summary that lists the safety boundary
    verbatim (no live trading, no profitability, no
    direction, no auto-tuning, no DeepSeek, Phase 12
    FORBIDDEN) and surfaces `RAVEUSDT: ABSENT` /
    `STOUSDT: ABSENT` because no D-A payload reached the
    runner.

`RAVEUSDT` and `STOUSDT` were neither evaluated nor
classified by this run; they are recorded as `ABSENT`. The
runner specifically supports them as
`MISSED_STRONG_TAIL` / `NEEDS_TRIAGE` /
`INSUFFICIENT_PRICE_PATH` candidates once a real D-A
artefact is supplied; nothing was fabricated.

### Tests

  - `tests/unit/test_post_discovery_outcome_metrics.py` -
    20 cases pass (no regression vs. PR #67 head).
  - `tests/unit/test_post_discovery_outcome_evidence_runner.py`
    - 8 new cases covering: insufficient-evidence path,
    coverage-payload happy path, missed-strong-tail
    surfacing, operator price-paths refinement, export-dir
    fallback, forbidden-key guard on every emitted artefact,
    forbidden-imports static check on the runner source,
    and CLI exit code on missing inputs.
  - Full unit-test suite: `2450 passed`.

### What this evidence-closeout PR does NOT change

  - **NO** change to `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/llm/`, `app/telegram/`,
    `app/config/`.
  - **NO** change to runtime thresholds, `symbol_limit`,
    `candidate_pool`, Regime weights, the DeepSeek transport,
    or the Telegram outbound transport.
  - **NO** new private API surface, signed endpoint,
    `listenKey`, real Telegram outbound, or DeepSeek trade
    decision.
  - **NO** Severe Missed Tail Triage, Replay / Reflection
    extension, DeepSeek integration, or Phase 12 work.

### D-B status

  - **Status: IN_REVIEW / INSUFFICIENT_EVIDENCE /
    EVIDENCE_CLOSEOUT_ONLY.**
  - D-B does **NOT** authorise live trading.
  - D-B does **NOT** prove strategy profitability.
  - D-B does **NOT** solve direction (long / short / entry /
    exit / stop / target / position size / leverage).
  - D-B does **NOT** authorise automatic parameter tuning.
  - D-B does **NOT** authorise DeepSeek trade decisions.
  - Phase 12 remains **FORBIDDEN**.



## Evidence closeout (PR after #69) — ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT

> **Status: ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
> PRICE_PATH_INSUFFICIENT** (explicitly **NOT** full quality
> accepted).
>
> This is a **docs-only** closeout. PR #69 fixed the D-B
> evidence runner input adapter gap so the runner consumes
> the **real** D-A export shape
> (`HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` events whose
> payload **is** the per-mover record, not wrapped in a
> `record` key). The real VPS D-A export evidence was rerun
> on `main`. This closeout PR records the resulting B1
> evidence run and flips the slice from
> `IN_REVIEW / INSUFFICIENT_EVIDENCE / EVIDENCE_CLOSEOUT_ONLY`
> to **`ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY /
> PRICE_PATH_INSUFFICIENT`**.

### Required closeout statements (verbatim)

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

### D-A export input check (real VPS rerun on `main`)

  - `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = 2`
  - `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = 300`
  - `D_A_EXPORT_INPUT_CHECK = PASS`

### B1 evidence run output

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

### What `ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT` means

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
    `INSUFFICIENT_PRICE_PATH` because the D-A export does
    not yet carry post-first-seen K-line price paths for
    those movers; 105/300 records (35%) are
    `MISSED_STRONG_TAIL` (the system never had a first-seen
    anchor at all). Neither outcome class lets the report
    classify the *quality* of the system's timing — we
    cannot tell from this run whether the first sighting
    was early, late, choppy, late-reversal, or
    fake-breakout, because the price path that would allow
    that classification is missing for every evaluable
    record. This is the **partial quality** half of the
    acceptance.
  - **`RAVEUSDT` and `STOUSDT` remain unresolved by D-B
    alone.** Both show up in this run as
    `INSUFFICIENT_PRICE_PATH / INSUFFICIENT_DATA`; they
    require price-path completeness or explicit data-gap
    triage before the Severe Missed Tail Triage slice can
    consume them.

### What `ACCEPTED_TOOLCHAIN / PARTIAL_QUALITY / PRICE_PATH_INSUFFICIENT` does NOT mean

  - **D-B does NOT solve direction.** The runner does not
    emit, and is forbidden to emit, any `long` / `short` /
    `entry` / `exit` / `stop` / `target` / `position_size`
    / `leverage` field. The two label sets
    (`detection_timing_label`, `outcome_label`) are
    descriptive only.
  - **D-B does NOT prove strategy profitability.** No PnL
    was simulated; no order was submitted; no Risk Engine
    decision was reproduced. The labels describe what the
    reference set already recorded; they do not measure
    P&L.
  - **D-B does NOT authorise auto-tuning.** The labels
    MUST NOT drive `symbol_limit` expansion, anomaly
    threshold changes, candidate-pool capacity changes,
    Regime weight changes, or any other runtime knob.
    "Looking at the answer key" against the post-hoc D-A
    reference set is forbidden.
  - **D-B does NOT authorise DeepSeek trade decisions.**
    DeepSeek remains read-only / sandbox-only / offline
    under the AI Layer Constitution; D-B's labels are
    **not** trade authorisation surface for DeepSeek or
    any other LLM.
  - **Phase 12 remains FORBIDDEN.** No Phase 1 safety
    flag is loosened by this closeout; Spec §41 Go/No-Go
    has not been initiated.

### Next allowed route (paper-only; gated, sequential)

  - **B1 (this slice) closeout** — accepted as
    **toolchain + partial quality only**, NOT
    direction-quality. This is the closeout currently
    being recorded.
  - Then **either** (operator's choice, gated by an
    explicit kickoff PR per slice):
      - **B1.1** — *Historical Price Path Completeness /
        Kline Path Adapter* — likely needed because
        195/300 records lack sufficient post-first-seen
        price path, and `RAVEUSDT` / `STOUSDT` remain
        unresolved on price-path / data-gap grounds.
        Improving D-B outcome quality before B2 is the
        **recommended** next route.
      - **B2** — *Severe Missed Tail Triage* —
        admissible **only with the explicit note that
        `RAVEUSDT` and `STOUSDT` currently require
        price-path / data-gap triage** before they can be
        classified as severe missed tails by D-B alone.
  - The **next allowed route is NOT** to start DeepSeek
    directly, and is **NOT** to start blind walk-forward
    directly.
  - Recommended next slice after this docs PR: **B1.1
    Price Path Completeness / Kline Path Adapter.**

### What this docs-only closeout PR did NOT change

  - **No** file under `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `exchanges/`,
    `llm/`, `telegram/`, or database schema is touched.
  - **No** event name is added, removed, or renamed.
  - **No** schema version is changed.
  - **No** runtime behaviour is changed.
  - **No** test was run by this PR.
  - **No** paper run, export, replay, or historical
    builder was invoked by this PR.
  - **No** real API was contacted by this PR.

### Safety boundary (held end-to-end)

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

**The Risk Engine remains the single trade-decision gate.**
