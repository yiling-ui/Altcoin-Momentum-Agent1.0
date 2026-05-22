# AMA-RT Phase 11C - Real Binance Public Market Data Read-Only Paper

**Status:** in development - the original Phase 11C real-data
acceptance is paused; **Phase 11C.1A** (PR-A, merged) capped the
public REST gateway with a sliding-window rate-limit governor;
**Phase 11C.1B** (PR-B, this branch) adds the WebSocket-first
all-market radar so the runner can discover demon coins (妖币)
without per-symbol REST detail polling.
**Phase tag (PR-B):** `phase_11c_1b_ws_first_radar`
**Branch (PR-B):** `feature/phase-11c1-ws-first-all-market-radar`
**Version (PR-B):** `1.4.0a11c.1b`
**Predecessor:** Phase 11C.1A - Binance Public REST Rate Limit Governor & 418 Protection (PR-A, merged)
**Dry-run evidence:** see [`docs/PHASE_11C_1B_DRY_RUN_EVIDENCE.md`](./PHASE_11C_1B_DRY_RUN_EVIDENCE.md) for the actual `--dry-run` boot banner, exit banner, events.db audit, per-iteration tracking record, discovered demon-coin list, daily-report excerpt, and rate-limit governor evidence captured on this branch.

---

## §11C.1B - WebSocket-First All-Market Demon Coin Radar (PR-B)

### Why this PR exists

Phase 11C.1A (PR-A) capped the public REST gateway with a
sliding-window rate-limit governor and shut every per-loop detail
REST surface so the bootstrap path could not trigger HTTP 429 / 418
again. The PR-A trade-off was that the runner could see *only* the
symbols the bootstrap already knew about; it could not detect a
brand-new "demon coin" that suddenly woke up between two bootstrap
cadences.

Phase 11C.1B (PR-B) restores the discovery surface by driving an
**all-market radar** off Binance's public WebSocket streams. The
goal is **NOT** to lower discovery capability - it is to *raise*
discovery throughput while keeping REST pressure near zero.

The five public streams below are the only network surfaces this
PR is allowed to subscribe to:

  - `!ticker@arr`        - 24h rolling stats per symbol
  - `!miniTicker@arr`    - light-weight last/volume push
  - `!bookTicker`        - per-symbol best bid/ask updates
  - `!markPrice@arr`     - mark price + funding rate per symbol
  - `!forceOrder@arr`    - liquidation events

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
| Routed-private endpoint (`/private`)        | refused at path-root allowlist (`FORBIDDEN_WS_PATH_ROOTS`) |
| Routed acceptance path                      | `/public/{ws,stream}` + `/market/{ws,stream}` (`ALLOWED_PUBLIC_WS_PATH_ROOTS`) |
| Stream route classification                 | `!bookTicker` -> PUBLIC; `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` / `!forceOrder@arr` -> MARKET |
| DeepSeek / Square / real Telegram outbound  | not connected                |
| Phase 12                                    | NOT entered                  |

### What PR-B ships

| Surface                                              | Behaviour                                                                          |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `app/exchanges/binance_public_ws.py`                 | New module: `BinancePublicWSClient`, `WSConfig`, `WSMessage`, `WSMessagePump`, `InProcessWSPump`, `_RefusalTransport`, **`StdlibPublicWSTransport`** (real-network RFC 6455 client, stdlib only, route-aware), **`MultiTransportPublicWSManager`** (owns one routed `StdlibPublicWSTransport` per route - PUBLIC + MARKET - and merges their messages behind a single `WSMessagePump` interface), `create_real_public_ws_transport` (returns the manager), `classify_stream_route`, `split_streams_by_route`, `assert_public_ws_stream_allowed`, `assert_public_ws_url_allowed`, `assert_public_ws_path_allowed`, `PublicWSCredentialForbidden`, `PublicWSStreamForbidden`, `PublicWSTransportError`. Path-root allowlist (`ALLOWED_PUBLIC_WS_PATH_ROOTS`): `/public/ws`, `/public/stream`, `/market/ws`, `/market/stream`. Forbidden path roots (`FORBIDDEN_WS_PATH_ROOTS`): `private`, `ws-api`, `ws-fapi`, `ws-papi`, `trading-api`, `userDataStream`. Legacy unrouted `/ws` / `/stream` accepted for back-compat fixtures only (NOT the WS-first acceptance path). |
| `app/market_data_public/radar.py`                    | New module: `AllMarketRadarSnapshot` (frozen pydantic v2 model), `AllMarketRadarBuffer` (per-symbol rolling state for price / volume history + per-batch volume rank), `pre_anomaly_score_light` (pure additive scoring with deterministic reason tags). |
| `app/market_data_public/candidate_pool.py`           | New module: `CandidatePool`, `CandidatePoolConfig`, `Candidate`. Default `candidate_pool_size=20`, `active_detail_limit=3`, `candidate_ttl_seconds=900`, `radar_score_threshold=30.0`. Each candidate carries a Phase 8.5 `OpportunityIdentity` with `source_phase="phase_11c_1b_ws_first_radar"`. |
| `app/market_data_public/ws_radar_chain.py`           | New module: `WSRadarChainDriver` emits PRE_ANOMALY_DETECTED -> ANOMALY_DETECTED -> STATE_TRANSITION (+ Phase 8.5 LearningReadyContext on each, + RISK_REJECTED via the live RiskEngine) per ACTIVE candidate. |
| `app/core/events.py`                                 | Three new EventType entries: `PUBLIC_WS_CONNECTED`, `PUBLIC_WS_DISCONNECTED`, `PUBLIC_WS_STALE`. |
| `app/paper_run/daily_report.py`                      | `DailyReportSnapshot` + `DailyReportBuilder` extended with WS + radar metrics; new "Phase 11C.1B WebSocket all-market radar" Markdown section. |
| `scripts/run_public_market_paper.py`                 | New CLI flags `--ws-first` / `--ws-disabled` (mutex), `--candidate-pool-size`, `--active-detail-limit`, `--ws-staleness-threshold-ms`, `--candidate-ttl-seconds`. Default `ws_first=True`. Module-level `_build_real_public_ws_transport` + `_build_rest_transport` factories (testability hooks). Pre-flight refusal: `--ws-first` without `--dry-run` REQUIRES a real public WS transport - rc=2 if the factory returns `None` or raises. Per-loop body: pump WS messages -> radar.ingest_messages -> score every snapshot -> pool.offer -> pool.expire -> when `ws_client.is_stale` skip the active head (DATA_DEGRADED gate, no events on stale data) -> drive WSRadarChainDriver on the active head. The active head also receives REST detail through the existing PR-A governor. |
| `tests/unit/test_phase11c_1b_ws_radar.py`            | Scaffold + radar + pool + chain tests (28). |
| `tests/unit/test_phase11c_1b_real_ws_adapter.py`     | Real WS adapter + runner refusal + reconnect backoff + staleness + safety flags + RFC 6455 handshake/frame audit tests (19). |
| `tests/unit/test_phase11c_no_network.py`             | Source-tree audit extended: PHASE_11C_FILES grew the four new files; `test_no_private_websocket_artefacts` blocks listenKey / userDataStream / ws-api / trading-api / @accountUpdate / @orderTradeUpdate / @marginCall / @balanceUpdate / @positionUpdate as non-docstring string literals across the source set; the third-party HTTP / WebSocket package deny-list (`websockets` / `websocket-client` / `aiohttp` / `requests` / `httpx` / `urllib3`) continues to hold. |

