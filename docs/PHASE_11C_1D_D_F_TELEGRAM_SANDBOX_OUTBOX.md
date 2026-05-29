# Phase 11C.1D-D-F — Telegram Sandbox Outbox v0 (PR99)

> **Status: IN_REVIEW** (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Mode: paper only.** **Phase 12: FORBIDDEN.**
> **Trade authority: false. Live capital: false. Live trading:
> false. Auto-tuning: disabled. Telegram outbound: disabled.
> Telegram production / live channel: disabled. Telegram command
> authority: disabled. Binance private API: disabled.
> LLM / DeepSeek: not invoked. Network: never opened.**

## 1. Purpose

This phase ships the **Telegram Sandbox Outbox v0** — the
deterministic, paper-only, **file-only** Telegram notification
surface of the strict blind walk-forward stack defined by Phase
11C.1D-D (PR93, the *Strict Blind Walk-forward Sim-Live
Constitution*).

PR99 implements the *sixth* anti-future-lookahead infrastructure
block of that stack:

  - the closed taxonomy of Telegram sandbox message types
    (`TelegramSandboxMessageType`),
  - the closed taxonomy of Telegram sandbox message severities
    (`TelegramSandboxSeverity`),
  - the four mandatory simulated / no-live transcript labels,
  - the frozen, JSON-serialisable Telegram sandbox message
    (`TelegramSandboxMessage`),
  - the frozen sandbox outbox configuration
    (`TelegramSandboxOutboxConfig`),
  - the deterministic, paper-only, file-only outbox
    (`TelegramSandboxOutbox`).

The outbox writes only deterministic local JSONL + Markdown
transcript files for operator review and blind-run evidence. It
NEVER opens a network socket, NEVER calls the Telegram Bot API,
NEVER reads a Telegram production token, NEVER targets a
production / live channel, NEVER accepts an inbound command, NEVER
carries Telegram command authority, NEVER authorises a runtime
config patch, NEVER touches the Risk Engine, the Execution FSM, the
real exchange gateway, or any runtime config.

PR99 does **NOT**:

  - implement the **Blind Walk-forward Runner** (PR100),
  - connect the outbox to a real Telegram bot,
  - target a production / live Telegram channel,
  - read a Telegram production token,
  - accept inbound Telegram commands,
  - touch the Risk Engine, Execution FSM, real exchange gateway,
    or any runtime config.

## 2. Relation to PR93 (Strict Blind Walk-forward Sim-Live
##    Constitution)

PR99 is the §13 artefact of the constitution: a paper-only,
file-only Telegram notification surface that produces
deterministic JSONL + Markdown transcripts for operator review and
blind-run evidence. It holds every safety boundary defined by
PR93:

| flag | value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `simulated_only` | `True` |
| `no_live_order` | `True` |
| `no_live_order_assertion` | `True` |
| `no_real_capital_assertion` | `True` |
| `no_telegram_command_authority` | `True` |
| `live_trading` | `False` |
| `live_capital_enabled` | `False` |
| `exchange_live_orders` | `False` |
| `binance_private_api_enabled` | `False` |
| `signed_endpoint_reachable` | `False` |
| `private_websocket_reachable` | `False` |
| `account_endpoint_reachable` | `False` |
| `order_endpoint_reachable` | `False` |
| `position_endpoint_reachable` | `False` |
| `leverage_endpoint_reachable` | `False` |
| `margin_endpoint_reachable` | `False` |
| `real_exchange_order_path` | `False` |
| `real_capital` | `False` |
| `telegram_outbound_enabled` | `False` |
| `telegram_live_command_authority` | `False` |
| `telegram_production_channel_enabled` | `False` |
| `ai_trade_authority` | `False` |
| `trade_authority` | `False` |
| `auto_tuning_allowed` | `False` |
| `phase_12_forbidden` | **`True`** |

These flags are mirrored in `_safety_payload()` in
`app/sim/telegram_sandbox_outbox.py` and re-asserted on every
serialisation boundary (`to_dict()` / `to_json()` /
`safety_payload()`).

## 3. Relation to PR94 / PR95 / PR96 / PR97 / PR98

PR99 strictly **consumes** the existing strict blind walk-forward
substrate. It does **NOT** modify any PR94..PR98 source.

  - **PR94 — SimulationClock + Time-Wall Guard.** PR99 timestamps
    every `TelegramSandboxMessage` via `SimulationClock`-derived
    simulated time
    (:pyattr:`TelegramSandboxMessage.timestamp_simulated`). PR99
    NEVER consults the wall-clock. Every `to_dict()` /
    `safety_payload()` payload PR99 produces is passed through
    `assert_no_forbidden_fields` from PR94's time-wall guard.
  - **PR95 — Historical Market Store v0.** PR99 reads no market
    data directly; it consumes the simulated outputs of the PR98
    `SimulatedCapitalFlowEngine` / `TradeLedger` (and the PR97
    `MockExchange`) only when a caller chooses to pipe them in as
    `body` / `evidence_refs`. PR99 itself NEVER consults the
    Historical Market Store.
  - **PR96 — ReplayFeedProvider v0.** PR99 reads no replay batch
    directly; the caller (a future PR100 Blind Runner) is
    responsible for relaying a `ReplayFeedBatch` summary into a
    `TelegramSandboxMessage` if it wishes to alert on it.
  - **PR97 — MockExchange + Pessimistic Fill Model v0.** PR99
    reads no `MockOrder` / `MockFill` directly; the caller may
    summarise a fill into the `body` / `evidence_refs` of a
    `SIMULATED_ENTRY_ALERT` / `SIMULATED_EXIT_ALERT` /
    `FORCED_EXIT` message. PR99 NEVER advertises a real exchange
    order id, an api key, an api secret, a signed-endpoint
    reference, or a real account id.
  - **PR98 — Simulated Capital Flow + Trade Ledger v0.** PR99
    reads no `SimulatedCapitalState` / `TradeLedgerEntry` /
    `EquityTimeseriesPoint` directly; the caller may summarise
    them into `EQUITY_SUMMARY` / `FAILURE_LEDGER_SUMMARY` /
    `MONTHLY_BLIND_TEST_SUMMARY` messages. PR99 NEVER claims
    trade authority or live-capital authority over the engine's
    state.

## 4. Sandbox outbox schema

### 4.1 `TelegramSandboxMessage`

Frozen, JSON-serialisable, paper-only:

  - `message_id` (str, non-empty),
  - `timestamp_simulated` (timezone-aware UTC `datetime`),
  - `message_type` (closed taxonomy — see §5),
  - `title` (str, non-empty),
  - `body` (str, non-empty),
  - `severity` (closed taxonomy — `INFO` / `NOTICE` / `WARNING` /
    `CRITICAL`),
  - `symbol` (Optional[str]),
  - `evidence_refs` (Tuple[str, ...]),
  - hard-pinned safety markers (cannot be flipped at
    construction): `sandbox_only=True`,
    `no_live_order_assertion=True`,
    `no_real_capital_assertion=True`,
    `no_telegram_command_authority=True`,
    `phase_12_forbidden=True`, `trade_authority=False`,
    `auto_tuning_allowed=False`.

`TelegramSandboxMessage.to_dict()` runs through
`assert_no_forbidden_fields` and an extra outbox-specific guard
that rejects every Telegram-bot-token / production-channel-id /
api-key / api-secret / real-exchange-order-id / signed-endpoint
field name.

### 4.2 `TelegramSandboxOutboxConfig`

Frozen configuration:

  - `output_jsonl_path` (str, default
    `data/reports/telegram_sandbox_outbox.jsonl`),
  - `output_markdown_path` (str, default
    `data/reports/telegram_sandbox_messages.md`),
  - `append_mode` (bool, default `False`),
  - `include_evidence_refs` (bool, default `True`),
  - `max_message_body_chars` (Optional[int], default `None`),
  - hard-pinned safety markers (cannot be flipped):
    `sandbox_only=True`, `telegram_outbound_enabled=False`,
    `telegram_live_command_authority=False`,
    `telegram_production_channel_enabled=False`,
    `command_authority=False`.

Tests **MUST** instantiate the config with a
`tmp_path`-based output path. The default
`data/reports/telegram_sandbox_*` paths are NEVER touched by tests.

### 4.3 `TelegramSandboxOutbox`

Public API:

  - `append_message(message)` — append a single message; defensive
    re-check of every hard-pinned safety marker; raises on any
    forbidden field.
  - `append_messages(messages)` — bulk append.
  - `render_message(message)` — return the deterministic Markdown
    rendering of a single message (with the four mandatory labels
    on dedicated lines at the very top).
  - `write_jsonl(path=None)` — write every appended message as one
    JSON object per line, `sort_keys=True`, deterministic.
  - `write_markdown_transcript(path=None)` — write the full
    Markdown transcript (header + per-message section).
  - `list_messages()` — return the appended messages as a
    deterministic tuple.
  - `reset()` — clear the in-memory message list (does NOT
    truncate any on-disk file).
  - `safety_payload()` — return the paper-only safety boundary
    payload.
  - `to_dict()` — return the deterministic outbox snapshot.

Public properties (defensive tripwires): `config`, `sandbox_only`
(=`True`), `telegram_outbound_enabled` (=`False`),
`telegram_live_command_authority` (=`False`),
`telegram_production_channel_enabled` (=`False`),
`no_live_order_assertion` (=`True`),
`no_real_capital_assertion` (=`True`),
`no_telegram_command_authority` (=`True`),
`phase_12_forbidden` (=`True`), `trade_authority` (=`False`),
`auto_tuning_allowed` (=`False`), `message_count`.

The outbox exposes **no** public method with a Telegram / network
verb (`send_message`, `send_document`, `send_telegram`, `post`,
`get`, `connect`, `open_websocket`, `place_order`, `sign`, etc.).

## 5. Message type taxonomy

`TelegramSandboxMessageType.ALLOWED` is a closed frozenset of
exactly the following 13 values:

  - `SIMULATED_ENTRY_ALERT`
  - `SIMULATED_EXIT_ALERT`
  - `RISK_REJECTION`
  - `FORCED_EXIT`
  - `STALE_FEED`
  - `OUTAGE`
  - `DATA_GAP`
  - `RIGHT_TAIL_CAPTURED`
  - `SEVERE_MISSED_TAIL`
  - `EQUITY_SUMMARY`
  - `FAILURE_LEDGER_SUMMARY`
  - `MONTHLY_BLIND_TEST_SUMMARY`
  - `AI_OPERATOR_BRIEFING_READY`

Each value is a paper-only descriptor of the **kind** of sandbox
notification being recorded. None of these values is a trade
instruction, a runtime patch, or a Telegram command authority
signal. They appear only as JSON / Markdown **values**, never as
field **names**, so the project-wide
`app.sim.time_wall_guard.FORBIDDEN_OUTPUT_FIELDS` guard remains
untouched.

## 6. Mandatory simulated / no-live labels

Every rendered Markdown message MUST contain — verbatim, on its
own dedicated line, at the very top of the rendering — all four
of:

  - `[SIMULATED HISTORICAL BLIND TEST]`
  - `[NO LIVE ORDER]`
  - `[NO REAL CAPITAL]`
  - `[NO TELEGRAM COMMAND AUTHORITY]`

These labels are exposed as module constants
(`SIMULATED_HISTORICAL_BLIND_TEST_LABEL`,
`NO_LIVE_ORDER_LABEL`, `NO_REAL_CAPITAL_LABEL`,
`NO_TELEGRAM_COMMAND_AUTHORITY_LABEL`) and as the tuple
`MANDATORY_LABELS`.

The Markdown transcript also re-renders the four labels in its
header, plus a per-message footer pinning every disabled-by-design
flag (`telegram_outbound_enabled=false`,
`telegram_live_command_authority=false`,
`telegram_production_channel_enabled=false`, etc.).

## 7. JSONL output

`TelegramSandboxOutbox.write_jsonl(path=None)` writes one JSON
object per line, `sort_keys=True`, UTF-8 encoded, **deterministic**
given identical inputs. Each JSON object is a
`TelegramSandboxMessage.to_dict()` payload, with the safety-boundary
keys (`sandbox_only`, `simulated_only`, `no_live_order`,
`no_live_order_assertion`, `no_real_capital_assertion`,
`no_telegram_command_authority`, `live_trading`,
`live_capital_enabled`, `exchange_live_orders`,
`binance_private_api_enabled`, `signed_endpoint_reachable`,
`private_websocket_reachable`, `account_endpoint_reachable`,
`order_endpoint_reachable`, `position_endpoint_reachable`,
`leverage_endpoint_reachable`, `margin_endpoint_reachable`,
`real_exchange_order_path`, `real_capital`,
`telegram_outbound_enabled`, `telegram_live_command_authority`,
`telegram_production_channel_enabled`, `ai_trade_authority`,
`trade_authority`, `auto_tuning_allowed`, `phase_12_forbidden`)
re-pinned on every record.

Default path: `data/reports/telegram_sandbox_outbox.jsonl`. Tests
MUST override this with a `tmp_path`-based path.

## 8. Markdown transcript output

`TelegramSandboxOutbox.write_markdown_transcript(path=None)` writes
a deterministic Markdown transcript:

  - a header (with the four mandatory labels and a tripwire block),
  - one section per appended message (rendered via
    `render_message(...)`).

Default path: `data/reports/telegram_sandbox_messages.md`. Tests
MUST override this with a `tmp_path`-based path.

## 9. `evidence_refs` usage

`TelegramSandboxMessage.evidence_refs` is a tuple of opaque
non-empty strings naming a related evidence record (typically a
`ReplayFeedBatch.batch_id`, a `MockOrder.order_id`, a
`MockFill.fill_id`, a `TradeLedgerEntry.trade_id`, an
`EquityTimeseriesPoint` index, an AI briefing index, etc.).

`evidence_refs` are preserved verbatim in the in-memory message,
in `to_dict()`, in the JSONL output, and in the Markdown
transcript when `config.include_evidence_refs=True` (the default).
Setting `config.include_evidence_refs=False` strips them from the
JSONL / Markdown output but the in-memory message is unchanged.

The `evidence_refs` MUST NOT carry a Telegram bot token, a
production / live channel id, an api key, an api secret, a real
exchange order id, a real account id, or a signed-endpoint
reference. Operators are responsible for ensuring the values they
pass to `evidence_refs` are paper-only references.

## 10. Forbidden behaviour (PR99 cannot, regardless of caller intent)

  - call the Telegram Bot API,
  - read a Telegram production token,
  - send a real Telegram message,
  - target a production / live Telegram channel,
  - accept an inbound Telegram command,
  - carry Telegram command authority,
  - call DeepSeek / OpenAI / Anthropic / any LLM,
  - call Binance private API / open a private websocket / fetch
    account / order / position / leverage / margin endpoints,
  - place a real order,
  - emit any direction / sizing / risk / execution-config field,
  - emit any runtime-tuning patch (`runtime_config_patch` /
    `symbol_limit_patch` / `threshold_patch` /
    `candidate_pool_patch` / `regime_weight_patch` /
    `strategy_parameter_patch`),
  - emit any `apply_change` / `deploy_change` / `enable_live` /
    `live_ready` / `trading_approved` flag,
  - emit a real exchange order id, a real account id, an api key,
    an api secret, a Telegram bot token, a production channel id,
    or a signed-endpoint reference,
  - authorise live trading or auto-tuning,
  - implement the Blind Walk-forward Runner (PR100),
  - enter Phase 12.

The Risk Engine remains the **single trade-decision gate**.

## 11. Files added by this PR

  - `app/sim/telegram_sandbox_outbox.py`
    - `TelegramSandboxMessageType`, `TelegramSandboxSeverity`
      (closed taxonomies)
    - `TelegramSandboxMessage` (frozen dataclass)
    - `TelegramSandboxOutboxConfig` (frozen dataclass)
    - `TelegramSandboxOutbox` (paper-only / file-only writer)
    - `MANDATORY_LABELS` /
      `SIMULATED_HISTORICAL_BLIND_TEST_LABEL` /
      `NO_LIVE_ORDER_LABEL` / `NO_REAL_CAPITAL_LABEL` /
      `NO_TELEGRAM_COMMAND_AUTHORITY_LABEL`
    - `DEFAULT_OUTPUT_JSONL_PATH` /
      `DEFAULT_OUTPUT_MARKDOWN_PATH`
  - `app/sim/__init__.py` — re-exports the above alongside the
    PR94 / PR95 / PR96 / PR97 / PR98 substrate.
  - `tests/unit/test_telegram_sandbox_outbox.py` — 23 PASSING
    tests covering all 21 brief-mandated scenarios plus
    closed-taxonomy enforcement and reset semantics.
  - `docs/PHASE_11C_1D_D_F_TELEGRAM_SANDBOX_OUTBOX.md` — this
    design / acceptance doc.

## 12. Files explicitly NOT touched

  - `app/risk/**`
  - `app/execution/**`
  - `app/exchanges/**`
  - `app/telegram/**` (the existing Phase 10D fake / refusal
    boundary remains untouched; PR99 does NOT reuse the real
    outbound path)
  - `app/config/**`
  - `app/sim/simulation_clock.py` (PR94 — reused verbatim)
  - `app/sim/time_wall_guard.py` (PR94 — reused verbatim)
  - `app/sim/historical_market_store.py` (PR95 — reused verbatim)
  - `app/sim/replay_feed_provider.py` (PR96 — reused verbatim)
  - `app/sim/mock_exchange.py` (PR97 — reused verbatim)
  - `app/sim/pessimistic_fill_model.py` (PR97 — reused verbatim)
  - `app/sim/simulated_capital_flow.py` (PR98 — reused verbatim)
  - `app/sim/trade_ledger.py` (PR98 — reused verbatim)
  - runtime config files
  - `symbol_limit`, anomaly thresholds, `candidate_pool`, regime
    weights

## 13. Test contract

`tests/unit/test_telegram_sandbox_outbox.py` covers, at minimum,
the 21 brief-mandated scenarios:

  1. builds sandbox message with required assertions
  2. rendered message contains all four mandatory labels
  3. `append_message` writes JSONL to a temp file
  4. Markdown transcript generated to a temp file
  5. `evidence_refs` preserved
  6. simulated entry alert remains simulated-only
  7. risk rejection message remains review-only
  8. forced exit message remains simulated-only
  9. equity summary message has no trade authority
  10. AI briefing ready message has no AI trade authority
  11. `telegram_outbound_enabled=False`
  12. `telegram_live_command_authority=False`
  13. `telegram_production_channel_enabled=False`
  14. `phase_12_forbidden=True`
  15. `auto_tuning_allowed=False`
  16. `trade_authority=False`
  17. no token / production-channel-id fields in serialised
      outputs
  18. forbidden fields absent from serialised outputs
  19. module does not import `app.risk` / `app.execution` /
      `app.exchanges` / `app.telegram` / `app.config`
  20. no Telegram Bot API / DeepSeek / LLM / network call path
  21. deterministic output

Plus two defensive extras:

  - closed-taxonomy and phase-name string presence
  - `reset()` clears the in-memory list but does NOT truncate any
    on-disk artefact

All tests run **without network**, with **temp paths**, and never
write to the default `data/reports/telegram_sandbox_*` files.

## 14. Allowed transitions out of Phase 11C.1D-D-F

| From | To | Authorised by |
| --- | --- | --- |
| Phase 11C.1D-D-F IN_REVIEW | Phase 11C.1D-D-F ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-D-F IN_REVIEW | PR100 — Blind Walk-forward Runner v0 | After a successful PR99 acceptance; PR100 itself opens its own gate. |
| Phase 11C.1D-D-F IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** A complete blind walk-forward run requires PR94 → PR100 to have been accepted in order. |
| any | Phase 12 | **FORBIDDEN.** |

A successful PR99 only authorises **PR100 — Blind Walk-forward
Runner v0** to begin its own gate. It does NOT authorise live
trading, auto-tuning, real Telegram outbound, real production /
live Telegram channel, Telegram command authority, or Phase 12.

## 15. Inheritance

Phase 11C.1D-D-F inherits, verbatim, every Phase 1, Phase 11C,
Phase 11C.1A, Phase 11C.1B, Phase 11C.1C-A through Phase
11C.1C-C-B-B-B-E-D, Phase AI-1 through Phase AI-CHECKPOINT, Phase
11C / Offline Rule Sandbox Replay, Phase 11C.1D-B *Paper Shadow
Strategy Validation*, Phase 11C.1D-C *Risk / Execution / Capital
Safety Matrix*, Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
Constitution*, Phase 11C.1D-D-A *SimulationClock + Time-Wall
Guard*, Phase 11C.1D-D-B *Historical Market Store v0*, Phase
11C.1D-D-C *ReplayFeedProvider v0*, Phase 11C.1D-D-D *MockExchange
+ Pessimistic Fill Model v0*, and Phase 11C.1D-D-E *Simulated
Capital Flow + Trade Ledger v0* forbidden item.

The Risk Engine remains the single trade-decision gate.
**Phase 12 remains FORBIDDEN.**
