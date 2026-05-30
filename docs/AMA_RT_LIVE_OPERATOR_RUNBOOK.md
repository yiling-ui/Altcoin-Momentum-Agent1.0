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

The kill switch has two distinct states:

- **ready / available** — the subsystem exists, its persisted state is
  readable, and the operator can trigger it. This is the normal state and
  is a launch-readiness requirement.
- **active (emergency halt)** — the switch has been triggered; every new
  entry is blocked.

```
/kill_status       → shows ready / active / blocks_new_entries
/kill_all          → returns a KILL code (not yet active)
/confirm_kill CODE → ACTIVATES the kill switch + pauses new entries
```

`/kill_all` → `/confirm_kill CODE` arms the kill switch into the **active**
state and alerts. A controlled cancel/exit (if wired in a later PR) routes
through the PR113 execution gateway + safety gate. While the kill switch is
**active**, `/confirm_live` is refused. LIVE_LIMITED never requires the kill
switch to be active — it only requires the kill switch to be **ready** and
**not active**.

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


---

## 11. AI briefings (PR115 — DeepSeek Live Intelligence v0)

PR115 connects DeepSeek to the operator workflow **only** as market
intelligence. The AI summarises live-approved evidence, compresses it into
a readable briefing, explains live risk, and can push the briefing to
Telegram. **The AI has no trade authority** and cannot decide direction /
size / leverage / stop / take-profit / target / order, cannot call the
execution gateway, cannot change mode / profile / risk, and cannot use
blind / replay / sim evidence. See
`docs/AMA_RT_DEEPSEEK_LIVE_INTELLIGENCE.md`.

Enable DeepSeek (optional; safe to leave off):

```
AMA_DEEPSEEK_API_KEY=<key>      # held masked; Authorization header only
AMA_DEEPSEEK_ENABLED=true
```

CLI (never submits orders, never switches mode / profile, never calls the
execution gateway, masks secrets):

```
python scripts/live_ai_briefing.py --status-json
python scripts/live_ai_briefing.py --brief --json
python scripts/live_ai_briefing.py --brief --dry-run
python scripts/live_ai_briefing.py --validate-output sample.json
```

If the DeepSeek key is missing or disabled the briefing returns
`MISSING_SECRET` / `DISABLED` rather than crashing. Telegram AI commands
(`/ai_status`, `/brief`, `/explain_risk`, `/explain_position <SYMBOL>`,
`/summarize_pnl`, `/summarize_rejections`) return informational cards only
(`ai_trade_authority=false`, `no_order_instruction=true`). The 10U live
launch still requires **PR116**.


---

# PR116 — 10U LIVE_LIMITED Launch Runbook

This is the final live operator runbook. The full launch-pack reference is
`docs/AMA_RT_10U_LIVE_LIMITED_LAUNCH_PACK.md`. Default behaviour stays safe:
`LIVE_SHADOW`, no real orders, no trade authority, no AI trade authority.

## Configure API keys

  - Set `AMA_BINANCE_API_KEY` / `AMA_BINANCE_API_SECRET` from a key that
    has **futures trade** but **no withdraw** permission.
  - Set `AMA_BINANCE_ENABLE_PRIVATE_READ=true` to read the account.
  - Keep `AMA_BINANCE_ENABLE_PRIVATE_TRADE=false` until Phase D.
  - Set `AMA_TELEGRAM_BOT_TOKEN` + `AMA_TELEGRAM_ALLOWED_CHAT_IDS` (your
    operator chat id) + `AMA_TELEGRAM_OUTBOUND_ENABLED=true`.
  - Optionally set `AMA_DEEPSEEK_API_KEY` + `AMA_DEEPSEEK_ENABLED=true`.

## Verify no withdraw permission

Run the launch check and inspect the warnings. A key reporting a high-risk
(withdraw / internal-transfer) permission raises a warning. PR116 does
**not** require withdraw permission; if it is detectable, it is a NO-GO
warning to fix on the exchange.

