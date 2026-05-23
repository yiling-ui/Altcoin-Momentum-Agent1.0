# AMA-RT Adaptive Market Operating System Governance

## 自适应市场操作系统架构治理文档

> **Status: GUIDANCE-ONLY architecture governance document.**
> This document is a **non-binding governance reference** that
> records the long-term architecture principles, anti-AI-hallucination
> rules, anti-context-drift rules, anti-overfitting rules, anti-black-box
> rules, and anti-AI-bypass-of-Risk-Engine rules for AMA-RT V1.4.
>
> **This document does NOT change any phase state.**
> **This document does NOT loosen any safety flag.**
> **This document does NOT authorise any new runtime behaviour.**
> **This document does NOT authorise Phase 12.**
> **This document does NOT authorise live trading.**
> **This document does NOT authorise API keys.**
> **This document does NOT authorise private endpoints.**
> **This document does NOT authorise DeepSeek trade decisions.**
> **This document does NOT authorise real Telegram outbound.**
> **This document does NOT authorise AI Learning that decides trades.**
> **This document does NOT authorise Phase 11C.1C-C-B-B kickoff
> bypassing the standard gate.**
>
> The current AMA-RT phase is **Phase 11C paper-only, late stage**
> (`Phase 11C.1C-C-B-A = ACCEPTED`,
> `Phase 11C.1C-C-B-B = NEXT_ALLOWED / NOT_STARTED`). Phase 12
> (real money / live trading) **remains FORBIDDEN**. The Phase 1
> safety lock (`mode=paper`, `live_trading=False`,
> `right_tail=False`, `llm=False`, `exchange_live_orders=False`,
> `telegram_outbound_enabled=False`,
> `binance_private_api_enabled=False`) is unchanged by this
> document. See `docs/PROJECT_STATUS.md` and `docs/PHASE_GATE.md`
> for the authoritative phase state.

---

## 1. Core Positioning

**AMA-RT is not an auto-trading bot.**
**AMA-RT is an Adaptive Market Operating System.**

AMA-RT's purpose is to operate as an adaptive layer over the live
market: it ingests real public market data, builds a structural
view of regime / candidates / clusters / liquidity / outcomes, and
expresses **paper-only** risk views that a human operator (and,
in later phases, a tightly-gated execution surface) can choose to
act on under the existing safety architecture.

AMA-RT goals:

- **Dynamically understand market structure changes.** Regimes
  shift; liquidity migrates; correlation clusters re-form. The
  system must read those shifts as first-class state, not as
  noise to be filtered out of a fixed strategy.
- **Identify right-tail opportunities.** The system's job is to
  surface where capital absorption / persistent flow is forming,
  not to predict tomorrow's price.
- **Limit systemic risk.** Risk Engine + No-Trade Gate +
  Execution FSM + Phase Gate are non-bypassable. The Adaptive
  Market Operating System is **subordinate** to the safety
  architecture, never a way around it.
- **Switch paper-only risk-expression mode by market state.**
  Across regimes, the system varies how it *describes* risk
  (`strategy_mode`, `candidate_stage`, `early_tail_score`,
  `tail_label`, `suggested_cluster_action`, etc.) — these are
  paper / virtual labels; they MUST NEVER trigger a real trade
  on their own.
- **Real trade authority is preserved.** Any real-trade
  capability (now or in the future) remains gated by the
  **Phase Gate**, the **Risk Engine**, the **Execution FSM**,
  and the **Spec §41 Go/No-Go** checklist. AMA-RT is the
  observation / interpretation / labelling layer; it does not
  hold trade authority.

---

## 2. Core Philosophy

The Adaptive Market Operating System is built on the following
beliefs, which the rest of the architecture must reflect:

- **Markets are dynamic adversarial systems.** No fixed strategy
  is permanently effective. A strategy that worked last cycle
  is evidence about *that* cycle, not a guarantee about the
  next one.
- **Fixed strategies decay.** Decay is the default outcome, not
  the exception. The system must keep validating its own
  assumptions and downgrade strategies whose statistical
  support has degraded.
