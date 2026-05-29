# Phase 11C.1D-D — Strict Blind Walk-forward Sim-Live Constitution

> *Strict Forward-only Historical Sim-Live Blind Walk-forward Design Baseline*
> *盲测设计宪法 / 严格前向 Sim-Live 盲测基线*
>
> **Status:** IN_REVIEW (after this docs-only PR is merged the
> phase moves from IN_REVIEW to ACCEPTED only via a separate
> docs-closeout PR; this PR alone does NOT mark the phase
> ACCEPTED).
> **Type:** **docs-only constitution.** No runtime code, no
> configuration, no tests, no scripts, no data files are
> introduced or modified by this PR.
> **Parent:** Phase 11C umbrella.
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

---

## 0. Pre-amble — what this document is and is NOT

This document is the **Strict Blind Walk-forward Sim-Live
Constitution**. It is the highest engineering constraint on the
AMA-RT V1.4 blind-test phase. It is the human-owner-supplied
strict forward-only anti-lookahead blind-test design that the
Phase 11C.1D-C *Risk / Execution / Capital Safety Matrix v0*
acceptance rule explicitly requires before *Blind Walk-forward
implementation* may begin.

This document IS:

  * a docs-only design baseline,
  * a closed list of forbidden behaviours during blind windows,
  * a closed list of mandatory invariants that any later
    implementation PR (PR94 → PR100) must satisfy,
  * the binding contract for §1 *Purpose* through §20 *Final
    Governance Rule*, plus the owner-review enhancements §A
    through §F.

This document IS NOT:

  * an implementation,
  * a SimulationClock,
  * a Time-Wall Guard,
  * a Historical Market Store,
  * a ReplayFeedProvider,
  * a MockExchange,
  * a Pessimistic Fill Model,
  * a Simulated Capital Flow,
  * a Telegram Sandbox Outbox,
  * a Blind Walk-forward Runner,
  * an authorisation to enter Phase 12,
  * an authorisation to enable live orders,
  * an authorisation to connect to Binance private API,
  * an authorisation to grant AI trade authority,
  * an authorisation to grant Telegram command authority,
  * an authorisation to auto-tune any rule, threshold, or
    parameter.

Acceptance of this constitution only authorises the next
allowed paper-only step (**PR94 — SimulationClock + Time-Wall
Guard**). It does NOT authorise the rest of the engineering
route (PR95 → PR100); each of those phases must pass its own
gate.

---

## 1. Purpose

AMA-RT blind testing is **not** an ordinary backtest. It is a
**strict forward-only historical sim-live**: the system must
run on a past historical timeline as if it were live, extract
maximum learning value from the historical record, and
unconditionally refuse any form of look-ahead, future-leak, or
overfitting.

The point is **truthful quantitative validation**, not pretty
equity curves. A pretty curve produced by even one form of
leakage is not evidence; it is a falsification.

The blind walk-forward phase therefore exists to answer one
question and one question only:

> *Given only what the system could have known at simulated
> time T, would AMA-RT have made the decisions it did, and
> would those decisions have produced the result they claim
> on the closed historical record?*

