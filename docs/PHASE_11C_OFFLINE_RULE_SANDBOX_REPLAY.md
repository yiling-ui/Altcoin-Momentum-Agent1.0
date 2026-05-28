# Phase 11C / Offline Rule Sandbox Replay v0

> **Status:** IN_REVIEW (after this implementation PR)
> **Mode:** paper only
> **Phase 12:** FORBIDDEN
> **Trade authority:** none
> **Writes runtime config:** no
> **Auto-tuning:** disabled

---

## 1. Purpose

The Offline Rule Sandbox Replay is a strictly offline, deterministic
"what-if" layer. It lets the operator safely answer questions about
hypothetical rule changes against historical evidence, without touching
runtime config, without authorizing trades, and without progressing to
Phase 12.

Examples of questions it is designed to answer:

- If `early_tail_score` threshold were lowered, would severe miss rate fall?
- If candidate score cutoff were adjusted, would late chase rise?
- If a reject rule were relaxed, would false-negative rejects decrease?
- Does the rule change introduce more fake breakouts than it prevents
  severe misses?

The answer is always a *review-only* signal. The sandbox cannot, and is
not allowed to, apply changes anywhere.

## 2. Relation to roadmap gap #2

Roadmap gap #2 ("operator cannot safely probe rule changes against
historical evidence before paper-shadowing them") is the explicit motive
for this phase. Phase 11C closes that gap by providing:

- a typed scenario schema for hypothetical rule changes,
- a deterministic replay engine over baseline evidence,
- a conservative recommendation taxonomy,
- a JSON+Markdown report that is purely informational.

A successful sandbox run **only** unlocks preparation for the next phase
(Paper Shadow Strategy Validation). It does not unlock Phase 12, live
trading, or any auto-tuning loop.

## 3. Allowed inputs

The replay reads, but never writes, the following evidence:

| Source | Used for |
| --- | --- |
| `block_b_integrated_evidence_report.json` | discovery_quality, post_discovery_outcomes, reject_attributions, severe_miss_triage, replay_summary |
| `block_c_integrated_checkpoint_report.json` | same sections (Block C view) |
| `ai_integrated_checkpoint_report.json` | reflection_summary, discovery_quality |
| `scenario.json` | operator-supplied `OfflineRuleSandboxScenario`(s) |

If `scenario.json` is missing, the runner falls back to a
`source=example_fixture` scenario. The fixture is explicitly **not**
operator-approved; it exists only so the runner can be smoke-tested.

## 4. Allowed outputs

The runner produces exactly two files in `--output-dir`:

- `offline_rule_sandbox_report.json` — machine-readable report
- `offline_rule_sandbox_report.md` — human-readable summary

It also emits structured event records (in-memory and embedded in the
JSON report) limited to:

- `OFFLINE_RULE_SANDBOX_REPLAY_RUN`
- `OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED`
- `OFFLINE_RULE_SANDBOX_REPORT_GENERATED`

No trade-action events are defined or emitted.

## 5. Scenario schema

`OfflineRuleSandboxScenario`:

| field | type | notes |
| --- | --- | --- |
| `scenario_id` | str | unique id |
| `name` | str | human label |
| `reference_window` | str | e.g. `60d` |
| `baseline_label` | str | label of baseline evidence bundle |
| `hypothetical_rule_changes` | tuple[`HypotheticalRuleChange`] | hypothetical, not patches |
| `cohort_filters` | mapping | optional cohort scope |
| `source_reports` | tuple[str] | evidence file references |
| `evidence_refs` | tuple[str] | provenance |
| `source` | str | `operator_supplied` or `example_fixture` |
| `sandbox_only` | bool | enforced `True` |
| `writes_runtime_config` | bool | enforced `False` |
| `auto_tuning_allowed` | bool | enforced `False` |

`HypotheticalRuleChange`:

| field | type | notes |
| --- | --- | --- |
| `rule_name` | str | name of the rule under hypothesis |
| `baseline_value` | any | observed/current value |
| `sandbox_value` | any | hypothetical value |
| `change_type` | str | one of: `threshold_decrease`, `threshold_increase`, `score_cutoff_decrease`, `score_cutoff_increase`, `reject_rule_relax`, `reject_rule_tighten`, `cohort_filter_widen`, `cohort_filter_narrow`, `noop` |
| `rationale` | str | why this hypothesis is interesting |
| `evidence_refs` | tuple[str] | supporting evidence |

The dataclass deliberately rejects `rule_name` values that contain
runtime-patch tokens (`runtime_config_patch`, `threshold_patch`,
`symbol_limit_patch`, `candidate_pool_patch`, `regime_weight_patch`,
`strategy_parameter_patch`). It also serializes `is_hypothetical=true`
and `is_runtime_patch=false` so reviewers cannot mistake it for a patch.

## 6. Result schema

`OfflineRuleSandboxResult`:

| field | type | notes |
| --- | --- | --- |
| `scenario_id` | str | |
| `status` | str | `COMPLETED`, `INSUFFICIENT_EVIDENCE`, `INCONCLUSIVE`, `DATA_GAP`, or `ERROR` |
| `baseline_metrics` | mapping[str,float] | observed baseline |
| `sandbox_metrics` | mapping[str,float] | baseline + delta, clipped to `[0,1]` for rates |
| `delta_metrics` | mapping[str,float] | per-metric delta |
| `likely_benefits` | tuple[str] | direction-of-effect benefits |
| `likely_risks` | tuple[str] | direction-of-effect risks |
| `overfit_warnings` | tuple[str] | e.g. `many_simultaneous_rule_changes` |
| `data_gap_warnings` | tuple[str] | preserved from inputs and from baseline |
| `recommendation_level` | str | see §7 |

