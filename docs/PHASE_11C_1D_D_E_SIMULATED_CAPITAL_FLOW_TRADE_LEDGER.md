# Phase 11C.1D-D-E — Simulated Capital Flow + Trade Ledger v0 (PR98)

> **Status: IN_REVIEW** (after this implementation PR; not `ACCEPTED`
> until maintainer review).
> **Mode: paper only.** **Phase 12: FORBIDDEN.**
> **Trade authority: false. Live capital: false. Auto-tuning:
> disabled. Telegram outbound: disabled. Binance private API:
> disabled. LLM / DeepSeek: not invoked.**

## 1. Purpose

This phase ships the **Simulated Capital Flow + Trade Ledger v0** —
the deterministic paper-only capital-accounting layer of the strict
blind walk-forward stack defined by Phase 11C.1D-D (PR93, the *Strict
Blind Walk-forward Sim-Live Constitution*).

PR98 implements the *fifth* anti-future-lookahead infrastructure
block of that stack:

  - the simulated capital state (`SimulatedCapitalState`),
  - the simulated position book (`SimulatedPosition`),
  - the trade ledger (`TradeLedgerEntry` / `TradeLedger` /
    `TradeLedgerSummary`),
  - the equity timeseries (`EquityTimeseriesPoint`),
  - the engine that consumes :class:`MockFill` events and produces
    those four outputs (`SimulatedCapitalFlowEngine`).

PR98 does **NOT**:

  - implement the **Telegram Sandbox Outbox** (PR99),
  - implement the **Blind Walk-forward Runner** (PR100),
  - connect the simulated capital state to a real account,
  - touch the Risk Engine, Execution FSM, real exchange gateway, or
    any runtime config.

## 2. Relation to PR93 (Strict Blind Walk-forward Sim-Live
##    Constitution)

PR98 is the §12 artefact of the constitution: a paper-only
capital-accounting and trade-ledger surface that consumes
:class:`MockFill` outputs from PR97 and produces deterministic state
/ ledger / equity-timeseries snapshots for downstream review. It
holds every safety boundary defined by PR93:

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `simulated_only` | `True` |
| `no_live_order` | `True` |
| `live_trading` | `False` |
| `live_capital_enabled` | `False` |
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
| `ai_trade_authority` | `False` |
| `trade_authority` | `False` |
| `auto_tuning_allowed` | `False` |
| `phase_12_forbidden` | **`True`** |

These flags are mirrored in `_safety_payload()` in both
`app/sim/simulated_capital_flow.py` and `app/sim/trade_ledger.py`,
and are re-asserted on every serialisation boundary
(`to_dict()` / `to_json()` / `safety_payload()`).

## 3. Relation to PR94 / PR95 / PR96 / PR97

PR98 strictly **consumes** the existing strict blind walk-forward
substrate. It does **NOT** modify any PR94..PR97 source.

  - **PR94 — SimulationClock + Time-Wall Guard.** PR98 timestamps
    every state / ledger / equity-timeseries output via
    `SimulationClock`-derived simulated time
    (`MockFill.filled_at_simulated`, explicit `simulated_time`
    inputs). PR98 NEVER consults the wall-clock. Every output
    serialised by PR98 is also passed through
    `assert_no_forbidden_fields` from PR94's time-wall guard.
  - **PR95 — Historical Market Store v0.** PR98 reads no market
    data directly; it consumes mark prices via
    `apply_mark_prices(...)` (explicit) or via
    `apply_replay_batch(batch)` which extracts the `close` of every
    visible 1m / 5m kline emitted by a `ReplayFeedBatch` — i.e.
    every mark obeys `available_at <= simulated_time` and
    closed-candle visibility by construction.
  - **PR96 — ReplayFeedProvider v0.** `apply_replay_batch(batch)`
    accepts a `ReplayFeedBatch` directly and uses its `klines_1m` /
    `klines_5m` close prices as marks. The batch's hard-pinned
    `phase_12_forbidden=True` / `auto_tuning_allowed=False` /
    `trade_authority=False` flags are mirrored in PR98's outputs.
  - **PR97 — MockExchange + Pessimistic Fill Model v0.** PR98's
    primary input is the :class:`MockFill` stream produced by
    :class:`MockExchange`. PR98 NEVER produces, signs, or transmits
    a real order. PR98 NEVER advertises a real exchange order id, an
    api key, an api secret, a real account id, or a signed-endpoint
    reference.

