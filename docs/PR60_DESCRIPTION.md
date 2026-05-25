# PR #60 — Phase 11C.1C-C-B-B-B-D: Mover Capture Recall & Missed-Tail Coverage Audit v0 (docs-only kickoff)

> **Status: DOCS-ONLY KICKOFF / SCOPE ALIGNMENT.** This PR
> defines Phase 11C.1C-C-B-B-B-D (*Mover Capture Recall &
> Missed-Tail Coverage Audit v0 / 异动币捕捉召回与漏捕右尾
> 覆盖审计 v0*) as the **fourth child slice** under the
> Phase 11C.1C-C-B-B-B parent. The parent phase is **not**
> renamed: Phase 11C.1C-C-B-B-B remains *Strategy Validation
> Lab (deeper) & richer Cluster Exposure Control follow-up*.
> **No runtime code is shipped by this PR.** **No phase's
> acceptance state is flipped.** Phase 11C.1C-C-B-B-B-D
> remains `NEXT_ALLOWED / NOT_STARTED`; this PR scopes the
> slice in place.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> new strategy. **NOT** a trading module. **NOT** a new
> runtime module. **NOT** the complete Strategy Validation
> Lab follow-up. **NOT** Phase 11C.1C-C-B-B-B-D *closeout*
> (the closeout will be a separate docs-only PR after the
> operator captures A1 / A2 audit evidence). **NOT** a
> Historical 30D+ Blind Replay / Walk-forward Validation
> gate (that gate is reserved for a Phase 12 candidate
> review and is explicitly out of scope here; it belongs
> after the major paper modules and the paper validation
> chain are complete, before small-money live trading).
> **NOT** Phase 12.
>
> The Mover Capture Recall & Missed-Tail Coverage Audit v0
> is **paper-only / report-only / evidence-only** end to
> end. It does not add a new runtime module, a new event
> type, a new strategy, a new execution surface, a new
> optimiser, or a new AI authority. It defines the coverage
> audit cadence (A1 / A2 with A3+ reserved), the audit
> input sources, the audit objects, the per-mover evidence
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
    Cohort Stability & Sample Sufficiency Protocol v0 /
    *长窗口 Cohort 稳定性与样本充足协议 v0*.
  - **Phase 11C.1C-C-B-B-B-D** — *defined by this PR*.
    `NEXT_ALLOWED / NOT_STARTED`. **Fourth child slice**
    under Phase 11C.1C-C-B-B-B. Mover Capture Recall &
    Missed-Tail Coverage Audit v0 / *异动币捕捉召回与漏捕
    右尾覆盖审计 v0*. Docs / evidence-template only. No
    new runtime module. No new event type. No trade
    authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Branch + base

  - Branch:
    `docs/phase-11c1c-c-b-b-b-d-mover-capture-recall-kickoff`
  - Base: `main` (post PR #59 closeout).

## What this PR does

  - **Defines** Phase 11C.1C-C-B-B-B-D as the *Mover
    Capture Recall & Missed-Tail Coverage Audit v0 / 异动
    币捕捉召回与漏捕右尾覆盖审计 v0* — the fourth child
    slice under Phase 11C.1C-C-B-B-B.
  - **Records** the **why** for this slice: PR #58
    docs-only kickoff merged Phase 11C.1C-C-B-B-B-C in
    place; PR #59 closeout flipped B-B-B-C to `ACCEPTED`
    on the basis of operator-VPS W1 / W1+ 2 h, W2 4 h, and
    W3 24 h upper-bound early-stop paper WS evidence —
    proving that **long-window paper data collection works
    end-to-end**. B-B-B-C did **not** answer "are the
    samples the system collects the right ones?" — i.e.,
    does the discovery layer actually cover real market
    movers? The operator observed an external case during
    the B-B-B-C window: SAGAUSDT showed an obvious move on
    Binance's public 24 h gainer board, and the system
    captured SAGAUSDT end-to-end through the full
    discovery chain (`PRE_ANOMALY_DETECTED` →
    `ANOMALY_DETECTED` → `MARKET_REGIME_ASSESSED` →
    `CANDIDATE_STAGE_CLASSIFIED` → `OPPORTUNITY_SCORED` →
    `STRATEGY_MODE_SELECTED` → `CLUSTER_CONTEXT_ATTACHED`
    → `LABEL_QUEUE_ENQUEUED` → `LABEL_TRACKING_STARTED` →
    `TAIL_LABEL_ASSIGNED` →
    `STRATEGY_VALIDATION_SAMPLE_CREATED`). One coin proves
    nothing; the right next step is to **institutionalise
    "human looks at the gainer board vs. did the system
    see it" as a coverage audit** — and define exactly
    what counts as captured, missed, correctly excluded,
    or genuinely missed. This is a **paper-only**,
    **report-only**, **evidence-only** coverage audit of
    the **discovery layer**; it is **not** a strategy
    validation, **not** a trading-profit measurement, and
    **not** a Historical 30D+ Blind Replay / Walk-forward
    Validation.
  - **Defines** the seven coverage questions the audit
    answers, **and only these seven**:
      1. Did real market movers get captured by the
         system?
      2. If captured, at which discovery layer?
         (`MARKET_SNAPSHOT` / `PRE_ANOMALY_DETECTED` /
         `ANOMALY_DETECTED` / `MARKET_REGIME_ASSESSED` /
         `CANDIDATE_STAGE_CLASSIFIED` /
         `OPPORTUNITY_SCORED` / `STRATEGY_MODE_SELECTED` /
         `CLUSTER_CONTEXT_ATTACHED` /
         `LABEL_QUEUE_ENQUEUED` / `LABEL_TRACKING_STARTED`
         / `LABEL_WINDOW_COMPLETED` /
         `TAIL_LABEL_ASSIGNED` /
         `STRATEGY_VALIDATION_SAMPLE_CREATED`.)
      3. If not captured, why? Allowed missed-mover
         reasons (taxonomy): `not_in_futures_universe`,
         `not_in_exchange_info`, `not_usdt_perpetual`,
         `symbol_limit_excluded`,
         `candidate_pool_capacity_evicted`,
         `score_too_low`, `liquidity_insufficient`,
         `data_stale_or_degraded_or_unreliable`,
         `risk_rejected`, `no_completed_tail_label_yet`.
      4. Were the top movers captured early enough?
         (`first_seen_latency_seconds` per captured mover,
         `median_first_seen_latency_seconds` per audit
         window.)
      5. Did captured movers proceed into the label /
         validation pipeline? (`label_tracking_rate`,
         `tail_label_assigned_rate`,
         `strategy_validation_sample_rate`.)
      6. Are missed movers a system-coverage problem or a
         market / exchange-coverage problem?
      7. Were captured-but-rejected movers rejected for
         sound conservative reasons?
         (`risk_rejected_mover_count` is **not** treated
         as a system failure.)
  - **Defines** the audit cadence (operator-driven; not
    auto-scheduled):
      - **A1 — first end-to-end coverage audit pass.**
      - **A2 — second audit pass against an independent
        paper observation window.**
      - **A3+ — reserved for later child slices; out of
        scope for this PR; not implemented in this PR.**
  - **Defines** the audit input sources (read-only; reuse
    existing surfaces):
      - Binance **public** 24 h ticker / public market
        data (existing public REST surface; Phase 11C.1A
        rate-limit governor; not a private endpoint).
      - `EventRepository` (existing events.db).
      - Daily report (existing Phase 11B + 11C sections).
      - Phase 8.5 export bundle / Phase 10A replay bundle.
      - `StrategyValidationDataset` (Phase
        11C.1C-C-B-B-A artefact).
      - `PaperAlphaGateReport` (Phase 11C.1C-C-B-B-B-A
        artefact).
      - `RegimeClusterEvidencePack` (Phase
        11C.1C-C-B-B-B-B artefact).
      - `SymbolUniverse` and `exchangeInfo`-as-truth
        catalogue (Phase 11C.1B artefacts).
      - Candidate pool logs / capacity-eviction evidence
        (where available from existing runtime
        instrumentation).
  - **Defines** the audit objects:
      - Top gainers / top movers in the eligible USDT
        perpetual universe.
      - Detected anomalies during the audit window.
      - Pre-anomaly candidates during the audit window.
      - Label-tracked candidates.
      - Validation samples.
      - Risk-rejected movers.
      - Movers excluded because not in the current
        tradable universe.
  - **Lists** the allowed outputs (docs / evidence
    templates only):
      - `top_mover_capture_summary`
      - `captured_mover_evidence`
      - `missed_mover_audit`
      - `symbol_universe_exclusion_summary`
      - `candidate_eviction_summary`
      - `risk_rejection_summary`
      - `first_seen_latency_summary`
      - `capture_recall_rate`
      - `missed_tail_candidate_list`
      - `coverage_warning`
      - `insufficient_coverage_reasons`
  - **Lists** the key metrics (descriptive only):
      - `top_mover_count`
      - `captured_top_mover_count`
      - `missed_top_mover_count`
      - `capture_recall_rate`
      - `anomaly_detected_rate`
      - `label_tracking_rate`
      - `tail_label_assigned_rate`
      - `strategy_validation_sample_rate`
      - `risk_rejected_mover_count`
      - `not_in_universe_count`
      - `capacity_evicted_count`
      - `data_unreliable_count`
      - `median_first_seen_latency_seconds`
  - **Records** the eight interpretation principles
    (must be read verbatim):
      1. Captured-but-rejected ≠ failure (Risk Engine
         remains the single trade-decision gate).
      2. Missed-but-not-in-universe ≠ failure (out of
         scope by design).
      3. Coverage warning is only raised when the mover
         is in the eligible universe AND shows clear
         right-tail behaviour AND was missed for a
         system-correctable reason.
      4. A single mover proves nothing (SAGAUSDT
         specifically does not authorise rule
         relaxation).
      5. Capture audit ≠ trading-profit evidence
         (separate, larger gate).
      6. Low coverage is a `review` outcome, not a
         `relax` outcome.
      7. High coverage does not authorise live trading.
      8. Single-coin / "妖币" reframing is forbidden.
  - **Records** the boundary table and the slice-specific
    forbidden items (carries forward verbatim from
    B-B-B-A / B-B-B-B / B-B-B-C + adds slice-specific
    items for coverage audit).
  - **Refreshes** the Phase 11C.1C-C-B-B-B-D placeholder
    sections in `docs/PHASE_GATE.md` and
    `docs/PROJECT_STATUS.md` so the slice is now defined
    by name and scope, while remaining `NEXT_ALLOWED /
    NOT_STARTED`.
  - **Refreshes** the *Architecture governance
    (guidance-only; no phase change)* closing paragraph
    in `docs/PHASE_GATE.md` to reflect the current
    open-phase state (B-B-B-A = ACCEPTED; B-B-B-B =
    ACCEPTED; B-B-B-C = ACCEPTED; B-B-B = NEXT_ALLOWED /
    NOT_STARTED; B-B-B-D = NEXT_ALLOWED / NOT_STARTED
    with full scope; Phase 12 = FORBIDDEN).
  - **Records** this PR in `docs/CHANGELOG.md >
    [Unreleased]` and `docs/PR60_DESCRIPTION.md`.

## What this PR does NOT do

  - It does **NOT** flip any phase's acceptance state.
  - It does **NOT** rename Phase 11C.1C-C-B-B-B.
  - It does **NOT** implement the Mover Capture Recall &
    Missed-Tail Coverage Audit v0 — the audit is defined
    as docs / evidence templates only, and the slice will
    not introduce any new runtime module or new event
    type at any point in its lifecycle.
  - It does **NOT** auto-schedule A1 / A2 / A3+ runs.
    The cadence is operator-driven.
  - It does **NOT** widen, replace, or relax the existing
    Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` minimums or the Paper Alpha
    Gate v0 `INCONCLUSIVE` minimums or the Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0
    cadence.
  - It does **NOT** authorise any rule relaxation on the
    basis of single-coin / "妖币" cases (SAGAUSDT or
    otherwise).
  - It does **NOT** stand in for a Historical 30D+ Blind
    Replay / Walk-forward Validation gate (that gate is
    reserved for a Phase 12 candidate review and is
    explicitly out of scope here).
  - It does **NOT** add any new Python module under
    `app/`.
  - It does **NOT** add any new event type.
  - It does **NOT** modify any runtime behaviour.
  - It does **NOT** modify configuration schemas,
    defaults, or YAML.
  - It does **NOT** add or modify tests.
  - It does **NOT** run tests.
  - It does **NOT** authorise live trading, API keys,
    private endpoints, DeepSeek trade decisions, real
    Telegram outbound, AI Learning, automatic parameter
    optimisation, reinforcement learning, the complete
    Strategy Validation Lab follow-up, or Phase 12.
  - It does **NOT** modify `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `llm/`,
    `telegram/`, or `exchange/`.

## Changed files

```
docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md   (NEW)
docs/PR60_DESCRIPTION.md                                     (NEW)
docs/PHASE_GATE.md                                           (modified — docs-only)
docs/PROJECT_STATUS.md                                       (modified — docs-only)
docs/CHANGELOG.md                                            (modified — docs-only)
```

No file under `app/`, `scripts/`, `tests/`, `configs/`,
`risk/`, `execution/`, `llm/`, `telegram/`, or `exchange/`
is touched.

## Allowed file edits

  - `docs/PROJECT_STATUS.md`
  - `docs/PHASE_GATE.md`
  - `docs/CHANGELOG.md`
  - `docs/PHASE_11C_1C_C_B_B_B_D_MOVER_CAPTURE_RECALL_AUDIT.md`
    (NEW)
  - `docs/PR60_DESCRIPTION.md` (NEW; this document)

## Allowed outputs (docs / evidence templates only) — recorded for future PRs in the cycle

Each is a **descriptive document, evidence row, or
summary**. None has trade authority. None is read by the
Risk Engine or the Execution FSM. None is a new Python
module, a new event type, or a new runtime hook:

  - `top_mover_capture_summary`
  - `captured_mover_evidence`
  - `missed_mover_audit`
  - `symbol_universe_exclusion_summary`
  - `candidate_eviction_summary`
  - `risk_rejection_summary`
  - `first_seen_latency_summary`
  - `capture_recall_rate`
  - `missed_tail_candidate_list`
  - `coverage_warning`
  - `insufficient_coverage_reasons`

## Audit cadence (operator-driven; not auto-scheduled)

  - **A1 — first end-to-end coverage audit pass.**
  - **A2 — second audit pass against an independent
    paper observation window.**
  - **A3+ — reserved for later child slices; out of
    scope for this PR.**

This PR **must not** implement an automatic scheduler, an
auto-trigger, or any runtime change that drives A1 / A2 /
A3+ on a clock. The cadence is **operator-driven** and
recorded as a **protocol**, not as code.

## Interpretation principles (carry forward verbatim)

  1. **Captured-but-rejected ≠ failure.** A mover that
     was captured by the discovery layer and then
     rejected by the Risk Engine is recorded under
     `risk_rejected_mover_count`. **Risk-rejection is a
     conservative paper outcome, not a coverage failure.**
  2. **Missed-but-not-in-universe ≠ failure.** A mover
     not in the futures universe / not in `exchangeInfo`
     / not USDT perpetual is **out of scope** by design;
     recording it under `not_in_universe_count` is
     **expected**.
  3. **Coverage warning is only raised when the mover is
     in the eligible universe AND shows a clear
     right-tail signal AND was missed for a
     system-correctable reason.** A warning is **not** an
     authorisation to relax any rule.
  4. **A single mover proves nothing.** SAGAUSDT being
     captured end-to-end (the trigger case) does **not**
     prove the strategy is effective; conversely, a
     single missed mover does **not** prove the discovery
     layer is broken.
  5. **Capture audit ≠ trading-profit evidence.** The
     audit only proves whether the **discovery layer**
     covers real market movers; it does **not** prove
     trading profit, trading edge, strategy correctness,
     or risk-adjusted return. Those claims require a
     separate, larger gate (Historical 30D+ Blind Replay /
     Walk-forward Validation) which is **not** in scope.
  6. **Low coverage is a `review` outcome, not a `relax`
     outcome.** If `capture_recall_rate` is low, the
     correct response is to record the result, queue a
     human review, and consider whether the system is
     missing a structural piece — **not** to widen
     thresholds, drop universe filters, or weaken the
     Risk Engine.
  7. **High coverage does not authorise live trading.**
     Even `capture_recall_rate=1.0` does **not**
     authorise live orders, API keys, private endpoints,
     DeepSeek trade decisions, real Telegram outbound, AI
     Learning, automatic parameter optimisation,
     reinforcement learning, or Phase 12.
  8. **Single-coin or "妖币" reframing is forbidden.**
     The audit must not be retro-fit around a single
     coin (SAGAUSDT or anything else).

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
  - Auto-rule-relaxation on a single-coin / "妖币"
    case.
  - Auto-scheduling A1 / A2 / A3+ runs from runtime
    code.
  - Risk Engine override / bypass.
  - Execution FSM override / bypass.
  - Phase Gate override / bypass.
  - Triggering a real trade from any audit artefact.
  - Modifying position size / leverage / stop-loss /
    target price from any audit artefact.
  - Modifying the Risk Engine or the Execution FSM from
    any audit artefact.
  - Replacing the Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE`
    rule with a relaxed rule.
  - Replacing the Long-Window Cohort Stability & Sample
    Sufficiency Protocol v0 cadence with a relaxed
    cadence.
  - Implementing the Mover Capture Recall & Missed-Tail
    Coverage Audit v0 as a new runtime module — the
    slice is intentionally **docs / evidence template
    only** end-to-end; if a future need for a new runtime
    module emerges, it must be opened as a separate child
    slice with its own kickoff / implementation /
    closeout cycle.
  - Implementing the complete Strategy Validation Lab
    follow-up (reserved for later child slices under
    Phase 11C.1C-C-B-B-B).
  - Treating Phase 11C.1C-C-B-B-B-D as a Historical 30D+
    Blind Replay / Walk-forward Validation. **It is
    not.** That gate belongs after the major paper
    modules and the paper validation chain are complete,
    before small-money live trading, as a Phase 12
    candidate pre-gate.
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
    11C.1C-C-B-B-B-D remains `NEXT_ALLOWED / NOT_STARTED`
    (this PR scopes the slice; it does not flip its
    state). Phase 12 remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
    its existing definition — *Strategy Validation Lab
    (deeper) & richer Cluster Exposure Control follow-up*.
  - Phase 11C.1C-C-B-B-B-D *closeout* (out of scope; will
    be authored after the operator captures A1 / A2 audit
    evidence and a separate docs-only closeout PR flips
    the slice to `ACCEPTED`).
  - Phase 11C.1C-C-B-B-B-E / further child slices (out of
    scope; will require their own kickoff PRs).
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

  - [x] Docs-only PR; no runtime code modified.
  - [x] No new Python files.
  - [x] No new event types.
  - [x] No new tests.
  - [x] No tests run.
  - [x] No runtime behaviour changed.
  - [x] No `app/` / `scripts/` / `tests/` / `configs/`
    changes.
  - [x] No `execution/` / `risk/` / `llm/` / `telegram/`
    / `exchange/` changes.
  - [x] No strategy runtime code changes.
  - [x] No phase's acceptance state flipped — Phase
    11C.1C-C-B-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`;
    Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED /
    NOT_STARTED` (scoped by this PR; not flipped).
  - [x] Phase 11C.1C-C-B-B-B parent is **not** renamed;
    it remains *Strategy Validation Lab (deeper) & richer
    Cluster Exposure Control follow-up*.
  - [x] Phase 11C.1C-C-B-B-B-D is recorded as the fourth
    child slice under Phase 11C.1C-C-B-B-B = Mover
    Capture Recall & Missed-Tail Coverage Audit v0 /
    异动币捕捉召回与漏捕右尾覆盖审计 v0.
  - [x] Audit cadence recorded (A1 / A2 with A3+
    reserved; operator-driven; not auto-scheduled).
  - [x] Audit input sources recorded (Binance public 24 h
    ticker / public market data, `EventRepository`, daily
    report, Phase 8.5 export / Phase 10A replay,
    `StrategyValidationDataset`, `PaperAlphaGateReport`,
    `RegimeClusterEvidencePack`, `SymbolUniverse` /
    `exchangeInfo`-as-truth catalogue, candidate pool
    logs / capacity-eviction evidence).
  - [x] Audit objects recorded (top gainers / top movers
    in eligible USDT-perpetual universe, detected
    anomalies, pre-anomaly candidates, label-tracked
    candidates, validation samples, risk-rejected movers,
    movers excluded because not in current tradable
    universe).
  - [x] Allowed outputs explicitly listed
    (`top_mover_capture_summary`,
    `captured_mover_evidence`, `missed_mover_audit`,
    `symbol_universe_exclusion_summary`,
    `candidate_eviction_summary`,
    `risk_rejection_summary`,
    `first_seen_latency_summary`, `capture_recall_rate`,
    `missed_tail_candidate_list`, `coverage_warning`,
    `insufficient_coverage_reasons`) and marked
    descriptive only.
  - [x] Key metrics recorded
    (`top_mover_count`, `captured_top_mover_count`,
    `missed_top_mover_count`, `capture_recall_rate`,
    `anomaly_detected_rate`, `label_tracking_rate`,
    `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`,
    `risk_rejected_mover_count`,
    `not_in_universe_count`, `capacity_evicted_count`,
    `data_unreliable_count`,
    `median_first_seen_latency_seconds`).
  - [x] Eight interpretation principles recorded verbatim
    (captured-but-rejected ≠ failure;
    missed-but-not-in-universe ≠ failure; coverage
    warning only when in eligible universe AND clear
    right-tail AND system-correctable reason; a single
    mover incl. SAGAUSDT proves nothing; capture audit ≠
    trading-profit evidence; low coverage = `review`,
    not `relax`; high coverage does not authorise live
    trading; single-coin / "妖币" reframing is
    forbidden).
  - [x] Slice-specific forbidden items recorded
    (cannot trigger real trades / modify position size /
    modify leverage / modify stops / modify targets /
    modify Risk Engine / modify Execution FSM / let AI
    decide direction or sizing or leverage or stops or
    targets or execution / auto-optimise parameters /
    auto-relax rules / auto-schedule A1 / A2 / A3+;
    cannot replace Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule; cannot replace Paper
    Alpha Gate v0 `INCONCLUSIVE` rule; cannot replace
    Long-Window Cohort Stability & Sample Sufficiency
    Protocol v0 cadence; cannot stand in for Historical
    30D+ Blind Replay / Walk-forward Validation; cannot
    enter Phase 12).
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

## Why a separate child slice (and not B-B-B itself)?

The deeper Phase 11C.1C-C-B-B follow-up under the parent
Phase 11C.1C-C-B-B-B is broad: richer cohort comparisons,
extended cluster heuristics, longer-window correlations,
dataset-driven retrospective audits, alpha-evidence gates,
and discovery-layer coverage audits are *all* candidate
slices. Three child slices have already shipped (B-B-B-A
— Paper Alpha Gate v0; B-B-B-B — Regime & Cluster Cohort
Evidence Pack v0; B-B-B-C — Long-Window Cohort Stability
& Sample Sufficiency Protocol v0). Bundling further work
into a single PR would conflate independent design
decisions, risk overscope, and break the established
pattern of small, auditable child slices (Phase
11C.1C-C-A → Phase 11C.1C-C-B-A → Phase 11C.1C-C-B-B-A →
Phase 11C.1C-C-B-B-B-A → Phase 11C.1C-C-B-B-B-B → Phase
11C.1C-C-B-B-B-C → Phase 11C.1C-C-B-B-B-D).

Phase 11C.1C-C-B-B-B-D therefore carves out **only** the
*Mover Capture Recall & Missed-Tail Coverage Audit v0* —
a docs / evidence-template-only audit protocol that
codifies the discovery-layer coverage check, the
missed-mover reason taxonomy, the recall-rate metrics, and
the eight interpretation rules that protect against
single-coin reframing. This directly applies the AMOS
governance
(`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`) to
the next concrete step: **add fewer modules, accumulate
more structural data; verify Regime more, talk less about
"strategy"; and prove which states really carry right-tail
value rather than chase a universal model**. The audit
proves the discovery layer covers real market movers; it
does **not** prove the strategy can trade.

## Out of scope (handled by future PRs in the cycle)

The substantive Phase 11C.1C-C-B-B-B-D closeout — the
verbatim A1 / A2 operator-VPS coverage audit transcripts,
the cross-window stability checklist results, and the
Phase 8.5 export / Phase 10A replay round-trip evidence —
is **out of scope** for this docs-only kickoff. It will be
authored alongside a future docs-only closeout PR after
the operator captures the A1 / A2 audit evidence on the
operator-VPS, and reviewed against the Phase 1 safety lock
+ the AMOS governance rails in
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` (Truth
Layer / Reality Check / Anti-overfitting / Feedback
Isolation / Limited Complexity).

The Historical 30D+ Blind Replay / Walk-forward Validation
gate is **not** in scope for this slice. That gate is a
**separate, larger gate** that belongs **after** the core
paper modules and the paper validation chain are complete
and **before** any small-money live trading. It is one of
the candidate Phase 12 pre-gates.
