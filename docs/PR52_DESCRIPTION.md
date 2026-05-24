# PR #52 — Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0 (implementation)

> **Status: IN_REVIEW.** Branch:
> `feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`. PR #51
> (the docs-only kickoff) merged into `main` on 2026-05-24
> and is the gating predecessor.
>
> **This PR is paper / report / evidence only.** **NOT** live
> trading. **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** the
> complete Strategy Validation Lab follow-up. **NOT** Phase
> 12.
>
> The Risk Engine remains the single trade-decision gate. The
> Paper Alpha Gate v0 verdict (`PASS` / `WARN` / `FAIL` /
> `INCONCLUSIVE`) is a **descriptive label** for human review
> and **MUST NEVER trigger a real trade**, **MUST NEVER**
> modify position size, leverage, stop-loss, target price,
> the Risk Engine, or the Execution FSM.

## What this PR ships

### 1. New module — `app/adaptive/paper_alpha_gate.py`

Pure-function module + frozen value-object models:

  - `PaperAlphaGateStatus` (string-constant holder; allowed:
    `PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`).
  - `PaperAlphaGateRule`, `PaperAlphaGateRuleResult`,
    `PaperAlphaGateCohortResult`,
    `PaperAlphaGateInput`, `PaperAlphaGateReport`.
  - Pure functions: `build_paper_alpha_gate_input`,
    `evaluate_paper_alpha_gate`,
    `evaluate_strategy_mode_alpha`,
    `evaluate_candidate_stage_alpha`,
    `evaluate_score_bucket_alpha`,
    `evaluate_cluster_alpha`, `build_paper_alpha_gate_report`,
    `export_paper_alpha_gate_payload`,
    `load_paper_alpha_gate_payload`.
  - Schema version:
    `phase_11c_1c_c_b_b_b_a.paper_alpha_gate.v1`.

The evaluator is **deterministic**. Identical inputs always
yield identical outputs. No I/O, no clock read, no
`EventRepository.append_event` call.

### 2. Four new `EventType` values in `app/core/events.py`

  - `PAPER_ALPHA_GATE_EVALUATED` — top-level gate decision
    + reasons + warnings.
  - `PAPER_ALPHA_RULE_EVALUATED` — one event per named rule
    (rule_id, observed_value, threshold, severity,
    triggered).
  - `PAPER_ALPHA_COHORT_EVALUATED` — one event per cohort
    dimension (`strategy_mode` / `candidate_stage` /
    `opportunity_score_bucket` / `early_tail_score_bucket` /
    `cluster_leader_vs_follower` / `tail_label_distribution`).
  - `PAPER_ALPHA_REPORT_GENERATED` — full
    `PaperAlphaGateReport` payload for replay.

Every payload carries the brief-mandated identity block:
`schema_version`, `paper_alpha_gate_version`,
`source_phase`, `report_id`, `dataset_id`, `timestamp`,
`gate_status`, `strategy_version`, `scoring_version`,
`risk_config_version`, `state_machine_version`.

### 3. `StrategyValidationRuntime` extended

  - `flush_report()` now also runs Paper Alpha Gate v0 on the
    same flush as the dataset / quality-gate emission (only
    when the dataset was built; otherwise the alpha gate is
    skipped — there is no input to evaluate).
  - New runtime properties: `latest_paper_alpha_report`,
    `paper_alpha_gate_evaluated_count`,
    `paper_alpha_rule_evaluated_count`,
    `paper_alpha_cohort_evaluated_count`,
    `paper_alpha_report_generated_count`.
  - `metrics_payload()` exposes the new
    `paper_alpha_*` fields (status, reasons, warnings, sample
    count, per-cohort results, warning / signal counts, full
    report payload).
  - `StrategyValidationRuntimeConfig` extended with
    `paper_alpha_gate_enabled` (default `True`) and 8
    `paper_alpha_*` thresholds. Setting
    `paper_alpha_gate_enabled=False` disables the new
    sub-slice without affecting the parent dataset /
    quality-gate contract.

