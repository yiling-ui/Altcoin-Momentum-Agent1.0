# AMA-RT Project Status

This document is the at-a-glance status board for AMA-RT V1.4. It is
intentionally short. The full phase-gate ledger lives in
`docs/PHASE_GATE.md`; per-phase deep dives live in their own
`PHASE_*` documents.

## Current phase

> **Phase 11C.1B = ACCEPTED.**
> **Phase 11C.1C = NEXT_ALLOWED / NOT_STARTED.**
> **We are still in paper mode. Phase 12 (real money / live trading)
> remains FORBIDDEN.**

The Phase 1 safety lock is unchanged across the Phase 11C.1B closeout:
`mode=paper`, `live_trading=False`, `right_tail=False`, `llm=False`,
`exchange_live_orders=False`, `telegram_outbound_enabled=False`,
`binance_private_api_enabled=False`. No Binance API key, no Binance
API secret, no signed endpoint, no private WebSocket, no `listenKey`,
no DeepSeek trade decision, no real Telegram outbound, no Phase 12.

| Date (UTC) | Phase    | Tag                                        | State   | Evidence                                                |
| ---------- | -------- | ------------------------------------------ | ------- | ------------------------------------------------------- |
| 2026-05-22 | Phase 11C.1C | Adaptive Candidate Regime & Strategy Selector | **NEXT_ALLOWED / NOT_STARTED** (paper-mode only; no implementation in this repo state) | `docs/PHASE_GATE.md` §"Open phase: Phase 11C.1C" |
| 2026-05-22 | Phase 11C.1B | WebSocket-First All-Market Demon Coin Radar (incl. SymbolUniverse exchangeInfo-as-truth, non-ASCII contracts allowed) | **ACCEPTED** — 5min / 10min / 1h real WS smoke PASS (no 429, no 418, no stale, no ingestion errors); export zip generated; events.db readable; PRs #31 / #32 / #33 / #34 merged; safety flags unchanged | `docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1B |
| 2026-05-21 | Phase 11C.1A | Binance Public REST Rate Limit Governor & 418 Protection | merged        | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md` §11C.1A     |
| 2026-05-21 | Phase 11C | Real Binance Public Market Data Read-Only Paper | open (parent); Phase 11C.1B (5min / 10min / 1h smoke) ACCEPTED 2026-05-22; longer-window (6h / 24h) acceptance still optional / not yet run | `docs/PHASE_11C_PUBLIC_MARKET_READONLY.md`             |
| 2026-05-19 | Phase 11B-HF | Cloud Paper - High-Frequency observation     | accepted (GO) | 30/30 dry-run PASS, 648/648 24h@2min observations PASS |
| 2026-05-19 | Phase 11B | Cloud Paper Acceptance                       | accepted (GO) | `docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md`            |
| ...        | Phase 10D | Telegram Outbound + Export Commands          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10C | LLM Guarded Interpreter (receive-only)       | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10B | Reflection + Replay engines (read-only)      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 10A | Replay engine substrate                      | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 9   | Execution FSM + Reconciliation               | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 8.5 | Learning-Ready Data Contract                 | merged        | `docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md`           |
| ...        | Phase 8   | Capital Flow Engine                          | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 7   | Risk Engine + No-Trade Gate                  | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 6   | Pre-Anomaly + Anomaly + Confirmation + Manipulation | merged | `docs/CHANGELOG.md`                                  |
| ...        | Phase 5   | Regime + Universe + Liquidity                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 4   | Market Data Buffer                           | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 3   | Exchange Gateway (read-only abstract)        | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 2   | Event Sourcing + Database Set                | merged        | `docs/CHANGELOG.md`                                    |
| ...        | Phase 1   | Safety Foundation                            | merged        | `docs/CHANGELOG.md`                                    |

## Live safety flags (Phase 1 lock)

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

The Phase 1 safety lock in `app/config/settings.py::_apply_phase1_safety_lock`
hard-coerces the first five flags. The Phase 11C
`MarketDataConfig` and `SafetyConfig` schemas refuse to load any
deployment that flips a `forbid_*` flag.

## Why the Phase 11C real-data acceptance was paused (historical, RESOLVED)

The first 24h test against the real Binance public REST endpoints
(`fapi.binance.com`) exposed two failure modes the original Phase 11C
runner did not protect against:

  1. HTTP 429 (Too Many Requests). Binance returned this once the
     per-IP weight budget was exceeded. The runner kept polling and
     escalated to:
  2. HTTP 418 (I'm a teapot). Binance uses 418 to signal a real IP
     ban.

Phase 11C's safety lock held throughout (`mode=paper`,
`live_trading=False`, no API key, no signed endpoint, no real order),
but the gateway was unusable for real-data acceptance until the
rate-limit problem is fixed.

**Phase 11C.1A** (PR #31) shipped the fix in three layers:

  - a new `BinancePublicRestGovernor`
    (`app/exchanges/binance_rate_limit.py`) that wraps every public
    REST call, tracks the rolling weight budget, sleeps the
    `Retry-After` window on 429, latches into protection mode on
    418, and opens a P1 incident;
  - lower defaults (`symbol_limit=5`, `rest_poll_interval_seconds=60`,
    `weight_budget_per_minute=300`, soft 0.50 / hard 0.75);
  - a layered REST runner that does `exchangeInfo` / `ticker/24hr`
    only at bootstrap and refuses per-symbol detail REST calls
    unless a candidate ranking selects them.

**Phase 11C.1B** (PRs #32 / #33 / #34) then shipped the WebSocket-first
all-market radar + the routed real-network public WS adapter + the
WS poll fix + the SymbolUniverse exchangeInfo-as-truth gate (non-ASCII
contracts admitted; ASCII-only regex banned). The 5min / 10min / 1h
real-WS smoke ladder now passes cleanly with zero 429 / 418 / stale /
ingestion errors. See "Phase 11C.1B acceptance evidence (closeout)"
below for the headline numerics.

PR-C (cluster exposure control + multi-candidate priority ranking)
remains a separate, future scope item and is **not** required for the
Phase 11C.1B closeout; it is tracked alongside the future
Phase 11C.1C — Adaptive Candidate Regime & Strategy Selector work.

## What Phase 11C is

Phase 11C is real **Binance public market data** read-only paper.
It connects to public REST endpoints (`/fapi/v1/exchangeInfo`,
`/fapi/v1/ticker/24hr`, `/fapi/v1/klines`, `/fapi/v1/aggTrades`,
`/fapi/v1/depth`, `/fapi/v1/fundingRate`, `/fapi/v1/openInterest`,
`/fapi/v1/premiumIndex`, `/fapi/v1/ticker/bookTicker`), feeds the
data through the existing `MarketDataBuffer` and Risk Engine, and
emits the full Phase 11C event chain into `events.db`.

## What Phase 11C is NOT

- NOT live trading
- NOT connected to the Binance trading API
- NOT consuming any Binance API key / API secret
- NOT calling any signed endpoint
- NOT calling any account / position / leverage / margin endpoint
- NOT connected to DeepSeek
- NOT connected to a real Telegram bot
- NOT connected to 币安广场
- NOT a path into Phase 12

## Open phase

**Phase 11C.1C — Adaptive Candidate Regime & Strategy Selector.**
NEXT_ALLOWED, NOT_STARTED. **No code in this repo state implements
Phase 11C.1C.** Phase 11C.1C must hold the same Phase 1 safety lock
and inherits every Phase 11C.1B forbidden item; in particular it MUST
NOT introduce a Strategy Selector with live-trading authority, MUST
NOT enable AI Learning that auto-decides trades, MUST NOT touch the
trading API, and MUST NOT enter Phase 12. The detailed gate criteria
will be drafted in `docs/PHASE_GATE.md` when Phase 11C.1C work
actually begins; until then it is intentionally blank.

## Phase 11C.1B acceptance evidence (closeout)

Phase 11C.1B closed on **2026-05-22 (UTC)** with the following
evidence on file. Full numerics live in
`docs/PHASE_GATE.md` §"Phase 11C.1B acceptance summary"; this section
is the at-a-glance summary.

### PRs that compose Phase 11C.1B

| PR    | Scope                                                                                                | Status |
| ----- | ---------------------------------------------------------------------------------------------------- | ------ |
| #31   | Phase 11C.1A — Binance Public REST Governor / 429 backoff / 418 shutdown protection                  | merged |
| #32   | Phase 11C.1B PR-B — WebSocket-first all-market radar; real `StdlibPublicWSTransport`; routed `/public/stream` + `/market/stream` | merged |
| #33   | Phase 11C.1B follow-up — fix real WS poll zero-timeout that left `ws_messages_received=0`             | merged |
| #34   | Phase 11C.1B follow-up — `SymbolUniverse` / exchangeInfo-as-truth; non-ASCII contracts admitted; ASCII-only regex banned | merged |

### Real-WS smoke ladder (PASS)

| Smoke run        | Duration | Outcome | Headline metrics                                                                                                              |
| ---------------- | -------- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 5 min real WS    | 5 min    | PASS    | `ws_messages_received=30317`, `ws_chains_emitted=12`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 10 min real WS   | 608 s    | PASS    | `ws_messages_received=59644`, `ws_chains_emitted=27`, `ingestion_errors=0`, `rate_limit_429_count=0`, `rate_limit_418_count=0`, `ws_stale_count=0` |
| 1 h real WS (clean) | 3600 s | PASS    | `dry_run=false`, `ws_real_transport=true`, `ws_messages_received=349134`, `ws_chains_emitted=177`, `ws_learning_ready_attached=177`, `snapshots_emitted=177`, `ingestion_errors=0`, `HTTP 429 count=0`, `HTTP 418 count=0`, `rate_limit_ban=False`, `ws_reconnect_count=0`, `ws_staleness_ms_max=0`, `ws_stale_count=0`, `ws_currently_stale=False` |

### Persistence + export evidence

  - `events.db` readable: `events_count=56644`. The event-aggregation
    query passed without traceback.
  - Phase 8.5 export: generated successfully; export files are zip
    archives.
  - Demon-coin discovery sanity: `EDENUSDT` appeared in the radar
    top-symbols list AND in the top event-volume aggregation, which
    is the qualitative evidence that the WS-first all-market radar
    is functioning end-to-end.

### Safety boundary held throughout the Phase 11C.1B acceptance run

```
trading_mode                    = paper
live_trading_enabled            = False
right_tail_enabled              = False
llm_enabled                     = False
exchange_live_order_enabled     = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
real Binance API key            = not loaded
real Binance API secret         = not loaded
real signed endpoint call       = none
real private WebSocket          = none (`/private` refused at allowlist)
real listenKey / user data WS   = none
real DeepSeek trade decision    = none
real Telegram outbound          = none
Phase 12                        = FORBIDDEN (gate unchanged)
```

## Phase 11C.1B — what it ships (closeout reference)

PR-B adds three new modules + extends two existing ones:

  - `app/exchanges/binance_public_ws.py` -
    `BinancePublicWSClient` + `WSConfig` + `WSMessage` +
    `WSMessagePump` + `InProcessWSPump` + `_RefusalTransport`
    (default; refuses any real-network call) +
    **`StdlibPublicWSTransport`** (real-network RFC 6455 client
    built on the Python standard library only, route-aware) +
    **`MultiTransportPublicWSManager`** (owns one routed
    `StdlibPublicWSTransport` per route - PUBLIC + MARKET - and
    merges their messages behind a single `WSMessagePump`
    interface) + `create_real_public_ws_transport` factory +
    `classify_stream_route` + `split_streams_by_route` +
    `assert_public_ws_stream_allowed` +
    `assert_public_ws_url_allowed` +
    `assert_public_ws_path_allowed`. Stream allowlist:
    `!ticker@arr`, `!miniTicker@arr`, `!bookTicker`,
    `!markPrice@arr`, `!forceOrder@arr`. Stream-route
    classification: `!bookTicker` is the PUBLIC route;
    `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` /
    `!forceOrder@arr` are the MARKET route. Path-root
    acceptance allowlist: `/public/ws`, `/public/stream`,
    `/market/ws`, `/market/stream` (legacy unrouted `/ws` /
    `/stream` are kept as back-compat for the in-process pump
    fixtures only). Forbidden path roots: `/private`, `/ws-api`,
    `/ws-fapi`, `/ws-papi`, `/trading-api`, `/userDataStream`.
    Host allowlist: `fstream.binance.com`,
    `fstream.binancefuture.com`. The transport refuses every
    credential-shaped kwarg (`api_key` / `api_secret` /
    `listen_key` / `token` / `signature` / `passphrase`) and
    never reads `BINANCE_API_KEY` / `BINANCE_API_SECRET`.
  - `app/market_data_public/radar.py` -
    `AllMarketRadarSnapshot` (frozen pydantic model) +
    `AllMarketRadarBuffer` (per-symbol rolling state) +
    `pre_anomaly_score_light` (pure additive scoring with
    deterministic reason tags).
  - `app/market_data_public/candidate_pool.py` - `CandidatePool`
    with default `candidate_pool_size=20`, `active_detail_limit=3`,
    `candidate_ttl_seconds=900`. Each candidate carries a
    Phase 8.5 `OpportunityIdentity` with
    `source_phase="phase_11c_1b_ws_first_radar"`.
  - `app/market_data_public/ws_radar_chain.py` -
    `WSRadarChainDriver` emits PRE_ANOMALY_DETECTED ->
    ANOMALY_DETECTED -> STATE_TRANSITION (+ Phase 8.5
    LearningReadyContext on each, + RISK_REJECTED via the live
    RiskEngine) per ACTIVE candidate.
  - `app/core/events.py` - three new EventType entries:
    `PUBLIC_WS_CONNECTED`, `PUBLIC_WS_DISCONNECTED`,
    `PUBLIC_WS_STALE`.
  - `app/paper_run/daily_report.py` - `DailyReportSnapshot` +
    `DailyReportBuilder` extended with WS + radar metrics; new
    `Phase 11C.1B WebSocket all-market radar` Markdown section.
  - `scripts/run_public_market_paper.py` - new CLI flags
    `--ws-first` (default ON) / `--ws-disabled` (mutex),
    `--candidate-pool-size`, `--active-detail-limit`,
    `--ws-staleness-threshold-ms`, `--candidate-ttl-seconds`. The
    runner pumps WS -> ingest into radar -> score every snapshot
    -> offer to pool -> expire stale candidates -> drive
    WSRadarChainDriver on the active head (skipped while
    `ws_client.is_stale=True`, the data-degraded gate); the
    active head also receives REST detail through the existing
    PR-A governor.

### Real routed public WS adapter

PR #32 ships the real-network public WebSocket adapter inline.
**`StdlibPublicWSTransport`** is a single-class, stdlib-only RFC
6455 client; **`MultiTransportPublicWSManager`** owns one of those
adapters per route (PUBLIC + MARKET) and presents them behind a
single `WSMessagePump` interface. The pair targets the documented
Binance USDⓈ-M Futures routed endpoints
(`wss://fstream.binance.com/public/stream` and
`wss://fstream.binance.com/market/stream`). The unrouted
`wss://fstream.binance.com/stream?streams=...` path silently
drops market-class streams (per the Binance public-WS reference)
and is therefore NOT the acceptance path; the routed-private
endpoint `wss://fstream.binance.com/private` is forbidden at the
path-root allowlist (`FORBIDDEN_WS_PATH_ROOTS`). The adapter
performs the HTTP/1.1 Upgrade handshake (`GET <route>/stream` with
`Sec-WebSocket-Key` / `Sec-WebSocket-Version: 13`), validates the
server's `Sec-WebSocket-Accept`, parses RFC 6455 text frames, and
surfaces decoded `WSMessage` envelopes. The third-party WebSocket
package deny-list (`websockets` / `websocket-client` / `aiohttp` /
`requests` / `httpx` / `urllib3`) in
`tests/unit/test_phase11c_no_network.py` continues to hold.

The runner refuses to silently fall back to the PR-A
bootstrap-only REST path: `--ws-first` without `--dry-run`
**requires** a real public WS pump. If the factory returns
`None` or raises, the runner exits with `rc=2` and the message
`real public WebSocket transport is required for --ws-first
without --dry-run`. The only path to REST-only operation is the
explicit `--ws-disabled` flag, documented as NOT the Phase 11C.1B
acceptance path.

## Phase 11C.1B execution modes

| CLI                                       | Behaviour                                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `--ws-first --dry-run` (default)          | In-process pump, deterministic synthetic messages, no socket, full event chain.                                        |
| `--ws-first` (no `--dry-run`)             | Real `MultiTransportPublicWSManager` opening routed PUBLIC (`/public/stream`) + MARKET (`/market/stream`) endpoints. RC=2 if the factory cannot produce one - never silently falls back to REST. |
| `--ws-disabled`                           | PR-A bootstrap-only REST path. Documented as **not** the Phase 11C.1B all-market demon-radar acceptance path.          |
