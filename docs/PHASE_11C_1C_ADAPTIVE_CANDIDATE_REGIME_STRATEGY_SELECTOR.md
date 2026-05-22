# Phase 11C.1C-A — Adaptive Candidate Regime & Strategy Selector Contracts

This document is the canonical specification for Phase 11C.1C-A. It
extends the Phase 11C.1B WebSocket-first all-market radar with the
**first version** of the Adaptive Candidate Regime & Strategy
Selector contracts.

> **Phase 11C.1C-A is NOT live trading. It is NOT AI Learning. It is
> NOT a complete strategy validator. It is NOT a complete MFE/MAE
> processor. It is the data-contract + scoring + selector + paper-only
> routing first version.**

## What this PR ships

1. New package **`app/adaptive/`** with seven Pydantic v2 frozen
   value objects + five pure classifier / scorer functions:
   - `MarketRegimeAssessment` (regime bucket + risk multiplier)
   - `CandidateStageAssessment` (early / mid / late / blowoff /
     dumped)
   - `OpportunityScore` (S / A / B / C grade)
   - `StrategyModeDecision` (follow / pullback / observe / reject)
   - `ClusterContext` (cluster_id + leader + rank)
   - `LabelQueueContract` (5m / 15m / 30m / 1h / 4h tracking
     windows; `mfe_mae_label_pending=True` and
     `future_tail_label_pending=True` by default)
   - `AdaptiveCandidateContext` (one-shot bundle of the above)
   - `assess_market_regime`, `classify_candidate_stage`,
     `compute_opportunity_score`, `select_strategy_mode`,
     `build_cluster_context`, `build_label_queue_contract`,
     `build_adaptive_candidate_context`.
2. Six new EventType entries in `app/core/events.py`:
   - `MARKET_REGIME_ASSESSED`
   - `CANDIDATE_STAGE_CLASSIFIED`
   - `OPPORTUNITY_SCORED`
   - `STRATEGY_MODE_SELECTED`
   - `CLUSTER_CONTEXT_ATTACHED`
   - `LABEL_QUEUE_ENQUEUED`
3. `LearningReadyContext` (Phase 8.5) extended with an optional
   `adaptive_candidate` field. Existing eleven canonical
   learning-ready event types are unchanged.
4. `VirtualTradePlan` extended with eleven optional adaptive
   fields: `opportunity_score`, `opportunity_grade`,
   `candidate_stage`, `strategy_mode`, `cluster_id`,
   `cluster_leader`, `label_queue_pending`, `follow_allowed`,
   `pullback_allowed`, `observe_only`, `reject_reason`. All
   default to `None` so existing callers continue to work.
5. `WSRadarChainDriver` extended:
   - builds an `AdaptiveCandidateContext` per ACTIVE candidate
   - emits the six new events alongside the existing
     `PRE_ANOMALY_DETECTED` / `ANOMALY_DETECTED` /
     `STATE_TRANSITION` chain
   - attaches the adaptive context to every event's
     `learning_ready.adaptive_candidate`
   - propagates the adaptive fields onto the paper
     `VirtualTradePlan`
   - tracks per-regime / per-stage / per-mode / per-grade
     histograms and exposes `adaptive_metrics_payload()` for the
     runner / daily report
6. `DailyReportBuilder` accepts a new `adaptive_metrics` kwarg and
   emits a new
   `## Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector`
   Markdown section with every brief-mandated counter
   (`market_regime_counts`, `candidate_stage_counts`,
   `strategy_mode_counts`, `opportunity_grade_counts`,
   `top_opportunity_scores`, `label_queue_enqueued`,
   `observe_count`, `reject_count`, `follow_count`,
   `pullback_count`, `late_chase_rejected_count`,
   `blowoff_observed_count`).
7. The Phase 11C runner (`scripts/run_public_market_paper.py`)
   populates `adaptive_metrics` from
   `WSRadarChainDriver.adaptive_metrics_payload()` on every loop
   tick, so the daily report carries the latest adaptive figures
   on shutdown.
8. New test file
   `tests/unit/test_phase11c_1c_a_adaptive_candidate.py` (31
   tests) pinning every brief-mandated behaviour. The Phase 8.5 +
   Phase 10A + Phase 11B + Phase 11C / 11C.1A / 11C.1B test
   surfaces remain unchanged; the new tests run in-process with
   the deterministic radar / candidate-pool / chain pipeline.

## What this PR does NOT do

- It does NOT enable live trading.
- It does NOT touch the Binance trading API.
- It does NOT consume any Binance API key / API secret /
  `listenKey` / signed endpoint / private WebSocket / user data
  stream / trading WebSocket API / account / margin / position /
  leverage / balance / order private WS variant.
- It does NOT enable real Telegram outbound.
- It does NOT enable DeepSeek as a trade-decision authority.
- It does NOT introduce a Strategy Selector with live-trading
  authority.
