# Phase 11C.1D-D-A — SimulationClock + Time-Wall Guard (PR94)

> *Strict forward-only historical sim-live time substrate*
> *严格前向 Sim-Live 模拟时钟与时间墙守卫 v0*
>
> **Status:** IN_REVIEW (after this implementation PR; not
> `ACCEPTED` until maintainer review).
> **Type:** **Implementation PR** (paper / report / evidence-only
> infrastructure).
> **Parent:** Phase 11C.1D-D *Strict Blind Walk-forward Sim-Live
> Constitution* (PR93, merged).
> **Trade authority:** **none.**
> **Phase 12:** **FORBIDDEN.**

---

## 0. Pre-amble — what this PR is and is NOT

This PR ships the **first** anti-future-lookahead infrastructure
block of the strict blind walk-forward stack defined by Phase
11C.1D-D (PR93). It is a small, deterministic, pure-Python time
substrate. It introduces **no** runtime hot-path wiring, **no**
new event types, **no** schema migration, **no** I/O, **no**
network, and **no** authority over the Risk Engine or the
Execution FSM.

This PR IS:

  - a `SimulationClock` (strict forward-only simulated UTC clock),
  - a `HistoricalRecordTime` four-timestamp helper
    (`event_time` / `available_at` / `ingested_at` / `source`),
  - a `TimeWallGuard` (the `available_at <= simulated_time`
    enforcement layer with `NoLookaheadViolation` audit objects),
  - a `CandleVisibilityGuard` (the closed-candle visibility rule,
    final OHLCV invisible before close),
  - a recursive `assert_no_forbidden_fields` guard against
    trade-action / runtime-config-patch / "live ready" fields,
  - the matching unit-test module
    `tests/unit/test_simulation_clock_time_wall_guard.py`.

