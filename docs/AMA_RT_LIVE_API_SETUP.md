# AMA-RT Live API Setup (PR111)

Step-by-step setup for the Binance / Telegram / DeepSeek live APIs.

> PR111 connects real read APIs but **never places a real order**. The
> default runtime mode is `LIVE_SHADOW`. You can run a full "shadow"
> session - real connectivity, real balances, real push - with zero
> trading risk.

---

## 0. Golden rules

- Never hard-code a secret. Put secrets in a local `.env` (gitignored) or
  a secrets manager. Never commit real keys.
- Prefer Binance API keys **without withdraw permission**. PR111 never
  needs withdraw and will warn if it is present.
- A missing secret never crashes the system - the health check reports
  `API_HEALTH_MISSING_SECRET`.
- `AMA_SECRET_LOGGING_ALLOWED` must remain `false`. PR111 never logs a raw
  secret regardless of its value.

---

## 1. Copy the example env

```bash
cp .env.example .env
# edit .env and fill in the values you want to test
```

The `.env` file is gitignored. The example file documents every variable.

---

## 2. Binance

1. Create an API key on Binance (futures-enabled).
2. **Disable withdraw permission.** Enable "Reading" (and "Futures" if you
   later want trade-capable reads). PR111 only reads.
3. Restrict the key by IP if your deployment has a static IP.
4. Set in `.env`:
   ```
   AMA_BINANCE_API_KEY=<your key>
   AMA_BINANCE_API_SECRET=<your secret>
   AMA_BINANCE_ENABLE_PRIVATE_READ=true
   ```
5. (Optional) Use the futures testnet:
   ```
   AMA_BINANCE_USE_TESTNET=true
   ```
6. Verify:
   ```bash
   python scripts/live_api_health_check.py --binance
   ```
   Expect `binance_public_status=PASS`. With a valid read key,
   `binance_private_read=PASS` and `can_read_account/positions/income=True`.
   A `high_risk_permission_warning=True` means your key still has withdraw
   enabled - disable it.

---

## 3. Telegram

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Find your chat id (e.g. send a message to the bot and read
   `getUpdates`, or use a chat-id helper bot).
3. Set in `.env`:
   ```
   AMA_TELEGRAM_BOT_TOKEN=<bot token>
   AMA_TELEGRAM_ALLOWED_CHAT_IDS=<your chat id>
   AMA_TELEGRAM_OUTBOUND_ENABLED=true
   ```
4. Verify (no message sent yet):
   ```bash
   python scripts/live_api_health_check.py --telegram
   ```
5. Send an explicit test message (opt-in):
   ```bash
   python scripts/live_api_health_check.py --telegram --send-telegram-test
   ```
   With outbound disabled, the health check reports
   `TELEGRAM_OUTBOUND_DISABLED` and sends nothing.

---

## 4. DeepSeek

1. Get a DeepSeek API key.
2. Set in `.env`:
   ```
   AMA_DEEPSEEK_API_KEY=<your key>
   AMA_DEEPSEEK_ENABLED=true
   ```
3. Verify (this calls the API):
   ```bash
   python scripts/live_api_health_check.py --deepseek
   ```
   Expect `deepseek_status=PASS` and `ai_trade_authority=false`. DeepSeek
   output is market-intelligence only; any trade-authority field in the
   response is stripped and flagged.

---

## 5. Full check

```bash
python scripts/live_api_health_check.py --all --json
```

Confirm in the report:
- `exchange_live_orders=false`
- `ai_trade_authority=false`
- `live_runtime_mode=LIVE_SHADOW`
- `secrets_masked=true`

---

## 6. Funding fee / commission accounting

Once private read works, income history is classified into the Capital
Event contract (funding / commission / realized PnL / transfers). Funding
is kept separate from trading PnL:

```
net_strategy_pnl = gross_realized_pnl - commission_total + funding_total
```

See `docs/AMA_RT_API_INTEGRATION_PACK.md` §7 for the full mapping.

---

## 7. Warnings

1. **PR111 does NOT enable live orders.** Even with a trade-capable key,
   the order path is blocked (`TRADE_API_BLOCKED_BY_PR111`).
2. **API keys should not include withdraw permission** if avoidable.
3. **LIVE_SHADOW remains the default** and PR111 never auto-escalates to
   LIVE_LIMITED.
4. The next PR after PR111 is the live capital / risk / execution
   integration.
