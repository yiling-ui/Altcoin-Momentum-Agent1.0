# AMA-RT - Altcoin Momentum Agent (Right Tail Edition)

> **Phase status:** Phase 3 - Exchange Gateway Read-Only. **Paper mode only.**
> The Exchange Gateway shipped in this branch is **read-only by construction**.
> This repository does **not** trade real money, does **not** open any
> outbound network socket, does **not** import any exchange SDK
> (`ccxt`, `binance-connector`, `python-binance` are intentionally
> absent from `requirements.txt`), does **not** call any LLM, and does
> **not** read real API keys. Phase 3 introduces an abstract
> `ExchangeClientBase` whose four write surfaces (`create_order`,
> `cancel_order`, `set_leverage`, `set_margin_mode`) **always** raise
> `SafeModeViolation`. The only concrete client wired into
> `python -m app.main` is `MockExchangeClient`, which serves
> deterministic in-memory data.

---

## What this repository is

This is the implementation of the production specification in
`docs/AMA_RT_V1_4_Production_Spec_Kiro.md`.

| Phase | Issue | Status | Branch / PR |
| --- | --- | --- | --- |
| Phase 1 - Safety Foundation | #1  | merged | `feature/phase-1-safety-foundation` (PR #11), `feature/phase-1-review-fixes` (PR #12) |
| Phase 2 - Event Sourcing and Database | #2  | merged | `feature/phase-2-event-sourcing-database` (PR #13) |
| Phase 3 - Exchange Gateway Read-Only | #3  | this branch | `feature/phase-3-exchange-gateway-read-only` |
| Phase 4 - Market Data Buffer | #4  | open | - |
| Phase 5 - Regime / Universe / Liquidity | #5  | open | - |
| Phase 6 - Scanner / Confirmation / Manipulation | #6  | open | - |
| Phase 7 - State Machine / Risk Engine | #7  | open | - |
| Phase 8 - Capital Flow / Profit Harvest / Rebase | #8  | open | - |
| Phase 9 - Execution FSM / Reconciliation | #9  | open | - |
| Phase 10 - LLM / Telegram / Replay / Reflection | #10 | open | - |

## Phase 3 deliverable

Phase 3 introduces the `app/exchanges/` package - the **read-only**
abstraction every later phase will sit on top of. Specifically:

- **`ExchangeClientBase` abstract class** (`app/exchanges/base.py`)
  - 6 abstract read-only methods every concrete client must implement:
    `get_symbols`, `get_orderbook`, `get_recent_trades`,
    `get_funding_rate`, `get_open_interest`, `get_account_snapshot`.
  - 4 **concrete** write surfaces (`create_order`, `cancel_order`,
    `set_leverage`, `set_margin_mode`) that **always** raise
    `SafeModeViolation`. Subclasses cannot accidentally overwrite the
    refusal - they would have to delete the inherited method on
    purpose, and the test suite asserts that they have not.
  - `ExchangeHealth` value-object with state transitions (
    `UNINITIALISED -> CONNECTED -> DEGRADED / RECONNECTING /
    DISCONNECTED`), counters and an `is_data_trustworthy()` predicate.
  - `WebSocketManager` skeleton (`connect / disconnect / subscribe /
    unsubscribe`) that emits a `DATA_UNRELIABLE` event with the
    pending subscription set on every drop. **No real socket is
    opened in Phase 3.**
  - Health transitions emit `EXCHANGE_CONNECTED` /
    `EXCHANGE_DISCONNECTED` / `EXCHANGE_DEGRADED` events through
    `EventRepository` so the Phase 2 substrate can replay the gateway
    lifecycle.
  - `_require_trustworthy(surface=...)` helper that refuses tier-A
    reads with `ExchangeConnectionError` whenever the link is not
    `CONNECTED` (Spec §14.2 + §31).
  - `reliability_tiers` static map that documents the default
    `DataReliability` tier each surface returns (Spec §13.3).

- **`BinanceClient` skeleton** (`app/exchanges/binance.py`)
  - Real Binance USDT-M perpetual implementation lands in Phase 4
    (Market Data Buffer) and Phase 9 (Execution FSM). Phase 3 ships
    the class so future phases have a stable target to extend.
  - All 6 read methods raise `NotImplementedError`.
  - All 4 write methods inherit the base-class `SafeModeViolation`
    refusal.
  - The constructor **refuses** if any `api_key` / `api_secret` is
    supplied (Spec §37 anti-leak rule). Phase 3 must not hold a real
    key in process memory.
  - The module imports no exchange SDK and no outbound network
    library - asserted by `tests/unit/test_phase3_no_network.py`.

