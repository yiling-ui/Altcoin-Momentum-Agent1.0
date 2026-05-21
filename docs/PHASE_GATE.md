# AMA-RT Phase Gate Ledger

Single canonical record of which phases have closed, which are open,
and what the gate criteria for the next phase look like. Each phase
must have an explicit acceptance record before the next phase opens.

The five Phase 1 safety flags REMAIN LOCKED across every phase below;
**no phase in this document loosens them**. Loosening any of them is a
Phase 12+ concern and requires the Spec §41 Go/No-Go checklist.

## Closed phases

| #     | Title                                              | Closed (UTC)    | Acceptance evidence                                            |
| ----- | -------------------------------------------------- | --------------- | -------------------------------------------------------------- |
| 1     | Safety Foundation                                  | 2025-10 (est.)  | `docs/CHANGELOG.md`                                            |
| 2     | Event Sourcing + Database Set                      | 2025-10 (est.)  | `docs/CHANGELOG.md`                                            |
| 3     | Exchange Gateway (read-only abstract)              | 2025-11 (est.)  | `docs/CHANGELOG.md`, `tests/unit/test_phase3_no_network.py`    |
| 4     | Market Data Buffer                                 | 2025-11 (est.)  | `docs/CHANGELOG.md`, `tests/unit/test_phase4_no_network.py`    |
| 5     | Regime + Universe + Liquidity                      | 2025-12 (est.)  | `docs/CHANGELOG.md`                                            |
| 6     | Pre-Anomaly + Anomaly + Confirmation + Manipulation | 2025-12 (est.) | `docs/CHANGELOG.md`                                            |
| 7     | Risk Engine + No-Trade Gate + Account Tier         | 2026-01 (est.)  | `docs/CHANGELOG.md`                                            |
| 8     | Capital Flow Engine                                | 2026-02 (est.)  | `docs/CHANGELOG.md`                                            |
| 8.5   | Learning-Ready Data Contract                       | 2026-02 (est.)  | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`                   |
| 9     | Execution FSM + Reconciliation                     | 2026-03 (est.)  | `docs/CHANGELOG.md`                                            |
| 10A   | Replay Engine substrate                            | 2026-03 (est.)  | `docs/CHANGELOG.md`                                            |
| 10B   | Reflection + Replay (read-only)                    | 2026-04 (est.)  | `docs/CHANGELOG.md`                                            |
| 10C   | LLM Guarded Interpreter (receive-only)             | 2026-04 (est.)  | `docs/CHANGELOG.md`                                            |
| 10D   | Telegram Outbound + Export Commands                | 2026-05 (est.)  | `docs/CHANGELOG.md`                                            |
| 11B   | Cloud Paper Acceptance                             | 2026-05-19      | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`                    |
| 11B-HF | Cloud Paper - High-Frequency observation          | 2026-05-19      | 30/30 dry-run PASS; 648/648 24h@2min observations PASS         |

### Phase 11B-HF acceptance summary

```
30x dry-run:        30/30 PASS
24h / 2min HF run observed: 648 PASS
go_decision=GO:     648
accepted=True:      648
FAIL:                 0
ERROR:                0
mode:               paper
live_trading:       False
right_tail:         False
llm:                False
exchange_live_orders: False
telegram_outbound_enabled: False
real Binance API:   not connected
real Telegram:      not connected
real DeepSeek:      not connected
```

## Open phase: Phase 11C

**Phase 11C - Real Binance Public Market Data Read-Only Paper.**
First phase that talks to a real exchange. Public-market REST only;
no API key; no signed endpoint; no account / position / leverage /
margin endpoint; no real order; no DeepSeek; no Telegram outbound.

### Phase 11C boundary (must hold for the entire run)

| Invariant                                | Required value               |
| ---------------------------------------- | ---------------------------- |
| `mode`                                   | `paper`                      |
| `live_trading`                           | `False`                      |
| `right_tail`                             | `False`                      |
| `llm`                                    | `False`                      |
| `exchange_live_orders`                   | `False`                      |
| `telegram_outbound_enabled`              | `False`                      |
| `binance_private_api_enabled`            | `False`                      |
| `safety.forbid_private_credentials`      | `True`                       |
| `safety.forbid_signed_endpoints`         | `True`                       |
| `safety.forbid_trade_endpoints`          | `True`                       |
| `safety.forbid_account_endpoints`        | `True`                       |
| `safety.forbid_position_endpoints`       | `True`                       |
| `safety.forbid_leverage_endpoints`       | `True`                       |
| `safety.forbid_margin_endpoints`         | `True`                       |
| `safety.forbid_live_trading`             | `True`                       |
| `safety.forbid_right_tail`               | `True`                       |
| `safety.forbid_llm_trade_decisions`      | `True`                       |
| `safety.forbid_telegram_outbound`        | `True`                       |
| `market_data.provider`                   | `binance_public`             |
| `market_data.read_only`                  | `True`                       |
| `market_data.symbol_limit`               | `(0, 200]`, default 20       |

