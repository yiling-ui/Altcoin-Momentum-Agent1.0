# AMA-RT Live Capital / Risk / Funding-Aware PnL (PR112)

> **Status: PR112 IN_REVIEW.**
> **Type: read-only live capital / risk wiring + 10U profile enforcement.**
> **Hard boundary: NO real orders. NO cancel. NO leverage / margin change.
> NO auto-switch to LIVE_LIMITED. NO auto-escalate of the capital profile.**

PR112 wires the PR111 real Binance private-read results into a live
capital / risk engine and strictly enforces the `L1_10U_PROBE`
small-capital profile. It prepares the ground for PR113's real order
execution gateway — but **PR112 itself never submits an order**.

> **PR113 follow-on (IN_REVIEW):** the next slice — the **Live Execution
> Gateway** (`docs/AMA_RT_LIVE_EXECUTION_GATEWAY.md`) — adds the first
> code path able to compose + send a real Binance order, behind a hard
> 15-point gate, **blocked by default**. PR113 consumes this PR112 dry
> `LiveRiskDecision`: a real order is only ever authorised when the
> decision is `approved` AND the context is fully armed
> (`authorize_real_order`), and the gate then re-checks every flag. PR113
> begins carrying funding forward into a per-order `net_pnl = realized −
> fee + funding_usdt_attributed`; position-level funding attribution
> remains the PR114 handoff (`UNATTRIBUTED_PENDING_POSITION_LINK`).

---

## 1. PR112 does NOT (read this first)

1. **PR112 still does not place real orders.** Every risk decision has
   `real_order_allowed = false`.
2. **PR112 reads real account state only** (PR111 private read).
3. **PR112 enforces `L1_10U_PROBE`** as the current small-cap profile.
4. **Funding fee and commission are included in net PnL.**
5. **Deposit / withdrawal do not count as strategy PnL.**
6. **Account-level funding attribution is implemented; position-level
   attribution is the next PR** (`UNATTRIBUTED_PENDING_POSITION_LINK`).
7. **If the account grows rapidly, a profile mismatch is detected and
   the operator must switch the profile manually** — there is no
   auto-upgrade.
8. **`LIVE_SHADOW` and `LIVE_LIMITED` remain separate.** A real-order
   intent is rejected in `LIVE_SHADOW`.

Safety flags remain locked:

```
phase_12_forbidden                        = True
live_trading                              = False
exchange_live_orders                      = False
trade_authority                           = False
ai_trade_authority                        = False
binance_private_trade_enabled_by_config   = False (unless operator later
                                                   sets the env, and even
                                                   then PR111/PR112 block it)
```

---

## 2. What PR112 adds

| Area | Module |
|------|--------|
| Live capital state from account snapshot | `app/live/capital_state.py` |
| Funding-aware PnL + external-flow separation | `app/live/pnl_accounting.py` |
| Capital profile enforcement + live order risk pre-check | `app/live/live_risk_engine.py` |
| Orchestration + Telegram operator payloads | `app/live/live_capital_service.py` |
| Status CLI | `scripts/live_capital_status.py` |

PR112 reuses PR110/PR111 contracts: `LiveRuntimeMode` / `OrderSource`
(`app.core.enums`), the Capital Profile ladder
(`app.live.capital_profile`), the Capital Event contract
(`app.live.capital_event`), the Binance income classifier
(`app.live.binance_income`), and the right-tail leverage gate
(`app.live.leverage_gate`).

---

## 3. `LiveCapitalState`

Built from a PR111 `BinanceAccountSnapshot` (+ open-order count) via
`LiveCapitalState.from_account_snapshot(...)`:

| Field | Meaning |
|-------|---------|
| `account_id_masked` | masked account id (`abc***xyz`); raw never stored |
| `runtime_mode` | `LIVE_SHADOW` / `LIVE_LIMITED` |
| `capital_profile_id` | active profile id |
| `wallet_balance_usdt` | total wallet balance |
| `available_balance_usdt` | available (free) balance |
| `account_equity_usdt` | margin balance (wallet + unrealized) |
| `unrealized_pnl_usdt` | total unrealized PnL |
| `used_margin_usdt` | `max(0, equity − available)` |
| `free_margin_usdt` | available balance |
| `open_position_count` / `open_order_count` | live counts |
| `positions` | `LivePosition[]` (symbol, side, amt, entry, mark, uPnL, notional, leverage, isolated/cross, liq price, update_time) |
| `fetched_at` | snapshot timestamp |
| `source` | always `BINANCE_PRIVATE_READ` |
| `is_real_account_snapshot` | `True` |
| `real_orders_allowed` | **`False` in PR112** |
| `exchange_live_orders` | **`False`** |

---

## 4. Funding-aware PnL (`LivePnlSummary`)

The operator-facing net figure **always** includes commission and
funding:

```
net_strategy_pnl = gross_realized_pnl − commission_total + funding_total
```

External flows are tracked **separately** and never enter strategy PnL:

- a deposit / transfer-in is never strategy profit;
- a withdrawal / transfer-out is never strategy loss;
- unknown income types are preserved separately
  (`unknown_income_total_usdt`), never coerced into PnL.

`adjusted_strategy_equity_usdt` is the truthful equity;
`performance_equity_excluding_external_flows = equity − net_external_capital`
isolates strategy-only performance.

### Funding attribution (account-level in PR112)

- A funding row without a `trade_id` is marked
  `UNATTRIBUTED_PENDING_POSITION_LINK`.
