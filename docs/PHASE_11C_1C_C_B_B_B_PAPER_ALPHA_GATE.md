# Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0

> **Status: IN_REVIEW (PR #52 open).** The implementation PR
> ships the runtime data contracts + pure-function evaluator +
> deterministic rule set + four new typed events + daily-report
> section + tests + docs for the **first child slice** under
> Phase 11C.1C-C-B-B-B (Paper Alpha Gate v0). PR #51 (the
> docs-only kickoff) merged into `main` on 2026-05-24 and is
> the gating predecessor.
>
> **Phase 11C.1C-C-B-B-B-A (Paper Alpha Gate v0) is paper /
> report / evidence-only.** **NOT** live trading. **NOT** AI
> Learning. **NOT** automatic parameter optimisation. **NOT**
> reinforcement learning. **NOT** the complete Strategy
> Validation Lab follow-up. **NOT** Phase 12.
>
> The Risk Engine remains the single trade-decision gate. The
> Paper Alpha Gate v0 verdict (`PASS` / `WARN` / `FAIL` /
> `INCONCLUSIVE`) is a **descriptive label** for human review
> and **MUST NEVER trigger a real trade**, **MUST NEVER**
> modify position size, leverage, stop-loss, target price,
> Risk Engine state, or Execution FSM state.

