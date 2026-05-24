# Phase 11C.1C-C-B-B-B-B — Regime & Cluster Cohort Evidence Pack v0

> **Chinese name / 中文名:** *Regime 与 Cluster 分组证据包 v0*.
>
> **Status: ACCEPTED (closed 2026-05-24; PR #56 merged into
> `main` on 2026-05-24, mergeCommit `1a9abe2`; this docs-only
> closeout PR #57 records the operator-VPS paper evidence
> that flips the slice to `ACCEPTED`).** This document
> opened Phase 11C.1C-C-B-B-B-B as the **second child
> slice** under the Phase 11C.1C-C-B-B-B parent (*Strategy
> Validation Lab (deeper) & richer Cluster Exposure Control
> follow-up*). The parent phase is **not** renamed; it
> keeps its existing definition. Phase 11C.1C-C-B-B-B-A
> (*Paper Alpha Gate v0*) remains `ACCEPTED` (PR #52 + PR
> #54 closeout). Phase 11C.1C-C-B-B-B-C is now
> **NEXT_ALLOWED / NOT_STARTED** as the next child slice
> under the same parent (placeholder; not yet defined).
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



## Implementation summary (PR #56)

> **Status after PR #56:** Phase 11C.1C-C-B-B-B-B remains
> `NEXT_ALLOWED / NOT_STARTED` until the operator-VPS paper
> smoke + closeout PR records the acceptance evidence. PR
> #56 ships the substantive implementation (paper / report /
> evidence only); the closeout will flip the slice to
> `ACCEPTED`.
>
> The slice's per-cohort `status` is one of
> `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` /
> `EVIDENCE_SIGNAL` and is a **descriptive label only**.
> Every artefact (`regime_cohort_summary`,
> `cluster_cohort_summary`, `score_bucket_summary`,
> `stage_outcome_summary`,
> `strategy_mode_outcome_summary`,
> `regime_cluster_evidence_pack`, `warnings`,
> `insufficient_sample_reasons`) **MUST NEVER** trigger a
> real trade or modify position size, leverage, stop-loss,
> target price, the Risk Engine, or the Execution FSM. The
> Risk Engine remains the single trade-decision gate.

### What PR #56 ships

  - **`app/adaptive/regime_cluster_evidence_pack.py`**
    (NEW) — value objects + pure functions; schema version
    `phase_11c_1c_c_b_b_b_b.regime_cluster_evidence_pack.v1`.
    Deterministic / pure; no I/O, no clock read, no event
    emission, no network access, no API key read, no
    exchange call, no Risk Engine / Execution FSM
    mutation.
  - **`app/core/events.py`** — two new typed events:
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` and
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`. Both are
    paper / report / evidence only.
  - **`app/adaptive/strategy_validation_runtime.py`** —
    `StrategyValidationRuntimeConfig` extended with twelve
    new knobs (defaults match the module-level defaults);
    `observe_market_regime(opportunity_id, market_regime)`
    helper; new
    `_build_and_emit_regime_cluster_evidence_events` hook
    fires after the Phase 11C.1C-C-B-B-B-A Paper Alpha Gate
    evaluation; `metrics_payload()` extended with the new
    aggregates.
  - **`app/market_data_public/ws_radar_chain.py`** —
    `WSRadarChainDriver._post_chain` calls
    `strategy_validation_runtime.observe_market_regime`
    after every adaptive context is built so the pack can
    group on `market_regime`. Records whose regime was not
    observed safely degrade to `unknown`.
  - **`app/paper_run/daily_report.py`** —
    `DailyReportSnapshot` extended with fourteen new
    fields; the Markdown body renders a new
    *Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
    Evidence Pack v0* section with the boundary banner and
    per-cohort row rendering.
  - **`tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`**
    (NEW) — 23 brief-mandated tests.
  - **`tests/unit/test_phase11b_no_network.py`** —
    `allowed_phase_11b_references` allowlist extended with
    the two new EventType labels.

### Acceptance evidence ladder

