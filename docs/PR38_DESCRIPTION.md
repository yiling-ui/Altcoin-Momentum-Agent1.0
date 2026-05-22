# PR #38 Description — Phase 11C.1C-B: Adaptive Candidate Runtime Calibration & Early Tail Discovery v0

> **Status: IN_REVIEW / PR_OPEN.** PR #38 is open against `main`
> (post-PR-#37 baseline); it has **not** been merged. Phase
> 11C.1C-B will only be marked **ACCEPTED** after this PR is
> merged AND the smoke evidence below is accepted by a human
> reviewer. Phase 11C.1C-C remains **NOT_STARTED**. Phase 12
> (live trading) remains **FORBIDDEN**.
>
> Phase 11C.1C-A is **ACCEPTED** (closed 2026-05-22; PR #36
> merged; PR #37 docs closeout). This PR builds on that
> baseline.

## What this PR ships

Phase 11C.1C-B is the **paper-only first version** of the
Adaptive Candidate Runtime Calibration & Early Tail Discovery
layer that builds on top of the Phase 11C.1C-A contracts. It is
**NOT** live trading, **NOT** AI Learning, **NOT** complete
strategy validation, **NOT** the full MFE/MAE processor (the
queue stays a descriptive contract; the processor is reserved
for a later PR), **NOT** real Telegram outbound, **NOT** real
Binance trading API.

- **`RuntimeCalibrationMetrics`** value object in
  `app/adaptive/models.py` — frozen Pydantic v2 model carrying
  the brief-mandated fifteen runtime fields
  (`candidate_first_seen_ts`, `candidate_first_seen_price`,
  `current_price`, `price_change_since_first_seen`,
  `quote_volume_acceleration_1m`, `quote_volume_acceleration_5m`,
  `price_acceleration_1m`, `price_acceleration_5m`,
  `volume_rank`, `volume_rank_jump_5m`, `distance_to_24h_high`,
  `distance_from_first_seen`, `freshness_score`,
  `late_chase_risk`, `early_tail_score`). Attached to every
  `AdaptiveCandidateContext` under the new `runtime_calibration`
  field and rides into the Phase 8.5
  `learning_ready.adaptive_candidate.runtime_calibration`
  sub-block.
- **`app/adaptive/runtime.py`** — pure-function helpers
  (`compute_runtime_calibration`, `compute_early_tail_score`,
  `compute_late_chase_risk_score`, `compute_freshness_score`,
  `compute_relative_acceleration`). All pure; the existing
  source-tree audit
  (`test_adaptive_module_does_not_import_third_party_network_libs`)
  continues to cover the new module.
- **`Candidate` baselines + per-symbol rolling history** in
  `app/market_data_public/candidate_pool.py`:
  `first_seen_price`, `quote_volume_first_seen`,
  `volume_rank_first_seen` recorded ONCE at admission; rolling
  `price_history` / `quote_volume_history` /
  `volume_rank_history` capped at
  `per_symbol_history_max_samples=200` and trimmed to the last
  10 minutes; runtime-layer scores written back via
  `CandidatePool.update_runtime_metrics(...)`.
- **Early Tail Discovery v0 — capacity-protection invariant.**
  `CandidatePool._enforce_capacity` sorts candidates by a
  two-tier eviction key
  `(protected_flag, early_tail_score, radar_score, last_seen_ms)`
  so that a high-`early_tail_score` candidate can NEVER be
  evicted by a flat-radar-score competitor. Default threshold:
  `DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD = 60.0`.
- **`WSRadarChainDriver` integration** in
  `app/market_data_public/ws_radar_chain.py`: now accepts
  `candidate_pool=`, reads `candidate.first_seen_price`,
  threads rolling histories into `compute_runtime_calibration`,
  and exposes new aggregates via `adaptive_metrics_payload`
  (`top_early_tail_candidates`,
  `top_late_chase_risk_candidates`,
  `early_tail_score_top_symbols`,
  `opportunity_score_distribution`,
  `symbols_promoted_before_24h_top_move`,
  `eden_alt_near_examples`).
- **Daily report enhancement** in
  `app/paper_run/daily_report.py`: `DailyReportSnapshot` + the
  Markdown body now carry every brief-mandated field. New
  Markdown section
  `## Phase 11C.1C-B Adaptive Candidate Runtime Calibration &
  Early Tail Discovery v0` rendered after the existing
  11C.1C-A block.
- **Tests:**
  `tests/unit/test_phase11c_1c_b_runtime_calibration.py` (12
  brief-mandated cases:
  `test_early_tail_score_detects_volume_rank_jump`,
  `test_freshness_penalizes_late_chase`,
  `test_late_blowoff_never_follow`,
  `test_top_early_tail_candidates_reported`,
  `test_candidate_first_seen_price_preserved`,
  `test_volume_rank_jump_calculated`,
  `test_adaptive_runtime_fields_exportable`,
  `test_no_live_trading_flags_unchanged`,
  `test_runtime_calibration_payload_round_trips`,
  `test_pool_protects_high_early_tail_candidate_from_eviction`,
  `test_eden_alt_near_examples_surfaced`,
  `test_strategy_mode_does_not_authorise_real_trade`).

The new `early_tail_score` is descriptive only. It protects a
candidate from capacity-driven eviction in the candidate pool;
it does **NOT** authorise opening a real position. The Risk
Engine remains the single trade-decision gate;
`stop_unconfirmed=True` continues to lock the WS-radar chain
into the typed-reject path.

## Tests run (all PASS, no regression vs. post-PR-#37 main baseline)

```
python -m pytest tests/unit/test_phase11c_1c_b_runtime_calibration.py -q
                                              12 passed in 0.28s

python -m pytest tests/unit/ -k "phase11c_" -q
                                              257 passed, 1974 deselected in 8.85s

python -m pytest tests/ -q
                                              2231 passed in 14.32s
```

## 5 min real public WS smoke summary

```
command: python -m scripts.run_public_market_paper \
           --duration 5min --symbol-limit 5 --ws-first \
           --symbols BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT

banner phase tag                      Phase 11C.1C-A v1.4.0a11c.1c.a
                                      (CLI banner not yet bumped to
                                      11C.1C-B; will be flipped on
                                      ACCEPT or in a follow-up)
dry_run                               False
ws_real_transport                     True (real RFC 6455 stdlib
                                            transport;
                                            wss://fstream.binance.com
                                            routed PUBLIC + MARKET
                                            endpoints)
duration_seconds                      302
iterations                            5
chains_emitted                        12
ws_chains_emitted                     12
ws_messages_received                  30526
ws_risk_rejected                      12
ws_learning_ready_attached            12
snapshots_emitted                     12
radar_candidates_seen                 3029
candidate_pool_size_max               20
liquidation_events_seen               133

events.db (855 events total, all six adaptive event types
present at 72 each, plus the Phase 11C.1B chain)
  MARKET_REGIME_ASSESSED              72
  CANDIDATE_STAGE_CLASSIFIED          72
  OPPORTUNITY_SCORED                  72
  STRATEGY_MODE_SELECTED              72
  CLUSTER_CONTEXT_ATTACHED            72
  LABEL_QUEUE_ENQUEUED                72
  PRE_ANOMALY_DETECTED                87
  ANOMALY_DETECTED                    87
  STATE_TRANSITION                    87
  RISK_REJECTED                       87
  PUBLIC_WS_CONNECTED                 2
  PUBLIC_WS_DISCONNECTED              2

runtime_calibration block             present on every adaptive
                                      event (15 fields verified)
early_tail_score                      generated per ACTIVE
                                      candidate

daily report (`## Phase 11C.1C-B ...` section)
  top_early_tail_candidates           BEATUSDT 13.98,
                                      BEATUSDT 4.09,
                                      NEARUSDT 0.06
  top_late_chase_risk_candidates      SOPHUSDT 17.71,
                                      PLAYUSDT 16.72,
                                      WIFUSDT 14.76,
                                      SYRUPUSDT 14.33,
                                      BEATUSDT 13.86,
                                      BEATUSDT 12.80,
                                      PROMPTUSDT 9.39,
                                      NEARUSDT 1.68
  early_tail_score_top_symbols        EDEN/ALT/NEAR slot:
                                      NEARUSDT 0.06
  opportunity_score_distribution      40-50 x7, 50-60 x3,
                                      60-70 x2
  symbols_promoted_before_24h_top_move  0 (chain), 0 (pool)
  early_tail_protect_threshold        60.00 (default)

label_queue                           contract-only
                                      (LABEL_QUEUE_ENQUEUED
                                       emitted; no MFE/MAE
                                       processor)

rate_limit_429_count                  0
rate_limit_418_count                  0
rate_limit_ban                        False
rate_limit_protection_triggered       False
ws_stale_count                        0
ws_reconnect_count                    0
ws_currently_stale                    False
ws_data_degraded_ticks                0
used_weight_1m_max                    0
public_endpoint_calls                 0  (REST geo-blocked at
                                          the sandbox edge)

ingestion_errors                      12   (explainable: sandbox-
                                            region geo-block on
                                            Binance REST
                                            `fapi.binance.com`
                                            returned HTTP 451 for
                                            the active-head detail
                                            REST ladder
                                            (`/fapi/v1/exchangeInfo`,
                                            `/fapi/v1/aggTrades`,
                                            `/fapi/v1/depth`,
                                            `/fapi/v1/fundingRate`,
                                            `/fapi/v1/openInterest`,
                                            `/fapi/v1/premiumIndex`,
                                            `/fapi/v1/ticker/bookTicker`).
                                            SymbolUniverse fell back
                                            to the admit-all empty
                                            universe per the documented
                                            fallback path. All 146
                                            transport-level errors
                                            were HTTP 451 (region
                                            geoblock); NOT a 429,
                                            NOT a 418, NOT a Binance
                                            ban, NOT a TLS / WS issue.
                                            The real WS pump
                                            (wss://fstream.binance.com/public/stream
                                            + /market/stream) ran
                                            cleanly throughout: 30526
                                            frames, 0 stales, 0
                                            reconnects.)

events.db readable                    yes (855 events)
Phase 8.5 export                      generated successfully
                                      (`ama_rt_test_data_..._export_e.zip`,
                                       438711 bytes, 855 events,
                                       750 opportunities, 87
                                       rejections, 87 state
                                       transitions, redaction
                                       applied)
```

## Docs state confirmation

The PR updates the four phase-state docs to the post-PR-#37
baseline + adds the Phase 11C.1C-B IN_REVIEW evidence:

  - `docs/PROJECT_STATUS.md` — Current phase block flipped to:
    Phase 11C.1C-A = **ACCEPTED (closed 2026-05-22; PR #36 merged;
    PR #37 docs closeout)**, Phase 11C.1C-B = **IN_REVIEW /
    PR_OPEN (PR #38)**, Phase 11C.1C-C = **NOT_STARTED**, Phase
    12 = **FORBIDDEN**. Evidence-row table reflects the same
    states. Open-phase block is now Phase 11C.1C-B; new "Closed
    phase: Phase 11C.1C-A (acceptance closeout)" subsection
    appended.
  - `docs/PHASE_GATE.md` — Closed-phases table now contains the
    `11C.1C-A | ACCEPTED 2026-05-22` row (was placeholder
    comment). The previous `Open phase: Phase 11C.1C-A
    (IN_REVIEW)` and `Open phase: Phase 11C.1C-B (BLOCKED)`
    sections are replaced with `Closed phase: Phase 11C.1C-A
    (ACCEPTED)` and `Open phase: Phase 11C.1C-B (IN_REVIEW /
    PR_OPEN)` plus a new `Phase 11C.1C-B IN_REVIEW evidence
    (pre-merge / PR #38)` subsection containing the actual
    smoke numerics. The legacy `Open phase: Phase 11C.1C` block
    + the `Future phases` table both flipped to match.
  - `docs/CHANGELOG.md` — A new
    `### Phase 11C.1C-B - Adaptive Candidate Runtime Calibration
    & Early Tail Discovery v0` entry under `[Unreleased]`
    describing this PR; the existing `### Phase 11C.1C-A` entry
    flipped from IN_REVIEW to ACCEPTED (closed 2026-05-22; PR
    #36 merged; PR #37 docs closeout) and its trailing
    "PR #36 has not been merged" footer removed.
  - `docs/PHASE_11C_1C_B_RUNTIME_CALIBRATION.md` — Header
    blockquote prepended marking the doc as IN_REVIEW / PR_OPEN
    on PR #38.

The docs explicitly state Phase 11C.1C-B is **NOT** ACCEPTED,
**NOT** MERGED, **IN_REVIEW / PR_OPEN** until PR #38 is merged
and the smoke evidence is accepted.

## Safety flags confirmation

The Phase 1 safety lock held throughout the 30s dry-run + 5min
real WS smoke. Every flag below remains as printed by the
`env_guard_passed=True` runner banner:

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

The four `ExchangeClientBase` write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to
raise `SafeModeViolation` on the public REST client.

## Remaining risk

  - **CLI banner.** The runner banner still prints
    `Phase 11C.1C-A v1.4.0a11c.1c.a`. The runtime-calibration
    layer is functioning end-to-end on top of that banner; the
    label flip to `Phase 11C.1C-B v1.4.0a11c.1c.b` can be done
    on ACCEPT or in a follow-up doc-only PR. No behavioural
    impact.
  - **REST-side observations are degraded by the sandbox-region
    geoblock.** The real Binance public WS path is unaffected
    (30526 frames, 0 stale, 0 reconnect). On an
    operator-region VPS where REST is reachable, the active-head
    detail REST ladder will populate the candidate-detail
    fields and `early_tail_score` will be richer. The
    runtime-calibration layer itself does not regress.
  - **Phase 11C.1C-C (deeper Strategy Validation + Cluster
    Exposure Control + full MFE/MAE processor)** remains
    **NOT_STARTED** and out of scope for this PR. The
    `LabelQueueContract` ships as a descriptive contract only;
    no live processor is wired.
  - **Discovery numbers under sandbox geoblock.** The 5min
    smoke surfaced 3 early-tail candidates and 8
    late-chase-risk candidates on the WS-only data plane
    (BTCUSDT/ETHUSDT/BNBUSDT/SOLUSDT/ADAUSDT seed list); on the
    operator VPS where REST is reachable, the candidate pool
    ought to surface a richer mix.

## Phase-state assertions

> **Phase 11C.1C-B is IN_REVIEW / PR_OPEN before merge.** It is
> **NOT** ACCEPTED, **NOT** MERGED.
>
> **Phase 11C.1C-C remains NOT_STARTED.**
>
> **Phase 12 remains FORBIDDEN.**

## Phase 11C.1C-B explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` / `/userDataStream`
    path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Promoting `early_tail_score` / `strategy_mode` (paper /
    virtual) to a real-trade authority.
  - Enabling AI Learning that auto-decides trades.
  - Implementing the full MFE/MAE processor (the queue stays a
    descriptive contract; the processor is reserved for a later
    PR).
  - Issuing any real order.
  - Entering Phase 12.
