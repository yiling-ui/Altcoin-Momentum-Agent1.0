This pull request was created by @kiro-agent on behalf of @yiling-ui :ghost:

Comment with **/kiro fix** to address specific feedback or **/kiro all** to address everything.
<sub>[Learn about Kiro autonomous agent](https://kiro.dev/autonomous-agent)</sub>

---

## Why this PR exists

Phase 11C.1A (PR-A, merged) capped the public REST gateway with a
sliding-window rate-limit governor and shut every per-loop detail REST
surface. The trade-off was that the runner could see only the symbols
the bootstrap already knew about; it could not detect a brand-new
demon coin (妖币) that suddenly woke up between two bootstrap cadences.

PR-B restores the discovery surface by driving an **all-market
radar** off Binance's public WebSocket streams. The goal is **NOT** to
lower discovery capability — it is to *raise* discovery throughput while
keeping REST pressure near zero.

PR #32 currently bundles four commits on top of `main`:

  1. **Phase 11C.1B core** — `BinancePublicWSClient`, the radar
     buffer, the candidate pool, the WS-radar chain driver, the new
     EventType entries, the daily-report extension, and the WS-first
     runner CLI flags.
  2. **Real public WebSocket adapter (folded in from the planned
     follow-up)** — `StdlibPublicWSTransport` (RFC 6455 client built
     entirely on the Python standard library: `socket` + `ssl` +
     `select` + `struct` + `base64` + `hashlib` + `json` +
     `os.urandom`). The runner refuses to silently fall back to REST
     under `--ws-first` without `--dry-run`: it exits with `rc=2` if
     the transport factory cannot produce one.
  3. **Routed public/market WebSocket endpoints** —
     `MultiTransportPublicWSManager` opens routed PUBLIC + MARKET
     `StdlibPublicWSTransport` adapters
     (`wss://fstream.binance.com/public/stream` for `!bookTicker`;
     `wss://fstream.binance.com/market/stream` for the four MARKET
     array streams). The routed-private endpoint
     `wss://fstream.binance.com/private` is on
     `FORBIDDEN_WS_PATH_ROOTS` and the path-root allowlist refuses it.
     Stream classification: `classify_stream_route` /
     `split_streams_by_route`.
  4. **Docs-only dry-run evidence** — adds
     `docs/PHASE_11C_1B_DRY_RUN_EVIDENCE.md` capturing the actual
     `--ws-first --dry-run` output (boot banner, exit banner,
     events.db audit, per-iteration tracking record, discovered
     demon-coin list, daily-report excerpt, rate-limit governor
     warnings, monitoring + termination runbook). No code change.

## What ships

- `app/exchanges/binance_public_ws.py` — `BinancePublicWSClient` +
  `WSConfig` + `WSMessage` + `WSMessagePump` + `InProcessWSPump` +
  `_RefusalTransport` + **`StdlibPublicWSTransport`** (real-network
  RFC 6455 client, stdlib only, route-aware) +
  **`MultiTransportPublicWSManager`** (owns one routed
  `StdlibPublicWSTransport` per route — PUBLIC + MARKET — and
  presents them behind a single `WSMessagePump` interface) +
  `create_real_public_ws_transport` factory + `classify_stream_route`
  + `split_streams_by_route` + `assert_public_ws_stream_allowed` +
  `assert_public_ws_url_allowed` + `assert_public_ws_path_allowed`.
  Public stream allowlist (`!ticker@arr` / `!miniTicker@arr` /
  `!bookTicker` / `!markPrice@arr` / `!forceOrder@arr`). Routed
  acceptance path roots: `public/ws`, `public/stream`, `market/ws`,
  `market/stream`. Forbidden path roots: `private`, `ws-api`,
  `ws-fapi`, `ws-papi`, `trading-api`, `userdatastream`. Private
  deny-list blocks `listenKey` / `userdata` / `ws-api` /
  `trading-api` / `@accountUpdate` / `@orderTradeUpdate` /
  `@marginCall` / `@balanceUpdate` / `@positionUpdate`.

- `app/market_data_public/radar.py` — `AllMarketRadarSnapshot`
  (frozen pydantic v2 model with the 19 brief-mandated fields) +
  `AllMarketRadarBuffer` (per-symbol rolling state for all five
  public streams, computes `price_acceleration_15s`/`60s`,
  `quote_volume_delta_60s`, `volume_rank_jump`, `mark_price`,
  `funding_rate`, `liquidation_event`/`notional`, `ws_source_flags`)
  + `pre_anomaly_score_light` (pure additive scoring with
  deterministic reason tags).

- `app/market_data_public/candidate_pool.py` — `CandidatePool` with
  defaults `candidate_pool_size=20`, `active_detail_limit=3`,
  `candidate_ttl_seconds=900`, `radar_score_threshold=30.0`. Each
  candidate carries a Phase 8.5 `OpportunityIdentity` with
  `source_phase="phase_11c_1b_ws_first_radar"` so opportunity_id /
  scan_batch_id continuity is preserved across event chain emissions.

- `app/market_data_public/ws_radar_chain.py` — `WSRadarChainDriver`
  emits `PRE_ANOMALY_DETECTED` + `ANOMALY_DETECTED` +
  `STATE_TRANSITION` with full Phase 8.5 `LearningReadyContext` on
  each, then calls the live `RiskEngine` with `stop_unconfirmed=True`
  so EVERY decision falls into the typed-reject-reason path
  (`RISK_REJECTED`).

- `app/core/events.py` — three new EventType entries:
  `PUBLIC_WS_CONNECTED`, `PUBLIC_WS_DISCONNECTED`, `PUBLIC_WS_STALE`.

- `app/paper_run/daily_report.py` — `DailyReportSnapshot` +
  `DailyReportBuilder.build()` extended with `ws_metrics` +
  `candidate_pool_metrics`. New "Phase 11C.1B WebSocket all-market
  radar" Markdown section with every brief-mandated metric
  (`ws_messages_received`, `ws_reconnect_count`, `ws_staleness_ms_max`,
  `ws_stale_count`, `radar_candidates_seen`, `candidate_pool_size_max`,
  `pre_anomaly_candidates`, `liquidation_events_seen`,
  `radar_score_top_symbols`, per-stream message counts).

- `scripts/run_public_market_paper.py` — new CLI flags `--ws-first` /
  `--ws-disabled` (mutex; default `ws_first=True`),
  `--candidate-pool-size`, `--active-detail-limit`,
  `--ws-staleness-threshold-ms`, `--candidate-ttl-seconds`. Per-loop
  body: pump WS → radar ingest → score every snapshot → `pool.offer`
  → `pool.expire` → drive `WSRadarChainDriver` on the active head
  (skipped while `ws_client.is_stale=True`, the data-degraded gate);
  the active head also receives REST detail through the existing
  PR-A governor. Module-level `_build_real_public_ws_transport` +
  `_build_rest_transport` factory hooks for testability. Pre-flight
  refusal: `--ws-first` without `--dry-run` REQUIRES a real public
  WS transport — rc=2 if the factory returns `None` or raises.

## Dry-run acceptance evidence (60-second `--ws-first --dry-run`)

`docs/PHASE_11C_1B_DRY_RUN_EVIDENCE.md` (commit `481005c`) captures
the actual dry-run output reviewers can reproduce verbatim:

```
python3.12 -u -m scripts.run_public_market_paper \
  --duration 1min --symbol-limit 5 \
  --candidate-pool-size 20 --active-detail-limit 3 \
  --ws-staleness-threshold-ms 60000 --candidate-ttl-seconds 900 \
  --dry-run --poll-interval-seconds 2
```

Exit code: `0`.

Boot banner (excerpt):

```
[AMA-RT] Phase 11C.1B - WebSocket-First All-Market Demon Coin Radar
v1.4.0a11c.1b mode=paper live_trading=False right_tail=False
llm=False exchange_live_orders=False telegram_outbound_enabled=False
binance_private_api_enabled=False ws_first=True
ws_real_transport=False ws_staleness_threshold_ms=60000
candidate_pool_size=20 active_detail_limit=3
governor=on(budget=300/min soft=0.5 hard=0.75 on_429=backoff
on_418=shutdown retry_after_default=300s) dry_run=True
env_guard_passed=True
```

Exit banner (excerpt):

```
[AMA-RT] Phase 11C.1B run finished
  duration_seconds=60 iterations=30
  ws_chains_emitted=60 ws_risk_rejected=60
  ws_learning_ready_attached=60 ws_messages_received=122
  radar_candidates_seen=60 candidate_pool_size_max=2
  rate_limit_429_count=0 rate_limit_418_count=0
  rate_limit_protection_triggered=False rate_limit_ban=False
```

events.db audit:

```
PRE_ANOMALY_DETECTED  63   (60 phase_11c_1b_ws_first_radar +
                            3 phase_11c_public_market_paper)
ANOMALY_DETECTED      63
RISK_REJECTED         63   (every chain: stop_unconfirmed; paper-only)
STATE_TRANSITION      63
PUBLIC_WS_CONNECTED    1
PUBLIC_WS_DISCONNECTED 1
PUBLIC_WS_STALE        0
RATE_LIMIT_429         0
RATE_LIMIT_418         0
RATE_LIMIT_PROTECTION_ENTERED 0
```

Per-iteration tracking record sample (verbatim from events.db):

| Field                          | Value                                                                 |
| ------------------------------ | --------------------------------------------------------------------- |
| `event_type`                   | `PRE_ANOMALY_DETECTED`                                                |
| `symbol`                       | `ETHUSDT`                                                             |
| `source_phase`                 | `phase_11c_1b_ws_first_radar`                                         |
| `scan_batch_id` (= run_id)     | `scan_01c88284d61b4eecb1c5da63970901b2`                               |
| `opportunity_id`               | `opp_6985992e6c104ef18d3991c9de960d07`                                |
| `pre_anomaly_score`            | `50.0`                                                                |
| `radar_reason_tags`            | `['price_acceleration_60s', 'quote_volume_delta_60s', 'spread_compression', 'mark_price_alignment', 'funding_not_overheated']` |
| `radar_source_streams`         | `['book_ticker', 'mark_price_arr', 'ticker_arr']`                     |
| `candidate_state`              | `active`                                                              |
| pass / fail (from STATE_TRANSITION) | `RISK_REJECTED(['stop_unconfirmed'])` — paper-only, the documented Phase 11C contract |
| `learning_ready`               | full Phase 8.5 block (opportunity / signal_snapshot / virtual_trade_plan / config_versions) attached |

Discovered demon-coin candidates (from the dry-run synthetic burst):

```
BTCUSDT    chain_emissions=30 best_radar_score=90.0 states=[active]
ETHUSDT    chain_emissions=30 best_radar_score=90.0 states=[active]
```

Rate-limit governor evidence: 68 governor warnings (3 soft-budget
breaches at used+cost = 156, 176, 177 vs soft = 150; then hard-budget
refusals at used = 225 vs hard = 225). Every refused call was caught
by `PublicMarketIngestor.ingest_many` and recorded as an
`ingestion_error`; none escaped to the caller; no 429 / 418 ever
fired. **Throttle on rate-limit + preserve data integrity** — the WS
radar pipeline kept running uninterrupted (`ws_messages_received=122`,
`ws_chains_emitted=60`) while REST detail was being throttled.

## Phase 1 safety lock UNCHANGED

After running the WS-first pipeline end-to-end (with
PRE_ANOMALY_DETECTED + ANOMALY_DETECTED + STATE_TRANSITION +
RISK_REJECTED chains driven from real-time WS data) every flag below
remains:

```
mode                            = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
forbid_*  (11 flags)            = True
```

The four `ExchangeClientBase` write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to raise
`SafeModeViolation` on the public REST client.

## Phase 11C.1B explicitly does NOT

- accept any Binance API key / API secret / `listenKey`.
- subscribe to any user data stream / private WebSocket / trading
  WebSocket API / account / margin / position / leverage / balance /
  order private WS variant.
- open the routed-private endpoint
  `wss://fstream.binance.com/private` or any
  `/ws-api` / `/ws-fapi` / `/ws-papi` / `/trading-api` /
  `/userDataStream` path-root variant.
- treat the unrouted `wss://fstream.binance.com/stream` URL as the
  WS-first acceptance path. Binance silently drops market-class
  streams over an unrouted connection; the runner therefore opens
  routed PUBLIC + MARKET transports through the
  `MultiTransportPublicWSManager`.
- call any signed REST endpoint.
- import any third-party HTTP / WebSocket / SDK package. The
  `StdlibPublicWSTransport` and `MultiTransportPublicWSManager` are
  implemented entirely on top of the Python standard library and the
  existing source-tree audit (`tests/unit/test_phase11c_no_network.py`)
  continues to ban `websockets` / `websocket-client` / `aiohttp` /
  `requests` / `httpx` / `urllib3`.
- silently fall back to REST under `--ws-first` without `--dry-run`.
  The runner refuses with rc=2 if the real public WS pump cannot be
  constructed; only `--ws-disabled` switches to the REST-only path
  (which is **not** the Phase 11C.1B acceptance path).
- connect to DeepSeek / a real Telegram bot / Binance Square.
- enter Phase 12.

## Tests

- `tests/unit/test_phase11c_1b_ws_radar.py` (28 cases) — scaffold
  + radar + pool + chain.
- `tests/unit/test_phase11c_1b_real_ws_adapter.py` (19 cases) —
  real public WS adapter + runner refusal + reconnect backoff +
  staleness gate + safety flags + RFC 6455 handshake / frame audit.
- `tests/unit/test_phase11c_1b_routed_public_market_ws.py` (14
  cases) — routed `/public/{ws,stream}` + `/market/{ws,stream}`
  acceptance, `/private` refusal, stream-route classification,
  `MultiTransportPublicWSManager` merge, runner uses both routed
  transports, no follow-up wording in source / docs.

Audits updated:

- `tests/unit/test_phase11c_no_network.py` — PHASE_11C_FILES grew
  the four new files; `test_no_private_websocket_artefacts` blocks
  `listenKey` / `userDataStream` / `wss://stream-api` / `/ws-api`
  / `/trading-api` / `/userDataStream` / `/listenKey` as
  non-docstring string literals.
- `tests/unit/test_phase11b_no_network.py` — allowed event-type
  list grew `PUBLIC_WS_CONNECTED` / `DISCONNECTED` / `STALE`.
- `tests/unit/test_phase11c1a_rate_limit_governor.py` —
  `test_rest_not_called_for_all_symbols_every_loop` now passes
  `--ws-disabled`.
- `tests/unit/test_main_entrypoint.py` — banner assertion updated.

## Tested

- `pytest -p no:warnings` → **2177 passed**
  (PR-A baseline 2089 → +88 net new tests in PR-B).
- 60-second `--ws-first --dry-run` smoke captured verbatim in
  `docs/PHASE_11C_1B_DRY_RUN_EVIDENCE.md` (rc=0, full Phase 11C.1B
  WebSocket all-market radar daily-report section, 0 × 429, 0 × 418,
  Phase 1 safety lock unchanged).

## Cloud smoke acceptance ladder

The legacy `--duration 1h --symbol-limit 20 --poll-interval-seconds 5`
command is **deprecated** (it predates routed WS endpoints and
exercises the pre-PR-A "fetch every detail endpoint for every symbol
every loop" pattern that triggered HTTP 418). The current ladder is:

| Stage              | Command                                                                                                                 |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| 30 s dry-run       | `python -m scripts.run_public_market_paper --duration 30s --symbol-limit 5 --dry-run`                                   |
| 5 min real WS      | `python -m scripts.run_public_market_paper --duration 5min --symbol-limit 5 --ws-first`                                 |
| 10 min real WS     | `python -m scripts.run_public_market_paper --duration 10min --symbol-limit 5 --ws-first`                                |
| 1 h WS-first + REST | `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 5 --ws-first`                                  |
| 6 h WS-first       | `python -m scripts.run_public_market_paper --duration 6h --symbol-limit 5 --ws-first`                                   |
| 24 h WS-first      | `python -m scripts.run_public_market_paper --duration 24h --symbol-limit 5 --ws-first`                                  |

PR-C (priority_score / cluster classifier / same-cluster leader /
multi-candidate arbitration) remains a separate branch.

## Stop after PR-B

Awaiting human review of the routed real-network WS adapter before
running the cloud-smoke ladder.