## 4. Files added by this PR

  - `app/sim/simulated_capital_flow.py`
    - `SimulatedCapitalConfig` (frozen dataclass)
    - `SimulatedPosition` (mutable dataclass)
    - `SimulatedCapitalState` (frozen dataclass)
    - `SimulatedCapitalFlowEngine` (engine)
    - `PositionSide`, `PositionStatus`, `RiskFreezeReason` (closed
      taxonomies)
    - `CapitalFrozenError` (raised on attempts to open a NEW
      simulated position while frozen)
  - `app/sim/trade_ledger.py`
    - `TradeLedgerEntry` (frozen dataclass)
    - `TradeLedger` (append-only ledger)
    - `TradeLedgerSummary` (frozen summary)
    - `EquityTimeseriesPoint` (frozen dataclass)
    - `TradeOutcome`, `TradeFailureFlag` (closed taxonomies)
  - `app/sim/__init__.py` — re-exports the above alongside the PR94
    / PR95 / PR96 / PR97 substrate.
  - `tests/unit/test_simulated_capital_flow_trade_ledger.py` — 26
    PASSING tests covering all 24 brief-mandated scenarios plus
    closed-taxonomy enforcement and phase-name-string presence.
  - `docs/PHASE_11C_1D_D_E_SIMULATED_CAPITAL_FLOW_TRADE_LEDGER.md`
    — this design / acceptance doc.

## 5. Files explicitly NOT touched

  - `app/risk/**`
  - `app/execution/**`
  - `app/exchanges/**`
  - `app/telegram/**`
  - `app/config/**`
  - `app/sim/simulation_clock.py` (PR94 — reused verbatim)
  - `app/sim/time_wall_guard.py` (PR94 — reused verbatim)
  - `app/sim/historical_market_store.py` (PR95 — reused verbatim)
  - `app/sim/replay_feed_provider.py` (PR96 — reused verbatim)
  - `app/sim/mock_exchange.py` (PR97 — reused verbatim)
  - `app/sim/pessimistic_fill_model.py` (PR97 — reused verbatim)
  - runtime config files
  - `symbol_limit`, anomaly thresholds, `candidate_pool`, regime
    weights

## 6. Public surface

### 6.1 `SimulatedCapitalConfig`

Frozen configuration:

  - `initial_capital` (float, > 0)
  - `base_currency` (str, default `"USDT"`)
  - `max_active_positions` (int, > 0)
  - `max_symbol_exposure_pct` (float, in (0, 1])
  - `max_regime_exposure_pct` (Optional[float], in (0, 1])
  - `single_trade_risk_budget_pct` (float, in (0, 1])
  - `profit_lock_fraction` (float, in [0, 1])
  - `locked_profit_reuse_allowed` (bool, default `False`)
  - `consecutive_loss_pause_threshold` (Optional[int], > 0)
  - `max_drawdown_pause_pct` (Optional[float], in (0, 1])
  - `paper_liquidation_stress_enabled` (bool, default `True`)
  - hard-pinned `sandbox_only=True`, `live_capital_enabled=False`

### 6.2 `SimulatedPosition`

Mutable dataclass with hard-pinned safety markers
(`simulated_only=True` / `no_live_order=True` /
`live_capital_enabled=False` / `phase_12_forbidden=True` /
`trade_authority=False` / `auto_tuning_allowed=False`).

Fields: `position_id`, `symbol`, `side` (LONG / SHORT, paper-only
descriptor), `qty`, `avg_entry_price`, `opened_at_simulated`,
`updated_at_simulated`, `realized_pnl`, `unrealized_pnl`,
`fees_paid`, `slippage_paid`, `funding_paid`, `status` (OPEN /
CLOSED), `evidence_refs`, `max_favorable_excursion`,
`max_drawdown_during_trade`.

`side` is a paper-only descriptor of the simulated position's
direction; it is **NEVER** an AI / strategy recommendation, **NEVER**
a trade authority signal, **NEVER** a runtime config patch.

### 6.3 `SimulatedCapitalState`

Frozen snapshot:

  - `timestamp`, `initial_capital`,
  - `exchange_equity`, `locked_profit`, `open_risk`,
    `unrealized_pnl`, `realized_pnl`, `total_lifetime_equity`,
    `drawdown`,
  - `active_positions` (count), `risk_state` (closed taxonomy),
    `capital_frozen` (bool), `freeze_reason` (Optional[str]).

`risk_state` and `freeze_reason` are drawn from the closed
`RiskFreezeReason` taxonomy (`NORMAL` /
`MAX_DRAWDOWN_EXCEEDED` / `CONSECUTIVE_LOSS_PAUSE` /
`LIQUIDATION_STRESS` / `MANUAL_FREEZE`).

### 6.4 `TradeLedgerEntry`

