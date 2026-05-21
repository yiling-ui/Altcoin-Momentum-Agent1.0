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

## Open phase: Phase 11C.1B

**Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar (PR-B).**
Phase 11C.1A (PR-A) shipped the rate-limit governor and capped per-loop
REST detail; the trade-off was that the runner could see only the
symbols the bootstrap already knew about. PR-B adds the WebSocket-first
all-market radar so the runner can discover demon coins (妖币) without
per-symbol REST detail polling. The goal is not to lower discovery
capability - it is to *raise* discovery throughput while keeping REST
pressure near zero.

PR-B subscribes to FIVE public Binance WebSocket streams only:

  - `!ticker@arr`
  - `!miniTicker@arr`
  - `!bookTicker`
  - `!markPrice@arr`
  - `!forceOrder@arr`

PR-B does NOT subscribe to `listenKey`, the user data stream, the
trading WebSocket API, or any private WebSocket. The default WS
transport refuses to open a real socket (`NotImplementedError`); the
in-process pump is wired under `--dry-run` and the stdlib WS adapter
is a follow-up PR.

### Phase 11C.1B boundary (must hold for the entire PR-B scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| Binance API key / secret                    | refused at construction      |
| Signed endpoint                             | refused at allowlist check   |
| `listenKey` / user data stream              | refused at WS allowlist + URL parser |
| Private WebSocket / trading WS API          | refused at WS allowlist      |
| `market_data.provider`                      | `binance_public`             |
| `market_data.read_only`                     | `True`                       |
| `candidate_pool_size` (default)             | `20`                         |
| `active_detail_limit` (default)             | `3`                          |
| `candidate_ttl_seconds` (default)           | `900`                        |
| `ws_staleness_threshold_ms` (default)       | `3000`                       |
| `radar_score_threshold` (default)           | `30.0`                       |

### Phase 11C.1B acceptance criteria

