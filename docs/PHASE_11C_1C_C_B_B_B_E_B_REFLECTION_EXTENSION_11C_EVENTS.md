# Phase 11C.1C-C-B-B-B-E-B — Reflection Extension for 11C Adaptive Events v0

**Status:** IN_REVIEW
**Block:** Block C2 (Reflection Extension v0)
**Mode:** paper / report-only
**Phase 12:** FORBIDDEN
**Auto-tuning:** disallowed
**Live trading:** disallowed
**LLM / DeepSeek:** disallowed
**Cloud closeout:** out of scope (this phase does NOT close cloud
evidence)

---

## Purpose

Extend the existing `app/reflection/` engine so the Phase 11C
adaptive / discovery / evidence event chain produced by Block A and
Block B can be reflected on deterministically into a small set of
read-only structured tags / summaries / counts / warnings. The
output feeds:

  - operator audit / triage workflows over the events.db file;
  - regression tests that exercise the Block A / Block B chain at
    the reflection level;
  - the next-allowed phase **C3 Evidence Contract Baseline** — the
    only successor a successful Phase 11C.1C-C-B-B-B-E-B authorises.

Reflection only emits **structured tags / summaries / counts /
warnings**. It does NOT and CANNOT:

  - emit trade advice (no `buy` / `sell` / `long` / `short` /
    `direction` / `side` / `entry` / `exit`);
  - emit sizing or risk numbers (no `position_size` / `leverage` /
    `stop` / `stop_loss` / `target` / `take_profit` / `risk_budget`);
  - emit a runtime config patch (no `runtime_config_patch` /
    `symbol_limit_patch` / `threshold_patch` / `candidate_pool_patch`
    / `regime_weight_patch`);
  - call an LLM, DeepSeek, or any natural-language model;
  - depend on chat history;
  - mutate `events.db`, runtime parameters, or any shared state;
  - import `app.risk`, `app.execution`, `app.exchanges`, `app.llm`,
    or `app.telegram`.

## Supported event groups

The engine consumes (read-only) the following event groups:

| Group | Events |
|-------|--------|
| **Candidate lifecycle (LABEL\_\*)** | `LABEL_TRACKING_STARTED`, `LABEL_WINDOW_UPDATED`, `LABEL_WINDOW_COMPLETED` |
| **Tail outcome (TAIL_LABEL\_\* / MISSED_TAIL\_\* / FAKE_BREAKOUT\_\*)** | `TAIL_LABEL_ASSIGNED`, `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED` |
| **Mover coverage (MOVER_CAPTURE\_\* / HISTORICAL_MOVER_COVERAGE\_\*)** | `MOVER_CAPTURE_PATH_AUDITED`, `MOVER_CAPTURE_RECALL_AUDIT_GENERATED`, `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`, `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED` |
| **Post-discovery outcome (POST_DISCOVERY_OUTCOME\_\*)** | `POST_DISCOVERY_OUTCOME_EVALUATED`, `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` |
| **Reject attribution (REJECT_TO_OUTCOME\_\*)** | `REJECT_TO_OUTCOME_CASE_ATTRIBUTED`, `REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED`, `FALSE_NEGATIVE_REJECT_DETECTED`, `CORRECT_PROTECTIVE_REJECT_CONFIRMED` |
| **Severe miss (SEVERE_MISSED_TAIL\_\*)** | `SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED`, `SEVERE_MISSED_TAIL_TRIAGE_GENERATED`, `SEVERE_MISS_ESCALATION_REQUIRED` |
| **Discovery quality (DISCOVERY_QUALITY\_\*)** | `DISCOVERY_QUALITY_BUCKET_EVALUATED`, `DISCOVERY_QUALITY_SCORECARD_GENERATED` |
| **Strategy validation (STRATEGY_VALIDATION\_\*)** | `STRATEGY_VALIDATION_SAMPLE_CREATED`, `STRATEGY_MODE_VALIDATED`, `CANDIDATE_STAGE_VALIDATED`, `SCORE_BUCKET_VALIDATED`, `CLUSTER_EXPOSURE_ASSESSED`, `CLUSTER_LEADER_VALIDATED`, `STRATEGY_VALIDATION_DATASET_BUILT` |
| **Paper alpha (PAPER_ALPHA\_\*)** | `PAPER_ALPHA_GATE_EVALUATED`, `PAPER_ALPHA_RULE_EVALUATED`, `PAPER_ALPHA_COHORT_EVALUATED`, `PAPER_ALPHA_REPORT_GENERATED` |
| **Regime cluster (REGIME_CLUSTER\_\*)** | `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED` |

