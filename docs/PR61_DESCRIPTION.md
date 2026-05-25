# PR #61 — Phase 11C.1C-C-B-B-B-D — Mover Capture Recall & Missed-Tail Coverage Audit v0 (implementation)

> **Status: IN_REVIEW.** Implementation PR for Phase
> 11C.1C-C-B-B-B-D (*Mover Capture Recall & Missed-Tail
> Coverage Audit v0 / 异动币捕捉召回与漏捕右尾覆盖审计 v0*).
> Defined in place by the docs-only kickoff PR #60.
> This PR wires the deterministic, paper-only audit
> layer into the runtime; it does **not** flip the
> slice's state. A separate docs-only **closeout** PR
> will record the operator-VPS paper WS evidence and
> flip the slice to `ACCEPTED`.

## Summary

This PR implements the Phase 11C.1C-C-B-B-B-D Mover
Capture Recall & Missed-Tail Coverage Audit v0 layer.
The audit institutionalises the operator's "did the
system actually see this mover?" cross-check: instead of
relying on ad-hoc human screenshots of Binance's public
24 h gainer board, the system now produces a structured,
deterministic, replayable per-mover capture-path
evidence record + structured miss-reason taxonomy +
descriptive top-level audit status, all paper / report /
evidence only.

### Why this PR exists (positioning under AMOS)

The trigger is the SAGAUSDT case: the operator observed
a clear move on the public 24 h gainer board, and
manual cross-check confirmed AMA-RT had captured
SAGAUSDT end-to-end through every chain stage
(`PRE_ANOMALY_DETECTED` → `ANOMALY_DETECTED` →
`MARKET_REGIME_ASSESSED` → `CANDIDATE_STAGE_CLASSIFIED`
→ `OPPORTUNITY_SCORED` → `STRATEGY_MODE_SELECTED` →
`CLUSTER_CONTEXT_ATTACHED` → `LABEL_QUEUE_ENQUEUED` →
`LABEL_TRACKING_STARTED` → `TAIL_LABEL_ASSIGNED` →
`STRATEGY_VALIDATION_SAMPLE_CREATED`). One coin proves
nothing; the **right** next step is to institutionalise
the cross-check.

This PR does that. The audit is paper / virtual / report
only; the Risk Engine remains the single trade-decision
gate.

## What this PR is NOT

  - **NOT** a new strategy.
  - **NOT** a trading module.
  - **NOT** AI Learning.
  - **NOT** automatic parameter optimisation.
  - **NOT** reinforcement learning.
  - **NOT** a Historical 30D+ Blind Replay /
    Walk-forward Validation gate (that gate is reserved
    for a Phase 12 candidate review and is explicitly
    out of scope here; it belongs after the major paper
    modules and the paper validation chain are
    complete, before small-money live trading).
  - **NOT** the complete Strategy Validation Lab
    follow-up.
  - **NOT** Phase 12.

## Changed files

  - `app/core/events.py` — added
    `MOVER_CAPTURE_RECALL_AUDIT_GENERATED` and
    `MOVER_CAPTURE_PATH_AUDITED` to the `EventType`
    enum (paper / report / evidence only).
  - `app/adaptive/mover_capture_recall_audit.py` —
    new module with data models + status / miss-reason
    taxonomies + deterministic pure functions + thin
    `MoverCaptureRecallAuditRuntime` orchestrator.
  - `app/paper_run/daily_report.py` — new
    `mover_capture_audit_metrics` kwarg on `build()` /
    `_aggregate()`; new snapshot fields the brief
    enumerates; new Markdown section
    `## Phase 11C.1C-C-B-B-B-D Mover Capture Recall &
    Missed-Tail Coverage Audit v0` rendered with every
    field + per-mover record table.
  - `scripts/run_public_market_paper.py` — new helper
    `_build_mover_capture_recall_audit_input(...)` and
    shutdown-path hook that flushes the audit through
    `MoverCaptureRecallAuditRuntime` and threads the
    metrics into the daily report.
  - `tests/unit/test_phase11c_1c_c_b_b_b_d_mover_capture_recall_audit.py`
    — 21 new deterministic tests (see "Tests" below).
  - `tests/unit/test_phase11b_no_network.py` —
    allowlist extended to include the two new event
    types so the existing "Phase 11B references
    unexpected EventType values" guard still passes.
  - `docs/PROJECT_STATUS.md` — active-phase block
    extended with the Phase 11C.1C-C-B-B-B-D = IN_REVIEW
    line; timeline table extended with the
    implementation PR row.
  - `docs/PHASE_GATE.md` — added the Phase
    11C.1C-C-B-B-B-D IN_REVIEW row directly under the
    NEXT_ALLOWED definition row.
  - `docs/CHANGELOG.md` — new
    "Phase 11C.1C-C-B-B-B-D implementation" section.
  - `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`
    — new "Implementation (PR #61 — IN_REVIEW)" section
    appended at the bottom.
  - `docs/PR61_DESCRIPTION.md` — this file.

## Tests run