Frozen, JSON-serialisable:

  - `trade_id`, `symbol`,
  - `entry_time`, `exit_time`,
  - `entry_reason`, `exit_reason`, `regime_state`, `candidate_rank`,
    `risk_decision`,
  - `order_type`, `requested_qty`, `filled_qty`,
    `avg_fill_price`, `slippage_bps`, `fee`,
  - `max_drawdown_during_trade`, `max_favorable_excursion`,
  - `net_pnl`, `locked_profit_delta`,
  - `failure_flags` (closed `TradeFailureFlag` taxonomy),
  - `evidence_refs`, `outcome` (`WIN` / `LOSS` / `BREAKEVEN`),
  - hard-pinned safety markers.

### 6.5 `EquityTimeseriesPoint`

Frozen, JSON-serialisable: `timestamp`, `exchange_equity`,
`locked_profit`, `open_risk`, `unrealized_pnl`, `realized_pnl`,
`total_lifetime_equity`, `drawdown`, `active_positions`,
`risk_state`, plus hard-pinned safety markers.

### 6.6 `SimulatedCapitalFlowEngine`

Public methods:

  - `consume_fill(fill, *, evidence_refs, regime_state,
    candidate_rank, risk_decision)` — the primary entrypoint.
    Returns a `TradeLedgerEntry` if the fill fully closed a
    position; otherwise `None`.
  - `apply_mark_prices(mark_prices, simulated_time)` — update
    unrealised PnL and emit a fresh `EquityTimeseriesPoint`.
  - `apply_replay_batch(batch)` — extract close prices from a
    `ReplayFeedBatch` and call `apply_mark_prices`.
  - `apply_funding(symbol, funding_amount, simulated_time)` —
    apply a funding cash impact on an open simulated position.
  - `forced_exit(symbol, *, exit_price, simulated_time, fee,
    slippage_bps, evidence_refs)` — paper-only synthetic forced
    close producing a ledger entry tagged
    `FORCED_EXIT_TRIGGERED`.
  - `freeze_capital(reason)` / `unfreeze_capital()` —
    explicit freeze controls.
  - `get_state(simulated_time=None)`,
    `get_positions()`,
    `get_ledger()`,
    `get_equity_timeseries()`,
    `available_capital_for_new_exposure()`,
    `to_dict()`, `safety_payload()`.

The engine is deterministic: two engines fed identical fills /
mark-prices / config produce identical state / ledger / equity
timeseries.

## 7. Locked-profit rule

`locked_profit_reuse_allowed` defaults to `False`. When it is
`False` AND `profit_lock_fraction > 0`, the engine moves
`net_pnl * profit_lock_fraction` from `exchange_equity` into
`locked_profit` on every closed trade with `net_pnl > 0`. The
locked amount is recorded on the ledger entry as
`locked_profit_delta`.

`available_capital_for_new_exposure()` excludes `locked_profit`
when `locked_profit_reuse_allowed=False`, and includes it when
`True`. PR98 NEVER auto-applies the unlock; it is always a future
manual / config decision.

## 8. Drawdown / capital-freeze behaviour

  - `total_lifetime_equity` is the running peak of
    `exchange_equity + locked_profit + unrealized_pnl` over all
    observed events.
  - `drawdown` is the descriptive
    `(peak - current) / peak` (clipped to `>= 0`).
  - When `max_drawdown_pause_pct` is set and the observed drawdown
    meets / exceeds it, the engine sets `capital_frozen=True` with
    `freeze_reason=MAX_DRAWDOWN_EXCEEDED`.
  - When `consecutive_loss_pause_threshold` is set and the running
    streak of LOSS trades meets it, the engine freezes with
    `freeze_reason=CONSECUTIVE_LOSS_PAUSE`.
  - While frozen, attempting to open a NEW simulated position
    raises `CapitalFrozenError`. Reductions / closes / forced exits
    on existing positions remain allowed.
  - `freeze_capital(reason)` / `unfreeze_capital()` are the manual
    controls. `MANUAL_FREEZE` and `LIQUIDATION_STRESS` are not
    auto-cleared.

PR98 NEVER mutates a runtime config and NEVER authorises live
trading. Freeze is a paper-only descriptive flag.

## 9. Fee / slippage / funding accounting

  - On every fill (open / increase / reduce / close), the engine
    deducts `fill.fee` from `exchange_equity` (cash impact of fee).
  - The engine tracks `slippage_paid` per position descriptively as
    `fill_price * filled_qty * slippage_bps / 10000`. This is a
    descriptive figure; PnL is computed from `fill_price` only (the
    pessimistic adverse fill from PR97 already encodes the slippage).
  - On reduce / close fills, the engine credits gross PnL
    (`(exit - entry) * qty * (+1 LONG / -1 SHORT)`) to
    `exchange_equity` and deducts the close fee. Net PnL on the
    ledger entry equals
    `realized_pnl_gross - sum(fees over both legs) + sum(funding)`.
  - `funding_impact` on a fill (or a separate
    `apply_funding(...)` call) is added to `exchange_equity` and to
    the position's `funding_paid`. Funding flows into the ledger
    entry's `net_pnl`.

