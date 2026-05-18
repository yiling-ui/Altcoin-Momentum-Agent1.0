# Changelog

All notable changes to AMA-RT will be recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the project phase plan in `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` §43.

## [Unreleased]

### Phase 4 - Review fixes (PR #15 review feedback)

#### Added

- **`MarketDataBufferConfig.market_snapshot_event_emit_enabled`**
  (default `True`) - construct-time throttle for `MARKET_SNAPSHOT`
  events. Phase 4 keeps the existing per-call
  ``snapshot(symbol, emit_event=...)`` override; this config flag
  lets a Phase 5+ high-frequency consumer (anomaly scanner, regime
  engine) flip the default once instead of having to remember
  ``emit_event=False`` at every call site. The MarketSnapshot return
  value is unchanged - only the events.db append is suppressed -
  so downstream code stays event-shape-stable.
- **`MarketDataBuffer.market_snapshot_events_skipped`** property +
  **`BufferStats.market_snapshot_events_skipped`** field. Confirms
  that the throttle is actually doing what it claims to do.
- **`MarketDataBuffer.late_trades_dropped_total`** property +
  **`BufferStats.late_trades_dropped_total`** field. Aggregates
  `CandleBuilder.dropped_late_trades` across every tracked symbol
  so an out-of-order tape (mis-ordered REST replay, inverted aggTrade
  delivery, producer clock skew) is observable from a single counter.
  Issue #5 / #6 monitoring will alert on this.
- **`refresh_from_exchange` docstring rewritten** to declare the
  Phase 4 boundary verbatim: mock-only / fixture-driven by default,
  no auto-connect to a real public adapter, opt-in only with no API
  key and no write surface, tests must not depend on real network.
  The contract is pinned by
  `tests/unit/test_market_data_buffer_review_fixes.py
  ::test_refresh_from_exchange_docstring_declares_phase4_boundary`.
- **8 new unit tests**
  (`tests/unit/test_market_data_buffer_review_fixes.py`):
  - `test_default_emits_market_snapshot_event`
  - `test_explicit_emit_false_skips_event`
  - `test_config_flag_disables_emit_by_default`
  - `test_config_flag_off_but_explicit_true_still_emits`
  - `test_late_trades_dropped_counter_starts_at_zero`
  - `test_late_trades_dropped_counter_increments_on_out_of_order_tape`
  - `test_late_trades_dropped_counter_isolates_per_symbol_aggregate`
  - `test_refresh_from_exchange_docstring_declares_phase4_boundary`

#### Changed

- `MarketDataBuffer.snapshot()` parameter `emit_event` is now
  `bool | None` (default `None`); `None` resolves to the new config
  flag. `True` / `False` overrides remain available per call. This is
  source-compatible: every existing call site that passed
  `emit_event=True` / `emit_event=False` keeps its old behaviour
  exactly.

#### Tests

**+8 review-fix tests on top of 311 = 319 total. Full suite: 319
passed in 2.21s.**

#### Live trading risk

None. The review fixes only add observability counters, a
construct-time throttle for an existing event emission, and tighten
the docstring of an existing helper. No new mode flag, no loosened
safety lock, no new dependency, no new write surface, no new
network surface.

### Phase 4 - Market Data Buffer

#### Added
- **`app/market_data/` package** introducing the in-process Market
  Data Buffer that every later phase will read from. The package
  never imports an exchange SDK, never opens an outbound socket,
  never reads a credential, never adds a write surface. This is
  asserted by `tests/unit/test_phase4_no_network.py` (and by the
  pre-existing repo-wide `test_phase3_no_network.py`).

- **`app/market_data/models.py`** - frozen Pydantic v2 value objects:
  - `Bar`, `BarInterval` (`M1` / `M5`).
  - `LiquidationEvent`, `LiquidationSide` (data shape only - Phase 4
    does NOT subscribe to a real liquidation feed).
  - `MarketDataBufferConfig`, `MarketDataStalenessConfig` -
    rolling-window widths (1m / 5m / 15m), bar-history sizes, ATR
    windows, per-surface staleness thresholds.
  - `MarketDataDegradedReason` enum: `never_initialised`,
    `exchange_disconnected`, `exchange_degraded`, `trades_stale`,
    `orderbook_stale`, `oi_stale`, `funding_stale`,
    `rest_ws_conflict`, `explicit_mark`. Vocabulary locked by
    `tests/unit/test_market_data_models.py::test_degraded_reason_vocabulary`.
  - `BufferStats` - per-tick observability shape exposed by
    `MarketDataBuffer.stats()`.
  - The Spec §11.1 `MarketSnapshot` model lives in
    `app/core/models.py` (Phase 1) - this PR populates it, it does
    NOT redefine it.

