# AMA-RT API Integration Pack v0 (PR111)

> Status: **PR111 IN_REVIEW**
> Scope: Binance + Telegram + DeepSeek **API Health & Permission Layer**.
> Hard boundary: **No live orders. No leverage/margin changes. No AI trade
> authority. LIVE_SHADOW is the default.**

PR111 is the first step on the real-capital road map. It builds the real
API clients, secret loading, permission checks, health checks, account /
funding / fee reads, a Telegram test-message path, and a DeepSeek test
briefing path - all behind the `app/live/` package - **without ever
placing a real order**.

AMA-RT is a short-horizon, right-tail capture system, not a low-volatility
yield product. This pack is built to serve real market operation: real API
connectivity, real market data, real balances, real operator push - but
with the order path hard-blocked until a later PR.

---

## 1. What PR111 adds

| Area | Module |
|------|--------|
| Secret loading + masking | `app/live/secrets.py` |
| Live API config (env) + runtime mode | `app/live/api_config.py` |
| Binance income → PR110 Capital Event contract | `app/live/binance_income.py` |
| Binance models | `app/live/binance_models.py` |
| Binance permissions | `app/live/binance_permissions.py` |
| Binance client (public / private-read / private-trade-blocked) | `app/live/binance_client.py` |
| Telegram client + health | `app/live/telegram_client.py`, `app/live/telegram_health.py` |
| DeepSeek client + health | `app/live/deepseek_client.py`, `app/live/deepseek_health.py` |
| Unified health report | `app/live/health.py` |
| Health-check CLI | `scripts/live_api_health_check.py` |

Built on PR110: PR111 reuses PR110's `LiveRuntimeMode`
(`app.core.enums`), the Capital Event contract
(`app.live.capital_event`: `LiveCapitalEvent` / `CapitalEventType` /
`CapitalEventLedger`), and the Capital Profile ladder
(`app.live.capital_profile`) rather than duplicating them.
`app/live/binance_income.py` only maps Binance `/fapi/v1/income` rows
onto those PR110 types.

---

## 2. Required environment variables

All are optional; safe defaults apply. A missing secret never crashes -
the health check reports `API_HEALTH_MISSING_SECRET`.

### Binance
- `AMA_BINANCE_API_KEY`
- `AMA_BINANCE_API_SECRET`
- `AMA_BINANCE_BASE_URL` (default `https://api.binance.com`)
- `AMA_BINANCE_FAPI_BASE_URL` (default `https://fapi.binance.com`)
- `AMA_BINANCE_ENABLE_PRIVATE_READ` (default `false`)
- `AMA_BINANCE_ENABLE_PRIVATE_TRADE` (default `false`; order path stays blocked regardless)
- `AMA_BINANCE_USE_TESTNET` (default `false`)

### Telegram
- `AMA_TELEGRAM_BOT_TOKEN`
- `AMA_TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated)
- `AMA_TELEGRAM_OUTBOUND_ENABLED` (default `false`)

### DeepSeek
- `AMA_DEEPSEEK_API_KEY`
- `AMA_DEEPSEEK_BASE_URL` (default `https://api.deepseek.com`)
- `AMA_DEEPSEEK_MODEL` (default `deepseek-chat`)
- `AMA_DEEPSEEK_ENABLED` (default `false`)

### General
- `AMA_LIVE_RUNTIME_MODE` (default `LIVE_SHADOW`)
- `AMA_LIVE_API_HEALTHCHECK_ENABLED` (default `true`)
- `AMA_SECRET_LOGGING_ALLOWED` (default `false`, must stay `false`)

See `docs/AMA_RT_LIVE_API_SETUP.md` for step-by-step setup.

---

## 3. Running the health check

```bash
python scripts/live_api_health_check.py --all
python scripts/live_api_health_check.py --binance
python scripts/live_api_health_check.py --telegram
python scripts/live_api_health_check.py --deepseek
python scripts/live_api_health_check.py --all --json
# Explicit, opt-in Telegram test message (outbound must be enabled):
python scripts/live_api_health_check.py --telegram --send-telegram-test --chat-id 123456
```