### How the WS-first pipeline works

```
                                        Phase 8.5
                                   LearningReadyContext
                                            ^
                                            |
   Binance public WS  -->  BinancePublicWSClient
   (5 ALLOWLIST streams)         |
        |                        |
        v                        v
   AllMarketRadarBuffer  -->  RadarScoreResult  -->  CandidatePool
        |                        ^                       |
        |                        |                       v
        +-- per-symbol           |                  active head
            rolling state        |                  (default 3)
                                 |                       |
                            pre_anomaly_                  |
                            score_light                   |
                                                          v
                                                  WSRadarChainDriver
                                                          |
                                                          v
                                              PRE_ANOMALY_DETECTED
                                              ANOMALY_DETECTED
                                              STATE_TRANSITION
                                              + RiskEngine.evaluate
                                                (stop_unconfirmed=True)
                                              -> RISK_REJECTED
```

REST in PR-B is bootstrap-only (one `exchangeInfo` + one
`ticker/24hr` to resolve the symbol list) plus per-loop detail
calls **only for the candidate pool's active head** (default
3 symbols). The full per-symbol detail loop that triggered the
24h test's HTTP 418 is gone for good.

### Connection management

| Lifecycle event           | Behaviour                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| `connect`                 | Pump connects + emits `PUBLIC_WS_CONNECTED` + re-subscribes to the configured stream set.  |
| `disconnect`              | Pump disconnects + emits `PUBLIC_WS_DISCONNECTED`.                                         |
| `reconnect` (auto)        | Disconnect + sleep configured backoff (default 1 s, max 30 s) + reconnect; reconnect_count++. |
| `pump_messages` no data   | Updates the staleness detector; if the last-message gap >= `staleness_threshold_ms` (default 3000 ms) the manager emits `PUBLIC_WS_STALE` and flips `is_stale=True`. |
| Pump drops underneath     | Detected on the next `pump_messages` call; auto-disconnect + emit. |
| Default transport         | `_RefusalTransport` raises `NotImplementedError` on `connect`. The runner picks **`MultiTransportPublicWSManager`** (which owns two routed `StdlibPublicWSTransport` adapters - one PUBLIC at `/public/stream`, one MARKET at `/market/stream`) instead whenever `--ws-first` is set without `--dry-run`. The runner refuses to start (rc=2) if the real transport factory returns `None` or raises - it does NOT silently fall back to REST. The in-process pump is wired under `--dry-run`. |
| Routed real-network adapter | `StdlibPublicWSTransport(route="public" \| "market")` connects to `wss://fstream.binance.com/<route>/stream?streams=...` only, sends a stdlib-only RFC 6455 client handshake (`Sec-WebSocket-Key`, `Sec-WebSocket-Version: 13`), validates `Sec-WebSocket-Accept`, parses RFC 6455 text frames, answers pings inline, and surfaces decoded `WSMessage` envelopes. Refuses every credential-shaped kwarg; never reads `BINANCE_API_KEY` / `BINANCE_API_SECRET`; refuses any non-routed (and non-legacy-fixture) path; refuses any URL embedding `listenKey` / `userdata` / `ws-api` / `ws-fapi` / `ws-papi` / `trading-api` / `signature` / `apiKey`; refuses the `/private` routed endpoint at the path-root allowlist. The `MultiTransportPublicWSManager` runs one routed transport per route, splits streams via `classify_stream_route` (`!bookTicker` -> PUBLIC; `!ticker@arr` / `!miniTicker@arr` / `!markPrice@arr` / `!forceOrder@arr` -> MARKET), and drains both transports on `poll()`. |
| Data-degraded gate        | When `ws_client.is_stale=True` the runner SKIPS the candidate-pool active-head iteration: no PRE_ANOMALY_DETECTED / ANOMALY_DETECTED / STATE_TRANSITION events fire on stale data. The PUBLIC_WS_STALE event is still emitted. The Phase 1 / Phase 11C safety flags are unchanged - this is a pure read-only quality downgrade. The runner counts `ws_data_degraded_ticks` for the daily report. |

### Candidate pool behaviour

The pool admits a symbol when at least one of:

  - `radar_score >= radar_score_threshold` (default 30.0)
  - `volume_rank_jump >= volume_rank_jump_threshold` (default 3)
  - `|price_acceleration_60s| >= price_acceleration_threshold` (default 0.005)
  - `liquidation_event=True` (when `liquidation_promotes=True`)

State transitions:

  - `WATCHING` -> `ACTIVE`: radar_score crosses the threshold on a
    later offer (upgrade_count++).
  - `ACTIVE` -> `WATCHING`: radar_score falls below the threshold
    (downgrade_count++).
  - any state -> evicted: pool is over capacity; lowest-score (and
    oldest) candidate is dropped.
  - any state -> `EXPIRED`: pool.expire() runs and the candidate's
    last_seen_ms is older than `candidate_ttl_seconds`.

Every candidate carries a Phase 8.5 `OpportunityIdentity` with
`source_phase="phase_11c_1b_ws_first_radar"`, so Reflection / Replay
can split WS-radar candidates from REST-bootstrap candidates.

### Daily report - new section

The Phase 11B daily report grew a `## Phase 11C.1B WebSocket
all-market radar` section with every brief-mandated metric:

  - `ws_messages_received`
  - `ws_reconnect_count`
  - `ws_staleness_ms_max`
  - `ws_stale_count`
  - `ws_connect_count` / `ws_disconnect_count`
  - `radar_candidates_seen`
  - `candidate_pool_size_max`
  - `pre_anomaly_candidates`
  - `liquidation_events_seen`
  - per-stream WS message counts
  - top-N candidate symbols + radar scores

The aggregator cross-checks the event-log counts of
`PUBLIC_WS_CONNECTED` / `PUBLIC_WS_DISCONNECTED` / `PUBLIC_WS_STALE`
against the WS client's `metrics_payload` so a stale governor
counter cannot hide a real connection event.

