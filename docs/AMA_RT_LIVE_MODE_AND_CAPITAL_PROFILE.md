# AMA-RT Live Runtime Mode & Capital Profile Ladder (PR110)

> **Status: IN_REVIEW.** Companion to `docs/AMA_RT_LIVE_FOUNDATION_SPEC.md`.

This document is the authoritative description of the two PR110
concepts most easily confused: the **live runtime mode**
(`LIVE_SHADOW` vs `LIVE_LIMITED`) and the **capital profile ladder**
(`L0_SHADOW` .. `L8_10M_CAPITAL_PRESERVATION`).

PR110 does NOT enable live trading, does NOT connect the Binance
private API, does NOT place orders, and does NOT enable Telegram
outbound. Everything below is contract / model only.

---

## 1. Runtime mode: LIVE_SHADOW vs LIVE_LIMITED

`LiveRuntimeMode` is a **different concept** from the Phase 1
`TradingMode`. `TradingMode` (locked to `paper`) is the historical
trade-authority ladder; `LiveRuntimeMode` describes how the
live-preparation layer is running right now.

### LIVE_SHADOW (空盘跑) — the default

- May connect a **read-only** Binance context: read market data, read
  account balance, read positions, read `exchangeInfo` / filters.
- May generate a **shadow** entry / exit plan and a Telegram push.
- `real_order = False`, `real_capital_changed = False`.
- **NEVER** places / cancels an order, changes leverage, or changes
  margin mode.

### LIVE_LIMITED (有资金跑)

- Real small-capital trading is permitted **in principle**, but PR110
  does **not** implement real order placement.
- Every real order must pass the Risk Engine + Capital Profile + Kill
  Switch.
- Initial profile is **`L1_10U_PROBE`** only.
- Requires **operator double-confirmation**.
- Requires the API health check (a later PR) to pass.
- Requires the kill switch to be **armed**.
- Requires a **valid** capital profile.
- Every switch is **audited**.

### LIVE_SHADOW and LIVE_LIMITED are different and must never be confused

The former can never move real capital. The latter is the only mode
that ever could (in a future PR) — and only behind the operator
confirmation handshake.

### Defaults & restart safety

- The default mode is **`LIVE_SHADOW`**.
- A system restart must **never** automatically enter `LIVE_LIMITED`.
  `LiveModeGuard.from_config` always boots in `LIVE_SHADOW` regardless
  of the configured `runtime_mode`.
- `LIVE_LIMITED` depends on a **persisted operator confirmation state**.
- With no confirmation state, **any live order attempt is refused**
  (`assert_live_orders_allowed()` raises `LiveModeViolation`).

### The confirmation handshake

1. Operator runs `/mode live_limited` → `LiveModeGuard.request_live_limited(...)`
   returns a **risk summary** + a **confirmation code**, and emits
   `LIVE_MODE_SWITCH_REQUESTED`. The risk summary contains: current
   mode, current capital profile, current account equity, max account
   capital, max position notional, max daily loss, max total loss, max
   leverage, kill-switch armed?, real orders allowed?, confirmation
   code.
2. Operator runs `/confirm_live CODE` → `LiveModeGuard.confirm_live(code)`.
   It is accepted only if: a request is pending, the code matches, the
   profile allows real orders + `LIVE_LIMITED`, and the kill switch is
   armed. On success it emits `LIVE_MODE_SWITCH_CONFIRMED`,
   `LIVE_LIMITED_ARMED`, `LIVE_LIMITED_ACTIVE`. On failure it emits
   `LIVE_MODE_SWITCH_REJECTED` and stays `LIVE_SHADOW`.

### Events

`LIVE_MODE_SWITCH_REQUESTED`, `LIVE_MODE_SWITCH_CONFIRMED`,
`LIVE_MODE_SWITCH_REJECTED`, `LIVE_LIMITED_ARMED`,
`LIVE_LIMITED_DISARMED`, `LIVE_SHADOW_ACTIVE`, `LIVE_LIMITED_ACTIVE`.

---

## 2. Capital Profile Ladder (1U → 10,000,000U)

Capital must scale through profiles; the 10U method is never re-used at
every scale. As capital grows, the strategy, position sizing, leverage,
liquidity constraints, and harvest / withdrawal rules must adjust
automatically per profile.

