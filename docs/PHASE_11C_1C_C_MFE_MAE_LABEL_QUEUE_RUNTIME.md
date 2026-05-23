# Phase 11C.1C-C-A — MFE / MAE Label Queue Runtime & Tail Outcome Tracking

> **Status: ACCEPTED (closed 2026-05-23; PR #40 merged into
> `main`, mergeCommit `75d3c7c`).** PR #40 (branch
> `feature/phase-11c1c-c-mfe-mae-label-queue-runtime`, code
> commit `4889087`, docs-gate-fix commit `6d6044d`) merged
> into `main` on 2026-05-23 (UTC); the operator-VPS 10 min
> real public WS smoke evidence captured under
> `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence
> (closeout)" was accepted; Phase 11C.1C-C-A is therefore
> **ACCEPTED**. Phase 11C.1C-C-B (deeper Strategy Validation
> Lab + Cluster Exposure Control) is **NEXT_ALLOWED /
> NOT_STARTED**: Phase 11C.1C-C-A acceptance does **NOT**
> authorise Phase 11C.1C-C-B kickoff bypassing the standard
> gate. **Phase 12 (real money / live trading) remains
> FORBIDDEN.**
>
> **Phase 11C.1C-C-A acceptance does NOT authorise live
> trading, API keys, private endpoints, DeepSeek trade
> decisions, real Telegram outbound, or Phase 12.**

This document is the canonical scope, boundary, and forbidden-item
brief for Phase 11C.1C-C-A. The at-a-glance status board is in
`docs/PROJECT_STATUS.md`; the phase-gate ledger entry is in
`docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-A
(ACCEPTED)"; the changelog block is in
`docs/CHANGELOG.md`; the PR-side description and operator-VPS
smoke runbook is in `docs/PR40_DESCRIPTION.md`.

## 1. What Phase 11C.1C-C-A is

Phase 11C.1C-C-A ships the **paper-only first runtime** that
consumes the Phase 11C.1C-A `LABEL_QUEUE_ENQUEUED` contract
and produces forward MFE / MAE / `tail_label` outcomes per
ACTIVE candidate over five tracking windows.

Goal: validate Phase 11C.1C-B's `early_tail_score` /
`opportunity_score` / `strategy_mode` decisions by labelling
forward outcomes (5m / 15m / 30m / 1h / 4h windows) so the
**future** Strategy Validation Lab (Phase 11C.1C-C-B) has real
labelled data to learn from.

Phase 11C.1C-C-A is the **runtime + tail-label layer only**.
It does NOT include the validation-lab decisions, the cluster
exposure controls, or any AI Learning loop.

## 2. What Phase 11C.1C-C-A is NOT

- **NOT** live trading.
- **NOT** real Binance trading API.
- **NOT** the complete Strategy Validation Lab (reserved for
  Phase 11C.1C-C-B).
- **NOT** Cluster Exposure Control (reserved for Phase
  11C.1C-C-B).
- **NOT** AI Learning that auto-decides trades.
- **NOT** real Telegram outbound.
- **NOT** real DeepSeek trade decisions.
- **NOT** a path into Phase 12.
- **NOT** authorised to flip any Phase 1 safety flag.
- **NOT** authorised to read or store any Binance API key /
  secret / `listenKey`.
- **NOT** authorised to call any signed endpoint.
- **NOT** authorised to subscribe to any private WebSocket
  variant.
- **NOT** authorised to promote `mfe_pct` / `mae_pct` /
  `tail_label` / `strategy_mode` / `early_tail_score` /
  `MISSED_TAIL_DETECTED` / `FAKE_BREAKOUT_DETECTED` to a
  real-trade authority.

`mfe_pct` / `mae_pct` / `tail_label` / `strategy_mode` MUST
NEVER trigger a real trade. They are descriptive, paper /
virtual labels only. The Risk Engine remains the single
trade-decision gate.

## 3. Scope (in PR #40)

