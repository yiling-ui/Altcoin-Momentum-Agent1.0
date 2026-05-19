# AMA-RT Operator Runbook

> **Status:** Phase 11B - Cloud Paper Trading (Issue #11B).
> Paper mode only. No live trading. No real exchange order. No real
> withdrawal. No real Telegram outbound. No real DeepSeek transport.

This runbook tells an operator how to react when the Phase 11B
cloud loop alerts them. Every command in this file is **paper-mode
only**; the four `ExchangeClientBase` write surfaces (`create_order`,
`cancel_order`, `set_leverage`, `set_margin_mode`) continue to raise
`SafeModeViolation` regardless of any operator action.

## 0. Boot expectations

Before deploying the Phase 11B cloud loop, confirm:

- `app/config/defaults.yaml` resolves to:
  - `mode.trading_mode = paper`
  - `mode.live_trading_enabled = false`
  - `mode.right_tail_enabled = false`
  - `mode.llm_enabled = false`
  - `mode.exchange_live_order_enabled = false`
- `app/config/paper_cloud.yaml` repeats the same hard expectations.
- The deploy environment **does not** export any of the following
  variables to a non-empty value:
  - `AMA_LIVE_TRADING_ENABLED`, `AMA_RIGHT_TAIL_ENABLED`,
    `AMA_LLM_ENABLED`, `AMA_EXCHANGE_LIVE_ORDER_ENABLED`
  - `AMA_EXCHANGE_API_KEY`, `AMA_EXCHANGE_API_SECRET`
  - `AMA_TELEGRAM_BOT_TOKEN`, `AMA_DEEPSEEK_API_KEY`
  - `BINANCE_API_KEY`, `BINANCE_API_SECRET`
  - `TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY`
  - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

The `EnvGuard` re-checks every variable above on every boot and
refuses to start if any is set. The Phase 1 safety lock will coerce
the resolved Settings back to safe values regardless, but the
env-guard surfaces dangerous *intent* in the deploy log.

Run the supervisor:

```bash
python -m scripts.run_paper_cloud --acceptance-dry-run
```

A successful boot prints a structured banner ending with
`go_decision=GO accepted=True`. A failed boot exits non-zero with a
short refusal message.

## 1. `/pause`

**What it does:** flips the Telegram command center's
`new_opens_paused` advisory flag to `True`. The Risk Engine remains
the single trading-decision gate; the flag is a HINT the next caller
may consume to refuse new opens.

**When to send it:**
- Operator wants to drain trading without a hard stop.
- Pre-flight before a manual config change.

**Audit trail:** `TELEGRAM_COMMAND_RECEIVED` + an extra audit row in
`LOUD_AUDIT_COMMANDS` for `/pause`.

**Response:** "pause: new_opens_paused=True. Risk Engine remains the
single trading gate; this flag is advisory."

## 2. `/resume`

**What it does:** clears the `new_opens_paused` advisory flag. The
Risk Engine still owns the final go / no-go on every new open.

**Two-step confirmation:** `/resume` requires the explicit
`confirmed=True` arg. The first call returns
`CommandStatus.NEEDS_CONFIRMATION`; the second call (with
confirmation) clears the pause flag.

**P0 latched-pause caveat:** if a P0 reconciliation mismatch fired
recently, the Reconciler keeps `new_opens_paused=True` until ALL of
the following are met:

1. Every P0 incident is marked resolved
   (`IncidentRepository.resolve_incident` for each one).
2. Protection mode is exited
   (`Reconciler.exit_protection_mode(...)`).
3. The operator has staged
   `Reconciler.confirm_operator_resume(...)`.
4. The next reconciliation pass is clean.

`/resume` alone does NOT clear a P0 latched pause. The operator must
first walk the four steps above.

## 3. `/kill_all`

**What it does:** records the operator's intent and pauses new
opens. **Does NOT call any real exchange surface in Phase 11B.**
The four `ExchangeClientBase` write surfaces continue to refuse.

**Use this when:**
- Operator wants every open paper position closed defensively.

**Note:** the Phase 9 `ExecutionFSMDriver` is the only path that
runs the reduce-only protective close on a session it owns. Phase
11B `/kill_all` writes audit events but does not directly drive
those sessions; the operator should follow the kill_all with a
manual session-by-session inspection if multiple positions exist.

## 4. `/rebase`

**What it does:** records the operator's intent for a Capital Flow
rebase. **Does NOT execute a real withdrawal in Phase 11B.** The
Phase 8 `CapitalFlowEngine` remains the only entry point that
mutates capital.db.

**Two-step confirmation:** required.

## 5. `/export_test_data 24h`

**What it does:** runs the Phase 8.5
`TestDataExportService.export(range_label='24h', type_filter='all')`
and sends the redacted ``.zip`` as a Telegram document attachment +
a SHORT generating-summary caption. The bytes are redacted by the
service before zipping; the dispatcher re-runs the redaction gate on
the caption.

**Use this when:**
- After every cloud boot ("立即运行 /export_test_data 24h").
- Whenever the operator wants a fresh manifest + summary for an
  audit window.

**Other export commands:** `/export_events`, `/export_rejections`,
`/export_capital`, `/export_report`, `/export_learning_dataset` -
each has a fixed canonical default range; only `/export_test_data`
accepts an explicit range arg.

## 6. P0 incident response

Phase 11B detects the following P0 conditions:

- **Ghost position** - local empty + remote position present.
- **Missing remote position** - local has a position + remote empty.
- **Position qty / direction mismatch** between local + remote.
- **Stop mismatch / unattached stop** - local says stop attached,
  remote has no stop on the position.
- **Stop attachment failure** - the Execution FSM driver's
  `on_stop_failed` path opens a P0 incident and runs an automatic
  reduce-only protective close on the paper position.

When a P0 fires:

1. The supervisor latches `new_opens_paused=True`.
2. The Reconciler (via `IncidentRepository.enter_protection_mode`)
   emits `PROTECTION_MODE_ENTERED`.
3. The dispatcher pushes a `CRITICAL` Telegram alert (which bypasses
   throttle and dedupe).
4. The operator inspects:
   - `data/sqlite/incidents.db.incidents` (open incidents).
   - `data/sqlite/events.db` (RECONCILIATION_MISMATCH events).
   - The latest `data/reports/exports/*.zip` for full context.
5. Once the operator has confirmed every position / stop is in a
   known state on the exchange:
   - call `IncidentRepository.resolve_incident(...)` for each P0;
   - call `Reconciler.exit_protection_mode(...)` to clear protection
     mode;
   - call `Reconciler.confirm_operator_resume(...)` to stage the
     resume confirmation;
   - run one more reconciliation pass; the latch clears only when
     this pass is clean AND every step above has been performed.

## 7. Daily report

Generated automatically at the configured cadence by the
`DailyReportBuilder`. Lives under
`data/reports/daily/{YYYY-MM-DD}-paper-report.md`. The report is a
Markdown digest of the previous window: event count, candidate
opportunity count, risk approvals / rejections, paper trades,
incident counts, protection mode entries, Telegram message counts,
data-export counts, top reject reasons, top symbols, error /
degraded notes.

Use the daily report to:

- Spot a regression (e.g. a sudden uptick in `STOP_UNCONFIRMED`
  rejections).
- Confirm the last 24-hour window had zero P0 incidents.
- Validate that the export scheduler is firing on cadence.

## 8. Stopping the cloud loop

The Phase 11B supervisor is a one-shot acceptance dry-run; long-
running cadences land in a future PR behind Spec §41 Go/No-Go. To
stop a long-running deploy:

1. Send `/pause` to drain new opens.
2. Wait for any in-flight paper trade to close
   (the Phase 9 driver always sees a final
   `POSITION_CLOSED` event).
3. Send `SIGTERM` to the supervisor process.

The supervisor's `_teardown` closes every database cleanly and
emits a `DATA_UNRELIABLE` row on the way out so a future replay
sees the lifecycle end.
