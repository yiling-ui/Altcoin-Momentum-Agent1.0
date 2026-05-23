# PR #40 — Phase 11C.1C-C-A: MFE / MAE Label Queue Runtime & Tail Outcome Tracking

> **Status: IN_REVIEW / PR_OPEN. NOT MERGEABLE YET.**
>
> **A 10 min real public WS smoke from operator VPS is REQUIRED
> before merge.** The Kiro-side sandbox cannot serve as the
> smoke host (Binance-region HTTP 451 geoblock; same as the
> Phase 11C.1C-B closeout). Until the operator-VPS smoke is on
> file, PR #40 must NOT be merged.

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
  - Commit: `4889087` (single commit)
  - Diff stat: 11 files, +3448 / -10
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

## 10 min real public WS smoke (REQUIRED from operator VPS)

> **10 min real WS smoke is required from operator VPS before
> merge.** The Kiro-side sandbox cannot serve as authoritative
> evidence (Binance-region HTTP 451 geoblock), so a
> sandbox-sourced WS smoke MUST NOT be filed under
> `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence".

Run from a Binance-reachable VPS:

```
python -m scripts.run_public_market_paper \
  --duration 10min \
  --symbol-limit 5 \
  --ws-first
```

Required fields (capture verbatim from runner output / daily
report and back-fill the table below):

| Field                                                                             | Required value                                            | Operator-recorded value |
| --------------------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------- |
| `dry_run`                                                                         | `false`                                                   | _____                   |
| `ws_real_transport`                                                               | `true`                                                    | _____                   |
| `ws_messages_received`                                                            | `> 0`                                                     | _____                   |
| `LABEL_TRACKING_STARTED`                                                          | `> 0`                                                     | _____                   |
| `LABEL_WINDOW_UPDATED`                                                            | `> 0`                                                     | _____                   |
| `LABEL_WINDOW_COMPLETED`                                                          | `> 0` (5m primary window must close inside the 10 min run) | _____                   |
| `TAIL_LABEL_ASSIGNED`                                                             | `> 0`                                                     | _____                   |
| Daily-report section heading                                                      | contains `"Phase 11C.1C-C-A MFE / MAE Label Queue Runtime & Tail Outcome Tracking"` | _____                   |
| `pending_label_records`                                                           | sane value                                                 | _____                   |
| `completed_label_records`                                                         | sane value                                                 | _____                   |
| `unresolved_label_records`                                                        | sane value                                                 | _____                   |
| `rate_limit_429_count`                                                            | `0`                                                        | _____                   |
| `rate_limit_418_count`                                                            | `0`                                                        | _____                   |
| `rate_limit_ban`                                                                  | `False`                                                    | _____                   |
| `ws_stale_count`                                                                  | `0` (or every stale tick explained)                        | _____                   |
| `ingestion_errors`                                                                | `0` (or every ingestion error explained)                   | _____                   |
| Phase 1 safety flags after the run (`live_trading=False`, `right_tail=False`, `llm=False`, `exchange_live_orders=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`) | unchanged | _____                   |

Once captured, file the verbatim runner output under
`docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance evidence"
and back-fill the same numbers under the corresponding row in
`docs/PROJECT_STATUS.md`. Only then can Phase 11C.1C-C-A move
from **IN_REVIEW** to **ACCEPTED** and PR #40 be merged.

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

  - [ ] Confirm Phase 11C.1C-C-A scope matches
    `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md`.
  - [ ] Confirm `docs/PROJECT_STATUS.md` records Phase
    11C.1C-C-A as **IN_REVIEW / PR_OPEN** and Phase 11C.1C-C-B
    as **NOT_STARTED**.
  - [ ] Confirm `docs/PHASE_GATE.md` records Phase 11C.1C-C-A
    as IN_REVIEW with the inherited boundary table and the
    operator-VPS smoke as REQUIRED but NOT YET FILED.
  - [ ] Confirm `docs/CHANGELOG.md` carries the Phase
    11C.1C-C-A IN_REVIEW block.
  - [ ] Confirm the test ladder is GREEN on the PR branch
    (30 / 287 / 2261).
  - [ ] Confirm safety regression tests pin the Phase 1 flags
    and prove the runtime never emits `ORDER_*` /
    `POSITION_*` / `STOP_*` / `TELEGRAM_MESSAGE_SENT`.
  - [ ] **Run the 10 min real public WS smoke from operator
    VPS** and capture every required field above.
  - [ ] File the verbatim runner output under
    `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance
    evidence" and back-fill `docs/PROJECT_STATUS.md`.
  - [ ] **Only after** all of the above: re-review and merge.

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
