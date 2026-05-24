# Phase 11C.1C-C-B-B-B-B — Regime & Cluster Cohort Evidence Pack v0

> **Chinese name / 中文名:** *Regime 与 Cluster 分组证据包 v0*.
>
> **Status: NEXT_ALLOWED / NOT_STARTED (docs-only kickoff /
> scope alignment).** This document opens Phase
> 11C.1C-C-B-B-B-B as the **second child slice** under the
> Phase 11C.1C-C-B-B-B parent (*Strategy Validation Lab
> (deeper) & richer Cluster Exposure Control follow-up*).
> The parent phase is **not** renamed; it keeps its existing
> definition. Phase 11C.1C-C-B-B-B-A (*Paper Alpha Gate v0*)
> remains `ACCEPTED` (PR #52 + PR #54 closeout). **No
> runtime code is shipped by this PR.** The substantive
> implementation is reserved for a separate implementation
> PR that will land after this docs-only kickoff is
> reviewed.
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT**
> reinforcement-learning-driven parameter tuning. **NOT** a
> strategy-implementation slice. **NOT** a trading module.
> **NOT** the complete Strategy Validation Lab follow-up.
> **NOT** Phase 12.
>
> The Risk Engine remains the single trade-decision gate.
> Every artefact this slice produces (regime / cluster /
> bucket / stage / strategy-mode cohort summaries, the
> consolidated `regime_cluster_evidence_pack`, warnings, and
> insufficient-sample reasons) is a **descriptive label**
> for human review and **MUST NEVER trigger a real trade**,
> **MUST NEVER** modify position size, leverage, stop-loss,
> target price, the Risk Engine, or the Execution FSM.

## Why this slice exists (positioning under AMOS)

This slice is a direct application of the
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` governance
to the next concrete step under Phase 11C.1C-C-B-B-B. AMOS
treats AMA-RT as an *Adaptive Market Operating System*: the
goal is long-term stable operation, adapting to market
change, and being capable of capturing 5x+ right-tail upside
*when it is genuinely available* — **not** promising
returns, **not** running an auto-strategy bot, and **not**
letting AI drive execution.

Under that frame, the project's main line must converge on:

  - Add fewer modules; accumulate more structural data.
  - Talk less about "strategy"; verify Regime more.
  - Stop chasing a universal model; prove which states
    really carry right-tail value.
  - Evidence first, runtime change later.

Phase 11C.1C-C-B-B-B-B is exactly that step. Instead of
adding a new strategy or a new execution surface, this
slice defines **how we will compress the paper-only data
already produced by the upstream slices** (Phase 11C.1C-C-A
label-tracking outcomes, Phase 11C.1C-C-B-A validation
samples / cluster exposure assessments, Phase 11C.1C-C-B-B-A
validation dataset / quality gate, Phase 11C.1C-C-B-B-B-A
Paper Alpha Gate v0 verdict) into a **structured cohort
evidence pack** organised by Regime, Cluster, Stage,
Strategy Mode, and Score Bucket — so that the questions
"which states carry right-tail value, and which states
must be down-weighted or rejected" become answerable with
data, not opinion.

## Phase boundary (parent / child relationship)

  - **Phase 11C.1C-C-A** — `ACCEPTED` (PR #40 merged into
    `main`, 2026-05-23, mergeCommit `75d3c7c`). Provides
    `LABEL_TRACKING_*` / `LABEL_WINDOW_*` / `TAIL_LABEL_ASSIGNED`
    / `MFE_pct` / `MAE_pct` / `tail_label` outcomes per
    ACTIVE candidate.
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
    renamed** by this kickoff; this slice is one *child
    slice* under this parent.
  - **Phase 11C.1C-C-B-B-B-A** — `ACCEPTED` (PR #52 merged
    into `main`, 2026-05-24, mergeCommit `f8ba315`; closeout
    via PR #54). First child slice under Phase
    11C.1C-C-B-B-B. Paper Alpha Gate v0. Paper /
    report-only. The Paper Alpha Gate verdict (`PASS` /
    `WARN` / `FAIL` / `INCONCLUSIVE`) is one of the
    upstream artefacts the evidence pack will reference.
  - **Phase 11C.1C-C-B-B-B-B** — *this document*.
    `NEXT_ALLOWED / NOT_STARTED`. **Second child slice**
    under Phase 11C.1C-C-B-B-B. Regime & Cluster Cohort
    Evidence Pack v0. Paper / report / evidence-only. No
    trade authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Scope (what this slice is)

Phase 11C.1C-C-B-B-B-B is a **read-only / evidence-only
compression layer** on top of the artefacts produced by
the upstream slices. It does not add a new strategy, a new
execution surface, a new optimiser, or a new AI authority.
Its job is to organise the data we already produce into
cohort summaries that make the right questions answerable.

The substantive contract — the field list, the schema
version, the daily-report layout, the threshold defaults,
the brief-mandated tests, the dry-run / real-WS smoke
evidence — is **out of scope for this kickoff PR** and will
be authored alongside the Phase 11C.1C-C-B-B-B-B
implementation PR. This kickoff records only the scope,
boundary, forbidden list, allowed-output list, and the
acceptance-gate placeholder.

### Inputs the evidence pack reads (from upstream phases)

  - `StrategyValidationDataset` (Phase 11C.1C-C-B-B-A) and
    `StrategyValidationQualityGate` status / reasons.
  - `StrategyValidationReport` (Phase 11C.1C-C-B-A) and the
    seven `STRATEGY_VALIDATION_*` events.
  - `ClusterExposureAssessment` (Phase 11C.1C-C-B-A) with
    `cluster_id`, `cluster_leader`, follower set,
    `suggested_cluster_action`.
  - `LabelTrackingRecord` outcomes (Phase 11C.1C-C-A) with
    `tail_label`, `mfe_pct`, `mae_pct`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`.
  - `AdaptiveCandidateContext` (Phase 11C.1C-A / 11C.1C-B)
    fields: `market_regime`, `candidate_stage`,
    `strategy_mode`, `opportunity_score`,
    `early_tail_score`, `runtime_calibration` (15 fields).
  - `PaperAlphaGateReport` (Phase 11C.1C-C-B-B-B-A) verdict
    + cohort results (read for cross-referencing only; the
    evidence pack does not override or replace it).

### Outputs the evidence pack is permitted to produce

The implementation PR will produce **only** the following
report-only artefacts. Each is paper-only / descriptive
/ replay-friendly. None has trade authority.

  - `regime_cohort_summary` — per-`market_regime` cohort row
    (sample count, completed-tail-label count,
    `strong_tail_rate`, `reached_3r_rate`, `reached_5r_rate`,
    `fake_breakout_rate`, `missed_tail_rate`,
    `late_chase_failure_rate`, `avg_mfe`, `avg_mae`).
  - `cluster_cohort_summary` — per-`cluster_id` cohort row
    (size, leader symbol, follower set, sample count,
    leader-vs-follower advantage on `strong_tail_rate` /
    `reached_3r_rate` / `avg_mfe`,
    `suggested_cluster_action` distribution).
  - `score_bucket_summary` — per-`opportunity_score_bucket`
    and per-`early_tail_score_bucket` cohort row (sample
    count, `strong_tail_rate`, `reached_3r_rate`,
    `reached_5r_rate`, `fake_breakout_rate`,
    `late_chase_failure_rate`).
  - `stage_outcome_summary` — per-`candidate_stage` cohort
    row (sample count, `strong_tail_rate`,
    `fake_breakout_rate`, `missed_tail_rate`,
    `late_chase_failure_rate`).
  - `strategy_mode_outcome_summary` — per-`strategy_mode`
    (`follow` / `pullback` / `observe` / `reject`) cohort
    row (sample count, `strong_tail_rate`,
    `fake_breakout_rate`, expected-vs-actual outcome
    distribution).
  - `regime_cluster_evidence_pack` — top-level container
    that bundles the five summaries above, the upstream
    Paper Alpha Gate verdict, and a small `warnings` /
    `insufficient_sample_reasons` block. Carries
    `report_id`, `dataset_id`, `evaluated_at`,
    `schema_version`, and a version block (strategy /
    scoring / risk-config / state-machine versions) so the
    artefact is fully replayable.
  - `warnings` — paper-only diagnostic warnings
    (`fake_breakout_warning`, `late_chase_warning`,
    `missed_alpha_warning`, `follower_outperforms_leader_warning`,
    `low_sample_warning`, `regime_outcome_inverted_warning`).
  - `insufficient_sample_reasons` — explicit list of cohorts
    where sample count fell below the implementation PR's
    minimum (so the evidence pack never silently inflates
    rates on thin data; missing data is treated as
    `INCONCLUSIVE`, not as a `PASS` or `FAIL`).

These outputs are **only** allowed forms. Any artefact that
implies a real-trade authority, a position-sizing
recommendation, a leverage decision, a stop-loss target,
or an Execution FSM transition is **out of scope** and
forbidden.

## Questions this slice must answer

Phase 11C.1C-C-B-B-B-B exists to make the following
questions answerable from cohort summaries (rather than
from anecdote, opinion, or a single backtest):

  1. Which Regimes are more likely to produce
     `strong_tail` / `reached_3r` / `reached_5r`?
  2. Which Regimes are more likely to produce
     `fake_breakout` / `late_chase_failure`?
  3. Is the `cluster_leader` materially better than its
     `follower`s on the same cohort?
  4. Does the high `opportunity_score_bucket` actually
     out-perform the low bucket?
  5. Does the high `early_tail_score_bucket` actually
     out-perform the low bucket?
  6. Do `follow` / `pullback` / `observe` / `reject`
     downstream outcomes match expectations?
  7. Which state combinations deserve continued paper
     observation?
  8. Which state combinations must be down-weighted or
     rejected?

The evidence pack must surface these answers as cohort
rows + warnings + insufficient-sample reasons. It must
**not** convert the answers into auto-decisions, parameter
mutations, or trade actions.

## Core principles (carried forward verbatim)

  - **Add fewer modules; accumulate more structural data.**
    The slice is allowed to add report-only aggregators; it
    is **not** allowed to add new runtime decision modules,
    new execution paths, or new AI authority.
  - **Talk less about "strategy"; verify Regime more.** The
    slice's centre of gravity is `market_regime` /
    `cluster_id` / `candidate_stage` cohorts, not
    `strategy_mode`-as-a-promise. `strategy_mode` is a
    label being **validated** by this slice, not a label
    being **trusted** by it.
  - **Stop chasing a universal model; prove which states
    really carry right-tail value.** Output rows must
    surface heterogeneity (some states have right-tail
    value, others do not) rather than collapse to a single
    "system score".
  - **All new content must be replayable.** Every artefact
    must round-trip through the Phase 8.5 export bundle
    and the Phase 10A replay engine; the implementation PR
    must demonstrate this.
  - **All new content must reduce the human-interpretation
    cost.** Each cohort row is rendered with a stable
    layout, sample counts, threshold annotations, and an
    explicit `INCONCLUSIVE` label when sample size is
    insufficient.
  - **All new content must serve Regime / Liquidity / Right
    Tail judgement.** Outputs that do not directly
    contribute to one of those three are out of scope for
    v0.
  - **Forbid unverifiable AI output.** No LLM-generated
    cohort interpretation is treated as fact. AI may
    *describe* a cohort row (when LLM features are turned
    on in a future phase under the AMOS rails), but its
    description is never recorded as the cohort's outcome.
  - **Forbid system-complexity growth.** The slice must add
    at most one cohesive evidence-pack module + the daily
    report rendering hook + the four documents (kickoff,
    PR description, PHASE_GATE entry, CHANGELOG entry).
    Any wider surface is out of scope and must be split
    into a separate child slice.
  - **Forbid loosening rules on low samples.** If a cohort
    has fewer samples than the configured minimum, the
    cohort is marked `INCONCLUSIVE` with the reason
    appended to `insufficient_sample_reasons`. The
    implementation PR is **not** allowed to silently
    accept thin data, and is **not** allowed to widen
    thresholds in response to thin data.

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
| Position size / leverage / stop-loss / target price | unchanged; cannot be modified by any evidence-pack output |
| `regime_cohort_summary`                     | descriptive label only; MUST NEVER trigger a real trade |
| `cluster_cohort_summary`                    | descriptive label only; MUST NEVER trigger a real trade |
| `score_bucket_summary`                      | descriptive label only; MUST NEVER trigger a real trade |
| `stage_outcome_summary`                     | descriptive label only; MUST NEVER trigger a real trade |
| `strategy_mode_outcome_summary`             | descriptive label only; MUST NEVER trigger a real trade |
| `regime_cluster_evidence_pack`              | descriptive label only; MUST NEVER trigger a real trade |
| `warnings` / `insufficient_sample_reasons`  | descriptive labels only; MUST NEVER trigger a real trade |
| AI authority                                | NOT permitted to decide direction / position size / leverage / stop / target / execution |
| Automatic parameter optimisation            | NOT permitted                |
| Reinforcement learning                      | NOT permitted                |
| Auto-rule-relaxation on low samples         | NOT permitted                |
| Phase 12 (live trading)                     | FORBIDDEN                    |

## Explicitly forbidden by this slice

This slice carries forward every Phase 1 / 11C.1B / 11C.1C-A
/ 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A /
11C.1C-C-B-B-B-A forbidden item verbatim, and adds the
following slice-specific forbidden items:

  - Triggering a real trade.
  - Modifying position size.
  - Modifying leverage.
  - Modifying stop-loss.
  - Modifying target price.
  - Modifying the Risk Engine.
  - Modifying the Execution FSM.
  - Letting AI / LLM decide direction, position size,
    leverage, stop-loss, target price, or execution.
  - Auto-optimising parameters.
  - Auto-relaxing rules.
  - Promoting any evidence-pack output
    (`regime_cohort_summary`, `cluster_cohort_summary`,
    `score_bucket_summary`, `stage_outcome_summary`,
    `strategy_mode_outcome_summary`,
    `regime_cluster_evidence_pack`, `warnings`,
    `insufficient_sample_reasons`) to a real-trade
    authority.
  - Replacing the Paper Alpha Gate v0 verdict with
    evidence-pack output. The Paper Alpha Gate v0 verdict
    remains the canonical descriptive label for "is the
    sample sufficient to claim alpha"; the evidence pack
    is *additive*, not a replacement.
  - Adding new event types, new Python modules, or new
    runtime behaviour in this kickoff PR. (The
    implementation PR may add a small evidence-pack module
    and at most a small number of new event types; the
    detailed contract will be authored there and reviewed
    against the Phase 1 safety lock + AMOS rails.)
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/` in this kickoff PR.
  - Modifying configuration schemas, defaults, or YAML in
    this kickoff PR.
  - Adding or modifying tests in this kickoff PR.
  - Flipping any phase's acceptance state. Phase
    11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-B is introduced at `NEXT_ALLOWED
    / NOT_STARTED`. Phase 12 remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
    its existing definition.
  - Phase 11C.1C-C-B-B-B-B *implementation* (out of scope
    for this kickoff PR; will be authored in a separate
    implementation PR).
  - Phase 12 / live trading kickoff.

## Acceptance gate (placeholder; to be detailed by the implementation PR)

The Phase 11C.1C-C-B-B-B-B implementation PR will define
the substantive gate criteria. The placeholders below
record what the gate is **expected** to require, so the
implementation PR is reviewed against a known shape:

  - `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`
    PASS (brief-mandated cases — exact count to be
    determined by the implementation PR).
  - `tests/unit -k phase11c_` PASS with no regression vs.
    the post-PR-#54 main baseline.
  - Full `tests/` PASS with no regression vs. the
    post-PR-#54 main baseline.
  - 30 s dry-run smoke produces the new evidence pack
    section (`regime_cohort_summary`,
    `cluster_cohort_summary`, `score_bucket_summary`,
    `stage_outcome_summary`,
    `strategy_mode_outcome_summary`,
    `regime_cluster_evidence_pack`, `warnings`,
    `insufficient_sample_reasons`) with `INCONCLUSIVE`
    cohort statuses for thin samples — exactly the brief's
    "do not loosen rules on low samples" requirement.
  - Operator-VPS 10 min real public WS smoke (paper-only)
    PASSED with non-empty cohort rows where the upstream
    label-tracking has produced enough completions to
    satisfy the configured cohort minimums; cohorts that
    do not yet reach the minimums are correctly marked
    `INCONCLUSIVE`.
  - Phase 8.5 export bundle round-trips the new evidence
    pack artefacts (zip generated, manifest event count
    sane, redaction applied, `events.jsonl` exists, the
    new event types — if any — are listed in the export
    package and accepted by the Phase 10A replay engine).
  - Daily report contains the new "Phase 11C.1C-C-B-B-B-B
    Regime & Cluster Cohort Evidence Pack v0" Markdown
    section.
  - Safety flags unchanged across the run (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by the evidence-pack slice.
  - No evidence-pack output is read by the Risk Engine or
    the Execution FSM.
  - Phase 12 stays `FORBIDDEN`.

## What this kickoff PR does

  - **Introduces** Phase 11C.1C-C-B-B-B-B as the second
    child slice under Phase 11C.1C-C-B-B-B.
  - **Defines** the Regime & Cluster Cohort Evidence Pack
    v0 scope, boundary, forbidden-item list, allowed
    outputs, and acceptance-gate placeholder in this
    document.
  - **Records** the parent / child relationship explicitly
    in `docs/PHASE_GATE.md` and `docs/PROJECT_STATUS.md` so
    the parent phase is **not** renamed.
  - **Refreshes** the *Architecture governance
    (guidance-only; no phase change)* closing paragraph in
    `docs/PHASE_GATE.md` to reflect the current open-phase
    state (B-B-B-A = ACCEPTED; B-B-B = NEXT_ALLOWED /
    NOT_STARTED; B-B-B-B = NEXT_ALLOWED / NOT_STARTED;
    Phase 12 = FORBIDDEN).
  - **Records** this PR in `docs/CHANGELOG.md > [Unreleased]`
    and `docs/PR55_DESCRIPTION.md`.

## What this kickoff PR does NOT do

  - It does **NOT** implement the Regime & Cluster Cohort
    Evidence Pack v0.
  - It does **NOT** add any new Python module under `app/`.
  - It does **NOT** add any new event type.
  - It does **NOT** modify any runtime behaviour.
  - It does **NOT** modify configuration schemas, defaults,
    or YAML.
  - It does **NOT** add or modify tests.
  - It does **NOT** flip any phase's acceptance state.
  - It does **NOT** rename Phase 11C.1C-C-B-B-B.
  - It does **NOT** authorise live trading, API keys,
    private endpoints, DeepSeek trade decisions, real
    Telegram outbound, AI Learning, automatic parameter
    optimisation, reinforcement learning, the complete
    Strategy Validation Lab follow-up, or Phase 12.
  - It does **NOT** modify `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `llm/`, `telegram/`,
    or `exchange/`.

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