- **The system studies absorption, liquidity, and structure —
  not raw price prediction.** Where capital is being absorbed,
  how liquidity is migrating across clusters, and how structure
  is forming around a candidate are closer to the underlying
  market reality than a candle-by-candle direction guess.
- **Candles can be induced.** Price prints alone can be
  spoofed, faded, painted, and momentarily distorted. Real
  trades, real depth behaviour, real funding / OI / spread
  shifts, and real cross-venue flow are closer to ground truth
  and harder to fake at scale.
- **The goal is not to predict price.** The goal is to
  understand **what kind of market behaviour, in what kind of
  market state, is more likely to attract persistent capital
  absorption.** That is a structural question about the market,
  not a directional bet on a chart.

---

## 3. AI Authority Boundary

AI / LLM components in AMA-RT (DeepSeek, any other narrative
interpreter, any future LLM-backed cognition surface) operate
under a strict, non-negotiable authority boundary.

### 3.1 AI / LLM IS allowed to do

- **Market explanation.** Plain-language explanation of what is
  visible in the structured data.
- **Narrative interpretation.** Reading qualitative narrative
  and naming it.
- **Regime interpretation.** Translating regime engine output
  into narrative-level descriptions.
- **Structural anomaly explanation.** Explaining structural
  oddities surfaced by the data.
- **Replay / reflection summarisation.** Summarising replay or
  reflection runs into human-readable narratives.
- **Evidence compression.** Condensing structured evidence into
  shorter, citation-bearing summaries.

### 3.2 AI / LLM is permanently FORBIDDEN to do

- Place an order.
- Close a position.
- Modify leverage.
- Modify position size.
- Modify a stop-loss.
- Modify a take-profit / target price.
- Bypass, override, or disable the Risk Engine.
- Bypass, override, or disable the Execution FSM.
- Bypass, override, or disable the Phase Gate.
- Trigger a real trade through any path, including
  side-channels (Telegram, exports, manifests, summaries).
- **Treat its own text output as a training fact.** The model's
  prior commentary is **never** ground truth; it is commentary.

This boundary holds across all phases, including any future
Phase 11D (LLM read-only narrative) and any future Phase 12.
AI / LLM authority is **explanatory only**.

---

## 4. Stateless AI Cognition

LLMs are not long-term, stable memory stores. Every AI inference
must be treated as a **stateless reconstruction** of cognition
over verifiable structured data.

Rules:

- **AI inference must be stateless.** Each call must reconstruct
  its understanding from structured truth, not from chat
  history.
- **Each inference must rebuild cognition from structured real
  data.** No reliance on long-running session memory as a fact
  source.
- **Chat context must NOT be used as a fact source.** The
  conversational stream is convenience for the human reviewer,
  not evidence.
- **A previous assistant response must NOT be treated as
  fact.** Prior LLM output is text; text is not a price, a
  trade, or a market state.
- **AI must never train (or be trained) on its own past
  commentary as labels.** Self-labelling is a hallucination
  attractor and is permanently prohibited.

### 4.1 Fact-source priority order

When any AI / LLM call needs to ground a claim, it MUST consult
sources in the following priority order:

1. **Exchange public market data** (real REST + real public
   WebSocket frames captured at the time the claim is made).
2. **`EventRepository`** (the canonical event log on disk).
3. **Replay / Export** artifacts (the Phase 8.5 export, the
   Phase 10A replay engine, daily reports).
4. **Structured reports** generated by the system
   (Strategy Validation Lab cohorts, daily-report sections,
   etc.).
