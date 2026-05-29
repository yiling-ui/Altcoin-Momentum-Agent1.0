# Phase 11C.1D-D-G — Blind Walk-forward Runner v0 (PR100)

> Strict blind walk-forward orchestrator. The **seventh**
> anti-future-lookahead infrastructure block of the strict blind
> walk-forward stack defined by Phase 11C.1D-D (PR93,
> the *Strict Blind Walk-forward Sim-Live Constitution*).
> Paper-only / report-only / sandbox-only. Phase 12 remains
> **FORBIDDEN**.

## Purpose

PR100 strings PR94..PR99 substrate (the SimulationClock + Time-Wall
Guard, the Historical Market Store, the ReplayFeedProvider, the
MockExchange + Pessimistic Fill Model, the Simulated Capital Flow +
Trade Ledger, the Telegram Sandbox Outbox) into the first version of
the strict forward-only historical sim-live blind runner. The runner
implements the `train` / `freeze` / `blind` / `score` /
`experience-update` loop that the Constitution requires, drives a
:class:`SimulationClock` from `window.blind_start` to
`window.blind_end`, pulls one batch per step from the
:class:`ReplayFeedProvider`, marks the
:class:`SimulatedCapitalFlowEngine` against the closed 1m candles in
each batch, forwards orders returned by an optional decision
callback to the :class:`MockExchange`, forwards every fill back into
the :class:`SimulatedCapitalFlowEngine` so the trade ledger and the
equity time-series stay consistent, writes a paper-only Telegram
sandbox transcript via the :class:`TelegramSandboxOutbox`, records
every :class:`NoLookaheadViolation` and every
:class:`BlindRunInvalidationReason`, and scores **only** after
`window.blind_end` (never inside the blind window).

## Relation to PR93 / PR94..PR99

| PR  | Module                                    | Role inside PR100                                       |
| --- | ----------------------------------------- | ------------------------------------------------------- |
| 93  | Constitution                              | Hard-pinned safety boundary, §5/§6/§7/§9/§F semantics   |
| 94  | `simulation_clock.py` / `time_wall_guard` | Forward-only clock, `available_at <= simulated_time`    |
| 95  | `historical_market_store.py`              | As-of record substrate, closed-candle visibility        |
| 96  | `replay_feed_provider.py`                 | Forward-only batch feed driving the runner              |
| 97  | `mock_exchange.py` / `pessimistic_fill_*` | Conservative simulated fills                            |
| 98  | `simulated_capital_flow.py` / `trade_ledger` | Simulated capital, equity time-series, trade ledger  |
| 99  | `telegram_sandbox_outbox.py`              | File-only Telegram transcript                           |
| 100 | `blind_walk_forward_runner.py` *(this PR)* | Orchestrates the strict blind walk-forward loop end-to-end |

