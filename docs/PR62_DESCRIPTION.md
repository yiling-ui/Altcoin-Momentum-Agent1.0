# PR #62 — Phase 11C.1C-C-B-B-B-D Docs Closeout

> **Status: docs-only closeout / acceptance flip.** This
> PR flips Phase 11C.1C-C-B-B-B-D (*Mover Capture Recall &
> Missed-Tail Coverage Audit v0 / 异动币捕捉召回与漏捕右
> 尾覆盖审计 v0*) from `IN_REVIEW` (PR #61 implementation
> merged into `main`) to `ACCEPTED`, records the
> operator-VPS 10 min WS paper smoke evidence, and opens
> Phase 11C.1C-C-B-B-B-D-A (*Historical 60D Mover Coverage
> Backfill Audit v0 / 历史 60 天异动币覆盖回填审计 v0*)
> as `NEXT_ALLOWED / NOT_STARTED`. **No runtime code is
> modified.** **No new event type, no new Python file,
> no new test, no configuration change.** **No tests are
> run as part of this PR.** Phase 12 remains **FORBIDDEN**.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT**
> rule relaxation based on SAGAUSDT or any small number
> of movers. **NOT** Risk Engine change. **NOT**
> Execution FSM change. **NOT** automatic `symbol_limit`
> expansion / anomaly threshold changes / candidate-pool
> capacity changes / Regime weight changes. **NOT**
> Historical 30D+ Blind Replay / Walk-forward Validation
> (that gate is reserved for Phase 12 candidate review
> and is explicitly out of scope here). **NOT** Phase 12.

## Summary of changes

This PR is **docs-only**. It modifies:

  - `docs/PROJECT_STATUS.md` — flips Phase
    11C.1C-C-B-B-B-D to `ACCEPTED`; adds Phase
    11C.1C-C-B-B-B-D-A as `NEXT_ALLOWED / NOT_STARTED`;
    records the operator-VPS 10 min WS paper smoke
    evidence + audit result + export evidence in the
    active-phase block; appends a slice-specific
    `does NOT authorise` block; adds new closeout +
    next-slice rows in the per-phase ledger; marks the
    prior IN_REVIEW row as `MERGED — SUPERSEDED`.
  - `docs/PHASE_GATE.md` — adds a new closed-phases row
    for Phase 11C.1C-C-B-B-B-D (ACCEPTED, 2026-05-25);
    replaces the two B-B-B-D NEXT_ALLOWED / IN_REVIEW
    rows in the Open / Reserved table with a single
    `ACCEPTED — see Closed phases table above` row +
    a new Phase 11C.1C-C-B-B-B-D-A `NEXT_ALLOWED /
    NOT_STARTED` row; renames the
    `## Open phase: Phase 11C.1C-C-B-B-B-D` detail
    section to `## Closed phase: Phase 11C.1C-C-B-B-B-D
    (ACCEPTED)` and updates the status note; adds a new
    `## Phase 11C.1C-C-B-B-B-D acceptance evidence
    (operator-VPS 10 min WS paper smoke PASSED)`
    section; adds a new
    `## Open phase: Phase 11C.1C-C-B-B-B-D-A
    (NEXT_ALLOWED / NOT_STARTED)` section; updates the
    Phase 12 row to reference PR #62.
  - `docs/CHANGELOG.md` — adds a new `[Unreleased]`
    entry: `Phase 11C.1C-C-B-B-B-D accepted - Mover
    Capture Recall & Missed-Tail Coverage Audit v0
    docs-only closeout (PR #62)`.
  - `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`
    — appends a new `## Closeout (PR #62 — ACCEPTED)`
    section recording the PR #61 implementation summary,
    the operator-VPS 10 min WS paper smoke transcript,
    the daily-report excerpt, the `MOVER_CAPTURE_*`
    event counts, the audit result + interpretation
    rules verbatim, the Phase 8.5 export evidence, the
    rationale for opening Phase 11C.1C-C-B-B-B-D-A, the
    D-A boundary, the explicit "does NOT authorise"
    list, the safety-boundary table, and the
    forbidden-surface list.
  - `docs/PR62_DESCRIPTION.md` (this file).

