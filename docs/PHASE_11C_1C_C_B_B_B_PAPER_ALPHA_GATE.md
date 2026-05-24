# Phase 11C.1C-C-B-B-B-A — Paper Alpha Gate v0 (docs-only kickoff)

> **Status: NEXT_ALLOWED / NOT_STARTED.** This document is a
> **docs-only kickoff / scope-alignment** record for Phase
> 11C.1C-C-B-B-B-A. **No runtime code is shipped by the PR
> that introduces this document.** Implementation will land in
> a separate PR after this kickoff is reviewed and accepted.
>
> **Phase 11C.1C-C-B-B-B-A (Paper Alpha Gate v0) is paper /
> report only.** **NOT** live trading. **NOT** AI Learning.
> **NOT** automatic parameter optimisation. **NOT**
> reinforcement learning. **NOT** the complete Strategy
> Validation Lab follow-up. **NOT** Phase 12.
>
> The Risk Engine remains the single trade-decision gate. The
> Paper Alpha Gate v0 result (`PASS` / `WARN` / `FAIL` /
> `INCONCLUSIVE`) is a **descriptive label** for human review
> and **MUST NEVER trigger a real trade**, **MUST NEVER**
> modify position size, leverage, stop-loss, target price,
> Risk Engine state, or Execution FSM state.

## Phase boundary (parent / child relationship)

  - **Phase 11C.1C-C-B-B-A** — `ACCEPTED` (PR #44 merged into
    `main`, 2026-05-23, mergeCommit `3ecfc3b`). Strategy
    Validation Dataset Builder & Quality Gate v0. Paper /
    report-only. The dataset / summary / quality-gate
    artefacts produced by this slice are the *inputs* the
    Paper Alpha Gate v0 reads from.
  - **Phase 11C.1C-C-B-B-B** — `NEXT_ALLOWED / NOT_STARTED`.
    *Parent* phase. Strategy Validation Lab (deeper) & richer
    Cluster Exposure Control follow-up. Phase 11C.1C-C-B-B-B
    has **NOT** been renamed. The Paper Alpha Gate v0 is one
    slice under this parent, not the parent itself.
  - **Phase 11C.1C-C-B-B-B-A** — *this document*.
    `NEXT_ALLOWED / NOT_STARTED`. **First slice** under Phase
    11C.1C-C-B-B-B. Paper Alpha Gate v0. Paper / report-only.
    No trade authority. Reads
    `StrategyValidationDataset` /
    `StrategyValidationQualityGate` /
    `StrategyValidationReport` artefacts and emits a
    descriptive alpha-evidence verdict.
  - **Phase 12** — `FORBIDDEN`. Phase 1 safety lock unchanged.

## Why a separate child slice (and not B-B-B itself)?

The deeper Phase 11C.1C-C-B-B follow-up under the parent Phase
11C.1C-C-B-B-B is broad: richer cohort comparisons, extended
cluster heuristics, longer-window correlations,
dataset-driven retrospective audits, and an alpha-evidence
gate are *all* candidate slices. Bundling them into a single
PR would conflate independent design decisions, risk
overscope, and break the established pattern of small,
auditable child slices (Phase 11C.1C-C-A → Phase 11C.1C-C-B-A
→ Phase 11C.1C-C-B-B-A → Phase 11C.1C-C-B-B-B-A).

Phase 11C.1C-C-B-B-B-A therefore carves out **only** the
*Paper Alpha Gate v0* — the smallest auditable evidence-gate
on top of the Phase 11C.1C-C-B-B-A artefacts — leaving the
remaining deeper Lab follow-up work for later child slices
(B-B-B-B, B-B-B-C, …) under the same Phase 11C.1C-C-B-B-B
parent.

## What Paper Alpha Gate v0 is

Paper Alpha Gate v0 is a **paper-only / report-only
evidence-gate** that aggregates the existing Phase
11C.1C-C-B-B-A `StrategyValidationDataset` /
`StrategyValidationQualityGate` /
`StrategyValidationReport` artefacts (and, transitively, the
Phase 11C.1C-C-B-A samples and the Phase 11C.1C-C-A label
runtime outcomes) into a single descriptive verdict for human
review.

