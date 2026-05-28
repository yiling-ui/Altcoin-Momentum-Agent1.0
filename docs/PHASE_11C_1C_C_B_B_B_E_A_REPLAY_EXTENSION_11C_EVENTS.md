# Phase 11C.1C-C-B-B-B-E-A — Replay Extension for 11C Adaptive Events v0

**Status:** IN_REVIEW
**Block:** Block C1 (Replay Extension v0)
**Mode:** paper / replay-only
**Phase 12:** FORBIDDEN
**Auto-tuning:** disallowed
**Live trading:** disallowed
**Cloud closeout:** out of scope (this phase does NOT close cloud
evidence)

---

## Purpose

Extend the existing `app/replay/` engine so the Phase 11C
adaptive / discovery / evidence event chain produced by Block A and
Block B can be reconstructed deterministically into a small set of
read-only value objects. The objects feed:

  - the upcoming **Phase 11C.1C-C-B-B-B-E-B Reflection Extension for
    11C Adaptive Events v0** (the only phase a successful Phase
    11C.1C-C-B-B-B-E-A can authorise);
  - operator audit / replay over the events.db file;
  - regression tests that exercise the Block A / Block B chain at the
    event-stream level.

The extension is **read-only**:

  - it does not append, mutate, or reorder rows in `events.db`;
  - it does not derive runtime parameters or threshold patches;
  - it never produces direction, sizing, leverage, stop, target, or
    risk-budget fields;
  - it never imports `app.risk`, `app.execution`, `app.exchanges`,
    `app.llm`, or `app.telegram`.

## Supported event groups

The extension consumes (read-only) the following event-type groups:

| Group | Events |
|-------|--------|
| **Discovery timeline** | `MARKET_REGIME_ASSESSED`, `CANDIDATE_STAGE_CLASSIFIED`, `OPPORTUNITY_SCORED`, `STRATEGY_MODE_SELECTED`, `CLUSTER_CONTEXT_ATTACHED`, `LABEL_QUEUE_ENQUEUED` |
| **Candidate lifecycle (LABEL\_\*)** | `LABEL_TRACKING_STARTED`, `LABEL_WINDOW_UPDATED`, `LABEL_WINDOW_COMPLETED` |
| **Tail outcome (TAIL_LABEL\_\* / MISSED_TAIL\_\* / FAKE_BREAKOUT\_\*)** | `TAIL_LABEL_ASSIGNED`, `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED` |
| **Mover coverage (MOVER_CAPTURE\_\* / HISTORICAL_MOVER_COVERAGE\_\*)** | `MOVER_CAPTURE_PATH_AUDITED`, `MOVER_CAPTURE_RECALL_AUDIT_GENERATED`, `HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`, `HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED` |
| **Post-discovery outcome (POST_DISCOVERY_OUTCOME\_\*)** | `POST_DISCOVERY_OUTCOME_EVALUATED`, `POST_DISCOVERY_OUTCOME_REPORT_GENERATED` |
| **Reject attribution (REJECT_TO_OUTCOME\_\*)** | `REJECT_TO_OUTCOME_CASE_ATTRIBUTED`, `REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED`, `FALSE_NEGATIVE_REJECT_DETECTED`, `CORRECT_PROTECTIVE_REJECT_CONFIRMED` |
| **Severe miss (SEVERE_MISSED_TAIL\_\*)** | `SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED`, `SEVERE_MISSED_TAIL_TRIAGE_GENERATED`, `SEVERE_MISS_ESCALATION_REQUIRED` |
| **Discovery quality (DISCOVERY_QUALITY\_\*)** | `DISCOVERY_QUALITY_BUCKET_EVALUATED`, `DISCOVERY_QUALITY_SCORECARD_GENERATED` |
| **Strategy validation (STRATEGY_VALIDATION\_\*)** | `STRATEGY_VALIDATION_SAMPLE_CREATED`, `STRATEGY_VALIDATION_REPORT_GENERATED`, `STRATEGY_MODE_VALIDATED`, `CANDIDATE_STAGE_VALIDATED`, `SCORE_BUCKET_VALIDATED`, `CLUSTER_EXPOSURE_ASSESSED`, `CLUSTER_LEADER_VALIDATED`, `STRATEGY_VALIDATION_DATASET_BUILT`, `STRATEGY_VALIDATION_DATASET_EXPORTED`, `STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED` |
| **Paper alpha (PAPER_ALPHA\_\*)** | `PAPER_ALPHA_GATE_EVALUATED`, `PAPER_ALPHA_RULE_EVALUATED`, `PAPER_ALPHA_COHORT_EVALUATED`, `PAPER_ALPHA_REPORT_GENERATED` |
| **Regime cluster (REGIME_CLUSTER\_\*)** | `REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`, `REGIME_CLUSTER_COHORT_SUMMARY_GENERATED` |

The full union is exported from
`app.replay.adaptive_replay_11c.ADAPTIVE_REPLAY_EVENT_TYPES`.

