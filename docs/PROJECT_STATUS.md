# AMA-RT Project Status

This document is the at-a-glance status board for AMA-RT V1.4. It is
intentionally short. The full phase-gate ledger lives in
`docs/PHASE_GATE.md`; per-phase deep dives live in their own
`PHASE_*` documents.

## Current phase

> **Phase 11C.1C-C-B-B-B-C = ACCEPTED (closed 2026-05-25;
> PR #58 docs-only kickoff merged into `main` on
> 2026-05-25; this docs-only closeout PR #59 records the
> operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h
> upper-bound early-stop paper WS evidence and flips the
> slice to `ACCEPTED`).** Long-Window Cohort Stability &
> Sample Sufficiency Protocol v0 / *长窗口 Cohort 稳定性
> 与样本充足协议 v0* — third child slice under the Phase
> 11C.1C-C-B-B-B parent — paper / report / evidence only.
> **NOT** live trading, **NOT** AI Learning, **NOT**
> automatic parameter optimisation, **NOT** reinforcement
> learning, **NOT** rule relaxation based on low samples,
> **NOT** a Risk Engine change, **NOT** an Execution FSM
> change, **NOT** a strategy implementation, **NOT** a
> trading module, **NOT** a new runtime module, **NOT**
> the complete Strategy Validation Lab follow-up, **NOT**
> Phase 12. **B-B-B-C acceptance is acceptance of the
> long-window data collection and sample-sufficiency
> protocol — it does NOT mean any Regime / Cluster has
> proven right-tail advantage yet, and it does NOT mean
> strategy effectiveness is proven.** The long-window
> protocol artefacts (`long_window_run_plan`,
> `sample_sufficiency_checklist`,
> `cohort_stability_checklist`,
> `operator_vps_evidence_template`,
> `export_replay_evidence_template`,
> `closeout_acceptance_template`) and the per-window
> outputs (`paper_alpha_gate_status`,
> `regime_cluster_evidence_status`,
> `insufficient_sample_reasons`, daily-report Paper Alpha
> Gate section, daily-report Regime & Cluster Cohort
> Evidence Pack section, `PAPER_ALPHA_*` and
> `REGIME_CLUSTER_*` event counts, Phase 8.5 export
> bundles) produced by this slice are **descriptive
> labels / artefacts only** for human review and **MUST
> NEVER trigger a real trade**, **MUST NEVER** modify
> position size, leverage, stop-loss, target price, the
> Risk Engine, or the Execution FSM; the Risk Engine
> remains the single trade-decision gate.
>
> **Phase 11C.1C-C-B-B-B-B = ACCEPTED (closed 2026-05-24; PR
> #56 merged into `main`, mergeCommit `1a9abe2`; operator-VPS
> 10 min WS paper smoke evidence + Regime & Cluster Cohort
> Evidence Pack daily report + two `REGIME_CLUSTER_*` event
> counts + Phase 8.5 export bundle accepted via this docs-only
> closeout PR #57).** Regime & Cluster Cohort Evidence Pack v0
> / *Regime 与 Cluster 分组证据包 v0* — second child slice
> under the Phase 11C.1C-C-B-B-B parent — paper / report /
> evidence only. **NOT** live trading, **NOT** AI Learning,
> **NOT** automatic parameter optimisation, **NOT**
> reinforcement learning, **NOT** the complete Strategy
> Validation Lab follow-up, **NOT** Phase 12. The per-cohort
> `status` (`INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING`
> / `EVIDENCE_SIGNAL`) and the top-level
> `regime_cluster_evidence_status` produced by this slice are
> **descriptive labels** for human review and **MUST NEVER
> trigger a real trade**, **MUST NEVER** modify position size,
> leverage, stop-loss, target price, the Risk Engine, or the
> Execution FSM; the Risk Engine remains the single
> trade-decision gate.
>
> **Phase 11C.1C-C-B-B-B-A = ACCEPTED (closed 2026-05-24; PR
> #52 merged into `main`, mergeCommit `f8ba315`; operator-VPS
> 10 min WS paper smoke evidence + Paper Alpha Gate daily
> report + four `PAPER_ALPHA_*` event counts + Phase 8.5
> export bundle accepted via docs-only closeout PR #54).**
> Paper Alpha Gate v0 — first child slice under the Phase
> 11C.1C-C-B-B-B parent — paper / report / evidence only.
> **NOT** live trading, **NOT** AI Learning, **NOT** automatic
> parameter optimisation, **NOT** reinforcement learning,
> **NOT** the complete Strategy Validation Lab follow-up,
> **NOT** Phase 12. The `paper_alpha_gate_status` produced by
> this slice (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) is a
> **descriptive label** for human review and **MUST NEVER
> trigger a real trade**, **MUST NEVER** modify position size,
> leverage, stop-loss, target price, the Risk Engine, or the
> Execution FSM; the Risk Engine remains the single
> trade-decision gate.
>
> **Phase 11C.1C-C-B-B-A = ACCEPTED (closed 2026-05-23; PR #44
> merged into `main`, mergeCommit `3ecfc3b`).** Strategy
> Validation Dataset Builder & Quality Gate v0 on top of the
> Phase 11C.1C-C-B-A `StrategyValidationSample` /
> `StrategyValidationReport` / `ClusterExposureAssessment`
> artefacts. Paper / report only. **NOT** live trading, **NOT**
> AI Learning, **NOT** the complete Strategy Validation Lab
> follow-up (Phase 11C.1C-C-B-B-B), **NOT** automatic parameter
> optimisation, **NOT** Phase 12. The
> ``validation_quality_gate_status`` produced by this slice
> (``pass`` / ``warn`` / ``fail``) is a **descriptive label**
> for human review and **MUST NEVER trigger a real trade**; the
> Risk Engine remains the single trade-decision gate.
>
> Phase 11C.1C-C-B-A — *Strategy Validation Lab v0 & Cluster
> Exposure Control Contracts* — was accepted on 2026-05-23
> (PR #42 merged into `main`, mergeCommit `cc18047`) and is the
> gating predecessor. PR #44 shipped the **first slice** of the
> deeper Phase 11C.1C-C-B-B work: dataset contract + builder +
> quality gate v0 + three new typed events
> (`STRATEGY_VALIDATION_DATASET_BUILT`,
> `STRATEGY_VALIDATION_DATASET_EXPORTED`,
> `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`). The dataset is
> exportable + replayable + auditable. Real WS 10 min smoke was
> NOT required for this PR (the smallest Phase 11C.1C-C-A
> tracking window is 5 min and cannot complete in a 30 s
> dry-run); reserved for Phase 11C.1C-C-B-B-B closeout when
> non-empty datasets are first observable end-to-end.
> `validation_quality_gate_status=fail` is the **expected**
> output for the 30 s dry-run because samples are necessarily
> in-flight in a low-sample window; the field is descriptive
> only and cannot trigger real trading.
>
> **Phase 11C.1C-C-B-B-A = ACCEPTED (closed 2026-05-23; PR #44 merged into `main`, mergeCommit `3ecfc3b`).**
> **Phase 11C.1C-C-B-B-B = NEXT_ALLOWED / NOT_STARTED (parent; unchanged definition — *Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up*; will require its own kickoff PRs (one per child slice), brief, scope, boundary table, forbidden list, and acceptance evidence).**
> **Phase 11C.1C-C-B-B-B-A = ACCEPTED (closed 2026-05-24; PR #52 merged into `main` on 2026-05-24, mergeCommit `f8ba315`; operator-VPS 10 min WS paper smoke evidence + Paper Alpha Gate daily report + four `PAPER_ALPHA_*` event counts + Phase 8.5 export bundle accepted via docs-only closeout PR #54; first child slice under Phase 11C.1C-C-B-B-B — *Paper Alpha Gate v0*; verdict `INCONCLUSIVE` with `paper_alpha_gate_sample_count=20`, `completed_tail_label_count_below_min=0<10`, expected and accepted as a low-completed-label result).**
> **Phase 11C.1C-C-B-B-B-B = ACCEPTED (closed 2026-05-24; PR #56 merged into `main` on 2026-05-24, mergeCommit `1a9abe2`; operator-VPS 10 min WS paper smoke evidence + Regime & Cluster Cohort Evidence Pack daily report + two `REGIME_CLUSTER_*` event counts + Phase 8.5 export bundle accepted via this docs-only closeout PR #57; second child slice under Phase 11C.1C-C-B-B-B — *Regime & Cluster Cohort Evidence Pack v0 / Regime 与 Cluster 分组证据包 v0*; status `INSUFFICIENT_SAMPLE` with `sample_count=14<20` and `completed_tail_label_count=0<10`, expected and accepted as a low-sample / low-completed-tail-label result; the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient. Paper / report / evidence-only — allowed outputs `regime_cohort_summary` / `cluster_cohort_summary` / `score_bucket_summary` / `stage_outcome_summary` / `strategy_mode_outcome_summary` / `regime_cluster_evidence_pack` / `warnings` / `insufficient_sample_reasons` are descriptive labels only, MUST NEVER trigger a real trade, and grant no trade authority. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item verbatim.**
> **Phase 11C.1C-C-B-B-B-C = ACCEPTED (closed 2026-05-25; PR #58 docs-only kickoff merged into `main`; this docs-only closeout PR #59 records the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence and flips the slice to `ACCEPTED`; third child slice under Phase 11C.1C-C-B-B-B — *Long-Window Cohort Stability & Sample Sufficiency Protocol v0 / 长窗口 Cohort 稳定性与样本充足协议 v0*; W1 / W1+ 2 h paper WS run PASSED with `duration_seconds=7200.0`, `uptime≈7238s`, 2 h event counts `PAPER_ALPHA_*` 18/3/3/27 + `REGIME_CLUSTER_*` 10/2, daily report `regime_cluster_sample_count=189`, `completed_tail_label_count=0`, status `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` accepted as valid low-completed-label evidence (not runtime failure), 2 h export `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip` `manifest_event_count=23001` `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`; W2 4 h paper WS run PASSED with configured `duration_seconds=14400.0` actual runtime ≈ `14417s`, `iterations=237`, `chains_emitted=704`, `ws_messages_received=1324423`, `radar_candidates_seen=152221`, `liquidation_events_seen=4076`, 4 h event counts `PAPER_ALPHA_*` 24/4/4/36 + `REGIME_CLUSTER_*` 15/3, `paper_alpha_gate_status=INCONCLUSIVE` `sample_count=164` reason `completed_tail_label_count_below_min=2<10`, `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` `completed_tail_label_count=2` (progress from 0 to 2 completed labels still below 10-label threshold — `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct result, does NOT indicate runtime failure, does NOT authorise rule relaxation), 4 h export `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip` `manifest_event_count=61546` `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`; W3 24 h upper-bound run PASSED with watcher early-stop at `total_elapsed_seconds=900`, `final_tail_labels_since_start=20>=10`, `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`, 24 h full runtime NOT NEEDED — proves the B-B-B-C sample sufficiency protocol can save runtime while preserving evidence; W3 export PASSED with latest export zip after W3 early-stop `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip` generated 2026-05-25 12:41 UTC `manifest_event_count=62761` `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3 export-range event counts `TAIL_LABEL_ASSIGNED=495`, `LABEL_WINDOW_COMPLETED=495`, `STRATEGY_VALIDATION_SAMPLE_CREATED=397`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`, `PAPER_ALPHA_GATE_EVALUATED=5`, `PAPER_ALPHA_RULE_EVALUATED=45`, `PAPER_ALPHA_COHORT_EVALUATED=30`, `PAPER_ALPHA_REPORT_GENERATED=5` (clarification: `final_tail_labels_since_start=20` is the watcher early-stop condition for the 900 s live window; `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range event count — both valid, different scopes); B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol, does NOT mean any Regime / Cluster has proven right-tail advantage yet, does NOT authorise live trading, does NOT authorise rule relaxation, does NOT authorise automatic parameter optimisation, does NOT authorise AI Learning, does NOT authorise changing the Risk Engine or the Execution FSM, does NOT authorise Phase 12. Paper / report / evidence-only; grants no trade authority. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim).**
> **Phase 11C.1C-C-B-B-B-D = NEXT_ALLOWED / NOT_STARTED — next child slice under Phase 11C.1C-C-B-B-B (placeholder; not yet defined by name or scope). Phase 11C.1C-C-B-B-B-C acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard gate; Phase 11C.1C-C-B-B-B-D will require its own kickoff PR, brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C forbidden item verbatim. Paper / report / evidence-only; grants no trade authority.**
> **Phase 11C.1C-C-B-A = ACCEPTED (closed 2026-05-23; PR #42 merged into `main`, mergeCommit `cc18047`).**
> **Phase 11C.1C-C-A = ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`).**
> **Phase 11C.1C-B = ACCEPTED (closed 2026-05-22; PR #38 merged into `main`).**
> **Phase 11C.1C-A = ACCEPTED (closed 2026-05-22; PR #36 merged via PR #37 docs closeout).**
> **Phase 11C.1B = ACCEPTED (closed 2026-05-22).**
> **Phase 12 (real money / live trading) = FORBIDDEN.**
> **We are still in paper mode.**
>
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-A does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-A does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-A does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-A does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-A does NOT authorise Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-A does NOT authorise Phase 12.**
> **`validation_quality_gate_status` cannot trigger real trading.**
> **The Risk Engine remains the single trade-decision gate.**
>
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise Phase 12.**
> **Paper Alpha Gate verdicts remain paper-only / report-only / evidence-only.**
> **Paper Alpha Gate verdicts cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **`paper_alpha_gate_status=INCONCLUSIVE` is an expected and accepted result for this smoke window because `completed_tail_label_count=0<10`.** This means the Paper Alpha Gate correctly refused to overfit or force a `PASS` when completed tail labels were insufficient. **`INCONCLUSIVE` does NOT mean runtime failure. `INCONCLUSIVE` does NOT authorise strategy changes. `INCONCLUSIVE` does NOT authorise live trading. `INCONCLUSIVE` does NOT authorise Phase 12.**
>
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 12.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only.**
> **Regime & Cluster Evidence Pack outputs cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` is an expected and accepted result for this smoke window because `sample_count=14<20` and `completed_tail_label_count=0<10`.** This means the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient. **`INSUFFICIENT_SAMPLE` does NOT mean runtime failure. `INSUFFICIENT_SAMPLE` does NOT authorise strategy changes. `INSUFFICIENT_SAMPLE` does NOT authorise rule relaxation. `INSUFFICIENT_SAMPLE` does NOT authorise live trading. `INSUFFICIENT_SAMPLE` does NOT authorise Phase 12.**
>
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise Phase 12.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise rule relaxation based on low samples.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise changing the Risk Engine or the Execution FSM.**
> **Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard gate.**
> **B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol — it does NOT mean any Regime / Cluster has proven right-tail advantage yet, and it does NOT mean strategy effectiveness is proven.**
> **Long-window protocol outputs (`long_window_run_plan`, `sample_sufficiency_checklist`, `cohort_stability_checklist`, `operator_vps_evidence_template`, `export_replay_evidence_template`, `closeout_acceptance_template`) and per-window outputs (`paper_alpha_gate_status`, `regime_cluster_evidence_status`, `insufficient_sample_reasons`, daily-report Paper Alpha Gate section, daily-report Regime & Cluster Cohort Evidence Pack section, `PAPER_ALPHA_*` and `REGIME_CLUSTER_*` event counts, Phase 8.5 export bundles) remain paper-only / report-only / evidence-only.**
> **Long-window protocol outputs and per-window outputs cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **The W2 4 h window's progress from `completed_tail_label_count=0` to `completed_tail_label_count=2` is real progress but still below the 10-label sufficiency threshold; therefore `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct W2 result. This does NOT indicate runtime failure. This does NOT authorise rule relaxation.**
> **The W3 24 h upper-bound watcher early-stop at `total_elapsed_seconds=900`, `final_tail_labels_since_start=20>=10` proves the B-B-B-C sample sufficiency protocol can save runtime while preserving evidence; the full 24 h runtime was NOT NEEDED. This does NOT authorise live trading. This does NOT authorise Phase 12.**
>
> PR #42 — the Phase 11C.1C-C-B-A *Strategy Validation Lab v0
> & Cluster Exposure Control Contracts* branch
> (`feature/phase-11c1c-c-b-strategy-validation-cluster-control`)
> — has **merged into `main`** (mergeCommit `cc18047`). The
> branch shipped the data contracts
> (`StrategyValidationSample`, `StrategyValidationReport`,
> `ClusterExposureAssessment`, …), the pure aggregators
> (`build_strategy_validation_report`, `aggregate_by_strategy_mode`,
> `aggregate_by_candidate_stage`,
> `aggregate_by_opportunity_score_bucket`,
> `aggregate_by_early_tail_score_bucket`,
> `aggregate_tail_label_distribution`,
> `evaluate_cluster_leader_performance`,
> `assess_cluster_exposure`), the runtime
> (`StrategyValidationRuntime`), the seven new typed events
> (`STRATEGY_VALIDATION_SAMPLE_CREATED` /
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_EXPOSURE_ASSESSED` /
> `CLUSTER_LEADER_VALIDATED`), the daily-report section, and
> the wiring through `WSRadarChainDriver` +
> `scripts/run_public_market_paper.py`. **Phase 11C.1C-C-B-A
> is paper-only**: the `suggested_cluster_action` field on every
> `ClusterExposureAssessment` is one of `leader_only` /
> `observe_followers` / `reject_cluster` / `no_action` and
> **MUST NEVER trigger a real trade**; the Risk Engine remains
> the single trade-decision gate. Phase 11C.1C-C-B-A acceptance
> does **NOT** authorise live trading, API keys, private
> endpoints, DeepSeek trade decisions, real Telegram outbound,
> Phase 11C.1C-C-B-B kickoff bypassing the standard gate, or
> Phase 12. **Tests:** 25/25 brief-mandated tests PASS,
> 312/312 phase11c\_ tests PASS, 2286/2286 full pytest PASS on
> the PR branch (no regression vs. the post-PR-#41 main 2261
> baseline). The 30 s dry-run is **contract-only** (the
> smallest Phase 11C.1C-C-A tracking window is 5 min; a 30 s
> run cannot complete a primary window). The
> **operator-VPS 10 min real public WS smoke PASSED** with
> `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`,
> `ws_real_transport=true`,
> `ws_messages_received=76324`, `ws_chains_emitted=27`,
> `learning_ready_attached=27`, `snapshots_emitted=27`,
> `ingestion_errors=0`,
> `STRATEGY_VALIDATION_SAMPLE_CREATED=24`,
> `STRATEGY_VALIDATION_REPORT_GENERATED=1`,
> `STRATEGY_MODE_VALIDATED=4`,
> `CANDIDATE_STAGE_VALIDATED=5`,
> `SCORE_BUCKET_VALIDATED=8`,
> `CLUSTER_EXPOSURE_ASSESSED=1`,
> `CLUSTER_LEADER_VALIDATED=1` (authoritative SQLite query;
> see daily-report counter snapshot caveat below), non-empty
> daily-report cohort lines, `HTTP 429 count=0`,
> `HTTP 418 count=0`, `rate_limit_ban=False`,
> `ws_reconnect_count=0`, `ws_stale_count=0`,
> `ws_currently_stale=False`, and Phase 1 safety lock
> unchanged. PR #42 has **merged into `main`** (mergeCommit
> `cc18047`, merged 2026-05-23 UTC); the smoke evidence above
> was accepted; this docs-only closeout PR therefore records
> Phase 11C.1C-C-B-A as **ACCEPTED**. Phase 11C.1C-C-B-B is
> now **NEXT_ALLOWED / NOT_STARTED**: Phase 11C.1C-C-B-A
> acceptance does **NOT** authorise Phase 11C.1C-C-B-B
> kickoff bypassing the standard gate; Phase 11C.1C-C-B-B
> will require its own kickoff PR, brief, scope, boundary
> table, forbidden list, and acceptance evidence. Phase 12
> remains **FORBIDDEN**.
>
> *Daily-report counter snapshot caveat.* The daily report's
> top event-count lines may show
> `STRATEGY_VALIDATION_REPORT_GENERATED` /
> `STRATEGY_MODE_VALIDATED` / `CANDIDATE_STAGE_VALIDATED` /
> `SCORE_BUCKET_VALIDATED` / `CLUSTER_*` counts as **0**
> because those event counters appear to be snapshotted
> **before** shutdown flush. The authoritative event
> repository SQLite query confirms those events were
> emitted; the daily report **section itself** rendered the
> Strategy Validation cohorts non-empty and correctly. This
> is a daily-report instrumentation nuance and does **not**
> invalidate the smoke; a future polish can move the counter
> snapshot after the shutdown flush, but it is **not** in
> scope for Phase 11C.1C-C-B-A.

The Phase 1 safety lock held end-to-end across the Phase 11C.1C-B
acceptance evidence runs and remains in force on `main`:
`mode=paper`, `live_trading=False`, `right_tail=False`,
`llm=False`, `exchange_live_orders=False`,
`telegram_outbound_enabled=False`, `binance_private_api_enabled=False`.
No Binance API key, no Binance API secret, no signed endpoint, no
private WebSocket, no `listenKey`, no DeepSeek trade decision, no
real Telegram outbound, no Phase 12. Phase 11C.1C-B is **paper /
virtual** only: the new `early_tail_score` and `runtime_calibration`
block are paper / descriptive fields; the Risk Engine remains the
single trade-decision gate.

| Date (UTC) | Phase    | Tag                                        | State   | Evidence                                                |
| ---------- | -------- | ------------------------------------------ | ------- | ------------------------------------------------------- |
| 2026-05-23 | Phase 11C.1C-C-B-B-B | Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up (parent; unchanged definition; reserved for the deeper Phase 11C.1C-C-B-B follow-up after Phase 11C.1C-C-B-B-A is ACCEPTED) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-A is now **ACCEPTED** (PR #44 merged into `main`, mergeCommit `3ecfc3b`), so Phase 11C.1C-C-B-B-B is now **NEXT_ALLOWED**; no implementation has started. The parent phase is **not** renamed by Paper Alpha Gate v0; the Paper Alpha Gate v0 is one *child slice* under this parent (Phase 11C.1C-C-B-B-B-A), not the parent itself. Phase 11C.1C-C-B-B-A acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate; Phase 11C.1C-C-B-B-B will require its own kickoff PRs (one per child slice), brief, scope, boundary table, forbidden list, and acceptance evidence. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-A | Paper Alpha Gate v0 (paper / report-only first child slice under Phase 11C.1C-C-B-B-B; implementation + closeout) | **ACCEPTED (closed 2026-05-24; PR #52 merged into `main` on 2026-05-24, mergeCommit `f8ba315`; this docs-only closeout PR #54 records the operator-VPS evidence)** — branch (implementation) `feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`. Implementation PR shipped `app/adaptive/paper_alpha_gate.py` (pure-function module: `PaperAlphaGateStatus`, `PaperAlphaGateRule`, `PaperAlphaGateRuleResult`, `PaperAlphaGateCohortResult`, `PaperAlphaGateInput`, `PaperAlphaGateReport`, plus the nine pure functions `build_paper_alpha_gate_input` / `evaluate_paper_alpha_gate` / `evaluate_strategy_mode_alpha` / `evaluate_candidate_stage_alpha` / `evaluate_score_bucket_alpha` / `evaluate_cluster_alpha` / `build_paper_alpha_gate_report` / `export_paper_alpha_gate_payload` / `load_paper_alpha_gate_payload`); four new typed events (`PAPER_ALPHA_GATE_EVALUATED`, `PAPER_ALPHA_RULE_EVALUATED`, `PAPER_ALPHA_COHORT_EVALUATED`, `PAPER_ALPHA_REPORT_GENERATED`); `StrategyValidationRuntime` extended to evaluate the gate on the same flush as the dataset / quality-gate emission; Phase 11B daily-report section. Schema version `phase_11c_1c_c_b_b_b_a.paper_alpha_gate.v1`. The verdict (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) is **descriptive only** for human review and **MUST NEVER trigger a real trade**, **MUST NEVER** modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM. **Operator-VPS 10 min WS paper smoke PASSED**: `duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`. Daily report contains `"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"` with `paper_alpha_gate_status=INCONCLUSIVE`, `paper_alpha_gate_sample_count=20`, reason `completed_tail_label_count_below_min=0<10`. `PAPER_ALPHA_GATE_EVALUATED=1`, `PAPER_ALPHA_RULE_EVALUATED=9`, `PAPER_ALPHA_COHORT_EVALUATED=6`, `PAPER_ALPHA_REPORT_GENERATED=1`. Phase 8.5 export bundle generated at `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip` (`export_test_data=OK`, `manifest_event_count=1572`, `redaction_applied=True`, `events.jsonl` exists, export contains `PAPER_ALPHA_*` events, `EXPORT_PAPER_ALPHA_GATE_CHECK=PASS`); export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. `paper_alpha_gate_status=INCONCLUSIVE` is the **expected and accepted** result for this smoke window because `completed_tail_label_count=0<10` — the Paper Alpha Gate correctly refused to overfit or force a `PASS` when completed tail labels were insufficient; `INCONCLUSIVE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise live trading, does NOT authorise Phase 12. Safety flags unchanged across the operator-VPS run (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`; `docs/PR52_DESCRIPTION.md`; `docs/PR54_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_b_a_paper_alpha_gate.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-A (ACCEPTED)" + §"Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-A (kickoff) | Paper Alpha Gate v0 (docs-only kickoff / scope alignment, superseded by the PR #52 implementation; closed via PR #54 docs-only closeout) | **SUPERSEDED by PR #52 (now ACCEPTED via this docs-only closeout PR #54).** PR #51 (the docs-only kickoff) merged into `main` on 2026-05-24 and recorded the parent / child relationship + boundary table + forbidden list. The ACCEPTED row above tracks the implementation PR (PR #52, merged 2026-05-24, mergeCommit `f8ba315`) and this docs-only closeout PR (PR #54). | `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`; `docs/PR51_DESCRIPTION.md`; `docs/PR54_DESCRIPTION.md` |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-B (closeout) | Regime & Cluster Cohort Evidence Pack v0 docs-only closeout / acceptance flip (paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B; closeout via PR #57) | **ACCEPTED (closed 2026-05-24; PR #56 merged into `main` on 2026-05-24, mergeCommit `1a9abe2`; this docs-only closeout PR #57 records the operator-VPS paper evidence and flips the slice to `ACCEPTED`)**. **Operator-VPS 10 min WS paper smoke PASSED**: `duration_seconds=600.0`, `uptime≈608s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`. Daily report contains `"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"` with `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`, `sample_count=14`, `completed_tail_label_count=0`, `insufficient_sample_reasons=[sample_count_below_min=14<20, completed_tail_label_count_below_min=0<10]`. `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=1`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=5`. Phase 8.5 export bundle generated at `data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip` (`export_test_data=OK`, `manifest_event_count=3151`, `redaction_applied=True`, `events.jsonl` exists, export contains `REGIME_CLUSTER_*` events, `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK=PASS`); export package files observed: `manifest.json`, `summary_report.md`, `events.jsonl`, `opportunities.jsonl`, `signal_snapshots.jsonl`, `risk_decisions.jsonl`, `state_transitions.jsonl`, `capital_events.jsonl`, `virtual_trade_plans.jsonl`. `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` is the **expected and accepted** result for this smoke window because `sample_count=14<20` and `completed_tail_label_count=0<10` — the Regime & Cluster Evidence Pack correctly refused to overfit or force a regime / cluster conclusion when structural samples were insufficient; `INSUFFICIENT_SAMPLE` does NOT mean runtime failure, does NOT authorise strategy changes, does NOT authorise rule relaxation, does NOT authorise live trading, does NOT authorise Phase 12. Safety flags unchanged across the operator-VPS run (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** a strategy implementation, **NOT** a trading module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`; `docs/PR56_DESCRIPTION.md`; `docs/PR57_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" + §"Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED)" |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-C (closeout) | Long-Window Cohort Stability & Sample Sufficiency Protocol v0 docs-only closeout / acceptance flip (paper / report / evidence-only third child slice under Phase 11C.1C-C-B-B-B; closeout via PR #59) | **ACCEPTED (closed 2026-05-25; PR #58 docs-only kickoff merged into `main`; this docs-only closeout PR #59 records the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence and flips the slice to `ACCEPTED`)**. **W1 / W1+ 2 h paper WS run PASSED**: `duration_seconds=7200.0`, `uptime≈7238s`, `ws_first=true`, `ws_real_transport=true`, `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`, `risk_approved=0`, live trading disabled. 2 h event counts: `PAPER_ALPHA_COHORT_EVALUATED=18`, `PAPER_ALPHA_GATE_EVALUATED=3`, `PAPER_ALPHA_REPORT_GENERATED=3`, `PAPER_ALPHA_RULE_EVALUATED=27`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`. 2 h daily report contains both the Paper Alpha Gate section and the Regime & Cluster Cohort Evidence Pack section; `regime_cluster_sample_count=189`, `regime_cluster_completed_tail_label_count=0`, status remained `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` because `completed_tail_label_count=0<10` (accepted as valid low-completed-label evidence, not runtime failure). 2 h export bundle generated at `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip` (`export_test_data=OK`, `manifest_event_count=23001`, `redaction_applied=True`, `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`). **W2 4 h paper WS run PASSED**: configured `duration_seconds=14400.0`, actual runtime ≈ `14417s`, `iterations=237`, `chains_emitted=704`, `ws_chains_emitted=704`, `ws_real_transport=True`, `ws_reconnect_count=0`, `ws_staleness_ms_max=0`, `ws_stale_count=0`, `ingestion_errors=0`, `public_endpoint_calls=4226`, `ws_messages_received=1324423`, `radar_candidates_seen=152221`, `candidate_pool_size_max=20`, `liquidation_events_seen=4076`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `rate_limit_ban=False`, `risk_approved=0`, `risk_rejected=704`. 4 h event counts: `PAPER_ALPHA_COHORT_EVALUATED=24`, `PAPER_ALPHA_GATE_EVALUATED=4`, `PAPER_ALPHA_REPORT_GENERATED=4`, `PAPER_ALPHA_RULE_EVALUATED=36`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`. 4 h daily report: `paper_alpha_gate_status=INCONCLUSIVE`, `paper_alpha_gate_sample_count=164`, reason `completed_tail_label_count_below_min=2<10`; `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`, `regime_cluster_sample_count=164`, `regime_cluster_completed_tail_label_count=2`, reason `completed_tail_label_count_below_min=2<10` — progress from 0 to 2 completed labels still below the 10-label threshold; `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE` remained the correct W2 result, does NOT indicate runtime failure, does NOT authorise rule relaxation. 4 h export bundle at `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip` (`export_test_data=OK`, `manifest_event_count=61546`, `redaction_applied=True`, `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`). **W3 24 h upper-bound run PASSED with watcher early-stop**: `total_elapsed_seconds=900`, `final_tail_labels_since_start=20`, `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`, 24 h full runtime NOT NEEDED — proves the B-B-B-C sample sufficiency protocol can save runtime while preserving evidence. W3 safety summary held end-to-end (`mode=paper`, `live_trading=False`, `right_tail=False`, `llm=False`, `exchange_live_orders=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, `risk_approved=0`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_real_transport=True`); watcher logs `data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`, `data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`. **W3 export PASSED**: latest export zip after W3 early-stop `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`, generated 2026-05-25 12:41 UTC, `manifest_event_count=62761`, `redaction_applied=True`, `events.jsonl` exists, `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3 export-range event counts `TAIL_LABEL_ASSIGNED=495`, `LABEL_WINDOW_COMPLETED=495`, `STRATEGY_VALIDATION_SAMPLE_CREATED=397`, `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`, `PAPER_ALPHA_GATE_EVALUATED=5`, `PAPER_ALPHA_RULE_EVALUATED=45`, `PAPER_ALPHA_COHORT_EVALUATED=30`, `PAPER_ALPHA_REPORT_GENERATED=5` (clarification: `final_tail_labels_since_start=20` is the watcher early-stop condition for the 900 s live window; `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range event count — both valid, different scopes, do not confuse the two numbers). **B-B-B-C acceptance is acceptance of the long-window data collection and sample-sufficiency protocol** — it does **NOT** mean any Regime / Cluster has proven right-tail advantage yet, does **NOT** mean strategy effectiveness is proven, does **NOT** authorise live trading, does **NOT** authorise rule relaxation based on low samples, does **NOT** authorise automatic parameter optimisation, does **NOT** authorise AI Learning, does **NOT** authorise changing the Risk Engine or the Execution FSM, does **NOT** authorise Phase 12. It records that 2 h works, 4 h works, completed labels begin to appear over longer windows, 24 h upper-bound early-stop works, completed-tail-label sufficiency threshold can be reached early, export / replay evidence preserves the results, low-sample states remain conservative, and no trade authority was granted. Long-window protocol outputs (`long_window_run_plan`, `sample_sufficiency_checklist`, `cohort_stability_checklist`, `operator_vps_evidence_template`, `export_replay_evidence_template`, `closeout_acceptance_template`) and per-window outputs (`paper_alpha_gate_status`, `regime_cluster_evidence_status`, `insufficient_sample_reasons`, daily-report Paper Alpha Gate section, daily-report Regime & Cluster Cohort Evidence Pack section, `PAPER_ALPHA_*` and `REGIME_CLUSTER_*` event counts, Phase 8.5 export bundles) remain paper-only / report-only / evidence-only and cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes; the Risk Engine remains the single trade-decision gate. Safety flags unchanged across W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop runs (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** rule relaxation based on low samples, **NOT** Risk Engine change, **NOT** Execution FSM change, **NOT** a strategy implementation, **NOT** a trading module, **NOT** a new runtime module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`; `docs/PR58_DESCRIPTION.md`; `docs/PR59_DESCRIPTION.md`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-C (ACCEPTED)" + §"Phase 11C.1C-C-B-B-B-C acceptance evidence (operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h upper-bound early-stop paper WS evidence PASSED)" |
| 2026-05-25 | Phase 11C.1C-C-B-B-B-D | Next child slice (placeholder; not yet defined) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-B-C is now `ACCEPTED` (PR #58 docs-only kickoff merged into `main`; closeout via PR #59), so Phase 11C.1C-C-B-B-B-D is now **NEXT_ALLOWED**; no implementation has started; no kickoff PR has been opened. The child slice is **not yet defined by name or scope** in this PR — Phase 11C.1C-C-B-B-B-C acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard gate. Phase 11C.1C-C-B-B-B-D will require its own kickoff PR, brief, scope, boundary table, forbidden list, and acceptance evidence. The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B remains *Strategy Validation Lab (deeper) & richer Cluster Exposure Control follow-up*. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B / 11C.1C-C-B-B-B-C forbidden item verbatim. Paper / report / evidence-only; grants no trade authority. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B-D (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-C (kickoff) | Long-Window Cohort Stability & Sample Sufficiency Protocol v0 (docs / evidence-template-only third child slice under Phase 11C.1C-C-B-B-B; docs-only kickoff via PR #58) | **SUPERSEDED by the closeout row above (Phase 11C.1C-C-B-B-B-C = ACCEPTED via PR #59).** PR #58 (the docs-only kickoff) merged into `main` on 2026-05-25 and recorded the parent / child relationship + boundary table + forbidden list + long-window run cadence + sample sufficiency / cohort stability principles + allowed outputs. The ACCEPTED row above tracks the W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper WS evidence captured by the operator-VPS and recorded by this docs-only closeout PR (PR #59). | `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`; `docs/PR58_DESCRIPTION.md`; `docs/PR59_DESCRIPTION.md` |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-B | Regime & Cluster Cohort Evidence Pack v0 (*Regime 与 Cluster 分组证据包 v0*; paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B; docs-only kickoff via PR #55) | **NEXT_ALLOWED / NOT_STARTED** — Phase 11C.1C-C-B-B-B-A is `ACCEPTED` (PR #52 merged into `main` on 2026-05-24, mergeCommit `f8ba315`; closeout via PR #54), so Phase 11C.1C-C-B-B-B-B is **NEXT_ALLOWED**. PR #55 is the **docs-only kickoff / scope alignment** for this slice; **no runtime code is shipped by the kickoff PR**. The substantive Phase 11C.1C-C-B-B-B-B implementation requires a **separate implementation PR**. Allowed outputs (paper / report / evidence-only): `regime_cohort_summary`, `cluster_cohort_summary`, `score_bucket_summary`, `stage_outcome_summary`, `strategy_mode_outcome_summary`, `regime_cluster_evidence_pack`, `warnings`, `insufficient_sample_reasons` — each is a descriptive label only and **MUST NEVER trigger a real trade**, **MUST NEVER** modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM; the Risk Engine remains the single trade-decision gate. Slice exists to make eight cohort questions answerable from data (which Regimes produce `strong_tail` / `reached_3r` / `reached_5r`; which Regimes produce `fake_breakout` / `late_chase_failure`; whether `cluster_leader` beats followers; whether high `opportunity_score_bucket` beats low; whether high `early_tail_score_bucket` beats low; whether `follow` / `pullback` / `observe` / `reject` outcomes match expectations; which state combinations deserve continued paper observation; which must be down-weighted or rejected). Core principles: add fewer modules / accumulate more structural data; verify Regime more / talk less about strategy; prove which states carry right-tail value; replayable; reduces human-interpretation cost; serves Regime / Liquidity / Right Tail judgement; forbid unverifiable AI output; forbid system-complexity growth; forbid loosening rules on low samples. **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** a strategy implementation, **NOT** a trading module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item verbatim. Phase 12 remains **FORBIDDEN**. **SUPERSEDED by the closeout row above (Phase 11C.1C-C-B-B-B-B = ACCEPTED via PR #57).** | `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`; `docs/PR55_DESCRIPTION.md`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" |
| 2026-05-24 | Phase 11C.1C-C-B-B-B-B (implementation) | Regime & Cluster Cohort Evidence Pack v0 implementation (paper / report / evidence-only second child slice under Phase 11C.1C-C-B-B-B; implementation via PR #56) | **MERGED — superseded by the closeout row above (Phase 11C.1C-C-B-B-B-B = ACCEPTED via PR #57; PR #56 mergeCommit `1a9abe2`)** — branch (implementation) `feature/phase-11c1c-c-b-b-b-b-regime-cluster-evidence-pack-v0`. PR #56 ships `app/adaptive/regime_cluster_evidence_pack.py` (pure-function module: `RegimeClusterEvidencePackStatus`, `RegimeClusterCohortKey`, `RegimeClusterCohortStats`, `RegimeClusterEvidenceRecord`, `RegimeClusterEvidenceInput`, `RegimeCohortSummary`, `ClusterCohortSummary`, `ScoreBucketSummary`, `StageOutcomeSummary`, `StrategyModeOutcomeSummary`, `RegimeClusterEvidencePack`, plus the nine pure functions `build_regime_cluster_evidence_input` / `build_regime_cohort_summary` / `build_cluster_cohort_summary` / `build_score_bucket_summary` / `build_stage_outcome_summary` / `build_strategy_mode_outcome_summary` / `build_regime_cluster_evidence_pack` / `export_regime_cluster_evidence_payload` / `load_regime_cluster_evidence_payload`); two new typed events (`REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED`); `StrategyValidationRuntime` extended to build / emit / cache the pack on the same flush as the dataset / quality-gate / Paper Alpha Gate emission; `WSRadarChainDriver._post_chain` wires `observe_market_regime` per opportunity; Phase 11B daily-report section. Schema version `phase_11c_1c_c_b_b_b_b.regime_cluster_evidence_pack.v1`. The per-cohort `status` (`INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` / `EVIDENCE_SIGNAL`) and the top-level `regime_cluster_evidence_status` are **descriptive only** for human review and **MUST NEVER trigger a real trade**, **MUST NEVER** modify position size, leverage, stop-loss, target price, the Risk Engine, or the Execution FSM. Tests: 23/23 brief-mandated + 389/389 phase11c_ + 2363/2363 full pytest PASS on the PR branch (no regression vs. post-PR-#55 main baseline). 30 s dry-run smoke produces the new section with `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE` (expected — Phase 11C.1C-C-A primary tracking window is 5 minutes; the brief's "do not loosen rules on low samples" rule is honoured); explicit `regime_cluster_insufficient_sample_reasons` populated; no `ORDER_*` / `POSITION_*` / `STOP_*` / `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED` events emitted. Real-WS 10 min smoke is **NOT REQUIRED** for PR #56 (this PR is a deterministic evidence-compression layer; non-empty cohort rows depend on the upstream Phase 11C.1C-C-A primary tracking window resolving — reserved for the closeout PR). The slice remains **NEXT_ALLOWED / NOT_STARTED** until the operator-VPS paper smoke + closeout PR records the acceptance evidence. Safety flags unchanged across the run (`mode=paper`, `live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no Binance API key, no Binance API secret, no signed endpoint, no account / order / position / leverage / margin endpoint, no private WebSocket, no `listenKey`, no DeepSeek trade decision, no real Telegram outbound). **NOT** live trading, **NOT** AI Learning, **NOT** automatic parameter optimisation, **NOT** reinforcement learning, **NOT** a strategy implementation, **NOT** a trading module, **NOT** the complete Strategy Validation Lab follow-up, **NOT** Phase 12. Inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A forbidden item. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`; `docs/PR56_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_b_b_regime_cluster_evidence_pack.py`; `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B-B (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-23 | Phase 11C.1C-C-B-B-A | Strategy Validation Dataset Builder & Quality Gate v0 (paper / report-only first slice of Phase 11C.1C-C-B-B; ships dataset record / dataset / summary / quality-gate contracts + pure functions + the runtime hook that emits three new typed events on top of the Phase 11C.1C-C-B-A `StrategyValidationSample` / `StrategyValidationReport` / `ClusterExposureAssessment` artefacts) | **ACCEPTED (closed 2026-05-23; PR #44 merged into `main`, mergeCommit `3ecfc3b`)** — `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py` 27/27 PASS (brief-mandated cases); `tests/unit -k phase11c_` 339/339 PASS (312 baseline + 27 new); full `tests/` 2313/2313 PASS on the PR branch (no regression vs. post-PR-#43 main 2286 baseline). 30 s dry-run smoke produced an empty / low-sample report at `data/reports/phase11c/2026-05-23-phase11c-public-market.md` with the new "Phase 11C.1C-C-B-B-A Strategy Validation Dataset Builder & Quality Gate v0" section: `STRATEGY_VALIDATION_DATASET_BUILT=1`, `STRATEGY_VALIDATION_DATASET_EXPORTED=1`, `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED=1`, `validation_dataset_records=2`, `validation_dataset_symbols=BTCUSDT,ETHUSDT`, `validation_quality_gate_status=fail` (expected — the smallest Phase 11C.1C-C-A tracking window is 5 minutes; samples are necessarily in-flight in a 30 s smoke), `validation_dataset_export_ready=True`, `validation_dataset_replay_ready=True`. Real WS 10 min smoke is **NOT required** for this PR — the smallest Phase 11C.1C-C-A tracking window is 5 minutes and cannot complete in 30 s; reserved for Phase 11C.1C-C-B-B-B closeout when non-empty datasets are first observable end-to-end. Safety flags unchanged (`live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `trading_mode_paper=True`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no API key, no signed endpoint, no private WS, no listenKey, no DeepSeek trade decision, no real Telegram outbound). The `validation_quality_gate_status` field on every `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` event is descriptive only (`pass` / `warn` / `fail`) and **MUST NEVER trigger a real trade**; the Risk Engine remains the single trade-decision gate. PR #44 has merged into `main` (mergeCommit `3ecfc3b`, merged 2026-05-23 UTC); the dry-run smoke evidence above was accepted; Phase 11C.1C-C-B-B-A is therefore **ACCEPTED**. Phase 11C.1C-C-B-B-B is now **NEXT_ALLOWED / NOT_STARTED**; Phase 11C.1C-C-B-B-A acceptance does **NOT** authorise Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_B_VALIDATION_DATASET_QUALITY_GATE.md`; `docs/PR44_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-B-A (ACCEPTED)" + §"Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED / NOT_STARTED)" |
| 2026-05-23 | Phase 11C.1C-C-B-A | Strategy Validation Lab v0 & Cluster Exposure Control Contracts (paper / report-only first slice of Phase 11C.1C-C-B; ships data contracts + pure aggregators + runtime that emits seven new typed events on top of the Phase 11C.1C-C-A `LabelTrackingRecord` outcomes) | **ACCEPTED (closed 2026-05-23; PR #42 merged into `main`, mergeCommit `cc18047`)** — `tests/unit/test_phase11c_1c_c_b_strategy_validation.py` 25 PASS (brief-mandated cases); `tests/unit -k phase11c_` 312 PASS (287 baseline + 25 new); full `tests/` 2286 PASS on the PR branch (no regression vs. post-PR-#41 main 2261 baseline). 30 s dry-run smoke is contract-only (smallest Phase 11C.1C-C-A tracking window is 5m and cannot complete in 30 s); the runtime emits an empty-but-well-formed `STRATEGY_VALIDATION_REPORT_GENERATED` so the daily report still renders the new section. **Operator-VPS 10 min real public WS smoke PASSED** on 2026-05-23 against PR #42 head (commit `0bedcce`): `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=76324`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `ingestion_errors=0`, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`. Authoritative SQLite event-count query (captured after shutdown flush): `STRATEGY_VALIDATION_SAMPLE_CREATED=24`, `STRATEGY_VALIDATION_REPORT_GENERATED=1`, `STRATEGY_MODE_VALIDATED=4`, `CANDIDATE_STAGE_VALIDATED=5`, `SCORE_BUCKET_VALIDATED=8`, `CLUSTER_EXPOSURE_ASSESSED=1`, `CLUSTER_LEADER_VALIDATED=1`. Daily report contains the new "Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster Exposure Control Contracts" section with non-empty cohort lines (`strategy_mode=reject n=24`; `candidate_stage=early n=24`; `opportunity_score_bucket=0-49 n=13` / `50-64 n=11`; `early_tail_score_bucket=0-24 n=24`; `cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action`); `tail_label_distribution = unresolved x 24` (5m primary windows still in-flight at the 10 min boundary, as expected). Daily-report counter snapshot caveat: top event-count lines may show 0 because counters are snapshotted before shutdown flush; SQLite query is authoritative and confirms emission. Safety flags unchanged (`live_trading=False`, `exchange_live_orders=False`, `right_tail=False`, `llm=False`, `trading_mode_paper=True`, `telegram_outbound_enabled=False`, `binance_private_api_enabled=False`, no API key, no signed endpoint, no private WS, no listenKey, no DeepSeek trade decision, no real Telegram outbound). The Kiro-side sandbox cannot host this smoke (Binance-region HTTP 451 geoblock — historical context only, not the current blocker; same as the Phase 11C.1C-B / Phase 11C.1C-C-A closeouts). The `suggested_cluster_action` field on every `ClusterExposureAssessment` is paper / report only (`leader_only` / `observe_followers` / `reject_cluster` / `no_action`) and **MUST NEVER trigger a real trade**; the Risk Engine remains the single trade-decision gate. PR #42 has merged into `main` (mergeCommit `cc18047`, merged 2026-05-23 UTC); the smoke evidence above was accepted; this docs-only closeout PR therefore flips Phase 11C.1C-C-B-A to **ACCEPTED**, mirroring the PR #36 → PR #37, PR #38 → PR #39, and PR #40 → PR #41 closeout pattern. Phase 11C.1C-C-B-B is now **NEXT_ALLOWED / NOT_STARTED**; Phase 11C.1C-C-B-A acceptance does **NOT** authorise Phase 11C.1C-C-B-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_B_STRATEGY_VALIDATION_CLUSTER_CONTROL.md`; `docs/PR42_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_b_strategy_validation.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-B-A (ACCEPTED)" + §"Phase 11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real public WS smoke PASSED)" |
| 2026-05-23 | Phase 11C.1C-C-A | MFE / MAE Label Queue Runtime & Tail Outcome Tracking (paper-only runtime that consumes the Phase 11C.1C-A `LABEL_QUEUE_ENQUEUED` contract and produces forward MFE / MAE / `tail_label` outcomes per ACTIVE candidate) | **ACCEPTED (closed 2026-05-23; PR #40 merged into `main`, mergeCommit `75d3c7c`)** — `tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py` 30 PASS (brief-mandated cases); `tests/unit -k phase11c_` 287 PASS; full `tests/` 2261 PASS on the PR branch (no regression vs. post-PR-#38 main baseline). 30 s dry-run smoke is contract-only (the smallest tracking window is 5m and cannot complete in 30 s). **Operator-VPS 10 min real public WS smoke PASSED** (`duration_seconds=600.0`, `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=56592`, `ws_chains_emitted=27`, `learning_ready_attached=27`, `snapshots_emitted=27`, `LABEL_TRACKING_STARTED=19` runner / `36` events.db, `LABEL_WINDOW_UPDATED=38` / `82`, `LABEL_WINDOW_COMPLETED=11` / `20`, `TAIL_LABEL_ASSIGNED=11` / `20`, `MISSED_TAIL_DETECTED=0`, `FAKE_BREAKOUT_DETECTED=0`, pending=8 / completed=11 / expired=0 / unresolved=0, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_stale_count=0`, `ws_currently_stale=False`, `ingestion_errors=0`, safety flags unchanged); the Kiro sandbox could not host the smoke (Binance-region HTTP 451 geoblock, same as the Phase 11C.1C-B closeout), so the operator ran it from a Binance-reachable VPS. PR #40 has merged into `main` (mergeCommit `75d3c7c`); the smoke evidence above was accepted; Phase 11C.1C-C-A is therefore **ACCEPTED**. Phase 11C.1C-C-A acceptance does **NOT** authorise Phase 11C.1C-C-B kickoff bypassing the standard gate. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md`; `docs/PR40_DESCRIPTION.md`; `tests/unit/test_phase11c_1c_c_a_label_queue_runtime.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-C-A (ACCEPTED)" + §"Phase 11C.1C-C-A acceptance evidence (closeout)" |
| 2026-05-22 | Phase 11C.1C-B | Adaptive Candidate Runtime Calibration & Early Tail Discovery v0 (paper-only runtime calibration metrics + Early Tail Discovery v0 + daily-report enhancements) | **ACCEPTED (closed 2026-05-22; PR #38 merged into `main`)** — `tests/unit/test_phase11c_1c_b_runtime_calibration.py` 12 PASS; `tests/unit -k phase11c_` 257 PASS; full `tests/` 2231 PASS with no regression vs. the post-PR-#37 main baseline; 30s dry-run produced a `runtime_calibration` block with all 15 fields on every adaptive event and `early_tail_score` per ACTIVE candidate; 5min real public WS smoke (`--ws-first`, no `--dry-run`) confirmed `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=30526`, `ws_chains_emitted=12`, runtime calibration block present on every adaptive event, daily report contains `top_early_tail_candidates` / `top_late_chase_risk_candidates` / `early_tail_score_top_symbols` / `opportunity_score_distribution`, `label_queue` remains contract-only, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `rate_limit_ban=False`, `ws_stale_count=0`, `ws_reconnect_count=0`, `ingestion_errors=12` (explainable: sandbox-region geoblock HTTP 451 on Binance REST; NOT a 429/418/ban; WS pump ran cleanly), safety flags unchanged. PR #38 merged into `main` (mergeCommit `ce4b6de`); the smoke evidence above was accepted; Phase 11C.1C-B is therefore **ACCEPTED**. Phase 11C.1C-C is now **NEXT_ALLOWED / NOT_STARTED**. Phase 12 remains **FORBIDDEN**. | `docs/PHASE_11C_1C_B_RUNTIME_CALIBRATION.md`; `tests/unit/test_phase11c_1c_b_runtime_calibration.py`; `docs/PHASE_GATE.md` §"Phase 11C.1C-B acceptance evidence (closeout)" |
| 2026-05-22 | Phase 11C.1C-A | Adaptive Candidate Regime & Strategy Selector Contracts (paper-only data contracts + scoring + selector + paper-only routing first version) | **ACCEPTED (PR #36 merged; PR #37 docs closeout)** — 244/244 phase11c tests + 2219/2219 full pytest pass on the PR branch; 30s dry-run produces the six adaptive events per ACTIVE candidate; 5min real public WS smoke produced 32842 real WS messages, 12 chains, 12 each of the six adaptive event types, 0 stales, 0 reconnects, 0 rate-limit 429/418/ban; daily report contains the Phase 11C.1C-A adaptive section; safety flags unchanged. PR #36 merged into `main`; PR #37 closed the Phase 11C.1C-A docs gate. | `docs/PHASE_11C_1C_ADAPTIVE_CANDIDATE_REGIME_STRATEGY_SELECTOR.md`; `tests/unit/test_phase11c_1c_a_adaptive_candidate.py`; `docs/PHASE_GATE.md` §"Closed phase: Phase 11C.1C-A (ACCEPTED)" |
| 2026-05-22 | Phase 11C.1B | WebSocket-First All-Market Demon Coin Radar (incl. SymbolUniverse exchangeInfo-as-truth, non-ASCII contracts allowed) | **ACCEPTED** — 5min / 10min / 1h real WS smoke PASS (no 429, no 418, no stale, no ingestion errors); export zip generated; events.db readable; PRs #31 / #32 / #33 / #34 merged; safety flags unchanged | `docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B |
| 2026-05-21 | Phase 11C.1A | Binance Public REST Rate Limit Governor & 418 Protection | merged        | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1A     |
| 2026-05-21 | Phase 11C | Real Binance Public Market Data Read-Only Paper | open (parent); Phase 11C.1B (5min / 10min / 1h smoke) ACCEPTED 2026-05-22; longer-window (6h / 24h) acceptance still optional / not yet run | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md`             |
| 2026-05-19 | Phase 11B-HF | Cloud Paper - High-Frequency observation     | accepted (GO) | 30/30 dry-run PASS, 648/648 24h@2min observations PASS |
| 2026-05-19 | Phase 11B | Cloud Paper Acceptance                       | accepted (GO) | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`            |
| ...        | Phase 10D | Telegram Outbound + Export Commands          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10C | LLM Guarded Interpreter (receive-only)       | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10B | Reflection + Replay engines (read-only)      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10A | Replay engine substrate                      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 9   | Execution FSM + Reconciliation               | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 8.5 | Learning-Ready Data Contract                 | merged        | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`           |
| ...        | Phase 8   | Capital Flow Engine                          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 7   | Risk Engine + No-Trade Gate                  | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 6   | Pre-Anomaly + Anomaly + Confirmation + Manipulation | merged | `docs/CHANGELOG.md`                                  |
| ...        | Phase 5   | Regime + Universe + Liquidity                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 4   | Market Data Buffer                           | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 3   | Exchange Gateway (read-only abstract)        | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 2   | Event Sourcing + Database Set                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 1   | Safety Foundation                            | merged        | `docs/CHANGELOG.md`                                    |

## Live safety flags (Phase 1 lock)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

The Phase 1 safety lock in `app/config/settings.py::_apply_phase1_safety_lock`
hard-coerces the first five flags. The Phase 11C
`MarketDataConfig` and `SafetyConfig` schemas refuse to load any
deployment that flips a `forbid_*` flag.

## Why the Phase 11C real-data acceptance was paused (historical, RESOLVED)

The first 24h test against the real Binance public REST endpoints
(`fapi.binance.com`) exposed two failure modes the original Phase 11C
runner did not protect against:

  1. HTTP 429 (Too Many Requests). Binance returned this once the
     per-IP weight budget was exceeded. The runner kept polling and
     escalated to:
  2. HTTP 418 (I'm a teapot). Binance uses 418 to signal a real IP
     ban.

Phase 11C's safety lock held throughout (`mode=paper`,
`live_trading=False`, no API key, no signed endpoint, no real order),
but the gateway was unusable for real-data acceptance until the
rate-limit problem is fixed.

**Phase 11C.1A** (PR #31) shipped the fix in three layers:

  - a new `BinancePublicRestGovernor`
    (`app/exchanges/binance_rate_limit.py`) that wraps every public
    REST call, tracks the rolling weight budget, sleeps the
    `Retry-After` window on 429, latches into protection mode on
    418, and opens a P1 incident;
  - lower defaults (`symbol_limit=5`, `rest_poll_interval_seconds=60`,
    `weight_budget_per_minute=300`, soft 0.50 / hard 0.75);
  - a layered REST runner that does `exchangeInfo` / `ticker/24hr`
    only at bootstrap and refuses per-symbol detail REST calls
    unless a candidate ranking selects them.

**Phase 11C.1B** (PRs #32 / #33 / #34) then shipped the WebSocket-first
all-market radar + the routed real-network public WS adapter + the
WS poll fix + the SymbolUniverse exchangeInfo-as-truth gate (non-ASCII
contracts admitted; ASCII-only regex banned). The 5min / 10min / 1h
real-WS smoke ladder now passes cleanly with zero 429 / 418 / stale /
ingestion errors. See "Phase 11C.1B acceptance evidence (closeout)"
below for the headline numerics.

PR-C (cluster exposure control + multi-candidate priority ranking)
remains a separate, future scope item and is **not** required for the
Phase 11C.1B closeout; it is tracked alongside the future
Phase 11C.1C — Adaptive Candidate Regime & Strategy Selector work.

## What Phase 11C is

Phase 11C is real **Binance public market data** read-only paper.
It connects to public REST endpoints (`/fapi/v1/exchangeInfo`,
`/fapi/v1/ticker/24hr`, `/fapi/v1/klines`, `/fapi/v1/aggTrades`,
`/fapi/v1/depth`, `/fapi/v1/fundingRate`, `/fapi/v1/openInterest`,
`/fapi/v1/premiumIndex`, `/fapi/v1/ticker/bookTicker`), feeds the
data through the existing `MarketDataBuffer` and Risk Engine, and
emits the full Phase 11C event chain into `events.db`.

## What Phase 11C is NOT

- NOT live trading
- NOT connected to the Binance trading API
- NOT consuming any Binance API key / API secret
- NOT calling any signed endpoint
- NOT calling any account / position / leverage / margin endpoint
- NOT connected to DeepSeek
- NOT connected to a real Telegram bot
- NOT connected to 币安广场
- NOT a path into Phase 12

## Open phase

**Phase 11C.1C-C-B-B-B — Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up.** Status:
**NEXT_ALLOWED / NOT_STARTED.** Phase 11C.1C-C-B-B-A (PR #44)
merged into `main` on 2026-05-23 (mergeCommit `3ecfc3b`); the
30 s dry-run smoke evidence (empty / low-sample quality-gate
report with `validation_quality_gate_status=fail`, exactly the
brief's expectation for a low-sample window) was accepted;
Phase 11C.1C-C-B-B-A is therefore **ACCEPTED**, and Phase
11C.1C-C-B-B-B is now **NEXT_ALLOWED**. No implementation has
started in this repo state; Phase 11C.1C-C-B-B-B will require
its own kickoff PR, brief, scope, boundary table, forbidden
list, and acceptance evidence.

> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise Phase
> 11C.1C-C-B-B-B kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise private
> endpoints.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise DeepSeek
> trade decisions.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise real
> Telegram outbound.**
> **Phase 11C.1C-C-B-B-A acceptance does NOT authorise Phase 12.**
> **`validation_quality_gate_status` (`pass` / `warn` / `fail`)
> cannot trigger real trading** — it is a descriptive label
> only; the Risk Engine remains the single trade-decision
> gate.
> **Validation result / cluster action / `strategy_mode` /
> `suggested_cluster_action` / `mfe_pct` / `mae_pct` /
> `tail_label` cannot trigger real trading** — they are
> descriptive labels only; the Risk Engine remains the
> single trade-decision gate.
> **Phase 12 (real money / live trading) remains FORBIDDEN.**

Phase 11C.1C-C-B-B-B inherits every Phase 1 + Phase 11C.1B +
Phase 11C.1C-A + Phase 11C.1C-B + Phase 11C.1C-C-A +
Phase 11C.1C-C-B-A + Phase 11C.1C-C-B-B-A forbidden item:

  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`, the
    seven `STRATEGY_VALIDATION_*` events, validation cohort
    stats, `suggested_cluster_action`,
    `validation_quality_gate_status`,
    `STRATEGY_VALIDATION_DATASET_BUILT`,
    `STRATEGY_VALIDATION_DATASET_EXPORTED`,
    `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`) to a
    real-trade authority
  - automatic parameter optimisation that self-modifies the
    runtime configuration
  - reinforcement learning that drives trade decisions
  - AI Learning that auto-decides trades
  - the complete Strategy Validation Lab follow-up
  - the Paper Alpha Gate v0 (Paper Alpha Gate v0 is NOT
    implemented by Phase 11C.1C-C-B-B-A; it may only start
    as the Phase 11C.1C-C-B-B-B-A child slice after this
    docs-only kickoff and a separate implementation PR;
    Paper Alpha Gate v0 remains paper-only / report-only
    and grants no trade authority — verdict (`PASS` /
    `WARN` / `FAIL` / `INCONCLUSIVE`) MUST NEVER trigger a
    real trade or modify position size, leverage,
    stop-loss, target price, the Risk Engine, or the
    Execution FSM)

See `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C-C-B-B-B
(NEXT_ALLOWED / NOT_STARTED)" for the inherited boundary
table.

### Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0 (first child slice; ACCEPTED via PR #54 docs-only closeout)

**Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0.** Status:
**ACCEPTED (closed 2026-05-24; PR #52 merged into `main` on
2026-05-24, mergeCommit `f8ba315`; this docs-only closeout PR
#54 records the operator-VPS paper evidence that flips the
slice to `ACCEPTED`).** Phase 11C.1C-C-B-B-B-A is the
**first child slice** under the Phase 11C.1C-C-B-B-B parent.
The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B
remains *Strategy Validation Lab (deeper) & richer Cluster
Exposure Control follow-up*. Phase 11C.1C-C-B-B-B-A carves
out **only** the *Paper Alpha Gate v0* — the smallest
auditable evidence-gate on top of the Phase 11C.1C-C-B-B-A
artefacts — leaving the remaining deeper Lab follow-up work
for later child slices (B-B-B-B, B-B-B-C, …) under the same
parent.

PR #52 (branch
`feature/phase-11c1c-c-b-b-b-a-paper-alpha-gate-v0`) merged
the Paper Alpha Gate v0 implementation into `main` on
2026-05-24. PR #54 (this docs-only closeout) records the
operator-VPS paper evidence and flips Phase 11C.1C-C-B-B-B-A
to `ACCEPTED`, mirroring the PR #36 → PR #37, PR #38 → PR
#39, PR #40 → PR #41, PR #42 → PR #43, PR #44 → PR #50, and
PR #52 → PR #53 → PR #54 docs-only closeout pattern.

The full Phase 11C.1C-C-B-B-B-A scope, boundary, and
forbidden-item list are recorded in
`docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md`,
`docs/PR52_DESCRIPTION.md`, and
`docs/PR54_DESCRIPTION.md`.

> **Phase 11C.1C-C-B-B-B-A is paper / report / evidence only.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-A acceptance does NOT authorise Phase 12.**
> **Paper Alpha Gate v0 verdict (`PASS` / `WARN` / `FAIL` / `INCONCLUSIVE`) cannot trigger real trading**, modify position size, modify leverage, modify stop-loss, modify target price, modify the Risk Engine, or modify the Execution FSM — it is a descriptive label only.
> **Paper Alpha Gate verdicts remain paper-only / report-only / evidence-only.**
> **Paper Alpha Gate verdicts cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **Risk Engine remains the single trade-decision gate.**
> **Execution FSM remains paper today.**
> **Phase 12 (real money / live trading) remains FORBIDDEN.**

Phase 11C.1C-C-B-B-B-A is paper / report / evidence-only and:

  - is **NOT** real / live trading;
  - is **NOT** AI Learning;
  - is **NOT** automatic parameter optimisation;
  - is **NOT** reinforcement learning;
  - is **NOT** the complete Strategy Validation Lab
    follow-up (reserved for later child slices under Phase
    11C.1C-C-B-B-B);
  - is **NOT** a strategy-quality / profitability oracle;
  - is **NOT** a strategy autonomous optimisation loop;
  - is **NOT** a position-sizing / leverage / stop-loss /
    target-price modifier;
  - is **NOT** a Risk Engine override / bypass;
  - is **NOT** an Execution FSM override / bypass;
  - is **NOT** a Phase Gate override / bypass;
  - is **NOT** a path into Phase 12;
  - is **NOT** a sample-trust gate (the existing Phase
    11C.1C-C-B-B-A `validation_quality_gate_status` field is
    the sample-trust gate; Paper Alpha Gate v0 *consumes*
    that field as an input);
  - is **NOT** a real-trade authority of any kind.

#### Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min WS paper smoke PASSED + Phase 8.5 export bundle)

Operator-VPS 10 min WS paper smoke:

  - `duration_seconds = 600.0`
  - `uptime ≈ 608s`
  - `ws_first = true`
  - `ws_real_transport = true`
  - `ingestion_errors = 0`
  - `HTTP 429 = 0`
  - `HTTP 418 = 0`

Paper Alpha Gate daily report:

  - Daily report contains `"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0"`
  - `paper_alpha_gate_status = INCONCLUSIVE`
  - `paper_alpha_gate_sample_count = 20`
  - reason: `completed_tail_label_count_below_min=0<10`

Paper Alpha Gate events (runner snapshot + events.db
type-count cross-check, after shutdown flush):

  - `PAPER_ALPHA_GATE_EVALUATED = 1`
  - `PAPER_ALPHA_RULE_EVALUATED = 9`
  - `PAPER_ALPHA_COHORT_EVALUATED = 6`
  - `PAPER_ALPHA_REPORT_GENERATED = 1`

Export evidence (Phase 8.5 export bundle):

  - `export_test_data = OK`
  - export zip generated: `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip`
  - `manifest_event_count = 1572`
  - `redaction_applied = True`
  - `events.jsonl` exists
  - export contains `PAPER_ALPHA_*` events
  - `EXPORT_PAPER_ALPHA_GATE_CHECK = PASS`

Export package files observed:

  - `manifest.json`
  - `summary_report.md`
  - `events.jsonl`
  - `opportunities.jsonl`
  - `signal_snapshots.jsonl`
  - `risk_decisions.jsonl`
  - `state_transitions.jsonl`
  - `capital_events.jsonl`
  - `virtual_trade_plans.jsonl`

`paper_alpha_gate_status = INCONCLUSIVE` is an **expected
and accepted** result for this smoke window because
`completed_tail_label_count = 0 < 10`. This means the Paper
Alpha Gate correctly refused to overfit or force a `PASS`
when completed tail labels were insufficient. **`INCONCLUSIVE`
does NOT mean runtime failure. `INCONCLUSIVE` does NOT
authorise strategy changes. `INCONCLUSIVE` does NOT authorise
live trading. `INCONCLUSIVE` does NOT authorise Phase 12.**

Safety boundary held end-to-end across the operator-VPS run:

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

See `docs/PHASE_11C_1C_C_B_B_B_PAPER_ALPHA_GATE.md` for the
full Phase 11C.1C-C-B-B-B-A scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Closed
phase: Phase 11C.1C-C-B-B-B-B-A (ACCEPTED)" + §"Phase
11C.1C-C-B-B-B-A acceptance evidence (operator-VPS 10 min
WS paper smoke PASSED)" for the verbatim transcript; see
`docs/PR51_DESCRIPTION.md` for the docs-only kickoff PR; see
`docs/PR52_DESCRIPTION.md` for the merged implementation PR;
see `docs/PR54_DESCRIPTION.md` for this docs-only closeout
PR.

### Phase 11C.1C-C-B-B-B-B — Regime & Cluster Cohort Evidence Pack v0 (second child slice; ACCEPTED via PR #57 docs-only closeout)

**Phase 11C.1C-C-B-B-B-B — *Regime & Cluster Cohort Evidence
Pack v0 / Regime 与 Cluster 分组证据包 v0*.** Status:
**ACCEPTED (closed 2026-05-24; PR #56 merged into `main` on
2026-05-24, mergeCommit `1a9abe2`; this docs-only closeout PR
#57 records the operator-VPS paper evidence that flips the
slice to `ACCEPTED`).** Phase 11C.1C-C-B-B-B-B is the
**second child slice** under the Phase 11C.1C-C-B-B-B
parent. The parent phase is **not** renamed: Phase
11C.1C-C-B-B-B remains *Strategy Validation Lab (deeper) &
richer Cluster Exposure Control follow-up*. Phase
11C.1C-C-B-B-B-B carved out **only** the *Regime & Cluster
Cohort Evidence Pack v0* — a read-only / evidence-only
compression layer on top of the Phase 11C.1C-C-B-B-A
artefacts — leaving the remaining deeper Lab follow-up
work for later child slices (B-B-B-C, …) under the same
parent.

PR #55 (docs-only kickoff) recorded the scope, boundary,
forbidden list, and allowed outputs. PR #56 (branch
`feature/phase-11c1c-c-b-b-b-b-regime-cluster-evidence-pack-v0`)
merged the substantive Regime & Cluster Cohort Evidence
Pack v0 implementation into `main` on 2026-05-24
(mergeCommit `1a9abe2`). PR #57 (this docs-only closeout)
records the operator-VPS paper evidence and flips Phase
11C.1C-C-B-B-B-B to `ACCEPTED`, mirroring the PR #36 → PR
#37, PR #38 → PR #39, PR #40 → PR #41, PR #42 → PR #43, PR
#44 → PR #50, and PR #52 → PR #54 docs-only closeout
pattern.

The full Phase 11C.1C-C-B-B-B-B scope, boundary, and
forbidden-item list are recorded in
`docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`,
`docs/PR55_DESCRIPTION.md`,
`docs/PR56_DESCRIPTION.md`, and
`docs/PR57_DESCRIPTION.md`.

> **Phase 11C.1C-C-B-B-B-B is paper / report / evidence only.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise live trading.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise API keys.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise private endpoints.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise DeepSeek trade decisions.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise real Telegram outbound.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise AI Learning.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 12.**
> **Regime & Cluster Evidence Pack outputs (per-cohort `status` and top-level `regime_cluster_evidence_status` — `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` / `EVIDENCE_SIGNAL`) cannot trigger real trading**, modify position size, modify leverage, modify stop-loss, modify target price, modify the Risk Engine, or modify the Execution FSM — they are descriptive labels only.
> **Regime & Cluster Evidence Pack outputs remain paper-only / report-only / evidence-only.**
> **Regime & Cluster Evidence Pack outputs cannot trigger orders, leverage, position sizing, stop changes, target changes, Risk Engine changes, or Execution FSM changes.**
> **Risk Engine remains the single trade-decision gate.**
> **Execution FSM remains paper today.**
> **Phase 12 (real money / live trading) remains FORBIDDEN.**

Phase 11C.1C-C-B-B-B-B is paper / report / evidence-only and:

  - is **NOT** real / live trading;
  - is **NOT** AI Learning;
  - is **NOT** automatic parameter optimisation;
  - is **NOT** reinforcement learning;
  - is **NOT** the complete Strategy Validation Lab
    follow-up (reserved for later child slices under Phase
    11C.1C-C-B-B-B);
  - is **NOT** a strategy implementation;
  - is **NOT** a trading module;
  - is **NOT** a position-sizing / leverage / stop-loss /
    target-price modifier;
  - is **NOT** a Risk Engine override / bypass;
  - is **NOT** an Execution FSM override / bypass;
  - is **NOT** a Phase Gate override / bypass;
  - is **NOT** a path into Phase 12;
  - is **NOT** a replacement for the Phase 11C.1C-C-B-B-B-A
    Paper Alpha Gate v0 verdict (the evidence pack is
    *additive*, not a replacement);
  - is **NOT** a real-trade authority of any kind.

**Why this slice exists (positioning under AMOS).** This
slice is a direct application of the
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` governance
to the next concrete step under Phase 11C.1C-C-B-B-B. The
project's main line must converge on: add fewer modules /
accumulate more structural data; verify Regime more / talk
less about strategy; prove which states really carry
right-tail value rather than chase a universal model. Phase
11C.1C-C-B-B-B-B is exactly that step — a **read-only /
evidence-only compression layer** that organises the
artefacts already produced by upstream slices (Phase
11C.1C-C-A label-tracking outcomes, Phase 11C.1C-C-B-A
validation samples / cluster exposure assessments, Phase
11C.1C-C-B-B-A validation dataset / quality gate, Phase
11C.1C-C-B-B-B-A Paper Alpha Gate verdict) into cohort
summaries by Regime, Cluster, Stage, Strategy Mode, and
Score Bucket.

**Allowed outputs (paper / report / evidence-only).** Each
is a **descriptive label only**. None has trade authority.
None is read by the Risk Engine or the Execution FSM:

  - `regime_cohort_summary`
  - `cluster_cohort_summary`
  - `score_bucket_summary`
  - `stage_outcome_summary`
  - `strategy_mode_outcome_summary`
  - `regime_cluster_evidence_pack`
  - `warnings`
  - `insufficient_sample_reasons`

#### Phase 11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min WS paper smoke PASSED + Phase 8.5 export bundle)

Operator-VPS 10 min WS paper smoke:

  - `duration_seconds = 600.0`
  - `uptime ≈ 608s`
  - `ws_first = true`
  - `ws_real_transport = true`
  - `ingestion_errors = 0`
  - `HTTP 429 = 0`
  - `HTTP 418 = 0`

Regime & Cluster Cohort Evidence Pack daily report:

  - Daily report contains `"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"`
  - `regime_cluster_evidence_status = INSUFFICIENT_SAMPLE`
  - `sample_count = 14`
  - `completed_tail_label_count = 0`
  - `insufficient_sample_reasons`:
      - `sample_count_below_min=14<20`
      - `completed_tail_label_count_below_min=0<10`

Regime & Cluster Cohort Evidence Pack events (runner
snapshot + events.db type-count cross-check, after shutdown
flush):

  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = 1`
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 5`

Export evidence (Phase 8.5 export bundle):

  - `export_test_data = OK`
  - export zip generated:
    `data/reports/exports/ama_rt_test_data_1779635774169_export_d.zip`
  - `manifest_event_count = 3151`
  - `redaction_applied = True`
  - `events.jsonl` exists
  - export contains `REGIME_CLUSTER_*` events
  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = 1` (in export)
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 5` (in export)
  - `EXPORT_REGIME_CLUSTER_EVIDENCE_CHECK = PASS`

Export package files observed:

  - `manifest.json`
  - `summary_report.md`
  - `events.jsonl`
  - `opportunities.jsonl`
  - `signal_snapshots.jsonl`
  - `risk_decisions.jsonl`
  - `state_transitions.jsonl`
  - `capital_events.jsonl`
  - `virtual_trade_plans.jsonl`

`regime_cluster_evidence_status = INSUFFICIENT_SAMPLE` is
an **expected and accepted** result for this smoke window
because `sample_count = 14 < 20` and
`completed_tail_label_count = 0 < 10`. This means the
Regime & Cluster Evidence Pack **correctly refused to
overfit or force a regime / cluster conclusion when
structural samples were insufficient**. **`INSUFFICIENT_SAMPLE`
does NOT mean runtime failure. `INSUFFICIENT_SAMPLE` does
NOT authorise strategy changes. `INSUFFICIENT_SAMPLE` does
NOT authorise rule relaxation. `INSUFFICIENT_SAMPLE` does
NOT authorise live trading. `INSUFFICIENT_SAMPLE` does NOT
authorise Phase 12.**

Safety boundary held end-to-end across the operator-VPS run:

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

See `docs/PHASE_11C_1C_C_B_B_B_B_REGIME_CLUSTER_EVIDENCE_PACK.md`
for the full Phase 11C.1C-C-B-B-B-B scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Closed
phase: Phase 11C.1C-C-B-B-B-B (ACCEPTED)" + §"Phase
11C.1C-C-B-B-B-B acceptance evidence (operator-VPS 10 min
WS paper smoke PASSED)" for the verbatim transcript; see
`docs/PR55_DESCRIPTION.md` for the docs-only kickoff PR; see
`docs/PR56_DESCRIPTION.md` for the merged implementation
PR; see `docs/PR57_DESCRIPTION.md` for this docs-only
closeout PR.

### Phase 11C.1C-C-B-B-B-C — Long-Window Cohort Stability & Sample Sufficiency Protocol v0 (*长窗口 Cohort 稳定性与样本充足协议 v0*; docs / evidence-template-only third child slice under Phase 11C.1C-C-B-B-B; ACCEPTED via PR #58 docs-only kickoff + PR #59 docs-only closeout)

**Phase 11C.1C-C-B-B-B-C — Long-Window Cohort Stability &
Sample Sufficiency Protocol v0 / 长窗口 Cohort 稳定性与样
本充足协议 v0.** Status: **ACCEPTED (closed 2026-05-25;
PR #58 docs-only kickoff merged into `main`; this
docs-only closeout PR #59 records the operator-VPS W1 /
W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop paper
WS evidence and flips the slice to `ACCEPTED`).** Phase
11C.1C-C-B-B-B-B (*Regime & Cluster Cohort Evidence Pack
v0*) is `ACCEPTED` (PR #56 merged into `main` on
2026-05-24, mergeCommit `1a9abe2`; closeout via PR #57);
PR #58 was the docs-only kickoff for B-B-B-C; PR #59
records the W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound
early-stop paper WS evidence and flips Phase
11C.1C-C-B-B-B-C to `ACCEPTED`. The slice remains
intentionally **docs / evidence-template only** end-to-end
(no future implementation PR added a new runtime module
under this slice — it consumed the existing Regime &
Cluster Cohort Evidence Pack v0 and Paper Alpha Gate v0
runtime + daily-report + Phase 8.5 export pipeline). Phase
11C.1C-C-B-B-B-D is now **NEXT_ALLOWED / NOT_STARTED**
(placeholder; not yet defined; will require its own
kickoff PR, brief, scope, boundary table, forbidden list,
and acceptance evidence).

The parent phase is **not** renamed: Phase 11C.1C-C-B-B-B
remains *Strategy Validation Lab (deeper) & richer Cluster
Exposure Control follow-up*. Phase 11C.1C-C-B-B-B-C carved
out the third small, auditable slice under that parent —
following B-B-B-A (Paper Alpha Gate v0) and B-B-B-B
(Regime & Cluster Cohort Evidence Pack v0).

**B-B-B-C acceptance is acceptance of the long-window data
collection and sample-sufficiency protocol.** It does
**NOT** mean any Regime / Cluster has proven right-tail
advantage yet, does **NOT** mean strategy effectiveness is
proven, does **NOT** authorise live trading, API keys,
private endpoints, DeepSeek trade decisions, real Telegram
outbound, AI Learning, automatic parameter optimisation,
reinforcement learning, rule relaxation based on low
samples, Risk Engine changes, Execution FSM changes, or
Phase 12. It records that 2 h works, 4 h works, completed
labels begin to appear over longer windows, the 24 h
upper-bound early-stop works, the completed-tail-label
sufficiency threshold can be reached early, export /
replay evidence preserves the results, low-sample states
remain conservative (`INSUFFICIENT_SAMPLE` /
`INCONCLUSIVE` are valid outputs not failures), and no
trade authority was granted by any window.

#### Phase 11C.1C-C-B-B-B-C operator-VPS evidence (recorded by PR #59)

  - **W1 / W1+ — 2 h Long-Window Paper WS Run (PASS):**
    `duration_seconds=7200.0`, `uptime≈7238s`,
    `ws_first=true`, `ws_real_transport=true`,
    `ingestion_errors=0`, `HTTP 429=0`, `HTTP 418=0`,
    `risk_approved=0`, live trading disabled. 2 h event
    counts: `PAPER_ALPHA_COHORT_EVALUATED=18`,
    `PAPER_ALPHA_GATE_EVALUATED=3`,
    `PAPER_ALPHA_REPORT_GENERATED=3`,
    `PAPER_ALPHA_RULE_EVALUATED=27`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`. 2 h daily
    report contains both the Paper Alpha Gate section and
    the Regime & Cluster Cohort Evidence Pack section;
    `regime_cluster_sample_count=189`,
    `regime_cluster_completed_tail_label_count=0`, status
    remained `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE`
    because `completed_tail_label_count=0<10` (accepted
    as valid low-completed-label evidence, not runtime
    failure). 2 h export bundle:
    `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`,
    `manifest_event_count=23001`, `redaction_applied=True`,
    `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`.
  - **W2 — 4 h Long-Window Paper WS Run (PASS):**
    configured `duration_seconds=14400.0`, actual runtime
    ≈ `14417s`, `iterations=237`, `chains_emitted=704`,
    `ws_chains_emitted=704`, `ws_real_transport=True`,
    `ws_reconnect_count=0`, `ws_staleness_ms_max=0`,
    `ws_stale_count=0`, `ingestion_errors=0`,
    `public_endpoint_calls=4226`,
    `ws_messages_received=1324423`,
    `radar_candidates_seen=152221`,
    `candidate_pool_size_max=20`,
    `liquidation_events_seen=4076`,
    `rate_limit_429_count=0`, `rate_limit_418_count=0`,
    `rate_limit_ban=False`, `risk_approved=0`,
    `risk_rejected=704`. 4 h event counts:
    `PAPER_ALPHA_COHORT_EVALUATED=24`,
    `PAPER_ALPHA_GATE_EVALUATED=4`,
    `PAPER_ALPHA_REPORT_GENERATED=4`,
    `PAPER_ALPHA_RULE_EVALUATED=36`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`. 4 h daily
    report: `paper_alpha_gate_status=INCONCLUSIVE`,
    `paper_alpha_gate_sample_count=164`, reason
    `completed_tail_label_count_below_min=2<10`;
    `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
    `regime_cluster_sample_count=164`,
    `regime_cluster_completed_tail_label_count=2`, reason
    `completed_tail_label_count_below_min=2<10` —
    progress from 0 to 2 completed labels still below the
    10-label sufficiency threshold; `INCONCLUSIVE` /
    `INSUFFICIENT_SAMPLE` remained the correct W2 result;
    does **NOT** indicate runtime failure; does **NOT**
    authorise rule relaxation. 4 h export bundle:
    `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`,
    `manifest_event_count=61546`, `redaction_applied=True`,
    `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`.
  - **W3 — 24 h upper-bound run with watcher early-stop
    (PASS):** `total_elapsed_seconds=900`,
    `final_tail_labels_since_start=20`,
    `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`,
    24 h full runtime NOT NEEDED — proves the B-B-B-C
    sample sufficiency protocol can save runtime while
    preserving evidence. W3 safety summary held end-to-end
    (`mode=paper`, `live_trading=False`, `right_tail=False`,
    `llm=False`, `exchange_live_orders=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`,
    `risk_approved=0`, `ingestion_errors=0`,
    `rate_limit_429_count=0`, `rate_limit_418_count=0`,
    `ws_real_transport=True`); watcher logs
    `data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`,
    `data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`.
  - **W3 export evidence (PASS):** latest export zip after
    W3 early-stop
    `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`,
    generated 2026-05-25 12:41 UTC,
    `manifest_event_count=62761`,
    `redaction_applied=True`, `events.jsonl` exists,
    `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`. W3
    export-range event counts: `TAIL_LABEL_ASSIGNED=495`,
    `LABEL_WINDOW_COMPLETED=495`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED=397`,
    `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`,
    `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`,
    `PAPER_ALPHA_GATE_EVALUATED=5`,
    `PAPER_ALPHA_RULE_EVALUATED=45`,
    `PAPER_ALPHA_COHORT_EVALUATED=30`,
    `PAPER_ALPHA_REPORT_GENERATED=5`. **Clarification:**
    `final_tail_labels_since_start=20` is the watcher
    early-stop condition for the 900 s live window;
    `TAIL_LABEL_ASSIGNED=495` is the 24 h export-range
    event count — both valid, different scopes (live-run
    window vs. export-range window). **Do not confuse
    the two numbers.**
  - **Safety boundary held end-to-end** across W1 / W1+
    2 h, W2 4 h, and W3 24 h upper-bound early-stop:
    `mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound,
    Phase 12 stayed **FORBIDDEN**.

This slice exists because PR #57 closeout flipped B-B-B-B
to `ACCEPTED` with
`regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`
(`sample_count=14<20`, `completed_tail_label_count=0<10`)
— **runtime / report / export are correct, but the 10
min observation window is too short to support a Regime /
Cluster right-tail conclusion**. The right next step is
**not** to add a new strategy module, a new AI authority,
or a new optimiser; the right next step is to
**accumulate structural data across longer paper
observation windows** until cohort samples are large
enough for the Regime & Cluster Cohort Evidence Pack and
the Paper Alpha Gate to produce non-`INSUFFICIENT_SAMPLE`
/ non-`INCONCLUSIVE` verdicts that a human can act on as
evidence. This slice codifies that step as a **protocol**
— a long-window paper data-collection cadence (W1 = 1 h,
W2 = 4 h, W3 = 24 h, W4+ multi-day reserved;
**operator-driven; not auto-scheduled**), a sample
sufficiency rule, and cohort stability acceptance
criteria — while keeping all of the Phase 1 safety lock
invariants in force.

> **Phase 11C.1C-C-B-B-B-B acceptance does NOT authorise Phase 11C.1C-C-B-B-B-C kickoff bypassing the standard gate.**
> **Phase 11C.1C-C-B-B-B-C is paper / report / evidence-only.**
> **Phase 11C.1C-C-B-B-B-C grants no trade authority.**
> **Phase 11C.1C-C-B-B-B-C is NOT a strategy implementation.**
> **Phase 11C.1C-C-B-B-B-C is NOT a trading module.**
> **Phase 11C.1C-C-B-B-B-C is NOT a new runtime module.**
> **Phase 11C.1C-C-B-B-B-C is NOT AI Learning.**
> **Phase 11C.1C-C-B-B-B-C is NOT automatic parameter optimisation.**
> **Phase 11C.1C-C-B-B-B-C is NOT reinforcement learning.**
> **Phase 11C.1C-C-B-B-B-C is NOT the complete Strategy Validation Lab follow-up.**
> **Phase 11C.1C-C-B-B-B-C is NOT Phase 12.**
> **Phase 11C.1C-C-B-B-B-C inherits every Phase 1 / 11C.1B / 11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B forbidden item verbatim.**

The full kickoff scope (long-window run cadence,
per-window evidence fields, sample sufficiency principle,
cohort stability principle, allowed outputs, boundary
table, slice-specific forbidden items, and acceptance-gate
placeholder) is recorded in
`docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`
and the kickoff PR description is in
`docs/PR58_DESCRIPTION.md`; the corresponding
`docs/PHASE_GATE.md` *Open phase: Phase 11C.1C-C-B-B-B-C
(NEXT_ALLOWED / NOT_STARTED)* section carries the same
content for the canonical phase ledger.

#### Allowed outputs (docs / evidence templates only)

  - `long_window_run_plan` — operator-facing run plan for
    W1 (1 h) / W2 (4 h) / W3 (24 h); recorded in
    `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`.
  - `sample_sufficiency_checklist` — verbatim checklist
    of `sample_count`, `completed_tail_label_count`,
    `*_status` fields, and `insufficient_sample_reasons`
    that must be captured per window.
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
  - `closeout_acceptance_template` — verbatim shape of
    the docs-only closeout PR that would flip Phase
    11C.1C-C-B-B-B-C to `ACCEPTED` (mirrors the PR #54 /
    PR #57 pattern).

#### Per-window evidence fields the operator must capture verbatim

  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED` count.
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED` count.
  - `PAPER_ALPHA_GATE_EVALUATED` count.
  - `PAPER_ALPHA_RULE_EVALUATED` count.
  - `PAPER_ALPHA_COHORT_EVALUATED` count.
  - `PAPER_ALPHA_REPORT_GENERATED` count.
  - daily report Regime & Cluster section
    (`## Phase 11C.1C-C-B-B-B-B …`).
  - daily report Paper Alpha Gate section
    (`## Phase 11C.1C-C-B-B-B-A …`).
  - `sample_count`.
  - `completed_tail_label_count`.
  - `regime_cluster_evidence_status` (one of
    `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` / `WARNING` /
    `EVIDENCE_SIGNAL`).
  - `paper_alpha_gate_status` (one of `PASS` / `WARN` /
    `FAIL` / `INCONCLUSIVE`).
  - `insufficient_sample_reasons` (verbatim list).
  - Phase 8.5 export package (zip generated, manifest
    event count sane, redaction applied, `events.jsonl`
    exists).
  - export contains `REGIME_CLUSTER_*` events.
  - export contains `PAPER_ALPHA_*` events.
  - safety flags (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no API key, no
    signed endpoint, no private WS, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).

#### Sample sufficiency principle (carries forward verbatim)

  - Low samples cannot output strong conclusions.
  - When `completed_tail_label_count` is below the Regime
    & Cluster Evidence Pack v0 minimum, no Regime /
    Cluster right-tail conclusion is permitted from the
    cohort rows.
  - `INSUFFICIENT_SAMPLE` (Regime & Cluster) and
    `INCONCLUSIVE` (Paper Alpha Gate) are **valid
    outputs, not failures**.
  - Cohort signals are only allowed once samples are
    sufficient.
  - Cohort signals — even when sample-sufficient — remain
    paper-only / report-only / evidence-only.
  - Cohort signals cannot trigger trades, modify
    parameters, relax rules, or enter Phase 12.

#### Cohort stability principle (carries forward verbatim)

  - A signal that appears in one short window and
    disappears in the next is **not** treated as
    evidence.
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

#### Slice-specific forbidden items

This slice carries forward every Phase 1 / 11C.1B /
11C.1C-A / 11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A /
11C.1C-C-B-B-A / 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B
forbidden item verbatim, and adds the following
slice-specific forbidden items:

  - Triggering a real trade.
  - Modifying position size / leverage / stop-loss /
    target price / Risk Engine / Execution FSM.
  - Letting AI / LLM decide direction, position size,
    leverage, stop-loss, target price, or execution.
  - Auto-optimising parameters in response to long-window
    cohort signals.
  - Auto-relaxing rules in response to low-sample windows.
  - Auto-scheduling W1 / W2 / W3 / W4+ runs from runtime
    code.
  - Replacing the Regime & Cluster Cohort Evidence Pack
    v0 `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE` rule
    with a relaxed rule.
  - Implementing the protocol as a new runtime module —
    the slice is intentionally **docs / evidence template
    only** end-to-end.
  - Adding new event types, new Python modules, or new
    runtime behaviour at any point in this slice's
    lifecycle.
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/`.
  - Running tests as part of this kickoff PR.
  - Phase 12 / live trading kickoff.

### Required operator-VPS paper evidence before Phase 11C.1C-C-B-B-B-A closeout `ACCEPTED` — FILED via PR #54

Phase 11C.1C-C-B-B-B-A closeout from
`MERGED / AWAITING_OPERATOR_VPS_EVIDENCE / CLOSEOUT_PENDING`
to `ACCEPTED` required the operator to file the following
**operator-VPS paper evidence** in a separate docs-only
closeout PR (mirroring the PR #36 → PR #37, PR #38 → PR
#39, PR #40 → PR #41, PR #42 → PR #43, PR #44 → PR #50
docs-only closeout pattern). **All required evidence has been
filed via this docs-only closeout PR #54** (see
"Phase 11C.1C-C-B-B-B-A acceptance evidence (operator-VPS
10 min WS paper smoke PASSED + Phase 8.5 export bundle)"
above):

  - `paper_alpha_gate_status` (verbatim from the daily
    report; one of `PASS` / `WARN` / `FAIL` /
    `INCONCLUSIVE`) ✅ filed: `INCONCLUSIVE`
  - `paper_alpha_gate_sample_count` ✅ filed: `20`
  - `PAPER_ALPHA_GATE_EVALUATED` event count ✅ filed: `1`
  - `PAPER_ALPHA_RULE_EVALUATED` event count ✅ filed: `9`
  - `PAPER_ALPHA_COHORT_EVALUATED` event count ✅ filed: `6`
  - `PAPER_ALPHA_REPORT_GENERATED` event count ✅ filed: `1`
  - the daily-report "Phase 11C.1C-C-B-B-B-A Paper Alpha
    Gate v0" section ✅ filed
  - export bundle / replay readability check ✅ filed:
    `data/reports/exports/ama_rt_test_data_1779627957433_export_1.zip`,
    `manifest_event_count=1572`, `redaction_applied=True`,
    `events.jsonl` exists, export contains `PAPER_ALPHA_*`
    events, `EXPORT_PAPER_ALPHA_GATE_CHECK=PASS`
  - safety flags unchanged across the operator-VPS run ✅
    filed (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance API
    key, no Binance API secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound)
  - **Phase 12 remains FORBIDDEN** across the operator-VPS
    run ✅ filed

This docs-only closeout PR #54 is therefore complete; Phase
11C.1C-C-B-B-B-A is now **ACCEPTED**; Phase 11C.1C-C-B-B-B-B
is now **NEXT_ALLOWED / NOT_STARTED**; Phase 12 remains
**FORBIDDEN**.

## Closed phase: Phase 11C.1C-C-B-B-A (acceptance closeout)

**Phase 11C.1C-C-B-B-A — Strategy Validation Dataset Builder
& Quality Gate v0 (PR #44).** Status: **ACCEPTED (closed
2026-05-23; PR #44 merged into `main`, mergeCommit
`3ecfc3b`).** Phase 11C.1C-C-B-B-A shipped the **paper /
report-only first slice** of the deeper Phase 11C.1C-C-B-B
work on top of the Phase 11C.1C-C-B-A
`StrategyValidationSample` / `StrategyValidationReport` /
`ClusterExposureAssessment` artefacts: the dataset record /
dataset / summary / quality-gate v0 contracts + pure builders
+ the runtime hook that emits three new typed events
(`STRATEGY_VALIDATION_DATASET_BUILT`,
`STRATEGY_VALIDATION_DATASET_EXPORTED`,
`STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED`). It does **NOT**
ship the complete Strategy Validation Lab follow-up, the
Paper Alpha Gate v0, AI Learning, automatic parameter
optimisation, reinforcement learning, or richer cluster
heuristics — those are reserved for Phase 11C.1C-C-B-B-B and
now sit at **NEXT_ALLOWED / NOT_STARTED**.

The acceptance evidence is **fully on file**:

  - PR #44 merged into `main` (mergeCommit `3ecfc3b`,
    merged 2026-05-23 UTC).
  - **Strategy Validation Dataset Builder implemented.**
  - **Quality Gate v0 implemented.**
  - **`STRATEGY_VALIDATION_DATASET_BUILT` emitted.**
  - **`STRATEGY_VALIDATION_DATASET_EXPORTED` emitted.**
  - **`STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` emitted.**
  - Targeted tests:
    `tests/unit/test_phase11c_1c_c_b_b_validation_dataset_quality_gate.py`
    **27 / 27 PASS** (brief-mandated cases).
  - Phase 11C focus filter: `tests/unit -k phase11c_`
    **339 / 339 PASS** (312 baseline + 27 new).
  - Full pytest: `tests/` **2313 / 2313 PASS** on the PR
    branch (no regression vs. post-PR-#43 main 2286
    baseline).
  - 30 s dry-run smoke generated the dataset and the
    quality-gate report at
    `data/reports/phase11c/2026-05-23-phase11c-public-market.md`
    with the new "Phase 11C.1C-C-B-B-A Strategy Validation
    Dataset Builder & Quality Gate v0" section:
    `STRATEGY_VALIDATION_DATASET_BUILT=1`,
    `STRATEGY_VALIDATION_DATASET_EXPORTED=1`,
    `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED=1`,
    `validation_dataset_records=2`,
    `validation_dataset_symbols=BTCUSDT,ETHUSDT`,
    `validation_quality_gate_status=fail`,
    `validation_dataset_export_ready=True`,
    `validation_dataset_replay_ready=True`.
  - **`validation_quality_gate_status=fail` is the EXPECTED
    output for the low-sample 30 s dry-run** — the smallest
    Phase 11C.1C-C-A primary tracking window is 5 minutes,
    so samples that landed in the 30 s window are necessarily
    in-flight / unresolved. The quality gate correctly
    classifies the dataset as too thin for downstream
    review — exactly the brief's "empty or low-sample
    quality gate report" requirement.
  - **`validation_quality_gate_status` is descriptive only**
    (`pass` / `warn` / `fail`) and **MUST NEVER trigger a
    real trade**; the Risk Engine remains the single
    trade-decision gate. No module reads `gate_status` to
    drive execution; this is pinned by every quality-gate
    test case.
  - **No live trading.** No `ORDER_*` / `POSITION_*` /
    `STOP_*` / `TELEGRAM_MESSAGE_SENT` / `EXIT_TRIGGERED`
    event was emitted by the dataset / quality-gate slice.
  - **No API key.** No Binance API key / API secret was
    loaded; the runner's `EnvGuard` refuses to boot if any
    forbidden credential env-var is set non-empty.
  - **No private endpoint.** No signed endpoint, no account
    / order / position / leverage / margin endpoint, no
    private WebSocket, no `listenKey`, no DeepSeek trade
    decision, no real Telegram outbound.

Real WS 10 min smoke was **NOT required** for this PR — the
smallest Phase 11C.1C-C-A primary tracking window is 5
minutes and cannot complete in a 30 s dry-run; it is reserved
for Phase 11C.1C-C-B-B-B closeout when non-empty datasets are
first observable end-to-end.

Safety boundary held end-to-end across the Phase 11C.1C-C-B-B-A
acceptance evidence runs:

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

Phase 11C.1C-C-B-B-A acceptance does **NOT** authorise:

  - Phase 11C.1C-C-B-B-B kickoff bypassing the standard gate.
  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting `validation_quality_gate_status` /
    `STRATEGY_VALIDATION_DATASET_*` / any other paper / virtual
    signal to a real-trade authority
  - AI Learning that auto-decides trades
  - automatic parameter optimisation
  - reinforcement learning
  - Paper Alpha Gate v0 (Paper Alpha Gate v0 is NOT
    implemented by Phase 11C.1C-C-B-B-A; it may only start
    as the Phase 11C.1C-C-B-B-B-A child slice after this
    docs-only kickoff and a separate implementation PR;
    Paper Alpha Gate v0 remains paper-only / report-only
    and grants no trade authority)
  - the complete Strategy Validation Lab follow-up

The `validation_quality_gate_status` field on every
`STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` event is one of
`pass` / `warn` / `fail` — paper / report-only descriptive
labels for a human reviewer; **MUST NEVER trigger a real
trade.** The Risk Engine remains the single trade-decision
gate.

See
`docs/PHASE_11C_1C_C_B_B_VALIDATION_DATASET_QUALITY_GATE.md`
for the full Phase 11C.1C-C-B-B-A scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Closed
phase: Phase 11C.1C-C-B-B-A (ACCEPTED)" for the acceptance
gate, and §"Open phase: Phase 11C.1C-C-B-B-B (NEXT_ALLOWED /
NOT_STARTED)" for the inherited boundary table.

## Closed phase: Phase 11C.1C-C-B-A (acceptance closeout)

**Phase 11C.1C-C-B-A — Strategy Validation Lab v0 & Cluster
Exposure Control Contracts (PR #42).** Status: **ACCEPTED
(closed 2026-05-23; PR #42 merged into `main`, mergeCommit
`cc18047`).** Phase 11C.1C-C-B-A shipped the **paper /
report-only first slice** of the deeper Phase 11C.1C-C-B
Strategy Validation Lab work on top of the Phase 11C.1C-C-A
`LabelTrackingRecord` outcomes. It does **NOT** ship the
complete Strategy Validation Lab, AI Learning, automatic
parameter optimisation, reinforcement learning, or richer
cluster heuristics — those are reserved for Phase
11C.1C-C-B-B and now sit at **NEXT_ALLOWED / NOT_STARTED**.

The acceptance gate is **fully on file**:

  - Test ladder green: 25 brief-mandated tests + 312 phase11c
    tests + 2286 full pytest, no regression vs. the
    post-PR-#41 main 2261 baseline.
  - **Operator-VPS 10 min real public WS smoke PASSED** (run
    from a Binance-reachable VPS against commit `0bedcce`):
    `duration_seconds=600.0`, `uptime=611s`, `dry_run=false`,
    `ws_real_transport=true`,
    `ws_messages_received=76324`, `ws_chains_emitted=27`,
    `learning_ready_attached=27`, `snapshots_emitted=27`,
    `ingestion_errors=0`, `HTTP 429 count=0`,
    `HTTP 418 count=0`, `rate_limit_ban=False`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `ws_currently_stale=False`. Authoritative SQLite
    event-count query (captured **after** shutdown flush):
    `STRATEGY_VALIDATION_SAMPLE_CREATED=24`,
    `STRATEGY_VALIDATION_REPORT_GENERATED=1`,
    `STRATEGY_MODE_VALIDATED=4`,
    `CANDIDATE_STAGE_VALIDATED=5`,
    `SCORE_BUCKET_VALIDATED=8`,
    `CLUSTER_EXPOSURE_ASSESSED=1`,
    `CLUSTER_LEADER_VALIDATED=1`. Safety flags unchanged.
  - Daily report contains `"## Phase 11C.1C-C-B-A Strategy
    Validation Lab v0 & Cluster Exposure Control Contracts"`
    with non-empty cohort lines (`strategy_mode=reject n=24`;
    `candidate_stage=early n=24`;
    `opportunity_score_bucket=0-49 n=13` / `50-64 n=11`;
    `early_tail_score_bucket=0-24 n=24`;
    `cluster=USDT size=22 correlated=24 leader=PAXGUSDT action=no_action`);
    `tail_label_distribution = unresolved x 24` (5m primary
    windows still in-flight at the 10 min boundary, as
    expected). Daily-report counter snapshot caveat: top
    event-count lines may show 0 because counters are
    snapshotted before shutdown flush; SQLite query is
    authoritative and confirms emission.
  - Safety boundary held end-to-end: `mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`; no Binance API key,
    no Binance API secret, no signed endpoint, no account /
    order / position / leverage / margin endpoint, no private
    WebSocket, no `listenKey`, no DeepSeek trade decision, no
    real Telegram outbound; Phase 12 remained **FORBIDDEN**.

The Kiro-side sandbox could **not** host the smoke (the same
Binance-region HTTP 451 geoblock recorded under the Phase
11C.1C-B / Phase 11C.1C-C-A closeouts still applies to the
Kiro sandbox), so the operator ran it from a Binance-reachable
VPS and back-filled the verbatim transcript under
`docs/PHASE_GATE.md` §"Phase 11C.1C-C-B-A acceptance evidence
(operator-VPS 10 min real public WS smoke PASSED)". A sandbox
WS smoke would **not** have been authoritative evidence and
was **not** filed as such.

PR #42 has **merged into `main`** (mergeCommit `cc18047`,
merged 2026-05-23 UTC); the smoke evidence above was
accepted; this docs-only closeout PR therefore flips Phase
11C.1C-C-B-A to **ACCEPTED** under `docs/PROJECT_STATUS.md` /
`docs/PHASE_GATE.md` / `docs/CHANGELOG.md`, mirroring the PR
#36 → PR #37, PR #38 → PR #39, and PR #40 → PR #41 closeout
pattern.

Phase 11C.1C-C-B-A acceptance does **NOT** authorise:

  - Phase 11C.1C-C-B-B kickoff bypassing the standard gate.
  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`, the
    seven `STRATEGY_VALIDATION_*` events, validation cohort
    stats, `suggested_cluster_action`) to a real-trade
    authority
  - automatic parameter optimisation that self-modifies the
    runtime configuration
  - reinforcement learning that drives trade decisions
  - AI Learning that auto-decides trades

The `suggested_cluster_action` field on every
`ClusterExposureAssessment` is one of `leader_only` /
`observe_followers` / `reject_cluster` / `no_action` —
paper / report-only labels for a human reviewer; **MUST
NEVER trigger a real trade.** The Risk Engine remains the
single trade-decision gate.

See `docs/PHASE_11C_1C_C_B_STRATEGY_VALIDATION_CLUSTER_CONTROL.md`
for the full Phase 11C.1C-C-B-A scope, boundary, and
forbidden-item list; see `docs/PHASE_GATE.md` §"Phase
11C.1C-C-B-A acceptance evidence (operator-VPS 10 min real
public WS smoke PASSED)" for the verbatim operator-VPS smoke
transcript.

## Closed phase: Phase 11C.1C-C-A (acceptance closeout)

**Phase 11C.1C-C-A — MFE / MAE Label Queue Runtime & Tail
Outcome Tracking (PR #40).** Status: **ACCEPTED (closed
2026-05-23; PR #40 merged into `main`, mergeCommit
`75d3c7c`).** Phase 11C.1C-C-A shipped the **paper-only first
runtime** that consumes the Phase 11C.1C-A
`LABEL_QUEUE_ENQUEUED` contract and produces forward
MFE / MAE / `tail_label` outcomes per ACTIVE candidate over
five tracking windows (5m primary, 15m / 30m / 1h / 4h
secondary). It does **NOT** ship the deeper Strategy
Validation Lab, AI Learning, or Cluster Exposure Control —
those are reserved for Phase 11C.1C-C-B and now sit at
**NEXT_ALLOWED / NOT_STARTED**.

The acceptance gate is **fully on file**:

  - Test ladder green: 30 brief-mandated tests + 287 phase11c
    tests + 2261 full pytest, no regression vs. the
    post-PR-#38 main baseline.
  - **Operator-VPS 10 min real public WS smoke PASSED** (run
    from a Binance-reachable VPS against commit `6d6044d`):
    `dry_run=false`, `ws_real_transport=true`,
    `ws_messages_received=56592`, `ws_chains_emitted=27`,
    `learning_ready_attached=27`, `snapshots_emitted=27`,
    `LABEL_TRACKING_STARTED=19` (runner) / `36` (events.db),
    `LABEL_WINDOW_UPDATED=38` / `82`,
    `LABEL_WINDOW_COMPLETED=11` / `20` (5m primary window
    closed inside the 10 min run), `TAIL_LABEL_ASSIGNED=11`
    / `20`, `MISSED_TAIL_DETECTED=0`,
    `FAKE_BREAKOUT_DETECTED=0`, `pending_label_records=8`,
    `completed_label_records=11`, `expired_label_records=0`,
    `unresolved_label_records=0`, `HTTP 429 count=0`,
    `HTTP 418 count=0`, `rate_limit_ban=False`,
    `ws_reconnect_count=0`, `ws_stale_count=0`,
    `ws_currently_stale=False`, `ingestion_errors=0`,
    safety flags unchanged.
  - Daily report contains `"## Phase 11C.1C-C-A MFE / MAE
    Label Queue Runtime & Tail Outcome Tracking"`.
  - Safety boundary held end-to-end: no API key, no signed
    endpoint, no private WebSocket, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound, Phase
    12 remained **FORBIDDEN**.

The Kiro-side sandbox could **not** host the smoke (the same
Binance-region HTTP 451 geoblock recorded under the Phase
11C.1C-B closeout still applies to the Kiro sandbox), so the
operator ran it from a Binance-reachable VPS and back-filled
the verbatim transcript under `docs/PHASE_GATE.md` §"Phase
11C.1C-C-A acceptance evidence (closeout)". A sandbox WS
smoke would **not** have been authoritative evidence and was
**not** filed as such.

PR #40 has **merged into `main`** (mergeCommit `75d3c7c`,
merged 2026-05-23 UTC); the smoke evidence above was
accepted; this docs-only closeout PR therefore flips Phase
11C.1C-C-A to **ACCEPTED** under `docs/PROJECT_STATUS.md` /
`docs/PHASE_GATE.md` / `docs/CHANGELOG.md`, mirroring the PR
#36 → PR #37 and PR #38 → PR #39 closeout pattern.

Phase 11C.1C-C-A acceptance does **NOT** authorise:

  - Phase 11C.1C-C-B kickoff bypassing the standard gate.
  - live trading
  - Binance API key / secret
  - signed endpoint
  - private websocket
  - listenKey
  - account / order / position / leverage / margin endpoint
  - DeepSeek trade decision
  - real Telegram outbound
  - Phase 12
  - real orders
  - promoting any paper / virtual signal (`strategy_mode`,
    `early_tail_score`, `mfe_pct`, `mae_pct`, `tail_label`,
    `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`) to a
    real-trade authority

See `docs/PHASE_11C_1C_C_MFE_MAE_LABEL_QUEUE_RUNTIME.md` for
the full Phase 11C.1C-C-A scope, boundary, and forbidden-item
list; see `docs/PHASE_GATE.md` §"Phase 11C.1C-C-A acceptance
evidence (closeout)" for the verbatim operator-VPS smoke
transcript.

## Closed phase: Phase 11C.1C-B (acceptance closeout)

**Phase 11C.1C-B — Adaptive Candidate Runtime Calibration &
Early Tail Discovery v0 (PR #38).** Status: **ACCEPTED (closed
2026-05-22; PR #38 merged into `main`, mergeCommit
`ce4b6de`).** Phase 11C.1C-B shipped the **paper-only first
version** of the Adaptive Candidate Runtime Calibration & Early
Tail Discovery layer on top of the Phase 11C.1C-A contracts
(`AdaptiveCandidateContext`, the six adaptive event types,
`MarketRegimeAssessment` / `CandidateStageAssessment` /
`OpportunityScore` / `StrategyModeDecision` / `ClusterContext` /
`LabelQueueContract`). The 30s dry-run + 5min real public WS
smoke evidence captured under `docs/PHASE_GATE.md` §"Phase
11C.1C-B acceptance evidence (closeout)" was accepted; PR #38
has merged into `main`. Every Phase 1 safety flag remained
`False` end-to-end across the acceptance runs. Phase 11C.1C-B
is **NOT** live trading, **NOT** AI Learning, **NOT** complete
Strategy Validation, **NOT** the full MFE/MAE processor — those
are reserved for Phase 11C.1C-C. The Phase 1 safety lock and
every Phase 11C.1B / 11C.1C-A forbidden item carry over
unchanged; Phase 12 (live trading) stays `FORBIDDEN`.

Phase 11C.1C-B shipped:

  - **Runtime calibration metrics** attached to every adaptive
    candidate: `candidate_first_seen_ts`,
    `candidate_first_seen_price`, `current_price`,
    `price_change_since_first_seen`,
    `quote_volume_acceleration_1m`,
    `quote_volume_acceleration_5m`, `price_acceleration_1m`,
    `price_acceleration_5m`, `volume_rank`, `volume_rank_jump_5m`,
    `distance_to_24h_high`, `distance_from_first_seen`,
    `freshness_score`, `late_chase_risk`, `early_tail_score`.
  - **Early Tail Discovery v0.** The candidate pool's capacity
    eviction does NOT discard candidates with high
    `early_tail_score`. The radar surfaces volume-rank jumps,
    quote-volume accelerations, and price accelerations on
    EDEN / ALT / NEAR-style demon-coin starts EARLIER than
    Phase 11C.1B's flat radar score.
  - **Stage calibration.** ``early`` + high volume expansion +
    high freshness MAY enter ``follow`` / ``pullback`` (paper /
    virtual). ``late`` / ``blowoff`` MUST NEVER upgrade to
    ``follow``. ``manipulation_risk`` high MUST ``reject`` or
    ``observe``.
  - **Daily-report enhancements.** New fields:
    `top_early_tail_candidates`, `top_late_chase_risk_candidates`,
    `early_tail_score_top_symbols`,
    `opportunity_score_distribution`,
    `symbols_promoted_before_24h_top_move`, plus EDEN / ALT /
    NEAR style candidate examples when present.
  - **Event / export compatibility.** Every new field lands in
    `EventRepository`, the Phase 8.5 learning-ready payload, the
    daily report, and the Phase 8.5 export. Phase 10A replay
    accepts the new fields without failure.

Phase 11C.1C-B is **paper-mode only**. The new
`early_tail_score` is a descriptive / paper field that protects
a candidate from capacity-driven eviction in the candidate pool
but does NOT authorise opening a real position. The Risk Engine
remains the single trade-decision gate; `stop_unconfirmed=True`
continues to lock the WS-radar chain into the typed-reject path.

> Phase 11C.1C-B specifically does NOT authorise:
>
>   - live trading
>   - Binance API key / secret
>   - signed endpoint
>   - private websocket
>   - listenKey
>   - account / order / position / leverage / margin endpoint
>   - DeepSeek trade decision
>   - real Telegram outbound
>   - Phase 12
>   - AI Learning
>   - the full MFE/MAE processor
>   - real orders
>   - promoting `early_tail_score` / `strategy_mode` to a
>     real-trade authority

See `docs/PHASE_11C_1C_B_RUNTIME_CALIBRATION.md` for the full
runtime-calibration first-version contract; see
`docs/PHASE_GATE.md` §"Phase 11C.1C-B acceptance evidence
(closeout)" for the acceptance smoke evidence numerics.

## Closed phase: Phase 11C.1C-A (acceptance closeout)

**Phase 11C.1C-A — Adaptive Candidate Regime & Strategy Selector
Contracts (PR #36).** Status: **ACCEPTED (closed 2026-05-22; PR
#36 merged; PR #37 docs closeout).** Phase 11C.1C-A shipped the
**paper-only first version** of the data contracts + scoring +
selector + paper-only routing for the Adaptive Candidate Regime &
Strategy Selector. The 30s dry-run + 5min real public WS smoke
evidence captured under `docs/PHASE_GATE.md` §"Phase 11C.1C-A
acceptance evidence" was accepted; PR #36 has merged into
`main`; PR #37 closed out the docs gate. Every Phase 1 safety
flag remained `False` end-to-end across the acceptance runs.
Phase 11C.1C-A is **NOT** live trading, **NOT** AI Learning,
**NOT** complete Strategy Validation, **NOT** the full MFE/MAE
processor — those are reserved for later PRs (Phase 11C.1C-B /
11C.1C-C). The Phase 1 safety lock and every Phase 11C.1B
forbidden item carry over unchanged; Phase 12 (live trading)
stays `FORBIDDEN`.

See `docs/PHASE_11C_1C_ADAPTIVE_CANDIDATE_REGIME_STRATEGY_SELECTOR.md`
for the full first-version contract.

## Phase 11C.1B acceptance evidence (closeout)

Phase 11C.1B closed on **2026-05-22 (UTC)** with the following
evidence on file. Full numerics live in
`docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; this section
is the at-a-glance summary.

### PRs that compose Phase 11C.1B

| PR    | Scope                                                                                                | Status |
| ----- | ---------------------------------------------------------------------------------------------------- | ------ |
| #31   | Phase 11C.1A — Binance Public REST Governor / 429 backoff / 418 shutdown protection                  | merged |
| #32   | Phase 11C.1B PR-B — WebSocket-first all-market radar; real `StdlibPublicWSTransport`; routed `/public/stream` + `/market/stream` | merged |
| #33   | Phase 11C.1B follow-up — fix real WS poll zero-timeout that left `ws_messages_received=0`             | merged |
| #34   | Phase 11C.1B follow-up — `SymbolUniverse` / exchangeInfo-as-truth; non-ASCII contracts admitted; ASCII-only regex banned | merged |

### Real-WS smoke ladder (PASS)

| Smoke run        | Duration | Outcome | Headline metrics                                                                                                              |
| ---------------- | -------- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 5 min real WS    | 5 min    | PASS    | `ws_messages_received=30317`, `ws_chains_emitted=12`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 10 min real WS   | 608 s    | PASS    | `ws_messages_received=59644`, `ws_chains_emitted=27`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 1 h real WS (clean) | 3600 s | PASS    | `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=349134`, `ws_chains_emitted=177`, `ws_learning_ready_attached=177`, `snapshots_emitted=177`, `ingestion_errors=0`, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_staleness_ms_max=0`, `ws_stale_count=0`, `ws_currently_stale=False` |

### Persistence + export evidence

  - `events.db` readable: `events_count=56644`. The event-aggregation
    query passed without traceback.
  - Phase 8.5 export: generated successfully; export files are zip
    archives.
  - Demon-coin discovery sanity: `EDENUSDT` appeared in the radar
    top-symbols list AND in the top event-volume aggregation, which
    is the qualitative evidence that the WS-first all-market radar
    is functioning end-to-end.

### Safety boundary held throughout the Phase 11C.1B acceptance run

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
real private WebSocket          = none (`/private` refused at allowlist)
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

## Phase 11C.1B — what it ships (closeout reference)

PR-B adds three new modules + extends two existing ones:

  - `app/exchanges/binance_public_ws.py` -
    `BinancePublicWSClient` + `WSConfig` + `WSMessage` +
    `WSMessagePump` + `InProcessWSPump` + `_RefusalTransport`
    (default; refuses any real-network call) +
    **`StdlibPublicWSTransport`** (real-network RFC 6455 client
    built on the Python standard library only, route-aware) +
    **`MultiTransportPublicWSManager`** (owns one routed
    `StdlibPublicWSTransport` per route - PUBLIC + MARKET - and
    merges their messages behind a single `WSMessagePump`
    interface) + `create_real_public_ws_transport` factory +
    `classify_stream_route` + `split_streams_by_route` +
    `assert_public_ws_stream_allowed` +
    `assert_public_ws_url_allowed` +
    `assert_public_ws_path_allowed`. Stream allowlist:
    `!ticker@arr`, `!miniTicker@arr`, `!bookTicker`,
    `!markPrice@arr`, `!forceOrder@arr`. Stream-route
    classification: `!bookTicker` is the PUBLIC route;
    `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` /
    `!forceOrder@arr` are the MARKET route. Path-root
    acceptance allowlist: `/public/ws`, `/public/stream`,
    `/market/ws`, `/market/stream` (legacy unrouted `/ws` /
    `/stream` are kept as back-compat for the in-process pump
    fixtures only). Forbidden path roots: `/private`, `/ws-api`,
    `/ws-fapi`, `/ws-papi`, `/trading-api`, `/userDataStream`.
    Host allowlist: `fstream.binance.com`,
    `fstream.binancefuture.com`. The transport refuses every
    credential-shaped kwarg (`api_key` / `api_secret` /
    `listen_key` / `token` / `signature` / `passphrase`) and
    never reads `BINANCE_API_KEY` / `BINANCE_API_SECRET`.
  - `app/market_data_public/radar.py` -
    `AllMarketRadarSnapshot` (frozen pydantic model) +
    `AllMarketRadarBuffer` (per-symbol rolling state) +
    `pre_anomaly_score_light` (pure additive scoring with
    deterministic reason tags).
  - `app/market_data_public/candidate_pool.py` - `CandidatePool`
    with default `candidate_pool_size=20`, `active_detail_limit=3`,
    `candidate_ttl_seconds=900`. Each candidate carries a
    Phase 8.5 `OpportunityIdentity` with
    `source_phase="phase_11c_1b_ws_first_radar"`.
  - `app/market_data_public/ws_radar_chain.py` -
    `WSRadarChainDriver` emits PRE_ANOMALY_DETECTED ->
    ANOMALY_DETECTED -> STATE_TRANSITION (+ Phase 8.5
    LearningReadyContext on each, + RISK_REJECTED via the live
    RiskEngine) per ACTIVE candidate.
  - `app/core/events.py` - three new EventType entries:
    `PUBLIC_WS_CONNECTED`, `PUBLIC_WS_DISCONNECTED`,
    `PUBLIC_WS_STALE`.
  - `app/paper_run/daily_report.py` - `DailyReportSnapshot` +
    `DailyReportBuilder` extended with WS + radar metrics; new
    `Phase 11C.1B WebSocket all-market radar` Markdown section.
  - `scripts/run_public_market_paper.py` - new CLI flags
    `--ws-first` (default ON) / `--ws-disabled` (mutex),
    `--candidate-pool-size`, `--active-detail-limit`,
    `--ws-staleness-threshold-ms`, `--candidate-ttl-seconds`. The
    runner pumps WS -> ingest into radar -> score every snapshot
    -> offer to pool -> expire stale candidates -> drive
    WSRadarChainDriver on the active head (skipped while
    `ws_client.is_stale=True`, the data-degraded gate); the
    active head also receives REST detail through the existing
    PR-A governor.

### Real routed public WS adapter

PR #32 ships the real-network public WebSocket adapter inline.
**`StdlibPublicWSTransport`** is a single-class, stdlib-only RFC
6455 client; **`MultiTransportPublicWSManager`** owns one of those
adapters per route (PUBLIC + MARKET) and presents them behind a
single `WSMessagePump` interface. The pair targets the documented
Binance USDⓈ-M Futures routed endpoints
(`wss://fstream.binance.com/public/stream` and
`wss://fstream.binance.com/market/stream`). The unrouted
`wss://fstream.binance.com/stream?streams=...` path silently
drops market-class streams (per the Binance public-WS reference)
and is therefore NOT the acceptance path; the routed-private
endpoint `wss://fstream.binance.com/private` is forbidden at the
path-root allowlist (`FORBIDDEN_WS_PATH_ROOTS`). The adapter
performs the HTTP/1.1 Upgrade handshake (`GET <route>/stream` with
`Sec-WebSocket-Key` / `Sec-WebSocket-Version: 13`), validates the
server's `Sec-WebSocket-Accept`, parses RFC 6455 text frames, and
surfaces decoded `WSMessage` envelopes. The third-party WebSocket
package deny-list (`websockets` / `websocket-client` / `aiohttp` /
`requests` / `httpx` / `urllib3`) in
`tests/unit/test_phase11c_no_network.py` continues to hold.

The runner refuses to silently fall back to the PR-A
bootstrap-only REST path: `--ws-first` without `--dry-run`
**requires** a real public WS pump. If the factory returns
`None` or raises, the runner exits with `rc=2` and the message
`real public WebSocket transport is required for --ws-first
without --dry-run`. The only path to REST-only operation is the
explicit `--ws-disabled` flag, documented as NOT the Phase 11C.1B
acceptance path.

## Phase 11C.1B execution modes

| CLI                                       | Behaviour                                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `--ws-first --dry-run` (default)          | In-process pump, deterministic synthetic messages, no socket, full event chain.                                        |
| `--ws-first` (no `--dry-run`)             | Real `MultiTransportPublicWSManager` opening routed PUBLIC (`/public/stream`) + MARKET (`/market/stream`) endpoints. RC=2 if the factory cannot produce one - never silently falls back to REST. |
| `--ws-disabled`                           | PR-A bootstrap-only REST path. Documented as **not** the Phase 11C.1B all-market demon-radar acceptance path.          |


## Architecture governance (guidance-only)

A new architecture governance document has been added to the
repository:

  - `docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md` —
    *AMA-RT Adaptive Market Operating System Governance /
    自适应市场操作系统架构治理文档.*

This document is **guidance-only**. It records the long-term
architectural rails of AMA-RT: core positioning ("AMA-RT is
not an auto-trading bot, AMA-RT is an Adaptive Market
Operating System"), AI authority boundaries (LLMs may explain,
LLMs may **not** trade / size / leverage / stop / target),
stateless AI cognition, the Truth Layer, the Reality Check
Layer, anti-overfitting governance, feedback isolation, the
nine-layer architecture, the not-implemented-yet backlog, and
the explicit rejections list (incl. AI autonomous trading,
direct price prediction, RL live trading, black-box parameter
optimisation, AI bypassing the Risk Engine, direct Phase 12
jump).

The governance document **does NOT**:

  - change the current phase,
  - flip any safety flag,
  - authorise any runtime behavior,
  - authorise live trading, API keys, signed endpoints,
    private WebSockets, `listenKey`, DeepSeek trade
    decisions, or real Telegram outbound,
  - advance any later phase to ACCEPTED,
  - kick off Phase 11C.1C-C-B-B-B,
  - authorise Phase 12.

Current phase is now **Phase 11C.1C-C-B-B-B**
(NEXT_ALLOWED / NOT_STARTED) per `docs/PHASE_GATE.md`. Phase
11C.1C-C-B-B-A is **ACCEPTED** (PR #44 merged into `main`,
mergeCommit `3ecfc3b`, 2026-05-23 UTC); current work focus
remains *validation / dataset / quality gate / replay
verification*, and **Phase 12 (real money / live trading)
remains FORBIDDEN**. The Phase 1 safety lock continues to
hold: `mode=paper`, `live_trading=False`, `right_tail=False`,
`llm=False`, `exchange_live_orders=False`,
`telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no
Binance API secret, no signed endpoint, no private WebSocket,
no `listenKey`, no DeepSeek trade decision, no real Telegram
outbound.