### Phase 11C.1B acceptance criteria

1. `pytest` 全部通过 (currently `2177 passed`).
2. The new test files
   `tests/unit/test_phase11c_1b_ws_radar.py` (scaffold + radar +
   pool + chain),
   `tests/unit/test_phase11c_1b_real_ws_adapter.py` (real public
   WS adapter + runner refusal + reconnect backoff + staleness
   gate + safety flags), and
   `tests/unit/test_phase11c_1b_routed_public_market_ws.py`
   (routed `/public/{ws,stream}` + `/market/{ws,stream}`
   acceptance, `/private` refusal, stream-route classification,
   `MultiTransportPublicWSManager` merge, runner uses both
   routed transports, no follow-up wording in source / docs)
   pin every behaviour the brief calls out:
   - **Scaffold + radar + pool + chain**:
     - `test_public_ws_stream_allowlist`
     - `test_private_ws_forbidden`
     - `test_listen_key_forbidden`
     - `test_user_data_stream_forbidden`
     - `test_all_market_ticker_updates_radar_snapshot`
     - `test_book_ticker_updates_spread`
     - `test_mark_price_updates_funding`
     - `test_force_order_sets_liquidation_event`
     - `test_radar_score_detects_price_volume_acceleration`
     - `test_candidate_pool_adds_top_radar_symbols`
     - `test_candidate_pool_expires_old_candidates`
     - `test_ws_stale_enters_data_degraded`
     - `test_ws_first_runner_does_not_call_rest_detail_for_all_symbols`
     - `test_learning_ready_payload_from_ws_candidate`
     - `test_safety_flags_unchanged_with_ws_enabled`
   - **Real public WS adapter + runner refusal**:
     - `test_real_public_ws_adapter_allows_only_public_hosts`
     - `test_real_public_ws_adapter_rejects_private_hosts`
     - `test_real_public_ws_adapter_rejects_listen_key`
     - `test_real_public_ws_adapter_rejects_user_data_stream`
     - `test_real_public_ws_adapter_rejects_trading_ws_api`
     - `test_real_public_ws_adapter_rejects_credentials`
     - `test_runner_real_ws_first_refuses_if_transport_missing`
     - `test_runner_real_ws_first_uses_ws_adapter`
     - `test_runner_real_ws_first_does_not_silent_fallback_to_rest`
     - `test_ws_reconnect_backoff`
     - `test_ws_staleness_enters_data_degraded`
     - `test_public_ws_connected_event_written`
     - `test_public_ws_stale_event_written`
     - `test_safety_flags_unchanged_with_real_ws_enabled`
     - `test_no_private_ws_or_listen_key_in_phase11c1b`
   - **Routed public/market WebSocket endpoints**:
     - `test_routed_public_ws_path_allowed`
     - `test_routed_market_ws_path_allowed`
     - `test_private_routed_ws_forbidden`
     - `test_unrouted_market_stream_rejected_or_not_used`
     - `test_mark_price_stream_uses_market_route`
     - `test_book_ticker_stream_uses_public_route`
     - `test_multi_transport_ws_manager_merges_public_and_market_messages`
     - `test_multi_transport_ws_manager_subscribe_routes_to_correct_transport`
     - `test_multi_transport_ws_manager_refuses_credentials`
     - `test_multi_transport_ws_manager_refuses_private_streams_at_construction`
     - `test_runner_real_ws_first_uses_routed_public_and_market_transports`
     - `test_no_followup_adapter_stale_text_in_docs_or_help`
     - `test_safety_flags_unchanged_with_routed_ws`
     - `test_no_private_ws_listen_key_or_user_data_stream`
   plus supporting tests (RFC 6455 handshake validation, frame
   parsing, private-shaped message drop).
3. The four `ExchangeClientBase` write surfaces still raise
   `SafeModeViolation` when invoked on the public REST client.
4. The Phase 8.5 export pipeline accepts the three new
   `PUBLIC_WS_*` event types (no schema change required - the
   export layer streams every EventType through unchanged).
5. The Phase 10A replay engine and Phase 10B reflection engine
   accept the new event types (asserted by the existing
   `test_phase11c_export_and_replay.py` continuing to pass).
6. The daily Markdown report contains the new "Phase 11C.1B
   WebSocket all-market radar" section with every required field,
   including the new `ws_real_transport` and
   `ws_data_degraded_ticks` fields.
7. No file in the Phase 11C source set imports a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package; only stdlib +
   loguru + pydantic + the existing `app.*` modules. The
   `StdlibPublicWSTransport` is implemented entirely on top of
   `socket` + `ssl` + `select` + `struct` + `base64` + `hashlib`
   + `json` + `os.urandom` (RFC 6455 client).
8. Under `--ws-first` without `--dry-run`, the runner uses the
   real `StdlibPublicWSTransport` and does NOT silently fall back
   to REST bootstrap. If the transport factory returns `None` or
   raises, the runner exits with `rc=2` and the message
   `real public WebSocket transport is required for --ws-first
   without --dry-run`.

### Phase 11C.1B explicitly does NOT

- accept any Binance API key / API secret.
- accept any `listenKey`.
- subscribe to any user data stream.
- subscribe to the trading WebSocket API.
- subscribe to any account / margin / position / leverage / balance
  / order private WebSocket variant.
- open the routed-private endpoint
  `wss://fstream.binance.com/private` (or any
  `/ws-api` / `/ws-fapi` / `/ws-papi` / `/trading-api` /
  `/userDataStream` path-root variant). The `/private` root is on
  `FORBIDDEN_WS_PATH_ROOTS` and the path-root allowlist refuses
  it before connect runs.
- treat the unrouted `wss://fstream.binance.com/stream` URL as the
  WS-first acceptance path. Binance silently drops market-class
  streams over an unrouted connection (per the public-WS
  reference); the runner therefore opens routed PUBLIC + MARKET
  transports through `MultiTransportPublicWSManager` and only
  accepts the unrouted path on the in-process pump fixtures.
- call any signed REST endpoint.
- import any third-party HTTP / WebSocket / SDK package. The
  real-network `StdlibPublicWSTransport` and the routed
  `MultiTransportPublicWSManager` are stdlib-only.
- silently fall back to REST under `--ws-first` without
  `--dry-run`. The runner refuses with rc=2 if the real public
  WS pump cannot be constructed; only `--ws-disabled` switches
  to the REST-only path (which is **not** the Phase 11C.1B
  acceptance path).
- connect to DeepSeek.
- connect to a real Telegram bot.
- connect to Binance Square.
- enter Phase 12.

### Resuming the Phase 11C real-data 24h acceptance run

