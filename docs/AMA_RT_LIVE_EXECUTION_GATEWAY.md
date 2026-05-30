# AMA-RT Live Execution Gateway (PR113)

> **PR113 — Live Execution Gateway v0: Binance Order Execution Adapter +
> Order Lifecycle + Fill Ledger + Strict LIVE_LIMITED Gate.**
> **Status: IN_REVIEW.**
> **Type: real order execution skeleton — real order code exists but is
> BLOCKED by default.**

PR113 introduces the first AMA-RT code path that can compose and send a
real Binance USDT-M futures order. It is built behind a hard,
multi-condition gate so that the **default state remains completely
safe** and no real order can leave the system by accident.

This document is the canonical contract for the live execution layer.

---

## 1. What PR113 introduces

The `LiveExecutionGateway` is the **single entry point** for every real
order. The end-to-end order path is:

```
Signal / Strategy Plan
  → LiveOrderIntent            (app/live/execution_models.py)
  → LiveRiskDecision           (PR112 dry pre-check; real_order_allowed=False)
  → LiveExecutionGateway       (app/live/execution_gateway.py)
      → LivePathIsolationGuard (only OrderSource.LIVE may pass)
      → AI refusal             (ai_trade_authority is forbidden)
      → order validation       (exchangeInfo precision / minNotional)
      → evaluate_execution_permission (the 15-point gate)
  → BinanceExecutionAdapter    (app/live/binance_execution_adapter.py)
  → LiveOrderResult / LiveFillEvent
  → LiveOrderLedger            (app/live/order_ledger.py)
  → Telegram payload           (app/live/execution_telegram.py)
```

New modules under `app/live/`:

| Module | Responsibility |
| --- | --- |
| `execution_models.py` | `LiveOrderIntent`, `LiveOrderRequest`, `LiveOrderResult`, `LiveFillEvent`, `OrderValidationResult` + enums |
| `binance_execution_adapter.py` | `BinanceExecutionAdapter` — compose/send order/cancel/status, blocked by default |
| `order_ledger.py` | `LiveOrderLedger` — append-only LIVE order/fill/cancel rows |
| `execution_gateway.py` | `LiveExecutionGateway`, `ExecutionPermissionContext`, `evaluate_execution_permission` |
| `execution_telegram.py` | order-lifecycle Telegram payload builders |
| `execution_errors.py` | typed execution errors |

CLI: `scripts/live_execution_smoke.py`.

---

## 2. Default state is BLOCKED (safe by default)

The default posture is unchanged and safe:

  - `runtime_mode = LIVE_SHADOW` (空盘跑)
  - `exchange_live_orders = false`
  - `trade_authority = false`
  - `live_trading = false`
  - `ai_trade_authority = false`
  - Binance `enable_private_trade = false`
  - **no real order by default**

With these defaults the gateway returns a `BLOCKED` result and the
adapter never opens a socket.

---

## 3. The 15-point execution gate

A real order request leaves the system **only** when every condition is
true (`evaluate_execution_permission`):

1. `runtime_mode = LIVE_LIMITED`
2. `live_limited_confirmed = true`
3. `capital_profile_id` allows real orders (e.g. `L1_10U_PROBE`)
4. `exchange_live_orders = true`
5. `trade_authority = true`
6. Binance private trade enabled by config
7. `LiveRiskDecision.approved = true`
8. `LiveRiskDecision.real_order_allowed = true`
9. kill switch **not** active
10. `source = LIVE` (no live path isolation violation)
11. order has a `client_order_id`
12. order passes exchangeInfo precision / minNotional checks
13. order notional / leverage within the active profile
14. stop / exit plan present for an opening order (or a documented
    emergency / order-type exception)
15. account capital within the profile cap (or operator-acknowledged)

If any condition fails, the gateway emits `LIVE_EXECUTION_BLOCKED`,
writes an auditable (non-real) ledger row, builds a Telegram
`LIVE_EXECUTION_BLOCKED` payload, and returns a `BLOCKED`
`LiveOrderResult` — **no socket is opened**.

### `real_order_allowed` is hard to turn on

PR112's `evaluate_live_order_risk` always returns
`real_order_allowed = False`. The only place that can flip it True is
`authorize_real_order(decision, context)`, and it does so **only when the
decision is approved AND the context is fully armed** (LIVE_LIMITED +
confirmed + exchange_live_orders + trade_authority + private trade +
kill-switch off + not AI). Even after the flip, the gate re-checks every
flag independently (defence in depth).

---

## 4. Binance execution adapter

`BinanceExecutionAdapter` supports:

  - `submit_order(...)` — `MARKET` / `LIMIT`, `reduce_only` close
  - `cancel_order(...)`
  - `get_order(...)` / `get_open_orders(...)` (idempotent reads, safe to retry)
  - `get_user_trades(...)` (fills, with fee)
  - `normalize_order(...)` (tickSize / stepSize / precision)
  - `validate_order_against_exchange_info(...)` (tradable / minQty / minNotional)

`STOP_MARKET` / `TAKE_PROFIT_MARKET` have model + validation support;
their full send path can be staged in a follow-up.

