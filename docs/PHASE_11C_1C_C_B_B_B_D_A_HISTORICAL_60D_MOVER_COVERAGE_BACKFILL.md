# Phase 11C.1C-C-B-B-B-D-A — Historical 60D Mover Coverage Backfill Audit v0

> **Chinese name / 中文名:** *历史 60 天异动币覆盖回填审计 v0*.
>
> **Status: NEXT_ALLOWED / NOT_STARTED (defined in place
> by this docs-only kickoff PR #63; this PR scopes the
> slice; it does not flip its state).** This document
> opens Phase 11C.1C-C-B-B-B-D-A as the **next allowed
> child slice** under the Phase 11C.1C-C-B-B-B parent
> (*Strategy Validation Lab (deeper) & richer Cluster
> Exposure Control follow-up*) and on top of the
> `ACCEPTED` Phase 11C.1C-C-B-B-B-D (*Mover Capture
> Recall & Missed-Tail Coverage Audit v0 / 异动币捕捉召
> 回与漏捕右尾覆盖审计 v0*). The parent phase is **not**
> renamed; it keeps its existing definition. Phase
> 11C.1C-C-B-B-B-A (*Paper Alpha Gate v0*) remains
> `ACCEPTED` (PR #52 + PR #54 closeout). Phase
> 11C.1C-C-B-B-B-B (*Regime & Cluster Cohort Evidence
> Pack v0*) remains `ACCEPTED` (PR #56 + PR #57
> closeout). Phase 11C.1C-C-B-B-B-C (*Long-Window Cohort
> Stability & Sample Sufficiency Protocol v0*) remains
> `ACCEPTED` (PR #58 docs-only kickoff + PR #59 docs-only
> closeout). Phase 11C.1C-C-B-B-B-D (*Mover Capture
> Recall & Missed-Tail Coverage Audit v0*) remains
> `ACCEPTED` (PR #60 docs-only kickoff + PR #61
> implementation + PR #62 docs-only closeout).
>
> Paper / report / evidence only. **NOT** live trading.
> **NOT** AI Learning. **NOT** automatic parameter
> optimisation. **NOT** reinforcement learning. **NOT** a
> new strategy. **NOT** a trading module. **NOT** a new
> runtime module. **NOT** the complete Strategy Validation
> Lab follow-up. **NOT** a Historical 30D+ / 60D *complete
> strategy* blind replay / walk-forward validation gate
> (that gate is reserved until small-money live trading
> prep and is **not** in scope here). **NOT** the Phase
> 11C.1C-C-B-B-B-D-A *implementation* (the implementation,
> if any, requires a separate PR cycle). **NOT** the Phase
> 11C.1C-C-B-B-B-D-A *closeout* (the closeout will be a
> separate docs-only PR after the operator captures the
> backfill audit evidence). **NOT** Phase 12.
>
> The Risk Engine remains the single trade-decision gate.
> Every artefact this slice defines (60D top-mover
> reference sets, per-mover capture-path evidence rows,
> miss-reason summaries, first-seen latency summaries,
> capture recall rates, coverage warnings,
> insufficient-coverage reasons, evidence templates) is a
> **descriptive document / evidence template** for human
> review and **MUST NEVER trigger a real trade**, **MUST
> NEVER** modify position size, leverage, stop-loss,
> target price, the Risk Engine, the Execution FSM,
> `symbol_limit`, the candidate pool capacity, anomaly
> thresholds, or Regime weights.

## Phase 11C.1C-C-B-B-B-D-A.1 — Historical 60D Mover Reference Store Builder v0 (PR #65)

> **Status: DATA-PREPARATION CHILD TASK (PR #65).** Phase
> 11C.1C-C-B-B-B-D-A.1 is the small, public-data-only data
> preparation step under `IN_REVIEW` Phase 11C.1C-C-B-B-B-D-A.
> It ships
> `scripts/build_historical_mover_reference_store.py` — a
> minimal builder that produces the
> `data/historical_market_store/` artefacts the audit's
> `load_historical_market_store(...)` consumes today.
> Paper / report / evidence only. **NOT** strategy blind
> replay; **NOT** PnL backtest; **NOT** trading module;
> **NOT** AI Learning; **NOT** automatic parameter
> optimisation; **NOT** reinforcement learning; **NOT** the
> small-money live-trading pre-validation gate; **NOT** the
> Phase 11C.1C-C-B-B-B-D-A *closeout*; **NOT** Phase 12. The
> Risk Engine remains the single trade-decision gate.
>
> **Scope of PR #65:**
>
>   - New script `scripts/build_historical_mover_reference_store.py`.
>   - Public-only data source
>     (`BinanceFuturesPublicSource`) reusing the Phase 11C
>     allowlist (`assert_public_endpoint_allowed`); refuses
>     every credential-shaped kwarg + every signed-request
>     query parameter; refuses to start when any of
>     `BINANCE_API_KEY` / `BINANCE_API_SECRET` / `BINANCE_KEY`
>     / `BINANCE_SECRET` / `BINANCE_TOKEN` /
>     `BINANCE_PASSPHRASE` is set.
>   - CLI flags: `--days`, `--timeframe`, `--top-n`,
>     `--symbol-limit`, `--output-dir`, `--rest-base-url`,
>     `--audit-window-end-utc-ms`,
>     `--request-sleep-seconds`, `--dry-run`,
>     `--no-network` (alias `--no-network-test-mode`),
>     `--quiet`.
>   - On-disk layout (matches the existing D-A loader, no
>     loader change needed):
>     `data/historical_market_store/exchange_info/*.{json,jsonl}`,
>     `data/historical_market_store/top_movers/*.jsonl`,
>     `data/historical_market_store/manifests/*.json`.
>   - JSONL row carries both the brief-mandated columns
>     (`symbol`, `mover_window_start_utc`,
>     `mover_window_end_utc`, `reference_timestamp_utc`,
>     `top_mover_rank`, `window_gain_pct`,
>     `max_24h_gain_pct`, `open_price`, `close_price`,
>     `high_price`, `low_price`, `quote_volume`,
>     `eligible_usdt_perpetual`,
>     `source = binance_public_futures_klines_1h`,
>     `lookahead_policy = post_hoc_reference_only`,
>     `generated_at_utc`) and the loader-required columns
>     (`snapshot_date`, `reference_timestamp_utc_ms`,
>     `mover_window_start_utc_ms`,
>     `mover_window_end_utc_ms`, `max_window_gain`,
>     `max_24h_gain`, `quote_volume_usdt`, `quote_asset`,
>     `contract_type`).
>   - Manifest records the public-only invariants
>     (`public_endpoint_only=true`, `private_api_used=false`,
>     `api_key_loaded=false`, `signed_endpoint_used=false`,
>     `binance_private_api_enabled=false`,
>     `telegram_outbound_enabled=false`,
>     `live_trading_enabled=false`,
>     `exchange_live_order_enabled=false`,
>     `right_tail_enabled=false`, `llm_enabled=false`,
>     `trading_mode="paper"`), the Lookahead Guard label
>     (`lookahead_guard=reference_set_is_post_hoc_audit_only`,
>     `lookahead_policy=post_hoc_reference_only`,
>     `lookahead_forbidden_fields=[...]`), the public REST
>     allowlist + forbidden private endpoints + forbidden
>     query parameters, the recorded public REST calls
>     (path + status), the run mode flags (`dry_run`,
>     `no_network_test_mode`), and a `boundary` block
>     listing what the builder is **NOT**.
>   - Lookahead Guard enforced at write time:
>     `validate_no_lookahead_fields(...)` rejects any row
>     containing `completed_tail_label` /
>     `tail_label_completed` / `final_max_gain` /
>     `future_return` / `future_max_gain` /
>     `future_max_window_gain` / `future_max_24h_gain` /
>     `post_window_return` / `post_window_max_gain` /
>     `lookahead_return` / `lookahead_max_gain` /
>     `settled_tail_outcome` / `primary_window_completed`.
>   - `app/adaptive/historical_mover_coverage_backfill.py`
>     is **NOT** modified. The audit's miss-reason
>     taxonomy, event types, capture-path order, lookahead
>     guard helpers, and runtime payloads are untouched.
>   - 16 new unit tests under
>     `tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_reference_store.py`,
>     covering the brief-mandated cases plus a CLI smoke
>     and a credential-env refusal smoke.
>   - `.gitignore` updated to exclude
>     `data/historical_market_store/`.
>
> **Out of scope for PR #65:**
>
>   - Real 60D historical data is **not** bundled. Real 60D
>     data generation against Binance public futures
>     endpoints is **required after merge** before
>     Phase 11C.1C-C-B-B-B-D-A can be flipped to
>     `ACCEPTED`. The closeout PR (separate, docs-only)
>     must record the operator-VPS evidence (live
>     `HISTORICAL_MOVER_COVERAGE_*` event counts, daily
>     report excerpt, Phase 8.5 export bundle manifest
>     count, audit `backfill_status`) over the real 60D
>     window.
>   - PR #65 does **NOT** modify the public-market paper
>     runner. The runner already accepts
>     `--historical-mover-store-dir` (added by PR #64) and
>     can consume the artefacts produced by the builder
>     once the operator runs it on the real public REST
>     surface.

## Why this slice exists (positioning under AMOS)

This slice is a direct application of the
`docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`
governance to the next concrete step under Phase
11C.1C-C-B-B-B and on top of the `ACCEPTED` Phase
11C.1C-C-B-B-B-D. AMOS treats AMA-RT as an *Adaptive
Market Operating System*: the goal is **long-term stable
operation, adaptation to market structural change, and
the ability to capture 5x+ altcoin right-tail upside in
short-term moves when it is genuinely available** —
**not** promising returns, **not** running an
auto-strategy bot, and **not** letting AI drive
execution.

Under that frame, the project's main line for this
period must converge on:

  - **Add fewer modules; accumulate more structural
    data.**
  - **Talk less about "strategy"; verify Regime more.**
  - **Stop chasing a universal model; prove which states
    really carry right-tail value.**

The trigger for Phase 11C.1C-C-B-B-B-D-A is concrete and
measurable, and it is **different** from the trigger for
Phase 11C.1C-C-B-B-B-D:

  - Phase 11C.1C-C-B-B-B-D (PR #61) proved that the Mover
    Capture Recall & Missed-Tail Coverage Audit v0 layer
    can run in real paper mode end-to-end:
    `MOVER_CAPTURE_RECALL_AUDIT_GENERATED=1`,
    `MOVER_CAPTURE_PATH_AUDITED=20`,
    `mover_capture_audit_status=DEGRADED`,
    `capture_recall_rate=0.2000` over a 10 min
    operator-VPS WS smoke window (PR #62 closeout,
    accepted as evidence that the audit layer **runs**,
    **reports**, and **exports** correctly — not as
    evidence that the discovery layer is "good
    enough").
  - **However**: a 10 min live audit window is too short
    and too market-dependent to answer the substantive
    coverage question. On a calm day the gainer board
    may show no clear tails; on a noisy day a single
    coin (e.g. SAGAUSDT) may dominate the signal but
    prove nothing about general coverage. Waiting for
    several "good" market days to accumulate enough
    10 min windows wastes operator time and risks
    selection bias on the operator's side.
  - The **right next step** is therefore to evaluate
    discovery-layer coverage **over the past 60 days**
    as a structured **backfill audit**, not as another
    series of 10 min live windows. This converts the
    "human looks at the gainer board vs. did the system
    see it" check from anecdote into a deterministic,
    historical, replay-friendly audit.

Phase 11C.1C-C-B-B-B-D-A codifies that step as a
**paper-only historical backfill coverage audit
protocol**. It does **not** add a new strategy module, a
new AI authority, or a new optimiser. It does **not**
prove the strategy can trade. It only proves whether the
**discovery layer covered real market movers over the
past 60 days**.

## Phase boundary (parent / child relationship)

  - **Phase 11C.1B** — `ACCEPTED` (closed 2026-05-22).
    Provides `SymbolUniverse` / `exchangeInfo`-as-truth
    catalogue + WS-first all-market demon coin radar.
  - **Phase 11C.1C-A** — `ACCEPTED` (PR #36 + PR #37
    closeout). Adaptive Candidate Regime & Strategy
    Selector contracts (paper-only).
  - **Phase 11C.1C-B** — `ACCEPTED` (PR #38). Adaptive
    Candidate Runtime Calibration & Early Tail
    Discovery v0 (paper-only).
  - **Phase 11C.1C-C-A** — `ACCEPTED` (PR #40 + PR #41
    closeout). MFE / MAE Label Queue Runtime & Tail
    Outcome Tracking. Provides `LABEL_TRACKING_*` /
    `LABEL_WINDOW_*` / `TAIL_LABEL_ASSIGNED` outcomes
    per ACTIVE candidate.
  - **Phase 11C.1C-C-B-A** — `ACCEPTED` (PR #42 + PR #43
    closeout). Strategy Validation Lab v0 & Cluster
    Exposure Control Contracts. Provides
    `StrategyValidationSample`,
    `StrategyValidationReport`,
    `ClusterExposureAssessment`,
    `suggested_cluster_action` artefacts.
  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 + PR
    #45 closeout). Strategy Validation Dataset Builder
    & Quality Gate v0. Provides
    `StrategyValidationDataset` /
    `StrategyValidationQualityGate` artefacts.
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED /
    NOT_STARTED`. *Parent* phase. Strategy Validation
    Lab (deeper) & richer Cluster Exposure Control
    follow-up. **Not renamed** by this kickoff.
  - **Phase 11C.1C-C-B-B-B-A** — `ACCEPTED` (PR #52 +
    PR #54 closeout). First child slice. Paper Alpha
    Gate v0.
  - **Phase 11C.1C-C-B-B-B-B** — `ACCEPTED` (PR #56 +
    PR #57 closeout). Second child slice. Regime &
    Cluster Cohort Evidence Pack v0.
  - **Phase 11C.1C-C-B-B-B-C** — `ACCEPTED` (PR #58
    docs-only kickoff + PR #59 docs-only closeout,
    2026-05-25). Third child slice. Long-Window Cohort
    Stability & Sample Sufficiency Protocol v0.
  - **Phase 11C.1C-C-B-B-B-D** — `ACCEPTED` (PR #60
    docs-only kickoff + PR #61 implementation + PR #62
    docs-only closeout, 2026-05-25). Fourth child slice.
    Mover Capture Recall & Missed-Tail Coverage Audit v0
    / *异动币捕捉召回与漏捕右尾覆盖审计 v0*.
  - **Phase 11C.1C-C-B-B-B-D-A** — *this document*.
    `NEXT_ALLOWED / NOT_STARTED`. **Next allowed child
    slice** under Phase 11C.1C-C-B-B-B (on top of the
    `ACCEPTED` B-B-B-D track). Historical 60D Mover
    Coverage Backfill Audit v0 / *历史 60 天异动币覆盖
    回填审计 v0*. Docs / evidence-template only. No new
    runtime module. No new event type. No new strategy.
    No trade authority.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock
    unchanged.

## Scope (what this slice IS)

Phase 11C.1C-C-B-B-B-D-A is a **paper-only, report-only,
evidence-only historical coverage backfill audit
protocol slice**. It defines the 60D reference-set
shape, the per-mover audit fields, the miss-reason
taxonomy, the allowed outputs, the interpretation rules,
and the evidence-template shape that the operator and
any future closeout PR must follow.

The audit answers eight explicit questions about the
**past 60 days of eligible USDT perpetual movers**, **and
only these eight**:

  1. **Over the past 60 days, did AMA-RT discover the
     eligible USDT perpetual movers?** (Per-mover
     `system_captured = true / false`.)
  2. **If discovered, when was the first detection?**
     (`first_seen_time_utc`.)
  3. **What was the first detection event?**
     (`first_seen_event_type`.)
  4. **How deep did the capture path go?**
     (`capture_path_depth` and the per-stage booleans
     `reached_anomaly`, `reached_label_queue`,
     `reached_tail_label`,
     `reached_strategy_validation_sample`.)
  5. **If not discovered, why?** (`miss_reason` from the
     fixed taxonomy below.)
  6. **Is each missed mover a universe-coverage issue or
     a discovery-layer warning?** (i.e., is the mover
     out-of-scope by design, or in-eligible-universe but
     missed for a system-correctable reason?)
  7. **Which captured movers were rejected by the Risk
     Engine?** (`risk_rejected = true`; this is recorded
     as a **conservative paper outcome**, not as a
     discovery failure.)
  8. **Which captured movers only made it partway and
     never entered the label / validation chain?**
     (`status = partially_captured`, with explicit
     `reached_*` booleans showing how far the path went.)

The audit produces only descriptive output. It does
**not** decide trades. It does **not** widen or relax
any existing threshold. It does **not** override the
Risk Engine, the Execution FSM, the SymbolUniverse, the
candidate pool capacity, or any other runtime gate. It
does **not** retroactively change rules to chase past
movers — it only records what the system did and did
not see.

### Why this is *not* a complete strategy blind replay

A Historical 30D+ / 60D **complete strategy** blind
replay / walk-forward validation is a **separate, larger
gate** that belongs **after** the major paper modules and
the paper validation chain are complete and **before**
any small-money live trading. It is one of the candidate
Phase 12 pre-gates. It scores the strategy's
trade-by-trade behaviour against historical right-tail
outcomes and asks whether the strategy is **profitable**
on past data.

Phase 11C.1C-C-B-B-B-D-A is **strictly narrower**:

  - It is a **discovery-layer** coverage audit only.
  - It does **not** ask whether the strategy is
    profitable on past data.
  - It does **not** ask whether trade entries / exits
    would have been correct.
  - It does **not** ask whether position sizing,
    leverage, stops, or targets would have been
    correct.
  - It only asks **whether eligible USDT perpetual
    movers were observed by the discovery layer over
    the past 60 days, when they were first observed,
    how deep the capture path went, and why the missed
    ones were missed**.

A high `capture_recall_rate` over the 60D backfill does
**not** authorise live trading. A low
`capture_recall_rate` over the 60D backfill does **not**
authorise rule relaxation, automatic `symbol_limit`
expansion, automatic anomaly threshold changes, automatic
candidate-pool capacity changes, automatic Regime weight
changes, or any Risk Engine / Execution FSM change.

### Why this is *not* a new runtime module

The discovery-layer events (`PRE_ANOMALY_DETECTED`,
`ANOMALY_DETECTED`, `MARKET_REGIME_ASSESSED`,
`CANDIDATE_STAGE_CLASSIFIED`, `OPPORTUNITY_SCORED`,
`STRATEGY_MODE_SELECTED`, `CLUSTER_CONTEXT_ATTACHED`,
`LABEL_QUEUE_ENQUEUED`, `LABEL_TRACKING_STARTED`,
`LABEL_WINDOW_COMPLETED`, `TAIL_LABEL_ASSIGNED`,
`STRATEGY_VALIDATION_SAMPLE_CREATED`,
`MOVER_CAPTURE_RECALL_AUDIT_GENERATED`,
`MOVER_CAPTURE_PATH_AUDITED`) are already emitted by
Phase 11C.1B → Phase 11C.1C-C-B-B-B-D. The Phase 8.5
export bundle, the Phase 10A replay engine, the
`StrategyValidationDataset`, the `PaperAlphaGateReport`,
the `RegimeClusterEvidencePack`, the
`MoverCaptureRecallAuditReport`, the SymbolUniverse, the
`exchangeInfo`-as-truth catalogue, and the candidate
pool logs all exist on `main`. The Binance public 24 h
ticker / klines / market-data endpoints are already
reachable through the existing public REST surface
(Phase 11C.1A rate-limit governor + Phase 11C.1B
all-market radar; **public only**, no signed
endpoints, no `listenKey`, no private WebSocket).
**Nothing new needs to ship in `app/` to support a
Historical 60D Mover Coverage Backfill Audit.** The
path forward is to define the audit shape and the
evidence template, and run the existing surfaces
against an external "what did Binance's public 60D
top-mover series actually look like?" reference series.

### Why this is *not* the implementation or the closeout

This is the **kickoff** PR. It scopes Phase
11C.1C-C-B-B-B-D-A in place. It does **not** build the
backfill, run the backfill, produce any backfill audit
transcript, or flip the slice to `ACCEPTED`. The
implementation (if any) and the closeout are **separate,
later PRs**. Even the implementation, if it ships, must
be docs / evidence-template-driven where possible — no
new runtime module, no new event type, no new strategy,
no trade authority.

## 60D top-mover reference set (must be defined verbatim)

Every Phase 11C.1C-C-B-B-B-D-A audit pass requires a
**60D top-mover reference set** assembled from Binance
**public** market data only. The reference set is the
ground truth against which the discovery layer is
audited. It is **not** a strategy signal. It is **not**
read by the Risk Engine. It is **not** read by the
Execution FSM. It is a **historical, descriptive, paper
artefact**.

For each day / each window over the 60D backfill range,
the reference set must record:

  - **`reference_window_start_utc`** — UTC timestamp of
    the start of the mover window (e.g. day boundary or
    rolling window start).
  - **`reference_window_end_utc`** — UTC timestamp of
    the end of the mover window.
  - **`top_mover_symbol`** — the symbol that registered
    a top mover (e.g. top gainer / top mover / high
    momentum mover) within the window.
  - **`top_mover_rank`** — the symbol's rank within the
    window's top mover list (e.g. `1` for the day's
    top gainer; smaller is "more obvious").
  - **`max_window_gain`** — the max % move observed for
    the symbol within the reference window
    (descriptive only; no thresholding implied here).
  - **`max_24h_gain`** — the max 24 h % move observed
    for the symbol on a 24 h basis where available
    (descriptive only).
  - **`reference_timestamp_utc`** — the canonical
    timestamp the reference series uses to mark "the
    mover became obvious" (e.g. the bar close at which
    the cumulative gain first crossed the day's
    eventual peak threshold). Used to compute
    `first_seen_latency_seconds` against AMA-RT's own
    discovery time when both are present.

The reference set must explicitly classify each candidate
symbol against the **eligible USDT perpetual universe**:

  - **`eligible_usdt_perpetual = true`** — symbol is
    listed on Binance USDT-margined perpetual futures
    `exchangeInfo` for the entire reference window AND
    is USDT-margined AND is perpetual AND is
    tradable / not delisted AND is not in any
    excluded-symbol list maintained by `SymbolUniverse`.
  - **`eligible_usdt_perpetual = false`** — symbol fails
    one or more of the above. Such symbols are recorded
    for completeness but **must not** count against the
    discovery layer when computing
    `capture_recall_rate`; they are out of scope by
    design.

Excluded symbols include (but are not limited to):

  - non-futures listings (spot-only);
  - non-USDT-margined futures (e.g. coin-margined);
  - non-perpetual futures (quarterly, etc.);
  - symbols not present in `exchangeInfo` for the
    reference window;
  - delisted / inactive symbols.

The reference set is a **public-data artefact**. It must
not depend on any signed endpoint, any private
WebSocket, any `listenKey`, any account / order /
position / leverage / margin endpoint, any DeepSeek
output, or any Telegram outbound. It is read-only with
respect to AMA-RT's runtime.

## Per-captured-mover record shape (must be defined verbatim)

For every reference-set top mover (eligible or
otherwise), Phase 11C.1C-C-B-B-B-D-A must record an audit
row with **at least** the following descriptive fields:

  - **`top_mover_symbol`** — symbol from the reference
    set.
  - **`mover_window_start_utc`** — start of the
    reference window.
  - **`mover_window_end_utc`** — end of the reference
    window.
  - **`top_mover_rank`** — rank within the reference
    window.
  - **`max_window_gain`** — max % move within the
    window (descriptive).
  - **`max_24h_gain`** — max 24 h % move where
    available (descriptive).
  - **`eligible_usdt_perpetual`** — `true` / `false` as
    defined above.
  - **`system_captured`** — `true` if AMA-RT emitted at
    least one discovery-layer event for the symbol
    within the audit window; otherwise `false`.
  - **`first_seen_time_utc`** — the UTC timestamp of
    the **first** discovery-layer event for the symbol
    within the audit window; `null` if the symbol was
    not captured.
  - **`first_seen_event_type`** — the event type of the
    first discovery-layer event (e.g.
    `PRE_ANOMALY_DETECTED`, `ANOMALY_DETECTED`,
    `MARKET_REGIME_ASSESSED`,
    `CANDIDATE_STAGE_CLASSIFIED`,
    `OPPORTUNITY_SCORED`, `STRATEGY_MODE_SELECTED`,
    `CLUSTER_CONTEXT_ATTACHED`,
    `LABEL_QUEUE_ENQUEUED`, `LABEL_TRACKING_STARTED`,
    `LABEL_WINDOW_COMPLETED`, `TAIL_LABEL_ASSIGNED`,
    `STRATEGY_VALIDATION_SAMPLE_CREATED`); `null` if
    the symbol was not captured.
  - **`first_seen_latency_seconds`** —
    `first_seen_time_utc - reference_timestamp_utc`
    in seconds, computed only where both timestamps
    exist; `null` otherwise.
  - **`capture_path_depth`** — integer depth in the
    canonical capture path (counting from
    `MARKET_SNAPSHOT` / `PRE_ANOMALY_DETECTED` at
    depth 1 up to
    `STRATEGY_VALIDATION_SAMPLE_CREATED` at depth N);
    `0` if not captured.
  - **`reached_anomaly`** — `true` if the symbol
    reached `ANOMALY_DETECTED` within the audit
    window.
  - **`reached_label_queue`** — `true` if the symbol
    reached `LABEL_QUEUE_ENQUEUED`.
  - **`reached_tail_label`** — `true` if the symbol
    reached `TAIL_LABEL_ASSIGNED`.
  - **`reached_strategy_validation_sample`** — `true`
    if the symbol reached
    `STRATEGY_VALIDATION_SAMPLE_CREATED`.
  - **`risk_rejected`** — `true` if the Risk Engine
    rejected the symbol after capture (recorded as a
    conservative paper outcome, **not** as a
    discovery failure).
  - **`status`** — one of:
      - `captured` — captured AND reached the label /
        validation chain.
      - `partially_captured` — captured but did not
        reach `LABEL_QUEUE_ENQUEUED` / later stages.
      - `missed` — eligible USDT perpetual mover that
        was not captured.
      - `excluded` — not in the eligible USDT
        perpetual universe; out of scope by design.
  - **`miss_reason`** — exactly one value from the
    fixed taxonomy below; required when
    `status = missed`; required when
    `status = partially_captured` (explaining why the
    capture path stopped); set to `null` when
    `status = captured` and not risk-rejected; set to
    `risk_rejected` when the symbol was captured and
    then rejected by the Risk Engine.

## Miss-reason taxonomy (must be defined verbatim)

Phase 11C.1C-C-B-B-B-D-A introduces **no new runtime
event** and **no new runtime taxonomy**. It only
defines a **descriptive** miss-reason taxonomy used
inside the audit document / evidence template. The
allowed values are exactly:

  - `not_in_futures_universe` — symbol is not in the
    futures universe at all.
  - `symbol_not_in_exchange_info` — symbol is not in
    `exchangeInfo` for the reference window.
  - `not_usdt_perpetual` — symbol is in futures but is
    not a USDT-margined perpetual contract (e.g.
    coin-margined, quarterly).
  - `missing_historical_reference_data` — the 60D
    reference set has no usable mover-event timestamp
    for this symbol in the window.
  - `missing_event_history` — AMA-RT has no event
    history for this symbol in the audit window
    (e.g. the system was not running, or the events.db
    has no entries for the window).
  - `below_liquidity_threshold` — symbol failed
    AMA-RT's liquidity / volume gating.
  - `symbol_limit_excluded` — symbol was excluded by
    the active `symbol_limit` cap.
  - `candidate_pool_evicted` — symbol was evicted from
    the candidate pool because of capacity pressure.
  - `insufficient_ws_data` — too few WS frames
    received for the symbol within the window to
    produce any discovery-layer event.
  - `stale_data` — data was present but stale beyond
    the staleness threshold; treated as unreliable.
  - `data_unreliable` — data was present but flagged
    as unreliable (e.g. inconsistent ticker rows,
    suspect liquidations).
  - `no_anomaly_threshold_cross` — the discovery layer
    saw the symbol but no anomaly threshold was
    crossed (the symbol moved within normal bounds
    from AMA-RT's vantage point).
  - `risk_rejected` — captured by the discovery layer
    and then rejected by the Risk Engine. Recorded as
    a conservative paper outcome; **not** a discovery
    failure.
  - `no_completed_tail_label_yet` — captured and
    label-queued, but the tail-label window had not
    completed at the time of the audit.
  - `unknown` — the audit cannot classify the miss;
    flagged for human review. **`unknown` is a
    `review` signal, not a `relax` signal — it does
    NOT authorise rule relaxation.**

The 14 explicit values plus `unknown` are the only
values allowed. New values must not be introduced
inside this slice; they require a separate kickoff PR
under a new child slice.

## Allowed outputs (docs / evidence templates only)

Each is a **descriptive document, evidence row, or
summary**. None has trade authority. None is read by the
Risk Engine or the Execution FSM. None is a new Python
module, a new event type, or a new runtime hook:

  - `historical_60d_mover_reference_set` — the 60D
    top-mover reference set (per-window /
    per-symbol).
  - `historical_60d_capture_path_audit` — per-mover
    audit rows (with all fields above).
  - `historical_60d_miss_reason_summary` — counts /
    grouping by `miss_reason`.
  - `historical_60d_first_seen_summary` — counts /
    distributions for `first_seen_time_utc`,
    `first_seen_event_type`, and
    `first_seen_latency_seconds`.
  - `historical_60d_capture_recall_summary` —
    `top_mover_count`, `eligible_top_mover_count`,
    `captured_top_mover_count`,
    `partially_captured_top_mover_count`,
    `missed_top_mover_count`, `excluded_top_mover_count`,
    `capture_recall_rate`,
    `eligible_capture_recall_rate`,
    `risk_rejected_mover_count`,
    `not_in_universe_count`,
    `data_unreliable_count`,
    `median_first_seen_latency_seconds`.
  - `historical_60d_coverage_warning` — list of
    coverage warnings raised under the strict
    interpretation rules (see below).
  - `historical_60d_export_replay_evidence_template` —
    the shape of the export / replay evidence bundle a
    future closeout PR will record (Phase 8.5 export
    zip path, manifest event count, redaction status,
    events.jsonl presence, presence of relevant
    `MOVER_CAPTURE_*` events, etc.).

## Audit cadence (operator-driven; not auto-scheduled)

  - **B1 — first end-to-end 60D historical backfill
    audit pass.** Operator chooses the 60D window
    end-date (typically: the most recent UTC day with
    closed events.db / export bundles).
  - **B2 — second 60D historical backfill audit pass
    against an independent operator-VPS replay window.**
    Used to detect operator / pipeline non-determinism.
  - **B3+ — reserved for later child slices; out of
    scope for this PR; not implemented in this PR.**

This PR **must not** implement an automatic scheduler,
an auto-trigger, or any runtime change that drives B1 /
B2 / B3+ on a clock. The cadence is **operator-driven**
and recorded as a **protocol**, not as code.

## Allowed input sources (read-only; reuse existing surfaces)

  - Binance **public** 24 h ticker / public klines /
    public market data (existing public REST surface;
    Phase 11C.1A rate-limit governor; **not** a private
    endpoint, **not** a signed endpoint, **not** a
    `listenKey`).
  - `EventRepository` / events.db (existing, read-only).
  - Daily report (existing Phase 11B + 11C sections).
  - Phase 8.5 export bundle / Phase 10A replay bundle
    over the 60D window.
  - `StrategyValidationDataset` (Phase 11C.1C-C-B-B-A
    artefact).
  - `PaperAlphaGateReport` (Phase 11C.1C-C-B-B-B-A
    artefact).
  - `RegimeClusterEvidencePack` (Phase
    11C.1C-C-B-B-B-B artefact).
  - `MoverCaptureRecallAuditReport` (Phase
    11C.1C-C-B-B-B-D artefact).
  - `SymbolUniverse` and `exchangeInfo`-as-truth
    catalogue (Phase 11C.1B artefacts).
  - Candidate pool logs / capacity-eviction evidence
    (where available from existing runtime
    instrumentation).

All input sources are **read-only** with respect to
AMA-RT's runtime. The audit must not modify them, must
not trigger a re-run that changes them, and must not
write back into them.

## Audit objects

  - 60D top gainers / top movers / high-momentum
    movers in the eligible USDT perpetual universe.
  - 60D detected anomalies.
  - 60D pre-anomaly candidates.
  - 60D label-tracked candidates.
  - 60D validation samples.
  - 60D risk-rejected captured movers.
  - 60D excluded symbols (not in eligible universe).

## Interpretation principles (must be read verbatim)

  1. **Captured ≠ tradable.** A symbol reaching
     `STRATEGY_VALIDATION_SAMPLE_CREATED` does **not**
     mean the strategy can trade it; tradability
     requires Risk Engine approval and is out of scope
     for this slice.
  2. **Captured early ≠ strategy profitable.** A low
     `first_seen_latency_seconds` does **not** mean the
     strategy would have been profitable; the audit
     measures discovery, not P&L.
  3. **Missed and not-in-futures-universe ≠ system
     failure.** Out-of-scope-by-design symbols
     (non-futures, non-USDT, non-perpetual,
     not-in-`exchangeInfo`, delisted) are recorded but
     do **not** count against the discovery layer.
  4. **Missed and in-eligible-universe IS a coverage
     warning.** When a missed symbol is in the eligible
     USDT perpetual universe AND showed clear
     right-tail behaviour AND was missed for a
     system-correctable reason, a coverage warning
     **must** be raised — for human review only.
  5. **`risk_rejected` ≠ discovery failure.** The
     symbol was discovered; the Risk Engine performed
     its conservative paper job. The Risk Engine
     remains the single trade-decision gate.
  6. **`missed` and `unknown` are `review` signals.**
     They must enter human review. They must **not**
     trigger automatic rule relaxation, automatic
     `symbol_limit` expansion, automatic anomaly
     threshold changes, automatic candidate-pool
     capacity changes, automatic Regime weight
     changes, or any Risk Engine / Execution FSM
     change.
  7. **High `capture_recall_rate` does NOT authorise
     live trading.** Even
     `eligible_capture_recall_rate=1.0` over the 60D
     backfill does **not** authorise live orders, API
     keys, private endpoints, DeepSeek trade
     decisions, real Telegram outbound, AI Learning,
     automatic parameter optimisation, reinforcement
     learning, or Phase 12.
  8. **Low `capture_recall_rate` does NOT authorise
     parameter changes.** A low recall is a `review`
     outcome only. The audit must **not** be retro-fit
     around the past — no thresholds, weights,
     symbol-limits, or capacities may be changed on
     the basis of historical movers (this would be
     "looking at the answer key", which the audit
     forbids by construction).

## Forbidden by this slice (carry forward verbatim + slice-specific items)

The following are forbidden by this slice **and by every
later D-A PR (implementation / closeout)** unless a
separate, named slice opens them:

### Trading / execution / live-trading surface

  - Real trading.
  - Live trading.
  - Binance API key / secret.
  - Signed endpoint / `listenKey` / private WebSocket.
  - Account / order / position / leverage / margin
    endpoint.
  - DeepSeek trade decision.
  - Real Telegram outbound.

### AI / autonomy

  - AI deciding direction / position size / leverage /
    stop / target / execution.
  - Automatic parameter optimisation.
  - Reinforcement learning.
  - AI Learning that auto-decides trades.

### Auto-rule relaxation (the core risk for this slice)

  - Auto-rule-relaxation on low coverage.
  - Auto-rule-relaxation on a single-coin / "妖币"
    case (SAGAUSDT or otherwise).
  - Automatic `symbol_limit` expansion.
  - Automatic anomaly threshold changes.
  - Automatic candidate-pool capacity changes.
  - Automatic Regime weight changes.
  - Auto-tuning any threshold against the historical
    reference set ("looking at the answer key").
  - Treating a high `capture_recall_rate` as live-trade
    authorisation.
  - Treating a low `capture_recall_rate` as
    rule-relaxation authorisation.

### Runtime surface

  - Risk Engine override / bypass.
  - Execution FSM override / bypass.
  - Phase Gate override / bypass.
  - Triggering a real trade from any audit artefact.
  - Modifying position size / leverage / stop-loss /
    target price from any audit artefact.
  - Modifying the Risk Engine or the Execution FSM
    from any audit artefact.

### Inherited boundary

  - Replacing the Regime & Cluster Evidence Pack v0
    `INSUFFICIENT_SAMPLE` rule with a relaxed rule.
  - Replacing the Paper Alpha Gate v0 `INCONCLUSIVE`
    rule with a relaxed rule.
  - Replacing the Long-Window Cohort Stability &
    Sample Sufficiency Protocol v0 cadence with a
    relaxed cadence.
  - Replacing the Mover Capture Recall & Missed-Tail
    Coverage Audit v0 `DEGRADED` rule with a relaxed
    rule.

### Module / event / scope surface

  - Adding new Python modules under `app/`.
  - Adding new event types.
  - Modifying `app/`, `scripts/`, `tests/`,
    `configs/`, `risk/`, `execution/`, `llm/`,
    `telegram/`, or `exchange/`.
  - Modifying configuration schemas, defaults, or
    YAML.
  - Adding or modifying tests.
  - Running tests.
  - Modifying strategy runtime code.
  - Modifying runtime behaviour.
  - Implementing new functionality.
  - Implementing the Phase 11C.1C-C-B-B-B-D-A
    backfill as a new runtime module — the slice is
    intentionally **docs / evidence-template only**
    end-to-end at kickoff.
  - Treating Phase 11C.1C-C-B-B-B-D-A as a Historical
    30D+ / 60D *complete strategy* blind replay /
    walk-forward validation. **It is not.** That gate
    belongs after the major paper modules and the
    paper validation chain are complete, before
    small-money live trading, as a Phase 12 candidate
    pre-gate.

### Phase / gate surface

  - Flipping any phase's acceptance state. Phase
    11C.1C-C-B-B-A remains `ACCEPTED`. Phase
    11C.1C-C-B-B-B remains `NEXT_ALLOWED /
    NOT_STARTED`. Phase 11C.1C-C-B-B-B-A remains
    `ACCEPTED`. Phase 11C.1C-C-B-B-B-B remains
    `ACCEPTED`. Phase 11C.1C-C-B-B-B-C remains
    `ACCEPTED`. Phase 11C.1C-C-B-B-B-D remains
    `ACCEPTED`. Phase 11C.1C-C-B-B-B-D-A remains
    `NEXT_ALLOWED / NOT_STARTED` (this PR scopes the
    slice; it does not flip its state). Phase 12
    remains `FORBIDDEN`.
  - Renaming Phase 11C.1C-C-B-B-B. The parent phase
    keeps its existing definition — *Strategy
    Validation Lab (deeper) & richer Cluster Exposure
    Control follow-up*.
  - Phase 11C.1C-C-B-B-B-D-A *implementation* (out of
    scope; will be a separate PR if needed; even then
    must be docs / evidence-template-driven where
    possible).
  - Phase 11C.1C-C-B-B-B-D-A *closeout* (out of scope;
    will be authored after the operator captures B1 /
    B2 backfill audit evidence and a separate
    docs-only closeout PR flips the slice to
    `ACCEPTED`).
  - Phase 11C.1C-C-B-B-B-D-B / further child slices
    (out of scope; will require their own kickoff
    PRs).
  - Phase 12 / live trading kickoff.

## Safety boundary (Phase 1 lock unchanged)

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
real account / order / position / leverage / margin endpoint = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

The audit operates entirely on **public** Binance market
data, AMA-RT's own `EventRepository`, the Phase 8.5
export / Phase 10A replay surfaces, and existing report
artefacts. Nothing in this slice loads, requests, signs,
or transmits any private credential. Nothing in this
slice can authorise a real trade.

## Acceptance gate (placeholder; not flipped by this PR)

The Phase 11C.1C-C-B-B-B-D-A kickoff PR (this PR; PR
#63) **only** scopes the slice. A future docs-only
closeout PR will:

  - record the operator-driven B1 / B2 backfill audit
    transcripts;
  - record the resulting
    `historical_60d_capture_recall_summary` /
    `historical_60d_miss_reason_summary` /
    `historical_60d_first_seen_summary` /
    `historical_60d_coverage_warning` artefacts;
  - record the Phase 8.5 export evidence over the 60D
    window;
  - record the safety-flag invariants
    (`mode=paper`, `live_trading=False`,
    `exchange_live_orders=False`, `right_tail=False`,
    `llm=False`, `telegram_outbound_enabled=False`,
    `binance_private_api_enabled=False`, no Binance
    API key / secret, no signed endpoint, no
    account / order / position / leverage / margin
    endpoint, no private WebSocket, no `listenKey`,
    no DeepSeek trade decision, no real Telegram
    outbound);
  - record the closeout interpretation rules
    verbatim (high recall ≠ live trade authority; low
    recall ≠ rule-relaxation authority; risk-rejected
    ≠ discovery failure; `missed` / `unknown` are
    `review` signals only);
  - flip Phase 11C.1C-C-B-B-B-D-A to `ACCEPTED`.

The closeout will require its own docs-only PR. This
kickoff PR does **not** flip the slice's state.

## Out of scope (handled by future PRs in the cycle)

  - The substantive 60D backfill audit transcripts (B1,
    B2) — out of scope; will be authored alongside the
    docs-only closeout PR after the operator captures
    the B1 / B2 evidence.
  - The Historical 30D+ / 60D *complete strategy* blind
    replay / walk-forward validation gate — out of
    scope for this slice; reserved for a Phase 12
    candidate pre-gate.
  - Phase 11C.1C-C-B-B-B-E / further child slices — out
    of scope; will require their own kickoff PRs.
  - Phase 12 / live trading kickoff — `FORBIDDEN`.



---

## Phase 11C.1C-C-B-B-B-D-A v0 implementation update (PR #64)

> **Status: IN_REVIEW (PR #64; flipped 2026-05-25).** This update
> records the v0 engine / payload / report / Lookahead Guard
> implementation that lands with PR #64. Phase 11C.1C-C-B-B-B-D-A
> remains paper / report / evidence only. **No** real trade is
> authorised. **No** position size, leverage, stop-loss, target
> price, Risk Engine threshold, Execution FSM rule, `symbol_limit`,
> candidate-pool capacity, anomaly threshold, Regime weight, or any
> other runtime knob is modified by this PR or by any audit result
> it produces. The Risk Engine remains the single trade-decision
> gate. Phase 12 remains **FORBIDDEN**.

### What PR #64 ships

  - New module `app/adaptive/historical_mover_coverage_backfill.py`
    with the data models, deterministic pure functions, the
    Lookahead Guard helpers, the Historical Market Store loader,
    and the `HistoricalMoverCoverageBackfillRuntime`.
  - Two new typed events in `app/core/events.py`:
    `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED` (one per audit
    window) and `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED` (one per
    audited mover record).
  - Phase 11C public-market paper runner extended with two
    discovery flags: `--historical-mover-store-dir` and
    `--historical-reference-window-days`.
  - Daily report extended with a new "Phase 11C.1C-C-B-B-B-D-A
    Historical 60D Mover Coverage Backfill Audit v0" section that
    surfaces every brief-mandated metric (`backfill_status`,
    `top_mover_count`, `eligible_top_mover_count`,
    `captured_top_mover_count`,
    `partially_captured_top_mover_count`,
    `missed_top_mover_count`, `excluded_top_mover_count`,
    `capture_recall_rate`, `partial_capture_rate`, `miss_rate`,
    `anomaly_detected_rate`, `label_tracking_rate`,
    `tail_label_assigned_rate`,
    `strategy_validation_sample_rate`,
    `risk_rejected_mover_count`, `not_in_universe_count`,
    `missing_event_history_count`, `data_unreliable_count`,
    `median_first_seen_latency_seconds`,
    `p90_first_seen_latency_seconds`,
    `miss_reason_summary`, `coverage_warnings`,
    `lookahead_guard_warnings`) plus per-record sample rows.
  - New unit-test module
    `tests/unit/test_phase11c_1c_c_b_b_b_d_a_historical_mover_coverage_backfill.py`
    covering every brief-mandated case (18 tests + 4 supporting
    tests).

### Lookahead Guard (verbatim, enforced in code)

  - `completed_tail_label` MUST NOT drive reference selection.
  - future return / final max gain MUST NOT pollute the
    simulated live-radar score.
  - replay label MUST NOT contaminate `first_seen_time`.
  - reflection / report text / LLM narrative MUST NEVER serve as
    a capture event source.
  - `first_seen_time_utc` MUST come from the timestamp of an
    event that already existed at audit time.
  - the top-mover reference set MUST only be used for post-hoc
    audit; it cannot rewrite past decisions.

The guard is enforced by
`validate_no_lookahead_fields(...)` (rejects forbidden columns
in any reference / capture-source payload) and
`assert_capture_event_is_past_or_equal_reference_window(...)`
(rejects events outside the configured window with operator-only
grace bounds).

### Closeout requirements (still owed)

  - Real 60D historical data is not bundled and is **not**
    required for this PR's acceptance.
  - A subsequent operator-driven evidence-collection run that
    populates `data/historical_market_store/top_movers/*.jsonl`
    and `data/historical_market_store/exchange_info/*.jsonl`
    plus a docs-only closeout PR is required to flip the slice
    to `ACCEPTED`.
  - The closeout PR must NOT relax thresholds, expand
    `symbol_limit`, modify candidate-pool capacity, modify
    anomaly thresholds, or modify Regime weights based on the
    historical audit numbers.