- **`MockExchangeClient`** (`app/exchanges/mock.py`)
  - Deterministic in-memory implementation used by the entrypoint and
    the test suite. **No network**.
  - Optional `MockExchangeSeed` lets tests inject fully predictable
    symbol lists, order books, tapes, funding, OI, and account
    snapshots.
  - `simulate_disconnect` / `simulate_reconnect` /
    `simulate_degraded` test hooks drive the Phase 4+ No-Trade Gate
    paths.
  - Tier-A surfaces (`get_orderbook`, `get_recent_trades`) refuse when
    not `CONNECTED`; tier-B REST surfaces (`get_symbols`,
    `get_account_snapshot`) remain usable when `DEGRADED` per Spec
    §13.3.

- **Phase 3 boot self-check** in `python -m app.main`
  - The entrypoint instantiates `MockExchangeClient`, runs
    `assert_read_only()`, **probes every banned write surface** and
    refuses to start unless each one raises `SafeModeViolation`.
  - One `EXCHANGE_CONNECTED` and (on shutdown) one
    `EXCHANGE_DISCONNECTED` + `DATA_UNRELIABLE` event are written so
    replay tests can confirm the lifecycle.
  - The status banner now reports
    `exchange=<name>/<state> exchange_symbols=N exchange_connected_events=1`.
  - The Phase 1 safety lock and `_assert_phase1_safety()` boot check
    remain unchanged. Phase 3 adds `_assert_phase3_read_only()` *on
    top* of them.

- **New core vocabulary**
  - `ExchangeConnectionState` enum (`UNINITIALISED / CONNECTED /
    DEGRADED / RECONNECTING / DISCONNECTED`) with an
    `is_trustworthy` predicate.
  - `DataReliability.is_at_least()` helper so every later module
    compares tiers consistently.
  - New `EventType` values: `EXCHANGE_CONNECTED`,
    `EXCHANGE_DISCONNECTED`, `EXCHANGE_DEGRADED`. `DATA_UNRELIABLE`
    was already declared in Phase 1.
  - New typed errors: `SafeModeViolation` (subclass of
    `SafetyViolation`), `ExchangeError`, `ExchangeConnectionError`.

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
of them is wrong (`SafetyViolation`). Phase 3 does **not** loosen any
of these. Phase 3 adds an *additional* runtime guard,
`_assert_phase3_read_only()`, that probes every banned write surface
and refuses to boot unless each one raises `SafeModeViolation`.

## Repository layout

```
app/
  config/         settings + YAML configs (defaults / risk / strategy)
  core/           enums, events, models, clock, errors, constants
                  (Phase 3: ExchangeConnectionState enum, EXCHANGE_*
                   event types, SafeModeViolation / ExchangeError)
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
  exchanges/                ## Phase 3 - read-only Exchange Gateway
    __init__.py             public exports
    models.py               ExchangeSymbol, OrderBook, RecentTrade,
                            FundingRate, OpenInterest, AccountSnapshot
    base.py                 ExchangeClientBase + ExchangeHealth +
                            WebSocketManager + write-surface refusals
    binance.py              BinanceClient skeleton (NotImplementedError)
    mock.py                 MockExchangeClient (deterministic, no network)
  execution/      Execution FSM skeleton (full impl in Issue #9)
  risk/           Risk Engine skeleton (full impl in Issue #7)
  telegram/       Telegram Command Center skeleton (Issue #10)
  monitoring/     metrics + health + alerts (in-memory)
  main.py         Phase 3 entrypoint with read-only self-check
scripts/
  init_db.py      Initialise all five Phase 2 databases
tests/
  unit/
    test_database_set.py            multi-db connection + migrations
    test_phase2_schemas.py          Phase 2 schema column contract
    test_event_repository.py        EventRepository full Phase 2 API
    test_init_db_script.py          init_db.py
    test_main_entrypoint.py         entrypoint smoke incl. Phase 3
    test_exchange_models.py         Phase 3 model contracts + tiers
    test_exchange_base.py           ExchangeClientBase + WS + Health
    test_binance_client.py          BinanceClient skeleton refusals
    test_mock_exchange_client.py    MockExchangeClient lifecycle
    test_phase3_no_network.py       repo-wide no-SDK / no-import scan
    ... + the Phase 1 tests (enums, models, settings, telegram, etc.)
docs/
  AMA_RT_V1_4_Production_Spec_Kiro.md  - V1.4 production spec
  IMPLEMENTATION_PLAN.md, GO_NO_GO.md, TEST_MATRIX.md
  CHANGELOG.md
.env.example      Placeholder env vars (no real keys)
.gitignore        Excludes .env, data/, *.db, etc.
pyproject.toml
requirements.txt  No exchange SDK, no HTTP client
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

# 3. Run the Phase 3 entrypoint - prints a status banner and exits 0:
python -m app.main
# Sample output:
# [AMA-RT] Phase 3 - Exchange Gateway Read-Only v1.4.0a3 mode=paper \
#   live_trading=False right_tail=False llm=False exchange_live_orders=False \
#   databases=5 events_count=5 capital_events=1 \
#   exchange=mock/connected exchange_symbols=3 exchange_connected_events=1 \
#   risk_decision=True/paper_only_skeleton_approval health=ok

# 4. Run the test suite (204 tests):
pytest
```

