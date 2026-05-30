# AMA-RT Live Foundation v0 Spec (PR110)

> **Status: IN_REVIEW.** This document describes the live-preparation
> safety foundation introduced by PR110. It is the authoritative
> contract for `app/live/`.

> **PR112 follow-on (IN_REVIEW):** PR112 builds the read-only live
> capital / risk layer on this foundation — `LiveCapitalState` from the
> PR111 private read, funding-aware PnL
> (`net = realized − commission + funding`, deposits/withdrawals kept out
> of strategy PnL), `L1_10U_PROBE` enforcement (usable capital capped at
> 10U, no auto-escalation), and a deterministic *dry* live order risk
> pre-check (`real_order_allowed=false`). The hard safety boundary below
> is unchanged. See `docs/AMA_RT_LIVE_CAPITAL_RISK_PNL.md`.

## What AMA-RT is

AMA-RT V1.4 is a crypto altcoin **right-tail capture / adaptive market
operating system** — not a low-volatility annualised-return trading
bot. The objective is short-horizon high return: capture "demon coin"
right tails and rapidly amplify small capital, while strict risk
control prevents systemic loss of control.

The roadmap has switched from large-scale cloud blind testing
(uneconomic data ingestion on the current server; the Kiro
subscription is ending) to a **10U small-capital live-preparation**
posture. PR110 builds the hard pre-live boundaries.

## PR110 explicitly does NOT (read this first)

1. **PR110 does not enable live trading.**
2. **PR110 does not connect the Binance private API.**
3. **PR110 does not place (or cancel) any order.**
4. **PR110 does not enable Telegram outbound.**
5. **PR110 only creates the live safety foundation.**
6. **The blind / replay / sim path is locked away from live.**
7. **LIVE_SHADOW and LIVE_LIMITED are different and must never be
   confused.**
8. **Capital must scale through profiles from 1U to 10,000,000U** — the
   10U method is never re-used at every scale.
9. **Deposits and withdrawals must not pollute strategy PnL.**
10. **Leverage boost is deterministic and profile-bound, not
    AI-driven.**

## Hard safety boundary

```
phase_12_forbidden            = True
live_trading                  = False   (by default)
exchange_live_orders          = False   (by default)
binance_private_api_enabled   = False   (by default)
telegram_outbound_enabled     = False   (by default)
ai_trade_authority            = False
trade_authority               = False   (by default)
right_tail_live_boost_enabled = False   (by default)
```

The five Phase 1 safety flags (`trading_mode=paper`,
`live_trading_enabled=False`, `right_tail_enabled=False`,
`llm_enabled=False`, `exchange_live_order_enabled=False`) remain locked
across PR110. The `live:` config section
(`app/config/schema.py::LiveConfig`) refuses at boot to load any of the
capability flags above as `True`, and refuses `phase_12_forbidden=False`.

## Components

### 1. Live Path Isolation (`app/live/path_isolation.py`, `app/live/gateway.py`)

Every order intent carries an `OrderSource`
(`SIM` / `BLIND` / `REPLAY` / `PAPER_SHADOW` / `LIVE`). The historical
/ blind / replay / simulated / paper-shadow stack — SimulationClock,
HistoricalMarketStore, ReplayFeedProvider, MockExchange,
SimulatedCapitalFlow, Telegram Sandbox Outbox, Blind Walk-forward
Runner, Paper Shadow Strategy Bridge, Core Strategy Sim-Live Bridge —
may continue to exist for testing, but may **never** reach a live
order gateway.

- `LivePathIsolationGuard.authorize(intent)` returns an
  `IsolationDecision`; only `OrderSource.LIVE` is admissible.
- `LivePathIsolationGuard.assert_live_path(intent)` raises
  `LivePathIsolationViolation` and emits a `LIVE_PATH_BLOCKED` event
  for any non-LIVE source.
- `classify_source_module(name)` is fail-safe: an unknown / simulation
  module name maps to a blocked source (`SIM` / `BLIND` / `REPLAY` /
  `PAPER_SHADOW`), **never** `LIVE`.
- `LiveExecutionGateway.submit_order(intent)` is the single reserved
  entry point for the (future) live path. In PR110 it refuses every
  submission: non-LIVE source → `LivePathIsolationViolation`; LIVE but
  mode not armed → `LiveModeViolation`; LIVE + armed → `SafeModeViolation`
  (no execution adapter exists).

### 2. Runtime Mode Guard (`app/live/runtime_mode.py`)

See `docs/AMA_RT_LIVE_MODE_AND_CAPITAL_PROFILE.md`.

### 3. Capital Profile Ladder (`app/live/capital_profile.py`)

See `docs/AMA_RT_LIVE_MODE_AND_CAPITAL_PROFILE.md`.

### 4. Capital Event Contract (`app/live/capital_event.py`)

`CapitalEventType` classifies every real balance change:
`EXTERNAL_DEPOSIT`, `EXTERNAL_WITHDRAWAL`, `REALIZED_PNL`,
`REALIZED_LOSS`, `FEE`, `FUNDING_FEE`, `FUNDING_INCOME`,
`MANUAL_ADJUSTMENT`, `TRANSFER_IN`, `TRANSFER_OUT`, `PROFIT_HARVEST`,
`CAPITAL_REBASE`.

