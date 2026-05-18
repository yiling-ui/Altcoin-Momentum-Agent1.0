# Changelog

All notable changes to AMA-RT will be recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the project phase plan in `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` §43.

## [Unreleased]

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
  for the same reason - it no longer claims Phase 4 will plug in a
  real `aiohttp` / `websockets` client. New test
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
