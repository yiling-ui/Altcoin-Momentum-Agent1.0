# Phase 11C.1C-C-B-B-B-D-C-A — Reject-to-Outcome Attribution v0

*拒绝决策到结果归因 v0*

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**

## Purpose

Phase 11C.1C-C-B-B-B-D-A described the *discovery* layer (did we
see the mover, when, how deep). Phase 11C.1C-C-B-B-B-D-B described
the *post-discovery outcome* (how much room remained after first
sighting). The project still lacked a closed loop linking
**candidate-level reject decisions** to those **outcome labels**.

The four pre-existing inputs were already in place:

  - `RISK_REJECTED` — Risk Engine reject events with reasons.
  - `TAIL_LABEL_ASSIGNED` — closed Phase 11C.1C-C-A label
    decisions (`strong_tail` / `weak_tail` / ...).
  - `POST_DISCOVERY_OUTCOME_*` — Phase 11C.1C-C-B-B-B-D-B
    descriptive outcome labels.
  - `HISTORICAL_MOVER_COVERAGE_*` — Phase 11C.1C-C-B-B-B-D-A
    coverage records.

What was missing was the closure:

```
opportunity_id
    -> risk_reject_reason / no_trade_reason / strategy_mode
    -> tail_label / post_discovery_outcome
    -> reject correctness verdict
```

This phase ships that closure as a **paper / report / evidence**
attribution layer. For every audited candidate the runtime
answers a single question: *was the reject the right call?*

The verdict is descriptive only. It NEVER triggers a real trade,
NEVER modifies the Risk Engine, NEVER loosens any rule, and NEVER
authorises auto-tuning of any runtime knob.

## Inputs

`RejectAttributionInput` carries:

  - **identity** — `opportunity_id`, `symbol`, `reference_window`,
    `first_seen_time_utc_ms`;
  - **reject / no-trade signals** —
    `risk_reject_reasons: tuple[str, ...]`,
    `no_trade_reasons: tuple[str, ...]`,
    `strategy_mode: str | None`,
    `candidate_stage: str | None`,
    `opportunity_score_bucket: str | None`;
  - **outcome surface** — `tail_label`,
    `post_discovery_outcome_label`, `detection_timing_label`,
    `post_seen_mfe_pct`, `post_seen_mae_pct`,
    `remaining_upside_to_peak_pct`, `price_path_status`;
  - **data-quality flags** — `data_quality_flags: tuple[str, ...]`;
  - **evidence pointers** — `evidence_refs: tuple[str, ...]`,
    `notes: str | None`.

The bundle is paper / report / evidence only. **No field
authorises a real trade or modifies any runtime knob.**

## Outputs

### `RejectAttributionRecord`

One per audited candidate. Carries:

  - identity columns (`opportunity_id`, `symbol`,
    `reference_window`);
  - the closed `verdict` (`RejectAttributionVerdict`);
  - `primary_reason` + up to three `secondary_reasons`;
  - `was_reject_protective: bool`;
  - `was_false_negative: bool`;
  - `needs_operator_review: bool`;
  - `needs_data_recovery: bool`;
  - `needs_rule_review: bool`;
  - **`auto_tuning_allowed: bool` — hard-pinned to `False`** in
    every serialised payload, regardless of verdict;
  - `evidence_refs`, `warnings`;
  - `schema_version`, `source_phase`.

### `RejectAttributionReport`

Aggregate roll-up across many records. Carries:

  - `total_records`;
  - `false_negative_reject_count`;
  - `correct_protective_reject_count`;
  - `insufficient_evidence_count`;
  - `verdict_summary: dict[str, int]`;
  - `reason_summary: dict[str, int]`;
  - `needs_operator_review_symbols`;
  - `needs_rule_review_symbols`;
  - `needs_data_recovery_symbols`;
  - `evidence_refs`, `warnings`;
  - **`auto_tuning_allowed: bool` — hard-pinned to `False`** even
    when `false_negative_reject_count > 0`.

## Verdict taxonomy (closed)

