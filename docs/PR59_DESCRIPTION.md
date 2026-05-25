# PR #59 — Phase 11C.1C-C-B-B-B-C Docs Closeout

> **Type: Docs-only closeout / acceptance flip.**
> **Runtime effect: none.**
> **Phase ledger effect:** flips Phase 11C.1C-C-B-B-B-C
> from `NEXT_ALLOWED / NOT_STARTED` (defined in place by
> PR #58 docs-only kickoff) to `ACCEPTED` on the basis of
> the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3 24 h
> upper-bound early-stop paper WS evidence; introduces
> Phase 11C.1C-C-B-B-B-D as `NEXT_ALLOWED / NOT_STARTED`
> (placeholder; not yet defined). **No new runtime feature
> is authorised by this PR.**
> **Safety flag effect: none.**
> **Trade authority granted: none.**
>
> **This PR is paper / report / evidence only.** **NOT**
> live trading. **NOT** AI Learning. **NOT** automatic
> parameter optimisation. **NOT** reinforcement learning.
> **NOT** the complete Strategy Validation Lab follow-up.
> **NOT** Phase 11C.1C-C-B-B-B-D implementation. **NOT**
> Phase 12.
>
> The Risk Engine remains the single trade-decision gate.
> The Long-Window Cohort Stability & Sample Sufficiency
> Protocol v0 outputs (`long_window_run_plan`,
> `sample_sufficiency_checklist`,
> `cohort_stability_checklist`,
> `operator_vps_evidence_template`,
> `export_replay_evidence_template`,
> `closeout_acceptance_template`) and the per-window
> outputs consumed by this protocol (`paper_alpha_gate_status`,
> `regime_cluster_evidence_status`,
> `insufficient_sample_reasons`, daily-report Paper Alpha
> Gate section, daily-report Regime & Cluster Cohort
> Evidence Pack section, `PAPER_ALPHA_*` and
> `REGIME_CLUSTER_*` event counts, Phase 8.5 export
> bundles) are **descriptive labels / artefacts** for
> human review and **MUST NEVER trigger a real trade**,
> **MUST NEVER** modify position size, leverage,
> stop-loss, target price, the Risk Engine, or the
> Execution FSM. **Long-window protocol outputs and
> per-window outputs remain paper-only / report-only /
> evidence-only.** **Long-window protocol outputs and
> per-window outputs cannot trigger orders, leverage,
> position sizing, stop changes, target changes, Risk
> Engine changes, or Execution FSM changes.**

## What this PR does

This is the docs-only closeout PR for Phase
11C.1C-C-B-B-B-C (Long-Window Cohort Stability & Sample
Sufficiency Protocol v0 / *长窗口 Cohort 稳定性与样本充足
协议 v0*). It records the **operator-VPS W1 / W1+ 2 h, W2
4 h, and W3 24 h upper-bound early-stop paper WS
evidence** required to flip Phase 11C.1C-C-B-B-B-C from
`NEXT_ALLOWED / NOT_STARTED` (defined in place by PR #58
docs-only kickoff) to `ACCEPTED`, mirroring the PR #36 →
PR #37, PR #38 → PR #39, PR #40 → PR #41, PR #42 → PR
#43, PR #44 → PR #50, PR #52 → PR #54, and PR #56 → PR
#57 docs-only closeout pattern.

PR #58 was the docs-only kickoff for B-B-B-C; this PR (PR
#59) records the long-window paper evidence and flips the
slice to `ACCEPTED`. **No implementation PR exists or is
authored under this slice** — the slice is intentionally
**docs / evidence-template only** end-to-end (it consumed
the existing Regime & Cluster Cohort Evidence Pack v0 and
Paper Alpha Gate v0 runtime + daily-report + Phase 8.5
export pipeline).

## Phase

  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 merged
    into `main`, 2026-05-23, mergeCommit `3ecfc3b`).
  - **Phase 11C.1C-C-B-A** — `ACCEPTED` (PR #42 merged
    into `main`, 2026-05-23, mergeCommit `cc18047`).
  - **Phase 11C.1C-C-A** — `ACCEPTED` (PR #40 merged into
    `main`, 2026-05-23, mergeCommit `75d3c7c`).
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED /
    NOT_STARTED`. *Parent* phase. Strategy Validation Lab
    (deeper) & richer Cluster Exposure Control follow-up.
    **Not renamed by this PR.**
  - **Phase 11C.1C-C-B-B-B-A** — `ACCEPTED` (PR #52
    merged into `main`, 2026-05-24, mergeCommit
    `f8ba315`; closeout via PR #54). First child slice.
    Paper Alpha Gate v0.
  - **Phase 11C.1C-C-B-B-B-B** — `ACCEPTED` (PR #56
    merged into `main`, 2026-05-24, mergeCommit
    `1a9abe2`; closeout via PR #57). Second child slice.
    Regime & Cluster Cohort Evidence Pack v0.
  - **Phase 11C.1C-C-B-B-B-C** — *flipped to `ACCEPTED`
    by this PR*. PR #58 docs-only kickoff merged into
    `main` on 2026-05-25; this docs-only closeout PR #59
    records the operator-VPS W1 / W1+ 2 h, W2 4 h, and W3
    24 h upper-bound early-stop paper WS evidence and
    flips the slice to `ACCEPTED`. Third child slice
    under Phase 11C.1C-C-B-B-B. Long-Window Cohort
    Stability & Sample Sufficiency Protocol v0 / 长窗口
    Cohort 稳定性与样本充足协议 v0. Docs / evidence-
    template only. No new runtime module. No trade
    authority.
  - **Phase 11C.1C-C-B-B-B-D** — `NEXT_ALLOWED /
    NOT_STARTED` (placeholder; not yet defined). Will
    require its own kickoff PR, brief, scope, boundary
    table, forbidden list, and acceptance evidence.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Branch & merge

  - Branch:
    `docs/phase-11c1c-c-b-b-b-c-long-window-cohort-stability-closeout`.
  - Target: `main`.
  - Status: open for review (this PR; docs-only closeout).

## Changed files

```
docs/PROJECT_STATUS.md                                                 (modified — docs-only)
docs/PHASE_GATE.md                                                     (modified — docs-only)
docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md            (modified — docs-only)
docs/CHANGELOG.md                                                      (modified — docs-only)
docs/PR59_DESCRIPTION.md                                               (NEW)
```

No file under `app/`, `scripts/`, `tests/`, `configs/`,
`risk/`, `execution/`, `llm/`, `telegram/`, or `exchange/`
is touched.

## Acceptance evidence (recorded by this PR)

### W1 / W1+ — 2 h Long-Window Paper WS Run (PASS)

  - `duration_seconds = 7200.0`
  - `uptime ≈ 7238s`
  - `ws_first = true`
  - `ws_real_transport = true`
  - `ingestion_errors = 0`
  - `HTTP 429 = 0`
  - `HTTP 418 = 0`
  - `risk_approved = 0`
  - live trading disabled

#### W1 / W1+ 2 h event counts

  - `PAPER_ALPHA_COHORT_EVALUATED = 18`
  - `PAPER_ALPHA_GATE_EVALUATED = 3`
  - `PAPER_ALPHA_REPORT_GENERATED = 3`
  - `PAPER_ALPHA_RULE_EVALUATED = 27`
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 10`
  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = 2`

#### W1 / W1+ 2 h Daily report

  - Paper Alpha Gate section exists.
  - Regime & Cluster Cohort Evidence Pack section exists.
  - Regime / cluster `sample_count = 189`.
  - Regime / cluster `completed_tail_label_count = 0`.
  - Status remained `INSUFFICIENT_SAMPLE` /
    `INCONCLUSIVE` because
    `completed_tail_label_count=0<10`.
  - Accepted as **valid low-completed-label evidence**,
    not runtime failure.

#### W1 / W1+ 2 h Export evidence

  - `export_test_data = OK`
  - export zip path:
    `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`
  - `manifest_event_count = 23001`
  - `redaction_applied = True`
  - `events.jsonl` exists.
  - `EXPORT_LONG_WINDOW_W1_2H_CHECK = PASS`.

### W2 — 4 h Long-Window Paper WS Run (PASS)

  - configured `duration_seconds = 14400.0`.
  - actual runtime ≈ `14417s`.
  - `iterations = 237`.
  - `chains_emitted = 704`.
  - `ws_chains_emitted = 704`.
  - `ws_real_transport = True`.
  - `ws_reconnect_count = 0`.
  - `ws_staleness_ms_max = 0`.
  - `ws_stale_count = 0`.
  - `ingestion_errors = 0`.
  - `public_endpoint_calls = 4226`.
  - `ws_messages_received = 1324423`.
  - `radar_candidates_seen = 152221`.
  - `candidate_pool_size_max = 20`.
  - `liquidation_events_seen = 4076`.
  - `rate_limit_429_count = 0`.
  - `rate_limit_418_count = 0`.
  - `rate_limit_ban = False`.
  - `risk_approved = 0`.
  - `risk_rejected = 704`.

#### W2 4 h event counts

  - `PAPER_ALPHA_COHORT_EVALUATED = 24`
  - `PAPER_ALPHA_GATE_EVALUATED = 4`
  - `PAPER_ALPHA_REPORT_GENERATED = 4`
  - `PAPER_ALPHA_RULE_EVALUATED = 36`
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 15`
  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = 3`

#### W2 4 h Daily report

  - `paper_alpha_gate_status = INCONCLUSIVE`.
  - `paper_alpha_gate_sample_count = 164`.
  - reason: `completed_tail_label_count_below_min=2<10`.
  - `regime_cluster_evidence_status = INSUFFICIENT_SAMPLE`.
  - Regime / cluster `sample_count = 164`.
  - Regime / cluster `completed_tail_label_count = 2`.
  - reason: `completed_tail_label_count_below_min=2<10`.

#### Important interpretation of W2

  - 4 h showed **progress** from `0` completed labels to
    `2` completed labels.
  - Still below the `10` completed-tail-label sufficiency
    threshold.
  - Therefore `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE`
    remained the **correct** result for W2.
  - This does **NOT** indicate runtime failure.
  - This does **NOT** authorise rule relaxation.

#### W2 4 h Export evidence

  - `export_test_data = OK`.
  - export zip path:
    `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`.
  - `manifest_event_count = 61546`.
  - `redaction_applied = True`.
  - `EXPORT_LONG_WINDOW_W2_4H_CHECK = PASS`.

### W3 — 24 h upper-bound run with watcher early-stop (PASS)

  - W3 was started as a **24 h upper-bound** paper WS
    run.
  - A watcher stopped the run early when tail-label
    sufficiency was reached.
  - `total_elapsed_seconds = 900`.
  - `final_tail_labels_since_start = 20`.
  - `SAMPLE_SUFFICIENCY_REACHED = final_tail_labels=20>=10`.
  - Early-stop condition triggered successfully.
  - 24 h full runtime was **NOT NEEDED**.
  - **This proves the B-B-B-C sample sufficiency protocol
    can save runtime while preserving evidence.**

#### W3 run safety summary (held end-to-end across the 900 s window)

  - `mode = paper`.
  - `live_trading = False`.
  - `right_tail = False`.
  - `llm = False`.
  - `exchange_live_orders = False`.
  - `telegram_outbound_enabled = False`.
  - `binance_private_api_enabled = False`.
  - `risk_approved = 0`.
  - `ingestion_errors = 0`.
  - `rate_limit_429_count = 0`.
  - `rate_limit_418_count = 0`.
  - `ws_real_transport = True`.

#### W3 watcher logs (filenames as recorded by the operator)

  - `run_log = data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`.
  - `watch_log = data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`.

### W3 export evidence (PASS)

  - latest export zip generated after W3 early-stop:
    `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`.
  - generated at 2026-05-25 12:41 UTC.
  - `manifest_event_count = 62761`.
  - `redaction_applied = True`.
  - `events.jsonl` exists.
  - `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK = PASS`.

#### W3 export event counts (export-range, full 24 h export window)

  - `TAIL_LABEL_ASSIGNED = 495`.
  - `LABEL_WINDOW_COMPLETED = 495`.
  - `STRATEGY_VALIDATION_SAMPLE_CREATED = 397`.
  - `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED = 4`.
  - `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED = 20`.
  - `PAPER_ALPHA_GATE_EVALUATED = 5`.
  - `PAPER_ALPHA_RULE_EVALUATED = 45`.
  - `PAPER_ALPHA_COHORT_EVALUATED = 30`.
  - `PAPER_ALPHA_REPORT_GENERATED = 5`.

#### Clarification on the two W3 numbers

  - `final_tail_labels_since_start = 20` is the **watcher
    early-stop condition** for this W3 run — it counts
    the tail labels that completed during the **900 s**
    window the operator actually ran, and it is the
    threshold against which the watcher decided to stop
    early.
  - `TAIL_LABEL_ASSIGNED = 495` is the **24 h
    export-range event count** captured from the Phase
    8.5 export bundle — it counts tail labels assigned
    across the **full 24 h export window** (which
    includes pre-existing events.db-resident tail-label
    records that the export range covers, not just the
    900 s that the runner was live for).
  - **Do not confuse the two numbers.**
  - Both are valid; they represent different scopes
    (live-run window vs. export-range window).

## Closeout interpretation (must be read verbatim)

  - **B-B-B-C acceptance is acceptance of the long-window
    data collection and sample-sufficiency protocol.**
  - It does **NOT** mean any Regime / Cluster has proven
    right-tail advantage yet.
  - It does **NOT** mean strategy effectiveness is proven.
  - It does **NOT** authorise live trading.
  - It does **NOT** authorise Phase 12.
  - It does **NOT** authorise rule relaxation based on low
    samples.
  - It does **NOT** authorise automatic parameter
    optimisation.
  - It does **NOT** authorise AI Learning.
  - It does **NOT** authorise reinforcement learning.
  - It does **NOT** authorise changing the Risk Engine or
    the Execution FSM.
  - It does **NOT** authorise Phase 11C.1C-C-B-B-B-D
    kickoff bypassing the standard gate.
  - It records that:
      - 2 h paper WS run works.
      - 4 h paper WS run works.
      - completed labels begin to appear over longer
        windows.
      - 24 h upper-bound early-stop works.
      - completed-tail-label sufficiency threshold can be
        reached early.
      - export / replay evidence preserves the results.
      - low-sample states remain conservative
        (`INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` are valid
        outputs not failures).
      - no trade authority was granted by any window.

## Safety boundary held end-to-end across W1 / W1+ 2 h, W2 4 h, and W3 24 h upper-bound early-stop runs

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

## Phase 11C.1C-C-B-B-B-C acceptance does NOT authorise

  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise live trading.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise API keys.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise private endpoints.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise DeepSeek trade decisions.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise real Telegram outbound.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise Phase 12.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise automatic parameter optimisation.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise AI Learning.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise reinforcement learning.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise rule relaxation based on low samples.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise changing the Risk Engine or the Execution
    FSM.
  - Phase 11C.1C-C-B-B-B-C acceptance does **NOT**
    authorise Phase 11C.1C-C-B-B-B-D kickoff bypassing
    the standard gate.
  - Long-window protocol outputs and per-window outputs
    remain paper-only / report-only / evidence-only.
  - Long-window protocol outputs and per-window outputs
    cannot trigger orders, leverage, position sizing,
    stop changes, target changes, Risk Engine changes, or
    Execution FSM changes.

## Forbidden by this PR (carries forward verbatim)

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
  - Modifying `app/`, `scripts/`, `tests/`, `configs/`,
    `risk/`, `execution/`, `llm/`, `telegram/`, or
    `exchange/`.
  - Modifying configuration schemas, defaults, or YAML.
  - Modifying strategy runtime code.
  - Adding or modifying tests.
  - Adding new Python modules.
  - Adding new event types.
  - Modifying runtime behavior.
  - Implementing new functionality.
  - Phase 11C.1C-C-B-B-B-D implementation (reserved for
    the next child slice; will require its own kickoff
    PR, brief, scope, boundary table, forbidden list, and
    acceptance evidence).
  - Phase 11C.1C-C-B-B-B-D kickoff bypassing the standard
    gate.
  - Phase 12 / live trading kickoff.

## Allowed file edits

  - `docs/PROJECT_STATUS.md`
  - `docs/PHASE_GATE.md`
  - `docs/CHANGELOG.md`
  - `docs/PHASE_11C_1C_C_B_B_B_C_LONG_WINDOW_COHORT_STABILITY.md`
  - `docs/PR58_DESCRIPTION.md` (exists; not modified by
    this PR)
  - `docs/PR59_DESCRIPTION.md` (NEW; this document)

## Acceptance gate (docs-only closeout)

  - Docs-only PR. **No code modified** under `app/`,
    `scripts/`, `tests/`, `configs/`, `risk/`,
    `execution/`, `llm/`, `telegram/`, or `exchange/`.
  - **No new Python files.**
  - **No new event types.**
  - **No new tests.**
  - **No tests run.**
  - **No dry-run / smoke required** by this PR (the
    operator-VPS W1 / W1+ 2 h, W2 4 h, W3 24 h
    upper-bound early-stop paper WS evidence was captured
    pre-PR; this PR **records** the evidence in the
    ledger).
  - Phase 11C.1C-C-B-B-B-C flipped to `ACCEPTED`.
  - Phase 11C.1C-C-B-B-B-D introduced at `NEXT_ALLOWED /
    NOT_STARTED`.
  - Safety boundary held end-to-end (`mode=paper`,
    `live_trading=False`, `exchange_live_orders=False`,
    `right_tail=False`, `llm=False`,
    `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no API key, no
    signed endpoint, no private WS, no `listenKey`, no
    DeepSeek trade decision, no real Telegram outbound).
  - **Phase 12 remains FORBIDDEN.**