After PR #32 merges (which ships the routed real-network
`MultiTransportPublicWSManager` inline), the Phase 11C real-data
24h acceptance run resumes with:

  - bootstrap REST: one `exchangeInfo` + one `ticker/24hr`.
  - public routed WS:
    `wss://fstream.binance.com/public/stream?streams=!bookTicker`.
  - market routed WS:
    `wss://fstream.binance.com/market/stream?streams=!ticker@arr/!miniTicker@arr/!markPrice@arr/!forceOrder@arr`.
  - candidate pool: top N (default 20) demon coins, active head 3.
  - per-loop REST detail: ONLY for the active head, gated on the
    PR-A rate-limit governor.
  - daily report: WS lifecycle + radar candidates + rate-limit
    governor metrics + per-route message counts in one Markdown
    body.

PR-B is responsible for the WS radar + `CandidatePool`
foundational candidate set + the learning-ready event chain.
PR-C is responsible for `priority_score` / cluster classifier /
same-cluster leader / multi-candidate arbitration; it remains a
separate branch.

### Phase 11C.1B cloud smoke acceptance ladder

The legacy command:

```
python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20 --poll-interval-seconds 5
```

is **deprecated**. It exercises the pre-PR-A "fetch every detail
endpoint for every symbol every loop" pattern that triggered HTTP
418, and it predates the routed public+market WebSocket
endpoints. The current acceptance ladder is:

| Stage              | Command                                                                                                                              | Status (UTC)              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------- |
| 30 s dry-run       | `python -m scripts.run_public_market_paper --duration 30s --symbol-limit 5 --dry-run`                                                | PASS                      |
| 5 min real WS      | `python -m scripts.run_public_market_paper --duration 5min --symbol-limit 5 --ws-first`                                              | **PASS (2026-05-22)**     |
| 10 min real WS     | `python -m scripts.run_public_market_paper --duration 10min --symbol-limit 5 --ws-first`                                             | pending                   |
| 1 h WS-first + REST | `python -m scripts.run_public_market_paper --duration 1h --symbol-limit 5 --ws-first`                                               | pending                   |
| 6 h WS-first       | `python -m scripts.run_public_market_paper --duration 6h --symbol-limit 5 --ws-first`                                                | pending                   |
| 24 h WS-first      | `python -m scripts.run_public_market_paper --duration 24h --symbol-limit 5 --ws-first`                                               | pending (Phase 11C close) |

The 5-min PASS rung records: ``ws_messages_received > 0``,
``ws_chains_emitted > 0``, ``radar_candidates_seen >= 0`` (no
longer stuck at 0 due to no messages), ``PUBLIC_WS_CONNECTED``
written to ``events.db``, ``rate_limit_429_count = 0``,
``rate_limit_418_count = 0``, ``rate_limit_ban = False``, every
safety flag unchanged. The earlier failure mode
(``ws_messages_received = 0`` for the full 300s window) was a
zero-timeout ``recv`` short-circuit in the stdlib WS transport;
fixed by always draining the recv buffer non-blockingly at the
top of every ``poll`` call (and by routing the runner's wait
window through the WS pump's blocking timeout instead of an
unrelated ``time.sleep``). Pinned by
``test_real_ws_transport_drains_buffered_bytes_with_zero_timeout``
+ ``test_real_ws_runner_loop_pattern_drains_messages_with_zero_timeout``.

PR-C (priority_score / cluster classifier / same-cluster leader /
multi-candidate arbitration) remains a separate branch.

### Phase 11C.1B follow-up: SymbolUniverse (exchangeInfo-as-truth)

Binance USDⓈ-M Futures lists non-ASCII contracts in production -
documented examples include ``我踏马来了USDT`` and ``币安人生USDT``.
Each is a real Binance contract with its own
``/fapi/v1/exchangeInfo`` entry, its own all-market WS push, and
its own REST detail endpoints. The Phase 11C.1B brief therefore
forbids any character-class regex
(``^[A-Z0-9_]{2,30}(USDT|USDC)$`` or any equivalent) on the
symbol-validation path; the only authoritative source is the
snapshot pulled from ``/fapi/v1/exchangeInfo`` at runner startup.

#### Implementation

  - ``app/market_data_public/symbol_universe.py`` -
    :class:`SymbolUniverse.from_exchange_info(symbols)` builds the
    bootstrapped set; :meth:`SymbolUniverse.empty()` is the
    back-compat "admit everything" fallback for dry-run / fixture
    tests.
  - :meth:`CandidatePool.offer` consults the universe; symbols
    missing from the bootstrapped set surface a typed
    ``WS_SYMBOL_REJECTED`` event (a new entry on
    :class:`EventType`) and the candidate is dropped before it
    enters the pool's accounting.
  - The runner
    (:func:`scripts.run_public_market_paper.main`) bootstraps the
    universe from :meth:`BinancePublicClient.get_symbols` before
    constructing the candidate pool. On bootstrap failure
    (rate-limit protection, network error, etc.) the runner falls
    back to the empty universe and logs the degraded note - safety
    flags stay unchanged and the pool admits everything to avoid
    blocking the smoke ladder on a transient REST fault.
  - Source-tree audit: the test
    ``tests/unit/test_phase11c_1b_symbol_universe.py
    ::test_symbol_validation_uses_exchange_info_not_ascii_regex``
    walks every WS-radar / symbol-validation file and refuses any
    ``re.compile|match|fullmatch|search`` whose pattern smells
    like an ASCII-only symbol regex. The next PR that
    re-introduces one fails this test.

#### Contract

The brief is explicit: **the rejection reason is "not in
exchangeInfo", NEVER "non-ASCII character class".** A pure-ASCII
symbol that is missing from the snapshot (e.g. a brand-new
listing that came online mid-run, or a delisting whose WS pushes
arrived between bootstrap and subscribe) is treated identically
to a Chinese symbol that is missing.

#### Daily-report fields added

  - ``candidate_pool_rejected_by_universe`` - count of WS-radar
    offers refused because the symbol was missing from the
    bootstrapped exchangeInfo set;
  - ``ws_symbol_universe_size`` - cardinality of the bootstrapped
    set;
  - ``ws_symbol_universe_source`` - either ``"exchange_info"``
    (bootstrapped) or ``"empty_admit_all"`` (back-compat
    fallback);
  - ``ws_symbol_universe_bootstrapped`` - boolean;
  - ``ws_symbol_universe_bootstrap_ts_ms`` - the timestamp of the
    bootstrap snapshot.

#### Pinned by

  - ``test_non_ascii_exchange_symbol_allowed_if_in_exchange_info``
  - ``test_non_ascii_ws_symbol_rejected_if_not_in_exchange_info``
  - ``test_symbol_validation_uses_exchange_info_not_ascii_regex``
  - ``test_empty_universe_is_admit_all_back_compat``

---