This PR does **not** modify `app/`, `scripts/`, `tests/`,
`configs/`, `risk/`, `execution/`, `llm/`, `telegram/`,
`exchange/`, or any strategy runtime code.

## PR #61 implementation summary (recorded for closeout)

  - PR #61 implemented Phase 11C.1C-C-B-B-B-D Mover
    Capture Recall & Missed-Tail Coverage Audit v0.
  - It implemented paper-only / report-only /
    evidence-only audit logic.
  - It does **not** implement a trading strategy.
  - It does **not** authorise live trading.
  - It does **not** authorise AI Learning.
  - It does **not** authorise automatic parameter
    optimisation.
  - It does **not** authorise Phase 12.

Implementation included:

  - Top mover reference set
  - Capture path audit
  - Miss reason classification
  - Daily report section
  - Export / replay readable audit events
  - `EventRepository` integration
  - Deterministic unit tests
  - Safety boundary preservation

## Operator-VPS 10 min WS paper smoke evidence

```
duration_seconds                = 600.0
dry_run                         = false
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
risk_approved                   = 0
HTTP 429                        = 0
HTTP 418                        = 0
ws_reconnect_count              = 0
ws_stale_count                  = 0
live_trading_enabled            = False
exchange_live_order_enabled     = False
llm_enabled                     = False
right_tail_enabled              = False
```

Mover Capture event counts (events.db, authoritative):

```
MOVER_CAPTURE_RECALL_AUDIT_GENERATED = 1
MOVER_CAPTURE_PATH_AUDITED           = 20
```

Daily report contains:

```
## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0
```

## Audit result

```
mover_capture_audit_status      = DEGRADED
top_mover_count                 = 20
captured_top_mover_count        = 4
missed_top_mover_count          = 16
capture_recall_rate             = 0.2000
data_unreliable_count           = 4
risk_rejected_mover_count       = 4
```

### Audit-result interpretation (must be read verbatim)

  - **`DEGRADED` is an accepted audit output, not a
    runtime failure.**
  - **`DEGRADED` means the audit layer successfully
    surfaced coverage weakness / uncertainty.**
  - Captured-but-risk-rejected does **not** mean
    discovery failure (the Risk Engine remains the
    single trade-decision gate).
  - Missed-with-`unknown` reason is a `review` signal,
    **not** permission to loosen rules.
  - Low capture recall does **NOT** authorise automatic
    `symbol_limit` expansion.
  - Low capture recall does **NOT** authorise automatic
    anomaly threshold changes.
  - Low capture recall does **NOT** authorise automatic
    candidate-pool capacity changes.
  - Low capture recall does **NOT** authorise automatic
    Regime weight changes.
  - Low capture recall does **NOT** authorise Risk
    Engine changes.
  - **High capture recall would also NOT authorise live
    trading.**

## Phase 8.5 export evidence

```
export_test_data                = OK
export zip                      = data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip
manifest_event_count            = 63968
redaction_applied               = True
events.jsonl exists             = True
export contains MOVER_CAPTURE_* events
MOVER_CAPTURE_RECALL_AUDIT_GENERATED = 1
MOVER_CAPTURE_PATH_AUDITED           = 20
EXPORT_MOVER_CAPTURE_RECALL_CHECK = PASS
```

Export package files observed:

  - `manifest.json`
  - `summary_report.md`
  - `events.jsonl`
  - `opportunities.jsonl`
  - `signal_snapshots.jsonl`
  - `risk_decisions.jsonl`
  - `state_transitions.jsonl`
  - `capital_events.jsonl`
  - `virtual_trade_plans.jsonl`

## Why next slice is Phase 11C.1C-C-B-B-B-D-A

  - PR #61 proves the audit layer can run in real paper
    mode and export `MOVER_CAPTURE_*` evidence.
  - However, a 10 min live window may be too short and
    market-dependent.
  - Example: a real mover like SAGAUSDT can be missed or
    classified as `unknown` in a short audit window.
  - Waiting several quiet days may waste time if the
    market is calm.
  - Therefore the next slice should evaluate
    discovery-layer coverage over the past 60 days.
  - This is **not** complete strategy blind testing.
  - This is **not** Phase 12 pre-live validation.
  - This is **only** a discovery-layer coverage backfill
    audit.

