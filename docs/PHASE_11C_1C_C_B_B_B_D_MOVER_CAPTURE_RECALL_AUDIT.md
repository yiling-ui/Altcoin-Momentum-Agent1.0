# Phase 11C.1C-C-B-B-B-D — Mover Capture Recall & Missed-Tail Coverage Audit v0

> **Chinese name / 中文名:** *异动币捕捉召回与漏捕右尾覆盖审计 v0*.
>
> **Status: NEXT_ALLOWED / NOT_STARTED (defined in place by
> this docs-only kickoff PR #60; this PR scopes the slice;
> it does not flip its state).** This document opens Phase
> 11C.1C-C-B-B-B-D as the **fourth child slice** under the
> Phase 11C.1C-C-B-B-B parent (*Strategy Validation Lab
> (deeper) & richer Cluster Exposure Control follow-up*).
> The parent phase is **not** renamed; it keeps its
> existing definition. Phase 11C.1C-C-B-B-B-A (*Paper
> Alpha Gate v0*) remains `ACCEPTED` (PR #52 + PR #54
> closeout). Phase 11C.1C-C-B-B-B-B (*Regime & Cluster
> Cohort Evidence Pack v0*) remains `ACCEPTED` (PR #56 +
> PR #57 closeout). Phase 11C.1C-C-B-B-B-C (*Long-Window
> Cohort Stability & Sample Sufficiency Protocol v0*)
> remains `ACCEPTED` (PR #58 docs-only kickoff + PR #59
> docs-only closeout). Phase 11C.1C-C-B-B-B-E (next child
> slice, if any) remains undefined and is not opened by
> this PR.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> new strategy. **NOT** a trading module. **NOT** a new
> runtime module. **NOT** the complete Strategy Validation
> Lab follow-up. **NOT** a Historical 30D+ Blind Replay /
> Walk-forward Validation gate (that gate is reserved for
> Phase 12 candidate review and is **not** in scope here).
> **NOT** the Phase 11C.1C-C-B-B-B-D *implementation* (the
> implementation, if any, requires a separate PR — and even
> then will be evidence-template / docs-driven only, not a
> new runtime module). **NOT** Phase 12.
>
> The Risk Engine remains the single trade-decision gate.
> Every artefact this slice defines (top-mover capture
> summaries, captured-mover evidence rows, missed-mover
> audit rows, symbol-universe exclusion summaries,
> candidate-eviction summaries, risk-rejection summaries,
> first-seen latency summaries, capture recall rates,
> missed-tail candidate lists, coverage warnings,
> insufficient-coverage reasons) is a **descriptive
> document / evidence template** for human review and
> **MUST NEVER trigger a real trade**, **MUST NEVER**
> modify position size, leverage, stop-loss, target price,
> the Risk Engine, or the Execution FSM.

## Why this slice exists (positioning under AMOS)

