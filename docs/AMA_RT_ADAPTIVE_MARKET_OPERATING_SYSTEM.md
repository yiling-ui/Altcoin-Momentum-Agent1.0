# AMA-RT Adaptive Market Operating System Governance
# 自适应市场操作系统架构治理文档

> **Status:** Guidance-only architecture governance document.
> **Authority:** Long-term architectural principles + AI safety
> rails. **NOT** a phase implementation, **NOT** a runtime
> behavior change, **NOT** a phase-gate transition.
> **Scope of this PR:** docs-only.
>
> This document does **NOT** authorise any runtime behavior,
> any new phase, any new code path, any new event, any new
> configuration flag, any new exchange call, any new LLM
> call, any new Telegram outbound message, any new exchange
> private endpoint, or any change to the Phase 1 safety lock.
> It records architectural intent for future planning and
> review. It is binding as governance, not as implementation.

---

## 0. Document purpose

AMA-RT V1.4 is being built as a long-lived adaptive system,
not as a one-shot trading bot. Past experience shows three
recurring failure modes for this kind of system:

  1. **AI hallucination** — the LLM invents narratives,
     prices, regimes, or "verified results" that have no
     grounding in real market data.
  2. **Context drift** — the system's understanding of "what
     works" silently mutates across sessions because the LLM
     remembers its own prior outputs as if they were facts.
  3. **Overfitting / black-box optimisation / risk-engine
     bypass** — a single rare candidate (a "妖币" / demon
     coin) is generalised into a global rule, leverage / size
     / stops are quietly tuned by the AI, and the Risk Engine
     stops being the single trade-decision gate.

This document defines the architectural rails that prevent
all three. Every future phase, every future PR, every future
AI integration in this repository **MUST** read this
document and remain inside its rails. Violations are
review-blocking.

The document is intentionally *prose + invariants* rather
than code: code lives in `app/`, `scripts/`, `tests/`,
`risk/`, `execution/`, `llm/`, `telegram/`, `exchange/`, and
all of those are **out of scope for this PR**.

---

## 1. Core Positioning

> **AMA-RT is not an auto-trading bot.**
> **AMA-RT is an Adaptive Market Operating System.**

The system's role is to **continuously observe the market,
re-interpret the market, and re-allocate attention** as
market structure changes. Trading capability is one possible
output of the system, not its identity.

Goals (in order of priority):

  1. **Dynamically understand market structure changes.**
     What regime is the market in? What is the current
     dominant narrative? What is changing right now? What
     was true yesterday that is no longer true today?
  2. **Identify right-tail opportunities.** The system is
     biased toward asymmetric, low-frequency,
     high-information events (the "right tail"), not toward
     stable mid-frequency mean-reversion signals.
  3. **Limit systemic risk.** No single rare event, no
     single AI judgement, no single strategy regime is ever
     allowed to threaten the survival of capital.
  4. **Switch paper-only risk-expression mode** across
     market regimes. Different regimes warrant different
     paper / virtual risk expressions; the *regime selector*
     does not select trades, it selects the **shape** of the
     paper expression.
  5. **Real trading capability — when, and if, it is ever
     enabled — remains gated by the Phase Gate, the Risk
     Engine, the Execution FSM, and the Spec §41 Go/No-Go
     checklist.** None of those four gates may be bypassed
     by the AI, by the strategy selector, by the validation
     lab, by any LLM output, or by any future "smart"
     component.

Concretely, today (Phase 11C paper-only):

  - There is no live trading.
  - There is no real-money path.
  - The system observes Binance public market data, builds
    the adaptive candidate / strategy validation surface,
    and writes paper / virtual outcomes only.
  - "Trade" in this repository, **today**, means a paper /
    virtual expression in `events.db` and the daily report,
    nothing more.

---

## 2. Core Philosophy

