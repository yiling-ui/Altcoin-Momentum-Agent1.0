# AMA-RT Project Status

This document is the at-a-glance status board for AMA-RT V1.4. It is
intentionally short. The full phase-gate ledger lives in
`docs/PHASE_GATE.md`; per-phase deep dives live in their own
`PHASE_*` documents.

## Current phase

> **Phase 11C.1C-C-B-A = IN_REVIEW (PR #42 open).** Strategy
> Validation Lab v0 + Cluster Exposure Control Contracts on top
> of the Phase 11C.1C-C-A `LabelTrackingRecord` outcomes. **NOT**
> ACCEPTED yet, **NOT** live trading, **NOT** AI Learning,
> **NOT** the complete Strategy Validation Lab, **NOT**
> automatic parameter optimisation, **NOT** Phase 12. Paper /
> report only.
>
> **Operator-VPS 10 min real public WS smoke PASSED** on
> 2026-05-23 against PR #42 head (commit `0bedcce`); the
> verbatim transcript + the authoritative SQLite event-count
> query are filed under `docs/PHASE_GATE.md` §"Phase
> 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real
> public WS smoke PASSED)". **PR #42 is ready for human review
> and may be merged after reviewer confirms docs-only evidence
> backfill.** Phase 11C.1C-C-B-A flips to ACCEPTED only after
> PR #42 merges, via the standard docs-only closeout PR
> (mirroring PR #36 → PR #37, PR #38 → PR #39, PR #40 → PR
> #41); this current docs-only evidence backfill does **not**
> self-flip the phase to ACCEPTED.
>
> **Phase 11C.1C-C-A = ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`).**
> **Phase 11C.1C-C-B = IN_REVIEW (sub-phase Phase 11C.1C-C-B-A open).**
> **Phase 11C.1C-C-B-B = RESERVED / NOT_STARTED.**
> **Phase 11C.1C-B = ACCEPTED (closed 2026-05-22; PR #38 merged into `main`).**
> **Phase 11C.1C-A = ACCEPTED (closed 2026-05-22; PR #36 merged via PR #37 docs closeout).**
> **Phase 11C.1B = ACCEPTED (closed 2026-05-22).**
> **Phase 12 (real money / live trading) = FORBIDDEN.**
> **We are still in paper mode.**
>
> PR #42 — the Phase 11C.1C-C-B-A *Strategy Validation Lab v0
> & Cluster Exposure Control Contracts* branch
> (`feature/phase-11c1c-c-b-strategy-validation-cluster-control`)
> — is open for human review with the operator-VPS smoke
> evidence backfilled. The branch ships the data contracts
> (`StrategyValidationSample`, `StrategyValidationReport`,
> `ClusterExposureAssessment`, …), the pure aggregators
> (`build_strategy_validation_report`, `aggregate_by_strategy_mode`,
> `aggregate_by_candidate_stage`,
> `aggregate_by_opportunity_score_bucket`,
> `aggregate_by_early_tail_score_bucket`,
> `aggregate_tail_label_distribution`,
> `evaluate_cluster_leader_performance`,
> `assess_cluster_exposure`), the runtime
> (`StrategyValidationRuntime`), the seven new typed events
> (`STRATEGY_VALIDATION_SAMPLE_CREATED` /
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_EXPOSURE_ASSESSED` /
> `CLUSTER_LEADER_VALIDATED`), the daily-report section, and
> the wiring through `WSRadarChainDriver` +
> `scripts/run_public_market_paper.py`. **Phase 11C.1C-C-B-A
> is paper-only**: the `suggested_cluster_action` field on every
> `ClusterExposureAssessment` is one of `leader_only` /
> `observe_followers` / `reject_cluster` / `no_action` and
> **MUST NEVER trigger a real trade**; the Risk Engine remains
> the single trade-decision gate. Phase 11C.1C-C-B-A acceptance
> does **NOT** authorise live trading, API keys, private
> endpoints, DeepSeek trade decisions, real Telegram outbound,
> Phase 11C.1C-C-B-B kickoff bypassing the standard gate, or
> Phase 12. **Tests:** 25/25 brief-mandated tests PASS,
> 312/312 phase11c\_ tests PASS, 2286/2286 full pytest PASS on
> the PR branch (no regression vs. the post-PR-#41 main 2261
> baseline). The 30 s dry-run is **contract-only** (the
> smallest Phase 11C.1C-C-A tracking window is 5 min; a 30 s
> run cannot complete a primary window). The
> **operator-VPS 10 min real public WS smoke PASSED** with
> `dry_run=false`, `ws_real_transport=true`,
> `ws_messages_received=76324`, `ws_chains_emitted=27`,
> `STRATEGY_VALIDATION_SAMPLE_CREATED=24`,
> `STRATEGY_VALIDATION_REPORT_GENERATED=1`,
> `STRATEGY_MODE_VALIDATED=4`,
> `CANDIDATE_STAGE_VALIDATED=5`,
> `SCORE_BUCKET_VALIDATED=8`,
> `CLUSTER_EXPOSURE_ASSESSED=1`,
> `CLUSTER_LEADER_VALIDATED=1` (authoritative SQLite query;
> see daily-report counter snapshot caveat below), non-empty
> daily-report cohort lines, `HTTP 429 count=0`,
> `HTTP 418 count=0`, `rate_limit_ban=False`,
> `ws_reconnect_count=0`, `ws_stale_count=0`,
> `ws_currently_stale=False`, `ingestion_errors=0`, and Phase
> 1 safety lock unchanged. Phase 12 remains **FORBIDDEN**.
>
> *Daily-report counter snapshot caveat.* The daily report's
> top event-count lines may show
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_*` counts as **0**
> because those event counters appear to be snapshotted
> **before** shutdown flush. The authoritative event
> repository SQLite query confirms those events were
> emitted; the daily report **section itself** rendered the
> Strategy Validation cohorts non-empty and correctly. This
> is a daily-report instrumentation nuance and does **not**
> invalidate the smoke; a future polish can move the counter
> snapshot after the shutdown flush, but it is **not** in
> scope for Phase 11C.1C-C-B-A.

The Phase 1 safety lock held end-to-end across the Phase 11C.1C-B
acceptance evidence runs and remains in force on `main`:
`mode=paper`, `live_trading=False`, `right_tail=False`,
`llm=False`, `exchange_live_orders=False`,
`telegram_outbound_enabled=False`, `binance_private_api_enabled=False`.
No Binance API key, no Binance API secret, no signed endpoint, no
private WebSocket, no `listenKey`, no DeepSeek trade decision, no
real Telegram outbound, no Phase 12. Phase 11C.1C-B is **paper /
virtual** only: the new `early_tail_score` and `runtime_calibration`
block are paper / descriptive fields; the Risk Engine remains the
single trade-decision gate.

| Date (UTC) | Phase    | Tag                                        | State   | Evidence                                                |
| ---------- | -------- | ------------------------------------------ | ------- | ------------------------------------------------------- |
| 2026-05-23 | Phase 11C.1C-C-B-A | Strategy Validation Lab v0 & Cluster Exposure Control Contracts (paper / report-only first slice of Phase 11C.1C-C-B; ships data contracts + pure aggregators + runtime that emits seven new typed events on top of the Phase 11C.1C-C-A `LabelTrackingRecord` outcomes) | **IN_REVIEW (PR #42 open)** — `tests/unit/test_phase11c_1c_c_b_strategy_validation.py` 25 PASS (brief-mandated cases); `tests/unit -k phase11c_` 312 PASS (287 baseline + 25 new); full `tests/` 2286 PASS on the PR branch (no regression vs. post-PR-#41 main 2261 baseline). 30 s dry-run smoke is contract-only (smallest Phase 11C.1C-C-A tracking window is 5m and cannot complete in 30 s); the runtime emits an empty-but-well-formed `STRATEGY_VALIDATION_REPORT_GENERATED` so the daily report still renders the new section. **Operator-VPS 10 min real public WS smoke PASSED** on 2026-05-23 against PR #42 head (commit `0bedcce`): `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=76324`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `ingestion_errors=0`, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`. Authoritative SQLite event-count query (captured after shutdown flush): `STRATEGY_VALIDATION_SAMPLE_CREATED=24`, `STRATEGY_VALIDATION_REPORT_GENERATED=1`, `STRATEGY_MODE_VALIDATED=4`, `CANDIDATE_STAGE_VALIDATED=5`, `SCORE_BUCKET_VALIDATED=8`, `CLUSTER_EXPOSURE_ASSESSED=1`, `CLUSTER_LEADER_VALIDATED=1`. Daily report contains the new "Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster Exposure Control Contracts" section with non-empty cohort lines (`strategy_mode=reject n=24`; `candidate_stage=early n=24`; `opportunity_score_bucket=0-49 n=13` / `50-64 n=11`; `early_tail_score_bucket=0-24 n=24`; `cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action`); `tail_label_distribution = unresolved x 24` (5m primary windows still in-flight at the 10 min boundary, as expected). Daily-report counter snapshot caveat: top event-count lines may show 0 because counters are snapshotted before shutdown flush; SQLite query is authoritative and confirms emission. Safety flags unchanged (`live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `trading_mode_paper=True`, no API key, no signed endpoint, no private WS, no listenKey, no DeepSeek trade decision, no real Telegram outbound). The Kiro-side sandbox cannot host this smoke (Binance-region HTTP 451 geoblock — historical context only, not the current blocker; same as the Phase 11C.1C-B / Phase 11C.1C-C-A closeouts). The `suggested_cluster_action` field on every `ClusterExposureAssessment` is paper / report only (`leader_only` / `observe_followers` / `reject_cluster` / `no_action`) and **MUST NEVER trigger a real trade**; the Risk Engine remains the single trade-decision gate. **PR #42 is ready for human review and may be merged after reviewer confirms docs-only evidence backfill;** this evidence backfill does **NOT** self-flip the phase to ACCEPTED — that happens via the standard docs-only closeout PR after PR #42 has merged. Phase 11C.1C-C-B-B remains **NOT_STARTED**; Phase 11C.1C-C-B-A acceptance does **NOT** authorise Phase 11C.1C-C-B-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_STRATEGY_VALIDATION_CLUSTER_CONTROL.md`; `docs/PR42_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_strategy_validation.py`; `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-A (IN_REVIEW)" + §"Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)" |
| 2026-05-23 | Phase 11C.1C-C-A | MFE / MAE Label Queue Runtime & Tail Outcome Tracking (paper-only runtime that consumes the Phase 11C.1C-A `LABEL_QUEUE_ENQUEUED` contract and produces forward MFE / MAE / `tail_label` outcomes per ACTIVE candidate) | **ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`)** — `tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py` 30 PASS (brief-mandated cases); `tests/unit -k phase11c_` 287 PASS; full `tests/` 2261 PASS on the PR branch (no regression vs. post-PR-#38 main baseline). 30 s dry-run smoke is contract-only (the smallest tracking window is 5m and cannot complete in 30 s). **Operator-VPS 10 min real public WS smoke PASSED** (`duration_seconds=600.0`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=56592`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `LABEL_TRACKING_STARTED=19` runner / `36` events.db, `LABEL_WINDOW_UPDATED=38` / `82`, `LABEL_WINDOW_COMPLETED=11` / `20`, `TAIL_LABEL_ASSIGNED=11` / `20`, `MISSED_TAIL_DETECTED=0`, `FAKE_BREAKOUT_DETECTED=0`, pending=8 / completed=11 / expired=0 / unresolved=0, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`, `ingestion_errors=0`, safety flags unchanged); the Kiro sandbox could not host the smoke (Binance-region HTTP 451 geoblock, same as the Phase 11C.1C-B closeout), so the operator ran it from a Binance-reachable VPS. PR #40 has merged into `main` (mergeCommit `75d3c7c`); the smoke evidence above was accepted; Phase 11C.1C-C-A is therefore **ACCEPTED**. Phase 11C.1C-C-A acceptance does **NOT** authorise Phase 11C.1C-C-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md`; `docs/PR40_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-A (ACCEPTED)" + §"Phase 11C.1C-C-A acceptance evidence (closeout)" |
| 2026-05-23 | Phase 11C.1C-C-B | Adaptive Candidate Strategy Validation Lab & Cluster Exposure Control (placeholder; reserved for Phase 11C.1C-C follow-up after Phase 11C.1C-C-A is ACCEPTED) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-A is now **ACCEPTED** (PR #40 merged into `main`, mergeCommit `75d3c7c`), so Phase 11C.1C-C-B is now **NEXT_ALLOWED**; no implementation has started. Phase 11C.1C-C-A acceptance does **NOT** authorise Phase 11C.1C-C-B kickoff bypassing the standard gate; Phase 11C.1C-C-B will require its own kickoff PR, brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A forbidden item. | `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-22 | Phase 11C.1C-B | Adaptive Candidate Runtime Calibration & Early Tail Discovery v0 (paper-only runtime calibration metrics + Early Tail Discovery v0 + daily-report enhancements) | **ACCEPTED (closed 2026-05-22; PR #38 merged into `main`)** — `tests/unit/test_phase11c_1c_b_runtime_calibration.py` 12 PASS; `tests/unit -k phase11c_` 257 PASS; full `tests/` 2231 PASS with no regression vs. the post-PR-#37 main baseline; 30s dry-run produced a `runtime_calibration` block with all 15 fields on every adaptive event and `early_tail_score` per ACTIVE candidate; 5min real public WS smoke (`--ws-first`, no `--dry-run`) confirmed `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=30526`, `ws_chains_emitted=12`, runtime calibration block present on every adaptive event, daily report contains `top_early_tail_candidates` / `top_late_chase_risk_candidates` / `early_tail_score_top_symbols` / `opportunity_score_distribution`, `label_queue` remains contract-only, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `rate_limit_ban=False`, `ws_stale_count=0`, `ws_reconnect_count=0`, `ingestion_errors=12` (explainable: sandbox-region geoblock HTTP 451 on Binance REST; NOT a 429/418/ban; WS pump ran cleanly), safety flags unchanged. PR #38 merged into `main` (mergeCommit `ce4b6de`); the smoke evidence above was accepted; Phase 11C.1C-B is therefore **ACCEPTED**. Phase 11C.1C-C is now **NEXT_ALLOWED / NOT_STARTED**. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_B_RUNTIME_CALIBRATION.md`; `tests/unit/test_phase11c_1c_b_runtime_calibration.py`; `docs/PHASE_GATE.md` §"Phase 11C.1C-B acceptance evidence (closeout)" |
| 2026-05-22 | Phase 11C.1C-A | Adaptive Candidate Regime & Strategy Selector Contracts (paper-only data contracts + scoring + selector + paper-only routing first version) | **ACCEPTED (PR #36 merged; PR #37 docs closeout)** — 244/244 phase11c tests + 2219/2219 full pytest pass on the PR branch; 30s dry-run produces the six adaptive events per ACTIVE candidate; 5min real public WS smoke produced 32842 real WS messages, 12 chains, 12 each of the six adaptive event types, 0 stales, 0 reconnects, 0 rate-limit 429/418/ban; daily report contains the Phase 11C.1C-A adaptive section; safety flags unchanged. PR #36 merged into `main`; PR #37 closed the Phase 11C.1C-A docs gate. | `docs/PHASE_11C_1C_ADAPTIVE_CANDIDATE_REGIME_STRATEGY_SELECTOR.md`; `tests/unit/test_phase11c_1c_a_adaptive_candidate.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-A (ACCEPTED)" |
| 2026-05-22 | Phase 11C.1B | WebSocket-First All-Market Demon Coin Radar (incl. SymbolUniverse exchangeInfo-as-truth, non-ASCII contracts allowed) | **ACCEPTED** — 5min / 10min / 1h real WS smoke PASS (no 429, no 418, no stale, no ingestion errors); export zip generated; events.db readable; PRs #31 / #32 / #33 / #34 merged; safety flags unchanged | `docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B |
| 2026-05-21 | Phase 11C.1A | Binance Public REST Rate Limit Governor & 418 Protection | merged        | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1A     |
| 2026-05-21 | Phase 11C | Real Binance Public Market Data Read-Only Paper | open (parent); Phase 11C.1B (5min / 10min / 1h smoke) ACCEPTED 2026-05-22; longer-window (6h / 24h) acceptance still optional / not yet run | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md`             |
| 2026-05-19 | Phase 11B-HF | Cloud Paper - High-Frequency observation     | accepted (GO) | 30/30 dry-run PASS, 648/648 24h@2min observations PASS |
| 2026-05-19 | Phase 11B | Cloud Paper Acceptance                       | accepted (GO) | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`            |
| ...        | Phase 10D | Telegram Outbound + Export Commands          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10C | LLM Guarded Interpreter (receive-only)       | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10B | Reflection + Replay engines (read-only)      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10A | Replay engine substrate                      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 9   | Execution FSM + Reconciliation               | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 8.5 | Learning-Ready Data Contract                 | merged        | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`           |
| ...        | Phase 8   | Capital Flow Engine                          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 7   | Risk Engine + No-Trade Gate                  | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 6   | Pre-Anomaly + Anomaly + Confirmation + Manipulation | merged | `docs/CHANGELOG.md`                                  |
| ...        | Phase 5   | Regime + Universe + Liquidity                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 4   | Market Data Buffer                           | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 3   | Exchange Gateway (read-only abstract)        | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 2   | Event Sourcing + Database Set                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 1   | Safety Foundation                            | merged        | `docs/CHANGELOG.md`                                    |

## Live safety flags (Phase 1 lock)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

The Phase 1 safety lock in `app/config/settings.py::_apply_phase1_safety_lock`
hard-coerces the first five flags. The Phase 11C
`MarketDataConfig` and `SafetyConfig` schemas refuse to load any
deployment that flips a `forbid_*` flag.

## Why the Phase 11C real-data acceptance was paused (historical, RESOLVED)

The first 24h test against the real Binance public REST endpoints
(`fapi.binance.com`) exposed two failure modes the original Phase 11C
runner did not protect against:

  1. HTTP 429 (Too Many Requests). Binance returned this once the
     per-IP weight budget was exceeded. The runner kept polling and
     escalated to:
  2. HTTP 418 (I'm a teapot). Binance uses 418 to signal a real IP
     ban.

Phase 11C's safety lock held throughout (`mode=paper`,
`live_trading=False`, no API key, no signed endpoint, no real order),
but the gateway was unusable for real-data acceptance until the
rate-limit problem is fixed.

**Phase 11C.1A** (PR #31) shipped the fix in three layers:

  - a new `BinancePublicRestGovernor`
    (`app/exchanges/binance_rate_limit.py`) that wraps every public
    REST call, tracks the rolling weight budget, sleeps the
    `Retry-After` window on 429, latches into protection mode on
    418, and opens a P1 incident;
  - lower defaults (`symbol_limit=5`, `rest_poll_interval_seconds=60`,
    `weight_budget_per_minute=300`, soft 0.50 / hard 0.75);
  - a layered REST runner that does `exchangeInfo` / `ticker/24hr`
    only at bootstrap and refuses per-symbol detail REST calls
    unless a candidate ranking selects them.

**Phase 11C.1B** (PRs #32 / #33 / #34) then shipped the WebSocket-first
all-market radar + the routed real-network public WS adapter + the
WS poll fix + the SymbolUniverse exchangeInfo-as-truth gate (non-ASCII
contracts admitted; ASCII-only regex banned). The 5min / 10min / 1h
real-WS smoke ladder now passes cleanly with zero 429 / 418 / stale /
ingestion errors. See "Phase 11C.1B acceptance evidence (closeout)"
below for the headline numerics.

PR-C (cluster exposure control + multi-candidate priority ranking)
remains a separate, future scope item and is **not** required for the
Phase 11C.1B closeout; it is tracked alongside the future
Phase 11C.1C — Adaptive Candidate Regime & Strategy Selector work.

## What Phase 11C is

Phase 11C is real **Binance public market data** read-only paper.
It connects to public REST endpoints (`/fapi/v1/exchangeInfo`,
`/fapi/v1/ticker/24hr`, `/fapi/v1/klines`, `/fapi/v1/aggTrades`,
`/fapi/v1/depth`, `/fapi/v1/fundingRate`, `/fapi/v1/openInterest`,
`/fapi/v1/premiumIndex`, `/fapi/v1/ticker/bookTicker`), feeds the
data through the existing `MarketDataBuffer` and Risk Engine, and
emits the full Phase 11C event chain into `events.db`.

## What Phase 11C is NOT

- NOT live trading
- NOT connected to the Binance trading API
- NOT consuming any Binance API key / API secret
- NOT calling any signed endpoint
- NOT calling any account / position / leverage / margin endpoint
- NOT connected to DeepSeek
- NOT connected to a real Telegram bot
- NOT connected to 币安广场
- NOT a path into Phase 12

## Open phase

**Phase 11C.1C-C-B — Adaptive Candidate Strategy Validation
Lab & Cluster Exposure Control.** Status: **NEXT_ALLOWED /
NOT_STARTED.** Phase 11C.1C-C-A (PR #40) merged into `main`
on 2026-05-23 (mergeCommit `75d3c7c`); the operator-VPS 10
min real public WS smoke evidence on file under
`docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence
(closeout)" was accepted; Phase 11C.1C-C-A is therefore
**ACCEPTED**, and Phase 11C.1C-C-B is now **NEXT_ALLOWED**.
No implementation has started in this repo state; Phase
11C.1C-C-B will require its own kickoff PR, brief, scope,
boundary table, forbidden list, and acceptance evidence.

> **Phase 11C.1C-C-A acceptance does NOT authorise Phase
> 11C.1C-C-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-A acceptance does NOT authorise private
> endpoints.**
> **Phase 11C.1C-C-A acceptance does NOT authorise DeepSeek
> trade decisions.**
> **Phase 11C.1C-C-A acceptance does NOT authorise real
> Telegram outbound.**
> **Phase 11C.1C-C-A acceptance does NOT authorise Phase 12.**
> **`mfe_pct` / `mae_pct` / `tail_label` / `strategy_mode` MUST
> NEVER trigger a real trade** — they are descriptive labels
> only; the Risk Engine remains the single trade-decision gate.
> **Phase 12 (real money / live trading) remains FORBIDDEN.**

Phase 11C.1C-C-B inherits every Phase 1 + Phase 11C.1B +
Phase 11C.1C-A + Phase 11C.1C-B + Phase 11C.1C-C-A forbidden
item:

  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority

See `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B
(NEXT_ALLOWED / NOT_STARTED)" for the inherited boundary
table.

## Closed phase: Phase 11C.1C-C-A (acceptance closeout)

**Phase 11C.1C-C-A — MFE / MAE Label Queue Runtime & Tail
Outcome Tracking (PR #40).** Status: **ACCEPTED (closed
2026-05-23; PR #40 merged into `main`, mergeCommit
`75d3c7c`).** Phase 11C.1C-C-A shipped the **paper-only first
runtime** that consumes the Phase 11C.1C-A
`LABEL_QUEUE_ENQUEUED` contract and produces forward
MFE / MAE / `tail_label` outcomes per ACTIVE candidate over
five tracking windows (5m primary, 15m / 30m / 1h / 4h
secondary). It does **NOT** ship the deeper Strategy
Validation Lab, AI Learning, or Cluster Exposure Control —
those are reserved for Phase 11C.1C-C-B and now sit at
**NEXT_ALLOWED / NOT_STARTED**.

The acceptance gate is **fully on file**:

  - Test ladder green: 30 brief-mandated tests + 287 phase11c
    tests + 2261 full pytest, no regression vs. the
    post-PR-#38 main baseline.
  - **Operator-VPS 10 min real public WS smoke PASSED** (run
    from a Binance-reachable VPS against commit `6d6044d`):
    `dry_run=false`, `ws_real_transport=true`,
    `ws_messages_received=56592`, `ws_chains_emitted=27`,
    `learning_ready_attached=27`, `snapshots_emitted=27`,
    `LABEL_TRACKING_STARTED=19` (runner) / `36` (events.db),
    `LABEL_WINDOW_UPDATED=38` / `82`,
    `LABEL_WINDOW_COMPLETED=11` / `20` (5m primary window
    closed inside the 10 min run), `TAIL_LABEL_ASSIGNED=11`
    / `20`, `MISSED_TAIL_DETECTED=0`,
    `FAKE_BREAKOUT_DETECTED=0`, `pending_label_records=8`,
    `completed_label_records=11`, `expired_label_records=0`,
    `unresolved_label_records=0`, `HTTP 429 count=0`,
    `HTTP 418 count=0`, `rate_limit_ban=False`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `ws_currently_stale=False`, `ingestion_errors=0`,
    safety flags unchanged.
  - Daily report contains `"## Phase 11C.1C-C-A MFE / MAE
    Label Queue Runtime & Tail Outcome Tracking"`.
  - Safety boundary held end-to-end: no API key, no signed
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound, Phase
    12 remained **FORBIDDEN**.

The Kiro-side sandbox could **not** host the smoke (the same
Binance-region HTTP 451 geoblock recorded under the Phase
11C.1C-B closeout still applies to the Kiro sandbox), so the
operator ran it from a Binance-reachable VPS and back-filled
the verbatim transcript under `docs/PHASE_GATE.md` §"Phase
11C.1C-C-A acceptance evidence (closeout)". A sandbox WS
smoke would **not** have been authoritative evidence and was
**not** filed as such.

PR #40 has **merged into `main`** (mergeCommit `75d3c7c`,
merged 2026-05-23 UTC); the smoke evidence above was
accepted; this docs-only closeout PR therefore flips Phase
11C.1C-C-A to **ACCEPTED** under `docs/PROJECT_STATUS.md` /
`docs/PHASE_GATE.md` / `docs/CHANGELOG.md`, mirroring the PR
#36 → PR #37 and PR #38 → PR #39 closeout pattern.

Phase 11C.1C-C-A acceptance does **NOT** authorise:

  - Phase 11C.1C-C-B kickoff bypassing the standard gate.
  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority

See `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md` for
the full Phase 11C.1C-C-A scope, boundary, and forbidden-item
list; see `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance
evidence (closeout)" for the verbatim operator-VPS smoke
transcript.

## Closed phase: Phase 11C.1C-B (acceptance closeout)

**Phase 11C.1C-B — Adaptive Candidate Runtime Calibration &
Early Tail Discovery v0 (PR #38).** Status: **ACCEPTED (closed
2026-05-22; PR #38 merged into `main`, mergeCommit
`ce4b6de`).** Phase 11C.1C-B shipped the **paper-only first
version** of the Adaptive Candidate Runtime Calibration & Early
Tail Discovery layer on top of the Phase 11C.1C-A contracts
(`AdaptiveCandidateContext`, the six adaptive event types,
`MarketRegimeAssessment` / `CandidateStageAssessment` /
`OpportunityScore` / `StrategyModeDecision` / `ClusterContext` /
`LabelQueueContract`). The 30s dry-run + 5min real public WS
smoke evidence captured under `docs/PHASE_GATE.md` §"Phase
11C.1C-B acceptance evidence (closeout)" was accepted; PR #38
has merged into `main`. Every Phase 1 safety flag remained
`False` end-to-end across the acceptance runs. Phase 11C.1C-B
is **NOT** live trading, **NOT** AI Learning, **NOT** complete
Strategy Validation, **NOT** the full MFE/MAE processor — those
are reserved for Phase 11C.1C-C. The Phase 1 safety lock and
every Phase 11C.1B / 11C.1C-A forbidden item carry over
unchanged; Phase 12 (live trading) stays `FORBIDDEN`.

Phase 11C.1C-B shipped:

  - **Runtime calibration metrics** attached to every adaptive
    candidate: `candidate_first_seen_ts`,
    `candidate_first_seen_price`, `current_price`,
    `price_change_since_first_seen`,
    `quote_volume_acceleration_1m`,
    `quote_volume_acceleration_5m`, `price_acceleration_1m`,
    `price_acceleration_5m`, `volume_rank`, `volume_rank_jump_5m`,
    `distance_to_24h_high`, `distance_from_first_seen`,
    `freshness_score`, `late_chase_risk`, `early_tail_score`.
  - **Early Tail Discovery v0.** The candidate pool's capacity
    eviction does NOT discard candidates with high
    `early_tail_score`. The radar surfaces volume-rank jumps,
    quote-volume accelerations, and price accelerations on
    EDEN / ALT / NEAR-style demon-coin starts EARLIER than
    Phase 11C.1B's flat radar score.
  - **Stage calibration.** ``early`` + high volume expansion +
    high freshness MAY enter ``follow`` / ``pullback`` (paper /
    virtual). ``late`` / ``blowoff`` MUST NEVER upgrade to
    ``follow``. ``manipulation_risk`` high MUST ``reject`` or
    ``observe``.
  - **Daily-report enhancements.** New fields:
    `top_early_tail_candidates`, `top_late_chase_risk_candidates`,
    `early_tail_score_top_symbols`,
    `opportunity_score_distribution`,
    `symbols_promoted_before_24h_top_move`, plus EDEN / ALT /
    NEAR style candidate examples when present.
  - **Event / export compatibility.** Every new field lands in
    `EventRepository`, the Phase 8.5 learning-ready payload, the
    daily report, and the Phase 8.5 export. Phase 10A replay
    accepts the new fields without failure.

Phase 11C.1C-B is **paper-mode only**. The new
`early_tail_score` is a descriptive / paper field that protects
a candidate from capacity-driven eviction in the candidate pool
but does NOT authorise opening a real position. The Risk Engine
remains the single trade-decision gate; `stop_unconfirmed=True`
continues to lock the WS-radar chain into the typed-reject path.

> Phase 11C.1C-B specifically does NOT authorise:
>
>   - live trading
>   - Binance API key / secret
>   - signed endpoint
>   - private websocket
>   - listenKey
>   - account / order / position / leverage / margin endpoint
>   - DeepSeek trade decision
>   - real Telegram outbound
>   - Phase 12
>   - AI Learning
>   - the full MFE/MAE processor
>   - real orders
>   - promoting `early_tail_score` / `strategy_mode` to a
>     real-trade authority

See `docs/PHASE_11C_1C_B_RUNTIME_CALIBRATION.md` for the full
runtime-calibration first-version contract; see
`docs/PHASE_GATE.md` §"Phase 11C.1C-B acceptance evidence
(closeout)" for the acceptance smoke evidence numerics.

## Closed phase: Phase 11C.1C-A (acceptance closeout)

**Phase 11C.1C-A — Adaptive Candidate Regime & Strategy Selector
Contracts (PR #36).** Status: **ACCEPTED (closed 2026-05-22; PR
#36 merged; PR #37 docs closeout).** Phase 11C.1C-A shipped the
**paper-only first version** of the data contracts + scoring +
selector + paper-only routing for the Adaptive Candidate Regime &
Strategy Selector. The 30s dry-run + 5min real public WS smoke
evidence captured under `docs/PHASE_GATE.md` §"Phase 11C.1C-A
acceptance evidence" was accepted; PR #36 has merged into
`main`; PR #37 closed out the docs gate. Every Phase 1 safety
flag remained `False` end-to-end across the acceptance runs.
Phase 11C.1C-A is **NOT** live trading, **NOT** AI Learning,
**NOT** complete Strategy Validation, **NOT** the full MFE/MAE
processor — those are reserved for later PRs (Phase 11C.1C-B /
11C.1C-C). The Phase 1 safety lock and every Phase 11C.1B
forbidden item carry over unchanged; Phase 12 (live trading)
stays `FORBIDDEN`.

See `docs/PHASE_11C_1C_ADAPTIVE_CANDIDATE_REGIME_STRATEGY_SELECTOR.md`
for the full first-version contract.

## Phase 11C.1B acceptance evidence (closeout)

Phase 11C.1B closed on **2026-05-22 (UTC)** with the following
evidence on file. Full numerics live in
`docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; this section
is the at-a-glance summary.

### PRs that compose Phase 11C.1B

| PR    | Scope                                                                                                | Status |
| ----- | ---------------------------------------------------------------------------------------------------- | ------ |
| #31   | Phase 11C.1A — Binance Public REST Governor / 429 backoff / 418 shutdown protection                  | merged |
| #32   | Phase 11C.1B PR-B — WebSocket-first all-market radar; real `StdlibPublicWSTransport`; routed `/public/stream` + `/market/stream` | merged |
| #33   | Phase 11C.1B follow-up — fix real WS poll zero-timeout that left `ws_messages_received=0`             | merged |
| #34   | Phase 11C.1B follow-up — `SymbolUniverse` / exchangeInfo-as-truth; non-ASCII contracts admitted; ASCII-only regex banned | merged |

### Real-WS smoke ladder (PASS)

| Smoke run        | Duration | Outcome | Headline metrics                                                                                                              |
| ---------------- | -------- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 5 min real WS    | 5 min    | PASS    | `ws_messages_received=30317`, `ws_chains_emitted=12`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 10 min real WS   | 608 s    | PASS    | `ws_messages_received=59644`, `ws_chains_emitted=27`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 1 h real WS (clean) | 3600 s | PASS    | `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=349134`, `ws_chains_emitted=177`, `ws_learning_ready_attached=177`, `snapshots_emitted=177`, `ingestion_errors=0`, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_staleness_ms_max=0`, `ws_stale_count=0`, `ws_currently_stale=False` |

### Persistence + export evidence

  - `events.db` readable: `events_count=56644`. The event-aggregation
    query passed without traceback.
  - Phase 8.5 export: generated successfully; export files are zip
    archives.
  - Demon-coin discovery sanity: `EDENUSDT` appeared in the radar
    top-symbols list AND in the top event-volume aggregation, which
    is the qualitative evidence that the WS-first all-market radar
    is functioning end-to-end.

### Safety boundary held throughout the Phase 11C.1B acceptance run

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

## Phase 11C.1B — what it ships (closeout reference)

PR-B adds three new modules + extends two existing ones:

  - `app/exchanges/binance_public_ws.py` -
    `BinancePublicWSClient` + `WSConfig` + `WSMessage` +
    `WSMessagePump` + `InProcessWSPump` + `_RefusalTransport`
    (default; refuses any real-network call) +
    **`StdlibPublicWSTransport`** (real-network RFC 6455 client
    built on the Python standard library only, route-aware) +
    **`MultiTransportPublicWSManager`** (owns one routed
    `StdlibPublicWSTransport` per route - PUBLIC + MARKET - and
    merges their messages behind a single `WSMessagePump`
    interface) + `create_real_public_ws_transport` factory +
    `classify_stream_route` + `split_streams_by_route` +
    `assert_public_ws_stream_allowed` +
    `assert_public_ws_url_allowed` +
    `assert_public_ws_path_allowed`. Stream allowlist:
    `!ticker@arr`, `!miniTicker@arr`, `!bookTicker`,
    `!markPrice@arr`, `!forceOrder@arr`. Stream-route
    classification: `!bookTicker` is the PUBLIC route;
    `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` /
    `!forceOrder@arr` are the MARKET route. Path-root
    acceptance allowlist: `/public/ws`, `/public/stream`,
    `/market/ws`, `/market/stream` (legacy unrouted `/ws` /
    `/stream` are kept as back-compat for the in-process pump
    fixtures only). Forbidden path roots: `/private`, `/ws-api`,
    `/ws-fapi`, `/ws-papi`, `/trading-api`, `/userDataStream`.
    Host allowlist: `fstream.binance.com`,
    `fstream.binancefuture.com`. The transport refuses every
    credential-shaped kwarg (`api_key` / `api_secret` /
    `listen_key` / `token` / `signature` / `passphrase`) and
    never reads `BINANCE_API_KEY` / `BINANCE_API_SECRET`.
  - `app/market_data_public/radar.py` -
    `AllMarketRadarSnapshot` (frozen pydantic model) +
    `AllMarketRadarBuffer` (per-symbol rolling state) +
    `pre_anomaly_score_light` (pure additive scoring with
    deterministic reason tags).
  - `app/market_data_public/candidate_pool.py` - `CandidatePool`
    with default `candidate_pool_size=20`, `active_detail_limit=3`,
    `candidate_ttl_seconds=900`. Each candidate carries a
    Phase 8.5 `OpportunityIdentity` with
    `source_phase="phase_11c_1b_ws_first_radar"`.
  - `app/market_data_public/ws_radar_chain.py` -
    `WSRadarChainDriver` emits PRE_ANOMALY_DETECTED ->
    ANOMALY_DETECTED -> STATE_TRANSITION (+ Phase 8.5
    LearningReadyContext on each, + RISK_REJECTED via the live
    RiskEngine) per ACTIVE candidate.
  - `app/core/events.py` - three new EventType entries:
    `PUBLIC_WS_CONNECTED`, `PUBLIC_WS_DISCONNECTED`,
    `PUBLIC_WS_STALE`.
  - `app/paper_run/daily_report.py` - `DailyReportSnapshot` +
    `DailyReportBuilder` extended with WS + radar metrics; new
    `Phase 11C.1B WebSocket all-market radar` Markdown section.
  - `scripts/run_public_market_paper.py` - new CLI flags
    `--ws-first` (default ON) / `--ws-disabled` (mutex),
    `--candidate-pool-size`, `--active-detail-limit`,
    `--ws-staleness-threshold-ms`, `--candidate-ttl-seconds`. The
    runner pumps WS -> ingest into radar -> score every snapshot
    -> offer to pool -> expire stale candidates -> drive
    WSRadarChainDriver on the active head (skipped while
    `ws_client.is_stale=True`, the data-degraded gate); the
    active head also receives REST detail through the existing
    PR-A governor.

### Real routed public WS adapter

PR #32 ships the real-network public WebSocket adapter inline.
**`StdlibPublicWSTransport`** is a single-class, stdlib-only RFC
6455 client; **`MultiTransportPublicWSManager`** owns one of those
adapters per route (PUBLIC + MARKET) and presents them behind a
single `WSMessagePump` interface. The pair targets the documented
Binance USDⓈ-M Futures routed endpoints
(`wss://fstream.binance.com/public/stream` and
`wss://fstream.binance.com/market/stream`). The unrouted
`wss://fstream.binance.com/stream?streams=...` path silently
drops market-class streams (per the Binance public-WS reference)
and is therefore NOT the acceptance path; the routed-private
endpoint `wss://fstream.binance.com/private` is forbidden at the
path-root allowlist (`FORBIDDEN_WS_PATH_ROOTS`). The adapter
performs the HTTP/1.1 Upgrade handshake (`GET <route>/stream` with
`Sec-WebSocket-Key` / `Sec-WebSocket-Version: 13`), validates the
server's `Sec-WebSocket-Accept`, parses RFC 6455 text frames, and
surfaces decoded `WSMessage` envelopes. The third-party WebSocket
package deny-list (`websockets` / `websocket-client` / `aiohttp` /
`requests` / `httpx` / `urllib3`) in
`tests/unit/test_phase11c_no_network.py` continues to hold.

The runner refuses to silently fall back to the PR-A
bootstrap-only REST path: `--ws-first` without `--dry-run`
**requires** a real public WS pump. If the factory returns
`None` or raises, the runner exits with `rc=2` and the message
`real public WebSocket transport is required for --ws-first
without --dry-run`. The only path to REST-only operation is the
explicit `--ws-disabled` flag, documented as NOT the Phase 11C.1B
acceptance path.

## Phase 11C.1B execution modes

| CLI                                       | Behaviour                                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `--ws-first --dry-run` (default)          | In-process pump, deterministic synthetic messages, no socket, full event chain.                                        |
| `--ws-first` (no `--dry-run`)             | Real `MultiTransportPublicWSManager` opening routed PUBLIC (`/public/stream`) + MARKET (`/market/stream`) endpoints. RC=2 if the factory cannot produce one - never silently falls back to REST. |
| `--ws-disabled`                           | PR-A bootstrap-only REST path. Documented as **not** the Phase 11C.1B all-market demon-radar acceptance path.          |