## §11C.1A - Binance Public REST Rate Limit Governor & 418 Protection (PR-A)

### Why this PR exists

The first 24h test of the Phase 11C runner against the real
Binance public REST endpoints (`fapi.binance.com`) returned:

  1. HTTP 429 (Too Many Requests). Binance returned this once the
     per-IP weight budget was exceeded.
  2. HTTP 418 (I'm a teapot). The runner kept polling and Binance
     escalated to a real IP-level ban.

Phase 11C's safety lock held throughout the failure (`mode=paper`,
`live_trading=False`, no API key, no signed endpoint, no real
order, no DeepSeek, no real Telegram outbound), but the gateway
was unusable for real-data acceptance until the rate-limit problem
was fixed.

The brief explicitly forbids fixing this by simply lowering
`symbol_limit` and lengthening `poll_interval_seconds`. The full
fix is the **WebSocket-first all-market radar**:

  - REST bootstrap only.
  - REST candidate enrichment only (gated on a multi-candidate
    priority ranking).
  - Global REST rate governor.
  - 429 backoff.
  - 418 shutdown.
  - Cluster exposure control.

That work is split into three PRs:

  - **PR-A** (this branch) - Rate-Limit Governor + 418 Protection
    + conservative defaults + layered REST runner.
  - **PR-B** - WebSocket-first all-market radar +
    multi-candidate priority ranking + per-loop candidate
    enrichment that consumes `candidate_detail_limit`.
  - **PR-C** - Cluster exposure control.

PR-A holds in isolation: the runner refuses to overwhelm Binance,
records every 429 / 418 with full audit context, latches a P1
incident on 418, and stops the runner with `rc=2` without
auto-retrying, switching endpoints, or rotating source IP.

### What PR-A ships

| Surface                                 | Behaviour                                                                                       |
| --------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `app/exchanges/binance_rate_limit.py`   | New module: `BinancePublicRestGovernor`, `RestGovernorConfig`, `PublicRestResponse`, `RateLimitProtectionError`, `RateLimitBackoffActive`, `RateLimitBudgetExceeded`. |
| `app/exchanges/binance_public.py`       | `BinancePublicClient` accepts an optional `governor=`; the `_default_transport` captures status + headers and returns `PublicRestResponse`; `_request` routes through the governor's `before_request` / `record_response`; HTTP 418 raises :class:`RateLimitProtectionError`. |
| `app/config/schema.py`                  | New `RestGovernorSection` (validators on every knob); `MarketDataConfig.symbol_limit` lowered to 5; `MarketDataConfig.rest_poll_interval_seconds` lowered to 60.0. |
| `app/config/defaults.yaml`              | New `market_data.rest_governor` block; lowered defaults.                                        |
| `app/core/events.py`                    | Five new EventType entries: `RATE_LIMIT_429`, `RATE_LIMIT_BACKOFF_STARTED`, `RATE_LIMIT_BACKOFF_ENDED`, `RATE_LIMIT_418`, `RATE_LIMIT_PROTECTION_ENTERED`. |
| `app/paper_run/daily_report.py`         | `DailyReportSnapshot` + `DailyReportBuilder` extended with rate-limit metrics. |
| `scripts/run_public_market_paper.py`    | Layered REST runner: bootstrap-only REST in steady state; per-loop detail REST gated on a candidate ranking (empty in PR-A); new `--candidate-detail-limit` and `--legacy-detail-per-loop` CLI flags; default `--symbol-limit` lowered to 5; rc=2 on rate-limit protection. |
| `tests/unit/test_phase11c1a_rate_limit_governor.py` | 16 new tests pinning every behaviour the brief calls out. |

### Conservative new defaults

```yaml
market_data:
  symbol_limit: 5                          # was 20
  rest_poll_interval_seconds: 60.0         # was 5.0
  rest_governor:
    enabled: true
    weight_budget_per_minute: 300          # half of Binance's 1200/min
    soft_weight_ratio: 0.50                # warn at >=150 weight
    hard_weight_ratio: 0.75                # refuse at >=225 weight
    retry_after_default_seconds: 300       # used when Retry-After missing
    on_429: backoff                        # PR-A: only supported value
    on_418: shutdown                       # PR-A: only supported value
    candidate_detail_limit: 3              # max per-loop candidates
    rest_layering_enabled: true            # bootstrap-only REST
```

Each value is enforced by a Pydantic field validator on
`RestGovernorSection` so a misconfigured operator sees the failure
at boot, not at the first 429.

### How the governor works

```
  caller          governor                  transport
   |                  |                          |
   |---before_request----------->|              |
   |   (refuse if protection latched / backoff   |
   |    active / hard budget exhausted)          |
   |   reserves weight                           |
   |                  |                          |
   |---transport-call------------------------>   |
   |                                             |--- HTTP request --->
   |<------ PublicRestResponse(status, headers, body)
   |                  |                          |
   |---record_response---------->|               |
   |   reads X-MBX-USED-WEIGHT-1M / Retry-After  |
   |   on 429: emit RATE_LIMIT_429 +             |
   |           RATE_LIMIT_BACKOFF_STARTED,       |
   |           sleep retry_after,                |
   |           emit RATE_LIMIT_BACKOFF_ENDED     |
   |   on 418: emit RATE_LIMIT_418 +             |
   |           RATE_LIMIT_PROTECTION_ENTERED,    |
   |           open P1 incident,                 |
   |           raise RateLimitProtectionError    |
   |   commits reserved weight to rolling window |
```

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
| `market_data.symbol_limit`                  | `5` default                  |
| `market_data.rest_poll_interval_seconds`    | `60.0` default               |
| `rest_governor.weight_budget_per_minute`    | `300` default                |
| `rest_governor.on_429`                      | `"backoff"` (only allowed)   |
| `rest_governor.on_418`                      | `"shutdown"` (only allowed)  |
| Four ExchangeClientBase write surfaces      | refuse with SafeModeViolation, including AFTER 418 latch |

### Phase 11C.1A acceptance criteria

1. `pytest` 全部通过. Currently `2089 passed in 7.17s`.
2. The new test file
   `tests/unit/test_phase11c1a_rate_limit_governor.py` pins every
   behaviour the brief calls out. The full list:
   - `test_default_phase11c_polling_is_conservative`
   - `test_rest_governor_config_refuses_pathological_values`
   - `test_429_triggers_backoff_and_stops_batch`
   - `test_retry_after_header_is_respected`
   - `test_used_weight_header_is_recorded`
   - `test_418_triggers_shutdown_without_retry`
   - `test_rest_governor_blocks_when_budget_exceeded`
   - `test_governor_refuses_during_active_backoff`
   - `test_rest_not_called_for_all_symbols_every_loop`
   - `test_legacy_detail_per_loop_flag_re_enables_old_behaviour`
   - `test_no_live_trading_flags_after_429`
   - `test_no_live_trading_flags_after_418`
   - `test_phase_11c_write_surfaces_still_refuse_after_418`
   - `test_daily_report_contains_rate_limit_metrics`
   - `test_daily_report_after_418_marks_rate_limit_ban`
   - `test_export_service_handles_rate_limit_events`