The architectural philosophy below is not a slogan; it is the
basis on which every later layer is constructed.

  - **The market is a dynamic adversarial system. No fixed
    strategy is permanently valid.** Any strategy that worked
    yesterday is statistically more likely to fail today
    than to keep working. The system must *expect* its own
    rules to decay.
  - **Fixed strategies fail.** A strategy that does not
    adapt to regime, liquidity, narrative saturation, and
    capital flow will eventually meet a market it was not
    designed for. The system therefore prefers
    *configurable, regime-aware, paper-validated* strategies
    over hard-coded ones.
  - **The system researches capital absorption, liquidity,
    and market structure — not raw price prediction.** Price
    is the most easily manipulated, most easily induced
    surface of the market. Real volume, real liquidity
    behavior, real funding, real spread, real depth, real
    capital migration are closer to "what actually
    happened."
  - **Candles can be induced; real fills, liquidity behavior,
    and capital migration are closer to market truth.**
    Therefore the Truth Layer is built on fills / volume /
    OI / funding / spread / depth / liquidation /
    spot-perp divergence, not on candle shapes alone.
  - **The system's goal is not to predict price.** The
    system's goal is to **understand which market behaviors,
    in which market regimes, are more likely to attract and
    retain real capital** — i.e. which behaviors are more
    likely to form *durable absorption*. Absorption, not
    prediction, is the design objective.

If a future PR drifts toward "predict next bar direction"
or "AI tells us where price goes," it is out of philosophy.

---

## 3. AI Authority Boundary

This section is the most important rail in the document. It
is the contract that every LLM / AI integration in this
repository must obey, forever, regardless of capability
level.

### 3.1 Allowed AI / LLM behaviors

AI / LLM **may** do, and only do, the following:

  - **Market explanation.** Describe what the system
    already observed, in human language, against a
    structured payload it was given.
  - **Narrative interpretation.** Read social / news /
    headline context (when such a layer exists) and propose
    a *labelled* interpretation, never a trade.
  - **Regime interpretation.** Read regime / structure
    metrics and explain the current regime in human
    language.
  - **Structural anomaly explanation.** Given structured
    anomaly fields, explain *what kind* of anomaly this
    looks like.
  - **Replay / reflection summarisation.** Read a closed
    replay batch and produce a human-readable summary.
  - **Evidence compression.** Take many structured events
    and produce a shorter human-readable digest, without
    inventing fields not in the input.

In all cases the AI / LLM produces **commentary on top of
structured truth**, never the truth itself.

### 3.2 Forbidden AI / LLM behaviors (forever)

AI / LLM **MUST NEVER**, in any phase, in any environment,
in any configuration, do the following:

  - Place an order.
  - Close a position.
  - Modify leverage.
  - Modify position size.
  - Modify stop-loss.
  - Modify take-profit / target price.
  - Bypass the Risk Engine.
  - Bypass the Execution FSM.
  - Bypass the Phase Gate.
  - Trigger a real trade by any indirect mechanism (e.g.
    writing a flag that another component reads as
    authority).
  - Treat its own text output as a training fact, a label,
    or a ground-truth signal.

These prohibitions are **unconditional** and not weakened by
phase progression, by future "AI Learning" work, or by any
future capability upgrade. If a future PR introduces a path
where AI text can change leverage / size / stop / target /
order direction, that PR violates this document and must be
rejected at review.

### 3.3 Why this rail exists

Because LLMs hallucinate. Because LLMs can be prompt-injected
through user-controlled text (Telegram, news headlines,
social posts). Because giving an LLM *any* path to mutate
risk parameters is equivalent to giving an attacker that
path. The Risk Engine + Execution FSM + Phase Gate are the
only trade-decision gates and they are deterministic.

---

## 4. Stateless AI Cognition

LLMs are **not** long-lived, stable memory stores. The
system must treat every LLM invocation as a fresh, untrusted
worker that has no memory of prior conversations.

