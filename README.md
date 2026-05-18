# AMA-RT - Altcoin Momentum Agent (Right Tail Edition)

> **Phase status:** Phase 6 - Scanner / Confirmation / Manipulation.
> **Paper mode only.** Phase 6 adds four pure stateless classifiers
> on top of the Phase 4 `MarketDataBuffer` and the Phase 5
> `RegimeSnapshot`: `PreAnomalyScanner`, `AnomalyScanner`,
> `RealTradeConfirmation`, and `ManipulationDetector`. None of them
> trade. None of them open a socket. None of them call an LLM. The
> Risk Engine grew three optional Phase 6 hooks (M3 -> reject all,
> M2 -> reject ATTACK, T0/T1 -> reject ATTACK) but **adds no new
> rejection that weakens the Phase 1 safety lock**. This repository
> still does **not** trade real money, does **not** open any
> outbound network socket, does **not** import any exchange SDK
> (`ccxt`, `binance-connector`, `python-binance` are intentionally
> absent from `requirements.txt`), does **not** call any LLM, and
> does **not** read real API keys. The four write surfaces on
> `ExchangeClientBase` (`create_order`, `cancel_order`,
> `set_leverage`, `set_margin_mode`) continue to raise
> `SafeModeViolation` from the base class.

---

## What this repository is

This is the implementation of the production specification in
`docs/AMA_RT_V1_4_Production_Spec_Kiro.md`.

| Phase | Issue | Status | Branch / PR |
| --- | --- | --- | --- |
| Phase 1 - Safety Foundation | #1  | merged | `feature/phase-1-safety-foundation` (PR #11), `feature/phase-1-review-fixes` (PR #12) |
| Phase 2 - Event Sourcing and Database | #2  | merged | `feature/phase-2-event-sourcing-database` (PR #13) |
| Phase 3 - Exchange Gateway Read-Only | #3  | merged | `feature/phase-3-exchange-gateway-read-only` (PR #14) |
| Phase 4 - Market Data Buffer | #4  | merged | `feature/phase-4-market-data-buffer` (PR #15) |
| Phase 5 - Regime / Universe / Liquidity | #5  | merged | `feature/phase-5-regime-universe-liquidity` (PR #16) |
| Phase 6 - Scanner / Confirmation / Manipulation | #6  | this branch | `feature/phase-6-scanner-confirmation-manipulation` |
| Phase 7 - State Machine / Risk Engine | #7  | open | - |
| Phase 8 - Capital Flow / Profit Harvest / Rebase | #8  | open | - |
| Phase 9 - Execution FSM / Reconciliation | #9  | open | - |
| Phase 10 - LLM / Telegram / Replay / Reflection | #10 | open | - |

## Phase 6 deliverable

Phase 6 adds four pure stateless classifiers on top of the Phase 4
`MarketDataBuffer` and the Phase 5 `RegimeSnapshot`. They consume
already-collected metrics and produce typed decisions plus persisted
events. None of them trade. None of them open a socket. None of them
call an LLM. None of them touch a credential.

- **`app/scanner/` - Pre-Anomaly + Anomaly scanners** (Spec §17 / §18)
  - `PreAnomalyScanner.evaluate(PreAnomalyInput)` /
    `evaluate_snapshot(snapshot, ...)` returns a
    `PreAnomalyDecision` with `pre_anomaly_score` (0..100) and a
    typed `reason_tags: tuple[PreAnomalyReasonTag, ...]`. Six
    Spec §17.2 signals: volume base-expansion, spread compression,
    buy-pressure rising, OI soft-rise, funding-not-overheated,
    minor uptrend.
  - `AnomalyScanner.evaluate(AnomalyInput)` returns
    `AnomalyDecision` with `anomaly_score` (Spec §18.2 weighted
    sum) and `reason_tags: tuple[AnomalyReasonTag, ...]`. Eight
    Spec §18.1 signals: `OI_SPIKE`, `CVD_SPIKE`, `VOLUME_SPIKE`,
    `ATR_EXPANSION`, `FUNDING_EXTREME`, `LIQUIDATION_SPIKE`,
    `SWEEP`, `MULTI_TIMEFRAME_BREAKOUT`. Spec §18.2 weights live
    in `AnomalyConfig` (`weight_oi=0.25`, `weight_cvd=0.25`,
    `weight_volume=0.20`, `weight_atr=0.10`, `weight_funding=0.10`,
    `weight_liquidation=0.10`) and sum to 1.0; sweep + multi-tf-
    breakout add bonuses on top.
  - Emits one ``PRE_ANOMALY_DETECTED`` and one
    ``ANOMALY_DETECTED`` event per evaluation.

- **`app/confirmation/` - Real Trade Confirmation** (Spec §20)
  - `RealTradeConfirmation.evaluate(ConfirmationInput)` returns
    `ConfirmationDecision` mapping fired-signal count to
    :class:`TradeConfirmationLevel` (T0..T4):
    `0=T0, 1=T1, 2=T2, 3=T3, 4+=T4`. Five Spec §20.4 signals:
    CVD-price agreement, breakout hold over N bars, large-trade
    follow-through, trade-efficiency above mean, volume-up-price-
    move.
  - Emits one ``TRADE_CONFIRMED`` event per evaluation.

- **`app/manipulation/` - Manipulation Detector** (Spec §21)
  - `ManipulationDetector.evaluate(ManipulationInput)` returns
    `ManipulationDecision` mapping fired-signal count to
    :class:`ManipulationLevel` (M0..M3):
    `0=M0, 1=M1, 2=M2, 3+=M3`. Eight Spec §21.2 signals:
    CVD up + price flat (CVD-price divergence), volume up +
    price no move, OI up + price flat, funding hot + price
    weak, upper-wick growth, buy-pressure-no-push, book-wall
    flicker (caller-supplied count), narrative-after-pump.
  - Emits one ``MANIPULATION_DETECTED`` event per evaluation.

### Phase 6 hard rules (per Issue #6)

The Risk Engine (`app/risk/engine.py`) enforces these in
`RiskEngine.evaluate`:

