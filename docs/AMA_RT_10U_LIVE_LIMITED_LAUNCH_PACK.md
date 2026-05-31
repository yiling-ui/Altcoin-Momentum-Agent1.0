# AMA-RT 10U LIVE_LIMITED Launch Pack v0 (PR116)

The final stage that wires PR110–PR115 into a controlled,
operator-confirmed, small-capital real-money runtime. PR116 is the first
stage that **may** support real 10U `LIVE_LIMITED` operation — **but only
when every gate is explicitly satisfied.**

> **Default behaviour is always safe.** A bare boot / default config stays
> on `runtime_mode=LIVE_SHADOW`, `exchange_live_orders=false`,
> `live_trading=false`, `trade_authority=false`, `ai_trade_authority=false`,
> and sends **no real order**.

---

## 1. What PR116 adds

| Module | Purpose |
| --- | --- |
| `app/live/live_launch_models.py` | Frozen, log-safe data contracts: `LaunchReadinessReport`, `ShadowRunResult`, `SmokeResult` + `launch_safety_markers()`. |
| `app/live/live_runtime.py` | `LiveRuntime` — resolves the **active capital profile dynamically** (no hardcoded 10U), exposes `LiveProfileCaps`, builds the execution context, re-asserts live-source isolation. |
| `app/live/live_launch_readiness.py` | `LiveLaunchReadinessChecker` — the single end-to-end readiness check. Never sends a real order. |
| `app/live/live_shadow_runner.py` | `LiveShadowRunner` — the real-market shadow loop (空盘跑). |
| `app/live/live_limited_arming.py` | `evaluate_arming(...)` + `LiveLimitedSmoke` — the arming roll-up + the gated real-order smoke. |
| `app/live/live_kill_switch.py` | `LiveKillSwitch` — persisted, audited kill switch + controlled-exit-through-gateway contract. |
| `scripts/live_launch_check.py` | Readiness CLI. |
| `scripts/live_shadow_run.py` | LIVE_SHADOW runner CLI. |
| `scripts/live_limited_smoke.py` | LIVE_LIMITED smoke CLI (dry-run by default). |
| `app/live/telegram_commands.py` | Extended with `/launch_check`, `/live_readiness`, `/shadow_once`, `/live_smoke`, `/kill_status`. |

---

## 2. Launch readiness check

`scripts/live_launch_check.py` validates the full launch surface and emits
an overall `PASS` / `WARN` / `FAIL` plus two GO decisions
(`go_for_live_shadow`, `go_for_live_limited`).

```
python scripts/live_launch_check.py --json
python scripts/live_launch_check.py --binance --telegram --deepseek --json
python scripts/live_launch_check.py --pre-live-limited --json
python scripts/live_launch_check.py --pre-live-limited --require-real-keys --json
```

The report includes (selected): `overall_status`, `go_for_live_shadow`,
`go_for_live_limited`, `blockers`, `warnings`, `runtime_mode`,
`capital_profile_id`, `account_equity`, `usable_live_capital`,
`l1_10u_cap_enforced`, `binance_public_ok`, `binance_private_read_ok`,
`binance_private_trade_configured`, `binance_private_trade_enabled`,
`telegram_outbound_ok`, `telegram_allowed_chat_ok`,
`deepseek_ok_or_optional`, `kill_switch_ready`, `kill_switch_active`
(plus `kill_switch_armed` as a backward-compatible alias of
`kill_switch_active`), `exchange_live_orders`,
`trade_authority`, `ai_trade_authority`, `live_path_isolation_ok`,
`blind_sim_isolation_ok`, `funding_accounting_ok`, `order_precision_ok`,
`dry_order_validation_ok`, and `no_real_order_sent` (**always `true`**).

The readiness check builds a tiny DRY order and validates it against
`exchangeInfo` (precision / `minNotional`) and runs the deterministic
execution-permission gate — but it **never** submits.

`--pre-live-limited` only changes the *severity* of a missing
live-limited gate (FAIL instead of WARN). `go_for_live_limited` always
evaluates the **full** gate set, so a plain check (Phase A) returns
`WARN` (not `FAIL`) for missing keys, while still reporting NO-GO.

---

## 3. LIVE_SHADOW runner (空盘跑)

`scripts/live_shadow_run.py` consumes live public + private-read data,
builds the operator cards (account status / capital-profile status / PnL /
funding / positions + a `LIVE_SHADOW_SUMMARY`), optionally a DeepSeek
briefing, and optionally pushes them to Telegram.

