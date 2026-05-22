# PR #36 Description — Phase 11C.1C-A: Adaptive Candidate Regime & Strategy Selector Contracts

> **Status: IN_REVIEW / PR_OPEN.** PR #36 is open against `main`; it has
> **not** been merged. Phase 11C.1C-A will only be marked **ACCEPTED**
> after this PR is merged AND the smoke evidence below is accepted by
> a human reviewer. Phase 11C.1C-B remains
> **NOT_STARTED / BLOCKED_UNTIL_11C_1C_A_ACCEPTED** until that gate
> fires. Phase 12 (live trading) remains **FORBIDDEN**.

## What this PR ships

Phase 11C.1C-A is the **paper-only first version** of the data
contracts + scoring + selector + paper-only routing for the Adaptive
Candidate Regime & Strategy Selector. It is **NOT** live trading,
**NOT** AI Learning, **NOT** complete strategy validation, **NOT** the
full MFE/MAE processor — those are reserved for later sub-phases
(11C.1C-B / 11C.1C-C).

  - New `app/adaptive/` package with seven Pydantic v2 frozen value
    objects (`MarketRegimeAssessment`, `CandidateStageAssessment`,
    `OpportunityScore`, `StrategyModeDecision`, `ClusterContext`,
    `LabelQueueContract`, `AdaptiveCandidateContext`) + six pure
    classifier / scorer functions.
  - Six new `EventType` entries: `MARKET_REGIME_ASSESSED`,
    `CANDIDATE_STAGE_CLASSIFIED`, `OPPORTUNITY_SCORED`,
    `STRATEGY_MODE_SELECTED`, `CLUSTER_CONTEXT_ATTACHED`,
    `LABEL_QUEUE_ENQUEUED`. Emitted alongside the existing Phase
    11C.1B WS-radar event chain.
  - Phase 8.5 `LearningReadyContext` extended with optional
    `adaptive_candidate` field; `VirtualTradePlan` extended with
    eleven optional adaptive fields. All defaults remain `None` so
    existing callers keep working; the round-trip helper preserves
    them.
  - `WSRadarChainDriver` builds and emits the adaptive context per
    ACTIVE candidate, attaches it to `learning_ready`, and exposes
    `adaptive_metrics_payload()` for the runner / daily report.
  - `DailyReportBuilder.build()` accepts a new `adaptive_metrics`
    kwarg and renders the
    `## Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector`
    Markdown section.

The paper / virtual `strategy_mode` field is descriptive only. The
Risk Engine remains the single trade-decision gate;
`stop_unconfirmed=True` continues to lock the WS-radar chain into the
typed-reject path.

## Acceptance evidence (pre-merge)

### 30s dry-run smoke

```
command: python -m scripts.run_public_market_paper \
           --duration 30s --symbol-limit 3 --dry-run

banner phase tag                      Phase 11C.1C-A v1.4.0a11c.1c.a
dry_run                               True
adaptive_candidate context generated  yes (per ACTIVE candidate)
ws_messages_received                  6 (in-process pump)
ws_chains_emitted                     2
MARKET_REGIME_ASSESSED                2
CANDIDATE_STAGE_CLASSIFIED            2
OPPORTUNITY_SCORED                    2
STRATEGY_MODE_SELECTED                2
CLUSTER_CONTEXT_ATTACHED              2
LABEL_QUEUE_ENQUEUED                  2
daily report                          contains "## Phase 11C.1C-A
                                      Adaptive Candidate Regime &
                                      Strategy Selector"
events.db readable                    yes (43 events)
Phase 8.5 export                      generated successfully
                                      (zip, 25402 bytes)
ingestion_errors                      0
rate_limit_429_count                  0
rate_limit_418_count                  0
rate_limit_ban                        False
```

### 5min real public WS smoke (--ws-first, no --dry-run)

```
command: python -m scripts.run_public_market_paper \
           --duration 5min --symbol-limit 5 --ws-first \
           --symbols BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT

banner phase tag                      Phase 11C.1C-A v1.4.0a11c.1c.a
dry_run                               False
ws_real_transport                     True (real RFC 6455 stdlib
                                      transport against
                                      wss://fstream.binance.com routed
                                      PUBLIC + MARKET endpoints)
duration_seconds                      301
iterations                            5
ws_messages_received                  32842
ws_chains_emitted                     12
candidate_pool_size_max               20
radar_candidates_seen                 3043

# Adaptive event counts in the daily report:
MARKET_REGIME_ASSESSED count          12
CANDIDATE_STAGE_CLASSIFIED count      12
OPPORTUNITY_SCORED count              12
STRATEGY_MODE_SELECTED count          12
CLUSTER_CONTEXT_ATTACHED count        12
LABEL_QUEUE_ENQUEUED count            12
adaptive_metrics section in report    present
label_queue_enqueued                  12

# WS health:
rate_limit_429_count                  0
rate_limit_418_count                  0
rate_limit_ban                        False
ws_stale_count                        0
ws_reconnect_count                    0
ws_currently_stale                    False

# Persistence + export:
events.db readable                    yes (270 events; 14 each of the
                                      six adaptive event types across
                                      the 30s + 5min runs cumulative)
Phase 8.5 export                      generated successfully
                                      (zip, 119699 bytes)

# Caveat:
ingestion_errors                      12  EXPLAINABLE — see below
```