1. **`manipulation_level == M3` -> reject every NEW opening.**
   Reason `manipulation_m3`. Hard wall on new openings regardless of
   `attack_intent`. Spec §21.3 "M3 禁止交易".

   **Important - Phase 6 only ships the new-opening protection
   semantic.** Phase 7 (full Risk Engine + State Machine) and Phase 9
   (Execution FSM + Reconciliation) MUST preserve protective-exit
   and reduce-only closing flows under M3:

   - `LOCK_PROFIT`, `FORCED_EXIT`, `DISTRIBUTION_ALERT` exit paths
     must remain allowed - refusing them under M3 would trap a live
     position when manipulation is detected (P0 incident).
   - `kill_all` and reduce-only closing orders must remain allowed
     regardless of `manipulation_level` because they shrink
     exposure, never grow it.
   - Reconciliation must remain allowed to read / re-attach
     stop-loss state under M3.

   Phase 7 will add an explicit `is_protective_exit=True` (or
   equivalent) flag on `RiskRequest` so the M3 branch can
   distinguish "open" from "close / reduce / protect". Phase 6 does
   NOT ship that flag because Phase 6 has no exit path of its own;
   every Phase 6 caller is a non-attack self-check or a
   forward-looking opening adjudication. The caveat is pinned next
   to the inline M3 branch in `app/risk/engine.py` and asserted by
   `tests/unit/test_phase6_non_generation_invariant.py`.

2. **`manipulation_level == M2` AND `attack_intent=True` -> reject.**
   Reason `manipulation_m2_attack`. SCOUT / OBSERVE actions remain
   allowed. Spec §21.3 "M2 禁止进攻".
3. **`trade_confirmation_level in (T0, T1)` AND
   `attack_intent=True` -> reject.** Reason
   `trade_confirmation_too_low_for_attack`. SCOUT / OBSERVE
   remain allowed. Issue #6 "T0/T1 不允许进攻".
4. **`right_tail_amplify=True` always implies `attack_intent`** via
   `RiskRequest.effective_attack_intent`. Phase 1's
   `right_tail_disabled` rejection still fires regardless because
   `right_tail_enabled` is locked False through the limited-live
   phase.
