# Phase 11C.1C-C-B-B-B-D-D — Discovery Quality Scorecard v0 (*发现质量评分板 v0*)

> **Status: IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until evidence closeout).**
>
> **Type:** paper / report / evidence-only compression layer.
> **Runtime effect on real trading:** **none.**
> **Trade authority granted:** **none.**
> **Phase 12:** **FORBIDDEN.**

## 1. Purpose

Phase 11C.1C-C-B-B-B-D-A audited *discovery* (did we see the
mover?). Phase 11C.1C-C-B-B-B-D-B audited *post-discovery
outcome* (how much room remained after first sighting?). Phase
11C.1C-C-B-B-B-D-C-A closed the loop on *reject correctness*
(was the reject the right call?). Phase 11C.1C-C-B-B-B-D-C-B
attributed *severe misses* to a closed root-cause taxonomy.

The project still lacked a single descriptive number that an
operator can read at-a-glance to answer:

> "How **healthy** was discovery quality on this audit window?"

This slice ships that compression layer as a paper / report /
evidence-only **Discovery Quality Scorecard v0**. The scorecard
takes the simplified outputs of D-A / D-B / B2-A / B2-B and
emits, per audit window:

  - one descriptive ``quality_bucket`` (``GOOD`` / ``PARTIAL`` /
    ``WEAK`` / ``DEGRADED`` / ``INSUFFICIENT_EVIDENCE``);
  - per-axis rates (coverage / usable / early / late / severe /
    insufficient-price-path / false-negative-reject /
    correct-protective-reject / data-gap);
  - a preserved ``root_cause_summary`` from the upstream Severe
    Missed Tail Triage report;
  - the ``needs_operator_review`` / ``needs_data_recovery`` /
    ``needs_rule_review`` operator-routing flags;
  - a hard-pinned ``auto_tuning_allowed=False`` flag on every
    payload.

The scorecard is intentionally **non-actionable**: it is a
routing signal for human operators (review queue, data-recovery
queue, rule-review queue) and **never** a knob the runtime can
turn.

## 2. Inputs

The scorecard's input bundle is :class:`DiscoveryQualityScorecardInput`,
a frozen dataclass. Every field is paper / report / evidence
only.

  - ``reference_window`` — audit-window label (e.g. ``"60d"``).
  - ``coverage_total_count`` — total moves the D-A audit
    considered.
  - ``captured_count`` — captured movers (D-A).
  - ``missed_count`` — missed movers (D-A).
  - ``usable_discovery_count`` — discoveries with usable upside
    remaining (D-B).
  - ``early_discovery_count`` — early discoveries (D-B).
  - ``late_chase_count`` — late-chase candidates (D-B).
  - ``severe_miss_count`` — severe misses (B2-B).
  - ``insufficient_price_path_count`` — records where the
    price-path adapter could not produce a usable post-first-seen
    path (D-B / B1.1).
  - ``false_negative_reject_count`` — false-negative rejects
    (B2-A).
  - ``correct_protective_reject_count`` — correct protective
    rejects (B2-A).
  - ``data_gap_count`` — records flagged as ``data_gap`` (D-A /
    D-B / B1.1 / B2-B).
  - ``root_cause_summary`` — ``{label: count}`` dict from the
    Severe Miss Triage report.
  - ``evidence_refs`` — ``evt://...`` references anchoring the
    scorecard to replayable audit records. Empty
    ``evidence_refs`` triggers ``INSUFFICIENT_EVIDENCE``.
  - ``notes`` — optional operator-supplied free-form note.

The input bundle does NOT carry any direction / sizing /
runtime-knob field. The
:func:`assert_payload_has_no_forbidden_keys` recursive guard
refuses to emit any payload that contains
``buy`` / ``sell`` / ``long`` / ``short`` / ``direction`` /
``side`` / ``entry`` / ``exit`` / ``position_size`` /
``leverage`` / ``stop`` / ``stop_loss`` / ``target`` /
``take_profit`` / ``risk_budget`` / ``order`` /
``execution_command`` / ``runtime_config_patch`` /
``symbol_limit_patch`` / ``threshold_patch`` /
``candidate_pool_patch`` / ``regime_weight_patch``.

## 3. Outputs

The scorecard's output is :class:`DiscoveryQualityScorecard`, a
frozen dataclass.

  - ``reference_window`` — audit-window label.
  - ``quality_bucket`` — one of ``GOOD`` / ``PARTIAL`` / ``WEAK``
    / ``DEGRADED`` / ``INSUFFICIENT_EVIDENCE``.
  - ``coverage_rate`` — ``captured_count / coverage_total_count``.
  - ``usable_discovery_rate``,
  - ``early_discovery_rate``,
  - ``late_chase_rate``,
  - ``severe_miss_rate``,
  - ``insufficient_price_path_rate``,
  - ``false_negative_reject_rate``,
  - ``correct_protective_reject_rate``,
  - ``data_gap_rate`` — paired numerator / denominator rates,
    each clamped to ``[0.0, 1.0]``.
  - ``root_cause_summary`` — preserved from input.
  - ``notable_warnings`` — deduplicated warning labels (e.g.
    ``severe_miss_rate_severe`` / ``data_gap_rate_warn`` /
    ``false_negative_reject_rate_warn``).
  - ``needs_operator_review`` — bool.
  - ``needs_data_recovery`` — bool.
  - ``needs_rule_review`` — bool.
  - ``auto_tuning_allowed`` — **always ``False``** on every
    serialised payload (hard-pinned).
  - ``evidence_refs`` — preserved from input.
  - ``schema_version`` / ``source_phase`` — stable version
    labels.

