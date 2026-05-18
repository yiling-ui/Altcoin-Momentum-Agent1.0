# Changelog

All notable changes to AMA-RT will be recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the project phase plan in `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` §43.

## [Unreleased]

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