3. The four ExchangeClientBase write surfaces still raise
   :class:`SafeModeViolation` after the governor latches into
   protection mode.
4. The Phase 8.5 export pipeline accepts the new RATE_LIMIT_*
   event types.
5. The Phase 10A replay engine and Phase 10B reflection engine
   accept the new event types (no schema regression - asserted by
   the existing replay / reflection test surface).
6. The daily Markdown report contains a new "Phase 11C.1A
   rate-limit governor" section with every required field
   (rate_limit_429_count, rate_limit_418_count,
   retry_after_seconds_last/total, used_weight_1m_last/max,
   rest_requests_total, rest_requests_skipped_by_budget,
   rate_limit_protection_triggered, rate_limit_ban,
   ingestion_errors).
7. No `binance_rate_limit.py` import touches a third-party HTTP /
   WebSocket / SDK / LLM / Telegram bot package; only stdlib +
   loguru + the existing `app.*` modules.

### Phase 11C.1A explicitly does NOT

- ship the WebSocket-first all-market radar (PR-B).
- ship multi-candidate priority ranking (PR-B).
- ship cluster exposure control (PR-C).
- accept any Binance API key / API secret.
- call any signed endpoint.
- call any /order, /account, /position, /leverage, /margin endpoint.
- connect to DeepSeek.
- connect to a real Telegram bot.
- auto-retry after a 418.
- switch endpoints to evade a 418.
- rotate source IP to evade a 418.
- enter Phase 12.

### Pause on the Phase 11C real-data 24h acceptance

The Phase 11C real-data 24h acceptance run defined in the parent
phase below is **paused** until PR-A merges. PR-A on its own does
NOT issue per-loop detail REST (the candidate ranking lands in
PR-B) so the parent acceptance run will only resume once PR-B has
also landed.

---


## 1. What Phase 11C is

Phase 11C is the FIRST phase in the project that talks to a real
exchange. It is **public-market read-only** ingestion of Binance USDT-M
perpetual futures data, driven through the existing Phase 1 - 10D
paper pipeline. Specifically:

- Connects to Binance public REST endpoints only.
- Pulls klines / aggTrades / depth / funding / open interest /
  mark price / book ticker / exchangeInfo / ticker24hr.
- Feeds the data into the existing :class:`MarketDataBuffer`
  (Phase 4), produces real :class:`MarketSnapshot` objects, and
  emits the full Phase 11C event chain (Phase 4 - 8.5 vocabulary).
- Persists the events into `events.db` so Replay (Phase 10A),
  Reflection (Phase 10B), Export (Phase 8.5), and the daily report
  builder (Phase 11B) all consume real-data event chains without
  any code change in those layers.

## 2. What Phase 11C is NOT

**Phase 11C is NOT live trading.** Phase 11C is NOT a real-money phase.

- Phase 11C is NOT 实盘 (live trading).
- Phase 11C is NOT connected to the Binance trading API.
- Phase 11C does NOT consume any Binance API key.
- Phase 11C does NOT consume any Binance API secret.
- Phase 11C does NOT call any signed endpoint.
- Phase 11C does NOT call any account / position / leverage / margin
  endpoint.
- Phase 11C is NOT connected to DeepSeek.
- Phase 11C is NOT connected to a real Telegram bot.
- Phase 11C is NOT connected to the 币安广场 (Binance Square) feed.
- Phase 11C does NOT execute any real order.
- Phase 11C does NOT implement Phase 12. Passing Phase 11C does NOT
  imply approval to start Phase 12.

The only network surface Phase 11C ever touches is the Binance public
market data REST API on `fapi.binance.com`. The four
:class:`ExchangeClientBase` write surfaces - `create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode` - continue to
raise :class:`SafeModeViolation` on every code path.

## 3. Phase 11C goal

Collect real-market event flow through the paper pipeline so that
later Phase 11D / Phase 12 / Phase 13 work has:

- a real Phase 8.5 learning-ready dataset (opportunity_id /
  scan_batch_id / SignalSnapshot / RiskRejectedLearningPayload /
  VirtualTradePlan / ConfigVersions / LearningReadyContext);
- a real MFE / MAE labelling baseline;
- a real MARKET_SNAPSHOT stream the Reflection engine can walk;
- evidence that the four write surfaces and the Phase 1 safety lock
  hold under real-data load.

Phase 11C does NOT produce a trading edge. Phase 11C produces
**dataset + invariant evidence**.

## 4. Phase 11C boundary (every clause enforced by tests)

| Invariant                                | How it is enforced                                                                  |
| ---------------------------------------- | ----------------------------------------------------------------------------------- |
| `mode=paper`                             | `app/config/settings._apply_phase1_safety_lock` + `assert_paper_cloud_safety`       |
| `live_trading = False`                   | Phase 1 safety lock + Phase 11B safety assertion                                    |
| `right_tail = False`                     | Phase 1 safety lock                                                                 |
| `llm = False`                            | Phase 1 safety lock                                                                 |
| `exchange_live_orders = False`           | Phase 1 safety lock                                                                 |
| `telegram_outbound_enabled = False`      | `TelegramConfig.outbound_enabled` schema validator refuses `True`; `Settings.telegram_outbound_enabled` reads that field, NOT `telegram.enabled`, so flipping the in-process command-bus on never enables real HTTP outbound. |
| `binance_private_api_enabled = False`    | `BinancePublicClient` rejects api_key / api_secret with `SafeModeViolation`         |
| No signed endpoint                       | `assert_public_endpoint_allowed` + `FORBIDDEN_PRIVATE_ENDPOINTS` + AST audit        |
| No order endpoint                        | `assert_public_endpoint_allowed`                                                    |
| No account / position / leverage / margin endpoint | `assert_public_endpoint_allowed`                                          |
| No third-party HTTP / WS / SDK           | `tests/unit/test_phase3_no_network.py` + `tests/unit/test_phase11c_no_network.py`   |
| Four write surfaces refuse               | `tests/unit/test_phase11c_safety_flags.py::test_no_live_trading_in_phase11c`        |
| Schema cannot loosen `safety.*`          | `SafetyConfig` field validators raise on any `False`                                |
| Schema cannot flip `market_data.read_only` | `MarketDataConfig` field validator raises on `read_only=False`                    |
| Provider cannot be anything other than `binance_public` | `MarketDataConfig` field validator                                  |