## 4. Quality bucket taxonomy

The taxonomy is a closed 5-label set on
:class:`DiscoveryQualityBucket`:

| Label                   | Meaning (descriptive only)                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------ |
| `GOOD`                  | Coverage / usable rate cleared the GOOD threshold AND no axis tripped a warning.           |
| `PARTIAL`               | Coverage cleared the partial threshold but an axis (data gap / late chase) tripped a warn. |
| `WEAK`                  | Either coverage is below the partial threshold, OR severe miss tripped the warn tier.      |
| `DEGRADED`              | A data-gap / insufficient-price-path / severe-miss axis crossed the DEGRADED threshold.    |
| `INSUFFICIENT_EVIDENCE` | `coverage_total_count == 0` OR `evidence_refs` is empty.                                   |

`GOOD` / `PARTIAL` / `WEAK` / `DEGRADED` are **discovery-quality**
labels. They are **not** trade-approval labels and **not** an
input to a trade-decision pipeline.

Decision-flow priority (highest to lowest):

  1. ``INSUFFICIENT_EVIDENCE`` — when the inputs cannot support
     any other bucket.
  2. ``DEGRADED`` — any axis (data gap / insufficient price path
     / severe miss) crosses the DEGRADED threshold.
  3. ``WEAK`` — coverage below partial threshold OR severe miss
     warn tier OR a stray label cannot be matched.
  4. ``PARTIAL`` — coverage at the partial tier, OR data
     gap / insufficient price path / late chase tripped warn.
  5. ``GOOD`` — every axis clean.

The engine derives the bucket from a per-axis worst-case fold
across {coverage / usable / data / severe / late} so that any
single axis tripping DEGRADED locks the final bucket at
DEGRADED.

## 5. Event types

Two new typed events live in :class:`app.core.events.EventType`:

  - ``DISCOVERY_QUALITY_SCORECARD_GENERATED`` — the full
    :class:`DiscoveryQualityScorecard` payload was assembled and
    is available for export / replay.
  - ``DISCOVERY_QUALITY_BUCKET_EVALUATED`` — shorthand event for
    the operator-review queue. Carries the descriptive
    ``quality_bucket`` + ``evidence_refs`` and is suitable for
    routing without rehydrating the full scorecard.

Both event payloads MUST carry ``evidence_refs`` and
``auto_tuning_allowed=False``. Neither payload may contain any
direction / sizing / runtime-knob key.

## 6. Acceptance criteria

  1. Module imports cleanly under Python 3.11+.
  2. ``coverage_total_count == 0`` OR ``evidence_refs == ()``
     emits ``INSUFFICIENT_EVIDENCE`` with
     ``needs_operator_review=True`` and
     ``auto_tuning_allowed=False``.
  3. High coverage AND high usable rate AND low severe-miss /
     data-gap rates emit ``GOOD`` or ``PARTIAL``.
  4. High data-gap rate or insufficient-price-path rate emits at
     most ``PARTIAL`` / ``WEAK`` / ``DEGRADED`` and flips
     ``needs_data_recovery=True``.
  5. High severe-miss rate emits ``WEAK`` or ``DEGRADED`` and
     flips ``needs_operator_review=True``.
  6. High false-negative-reject rate flips
     ``needs_rule_review=True``, but ``auto_tuning_allowed`` MUST
     remain ``False``.
  7. ``root_cause_summary`` from the input is preserved verbatim
     on the output (modulo sorting / int coercion).
  8. No emitted payload contains any forbidden trade-authority /
     runtime-tuning key (recursive guard).
  9. The module does NOT import ``app.risk`` / ``app.execution``
     / ``app.exchanges`` / ``app.llm`` / ``app.telegram``.

The :file:`tests/unit/test_discovery_quality_scorecard.py` test
module enforces all nine criteria.

## 7. Safety boundary (held end-to-end)

  - ``mode = paper``
  - ``live_trading = False``
  - ``exchange_live_orders = False``
  - ``right_tail = False``
  - ``llm = False``
  - ``telegram_outbound_enabled = False``
  - ``binance_private_api_enabled = False``
  - no Binance API key / secret
  - no signed endpoint
  - no private websocket
  - no ``listenKey``
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**

The Risk Engine remains the single trade-decision gate.

## 8. Why this does NOT authorise auto-tuning

The brief's hardest invariant is that the discovery quality
scorecard MUST NEVER drive an automatic parameter change. Every
emitted scorecard carries ``auto_tuning_allowed=False``, and the
constant is hard-pinned in
:meth:`DiscoveryQualityScorecard.to_dict` so a downstream
serialiser cannot accidentally relax it.