```
python scripts/live_shadow_run.py --once --json
python scripts/live_shadow_run.py --loop --interval-seconds 60
python scripts/live_shadow_run.py --once --send-telegram
```

Every shadow run carries `real_order=false` and `no_real_order_sent=true`.
It never places / cancels an order, never changes capital / mode / profile,
and only sends Telegram when outbound is enabled **and** the chat id is
authorised.

---

## 4. LIVE_LIMITED arming workflow

Arming `LIVE_LIMITED` for a real order requires **every** gate:

1. Operator configures the env flags (see §8).
2. Operator runs the launch check (`--pre-live-limited`).
3. Operator switches mode in Telegram: `/mode live_limited`.
4. Operator confirms: `/confirm_live CODE`.
5. Kill switch is **ready** (available) and **not active** (no emergency
   halt engaged). An ACTIVE kill switch blocks every new entry, so it can
   never be a launch requirement.
6. Active profile is `L1_10U_PROBE` (or an operator-approved profile).
7. `exchange_live_orders=true` **and** `trade_authority=true`.
8. Binance private trade is enabled (`AMA_BINANCE_ENABLE_PRIVATE_TRADE=true`).
9. The `LiveExecutionGateway` approves; the `LiveRiskDecision` approves.
10. AI remains **no-authority** (`ai_trade_authority=false`).

`evaluate_arming(...)` rolls this up into an `ArmingStatus` whose
`fully_armed` is `True` only when **all** gates hold.

---

## 5. 10U live constraints (and scaling beyond 10U)

The active capital profile is read **dynamically** from
`app/live/capital_profile.py` (the PR110 ladder). PR116 hardcodes **no**
10U constant. `L1_10U_PROBE` is only the initial default; the runtime
supports switching to any profile (`L1_1U` … `L8_10M`) through persistent
state / env / the Telegram `/profile set` workflow — **without a code
change**.

For `L1_10U_PROBE`:

  - **max live account capital = 10U usable cap.** If the account holds
    more than 10U, only 10U is usable for the profile until the operator
    switches profile in a later stage.
  - max single position notional, max active positions, daily / total
    loss stop, max leverage, right-tail boost — all read from the active
    profile.
  - **No auto profile escalation.** If equity exceeds the active profile
    band, the system emits `CAPITAL_PROFILE_MISMATCH`, caps usable capital
    to the active profile, and demands an explicit operator switch.
  - **No use of the whole account if balance > 10U.**

Switching profile changes every cap (`max_position_notional`,
`max_position_pct`, `max_active_positions`, `max_symbol_exposure`,
`max_daily_loss`, `max_total_loss`, `base_leverage`, `max_leverage`,
`right_tail_boost`, `liquidity_floor`, `max_slippage`,
`kill_switch_threshold`) with no code change. Deposits / withdrawals affect
profile evaluation (through the truthful equity) but **never** pollute
strategy PnL (PR112 funding-aware PnL keeps external flows separate).

---

## 6. 10U live smoke (heavily gated)

`scripts/live_limited_smoke.py` defaults to `--dry-run` (no real order).

```
# Dry run (no real order):
python scripts/live_limited_smoke.py --dry-run --symbol RAVEUSDT \
    --notional 1 --leverage 1 --json

# Real order (only when ALL gates pass):
python scripts/live_limited_smoke.py --real-order --symbol RAVEUSDT \
    --notional 1 --leverage 1 \
    --i-understand-this-places-real-order --confirm-code <code> --json
```

A real order is only ever attempted when ALL of:

  - `--real-order` **and** `--i-understand-this-places-real-order` **and**
    `--confirm-code <code>` (== `$AMA_LIVE_EXECUTION_CONFIRM_CODE`),
  - `--max-notional-usdt` is within the active profile cap,
  - the runtime is an armed `LIVE_LIMITED`,
  - `exchange_live_orders=true`, `trade_authority=true`, private trade
    enabled,
  - the `LiveExecutionGateway` clears every gate (precision / `minNotional`,
    risk decision, stop/exit plan, profile notional/leverage, kill switch).

It routes through the **single** `LiveExecutionGateway`, mints a
`client_order_id`, writes the `LiveOrderLedger`, sends a `LIVE_SMOKE_RESULT`
card (with `fee` / `funding` / `net pnl` fields), and **never retries** (no
duplicate orders). It returns the exact exchange order status; it never
claims a fill/close unless the exchange confirms.

---

## 7. Kill switch and emergency workflow

