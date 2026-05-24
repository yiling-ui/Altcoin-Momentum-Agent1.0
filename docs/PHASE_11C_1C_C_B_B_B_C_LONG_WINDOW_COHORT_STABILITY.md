# Phase 11C.1C-C-B-B-B-C — Long-Window Cohort Stability & Sample Sufficiency Protocol v0

> **Chinese name / 中文名:** *长窗口 Cohort 稳定性与样本充足协议 v0*.
>
> **Status: NEXT_ALLOWED / NOT_STARTED (docs-only kickoff /
> scope alignment).** This document opens Phase
> 11C.1C-C-B-B-B-C as the **third child slice** under the
> Phase 11C.1C-C-B-B-B parent (*Strategy Validation Lab
> (deeper) & richer Cluster Exposure Control follow-up*).
> The parent phase is **not** renamed; it keeps its
> existing definition. Phase 11C.1C-C-B-B-B-A (*Paper Alpha
> Gate v0*) remains `ACCEPTED` (PR #52 + PR #54 closeout).
> Phase 11C.1C-C-B-B-B-B (*Regime & Cluster Cohort Evidence
> Pack v0*) remains `ACCEPTED` (PR #56 + PR #57 closeout).
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
