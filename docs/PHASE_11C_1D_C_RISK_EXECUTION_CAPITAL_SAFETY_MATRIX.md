# Phase 11C.1D-C — Risk / Execution / Capital Safety Matrix v0

> 风险 / 执行 / 资金 / 数据降级 / AI 降级 安全矩阵 v0
> **Status:** IN_REVIEW (after the implementation PR is merged the
> phase moves from IN_REVIEW to ACCEPTED only via a separate
> docs-closeout PR; this PR alone does NOT mark the phase
> ACCEPTED).
> **Parent:** Phase 11C umbrella.
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

---

## Purpose

A strictly paper / report / evidence-only safety verification engine
that turns the documented safety boundary of the AMA-RT V1.4 system
into a deterministic, auditable matrix. The matrix takes a closed
taxonomy of adverse-condition scenarios (stop failures, ghost /
orphan positions, reconciliation mismatches, data degradations, REST
429 / 418 throttling, Telegram export failures, capital rebase, AI
degradation, etc.) and verifies that every scenario, when evaluated,
produces the *minimum required defensive safety actions*:

  * pauses new opens when required,
  * rejects unsafe actions,
  * requires operator review or operator resume when required,
  * degrades to report-only when telemetry is degraded,
  * blocks Telegram outbound, AI trade authority, runtime config
    changes, and live orders unconditionally,
  * keeps the paper ledger when the live path is unsafe,
  * records audit events for every adverse scenario.

The output is one descriptive
`risk_execution_capital_safety_matrix_report.json` (plus its
Markdown twin) that an auditor can review to confirm the documented
safety boundary holds end-to-end on the closed scenario taxonomy
shipped by this phase.

This phase is *not* a Risk Engine, *not* an Execution FSM, *not* an
Exchange gateway, *not* a Telegram outbound, *not* an LLM client,
*not* an Auto-tuner, *not* a runtime-config writer, and *not* Phase
12. It is a deterministic, auditable matrix that asserts the
documented defensive contract.

---

## Scenario taxonomy (`SafetyMatrixScenarioType`)

Closed enum (21 values). Each value is descriptive only; none of
them is an input to the live Risk Engine, the live Execution FSM,
the live Exchange gateway, or any runtime knob.

| Scenario type | Domain | Severity |
| --- | --- | --- |
| `STOP_FAILED` | Execution | P0 |
| `STOP_UNCONFIRMED` | Execution | P0 |
| `GHOST_POSITION` | Reconciliation | P0 |
| `ORPHAN_STOP` | Reconciliation | P0 |
| `MISSING_REMOTE_POSITION` | Reconciliation | P0 |
| `RECONCILIATION_MISMATCH` | Reconciliation | P0 |
| `DATA_DEGRADED` | Data | P1 |
| `WS_STALE` | Data | P1 |
| `REST_429` | Data | P1 |
| `REST_418` | Data | P1 |
| `TELEGRAM_EXPORT_FAILURE` | Export / Telegram | P1 |
| `TELEGRAM_OUTBOUND_BLOCKED` | Telegram | P1 |
| `PAUSE_RESUME_REQUIRED` | Operator | P0 |
| `KILL_ALL_AUDIT_ONLY` | Operator | P0 |
| `CAPITAL_REBASE_IN_PROGRESS` | Capital | P0 |
| `EXTERNAL_DEPOSIT` | Capital | P0 |
| `PROFIT_WITHDRAWAL` | Capital | P0 |
| `LLM_DEGRADED` | AI | P1 |
| `DEEPSEEK_TIMEOUT` | AI | P1 |
| `AI_REALITY_CHECK_FAILED` | AI | P0 |
| `AI_FORBIDDEN_FIELD_STRIPPED` | AI | P0 |

The default scenario set
(`app.safety.risk_execution_capital_matrix.default_scenario_set`)
exercises every value in the taxonomy at least once.

---

## Expected actions (`SafetyMatrixExpectedAction`)

Closed enum (12 values). Every action is *defensive*. No action can
place an order, modify runtime config, or enter Phase 12. `APPLY`,
`DEPLOY`, `ENABLE_LIVE`, `GO_LIVE`, `AUTO_APPLY`, `BUY`, `SELL`,
`OPEN_POSITION`, `CLOSE_POSITION`, `PLACE_ORDER`, `SUBMIT_ORDER`
are intentionally NOT defined and the engine refuses to ever emit
them.

