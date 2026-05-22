# Phase 11C.1C-B - Adaptive Candidate Runtime Calibration & Early Tail Discovery v0

> **Status: ACCEPTED (closed 2026-05-22; PR #38 merged into
> `main`, mergeCommit `ce4b6de`).** PR #38 has been merged into
> `main`; the 30s dry-run + 5min real public WS smoke evidence
> recorded under `docs/PHASE_GATE.md` §"Phase 11C.1C-B
> acceptance evidence (closeout)" was accepted; Phase 11C.1C-B
> is therefore **ACCEPTED**. The contract below describes the
> **paper-only first version** that shipped via PR #38. Phase
> 11C.1C-A is **ACCEPTED** (closed 2026-05-22; PR #36 merged;
> PR #37 docs closeout). Phase 11C.1C-C (Adaptive Candidate
> Strategy Validation, Cluster Exposure Control & full MFE/MAE
> Processor) is **NEXT_ALLOWED / NOT_STARTED**. Phase 12 (real
> money / live trading) remains **FORBIDDEN**.
>
> **Phase 11C.1C-B acceptance does NOT authorise live trading,
> API keys, private endpoints, DeepSeek trade decisions, real
> Telegram outbound, or Phase 12.**

This document describes the **first version** of the Adaptive
Candidate Runtime Calibration & Early Tail Discovery layer that
ships in Phase 11C.1C-B. It builds on the Phase 11C.1C-A contracts
(`AdaptiveCandidateContext`, the six adaptive event types,
`MarketRegimeAssessment` / `CandidateStageAssessment` /
`OpportunityScore` / `StrategyModeDecision` / `ClusterContext` /
`LabelQueueContract`) and **calibrates** them against the real
WS-radar candidate stream so the system discovers demon coins
(妖币) earlier while refusing to chase late / blowoff tails.

Phase 11C.1C-B is **paper-mode only**. It does NOT introduce any
new trade authority; the Risk Engine remains the single
trade-decision gate, every Phase 1 safety flag stays `False`,
and Phase 12 (live trading) remains FORBIDDEN.

## Phase 11C.1C-B boundary (must hold for the entire scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Strategy mode                               | paper / virtual; not a real-trade authority |
| `early_tail_score`                          | descriptive only; protects the candidate from capacity eviction. Does NOT authorise an order. |
| Late / blowoff candidates                   | observe-only; NEVER follow / pullback |
| MFE/MAE processor                           | NOT implemented (queue is a contract) |
| AI Learning                                 | NOT implemented              |
| Phase 12                                    | FORBIDDEN                    |

## What ships in Phase 11C.1C-B

### 1. `RuntimeCalibrationMetrics` value object

A new frozen Pydantic v2 model in
`app/adaptive/models.py` carries the brief-mandated fifteen
fields:

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

The block is attached to every `AdaptiveCandidateContext`
(under the new `runtime_calibration` field) and rides into the
Phase 8.5 `learning_ready.adaptive_candidate.runtime_calibration`
sub-block on every event the WS-radar chain emits, so Phase 8.5
export, Phase 10A replay, and the daily report all pick it up
without schema gymnastics.

### 2. `app/adaptive/runtime.py` - pure-function helpers

  - `compute_runtime_calibration(...)` - top-level builder; takes
    raw runtime inputs (first-seen ts/price, current ts/price,
    price + quote-volume rolling history, current rank + 5m-old
    rank, candidate stage, blowoff risk) and returns the
    populated `RuntimeCalibrationMetrics`.
  - `compute_early_tail_score(...)` - additive 0..100 score
    derived from `volume_rank_jump_5m` + quote-volume / price
    accelerations + freshness, gated by stage and capped by
    distance from first-seen so a candidate that already ran 30%+
    above admission cannot accidentally re-qualify as "early".
  - `compute_late_chase_risk_score(...)` - 0..100 risk score
    that rises with distance from first-seen, proximity to 24h
    high, and lost freshness; clamped high for `late` /
    `blowoff` and clamped low for `dumped`.
  - `compute_freshness_score(...)` - simple
    `half_life / (half_life + elapsed)` decay, default
    half-life 5 minutes.
  - `compute_relative_acceleration(...)` - rolling-history
    helper used by both the price- and quote-volume- accelerator
    fields.

All functions are pure (no I/O, no global state); the source-tree
audit in `tests/unit/test_phase11c_1c_a_adaptive_candidate.py
::test_adaptive_module_does_not_import_third_party_network_libs`
already covers the new module.

### 3. `Candidate` baselines + per-symbol rolling history

