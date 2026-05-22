# Changelog

All notable changes to AMA-RT will be recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the project phase plan in `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` §43.

## [Unreleased]

### Phase 11C.1C-B - Adaptive Candidate Runtime Calibration & Early Tail Discovery v0

**Version:** `1.4.0a11c.1c.b` - Phase 11C.1C-B. Tracks the
**paper-only first version** of the Adaptive Candidate Runtime
Calibration & Early Tail Discovery layer that builds on top of
the Phase 11C.1C-A contracts.

> **Status: IN_REVIEW / PR_OPEN on PR #38.** PR #38 is currently
> open against `main` (post-PR-#37 baseline) and has **not** been
> merged. The entry below describes the changes shipped on the
> PR branch; Phase 11C.1C-B will only be marked **ACCEPTED**
> after PR #38 is merged AND a human reviewer accepts the 30s
> dry-run + 5min real public WS smoke evidence collected for
> the PR. Until that gate fires, this entry is pre-merge /
> IN_REVIEW. Phase 11C.1C-C remains **NOT_STARTED**. Phase 12
> remains **FORBIDDEN**.

> **Phase 11C.1C-B is NOT live trading. NOT AI Learning. NOT
> complete strategy validation. NOT the full MFE/MAE processor.
> NOT real Telegram outbound. NOT real Binance trading API. It
> is the runtime calibration metrics + Early Tail Discovery v0 +
> daily-report enhancements first version on top of the Phase
> 11C.1C-A contracts.**

#### `RuntimeCalibrationMetrics` value object (`app/adaptive/models.py`)

A new frozen Pydantic v2 model carrying the brief-mandated
fifteen fields:

  - `candidate_first_seen_ts`
  - `candidate_first_seen_price`
  - `current_price`
  - `price_change_since_first_seen`
  - `quote_volume_acceleration_1m`
  - `quote_volume_acceleration_5m`
  - `price_acceleration_1m`
  - `price_acceleration_5m`
  - `volume_rank`
  - `volume_rank_jump_5m`
  - `distance_to_24h_high`
  - `distance_from_first_seen`
  - `freshness_score`
  - `late_chase_risk`
  - `early_tail_score`

The block is attached to every `AdaptiveCandidateContext` (under
the new `runtime_calibration` field) and rides into the Phase
8.5 `learning_ready.adaptive_candidate.runtime_calibration`
sub-block on every event the WS-radar chain emits, so Phase 8.5
export, Phase 10A replay, and the daily report all pick it up
without schema gymnastics.

#### New `app/adaptive/runtime.py` - pure-function helpers

  - `compute_runtime_calibration(...)` - top-level builder; takes
    raw runtime inputs (first-seen ts/price, current ts/price,
    price + quote-volume rolling history, current rank +
    5m-old rank, candidate stage, blowoff risk) and returns the
    populated `RuntimeCalibrationMetrics`.
  - `compute_early_tail_score(...)` - additive 0..100 score
    derived from `volume_rank_jump_5m` + quote-volume / price
    accelerations + freshness, gated by stage and capped by
    distance from first-seen.
  - `compute_late_chase_risk_score(...)` - 0..100 risk score
    that rises with distance from first-seen, proximity to 24h
    high, and lost freshness; clamped high for `late` /
    `blowoff` and clamped low for `dumped`.
  - `compute_freshness_score(...)` - simple
    `half_life / (half_life + elapsed)` decay.
  - `compute_relative_acceleration(...)` - rolling-history
    helper.

All functions are pure (no I/O, no global state); the source-tree
audit in
`tests/unit/test_phase11c_1c_a_adaptive_candidate.py
::test_adaptive_module_does_not_import_third_party_network_libs`
already covers the new module.

#### `Candidate` baselines + per-symbol rolling history

`app/market_data_public/candidate_pool.py`:

  - **Stable baselines** recorded ONCE at admission:
    `first_seen_price`, `quote_volume_first_seen`,
    `volume_rank_first_seen`. These never get overwritten on
    subsequent `offer()` updates.
  - **Rolling histories** (`price_history`,
    `quote_volume_history`, `volume_rank_history`, oldest -> newest)
    capped at
    `CandidatePoolConfig.per_symbol_history_max_samples` (200)
    and trimmed to the last 10 minutes.
  - **Runtime-layer scores** (`early_tail_score`,
    `late_chase_risk_score`, `freshness_score`,
    `promoted_before_24h_top_move`) written back by the
    WS-radar chain driver via the new
    `CandidatePool.update_runtime_metrics(...)` method.

#### Early Tail Discovery v0 - capacity-protection invariant

`CandidatePool._enforce_capacity` now sorts candidates by a
two-tier eviction key so the brief's "do not evict high
`early_tail_score`" invariant holds:

```
evict_key = (
    1 if early_tail_score >= early_tail_protect_threshold else 0,
    early_tail_score,
    radar_score,
    last_seen_ms,
)
```

UNPROTECTED candidates (early-tail score below threshold) get
evicted first. PROTECTED candidates only get evicted if every
unprotected candidate has already been removed - and the lowest
early-tail score goes first. The default threshold lives in
`DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD = 60.0`.

#### WS-radar chain integration

`WSRadarChainDriver` (`app/market_data_public/ws_radar_chain.py`):

  - Now accepts an optional `candidate_pool=` handle so the
    driver can write runtime metrics back onto the candidate
    after every chain pass.
  - Reads `candidate.first_seen_price` (stable admission
    baseline) instead of the previous "approximate via
    snapshot" path.
  - Threads `candidate.price_history` /
    `candidate.quote_volume_history` /
    `pool.volume_rank_5m_ago(candidate)` into
    `compute_runtime_calibration`.
  - Tracks per-run aggregates surfaced by
    `adaptive_metrics_payload`:
      - `top_early_tail_candidates` (capped at 10)
      - `top_late_chase_risk_candidates` (capped at 10)
      - `early_tail_score_top_symbols`
      - `opportunity_score_distribution` (10-point bins:
        `0-10` ... `90-100`)
      - `symbols_promoted_before_24h_top_move`
      - `eden_alt_near_examples` - candidate symbols whose
        upper-cased name starts with `EDEN`, `ALT`, or `NEAR`
        and whose `early_tail_score > 0`.

#### Daily report enhancement

`DailyReportSnapshot` + the Markdown body
(`app/paper_run/daily_report.py`) now carry the new fields:

  - `top_early_tail_candidates`
  - `top_late_chase_risk_candidates`
  - `early_tail_score_top_symbols`
  - `opportunity_score_distribution`
  - `symbols_promoted_before_24h_top_move`
  - `eden_alt_near_examples`
  - `early_tail_protect_threshold`
  - `candidate_pool_promoted_before_24h_top_move`

The Markdown body adds a new section
`## Phase 11C.1C-B Adaptive Candidate Runtime Calibration & Early
Tail Discovery v0` after the existing Phase 11C.1C-A block,
explicitly noting the paper / virtual nature of the layer.

#### Phase 1 safety lock UNCHANGED

Phase 11C.1C-B does NOT touch the Phase 1 safety lock. After
running the runtime-calibration pipeline end-to-end every flag
below remains:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client.

#### Phase 11C.1C-B explicitly does NOT

- accept any Binance API key / API secret / `listenKey`.
- subscribe to any user data stream / private WebSocket / trading
  WebSocket API / account / margin / position / leverage / balance
  / order private WS variant.
- treat the new `early_tail_score` or the existing
  `strategy_mode` (paper / virtual) field as a real-trade
  authority. The Risk Engine remains the single trade-decision
  gate; `stop_unconfirmed=True` continues to lock the WS-radar
  chain into the typed-reject path.
- implement the full MFE/MAE processor. The
  `LabelQueueContract` is descriptive; the processor is reserved
  for a future PR (Phase 11C.1C-C).
- implement AI Learning. The Phase 11C.1C-B scoring / selector
  is deterministic.
- enable real Telegram outbound, DeepSeek trade decisions, or
  any third-party HTTP / WebSocket / SDK / LLM / Telegram bot
  import on the runtime-calibration surface.
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c_1c_b_runtime_calibration.py` (new,
  12 cases) pinning every brief-mandated behaviour:
  - `test_early_tail_score_detects_volume_rank_jump`
  - `test_freshness_penalizes_late_chase`
  - `test_late_blowoff_never_follow`
  - `test_top_early_tail_candidates_reported`
  - `test_candidate_first_seen_price_preserved`
  - `test_volume_rank_jump_calculated`
  - `test_adaptive_runtime_fields_exportable`
  - `test_no_live_trading_flags_unchanged`
  - `test_runtime_calibration_payload_round_trips`
  - `test_pool_protects_high_early_tail_candidate_from_eviction`
  - `test_eden_alt_near_examples_surfaced`
  - `test_strategy_mode_does_not_authorise_real_trade`

The full Phase 11C.1C-A test suite continues to pass with no
regression vs. the post-PR-#37 main baseline.

### Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector Contracts

**Version:** `1.4.0a11c.1c.a` - Phase 11C.1C-A. Tracks the
**paper-only first version** of the Adaptive Candidate Regime &
Strategy Selector contracts.

> **Status: ACCEPTED (closed 2026-05-22; PR #36 merged; PR #37
> docs closeout).** PR #36 has been merged into `main`; PR #37
> closed out the docs gate. The Phase 11C.1C-A acceptance smoke
> evidence (30s dry-run + 5min real public WS) was accepted; the
> entry below is the closeout record. Phase 11C.1C-B is now
> **IN_REVIEW / PR_OPEN** on PR #38 (see the Phase 11C.1C-B
> entry above).

> **Phase 11C.1C-A is NOT live trading. NOT AI Learning. NOT
> complete strategy validation. NOT the full MFE/MAE processor. It
> is the data-contract + scoring + selector + paper-only routing
> first version.**

#### New package: `app/adaptive/`

Seven Pydantic v2 frozen value objects + six pure
classifier / scorer functions:

- `MarketRegimeAssessment` - regime bucket + confidence + risk
  multiplier + allowed_strategy_modes + no_trade_reason. Buckets:
  `MEME_RISK_ON` / `SECTOR_ROTATION` / `BTC_ABSORPTION` /
  `ALT_RISK_OFF` / `SYSTEMIC_RISK` / `RISK_OFF` / `NO_TRADE` /
  `NEUTRAL`.
- `CandidateStageAssessment` - life-cycle stage (`early` / `mid`
  / `late` / `blowoff` / `dumped`) + freshness +
  late_chase_risk + blowoff_risk + first_seen_ts +
  first_seen_price + current_price + distance_from_first_seen +
  distance_to_24h_high.
- `OpportunityScore` - weighted-sum score + S/A/B/C grade.
- `StrategyModeDecision` - paper / virtual strategy expression
  (`follow` / `pullback` / `observe` / `reject`).
- `ClusterContext` - cluster_id + cluster_leader + cluster_rank
  + cluster_size + cluster_reason. The first-version classifier
  groups by quote-asset suffix.
- `LabelQueueContract` - opportunity_id / scan_batch_id / symbol
  / enqueued_at_ms / mfe_mae_label_pending / future_tail_label_pending
  / tracking_windows / reference_price. Default tracking
  windows: 5m / 15m / 30m / 1h / 4h.
- `AdaptiveCandidateContext` - one-shot bundle of the above plus
  the four version labels (`strategy_version` / `scoring_version`
  / `risk_config_version` / `state_machine_version`).
- `assess_market_regime`, `classify_candidate_stage`,
  `compute_opportunity_score`, `select_strategy_mode`,
  `build_cluster_context`, `build_label_queue_contract`,
  `build_adaptive_candidate_context` (one-shot orchestrator).

#### Six new EventType entries (`app/core/events.py`)

```
MARKET_REGIME_ASSESSED
CANDIDATE_STAGE_CLASSIFIED
OPPORTUNITY_SCORED
STRATEGY_MODE_SELECTED
CLUSTER_CONTEXT_ATTACHED
LABEL_QUEUE_ENQUEUED
```

The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
pipelines accept the new types unchanged. The Phase 8.5 eleven-type
`LEARNING_READY_EVENT_TYPES` tuple is unchanged; the new types are
exposed as the separate `ADAPTIVE_LEARNING_READY_EVENT_TYPES`
tuple so the Phase 8.5 contract stays load-bearing.

#### Scoring formula (first version)

```
score = (
    0.25 * momentum_strength
  + 0.20 * volume_expansion
  + 0.15 * liquidity_quality
  + 0.15 * regime_fit
  + 0.15 * freshness
  - 0.20 * manipulation_risk
  - 0.20 * late_chase_risk
)
```

Inputs clipped to `[0.0, 100.0]`; score clipped to `[0.0, 100.0]`.
Grade boundaries: S>=80, A in [65,80), B in [50,65), C<50.
Tunable via `OpportunityScoreInputs` + `OpportunityScoreWeights`.

#### Strategy selector (first version)

Decision flow (in priority order):

1. `manipulation_risk >= 60` -> **reject**.
2. regime is `RISK_OFF` / `NO_TRADE` / `SYSTEMIC_RISK` ->
   **reject**. `ALT_RISK_OFF` -> **observe**.
3. stage is `dumped` / `blowoff` / `late` -> **observe**.
4. `mid` + strong momentum + late_chase_risk high -> **pullback**.
5. `early` + every "follow" condition holds + regime allows
   follow -> **follow**.
6. otherwise -> **observe**.

The `mode` is a **paper / virtual** field. `follow` does NOT
authorise opening a position; the Risk Engine remains the single
trade-decision gate; `stop_unconfirmed=True` continues to lock the
chain into the typed-reject path.

#### Phase 8.5 contracts extended

- `LearningReadyContext` (Phase 8.5) gained an optional
  `adaptive_candidate` field; `to_event_payload()` renders it
  under the canonical `adaptive_candidate` key.
- `VirtualTradePlan` (Phase 8.5) gained eleven optional adaptive
  fields: `opportunity_score`, `opportunity_grade`,
  `candidate_stage`, `strategy_mode`, `cluster_id`,
  `cluster_leader`, `label_queue_pending`, `follow_allowed`,
  `pullback_allowed`, `observe_only`, `reject_reason`. All default
  to `None` so existing callers continue to work; the round-trip
  helper `payload_to_virtual_trade_plan` preserves them.

#### WS-radar chain wired

`WSRadarChainDriver.drive()` now:

  - builds an `AdaptiveCandidateContext` per ACTIVE candidate via
    `_build_adaptive_context_for_candidate`;
  - emits the six new events alongside the existing
    `PRE_ANOMALY_DETECTED` / `ANOMALY_DETECTED` /
    `STATE_TRANSITION` chain via `_emit_adaptive_events`;
  - attaches the adaptive context to every event's
    `learning_ready.adaptive_candidate`;
  - propagates the adaptive fields onto the paper
    `VirtualTradePlan`;
  - tracks per-regime / per-stage / per-mode / per-grade
    histograms and exposes `adaptive_metrics_payload()` for the
    runner / daily report (counters: `market_regime_counts`,
    `candidate_stage_counts`, `strategy_mode_counts`,
    `opportunity_grade_counts`, `top_opportunity_scores`,
    `follow_count`, `pullback_count`, `observe_count`,
    `reject_count`, `late_chase_rejected_count`,
    `blowoff_observed_count`, `label_queue_enqueued`).

#### Daily report (`app/paper_run/daily_report.py`)

- `DailyReportBuilder.build()` accepts a new `adaptive_metrics`
  kwarg.
- `DailyReportSnapshot` gained the brief-mandated adaptive fields:
  `market_regime_counts`, `candidate_stage_counts`,
  `strategy_mode_counts`, `opportunity_grade_counts`,
  `top_opportunity_scores`, `label_queue_enqueued`,
  `observe_count`, `reject_count`, `follow_count`,
  `pullback_count`, `late_chase_rejected_count`,
  `blowoff_observed_count`, `market_regime_assessed_count`,
  `candidate_stage_classified_count`,
  `opportunity_scored_count`, `strategy_mode_selected_count`,
  `cluster_context_attached_count`, `adaptive_metrics`.
- `_aggregate` cross-checks the event-log counts of the six new
  event types against the runner-side `adaptive_metrics` so a
  stale runner counter cannot under-report a real adaptive event.
- The Markdown body has a new
  `## Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector`
  section with every brief-mandated counter + per-regime,
  per-stage, per-mode, per-grade tables + a top-N opportunity
  score table.

#### Phase 11C runner (`scripts/run_public_market_paper.py`)

The runner populates `_Phase11CRunStats.adaptive_metrics` from
`WSRadarChainDriver.adaptive_metrics_payload()` on every loop tick
and passes the dict through to `DailyReportBuilder.build()` on
shutdown.

#### Phase 1 safety lock UNCHANGED

Phase 11C.1C-A does NOT touch the Phase 1 safety lock. After
running the adaptive pipeline end-to-end (with the six new
adaptive events firing alongside the Phase 11C.1B chain) every
flag below remains:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client.

#### Phase 11C.1C-A explicitly does NOT

- accept any Binance API key / API secret / `listenKey`.
- subscribe to any user data stream / private WebSocket / trading
  WebSocket API / account / margin / position / leverage / balance
  / order private WS variant.
- treat the new `strategy_mode` (paper / virtual) field as a
  real-trade authority. The Risk Engine remains the single
  trade-decision gate; `stop_unconfirmed=True` continues to lock
  the WS-radar chain into the typed-reject path.
- implement the full MFE/MAE processor. The
  `LabelQueueContract` is descriptive; the processor is reserved
  for a future PR (Phase 11C.1C-B).
- implement AI Learning. The Phase 11C.1C-A scoring / selector is
  deterministic; auto-decided trades are reserved for Phase
  11C.1C-B+.
- enable real Telegram outbound, DeepSeek trade decisions, or any
  third-party HTTP / WebSocket / SDK / LLM / Telegram bot import
  on the adaptive surface.
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c_1c_a_adaptive_candidate.py` (new, 31
  cases) pinning every brief-mandated behaviour:
  - `test_market_regime_assessment_contract`
  - `test_candidate_stage_assessment_contract_field_set`
  - `test_opportunity_score_contract_field_set`
  - `test_label_queue_contract_created`
  - `test_cluster_context_groups_by_quote_asset`
  - `test_candidate_stage_classifier_early`
  - `test_candidate_stage_classifier_mid`
  - `test_candidate_stage_classifier_late`
  - `test_candidate_stage_classifier_blowoff`
  - `test_candidate_stage_classifier_dumped`
  - `test_opportunity_score_formula`
  - `test_opportunity_grade_boundaries`
  - `test_strategy_selector_follow`
  - `test_strategy_selector_pullback`
  - `test_strategy_selector_observe_for_late`
  - `test_strategy_selector_observe_for_blowoff`
  - `test_strategy_selector_reject_for_high_manipulation`
  - `test_strategy_selector_reject_for_no_trade_regime`
  - `test_adaptive_candidate_context_payload_round_trips`
  - `test_adaptive_context_attached_to_learning_ready_payload`
  - `test_adaptive_event_types_distinct_from_phase_8_5_set`
  - `test_ws_radar_chain_emits_six_adaptive_events`
  - `test_virtual_trade_plan_contains_adaptive_fields`
  - `test_daily_report_contains_adaptive_candidate_metrics`
  - `test_export_replay_reads_adaptive_candidate_events`
  - `test_no_live_trading_flags_unchanged`
  - `test_no_real_telegram_outbound_flag_unchanged`
  - `test_no_binance_api_key_consumed`
  - `test_phase_12_remains_forbidden`
  - `test_strategy_mode_does_not_authorise_real_trade`
  - `test_adaptive_module_does_not_import_third_party_network_libs`
- `tests/unit/test_phase11b_no_network.py` extended: allowed
  paper_run event-type list grew the six new entries
  (`MARKET_REGIME_ASSESSED` / `CANDIDATE_STAGE_CLASSIFIED` /
  `OPPORTUNITY_SCORED` / `STRATEGY_MODE_SELECTED` /
  `CLUSTER_CONTEXT_ATTACHED` / `LABEL_QUEUE_ENQUEUED`).
- `tests/unit/test_main_entrypoint.py` updated: banner assertion
  now expects the Phase 11C.1C-A label "Adaptive Candidate
  Regime".

Total tests on PR #36: **2219 passed** in `tests/unit/`
(244 phase11c-prefixed cases including the 31 brief-mandated
`test_phase11c_1c_a_adaptive_candidate.py` cases). No regressions
relative to the 2166-test pre-Phase 11C.1C-A baseline. PR #36 has
been merged into `main`; PR #37 closed out the docs gate. The
test count above is the figure measured on the PR branch at
acceptance time.

#### Versions stamped on every adaptive event

```
strategy_version       = phase_11c_1c_a.strategy.v1
scoring_version        = phase_11c_1c_a.scoring.v1
risk_config_version    = phase_11c_1c_a.risk_config.v1
state_machine_version  = phase_11c_1c_a.state_machine.v1
```

A future PR that bumps the formula or the state machine bumps the
version label and Reflection / Replay automatically picks up the
change.

### Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar

**Version:** `1.4.0a11c.1b` - Phase 11C.1B. Tracks the Phase 11C
real-data acceptance recovery PR-B.

#### Phase 11C.1B 5-min real public WS smoke: PASS (2026-05-22)

The 5-min real public WS smoke now reports
`ws_messages_received > 0`, `ws_chains_emitted > 0`,
`PUBLIC_WS_CONNECTED` written, no 429 / 418, every safety flag
unchanged. The original failure was a zero-timeout `recv`
short-circuit in `StdlibPublicWSTransport.poll`; fixed by always
draining the recv buffer non-blockingly at the top of every
`poll` call (and routing the runner's wait window through the WS
pump's blocking timeout instead of an unrelated `time.sleep`).
See `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B and the
new regression tests
`test_real_ws_transport_drains_buffered_bytes_with_zero_timeout`
+ `test_real_ws_runner_loop_pattern_drains_messages_with_zero_timeout`.

#### Phase 11C.1B follow-up: SymbolUniverse (exchangeInfo-as-truth)

Binance USDⓈ-M Futures lists non-ASCII contracts in production -
documented examples include `我踏马来了USDT` and `币安人生USDT`. Each
is a real Binance contract with its own `/fapi/v1/exchangeInfo`
entry, its own all-market WS push, and its own REST detail
endpoints. Phase 11C.1B therefore validates symbols against the
bootstrapped `exchangeInfo` snapshot - NEVER an ASCII-only regex.

  - **New module** `app/market_data_public/symbol_universe.py`
    with `SymbolUniverse.from_exchange_info(symbols)` and
    `SymbolUniverse.empty()` (back-compat admit-all fallback).
  - **New event** `EventType.WS_SYMBOL_REJECTED` for symbols
    refused by the universe gate.
  - **CandidatePool** now consults the universe in `offer()`;
    rejected symbols emit `WS_SYMBOL_REJECTED` and never enter
    the pool's accounting.
  - **Runner** bootstraps the universe from
    `BinancePublicClient.get_symbols()` before constructing the
    candidate pool; falls back to the empty universe on
    bootstrap failure.
  - **Daily-report** payload extended with
    `candidate_pool_rejected_by_universe`,
    `ws_symbol_universe_size`, `ws_symbol_universe_source`,
    `ws_symbol_universe_bootstrapped`,
    `ws_symbol_universe_bootstrap_ts_ms`.
  - **New test file** `tests/unit/test_phase11c_1b_symbol_universe.py`
    with the 4 brief-mandated tests:
    - `test_non_ascii_exchange_symbol_allowed_if_in_exchange_info`
    - `test_non_ascii_ws_symbol_rejected_if_not_in_exchange_info`
    - `test_symbol_validation_uses_exchange_info_not_ascii_regex`
    - `test_empty_universe_is_admit_all_back_compat`

The brief is explicit: **the rejection reason is "not in
exchangeInfo", NEVER "non-ASCII character class".** A pure-ASCII
symbol that is missing from the snapshot is treated identically
to a Chinese symbol that is missing.

Total tests: **2184 passed** (was 2180 before the SymbolUniverse
follow-up; +4 new tests).

#### PR-B revision: routed public/market WebSocket endpoints

PR #32 now connects to the documented Binance USDⓈ-M Futures
*routed* public-market WebSocket endpoints:

```
PUBLIC route :  wss://fstream.binance.com/public/stream?streams=!bookTicker
MARKET route :  wss://fstream.binance.com/market/stream?streams=
                  !ticker@arr/!miniTicker@arr/!markPrice@arr/!forceOrder@arr
PRIVATE route:  wss://fstream.binance.com/private          # FORBIDDEN
```

The unrouted `wss://fstream.binance.com/stream?streams=...` URL
is NOT the acceptance path: per the Binance public-WS reference,
an unrouted connection silently drops market-class streams
(`!markPrice@arr`, `!ticker@arr`, etc.) so a runner that reports
`PUBLIC_WS_CONNECTED` against `/stream` would in fact miss most
of the radar's data. The new
`MultiTransportPublicWSManager` opens one routed
`StdlibPublicWSTransport` per route in parallel, splits the
configured stream set via `classify_stream_route` /
`split_streams_by_route`, and merges per-route messages behind a
single `WSMessagePump` interface so the
`BinancePublicWSClient` and the runner can pump the union without
any awareness of the underlying topology.

The `/private` routed endpoint is on `FORBIDDEN_WS_PATH_ROOTS`;
`assert_public_ws_path_allowed` refuses it explicitly. New
constants:

- `ALLOWED_PUBLIC_WS_PATH_ROOTS` (routed acceptance) =
  `{"public/ws", "public/stream", "market/ws", "market/stream"}`
- `LEGACY_UNROUTED_WS_PATH_ROOTS` (back-compat for in-process
  pump fixtures only) = `{"ws", "stream"}`
- `FORBIDDEN_WS_PATH_ROOTS` =
  `{"private", "ws-api", "ws-fapi", "ws-papi", "trading-api",
  "userdatastream"}`
- `STREAM_ROUTE_PUBLIC` / `STREAM_ROUTE_MARKET` /
  `STREAM_SUFFIX_ROUTE_PUBLIC` / `STREAM_SUFFIX_ROUTE_MARKET`
  - per-stream route classification.

The runner's WS-first acceptance path now uses the
`MultiTransportPublicWSManager` by default; the unrouted
`/stream` path is kept accepted by the URL parser only so the
in-process pump's existing fixtures still validate. The runner
continues to refuse `--ws-first` without `--dry-run` with rc=2 if
the factory cannot produce a real pump - it does NOT silently
fall back to REST.

The new `tests/unit/test_phase11c_1b_routed_public_market_ws.py`
file pins every behaviour the brief's PR #32 merge checklist
calls out (14 tests):

- `test_routed_public_ws_path_allowed`
- `test_routed_market_ws_path_allowed`
- `test_private_routed_ws_forbidden`
- `test_unrouted_market_stream_rejected_or_not_used`
- `test_mark_price_stream_uses_market_route`
- `test_book_ticker_stream_uses_public_route`
- `test_multi_transport_ws_manager_merges_public_and_market_messages`
- `test_multi_transport_ws_manager_subscribe_routes_to_correct_transport`
- `test_multi_transport_ws_manager_refuses_credentials`
- `test_multi_transport_ws_manager_refuses_private_streams_at_construction`
- `test_runner_real_ws_first_uses_routed_public_and_market_transports`
- `test_no_followup_adapter_stale_text_in_docs_or_help`
- `test_safety_flags_unchanged_with_routed_ws`
- `test_no_private_ws_listen_key_or_user_data_stream`

The Phase 1 safety lock continues to hold throughout. No Binance
API key / secret / `listenKey` is read; no signed REST endpoint
is called; the four ExchangeClientBase write surfaces continue
to refuse on the public client; DeepSeek / Square / real Telegram
outbound stay disconnected; Phase 12 is not entered.

#### Original PR-B scope below

Phase 11C.1A (PR-A, merged) capped the public REST gateway with a
sliding-window rate-limit governor and shut every per-loop detail
REST surface so the bootstrap path could not trigger HTTP 429 / 418
again. The PR-A trade-off was that the runner could see *only* the
symbols the bootstrap already knew about; it could not detect a
brand-new "demon coin" that suddenly woke up between two bootstrap
cadences. Phase 11C.1B (PR-B) restores the discovery surface by
driving an all-market radar off Binance's public WebSocket streams.
The goal is **NOT** to lower discovery capability - it is to *raise*
discovery throughput while keeping REST pressure near zero.

#### New module: `app/exchanges/binance_public_ws.py`

- `BinancePublicWSClient` - public-market WebSocket client.
  - Constructor refuses `api_key` / `api_secret` / `listen_key`
    and any credential-shaped `**kwargs`
    (`PublicWSCredentialForbidden`).
  - `connect` / `disconnect` / `reconnect` lifecycle with
    auto-reconnect (default initial backoff 1 s, max 30 s).
  - `pump_messages(timeout_seconds)` drains the pump, updates the
    heartbeat, and emits `PUBLIC_WS_STALE` once the gap between
    messages crosses `staleness_threshold_ms` (default 3000 ms).
  - `subscribe(streams)` runs every stream through
    `assert_public_ws_stream_allowed`.
  - `metrics_payload()` returns `ws_messages_received` /
    `ws_reconnect_count` / `ws_staleness_ms_max` / `ws_stale_count`
    / `ws_connect_count` / `ws_disconnect_count` /
    `ws_messages_received_by_stream` / `ws_streams_subscribed`.
- `WSConfig` - frozen dataclass; defaults match the brief
  (5 ALLOWLIST streams, `staleness_threshold_ms=3000`,
  `auto_reconnect=True`, `max_subscriptions=64`).
- `WSMessage(stream, data, received_at_ms)` - decoded message
  envelope.
- `WSMessagePump` (abstract) + `InProcessWSPump` (deterministic
  test pump) + `_RefusalTransport` (default; raises
  `NotImplementedError` on `connect`) +
  **`StdlibPublicWSTransport`** (real-network RFC 6455 client
  built on the Python standard library only - `socket` + `ssl` +
  `select` + `struct` + `base64` + `hashlib` + `json` +
  `os.urandom`; route-aware via the new `route="public" |
  "market" | None` constructor parameter; refuses every
  credential-shaped kwarg; never reads `BINANCE_API_KEY` /
  `BINANCE_API_SECRET`; only opens connections to allowlisted
  hosts and routed `/public/{ws,stream}` / `/market/{ws,stream}`
  path roots) +
  **`MultiTransportPublicWSManager`** (Phase 11C.1B routed
  public + market connection group; owns one routed
  `StdlibPublicWSTransport` per route; splits the configured
  streams via `classify_stream_route` and `split_streams_by_route`
  - `!bookTicker` -> PUBLIC, the four MARKET array streams ->
  MARKET; presents the union behind a single `WSMessagePump`
  interface; merges `poll()` output PUBLIC-first MARKET-second;
  exposes `routes` / `transports` / `messages_received_by_route`
  / `metrics_payload`).
- `create_real_public_ws_transport(config=WSConfig(), **kwargs)`
  - public factory for the real-network WS pump. Returns a
  `MultiTransportPublicWSManager` (routed PUBLIC + MARKET
  topology). The runner imports this and calls it whenever
  `--ws-first` is set without `--dry-run`.
- `classify_stream_route(stream)` and
  `split_streams_by_route(streams)` - public helpers that map
  each allowlisted stream to its `"public"` / `"market"` route
  per the Binance USDⓈ-M Futures public-WS reference.
- `assert_public_ws_path_allowed(path)` +
  `ALLOWED_PUBLIC_WS_PATH_ROOTS = {"public/ws", "public/stream",
  "market/ws", "market/stream"}` (the routed acceptance set)
  + `LEGACY_UNROUTED_WS_PATH_ROOTS = {"ws", "stream"}` (kept as
  back-compat for the in-process pump fixtures only) +
  `FORBIDDEN_WS_PATH_ROOTS = {"private", "ws-api", "ws-fapi",
  "ws-papi", "trading-api", "userdatastream"}` (refused at the
  path-root layer in addition to the substring deny-list).
  `assert_public_ws_url_allowed` now runs
  `assert_public_ws_path_allowed` so a hand-composed
  `wss://fstream.binance.com/private/...` URL is refused before
  any socket is opened.
- Public allowlist: `!ticker@arr`, `!miniTicker@arr`,
  `!bookTicker`, `!markPrice@arr`, `!forceOrder@arr` plus the
  per-symbol variants of those streams.
- Private deny-list (`FORBIDDEN_WS_TOKENS`): `listenkey`,
  `userdata`, `userdatastream`, `ws-api`, `trading-api`,
  `ws/api`, `ws-fapi`, `ws-papi`, `accountupdate`,
  `ordertradeupdate`, `orderupdate`, `margincall`, `balanceupdate`,
  `positionupdate`, `leverageupdate`, `accountconfigupdate`.
- Allowed hosts: `fstream.binance.com`,
  `fstream.binancefuture.com`. Only `wss://` URLs accepted.

#### New module: `app/market_data_public/radar.py`

- `AllMarketRadarSnapshot` - frozen pydantic v2 model with every
  brief-mandated field: `symbol`, `timestamp`, `last_price`,
  `price_change_pct_24h`, `price_acceleration_15s`,
  `price_acceleration_60s`, `quote_volume`,
  `quote_volume_delta_60s`, `volume_rank`, `volume_rank_jump`,
  `bid`, `ask`, `spread_pct`, `best_bid_qty`, `best_ask_qty`,
  `mark_price`, `funding_rate`, `liquidation_event`,
  `liquidation_notional`, `ws_source_flags`. `to_payload()` returns
  a JSON-safe dict.
- `AllMarketRadarBuffer` - per-symbol rolling state. Ingest
  handlers cover all five public streams. Computes
  `price_acceleration_15s` / `price_acceleration_60s` /
  `quote_volume_delta_60s` over the rolling history. Maintains
  per-batch volume rank + diffs against the previous batch for
  `volume_rank_jump`. Liquidation events roll off after 60 s.
- `pre_anomaly_score_light(snapshot)` - pure additive scoring,
  capped at 100. Reason tags: `price_acceleration_15s`,
  `price_acceleration_60s`, `quote_volume_delta_60s`,
  `volume_rank_jump`, `spread_compression`,
  `mark_price_alignment`, `liquidation_event`,
  `funding_not_overheated`, `insufficient_history`.
- `RadarScoreConfig` - tunable thresholds; defaults conservative.

#### New module: `app/market_data_public/candidate_pool.py`

- `CandidatePool` - bounded, TTL-aware pool fed from the
  all-market radar. Defaults: `candidate_pool_size=20`,
  `active_detail_limit=3`, `candidate_ttl_seconds=900`,
  `radar_score_threshold=30.0`,
  `volume_rank_jump_threshold=3`,
  `price_acceleration_threshold=0.005`,
  `liquidation_promotes=True`.
- Admission rules: `radar_score >= threshold` OR `volume_rank_jump
  >= threshold` OR `|price_acceleration_60s| >= threshold` OR
  `liquidation_event=True`.
- State machine: WATCHING / ACTIVE / EXPIRED. `pool.expire()`
  drops every candidate older than `candidate_ttl_seconds`.
  Eviction by lowest score + oldest when over capacity.
- Each candidate carries a Phase 8.5 `OpportunityIdentity` with
  `source_phase="phase_11c_1b_ws_first_radar"` so Reflection /
  Replay can split WS-radar candidates from REST-bootstrap
  candidates.
- `metrics_payload()` returns `radar_candidates_seen` /
  `candidate_pool_size` / `candidate_pool_size_max` /
  `candidate_pool_admitted` / `candidate_pool_promoted` /
  `candidate_pool_demoted` / `candidate_pool_expired` /
  `candidate_pool_evicted` / `candidate_pool_active_head` /
  `candidate_pool_top_symbols`.

#### New module: `app/market_data_public/ws_radar_chain.py`

- `WSRadarChainDriver` - drives the Phase 11C.1B event chain for
  one ACTIVE candidate.
  - Reuses the candidate's `OpportunityIdentity` so
    `opportunity_id` / `scan_batch_id` continuity is preserved
    across emissions.
  - Emits `PRE_ANOMALY_DETECTED` + `ANOMALY_DETECTED` +
    `STATE_TRANSITION` with a Phase 8.5 `LearningReadyContext`
    attached to each (opportunity + signal_snapshot +
    virtual_trade_plan + config_versions + source_phase).
  - Maps radar reason tags onto the existing Phase 6
    `PreAnomalyReasonTag` / `AnomalyReasonTag` vocabulary so
    Reflection / Replay continue to work unchanged.
  - Calls the live `RiskEngine` with `stop_unconfirmed=True` so
    EVERY decision falls into the typed-reject-reason path. The
    Risk Engine emits `RISK_REJECTED` with the same
    `learning_ready` block.

#### Three new EventType entries (`app/core/events.py`)

```
PUBLIC_WS_CONNECTED
PUBLIC_WS_DISCONNECTED
PUBLIC_WS_STALE
```

The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
pipelines accept the new types unchanged.

#### Layered WS-first runner (`scripts/run_public_market_paper.py`)

- New CLI flags:
  - `--ws-first` / `--ws-disabled` (mutex; default `ws_first=True`).
  - `--candidate-pool-size N` (default 20).
  - `--active-detail-limit N` (default 3).
  - `--ws-staleness-threshold-ms MS` (default 3000).
  - `--candidate-ttl-seconds S` (default 900).
- Default `ws_first=True`. Under `--dry-run` the runner wires an
  `InProcessWSPump` and a `_push_dry_run_ws_messages` helper that
  pushes a deterministic burst of synthetic `!ticker@arr` /
  `!bookTicker` / `!markPrice@arr` per iteration so the radar /
  pool / chain pipeline can exercise every code path without a
  network.
- Without `--dry-run` AND with `--ws-first` (the Phase 11C.1B
  acceptance path): the runner calls
  `_build_real_public_ws_transport(config)` (module-level factory
  defaulting to `MultiTransportPublicWSManager`, which owns one
  routed `StdlibPublicWSTransport` per route - PUBLIC at
  `/public/stream`, MARKET at `/market/stream`). If the factory
  returns `None` or raises, **the runner refuses to start** with
  rc=2 and the message `real public WebSocket transport is
  required for --ws-first without --dry-run`. The runner does NOT
  silently fall back to the PR-A bootstrap-only REST path.
  Operators who cannot reach `fstream.binance.com` use the
  explicit `--ws-disabled` flag, documented as **not** the Phase
  11C.1B all-market demon-radar acceptance path.
- The pre-flight refusal happens BEFORE the REST symbol resolution
  call so a host with no public Binance access at all surfaces the
  refusal cleanly.
- Module-level `_build_rest_transport(*, dry_run)` factory mirrors
  the WS factory; tests monkey-patch both to drive the runner
  end-to-end without any real network.
- Per-loop body:
  1. pump WS messages -> `radar_buffer.ingest_messages`;
  2. score every symbol with new state via
     `pre_anomaly_score_light` and offer to the pool;
  3. `pool.expire()`;
  4. when `ws_client.is_stale=True`: increment
     `ws_data_degraded_ticks` and SKIP the active-head iteration
     (no PRE_ANOMALY_DETECTED / ANOMALY_DETECTED /
     STATE_TRANSITION events on stale data; safety flags
     unchanged);
  5. otherwise drive `WSRadarChainDriver` on the active head;
  6. feed the active head into `PublicMarketIngestor.ingest_many`
     so the existing MARKET_SNAPSHOT / Phase 4 contract continues
     to fire for those symbols (gated by the PR-A rate-limit
     governor).
- Banner: `[AMA-RT] Phase 11C.1B - WebSocket-First All-Market
  Demon Coin Radar v1.4.0a11c.1b ...` now also reports
  `ws_real_transport=...`. Exit banner reports `ws_real_transport`
  + `ws_data_degraded_ticks` + WS metrics + radar candidates +
  governor metrics on shutdown.

#### Daily report (`app/paper_run/daily_report.py`)

- `DailyReportBuilder.build()` accepts new `ws_metrics` +
  `candidate_pool_metrics` kwargs.
- `DailyReportSnapshot` grew the brief-mandated WS / radar fields:
  `ws_messages_received`, `ws_messages_received_by_stream`,
  `ws_reconnect_count`, `ws_staleness_ms_max`, `ws_stale_count`,
  `ws_connect_count`, `ws_disconnect_count`, `ws_is_stale`,
  `radar_candidates_seen`, `candidate_pool_size_max`,
  `pre_anomaly_candidates`, `liquidation_events_seen`,
  `radar_score_top_symbols`, `ws_metrics`,
  `candidate_pool_metrics`.
- `_aggregate` cross-checks the event-log counts of
  `PUBLIC_WS_CONNECTED` / `PUBLIC_WS_DISCONNECTED` /
  `PUBLIC_WS_STALE` against the WS client's `metrics_payload` so a
  stale governor counter cannot hide a real connection event.
- The Markdown body has a new
  `## Phase 11C.1B WebSocket all-market radar` section + per-stream
  message counts + a top-N candidate-symbol table.

#### Phase 1 safety lock UNCHANGED

Phase 11C.1B does NOT touch the Phase 1 safety lock. After running
the WS-first pipeline end-to-end (with PRE_ANOMALY_DETECTED /
ANOMALY_DETECTED / STATE_TRANSITION + RISK_REJECTED chains driven
from real-time WS data) every flag below remains:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client.

#### Phase 11C.1B explicitly does NOT

- accept any Binance API key / API secret / `listenKey`.
- subscribe to any user data stream / private WebSocket / trading
  WebSocket API / account / margin / position / leverage / balance
  / order private WS variant.
- open the routed-private endpoint
  `wss://fstream.binance.com/private` or any
  `/ws-api` / `/ws-fapi` / `/ws-papi` / `/trading-api` /
  `/userDataStream` path-root variant. `/private` is on
  `FORBIDDEN_WS_PATH_ROOTS`; the path-root allowlist refuses it
  before connect runs.
- treat the unrouted `wss://fstream.binance.com/stream` URL as
  the WS-first acceptance path. Binance silently drops
  market-class streams over an unrouted connection (per the
  public-WS reference); the runner therefore opens routed PUBLIC
  + MARKET transports through the `MultiTransportPublicWSManager`.
- call any signed REST endpoint.
- connect to DeepSeek / a real Telegram bot / Binance Square.
- import any third-party HTTP / WebSocket / SDK package. The
  `StdlibPublicWSTransport` and `MultiTransportPublicWSManager`
  are implemented entirely on top of the
  Python standard library (`socket` + `ssl` + `select` + `struct`
  + `base64` + `hashlib` + `json` + `os.urandom`) and the existing
  source-tree audit (`tests/unit/test_phase11c_no_network.py`)
  continues to ban `websockets` / `websocket-client` / `aiohttp`
  / `requests` / `httpx` / `urllib3`.
- silently fall back to REST under `--ws-first` without
  `--dry-run`. The runner refuses with rc=2 if the real public WS
  transport cannot be constructed; only `--ws-disabled` switches
  to the REST-only path (which is **not** the Phase 11C.1B
  acceptance path).
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c_1b_ws_radar.py` (new, 28 cases)
  pinning every brief-mandated behaviour:
  - `test_public_ws_stream_allowlist`
  - `test_private_ws_forbidden`
  - `test_listen_key_forbidden`
  - `test_user_data_stream_forbidden`
  - `test_default_ws_config_is_conservative`
  - `test_all_market_ticker_updates_radar_snapshot`
  - `test_book_ticker_updates_spread`
  - `test_mark_price_updates_funding`
  - `test_force_order_sets_liquidation_event`
  - `test_radar_score_detects_price_volume_acceleration`
  - `test_radar_score_falls_back_to_insufficient_history`
  - `test_candidate_pool_adds_top_radar_symbols`
  - `test_candidate_pool_expires_old_candidates`
  - `test_candidate_pool_evicts_lowest_score_when_over_capacity`
  - `test_ws_stale_enters_data_degraded`
  - `test_ws_disconnect_emits_disconnected_event`
  - `test_ws_reconnect_count_increments`
  - `test_ws_first_runner_does_not_call_rest_detail_for_all_symbols`
  - `test_ws_disabled_runner_falls_back_to_pra`
  - `test_learning_ready_payload_from_ws_candidate`
  - `test_safety_flags_unchanged_with_ws_enabled`
  - `test_default_ws_transport_refuses_to_open_a_real_socket`
  - `test_ws_client_subscribe_refuses_private_streams`
  - `test_ws_metrics_payload_includes_brief_field_set`
  - `test_candidate_pool_metrics_payload_includes_brief_field_set`
  - `test_radar_score_attaches_liquidation_event_tag`
  - `test_volume_rank_jump_admits_into_candidate_pool`
  - `test_phase_11c_1b_files_exist`
- `tests/unit/test_phase11c_no_network.py` extended:
  PHASE_11C_FILES grew the four new files (`binance_public_ws.py`,
  `radar.py`, `candidate_pool.py`, `ws_radar_chain.py`).
  `FORBIDDEN_TOP_LEVEL_PACKAGES` keeps every third-party WS
  package (`websockets`, `websocket`, `websocket_client`) on the
  deny list. New `test_no_private_websocket_artefacts` blocks
  `listenKey` / `userDataStream` / `wss://stream-api` /
  `/ws-api` / `/trading-api` / `/userDataStream` / `/listenKey`
  as non-docstring string literals across the source set.
- `tests/unit/test_phase11b_no_network.py` extended: allowed
  event-type list grew `PUBLIC_WS_CONNECTED` /
  `PUBLIC_WS_DISCONNECTED` / `PUBLIC_WS_STALE` so the
  daily-report aggregator's references pass.
- `tests/unit/test_phase11c1a_rate_limit_governor.py` updated:
  `test_rest_not_called_for_all_symbols_every_loop` now passes
  `--ws-disabled` so the PR-A bootstrap-only assertion holds
  byte-for-byte verbatim.

Full test suite: **2144 passed** with PR-B applied. No
regressions in the existing 2089-test surface; PR-B adds 55 net
new passing tests.

### Phase 11C.1A - Binance Public REST Rate Limit Governor & 418 Protection

**Version:** `1.4.0a11c.1a` - Phase 11C.1A. Tracks the Phase 11C
real-data acceptance recovery PR-A.

The first 24h test of the Phase 11C runner against real Binance
public REST (`fapi.binance.com`) returned HTTP 429 (Too Many
Requests) and then HTTP 418 (I'm a teapot, IP ban) at the original
defaults (`symbol_limit=20`, `rest_poll_interval_seconds=5.0`, six
detail endpoints per symbol per loop). The Phase 1 safety lock held
throughout (`mode=paper`, `live_trading=False`, no API key, no
signed endpoint, no real order, no DeepSeek, no real Telegram
outbound), but the gateway was unusable for real-data acceptance.

This PR-A ships the rate-limit fix in three layers without
reducing妖币-discovery capability or breaking the Phase 11C
boundary.

#### New module: `app/exchanges/binance_rate_limit.py`

- `BinancePublicRestGovernor` - sliding-window weight budget,
  Retry-After respecting backoff, IP-ban protection mode.
  - `before_request(endpoint_path)` - reserves the planned weight,
    refuses the call if the hard budget is exhausted
    (:class:`RateLimitBudgetExceeded`), if a Retry-After backoff
    window is still active (:class:`RateLimitBackoffActive`), or if
    protection mode is latched (:class:`RateLimitProtectionError`).
  - `record_response(endpoint_path, PublicRestResponse)` - reads
    `X-MBX-USED-WEIGHT-1M` (case-insensitive); on HTTP 429 emits
    `RATE_LIMIT_429` + `RATE_LIMIT_BACKOFF_STARTED`, sleeps the
    Retry-After window (300 s default), emits
    `RATE_LIMIT_BACKOFF_ENDED`; on HTTP 418 emits `RATE_LIMIT_418` +
    `RATE_LIMIT_PROTECTION_ENTERED`, opens a P1 incident through
    the configured protection hook (:class:`IncidentRepository`),
    and raises :class:`RateLimitProtectionError`.
  - `record_transport_error(endpoint_path)` - releases the
    reserved weight when the transport raises before producing a
    response so the rolling-window budget does not double-bill.
  - `metrics_payload()` - JSON-safe counters for the daily report.
- `RestGovernorConfig` - frozen dataclass with conservative defaults:
  `weight_budget_per_minute=300`, `soft_weight_ratio=0.50`,
  `hard_weight_ratio=0.75`, `retry_after_default_seconds=300`,
  `on_429="backoff"`, `on_418="shutdown"`,
  `endpoint_weights=DEFAULT_ENDPOINT_WEIGHTS`. Refuses pathological
  values at construction time.
- `PublicRestResponse(body, status, headers)` - transport-agnostic
  response envelope.
- `RateLimitProtectionError` (subclass of `SafeModeViolation`),
  `RateLimitBackoffActive`, `RateLimitBudgetExceeded`.
- `DEFAULT_ENDPOINT_WEIGHTS` for the Phase 11C public-market subset
  (`/fapi/v1/exchangeInfo`=1, `/fapi/v1/ticker/24hr`=40,
  `/fapi/v1/ticker/bookTicker`=5, `/fapi/v1/depth`=20,
  `/fapi/v1/aggTrades`=20, `/fapi/v1/trades`=5, `/fapi/v1/klines`=5,
  `/fapi/v1/fundingRate`=1, `/fapi/v1/openInterest`=1,
  `/fapi/v1/premiumIndex`=1).

The whole module uses only the Python standard library + loguru.
No third-party HTTP / WebSocket / SDK is imported; no `os.environ`
is read; no credential parameter is accepted; no write surface is
defined.

#### Wired into `BinancePublicClient`

- `BinancePublicClient.__init__(governor=...)` - new optional kwarg.
  When wired, every public REST request goes through the governor
  before reaching the transport.
- `_default_transport` upgraded to capture HTTP status + headers
  and return :class:`PublicRestResponse`. HTTP 429 / 418 are NOT
  raised - the envelope is handed to the governor so it can read
  Retry-After / used-weight / decide what to do.
- `_request` flow now: allowlist check -> `governor.before_request`
  -> transport call -> `governor.record_response` -> 200 returns the
  body, 429 raises `ExchangeError` after the governor's backoff,
  418 raises :class:`RateLimitProtectionError`.

#### Conservative new defaults (`app/config/defaults.yaml`)

| Knob                                         | Old   | New (Phase 11C.1A) |
| -------------------------------------------- | ----- | ------------------ |
| `market_data.symbol_limit`                   | 20    | 5                  |
| `market_data.rest_poll_interval_seconds`     | 5.0   | 60.0               |
| `market_data.rest_governor.weight_budget_per_minute` | -     | 300                |
| `market_data.rest_governor.soft_weight_ratio`        | -     | 0.50               |
| `market_data.rest_governor.hard_weight_ratio`        | -     | 0.75               |
| `market_data.rest_governor.retry_after_default_seconds` | -    | 300                |
| `market_data.rest_governor.on_429`           | -     | `backoff`          |
| `market_data.rest_governor.on_418`           | -     | `shutdown`         |
| `market_data.rest_governor.candidate_detail_limit`   | -     | 3                  |
| `market_data.rest_governor.rest_layering_enabled`    | -     | true               |

Each value is enforced by a Pydantic validator on
`RestGovernorSection`; pathological knobs are refused at boot.

#### Layered REST runner (`scripts/run_public_market_paper.py`)

- New `--candidate-detail-limit N` CLI flag (default from settings,
  3).
- New `--legacy-detail-per-loop` flag - off by default; documented
  as the original "every endpoint for every symbol every tick"
  behaviour that triggered the 418. Kept only for back-compat
  smoke tests.
- The runner builds a `BinancePublicRestGovernor` (with the
  `IncidentRepository` as the protection hook) and passes it to
  the public client.
- Bootstrap: one `exchangeInfo` (or one `ticker/24hr`) at boot to
  resolve the symbol list. Per-loop body iterates only the
  candidate symbols (empty in PR-A; populated by Phase 11C.1B
  PR-B), capped at `candidate_detail_limit`.
- Per-loop invariants pinned: `client.assert_public_only()`;
  governor metrics snapshot copied into `_Phase11CRunStats`.
- Hard stop on `governor.in_protection_mode`; runner returns
  `rc=2` when `rate_limit_protection_triggered=True`.
- Default `--symbol-limit` lowered to 5.

#### Daily report (`app/paper_run/daily_report.py`)

- `DailyReportBuilder.build()` now accepts `rate_limit_metrics` and
  `ingestion_errors` kwargs.
- `DailyReportSnapshot` grew the fields the brief calls out:
  `rate_limit_429_count`, `rate_limit_418_count`,
  `retry_after_seconds_last`, `retry_after_seconds_total`,
  `used_weight_1m_last`, `used_weight_1m_max`,
  `rest_requests_total`, `rest_requests_skipped_by_budget`,
  `rate_limit_protection_triggered`, `rate_limit_ban`,
  `rate_limit_backoff_started_count`,
  `rate_limit_backoff_ended_count`, `ingestion_errors`,
  `rate_limit_metrics`.
- `_aggregate` cross-checks the event-log counts (RATE_LIMIT_429,
  RATE_LIMIT_418, RATE_LIMIT_BACKOFF_STARTED,
  RATE_LIMIT_BACKOFF_ENDED, RATE_LIMIT_PROTECTION_ENTERED) against
  the governor's counters and uses the larger value so a stale
  governor cannot hide a real protection event.
- The Markdown body has a new "Phase 11C.1A rate-limit governor"
  section with every required field.

#### Five new EventType entries (`app/core/events.py`)

```
RATE_LIMIT_429
RATE_LIMIT_BACKOFF_STARTED
RATE_LIMIT_BACKOFF_ENDED
RATE_LIMIT_418
RATE_LIMIT_PROTECTION_ENTERED
```

The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
pipelines accept the new types without code changes (asserted by
`test_export_service_handles_rate_limit_events`).

#### Phase 1 safety lock UNCHANGED

Phase 11C.1A does NOT touch the Phase 1 safety lock. After a 429
**or** a 418, the following all remain:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_private_credentials      = True
forbid_signed_endpoints         = True
forbid_trade_endpoints          = True
forbid_account_endpoints        = True
forbid_position_endpoints       = True
forbid_leverage_endpoints       = True
forbid_margin_endpoints         = True
forbid_live_trading             = True
forbid_right_tail               = True
forbid_llm_trade_decisions      = True
forbid_telegram_outbound        = True
```

The four ExchangeClientBase write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise :class:`SafeModeViolation` even after the governor has
latched into protection mode (asserted by
`test_phase_11c_write_surfaces_still_refuse_after_418`).

#### Phase 11C.1A explicitly does NOT

- ship the WebSocket-first all-market radar (PR-B).
- ship multi-candidate priority ranking (PR-B).
- ship cluster exposure control (PR-C).
- accept any Binance API key / API secret.
- call any signed endpoint.
- call any /order, /account, /position, /leverage, /margin endpoint.
- connect to DeepSeek.
- connect to a real Telegram bot.
- auto-retry after a 418.
- switch endpoints to evade a 418.
- rotate source IP to evade a 418.
- enter Phase 12.

#### Tests

- `tests/unit/test_phase11c1a_rate_limit_governor.py` (new, 16 cases)
  - `test_default_phase11c_polling_is_conservative`
  - `test_rest_governor_config_refuses_pathological_values`
  - `test_429_triggers_backoff_and_stops_batch`
  - `test_retry_after_header_is_respected`
  - `test_used_weight_header_is_recorded`
  - `test_418_triggers_shutdown_without_retry`
  - `test_rest_governor_blocks_when_budget_exceeded`
  - `test_governor_refuses_during_active_backoff`
  - `test_rest_not_called_for_all_symbols_every_loop`
  - `test_legacy_detail_per_loop_flag_re_enables_old_behaviour`
  - `test_no_live_trading_flags_after_429`
  - `test_no_live_trading_flags_after_418`
  - `test_phase_11c_write_surfaces_still_refuse_after_418`
  - `test_daily_report_contains_rate_limit_metrics`
  - `test_daily_report_after_418_marks_rate_limit_ban`
  - `test_export_service_handles_rate_limit_events`
- `tests/unit/test_phase11c_safety_flags.py` updated to assert the
  new defaults (`symbol_limit=5`, `rest_poll_interval_seconds=60.0`,
  `rest_governor.*`).
- `tests/unit/test_phase11c_runner.py` updated:
  `test_arg_parser_default_symbol_limit_is_5`.
- `tests/unit/test_phase11b_no_network.py` allow-list extended with
  the five new RATE_LIMIT_* event types (the daily report
  aggregator references but never emits them; emission lives in
  `app/exchanges/binance_rate_limit.py` which is NOT a paper_run
  file).

Full test suite: **2089 passed in 7.17s** with PR-A applied. No
regressions in the existing 2073-test surface.

### Phase 11C - Real Binance Public Market Data Read-Only Paper

**Version:** `1.4.0a11c` - Phase 11C - Real Binance Public Market
Data Read-Only Paper. **Closes Issue #11C.**

Phase 11C is the FIRST phase in the project allowed to talk to a
real exchange. It is **public-market read-only** ingestion of
Binance USDT-M perpetual futures data, driven through the existing
Phase 1 - 11B paper pipeline. Phase 11C is NOT live trading, NOT
connected to the trading API, NOT connected to DeepSeek, NOT
connected to a real Telegram bot, NOT a path into Phase 12.

#### Public surface

- `app/exchanges/binance_public.py`
  - `BinancePublicClient` - public-market read-only Binance USDT-M
    perpetual gateway. Subclasses `ExchangeClientBase`; the four
    write surfaces (`create_order`, `cancel_order`, `set_leverage`,
    `set_margin_mode`) inherit `SafeModeViolation` refusal
    unchanged. `get_account_snapshot` is overridden to raise
    `SafeModeViolation` explicitly. Constructor refuses `api_key` /
    `api_secret` and any credential-shaped `**kwargs`.
  - `assert_public_endpoint_allowed(url)` - hard endpoint allowlist.
    Refuses any path not in the public-market set, any URL on a
    non-Binance host, any `http://` URL, any URL carrying
    `signature` / `timestamp` / `recvWindow` / `apiKey`.
  - `PUBLIC_MARKET_ENDPOINT_ALLOWLIST` - the closed list of paths
    Phase 11C is allowed to call.
  - `FORBIDDEN_PRIVATE_ENDPOINTS` - explicit deny-list of trading /
    account / position / leverage / margin endpoints.
  - `PublicMarkPrice` - mark + index + last funding + next funding
    envelope from `/fapi/v1/premiumIndex`.

- `app/market_data_public/`
  - `PublicMarketIngestor` - drives REST polling against
    `BinancePublicClient`, feeds the `MarketDataBuffer`, and
    produces enriched `MarketSnapshot` objects (mark_price + fresh
    book ticker on top of the Phase 4 contract).
  - `PaperEventChainDriver` - emits the full Phase 11C event chain
    per `(symbol, snapshot)`. Attaches a Phase 8.5
    `LearningReadyContext` (opportunity / signal_snapshot /
    virtual_trade_plan / config_versions) to every `RISK_REJECTED`
    and `STATE_TRANSITION`.

- `scripts/run_public_market_paper.py`
  - `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20`
  - `python -m scripts.run_public_market_paper --duration 6h --symbol-limit 20`
  - `python -m scripts.run_public_market_paper --duration 24h --symbol-limit 20`
  - Runs the Phase 11B `EnvGuard` against `BINANCE_API_KEY`,
    `BINANCE_API_SECRET`, `TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY`,
    ... before opening any database. Refuses to start if any
    forbidden credential env-var is set non-empty.
  - Pins `client.assert_public_only()` on every loop tick.
  - Builds a daily Markdown report at
    `data/reports/phase11c/{date}-phase11c-public-market.md` on
    graceful shutdown.
  - `--dry-run` swaps the default `urllib.request` transport for an
    in-process deterministic transport so CI / smoke tests never
    touch the network.

#### New configuration

`app/config/defaults.yaml` gains two top-level sections, each
strictly validated by Pydantic field-validators in
`app/config/schema.py`:

- `market_data:` - `provider: binance_public` (only allowed value),
  `read_only: true` (cannot be flipped), `symbol_limit: 20` (in
  `(0, 200]`), `rest_base_url: https://fapi.binance.com`, plus
  feature flags for the public surfaces.
- `safety:` - 11 `forbid_*` flags. The schema raises
  `ValidationError` if any of them is loaded as `False`.

`Settings` exposes the Phase 11C convenience accessors
`Settings.market_data`, `Settings.safety`,
`Settings.telegram_outbound_enabled`.

#### No new EventType

Phase 11C reuses the existing Phase 1 - 10D vocabulary. The chain
emits `MARKET_SNAPSHOT`, `PRE_ANOMALY_DETECTED`,
`ANOMALY_DETECTED`, `LIQUIDITY_CHECKED`, `TRADE_CONFIRMED`,
`MANIPULATION_DETECTED`, `RISK_APPROVED` / `RISK_REJECTED`,
`STATE_TRANSITION` per symbol per tick.

#### Phase 11C boundary (every clause enforced by tests)

  1. **No live trading.** The five Phase 1 safety flags remain locked.
     `telegram_outbound_enabled` and `binance_private_api_enabled`
     are both False.
  2. **No API key.** The constructor refuses `api_key` /
     `api_secret`. `tests/unit/test_phase11c_binance_public_client.py`
     pins both refusal paths.
  3. **No signed endpoint.** Every URL goes through
     `assert_public_endpoint_allowed`. The function refuses every
     entry in `FORBIDDEN_PRIVATE_ENDPOINTS` and every URL carrying
     a `signature` / `timestamp` / `recvWindow` / `apiKey` query
     parameter.
  4. **No third-party HTTP / WebSocket / exchange / LLM / Telegram
     SDK.** Phase 11C uses `urllib.request` from the Python standard
     library only. `tests/unit/test_phase3_no_network.py` and
     `tests/unit/test_phase11c_no_network.py` AST-audit the source
     set.
  5. **The four ExchangeClientBase write surfaces remain refused.**
     Inherited from Phase 3.
  6. **`MarketDataConfig.read_only` cannot be set to False** at the
     schema layer.
  7. **`SafetyConfig.forbid_*` cannot be set to False** at the
     schema layer.
  8. **No `os.environ` read** anywhere in the Phase 11C source set.
     Env inspection is delegated to the Phase 11B `EnvGuard`.
  9. **No `create_order` / `cancel_order` / `set_leverage` /
     `set_margin_mode` call.** AST-audited.

#### Phase 11C does NOT implement

  - Real WebSocket transport (the `websocket_enabled` flag is
    accepted as a future-capability hook; Phase 11C ships the REST
    poller only).
  - Real account / position / equity persistence (the public client
    refuses every authenticated endpoint).
  - Any LLM / DeepSeek / Telegram / 币安广场 surface.
  - Phase 12. Passing Phase 11C does NOT authorise Phase 12.

#### Tests

  - `tests/unit/test_phase11c_binance_public_client.py` - construction,
    credential refusal, endpoint allowlist (positive + negative),
    read-only API behaviour, MarketSnapshot serialization.
  - `tests/unit/test_phase11c_event_chain.py` - end-to-end event
    chain + learning-ready payload + STATE_TRANSITION carries
    learning_ready.
  - `tests/unit/test_phase11c_safety_flags.py` - the five Phase 1
    flags + 11 Phase 11C `forbid_*` flags + write-surface refusal
    + LLM-decision boundary + signed-query-parameter refusal.
  - `tests/unit/test_phase11c_runner.py` - argparse, duration parser,
    dry-run smoke, env-guard refusal, host refusal.
  - `tests/unit/test_phase11c_no_network.py` - source-tree audit.
  - `tests/unit/test_phase11c_export_and_replay.py` - Phase 8.5
    export round-trip + Phase 10A replay round-trip + Phase 10B
    Reflection compatibility.
  - `tests/unit/test_phase11c_telegram_outbound.py` - reviewer-
    requested defence-in-depth on the
    `telegram_outbound_enabled` semantics. Pins:
    `Settings.telegram_outbound_enabled` reads
    `defaults.telegram.outbound_enabled`, NOT
    `defaults.telegram.enabled`; the schema refuses
    `outbound_enabled=True`; the Phase 11C runtime source set
    imports no real Telegram transport
    (:class:`TelegramHttpClient` /
    :class:`TelegramExportBridge` /
    :class:`TelegramCommandCenter`).

Total Phase 11C coverage: 112 new tests; 0 failures; full suite
2071 passed.

#### Phase 1 - 10D contracts that remain in force

All Phase 1 - 10D contracts remain in force unchanged. Phase 11C
ADDS one new exchange client + one new ingestion package + one new
runner + four documentation files; it does NOT modify any existing
event type, any existing schema field, or any existing safety
constant.

### Phase 10D - Telegram Outbound + Export Commands (Issue #10 Part 4)

**Version:** `1.4.0a10d` - Phase 10D - Telegram Outbound + Export Commands.

Phase 10D ships the operator-facing :mod:`app.telegram` outbound
layer plus the file-export bridge layered on top of the Phase 8.5
:class:`TestDataExportService`. **Closes Issue #10**.

Public surface
--------------

  - 10 production-grade formatters that replace the Phase 1
    placeholders: ``format_system_status``, ``format_market_regime``,
    ``format_candidate_symbol``, ``format_state_transition``,
    ``format_order_event``, ``format_risk_rejection``,
    ``format_profit_lock``, ``format_capital_rebase``,
    ``format_incident_alert``, ``format_daily_report``. Every
    formatter is a pure function (string in, string out, no IO),
    short, banner-tagged with ``mode=PAPER|LIVE_LIMITED|LIVE``,
    redacted, and free of trade-decision side effects. The
    risk-rejection formatter MUST surface six high-priority reasons
    when present: ``stop_unconfirmed``, ``unknown_position``,
    ``rebase_in_progress``, ``manipulation_m3``, ``data_degraded``,
    ``no_exit_channel``.
  - :class:`TelegramOutboundClient` ABC + :class:`FakeTelegramClient`
    (deterministic in-process recorder; default transport for paper
    mode) + :class:`TelegramHttpClient` (refusal-only HTTP skeleton -
    every call raises :class:`TelegramTransportError`; the real
    transport ships behind Spec §41 Go/No-Go in a separate PR).
  - :class:`AlertDispatcher` proactive push pipeline. Per-key
    cooldown + dedupe; ``AlertSeverity`` ladder (INFO / WARNING /
    CRITICAL); CRITICAL bypasses cooldown; auto-promotion of
    ``stop_unconfirmed`` / ``unknown_position`` to CRITICAL;
    aggregation of low-severity risk rejections into a rolling
    10-minute summary; defence-in-depth redaction gate via
    :func:`app.exports.redaction.assert_no_forbidden_substrings`.
  - :class:`TelegramCommandCenter` 16-command operator surface:
    ``/status`` ``/positions`` ``/pnl`` ``/risk`` ``/capital``
    ``/incidents`` ``/pause`` ``/resume`` ``/kill_all`` ``/rebase``
    + 6 ``/export_*`` commands. Operator allow-list, two-step
    confirmation for ``/resume`` + ``/rebase``, audit events for
    every command (``TELEGRAM_COMMAND_RECEIVED``,
    ``TELEGRAM_COMMAND_REJECTED``).
  - :class:`TelegramExportBridge` connects ``/export_*`` to the
    Phase 8.5 :class:`TestDataExportService`. Sends a SHORT
    generating-summary caption + the redacted ``.zip`` document
    attachment in a single ``send_document`` call. Refuses
    chat-dump of raw JSONL/CSV. Audit events:
    ``DATA_EXPORT_GENERATED`` / ``DATA_EXPORT_FAILED``.

Five new EventType values
-------------------------

  - ``TELEGRAM_COMMAND_REJECTED`` - non-admin / unknown command paths
  - ``TELEGRAM_MESSAGE_SENT`` - every successful proactive push
  - ``TELEGRAM_SEND_FAILED`` - every transport / redaction failure
  - ``DATA_EXPORT_GENERATED`` - successful ``/export_*`` zip + send
  - ``DATA_EXPORT_FAILED`` - every export failure path

Boot drill (`python -m app.main`)
---------------------------------

```
[AMA-RT] Phase 10D - Telegram Outbound + Export Commands v1.4.0a10d \
  mode=paper live_trading=False right_tail=False llm=False \
  exchange_live_orders=False ... (Phase 1-10C fields unchanged) ... \
  telegram_outbound_enabled=False telegram_messages_sent=10 \
  telegram_documents_sent=1 telegram_send_failed_count=0 \
  telegram_redaction_blocked=0 telegram_message_sent_events=11 \
  telegram_send_failed_events=0 telegram_command_rejected_events=1 \
  data_export_generated=1 data_export_failed=0 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

The Phase 10D self-check runs after the Phase 10C self-check. It:

  - dispatches one alert through every formatter (10 messages_sent),
  - drives one ``/export_test_data 24h`` end-to-end through the
    bridge (1 documents_sent + 1 ``DATA_EXPORT_GENERATED``),
  - drives one unauthorised ``/status`` (1 ``TELEGRAM_COMMAND_REJECTED``),
  - asserts zero ``TELEGRAM_SEND_FAILED``, zero ``redaction_blocked``,
  - asserts every recorded outbound call is free of forbidden
    literals (``BINANCE_API_KEY=``, ``TELEGRAM_BOT_TOKEN=``, etc.),
  - registers a new ``telegram_outbound`` health probe (always OK
    when the transport is the FakeClient).

Phase 10D boundary (every clause enforced by tests)
---------------------------------------------------

  1. **No real network call.** The default outbound transport is
     :class:`FakeTelegramClient`. The :class:`TelegramHttpClient` is
     a refusal-only skeleton; even when ``outbound_enabled=True``
     and ``token_provided=True`` it raises
     :class:`TelegramTransportError`.
  2. **No write surface.** No file under ``app/telegram/`` defines
     ``create_order`` / ``cancel_order`` / ``set_leverage`` /
     ``set_margin_mode``.
  3. **No Telegram command bypasses the Risk Engine.** ``/pause`` /
     ``/resume`` flip an in-process advisory flag only.
  4. **``/kill_all``** records audit events but does NOT call any
     real exchange write surface in Phase 10D.
  5. **``/rebase``** does NOT execute a real withdrawal; the Phase 8
     Capital Flow Engine remains the only entry point.
  6. **No state-mutating component import** under
     ``app/telegram/``. AST scan blocks ``RiskEngine`` /
     ``ExecutionFSMDriver`` / ``CapitalFlowEngine`` / etc.
  7. **No third-party Telegram bot library imported.** AST scan
     blocks ``python_telegram_bot`` / ``telebot`` / ``aiogram``.
  8. **No HTTP / WebSocket library imported.** AST scan blocks
     ``aiohttp`` / ``httpx`` / ``requests`` / ``websockets``.
  9. **No exchange / LLM SDK imported.** AST scan blocks ``ccxt`` /
     ``binance`` / ``openai`` / ``anthropic`` / ``deepseek``.
  10. **No ``os.environ`` reads.** Credentials must be passed in
      explicitly. AST scan blocks ``os.environ.get`` / ``os.getenv``
      / bare ``getenv()``.
  11. **No hard-coded secret.** AST scan blocks ``api_key`` /
      ``api_secret`` / ``bot_token`` / ``telegram_token`` parameters
      or concrete env-var literals.
  12. **No exception escapes.** Dispatcher / command center /
      export bridge NEVER raise into the caller.
  13. **No raw chat dump.** The bridge attaches the ``.zip`` as a
      Telegram document; ``ExportError`` / size-cap exceeded paths
      reply with a SHORT error message and write
      ``DATA_EXPORT_FAILED``.
  14. **Defence-in-depth redaction.** Every outbound message goes
      through :func:`app.exports.redaction.assert_no_forbidden_substrings`
      before reaching the transport.
  15. **The Phase 1 safety lock remains in force.**

Tests
-----

Phase 10D adds the following test files under ``tests/unit/``:

  - ``test_telegram_formatter.py`` (rewritten): 10 formatters, every
    mandatory tag, every high-priority risk-rejection reason,
    redaction smoke tests, mode banner + live flag.
  - ``test_telegram_outbound.py``: ABC cannot be instantiated;
    FakeTelegramClient records calls; HTTP refuses; failure
    injection.
  - ``test_telegram_alerts.py``: throttle / dedupe / severity ladder
    / cooldown / P0 bypass / aggregation flush / redaction gate.
  - ``test_telegram_command_center.py`` (extends Phase 1): 16
    commands; allow-list; two-step confirmation; audit events;
    ``/kill_all`` / ``/rebase`` paper-mode safety.
  - ``test_telegram_export_bridge.py``: ``/export_*`` -> service ->
    generating caption + sendDocument; ``DATA_EXPORT_GENERATED`` /
    ``DATA_EXPORT_FAILED``; size-cap refusal path.
  - ``test_phase10d_boundary.py``: cumulative defence-in-depth pins.
  - ``test_phase10d_no_network.py``: per-file AST scan of
    ``app/telegram/``.

Live trading risk: NONE.

  - ``requirements.txt`` and ``pyproject.toml`` contain no exchange
    SDK, no HTTP / WebSocket / LLM client, no Telegram bot library.
  - No source under ``app/telegram/`` imports ``ccxt``, ``binance``,
    ``aiohttp``, ``websockets``, ``requests``, ``httpx``,
    ``openai``, ``anthropic``, ``deepseek``,
    ``python_telegram_bot``, ``telebot``, or ``aiogram``.
  - No source under ``app/telegram/`` defines ``create_order`` /
    ``cancel_order`` / ``set_leverage`` / ``set_margin_mode``.
  - No source under ``app/telegram/`` reads ``os.environ`` or
    declares an ``api_key`` / ``api_secret`` / ``bot_token``
    parameter / concrete env-var literal.
  - The Phase 1 safety lock and every later boundary remain
    unchanged.

Real exchange order risk: NONE. ``/kill_all`` and ``/rebase`` write
audit events only. The four :class:`ExchangeClientBase` write
surfaces continue to raise :class:`SafeModeViolation`.

Telegram token leak risk: NONE. No token parameter or literal
anywhere under ``app/telegram/``. The :class:`TelegramHttpClient`
constructor accepts a boolean ``token_provided`` flag instead of a
real token.

LLM overreach risk: NONE. Phase 10D does NOT call the LLM Guarded
Interpreter; the Risk Engine remains the single trading-decision
gate.

### Phase 10C - LLM Guarded Interpreter (Issue #10 Part 3)

**Version:** `1.4.0a10c` - Phase 10C - LLM Guarded Interpreter.

Phase 10C adds the receive-only :mod:`app.llm` package: a sandboxed,
schema-validated, never-trading LLM intelligence layer that
compresses community / catalyst / narrative text into a small,
strictly typed intelligence payload (Spec §22). The output is
*purely informational*; it never carries a trade direction, a
leverage, a target price, an order, a stop, or any other field that
could move money. The Risk Engine remains the single gate.

Public surface
--------------

  - `LLMGuardedInterpreter` - top-level orchestrator. Constructor
    is keyword-only: `(*, client, event_repo=None, config=None,
    cache=None, llm_enabled=False)`. `interpret(input)` NEVER
    raises into the caller; every transport / schema / guardrail
    failure becomes a degraded :class:`LLMInterpretationResult`.
  - `LLMInterpreterConfig` - tunable thresholds (Spec §22.4
    anomaly-score throttle: <60 -> SKIP, 60-75 -> LIGHT,
    75-90 -> STANDARD, >=90 -> FULL).
  - `LLMTokenBucket` - in-process Spec §22.4 throttle classifier.
  - `LLMInterpretationInput` / `LLMInterpretationResult` - frozen
    dataclasses; `to_payload()` is JSON-safe and provably free of
    forbidden trade-action fields.
  - `FakeLLMClient` - deterministic in-memory transport used by
    tests AND the boot self-check.
  - `DeepSeekClient` - refusal-only skeleton. Refuses unless
    `llm_enabled=True` AND `api_key_provided=True`; refuses anyway
    in Phase 10C. The real adapter ships behind Spec §41 Go/No-Go.
  - `LLMCache` - LRU cache keyed on `(input_hash, prompt_version,
    schema_version, model_name, throttle_tier, symbol)`. **Refuses
    to store credential keys**.
  - `validate_llm_output` - pure-function Spec §22.2 schema
    validator. No external dependency (we deliberately do NOT add
    `jsonschema` to `requirements.txt`).
  - `sanitize_input_text` - light-touch input cleaner (NFC, control
    chars, whitespace, max-len). Preserves prompt-injection markers
    so the detector can still flag them.
  - `detect_prompt_injection` - 12-pattern regex sniffer.
  - `enforce_field_whitelist` - drops any output key outside the
    Spec §22.2 closed schema.
  - `strip_forbidden_fields` - drops + records any trade-action
    key (`direction`, `leverage`, `position_size`, `target_price`,
    `order_type`, `stop_price`, `take_profit`, `should_buy`,
    `should_short`, `trade_decision`, `entry`, `exit`,
    `liquidation_price`, `margin_mode`, `risk_budget`, `order`,
    `signal_to_trade`).
  - Three new EventType values: `LLM_INTERPRETED`, `LLM_DEGRADED`,
    `LLM_SCHEMA_REJECTED`. The interpreter is the only Phase 10C
    write surface; tests assert it is limited to these three event
    types.

Boot drill (`python -m app.main`)
---------------------------------

```
[AMA-RT] Phase 10C - LLM Guarded Interpreter v1.4.0a10c mode=paper \
  live_trading=False right_tail=False llm=False exchange_live_orders=False \
  ... (Phase 1-10B fields unchanged) ... \
  llm_interpreter_degraded=True llm_interpreter_reasons=llm_disabled \
  llm_events=1 llm_degraded_count=1 llm_interpreted_events=0 \
  llm_degraded_events=1 llm_schema_rejected_events=0 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

The boot self-check exercises the interpreter end-to-end against a
deterministic :class:`FakeLLMClient` with `llm_enabled=False`. It
asserts:

  - `result.degraded == True`
  - `'llm_disabled' in result.degraded_reason_values`
  - `result.to_payload()` is free of forbidden trade-action fields
  - `fake_llm_client.calls == 0` (the transport was NOT invoked)
  - exactly one `LLM_DEGRADED` event was written to `events.db`

Phase 10C boundary
------------------

1. **No real network call by default.** No `aiohttp` / `httpx` /
   `requests` / `websockets` / `ccxt` / `binance` / `openai` /
   `anthropic` / `deepseek` import anywhere under `app/llm/`. The
   default transport is `FakeLLMClient`.
2. **No write surface.** No file under `app/llm/` defines
   `create_order` / `cancel_order` / `set_leverage` /
   `set_margin_mode`.
3. **No LLM-driven trade action.** Closed output schema; forbidden
   fields stripped + recorded; result degraded if any forbidden
   field was present.
4. **No state-mutating component import.** No `RiskEngine`,
   `ExecutionFSMDriver`, `Reconciler`, `CapitalFlowEngine`,
   `IncidentRepository`, `MockExchangeClient`, `BinanceClient`,
   `MarketDataBuffer`, `TelegramCommandCenter`, `RegimeEngine`.
5. **No `os.environ` reads.** Credentials must be passed in
   explicitly by the caller.
6. **No hard-coded secret.** No `api_key` / `api_secret` /
   `bot_token` parameter or concrete literal anywhere under
   `app/llm/`.
7. **No exception escapes.** The interpreter NEVER raises into the
   caller.
8. **No Telegram outbound.** Phase 10D owns that surface.
9. **No Issue #10 Part 10D work.**
10. **Phase 1 safety lock unchanged.** `llm_enabled` stays
    `False` at boot.

Tests
-----

Phase 10C adds nine new test files under `tests/unit/`:

  - `test_llm_models.py` - vocabularies + result schema pinned
  - `test_llm_schema.py` - validator behaviour
  - `test_llm_prompts.py` - system prompt content + version pinned
  - `test_llm_guardrails.py` - whitelist / forbidden / injection
    detector / sanitizer
  - `test_llm_cache.py` - LRU + credential refusal
  - `test_llm_client.py` - FakeLLMClient + DeepSeekClient skeleton
  - `test_llm_interpreter.py` - end-to-end (Issue acceptance #1-#18)
  - `test_phase10c_boundary.py` - cumulative defence-in-depth
  - `test_phase10c_no_network.py` - per-file AST scan

`tests/unit/test_main_entrypoint.py` extended to assert the
Phase 10C banner string and the LLM event counts.

Live trading risk
-----------------

**None.** No new exchange SDK, no HTTP / WebSocket / LLM client, no
Telegram bot library is added. The four `ExchangeClientBase` write
surfaces continue to raise `SafeModeViolation`. Phase 1 safety
lock remains in force.

LLM overreach risk
------------------

**None.** Phase 10C does NOT introduce a real LLM transport. The
`DeepSeekClient` is a refusal-only skeleton; even when
`llm_enabled=True` and `api_key_provided=True` it raises
`TransportError`. The result schema is closed; the guardrail
strips every forbidden trade-action field; the orchestrator never
calls the Risk Engine, the Execution FSM, the Capital Flow Engine,
or any write surface.


### Phase 10B - Reflection Engine (Issue #10 Part 2)

Phase 10B delivers the read-only Reflection Engine on top of the
Phase 10A Replay Engine. The engine consumes one
`PaperTradeReplay` plus the surrounding Phase 10A risk / state /
incident replays plus the Phase 8.5 `learning_ready` payload, and
produces one structured `ReflectionResult` per paper-trade
lifecycle. The result carries a typed `mistake_tags` list (drawn
from a frozen 12-issue + 3-diagnostic vocabulary - **no
free-form natural-language reflection** is produced),
deterministic MFE / MAE / `tail_contribution` metrics
(`None` when data is insufficient, NEVER fabricated), and four
`QualityScore` axes. This is **Part 2 of 4** of Issue #10; Parts
10C (LLM Guarded Interpreter) and 10D (Telegram outbound +
Export commands) ship in separate PRs. Issue #10 will be closed
by Part 10D.

#### Added

##### `app/reflection/` - Reflection Engine

- `ReflectionEngine(replay=, event_repo=, config=)` - read-only
  constructor. Construct from a wired `ReplayEngine` (preferred)
  or from an `EventRepository` (the engine will build its own
  ReplayEngine). Phase 10B does NOT re-implement Replay; it
  consumes the existing Phase 10A surface.
- `ReflectionEngine.reflect_paper_trade(client_order_id=,
  opportunity_id=)` - reflect on one paper-trade lifecycle,
  identified by either key. The engine asks Replay for the
  surrounding context (risk decisions for the symbol, state
  transitions for the symbol, P0 incidents in the window).
- `ReflectionEngine.reflect(input)` - lower-level entry point
  taking a `ReflectionInput` directly; tests use this to inject
  hand-crafted context.
- `ReflectionConfig` - tunable thresholds for tag-rule firing
  (`late_entry_pct`, `slippage_overrun_pct`,
  `execution_delay_ms`, `weak_volume_anomaly_threshold`,
  `trap_score_threshold`).

##### Value objects

- `ReflectionResult` - frozen dataclass with the Issue-mandated
  field set: `opportunity_id`, `client_order_id`, `symbol`,
  `setup`, `result`, `mistake_tags`, `mfe`, `mae`,
  `tail_contribution`, `entry_quality`, `exit_quality`,
  `risk_process_quality`, `execution_quality`,
  `data_quality_notes`, `source_event_ids`, `learning_ready`,
  `generated_at`. JSON-safe via `to_payload()`.
- `ReflectionInput` - frozen dataclass bundling
  `paper_trade: PaperTradeReplay` plus optional
  `risk_decisions`, `state_transitions`, `incidents`,
  `learning_ready` so callers can drive the engine without
  Replay re-reading events.db.
- `QualityScore` - HIGH / MEDIUM / LOW / UNKNOWN.
- `TradeOutcome` - WIN / LOSS / BREAKEVEN / PROTECTED / OPEN /
  UNKNOWN.
- `UnknownReason` - typed "data insufficient" reason vocabulary
  (11 reasons; the engine NEVER invents a free-form reason).

##### Mistake-tag vocabulary

- `MistakeTag` - frozen 15-value enum:

  Issue-required (12):
  `late_entry`, `early_exit`, `weak_volume`, `fake_breakout`,
  `high_trap_score`, `ignored_no_trade_gate`, `slippage_error`,
  `execution_delay`, `stop_not_confirmed`, `tail_saved_trade`,
  `tail_failed`, `right_tail_success`.

  Diagnostic (Phase 10B):
  `insufficient_data`, `no_lifecycle_observed`,
  `incident_during_lifecycle`.

- `ISSUE_REQUIRED_MISTAKE_TAGS` / `DIAGNOSTIC_MISTAKE_TAGS`
  frozensets so consumers can iterate / filter without
  re-listing the strings.

##### Metric helpers (deterministic)

- `compute_mfe(events, *, direction_long=, entry_price=)` -
  Maximum Favourable Excursion as an absolute price delta.
  Returns `MetricResult(value=None,
  unknown_reasons=(...))` when fewer than two price observations
  are available (Phase 9 paper-mode landmarks-only case) or
  when no fill price is recorded.
- `compute_mae(events, ...)` - Maximum Adverse Excursion;
  same insufficient-data semantics.
- `compute_tail_contribution(events=, state_transitions=,
  realized_pnl=, virtual_trade_plan=)` - tail PnL attribution.
  Returns 0.0 when no `RIGHT_TAIL_AMPLIFY` lifecycle was
  observed AND a virtual_trade_plan was supplied (we can confidently
  say zero); returns `None` when no RTA was observed AND no plan
  is available.
- `realized_pnl_for(events)` - read realised PnL off the closing
  event payload.
- `MetricResult` - `value: float | None` plus
  `unknown_reasons: tuple[UnknownReason, ...]`.

##### Tag-rule emission rules

- `stop_not_confirmed`: `summary.stop_confirmed == False` OR a
  `STOP_FAILED` event landed in the lifecycle.
- `ignored_no_trade_gate`: a `RISK_REJECTED` for the same
  `opportunity_id` precedes an `ORDER_SENT` for the same
  `opportunity_id`. (This MUST NOT happen in Phase 9; the tag
  fires loudly if it does.)
- `slippage_error`: `|fill_price - limit_price| / limit_price`
  exceeds the request's `max_slippage_pct` AND the engine-level
  threshold (defence in depth).
- `execution_delay`: `ack_ts - sent_ts` exceeds
  `ReflectionConfig.execution_delay_ms` (default 1500ms).
- `late_entry`: `|fill_price - virtual_entry| / virtual_entry`
  exceeds `ReflectionConfig.late_entry_pct` (default 0.5%).
  Requires `virtual_trade_plan`; otherwise unknown.
- `weak_volume`: `signal_snapshot.anomaly_score` below
  `ReflectionConfig.weak_volume_anomaly_threshold` (default
  50.0). Requires `signal_snapshot`; otherwise unknown.
- `high_trap_score`: `signal_snapshot.trap_score` >=
  `ReflectionConfig.trap_score_threshold` (default 0.6) OR
  `signal_snapshot.no_trade_reason` contains a `trap` substring.
- `fake_breakout`: state chain shows a transition INTO
  `confirm` / `attack` followed immediately by a transition INTO
  `observe` / `scout` / `no_trade`.
- `tail_saved_trade`: lifecycle entered `right_tail_amplify`
  AND closed with `realized_pnl > 0`.
- `tail_failed`: lifecycle entered `right_tail_amplify` AND
  closed with `realized_pnl < 0`.
- `right_tail_success`: lifecycle entered `right_tail_amplify`
  AND a recorded mark / last / exit price reached or exceeded
  `virtual_trade_plan.virtual_tp2`.
- `early_exit`: position closed below `virtual_tp1` (LONG plan)
  or above it (SHORT plan). Requires plan + close price.
- `incident_during_lifecycle`: any incident's open / resolve
  timestamp falls inside the lifecycle window, or the incident
  window straddles the lifecycle.
- `insufficient_data`: any data-quality note landed AND no
  Issue-required tag fired.

##### Boot drill (`python -m app.main`)

The entrypoint runs the Phase 10B self-check **after** the
Phase 10A self-check. The self-check reflects on the boot
paper-trade lifecycle and asserts:

  - the result is `breakeven` (boot drill closes at PnL=0);
  - the `client_order_id` matches the boot order;
  - `source_event_ids` is non-empty;
  - no Issue-required `mistake_tag` fires (the diagnostic
    `insufficient_data` tag MAY fire because the boot drill
    does not attach a `virtual_trade_plan` / `signal_snapshot`,
    which is an honest "we cannot tell" signal).

If any of these contracts diverges, the entrypoint refuses to
print the banner and exits non-zero.

The boot banner gains four Phase 10B fields:

```
reflection_setup=unknown reflection_result=breakeven
reflection_mistake_tags=1 reflection_data_quality_notes=4
```

A new `reflection_engine` health probe registers `OK` when no
Issue-required `mistake_tag` fired, `DEGRADED` otherwise.

##### Documentation + version bump

- `app/__init__.py` -> `1.4.0a10b` /
  `Phase 10B - Reflection Engine`.
- `pyproject.toml` -> `1.4.0a10b`.
- `README.md` -> Phase 10B deliverable + boundary section +
  status table updated (Phase 10A marked merged with PR #23,
  Phase 10B = "this branch", Parts 10C / 10D listed as open).
- `docs/CHANGELOG.md` -> Phase 10B entry prepended; Phase 10A
  entry preserved verbatim below.

#### Phase 10B boundary

1. **Read-only.** Reflection imports no state-mutating
   component (no `CapitalFlowEngine`, no `ExecutionFSMDriver`,
   no `Reconciler`, no `RiskEngine`, no `IncidentRepository`,
   no `MockExchangeClient`, no `BinanceClient`, no
   `MarketDataBuffer`, no `TelegramCommandCenter`, no
   `RegimeEngine`). AST scan enforces this on every file under
   `app/reflection/`.
2. **No write surface.** No file under `app/reflection/`
   defines `create_order` / `cancel_order` / `set_leverage` /
   `set_margin_mode`. AST scan enforces this.
3. **No `EventRepository.append_event` / `append_many`** call
   anywhere in `app/reflection/`. AST scan enforces this; the
   boot self-check confirms `events.count` is unchanged after
   the Reflection self-check runs.
4. **No socket / no exchange SDK / no LLM client / no Telegram
   bot library.** AST scan enforces this against every `.py`
   file under `app/reflection/`.
5. **No `os.environ` / `getenv` reads** anywhere in
   `app/reflection/`. AST scan enforces this.
6. **No `api_key` / `api_secret` / `bot_token` parameter or
   concrete literal** anywhere in `app/reflection/`. AST scan
   enforces this.
7. **Read-only against `events.db` only.** No file under
   `app/reflection/` opens any other database directly.
8. **No Issue #10 Part 10C / 10D work.** No LLM client, no
   Telegram outbound, no Export commands.
9. **No free-form natural-language reflection.** Every
   observation lands as one of the values in `MistakeTag`.

#### Defence in depth (cumulative, all unit-tested)

1. `app/config/settings.py::_apply_phase1_safety_lock()`
   overwrites the five flags after YAML + env loading.
2. `app/main.py::_assert_phase1_safety()` raises
   `SafetyViolation` at boot if any flag has drifted.
3. `app/main.py::_assert_phase3_read_only()` probes every
   banned write surface and raises `SafeModeViolation` if any
   of them stops refusing.
4. `app/main.py::_assert_phase9_no_live_writes()` confirms the
   FSM driver constructed under paper-mode flags.
5. `app/risk/engine.py` rejects `live_trading_required=True`,
   `right_tail_amplify=True`, every Phase 6 / 7 / 8 hard-rule
   branch.
6. `app/exchanges/base.py::ExchangeClientBase.{create_order,
   cancel_order, set_leverage, set_margin_mode}` always raise
   `SafeModeViolation`.
7. `app/execution/fsm.py::ExecutionFSMDriver.__init__` raises
   `SafeModeViolation` if any of the three trading flags has
   drifted.
8. `MarginMode` enum cannot construct a cross-margin
   `OrderRequest` even via typo.
9. `StopEvent` cannot construct a non-reduce-only stop even
   via typo.
10. **Phase 10A:** AST scans on every `.py` under
    `app/replay/` enforce no network / no SDK / no API key /
    no write surface / no `os.environ` / no
    `EventRepository.append_event` / no state-mutating
    component import.
11. **Phase 10B adds:** AST scans on every `.py` under
    `app/reflection/` enforce the same set of clauses, plus
    no LLM client import (deferred to Part 10C), no
    `MistakeTag` / `ReflectionResult` mutation surface (the
    value objects are frozen).

#### Live trading risk

**None.** Phase 10B adds no new `create_order` / `cancel_order`
/ `set_leverage` / `set_margin_mode` call site. The four
`SafeModeViolation` refusals on `ExchangeClientBase` continue
to apply.

### Phase 10A - Replay Engine (Issue #10 Part 1)

Phase 10A delivers the read-only Replay Engine on top of every
Phase 1-9 contract. The engine reconstructs paper trade
lifecycles, capital rebases, risk decisions, P0 incidents, trade
state transitions, telegram commands, and Phase 8.5
learning-ready payloads from `events.db`, plus a P0 latched-pause
invariant verifier that audits the Phase 9 fix-up rule (PR #22).
This is **Part 1 of 4** of Issue #10; Parts 10B (Reflection),
10C (LLM Guarded Interpreter) and 10D (Telegram outbound +
Export commands) ship in separate PRs.

#### Added

##### `app/replay/` - Replay Engine

- `ReplayEngine(event_repo)` - read-only constructor. The engine
  holds an :class:`EventRepository` reference but never writes
  through it. The constructor signature is pinned: a single
  keyword-only `event_repo` parameter and nothing else. No
  exchange client, no capital flow engine, no risk engine, no
  market data buffer, no Telegram bot, no LLM client.
- Replay value objects (frozen dataclasses, all expose
  `to_payload()` for JSON-safe serialisation):
    - `PaperTradeReplay` - the Phase 9 paper trade lifecycle
      reconstructed from `events.db`. Carries the
      :class:`PaperLifecycleSummary` produced by the existing
      `reconstruct_paper_lifecycle` helper plus a
      :class:`ReplayDiffReport` that compares the observed event
      chain against the canonical Phase 9 happy-path ordering.
    - `CapitalRebaseReplay` - one capital rebase plus the
      surrounding `CAPITAL_DEPOSIT` / `CAPITAL_WITHDRAWAL` /
      `PROFIT_HARVEST` / `RISK_BUDGET_RECALCULATED` events that
      land within a 50ms window of the rebase.
    - `RiskDecisionReplay` - one `RISK_APPROVED` /
      `RISK_REJECTED` event with every Phase 7 / Phase 8.5
      payload field surfaced as a typed attribute, plus the
      Phase 8.5 `learning_ready` block (read back exactly as
      Phase 8.5 wrote it).
    - `IncidentReplay` - one incident lifecycle (OPEN +
      optional RESOLVE + protection-mode entered/exited window)
      reconstructed from `events.db` alone. The PROTECTION_MODE
      events are scoped to the incident's open-to-resolve
      window when an `incident_id` filter is supplied.
    - `StateTransitionReplay` - the Phase 7 trade-state ladder
      for one symbol (or all symbols).
    - `TelegramCommandReplay` - one
      `TELEGRAM_COMMAND_RECEIVED` event reconstructed; ready
      for Phase 10D.
    - `LearningReadyReplay` - the Phase 8.5 learning-ready
      block extracted from one event, with `has_opportunity` /
      `has_signal_snapshot` / `has_virtual_trade_plan` /
      `has_config_versions` / `has_risk_decision` projections.
    - `P0LatchedPauseInvariantReport` - audit over a sequence
      of `RECONCILIATION_RESOLVED` events. Flags any clean pass
      that reports `has_open_p0_incident=True` /
      `protection_mode_active=True` and
      `new_opens_paused=False`, or `p0_latched_pause=True` with
      any blocker active and `new_opens_paused=False`.
- Diff infrastructure (`app/replay/diff.py`):
    - `DiffKind` (`MATCH`, `MISSING`, `EXTRA`, `REORDERED`).
    - `DiffEntry` and `ReplayDiffReport` (frozen dataclasses).
    - `compare_event_chains(expected, observed, *, label)` -
      pure-function structural diff over two event-type chains.
      Uses :class:`difflib.SequenceMatcher` so the result is
      deterministic across runs.
- Read-only loaders (`app/replay/loaders.py`) - one helper per
  Phase 9 lifecycle group:
    - `load_all_events`, `stream_events` (lazy iterator)
    - `load_events_for_order`, `load_events_for_position`,
      `load_events_for_symbol`, `load_events_for_opportunity`
    - `load_capital_flow_events`, `load_risk_decision_events`,
      `load_incident_lifecycle_events`,
      `load_state_transition_events`,
      `load_telegram_command_events`,
      `load_reconciliation_events`
    - `has_learning_ready`, `extract_learning_ready` (returns a
      shallow copy so callers cannot mutate source payloads),
      `opportunity_id_for`
    - `pair_reconciliation_passes` - groups
      `RECONCILIATION_STARTED` / `RECONCILIATION_MISMATCH` /
      `RECONCILIATION_RESOLVED` triplets by their `started_at`
      payload key.
- Canonical chains pinned at module level so future PRs cannot
  silently drift them: `CANONICAL_CLOSED_PAPER_TRADE_CHAIN`,
  `CANONICAL_OPEN_PAPER_TRADE_CHAIN`. The Replay diff
  normalises the observed chain into canonical progression
  order before comparing because Phase 9 emits the entire paper
  trade lifecycle inside a single millisecond and
  `EventRepository` ties on `(timestamp, event_id)` where the
  secondary sort is a random UUID.

##### Boot drill (`python -m app.main`)

The entrypoint runs the Phase 10A self-check after the Phase 9
paper-trade and reconciliation drill. It exercises every public
replay surface:

  - replay the boot paper trade (must match the canonical chain),
  - confirm at least one capital event landed,
  - replay the bootstrap RISK_APPROVED decision,
  - confirm zero P0 incidents,
  - replay the boot STATE_TRANSITION ladder,
  - replay the boot Telegram /status command,
  - verify the P0 latched-pause invariant against the boot's
    clean reconciliation pass.

The boot banner gains five new fields:

```
replay_paper_trade_matched=True
replay_p0_incidents=0
replay_telegram_commands=1
replay_state_transitions=1
replay_p0_latched_pause_invariant=True
```

#### Phase 10A boundary

Phase 10A is **read-only**:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client /
    Telegram bot library
  - reads NO `os.environ`
  - defines NO `create_order` / `cancel_order` / `set_leverage` /
    `set_margin_mode` method
  - does NOT subclass `ExchangeClientBase`
  - does NOT instantiate any state-mutating component (the AST
    scan in `tests/unit/test_phase10a_boundary.py` enforces
    this against every file under `app/replay/`)
  - does NOT call `EventRepository.append_event` /
    `append_many` (AST scan in
    `tests/unit/test_phase10a_no_network.py`)

#### Tests

`+119` new Phase 10A tests on top of `1130` retained from
Phase 1-9 = **`1249` total**.

| File | Tests | Covers |
| --- | --- | --- |
| `test_replay_diff.py` | 13 | DiffKind vocabulary, DiffEntry payload, identical/empty/missing/extra/reordered combinations, determinism, JSON round-trip, frozen dataclass. |
| `test_replay_loaders.py` | 21 | Every event-type tuple matches its phase, every loader produces the right filter behaviour, learning-ready reads, opportunity_id extraction (top-level + nested in learning_ready), reconciliation pass pairing. |
| `test_replay_engine.py` | 22 | Acceptance criteria 1-7: replay one paper trade, replay capital rebase (event_id and timestamp), replay risk rejection under M3, replay risk decision by event_id, replay P0 incident lifecycle (with protection-mode events scoped to the incident window), replay STATE_TRANSITION ladder, replay TELEGRAM_COMMAND_RECEIVED, read Phase 8.5 learning-ready payload. Plus determinism, JSON-safety, no event-stream writes, constructor pin (event_repo only). |
| `test_replay_p0_latched_pause.py` | 10 | Empty trail / clean passes / P0 latched + pause kept / full operator resume protocol / synthesised violations (blocker_active_but_unpaused, latched_but_unpaused) / window filters / JSON round-trip. |
| `test_phase10a_boundary.py` | 14 | Phase 1 / 3 / 9 invariants, package does not subclass ExchangeClientBase, no write surface method definitions, public exports complete, canonical chains pinned. Replay engine constructor accepts only `event_repo`. |
| `test_phase10a_no_network.py` | ~50 | Per-file AST scan of every `.py` under `app/replay/`: no forbidden import, no write-surface method definition, no `api_key` / `api_secret` / `bot_token` parameter or literal, no `os.environ.get` / `getenv()`, no `send_message` / `send_document` / `send_photo` reference, no other-DB `sqlite3.connect`, no `EventRepository.append_event` / `append_many` call, no state-mutating component import. |

`tests/unit/test_main_entrypoint.py` extended (one assertion
flip) for the Phase 10A boot banner string and the five new
banner fields.

### Issue #10 acceptance criteria (Part 10A subset)

| # | Criterion | Test |
| --- | --- | --- |
| 1 | Replay can rebuild a mock paper trade | `test_replay_paper_trade_returns_summary_and_clean_diff` |
| 2 | Replay can rebuild a Capital Rebase | `test_replay_capital_rebase_after_deposit` |
| 3 | Replay can rebuild a Risk rejection | `test_replay_risk_rejection_under_m3` |
| 4 | Replay can rebuild a P0 incident | `test_replay_p0_incident_reconstructs_open_and_resolve` |
| 5 | Replay can read Phase 8.5 learning-ready payload | `test_replay_reads_learning_ready_block` |
| 6 | Replay does not trigger trading actions | `test_replay_does_not_write_to_events_db` + AST scan |
| 7 | Replay does not depend on real network | `test_phase10a_no_network.py::test_no_forbidden_imports` |
| 8 | pytest 全部通过 | 1249 passed |

### Boundary preserved

  - No new exchange SDK / HTTP / WebSocket / LLM client /
    Telegram bot library in `requirements.txt` /
    `pyproject.toml`.
  - No new `create_order` / `cancel_order` / `set_leverage` /
    `set_margin_mode` call site.
  - No change to the Phase 1 safety lock.
  - No change to the Phase 3 read-only invariant.
  - No change to the Phase 9 Execution FSM driver / Reconciler
    contract. Replay reads but never writes.
  - No real-trade persistence into `trades.db` / `positions.db`.
  - No LLM in trade decisions.
  - No Telegram outbound; the Phase 1 in-process command bus
    skeleton is unchanged.

#### Version

`app/__init__.py` -> `1.4.0a10` /
`Phase 10A - Replay Engine`. `pyproject.toml` -> `1.4.0a10`.

### Phase 9 - Execution FSM + Reconciliation

Phase 9 wires the Execution FSM driver and the Reconciliation
loop on top of every Phase 1-8.5 contract. The driver advances
per-order sessions through the 15 ``ExecutionState`` values, emits
the matching ``ORDER_*`` / ``STOP_*`` / ``POSITION_*`` events,
and consults the Risk Engine on every NEW open AND every
reduce-only / protective-exit / kill_all path. Phase 9 runs
ENTIRELY in paper / mock mode; the four ``ExchangeClientBase``
write surfaces continue to raise ``SafeModeViolation`` and are
NEVER overridden.

#### Added

##### `app/execution/` - Execution FSM driver

- `OrderRequest` (frozen Pydantic v2): `client_order_id`, `symbol`,
  `side`, `kind`, `qty`, `limit_price`, `intent`, `direction`,
  `time_in_force`, `margin_mode`, `leverage`, `reduce_only`,
  `stop_price`, `invalid_price`, `max_slippage_pct`,
  `opportunity_id`, `notes`. Validators enforce `qty > 0`,
  `leverage >= 1.0`, `0 < max_slippage_pct <= 0.10`,
  `margin_mode == ISOLATED` (cross margin is not declared at the
  enum level so a typo cannot construct one). `is_new_open` /
  `is_reduce_only_intent` properties derive from the intent
  vocabulary so callers cannot accidentally swap polarity.
- `OrderIntent` (8 values): `NEW_OPEN`, `SCALE_IN`, `LOCK_PROFIT`,
  `FORCED_EXIT`, `DISTRIBUTION_EXIT`, `PROTECTIVE_CLOSE`,
  `KILL_ALL`, `STOP_ATTACH`. Plus `NEW_OPEN_INTENTS` and
  `REDUCE_ONLY_INTENTS` partition sets that exhaust the enum.
- `OrderKind` (`LIMIT` / `MARKET` / `STOP_MARKET` / `STOP_LIMIT`).
- `OrderSide` (`BUY` / `SELL`) plus the `side_for_direction(direction,
  is_close)` helper that resolves the canonical mapping.
- `MarginMode` - the enum **only** declares `ISOLATED`. Cross
  margin is forbidden in Phase 9 (Spec §13.2 + §30.2 "禁止 cross
  margin") and the enum guarantees it cannot even be constructed.
- `TimeInForce` (`GTC` / `IOC` / `FOK`).
- `FillEvent` (frozen Pydantic v2): one fill applied to a session.
  Validates `fill_qty > 0`, `fill_price > 0`.
- `StopEvent` (frozen Pydantic v2): reduce-only stop attachment
  descriptor. The `reduce_only=True` invariant is enforced at the
  model layer (Spec §30.2 "止盈止损必须 reduce-only") so a stop
  cannot be constructed with `reduce_only=False`.
- `ExecutionSession` (mutable dataclass): per-order lifecycle state
  including `state`, `exchange_order_id`, `stop_order_id`,
  `position_id`, `filled_qty`, `avg_fill_price`, `realized_pnl`,
  transition history, learning-context payload, incident_id,
  protection-mode flag.
- `ExecutionResult` (frozen): return value of `submit_order`
  carrying `accepted`, the session, and the rejection reasons.
- `ExecutionFSMDriver`:
  - `submit_order(...)` drives `IDLE -> SIGNAL_RECEIVED ->
    RISK_CHECKED -> ORDER_SENT`. Calls
    `RiskEngine.evaluate(...)` with `is_new_open` derived from the
    intent. On rejection, the session is reverted to `IDLE` with
    `rejection_reasons` attached and removed from the driver's
    `_sessions` map. On approval, records the order in the paper
    ledger and writes one `ORDER_SENT` event.
  - `on_ack(...)` -> `ACK_RECEIVED` + `ORDER_ACK` event.
  - `on_partial_fill(...)` -> `PARTIAL_FILLED` + `ORDER_PARTIAL_FILLED`
    event. **Recomputes risk on the remaining size** (Spec §30.2
    hard rule "部分成交必须重算风险"); a re-rejection drives the
    session into `ERROR_PROTECTION`.
  - `on_full_fill(...)` -> `FULL_FILLED` + `ORDER_FILLED` event.
    Validates that the cumulative filled qty equals the request
    size.
  - `attach_stop(stop_price=...)` -> `STOP_SENT` + `STOP_SENT`
    event. The stop is constructed with `reduce_only=True`; any
    reduce-only intent (`LOCK_PROFIT` / `FORCED_EXIT` / etc.) is
    refused as a stop attachment target.
  - `on_stop_confirmed(stop=...)` -> `STOP_CONFIRMED` ->
    `POSITION_OPEN`. Records the paper position and writes one
    `POSITION_OPENED` event.
  - `on_stop_failed(reason=...)` -> `STOP_FAILED` ->
    `ERROR_PROTECTION`. Spec §30.3 "止损挂不上：立即保护平仓":
    the driver opens a P0 incident via the protection hook,
    emits `PROTECTION_MODE_ENTERED`, and runs an automatic
    reduce-only protective close on the paper position.
  - `trigger_exit(reason=...)` -> `EXIT_TRIGGERED` ->
    `POSITION_CLOSING`. Calls `RiskEngine.evaluate(...)` with
    `is_new_open=False` so M3 / DATA_DEGRADED / REGIME /
    EXCHANGE_DISCONNECTED / REBASE_IN_PROGRESS gates do NOT block
    the exit (Phase 7 protective-exit caveat; Phase 8 rebase rule).
  - `on_position_closed(realized_pnl=...)` -> `POSITION_CLOSED` ->
    `IDLE`. Removes the paper position from the ledger.
  - `enter_error_protection(...)` / `exit_protection_mode(...)` -
    public entry points for the operator override path.
  - `simulate_paper_lifecycle(...)` - high-level helper used by
    the boot drill.
  - **Construction-time refusal** of `trading_mode != paper`,
    `live_trading_enabled=True`, `exchange_live_order_enabled=True`
    (defence in depth on top of the Phase 1 boot guard).
  - **Every Phase 9 event carries `opportunity_id` and
    `learning_ready`** when the caller supplies them, so future
    Replay / Reflection / Dataset Builder can group every order /
    stop / fill / position event by opportunity (Phase 8.5
    contract).
- `PaperLedger` - in-memory paper-mode store of `PaperOrder` /
  `PaperStop` / `PaperPosition` / `PaperEquity`. Pure data; never
  opens a network surface. Provides observability counters
  (`orders_recorded`, `stops_recorded`, `positions_opened`,
  `positions_closed`).
- The Phase 1 `ExecutionFSM` skeleton + `IllegalTransition` are
  preserved verbatim for back-compat (Phase 1 tests + the boot
  drill still construct it).

##### `app/incidents/` - IncidentRepository

- `Incident` dataclass (`incident_id`, `level`, `title`,
  `description`, `source_module`, `symbol`, `position_id`,
  `opened_at`, `resolved_at`, `resolution`, `payload`).
- `IncidentRecord` dataclass (one row of the `incident_log` table).
- `INCIDENT_STATE_OPENED` / `INCIDENT_STATE_UPDATED` /
  `INCIDENT_STATE_RESOLVED` constants matching the Phase 2
  `incidents.sql` schema.
- `IncidentRepository`:
  - `open_incident(level=, title=, description=, source_module=,
    symbol=, position_id=, payload=, ...)` - writes one row into
    `incidents.incidents` + one row into
    `incidents.incident_log` + one `INCIDENT_OPENED` event.
  - `update_incident(incident_id=, note=, payload=, ...)` -
    appends one `incident_log` row with state=`updated`.
  - `resolve_incident(incident_id=, resolution=, ...)` - updates
    the `incidents` row's `resolved_at` / `resolution` columns +
    appends a `resolved` row + emits one `INCIDENT_RESOLVED`
    event.
  - `enter_protection_mode(reason=, ...)` /
    `exit_protection_mode(reason=, ...)` - emit
    `PROTECTION_MODE_ENTERED` / `PROTECTION_MODE_EXITED` events
    and toggle the `in_protection_mode` flag.
  - Read-only queries: `get_incident(incident_id)`,
    `list_open_incidents(level=, symbol=)`, `list_log_for(incident_id)`.
  - Counters for monitoring: `opened_count`, `resolved_count`,
    `protection_entered_count`, `protection_exited_count`,
    `last_protection_reason`.
- `ProtectionHook` typing.Protocol exposing `open_incident`,
  `enter_protection_mode`, `exit_protection_mode` so the FSM
  driver and the Reconciler stay decoupled from the SQLite layer
  (tests substitute mocks).

Phase 9 is the **first phase that writes to `incidents.db`**.
Earlier phases shipped only the schema; Phase 2 explicitly
forbade writes.

##### `app/reconciliation/` - Reconciliation engine

- `MismatchType` (8 values): `ORDER_MISMATCH`,
  `POSITION_MISMATCH`, `STOP_MISMATCH`, `EQUITY_DRIFT`,
  `WS_REST_CONFLICT` (the 5 mandated by Issue #9), plus three
  P0-promoted sub-types `GHOST_POSITION`,
  `MISSING_REMOTE_POSITION`, `UNATTACHED_STOP` so reflection /
  replay can group P0 incidents by canonical name without
  re-deriving them from the parent payload.
- `MismatchSeverity` (`P0` / `P1` / `P2`).
- `OrderView` / `PositionView` / `StopView` / `EquitySnapshot` /
  `LinkHealth` - frozen value objects describing the two snapshot
  sides.
- `LocalSnapshot` / `RemoteSnapshot` - the two inputs the
  reconciler consumes. Pure functions
  `local_snapshot_from_paper_ledger(...)` /
  `remote_snapshot_from_paper_ledger(...)` build them from the
  in-process paper ledger; tests can construct divergent
  snapshots directly to exercise the mismatch paths.
- `Mismatch` (frozen): one concrete mismatch carrying
  `mismatch_type`, `severity`, `symbol`, `summary`, `details`.
- `ReconciliationDecision` (frozen): result of one pass. Carries
  `started_at`, `finished_at`, `mismatches`, `incidents_opened`,
  `new_opens_paused`, `protection_mode_entered`, `notes`. Plus
  `matched`, `severities`, `has_p0` derived properties.
- `Reconciler`:
  - `reconcile(local=, remote=)` writes one
    `RECONCILIATION_STARTED` event, one
    `RECONCILIATION_MISMATCH` event per mismatch, and one
    `RECONCILIATION_RESOLVED` event with
    `mismatch_count` / `p0_count` / `p1_count` /
    `new_opens_paused` / `incident_ids` / `notes`.
  - Opens a P0 incident via `protection_hook.open_incident(...)`
    on every P0 mismatch.
  - Drives `protection_hook.enter_protection_mode(...)` on any
    P0 mismatch; the boot drill registers an
    `IncidentRepository` as the hook so this lands in
    `incidents.db` AND emits a `PROTECTION_MODE_ENTERED` event.
  - `new_opens_paused=True` on any non-empty mismatch list; the
    flag advises the FSM driver to refuse new `NEW_OPEN` /
    `SCALE_IN` `submit_order` calls until the next clean
    reconciliation.
  - A clean reconciliation clears `new_opens_paused`
    automatically (operator-equivalent of `/resume`).
  - Tunable thresholds: `equity_drift_tolerance_abs=0.01` USDT,
    `equity_drift_tolerance_rel=0.005` (0.5%),
    `qty_tolerance=1e-9`, `stop_price_tolerance_pct=0.001`
    (0.1%). The reconciler treats abs OR rel passing as "within
    tolerance" - both must exceed before the drift fires.

##### Risk Engine integration (Phase 9-only consumer of an existing API)

Phase 9 makes **no** changes to `RiskEngine` / `RiskRequest`. The
existing Phase 7 protective-exit caveat (`is_new_open=False` is
the right way to bypass M3 / DATA_DEGRADED / REGIME /
EXCHANGE_DISCONNECTED gates) and the Phase 8 rebase rule
(`is_rebase_in_progress` blocks new opens but never blocks exits)
already do the right thing. Phase 9 simply derives `is_new_open`
from the `OrderIntent` vocabulary so callers cannot pass the
wrong flag.

Verified by the Phase 9 boundary tests: M3 + protective close
PASSES, DATA_DEGRADED + protective close PASSES,
REBASE_IN_PROGRESS + protective close PASSES; the corresponding
`is_new_open=True` paths are still rejected.

##### Boot drill (`python -m app.main`)

The boot drill now drives ONE paper-mode order through the full
Execution FSM (`NEW_OPEN` -> `POSITION_OPEN` -> `LOCK_PROFIT` exit
-> `POSITION_CLOSED` -> `IDLE`) and runs ONE reconciliation pass
against snapshots built from the same paper ledger. In paper mode
the local view equals the remote view, so the boot reconciliation
is always clean (zero mismatches, zero incidents). The banner
gained 14 new fields (`orders_submitted`, `order_sent_events`,
`order_filled_events`, `stops_confirmed`, `positions_opened`,
`positions_closed`, `reconciliations_run`,
`reconciliation_started_events`, `reconciliation_resolved_events`,
`reconciliation_mismatches`, `new_opens_paused`,
`incidents_opened`, `protection_mode_entered`).

Two new health probes are registered:
  - `execution_driver` - DEGRADED if the driver has entered
    `ERROR_PROTECTION` at least once.
  - `reconciliation` - DEGRADED if `new_opens_paused=True` at the
    end of the boot pass.

##### Documentation + version bump

- `app/__init__.py` -> `1.4.0a9` /
  `Phase 9 - Execution FSM Reconciliation`.
- `pyproject.toml` -> `1.4.0a9`.
- `README.md` -> Phase 9 deliverable + boundary section + status
  table updated (Phase 8.5 marked merged, Phase 9 is "this branch").
- `docs/CHANGELOG.md` -> Phase 9 entry prepended; the Phase 8.5
  entries are preserved verbatim below.

#### Tests

```
$ python3.12 -m pytest tests/unit
1091 passed in 9.28s
```

**+149 new Phase 9 tests on top of 942 retained from Phase 1-8.5 = 1091 total.**

| File | Tests | Covers |
| --- | --- | --- |
| `test_execution_models.py` | 16 | OrderRequest validators (qty / leverage / margin_mode / slippage), `is_new_open` / `is_reduce_only_intent` derivation, intent partition complete, FillEvent / StopEvent validators (incl. `reduce_only` enforcement), `side_for_direction`, OrderKind / MarginMode vocabularies. |
| `test_paper_ledger.py` | 10 | record_order, partial-fill clamping, close_order, stops, positions (incl. cascading stop removal on close), equity snapshot. |
| `test_execution_fsm_driver.py` | 28 | construction guards (3), submit_order happy path + opportunity_id propagation + learning_ready propagation + duplicate refusal, market-order on NEW_OPEN refused vs allowed for protective close, reduce_only auto-resolution, risk rejection paths (M3 new open, M3 protective close PASSES, DATA_DEGRADED protective close PASSES, REBASE_IN_PROGRESS protective close PASSES), full lifecycle event sequence, partial fill recompute (Spec §30.2), VWAP computation, full fill consume remaining, stop attach reduce_only, on_stop_failed -> ERROR_PROTECTION + P0 incident + protective close, on_stop_confirmed -> POSITION_OPENED + paper position, trigger_exit calls Risk Engine with is_new_open=False, M3 protective exit does not open incident, enter / exit_protection_mode lifecycle. |
| `test_incidents_repository.py` | 8 | open_incident writes row + log + INCIDENT_OPENED, update_incident appends log row only, resolve_incident updates row + emits INCIDENT_RESOLVED, get / list helpers, enter / exit protection mode events, ProtectionHook surface. |
| `test_reconciler.py` | 16 | clean recon, paper ledger round trip clean, ghost position P0 + new_opens_paused + protection_hook P0 incident, missing remote position P0, position qty disagreement P0, unattached_stop P0, order local-only P1, order qty disagreement, equity within tolerance / above tolerance, WS-REST conflict P1, both-connected no fire, new_opens_paused state machine clears on clean recon, RECONCILIATION_RESOLVED payload counts, RECONCILIATION_MISMATCH event per mismatch. |
| `test_phase9_boundary.py` | 16 | Phase 1 lock unchanged, Phase 3 write surfaces still refuse on Mock + Binance skeleton, Phase 9 packages don't subclass ExchangeClientBase, no write surface method definitions, OrderIntent / OrderKind / MarginMode / MismatchType / MismatchSeverity vocabularies pinned, driver construction guard, all Phase 9 EventType values reachable, public exports, OrderRequest model-level validators. |
| `test_phase9_no_network.py` | ~50 | per-file AST scan of every `.py` under `app/execution/`, `app/incidents/`, `app/reconciliation/`: no forbidden import (ccxt / binance / aiohttp / websockets / requests / httpx / openai / anthropic / deepseek / telegram), no write-surface method, no `api_key` / `api_secret` / `bot_token` parameter or literal, no `os.environ.get` / `getenv()`, no `send_message` / `send_document` / `send_photo` reference, no other-DB `sqlite3.connect`. |

`tests/unit/test_main_entrypoint.py` was extended (not replaced)
to assert the new Phase 9 banner fields and Phase 9 event counts
(1 each of `ORDER_SENT` / `ORDER_ACK` / `ORDER_FILLED` /
`STOP_SENT` / `STOP_CONFIRMED` / `POSITION_OPENED` /
`EXIT_TRIGGERED` / `POSITION_CLOSED`, 1 `RECONCILIATION_STARTED`
+ `RECONCILIATION_RESOLVED`, 0 `RECONCILIATION_MISMATCH`, 0
`INCIDENT_OPENED`, 0 `PROTECTION_MODE_ENTERED`).

#### Live trading risk

**None.**

  - `requirements.txt` and `pyproject.toml` contain no exchange
    SDK, no HTTP / WebSocket client, no LLM client, no Telegram
    bot library.
  - No source under `app/execution/`, `app/incidents/`,
    `app/reconciliation/` imports `ccxt`, `binance`, `aiohttp`,
    `websockets`, `requests`, `httpx`, `openai`, `anthropic`,
    `deepseek`, or any Telegram library.
  - No source under those packages defines `create_order` /
    `cancel_order` / `set_leverage` / `set_margin_mode`.
  - `MarginMode` enum does not even declare `CROSS`.
  - `ExchangeClientBase.{create_order, cancel_order, set_leverage,
    set_margin_mode}` continue to raise `SafeModeViolation` from
    the base class.
  - The Phase 1 safety lock + the Phase 3 read-only invariant +
    every Phase 4 / 5 / 6 / 7 / 8 / 8.5 contract are unchanged.
    Boot banner still shows
    `mode=paper live_trading=False right_tail=False llm=False
    exchange_live_orders=False`.
  - The `ExecutionFSMDriver` refuses to construct unless the
    Phase 1 safety lock matches paper-mode (defence in depth).

## [Unreleased - prior]

### Phase 8.5 - Learning-Ready Data Contract + Test Data Export Contract

Phase 8.5 lays the **passive data contract** every future phase
will read: Replay (Issue #10), MFE/MAE labelling, Tail labelling,
Dataset Builder, AI Learning. It also ships the cloud-test-friendly
**Test Data Export Service** (zip + manifest + summary + redaction)
plus a CLI. The full AI Learning, Feature Store, model training,
strategy ordering, live trading, real network, LLM and Telegram
outbound are **NOT** implemented in this phase.

#### Added

##### `app/learning/` - Learning-Ready Data Contract

- `OpportunityIdentity` (frozen Pydantic v2): `opportunity_id`,
  `scan_batch_id`, `symbol`, `first_seen_ts`, `source_phase`. Plus
  `make_opportunity_id` / `make_scan_batch_id` factories so a
  scanner / confirmation / risk engine call can generate a stable
  identifier deterministically.
- `signal_snapshot_to_payload` / `payload_to_signal_snapshot`:
  Spec §11.2 SignalSnapshot serialiser/deserialiser. The Phase 1
  `app.core.models.SignalSnapshot` is the single source of truth;
  Phase 8.5 only adds a deterministic JSON-safe serialisation
  contract.
- `VirtualTradePlan` (frozen Pydantic v2): `virtual_entry`,
  `virtual_stop`, `virtual_tp1`, `virtual_tp2`, `invalid_price`,
  `suggested_leverage`, `risk_budget_pct`, `direction`, `setup_type`.
  Validates `suggested_leverage >= 1.0` and `0 <= risk_budget_pct <= 1.0`.
  This is a **paper-only descriptive plan**; constructing one
  triggers no order, ever.
- `ConfigVersions` (frozen Pydantic v2) with the six Issue-mandated
  identifiers: `strategy_version`, `risk_config_version`,
  `scoring_version`, `capital_state_version`, `state_machine_version`,
  `llm_prompt_version`. Defaults are pegged to `v1.4.0a8.5`;
  `llm_prompt_version` defaults to `n/a` because Phase 8.5 forbids
  any LLM trade involvement (Spec rule 7).
- `RiskRejectedLearningPayload`: typed enrichment carrying
  `opportunity_id`, `reject_reasons`, `account_life_tier`, `regime`,
  `universe_eligible`, `liquidity_state`, `trade_confirmation_level`,
  `manipulation_level`, `capital_state_version`, `risk_config_version`,
  plus Phase 7 breaker / `is_new_open` / `attack_intent` context.
- `LearningReadyContext` aggregator + `attach_learning_ready` merge
  helper. Mutation-free: existing event-payload keys are preserved
  bit-for-bit, the enrichment lands under a new `learning_ready`
  sub-key. The Phase 1 `EventRepository.append_event` API is
  unchanged; Phase 8.5 simply makes it possible for emitters to
  carry the contract.
- `LEARNING_READY_KEY = "learning_ready"` and
  `LEARNING_READY_EVENT_TYPES` (the 11 event types Issue #8.5
  requires: `PRE_ANOMALY_DETECTED`, `ANOMALY_DETECTED`,
  `TRADE_CONFIRMED`, `MANIPULATION_DETECTED`, `UNIVERSE_FILTERED`,
  `LIQUIDITY_CHECKED`, `RISK_APPROVED`, `RISK_REJECTED`,
  `STATE_TRANSITION`, `CAPITAL_REBASE`,
  `RISK_BUDGET_RECALCULATED`).

##### Risk Engine integration

- `RiskRequest` gained five **optional** Phase 8.5 fields:
  `opportunity`, `opportunity_id`, `virtual_trade_plan`,
  `config_versions`, `learning_context`. All default to `None`;
  legacy callers retain byte-for-byte compatible audit payloads.
- `RiskEngine._record(...)` now synthesises a
  `RiskRejectedLearningPayload` from the request + decision +
  breaker state and merges a `learning_ready` block into the
  `RISK_APPROVED` / `RISK_REJECTED` payload. A caller-supplied
  `learning_context` always wins over the synthesised one. The
  legacy reasons / account_tier / regime / no_trade_gate audit
  fields stay untouched so Phase 1 / Phase 6 / Phase 7 tests pass
  unchanged.

##### `app/exports/` - Test Data Export Service

- `TestDataExportService.export(...)` produces a redacted `.zip`
  bundle under `data/reports/exports/ama_rt_test_data_<ts>_<id>.zip`.
  Default zip contents (with `type=all`):
    `manifest.json`, `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`, `virtual_trade_plans.jsonl`.
- Time ranges supported: `today`, `24h`, `7d`, `range` (with
  explicit `start_ms` / `end_ms`).
- Type filters supported: `all`, `events`, `opportunities`,
  `rejections`, `capital`, `state`, `learning`.
- `manifest.json` carries every Issue-mandated field
  (`export_id`, `generated_at`, `time_range_start`, `time_range_end`,
  `trading_mode`, `app_version`, `event_count`, `opportunity_count`,
  `risk_rejected_count`, `state_transition_count`,
  `capital_event_count`, `redaction_applied=true`) plus a
  per-export `safety_summary` snapshot of the Phase 1 lock so a
  reviewer can spot a leaked flag at a glance.
- `summary_report.md` includes time range, totals, top reject
  reasons, top symbols by event count, paper PnL (from
  `CAPITAL_REBASE.net_trading_pnl`), and incident / degraded /
  protection-mode flags.
- `redact(...)` walks any JSON-safe value and replaces sensitive
  fields with `[REDACTED]`. The redactor covers (a) sensitive key
  substrings (`api_key`, `api_secret`, `secret`, `token`,
  `password`, `auth`, `credential`, `private_key`, `bot_token`,
  `webhook`, `withdrawal_address`, `address`, `passphrase`,
  `session`, `cookie`, `ssh`, `smtp`, ...), (b) absolute filesystem
  paths (`/home`, `/root`, `/Users`, `C:\Users`, `/etc`, `/var/lib`,
  `/usr/local`, `/.env`), and (c) value patterns (Telegram bot
  tokens `\d{8,12}:[A-Za-z0-9_-]{30,}`, Binance-style 64-char
  keys, AWS `AKIA...` keys, OpenAI/Anthropic/DeepSeek `sk-...`
  tokens, `AMA_*_KEY/SECRET/TOKEN/PASSWORD` env-var literals).
- `assert_no_forbidden_substrings(...)` is a defence-in-depth gate
  on the export path; the service refuses to write the zip if any
  forbidden literal slips through.
- `TestDataExportService.max_zip_bytes` defaults to 50 MiB. Issue
  #10 will add Telegram-side fragmentation; Phase 8.5 just refuses
  to grow beyond the cap and asks the caller to narrow the window.
- CLI: `app/exports/cli.py` + `scripts/export_test_data.py` shim.
  Examples:
    ```
    python -m scripts.export_test_data --range 24h
    python -m scripts.export_test_data --range 7d
    python -m scripts.export_test_data --type rejections
    python -m scripts.export_test_data --start 2026-05-01 --end 2026-05-07
    ```

##### Documentation

- `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`: the future Telegram
  Command Center MUST add `/export_test_data {24h,7d,today}`,
  `/export_rejections 24h`, `/export_report today`,
  `/export_learning_dataset 7d`. The contract spells out: short
  text summary first, then `sendDocument` (NOT raw chat dump),
  paper-mode banner pinned, operator allow-list, refusal on size
  cap. Issue #10 will implement the bot client; Phase 8.5 ships
  ONLY the contract.
- `app/__init__.py` bumped to `1.4.0a8.5` /
  `Phase 8.5 - Learning-Ready Data Contract + Test Data Export Contract`.
- `pyproject.toml` version bumped to `1.4.0a8.5`.

#### Boundary (Phase 8.5 prohibitions, all enforced by tests)

1. **No full AI Learning.** No model training. No Feature Store.
   No complex Data Collection Module.
2. **No Telegram outbound.** The `app/telegram` package remains
   a Phase 1 in-process command-bus skeleton.
3. **No real network.** No exchange SDK, no HTTP / WebSocket
   client, no LLM client imported anywhere under `app/learning/`
   or `app/exports/`.
4. **No API key in process memory.** No `api_key` / `api_secret`
   parameter on any Phase 8.5 surface; no `os.environ` /
   `os.getenv` / bare `getenv` call under `app/learning/` or
   `app/exports/` (AST scan).
5. **No write surface.** No new `create_order`, `cancel_order`,
   `set_leverage`, `set_margin_mode` method. The four
   `SafeModeViolation` refusals on `ExchangeClientBase` are
   unchanged.
6. **No LLM in trade decisions.** `llm_prompt_version` is `"n/a"`
   by default; the LLM prompt label only *records* a version for
   Reflection (Issue #10). Spec rule 7 still bans LLM
   participation in trading actions.
7. **No Issue #9 work.** Execution FSM driver / Reconciliation
   are deferred.
8. **No Issue #10 work.** LLM, Telegram outbound, Replay diff
   reports, Reflection are deferred.

#### Tests

```
$ python3.12 -m pytest tests/unit
933 passed in 7.40s
```

**+150 new Phase 8.5 tests** on top of the 783 retained from
Phase 1-8 = **933 total**:

| File | Tests | What it covers |
| --- | --- | --- |
| `test_opportunity_identity.py` | 8 | factory ids, prefix contract, frozen contract, payload round-trip, extra-field rejection, url-safe characters |
| `test_signal_snapshot_payload.py` | 5 | Spec §11.2 field set, enum-as-string contract, JSON-safe, round-trip preserves fields, defaults round-trip |
| `test_virtual_trade_plan.py` | 8 | required fields present, optional `None`s round-trip, JSON-safe, leverage/risk-budget validators, frozen contract |
| `test_config_versions.py` | 7 | six Issue-mandated fields, `llm_prompt_version='n/a'` default, JSON-safe, round-trip, frozen, legacy-payload back-fill |
| `test_learning_ready_context.py` | 9 | the 11 event types pin, `LEARNING_READY_KEY` constant, mutation-free merge, full-context payload, empty-context emits empty dict |
| `test_risk_rejected_payload.py` | 6 | enum-as-string serialisation, RISK_REJECTED carries learning_ready when supplied, legacy request leaves payload byte-compatible, RISK_APPROVED with explicit `opportunity_id`, explicit-context override beats synthesised |
| `test_event_repository_learning_ready.py` | 3 | round-trip of `learning_ready` block via `EventRepository.append_event` + `list_events`, all 11 event types preserved on disk, JSON-serialisable on disk |
| `test_export_redaction.py` | 12 | top-level keys, nested keys, mutation-free input, value-pattern matching (Telegram, OpenAI), filesystem path stripping, short strings pass through, forbidden-substring gate, sensitive-key contract |
| `test_export_service.py` | 22 | time range helpers (today/24h/7d/range/parse_iso_date), zip materialised, manifest + summary + 7 jsonl shards, redaction end-to-end, type filters (rejections/capital/state/learning), unknown filter rejected, empty window still produces zip, size cap refused, safety_summary on manifest, output filename layout |
| `test_export_cli.py` | 8 | `--range 24h` / `7d` / `today`, `--type rejections`, `--range range --start --end`, missing start/end error, oversized cap error, missing events.db error |
| `test_phase8_5_boundary.py` | 9 | Phase 1 lock unchanged, write surfaces still refuse `SafeModeViolation`, BinanceClient still refuses credentials, learning/exports packages do NOT subclass `ExchangeClientBase`, no write-surface methods on learning/exports, redaction substring contract, default zip cap finite, Telegram contract doc present |
| `test_phase8_5_no_network.py` | ~52 | per-file AST scan of every `.py` under `app/learning/` + `app/exports/`: no forbidden import (ccxt, binance, aiohttp, websockets, requests, httpx, openai, anthropic, deepseek, telegram libraries), no write-surface method definition, no `api_key` / `api_secret` parameter, no concrete `BINANCE_API_KEY=` / `TELEGRAM_BOT_TOKEN=` literal in source, no `os.environ.get` / `os.getenv` / bare `getenv()` call, no `send_message` / `send_document` / `send_photo` reference |

`tests/unit/test_main_entrypoint.py` was extended (one assertion
flip) to expect the Phase 8.5 banner string.

#### Live trading risk

**None.**

- `requirements.txt` and `pyproject.toml` contain no exchange SDK,
  no HTTP client, no LLM client, no Telegram bot library.
- No source file under `app/learning/` or `app/exports/` imports
  `ccxt`, `binance`, `aiohttp`, `websockets`, `requests`, `httpx`,
  `openai`, `anthropic`, `deepseek`, or any Telegram library
  (asserted by `tests/unit/test_phase8_5_no_network.py`).
- No source file under `app/learning/` or `app/exports/` defines
  `create_order` / `cancel_order` / `set_leverage` /
  `set_margin_mode` (asserted by the same test module).
- No source file under `app/learning/` or `app/exports/` reads
  `os.environ` / `os.getenv` / a bare `getenv()` (AST scan).
- The Phase 1 safety lock, Phase 3 read-only invariant, Phase 4
  Market Data Buffer boundary, Phase 5 Regime / Universe /
  Liquidity contract, Phase 6 Scanner / Confirmation /
  Manipulation contract, Phase 7 State Machine + Risk Engine
  contract, and Phase 8 Capital Flow Engine + External Capital
  Flow vocabulary are all unchanged. The boot banner still shows
  `mode=paper live_trading=False right_tail=False llm=False
  exchange_live_orders=False`.
- The export service is **read-only against `events.db`**. It
  never opens a socket, never calls a write surface, never mutates
  any other database, never writes outside the configured output
  directory.
- The CLI refuses to operate when `trading_mode != paper`.

#### Real exchange order risk

**None.** Phase 8.5 adds no new `create_order` / `cancel_order` /
`set_leverage` / `set_margin_mode` call site. The four
`SafeModeViolation` refusals on `ExchangeClientBase` continue to
apply.

---

## [Unreleased - Phase 8 review fix - already in main via PR #19]

### Phase 8 - Issue #8 review fix: External Capital Flow semantics

Issue #8 review pointed out that the Phase-8 PR conflated several
distinct capital concepts. This patch implements the full External
Capital Flow vocabulary so the engine cannot mis-classify principal
withdrawals as profit and cannot mis-classify external deposits as
trading P&L.

#### Capital semantics (hard rules)

1. **External deposit is NOT trading profit.** A `CAPITAL_DEPOSIT`
   bumps `external_deposits_total` and `exchange_equity`; it never
   touches `withdrawn_profit` and never inflates `net_trading_pnl`.
2. **Principal withdrawal is NOT a loss.** When a withdrawal exceeds
   `available_profit` the excess lands in `principal_withdrawn_total`,
   never in `withdrawn_profit`.
3. **Profit withdrawal is NOT a drawdown.** `lifetime_account_value`
   is invariant under withdrawals.
4. **Risk Budget is based ONLY on `trading_capital`.** Already-
   withdrawn profit and historical peaks never re-enter the budget.
5. **Performance / `net_trading_pnl` excludes `external_deposits_total`.**
   Reporting must use `net_trading_pnl`, not `lifetime_equity`, when
   external deposits are present.
6. **`initial_capital` is immutable after construction.** The engine
   raises on any reassignment attempt.

#### Formulas

```
net_contributed_capital = initial_capital
                            + external_deposits_total
                            - principal_withdrawn_total

lifetime_account_value  = exchange_equity
                            + withdrawn_profit
                            + principal_withdrawn_total

net_trading_pnl         = lifetime_account_value
                            - initial_capital
                            - external_deposits_total

trading_capital         = exchange_equity
risk_budget             = trading_capital
```

#### Added

- `CapitalState.external_deposits_total` and
  `CapitalState.principal_withdrawn_total` fields, plus the
  computed properties `lifetime_account_value`,
  `net_contributed_capital`, and `net_trading_pnl`.
- `CapitalSnapshot` mirrors the new fields. The
  `capital.db.capital_snapshots` table gains
  `external_deposits_total` and `principal_withdrawn_total`
  columns; `app/database/migrations.py` ships an idempotent
  ALTER-TABLE for existing Phase-7 capital.db files.
- `RebaseResult` now carries the full External Capital Flow audit
  trail: `profit_part`, `principal_part`, `withdrawal_type`,
  `available_profit_before`, plus before/after values for
  `principal_withdrawn_total`, `external_deposits_total`,
  `lifetime_account_value`, and `net_trading_pnl`.
- `CapitalFlowEngine.deposit()` is now a full external-deposit
  flow: it bumps `external_deposits_total`, sets
  `is_rebase_in_progress=True` for the duration, emits the
  full event trio (CAPITAL_DEPOSIT + CAPITAL_REBASE +
  RISK_BUDGET_RECALCULATED), persists a snapshot, and returns
  a `RebaseResult`. `withdrawn_profit` is never touched by a
  deposit.
- `CapitalFlowEngine.replay_capital_events` /
  `CapitalFlowEngine.reconstruct_current_snapshot` rebuild a
  `CapitalState` from the persisted CAPITAL_* event stream. The
  reconstruction sorts by `(timestamp ASC, rowid ASC)` so events
  emitted within the same millisecond replay in the order they
  were inserted.
- New convenience properties on `CapitalFlowEngine`:
  `lifetime_account_value`, `net_contributed_capital`,
  `net_trading_pnl`, `external_deposits_total`,
  `principal_withdrawn_total`, `withdrawn_profit`. The setter for
  `initial_capital` now raises `AttributeError` so the immutability
  contract is enforced at the language level.
- `CAPITAL_WITHDRAWAL` payload now carries `withdrawal_type`
  (`"profit"` / `"principal"` / `"mixed"`), `profit_part`,
  `principal_part`, `available_profit_before`,
  `lifetime_account_value_before`, `initial_capital`, and
  `external_deposits_total`. `PROFIT_HARVEST` is only emitted
  when `profit_part > 0` so harvest analytics never see pure-
  principal withdrawals. `CAPITAL_REBASE` payloads carry the full
  External Capital Flow snapshot so a Replay engine can rebuild
  state deterministically.
- 25 new tests in `tests/unit/test_capital_flow_engine.py`
  covering: profit-only withdrawal (Test 1), mixed withdrawal
  (Test 2), pure-principal withdrawal, mid-stream deposit (Test 3),
  deposit + trading P&L (Test 4), deposit + profit withdrawal
  (Test 5), withdrawal exceeding available profit (Test 6),
  rebase gating (Test 7 - REBASE_IN_PROGRESS plus
  stop_unconfirmed / unknown_position post-rebase), event-
  sourced reconstruction (Test 8), `initial_capital` immutability,
  deposit-emits-full-event-trio, and CAPITAL_WITHDRAWAL payload
  semantics.

#### Changed

- `app/capital/rebase.py::execute_rebase` now classifies a
  withdrawal *before* mutating state: it computes
  `available_profit = max(0, net_trading_pnl_before)` and splits
  the withdrawal into `profit_part` and `principal_part`. Only
  `profit_part` accumulates onto `withdrawn_profit`; the rest
  lands on `principal_withdrawn_total`.
- `app/capital/profit_harvest.py::suggest_harvest` accepts
  optional `external_deposits_total` and
  `principal_withdrawn_total` parameters. The 2x / 5x / 10x
  multiplier ladder now triggers on the
  `lifetime_account_value / net_contributed_capital` ratio so
  external deposits never mis-trigger a harvest suggestion.
  When both new parameters default to `0` the old formula is
  preserved exactly.
- `Risk Engine` already gates new opens via
  `is_rebase_in_progress`; this remains the only place that
  authorises resume. Clearing the flag does NOT auto-approve
  new opens - the No-Trade Gate (stop_unconfirmed,
  unknown_position, regime, liquidity, account tier, circuit
  breakers, manipulation) still has final authority.

#### Safety

- No real withdrawal API. The engine only RECORDS withdrawals.
- No live trading. Phase 1 safety lock unchanged.
- No exchange write API. Phase 1 safety lock unchanged.
- No LLM. Phase 1 safety lock unchanged.
- No Issue #9 / #10 work shipped here.
- `initial_capital` immutability is enforced at the language
  level (setter raises `AttributeError`).

### Phase 7 - Issue #7 review fix: conservative throughput discount

Issue #7 review pointed out that the original PR deferred the
Phase 5 ``can_exit_position`` upper-bound discount to Issue #8 / #9.
That is wrong - Spec §27.2 + §19.2 require the Risk Engine to apply
the conservative discount itself. This commit moves the discount on
to the Phase 7 No-Trade Gate, where Issue #7 actually wants it.

#### Added

- ``RiskEngine.throughput_safety_factor`` (default ``0.5``) and a
  matching ``throughput_safety_factor: float | None`` field on
  :class:`RiskRequest`. Allowed range is ``(0.0, 1.0]``; the engine
  raises ``ValueError`` outside that range. Per-request overrides
  are honoured.
- ``RiskRequest.max_exit_seconds`` (optional) - ceiling for the
  discounted re-check. When ``None`` the engine derives it from the
  supplied :class:`LiquidityDecision` / :class:`ExitPlan`.
- ``NoTradeGateInput.throughput_safety_factor`` and
  ``NoTradeGateInput.max_exit_seconds`` so the gate can be driven
  directly by tests / replay.
- :attr:`RiskRejectReason.LIQUIDITY_THROUGHPUT_INSUFFICIENT` typed
  reject reason: fires when
  ``estimated_exit_seconds / throughput_safety_factor`` exceeds the
  resolved ``max_exit_seconds`` ceiling on a new opening.
- ``RISK_APPROVED`` / ``RISK_REJECTED`` audit payload now carries
  ``throughput_safety_factor`` and ``max_exit_seconds`` so
  Reflection (Issue #10) can reproduce the decision.
- README "Phase 7 conservative throughput discount" subsection that
  explains the Issue #7 hard rule, the resolution policy
  (``RiskRequest.throughput_safety_factor`` -> engine default), and
  the reuse rule for any future Phase 5
  ``LiquidityConfig.throughput_safety_factor``.

#### Changed

- ``app/risk/no_trade_gate.py`` - the Phase 5 ``can_exit_position``
  output is now treated as an upper bound. The gate runs the raw
  feasibility check first (``NO_EXIT_CHANNEL`` /
  ``LIQUIDITY_REJECTED`` / ``DATA_DEGRADED`` still fire as before)
  and then runs the discounted re-check on every new opening with a
  feasible plan. Step ordering is deterministic so reflective tools
  see the most severe / earliest reason at index 0.
- ``app/risk/engine.py`` - ``RiskEngine.__init__`` accepts the new
  keyword. Audit payload extended.
- README + CHANGELOG explicit: "Risk Engine treats liquidity
  throughput as an upper bound and applies a conservative safety
  factor before allowing ATTACK / RIGHT_TAIL_AMPLIFY."

#### Reuse policy

If a future Phase 5 PR ever adds ``throughput_safety_factor`` to
``LiquidityConfig``, the Phase 7 engine MUST consume that field
directly instead of defining its own. As of this commit no such
field exists on ``LiquidityConfig`` and the
``app/liquidity/`` package is unchanged.

#### Tests

**+9 new tests on top of the 714 from the Phase 7 PR = 723 total,
all passing.**

| Test | Pins |
| --- | --- |
| ``test_throughput_safety_factor_default_is_one_half`` | Default factor is 0.5. |
| ``test_throughput_safety_factor_invalid_rejected`` | (0.0, 1.0] enforced; constructor raises ``ValueError`` outside that range. |
| ``test_raw_feasible_plan_rejected_when_discounted_exceeds_ceiling`` | Issue #7 review fix: 40s raw + factor 0.5 -> 80s discounted -> REJECT with ``liquidity_throughput_insufficient``. |
| ``test_raw_feasible_plan_passes_when_discounted_under_ceiling`` | 10s raw + factor 0.5 -> 20s discounted -> APPROVE. |
| ``test_data_degraded_blocks_even_when_raw_plan_is_feasible`` | Issue #7 review fix: feasible plan + degraded data -> still rejected with ``data_degraded``. |
| ``test_no_trade_gate_throughput_discount_directly`` | Direct ``evaluate_no_trade_gate(...)`` regression so the discount is independently pinned at the gate level. |
| ``test_per_request_safety_factor_override_honoured`` | Per-request ``throughput_safety_factor=1.0`` (no discount) approves the same input that 0.5 would refuse. |
| ``test_engine_level_safety_factor_override_honoured`` | ``RiskEngine(throughput_safety_factor=0.9)`` approves a 40s/60s plan. |
| ``test_audit_payload_includes_throughput_safety_factor`` | The factor is on the persisted ``RISK_APPROVED`` audit row. |

#### Live trading risk

**None.** This commit only adds defensive plumbing: a new
multiplicative discount, a new typed reject reason, two new
optional ``RiskRequest`` fields, and audit-payload entries. No new
mode flag, no loosened safety lock, no new dependency, no new
write surface, no new network surface, no LLM. The Phase 1 safety
lock, the Phase 3 read-only invariant, the Phase 4 / 5 / 6
boundaries remain unchanged.

### Phase 7 - State Machine Risk Engine

#### Added

- **`app/state_machine/` package** (Spec §26, Issue #7).
  - `TradeStateMachine` per-symbol Trade State Machine implementing
    the Spec §26.1 ladder (`NO_TRADE -> OBSERVE -> SCOUT -> CONFIRM
    -> ATTACK -> RIGHT_TAIL_AMPLIFY -> LOCK_PROFIT ->
    DISTRIBUTION_ALERT -> FORCED_EXIT`).
  - Whitelisted transition table forbidding level skipping
    (Issue #7 hard rule 1). OBSERVE cannot directly become
    RIGHT_TAIL_AMPLIFY; SCOUT cannot directly become ATTACK; every
    illegal attempt raises :class:`IllegalStateTransition`.
  - `promote(TradeStateContext)` / `downgrade(reason)` /
    `record_breakout_failure()` / `record_distribution_bar()` /
    `lock_profit()` / `distribution_alert()` / `forced_exit()` /
    `tick(clock_ms)` / `reset()` operations. Each successful
    transition writes one ``STATE_TRANSITION`` event with the
    `from / to / trigger / reasons` payload.
  - Phase 7 hard rules enforced: CONFIRM-failures downgrade to
    SCOUT after the configured threshold; DISTRIBUTION_ALERT
    cannot promote; FORCED_EXIT is sticky (only `reset()` clears
    it); a losing position cannot enter RIGHT_TAIL_AMPLIFY;
    right-tail amplification must come from floating profit.
  - Spec §26.4 timeouts implemented in `tick(clock_ms)`: OBSERVE
    -> NO_TRADE after 30 min, SCOUT -> NO_TRADE after 12 min,
    ATTACK -> LOCK_PROFIT on `cvd_weakening=True`,
    RIGHT_TAIL_AMPLIFY -> LOCK_PROFIT on
    `right_tail_core_failed=True`, DISTRIBUTION_ALERT -> FORCED_EXIT
    after 3 confirming bars.
  - :class:`TimeoutConfig` exposes the timeout policy as a frozen
    dataclass so YAML overrides remain a future, additive change.

- **`app/risk/no_trade_gate.py`** (Spec §27.2, Issue #7).
  - `evaluate_no_trade_gate(NoTradeGateInput) -> NoTradeGateDecision`
    composes every Spec §27.2 condition into a typed
    :class:`RiskRejectReason` list. Walks in stable order so the
    "first" reason in the list is the most severe / earliest.
  - Reads Phase 5 `RegimeSnapshot.risk_permission`,
    `UniverseDecision.eligible`, `LiquidityDecision.passed`, and
    `ExitPlan.feasible`.
  - Reads Phase 6 `ManipulationLevel` and
    `TradeConfirmationLevel`.
  - Reads exchange-link state, market-data degraded view,
    stop-confirmation, position-known flag, and the two circuit
    breaker states.
  - Honours the `is_new_open` flag so Phase 9 can call the gate
    on a protective-exit / reduce-only path without M3 / regime /
    data-degraded firing.

- **`app/risk/account_tier.py`** (Spec §27.4, Issue #7).
  - `classify_account_tier(current_equity, initial_capital) ->
    AccountLifeTier` pure function (A..F by equity ratio).
  - `ACCOUNT_TIER_POLICY` table + `policy_for(tier)` helper. Each
    `AccountTierPolicy` exposes `allow_new_open`, `allow_attack`,
    `allow_right_tail_amplify`, `allow_live_trading`, `halt_only`,
    `paper_only`, `notes`. Tiers D / E / F progressively restrict
    the ladder; tier F is halt-only.

- **`app/risk/circuit_breaker.py`** (Spec §27.2, Issue #7).
  - `ConsecutiveLossCircuitBreaker` opens after N consecutive
    losses (default 5). `record_loss()` / `record_win()` /
    `reset()`. A winning trade does NOT auto-close an opened
    breaker - Phase 7 requires an explicit `reset()`.
  - `DailyLossCircuitBreaker` opens once cumulative gross daily
    loss exceeds `max_daily_loss_pct * initial_capital` (default
    5%). Rolls over on UTC date change. Same explicit-`reset()`
    contract.

- **`app/risk/engine.py` Phase 7 extension** (Spec §27, Issue #7).
  - `RiskRequest` gained ten optional Phase 7 fields:
    `is_new_open` (default `True` for backwards compat),
    `regime_snapshot`, `universe_decision`, `liquidity_decision`,
    `exit_plan`, `is_data_degraded`, `exchange_connection_state`,
    `current_equity`, `initial_capital`, `account_tier_override`.
  - `RiskEngine.evaluate(...)` now composes the Phase 1 hard
    flags + Phase 6 hard rules + the Phase 7 No-Trade Gate +
    Account Life Tier policy + Circuit Breaker state into one
    decision.
  - `RiskEngine.record_loss(loss_amount=)` /
    `record_win(profit_amount=)` /
    `configure_initial_capital(initial_capital=)` are the public
    hooks Issue #8 (Capital Flow Engine) will use to record
    realised PnL onto the breakers without re-instantiating the
    engine.
  - The audit payload extends Phase 6 with `account_tier`,
    `is_new_open`, `regime`, `risk_permission`,
    `exchange_connection_state`, `daily_loss_breaker_state`,
    `consecutive_loss_breaker_state`, `no_trade_gate_reasons`,
    `no_trade_gate_notes`. Reasons are still rendered as
    byte-compatible strings so Phase 1 / Phase 6 Replay code
    keeps working unchanged.

- **`app/core/enums.py`** new vocabulary:
  - `CircuitBreakerState` (`closed`, `open_daily_loss`,
    `open_consecutive_loss`, `cool_down`).
  - `TradeStateTrigger` (`signal`, `promote`, `downgrade`,
    `timeout`, `lock_profit`, `distribution_alert`,
    `forced_exit`, `kill_switch`, `reset`).
  - `RiskRejectReason` typed enum with **23** values covering
    Phase 1 + Phase 6 + Phase 7 reasons. Values match the Phase 1
    / Phase 6 string reasons byte-for-byte so existing tests and
    audit rows stay byte-compatible.

- **Phase 7 boot self-check in `python -m app.main`**.
  - Drives a `TradeStateMachine` `NO_TRADE -> OBSERVE`
    transition for the first mock symbol. One additional
    ``STATE_TRANSITION`` event is written via the state-machine
    module (the Phase 6 boot drill already wrote one
    `IDLE -> IDLE` marker; Phase 7 raises the total to two).
  - Calls `RiskEngine.evaluate(...)` with
    `is_new_open=False`, the Phase 5 regime snapshot, the Phase
    6 manipulation + confirmation levels, and the exchange link
    state. The bootstrap stays a clean approval because every
    `is_new_open=True`-only gate is bypassed.
  - Banner extended with four Phase 7 fields:
    `state_transitions=`, `trade_state=`, `daily_loss_breaker=`,
    `consecutive_loss_breaker=`.

- **Documentation**.
  - `README.md` rewritten: status table updated (Phase 6 ->
    merged, Phase 7 -> this branch); new "Phase 7 deliverable"
    section with the State Machine ladder + transition rules,
    No-Trade Gate composition, Account Life Tier table, Circuit
    Breaker contract, protective-exit caveat, and seven semantic
    locks.
  - `docs/CHANGELOG.md`: this entry. Phase 6 entries are
    preserved below.
  - `app/__init__.py` bumped to `Phase 7 - State Machine Risk
    Engine` / `1.4.0a7`.

#### Phase 7 hard rules enforced

| Rule | Enforcement |
|---|---|
| 1. No trade-state level skipping | `ALLOWED_TRANSITIONS` whitelist + `IllegalStateTransition`. |
| 2. SCOUT cannot become ATTACK directly | SCOUT -> CONFIRM is the only legal step in `ALLOWED_TRANSITIONS`. |
| 3. CONFIRM failures must downgrade | `record_breakout_failure()` after 2 consecutive failures returns SCOUT. |
| 4. DISTRIBUTION_ALERT cannot promote | `promote(...)` refuses with `cannot_promote_from_distribution_alert`. |
| 5. FORCED_EXIT is sticky | `ALLOWED_TRANSITIONS[FORCED_EXIT] = frozenset()`; only `reset()` clears it. |
| 6. Losing position cannot amplify | Refused at promotion; refused at engine via `right_tail_from_principal_forbidden`. |
| 7. SYSTEMIC_RISK -> BLOCK_ALL | `RiskRejectReason.REGIME_BLOCK_ALL` fires for every new opening. |
| 8. ALT_RISK_OFF -> ALLOW_SCOUT no attack | `RiskRejectReason.REGIME_SCOUT_ONLY_FOR_ATTACK` fires for `attack_intent=True`. |
| 9. M3 blocks new open | `RiskRejectReason.MANIPULATION_M3` fires when `is_new_open=True`; protective exits pass with `is_new_open=False`. |
| 10. M2 + attack_intent blocks | `RiskRejectReason.MANIPULATION_M2_ATTACK`. |
| 11. T0/T1 + attack_intent blocks | `RiskRejectReason.TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK`. |
| 12. 5 consecutive losses pause new open | `ConsecutiveLossCircuitBreaker` opens; engine emits `CONSECUTIVE_LOSS_BREAKER_OPEN`. |
| 13. Daily loss threshold pauses new open | `DailyLossCircuitBreaker` opens; engine emits `DAILY_LOSS_BREAKER_OPEN`. |
| 14. State transitions persisted | One `STATE_TRANSITION` event per accepted transition. |
| 15. Reject events carry typed reasons | Every reason is a `RiskRejectReason` value; rendered as its string in the audit row. |

#### Tests

123 new Phase 7 unit tests on top of the 591 retained from
Phase 1-6 = 714 total, all passing.

| File | Tests | What it covers |
| --- | --- | --- |
| `tests/unit/test_state_machine.py` | 27 | Issue #7 acceptance criteria 1+2 (no level skipping, no SCOUT->ATTACK), promotion guards, downgrade ladder, CONFIRM-failure threshold, DISTRIBUTION_ALERT cannot promote, three-bar -> FORCED_EXIT, FORCED_EXIT is sticky / only reset() clears it, Spec §26.4 timeouts (OBSERVE / SCOUT / ATTACK / RIGHT_TAIL_AMPLIFY), `STATE_TRANSITION` events persisted, refusal counter, custom `TimeoutConfig` honoured. |
| `tests/unit/test_account_tier.py` | 12 | Tier A..F classifier boundary tests, F when initial_capital invalid, per-tier `AccountTierPolicy` flags, policy table covers every tier. |
| `tests/unit/test_circuit_breaker.py` | 9 | Issue #7 acceptance criteria 12+13: 5 consecutive losses open the breaker; daily-loss threshold opens the breaker; winning does not auto-close an opened breaker; explicit reset returns to closed; gross daily loss is measured (not net); zero-amount and zero-initial-capital edge cases. |
| `tests/unit/test_no_trade_gate.py` | 23 | Every Spec §27.2 condition individually + composed. Acceptance criteria 4 (M2 + attack), 5 (T0/T1 + attack), 8 (liquidity not exitable), 9 (DATA_DEGRADED), plus the ALLOW_SCOUT-no-attack semantic lock and the M3 protective-exit caveat. |
| `tests/unit/test_risk_engine_phase7.py` | 18 | Liquidity reject, no-exit-channel reject, SYSTEMIC_RISK overrides T4 / M0, ALLOW_ATTACK alone does not authorise live trade, T3 alone does not authorise, M3 protective-exit caveat, DATA_DEGRADED rejects new open / passes protective exit, breakers + tier policies, audit payload exposes Phase 7 fields, Phase 1 + Phase 6 + Phase 7 reasons accumulate, `legacy_request_still_approved`. |
| `tests/unit/test_phase7_boundary.py` | 16 | Phase 1 + Phase 3 invariants unchanged, TradeState / AccountLifeTier / CircuitBreakerState / TradeStateTrigger / `RiskRejectReason` vocabularies pinned, public exports complete (`app.risk.__all__`, `app.state_machine.__all__`), Risk Engine + State Machine expose no write surface, do not subclass ExchangeClientBase, `RiskRequest` Phase 7 fields present, `is_new_open` defaults True. |
| `tests/unit/test_phase7_no_network.py` | 9 | No exchange SDK / LLM import under `app/state_machine/` or `app/risk/`, no `api_key` substring, no `os.environ` / `getenv` (AST scan), no write surface, no Issue #8 / #9 / #10 module imports, no MarketDataBuffer / Mock / Binance constructor call, no stand-alone BTC/ETH module added, no other-DB direct sqlite3.connect. |
| `tests/unit/test_main_entrypoint.py` | extended | Phase 7 banner fields (`Phase 7 - State Machine Risk Engine`, `state_transitions=`, `trade_state=`, `daily_loss_breaker=`, `consecutive_loss_breaker=`). |

#### Issue #7 acceptance criteria

| # | Criterion | Test |
| --- | --- | --- |
| 1 | OBSERVE 不能直接 RIGHT_TAIL_AMPLIFY | `test_observe_cannot_directly_become_right_tail_amplify` |
| 2 | SCOUT 不能直接 ATTACK | `test_scout_cannot_directly_become_attack` |
| 3 | M3 必须禁止新开仓 | `test_m3_blocks_new_open` (gate), `test_m3_does_not_block_protective_exit_when_is_new_open_false` (engine) |
| 4 | M2 + attack_intent 必须禁止 ATTACK / RIGHT_TAIL_AMPLIFY | `test_m2_with_attack_intent_blocks` |
| 5 | T0/T1 + attack_intent 必须拒绝进攻 | `test_t0_with_attack_intent_blocks` / `test_t1_with_attack_intent_blocks` |
| 6 | T3/T4 不得单独批准交易 | `test_t3_alone_does_not_authorise_live_trade` |
| 7 | ALLOW_ATTACK 不得单独批准交易 | `test_allow_attack_alone_does_not_authorise_live_trade` |
| 8 | Liquidity 不可退出时必须拒绝进攻 | `test_liquidity_rejected_blocks_attack` / `test_no_exit_channel_blocks_attack` |
| 9 | DATA_DEGRADED 时必须拒绝或降级 | `test_data_degraded_rejects_new_open` / `test_data_degraded_does_not_block_protective_exit` |
| 10 | stop_unconfirmed 必须拒绝新开仓 | `test_stop_unconfirmed_blocks` (gate) + Phase 1 test still applies |
| 11 | unknown_position 必须拒绝新开仓 | `test_unknown_position_blocks` / `test_unknown_position_rejected_for_new_open` |
| 12 | 连续亏损 5 次必须暂停新开仓 | `test_consecutive_loss_breaker_opens_at_threshold` + `test_consecutive_loss_breaker_blocks_new_open` |
| 13 | 单日亏损触发必须暂停新开仓 | `test_daily_loss_breaker_opens_at_threshold` + `test_daily_loss_breaker_blocks_new_open` |
| 14 | 状态转移事件可回放 | `test_state_transition_event_persisted` / `test_full_ladder_writes_all_transition_events` |
| 15 | 风控拒绝事件包含 reason_tags | `test_audit_payload_includes_phase7_fields` (typed `RiskRejectReason` -> string) |
| 16 | pytest 全部通过 | 714 passed |
| 17 | 不存在 live trading 风险 | Defence-in-depth (see "Live trading risk" below) |
| 18 | 不存在真实交易所下单风险 | Same as 17 |

#### Live trading risk

**None.** Phase 7 is additive on top of the Phase 1 - 6 safety
substrate. No exchange SDK, no HTTP client, no LLM client, no
write surface. The Phase 1 safety lock, the Phase 3 read-only
invariant, the Phase 4 / 5 / 6 boundaries are all unchanged. The
boot banner still shows
`mode=paper live_trading=False right_tail=False llm=False
exchange_live_orders=False`.

#### Real exchange order risk

**None.** No `create_order` / `cancel_order` / `set_leverage` /
`set_margin_mode` call site is added. The four
`SafeModeViolation` refusals on `ExchangeClientBase` continue to
apply.

#### Next-phase recommendation

After this merges, **Issue #8 (Phase 8 - Capital Flow / Profit
Harvest / Rebase)** is the next phase. Issue #8 will:

- Replace the in-memory counters in
  `RiskEngine.consecutive_loss_breaker` / `daily_loss_breaker`
  with `capital.db.capital_snapshots` lookups.
- Drive `RiskEngine.configure_initial_capital(...)` from the
  capital event stream, so Account Tier classification is
  always anchored to the latest `lifetime_equity`.
- Add the `CAPITAL_REBASE` flow: pause new openings, recompute
  `risk_budget`, recompute `account_life_tier`, then resume.
- Land the `withdrawn_profit` invariant so a user-initiated
  withdrawal is NOT misread as a draw-down.

The Phase 7 boundary (no exchange SDK, no real network, no API
key, no write surface, no LLM, no stand-alone BTC/ETH module,
trade-state level whitelist) plus the cumulative defence-in-depth
layers will continue to gate against accidental live trading
until the Go/No-Go checklist (§41) is executed end to end.

### Phase 6 - Scanner Confirmation Manipulation

#### Added

- **`app/scanner/` package** (Spec §17 / §18, Issue #6).
  - `PreAnomalyScanner.evaluate(PreAnomalyInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`PreAnomalyDecision` with `pre_anomaly_score` and
    `reason_tags`. Six Spec §17.2 signals: volume base-expansion,
    spread compression, buy-pressure rising, OI soft-rise,
    funding-not-overheated, minor uptrend.
  - `AnomalyScanner.evaluate(AnomalyInput)` returns
    :class:`AnomalyDecision` with `anomaly_score` (Spec §18.2
    weighted sum) and `reason_tags`. Eight Spec §18.1 signals:
    `OI_SPIKE`, `CVD_SPIKE`, `VOLUME_SPIKE`, `ATR_EXPANSION`,
    `FUNDING_EXTREME`, `LIQUIDATION_SPIKE`, `SWEEP`,
    `MULTI_TIMEFRAME_BREAKOUT`. The Spec §18.2 weights live in
    `AnomalyConfig` and sum to 1.0; sweep + multi-tf-breakout add
    bonuses on top so a clean structural breakout is not missed
    when the underlying spikes are not yet extreme.
  - Emits one ``PRE_ANOMALY_DETECTED`` and one ``ANOMALY_DETECTED``
    event per evaluation. Both event types were already declared
    in the Phase 1 :class:`EventType` vocabulary; Phase 6
    populates them.

- **`app/confirmation/` package - Real Trade Confirmation**
  (Spec §20, Issue #6).
  - `RealTradeConfirmation.evaluate(ConfirmationInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`ConfirmationDecision` mapping fired-signal count to a
    :class:`TradeConfirmationLevel` (T0..T4):
    - 0 signals  -> T0
    - 1 signal   -> T1
    - 2 signals  -> T2
    - 3 signals  -> T3
    - 4+ signals -> T4
  - Five Spec §20.4 signals: CVD-price agreement, breakout hold
    over N bars, large-trade follow-through, trade-efficiency
    above mean, volume-up-price-move.
  - Emits one ``TRADE_CONFIRMED`` event per evaluation.

- **`app/manipulation/` package - Manipulation Detector**
  (Spec §21, Issue #6).
  - `ManipulationDetector.evaluate(ManipulationInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    :class:`ManipulationDecision` mapping fired-signal count to a
    :class:`ManipulationLevel` (M0..M3):
    - 0 signals  -> M0
    - 1 signal   -> M1
    - 2 signals  -> M2
    - 3+ signals -> M3
  - Eight Spec §21.2 signals: CVD up + price flat (CVD-price
    divergence), volume up + price no move, OI up + price flat,
    funding hot + price weak, upper-wick growth, buy-pressure-
    no-push, book-wall flicker (caller-supplied count), narrative-
    after-pump.
  - Emits one ``MANIPULATION_DETECTED`` event per evaluation.

- **Risk Engine Phase 6 hooks** (Issue #6 hard rules).
  - `RiskRequest` gained three optional fields:
    - `manipulation_level: ManipulationLevel | None`
    - `trade_confirmation_level: TradeConfirmationLevel | None`
    - `attack_intent: bool` (default `False`)
  - New `RiskRequest.effective_attack_intent` property:
    `right_tail_amplify=True` always implies attack intent.
  - Three new Phase 6 rejection rules in `RiskEngine.evaluate`:
    - `manipulation_m3` -> reject every new opening
      (Spec §21.3 "M3 禁止交易").
    - `manipulation_m2_attack` -> reject ATTACK /
      RIGHT_TAIL_AMPLIFY only (Spec §21.3 "M2 禁止进攻").
    - `trade_confirmation_too_low_for_attack` -> reject ATTACK
      candidates when the level is T0 / T1 (Issue #6 "T0/T1 不
      允许进攻"). Smaller scout / observe actions remain
      allowed; the gate is size-class, not blanket.
  - The ``RISK_REJECTED`` / ``RISK_APPROVED`` audit payload now
    carries `attack_intent`, `manipulation_level`,
    `trade_confirmation_level` so Replay (Issue #10) can
    reconstruct every Phase 6 decision from `events.db` alone.
  - Phase 1 hard rejections (`live_trading_disabled`,
    `right_tail_disabled`, `stop_unconfirmed`, `unknown_position`,
    `trading_mode_inconsistent`) are unchanged. The Phase 6 rules
    are additive.

- **Reason-tag enums in `app/core/enums.py`:**
  - `PreAnomalyReasonTag` (9 values: 6 Spec §17.2 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `AnomalyReasonTag` (11 values: 8 Spec §18.1 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `ConfirmationReasonTag` (8 values: 5 Spec §20.4 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).
  - `ManipulationReasonTag` (11 values: 8 Spec §21.2 signals +
    `DATA_DEGRADED` / `REGIME_BLOCKED` / `INSUFFICIENT_HISTORY`).

- **Event-emission throttle**, mirroring the Phase 5 PR #16
  review-fix shape:
  - Each of `PreAnomalyConfig`, `AnomalyConfig`,
    `ConfirmationConfig`, `ManipulationConfig` exposes
    `event_emit_enabled: bool` (default `True`).
  - Every classifier accepts a per-call `emit_event: bool | None`
    on its `evaluate` and `evaluate_snapshot` entry points.
  - Resolution rule: `True` -> always emit, `False` -> always
    skip, `None` -> follow the config flag.
  - Each classifier exposes two counters:
    `<event>_events_emitted` and `<event>_events_skipped`. Issue
    #7's full Top-200 scanner can flip the config flag off and
    confirm via the counter that the event is being skipped.

- **Boot drill in `python -m app.main`:**
  - After the Phase 5 Liquidity loop, runs all four classifiers
    once per mock symbol (3 symbols -> 12 new events: 3
    ``PRE_ANOMALY_DETECTED``, 3 ``ANOMALY_DETECTED``, 3
    ``TRADE_CONFIRMED``, 3 ``MANIPULATION_DETECTED``).
  - Tracks the worst-observed manipulation + confirmation level
    and feeds them into the bootstrap Risk Engine self-check
    with `attack_intent=False` so the bootstrap stays approved.
    The resulting ``RISK_APPROVED`` audit row exercises the new
    payload fields end-to-end.
  - Banner extended with four new fields:
    `pre_anomaly_events`, `anomaly_events`,
    `trade_confirmed_events`, `manipulation_events`.

#### Phase 6 hard rules (per Issue #6)

1. **M2 forbids ATTACK / RIGHT_TAIL_AMPLIFY.** Risk Engine emits
   `manipulation_m2_attack` when `attack_intent=True`.
2. **M3 forbids any new opening.** Risk Engine emits
   `manipulation_m3` regardless of `attack_intent`.
3. **T0 / T1 forbid ATTACK candidates.** Risk Engine emits
   `trade_confirmation_too_low_for_attack` when
   `attack_intent=True`.
4. **All four classifier outputs are persisted as events.** One
   event per evaluation, full payload + reason-tag list, so
   Reflection (Issue #10) and Replay can reconstruct the
   decision from `events.db` alone.
5. **Every reject path carries `reason_tags`.** Tuples of typed
   enum values, never free-form strings.

#### Phase 6 boundary (declared explicitly so the next PR cannot drift)

1. Pre-Anomaly / Anomaly / Real-Trade Confirmation / Manipulation
   ONLY. **No Strategy Engine, no State Machine, no LLM, no
   Capital Flow, no Execution FSM, no Reconciliation.** Those
   land with Issue #7 / #8 / #9 / #10.
2. **No write surface added.** The four `SafeModeViolation`
   refusals on `ExchangeClientBase` are unchanged.
3. **No LLM.** No `app/scanner/`, `app/confirmation/`,
   `app/manipulation/` source file imports `openai`, `anthropic`,
   `deepseek`, or any other LLM client. Issue #6 forbids using an
   LLM to decide direction or to bypass the Risk Engine.
4. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
   `BinanceClient.get_*` continues to raise `NotImplementedError`.
5. **No API key.** No source file under the three new packages
   reads `os.environ` for a credential, accepts an `api_key`
   keyword argument, or persists a key.
6. **No auto-connect.** The classifiers do not own a
   `MarketDataBuffer`, do not own an `ExchangeClientBase`, and
   never instantiate one for themselves.
7. **Phase 1 / 3 / 4 / 5 invariants intact.** The Phase 1 safety
   lock, the Phase 3 read-only invariant, the Phase 4 Market Data
   Buffer boundary, and the Phase 5 Regime / Universe / Liquidity
   contract are unchanged.

#### Tests

`tests/unit/test_pre_anomaly_scanner.py`,
`tests/unit/test_anomaly_scanner.py`,
`tests/unit/test_real_trade_confirmation.py`,
`tests/unit/test_manipulation_detector.py`,
`tests/unit/test_risk_engine_phase6.py`,
`tests/unit/test_phase6_no_network.py`,
`tests/unit/test_phase6_boundary.py`, plus the existing
`tests/unit/test_main_entrypoint.py` extended with the Phase 6
banner + 4 new event-type assertions.

**+117 new Phase 6 tests on top of the 457 retained from Phase
1-5 = 574 total, all passing.**

Issue #6 acceptance criteria covered:

1. **mock 数据能触发 T3** -
   `test_mock_input_triggers_t3` (3 fired signals).
2. **mock 派发数据能触发 M2/M3** -
   `test_distribution_mock_data_triggers_m2`,
   `test_distribution_mock_data_triggers_m3`,
   `test_full_distribution_with_wick_and_flicker_triggers_m3`.
3. **M3 时 Risk Engine 必须拒绝** -
   `test_m3_rejects_observation_request`,
   `test_m3_rejects_attack_request`,
   `test_m3_rejection_writes_audit_event`.
4. **Volume Up + Price No Move 有测试** -
   `test_volume_up_price_no_move_signal_fires`,
   `test_volume_up_price_no_move_does_not_fire_when_price_actually_moves`.
5. **OI Up + Price Flat 有测试** -
   `test_oi_up_price_flat_signal_fires`,
   `test_oi_up_price_flat_does_not_fire_when_price_moves`.
6. **pytest 通过** - 574 passed.

#### Live trading risk

**None.** Phase 6 adds:

- Four pure stateless classifiers (`PreAnomalyScanner`,
  `AnomalyScanner`, `RealTradeConfirmation`,
  `ManipulationDetector`).
- Four reason-tag enums + four event-payload shapes.
- Three new optional fields on `RiskRequest` and three additive
  rejection rules in `RiskEngine.evaluate` that follow the same
  pattern Phase 1 introduced.
- One boot-drill loop that exercises every classifier against
  the deterministic `MockExchangeClient`.
- 117 new unit tests.

What Phase 6 does NOT add:

- No exchange SDK in `requirements.txt` / `pyproject.toml`.
- No outbound HTTP / WebSocket client of any kind in `app/`.
- No LLM client of any kind.
- No `create_order` / `cancel_order` / `set_leverage` /
  `set_margin_mode` call site.
- No new mode flags, no loosened safety lock, no relaxed
  read-only invariant.

The `python -m app.main` boot banner continues to log all five
safety flags every run:

```
mode=paper live_trading=False right_tail=False
llm=False exchange_live_orders=False
```

Sample Phase 6 boot output:

```
[AMA-RT] Phase 6 - Scanner Confirmation Manipulation v1.4.0a6 \
  mode=paper live_trading=False right_tail=False \
  llm=False exchange_live_orders=False \
  databases=5 events_count=31 capital_events=1 \
  exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
  market_data=3/0 market_snapshots=3 data_unreliable=1 \
  regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
  universe=0/3 universe_events=3 liquidity_events=6 \
  pre_anomaly_events=3 anomaly_events=3 trade_confirmed_events=3 \
  manipulation_events=3 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

### Phase 5 - Review fixes (PR #16 review feedback)

The four follow-up clarifications requested on PR #16 are documentation
+ observability only. No mode flag is loosened, no safety lock is
relaxed, no new dependency, no new write surface, no new network
surface. The Phase 1 safety lock and the Phase 3 read-only invariant
are unchanged.

#### Added

- **`UniverseConfig.event_emit_enabled`** (default `True`) -
  construct-time throttle for `UNIVERSE_FILTERED` events. Phase 5's
  boot drill, replay, and reflection paths still observe every
  decision; Issue #6's full Top-200 scanner can flip this to `False`
  to avoid bloating events.db at scan rate. The per-call
  `emit_event=True` override on
  `UniverseFilter.evaluate` / `evaluate_snapshot` / `evaluate_many`
  still lets monitoring write an on-demand audit-trail entry.
  Mirrors Phase 4's
  `MarketDataBufferConfig.market_snapshot_event_emit_enabled`.
- **`LiquidityConfig.event_emit_enabled`** (default `True`) - the
  same construct-time throttle for `LIQUIDITY_CHECKED` events. Two
  events per symbol per tick (one `check="evaluate"` + one
  `check="can_exit_position"`) at Top-200 scan rate would mean
  ~400 events/tick; Issue #6 / #7 high-frequency consumers will flip
  this to `False`.
- **`UniverseFilter.universe_filtered_events_skipped`** property -
  counts decisions that were NOT persisted because either the
  per-call override or the config flag suppressed them. Confirms
  the throttle is doing what it claims.
- **`LiquidityFilter.liquidity_checked_events_skipped`** property -
  the same counter for the Liquidity Filter. Both `evaluate` and
  `can_exit_position` increment it.
- **`emit_event` resolution policy** (mirrors the Phase 4 review
  fix on `MarketDataBuffer.snapshot()`):

  ```text
  emit_event=True   -> always emit (per-call override)
  emit_event=False  -> always skip (per-call override)
  emit_event=None   -> follow config.event_emit_enabled (default)
  ```

  applied on `UniverseFilter.evaluate`,
  `UniverseFilter.evaluate_snapshot`,
  `UniverseFilter.evaluate_many`,
  `LiquidityFilter.evaluate`,
  `LiquidityFilter.evaluate_with_buffer`,
  `LiquidityFilter.can_exit_position`, and the module-level
  `app.liquidity.filter.can_exit_position` free function.

- **`RiskPermission` docstring rewritten** to make the
  regime-cycle-gate vs. trade-approval distinction explicit
  (review items 1 + 2). Key clarifications now part of the
  source:
  1. `ALLOW_ATTACK` is a market-cycle permission, NOT a trade
     approval. A real opening still requires Universe.eligible,
     Liquidity.passed, can_exit_position.feasible, Issue #6 scanners
     (Pre-Anomaly / Anomaly / Real-Trade Confirmation /
     Manipulation), and the Issue #7 Risk Engine's final word.
     The eight-step conjunctive ladder is enumerated in the
     docstring.
  2. `ALLOW_SCOUT` (the `ALT_RISK_OFF` fallback and the unknown-
     inputs default) permits only OBSERVE or a tiny SCOUT
     candidate. Issue #7 MUST further restrict: NO ATTACK, NO
     RIGHT_TAIL_AMPLIFY, SCOUT size capped at the per-trade scout
     budget. The `right_tail_enabled` flag is locked False through
     the limited-live phase regardless.
  3. `OBSERVE_ONLY` blocks new openings; existing positions
     remain managed.
  4. `BLOCK_ALL` is SYSTEMIC_RISK; no new opening of any kind.

- **`REGIME_TO_RISK_PERMISSION` map docstring** in
  `app/regime/models.py` echoes the same warning so anyone reading
  the source-of-truth dict sees the regime-gate vs.
  trade-approval distinction without having to chase the enum.

- **`RegimeSnapshot.risk_permission` docstring warning** -
  pointed at `RiskPermission` for the full ladder. The first
  reader of a `RegimeSnapshot` value will not silently treat
  `ALLOW_ATTACK` as authorisation.

- **`LiquidityFilter.can_exit_position` docstring rewritten** to
  cover the throughput-discount contract (review item 3):
  - The `volume_5m / 300s` fallback is documented as an UPPER
    BOUND, not a conservative estimate. Three reasons are listed
    (calm-tape extrapolation, no-crowding assumption, no ATR / OI
    discount).
  - Issue #7's Risk Engine MUST apply a conservative discount on
    top. Three recommended directions are documented (ATR-scaled
    divisor, fraction-of-average cap, post-discount feasibility
    re-check). Phase 5 ships the gate; sizing decisions are
    Issue #7's job.
  - Degraded-data contract pinned: callers in Phase 7+ MUST pass
    `MarketDataBuffer.is_degraded(symbol)` through, never invert
    `feasible=False`, never feed a stale book with
    `is_data_degraded=False`. The buffer's degraded view is the
    single source of truth.
- **`_VOLUME_WINDOW_5M_SECONDS` module constant** in
  `app/liquidity/filter.py` got its own warning comment block
  describing the same upper-bound assumption set so a future
  reader of the constant does not need to chase the docstring.
- **Free-function `can_exit_position`** docstring restates the
  same throughput-and-degraded contract with a pointer back to
  the method form.

#### Tests

`tests/unit/test_phase5_review_fixes.py` (NEW) covers:
- The two new config flags exist with correct defaults.
- The `*_events_skipped` counters are exposed and start at zero.
- `event_emit_enabled=False` + `emit_event=None` -> emits 0,
  skipped += 1 (Universe and Liquidity).
- `event_emit_enabled=False` + `emit_event=True` -> still emits
  (per-call override beats config).
- `event_emit_enabled=True` + `emit_event=False` -> still skips
  (per-call override beats config).
- `can_exit_position` (both method and free function) honours
  the same `bool | None` resolution rules.
- `RiskPermission` docstring contains the
  "regime-cycle permission" + "NOT a trade approval" wording so
  the regime-gate vs. trade-approval distinction cannot drift.
- `REGIME_TO_RISK_PERMISSION` map docstring contains the same
  warning so a future map mutation cannot silently weaken the
  contract.
- `LiquidityFilter.can_exit_position` docstring contains the
  upper-bound + Issue #7-discount + degraded-data wording.

#### Live trading risk

**None.** This commit only:

- Adds two construct-time throttle flags that default to today's
  behaviour (emit every event).
- Adds two skipped-event counters for monitoring.
- Rewrites three docstrings (`RiskPermission`,
  `REGIME_TO_RISK_PERMISSION`, `RegimeSnapshot.risk_permission`,
  `LiquidityFilter.can_exit_position`) and one constant comment
  (`_VOLUME_WINDOW_5M_SECONDS`).
- Adds one test file pinning the new flags + the docstring
  boundary phrases.

The Phase 1 safety lock, the Phase 3 read-only invariant, the
Phase 4 Market Data Buffer boundary, and the original Phase 5
classifier behaviour are all unchanged.

### Phase 5 - Regime Universe Liquidity

#### Added

- **`app/regime/` package** introducing the Regime Engine (Spec §15).
  - `RegimeConfig`, `RegimeInput`, `RegimeSnapshot` (Pydantic v2 frozen
    value objects).
  - `REGIME_TO_RISK_PERMISSION` static map (Spec §15.3) wired into
    Phase 7's future Risk Engine, the Universe Filter, and the
    Liquidity Filter.
  - `RegimeEngine.evaluate(request=...)` for tests and
    `RegimeEngine.evaluate(buffer=..., btc_symbol=...)` /
    `evaluate_from_buffer()` for the boot path. The classifier walks
    in this order:

      1. **SYSTEMIC_RISK overrides** - explicit flag, BTC return <=
         configured drop threshold, BTC ATR >= configured extreme.
         All three force `MarketRegime.SYSTEMIC_RISK` /
         `RiskPermission.BLOCK_ALL`.
      2. **Data degraded fallback** - any input flagged
         `data_degraded=True` falls back to `MarketRegime.ALT_RISK_OFF`
         / `RiskPermission.ALLOW_SCOUT`.
      3. **Trend / volatility / liquidity classifier** - five regimes:
         `MEME_RISK_ON`, `SECTOR_ROTATION`, `BTC_ABSORPTION`,
         `ALT_RISK_OFF`, `SYSTEMIC_RISK`.
  - One ``REGIME_UPDATED`` event per evaluation, with the full Spec
    §15.1 payload (`market_regime`, `btc_trend`, `btc_volatility`,
    `alt_liquidity`, `risk_permission`, `reason_tags`).

- **`app/universe/` package** introducing the Universe Filter
  (Spec §16).
  - `UniverseConfig`, `UniverseInput`, `UniverseDecision` value
    objects.
  - `UniverseFilter.evaluate(...)` walks **nine** reject conditions in
    a stable order and returns the full reason list:
    `REGIME_BLOCKED`, `DATA_DEGRADED`, `ABNORMAL_DATA_FLAG`,
    `DATA_RELIABILITY_TOO_LOW`, `CONTRACT_NOT_TRADING`,
    `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`, `TRADE_DISCONTINUOUS`,
    `VOLUME_BELOW_MINIMUM`.
  - `evaluate_snapshot(snapshot, symbol_meta=, regime=, ...)`
    convenience helper consumes the Phase 4 `MarketSnapshot` directly.
  - One ``UNIVERSE_FILTERED`` event per symbol with the eligibility
    decision, full reject-reason list, and the input metrics. The
    event is persisted regardless of the eligible / rejected outcome
    so Replay (Issue #10) can rebuild the decision from events.db.

- **`app/liquidity/` package** introducing the Liquidity Filter
  (Spec §19).
  - `LiquidityConfig`, `LiquidityInput`, `LiquidityDecision`,
    `ExitPlan`, `Side` value objects.
  - **`app/liquidity/slippage.py`** - pure helpers: `estimate_book_walk`,
    `estimated_slippage_pct`, `walk_book_for_quote_notional`. Each
    walks the *opposite* side of the order book against a planned qty
    or a planned quote-notional and returns a `BookWalkResult` with
    cleared qty, weighted-average fill price, worst price, slippage
    pct, and an `exhausted` flag. No state, no events, no IO.
  - `LiquidityFilter.evaluate(...)` produces a `LiquidityDecision`
    with `spread_score`, `depth_score`, `estimated_slippage_pct`,
    `estimated_exit_seconds`, `exit_plan`, and the full reject-reason
    list. Reasons: `REGIME_BLOCKED`, `DATA_DEGRADED`, `BOOK_MISSING`,
    `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`, `SLIPPAGE_TOO_HIGH`,
    `NO_EXIT_CHANNEL`, `EXIT_TOO_SLOW`. Spec §19.1.
  - **`LiquidityFilter.can_exit_position(symbol, qty,
    max_slippage_pct, max_seconds, ...)`** (Spec §19.2 - mandatory
    function). Returns an `ExitPlan` describing whether the position
    can be flattened within `max_seconds` at `<= max_slippage_pct`
    given the current book and rolling 5-minute throughput.
    `feasible=False` is the binary the Risk Engine (Issue #7) will
    consult through the No-Trade Gate.
  - Module-level **`can_exit_position(...)` free function** so
    Issue #7's No-Trade Gate can call it without keeping a filter
    instance around.
  - One ``LIQUIDITY_CHECKED`` event per call, tagged
    `check="evaluate"` or `check="can_exit_position"`, with the full
    metric set on the payload.

- **Core vocabulary additions** in `app/core/enums.py`:
  - `BtcTrend` (UP / SIDEWAYS / DOWN / UNKNOWN).
  - `BtcVolatility` (LOW / NORMAL / HIGH / EXTREME / UNKNOWN).
  - `AltLiquidity` (EXPANDING / STABLE / CONTRACTING / DRY / UNKNOWN).
  - `RiskPermission` (ALLOW_ATTACK / ALLOW_SCOUT / OBSERVE_ONLY /
    BLOCK_ALL). Spec §15.3 maps every regime to one of these values.
  - `UniverseRejectReason` - 9 hardcoded reasons.
  - `LiquidityRejectReason` - 8 hardcoded reasons.
  - `MarketRegime` was already declared in Phase 1; the
    `REGIME_UPDATED` / `UNIVERSE_FILTERED` / `LIQUIDITY_CHECKED`
    event types were already declared in Phase 1 too. Phase 5
    populates them.

#### Phase 5 boot self-check in `python -m app.main`

Phase 5 extends the boot drill to drive every new module against the
same deterministic in-process mock + buffer:

  - One ``REGIME_UPDATED`` event written. The default mock seed
    classifies as `ALT_RISK_OFF / ALLOW_SCOUT` (BTC trend cannot be
    derived from the seed - we have no historical bars - so the
    engine falls back to the conservative risk-off label, exactly as
    Issue #5 mandates).
  - One ``UNIVERSE_FILTERED`` event per symbol. The deterministic
    mock book is intentionally shallow, so the boot drill exercises
    the rejection path end-to-end (depth_insufficient,
    trade_discontinuous, regime_blocked when applicable).
  - Two ``LIQUIDITY_CHECKED`` events per symbol: one from
    `LiquidityFilter.evaluate` (`check="evaluate"`) and one from
    `LiquidityFilter.can_exit_position` (`check="can_exit_position"`).
  - A `regime_gate` health probe is registered. It reports
    `DEGRADED` only when `risk_permission` is `BLOCK_ALL`.
  - Banner extended with seven Phase 5 fields:
    `regime=<market_regime>/<risk_permission>`, `regime_events`,
    `universe=<eligible>/<total>`, `universe_events`,
    `liquidity_events`.

  Sample boot output (default mock seed; same shape every run):

  ```
  [AMA-RT] Phase 5 - Regime Universe Liquidity v1.4.0a5 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=19 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
    universe=0/3 universe_events=3 liquidity_events=6 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

#### Phase 5 hard rules enforced

1. **SYSTEMIC_RISK -> BLOCK_ALL** is the only action attached to
   `RiskPermission.BLOCK_ALL`, which sits in
   `UniverseConfig.blocking_risk_permissions` and
   `LiquidityConfig.blocking_risk_permissions` by default. Any new
   opening through either filter is hard-rejected with
   `REGIME_BLOCKED`.
2. **Insufficient liquidity -> reject** with reasons. The Liquidity
   Filter inspects spread, depth, slippage, and exit time;
   any single threshold violation produces a typed reject reason.
3. **No exit channel -> reject the attack candidate.** The
   `can_exit_position` book walk returns `exhausted=True` when the
   book runs out before `qty` is filled; that maps to
   `NO_EXIT_CHANNEL` and `feasible=False` on the `ExitPlan`.
4. **Data degraded -> reject (or downgrade for the regime).** The
   buffer's `is_degraded(symbol)` flows into both filters as
   `is_data_degraded=True`, producing `DATA_DEGRADED` reject reasons.
   The Regime Engine treats the same flag as a fall-back to
   `ALT_RISK_OFF / ALLOW_SCOUT`.
5. **Every reject carries `reject_reasons`.** Both filters return
   `tuple[RejectReason, ...]` plus a free-form `notes` tuple.
6. **Every reject is persisted as one event.** The
   ``UNIVERSE_FILTERED`` and ``LIQUIDITY_CHECKED`` events carry the
   full metric snapshot AND the reason list, so Replay (Issue #10)
   can rebuild the decision from events.db alone.

#### Phase 5 boundary (declared explicitly to avoid drift)

This PR observes the boundary set by Issue #5:

1. **Regime / Universe / Liquidity ONLY.** No anomaly scanner, no
   real-trade confirmation, no manipulation detector, no strategy,
   no state machine. Those land in Issue #6 / #7.
2. The three engines read from the Phase 4 `MarketDataBuffer` and
   the Phase 3 `ExchangeClientBase` only. **They do NOT call any
   write surface; they do NOT add any write surface.** The four
   `SafeModeViolation` refusals on `ExchangeClientBase` are
   unchanged.
3. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
   `BinanceClient.get_*` continues to raise `NotImplementedError`
   for every read method.
4. **No API key.** None of `app/regime/`, `app/universe/`,
   `app/liquidity/` parameterises a credential, reads `os.environ`
   for one, or has an `api_key` keyword argument anywhere.
5. **No write surface.** Same refusal as Phase 3 / Phase 4.
6. **No auto-connect.** The three engines do not own a
   :class:`MarketDataBuffer`, do not own an
   :class:`ExchangeClientBase`, and never instantiate one for
   themselves. Tests pass stub buffers / explicit inputs.
7. **Tests do not depend on real network**
   (`test_phase3_no_network.py`, `test_phase4_no_network.py`, and
   the new `test_phase5_no_network.py`).
8. `BinanceClient.get_account_snapshot` continues to refuse outright
   in Phase 3, Phase 4, **and** Phase 5. No change.

#### Not in Phase 5 (deferred)

- Issue #6 - Pre-anomaly / Anomaly / Real-Trade Confirmation /
  Manipulation Detector.
- Issue #7 - Full Risk Engine + State Machine (will read
  `RegimeSnapshot.risk_permission`, `UniverseDecision.eligible`, and
  `LiquidityFilter.can_exit_position` at the No-Trade Gate).
- Issue #8 - Capital Flow Engine.
- Issue #9 - Real Execution FSM + Reconciliation.
- Issue #10 - LLM, Telegram outbound, Replay diff reports,
  Reflection.

#### Live trading risk

**None.** Phase 5 ships only three pure classifiers (`RegimeEngine`,
`UniverseFilter`, `LiquidityFilter`), pure helpers
(`estimate_book_walk`, `walk_book_for_quote_notional`), three new
event-emission paths through the existing `EventRepository`, and a
boot-time self-check that drives them through one decision per
symbol against the deterministic `MockExchangeClient`. No exchange
SDK is added. No outbound HTTP / WebSocket library is imported. No
API key is read. No write surface is added. The Phase 1 safety
lock, the Phase 3 read-only invariant, and the Phase 4 Market Data
Buffer boundary are unchanged. Seven layers of defence (config
lock, Phase 1 boot assertion, Phase 3 read-only assertion, Risk
Engine refusal, base-class write-surface refusal, Phase 4 no-network
/ no-API-key tests, Phase 5 no-network / no-write-surface / no-API-key
tests) are all unit-tested.

### Phase 4 - Review fixes (PR #15 review feedback)

#### Added

- **`MarketDataBufferConfig.market_snapshot_event_emit_enabled`**
  (default `True`) - construct-time throttle for `MARKET_SNAPSHOT`
  events. Phase 4 keeps the existing per-call
  ``snapshot(symbol, emit_event=...)`` override; this config flag
  lets a Phase 5+ high-frequency consumer (anomaly scanner, regime
  engine) flip the default once instead of having to remember
  ``emit_event=False`` at every call site. The MarketSnapshot return
  value is unchanged - only the events.db append is suppressed -
  so downstream code stays event-shape-stable.
- **`MarketDataBuffer.market_snapshot_events_skipped`** property +
  **`BufferStats.market_snapshot_events_skipped`** field. Confirms
  that the throttle is actually doing what it claims to do.
- **`MarketDataBuffer.late_trades_dropped_total`** property +
  **`BufferStats.late_trades_dropped_total`** field. Aggregates
  `CandleBuilder.dropped_late_trades` across every tracked symbol
  so an out-of-order tape (mis-ordered REST replay, inverted aggTrade
  delivery, producer clock skew) is observable from a single counter.
  Issue #5 / #6 monitoring will alert on this.
- **`refresh_from_exchange` docstring rewritten** to declare the
  Phase 4 boundary verbatim: mock-only / fixture-driven by default,
  no auto-connect to a real public adapter, opt-in only with no API
  key and no write surface, tests must not depend on real network.
  The contract is pinned by
  `tests/unit/test_market_data_buffer_review_fixes.py
  ::test_refresh_from_exchange_docstring_declares_phase4_boundary`.
- **8 new unit tests**
  (`tests/unit/test_market_data_buffer_review_fixes.py`):
  - `test_default_emits_market_snapshot_event`
  - `test_explicit_emit_false_skips_event`
  - `test_config_flag_disables_emit_by_default`
  - `test_config_flag_off_but_explicit_true_still_emits`
  - `test_late_trades_dropped_counter_starts_at_zero`
  - `test_late_trades_dropped_counter_increments_on_out_of_order_tape`
  - `test_late_trades_dropped_counter_isolates_per_symbol_aggregate`
  - `test_refresh_from_exchange_docstring_declares_phase4_boundary`

#### Changed

- `MarketDataBuffer.snapshot()` parameter `emit_event` is now
  `bool | None` (default `None`); `None` resolves to the new config
  flag. `True` / `False` overrides remain available per call. This is
  source-compatible: every existing call site that passed
  `emit_event=True` / `emit_event=False` keeps its old behaviour
  exactly.

#### Tests

**+8 review-fix tests on top of 311 = 319 total. Full suite: 319
passed in 2.21s.**

#### Live trading risk

None. The review fixes only add observability counters, a
construct-time throttle for an existing event emission, and tighten
the docstring of an existing helper. No new mode flag, no loosened
safety lock, no new dependency, no new write surface, no new
network surface.

### Phase 4 - Market Data Buffer

#### Added
- **`app/market_data/` package** introducing the in-process Market
  Data Buffer that every later phase will read from. The package
  never imports an exchange SDK, never opens an outbound socket,
  never reads a credential, never adds a write surface. This is
  asserted by `tests/unit/test_phase4_no_network.py` (and by the
  pre-existing repo-wide `test_phase3_no_network.py`).

- **`app/market_data/models.py`** - frozen Pydantic v2 value objects:
  - `Bar`, `BarInterval` (`M1` / `M5`).
  - `LiquidationEvent`, `LiquidationSide` (data shape only - Phase 4
    does NOT subscribe to a real liquidation feed).
  - `MarketDataBufferConfig`, `MarketDataStalenessConfig` -
    rolling-window widths (1m / 5m / 15m), bar-history sizes, ATR
    windows, per-surface staleness thresholds.
  - `MarketDataDegradedReason` enum: `never_initialised`,
    `exchange_disconnected`, `exchange_degraded`, `trades_stale`,
    `orderbook_stale`, `oi_stale`, `funding_stale`,
    `rest_ws_conflict`, `explicit_mark`. Vocabulary locked by
    `tests/unit/test_market_data_models.py::test_degraded_reason_vocabulary`.
  - `BufferStats` - per-tick observability shape exposed by
    `MarketDataBuffer.stats()`.
  - The Spec §11.1 `MarketSnapshot` model lives in
    `app/core/models.py` (Phase 1) - this PR populates it, it does
    NOT redefine it.

- **`app/market_data/candles.py`** - streaming OHLCV builder with
  buy / sell taker volume split. Late trades (arrived after their
  bucket has already closed) are *dropped*, not back-filled (Spec
  §14.2: silent rewrites are forbidden); the
  `dropped_late_trades` counter exposes the count for monitoring.
  Multi-minute gaps between trades are filled with **flat synthetic
  bars** so ATR sees no missing slots.

- **`app/market_data/cvd.py`** - pure CVD calculator
  (`signed_volume`, `compute_cvd`). Honours Binance's
  `is_buyer_maker=True` convention as "the aggressor was a seller";
  falls back to `RecentTrade.side` when the flag is unset (mock
  fixtures).

- **`app/market_data/atr.py`** - SMA-of-True-Range over closed
  bars. Returns `None` for fewer than two closed bars. Wilder-style
  EMA smoothing is deliberately deferred to Issue #6 / #7 - SMA is
  enough for Phase 4's data-quality role and trivially deterministic
  under replay.

- **`app/market_data/oi.py`** + **`app/market_data/funding.py`** -
  `OpenInterestSnapshotState` and `FundingSnapshotState` keep the
  latest plus previous snapshot per symbol. Out-of-order updates are
  rejected. Cross-symbol updates raise `ValueError`. `delta()` and
  `percent_change()` handle the zero-baseline case explicitly.

- **`app/market_data/liquidation.py`** - bounded
  `LiquidationFeedState` deque per symbol; FIFO eviction with a
  configurable capacity. Phase 4 ships only the data structure and a
  `LiquidationEvent` shape - there is no `get_liquidations` method
  on the gateway, no real-time feed, no auto-subscribe.

- **`app/market_data/buffer.py` - `MarketDataBuffer`**:
  - Lazy per-symbol state via `track(symbol)` or auto-creation on
    first ingest.
  - Rolling trade windows for **1m / 5m / 15m**, anchored to the
    *latest observed timestamp across all surfaces* so the buffer
    is fully deterministic under replay (Spec §14, Issue #4
    "necessary support" list).
  - 1m and 5m candle builders fed by every ingested trade.
  - Latest order book per symbol with reliability tier carried.
  - Latest / previous funding rate and open interest.
  - Bounded liquidation history.
  - **`is_degraded(symbol)` and `degraded_reasons(symbol)`** for the
    future No-Trade Gate (Issue #7) and Reconciliation loop
    (Issue #9). Spec §14.2 + §31: untrustworthy data must NOT feed
    new openings.
  - **`snapshot(symbol)`** returns a Spec §11.1 `MarketSnapshot`
    populated with `last_price`, `bid`, `ask`, `spread_pct`,
    `volume_1m`, `volume_5m`, `cvd_1m`, `cvd_5m`, `atr_1m`,
    `atr_5m`, `oi`, `funding_rate`, `orderbook_depth_usdt`. Emits a
    `MARKET_SNAPSHOT` event when an `EventRepository` is wired in.
  - **`cvd_15m(symbol)`** for the 15-minute window required by
    Issue #4.
  - **REST vs WS conflict detection** (Spec §14.2): when an
    incoming order book has a different `DataReliability` tier than
    the existing one, the buffer emits a single
    `DATA_UNRELIABLE` event tagged
    `MarketDataDegradedReason.REST_WS_CONFLICT` with the previous
    and incoming tiers in the payload, AND keeps the strong-tier
    book on a tier downgrade. A tier upgrade (e.g. REST -> WS) is
    accepted but still counted; the audit trail captures both.
  - **`on_websocket_disconnect(reason=...)`** - marks every tracked
    symbol as `EXCHANGE_DISCONNECTED` and writes one batched
    `DATA_UNRELIABLE` event with `scope=all_symbols`,
    `trigger=websocket_disconnect`, and the full symbol list.
    Issue #4 acceptance criterion 4.
  - **`on_websocket_reconnect(reason=...)`** - clears the explicit
    disconnect / degraded reasons (stale-window reasons are
    recomputed and may legitimately stay set until fresh data
    arrives).
  - **Exchange-link health propagation**: when wired to an
    `ExchangeClientBase`, the gateway's
    `ExchangeConnectionState.{DISCONNECTED, DEGRADED, UNINITIALISED}`
    automatically maps to the corresponding degraded reason on every
    symbol view.
  - **`mark_degraded` / `clear_explicit_degraded`** for manual
    test-driven and Reconciliation-driven transitions.
  - **`refresh_from_exchange(symbol)`** - convenience helper that
    pulls trades, book, funding and OI from the attached client and
    feeds them through the ingest path. **Phase 4 only ever wires a
    `MockExchangeClient`** here; if a `BinanceClient` skeleton ever
    gets wired in, the call surfaces the underlying
    `NotImplementedError` instead of pretending it has data
    (asserted by
    `test_refresh_from_exchange_propagates_notimplementederror_from_binance`).
    The helper batches its emits so a fresh refresh produces at most
    one `DATA_UNRELIABLE` event per symbol regardless of how many
    surfaces it touched.

- **Boot path additions** in `python -m app.main`:
  - `_build_phase4_boot_seed()` constructs a deterministic
    in-process tape anchored at `now_ms()` so the buffer's
    staleness gate sees a fresh window. **No fixture file is read,
    no network call is made, no credential is consumed.**
  - `MarketDataBuffer` is instantiated, every symbol the mock
    exposes is `track`-ed, `refresh_from_exchange`-ed, and
    `snapshot`-ed.
  - One WS disconnect + reconnect probe is driven through the
    buffer so the audit trail at boot includes one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`
    and one recovery.
  - A `market_data_buffer` health probe is registered that goes
    `DEGRADED` if any symbol is degraded.
  - Banner extended with three Phase 4 fields:
    - `market_data=<tracked>/<degraded>`
    - `market_snapshots=<count>`
    - `data_unreliable=<count>`

  Sample boot output:

  ```
  [AMA-RT] Phase 4 - Market Data Buffer v1.4.0a4 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=9 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

- **76 new unit tests**:
  - `tests/unit/test_market_data_models.py` (8) - `Bar` /
    `LiquidationEvent` shape, `BarInterval` widths,
    `MarketDataBufferConfig` defaults, frozen-ness, degraded-reason
    vocabulary.
  - `tests/unit/test_market_data_candles.py` (12) - bucket
    alignment, first-trade live bar, in-place updates, bar
    closing, multi-minute gap filling with flat bars, late-trade
    drop, buy/sell volume split (both `is_buyer_maker` and `side`
    fallback), `force_close` padding, history bound, cross-symbol
    rejection.
  - `tests/unit/test_market_data_cvd.py` (7) - `signed_volume`
    sign, `compute_cvd` empty / pure-buy / pure-sell / mixed,
    Issue #4 acceptance criterion 1.
  - `tests/unit/test_market_data_atr.py` (8) - True Range with /
    without prev close, `compute_atr` `None` cases, simple-average
    correctness, prev-close from history when window is smaller
    than history, unclosed-bar exclusion, Issue #4 acceptance
    criterion 2.
  - `tests/unit/test_market_data_oi_funding_liquidation.py` (12) -
    initial state, advance-on-update, out-of-order rejection,
    cross-symbol rejection, zero-baseline percent change,
    capacity eviction, recent-since-ts filter.
  - `tests/unit/test_market_data_buffer.py` (25) - lazy track,
    never-initialised symbol, rolling-window math, MarketSnapshot
    Spec §11.1 fields, CVD helpers match `compute_cvd`,
    Issue #4 acceptance criterion 3 (no data -> degraded; partial
    data -> stale; fresh data -> clean), live recomputation of
    staleness, Issue #4 acceptance criterion 4 (WS disconnect ->
    DATA_UNRELIABLE), reconnect clears explicit reasons,
    `mark_degraded` / `clear_explicit_degraded` semantics, REST vs
    WS conflict in both directions plus same-tier-newer-wins,
    exchange health propagation (DISCONNECTED, DEGRADED), per-symbol
    liquidation deque, stats consistency, `refresh_from_exchange`
    requires a client, `BinanceClient` skeleton surfaces
    `NotImplementedError`, disconnected-client short-circuit,
    constructor refuses an `api_key` parameter, `BinanceClient`
    still refuses credentials at construction.
  - `tests/unit/test_phase4_no_network.py` (4) - `app/market_data/`
    imports no network library, mentions no `api_key` /
    `api_secret`, never creates `market.db`, and
    `BinanceClient.get_account_snapshot` continues to raise
    `NotImplementedError` with messages that mention "skeleton",
    "phase 4" and "api key".
  - `tests/unit/test_main_entrypoint.py` extended (1 test, now
    Phase 4-aware) - banner contains `Phase 4 - Market Data
    Buffer`, `market_data=...`, `market_snapshots=...`,
    `data_unreliable=...`, and the events DB contains at least one
    `MARKET_SNAPSHOT` event plus one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 4 - Market Data
  Buffer`; `__version__` is `1.4.0a4`.
- `app/main.py` - new `_build_phase4_boot_seed()` helper, boot path
  drives the buffer through one full ingest + snapshot + WS
  disconnect / reconnect cycle. The Phase 1
  `_assert_phase1_safety()` and Phase 3 `_assert_phase3_read_only()`
  guards are unchanged. `STATE_TRANSITION` reason updated to
  `phase4_boot`. Exchange shutdown reason updated to
  `phase4_shutdown`.

#### Phase 4 boundary (declared explicitly to avoid drift)

This PR observes the boundary set by Issue #4 and the user-facing
review of PR #14:

1. **Market Data Buffer ONLY.** No Regime / Universe / Liquidity
   engine, no Scanner, no Confirmation, no Manipulation Detector.
2. The buffer is fed by `MockExchangeClient` / fixture data **by
   default**. The boot path uses the deterministic mock; tests use
   deterministic fixtures.
3. **No real Binance WebSocket and no real REST.** `BinanceClient`
   continues to raise `NotImplementedError` for every read method.
4. **No API key.** `BinanceClient.__init__` still refuses any
   credential. `MarketDataBuffer.__init__` exposes no `api_key`
   parameter (asserted by a test that passes the kwarg and expects
   a `TypeError`).
5. **No write surface.** The four `SafeModeViolation` refusals on
   `ExchangeClientBase` (`create_order`, `cancel_order`,
   `set_leverage`, `set_margin_mode`) are unchanged.
6. **No auto-connect.** `MarketDataBuffer` opens no socket; it only
   receives data via `ingest_*` calls or via
   `refresh_from_exchange` against a deterministic
   `MockExchangeClient`.
7. **Tests do not depend on real network.** Both
   `test_phase3_no_network.py` and the new
   `test_phase4_no_network.py` enforce this.
8. **`BinanceClient.get_account_snapshot` remains mock-only /
   skeleton-only in both Phase 3 and Phase 4.** Real account
   snapshots require an authenticated REST call and an API key,
   forbidden until the limited-live phase. Locked by
   `test_binance_client_get_account_snapshot_remains_skeleton` in
   `test_phase4_no_network.py`.

#### Not in Phase 4 (deferred)
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine (will read `is_degraded` from this
  buffer to drive the No-Trade Gate).
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a
  real `create_order` is *allowed* to exist, behind the Risk
  Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports,
  Reflection.

#### Live trading risk
**None.** Phase 4 ships only an in-process buffer and a
deterministic boot drill. No exchange SDK is added. No outbound
HTTP / WebSocket library is imported. No API key is read. No
write surface is added. The Phase 1 safety lock and Phase 3
read-only invariant are unchanged. Six layers of defence (config
lock, Phase 1 boot assertion, Phase 3 read-only assertion, Risk
Engine refusal, base-class write-surface refusal, Phase 4
no-network / no-api-key tests) are all unit-tested.

### Phase 3 - Review fixes (Issue #3 review feedback)

#### Changed

- **Reliability tier alignment** (review item 1). The default
  `OrderBook.reliability` was tier B; this was inconsistent with
  the rest of the PR description and with the actual Phase 4+ source
  (a WS-maintained depth-diff book is tier A). Updated:
  - `app/exchanges/base.ExchangeClientBase.reliability_tiers` now
    returns `get_orderbook -> A` (was B). The full table is now
    locked: `get_recent_trades=A`, `get_orderbook=A`,
    `get_funding_rate=B`, `get_open_interest=B`, `get_symbols=B`,
    `get_account_snapshot=B`.
  - `app/exchanges/models.OrderBook.reliability` default raised from
    `DataReliability.B` to `DataReliability.A`. Adapters that fall
    back to a REST snapshot when the WS link is degraded must tag
    that response tier B explicitly.
  - `MockExchangeClient.get_orderbook` now stamps its synthetic book
    as tier A (it is the in-memory analogue of a WS-maintained book).
    A tier-B `OrderBook` supplied via `MockExchangeSeed.orderbooks`
    is preserved as-is - the mock does not silently upgrade it.
  - 4 new tests pin the new contract:
    `test_reliability_tiers_contract` (full-table assertion),
    `test_reliability_tiers_lists_all_six_read_methods`,
    `test_orderbook_default_reliability_is_a_at_model_level`,
    `test_orderbook_can_be_tagged_tier_b_for_rest_fallback`,
    `test_mock_synthetic_orderbook_is_tier_a`,
    `test_mock_can_serve_a_tier_b_seed_orderbook`.
- **Phase 4 constraint hardened** (review item 2). The Phase 4
  recommendation in the PR description and the
  `BinanceClient.get_*` `NotImplementedError` messages are reworded:
  Phase 4 (Market Data Buffer) must drive the buffer from
  `MockExchangeClient` / fixture data **by default**; any real public
  read-only WS / REST adapter must be opt-in (off by default),
  require no API key, expose no write surface, and not auto-connect
  to the real exchange. `WebSocketManager`'s docstring is reworded
  for the same reason - it no longer claims Phase 4 will adopt any
  particular network library. New test
  `test_binance_real_market_data_methods_message_is_explicit_about_phase4_constraints`
  asserts every public-data `NotImplementedError` message contains
  the four constraint phrases ("opt-in", "off by default", "no API
  key", "no write surface", "auto-connect").
- **`get_account_snapshot` mock-only / skeleton-only** (review item
  3). The `BinanceClient.get_account_snapshot` `NotImplementedError`
  message is rewritten to say explicitly: real account snapshots
  require authentication and an API key, both of which are forbidden
  until the limited-live phase; the only working implementation is
  `MockExchangeClient.get_account_snapshot`. New test
  `test_binance_get_account_snapshot_message_is_explicit_about_no_api_key`
  asserts the message contains "api key", "authenticated",
  "mockexchangeclient", and "limited-live".
- **README** updated with an explicit "Reliability tier contract"
  table and a "Phase 4 constraints" section that declares the four
  Phase 4 invariants up-front so the next PR cannot drift.

#### Tests
**+7 review-fix tests on top of 97 Phase 3 tests = 104 Phase 3 tests
total. Full suite: 211 passed in 1.87s** (107 retained from
Phase 1 / 2 + 104 Phase 3).

#### Live trading risk
None. The review fixes only adjust default reliability tiers,
strengthen `NotImplementedError` messages, and tighten Phase 4
constraint documentation. No new mode flag, no loosened safety lock,
no new dependency, no new write surface.

### Phase 3 - Exchange Gateway Read-Only

#### Added
- **`app/exchanges/` package** introducing the read-only Exchange Gateway
  abstraction. The package never imports an exchange SDK and never opens
  an outbound socket; this is asserted by
  `tests/unit/test_phase3_no_network.py`.
- **`ExchangeClientBase` abstract class** (`app/exchanges/base.py`):
  - 6 abstract read-only methods: `get_symbols`, `get_orderbook`,
    `get_recent_trades`, `get_funding_rate`, `get_open_interest`,
    `get_account_snapshot`.
  - 4 **concrete** write surfaces (`create_order`, `cancel_order`,
    `set_leverage`, `set_margin_mode`) that **always** raise
    `SafeModeViolation`. Subclasses inherit the refusal.
  - `ExchangeHealth` value-object with state transitions
    (`UNINITIALISED -> CONNECTED -> DEGRADED / RECONNECTING /
    DISCONNECTED`), counters and an `is_data_trustworthy()` predicate.
  - `WebSocketManager` skeleton (`connect / disconnect / subscribe /
    unsubscribe`) that emits `DATA_UNRELIABLE` with the pending
    subscription set on every drop. **No real socket is opened in
    Phase 3.**
  - Health transitions emit `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `EXCHANGE_DEGRADED` events through
    `EventRepository`.
  - `_require_trustworthy(surface=...)` helper raises
    `ExchangeConnectionError` whenever the link is not `CONNECTED`
    (Spec §14.2 + §31).
  - `READ_ONLY_METHODS` and `WRITE_SURFACE_METHODS` module-level
    tuples used by the entrypoint and the test suite to assert the
    Phase 3 contract.
  - `assert_read_only()` boot-time guard.
  - `reliability_tiers` static map documenting the default
    `DataReliability` tier each surface returns (Spec §13.3).
- **`BinanceClient` skeleton** (`app/exchanges/binance.py`):
  - All 6 read methods raise `NotImplementedError` pointing at the
    later phase that owns the real adapter (Phase 4 / 8 / 9).
  - All 4 write methods inherit `SafeModeViolation` from the base
    class (asserted by tests; the skeleton must NOT override them).
  - Constructor refuses any `api_key` / `api_secret` (Spec §37 anti-leak).
- **`MockExchangeClient`** (`app/exchanges/mock.py`):
  - Deterministic in-memory implementation used by the entrypoint and
    the test suite. **No network**.
  - Optional `MockExchangeSeed` for fully predictable test fixtures.
  - `simulate_disconnect` / `simulate_reconnect` /
    `simulate_degraded` test hooks drive the No-Trade Gate paths.
  - Tier-A surfaces refuse when not `CONNECTED`; tier-B REST surfaces
    (`get_symbols`, `get_account_snapshot`) remain usable when
    `DEGRADED` per Spec §13.3.
- **Read-only data models** (`app/exchanges/models.py`): Pydantic v2
  frozen models `ExchangeSymbol`, `OrderBook` (+ `OrderBookLevel`,
  with bid/ask sort validation), `RecentTrade`, `FundingRate`,
  `OpenInterest`, `AccountSnapshot`. Each carries an explicit
  `reliability: DataReliability` field with the default tier per
  surface.
- **New core vocabulary**:
  - `app/core/enums.ExchangeConnectionState` enum (`UNINITIALISED /
    CONNECTED / DEGRADED / RECONNECTING / DISCONNECTED`) with an
    `is_trustworthy` property.
  - `app/core/enums.DataReliability.is_at_least()` helper for
    consistent tier comparisons (Spec §13.3).
  - `app/core/events.EventType.{EXCHANGE_CONNECTED,
    EXCHANGE_DISCONNECTED, EXCHANGE_DEGRADED}`. `DATA_UNRELIABLE` was
    already declared in Phase 1.
  - `app/core/errors.SafeModeViolation` (subclass of
    `SafetyViolation`).
  - `app/core/errors.ExchangeError` and
    `app/core/errors.ExchangeConnectionError`.
- **Phase 3 boot self-check** in `python -m app.main`:
  - Instantiates `MockExchangeClient(event_repo=repo, autostart=True)`,
    runs `assert_read_only()`, **probes every banned write surface**
    and refuses to start unless each one raises `SafeModeViolation`.
  - Calls `get_symbols()` to prove the read path works.
  - Registers an `exchange_link` health probe.
  - Emits `EXCHANGE_CONNECTED` on start and
    `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE` on shutdown so
    replay-based tests can confirm the lifecycle closed.
  - Status banner now reports
    `exchange=<name>/<state> exchange_symbols=N exchange_connected_events=1`.
- **97 new unit tests**:
  - `tests/unit/test_exchange_models.py` (15) - `DataReliability`
    ordering (A>B>C>D), `is_at_least` helper,
    `ExchangeConnectionState.is_trustworthy`, `OrderBook` sort
    validation, frozen models, default reliability tiers per model.
  - `tests/unit/test_exchange_base.py` (20) - cannot instantiate the
    ABC directly; `READ_ONLY_METHODS == __abstractmethods__`; write
    surfaces are concrete on the base class; `SafeModeViolation`
    IS-A `SafetyViolation`; `ExchangeError` IS-A `AMARTError` and is
    NOT a `SafetyViolation`; `assert_read_only` refuses when
    `_live_orders_enabled=True`; `WebSocketManager` connect /
    disconnect lifecycle and the `DATA_UNRELIABLE` event payload;
    `ExchangeHealth` counters; `start` / `stop` / `_mark_degraded`
    emit the matching events through `EventRepository`;
    `_require_trustworthy` refuses when uninitialised / disconnected;
    `reliability_tiers` contract; no network library imports.
  - `tests/unit/test_binance_client.py` (20) - `name='binance'`;
    refuses any `api_key` / `api_secret`; every read method raises
    `NotImplementedError`; every write surface refuses with
    `SafeModeViolation`; every read method is overridden on
    `BinanceClient` itself; write surfaces NOT overridden (inherit
    base refusal); module imports no network library.
  - `tests/unit/test_mock_exchange_client.py` (28) - `autostart`
    emits `EXCHANGE_CONNECTED`; default seed has BTCUSDT, ETHUSDT,
    PEPEUSDT; orderbook / trades / funding / OI / account read
    paths; `MockExchangeSeed` determinism; `simulate_disconnect`
    emits `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE`; tier-A
    surfaces refused when `DEGRADED`; tier-B surfaces (symbols,
    account_snapshot) ALLOWED when `DEGRADED`; both refused when
    `DISCONNECTED`; `simulate_reconnect` restores trust + new
    `EXCHANGE_CONNECTED`; write surfaces refuse; mock does NOT
    override write surfaces; lifecycle smoke; no network library
    imports.
  - `tests/unit/test_phase3_no_network.py` (3) - `requirements.txt`
    and `pyproject.toml` contain no exchange SDK / HTTP client; no
    file under `app/` issues an `import` for any forbidden token.
  - Existing `tests/unit/test_main_entrypoint.py` extended to assert
    the Phase 3 banner fields and the new `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `DATA_UNRELIABLE` events.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 3 - Exchange Gateway
  Read-Only`; `__version__` is `1.4.0a3`.
- `app/main.py` - new `_assert_phase3_read_only(client)` guard that
  probes every entry in `WRITE_SURFACE_METHODS` and raises
  `SafeModeViolation` if any of them stops refusing. The existing
  `_assert_phase1_safety()` check is unchanged. Banner extended with
  `exchange=<name>/<state>`, `exchange_symbols=N`,
  `exchange_connected_events=1`. `STATE_TRANSITION` reason updated to
  `phase3_boot`. The exchange is stopped cleanly on shutdown
  (`reason="phase3_shutdown"`), which emits `DATA_UNRELIABLE` +
  `EXCHANGE_DISCONNECTED`.

#### Not in Phase 3 (deferred)
- Issue #4 - real Market Data Buffer; `BinanceClient` read methods
  remain `NotImplementedError` until then.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine.
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a real
  `create_order` is *allowed* to exist, behind the Risk Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection.

#### Live trading risk
**None.** Phase 3 ships only an abstract read-only gateway plus a
deterministic in-memory mock. The four write surfaces always raise
`SafeModeViolation`; the Phase 1 safety lock is unchanged; no exchange
SDK / HTTP / WebSocket library is installed; no real API key is
accepted by `BinanceClient`. Five layers of defence (config lock, boot
assertion, Phase 3 read-only assertion, Risk Engine refusal, base-class
write-surface refusal) are all unit-tested.

### Phase 2 - Event Sourcing and Database

#### Added
- **Five SQLite databases** (Spec §33.1) opened in WAL mode and migrated
  by an idempotent runner: `events.db`, `trades.db`, `positions.db`,
  `capital.db`, `incidents.db`.
- **New schema files** under `app/database/schemas/`:
  - `trades.sql` - fills (write-once); writers land in Issue #9.
  - `positions.sql` - position lifecycle; writers land in Issues #7/#9.
  - `capital.sql` - `capital_snapshots` (Issue #8) and
    `capital_events_index` (mirror written by Phase 2 EventRepository).
  - `incidents.sql` - `incidents` + `incident_log`; writers land in
    Issues #9/#10.
- **`events.db` schema upgrade**: added the `created_at` column required
  by the Issue #2 field contract; added composite indexes
  `(event_type, timestamp)` and `(symbol, timestamp)` and an
  `order_id` index. The migration auto-upgrades a Phase 1 events.db by
  adding the column and backfilling from `timestamp`.
- **`app/database/connection.DatabaseSet`** - container that opens /
  closes a known set of databases atomically, with typed accessors
  (`.events`, `.trades`, `.positions`, `.capital`, `.incidents`),
  `__iter__`, idempotent `close()`, and an `open_database_set()` context
  manager.
- **`app/database/migrations.migrate_database` and
  `migrate_database_set`** - apply each database's schema; idempotent.
- **`EventRepository` Phase 2 API**:
  - `append_event` / `append_many` (returns events with `created_at`
    populated)
  - `list_events` / `replay_events` (lazy iterator) / `count_events`
  - filters: `event_type`, `event_types` (iterable), `symbol`,
    `source_module`, `position_id`, `order_id`, `since_ts`, `until_ts`,
    `limit`, `offset`
  - persistence failures logged via `loguru` and raised as
    `EventPersistenceError` (no silent loss). Includes a `failed_appends`
    counter for monitoring.
  - capital event helpers: `record_capital_deposit`,
    `record_capital_withdrawal`, `record_profit_harvest`,
    `record_capital_rebase`, `record_risk_budget_recalculated`.
  - **cross-database write**: when constructed with a `capital_conn`
    every `CAPITAL_*` event is mirrored into
    `capital.db.capital_events_index` so Issue #8 has a fast lookup
    table. Mirror failures are logged but do NOT roll back the events
    write (the index is rebuildable from events.db).
- **Phase 1 method aliases preserved** on `EventRepository` (`append`,
  `list`, `replay`, `count`) so the Risk Engine, Telegram bot and
  Execution FSM skeletons keep working unchanged.
- **`scripts/init_db.py`** rewritten to migrate all five databases and
  print each db's journal mode + schema file. Still idempotent.
- **`app/main.py`** opens & migrates all five databases, emits a
  CAPITAL_DEPOSIT marker (paper-mode bookkeeping, amount=0.0) so the
  capital_events_index path is exercised end-to-end. The Phase 1 safety
  lock and `_assert_phase1_safety()` remain unchanged.
- **`app/core/errors.EventPersistenceError`** - typed exception for the
  persistence failure path.
- **`app/core/events.Event.created_at`** - new field; `None` for
  in-memory events, populated by `EventRepository` from the SQLite
  default expression on insert.
- **51 new unit tests**:
  - `tests/unit/test_database_set.py` (12) - DatabaseSet, WAL pragma,
    multi-db migration, Phase-1 -> Phase-2 events.db upgrade.
  - `tests/unit/test_phase2_schemas.py` (8) - column contract for
    trades / positions / capital / incidents tables, event-type
    vocabulary, "no leak from Issue #3/#9/#10" check.
  - `tests/unit/test_event_repository.py` rewritten (31) - full Phase 2
    API surface, filter combinations, persistence failure path, capital
    helpers, capital_events_index mirror.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 2 - Event Sourcing and
  Database`; `__version__` is `1.4.0a2`.
- `tests/conftest.py` - new `phase2_dbs` and `events_repo_with_capital`
  fixtures.

#### Not in Phase 2 (deferred)
- Issue #3 - Exchange Gateway (read-only).
- Issue #4 - Market Data Buffer.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine; uses positions.db.
- Issue #8 - Capital Flow Engine; uses capital_snapshots and the
  capital_events_index table this PR ships.
- Issue #9 - full Execution FSM + Reconciliation; uses trades.db and
  incidents.db.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection;
  uses the incidents tables this PR ships.

#### Live trading risk
None. Phase 2 only adds passive SQLite schemas, a connection helper,
the EventRepository extension and tests. No exchange SDK, no outbound
network, no LLM, no Telegram client. Phase 1 safety lock unchanged.

### Phase 1 - Safety Foundation

#### Added
- Project skeleton under `app/`, `tests/`, `scripts/`, `data/`, `docs/`.
- `pyproject.toml` and `requirements.txt` with a minimal dependency set
  (Pydantic, pydantic-settings, PyYAML, loguru, pytest). No exchange SDK,
  no LLM client, no Telegram client.
- Configuration system (`app/config/`) with `defaults.yaml`, `risk.yaml`,
  `strategy.yaml`, validated by Pydantic schemas in `schema.py`. Loader in
  `settings.py` applies a Phase 1 safety lock that hard-codes:
  `trading_mode=paper`, `live_trading_enabled=false`,
  `right_tail_enabled=false`, `llm_enabled=false`,
  `exchange_live_order_enabled=false`. Even malicious env vars cannot
  flip these flags.
- Core domain types: `app/core/enums.py`, `app/core/events.py`,
  `app/core/models.py`, `app/core/clock.py`, `app/core/errors.py`,
  `app/core/constants.py`. Mirrors Spec §11 / §46 / §12.
- SQLite Event Sourcing substrate: `app/database/schema.sql`,
  `connection.py`, `migrations.py`, `repositories.EventRepository`
  (append, append_many, list, replay, count). WAL mode enforced.
- Init script `scripts/init_db.py`.
- Skeletons (no live behaviour):
  - `app/risk/engine.RiskEngine` - rejects any live or right-tail action.
  - `app/execution/fsm.ExecutionFSM` - typed transition table; refuses
    `request_send_order` without a Risk Engine approval.
  - `app/telegram/bot.TelegramCommandCenter` - in-process command bus,
    audit-logs every command, requires confirmation for `/resume`.
  - `app/monitoring/{metrics,health,alerts}.py` - in-memory only.
- Entrypoint `python -m app.main` - asserts the safety lock, initialises
  the events database, drives one Risk Engine self-check + one Telegram
  `/status` audit event, prints a one-line status banner, exits 0.
- Pytest suite covering enums, models, settings safety lock, event
  repository, Risk Engine, Execution FSM, Telegram bus, monitoring, the
  init script, and the entrypoint smoke test.
- `.env.example` (no real keys), `.gitignore` (excludes `.env`,
  `data/sqlite/*`, `*.db`), `docs/CHANGELOG.md`.
- `README.md` re-written to describe Phase 1 scope, paper-mode default,
  and explicit "no live trading" guarantee.

#### Not in Phase 1 (deferred to later issues)
- Issue #2: full Event Sourcing schema for trades / positions / capital /
  incidents databases, replay across multiple databases.
- Issue #3: any Exchange Gateway code, even read-only.
- Issue #4: Market Data Buffer.
- Issue #5: Regime / Universe / Liquidity engines.
- Issue #6: Pre-anomaly / Anomaly / Confirmation / Manipulation scanners.
- Issue #7: full Risk Engine (No-Trade Gate, Account Life Tier,
  circuit breakers).
- Issue #8: Capital Flow Engine (rebase, harvest).
- Issue #9: full Execution FSM with reconciliation against an exchange.
- Issue #10: LLM Interpreter, Telegram outbound, Replay diff reports,
  Reflection.
