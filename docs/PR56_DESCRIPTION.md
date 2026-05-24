# PR #56 — Phase 11C.1C-C-B-B-B-B implementation: Regime & Cluster Cohort Evidence Pack v0

> **Type:** Implementation PR (paper / report / evidence-only).
> **Phase:** Phase 11C.1C-C-B-B-B-B — Regime & Cluster Cohort
> Evidence Pack v0 / *Regime 与 Cluster 分组证据包 v0*
> (the **second child slice** under the Phase 11C.1C-C-B-B-B
> parent). The parent phase is **not** renamed; its definition
> is unchanged.
> **Status after merge:** Phase 11C.1C-C-B-B-B-B remains
> `NEXT_ALLOWED / NOT_STARTED` until the operator-VPS paper
> smoke + closeout PR records the acceptance evidence.
> Phase 11C.1C-C-B-B-B-A remains `ACCEPTED`. Phase
> 11C.1C-C-B-B-B remains `NEXT_ALLOWED / NOT_STARTED`. Phase 12
> remains **FORBIDDEN**.
>
> This PR is paper / report / evidence only. **NOT** live
> trading. **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a new
> strategy. **NOT** a trading module. **NOT** the complete
> Strategy Validation Lab follow-up. **NOT** Phase 12.
>
> Every artefact this PR introduces (`regime_cohort_summary`,
> `cluster_cohort_summary`, `score_bucket_summary`,
> `stage_outcome_summary`, `strategy_mode_outcome_summary`,
> `regime_cluster_evidence_pack`, `warnings`,
> `insufficient_sample_reasons`, the per-cohort
> `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` /
> `EVIDENCE_SIGNAL` status, the two new event types) is a
> **descriptive label** for human review. Outputs **MUST NEVER**
> trigger a real trade or modify position size, leverage,
> stop-loss, target price, the Risk Engine, or the Execution
> FSM. The Risk Engine remains the single trade-decision gate.

## Why this slice exists (positioning under AMOS)