Delta keys: `coverage_rate_delta`, `usable_discovery_rate_delta`,
`severe_miss_rate_delta`, `false_negative_reject_rate_delta`,
`late_chase_rate_delta`, `fake_breakout_rate_delta`,
`data_gap_rate_delta`, `median_mfe_delta`, `median_mae_delta`.

`OfflineRuleSandboxReport` adds:

- `report_id`
- `generated_at_utc`
- `reference_window`
- `scenarios`, `scenario_results`
- `best_review_candidates` (PROMISING_FOR_PAPER_SHADOW only)
- `rejected_scenarios` (REJECTED_BY_EVIDENCE only)
- `known_gaps`
- `next_allowed_phase` (= `Paper Shadow Strategy Validation preparation`)
- `phase_12_forbidden=true`
- `auto_tuning_allowed=false`
- `writes_runtime_config=false`
- `trade_authority=false`
- `sandbox_only=true`

## 7. Recommendation levels

The engine may emit **only** one of these levels. Every other label
(including `APPLY`, `DEPLOY`, `ENABLE_LIVE`, `TRADE`, `BUY`, `SELL`,
`GO_LIVE`, `AUTO_APPLY`) is rejected at construction time:

| Level | Meaning |
| --- | --- |
| `REVIEW_ONLY` | default; signal weak or balanced; needs operator review |
| `INCONCLUSIVE` | not enough evidence or too many data gaps |
| `PROMISING_FOR_PAPER_SHADOW` | benefits clearly outweigh risks AND no severe overfit warning; operator MAY consider scheduling a Paper Shadow run |
| `RISKY` | risks at least as large as benefits; do not advance |
| `REJECTED_BY_EVIDENCE` | risks dominate clearly |

`PROMISING_FOR_PAPER_SHADOW` does **not** authorize a paper shadow run
on its own — it only marks the scenario as a candidate for the *next*
phase's preparation work. The Paper Shadow Strategy Validation phase
itself is not part of Phase 11C.

## 8. Why this is not auto-tuning

- The engine never selects rule values; it only scores values supplied
  by the operator in a scenario file (or the example fixture).
- The engine never iterates, never optimizes, never gradient-descends.
- The mapping from rule change to delta metrics is a fixed, auditable
  sensitivity table (see `_BASE_VECTORS` in
  `app/sandbox/offline_rule_sandbox.py`).
- `OfflineRuleSandboxEngine.auto_tuning_allowed` is `False` and the
  scenario constructor refuses to set it `True`.
- `SAFETY_CONTRACT["auto_tuning_allowed"] is False`.

## 9. Why this does not write runtime config

- No file in `app/config/**` is read or written.
- The engine and runner do not import `app.config`.
- `HypotheticalRuleChange` is named, structured, and serialized so
  that it cannot be confused with a `runtime_config_patch` /
  `threshold_patch` / `symbol_limit_patch` /
  `candidate_pool_patch` / `regime_weight_patch` /
  `strategy_parameter_patch`. Each of those names is a forbidden
  output field name and triggers a `ValueError` if it ever appears.
- The output JSON+MD live under `data/reports/rule_sandbox/`, never
  alongside runtime config.

## 10. Why this does not authorize live trading

- `mode=paper`, `live_trading=False`, `exchange_live_orders=False`.
- The engine and runner do not import `app.risk`, `app.execution`,
  `app.exchanges`, or `app.telegram`.
- The forbidden output-field set blocks any payload that contains
  `buy`, `sell`, `long`, `short`, `direction`, `entry`, `exit`,
  `position_size`, `leverage`, `stop`, `stop_loss`, `target`,
  `take_profit`, `risk_budget`, `order`, `execution_command`,
  `signal_to_trade`, `should_buy`, `should_short`, `apply_change`,
  `deploy_change`, or `enable_live`.
- `OfflineRuleSandboxReport.trade_authority` is `False`.

## 11. Why this does not enter Phase 12

- `phase_12_forbidden=True` is emitted in every report.
- `next_allowed_phase` is hard-coded to
  `Paper Shadow Strategy Validation preparation`.
- The engine has no knowledge of Phase 12 mechanics and no path to
  unlock them. The phase gate (see `docs/PHASE_GATE.md`) explicitly
  records the gate as CLOSED.

## 12. Successful sandbox -> only Paper Shadow preparation

A scenario that lands at `PROMISING_FOR_PAPER_SHADOW` does **not** mean
the rule should be applied. It means the operator may begin the
preparation checklist for **Paper Shadow Strategy Validation**, which is
a separate phase and is out of scope for this PR.

## 13. Test command

```
python -m pytest tests/unit/test_offline_rule_sandbox_replay.py -q
```

## 14. Hard "do not" list (Phase 11C)

- Do not modify `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
  `app/telegram/**`, or `app/config/**`.
- Do not generate `runtime_config_patch`, `threshold_patch`,
  `symbol_limit_patch`, `candidate_pool_patch`, `regime_weight_patch`,
  or `strategy_parameter_patch`.
- Do not emit `buy`, `sell`, `long`, `short`, `direction`, `entry`,
  `exit`, `position_size`, `leverage`, `stop`, `stop_loss`, `target`,
  `take_profit`, `risk_budget`, `order`, or `execution_command`.
- Do not call DeepSeek / LLM / network endpoints.
- Do not send Telegram messages.
- Do not touch the Binance private API.
- Do not auto-tune.
- Do not enter Phase 12.