`app/market_data_public/candidate_pool.py`:

  - **Stable baselines** recorded ONCE at admission:
    `first_seen_price`, `quote_volume_first_seen`,
    `volume_rank_first_seen`. These never get overwritten on
    subsequent `offer()` updates so the runtime calibration block
    can diff the current snapshot against a stable reference.
  - **Rolling histories** (`price_history`,
    `quote_volume_history`, `volume_rank_history`, oldest -> newest)
    capped at
    `CandidatePoolConfig.per_symbol_history_max_samples` (200) and
    trimmed to the last 10 minutes so 1m / 5m accelerations have
    real samples to chew on.
  - **Runtime-layer scores** (`early_tail_score`,
    `late_chase_risk_score`, `freshness_score`,
    `promoted_before_24h_top_move`) written back by the
    WS-radar chain driver via the new
    `CandidatePool.update_runtime_metrics(...)` method.

### 4. Early Tail Discovery v0 - capacity-protection invariant

`CandidatePool._enforce_capacity` now sorts candidates by a
two-tier eviction key so the brief's
"不因为候选池 capacity evict 而丢失高 early_tail_score 候选"
invariant holds:

```
evict_key = (
    1 if early_tail_score >= early_tail_protect_threshold else 0,
    early_tail_score,
    radar_score,
    last_seen_ms,
)
```

UNPROTECTED candidates (early-tail score below the threshold) get
evicted first. PROTECTED candidates (early-tail score above the
threshold) get evicted only if every unprotected candidate has
already been removed - and even then the lowest early-tail score
goes first. The default threshold lives in
`DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD = 60.0`.

### 5. WS-radar chain integration

`WSRadarChainDriver` (`app/market_data_public/ws_radar_chain.py`):

  - Now accepts an optional `candidate_pool=` handle so the
    driver can write runtime metrics back onto the candidate
    after every chain pass.
  - Reads `candidate.first_seen_price` (the stable admission
    baseline) instead of the previous "approximate via
    snapshot" path.
  - Threads `candidate.price_history` /
    `candidate.quote_volume_history` /
    `pool.volume_rank_5m_ago(candidate)` into
    `compute_runtime_calibration`.
  - Tracks per-run aggregates surfaced by
    `adaptive_metrics_payload`:
      - `top_early_tail_candidates` (chain-side; capped at 10)
      - `top_late_chase_risk_candidates` (chain-side; capped at 10)
      - `early_tail_score_top_symbols` (alias kept for the
        brief-mandated daily-report field name)
      - `opportunity_score_distribution` (10-point bins:
        `0-10` ... `90-100`)
      - `symbols_promoted_before_24h_top_move`
      - `eden_alt_near_examples` - candidate symbols whose
        upper-cased name starts with `EDEN`, `ALT`, or `NEAR` and
        whose `early_tail_score > 0`. Surfaces the brief's
        "EDEN/ALT/NEAR style candidate examples if present".

### 6. Daily report enhancement

`DailyReportSnapshot` + the Markdown body (`app/paper_run/daily_report.py`)
now carry the new fields:

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

### 7. Tests

`tests/unit/test_phase11c_1c_b_runtime_calibration.py` pins every
behaviour the brief calls out:

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
regression. The full `tests/` surface goes from 2219 -> 2231
passing tests (the +12 are this PR's brief-mandated tests).

## Phase 11C.1C-B explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position / leverage
    / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` / `/userDataStream`
    path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Promoting `early_tail_score` / `strategy_mode` to a real-trade
    authority.
  - Enabling AI Learning that auto-decides trades.
  - Implementing the full MFE/MAE processor (the queue stays a
    descriptive contract; the processor is reserved for a later
    PR).
  - Issuing any real order.
  - Entering Phase 12.

## Smoke evidence

```
pytest tests/                    2231 PASS  (2219 baseline + 12 new)
pytest tests/ -k phase11c        272 PASS

30 s dry-run smoke
  command:                       python -m scripts.run_public_market_paper \
                                   --duration 30s --symbol-limit 3 --dry-run \
                                   --poll-interval-seconds 1
  banner phase tag               Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
  dry_run                        True
  duration_seconds               30
  iterations                     30
  ws_chains_emitted              60
  MARKET_REGIME_ASSESSED         60
  CANDIDATE_STAGE_CLASSIFIED     60
  OPPORTUNITY_SCORED             60
  STRATEGY_MODE_SELECTED         60
  CLUSTER_CONTEXT_ATTACHED       60
  LABEL_QUEUE_ENQUEUED           60
  daily report                   contains "## Phase 11C.1C-B Adaptive
                                 Candidate Runtime Calibration &
                                 Early Tail Discovery v0"
  events.db readable             yes
  runtime_calibration block      present on every adaptive event
                                 (15 fields verified)
  rate_limit_429_count           0
  rate_limit_418_count           0
  rate_limit_ban                 False
  ws_stale_count                 0
  ws_reconnect_count             0
```

Safety flags held throughout:

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none (`/private` refused at allowlist)
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```