| Layer                                                       | Result                                                |
| ----------------------------------------------------------- | ----------------------------------------------------- |
| `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py` | **23/23 PASS** (brief-mandated cases) |
| `tests/unit/ -k phase11c_`                                  | **389/389 PASS** (366 baseline + 23 new) |
| `tests/` (full surface)                                     | **2363/2363 PASS** (no regression vs. post-PR-#55 main baseline) |
| 30 s dry-run smoke                                          | Daily report contains the new Phase 11C.1C-C-B-B-B-B section; `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` (expected for a 30 s window — Phase 11C.1C-C-A primary tracking window is 5 minutes and cannot complete in 30 s); explicit `regime_cluster_insufficient_sample_reasons` populated; no `ORDER_*` / `POSITION_*` / `STOP_*` / `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` events emitted. |
| Real-WS 10 min smoke                                        | **NOT REQUIRED** for this PR. PR #56 is a deterministic evidence-compression layer; non-empty cohort rows depend on the upstream Phase 11C.1C-C-A primary tracking window resolving. Real non-empty cohort validation is reserved for the Phase 11C.1C-C-B-B-B-B closeout / operator-VPS run. |
| Phase 8.5 export bundle                                     | Carries the two new event types (cross-checked by `test_regime_cluster_events_exportable`). |
| Phase 10A replay                                            | Accepts the two new event types without raising; legacy rows missing `schema_version` are tolerated (cross-checked by `test_replay_reads_regime_cluster_events`). |
| Phase 1 safety flags                                        | Unchanged (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). |
| Phase 12                                                    | **FORBIDDEN** (Phase 1 safety lock unchanged).         |

### Allowed outputs surfaced by PR #56

Each is a **descriptive label only**. None has trade
authority. None is read by the Risk Engine or the Execution
FSM:

  - `regime_cohort_summary`
  - `cluster_cohort_summary`
  - `score_bucket_summary`
  - `stage_outcome_summary`
  - `strategy_mode_outcome_summary`
  - `regime_cluster_evidence_pack`
  - `warnings`
  - `insufficient_sample_reasons`

### Closeout requirements (deferred to a future PR)

The slice will only flip to `ACCEPTED` after a separate
docs-only closeout PR records:

  - Operator-VPS 10 min real public WS paper smoke transcript
    (`duration_seconds=600.0`, `dry_run=false`,
    `ws_real_transport=true`, non-zero
    `ws_messages_received` / `ws_chains_emitted`,
    `ingestion_errors=0`, no rate-limit violations).
  - Daily report excerpt showing the Phase 11C.1C-C-B-B-B-B
    section with non-empty cohort rows for the cohorts
    where the upstream Phase 11C.1C-C-A primary tracking
    window has resolved sufficient samples; cohorts that do
    not yet reach the configured minimums are correctly
    marked `INSUFFICIENT_SAMPLE` per the brief's "do not
    loosen rules on low samples" rule.
  - SQLite event-count query for
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` and
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`.
  - Phase 8.5 export bundle reference confirming the new
    event types are present in the zip.
  - Safety-flag invariants captured verbatim.

## Safety flags after PR #56 (Phase 1 lock unchanged)

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



## Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED + Phase 8.5 export bundle) — FILED via PR #57

> **Status flipped:** Phase 11C.1C-C-B-B-B-B is now
> **ACCEPTED** (PR #56 merged into `main` on 2026-05-24,
> mergeCommit `1a9abe2`; this docs-only closeout PR #57
> records the operator-VPS paper evidence below). The
> closeout mirrors the PR #36 → PR #37, PR #38 → PR #39, PR
> #40 → PR #41, PR #42 → PR #43, PR #44 → PR #50, and PR
> #52 → PR #54 docs-only closeout pattern.

### Operator-VPS 10 min WS paper smoke

```
duration_seconds                = 600.0
uptime                          ≈ 608s
ws_first                        = true
ws_real_transport               = true
ingestion_errors                = 0
HTTP 429 count                  = 0
HTTP 418 count                  = 0
```

### Regime & Cluster Cohort Evidence Pack daily report

```
daily report contains           : "## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"
regime_cluster_evidence_status  = INSUFFICIENT_SAMPLE
sample_count                    = 14
completed_tail_label_count      = 0
insufficient_sample_reasons     :
  - sample_count_below_min=14<20
  - completed_tail_label_count_below_min=0<10
```

### Regime & Cluster event counts (runner snapshot + events.db type-count cross-check, after shutdown flush)

```
REGIME_CLUSTER_EVIDENCE_PACK_GENERATED  = 1
REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 5
```

### Phase 8.5 export bundle

```
export_test_data                = OK
export zip                      = data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip
manifest_event_count            = 3151
redaction_applied               = True
events.jsonl                    = exists
export contains REGIME_CLUSTER_* events                  = yes
EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK                     = PASS
```

### Export package files observed

```
manifest.json
summary_report.md
events.jsonl
opportunities.jsonl
signal_snapshots.jsonl
risk_decisions.jsonl
state_transitions.jsonl
capital_events.jsonl
virtual_trade_plans.jsonl
```

### Why `regime_cluster_evidence_status = INSUFFICIENT_SAMPLE` was the expected and accepted result

`regime_cluster_evidence_status = INSUFFICIENT_SAMPLE` is
an **expected and accepted** result for this smoke window
because `sample_count = 14 < 20` and
`completed_tail_label_count = 0 < 10`. This means the
Regime & Cluster Evidence Pack **correctly refused to
overfit or force a regime / cluster conclusion when
structural samples were insufficient**. The brief's
"forbid loosening rules on low samples" rule was honoured
end-to-end:

  - **`INSUFFICIENT_SAMPLE` does NOT mean runtime failure.**
    The runtime emitted both new event types
    (`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`), the
    daily report rendered the new section, and the export
    bundle round-trips cleanly through Phase 8.5 / Phase
    10A.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise strategy
    changes.** No threshold / parameter / strategy change
    is implied by or permitted on the basis of this
    status.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise rule
    relaxation.** No cohort minimum, no quality-gate
    threshold, no Paper Alpha Gate threshold, and no Risk
    Engine threshold may be widened in response.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise live
    trading.** The Risk Engine remains the single
    trade-decision gate, and no execution surface reads
    the evidence pack.
  - **`INSUFFICIENT_SAMPLE` does NOT authorise Phase 12.**
    Phase 12 stays `FORBIDDEN` under the Phase 1 safety
    lock.

### Safety boundary held end-to-end across the operator-VPS run

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

### Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise

  - Phase 11C.1C-C-B-B-B-B acceptance does **NOT** authorise
    live trading.
  - Phase 11C.1C-C-B-B-B-B acceptance does **NOT** authorise
    API keys.
  - Phase 11C.1C-C-B-B-B-B acceptance does **NOT** authorise
    private endpoints.
  - Phase 11C.1C-C-B-B-B-B acceptance does **NOT** authorise
    DeepSeek trade decisions.
  - Phase 11C.1C-C-B-B-B-B acceptance does **NOT** authorise
    real Telegram outbound.
  - Phase 11C.1C-C-B-B-B-B acceptance does **NOT** authorise
    Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard
    gate.
  - Phase 11C.1C-C-B-B-B-B acceptance does **NOT** authorise
    Phase 12.
  - Regime & Cluster Evidence Pack outputs remain
    paper-only / report-only / evidence-only.
  - Regime & Cluster Evidence Pack outputs cannot trigger
    orders, leverage, position sizing, stop changes, target
    changes, Risk Engine changes, or Execution FSM changes.

### Acceptance conditions checked off

  - [x] Operator-VPS 10 min WS paper smoke PASSED
    (`duration_seconds=600.0`, `uptime≈608s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`).
  - [x] Daily report contains
    `"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
    Evidence Pack v0"`.
  - [x] `regime_cluster_evidence_status =
    INSUFFICIENT_SAMPLE` is correctly recorded as the
    expected and accepted result for `sample_count=14<20`
    + `completed_tail_label_count=0<10`.
  - [x] `insufficient_sample_reasons` populated with
    explicit reasons (`sample_count_below_min=14<20`,
    `completed_tail_label_count_below_min=0<10`).
  - [x] `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1` and
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`
    cross-checked against the events.db type-count query
    after shutdown flush.
  - [x] Phase 8.5 export zip generated successfully
    (`data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip`,
    `manifest_event_count=3151`,
    `redaction_applied=True`, `events.jsonl` exists,
    export contains `REGIME_CLUSTER_*` events,
    `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK=PASS`).
  - [x] Export package files observed (`manifest.json`,
    `summary_report.md`, `events.jsonl`,
    `opportunities.jsonl`, `signal_snapshots.jsonl`,
    `risk_decisions.jsonl`, `state_transitions.jsonl`,
    `capital_events.jsonl`,
    `virtual_trade_plans.jsonl`).
  - [x] Phase 1 safety flags unchanged (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`).
  - [x] No Binance API key.
  - [x] No Binance API secret.
  - [x] No signed endpoint.
  - [x] No account / order / position / leverage / margin
    endpoint.
  - [x] No private WebSocket.
  - [x] No `listenKey`.
  - [x] No DeepSeek trade decision.
  - [x] No real Telegram outbound.
  - [x] No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event
    emitted by the new pipeline.
  - [x] No evidence-pack output is read by the Risk Engine
    or the Execution FSM.
  - [x] Phase 12 stays `FORBIDDEN`.

This docs-only closeout PR #57 is therefore complete; Phase
11C.1C-C-B-B-B-B is now **ACCEPTED**; Phase
11C.1C-C-B-B-B-C is now **NEXT_ALLOWED / NOT_STARTED**;
Phase 12 remains **FORBIDDEN**.