1. `pytest` 全部通过. Currently `2144 passed`.
2. The new test file
   `tests/unit/test_phase11c_1b_ws_radar.py` pins every behaviour
   the brief calls out (15 explicit + 13 supporting). Full list in
   `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B.
3. The four `ExchangeClientBase` write surfaces still raise
   `SafeModeViolation`.
4. No file in the Phase 11C source set imports a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package.
5. The Phase 11B daily-report Markdown body contains the new
   `Phase 11C.1B WebSocket all-market radar` section with every
   brief-mandated metric.
6. The Phase 8.5 export, Phase 10A replay, and Phase 10B reflection
   pipelines accept the three new `PUBLIC_WS_*` event types.

### Phase 11C.1B explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret /
    `listenKey`.
  - Calling any signed endpoint.
  - Subscribing to any user data stream / private WebSocket /
    trading WebSocket API / account / margin / position / leverage
    / balance / order private WS variant.
  - Connecting to DeepSeek.
  - Connecting to the real Telegram outbound HTTP transport.
  - Connecting to Binance Square.
  - Auto-retrying after a 418.
  - Switching endpoints to evade a 418.
  - Rotating source IP to evade a 418.
  - Entering Phase 12.

### How Phase 11C.1B unblocks the Phase 11C real-data acceptance run

After PR-B merges (and once the stdlib WS adapter follow-up PR
lands), the Phase 11C real-data 24h acceptance run resumes with:

  - bootstrap REST: one `exchangeInfo` + one `ticker/24hr`.
  - public WS: 5 ALLOWLIST streams covering every USDT-M perpetual.
  - candidate pool: top N (default 20) demon coins, active head 3.
  - per-loop REST detail: ONLY for the active head, gated on the
    PR-A rate-limit governor.

PR-C (cluster exposure control) remains a separate branch.

## Closed phase: Phase 11C.1A

**Phase 11C.1A - Binance Public REST Rate Limit Governor & 418
Protection (PR-A).** Merged. Phase 11C real-data acceptance is paused
until PR-B + the stdlib WS adapter follow-up land.

  - **PR-A** (closed, `feature/phase-11c1-rest-rate-limit-governor`)
    ships `BinancePublicRestGovernor` (sliding-window weight budget,
    429 backoff, 418 shutdown, `Retry-After`, used-weight tracking),
    lower defaults, and the layered REST runner. NO new candidate
    ranking, NO WebSocket transport.
  - **PR-B** (this branch, `feature/phase-11c1-ws-first-all-market-radar`)
    ships the WebSocket-first all-market radar +
    multi-candidate priority ranking + `candidate_detail_limit`
    consumption. The default WS transport refuses to open a real
    socket; the in-process pump covers `--dry-run`; the stdlib WS
    adapter is a follow-up PR.
  - **PR-C** (separate branch, NOT in this PR) ships cluster
    exposure control.

### Phase 11C.1A boundary (must hold for the entire PR-A scope)

| Invariant                                   | Required value               |
| ------------------------------------------- | ---------------------------- |
| `mode`                                      | `paper`                      |
| `live_trading`                              | `False`                      |
| `right_tail`                                | `False`                      |
| `llm`                                       | `False`                      |
| `exchange_live_orders`                      | `False`                      |
| `telegram_outbound_enabled`                 | `False`                      |
| `telegram.outbound_enabled` (schema-locked) | `False`                      |
| `binance_private_api_enabled`               | `False`                      |
| `safety.forbid_*` (11 flags)                | `True` for every flag        |
| `market_data.provider`                      | `binance_public`             |
| `market_data.read_only`                     | `True`                       |
| `market_data.symbol_limit` (default)        | `5` (was `20`, lowered)      |
| `market_data.rest_poll_interval_seconds` (default) | `60.0` (was `5.0`)    |
| `market_data.rest_governor.weight_budget_per_minute` | `300`              |
| `market_data.rest_governor.soft_weight_ratio`        | `0.50`             |
| `market_data.rest_governor.hard_weight_ratio`        | `0.75`             |
| `market_data.rest_governor.retry_after_default_seconds` | `300`           |
| `market_data.rest_governor.on_429`          | `"backoff"` (only allowed)   |
| `market_data.rest_governor.on_418`          | `"shutdown"` (only allowed)  |
| `market_data.rest_governor.candidate_detail_limit` | `3`                   |
| `market_data.rest_governor.rest_layering_enabled`  | `True`                |

### Phase 11C.1A acceptance criteria

1. `pytest` 全部通过 (currently `2089 passed`).
2. The new test file `tests/unit/test_phase11c1a_rate_limit_governor.py`
   pins, at minimum, every behaviour the brief calls out:
   - `test_429_triggers_backoff_and_stops_batch`
   - `test_418_triggers_shutdown_without_retry`
   - `test_retry_after_header_is_respected`
   - `test_used_weight_header_is_recorded`
   - `test_rest_governor_blocks_when_budget_exceeded`
   - `test_default_phase11c_polling_is_conservative`
   - `test_rest_not_called_for_all_symbols_every_loop`
   - `test_no_live_trading_flags_after_429`
   - `test_no_live_trading_flags_after_418`
   - `test_daily_report_contains_rate_limit_metrics`
3. The four `ExchangeClientBase` write surfaces still raise
   :class:`SafeModeViolation` (asserted by
   `test_phase_11c_write_surfaces_still_refuse_after_418` even after
   the governor latches into protection mode).
4. The Phase 8.5 export pipeline accepts the five new
   `RATE_LIMIT_*` event types.
5. The Phase 10A replay engine accepts the new events (no schema
   regression - asserted by the existing replay test suite).
6. The Phase 10B reflection engine accepts the new events.
7. The daily Markdown report contains the `Phase 11C.1A
   rate-limit governor` section with every required field.
8. No `binance_rate_limit.py` import touches a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package; only stdlib +
   loguru + the existing `app.*` modules.

### Phase 11C.1A explicitly forbids

  - Connecting to the Binance trading API.
  - Reading or storing any Binance API key / API secret.
  - Calling any signed endpoint.
  - Calling any /order, /account, /position, /leverage, /margin endpoint.
  - Connecting to DeepSeek.
  - Connecting to the real Telegram outbound HTTP transport.
  - Auto-retrying after a 418.
  - Switching endpoints to evade a 418.
  - Rotating source IP to evade a 418.
  - Entering Phase 12.

### How Phase 11C.1A unblocks the Phase 11C real-data acceptance run

After PR-A merges:

  - The runner caps total per-IP weight at 300/min.
  - Bootstrap costs ~41 weight (one `exchangeInfo` + one
    `ticker/24hr`) and the steady-state loop costs ~0 weight in PR-A
    (no candidates -> no detail REST).
  - Any 429 sleeps the `Retry-After` window and emits the
    `RATE_LIMIT_429` / `RATE_LIMIT_BACKOFF_STARTED` /
    `RATE_LIMIT_BACKOFF_ENDED` audit trail.
  - Any 418 latches protection mode, opens a P1 incident, and
    stops the runner with `rc=2`. The runner does NOT auto-retry,
    does NOT switch endpoints, does NOT rotate source IP.

The Phase 11C real-data 24h acceptance run will resume only after
PR-B (WebSocket-first radar + candidate ranking) has also landed,
because PR-A on its own deliberately leaves the per-loop detail
REST silent.

## Closed phase: Phase 11C (held)

Phase 11C remains open as a parent phase; its real-data acceptance
run is paused until Phase 11C.1A + 11C.1B + 11C.1C ship. The
public-market client, allowlist, event chain, and runner skeleton
all continue to satisfy their original Phase 11C acceptance gates;
only the cadence and detail-REST behaviour have been narrowed.

## Closed phases (carry-forward)

The closed-phase ledger above remains unchanged. The Phase 11C
parent phase stays open until all three follow-up PRs land and the
real-data 24h acceptance run is reproduced.

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
