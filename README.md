# AMA-RT - Altcoin Momentum Agent (Right Tail Edition)

> **Phase status:** Phase 2 - Event Sourcing and Database. **Paper mode only.**
> This repository does **not** trade real money, does **not** connect to
> any exchange, does **not** call any LLM, and does **not** read real API
> keys. Phase 2 extends the SQLite substrate so future phases (Risk
> Engine, Capital Flow, Execution FSM, Reconciliation, Reflection) have
> a reliable, auditable, replayable event log to stand on.

---

## What this repository is

This is the implementation of the production specification in
`docs/AMA_RT_V1_4_Production_Spec_Kiro.md`.

| Phase | Issue | Status | Branch / PR |
| --- | --- | --- | --- |
| Phase 1 - Safety Foundation | #1  | merged | `feature/phase-1-safety-foundation` (PR #11), `feature/phase-1-review-fixes` (PR #12) |
| Phase 2 - Event Sourcing and Database | #2  | this branch | `feature/phase-2-event-sourcing-database` |
| Phase 3 - Exchange Gateway Read-Only | #3  | open | - |
| Phase 4 - Market Data Buffer | #4  | open | - |
| Phase 5 - Regime / Universe / Liquidity | #5  | open | - |
| Phase 6 - Scanner / Confirmation / Manipulation | #6  | open | - |
| Phase 7 - State Machine / Risk Engine | #7  | open | - |
| Phase 8 - Capital Flow / Profit Harvest / Rebase | #8  | open | - |
| Phase 9 - Execution FSM / Reconciliation | #9  | open | - |
| Phase 10 - LLM / Telegram / Replay / Reflection | #10 | open | - |

## Phase 2 deliverable

Phase 2 extends the Phase 1 SQLite substrate so the project has a
production-quality event-sourcing layer. Specifically:

- **Five separate SQLite databases** (Spec §33.1), each opened in WAL
  mode and migrated by an idempotent runner:

  | DB             | Schema file                          | Phase 2 writes? |
  | -------------- | ------------------------------------ | --------------- |
  | `events.db`    | `app/database/schema.sql`            | yes (`EventRepository`) |
  | `trades.db`    | `app/database/schemas/trades.sql`    | no - schema only (Issue #9) |
  | `positions.db` | `app/database/schemas/positions.sql` | no - schema only (Issue #7) |
  | `capital.db`   | `app/database/schemas/capital.sql`   | yes (`capital_events_index` mirror) |
  | `incidents.db` | `app/database/schemas/incidents.sql` | no - schema only (Issue #9 / #10) |

- **`EventRepository`** with every method Issue #2 requires:
  - `append_event(event)`
  - `append_many(events)`
  - `list_events(...)`
  - `replay_events(...)` (lazy iterator)
  - `count_events(...)`
  - filters: `event_type` / `event_types` / `symbol` / `source_module`
    / `position_id` / `order_id` / `since_ts` / `until_ts`
    / `limit` / `offset`
  - persistence failures are logged via `loguru` and raised as
    `EventPersistenceError` (no silent loss)
  - Phase 1 method names (`append`, `list`, `replay`, `count`) are
    preserved as backwards-compatible aliases so the existing skeleton
    callers (Risk Engine, Telegram, Execution FSM) keep working.

- **Capital event helpers** (Spec §28.3 / Issue #2):
  - `record_capital_deposit(amount, ...)`
  - `record_capital_withdrawal(amount, ...)`
  - `record_profit_harvest(amount, ...)`
  - `record_capital_rebase(exchange_equity, withdrawn_profit, lifetime_equity, trading_capital, ...)`
  - `record_risk_budget_recalculated(new_risk_budget, ...)`

  These wrappers produce canonically-shaped `CAPITAL_*` events. Every
  capital event written through `EventRepository` is **also mirrored**
  into `capital.db`'s `capital_events_index` table when the repository
  was constructed with a `capital_conn`. This lets the Capital Flow
  Engine (Issue #8) answer "which deposit/withdrawal/harvest happened
  in window X?" without scanning the full event log.

  > **Source of truth.** `events.db` is the canonical event log;
  > `capital_events_index` is a *derived, rebuildable* mirror. If a
  > mirror write fails, the repository logs the error but does NOT
  > roll back the events.db write - that would corrupt the canonical
  > log to protect a derived view. Use
  > `EventRepository.rebuild_capital_events_index()` to bring a stale
  > or wiped mirror back in sync with events.db. Issue #8 (Capital
  > Flow Engine) is expected to call this on startup. Pinned by
  > `test_rebuild_capital_events_index_*`.

- **`scripts/init_db.py`** now creates and migrates all five databases
  in one call, prints each database's journal mode and schema file, and
  is idempotent.

- **`python -m app.main`** opens all five databases, migrates them,
  emits a Phase-2 self-check audit trail (RISK_APPROVED, STATE_TRANSITION,
  TELEGRAM_COMMAND_RECEIVED, CAPITAL_DEPOSIT marker), and exits 0.

  > **Boot marker contract (Issue #8 must skip):** the boot CAPITAL_DEPOSIT
  > has `amount=0.0`, `source_module='bootstrap'`,
  > `payload['note']='phase2_boot_paper_marker'`. It is a *boot probe*,
  > not an accounting entry; it MUST NOT change `initial_capital`,
  > `lifetime_equity`, `withdrawn_profit`, `trading_capital` or any
  > performance figure. The contract is pinned by
  > `tests/unit/test_main_entrypoint.py::test_capital_boot_marker_contract_is_safe_for_issue8`.

  > **Banner Risk decision is a self-check, not a trade approval:** the
  > line `risk_decision=True/paper_only_skeleton_approval(paper_self_check_only)`
  > is the paper-mode boot self-check outcome only. The same Risk Engine
  > continues to hard-reject `live_trading_required=True`,
  > `right_tail_amplify=True`, `stop_unconfirmed=True`,
  > `unknown_position=True` - asserted by
  > `test_phase2_boot_risk_engine_still_rejects_live_trading`.

- **`created_at` column** added to the `events` table per Issue #2 field
  contract. The migration auto-upgrades a Phase 1 events.db (no
  `created_at` column) by adding the column and backfilling from
  `timestamp`.

## Default safety guarantees (unchanged from Phase 1)

Settings are loaded from `app/config/defaults.yaml` and validated by
`app/config/schema.py`. Regardless of YAML or environment-variable input,
`app/config/settings.py` applies a Phase 1 safety lock that forces:

| Flag                             | Value     |
| -------------------------------- | --------- |
| `trading_mode`                   | `paper`   |
| `live_trading_enabled`           | `False`   |
| `right_tail_enabled`             | `False`   |
| `llm_enabled`                    | `False`   |
| `exchange_live_order_enabled`    | `False`   |

`app/main.py` re-asserts these flags at boot and refuses to start if any
of them is wrong (`SafetyViolation`). Phase 2 does **not** loosen any of
these.

## Repository layout

```
app/
  config/         settings + YAML configs (defaults / risk / strategy)
  core/           enums, events, models, clock, errors, constants
  database/
    schema.sql              events.db DDL (with created_at)
    schemas/
      trades.sql            trades.db DDL
      positions.sql         positions.db DDL
      capital.sql           capital.db DDL (snapshots + events index)
      incidents.sql         incidents.db DDL (incidents + log)
    connection.py           open_sqlite + DatabaseSet (5 dbs)
    migrations.py           apply_schema, migrate_database_set
    repositories.py         EventRepository (full Phase 2 API)
  execution/      Execution FSM skeleton (full impl in Issue #9)
  risk/           Risk Engine skeleton (full impl in Issue #7)
  telegram/       Telegram Command Center skeleton (Issue #10)
  monitoring/     metrics + health + alerts (in-memory)
  main.py         Phase 2 entrypoint
scripts/
  init_db.py      Initialise all five Phase 2 databases
tests/
  unit/
    test_database_set.py        Phase 2 multi-db connection + migrations
    test_phase2_schemas.py      Schema column contract for the 4 new dbs
    test_event_repository.py    Full repo API + capital helpers
    test_init_db_script.py      Multi-db init + idempotency
    test_main_entrypoint.py     End-to-end smoke test
    ... + the Phase 1 tests (enums, models, settings, telegram, etc.)
docs/
  AMA_RT_V1_4_Production_Spec_Kiro.md  - V1.4 production spec
  IMPLEMENTATION_PLAN.md, GO_NO_GO.md, TEST_MATRIX.md
  CHANGELOG.md
.env.example      Placeholder env vars (no real keys)
.gitignore        Excludes .env, data/, *.db, etc.
pyproject.toml
requirements.txt
```

## Running

```bash
# 1. Install Python 3.11+ then:
pip install -r requirements.txt

# 2. Initialise all five databases (idempotent):
python -m scripts.init_db
# Sample output:
# [ama-rt][init_db] OK trading_mode=paper sqlite_dir=/.../sqlite
# [ama-rt][init_db]   events.db      journal=wal    schema=schema.sql
# [ama-rt][init_db]   trades.db      journal=wal    schema=trades.sql
# [ama-rt][init_db]   positions.db   journal=wal    schema=positions.sql
# [ama-rt][init_db]   capital.db     journal=wal    schema=capital.sql
# [ama-rt][init_db]   incidents.db   journal=wal    schema=incidents.sql

# 3. Run the Phase 2 entrypoint - prints a status banner and exits 0:
python -m app.main
# Sample output:
# [AMA-RT] Phase 2 - Event Sourcing and Database v1.4.0a2 mode=paper \
#   live_trading=False right_tail=False llm=False exchange_live_orders=False \
#   databases=5 events_count=4 capital_events=1 \
#   risk_decision=True/paper_only_skeleton_approval(paper_self_check_only) \
#   health=ok

# 4. Run the test suite:
pytest
```

To override the data directory (used by tests):

```bash
AMA_DATA_DIR=/tmp/ama python -m scripts.init_db
```

## Programmatic usage (Phase 2 API)

```python
from app.database.connection import DatabaseSet
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.core.events import Event, EventType

with DatabaseSet.open("./data/sqlite") as dbs:
    migrate_database_set(dbs)
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)

    repo.record_capital_deposit(amount=100.0, note="seed")
    repo.record_capital_withdrawal(amount=80.0, note="harvest")

    for event in repo.replay_events(event_type=EventType.CAPITAL_WITHDRAWAL):
        print(event.event_id, event.payload)
```

## What is NOT here yet

Everything in Issues #3 through #10. Specifically:

- No Exchange Gateway, no real WebSocket / REST adapter (Issue #3).
- No Market Data Buffer (Issue #4).
- No Regime / Universe / Liquidity engines (Issue #5).
- No anomaly / confirmation / manipulation scanners (Issue #6).
- No full Risk Engine - the Phase 1 engine still only refuses live and
  right-tail actions (Issue #7).
- No Capital Flow Engine, no Profit Harvest logic, no Rebase
  computation. Phase 2 only ships the **event recording** for these;
  Issue #8 implements the engine that *acts* on the events.
- No real Execution FSM driver, no Reconciliation against an exchange
  (Issue #9). Phase 2 only ships the `trades.db` and `incidents.db`
  schemas.
- No LLM Interpreter, no Telegram outbound bot, no Replay diff reports,
  no Reflection (Issue #10).

## Live trading risk

**There is no live trading risk in Phase 2.** This PR adds:

- Four new SQLite schemas (passive table definitions).
- A multi-database connection helper.
- An extended `EventRepository` API.
- A capital event recorder (write-only audit trail; *not* a Capital
  Flow Engine).
- Tests.

What this PR does NOT add:

- No exchange SDK in dependencies.
- No `create_order` / `cancel_order` / `set_leverage` call site.
- No outbound HTTP client.
- No Telegram bot library, no LLM client.
- No new mode flags, no loosened safety lock.

The Phase 1 `_apply_phase1_safety_lock()` and the
`_assert_phase1_safety()` boot-time check both remain unchanged and
covered by the same parametrised tests.

## License

Proprietary. Internal use only.