## 5. New code

### 5.1 `app/exchanges/binance_public.py`

`BinancePublicClient` is the public-only Binance USDT-M perpetual
gateway. Inherits :class:`ExchangeClientBase`, so the four write
surfaces remain refused. Constructor refuses `api_key` / `api_secret`
and any credential-shaped `**kwargs` with :class:`SafeModeViolation`.

Exposes:

- `get_symbols()` - filtered to USDT perpetual contracts
- `get_top_usdt_perpetual_symbols(limit=20)` - top USDT-perp by 24h vol
- `get_orderbook(symbol, depth=...)`
- `get_recent_trades(symbol, limit=...)` - aggTrades
- `get_book_ticker(symbol)` - fresh best bid / ask
- `get_funding_rate(symbol)` - falls back to `premiumIndex` on empty
- `get_open_interest(symbol)`
- `get_mark_price(symbol)` - mark + index + last funding + next funding
- `get_klines(symbol, interval='1m', limit=100)` - diagnostic only
- `get_account_snapshot()` - **explicitly raises** :class:`SafeModeViolation`

Endpoint allowlist is `PUBLIC_MARKET_ENDPOINT_ALLOWLIST`:

```
/fapi/v1/exchangeInfo
/fapi/v1/ticker/24hr
/fapi/v1/ticker/bookTicker
/fapi/v1/klines
/fapi/v1/aggTrades
/fapi/v1/trades
/fapi/v1/depth
/fapi/v1/fundingRate
/fapi/v1/openInterest
/fapi/v1/premiumIndex
```

Forbidden private endpoints (refused by name even when not in allowlist):

```
/fapi/v1/order, /fapi/v1/order/test, /fapi/v1/batchOrders,
/fapi/v1/allOrders, /fapi/v1/openOrders, /fapi/v1/openOrder,
/fapi/v1/userTrades, /fapi/v2/account, /fapi/v2/balance,
/fapi/v2/positionRisk, /fapi/v1/positionRisk,
/fapi/v1/positionSide/dual, /fapi/v1/leverage,
/fapi/v1/marginType, /fapi/v1/positionMargin,
/fapi/v1/income, /fapi/v1/leverageBracket,
/fapi/v1/multiAssetsMargin, /fapi/v1/listenKey
```

Forbidden query parameters (refused even on allowlisted paths):
`signature`, `timestamp`, `recvWindow`, `apiKey`.

Allowed hosts: `fapi.binance.com`, `fapi.binancefuture.com`. Only
`https://` URLs are accepted.

The default transport uses `urllib.request` from the Python standard
library. No third-party HTTP / WebSocket library is imported anywhere
in the Phase 11C source set. Tests inject a deterministic
`transport` callable so the test suite never opens a real socket.

### 5.2 `app/market_data_public/`

| Module                 | Role                                                                  |
| ---------------------- | --------------------------------------------------------------------- |
| `ingest.py`            | `PublicMarketIngestor` - REST polling -> `MarketDataBuffer` -> `MarketSnapshot` (with mark_price + fresh book ticker). Errors per surface are logged and counted; the loop never raises. |
| `event_chain.py`       | `PaperEventChainDriver` - emits the full Phase 11C event chain per `(symbol, snapshot)`, attaches Phase 8.5 `LearningReadyContext` to every `RISK_REJECTED` / `STATE_TRANSITION`. |
| `__init__.py`          | Public re-exports.                                                    |

The chain driver uses the live :class:`RiskEngine`:

```
RiskRequest(
    source_module="market_data_public.event_chain",
    action="paper_observe",
    symbol=...,
    live_trading_required=False,
    right_tail_amplify=False,
    stop_unconfirmed=True,            # locks every Phase 11C decision into REJECT
    is_new_open=True,
    opportunity=OpportunityIdentity(...),
    virtual_trade_plan=VirtualTradePlan(...),
    config_versions=ConfigVersions.defaults(),
    learning_context=LearningReadyContext(...),
)
```

`stop_unconfirmed=True` is the Phase 11C invariant: real market data
drives the *decision pipeline* but EVERY chain ends in
`RISK_REJECTED(reasons=['stop_unconfirmed'])`. No real order is ever
implied.

### 5.3 `scripts/run_public_market_paper.py`

The Phase 11C runner:

- argparse: `--duration`, `--symbol-limit`, `--symbols`,
  `--rest-base-url`, `--poll-interval-seconds`, `--dry-run`,
  `--no-banner`, `--no-daily-report`, `--paper-cloud-config`.
- Duration units: `ms`, `s`, `min`, `h`, `d`. Examples: `30s`,
  `2min`, `1h`, `6h`, `24h`.
- Uses `assert_paper_cloud_safety` (Phase 11B) + the Phase 11C
  `market_data` / `safety` checks before opening any database.
- Runs the Phase 11B `EnvGuard` against `BINANCE_API_KEY`,
  `BINANCE_API_SECRET`, `TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY`,
  ... (every entry from `DEFAULT_FORBIDDEN_CRED_ENV_VARS`). If any
  is set non-empty the runner raises :class:`SafetyViolation` and
  refuses to boot.
- Constructs `BinancePublicClient` (default real transport, or the
  in-process deterministic transport if `--dry-run` is set).
- Drives the loop at `poll_interval_seconds` cadence, emitting the
  full Phase 11C event chain per symbol per tick.
- Pins `client.assert_public_only()` on every loop tick.
- On graceful shutdown (SIGINT / SIGTERM / deadline) builds the
  daily Markdown report at `data/reports/phase11c/{date}-phase11c-public-market.md`.

Boot banner (single line, parseable):

```
[AMA-RT] Phase 11C - Real Binance Public Market Data Read-Only Paper v1.4.0a11c \
  mode=paper live_trading=False right_tail=False llm=False \
  exchange_live_orders=False telegram_outbound_enabled=False \
  binance_private_api_enabled=False \
  provider=binance_public rest_base_url=https://fapi.binance.com \
  symbols=20 duration_seconds=3600 poll_interval_seconds=5.0 \
  dry_run=False env_guard_passed=True
```

### 5.4 Configuration

`app/config/defaults.yaml` gains two top-level sections (the schema
in `app/config/schema.py` enforces every invariant):