The full union is exported from
`app.reflection.adaptive_11c.ADAPTIVE_REFLECTION_EVENT_TYPES`.

This phase introduces **no new event types**. Any new event-type
introduction is scoped to a future reflection/report event only and
is explicitly out of scope for this implementation PR.

## Reflection tags

Closed enum `AdaptiveReflectionTag` (string values, JSON-safe):

| Tag | Description (descriptive only) |
|-----|--------------------------------|
| `early_discovery` | Discovery happened early in the move. |
| `late_discovery` | Discovery happened late in the move. |
| `late_top_chase` | Trade entered after the move was mostly over. |
| `post_discovery_no_edge` | After discovery, no clear edge was visible. |
| `missed_tail` | A tail move was not captured. |
| `severe_miss` | A tail move was severely / critically missed. |
| `candidate_evicted_before_tail` | The candidate was evicted from the pool before the tail. |
| `risk_rejected_then_moved` | Risk Engine rejected, then the candidate ran. |
| `false_negative_reject` | The reject was wrong given the outcome (operator review). |
| `correct_protective_reject` | The reject was the right call given the outcome. |
| `weak_pre_anomaly` | Pre-anomaly signal was weak / not triggered. |
| `fake_breakout_detected` | Move shape consistent with a fake breakout. |
| `data_gap` | Source events flagged a data gap / unreliable data. |
| `insufficient_history` | Not enough historical price-path data to evaluate. |
| `degraded_discovery_quality` | Discovery-quality scorecard / bucket reports degraded. |
| `insufficient_evidence` | Reflection has insufficient evidence to assign a richer tag. |
| `needs_operator_review` | Operator should review this case. |
| `needs_data_recovery` | Underlying data needs recovery / re-collection. |
| `needs_rule_review` | Rule / threshold / policy should be reviewed (paper-only review; **NOT** auto-tuning). |

Tags are additive (a single case may carry several) and drawn from
this enum only. Reflection NEVER produces a free-form natural-
language tag.

## Reflection objects

All reflection objects are immutable (`@dataclass(frozen=True)`) and
expose a deterministic `to_payload() -> dict` method. Every payload
carries `schema_version`, `source_phase=phase_11c_1c_c_b_b_b_e_b`,
`source_module=reflection_11c_adaptive_engine`, and a
`reflection_object` discriminator.

| Object | Role |
|--------|------|
| `AdaptiveReflectionInput` | Read-only bundle of `Event`s the engine consumes. |
| `AdaptiveReflectionCase` | One reflection case per supported event. Carries `case_id`, `symbol`, `opportunity_id`, `event_type`, `tags`, `severity`, `evidence_refs`, `needs_operator_review`, `needs_data_recovery`, `needs_rule_review`, `auto_tuning_allowed=False`, `warnings`. |
| `AdaptiveReflectionSummary` | Aggregate roll-up across many cases with deterministic counts (`tag_counts`, `severity_counts`, `needs_operator_review_count`, etc.) and `auto_tuning_allowed=False`. |
| `Reflection11CAdaptiveEngine` | Pure, stateless engine with `reflect_event(ev)` and `reflect_events(events)`. |
| `AdaptiveReflectionSeverity` | Closed severity vocabulary (`info` / `low` / `medium` / `high` / `severe` / `unknown`). |

Every `AdaptiveReflectionCase.evidence_refs` always carries the
source `event.event_id` as a fallback so a downstream auditor can pin
a case back to its row even when the source payload omits explicit
`evidence_refs`.

## Acceptance criteria