This slice is a direct application of the
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` governance
to the next concrete step under Phase 11C.1C-C-B-B-B. AMOS
treats AMA-RT as an *Adaptive Market Operating System*: the
goal is **long-term stable operation, adaptation to market
structural change, and the ability to capture 5x+ altcoin
right-tail upside in short-term moves when it is genuinely
available** — **not** promising returns, **not** running an
auto-strategy bot, and **not** letting AI drive execution.

Under that frame, the project's main line for this period
must converge on:

  - **Add fewer modules; accumulate more structural data.**
  - **Talk less about "strategy"; verify Regime more.**
  - **Stop chasing a universal model; prove which states
    really carry right-tail value.**

The trigger for Phase 11C.1C-C-B-B-B-D is concrete and
measurable, and it is *different* from the trigger for
Phase 11C.1C-C-B-B-B-C:

  - Phase 11C.1C-C-B-B-B-C proved that **long-window
    paper data collection** works end-to-end (W1 / W1+ 2 h
    PASS, W2 4 h PASS, W3 24 h upper-bound early-stop
    PASS at `total_elapsed_seconds=900` with
    `final_tail_labels_since_start=20>=10`). Sample
    sufficiency, export evidence chain, and per-window
    `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` conservatism
    all hold.
  - **However**: B-B-B-C answered "*can the system
    accumulate enough structural samples over time?*". It
    did **not** answer "*are the samples the system
    accumulates the right ones?*" — i.e., does the
    discovery layer actually cover real market movers, or
    is the system collecting a self-selected subset that
    happens to satisfy our own thresholds?
  - The operator observed an external case during the
    B-B-B-C window: SAGAUSDT showed an obvious move on
    Binance's public 24 h gainer board. Cross-checking
    against AMA-RT's own events, SAGAUSDT was in fact
    captured end-to-end:
    `PRE_ANOMALY_DETECTED` →
    `ANOMALY_DETECTED` →
    `MARKET_REGIME_ASSESSED` →
    `CANDIDATE_STAGE_CLASSIFIED` →
    `OPPORTUNITY_SCORED` →
    `STRATEGY_MODE_SELECTED` →
    `CLUSTER_CONTEXT_ATTACHED` →
    `LABEL_QUEUE_ENQUEUED` →
    `LABEL_TRACKING_STARTED` →
    `TAIL_LABEL_ASSIGNED` →
    `STRATEGY_VALIDATION_SAMPLE_CREATED`.
  - SAGAUSDT alone proves nothing. Confirming a single
    mover by hand also proves nothing about coverage in
    general. **The right next step is therefore to
    institutionalise "human looks at the gainer board vs.
    did the system see it" as a coverage audit** — and
    define exactly what counts as captured, missed,
    correctly excluded, or genuinely missed.

Phase 11C.1C-C-B-B-B-D codifies that step as a **paper-only
coverage audit protocol**. It does **not** add a new
strategy module, a new AI authority, or a new optimiser.
It does **not** prove the strategy can trade. It only
proves whether the **discovery layer** covers real market
movers.

## Phase boundary (parent / child relationship)

  - **Phase 11C.1C-C-A** — `ACCEPTED` (PR #40 merged into
    `main`, 2026-05-23, mergeCommit `75d3c7c`). Provides
    `LABEL_TRACKING_*` / `LABEL_WINDOW_*` /
    `TAIL_LABEL_ASSIGNED` outcomes per ACTIVE candidate.
  - **Phase 11C.1C-C-B-A** — `ACCEPTED` (PR #42 merged into
    `main`, 2026-05-23, mergeCommit `cc18047`). Provides
    `StrategyValidationSample`, `StrategyValidationReport`,
    `ClusterExposureAssessment`, `suggested_cluster_action`
    artefacts.
  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 merged
    into `main`, 2026-05-23, mergeCommit `3ecfc3b`).
    Provides `StrategyValidationDataset` /
    `StrategyValidationQualityGate` artefacts.
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    *Parent* phase. Strategy Validation Lab (deeper) &
    richer Cluster Exposure Control follow-up. **Not
    renamed** by this kickoff.
  - **Phase 11C.1C-C-B-B-B-A** — `ACCEPTED` (PR #52 merged
    into `main`, 2026-05-24, mergeCommit `f8ba315`; closeout
    via PR #54). First child slice. Paper Alpha Gate v0.
  - **Phase 11C.1C-C-B-B-B-B** — `ACCEPTED` (PR #56 merged
    into `main`, 2026-05-24, mergeCommit `1a9abe2`; closeout
    via PR #57). Second child slice. Regime & Cluster Cohort
    Evidence Pack v0.
  - **Phase 11C.1C-C-B-B-B-C** — `ACCEPTED` (PR #58
    docs-only kickoff merged into `main`; PR #59 docs-only
    closeout merged into `main`, 2026-05-25). Third child
    slice. Long-Window Cohort Stability & Sample
    Sufficiency Protocol v0 / *长窗口 Cohort 稳定性与样本
    充足协议 v0*.
  - **Phase 11C.1C-C-B-B-B-D** — *this document*.
    `NEXT_ALLOWED / NOT_STARTED`. **Fourth child slice**
    under Phase 11C.1C-C-B-B-B. Mover Capture Recall &
    Missed-Tail Coverage Audit v0 / *异动币捕捉召回与漏捕
    右尾覆盖审计 v0*. Docs / evidence-template only. No new
    runtime module. No new event type. No trade authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Scope (what this slice IS)

Phase 11C.1C-C-B-B-B-D is a **paper-only, report-only,
evidence-only coverage audit protocol slice**. It defines
the audit cadence, the audit objects, the per-mover
evidence shape, the recall metrics, the
missed-mover-reason taxonomy, the interpretation rules,
and the evidence-template shape that the operator and any
future closeout PR must follow.

The audit answers seven explicit questions, **and only
these seven**:

  1. **Did real market movers get captured by the system?**
  2. **If captured, at which discovery layer?** Allowed
     layers (in order):
       - `MARKET_SNAPSHOT`
       - `PRE_ANOMALY_DETECTED`
       - `ANOMALY_DETECTED`
       - `MARKET_REGIME_ASSESSED`
       - `CANDIDATE_STAGE_CLASSIFIED`
       - `OPPORTUNITY_SCORED`
       - `STRATEGY_MODE_SELECTED`
       - `CLUSTER_CONTEXT_ATTACHED`
       - `LABEL_QUEUE_ENQUEUED`
       - `LABEL_TRACKING_STARTED`
       - `LABEL_WINDOW_COMPLETED`
       - `TAIL_LABEL_ASSIGNED`
       - `STRATEGY_VALIDATION_SAMPLE_CREATED`
  3. **If not captured, why?** Allowed missed-mover
     reasons (taxonomy; this slice does **not** introduce
     new reasons beyond this list):
       - `not_in_futures_universe`
       - `not_in_exchange_info`
       - `not_usdt_perpetual`
       - `symbol_limit_excluded`
       - `candidate_pool_capacity_evicted`
       - `score_too_low`
       - `liquidity_insufficient`
       - `data_stale_or_degraded_or_unreliable`
       - `risk_rejected`
       - `no_completed_tail_label_yet`
  4. **Were the top movers captured early enough?**
     (`first_seen_latency_seconds` per captured mover,
     and `median_first_seen_latency_seconds` per audit
     window.)
  5. **Did captured movers proceed into the label /
     validation pipeline?** (`label_tracking_rate`,
     `tail_label_assigned_rate`,
     `strategy_validation_sample_rate`.)
  6. **Are missed movers a system-coverage problem or a
     market / exchange-coverage problem?** (i.e., out of
     `not_in_futures_universe` /
     `not_in_exchange_info` / `not_usdt_perpetual`
     vs. system-side reasons.)
  7. **Were captured movers that were rejected by the
     Risk Engine rejected for sound conservative reasons?**
     (Risk-rejected movers are recorded as
     `risk_rejected_mover_count` and are explicitly
     **not** treated as system failures.)

The audit produces only descriptive output. It does
**not** decide trades. It does **not** widen or relax any
existing threshold. It does **not** override the Risk
Engine, the Execution FSM, the SymbolUniverse, the
candidate pool capacity, or any other runtime gate.

### Why this is *not* a new runtime module

The discovery-layer events (`PRE_ANOMALY_DETECTED`,
`ANOMALY_DETECTED`, `MARKET_REGIME_ASSESSED`,
`CANDIDATE_STAGE_CLASSIFIED`, `OPPORTUNITY_SCORED`,
`STRATEGY_MODE_SELECTED`, `CLUSTER_CONTEXT_ATTACHED`,
`LABEL_QUEUE_ENQUEUED`, `LABEL_TRACKING_STARTED`,
`LABEL_WINDOW_COMPLETED`, `TAIL_LABEL_ASSIGNED`,
`STRATEGY_VALIDATION_SAMPLE_CREATED`) are already emitted
by Phase 11C.1B → Phase 11C.1C-C-B-A. The Phase 8.5 export
bundle, the Phase 10A replay engine, the
`StrategyValidationDataset`, the `PaperAlphaGateReport`,
the `RegimeClusterEvidencePack`, the SymbolUniverse, the
exchangeInfo-as-truth catalogue, and the candidate pool
logs all exist on `main`. The Binance public 24 h ticker
endpoint is already reachable through the existing public
REST surface. **Nothing new needs to ship in `app/` to
support a Mover Capture Recall & Missed-Tail Coverage
Audit.** The path forward is to define the audit shape and
the evidence template, and run the existing pipeline with
an external "what did Binance's public 24 h gainer board
look like during this same window?" reference series.

### Why this is *not* a Historical 30D+ Blind Replay

A Historical 30D+ Blind Replay / Walk-forward Validation
is a **separate, larger gate** that belongs **after** the
core paper modules and the paper validation chain are
complete and **before** any small-money live trading. It
is one of the candidate Phase 12 pre-gates. It is **not**
in scope here.

Phase 11C.1C-C-B-B-B-D is a **paper-time** coverage audit
of the discovery layer running against **live public
market data**, not a historical playback. It does not make
walk-forward claims. It does not score the strategy
against historical right-tail outcomes. It does not need
30 days of blind data to operate; even a single-window
audit is meaningful as long as it answers the seven
coverage questions above.

## Audit cadence (operator-driven; not auto-scheduled)

This kickoff PR records the cadence shape only. The
substantive cadence numbers (audit window length, audit
window count, top-N gainer cutoff, etc.) will be authored
alongside the next PR in the cycle. None of these
parameters is auto-scheduled by this PR — the operator
runs the audit manually on the operator-VPS, in the order
recorded below.

| Audit window | Purpose | Auto-scheduled? |
| ------------ | ------- | --------------- |
| **A1**       | First end-to-end coverage audit pass against a single paper observation window. Validates that the audit transcript shape is well-formed and that the seven coverage questions can each be answered for that window. | **No.** Operator-driven. |
| **A2**       | Repeat against a second, longer paper observation window (e.g., one of the B-B-B-C W1 / W2 / W3 windows). Validates that recall rates, missed-mover reasons, and first-seen latencies are stable across at least two independent windows. | **No.** Operator-driven. |
| **A3+**      | Reserved for later child slices (under Phase 11C.1C-C-B-B-B or a successor parent). Captures cross-day / cross-regime coverage drift. **Out of scope for this PR.** **Not implemented in this PR.** | **No.** **Out of scope for this PR.** |

This PR **must not** implement an automatic scheduler, an
auto-trigger, or any runtime change that drives A1 / A2 /
A3+ on a clock. The cadence is **operator-driven** and
recorded as a **protocol**, not as code.

## Audit input sources (read-only; reuse existing surfaces)

The audit is allowed to consume — **read-only** — these
existing surfaces. It does **not** introduce new ingestion
paths:

  - Binance **public** 24 h ticker / public market data
    (the same public REST surface already governed by
    Phase 11C.1A's rate-limit governor; not a private
    endpoint).
  - `EventRepository` (the existing events.db), to extract
    the discovery-layer events listed above.
  - The daily report (existing Phase 11B + 11C sections).
  - The Phase 8.5 export bundle and the Phase 10A replay
    bundle.
  - `StrategyValidationDataset` (Phase 11C.1C-C-B-B-A
    artefact).
  - `PaperAlphaGateReport` (Phase 11C.1C-C-B-B-B-A
    artefact).
  - `RegimeClusterEvidencePack` (Phase 11C.1C-C-B-B-B-B
    artefact).
  - `SymbolUniverse` and `exchangeInfo`-as-truth catalogue
    (Phase 11C.1B artefacts).
  - Candidate pool logs / capacity-eviction evidence,
    where available from existing runtime instrumentation.

The audit is **not** allowed to consume:

  - Any private / signed Binance endpoint.
  - Any account / order / position / leverage / margin
    endpoint.
  - Any private WebSocket or `listenKey`.
  - Any DeepSeek trade-decision authority.
  - Any real Telegram outbound channel.
  - Any new ingestion path not already on `main`.

## Audit objects (what this slice audits)

The audit operates on these object classes — **all of
them paper-side**:

  - **Top gainers / top movers** in the eligible USDT
    perpetual universe (sourced from Binance's public 24 h
    ticker and intersected with `SymbolUniverse` /
    `exchangeInfo`-as-truth).
  - **Detected anomalies** during the audit window
    (sourced from `ANOMALY_DETECTED` events).
  - **Pre-anomaly candidates** during the audit window
    (sourced from `PRE_ANOMALY_DETECTED` events).
  - **Label-tracked candidates** (sourced from
    `LABEL_TRACKING_STARTED`, `LABEL_WINDOW_COMPLETED`,
    and `TAIL_LABEL_ASSIGNED` events).
  - **Validation samples** (sourced from
    `STRATEGY_VALIDATION_SAMPLE_CREATED` events).
  - **Risk-rejected movers** (sourced from existing
    risk-decision events on the candidate, where the
    candidate is a confirmed top-mover for the same
    window).
  - **Movers excluded because not in current tradable
    universe** (sourced from `SymbolUniverse` /
    `exchangeInfo` cross-check; reasons recorded under
    the missed-mover taxonomy).

## Allowed outputs (docs / evidence templates only)

Each is a **descriptive document, evidence row, or
summary**. None has trade authority. None is read by the
Risk Engine or the Execution FSM. None is a new Python
module, a new event type, or a new runtime hook:

  - `top_mover_capture_summary` — per audit-window summary
    of the eligible top-mover universe and how many of
    them the system observed at any discovery layer.
  - `captured_mover_evidence` — one row per captured
    mover, with `symbol`, the highest discovery layer
    reached during the audit window, the chain of
    discovery-layer events emitted for that symbol, and
    `first_seen_latency_seconds` (relative to the audit
    window start, or to the move's first appearance on
    the public 24 h gainer board).
  - `missed_mover_audit` — one row per missed mover, with
    `symbol`, the missed-mover reason from the taxonomy,
    and a free-text "operator note" field for human
    review.
  - `symbol_universe_exclusion_summary` — counts and
    examples of movers excluded because they were
    `not_in_futures_universe` /
    `not_in_exchange_info` /
    `not_usdt_perpetual` /
    `symbol_limit_excluded`.
  - `candidate_eviction_summary` — counts and examples of
    movers that the candidate pool evicted under
    capacity pressure (`candidate_pool_capacity_evicted`).
  - `risk_rejection_summary` — counts and examples of
    captured movers that the Risk Engine rejected
    (`risk_rejected`); recorded as **conservative
    rejections, not failures**.
  - `first_seen_latency_summary` — distribution of
    `first_seen_latency_seconds` across captured movers
    in the audit window, including
    `median_first_seen_latency_seconds`.
  - `capture_recall_rate` — ratio of
    `captured_top_mover_count` /
    `top_mover_count`, rounded conservatively, recorded
    as a **descriptive ratio**.
  - `missed_tail_candidate_list` — list of movers that
    were missed *and* (per the public 24 h ticker) showed
    a clear right-tail return. **The protocol is biased
    toward "do nothing"** about this list — it is a
    coverage warning, not a strategy directive.
  - `coverage_warning` — an optional warning string raised
    when missed-tail candidates fall in the eligible
    USDT-perpetual universe and exhibit clear right-tail
    behaviour but were not captured for any
    system-correctable reason.
  - `insufficient_coverage_reasons` — verbatim list of
    reasons the audit did not produce a confident
    coverage verdict (e.g., audit window too short, gainer
    board sample too thin, public ticker stale, exchange
    info refresh outdated, etc.).

These outputs are **only** allowed forms. Any artefact
that implies a real-trade authority, a position-sizing
recommendation, a leverage decision, a stop-loss target,
an Execution FSM transition, an automatic threshold
widening, or an automatic schedule is **out of scope** and
forbidden.

## Key metrics (descriptive only)

The audit records the following metrics **per audit
window**. They are descriptive only. **None** is consumed
by the Risk Engine, the Execution FSM, or any other
runtime gate. **None** is used to auto-relax thresholds or
auto-promote any signal. None is a new event type — the
metrics are derived inside the audit transcript only.

| Metric                                  | Meaning |
| --------------------------------------- | ------- |
| `top_mover_count`                       | Total top movers from Binance public 24 h ticker, intersected with the eligible USDT-perpetual universe, for the audit window. |
| `captured_top_mover_count`              | Subset of `top_mover_count` for which the system emitted at least one discovery-layer event during the audit window. |
| `missed_top_mover_count`                | `top_mover_count - captured_top_mover_count`. |
| `capture_recall_rate`                   | `captured_top_mover_count / top_mover_count` (descriptive ratio; conservative rounding). |
| `anomaly_detected_rate`                 | Share of captured movers that reached `ANOMALY_DETECTED`. |
| `label_tracking_rate`                   | Share of captured movers that reached `LABEL_TRACKING_STARTED`. |
| `tail_label_assigned_rate`              | Share of captured movers that reached `TAIL_LABEL_ASSIGNED`. |
| `strategy_validation_sample_rate`       | Share of captured movers that reached `STRATEGY_VALIDATION_SAMPLE_CREATED`. |
| `risk_rejected_mover_count`             | Captured movers that the Risk Engine rejected. **Not** treated as a system failure. |
| `not_in_universe_count`                 | Movers excluded because `not_in_futures_universe` / `not_in_exchange_info` / `not_usdt_perpetual` (i.e., market / exchange-coverage reasons, not system reasons). |
| `capacity_evicted_count`                | Movers excluded because the candidate pool was at capacity. |
| `data_unreliable_count`                 | Movers excluded because data for the symbol was stale / degraded / unreliable for that audit window. |
| `median_first_seen_latency_seconds`     | Median of `first_seen_latency_seconds` across captured movers. |

## Interpretation principles (must be read verbatim)

The audit's central interpretation rules — these MUST be
applied verbatim by every audit run, every closeout PR,
and every reviewer:

  1. **Captured-but-rejected ≠ failure.** A mover that was
     captured by the discovery layer and then rejected by
     the Risk Engine is recorded under
     `risk_rejected_mover_count`. **Risk-rejection is a
     conservative paper outcome, not a coverage failure.**
     The Risk Engine remains the single trade-decision
     gate.
  2. **Missed-but-not-in-universe ≠ failure.** A mover
     that does not exist in the futures universe / does
     not exist in `exchangeInfo` / is not a USDT
     perpetual is **out of scope** for AMA-RT by design.
     Recording it under `not_in_universe_count` is
     **expected**; treating it as a coverage failure is
     wrong.
  3. **Coverage warning is only raised when the mover is
     in the eligible universe AND shows a clear
     right-tail signal AND was missed for a
     system-correctable reason** (e.g., score too low,
     candidate pool capacity, data stale). A warning is
     **not** an authorisation to relax any rule.
  4. **A single mover proves nothing.** SAGAUSDT being
     captured end-to-end (the trigger case for this
     slice) does **not** prove the strategy is effective.
     Conversely, a single missed mover does **not** prove
     the discovery layer is broken. Coverage claims must
     be made over an audit window with a non-trivial
     `top_mover_count`.
  5. **Capture audit ≠ trading-profit evidence.** The
     audit only proves whether the **discovery layer**
     covers real market movers. It does **not** prove
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
     Even if the audit returns
     `capture_recall_rate=1.0` and every captured mover
     proceeded all the way to
     `STRATEGY_VALIDATION_SAMPLE_CREATED`, this slice's
     acceptance does **not** authorise live orders, API
     keys, private endpoints, DeepSeek trade decisions,
     real Telegram outbound, AI Learning, automatic
     parameter optimisation, reinforcement learning, or
     Phase 12. Phase 12 remains `FORBIDDEN`.
  8. **Single-coin or "妖币" reframing is forbidden.** The
     audit must not be retro-fit around a single coin
     (SAGAUSDT or anything else). Rules cannot be
     widened, thresholds cannot be relaxed, and universe
     filters cannot be dropped on the basis of a single
     case study.

These eight rules carry forward into every closeout PR.
Reviewers may not waive them.

## Boundary (must hold from day one)

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
| `listenKey` / user data stream              | refused                      |
| Private WebSocket / trading WS API          | refused                      |
| Routed-private endpoint (`/private`)        | refused                      |
| DeepSeek trade-decision authority           | NOT permitted                |
| Real Telegram outbound                      | NOT permitted                |
| Risk Engine authority                       | unchanged; remains the single trade-decision gate |
| Execution FSM authority                     | unchanged                    |
| SymbolUniverse / exchangeInfo-as-truth      | unchanged; audit only **reads** it |
| Candidate pool capacity                     | unchanged; audit only **reads** eviction evidence |
| Position size / leverage / stop-loss / target price | unchanged; cannot be modified by any audit output |
| `top_mover_capture_summary`                 | descriptive document only; MUST NEVER trigger a real trade |
| `captured_mover_evidence`                   | descriptive document only; MUST NEVER trigger a real trade |
| `missed_mover_audit`                        | descriptive document only; MUST NEVER trigger a real trade |
| `symbol_universe_exclusion_summary`         | descriptive document only; MUST NEVER trigger a real trade |
| `candidate_eviction_summary`                | descriptive document only; MUST NEVER trigger a real trade |
| `risk_rejection_summary`                    | descriptive document only; MUST NEVER trigger a real trade |
| `first_seen_latency_summary`                | descriptive document only; MUST NEVER trigger a real trade |
| `capture_recall_rate`                       | descriptive ratio only; MUST NEVER trigger a real trade |
| `missed_tail_candidate_list`                | descriptive document only; MUST NEVER trigger a real trade |
| `coverage_warning`                          | descriptive document only; MUST NEVER trigger a real trade |
| `insufficient_coverage_reasons`             | descriptive document only; MUST NEVER trigger a real trade |
| AI authority                                | NOT permitted to decide direction / position size / leverage / stop / target / execution |
| Automatic parameter optimisation            | NOT permitted                |
| Reinforcement learning                      | NOT permitted                |
| Auto-rule-relaxation on low coverage        | NOT permitted                |
| Auto-rule-relaxation on a single-coin case  | NOT permitted                |
| Automatic scheduling of A1 / A2 / A3+       | NOT permitted in this PR     |
| Historical 30D+ Blind Replay / Walk-forward | NOT in scope for this PR (reserved as a separate Phase 12 candidate pre-gate) |
| Phase 12 (live trading)                     | FORBIDDEN                    |

## Explicitly forbidden by this slice

This slice carries forward every Phase 1 / 11C.1B / 11C.1C-A
/ 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A /
11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C
forbidden item verbatim, and adds the following
slice-specific forbidden items:

  - Triggering a real trade.
  - Modifying position size.
  - Modifying leverage.
  - Modifying stop-loss.
  - Modifying target price.
  - Modifying the Risk Engine.
  - Modifying the Execution FSM.
  - Letting AI / LLM decide direction, position size,
    leverage, stop-loss, target price, or execution.
  - Auto-optimising parameters in response to coverage
    audit outputs.
  - Auto-relaxing rules in response to low coverage
    audits.
  - Auto-relaxing rules in response to a single-coin or
    "妖币" case.
  - Auto-scheduling A1 / A2 / A3+ runs from runtime code.
  - Promoting any audit artefact (top-mover capture
    summary, captured-mover evidence, missed-mover audit,
    universe exclusion summary, eviction summary,
    risk-rejection summary, first-seen latency summary,
    capture recall rate, missed-tail candidate list,
    coverage warning, insufficient-coverage reasons) to a
    real-trade authority.
  - Replacing the Regime & Cluster Cohort Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule with a relaxed rule. The
    audit consumes it; it does not rewrite it.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
    with a relaxed rule. The audit consumes it; it does
    not rewrite it.
  - Adding new event types in this kickoff PR.
  - Adding new event types in any future Phase
    11C.1C-C-B-B-B-D PR. (The slice is intentionally
    **docs / evidence template only** end-to-end; if a
    future need for a new runtime module emerges, it must
    be opened as a separate child slice with its own
    kickoff / implementation / closeout cycle.)
  - Adding new Python modules under `app/` in this kickoff
    PR.
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/` in this kickoff PR.
  - Modifying configuration schemas, defaults, or YAML in
    this kickoff PR.
  - Adding or modifying tests in this kickoff PR.
  - Running tests as part of this kickoff PR.
  - Treating Phase 11C.1C-C-B-B-B-D as a Historical 30D+
    Blind Replay / Walk-forward Validation. **It is
    not.** That gate belongs after the major paper
    modules and the paper validation chain are complete,
    before small-money live trading, as a Phase 12
    candidate pre-gate.
  - Flipping any phase's acceptance state. Phase
    11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED /
    NOT_STARTED` (this PR scopes the slice; it does not
    flip its state). Phase 12 remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
    its existing definition.
  - Phase 11C.1C-C-B-B-B-D *closeout* (out of scope; will
    be authored after the operator captures A1 / A2 audit
    evidence and a separate docs-only closeout PR flips
    the slice to `ACCEPTED`).
  - Phase 11C.1C-C-B-B-B-E / further child slices (out of
    scope; will require their own kickoff PRs).
  - Phase 12 / live trading kickoff.

## Acceptance gate (placeholder; to be detailed by the closeout PR)

The Phase 11C.1C-C-B-B-B-D closeout PR (a **future**
docs-only PR; not this one) will be authored only **after**
the operator-VPS captures the A1 / A2 audit evidence
required by this protocol. The placeholders below record
what the gate is **expected** to require, so the closeout
PR is reviewed against a known shape:

  - A1 (first end-to-end coverage audit pass) operator-VPS
    evidence captured verbatim, including:
      - audit window start / end timestamps,
      - `top_mover_count`,
      - `captured_top_mover_count`,
      - `missed_top_mover_count`,
      - `capture_recall_rate`,
      - `anomaly_detected_rate`,
      - `label_tracking_rate`,
      - `tail_label_assigned_rate`,
      - `strategy_validation_sample_rate`,
      - `risk_rejected_mover_count`,
      - `not_in_universe_count`,
      - `capacity_evicted_count`,
      - `data_unreliable_count`,
      - `median_first_seen_latency_seconds`,
      - per-captured-mover evidence rows,
      - per-missed-mover audit rows,
      - any `coverage_warning` raised,
      - any `insufficient_coverage_reasons` recorded.
  - A2 (second audit pass against an independent paper
    observation window) operator-VPS evidence captured
    verbatim, including the same fields.
  - A simple cross-window stability check: for any signal
    that this slice would otherwise call out as a
    coverage warning, the warning must persist across A1
    and A2; one-window-only warnings are recorded but not
    elevated.
  - At least one window in which the Phase 8.5 export
    bundle includes the discovery-layer events used by
    the audit (`PRE_ANOMALY_DETECTED`, `ANOMALY_DETECTED`,
    `MARKET_REGIME_ASSESSED`, `CANDIDATE_STAGE_CLASSIFIED`,
    `OPPORTUNITY_SCORED`, `STRATEGY_MODE_SELECTED`,
    `CLUSTER_CONTEXT_ATTACHED`, `LABEL_QUEUE_ENQUEUED`,
    `LABEL_TRACKING_STARTED`, `LABEL_WINDOW_COMPLETED`,
    `TAIL_LABEL_ASSIGNED`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED`).
  - Phase 10A replay engine accepts each window's export
    bundle without raising.
  - Safety flags unchanged across every audit window
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by any audit.
  - No new event type emitted by any audit.
  - No audit artefact is read by the Risk Engine or the
    Execution FSM.
  - Phase 12 stays `FORBIDDEN`.