`RejectAttributionVerdict` is a closed set of string constants:

  - `CORRECT_PROTECTIVE_REJECT` — the reject was correct given a
    weak / fake / dumped outcome.
  - `FALSE_NEGATIVE_REJECT` — non-hard-safety reject + strong
    outcome (`EARLY_CONTINUATION` / `MISSED_STRONG_TAIL` /
    `strong_tail`) + meaningfully positive `post_seen_mfe_pct`.
    Routes to operator review and rule review. **Does NOT
    authorise rule relaxation.**
  - `DATA_QUALITY_REJECT` — driven by `data_degraded` /
    `ws_stale` / `insufficient_price_path` /
    `data_unreliable` / `price_path_gap` / `ws_data_gap` /
    `rest_reference_gap`. Flips `needs_data_recovery=True`.
  - `LIQUIDITY_PROTECTIVE_REJECT` — driven by `spread` / `depth`
    / `slippage` / `exit_liquidity` / `thin_book` / `low_volume`.
  - `MANIPULATION_PROTECTIVE_REJECT` — driven by
    `manipulation` / `fake_breakout` / `m2` / `m3` / `spoof` /
    `wash` / `pump_dump`.
  - `STOP_SAFETY_REJECT` — driven by `stop_unconfirmed` /
    `missing_stop` / `stop_failed` / `stop_safety` /
    `stop_loss_missing`. Stays protective even when the
    candidate later runs upside.
  - `REBASE_PROTECTIVE_REJECT` — driven by `rebase` /
    `capital_rebase` / `harvest_pause`.
  - `SYSTEM_SAFETY_REJECT` — driven by `unknown_position` /
    `protection_mode` / `safety_pause` / `kill_switch` /
    `p0_latched_pause` / `incident_open`.
  - `STRATEGY_MODE_FALSE_NEGATIVE` — no Risk Engine reject; the
    strategy itself produced a no-trade outcome
    (`strategy_mode` ∈ {`reject`, `observe`, `hold`,
    `no_trade`, `none`}) and the candidate later ran a strong
    tail.
  - `NO_REJECT_FOUND` — no reject signals at all; nothing to
    attribute. Refuses to fabricate.
  - `INSUFFICIENT_EVIDENCE` — missing `evidence_refs` or missing
    every outcome field. Refuses to fabricate a verdict; routes
    to operator review.
  - `UNKNOWN` — fall-through; routes to operator review.

### Hard-safety priority

When more than one reason category matches, the engine resolves
in this priority order:

```
STOP_SAFETY > SYSTEM_SAFETY > DATA_QUALITY > LIQUIDITY
            > MANIPULATION > REBASE
```

A hard-safety verdict ALWAYS short-circuits the false-negative
check. The brief makes this explicit: *"如果 risk_reject_reasons
包含 stop_unconfirmed / unknown_position / missing_stop /
protection_mode：…即使后续上涨，也不能简单标 false negative."*

## Event types

Four new typed events in `app/core/events.py` (paper / report /
evidence only):

  - `EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED` — one
    `RejectAttributionReport` was assembled across many records.
  - `EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED` — one
    `RejectAttributionRecord` was emitted for one candidate.
  - `EventType.FALSE_NEGATIVE_REJECT_DETECTED` — one record was
    attributed `FALSE_NEGATIVE_REJECT` or
    `STRATEGY_MODE_FALSE_NEGATIVE`. Routes to the operator queue.
  - `EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED` — one record
    was attributed as a correct protective reject (any of the
    hard-safety verdicts or `CORRECT_PROTECTIVE_REJECT`).

Every payload MUST carry:

  - `evidence_refs: list[str]`;
  - `auto_tuning_allowed = False`;
  - `schema_version`.

Every payload MUST NOT carry any of:

```
buy, sell, long, short, direction, side,
entry, entry_price, exit, exit_price,
order, order_type, execution_command,
position_size, leverage,
stop, stop_loss, stop_price,
target, target_price, take_profit,
risk_budget,
runtime_config_patch, symbol_limit_patch, threshold_patch,
candidate_pool_patch, regime_weight_patch
```

The forbidden set is enforced in code by
`assert_payload_has_no_forbidden_keys`, which is called on every
emitted record / report payload.