A ``DEGRADED`` bucket is the strongest signal the layer can
emit — and even there, the bucket reflects **one audit
window**'s coverage health, not a portfolio of cases. Outcome
volatility is high in altcoin momentum; rule changes affect
every future candidate, not just the window in front of the
reviewer. Touching ``symbol_limit`` / anomaly thresholds /
candidate-pool capacity / Regime weights / Risk Engine on the
basis of a scorecard window is **out of scope** for this phase.

A high ``false_negative_reject_rate`` flips
``needs_rule_review=True`` — but ``auto_tuning_allowed`` stays
``False``. The operator-review queue and the rule-review queue
exist precisely so a *human* can decide whether a rule change is
warranted; the scorecard never makes that call itself.

## 9. Why this does NOT authorise live trading

The scorecard answers a *coverage / capture* question:
"how often did the system see the mover, and how usable was the
remaining post-discovery upside?" It does **not** answer:

  - Was the strategy profitable on this window? (no — the
    scorecard never evaluates strategy profitability.)
  - Should we open a position right now? (no — direction /
    sizing / stop / target are NEVER fields of the scorecard.)
  - Should we increase ``symbol_limit`` or relax the anomaly
    threshold? (no — runtime knobs are out of scope.)

A scorecard with ``quality_bucket=GOOD`` does **not** mean live
trading is approved. A scorecard with
``quality_bucket=DEGRADED`` does **not** mean live trading is
*disapproved* either; live-trading approval is a Phase 12
concern that requires the Spec §41 Go/No-Go checklist, and the
checklist has **not** been initiated.

The Risk Engine remains the single trade-decision gate.

## 10. Why GOOD / PARTIAL / DEGRADED are discovery-quality labels, not trade-approval labels

The labels describe **discovery health** — how often the
discovery pipeline (radar + filter + candidate pool + first-seen
detection) saw the moves the historical reference set lists.

They do **not** describe:

  - **Strategy quality** — whether a follow / pullback / observe
    / reject decision after first sighting was profitable.
    That's Phase 11C.1C-C-B-A's territory, not D-D's.
  - **Risk-decision quality** — whether the Risk Engine made the
    right reject / approve decision. That's Phase
    11C.1C-C-B-B-B-D-C-A's territory.
  - **Outcome quality** — whether the candidate ran or dumped
    after first sighting. That's Phase 11C.1C-C-B-B-B-D-B's
    territory.
  - **Trade-approval quality** — whether live trading should be
    enabled. That's a Phase 12 decision and is **forbidden** on
    every Phase 11C sub-phase.

A `GOOD` bucket means: *the discovery pipeline is seeing what
the reference set says it should be seeing on this window*. A
`DEGRADED` bucket means: *something in the discovery pipeline
or its evidence base is severely under-performing on this
window*. Either way, the bucket is a **diagnostic** signal for a
human operator, not a switch the runtime can flip.

## 11. What this PR does NOT ship

  - No change to ``app/risk/``, ``app/execution/``,
    ``app/exchanges/``, ``app/llm/``, ``app/telegram/``,
    ``app/config/``.
  - No change to ``symbol_limit``, anomaly thresholds,
    candidate-pool capacity, Regime weights, or any other
    runtime knob.
  - No new private API surface, no signed endpoint, no
    ``listenKey``, no real Telegram outbound, no DeepSeek trade
    decision.
  - No automatic parameter tuning. No "looking at the answer
    key" against the post-hoc D-A reference set.
  - No new strategy. No new trading module. No new direction
    classification. No new sizing rule.
  - No real evidence closeout. No real-data run is performed by
    this PR; the implementation is evidence-ready but the
    closeout is a separate later PR.
  - No Replay / Reflection extension for the new events
    (separate slice).
  - No DeepSeek integration (separate phase).
  - **No Phase 12.**

## 12. References

  - `docs/PHASE_11C_1C_C_B_B_B_D_A_HISTORICAL_60D_MOVER_COVERAGE_BACKFILL.md` — D-A.
  - `docs/PHASE_11C_1C_C_B_B_B_D_B_POST_DISCOVERY_OUTCOME_METRICS.md` — D-B.
  - `docs/PHASE_11C_1C_C_B_B_B_D_B_1_HISTORICAL_PRICE_PATH_KLINE_PATH_ADAPTER.md` — D-B.1.
  - `docs/PHASE_11C_1C_C_B_B_B_D_C_A_REJECT_TO_OUTCOME_ATTRIBUTION.md` — B2-A.
  - `docs/PHASE_11C_1C_C_B_B_B_D_C_B_SEVERE_MISSED_TAIL_TRIAGE.md` — B2-B.
  - `docs/PHASE_GATE.md` — phase-gate ledger.
  - `docs/PROJECT_STATUS.md` — at-a-glance status board.
  - `docs/CHANGELOG.md` — release notes.
  - Source: `app/adaptive/discovery_quality_scorecard.py`.
  - Tests: `tests/unit/test_discovery_quality_scorecard.py`.