The protocol explicitly accepts "we still do not have
enough coverage data" as a valid closeout result, exactly
the way Phase 11C.1C-C-B-B-B-A and Phase 11C.1C-C-B-B-B-B
accepted `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` smoke
results, and the way Phase 11C.1C-C-B-B-B-C accepted W1 /
W1+ / W2 windows whose
`completed_tail_label_count<10`. **Either outcome is
acceptable** as long as the audit transcript is
well-formed and the safety lock holds.

## What this kickoff PR does

  - **Defines** Phase 11C.1C-C-B-B-B-D as the *Mover
    Capture Recall & Missed-Tail Coverage Audit v0 / 异动
    币捕捉召回与漏捕右尾覆盖审计 v0* — the fourth child
    slice under Phase 11C.1C-C-B-B-B.
  - **Records** the audit cadence (A1 / A2 with A3+
    reserved), audit input sources, audit objects, allowed
    outputs (docs / evidence templates only), key metrics,
    the eight interpretation principles, the boundary
    table, slice-specific forbidden items, and the
    acceptance-gate placeholder in this document.
  - **Refreshes** the Phase 11C.1C-C-B-B-B-D placeholder
    text in `docs/PHASE_GATE.md` and
    `docs/PROJECT_STATUS.md` so the slice is now defined
    by name and scope, while remaining `NEXT_ALLOWED /
    NOT_STARTED`.
  - **Refreshes** the *Architecture governance
    (guidance-only; no phase change)* closing paragraph in
    `docs/PHASE_GATE.md` to reflect the current open-phase
    state (B-B-B-A = ACCEPTED; B-B-B-B = ACCEPTED;
    B-B-B-C = ACCEPTED; B-B-B = NEXT_ALLOWED /
    NOT_STARTED; B-B-B-D = NEXT_ALLOWED / NOT_STARTED with
    full scope; Phase 12 = FORBIDDEN).
  - **Records** this PR in `docs/CHANGELOG.md > [Unreleased]`
    and `docs/PR60_DESCRIPTION.md`.

