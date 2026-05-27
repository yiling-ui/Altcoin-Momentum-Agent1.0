# AMA-RT AI Layer Engineering Spec

> **Status:** Constitution / docs baseline. Paper / report /
> evidence only. **No runtime effect.** This document defines
> the boundaries and contracts that any AI / LLM / DeepSeek
> integration in AMA-RT V1.4 *must* respect. It does **not**
> introduce a new runtime module, a new event type, a new
> trading rule, or a new transport. Phase 12 remains
> **FORBIDDEN**.

## 0. Scope and identity

AMA-RT is **not** a generic auto-trading bot. AMA-RT V1.4 is
an **Adaptive Market Operating System** whose long-term goal
is to keep running stably, adapt to changing market structure,
and capture the fattest right tail of the altcoin market.
Short-term 5x+ is a **direction**, never a return promise.

The AI Layer (DeepSeek and any future LLM provider) sits
**alongside** the existing Truth Layer (`events.db`, replay,
reflection, exports) and **never replaces** it. The Risk
Engine remains the single trade-decision gate.

## 1. Four root constraints

The AI Layer is bound by four root constraints. These
constraints must be enforced in code, in tests, and in any
future provider adapter (e.g. DeepSeek, OpenAI, Anthropic).
They cannot be relaxed by a "smarter prompt", a fine-tune, a
multi-agent setup, or a chain-of-thought / tool-use harness.

### 1.1 Responsibility Isolation

**AI is read-only. AI does not execute.**

The AI Layer **must never**:

  - place an order;
  - close a position;
  - change leverage;
  - change position size;
  - change stop-loss;
  - change target price / take-profit;
  - override the Risk Engine;
  - override the Execution FSM;
  - alter runtime configuration (`symbol_limit`,
    candidate-pool capacity, anomaly thresholds, Regime
    weights, strategy parameters, capital flow rules,
    profit-harvest rules, rebase rules, redaction rules,
    safety flags).

The AI Layer is **observer + commentary** only. The Risk
Engine and the Execution FSM are the only trade-authority
surfaces. The four `ExchangeClientBase` write surfaces
(`create_order`, `cancel_order`, `set_leverage`,
`set_margin_mode`) continue to raise `SafeModeViolation` in
paper mode.

### 1.2 Stateless Inference

**Every AI call must be independent.**

The AI Layer **must**:

  - receive its inputs as a freshly constructed
    *Evidence Bundle* assembled from the Truth Layer at
    call time;
  - infer **only** from that Evidence Bundle.

The AI Layer **must not**:

  - depend on previous AI answers;
  - depend on its own chat history;
  - depend on previous briefings, summaries, or
    reflections it produced;
  - depend on long-lived "memory" of its own conclusions.

If a downstream consumer wants context across AI calls, that
context must be re-derived from the Truth Layer every call,
not carried in the AI's own session.

### 1.3 Hard Rule Anchoring

**Every AI conclusion must cite Truth Layer evidence and
pass Reality Check.**

Each AI output must include `evidence_refs` that point at
concrete, replayable artefacts in the Truth Layer (event
ids, snapshot ids, dataset rows, export bundle entries).

  - **No `evidence_refs` ⇒ no accepted AI conclusion.**
  - The Reality Check stage cross-checks the AI output
    against the cited evidence and rejects (degrades) any
    output that is unsupported, contradicted, or cannot
    be located.
  - "Confidence" without `evidence_refs` is **not** a
    substitute for evidence. Free-form rationale is
    commentary, not truth.

### 1.4 Feedback Isolation

**AI must not learn from its own text output.**

  - AI text is **commentary**, not truth.
  - Only **realized market outcomes** and **verified
    market facts** (Truth Layer) may be used for
    learning, retrospective evaluation, or later
    analysis.
  - The AI Layer must not be fed back its own historical
    answers as training data, fine-tune data,
    self-distillation data, or RAG seed data.
  - The AI Layer must not be wired into a closed loop
    where its own past briefings influence the next
    briefing's prompt.

This is what distinguishes AMA-RT's AI Layer from a
self-reinforcing "AI trader". AMA-RT does **not** allow
AI-to-AI feedback, AI-to-Risk-Engine feedback, or
AI-to-Execution-FSM feedback.

## 2. Allowed DeepSeek first-version outputs

