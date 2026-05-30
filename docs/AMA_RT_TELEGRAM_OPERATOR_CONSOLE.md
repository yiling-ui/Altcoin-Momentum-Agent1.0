# AMA-RT Telegram Operator Console (PR114)

> **PR114 — Telegram Operator Console v0 + Live Funding Attribution +
> Operator Workflow + Blind/Replay/Sim Isolation.**
> **Status: IN_REVIEW.**
> **Type: real Telegram operator desk (gated outbound) — real order code
> still BLOCKED by default; the console can NEVER place a naked order.**

PR114 gives the operator a real Telegram operating desk so they can see
the system, switch 空盘跑 / 有资金跑, view account / positions / PnL /
risk, and receive readable operator cards — **without ever bypassing the
Risk Engine, the Execution Gateway, the Capital Profile, or the kill
switch**. It also adds the first version of account-level funding /
commission attribution to the live order / position / trade ledger so
live PnL never silently ignores funding paid while a position was held.

> **This is not the final 10U launch.** Live trading does not begin until
> the launch PR (PR116) explicitly clears the stage docs. PR114 keeps
> `live_trading=false`, `exchange_live_orders=false`,
> `trade_authority=false`, `ai_trade_authority=false`,
> `runtime_mode=LIVE_SHADOW`, and `phase_12_forbidden=true` by default.

---

## 1. 空盘跑 vs 有资金跑 (LIVE_SHADOW vs LIVE_LIMITED)

| | 空盘跑 / `LIVE_SHADOW` | 有资金跑 / `LIVE_LIMITED` |
| --- | --- | --- |
| Real capital at risk | **never** | only after every gate passes |
| Reads live market / account | yes | yes |
| Produces a plan + card | yes (`SHADOW_*`) | yes (`LIVE_*`) |
| `real_order` | always `false` | `false` until a real fill lands |
| Default | **yes** | never the default; never on bare restart |

These two are **never** mixed. `LIVE_SHADOW` can never move real
capital; `LIVE_LIMITED` is the only mode that ever could (in a future
launch PR), and only behind the operator confirmation handshake.

`/status` always shows the current source as `LIVE_SHADOW` or
`LIVE_LIMITED` — never silently mixed with `SIM` / `BLIND` / `REPLAY` /
`PAPER_SHADOW`.

---

## 2. Command list

| Command | Effect |
| --- | --- |
| `/help` | Available commands + current mode. |
| `/status` | Runtime mode, capital profile, all safety flags, API health (if cached), kill-switch state, open-position count, equity (if available). |
| `/mode` | Show current mode + whether real orders are allowed. |
| `/mode shadow` | Switch back to `LIVE_SHADOW`; disarm `LIVE_LIMITED`; `real_order=false`. Writes `LIVE_MODE_CHANGED`. |
| `/mode live_limited` | **Does not switch.** Returns a risk summary + a confirmation code. Writes `LIVE_MODE_SWITCH_REQUESTED`. |
| `/confirm_live CODE` | Arm `LIVE_LIMITED` iff the code matches + is not expired + the profile allows real orders + `LIVE_LIMITED` is in the profile's allowed modes + the kill switch is not active. Writes `LIVE_LIMITED_ARMED` / `LIVE_MODE_SWITCH_REJECTED`. |
| `/positions` | Per-position symbol / side / size / entry / mark / uPnL / notional / leverage / liquidation / funding attribution status. |
| `/pnl` | gross realized PnL, commission, funding, net strategy PnL, unrealized, deposits, withdrawals, adjusted equity, funding attribution status. |
| `/risk` | Capital profile, max account capital, used profile capital, max position notional, max leverage, daily / total loss state, risk-halt, kill-switch state. |
| `/capital` | Wallet / available / equity, external deposits / withdrawals, profit harvest / rebase (if available), profile-mismatch warning. |
| `/profile` | Current profile + recommended profile (deterministic, from equity). |
| `/profile set <PROFILE_ID>` | Request a profile change. A **higher-risk** profile requires an explicit confirmation token (`/profile set L3_... confirm`). Writes `CAPITAL_PROFILE_CHANGED` / `PROFILE_CHANGE_REJECTED`. |
| `/pause` | Pause **new** entries (existing positions are not force-closed). Writes `LIVE_PAUSED`. |
| `/resume` | Resume scanning / new signals — **does not** bypass mode / risk / order gates. Writes `LIVE_RESUMED`. |
| `/kill_all` | High-risk. Returns a confirmation code. Writes `LIVE_KILL_SWITCH_ARM_REQUESTED`. |
| `/confirm_kill CODE` | Arm the kill switch (and pause). If a controlled cancel/exit callback is wired, it MUST route through the PR113 execution gateway + safety gate. Writes `LIVE_KILL_SWITCH`. |