The verdict is one of:

  - `PASS` — the gate's alpha-evidence checks were all met on
    a trustworthy dataset.
  - `WARN` — the gate's alpha-evidence checks were partially
    met or the dataset is borderline; human review required.
  - `FAIL` — the gate's alpha-evidence checks were not met
    on a trustworthy dataset.
  - `INCONCLUSIVE` — the dataset was too thin / too in-flight
    / failed the prior `validation_quality_gate_status` to
    support an alpha-evidence verdict.

The verdict is a **descriptive label only**. It is recorded
into the daily Markdown report and into a typed event so a
human reviewer can audit the alpha evidence *post-hoc*. **No
runtime module reads the verdict to drive execution. The Risk
Engine remains the single trade-decision gate.**

## What Paper Alpha Gate v0 is NOT

Paper Alpha Gate v0 is **NOT**:

  - real / live trading;
  - AI Learning;
  - automatic parameter optimisation;
  - reinforcement learning;
  - the complete Strategy Validation Lab follow-up;
  - a strategy-quality / profitability oracle;
  - a strategy autonomous optimisation loop;
  - a position-sizing / leverage / stop-loss / target-price
    modifier;
  - a Risk Engine override / bypass;
  - an Execution FSM override / bypass;
  - a Phase Gate override / bypass;
  - a path into Phase 12;
  - a sample-trust gate (the Phase 11C.1C-C-B-B-A
    `validation_quality_gate_status` field is the existing
    sample-trust gate; the Paper Alpha Gate v0 *consumes*
    that gate's status as an input, it does not replace it);
  - a real-trade authority of any kind.

## Boundary (must hold from day one of the implementation PR)

| Invariant                                   | Required value                |
| ------------------------------------------- | ----------------------------- |
| `mode`                                      | `paper`                       |
| `live_trading`                              | `False`                       |
| `right_tail`                                | `False`                       |
| `llm`                                       | `False`                       |
| `exchange_live_orders`                      | `False`                       |
| `telegram_outbound_enabled`                 | `False`                       |
| `binance_private_api_enabled`               | `False`                       |
| `safety.forbid_*` (11 flags)                | `True` for every flag         |
| Binance API key / secret                    | refused at construction       |
| Signed endpoint                             | refused at allowlist check    |
| `listenKey` / user data stream              | refused                       |
| Private WebSocket / trading WS API          | refused                       |
| Routed-private endpoint (`/private`)        | refused                       |
| DeepSeek trade-decision authority           | NOT permitted                 |
| Real Telegram outbound                      | NOT permitted                 |
| Paper Alpha Gate v0 verdict                 | descriptive label only        |
|   (`PASS` / `WARN` / `FAIL` /               | (`PASS` / `WARN` / `FAIL` /   |
|   `INCONCLUSIVE`)                           | `INCONCLUSIVE`); MUST NEVER   |
|                                             | trigger a real trade          |
| Paper Alpha Gate v0 verdict                 | MUST NEVER modify position    |
|                                             | size, leverage, stop-loss,    |
|                                             | target price, Risk Engine     |
|                                             | state, or Execution FSM state |
| `validation_quality_gate_status`            | descriptive label only        |
|   (input to Paper Alpha Gate v0)            | (`pass` / `warn` / `fail`);   |
|                                             | MUST NEVER trigger a real     |
|                                             | trade                         |
| AI Learning                                 | NOT permitted                 |
| Automatic parameter optimisation            | NOT permitted                 |
| Reinforcement learning                      | NOT permitted                 |
| Risk Engine override / bypass               | NOT permitted                 |
| Execution FSM override / bypass             | NOT permitted                 |
| Complete Strategy Validation Lab follow-up  | NOT in Paper Alpha Gate v0    |
|                                             | scope                         |
| Phase 12 (live trading)                     | FORBIDDEN                     |

## Explicitly forbidden (inherited verbatim)

  - Real trading.
  - Live trading.
  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position /
    leverage / balance / order private WS variant.
  - Connecting to the routed-private endpoint
    `wss://fstream.binance.com/private` (or any `/ws-api` /
    `/ws-fapi` / `/ws-papi` / `/trading-api` /
    `/userDataStream` path-root variant).
  - Connecting to DeepSeek as a trade-decision authority.
  - Connecting to the real Telegram outbound HTTP transport.
  - Right-tail score in production scope.
  - Promoting the Paper Alpha Gate v0 verdict (or any other
    paper / virtual signal — `validation_quality_gate_status`,
    `STRATEGY_VALIDATION_DATASET_*` events, the seven
    `STRATEGY_VALIDATION_*` events from Phase 11C.1C-C-B-A,
    `strategy_mode`, `early_tail_score`, `mfe_pct`, `mae_pct`,
    `tail_label`, `MISSED_TAIL_DETECTED`,
    `FAKE_BREAKOUT_DETECTED`, validation cohort stats,
    `suggested_cluster_action`) to a real-trade authority.
  - Letting the Paper Alpha Gate v0 verdict modify position
    size, leverage, stop-loss, target price, the Risk Engine,
    or the Execution FSM.
  - AI deciding direction / position size / leverage /
    stop-loss / target / execution.
  - Automatic parameter optimisation that self-modifies the
    runtime configuration.
  - Reinforcement learning that drives trade decisions.
  - AI Learning that auto-decides trades.
  - Risk Engine override / bypass.
  - Execution FSM override / bypass.
  - Phase Gate override / bypass.
  - Issuing any real order.
  - Phase 12 / live trading kickoff.

## Acceptance gate (placeholder; populated by the implementation PR)

This docs-only kickoff intentionally does **not** define the
runtime contract, event names, schema versions, dataclasses,
or threshold defaults of Paper Alpha Gate v0. Those will be
authored alongside the implementation PR and reviewed against:

  - the Phase 1 safety lock;
  - the AMOS governance rails in
    `docs/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM.md`
    (Truth Layer / Reality Check / Anti-overfitting /
    Feedback Isolation / Limited Complexity);
  - the boundary table above (held end-to-end);
  - the explicitly-forbidden list above (held verbatim);
  - the requirement that the verdict is descriptive only and
    grants no trade authority;
  - the requirement that no module reads the verdict to drive
    execution, sizing, leverage, stops, targets, the Risk
    Engine, or the Execution FSM;
  - the requirement that Phase 12 stays `FORBIDDEN`.

The implementation PR's acceptance evidence will follow the
established pattern (brief-mandated tests + `tests/unit -k
phase11c_` baseline + full pytest baseline + dry-run smoke
and/or operator-VPS real public WS smoke as appropriate;
Phase 1 safety lock unchanged end-to-end). It is **out of
scope for this kickoff PR** to assert any test count, smoke
duration, or evidence transcript.

## What this kickoff PR does *not* do

  - It does **not** implement Paper Alpha Gate v0.
  - It does **not** add any new Python module under `app/`.
  - It does **not** add any new event type.
  - It does **not** modify any runtime behaviour.
  - It does **not** modify configuration schemas, defaults,
    or YAML.
  - It does **not** add or modify tests.
  - It does **not** flip any phase's acceptance state. Phase
    11C.1C-C-B-B-A remains `ACCEPTED`. Phase 11C.1C-C-B-B-B
    remains `NEXT_ALLOWED / NOT_STARTED`. Phase
    11C.1C-C-B-B-B-A is introduced at `NEXT_ALLOWED /
    NOT_STARTED`. Phase 12 remains `FORBIDDEN`.
  - It does **not** rename Phase 11C.1C-C-B-B-B. The parent
    phase keeps its existing definition: *Strategy Validation
    Lab (deeper) & richer Cluster Exposure Control
    follow-up*.
  - It does **not** authorise live trading, API keys, private
    endpoints, DeepSeek trade decisions, real Telegram
    outbound, AI Learning, automatic parameter optimisation,
    reinforcement learning, or Phase 12.

## Safety flags (Phase 1 lock unchanged)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

The Risk Engine remains the single trade-decision gate. The
Paper Alpha Gate v0 verdict, once implemented, will be a
*descriptive evidence label* read only by human reviewers and
by the daily Markdown report; it will **never** be read by an
execution path.