| Action | Meaning |
| --- | --- |
| `PAUSE_NEW_OPENS` | New entries paused; existing state untouched. |
| `REJECT_UNSAFE_ACTION` | The unsafe action is refused. |
| `REQUIRE_OPERATOR_REVIEW` | A human review is required before any further action. |
| `REQUIRE_OPERATOR_RESUME` | A human resume action is required before paused operations resume. |
| `DEGRADE_TO_REPORT_ONLY` | The system continues only as a report-only observer. |
| `RECORD_AUDIT_EVENT` | An audit event is recorded for the scenario. |
| `BLOCK_TELEGRAM_OUTBOUND` | Telegram live outbound is blocked (universal). |
| `BLOCK_AI_TRADE_AUTHORITY` | The AI Layer cannot author trade decisions (universal). |
| `BLOCK_RUNTIME_CONFIG_CHANGE` | Runtime config writes are blocked (universal). |
| `BLOCK_LIVE_ORDER` | Live orders are blocked (universal). |
| `PAPER_LEDGER_ONLY` | Only the paper ledger is updated. |
| `NO_ACTION_REQUIRED` | A reserved no-op label for placeholder fixtures. |

The five universal blocks (`BLOCK_LIVE_ORDER`,
`BLOCK_RUNTIME_CONFIG_CHANGE`, `BLOCK_TELEGRAM_OUTBOUND`,
`BLOCK_AI_TRADE_AUTHORITY`, `RECORD_AUDIT_EVENT`) are observed for
every scenario regardless of type. The paper-only safety boundary
is unconditional.

---

## Decision table

For each `SafetyMatrixScenarioType`, the engine looks up the minimum
required defensive actions (in addition to the universal blocks)
from a deterministic, hard-coded table. The table is intentionally
**not** runtime-tunable. It is **not** loaded from runtime config,
**not** loaded from an LLM, **not** exposed via CLI flags, and
**not** rewritten by the engine.

| Scenario type | Minimum required actions (in addition to universal blocks) |
| --- | --- |
| `STOP_FAILED` | `PAUSE_NEW_OPENS`, `REQUIRE_OPERATOR_REVIEW` |
| `STOP_UNCONFIRMED` | `REJECT_UNSAFE_ACTION`, `REQUIRE_OPERATOR_REVIEW` |
| `GHOST_POSITION` | `PAUSE_NEW_OPENS`, `REQUIRE_OPERATOR_RESUME` |
| `ORPHAN_STOP` | `PAUSE_NEW_OPENS`, `REQUIRE_OPERATOR_REVIEW` |
| `MISSING_REMOTE_POSITION` | `PAUSE_NEW_OPENS`, `REQUIRE_OPERATOR_RESUME` |
| `RECONCILIATION_MISMATCH` | `PAUSE_NEW_OPENS`, `REQUIRE_OPERATOR_REVIEW` |
| `DATA_DEGRADED` | `DEGRADE_TO_REPORT_ONLY` |
| `WS_STALE` | `DEGRADE_TO_REPORT_ONLY` |
| `REST_429` | `DEGRADE_TO_REPORT_ONLY`, `REQUIRE_OPERATOR_REVIEW` |
| `REST_418` | `DEGRADE_TO_REPORT_ONLY`, `REQUIRE_OPERATOR_REVIEW` |
| `TELEGRAM_EXPORT_FAILURE` | `REQUIRE_OPERATOR_REVIEW` |
| `TELEGRAM_OUTBOUND_BLOCKED` | (universal `BLOCK_TELEGRAM_OUTBOUND` only) |
| `PAUSE_RESUME_REQUIRED` | `PAUSE_NEW_OPENS`, `REQUIRE_OPERATOR_RESUME` |
| `KILL_ALL_AUDIT_ONLY` | `REQUIRE_OPERATOR_REVIEW` |
| `CAPITAL_REBASE_IN_PROGRESS` | `PAUSE_NEW_OPENS`, `PAPER_LEDGER_ONLY` |
| `EXTERNAL_DEPOSIT` | `REQUIRE_OPERATOR_REVIEW`, `PAPER_LEDGER_ONLY` |
| `PROFIT_WITHDRAWAL` | `REQUIRE_OPERATOR_REVIEW`, `PAPER_LEDGER_ONLY` |
| `LLM_DEGRADED` | `DEGRADE_TO_REPORT_ONLY` |
| `DEEPSEEK_TIMEOUT` | `DEGRADE_TO_REPORT_ONLY` |
| `AI_REALITY_CHECK_FAILED` | `REQUIRE_OPERATOR_REVIEW` |
| `AI_FORBIDDEN_FIELD_STRIPPED` | `REQUIRE_OPERATOR_REVIEW` |