To override the data directory (used by tests):

```bash
AMA_DATA_DIR=/tmp/ama python -m scripts.init_db
```

## Programmatic usage (Phase 3 read-only API)

```python
from app.exchanges import MockExchangeClient
from app.core.errors import SafeModeViolation, ExchangeConnectionError

client = MockExchangeClient(autostart=True)

# Read-only surfaces:
symbols = client.get_symbols()
book = client.get_orderbook("BTCUSDT", depth=5)
trades = client.get_recent_trades("BTCUSDT", limit=10)
funding = client.get_funding_rate("BTCUSDT")
oi = client.get_open_interest("BTCUSDT")
account = client.get_account_snapshot()

# Write surfaces always refuse:
try:
    client.create_order(symbol="BTCUSDT", side="buy", qty=1.0)
except SafeModeViolation as exc:
    print("expected:", exc)

# Disconnect simulation:
client.simulate_disconnect(reason="test")
try:
    client.get_orderbook("BTCUSDT")
except ExchangeConnectionError as exc:
    print("expected:", exc)
```

## What is NOT here yet

Everything in Issues #4 through #10. Specifically:

- **No real exchange adapter.** `BinanceClient` is a skeleton; every
  read method raises `NotImplementedError`. Real REST / WebSocket
  wiring lands in Issue #4 (Market Data Buffer) and Issue #9
  (Execution FSM / Reconciliation). The Phase 1 safety lock plus the
  Phase 3 `SafeModeViolation` refusals will continue to gate any
  write attempt that future phases add.
- No Market Data Buffer (Issue #4).
- No Regime / Universe / Liquidity engines (Issue #5).
- No anomaly / confirmation / manipulation scanners (Issue #6).
- No full Risk Engine - the Phase 1 engine still only refuses live and
  right-tail actions (Issue #7).
- No Capital Flow Engine; Phase 2 ships only the **event recording**
  for it (Issue #8).
- No real Execution FSM driver, no Reconciliation against an exchange
  (Issue #9).
- No LLM Interpreter, no Telegram outbound bot, no Replay diff reports,
  no Reflection (Issue #10).

## Live trading risk

**There is no live trading risk in Phase 3.** This PR adds:

- An abstract `ExchangeClientBase` whose four write surfaces are
  *concrete on the base class* and **always** raise `SafeModeViolation`.
- A `BinanceClient` skeleton that raises `NotImplementedError` on every
  read method and refuses to accept any API credential.
- A `MockExchangeClient` that returns deterministic in-memory data and
  inherits the same write-surface refusal.
- New core vocabulary (`ExchangeConnectionState`, `SafeModeViolation`,
  `ExchangeError`, `EXCHANGE_*` event types) plus tests.

What this PR does NOT add:

- No exchange SDK in `requirements.txt` / `pyproject.toml` (asserted
  by `tests/unit/test_phase3_no_network.py`).
- No real `create_order` / `cancel_order` / `set_leverage` /
  `set_margin_mode` call site.
- No outbound HTTP / WebSocket client of any kind in `app/`.
- No Telegram bot library, no LLM client.
- No new mode flags, no loosened safety lock.

Defence in depth (cumulative):

1. `app/config/settings.py::_apply_phase1_safety_lock()` overwrites
   the five flags after YAML + env loading.
2. `app/main.py::_assert_phase1_safety()` raises `SafetyViolation` at
   boot if any flag has drifted.
3. `app/main.py::_assert_phase3_read_only()` probes every banned
   write surface and raises `SafeModeViolation` if any of them stops
   refusing.
4. `app/risk/engine.py` rejects `live_trading_required=True` and
   `right_tail_amplify=True` requests.
5. `app/exchanges/base.py::ExchangeClientBase.{create_order,
   cancel_order, set_leverage, set_margin_mode}` always raise
   `SafeModeViolation`.

All five layers are unit-tested.

## License

Proprietary. Internal use only.