### 3.1 `app/adaptive/label_runtime.py` (NEW)

  - `LabelQueueRuntime`: consumes
    `AdaptiveCandidateContext` events emitted by the WS-radar
    chain; on each call to `observe(adaptive, source_event_id)`
    creates or updates a `LabelTrackingRecord` and emits the
    six new event types (see §3.2).
  - `LabelTrackingRecord`: per-opportunity record carrying
    identity (`tracking_id`, `opportunity_id`, `scan_batch_id`,
    `symbol`, `source_event_id`), entry context
    (`candidate_first_seen_ts`, `first_seen_price`,
    `virtual_risk_unit_pct`), and per-window
    `TrackingWindowState`.
  - `TrackingWindowState`: per-window state carrying `mfe_pct`,
    `mae_pct`, `time_to_mfe`, `time_to_mae`, the R-multiple
    flags (`reached_2r` / `reached_3r` / `reached_5r` /
    `reached_10r`), the per-window `tail_label`, and the
    independent `MISSED_TAIL_DETECTED` /
    `FAKE_BREAKOUT_DETECTED` flags.
  - `LabelQueueRuntimeConfig`: every threshold is configurable -
    R-multiples, fake_breakout, late_chase_failure, dumped,
    stopped_before_tail, missed_tail. `max_pending_records`
    caps the queue. `grace_period_seconds` extends the
    auto-expiry beyond the longest tracking window.
  - Pure helpers: `compute_pct_return`,
    `update_window_with_price`, `assign_tail_label_for_window`.
  - Schema-versioned via
    `LABEL_TRACKING_SCHEMA_VERSION = "phase_11c_1c_c_a.label_tracking.v1"`.
    Old events without the runtime sub-block remain replayable.

### 3.2 `app/core/events.py` (six new event types)

  - `LABEL_TRACKING_STARTED`
  - `LABEL_WINDOW_UPDATED`
  - `LABEL_WINDOW_COMPLETED`
  - `TAIL_LABEL_ASSIGNED`
  - `MISSED_TAIL_DETECTED`
  - `FAKE_BREAKOUT_DETECTED`

Each payload carries the identity tuple
(`tracking_id` / `opportunity_id` / `scan_batch_id` /
`symbol` / `source_event_id`) plus the `schema_version`
stamp. Each event is plumbed through `EventRepository` and
the Phase 8.5 learning-ready payload exactly the same way the
six adaptive events from Phase 11C.1C-A are.

### 3.3 `app/config/schema.py` + `app/config/defaults.yaml`

A new `label_queue_runtime` YAML section. Fields:

  - `max_pending_records`
  - `grace_period_seconds`
  - tracking windows: `5m` (primary), `15m`, `30m`, `1h`, `4h`
  - per-window thresholds: `r_multiples`, `fake_breakout`,
    `late_chase_failure`, `dumped`, `stopped_before_tail`,
    `missed_tail`

`app/config/settings.py` exposes the block to the runner.

### 3.4 `app/market_data_public/ws_radar_chain.py`

`WSRadarChainDriver` accepts an optional
`label_queue_runtime` kwarg. After emitting
`LABEL_QUEUE_ENQUEUED` it captures the event_id and calls
`runtime.observe(adaptive, source_event_id)` so a
`LabelTrackingRecord` is created (idempotent) and price ticks
advance MFE / MAE on every subsequent chain pass. The driver
never authorises a real order; the runtime never opens a
real position; the runtime never reads a private API; the
runtime never infers live position PnL.

### 3.5 `app/paper_run/daily_report.py`

`DailyReportSnapshot` + Markdown body surface every
brief-mandated metric:

  - tracking-started / window-updated / window-completed /
    tail-label / missed-tail / fake-breakout counts
  - pending / completed / expired / unresolved record counts
  - `tail_label_distribution`
  - `reached_2r` / `reached_3r` / `reached_5r` /
    `reached_10r` counts
  - outcomes by `early_tail` / `opportunity` / `strategy_mode`
    / `late_chase_risk` bucket
  - top-MFE / worst-MAE / missed-tail / fake-breakout symbol
    lists
  - section heading: `## Phase 11C.1C-C-A MFE / MAE Label
    Queue Runtime & Tail Outcome Tracking`

### 3.6 `scripts/run_public_market_paper.py`

The runner instantiates `LabelQueueRuntime` from settings,
ticks it on every loop iteration plus on shutdown, and
threads `label_runtime_metrics` into the daily report.

### 3.7 Tests (`tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`)

30 brief-mandated tests covering:

  - `compute_pct_return` math
  - `update_window_with_price` MFE / MAE math
  - R-multiple flags (with and without `virtual_risk_unit_pct`)
  - `stopped_before_tail` flag
  - every tail_label outcome: `strong_tail`,
    `moderate_tail`, `weak_tail`, `fake_breakout`,
    `late_chase_failure`, `dumped`, `unresolved` (default)
  - independent `MISSED_TAIL_DETECTED` flag
  - idempotent tracking start (per `opportunity_id`; fallback
    by `(symbol, candidate_first_seen_ts, first_seen_price)`)
  - lifecycle states (`pending` → `completed` / `expired`)
  - capacity guard (`max_pending_records` bounded)
  - missing-price safety (returns `None`, never raises)
  - chain driver emits `LABEL_TRACKING_STARTED`
  - chain driver updates MFE / MAE on subsequent drives
  - completed window assigns tail label
  - daily report surfaces label runtime metrics
  - export carries the new event types
  - export remains backward-compatible with old events
  - replay reads the new events and old events
  - replay handles missing `schema_version` field
  - learning-ready payload shape matches
  - safety regression: Phase 1 flags unchanged; runtime never
    emits `ORDER_*`, `POSITION_*`, `STOP_*`, or
    `TELEGRAM_MESSAGE_SENT` events
  - safety regression: runtime does not open a position or
    authorise a trade