The kill switch has two distinct states (PR116 hotfix):

  - **ready / available** — the subsystem exists, its persisted state is
    readable, and the operator can trigger it. A LIVE_LIMITED launch
    REQUIRES the kill switch to be ready.
  - **active (emergency halt)** — the switch has been triggered. A
    LIVE_LIMITED launch REQUIRES the kill switch to be **not** active (an
    active kill switch blocks every new entry).

`/kill_all` → `/confirm_kill CODE` (a two-step confirmation) moves the kill
switch into the **active** state. When active:

  - **new entries are blocked immediately** (the persisted active flag is
    the source of truth the execution context consults),
  - the state is visible in `/status`, `/kill_status`, and the readiness
    report as both `kill_switch_ready` and `kill_switch_active`.

**PR116 limit (documented):** a real cancel / exit only happens through the
`LiveExecutionGateway` and only when a controlled-exit callback is wired.
With no callback wired, the kill switch **activates + halts new entries**
and tells the operator, in plain language, that open positions must be
closed **manually on the exchange**. The kill switch **never** claims a
position is closed unless the exchange actually confirmed it.

---

## 8. Operator env flags

| Env var | Default | Meaning |
| --- | --- | --- |
| `AMA_LIVE_RUNTIME_MODE` | `LIVE_SHADOW` | Never auto-escalates above shadow. |
| `AMA_LIVE_CAPITAL_PROFILE_ID` / `AMA_LIVE_CAPITAL_PROFILE` | `L0_SHADOW` | Active capital profile (e.g. `L1_10U_PROBE`). |
| `AMA_BINANCE_ENABLE_PRIVATE_READ` | `false` | Enable account/positions/income read. |
| `AMA_BINANCE_ENABLE_PRIVATE_TRADE` | `false` | Enable the private trade path. |
| `AMA_LIVE_EXCHANGE_LIVE_ORDERS` | `false` | Operator flag — real orders. |
| `AMA_LIVE_TRADE_AUTHORITY` | `false` | Operator flag — trade authority. |
| `AMA_LIVE_AI_TRADE_AUTHORITY` | `false` | **Must stay false. AI has no trade authority.** |
| `AMA_LIVE_EXECUTION_CONFIRM_CODE` | (unset) | Expected real-order smoke confirmation code. |
| `AMA_TELEGRAM_OUTBOUND_ENABLED` | `false` | Enable Telegram outbound. |
| `AMA_TELEGRAM_ALLOWED_CHAT_IDS` | (unset) | Comma-separated allowed chat ids. |

---

## 9. Hard boundaries

**Forbidden in PR116:** default real trading; default
`exchange_live_orders=true`; default `trade_authority=true`; default
`LIVE_LIMITED`; automatic profile escalation; AI trade authority; Telegram
bypass of the Risk Engine / Execution Gateway; any blind / replay / sim /
paper-shadow / backtest / offline-AI / telegram-sandbox source entering the
live path; `MockExchange` / `SimulatedCapitalFlow` /
`HistoricalMarketStore` in the live path; an order without a
`client_order_id`; an entry order without a stop/exit plan; hiding
fees/funding in PnL; treating a deposit as profit or a withdrawal as loss;
claiming an order filled/closed unless the exchange confirms.

See `docs/AMA_RT_LIVE_OPERATOR_RUNBOOK.md` for the full Phase A–F runbook
and the explicit GO / NO-GO criteria.


---

## 10. PR117 — Final full-system sandbox audit (pre-launch gate)

Before the 10U `LIVE_LIMITED` launch is validated against real keys, run
the PR117 full-system sandbox audit. It exercises the **whole** PR110–PR116
chain end to end against the fake altcoin `RAVEUSDT_SANDBOX` with **fake
transports only** — it never sends a real order.

```bash
python scripts/live_full_system_sandbox_audit.py --json
```

A `PASS` (or `WARN`) with `ready_for_real_key_validation=true` is the
*go-to-real-key-validation* signal: the machinery is proven correct in the
sandbox, and the only remaining step before funded operation is
`scripts/live_launch_check.py --require-real-keys` with real (non-
placeholder) Binance / Telegram / DeepSeek credentials. A `FAIL` blocks the
launch until the reported blocker is fixed.

PR117 also re-proves, under the full chain, that capital can scale from 10U
→ 50U → 1,000U → … → 10,000,000U by an **operator** profile switch with no
code change, and that blind / replay / sim sources stay isolated from the
live path. See `docs/AMA_RT_FINAL_FULL_SYSTEM_AUDIT.md`.