## Phase A — No-key server validation

  - `python -m pytest tests/unit -q` — all green.
  - `python scripts/live_launch_check.py --json` — returns `WARN` (not
    `FAIL`) for missing keys; `no_real_order_sent=true`; `go_for_live_shadow`
    may be true once public market is reachable.
  - No real order is ever sent.

## Phase B — Real-key health check

  - `python scripts/live_api_health_check.py --binance --telegram --deepseek --json`
  - Binance public + private read OK; Telegram send test OK; DeepSeek OK.
  - Private trade still **disabled**.

## Phase C — LIVE_SHADOW

  - `python scripts/live_shadow_run.py --once --json`
  - `python scripts/live_shadow_run.py --loop --interval-seconds 60`
  - `python scripts/live_shadow_run.py --once --send-telegram`
  - Read the Telegram cards. **No real orders** (`real_order=false`).

## Phase D — Arm LIVE_LIMITED

  - Intentionally set the env: `AMA_LIVE_CAPITAL_PROFILE_ID=L1_10U_PROBE`,
    `AMA_BINANCE_ENABLE_PRIVATE_TRADE=true`,
    `AMA_LIVE_EXCHANGE_LIVE_ORDERS=true`, `AMA_LIVE_TRADE_AUTHORITY=true`,
    `AMA_LIVE_EXECUTION_CONFIRM_CODE=<your-code>`.
  - Telegram: `/mode live_limited` → returns a risk summary + a code.
  - Telegram: `/confirm_live CODE`.
  - Telegram: `/kill_all` → `/confirm_kill CODE` to arm the kill switch
    (or arm it via the operator workflow), then re-arm operation as needed.
  - `python scripts/live_launch_check.py --pre-live-limited --require-real-keys --json`
  - Verify `go_for_live_limited=true` **only** when all gates pass.

## Phase E — 10U tiny smoke

  - Max notional `<= 1U` or the profile config; manually confirm.
  - `python scripts/live_limited_smoke.py --dry-run --symbol RAVEUSDT --notional 1 --leverage 1 --json`
  - When ready: `python scripts/live_limited_smoke.py --real-order --symbol RAVEUSDT --notional 1 --leverage 1 --i-understand-this-places-real-order --confirm-code <code> --json`
  - Verify the order / fill / ledger / Telegram `LIVE_SMOKE_RESULT` card.
  - Immediate stop conditions: kill switch + manual close on the exchange.

## Phase F — Rollback

  - Telegram: `/mode shadow` (disarms LIVE_LIMITED).
  - Telegram: `/pause`.
  - Telegram: `/kill_all` → `/confirm_kill`.
  - Disable `AMA_LIVE_EXCHANGE_LIVE_ORDERS`, `AMA_LIVE_TRADE_AUTHORITY`,
    `AMA_BINANCE_ENABLE_PRIVATE_TRADE`.
  - Stop the runner.

## Logs to save

  - The `events.db` audit trail (mode switches, kill switch, order ledger).
  - The launch-check JSON reports.
  - The `LIVE_SMOKE_RESULT` cards + the `LiveOrderLedger` rows.

## Explicit GO / NO-GO

**GO for LIVE_SHADOW:** Binance public OK; no live orders; Telegram
optional; system stable.

**GO for LIVE_LIMITED:** real account read OK; `L1_10U` (or approved)
profile active; usable capital capped; kill switch **ready** (available)
and **not active**; Telegram allowed chat OK; `exchangeInfo` OK; DRY order
validation OK; no blind/sim source in the live path; operator confirmation
complete.

**NO-GO:** private read fail; secret placeholder; withdraw-permission
warning if detectable; profile mismatch unacknowledged; kill switch **not
ready** (subsystem unavailable) OR kill switch **active** (emergency halt
engaged); funding accounting unavailable; stop/exit plan unavailable;
Telegram not configured for the live operator; source isolation failure; AI
forbidden-field output accepted; execution gateway rejects.