Every command writes an audit event (`TELEGRAM_COMMAND_RECEIVED`, plus
the command-specific event). Unauthorised commands write
`TELEGRAM_UNAUTHORIZED_COMMAND`.

---

## 3. Configuring the bot token + allowed chat ids

Set these environment variables (never commit them):

```
AMA_TELEGRAM_BOT_TOKEN=<bot token from @BotFather>
AMA_TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
AMA_TELEGRAM_OUTBOUND_ENABLED=false   # keep false until you are ready
```

- The token is held as a `SecretValue`; it never appears in logs, repr,
  events, or any outbound message body (the redactor scrubs it).
- **Only** chat ids in `AMA_TELEGRAM_ALLOWED_CHAT_IDS` may run a command.
  An **empty** allow-list authorises **nobody** (fail closed).
- A command from an unauthorised chat id is refused and recorded as
  `TELEGRAM_UNAUTHORIZED_COMMAND`.

---

## 4. How mode switching works

```
/mode live_limited
   → returns CONFIRMATION CODE + risk summary (mode unchanged)
/confirm_live <CODE>
   → arms LIVE_LIMITED iff: code matches + not expired (5 min TTL)
                          + profile allows real orders
                          + LIVE_LIMITED is in profile.mode_allowed
                          + kill switch not active
   → writes LIVE_LIMITED_ARMED + LIVE_MODE_CHANGED
```

`/mode shadow` always returns to `LIVE_SHADOW` and disarms
`LIVE_LIMITED`. A fresh confirmation handshake is required to re-arm.

---

## 5. Why LIVE_LIMITED needs confirmation

Arming `LIVE_LIMITED` is the boundary between *empty-account* and
*funded* operation. A two-step handshake (request → confirm with a
one-time code) makes the switch deliberate and auditable, and prevents a
single fat-fingered command (or a replayed message) from arming a funded
mode. The persisted confirmation record is also what allows an armed
`LIVE_LIMITED` to survive a restart — without it, the state store fails
safe to `LIVE_SHADOW`.

---

## 6. Why Telegram cannot bypass risk / execution gateway

Arming `LIVE_LIMITED` does **not** by itself enable real orders. A real
order still requires, independently of Telegram:

- `exchange_live_orders=true` **and** `trade_authority=true` **and**
  Binance private trade enabled by config, **and**
- a `LiveRiskDecision` that is `approved` with `real_order_allowed=true`,
  **and**
- passing the PR113 `evaluate_execution_permission` 15-point gate,
  **and** `source=OrderSource.LIVE`, **and** the kill switch off.

The operator console exposes **no** path that flips
`exchange_live_orders` / `trade_authority`, and holds **no** Binance
execution adapter. It can only *reflect* those flags (`/status`,
`/mode`). `ai_trade_authority` is always `false` — AI never places an
order and an AI / offline source can never run a state-changing command.

---

## 7. Card examples

**SHADOW_ENTRY_PLAN** (空盘跑):

```
[ama-rt:live:SHADOW_ENTRY_PLAN] mode=空盘跑 symbol=RAVEUSDT side=LONG
planned_entry_price=0.5 planned_stop_price=0.45 planned_take_profit_1=0.6
planned_leverage=3 real_order=False
```
Fields: candidate_stage, opportunity_score, planned_entry_zone,
planned_entry_price, planned_stop_price, planned_take_profit_1/2,
planned_notional_usdt, planned_leverage, risk_decision, `real_order=false`,
`order_id=--`, `real_capital_changed=false`, event_id.

**LIVE_ENTRY_FILLED** (有资金跑): event=`LIVE_ORDER_FILLED`, symbol, side,
leverage, entry_price, quantity, notional_usdt, fee_usdt,
funding_usdt_so_far, order_id, client_order_id, account balance, risk_decision,
event_id.

