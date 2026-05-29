# Phase 11C.1D-D-D — MockExchange + Pessimistic Fill Model v0 (PR97)

> *Strict blind walk-forward simulated exchange + conservative fill model*
> *严格前向 Sim-Live 模拟交易所与保守成交模型 v0*
>
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Type:** **Implementation PR** (paper / report / evidence-only
> infrastructure).
> **Parent:** Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
> Constitution* (PR93, merged), Phase 11C.1D-D-A *SimulationClock
> + Time-Wall Guard* (PR94, merged), Phase 11C.1D-D-B
> *Historical Market Store v0* (PR95, merged), and Phase
> 11C.1D-D-C *ReplayFeedProvider v0* (PR96, merged).
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

---

## 0. Pre-amble — what this PR is and is NOT

This PR ships the **fourth** anti-future-lookahead infrastructure
block of the strict blind walk-forward stack defined by Phase
11C.1D-D (PR93). It is a small, deterministic, pure-Python
in-memory simulated exchange and conservative fill model. It
introduces **no** runtime hot-path wiring, **no** new event
types, **no** schema migration, **no** I/O, **no** network,
**no** real data fetch, **no** real exchange API, **no**
signed endpoint, **no** private websocket, **no** API key,
**no** API secret, and **no** authority over the Risk Engine,
the Execution FSM, or the Capital Flow Engine. PR97 builds
strictly on top of the PR94 + PR95 + PR96 substrate and re-uses
every PR94 / PR95 / PR96 primitive verbatim
(`SimulationClock`, `HistoricalRecordTime`, `TimeWallGuard`,
`CandleVisibilityGuard`, `NoLookaheadViolation`,
`assert_no_forbidden_fields`, `HistoricalMarketStore`,
`HistoricalMarketRecord`, `HistoricalKlineRecord`,
`SymbolStatusRecord`, `HistoricalMarketRecordType`,
`SymbolStatus`, `DataQualityFlag`, `DataCompletenessState`,
`ReplayFeedBatch`, `ReplayFeedProvider`,
`ReplayFeedProviderConfig`, `ReplayFeedDiagnostics`,
`ReplayFeedCursor`).