## 4. Tail label taxonomy (rule-based, no LLM)

Per window, once observation is complete, exactly one of:

| Label                  | Meaning                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------ |
| `strong_tail`          | High forward MFE; window closed in profit territory above the strong-tail threshold. |
| `moderate_tail`        | Moderate forward MFE; window closed above the moderate-tail threshold.               |
| `weak_tail`            | Small forward MFE; window closed below the moderate-tail threshold but above zero.   |
| `fake_breakout`        | Price spiked past the breakout threshold then collapsed back below entry.            |
| `late_chase_failure`   | Late entry that failed to deliver the expected continuation.                         |
| `dumped`               | Window closed deep below entry (MAE-dominated).                                      |
| `stopped_before_tail`  | The R-multiple stop got hit before the tail label window could resolve favourably.   |
| `unresolved`           | Default; window never received enough observations to assign a definite label.       |

`MISSED_TAIL_DETECTED` and `FAKE_BREAKOUT_DETECTED` are emitted
as **independent flags**, not tail_label values. Every
threshold is configurable via the
`label_queue_runtime` YAML section.

## 5. Idempotency, capacity, and safety properties

  - **Idempotency.** `observe(adaptive, source_event_id)` is
    idempotent per `opportunity_id`. The fallback
    deduplication key is
    `(symbol, candidate_first_seen_ts, first_seen_price)`.
  - **Capacity.** `max_pending_records` caps the queue. New
    records past the cap are refused without crashing.
  - **Auto-expiry.** Records older than
    `4h + grace_period_seconds` are auto-expired and moved to
    the `expired` state.
  - **Missing prices.** `update_window_with_price` returns
    `None` when no price is available; it does **not** raise.
  - **Schema versioning.** `LABEL_TRACKING_SCHEMA_VERSION =
    "phase_11c_1c_c_a.label_tracking.v1"`. Old events without
    the runtime sub-block are still replayable.

## 6. Safety boundary (must hold from day one; inherited)

| Invariant                                     | Required value                                            |
| --------------------------------------------- | --------------------------------------------------------- |
| `mode`                                        | `paper`                                                   |
| `live_trading`                                | `False`                                                   |
| `right_tail`                                  | `False`                                                   |
| `llm`                                         | `False`                                                   |
| `exchange_live_orders`                        | `False`                                                   |
| `telegram_outbound_enabled`                   | `False`                                                   |
| `binance_private_api_enabled`                 | `False`                                                   |
| `safety.forbid_*` (11 flags)                  | `True` for every flag                                     |
| Binance API key / secret                      | refused at construction                                   |
| Signed endpoint                               | refused at allowlist check                                |
| `listenKey` / user data stream                | refused at WS allowlist + URL parser                      |
| Private WebSocket / trading WS API            | refused at WS allowlist                                   |
| Routed-private endpoint (`/private`)          | refused at path-root allowlist                            |
| DeepSeek trade-decision authority             | NOT permitted                                             |
| Real Telegram outbound                        | NOT permitted                                             |
| `mfe_pct` / `mae_pct` / `tail_label` /        | descriptive label only;                                   |
|   `strategy_mode`                             | MUST NEVER trigger a real trade                           |
| AI Learning                                   | NOT implemented                                           |
| Strategy Validation Lab (full)                | NOT implemented (reserved for Phase 11C.1C-C-B)           |
| Cluster Exposure Control                      | NOT implemented (reserved for Phase 11C.1C-C-B)           |
| Phase 12 (live trading)                       | FORBIDDEN                                                 |

## 7. Phase 11C.1C-C-A explicitly forbids

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
  - Promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority.
  - Implementing the full Strategy Validation Lab.
  - Implementing Cluster Exposure Control.
  - Implementing AI Learning that auto-decides trades.
  - Issuing any real order.
  - Entering Phase 12.
  - Modifying the Risk Engine's status as the **single**
    trade-decision authority.

## 8. Acceptance gate (all met)