### Phase 11C acceptance criteria

1. `pytest` 全部通过.
2. `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20`
   completes without exception, producing a daily report at
   `data/reports/phase11c/{date}-phase11c-public-market.md`.
3. Real `MARKET_SNAPSHOT` events written to `events.db` carry the
   Phase 11C tag (`provider="binance_public"`, `phase="11C"`).
4. `SignalSnapshot` is built from real market data and written into
   the `learning_ready.signal_snapshot` block of every `RISK_REJECTED`
   / `STATE_TRANSITION` event.
5. `RISK_REJECTED` events carry `learning_ready.opportunity` with a
   real `opportunity_id` / `scan_batch_id` / `symbol` /
   `source_phase = "phase_11c_public_market_paper"` plus typed
   `reject_reasons` containing `"stop_unconfirmed"`.
6. `VirtualTradePlan` saved and round-trips through
   `payload_to_virtual_trade_plan`.
7. The Phase 8.5 export zip contains the dedicated streams
   (`opportunities.jsonl`, `signal_snapshots.jsonl`,
   `virtual_trade_plans.jsonl`, `risk_decisions.jsonl`,
   `state_transitions.jsonl`) populated from real-data events.
8. The Replay engine reads every Phase 11C event type without error.
9. The Reflection engine reads the Phase 11C event payload shape
   without error.
10. `assert_public_endpoint_allowed` rejects every signed / private
    endpoint listed in `FORBIDDEN_PRIVATE_ENDPOINTS`.
11. The four `ExchangeClientBase` write surfaces continue to raise
    `SafeModeViolation` on the public client.
12. The Phase 11C source-tree audit
    (`tests/unit/test_phase11c_no_network.py`) holds: no third-party
    HTTP / WebSocket / SDK / LLM / Telegram bot import; no write
    surface call; no credential-shaped parameter; no env-var read.

### What Phase 11C is allowed to read from Binance

```
GET /fapi/v1/exchangeInfo
GET /fapi/v1/ticker/24hr
GET /fapi/v1/ticker/bookTicker
GET /fapi/v1/klines
GET /fapi/v1/aggTrades
GET /fapi/v1/trades
GET /fapi/v1/depth
GET /fapi/v1/fundingRate
GET /fapi/v1/openInterest
GET /fapi/v1/premiumIndex
```

### What Phase 11C is NOT allowed to do (refused by the client)

- API key
- API secret
- any signed endpoint
- `signature` / `timestamp` / `recvWindow` / `apiKey` query parameter
- `/fapi/v1/order` / `/fapi/v1/order/test` / `/fapi/v1/batchOrders`
- `/fapi/v1/allOrders` / `/fapi/v1/openOrders` / `/fapi/v1/openOrder`
- `/fapi/v2/account` / `/fapi/v2/balance` / `/fapi/v2/positionRisk`
- `/fapi/v1/positionRisk` / `/fapi/v1/positionSide/dual`
- `/fapi/v1/leverage` / `/fapi/v1/marginType` / `/fapi/v1/positionMargin`
- `/fapi/v1/income` / `/fapi/v1/leverageBracket`
- `/fapi/v1/multiAssetsMargin` / `/fapi/v1/listenKey`
- any other non-allowlisted path

## Future phases

| Candidate          | Gate                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------- |
| Phase 11C+ (longer paper window, e.g. 7d / 14d) | Phase 11C 24h acceptance closed                                       |
| Phase 11D (DeepSeek READ-ONLY narrative interpreter) | Phase 11C closed; Phase 11C dataset reviewed                     |
| Phase 12 (Limited live)                         | NOT permitted from Phase 11C alone. Requires Spec §41 Go/No-Go.       |

**Phase 11C closing does NOT authorise Phase 12.** Phase 12 is gated
by:

  - Spec §41 Go/No-Go checklist
  - Phase 11D (or another Phase 11C+ window) closed
  - Multi-week paper-mode dataset reviewed
  - Operational evidence the four write surfaces, the No-Trade Gate,
    and the Reconciliation loop have held under real-data load