Output includes: `overall_status` (PASS/WARN/FAIL), per-provider statuses,
`safety_flags`, `live_runtime_mode`, `capital_profile_id`,
`exchange_live_orders`, `ai_trade_authority`, `telegram_outbound_enabled`,
and `secrets_masked=true`.

Exit codes: `0` PASS/SKIPPED, `1` WARN, `2` FAIL.

Health-check safety guarantees:
1. Never places orders.
2. Never switches mode.
3. Never enables live trading.
4. Never modifies leverage/margin.
5. Never sends a Telegram message unless `--send-telegram-test` is given.
6. Never calls DeepSeek unless `--deepseek` or `--all` is given.

---

## 4. Binance permission model

PR111 uses three access layers:

1. **PUBLIC_MARKET** - ping / server time / exchangeInfo / mark price /
   24h ticker / klines. No credential.
2. **PRIVATE_READ** - account / balances / positions / open orders (read) /
   income history. HMAC-SHA256 signed, requires
   `AMA_BINANCE_ENABLE_PRIVATE_READ=true` and credentials.
3. **PRIVATE_TRADE** - interface only. Every order / cancel / leverage /
   margin method is **BLOCKED**: it returns `TRADE_API_BLOCKED_BY_PR111`
   or raises `LiveTradeNotEnabled`. **No HTTP order request is ever built
   or sent.**

The health check reports: `public_market_ok`, `private_read_ok`,
`private_trade_configured`, `private_trade_enabled_by_config`,
`private_trade_blocked_by_mode`, `can_read_account`, `can_read_positions`,
`can_read_income`, `can_trade_if_account_reports_it`,
`high_risk_permission_warning`.

If a trade-capable key exists but the runtime mode is `LIVE_SHADOW`, the
order path stays blocked. `can_trade_if_account_reports_it` mirrors the
exchange's own flag - it is **not** a runtime authorisation.

### Relationship to PR110's locked `binance_private_api_enabled`
PR110's `live:` config locks `binance_private_api_enabled=False`; that
flag gates the PR110 **live order / execution** config path and is
deliberately left untouched (still `False`) by PR111. PR111's
**read-only** private access is a separate, independently env-gated path
(`AMA_BINANCE_ENABLE_PRIVATE_READ`) that can only read account / balance
/ position / income and can never place an order. PR111 does not flip,
read, or depend on PR110's `binance_private_api_enabled`, and PR110's
`LiveExecutionGateway` order path remains fully blocked.

**Withdraw permission is NEVER required.** If the API key reports
withdraw / high-risk permission, the health check raises
`BINANCE_PERMISSION_WARNING`. Prefer an API key without withdraw enabled.

### Precision / symbol rules
exchangeInfo is parsed into per-symbol filters (`tickSize`, `stepSize`,
`minQty`, `minNotional`, `pricePrecision`, `quantityPrecision`). Helpers:
`normalize_order_quantity`, `normalize_order_price`,
`validate_min_notional`, `validate_symbol_tradable`. PR111 only validates;
it never submits an order.

---

## 5. Telegram setup

The Telegram client masks the bot token everywhere. Outbound is gated by
`AMA_TELEGRAM_OUTBOUND_ENABLED` (default off). When disabled, the health
check reports `TELEGRAM_OUTBOUND_DISABLED` and never contacts the network.

Messages follow the operator contract banner:
`[ama-rt:<tag>] mode=<MODE> live=off <text>`.

A test message is only sent when outbound is enabled AND the operator
passes `--send-telegram-test`. No command-driven live switching is exposed
in PR111; a full operator console is a later PR (PR114).

---

## 6. DeepSeek setup

