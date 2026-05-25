# PR #63 — Phase 11C.1C-C-B-B-B-D-A: Historical 60D Mover Coverage Backfill Audit v0 (docs-only kickoff)

> **Status: DOCS-ONLY KICKOFF / SCOPE ALIGNMENT.** This PR
> defines Phase 11C.1C-C-B-B-B-D-A (*Historical 60D Mover
> Coverage Backfill Audit v0 / 历史 60 天异动币覆盖回填审
> 计 v0*) as the **next allowed child slice** under the
> Phase 11C.1C-C-B-B-B parent (on top of the `ACCEPTED`
> Phase 11C.1C-C-B-B-B-D track). The parent phase is **not**
> renamed: Phase 11C.1C-C-B-B-B remains *Strategy
> Validation Lab (deeper) & richer Cluster Exposure Control
> follow-up*. **No runtime code is shipped by this PR.**
> **No phase's acceptance state is flipped.** Phase
> 11C.1C-C-B-B-B-D-A remains `NEXT_ALLOWED / NOT_STARTED`;
> this PR scopes the slice in place.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> new strategy. **NOT** a trading module. **NOT** a new
> runtime module. **NOT** a new event type. **NOT** the
> complete Strategy Validation Lab follow-up. **NOT** Phase
> 11C.1C-C-B-B-B-D-A *implementation* (out of scope; will be
> a separate PR cycle if needed). **NOT** Phase
> 11C.1C-C-B-B-B-D-A *closeout* (out of scope; the closeout
> will be a separate docs-only PR after the operator
> captures B1 / B2 backfill audit evidence). **NOT** a
> Historical 30D+ / 60D *complete strategy* blind replay /
> walk-forward validation gate (that gate is reserved until
> small-money live trading prep and is **not** in scope
> here). **NOT** Phase 12.
>
> The Historical 60D Mover Coverage Backfill Audit v0 is
> **paper-only / report-only / evidence-only** end to end.
> It does not add a new runtime module, a new event type, a
> new strategy, a new execution surface, a new optimiser,
> or a new AI authority. It defines the historical backfill
> audit cadence (B1 / B2 with B3+ reserved), the audit
> input sources, the audit objects, the 60D top-mover
> reference set shape, the per-captured-mover audit row
> shape, the recall metrics, the missed-mover reason
> taxonomy, the eight interpretation rules, and the
> evidence-template shape that any future closeout PR must
> follow. The Risk Engine remains the single trade-decision
> gate.

