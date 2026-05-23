# PR #40 — Phase 11C.1C-C-A: MFE / MAE Label Queue Runtime & Tail Outcome Tracking

> **Status: IN_REVIEW / PR_OPEN.**
>
> **The operator-VPS 10 min real public WS smoke has PASSED.**
> The Kiro-side sandbox could not serve as the smoke host
> (Binance-region HTTP 451 geoblock; same as the Phase 11C.1C-B
> closeout), so the smoke run was performed by the operator on
> a Binance-reachable VPS. The verbatim smoke transcript is
> back-filled below under "10 min real public WS smoke
> (operator-VPS, PASSED)" and mirrored under
> `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence".
>
> **PR #40 is ready for human review and may be merged after
> the reviewer confirms this docs-only evidence backfill.** PR
> #40 will only be marked **ACCEPTED** under
> `docs/PROJECT_STATUS.md` / `docs/PHASE_GATE.md` /
> `docs/CHANGELOG.md` after PR #40 is merged, by a separate
> closeout PR (mirroring the PR #36 → PR #37 and PR #38 → PR
> #39 closeout pattern). Until then Phase 11C.1C-C-A remains
> **IN_REVIEW / PR_OPEN**.

## Phase

  - **Phase 11C.1C-C-A** — paper-only MFE / MAE Label Queue
    Runtime & Tail Outcome Tracking on top of the Phase
    11C.1C-A `LABEL_QUEUE_ENQUEUED` contract.
  - **Phase 11C.1C-C-B** — `NOT_STARTED`. Reserved for the
    deeper Strategy Validation Lab + Cluster Exposure Control;
    NOT authorised by this PR.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock unchanged.

## Branch + commit

  - Branch: `feature/phase-11c1c-c-mfe-mae-label-queue-runtime`
  - Code commit: `4889087` (the runtime + 30 brief-mandated
    tests; the full 11-file diff stat below).
  - Docs-gate-fix commit: `6d6044d` (the IN_REVIEW gate-state
    write-through landed by the previous docs-only commit on
    this branch; this is also the commit the operator-VPS
    10 min real WS smoke was run against).
  - Diff stat (code commit `4889087`): 11 files, +3448 / -10
    - `app/adaptive/__init__.py` (+29)
    - `app/adaptive/label_runtime.py` (+1459, NEW)
    - `app/config/defaults.yaml` (+38)
    - `app/config/schema.py` (+84)
    - `app/config/settings.py` (+5)
    - `app/core/events.py` (+69)
    - `app/market_data_public/ws_radar_chain.py` (+56 / -10)
    - `app/paper_run/daily_report.py` (+385)
    - `scripts/run_public_market_paper.py` (+46)
    - `tests/unit/test_phase11b_no_network.py` (+13)
    - `tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`
      (+1274, NEW, 30 tests)

## What ships

The full per-phase brief, including scope, boundary, forbidden
items, and acceptance gate, lives in
`docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md`. Headline:

  - `LabelQueueRuntime` consuming the Phase 11C.1C-A
    `LABEL_QUEUE_ENQUEUED` contract and producing forward
    MFE / MAE / `tail_label` outcomes per ACTIVE candidate
    over five tracking windows (5m primary, 15m / 30m / 1h /
    4h secondary).
  - Six new event types (`LABEL_TRACKING_STARTED`,
    `LABEL_WINDOW_UPDATED`, `LABEL_WINDOW_COMPLETED`,
    `TAIL_LABEL_ASSIGNED`, `MISSED_TAIL_DETECTED`,
    `FAKE_BREAKOUT_DETECTED`) plumbed through
    `EventRepository`, the Phase 8.5 learning-ready payload,
    Phase 8.5 export, and Phase 10A replay. Schema-versioned
    via
    `LABEL_TRACKING_SCHEMA_VERSION = "phase_11c_1c_c_a.label_tracking.v1"`.
  - Tail label taxonomy (rule-based, no LLM): `strong_tail`
    / `moderate_tail` / `weak_tail` / `fake_breakout` /
    `late_chase_failure` / `dumped` / `stopped_before_tail`
    / `unresolved`. `MISSED_TAIL_DETECTED` is an independent
    flag, not a tail_label value.
  - Daily-report enhancements with the new section
    `## Phase 11C.1C-C-A MFE / MAE Label Queue Runtime &
    Tail Outcome Tracking` and every brief-mandated metric.
  - `WSRadarChainDriver` integration: after emitting
    `LABEL_QUEUE_ENQUEUED`, the chain calls
    `runtime.observe(adaptive, source_event_id)` so MFE / MAE
    advance on every chain pass. Idempotent per
    `opportunity_id` with `(symbol, candidate_first_seen_ts,
    first_seen_price)` fallback.
  - `scripts/run_public_market_paper.py` instantiates
    `LabelQueueRuntime` from settings, ticks it on every loop
    iteration plus on shutdown.

## What does NOT ship

  - **NOT** the complete Strategy Validation Lab (reserved
    for Phase 11C.1C-C-B).
  - **NOT** Cluster Exposure Control (reserved for Phase
    11C.1C-C-B).
  - **NOT** AI Learning that auto-decides trades.
  - **NOT** real Binance trading API.
  - **NOT** any signed endpoint.
  - **NOT** any account / order / position / leverage /
    margin endpoint.
  - **NOT** any private WebSocket / `listenKey` / user data
    stream.
  - **NOT** real Telegram outbound.
  - **NOT** real DeepSeek trade decisions.
  - **NOT** Phase 12.

`mfe_pct` / `mae_pct` / `tail_label` / `strategy_mode` are
descriptive labels only. They MUST NEVER trigger a real trade.
The Risk Engine remains the single trade-decision gate.

## Test ladder (PR branch)

```
pytest tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py    PASS  30 / 30
pytest tests/unit/ -k "phase11c_"                                PASS  287 / 287
pytest tests/                                                    PASS  2261 / 2261
```

  - 287 phase11c tests = 257 (post-PR-#38 baseline) + 30 new.
  - 2261 full-suite tests = 2231 (post-PR-#38 baseline) + 30
    new.
  - No regression.
  - Test environment: Python 3.11.15, pydantic 2.13.4,
    pytest 9.0.3.

The 30 tests in
`tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py` cover
MFE / MAE math, R-multiple flags (with and without
`virtual_risk_unit_pct`), every tail_label outcome, the
independent `MISSED_TAIL_DETECTED` flag, idempotent tracking
start, lifecycle transitions (pending → completed / expired),
the capacity guard, missing-price safety, the chain-driver
integration, daily-report rendering, Export round-trip, Replay
backward compatibility (including missing `schema_version`),
the learning-ready payload shape, and two safety-regression
tests pinning the Phase 1 flags and proving the runtime never
emits `ORDER_*` / `POSITION_*` / `STOP_*` /
`TELEGRAM_MESSAGE_SENT`.

## 10 min real public WS smoke (operator-VPS, PASSED)

> **The operator-VPS 10 min real public WS smoke PASSED.** The
> verbatim runner output below is back-filled by the operator
> from a Binance-reachable VPS. The Kiro-side sandbox cannot
> serve as authoritative evidence (Binance-region HTTP 451
> geoblock; same as the Phase 11C.1C-B closeout), so this
> transcript is the authoritative smoke record. The same
> transcript is mirrored under `docs/PHASE_GATE.md` §"Phase
> 11C.1C-C-A acceptance evidence".

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
counts diverge (e.g. 19 vs. 36 `LABEL_TRACKING_STARTED`)
because the runner snapshots its in-memory aggregates at the
shutdown tick while events.db captures every emission across
the full 608 s uptime including the chain-passes that fired
after the runner's last aggregate snapshot. Both views
satisfy the brief's `> 0` thresholds and corroborate the
chain-driver integration.

| Field                                                                                                                                                                                | Required value                                                                                       | Operator-recorded value |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | ----------------------- |
| `dry_run`                                                                                                                                                                            | `false`                                                                                              | `false`                 |
| `ws_real_transport`                                                                                                                                                                  | `true`                                                                                               | `true`                  |
| `ws_messages_received`                                                                                                                                                               | `> 0`                                                                                                | `56592`                 |
| `LABEL_TRACKING_STARTED`                                                                                                                                                             | `> 0`                                                                                                | `19` (runner) / `36` (events.db) |
| `LABEL_WINDOW_UPDATED`                                                                                                                                                               | `> 0`                                                                                                | `38` (runner) / `82` (events.db) |
| `LABEL_WINDOW_COMPLETED`                                                                                                                                                             | `> 0` (5m primary window must close inside the 10 min run)                                            | `11` (runner) / `20` (events.db) |
| `TAIL_LABEL_ASSIGNED`                                                                                                                                                                | `> 0`                                                                                                | `11` (runner) / `20` (events.db) |
| Daily-report section heading                                                                                                                                                         | contains `"Phase 11C.1C-C-A MFE / MAE Label Queue Runtime & Tail Outcome Tracking"`                   | present                 |
| `pending_label_records`                                                                                                                                                              | sane value                                                                                            | `8`                     |
| `completed_label_records`                                                                                                                                                            | sane value                                                                                            | `11`                    |
| `unresolved_label_records`                                                                                                                                                           | sane value                                                                                            | `0`                     |
| `rate_limit_429_count`                                                                                                                                                               | `0`                                                                                                  | `0`                     |
| `rate_limit_418_count`                                                                                                                                                               | `0`                                                                                                  | `0`                     |
| `rate_limit_ban`                                                                                                                                                                     | `False`                                                                                              | `False`                 |
| `ws_stale_count`                                                                                                                                                                     | `0` (or every stale tick explained)                                                                   | `0`                     |
| `ingestion_errors`                                                                                                                                                                   | `0` (or every ingestion error explained)                                                              | `0`                     |
| Phase 1 safety flags after the run (`live_trading=False`, `right_tail=False`, `llm=False`, `exchange_live_orders=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`) | unchanged | unchanged               |

Every required field is filed. `MISSED_TAIL_DETECTED=0` /
`FAKE_BREAKOUT_DETECTED=0` are valid outcomes for a 10 min
window over five seed symbols and are not gate-blocking; they
record that no candidate hit the missed-tail / fake-breakout
thresholds during this particular run. The 5m primary window
closed inside the 10 min run (11 runner / 20 events.db
`LABEL_WINDOW_COMPLETED`), matching the brief.

## Safety boundary (must hold throughout)

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

The Phase 1 safety lock in
`app/config/settings.py::_apply_phase1_safety_lock` continues
to hard-coerce the first five flags. Phase 11C
`MarketDataConfig` and `SafetyConfig` schemas continue to
refuse any deployment that flips a `forbid_*` flag. The
`ExchangeClientBase` write surfaces continue to raise
`SafeModeViolation`.

## Reviewer checklist

  - [x] Confirm Phase 11C.1C-C-A scope matches
    `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md`.
  - [x] Confirm `docs/PROJECT_STATUS.md` records Phase
    11C.1C-C-A as **IN_REVIEW / PR_OPEN** and Phase 11C.1C-C-B
    as **NOT_STARTED**.
  - [x] Confirm `docs/PHASE_GATE.md` records Phase 11C.1C-C-A
    as IN_REVIEW with the inherited boundary table and the
    operator-VPS smoke as **PASSED**.
  - [x] Confirm `docs/CHANGELOG.md` carries the Phase
    11C.1C-C-A IN_REVIEW block with the operator-VPS smoke
    PASSED.
  - [x] Confirm the test ladder is GREEN on the PR branch
    (30 / 287 / 2261).
  - [x] Confirm safety regression tests pin the Phase 1 flags
    and prove the runtime never emits `ORDER_*` /
    `POSITION_*` / `STOP_*` / `TELEGRAM_MESSAGE_SENT`.
  - [x] **Operator-VPS 10 min real public WS smoke PASSED** —
    runner / events.db numerics filed under "10 min real
    public WS smoke (operator-VPS, PASSED)" above and mirrored
    under `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance
    evidence".
  - [ ] Reviewer confirms the docs-only evidence backfill on
    this branch (no app/ scripts/ tests/ changes), then merges
    PR #40.
  - [ ] After merge, a separate closeout PR (mirroring the PR
    #36 → PR #37 and PR #38 → PR #39 closeout pattern) flips
    Phase 11C.1C-C-A from **IN_REVIEW** to **ACCEPTED** under
    `docs/PROJECT_STATUS.md` / `docs/PHASE_GATE.md` /
    `docs/CHANGELOG.md`.

## Out-of-scope reminders for this PR

  - PR #40 must **not** ship Phase 11C.1C-C-B (Strategy
    Validation Lab + Cluster Exposure Control).
  - PR #40 must **not** ship AI Learning that auto-decides
    trades.
  - PR #40 must **not** read or store any Binance API key /
    secret / `listenKey`.
  - PR #40 must **not** call any signed endpoint.
  - PR #40 must **not** subscribe to any private WebSocket /
    user data stream / trading WebSocket API.
  - PR #40 must **not** connect to DeepSeek as a trade-decision
    authority.
  - PR #40 must **not** connect to the real Telegram outbound
    HTTP transport.
  - PR #40 must **not** modify the Risk Engine's status as the
    single trade-decision gate.
  - PR #40 must **not** open Phase 12.