D-A must require:

  - 60D top mover reference set;
  - eligible USDT perpetual universe filter;
  - `first_seen_time_utc` for every captured mover;
  - `first_seen_event_type`;
  - `first_seen_latency_seconds` where a mover reference
    timestamp exists;
  - `capture_path_depth`;
  - per-mover status (`captured` / `partially_captured` /
    `missed` / `excluded`);
  - miss-reason classification;
  - report / export / replay evidence.

D-A is **allowed** to answer:

  - over the past 60 days, **which eligible movers did
    AMA-RT detect**;
  - **when did AMA-RT first detect them**;
  - **which capture-path layer did they reach**;
  - **which movers were missed**;
  - **why were they missed**;
  - **which misses are universe-coverage issues** vs.
    discovery-layer warnings.

D-A must **NOT** answer:

  - whether the strategy is profitable;
  - whether live trading is allowed;
  - whether leverage / position / stops should change;
  - whether `symbol_limit` should auto-expand;
  - whether anomaly thresholds should auto-change;
  - whether candidate pool capacity should auto-change;
  - whether Phase 12 can begin.

## Phase 11C.1C-C-B-B-B-D acceptance does NOT authorise

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise API keys.
  - It does **NOT** authorise private endpoints.
  - It does **NOT** authorise DeepSeek trade decisions.
  - It does **NOT** authorise real Telegram outbound.
  - It does **NOT** authorise Phase 12.
  - It does **NOT** authorise automatic parameter
    optimisation.
  - It does **NOT** authorise AI Learning.
  - It does **NOT** authorise rule relaxation based on
    SAGAUSDT or any small number of movers.
  - It does **NOT** authorise changing the Risk Engine or
    the Execution FSM.
  - It does **NOT** authorise automatic `symbol_limit`
    expansion.
  - It does **NOT** authorise automatic anomaly threshold
    changes.
  - It does **NOT** authorise automatic candidate-pool
    capacity changes.
  - It does **NOT** authorise automatic Regime weight
    changes.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D-A
    kickoff bypassing the standard gate.

## Safety boundary (Phase 1 lock unchanged)

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
real account / order / position / leverage / margin endpoint = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