## Phase

  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 merged
    into `main`, 2026-05-23, mergeCommit `3ecfc3b`).
  - **Phase 11C.1C-C-B-A** — `ACCEPTED` (PR #42 merged into
    `main`, 2026-05-23, mergeCommit `cc18047`).
  - **Phase 11C.1C-C-A** — `ACCEPTED` (PR #40 merged into
    `main`, 2026-05-23, mergeCommit `75d3c7c`).
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    *Parent* phase. Strategy Validation Lab (deeper) &
    richer Cluster Exposure Control follow-up. **Not
    renamed by this PR.**
  - **Phase 11C.1C-C-B-B-B-A** — `ACCEPTED` (PR #52 merged
    into `main`, 2026-05-24, mergeCommit `f8ba315`;
    closeout via PR #54). First child slice. Paper Alpha
    Gate v0.
  - **Phase 11C.1C-C-B-B-B-B** — `ACCEPTED` (PR #56 merged
    into `main`, 2026-05-24, mergeCommit `1a9abe2`;
    closeout via PR #57). Second child slice. Regime &
    Cluster Cohort Evidence Pack v0.
  - **Phase 11C.1C-C-B-B-B-C** — `ACCEPTED` (PR #58
    docs-only kickoff merged into `main`; closeout via PR
    #59, 2026-05-25). Third child slice. Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0.
  - **Phase 11C.1C-C-B-B-B-D** — `ACCEPTED` (PR #60
    docs-only kickoff + PR #61 implementation + PR #62
    docs-only closeout merged into `main`, 2026-05-25).
    Fourth child slice. Mover Capture Recall & Missed-Tail
    Coverage Audit v0 / *异动币捕捉召回与漏捕右尾覆盖审
    计 v0*.
  - **Phase 11C.1C-C-B-B-B-D-A** — *defined by this PR*.
    `NEXT_ALLOWED / NOT_STARTED`. **Next allowed child
    slice** under Phase 11C.1C-C-B-B-B (on top of the
    `ACCEPTED` 11C.1C-C-B-B-B-D track). Historical 60D
    Mover Coverage Backfill Audit v0 / *历史 60 天异动币
    覆盖回填审计 v0*. Docs / evidence-template only. No
    new runtime module. No new event type. No trade
    authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Branch + base

  - Branch:
    `docs/phase-11c1c-c-b-b-b-d-a-historical-60d-mover-coverage-kickoff`
  - Base: `main` (post PR #62 closeout).

## What this PR does

  - **Defines** Phase 11C.1C-C-B-B-B-D-A as the *Historical
    60D Mover Coverage Backfill Audit v0 / 历史 60 天异动
    币覆盖回填审计 v0* — the next allowed child slice
    under Phase 11C.1C-C-B-B-B (on top of the `ACCEPTED`
    Phase 11C.1C-C-B-B-B-D track).
  - **Records** the **why** for this slice: PR #61 proved
    the Mover Capture Recall & Missed-Tail Coverage Audit
    v0 layer can run in real paper mode and export
    `MOVER_CAPTURE_*` evidence. PR #62 docs-only closeout
    flipped Phase 11C.1C-C-B-B-B-D to `ACCEPTED` on the
    basis of an operator-VPS 10 min WS paper smoke
    transcript with `mover_capture_audit_status=DEGRADED`
    and `capture_recall_rate=0.2000`. **However**: a
    10 min live audit window may be too short and
    market-dependent. On a calm day the gainer board may
    show no clear tails; on a noisy day a single coin
    (e.g. SAGAUSDT) may dominate the signal but prove
    nothing about general coverage. Waiting for several
    "good" market days to accumulate enough 10 min
    windows wastes operator time and risks selection bias
    on the operator's side. The right next step is to
    evaluate discovery-layer coverage **over the past 60
    days** as a structured **historical backfill audit**,
    not as another series of 10 min live windows. This
    converts "human looks at the gainer board vs. did the
    system see it" from anecdote into a deterministic,
    historical, replay-friendly audit. It is **not**
    complete strategy blind testing. It is **not** Phase
    12 pre-live validation. It is **only** a
    discovery-layer historical coverage backfill audit.
  - **Defines** the eight coverage questions the audit
    answers, **and only these eight**:
      1. Over the past 60 days, did AMA-RT discover the
         eligible USDT perpetual movers?
         (`system_captured = true / false`.)
      2. If discovered, when was the first detection?
         (`first_seen_time_utc`.)
      3. What was the first detection event?
         (`first_seen_event_type`.)
      4. How deep did the capture path go?
         (`capture_path_depth`, `reached_anomaly`,
         `reached_label_queue`, `reached_tail_label`,
         `reached_strategy_validation_sample`.)
      5. If not discovered, why? (`miss_reason` from the
         fixed taxonomy below.)
      6. Is each missed mover a universe-coverage issue or
         a discovery-layer warning?
      7. Which captured movers were rejected by the Risk
         Engine? (`risk_rejected = true`; conservative
         paper outcome, **not** discovery failure.)
      8. Which captured movers only made it partway and
         never entered the label / validation chain?
         (`status = partially_captured`.)
  - **Defines** the audit cadence (operator-driven; not
    auto-scheduled):
      - **B1 — first end-to-end 60D historical backfill
        audit pass.**
      - **B2 — second pass against an independent
        operator-VPS replay window.**
      - **B3+ — reserved for later child slices; out of
        scope for this PR; not implemented in this PR.**
  - **Defines** the audit input sources (read-only; reuse
    existing surfaces):
      - Binance **public** 24 h ticker / public klines /
        public market data (existing public REST surface;
        Phase 11C.1A rate-limit governor; not a private
        endpoint, not a signed endpoint, not a
        `listenKey`).
      - `EventRepository` / events.db (existing).
      - Daily report (existing Phase 11B + 11C sections).
      - Phase 8.5 export bundle / Phase 10A replay bundle
        over the 60D window.
      - `StrategyValidationDataset` (Phase 11C.1C-C-B-B-A
        artefact).
      - `PaperAlphaGateReport` (Phase 11C.1C-C-B-B-B-A
        artefact).
      - `RegimeClusterEvidencePack` (Phase
        11C.1C-C-B-B-B-B artefact).
      - `MoverCaptureRecallAuditReport` (Phase
        11C.1C-C-B-B-B-D artefact).
      - `SymbolUniverse` and `exchangeInfo`-as-truth
        catalogue (Phase 11C.1B artefacts).
      - Candidate pool logs / capacity-eviction evidence
        (where available).
  - **Defines** the audit objects:
      - 60D top gainers / top movers / high-momentum
        movers in the eligible USDT perpetual universe.
      - 60D detected anomalies.
      - 60D pre-anomaly candidates.
      - 60D label-tracked candidates.
      - 60D validation samples.
      - 60D risk-rejected captured movers.
      - 60D excluded symbols (not in the eligible
        universe).
  - **Defines** the **60D top-mover reference set fields**
    per window / per symbol:
      - `reference_window_start_utc`
      - `reference_window_end_utc`
      - `top_mover_symbol`
      - `top_mover_rank`
      - `max_window_gain`
      - `max_24h_gain`
      - `reference_timestamp_utc`
      - `eligible_usdt_perpetual` (true / false).
        Excluded: non-futures listings,
        non-USDT-margined, non-perpetual,
        not-in-`exchangeInfo`, delisted / inactive
        symbols.
  - **Defines** the **per-captured-mover audit row**:
      - `top_mover_symbol`
      - `mover_window_start_utc`
      - `mover_window_end_utc`
      - `top_mover_rank`
      - `max_window_gain`
      - `max_24h_gain`
      - `eligible_usdt_perpetual`
      - `system_captured`
      - `first_seen_time_utc`
      - `first_seen_event_type`
      - `first_seen_latency_seconds` (where a mover
        reference timestamp exists)
      - `capture_path_depth`
      - `reached_anomaly`
      - `reached_label_queue`
      - `reached_tail_label`
      - `reached_strategy_validation_sample`
      - `risk_rejected`
      - `status` (`captured` / `partially_captured` /
        `missed` / `excluded`)
      - `miss_reason`
  - **Defines** the **fixed `miss_reason` taxonomy**
    (descriptive only; no new runtime taxonomy added):
      - `not_in_futures_universe`
      - `symbol_not_in_exchange_info`
      - `not_usdt_perpetual`
      - `missing_historical_reference_data`
      - `missing_event_history`
      - `below_liquidity_threshold`
      - `symbol_limit_excluded`
      - `candidate_pool_evicted`
      - `insufficient_ws_data`
      - `stale_data`
      - `data_unreliable`
      - `no_anomaly_threshold_cross`
      - `risk_rejected`
      - `no_completed_tail_label_yet`
      - `unknown` (a `review` signal — **not** a `relax`
        signal)
  - **Lists** the allowed outputs (docs / evidence
    templates only):
      - `historical_60d_mover_reference_set`
      - `historical_60d_capture_path_audit`
      - `historical_60d_miss_reason_summary`
      - `historical_60d_first_seen_summary`
      - `historical_60d_capture_recall_summary`
      - `historical_60d_coverage_warning`
      - `historical_60d_export_replay_evidence_template`
  - **Records** the eight interpretation principles
    (must be read verbatim):
      1. **Captured ≠ tradable.**
      2. **Captured early ≠ strategy profitable.**
      3. **Missed and not-in-futures-universe ≠ system
         failure.**
      4. **Missed and in-eligible-universe IS a coverage
         warning** (for human review only).
      5. **`risk_rejected` ≠ discovery failure** (Risk
         Engine remains the single trade-decision gate).
      6. **`missed` and `unknown` are `review` signals**
         (no automatic rule relaxation; no automatic
         `symbol_limit` expansion; no automatic anomaly
         threshold change; no automatic candidate-pool
         capacity change; no automatic Regime weight
         change).
      7. **High `capture_recall_rate` does NOT authorise
         live trading.**
      8. **Low `capture_recall_rate` does NOT authorise
         parameter changes** (no "looking at the answer
         key" — no auto-tuning thresholds against the
         historical reference set).
  - **Records** the boundary table and the slice-specific
    forbidden items (carries forward verbatim from
    B-B-B-A / B-B-B-B / B-B-B-C / B-B-B-D + adds
    slice-specific items for the historical backfill
    audit).
  - **Refreshes** the Phase 11C.1C-C-B-B-B-D-A scaffolding
    in `docs/PHASE_GATE.md` and `docs/PROJECT_STATUS.md`
    so the slice is now defined by name, scope, and full
    audit shape, while remaining `NEXT_ALLOWED /
    NOT_STARTED`.
  - **Records** this PR in `docs/CHANGELOG.md >
    [Unreleased]` and `docs/PR63_DESCRIPTION.md`.

## What this PR does NOT do

  - It does **NOT** flip any phase's acceptance state.
  - It does **NOT** rename Phase 11C.1C-C-B-B-B.
  - It does **NOT** implement the Historical 60D Mover
    Coverage Backfill Audit v0 — the audit is defined as
    docs / evidence templates only, and the slice will
    not introduce any new runtime module or new event
    type at any point in its lifecycle.
  - It does **NOT** auto-schedule B1 / B2 / B3+ runs. The
    cadence is operator-driven.
  - It does **NOT** widen, replace, or relax the existing
    Mover Capture Recall & Missed-Tail Coverage Audit v0
    `DEGRADED` rule, the Regime & Cluster Evidence Pack
    v0 `INSUFFICIENT_SAMPLE` minimums, the Paper Alpha
    Gate v0 `INCONCLUSIVE` minimums, or the Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0
    cadence.
  - It does **NOT** authorise any rule relaxation on the
    basis of historical movers (no "looking at the
    answer key").
  - It does **NOT** stand in for a Historical 30D+ / 60D
    *complete strategy* blind replay / walk-forward
    validation gate (that gate is reserved for a Phase 12
    candidate review and is explicitly out of scope
    here).
  - It does **NOT** add any new Python module under
    `app/`.
  - It does **NOT** add any new event type.
  - It does **NOT** modify any runtime behaviour.
  - It does **NOT** modify configuration schemas,
    defaults, or YAML.
  - It does **NOT** add or modify tests.
  - It does **NOT** run tests.
  - It does **NOT** authorise live trading, API keys,
    private endpoints, signed endpoints, `listenKey` /
    private WebSocket, account / order / position /
    leverage / margin endpoints, DeepSeek trade
    decisions, real Telegram outbound, AI Learning,
    automatic parameter optimisation, reinforcement
    learning, the complete Strategy Validation Lab
    follow-up, or Phase 12.
  - It does **NOT** modify `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `llm/`,
    `telegram/`, or `exchange/`.

## Changed files

```
docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md   (NEW)
docs/PR63_DESCRIPTION.md                                                   (NEW)
docs/PHASE_GATE.md                                                         (modified — docs-only)
docs/PROJECT_STATUS.md                                                     (modified — docs-only)
docs/CHANGELOG.md                                                          (modified — docs-only)
```

No file under `app/`, `scripts/`, `tests/`, `configs/`,
`risk/`, `execution/`, `llm/`, `telegram/`, or `exchange/`
is touched.

## Allowed file edits

  - `docs/PROJECT_STATUS.md`
  - `docs/PHASE_GATE.md`
  - `docs/CHANGELOG.md`
  - `docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md`
    (NEW)
  - `docs/PR63_DESCRIPTION.md` (NEW; this document)

## Allowed outputs (docs / evidence templates only) — recorded for future PRs in the cycle

Each is a **descriptive document, evidence row, or
summary**. None has trade authority. None is read by the
Risk Engine or the Execution FSM. None is a new Python
module, a new event type, or a new runtime hook:

  - `historical_60d_mover_reference_set`
  - `historical_60d_capture_path_audit`
  - `historical_60d_miss_reason_summary`
  - `historical_60d_first_seen_summary`
  - `historical_60d_capture_recall_summary`
  - `historical_60d_coverage_warning`
  - `historical_60d_export_replay_evidence_template`

## Audit cadence (operator-driven; not auto-scheduled)

  - **B1 — first end-to-end 60D historical backfill audit
    pass.**
  - **B2 — second pass against an independent operator-VPS
    replay window.**
  - **B3+ — reserved for later child slices; out of scope
    for this PR.**

This PR **must not** implement an automatic scheduler, an
auto-trigger, or any runtime change that drives B1 / B2 /
B3+ on a clock. The cadence is **operator-driven** and
recorded as a **protocol**, not as code.

## Interpretation principles (carry forward verbatim)

  1. **Captured ≠ tradable.** A symbol reaching
     `STRATEGY_VALIDATION_SAMPLE_CREATED` does **not**
     mean the strategy can trade it; tradability requires
     Risk Engine approval and is out of scope for this
     slice.
  2. **Captured early ≠ strategy profitable.** A low
     `first_seen_latency_seconds` does **not** mean the
     strategy would have been profitable; the audit
     measures discovery, not P&L.
  3. **Missed and not-in-futures-universe ≠ system
     failure.** Out-of-scope-by-design symbols
     (non-futures, non-USDT, non-perpetual,
     not-in-`exchangeInfo`, delisted) are recorded but
     do **not** count against the discovery layer.
  4. **Missed and in-eligible-universe IS a coverage
     warning.** When a missed symbol is in the eligible
     USDT perpetual universe AND showed clear right-tail
     behaviour AND was missed for a system-correctable
     reason, a coverage warning **must** be raised — for
     human review only.
  5. **`risk_rejected` ≠ discovery failure.** The symbol
     was discovered; the Risk Engine performed its
     conservative paper job. The Risk Engine remains the
     single trade-decision gate.
  6. **`missed` and `unknown` are `review` signals.** They
     must enter human review. They must **not** trigger
     automatic rule relaxation, automatic `symbol_limit`
     expansion, automatic anomaly threshold changes,
     automatic candidate-pool capacity changes,
     automatic Regime weight changes, or any Risk Engine
     / Execution FSM change.
  7. **High `capture_recall_rate` does NOT authorise live
     trading.** Even
     `eligible_capture_recall_rate=1.0` over the 60D
     backfill does **not** authorise live orders, API
     keys, private endpoints, DeepSeek trade decisions,
     real Telegram outbound, AI Learning, automatic
     parameter optimisation, reinforcement learning, or
     Phase 12.
  8. **Low `capture_recall_rate` does NOT authorise
     parameter changes.** A low recall is a `review`
     outcome only. The audit must **not** be retro-fit
     around the past — no thresholds, weights,
     symbol-limits, or capacities may be changed on the
     basis of historical movers (this would be "looking
     at the answer key", which the audit forbids by
     construction).

## Forbidden by this PR (carries forward verbatim + slice-specific items)

  - Real trading.
  - Live trading.
  - Binance API key / secret.
  - Signed endpoint / `listenKey` / private WebSocket.
  - Account / order / position / leverage / margin
    endpoint.
  - DeepSeek trade decision.
  - Real Telegram outbound.
  - AI deciding direction / position size / leverage /
    stop / target / execution.
  - Automatic parameter optimisation.
  - Reinforcement learning.
  - AI Learning that auto-decides trades.
  - Auto-rule-relaxation on low coverage.
  - Auto-rule-relaxation on a single-coin / "妖币" case.
  - Auto-rule-relaxation on the basis of historical
    movers ("looking at the answer key").
  - Automatic `symbol_limit` expansion.
  - Automatic anomaly threshold changes.
  - Automatic candidate-pool capacity changes.
  - Automatic Regime weight changes.
  - Auto-scheduling B1 / B2 / B3+ runs from runtime
    code.
  - Risk Engine override / bypass.
  - Execution FSM override / bypass.
  - Phase Gate override / bypass.
  - Triggering a real trade from any audit artefact.
  - Modifying position size / leverage / stop-loss /
    target price from any audit artefact.
  - Modifying the Risk Engine or the Execution FSM from
    any audit artefact.
  - Replacing the Mover Capture Recall & Missed-Tail
    Coverage Audit v0 `DEGRADED` rule with a relaxed
    rule.
  - Replacing the Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
    with a relaxed rule.
  - Replacing the Long-Window Cohort Stability & Sample
    Sufficiency Protocol v0 cadence with a relaxed
    cadence.
  - Implementing the Historical 60D Mover Coverage
    Backfill Audit v0 as a new runtime module — the
    slice is intentionally **docs / evidence template
    only** end-to-end at kickoff; if a future need for a
    new runtime module emerges, it must be opened as a
    separate child slice with its own kickoff /
    implementation / closeout cycle.
  - Implementing the complete Strategy Validation Lab
    follow-up (reserved for later child slices under
    Phase 11C.1C-C-B-B-B).
  - Treating Phase 11C.1C-C-B-B-B-D-A as a Historical
    30D+ / 60D *complete strategy* blind replay /
    walk-forward validation. **It is not.** That gate
    belongs after the major paper modules and the paper
    validation chain are complete, before small-money
    live trading, as a Phase 12 candidate pre-gate.
  - Adding new Python modules under `app/`.
  - Adding new event types.
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/`.
  - Modifying configuration schemas, defaults, or YAML.
  - Adding or modifying tests.
  - Running tests.
  - Modifying strategy runtime code.
  - Modifying runtime behaviour.
  - Implementing new functionality.
  - Flipping any phase's acceptance state. Phase
    11C.1C-C-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-D remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-D-A remains `NEXT_ALLOWED /
    NOT_STARTED` (this PR scopes the slice; it does not
    flip its state). Phase 12 remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
    its existing definition — *Strategy Validation Lab
    (deeper) & richer Cluster Exposure Control
    follow-up*.
  - Phase 11C.1C-C-B-B-B-D-A *implementation* (out of
    scope; will be a separate PR if needed; even then
    must be docs / evidence-template-driven where
    possible).
  - Phase 11C.1C-C-B-B-B-D-A *closeout* (out of scope;
    will be authored after the operator captures B1 /
    B2 backfill audit evidence and a separate docs-only
    closeout PR flips the slice to `ACCEPTED`).
  - Phase 11C.1C-C-B-B-B-D-B / further child slices (out
    of scope; will require their own kickoff PRs).
  - Phase 12 / live trading kickoff.

## Acceptance gate (docs-only)

  - Docs-only PR. **No code modified** under `app/`,
    `scripts/`, `tests/`, `configs/`, `risk/`,
    `execution/`, `llm/`, `telegram/`, or `exchange/`.
  - **No new Python files.**
  - **No new event types.**
  - **No new tests.**
  - **No tests run.**
  - **No dry-run / smoke required** (no runtime change).
  - **No phase acceptance state flipped.**
  - Safety boundary held end-to-end (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - **Phase 12 remains FORBIDDEN.**

## Confirmation checklist

  - [x] **Changed files** —
    `docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md`
    (NEW), `docs/PR63_DESCRIPTION.md` (NEW),
    `docs/PHASE_GATE.md`, `docs/PROJECT_STATUS.md`,
    `docs/CHANGELOG.md`.
  - [x] **Confirm docs-only.** No runtime code modified.
  - [x] **Confirm no `app/` / `scripts/` / `tests/` /
    `configs/` changes.**
  - [x] **Confirm no `execution/` / `risk/` / `llm/` /
    `telegram/` / `exchange/` changes.**
  - [x] **Confirm no strategy runtime code changes.**
  - [x] **Confirm no new Python files.**
  - [x] **Confirm no new event types.**
  - [x] **Confirm no new tests.**
  - [x] **Confirm no tests run.**
  - [x] **Confirm no runtime behaviour changed.**
  - [x] **Confirm Phase 11C.1C-C-B-B-B-D remains
    `ACCEPTED`.**
  - [x] **Confirm Phase 11C.1C-C-B-B-B-D-A =
    `NEXT_ALLOWED / NOT_STARTED`** (defined as
    *Historical 60D Mover Coverage Backfill Audit v0 /
    历史 60 天异动币覆盖回填审计 v0*).
  - [x] **Confirm Phase 12 = `FORBIDDEN`.**
  - [x] No phase's acceptance state flipped — Phase
    11C.1C-C-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`;
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-D remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-D-A remains `NEXT_ALLOWED /
    NOT_STARTED` (scoped by this PR; not flipped).
  - [x] Phase 11C.1C-C-B-B-B parent is **not** renamed;
    it remains *Strategy Validation Lab (deeper) &
    richer Cluster Exposure Control follow-up*.
  - [x] Phase 11C.1C-C-B-B-B-D-A is recorded as the next
    allowed child slice on top of the
    Phase 11C.1C-C-B-B-B-D track = Historical 60D Mover
    Coverage Backfill Audit v0 / *历史 60 天异动币覆盖
    回填审计 v0*.
  - [x] Audit cadence recorded (B1 / B2 with B3+
    reserved; operator-driven; not auto-scheduled).
  - [x] Audit input sources recorded (Binance public
    24 h ticker / public klines / public market data,
    `EventRepository` / events.db, daily report, Phase
    8.5 export bundle / Phase 10A replay bundle over the
    60D window, `StrategyValidationDataset`,
    `PaperAlphaGateReport`, `RegimeClusterEvidencePack`,
    `MoverCaptureRecallAuditReport`, `SymbolUniverse` /
    `exchangeInfo`-as-truth catalogue, candidate pool
    logs / capacity-eviction evidence).
  - [x] Audit objects recorded (60D top gainers / top
    movers / high-momentum movers in eligible USDT
    perpetual universe, 60D detected anomalies, 60D
    pre-anomaly candidates, 60D label-tracked
    candidates, 60D validation samples, 60D risk-rejected
    captured movers, 60D excluded symbols).
  - [x] 60D top-mover reference set fields recorded
    verbatim (`reference_window_start_utc`,
    `reference_window_end_utc`, `top_mover_symbol`,
    `top_mover_rank`, `max_window_gain`,
    `max_24h_gain`, `reference_timestamp_utc`,
    `eligible_usdt_perpetual`).
  - [x] Per-captured-mover audit row recorded verbatim
    (`top_mover_symbol`, `mover_window_start_utc`,
    `mover_window_end_utc`, `top_mover_rank`,
    `max_window_gain`, `max_24h_gain`,
    `eligible_usdt_perpetual`, `system_captured`,
    `first_seen_time_utc`, `first_seen_event_type`,
    `first_seen_latency_seconds`, `capture_path_depth`,
    `reached_anomaly`, `reached_label_queue`,
    `reached_tail_label`,
    `reached_strategy_validation_sample`,
    `risk_rejected`, `status`, `miss_reason`).
  - [x] Fixed `miss_reason` taxonomy recorded verbatim
    (`not_in_futures_universe`,
    `symbol_not_in_exchange_info`, `not_usdt_perpetual`,
    `missing_historical_reference_data`,
    `missing_event_history`,
    `below_liquidity_threshold`,
    `symbol_limit_excluded`, `candidate_pool_evicted`,
    `insufficient_ws_data`, `stale_data`,
    `data_unreliable`, `no_anomaly_threshold_cross`,
    `risk_rejected`, `no_completed_tail_label_yet`,
    `unknown`).
  - [x] Allowed outputs explicitly listed
    (`historical_60d_mover_reference_set`,
    `historical_60d_capture_path_audit`,
    `historical_60d_miss_reason_summary`,
    `historical_60d_first_seen_summary`,
    `historical_60d_capture_recall_summary`,
    `historical_60d_coverage_warning`,
    `historical_60d_export_replay_evidence_template`)
    and marked descriptive only.
  - [x] Eight interpretation principles recorded
    verbatim (captured ≠ tradable; captured early ≠
    strategy profitable; missed and
    not-in-futures-universe ≠ system failure; missed
    and in-eligible-universe IS a coverage warning;
    `risk_rejected` ≠ discovery failure; `missed` and
    `unknown` are `review` signals; high recall does
    NOT authorise live trading; low recall does NOT
    authorise parameter changes / "looking at the
    answer key").
  - [x] Slice-specific forbidden items recorded
    (cannot trigger real trades / modify position size
    / modify leverage / modify stops / modify targets /
    modify Risk Engine / modify Execution FSM; cannot
    let AI decide direction or sizing or leverage or
    stops or targets or execution; cannot auto-optimise
    parameters; cannot auto-relax rules; cannot
    auto-expand `symbol_limit`; cannot auto-change
    anomaly thresholds; cannot auto-change
    candidate-pool capacity; cannot auto-change Regime
    weights; cannot use historical results to
    retro-tune any threshold ("looking at the answer
    key"); cannot auto-schedule B1 / B2 / B3+; cannot
    replace existing `DEGRADED` /
    `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` rules with
    relaxed rules; cannot replace Long-Window Cohort
    Stability & Sample Sufficiency Protocol v0 cadence;
    cannot stand in for Historical 30D+ / 60D
    *complete strategy* blind replay / walk-forward
    validation; cannot enter Phase 12).
  - [x] Safety boundary held end-to-end (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - [x] Phase 12 remains `FORBIDDEN`.

## Why a separate child slice (and not B-B-B-D itself)?

The deeper Phase 11C.1C-C-B-B follow-up under the parent
Phase 11C.1C-C-B-B-B is broad: richer cohort comparisons,
extended cluster heuristics, longer-window correlations,
dataset-driven retrospective audits, alpha-evidence gates,
discovery-layer coverage audits, and historical
discovery-layer coverage backfills are *all* candidate
slices. Four child slices have already shipped (B-B-B-A —
Paper Alpha Gate v0; B-B-B-B — Regime & Cluster Cohort
Evidence Pack v0; B-B-B-C — Long-Window Cohort Stability
& Sample Sufficiency Protocol v0; B-B-B-D — Mover Capture
Recall & Missed-Tail Coverage Audit v0). Bundling further
work into a single PR would conflate independent design
decisions, risk overscope, and break the established
pattern of small, auditable child slices (Phase
11C.1C-C-A → Phase 11C.1C-C-B-A → Phase 11C.1C-C-B-B-A →
Phase 11C.1C-C-B-B-B-A → Phase 11C.1C-C-B-B-B-B → Phase
11C.1C-C-B-B-B-C → Phase 11C.1C-C-B-B-B-D → Phase
11C.1C-C-B-B-B-D-A).

Phase 11C.1C-C-B-B-B-D-A therefore carves out **only**
the *Historical 60D Mover Coverage Backfill Audit v0* —
a docs / evidence-template-only audit protocol that
codifies the discovery-layer historical coverage check,
the missed-mover reason taxonomy, the recall-rate
metrics, and the eight interpretation rules that protect
against single-coin reframing **and** retro-fitting
thresholds against the historical reference set. This
directly applies the AMOS governance
(`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`) to
the next concrete step: **add fewer modules, accumulate
more structural data; verify Regime more, talk less
about "strategy"; and prove which states really carry
right-tail value rather than chase a universal model**.
The audit proves whether the discovery layer covered
real market movers over the past 60 days; it does **not**
prove the strategy can trade.

## Out of scope (handled by future PRs in the cycle)

The substantive Phase 11C.1C-C-B-B-B-D-A closeout — the
verbatim B1 / B2 operator-driven backfill audit
transcripts, the `historical_60d_capture_recall_summary`
/ `historical_60d_miss_reason_summary` /
`historical_60d_first_seen_summary` /
`historical_60d_coverage_warning` artefacts, the Phase
8.5 export evidence over the 60D window, and the
safety-flag invariants — is **out of scope** for this
docs-only kickoff. It will be authored alongside a future
docs-only closeout PR after the operator captures the
B1 / B2 backfill audit evidence on the operator-VPS, and
reviewed against the Phase 1 safety lock + the AMOS
governance rails in
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` (Truth
Layer / Reality Check / Anti-overfitting / Feedback
Isolation / Limited Complexity).

The Historical 30D+ / 60D *complete strategy* blind
replay / walk-forward validation gate is **not** in scope
for this slice. That gate is a **separate, larger gate**
that belongs **after** the core paper modules and the
paper validation chain are complete and **before** any
small-money live trading. It is one of the candidate
Phase 12 pre-gates.