| Surface | Result |
| ------- | ------ |
| `tests/unit/test_phase11c_1c_c_b_b_b_d_mover_capture_recall_audit.py` | **21 / 21 PASS** |
| `tests/unit/ -k phase11c_` | **410 / 410 PASS** |
| `tests/` (full surface) | **2384 / 2384 PASS** (no regression vs. post-PR #60 main baseline) |
| 30 s `--dry-run` smoke | Daily report contains the new Phase 11C.1C-C-B-B-B-D section; `mover_capture_audit_status=INSUFFICIENT_DATA`; safety summary held end-to-end. |
| Real-WS 10 min smoke | **NOT REQUIRED** for this PR. |

### New tests pinned

  - `test_top_mover_reference_set_contract`
  - `test_top_mover_reference_set_empty_input`
  - `test_capture_path_audit_detects_full_capture`
  - `test_capture_path_audit_detects_partial_capture`
  - `test_capture_path_audit_detects_missed_eligible_mover`
  - `test_capture_path_audit_excludes_not_in_futures_universe`
  - `test_miss_reason_classification_not_in_exchange_info`
  - `test_miss_reason_classification_candidate_pool_evicted`
  - `test_miss_reason_classification_data_unreliable`
  - `test_miss_reason_classification_risk_rejected`
  - `test_mover_capture_audit_metrics`
  - `test_mover_capture_audit_insufficient_data`
  - `test_mover_capture_audit_payload_roundtrip`
  - `test_mover_capture_audit_events_exportable`
  - `test_replay_reads_mover_capture_audit_events`
  - `test_runtime_metrics_payload_when_no_flush`
  - `test_daily_report_contains_mover_capture_audit_section`
  - `test_daily_report_section_renders_when_audit_metrics_missing`
  - `test_mover_capture_audit_does_not_trigger_execution`
  - `test_no_live_trading_flags_unchanged`
  - `test_phase_12_remains_forbidden`

## Dry-run summary

```
python -m scripts.run_public_market_paper --duration 30s --symbol-limit 3 --dry-run
```

Output excerpt:

```
[AMA-RT] Phase 11C.1C-B-IN_REVIEW run finished
duration_seconds=60 iterations=1 chains_emitted=2
ws_chains_emitted=2 ws_risk_rejected=2 risk_approved=0
risk_rejected=2 ... rate_limit_429_count=0
rate_limit_418_count=0 used_weight_1m_max=0
rate_limit_protection_triggered=False rate_limit_ban=False
daily_report=data/reports/phase11c/<DATE>-phase11c-public-market.md
notes=-
```

Daily-report excerpt (the new section):

```
## Phase 11C.1C-C-B-B-B-D Mover Capture Recall & Missed-Tail Coverage Audit v0
- MOVER_CAPTURE_RECALL_AUDIT_GENERATED count: **1**
- MOVER_CAPTURE_PATH_AUDITED count: **0**
- Mover capture audit status: **INSUFFICIENT_DATA**
- Top mover count: **0**
- Captured top mover count: **0**
- Capture recall rate: **0.0000**
...
### Mover capture insufficient data reasons
- `top_mover_count=0 below min=1`

### Mover capture audit warnings
- `known_universe is empty; eligibility classification is DEGRADED - all symbols treated as in-universe`
```

`INSUFFICIENT_DATA` is the **expected** result for a 30 s
dry-run window: the dry-run transport does not push real
Binance 24 h ticker rows, so the radar buffer has no top
movers to hand to the audit. The audit correctly
degrades.

## Whether real WS smoke is required

**Real WS smoke is NOT required for this PR.** PR #61 is
a deterministic coverage audit layer. Real non-empty
top-mover coverage validation depends on the upstream
Phase 11C.1B real WS push of `!ticker@arr` /
`!miniTicker@arr` over a long enough window for the
Phase 11C.1C-C-A primary tracking window to resolve and
for the Phase 11C.1C-C-B-A
:class:`StrategyValidationSample` records to land. This
is reserved for the Phase 11C.1C-C-B-B-B-D **closeout**
PR.

## Safety boundary confirmation (verbatim)

  - `mode=paper`
  - `live_trading=False`
  - `exchange_live_orders=False`
  - `right_tail=False`
  - `llm=False`
  - `telegram_outbound_enabled=False`
  - `binance_private_api_enabled=False`
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account / order / position / leverage / margin endpoint
  - no private WebSocket
  - no `listenKey`
  - no DeepSeek trade decision
  - no real Telegram outbound
  - Phase 12 remains **FORBIDDEN**

The audit results NEVER trigger orders, NEVER modify
position size / leverage / stop-loss / target price,
NEVER modify the Risk Engine / Execution FSM /
`symbol_limit` / candidate-pool capacity / anomaly
thresholds / Regime weights, NEVER call private API,
NEVER touch Telegram outbound / DeepSeek / live trading.

## Remaining risk

  - The 30 s `--dry-run` smoke produces an empty
    `top_movers` list and therefore an
    `INSUFFICIENT_DATA` audit report. This is the
    expected behaviour, but it means the live coverage
    behaviour (capture vs. miss vs. excluded
    classification on a real Binance 24 h ticker batch)
    has not been validated end-to-end yet — that
    validation is the Phase 11C.1C-C-B-B-B-D
    **closeout** PR's responsibility.
  - The audit's deny lists
    (`risk_rejected_symbols` /
    `data_unreliable_symbols` / etc.) are populated by
    the helper from `EventRepository` row scans plus the
    runner's stage observations. If a future PR adds a
    new typed event to the chain, the helper's
    `target_event_types` tuple will need to be extended
    to keep the per-stage capture map complete. The
    schema_version bump is the audit-side contract; old
    payloads remain replayable verbatim.

## Whether PR is ready for human review

**Yes.** All tests pass; the dry-run smoke writes the
new section; safety flags are untouched; no Phase 12
surface is introduced; the audit module is purely
descriptive and read-only with respect to runtime knobs.

The PR is ready for human review. Please do not merge a
**closeout** PR for Phase 11C.1C-C-B-B-B-D before the
operator-VPS paper WS evidence is captured.