#### ingestion_errors=12 — explainable

The 5min smoke was run from a sandbox region whose IP is geo-blocked
by Binance's REST endpoints (`fapi.binance.com` returns HTTP 451
"Unavailable for Legal Reasons"). The runner's existing graceful
fallback handled this:

  - The bootstrap `exchangeInfo` call returned 451; the runner fell
    back to the **empty admit-all `SymbolUniverse`** per its
    documented PR #34 fallback.
  - Per-loop active-head detail REST (`aggTrades` / `depth` /
    `fundingRate` / `openInterest` / `premiumIndex` /
    `bookTicker`) returned 451 and was counted as `ingestion_errors`.
    Twelve such errors over five minutes (one per active-head detail
    poll for the active candidates).

These are **NOT** Binance rate-limit errors:

  - `rate_limit_429_count = 0`
  - `rate_limit_418_count = 0`
  - `rate_limit_protection_triggered = False`
  - `rate_limit_ban = False`

The real WS pump itself ran cleanly throughout (`ws_real_transport=
True`, 32842 messages, 0 stales, 0 reconnects, 0 ws-stale ticks). On
a non-geoblocked operator host, the active-head REST detail polling
would succeed and `ingestion_errors` would be 0; the adaptive event
chain is unaffected by REST detail availability.

### Tests

```
python -m pytest tests/unit/test_phase11c_1c_a_adaptive_candidate.py -q
  31 passed

python -m pytest tests/unit/ -k "phase11c_" -q
  244 passed

python -m pytest tests/ -q
  2219 passed   (no regressions)
```

## Safety boundary held throughout

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
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to raise
`SafeModeViolation` on the public REST client. The new
`strategy_mode` field is paper / virtual only and never opens an
order; the Risk Engine remains the single trade-decision gate.

## Doc state corrected on this PR

The previous revision of this PR had prematurely flipped the project
docs to a "merged" state. That has been walked back in this revision:

  - `docs/PROJECT_STATUS.md` — Phase 11C.1C-A = **IN_REVIEW /
    PR_OPEN (PR #36)**; Phase 11C.1C-B = **NOT_STARTED /
    BLOCKED_UNTIL_11C_1C_A_ACCEPTED**; Phase 12 = **FORBIDDEN**.
  - `docs/PHASE_GATE.md` — Phase 11C.1C-A removed from the "Closed
    phases" table; new "Open phase: Phase 11C.1C-A (IN_REVIEW /
    PR_OPEN)" section with the pre-merge smoke evidence; Phase
    11C.1C-B status flipped from `NEXT_ALLOWED / NOT_STARTED` to
    `NOT_STARTED / BLOCKED_UNTIL_11C_1C_A_ACCEPTED`.
  - `docs/CHANGELOG.md` — explicit pre-merge IN_REVIEW callout under
    `[Unreleased]`; test-count line updated to the pre-merge
    figure measured on the PR branch.

> After PR #36 is merged and the smoke evidence is accepted, Phase
> 11C.1C-A may be marked **ACCEPTED** and only then will Phase
> 11C.1C-B become **NEXT_ALLOWED**.

## Acceptance checklist

- [x] `python -m scripts.run_public_market_paper --duration 30s --symbol-limit 3 --dry-run` — six adaptive events per candidate, daily report contains the Phase 11C.1C-A section, events.db readable, export zip generated.
- [x] `python -m scripts.run_public_market_paper --duration 5min --symbol-limit 5 --ws-first` — `ws_real_transport=True`, `dry_run=False`, 32842 real WS messages, adaptive events emitted, `adaptive_metrics` in daily report, `label_queue_enqueued > 0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `rate_limit_ban=False`, `ws_stale_count=0`, `ingestion_errors` explained (sandbox geo-block on REST, not a Binance rate-limit issue).
- [x] `pytest tests/unit/test_phase11c_1c_a_adaptive_candidate.py` — 31 PASS.
- [x] `pytest tests/unit/ -k "phase11c_"` — 244 PASS.
- [x] `pytest tests/` — 2219 PASS, no regressions.
- [x] Safety flags unchanged across both smoke runs.
- [x] No live trading, no API key, no signed endpoint, no private WebSocket.
- [x] Docs no longer prematurely claim PR #36 merged.
- [x] Phase 11C.1C-B remains NOT_STARTED until PR #36 is accepted.
- [x] Phase 12 remains FORBIDDEN.
