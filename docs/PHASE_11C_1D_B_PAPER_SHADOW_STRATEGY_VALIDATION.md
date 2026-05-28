# Phase 11C.1D-B — Paper Shadow Strategy Validation v0

> 纸面影子策略验证 v0
> **Status:** IN_REVIEW (after the implementation PR is merged the
> phase moves from IN_REVIEW to ACCEPTED only via a separate
> docs-closeout PR; this PR alone does NOT mark the phase
> ACCEPTED).
> **Parent:** Phase 11C umbrella.
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

---

## Purpose

A strictly paper-only / report-only / evidence-only cohort
evaluation layer that turns the structured outputs of the Block B
integrated evidence checkpoint, the Block C integrated checkpoint,
and the Offline Rule Sandbox Replay v0 (PR #89) into:

  * `PaperShadowSample` rows — one retrospective evidence row per
    discovery
  * cohort groupings keyed on regime / cluster / leader vs.
    follower / candidate stage / strategy mode / opportunity score
    bucket / early-tail score bucket / post-discovery outcome label
    / reject attribution verdict / severe miss root cause /
    discovery quality bucket
  * cohort-level metrics (sample count, usable discovery rate,
    median MFE, median MAE, late chase rate, fake breakout rate,
    severe miss rate, false-negative reject rate, data gap rate)
  * per-cohort recommendation labels drawn from a closed
    taxonomy: `REVIEW_ONLY`, `PROMISING_FOR_FORWARD_TEST`,
    `INCONCLUSIVE`, `RISKY`, `REJECTED_BY_EVIDENCE`

The output is one descriptive
`paper_shadow_strategy_validation_report.json` (plus its Markdown
twin) that an auditor can review to decide which discovery patterns
/ regime-cluster cohorts have a structural edge on the historical
record, and which look like noise / late chase / fake breakout /
data gap.

This phase is a *retrospective measurement layer*, not a trading
system. It does not place a paper trade, it does not place a real
trade, it does not modify any runtime knob, and it does not auto-
tune anything.

---

## Relation to Offline Rule Sandbox Replay v0 (PR #89)

The Offline Rule Sandbox Replay (Phase 11C) answers the question:

> *If we had changed a rule, how would historical discovery
> quality have shifted in direction?*

The Paper Shadow Strategy Validation (Phase 11C.1D-B) answers a
strictly different question:

> *Holding the current rules fixed, which discovery patterns and
> regime-cluster cohorts on the historical evidence record show a
> structural edge that justifies preparing them for the next
> paper / read-only step?*

Concretely:

| Aspect | Offline Rule Sandbox Replay v0 | Paper Shadow Strategy Validation v0 |
| --- | --- | --- |
| Scope | Hypothetical rule changes | Cohort evaluation under current rules |
| Verdicts | `REVIEW_ONLY`, `INCONCLUSIVE`, `PROMISING_FOR_PAPER_SHADOW`, `RISKY`, `REJECTED_BY_EVIDENCE` | `REVIEW_ONLY`, `INCONCLUSIVE`, `PROMISING_FOR_FORWARD_TEST`, `RISKY`, `REJECTED_BY_EVIDENCE` |
| Output verdict semantics | A scenario *might* warrant later paper-shadowing | A cohort *might* warrant later forward-test preparation |
| Trade authority | None | None |
| Runtime config writes | None | None |
| Auto-tuning | None | None |
| Phase 12 | FORBIDDEN | FORBIDDEN |

A `PROMISING_FOR_PAPER_SHADOW` verdict from Phase 11C is the
*upstream* gate that even allows Phase 11C.1D-B work to be
prepared. A `PROMISING_FOR_FORWARD_TEST` verdict from Phase
11C.1D-B is the *downstream* gate that allows Risk / Execution /
Capital Safety Matrix preparation OR strict walk-forward
preparation to be scoped. Neither verdict authorises live trading.

---

## Inputs

The runner reads three structured report files (all optional):

| Argument | Default path | Source |
| --- | --- | --- |
| `--block-b-report` | `data/reports/block_b_integrated_evidence/block_b_integrated_evidence_report.json` | Phase 11C.1C-C-B-B-B-D-E |
| `--block-c-report` | `data/reports/block_c_integrated_checkpoint/block_c_integrated_checkpoint_report.json` | Phase 11C.1C-C-B-B-B-E-D |
| `--rule-sandbox-report` | `data/reports/rule_sandbox/offline_rule_sandbox_report.json` | Phase 11C / PR #89 |

When a report is missing on disk, the runner substitutes a
deterministic example fixture marked `source=example_fixture` and
sets `used_example_fixture=true` in the payload. The fixture
NEVER claims to be operator-supplied paper evidence.

The runner accepts records from the following sections of each
input report (any present section is consumed):

  * `paper_shadow_samples`
  * `post_discovery_outcome_records`
  * `post_discovery_outcomes`
  * `severe_miss_records`
  * `reject_attribution_records`
  * `discovery_quality_records`
  * `samples`
  * `records`

Records are read for evidence only. Nothing is written back.

---

## Outputs

| Argument | Default path |
| --- | --- |
| `--output-dir` | `data/reports/paper_shadow_strategy_validation` |

Two files are written:

  * `paper_shadow_strategy_validation_report.json` — canonical
    report payload.
  * `paper_shadow_strategy_validation_report.md` — a human-
    readable Markdown twin.

The JSON payload always carries the project-wide invariants at the
serialisation boundary:

```json
{
  "phase": "Phase 11C.1D-B / Paper Shadow Strategy Validation v0",
  "sandbox_only": true,
  "writes_runtime_config": false,
  "auto_tuning_allowed": false,
  "trade_authority": false,
  "live_trading": false,
  "exchange_live_orders": false,
  "right_tail": false,
  "llm": false,
  "llm_outbound_enabled": false,
  "telegram_outbound_enabled": false,
  "binance_private_api_enabled": false,
  "phase_12_forbidden": true,
  "next_allowed_phase": "Risk / Execution / Capital Safety Matrix preparation or strict walk-forward preparation (paper / read-only)"
}
```

The recursive `assert_no_forbidden_fields` guard refuses to emit
any payload that carries a trade-action / runtime-config-patch /
"live ready" / "trading approved" / "phase_12_allowed" key at any
nesting depth.

---

## Cohort schema (`PaperShadowCohortKey`)

Cohorts are descriptive labels only. None of them are inputs to a
trade-decision pipeline, the Risk Engine, the Execution FSM,
`symbol_limit`, candidate-pool capacity, anomaly thresholds, or
Regime weights.

| Field | Description |
| --- | --- |
| `market_regime` | Block B / Block C regime label (e.g., `trend`, `range`, `chop`). |
| `cluster_id` | Adaptive cluster id from Phase 11C.1C work. |
| `leader_vs_follower` | Discovery-time leader / follower label. |
| `candidate_stage` | First-seen detection-timing label (e.g., `EARLY`, `MID_MOVE`, `LATE`). |
| `strategy_mode` | Operator-tagged strategy mode (e.g., `continuation`, `breakout`, `reversion`). |
| `opportunity_score_bucket` | Bucket of the discovery opportunity score: `very_low` / `low` / `medium` / `high` / `very_high`. |
| `early_tail_score_bucket` | Bucket of the early-tail score (same buckets). |
| `post_discovery_outcome_label` | Block B / D-B post-discovery outcome label (e.g., `EARLY_CONTINUATION`, `LATE_TOP_CHASE`). |
| `reject_attribution_verdict` | Block B / D-C-A reject-to-outcome attribution verdict. |
| `severe_miss_root_cause` | Block B / D-C-B severe miss root cause. |
| `discovery_quality_bucket` | Block B / D-D discovery-quality bucket. |

`cohort_id` is a `sha256` of the canonical, sorted JSON
representation of the cohort key, prefixed `cohort_`. It is stable
across runs.

---

## Sample schema (`PaperShadowSample`)

| Field | Description |
| --- | --- |
| `sample_id` | Stable, deduplicated sample id. |
| `symbol` | Reference symbol (descriptive only). |
| `reference_window` | Reference window string (e.g., `60d`). |
| `first_seen_time_utc` | UTC ISO timestamp of the first sighting. |
| `cohort_key` | The `PaperShadowCohortKey` this sample belongs to. |
| `source_event_refs` | Optional event-record refs from the source reports. |
| `post_seen_mfe_pct` | Post-first-seen Maximum Favourable Excursion (paper, retrospective). |
| `post_seen_mae_pct` | Post-first-seen Maximum Adverse Excursion (paper, retrospective). |
| `remaining_upside_to_peak_pct` | Remaining upside to the reference mover's peak after first sighting. |
| `late_chase` | Boolean: this sample looked like a late top chase. |
| `fake_breakout` | Boolean: this sample looked like a fake breakout. |
| `severe_miss` | Boolean: this sample is a severe miss case. |
| `false_negative_reject` | Boolean: this sample was rejected but went on to be a strong outcome. |
| `data_gap` | Boolean: this sample's evidence trail is incomplete. |
| `evidence_refs` | Pointers back to the source reports / replay artefacts. |
| `source` | `operator_supplied` or `example_fixture`. |

Defensive non-trade markers are always included on serialisation:
`is_paper_shadow_sample=true`, `is_trade=false`,
`is_runtime_patch=false`.

---

## Metrics (`PaperShadowCohortEvaluation`)

| Field | Description |
| --- | --- |
| `sample_count` | Number of samples in the cohort. |
| `usable_discovery_rate` | Share of samples that are NOT data gap, late chase, fake breakout, severe miss, or false-negative reject. |
| `median_mfe_pct` | Median post-first-seen MFE across samples (or `null`). |
| `median_mae_pct` | Median post-first-seen MAE across samples (or `null`). |
| `late_chase_rate` | Share of late-chase samples. |
| `fake_breakout_rate` | Share of fake-breakout samples. |
| `severe_miss_rate` | Share of severe-miss samples. |
| `false_negative_reject_rate` | Share of false-negative-reject samples. |
| `data_gap_rate` | Share of data-gap samples. |
| `confidence_bucket` | `very_low` / `low` / `medium` / `high` / `very_high`. |
| `quality_bucket` | Composite quality bucket (same labels). |
| `recommendation_level` | One of the closed taxonomy levels below. |

---

## Recommendation levels (closed taxonomy)

```
REVIEW_ONLY
PROMISING_FOR_FORWARD_TEST
INCONCLUSIVE
RISKY
REJECTED_BY_EVIDENCE
```

The classifier is conservative by design and intentionally NOT
runtime-tunable. The decision rules are:

  1. **Sample size too small** (`sample_count < 5`) →
     `INCONCLUSIVE`.
  2. **Catastrophic data gap** (`data_gap_rate >= 0.50`) →
     `RISKY` (the rates cannot be trusted).
  3. **High data gap** (`data_gap_rate >= 0.30`) →
     `INCONCLUSIVE`.
  4. **Catastrophic severe miss / fake breakout**
     (`severe_miss_rate >= 0.50` OR `fake_breakout_rate >= 0.50`) →
     `REJECTED_BY_EVIDENCE`.
  5. **Elevated severe miss / fake breakout**
     (`severe_miss_rate >= 0.30` OR `fake_breakout_rate >= 0.30`) →
     `RISKY`.
  6. **Promising path:** `sample_count >= 8` AND
     `usable_discovery_rate >= 0.55` AND
     `late_chase_rate <= 0.20` AND
     `fake_breakout_rate <= 0.15` AND
     `severe_miss_rate <= 0.15` →
     `PROMISING_FOR_FORWARD_TEST`.
  7. **Default:** `REVIEW_ONLY`.

`APPLY`, `DEPLOY`, `ENABLE_LIVE`, `TRADE`, `BUY`, `SELL`,
`GO_LIVE`, `AUTO_APPLY` are intentionally NOT defined and the
engine refuses to ever emit them.

---

## Why this is NOT live trading

  * The engine does not import `app.risk`, `app.execution`,
    `app.exchanges`, `app.telegram`, or `app.config`.
  * The engine does not call any HTTP / network library
    (`requests`, `aiohttp`, `httpx`, `urllib.request`,
    `http.client`, `websocket`, `websockets`, `ccxt`, `binance`,
    `telegram`, `deepseek`, `openai`, `anthropic`, `grpc`,
    `boto3`).
  * The engine does not place an order, sign a request, or read a
    private exchange API.
  * The engine does not produce `buy`, `sell`, `long`, `short`,
    `direction`, `entry`, `exit`, `position_size`, `leverage`,
    `stop`, `stop_loss`, `target`, `take_profit`, `risk_budget`,
    `order`, `execution_command`, `signal_to_trade`, `should_buy`,
    `should_short`, `apply_change`, `deploy_change`, or
    `enable_live`. The recursive `assert_no_forbidden_fields`
    guard refuses to serialise any payload that contains those
    names at any nesting depth.

---

## Why this is NOT auto-tuning

  * The classifier thresholds (sample-size cutoffs, data-gap-rate
    cutoffs, severe-miss / fake-breakout / late-chase cutoffs,
    usable-discovery-rate cutoff) are module-level Python
    constants. They are NOT loaded from runtime config, NOT
    loaded from an LLM, NOT exposed via CLI flags, and NOT
    rewritten by the engine.
  * No part of this phase produces or consumes
    `runtime_config_patch`, `threshold_patch`,
    `symbol_limit_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, or `strategy_parameter_patch`.
  * `auto_tuning_allowed=false` is pinned at the engine, the
    report, the SAFETY_CONTRACT, and every emitted event.

---

## Why this does NOT write runtime config

  * The engine does not import `app.config`.
  * The engine does not write to any path under
    `app/config/**`.
  * The runner only writes the two output files in
    `data/reports/paper_shadow_strategy_validation/` (or the
    operator-supplied `--output-dir`). It does NOT write to
    runtime YAML / JSON config used by the live system.
  * `writes_runtime_config=false` is pinned at the engine, the
    report, the SAFETY_CONTRACT, and every emitted event.

---

## Why this does NOT authorise Phase 12

  * `phase_12_forbidden=true` is pinned at the engine, the
    report, the SAFETY_CONTRACT, and every emitted event.
  * The literal string `"Phase 12"` is intentionally NOT a
    substring of `next_allowed_phase`. A unit test enforces this
    invariant.
  * A `PROMISING_FOR_FORWARD_TEST` verdict only marks a cohort as
    a candidate for the next allowed paper / read-only
    preparation step (Risk / Execution / Capital Safety Matrix
    preparation OR strict walk-forward preparation). It does NOT
    open the door to Phase 12.
  * Phase 12 (live trading / auto-tuning hot path) remains
    forbidden until it is unlocked by a separate, explicit
    operator gate that is OUT OF SCOPE for this phase.

---

## What a successful Paper Shadow run is allowed to authorise

A successful Paper Shadow Strategy Validation run with at least
one `PROMISING_FOR_FORWARD_TEST` cohort only authorises the next
allowed paper / read-only preparation step:

  * **Risk / Execution / Capital Safety Matrix preparation**
    (paper / read-only design and dry-run scoping work that does
    not place an order, does not modify runtime knobs, and does
    not enter Phase 12), OR
  * **strict walk-forward preparation**
    (paper / read-only design and dry-run scoping work that does
    not place an order, does not modify runtime knobs, and does
    not enter Phase 12).

Neither of those preparation steps places a real or paper trade,
neither modifies runtime config, neither auto-tunes, and neither
enters Phase 12. They are themselves separate phases with their
own briefs, their own safety contracts, and their own
implementation PRs.

---

## Allowed event types (added by this phase, all report / export / replay scope)

  * `PAPER_SHADOW_SAMPLE_CREATED`
  * `PAPER_SHADOW_COHORT_EVALUATED`
  * `PAPER_SHADOW_REPORT_GENERATED`

No trade-action events are added. No event is wired into the
runtime hot path. No database schema or migration is touched.

---

## Forbidden by this phase (verbatim)

  * Do not modify `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`, or `app/config/**`.
  * Do not write back to runtime config.
  * Do not modify `symbol_limit`, anomaly thresholds,
    `candidate_pool`, or Regime weights.
  * Do not generate `runtime_config_patch`, `threshold_patch`,
    `symbol_limit_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, or `strategy_parameter_patch`.
  * Do not output `buy`, `sell`, `long`, `short`, `direction`,
    `entry`, `exit`, `position_size`, `leverage`, `stop`,
    `stop_loss`, `target`, `take_profit`, `risk_budget`, `order`,
    `execution_command`, `signal_to_trade`, `should_buy`,
    `should_short`, `apply_change`, `deploy_change`, or
    `enable_live`.
  * Do not call DeepSeek / LLM / network endpoints.
  * Do not send Telegram messages.
  * Do not touch the Binance private API.
  * Do not auto-tune.
  * Do not enter Phase 12.

---

## Files shipped

  * `app/paper_shadow/__init__.py`
  * `app/paper_shadow/strategy_validation.py`
  * `scripts/run_paper_shadow_strategy_validation.py`
  * `tests/unit/test_paper_shadow_strategy_validation.py`
  * `docs/PHASE_11C_1D_B_PAPER_SHADOW_STRATEGY_VALIDATION.md`
    (this document)

Updated: `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
`docs/CHANGELOG.md`.

---

## Tests

```
python -m pytest tests/unit/test_paper_shadow_strategy_validation.py -q
```

ships **22 PASSING** tests covering the full safety contract for
this phase.

```
python -m pytest tests/unit -q
```

reports **3368 PASSING** tests, **0 failures** (was 3346 before
this phase; +22 from this phase).

---

## Allowed transitions

| From | To | Allowed? |
| --- | --- | --- |
| Phase 11C.1D-B IN_REVIEW | Phase 11C.1D-B ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-B IN_REVIEW | Risk / Execution / Capital Safety Matrix preparation | After a successful paper shadow run with at least one `PROMISING_FOR_FORWARD_TEST` cohort; transition itself is the next phase's responsibility. |
| Phase 11C.1D-B IN_REVIEW | Strict walk-forward preparation | After a successful paper shadow run with at least one `PROMISING_FOR_FORWARD_TEST` cohort; transition itself is the next phase's responsibility. |
| any | Phase 12 | **FORBIDDEN.** |

A `PROMISING_FOR_FORWARD_TEST` recommendation does **not**
authorise a forward-test run on its own — it only marks the cohort
as a candidate for the next phase's preparation work. The
forward-test phase itself is out of scope for Phase 11C.1D-B.

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.