PR100 reuses every PR94..PR99 source **verbatim**. PR100 does NOT
modify `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, or any other live-path module.

## train / freeze / blind / score / experience-update loop

1. **train** — descriptive only at v0. The runner accepts a
   :class:`BlindWalkForwardRunnerConfig` whose `window.train_start`
   / `window.train_end` describe the training segment. PR100 does
   not implement training; downstream PRs may attach a frozen,
   training-derived decision callback.
2. **freeze** — :meth:`prepare_manifest` builds a
   :class:`BlindRunManifest` whose hashes pin every input artefact
   (`config_hash`, `rule_hash`, `feature_schema_hash`,
   `data_manifest_hash`, `universe_manifest_hash`, `fee_model_hash`,
   `slippage_model_hash`, `latency_model_hash`, `outage_model_hash`,
   `fill_model_hash`). :meth:`freeze_artifacts` re-asserts the
   manifest is non-mutated and emits the run-start Telegram
   sandbox status entry.
3. **blind** — :meth:`run_blind_window` drives :meth:`step_once`
   until the replay finishes or `simulated_time >=
   window.blind_end`. Every step:
   1. processes previously-submitted orders against the new
      batch's closed bars (orders submitted at step `T` can fill
      only against bars at step `T+1` or later — the strict
      forward-only invariant for the order path);
   2. applies the batch's closed-candle marks to the capital flow;
   3. emits Telegram sandbox fill notices for any fills produced;
   4. invokes the optional decision callback (strategy-less in v0);
   5. submits new orders without an evaluation batch so they never
      see the same bar that produced the decision.
4. **score** — :meth:`score_after_window_close` runs **only** after
   `window.blind_end` and produces a :class:`BlindRunScore` with one
   of the closed statuses (`INSUFFICIENT_EVIDENCE`,
   `EVIDENCE_GENERATED`, `INVALIDATED_LOOKAHEAD_OR_DRIFT`,
   `FAILED_SAFETY_BOUNDARY`, `PARTIAL_EVIDENCE`).
5. **experience-update** — PR100 emits descriptive aggregates only
   (`generate_failure_ledger`, `generate_discovery_quality_ledger`).
   The runner NEVER writes a runtime config patch, NEVER mutates the
   Risk Engine, and NEVER mutates the Strategy / Execution / Capital
   layers.

## Manifest schema (`BlindRunManifest`)

| Field                            | Type            | Notes                                                |
| -------------------------------- | --------------- | ---------------------------------------------------- |
| `run_id`                         | `str`           | Deterministic; unique per run                        |
| `code_commit`                    | `str`           | Git commit / build id                                |
| `config_hash`                    | `sha256:<hex>`  | Frozen config artefact hash                          |
| `rule_hash`                      | `sha256:<hex>`  | Frozen rule artefact hash                            |
| `feature_schema_hash`            | `sha256:<hex>`  | Frozen feature schema artefact hash                  |
| `data_manifest_hash`             | `sha256:<hex>`  | Frozen data manifest artefact hash                   |
| `universe_manifest_hash`         | `sha256:<hex>`  | Frozen universe manifest artefact hash               |
| `train_start` / `train_end`      | UTC ISO-8601    | Training segment                                     |
| `blind_start` / `blind_end`      | UTC ISO-8601    | Blind segment                                        |
| `simulation_clock_start` / `…_end` | UTC ISO-8601 | Clock bounds (defaults to blind segment)             |
| `base_clock_step`                | `1m` (default)  | Must be `>= 1m`; `1m` is the v0 minimum              |
| `allowed_timeframes`             | tuple           | `("1m", "5m", "15m", "1h", "4h", "1d")` by default   |
| `fee_model_hash` / `slippage_model_hash` / `latency_model_hash` / `outage_model_hash` / `fill_model_hash` | `sha256:<hex>` | All frozen at manifest creation |
| `ai_enabled_state`               | `OFFLINE_ASOF_ONLY` / `OFFLINE_POST_WINDOW_ONLY` | AI is OFFLINE only |
| `telegram_sandbox_state`         | `SANDBOX_FILE_ONLY` / `DISABLED` | No real Telegram outbound      |
| `intrabar_ambiguity_policy`      | `WORST_CASE` / `AMBIGUOUS_INTRABAR_PATH` / `AMBIGUOUS` | Pessimistic |
| `phase_12_forbidden`             | `True`          | Hard-pinned                                          |
| `live_trading`                   | `False`         | Hard-pinned                                          |
| `exchange_live_orders`           | `False`         | Hard-pinned                                          |
| `binance_private_api_enabled`    | `False`         | Hard-pinned                                          |
| `auto_tuning_inside_blind_window`| `False`         | Hard-pinned                                          |
| `auto_tuning_allowed`            | `False`         | Hard-pinned                                          |

## 1m base clock step

PR100 v0 fixes the simulation base step at **1m**. Operators can
select any `allowed_timeframe` whose `parse_interval_seconds` is
`>= 1m`, but `1m` is both the default and the recommended setting
for a strict blind walk-forward run.

## Multi-timeframe closed-candle / as-of rule

The :class:`MultiTimeframeAsOfGuard` enforces, per timeframe:

  * the timeframe is in the allowed set,
  * the kline is **closed** at the consumer's `simulated_time`
    (`open_time + interval <= simulated_time`),
  * the record is **observable** at the consumer's `simulated_time`
    (`available_at <= simulated_time`).

The :class:`AsOfFeatureCache` is keyed by `as_of_time`. A consumer
that asks for a feature whose `as_of_time` is in the future of the
consumer's `simulated_time` receives `None` and the cache bumps a
future-access counter; values are NEVER disclosed before their
as-of time.

## AI as-of / post-window isolation

PR100 enforces three AI-isolation contracts even though no AI hot
path is wired in this phase:

  1. **Blind-window AI is OFFLINE** by default
     (`ai_blind_window_enabled=False`). The runner's
     :meth:`assert_blind_window_ai_evidence_bundle` rejects any
     bundle containing `tail_label` / `training_label` /
     `outcome` / `post_discovery_outcome` / `mfe` / `mae` /
     `future_replay` / `future_reflection` / `future_outcome` keys,
     and rejects any `evidence_refs` entry whose `available_at` is
     in the future of the consumer's `simulated_time`. Triggering
     either rejection records an `AI_OUTPUT_USED_AS_TRUTH_OR_LABEL`
     invalidation reason.
  2. **Post-window AI summary** is OFFLINE commentary only and is
     callable **only** after `window.blind_end`. The output carries
     `is_truth_layer_fact=False`, `is_training_label=False`,
     `is_tail_label=False`, `is_strategy_validation_sample=False`,
     `is_runtime_patch=False`, `is_ai_in_decision_chain=False`,
     `ai_authority="NONE"`.
  3. **AI output is commentary only** — under no circumstances may
     it become a Truth Layer fact, a training label, a tail label,
     a strategy validation sample, or a runtime config input. The
     Risk Engine, Execution FSM, Capital Flow Engine, and Strategy
     layers are completely off-limits to AI in this phase.

## No-lookahead violation handling

The runner forwards every :class:`NoLookaheadViolation` produced by
the :class:`ReplayFeedProvider` into its own ledger and records a
`FUTURE_RECORD_ACCESS` invalidation reason. The
`generate_failure_ledger` output captures one entry per violation;
the `no_lookahead_violations.json` artefact preserves the full list
plus invalidations and a re-pinned safety payload.

## Run invalidation rules (`BlindRunInvalidationReason`)

The closed taxonomy mirrors PR100 brief §9:

  * `FUTURE_RECORD_ACCESS`
  * `CONFIG_DRIFT`
  * `RULE_HASH_DRIFT`
  * `FEATURE_SCHEMA_DRIFT`
  * `DATA_MANIFEST_DRIFT_DURING_BLIND_WINDOW`
  * `UNIVERSE_MANIFEST_DRIFT_DURING_BLIND_WINDOW`
  * `TAIL_LABEL_LEAKAGE`
  * `POST_DISCOVERY_OUTCOME_LEAKAGE`
  * `REPLAY_REFLECTION_LEAKAGE`
  * `AI_OUTPUT_USED_AS_TRUTH_OR_LABEL`
  * `MANUAL_SAMPLE_DELETION`
  * `VALIDATION_TEST_TUNING`
  * `MISSING_FAILURE_LEDGER`
  * `UNLOGGED_RUNTIME_OVERRIDE`

Any non-empty invalidation tuple flips the run status to
`INVALIDATED_LOOKAHEAD_OR_DRIFT`.

## Status taxonomy (`BlindRunStatus`)

  * `INSUFFICIENT_EVIDENCE` — zero batches consumed and zero ledger
    entries.
  * `EVIDENCE_GENERATED` — clean run, evidence-ready, no
    invalidations, no safety-boundary breach.
  * `INVALIDATED_LOOKAHEAD_OR_DRIFT` — at least one closed-taxonomy
    invalidation reason recorded.
  * `FAILED_SAFETY_BOUNDARY` — safety-boundary breach observed
    (e.g., `live_trading` flipped to `True`, real Telegram outbound
    detected, Binance private API reachable).
  * `PARTIAL_EVIDENCE` — clean run but at least one
    partial-evidence reason recorded (data gaps that prevented full
    coverage).

## Output artefacts

Every run produces, under
`data/reports/blind_walk_forward/<run_id>/`:

  * `blind_run_manifest.json`
  * `trade_ledger.json`
  * `equity_timeseries.json`
  * `discovery_quality_ledger.json`
  * `failure_ledger.json`
  * `telegram_sandbox_transcript.md`
  * `blind_walk_forward_report.json`
  * `blind_walk_forward_report.md`
  * `no_lookahead_violations.json`

Every payload re-pins the safety boundary (`live_trading=False`,
`exchange_live_orders=False`, `binance_private_api_enabled=False`,
`telegram_outbound_enabled=False`,
`telegram_live_command_authority=False`,
`telegram_production_channel_enabled=False`,
`ai_trade_authority=False`, `trade_authority=False`,
`auto_tuning_inside_blind_window=False`,
`auto_tuning_allowed=False`, `phase_12_forbidden=True`) and is
checked against the project-wide `FORBIDDEN_OUTPUT_FIELDS` guard.
No payload may carry `runtime_config_patch`, `symbol_limit_patch`,
`threshold_patch`, `candidate_pool_patch`, `regime_weight_patch`,
`strategy_parameter_patch`, `apply_change`, `deploy_change`,
`enable_live`, `live_ready`, `trading_approved`, `api_key`,
`api_secret`, `real_order_id`, `exchange_order_id`, or
`real_account_id`. The trade ledger may carry a simulated
`order_type` / simulated `side` (these are not in the
`FORBIDDEN_OUTPUT_FIELDS` set), but every entry carries
`simulated_only=True`, `no_live_order=True`, `trade_authority=False`.

## What this PR does NOT authorise

  * **NOT** live trading. `live_trading=False`. `exchange_live_orders=False`.
    `real_capital=False`. `real_exchange_order_path=False`.
  * **NOT** auto-tuning. `auto_tuning_inside_blind_window=False`.
    `auto_tuning_allowed=False`. The runner never emits
    `runtime_config_patch` / `threshold_patch` / `symbol_limit_patch` /
    `candidate_pool_patch` / `regime_weight_patch` /
    `strategy_parameter_patch`.
  * **NOT** real Telegram outbound. `telegram_outbound_enabled=False`.
    `telegram_live_command_authority=False`.
    `telegram_production_channel_enabled=False`. The transcript is
    **file-only** Markdown / JSONL.
  * **NOT** the Binance private API. No signed endpoint, no private
    websocket, no listenKey, no `account` / `order` / `position` /
    `leverage` / `margin` endpoint reachable.
  * **NOT** Phase 12. `phase_12_forbidden=True`. Phase 12 remains
    **FORBIDDEN** by this phase, by the entire PR94..PR100 stack,
    and by the Constitution.

## What a successful PR100 acceptance authorises

A successful PR100 acceptance only authorises a paper-only
**blind-run checkpoint / operator evidence run**. It does NOT
authorise small-cap live trading, automatic parameter optimisation,
real Telegram outbound, real exchange orders, the Binance private
API, or Phase 12.

## Files

| File                                                             | Status   |
| ---------------------------------------------------------------- | -------- |
| `app/sim/blind_walk_forward_manifest.py`                         | NEW      |
| `app/sim/blind_walk_forward_scoring.py`                          | NEW      |
| `app/sim/blind_walk_forward_runner.py`                           | NEW      |
| `app/sim/__init__.py`                                            | EXTENDED |
| `scripts/run_blind_walk_forward.py`                              | NEW      |
| `tests/unit/test_blind_walk_forward_runner.py`                   | NEW      |
| `docs/PHASE_11C_1D_D_G_BLIND_WALK_FORWARD_RUNNER.md`             | NEW      |
| `docs/PROJECT_STATUS.md`                                         | UPDATED  |
| `docs/PHASE_GATE.md`                                             | UPDATED  |
| `docs/CHANGELOG.md`                                              | UPDATED  |

No file under `app/risk/`, `app/execution/`, `app/exchanges/`,
`app/telegram/`, `app/config/`, `app/ai/`, `app/safety/`,
`app/replay/`, `app/reflection/`, `app/paper_shadow/`,
`app/sandbox/`, `app/state_machine/`, `app/scanner/`,
`app/regime/`, `app/market_data/`, `app/market_data_public/`,
`app/universe/`, `app/liquidity/`, `app/manipulation/`,
`app/monitoring/`, `app/database/`, `app/exports/`, `app/incidents/`,
`app/learning/`, `app/llm/`, `app/paper_run/`,
`app/reconciliation/`, `app/confirmation/`, `app/capital/`,
`app/core/`, `app/main.py` is touched. The existing PR94..PR99
sources (`app/sim/simulation_clock.py`, `app/sim/time_wall_guard.py`,
`app/sim/historical_market_store.py`,
`app/sim/replay_feed_provider.py`, `app/sim/mock_exchange.py`,
`app/sim/pessimistic_fill_model.py`,
`app/sim/simulated_capital_flow.py`, `app/sim/trade_ledger.py`,
`app/sim/telegram_sandbox_outbox.py`) are reused **verbatim** and
are NOT modified by this PR.

## Test command

```
python -m pytest tests/unit/test_blind_walk_forward_runner.py -q
```

The dedicated test file ships **31 PASSING tests** that cover the
30 brief-mandated scenarios plus one bonus
`INSUFFICIENT_EVIDENCE`-on-empty-run check on the pure scoring
helper. The full unit suite remains green
(`python -m pytest tests/unit -q` — 3584 PASSING).