- `funding_attribution_status` rolls up to `NOT_APPLICABLE` /
  `ATTRIBUTED` / `UNATTRIBUTED_PENDING_POSITION_LINK`.
- **HANDOFF(PR113/PR114):** attach funding / commission / realized-PnL
  rows to the live trade ledger at position/trade level.

---

## 5. Capital profile enforcement (`L1_10U_PROBE`)

`evaluate_capital_profile_state(capital_state, profile, ...)` returns a
`CapitalProfileState` with a `profile_status` and a list of `flags`:

- `PROFILE_OK`
- `PROFILE_MISMATCH_EQUITY_ABOVE_RANGE` / `..._BELOW_RANGE`
- `ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP`
- `DAILY_LOSS_LIMIT_REACHED` / `TOTAL_LOSS_LIMIT_REACHED`
- `MAX_ACTIVE_POSITIONS_REACHED`
- `AVAILABLE_BALANCE_TOO_LOW`
- `RISK_HALT_ACTIVE` / `KILL_SWITCH_REQUIRED`

For `L1_10U_PROBE`:

- usable account capital is **capped at 10U**
  (`usable_capital = min(equity, max_account_capital_usdt)`), so a large
  real balance is never used blindly under the small profile;
- if equity exceeds the profile band, a
  `PROFILE_MISMATCH_EQUITY_ABOVE_RANGE` is flagged and the operator must
  reselect the profile — `auto_escalation_allowed = False`, **no
  auto-upgrade**;
- if equity falls below a configured safety floor, `risk_halt = True`.

---

## 6. Live order risk pre-check (dry)

`evaluate_live_order_risk(intent, capital_state, capital_profile,
leverage_gate, runtime_mode)` returns a `LiveRiskDecision`. It rejects on:

- `LIVE_SHADOW` (real-order intent not allowed),
- `source != LIVE`,
- account snapshot missing,
- capital profile invalid / real orders not allowed for profile,
- planned notional ≤ 0 / > profile max,
- account capital exceeds profile cap,
- planned leverage ≤ 0 / > profile max,
- insufficient available balance for the required margin,
- active positions ≥ profile max,
- daily / total loss limit reached,
- risk halt active,
- no stop plan / no exit plan,
- right-tail leverage gate rejection,
- symbol not tradable (when `exchangeInfo` is supplied).

**`real_order_allowed` is always `False` in PR112** — even an
`approved` decision is advisory until PR113's execution gateway consumes
it.

---

## 7. Telegram operator payloads (build-only; no outbound)

`app/live/live_capital_service.py` builds (never sends) the payloads:

- `LIVE_ACCOUNT_STATUS` — mode / profile / wallet / available / equity /
  unrealized / positions / open orders / real_orders_allowed / kill switch.
- `LIVE_CAPITAL_PROFILE_STATUS` — profile status + flags + usable capital.
- `LIVE_PNL_SUMMARY` — gross realized / commission / funding / net /
  deposits / withdrawals / adjusted equity / funding attribution.
- `LIVE_RISK_REJECT` — symbol / planned notional / planned leverage /
  reject reason / max allowed notional+leverage / equity / profile.
- `CAPITAL_PROFILE_MISMATCH` — current equity / current profile /
  recommended next profile / **no automatic upgrade**.
- `FUNDING_EVENT_SUMMARY` — funding / commission / attribution status.

Every payload carries `real_order = false`, `trade_authority = false`,
`ai_trade_authority = false`.

---

## 8. CLI — `scripts/live_capital_status.py`

```bash
python scripts/live_capital_status.py --json
python scripts/live_capital_status.py --pnl --json
python scripts/live_capital_status.py --risk-check-sample --symbol RAVEUSDT --notional 1 --leverage 1 --json
python scripts/live_capital_status.py --validate-env --env-file .env.live --json
```

Read-only: it never submits orders, never switches mode, never calls a
private-trade endpoint, masks secrets, and shows funding / commission +
capital profile status when income history is available.

---

## 9. PR111 usability hardening folded into PR112

- **Placeholder secret detection** — a placeholder (`PUT_YOUR_KEY_HERE`,
  `<your-key>`, `changeme`, …) is detected **before** any real HTTP call;
  the health check returns `PLACEHOLDER_SECRET_CONFIGURED` /
  `MISSING_REAL_SECRET` instead of a confusing HTTP 401.
- **Typed health messages** — `classify_api_error` distinguishes
  `INVALID_SECRET_OR_UNAUTHORIZED` (401), `PERMISSION_DENIED` (403),
  `RATE_LIMITED` (429), `API_ENDPOINT_UNAVAILABLE` (5xx/404),
  `NETWORK_ERROR`, `MALFORMED_API_RESPONSE` — never a single generic error.
- **`.env.live` validation** — `app/live/env_validation.py` flags
  `ENV_FILE_SUSPICIOUS_LINE` (e.g. a pasted shell command) and warns when
  `AMA_SECRET_LOGGING_ALLOWED` is missing or truthy. No secret value is
  ever printed.
- **Capital profile env compatibility** — both
  `AMA_LIVE_CAPITAL_PROFILE_ID` (priority) and `AMA_LIVE_CAPITAL_PROFILE`
  (alias) are supported. An invalid value yields an explicit
  `CONFIG_INVALID_CAPITAL_PROFILE` (never a silent fallback). This fixes
  the PR111 bug where `AMA_LIVE_CAPITAL_PROFILE=L1_10U_PROBE` was ignored
  and the health output still showed `L0_SHADOW`.