This PR IS:

  - a `MockOrderType` closed taxonomy: `MARKET`, `LIMIT`,
    `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `FORCED_EXIT`,
  - a `MockOrderSide` closed taxonomy: `BUY`, `SELL` —
    paper-only field; NEVER an AI / strategy recommendation,
  - a `MockOrderStatus` closed taxonomy: `CREATED`, `ACCEPTED`,
    `PARTIALLY_FILLED`, `FILLED`, `REJECTED`, `CANCELED`,
    `EXPIRED`, `STALE`, `AMBIGUOUS_INTRABAR_PATH`,
  - an `AmbiguousIntrabarPolicy` closed taxonomy:
    `WORST_CASE`, `AMBIGUOUS`,
  - a `LimitTouchFillPolicy` closed taxonomy:
    `NO_FILL_ON_TOUCH` (default), `ALLOW_FILL_ON_TOUCH`,
  - a `FillReason` closed taxonomy: `MARKET_FILL`,
    `LIMIT_FILL_ON_PENETRATION`, `STOP_TRIGGERED_FILL`,
    `TAKE_PROFIT_TRIGGERED_FILL`, `FORCED_EXIT_FILL`,
    `AMBIGUOUS_WORST_CASE_STOP_FILL`,
  - a `ConservativeAssumption` closed taxonomy:
    `TAKER_FEE_APPLIED`, `SLIPPAGE_APPLIED`,
    `LATENCY_PENALTY_APPLIED`, `LIMIT_PENETRATION_REQUIRED`,
    `STOP_ADVERSE_FILL`, `TAKE_PROFIT_CONSERVATIVE_FILL`,
    `FORCED_EXIT_CONSERVATIVE_FILL`,
    `AMBIGUOUS_INTRABAR_WORST_CASE`, `PARTIAL_FILL`,
    `NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA`,
  - a `MockOrder` (mutable so that lifecycle status / filled_qty
    can advance) carrying hard-pinned `simulated_only=True`,
    `no_live_order=True`, `phase_12_forbidden=True`,
    `trade_authority=False`, `auto_tuning_allowed=False`,
  - a `MockFill` (frozen) carrying `fill_id`, `order_id`,
    `symbol`, `side`, `filled_qty`, `fill_price`, `fee`,
    `slippage_bps`, `latency_bps`, `funding_impact`,
    `reference_price`, `fill_reason`,
    `filled_at_simulated`, `conservative_assumption` tuple,
    `evidence_refs`, plus the same hard-pinned safety markers,
  - a `MockExchangeConfig` (frozen) carrying `taker_fee_bps`,
    `maker_fee_bps`, `default_slippage_bps`,
    `latency_penalty_bps`, `stale_after_seconds`,
    `reject_if_no_visible_price` (default `True`),
    `limit_touch_fill_policy` (default `NO_FILL_ON_TOUCH`),
    `ambiguous_intrabar_policy` (default `WORST_CASE`),
    `partial_fill_enabled` (default `True`),
    optional `max_fill_fraction_per_batch` (in `(0, 1]`),
    hard-pinned `sandbox_only=True`,
    hard-pinned `live_order_enabled=False`,
  - a `FillModelDecision` describing the outcome of a single
    fill-model evaluation (fill / new_status / reason / detail),
  - a `PessimisticFillModel` (pure / deterministic /
    pessimistic) implementing the rules in §6 below,
  - an `OrderRequest` (frozen) used by
    `MockExchange.submit_order`,
  - a `MockExchangeDiagnostics` (mutable counters) carrying
    `orders_submitted_count`, `orders_accepted_count`,
    `orders_rejected_count`, `orders_canceled_count`,
    `orders_expired_count`, `orders_stale_count`,
    `orders_filled_count`, `orders_partially_filled_count`,
    `orders_ambiguous_intrabar_count`, `fills_count`,
    `process_batch_count`,
  - a `MockExchange` with `submit_order` /
    `cancel_order` / `expire_order` / `process_batch` /
    `get_order` / `list_open_orders` / `list_all_orders` /
    `list_fills` / `reset` / `safety_payload` / `to_dict`,
  - the matching unit-test module
    `tests/unit/test_mock_exchange_pessimistic_fill_model.py`
    (25 PASSING tests covering all 22 brief-mandated scenarios
    plus 3 defensive extras: closed-taxonomy enforcement,
    LIMIT/STOP/TP requires its trigger price, `reset()` clears
    state).

This PR is **NOT**:

  - a Simulated Capital Flow + Trade Ledger (PR98's
    responsibility),
  - a Telegram Sandbox Outbox (PR99's responsibility),
  - a Blind Walk-forward Runner (PR100's responsibility),
  - real Execution FSM wiring,
  - real Risk Engine integration,
  - a fetcher of real market network data,
  - a Binance private API client,
  - a signed-endpoint reachability layer,
  - a private websocket / listenKey client,
  - an authorisation to enter Phase 12,
  - an authorisation to enable live orders,
  - an authorisation to grant AI trade authority,
  - an authorisation to grant Telegram command authority,
  - an authorisation to auto-tune any rule, threshold, or
    parameter.

PR97 acceptance authorises the next allowed paper-only step
(**PR98 — Simulated Capital Flow + Trade Ledger v0**). It does
NOT authorise PR99 → PR100, live trading, auto-tuning, the
DeepSeek hot path, Telegram live outbound, or Phase 12.

---

## 1. Purpose

Strict blind walk-forward (PR93 §1) is **not** an ordinary
backtest. PR94 + PR95 + PR96 give us strict no-lookahead market
data. PR97 supplies the **simulated execution substrate**: an
order lifecycle simulator and a conservative fill model that
consumes only `ReplayFeedBatch` / `HistoricalKlineRecord`
visible market data and produces deterministic, paper-only,
audit-ready fills. The fill model is **pessimistic**:

  - market orders pay a taker fee plus slippage plus optional
    latency penalty adverse to the order's side,
  - limit orders refuse to fill on touch and require strict
    penetration beyond the limit before filling at the limit
    price,
  - stop orders fill at the **adverse** stop price plus taker
    fee plus slippage (a SELL stop fills BELOW the stop level;
    a BUY stop fills ABOVE the stop level),
  - take-profit orders fill at the trigger level adverse by
    slippage plus optional latency penalty (still pessimistic
    on the favorable side),
  - forced exits use a conservative market exit at the visible
    close price adverse by slippage + latency,
  - same-candle stop + take-profit triggers fall back to the
    adverse stop fill under `WORST_CASE` (the default) or to
    `AMBIGUOUS_INTRABAR_PATH` under `AMBIGUOUS`,
  - insufficient visible price data NEVER produces an
    optimistic fill: the order is `REJECTED` (if young) or
    `STALE` (if old), never `FILLED`.

The objective is **truthful, deterministic, reproducible
fill discipline**, not a fast simulator. Pretty equity curves
built on optimistic fills are not evidence; they are
falsifications. PR97 makes the optimistic-fill path
syntactically impossible for the modules that consume it
(PR98 → PR100).

---

## 2. Relation to PR93 constitution

PR93 (the *Strict Blind Walk-forward Sim-Live Constitution*)
is docs-only. PR97 is the **fourth implementation slice**
authorised by PR93 §19's engineering route (after PR94, PR95,
and PR96 were merged). PR97 implements §11 of PR93:

  - **§11 MockExchange + Pessimistic Fill Model.** The
    MockExchange consumes only ReplayFeedProvider /
    HistoricalMarketStore visible market data. It NEVER calls
    a real exchange endpoint. It NEVER signs a request. It
    NEVER touches the Binance private API. It NEVER opens a
    private websocket. It NEVER fetches account / order /
    position / leverage / margin endpoints. The Pessimistic
    Fill Model implements taker-fee + slippage + optional
    latency penalty arithmetic, no-fill-on-touch limit rules,
    adverse-fill stop rules, conservative take-profit rules,
    forced-exit conservative-market rules, and the closed-
    taxonomy ambiguous-intrabar handling described in §6.

PR97 does NOT touch §12 (Latency / Outage / Data Degradation
injection), §13 (Simulated Capital Flow), §14 (Telegram
sandbox), §15 (AI role), §16 (Required outputs), §17
(Acceptance criteria). Those are the responsibility of PR98
→ PR100, each behind its own gate.

---

## 3. Relation to PR94 / PR95 / PR96

PR97 reuses every prior primitive verbatim:

  - **PR94** — `SimulationClock`, `HistoricalRecordTime`,
    `TimeWallGuard`, `CandleVisibilityGuard`,
    `NoLookaheadViolation`, `assert_no_forbidden_fields`. PR97
    NEVER consults the wall-clock; every visible moment comes
    from caller-supplied `simulated_time` or
    `replay_batch.simulated_time`. PR97 NEVER substitutes
    `ingested_at` for `available_at`. Every `to_dict()`
    boundary in this PR runs through
    `assert_no_forbidden_fields`.
  - **PR95** — `HistoricalMarketStore`,
    `HistoricalKlineRecord`, `HistoricalMarketRecord`,
    `SymbolStatusRecord`, `HistoricalMarketRecordType`,
    `SymbolStatus`, `DataQualityFlag`,
    `DataCompletenessState`. PR97 only reads
    `HistoricalKlineRecord` (visible OHLCV) for fill arithmetic.
    By construction, every kline visible to PR97 has
    `available_at >= close_time` (PR95 invariant) — PR97 never
    sees an unclosed candle.
  - **PR96** — `ReplayFeedBatch`, `ReplayFeedProvider`,
    `ReplayFeedProviderConfig`, `ReplayFeedDiagnostics`,
    `ReplayFeedCursor`. PR97's `MockExchange.process_batch`
    consumes a single `ReplayFeedBatch`; PR97 NEVER bypasses
    the batch's strict no-lookahead / closed-candle / as-of
    universe contract. The `_latest_visible_kline(symbol,
    batch)` helper picks the latest 1m or 5m kline from the
    batch (preferring 1m over 5m) for the order's symbol,
    sorting by `close_time`. Only those klines reach the fill
    model.

PR97 does NOT modify any PR94 / PR95 / PR96 source file. The
existing PR94 / PR95 / PR96 modules are reused **verbatim**.

---

## 4. MockExchange contract

`MockExchange` is constructed with a `MockExchangeConfig`
and (optionally) a `PessimisticFillModel`. If no fill model
is supplied, the exchange constructs one from the same config.
The exchange's public surface is:

| method | behaviour |
| --- | --- |
| `submit_order(request, replay_batch=None, simulated_time=None)` | Accept an `OrderRequest`, build a `MockOrder` (status `ACCEPTED`), and (if a batch is supplied) immediately evaluate it against the visible kline. Returns the `MockOrder`. |
| `cancel_order(order_id, simulated_time)` | Cancel an open order (idempotent on terminal orders). Returns the `MockOrder` with status `CANCELED`. |
| `expire_order(order_id, simulated_time)` | Mark an open order as expired. Idempotent on terminal orders. |
| `process_batch(replay_batch)` | Evaluate every open order against `replay_batch`. Returns the list of `MockFill` objects produced **during this call**. |
| `get_order(order_id)` | Return the `MockOrder` or raise `KeyError`. |
| `list_open_orders()` | Return the list of currently-open orders, sorted by `order_id`. |
| `list_all_orders()` | Return the list of all orders, sorted by `order_id`. |
| `list_fills()` | Return all `MockFill` objects, in submission order. |
| `reset()` | Clear all in-memory state. **Test-only.** |
| `safety_payload()` | Return the project-wide safety boundary dict (re-pinned). |
| `to_dict()` | Return a JSON-serialisable view of `(config, diagnostics, order_count, fill_count)`. |

Public properties: `config`, `fill_model`, `diagnostics`,
`order_count`, `fill_count`, plus the defensive tripwires
`sandbox_only`, `simulated_only`, `no_live_order`,
`live_trading`, `exchange_live_orders`,
`binance_private_api_enabled`, `signed_endpoint_reachable`,
`private_websocket_reachable`, `account_endpoint_reachable`,
`order_endpoint_reachable`, `position_endpoint_reachable`,
`leverage_endpoint_reachable`, `margin_endpoint_reachable`,
`real_exchange_order_path`, `real_capital`,
`telegram_outbound_enabled`, `ai_trade_authority`,
`trade_authority`, `auto_tuning_allowed`,
`phase_12_forbidden`.

Two exchanges fed identical config + requests + batches
produce identical order / fill sequences (verified by
`test_deterministic_output_from_same_batch_config_order`).

---

## 5. Order lifecycle schema

The order status state machine:

```
                  ┌────────────────────────────────────────┐
                  │                                        ▼