## Acceptance criteria

  1. `tests/unit/test_reject_to_outcome_attribution.py` passes
     end-to-end.
  2. The full `tests/unit` suite still passes.
  3. The forbidden-key guard rejects any payload that contains a
     trade-authority / runtime-tuning key (covered by tests).
  4. The forbidden-import guard confirms
     `app/adaptive/reject_to_outcome_attribution.py` does NOT
     import any of `app.risk` / `app.execution` / `app.exchanges`
     / `app.llm` / `app.telegram` (covered by tests).
  5. `auto_tuning_allowed` is hard-pinned to `False` on every
     emitted record / report (covered by tests).
  6. Stop-safety / system-safety / data-quality / liquidity /
     manipulation / rebase rejects ALWAYS short-circuit the
     false-negative path (covered by tests).
  7. Hard-safety verdict on a positive-MFE outcome MUST NOT be
     marked as a false negative (covered by tests).

## Safety boundary

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

**The Risk Engine remains the single trade-decision gate.**

## Why this does NOT authorise auto-tuning

  - Every emitted record carries `auto_tuning_allowed=False`
    regardless of the verdict.
  - A `FALSE_NEGATIVE_REJECT` / `STRATEGY_MODE_FALSE_NEGATIVE`
    verdict only flips `needs_operator_review=True` (and
    `needs_rule_review=True` for the explicit-reject form). It
    does NOT modify `symbol_limit`, anomaly thresholds,
    candidate-pool capacity, Regime weights, or any other
    runtime knob.
  - The aggregate `RejectAttributionReport.auto_tuning_allowed`
    is also hard-pinned to `False`, even when
    `false_negative_reject_count > 0`. A high false-negative
    count is an operator-review signal, NOT an auto-tune signal.
  - "Looking at the answer key" against the post-hoc D-A / D-B
    reference set is forbidden.

## Why this does NOT authorise live trading

  - The module does not call any Risk Engine, Execution FSM,
    Exchange Adapter, LLM, or Telegram transport. The
    forbidden-import test pins this in code.
  - The forbidden-payload guard refuses to emit any payload that
    contains direction, sizing, stop, target, or runtime-tuning
    fields.
  - No event emitted by this module carries trade authority. The
    Risk Engine remains the single trade-decision gate.

## Why a `FALSE_NEGATIVE_REJECT` does NOT mean "loosen the Risk Engine"

  - A false-negative verdict is a single-case observation: at
    least one candidate ran upside after a non-hard-safety
    reject.
  - It does NOT mean the Risk Engine's *policy* is wrong. It
    might still be correct on average.
  - It does NOT account for the cases the same rule prevented
    from going wrong — those are also non-trades, and they are
    also part of the rule's value.
  - It does NOT guarantee a similar outcome on the next
    candidate; outcome volatility is high in altcoin momentum.
  - It MUST be reviewed by a human, against a portfolio of
    cases, before any rule is touched. The rule-touching itself
    is **out of scope for this phase**.

## What this PR ships

  - New module
    `app/adaptive/reject_to_outcome_attribution.py`
    (paper / pure / deterministic).
  - Four new typed events in `app/core/events.py`
    (`REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED`,
    `REJECT_TO_OUTCOME_CASE_ATTRIBUTED`,
    `FALSE_NEGATIVE_REJECT_DETECTED`,
    `CORRECT_PROTECTIVE_REJECT_CONFIRMED`).
  - New unit-test module
    `tests/unit/test_reject_to_outcome_attribution.py`
    covering every brief-mandated acceptance test (stop safety
    reject remains protective, data quality reject, liquidity
    protective reject, manipulation protective reject, false
    negative reject, strategy mode false negative, no reject
    found, insufficient evidence, forbidden fields absent, no
    forbidden imports).
  - Public exports added to `app/adaptive/__init__.py`.
  - This phase doc.

## What this PR does NOT ship

  - No change to `app/risk/`, `app/execution/`,
    `app/exchanges/`, `app/llm/`, `app/telegram/`,
    `app/config/`.
  - No change to `symbol_limit`, anomaly thresholds,
    `candidate_pool`, Regime weights, runtime config, or any
    other runtime knob.
  - No change to live trading flag, the DeepSeek transport, or
    the Telegram outbound transport.
  - No new private API surface, no signed endpoint, no
    `listenKey`, no real Telegram outbound, no DeepSeek trade
    decision.
  - No automatic parameter tuning. No "looking at the answer
    key" against the post-hoc reference set.
  - No new strategy. No new trading module. No direction call.
  - No Severe Missed Tail Triage slice (B2 — separate slice).
  - No Replay / Reflection extension for the new events
    (separate slice).
  - No DeepSeek integration (separate phase).
  - No Phase 12.
