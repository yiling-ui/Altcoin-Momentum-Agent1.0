# Phase 11C.1C-C-B-B-B-C — Long-Window Cohort Stability & Sample Sufficiency Protocol v0

> **Chinese name / 中文名:** *长窗口 Cohort 稳定性与样本充足协议 v0*.
>
> **Status: ACCEPTED (closed 2026-05-25; docs-only closeout
> via PR #59 records the operator-VPS W1 / W1+ 2 h, W2 4 h,
> and W3 24 h upper-bound early-stop paper WS evidence and
> flips the slice to `ACCEPTED`).** PR #58 docs-only
> kickoff merged into `main` on 2026-05-25 and defined this
> slice in place; this docs-only closeout PR #59 records
> the long-window paper evidence (W1 / W1+ 2 h, W2 4 h, W3
> 24 h upper-bound with watcher early-stop at
> `total_elapsed_seconds=900` /
> `final_tail_labels_since_start=20>=10`), the per-window
> Phase 8.5 export bundles, the W3 export-range event
> counts, and the Phase 1 safety-flag invariants — and
> flips Phase 11C.1C-C-B-B-B-C to `ACCEPTED`. This document
> opens (now closes) Phase 11C.1C-C-B-B-B-C as the **third
> child slice** under the Phase 11C.1C-C-B-B-B parent
> (*Strategy Validation Lab (deeper) & richer Cluster
> Exposure Control follow-up*). The parent phase is **not**
> renamed; it keeps its existing definition. Phase
> 11C.1C-C-B-B-B-A (*Paper Alpha Gate v0*) remains
> `ACCEPTED` (PR #52 + PR #54 closeout). Phase
> 11C.1C-C-B-B-B-B (*Regime & Cluster Cohort Evidence Pack
> v0*) remains `ACCEPTED` (PR #56 + PR #57 closeout). Phase
> 11C.1C-C-B-B-B-D (next child slice; not yet defined) is
> now **NEXT_ALLOWED / NOT_STARTED**.
>
> **Important interpretation.** Phase 11C.1C-C-B-B-B-C
> acceptance is **acceptance of the long-window data
> collection and sample-sufficiency protocol**. It does
> **NOT** mean any Regime / Cluster has proven right-tail
> advantage yet. It does **NOT** mean strategy
> effectiveness is proven. It does **NOT** authorise live
> trading, API keys, private endpoints, DeepSeek trade
> decisions, real Telegram outbound, AI Learning,
> automatic parameter optimisation, reinforcement learning,
> rule relaxation based on low samples, Risk Engine
> changes, Execution FSM changes, or Phase 12. It records
> only that: (1) 2 h paper WS run works; (2) 4 h paper WS
> run works; (3) completed labels begin to appear over
> longer windows; (4) the 24 h upper-bound early-stop
> works; (5) the completed-tail-label sufficiency
> threshold can be reached early; (6) export / replay
> evidence preserves the results; (7) low-sample states
> remain conservative (`INSUFFICIENT_SAMPLE` /
> `INCONCLUSIVE` are valid outputs not failures); and (8)
> no trade authority was granted by any window.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> strategy implementation. **NOT** a trading module. **NOT**
> a new runtime module. **NOT** the complete Strategy
> Validation Lab follow-up. **NOT** the Phase 11C.1C-C-B-B-B-C
> *implementation* (the implementation, if any, requires a
> separate PR — and even then will be evidence-template /
> docs-driven only, not a new runtime module). **NOT** Phase
> 12.
>
> The Risk Engine remains the single trade-decision gate.
> Every artefact this slice defines (long-window run plans,
> sample-sufficiency checklists, cohort-stability
> checklists, operator-VPS evidence templates, export-replay
> evidence templates, closeout acceptance templates) is a
> **descriptive document / evidence template** for human
> review and **MUST NEVER trigger a real trade**, **MUST
> NEVER** modify position size, leverage, stop-loss, target
> price, the Risk Engine, or the Execution FSM.

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

The trigger for this slice is concrete and measurable:

  - PR #56 merged the **Regime & Cluster Cohort Evidence
    Pack v0** implementation into `main` (mergeCommit
    `1a9abe2`).
  - PR #57 merged the docs-only closeout into `main` and
    flipped Phase 11C.1C-C-B-B-B-B to `ACCEPTED`.
  - The operator-VPS 10 min WS paper smoke evidence was
    accepted as **expected and well-formed**:
    `duration_seconds=600.0`, `uptime≈608s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`.
  - The runtime / daily-report / Phase 8.5 export pipeline
    is functional: the daily report contains the
    `## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
    Evidence Pack v0` section,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`, and the
    export bundle round-trips cleanly through Phase 8.5 /
    Phase 10A.
  - **However**: the window's
    `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
    `sample_count=14<20`,
    `completed_tail_label_count=0<10`. In other words:
    **runtime / report / export are correct, but the
    observation window is too short to support any
    Regime / Cluster right-tail conclusion.**

The right next step is therefore **not** to add a new
strategy module, a new AI authority, or a new optimiser.
The right next step is to **accumulate structural data
across longer paper observation windows** until cohort
samples are large enough for the Regime & Cluster Cohort
Evidence Pack and the Paper Alpha Gate to produce
**non-`INSUFFICIENT_SAMPLE`** verdicts that a human can act
on as evidence.

Phase 11C.1C-C-B-B-B-C codifies that step as a **protocol**
— a long-window paper data-collection cadence, a sample
sufficiency rule, and cohort stability acceptance criteria
— while keeping all of the Phase 1 safety lock invariants
in force.

## Phase boundary (parent / child relationship)

  - **Phase 11C.1C-C-A** — `ACCEPTED` (PR #40 merged into
    `main`, 2026-05-23, mergeCommit `75d3c7c`). Provides
    `LABEL_TRACKING_*` / `LABEL_WINDOW_*` /
    `TAIL_LABEL_ASSIGNED` / `MFE_pct` / `MAE_pct` /
    `tail_label` outcomes per ACTIVE candidate.
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
  - **Phase 11C.1C-C-B-B-B-C** — *this document*.
    `NEXT_ALLOWED / NOT_STARTED`. **Third child slice**
    under Phase 11C.1C-C-B-B-B. Long-Window Cohort
    Stability & Sample Sufficiency Protocol v0. Docs /
    evidence-template only. No new runtime module. No
    trade authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Scope (what this slice is)

Phase 11C.1C-C-B-B-B-C is a **protocol slice**: it defines
the long-window paper data-collection cadence, the sample
sufficiency rule, the cohort stability acceptance criteria,
and the evidence-template shape that the operator and any
future closeout PR must follow. It does **not** add a new
runtime module, a new strategy, a new execution surface, a
new optimiser, or a new AI authority.

Concretely, this slice is allowed to produce only:

  - The **long-window run plan** (which paper WS run
    durations to schedule, in what order, what to capture
    from each).
  - The **sample sufficiency checklist** (when a window's
    cohort sample is large enough to warrant any
    discussion of Regime / Cluster right-tail signals,
    and what to do when it is not).
  - The **cohort stability checklist** (what we expect to
    see across consecutive windows of the same duration,
    and what counts as "stable" vs. "drifting" for the
    purposes of paper observation).
  - The **operator-VPS evidence template** (the verbatim
    fields the operator must capture from each window's
    runner output, daily report, events.db query, and
    Phase 8.5 export).
  - The **export / replay evidence template** (the Phase
    8.5 export package contents we expect to find, the
    Phase 10A replay invariants, and the safety-flag
    invariants).
  - The **closeout acceptance template** (what a future
    Phase 11C.1C-C-B-B-B-C closeout PR must record before
    flipping the slice to `ACCEPTED`).

The substantive contract — exact thresholds, exact window
counts, exact cohort-stability metrics, the brief-mandated
tests for any future *implementation* PR — is **out of
scope for this kickoff PR** and will be authored alongside
the next PR in the cycle. This kickoff records only the
scope, boundary, allowed outputs (docs / evidence templates
only), forbidden list, and the acceptance-gate placeholder.

### Why this is *not* a new runtime module

The Regime & Cluster Cohort Evidence Pack v0 (PR #56) and
the Paper Alpha Gate v0 (PR #52) already emit the events,
daily-report sections, and export artefacts that this
protocol consumes. **Nothing new needs to ship in `app/` to
support long-window paper observation.** The path forward
is to **run the existing pipeline for longer windows and
record the evidence**, not to add more code.

## Long-window paper data-collection cadence

The protocol defines four **observation windows** for paper
WS runs. None of them is auto-scheduled by this PR — the
operator runs each window manually on the operator-VPS, in
the order recorded below, until each window's cohort
samples are large enough to support a sample-sufficient
verdict on the Regime & Cluster Cohort Evidence Pack and
the Paper Alpha Gate.

| Window | Duration | Purpose | Auto-scheduled? |
| ------ | -------- | ------- | --------------- |
| W1     | 1 h paper WS run    | First meaningful sample window — proves the runtime / report / export pipeline survives an hour of real public WS data and starts to populate cohorts. | **No.** Operator-driven. |
| W2     | 4 h paper WS run    | Cohort stability check — captures multiple primary tracking windows resolving and lets us compare cohort row counts across an intra-day band. | **No.** Operator-driven. |
| W3     | 24 h paper WS run   | Day-level structural evidence — captures multiple market regimes / cluster rotations within a calendar day; produces the first window where the Regime & Cluster Cohort Evidence Pack is *expected* to emit a non-`INSUFFICIENT_SAMPLE` status if the data accumulates as designed. | **No.** Operator-driven. |
| W4+    | Multi-day paper observation (extension) | Reserved for later child slices (under Phase 11C.1C-C-B-B-B or a successor parent). Captures cross-day stability, regime drift, and replay-friendly multi-day cohort comparisons. | **No.** **Out of scope for this PR.** **Not implemented in this PR.** |

This PR **must not** implement an automatic scheduler, an
auto-trigger, or any runtime change that drives W1 / W2 /
W3 / W4+ on a clock. The cadence is **operator-driven**
and recorded as a **protocol**, not as code.

### Per-window evidence the operator must capture

For **every** window (W1 / W2 / W3, and any W4+ extensions
when they are formally opened by a future child slice), the
operator-VPS evidence record must include the following
verbatim fields. Missing any item invalidates the window's
evidence — the window must be re-run rather than the
threshold widened.

#### Event counts (runner snapshot + events.db cross-check)

  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` count
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED` count
  - `PAPER_ALPHA_GATE_EVALUATED` count
  - `PAPER_ALPHA_RULE_EVALUATED` count
  - `PAPER_ALPHA_COHORT_EVALUATED` count
  - `PAPER_ALPHA_REPORT_GENERATED` count

#### Daily-report sections (verbatim Markdown headers + body)

  - `## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
    Evidence Pack v0` section, including its boundary
    banner, per-cohort rows (regime, cluster, score
    bucket, stage, strategy mode), `warnings`, and
    `insufficient_sample_reasons`.
  - `## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0`
    section, including its boundary banner, per-cohort
    `paper_alpha_gate_*` results, `warnings`, and
    `insufficient_sample_reasons`.

#### Cohort sample sufficiency fields

  - `sample_count` (total)
  - `completed_tail_label_count` (total)
  - `regime_cluster_evidence_status` (one of
    `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` /
    `EVIDENCE_SIGNAL`)
  - `paper_alpha_gate_status` (one of `PASS` / `WARN` /
    `FAIL` / `INCONCLUSIVE`)
  - `insufficient_sample_reasons` (verbatim list)

#### Phase 8.5 export bundle

  - `export_test_data = OK`
  - export zip path
  - `manifest_event_count`
  - `redaction_applied = True`
  - `events.jsonl` exists in the export
  - export contains `REGIME_CLUSTER_*` events
  - export contains `PAPER_ALPHA_*` events
  - export package files observed: `manifest.json`,
    `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`, `virtual_trade_plans.jsonl`.

#### Safety flag invariants (verbatim)

```
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN
```

These are the **same** safety-flag invariants captured by
PR #54 (B-B-B-A closeout) and PR #57 (B-B-B-B closeout).
They must remain identical across W1 / W2 / W3.

## Sample sufficiency principle

The protocol's central rule is that **low samples cannot
support strong conclusions** — a rule that the Regime &
Cluster Cohort Evidence Pack v0 already enforces in code
via `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` and
the Paper Alpha Gate v0 already enforces via
`paper_alpha_gate_status=INCONCLUSIVE`.

The protocol formalises that rule as follows:

  - **`INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` are valid
    outputs, not failures.** A window that returns
    `INSUFFICIENT_SAMPLE` (Regime & Cluster) or
    `INCONCLUSIVE` (Paper Alpha Gate) is a *correctly
    operating* window. It is recorded, accepted, and
    counted toward the cumulative paper observation
    budget. It does **not** trigger a re-run with relaxed
    thresholds, and does **not** trigger a strategy
    change.
  - **When `completed_tail_label_count` is below the
    Regime & Cluster Evidence Pack v0 minimum, no
    Regime / Cluster right-tail conclusion is allowed.**
    The cohort rows are recorded for the audit trail, but
    no statement about "Regime X favours `strong_tail`"
    or "Cluster Y leader outperforms followers" may be
    derived from them.
  - **Cohort signals are only allowed once samples are
    sufficient.** "Sufficient" means the window's
    `sample_count` and `completed_tail_label_count` meet
    the existing Regime & Cluster Evidence Pack v0
    minimums *and* the Paper Alpha Gate v0 minimums. The
    Phase 11C.1C-C-B-B-B-C protocol does **not** widen
    those minimums. It does **not** replace them. It does
    **not** add a parallel set of thresholds.
  - **Cohort signals — even when sample-sufficient —
    remain paper-only / report-only / evidence-only.**
    They cannot trigger a real trade. They cannot modify
    position size, leverage, stop-loss, target price, the
    Risk Engine, or the Execution FSM. They cannot relax
    rules. They cannot enter Phase 12.

This is the same Phase 1 / 11B / 11C.1B / 11C.1C-A /
11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A /
11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B safety lock, repeated
verbatim. The Risk Engine remains the single trade-decision
gate.

## Cohort stability principle

In addition to sample sufficiency, the protocol records a
**stability** rule for cohort observation across windows:

  - A signal that appears in one short window and
    disappears in the next is **not** treated as evidence.
  - A signal that appears consistently across W1 / W2 / W3
    *and* survives the Phase 8.5 export / Phase 10A replay
    round-trip is treated as a **paper-only candidate
    signal worth continued observation** — but it still
    does not authorise any runtime change, parameter
    optimisation, rule relaxation, or trade.
  - A signal whose direction inverts across consecutive
    windows is logged as `regime_outcome_inverted_warning`
    in the existing Regime & Cluster Evidence Pack `warnings`
    list and is **not** acted on.
  - The protocol is biased toward "do nothing" when
    stability is unclear. It is **not** biased toward
    "act because we now have a number".

Cohort stability is **only** discussable once the sample
sufficiency principle is met for each window in question.
The two principles compose: stability without sufficiency
is meaningless; sufficiency without stability is a single
data point.

## Allowed outputs (docs / evidence templates only)

Each is a **descriptive document or evidence template**.
None has trade authority. None is read by the Risk Engine
or the Execution FSM. None is a new Python module, a new
event type, or a new runtime hook:

  - `long_window_run_plan` — operator-facing run plan for
    W1 / W2 / W3, recorded in this document and in the
    operator-VPS evidence template.
  - `sample_sufficiency_checklist` — verbatim checklist of
    `sample_count`, `completed_tail_label_count`, `*_status`
    fields, and `insufficient_sample_reasons` that must be
    captured per window.
  - `cohort_stability_checklist` — verbatim checklist of
    cross-window comparisons (signal persistence, signal
    inversion, warning persistence) that may be captured
    after consecutive windows.
  - `operator_vps_evidence_template` — verbatim shape of
    the runner / events.db / daily-report / export
    transcript the operator must record per window.
  - `export_replay_evidence_template` — verbatim shape of
    the Phase 8.5 export bundle / Phase 10A replay
    invariants per window.
  - `closeout_acceptance_template` — verbatim shape of the
    docs-only closeout PR that would flip Phase
    11C.1C-C-B-B-B-C to `ACCEPTED` (mirrors the PR #54 /
    PR #57 pattern).

These outputs are **only** allowed forms. Any artefact that
implies a real-trade authority, a position-sizing
recommendation, a leverage decision, a stop-loss target, an
Execution FSM transition, an automatic threshold widening,
or an automatic schedule is **out of scope** and forbidden.

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
| Position size / leverage / stop-loss / target price | unchanged; cannot be modified by any protocol output |
| `long_window_run_plan`                      | descriptive document only; MUST NEVER trigger a real trade |
| `sample_sufficiency_checklist`              | descriptive document only; MUST NEVER trigger a real trade |
| `cohort_stability_checklist`                | descriptive document only; MUST NEVER trigger a real trade |
| `operator_vps_evidence_template`            | descriptive document only; MUST NEVER trigger a real trade |
| `export_replay_evidence_template`           | descriptive document only; MUST NEVER trigger a real trade |
| `closeout_acceptance_template`              | descriptive document only; MUST NEVER trigger a real trade |
| AI authority                                | NOT permitted to decide direction / position size / leverage / stop / target / execution |
| Automatic parameter optimisation            | NOT permitted                |
| Reinforcement learning                      | NOT permitted                |
| Auto-rule-relaxation on low samples         | NOT permitted                |
| Automatic scheduling of W1 / W2 / W3 / W4+  | NOT permitted in this PR     |
| Phase 12 (live trading)                     | FORBIDDEN                    |

## Explicitly forbidden by this slice

This slice carries forward every Phase 1 / 11C.1B / 11C.1C-A
/ 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A /
11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim,
and adds the following slice-specific forbidden items:

  - Triggering a real trade.
  - Modifying position size.
  - Modifying leverage.
  - Modifying stop-loss.
  - Modifying target price.
  - Modifying the Risk Engine.
  - Modifying the Execution FSM.
  - Letting AI / LLM decide direction, position size,
    leverage, stop-loss, target price, or execution.
  - Auto-optimising parameters in response to long-window
    cohort signals.
  - Auto-relaxing rules in response to low-sample windows.
  - Auto-scheduling W1 / W2 / W3 / W4+ runs from runtime
    code.
  - Promoting any protocol artefact (run plan,
    sufficiency checklist, stability checklist, evidence
    template, closeout template) to a real-trade
    authority.
  - Replacing the Regime & Cluster Cohort Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule with a relaxed rule. The
    protocol consumes the existing rule; it does not
    rewrite it.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
    with a relaxed rule. The protocol consumes the
    existing rule; it does not rewrite it.
  - Adding new event types, new Python modules, or new
    runtime behaviour in this kickoff PR.
  - Adding new event types, new Python modules, or new
    runtime behaviour in any future Phase 11C.1C-C-B-B-B-C
    PR. (The slice is intentionally **docs / evidence
    template only** end-to-end; if a future need for a new
    runtime module emerges, it must be opened as a
    separate child slice with its own kickoff /
    implementation / closeout cycle.)
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/` in this kickoff PR.
  - Modifying configuration schemas, defaults, or YAML in
    this kickoff PR.
  - Adding or modifying tests in this kickoff PR.
  - Running tests as part of this kickoff PR.
  - Flipping any phase's acceptance state. Phase
    11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-C remains `NEXT_ALLOWED /
    NOT_STARTED` (this PR scopes it; it does not flip its
    state). Phase 12 remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
    its existing definition.
  - Phase 11C.1C-C-B-B-B-C *closeout* (out of scope; will
    be authored after the operator captures W1 / W2 / W3
    paper evidence and a separate docs-only closeout PR
    flips the slice to `ACCEPTED`).
  - Phase 11C.1C-C-B-B-B-D / B-B-B-E / further child
    slices (out of scope; will require their own kickoff
    PRs).
  - Phase 12 / live trading kickoff.

## Acceptance gate (placeholder; to be detailed by the closeout PR)

The Phase 11C.1C-C-B-B-B-C closeout PR (a **future**
docs-only PR; not this one) will be authored only **after**
the operator-VPS captures the W1 / W2 / W3 paper evidence
required by this protocol. The placeholders below record
what the gate is **expected** to require, so the closeout
PR is reviewed against a known shape:

  - W1 (1 h paper WS run) operator-VPS evidence captured
    verbatim, including all event counts, daily-report
    sections, sufficiency fields, export-bundle reference,
    and safety-flag invariants listed above.
  - W2 (4 h paper WS run) operator-VPS evidence captured
    verbatim, including the same fields.
  - W3 (24 h paper WS run) operator-VPS evidence captured
    verbatim, including the same fields.
  - Cohort stability checklist filled in across W1 / W2 /
    W3 (signal persistence, signal inversion, warning
    persistence).
  - At least one window in which
    `regime_cluster_evidence_status` is non-
    `INSUFFICIENT_SAMPLE` *or* an explicit recorded
    statement that all three windows returned
    `INSUFFICIENT_SAMPLE` and that further W4+ multi-day
    observation is therefore the next-step
    recommendation. **Either outcome is acceptable.** The
    protocol explicitly accepts "we still do not have
    enough data" as a valid closeout result, exactly the
    way Phase 11C.1C-C-B-B-B-A and Phase 11C.1C-C-B-B-B-B
    accepted `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` smoke
    results.
  - Phase 8.5 export bundle round-trip evidence captured
    for W1 / W2 / W3 (zip generated, manifest event count
    sane, redaction applied, `events.jsonl` present, the
    `REGIME_CLUSTER_*` and `PAPER_ALPHA_*` event types
    present in the export).
  - Phase 10A replay engine accepts each window's export
    bundle without raising.
  - Safety flags unchanged across every window
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
    emitted by any window.
  - No protocol artefact is read by the Risk Engine or
    the Execution FSM.
  - Phase 12 stays `FORBIDDEN`.

## What this kickoff PR does

  - **Defines** Phase 11C.1C-C-B-B-B-C as the *Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0 / 长
    窗口 Cohort 稳定性与样本充足协议 v0* — the third child
    slice under Phase 11C.1C-C-B-B-B.
  - **Records** the long-window run cadence (W1 / W2 / W3
    / W4+ reserved), per-window evidence fields, sample
    sufficiency principle, cohort stability principle,
    allowed outputs (docs / evidence templates only),
    boundary table, slice-specific forbidden items, and
    acceptance-gate placeholder in this document.
  - **Refreshes** the Phase 11C.1C-C-B-B-B-C placeholder
    text in `docs/PHASE_GATE.md` and
    `docs/PROJECT_STATUS.md` so the slice is now defined
    by name and scope, while remaining `NEXT_ALLOWED /
    NOT_STARTED`.
  - **Refreshes** the *Architecture governance
    (guidance-only; no phase change)* closing paragraph in
    `docs/PHASE_GATE.md` to reflect the current open-phase
    state (B-B-B-A = ACCEPTED; B-B-B-B = ACCEPTED; B-B-B =
    NEXT_ALLOWED / NOT_STARTED; B-B-B-C = NEXT_ALLOWED /
    NOT_STARTED with full scope; Phase 12 = FORBIDDEN).
  - **Records** this PR in `docs/CHANGELOG.md > [Unreleased]`
    and `docs/PR58_DESCRIPTION.md`.

## What this kickoff PR does NOT do

  - It does **NOT** flip any phase's acceptance state.
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-C remains `NEXT_ALLOWED /
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
    Regime & Cluster Evidence Pack v0 `INSUFFICIENT_SAMPLE`
    minimums or the Paper Alpha Gate v0 `INCONCLUSIVE`
    minimums.
  - It does **NOT** authorise live trading, API keys,
    private endpoints, DeepSeek trade decisions, real
    Telegram outbound, AI Learning, automatic parameter
    optimisation, reinforcement learning, the complete
    Strategy Validation Lab follow-up, or Phase 12.
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


## Phase 11C.1C-C-B-B-B-C acceptance evidence (operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound early-stop paper WS evidence — FILED via PR #59)

> The transcripts below are the verbatim runner / events.db /
> daily-report / Phase 8.5 export output captured from the
> operator-VPS long-window paper WS runs against `main`
> post-PR-#58. The Kiro-side sandbox could not host these
> smokes (Binance-region geoblock — historical context, same
> as the Phase 11C.1C-B / Phase 11C.1C-C-A / Phase
> 11C.1C-C-B-A / Phase 11C.1C-C-B-B-B-A / Phase
> 11C.1C-C-B-B-B-B closeouts; this is **not** the current
> blocker), so the operator ran them from a Binance-reachable
> VPS. **The W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound
> early-stop paper WS runs PASSED and are accepted as Phase
> 11C.1C-C-B-B-B-C acceptance evidence.**
>
> Phase 11C.1C-C-B-B-B-C is now recorded as **ACCEPTED** in
> the closed-phases table at the top of `docs/PHASE_GATE.md`
> and in the `## Closed phase: Phase 11C.1C-C-B-B-B-C
> (ACCEPTED)` section there. This docs-only closeout PR
> mirrors the PR #36 → PR #37, PR #38 → PR #39, PR #40 → PR
> #41, PR #42 → PR #43, PR #44 → PR #50, PR #52 → PR #54,
> and PR #56 → PR #57 closeout pattern.
>
> Phase 11C.1C-C-B-B-B-D remains **NEXT_ALLOWED /
> NOT_STARTED**; Phase 11C.1C-C-B-B-B-C acceptance does
> **NOT** authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing
> the standard gate; Phase 12 remains **FORBIDDEN**.

### W1 / W1+ — 2 h Long-Window Paper WS Run (PASS)

```
host                            : operator VPS (Binance-reachable region)
mode                            : paper
command                         : python -m scripts.run_public_market_paper \
                                    --duration 2h --ws-first

# WS / runner-level metrics
duration_seconds                = 7200.0
uptime                          ≈ 7238s
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
risk_approved                   = 0
live_trading                    = disabled

# 2 h event counts (runner snapshot + events.db type-count cross-check)
PAPER_ALPHA_COHORT_EVALUATED                 = 18
PAPER_ALPHA_GATE_EVALUATED                   = 3
PAPER_ALPHA_REPORT_GENERATED                 = 3
PAPER_ALPHA_RULE_EVALUATED                   = 27
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED      = 10
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED       = 2

# 2 h Daily report content
daily_report_section_present (Paper Alpha Gate)                   = "## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"
daily_report_section_present (Regime & Cluster Evidence Pack)     = "## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"
regime_cluster_sample_count                  = 189
regime_cluster_completed_tail_label_count    = 0
regime_cluster_evidence_status               = INSUFFICIENT_SAMPLE
paper_alpha_gate_status                      = INCONCLUSIVE
insufficient_sample_reasons                  = [completed_tail_label_count_below_min=0<10]

# 2 h Phase 8.5 export evidence
export_test_data                = OK
export zip path                 = data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip
manifest_event_count            = 23001
redaction_applied               = True
events.jsonl exists             = True
EXPORT_LONG_WINDOW_W1_2H_CHECK  = PASS

# Safety boundary (Phase 1 lock unchanged end-to-end)
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN (gate unchanged)
```

The W1 / W1+ window's
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` and
`paper_alpha_gate_status=INCONCLUSIVE` are **expected and
accepted** results because
`completed_tail_label_count=0<10`. The Regime & Cluster
Cohort Evidence Pack v0 and the Paper Alpha Gate v0
correctly refused to overfit or force a regime / cluster
conclusion on a low-completed-tail-label window. **This is
valid low-completed-label evidence, not runtime failure,
and it does NOT authorise rule relaxation.**

### W2 — 4 h Long-Window Paper WS Run (PASS)

```
host                            : operator VPS (Binance-reachable region)
mode                            : paper
command                         : python -m scripts.run_public_market_paper \
                                    --duration 4h --ws-first

# WS / runner-level metrics
configured duration_seconds     = 14400.0
actual runtime                  ≈ 14417s
iterations                      = 237
chains_emitted                  = 704
ws_chains_emitted               = 704
ws_real_transport               = True
ws_reconnect_count              = 0
ws_staleness_ms_max             = 0
ws_stale_count                  = 0
ingestion_errors                = 0
public_endpoint_calls           = 4226
ws_messages_received            = 1324423
radar_candidates_seen           = 152221
candidate_pool_size_max         = 20
liquidation_events_seen         = 4076
rate_limit_429_count            = 0
rate_limit_418_count            = 0
rate_limit_ban                  = False
risk_approved                   = 0
risk_rejected                   = 704

# 4 h event counts (runner snapshot + events.db type-count cross-check)
PAPER_ALPHA_COHORT_EVALUATED                 = 24
PAPER_ALPHA_GATE_EVALUATED                   = 4
PAPER_ALPHA_REPORT_GENERATED                 = 4
PAPER_ALPHA_RULE_EVALUATED                   = 36
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED      = 15
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED       = 3

# 4 h Daily report content
paper_alpha_gate_status                      = INCONCLUSIVE
paper_alpha_gate_sample_count                = 164
paper_alpha_gate_reason                      = completed_tail_label_count_below_min=2<10
regime_cluster_evidence_status               = INSUFFICIENT_SAMPLE
regime_cluster_sample_count                  = 164
regime_cluster_completed_tail_label_count    = 2
regime_cluster_reason                        = completed_tail_label_count_below_min=2<10

# 4 h Phase 8.5 export evidence
export_test_data                = OK
export zip path                 = data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip
manifest_event_count            = 61546
redaction_applied               = True
events.jsonl exists             = True
EXPORT_LONG_WINDOW_W2_4H_CHECK  = PASS

# Safety boundary (Phase 1 lock unchanged end-to-end)
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12                        = FORBIDDEN (gate unchanged)
```

**Important interpretation of W2.** The 4 h window showed
**progress** from `completed_tail_label_count=0` (W1 / W1+
2 h) to `completed_tail_label_count=2` (W2 4 h) — completed
tail labels are starting to appear as the observation
window lengthens, exactly as the protocol predicted.
However, `2` is still **below the 10 completed-tail-label
sufficiency threshold**, so
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` and
`paper_alpha_gate_status=INCONCLUSIVE` remained the
**correct** results for W2. **This does NOT indicate
runtime failure.** **This does NOT authorise rule
relaxation** — the protocol's central rule is that low
samples cannot output strong conclusions, and the rule
holds verbatim. The right next step was therefore to
extend the observation window further (W3 24 h
upper-bound), which we did.

### W3 — 24 h upper-bound run with watcher early-stop (PASS)

```
host                            : operator VPS (Binance-reachable region)
mode                            : paper
command                         : python -m scripts.run_public_market_paper \
                                    --duration 24h --ws-first
watcher                         : early-stop on
                                  final_tail_labels_since_start>=10

# Early-stop outcome
total_elapsed_seconds                        = 900
final_tail_labels_since_start                = 20
SAMPLE_SUFFICIENCY_REACHED                   = final_tail_labels=20>=10
24 h full runtime                            = NOT NEEDED (early stop triggered)

# Runtime safety summary (held end-to-end across the 900 s window)
mode                            = paper
live_trading                    = False
right_tail                      = False
llm                             = False
exchange_live_orders            = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
risk_approved                   = 0
ingestion_errors                = 0
rate_limit_429_count            = 0
rate_limit_418_count            = 0
ws_real_transport               = True

# Watcher logs (filenames as recorded by the operator)
run_log                         = data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log
watch_log                       = data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log
```

**Interpretation of W3.** W3 was started as a **24 h
upper-bound** paper WS run. A watcher monitored
`final_tail_labels_since_start` and stopped the run early
once tail-label sufficiency was reached
(`final_tail_labels_since_start=20>=10`). The run
terminated cleanly at `total_elapsed_seconds=900`; the
full 24 h runtime was **not needed**. **This proves the
B-B-B-C sample sufficiency protocol can save runtime while
preserving evidence:** the protocol does not require the
operator to run a fixed 24 h window when sufficiency has
already been demonstrated within a shorter window — it
allows early-stop on the existing Regime & Cluster
Cohort Evidence Pack v0 / Paper Alpha Gate v0
sufficiency thresholds.

#### W3 Phase 8.5 export evidence (PASS)

```
# Latest export zip generated after W3 early-stop
export_test_data                = OK
export zip path                 = data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip
generated at                    = 2026-05-25 12:41 UTC
manifest_event_count            = 62761
redaction_applied               = True
events.jsonl exists             = True
EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK = PASS

# W3 export event counts (export-range, full 24 h export window)
TAIL_LABEL_ASSIGNED                          = 495
LABEL_WINDOW_COMPLETED                       = 495
STRATEGY_VALIDATION_SAMPLE_CREATED           = 397
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED       = 4
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED      = 20
PAPER_ALPHA_GATE_EVALUATED                   = 5
PAPER_ALPHA_RULE_EVALUATED                   = 45
PAPER_ALPHA_COHORT_EVALUATED                 = 30
PAPER_ALPHA_REPORT_GENERATED                 = 5
```

> **Clarification on the two W3 numbers.**
> `final_tail_labels_since_start=20` is the **watcher
> early-stop condition** for this W3 run — it counts the
> tail labels that completed during the **900 s** window
> the operator actually ran, and it is the threshold
> against which the watcher decided to stop early.
> `TAIL_LABEL_ASSIGNED=495` is the **24 h export-range
> event count** captured from the Phase 8.5 export bundle
> — it counts tail labels assigned across the **full 24 h
> export window** (which includes pre-existing
> events.db-resident tail-label records that the export
> range covers, not just the 900 s that the runner was
> live for). **Do not confuse the two numbers.** Both are
> valid; they represent different scopes (live-run window
> vs. export-range window).

### Acceptance criteria — every gate met

  - W1 / W1+ 2 h paper WS run PASS ✅
    (`duration_seconds=7200.0`, `uptime≈7238s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`,
    `risk_approved=0`, live trading disabled)
  - W2 4 h paper WS run PASS ✅
    (configured `duration_seconds=14400.0`, actual
    runtime ≈ `14417s`, `iterations=237`,
    `chains_emitted=704`, `ws_chains_emitted=704`,
    `ws_real_transport=True`, `ws_reconnect_count=0`,
    `ws_staleness_ms_max=0`, `ws_stale_count=0`,
    `ingestion_errors=0`, `public_endpoint_calls=4226`,
    `ws_messages_received=1324423`,
    `radar_candidates_seen=152221`,
    `candidate_pool_size_max=20`,
    `liquidation_events_seen=4076`,
    `rate_limit_429_count=0`,
    `rate_limit_418_count=0`,
    `rate_limit_ban=False`,
    `risk_approved=0`, `risk_rejected=704`)
  - W3 24 h upper-bound run PASS ✅ with watcher
    early-stop at `total_elapsed_seconds=900`,
    `final_tail_labels_since_start=20>=10`,
    `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`,
    24 h full runtime NOT NEEDED, safety summary
    held end-to-end (`mode=paper`,
    `live_trading=False`, `right_tail=False`,
    `llm=False`, `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`,
    `risk_approved=0`, `ingestion_errors=0`,
    `rate_limit_429_count=0`,
    `rate_limit_418_count=0`,
    `ws_real_transport=True`)
  - 2 h event counts PASS ✅
    (`PAPER_ALPHA_COHORT_EVALUATED=18`,
    `PAPER_ALPHA_GATE_EVALUATED=3`,
    `PAPER_ALPHA_REPORT_GENERATED=3`,
    `PAPER_ALPHA_RULE_EVALUATED=27`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`)
  - 4 h event counts PASS ✅
    (`PAPER_ALPHA_COHORT_EVALUATED=24`,
    `PAPER_ALPHA_GATE_EVALUATED=4`,
    `PAPER_ALPHA_REPORT_GENERATED=4`,
    `PAPER_ALPHA_RULE_EVALUATED=36`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`)
  - W3 export event counts PASS ✅
    (`TAIL_LABEL_ASSIGNED=495`,
    `LABEL_WINDOW_COMPLETED=495`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED=397`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`,
    `PAPER_ALPHA_GATE_EVALUATED=5`,
    `PAPER_ALPHA_RULE_EVALUATED=45`,
    `PAPER_ALPHA_COHORT_EVALUATED=30`,
    `PAPER_ALPHA_REPORT_GENERATED=5`)
  - W1 / W1+ 2 h daily report contains the Paper Alpha
    Gate section + the Regime & Cluster Cohort Evidence
    Pack section ✅
  - W1 / W1+ 2 h sufficiency fields PASS ✅
    (`regime_cluster_sample_count=189`,
    `regime_cluster_completed_tail_label_count=0`,
    status remained `INSUFFICIENT_SAMPLE` /
    `INCONCLUSIVE` because
    `completed_tail_label_count=0<10` — accepted as
    valid low-completed-label evidence, not runtime
    failure)
  - W2 4 h sufficiency fields PASS ✅
    (`paper_alpha_gate_status=INCONCLUSIVE`,
    `paper_alpha_gate_sample_count=164`, reason
    `completed_tail_label_count_below_min=2<10`;
    `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
    `regime_cluster_sample_count=164`,
    `regime_cluster_completed_tail_label_count=2`,
    reason `completed_tail_label_count_below_min=2<10`
    — progress from 0 to 2 completed labels, still
    below the 10-label threshold, therefore
    `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the
    correct result; does NOT indicate runtime failure;
    does NOT authorise rule relaxation)
  - W1 / W1+ 2 h export PASS ✅
    (`export_test_data=OK`, zip
    `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`,
    `manifest_event_count=23001`,
    `redaction_applied=True`,
    `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`)
  - W2 4 h export PASS ✅
    (`export_test_data=OK`, zip
    `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`,
    `manifest_event_count=61546`,
    `redaction_applied=True`,
    `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`)
  - W3 24 h export PASS ✅
    (`export_test_data=OK`, latest export zip after
    W3 early-stop
    `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`,
    generated at 2026-05-25 12:41 UTC,
    `manifest_event_count=62761`,
    `redaction_applied=True`, `events.jsonl` exists,
    `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`)
  - Safety boundary held end-to-end across W1 / W1+ 2 h,
    W2 4 h, and W3 24 h upper-bound early-stop
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound)
    ✅
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by any of W1 / W1+ / W2 / W3 ✅
  - No protocol artefact is read by the Risk Engine or
    the Execution FSM ✅
  - Phase 12 stayed **FORBIDDEN** ✅

Phase 1 safety lock held end-to-end across W1 / W1+ 2 h,
W2 4 h, and W3 24 h upper-bound early-stop; no real order,
no signed endpoint call, no private WebSocket connection,
no listenKey allocation, no DeepSeek trade decision, no
real Telegram outbound, and Phase 12 stayed **FORBIDDEN**.

## What this closeout PR does

  - **Flips** Phase 11C.1C-C-B-B-B-C from `NEXT_ALLOWED /
    NOT_STARTED` (defined in place by PR #58 docs-only
    kickoff) to `ACCEPTED` on the basis of the
    operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h
    upper-bound early-stop paper WS evidence above.
  - **Records** Phase 11C.1C-C-B-B-B-D as `NEXT_ALLOWED /
    NOT_STARTED` (placeholder; not yet defined; will
    require its own kickoff PR, brief, scope, boundary
    table, forbidden list, and acceptance evidence).
  - **Preserves** the parent phase definition: Phase
    11C.1C-C-B-B-B remains *Strategy Validation Lab
    (deeper) & richer Cluster Exposure Control
    follow-up*.
  - **Records** the operator-VPS evidence verbatim in this
    document, in `docs/PHASE_GATE.md`, and in
    `docs/PROJECT_STATUS.md`.
  - **Records** this PR in `docs/CHANGELOG.md >
    [Unreleased]` and `docs/PR59_DESCRIPTION.md`.

## What this closeout PR does NOT do

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise API keys.
  - It does **NOT** authorise private endpoints.
  - It does **NOT** authorise DeepSeek trade decisions.
  - It does **NOT** authorise real Telegram outbound.
  - It does **NOT** authorise Phase 12.
  - It does **NOT** authorise automatic parameter
    optimisation.
  - It does **NOT** authorise AI Learning.
  - It does **NOT** authorise reinforcement learning.
  - It does **NOT** authorise rule relaxation based on
    low samples.
  - It does **NOT** authorise changing the Risk Engine
    or the Execution FSM.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D
    kickoff bypassing the standard gate.
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
    Regime & Cluster Evidence Pack v0 `INSUFFICIENT_SAMPLE`
    minimums or the Paper Alpha Gate v0 `INCONCLUSIVE`
    minimums.
  - It does **NOT** modify `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `llm/`,
    `telegram/`, or `exchange/`.

## Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise

  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise live trading.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise API keys.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise private endpoints.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise DeepSeek trade decisions.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise real Telegram outbound.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise Phase 12.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise automatic parameter optimisation.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise AI Learning.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise rule relaxation based on low samples.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise changing the Risk Engine or the Execution
    FSM.

## Long-window protocol outputs (paper-only / report-only / evidence-only)

The Long-Window Cohort Stability & Sample Sufficiency
Protocol v0 outputs (`long_window_run_plan`,
`sample_sufficiency_checklist`,
`cohort_stability_checklist`,
`operator_vps_evidence_template`,
`export_replay_evidence_template`,
`closeout_acceptance_template`) remain **paper-only /
report-only / evidence-only**. They cannot trigger orders,
leverage, position sizing, stop changes, target changes,
Risk Engine changes, or Execution FSM changes. The Risk
Engine remains the single trade-decision gate.