**LIVE_EXIT_FILLED** (有资金跑): symbol, side, entry/exit time + price,
quantity, leverage, **gross_pnl**, **commission_total**,
**funding_fee_or_income**, **net_pnl**, **pnl_pct**, balance_after,
exit_reason, order_id / client_order_id, funding_attribution_status, event_id.

**LIVE_RISK_REJECT / LIVE_EXECUTION_BLOCKED**: symbol, planned_notional,
planned_leverage, reject_reason, max_allowed_notional, max_allowed_leverage,
runtime_mode, profile, `real_order=false`, event_id.

**LIVE_PNL_SUMMARY**: gross_realized_pnl, commission_total, funding_total,
net_strategy_pnl, unrealized_pnl, deposits, withdrawals, adjusted_equity,
funding_attribution_status.

**CAPITAL_EVENT_DETECTED**: event_type, amount, balance_before/after,
is_trading_pnl, is_external_capital_flow, affects_performance_stats,
explanation (deposit is **not** strategy profit; withdrawal is **not**
strategy loss).

---

## 8. Funding fee / commission display in PnL

`net_pnl = gross_realized_pnl − commission + funding`.

- Funding **income** is positive; funding **fee** paid is negative.
- The exit card and `/pnl` always display gross_pnl, commission, funding,
  and net_pnl together — funding is never hidden.
- A funding row whose time falls inside a held position interval is
  attributed to that trade / position; a row outside any interval stays
  account-level; a row over multiple overlapping same-symbol positions is
  marked `AMBIGUOUS_MULTIPLE_POSITIONS` and allocated deterministically by
  notional. No funding event is ever dropped. See
  `docs/AMA_RT_LIVE_CAPITAL_RISK_PNL.md` §Funding attribution.

---

## 9. Kill switch workflow

```
/kill_all
   → returns KILL confirmation code (kill switch NOT yet armed)
/confirm_kill <CODE>
   → arms the kill switch + pauses new entries (writes LIVE_KILL_SWITCH)
```

PR114 implements kill-switch arming + the operator card. If a controlled
cancel/exit path is wired (a later PR), it MUST go through the PR113
`LiveExecutionGateway` and its safety gate — the console never cancels or
exits directly.

---

## 10. Blind / Replay / Sim Isolation

Blind / replay / sim / paper-shadow / backtest / offline-AI /
telegram-sandbox code is retained **only** for research and offline
validation. It is **not** part of live trading authority:

- It cannot change live mode, live profile, live risk, or live execution.
- A non-`LIVE` source attempting a state-changing command is refused and
  recorded as `LIVE_SOURCE_REJECTED`.
- A non-`LIVE` order intent reaching the order gateway is refused and
  recorded as `LIVE_PATH_BLOCKED` (PR110 guard).
- `/status` shows the current source only as `LIVE_SHADOW` / `LIVE_LIMITED`.

Live system decisions come only from live-approved adapters (Binance
public live market, Binance private read, `LiveCapitalState`,
`LiveRiskDecision`, `LiveExecutionGateway`, the Telegram operator
console, and DeepSeek market-intelligence-only with live-safe evidence)
and deterministic live risk / capital gates.

---

## 11. CLI

```
python scripts/live_telegram_operator.py --status-json
python scripts/live_telegram_operator.py --send-test
python scripts/live_telegram_operator.py --dry-run --once
python scripts/live_telegram_operator.py --poll
python scripts/live_telegram_operator.py --command "/status"
```

Defaults: no real order, no live-mode switch without confirmation, no
unauthorised chat control, outbound suppressed unless
`AMA_TELEGRAM_OUTBOUND_ENABLED=true` and `--dry-run` is not set.

---

## 12. Persistent state

File-based, under `data/live_state/` (git-ignored):

| File | Content |
| --- | --- |
| `runtime_mode.json` | mode + `live_limited_armed` + `paused` |
| `telegram_confirmation_state.json` | pending / completed confirmation handshakes |
| `capital_profile_state.json` | active capital profile id |
| `kill_switch_state.json` | kill-switch armed flag |

Writes are atomic. The default is `LIVE_SHADOW` when a file is missing.
A corrupt file fails safe to `LIVE_SHADOW` with a warning. An armed
`LIVE_LIMITED` with no completed confirmation record fails safe to
`LIVE_SHADOW`.

---

## 13. Current stage

PR114 is **IN_REVIEW**. This is **not** the final 10U launch. Real
trading remains blocked by default until the launch PR (PR116) explicitly
updates the stage docs.