### 4. Daily report

  - `DailyReportSnapshot` extended with
    `paper_alpha_gate_evaluated_count`,
    `paper_alpha_rule_evaluated_count`,
    `paper_alpha_cohort_evaluated_count`,
    `paper_alpha_report_generated_count`,
    `paper_alpha_gate_status`,
    `paper_alpha_gate_reasons`,
    `paper_alpha_gate_warnings`,
    `paper_alpha_gate_sample_count`,
    `paper_alpha_strategy_mode_results`,
    `paper_alpha_candidate_stage_results`,
    `paper_alpha_score_bucket_results`,
    `paper_alpha_cluster_results`,
    `paper_alpha_missed_alpha_warnings`,
    `paper_alpha_late_chase_warnings`,
    `paper_alpha_follow_risk_warnings`,
    `paper_alpha_leader_preference_signals`,
    `paper_alpha_gate_report`.
  - `DailyReportBuilder.build()` cross-checks the runner
    counters against the events.db type-counts of the four
    new event types so a stale runner counter cannot
    under-report.
  - New Markdown section "Phase 11C.1C-C-B-B-B-A Paper Alpha
    Gate v0" with explicit "the
    `paper_alpha_gate_status` is a descriptive label and
    **MUST NEVER trigger a real trade** and **MUST NEVER**
    modify position size, leverage, stop-loss, target
    price, the Risk Engine, or the Execution FSM. Phase 12
    remains FORBIDDEN" disclaimer.

### 5. Tests

  - `tests/unit/test_phase11c_1c_c_b_b_b_a_paper_alpha_gate.py`
    — 27 brief-mandated cases:
    - `test_paper_alpha_gate_input_contract`
    - `test_paper_alpha_gate_status_vocabulary_locked`
    - `test_paper_alpha_cohort_dimensions_locked`
    - `test_paper_alpha_rule_definition_round_trips`
    - `test_paper_alpha_gate_inconclusive_on_low_samples`
    - `test_paper_alpha_gate_fails_when_quality_gate_fails`
    - `test_paper_alpha_gate_warns_on_missed_alpha`
    - `test_paper_alpha_gate_warns_on_late_chase_failure`
    - `test_paper_alpha_gate_warns_on_follow_fake_breakout`
    - `test_paper_alpha_gate_detects_high_score_bucket_signal`
    - `test_paper_alpha_gate_detects_early_tail_bucket_signal`
    - `test_paper_alpha_gate_detects_cluster_leader_signal`
    - `test_evaluate_paper_alpha_gate_is_deterministic`
    - `test_build_paper_alpha_gate_input_from_dataset_and_report`
    - `test_paper_alpha_gate_payload_roundtrip`
    - `test_load_paper_alpha_gate_payload_tolerates_missing_optional_fields`
    - `test_load_paper_alpha_gate_payload_rejects_non_mapping`
    - `test_paper_alpha_gate_events_exportable`
    - `test_replay_reads_paper_alpha_gate_events`
    - `test_daily_report_contains_paper_alpha_gate_metrics`
    - `test_daily_report_renders_when_no_paper_alpha_gate`
    - `test_paper_alpha_gate_inconclusive_when_dataset_empty`
    - `test_no_live_trading_flags_unchanged`
    - `test_paper_alpha_gate_does_not_trigger_execution`
    - `test_phase_12_remains_forbidden`
    - `test_runtime_config_paper_alpha_gate_can_be_disabled`
    - `test_paper_alpha_gate_disabled_skips_paper_alpha_events`
  - `tests/unit/test_phase11b_no_network.py` allow-list
    extended with the four new event types.

