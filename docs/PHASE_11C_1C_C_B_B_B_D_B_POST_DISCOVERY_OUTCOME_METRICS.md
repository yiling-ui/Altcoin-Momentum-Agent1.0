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