- It does NOT enable AI Learning that auto-decides trades.
- It does NOT implement the full MFE/MAE processor (the queue is
  a contract; the processor lands in a future PR).
- It does NOT implement full Strategy Validation (the selector is
  a first version; richer validation lands in a future PR).
- It does NOT enter Phase 12.

## Boundary that MUST hold

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
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| Routed-private endpoint (`/private`)        | refused at path-root allowlist |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| Phase 12 (live trading)                     | FORBIDDEN                    |

## Scoring formula (first version)

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

All inputs are clipped to `[0.0, 100.0]` before weighting; the
score is clipped to `[0.0, 100.0]` after summing. Grade
boundaries:

  - **S** : score >= 80
  - **A** : score in [65, 80)
  - **B** : score in [50, 65)
  - **C** : score < 50

Inputs and weights are configurable through
`OpportunityScoreInputs` and `OpportunityScoreWeights`; the brief
defaults are the load-bearing values.

## Strategy selector (first version)

Decision flow (in priority order):

  1. `manipulation_risk >= 60` → **reject** (`reject_reason =
     "high_manipulation_risk"`).
  2. regime is `RISK_OFF` / `NO_TRADE` / `SYSTEMIC_RISK` →
     **reject**. Regime `ALT_RISK_OFF` → **observe** (observe-only
     for reflection; no new opens).
  3. stage is `dumped` / `blowoff` / `late` → **observe**.
  4. stage is `mid` AND momentum_strength >= 60 AND
     late_chase_risk >= 60 → **pullback**.
  5. stage is `early` AND momentum_strength >= 60 AND
     volume_expansion >= 50 AND regime_fit >= 60 AND
     late_chase_risk <= 40 AND `follow` is in
     `regime.allowed_strategy_modes` → **follow**.
  6. otherwise → **observe**.

The `mode` is a **paper / virtual** field. Selecting `follow`
does **NOT** authorise opening a position; the Risk Engine remains
the single trade-decision gate. The Phase 11C.1B WS-radar chain
still calls the Risk Engine with `stop_unconfirmed=True` so EVERY
decision falls into the typed-reject-reason path.

## Candidate stage classifier (first version)

```
distance = (current_price - first_seen_price) / first_seen_price

  distance <= -0.10               -> dumped
  distance >= 0.30                -> late
  distance >= 0.15 AND accel_60s >= 0.05 -> blowoff
  distance >= 0.05                -> mid
  otherwise                       -> early
```

`freshness` decays as a half-life function of the elapsed wall
time since `first_seen_ts`; default half-life is 5 minutes.

## Market regime classifier (first version)

The classifier returns a conservative bucket from a small
aggregate input set:

  - `data_quality == "stale"` → **NO_TRADE**.
  - `liquidation_event_rate >= 0.10` → **SYSTEMIC_RISK**.
  - `avg_price_acceleration_60s <= -0.005 AND
    positive_acceleration_ratio < 0.30` → **ALT_RISK_OFF**.
  - `avg_price_acceleration_60s >= 0.005 AND
    positive_acceleration_ratio >= 0.55` → **MEME_RISK_ON**.
  - `avg_price_acceleration_60s >= 0.002 AND
    positive_acceleration_ratio >= 0.40` → **SECTOR_ROTATION**.
  - else → **NEUTRAL** / **BTC_ABSORPTION**.

`risk_multiplier` and `allowed_strategy_modes` come from default
mappings keyed on the bucket; future tuning can override per-call
without touching the bucket vocabulary.

## Acceptance criteria

1. `pytest tests/unit/test_phase11c_1c_a_adaptive_candidate.py`
   passes (31 tests).
2. The full Phase 11C test surface continues to pass (no
   regression).
3. The 30 s dry-run produces an `AdaptiveCandidateContext` for
   every active candidate and writes the six adaptive events into
   `events.db`.
4. The 5 min real-WS paper run produces adaptive fields on every
   chain (no regression in the Phase 11C.1B 5min smoke ladder).
5. The Phase 8.5 export zip + Phase 10A replay accept the six new
   event types without failure.
6. Every safety flag remains `False` after running the adaptive
   path end-to-end:
     - `mode = paper`
     - `live_trading_enabled = False`
     - `right_tail_enabled = False`
     - `llm_enabled = False`
     - `exchange_live_order_enabled = False`
     - `telegram_outbound_enabled = False`
     - `binance_private_api_enabled = False`
7. No live trading.
8. No API key.
9. No private endpoint.
10. Phase 12 stays `FORBIDDEN`.

## Versions stamped on every adaptive event

```
strategy_version       = phase_11c_1c_a.strategy.v1
scoring_version        = phase_11c_1c_a.scoring.v1
risk_config_version    = phase_11c_1c_a.risk_config.v1
state_machine_version  = phase_11c_1c_a.state_machine.v1
```

A future PR that bumps the formula or the state machine bumps the
version label and Reflection / Replay automatically picks up the
change.