5. **Human-approved phase docs** (`docs/PHASE_*`,
   `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
   `docs/CHANGELOG.md`, this document).
6. **AI analysis text** — **commentary only, never truth.**

If a higher-priority source contradicts a lower-priority source,
the higher-priority source wins. AI commentary at level 6 cannot
override anything above it.

---

## 5. Truth Layer

The **Truth Layer** is the immutable record of what actually
happened in the market and in the system. It is the only
acceptable substrate for claims about effectiveness.

### 5.1 Mandatory Truth Layer fields

The Truth Layer records, at minimum:

- `price`
- `volume`
- `OI` (open interest)
- `funding`
- `spread`
- `depth` (book / liquidity)
- `liquidation`
- spot / perp divergence
- `candidate_first_seen` (timestamp + price)
- `MFE` / `MAE` (max favourable / adverse excursion)
- `tail_label` (rule-based outcome label)
- risk rejection reason (`RISK_REJECTED.reason`)
- `strategy_mode` (paper / virtual)
- cluster context (cluster id / leader / size / correlated set)
- `report_id` / `opportunity_id` / `scan_batch_id` (every
  identity field needed to reproduce the record)

### 5.2 Truth Layer rules

- **AI judgements MUST cite Truth Layer fields.** A claim that a
  strategy is working must point to specific Truth Layer rows
  and fields.
- **No Truth Layer evidence ⇒ no claim of effectiveness.**
  Without Truth Layer support, a strategy / cluster / mode is
  **unsupported**, not "promising".
- **Truth Layer entries are immutable.** Corrections happen by
  emitting a new event referring to the prior `event_id`, not
  by overwriting history.
- **All Truth Layer entries carry full identity** (`report_id`,
  `opportunity_id`, `scan_batch_id`, `source_event_id`,
  `schema_version`) so any AI commentary can be unambiguously
  traced back to the underlying evidence.

---

## 6. Reality Check Layer

Every conclusion produced by an AI / LLM component or by the
Strategy Selector / Strategy Validation Lab must be passed
through a **Reality Check Layer** of hard, deterministic rules
before it is allowed to influence operator-facing output.

### 6.1 Reality Check downgrade / reject conditions

If the AI / Selector says "trend is healthy" (or any equivalent
narrative claim) but the Reality Check observes any of:

- `funding` is overheated (above configured cap)
- `spread` has widened beyond healthy band
- `depth` has collapsed
- spot volume is falling while perp is leading
- `late_chase_risk` is high
- data is stale or degraded (e.g. `ws_currently_stale=True`,
  REST geoblock fallbacks active)
- the Risk Engine has rejected the candidate
  (`RISK_REJECTED`), or the No-Trade Gate is active

then the AI / Selector conclusion MUST be **downgraded** (lower
weight, demoted to "observe", flagged in the report) or
**rejected outright**.

### 6.2 Reality Check priority

**Reality Check Layer outranks AI explanation.**
**Reality Check Layer outranks Strategy Selector output.**
**Reality Check Layer outranks AI confidence scores.**

When Reality Check disagrees with AI / Selector, Reality Check
wins, the disagreement is logged, and operator-facing surfaces
must reflect Reality Check's verdict, not the AI's.

---

## 7. Anti-Overfitting Governance

The Adaptive Market Operating System must resist the natural
tendency to overfit to small, vivid samples. The rules below
are non-negotiable.

- **No automatic loosening of rules from a small sample.** A
  handful of successes is not statistical support to relax
  thresholds.
- **No rewriting of global strategy from a single "妖币"
  / demon-coin case.** Anecdotal wins are anecdotes; they are
  not evidence to redesign the global pipeline.
- **No leverage / size increase from historical sample fit.**
  Curve-fit on past data does not authorise larger live (or
  future-live) exposure.
- **No optimisation of trade parameters using AI text labels.**
  AI narrative is commentary, not an objective function.
- **All strategy adjustments must pass, in order, every gate
  below before any production change:**
  1. **Dataset sample-count gate** (statistically meaningful
     count, configured per metric).
  2. **Validation quality gate** (Strategy Validation Lab
     cohort quality, p99 noise checks, distributional
     sanity).
  3. **Replay** (Phase 10A replay engine reproduces the
     proposed change against historical events).
  4. **Paper-only shadow validation** (the change runs in
     paper / shadow without any real-trade authority).
  5. **Human review** (a human reviewer signs off on the
     change against this governance document).
  6. **Phase Gate approval** (the change is recorded against
     the appropriate phase in `docs/PHASE_GATE.md`).

Any "auto-tuner" that bypasses any of those gates is a
governance violation and must be removed.

---

## 8. Feedback Isolation

AI / LLM components must not be allowed to learn from their own
output. The training / labelling surface is strictly isolated.

### 8.1 Allowed learning targets

The system MAY learn (under the gates in §7) from:

- `MFE` / `MAE` (real forward outcomes from the Truth Layer)
- `tail_label` (rule-based outcome label)
- `fake_breakout` events
- `missed_tail` events
- `late_chase_failure` events
- Risk-rejection outcomes (`RISK_REJECTED.reason` paired with
  the realised forward outcome)
- Replay-verified results (Phase 10A replay engine outputs)

### 8.2 Forbidden learning targets

The system MUST NEVER learn from:

- AI's own narrative text
- AI's own confidence scores
- AI's prior speculative output
- Telegram / Telegram-broadcast copy
- Unverified subjective human evaluations (a human pressing
  "looks good" without Truth Layer evidence)

This isolation is non-negotiable: it is the primary defence
against AI feedback loops, drift, and self-confirming
hallucination.

---

## 9. Architecture Layers

The Adaptive Market Operating System is composed of the
layers below. Each layer notes its current implementation
status and explicitly states whether it has trade authority.
**No layer below is authorised to trigger a real trade**: all
real-trade authority remains with the Phase Gate + Risk Engine
+ Execution FSM under the Phase 1 safety lock, and Phase 12 is
**FORBIDDEN**.

| # | Layer                          | Current implementation                                                                                                                                                                                                                                  | Not yet implemented                                                                                                                                                                  | Real-trade authority |
| - | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| 1 | Observation Layer              | Binance public REST governor (Phase 11C.1A) + routed public WS (Phase 11C.1B `MultiTransportPublicWSManager` over `/public/stream` + `/market/stream`); `MarketDataBuffer`; `AllMarketRadarBuffer`; `CandidatePool`.                                     | Cross-exchange flow ingestion; iceberg / spoof detection; private-data ingestion (forbidden under Phase 1).                                                                          | **NONE**             |
| 2 | Market Intelligence Layer      | Pre-anomaly / anomaly / state-transition / risk-rejection chain (Phase 11C.1B `WSRadarChainDriver`).                                                                                                                                                    | Liquidity intelligence; market-structure memory; lead-lag relationships; spot/perp divergence; stablecoin inflow; narrative acceleration / social saturation / bot amplification.    | **NONE**             |
| 3 | Regime Engine                  | `assess_market_regime` + `MarketRegimeAssessment` (Phase 11C.1C-A); paper-only.                                                                                                                                                                          | Regime transition prediction (deeper); narrative-aware cluster taxonomy.                                                                                                              | **NONE**             |
| 4 | Strategy Orchestrator          | `OpportunityScore` + `StrategyModeDecision` + `CandidateStageAssessment` + `ClusterContext` + `LabelQueueContract` (Phase 11C.1C-A); runtime calibration + early tail discovery v0 (Phase 11C.1C-B); paper / virtual `strategy_mode` only.                | Deeper strategy validation lab + richer cluster exposure control follow-up (Phase 11C.1C-C-B-B = NEXT_ALLOWED / NOT_STARTED).                                                         | **NONE**             |
| 5 | Risk Allocation Engine         | Phase 7 Risk Engine + No-Trade Gate; Phase 1 safety lock; Risk Engine is the **single trade-decision gate**.                                                                                                                                            | Multi-portfolio allocation; live-trade allocation (forbidden under Phase 1).                                                                                                          | gate-only (rejects)  |
| 6 | Execution FSM                  | Phase 9 Execution FSM + Reconciliation; paper ledger; **no live order surface**.                                                                                                                                                                        | Live exchange execution adapter (forbidden under Phase 1; gated by Phase 12).                                                                                                         | **NONE in paper**    |
| 7 | Replay / Verification Layer    | Phase 10A replay engine substrate; Phase 10B reflection + replay (read-only); Phase 8.5 learning-ready export.                                                                                                                                          | AI-driven replay narration (read-only, future Phase 11D).                                                                                                                              | **NONE**             |
| 8 | Truth Layer                    | `EventRepository` (Phase 2) + Phase 8.5 learning-ready contract + Phase 11C.1C-A through 11C.1C-C-B-A typed events (`MARKET_REGIME_ASSESSED`, `CANDIDATE_STAGE_CLASSIFIED`, `OPPORTUNITY_SCORED`, `STRATEGY_MODE_SELECTED`, `CLUSTER_CONTEXT_ATTACHED`, `LABEL_QUEUE_ENQUEUED`, `LABEL_TRACKING_STARTED`, `LABEL_WINDOW_UPDATED`, `LABEL_WINDOW_COMPLETED`, `TAIL_LABEL_ASSIGNED`, `MISSED_TAIL_DETECTED`, `FAKE_BREAKOUT_DETECTED`, `STRATEGY_VALIDATION_*`). | Cross-exchange flow Truth Layer; iceberg / spoof Truth Layer fields.                                                                                                                  | **NONE**             |
| 9 | Reality Check Layer            | Implicit in Risk Engine rules + `late_chase_risk` + `runtime_calibration` + WS staleness gate; partially expressed today.                                                                                                                               | Standalone Reality Check scoring module that can downgrade AI / Selector conclusions explicitly (future research).                                                                    | **NONE**             |

**Cross-cutting invariants:**

- The Phase 1 safety lock holds across **every** layer.
- No layer is authorised to bypass the Risk Engine, the
  Execution FSM, the Phase Gate, or this document.
- Paper / virtual labels (`strategy_mode`, `early_tail_score`,
  `tail_label`, `mfe_pct`, `mae_pct`,
  `suggested_cluster_action`, the `STRATEGY_VALIDATION_*`
  events, validation cohort statistics) are **descriptive
  only**; they MUST NEVER trigger a real trade.

---

## 10. Future Backlog / Not Implemented Yet

The items below are explicitly **NOT yet implemented**. Listing
them here serves as anti-hallucination defence: any claim that
they exist today is wrong. They are tracked as future research
or future phase work; this document does not authorise them.

| Item                                  | status              | trade_authority |
| ------------------------------------- | ------------------- | --------------- |
| Regime Transition Prediction          | `FUTURE_RESEARCH`   | `NONE`          |
| Liquidity Intelligence                | `FUTURE_RESEARCH`   | `NONE`          |
| Market Structure Memory               | `FUTURE_RESEARCH`   | `NONE`          |
| Narrative Acceleration                | `FUTURE_RESEARCH`   | `NONE`          |
| Social Saturation                     | `FUTURE_RESEARCH`   | `NONE`          |
| Bot Amplification                     | `FUTURE_RESEARCH`   | `NONE`          |
| Cross-exchange Flow                   | `NOT_STARTED`       | `NONE`          |
| Lead-lag Relationships                | `FUTURE_RESEARCH`   | `NONE`          |
| Spot / perp Divergence                | `NOT_STARTED`       | `NONE`          |
| Stablecoin Inflow                     | `NOT_STARTED`       | `NONE`          |
| Iceberg / Spoof Detection             | `FUTURE_RESEARCH`   | `NONE`          |
| Narrative-aware Cluster Taxonomy      | `FUTURE_RESEARCH`   | `NONE`          |
| AI Market Intelligence Layer          | `NOT_STARTED`       | `NONE`          |
| AI Interpretation Sandbox             | `NOT_STARTED`       | `NONE`          |
| AI Reality Check Scoring              | `FUTURE_RESEARCH`   | `NONE`          |

These items have `trade_authority = NONE` permanently. A future
phase that brings any of them online MUST keep
`trade_authority = NONE` until the Spec §41 Go/No-Go path
explicitly authorises otherwise (and it has not been
initiated).

---

## 11. Explicit Rejections

The following are **explicitly rejected** by this governance
document:

- **AI autonomous trading.** No AI / LLM may place, close, or
  modify any trade.
- **AI direct price prediction as a trade authority.** Even
  where the system explains likely flows, that explanation is
  commentary, not a trade signal.
- **Reinforcement learning live trading.** No RL loop may drive
  live trading. Learning, if any, runs on Truth Layer outcomes
  in paper / shadow only, and is gated by §7.
- **Black-box parameter optimisation.** Any parameter change
  must be auditable, reviewable, and traceable to Truth Layer
  evidence; opaque optimisation is rejected.
- **Infinite auto-optimisation.** No process is allowed to
  endlessly tune itself without the §7 gates and human
  review.
- **AI bypassing the Risk Engine.** The Risk Engine is the
  single trade-decision gate. AI cannot route around it.
- **AI modifying leverage / size / stop / target.** These are
  permanently outside AI authority.
- **Direct Phase 12 jump.** No phase transition skips ahead to
  Phase 12. Phase 12 requires the Spec §41 Go/No-Go checklist
  and remains **FORBIDDEN** under the Phase 1 safety lock.

---

## 12. Link to Current Phase

As of the date of this document, the authoritative phase state
recorded in `docs/PROJECT_STATUS.md` and `docs/PHASE_GATE.md`
is:

- **Current state: Phase 11C paper-only, late stage.**
- `Phase 11C.1C-C-B-A = ACCEPTED` (PR #42 merged into `main`,
  mergeCommit `cc18047`, closed 2026-05-23).
- `Phase 11C.1C-C-B-B = NEXT_ALLOWED / NOT_STARTED`.
- The current work focus is **validation / dataset / quality
  gate / replay verification** on top of Phase 11C.1C-C-A
  (`LabelTrackingRecord`) outcomes and the Phase 11C.1C-C-B-A
  Strategy Validation Lab v0 + Cluster Exposure Control
  Contracts.
- **Phase 12 remains FORBIDDEN.**

This document **does not change** any of the above. Specifically:

- **This document does not change any Phase Gate state.**
- **This document does not authorise any runtime behaviour.**
- **This document does not authorise Phase 11C.1C-C-B-B
  kickoff bypassing the standard gate.**
- **This document does not authorise Phase 12.**

For the authoritative phase state, see
`docs/PROJECT_STATUS.md` and `docs/PHASE_GATE.md`. For the
acceptance evidence audit trail, see `docs/CHANGELOG.md`.

---

## 13. Update PROJECT_STATUS / PHASE_GATE / CHANGELOG (reference, not state change)

The companion docs are updated only with **a reference** to
this governance document. The references state, in each:

- A new architecture governance document has been added at
  `docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`.
- The document is **guidance-only**.
- The document **does not change any current phase state**.
- The document **does not change any safety flag**.
- The document **does not authorise Phase 12**.

Those references are intentionally minimal. They are not phase
transitions, not acceptance records, not test results, and not
runtime changes.

---

## 14. Safety Boundary

The Phase 1 safety lock is preserved verbatim by this document:

```
mode                             = paper
live_trading                     = False
exchange_live_orders             = False
right_tail                       = False
llm                              = False
telegram_outbound_enabled        = False
binance_private_api_enabled      = False
no Binance API key
no Binance API secret
no signed endpoint
no account / order / position / leverage / margin endpoint
no private websocket
no listenKey
no DeepSeek trade decision
no real Telegram outbound
Phase 12 remains FORBIDDEN
```

This document does not loosen, soften, qualify, or rewrite any
of the above. Any future change to any of these invariants
requires the Spec §41 Go/No-Go checklist and an explicit phase
transition recorded in `docs/PHASE_GATE.md`.

---

## Document scope reminder (final)

- **Type:** Architecture governance / guidance-only.
- **Authority:** Non-binding guidance over future design and
  AI / LLM behaviour; binding *prohibitions* on AI authority,
  feedback loops, overfitting, and bypass paths as captured
  above. Any conflict with the safety architecture
  (Phase Gate, Risk Engine, Execution FSM, Phase 1 lock) is
  resolved in favour of the safety architecture.
- **Not in scope:** runtime code change, phase transition,
  acceptance evidence, test results, or any authorisation of
  new capabilities.
- **Authoritative phase state:** see `docs/PROJECT_STATUS.md`
  and `docs/PHASE_GATE.md`.
- **Phase 12 remains FORBIDDEN.**