## Replay objects

All replay objects are immutable (`@dataclass(frozen=True)`) and expose
a deterministic `to_payload() -> dict` method. Every payload carries
`schema_version`, `source_phase=phase_11c_1c_c_b_b_b_e_a`,
`replay_object`, and a `status` field (`ok` / `partial` / `degraded`).

| Replay object | Reconstructs |
|---------------|-----------------------------------------|
| `ReplayDiscoveryTimeline` | One opportunity's six-step discovery chain (`MARKET_REGIME_ASSESSED` → `LABEL_QUEUE_ENQUEUED`). |
| `ReplayCandidateLifecycle` | One `LabelTrackingRecord` lifecycle: `LABEL_TRACKING_STARTED` → `LABEL_WINDOW_UPDATED*` → `LABEL_WINDOW_COMPLETED`. |
| `ReplayTailOutcome` | One `TAIL_LABEL_ASSIGNED` outcome plus optional `MISSED_TAIL_DETECTED` / `FAKE_BREAKOUT_DETECTED` flags, grouped by `(opportunity_id, window_name)`. |
| `ReplayMoverCoverageCase` | One mover-capture or historical-60d coverage record, pinned to its parent rollup event. |
| `ReplayPostDiscoveryOutcomeCase` | One `POST_DISCOVERY_OUTCOME_EVALUATED` record with detection-timing / outcome labels and price-path metrics. |
| `ReplayRejectAttributionCase` | One reject-to-outcome case with verdict / reasons and links to `FALSE_NEGATIVE_REJECT_DETECTED` / `CORRECT_PROTECTIVE_REJECT_CONFIRMED` siblings. |
| `ReplaySevereMissCase` | One severe-missed-tail root-cause record with optional `SEVERE_MISS_ESCALATION_REQUIRED` link. |
| `ReplayDiscoveryQualityCase` | One discovery-quality bucket / scorecard pair. |

A top-level `AdaptiveReplayBundle` aggregates every list and pins
`input_event_count`, `replay_record_event_count`, and
`skipped_event_count` for the event-count invariant.

The public extension class is `AdaptiveEventReplayExtension`, with two
entry points:

  - `replay_all(*, since_ts, until_ts, symbol)` reads from
    `EventRepository` (read-only) and returns a bundle.
  - `replay_from_events(events)` operates on an in-memory event list
    (used by tests).

## Acceptance criteria

A run of `tests/unit/test_replay_11c_adaptive_events.py` is
**ACCEPTED** for Phase 11C.1C-C-B-B-B-E-A iff:

  1. The brief's required test surface (10 numbered checks) all pass.
  2. `replay_record_event_count == input_event_count` for every
     supported event group (the brief's "replay count == input event
     count" rule).
  3. Missing fields in any input event do **not** raise; the affected
     replay object reports `status="partial"` (record is intact but
     fields are missing) or `status="degraded"` (parent rollup
     missing, or the canonical anchor event is absent).
  4. Every replay object preserves `evidence_refs` or
     `record_event_id` / `parent_event_id` so a downstream auditor
     can pin the replay output back to its source event row.
  5. The replay source code does **not** import `app.risk`,
     `app.execution`, `app.exchanges`, `app.llm`, or `app.telegram`.
  6. The replay source code does **not** define order-creation,
     order-cancellation, leverage-mutation, or runtime-config-patch
     functions.
  7. No replay payload key is in `FORBIDDEN_REPLAY_PAYLOAD_KEYS`
     (`buy`, `sell`, `long`, `short`, `position_size`, `leverage`,
     `stop`, `stop_loss`, `target`, `take_profit`, `risk_budget`,
     `runtime_config_patch`, etc.).
  8. The replay output is deterministic under input reordering
     (sort key: `(timestamp, event_type, event_id)`).

After acceptance the phase status is **IN_REVIEW** until a maintainer
reviews and merges the implementation PR. The phase status is **NEVER**
auto-promoted to `ACCEPTED` by this implementation.

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

  - **This phase does NOT authorise live trading.** Every safety
    property above stays at its default (paper-only) value.
  - **This phase does NOT authorise auto-tuning.** No threshold,
    weight, or candidate-pool patch is produced. Replay payloads
    explicitly carry `auto_tuning_allowed=False` where applicable.
  - **This phase does NOT close out cloud evidence.** Block C
    closeout (Phase 11C.1C-C-B-B-B-E-Z) is the only place where cloud
    evidence is closed.
  - **A successful Phase 11C.1C-C-B-B-B-E-A only allows the next
    phase to start, namely Phase 11C.1C-C-B-B-B-E-B Reflection
    Extension for 11C Adaptive Events v0.** It does **not** allow any
    other phase to start. Phase 12 remains **FORBIDDEN**.

## Test command

```bash
python -m pytest tests/unit/test_replay_11c_adaptive_events.py -q
```

Optional regression run:

```bash
python -m pytest tests/unit -q
```