Hard adapter rules:

  - **Blocked by default.** No socket is opened unless
    `real_order_allowed=True` AND `enable_private_trade=True` AND
    `runtime_mode=LIVE_LIMITED` AND credentials are present. Otherwise it
    returns a `BLOCKED` result and emits `LIVE_ORDER_ADAPTER_BLOCKED`.
  - **Idempotency:** every order carries `newClientOrderId =
    client_order_id`. Orders / cancels are **never** blind-retried (no
    duplicate orders); only idempotent status reads may retry.
  - **It never changes leverage** (`set_leverage` refuses).
  - **It never changes margin mode** (`set_margin_mode` refuses).
  - timestamp / recvWindow / HMAC-SHA256 signature handled internally;
    the secret and the full signed URL are never logged. Binance error
    codes are surfaced via `BinanceExecutionHttpError` (sanitised msg).

---

## 5. Order ledger (separate from sim/blind)

`LiveOrderLedger` is an append-only ledger of LIVE order / fill / cancel
rows. It is **not** shared with the blind / sim / paper-shadow trade
ledger. Each row carries the brief-mandated fields, including
`intent_type` (ENTRY / EXIT / REDUCE / CANCEL), `is_real_order`,
`fee_usdt`, `funding_usdt_attributed`, `realized_pnl_usdt`, and
`net_pnl_usdt`.

**Funding is carried forward, never dropped:**

```
net_pnl = realized_pnl − fee + funding_usdt_attributed
```

PR113 keeps funding attribution pending: a fill's
`funding_attribution_status` defaults to
`UNATTRIBUTED_PENDING_POSITION_LINK`. Linking funding to a
position/trade is a PR114 handoff.

---

## 6. Telegram payloads

The gateway builds payloads (no outbound socket) for:
`LIVE_ORDER_SUBMIT_REQUESTED`, `LIVE_ORDER_SUBMITTED`,
`LIVE_ORDER_FILLED`, `LIVE_ORDER_PARTIALLY_FILLED`,
`LIVE_ORDER_CANCELED`, `LIVE_ORDER_REJECTED`, `LIVE_ORDER_FAILED`,
`LIVE_EXECUTION_BLOCKED`, `LIVE_EXIT_FILLED`.

Each payload carries the mode display (空盘跑 / 有资金跑), `runtime_mode`,
`real_order`, symbol/side/order_type/leverage, the **planned** vs.
**actual** entry / exit / stop / take-profit prices, quantity,
notional, `fee_usdt`, `funding_usdt`, gross/net PnL, `pnl_pct`,
balances, order ids, `risk_decision`, `reject_reason`, and `event_id`.

  - **空盘跑** (LIVE_SHADOW): `real_order=false`, `order_id="--"`,
    `actual_entry_price="--"`, `real_capital_changed=false`.
  - **有资金跑** (LIVE_LIMITED): `real_order` only becomes true after an
    actual fill on a real order; actual order / fill fields are shown.

---

## 7. CLI — `scripts/live_execution_smoke.py`

```bash
# 1. Permission-only (the gate; no normalization HTTP)
python scripts/live_execution_smoke.py --permission-check --json

# 2. Dry order validation (normalize + validate; never submits)
python scripts/live_execution_smoke.py --dry-run-order \
    --symbol RAVEUSDT --side BUY --notional 1 --leverage 1 --json

# 3. Real order — BLOCKED unless ALL gates AND all three flags
python scripts/live_execution_smoke.py --real-order \
    --i-understand-this-places-real-order --confirm-code <code> ...
```

The CLI prints `execution_permission`, `reject_reason`,
`exchange_live_orders`, `trade_authority`, `runtime_mode`,
`capital_profile_id`, `private_trade_enabled`,
`order_normalization_result`, and `no_real_order_sent`. The default
path always reports `no_real_order_sent=true`. The real-order path is
blocked unless the operator supplies all three confirmation flags, the
`--confirm-code` matches `AMA_LIVE_EXECUTION_CONFIRM_CODE`, **and** the
execution gate allows it.

---

## 8. Safety boundary (what PR113 still does NOT do)

1. PR113 introduces the live execution gateway, but the real order code
   is **blocked by default**.
2. Orders require `LIVE_LIMITED` + confirmation + risk approved +
   `exchange_live_orders=true` + `trade_authority=true` + private trade
   enabled.
3. `LIVE_SHADOW` never places orders.
4. **AI never places orders.** `ai_trade_authority` is a hard refusal
   (`AiTradeAuthorityForbidden`).
5. Telegram never bypasses the Risk Engine.
6. Blind / replay / sim / paper-shadow sources never reach live
   execution (`LivePathIsolationViolation`).
7. Funding attribution is carried forward and must be linked to a
   position/trade in a follow-up (`UNATTRIBUTED_PENDING_POSITION_LINK`).
8. The `L1_10U_PROBE` profile remains the default live test profile.
9. PR113 never changes leverage or margin mode.
10. Always run the dry-run smoke before any real order.

---

## 9. Tests

`tests/unit/test_pr113_execution_gateway.py` and
`tests/unit/test_pr113_cli.py` cover the 31 brief-mandated scenarios
(gate rejections, adapter normalization/validation/blocking, parse,
fills, ledger, Telegram payloads, AI / blind-sim refusal, CLI dry-run
and blocked real-order path) using a **fake Binance transport only** —
no real API calls. The full suite (`python -m pytest tests/unit -q`)
stays green, so PR110 / PR111 / PR112 are unaffected.

---

## 10. Status

**Current status = PR113 IN_REVIEW.**