## What this kickoff PR does NOT do

  - It does **NOT** flip any phase's acceptance state.
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-C remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-D remains `NEXT_ALLOWED /
    NOT_STARTED` (this PR scopes the slice; it does not
    flip its state). Phase 12 remains `FORBIDDEN`.
  - It does **NOT** rename Phase 11C.1C-C-B-B-B.
  - It does **NOT** add any new Python module under
    `app/`.
  - It does **NOT** add any new event type.
  - It does **NOT** modify any runtime behaviour.
  - It does **NOT** modify configuration schemas,
    defaults, or YAML.
  - It does **NOT** add or modify tests.
  - It does **NOT** run tests.
  - It does **NOT** widen, replace, or relax the existing
    Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` minimums or the Paper Alpha
    Gate v0 `INCONCLUSIVE` minimums or the Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0
    cadence.
  - It does **NOT** authorise live trading, API keys,
    private endpoints, DeepSeek trade decisions, real
    Telegram outbound, AI Learning, automatic parameter
    optimisation, reinforcement learning, the complete
    Strategy Validation Lab follow-up, or Phase 12.
  - It does **NOT** authorise any rule relaxation on the
    basis of single-coin / "妖币" cases (SAGAUSDT or
    otherwise).
  - It does **NOT** stand in for a Historical 30D+ Blind
    Replay / Walk-forward Validation gate (that gate is
    reserved for a Phase 12 candidate review and is
    explicitly out of scope here).
  - It does **NOT** modify `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `llm/`,
    `telegram/`, or `exchange/`.

## Safety flags after this PR (Phase 1 lock unchanged)

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
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```