- **`app/market_data/candles.py`** - streaming OHLCV builder with
  buy / sell taker volume split. Late trades (arrived after their
  bucket has already closed) are *dropped*, not back-filled (Spec
  §14.2: silent rewrites are forbidden); the
  `dropped_late_trades` counter exposes the count for monitoring.
  Multi-minute gaps between trades are filled with **flat synthetic
  bars** so ATR sees no missing slots.

- **`app/market_data/cvd.py`** - pure CVD calculator
  (`signed_volume`, `compute_cvd`). Honours Binance's
  `is_buyer_maker=True` convention as "the aggressor was a seller";
  falls back to `RecentTrade.side` when the flag is unset (mock
  fixtures).

- **`app/market_data/atr.py`** - SMA-of-True-Range over closed
  bars. Returns `None` for fewer than two closed bars. Wilder-style
  EMA smoothing is deliberately deferred to Issue #6 / #7 - SMA is
  enough for Phase 4's data-quality role and trivially deterministic
  under replay.

- **`app/market_data/oi.py`** + **`app/market_data/funding.py`** -
  `OpenInterestSnapshotState` and `FundingSnapshotState` keep the
  latest plus previous snapshot per symbol. Out-of-order updates are
  rejected. Cross-symbol updates raise `ValueError`. `delta()` and
  `percent_change()` handle the zero-baseline case explicitly.

- **`app/market_data/liquidation.py`** - bounded
  `LiquidationFeedState` deque per symbol; FIFO eviction with a
  configurable capacity. Phase 4 ships only the data structure and a
  `LiquidationEvent` shape - there is no `get_liquidations` method
  on the gateway, no real-time feed, no auto-subscribe.