## Confirmation checklist

  - [x] **Changed files** — `docs/PROJECT_STATUS.md`,
    `docs/PHASE_GATE.md`, `docs/CHANGELOG.md`,
    `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`,
    `docs/PR62_DESCRIPTION.md`.
  - [x] **Confirm docs-only.** No runtime code modified.
  - [x] **Confirm no `app/` / `scripts/` / `tests/` /
    `configs/` changes.**
  - [x] **Confirm Phase 11C.1C-C-B-B-B-D = `ACCEPTED`.**
  - [x] **Confirm Phase 11C.1C-C-B-B-B-D-A =
    `NEXT_ALLOWED / NOT_STARTED`** (defined as
    *Historical 60D Mover Coverage Backfill Audit v0 /
    历史 60 天异动币覆盖回填审计 v0*).
  - [x] **Confirm Phase 12 = `FORBIDDEN`.**
  - [x] **Confirm no runtime behaviour changed.**
  - [x] **Confirm no live trading.**
  - [x] **Confirm no API key.**
  - [x] **Confirm no private endpoint.**
  - [x] **Confirm no DeepSeek trade decision.**
  - [x] **Confirm no real Telegram outbound.**
  - [x] **Confirm no tests run.**
  - [x] **Confirm PR #61 implementation summary recorded
    verbatim** (paper-only / report-only / evidence-only
    audit logic; not a trading strategy; not live
    trading; not AI Learning; not automatic parameter
    optimisation; not Phase 12; implementation included
    top mover reference set, capture path audit, miss
    reason classification, daily report section, export
    / replay readable audit events, EventRepository
    integration, deterministic unit tests, safety
    boundary preservation).
  - [x] **Confirm operator-VPS 10 min WS paper smoke
    evidence recorded verbatim** (`duration_seconds=600.0`,
    `dry_run=false`, `ws_first=true`,
    `ws_real_transport=true`, `ingestion_errors=0`,
    `risk_approved=0`, `HTTP 429=0`, `HTTP 418=0`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `live_trading_enabled=False`,
    `exchange_live_order_enabled=False`,
    `llm_enabled=False`, `right_tail_enabled=False`).
  - [x] **Confirm Mover Capture event counts recorded
    verbatim** (`MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`,
    `MOVER_CAPTURE_PATH_AUDITED=20`).
  - [x] **Confirm daily report contains Mover Capture
    section verbatim** (`## Phase 11C.1C-C-B-B-B-D Mover
    Capture Recall & Missed-Tail Coverage Audit v0`).
  - [x] **Confirm audit result recorded verbatim**
    (`mover_capture_audit_status=DEGRADED`,
    `top_mover_count=20`,
    `captured_top_mover_count=4`,
    `missed_top_mover_count=16`,
    `capture_recall_rate=0.2000`,
    `data_unreliable_count=4`,
    `risk_rejected_mover_count=4`).
  - [x] **Confirm `DEGRADED` interpretation recorded
    verbatim** (DEGRADED is an accepted audit output,
    not a runtime failure; DEGRADED means the audit
    layer successfully surfaced coverage weakness /
    uncertainty; captured-but-risk-rejected ≠ discovery
    failure; missed-with-unknown is a review signal not
    permission to loosen rules; low recall does NOT
    authorise auto-changes to symbol_limit / anomaly
    thresholds / candidate-pool capacity / Regime
    weights / Risk Engine; high recall would also NOT
    authorise live trading).
  - [x] **Confirm Phase 8.5 export evidence recorded
    verbatim** (`export_test_data=OK`,
    `data/reports/exports/ama_rt_test_data_1779721036065_export_d.zip`,
    `manifest_event_count=63968`,
    `redaction_applied=True`, `events.jsonl` exists,
    export contains `MOVER_CAPTURE_*` events,
    `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`,
    `MOVER_CAPTURE_PATH_AUDITED=20`,
    `EXPORT_MOVER_CAPTURE_RECALL_CHECK=PASS`); export
    package files observed: `manifest.json`,
    `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`, `virtual_trade_plans.jsonl`.
  - [x] **Confirm Phase 11C.1C-C-B-B-B-D-A rationale
    recorded** (10 min window short / market-dependent;
    SAGAUSDT example; quiet days waste time; therefore
    D-A evaluates 60D discovery-layer coverage; not
    complete strategy blind testing; not Phase 12
    pre-live validation; only discovery-layer coverage
    backfill audit).
  - [x] **Confirm D-A required fields recorded verbatim**
    (60D top mover reference set; eligible USDT
    perpetual universe filter; `first_seen_time_utc`;
    `first_seen_event_type`;
    `first_seen_latency_seconds` where a mover reference
    timestamp exists; `capture_path_depth`; per-mover
    status `captured` / `partially_captured` / `missed`
    / `excluded`; miss-reason classification; report /
    export / replay evidence).
  - [x] **Confirm D-A boundary recorded verbatim**
    (allowed answers + forbidden answers).
  - [x] **Confirm slice-specific forbidden items
    recorded verbatim** (no live trading; no API keys;
    no private endpoints; no DeepSeek trade decisions;
    no real Telegram outbound; no Phase 12; no AI
    Learning; no automatic parameter optimisation; no
    rule relaxation based on SAGAUSDT / single-coin
    cases; no Risk Engine / Execution FSM changes; no
    automatic `symbol_limit` expansion; no automatic
    anomaly threshold changes; no automatic
    candidate-pool capacity changes; no automatic
    Regime weight changes; no Phase 11C.1C-C-B-B-B-D-A
    kickoff bypassing the standard gate).
  - [x] **Confirm safety boundary held end-to-end**
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - [x] **Confirm Phase 12 remains `FORBIDDEN`.**