```yaml
market_data:
  provider: binance_public           # only allowed value
  enabled: true
  read_only: true                    # MUST stay true
  symbol_limit: 20                   # 2C/4G VPS budget
  symbols_mode: top_usdt_perpetual
  rest_base_url: https://fapi.binance.com
  websocket_enabled: true            # accepted as a future-capability hook
  rest_enabled: true
  depth_enabled: true
  trades_enabled: true
  klines_enabled: true
  funding_enabled: true
  open_interest_enabled: true
  mark_price_enabled: true
  book_ticker_enabled: true
  max_ws_staleness_ms: 3000
  max_rest_latency_ms: 2000
  reconnect_backoff_seconds: 5
  rest_poll_interval_seconds: 5.0
  snapshot_interval_seconds: 5.0
  request_timeout_seconds: 5.0
  explicit_symbols: []

safety:
  forbid_private_credentials: true
  forbid_signed_endpoints: true
  forbid_trade_endpoints: true
  forbid_account_endpoints: true
  forbid_position_endpoints: true
  forbid_leverage_endpoints: true
  forbid_margin_endpoints: true
  forbid_live_trading: true
  forbid_right_tail: true
  forbid_llm_trade_decisions: true
  forbid_telegram_outbound: true
```

`MarketDataConfig` field validators refuse `read_only=False`,
non-`binance_public` provider, and `symbol_limit` outside `(0, 200]`.
`SafetyConfig` field validators refuse any `forbid_*: false`.

## 6. Event chain produced per symbol per tick

```
MARKET_SNAPSHOT
  └── payload includes: last_price, mark_price, bid, ask, spread_pct,
                        volume_1m, volume_5m, oi, funding_rate,
                        cvd_1m, cvd_5m, atr_1m, atr_5m,
                        orderbook_depth_usdt, degraded, degraded_reasons,
                        provider="binance_public", phase="11C"

PRE_ANOMALY_DETECTED
  └── opportunity_id, scan_batch_id, source_phase="phase_11c_public_market_paper",
      pre_anomaly_score, reason_tags, snapshot_summary

ANOMALY_DETECTED
  └── opportunity_id, scan_batch_id, anomaly_score, reason_tags

LIQUIDITY_CHECKED
  └── passed, spread_pct, orderbook_depth_usdt, volume_1m, volume_5m,
      reject_reasons

TRADE_CONFIRMED
  └── trade_confirmation_level (T0 by default in Phase 11C),
      reason_tags

MANIPULATION_DETECTED
  └── manipulation_level (M0 by default in Phase 11C), reason_tags

RISK_REJECTED   (Phase 7 surface; emitted by RiskEngine itself)
  └── reasons=["stop_unconfirmed"], plus
      learning_ready = {
        opportunity { opportunity_id, scan_batch_id, symbol, source_phase },
        signal_snapshot { ...11.2 fields... },
        virtual_trade_plan { ...11.3 fields... },
        config_versions { ...6 versions... },
        risk_decision { ...typed reject_reasons... },
        source_phase: "phase_11c_public_market_paper",
      }

STATE_TRANSITION
  └── from_state="no_trade", to_state="no_trade", trigger="downgrade",
      reject_reasons=["stop_unconfirmed"], phase="11C",
      learning_ready { ...same as above... }
```

The dedicated Phase 8.5 export streams (`opportunities.jsonl`,
`signal_snapshots.jsonl`, `virtual_trade_plans.jsonl`,
`risk_decisions.jsonl`, `state_transitions.jsonl`) all populate
correctly from real-data events.

## 7. Acceptance criteria (every item is testable)

| # | Criterion                                                                          | Test                                                       |
| - | ---------------------------------------------------------------------------------- | ---------------------------------------------------------- |
|  1 | pytest全部通过                                                                     | `pytest` (2071 tests pass)                                |
|  2 | runner启动无需API key                                                              | `test_public_market_runner_does_not_require_credentials`  |
|  3 | 1h public market read-only paper无异常                                             | `pytest tests/unit/test_phase11c_runner.py`               |
|  4 | 真实MARKET_SNAPSHOT写入EventRepository                                             | `test_public_market_event_repository_roundtrip`           |
|  5 | SignalSnapshot can be generated and written from real market data                  | `test_learning_ready_payload_from_real_market_snapshot`   |
|  6 | RISK_REJECTED carries opportunity_id + typed reject_reasons                        | `test_learning_ready_payload_from_real_market_snapshot`   |
|  7 | VirtualTradePlan saved + readable                                                  | `test_learning_ready_payload_from_real_market_snapshot`   |
|  8 | learning-ready payload exportable                                                  | `test_phase11c_events_round_trip_through_export`          |
|  9 | Export normal                                                                      | `test_phase11c_events_round_trip_through_export`          |
| 10 | Replay reads Phase 11C events                                                      | `test_phase11c_events_round_trip_through_replay`          |
| 11 | Reflection does not fail on real-market event shape                                | `test_phase11c_reflection_does_not_crash_on_real_market_event_chain` |
| 12 | Endpoint allowlist proves no trade endpoint is reachable                           | `test_public_endpoint_allowlist_rejects_order_endpoint`   |
| 13 | No API key                                                                         | `test_binance_public_client_rejects_private_credentials` + AST audit |
| 14 | No real trade                                                                      | `test_no_live_trading_in_phase11c`                        |
| 15 | live_trading = False                                                               | `test_phase11c_safety_flags_remain_false`                 |
| 16 | exchange_live_orders = False                                                       | `test_no_exchange_live_orders_in_phase11c`                |
| 17 | llm = False                                                                        | `test_no_llm_trade_decision_in_phase11c`                  |
| 18 | telegram_outbound_enabled = False                                                  | `test_phase11c_safety_flags_remain_false`                 |

## 8. Operating notes

- Default symbol set is the top 20 USDT-M perpetual symbols by 24h
  quote volume. The runner refuses `symbol_limit` outside `(0, 200]`.
  The default is conservative for a 2C/4G VPS; raise it gradually.
- Default REST cadence is 5s/symbol. With 20 symbols + 6 endpoints
  per tick (depth, aggTrades, fundingRate, openInterest, premiumIndex,
  bookTicker) that is 24 req/s sustained, which is well below the
  Binance public-data quota.
- The runner exits cleanly on SIGINT / SIGTERM. The current loop tick
  finishes, the daily report is built, and `events.db` / `incidents.db`
  / `capital.db` are flushed via `DatabaseSet.close()`.
- `--dry-run` swaps the default `urllib.request` transport for an
  in-process deterministic transport so CI / smoke tests never touch
  the network.

## 9. After Phase 11C

Phase 11C must run **at least one full 24h paper observation** with
real Binance public market data and pass every acceptance criterion
above before any of the following can be considered:

- Phase 11D: information-side / DeepSeek READ-ONLY narrative interpreter.
- An extended Phase 11C+ window (multi-day or multi-week) for
  longer-horizon dataset collection.

**Phase 11C does NOT lead directly into Phase 12.** The path forward
is explicitly Phase 11C -> Phase 11D (or Phase 11C+) -> review ->
Phase 12 only after the Spec §41 Go/No-Go checklist clears.