`CapitalEventLedger` keeps trading PnL strictly separate from external
flows and fees/funding:

- a deposit is **never** counted as strategy profit;
- a withdrawal is **never** counted as strategy loss;
- fees / funding are tracked in their own accumulators;
- capital-profile selection uses the *adjusted* equity, with
  `net_strategy_pnl` available so the operator can see strategy
  performance with external flows removed.

### 5. Right-tail Leverage Gate (`app/live/leverage_gate.py`)

`evaluate_right_tail_leverage_permission(evidence)` is a pure,
deterministic function. Inputs are deterministic evidence + the capital
profile + the runtime mode + the risk state ONLY.

Constitution:
- 没有浮盈不准疯狗 — no floating profit, no dog-pile boost.
- 没有退出通道不准重拳 — no exit channel, no heavy fist.
- 没有结构确认不准幻想 — no structure confirmation, no fantasy.
- AI 不得决定杠杆 — AI must not decide leverage.

Rejects: AI / LLM / Telegram / blind / future-label input
(`AI_INPUT_FORBIDDEN`), missing exit plan, missing stop plan, missing
liquidity evidence, risk-off regime, systemic risk, account drawdown
warning, risk halt, profile-disallows-boost, no-floating-profit boost
requests, slippage / spread over threshold, symbol exposure over
threshold, and leverage over the profile max. Grants a limited boost
(e.g. RAVE-like strong right tail) only when deterministic structure
strength + the profile both permit it; every boost grant carries
`requires_operator_ack=True`.

Output: `leverage_allowed`, `leverage_ratio`, `max_allowed_leverage`,
`reject_reason` (+ `reject_reasons`), `evidence_refs`,
`requires_operator_ack`.

### 6. Telegram Operator Contract (`app/live/telegram_operator_contract.py`)

Command contract: `/mode`, `/mode shadow`, `/mode live_limited`,
`/confirm_live CODE`, `/capital_profile`, `/capital_profile set <ID>`,
`/risk`, `/positions`, `/pnl`, `/pause`, `/resume`, `/kill_all`.

Card types: `SHADOW_ENTRY_PLAN`, `SHADOW_EXIT_PLAN`,
`SHADOW_RISK_REJECT`, `LIVE_ENTRY_SUBMITTED`, `LIVE_ENTRY_FILLED`,
`LIVE_EXIT_SUBMITTED`, `LIVE_EXIT_FILLED`, `LIVE_RISK_REJECT`,
`LIVE_ACCOUNT_HALTED`, `LIVE_KILL_SWITCH`, `LIVE_MODE_CHANGED`,
`CAPITAL_PROFILE_CHANGED`, `CAPITAL_EVENT_DETECTED`.

Card schema: common fields (`mode_display` 空盘跑/有资金跑,
`runtime_mode`, `capital_profile_id`, `symbol`, `side`,
`candidate_stage`, `opportunity_score`, `risk_decision`, `event_id`,
`opportunity_id`, `timestamp`) + planned fields (`planned_entry_zone`,
`planned_entry_price`, `planned_stop_price`, `planned_take_profit_1`,
`planned_take_profit_2`, `planned_exit_reason`,
`planned_notional_usdt`, `planned_leverage`) + real-order fields
(`order_id`, `client_order_id`, `entry_order_id`, `exit_order_id`,
`fill_price`, `entry_price`, `exit_price`, `quantity`,
`notional_usdt`, `leverage`, `fee_usdt`, `slippage_bps`,
`realized_pnl_usdt`, `pnl_pct`, `balance_before`, `balance_after`,
`equity_after`).

- **空盘跑 (shadow):** `real_order=False`, `real_capital_changed=False`,
  `order_id="--"`, every real-order field is `"--"`, but the planned
  fields are fully populated.
- **有资金跑 (funded):** the schema carries the real entry / exit / pnl
  / balance fields, the `risk_decision` and the kill-switch state.
  `real_order` only ever becomes `True` once a real execution adapter
  exists; PR110 has no adapter, so `real_order` is forced `False`.

## Audit events (PR110)

`LIVE_PATH_BLOCKED`, `LIVE_MODE_SWITCH_REQUESTED` / `_CONFIRMED` /
`_REJECTED`, `LIVE_LIMITED_ARMED` / `_DISARMED`, `LIVE_SHADOW_ACTIVE` /
`LIVE_LIMITED_ACTIVE`, `CAPITAL_EVENT_CLASSIFIED`,
`CAPITAL_PROFILE_CHANGED`, `CAPITAL_PROFILE_MISMATCH_DETECTED`,
`RIGHT_TAIL_LEVERAGE_EVALUATED`. None of these authorises a real trade,
moves real capital, or flips a Phase 1 safety flag.

## Out of scope (forbidden in PR110)

Real Binance order endpoint; real API key / secret; real Telegram
outbound; real order placement / cancellation; leverage / margin-mode
changes; Phase 12; AI deciding direction / size / leverage / stop /
target / exit; Telegram commands bypassing the Risk Engine; blind /
replay / sim modules influencing live execution; automatic capital
profile escalation; auto-entry into LIVE_LIMITED on restart; auto-tuning
from blind / replay results; any future label / MFE / MAE /
`completed_tail_label` influencing a live decision.