A run of `tests/unit/test_reflection_11c_adaptive_events.py` is
**ACCEPTED** for Phase 11C.1C-C-B-B-B-E-B iff:

  1. `POST_DISCOVERY_OUTCOME_*` events produce the
     `late_top_chase` / `early_discovery` / `post_discovery_no_edge`
     / `missed_tail` tags as documented (per `outcome_label`).
  2. `REJECT_TO_OUTCOME_*` events produce the
     `false_negative_reject` / `correct_protective_reject` tags as
     documented (per `verdict`); `DATA_QUALITY_REJECT` additionally
     produces `data_gap` and sets `needs_data_recovery=True`.
  3. `SEVERE_MISSED_TAIL_*` events produce the `severe_miss` /
     `missed_tail` tags; data-related root causes additionally
     produce `data_gap` + `needs_data_recovery` and rule-related
     root causes produce `needs_rule_review`.
  4. `DISCOVERY_QUALITY_*` events with `quality_bucket=DEGRADED`
     (or sufficiently weak scorecard metrics) produce the
     `degraded_discovery_quality` tag and set
     `needs_rule_review=True`.
  5. `HISTORICAL_MOVER_COVERAGE_*` records with
     `coverage_status=MISSED` produce the `missed_tail` tag.
  6. Missing fields in any input event do **not** raise; the
     affected case is flagged with `insufficient_evidence` and a
     descriptive `warnings` entry.
  7. `evidence_refs` are preserved on every emitted case
     (`event_id` always present as a fallback).
  8. Every emitted case + summary carries
     `auto_tuning_allowed=False`. Even if a malicious caller
     constructs a case with `auto_tuning_allowed=True`, the
     `to_payload()` serialiser emits `False`.
  9. The reflection module does **not** import `app.risk`,
     `app.execution`, `app.exchanges`, `app.llm`, or `app.telegram`.
 10. No emitted payload contains a forbidden key (`buy`, `sell`,
     `long`, `short`, `position_size`, `leverage`, `stop`,
     `stop_loss`, `target`, `take_profit`, `risk_budget`,
     `runtime_config_patch`, etc.). The module ships a recursive
     guard `_assert_no_forbidden_keys` invoked from every
     `to_payload()`.
 11. Reflection is deterministic under input reordering (sort key
     `(timestamp, event_type, event_id)`).

After acceptance, the phase status is **IN_REVIEW** until a
maintainer reviews and merges the implementation PR. The phase status
is **NEVER** auto-promoted to `ACCEPTED` by this implementation.

## Safety boundary

| Property | Value |
|----------|-------|
| `mode` | `paper` |
| `live_trading` | `False` |
| `exchange_live_orders` | `False` |
| `right_tail` | `False` |
| `llm` | `False` |
| `telegram_outbound_enabled` | `False` |
| `binance_private_api_enabled` | `False` |
| Binance API key / secret | not used |
| Signed endpoint | not used |
| Private websocket | not used |
| `listenKey` | not used |
| Real Telegram outbound | not used |
| DeepSeek trade decision | not used |
| Phase 12 | **FORBIDDEN** |
| Auto-tuning | **disallowed** |
| Modifies `app/risk/**` | **No** |
| Modifies `app/execution/**` | **No** |
| Modifies `app/exchanges/**` | **No** |
| Modifies `app/llm/**` | **No** |
| Modifies `app/telegram/**` | **No** |
| Modifies `app/config/**` | **No** |
| Modifies `symbol_limit` | **No** |
| Modifies `anomaly_threshold` | **No** |
| Modifies `candidate_pool` | **No** |
| Modifies regime weights | **No** |
| Generates `runtime_config_patch` | **No** |

## Authorisation scope

  - **This does NOT authorise live trading.** Every safety property
    above stays at its default (paper-only) value.
  - **This does NOT authorise auto-tuning.** Every emitted case +
    summary carries `auto_tuning_allowed=False`. The
    `needs_rule_review` tag is a paper-only operator-review signal
    and **NEVER** a runtime-knob change.
  - **This does NOT use AI / DeepSeek.** No LLM client, no DeepSeek
    transport, no natural-language generation. Reflection only emits
    closed-vocabulary tags + structured warnings.
  - **This does NOT close out cloud evidence.** Block C closeout is
    a separate, future PR.
  - **A successful Phase 11C.1C-C-B-B-B-E-B only authorises
    Phase 11C.1C-C-B-B-B-E-C "C3 Evidence Contract Baseline" to
    start.** It does **not** allow any other phase to start. Phase
    12 remains **FORBIDDEN**.

## Test command

```bash
python -m pytest tests/unit/test_reflection_11c_adaptive_events.py -q
```

Optional regression run:

```bash
python -m pytest tests/unit -q
```