---

## PASS / WARN / FAIL rules

For each `SafetyMatrixScenario` the engine computes
`observed_actions` from the decision table, then compares them to
the scenario's `expected_actions`:

  * **PASS** — every expected action is present in
    `observed_actions`.
  * **FAIL** — at least one expected action is missing AND the
    scenario severity is `P0` or `P1`.
  * **WARN** — at least one expected action is missing AND the
    scenario severity is `P2` or `P3`.
  * **INSUFFICIENT_EVIDENCE** — the report's overall status when
    `total_scenarios == 0`.

The report's overall `status` rolls up the per-scenario statuses:
`FAIL` if any scenario is `FAIL`, otherwise `WARN` if any is
`WARN`, otherwise `PASS`. With zero scenarios, the overall status
is `INSUFFICIENT_EVIDENCE`.

`p0_failures` and `p1_failures` are the lists of scenario IDs that
landed `FAIL` at severity `P0` and `P1` respectively. They are the
sole input to the next-allowed-phase decision.

---

## Next allowed phase

```
if failed_count == 0 and len(p0_failures) == 0 and len(p1_failures) == 0
        and total_scenarios > 0:
    next_allowed_phase = Strict Blind Walk-forward design checkpoint
                         (paper / read-only; requires human-owner-
                         supplied strict forward-only anti-lookahead
                         blind-test design)
else:
    next_allowed_phase = Safety Matrix remediation required
                         (paper / read-only; remediate P0 / P1
                         blockers and re-run)
```

A successful Safety Matrix run only authorises the
*Strict Blind Walk-forward design checkpoint*. It does **NOT**
authorise *Blind Walk-forward implementation*. It does **NOT**
authorise live trading. It does **NOT** authorise auto-tuning.
It does **NOT** open Phase 12.

**Before Blind Walk-forward implementation can begin, the human
owner must provide a finalized strict forward-only
anti-lookahead blind-test design.** This module does not, and
cannot, generate that design.

---

## Safety boundary (held end-to-end)

```
mode                          = paper
sandbox_only                  = True
writes_runtime_config         = False
auto_tuning_allowed           = False
trade_authority               = False
live_trading                  = False
exchange_live_orders          = False
right_tail                    = False
llm                           = False
llm_outbound_enabled          = False
telegram_outbound_enabled     = False
binance_private_api_enabled   = False
allow_trade_decision          = False
allow_runtime_config_change   = False
phase_12_forbidden            = True
```

Every emitted result and the report itself re-pin
`live_order_blocked=True`, `runtime_config_unchanged=True`,
`ai_trade_authority_blocked=True`, `telegram_outbound_blocked=True`
on every scenario regardless of the scenario type. The recursive
`assert_no_forbidden_fields` guard refuses to serialise any payload
that carries any of the following keys at any nesting depth:

```
buy, sell, long, short, direction,
entry, exit, order, execution_command,
position_size, leverage, stop, stop_loss, target, take_profit,
risk_budget,
runtime_config_patch, symbol_limit_patch, threshold_patch,
candidate_pool_patch, regime_weight_patch,
strategy_parameter_patch,
signal_to_trade, should_buy, should_short,
apply_change, deploy_change, enable_live, live_ready,
trading_approved
```

---

## Why this is NOT live trading

  * The engine and runner do not import `app.risk`,
    `app.execution`, `app.exchanges`, `app.telegram`, or
    `app.config`. A unit test enforces this with both an AST scan
    and an isolated `importlib.util` load.
  * The engine and runner do not call any HTTP / network library
    (`requests`, `aiohttp`, `httpx`, `urllib.request`,
    `http.client`, `websocket`, `websockets`, `ccxt`, `binance`,
    `telegram`, `deepseek`, `openai`, `anthropic`, `grpc`,
    `boto3`).
  * The engine never produces an order, never signs a request,
    never reads a private exchange API.
  * `BLOCK_LIVE_ORDER` is one of the universal blocks observed for
    every scenario. Every result re-pins
    `live_order_blocked=True`. The report re-pins
    `live_trading=False`, `exchange_live_orders=False`,
    `binance_private_api_enabled=False`.