Rules:

  - **AI inference must be stateless.** Every AI call must
    re-derive its understanding from structured real data,
    not from chat history.
  - **No reliance on chat context as a fact source.** The
    fact that a previous assistant message claimed something
    is **not** evidence that it is true.
  - **No reuse of previous assistant responses as facts.**
    Quoting "the AI said X yesterday" carries zero
    epistemic weight. The system must look at the Truth
    Layer instead.
  - **No use of AI's own past analysis as training labels.**
    The label set used for any future "learning" component
    is restricted to *real market outcomes*, see §6 and §8.
  - **Re-grounding on every call.** Every AI call must be
    given the *current* structured payload (Truth Layer
    + Reality Check + structured report) and must re-derive
    its narrative from that payload, not from memory.

### 4.1 Fact source priority (highest first)

The system may rely only on the following, ranked:

  1. **Exchange public market data** (Binance public REST /
     WebSocket — paper-only today).
  2. **`EventRepository`** — the append-only events.db record
     of what the system actually emitted, with timestamps.
  3. **Replay / Export** — the Phase 8.5 / Phase 10A replay
     and export artefacts derived from `EventRepository`.
  4. **Structured reports** — the daily report, the
     `StrategyValidationReport`, the
     `StrategyValidationDataset`, and similar
     deterministically-built artefacts.
  5. **Human-approved phase docs** — `docs/PHASE_*.md`,
     `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
     `docs/CHANGELOG.md`, this document.
  6. **AI analysis text — only as commentary, never as
     truth.** AI narrative may sit *next to* a structured
     payload; it may not *replace* it, *override* it, or
     *fabricate* it.

If a downstream component needs a value, it reads from
priority 1–5. It never reads from priority 6 as authority.

---

## 5. Truth Layer

The Truth Layer is the immutable, append-only, auditable
record of *what actually happened in the market and what the
system actually emitted*. It is the substrate every later
layer depends on.

### 5.1 Required fields

The Truth Layer records, at minimum, the following
structured facts (paper / virtual today, deterministic
either way):

  - `price`
  - `volume`
  - open interest (`OI`)
  - `funding`
  - `spread`
  - `depth`
  - `liquidation`
  - spot / perp divergence
  - candidate `first_seen` (timestamp + price)
  - `MFE` (maximum favourable excursion)
  - `MAE` (maximum adverse excursion)
  - `tail_label` (rule-based, no LLM)
  - risk rejection reason (every Risk Engine veto, with
    reason code)
  - `strategy_mode` (paper / virtual selector output)
  - cluster context (cluster id, cluster size, cluster
    leader, suggested cluster action — paper / report only)
  - `report_id` / `opportunity_id` / `scan_batch_id`
    identity triplet so every downstream artefact can be
    traced back to the source event.

### 5.2 Truth Layer rules

  - **Immutability.** Truth Layer rows are append-only.
    Editing past rows is forbidden; corrections are written
    as new rows that reference the original.
  - **Citation requirement.** Any AI judgement, any strategy
    validation conclusion, any cluster action, any daily
    report claim must reference the Truth Layer field(s)
    that support it. Claims without Truth Layer citation
    are **not** acceptable as evidence.
  - **No claim of strategy effectiveness without Truth
    Layer evidence.** "Strategy X works" is a forbidden
    claim unless backed by sample-level Truth Layer rows
    that the validation pipeline aggregated.
  - **The Truth Layer is the single source of truth.** When
    the AI narrative disagrees with the Truth Layer, the
    Truth Layer wins.

The Truth Layer in this repository is realised, today, by:

  - `app/database/` (events.db, schemas under
    `app/database/schemas/`),
  - `EventRepository`,
  - the Phase 8.5 export,
  - the Phase 11C.1C-C-A `LabelTrackingRecord` outcomes,
  - the Phase 11C.1C-C-B-A `StrategyValidationSample` /
    `StrategyValidationReport`,
  - the Phase 11C.1C-C-B-B-A `StrategyValidationDataset`.

This document does **not** modify any of those. It only
declares them as the canonical Truth Layer.

---

## 6. Reality Check Layer

Even if the AI judgement is well-formed, even if the
strategy selector recommends a paper expression, even if
the daily report looks healthy, the system **must** apply a
Reality Check before any conclusion is allowed to settle.

### 6.1 Reality Check is hard-rule, not AI

The Reality Check Layer is a deterministic gate that
inspects the Truth Layer for disconfirming evidence. It is
**not** an LLM. It is a set of explicit conditions.

Examples of Reality Check disconfirmers:

  - `funding` is overheated (above configured threshold).
  - `spread` is widening abnormally.
  - `depth` has collapsed (book thinness exceeds
    configured threshold).
  - Spot volume is falling while perp price is rising.
  - `late_chase_risk` is high.
  - Data is stale or degraded (`ws_stale`,
    `ingestion_errors`, `rate_limit_ban`).
  - The Risk Engine has rejected the candidate.

If any of these fire, the AI judgement and the strategy
selector recommendation **must be downweighted or rejected.**

### 6.2 Reality Check priority

  - **Reality Check > AI explanation.**
  - **Reality Check > Strategy Selector recommendation.**
  - **Reality Check > daily-report headline.**
  - **Risk Engine > Reality Check** (the Risk Engine remains
    the absolute trade-decision gate; Reality Check is an
    *additional* downweight, not a replacement).

### 6.3 Reality Check in the current repo

Reality-Check-shaped behavior is already partially expressed
in the existing repository (Risk Engine, no-trade gate,
manipulation detector, `late_chase_risk`, `ws_stale_count`,
HTTP 429 / 418 handling). This document does **not** modify
those. It declares them as the Reality Check Layer and
forbids future PRs from routing around them.

---

## 7. Anti-Overfitting Governance

Overfitting is the failure mode where rare success cases
quietly become global rules. The following rails are
permanent.

### 7.1 Forbidden behaviors

  - **No automatic rule loosening from small samples.** A
    strategy may not auto-loosen its thresholds because two
    or three recent candidates "looked good."
  - **No global strategy change from a single 妖币 (demon
    coin) case.** A single rare winner is anecdote, not
    evidence.
  - **No leverage / position-size increase from historical
    sample fits.** Backtest-style sample fitting may **never**
    feed leverage / size knobs.
  - **No tuning of trading parameters from AI text labels.**
    AI narrative is not a label. See §8 (Feedback Isolation).

### 7.2 Required gates before any strategy adjustment

Any change to strategy thresholds, scoring, or gating must
pass **all** of the following:

  1. **Dataset sample-count gate** — minimum sample count
     per cohort. (Today: the Phase 11C.1C-C-B-B-A
     `StrategyValidationQualityGate` v0 expresses an early
     version of this as a *sample-trust* gate; see
     `docs/PHASE_11C_1C_C_B_B_VALIDATION_DATASET_QUALITY_GATE.md`.)
  2. **Validation quality gate** — `pass` / `warn` / `fail`
     descriptive label. `warn` and `fail` are
     review-blocking for parameter changes.
  3. **Replay** — the change must replay against historical
     `events.db` without contradiction.
  4. **Paper-only shadow validation** — the change runs
     side-by-side in paper mode for a configurable cohort
     window before any further escalation.
  5. **Human review.**
  6. **Phase gate approval** — the change is associated
     with a phase that has explicit acceptance evidence on
     `docs/PHASE_GATE.md`.

Skipping any of the six is review-blocking.

### 7.3 Quality-gate semantics (today)

Today the `validation_quality_gate_status` produced by Phase
11C.1C-C-B-B-A is descriptive (`pass` / `warn` / `fail`) and
**MUST NEVER** trigger a real trade. It is a *sample trust*
label for human review, not a *strategy quality* label and
certainly not a trade authority.

---

## 8. Feedback Isolation

Self-supervised loops are a known cause of model collapse
and cognitive drift. AMA-RT must isolate AI feedback from AI
self-reference.

### 8.1 What may be learned (allowed label sources)

  - `MFE` / `MAE` outcomes (real or paper-deterministic).
  - `tail_label` (rule-based, no LLM).
  - `fake_breakout` outcomes.
  - `missed_tail` outcomes.
  - `late_chase_failure` outcomes.
  - Risk-rejection outcome (the rejection itself, plus the
    realised post-rejection trajectory recorded in the
    Truth Layer).
  - Replay-verified result (a replay run that produces the
    same labels deterministically).

All of the above are *exogenous* to the AI: they come from
the market or from rule-based deterministic processors.

### 8.2 What may NOT be learned (forbidden label sources)

  - The AI's own narrative text.
  - The AI's own confidence score / phrasing of certainty.
  - The AI's prior speculative text from a previous session.
  - Telegram message copy / commentary the system produced.
  - Unverified human subjective evaluation (e.g. "this looked
    great") not anchored to a Truth Layer field.

### 8.3 Why

Letting AI learn from AI is a feedback loop with no
external grounding. Letting AI learn from its own Telegram
copy is a feedback loop *plus* potential prompt-injection
surface. Both are forbidden.

---

## 9. Architecture Layers

The conceptual layering of AMA-RT is recorded below. This
section is **descriptive of intent**, not prescriptive of
new code. Each layer is annotated with current state.

### Layer index (top-down)

| # | Layer                          | Trade authority |
|---|--------------------------------|-----------------|
| 1 | Observation Layer              | NONE            |
| 2 | Market Intelligence Layer      | NONE            |
| 3 | Regime Engine                  | NONE            |
| 4 | Strategy Orchestrator          | NONE (paper)    |
| 5 | Risk Allocation Engine         | **GATE**        |
| 6 | Execution FSM                  | **GATE**        |
| 7 | Replay / Verification Layer    | NONE            |
| 8 | Truth Layer                    | NONE (substrate)|
| 9 | Reality Check Layer            | DOWNWEIGHT      |

Only layers 5 and 6 are trade-decision gates. **No other
layer may directly authorise a trade.** No AI / LLM may
authorise a trade at any layer.

### Layer state today

  - **Observation Layer.** Partially implemented:
    Binance public REST + public WS via `app/exchanges/`,
    `MarketDataBuffer`, the Phase 11C.1A rate-limit
    governor, the Phase 11C.1B WS-first all-market radar,
    the `SymbolUniverse` / exchangeInfo-as-truth contract.
    Trade authority: **NONE**.
  - **Market Intelligence Layer.** Partially implemented:
    `app/adaptive/cluster.py`, `app/adaptive/context.py`,
    candidate scoring, the Phase 11C.1C-B runtime
    calibration block (15 fields), early-tail discovery.
    Narrative / liquidity / cross-exchange / lead-lag /
    bot-amplification / iceberg-spoof intelligence are
    **NOT** implemented (see §10). Trade authority:
    **NONE**.
  - **Regime Engine.** Partially implemented:
    `app/adaptive/regime.py`,
    `app/adaptive/strategy_validation.py` cohort
    aggregation. Regime *transition prediction* is **NOT**
    implemented (see §10). Trade authority: **NONE**.
  - **Strategy Orchestrator.** Partially implemented:
    `app/adaptive/selector.py`,
    `app/adaptive/scoring.py`, `app/adaptive/stage.py`,
    Phase 11C.1C-A strategy selector contracts. Output is
    paper / virtual `strategy_mode` only. Trade authority:
    **NONE (paper)**.
  - **Risk Allocation Engine.** Implemented as the existing
    Risk Engine + no-trade gate (Phase 7). The Risk Engine
    is the *single* trade-decision gate. Trade authority:
    **GATE**.
  - **Execution FSM.** Implemented (Phase 9 — paper
    today). The FSM is the second gate; orders never reach
    the exchange except via this FSM, and today it is
    paper-only. Trade authority: **GATE**.
  - **Replay / Verification Layer.** Partially implemented:
    Phase 10A replay engine substrate, Phase 10B reflection
    + replay (read-only), Phase 8.5 export, Phase
    11C.1C-C-B-B-A dataset replay. Trade authority:
    **NONE**.
  - **Truth Layer.** Implemented as `EventRepository` /
    events.db / Phase 8.5 learning-ready payload. Trade
    authority: **NONE (substrate)**.
  - **Reality Check Layer.** Partially implemented as the
    Risk Engine veto reasons, manipulation detector,
    `late_chase_risk`, `ws_stale_count`, HTTP 429 / 418
    handling. A first-class *AI Reality Check Scoring*
    layer is **NOT** implemented (see §10). Trade
    authority: **DOWNWEIGHT** (and it never *grants*
    authority; it can only *withhold* it).

This document does **not** create any of the above. It
records the layering and the trade-authority annotation.

---

## 10. Future Backlog / Not Implemented Yet

The following capabilities are **not implemented**, are
**not authorised**, and **must not be claimed as shipped**
in any current phase doc, PR description, daily report,
Telegram message, or AI narrative.

| # | Capability                                | status         | trade_authority |
|---|-------------------------------------------|----------------|-----------------|
|  1 | Regime Transition Prediction             | NOT_STARTED    | NONE            |
|  2 | Liquidity Intelligence                   | NOT_STARTED    | NONE            |
|  3 | Market Structure Memory                  | NOT_STARTED    | NONE            |
|  4 | Narrative Acceleration                   | FUTURE_RESEARCH| NONE            |
|  5 | Social Saturation                        | FUTURE_RESEARCH| NONE            |
|  6 | Bot Amplification (detection)            | FUTURE_RESEARCH| NONE            |
|  7 | Cross-exchange Flow                      | NOT_STARTED    | NONE            |
|  8 | Lead-lag Relationships                   | NOT_STARTED    | NONE            |
|  9 | Spot / perp Divergence                   | NOT_STARTED    | NONE            |
| 10 | Stablecoin Inflow                        | NOT_STARTED    | NONE            |
| 11 | Iceberg / Spoof Detection                | FUTURE_RESEARCH| NONE            |
| 12 | Narrative-aware Cluster Taxonomy         | FUTURE_RESEARCH| NONE            |
| 13 | AI Market Intelligence Layer             | FUTURE_RESEARCH| NONE            |
| 14 | AI Interpretation Sandbox                | FUTURE_RESEARCH| NONE            |
| 15 | AI Reality Check Scoring                 | FUTURE_RESEARCH| NONE            |

Rules for this backlog:

  - **No item above may be claimed as shipped.** Any PR /
    report / Telegram message / AI narrative that says
    "AMA-RT does X" where X is in this table is **wrong**
    and must be corrected before merge.
  - **No item above grants trade authority.** When (and
    only when) an item is later promoted to a phase, the
    promotion must follow §7 (Anti-Overfitting Governance)
    and §13 (Phase / Status / Changelog discipline).
  - **No item above bypasses the Risk Engine or Execution
    FSM.** Items 13 / 14 / 15 (the AI-flavoured ones) are
    explicitly subject to §3 (AI Authority Boundary).

---

## 11. Explicit Rejections

The following are **permanently** rejected by this
governance document. Any future PR proposing them must be
rejected at review unless this document is first updated
with explicit human approval.

  - **AI autonomous trading.** AI never holds trade
    authority.
  - **AI direct price prediction.** The system's job is
    structural understanding, not next-bar guessing; AI
    output framed as "price will go to X" is rejected.
  - **Reinforcement learning in live trading.** RL on a
    live order book is rejected.
  - **Black-box parameter optimisation.** Optimisers that
    mutate runtime knobs without §7's six-gate process are
    rejected.
  - **Infinite auto-optimisation.** No background loop may
    self-tune without human approval and phase-gate
    acceptance.
  - **AI bypassing the Risk Engine.** Any path where AI
    output reaches an order without going through the Risk
    Engine is rejected.
  - **AI modifying leverage / size / stop-loss / target.**
    See §3.2.
  - **Direct jump to Phase 12.** Phase 12 is reachable only
    via Spec §41 Go/No-Go and only via the standard
    phase-gate progression.

---

## 12. Link to Current Phase

This document is published while the repository is in the
**Phase 11C paper-only second half**. Specifically:

  - The repository has accepted Phase 11C.1A, Phase 11C.1B,
    Phase 11C.1C-A, Phase 11C.1C-B, Phase 11C.1C-C-A, and
    Phase 11C.1C-C-B-A.
  - Phase 11C.1C-C-B-B-A is currently `IN_REVIEW` (PR #44).
  - Current work focus is **validation / dataset / quality
    gate / replay verification**, not new runtime
    capability.
  - **Phase 12 (real money / live trading) remains
    FORBIDDEN.**

This governance document:

  - Does **not** change any phase gate.
  - Does **not** authorise any runtime behavior.
  - Does **not** flip any safety flag.
  - Does **not** advance Phase 11C.1C-C-B-B-A to ACCEPTED.
  - Does **not** kick off Phase 11C.1C-C-B-B-B.
  - Does **not** authorise live trading, API keys, signed
    endpoints, private WebSockets, `listenKey`, DeepSeek
    trade decisions, real Telegram outbound, or Phase 12.

It is **guidance-only**, binding as architectural intent.

For the authoritative phase ledger see `docs/PHASE_GATE.md`
and `docs/PROJECT_STATUS.md`.

---

## 13. Update PROJECT_STATUS / PHASE_GATE / CHANGELOG

The companion edits to `docs/PROJECT_STATUS.md`,
`docs/PHASE_GATE.md`, and `docs/CHANGELOG.md` shipped in
this PR record only the following:

  - A new **architecture governance document** has been
    added (this file).
  - The new document is **guidance-only**.
  - The new document **does not change the current phase**.
  - The new document **does not change any safety flag**.
  - The new document **does not authorise Phase 12**.

No phase entry is flipped, no acceptance evidence is added,
no new event is plumbed, no new code path is created, no
new test is added.

---

## 14. Safety Boundary

The Phase 1 safety lock and every Phase 11C.1B / 11C.1C-A /
11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A
forbidden item carry over **unchanged** under this
document. Specifically, the following must hold and are
**not** modified by this PR:

```
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

