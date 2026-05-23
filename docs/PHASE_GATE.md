# AMA-RT Phase Gate Ledger

Single canonical record of which phases have closed, which are open,
and what the gate criteria for the next phase look like. Each phase
must have an explicit acceptance record before the next phase opens.

The five Phase 1 safety flags REMAIN LOCKED across every phase below;
**no phase in this document loosens them**. Loosening any of them is a
Phase 12+ concern and requires the Spec §41 Go/No-Go checklist.

## Closed phases

| #     | Title                                              | Closed (UTC)    | Acceptance evidence                                            |
| ----- | -------------------------------------------------- | --------------- | -------------------------------------------------------------- |
| 1     | Safety Foundation                                  | 2025-10 (est.)  | `docs/CHANGELOG.md`                                            |
| 2     | Event Sourcing + Database Set                      | 2025-10 (est.)  | `docs/CHANGELOG.md`                                            |
| 3     | Exchange Gateway (read-only abstract)              | 2025-11 (est.)  | `docs/CHANGELOG.md`, `tests/unit/test_phase3_no_network.py`    |
| 4     | Market Data Buffer                                 | 2025-11 (est.)  | `docs/CHANGELOG.md`, `tests/unit/test_phase4_no_network.py`    |
| 5     | Regime + Universe + Liquidity                      | 2025-12 (est.)  | `docs/CHANGELOG.md`                                            |
| 6     | Pre-Anomaly + Anomaly + Confirmation + Manipulation | 2025-12 (est.) | `docs/CHANGELOG.md`                                            |
| 7     | Risk Engine + No-Trade Gate + Account Tier         | 2026-01 (est.)  | `docs/CHANGELOG.md`                                            |
| 8     | Capital Flow Engine                                | 2026-02 (est.)  | `docs/CHANGELOG.md`                                            |
| 8.5   | Learning-Ready Data Contract                       | 2026-02 (est.)  | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`                   |
| 9     | Execution FSM + Reconciliation                     | 2026-03 (est.)  | `docs/CHANGELOG.md`                                            |
| 10A   | Replay Engine substrate                            | 2026-03 (est.)  | `docs/CHANGELOG.md`                                            |
| 10B   | Reflection + Replay (read-only)                    | 2026-04 (est.)  | `docs/CHANGELOG.md`                                            |
| 10C   | LLM Guarded Interpreter (receive-only)             | 2026-04 (est.)  | `docs/CHANGELOG.md`                                            |
| 10D   | Telegram Outbound + Export Commands                | 2026-05 (est.)  | `docs/CHANGELOG.md`                                            |
| 11B   | Cloud Paper Acceptance                             | 2026-05-19      | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`                    |
| 11B-HF | Cloud Paper - High-Frequency observation          | 2026-05-19      | 30/30 dry-run PASS; 648/648 24h@2min observations PASS         |
| 11C.1A | Binance Public REST Rate Limit Governor & 418 Protection | 2026-05-21 | PR #31 merged; `tests/unit/test_phase11c1a_rate_limit_governor.py` |
| 11C.1B | WebSocket-First All-Market Demon Coin Radar (incl. SymbolUniverse exchangeInfo-as-truth) | 2026-05-22 | PRs #32 / #33 / #34 merged; 5min / 10min / 1h real WS smoke PASS; export zip generated; events.db readable; safety flags unchanged. See "Phase 11C.1B acceptance summary" below. |
| 11C.1C-A | Adaptive Candidate Regime & Strategy Selector Contracts (paper-only) | 2026-05-22 | PR #36 merged; PR #37 docs closeout; 244/244 phase11c tests + 2219/2219 full pytest pass; 30s dry-run + 5min real public WS smoke PASS (32842 real WS messages, 12 chains, 12 each of the six adaptive event types, 0 stales, 0 reconnects, 0 rate-limit 429/418/ban); daily report contains the Phase 11C.1C-A adaptive section; safety flags unchanged. See "Closed phase: Phase 11C.1C-A (ACCEPTED)" below. |
| 11C.1C-B | Adaptive Candidate Runtime Calibration & Early Tail Discovery v0 (paper-only) | 2026-05-22 | PR #38 merged into `main` (mergeCommit `ce4b6de`); 12/12 brief-mandated tests + 257/257 phase11c tests + 2231/2231 full pytest pass on the PR branch; 30s dry-run + 5min real public WS smoke PASS (`dry_run=false`, `ws_real_transport=true`, 30526 real WS messages, 12 chains, 72 each of the six adaptive event types, runtime calibration block on every adaptive event with all 15 fields, `top_early_tail_candidates` / `top_late_chase_risk_candidates` / `early_tail_score_top_symbols` / `opportunity_score_distribution` in the daily report, `label_queue` contract-only, 0 stales, 0 reconnects, 0 rate-limit 429/418/ban); safety flags unchanged. See "Phase 11C.1C-B acceptance evidence (closeout)" below. |
| 11C.1C-C-A | MFE / MAE Label Queue Runtime & Tail Outcome Tracking (paper-only) | 2026-05-23 | PR #40 merged into `main` (mergeCommit `75d3c7c`); 30/30 brief-mandated tests + 287/287 phase11c tests + 2261/2261 full pytest PASS on the PR branch (no regression vs. post-PR-#38 main 2231 baseline); operator-VPS 10 min real public WS smoke PASS (`duration_seconds=600.0`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=56592`, `ws_chains_emitted=27`, `LABEL_TRACKING_STARTED=19` runner / `36` events.db, `LABEL_WINDOW_UPDATED=38` / `82`, `LABEL_WINDOW_COMPLETED=11` / `20`, `TAIL_LABEL_ASSIGNED=11` / `20`, `MISSED_TAIL_DETECTED=0`, `FAKE_BREAKOUT_DETECTED=0`, pending=8 / completed=11 / expired=0 / unresolved=0, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`, `ingestion_errors=0`); safety flags unchanged. See "Closed phase: Phase 11C.1C-C-A (ACCEPTED)" and "Phase 11C.1C-C-A acceptance evidence (closeout)" below. |
| 11C.1C-C-B-A | Strategy Validation Lab v0 & Cluster Exposure Control Contracts (paper / report-only) | 2026-05-23 | PR #42 merged into `main` (mergeCommit `cc18047`); 25/25 brief-mandated tests + 312/312 phase11c tests + 2286/2286 full pytest PASS on the PR branch (no regression vs. post-PR-#41 main 2261 baseline); operator-VPS 10 min real public WS smoke PASS against PR #42 head (commit `0bedcce`): `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=76324`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `STRATEGY_VALIDATION_SAMPLE_CREATED=24`, `STRATEGY_VALIDATION_REPORT_GENERATED=1`, `STRATEGY_MODE_VALIDATED=4`, `CANDIDATE_STAGE_VALIDATED=5`, `SCORE_BUCKET_VALIDATED=8`, `CLUSTER_EXPOSURE_ASSESSED=1`, `CLUSTER_LEADER_VALIDATED=1` (authoritative SQLite query captured after shutdown flush), non-empty daily-report cohort lines, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`, `ingestion_errors=0`; safety flags unchanged. See "Closed phase: Phase 11C.1C-C-B-A (ACCEPTED)" and "Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)" below. |


## Open / Reserved phases