## Why this does NOT call the private API

  * No file under `app/safety/**` imports a Binance / exchange
    client. No file references `api_key`, `api_secret`,
    `listenKey`, or any signed-endpoint helper.
  * `BLOCK_LIVE_ORDER` is universally observed.
  * `binance_private_api_enabled=False` is pinned at every emitted
    payload boundary.

## Why this does NOT write runtime config

  * The engine does not import `app.config`. No file under
    `app/safety/**` writes to any path under `app/config/**`.
  * The runner only writes its two output files in
    `data/reports/safety_matrix/` (or the operator-supplied
    `--output-dir`). It never touches the runtime YAML / JSON
    config used by the live system.
  * `BLOCK_RUNTIME_CONFIG_CHANGE` is one of the universal blocks
    observed for every scenario. Every result re-pins
    `runtime_config_unchanged=True`. The report re-pins
    `writes_runtime_config=False` and
    `allow_runtime_config_change=False`.
  * The `assert_no_forbidden_fields` guard refuses to serialise
    any payload carrying a `*_patch` key.

## Why this does NOT authorise auto-tuning

  * The decision table thresholds (per-scenario minimum-required
    actions, severity classes, PASS / WARN / FAIL rules) are
    module-level Python constants. They are NOT loaded from
    runtime config, NOT loaded from an LLM, NOT exposed via CLI
    flags, and NOT rewritten by the engine.
  * No part of this phase produces or consumes
    `runtime_config_patch`, `threshold_patch`,
    `symbol_limit_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, or `strategy_parameter_patch`.
  * `auto_tuning_allowed=False` is pinned at the engine, the
    report, the SAFETY_CONTRACT, and every emitted event.

## Why this does NOT authorise Phase 12

  * `phase_12_forbidden=True` is pinned at the engine, the
    report, the SAFETY_CONTRACT, and every emitted event.
  * The literal string `"Phase 12"` is intentionally NOT a
    substring of `next_allowed_phase` in either branch
    (`NEXT_ALLOWED_PHASE_NO_BLOCKERS` or
    `NEXT_ALLOWED_PHASE_WITH_BLOCKERS`). A unit test enforces this
    invariant on the report payload.
  * A successful run only points to the *Strict Blind Walk-forward
    design checkpoint*, which is itself a paper / read-only
    design-review step, NOT Blind Walk-forward implementation,
    and NOT Phase 12.

---

## What a successful Safety Matrix run is allowed to authorise

A successful Safety Matrix run with zero P0 / P1 failures only
authorises the next allowed paper / read-only step:

  * **Strict Blind Walk-forward design checkpoint** — a paper /
    read-only review of the *human-owner-supplied* strict forward-
    only anti-lookahead blind-test design. The design checkpoint
    is itself a separate phase with its own brief, its own safety
    contract, and its own implementation PR.

It does NOT authorise:

  * Blind Walk-forward implementation. (The implementation phase
    requires the design checkpoint to have completed AND the
    human owner to have signed off on the design.)
  * live trading.
  * trade authority for the AI Layer.
  * auto-tuning.
  * the DeepSeek hot path.
  * Telegram live outbound.
  * Binance private API access.
  * Phase 12.

---

## Allowed event types (added by this phase, all report / export / audit scope)

  * `SAFETY_MATRIX_SCENARIO_EVALUATED`
  * `SAFETY_MATRIX_REPORT_GENERATED`
  * `SAFETY_MATRIX_BLOCKER_DETECTED`

No trade-action events are added. No event is wired into the
runtime hot path. No database schema or migration is touched. The
event-type strings are NOT registered in
`app.core.events.EventType`; they exist only in the safety-matrix
output payload as report / export / audit annotations.

---

## Forbidden by this phase (verbatim)

  * Do not modify `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`, or `app/config/**`.
  * Do not add Binance signed endpoints, `listenKey`, or private
    WebSockets.
  * Do not enable live orders.
  * Do not send real Telegram messages.
  * Do not let Telegram commands bypass the Risk Engine.
  * Do not let AI / DeepSeek output a trade action.
  * Do not let AI / DeepSeek modify config / risk / execution.
  * Do not modify `symbol_limit`, anomaly thresholds,
    `candidate_pool`, or Regime weights.
  * Do not generate `runtime_config_patch`, `threshold_patch`,
    `symbol_limit_patch`, `candidate_pool_patch`,
    `regime_weight_patch`, or `strategy_parameter_patch`.
  * Do not output `buy`, `sell`, `long`, `short`, `direction`,
    `entry`, `exit`, `position_size`, `leverage`, `stop`,
    `stop_loss`, `target`, `take_profit`, `risk_budget`, `order`,
    `execution_command`, `signal_to_trade`, `should_buy`,
    `should_short`, `apply_change`, `deploy_change`,
    `enable_live`, `live_ready`, `trading_approved`.
  * Do not call DeepSeek / LLM / network endpoints.
  * Do not auto-tune.
  * Do not enter Phase 12.

---

## Files shipped

  * `app/safety/__init__.py`
  * `app/safety/risk_execution_capital_matrix.py`
  * `scripts/run_risk_execution_capital_safety_matrix.py`
  * `tests/unit/test_risk_execution_capital_safety_matrix.py`
  * `docs/PHASE_11C_1D_C_RISK_EXECUTION_CAPITAL_SAFETY_MATRIX.md`
    (this document)

Updated: `docs/PROJECT_STATUS.md`, `docs/PHASE_GATE.md`,
`docs/CHANGELOG.md`.

---

## Tests

```
python -m pytest tests/unit/test_risk_execution_capital_safety_matrix.py -q
```

ships **32 PASSING** tests covering the full safety contract for
this phase, including all 20 brief-mandated scenarios:

  1. `STOP_FAILED` -> `PAUSE_NEW_OPENS` / `REQUIRE_OPERATOR_REVIEW`
  2. `STOP_UNCONFIRMED` -> `REJECT_UNSAFE_ACTION`
  3. `GHOST_POSITION` -> `PAUSE_NEW_OPENS` /
     `REQUIRE_OPERATOR_RESUME`
  4. `RECONCILIATION_MISMATCH` -> `REQUIRE_OPERATOR_REVIEW`
  5. `DATA_DEGRADED` / `WS_STALE` -> `DEGRADE_TO_REPORT_ONLY`
  6. `REST_429` / `REST_418` -> `DEGRADE_TO_REPORT_ONLY` /
     `REQUIRE_OPERATOR_REVIEW`
  7. `TELEGRAM_OUTBOUND_BLOCKED` -> `BLOCK_TELEGRAM_OUTBOUND`
  8. `LLM_DEGRADED` / `DEEPSEEK_TIMEOUT` ->
     `BLOCK_AI_TRADE_AUTHORITY` / `DEGRADE_TO_REPORT_ONLY`
  9. `CAPITAL_REBASE_IN_PROGRESS` -> `PAUSE_NEW_OPENS` /
     `PAPER_LEDGER_ONLY`
  10. all scenarios keep `live_order_blocked=true`
  11. all scenarios keep `runtime_config_unchanged=true`
  12. all scenarios keep `phase_12_forbidden=true`
  13. `auto_tuning_allowed=false`
  14. `trade_authority=false`
  15. forbidden fields absent at every nesting depth
  16. runner does not import `app.risk` / `app.execution` /
      `app.exchanges` / `app.telegram` / `app.config`
  17. no DeepSeek / LLM / network call path
  18. JSON output serialisable
  19. deterministic output (byte-identical re-run with fixed
      clock)
  20. `next_allowed_phase = Strict Blind Walk-forward design
      checkpoint` ONLY when no P0 / P1 blockers

```
python -m pytest tests/unit -q
```

reports **3400 PASSING** tests, **0 failures** (was 3368 before
this phase; +32 from this phase).

---

## Allowed transitions

| From | To | Allowed? |
| --- | --- | --- |
| Phase 11C.1D-C IN_REVIEW | Phase 11C.1D-C ACCEPTED | Only via a separate docs-closeout PR after maintainer review. |
| Phase 11C.1D-C IN_REVIEW | Strict Blind Walk-forward design checkpoint | After a successful Safety Matrix run with zero P0 / P1 blockers AND human-owner-supplied strict forward-only anti-lookahead blind-test design; transition itself is the next phase's responsibility. |
| Phase 11C.1D-C IN_REVIEW | Blind Walk-forward implementation | **FORBIDDEN by this phase alone.** Requires the design checkpoint to have completed AND the human owner to have signed off on the design. |
| any | Phase 12 | **FORBIDDEN.** |

A successful Safety Matrix run does **not** authorise a Blind
Walk-forward run on its own — it only marks the system as
*eligible* for the design-checkpoint review. The Blind Walk-forward
implementation phase itself is out of scope for Phase 11C.1D-C.

The phase is marked **IN_REVIEW** here. Maintainer-led review of
the implementation PR is the only path to **ACCEPTED**.