| Profile | Equity band (USDT) | Real orders | Max acct cap | Max pos notional | Max pos % | Max active | Max sym exp % | Base lev | Max lev | RT boost | RT max lev | Liq floor (USDT) | Max slip (bps) | Min exit liq |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L0_SHADOW | 0 .. ∞ | **No** | 0 | 0 | 0 | 0 | 0 | 1 | 1 | No | 1 | 0 | 0 | 0 |
| L1_1U_MICRO_PROBE | 0.5 .. 5 | Yes | 1 | 3 | 1.00 | 1 | 1.00 | 1 | 3 | Yes | 5 | 0 | 120 | 0.20 |
| L1_10U_PROBE | 5 .. 25 | Yes | **10** | 20 | 1.00 | 1 | 1.00 | 2 | 5 | Yes | 10 | 0 | 80 | 0.30 |
| L2_25U_50U_SCOUT | 25 .. 100 | Yes | 50 | 100 | 0.80 | 2 | 0.80 | 2 | 5 | Yes | 8 | 0 | 60 | 0.35 |
| L3_100U_ATTACK_TEST | 100 .. 500 | Yes | 100 | 200 | 0.60 | 3 | 0.60 | 2 | 4 | Yes | 6 | 50,000 | 40 | 0.45 |
| L4_1K_GROWTH | 500 .. 5,000 | Yes | 1,000 | 1,500 | 0.40 | 4 | 0.40 | 2 | 3 | Yes | 4 | 250,000 | 25 | 0.55 |
| L5_10K_PROFIT_PROTECTION | 5,000 .. 50,000 | Yes | 10,000 | 12,000 | 0.25 | 5 | 0.25 | 1.5 | 3 | Yes | 3 | 1,000,000 | 15 | 0.65 |
| L6_100K_LIQUIDITY_CONSTRAINED | 50,000 .. 500,000 | Yes | 100,000 | 80,000 | 0.12 | 6 | 0.12 | 1.5 | 2 | **No** | 2 | 5,000,000 | 10 | 0.75 |
| L7_1M_INSTITUTIONAL_STYLE | 500,000 .. 5,000,000 | Yes | 1,000,000 | 500,000 | 0.06 | 8 | 0.06 | 1 | 2 | **No** | 1 | 20,000,000 | 6 | 0.85 |
| L8_10M_CAPITAL_PRESERVATION | 5,000,000 .. ∞ | Yes | 10,000,000 | 2,000,000 | 0.03 | 10 | 0.03 | 1 | 1 | **No** | 1 | 50,000,000 | 4 | 0.90 |

Each profile additionally carries `max_daily_loss_usdt` /
`max_daily_loss_pct`, `max_total_loss_usdt` / `max_total_loss_pct`,
`kill_switch_drawdown_pct`, `require_floating_profit_for_boost`,
`profit_harvest_enabled`, `withdrawal_awareness_enabled`,
`deposit_awareness_enabled`, `escalation_requirements`, and
`deescalation_rules`.

### Rules

1. `L0_SHADOW` does not allow real orders.
2. `L1_10U_PROBE` uses only tiny real capital
   (`max_account_capital_usdt = 10`).
3. `L2` .. `L8` define schema + default constraints only; they are
   **not** auto-enabled.
4. Capital profile escalation is **never** automatic
   (`AUTO_ESCALATION_ALLOWED = False`).
5. If the account grows quickly (e.g. 10U → 10,000U),
   `detect_profile_mismatch` returns `mismatch=True`,
   `direction="escalate"`, a suggested profile, and
   `requires_operator_action=True` — the operator must re-select the
   profile; the system never continues with the 10U method.
6. If equity falls (drawdown or withdrawal) below the band,
   de-escalation is supported (`direction="deescalate"`), again
   operator-driven.
7. Larger capital ⇒ stricter liquidity floor, symbol exposure, and
   slippage constraints.
8. Small capital may be more aggressive; large capital must account for
   fill depth, slippage, staged exit, profit lock, and withdrawal.

Mismatch detection uses the **adjusted** equity from the Capital Event
Contract, so an external deposit can never be mistaken for strategy
growth that "justifies" an escalation.