In addition:

  - **No Binance API key.**
  - **No Binance API secret.**
  - **No signed endpoint** call.
  - **No account / order / position / leverage / margin
    endpoint** call.
  - **No private WebSocket** subscription.
  - **No `listenKey`** / user data stream.
  - **No DeepSeek trade decision.**
  - **No real Telegram outbound.**
  - **Phase 12 remains FORBIDDEN.**

If any future PR — including future PRs that *cite this
document* — appears to weaken any of the above, that PR is
out of scope for this document and must be rejected at
review unless this document and the Phase 1 safety lock are
both first amended via human-approved phase-gate work.

---

## Appendix A. Document classification

  - **Type:** Architecture governance.
  - **Authority:** Long-term, binding.
  - **Scope of this PR:** docs-only.
  - **Runtime effect:** none.
  - **Phase effect:** none.
  - **Safety flag effect:** none.
  - **Trade authority granted:** none.
  - **Phase 12 status:** FORBIDDEN (unchanged).

## Appendix B. Reading order for new contributors

  1. `docs/PROJECT_STATUS.md` — what phase we're in.
  2. `docs/PHASE_GATE.md` — the authoritative phase ledger.
  3. `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` — the
     production spec (incl. §41 Go/No-Go).
  4. **This document** — the architectural rails.
  5. The relevant `docs/PHASE_*.md` for the current open
     phase.

If a contributor's PR appears to conflict with this
document, the PR is wrong by default and must either be
revised or this document must be amended *first* via a
separate, human-approved governance PR.
