# AMA-RT Live Operator Runbook (PR114)

> **Status: PR114 IN_REVIEW.** Operator-facing runbook for the live
> Telegram operating desk. **This is not the final 10U launch** — real
> trading remains blocked by default until the launch PR (PR116) updates
> the stage docs.

This runbook is the step-by-step guide for an operator running the live
console. It assumes PR110–PR113 are in place (live path isolation,
runtime mode guard, capital profile ladder, API integration, live
capital / risk, and the execution gateway).

---

## 1. Definitions

- **空盘跑 / `LIVE_SHADOW`** — empty-account run. Reads live data,
  produces plans + cards, never moves real capital. **Default.**
- **有资金跑 / `LIVE_LIMITED`** — funded run. Real small-capital trading
  is permitted *in principle*, only after the confirmation handshake AND
  all execution-gate flags are set. Never the default; never on a bare
  restart.

---

## 2. First-time setup

1. Create a Telegram bot via @BotFather; copy the bot token.
2. Find your numeric chat id (e.g. via @userinfobot).
3. Export the environment (never commit):

   ```
   AMA_TELEGRAM_BOT_TOKEN=<token>
   AMA_TELEGRAM_ALLOWED_CHAT_IDS=<your_chat_id>
   AMA_TELEGRAM_OUTBOUND_ENABLED=false
   ```

4. Confirm the console is safe:

   ```
   python scripts/live_telegram_operator.py --status-json
   ```

   You should see `runtime_mode=LIVE_SHADOW`, `no_real_order_sent=true`,
   and every `*_flag` false.

---

## 3. Daily operation (空盘跑)

- `/status` — confirm mode, profile, safety flags, kill switch.
- `/positions` — review open positions + funding attribution status.
- `/pnl` — gross / commission / funding / net PnL.
- `/risk` — profile limits + loss state.
- `/capital` — wallet / equity + external flows + mismatch warning.

In `LIVE_SHADOW`, every plan card shows `real_order=false` and
`order_id=--`. Nothing moves real capital.

---

## 4. Moving to 有资金跑 (LIVE_LIMITED)

> Only do this when you have explicitly decided to fund the account AND
> the launch stage permits real orders.

1. Select a funded profile (escalation needs confirmation):

   ```
   /profile set L1_10U_PROBE confirm
   ```

2. Request the switch (returns a code + risk summary — mode unchanged):

   ```
   /mode live_limited
   ```

3. Confirm within 5 minutes:

   ```
   /confirm_live <CODE>
   ```

`LIVE_LIMITED` is now **armed**, but **real orders are still blocked**
unless `exchange_live_orders`, `trade_authority`, and Binance private
trade are separately enabled in config AND every PR113 gate passes. The
console cannot set those flags.

To return to safety at any time:

```
/mode shadow
```

---

## 5. Pause / resume

- `/pause` — stop opening **new** positions. Existing positions are not
  force-closed.
- `/resume` — resume scanning. Does **not** bypass mode / risk / order
  gates.

---

## 6. Emergency: kill switch

```
/kill_all          → returns a KILL code (not yet armed)
/confirm_kill CODE → arms the kill switch + pauses new entries
```

PR114 arms the kill switch and alerts. A controlled cancel/exit (if
wired in a later PR) routes through the PR113 execution gateway + safety
gate. While the kill switch is armed, `/confirm_live` is refused.

---

## 7. Reading the cards

- 空盘跑 plan: `SHADOW_ENTRY_PLAN` / `SHADOW_EXIT_PLAN` — planned
  entry/stop/take-profit, `real_order=false`.
- 有资金跑 fills: `LIVE_ORDER_FILLED` / `LIVE_EXIT_FILLED` — actual
  entry/exit, fee, funding, gross/net PnL, pnl_pct, balance after.
- Rejections: `LIVE_RISK_REJECT` / `LIVE_EXECUTION_BLOCKED` — reject
  reason + the profile max ceilings.
- Capital events: `CAPITAL_EVENT_DETECTED` — a deposit is **not**
  strategy profit; a withdrawal is **not** strategy loss.
- Funding: `FUNDING_EVENT_ATTRIBUTED` — attributed vs account-level vs
  ambiguous funding.

---

## 8. Funding / commission in PnL

`net_pnl = gross_realized_pnl − commission + funding`. Funding income is
positive; funding fee is negative. The exit card and `/pnl` always show
all four numbers. Funding is attributed to a trade / position when its
timestamp falls inside the holding interval; otherwise it stays
account-level; overlapping same-symbol positions are marked ambiguous and
allocated deterministically by notional. No funding event is dropped.

---

## 9. Blind / Replay / Sim Isolation

- Blind / replay / sim / paper-shadow / backtest / offline-AI /
  telegram-sandbox code is retained **only** for research and offline
  validation. It is **not** part of live trading authority.
- It cannot change live mode, live profile, live risk, or live execution.
- A non-`LIVE` source attempting any live mutation is refused and
  recorded as `LIVE_SOURCE_REJECTED`; a non-`LIVE` order intent reaching
  the gateway is refused as `LIVE_PATH_BLOCKED`.
- Live decisions come only from live-approved adapters and deterministic
  live risk / capital gates.

---

## 10. Safety defaults (must stay this way until launch)

```
phase_12_forbidden     = true
live_trading           = false
exchange_live_orders   = false
trade_authority        = false
ai_trade_authority     = false
runtime_mode           = LIVE_SHADOW
```

PR114 is **IN_REVIEW**. The 10U launch is not live until the launch PR
(PR116) explicitly changes the stage docs.