The first DeepSeek integration is restricted to the
following output types. Each is a **descriptive label /
narrative** for human review. None of them grants trade
authority.

  - `MarketIntelligenceSummary`
  - `EvidenceCompressionReport`
  - `ReplaySummary`
  - `ReflectionSummary`
  - `OperatorBriefing`
  - `RegimeExplanation`
  - `CoverageAuditInterpretation`
  - `PostDiscoveryOutcomeExplanation`
  - `ContradictionSummary`
  - `EvidenceQualityAssessment`

Every output must:

  - be expressible as a closed schema (no free-form
    trade-action fields);
  - carry `evidence_refs` pointing at the Truth Layer;
  - be redacted via the existing
    `app.exports.redaction.redact()` surface before
    surfacing in any operator-facing channel;
  - be runnable / inspectable from replay artefacts.

## 3. Forbidden DeepSeek outputs

The following fields are **forbidden** in any AI / DeepSeek
output. If the model emits them, they must be stripped, the
result must be marked degraded, and the strip must be
recorded in the audit trail. The list is the union of
trade-action and runtime-knob fields:

  - `buy`
  - `sell`
  - `long`
  - `short`
  - `direction`
  - `entry`
  - `exit`
  - `position_size`
  - `leverage`
  - `stop`
  - `stop_loss`
  - `target`
  - `take_profit`
  - `risk_budget`
  - `order`
  - `execution_command`
  - `runtime_config_patch`
  - `symbol_limit_patch`
  - `threshold_patch`
  - `candidate_pool_patch`
  - `regime_weight_patch`
  - `strategy_parameter_patch`
  - `signal_to_trade`
  - `should_buy`
  - `should_short`

The forbidden list is **additive** with the existing Phase
10C forbidden trade-action set. Anything that resembles a
trade decision, an execution command, or a runtime tuning
patch is forbidden regardless of the exact field name; the
list above is the lower bound, not the upper bound.

## 4. DeepSeek first-version boundary

The first version of any DeepSeek (or equivalent LLM)
integration must satisfy every clause below:

  - **Sandbox / offline only.** No hot path. No call from
    the Risk Engine, the Execution FSM, the Capital Flow
    Engine, the Reconciler, or the public-market runner.
  - **No Risk Engine input.** The Risk Engine must remain
    independent of any AI / LLM signal. The Risk Engine
    is the single trade-decision gate.
  - **No Execution FSM input.** The Execution FSM must
    remain independent of any AI / LLM signal.
  - **No live Telegram outbound.** Any DeepSeek output
    surfaced into Telegram must go through the Phase 10D
    `FakeTelegramClient` recorder by default. Real
    Telegram outbound remains gated by Spec §41 Go/No-Go.
  - **No private exchange / account state** in the prompt
    or in the Evidence Bundle. No API key, no API secret,
    no `listenKey`, no signed-endpoint payload, no
    account / order / position / leverage / margin
    snapshot.
  - **No API secrets in prompt.** The prompt builder must
    fail closed if a credential-shaped substring is
    detected.
  - **No learning from AI output.** See §1.4.
  - **`evidence_refs` required.** See §1.3.
  - **Reality Check required.** Any output without
    Reality Check is degraded.

## 5. Phase posture

  - **Phase 12 (real money / live trading) remains
    FORBIDDEN.** Nothing in this spec authorises Phase
    12. The Spec §41 Go/No-Go checklist is the only path
    forward, and it has not been initiated.
  - The AI Layer described here is the docs baseline for
    later phases (`AI Layer Constitution docs baseline` →
    `DeepSeek Market Intelligence Sandbox` → `AI Reality
    Check / Evidence Citation Contract`). Each later
    phase requires its own kickoff PR, brief, scope,
    boundary table, forbidden list, and acceptance
    evidence.
  - This document does **not** ship runtime code, tests,
    config, or a transport. It is a constitution for
    future PRs to conform to.

## 6. Safety flag invariants

Across every AI / DeepSeek work item gated by this spec the
following must hold:

  - `mode=paper`
  - `live_trading=False`
  - `exchange_live_orders=False`
  - `right_tail=False`
  - `llm=False`
  - `telegram_outbound_enabled=False`
  - `binance_private_api_enabled=False`

No Binance API key, no Binance API secret, no signed
endpoint, no account / order / position / leverage / margin
endpoint, no private WebSocket, no `listenKey`, no real
Telegram outbound, no DeepSeek trade decision.

The Risk Engine remains the single trade-decision gate.
Phase 12 remains **FORBIDDEN**.
