# AMA-RT - Altcoin Momentum Agent (Right Tail Edition)

> **Phase status:** Phase 1 - Safety Foundation. **Paper mode only.**
> This repository does **not** trade real money, does **not** connect to
> any exchange, does **not** call any LLM, and does **not** read real API
> keys. It only ships the safety substrate that all later phases will
> stand on.

---

## What this repository is

This is the implementation of the Phase 1 deliverable described in:

- `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` (the V1.4 production spec)
- GitHub Issue #1 - Phase 1 Safety Foundation

Phase 1 builds the project skeleton, the configuration system, the core
domain types, the SQLite Event Sourcing substrate, and skeletons for the
Risk Engine, Execution FSM, Telegram Command Center, and Monitoring. It
does **not** implement any of the trading logic described in Issues
#2-#10.

## Default safety guarantees

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

The lock is unit-tested. To loosen any of these flags, a future PR must
explicitly raise the project phase, update the test suite, and modify
the lock - no environment override can bypass it.

In addition, `app/main.py` re-asserts these flags at boot and refuses to
start if any of them is wrong (`SafetyViolation`).

## Repository layout

```
app/
  config/         settings + YAML configs (defaults / risk / strategy)
  core/           enums, events, models, clock, errors, constants
  database/       schema.sql, connection helper, migrations, EventRepository
  execution/      Execution FSM skeleton
  risk/           Risk Engine skeleton
  telegram/       Telegram Command Center skeleton (in-process only)
  monitoring/     metrics + health + alerts (in-memory only)
  main.py         Phase 1 entrypoint
scripts/
  init_db.py      Initialise events.db
tests/
  unit/           Pytest suite for every Phase 1 module
docs/
  AMA_RT_V1_4_Production_Spec_Kiro.md  - full V1.4 production spec
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

# 2. Initialise the events database (idempotent):
python -m scripts.init_db

# 3. Run the Phase 1 entrypoint - prints a status banner and exits 0:
python -m app.main

# 4. Run the test suite:
pytest
```

Sample output:

```
[AMA-RT] Phase 1 - Safety Foundation v1.4.0a1 \
  mode=paper live_trading=False right_tail=False \
  llm=False exchange_live_orders=False \
  events_count=2 risk_decision=True/paper_only_skeleton_approval health=ok
```

## What is NOT here yet

Everything in Issues #2 through #10. Specifically:

- No Exchange Gateway, no real WebSocket / REST adapter (Issue #3).
- No Market Data Buffer (Issue #4).
- No Regime / Universe / Liquidity engines (Issue #5).
- No anomaly / confirmation / manipulation scanners (Issue #6).
- No full Risk Engine - the Phase 1 engine only refuses live and
  right-tail actions (Issue #7).
- No Capital Flow Engine, no Profit Harvest, no Rebase (Issue #8).
- No real Execution FSM driver and no Reconciliation (Issue #9).
- No LLM Interpreter, no Telegram outbound bot, no Replay, no
  Reflection (Issue #10).

## Live trading risk

There is **no live trading risk** in this PR. The codebase contains:

- No exchange SDK in dependencies.
- No real `create_order` / `cancel_order` / `set_leverage` call site.
- No outbound HTTP client.
- No Telegram bot library.
- No LLM client.

Every "trading" surface in Phase 1 is either a typed enum, an in-memory
skeleton, or an audit-log entry.

## License

Proprietary. Internal use only.
