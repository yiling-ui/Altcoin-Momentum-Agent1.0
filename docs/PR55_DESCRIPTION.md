# PR #55 — Phase 11C.1C-C-B-B-B-B: Regime & Cluster Cohort Evidence Pack v0 (docs-only kickoff)

> **Status: DOCS-ONLY KICKOFF / SCOPE ALIGNMENT.** This PR
> introduces Phase 11C.1C-C-B-B-B-B (*Regime & Cluster
> Cohort Evidence Pack v0 / Regime 与 Cluster 分组证据包 v0*)
> at `NEXT_ALLOWED / NOT_STARTED` as the **second child
> slice** under the Phase 11C.1C-C-B-B-B parent. The parent
> phase is **not** renamed: Phase 11C.1C-C-B-B-B remains
> *Strategy Validation Lab (deeper) & richer Cluster
> Exposure Control follow-up*. **No runtime code is shipped
> by this PR.**
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> strategy implementation. **NOT** a trading module. **NOT**
> the complete Strategy Validation Lab follow-up. **NOT**
> the Phase 11C.1C-C-B-B-B-B *implementation* (that lands
> in a separate PR after this kickoff is reviewed). **NOT**
> Phase 12.
>
> When implemented, every artefact this slice produces
> (`regime_cohort_summary`, `cluster_cohort_summary`,
> `score_bucket_summary`, `stage_outcome_summary`,
> `strategy_mode_outcome_summary`,
> `regime_cluster_evidence_pack`, `warnings`,
> `insufficient_sample_reasons`) will be a **descriptive
> label** for human review only. Outputs **MUST NEVER**
> trigger a real trade or modify position size, leverage,
> stop-loss, target price, the Risk Engine, or the
> Execution FSM. The Risk Engine remains the single
> trade-decision gate.