| #          | Title                                                                | State                       | Detail                                                                 |
| ---------- | -------------------------------------------------------------------- | --------------------------- | ---------------------------------------------------------------------- |
| 11C.1C-C-B-B | Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up | **NEXT_ALLOWED / NOT_STARTED** | Phase 11C.1C-C-B-A (PR #42) merged into `main` on 2026-05-23 (mergeCommit `cc18047`); the operator-VPS 10 min real public WS smoke evidence under §"Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)" was accepted; Phase 11C.1C-C-B-A is therefore **ACCEPTED**, and Phase 11C.1C-C-B-B is now **NEXT_ALLOWED**. NOT authorised by Phase 11C.1C-C-B-A acceptance bypassing the standard gate; will require its own kickoff PR, brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A forbidden item verbatim. |
| 12         | Real money / live trading                                            | **FORBIDDEN**               | Phase 12 remains **FORBIDDEN** under the Phase 1 safety lock. Spec §41 Go/No-Go checklist is the only path forward, and it has **not** been initiated. NOT permitted from any Phase 11C sub-phase alone (incl. Phase 11C.1C-C-A acceptance, Phase 11C.1C-C-B-A acceptance, Phase 11C.1C-C-B-B, or any other Phase 11C sub-phase). |


### Phase 11B-HF acceptance summary

```
30x dry-run:        30/30 PASS
24h / 2min HF run observed: 648 PASS
go_decision=GO:     648
accepted=True:      648
FAIL:                 0
ERROR:                0
mode:               paper
live_trading:       False
right_tail:         False
llm:                False
exchange_live_orders: False
telegram_outbound_enabled: False
real Binance API:   not connected
real Telegram:      not connected
real DeepSeek:      not connected
```

### Phase 11C.1B acceptance summary

Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar (incl. the
SymbolUniverse / exchangeInfo-as-truth follow-up) - was accepted on
**2026-05-22 (UTC)**. The acceptance evidence is the cloud real-WS
smoke ladder + the persistence + export sanity checks below; the Phase
1 safety lock is unchanged throughout.

**Composing PRs (all merged):**

  - PR #31 - Phase 11C.1A: Binance Public REST Governor / 429
    backoff / 418 shutdown protection.
  - PR #32 - Phase 11C.1B PR-B: WebSocket-first all-market radar;
    real `StdlibPublicWSTransport`; routed `/public/stream` +
    `/market/stream`.
  - PR #33 - Phase 11C.1B follow-up: fix real WS poll zero-timeout
    that was leaving `ws_messages_received=0`.
  - PR #34 - Phase 11C.1B follow-up: `SymbolUniverse` /
    exchangeInfo-as-truth; non-ASCII Binance contract symbols
    admitted; ASCII-only symbol regex banned on the validation
    path; `CandidatePool` now preserves the canonical exchangeInfo
    string verbatim.

**Real-WS smoke ladder (all PASS):**

```
5 min real WS    PASS
  ws_messages_received           = 30317
  ws_chains_emitted              = 12
  ingestion_errors               = 0
  rate_limit_429_count           = 0
  rate_limit_418_count           = 0
  ws_stale_count                 = 0

10 min real WS   PASS
  duration_seconds               = 608
  ws_messages_received           = 59644
  ws_chains_emitted              = 27
  ingestion_errors               = 0
  rate_limit_429_count           = 0
  rate_limit_418_count           = 0
  ws_stale_count                 = 0

1 h real WS (clean)  PASS
  duration_seconds               = 3600
  dry_run                        = false
  ws_real_transport              = true
  ws_messages_received           = 349134
  ws_chains_emitted              = 177
  ws_learning_ready_attached     = 177
  snapshots_emitted              = 177
  ingestion_errors               = 0
  HTTP 429 count                 = 0
  HTTP 418 count                 = 0
  rate_limit_ban                 = False
  ws_reconnect_count             = 0
  ws_staleness_ms_max            = 0
  ws_stale_count                 = 0
  ws_currently_stale             = False
```

**Persistence + export evidence:**

```
events.db
  events_count                   = 56644
  event-aggregation query        = passed without traceback
Phase 8.5 export
  outcome                        = generated successfully
  format                         = zip archive
Demon-coin discovery sanity
  EDENUSDT in radar top-symbols  = yes
  EDENUSDT in top event volume   = yes
```

**Safety flags held throughout the Phase 11C.1B acceptance run:**

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

**Acceptance conditions checked off:**

  - [x] Real WS 5 min run PASS.
  - [x] Real WS 10 min run PASS.
  - [x] Real WS 1 h run PASS.
  - [x] No HTTP 429 across the ladder.
  - [x] No HTTP 418 across the ladder.
  - [x] No `ws_stale` ticks across the ladder.
  - [x] No ingestion errors across the ladder.
  - [x] Phase 8.5 export zip generated successfully.
  - [x] `events.db` readable + event-aggregation query green.
  - [x] Phase 1 safety flags unchanged (`mode=paper`,
    `live_trading=False`, `right_tail=False`, `llm=False`,
    `exchange_live_orders=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`).

## Closed phase: Phase 11C.1C-A (ACCEPTED)

**Phase 11C.1C-A — Adaptive Candidate Regime & Strategy Selector
Contracts (PR #36).** Status: **ACCEPTED (closed 2026-05-22; PR
#36 merged; PR #37 docs closeout).** PR #36 was merged into
`main` and PR #37 closed out the Phase 11C.1C-A docs gate; the
smoke evidence below was accepted. Phase 11C.1C-A shipped the
**paper-only first version** of the data contracts + scoring +
selector + paper-only routing for the Adaptive Candidate Regime &
Strategy Selector. Phase 11C.1C-B is now **ACCEPTED (closed
2026-05-22; PR #38 merged into `main`, mergeCommit `ce4b6de`)** —
see "Closed phase: Phase 11C.1C-B (ACCEPTED)" below; Phase
11C.1C-C-A is **ACCEPTED (closed 2026-05-23; PR #40 merged
into `main`, mergeCommit `75d3c7c`)** — see "Closed phase:
Phase 11C.1C-C-A (ACCEPTED)" above; Phase 11C.1C-C-B is
**NEXT_ALLOWED / NOT_STARTED** (see "Open phase: Phase
11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" above); Phase 12
(live trading) remains **FORBIDDEN**.

## Closed phase: Phase 11C.1C-B (ACCEPTED)

**Phase 11C.1C-B — Adaptive Candidate Runtime Calibration & Early
Tail Discovery v0 (PR #38).** Status: **ACCEPTED (closed
2026-05-22; PR #38 merged into `main`, mergeCommit
`ce4b6de`).** PR #38 has been merged into `main`; the 30s
dry-run + 5min real public WS smoke evidence captured below
under "Phase 11C.1C-B acceptance evidence (closeout)" was
accepted. Phase 11C.1C-B shipped the **paper-only first
version** of the Adaptive Candidate Runtime Calibration & Early
Tail Discovery layer on top of the Phase 11C.1C-A contracts.
Phase 11C.1C-C-A is now **ACCEPTED (closed 2026-05-23; PR #40
merged into `main`, mergeCommit `75d3c7c`)** — see "Closed
phase: Phase 11C.1C-C-A (ACCEPTED)" above; Phase 11C.1C-C-B is
**NEXT_ALLOWED / NOT_STARTED** (see "Open phase: Phase
11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" above); Phase 12
(live trading) remains **FORBIDDEN**.

> **Phase 11C.1C-B acceptance does NOT authorise live trading.**
> **Phase 11C.1C-B does NOT authorise API keys.**
> **Phase 11C.1C-B does NOT authorise private endpoints.**
> **Phase 11C.1C-B does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-B does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-B does NOT authorise Phase 12.**

> Phase 11C.1C-B is **paper-mode only**. It is **NOT** live
> trading, **NOT** AI Learning, **NOT** complete Strategy
> Validation, **NOT** the full MFE/MAE processor, **NOT** real
> Telegram outbound, **NOT** real Binance trading API. Phase
> 12 (live trading) stays `FORBIDDEN`.

### Phase 11C.1C-B scope (shipped on `main` via PR #38)

  1. **Runtime calibration metrics** attached to every adaptive
     candidate context (Phase 8.5 ``learning_ready`` +
     ``AdaptiveCandidateContext`` + the six adaptive events):
     - ``candidate_first_seen_ts``
     - ``candidate_first_seen_price``
     - ``current_price``
     - ``price_change_since_first_seen``
     - ``quote_volume_acceleration_1m``
     - ``quote_volume_acceleration_5m``
     - ``price_acceleration_1m``
     - ``price_acceleration_5m``
     - ``volume_rank``
     - ``volume_rank_jump_5m``
     - ``distance_to_24h_high``
     - ``distance_from_first_seen``
     - ``freshness_score``
     - ``late_chase_risk``
     - ``early_tail_score``
  2. **Early Tail Discovery v0.** The candidate pool's capacity
     eviction does NOT discard candidates with high
     ``early_tail_score``. The radar surfaces volume-rank
     jumps, quote-volume accelerations, and price accelerations
     on EDEN / ALT / NEAR-style demon-coin starts EARLIER than
     Phase 11C.1B's flat radar score.
  3. **Stage calibration.** ``early`` + high volume expansion +
     high freshness MAY enter ``follow`` / ``pullback`` (paper /
     virtual). ``late`` / ``blowoff`` MUST NEVER upgrade to
     ``follow``. ``manipulation_risk`` high MUST ``reject`` or
     ``observe``.
  4. **Daily-report enhancements.** New fields:
     - ``top_early_tail_candidates``
     - ``top_late_chase_risk_candidates``
     - ``candidate_stage_counts`` (already present from
       Phase 11C.1C-A; carry forward unchanged)
     - ``strategy_mode_counts`` (already present from
       Phase 11C.1C-A; carry forward unchanged)
     - ``opportunity_score_distribution``
     - ``early_tail_score_top_symbols``
     - ``symbols_promoted_before_24h_top_move``
     - EDEN / ALT / NEAR style candidate examples when present
  5. **Event / export compatibility.** Every new field lands in
     ``EventRepository``, the Phase 8.5 learning-ready payload,
     the daily report, and the Phase 8.5 export. Phase 10A
     replay accepts the new fields without failure.

### Phase 11C.1C-B boundary (held throughout the entire scope)

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
| Strategy mode (incl. follow / pullback)     | paper / virtual; no real-trade authority |
| `early_tail_score`                          | descriptive only; protects from capacity eviction; NOT a real-trade authority |
| AI Learning                                 | NOT implemented              |
| Full MFE/MAE processor                      | NOT implemented (queue is a contract) |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-B explicitly forbids (inherited from Phase 11C.1C-A)

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
  - Promoting `early_tail_score` / `strategy_mode` (paper /
    virtual) to a real-trade authority.
  - Enabling AI Learning that auto-decides trades.
  - Implementing the full MFE/MAE processor (the queue stays a
    descriptive contract; the processor is reserved for Phase
    11C.1C-C).
  - Issuing any real order.
  - Entering Phase 12.

### Phase 11C.1C-B acceptance criteria (all met)

1. `pytest tests/unit/test_phase11c_1c_b_runtime_calibration.py`
   passed (12 brief-mandated tests).
2. `pytest tests/unit -k phase11c_` passed (257) with no
   regression vs. the post-PR-#37 main baseline.
3. The full `tests/` surface continued to pass (2231) with no
   regression vs. the post-PR-#37 main baseline.
4. The 30 s dry-run produced a `runtime_calibration` block (15
   fields) on every adaptive event and an `early_tail_score`
   per ACTIVE candidate; the daily report included the
   `## Phase 11C.1C-B` section.
5. The 5 min real public WS paper run recorded:
   - `dry_run=false`
   - `ws_real_transport=true`
   - `ws_messages_received=30526` (`> 0`)
   - `ws_chains_emitted=12` (`> 0`)
   - `runtime_calibration` block present on every adaptive event
   - `early_tail_score` generated per ACTIVE candidate
   - `top_early_tail_candidates` present in daily report
   - `top_late_chase_risk_candidates` present in daily report
   - `early_tail_score_top_symbols` present in daily report
   - `opportunity_score_distribution` present in daily report
   - `label_queue` remains contract-only
   - `rate_limit_429_count=0`
   - `rate_limit_418_count=0`
   - `rate_limit_ban=False`
   - `ws_stale_count=0`
   - `ingestion_errors=12` (explainable: sandbox-region
     geoblock HTTP 451 on Binance REST; NOT a 429/418/ban; WS
     pump ran cleanly throughout)
6. Every safety flag remained `False` after running the
   runtime-calibration path end-to-end.
7. No live trading.
8. No API key.
9. No private endpoint.
10. Phase 12 stayed `FORBIDDEN`.

## Closed phase: Phase 11C.1C-C-A (ACCEPTED)

**Phase 11C.1C-C-A — MFE / MAE Label Queue Runtime & Tail
Outcome Tracking (PR #40).** Status: **ACCEPTED (closed
2026-05-23; PR #40 merged into `main`, mergeCommit
`75d3c7c`).** PR #40 (branch
`feature/phase-11c1c-c-mfe-mae-label-queue-runtime`, code
commit `4889087`, docs-gate-fix commit `6d6044d`) has merged
into `main`; the operator-VPS 10 min real public WS smoke
evidence captured below under "Phase 11C.1C-C-A acceptance
evidence (closeout)" was accepted. Phase 11C.1C-C-A shipped
the **paper-only first runtime** that consumes the Phase
11C.1C-A `LABEL_QUEUE_ENQUEUED` contract and produces forward
MFE / MAE / `tail_label` outcomes per ACTIVE candidate over
five tracking windows (5m primary, 15m / 30m / 1h / 4h
secondary). It does NOT ship the deeper Strategy Validation
Lab, AI Learning, or Cluster Exposure Control — those are
reserved for Phase 11C.1C-C-B (see "Open phase: Phase
11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" below).

> **Phase 11C.1C-C-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-A acceptance does NOT authorise Phase 12.**
> **Phase 11C.1C-C-A acceptance does NOT authorise Phase
> 11C.1C-C-B kickoff bypassing the standard gate.**
> **`mfe_pct` / `mae_pct` / `tail_label` / `strategy_mode` MUST
> NEVER trigger a real trade.**

> Phase 11C.1C-C-A is **paper-mode only**. It is **NOT** live
> trading, **NOT** AI Learning, **NOT** the complete Strategy
> Validation Lab, **NOT** Cluster Exposure Control, **NOT**
> real Telegram outbound, **NOT** real Binance trading API.
> Phase 12 (live trading) remains `FORBIDDEN`.

### Phase 11C.1C-C-A scope (in PR #40)

  1. **`LabelQueueRuntime`** (`app/adaptive/label_runtime.py`)
     consuming the Phase 11C.1C-A `LABEL_QUEUE_ENQUEUED`
     contract and producing forward outcome labels per ACTIVE
     candidate. Pure helpers: `compute_pct_return`,
     `update_window_with_price`, `assign_tail_label_for_window`.
     Schema-versioned via
     `LABEL_TRACKING_SCHEMA_VERSION = "phase_11c_1c_c_a.label_tracking.v1"`.
  2. **Five tracking windows.** 5m primary; 15m / 30m / 1h / 4h
     secondary. Each window tracks MFE (max favourable excursion,
     %), MAE (max adverse excursion, %), `time_to_mfe`,
     `time_to_mae`, R-multiple flags
     (`reached_2r` / `reached_3r` / `reached_5r` / `reached_10r`)
     when `virtual_risk_unit_pct` is configured.
  3. **Tail label taxonomy (rule-based, no LLM).** Per window,
     once observation is complete, one of:
     `strong_tail` / `moderate_tail` / `weak_tail` /
     `fake_breakout` / `late_chase_failure` / `dumped` /
     `stopped_before_tail` / `unresolved` (default). All
     thresholds are configurable (R-multiples, fake_breakout,
     late_chase_failure, dumped, stopped_before_tail,
     missed_tail). `MISSED_TAIL_DETECTED` is emitted as an
     independent flag, not a tail_label value.
  4. **Six new event types** plumbed through `EventRepository`:
     `LABEL_TRACKING_STARTED`, `LABEL_WINDOW_UPDATED`,
     `LABEL_WINDOW_COMPLETED`, `TAIL_LABEL_ASSIGNED`,
     `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`. Each
     payload carries identity (`tracking_id` / `opportunity_id`
     / `scan_batch_id` / `symbol` / `source_event_id`) plus the
     `schema_version` stamp.
  5. **Idempotency + capacity guards.** `opportunity_id` index
     dedupes; `(symbol, candidate_first_seen_ts,
     first_seen_price)` is the fallback key.
     `max_pending_records` caps the queue. Records past
     `4h + grace_period_seconds` are auto-expired. Missing
     prices return `None`, never raise.
  6. **`WSRadarChainDriver` integration.** After emitting
     `LABEL_QUEUE_ENQUEUED`, the chain captures the `event_id`
     and calls `runtime.observe(adaptive, source_event_id)` so
     that a `LabelTrackingRecord` is created (idempotent) and
     price ticks advance MFE / MAE on every subsequent chain
     pass.
  7. **Daily-report enhancements.** New
     `DailyReportSnapshot` fields surface every brief-mandated
     metric: tracking-started / window-updated / window-completed
     / tail-label / missed-tail / fake-breakout counts;
     pending / completed / expired / unresolved record counts;
     `tail_label_distribution`; `reached_2r` /  `reached_3r` /
     `reached_5r` / `reached_10r` counts; outcomes by
     `early_tail` / `opportunity` / `strategy_mode` /
     `late_chase_risk` bucket; top-MFE / worst-MAE / missed-tail
     / fake-breakout symbol lists.
  8. **`scripts/run_public_market_paper.py`** instantiates
     `LabelQueueRuntime` from settings, ticks it on every loop
     iteration plus on shutdown, and threads
     `label_runtime_metrics` into the daily report.
  9. **Config schema** (`app/config/schema.py` +
     `app/config/defaults.yaml`): new `label_queue_runtime`
     YAML section with every threshold, `max_pending_records`,
     `grace_period_seconds`, and the five tracking windows.

### Phase 11C.1C-C-A boundary (must hold from day one; inherited)

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
| `mfe_pct` / `mae_pct` / `tail_label` /      | descriptive label only;       |
|   `strategy_mode`                           | MUST NEVER trigger a real     |
|                                             | trade                         |
| AI Learning                                 | NOT implemented              |
| Strategy Validation Lab (full)              | NOT implemented (reserved for Phase 11C.1C-C-B) |
| Cluster Exposure Control                    | NOT implemented (reserved for Phase 11C.1C-C-B) |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-C-A explicitly forbids (inherited verbatim)

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
  - Auto-retrying after a 418, switching endpoints to evade a
    418, rotating source IP to evade a 418.
  - Promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority.
  - Implementing the full Strategy Validation Lab.
  - Implementing Cluster Exposure Control.
  - Implementing AI Learning that auto-decides trades.
  - Issuing any real order.
  - Entering Phase 12.

### Phase 11C.1C-C-A acceptance gate (all met)

1. **Targeted test file** —
   `pytest tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`
   green. **Status: GREEN on PR branch (30 / 30 PASS).**
2. **Phase 11C focus filter** —
   `pytest tests/unit -k phase11c_` green with no regression
   vs. the post-PR-#38 main baseline of 257.
   **Status: GREEN on PR branch (287 / 287 PASS).**
3. **Full pytest** — `pytest tests/` green with no regression
   vs. the post-PR-#38 main baseline of 2231. **Status: GREEN
   on PR branch (2261 / 2261 PASS).**
4. **30 s dry-run smoke** — runner emits
   `LABEL_TRACKING_STARTED` per ACTIVE candidate and the 5m
   primary window stays `pending` (a 30s run is too short for
   the 5m window to complete). **Status: claimed by PR #40
   commit message; the dry-run path is exercised by the
   integration tests inside the targeted test file.**
5. **10 min real public WS smoke from operator VPS** —
   **PASSED.** The operator-VPS 10 min real WS smoke run from
   the `feature/phase-11c1c-c-mfe-mae-label-queue-runtime`
   branch at commit `6d6044d`
   (`python -m scripts.run_public_market_paper --duration
   10min --symbol-limit 5 --ws-first`) recorded, with the
   verbatim runner output captured below under "Phase
   11C.1C-C-A acceptance evidence (closeout)":
   - `duration_seconds=600.0`
   - `dry_run=false`
   - `ws_real_transport=true`
   - `ws_messages_received=56592` (`> 0`)
   - `LABEL_TRACKING_STARTED=19` (runner) / `36` (events.db)
     (`> 0`)
   - `LABEL_WINDOW_UPDATED=38` (runner) / `82` (events.db)
     (`> 0`)
   - `LABEL_WINDOW_COMPLETED=11` (runner) / `20` (events.db)
     (`> 0` — 5m primary window closed inside the 10 min run)
   - `TAIL_LABEL_ASSIGNED=11` (runner) / `20` (events.db)
     (`> 0`)
   - daily report contains `"Phase 11C.1C-C-A MFE / MAE Label
     Queue Runtime & Tail Outcome Tracking"`
   - `pending_label_records=8` /
     `completed_label_records=11` /
     `expired_label_records=0` /
     `unresolved_label_records=0`
   - `rate_limit_429_count=0`
   - `rate_limit_418_count=0`
   - `rate_limit_ban=False`
   - `ws_reconnect_count=0`
   - `ws_stale_count=0`
   - `ws_currently_stale=False`
   - `ingestion_errors=0`
   - `MISSED_TAIL_DETECTED=0` and `FAKE_BREAKOUT_DETECTED=0`
     are valid outcomes for a 10 min window over five seed
     symbols and are not gate-blocking
   - safety flags unchanged (`live_trading_enabled=False`,
     `right_tail_enabled=False`, `llm_enabled=False`,
     `exchange_live_order_enabled=False`,
     `trading_mode_paper=True`; no API key, no signed
     endpoint, no private websocket, no listenKey, no
     DeepSeek trade decision, no real Telegram outbound,
     Phase 12 remains FORBIDDEN)
6. **Safety regression test** — confirms that running the
   label-runtime path end-to-end leaves every Phase 1 safety
   flag at its locked value and that the runtime never emits
   `ORDER_*`, `POSITION_*`, `STOP_*`, or
   `TELEGRAM_MESSAGE_SENT` events. **Status: GREEN on PR
   branch (covered by `test_no_live_trading_flags_unchanged`
   and
   `test_label_runtime_does_not_open_position_or_authorise_trade`).**

The Kiro-side sandbox could not serve as the smoke host for
#5 because the same Binance-region HTTP 451 geoblock that was
recorded under "Phase 11C.1C-B acceptance evidence (closeout)"
still applies to the Kiro sandbox; the operator therefore ran
the 10 min real WS smoke from a Binance-reachable VPS, and
the verbatim transcript is filed below under "Phase
11C.1C-C-A acceptance evidence (closeout)". A sandbox WS
smoke would **not** have been authoritative evidence and was
**not** filed as such. PR #40 merged into `main` on
2026-05-23 (mergeCommit `75d3c7c`); this docs-only closeout
PR therefore flips Phase 11C.1C-C-A to **ACCEPTED**, mirroring
the PR #36 → PR #37 and PR #38 → PR #39 closeout pattern.

## Closed phase: Phase 11C.1C-C-B-A (ACCEPTED)

**Phase 11C.1C-C-B-A — Strategy Validation Lab v0 & Cluster
Exposure Control Contracts (PR #42).** Status: **ACCEPTED
(closed 2026-05-23; PR #42 merged into `main`, mergeCommit
`cc18047`).** PR #42 (branch
`feature/phase-11c1c-c-b-strategy-validation-cluster-control`,
PR-head commit `0bedcce`) merged into `main` on 2026-05-23
(UTC); the operator-VPS 10 min real public WS smoke evidence
captured below under §"Phase 11C.1C-C-B-A acceptance
evidence (operator-VPS 10 min real public WS smoke PASSED)"
was accepted. Phase 11C.1C-C-B-A shipped the **paper /
report-only first slice** of the deeper Phase 11C.1C-C-B
Strategy Validation Lab work on top of the Phase 11C.1C-C-A
`LabelTrackingRecord` outcomes; it ships the data contracts,
pure aggregators, and the `StrategyValidationRuntime` that
emits the seven new typed events, but it does **NOT** ship
the complete Strategy Validation Lab, AI Learning, automatic
parameter optimisation, reinforcement learning, or richer
cluster heuristics — those are reserved for Phase
11C.1C-C-B-B (see §"Open phase: Phase 11C.1C-C-B-B
(NEXT_ALLOWED / NOT_STARTED)" below).

> **Phase 11C.1C-C-B-A is paper / report only.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise Phase 11C.1C-C-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise Phase 12.**
> **Validation result / cluster action / `strategy_mode` /
> `suggested_cluster_action` / `mfe_pct` / `mae_pct` /
> `tail_label` cannot trigger real trading** — they are
> descriptive labels only; the Risk Engine remains the
> single trade-decision gate.
> **Phase 12 (live trading) remains FORBIDDEN.**

### Phase 11C.1C-C-B-A scope (PR #42)

  - **Data contracts** (`app/adaptive/strategy_validation.py`):
    `StrategyValidationSample`, `StrategyValidationWindowStats`,
    `StrategyModeValidationStats`,
    `CandidateStageValidationStats`,
    `OpportunityScoreBucketStats`,
    `EarlyTailScoreBucketStats`, `TailLabelDistribution`,
    `ClusterLeaderValidationStats`,
    `ClusterExposureAssessment`, `StrategyValidationReport`.
  - **Pure aggregators**:
    `build_strategy_validation_sample`,
    `aggregate_by_strategy_mode` (with `observe` + `reject`
    cohorts surfaced even when empty),
    `aggregate_by_candidate_stage` (with `dumped` flagged as
    not-a-long-opportunity),
    `aggregate_by_opportunity_score_bucket` (`0-49 / 50-64 /
    65-79 / 80-100`),
    `aggregate_by_early_tail_score_bucket` (`0-24 / 25-49 /
    50-74 / 75-100`),
    `aggregate_tail_label_distribution`,
    `evaluate_cluster_leader_performance`,
    `assess_cluster_exposure`,
    `build_strategy_validation_report`.
  - **Runtime**
    (`app/adaptive/strategy_validation_runtime.py`):
    `StrategyValidationRuntimeConfig` + `StrategyValidationRuntime`
    (idempotent per `opportunity_id`).
  - **Seven new event types**:
    `STRATEGY_VALIDATION_SAMPLE_CREATED`,
    `STRATEGY_VALIDATION_REPORT_GENERATED`,
    `STRATEGY_MODE_VALIDATED`, `CANDIDATE_STAGE_VALIDATED`,
    `SCORE_BUCKET_VALIDATED`, `CLUSTER_EXPOSURE_ASSESSED`,
    `CLUSTER_LEADER_VALIDATED`. Schema version label
    `phase_11c_1c_c_b_a.strategy_validation.v1`.
  - **Wiring**: `WSRadarChainDriver` accepts a new
    `strategy_validation_runtime` kwarg; runner instantiates
    from `settings.strategy_validation` and flushes a final
    report on shutdown.
  - **Daily-report enhancements**: new section
    `## Phase 11C.1C-C-B-A Strategy Validation Lab v0 &
    Cluster Exposure Control Contracts` with paper /
    report-only boundary preamble + every brief-mandated
    metric.
  - **Configuration**: `StrategyValidationSection` Pydantic
    schema; `strategy_validation:` block in
    `app/config/defaults.yaml`; `Settings.strategy_validation`
    accessor.
  - **Cluster actions** (paper / report only):
    `leader_only` / `observe_followers` / `reject_cluster` /
    `no_action`. **MUST NEVER trigger a real trade.**
  - **Tests**: 25/25 PASS (brief-mandated cases); 312/312
    phase11c\_ tests PASS; 2286/2286 full pytest PASS on the PR
    branch (no regression vs. post-PR-#41 main 2261 baseline).

### Phase 11C.1C-C-B-A inherited boundary (held from day one)

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
| `suggested_cluster_action`                  | paper / report only;          |
|   (`leader_only` / `observe_followers` /    | MUST NEVER trigger a real     |
|   `reject_cluster` / `no_action`)           | trade                         |
| `mfe_pct` / `mae_pct` / `tail_label` /      | descriptive label only;       |
|   `strategy_mode` / `early_tail_score` /    | MUST NEVER trigger a real     |
|   `MISSED_TAIL_DETECTED` /                  | trade                         |
|   `FAKE_BREAKOUT_DETECTED` /                |                               |
|   `STRATEGY_VALIDATION_*` events            |                               |
| AI Learning                                 | NOT implemented              |
| Automatic parameter optimisation            | NOT implemented              |
| Reinforcement learning                      | NOT implemented              |
| Phase 12 (live trading)                     | FORBIDDEN                    |

### Phase 11C.1C-C-B-A explicitly forbidden (inherited verbatim)

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Auto-retrying after a 418, switching endpoints to evade a
    418, rotating source IP to evade a 418.
  - Promoting any paper / virtual signal (including the new
    `STRATEGY_VALIDATION_*` events,
    `suggested_cluster_action`, cohort stats, validation
    samples) to a real-trade authority.
  - Implementing AI Learning that auto-decides trades.
  - Implementing automatic parameter optimisation that
    self-modifies the runtime configuration.
  - Implementing reinforcement learning that drives trade
    decisions.
  - Issuing any real order.
  - Entering Phase 12.

### Phase 11C.1C-C-B-A acceptance gate (status: ALL GATES MET; PR #42 merged into `main`)

  - `python -m pytest tests/unit/test_phase11c_1c_c_b_strategy_validation.py -q`
    → 25/25 PASS.
  - `python -m pytest tests/unit/ -k "phase11c_" -q`
    → 312/312 PASS, no regression.
  - `python -m pytest tests/ -q`
    → 2286/2286 PASS, no regression.
  - 30 s dry-run smoke is **contract-only** (smallest Phase
    11C.1C-C-A tracking window is 5 min; cannot complete in
    30 s); the runner emits an empty-but-well-formed
    `STRATEGY_VALIDATION_REPORT_GENERATED` so the daily report
    still renders the new section.
  - **Operator-VPS 10 min real public WS smoke PASSED** on
    2026-05-23 against PR #42 head (commit `0bedcce`;
    branch
    `feature/phase-11c1c-c-b-strategy-validation-cluster-control`).
    The Kiro-side sandbox cannot host this smoke
    (Binance-region HTTP 451 geoblock — historical context;
    same as the Phase 11C.1C-B / Phase 11C.1C-C-A closeouts).
    The verbatim runner output + the authoritative SQLite
    event-count query are filed under §"Phase 11C.1C-C-B-A
    acceptance evidence (operator-VPS 10 min real public WS
    smoke PASSED)" below. PR #42 has merged into `main`
    (mergeCommit `cc18047`); the smoke evidence above was
    accepted; this docs-only closeout PR therefore flips
    Phase 11C.1C-C-B-A to **ACCEPTED** in the closed-phases
    table at the top of this document, mirroring the PR #36
    → PR #37, PR #38 → PR #39, and PR #40 → PR #41 closeout
    pattern.

## Open phase: Phase 11C.1C-C-B-B (NEXT_ALLOWED / NOT_STARTED)

**Phase 11C.1C-C-B-B — Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up.** Status:
**NEXT_ALLOWED / NOT_STARTED.** Phase 11C.1C-C-B-A (PR #42)
merged into `main` on 2026-05-23 (mergeCommit `cc18047`); the
operator-VPS 10 min real public WS smoke evidence under
§"Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10
min real public WS smoke PASSED)" was accepted; Phase
11C.1C-C-B-A is therefore **ACCEPTED**, and Phase
11C.1C-C-B-B is now **NEXT_ALLOWED**. No implementation has
started in this repo state. **Phase 11C.1C-C-B-A acceptance
does NOT authorise Phase 11C.1C-C-B-B kickoff bypassing the
standard gate.** Phase 11C.1C-C-B-B will require its own
kickoff PR, brief, scope, boundary table, forbidden list,
and acceptance evidence and inherits every Phase 1 / 11C.1B
/ 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A forbidden
item verbatim.

> **Phase 11C.1C-C-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-A acceptance does NOT authorise Phase 12.**
> **Validation result / cluster action / `strategy_mode` /
> `suggested_cluster_action` / `mfe_pct` / `mae_pct` /
> `tail_label` cannot trigger real trading** — they are
> descriptive labels only; the Risk Engine remains the
> single trade-decision gate.
> **Phase 12 (live trading) remains FORBIDDEN.**

## Phase 11C.1C-C-A acceptance evidence (closeout)

> The transcript below is the verbatim runner / events.db
> output captured from the operator-VPS 10 min real public WS
> smoke run against the PR #40 branch
> (`feature/phase-11c1c-c-mfe-mae-label-queue-runtime`) at
> commit `6d6044d`. The Kiro-side sandbox could not host this
> smoke (Binance-region HTTP 451 geoblock; same as the Phase
> 11C.1C-B closeout), so the operator ran it from a
> Binance-reachable VPS. **The smoke PASSED and was accepted
> as Phase 11C.1C-C-A acceptance evidence.**
>
> PR #40 merged into `main` on 2026-05-23 (mergeCommit
> `75d3c7c`); Phase 11C.1C-C-A is now recorded as **ACCEPTED**
> in the closed-phases table at the top of this document and
> in the `## Closed phase: Phase 11C.1C-C-A (ACCEPTED)`
> section above. This docs-only closeout PR mirrors the PR
> #36 → PR #37 and PR #38 → PR #39 closeout pattern.

```
branch                          : feature/phase-11c1c-c-mfe-mae-label-queue-runtime
commit                          : 6d6044d
host                            : operator VPS (Binance-reachable region)
command                         : python -m scripts.run_public_market_paper \
                                    --duration 10min --symbol-limit 5 --ws-first

# WS / runner-level metrics
duration_seconds                = 600.0
uptime                          = 608s
dry_run                         = false
ws_real_transport               = true
ws_messages_received            = 56592
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

# Phase 11C.1C-C-A label-runtime metrics (runner / daily report)
LABEL_TRACKING_STARTED count    = 19
LABEL_WINDOW_UPDATED count      = 38
LABEL_WINDOW_COMPLETED count    = 11
TAIL_LABEL_ASSIGNED count       = 11
MISSED_TAIL_DETECTED count      = 0
FAKE_BREAKOUT_DETECTED count    = 0
pending_label_records           = 8
completed_label_records         = 11
expired_label_records           = 0
unresolved_label_records        = 0

# events.db SQLite confirmation
LABEL_TRACKING_STARTED          | 36
LABEL_WINDOW_UPDATED            | 82
LABEL_WINDOW_COMPLETED          | 20
TAIL_LABEL_ASSIGNED             | 20

# Safety boundary (held end-to-end)
exchange_live_order_enabled     = False
live_trading_enabled            = False
llm_enabled                     = False
right_tail_enabled              = False
trading_mode_paper              = True
no live trading                 = confirmed
no API key                      = confirmed
no signed endpoint              = confirmed
no private websocket            = confirmed
no listenKey                    = confirmed
no DeepSeek trade decision      = confirmed
no real Telegram outbound       = confirmed
Phase 12                        = FORBIDDEN (gate unchanged)
```

The runner-level event counters and the events.db SQLite
counts diverge (e.g. `LABEL_TRACKING_STARTED=19` runner vs.
`36` events.db) because the runner snapshots its in-memory
aggregates at the shutdown tick while events.db captures every
emission across the full 608 s uptime including the
chain-passes that fired after the runner's last aggregate
snapshot. Both views satisfy the brief's `> 0` thresholds and
corroborate the chain-driver integration end-to-end.

`MISSED_TAIL_DETECTED=0` and `FAKE_BREAKOUT_DETECTED=0` are
valid outcomes for a 10 min window over five seed symbols and
are not gate-blocking; they record that no candidate hit the
missed-tail / fake-breakout thresholds during this particular
run.

The 5m primary tracking window closed inside the 10 min run
(11 runner / 20 events.db `LABEL_WINDOW_COMPLETED`), matching
the brief; 8 records remained `pending` (correctly waiting on
the longer 15m / 30m / 1h / 4h secondary windows) and 0
records were `expired` or `unresolved`.

Phase 1 safety lock held end-to-end across the smoke run; no
real order, no signed endpoint call, no private WebSocket
connection, no listenKey allocation, no DeepSeek trade
decision, no real Telegram outbound, and Phase 12 stayed
**FORBIDDEN**.

## Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)

> The transcript below is the verbatim runner output and the
> authoritative `events.db` SQLite query captured from the
> operator-VPS 10 min real public WS smoke run against the
> PR #42 branch
> (`feature/phase-11c1c-c-b-strategy-validation-cluster-control`)
> at commit `0bedcce`. The Kiro-side sandbox could not host
> this smoke (Binance-region HTTP 451 geoblock — historical
> context, same as the Phase 11C.1C-B / Phase 11C.1C-C-A
> closeouts; this is **not** the current blocker), so the
> operator ran it from a Binance-reachable VPS. **The smoke
> PASSED and was accepted as Phase 11C.1C-C-B-A acceptance
> evidence.**
>
> PR #42 merged into `main` on 2026-05-23 (mergeCommit
> `cc18047`); Phase 11C.1C-C-B-A is now recorded as
> **ACCEPTED** in the closed-phases table at the top of this
> document and in the `## Closed phase: Phase 11C.1C-C-B-A
> (ACCEPTED)` section above. This docs-only closeout PR
> mirrors the PR #36 → PR #37, PR #38 → PR #39, and PR #40 →
> PR #41 closeout pattern.
>
> Phase 11C.1C-C-B-B remains **NEXT_ALLOWED / NOT_STARTED**;
> Phase 11C.1C-C-B-A acceptance does **NOT** authorise Phase
> 11C.1C-C-B-B kickoff bypassing the standard gate; Phase 12
> remains **FORBIDDEN**.

```
branch                          : feature/phase-11c1c-c-b-strategy-validation-cluster-control
commit                          : 0bedcce
host                            : operator VPS (Binance-reachable region)
command                         : python -m scripts.run_public_market_paper \
                                    --duration 10min --symbol-limit 5 --ws-first

# Note on banner flag
# The runner does NOT support --emit-banner. The banner is emitted
# by default; pass --no-banner to suppress.

# WS / runner-level metrics
duration_seconds                = 600.0
uptime                          = 611s
dry_run                         = false
ws_real_transport               = true
ws_messages_received            = 76324
ws_chains_emitted               = 27
learning_ready_attached         = 27
snapshots_emitted               = 27
ingestion_errors                = 0

# Rate-limit / health
HTTP 429 count                  = 0
HTTP 418 count                  = 0
rate_limit_ban                  = False
ws_reconnect_count              = 0
ws_stale_count                  = 0
ws_currently_stale              = False

# Strategy Validation events (authoritative, from events.db SQLite query
# `SELECT event_type, COUNT(*) FROM events GROUP BY event_type;`,
# captured AFTER shutdown flush)
STRATEGY_VALIDATION_SAMPLE_CREATED       = 24
STRATEGY_VALIDATION_REPORT_GENERATED     =  1
STRATEGY_MODE_VALIDATED                  =  4
CANDIDATE_STAGE_VALIDATED                =  5
SCORE_BUCKET_VALIDATED                   =  8
CLUSTER_EXPOSURE_ASSESSED                =  1
CLUSTER_LEADER_VALIDATED                 =  1

# Daily-report content
daily_report_section_present    = "Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster Exposure Control Contracts"

# Non-empty cohort lines from the daily report
strategy_mode=reject                  n=24
candidate_stage=early                 n=24
opportunity_score_bucket=0-49         n=13
opportunity_score_bucket=50-64        n=11
early_tail_score_bucket=0-24          n=24
cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action

# tail_label_distribution (10 min run; 5m primary windows still in-flight)
tail_label_distribution         = unresolved x 24

# Safety boundary (Phase 1 lock unchanged end-to-end)
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

### Acceptance criteria — every gate met

  - `dry_run = false` ✅
  - `ws_real_transport = true` ✅
  - `ws_messages_received = 76324` (≥ 5000) ✅
  - `ws_chains_emitted = 27` (≥ 1) ✅
  - `STRATEGY_VALIDATION_SAMPLE_CREATED = 24` (≥ 1) ✅
  - `STRATEGY_VALIDATION_REPORT_GENERATED = 1` (≥ 1) ✅
  - `STRATEGY_MODE_VALIDATED = 4` ✅ (the four canonical
    modes `follow` / `pullback` / `observe` / `reject` are
    emitted even when a cohort is empty — observed `reject`
    cohort `n=24`)
  - `CANDIDATE_STAGE_VALIDATED = 5` ✅
  - `SCORE_BUCKET_VALIDATED = 8` ✅
  - `CLUSTER_EXPOSURE_ASSESSED = 1` ✅
  - `CLUSTER_LEADER_VALIDATED = 1` ✅
  - Daily report contains the new Phase 11C.1C-C-B-A section
    with non-empty `strategy_mode` and `candidate_stage`
    cohort lines ✅
  - Safety flags unchanged (`mode=paper`,
    `live_trading=False`, `right_tail=False`, `llm=False`,
    `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`) ✅
  - `HTTP 429 count = 0`, `HTTP 418 count = 0`,
    `rate_limit_ban = False` ✅
  - `ws_reconnect_count = 0`, `ws_stale_count = 0`,
    `ws_currently_stale = False`, `ingestion_errors = 0` ✅

The 5 m primary tracking windows that opened during the 10
min run had not all completed by shutdown, so `unresolved`
is the expected dominant `tail_label` for a 10 min run; the
`STRATEGY_VALIDATION_SAMPLE_CREATED = 24` count confirms the
runtime fired end-to-end on real Binance public WS data, and
the `STRATEGY_VALIDATION_REPORT_GENERATED = 1` event records
the shutdown flush.

Phase 1 safety lock held end-to-end across the smoke run;
no real order, no signed endpoint call, no private
WebSocket connection, no listenKey allocation, no DeepSeek
trade decision, no real Telegram outbound, and Phase 12
stayed **FORBIDDEN**.

## Phase 11C.1C-B acceptance evidence (closeout)

> The smoke-evidence transcript below is the verbatim runner
> output captured from the PR #38 branch at acceptance time.
> The banner string `Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b`
> is the literal `__phase__` / `__version__` value that the
> Python runtime printed on `main` when the smoke runs were
> performed; it is preserved here because rewriting verbatim
> historical evidence would mis-state what the runner actually
> printed. Bumping the banner to drop the trailing `-IN_REVIEW`
> suffix would require a runtime-code change to
> `app/__init__.py` and is therefore reserved for a separate
> follow-up code PR; this docs-only closeout intentionally does
> NOT touch any runtime code. The Phase 11C.1C-B gate state
> recorded in the closed-phases table at the top of this
> document and in the `## Closed phase: Phase 11C.1C-B
> (ACCEPTED)` section above is the authoritative one and reads
> **ACCEPTED**.

```
test_phase11c_1c_b_runtime_calibration.py  12 passed   (brief-mandated cases)
tests/unit/ -k phase11c_                  257 passed   (no regression vs. post-PR-#37 main)
tests/                                    2231 passed   (no regression vs. post-PR-#37 main)

30 s dry-run smoke
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 30s --symbol-limit 3 --dry-run \
                                          --poll-interval-seconds 1
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
                                        (banner now reflects the
                                        post-bump label
                                        `Phase 11C.1C-B-IN_REVIEW
                                        v1.4.0a11c.1c.b`; the
                                        underlying smoke numerics
                                        are unchanged because the
                                        bump is a code-label-only
                                        change.)
  dry_run                               True
  ws_real_transport                     False (in-process pump as expected
                                                under --dry-run)
  duration_seconds                      30
  iterations                            30
  chains_emitted                        3
  ws_chains_emitted                     60
  ws_messages_received                  122 (in-process pump)
  ws_risk_rejected                      60
  learning_ready_attached               3
  ws_learning_ready_attached            60
  snapshots_emitted                     3
  radar_candidates_seen                 60
  candidate_pool_size_max               2
  MARKET_REGIME_ASSESSED                fired per ACTIVE candidate
  CANDIDATE_STAGE_CLASSIFIED            fired per ACTIVE candidate
  OPPORTUNITY_SCORED                    fired per ACTIVE candidate
  STRATEGY_MODE_SELECTED                fired per ACTIVE candidate
  CLUSTER_CONTEXT_ATTACHED              fired per ACTIVE candidate
  LABEL_QUEUE_ENQUEUED                  fired per ACTIVE candidate
  runtime_calibration block             present on every adaptive event
                                        (15 fields verified)
  early_tail_score                      computed per ACTIVE candidate
  daily report                          contains "## Phase 11C.1C-B Adaptive
                                        Candidate Runtime Calibration &
                                        Early Tail Discovery v0"
  top_early_tail_candidates             present
  top_late_chase_risk_candidates        present (10 entries)
  early_tail_score_top_symbols          present (EDEN/ALT/NEAR slot)
  opportunity_score_distribution        present (50-60 x30, 70-80 x30)
  label_queue                           contract-only (no MFE/MAE processor)
  events.db readable                    yes
  ingestion_errors                      57  (REST budget-exhaustion refusals
                                              from the in-process governor;
                                              NOT a 429, NOT a 418, NOT a
                                              ban; expected under --dry-run
                                              once the bootstrap weight is
                                              consumed)
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False
  rate_limit_protection_triggered       False
  ws_stale_count                        0
  ws_reconnect_count                    0
  ws_data_degraded_ticks                0
  used_weight_1m_max                    0

5 min real public WS smoke (--ws-first, no --dry-run)
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 5min --symbol-limit 5 --ws-first \
                                          --symbols BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
                                        (banner now reflects the
                                        post-bump label; the
                                        underlying smoke numerics
                                        are unchanged because the
                                        bump is a code-label-only
                                        change.)
  dry_run                               False
  ws_real_transport                     True (real RFC 6455 stdlib transport;
                                              wss://fstream.binance.com routed
                                              PUBLIC + MARKET endpoints)
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
  MARKET_REGIME_ASSESSED count          72 (events.db)
  CANDIDATE_STAGE_CLASSIFIED count      72 (events.db)
  OPPORTUNITY_SCORED count              72 (events.db)
  STRATEGY_MODE_SELECTED count          72 (events.db)
  CLUSTER_CONTEXT_ATTACHED count        72 (events.db)
  LABEL_QUEUE_ENQUEUED count            72 (events.db)
  PRE_ANOMALY_DETECTED                  87
  ANOMALY_DETECTED                      87
  STATE_TRANSITION                      87
  RISK_REJECTED                         87 (`stop_unconfirmed` x24 + others)
  PUBLIC_WS_CONNECTED                   2
  PUBLIC_WS_DISCONNECTED                2
  runtime_calibration block             present on every adaptive event
                                        (15 fields verified)
  early_tail_score                      generated per ACTIVE candidate
  top_early_tail_candidates             present in daily report
                                        (3 entries: BEATUSDT 13.98, BEATUSDT
                                         4.09, NEARUSDT 0.06)
  top_late_chase_risk_candidates        present in daily report
                                        (8 entries: SOPHUSDT 17.71, PLAYUSDT
                                         16.72, WIFUSDT 14.76, SYRUPUSDT
                                         14.33, BEATUSDT 13.86 / 12.80,
                                         PROMPTUSDT 9.39, NEARUSDT 1.68)
  early_tail_score_top_symbols          present in daily report
                                        (EDEN/ALT/NEAR slot: NEARUSDT 0.06)
  opportunity_score_distribution        present in daily report
                                        (40-50 x7, 50-60 x3, 60-70 x2)
  symbols_promoted_before_24h_top_move  0 (chain), 0 (pool)
  early_tail_protect_threshold          60.00 (DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD)
  label_queue                           contract-only (LABEL_QUEUE_ENQUEUED
                                        emitted; no MFE/MAE processor)
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False
  rate_limit_protection_triggered       False
  ws_stale_count                        0
  ws_reconnect_count                    0
  ws_currently_stale                    False
  ws_data_degraded_ticks                0
  used_weight_1m_max                    0
  public_endpoint_calls                 0  (REST fully geo-blocked at the
                                            sandbox edge; see ingestion_errors
                                            note below)
  ingestion_errors                      12  (explainable: sandbox-region
                                              geo-block on Binance REST
                                              `fapi.binance.com` returned
                                              HTTP 451 for the active-head
                                              detail REST ladder
                                              (`/fapi/v1/exchangeInfo`,
                                              `/fapi/v1/aggTrades`,
                                              `/fapi/v1/depth`,
                                              `/fapi/v1/fundingRate`,
                                              `/fapi/v1/openInterest`,
                                              `/fapi/v1/premiumIndex`,
                                              `/fapi/v1/ticker/bookTicker`).
                                              SymbolUniverse fell back to the
                                              admit-all empty universe per
                                              the documented fallback path.
                                              All 146 transport-level 451s
                                              are HTTP 451 (region geoblock),
                                              NOT a 429, NOT a 418, NOT a
                                              Binance ban, NOT a TLS / WS
                                              issue. The real WS pump
                                              (`wss://fstream.binance.com/public/stream`
                                              + `/market/stream`) ran cleanly
                                              throughout: 30526 frames, 0
                                              stales, 0 reconnects.)
  events.db readable                    yes (855 events; all six Phase
                                              11C.1C-A adaptive event types
                                              present at 72 each)
  Phase 8.5 export                      generated successfully
                                        (`ama_rt_test_data_..._export_e.zip`,
                                         438711 bytes, 855 events, 750
                                         opportunities, 87 rejections, 87
                                         state transitions, redaction
                                         applied)
```

Safety flags held throughout the Phase 11C.1C-B acceptance smoke
runs (30s dry-run + 5min real WS):

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

## Phase 11C.1C-A acceptance evidence (closeout)

**Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector
Contracts (PR #36, ACCEPTED).** Phase 11C.1C-A is the
**paper-only first version** of the data contracts + scoring +
selector + paper-only routing for the Adaptive Candidate Regime &
Strategy Selector. PR #36 has merged into `main` and PR #37
closed the docs gate. The PR shipped:

  - new `app/adaptive/` package with
    `MarketRegimeAssessment` / `CandidateStageAssessment` /
    `OpportunityScore` / `StrategyModeDecision` / `ClusterContext`
    / `LabelQueueContract` / `AdaptiveCandidateContext` value
    objects + the cheap `assess_market_regime` /
    `classify_candidate_stage` / `compute_opportunity_score` /
    `select_strategy_mode` / `build_cluster_context` /
    `build_label_queue_contract` /
    `build_adaptive_candidate_context` pure functions;
  - six new EventType entries (`MARKET_REGIME_ASSESSED` /
    `CANDIDATE_STAGE_CLASSIFIED` / `OPPORTUNITY_SCORED` /
    `STRATEGY_MODE_SELECTED` / `CLUSTER_CONTEXT_ATTACHED` /
    `LABEL_QUEUE_ENQUEUED`) emitted alongside the existing
    Phase 11C.1B WS-radar event chain;
  - Phase 8.5 `LearningReadyContext` extended with an optional
    `adaptive_candidate` field;
  - Phase 8.5 `VirtualTradePlan` extended with eleven optional
    adaptive fields (`opportunity_score`, `opportunity_grade`,
    `candidate_stage`, `strategy_mode`, `cluster_id`,
    `cluster_leader`, `label_queue_pending`, `follow_allowed`,
    `pullback_allowed`, `observe_only`, `reject_reason`);
  - `WSRadarChainDriver` builds and emits the adaptive context per
    ACTIVE candidate, attaches it to `learning_ready`, and exposes
    `adaptive_metrics_payload()` for the runner / daily report;
  - `DailyReportBuilder` accepts a new `adaptive_metrics` kwarg
    and renders the
    `## Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector`
    Markdown section.

### Phase 11C.1C-A boundary (held throughout the entire scope)

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
| Adaptive event emission                     | descriptive only; never opens an order |
| MFE/MAE processor                           | NOT implemented (queue is a contract) |
| AI Learning                                 | NOT implemented              |
| Phase 12                                    | FORBIDDEN                    |

### Phase 11C.1C-A acceptance criteria (all met)

1. `pytest tests/unit/test_phase11c_1c_a_adaptive_candidate.py`
   passed (31 brief-mandated tests).
2. The full Phase 11C test surface continued to pass; total
   `tests/unit/` test count after PR #36: **2219 passed**.
3. The 30 s dry-run produced an `AdaptiveCandidateContext` for
   every active candidate and wrote the six adaptive events into
   `events.db`.
4. The 5 min real-WS paper run produced adaptive fields on every
   chain (no regression in the Phase 11C.1B 5min smoke ladder).
5. The Phase 8.5 export zip + Phase 10A replay accepted the six
   new event types without failure.
6. Every safety flag remained `False` after running the adaptive
   path end-to-end.
7. No live trading.
8. No API key.
9. No private endpoint.
10. Phase 12 stayed `FORBIDDEN`.

### Phase 11C.1C-A acceptance smoke evidence (closeout)

```
test_phase11c_1c_a_adaptive_candidate.py  31 PASS
tests/unit/                               2219 PASS  (no regression; PR #36 branch)

30 s dry-run smoke
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 30s --symbol-limit 3 --dry-run
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
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
  daily report                          contains "## Phase 11C.1C-A Adaptive
                                        Candidate Regime & Strategy Selector"
  events.db readable                    yes
  Phase 8.5 export                      generated successfully (zip)
  ingestion_errors                      0
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False

5 min real public WS smoke (--ws-first, no --dry-run)
  command:                              python -m scripts.run_public_market_paper \
                                          --duration 5min --symbol-limit 5 --ws-first \
                                          --symbols BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT
  banner phase tag                      Phase 11C.1C-B-IN_REVIEW v1.4.0a11c.1c.b
  dry_run                               False
  ws_real_transport                     True (real RFC 6455 stdlib transport;
                                              wss://fstream.binance.com routed
                                              PUBLIC + MARKET endpoints)
  duration_seconds                      301
  iterations                            5
  ws_messages_received                  32842
  ws_chains_emitted                     12
  candidate_pool_size_max               20
  radar_candidates_seen                 3043
  MARKET_REGIME_ASSESSED count          12
  CANDIDATE_STAGE_CLASSIFIED count      12
  OPPORTUNITY_SCORED count              12
  STRATEGY_MODE_SELECTED count          12
  CLUSTER_CONTEXT_ATTACHED count        12
  LABEL_QUEUE_ENQUEUED count            12
  adaptive_metrics section in report    present
  label_queue_enqueued                  12
  rate_limit_429_count                  0
  rate_limit_418_count                  0
  rate_limit_ban                        False
  ws_stale_count                        0
  ws_reconnect_count                    0
  ws_currently_stale                    False
  ingestion_errors                      12  (explainable: sandbox-region
                                              geo-block on REST fapi.binance.com
                                              returned HTTP 451 for active-head
                                              detail REST and exchangeInfo
                                              bootstrap; SymbolUniverse fell
                                              back to the empty admit-all
                                              universe per the documented
                                              fallback. NOT a 429, NOT a 418,
                                              NOT a Binance ban, NOT an
                                              ingestion bug. The real WS pump
                                              ran cleanly throughout.)
  events.db readable                    yes (270 events; 14 each of the six
                                              adaptive event types across the
                                              30s + 5min runs)
  Phase 8.5 export                      generated successfully (zip,
                                              119699 bytes)
```

Safety flags held throughout the Phase 11C.1C-A pre-merge smoke
runs (30s dry-run + 5min real WS):

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

## Closed phase: Phase 11C.1B (historical reference)

(See "Phase 11C.1B acceptance summary" above for the full closeout
record.)

## Open phase (legacy): Phase 11C.1C

The original "Phase 11C.1C" placeholder has been split into
sequential sub-phases. Phase 11C.1C-A is **ACCEPTED (closed
2026-05-22; PR #36 merged; PR #37 docs closeout)**. Phase
11C.1C-B (Adaptive Candidate Runtime Calibration & Early Tail
Discovery v0) is **ACCEPTED (closed 2026-05-22; PR #38 merged
into `main`, mergeCommit `ce4b6de`)** — see "Closed phase: Phase
11C.1C-B (ACCEPTED)" above. Phase 11C.1C-C-A (MFE / MAE Label
Queue Runtime & Tail Outcome Tracking) is **ACCEPTED (closed
2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`)**
— see "Closed phase: Phase 11C.1C-C-A (ACCEPTED)" above. Phase
11C.1C-C-B (Adaptive Candidate Strategy Validation Lab &
Cluster Exposure Control) is **NEXT_ALLOWED / NOT_STARTED** —
see "Open phase: Phase 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)"
above. Phase 12 (live trading) remains **FORBIDDEN**.

### Phase 11C.1C boundary (must hold from day one)

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

### Phase 11C.1C explicitly forbids (inherited from Phase 11C.1B)

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
  - Auto-retrying after a 418, switching endpoints to evade a 418,
    rotating source IP to evade a 418.
  - Introducing a Strategy Selector with live-trading authority.
  - Enabling AI Learning that auto-decides trades.
  - Entering Phase 12.

### Phase 11C.1C acceptance gate (placeholder)

To be filled in by the Phase 11C.1C kickoff PR. At minimum the gate
will require:

  1. The Phase 1 safety lock unchanged.
  2. A real-WS smoke ladder analogous to Phase 11C.1B's 5min / 10min
     / 1h ladder, with zero 429 / 418 / stale / ingestion errors.
  3. Adaptive candidate-regime / strategy-selector decisions emitted
     as typed events into `events.db` with a Phase 8.5
     `LearningReadyContext`, but **without** authority to issue real
     orders.
  4. A source-tree audit refusing any third-party HTTP / WebSocket /
     SDK / LLM / Telegram / trading-API import on the Phase 11C.1C
     surface.
  5. The four `ExchangeClientBase` write surfaces still raise
     `SafeModeViolation` after every Phase 11C.1C run.

## Closed phase: Phase 11C.1B

**Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar (PR-B).**
Phase 11C.1A (PR-A) shipped the rate-limit governor and capped per-loop
REST detail; the trade-off was that the runner could see only the
symbols the bootstrap already knew about. PR-B adds the WebSocket-first
all-market radar so the runner can discover demon coins (妖币) without
per-symbol REST detail polling. The goal is not to lower discovery
capability - it is to *raise* discovery throughput while keeping REST
pressure near zero.

PR-B subscribes to FIVE public Binance WebSocket streams only,
routed through the documented public + market USDⓈ-M Futures
WebSocket endpoints:

  - PUBLIC route (`wss://fstream.binance.com/public/stream`):
    - `!bookTicker`
  - MARKET route (`wss://fstream.binance.com/market/stream`):
    - `!ticker@arr`
    - `!miniTicker@arr`
    - `!markPrice@arr`
    - `!forceOrder@arr`

PR-B does NOT subscribe to `listenKey`, the user data stream, the
trading WebSocket API, the `/private` routed surface, or any
other private WebSocket. The default WS transport refuses to open
a real socket (`NotImplementedError`); the in-process pump is
wired under `--dry-run`; **the real-network stdlib WS adapter
(`StdlibPublicWSTransport`) and the routed
`MultiTransportPublicWSManager` ship in this PR**. The runner
refuses to silently fall back to REST under `--ws-first` without
`--dry-run`: if the real public WS pump cannot be constructed,
the runner exits with `rc=2`. Operators who genuinely cannot
reach `fstream.binance.com` use `--ws-disabled` (PR-A
bootstrap-only REST), which is documented as **not** the Phase
11C.1B all-market demon-radar acceptance path.

### Phase 11C.1B boundary (must hold for the entire PR-B scope)

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
| Routed-private endpoint (`/private`)        | refused at path-root allowlist (`FORBIDDEN_WS_PATH_ROOTS`) |
| Routed acceptance path                      | `/public/{ws,stream}` + `/market/{ws,stream}` (`ALLOWED_PUBLIC_WS_PATH_ROOTS`) |
| Stream route classification                 | `!bookTicker` -> PUBLIC; `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` / `!forceOrder@arr` -> MARKET |
| `market_data.provider`                      | `binance_public`             |
| `market_data.read_only`                     | `True`                       |
| `candidate_pool_size` (default)             | `20`                         |
| `active_detail_limit` (default)             | `3`                          |
| `candidate_ttl_seconds` (default)           | `900`                        |
| `ws_staleness_threshold_ms` (default)       | `3000`                       |
| `radar_score_threshold` (default)           | `30.0`                       |

### Phase 11C.1B acceptance criteria

1. `pytest` 全部通过. Currently `2184 passed`.
2. The new test files
   `tests/unit/test_phase11c_1b_ws_radar.py` (scaffold + radar +
   pool + chain),
   `tests/unit/test_phase11c_1b_real_ws_adapter.py` (real public
   WS adapter + runner refusal + reconnect backoff + staleness
   gate + safety flags + RFC 6455 handshake / frame audit),
   `tests/unit/test_phase11c_1b_routed_public_market_ws.py`
   (routed `/public/{ws,stream}` + `/market/{ws,stream}`
   acceptance, `/private` refusal, stream-route classification,
   `MultiTransportPublicWSManager` merge, runner uses both
   routed transports, no follow-up wording in source / docs), and
   `tests/unit/test_phase11c_1b_symbol_universe.py`
   (exchangeInfo-as-truth gate + non-ASCII contract admission +
   `WS_SYMBOL_REJECTED` audit + source-tree audit refusing any
   ASCII-only symbol regex)
   pin every behaviour the brief calls out (15 brief-mandated +
   11 routed-endpoint + 4 SymbolUniverse + supporting). Full list
   in `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B.
3. The four `ExchangeClientBase` write surfaces still raise
   `SafeModeViolation`.
4. No file in the Phase 11C source set imports a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package. The
   `StdlibPublicWSTransport` is implemented entirely on top of
   `socket` + `ssl` + `select` + `struct` + `base64` + `hashlib`
   + `json` + `os.urandom` (RFC 6455 client).
5. The Phase 11B daily-report Markdown body contains the new
   `Phase 11C.1B WebSocket all-market radar` section with every
   brief-mandated metric, including the new `ws_real_transport`
   and `ws_data_degraded_ticks` fields.
6. The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
   pipelines accept the three new `PUBLIC_WS_*` event types.
7. Under `--ws-first` without `--dry-run`, the runner uses the real
   `StdlibPublicWSTransport` and does NOT silently fall back to
   REST bootstrap. If the transport factory returns `None` or
   raises, the runner exits with `rc=2` and the message
   `real public WebSocket transport is required for --ws-first
   without --dry-run`.

### Phase 11C.1B explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position / leverage
    / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any
    `/ws-api` / `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Treating the unrouted `wss://fstream.binance.com/stream` URL
    as the WS-first acceptance path (Binance silently drops
    market-class streams over an unrouted connection).
  - Connecting to DeepSeek.
  - Connecting to the real Telegram outbound HTTP transport.
  - Connecting to Binance Square.
  - Auto-retrying after a 418.
  - Switching endpoints to evade a 418.
  - Rotating source IP to evade a 418.
  - Entering Phase 12.

### How Phase 11C.1B unblocks the Phase 11C real-data acceptance run

After PR #32 merges (which ships the routed real-network
`MultiTransportPublicWSManager` inline), the Phase 11C real-data
24h acceptance run resumes with:

  - bootstrap REST: one `exchangeInfo` + one `ticker/24hr`.
  - public routed WS:
    `wss://fstream.binance.com/public/stream?streams=!bookTicker`.
  - market routed WS:
    `wss://fstream.binance.com/market/stream?streams=!ticker@arr/!miniTicker@arr/!markPrice@arr/!forceOrder@arr`.
  - candidate pool: top N (default 20) demon coins, active head 3.
  - per-loop REST detail: ONLY for the active head, gated on the
    PR-A rate-limit governor.

### Phase 11C.1B acceptance ladder (smoke runs)

| Cloud smoke         | Command                                                                                                                              | Status (UTC)                |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------- |
| 30 s dry-run        | `python -m scripts.run_public_market_paper --duration 30s --symbol-limit 5 --dry-run`                                                | PASS                        |
| 5 min real WS       | `python -m scripts.run_public_market_paper --duration 5min --symbol-limit 5 --ws-first`                                              | **PASS (2026-05-22)**       |
| 10 min real WS      | `python -m scripts.run_public_market_paper --duration 10min --symbol-limit 5 --ws-first`                                             | **PASS (2026-05-22)**       |
| 1 h real WS (clean) | `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 5 --ws-first`                                                | **PASS (2026-05-22)**       |
| 6 h WS-first        | `python -m scripts.run_public_market_paper --duration 6h --symbol-limit 5 --ws-first`                                                | optional / not required for Phase 11C.1B closeout |
| 24 h WS-first       | `python -m scripts.run_public_market_paper --duration 24h --symbol-limit 5 --ws-first`                                               | optional / parent Phase 11C longer-window, not required for Phase 11C.1B closeout |

All three Phase 11C.1B acceptance rungs (5min / 10min / 1h) record:
`ws_messages_received > 0`, `ws_chains_emitted > 0`,
`radar_candidates_seen >= 0` (no longer stuck at 0 due to no
messages), `PUBLIC_WS_CONNECTED` written, no 429 / 418, no
`ws_stale_count`, no ingestion errors, every safety flag
unchanged. Full numerics live in
"Phase 11C.1B acceptance summary" above. The earlier failure mode
(`ws_messages_received=0` for the full 300s window of the first
5-min run) was a zero-timeout `recv` short-circuit in the stdlib
WS transport; fixed by draining the recv buffer non-blockingly at
the top of every `poll` call (PR #33).

The 6h / 24h rungs are intentionally **optional**: Phase 11C.1B
closure does NOT require them. They belong to the parent Phase
11C longer-window observation work (or to a future Phase 11C+
multi-week paper window) and remain available to anyone who wants
extra confidence before Phase 11C.1C kicks off.

The legacy command
`python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20 --poll-interval-seconds 5`
is **deprecated**. It exercises the pre-PR-A "fetch every detail
endpoint for every symbol every loop" pattern that triggered HTTP
418, and it predates routed WS endpoints.

### Phase 11C.1B follow-up: SymbolUniverse (exchangeInfo-as-truth)

Binance USDⓈ-M Futures lists non-ASCII contracts in production -
documented examples include `我踏马来了USDT` and `币安人生USDT`. Each
is a real Binance contract with its own `/fapi/v1/exchangeInfo`
entry, its own all-market WS push, and its own REST detail
endpoints. The Phase 11C.1B brief therefore forbids any
character-class regex (`^[A-Z0-9_]{2,30}(USDT|USDC)$` or any
equivalent) on the symbol-validation path; the only authoritative
source is the snapshot pulled from `/fapi/v1/exchangeInfo` at
runner startup.

Implementation:

  - `app/market_data_public/symbol_universe.py` -
    `SymbolUniverse.from_exchange_info(symbols)` builds the
    bootstrapped set; `SymbolUniverse.empty()` is the back-compat
    "admit everything" fallback for dry-run / fixture tests.
  - `CandidatePool.offer()` consults the universe; symbols missing
    from the bootstrapped set surface a typed `WS_SYMBOL_REJECTED`
    event (new entry on `EventType`) and the candidate is dropped
    before it enters the pool's accounting.
  - The runner (`scripts/run_public_market_paper.main`) bootstraps
    the universe from `client.get_symbols()` before constructing
    the candidate pool. On bootstrap failure (rate-limit
    protection, network error, etc.) the runner falls back to the
    empty universe and logs the degraded note - safety flags stay
    unchanged and the pool admits everything to avoid blocking the
    smoke ladder on a transient REST fault.
  - Source-tree audit: `tests/unit/test_phase11c_1b_symbol_universe.py
    ::test_symbol_validation_uses_exchange_info_not_ascii_regex`
    walks every WS-radar / symbol-validation file and refuses
    any `re.compile|match|fullmatch|search` whose pattern smells
    like an ASCII-only symbol regex. The next PR that re-introduces
    one fails this test.

The brief is explicit: **the rejection reason is "not in
exchangeInfo", NEVER "non-ASCII character class".** A pure-ASCII
symbol that is missing from the snapshot (e.g. a brand-new listing
that came online mid-run, or a delisting whose WS pushes arrived
between bootstrap and subscribe) is treated identically to a
Chinese symbol that is missing.

PR-C (priority_score / cluster classifier / same-cluster leader /
multi-candidate arbitration) remains a separate branch.

## Closed phase: Phase 11C.1A

**Phase 11C.1A - Binance Public REST Rate Limit Governor & 418
Protection (PR-A).** Merged. The Phase 11C real-data acceptance
pause that motivated this PR was **resolved** by the combined work
of PRs #31 + #32 + #33 + #34: PR #31 shipped the rate-limit
governor here; PR #32 shipped the WebSocket-first all-market radar
+ the routed real-network public WS adapter; PR #33 fixed the
real-WS poll zero-timeout; PR #34 enforced exchangeInfo-as-truth
symbol validation. Phase 11C.1B is now ACCEPTED.

  - **PR-A** (closed, merged in PR #31)
    ships `BinancePublicRestGovernor` (sliding-window weight budget,
    429 backoff, 418 shutdown, `Retry-After`, used-weight tracking),
    lower defaults, and the layered REST runner. NO new candidate
    ranking, NO WebSocket transport.
  - **PR-B** (closed, merged in PR #32, with follow-ups PR #33 +
    PR #34)
    ships the WebSocket-first all-market radar, candidate pool
    plumbing, `candidate_detail_limit` consumption for REST detail
    enrichment, the real-network `StdlibPublicWSTransport` (RFC
    6455 over `socket` + `ssl`, stdlib only), and the routed
    `MultiTransportPublicWSManager` (one `StdlibPublicWSTransport`
    per route - PUBLIC at `/public/stream`, MARKET at
    `/market/stream`). The default WS transport still refuses to
    open a real socket (`NotImplementedError`); the in-process
    pump covers `--dry-run`; the
    `MultiTransportPublicWSManager` is selected by the runner
    whenever `--ws-first` is set without `--dry-run`. The
    routed-private endpoint `/private` is on
    `FORBIDDEN_WS_PATH_ROOTS` and is never opened.
    Multi-candidate priority ranking, `priority_score`, cluster
    classifier, same-cluster leader selection, and strategy
    selector are explicitly **NOT** in Phase 11C.1B scope: most
    of those contracts subsequently landed in Phase 11C.1C-A
    (ACCEPTED) and Phase 11C.1C-B (ACCEPTED). The MFE/MAE
    Label Queue Runtime & Tail Outcome Tracking subsequently
    landed in Phase 11C.1C-C-A (ACCEPTED 2026-05-23, PR #40
    merged, mergeCommit `75d3c7c`). The remainder (deeper
    Strategy Validation Lab, Cluster Exposure Control) is Phase
    11C.1C-C-B scope (NEXT_ALLOWED /
    NOT_STARTED).
  - **PR-C** (priority_score / cluster classifier / same-cluster
    leader / multi-candidate arbitration) is **not** Phase 11C.1B
    work. The data-contract / scoring / selector first version
    shipped in Phase 11C.1C-A (ACCEPTED); the runtime-calibration
    + Early Tail Discovery first version shipped in Phase
    11C.1C-B (ACCEPTED); the MFE/MAE Label Queue Runtime + Tail
    Outcome Tracking first version shipped in Phase 11C.1C-C-A
    (ACCEPTED). The remaining work (deeper Strategy Validation
    Lab, Cluster Exposure Control) rolls into Phase 11C.1C-C-B,
    which is currently NEXT_ALLOWED / NOT_STARTED (see "Open
    phase: Phase 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)"
    above).

### Phase 11C.1A boundary (must hold for the entire PR-A scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `telegram.outbound_enabled` (schema-locked) | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| `market_data.provider`                      | `binance_public`             |
| `market_data.read_only`                     | `True`                       |
| `market_data.symbol_limit` (default)        | `5` (was `20`, lowered)      |
| `market_data.rest_poll_interval_seconds` (default) | `60.0` (was `5.0`)    |
| `market_data.rest_governor.weight_budget_per_minute` | `300`              |
| `market_data.rest_governor.soft_weight_ratio`        | `0.50`             |
| `market_data.rest_governor.hard_weight_ratio`        | `0.75`             |
| `market_data.rest_governor.retry_after_default_seconds` | `300`           |
| `market_data.rest_governor.on_429`          | `"backoff"` (only allowed)   |
| `market_data.rest_governor.on_418`          | `"shutdown"` (only allowed)  |
| `market_data.rest_governor.candidate_detail_limit` | `3`                   |
| `market_data.rest_governor.rest_layering_enabled`  | `True`                |

### Phase 11C.1A acceptance criteria

1. `pytest` 全部通过 (currently `2089 passed`).
2. The new test file `tests/unit/test_phase11c1a_rate_limit_governor.py`
   pins, at minimum, every behaviour the brief calls out:
   - `test_429_triggers_backoff_and_stops_batch`
   - `test_418_triggers_shutdown_without_retry`
   - `test_retry_after_header_is_respected`
   - `test_used_weight_header_is_recorded`
   - `test_rest_governor_blocks_when_budget_exceeded`
   - `test_default_phase11c_polling_is_conservative`
   - `test_rest_not_called_for_all_symbols_every_loop`
   - `test_no_live_trading_flags_after_429`
   - `test_no_live_trading_flags_after_418`
   - `test_daily_report_contains_rate_limit_metrics`
3. The four `ExchangeClientBase` write surfaces still raise
   :class:`SafeModeViolation` (asserted by
   `test_phase_11c_write_surfaces_still_refuse_after_418` even after
   the governor latches into protection mode).
4. The Phase 8.5 export pipeline accepts the five new
   `RATE_LIMIT_*` event types.
5. The Phase 10A replay engine accepts the new events (no schema
   regression - asserted by the existing replay test suite).
6. The Phase 10B reflection engine accepts the new events.
7. The daily Markdown report contains the `Phase 11C.1A
   rate-limit governor` section with every required field.
8. No `binance_rate_limit.py` import touches a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package; only stdlib +
   loguru + the existing `app.*` modules.

### Phase 11C.1A explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret.
  - Calling any signed endpoint.
  - Calling any /order, /account, /position, /leverage, /margin endpoint.
  - Connecting to DeepSeek.
  - Connecting to the real Telegram outbound HTTP transport.
  - Auto-retrying after a 418.
  - Switching endpoints to evade a 418.
  - Rotating source IP to evade a 418.
  - Entering Phase 12.

### How Phase 11C.1A unblocks the Phase 11C real-data acceptance run

After PR-A merges:

  - The runner caps total per-IP weight at 300/min.
  - Bootstrap costs ~41 weight (one `exchangeInfo` + one
    `ticker/24hr`) and the steady-state loop costs ~0 weight in PR-A
    (no candidates -> no detail REST).
  - Any 429 sleeps the `Retry-After` window and emits the
    `RATE_LIMIT_429` / `RATE_LIMIT_BACKOFF_STARTED` /
    `RATE_LIMIT_BACKOFF_ENDED` audit trail.
  - Any 418 latches protection mode, opens a P1 incident, and
    stops the runner with `rc=2`. The runner does NOT auto-retry,
    does NOT switch endpoints, does NOT rotate source IP.

The Phase 11C real-data acceptance pause **was resolved** once
PR-B (WebSocket-first radar) landed alongside PR-A and its
follow-ups. Candidate ranking remains Phase 11C.1C scope. PR-B
merged via PR #32, with follow-ups in PR #33 and PR #34; the
Phase 11C.1B real-WS smoke ladder (5min / 10min / 1h) ran cleanly
on 2026-05-22 (UTC) and Phase 11C.1B is ACCEPTED.

## Phase 11C parent (open, follow-ups landed)

Phase 11C remains open as a parent / umbrella phase. Phase 11C.1A,
Phase 11C.1B, Phase 11C.1C-A, Phase 11C.1C-B, and Phase
11C.1C-C-A have all **shipped** (PRs #31 / #32 / #33 / #34 /
#36 / #38 / #40 merged into `main`); Phase 11C.1B, Phase
11C.1C-A, Phase 11C.1C-B, and Phase 11C.1C-C-A are ACCEPTED.
Phase 11C.1C-C-B (Adaptive Candidate Strategy Validation Lab +
Cluster Exposure Control) is **NEXT_ALLOWED /
NOT_STARTED**. The longer-window real-data observation rungs
(6h / 24h / multi-week) remain optional under the parent and are
NOT required for Phase 11C.1C-C-A closure. The public-market
client, allowlist, event chain, and runner skeleton continue to
satisfy the original Phase 11C acceptance gates; only the cadence
and detail-REST behaviour have been narrowed.

## Closed phases (carry-forward)

The closed-phase ledger above remains unchanged. The Phase 11C
parent phase stays open while Phase 11C.1C is drafted; longer
real-data windows (6h / 24h / multi-week) are tracked here but
are **not** Phase 11C.1B closure prerequisites.

### Phase 11C acceptance criteria

1. `pytest` 全部通过.
2. `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 5 --ws-first`
   completes without exception, producing a daily report at
   `data/reports/phase11c/{date}-phase11c-public-market.md`. The
   1h WS-first run is the active Phase 11C acceptance gate; the
   6h / 24h WS-first runs are **optional** parent Phase 11C
   longer-window observation rungs (or part of a future Phase
   11C+ multi-week paper window) and are NOT required to close
   Phase 11C.1B. The legacy command
   `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20 --poll-interval-seconds 5`
   is **deprecated and must not be used** - it predates the
   PR-A rate-limit governor and the PR-B routed WS endpoints,
   and exercises the pre-PR-A "fetch every detail endpoint for
   every symbol every loop" pattern that triggered HTTP 418.
3. Real `MARKET_SNAPSHOT` events written to `events.db` carry the
   Phase 11C tag (`provider="binance_public"`, `phase="11C"`).
4. `SignalSnapshot` is built from real market data and written into
   the `learning_ready.signal_snapshot` block of every `RISK_REJECTED`
   / `STATE_TRANSITION` event.
5. `RISK_REJECTED` events carry `learning_ready.opportunity` with a
   real `opportunity_id` / `scan_batch_id` / `symbol` /
   `source_phase = "phase_11c_public_market_paper"` plus typed
   `reject_reasons` containing `"stop_unconfirmed"`.
6. `VirtualTradePlan` saved and round-trips through
   `payload_to_virtual_trade_plan`.
7. The Phase 8.5 export zip contains the dedicated streams
   (`opportunities.jsonl`, `signal_snapshots.jsonl`,
   `virtual_trade_plans.jsonl`, `risk_decisions.jsonl`,
   `state_transitions.jsonl`) populated from real-data events.
8. The Replay engine reads every Phase 11C event type without error.
9. The Reflection engine reads the Phase 11C event payload shape
   without error.
10. `assert_public_endpoint_allowed` rejects every signed / private
    endpoint listed in `FORBIDDEN_PRIVATE_ENDPOINTS`.
11. The four `ExchangeClientBase` write surfaces continue to raise
    `SafeModeViolation` on the public client.
12. The Phase 11C source-tree audit
    (`tests/unit/test_phase11c_no_network.py`) holds: no third-party
    HTTP / WebSocket / SDK / LLM / Telegram bot import; no write
    surface call; no credential-shaped parameter; no env-var read.

### What Phase 11C is allowed to read from Binance

```
GET /fapi/v1/exchangeInfo
GET /fapi/v1/ticker/24hr
GET /fapi/v1/ticker/bookTicker
GET /fapi/v1/klines
GET /fapi/v1/aggTrades
GET /fapi/v1/trades
GET /fapi/v1/depth
GET /fapi/v1/fundingRate
GET /fapi/v1/openInterest
GET /fapi/v1/premiumIndex
```

### What Phase 11C is NOT allowed to do (refused by the client)

- API key
- API secret
- any signed endpoint
- `signature` / `timestamp` / `recvWindow` / `apiKey` query parameter
- `/fapi/v1/order` / `/fapi/v1/order/test` / `/fapi/v1/batchOrders`
- `/fapi/v1/allOrders` / `/fapi/v1/openOrders` / `/fapi/v1/openOrder`
- `/fapi/v2/account` / `/fapi/v2/balance` / `/fapi/v2/positionRisk`
- `/fapi/v1/positionRisk` / `/fapi/v1/positionSide/dual`
- `/fapi/v1/leverage` / `/fapi/v1/marginType` / `/fapi/v1/positionMargin`
- `/fapi/v1/income` / `/fapi/v1/leverageBracket`
- `/fapi/v1/multiAssetsMargin` / `/fapi/v1/listenKey`
- any other non-allowlisted path

## Future phases

| Candidate          | Gate                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------- |
| Phase 11C.1C-A (Adaptive Candidate Regime & Strategy Selector Contracts) | **ACCEPTED (closed 2026-05-22; PR #36 merged; PR #37 docs closeout).** Paper-mode only. See "Closed phase: Phase 11C.1C-A (ACCEPTED)" above for the closeout record. |
| Phase 11C.1C-B (Adaptive Candidate Runtime Calibration & Early Tail Discovery v0) | **ACCEPTED (closed 2026-05-22; PR #38 merged into `main`, mergeCommit `ce4b6de`).** Paper-mode only. See "Closed phase: Phase 11C.1C-B (ACCEPTED)" above for the closeout record and "Phase 11C.1C-B acceptance evidence (closeout)" below for the verbatim smoke transcript. **Phase 11C.1C-B acceptance does NOT authorise live trading, API keys, private endpoints, DeepSeek trade decisions, real Telegram outbound, or Phase 12.** |
| Phase 11C.1C-C-A (MFE / MAE Label Queue Runtime & Tail Outcome Tracking) | **ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`).** Paper-mode only. See "Closed phase: Phase 11C.1C-C-A (ACCEPTED)" above for the closeout record and "Phase 11C.1C-C-A acceptance evidence (closeout)" above for the verbatim operator-VPS smoke transcript. **Phase 11C.1C-C-A acceptance does NOT authorise live trading, API keys, private endpoints, DeepSeek trade decisions, real Telegram outbound, Phase 11C.1C-C-B kickoff bypassing the standard gate, or Phase 12.** |
| Phase 11C.1C-C (deeper Strategy Validation + Cluster Exposure Control + full MFE/MAE processor) | Split into Phase 11C.1C-C-A (MFE / MAE Label Queue Runtime & Tail Outcome Tracking) and Phase 11C.1C-C-B (deeper Strategy Validation Lab + Cluster Exposure Control). Phase 11C.1C-C-A is now **ACCEPTED**; Phase 11C.1C-C-B is **NEXT_ALLOWED / NOT_STARTED**. Paper-mode only. See "Open phase: Phase 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED)" above. |
| Phase 11C.1C (parent, legacy) | **OPEN.** Split into 11C.1C-A (ACCEPTED), 11C.1C-B (ACCEPTED), 11C.1C-C-A (ACCEPTED), and 11C.1C-C-B (NEXT_ALLOWED / NOT_STARTED). Paper-mode only. |
| Phase 11C+ (longer paper window, e.g. 7d / 14d) | Phase 11C parent 24h acceptance closed (still optional after the 11C.1B 1h PASS).      |
| Phase 11D (DeepSeek READ-ONLY narrative interpreter) | Phase 11C closed; Phase 11C dataset reviewed.                                    |
| Phase 12 (Limited live trading) | **FORBIDDEN.** NOT permitted from Phase 11C.1B alone, NOT permitted from Phase 11C.1C-A alone, NOT permitted from Phase 11C.1C-B alone, NOT permitted from Phase 11C.1C-C-A alone, NOT permitted from Phase 11C.1C-C-B alone, NOT permitted from any Phase 11C sub-phase alone. Requires Spec §41 Go/No-Go. |

**Phase 11C.1B closing does NOT authorise Phase 12.** Phase 12 is gated
by:

  - Spec §41 Go/No-Go checklist
  - Phase 11C.1C closed
  - Phase 11D (or another Phase 11C+ window) closed
  - Multi-week paper-mode dataset reviewed
  - Operational evidence the four write surfaces, the No-Trade Gate,
    and the Reconciliation loop have held under real-data load
  - Explicit operator sign-off; Phase 12 is never auto-promoted



## Architecture governance reference (guidance-only)

A new architecture governance document has been added at
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` ("AMA-RT
Adaptive Market Operating System Governance / 自适应市场操作系统
架构治理文档"). It records the long-term architecture
principles for AMA-RT V1.4 — anti-AI-hallucination,
anti-context-drift, anti-overfitting, anti-black-box-decision,
and anti-AI-bypass-of-Risk-Engine — and is referenced here so
the Phase Gate ledger has a single pointer to the governing
architecture document.

The new document is **guidance-only**:

  - It does **NOT** change any current Phase Gate state.
    Phase 11C.1C-C-B-A remains **ACCEPTED**; Phase
    11C.1C-C-B-B remains **NEXT_ALLOWED / NOT_STARTED**;
    every previously-closed phase entry in the Closed Phases
    table is preserved verbatim.
  - It does **NOT** change any Phase 1 safety flag
    (`mode=paper`, `live_trading=False`, `right_tail=False`,
    `llm=False`, `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False` are unchanged).
  - It does **NOT** authorise live trading, API keys, private
    endpoints, DeepSeek trade decisions, real Telegram
    outbound, AI Learning that decides trades, automatic
    parameter optimisation, reinforcement learning that
    drives trade decisions, Phase 11C.1C-C-B-B kickoff
    bypassing the standard gate, or Phase 12.
  - It does **NOT** authorise any new runtime behaviour and
    does **NOT** modify any code under `app/`, `scripts/`,
    `tests/`, or any runtime configuration.
  - **Phase 12 remains FORBIDDEN.** Phase 12 continues to
    require the Spec §41 Go/No-Go checklist; this governance
    document does not initiate that path.

For the full content, see
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`.
