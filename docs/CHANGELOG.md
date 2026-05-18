# Changelog

All notable changes to AMA-RT will be recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the project phase plan in `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` §43.

## [Unreleased]

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