## Phase

  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 merged
    into `main`, 2026-05-23, mergeCommit `3ecfc3b`).
    Provides the `StrategyValidationDataset` /
    `StrategyValidationQualityGate` artefacts the
    evidence pack will read.
  - **Phase 11C.1C-C-B-A** — `ACCEPTED` (PR #42 merged into
    `main`, 2026-05-23, mergeCommit `cc18047`). Provides
    the `StrategyValidationSample` /
    `StrategyValidationReport` / `ClusterExposureAssessment`
    artefacts the evidence pack will read.
  - **Phase 11C.1C-C-A** — `ACCEPTED` (PR #40 merged into
    `main`, 2026-05-23, mergeCommit `75d3c7c`). Provides
    the `LabelTrackingRecord` / `tail_label` / `mfe_pct` /
    `mae_pct` / `MISSED_TAIL_DETECTED` /
    `FAKE_BREAKOUT_DETECTED` outcomes the evidence pack
    will read.
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    *Parent* phase. Strategy Validation Lab (deeper) &
    richer Cluster Exposure Control follow-up. **Not
    renamed by this PR.** Phase 11C.1C-C-B-B-B-B is one
    *child slice* under this parent (the second child
    slice), not the parent itself.
  - **Phase 11C.1C-C-B-B-B-A** — `ACCEPTED` (PR #52 merged
    into `main`, 2026-05-24, mergeCommit `f8ba315`;
    closeout via PR #54). First child slice under Phase
    11C.1C-C-B-B-B (*Paper Alpha Gate v0*). Paper /
    report-only. The Paper Alpha Gate verdict is one of
    the upstream artefacts the evidence pack will
    cross-reference (read-only).
  - **Phase 11C.1C-C-B-B-B-B** — *introduced by this PR*.
    `NEXT_ALLOWED / NOT_STARTED`. **Second child slice**
    under Phase 11C.1C-C-B-B-B. Regime & Cluster Cohort
    Evidence Pack v0. Paper / report / evidence-only. No
    trade authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Branch + base

  - Branch: `docs/phase-11c1c-c-b-b-b-b-regime-cluster-evidence-kickoff`
  - Base: `main` (post PR #54 closeout).

## What this PR does

  - **Introduces** Phase 11C.1C-C-B-B-B-B as the second
    child slice under Phase 11C.1C-C-B-B-B.
  - **Defines** the Regime & Cluster Cohort Evidence Pack
    v0 scope, boundary, allowed outputs, eight cohort
    questions, core principles, forbidden-item list, and
    acceptance-gate placeholder in
    `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`.
  - **Records** the parent / child relationship explicitly
    in `docs/PHASE_GATE.md` and `docs/PROJECT_STATUS.md` so
    the parent phase is **not** renamed.
  - **Refreshes** the *Architecture governance
    (guidance-only; no phase change)* closing paragraph in
    `docs/PHASE_GATE.md` to reflect the current open-phase
    state (B-B-A = ACCEPTED; B-B-B = NEXT_ALLOWED /
    NOT_STARTED; B-B-B-A = ACCEPTED; B-B-B-B = NEXT_ALLOWED
    / NOT_STARTED; Phase 12 = FORBIDDEN).
  - **Records** this PR in `docs/CHANGELOG.md > [Unreleased]`
    and `docs/PR55_DESCRIPTION.md`.

## What this PR does NOT do

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

## Changed files

```
docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md   (NEW)
docs/PR55_DESCRIPTION.md                                       (NEW)
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
  - `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`
    (NEW)
  - `docs/PR55_DESCRIPTION.md` (NEW; this document)

## Allowed outputs (paper / report / evidence-only) — recorded for the implementation PR

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

## Questions to be answered by cohort evidence

  1. Which Regimes are more likely to produce
     `strong_tail` / `reached_3r` / `reached_5r`?
  2. Which Regimes are more likely to produce
     `fake_breakout` / `late_chase_failure`?
  3. Is the `cluster_leader` materially better than its
     followers on the same cohort?
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

## Core principles (carried forward verbatim)

  - Add fewer modules; accumulate more structural data.
  - Talk less about "strategy"; verify Regime more.
  - Stop chasing a universal model; prove which states
    really carry right-tail value.
  - All new content must be replayable.
  - All new content must reduce the human-interpretation
    cost.
  - All new content must serve Regime / Liquidity / Right
    Tail judgement.
  - Forbid unverifiable AI output.
  - Forbid system-complexity growth.
  - Forbid loosening rules on low samples.

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
  - Risk Engine override / bypass.
  - Execution FSM override / bypass.
  - Phase Gate override / bypass.
  - Triggering a real trade from any evidence-pack output.
  - Modifying position size / leverage / stop-loss / target
    price from any evidence-pack output.
  - Modifying the Risk Engine or the Execution FSM from
    any evidence-pack output.
  - Replacing the Paper Alpha Gate v0 verdict with
    evidence-pack output (the evidence pack is *additive*,
    not a replacement).
  - Implementing the Regime & Cluster Cohort Evidence Pack
    v0 (this PR is docs-only; the implementation lands in
    a separate PR that opens Phase 11C.1C-C-B-B-B-B as the
    second child slice under Phase 11C.1C-C-B-B-B).
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
  - Modifying strategy runtime code.
  - Modifying runtime behaviour.
  - Implementing new functionality.
  - Flipping any phase's acceptance state. Phase
    11C.1C-C-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`.
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B-B is introduced at `NEXT_ALLOWED /
    NOT_STARTED`. Phase 12 remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase keeps
    its existing definition — *Strategy Validation Lab
    (deeper) & richer Cluster Exposure Control follow-up*.
  - Phase 11C.1C-C-B-B-B-B implementation (out of scope
    for this kickoff PR).
  - Phase 12 / live trading kickoff.

## Acceptance gate (docs-only)

  - Docs-only PR. **No code modified** under `app/`,
    `scripts/`, `tests/`, `configs/`, `risk/`, `execution/`,
    `llm/`, `telegram/`, or `exchange/`.
  - **No new Python files.**
  - **No new event types.**
  - **No new tests.**
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
  - [x] No runtime behaviour changed.
  - [x] No `app/` / `scripts/` / `tests/` / `configs/`
    changes.
  - [x] No `execution/` / `risk/` / `llm/` / `telegram/` /
    `exchange/` changes.
  - [x] No strategy runtime code changes.
  - [x] No phase's acceptance state flipped — Phase
    11C.1C-C-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`;
    Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`; Phase
    11C.1C-C-B-B-B-B is introduced at `NEXT_ALLOWED /
    NOT_STARTED`.
  - [x] Phase 11C.1C-C-B-B-B parent is **not** renamed; it
    remains *Strategy Validation Lab (deeper) & richer
    Cluster Exposure Control follow-up*.
  - [x] Phase 11C.1C-C-B-B-B-B is recorded as the second
    child slice under Phase 11C.1C-C-B-B-B = Regime &
    Cluster Cohort Evidence Pack v0 / Regime 与 Cluster 分
    组证据包 v0.
  - [x] Allowed outputs explicitly listed
    (`regime_cohort_summary`, `cluster_cohort_summary`,
    `score_bucket_summary`, `stage_outcome_summary`,
    `strategy_mode_outcome_summary`,
    `regime_cluster_evidence_pack`, `warnings`,
    `insufficient_sample_reasons`) and marked descriptive
    only.
  - [x] Eight cohort questions recorded.
  - [x] Core principles recorded verbatim (少加模块 / 多积
    累结构数据; 少讲策略 / 多验证 Regime; 少追求全能 / 多证
    明哪些状态真的有右尾价值; 可 Replay; 减少人工解释成本;
    服务 Regime / Liquidity / Right Tail 判断; 禁止不可验
    证 AI 输出; 禁止系统复杂度膨胀; 禁止根据低样本放宽规
    则).
  - [x] Slice-specific forbidden items recorded
    (cannot trigger real trades / modify position size /
    modify leverage / modify stops / modify targets /
    modify Risk Engine / modify Execution FSM / let AI
    decide direction or sizing or leverage or stops or
    targets or execution / auto-optimise parameters /
    auto-relax rules; cannot enter Phase 12).
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
alpha-evidence gate are *all* candidate slices. The first
child slice (Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0)
already shipped. Bundling further deeper work into a single
PR would conflate independent design decisions, risk
overscope, and break the established pattern of small,
auditable child slices (Phase 11C.1C-C-A → Phase
11C.1C-C-B-A → Phase 11C.1C-C-B-B-A → Phase
11C.1C-C-B-B-B-A → Phase 11C.1C-C-B-B-B-B).

Phase 11C.1C-C-B-B-B-B therefore carves out **only** the
*Regime & Cluster Cohort Evidence Pack v0* — a read-only /
evidence-only compression layer that organises the data
already produced by the upstream slices into cohort
summaries by Regime, Cluster, Stage, Strategy Mode, and
Score Bucket. This directly applies the AMOS governance
(`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`) to the
next concrete step: add fewer modules, accumulate more
structural data; verify Regime more, talk less about
"strategy"; and prove which states really carry right-tail
value rather than chase a universal model.

## Out of scope (handled by the implementation PR)

The substantive Regime & Cluster Cohort Evidence Pack v0
implementation contract — exact event names (if any),
schema versions, dataclasses, threshold defaults,
daily-report layout, Phase 8.5 export / Phase 10A replay
compatibility, brief-mandated tests, dry-run / real-WS
smoke evidence — is **out of scope** for this docs-only
kickoff. It will be authored alongside the Phase
11C.1C-C-B-B-B-B implementation PR and reviewed against
the Phase 1 safety lock + the AMOS governance rails in
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` (Truth
Layer / Reality Check / Anti-overfitting / Feedback
Isolation / Limited Complexity).
