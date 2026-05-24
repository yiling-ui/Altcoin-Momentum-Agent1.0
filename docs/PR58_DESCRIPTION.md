# PR #58 — Phase 11C.1C-C-B-B-B-C: Long-Window Cohort Stability & Sample Sufficiency Protocol v0 (docs-only kickoff)

> **Status: DOCS-ONLY KICKOFF / SCOPE ALIGNMENT.** This PR
> defines Phase 11C.1C-C-B-B-B-C (*Long-Window Cohort
> Stability & Sample Sufficiency Protocol v0 / 长窗口
> Cohort 稳定性与样本充足协议 v0*) as the **third child
> slice** under the Phase 11C.1C-C-B-B-B parent. The parent
> phase is **not** renamed: Phase 11C.1C-C-B-B-B remains
> *Strategy Validation Lab (deeper) & richer Cluster
> Exposure Control follow-up*. **No runtime code is shipped
> by this PR.** **No phase's acceptance state is flipped.**
> Phase 11C.1C-C-B-B-B-C remains `NEXT_ALLOWED /
> NOT_STARTED`; this PR scopes the slice in place.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> strategy implementation. **NOT** a trading module. **NOT**
> a new runtime module. **NOT** the complete Strategy
> Validation Lab follow-up. **NOT** Phase
> 11C.1C-C-B-B-B-C *closeout* (the closeout will be a
> separate docs-only PR after the operator captures W1 /
> W2 / W3 paper evidence). **NOT** Phase 12.
>
> The Long-Window Cohort Stability & Sample Sufficiency
> Protocol v0 is **docs / evidence-template only**
> end-to-end. It does not add a new runtime module, a new
> event type, a new strategy, a new execution surface, a
> new optimiser, or a new AI authority. It defines the
> long-window paper data-collection cadence (1 h → 4 h →
> 24 h, with multi-day reserved), the sample sufficiency
> rule, the cohort stability acceptance criteria, and the
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
  - **Phase 11C.1C-C-B-B-B-C** — *defined by this PR*.
    `NEXT_ALLOWED / NOT_STARTED`. **Third child slice**
    under Phase 11C.1C-C-B-B-B. Long-Window Cohort
    Stability & Sample Sufficiency Protocol v0 / 长窗口
    Cohort 稳定性与样本充足协议 v0. Docs / evidence-template
    only. No new runtime module. No trade authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Branch + base

  - Branch:
    `docs/phase-11c1c-c-b-b-b-c-long-window-cohort-stability-kickoff`
  - Base: `main` (post PR #57 closeout).

## What this PR does

  - **Defines** Phase 11C.1C-C-B-B-B-C as the *Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0* —
    the third child slice under Phase 11C.1C-C-B-B-B.
  - **Records** the **why** for this slice (PR #56
    implemented Regime & Cluster Cohort Evidence Pack v0;
    PR #57 closeout flipped B-B-B-B to `ACCEPTED`; the
    operator-VPS 10 min WS paper smoke evidence was
    accepted as well-formed but
    `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`
    with `sample_count=14<20` and
    `completed_tail_label_count=0<10`; runtime / report /
    export are correct, but the observation window is too
    short to support a Regime / Cluster right-tail
    conclusion; the right next step is to **accumulate
    structural data across longer paper observation
    windows**, not add a new strategy or AI module).
  - **Defines** the long-window run cadence:
      - **W1 — 1 h paper WS run** (first meaningful sample
        window).
      - **W2 — 4 h paper WS run** (cohort stability check).
      - **W3 — 24 h paper WS run** (day-level structural
        evidence).
      - **W4+ — multi-day paper observation** (reserved;
        out of scope for this PR; not implemented in this
        PR; not auto-scheduled in this PR).
  - **Records** the per-window evidence fields the
    operator must capture verbatim:
      - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`
      - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`
      - `PAPER_ALPHA_GATE_EVALUATED`
      - `PAPER_ALPHA_RULE_EVALUATED`
      - `PAPER_ALPHA_COHORT_EVALUATED`
      - `PAPER_ALPHA_REPORT_GENERATED`
      - daily report Regime & Cluster section
      - daily report Paper Alpha Gate section
      - `sample_count`
      - `completed_tail_label_count`
      - `regime_cluster_evidence_status`
      - `paper_alpha_gate_status`
      - `insufficient_sample_reasons`
      - export package (Phase 8.5)
      - export contains `REGIME_CLUSTER_*` events
      - export contains `PAPER_ALPHA_*` events
      - safety flags
  - **Defines** the sample sufficiency principle (low
    samples cannot support strong conclusions;
    `INSUFFICIENT_SAMPLE` and `INCONCLUSIVE` are valid
    outputs not failures; cohort signals are only
    discussable once samples are sufficient; sample
    sufficiency does not authorise a real trade or any
    runtime change).
  - **Defines** the cohort stability principle (signals
    must persist across consecutive windows to count as
    paper-only candidate signals; signal inversion is
    logged as a warning; the protocol is biased toward
    "do nothing" when stability is unclear).
  - **Lists** the allowed outputs (docs / evidence
    templates only):
      - `long_window_run_plan`
      - `sample_sufficiency_checklist`
      - `cohort_stability_checklist`
      - `operator_vps_evidence_template`
      - `export_replay_evidence_template`
      - `closeout_acceptance_template`
  - **Records** the boundary table and the slice-specific
    forbidden items (carries forward verbatim from
    B-B-B-A / B-B-B-B + adds slice-specific items for
    long-window observation).
  - **Refreshes** the Phase 11C.1C-C-B-B-B-C placeholder
    sections in `docs/PHASE_GATE.md` and
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

## What this PR does NOT do

  - It does **NOT** flip any phase's acceptance state.
  - It does **NOT** rename Phase 11C.1C-C-B-B-B.
  - It does **NOT** implement the Long-Window Cohort
    Stability & Sample Sufficiency Protocol v0 — the
    protocol is defined as docs / evidence templates only,
    and the slice will not introduce any new runtime
    module or new event type at any point in its lifecycle.
  - It does **NOT** auto-schedule W1 / W2 / W3 / W4+ runs.
    The cadence is operator-driven.
  - It does **NOT** widen, replace, or relax the existing
    Regime & Cluster Evidence Pack v0 `INSUFFICIENT_SAMPLE`
    minimums or the Paper Alpha Gate v0 `INCONCLUSIVE`
    minimums.
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
docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md   (NEW)
docs/PR58_DESCRIPTION.md                                       (NEW)
docs/PHASE_GATE.md                                             (modified — docs-only)
docs/PROJECT_STATUS.md                                         (modified — docs-only)
docs/CHANGELOG.md                                              (modified — docs-only)
```

No file under `app/`, `scripts/`, `tests/`, `configs/`,
`risk/`, `execution/`, `llm/`, `telegram/`, or `exchange/`
is touched.

## Allowed file edits

  - `docs/PROJECT_STATUS.md`
  - `docs/PHASE_GATE.md`
  - `docs/CHANGELOG.md`
  - `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`
    (NEW)
  - `docs/PR58_DESCRIPTION.md` (NEW; this document)

## Allowed outputs (docs / evidence templates only) — recorded for future PRs in the cycle

Each is a **descriptive document or evidence template**.
None has trade authority. None is read by the Risk Engine
or the Execution FSM. None is a new Python module, a new
event type, or a new runtime hook:

  - `long_window_run_plan`
  - `sample_sufficiency_checklist`
  - `cohort_stability_checklist`
  - `operator_vps_evidence_template`
  - `export_replay_evidence_template`
  - `closeout_acceptance_template`

## Long-window run cadence (operator-driven; not auto-scheduled)

  - **W1 — 1 h paper WS run**: first meaningful sample
    window.
  - **W2 — 4 h paper WS run**: cohort stability check.
  - **W3 — 24 h paper WS run**: day-level structural
    evidence.
  - **W4+ — multi-day paper observation**: reserved; out
    of scope for this PR; will require its own child slice
    when formally opened.

This PR **must not** implement an automatic scheduler, an
auto-trigger, or any runtime change that drives W1 / W2 /
W3 / W4+ on a clock. The cadence is **operator-driven** and
recorded as a **protocol**, not as code.

## Sample sufficiency principle (carries forward verbatim)

  - Low samples cannot output strong conclusions.
  - When `completed_tail_label_count` is below the Regime
    & Cluster Evidence Pack v0 minimum, no Regime / Cluster
    right-tail conclusion is permitted from the cohort
    rows.
  - `INSUFFICIENT_SAMPLE` (Regime & Cluster) and
    `INCONCLUSIVE` (Paper Alpha Gate) are **valid outputs,
    not failures**.
  - Cohort signals are only allowed once samples are
    sufficient.
  - Cohort signals — even when sample-sufficient — remain
    paper-only / report-only / evidence-only.
  - Cohort signals cannot trigger trades, modify
    parameters, relax rules, or enter Phase 12.

## Cohort stability principle (carries forward verbatim)

  - A signal that appears in one short window and
    disappears in the next is **not** treated as evidence.
  - A signal that persists across W1 / W2 / W3 *and*
    survives the Phase 8.5 export / Phase 10A replay
    round-trip is treated as a **paper-only candidate
    signal worth continued observation** — but it still
    does not authorise any runtime change, parameter
    optimisation, rule relaxation, or trade.
  - A signal whose direction inverts across consecutive
    windows is logged as `regime_outcome_inverted_warning`
    and is **not** acted on.
  - The protocol is biased toward "do nothing" when
    stability is unclear.

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
  - Auto-rule-relaxation on low samples.
  - Auto-scheduling W1 / W2 / W3 / W4+ runs from runtime
    code.
  - Risk Engine override / bypass.
  - Execution FSM override / bypass.
  - Phase Gate override / bypass.
  - Triggering a real trade from any protocol artefact.
  - Modifying position size / leverage / stop-loss / target
    price from any protocol artefact.
  - Modifying the Risk Engine or the Execution FSM from
    any protocol artefact.
  - Replacing the Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
    with a relaxed rule.
  - Implementing the Long-Window Cohort Stability & Sample
    Sufficiency Protocol v0 as a new runtime module — the
    slice is intentionally **docs / evidence template
    only** end-to-end; if a future need for a new runtime
    module emerges, it must be opened as a separate child
    slice with its own kickoff / implementation / closeout
    cycle.
  - Implementing the complete Strategy Validation Lab
    follow-up (reserved for later child slices under Phase
    11C.1C-C-B-B-B).
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
    11C.1C-C-B-B-B-C remains `NEXT_ALLOWED / NOT_STARTED`
    (this PR scopes the slice; it does not flip its
    state). Phase 12 remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
    its existing definition — *Strategy Validation Lab
    (deeper) & richer Cluster Exposure Control follow-up*.
  - Phase 11C.1C-C-B-B-B-C *closeout* (out of scope; will
    be authored after the operator captures W1 / W2 / W3
    paper evidence and a separate docs-only closeout PR
    flips the slice to `ACCEPTED`).
  - Phase 11C.1C-C-B-B-B-D / B-B-B-E / further child
    slices (out of scope; will require their own kickoff
    PRs).
  - Phase 12 / live trading kickoff.

## Acceptance gate (docs-only)

  - Docs-only PR. **No code modified** under `app/`,
    `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
    `llm/`, `telegram/`, or `exchange/`.
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
  - [x] No `execution/` / `risk/` / `llm/` / `telegram/` /
    `exchange/` changes.
  - [x] No strategy runtime code changes.
  - [x] No phase's acceptance state flipped — Phase
    11C.1C-C-B-B-B-B remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`;
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-C remains `NEXT_ALLOWED / NOT_STARTED`
    (scoped by this PR; not flipped).
  - [x] Phase 11C.1C-C-B-B-B parent is **not** renamed; it
    remains *Strategy Validation Lab (deeper) & richer
    Cluster Exposure Control follow-up*.
  - [x] Phase 11C.1C-C-B-B-B-C is recorded as the third
    child slice under Phase 11C.1C-C-B-B-B = Long-Window
    Cohort Stability & Sample Sufficiency Protocol v0 /
    长窗口 Cohort 稳定性与样本充足协议 v0.
  - [x] Long-window run cadence recorded (W1=1 h, W2=4 h,
    W3=24 h, W4+ multi-day reserved; operator-driven; not
    auto-scheduled).
  - [x] Per-window evidence fields recorded verbatim
    (`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`,
    `PAPER_ALPHA_GATE_EVALUATED`,
    `PAPER_ALPHA_RULE_EVALUATED`,
    `PAPER_ALPHA_COHORT_EVALUATED`,
    `PAPER_ALPHA_REPORT_GENERATED`, daily report Regime &
    Cluster section, daily report Paper Alpha Gate section,
    `sample_count`, `completed_tail_label_count`,
    `regime_cluster_evidence_status`,
    `paper_alpha_gate_status`,
    `insufficient_sample_reasons`, export package, export
    contains `REGIME_CLUSTER_*` events, export contains
    `PAPER_ALPHA_*` events, safety flags).
  - [x] Sample sufficiency principle recorded
    (`INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` are valid
    outputs not failures; cohort signals only allowed once
    sample-sufficient; cohort signals remain
    paper-only / report-only / evidence-only; cannot
    trigger trades / modify parameters / relax rules /
    enter Phase 12).
  - [x] Cohort stability principle recorded (signals must
    persist across windows; inversion is a warning;
    biased toward "do nothing" when stability is unclear).
  - [x] Allowed outputs explicitly listed
    (`long_window_run_plan`, `sample_sufficiency_checklist`,
    `cohort_stability_checklist`,
    `operator_vps_evidence_template`,
    `export_replay_evidence_template`,
    `closeout_acceptance_template`) and marked descriptive
    only.
  - [x] Slice-specific forbidden items recorded
    (cannot trigger real trades / modify position size /
    modify leverage / modify stops / modify targets /
    modify Risk Engine / modify Execution FSM / let AI
    decide direction or sizing or leverage or stops or
    targets or execution / auto-optimise parameters /
    auto-relax rules / auto-schedule W1 / W2 / W3 / W4+;
    cannot replace Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule; cannot replace Paper
    Alpha Gate v0 `INCONCLUSIVE` rule; cannot enter Phase
    12).
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
dataset-driven retrospective audits, and an
alpha-evidence gate are *all* candidate slices. Two child
slices already shipped (B-B-B-A — Paper Alpha Gate v0;
B-B-B-B — Regime & Cluster Cohort Evidence Pack v0).
Bundling further work into a single PR would conflate
independent design decisions, risk overscope, and break
the established pattern of small, auditable child slices
(Phase 11C.1C-C-A → Phase 11C.1C-C-B-A → Phase
11C.1C-C-B-B-A → Phase 11C.1C-C-B-B-B-A → Phase
11C.1C-C-B-B-B-B → Phase 11C.1C-C-B-B-B-C).

Phase 11C.1C-C-B-B-B-C therefore carves out **only** the
*Long-Window Cohort Stability & Sample Sufficiency
Protocol v0* — a docs / evidence-template-only protocol
that codifies the long-window paper data-collection
cadence, the sample sufficiency rule, and the cohort
stability acceptance criteria. This directly applies the
AMOS governance
(`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`) to
the next concrete step: **add fewer modules, accumulate
more structural data; verify Regime more, talk less about
"strategy"; and prove which states really carry right-tail
value rather than chase a universal model**.

## Out of scope (handled by future PRs in the cycle)

The substantive Phase 11C.1C-C-B-B-B-C closeout — the
verbatim W1 / W2 / W3 operator-VPS evidence transcripts,
the cross-window cohort stability checklist results, and
the Phase 8.5 export / Phase 10A replay round-trip
evidence — is **out of scope** for this docs-only kickoff.
It will be authored alongside a future docs-only closeout
PR after the operator captures the W1 / W2 / W3 paper
evidence on the operator-VPS, and reviewed against the
Phase 1 safety lock + the AMOS governance rails in
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` (Truth
Layer / Reality Check / Anti-overfitting / Feedback
Isolation / Limited Complexity).