Every other engineering convenience (retraining shortcuts,
"just one more parameter", "a tiny peek at the label", "a
small AI nudge", "let me see the final equity first") is
explicitly forbidden by this constitution.

---

## 2. Safety Boundary

The blind walk-forward phase MUST hold the following safety
boundary at all times. Each flag is the project-wide invariant
already pinned by Phase 1 / Phase 11C / Phase 11C.1D-B / Phase
11C.1D-C; this constitution restates them so the blind-test
boundary cannot drift out of sync.

| flag | required value |
| --- | --- |
| `live_trading` | `False` |
| `exchange_live_orders` | `False` |
| `binance_private_api_enabled` | `False` |
| `signed_endpoint_reachable` | `False` |
| `private_websocket_reachable` | `False` |
| `account_endpoint_reachable` | `False` |
| `order_endpoint_reachable` | `False` |
| `position_endpoint_reachable` | `False` |
| `leverage_endpoint_reachable` | `False` |
| `margin_endpoint_reachable` | `False` |
| `real_exchange_order_path` | `False` |
| `real_capital` | `False` |
| `telegram_live_command_authority` | `False` |
| `ai_trade_authority` | `False` |
| `auto_tuning_inside_blind_window` | `False` |
| `phase_12_forbidden` | **`True`** |

The Risk Engine remains the single trade-decision gate. Any
runtime payload emitted by a blind-test surface that contradicts
the table above MUST be refused at the serialisation boundary.

---

## 3. Sim-live Namespace

The blind walk-forward phase introduces a **separate sim-live
namespace** so that no dangerous live flag (`live_trading`,
`exchange_live_orders`, `binance_private_api_enabled`, …) is
ever reused, even by accident, to authorise simulation-only
behaviour. The sim-live namespace flags are:

| flag | required value |
| --- | --- |
| `mode` | `historical_blind_sim_live` |
| `historical_replay_enabled` | `True` |
| `simulation_clock_enabled` | `True` |
| `time_wall_guard_enabled` | `True` |
| `mock_exchange_enabled` | `True` |
| `paper_shadow_execution_enabled` | `True` |
| `simulated_order_lifecycle_enabled` | `True` |
| `simulated_position_lifecycle_enabled` | `True` |
| `simulated_capital_flow_enabled` | `True` |
| `telegram_sandbox_outbox_enabled` | `True` |
| `ai_offline_briefing_enabled` | `True` |

**No sim-live flag may flip a live-trading flag** under any
condition. Setting `historical_replay_enabled=True` does NOT
flip `live_trading`. Setting `mock_exchange_enabled=True` does
NOT flip `exchange_live_orders`. Setting
`telegram_sandbox_outbox_enabled=True` does NOT flip
`telegram_live_command_authority`. Setting
`ai_offline_briefing_enabled=True` does NOT flip
`ai_trade_authority`.

The sim-live namespace is **additive**: it adds simulation
permissions on top of the safety boundary in §2. It cannot
subtract from the safety boundary.

---

## 4. Required Architecture

Blind walk-forward MUST be wired exactly as below. Every arrow
is enforced by code or by tests; every box that touches
simulation must use the SimulationClock and the Time-Wall Guard.

```
HistoricalReplayProvider
   ↓
MarketDataBuffer
   ↓
Regime Engine
   ↓
Discovery / Radar
   ↓
Candidate Pool
   ↓
Strategy Orchestrator / Shadow Rule Evaluation
   ↓
Risk Engine
   ↓
Execution FSM
   ↓
MockExchange
   ↓
Simulated Position Book
   ↓
Simulated Capital Flow
   ↓
Replay / Reflection / Export
   ↓
Telegram Sandbox Outbox
   ↓
AI Offline Operator Briefing
```

The following two arrows are **explicitly forbidden** during a
blind walk-forward run:

  * `Execution FSM → Real Exchange Gateway → Binance signed
    order endpoint` — forbidden. The Execution FSM must route
    only to the MockExchange.
  * `AI Output → Strategy / Risk / Execution / Config /
    Position / Leverage / Stop / Target` — forbidden. AI output
    may be commentary only and may not steer any of these
    surfaces.

Any blind-test runtime that exposes either of these arrows MUST
be invalidated under §F.

---

## 5. Time-Wall Constitution

The blind window obeys a single time discipline.

  * All simulation-sensitive components MUST use the
    `SimulationClock` (PR94). They MUST NOT call
    `datetime.now()`, `datetime.utcnow()`, `time.time()`,
    `time.monotonic()`, `pandas.Timestamp.now()`, or any other
    wall-clock source as the **market-state decision time**.
    (Operating-system wall clock may still be used for
    file-write timestamps, log rotation, and other non-decision
    bookkeeping, but these values may not be fed back into any
    market or trade decision.)
  * Every historical record MUST distinguish four timestamps:
      * `event_time` — when the underlying market event
        actually occurred,
      * `available_at` — the earliest time at which a sim-live
        consumer could legitimately have observed the record
        (e.g. candle close time + exchange publication
        latency),
      * `source` — which provider / endpoint produced the
        record,
      * `ingested_at` — when the record entered the historical
        store.
  * At simulated time `T`, the system MAY only read records
    whose `available_at <= T`.
  * Any read of a record whose `available_at > T` MUST be
    rejected by the Time-Wall Guard and logged as a
    `NO_LOOKAHEAD_VIOLATION`.
  * `ingested_at` is **not** a substitute for `available_at`.
    A record whose `ingested_at <= T` but whose
    `available_at > T` is still future data and MUST be
    rejected.

A run that records even one `NO_LOOKAHEAD_VIOLATION` is
invalidated under §F.

---

## 6. Candle Visibility Rule

The blind window cannot peek at unfinished candles.

  * A 1m candle's OHLCV is **fully visible** only after that
    candle has closed. Final `high` / `low` / `close` /
    `volume` of an unfinished 1m candle are NOT readable inside
    the blind window.
  * A 5m candle's OHLCV is fully visible only after the 5m
    candle has closed. Same rule.
  * Any longer-period candle (15m / 1h / 4h / 1d / …) follows
    the same rule.
  * If the historical store does NOT carry tick or trade data
    for an interval, the intra-bar path between
    `open` / `high` / `low` / `close` is **ambiguous** and must
    be modelled either:
      * **conservatively** (worst-case assumption against the
        position), or
      * with the explicit marker `AMBIGUOUS_INTRABAR_PATH`,
        which the Pessimistic Fill Model in §11 propagates as a
        worst-case fill.

A favourable intra-bar path **must never** be the default
assumption. "Touched my limit price therefore filled" is
forbidden. "Touched my stop therefore filled at exactly stop
price" is forbidden. Both are leakage in disguise.

---

## 7. Outcome Label Isolation

The following labels are **outcome labels** and only become
valid evidence after the blind window has fully closed and the
window's data manifest has been frozen.

The blind window MUST NOT read:

  * future top-mover labels,
  * completed tail labels,
  * post-discovery outcome metrics,
  * future MFE / MAE / peak / trough,
  * severe missed-tail labels,
  * final window PnL,
  * future drawdown,
  * future funding-rate changes,
  * future regime labels,
  * future AI briefings,
  * future replay summaries,
  * future reflection summaries.

These artefacts are produced only by the windows that have
already closed (training history) or by the scoring / audit
pass run **after** the current blind window terminates. They
cannot be loaded into:

  * the candidate pool,
  * the radar,
  * the regime engine,
  * the strategy orchestrator,
  * the shadow-rule evaluator,
  * the risk engine,
  * the execution FSM,
  * any feature store keyed at `as_of_time = T`.

A run that uses any of the above as decision input is
invalidated under §F.

---

## 8. Training / Freeze / Blind / Score / Experience Update Loop

The blind walk-forward phase enforces a strict five-stage
loop. The loop is one-directional. The blind stage cannot
modify the train stage; the score stage cannot modify the
blind stage; the experience-update stage cannot retroactively
modify any closed window.

### 8.1 Train Window

  * Training MAY use only **already-closed** historical
    windows whose data manifest is frozen.
  * Allowed training activities: descriptive statistics,
    failure-case replay, generation of rule candidates,
    creation of experience-ledger artefacts, calibration of
    fee / slippage / latency / outage / data-degradation
    models against historical evidence.
  * Training MAY NOT use any record whose `available_at`
    falls inside the upcoming blind window.

### 8.2 Freeze

Before a blind window opens, **all** of the following MUST be
frozen and content-hashed:

  * the runtime code (git commit hash),
  * the runtime configuration,
  * the rule set (rule IDs + rule content hash),
  * the data manifest (per-symbol, per-interval, per-source
    record list with `available_at` boundaries),
  * the universe manifest (the as-of market universe — see
    §9),
  * the feature schema (feature names, types, transformations,
    cache keys),
  * the fee model,
  * the slippage model,
  * the latency model,
  * the outage / data-degradation injection model,
  * the AI offline state (prompt templates, briefing
    templates, citation rules).

Each frozen artefact emits an immutable hash. The hash is
recorded in the Blind Run Manifest (§16).

### 8.3 Blind Window

The blind window MUST:

  * use **only** the frozen artefacts from §8.2,
  * obey the time wall (§5) — every read uses `available_at <=
    simulated_time`,
  * obey the candle visibility rule (§6),
  * obey the outcome label isolation rule (§7),
  * not auto-tune any rule, threshold, parameter, weight, or
    AI prompt,
  * not re-load a fresher data manifest mid-window,
  * not consult the final outcome of the window in progress,
  * not consult any future label,
  * not alter parameters based on the partial result observed
    so far inside the same blind window.

### 8.4 Score

Scoring runs **only after** the blind window has closed. It
MAY:

  * compute discovery quality / capture quality / missed-tail
    counts,
  * compute simulated trade results, capital curve, drawdown,
    win rate, expectancy,
  * compute failure-cause attribution,
  * compute cohort analyses,
  * cross-check evidence against the existing Phase 11C
    artefacts (Paper Alpha Gate, Regime & Cluster Cohort
    Evidence Pack, Mover Capture Recall, Discovery Quality
    Scorecard).

Scoring MAY NOT retroactively change the trade ledger or any
event recorded inside the closed blind window.

### 8.5 Experience Update

Evidence from a **closed** blind window MAY enter the
experience ledger. The next training window MAY learn from it.

Evidence from the **currently open** blind window MAY NOT
enter the experience ledger, MAY NOT change rule candidates in
flight, and MAY NOT contaminate the still-running blind
window.

---

## 9. As-of Market Universe

Survivorship bias is forbidden.

  * The blind window MUST NOT use the *current* exchange
    symbol list to reconstruct the past.
  * At simulated time `T`, the eligible symbol universe is
    only those symbols that, **at time T**, were:
      * already listed (`listed_at <= T`),
      * not yet delisted (`delisted_at IS NULL OR delisted_at
        > T`),
      * in a tradable status (e.g. Binance `TRADING`),
      * carrying sufficient data quality to be admissible
        (`data_completeness_state` permits decisions).

The universe manifest MUST carry, at a minimum, these required
fields per symbol-record:

| field | description |
| --- | --- |
| `symbol` | canonical exchange symbol (preserves verbatim case + non-ASCII) |
| `market_type` | spot / perpetual / dated futures / etc. |
| `listed_at` | first time the symbol became listable |
| `delisted_at` | first time the symbol became unlistable (nullable) |
| `status` | `TRADING` / `BREAK` / `HALT` / `DELISTED` / etc. |
| `available_at` | first time this universe row could legitimately be observed |
| `min_notional` | exchange minimum-notional rule active at `available_at` |
| `tick_size` | exchange tick size active at `available_at` |
| `step_size` | exchange step size active at `available_at` |
| `contract_type` | for futures / perpetuals (`USDT_PERPETUAL`, etc.) |
| `data_completeness_state` | descriptive marker (`OK` / `DEGRADED` / `INSUFFICIENT` / …) |

A symbol that was not yet listed at `T`, that was already
delisted at `T`, that was in a non-tradable state at `T`, or
whose data was unreliable at `T`, MUST NOT enter the candidate
pool at `T`.

---

## 10. Historical Data Scope

v0 of the blind walk-forward stack is **not** required to
carry two years of full tick-level orderbook data. The minimum
v0 scope is enough to make a forward-only simulation honest.

### 10.1 Minimum v0 historical data

  * 1m kline (open / high / low / close / volume / trade-count
    / quote-volume),
  * 5m kline,
  * funding rate (per symbol, per funding interval, where
    applicable),
  * open interest (per symbol, per interval, where available),
  * 24h ticker snapshots (where available),
  * exchangeInfo / symbol metadata (with `as_of` semantics),
  * listing / delisting / symbol-status timeline.

### 10.2 Later high-fidelity data (out of scope for v0)

The following are explicit **non-goals for v0** and are
deferred:

  * tick trades,
  * `aggTrades`,
  * historical orderbook snapshots,
  * depth updates,
  * queue-position modelling,
  * microstructure-level slippage modelling.

A v0 run that only carries the §10.1 set is acceptable; the
Pessimistic Fill Model in §11 absorbs the resulting
intra-bar uncertainty.

---

## 11. MockExchange + Pessimistic Fill Model

The MockExchange is the **only** order-routing destination
inside a blind walk-forward run.

### 11.1 What the MockExchange must simulate

  * market orders,
  * limit orders,
  * stop orders,
  * take-profit orders,
  * forced-exit / liquidation flow,
  * partial fills,
  * rejects (notional too small, price too far from book,
    rate-limited, paused, etc.),
  * cancels,
  * stale-order timeouts,
  * position updates (open / increase / reduce / close),
  * fee accounting,
  * slippage,
  * funding-rate accrual,
  * reconciliation mismatches (ghost / orphan / missing
    remote),
  * outages (exchange unreachable, partial-symbol outage),
  * WebSocket staleness,
  * REST 429 throttling,
  * REST 418 ban.

### 11.2 What the MockExchange MUST NOT do

  * call any real exchange endpoint,
  * import or instantiate any real exchange HTTP / WS client
    along the simulation path,
  * read any real Binance signed-endpoint response,
  * leak any real account / order / position data into the
    sim.

### 11.3 Pessimistic Fill Model (default)

The default fill model is **conservative**:

  * **Market order:** filled at `visible_price + taker_fee +
    slippage + latency_penalty`. The visible price is the
    candle-close price applicable at `available_at <=
    simulated_time`, never a future intra-bar extreme.
  * **Limit order:** "the market touched my limit price"
    does NOT mean "I am filled". Without tick / orderbook
    data, partial-touch fills are modelled probabilistically
    or rejected as unfillable; never filled in full by
    default.
  * **Stop loss:** stop triggers cause **adverse** execution
    (slippage on the wrong side, latency penalty, possibly
    partial fills) — never an exact fill at the stop price.
  * **Stop / target on the same candle:** when both stop and
    target are touched within the same intra-bar window and
    no tick data exists to disambiguate the order, the run
    MUST use the **worst-case** outcome OR explicitly mark
    the trade `AMBIGUOUS_INTRABAR_PATH` and propagate that
    marker into the trade ledger and into scoring.

Any "favourable default" — exact fill at limit, exact fill at
stop, target hits before stop "because it's a long", touched
price = filled — is forbidden.

---

## 12. Latency / Outage / Data Degradation Injection

Blind walk-forward without realistic degradation is
overfitting. Required injection points:

  * market-data latency (per-source distribution),
  * order-acknowledgement latency,
  * WebSocket stale-feed periods,
  * WebSocket disconnect events,
  * REST throttling (HTTP 429 backoff cycles),
  * REST ban (HTTP 418),
  * data gaps (missing candles / missing trades / missing
    funding records),
  * partial symbol outages (one symbol's feed is bad while the
    rest are fine),
  * reconciliation mismatches between the simulated position
    book and the simulated exchange state,
  * Telegram delivery failures (sandbox outbox unable to
    write),
  * AI briefing failures (offline AI unavailable / timed out /
    `forbidden_field_stripped`).

The injection model is part of the frozen artefact set in §8.2.
Tweaking the injection model mid-window is forbidden.

---

## 13. Simulated Capital Flow

The simulated-capital state must always emit a closed,
auditable set of fields:

| field | meaning |
| --- | --- |
| `initial_capital` | capital injected at the start of the simulation |
| `exchange_equity` | equity currently held inside the simulated exchange |
| `locked_profit` | profit set aside / withdrawn from active risk capital |
| `open_risk` | total open-position notional risk currently exposed |
| `unrealized_pnl` | mark-to-market PnL on open simulated positions |
| `realized_pnl` | PnL from closed simulated positions |
| `total_lifetime_equity` | cumulative equity since start (incl. locked profit) |
| `drawdown` | current drawdown vs. peak `total_lifetime_equity` |
| `active_positions` | count + notional of open simulated positions |
| `risk_state` | descriptive risk-state label from the safety matrix |

**Locked-profit rule.** `locked_profit` MAY NOT be reused as
active risk capital inside the same blind window unless the
**frozen** configuration of that window explicitly authorises
re-use. The blind window cannot make this decision in flight;
re-use authorisation is part of §8.2 freeze artefacts.

---

## 14. Telegram Sandbox

The blind walk-forward phase has **no real Telegram outbound**
under any circumstance. v0 only writes to a file outbox:

  * `data/reports/telegram_sandbox_outbox.jsonl`
  * `data/reports/telegram_sandbox_messages.md`

Every sandbox message MUST carry the following four banner
markers verbatim:

  * `[SIMULATED HISTORICAL BLIND TEST]`
  * `[NO LIVE ORDER]`
  * `[NO REAL CAPITAL]`
  * `[NO TELEGRAM COMMAND AUTHORITY]`

Telegram MUST NOT be wired into any execution authority.
Inbound Telegram commands have **no decision authority** inside
a blind walk-forward run; they are recorded as inert audit
events at most. `telegram_live_command_authority=false` is the
hard pin (§2).

---

## 15. AI Role

The AI Layer is **offline intelligence only**.

### 15.1 What the AI Layer MAY do

  * evidence compression,
  * operator briefing,
  * replay summary,
  * reflection summary,
  * claim-citation review,
  * reality-check commentary,
  * failure-explanation drafts.

### 15.2 What the AI Layer MUST NOT do

  * direction decisions (long / short / direction class),
  * symbol-selection authority,
  * position sizing,
  * leverage decisions,
  * stop-loss decisions,
  * target / take-profit decisions,
  * execution timing,
  * risk-budget changes,
  * runtime-configuration patches,
  * training-label generation,
  * tail-label generation,
  * Truth Layer fact creation (AI output is **commentary**
    only — it cannot become a *fact* asserted by the system),
  * auto-tuning triggers.

AI output that violates §15.2 MUST be stripped at the
serialisation boundary (the existing
`assert_no_forbidden_fields` recursive guard or its successor)
and the violation MUST be recorded as
`AI_FORBIDDEN_FIELD_STRIPPED` (already in the safety matrix
taxonomy from Phase 11C.1D-C).

---

## 16. Required Outputs

A blind walk-forward run MUST emit, at minimum, the following
artefacts. Each output is descriptive only; none of them is an
actionable runtime-config patch or trade order.

  * **Blind Run Manifest** — frozen-artefact hashes from §8.2,
    sim-live namespace flags, safety boundary flags, blind
    window `[start_simulated_time, end_simulated_time)`,
    universe manifest hash, data manifest hash, fee / slippage
    / latency / outage model hashes, AI offline state hash,
    code commit hash.
  * **Trade Ledger** — every simulated order (open, modify,
    cancel, fill, partial fill, reject) with `simulated_time`,
    `available_at`, fill model verdict, fee, slippage, latency
    penalty, intra-bar ambiguity marker (where applicable).
  * **Equity Timeseries** — sampled `total_lifetime_equity`,
    `exchange_equity`, `unrealized_pnl`, `realized_pnl`,
    `drawdown`, `open_risk`, `locked_profit`, `active_positions`.
  * **Discovery Quality Ledger** — discovery / capture /
    missed-tail counts cross-referenced to the Phase 11C
    discovery quality scorecard (descriptive only).
  * **Failure Ledger** — every adverse-condition event from
    §12 (latency, outage, WS stale, REST 429 / 418, data gap,
    reconciliation mismatch, Telegram delivery failure, AI
    briefing failure) with timestamps and context.
  * **Telegram Sandbox Transcript** — `telegram_sandbox_outbox.jsonl`
    + `telegram_sandbox_messages.md`, every message banner-
    marked per §14.
  * **AI Operator Briefing** — descriptive-only briefing
    artefact compatible with the Phase AI-5 / AI-6 contracts.

---

## 17. Acceptance Criteria

A blind walk-forward implementation is valid only if **every**
condition below holds. A single violation invalidates the run
under §F.

  * The SimulationClock is used by every simulation-sensitive
    component.
  * The Time-Wall Guard rejects every read whose
    `available_at > simulated_time`, and every such rejection
    is logged as `NO_LOOKAHEAD_VIOLATION`.
  * Every read inside the blind window obeys `available_at <=
    simulated_time`.
  * Outcome labels (§7) are unavailable to all decision
    surfaces inside the blind window.
  * All training artefacts (§8.2) are frozen with content
    hashes before the blind window opens.
  * The blind window cannot auto-tune.
  * The market universe is reconstructed as-of historical
    time (§9), with no survivorship bias.
  * The Execution FSM routes only to the MockExchange.
  * No real Binance private endpoint is reachable.
  * No real order can be placed.
  * Telegram is sandbox-only (§14).
  * The AI Layer is offline-only (§15) and has no trading
    authority.
  * The Trade Ledger is generated.
  * The Equity Timeseries is generated.
  * The Discovery Quality Ledger is generated.
  * The Failure Ledger is generated.
  * Replay / Reflection / Export evidence is generated.
  * Phase 12 remains forbidden.

---

## 18. Explicit Non-goals for v0

The following are **out of scope** for v0 of the blind
walk-forward stack and MAY NOT be smuggled in via any side
channel:

  * a full two-year orderbook replay,
  * full tick-level matching for every symbol,
  * production Telegram channel posting,
  * real Binance private API access,
  * real account reconciliation,
  * real position reconciliation,
  * AI strategy generation,
  * AI parameter tuning,
  * automatic live deployment,
  * Phase 12 readiness.

Any future PR that wants to add one of these MUST first open
its own gate, its own kickoff PR with brief / boundary /
forbidden list, and its own acceptance evidence. None of the
PR94 → PR100 implementation route is allowed to broaden v0
scope by stealth.

---

## 19. Recommended Engineering Route

The blind walk-forward stack is built bottom-up. Each step is
its own PR with its own gate, its own brief, its own forbidden
list, and its own acceptance evidence. Acceptance of one step
**does not** authorise the next step to skip its gate; each
step's gate must be opened explicitly.

| step | scope |
| --- | --- |
| **PR93** | **Strict Blind Walk-forward Sim-Live Constitution** (this docs-only PR). |
| PR94 | SimulationClock + Time-Wall Guard. |
| PR95 | Historical Market Store v0. |
| PR96 | ReplayFeedProvider. |
| PR97 | MockExchange + Pessimistic Fill Model v0. |
| PR98 | Simulated Capital Flow + Trade Ledger. |
| PR99 | Telegram Sandbox Outbox. |
| PR100 | Blind Walk-forward Runner v0. |

PR93 acceptance authorises **only** PR94 to begin. PR94
acceptance authorises **only** PR95 to begin. And so on.
Skipping a step is forbidden.

---

## 20. Final Governance Rule

The Strict Blind Walk-forward stack MAY simulate a full
live-trading system on the historical record.

It MAY NOT become a live-trading system.

  * **Phase 12 remains forbidden.**
  * **Real trading remains forbidden.**
  * **Private exchange access remains forbidden.**
  * **AI trade authority remains forbidden.**
  * **Telegram command trading remains forbidden.**

Any documentation, implementation, runtime payload, or AI
output that contradicts the five lines above is invalid by
construction and MUST be invalidated under §F.

---

## §A. Explicit Leakage Test Suite (owner-review enhancement)

Any later PR that implements blind walk-forward machinery MUST
also implement the following test suite. The test names below
are normative; later PRs may add more tests, but may not rename
or omit any of these. Each test asserts that a specific class
of leakage is impossible.

  * `test_available_at_future_record_rejected` — at simulated
    time `T`, any read of a record whose `available_at > T` is
    rejected by the Time-Wall Guard and logged as
    `NO_LOOKAHEAD_VIOLATION`.
  * `test_unclosed_candle_high_low_not_visible` — the final
    `high` / `low` / `close` / `volume` of a candle whose
    `close_time > T` are not visible at `T`.
  * `test_future_tail_label_unavailable_in_blind_window` — no
    tail-label whose `available_at > window_close_time` can be
    read by any decision surface inside the blind window.
  * `test_post_discovery_outcome_unavailable_before_window_close`
    — no post-discovery outcome metric (B-B-B-D-B family) is
    readable inside the blind window before the window
    closes.
  * `test_ai_briefing_unavailable_as_truth` — AI briefings
    cannot be loaded as Truth Layer facts; AI output is
    rejected at the Truth Layer ingest path.
  * `test_replay_reflection_summary_unavailable_during_blind_window`
    — replay summaries and reflection summaries from windows
    whose `available_at > T` are unavailable to any decision
    surface at `T`.
  * `test_config_drift_invalidates_window` — if the runtime
    configuration / rule set / feature schema / data manifest /
    universe manifest hash changes mid-window, the run is
    flagged `INVALIDATED_LOOKAHEAD_OR_DRIFT` (see §F).

---

## §B. Feature Store as-of Rule (owner-review enhancement)

Feature engineering is the most common channel for accidental
look-ahead. The blind walk-forward stack therefore enforces:

  * Any feature value used at simulated time `T` MUST be
    computed only from records with `available_at <= T`.
  * The feature cache MUST be keyed by `as_of_time` (the
    simulated time at which the feature was computed). A
    feature value computed at `T1 > T` MAY NOT be reused as
    the value at `T < T1`.
  * Feature values computed after `T` MUST NOT be reused
    inside `T`.
  * The feature store MUST NOT precompute future-window
    features and expose them to any `T` earlier than the
    feature's `as_of_time`.
  * Cross-symbol features (e.g. cohort statistics, regime
    aggregates) follow the same rule — every input record's
    `available_at` must be `<= T`.

A feature read that violates §B is a `NO_LOOKAHEAD_VIOLATION`
and invalidates the run under §F.

---

## §C. Hyperparameter / Rule Search Budget (owner-review enhancement)

Unbounded sweeps overfit the history. The blind walk-forward
stack therefore caps search and forbids tuning on the test
set.

  * `max_scenarios_per_training_window` — the training window
    has a hard cap on the number of hyperparameter / rule
    candidates evaluated. The cap is part of the frozen
    config (§8.2).
  * `max_rule_candidates_promoted` — the number of candidates
    promoted from training into the next window's frozen
    rule set is capped.
  * Every rejected candidate MUST be logged with its
    rejection reason. (Silent rejection is forbidden; it
    hides effective sweeps.)
  * No unlimited parameter sweep is allowed at any stage.
  * No repeated tuning on validation or test outcomes is
    allowed. A blind window's outcome MUST NOT influence
    parameter selection for the *same* blind window or the
    *same* training window.
  * A sandbox / training-window result MAY NOT directly
    become runtime configuration. Promotion requires (i) the
    next training-window freeze and (ii) a separate review
    PR. The sandbox cannot self-promote.

---

## §D. Mandatory Final Untouched Holdout (owner-review enhancement)

Walk-forward without a final untouched holdout is
self-deception. The blind walk-forward stack therefore
mandates:

  * A **final untouched holdout** is mandatory before any
    small-capital Go / No-Go decision.
  * Recommended duration: **60 to 90 days** minimum (longer
    is acceptable; shorter is not).
  * The final holdout MUST NOT be used for tuning, rule
    selection, model selection, AI prompt tuning, or any
    other parameter / configuration decision. It is read only
    once, after every other window has closed.
  * If the final holdout result is `INCONCLUSIVE` (e.g.
    insufficient samples, failure-ledger heavy, leakage flag
    raised, drift flag raised), the result MAY NOT
    authorise small-capital live trading. `INCONCLUSIVE` is
    a `review` outcome, not a `relax` outcome.

The final holdout's data manifest is frozen at the same time
the blind walk-forward chain begins, so future data revisions
cannot retroactively rewrite it (see §E).

---

## §E. Data Revision / Late Arrival Policy (owner-review enhancement)

Real exchanges revise records (corrected funding rates,
backfilled candles, late-arriving trades). The blind
walk-forward stack therefore mandates:

  * If a record was **not** available at simulated time `T`,
    a later correction of that record MAY NOT be used inside
    `T`. The Time-Wall Guard rejects the corrected record at
    `T` based on its `available_at`.
  * A late-arriving record MAY only affect future windows
    whose `simulated_time >= record.available_at`.
  * Every data revision MUST be logged with:
      * `revision_time` (when the corrected record arrived),
      * `available_at` (when the corrected record could
        legitimately be observed; usually `revision_time`
        plus exchange publication latency),
      * `affected_window` (which blind window(s) consumed the
        prior version).
  * Replaying a window with corrected data REQUIRES an
    explicit data-manifest hash change. The corrected replay
    MUST NOT overwrite the original run's evidence; it
    becomes a new run with a new Blind Run Manifest hash.
    Both runs are kept side-by-side for audit.

---

## §F. Run Invalidation Rules (owner-review enhancement)

A blind walk-forward run that violates this constitution MUST
carry the explicit invalidation status:

> **`INVALIDATED_LOOKAHEAD_OR_DRIFT`**

A run MUST be invalidated if any of the following occurs:

  * **Configuration drift** — any frozen runtime config
    changes during the blind window.
  * **Rule-hash drift** — the rule set's content hash changes
    during the blind window.
  * **Feature-schema drift** — feature names / types /
    transformations change during the blind window.
  * **Data-manifest drift** — the data manifest hash changes
    during the blind window.
  * **Universe-manifest drift** — the universe manifest hash
    changes during the blind window.
  * **Future-record access** — a read of a record whose
    `available_at > simulated_time` is observed.
  * **Tail-label leakage** — any tail-label whose
    `available_at > window_close_time` is read by any decision
    surface inside the blind window.
  * **Post-discovery outcome leakage** — any post-discovery
    outcome metric is read inside the blind window before the
    window closes.
  * **Replay / reflection summary leakage** — any future
    replay or reflection summary is read inside the blind
    window.
  * **AI output used as truth / label / strategy sample** —
    any AI output that has been promoted into the Truth
    Layer, into a training label, into a tail label, or into
    a strategy sample.
  * **Manual sample deletion** — any post-hoc removal of
    samples from the blind window's evidence.
  * **Validation / test tuning** — any parameter, rule,
    feature, or AI prompt tuned against validation- or
    test-window outcomes.
  * **Missing failure ledger** — a run that fails to emit
    the required Failure Ledger (§16) cannot prove its
    own degradations were modelled.
  * **Unlogged runtime override** — any operator override
    issued during the blind window that is not recorded with
    timestamp, source, intent, and resulting state change.

`INVALIDATED_LOOKAHEAD_OR_DRIFT` is **not** a runtime knob.
It is a closed-status outcome that can only be removed by
**re-running the entire window** with a fresh frozen artefact
set. It cannot be overridden by AI commentary, by operator
note, by Telegram message, or by any "exception". Once
recorded, it is part of the run's permanent evidence.

---

## Acceptance criteria for this docs-only PR93

This PR (PR93) is a **constitution**, not an implementation.
Its own acceptance criteria are docs-only:

  * `docs/PHASE_11C_1D_D_STRICT_BLIND_WALK_FORWARD_SIM_LIVE_CONSTITUTION.md`
    exists and contains §1 through §20 plus owner-review
    enhancements §A through §F, verbatim with the human
    owner's draft + owner-review additions.
  * `docs/PROJECT_STATUS.md` records PR93 as
    `IN_REVIEW` with the prior 11C.1D-C entry preserved as
    historical context.
  * `docs/PHASE_GATE.md` records PR93 as an open phase whose
    successful acceptance unlocks **only** PR94
    (SimulationClock + Time-Wall Guard) — and no other phase.
  * `docs/CHANGELOG.md` carries a docs-only entry for PR93
    that explicitly states **no runtime behaviour changed**.
  * No file under `app/`, `scripts/`, `tests/`, `configs/`,
    `data/`, no `requirements.txt`, no `pyproject.toml`, and
    no `.env*` is touched by this PR.
  * `git diff --name-only` and `git diff --stat` against
    `origin/main` show only `docs/**` (and at most a
    lightweight `README.md` sync, if performed).

PR93 does **not** authorise live trading, does **not**
authorise auto-tuning, does **not** authorise the DeepSeek
hot path, does **not** authorise Telegram live outbound, does
**not** authorise opening Phase 12. **Phase 12 remains
FORBIDDEN.**

---

## Inheritance

This phase inherits, verbatim, every Phase 1, Phase 11C, Phase
11C.1A, Phase 11C.1B, Phase 11C.1C-A, Phase 11C.1C-B, Phase
11C.1C-C-A, Phase 11C.1C-C-B-A, Phase 11C.1C-C-B-B-A, Phase
11C.1C-C-B-B-B-A, Phase 11C.1C-C-B-B-B-B, Phase 11C.1C-C-B-B-B-C,
Phase 11C.1C-C-B-B-B-D, Phase 11C.1C-C-B-B-B-D-A, Phase
11C.1C-C-B-B-B-D-B, Phase 11C.1C-C-B-B-B-D-B.1, Phase
11C.1C-C-B-B-B-D-C-A, Phase 11C.1C-C-B-B-B-D-C-B, Phase
11C.1C-C-B-B-B-D-D, Phase 11C.1C-C-B-B-B-D-E, Phase
11C.1C-C-B-B-B-E-A, Phase 11C.1C-C-B-B-B-E-B, Phase
11C.1C-C-B-B-B-E-C, Phase AI-1, Phase AI-2, Phase AI-3, Phase
AI-4, Phase AI-5, Phase AI-6, Phase AI-CHECKPOINT, Phase 11C
Offline Rule Sandbox Replay, Phase 11C.1D-B Paper Shadow
Strategy Validation, and Phase 11C.1D-C Risk / Execution /
Capital Safety Matrix forbidden item.

The Risk Engine remains the single trade-decision gate. Phase
12 remains **FORBIDDEN**.
