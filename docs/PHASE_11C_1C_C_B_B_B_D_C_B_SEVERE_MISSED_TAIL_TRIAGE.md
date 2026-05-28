# Phase 11C.1C-C-B-B-B-D-C-B — Severe Missed Tail Triage v0

*严重漏捕右尾归因 v0*

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**

## Purpose

Phase 11C.1C-C-B-B-B-D-A described the *discovery* layer ("did we
see the mover?"). Phase 11C.1C-C-B-B-B-D-B / B.1 described the
*post-discovery outcome* ("how much room remained, and was the
price path even available?"). Phase 11C.1C-C-B-B-B-D-C-A closed
the loop between **candidate-level reject decisions** and the
post-discovery outcome ("was the reject the right call?").

The project still lacked one piece: when a meaningful mover such
as `RAVEUSDT` or `STOUSDT` shows up in the historical 60D mover
reference set but not in the radar's captured set, *why* did we
miss it? The four upstream layers each give a partial answer:

  - D-A says "this mover was missed / partially captured".
  - D-B / B1.1 says "the post-first-seen price path is missing /
    insufficient" or "outcome label is `INSUFFICIENT_PRICE_PATH`
    / `MISSED_STRONG_TAIL`".
  - B2-A says "the Risk Engine rejected this candidate, and the
    reject was protective / a false negative / insufficient
    evidence".

But none of them, on their own, attributes the **single
descriptive root cause** that an operator can route to a queue
("data recovery", "operator review", "rule review"). That is
what this phase ships.

The Severe Missed Tail Triage v0 layer consumes the **simplified**
outputs of D-A / D-B / B1.1 / B2-A and emits, per audited severe
miss, a closed root-cause taxonomy plus a closed severity
taxonomy. It refuses to fabricate a root cause when evidence is
insufficient, and it never authorises a runtime change.

This phase turns severe-miss cases such as `RAVEUSDT` /
`STOUSDT` from "we missed it" into **auditable root cause**.

The phase is **strictly attribution only** — no parameter
changes, no trade suggestions, no rule modifications.

## Inputs

`SevereMissTriageInput` carries the simplified outputs of the
upstream layers:

  - **identity** — `symbol`, `reference_window`;
  - **D-A signals** — `capture_status`, `d_a_miss_reason`,
    `candidate_pool_seen`, `candidate_pool_evicted`,
    `universe_eligible`, `symbol_limit_included`;
  - **D-B signals** — `d_b_outcome_label`,
    `d_b_detection_timing_label`, `post_seen_mfe_pct`,
    `post_seen_mae_pct`, `remaining_upside_to_peak_pct`;
  - **B1.1 signals** — `price_path_status`,
    `price_path_missing_reason`;
  - **B2-A signals** — `reject_attribution_verdict`,
    `reject_attribution_primary_reason`;
  - **data-quality flags** — `data_gap_flags: tuple[str, ...]`;
  - **evidence pointers** — `evidence_refs: tuple[str, ...]`,
    `notes: str | None`.

The bundle is paper / report / evidence only. **No field
authorises a real trade or modifies any runtime knob.**

## Outputs

### `SevereMissTriageRecord`

One per audited severe miss. Carries:

  - identity (`symbol`, `reference_window`);
  - `severity` (closed `SevereMissSeverity` taxonomy);
  - `root_cause` (closed `SevereMissRootCause` taxonomy);
  - `secondary_causes` — up to six descriptive secondary
    signals;
  - `needs_operator_review: bool` — route to operator queue;
  - `needs_data_recovery: bool` — route to data-recovery
    backlog;
  - `needs_rule_review: bool` — route to rule-review backlog
    (NEVER auto-apply);
  - **`auto_tuning_allowed: bool` — hard-pinned to `False`** in
    every serialised payload, regardless of severity or root
    cause;
  - `evidence_refs`, `warnings`;
  - `schema_version`, `source_phase`.

### `SevereMissTriageReport`

Aggregate roll-up across many records. Carries:

  - `total_records`;
  - `severe_count`;
  - `critical_count`;
  - `insufficient_evidence_count`;
  - `root_cause_summary: dict[str, int]`;
  - `needs_operator_review_symbols`;
  - `needs_data_recovery_symbols`;
  - `needs_rule_review_symbols`;
  - `notable_symbols` — symbols deserving human attention
    (SEVERE / CRITICAL severity OR a system-rule-gap or
    risk-related root cause);
  - `evidence_refs`, `warnings`;
  - **`auto_tuning_allowed: bool` — hard-pinned to `False`** even
    when `critical_count > 0`.

## Root cause taxonomy (closed)

`SevereMissRootCause` is a closed set of string constants:

  - `UNIVERSE_GAP` — the candidate was not in the eligible
    universe at all (delisted, non-USDT-perpetual, out of
    scope).
  - `SYMBOL_LIMIT_GAP` — the candidate was universe-eligible but
    excluded by `symbol_limit`. Routes to **rule review**, never
    to automatic `symbol_limit` expansion.
  - `CANDIDATE_POOL_EVICTED` — the candidate was observed by the
    radar / candidate pool but was evicted before promotion.
    Routes to operator review; does **not** authorise automatic
    capacity expansion.
  - `THRESHOLD_TOO_STRICT` — reserved for future briefs that
    accumulate cohort-level evidence; **NEVER** asserted from a
    single coin.
  - `PRE_ANOMALY_WEAK` — reserved for future briefs.
  - `ANOMALY_TOO_LATE` — reserved for future briefs.
  - `WS_DATA_GAP` — the candidate was missed because the WS feed
    was stale at the relevant time.
  - `REST_REFERENCE_GAP` — the candidate was missed because the
    REST reference snapshot was missing.
  - `EVENT_HISTORY_MISSING` — the candidate was missed because
    the EventRepository event history is incomplete for that
    window.
  - `PRICE_PATH_MISSING` — D-B / B1.1 reported the post-first-seen
    price path is missing. Routes to **data recovery** only;
    does **NOT** assert any threshold problem.
  - `PRICE_PATH_INSUFFICIENT` — D-B / B1.1 reported the
    post-first-seen price path has too few points to evaluate.
  - `NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME` — B1.1
    daily-bucket adapter reported the local Historical Market
    Store has no top-mover row whose day window covers the
    candidate's `first_seen_time_utc_ms`. **This is the
    `RAVEUSDT` / `STOUSDT` cluster's current label.**
  - `RISK_REJECTED_PROTECTIVE` — B2-A verdict was one of
    `CORRECT_PROTECTIVE_REJECT` / `STOP_SAFETY_REJECT` /
    `DATA_QUALITY_REJECT` / `LIQUIDITY_PROTECTIVE_REJECT` /
    `MANIPULATION_PROTECTIVE_REJECT` / `REBASE_PROTECTIVE_REJECT`
    / `SYSTEM_SAFETY_REJECT`. Severity is `LOW` — the reject was
    the right call.
  - `RISK_REJECTED_FALSE_NEGATIVE` — B2-A verdict was
    `FALSE_NEGATIVE_REJECT`. Severity is `CRITICAL`. Routes to
    operator review **and** rule review. **Does NOT authorise
    rule relaxation.** `auto_tuning_allowed` remains `False`.
  - `STRATEGY_MODE_FALSE_NEGATIVE` — B2-A verdict was
    `STRATEGY_MODE_FALSE_NEGATIVE`. Severity is `HIGH`. Routes to
    operator review and rule review.
  - `LABEL_WINDOW_TOO_SHORT` — reserved for future briefs.
  - `TRUE_DISCOVERY_FAILURE` — none of the above and
    `capture_status=missed` AND `post_seen_mfe_pct` is
    meaningfully positive. Severity is `SEVERE`.
  - `INSUFFICIENT_EVIDENCE` — `evidence_refs` are missing OR
    every triage signal is absent. Triage refuses to fabricate a
    root cause.
  - `UNKNOWN` — fall-through. Routes to operator review.

## Severity taxonomy (closed)

`SevereMissSeverity` is a closed set of string constants:

  - `LOW` — the case is informational (e.g. correctly protective
    risk reject). No queue action required.
  - `MEDIUM` — data gap or scope-eligibility issue. Routes to
    data recovery (price path) or operator review (universe).
  - `HIGH` — system-correctable miss (`SYMBOL_LIMIT_GAP`,
    `CANDIDATE_POOL_EVICTED`, `STRATEGY_MODE_FALSE_NEGATIVE`).
    Routes to operator / rule-review queue.
  - `SEVERE` — `TRUE_DISCOVERY_FAILURE`. Significant miss with
    no upstream gap to attribute it to; routes to operator
    review.
  - `CRITICAL` — `RISK_REJECTED_FALSE_NEGATIVE`. Routes to
    operator review **and** rule review. **NOT** permission to
    relax the Risk Engine.
  - `INSUFFICIENT_EVIDENCE` — assigned when the engine refuses
    to fabricate a root cause.

`CRITICAL` is an **escalation signal**, not a trade authority
signal. The Risk Engine remains the single trade-decision gate.

## Triage decision flow

The engine evaluates the input in this exact priority order. The
first matching rule wins; remaining rules are surfaced as
`secondary_causes` for human review.

1. **Insufficient evidence** — no `evidence_refs`, no `symbol`,
   or no triage signals at all.
2. **Universe gap** — `universe_eligible=False`.
3. **Symbol-limit gap** — `symbol_limit_included=False`.
4. **Candidate pool evicted** — `candidate_pool_seen=True` AND
   `candidate_pool_evicted=True`.
5. **Price path missing** — `price_path_status` ∈
   `{missing, absent, insufficient, …}` OR
   `price_path_missing_reason` is set. The engine maps the
   `no_top_mover_row_covering_first_seen_time` reason to its
   own root-cause label so the `RAVEUSDT` / `STOUSDT` cluster
   keeps its dedicated taxonomy slot. **Routes to data
   recovery only**; **MUST NOT** assert a threshold problem.
6. **Risk rejected protective** — `reject_attribution_verdict`
   ∈ `PROTECTIVE_REJECT_ATTRIBUTION_VERDICTS`.
7. **Risk rejected false negative** —
   `reject_attribution_verdict == "FALSE_NEGATIVE_REJECT"`.
8. **Strategy mode false negative** —
   `reject_attribution_verdict == "STRATEGY_MODE_FALSE_NEGATIVE"`.
9. **True discovery failure** — none of the above AND
   `capture_status=missed` AND
   `post_seen_mfe_pct >= true_discovery_failure_mfe_threshold`
   (default 5%).
10. **Unknown** — fall-through. Routes to operator review.

## Event types

The phase introduces three new typed events on
:class:`app.core.events.EventType`:

  - `SEVERE_MISSED_TAIL_TRIAGE_GENERATED` — one
    :class:`SevereMissTriageReport` was emitted across many
    records. Carries the aggregate counts, the root-cause
    summary, and the operator-review / rule-review /
    data-recovery symbol lists.
  - `SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED` — one
    :class:`SevereMissTriageRecord` was emitted for one
    audited candidate. Carries the descriptive root_cause +
    severity + `evidence_refs`.
  - `SEVERE_MISS_ESCALATION_REQUIRED` — shorthand event for
    the operator-review / rule-review queue: one record was
    attributed `SEVERE` / `CRITICAL` severity OR a
    rule-related root cause that needs human review.

Every emitted payload:

  - **MUST** include `evidence_refs`;
  - **MUST** carry `auto_tuning_allowed=False`;
  - **MUST NOT** include `buy` / `sell` / `long` / `short` /
    `direction` / `side` / `entry` / `exit` / `position_size` /
    `leverage` / `stop` / `stop_loss` / `target` /
    `take_profit` / `risk_budget` / `order` /
    `execution_command` / `runtime_config_patch` /
    `symbol_limit_patch` / `threshold_patch` /
    `candidate_pool_patch` / `regime_weight_patch`.

The `assert_payload_has_no_forbidden_keys` recursive guard
defends every emission point; a planted forbidden key raises
`SevereMissedTailTriageForbiddenFieldError` at emission time.

## Acceptance criteria

The brief mandates the following per-case acceptance tests
(implemented in
`tests/unit/test_severe_missed_tail_triage.py`):

1. **Price path missing (RAVE / STO style).** Inputs with
   `price_path_missing_reason=no_top_mover_row_covering_first_seen_time`
   route to `needs_data_recovery=True` and **MUST NOT** assert
   any threshold problem.
2. **Candidate pool evicted.** Root cause is
   `CANDIDATE_POOL_EVICTED`; severity `HIGH`.
3. **Symbol limit gap.** Root cause is `SYMBOL_LIMIT_GAP`;
   `needs_rule_review=True`; `auto_tuning_allowed=False`.
4. **Universe gap.** Root cause is `UNIVERSE_GAP`.
5. **Risk rejected protective.** B2-A verdict is one of
   `CORRECT_PROTECTIVE_REJECT` / `STOP_SAFETY_REJECT` /
   `DATA_QUALITY_REJECT` / `LIQUIDITY_PROTECTIVE_REJECT` /
   `MANIPULATION_PROTECTIVE_REJECT`. Root cause is
   `RISK_REJECTED_PROTECTIVE`.
6. **Risk rejected false negative.** B2-A verdict is
   `FALSE_NEGATIVE_REJECT`. Root cause is
   `RISK_REJECTED_FALSE_NEGATIVE`; severity `CRITICAL`;
   `auto_tuning_allowed=False`.
7. **Strategy mode false negative.** B2-A verdict is
   `STRATEGY_MODE_FALSE_NEGATIVE`. Root cause is
   `STRATEGY_MODE_FALSE_NEGATIVE`.
8. **True discovery failure.** No other gap;
   `capture_status=missed`; MFE meaningfully positive. Root
   cause is `TRUE_DISCOVERY_FAILURE`; severity `SEVERE`.
9. **Insufficient evidence.** Missing `evidence_refs` or no
   signals at all. Severity `INSUFFICIENT_EVIDENCE`; root cause
   `INSUFFICIENT_EVIDENCE`. **MUST NOT** fabricate a more
   specific reason.
10. **Forbidden fields absent.** No record / report payload may
    contain a trade-authority or runtime-tuning field.
11. **Forbidden imports.** `severe_missed_tail_triage.py` MUST
    NOT import `app.risk` / `app.execution` / `app.exchanges` /
    `app.llm` / `app.telegram`.

## Safety boundary

Held end-to-end across this phase:

  - `mode = paper`
  - `live_trading = False`
  - `exchange_live_orders = False`
  - `right_tail = False`
  - `llm = False`
  - `telegram_outbound_enabled = False`
  - `binance_private_api_enabled = False`
  - no Binance API key
  - no Binance API secret
  - no signed endpoint
  - no account / order / position / leverage / margin endpoint
  - no private websocket
  - no `listenKey`
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

## Why this phase does NOT authorise auto-tuning

The brief's hardest invariant is that root-cause triage MUST
NEVER drive an automatic parameter change. Every emitted record
and every emitted report carries `auto_tuning_allowed=False`;
the constant is hard-pinned in `to_dict()` so a downstream
serialiser cannot accidentally relax it.

A `RISK_REJECTED_FALSE_NEGATIVE` verdict (severity `CRITICAL`)
is the strongest signal the layer can emit — and even there:

  - the verdict reflects ONE candidate's outcome, not a
    portfolio of cases;
  - it does NOT account for the candidates the same rule
    correctly rejected;
  - outcome volatility is high in altcoin momentum;
  - rule changes affect *every future candidate*, not just the
    one in front of the reviewer.

Touching the rule itself is **out of scope** for this phase. A
`CRITICAL` severity routes to operator review and rule review
queues only. Auto-tuning of `symbol_limit`, anomaly thresholds,
candidate-pool capacity, or Regime weights is **forbidden**.

## Why this phase does NOT authorise live trading

The triage layer never emits a direction (long / short / entry /
exit / stop / target), never emits a sizing field
(`position_size` / `leverage` / `risk_budget`), never emits an
order / execution command, and never modifies the Risk Engine or
the Execution FSM. The closed taxonomy is descriptive only.

Phase 12 (real money / live trading) requires the Spec §41
Go/No-Go checklist, which has **not** been initiated. Phase 12
remains **FORBIDDEN**.

## Why `RAVEUSDT` / `STOUSDT` currently can only be triage candidates, not parameter-error proof

Under the B1 / B1.1 closeout, both symbols are recorded as

```
price_path_loaded = false
source = absent
missing_reason = no_top_mover_row_covering_first_seen_time
```

That means the local Historical Market Store does not yet
contain a top-mover row whose day window covers the record's
`first_seen_time_utc_ms`. From that fact alone, **we cannot
distinguish** the following four very different worlds:

  1. The mover was visible on the live feed and the system
     missed it (a `TRUE_DISCOVERY_FAILURE`).
  2. The mover was visible on the live feed and the Risk
     Engine rejected it for a non-hard-safety reason (a
     `RISK_REJECTED_FALSE_NEGATIVE`).
  3. The mover was visible on the live feed and the strategy
     mode said `observe` / `reject` (a
     `STRATEGY_MODE_FALSE_NEGATIVE`).
  4. The mover was never observable on the live feed because
     of a data gap (`WS_DATA_GAP`, `REST_REFERENCE_GAP`, or a
     `PRICE_PATH_MISSING` price path that obscures the
     post-first-seen behaviour).

Asserting "RAVEUSDT proves the threshold is too strict" against
this evidence base would be **looking at the answer key** — the
Historical 60D mover reference is post-hoc, and using it to
back-tune live parameters is exactly the auto-tuning failure
mode the brief forbids. This phase therefore classifies both
symbols as

```
root_cause = NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME
severity   = MEDIUM
needs_data_recovery = True
needs_rule_review   = False
auto_tuning_allowed = False
```

— a **data-gap triage candidate**. Once price-path completeness
is restored (later optional task), the engine can re-attribute
the same case to whichever of the four worlds above the new
evidence supports. **Until then**, asserting a parameter error
from a single coin is forbidden.

## Forbidden surface (verbatim)

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/llm/**`, `app/telegram/**`, `app/config/**`.
  - `symbol_limit` / `candidate_pool` / anomaly threshold /
    Regime-weight runtime knobs.
  - Binance private API (no API key, no API secret, no signed
    endpoint, no `listenKey`, no private WS).
  - Live orders.
  - Real Telegram outbound.
  - DeepSeek / LLM trade decisions (direction, position size,
    leverage, stop-loss, target price, execution command,
    runtime config patch).
  - Automatic parameter tuning (incl. `symbol_limit` expansion,
    anomaly threshold change, candidate pool capacity change,
    Regime weight change).
  - Phase 12 (real money / live trading).
  - Severe Missed Tail Triage outputs **MUST NOT** trigger any
    of the above. They are paper / report / evidence only.

## What this PR does NOT ship

  - No change to `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/llm/`, `app/telegram/`,
    `app/config/`.
  - No change to live trading flag, runtime config, thresholds,
    `symbol_limit`, `candidate_pool`, Regime weights, the
    DeepSeek transport, or the Telegram outbound transport.
  - No new private API surface, no signed endpoint, no
    `listenKey`, no real Telegram outbound, no DeepSeek trade
    decision.
  - No automatic parameter tuning. No "looking at the answer
    key" against the post-hoc D-A reference set.
  - No new strategy. No new trading module. No new direction
    classification. No new sizing rule.
  - No evidence closeout. No real-data run is performed by this
    PR; the implementation is evidence-ready but the closeout
    is a separate later PR.
  - No Replay / Reflection extension for the new events
    (separate slice).
  - No DeepSeek integration (separate phase).
  - **No Phase 12.**