The DeepSeek client masks the API key. Output is **MARKET_INTELLIGENCE_ONLY**.
It may carry: `market_summary`, `evidence_summary`, `risk_notes`,
`operator_briefing`, `contradiction_notes`, `confidence_commentary`.

It must NOT carry any trade-authority field (`should_buy`, `should_sell`,
`direction`, `position_size`, `leverage`, `stop_price`, `take_profit`,
`order_type`, `execution_decision`, `runtime_config_patch`, ...). The
validator strips and flags any such field and emits
`DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`. Every result pins
`ai_trade_authority = false`.

---

## 7. Funding fee / commission accounting

Binance income rows (`/fapi/v1/income`) are mapped by
`app/live/binance_income.py` into **PR110's** Capital Event contract
(`app.live.capital_event`). Funding is **never mixed** with trading
price PnL — PR110's `CapitalEventLedger` keeps `total_funding` separate
from `total_realized_pnl`.

Recognised income types: `REALIZED_PNL`, `FUNDING_FEE`, `COMMISSION`,
`TRANSFER`, `INTERNAL_TRANSFER`, `WELCOME_BONUS`. Unknown / unmapped
types are preserved verbatim (`UNKNOWN_INCOME_TYPE`), tallied separately,
and **never** coerced into a capital-event type (so they can never
pollute realized PnL / fees / funding / deposits).

Mapping into PR110 `CapitalEventType`:
- `REALIZED_PNL` -> `REALIZED_PNL` (>=0) / `REALIZED_LOSS` (<0)
- `FUNDING_FEE` -> `FUNDING_INCOME` (>=0) / `FUNDING_FEE` (<0)
- `COMMISSION` -> `FEE`
- `TRANSFER` / `INTERNAL_TRANSFER` -> `TRANSFER_IN` (>=0) / `TRANSFER_OUT` (<0)
- `WELCOME_BONUS` -> `EXTERNAL_DEPOSIT` (inferable external credit)

The summary (`BinanceIncomeSummary`, backed by PR110's
`CapitalEventLedger`) exposes:
```
gross_realized_pnl   (= ledger.total_realized_pnl)
commission_total     (= ledger.total_fees)
funding_total        (= ledger.total_funding)
net_strategy_pnl = gross_realized_pnl - commission_total + funding_total
```
```

When funding cannot yet be attributed to a `trade_id`, it is stored as an
account-level event with
`attribution_status = UNATTRIBUTED_PENDING_POSITION_LINK`.

**HANDOFF(PR113/PR114):** position-level funding attribution MUST be added
before real live PnL is considered final. PR111 only does account-level
classification.

---

## 8. Audit events

`API_SECRET_LOADED_MASKED`, `API_HEALTH_CHECK_STARTED`,
`API_HEALTH_CHECK_COMPLETED`, `BINANCE_PUBLIC_HEALTH_OK`,
`BINANCE_PRIVATE_READ_OK`, `BINANCE_PRIVATE_TRADE_BLOCKED`,
`BINANCE_PERMISSION_WARNING`, `BINANCE_ACCOUNT_SNAPSHOT_READ`,
`BINANCE_INCOME_HISTORY_READ`, `FUNDING_EVENT_DETECTED`,
`COMMISSION_EVENT_DETECTED`, `TELEGRAM_TEST_MESSAGE_SENT`,
`TELEGRAM_OUTBOUND_DISABLED`, `DEEPSEEK_HEALTH_OK`,
`DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`.

Every payload is safe for logs: no API key, no secret, no token, no full
signature, no sensitive account identifier beyond an allowed masked form.

---

## 9. Warnings (read before configuring keys)

1. **PR111 does NOT enable live orders.** The order path is blocked.
2. **Avoid withdraw permission** on API keys where possible. PR111 never
   requires it and warns if it is present.
3. **LIVE_SHADOW remains the default.** PR111 never auto-escalates.
4. The next PR after PR111 is the live capital / risk / execution
   integration (LIVE_LIMITED 10U small-capital path), still behind the
   Risk Engine + Execution FSM.