## 10. No real account access / no live order path

PR98 is paper-only:

  - It NEVER imports `app.risk`, `app.execution`, `app.exchanges`,
    `app.telegram`, or `app.config`.
  - It NEVER imports `deepseek`, `openai`, `anthropic`,
    `telegram`, `binance`, `ccxt`, `httpx`, `aiohttp`,
    `requests`, `urllib.request`, `socket`, `grpc`, `boto3`, or
    any websocket transport.
  - It NEVER produces a real exchange order id, a real account id,
    an api key, an api secret, a signed-endpoint reference, or a
    listenKey.
  - It NEVER calls `place_order`, `place_real_order`,
    `sign_request`, `sign`, `open_websocket`, `private_websocket`,
    `listen_key`, `set_leverage`, `apply_change`, `deploy`,
    `enable_live`, `fetch_account`, `fetch_position`, or
    `fetch_balance`.
  - Every `to_dict()` / `to_json()` / `safety_payload()` boundary
    is run through `assert_no_forbidden_fields`. The forbidden field
    set is the project-wide :data:`FORBIDDEN_OUTPUT_FIELDS` plus the
    explicit list (`runtime_config_patch`, `symbol_limit_patch`,
    `threshold_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, `strategy_parameter_patch`,
    `apply_change`, `deploy_change`, `enable_live`, `live_ready`,
    `trading_approved`, `real_order_id`, `exchange_order_id`,
    `real_account_id`, `api_key`, `api_secret`).

## 11. What PR98 does NOT do

PR98 does **NOT** implement the **Telegram Sandbox Outbox** (PR99).
PR98 does **NOT** implement the **Blind Walk-forward Runner**
(PR100). PR98 does **NOT** authorise live trading. PR98 does **NOT**
authorise auto-tuning. PR98 does **NOT** authorise Phase 12. **Phase
12 remains FORBIDDEN.**

The Risk Engine remains the single trade-decision gate.

## 12. Tests

```
python -m pytest tests/unit/test_simulated_capital_flow_trade_ledger.py -q
# 26 PASSED
python -m pytest tests/unit -q
# 3530 PASSED, 0 failures (was 3504 before this phase; +26 from
# this phase)
```

The 26 PR98 tests cover:

  1. initialises capital state from `initial_capital`,
  2. mock fill opens simulated position (BUY -> LONG, SELL -> SHORT),
  3. opposite-side fill reduces / closes position,
  4. fees / slippage reduce equity,
  5. realised PnL is deterministic across two runs,
  6. unrealised PnL updates from mark price (explicit + replay batch),
  7. open_risk updates with active positions,
  8. drawdown updates from equity timeseries,
  9. locked_profit is not reused when
     `locked_profit_reuse_allowed=False`,
 10. capital freezes after configured drawdown threshold (and
     refuses new opens with `CapitalFrozenError`),
 11. forced exit produces ledger entry tagged
     `FORCED_EXIT_TRIGGERED`,
 12. funding impact is applied (cash + position bookkeeping +
     ledger `net_pnl`),
 13. trade ledger appends and summarises entries deterministically
     (with symbol query and time-range query),
 14. equity timeseries point JSON serialisable (round-trip),
 15. all outputs `simulated_only=True` / `no_live_order=True`,
 16. `phase_12_forbidden=True`,
 17. `auto_tuning_allowed=False`,
 18. `trade_authority=False` (and `ai_trade_authority=False`),
 19. `live_capital_enabled=False`,
 20. forbidden fields absent from serialised outputs,
 21. module does not import
     `app.risk` / `app.execution` / `app.exchanges` /
     `app.telegram` / `app.config`,
 22. no DeepSeek / LLM / Telegram / Binance / network call path,
 23. no real account / signed endpoint / API key / listenKey
     fields,
 24. deterministic output across two independent runs,
 plus closed-taxonomy enforcement and phase-name-string presence.

## 13. Successor allowed by this phase

A successful PR98 only authorises **PR99 — Telegram Sandbox Outbox
v0** to begin its own gate. It does **NOT** authorise:

  - the **Blind Walk-forward Runner** (PR100),
  - **Phase 12** (FORBIDDEN),
  - **live trading**,
  - **auto-tuning**,
  - real Telegram outbound,
  - real Binance private API access,
  - any runtime config write.

The Risk Engine remains the single trade-decision gate.