This PR is the substantive implementation of the
[Phase 11C.1C-C-B-B-B-B kickoff (PR #55)](./PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md)
docs-only scope. AMOS treats AMA-RT as an *Adaptive Market
Operating System*: long-term stable operation, adapting to
market change, and being capable of capturing 5x+ right-tail
upside *when it is genuinely available* — **not** promising
returns, **not** running an auto-strategy bot, and **not**
letting AI drive execution.

Under that frame, the project's main line must converge on:

  - Add fewer modules; accumulate more structural data.
  - Talk less about "strategy"; verify Regime more.
  - Stop chasing a universal model; prove which states
    really carry right-tail value.
  - Evidence first, runtime change later.

This PR ships exactly that step. Instead of adding a new
strategy or a new execution surface, it compresses the
paper-only data already produced by the upstream slices
(Phase 11C.1C-C-A label-tracking outcomes, Phase 11C.1C-C-B-A
validation samples / cluster exposure assessments, Phase
11C.1C-C-B-B-A validation dataset / quality gate, Phase
11C.1C-C-B-B-B-A Paper Alpha Gate v0 verdict) into a
**structured cohort evidence pack** organised by Regime,
Cluster, Stage, Strategy Mode, and Score Bucket — so that
the questions "which states carry right-tail value, and
which states must be down-weighted or rejected" become
answerable with data, not opinion.

## What this PR adds

### New module — `app/adaptive/regime_cluster_evidence_pack.py`

Phase 11C.1C-C-B-B-B-B value objects + pure functions:

| Symbol | Purpose |
| ------ | ------- |
| `RegimeClusterEvidencePackStatus` | Allowed status labels (`INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` / `EVIDENCE_SIGNAL`). |
| `RegimeClusterCohortKey` | `(dimension, value)` identity for one cohort row. |
| `RegimeClusterCohortStats` | Shared per-cohort numerics (sample counts, tail-label counts, MFE / MAE medians, derived rates, status, signals, warnings, notes). |
| `RegimeClusterEvidenceRecord` | Normalised per-sample row consumed by the cohort builders. |
| `RegimeClusterEvidenceInput` | Everything the pack builder consumes (records + provenance + version block). |
| `RegimeCohortSummary` | Per-`market_regime` cohort summary. |
| `ClusterCohortSummary` | Per-`cluster_id` cohort summary + leader-vs-follower breakdown. |
| `ScoreBucketSummary` | Per-`opportunity_score_bucket` and per-`early_tail_score_bucket` cohort summary. |
| `StageOutcomeSummary` | Per-`candidate_stage` cohort summary. |
| `StrategyModeOutcomeSummary` | Per-`strategy_mode` cohort summary. |
| `RegimeClusterEvidencePack` | Top-level container that bundles every summary + the upstream Paper Alpha Gate verdict + warnings + insufficient-sample reasons. |

Pure functions:

  - `build_regime_cluster_evidence_input(...)` — assembles
    a `RegimeClusterEvidenceInput` from a
    `StrategyValidationDataset` (and an optional
    `regime_by_opportunity` mapping the runtime supplies).
    Records whose regime is missing safely degrade to
    `unknown`.
  - `build_regime_cohort_summary(...)`
  - `build_cluster_cohort_summary(...)`
  - `build_score_bucket_summary(...)`
  - `build_stage_outcome_summary(...)`
  - `build_strategy_mode_outcome_summary(...)`
  - `build_regime_cluster_evidence_pack(...)` — top-level
    builder; emits `INSUFFICIENT_SAMPLE` whenever the total
    or completed-tail-label pool falls below the configured
    minimums; aggregates per-cohort warnings and signals.
  - `export_regime_cluster_evidence_payload(...)` /
    `load_regime_cluster_evidence_payload(...)` — JSON-safe
    round-trip helpers; tolerate payloads from old
    `schema_version`s.

Every payload carries
`schema_version =
phase_11c_1c_c_b_b_b_b.regime_cluster_evidence_pack.v1` plus
the four canonical version labels
(`strategy_version` / `scoring_version` /
`risk_config_version` / `state_machine_version`).

All functions are deterministic / pure: no I/O, no clock
read, no event emission, no network access, no API key
read, no exchange call, no Risk Engine / Execution FSM
mutation.

### Two new typed events — `app/core/events.py`

  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` — full pack
    payload so a downstream auditor can replay the report
    from one event-log row.
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED` — one event
    per named cohort summary
    (`regime_cohort_summary` / `cluster_cohort_summary` /
    `score_bucket_summary` / `stage_outcome_summary` /
    `strategy_mode_outcome_summary`); the payload's
    `summary_name` field disambiguates.

Both events carry `report_id`, `dataset_id`, `timestamp`,
`evidence_pack_status` (descriptive only),
`schema_version`, `regime_cluster_evidence_version`,
`source_phase`, and the four canonical version labels.

Neither event is consumed by the Risk Engine or the
Execution FSM. The export pipeline picks them up
automatically since it streams every event from `events.db`.

### Runtime integration — `app/adaptive/strategy_validation_runtime.py`

  - `StrategyValidationRuntimeConfig` extended with twelve
    Phase 11C.1C-C-B-B-B-B knobs
    (`regime_cluster_evidence_pack_enabled`,
    `regime_cluster_min_total_samples`,
    `regime_cluster_min_completed_tail_labels`,
    `regime_cluster_min_cohort_samples`,
    `regime_cluster_strong_tail_signal_rate`,
    `regime_cluster_reached_3r_signal_rate`,
    `regime_cluster_reached_5r_signal_rate`,
    `regime_cluster_fake_breakout_warning_rate`,
    `regime_cluster_missed_tail_warning_rate`,
    `regime_cluster_late_chase_failure_warning_rate`,
    `regime_cluster_leader_preference_advantage`,
    `regime_cluster_high_bucket_advantage`).
    Defaults match the module-level defaults so the runner
    does not need to opt in explicitly.
  - `observe_market_regime(opportunity_id, market_regime)`
    helper attaches the regime per opportunity. Called by
    `WSRadarChainDriver._post_chain` after every adaptive
    context is built. Records whose regime was not
    observed safely degrade to `unknown` per the brief.
  - `_build_and_emit_regime_cluster_evidence_events(...)`
    builds the pack from the cached
    `StrategyValidationDataset` /
    `StrategyValidationQualityGateResult` /
    `PaperAlphaGateReport` artefacts after every
    flush_report, emits both event types, and caches the
    pack on the runtime for the daily-report builder.
  - `metrics_payload()` extended with the
    Phase 11C.1C-C-B-B-B-B aggregates.

### WS-radar wiring — `app/market_data_public/ws_radar_chain.py`

`WSRadarChainDriver._post_chain` calls
`strategy_validation_runtime.observe_market_regime` after
every adaptive context is built so the pack can group on
`market_regime` without re-querying `events.db`. The driver
does NOT trigger any real trade as a result of this change.

### Daily report — `app/paper_run/daily_report.py`

`DailyReportSnapshot` extended with fourteen new fields:

  - `regime_cluster_evidence_pack_generated_count`
  - `regime_cluster_cohort_summary_generated_count`
  - `regime_cluster_evidence_status`
  - `regime_cluster_sample_count`
  - `regime_cluster_completed_tail_label_count`
  - `regime_cluster_insufficient_sample_reasons`
  - `regime_cluster_warnings`
  - `regime_cluster_signals`
  - `regime_cohort_summary`
  - `cluster_cohort_summary`
  - `score_bucket_summary`
  - `stage_outcome_summary`
  - `strategy_mode_outcome_summary`
  - `regime_cluster_evidence_pack`

`to_payload()` carries every new field. The Markdown body
renders a new *Phase 11C.1C-C-B-B-B-B Regime & Cluster
Cohort Evidence Pack v0* section with the boundary banner
("paper / report / evidence-only", "MUST NEVER trigger a
real trade", "Phase 12 remains FORBIDDEN") and per-cohort
row rendering across the seven cohort dimensions.

### Tests — `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`

23 brief-mandated tests covering:

  - `test_regime_cluster_evidence_input_contract`
  - `test_regime_cluster_evidence_pack_status_vocabulary_locked`
  - `test_regime_cluster_cohort_dimensions_locked`
  - `test_regime_cluster_evidence_insufficient_on_low_samples`
  - `test_regime_cluster_evidence_insufficient_on_low_completed_tail_labels`
  - `test_regime_cohort_summary_counts_tail_outcomes`
  - `test_cluster_leader_vs_follower_summary`
  - `test_score_bucket_summary_detects_high_bucket_signal`
  - `test_stage_outcome_summary_detects_missed_tail_warning`
  - `test_strategy_mode_summary_detects_fake_breakout_warning`
  - `test_build_regime_cluster_evidence_pack_from_dataset`
  - `test_regime_cluster_payload_roundtrip`
  - `test_load_regime_cluster_evidence_payload_rejects_non_mapping`
  - `test_regime_cluster_events_exportable`
  - `test_replay_reads_regime_cluster_events`
  - `test_daily_report_contains_regime_cluster_section`
  - `test_daily_report_renders_when_no_evidence_pack`
  - `test_regime_cluster_evidence_pack_insufficient_when_dataset_empty`
  - `test_no_live_trading_flags_unchanged`
  - `test_regime_cluster_evidence_does_not_trigger_execution`
  - `test_phase_12_remains_forbidden`
  - `test_runtime_config_regime_cluster_evidence_pack_can_be_disabled`
  - `test_regime_cluster_disabled_skips_evidence_events`

`tests/unit/test_phase11b_no_network.py` — the
`allowed_phase_11b_references` allowlist was extended with
the two new EventType labels (mirrors how PAPER_ALPHA_*
were added by PR #52).

## Verification

```
tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py
  -> 23/23 PASS

tests/unit -k phase11c_
  -> 389/389 PASS (366 baseline + 23 new)

tests/  (full surface)
  -> 2363/2363 PASS (no regression vs. post-PR-#55 main)

30 s dry-run smoke
  -> Daily report contains the new
     "## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
     Evidence Pack v0" section.
  -> regime_cluster_evidence_status=INSUFFICIENT_SAMPLE
     (expected for a 30 s window — Phase 11C.1C-C-A primary
     tracking window is 5 minutes and cannot complete in
     30 s; this is exactly the brief's
     "do not loosen rules on low samples" requirement).
  -> regime_cluster_insufficient_sample_reasons populated
     with explicit reasons.
  -> No ORDER_* / POSITION_* / STOP_* /
     TELEGRAM_MESSAGE_SENT / EXIT_TRIGGERED events emitted.

Real-WS 10 min smoke
  -> NOT REQUIRED for this PR. This PR is a deterministic
     evidence-compression layer over the upstream Phase
     11C.1C-C-A label-tracking outcomes; non-empty cohort
     rows depend on the upstream primary tracking window
     resolving. Real non-empty cohort validation is
     reserved for the Phase 11C.1C-C-B-B-B-B closeout /
     operator-VPS run.
```

## Safety boundary held throughout

| Invariant                                   | Required value           | After PR |
| ------------------------------------------- | ------------------------ | -------- |
| `mode`                                      | `paper`                  | `paper`  |
| `live_trading`                              | `False`                  | `False`  |
| `right_tail`                                | `False`                  | `False`  |
| `llm`                                       | `False`                  | `False`  |
| `exchange_live_orders`                      | `False`                  | `False`  |
| `telegram_outbound_enabled`                 | `False`                  | `False`  |
| `binance_private_api_enabled`               | `False`                  | `False`  |
| `safety.forbid_*` (11 flags)                | `True` for every flag    | unchanged |
| Binance API key / secret                    | not loaded               | not loaded |
| Signed endpoint                             | none                     | none |
| `listenKey` / user data WS                  | none                     | none |
| Private WebSocket / trading WS API          | none                     | none |
| Routed-private endpoint (`/private`)        | refused                  | refused |
| DeepSeek trade-decision authority           | NOT permitted            | NOT permitted |
| Real Telegram outbound                      | NOT permitted            | NOT permitted |
| Risk Engine authority                       | unchanged                | unchanged |
| Execution FSM authority                     | unchanged                | unchanged |
| `regime_cluster_evidence_status`            | descriptive only         | descriptive only |
| Phase 12                                    | FORBIDDEN                | FORBIDDEN |

No `ORDER_*` / `POSITION_*` / `STOP_*` /
`TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` event is emitted
by the new pipeline.

## Forbidden by this PR (carries forward verbatim)

  - Real trading.
  - Live trading.
  - Binance API key / secret.
  - Signed endpoint / `listenKey` / private WebSocket.
  - Account / order / position / leverage / margin
    endpoint.
  - DeepSeek trade decision.
  - Real Telegram outbound.
  - AI deciding direction / position size / leverage / stop
    / target / execution.
  - Automatic parameter optimisation.
  - Auto-relaxing rules on low samples.
  - Promoting any evidence-pack output (status / signals /
    warnings / cohort rows / `regime_cluster_evidence_pack`)
    to a real-trade authority.
  - Modifying position size / leverage / stop-loss / target
    price / Risk Engine / Execution FSM.
  - Replacing the Paper Alpha Gate v0 verdict with the
    evidence-pack output.
  - Phase 11C.1C-C-B-B-B-C kickoff or any later phase.
  - Phase 12 / live trading.

## Remaining risk / known limitations

  - The 30 s dry-run dataset is structurally too thin to
    surface meaningful cohort rates, so the pack correctly
    emits `INSUFFICIENT_SAMPLE`. Real non-empty cohort rows
    require the upstream Phase 11C.1C-C-A primary tracking
    window (5 minutes) to resolve, which only happens on
    the operator-VPS smoke. This is the expected acceptance
    path; **the closeout PR will record the operator-VPS
    paper smoke evidence**.
  - `market_regime` is observed via
    `WSRadarChainDriver._post_chain`. Records whose regime
    was not observed safely degrade to `unknown` per the
    brief. A future PR may extend the dataset record itself
    to carry `market_regime` directly; v0 keeps the
    field-augmentation strategy out of the dataset to avoid
    bumping the Phase 11C.1C-C-B-B-A schema.
  - The pack is deterministic / pure. It does NOT drive any
    runtime decision; the per-cohort `status` is a
    descriptive label only. The operator-VPS closeout PR
    must explicitly confirm that no real-trade authority
    was inferred from the pack.

## Whether this PR is ready for human review

**Yes.** Every test in the brief-mandated test file passes
(23/23). The full Phase 11C suite passes (389/389). The
full pytest surface passes (2363/2363) with no regression
vs. the post-PR-#55 main baseline. The 30 s dry-run smoke
correctly emits an `INSUFFICIENT_SAMPLE` evidence pack and
the daily-report renders the new section. Phase 1 safety
flags held throughout. Phase 12 remains `FORBIDDEN`. The
operator-VPS paper smoke + closeout PR is required before
the slice flips to `ACCEPTED`; that is **not** in scope for
this PR.