CREATED ──► ACCEPTED ──► PARTIALLY_FILLED ──► FILLED  (terminal)
                  │              │
                  ├──► REJECTED  (terminal, never filled or insufficient data)
                  ├──► CANCELED  (terminal, operator or paired-WORST_CASE)
                  ├──► EXPIRED   (terminal, operator)
                  ├──► STALE     (terminal, age >= stale_after_seconds without fill)
                  └──► AMBIGUOUS_INTRABAR_PATH (terminal, AMBIGUOUS policy)
```

Notes:

  - `submit_order` always transitions through `CREATED ->
    ACCEPTED` at construction. The `CREATED` literal is
    available so that downstream PRs (PR98+) can model a
    pre-acceptance moment if they want to; PR97's
    `MockExchange` collapses `CREATED -> ACCEPTED` into the
    same instant.
  - `PARTIALLY_FILLED` is **not** terminal. Subsequent
    `process_batch` calls may fill more of the remaining
    quantity until either `FILLED` (terminal) or another
    terminal status is reached.
  - Every status transition stamps
    `last_status_change_at_simulated`.
  - `CANCELED` may be reached via operator
    (`cancel_order(order_id, simulated_time)`) **or** via the
    `WORST_CASE` ambiguous-intrabar policy when the paired
    stop fires (the take-profit is canceled).
  - `STALE` is reached when the order's age (relative to
    `created_at_simulated`) is `>= stale_after_seconds` AND
    the next evaluation has no visible price reference.
  - `REJECTED` is reached when the order's age is
    `< stale_after_seconds` AND the next evaluation has no
    visible price reference AND
    `reject_if_no_visible_price=True`.
  - `AMBIGUOUS_INTRABAR_PATH` is reached on both paired
    orders when the same kline triggers both the stop and
    take-profit levels AND
    `ambiguous_intrabar_policy=AMBIGUOUS`.

---

## 6. Fill model schema

`PessimisticFillModel.evaluate(order, kline, *,
simulated_time, fill_id, ambiguous_intrabar_pair=False)`
returns a `FillModelDecision`. The decision either yields a
`MockFill` (advancing the order to `FILLED` /
`PARTIALLY_FILLED`), yields a non-fill terminal status
(`REJECTED` / `STALE` / `EXPIRED` / `AMBIGUOUS_INTRABAR_PATH`
/ `CANCELED`), or leaves the order open
(`new_status=None`, `fill=None`).

Every `MockFill` carries:

| field | role |
| --- | --- |
| `fill_id` | deterministic `"mock_fill_{counter:08d}"` |
| `order_id` | the parent `MockOrder.order_id` |
| `symbol` | matches the order |
| `side` | matches the order |
| `filled_qty` | strictly positive; bounded by `eligible_qty` |
| `fill_price` | strictly positive; computed per §6.x |
| `fee` | non-negative; `fill_price * filled_qty * fee_bps / 10000` |
| `slippage_bps` | non-negative |
| `latency_bps` | non-negative or `None` |
| `funding_impact` | reserved for PR98; defaults to `None` |
| `reference_price` | the visible reference (kline close, limit, stop, or TP level) |
| `fill_reason` | one of `FillReason.ALLOWED` |
| `filled_at_simulated` | UTC-aware |
| `conservative_assumption` | non-empty closed-taxonomy tuple |
| `evidence_refs` | optional string refs |
| safety markers | hard-pinned `simulated_only=True`, `no_live_order=True`, `phase_12_forbidden=True`, `trade_authority=False`, `auto_tuning_allowed=False` |

### 6.1 Market order conservative rule

For `MARKET` orders, the reference price is `kline.close`.
Total adverse bps is `default_slippage_bps +
latency_penalty_bps`. Fill price is:

  - `BUY`: `reference * (1 + total_bps / 10000)`,
  - `SELL`: `reference * (1 - total_bps / 10000)`.

Fee is the **taker** fee on the fill notional. Conservative
markers: `TAKER_FEE_APPLIED`, `SLIPPAGE_APPLIED` (when
`slippage_bps > 0`), `LATENCY_PENALTY_APPLIED` (when
`latency_penalty_bps > 0`). `FillReason.MARKET_FILL`.

### 6.2 Limit order no-fill-on-touch rule

For `LIMIT` orders:

  - `BUY` limit at `L`: fill iff `kline.low < L`
    (strictly penetrates). If `kline.low == L` only,
    `NO_FILL_ON_TOUCH` (the default) refuses to fill;
    `ALLOW_FILL_ON_TOUCH` is exposed only for parity testing.
  - `SELL` limit at `L`: fill iff `kline.high > L`
    (strictly penetrates). Touch-only does not fill under
    `NO_FILL_ON_TOUCH`.

When penetration occurs, the fill price is the **limit** (the
conservative best-case trade price for the resting order). If
`latency_penalty_bps > 0`, the fill price is moved adverse by
the latency component.

Fee is the **maker** fee (limit orders typically rest in the
book). The model is intentionally not advertising "free maker
rebate"; the maker fee is charged. Conservative markers:
`TAKER_FEE_APPLIED` (i.e., "fee applied"),
`LIMIT_PENETRATION_REQUIRED`, `LATENCY_PENALTY_APPLIED` (when
applicable). `FillReason.LIMIT_FILL_ON_PENETRATION`.

### 6.3 Stop-loss adverse fill rule

For `STOP_MARKET` orders:

  - Trigger condition:
      - `BUY` stop (covering a short): `kline.high >= stop_price`,
      - `SELL` stop (closing a long): `kline.low <= stop_price`.
  - Fill price (when triggered): `stop_price` moved adverse
    by `default_slippage_bps + latency_penalty_bps` bps:
      - `BUY`: `stop_price * (1 + total_bps / 10000)` (worse
        than the stop level),
      - `SELL`: `stop_price * (1 - total_bps / 10000)` (worse
        than the stop level).

Fee is the **taker** fee. Conservative markers:
`TAKER_FEE_APPLIED`, `SLIPPAGE_APPLIED`,
`LATENCY_PENALTY_APPLIED` (when applicable),
`STOP_ADVERSE_FILL`. `FillReason.STOP_TRIGGERED_FILL`.

### 6.4 Take-profit conservative rule

For `TAKE_PROFIT_MARKET` orders, the trigger level is also
stored in `stop_price`:

  - Trigger condition:
      - `SELL` TP (long position locking gain):
        `kline.high >= stop_price`,
      - `BUY` TP (short position locking gain):
        `kline.low <= stop_price`.
  - Fill price (when triggered): `stop_price` moved adverse
    by `default_slippage_bps + latency_penalty_bps` bps. The
    TP fill is **not** at the favorable extreme of the bar;
    we cannot prove the favorable price persisted.

Fee is the **taker** fee. Conservative markers:
`TAKER_FEE_APPLIED`, `SLIPPAGE_APPLIED`,
`LATENCY_PENALTY_APPLIED` (when applicable),
`TAKE_PROFIT_CONSERVATIVE_FILL`.
`FillReason.TAKE_PROFIT_TRIGGERED_FILL`.

### 6.5 Forced exit rule

For `FORCED_EXIT` orders (used by the future PR98 Capital
Flow Engine when a position must be unwound), the fill is a
conservative market exit at `kline.close` adverse by
`default_slippage_bps + latency_penalty_bps`. Fee is the
taker fee. Conservative markers: `TAKER_FEE_APPLIED`,
`SLIPPAGE_APPLIED`, `LATENCY_PENALTY_APPLIED` (when
applicable), `FORCED_EXIT_CONSERVATIVE_FILL`.
`FillReason.FORCED_EXIT_FILL`.

### 6.6 Insufficient visible data: no optimistic fill

If `kline is None` (no visible price reference for the
order's symbol in the batch), the model NEVER produces a
fill. Instead, when `reject_if_no_visible_price=True` (the
default):

  - if the order's age `>= stale_after_seconds`, the order
    transitions to `STALE`,
  - otherwise the order transitions to `REJECTED`.

Conservative marker: `NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA`
(carried on the `FillModelDecision.reason`). When
`reject_if_no_visible_price=False`, the order remains open.

---

## 7. Ambiguous intrabar handling

Same-candle stop + take-profit trigger detection runs in
`MockExchange._is_ambiguous_intrabar_pair(order, kline)`:

  - the order is `STOP_MARKET` or `TAKE_PROFIT_MARKET`,
  - a paired open order exists (matched via
    `pair_with_order_id` on either side),
  - the partner is the **opposite** type (a stop is paired
    with a take-profit, not another stop / TP),
  - both trigger levels are touched by the same kline:
      - the stop level is within `[kline.low, kline.high]`
        on the stop side,
      - the TP level is within `[kline.low, kline.high]` on
        the TP side.

When the ambiguity is detected, the configured policy
applies:

| `ambiguous_intrabar_policy` | stop order | take-profit order |
| --- | --- | --- |
| `WORST_CASE` (default) | `FILLED` with `fill_reason=AMBIGUOUS_WORST_CASE_STOP_FILL`, fill at the adverse stop level (worst-case for the position) | `CANCELED` (cannot prove the favorable level was hit first) |
| `AMBIGUOUS` | `AMBIGUOUS_INTRABAR_PATH` (no fill) | `AMBIGUOUS_INTRABAR_PATH` (no fill) |

The model NEVER picks the favorable result. Without tick /
trade data, intra-bar ordering is intrinsically unknowable;
the only honest options are "assume the worst" or "refuse
to commit". PR97 implements both.

---

## 8. Fees / slippage / latency assumptions

| field | role | default |
| --- | --- | --- |
| `taker_fee_bps` | basis-points fee charged on market / stop / TP / forced-exit fills, and (conservatively) on limit fills via `_compute_fee` (the limit branch uses the maker fee scalar) | `4.0` |
| `maker_fee_bps` | basis-points fee charged on limit fills | `2.0` |
| `default_slippage_bps` | basis-points slippage applied adverse to the order's side on market / stop / TP / forced-exit fills | `5.0` |
| `latency_penalty_bps` | additional basis-points adverse penalty applied on every fill type (market, limit, stop, TP, forced-exit) | `0.0` |
| `stale_after_seconds` | order age threshold for the `STALE` transition when no visible price | `300.0` |

All fee / bps values are non-negative. `MockExchangeConfig`
refuses negative values at construction.

`max_fill_fraction_per_batch` (optional, in `(0, 1]`) caps
each `process_batch` fill at the given fraction of the
order's **requested** quantity (not the remaining quantity).
This is a per-batch cap, so a 4-unit order with
`max_fill_fraction_per_batch=0.5` fills 2 units per batch
until completion. When set, `partial_fill_enabled=True` is
required.

---

## 9. This does NOT implement Simulated Capital Flow

PR97 has no concept of equity, balance, position, leverage,
margin, funding, or P&L. It has no `Position` /
`CapitalAccount` / `TradeLedger` / `EquityCurve` /
`MarginAccount` / `FundingSchedule` data type. It has no
`apply_fill_to_position` / `mark_to_market` /
`accrue_funding` / `update_equity` method. The Simulated
Capital Flow + Trade Ledger (Constitution §13) is PR98's
responsibility.

`MockFill.funding_impact` is a placeholder field reserved for
PR98; PR97 always sets it to `None`.

---

## 10. This does NOT implement Trade Ledger

PR97 has no Trade Ledger. PR97 does not group fills into
trades, does not compute realised / unrealised P&L, does not
track open positions, does not track close prices, does not
compute MFE / MAE / drawdown, and does not produce a Trade
Ledger artifact. `MockExchange.list_fills()` is a flat list
of `MockFill` objects in submission order, NOT a
trade-grouped view. The Trade Ledger is PR98's responsibility.

---

## 11. This does NOT implement Blind Walk-forward Runner

PR97 has no concept of a run, a window, a freeze, a manifest
hash, a Blind Run Manifest, an Equity Timeseries, a Discovery
Quality Ledger, a Failure Ledger, a Telegram Sandbox
Transcript, or an AI Operator Briefing (Constitution §16).
It has no training / freeze / blind / score / experience-
update loop (Constitution §8). It has no run-status taxonomy.
It has no `INVALIDATED_LOOKAHEAD_OR_DRIFT` concept. The
Blind Walk-forward Runner is PR100's responsibility.

PR97 supplies the **simulated execution substrate** that the
runner will consume. That is the entire scope.

---

## 12. This does NOT call real exchange

Hard rules (verified by tests):

  - `MockExchange.binance_private_api_enabled = False`,
  - `MockExchange.signed_endpoint_reachable = False`,
  - `MockExchange.private_websocket_reachable = False`,
  - `MockExchange.account_endpoint_reachable = False`,
  - `MockExchange.order_endpoint_reachable = False`,
  - `MockExchange.position_endpoint_reachable = False`,
  - `MockExchange.leverage_endpoint_reachable = False`,
  - `MockExchange.margin_endpoint_reachable = False`,
  - `MockExchange.real_exchange_order_path = False`,
  - `MockExchange.real_capital = False`,
  - `MockExchange.exchange_live_orders = False`.

Every `MockOrder.order_id` is a deterministic
`"mock_order_{counter:08d}"` string; every `MockFill.fill_id`
is a deterministic `"mock_fill_{counter:08d}"` string. Neither
ever advertises a real exchange order id, an api key, an api
secret, a signed-endpoint reference, a binance signature, a
listenKey, or any private-websocket URL. The forbidden-field
guard rejects payloads carrying any of `api_key`,
`api_secret`, `exchange_order_id`, `real_order_id`,
`binance_signed`, `private_websocket_url`, `listenkey`,
`listen_key`. Public method names are also asserted
disjoint from `place_order`, `place_real_order`,
`sign_request`, `sign`, `open_websocket`,
`private_websocket`, `listen_key`, `set_leverage`,
`set_stop`, `set_target`, `apply_change`, `deploy`,
`enable_live`.

`MockExchangeConfig` refuses construction with
`live_order_enabled=True` or `sandbox_only=False` (any such
attempt raises `ValueError` at construction time).

---

## 13. This does NOT authorise live trading

Hard safety boundary (Phase 11C.1D-D-D / PR97):

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `simulated_only` | `True` |
| `no_live_order` | `True` |
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
| `telegram_outbound_enabled` | `False` |
| `telegram_live_command_authority` | `False` |
| `ai_trade_authority` | `False` |
| `trade_authority` | `False` |
| `auto_tuning_allowed` | `False` |
| `phase_12_forbidden` | **`True`** |

Every record / batch / fill / order / config / diagnostics /
exchange `to_dict()` re-pins this boundary at the
serialisation edge via the recursive
`assert_no_forbidden_fields` guard. The Risk Engine remains
the single trade-decision gate. The MockExchange has no
authority to place a real order, ever.

---

## 14. This does NOT authorise auto-tuning

PR97 NEVER writes runtime config. PR97 exposes no
`apply_change`, `deploy_change`, `runtime_config_patch`,
`symbol_limit_patch`, `threshold_patch`, `candidate_pool_patch`,
`regime_weight_patch`, or `strategy_parameter_patch` field.
The recursive `assert_no_forbidden_fields` guard refuses any
payload that smuggles those names at any nesting depth.
`auto_tuning_allowed=False` is re-pinned on every
serialisation boundary.

A `MockExchangeDiagnostics` counter (e.g., `orders_stale_count`,
`orders_rejected_count`, `orders_ambiguous_intrabar_count`)
is descriptive audit metadata only. It MUST NEVER trigger a
runtime knob change. It MUST NEVER trigger a real trade.

---

## 15. This does NOT authorise Phase 12

Phase 12 remains **FORBIDDEN**. The literal string
`"Phase 12"` does not appear as a destination in
`MOCK_EXCHANGE_PHASE_NAME` or
`PESSIMISTIC_FILL_MODEL_PHASE_NAME`. Every `to_dict()`
boundary re-pins `phase_12_forbidden=True`. Tests assert
that the flag is true on the exchange, every PR97 dataclass,
every emitted fill, and every diagnostic snapshot.

---

## 16. Successful PR97 only allows PR98 Simulated Capital Flow + Trade Ledger

Next-allowed-phase decision rule:

  - PR97 acceptance only authorises **PR98 — Simulated
    Capital Flow + Trade Ledger v0** to begin its own gate.
  - PR97 acceptance does **NOT** authorise PR99 (Telegram
    Sandbox Outbox), PR100 (Blind Walk-forward Runner), live
    trading, auto-tuning, the DeepSeek hot path, Telegram
    live outbound, or Phase 12. **Phase 12 remains
    FORBIDDEN.**

---

## 17. File map

| file | role |
| --- | --- |
| `app/sim/mock_exchange.py` | the `MockExchange` core implementation |
| `app/sim/pessimistic_fill_model.py` | the `PessimisticFillModel` core implementation, plus all closed-taxonomy types and the `MockOrder` / `MockFill` / `MockExchangeConfig` / `FillModelDecision` dataclasses |
| `app/sim/__init__.py` | re-exports the new public surface alongside the PR94 + PR95 + PR96 substrate |
| `tests/unit/test_mock_exchange_pessimistic_fill_model.py` | 25 PASSING tests covering all 22 brief-mandated scenarios plus 3 defensive extras (closed-taxonomy enforcement, LIMIT/STOP/TP requires its trigger price, `reset()` clears state) |
| `docs/PHASE_11C_1D_D_D_MOCK_EXCHANGE_PESSIMISTIC_FILL_MODEL.md` | this file |
| `docs/PROJECT_STATUS.md` | current-phase block updated |
| `docs/PHASE_GATE.md` | new *Open phase: Phase 11C.1D-D-D* section appended; Phase 12 row unchanged |
| `docs/CHANGELOG.md` | this PR's entry |

Files **explicitly NOT touched** by this PR:

  - `app/risk/**`, `app/execution/**`, `app/exchanges/**`,
    `app/telegram/**`, `app/config/**`,
  - `app/sim/simulation_clock.py`,
    `app/sim/time_wall_guard.py`,
    `app/sim/historical_market_store.py`,
    `app/sim/replay_feed_provider.py` (PR94 + PR95 + PR96
    contracts are reused verbatim; not modified),
  - `app/safety/**`, `app/ai/**`, `app/replay/**`,
    `app/reflection/**`, `app/paper_shadow/**`,
    `app/sandbox/**`, `app/state_machine/**`,
    `app/scanner/**`, `app/regime/**`, `app/market_data/**`,
    `app/market_data_public/**`, `app/universe/**`,
    `app/liquidity/**`, `app/manipulation/**`,
    `app/monitoring/**`, `app/database/**`,
    `app/exports/**`, `app/incidents/**`,
    `app/learning/**`, `app/llm/**`, `app/paper_run/**`,
    `app/reconciliation/**`, `app/confirmation/**`,
    `app/capital/**`, `app/core/**`, `app/main.py`,
  - `scripts/**`, `configs/**`, `data/**`,
    `requirements.txt`, `pyproject.toml`, `.env*`.

---

## 18. Test command

```
python -m pytest tests/unit/test_mock_exchange_pessimistic_fill_model.py -q
```

Result: **25 PASSING** tests covering all 22 brief-mandated
scenarios plus 3 defensive extras.

Full suite:

```
python -m pytest tests/unit -q
```

Result: **3504 PASSING** tests, 0 failures (was 3479 before
this phase; +25 from this phase).

---

## 19. Acceptance status

**Status:** IN_REVIEW (after this implementation PR; not
`ACCEPTED` until maintainer review).

`ACCEPTED` requires a separate docs-closeout PR after
maintainer review.

Phase 12 remains **FORBIDDEN**.