### 6. Docs

  - `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md` — the
    docs-only kickoff document (PR #51) is replaced with the
    full IN_REVIEW spec (this PR ships the runtime).
  - `docs/PROJECT_STATUS.md` — Phase 11C.1C-C-B-B-B-A row
    flipped to `IN_REVIEW (PR #52 open)`.
  - `docs/PHASE_GATE.md` — Open phase entry refreshed;
    forbidden item updated to reflect implementation
    landing.
  - `docs/CHANGELOG.md` — new IN_REVIEW entry.
  - `docs/PR52_DESCRIPTION.md` — *this document*.

## Acceptance evidence

### Tests

```
$ python -m pytest tests/unit/test_phase11c_1c_c_b_b_b_a_paper_alpha_gate.py -q
27 passed

$ python -m pytest tests/unit/ -k "phase11c_" -q
366 passed (339 baseline + 27 new)

$ python -m pytest tests/ -q
2340 passed (2313 baseline + 27 new), 0 failed
```

No regression vs. post-PR-#51 main 2313 baseline.

### Dry-run smoke (30 s)

```
host                            : Kiro sandbox (dry-run; no network)
command                         : python -m scripts.run_public_market_paper \
                                    --duration 30s --symbol-limit 3 --dry-run

# Phase 11C.1C-C-B-B-B-A new section in daily report
PAPER_ALPHA_GATE_EVALUATED count    = 1
PAPER_ALPHA_RULE_EVALUATED count    = 8
PAPER_ALPHA_COHORT_EVALUATED count  = 6
PAPER_ALPHA_REPORT_GENERATED count  = 1
paper_alpha_gate_status             = INCONCLUSIVE
paper_alpha_gate_sample_count       = (low; thin dataset; expected)
paper_alpha_gate_reasons:
  - validation_quality_gate_status=fail
  - sample_count_below_min=...
  - completed_tail_label_count_below_min=...
  - paper_alpha_gate_v0_no_positive_signal

# Safety boundary (Phase 1 lock unchanged end-to-end)
mode                            = paper
exchange_live_order_enabled     = False
live_trading_enabled            = False
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
Phase 12                        = FORBIDDEN (gate unchanged)
```

`paper_alpha_gate_status=INCONCLUSIVE` is the **expected**
output for the low-sample 30 s dry-run because the upstream
Phase 11C.1C-C-B-B-A `validation_quality_gate_status=fail`
(samples are necessarily in-flight in a 30 s window). The
gate refuses to assert "no alpha" on an untrustworthy
dataset; it instead refuses to evaluate, exactly the brief's
"sample-insufficient ⇒ auditable INCONCLUSIVE" requirement.

### Real WS 10 min smoke — NOT required for this PR

The Phase 11C.1C-C-B-B-B-A scope is the Paper Alpha Gate v0
contract + deterministic evaluator. The brief explicitly
waives the real WS smoke:

> "本 PR 不强制要求 10min real WS smoke，原因：本 PR 是
> Paper Alpha Gate contract + deterministic evaluation
> layer，目标是样本不足时也能输出可审计 gate result；真实非
> 空样本验证留到后续阶段或 closeout。"

A non-empty Paper Alpha Gate verdict is reserved for a later
closeout when the upstream Phase 11C.1C-C-B-B-A dataset has
accumulated enough completed primary-window samples to drive
a non-INCONCLUSIVE decision.

## Forbidden by this PR

  - Real trading.
  - Binance private API / signed endpoint / listenKey /
    private WebSocket.
  - LLM / DeepSeek trade decision.
  - Real Telegram outbound.
  - Right-tail score in production scope.
  - `paper_alpha_gate_status` triggering real downstream
    execution.
  - `paper_alpha_gate_status` modifying position size,
    leverage, stop-loss, target price, the Risk Engine, or
    the Execution FSM.
  - AI deciding direction / position size / leverage /
    stop-loss / target / execution.
  - Automatic parameter optimisation.
  - Reinforcement learning.
  - Risk Engine override (the Risk Engine remains the single
    trade-decision gate).
  - Execution FSM override.
  - Phase 11C.1C-C-B-B-B-B implementation (reserved for the
    next child slice).
  - Complete Strategy Validation Lab follow-up.
  - Phase 12 / live trading kickoff.

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

## Remaining risk

  - The Paper Alpha Gate v0 verdict requires upstream Phase
    11C.1C-C-B-B-A samples that have **completed** their
    primary tracking window (5m). A 30 s dry-run cannot
    produce non-empty samples by construction; the verdict is
    therefore expected to be `INCONCLUSIVE` in any short
    smoke and only becomes meaningful once the operator-VPS
    runs the system long enough for primary windows to
    complete. This is recorded in
    `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md` as a known
    limitation and is a follow-up closeout concern, not a
    blocker for the contract.
  - The threshold defaults
    (`paper_alpha_high_bucket_advantage = 0.10`,
    `paper_alpha_late_chase_fake_breakout_rate = 0.30`,
    `paper_alpha_missed_alpha_strong_tail_rate = 0.20`,
    `paper_alpha_follow_fake_breakout_rate = 0.30`,
    `paper_alpha_leader_preference_advantage = 0.10`) are v0
    defaults; once non-empty samples accumulate, the
    operator may want to revisit them. Threshold tuning is
    out of scope for this PR; it will land as a future
    closeout follow-up that is itself paper-only.

## Reviewer checklist

  - [ ] `paper_alpha_gate.py` is paper / report only
        (deterministic, no I/O, no `EventRepository`
        access).
  - [ ] Risk Engine + Execution FSM are not modified.
  - [ ] No new path opens a Binance private endpoint, a
        signed call, a `listenKey`, a private WS, a real
        Telegram outbound, or a DeepSeek trade decision.
  - [ ] All four new event types attribute to the runtime
        `source_module = adaptive.strategy_validation_runtime`.
  - [ ] `paper_alpha_gate_status` cannot be `approved` /
        `trade` / `open` / `buy` / `sell` / `live` (verified
        by `test_phase_12_remains_forbidden`).
  - [ ] 27/27 brief-mandated tests PASS.
  - [ ] 366/366 phase11c tests PASS.
  - [ ] 2340/2340 full pytest PASS (no regression vs.
        post-PR-#51 main 2313 baseline).
  - [ ] Phase 1 safety lock unchanged.
  - [ ] Phase 12 remains FORBIDDEN.

## Branch & merge

  - Branch:
    `feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`.
  - Target: `main`.
  - Open PR (this document is its description).