This PR is **NOT**:

  - a Blind Walk-forward Runner (PR100's responsibility),
  - a Historical Market Store (PR95's responsibility),
  - a ReplayFeedProvider (PR96's responsibility),
  - a MockExchange + Pessimistic Fill Model (PR97's responsibility),
  - a Simulated Capital Flow + Trade Ledger (PR98's responsibility),
  - a Telegram Sandbox Outbox (PR99's responsibility),
  - an authorisation to enter Phase 12,
  - an authorisation to enable live orders,
  - an authorisation to connect to Binance private API,
  - an authorisation to grant AI trade authority,
  - an authorisation to grant Telegram command authority,
  - an authorisation to auto-tune any rule, threshold, or parameter.

PR94 acceptance authorises the next allowed paper-only step
(**PR95 — Historical Market Store v0**). It does NOT authorise
the rest of the engineering route; each of PR95 → PR100 must
pass its own gate.

---

## 1. Purpose

Strict blind walk-forward (PR93 §1) is **not** an ordinary
backtest. At simulated time `T`, the system MAY only access
records whose `available_at <= T`. To make that rule machine-
enforceable, every later module that touches simulation-sensitive
state must consume a single, deterministic, forward-only clock
and a single, deterministic, audit-rich time wall.

PR94 supplies exactly that. Nothing more, nothing less.

The objective is **truthful, deterministic, reproducible time
discipline**, not pretty equity curves. Pretty curves produced
by even one form of leakage are not evidence; they are
falsifications. PR94 makes the leakage path syntactically
impossible for the modules that consume it.

---

## 2. Relation to PR93 constitution

PR93 (the *Strict Blind Walk-forward Sim-Live Constitution*) is
docs-only. PR94 is the **first implementation slice** authorised
by PR93 §19's engineering route. PR94 implements only the
substrate required by:

  - **§5 Time-Wall Constitution.** Every historical record MUST
    distinguish four timestamps. At simulated time `T`, the
    system MAY only read records whose `available_at <= T`. Any
    read of `available_at > T` MUST be rejected and logged as
    `NO_LOOKAHEAD_VIOLATION`. `ingested_at` is not a substitute
    for `available_at`.
  - **§6 Candle visibility rule.** A 1m / 5m / longer-period
    candle's final OHLCV is fully visible only after that
    candle has closed. Without tick / trade data, intra-bar
    paths are ambiguous and cannot be inferred.
  - **§7 Outcome-label isolation.** Outcome labels (future
    top-mover labels, completed tail labels, post-discovery
    outcome metrics, future MFE / MAE, severe missed-tail
    labels, final window PnL, future drawdown, future funding-
    rate changes, future regime labels, future AI briefings,
    future replay summaries, future reflection summaries) MAY
    ONLY be used after the blind window has closed.

PR94 ships the *enforcement primitives*; PR95..PR100 will wire
them into the production data path. PR94 is a strict subset of
the constitution's scope.

---

## 3. SimulationClock contract

`app.sim.SimulationClock` is the **only** source of market-state
decision time inside a strict blind walk-forward run.

  - `start_time_utc` is timezone-aware UTC. Naive datetimes are
    rejected. Non-UTC offsets are normalised to UTC.
  - `current_time_utc` is timezone-aware UTC.
  - `end_time_utc` is optional and timezone-aware UTC; when
    set, `step` / `set_time` cannot exceed it.
  - `monotonic_forward_only=True` is the default. The clock
    cannot move backward. Rewinds require an explicit test-only
    flag (`monotonic_forward_only=False`).
  - `step(delta)` accepts a `timedelta`, a number of seconds, or
    an interval string (`"1m"`, `"5m"`, `"1h"`, …).
  - `set_time(new_time)` sets the simulated time explicitly,
    forward-only by default, and refuses to precede
    `start_time_utc`.
  - `now()` returns `current_time_utc`. It is the **only**
    callable that downstream consumers may use as decision time.
  - `assert_within_bounds()` raises if `current_time_utc` has
    drifted outside `[start_time_utc, end_time_utc]`.

The clock NEVER consults the real wall-clock. Modules that
consume it MUST NOT call `datetime.now()` / `datetime.utcnow()` /
`time.time()` / `time.monotonic()` / `pandas.Timestamp.now()` as
a substitute for market-state decision time. The wall-clock may
still be used for **non-decision** diagnostic metadata (file
write timestamps, log rotation), but those values may not feed
back into any market or trade decision.

The clock is therefore **deterministic** and **reproducible**
under identical inputs.

---

## 4. event_time vs available_at vs ingested_at

`app.sim.HistoricalRecordTime` carries the four timestamps the
constitution mandates:

| field | meaning |
| --- | --- |
| `event_time` | when the underlying market event actually occurred |
| `available_at` | the earliest time at which a sim-live consumer could legitimately have observed the record (e.g. candle close time + exchange publication latency) |
| `ingested_at` | when the record entered the historical store |
| `source` | which provider / endpoint produced the record |

Constructor invariants:

  - `event_time`, `available_at`, and `ingested_at` (when set)
    are timezone-aware UTC. Naive datetimes are rejected.
  - `available_at >= event_time`. A record cannot be available
    before its event happened.
  - If `interval` is supplied, it must be one of the closed
    interval taxonomy (`"1m"`, `"3m"`, `"5m"`, `"15m"`, `"30m"`,
    `"1h"`, `"2h"`, `"4h"`, `"6h"`, `"8h"`, `"12h"`, `"1d"`).

`HistoricalRecordTime.to_dict()` always carries
`phase_12_forbidden=True`, `auto_tuning_allowed=False`,
`trade_authority=False`, `is_trade=False`,
`is_runtime_patch=False`. The dict is JSON-serialisable.

---

## 5. available_at <= simulated_time rule

`app.sim.TimeWallGuard` enforces the §5 time-wall.

  - `can_read(record, simulated_time) -> bool`. True iff the
    record's `available_at` is present AND
    `available_at <= simulated_time`.
  - `assert_can_read(record, simulated_time)`. Raises
    `ValueError` with a `NO_LOOKAHEAD_VIOLATION` marker on
    rejection.
  - `validate_no_lookahead(record, simulated_time) -> Optional[NoLookaheadViolation]`.
    Returns a violation object when the record cannot be read.
  - `filter_available(records, simulated_time) -> (allowed, violations)`.
    Splits the input into the readable subset and the violation
    list. Records are NEVER silently dropped; every rejected
    record produces an auditable `NoLookaheadViolation`.
  - `reject_future_records(records, simulated_time) -> List[NoLookaheadViolation]`.
    Thin wrapper over `filter_available`.

The guard accepts both `HistoricalRecordTime` instances and
`Mapping`-shaped records that carry `event_time` /
`available_at` / `ingested_at` / `record_id` / `symbol` /
`source` keys.

`ingested_at` is **never** used as availability. A record whose
`ingested_at <= T` but whose `available_at > T` is still future
data and is rejected with reason `FUTURE_AVAILABLE_AT`. The
dedicated `make_ingested_at_used_as_availability_violation`
helper exists for downstream auditors to record the substitution
explicitly when they detect it.

A missing `available_at` produces a `MISSING_AVAILABLE_AT`
violation. We cannot prove a record was visible at `T` without
its `available_at`, so the safe default is to reject.

---

## 6. Closed-candle visibility rule

`app.sim.CandleVisibilityGuard` enforces the §6 candle
visibility rule.

  - `candle_close_time(open_time, interval)` returns
    `open_time + interval_seconds`.
  - `is_candle_closed(open_time, interval, simulated_time)`
    returns `True` iff `simulated_time >= candle_close_time`.
    A simulated-time tick exactly at the close instant counts
    as closed.
  - `assert_candle_fields_visible(candle, simulated_time)`
    raises `ValueError` with marker `UNCLOSED_CANDLE_FIELD_ACCESS`
    if any final OHLCV field (`high` / `low` / `close` /
    `volume`) is read before the candle has closed.
  - `visible_candle_fields(candle, simulated_time)` returns a
    copy of the candle with final OHLCV stripped if the candle
    is unclosed; only `open_time` / `open` / `interval` /
    `symbol` / `is_partial` / `source` / `available_at` /
    `event_time` may be read on an open candle, and only as
    explicitly partial metadata.

If the historical store has no tick / trade data for an
interval, the intra-bar path between `open` / `high` / `low` /
`close` is ambiguous and the consumer MUST either model
conservatively (worst-case) or mark the trace
`AMBIGUOUS_INTRABAR_PATH` and propagate that marker. PR94 does
not pick a fill model; PR97 does. PR94 only refuses to leak
unclosed candle fields.

---

## 7. No-lookahead violation handling

`app.sim.NoLookaheadViolation` is the audit substrate.
Violations are descriptive only. They never carry direction,
sizing, leverage, stops, targets, or risk-budget fields. They
never authorise live trading, auto-tuning, or Phase 12.

Closed reason taxonomy (PR94):

  - `FUTURE_AVAILABLE_AT` — `available_at > simulated_time`.
  - `MISSING_AVAILABLE_AT` — record carries no `available_at`.
  - `INGESTED_AT_USED_AS_AVAILABILITY` — caller substituted
    `ingested_at` for `available_at` (still future data).
  - `UNCLOSED_CANDLE_FIELD_ACCESS` — final OHLCV read before
    candle close.
  - `OUTCOME_LABEL_DURING_BLIND_WINDOW` — outcome label read
    inside the blind window (Constitution §7).

Closed severity taxonomy: `P0`, `P1`. PR94 defaults to `P0` for
every violation; later PRs may classify some lower-impact
violations as `P1`.

Each violation carries:

  - `violation_id` (deterministic, monotonic, per-guard),
  - `reason`, `severity`,
  - `simulated_time`, `event_time`, `available_at`,
  - `record_id`, `symbol`, `source`, `detail`,
  - hard-pinned `phase_12_forbidden=True`,
    `auto_tuning_allowed=False`, `trade_authority=False`,
  - defensive markers `is_no_lookahead_violation=True`,
    `is_trade=False`, `is_runtime_patch=False`.

`NoLookaheadViolation.to_dict()` is JSON-serialisable and runs
through the recursive `assert_no_forbidden_fields` guard before
returning.

---

## 8. Forbidden future labels / outcome usage

The §7 closed list of outcome labels MUST NOT enter any decision
surface inside the blind window:

  - future top-mover labels,
  - completed tail labels,
  - post-discovery outcome metrics,
  - future MFE / MAE / peak / trough,
  - severe missed-tail labels,
  - final window PnL,
  - future drawdown,
  - future funding-rate changes,
  - future regime labels,
  - future AI briefings,
  - future replay summaries,
  - future reflection summaries.

`TimeWallGuard.make_outcome_label_violation(...)` constructs a
`NoLookaheadViolation` with reason
`OUTCOME_LABEL_DURING_BLIND_WINDOW` for downstream auditors to
record the read attempt. PR94 does not yet wire this helper into
the production hot path; downstream PR95..PR100 will.

---

## 9. Forbidden field guard

PR94 outputs MUST NOT carry any of the following field names at
any nesting depth:

`buy`, `sell`, `long`, `short`, `direction`,
`entry`, `exit`, `position_size`, `leverage`,
`stop`, `stop_loss`, `target`, `take_profit`, `risk_budget`,
`order`, `execution_command`,
`runtime_config_patch`, `symbol_limit_patch`, `threshold_patch`,
`candidate_pool_patch`, `regime_weight_patch`,
`strategy_parameter_patch`,
`signal_to_trade`, `should_buy`, `should_short`,
`apply_change`, `deploy_change`, `enable_live`, `live_ready`,
`trading_approved`.

`assert_no_forbidden_fields(payload)` walks any nested
`Mapping` / `list` / `tuple` and raises `ValueError` on the first
violation. Every PR94 `to_dict()` result runs through this guard
defensively.

---

## 10. Hard safety boundary

| flag | required value |
| --- | --- |
| `mode` | `paper` |
| `sandbox_only` | `True` |
| `live_trading` | `False` |
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
| `ai_trade_authority` | `False` |
| `trade_authority` | `False` |
| `auto_tuning_allowed` | `False` |
| `phase_12_forbidden` | **`True`** |

The Risk Engine remains the single trade-decision gate.

---

## 11. Forbidden by this PR

  - Do not modify `app/risk/**`, `app/execution/**`,
    `app/exchanges/**`, `app/telegram/**`, `app/config/**`.
  - Do not implement a Blind Walk-forward Runner (PR100).
  - Do not implement a Historical Market Store (PR95).
  - Do not implement a ReplayFeedProvider (PR96).
  - Do not implement a MockExchange + Pessimistic Fill Model
    (PR97).
  - Do not implement a Simulated Capital Flow + Trade Ledger
    (PR98).
  - Do not implement a Telegram Sandbox Outbox (PR99).
  - Do not enable live orders.
  - Do not connect to Binance private API.
  - Do not enable any real Telegram outbound.
  - Do not call DeepSeek / LLM / any network transport.
  - Do not grant AI / DeepSeek any trade authority.
  - Do not auto-tune anything.
  - Do not enter Phase 12.

The unit tests assert these constraints by AST-walking the new
modules and the `app.sim` package init, plus by import-time
inspection of `sys.modules`.

---

## 12. Non-goals

PR94 does NOT, and CANNOT:

  - implement the Blind Walk-forward Runner,
  - implement the Historical Market Store,
  - implement the ReplayFeedProvider,
  - implement the MockExchange,
  - implement the Pessimistic Fill Model,
  - implement Simulated Capital Flow,
  - implement the Telegram Sandbox Outbox,
  - authorise live trading,
  - authorise auto-tuning,
  - authorise Phase 12.

A successful PR94 merge **only** authorises **PR95 — Historical
Market Store v0** to begin its own gate.

---

## 13. Files added / modified by this PR

  - Added: `app/sim/__init__.py`
  - Added: `app/sim/simulation_clock.py`
  - Added: `app/sim/time_wall_guard.py`
  - Added: `tests/unit/test_simulation_clock_time_wall_guard.py`
  - Added: `docs/PHASE_11C_1D_D_A_SIMULATION_CLOCK_TIME_WALL_GUARD.md`
    (this file).
  - Modified: `docs/PROJECT_STATUS.md` (current-phase block
    prepended; prior 11C.1D-D entry preserved as historical
    context).
  - Modified: `docs/PHASE_GATE.md` (PR94 entry added to the
    *Open / Reserved phases* section).
  - Modified: `docs/CHANGELOG.md` (this PR's entry).

Files explicitly NOT touched: `app/risk/**`, `app/execution/**`,
`app/exchanges/**`, `app/telegram/**`, `app/config/**`,
`app/ai/**`, `app/safety/**`, `scripts/**`, `configs/**`,
`data/**`, `requirements.txt`, `pyproject.toml`, `.env*`.

---

## 14. Tests

Required test names (this PR ships all of them):

  1. `test_simulation_clock_starts_at_configured_utc_time`
  2. `test_simulation_clock_advances_forward_deterministically`
  3. `test_simulation_clock_cannot_move_backward_by_default`
  4. `test_time_wall_guard_allows_record_with_available_at_le_simulated_time`
  5. `test_time_wall_guard_rejects_future_record`
  6. `test_time_wall_guard_does_not_use_ingested_at_as_availability`
  7. `test_missing_available_at_creates_no_lookahead_violation`
  8. `test_filter_available_returns_allowed_and_violations_no_silent_drop`
  9. `test_1m_candle_final_ohlcv_invisible_before_close`
  10. `test_1m_candle_final_ohlcv_visible_after_close`
  11. `test_5m_candle_final_ohlcv_invisible_before_close`
  12. `test_unclosed_candle_field_access_creates_violation`
  13. `test_outcome_label_during_blind_window_creates_violation`
  14. `test_no_lookahead_violation_is_json_serializable`
  15. `test_phase_12_forbidden_everywhere`
  16. `test_auto_tuning_allowed_false_everywhere`
  17. `test_trade_authority_false_everywhere`
  18. `test_forbidden_fields_absent_in_all_outputs`
  19. `test_no_forbidden_app_imports_in_module_or_init`
  20. `test_no_deepseek_llm_telegram_binance_or_network_path`
  21. `test_deterministic_output`

Plus the extra defensive tests:

  - `test_parse_interval_seconds_closed_taxonomy`
  - `test_ensure_utc_aware_rejects_naive_datetime`
  - `test_historical_record_time_invariants`
  - `test_no_lookahead_violation_reason_and_severity_closed_enums`
  - `test_forbidden_output_fields_brief_mandated`
  - `test_time_wall_guard_does_not_steer_trades`

Run: `python -m pytest tests/unit/test_simulation_clock_time_wall_guard.py -q`.

---

## 15. Acceptance + next-allowed-phase

PR94 is marked **IN_REVIEW**. Maintainer-led review of the
implementation PR is the only path to **ACCEPTED**.

Successful PR94 acceptance only authorises:

  - **PR95 — Historical Market Store v0** (paper / read-only;
    requires its own gate, its own kickoff PR with brief /
    boundary / forbidden list, and its own acceptance evidence).

PR94 acceptance does **NOT** authorise:

  - PR96 / PR97 / PR98 / PR99 / PR100,
  - the Blind Walk-forward Runner,
  - live trading,
  - auto-tuning,
  - the DeepSeek hot path,
  - Telegram live outbound,
  - Phase 12.

**Phase 12 remains FORBIDDEN.**