## Phase boundary (parent / child relationship)

  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 merged into
    `main`, 2026-05-23, mergeCommit `3ecfc3b`). Strategy
    Validation Dataset Builder & Quality Gate v0. Paper /
    report-only. The dataset / summary / quality-gate
    artefacts produced by this slice are the *inputs* the
    Paper Alpha Gate v0 reads from.
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    *Parent* phase. Strategy Validation Lab (deeper) & richer
    Cluster Exposure Control follow-up. The parent phase is
    **not** renamed by Paper Alpha Gate v0; the Paper Alpha
    Gate v0 is one *child slice* under this parent.
  - **Phase 11C.1C-C-B-B-B-A** — *this document*.
    `IN_REVIEW` (PR #52 open). **First child slice** under
    Phase 11C.1C-C-B-B-B. Paper Alpha Gate v0. Paper /
    report-only. No trade authority. Reads
    `StrategyValidationDataset` /
    `StrategyValidationQualityGate` /
    `StrategyValidationReport` artefacts and emits a
    descriptive alpha-evidence verdict.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock unchanged.

## What ships

### 1. New module — `app/adaptive/paper_alpha_gate.py`

Pure-function module. Models:

  - `PaperAlphaGateStatus` — string-constant holder for the
    four allowed verdict labels (`PASS` / `WARN` / `FAIL` /
    `INCONCLUSIVE`).
  - `PaperAlphaGateRule` — named threshold check definition
    (rule_id, description, threshold, severity).
  - `PaperAlphaGateRuleResult` — one rule evaluation outcome
    (rule_id, triggered, observed_value, threshold, severity,
    message).
  - `PaperAlphaGateCohortResult` — one cohort dimension's
    outcome (dimension, sample_count, status, signals,
    warnings, notes, metrics).
  - `PaperAlphaGateInput` — the structured snapshot the gate
    consumes (report_id, dataset_id, sample_count,
    completed_tail_label_count, quality_gate_status,
    quality_gate_reasons, per-mode / per-stage / per-bucket /
    per-cluster cohort stats, version block,
    schema_version).
  - `PaperAlphaGateReport` — top-level report container
    (report_id, dataset_id, sample_count,
    quality_gate_status, evaluated_at, gate_status, reasons,
    warnings, rule_results, cohort_results, version block,
    schema_version).

Pure functions:

  - `build_paper_alpha_gate_input(dataset, quality_gate_result,
    validation_report, *, report_id=None)` → builds a
    `PaperAlphaGateInput` from the upstream artefacts.
  - `evaluate_paper_alpha_gate(gate_input, ...)` →
    `(gate_status, reasons, warnings, cohort_results,
    rule_results)`. **Deterministic.**
  - `evaluate_strategy_mode_alpha(gate_input, ...)` →
    per-strategy_mode `PaperAlphaGateCohortResult`.
  - `evaluate_candidate_stage_alpha(gate_input, ...)` →
    per-candidate_stage `PaperAlphaGateCohortResult`.
  - `evaluate_score_bucket_alpha(gate_input, ...)` → 2-tuple of
    `PaperAlphaGateCohortResult` for opportunity_score and
    early_tail_score buckets.
  - `evaluate_cluster_alpha(gate_input, ...)` → cluster-leader
    `PaperAlphaGateCohortResult`.
  - `build_paper_alpha_gate_report(gate_input, *, evaluated_at,
    ...)` → assembles the full `PaperAlphaGateReport`.
  - `export_paper_alpha_gate_payload(report)` → JSON-safe
    dict.
  - `load_paper_alpha_gate_payload(payload)` → reconstructs a
    `PaperAlphaGateReport`. Tolerates missing optional fields.

### 2. Paper Alpha Gate v0 rule set

The first version judges only "does the validation sample
support continued paper observation" — it does **not** judge
whether the strategy is profitable or whether a real trade
should be placed.

Top-level decision tree:

  1. `validation_quality_gate_status = fail` → `INCONCLUSIVE`
     (the dataset is structurally untrustworthy; the brief
     allows `INCONCLUSIVE` or `FAIL`; we emit `INCONCLUSIVE`
     so a downstream auditor knows the gate refused to assert
     "no alpha"). The block-rule
     `quality_gate_status_must_not_fail` surfaces in the
     rule_results regardless.
  2. `sample_count < min_total_samples` → `INCONCLUSIVE`.
  3. `completed_tail_label_count < min_completed_tail_labels`
     → `INCONCLUSIVE`.
  4. Any cohort warning fires → `WARN`.
  5. High opportunity_score bucket clearly out-performs low
     bucket **AND** high early_tail_score bucket clearly
     out-performs low bucket **AND** no warnings → `PASS`.
  6. Only one positive signal (e.g. opportunity bucket alone,
     or cluster-leader alone) **AND** no warnings → `WARN`.
  7. Otherwise → `INCONCLUSIVE`.

Per-cohort warnings raised by the gate:

  - `follow_risk_warning` — `follow.fake_breakout_rate` is
    above the `paper_alpha_follow_fake_breakout_rate`
    threshold on a non-thin cohort.
  - `missed_alpha_warning` — `observe.strong_tail_rate` or
    `reject.strong_tail_rate` is above the
    `paper_alpha_missed_alpha_strong_tail_rate` threshold on
    a non-thin cohort.
  - `late_chase_warning` — `late.fake_breakout_rate` or
    `blowoff.fake_breakout_rate` is above the
    `paper_alpha_late_chase_fake_breakout_rate` threshold on
    a non-thin cohort.
  - `early_tail_no_alpha_advantage` — high early_tail_score
    bucket failed to beat the low bucket; the gate refuses to
    `PASS` on early-tail evidence alone (the brief
    explicitly says "if early tail high bucket has no
    advantage, the gate cannot PASS").

Per-cohort signals raised by the gate:

  - `high_score_bucket_outperforms_low_signal` — high
    opportunity_score bucket's `strong_tail_rate` /
    `p_reached_3r` / `p_reached_5r` advantage over the low
    bucket exceeds `paper_alpha_high_bucket_advantage`.
  - `high_early_tail_bucket_outperforms_low_signal` — high
    early_tail_score bucket beats the low bucket on at least
    one of `strong_tail_rate` / `p_reached_3r`.
  - `leader_preference_signal` — average leader-vs-follower
    advantage (across non-thin clusters) exceeds
    `paper_alpha_leader_preference_advantage` on either
    `strong_tail_rate` or `avg_mfe`.
  - `follow_safe_signal` — follow cohort's
    `fake_breakout_rate` is within threshold.
  - `follow_strong_tail_present_signal` — follow cohort
    produced a non-zero `strong_tail_rate`.

Default thresholds (configurable via
`StrategyValidationRuntimeConfig`):

  - `paper_alpha_min_total_samples = 20`
  - `paper_alpha_min_completed_tail_labels = 10`
  - `paper_alpha_min_bucket_samples = 5`
  - `paper_alpha_high_bucket_advantage = 0.10`
  - `paper_alpha_late_chase_fake_breakout_rate = 0.30`
  - `paper_alpha_missed_alpha_strong_tail_rate = 0.20`
  - `paper_alpha_follow_fake_breakout_rate = 0.30`
  - `paper_alpha_leader_preference_advantage = 0.10`

### 3. New event types

Four new typed events emitted through `EventRepository` with
the brief-mandated identity block (`schema_version`,
`paper_alpha_gate_version`, `source_phase`, `report_id`,
`dataset_id`, `timestamp`, `gate_status`, `strategy_version`,
`scoring_version`, `risk_config_version`,
`state_machine_version`):

  - `PAPER_ALPHA_GATE_EVALUATED`
  - `PAPER_ALPHA_RULE_EVALUATED`
  - `PAPER_ALPHA_COHORT_EVALUATED`
  - `PAPER_ALPHA_REPORT_GENERATED`

Schema version: `phase_11c_1c_c_b_b_b_a.paper_alpha_gate.v1`.

### 4. Runtime wiring

The Phase 11C.1C-C-B-B-A `StrategyValidationRuntime` is
extended:

  - `flush_report()` calls
    `_build_and_emit_paper_alpha_gate_events` after the
    dataset / quality-gate emission. The Paper Alpha Gate v0
    runs on the same flush as the dataset / quality gate so
    the four artefacts share the same `report_id` /
    `dataset_id`.
  - New runtime properties: `latest_paper_alpha_report`,
    `paper_alpha_gate_evaluated_count`,
    `paper_alpha_rule_evaluated_count`,
    `paper_alpha_cohort_evaluated_count`,
    `paper_alpha_report_generated_count`.
  - `metrics_payload()` exposes
    `paper_alpha_gate_status`, `paper_alpha_gate_reasons`,
    `paper_alpha_gate_warnings`,
    `paper_alpha_gate_sample_count`,
    `paper_alpha_strategy_mode_results`,
    `paper_alpha_candidate_stage_results`,
    `paper_alpha_score_bucket_results`,
    `paper_alpha_cluster_results`,
    `paper_alpha_missed_alpha_warnings`,
    `paper_alpha_late_chase_warnings`,
    `paper_alpha_follow_risk_warnings`,
    `paper_alpha_leader_preference_signals`, plus the four
    event counters and the full
    `paper_alpha_gate_report` payload.
  - `StrategyValidationRuntimeConfig` is extended with
    `paper_alpha_gate_enabled` (default `True`) and the eight
    `paper_alpha_*` thresholds. Setting
    `paper_alpha_gate_enabled=False` disables the new
    sub-slice without affecting the parent dataset /
    quality-gate contract.

### 5. Daily report

The Phase 11B daily report carries a new section
"Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0" with:

  - `PAPER_ALPHA_GATE_EVALUATED` count (event-log + runner
    counter cross-check).
  - `PAPER_ALPHA_RULE_EVALUATED` count.
  - `PAPER_ALPHA_COHORT_EVALUATED` count.
  - `PAPER_ALPHA_REPORT_GENERATED` count.
  - `paper_alpha_gate_status` (descriptive label only).
  - `paper_alpha_gate_sample_count`.
  - `paper_alpha_missed_alpha_warnings`.
  - `paper_alpha_late_chase_warnings`.
  - `paper_alpha_follow_risk_warnings`.
  - `paper_alpha_leader_preference_signals`.
  - `paper_alpha_gate_reasons`.
  - `paper_alpha_gate_warnings`.
  - Per-dimension cohort metric lines for `strategy_mode`,
    `candidate_stage`, `opportunity_score_bucket`,
    `early_tail_score_bucket`, `cluster_leader_vs_follower`.

The Markdown body explicitly disclaims the descriptive nature
of `paper_alpha_gate_status` and reiterates that the verdict
**MUST NEVER trigger a real trade** and **MUST NEVER** modify
position size, leverage, stop-loss, target price, the Risk
Engine, or the Execution FSM. **Phase 12 remains FORBIDDEN.**

### 6. Export / replay

The Phase 8.5 export bundle `events.jsonl` carries the four
new event types automatically (the export service streams
every row from events.db). The Phase 10A replay engine
accepts the rows without raising; legacy / future rows
missing `schema_version` are tolerated.

## What does NOT ship

  - **Real trading**. The Paper Alpha Gate v0 is paper /
    report only. No `ORDER_*` / `POSITION_*` / `STOP_*` /
    `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event is ever
    emitted by this slice.
  - **AI Learning** (Phase 12). FORBIDDEN.
  - **Automatic parameter optimisation**. FORBIDDEN.
  - **Reinforcement learning**. FORBIDDEN.
  - **Complete Strategy Validation Lab follow-up
    (Phase 11C.1C-C-B-B-B-B and beyond)**. Reserved for the
    next gate.
  - **Trade decisions driven by gate verdict**. The Risk
    Engine remains the single trade-decision gate.
    `gate_status` cannot enable / disable orders, modify
    position size, leverage, stop-loss, target price, the
    Risk Engine, or the Execution FSM.
  - **Strategy quality / profitability oracle**. The gate
    only judges "does this sample support continued paper
    observation"; profitability is out of scope.

## Real-WS smoke not required for this PR

The Phase 11C.1C-C-B-B-B-A scope is **Paper Alpha Gate v0
contract + deterministic evaluation layer**. The brief
explicitly waives the real WS smoke for this slice:

  > "本 PR 不强制要求 10min real WS smoke，原因：本 PR 是
  > Paper Alpha Gate contract + deterministic evaluation
  > layer，目标是样本不足时也能输出可审计 gate result；真实非
  > 空样本验证留到后续阶段或 closeout。"

The 30 s dry-run produces an `INCONCLUSIVE` Paper Alpha Gate
report (because the dataset is too thin / the upstream
quality gate has emitted `fail`); that is the brief's
"sample-insufficient ⇒ auditable INCONCLUSIVE" requirement.
A non-empty Paper Alpha Gate verdict is reserved for a later
closeout when the upstream dataset has accumulated enough
completed primary-window samples to make a decision.

## Safety boundary (held end-to-end)

```
mode                            = paper
live_trading_enabled            = False
exchange_live_order_enabled     = False
right_tail_enabled              = False
llm_enabled                     = False
trading_mode_paper              = True
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
no API key                      = confirmed
no signed endpoint              = confirmed
no private websocket            = confirmed
no listenKey                    = confirmed
no DeepSeek trade decision      = confirmed
no real Telegram outbound       = confirmed
Phase 12                        = FORBIDDEN
```

## Tests

  - `tests/unit/test_phase11c_1c_c_b_b_b_a_paper_alpha_gate.py`
    — 27 brief-mandated cases (input contract, status
    vocabulary, cohort dimensions, rule definition,
    INCONCLUSIVE on low samples, INCONCLUSIVE/FAIL on QG fail,
    missed_alpha / late_chase / follow_risk warnings, high
    score bucket signal, early tail bucket signal positive +
    negative, cluster leader signal, deterministic,
    `build_paper_alpha_gate_input` from upstream artefacts,
    payload roundtrip, legacy payload tolerance, non-mapping
    rejected, runtime emits the four events, export bundle
    carries them, replay accepts them, daily report metrics
    + Markdown, empty-state INCONCLUSIVE, Phase 1 safety
    flags unchanged, no execution events emitted, Phase 12
    forbidden, runtime config knob disables the gate).
  - `tests/unit/test_phase11b_no_network.py` —
    `test_phase11b_event_emission_does_not_invent_new_event_types`
    extended to allow the four new event types.
  - Full pytest run: 2340 passed (2313 baseline + 27 new). No
    regression.
  - `tests/unit/ -k phase11c_` filter: 366 passed (339
    baseline + 27 new).

## Forbidden by this PR

  - Live trading (`live_trading_enabled=False` cannot flip to
    `True`).
  - Binance private API / signed endpoint / listenKey /
    private WebSocket.
  - LLM / DeepSeek trade decision.
  - Real Telegram outbound.
  - Right-tail score in production scope (Phase 1 safety
    lock).
  - Paper Alpha Gate v0 verdict triggering real downstream
    execution.
  - Paper Alpha Gate v0 verdict modifying position size,
    leverage, stop-loss, target price, the Risk Engine, or
    the Execution FSM.
  - AI deciding direction / position size / leverage /
    stop-loss / target / execution.
  - Automatic parameter optimisation.
  - Reinforcement learning.
  - Risk Engine override (the Risk Engine remains the single
    trade-decision gate).
  - Phase 11C.1C-C-B-B-B-B implementation (reserved for the
    next child slice).
  - Phase 12 / live trading kickoff.