- **`app/market_data/buffer.py` - `MarketDataBuffer`**:
  - Lazy per-symbol state via `track(symbol)` or auto-creation on
    first ingest.
  - Rolling trade windows for **1m / 5m / 15m**, anchored to the
    *latest observed timestamp across all surfaces* so the buffer
    is fully deterministic under replay (Spec §14, Issue #4
    "necessary support" list).
  - 1m and 5m candle builders fed by every ingested trade.
  - Latest order book per symbol with reliability tier carried.
  - Latest / previous funding rate and open interest.
  - Bounded liquidation history.
  - **`is_degraded(symbol)` and `degraded_reasons(symbol)`** for the
    future No-Trade Gate (Issue #7) and Reconciliation loop
    (Issue #9). Spec §14.2 + §31: untrustworthy data must NOT feed
    new openings.
  - **`snapshot(symbol)`** returns a Spec §11.1 `MarketSnapshot`
    populated with `last_price`, `bid`, `ask`, `spread_pct`,
    `volume_1m`, `volume_5m`, `cvd_1m`, `cvd_5m`, `atr_1m`,
    `atr_5m`, `oi`, `funding_rate`, `orderbook_depth_usdt`. Emits a
    `MARKET_SNAPSHOT` event when an `EventRepository` is wired in.
  - **`cvd_15m(symbol)`** for the 15-minute window required by
    Issue #4.
  - **REST vs WS conflict detection** (Spec §14.2): when an
    incoming order book has a different `DataReliability` tier than
    the existing one, the buffer emits a single
    `DATA_UNRELIABLE` event tagged
    `MarketDataDegradedReason.REST_WS_CONFLICT` with the previous
    and incoming tiers in the payload, AND keeps the strong-tier
    book on a tier downgrade. A tier upgrade (e.g. REST -> WS) is
    accepted but still counted; the audit trail captures both.
  - **`on_websocket_disconnect(reason=...)`** - marks every tracked
    symbol as `EXCHANGE_DISCONNECTED` and writes one batched
    `DATA_UNRELIABLE` event with `scope=all_symbols`,
    `trigger=websocket_disconnect`, and the full symbol list.
    Issue #4 acceptance criterion 4.
  - **`on_websocket_reconnect(reason=...)`** - clears the explicit
    disconnect / degraded reasons (stale-window reasons are
    recomputed and may legitimately stay set until fresh data
    arrives).
  - **Exchange-link health propagation**: when wired to an
    `ExchangeClientBase`, the gateway's
    `ExchangeConnectionState.{DISCONNECTED, DEGRADED, UNINITIALISED}`
    automatically maps to the corresponding degraded reason on every
    symbol view.
  - **`mark_degraded` / `clear_explicit_degraded`** for manual
    test-driven and Reconciliation-driven transitions.
  - **`refresh_from_exchange(symbol)`** - convenience helper that
    pulls trades, book, funding and OI from the attached client and
    feeds them through the ingest path. **Phase 4 only ever wires a
    `MockExchangeClient`** here; if a `BinanceClient` skeleton ever
    gets wired in, the call surfaces the underlying
    `NotImplementedError` instead of pretending it has data
    (asserted by
    `test_refresh_from_exchange_propagates_notimplementederror_from_binance`).
    The helper batches its emits so a fresh refresh produces at most
    one `DATA_UNRELIABLE` event per symbol regardless of how many
    surfaces it touched.

- **Boot path additions** in `python -m app.main`:
  - `_build_phase4_boot_seed()` constructs a deterministic
    in-process tape anchored at `now_ms()` so the buffer's
    staleness gate sees a fresh window. **No fixture file is read,
    no network call is made, no credential is consumed.**
  - `MarketDataBuffer` is instantiated, every symbol the mock
    exposes is `track`-ed, `refresh_from_exchange`-ed, and
    `snapshot`-ed.
  - One WS disconnect + reconnect probe is driven through the
    buffer so the audit trail at boot includes one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`
    and one recovery.
  - A `market_data_buffer` health probe is registered that goes
    `DEGRADED` if any symbol is degraded.
  - Banner extended with three Phase 4 fields:
    - `market_data=<tracked>/<degraded>`
    - `market_snapshots=<count>`
    - `data_unreliable=<count>`

  Sample boot output:

  ```
  [AMA-RT] Phase 4 - Market Data Buffer v1.4.0a4 mode=paper \
    live_trading=False right_tail=False llm=False exchange_live_orders=False \
    databases=5 events_count=9 capital_events=1 \
    exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
    market_data=3/0 market_snapshots=3 data_unreliable=1 \
    risk_decision=True/paper_only_skeleton_approval health=ok
  ```

- **76 new unit tests**:
  - `tests/unit/test_market_data_models.py` (8) - `Bar` /
    `LiquidationEvent` shape, `BarInterval` widths,
    `MarketDataBufferConfig` defaults, frozen-ness, degraded-reason
    vocabulary.
  - `tests/unit/test_market_data_candles.py` (12) - bucket
    alignment, first-trade live bar, in-place updates, bar
    closing, multi-minute gap filling with flat bars, late-trade
    drop, buy/sell volume split (both `is_buyer_maker` and `side`
    fallback), `force_close` padding, history bound, cross-symbol
    rejection.
  - `tests/unit/test_market_data_cvd.py` (7) - `signed_volume`
    sign, `compute_cvd` empty / pure-buy / pure-sell / mixed,
    Issue #4 acceptance criterion 1.
  - `tests/unit/test_market_data_atr.py` (8) - True Range with /
    without prev close, `compute_atr` `None` cases, simple-average
    correctness, prev-close from history when window is smaller
    than history, unclosed-bar exclusion, Issue #4 acceptance
    criterion 2.
  - `tests/unit/test_market_data_oi_funding_liquidation.py` (12) -
    initial state, advance-on-update, out-of-order rejection,
    cross-symbol rejection, zero-baseline percent change,
    capacity eviction, recent-since-ts filter.
  - `tests/unit/test_market_data_buffer.py` (25) - lazy track,
    never-initialised symbol, rolling-window math, MarketSnapshot
    Spec §11.1 fields, CVD helpers match `compute_cvd`,
    Issue #4 acceptance criterion 3 (no data -> degraded; partial
    data -> stale; fresh data -> clean), live recomputation of
    staleness, Issue #4 acceptance criterion 4 (WS disconnect ->
    DATA_UNRELIABLE), reconnect clears explicit reasons,
    `mark_degraded` / `clear_explicit_degraded` semantics, REST vs
    WS conflict in both directions plus same-tier-newer-wins,
    exchange health propagation (DISCONNECTED, DEGRADED), per-symbol
    liquidation deque, stats consistency, `refresh_from_exchange`
    requires a client, `BinanceClient` skeleton surfaces
    `NotImplementedError`, disconnected-client short-circuit,
    constructor refuses an `api_key` parameter, `BinanceClient`
    still refuses credentials at construction.
  - `tests/unit/test_phase4_no_network.py` (4) - `app/market_data/`
    imports no network library, mentions no `api_key` /
    `api_secret`, never creates `market.db`, and
    `BinanceClient.get_account_snapshot` continues to raise
    `NotImplementedError` with messages that mention "skeleton",
    "phase 4" and "api key".
  - `tests/unit/test_main_entrypoint.py` extended (1 test, now
    Phase 4-aware) - banner contains `Phase 4 - Market Data
    Buffer`, `market_data=...`, `market_snapshots=...`,
    `data_unreliable=...`, and the events DB contains at least one
    `MARKET_SNAPSHOT` event plus one batched
    `DATA_UNRELIABLE` event with `trigger=websocket_disconnect`.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 4 - Market Data
  Buffer`; `__version__` is `1.4.0a4`.
- `app/main.py` - new `_build_phase4_boot_seed()` helper, boot path
  drives the buffer through one full ingest + snapshot + WS
  disconnect / reconnect cycle. The Phase 1
  `_assert_phase1_safety()` and Phase 3 `_assert_phase3_read_only()`
  guards are unchanged. `STATE_TRANSITION` reason updated to
  `phase4_boot`. Exchange shutdown reason updated to
  `phase4_shutdown`.

#### Phase 4 boundary (declared explicitly to avoid drift)

This PR observes the boundary set by Issue #4 and the user-facing
review of PR #14:

1. **Market Data Buffer ONLY.** No Regime / Universe / Liquidity
   engine, no Scanner, no Confirmation, no Manipulation Detector.
2. The buffer is fed by `MockExchangeClient` / fixture data **by
   default**. The boot path uses the deterministic mock; tests use
   deterministic fixtures.
3. **No real Binance WebSocket and no real REST.** `BinanceClient`
   continues to raise `NotImplementedError` for every read method.
4. **No API key.** `BinanceClient.__init__` still refuses any
   credential. `MarketDataBuffer.__init__` exposes no `api_key`
   parameter (asserted by a test that passes the kwarg and expects
   a `TypeError`).
5. **No write surface.** The four `SafeModeViolation` refusals on
   `ExchangeClientBase` (`create_order`, `cancel_order`,
   `set_leverage`, `set_margin_mode`) are unchanged.
6. **No auto-connect.** `MarketDataBuffer` opens no socket; it only
   receives data via `ingest_*` calls or via
   `refresh_from_exchange` against a deterministic
   `MockExchangeClient`.
7. **Tests do not depend on real network.** Both
   `test_phase3_no_network.py` and the new
   `test_phase4_no_network.py` enforce this.
8. **`BinanceClient.get_account_snapshot` remains mock-only /
   skeleton-only in both Phase 3 and Phase 4.** Real account
   snapshots require an authenticated REST call and an API key,
   forbidden until the limited-live phase. Locked by
   `test_binance_client_get_account_snapshot_remains_skeleton` in
   `test_phase4_no_network.py`.

#### Not in Phase 4 (deferred)
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine (will read `is_degraded` from this
  buffer to drive the No-Trade Gate).
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a
  real `create_order` is *allowed* to exist, behind the Risk
  Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports,
  Reflection.

#### Live trading risk
**None.** Phase 4 ships only an in-process buffer and a
deterministic boot drill. No exchange SDK is added. No outbound
HTTP / WebSocket library is imported. No API key is read. No
write surface is added. The Phase 1 safety lock and Phase 3
read-only invariant are unchanged. Six layers of defence (config
lock, Phase 1 boot assertion, Phase 3 read-only assertion, Risk
Engine refusal, base-class write-surface refusal, Phase 4
no-network / no-api-key tests) are all unit-tested.

### Phase 3 - Review fixes (Issue #3 review feedback)

#### Changed

- **Reliability tier alignment** (review item 1). The default
  `OrderBook.reliability` was tier B; this was inconsistent with
  the rest of the PR description and with the actual Phase 4+ source
  (a WS-maintained depth-diff book is tier A). Updated:
  - `app/exchanges/base.ExchangeClientBase.reliability_tiers` now
    returns `get_orderbook -> A` (was B). The full table is now
    locked: `get_recent_trades=A`, `get_orderbook=A`,
    `get_funding_rate=B`, `get_open_interest=B`, `get_symbols=B`,
    `get_account_snapshot=B`.
  - `app/exchanges/models.OrderBook.reliability` default raised from
    `DataReliability.B` to `DataReliability.A`. Adapters that fall
    back to a REST snapshot when the WS link is degraded must tag
    that response tier B explicitly.
  - `MockExchangeClient.get_orderbook` now stamps its synthetic book
    as tier A (it is the in-memory analogue of a WS-maintained book).
    A tier-B `OrderBook` supplied via `MockExchangeSeed.orderbooks`
    is preserved as-is - the mock does not silently upgrade it.
  - 4 new tests pin the new contract:
    `test_reliability_tiers_contract` (full-table assertion),
    `test_reliability_tiers_lists_all_six_read_methods`,
    `test_orderbook_default_reliability_is_a_at_model_level`,
    `test_orderbook_can_be_tagged_tier_b_for_rest_fallback`,
    `test_mock_synthetic_orderbook_is_tier_a`,
    `test_mock_can_serve_a_tier_b_seed_orderbook`.
- **Phase 4 constraint hardened** (review item 2). The Phase 4
  recommendation in the PR description and the
  `BinanceClient.get_*` `NotImplementedError` messages are reworded:
  Phase 4 (Market Data Buffer) must drive the buffer from
  `MockExchangeClient` / fixture data **by default**; any real public
  read-only WS / REST adapter must be opt-in (off by default),
  require no API key, expose no write surface, and not auto-connect
  to the real exchange. `WebSocketManager`'s docstring is reworded
  for the same reason - it no longer claims Phase 4 will adopt any
  particular network library. New test
  `test_binance_real_market_data_methods_message_is_explicit_about_phase4_constraints`
  asserts every public-data `NotImplementedError` message contains
  the four constraint phrases ("opt-in", "off by default", "no API
  key", "no write surface", "auto-connect").
- **`get_account_snapshot` mock-only / skeleton-only** (review item
  3). The `BinanceClient.get_account_snapshot` `NotImplementedError`
  message is rewritten to say explicitly: real account snapshots
  require authentication and an API key, both of which are forbidden
  until the limited-live phase; the only working implementation is
  `MockExchangeClient.get_account_snapshot`. New test
  `test_binance_get_account_snapshot_message_is_explicit_about_no_api_key`
  asserts the message contains "api key", "authenticated",
  "mockexchangeclient", and "limited-live".
- **README** updated with an explicit "Reliability tier contract"
  table and a "Phase 4 constraints" section that declares the four
  Phase 4 invariants up-front so the next PR cannot drift.

#### Tests
**+7 review-fix tests on top of 97 Phase 3 tests = 104 Phase 3 tests
total. Full suite: 211 passed in 1.87s** (107 retained from
Phase 1 / 2 + 104 Phase 3).

#### Live trading risk
None. The review fixes only adjust default reliability tiers,
strengthen `NotImplementedError` messages, and tighten Phase 4
constraint documentation. No new mode flag, no loosened safety lock,
no new dependency, no new write surface.

### Phase 3 - Exchange Gateway Read-Only

#### Added
- **`app/exchanges/` package** introducing the read-only Exchange Gateway
  abstraction. The package never imports an exchange SDK and never opens
  an outbound socket; this is asserted by
  `tests/unit/test_phase3_no_network.py`.
- **`ExchangeClientBase` abstract class** (`app/exchanges/base.py`):
  - 6 abstract read-only methods: `get_symbols`, `get_orderbook`,
    `get_recent_trades`, `get_funding_rate`, `get_open_interest`,
    `get_account_snapshot`.
  - 4 **concrete** write surfaces (`create_order`, `cancel_order`,
    `set_leverage`, `set_margin_mode`) that **always** raise
    `SafeModeViolation`. Subclasses inherit the refusal.
  - `ExchangeHealth` value-object with state transitions
    (`UNINITIALISED -> CONNECTED -> DEGRADED / RECONNECTING /
    DISCONNECTED`), counters and an `is_data_trustworthy()` predicate.
  - `WebSocketManager` skeleton (`connect / disconnect / subscribe /
    unsubscribe`) that emits `DATA_UNRELIABLE` with the pending
    subscription set on every drop. **No real socket is opened in
    Phase 3.**
  - Health transitions emit `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `EXCHANGE_DEGRADED` events through
    `EventRepository`.
  - `_require_trustworthy(surface=...)` helper raises
    `ExchangeConnectionError` whenever the link is not `CONNECTED`
    (Spec §14.2 + §31).
  - `READ_ONLY_METHODS` and `WRITE_SURFACE_METHODS` module-level
    tuples used by the entrypoint and the test suite to assert the
    Phase 3 contract.
  - `assert_read_only()` boot-time guard.
  - `reliability_tiers` static map documenting the default
    `DataReliability` tier each surface returns (Spec §13.3).
- **`BinanceClient` skeleton** (`app/exchanges/binance.py`):
  - All 6 read methods raise `NotImplementedError` pointing at the
    later phase that owns the real adapter (Phase 4 / 8 / 9).
  - All 4 write methods inherit `SafeModeViolation` from the base
    class (asserted by tests; the skeleton must NOT override them).
  - Constructor refuses any `api_key` / `api_secret` (Spec §37 anti-leak).
- **`MockExchangeClient`** (`app/exchanges/mock.py`):
  - Deterministic in-memory implementation used by the entrypoint and
    the test suite. **No network**.
  - Optional `MockExchangeSeed` for fully predictable test fixtures.
  - `simulate_disconnect` / `simulate_reconnect` /
    `simulate_degraded` test hooks drive the No-Trade Gate paths.
  - Tier-A surfaces refuse when not `CONNECTED`; tier-B REST surfaces
    (`get_symbols`, `get_account_snapshot`) remain usable when
    `DEGRADED` per Spec §13.3.
- **Read-only data models** (`app/exchanges/models.py`): Pydantic v2
  frozen models `ExchangeSymbol`, `OrderBook` (+ `OrderBookLevel`,
  with bid/ask sort validation), `RecentTrade`, `FundingRate`,
  `OpenInterest`, `AccountSnapshot`. Each carries an explicit
  `reliability: DataReliability` field with the default tier per
  surface.
- **New core vocabulary**:
  - `app/core/enums.ExchangeConnectionState` enum (`UNINITIALISED /
    CONNECTED / DEGRADED / RECONNECTING / DISCONNECTED`) with an
    `is_trustworthy` property.
  - `app/core/enums.DataReliability.is_at_least()` helper for
    consistent tier comparisons (Spec §13.3).
  - `app/core/events.EventType.{EXCHANGE_CONNECTED,
    EXCHANGE_DISCONNECTED, EXCHANGE_DEGRADED}`. `DATA_UNRELIABLE` was
    already declared in Phase 1.
  - `app/core/errors.SafeModeViolation` (subclass of
    `SafetyViolation`).
  - `app/core/errors.ExchangeError` and
    `app/core/errors.ExchangeConnectionError`.
- **Phase 3 boot self-check** in `python -m app.main`:
  - Instantiates `MockExchangeClient(event_repo=repo, autostart=True)`,
    runs `assert_read_only()`, **probes every banned write surface**
    and refuses to start unless each one raises `SafeModeViolation`.
  - Calls `get_symbols()` to prove the read path works.
  - Registers an `exchange_link` health probe.
  - Emits `EXCHANGE_CONNECTED` on start and
    `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE` on shutdown so
    replay-based tests can confirm the lifecycle closed.
  - Status banner now reports
    `exchange=<name>/<state> exchange_symbols=N exchange_connected_events=1`.
- **97 new unit tests**:
  - `tests/unit/test_exchange_models.py` (15) - `DataReliability`
    ordering (A>B>C>D), `is_at_least` helper,
    `ExchangeConnectionState.is_trustworthy`, `OrderBook` sort
    validation, frozen models, default reliability tiers per model.
  - `tests/unit/test_exchange_base.py` (20) - cannot instantiate the
    ABC directly; `READ_ONLY_METHODS == __abstractmethods__`; write
    surfaces are concrete on the base class; `SafeModeViolation`
    IS-A `SafetyViolation`; `ExchangeError` IS-A `AMARTError` and is
    NOT a `SafetyViolation`; `assert_read_only` refuses when
    `_live_orders_enabled=True`; `WebSocketManager` connect /
    disconnect lifecycle and the `DATA_UNRELIABLE` event payload;
    `ExchangeHealth` counters; `start` / `stop` / `_mark_degraded`
    emit the matching events through `EventRepository`;
    `_require_trustworthy` refuses when uninitialised / disconnected;
    `reliability_tiers` contract; no network library imports.
  - `tests/unit/test_binance_client.py` (20) - `name='binance'`;
    refuses any `api_key` / `api_secret`; every read method raises
    `NotImplementedError`; every write surface refuses with
    `SafeModeViolation`; every read method is overridden on
    `BinanceClient` itself; write surfaces NOT overridden (inherit
    base refusal); module imports no network library.
  - `tests/unit/test_mock_exchange_client.py` (28) - `autostart`
    emits `EXCHANGE_CONNECTED`; default seed has BTCUSDT, ETHUSDT,
    PEPEUSDT; orderbook / trades / funding / OI / account read
    paths; `MockExchangeSeed` determinism; `simulate_disconnect`
    emits `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE`; tier-A
    surfaces refused when `DEGRADED`; tier-B surfaces (symbols,
    account_snapshot) ALLOWED when `DEGRADED`; both refused when
    `DISCONNECTED`; `simulate_reconnect` restores trust + new
    `EXCHANGE_CONNECTED`; write surfaces refuse; mock does NOT
    override write surfaces; lifecycle smoke; no network library
    imports.
  - `tests/unit/test_phase3_no_network.py` (3) - `requirements.txt`
    and `pyproject.toml` contain no exchange SDK / HTTP client; no
    file under `app/` issues an `import` for any forbidden token.
  - Existing `tests/unit/test_main_entrypoint.py` extended to assert
    the Phase 3 banner fields and the new `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `DATA_UNRELIABLE` events.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 3 - Exchange Gateway
  Read-Only`; `__version__` is `1.4.0a3`.
- `app/main.py` - new `_assert_phase3_read_only(client)` guard that
  probes every entry in `WRITE_SURFACE_METHODS` and raises
  `SafeModeViolation` if any of them stops refusing. The existing
  `_assert_phase1_safety()` check is unchanged. Banner extended with
  `exchange=<name>/<state>`, `exchange_symbols=N`,
  `exchange_connected_events=1`. `STATE_TRANSITION` reason updated to
  `phase3_boot`. The exchange is stopped cleanly on shutdown
  (`reason="phase3_shutdown"`), which emits `DATA_UNRELIABLE` +
  `EXCHANGE_DISCONNECTED`.

#### Not in Phase 3 (deferred)
- Issue #4 - real Market Data Buffer; `BinanceClient` read methods
  remain `NotImplementedError` until then.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine.
- Issue #8 - Capital Flow Engine.
- Issue #9 - real Execution FSM + Reconciliation; first place a real
  `create_order` is *allowed* to exist, behind the Risk Engine.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection.

#### Live trading risk
**None.** Phase 3 ships only an abstract read-only gateway plus a
deterministic in-memory mock. The four write surfaces always raise
`SafeModeViolation`; the Phase 1 safety lock is unchanged; no exchange
SDK / HTTP / WebSocket library is installed; no real API key is
accepted by `BinanceClient`. Five layers of defence (config lock, boot
assertion, Phase 3 read-only assertion, Risk Engine refusal, base-class
write-surface refusal) are all unit-tested.

### Phase 2 - Event Sourcing and Database

#### Added
- **Five SQLite databases** (Spec §33.1) opened in WAL mode and migrated
  by an idempotent runner: `events.db`, `trades.db`, `positions.db`,
  `capital.db`, `incidents.db`.
- **New schema files** under `app/database/schemas/`:
  - `trades.sql` - fills (write-once); writers land in Issue #9.
  - `positions.sql` - position lifecycle; writers land in Issues #7/#9.
  - `capital.sql` - `capital_snapshots` (Issue #8) and
    `capital_events_index` (mirror written by Phase 2 EventRepository).
  - `incidents.sql` - `incidents` + `incident_log`; writers land in
    Issues #9/#10.
- **`events.db` schema upgrade**: added the `created_at` column required
  by the Issue #2 field contract; added composite indexes
  `(event_type, timestamp)` and `(symbol, timestamp)` and an
  `order_id` index. The migration auto-upgrades a Phase 1 events.db by
  adding the column and backfilling from `timestamp`.
- **`app/database/connection.DatabaseSet`** - container that opens /
  closes a known set of databases atomically, with typed accessors
  (`.events`, `.trades`, `.positions`, `.capital`, `.incidents`),
  `__iter__`, idempotent `close()`, and an `open_database_set()` context
  manager.
- **`app/database/migrations.migrate_database` and
  `migrate_database_set`** - apply each database's schema; idempotent.
- **`EventRepository` Phase 2 API**:
  - `append_event` / `append_many` (returns events with `created_at`
    populated)
  - `list_events` / `replay_events` (lazy iterator) / `count_events`
  - filters: `event_type`, `event_types` (iterable), `symbol`,
    `source_module`, `position_id`, `order_id`, `since_ts`, `until_ts`,
    `limit`, `offset`
  - persistence failures logged via `loguru` and raised as
    `EventPersistenceError` (no silent loss). Includes a `failed_appends`
    counter for monitoring.
  - capital event helpers: `record_capital_deposit`,
    `record_capital_withdrawal`, `record_profit_harvest`,
    `record_capital_rebase`, `record_risk_budget_recalculated`.
  - **cross-database write**: when constructed with a `capital_conn`
    every `CAPITAL_*` event is mirrored into
    `capital.db.capital_events_index` so Issue #8 has a fast lookup
    table. Mirror failures are logged but do NOT roll back the events
    write (the index is rebuildable from events.db).
- **Phase 1 method aliases preserved** on `EventRepository` (`append`,
  `list`, `replay`, `count`) so the Risk Engine, Telegram bot and
  Execution FSM skeletons keep working unchanged.
- **`scripts/init_db.py`** rewritten to migrate all five databases and
  print each db's journal mode + schema file. Still idempotent.
- **`app/main.py`** opens & migrates all five databases, emits a
  CAPITAL_DEPOSIT marker (paper-mode bookkeeping, amount=0.0) so the
  capital_events_index path is exercised end-to-end. The Phase 1 safety
  lock and `_assert_phase1_safety()` remain unchanged.
- **`app/core/errors.EventPersistenceError`** - typed exception for the
  persistence failure path.
- **`app/core/events.Event.created_at`** - new field; `None` for
  in-memory events, populated by `EventRepository` from the SQLite
  default expression on insert.
- **51 new unit tests**:
  - `tests/unit/test_database_set.py` (12) - DatabaseSet, WAL pragma,
    multi-db migration, Phase-1 -> Phase-2 events.db upgrade.
  - `tests/unit/test_phase2_schemas.py` (8) - column contract for
    trades / positions / capital / incidents tables, event-type
    vocabulary, "no leak from Issue #3/#9/#10" check.
  - `tests/unit/test_event_repository.py` rewritten (31) - full Phase 2
    API surface, filter combinations, persistence failure path, capital
    helpers, capital_events_index mirror.

#### Changed
- `app/__init__.py` - `__phase__` is now `Phase 2 - Event Sourcing and
  Database`; `__version__` is `1.4.0a2`.
- `tests/conftest.py` - new `phase2_dbs` and `events_repo_with_capital`
  fixtures.

#### Not in Phase 2 (deferred)
- Issue #3 - Exchange Gateway (read-only).
- Issue #4 - Market Data Buffer.
- Issue #5 - Regime / Universe / Liquidity engines.
- Issue #6 - Pre-anomaly / Anomaly / Confirmation / Manipulation
  scanners.
- Issue #7 - full Risk Engine; uses positions.db.
- Issue #8 - Capital Flow Engine; uses capital_snapshots and the
  capital_events_index table this PR ships.
- Issue #9 - full Execution FSM + Reconciliation; uses trades.db and
  incidents.db.
- Issue #10 - LLM, Telegram outbound, Replay diff reports, Reflection;
  uses the incidents tables this PR ships.

#### Live trading risk
None. Phase 2 only adds passive SQLite schemas, a connection helper,
the EventRepository extension and tests. No exchange SDK, no outbound
network, no LLM, no Telegram client. Phase 1 safety lock unchanged.

### Phase 1 - Safety Foundation

#### Added
- Project skeleton under `app/`, `tests/`, `scripts/`, `data/`, `docs/`.
- `pyproject.toml` and `requirements.txt` with a minimal dependency set
  (Pydantic, pydantic-settings, PyYAML, loguru, pytest). No exchange SDK,
  no LLM client, no Telegram client.
- Configuration system (`app/config/`) with `defaults.yaml`, `risk.yaml`,
  `strategy.yaml`, validated by Pydantic schemas in `schema.py`. Loader in
  `settings.py` applies a Phase 1 safety lock that hard-codes:
  `trading_mode=paper`, `live_trading_enabled=false`,
  `right_tail_enabled=false`, `llm_enabled=false`,
  `exchange_live_order_enabled=false`. Even malicious env vars cannot
  flip these flags.
- Core domain types: `app/core/enums.py`, `app/core/events.py`,
  `app/core/models.py`, `app/core/clock.py`, `app/core/errors.py`,
  `app/core/constants.py`. Mirrors Spec §11 / §46 / §12.
- SQLite Event Sourcing substrate: `app/database/schema.sql`,
  `connection.py`, `migrations.py`, `repositories.EventRepository`
  (append, append_many, list, replay, count). WAL mode enforced.
- Init script `scripts/init_db.py`.
- Skeletons (no live behaviour):
  - `app/risk/engine.RiskEngine` - rejects any live or right-tail action.
  - `app/execution/fsm.ExecutionFSM` - typed transition table; refuses
    `request_send_order` without a Risk Engine approval.
  - `app/telegram/bot.TelegramCommandCenter` - in-process command bus,
    audit-logs every command, requires confirmation for `/resume`.
  - `app/monitoring/{metrics,health,alerts}.py` - in-memory only.
- Entrypoint `python -m app.main` - asserts the safety lock, initialises
  the events database, drives one Risk Engine self-check + one Telegram
  `/status` audit event, prints a one-line status banner, exits 0.
- Pytest suite covering enums, models, settings safety lock, event
  repository, Risk Engine, Execution FSM, Telegram bus, monitoring, the
  init script, and the entrypoint smoke test.
- `.env.example` (no real keys), `.gitignore` (excludes `.env`,
  `data/sqlite/*`, `*.db`), `docs/CHANGELOG.md`.
- `README.md` re-written to describe Phase 1 scope, paper-mode default,
  and explicit "no live trading" guarantee.

#### Not in Phase 1 (deferred to later issues)
- Issue #2: full Event Sourcing schema for trades / positions / capital /
  incidents databases, replay across multiple databases.
- Issue #3: any Exchange Gateway code, even read-only.
- Issue #4: Market Data Buffer.
- Issue #5: Regime / Universe / Liquidity engines.
- Issue #6: Pre-anomaly / Anomaly / Confirmation / Manipulation scanners.
- Issue #7: full Risk Engine (No-Trade Gate, Account Life Tier,
  circuit breakers).
- Issue #8: Capital Flow Engine (rebase, harvest).
- Issue #9: full Execution FSM with reconciliation against an exchange.
- Issue #10: LLM Interpreter, Telegram outbound, Replay diff reports,
  Reflection.