Phase 11C.1C-C-A is **ACCEPTED**: every gate below was met
on the PR branch and the operator-VPS 10 min real WS smoke
PASSED. PR #40 merged into `main` on 2026-05-23 (mergeCommit
`75d3c7c`); the operator-VPS smoke transcript is filed under
`docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence
(closeout)".

| Gate                                                                                                                | Status (PR #40 branch)                                              |
| ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `pytest tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`                                                     | **PASS - 30 / 30**                                                   |
| `pytest tests/unit/ -k phase11c_`                                                                                   | **PASS - 287 / 287** (no regression vs. post-PR-#38 main 257 baseline; +30 from new file) |
| `pytest tests/`                                                                                                     | **PASS - 2261 / 2261** (no regression vs. post-PR-#38 main 2231 baseline; +30 from new file) |
| 30 s dry-run smoke (LABEL_TRACKING_STARTED emitted; 5m primary windows pending)                                     | claimed by PR #40 commit message; covered by integration tests inside the targeted test file |
| Safety regression test (Phase 1 flags unchanged; no `ORDER_*` / `POSITION_*` / `STOP_*` / `TELEGRAM_MESSAGE_SENT`)   | **PASS** (covered by `test_no_live_trading_flags_unchanged` and `test_label_runtime_does_not_open_position_or_authorise_trade`) |
| 10 min real public WS smoke from operator VPS                                                                       | **PASSED.** Filed verbatim under `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence (closeout)". |

## 9. Operator-VPS 10 min real public WS smoke (PASSED)

Run from a Binance-reachable VPS against commit `6d6044d`:

```
python -m scripts.run_public_market_paper \
  --duration 10min \
  --symbol-limit 5 \
  --ws-first
```

Recorded values (verbatim from runner output / daily report;
full transcript under `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A
acceptance evidence (closeout)"):

  - `duration_seconds = 600.0`
  - `dry_run = false`
  - `ws_real_transport = true`
  - `ws_messages_received = 56592` (`> 0`)
  - `LABEL_TRACKING_STARTED = 19` (runner) / `36` (events.db)
    (`> 0`)
  - `LABEL_WINDOW_UPDATED = 38` (runner) / `82` (events.db)
    (`> 0`)
  - `LABEL_WINDOW_COMPLETED = 11` (runner) / `20` (events.db)
    (`> 0` — 5m primary window closed inside the 10 min run)
  - `TAIL_LABEL_ASSIGNED = 11` (runner) / `20` (events.db)
    (`> 0`)
  - daily report contains `"Phase 11C.1C-C-A MFE / MAE Label
    Queue Runtime & Tail Outcome Tracking"`
  - `pending_label_records = 8`,
    `completed_label_records = 11`,
    `expired_label_records = 0`,
    `unresolved_label_records = 0`
  - `rate_limit_429_count = 0`
  - `rate_limit_418_count = 0`
  - `rate_limit_ban = False`
  - `ws_stale_count = 0`
  - `ws_reconnect_count = 0`
  - `ws_currently_stale = False`
  - `ingestion_errors = 0`
  - `MISSED_TAIL_DETECTED = 0` and `FAKE_BREAKOUT_DETECTED = 0`
    are valid outcomes for a 10 min window over five seed
    symbols and are not gate-blocking
  - safety flags unchanged

The Kiro-side sandbox **could not** serve as the smoke host:
the same Binance-region HTTP 451 geoblock that was recorded
under Phase 11C.1C-B's closeout still applies. A
sandbox-sourced WS smoke would **not** have been authoritative
evidence and was **not** filed as such; the operator therefore
ran the smoke from a Binance-reachable VPS.

The verbatim operator-VPS transcript is on file under
`docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence
(closeout)". Phase 11C.1C-C-A is now **ACCEPTED**.

## 10. What Phase 11C.1C-C-A acceptance does NOT enable

Acceptance of Phase 11C.1C-C-A does **NOT** authorise:

  - Phase 11C.1C-C-B kickoff bypassing the standard gate.
  - Live trading.
  - API keys.
  - Private endpoints.
  - DeepSeek trade decisions.
  - Real Telegram outbound.
  - Phase 12.

Phase 11C.1C-C-B will be opened only via its own kickoff PR,
with its own brief, its own scope, its own boundary table, its
own forbidden list, and its own acceptance evidence. Phase
11C.1C-C-B is currently **NEXT_ALLOWED / NOT_STARTED**; it
inherits every Phase 1 + Phase 11C.1B + Phase 11C.1C-A + Phase
11C.1C-B + Phase 11C.1C-C-A forbidden item verbatim.

Phase 12 (real money / live trading) remains **FORBIDDEN**.