5. **All four classifier outputs are persisted as events.** One
   event per evaluation with the full reason-tag list, so
   Reflection (Issue #10) and Replay can reconstruct the decision
   from `events.db` alone.

The Phase 1 hard rejections (`live_trading_disabled`,
`right_tail_disabled`, `stop_unconfirmed`, `unknown_position`,
`trading_mode_inconsistent`) are unchanged. The Phase 6 rules are
**additive**.

### Phase 6 classifier contract: indicators / levels only, NEVER trade approval

A common failure mode of momentum systems is silently treating a
high anomaly score or a strong confirmation tier as authorisation
to open a position. **Phase 6 explicitly forbids this.** The four
classifiers in this PR are passive scorers / level mappers:

- **`pre_anomaly_score` and `anomaly_score` are CANDIDATE and
  ANOMALY INDICATORS only - NOT entry signals.** A high score does
  NOT authorise opening a position. `PreAnomalyScanner` and
  `AnomalyScanner` return :class:`PreAnomalyDecision` /
  :class:`AnomalyDecision` value objects (score + reason_tags +
  notes) and emit one event each. They never construct an
  :class:`app.core.models.TradeDecision`, never enqueue an order,
  never mutate a position.
- **T3 / T4 is a trade-confirmation LEVEL only - NOT a trade
  approval.** `RealTradeConfirmation` returns a
  :class:`ConfirmationDecision` (level + reason_tags + notes).
  Whether a real opening is permitted is the conjunction of:
  - the Phase 5 regime gate (`RegimeSnapshot.risk_permission`);
  - the Phase 5 universe / liquidity decisions
    (`UniverseDecision.eligible`, `LiquidityDecision.passed`,
    `can_exit_position(...).feasible`);
  - the Phase 6 confirmation tier (T2+ for ATTACK candidates);
  - the Phase 6 manipulation tier (M0 / M1 for ATTACK candidates);
  - the Phase 7 No-Trade Gate + Risk Engine final adjudication; and
  - the Phase 9 Execution FSM transition.

  A T4 reading on its own authorises nothing. Phase 7's Risk
  Engine / State Machine / No-Trade Gate, working with Liquidity,
  Manipulation, and Regime, makes the actual opening decision.
- **M-tier is a manipulation LEVEL only - NOT a trade approval.**
  Same shape as T-tier above. The detector returns a
  :class:`ManipulationDecision` (level + reason_tags + notes).

The non-generation invariant is pinned by
`tests/unit/test_phase6_non_generation_invariant.py`:

- The four decision value-objects expose only score / level +
  reason_tags + notes + timestamp - no `direction`, `entry_zone`,
  `qty`, `stop_price`, `position_id`, `order_id`,
  `take_profit_plan` (per-class field-set assertions).
- A live evaluation of each classifier returns a
  `<X>Decision`, NEVER a :class:`TradeDecision`
  (`isinstance` assertions).
- No source file under `app/scanner/`, `app/confirmation/`,
  `app/manipulation/` imports `TradeDecision`, instantiates one,
  or imports any `app.execution.order_manager` /
  `app.execution.stop_manager` / `app.positions.*` /
  `app.reconciliation` module (source-tree scan).
- The package and class docstrings carry the "indicators only" /
  "level only" / "NOT an entry signal" / "NOT a trade approval"
  wording so a future Phase 7 PR cannot misread the boundary
  (docstring assertions).

### Phase 6 boundary (declared explicitly to avoid drift)

1. Pre-Anomaly / Anomaly / Real-Trade Confirmation / Manipulation
   ONLY. **No Strategy Engine, no State Machine, no LLM, no
   Capital Flow, no Execution FSM, no Reconciliation.** Those
   land with Issue #7 / #8 / #9 / #10.
2. Reads only. **No write surface added.** The four
   `SafeModeViolation` refusals on `ExchangeClientBase` are
   unchanged.
3. **No LLM.** No source file under `app/scanner/`,
   `app/confirmation/`, `app/manipulation/` imports `openai`,
   `anthropic`, `deepseek`, or any other LLM client. Issue #6
   forbids using an LLM to decide direction or to bypass the
   Risk Engine.
4. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
   `BinanceClient.get_*` continues to raise `NotImplementedError`.
5. **No API key.** No source file under the three new packages
   reads `os.environ` for a credential, accepts an `api_key`
   keyword argument, or persists a key (an AST scan in
   `tests/unit/test_phase6_no_network.py` enforces this).
6. **No auto-connect.** The classifiers do not own a
   `MarketDataBuffer`, do not own an `ExchangeClientBase`, and
   never instantiate one for themselves
   (`tests/unit/test_phase6_boundary.py` enforces this).
7. **Tests do not depend on real network.**
   `test_phase6_no_network.py` enforces this at the source-tree
   level and cooperates with the existing
   `test_phase3_no_network.py`, `test_phase4_no_network.py`, and
   `test_phase5_no_network.py`.

### Phase 6 boot self-check in `python -m app.main`

After the Phase 5 Liquidity loop, the entrypoint:

- Instantiates `PreAnomalyScanner`, `AnomalyScanner`,
  `RealTradeConfirmation`, `ManipulationDetector` and runs each
  classifier once per mock symbol. With three mock symbols this
  produces 12 new events:
  - 3 ``PRE_ANOMALY_DETECTED``
  - 3 ``ANOMALY_DETECTED``
  - 3 ``TRADE_CONFIRMED``
  - 3 ``MANIPULATION_DETECTED``
- Tracks the worst-observed manipulation + confirmation level and
  feeds them into the bootstrap Risk Engine self-check with
  `attack_intent=False` so the bootstrap stays approved. The
  resulting ``RISK_APPROVED`` audit row exercises the new payload
  fields end-to-end.
- Banner extended with four new fields: `pre_anomaly_events`,
  `anomaly_events`, `trade_confirmed_events`,
  `manipulation_events`.

Sample boot output:

```
[AMA-RT] Phase 6 - Scanner Confirmation Manipulation v1.4.0a6 \
  mode=paper live_trading=False right_tail=False \
  llm=False exchange_live_orders=False \
  databases=5 events_count=31 capital_events=1 \
  exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
  market_data=3/0 market_snapshots=3 data_unreliable=1 \
  regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
  universe=0/3 universe_events=3 liquidity_events=6 \
  pre_anomaly_events=3 anomaly_events=3 trade_confirmed_events=3 \
  manipulation_events=3 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

### Phase 6 event-emission throttle

Each of `PreAnomalyConfig`, `AnomalyConfig`,
`ConfirmationConfig`, `ManipulationConfig` exposes
`event_emit_enabled: bool` (default `True`). Every classifier
accepts a per-call `emit_event: bool | None` on its `evaluate`
and `evaluate_snapshot` entry points:

```text
emit_event=True   -> always emit (per-call override)
emit_event=False  -> always skip (per-call override)
emit_event=None   -> follow config.event_emit_enabled (default)
```

Each classifier exposes two counters:
`<event>_events_emitted` and `<event>_events_skipped`. Issue #7's
full Top-200 scanner can flip the config flag off and confirm via
the counter that the event is being skipped, without losing the
underlying classifier output. Mirrors the Phase 5 PR #16
review-fix shape (`UniverseConfig.event_emit_enabled`,
`LiquidityConfig.event_emit_enabled`).

## Phase 5 deliverable

Phase 5 introduces three pure classifiers that consume the Phase 4
:class:`MarketDataBuffer` and the Phase 3 :class:`ExchangeClientBase`
and produce typed decisions plus persisted events. None of them
trade. None of them open a socket. None of them touch a credential.

- **`app/regime/` - Regime Engine** (Spec §15)
  - `RegimeEngine.evaluate(request=...)` /
    `evaluate_from_buffer(buffer, btc_symbol=, alt_symbols=)`.
  - Output schema (`RegimeSnapshot`): `market_regime`, `btc_trend`,
    `btc_volatility`, `alt_liquidity`, `risk_permission`,
    `reason_tags`. Spec §15.1.
  - Five regimes: `MEME_RISK_ON`, `SECTOR_ROTATION`,
    `BTC_ABSORPTION`, `ALT_RISK_OFF`, `SYSTEMIC_RISK`. Spec §15.2.
  - `REGIME_TO_RISK_PERMISSION` (Spec §15.3) is the source-of-truth
    map every later phase consults:

    | Regime | Risk permission |
    |---|---|
    | `MEME_RISK_ON`     | `ALLOW_ATTACK` |
    | `SECTOR_ROTATION`  | `ALLOW_ATTACK` |
    | `BTC_ABSORPTION`   | `OBSERVE_ONLY` |
    | `ALT_RISK_OFF`     | `ALLOW_SCOUT`  |
    | `SYSTEMIC_RISK`    | `BLOCK_ALL`    |

  - Emits one ``REGIME_UPDATED`` event per evaluation.

- **`app/universe/` - Universe Filter** (Spec §16)
  - `UniverseFilter.evaluate(UniverseInput)` /
    `evaluate_snapshot(snapshot, symbol_meta=, regime=, ...)`.
  - 9 reject conditions (typed enum values, full reason list
    returned):
    `REGIME_BLOCKED`, `DATA_DEGRADED`, `ABNORMAL_DATA_FLAG`,
    `DATA_RELIABILITY_TOO_LOW`, `CONTRACT_NOT_TRADING`,
    `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`, `TRADE_DISCONTINUOUS`,
    `VOLUME_BELOW_MINIMUM`.
  - Emits one ``UNIVERSE_FILTERED`` event per evaluated symbol,
    eligible or rejected.

- **`app/liquidity/` - Liquidity Filter + can_exit_position**
  (Spec §19)
  - `LiquidityFilter.evaluate(LiquidityInput)` returns a
    `LiquidityDecision` with `spread_score`, `depth_score`,
    `estimated_slippage_pct`, `estimated_exit_seconds`, an
    `ExitPlan`, and the full reject-reason list.
  - **`LiquidityFilter.can_exit_position(symbol, qty,
    max_slippage_pct, max_seconds, ...)`** (Spec §19.2 - mandatory
    function): returns an `ExitPlan` describing whether the
    position can be flattened within `max_seconds` at <=
    `max_slippage_pct` given the current book and rolling
    5-minute throughput. `feasible=False` is the binary the Risk
    Engine (Issue #7) will consult through the No-Trade Gate.
  - Module-level `can_exit_position(...)` free function so
    Issue #7 can call it without instantiating a filter.
  - 8 reject reasons: `REGIME_BLOCKED`, `DATA_DEGRADED`,
    `BOOK_MISSING`, `SPREAD_TOO_WIDE`, `DEPTH_INSUFFICIENT`,
    `SLIPPAGE_TOO_HIGH`, `NO_EXIT_CHANNEL`, `EXIT_TOO_SLOW`.
  - Emits one ``LIQUIDITY_CHECKED`` event per call, tagged
    `check="evaluate"` or `check="can_exit_position"`.
  - Pure helpers in `app/liquidity/slippage.py`:
    `estimate_book_walk(book, qty=, side=)`,
    `estimated_slippage_pct(book, qty=, side=)`,
    `walk_book_for_quote_notional(book, quote_notional=, side=)`.
    All stateless, no IO, no events.

### Phase 5 hard rules (per Issue #5)

1. **SYSTEMIC_RISK -> reject every new opening.** The regime maps to
   `RiskPermission.BLOCK_ALL`, which is in the
   `blocking_risk_permissions` set of both Universe and Liquidity
   configs.
2. **Insufficient liquidity -> reject with reasons.** Every threshold
   violation produces a typed reject-reason enum value.
3. **No exit channel -> reject the attack candidate.** Book walk
   exhaustion maps to `NO_EXIT_CHANNEL`.
4. **Data degraded -> reject / downgrade.** `is_degraded(symbol)`
   flows into both filters as `is_data_degraded=True`.
5. **Every reject carries `reject_reasons`.** Tuples of typed enum
   values, never free-form strings (free-form `notes` are a
   secondary advisory channel).
6. **Every reject is persisted as one event** through
   :class:`EventRepository`.

### Phase 5 boundary (declared explicitly to avoid drift)

1. Regime / Universe / Liquidity ONLY. No Scanner, no Confirmation,
   no Manipulation, no Strategy, no State Machine.
2. Reads only. **No write surface added.** The four
   `SafeModeViolation` refusals on `ExchangeClientBase` are
   unchanged.
3. **No real Binance WebSocket and no real REST.** The boot path
   continues to drive the deterministic `MockExchangeClient`.
4. **No API key.** No file under `app/regime/`, `app/universe/`,
   `app/liquidity/` reads `os.environ` for a credential, accepts an
   `api_key` keyword argument, or persists a key.
5. **No auto-connect.** The three engines do not own a
   `MarketDataBuffer`, do not own an `ExchangeClientBase`, and
   never instantiate one for themselves.
6. **Tests do not depend on real network.**
   `test_phase5_no_network.py` enforces this at the source-tree
   level and cooperates with the existing
   `test_phase3_no_network.py` and `test_phase4_no_network.py`.

### Phase 5 boot self-check in `python -m app.main`

- One `RegimeEngine` is instantiated and evaluated against the
  Phase 4 buffer + the deterministic mock seed. One
  ``REGIME_UPDATED`` event is written.
- One `UniverseFilter` evaluation is run per symbol the mock
  exposes. One ``UNIVERSE_FILTERED`` event is written per call. The
  default mock book is intentionally shallow, so the boot drill
  exercises the rejection path end-to-end.
- One `LiquidityFilter.evaluate(...)` call is made per symbol, and
  one `can_exit_position(...)` call. Two ``LIQUIDITY_CHECKED``
  events per symbol, tagged `check="evaluate"` and
  `check="can_exit_position"`.
- A `regime_gate` health probe is registered. It reports
  `DEGRADED` only when `risk_permission=BLOCK_ALL`.
- The Phase 4 + Phase 3 self-checks (read-only assertion,
  market-data-buffer lifecycle) are unchanged.

Sample boot output:

```
[AMA-RT] Phase 5 - Regime Universe Liquidity v1.4.0a5 mode=paper \
  live_trading=False right_tail=False llm=False exchange_live_orders=False \
  databases=5 events_count=19 capital_events=1 \
  exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
  market_data=3/0 market_snapshots=3 data_unreliable=1 \
  regime=ALT_RISK_OFF/ALLOW_SCOUT regime_events=1 \
  universe=0/3 universe_events=3 liquidity_events=6 \
  risk_decision=True/paper_only_skeleton_approval health=ok
```

### Phase 5 review-fix observability (PR #16 review feedback)

Four follow-up clarifications were added on top of the original
Phase 5 PR. Documentation + observability only - no behaviour
change, no loosened safety guarantee.

1. **`RiskPermission` is a regime-cycle gate, NOT a trade
   approval.** The `RiskPermission` enum docstring now spells out
   the eight-step conjunctive ladder a real opening has to clear
   in Phase 7+: regime gate → universe → liquidity → can_exit →
   pre-anomaly / anomaly → real-trade confirmation T2+ → no-
   manipulation → Risk Engine final approval → Execution FSM
   transition. `ALLOW_ATTACK` is "regime is risk-on", nothing
   more.

2. **`ALT_RISK_OFF -> ALLOW_SCOUT` permits OBSERVE or a tiny
   SCOUT candidate only.** Issue #7 MUST further restrict this
   path: NO ATTACK, NO RIGHT_TAIL_AMPLIFY, SCOUT size capped at
   the per-trade scout budget. `right_tail_enabled` remains
   locked False through the limited-live phase regardless of
   what the regime gate says.

3. **`can_exit_position` throughput estimate is an UPPER BOUND.**
   The `volume_5m / 300s` fallback assumes the next 5 minutes
   will print at the same pace as the previous 5 minutes, that
   our outflow does not crowd its own exit price, and that ATR /
   OI do not expand into the exit window. None of these hold in
   a thinning or panicking tape. The 5x `min_depth_multiplier`
   cushion is what makes Phase 5 safe under normal regimes; the
   throughput value itself is permissive. **Issue #7's Risk
   Engine MUST apply a conservative discount on top** before
   sizing an attack candidate (recommended directions: ATR-scaled
   divisor, fraction-of-average cap, post-discount feasibility
   re-check). Degraded data already maps to
   `LiquidityRejectReason.DATA_DEGRADED` and forces
   `feasible=False`; callers MUST pass
   `MarketDataBuffer.is_degraded(symbol)` through and never
   invert the result.

4. **Construct-time event throttle for high-frequency scans.**
   Phase 5 emits one `UNIVERSE_FILTERED` per evaluated symbol
   and two `LIQUIDITY_CHECKED` per evaluated symbol (one
   `check="evaluate"` + one `check="can_exit_position"`). At
   Top-200 scan rate that is 600 events per tick - too noisy
   for events.db. Two new construct-time flags now mirror the
   Phase 4 PR #15 review-fix shape:

   - `UniverseConfig.event_emit_enabled` (default `True`)
   - `LiquidityConfig.event_emit_enabled` (default `True`)

   Issue #6's full Top-200 scanner can flip these to `False` to
   stop bloating events.db while still receiving every
   `UniverseDecision` / `LiquidityDecision` / `ExitPlan` return
   value. Per-call `emit_event=True` overrides remain available
   for monitoring / on-demand audit-trail entries; per-call
   `emit_event=False` overrides remain available for tests. The
   resolution rule:

   ```text
   emit_event=True   -> always emit (per-call override)
   emit_event=False  -> always skip (per-call override)
   emit_event=None   -> follow config.event_emit_enabled
   ```

   Two new counters confirm the throttle is doing its job:

   - `UniverseFilter.universe_filtered_events_skipped`
   - `LiquidityFilter.liquidity_checked_events_skipped`

   Both increment whenever a decision was suppressed by either
   the per-call override or the config flag.

   Pinned by `tests/unit/test_phase5_review_fixes.py`.

## Phase 4 deliverable

Phase 4 introduces the `app/market_data/` package - the in-process
**Market Data Buffer** that every later phase will read from. The
package never imports an exchange SDK, never opens an outbound
socket, never reads a credential, never adds a write surface.

- **`MarketDataBuffer`** (`app/market_data/buffer.py`)
  - Per-symbol rolling trade windows for **1m / 5m / 15m**.
  - 1m + 5m candle builders fed by every ingested trade. Late trades
    (those that arrive after their bucket has already closed) are
    *dropped* (Spec §14.2 forbids silent rewrites). Multi-minute
    gaps between trades are filled with **flat synthetic bars** so
    ATR sees no missing slots.
  - Latest order book per symbol (with reliability tier preserved).
  - Latest / previous funding rate and open interest.
  - Bounded liquidation history.
  - **`is_degraded(symbol)` and `degraded_reasons(symbol)`** for the
    future No-Trade Gate (Issue #7) and Reconciliation loop
    (Issue #9). Spec §14.2 + §31.
  - **`snapshot(symbol)`** returns a Spec §11.1 `MarketSnapshot` with
    `cvd_1m`, `cvd_5m`, `atr_1m`, `atr_5m`, `volume_1m`,
    `volume_5m`, latest funding and OI. Emits a `MARKET_SNAPSHOT`
    event when an `EventRepository` is wired in.
  - **REST vs WS conflict detection** (Spec §14.2): a tier mismatch
    on incoming order books emits a `DATA_UNRELIABLE` event tagged
    `MarketDataDegradedReason.REST_WS_CONFLICT` and never silently
    overwrites strong-tier data with weak-tier data.
  - **`on_websocket_disconnect` / `on_websocket_reconnect`** drive the
    `EXCHANGE_DISCONNECTED` reason in and out of the symbol view and
    write a batched `DATA_UNRELIABLE` event with the full symbol
    list (Issue #4 acceptance criterion 4).
  - **Exchange health propagation**: an `ExchangeClientBase` whose
    `health.state` is `DISCONNECTED` / `DEGRADED` / `UNINITIALISED`
    automatically maps to the corresponding degraded reason on
    every symbol view. The buffer NEVER reads `now_ms()` to anchor
    staleness - it uses the latest observed timestamp across all
    surfaces, so the buffer is fully deterministic under replay.

- **Helpers**
  - `compute_cvd(trades)` - signed taker volume sum (positive on buy
    aggression, negative on sell aggression). Honours the Binance
    `is_buyer_maker=True` convention; falls back to
    `RecentTrade.side` when the flag is unset (mock fixtures).
  - `compute_atr(bars, window=14)` - SMA-of-True-Range over closed
    bars. Returns `None` for fewer than two closed bars.
  - `CandleBuilder` - streaming OHLCV with buy / sell taker volume
    split.
  - `OpenInterestSnapshotState`, `FundingSnapshotState` - latest /
    previous snapshot with out-of-order rejection.
  - `LiquidationFeedState` - bounded deque per symbol.

- **Phase 4 hard boundary** (declared explicitly so the next PR
  cannot drift):

  1. Market Data Buffer ONLY. No Regime / Universe / Liquidity
     engine, no Scanner, no Confirmation, no Manipulation Detector.
  2. The buffer is fed by `MockExchangeClient` / fixture data **by
     default**. The boot path uses the deterministic mock; tests use
     deterministic fixtures.
  3. **No real Binance WebSocket and no real REST.** `BinanceClient`
     continues to raise `NotImplementedError` for every read method.
  4. **No API key.** `BinanceClient.__init__` still refuses any
     credential. `MarketDataBuffer.__init__` exposes no `api_key`
     parameter.
  5. **No write surface.** The four `SafeModeViolation` refusals on
     `ExchangeClientBase` are unchanged.
  6. **No auto-connect.** `MarketDataBuffer` opens no socket; it
     only receives data via `ingest_*` calls or via
     `refresh_from_exchange` against a deterministic
     `MockExchangeClient`. **The
     `MarketDataBuffer.refresh_from_exchange` docstring restates this
     boundary verbatim and `test_market_data_buffer_review_fixes.py
     ::test_refresh_from_exchange_docstring_declares_phase4_boundary`
     pins it.**
  7. **Tests do not depend on real network**
     (`test_phase3_no_network.py`, `test_phase4_no_network.py`).
  8. **`BinanceClient.get_account_snapshot` remains mock-only /
     skeleton-only in both Phase 3 and Phase 4.** Real account
     snapshots require an authenticated REST call and an API key,
     forbidden until the limited-live phase.

- **Phase 4 review-fix observability** (PR #15 review)

  - `MarketDataBufferConfig.market_snapshot_event_emit_enabled` (default
    `True`) is the construct-time throttle for `MARKET_SNAPSHOT`
    events. Phase 5+ high-frequency consumers (anomaly scanner, regime
    engine) can flip it to `False` to stop bloating `events.db` while
    still receiving every `MarketSnapshot` return value. Per-call
    `emit_event=True` / `emit_event=False` overrides the config.
  - `MarketDataBuffer.late_trades_dropped_total` (also exposed via
    `BufferStats.late_trades_dropped_total`) sums the
    `CandleBuilder.dropped_late_trades` counter across every tracked
    symbol. A non-zero value is a leading indicator of an out-of-order
    tape (mis-ordered REST replay, inverted aggTrade delivery,
    clock-skew on the producer) and Issue #5 / #6 monitoring will
    alert on it.

- **Phase 4 boot self-check** in `python -m app.main`
  - Constructs a deterministic in-process boot tape via
    `_build_phase4_boot_seed()` so the buffer's staleness gate sees a
    fresh window.
  - Tracks every symbol the mock exposes, runs
    `refresh_from_exchange` on each, and produces one
    `MARKET_SNAPSHOT` per symbol.
  - Drives one WS disconnect + reconnect probe through the buffer so
    the audit trail shows one batched `DATA_UNRELIABLE` event with
    `trigger=websocket_disconnect`.
  - Registers a `market_data_buffer` health probe.
  - Banner extended with `market_data=<tracked>/<degraded>`,
    `market_snapshots=<count>`, `data_unreliable=<count>`.

  Sample boot output:

  ```
  [AMA-RT] Phase 4 - Market Data Buffer v1.4.0a4 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=9 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

## Phase 3 deliverable

Phase 3 introduces the `app/exchanges/` package - the **read-only**
abstraction every later phase will sit on top of. Specifically:

- **`ExchangeClientBase` abstract class** (`app/exchanges/base.py`)
  - 6 abstract read-only methods every concrete client must implement:
    `get_symbols`, `get_orderbook`, `get_recent_trades`,
    `get_funding_rate`, `get_open_interest`, `get_account_snapshot`.
  - 4 **concrete** write surfaces (`create_order`, `cancel_order`,
    `set_leverage`, `set_margin_mode`) that **always** raise
    `SafeModeViolation`. Subclasses cannot accidentally overwrite the
    refusal - they would have to delete the inherited method on
    purpose, and the test suite asserts that they have not.
  - `ExchangeHealth` value-object with state transitions (
    `UNINITIALISED -> CONNECTED -> DEGRADED / RECONNECTING /
    DISCONNECTED`), counters and an `is_data_trustworthy()` predicate.
  - `WebSocketManager` skeleton (`connect / disconnect / subscribe /
    unsubscribe`) that emits a `DATA_UNRELIABLE` event with the
    pending subscription set on every drop. **No real socket is
    opened in Phase 3.**
  - Health transitions emit `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `EXCHANGE_DEGRADED` events through
    `EventRepository` so the Phase 2 substrate can replay the gateway
    lifecycle.
  - `_require_trustworthy(surface=...)` helper that refuses tier-A
    reads with `ExchangeConnectionError` whenever the link is not
    `CONNECTED` (Spec §14.2 + §31).
  - `reliability_tiers` static map that documents the default
    `DataReliability` tier each surface returns (Spec §13.3).

- **`BinanceClient` skeleton** (`app/exchanges/binance.py`)
  - Real Binance USDT-M perpetual implementation lands later. Phase 3
    ships the class so future phases have a stable target to extend.
  - All 6 read methods raise `NotImplementedError` and the message of
    each spells out the Phase 4 constraints (see *Phase 4 constraints*
    below). `get_account_snapshot` raises a stronger message: it must
    remain mock-only / skeleton-only in **both** Phase 3 and Phase 4
    because a real account snapshot needs an authenticated REST call
    and an API key, neither of which is allowed before the
    limited-live phase.
  - All 4 write methods inherit the base-class `SafeModeViolation`
    refusal.
  - The constructor **refuses** if any `api_key` / `api_secret` is
    supplied (Spec §37 anti-leak rule). Phase 3 must not hold a real
    key in process memory.
  - The module imports no exchange SDK and no outbound network
    library - asserted by `tests/unit/test_phase3_no_network.py`.

- **`MockExchangeClient`** (`app/exchanges/mock.py`)
  - Deterministic in-memory implementation used by the entrypoint and
    the test suite. **No network**.
  - Optional `MockExchangeSeed` lets tests inject fully predictable
    symbol lists, order books, tapes, funding, OI, and account
    snapshots.
  - `simulate_disconnect` / `simulate_reconnect` /
    `simulate_degraded` test hooks drive the Phase 4+ No-Trade Gate
    paths.
  - Tier-A surfaces (`get_orderbook`, `get_recent_trades`) refuse when
    not `CONNECTED`; tier-B REST surfaces (`get_symbols`,
    `get_account_snapshot`) remain usable when `DEGRADED` per Spec
    §13.3. A REST-fallback book passed via `MockExchangeSeed` is
    preserved as tier B - the mock does not silently upgrade it.

### Reliability tier contract (Spec §13.3)

Locked by `app/exchanges/base.ExchangeClientBase.reliability_tiers`
and asserted by `tests/unit/test_exchange_base.py
::test_reliability_tiers_contract`:

| Surface                | Default tier | Source                              |
| ---------------------- | ------------ | ----------------------------------- |
| `get_recent_trades`    | A            | WS aggTrade / trade stream          |
| `get_orderbook`        | A            | WS depth-diff maintained book       |
| `get_funding_rate`     | B            | REST                                |
| `get_open_interest`    | B            | REST                                |
| `get_symbols`          | B            | REST exchangeInfo                   |
| `get_account_snapshot` | B            | mock-only / skeleton-only in Phase 3+4 |

Adapters that fall back to a tier-B REST orderbook snapshot when the WS
link is degraded must tag *that specific response* with
`DataReliability.B` on the model. The default mapping above documents
the canonical, healthy-link tier - not the worst case.

### Phase 4 constraints (declared up-front so the next PR cannot drift)

Phase 4 (Issue #4 - Market Data Buffer) **must**:

1. Drive the Market Data Buffer from `MockExchangeClient` / fixture
   data **by default**.
2. Treat any real public read-only WS / REST adapter as **opt-in**
   (off by default) - never auto-connect to the real exchange.
3. Require **no API key**, accept **no credentials**, expose **no
   write surface**.
4. Keep `get_account_snapshot` as a skeleton on `BinanceClient`. A
   real account snapshot needs an authenticated REST call; that is
   forbidden until the limited-live phase. The only working
   implementation in Phase 3 and Phase 4 is
   `MockExchangeClient.get_account_snapshot`.
5. Inherit every Phase 1 / Phase 3 safety guarantee unchanged.

Each `BinanceClient` read method raises a `NotImplementedError` whose
message restates points 1-3 verbatim, so any traceback reminds the
caller what the next-phase contract is. `get_account_snapshot`
additionally restates point 4.

- **Phase 3 boot self-check** in `python -m app.main`
  - The entrypoint instantiates `MockExchangeClient`, runs
    `assert_read_only()`, **probes every banned write surface** and
    refuses to start unless each one raises `SafeModeViolation`.
  - One `EXCHANGE_CONNECTED` and (on shutdown) one
    `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE` event are written so
    replay tests can confirm the lifecycle.
  - The status banner now reports
    `exchange=<name>/<state> exchange_symbols=N exchange_connected_events=1`.
  - The Phase 1 safety lock and `_assert_phase1_safety()` boot check
    remain unchanged. Phase 3 adds `_assert_phase3_read_only()` *on
    top* of them.

- **New core vocabulary**
  - `ExchangeConnectionState` enum (`UNINITIALISED / CONNECTED /
    DEGRADED / RECONNECTING / DISCONNECTED`) with an
    `is_trustworthy` predicate.
  - `DataReliability.is_at_least()` helper so every later module
    compares tiers consistently.
  - New `EventType` values: `EXCHANGE_CONNECTED`,
    `EXCHANGE_DISCONNECTED`, `EXCHANGE_DEGRADED`. `DATA_UNRELIABLE`
    was already declared in Phase 1.
  - New typed errors: `SafeModeViolation` (subclass of
    `SafetyViolation`), `ExchangeError`, `ExchangeConnectionError`.

## Default safety guarantees (unchanged from Phase 1)

Settings are loaded from `app/config/defaults.yaml` and validated by
`app/config/schema.py`. Regardless of YAML or environment-variable input,
`app/config/settings.py` applies a Phase 1 safety lock that forces:

| Flag                             | Value     |
| -------------------------------- | --------- |
| `trading_mode`                   | `paper`   |
| `live_trading_enabled`           | `False`   |
| `right_tail_enabled`             | `False`   |
| `llm_enabled`                    | `False`   |
| `exchange_live_order_enabled`    | `False`   |

`app/main.py` re-asserts these flags at boot and refuses to start if any
of them is wrong (`SafetyViolation`). Phase 3 does **not** loosen any
of these. Phase 3 adds an *additional* runtime guard,
`_assert_phase3_read_only()`, that probes every banned write surface
and refuses to boot unless each one raises `SafeModeViolation`.

## Repository layout

```
app/
  config/         settings + YAML configs (defaults / risk / strategy)
  core/           enums, events, models, clock, errors, constants
                  (Phase 3: ExchangeConnectionState enum, EXCHANGE_*
                   event types, SafeModeViolation / ExchangeError)
  database/
    schema.sql              events.db DDL (with created_at)
    schemas/
      trades.sql            trades.db DDL
      positions.sql         positions.db DDL
      capital.sql           capital.db DDL (snapshots + events index)
      incidents.sql         incidents.db DDL (incidents + log)
    connection.py           open_sqlite + DatabaseSet (5 dbs)
    migrations.py           apply_schema, migrate_database_set
    repositories.py         EventRepository (full Phase 2 API)
  exchanges/                ## Phase 3 - read-only Exchange Gateway
    __init__.py             public exports
    models.py               ExchangeSymbol, OrderBook, RecentTrade,
                            FundingRate, OpenInterest, AccountSnapshot
    base.py                 ExchangeClientBase + ExchangeHealth +
                            WebSocketManager + write-surface refusals
    binance.py              BinanceClient skeleton (NotImplementedError)
    mock.py                 MockExchangeClient (deterministic, no network)
  market_data/              ## Phase 4 - Market Data Buffer
    __init__.py             public exports
    models.py               Bar / BarInterval / LiquidationEvent /
                            MarketDataBufferConfig /
                            MarketDataDegradedReason / BufferStats
    candles.py              CandleBuilder + bucket_start_ms
    cvd.py                  signed_volume + compute_cvd
    atr.py                  true_range + compute_atr
    oi.py                   OpenInterestSnapshotState
    funding.py              FundingSnapshotState
    liquidation.py          LiquidationFeedState
    buffer.py               MarketDataBuffer (track / ingest_* /
                            snapshot / is_degraded /
                            on_websocket_disconnect / reconnect /
                            mark_degraded / refresh_from_exchange)
  execution/      Execution FSM skeleton (full impl in Issue #9)
  risk/           Risk Engine skeleton (full impl in Issue #7)
  telegram/       Telegram Command Center skeleton (Issue #10)
  monitoring/     metrics + health + alerts (in-memory)
  main.py         Phase 4 entrypoint with read-only self-check +
                  Market Data Buffer self-check
scripts/
  init_db.py      Initialise all five Phase 2 databases
tests/
  unit/
    test_database_set.py            multi-db connection + migrations
    test_phase2_schemas.py          Phase 2 schema column contract
    test_event_repository.py        EventRepository full Phase 2 API
    test_init_db_script.py          init_db.py
    test_main_entrypoint.py         entrypoint smoke incl. Phase 4
    test_exchange_models.py         Phase 3 model contracts + tiers
    test_exchange_base.py           ExchangeClientBase + WS + Health
    test_binance_client.py          BinanceClient skeleton refusals
    test_mock_exchange_client.py    MockExchangeClient lifecycle
    test_phase3_no_network.py       repo-wide no-SDK / no-import scan
    test_market_data_models.py      Phase 4 value-object contract
    test_market_data_candles.py     CandleBuilder + bucket alignment
    test_market_data_cvd.py         CVD calculator + acceptance #1
    test_market_data_atr.py         ATR + acceptance #2
    test_market_data_oi_funding_liquidation.py  OI / funding / liq state
    test_market_data_buffer.py      MarketDataBuffer + acceptance #3, #4
    test_phase4_no_network.py       Phase 4 no-network / no-API-key scan
    test_market_data_buffer_review_fixes.py  PR #15 review fixes:
                                    snapshot() throttle + late-trade
                                    counter + refresh_from_exchange
                                    docstring boundary
    ... + the Phase 1 tests (enums, models, settings, telegram, etc.)
docs/
  AMA_RT_V1_4_Production_Spec_Kiro.md  - V1.4 production spec
  IMPLEMENTATION_PLAN.md, GO_NO_GO.md, TEST_MATRIX.md
  CHANGELOG.md
.env.example      Placeholder env vars (no real keys)
.gitignore        Excludes .env, data/, *.db, etc.
pyproject.toml
requirements.txt  No exchange SDK, no HTTP client
```

## Running

```bash
# 1. Install Python 3.11+ then:
pip install -r requirements.txt

# 2. Initialise all five databases (idempotent):
python -m scripts.init_db
# Sample output:
# [ama-rt][init_db] OK trading_mode=paper sqlite_dir=/.../sqlite
# [ama-rt][init_db]   events.db      journal=wal    schema=schema.sql
# [ama-rt][init_db]   trades.db      journal=wal    schema=trades.sql
# [ama-rt][init_db]   positions.db   journal=wal    schema=positions.sql
# [ama-rt][init_db]   capital.db     journal=wal    schema=capital.sql
# [ama-rt][init_db]   incidents.db   journal=wal    schema=incidents.sql

# 3. Run the Phase 4 entrypoint - prints a status banner and exits 0:
python -m app.main
# Sample output:
# [AMA-RT] Phase 4 - Market Data Buffer v1.4.0a4 mode=paper \
#   live_trading=False right_tail=False llm=False exchange_live_orders=False \
#   databases=5 events_count=9 capital_events=1 \
#   exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
#   market_data=3/0 market_snapshots=3 data_unreliable=1 \
#   risk_decision=True/paper_only_skeleton_approval health=ok

# 4. Run the test suite (319 tests):
pytest
```

To override the data directory (used by tests):

```bash
AMA_DATA_DIR=/tmp/ama python -m scripts.init_db
```

## Programmatic usage (Phase 3 read-only API)

```python
from app.exchanges import MockExchangeClient
from app.core.errors import SafeModeViolation, ExchangeConnectionError

client = MockExchangeClient(autostart=True)

# Read-only surfaces:
symbols = client.get_symbols()
book = client.get_orderbook("BTCUSDT", depth=5)
trades = client.get_recent_trades("BTCUSDT", limit=10)
funding = client.get_funding_rate("BTCUSDT")
oi = client.get_open_interest("BTCUSDT")
account = client.get_account_snapshot()

# Write surfaces always refuse:
try:
    client.create_order(symbol="BTCUSDT", side="buy", qty=1.0)
except SafeModeViolation as exc:
    print("expected:", exc)

# Disconnect simulation:
client.simulate_disconnect(reason="test")
try:
    client.get_orderbook("BTCUSDT")
except ExchangeConnectionError as exc:
    print("expected:", exc)
```

## Programmatic usage (Phase 4 Market Data Buffer)

```python
from app.exchanges import MockExchangeClient
from app.market_data import MarketDataBuffer

client = MockExchangeClient(autostart=True)
buffer = MarketDataBuffer(exchange=client)

buffer.track("BTCUSDT")
buffer.refresh_from_exchange("BTCUSDT")          # uses the mock only

snapshot = buffer.snapshot("BTCUSDT", emit_event=False)
print(snapshot.cvd_1m, snapshot.atr_1m, snapshot.volume_1m)

# Out-of-order tape detection: the CandleBuilder drops late trades
# (Spec section 14.2 forbids silent rewrites) and BufferStats surfaces
# the cumulative count so monitoring can alert on it.
print(buffer.stats().late_trades_dropped_total)

# Phase 5+ high-frequency callers should construct the buffer with the
# throttle hook off so events.db does not bloat:
#   from app.market_data.models import MarketDataBufferConfig
#   cfg = MarketDataBufferConfig(market_snapshot_event_emit_enabled=False)
#   buffer = MarketDataBuffer(exchange=client, config=cfg)
# An on-demand audit-trail entry is still possible via
# ``buffer.snapshot(symbol, emit_event=True)``.

# WS disconnect drives DATA_UNRELIABLE through to consumers.
buffer.on_websocket_disconnect(reason="test")
assert buffer.is_degraded("BTCUSDT")
```

## What is NOT here yet

Everything in Issues #5 through #10. Specifically:

- **No real exchange adapter.** `BinanceClient` is a skeleton; every
  read method raises `NotImplementedError`. Phase 4 (this PR) drives
  the Market Data Buffer from `MockExchangeClient` only under the
  constraints listed in *Phase 4 hard boundary* above: mock / fixture
  data is the default, no real adapter is added, no API key, no write
  surface, no auto-connect to the real exchange.
  `get_account_snapshot` remains a skeleton in Phase 3 **and** Phase 4
  because authenticated account reads cannot land before the
  limited-live phase. Real authenticated REST and the user-data
  WebSocket stream both land with Issue #9 (Reconciliation), behind
  the Risk Engine.
- No Regime / Universe / Liquidity engines (Issue #5).
- No anomaly / confirmation / manipulation scanners (Issue #6).
- No full Risk Engine - the Phase 1 engine still only refuses live and
  right-tail actions. Issue #7 will read `MarketDataBuffer.is_degraded`
  for its No-Trade Gate.
- No Capital Flow Engine; Phase 2 ships only the **event recording**
  for it (Issue #8).
- No real Execution FSM driver, no Reconciliation against an exchange
  (Issue #9).
- No LLM Interpreter, no Telegram outbound bot, no Replay diff reports,
  no Reflection (Issue #10).

## Live trading risk

**There is no live trading risk in Phase 4.** This PR adds:

- An in-process `MarketDataBuffer` that consumes deterministic
  `RecentTrade`, `OrderBook`, `FundingRate`, `OpenInterest` and
  `LiquidationEvent` value objects.
- Pure helpers (`compute_cvd`, `compute_atr`, `CandleBuilder`,
  `OpenInterestSnapshotState`, `FundingSnapshotState`,
  `LiquidationFeedState`) plus a `MARKET_SNAPSHOT` /
  `DATA_UNRELIABLE` event-emission path through the existing
  `EventRepository`.
- A boot-time self-check that drives the buffer through one ingest +
  snapshot + WS disconnect / reconnect cycle using the deterministic
  `MockExchangeClient` only.
- 76 new unit tests on top of the 235 retained from Phase 1 / 2 / 3
  (311 total).

What this PR does NOT add:

- No exchange SDK in `requirements.txt` / `pyproject.toml` (asserted
  by `tests/unit/test_phase3_no_network.py` and
  `tests/unit/test_phase4_no_network.py`).
- No outbound HTTP / WebSocket client of any kind in `app/`.
- No real `create_order` / `cancel_order` / `set_leverage` /
  `set_margin_mode` call site.
- No `BinanceClient` implementation; every read method still raises
  `NotImplementedError`. `get_account_snapshot` continues to refuse
  outright with a message that mentions "skeleton", "phase 4" and
  "api key".
- No `api_key` / `api_secret` parameter anywhere under
  `app/market_data/`.
- No `market.db` (the buffer is in-memory only).
- No Telegram bot library, no LLM client.
- No new mode flags, no loosened safety lock.

Defence in depth (cumulative):

1. `app/config/settings.py::_apply_phase1_safety_lock()` overwrites
   the five flags after YAML + env loading.
2. `app/main.py::_assert_phase1_safety()` raises `SafetyViolation` at
   boot if any flag has drifted.
3. `app/main.py::_assert_phase3_read_only()` probes every banned
   write surface and raises `SafeModeViolation` if any of them stops
   refusing.
4. `app/risk/engine.py` rejects `live_trading_required=True` and
   `right_tail_amplify=True` requests.
5. `app/exchanges/base.py::ExchangeClientBase.{create_order,
   cancel_order, set_leverage, set_margin_mode}` always raise
   `SafeModeViolation`.

All five layers are unit-tested.

## License

Proprietary. Internal use only.