## Reviewer checklist

  - [ ] **Confirm docs-only.** Only files under `docs/`
        are modified. Verify with `git diff --stat`.
  - [ ] **Confirm no `app/` / `scripts/` / `tests/` /
        `configs/` changes.**
  - [ ] **Confirm no `execution/` / `risk/` / `llm/` /
        `telegram/` / `exchange/` changes.**
  - [ ] **Confirm no strategy runtime code changes.**
  - [ ] **Confirm Phase 11C.1C-C-B-B-B-C = ACCEPTED.**
  - [ ] **Confirm Phase 11C.1C-C-B-B-B-D = NEXT_ALLOWED /
        NOT_STARTED.**
  - [ ] **Confirm Phase 12 = FORBIDDEN.**
  - [ ] **Confirm no runtime behavior changed.**
  - [ ] **Confirm no live trading.**
  - [ ] **Confirm no API key.**
  - [ ] **Confirm no private endpoint.**
  - [ ] **Confirm no DeepSeek trade decision.**
  - [ ] **Confirm no real Telegram outbound.**
  - [ ] **Confirm no tests run.**
  - [ ] **Confirm W1 / W1+ 2 h paper WS run evidence is
        recorded verbatim** (`duration_seconds=7200.0`,
        `uptime≈7238s`, `ws_first=true`,
        `ws_real_transport=true`, `ingestion_errors=0`,
        `HTTP 429=0`, `HTTP 418=0`, `risk_approved=0`,
        live trading disabled; 2 h event counts
        `PAPER_ALPHA_COHORT_EVALUATED=18`,
        `PAPER_ALPHA_GATE_EVALUATED=3`,
        `PAPER_ALPHA_REPORT_GENERATED=3`,
        `PAPER_ALPHA_RULE_EVALUATED=27`,
        `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=10`,
        `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=2`; daily
        report `regime_cluster_sample_count=189`,
        `completed_tail_label_count=0`, status remained
        `INSUFFICIENT_SAMPLE` / `INCONCLUSIVE` because
        `completed_tail_label_count=0<10`; 2 h export
        `data/reports/exports/ama_rt_test_data_1779693570447_export_d.zip`,
        `manifest_event_count=23001`,
        `redaction_applied=True`,
        `EXPORT_LONG_WINDOW_W1_2H_CHECK=PASS`).
  - [ ] **Confirm W2 4 h paper WS run evidence is recorded
        verbatim** (configured `duration_seconds=14400.0`,
        actual runtime ≈ `14417s`, `iterations=237`,
        `chains_emitted=704`, `ws_chains_emitted=704`,
        `ws_real_transport=True`, `ws_reconnect_count=0`,
        `ws_staleness_ms_max=0`, `ws_stale_count=0`,
        `ingestion_errors=0`,
        `public_endpoint_calls=4226`,
        `ws_messages_received=1324423`,
        `radar_candidates_seen=152221`,
        `candidate_pool_size_max=20`,
        `liquidation_events_seen=4076`,
        `rate_limit_429_count=0`,
        `rate_limit_418_count=0`,
        `rate_limit_ban=False`, `risk_approved=0`,
        `risk_rejected=704`; 4 h event counts
        `PAPER_ALPHA_COHORT_EVALUATED=24`,
        `PAPER_ALPHA_GATE_EVALUATED=4`,
        `PAPER_ALPHA_REPORT_GENERATED=4`,
        `PAPER_ALPHA_RULE_EVALUATED=36`,
        `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=15`,
        `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=3`; daily
        report `paper_alpha_gate_status=INCONCLUSIVE`,
        `paper_alpha_gate_sample_count=164`, reason
        `completed_tail_label_count_below_min=2<10`;
        `regime_cluster_evidence_status=INSUFFICIENT_SAMPLE`,
        `sample_count=164`,
        `completed_tail_label_count=2`, reason
        `completed_tail_label_count_below_min=2<10`; 4 h
        export
        `data/reports/exports/ama_rt_test_data_1779708773055_export_8.zip`,
        `manifest_event_count=61546`,
        `redaction_applied=True`,
        `EXPORT_LONG_WINDOW_W2_4H_CHECK=PASS`).
  - [ ] **Confirm W2 progress 0 → 2 completed labels is
        correctly explained as expected progress, still
        below the 10-label sufficiency threshold,
        therefore `INCONCLUSIVE` / `INSUFFICIENT_SAMPLE`
        remained the correct W2 result; does NOT indicate
        runtime failure; does NOT authorise rule
        relaxation.**
  - [ ] **Confirm W3 24 h upper-bound watcher early-stop
        evidence is recorded verbatim**
        (`total_elapsed_seconds=900`,
        `final_tail_labels_since_start=20`,
        `SAMPLE_SUFFICIENCY_REACHED=final_tail_labels=20>=10`,
        24 h full runtime NOT NEEDED, safety summary held
        end-to-end across the 900 s window, watcher logs
        `data/logs/pr58_w3_24h_ws_2026-05-25T11:56:10Z.log`
        and
        `data/logs/pr58_w3_24h_watch_2026-05-25T11:56:10Z.log`).
  - [ ] **Confirm W3 export evidence is recorded verbatim**
        (latest export zip after W3 early-stop
        `data/reports/exports/ama_rt_test_data_1779712866542_export_6.zip`,
        generated 2026-05-25 12:41 UTC,
        `manifest_event_count=62761`,
        `redaction_applied=True`, `events.jsonl` exists,
        `EXPORT_LONG_WINDOW_W3_EARLY_STOP_CHECK=PASS`; W3
        export-range event counts
        `TAIL_LABEL_ASSIGNED=495`,
        `LABEL_WINDOW_COMPLETED=495`,
        `STRATEGY_VALIDATION_SAMPLE_CREATED=397`,
        `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED=4`,
        `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED=20`,
        `PAPER_ALPHA_GATE_EVALUATED=5`,
        `PAPER_ALPHA_RULE_EVALUATED=45`,
        `PAPER_ALPHA_COHORT_EVALUATED=30`,
        `PAPER_ALPHA_REPORT_GENERATED=5`).
  - [ ] **Confirm the clarification of the two W3 numbers
        is recorded verbatim** —
        `final_tail_labels_since_start=20` is the watcher
        early-stop condition for the 900 s live window;
        `TAIL_LABEL_ASSIGNED=495` is the 24 h
        export-range event count; both valid, different
        scopes.
  - [ ] **Confirm B-B-B-C acceptance is correctly
        explained as acceptance of the long-window data
        collection and sample-sufficiency protocol** —
        does NOT mean any Regime / Cluster has proven
        right-tail advantage yet, does NOT mean strategy
        effectiveness is proven, does NOT authorise live
        trading, does NOT authorise rule relaxation
        based on low samples, does NOT authorise
        automatic parameter optimisation, does NOT
        authorise AI Learning, does NOT authorise
        changing the Risk Engine or the Execution FSM,
        does NOT authorise Phase 12; records only that
        2 h works, 4 h works, completed labels begin to
        appear over longer windows, 24 h upper-bound
        early-stop works, completed-tail-label
        sufficiency threshold can be reached early,
        export / replay evidence preserves the results,
        low-sample states remain conservative, no trade
        authority granted.
  - [ ] **Confirm Phase 1 safety lock unchanged
        end-to-end** (`mode=paper`, `live_trading=False`,
        `exchange_live_orders=False`, `right_tail=False`,
        `llm=False`, `telegram_outbound_enabled=False`,
        `binance_private_api_enabled=False`, no Binance
        API key, no Binance API secret, no signed
        endpoint, no account / order / position /
        leverage / margin endpoint, no private WebSocket,
        no `listenKey`, no DeepSeek trade decision, no
        real Telegram outbound).
